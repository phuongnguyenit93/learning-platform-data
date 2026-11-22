# Tích hợp Spring Data JDBC và ranh giới với JPA

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tích hợp các hệ thống qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Một luồng thực tế thường cần lưu đơn hàng vào PostgreSQL, phát sự kiện bằng transactional outbox, xử lý trùng lặp từ message broker và đọc dữ liệu để gọi downstream. Việc chọn **Spring Data JDBC**, **Spring Data JPA**, `JdbcTemplate` hay **jOOQ** ảnh hưởng đến ranh giới dữ liệu, transaction, SQL được tạo, tối ưu truy vấn và khả năng phục hồi.

Spring Data JDBC cung cấp **repository và mapping theo relational aggregate**, nhưng **không có JPA persistence context**. Nó phù hợp khi muốn biểu diễn rõ phần dữ liệu được lưu cùng nhau, cập nhật tường minh, không phụ thuộc lazy loading/dirty checking. Spring Data JPA bổ sung JPA entity lifecycle, association mapping, persistence context và ORM sâu hơn. `JdbcTemplate`/`JdbcClient` cho phép truy cập SQL trực tiếp; jOOQ đặc biệt mạnh ở truy vấn SQL phức tạp có kiểu.

Bài thuộc chương **JDBC và jOOQ**, chủ đề **Tích hợp Spring Data JDBC và ranh giới với JPA**. Nội dung gắn vào bối cảnh cấu hình kết nối, hợp đồng dữ liệu, giao dịch, lỗi, idempotency, kiểm thử và observability của các luồng tích hợp Spring Boot.

Sau bài học, bạn có thể:

1. Phân biệt JDBC driver, `DataSource`, `JdbcTemplate`, `JdbcClient`, Spring Data JDBC repository, JPA và jOOQ.
2. Thiết kế **aggregate root**, child entities và references đúng theo Spring Data JDBC.
3. Dùng `@Table`, `@Id`, `@MappedCollection`, `@Version`, `CrudRepository` và `save()`.
4. Hiểu vì sao Spring Data JDBC không có JPA dirty checking, lazy loading hoặc managed entity graph.
5. Biết khi nào dùng repository và khi nào cần SQL projection, JdbcClient hoặc jOOQ.
6. Đặt local transaction đúng ranh giới, kết hợp outbox và idempotency để gửi HTTP/broker an toàn.
7. Kiểm thử mapping/optimistic locking/rollback/migration bằng PostgreSQL Testcontainers.
8. Chẩn đoán SQL chậm, connection pool exhaustion, contention và những lỗi do chọn sai abstraction.

> **Nguyên tắc:** Spring Data JDBC là *aggregate-oriented persistence*, không phải “JPA tối giản với ít tính năng hơn”. Nó chọn **một mô hình persistence khác**, nên việc chuyển từ JPA sang JDBC không chỉ là đổi dependency.

## 1. Bức tranh các tầng SQL trong Spring Boot

~~~mermaid
flowchart TD
    S["OrderService / IntegrationFlow"] --> R["Spring Data JDBC Repository"]
    S --> J["JdbcTemplate / JdbcClient"]
    S --> Q["jOOQ DSLContext"]
    S --> P["Spring Data JPA Repository"]
    R --> M["Spring Data JDBC Relational Mapping"]
    J --> SQL["SQL tường minh"]
    Q --> SQL
    P --> E["JPA EntityManager / Hibernate"]
    M --> DS["DataSource / HikariCP"]
    SQL --> DS
    E --> DS
    DS --> DB["PostgreSQL / MySQL / SQL Server"]
~~~

| Thành phần | Vai trò | Không tự cung cấp |
| --- | --- | --- |
| JDBC driver | Nói giao thức SQL với database | Domain mapping và transaction nghiệp vụ |
| `DataSource`/HikariCP | Cấp, quản lý và tái sử dụng JDBC connections | Repository API |
| `JdbcTemplate` | Thực thi SQL, bind parameters, map results | Aggregate lifecycle |
| `JdbcClient` | Fluent SQL API trên Spring JDBC (Spring Framework 6.1+) | ORM hoặc JPA persistence context |
| **Spring Data JDBC** | Lưu relational aggregate qua Spring Data repository | Lazy association/dirty checking kiểu JPA |
| **jOOQ** | SQL DSL có kiểu, code generation, JOIN/CTE/window | JPA managed entity |
| **Spring Data JPA** | ORM entities/relationships, persistence context, dirty checking | SQL luôn tối giản hoặc không có N+1 |

Các lớp có thể **cùng tồn tại** trên một `DataSource`, nhưng muốn tham gia cùng transaction phải đảm bảo infrastructure/transaction manager giống nhau. Một `DSLContext` tự tạo ngoài Spring có thể dùng connection khác, không tự rollback cùng repository.

## 2. Thiết kế theo aggregate root

Trong Domain-Driven Design, **aggregate** là nhóm dữ liệu cần nhất quán cùng nhau; mọi thay đổi đi qua **aggregate root**. Ví dụ:

~~~mermaid
flowchart TD
    O["PurchaseOrder — aggregate root"]
    O --> L1["OrderLine SKU-A"]
    O --> L2["OrderLine SKU-B"]
    O -. "customerId tham chiếu" .-> C["Customer — aggregate độc lập"]
    O -. "shipmentId tham chiếu" .-> H["Shipment — aggregate độc lập"]
~~~

- `PurchaseOrder` là root được repository lưu.
- `OrderLine` là child nằm trong vòng đời Order.
- `Customer` và `Shipment` có vòng đời riêng; Order chỉ giữ ID hoặc reference.
- Các invariants như số lượng dương, không trùng SKU, tổng số dòng tối đa được kiểm tra trong domain/application service.
- Database constraints là lớp bảo vệ cuối trước races hoặc ứng dụng khác ghi trực tiếp.

