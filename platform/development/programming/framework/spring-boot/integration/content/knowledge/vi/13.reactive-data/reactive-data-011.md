# Phối hợp R2DBC với công cụ migration dùng JDBC

## 1. Bài toán trong một hệ thống tích hợp Spring Boot

Giả sử dịch vụ tích hợp nhận sự kiện từ HTTP, ghi dữ liệu nghiệp vụ và một bản ghi *outbox* vào PostgreSQL, sau đó có tiến trình gửi sự kiện tới message broker. Dịch vụ muốn dùng **Spring Data R2DBC** để truy cập dữ liệu theo mô hình reactive, nhưng vẫn phải tạo bảng, thay đổi cột, bổ sung chỉ mục và quản lý lịch sử schema một cách có kiểm soát.

Vấn đề là **R2DBC và công cụ migration giải quyết hai công việc khác nhau**:

- **R2DBC** cung cấp `ConnectionFactory` và API truy cập cơ sở dữ liệu theo Reactive Streams, thích hợp cho luồng xử lý nghiệp vụ không chặn trong Spring WebFlux.
- **Flyway/Liquibase** quản lý phiên bản schema và dữ liệu tham chiếu bằng các migration có thứ tự, kiểm tra lịch sử áp dụng và phát hiện sai lệch. Trong cấu hình phổ biến với cơ sở dữ liệu quan hệ, các công cụ này sử dụng **JDBC**, tức là thao tác chặn luồng.
- **Spring Boot** có thể cấu hình hai cơ chế kết nối tới **cùng một database vật lý**: JDBC phục vụ migration ở giai đoạn khởi tạo hoặc job triển khai; R2DBC phục vụ truy vấn trong thời gian ứng dụng chạy.

Việc có JDBC trên classpath **không khiến các truy vấn R2DBC trở thành JDBC**. Tương tự, dùng R2DBC cho nghiệp vụ **không đồng nghĩa** Flyway/Liquibase sẽ tự chạy qua R2DBC.

### Sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    Deploy["Khởi động / pipeline triển khai"] --> Migration["Flyway hoặc Liquibase"]
    Migration --> JDBC["JDBC driver"]
    JDBC --> DB[("PostgreSQL: schema + dữ liệu")]
    App["HTTP / broker adapter"] --> Service["Reactive service"]
    Service --> R2DBC["Spring Data R2DBC / ConnectionFactory"]
    R2DBC --> DB
    DB --> Outbox["Bảng nghiệp vụ và integration_outbox"]
~~~

| Tiêu chí | Nhánh migration | Nhánh nghiệp vụ |
|---|---|---|
| Mục đích | DDL, phiên bản schema, dữ liệu khởi tạo có kiểm soát | Đọc/ghi bản ghi của ứng dụng |
| API kết nối | JDBC `DataSource` hoặc kết nối JDBC riêng của Flyway/Liquibase | R2DBC `ConnectionFactory` |
| URL PostgreSQL | `jdbc:postgresql://host:5432/db` | `r2dbc:postgresql://host:5432/db` |
| Thời điểm | Trước khi phục vụ lưu lượng, hoặc trong job triển khai | Khi xử lý request, message, scheduler |
| Tính chất I/O | Blocking | Reactive, không chặn theo hợp đồng của driver |
| Giao dịch | Migration quản lý theo khả năng của công cụ/database | `R2dbcTransactionManager` hoặc `TransactionalOperator` |
| Quyền truy cập lý tưởng | Tài khoản có quyền DDL cần thiết | Tài khoản ứng dụng được giới hạn quyền DML |

**Nguyên tắc cốt lõi:** hai URL phải trỏ đến **đúng database và schema dự kiến**, nhưng không nhất thiết dùng cùng tài khoản. Việc migration thành công ở database A không giúp ứng dụng R2DBC đang kết nối nhầm database B.

## 2. Chọn cách phối hợp

Có hai cách vận hành thường gặp:

**Cách A — migration khi khởi động ứng dụng.** Spring Boot chạy Flyway/Liquibase đồng bộ trong quá trình tạo application context; khi migration thất bại thì ứng dụng không hoàn tất khởi động bình thường. Cách này thuận tiện cho phát triển, thử nghiệm và dịch vụ có quy trình triển khai đơn giản.

**Cách B — migration là một bước triển khai riêng.** Pipeline hoặc Kubernetes Job chạy công cụ migration trước, xác nhận thành công rồi mới triển khai phiên bản ứng dụng dùng schema mới. Cách này phù hợp khi có nhiều replica, migration lâu, quyền DDL được tách riêng hoặc cần kiểm soát thời điểm thay đổi cấu trúc dữ liệu.

Không chạy migration trong controller, consumer message, reactive operator hay một `Mono.fromCallable(...)` được kích hoạt bởi request. Dời JDBC sang scheduler có thể tránh chặn event loop, nhưng **không** giải quyết bài toán quản lý schema và thứ tự triển khai.

## 3. Ví dụ hoàn chỉnh: PostgreSQL, Flyway và Spring Data R2DBC

Ví dụ sau dùng Flyway để tạo bảng `integration_outbox`, sau đó dùng R2DBC để đọc những bản ghi đang chờ chuyển tới broker. Tên bảng và khóa `event_key` minh họa cách dịch vụ tích hợp kiểm soát phát sự kiện lặp.

### 3.1. Khai báo thư viện

Với dự án **Spring Boot 4.x** dùng Spring Boot BOM, phần phụ thuộc Maven có thể gồm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Flyway sử dụng JDBC để chạy migration. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Với **Spring Boot 3.x**, thường khai báo `org.flywaydb:flyway-core` thay cho starter Flyway của Boot 4; vẫn cần module hỗ trợ PostgreSQL tương ứng với phiên bản Flyway và JDBC driver. Giữ phiên bản phụ thuộc theo BOM của phiên bản Spring Boot đang dùng, tránh tự ghép các bản Flyway không tương thích. Phần cấu hình hai kết nối dưới đây giữ cùng ý tưởng ở hai dòng phiên bản.

Chỉ sử dụng một trong hai công cụ Flyway và Liquibase làm **nguồn quản lý schema chính** của database. Thêm cả hai thư viện rồi để cả hai cùng khởi tạo schema sẽ khiến thứ tự và lịch sử migration khó kiểm soát.

### 3.2. Hai cấu hình URL độc lập

`src/main/resources/application.yml`:

~~~yaml
spring:
  r2dbc:
    url: ${APP_R2DBC_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}

  flyway:
    enabled: true
    url: ${MIGRATION_JDBC_URL}
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
    locations: classpath:db/migration

  sql:
    init:
      mode: never
~~~

Ví dụ hai biến kết nối trong môi trường phát triển:

~~~text
APP_R2DBC_URL=r2dbc:postgresql://localhost:5432/integration_db
MIGRATION_JDBC_URL=jdbc:postgresql://localhost:5432/integration_db
~~~

Các biến tài khoản/mật khẩu cần được cấp qua cấu hình môi trường hoặc secret manager. Ở production, `APP_DB_USER` nên có quyền DML cần thiết còn `MIGRATION_DB_USER` có quyền tạo/sửa schema theo quy trình triển khai.

**Vì sao cấu hình `spring.flyway.url`?** Khi có R2DBC `ConnectionFactory`, Spring Boot thông thường không tự cấu hình JDBC `DataSource` mặc định. Khai báo `spring.flyway.url` cùng thông tin xác thực giúp Flyway tự dùng kết nối JDBC của nó; không phải thêm một `DataSource` dùng chung vào toàn bộ reactive service chỉ để migration. Nếu dự án chủ động quản lý nhiều JDBC `DataSource`, có thể cấu hình bean dành cho Flyway riêng, nhưng phải chỉ rõ bean đó để tránh migrate nhầm cơ sở dữ liệu.

`spring.sql.init.mode: never` tắt cơ chế chạy `schema.sql`/`data.sql` mặc định để không có hai cơ chế cùng tạo schema. Với ứng dụng có JPA song song, cũng cần kiểm soát `hibernate.hbm2ddl.auto` hoặc `spring.jpa.hibernate.ddl-auto`, tránh ORM tự cập nhật schema ngoài lịch sử migration.

### 3.3. Tạo migration có phiên bản

Đặt tệp tại `src/main/resources/db/migration/V1__create_integration_outbox.sql`:

~~~sql
CREATE TABLE integration_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(120) NOT NULL UNIQUE,
    destination VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_integration_outbox_status
        CHECK (status IN ('PENDING', 'SENT', 'FAILED'))
);