Spring Data JDBC cố ý đặt trọng tâm vào aggregate boundary. Nếu một object chỉ là reference đến aggregate khác, không nên map nó như một object graph để tự cascade insert/update toàn bộ.

### 2.1. JPA nghĩ theo entity graph

Trong JPA/Hibernate, `OrderEntity` có thể sở hữu `@OneToMany` lines và `@ManyToOne` customer, mỗi association có fetch/cascade rules. Persistence context quản lý những entities đã load, và Hibernate có thể dirty-check fields.

Spring Data JDBC **không** quản lý mọi object trong persistence context và **không tự lazy load** khi gọi getter. Nó load/persist quan hệ thuộc aggregate theo mapping rõ, không có object graph ORM vô hạn.

### 2.2. Khi nào một child nên trở thành aggregate khác?

Cân nhắc tách nếu child có identity riêng, được các hệ thống khác tham chiếu trực tiếp, có lifecycle độc lập, update concurrency rất cao hoặc khiến mỗi lần load/save root quá lớn. Ví dụ shipment/payment thường không nên tự động cascade từ order nếu có state machine và transactions riêng.

## 3. Dependencies Spring Boot

Ví dụ Gradle Groovy DSL với Spring Boot 3.x, Java 17+ và PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    // Với các Flyway releases cần driver/dialect module:
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    // Khi serialize JSON event outbox bằng Jackson:
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Sử dụng Spring Boot BOM để quản lý versions. Với Boot 4/Spring Data/JDBC hoặc Flyway thế hệ mới, tên starter/module/import có thể khác; đối chiếu chính xác với version của project. Không thêm `spring-boot-starter-data-jpa` chỉ để có Spring Data repositories.

### 3.1. Datasource và pool

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/integration_db}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-jdbc
      maximum-pool-size: 12
      connection-timeout: 3000
      max-lifetime: 1800000

  flyway:
    enabled: true
~~~

Giá trị timeouts Hikari dạng số như trên thường dùng **mili giây**; xác minh binder/driver version. `maximum-pool-size` tính **per instance/pod**: 8 replicas × 12 ≈ 96 connections, chưa tính các ứng dụng khác. Không hardcode password production. PostgreSQL TLS và server hostname verification phải được cấu hình riêng theo JDBC driver/policy.

### 3.2. Auto-configuration không phải tự động tạo toàn bộ schema

Với dependency phù hợp, Boot có thể cung cấp DataSource, JDBC mapping/repositories, transaction manager và Flyway. Schema production nên được quản lý bằng migrations. Đừng nghĩ Spring Data JDBC sẽ tự tạo hoặc đồng bộ các tables như một tiện ích ORM schema generator.

## 4. Schema SQL cho PurchaseOrder aggregate

Ví dụ migration PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    external_id VARCHAR(120) NOT NULL UNIQUE,
    customer_id VARCHAR(120) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_order_lines (
    order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id) ON DELETE CASCADE,
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_position)
);

CREATE INDEX idx_purchase_orders_customer
    ON purchase_orders(customer_id);
~~~

Giả sử migration được lưu trong `db/migration/V1__create_orders.sql`. Theo phạm vi STEP 4, bài chỉ cung cấp đoạn SQL, **không tạo thêm file migration**.

**Ranh giới trách nhiệm:**

- `purchase_orders.id` là technical primary key.
- `external_id` là business identity, unique để hỗ trợ idempotency.
- `version` phục vụ optimistic locking.
- `purchase_order_lines.order_id` là foreign key về root.
- `line_position` lưu thứ tự collection; **không phải stable business lineId**.
- `CHECK(quantity > 0)` bảo vệ invariant khi có SQL writer khác.

Nếu mỗi order line cần stable identity qua reorder, thêm business line ID/unique constraint hoặc thiết kế aggregate khác, không dựa mãi vào list index.

## 5. Mapping root và child bằng Spring Data JDBC

### 5.1. PurchaseOrder aggregate root

~~~java
// PurchaseOrder.java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        @Column("external_id") String externalId,
        @Column("customer_id") String customerId,
        String status,
        @MappedCollection(
                idColumn = "order_id",
                keyColumn = "line_position")
        List<PurchaseOrderLine> lines) {

    public PurchaseOrder {
        lines = List.copyOf(lines);
    }

    public PurchaseOrder withStatus(String status) {
        return new PurchaseOrder(
                id, version, externalId, customerId,
                status, lines);
    }
}
~~~

Lớp `@Id`/`@Version` thuộc `org.springframework.data.annotation`, không dùng `jakarta.persistence.Id`/`jakarta.persistence.Version`. `@Table` và `@MappedCollection` thuộc Spring Data Relational.

Java record hỗ trợ immutable state; constructor compact tạo defensive copy nhưng yêu cầu `lines` khác null và không có null elements. Validate input trước khi tạo aggregate.

### 5.2. Child entity

~~~java
// PurchaseOrderLine.java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order_lines")
public record PurchaseOrderLine(
        String sku,
        int quantity) {

    public PurchaseOrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity phải > 0");
        }
    }
}
~~~

`@MappedCollection(idColumn="order_id", keyColumn="line_position")` xác định foreign key và list/map key column. Với root record/child record, Spring Data JDBC cần constructor/value mapping phù hợp version. Vì vậy phải có integration test save/load/update, đặc biệt khi dùng immutable aggregates và generated IDs.

### 5.3. Mapping annotations khác JPA

| Spring Data JDBC | JPA |
| --- | --- |
| `org.springframework.data.relational.core.mapping.Table` | `jakarta.persistence.Table` |
| `org.springframework.data.annotation.Id` | `jakarta.persistence.Id` |
| `org.springframework.data.annotation.Version` | `jakarta.persistence.Version` |
| `@MappedCollection` | `@OneToMany`, `@ElementCollection` |
| Lưu aggregate tường minh | EntityManager/persistence context |
| Không JPA lazy loading | Có thể LAZY theo provider/mapping |

Không dùng một entity Java vừa là JPA entity vừa là Spring Data JDBC aggregate nếu chưa có lý do và kiểm thử rất rõ; hai mô hình annotation/lifecycle khác nhau.

## 6. CrudRepository: lưu và truy vấn root

~~~java
// PurchaseOrderRepository.java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByExternalId(String externalId);

    boolean existsByExternalId(String externalId);
}
~~~

Repository là Spring-managed proxy; nó **không phải một JDBC Connection**. DataSource/HikariCP cấp JDBC connections cho operations khi cần. Domain service thường inject repository singleton.

### 6.1. Insert aggregate

~~~java
import java.util.List;

PurchaseOrder draft = new PurchaseOrder(
        null,
        null,
        "EXT-2026-001",
        "CUST-10",
        "DRAFT",
        List.of(
                new PurchaseOrderLine("SKU-A", 2),
                new PurchaseOrderLine("SKU-B", 3)));

PurchaseOrder saved = repository.save(draft);

// Dùng saved.id(), saved.version().
// Không giả định draft immutable bị mutate tại chỗ.
~~~

Với generated ID, `save` có thể trả **một instance mới** chứa id/version thay vì thay đổi input object. Luôn dùng giá trị trả về khi tiếp tục xử lý một immutable aggregate.

### 6.2. Đọc aggregate

~~~java
PurchaseOrder loaded =
        repository.findByExternalId("EXT-2026-001")
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không tìm thấy order"));
~~~

Spring Data JDBC load root cùng các children được map theo aggregate. Nó không có JPA persistence context/lazy loading như Hibernate; các collections liên quan có thể làm tăng SQL queries. Với endpoint chỉ cần summary, không load toàn aggregate hàng nghìn dòng khi SQL projection là đủ.

### 6.3. Cập nhật tường minh

~~~java
PurchaseOrder existing =
        repository.findByExternalId("EXT-2026-001")
                .orElseThrow();

PurchaseOrder confirmed =
        repository.save(existing.withStatus("CONFIRMED"));
~~~

**Không có dirty checking**: nếu chỉ gọi `existing.withStatus("CONFIRMED")` rồi kết thúc `@Transactional` mà **không save**, Spring Data JDBC không tự phát lệnh UPDATE.

### 6.4. Save new/existing

Spring Data JDBC quyết định entity mới hay đã tồn tại dựa trên ID, `@Version` và các cơ chế như `Persistable`. Với generated ID/version null thường nhận diện entity mới. Nếu application **tự cấp ID**, cần kiểm tra new-state detection; một object có ID không nhất thiết được repository tự insert như bạn mong muốn.

## 7. Save semantics và chi phí cập nhật children

Spring Data JDBC lưu **trạng thái aggregate** được cung cấp. Trong nhiều cấu hình/phiên bản, khi lưu aggregate root đã tồn tại, Spring Data JDBC có thể **xóa và tạo lại các dependent child rows**, dù chỉ một field của root thay đổi. SQL cụ thể tùy version/mapping/optimizations.

Hệ quả:

- Order 2–20 lines thường dễ quản lý.
- Aggregate 50.000 lines có thể gây nhiều INSERT/DELETE, locks và transaction latency.
- Trigger/audit và các foreign keys tham chiếu child rows có thể chịu tác động.
- Không assume save chỉ UPDATE columns changed như JPA dirty checking.
- Thử nghiệm SQL thực trước khi thiết kế aggregate rất lớn.

### 7.1. Điều chỉnh aggregate boundary thay vì tăng connection pool

Nếu child được update độc lập, có identity riêng hoặc tần suất cao, tách thành aggregate khác và dùng reference. Tăng Hikari pool không giải quyết một aggregate update gây hàng nghìn SQL writes.

### 7.2. Root references không tự cascade

Tham chiếu Customer/Shipment aggregate khác nên là ID. Spring Data JDBC có `AggregateReference<T, ID>`:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

// Customer là type minh họa ở bounded context khác.
AggregateReference<Customer, Long> customer =
        AggregateReference.to(123L);
~~~

Reference này biểu diễn identity, **không tự truy vấn/lazy-load Customer** và không tạo cascade. Nếu đối tác nằm ở microservice khác, giữ `customerId` dạng string có thể đơn giản hơn.

## 8. So sánh Spring Data JDBC và JPA

| Chủ đề | Spring Data JDBC | Spring Data JPA |
| --- | --- | --- |
| Model | Aggregate root và owned children | JPA entities/object graph |
| Persistence context | Không có kiểu JPA | EntityManager quản lý managed entities |
| Dirty checking | Không; cần save rõ | Có trên managed entities |
| Lazy loading | Không theo kiểu JPA | Có thể LAZY tùy association/provider |
| Relationships | `@MappedCollection`, IDs/references | `@OneToMany`, `@ManyToOne`, cascades |
| Repository | Spring Data `CrudRepository` | `JpaRepository` |
| Entity annotations | Spring Data Relational | Jakarta Persistence |
| ORM state management | Không JPA flush/first-level cache | Có flush, identity map, snapshots |
| Query | Derived queries, SQL `@Query`, projections | JPQL/Criteria/native SQL/projections |
| Child persistence | Theo aggregate boundary | Theo persistence context/cascade |
| Optimistic locking | Spring `@Version` | JPA `@Version` |
| Batch/complex SQL | Phối hợp JdbcTemplate/jOOQ | Có thể dùng native SQL/jOOQ bổ sung |
| Complexity | Dễ suy luận khi aggregate vừa phải | Mạnh hơn nhưng cần hiểu fetch/flush/N+1 |