CREATE INDEX idx_integration_outbox_pending
    ON integration_outbox (created_at, id)
    WHERE status = 'PENDING';
~~~

Flyway tìm những migration theo quy ước tên `V<version>__<description>.sql`. Tên sử dụng **hai dấu gạch dưới** trước phần mô tả; số phiên bản chỉ tăng theo lịch sử thay đổi. Bảng `flyway_schema_history` ghi phiên bản, checksum và kết quả áp dụng để tránh chạy lại migration đã hoàn tất.

Khi yêu cầu nghiệp vụ bổ sung số lần gửi lại, tạo **tệp mới** `V2__add_outbox_retry_count.sql`:

~~~sql
ALTER TABLE integration_outbox
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
~~~

Không chỉnh sửa `V1` sau khi đã triển khai đến môi trường chia sẻ: checksum sẽ thay đổi và Flyway có thể từ chối xác thực. Việc sửa lỗi schema được thực hiện bằng migration tiếp theo hoặc quy trình phục hồi được kiểm soát.

Đoạn DDL trên dành cho PostgreSQL. Với hệ quản trị khác, kiểu `UUID`, `JSONB`, `TIMESTAMPTZ`, partial index và khả năng transactional DDL cần được chuyển đổi hoặc kiểm chứng riêng.

### 3.4. Đọc dữ liệu bằng R2DBC sau migration

Ví dụ một adapter chỉ đọc những sự kiện chưa gửi, sử dụng `DatabaseClient` của Spring Data R2DBC:

~~~java
package example.integration.outbox;

import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

record PendingEvent(UUID id, String eventKey, String destination, String payload) {}

@Repository
public class OutboxReader {
    private final DatabaseClient databaseClient;