### 8.1. JPA dirty checking ví dụ

~~~java
// JPA-only code, không phải Spring Data JDBC.
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class JpaOrderEntity {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    protected JpaOrderEntity() {
    }

    public void confirm() {
        this.status = "CONFIRMED";
    }
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void confirmJpa(Long id) {
    JpaOrderEntity entity =
            entityManager.find(JpaOrderEntity.class, id);

    entity.confirm();

    // Hibernate/JPA có thể flush khi thích hợp;
    // managed entity được theo dõi trong persistence context.
}
~~~

Snippet giả định `entityManager` được inject đúng. Flush có thể xảy ra trước query hoặc lúc commit tùy flush mode, không chỉ khi method return.

### 8.2. Spring Data JDBC tương đương

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void confirmJdbc(Long id) {
    PurchaseOrder order =
            repository.findById(id).orElseThrow();

    repository.save(order.withStatus("CONFIRMED"));
}
~~~

Với JDBC, annotation `@Transactional` làm các SQL operations trong cùng local transaction, **không thêm cơ chế theo dõi Java object**.

### 8.3. Chọn theo đúng use case

Nên cân nhắc Spring Data JDBC khi:

- Write model rõ aggregate boundaries.
- Muốn domain model gọn, dễ đọc SQL/lifecycle.
- Không cần lazy JPA entity graph.
- Dữ liệu aggregate vừa phải.
- Thường kết hợp read models/reporting bằng SQL tùy chỉnh.
- Dùng transaction cục bộ/outbox để tích hợp bên ngoài.

Nên cân nhắc JPA khi:

- Entity graph/associations phức tạp là phần cốt lõi.
- Persistence context, cascading, dirty checking giúp giảm code đáng kể.
- Cần các JPA capabilities như JPQL/Criteria/entity graphs.
- Đội ngũ hiểu và vận hành được fetch plans, flush modes, N+1 và caching.

**Không chọn JPA chỉ vì schema nhiều bảng**; SQL JOIN phức tạp cho báo cáo đôi khi hợp jOOQ hơn một graph ORM.

## 9. Repository hay JdbcTemplate/JdbcClient/jOOQ?

Một ứng dụng có thể dùng:

- **Spring Data JDBC** để write root aggregates.
- **JdbcClient** hoặc **JdbcTemplate** để đọc projection gọn, batch updates và SQL trực tiếp.
- **jOOQ** để sinh SQL có kiểu, xử lý CTE, window functions, vendor-specific features.
- **JPA** trong bounded context khác thực sự cần ORM.

### 9.1. Read projection bằng JdbcClient

Spring Framework 6.1+ hỗ trợ `JdbcClient`:

~~~java
// OrderReadRepository.java
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {

    private final JdbcClient jdbcClient;

    public OrderReadRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public List<OrderListItem> findRecent(int limit) {
        if (limit <= 0 || limit > 200) {
            throw new IllegalArgumentException(
                    "limit phải trong 1..200");
        }

        return jdbcClient.sql(
                """
                SELECT id, external_id, status
                FROM purchase_orders
                ORDER BY id DESC
                LIMIT :limit
                """)
                .param("limit", limit)
                .query((rs, rowNum) ->
                        new OrderListItem(
                                rs.getLong("id"),
                                rs.getString("external_id"),
                                rs.getString("status")))
                .list();
    }

    public record OrderListItem(
            long id, String externalId, String status) {
    }
}
~~~

Chỉ lấy 3 columns, **không materialize toàn bộ lines**. Với Spring Framework cũ hơn 6.1, dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`.

**SQL injection:** dùng parameter binding cho values; không nối input vào SQL. Tên columns, ORDER BY fields hoặc table name nếu dynamic phải đến từ allowlist.

### 9.2. jOOQ với generated SQL types

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
}
~~~

Một snippet giả định project đã chạy **jOOQ code generation** từ schema:

~~~java
import java.util.List;
import org.jooq.DSLContext;

import static com.example.jooq.tables.PurchaseOrders.PURCHASE_ORDERS;

public List<String> findExternalIds(
        DSLContext dsl, String status, int limit) {

    return dsl.select(PURCHASE_ORDERS.EXTERNAL_ID)
            .from(PURCHASE_ORDERS)
            .where(PURCHASE_ORDERS.STATUS.eq(status))
            .orderBy(PURCHASE_ORDERS.ID.desc())
            .limit(limit)
            .fetch(PURCHASE_ORDERS.EXTERNAL_ID);
}
~~~

`com.example.jooq.tables.PurchaseOrders` **không được tạo bởi starter tự động**; phải có jOOQ codegen task và schema thực. jOOQ phù hợp với SQL phức tạp nhưng không tự thay thế aggregate persistence của Spring Data JDBC.

### 9.3. Shared transaction khi kết hợp

Nếu Spring Data JDBC repository, JdbcTemplate và `DSLContext` của jOOQ sử dụng **cùng DataSource và Spring transaction integration phù hợp**, có thể tham gia cùng một local JDBC transaction. Với jOOQ, Boot starter có cơ chế tích hợp transaction/connection provider theo điều kiện; nếu tự tạo một `DSLContext` với connection khác, **không được giả định rollback chung**.

Kiểm thử bằng cách cố tình ném exception sau cả repository save và jOOQ update, rồi xác nhận **cả hai rollback**.

## 10. @Query và @Modifying

Spring Data JDBC repositories có thể khai báo SQL trực tiếp cho query không thuận tiện với derived queries:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface OrderStatisticsRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("SELECT COUNT(*) FROM purchase_orders WHERE status = :status")
    long countByStatus(String status);
}
~~~

Khi custom query trả aggregate có collections, cần kiểm tra cách materialization hoạt động; không coi một JOIN tùy ý là đủ cho Spring Data JDBC tự reconstruct đúng mọi associations.

### 10.1. SQL update có optimistic condition

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface OrderMaintenanceRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
            UPDATE purchase_orders
               SET status = 'ARCHIVED',
                   version = version + 1
             WHERE id = :id
               AND version = :version
            """)
    int archiveIfVersionMatches(
            @Param("id") Long id,
            @Param("version") Long version);
}
~~~

Kiểm tra rows affected: `1` nghĩa update thành công; `0` có thể là not found/version conflict. SQL trực tiếp có thể **bypass aggregate callbacks, repository version mechanics và business invariants**; không dùng tùy tiện cho commands phức tạp.

### 10.2. Khi dùng trực tiếp SQL

Nên dùng cho read models, bulk updates, upserts và operations mà bạn cố ý kiểm soát SQL. Nhưng phải:

- Kiểm tra transaction boundary.
- Bảo vệ optimistic locking/unique keys nếu cần.
- Không phá các aggregate invariants.
- Ghi audit/outbox cho side effects có liên quan.
- Validate SQL parameters/permissions.

## 11. @Version và optimistic locking

Hai worker cùng đọc order version=3:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as PostgreSQL
    A->>D: SELECT order version=3
    B->>D: SELECT order version=3
    A->>D: UPDATE id=? AND version=3
    D-->>A: Version updated to 4
    B->>D: UPDATE id=? AND version=3
    D-->>B: Conflict, zero matching rows
~~~

Spring Data JDBC `@Version` giúp phát hiện lost update bằng optimistic locking khi lưu existing aggregate. Tùy version, lỗi có thể là `OptimisticLockingFailureException` hoặc subtype của Spring data-access exceptions.

### 11.1. Optimistic locking không thay unique business key

Hai requests có thể cùng thấy `existsByExternalId("EXT-10") = false`, rồi cùng insert. Chỉ **UNIQUE(external_id)** ở database giải quyết race chắc chắn. Có thể map duplicate-key thành idempotent result hoặc HTTP 409 theo contract.

### 11.2. Xử lý version conflict

1. Reload aggregate mới nhất.
2. Kiểm tra business command còn hợp lệ không.
3. Nếu operation đã được áp dụng, trả kết quả idempotent.
4. Nếu cần cập nhật lại, tính trạng thái mới dựa trên version mới.
5. Retry số lần hữu hạn khi an toàn.
6. Không phát HTTP/broker side effects **trong mỗi retry attempt**.

Nếu giữ external side effect trong transaction, một optimistic conflict sau network call không thể tự rollback phía remote.

## 12. Transaction của database khác giao dịch HTTP/broker

~~~mermaid
flowchart LR
    C["Confirm command"] --> T["Spring @Transactional"]
    T --> R["Spring Data JDBC repository"]
    T --> O["Outbox SQL insert"]
    R --> D["PostgreSQL"]
    O --> D
    D --> W["Outbox relay sau COMMIT"]
    W --> K["Kafka / RabbitMQ"]
    W --> H["HTTP partner"]
~~~

Một `@Transactional` với JDBC transaction manager chỉ atomic trên tài nguyên database được quản lý. Redis cache, HTTP request, Kafka producer send hay RabbitMQ publish không tự nằm trong cùng transaction.

### 12.1. Anti-pattern: HTTP trong SQL transaction

~~~java
@Transactional
public void confirmAndNotify(String externalId) {
    PurchaseOrder current = repository
            .findByExternalId(externalId)
            .orElseThrow();

    repository.save(current.withStatus("CONFIRMED"));

    erpRestClient.post()
            .uri("/v1/orders")
            .body(current)
            .retrieve()
            .toBodilessEntity();

    kafkaTemplate.send("orders.events", externalId, "CONFIRMED");
}
~~~

Snippet này chỉ minh họa bẫy thiết kế, giả định dependencies được inject. ERP có thể commit rồi SQL rollback; Kafka send async có thể hoàn tất sau SQL commit hoặc thành công trước khi SQL rollback; JDBC connection có thể bị giữ trong lúc HTTP timeout.

**Pool size không giải quyết distributed consistency.** Dùng transactional outbox, saga/reconciliation hoặc distributed transaction có chủ đích khi được hỗ trợ.

### 12.2. Transactional outbox schema

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_outbox_due
ON integration_outbox(status, next_attempt_at, created_at);
~~~

Lưu event intent cùng transaction với aggregate update; worker sau commit mới publish. `eventId` phải giữ ổn định khi retry. Consumer cần inbox/unique constraint để không áp business effect nhiều lần.

## 13. Application service lưu aggregate và outbox

Dùng `NamedParameterJdbcTemplate` vì câu SQL outbox không phải root aggregate mapping:

~~~java
// OrderConfirmationService.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {

    private final PurchaseOrderRepository orders;
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public OrderConfirmationService(
            PurchaseOrderRepository orders,
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public PurchaseOrder confirm(String externalId) {
        PurchaseOrder current = orders
                .findByExternalId(externalId)
                .orElseThrow();

        if ("CONFIRMED".equals(current.status())) {
            return current; // Idempotent command.
        }

        if (!"DRAFT".equals(current.status())) {
            throw new IllegalStateException(
                    "Trạng thái không cho phép xác nhận");
        }

        PurchaseOrder saved =
                orders.save(current.withStatus("CONFIRMED"));

        UUID eventId = UUID.randomUUID();
        String payload = toJson(new OrderConfirmedEvent(
                eventId.toString(),
                saved.externalId(),
                saved.version()));

        var params = new MapSqlParameterSource()
                .addValue("eventId", eventId)
                .addValue("aggregateId", saved.id())
                .addValue("payload", payload);

        jdbc.update(
                """
                INSERT INTO integration_outbox(
                    event_id, aggregate_type, aggregate_id,
                    event_type, payload, status)
                VALUES (:eventId, 'PurchaseOrder', :aggregateId,
                        'OrderConfirmed', CAST(:payload AS jsonb), 'PENDING')
                """,
                params);

        return saved;
    }

    private String toJson(OrderConfirmedEvent event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "Không serialize được outbox event", e);
        }
    }

    public record OrderConfirmedEvent(
            String eventId, String externalId, Long version) {
    }
}
~~~

Nếu outbox INSERT fail, Spring transaction rollback cả aggregate change (vì exception runtime). `@Transactional` cần được gọi qua Spring proxy, không self-invoke rồi nghĩ đã có transaction.

**Business idempotency:** Nếu order đã CONFIRMED thì không phát event mới. Với concurrent requests, `@Version` và database constraints cần kiểm thử để ngăn duplicate commits. Nếu command có ID riêng, có thể thêm bảng `processed_commands` với UNIQUE(commandId).

**Outbox là at-least-once:** Broker có thể nhận event, nhưng relay crash trước khi ghi `BROKER_CONFIRMED`; sau restart relay phát lại. Consumer/partner phải có idempotency hoặc reconciliation.

### 13.1. Không giữ SQL transaction trong lúc gọi network

Nếu HTTP timeout mất 15 giây trong một SQL transaction, JDBC connection và locks có thể bị giữ 15 giây. Khi nhiều workers chạy đồng thời, pool exhausted. Phát event intent từ local transaction rồi gọi network **sau commit** với retry budget riêng.

### 13.2. Handoff sang consumer

Nếu broker consumer lưu aggregate, chỉ ACK/commit offset sau khi business transaction hoặc durable handoff hoàn tất theo contract. Nếu DB commit rồi ACK thất bại, message sẽ redeliver; dùng inbox hoặc unique event ID để tránh xử lý trùng.

## 14. JdbcAggregateTemplate và thao tác explicit

Ngoài `CrudRepository`, Spring Data JDBC có `JdbcAggregateTemplate` khi muốn thao tác aggregate bằng API chương trình hóa:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate aggregates;

    public PurchaseOrderWriter(JdbcAggregateTemplate aggregates) {
        this.aggregates = aggregates;
    }

    public PurchaseOrder insertNew(PurchaseOrder order) {
        return aggregates.insert(order);
    }
}
~~~

`insert` làm rõ ý định insert. Sử dụng đúng repository/template API theo version và test với generated IDs. `JdbcAggregateTemplate` vẫn là persistence abstraction cho aggregates, **không phải JPA EntityManager**.

### 14.1. Khi nào dùng bulk SQL?

Một batch 100.000 inventory updates thường không cần materialize 100.000 aggregate roots nếu chỉ cập nhật counters có điều kiện. `JdbcTemplate.batchUpdate` hoặc jOOQ bulk/upsert có thể hiệu quả hơn, nhưng phải tự bảo đảm:

- Unique constraints/idempotency.
- Business version check.
- Transaction chunking và bounded memory.
- Audit/outbox khi cần.
- Không bỏ qua aggregate invariant một cách nguy hiểm.

## 15. Read model, pagination và streaming

Một API list đơn hàng thường chỉ cần id, externalId, status. Dùng projection qua SQL/jOOQ thay vì load mọi `PurchaseOrderLine`.

### 15.1. Keyset pagination

~~~sql
SELECT id, external_id, status
FROM purchase_orders
WHERE id > ?
ORDER BY id
LIMIT ?;
~~~

Keyset pagination phù hợp polling/reconciliation trên tập lớn nếu cursor ổn định. Offset pagination có thể lặp/bỏ rows khi dữ liệu thay đổi nhanh. Dùng batch size hữu hạn và checkpoint để xử lý hàng triệu records.

### 15.2. JDBC stream giữ connection

Một ResultSet/cursor thường gắn với JDBC connection/transaction. Nếu trả stream ra ngoài method rồi chuyển sang async executor sau khi transaction đóng, cursor có thể không dùng được. Materialize chunks nhỏ hoặc giữ cursor lifecycle đúng, không giữ pool connection quá lâu.

### 15.3. Truy vấn tổng hợp dùng SQL thay vì entity graph

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM purchase_orders
WHERE status = 'CONFIRMED'
GROUP BY customer_id
ORDER BY order_count DESC;
~~~

Đây là loại query hợp JdbcClient/jOOQ. Không load toàn bộ aggregates rồi `stream().collect(groupingBy(...))` chỉ để đếm trong Java.

## 16. Xử lý lỗi JDBC và concurrency

| Tình huống | Exception/group thường gặp | Cách ứng xử |
| --- | --- | --- |
| Duplicate business key | `DuplicateKeyException` | Conflict/idempotent response |
| Version mismatch | `OptimisticLockingFailureException` | Reload/reconcile/bounded retry |
| FK/CHECK/NOT NULL violation | `DataIntegrityViolationException` | Sửa input/logic/schema |
| SQL syntax/migration sai | `BadSqlGrammarException` | Sửa code/schema, không retry |
| Connection unavailable | `CannotGetJdbcConnectionException` | Kiểm tra DB/pool/network |
| Deadlock/serialization | `TransientDataAccessException` subtype | Retry transaction có giới hạn |
| Query timeout | Driver/Spring data-access exception | Phân biệt query, network và outcome |

Tên exception cụ thể phụ thuộc driver, SQL state, Spring version và exception translation. Không viết một catch-all `DataAccessException` rồi retry vô hạn.

### 16.1. Ba cơ chế bảo vệ khác nhau

- `@Version`: lost update trên **existing root**.
- `UNIQUE(external_id)`: duplicate identity khi **concurrent inserts**.
- `@Transactional`: atomicity của các operations **trên cùng local DB transaction**.

Chúng bổ sung nhau. Version không thay unique key, transaction không thay domain validation và không tự rollback một HTTP call.

### 16.2. Retry chỉ khi an toàn

Với optimistic conflict, reload state mới rồi đánh giá lại command. Không retry nguyên service method nếu method vừa gọi remote API có side effect. Với lỗi COMMIT outcome unknown, dùng business key/idempotency và status lookup để xác định kết quả.

## 17. Kiểm thử với PostgreSQL Testcontainers

Unit test domain không chứng minh schema mapping, generated IDs, children, version SQL hoặc transaction rollback. Nên test với PostgreSQL thực qua Testcontainers.

### 17.1. Test dependencies

~~~groovy
dependencies {
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với Boot 4, test starter/packages có thể được tổ chức lại; điều chỉnh theo version dự án. `@ServiceConnection` được hỗ trợ ở những dòng Boot hiện đại có Boot Testcontainers support.

### 17.2. @DataJdbcTest cho repository

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void saveAndReloadLines() {
        PurchaseOrder draft = new PurchaseOrder(
                null, null, "TEST-ORDER-001", "CUST-1",
                "DRAFT",
                List.of(
                        new PurchaseOrderLine("SKU-A", 2),
                        new PurchaseOrderLine("SKU-B", 3)));

        PurchaseOrder saved = repository.save(draft);

        assertNotNull(saved.id());

        PurchaseOrder loaded =
                repository.findById(saved.id())
                        .orElseThrow();

        assertEquals("TEST-ORDER-001", loaded.externalId());
        assertEquals(2, loaded.lines().size());
    }
}
~~~

Test yêu cầu migrations được thực thi trong test context, đúng Spring Boot/Testcontainers version. H2 không chứng minh PostgreSQL JSONB, `ON CONFLICT`, locks, transaction isolation hay identity semantics.

### 17.3. Các bài test bắt buộc

| Test | Điều cần assert |
| --- | --- |
| New aggregate insert | ID/version, root + children được lưu |
| Reload aggregate | Đúng fields, list order, child count |
| Save updated root | Status mới và children không mất |
| Invalid quantity | Domain validation/DB CHECK reject |
| Duplicate externalId | UNIQUE constraint chặn race |
| Two concurrent versions | Stale save bị optimistic locking từ chối |
| Outbox insert fails | Root update rollback cùng transaction |
| jOOQ+repository transaction | Hai SQL operations cùng rollback |
| Outbox relay crash after broker ACK | Replay dùng eventId cũ, không mất intent |
| Kafka/Rabbit consumer replay | Inbox/dedupe bảo vệ side effects |
| Connection pool saturation | Timeout và bounded concurrency rõ |
| Migration compatibility | Schema thực tương thích mapping |

### 17.4. Test transaction rollback

~~~text
Given PurchaseOrder DRAFT trong PostgreSQL
When OrderConfirmationService.confirm()
And outbox INSERT bị lỗi
Then transaction rollback
And Order status vẫn DRAFT
And không có outbox row được commit
~~~

Test trên một DB thật, không chỉ mock repository. Nếu repository dùng DataSource A và outbox dùng DataSource B, test này có thể phơi bày partial commits và buộc kiến trúc sửa transaction wiring.

### 17.5. Test optimistic locking đúng cách

Hai transactions/instances cùng đọc version 3; transaction A save thành công; transaction B thử save object với version 3 và phải bị từ chối. Đừng chỉ dùng một object mutable chia sẻ trong test rồi kết luận đã thử concurrency.

## 18. Quan sát và vận hành SQL trong luồng tích hợp

| Metric/trace | Tầng | Ý nghĩa |
| --- | --- | --- |
| `hikaricp.connections.active` | Pool | Connections đang được dùng |
| `hikaricp.connections.idle` | Pool | Connections đang rảnh |
| `hikaricp.connections.pending` | Pool | Threads chờ connection |
| `hikaricp.connections.timeout` | Pool | Acquire timeout count |
| SQL query/update duration | Database | Query/lock/binding cost |
| Transaction duration/rollback | Spring/DB | Giao dịch kéo dài/thất bại |
| Duplicate/version conflicts | Application | Concurrent requests/replay |
| Outbox oldest pending age | Integration | Ý định gửi chưa hoàn thành |
| Broker producer confirmed | Messaging | Broker accepted, không phải consumer processed |
| Consumer inbox duplicates | Consumer | Event replay được xử lý an toàn |
| End-to-end business lag | Application | Từ command tới downstream applied |

Tên metrics SQL/transaction chính xác phụ thuộc instrumentation/driver/Boot version. Actuator có thể cung cấp Hikari metrics khi được cấu hình phù hợp, nhưng không assume SQL timer tự tồn tại trong mọi project.

### 18.1. Ví dụ dấu hiệu pool starvation

~~~text
HTTP request A
  -> @Transactional BEGIN
  -> JDBC SELECT + UPDATE
  -> chờ ERP HTTP 15 giây
  -> COMMIT + return JDBC Connection

Requests B..N
  -> chờ Hikari pool
  -> connectionTimeout
~~~

Giải pháp chính là **rút ngắn transaction** và tách remote call bằng outbox/saga. Tăng `maximum-pool-size` không giúp khi nhiều long-running transactions và DB đã quá tải.

### 18.2. Secrets/PII và metric cardinality

Không log đầy đủ query bind values chứa customer PII, DB password, access token hoặc raw event payload. Tags nên có số giá trị hữu hạn như `component=jdbc`, `operation=confirmOrder`, `outcome=optimistic_conflict`; không thêm eventId/orderId/customerId thành metric labels.

### 18.3. Health không phải business completion

DataSource health UP chỉ cho biết DB có thể kết nối tại thời điểm kiểm tra. Nó không chứng minh outbox relay đang phát sự kiện, consumer không có backlog, hoặc ERP đã xử lý. Theo dõi transaction/pool metrics **và** business lag/retry/DLQ riêng.

## 19. Những anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách đúng hơn |
| --- | --- | --- |
| Coi Spring Data JDBC là JPA đổi package | Sai mapping/lifecycle | Thiết kế aggregate-oriented |
| Sửa immutable object nhưng không save | Không có dirty checking | `repository.save(updated)` |
| Dùng JPA `@OneToMany` cho JDBC child | Sai annotation | `@MappedCollection` |
| Một aggregate chứa toàn bộ customer/order/payment graph | SQL nhiều, sai consistency boundary | Tách aggregate references |
| Dùng line index làm stable line ID | Reorder gây mất identity | Business lineId khi cần |
| Load mọi lines để trả trang summary | Tốn SQL/memory | JdbcClient/jOOQ projection |
| Custom SQL update quên version/outbox | Lost update/missing events | Conditional update + event contract |
| `existsByExternalId` rồi insert không có UNIQUE | Race condition | Database unique constraint |
| Gọi HTTP/Kafka trong SQL transaction | Không thể rollback remote side effect | Outbox/reconciliation |
| Dùng jOOQ khác DataSource nhưng nghĩ cùng transaction | Partial commits | Spring transaction integration |
| Retry mọi DataAccessException | Loop với lỗi permanent | Phân loại và giới hạn retry |
| Tăng pool để sửa truy vấn/locks chậm | Tăng contention | Index/SQL/transaction tuning |
| Dùng H2 test cho PostgreSQL JSONB/locks | SQL semantics khác | PostgreSQL Testcontainers |
| Coi broker ACK là consumer processed | Sai messaging semantics | Business completion metrics |

## 20. Checklist production

- [ ] Đã chọn Spring Data JDBC vì aggregate-oriented write model phù hợp.
- [ ] Phân biệt JdbcTemplate/JdbcClient, Data JDBC, JPA và jOOQ.
- [ ] Aggregate root/children có boundaries và invariants rõ.
- [ ] External aggregate references ở dạng ID/AggregateReference.
- [ ] Mapping `@Table`, `@Id`, `@Version`, `@MappedCollection` đúng Spring Data JDBC.
- [ ] Migration tạo tables, FK, CHECK và UNIQUE business IDs.
- [ ] Immutable entity dùng giá trị trả về của `save` để lấy ID/version mới.
- [ ] Test insert/load/update/delete root và child collection.
- [ ] Đã đo chi phí resave aggregate, không tạo aggregate quá lớn.
- [ ] `@Version`, unique constraints và application idempotency bảo vệ concurrency.
- [ ] Direct SQL/jOOQ không bỏ quên audit, optimistic version hay invariants.
- [ ] Query danh sách/reporting dùng projection/pagination.
- [ ] Spring Data JDBC/jOOQ/JdbcClient cùng transaction khi cần atomicity.
- [ ] SQL transactions ngắn; HTTP/broker side effects qua outbox khi cần.
- [ ] Outbox có eventId ổn định, inbox/consumer chống replay.
- [ ] Retry theo loại lỗi, không retry non-transient SQL/authorization vô hạn.
- [ ] PostgreSQL Testcontainers test mapping, migrations, locks và rollback.
- [ ] Có metrics pool active/idle/pending, SQL latency, conflicts và business lag.
- [ ] Không ghi raw SQL parameters nhạy cảm, tokens hoặc PII vào logs/metrics.
- [ ] Tuân theo DB TLS, credentials, least privilege và connection budget.

**Ghi nhớ:** Spring Data JDBC sử dụng Spring Data repositories để lưu **relational aggregates**, nhưng không có persistence context, lazy loading và dirty checking như JPA. `save()` là hành động tường minh; một aggregate quá lớn có thể làm nhiều SQL khi cập nhật children. Spring Data JDBC có thể kết hợp `JdbcClient` hoặc jOOQ để tận dụng SQL mạnh mẽ mà không biến write model thành ORM graph. Trong Spring Boot Integration, tính đúng đắn đến từ **aggregate boundaries, database constraints, local transaction, outbox/inbox, kiểm thử và observability**, không chỉ từ việc chọn thư viện truy cập SQL.

## Tài liệu tham khảo

- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): aggregate model, repositories và mapping.
- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): immutable entities và constructors.
- [Spring Data JDBC — Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): save/new state và aggregate persistence.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): @Table, @Id, @MappedCollection, references.
- [Spring Data JDBC — Transactions](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction behavior.
- [Spring Data JPA — Reference](https://docs.spring.io/spring-data/jpa/reference/): JPA repositories, ORM lifecycle.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate, JdbcClient.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): PlatformTransactionManager.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, pooling, JDBC, jOOQ và JPA.
- [jOOQ — Manual](https://www.jooq.org/doc/latest/manual/): SQL DSL, code generation, transactions.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned schema migrations.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): integration tests against PostgreSQL.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): atomic business data + outbox.