    public OutboxReader(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PendingEvent> findPending(int limit) {
        return databaseClient.sql("""
                SELECT id, event_key, destination, payload::text AS payload
                  FROM integration_outbox
                 WHERE status = 'PENDING'
                 ORDER BY created_at, id
                 LIMIT :limit
                """)
            .bind("limit", limit)
            .map((row, metadata) -> new PendingEvent(
                row.get("id", UUID.class),
                row.get("event_key", String.class),
                row.get("destination", String.class),
                row.get("payload", String.class)))
            .all();
    }
}
~~~

Trong PostgreSQL, `payload::text` chuyển JSONB thành văn bản để minh họa cách ánh xạ đơn giản; hệ thống thực có thể dùng codec/kiểu dữ liệu JSON của driver. `findPending` tạo một `Flux`: truy vấn sẽ thực thi khi có subscriber, dùng kết nối R2DBC và **không cần** gọi JDBC/Flyway trong phương thức này.

Trong luồng outbox thực tế còn phải có cơ chế *claim/lock*, cập nhật trạng thái, retry và xử lý phát lặp; câu `SELECT` phía trên chỉ minh họa tương tác với **bảng đã được migration tạo ra**, chưa phải thuật toán gửi sự kiện an toàn cho nhiều worker.

### 3.5. Trình tự khởi động dự kiến

1. Spring Boot đọc `spring.flyway.*` và `spring.r2dbc.*`.
2. Flyway kết nối PostgreSQL bằng JDBC, đối chiếu `flyway_schema_history` rồi áp dụng migration chưa chạy theo thứ tự.
3. Nếu migration lỗi, quá trình khởi tạo ứng dụng phải thất bại và readiness không được báo sẵn sàng phục vụ.
4. Khi migration hoàn tất, các thành phần truy cập dữ liệu trong runtime dùng `ConnectionFactory` R2DBC.
5. Request HTTP, consumer và bộ gửi outbox sử dụng schema đã được cập nhật.

Spring Boot có cơ chế nhận diện database initializer và quan hệ phụ thuộc khi khởi động. Tuy nhiên, bean tự viết mà **chủ động truy cập database trong lúc khởi tạo** có thể cần `@DependsOnDatabaseInitialization` hoặc một cơ chế thứ tự rõ ràng; không nên giả định mọi `@PostConstruct` truy vấn đều tự chờ Flyway.

## 4. Ranh giới giao dịch và độ tin cậy của luồng tích hợp

**Migration JDBC và giao dịch R2DBC là hai phạm vi tách biệt.** Giao dịch mà Flyway mở khi chạy DDL không thể được gộp vào `@Transactional` reactive của một request. Dùng chung database chỉ đồng nghĩa hai nhánh nhìn thấy cùng schema/dữ liệu đã commit; nó không tạo giao dịch phân tán qua JDBC, R2DBC và broker.

Trong ví dụ outbox, nếu cần bảo đảm việc ghi dữ liệu nghiệp vụ và bản ghi outbox cùng thành công hoặc cùng thất bại, hãy dùng **cùng một giao dịch R2DBC**:

~~~java
// Minh họa ý tưởng: cả hai thao tác phải dùng cùng R2DBC connection/transaction.
Mono<Void> storeAndQueue(Command command) {
    return transactionalOperator.transactional(
        saveBusinessRecord(command)
            .then(insertOutboxRecord(command))
    );
}
~~~

Trong đó `saveBusinessRecord` và `insertOutboxRecord` là các phương thức R2DBC trả về `Mono`, còn `transactionalOperator` dùng reactive transaction manager tương ứng. Chúng không phải API có sẵn để sao chép nguyên khối. Sau commit, một tiến trình khác gửi message tới broker. Phía nhận vẫn cần **idempotency**, bởi gửi lại có thể tạo sự kiện trùng dù việc ghi outbox đã nguyên tử.

Không gọi `Flyway.migrate()`, `JdbcTemplate` hoặc `DataSource.getConnection()` trên event loop của HTTP/consumer reactive. JDBC có thể hợp lý tại startup hoặc trong công việc nền được bố trí riêng; không nên làm chặn chuỗi xử lý reactive chỉ để truy vấn thông thường.

## 5. Vận hành migration an toàn ở nhiều môi trường

### 5.1. Môi trường phát triển và staging

Ở môi trường thử nghiệm, việc để Spring Boot tự chạy Flyway khi startup giúp phát hiện thiếu migration sớm. Cần dùng cùng bộ migration cho database mới và database đã có dữ liệu, rồi kiểm tra API R2DBC vẫn đọc/ghi đúng.

Với database đã tồn tại trước khi đưa Flyway vào, phải khảo sát schema thật và xác lập **baseline** có kiểm soát. Không tùy tiện bật `baselineOnMigrate` để che lỗi hoặc coi schema hiện hữu đã đúng khi chưa xác minh.

### 5.2. Production và nhiều replica

Khi scale nhiều instance, không nên dựa vào việc từng replica tự sửa schema trong lúc nhận request. Dù công cụ migration có cơ chế phối hợp/khóa để tránh áp dụng cùng một migration đồng thời, các instance cũ và mới vẫn có thể cùng truy cập database trong một đợt rolling deployment.

Một quy trình triển khai điển hình:

1. Build artifact chứa migration đã được review, thử trên bản sao dữ liệu phù hợp.
2. Chạy Flyway bằng một deployment job có quyền DDL và cấu hình JDBC đúng database đích.
3. Chỉ sau khi job thành công, triển khai ứng dụng R2DBC mới; nếu migration lỗi thì dừng rollout.
4. Với chế độ migration tách riêng, tắt Flyway ở runtime ứng dụng bằng `spring.flyway.enabled=false` (hoặc không đưa công cụ migration vào runtime).
5. Theo dõi readiness, lỗi SQL, độ trễ truy vấn và backlog/retry của outbox hoặc consumer sau triển khai.

Đối với thay đổi không tương thích ngược, dùng chiến lược **expand → migrate/backfill → contract**. Ví dụ: thêm cột mới mà code cũ vẫn chạy được; triển khai code đọc/ghi tương thích; backfill theo lô; cuối cùng mới xóa cột cũ khi không còn replica sử dụng. Với bảng lớn, đánh giá thời gian giữ khóa, chi phí tạo chỉ mục, khả năng rollback DDL của database và lưu lượng hiện tại.

### 5.3. Quyền và cấu hình

- Dùng tài khoản migration cho DDL; tài khoản R2DBC có quyền tối thiểu cần cho truy vấn/nghiệp vụ. Giới hạn quyền của tài khoản chạy application.
- Xác minh **host, port, database, schema/search path** của hai nhánh ở từng profile; cùng tên database ở hai host khác nhau vẫn là hai nơi độc lập.
- Mật khẩu đưa qua secret/config bên ngoài mã nguồn; bật TLS theo yêu cầu hạ tầng và driver tương ứng.
- Theo dõi lịch sử migration, kết quả pipeline, thời gian khởi động, lỗi `relation does not exist`, lỗi checksum/permission và lỗi chuyển đổi dữ liệu sau migration.
- Nếu buộc phải chạy JDBC trong cùng service, kiểm soát số kết nối JDBC và R2DBC riêng. Hai giao thức không tự chia sẻ một connection pool.

## 6. Dùng Liquibase thay Flyway

Liquibase cũng dùng JDBC trong mô hình này; thay phần Flyway bằng Liquibase và cấu hình đường dẫn changelog, ví dụ:

~~~yaml
spring:
  r2dbc:
    url: ${APP_R2DBC_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}
  liquibase:
    enabled: true
    url: ${MIGRATION_JDBC_URL}
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  sql:
    init:
      mode: never
~~~

Với Liquibase, dùng dependency tương ứng cho phiên bản Spring Boot đang chạy (ví dụ `liquibase-core` ở Boot 3.x hoặc starter Liquibase ở Boot 4.x) cùng PostgreSQL JDBC driver. Lịch sử thay đổi được quản lý bởi changelog và các bảng như `DATABASECHANGELOG`, `DATABASECHANGELOGLOCK`. Không đồng thời giữ cả `spring.flyway.enabled=true` và `spring.liquibase.enabled=true` trên cùng schema nếu chưa có thiết kế chuyển đổi công cụ rõ ràng.

| Nhu cầu | Flyway | Liquibase |
|---|---|---|
| Quản lý migration SQL có thứ tự | Tệp SQL phiên bản, quy ước `V...__....sql` | Changelog SQL/XML/YAML/JSON, changeset có ID/author |
| Lịch sử đã chạy | `flyway_schema_history` | `DATABASECHANGELOG` |
| Khóa/phối hợp khi migration | Do Flyway và database xử lý theo cơ chế tương ứng | Có cơ chế changelog lock |
| Dùng với R2DBC runtime | Cấu hình JDBC riêng | Cấu hình JDBC riêng |
| Lựa chọn | Ưu tiên SQL migration đơn giản, dễ review | Phù hợp khi cần hệ changeset/changelog và tính năng tương ứng |

Việc chọn công cụ phụ thuộc cách tổ chức thay đổi schema; cả hai đều không thay thế trách nhiệm bảo đảm tương thích giữa phiên bản ứng dụng và schema.

## 7. Kiểm thử phối hợp JDBC migration + R2DBC

Kiểm thử có giá trị nhất là một **integration test dùng PostgreSQL thật** (có thể cung cấp qua Testcontainers), vì H2 hoặc mock không phản ánh đầy đủ `JSONB`, kiểu thời gian, khóa và DDL của PostgreSQL.

Tạo container PostgreSQL dùng chung cho cả nhánh:

~~~text
spring.r2dbc.url      = r2dbc:postgresql://<test-host>:<test-port>/<test-db>
spring.flyway.url     = jdbc:postgresql://<test-host>:<test-port>/<test-db>
spring.r2dbc.username = <test-user>
spring.flyway.user    = <test-user>
~~~

Các thuộc tính trên chỉ minh họa mapping; trong test nên cấp giá trị động từ container (chẳng hạn qua `@DynamicPropertySource`) và chỉ dùng mật khẩu thử nghiệm.

Các ca kiểm thử cần bao phủ:

1. **Database trống:** startup chạy `V1`, bảng `integration_outbox` và chỉ mục tồn tại; truy vấn R2DBC chạy được.
2. **Khởi động lần hai:** migration đã hoàn tất không bị áp dụng lặp; lịch sử phiên bản nhất quán.
3. **Tiến hóa schema:** thêm `V2`, dữ liệu `V1` vẫn đọc được và truy vấn mới hoạt động.
4. **Sai cấu hình:** JDBC migration trỏ nhầm database hoặc dùng tài khoản thiếu quyền phải được phát hiện trước khi phục vụ lưu lượng.
5. **Migration lỗi:** script SQL lỗi phải khiến job/startup thất bại; không nuốt lỗi rồi cho application phục vụ trên schema chưa hoàn chỉnh.
6. **Checksum thay đổi:** sửa tệp version đã áp dụng phải gây cảnh báo/xác thực thất bại; không tự động `repair` trong mọi trường hợp.
7. **Ghi nghiệp vụ cùng outbox:** khi chèn outbox thất bại, giao dịch R2DBC phải rollback cả thao tác nghiệp vụ; khi retry với cùng `event_key`, khóa unique giúp phát hiện ghi trùng.

Trong hệ thống tích hợp có message broker, còn phải thử gửi trùng, crash sau khi publish nhưng trước khi cập nhật trạng thái, retry/backoff và tương thích schema giữa nhiều replica. Đây là kiểm thử của **luồng dữ liệu**, khác với việc migration chạy thành công.

## 8. Sự cố thường gặp và cách chẩn đoán

| Hiện tượng | Khả năng thường gặp | Kiểm tra/khắc phục |
|---|---|---|
| Flyway không khởi chạy | Thiếu starter/auto-configuration hoặc `spring.flyway.enabled=false` | Kiểm tra dependency theo phiên bản Boot, cấu hình và startup log |
| Báo thiếu `DataSource` hoặc không tìm thấy JDBC driver | Ứng dụng chỉ có R2DBC; chưa khai báo JDBC URL/driver | Thêm PostgreSQL JDBC driver và `spring.flyway.url`, user, password |
| Báo PostgreSQL không được hỗ trợ | Thiếu module Flyway theo database ở các bản Flyway yêu cầu module riêng | Thêm `flyway-database-postgresql` tương thích |
| `relation "integration_outbox" does not exist` | Migration không chạy, chạy sai DB/schema hoặc truy vấn quá sớm | So khớp JDBC/R2DBC URL + schema, history table và thứ tự khởi tạo |
| Validate/checksum lỗi | Đã sửa migration từng được áp dụng hoặc database bị drift | So sánh bản phát hành và lịch sử; tạo migration sửa lỗi thay vì sửa lịch sử tùy tiện |
| Startup lâu / timeout | DDL tốn thời gian, khóa bảng, tranh chấp migration | Đo thời gian migration, tối ưu DDL, cân nhắc job triển khai riêng |
| Độ trễ tăng hoặc cảnh báo blocking | Gọi JDBC trong luồng WebFlux | Giữ JDBC ở startup/job; dùng R2DBC cho truy vấn runtime |
| Chạy tốt local nhưng lỗi staging | Khác profile, quyền, tên schema, mạng, TLS hoặc phiên bản PostgreSQL | Kiểm tra cấu hình hiệu lực và migration log cho từng môi trường |

## 9. Những điểm cần tự giải thích được

- Vì sao một reactive service vẫn hợp lý khi có JDBC driver trên classpath? Ranh giới nào bảo đảm JDBC không chặn request?
- Khi cấu hình đồng thời `spring.r2dbc.url` và `spring.flyway.url`, điều gì chứng minh chúng nhắm tới cùng database/schema?
- Vì sao `@Transactional` của R2DBC không bao trùm Flyway và việc publish message tới broker?
- Nếu có năm replica và cần thêm cột bắt buộc, sẽ triển khai migration, code và backfill theo thứ tự nào để các phiên bản cùng chạy an toàn?
- Sẽ phát hiện ở đâu nếu migration thành công nhưng API mới vẫn nhận lỗi `relation does not exist`?

**Kết luận kỹ thuật:** Trong Spring Boot Integration, dùng **JDBC cho công việc thay đổi schema có kiểm soát** và **R2DBC cho truy cập dữ liệu runtime** là một cách phối hợp hợp lý. Chất lượng tích hợp phụ thuộc vào cùng đích database, thứ tự triển khai, kiểm soát giao dịch ở đúng lớp, khả năng xử lý lỗi/duplicate, kiểm thử với database thật và quan sát toàn bộ luồng.

### Tài liệu tham khảo

- Spring Boot — [Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway/Liquibase, thứ tự khởi tạo và lưu ý tránh nhiều cơ chế tạo schema.
- Spring Boot — [SQL Databases / Using R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html): `ConnectionFactory`, thuộc tính `spring.r2dbc.*` và quan hệ với JDBC `DataSource`.
- Flyway — [PostgreSQL Database](https://documentation.red-gate.com/fd/postgresql-database-277579325.html): JDBC driver và module hỗ trợ PostgreSQL.
