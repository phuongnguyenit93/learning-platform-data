# Quản lý cấu hình persistence unit giữa các môi trường

Một ứng dụng Java sử dụng **Jakarta Persistence (JPA)** có thể dùng cùng một tập entity cho các môi trường **local development, integration test, staging và production**, nhưng không nên dùng nguyên một cấu hình kết nối, giao dịch, sinh schema, logging và cache cho tất cả môi trường. Nếu quản lý kém, ứng dụng có thể vô tình kết nối production từ máy developer, để Hibernate tự sửa schema đang có dữ liệu, chạy test trên H2 rồi tưởng đã kiểm thử PostgreSQL, hoặc ghi mật khẩu và bind parameters nhạy cảm vào log.

Trung tâm của bài toán là **persistence unit (PU)**: đơn vị cấu hình xác định tập entity được quản lý, JPA provider, transaction model, dữ liệu kết nối và những thuộc tính điều khiển provider. Trong Java SE, `persistence.xml` thường khai báo PU và `Persistence.createEntityManagerFactory(...)` khởi tạo nó. Trong Jakarta EE, application server có thể cung cấp DataSource và JTA transaction. Trong Spring Boot, framework thường tự tạo `EntityManagerFactory` từ `DataSource`, entity scanning và các properties mà không nhất thiết cần một `persistence.xml` do lập trình viên viết.

Ví dụ một cấu hình dành cho phát triển:

```properties
# Minh họa: cấu hình provider cụ thể, CHỈ dành cho local DB.
jakarta.persistence.jdbc.url=jdbc:postgresql://localhost:5432/orders_dev
hibernate.show_sql=true
hibernate.hbm2ddl.auto=update
```

sẽ **nguy hiểm nếu áp nguyên vào production**. Database production cần quyền hạn tối thiểu, migration có kiểm soát, logging tránh rò dữ liệu và một transaction/cache/pool strategy phù hợp tải thực tế. Thậm chí ở local, `update` không thay thế kiểm thử migrations thật.

> **Nguyên tắc xuyên suốt:** **Một bản build, nhiều môi trường; hợp đồng JPA và schema được quản lý rõ ràng; cấu hình phụ thuộc môi trường được cấp qua cơ chế đáng tin; secrets không nằm trong source; mỗi lần khởi động phải xác nhận mình đang dùng đúng persistence unit, database, transaction model và migration state.**

Bài học này thuộc chương **Vận hành và di trú** của module **Data Persistence Relational Access ORM JPA**. Ta sẽ đi từ cấu trúc persistence unit đến cấu hình Java SE, Jakarta EE và Spring Boot; tách dev/test/staging/prod; quản lý secrets, provider options, transaction, schema migrations, multiple persistence units, multi-tenancy, observability, triển khai rolling/blue-green, rollback, kiểm thử cấu hình và xử lý sự cố.

---

## 1. Persistence unit là gì và tại sao nó quan trọng?

**Persistence unit** là một tập metadata và cấu hình mà JPA provider dùng để tạo `EntityManagerFactory`, từ đó tạo/cung cấp các `EntityManager` và quản lý entity lifecycle.

```text
Application code
      |
      v
EntityManagerFactory
      |
      +-- Persistence Unit: ordersPU
      |      |
      |      +-- entity classes / mapping files
      |      +-- JPA provider
      |      +-- transaction type
      |      +-- DataSource / JDBC details
      |      +-- standard JPA properties
      |      +-- provider extensions
      |
      v
EntityManager(s)
      |
      v
JDBC / connection pool
      |
      v
Database
```

### 1.1. Những gì PU có thể xác định

| Thành phần | Ví dụ | Đổi theo môi trường? |
| --- | --- | --- |
| Tên PU | `ordersPU` | Thường giữ ổn định |
| Entity classes | `PurchaseOrder`, `Customer` | Nên giữ cùng artifact |
| Mapping metadata | `@Table`, `@JoinColumn`, `orm.xml` | Giữ ổn định, thay bằng migration có kiểm soát |
| Provider | Hibernate hoặc EclipseLink | Thường giữ một provider/version theo release |
| Transaction type | `RESOURCE_LOCAL` hoặc `JTA` | Theo deployment architecture, không tự thay tùy tiện |
| JDBC URL / DataSource | `orders_dev`, `orders_prod` | **Phải khác theo môi trường** |
| Username/credentials | Local account, runtime role | **Phải tách** |
| Schema management | create/drop, none, validate | Test và production khác nhau |
| SQL logging | DEBUG/TRACE hoặc OFF | Khác theo bảo mật và troubleshooting |
| Pool sizing | 3 connections hoặc 20 connections | Theo workload và database limits |
| Cache | Disabled/testing hoặc tuned | Theo consistency/performance requirements |
| Timeouts, batching | Giá trị đo trên từng môi trường | Có thể khác, phải có baseline |

Tách đúng dữ liệu **ít thay đổi và thuộc artifact** khỏi dữ liệu **phụ thuộc môi trường và vận hành** là nền tảng để deploy an toàn.

### 1.2. PU không đồng nghĩa một database

Một application có thể có nhiều persistence units dùng các databases khác nhau. Ngược lại, hai PUs có thể cùng trỏ một database/schema — điều này cần chủ đích vì chúng không tự chia sẻ cùng một persistence context, cache hoặc transaction coordination.

### 1.3. PU không đồng nghĩa schema

Tên PU `ordersPU` không buộc DB schema phải tên `orders`. Schema/catalog search paths, table mappings và default schema có thể được điều khiển riêng theo DBMS/provider. Không suy kết nối đúng chỉ vì tên PU đúng.

### 1.4. PU không phải một transaction

`EntityManagerFactory` thường được tạo một lần cho ứng dụng và có thể cung cấp nhiều `EntityManager`. Mỗi hoạt động transaction phải dùng transaction boundary phù hợp; đừng tạo một `EntityManagerFactory` mới cho mỗi HTTP request.

## 2. Hợp đồng chuẩn Jakarta Persistence và phần mở rộng provider

Cấu hình cần phân biệt hai nhóm.

**Nhóm tiêu chuẩn Jakarta Persistence** gồm những API/thuộc tính như:

- `META-INF/persistence.xml` và `<persistence-unit>`.
- `transaction-type="RESOURCE_LOCAL"` hoặc `"JTA"`.
- `<jta-data-source>` và `<non-jta-data-source>`.
- `jakarta.persistence.jdbc.url`, `jakarta.persistence.jdbc.user`, `jakarta.persistence.jdbc.password`, `jakarta.persistence.jdbc.driver`.
- `jakarta.persistence.schema-generation.database.action`.
- `jakarta.persistence.schema-generation.scripts.action` và các cấu hình script/source/target liên quan.
- `jakarta.persistence.sharedCache.mode` hay `<shared-cache-mode>` theo cách cấu hình tương ứng của đặc tả.
- `jakarta.persistence.validation.mode` và `<validation-mode>`.

**Nhóm riêng của Hibernate** có thể gồm:

- `hibernate.hbm2ddl.auto` (ví dụ `validate`, `update`).
- `hibernate.show_sql` / `hibernate.format_sql`.
- `hibernate.generate_statistics`.
- `hibernate.jdbc.batch_size`.
- `hibernate.default_batch_fetch_size`.
- `hibernate.cache.use_second_level_cache`.
- `hibernate.physical_naming_strategy`.
- Một số properties dialect/connection/pool khác theo version.

**Spring Boot** lại có lớp cấu hình riêng như `spring.datasource.*`, `spring.jpa.*` và `spring.flyway.*`; Spring chuyển một số thông tin xuống Hibernate/JPA, một số khác được Spring hoặc HikariCP tiêu thụ.

### 2.1. Vì sao phải phân loại?

Khi đổi từ Hibernate sang EclipseLink, việc dùng `EntityManager` vẫn có thể giữ nguyên, nhưng `hibernate.hbm2ddl.auto=validate` không tự được provider mới hiểu. Khi đổi từ Java SE sang application server/JTA, cách lấy connection và bắt đầu transaction thay đổi.

### 2.2. API cấu hình chuẩn không bảo đảm runtime behavior giống nhau

Ngay cả `jakarta.persistence.query.timeout` hay shared cache hints cũng có mức hỗ trợ/hiệu quả phụ thuộc provider, JDBC driver và DBMS. **Portability của property name không có nghĩa mọi môi trường thực thi đồng nhất**.

### 2.3. Quy tắc vận hành

Mỗi property đáng chú ý nên có:

1. **Chủ sở hữu**: chuẩn JPA, Hibernate, Spring, driver, pool hay DBMS.
2. **Giá trị mặc định thực tế** trên stack đã pin.
3. **Nguồn override** giữa các môi trường.
4. **Rủi ro** khi cấu hình sai.
5. **Cách xác nhận** nó có hiệu lực.

## 3. Cấu trúc persistence.xml cơ bản

Trong Java SE, file thường nằm ở:

```text
src/main/resources/META-INF/persistence.xml
```

Ví dụ Jakarta Persistence 3.1:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      https://jakarta.ee/xml/ns/persistence
      https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit
        name="ordersPU"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>
            com.example.orders.domain.PurchaseOrder
        </class>
        <class>
            com.example.orders.domain.Customer
        </class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="none"/>
        </properties>
    </persistence-unit>
</persistence>
```

Đây là ví dụ lựa chọn **Hibernate làm provider** và resource-local transactions. Các phiên bản Jakarta Persistence khác có version/schema XML khác; cần dùng XML namespace/version phù hợp dependency đã khóa.

### 3.1. Vì sao không đặt JDBC password trong XML?

Vì `persistence.xml` thường được đóng gói vào JAR/WAR, đưa lên artifact registry và deploy qua nhiều môi trường. Ghi mật khẩu production vào đó làm secrets tồn tại trong artifact và source history.

### 3.2. Vì sao dùng tên PU ổn định?

`ordersPU` là một logical name mà code/bootstrap có thể dùng ở mọi môi trường. Thay đổi tên PU theo `ordersPU-dev`, `ordersPU-prod` không cần thiết nếu khác biệt chỉ là connection properties.

### 3.3. Provider element có nên cố định?

Thêm `<provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>` giúp khởi động rõ ràng trên stack Hibernate. Nhưng nó cũng cố ý phụ thuộc Hibernate. Nếu sản phẩm thực sự cần đổi provider, cần chiến lược discovery/config riêng và test matrix thay vì nghĩ xóa tên provider là đủ để có portability.

### 3.4. exclude-unlisted-classes

`<exclude-unlisted-classes>true</exclude-unlisted-classes>` giúp kiểm soát entity membership khi danh sách `<class>` rõ ràng, nhưng yêu cầu thêm entity mới vào metadata đúng cách. Cơ chế quét entity có thể khác giữa Java SE/Jakarta EE/Spring. Test bootstrap phải chứng minh những entity mong đợi được đăng ký.

### 3.5. Không lặp cùng một PU ở nhiều persistence.xml không kiểm soát

Nhiều modules/JARs có `META-INF/persistence.xml` trùng tên PU có thể khiến bootstrap/packaging khó dự đoán tùy môi trường. Hãy thiết kế ownership của từng PU và kiểm tra artifact cuối cùng.

## 4. Cách một persistence unit được khởi tạo

Trong Java SE:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("ordersPU");
```

Provider đọc metadata và tạo factory. Sau đó:

```java
try (EntityManager em = emf.createEntityManager()) {
    // Dùng EntityManager theo transaction lifecycle thích hợp.
}
```

Ví dụ try-with-resources chỉ thích hợp khi kiểu `EntityManager` trong Jakarta Persistence version đang dùng là `AutoCloseable`; nếu dùng version/API không hỗ trợ, dùng `try/finally { em.close(); }`. Trong các ví dụ dưới đây, ta dùng `try/finally` để tránh phụ thuộc vào điều này.

### 4.1. Đừng khởi tạo EntityManagerFactory theo từng request

Tạo `EntityManagerFactory` thường tốn chi phí metadata, provider startup và cache/connection infrastructure. Một service Java SE thường tạo factory một lần cho application lifecycle và đóng khi shutdown.

### 4.2. Đừng chia sẻ EntityManager giữa các threads

`EntityManager` không được thiết kế như một singleton dùng đồng thời bởi nhiều threads. Tạo/sử dụng nó theo scope transaction/request phù hợp.

### 4.3. Nên đóng đúng resources

`EntityManager.close()` và `EntityManagerFactory.close()` là các thao tác lifecycle khác nhau. Trong Spring/Jakarta EE, framework hoặc container quản lý nhiều resources; không tự đóng injected container-managed entity manager.

## 5. Java SE: override JDBC properties theo môi trường

`Persistence.createEntityManagerFactory(String, Map)` cho phép truyền các configuration properties tại bootstrap.

Giữ `persistence.xml` chứa mapping và những options chung, còn runtime lấy cấu hình kết nối từ environment/secret provider:

```java
package com.example.orders.bootstrap;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.util.HashMap;
import java.util.Map;

public final class PersistenceBootstrap {

    private PersistenceBootstrap() {}

    public static EntityManagerFactory createFactory() {
        String jdbcUrl = requiredEnv("ORDERS_JDBC_URL");
        String username = requiredEnv("ORDERS_DB_USER");
        String password = requiredEnv("ORDERS_DB_PASSWORD");

        Map<String, Object> properties = new HashMap<>();

        properties.put(
            "jakarta.persistence.jdbc.url",
            jdbcUrl
        );
        properties.put(
            "jakarta.persistence.jdbc.user",
            username
        );
        properties.put(
            "jakarta.persistence.jdbc.password",
            password
        );
        properties.put(
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver"
        );
        properties.put(
            "jakarta.persistence.schema-generation.database.action",
            "none"
        );

        return Persistence.createEntityManagerFactory(
            "ordersPU",
            properties
        );
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing required environment variable: " + name
            );
        }
        return value;
    }
}
```

### 5.1. Ưu điểm

- Một artifact dùng cho nhiều môi trường.
- URL và credentials được inject khi deploy.
- Thiếu cấu hình bắt buộc sẽ **fail fast**.
- Không đưa password vào logs hoặc Git.
- Có thể override settings theo test harness.

### 5.2. Điểm cần cẩn trọng

- Một environment variable là một **kênh chuyển secret**, chưa phải secret manager hoàn chỉnh. Trong môi trường có yêu cầu bảo mật cao, cân nhắc Vault, cloud secret manager hoặc workload identity.
- Không log toàn bộ map `properties` vì có password.
- Không đặt default kiểu `jdbc:postgresql://prod...` khi thiếu biến.
- Không chạy fallback về H2 khi production JDBC URL thiếu.
- Đặt tên biến theo ý nghĩa rõ để tránh nhầm giữa Order DB và Analytics DB.
- Đảm bảo đúng driver/provider được đóng gói trong artifact.

### 5.3. Thứ tự ưu tiên cấu hình

Map truyền lúc bootstrap có thể override những property entries trong `persistence.xml` theo contract/cơ chế hỗ trợ, nhưng **không nên giả định một precedence chung cho tất cả properties ở mọi framework**. Jakarta EE có container overrides, Spring có external configuration và programmatic factory customizers.

Hãy xác định thứ tự cụ thể của framework/provider đang dùng, rồi kiểm tra **giá trị có hiệu lực sau khi factory/connection được tạo**.

### 5.4. Không đặt password trong command-line flags tùy tiện

Các tham số CLI hoặc shell history/process inspection có thể làm rò thông tin. Dùng secure injection phù hợp với hạ tầng.

## 6. Resource-local transactions và JTA là hai mô hình khác

`transaction-type` tác động sâu đến cách application bắt đầu/commit transaction.

### 6.1. RESOURCE_LOCAL

Trong Java SE resource-local:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    PurchaseOrder order = new PurchaseOrder(...);
    em.persist(order);

    em.getTransaction().commit();
} catch (RuntimeException e) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw e;
} finally {
    em.close();
}
```

`getTransaction()` trả `EntityTransaction` để ứng dụng quản lý boundaries.

### 6.2. JTA

Trong Jakarta EE hoặc một runtime được tích hợp JTA:

```xml
<persistence-unit
    name="ordersPU"
    transaction-type="JTA">

    <jta-data-source>
        java:app/jdbc/OrdersDataSource
    </jta-data-source>
</persistence-unit>
```

Application/container thường dùng transaction manager hoặc `@Transactional` phù hợp để phối hợp transaction:

```java
@PersistenceContext(unitName = "ordersPU")
private EntityManager em;

@Transactional
public void createOrder(PurchaseOrder order) {
    em.persist(order);
}
```

Đây là ví dụ ở môi trường container/Jakarta Transactions thích hợp. Không gọi `em.getTransaction().begin()` trong JTA container-managed flow như resource-local.

### 6.3. jta-data-source và non-jta-data-source

`<jta-data-source>` trỏ nguồn connection được tích hợp JTA. `<non-jta-data-source>` mô tả nguồn non-JTA theo cấu hình/runtime tương ứng.

Chọn sai loại DataSource có thể gây transaction không enlist, auto-commit sai hoặc thay đổi không rollback như mong đợi.

### 6.4. Có thể đổi transaction-type giữa môi trường không?

Có thể trong những hệ thống có mục tiêu cụ thể, nhưng đó là **thay đổi kiến trúc execution**, không chỉ sửa một connection string. Nếu local dùng RESOURCE_LOCAL còn production JTA, integration tests cần bao phủ transaction boundaries sát production để phát hiện lỗi flush/commit/rollback.

### 6.5. Spring @Transactional không đồng nghĩa JTA

Spring `@Transactional` là abstraction của Spring Transaction Management. Tùy transaction manager, nó có thể quản lý JPA resource-local transaction hoặc JTA. Không thể suy transaction type của PU chỉ từ annotation đó.

## 7. DataSource và connection pooling

Trong production, connection thường được cung cấp bởi **DataSource/connection pool** thay vì mỗi `EntityManager` mở một physical connection mới theo cách thô.

```text
Application threads
      |
      v
JPA EntityManager(s)
      |
      v
JDBC DataSource / pool
  idle / active / pending
      |
      v
Database max_connections
```

### 7.1. Những settings thay đổi theo môi trường

| Setting | Dev/Test | Production |
| --- | --- | --- |
| Pool max size | Nhỏ | Theo tải, pod count và DB limits |
| Connection timeout | Đủ ngắn để test fail rõ | Theo SLO và retry policy |
| Idle connections | Thấp | Theo cost/concurrency |
| Connection max lifetime | Có thể mặc định | Phù hợp network/proxy DB timeout |
| Connection validation | Basic | Health check và resilience policy |
| Leak detection | Khi debug | Sampling/guardrails nếu có |
| Statement timeout | Test-specific | Theo endpoint và workloads |
| TLS | Có thể tắt trên local isolated DB | Bật theo security policy |

### 7.2. Pool size phải tính toàn hệ thống

Nếu mỗi pod có max pool 20 và triển khai 15 pods, lý thuyết có thể có tới 300 connections của riêng service, chưa tính batch jobs và admin tools.

```text
max_database_connections_needed
  ≈ max_connections_per_instance
    × max_simultaneous_instances
    + other_clients
    + safety_margin
```

Đây là ước lượng capacity, không phải công thức chính xác cho mọi workload. Cần đối chiếu với DB service limits.

### 7.3. Một pool lớn không luôn nhanh hơn

Pool quá lớn có thể làm database chịu nhiều queries tranh CPU/IO cùng lúc và tăng latency. Benchmark thông lượng và p95/p99 ở điều kiện tương tự production.

### 7.4. Pool timeout không giống JDBC statement timeout

Chờ **lấy connection** và chờ **SQL execution** là hai loại latency khác nhau. Cần metrics riêng để chẩn đoán đúng.

## 8. Ma trận cấu hình dev, test, staging, production

Một cách quản lý là viết ma trận theo **mục tiêu**, không bắt đầu bằng copy nhiều file cấu hình rồi sửa thủ công.

| Chiều | Local dev | Integration test | Staging | Production |
| --- | --- | --- | --- | --- |
| DBMS | Có thể PostgreSQL local | PostgreSQL Testcontainers | Cùng DBMS major mục tiêu | DBMS được hỗ trợ chính thức |
| DB name | `orders_dev` | DB tạm | `orders_stage` | `orders_prod` |
| Credentials | Local least-privilege | Ephemeral | Secret manager | Secret manager/runtime role |
| DDL | Migrations ưu tiên | Migrations từ DB sạch | Chỉ migrations pipeline | Chỉ migrations pipeline |
| JPA schema action | `none` hoặc setup cô lập | `none` với migrations | `none` | **`none`** |
| Hibernate validate | Tùy stack | Nên cân nhắc | Cân nhắc | Theo policy khởi động |
| SQL log | DEBUG theo nhu cầu | DEBUG khi chẩn đoán | Có sampling/redaction | Không bật bind TRACE mặc định |
| Batch/Fetch | Dùng baseline | Cố định để test | Tương đương prod | Theo benchmark |
| L2 cache | Có thể tắt để dễ debug | Tắt/bypass hoặc test riêng | Gần prod | Theo consistency/SLO |
| Pool | Nhỏ | Nhỏ/cô lập | Tương tự workload | Theo capacity |
| Alert/metrics | Basic | Tests/logs | Validation | SLO, dashboards |
| Seed data | Synthetic | Fixture | De-identified | Dữ liệu nghiệp vụ thật |

### 8.1. Không bắt buộc mọi giá trị giống production

Ví dụ production pool 20 nhưng test có 2 connections vẫn đủ cho một test mapping; test concurrent locking sẽ cần setup ít nhất hai independent connections.

### 8.2. Những giá trị nên giống khi kiểm thử hành vi

- DBMS major version và JDBC driver phù hợp.
- JPA provider và SQL dialect.
- Migration schema.
- ID generation.
- Transaction type/isolation khi behavior phụ thuộc.
- Entity scanning/mapping.
- Những cache/fetch settings ảnh hưởng test scenario.

### 8.3. Khi nào staging cần gần production hơn?

Nếu staging dùng để kiểm thử rollout, locks, RLS, TLS, network/proxy hoặc performance, chênh lệch cấu hình lớn sẽ làm staging mất ý nghĩa. Nhưng staging vẫn không tự đại diện production-scale workload.

## 9. Spring Boot: nguồn cấu hình có lớp riêng

Trong Spring Boot, một ứng dụng JPA điển hình dùng:

```text
application.yml
application-dev.yml
application-test.yml
application-staging.yml
application-prod.yml
       |
       v
Spring externalized configuration
       |
       v
DataSource + ConnectionPool
       |
       v
EntityManagerFactory / transaction manager
       |
       v
Hibernate / JDBC / DBMS
```

Spring Boot thường tự cấu hình persistence unit dựa trên entity scanning, `DataSource`, Hibernate provider và Spring Boot JPA properties; không nhất thiết cần `META-INF/persistence.xml` thủ công.

### 9.1. application.yml: những mặc định an toàn

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: none
    properties:
      hibernate:
        format_sql: false

  flyway:
    enabled: true

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: WARN
```

Đây là **cấu hình Spring Boot/Hibernate**, không phải XML JPA chuẩn. Tên/behavior một số properties có thể thay đổi theo Spring Boot/Hibernate major version.

### 9.2. Vì sao mặc định không tạo schema?

Nếu người vận hành quên bật profile hoặc secret không được inject, trạng thái mặc định nên **an toàn**, không cho ORM tự tạo/xóa/đổi tables trên một DB ngoài ý muốn.

### 9.3. Vì sao open-in-view=false?

`spring.jpa.open-in-view=false` là tùy chọn Spring có thể giúp tránh lazy loading vô tình ở serialization layer và làm rõ service transaction boundary. Nó không giải quyết toàn bộ vấn đề fetch plan và cũng không thuộc JPA standard.

### 9.4. Migrations được bật không đồng nghĩa có quyền DDL

Spring Flyway có thể cần một migration DataSource/credential riêng. Tùy deployment, migrations có thể chạy trong CI/CD job độc lập và application runtime không chạy Flyway. Chọn **một chủ thể chịu trách nhiệm triển khai schema**.

## 10. application-dev.yml: tiện debug nhưng vẫn kiểm soát

```yaml
spring:
  datasource:
    url: "${ORDERS_DB_URL:jdbc:postgresql://localhost:5432/orders_dev}"
    username: "${ORDERS_DB_USER:orders_dev}"
    password: "${ORDERS_DB_PASSWORD:}"

    hikari:
      maximum-pool-size: 4

  jpa:
    properties:
      hibernate:
        format_sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
```

`${...}` là cú pháp placeholder của Spring sau khi file được ghi; dấu `:` thể hiện default trong cú pháp Spring property placeholder tương ứng.

### 10.1. Default chỉ nên trỏ vào DB local

Một local default như `localhost/orders_dev` có thể giúp developer bắt đầu nhanh. Nhưng production không nên có fallback URL hoặc username/password local.

### 10.2. Không đặt dev password thật vào repository

Ví dụ để trống default password có ý nghĩa tránh hard-code credential. Khi chạy local, inject từ developer secret store hoặc local env không commit.

### 10.3. SQL bind logging

Trong môi trường dev với test data, có thể bật `org.hibernate.orm.jdbc.bind` để debug binding khi cần. Không bật TRACE bind logging vô điều kiện với dữ liệu khách hàng thật.

### 10.4. DDL update trong dev?

`hibernate.hbm2ddl.auto=update` có thể tiện cho một prototype local disposable DB, nhưng làm tăng chênh lệch với staging/prod schema. Với một dự án có migrations, **dùng migrations ngay ở dev** giúp phát hiện sai lệch trước.

## 11. application-prod.yml: fail-closed với cấu hình quan trọng

Ví dụ:

```yaml
spring:
  datasource:
    url: "${ORDERS_DB_URL}"
    username: "${ORDERS_DB_USER}"
    password: "${ORDERS_DB_PASSWORD}"

    hikari:
      maximum-pool-size: 16
      connection-timeout: 3000

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: none
    properties:
      hibernate:
        show_sql: false
        format_sql: false
        generate_statistics: false
        jdbc:
          batch_size: 32

  flyway:
    enabled: false

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: WARN
```

Đây là **một lựa chọn kiến trúc mẫu**: migrations chạy bằng job độc lập trước application rollout, nên Flyway bị tắt ở runtime app. Nếu dự án chọn app-startup migrations, cấu hình và quyền DB phải khác; không copy `flyway.enabled=false` mà bỏ luôn migrations.

### 11.1. Giá trị ví dụ không phải ngưỡng tối ưu chung

`maximum-pool-size=16`, `connection-timeout=3000`, `batch_size=32` chỉ minh họa. Cần hiệu chỉnh theo DB capacity, số pods, workloads, ID strategy và SLO.

### 11.2. Fail fast khi thiếu secret

Nếu biến `ORDERS_DB_PASSWORD` không được cấp, production nên fail khi bootstrap/thử connection thay vì tự chuyển sang một database khác.

### 11.3. DDL guardrails

Production nên có ít nhất:

- `database.action=none` trong cấu hình JPA tương ứng.
- Không bật Hibernate `hbm2ddl.auto=create`, `create-drop` hoặc `update`.
- DB application role không có quyền CREATE/ALTER/DROP không cần thiết.
- Migrations thuộc deployment job/role đã kiểm soát.
- Startup validation/health checks phù hợp.

Đừng chỉ tin một dòng `ddl-auto=none` nếu một property override khác có thể bật DDL trên runtime.

### 11.4. Hibernate statistics production

`hibernate.generate_statistics=true` hữu ích khi debug nhưng có overhead/counter scope. Dùng theo chiến lược observability và đo overhead. Không coi nó là lựa chọn mặc định bắt buộc để “giám sát”.

## 12. application-test.yml: database test độc lập

Một test profile có thể dùng Testcontainers PostgreSQL cùng migrations.

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false

  flyway:
    enabled: true

logging:
  level:
    org.hibernate.SQL: DEBUG
```

`validate` trong `ddl-auto` là hành vi Hibernate-specific, không phải một `jakarta.persistence.schema-generation.database.action` chuẩn.

### 12.1. Không mặc định để @DataJpaTest thay DB thành H2

Nếu test muốn PostgreSQL container, kiểm soát DataSource replacement theo version Spring Boot, ví dụ dùng `@AutoConfigureTestDatabase(replace = NONE)` khi phù hợp.

### 12.2. JDBC URL/port từ container, không cố định

Dùng `postgres.getJdbcUrl()` và dynamic properties/`@ServiceConnection` (nếu version hỗ trợ) thay vì hard-code port 5432.

### 12.3. Test nên dùng database thật khi behavior phụ thuộc DBMS

Nếu production là PostgreSQL và use case dùng `jsonb`, partial indexes, sequences, RLS hoặc locking semantics, test H2 compatibility mode không đủ để khẳng định tương đương.

### 12.4. Test schema và migration từ trạng thái rỗng

`PostgreSQL container -> Flyway/Liquibase -> JPA bootstrap -> tests` giúp xác nhận mapping trên schema thật.

### 12.5. Test upgrade schema cần dữ liệu cũ

Một database trắng không phát hiện mọi lỗi backfill hay constraints khi production có historical rows. Cần suite riêng tạo schema/data phiên bản cũ rồi apply migrations mới.

## 13. Chọn và kích hoạt đúng môi trường

Với Spring Boot, profiles giúp bật phần cấu hình phù hợp:

```text
SPRING_PROFILES_ACTIVE=dev
SPRING_PROFILES_ACTIVE=test
SPRING_PROFILES_ACTIVE=staging
SPRING_PROFILES_ACTIVE=prod
```

### 13.1. Profile không phải authorization

Một process `prod` không được phép tự tin vào thông tin “prod” do client gửi. Active profile là thông số deployment, không phải kiểm tra quyền truy cập database.

### 13.2. Đừng chỉ dựa vào profile string

Production guardrails nên còn có:

- Runtime DB credentials thiếu quyền DDL.
- Network policies chặn DB không thuộc môi trường.
- Secret boundaries theo namespace/account.
- Migrations pipeline độc lập.
- Checks về URL/DB identity/schema version.
- Monitoring những trường hợp config lạc môi trường.

### 13.3. Config precedence

Spring có nhiều nguồn: package files, profile files, environment variables, command-line properties, config servers, deployment overrides. **Thứ tự ưu tiên phải được xem theo Spring Boot version thực đang dùng.**

Một cấu hình `application-prod.yml` không đảm bảo thắng một environment override có ưu tiên cao hơn. Vì vậy test **effective configuration**, không chỉ xem source YAML.

### 13.4. Không bỏ undefined placeholder thành default nguy hiểm

Sai tư duy:

```yaml
spring:
  datasource:
    url: "${ORDERS_DB_URL:jdbc:postgresql://prod-db/orders}"
```

Nếu biến thiếu, app có thể âm thầm kết nối DB production thay vì fail. Đừng đặt production URL vào fallback.

## 14. Secrets: tách thông tin kết nối khỏi artifact

Một persistence unit thường cần database identity và secret.

### 14.1. Secrets không nên nằm trong

- `persistence.xml` đã commit.
- `application-prod.yml` trong repository.
- Unit test source code dùng credential production.
- Docker image layers.
- Logs/stack traces/raw configuration dumps.
- Git history hoặc công cụ paste/debug ngoài chính sách.

### 14.2. Những nơi có thể cấp secrets

- Cloud Secret Manager/Vault.
- Kubernetes Secret và secret injection phù hợp threat model.
- Runtime workload identity để lấy short-lived credentials.
- Encrypted config repository với access control thích hợp.
- Environment variables theo policy hạ tầng.
- Application server-managed JNDI DataSource.

### 14.3. Environment variable chưa phải secret storage an toàn tuyệt đối

Giá trị env có thể được thấy bởi một số diagnostics/process introspection hoặc deployment tooling tùy hệ thống. Hãy chọn cơ chế phù hợp với yêu cầu tổ chức và tránh log/env dumps.

### 14.4. Rotation

Nếu database password được thay, connection pool có thể giữ connections hoặc credentials cũ. Cần kế hoạch:

1. Tạo/đưa credential mới có giai đoạn giao thoa nếu DB hỗ trợ.
2. Cập nhật secret provider.
3. Cho app/pool tạo connections mới.
4. Quan sát auth failures.
5. Thu hồi credential cũ.
6. Kiểm tra không còn pods/jobs dùng secret cũ.

Không cho rằng thay file secret trên đĩa tự động khiến mọi existing connection dùng mật khẩu mới.

### 14.5. Phân quyền tách migration và runtime

Runtime account chỉ nên có SELECT/INSERT/UPDATE/DELETE hoặc quyền cụ thể cần thiết; schema migration account mới có CREATE/ALTER/DROP theo chính sách. Điều này giúp ngăn `hbm2ddl.auto=update` vô tình thay schema ngay cả khi một cấu hình sai được bật.

## 15. Quản lý schema: JPA generation khác migration

JPA có thuộc tính chuẩn:

```properties
jakarta.persistence.schema-generation.database.action=none
```

Một số giá trị action chuẩn là:

- `none`.
- `create`.
- `drop`.
- `drop-and-create`.

Đây là schema generation actions, không phải công cụ migration versioned đầy đủ.

### 15.1. Vấn đề khi dùng ORM tự sửa schema production

- Không có kế hoạch backfill cột cũ.
- Có thể tạo/drop objects ngoài dự kiến.
- Thiếu migration history.
- Không giải quyết tương thích hai application versions khi rolling deploy.
- Khó review/rollback.
- Có thể gây locks trên bảng lớn.
- Có thể làm mất dữ liệu nếu cấu hình destructive.

### 15.2. Flyway/Liquibase là một hướng quản lý schema

Một pipeline:

```text
Code + entity mapping
          |
          v
Review versioned migration
          |
          v
CI migrations test on target DBMS
          |
          v
Deploy migration with controlled identity
          |
          v
Verify schema version
          |
          v
Roll application code
```

Flyway/Liquibase không phải Jakarta Persistence APIs; chúng phối hợp với JPA bằng một data contract chung.

### 15.3. Một schema owner tại mỗi thời điểm

Nếu Flyway quản lý schema production, không để Hibernate `create-drop` hoặc `update` thay bảng sau đó. Tránh nhiều services cùng startup DDL trên shared schema.

### 15.4. Vì sao schema validation vẫn cần test?

Một provider-specific `validate` có thể phát hiện table/column mismatch ở bootstrap. Nhưng nó **không thay kiểm thử database constraints, index policy, triggers hoặc backfill correctness**.

### 15.5. Một cột mới cần nhiều bước

Không chỉ thêm:

```java
@Column(nullable = false)
private String shippingCode;
```

nếu production đang có hàng triệu orders chưa có giá trị này. Cần thiết kế migration expand/backfill/validate/contract theo độ tương thích ứng dụng.

## 16. Migration expand-and-contract khi nhiều phiên bản cùng chạy

Trong rolling deployment, application version N và N+1 có thể cùng kết nối một database trong vài phút hoặc lâu hơn.

### 16.1. Ví dụ đổi tên cột

Muốn đổi:

```text
purchase_orders.customer_name
  ->
purchase_orders.buyer_name
```

Một migration `RENAME COLUMN` ngay trước khi deploy app mới có thể làm app cũ không chạy được.

### 16.2. Quy trình an toàn hơn

**Expand:**

- Thêm cột `buyer_name` có khả năng tương thích.
- Đảm bảo app cũ tiếp tục chạy.
- Cập nhật write path hoặc dual write theo policy khi cần.

**Migrate/backfill:**

- Chép dữ liệu lịch sử.
- Cung cấp read fallback hoặc chuyển dần read path.
- Quan sát dữ liệu mới/cũ có nhất quán.

**Switch:**

- Deploy app đọc cột mới.
- Xác nhận mọi instances đã dùng mapping mới.

**Contract:**

- Khi không còn reader/writer cũ, bỏ cột cũ trong migration sau.

### 16.3. Tách backward và forward compatibility

Phải trả lời cả hai:

- App cũ có chạy với schema mới được expand không?
- App mới có chạy khi migration mới hoàn thành nhưng dữ liệu backfill chưa xong không?

Một migration đúng cú pháp vẫn có thể phá rolling deploy nếu không giải quyết hai điều này.

### 16.4. Rollback ứng dụng không đồng nghĩa rollback schema

Nếu application mới bị lỗi, thường muốn rollback code nhanh. Nhưng DDL destructive hoặc backfill đã commit có thể không thể đảo ngược an toàn. Vì vậy schema migration nên thiết kế theo hướng **backward-compatible cho ít nhất một cửa sổ rollback**.

## 17. Ràng buộc schema không được sinh tự động ngoài ý muốn

Trong production, các nguy cơ đặc biệt:

| Cấu hình | Có thể xảy ra | Độ an toàn trên DB có dữ liệu |
| --- | --- | --- |
| JPA `database.action=none` | Không yêu cầu schema generation | Phù hợp khi migrations quản lý schema |
| JPA `create` | Tạo schema objects theo generation | Không dùng tùy tiện |
| JPA `drop-and-create` | Drop rồi tạo schema | **Nguy hiểm** |
| Hibernate `hbm2ddl.auto=validate` | Kiểm tra mapping/schema một phần | Có thể hữu ích với policy rõ |
| Hibernate `hbm2ddl.auto=update` | Tự thay schema | Rủi ro nếu thay migration pipeline |
| Hibernate `hbm2ddl.auto=create-drop` | Tạo và drop theo lifecycle | Chỉ cho DB disposable theo setup phù hợp |

### 17.1. Đừng đặt niềm tin vào “đây là môi trường staging”

Staging có thể chứa dữ liệu test tốn công chuẩn bị hoặc dữ liệu đã de-identify. DDL destructive vẫn cần quyền kiểm soát và xác nhận.

### 17.2. Fail fast với DB identity mismatch

Nếu app được khai báo `DEPLOY_ENV=prod` nhưng kết nối `orders_dev`, phải có chính sách phát hiện mismatched target trước khi nhận traffic.

### 17.3. DB privileges là lớp bảo vệ cuối

Một runtime DB role không có quyền DROP/ALTER vẫn không thể thực hiện schema migration nguy hiểm dù có configuration bug; nhưng nó vẫn có thể làm hại dữ liệu qua DML nếu bị cấp quyền quá rộng. Authorization và tenant isolation vẫn cần thiết.

## 18. Nguồn sự thật của mapping và tên bảng/cột

Một môi trường chạy Hibernate với naming strategy A, môi trường khác chạy strategy B có thể sinh SQL tham chiếu tên khác.

Ví dụ:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Column(name = "created_at")
    private Instant createdAt;
}
```

Explicit naming giúp giảm phụ thuộc vào naming strategy, nhưng không loại hết khác biệt của provider/dialect.

### 18.1. Provider-specific naming configuration

Các thuộc tính như `hibernate.physical_naming_strategy` là Hibernate extensions. Nếu override theo profile, có thể vô tình làm mapping khác giữa test và production.

### 18.2. Nguyên tắc

- Giữ naming strategy ổn định trong cùng release.
- Version schema qua migrations.
- Dùng explicit column/table names cho schema contract quan trọng.
- Kiểm tra entity scanning/orm.xml packages.
- Chạy integration tests trên migration schema thật.

### 18.3. Default schema và search_path

Đúng JDBC URL chưa đủ nếu default schema khác. PostgreSQL có `search_path`, DBMS khác có catalog/schema concepts riêng. Một test nên xác nhận `current_database()` và `current_schema()` khi cần.

### 18.4. Không dùng schema search path từ request tùy ý

Nếu multi-tenancy dùng schema switching, tenant phải đến từ trusted context và pooled connections phải reset session state, tránh leakage giữa requests.

## 19. SQL dialect: auto-detection hay chỉ định rõ?

ORM provider cần biết database dialect/platform để sinh SQL về pagination, identity, sequence, locking, functions và types.

### 19.1. Hibernate dialect

Hibernate hiện đại thường có thể nhận diện dialect từ JDBC metadata trong những môi trường phù hợp. Có trường hợp team đặt rõ `hibernate.dialect` vì database/proxy/driver không cung cấp metadata đầy đủ hoặc dùng custom dialect.

### 19.2. Có nên khác giữa dev và prod?

Nếu production PostgreSQL nhưng dev H2, khác dialect là một tín hiệu rằng một số SQL behavior chưa được test tương đương. Có thể chấp nhận để chạy smoke tests nhanh, nhưng test contract quan trọng cần dùng PostgreSQL.

### 19.3. Cố định dialect sai nguy hiểm

Ép PostgreSQL dialect khi thật sự kết nối MySQL/H2 không biến engine đó thành PostgreSQL; nó có thể gây SQL syntax errors hoặc behavior khó dự đoán.

### 19.4. Kiểm tra lúc startup

Ghi rõ DB product/version và provider version (không tiết lộ credentials). Khi build bị chuyển DB ngoài ý muốn, thông tin này giúp điều tra nhanh.

## 20. Cấu hình cache: performance và consistency là trade-off

JPA có shared cache concepts và `EntityManagerFactory.getCache()`. Hibernate còn có L2/query cache extensions.

### 20.1. Tại sao cache có thể khác theo môi trường?

- Dev muốn dễ debug và thấy SQL nên có thể tắt L2.
- Integration test thường muốn tránh cache che mapping/read behavior.
- Production có thể bật L2 với entity ít thay đổi và strong invalidation policy.
- Staging nên mô phỏng cache behavior nếu tính đúng/phân phối tải phụ thuộc cache.

### 20.2. Test cold và warm cache riêng

`EntityManager.clear()` chỉ làm sạch L1; nó **không tự clear shared/L2 cache**.

Nếu test cần xác nhận SQL SELECT thực sự, có thể dùng `CacheRetrieveMode.BYPASS` hoặc cấu hình tắt shared cache phù hợp.

### 20.3. Cache không phải cấu hình “bật là nhanh”

Query cache/second-level cache có overhead, memory usage, invalidation và stale-data risk. Với bulk DML, native SQL hoặc external writers, consistency là vấn đề quan trọng.

### 20.4. Cache keys trong multi-tenancy

Nếu cache key không bao gồm tenant context phù hợp, có nguy cơ cross-tenant data leak tùy cache/provider mapping. Cần test isolation, không chỉ đo hit ratio.

## 21. JDBC batching, fetch plan và cấu hình hiệu năng

Ví dụ Hibernate:

```properties
hibernate.jdbc.batch_size=32
hibernate.order_inserts=true
hibernate.order_updates=true
hibernate.default_batch_fetch_size=24
```

### 21.1. Không phải cùng một loại batch

- `hibernate.jdbc.batch_size`: batching thao tác DML ở JDBC.
- `hibernate.default_batch_fetch_size`: gom các entity/association fetches.
- `setMaxResults(50)`: giới hạn kết quả query theo API chuẩn JPA.
- JDBC fetch size: hint về fetch rows trong driver.

### 21.2. Không mặc định tốt ở mọi môi trường

Nếu production dùng IDENTITY, một số Hibernate insert batching patterns có thể không thực hiện như kỳ vọng. Nếu batch size quá lớn, có thể tăng memory, lock duration hoặc số SQL parameters.

### 21.3. Cấu hình test nên phản ánh thứ cần kiểm tra

Khi test business correctness, có thể cố định batch size đơn giản. Khi test throughput/SQL ordering, cần chạy config gần production và quan sát JDBC executions.

### 21.4. Đổi fetch plan vì N+1 không nhất thiết cần đổi PU

Nhiều vấn đề N+1 nên xử lý ở query/DTO/EntityGraph hoặc domain boundary. `default_batch_fetch_size` là một tiện ích provider-specific, không thay thiết kế query rõ ràng.

## 22. Logging và bảo mật dữ liệu

SQL log rất hữu ích ở dev nhưng có thể mang dữ liệu nhạy cảm.

### 22.1. Hibernate SQL log

Ví dụ Hibernate 6 + Spring:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`org.hibernate.orm.jdbc.bind` có thể ghi parameter values; log có thể chứa PII, token, secret hoặc identifiers.

### 22.2. Production policy

- Không bật raw bind logging mặc định.
- Có redaction/sampling.
- Áp dụng log retention/access control.
- Không ghi toàn bộ persistence properties.
- SQL tracing nên dùng fingerprint/normalized statements khi phù hợp.
- Không đưa DB password/connection secrets vào error pages.

### 22.3. Log SQL có overhead

Khi cần benchmark, kiểm soát logging level giữa hai lần đo. Bật TRACE có thể làm kết quả latency khác đáng kể.

### 22.4. Thay thế quan sát

Dùng metrics về JDBC connection usage, request latency, database wait events, SQL execution count theo operation, tracing có redaction. Hibernate Statistics provider-specific hữu ích nhưng global counters không tự phân tách từng request.

## 23. Observability: xác nhận cấu hình có hiệu lực

Một application deployment nên có một tập thông tin để người vận hành biết nó khởi động với DB và PU đúng.

### 23.1. Startup diagnostic an toàn

Có thể ghi:

```text
service=orders-api
environment=prod
persistenceUnit=ordersPU
provider=Hibernate <version>
jdbcProduct=PostgreSQL
jdbcMajorVersion=16
schemaMigrationVersion=V42
transactionMode=RESOURCE_LOCAL (if confirmed)
poolMaxSize=16
schemaManagement=external-migrations
```

Đây là mẫu log, không phải giá trị thật của hệ thống.

### 23.2. Những gì không được log

- Password.
- Access token.
- Full JDBC URL nếu chứa username/password hoặc query params nhạy cảm.
- Private key/cert contents.
- Secret manager response bodies.
- Raw bind parameter values chứa PII.

### 23.3. Database identity check

Khi dùng PostgreSQL, `SELECT current_database(), current_schema()` là một cách biết connection đang trỏ đâu. Chỉ dùng thông tin được phép hiển thị trong logs/health diagnostics.

### 23.4. Health checks

Phân biệt:

- **Liveness**: process hoạt động.
- **Readiness**: process có thể nhận traffic, database connectivity và schema version tương thích.
- **Migration readiness**: migrations đã hoàn thành/được ứng dụng chấp nhận.

Không làm liveness phụ thuộc vào một query DB liên tục khiến hạ tầng restart application vô hạn khi DB gặp sự cố tạm thời.

### 23.5. Metrics

Các nhóm quan trọng:

| Nhóm | Ví dụ |
| --- | --- |
| Pool | active/idle/pending connections, acquisition latency |
| JPA operation | count, duration, errors |
| JDBC | execution count, timeout, latency |
| DB | CPU, IO, locks, slow queries |
| Transactions | commit, rollback, retry |
| Cache | hit/miss, invalidation anomalies |
| Schema | migration state/version, startup mismatch |
| API | p50/p95/p99, error rate |

## 24. Quản lý nhiều persistence units

Một ứng dụng có thể có:

```text
ordersPU -> orders database
analyticsPU -> analytics database
```

Ví dụ Java SE:

```xml
<persistence-unit
    name="ordersPU"
    transaction-type="RESOURCE_LOCAL">
    <class>com.example.orders.domain.PurchaseOrder</class>
</persistence-unit>

<persistence-unit
    name="analyticsPU"
    transaction-type="RESOURCE_LOCAL">
    <class>com.example.analytics.domain.SalesSnapshot</class>
</persistence-unit>
```

Các units cũng cần metadata provider và DataSource/properties tại bootstrap; snippet này chỉ thể hiện cấu trúc tên.

### 24.1. Bootstrap có chủ đích

```java
EntityManagerFactory ordersEmf =
    Persistence.createEntityManagerFactory(
        "ordersPU", ordersProperties
    );

EntityManagerFactory analyticsEmf =
    Persistence.createEntityManagerFactory(
        "analyticsPU", analyticsProperties
    );
```

### 24.2. Không trộn repositories

Một SalesSnapshot query không nên vô tình chạy bằng ordersPU. Entity membership và repository wiring phải xác định rõ.

### 24.3. @PersistenceContext unitName

Trong môi trường hỗ trợ injection:

```java
@PersistenceContext(unitName = "ordersPU")
private EntityManager ordersEm;

@PersistenceContext(unitName = "analyticsPU")
private EntityManager analyticsEm;
```

### 24.4. Hai PUs không tự có một atomic transaction

Nếu viết cả hai databases trong một business operation, resource-local transactions riêng không tạo distributed atomic commit. JTA/XA hoặc outbox/saga strategy cần được thiết kế khi requirement đòi hỏi consistency liên resource.

### 24.5. Tách names và credentials

`ORDERS_DB_URL`, `ANALYTICS_DB_URL` và secret scopes riêng giúp giảm nguy cơ accidental cross-database writes.

## 25. Multi-tenancy là cấu hình và security design, không chỉ URL

Chiến lược lưu trữ có thể là:

- Shared schema + cột `tenant_id`.
- Schema riêng mỗi tenant.
- Database riêng mỗi tenant.
- Hybrid.

### 25.1. Shared schema

PU có thể chung, nhưng mọi query/business operation cần tenant scope, composite FKs/UNIQUE theo tenant khi phù hợp, authorization và có thể có RLS.

### 25.2. Schema per tenant

Có thể cần schema switching theo connection/session. Phải reset state khi connection về pool; không lấy schema name trực tiếp từ untrusted request.

### 25.3. Database per tenant

Cần routing từ **trusted tenant context** tới đúng DataSource/PersistenceUnit/connection. Pool capacity, migrations và cache isolation là vấn đề riêng.

### 25.4. Hibernate multi-tenancy settings

Hibernate có extension dành cho tenant resolution/connection handling; không phải mọi giải pháp đều dùng chung PU wiring. Cần test theo version được triển khai và xác nhận cross-tenant isolation.

### 25.5. Không tin cache chỉ vì query đã có tenant predicate

Cache key, lazy loads, native SQL và query result cache đều cần kiểm soát tenant isolation theo provider.

## 26. Test cấu hình runtime thay vì đọc mỗi source file

Một cấu hình có thể trông đúng trong YAML nhưng bị override khi deploy.

### 26.1. Test bootstrap

Kiểm tra factory khởi động được với:

- Expected PU name.
- Expected provider.
- Expected entity mappings.
- Expected JDBC URL/DBMS.
- Expected transaction type.
- DDL disabled trong môi trường không disposable.
- Expected migration version.

### 26.2. Test fail-fast khi thiếu biến

Ví dụ unit test cho `requiredEnv` (hoặc abstraction cho config source) nên chứng minh thiếu `ORDERS_DB_URL` gây lỗi rõ, **không fallback** sang DB khác.

Đối với `System.getenv`, để test dễ dàng hơn có thể trừu tượng hóa config source qua interface/map thay vì sửa môi trường process trong test.

### 26.3. Test isolation giữa profiles

- Dev không kết nối prod.
- Test không kết nối local developer DB.
- Staging dùng secret/staging identity đúng.
- Production không dùng H2.
- Không profile nào bật destructive schema action ngoài disposable test.

### 26.4. Test migration

- Empty database → apply all migrations.
- Old database with legacy fixtures → apply new migrations.
- Mapping/entity round-trip sau migrate.
- Negative tests FK/UNIQUE/CHECK.
- Schema version được app chấp nhận.

### 26.5. Test không chỉ assert startup xanh

Một test chỉ tạo `EntityManagerFactory` thành công chưa chắc database constraints tồn tại, JSONB queries chạy hoặc locks đúng. Cần assertions ứng với contract.

## 27. Testcontainers cho PU trong integration test

Với PostgreSQL Testcontainers (API ví dụ theo nhóm phiên bản Java Testcontainers hỗ trợ):

```java
@Testcontainers
class OrderJpaIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.6");

    @Test
    void canBootstrapAgainstContainer() {
        Map<String, Object> props = Map.of(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl(),
            "jakarta.persistence.jdbc.user",
            postgres.getUsername(),
            "jakarta.persistence.jdbc.password",
            postgres.getPassword(),
            "jakarta.persistence.schema-generation.database.action",
            "none"
        );

        // Apply real migrations before creating EMF.
        // Then bootstrap and test entity/query behavior.
    }
}
```

Đây là khung minh họa: cần imports, dependencies, container lifecycle và migration setup đúng version. Một số major versions của Testcontainers thay đổi module names/packages; pin và theo tài liệu version của dự án.

### 27.1. Mục tiêu

Dùng PostgreSQL thật thay vì H2 để xác nhận:

- SQL dialect.
- Sequence/IDENTITY.
- FK/UNIQUE/CHECK.
- JSONB/native SQL nếu có.
- Transaction/locking behavior.
- Migrations.

### 27.2. Không hard-code port

Dùng `postgres.getJdbcUrl()` vì host port có thể được map động.

### 27.3. Spring @DataJpaTest

Với Spring, dùng `@DynamicPropertySource` hoặc `@ServiceConnection` nếu version hỗ trợ. Đảm bảo `@DataJpaTest` không thay DataSource container bằng embedded DB ngoài ý muốn.

### 27.4. Commit visibility vs rollback test

`persist -> flush -> clear -> find` trong cùng transaction kiểm tra round-trip tốt hơn L1-only test; nhưng để chứng minh committed visibility, commit transaction đầu rồi đọc qua EntityManager/transaction độc lập.

## 28. Thực hiện cấu hình theo một schema rõ ràng

Thay vì property files biến thiên tùy ý, có thể tổ chức một **configuration contract**.

Ví dụ:

```text
orders.persistence.unit.name     = ordersPU
orders.database.url              = (required)
orders.database.username         = (required)
orders.database.password         = (secret)
orders.database.dialect          = detected/explicit policy
orders.transaction.mode          = resource-local or JTA
orders.schema.owner              = migrations
orders.schema.expected-version   = V42
orders.jpa.ddl-action            = none
orders.jdbc.batch-size           = environment-tuned
orders.pool.max-size             = capacity-tuned
orders.metrics.enabled           = policy
```

Đây là **schema cấu hình khái niệm do team tự định nghĩa**, không phải một nhóm property names mặc định của JPA hoặc Spring.

### 28.1. Validate cấu hình sớm

- URL bắt buộc.
- Username/password hoặc workload identity hợp lệ.
- Pool max không âm/vượt capacity guardrail.
- Env/prod không cho phép destructive DDL.
- PU name nằm trong allowlist.
- Provider/DBMS version được hỗ trợ.
- Migration version tương thích.
- Tenant routing không có default tenant nguy hiểm.

### 28.2. Dùng typed configuration

Trong Spring Boot, có thể dùng `@ConfigurationProperties` và validation để quản lý các thuộc tính application-level, rồi map sang provider properties ở một nơi. Đừng rải `@Value("${...}")` không thống nhất khắp code.

### 28.3. Đừng tạo một lớp abstraction phức tạp hơn vấn đề

Nếu ứng dụng chỉ có một PU và một DBMS, cấu hình rõ trong vài files + secret injection đã đủ. Hãy tách adapter/multi-provider abstraction khi yêu cầu thực sự có.

## 29. Tại sao tránh cấu hình “môi trường là tên profile” duy nhất?

Profiles giúp chọn defaults, nhưng không giải quyết:

- Secrets.
- DB privileges.
- Network isolation.
- Migration version.
- Runtime DB identity.
- Pool capacity.
- Feature rollout.
- Read replicas.
- Tenant routing.
- Production failover.

### 29.1. Một lỗi deployment điển hình

```text
SPRING_PROFILES_ACTIVE=prod
ORDERS_DB_URL=jdbc:postgresql://staging-db/orders
```

Spring vẫn có thể khởi động nếu không có check khác. Log chỉ ghi “prod profile” không bảo đảm target database là prod.

### 29.2. Guardrail nhiều lớp

- Validate DB endpoint theo environment allowlist khi phù hợp.
- Runtime network segmentation.
- Separate cloud accounts/namespaces.
- Secret scopes riêng.
- Startup metadata check.
- DB role least privilege.
- Readiness fail nếu migration version không tương thích.

### 29.3. Tránh hard-coded production endpoints trong source

Endpoints và secrets phải được cung cấp bởi deployment management, không nhúng trong code tạo `EntityManagerFactory`.

## 30. Connection failures và retry policy

Một application có thể lỗi bootstrap vì DB chưa sẵn sàng, DNS, credential, schema version hoặc pool saturation.

### 30.1. Phân biệt các lỗi

| Triệu chứng | Khả năng nguyên nhân |
| --- | --- |
| Connection refused | Sai host/port, network, DB down |
| Authentication failed | Sai credential/role hoặc secret rotation |
| Unknown database/schema | URL/schema hoặc migrations sai |
| Relation does not exist | Migration chưa chạy hoặc search_path sai |
| Sequence does not exist | Generator mapping vs migrations mismatch |
| Permission denied | Runtime DB role thiếu grant |
| Schema validation failed | Mapping/schema không tương thích |
| Timeout acquiring connection | Pool saturation/connection leak |
| Query timeout | SQL/lock/network/query policy |
| Transactions not rolling back | Transaction manager/DataSource mismatch |

### 30.2. Retry phải có giới hạn

Một service có thể retry kết nối DB tạm thời khi khởi động, với backoff và giới hạn phù hợp. Không retry vô hạn với **wrong credentials** hoặc **incompatible schema version** và gọi đó là resilience.

### 30.3. Không tự chạy destructive schema fix

Khi table thiếu hoặc schema mismatch, production service không nên tự chuyển sang `create-drop` hoặc `update` để “sửa lỗi khởi động”. Cần kiểm tra migration pipeline và deploy state.

### 30.4. Phân biệt readiness với liveness

Database tạm thời unreachable có thể khiến service không ready; điều đó không nhất thiết phải gây restart process liên tục nếu liveness vẫn bình thường.

## 31. Di trú provider hoặc Jakarta namespace

Khi nâng từ hệ sinh thái `javax.persistence.*` sang `jakarta.persistence.*`, cần xem cả:

- Java imports và annotations.
- `persistence.xml` namespace/version.
- JDBC/JPA property prefixes.
- Entity listeners, converters.
- Validation API.
- Hibernate/EclipseLink version tương thích.
- Spring Boot/framework version.
- Bytecode enhancement tooling.
- Database schema migrations.
- SQL generation and dialect behavior.

### 31.1. Không chỉ đổi tên package

Một provider major version có thể đổi default type mappings, sequence behavior, generated SQL, cache handling hoặc query parser.

### 31.2. Test trên DBMS thật

So sánh cùng migrations, data fixtures và business queries trước/sau khi upgrade. Những test quan trọng:

- CRUD round-trip.
- Enum/UUID/JSON/timestamp mappings.
- Transactions/locking.
- Cascade/orphan removal.
- Generated IDs.
- Native SQL.
- Schema validation.
- SQL performance regression.

### 31.3. Giữ một chiến lược rollback có thực

Nếu code mới yêu cầu schema mới, cần xác nhận code cũ vẫn hoạt động với schema expanded hoặc có đường rollback triển khai có thể thực hiện an toàn.

### 31.4. Không trộn hai Jakarta Persistence versions trong cùng runtime

Dependency conflicts có thể gây `ClassNotFoundException`, `NoSuchMethodError` hoặc provider bootstrap errors. Lock BOM/dependencies nhất quán.

## 32. Staging và production: so sánh cấu hình hiệu lực

Staging thường phục vụ thử nghiệm cuối trước production nhưng có thể khác đáng kể.

### 32.1. Những yếu tố nên tương đương khi cần

- JPA provider major/minor.
- JDBC driver.
- DBMS engine/version.
- Migration state.
- Transaction manager.
- Entity scanning/naming.
- Cache mode (nếu feature cần).
- Batch/fetch tuning (nếu performance cần).
- DB roles/RLS behavior.
- Pool/network characteristics ở mức đại diện.

### 32.2. Những yếu tố không nên sao chép nguyên

- Production credentials.
- Dữ liệu nhận dạng cá nhân.
- Production database endpoint.
- Quyền DBA.
- Token/signing keys.
- Full production-sized pool nếu staging infrastructure không chịu được.

### 32.3. Cấu hình khác phải được ghi lý do

Ví dụ:

```text
staging.pool.max=8
prod.pool.max=16
reason=staging only has 1 DB instance and reduced traffic
```

Đây là metadata vận hành nội bộ, không phải JPA settings chuẩn.

### 32.4. Thử rollout

Có thể chạy canary/blue-green với schema compatible, check readiness và endpoint correctness trước khi chuyển traffic. Cấu hình PU phải phù hợp cả hai application versions trong cửa sổ rollout.

## 33. Database migration và transaction boundaries

Migrations có thể làm thay đổi schema trong khi application còn chạy.

### 33.1. Không chạy DDL mọi lúc app khởi động khi có nhiều replicas

Nếu 10 pods cùng khởi động và tự thay schema, có thể gây race, locks hoặc repeated migration attempts. Một migration job chuyên trách hoặc migration tool với locking/chính sách chạy một lần phù hợp sẽ rõ ràng hơn.

### 33.2. JDBC connections có thể giữ prepared statements

Sau schema changes, một số drivers/DBMS/pools có thể cần xử lý prepared statement caches và plan invalidation. Kiểm tra behavior trong staging khi thay đổi incompatible DDL.

### 33.3. Đừng coi rollback DDL đơn giản

Một số DDL/DBMS không hỗ trợ transactional rollback theo cách kỳ vọng. Một migration đã được apply có thể không dễ đảo ngược mà không mất dữ liệu.

### 33.4. Versioned migrations là lịch sử vận hành

Bản release nên biết mình tương thích với schema version range nào, không chỉ “migrations đã chạy gần đây”.

## 34. Phân quyền DB và sơ đồ deploy an toàn

```text
CI/CD pipeline
   |
   +--> migration job
   |      credentials = schema_migrator
   |      permissions = CREATE/ALTER as required
   |
   +--> deploy application
          credentials = orders_app
          permissions = scoped DML
          schema-generation = none
          readiness = schema version compatible
```

### 34.1. Vì sao tách roles?

Nếu application bị cấu hình sai `hbm2ddl.auto=update`, một role không có DDL privilege sẽ ngăn SQL thay schema. Đồng thời reduces blast radius nếu runtime bị khai thác.

### 34.2. Cẩn trọng với privilege thiếu

Nếu app cần đọc sequence, execute procedure hoặc quyền trên view nhưng role chưa được grant, lỗi có thể chỉ xuất hiện khi chạy use case tương ứng. Integration test với **runtime-like role** rất hữu ích.

### 34.3. RLS và connection pooling

Nếu dùng PostgreSQL RLS theo session/transaction variable, tenant context phải được đặt từ trusted identity và reset/scope đúng giữa pooled connections. Một app test dùng superuser có thể bypass RLS và che lỗi.

### 34.4. Security và consistency không chỉ là cấu hình PU

Bảo vệ resource authorization, parameterized JPQL, DTO validation, transaction invariants và DB constraints vẫn phải được thiết kế trong application/schema.

## 35. Đọc replica, primary và topology

Một ứng dụng có thể dùng primary để ghi và replicas để đọc.

```text
Write transaction
      |
      v
Primary database
      |
      +---- asynchronous replication ----> Read replica
```

### 35.1. Một PU có tự biết route read/write không?

Không có API chuẩn JPA quy định mọi PU sẽ tự tách read/write routing. Framework/provider/DataSource routing có thể làm điều đó nếu được cấu hình, nhưng transaction và consistency semantics cần rõ.

### 35.2. Read-your-writes

Một write vừa commit trên primary có thể chưa có trên replica do replication lag. Nếu nghiệp vụ cần đọc thấy ngay sau ghi, phải có routing/consistency policy phù hợp.

### 35.3. Transactions trên nhiều databases

Một `EntityManager` trỏ read replica không tự có cùng snapshot với write transaction trên primary. Với nhiều PUs, coordination và cache invalidation càng cần rõ.

### 35.4. Test cần topology tương ứng

Một PostgreSQL container đơn lẻ không tự kiểm thử replication lag/failover. Khi feature phụ thuộc topology, cần test môi trường nhiều instances hoặc staging chuyên biệt.

## 36. Vận hành schema compatibility khi deploy

Một release nên có các **preflight checks** trước khi nhận traffic.

### 36.1. Preflight cơ bản

- Environment đúng.
- DB endpoint nằm trong expected boundary.
- Secret/credential đã inject.
- Provider/JDBC driver compatible.
- Connection được mở với quyền đúng.
- Migration version đã apply.
- Required tables/sequences/indexes/constraints có mặt.
- Runtime không bật schema create/drop.
- Transaction manager đúng.
- Cache/multi-tenant context an toàn.

### 36.2. Preflight không thay integration tests

Chạy một `SELECT 1` xác nhận DB reachable nhưng chưa xác nhận `@ManyToOne` mapping hay native JSONB query chạy đúng.

### 36.3. Preflight lỗi thì làm gì?

Fail readiness/deployment rõ ràng, ghi diagnostics đã redacted và để pipeline/operator sửa migration/config. Tránh tự tạo schema ngoài policy.

### 36.4. Có nên kiểm tra mọi constraint mỗi request?

Không. Migration/schema tests và startup checks phù hợp hơn; request path nên tập trung business operations và metrics.

## 37. Quy trình thay đổi cấu hình có kiểm soát

Không phải mọi configuration change đều “nhẹ” hơn code change.

### 37.1. Phân loại thay đổi

| Loại | Ví dụ | Rủi ro |
| --- | --- | --- |
| Connection | DB URL, secret, TLS | Kết nối nhầm DB, downtime, credential leak |
| Transaction | RESOURCE_LOCAL ↔ JTA, isolation | Inconsistent commits/rollback |
| Schema | DDL action, naming strategy | Data loss/schema drift |
| Performance | Pool, batching, fetch size | DB saturation/latency regression |
| Cache | L2/query cache enable | Stale data, memory, tenant leak |
| Logging | SQL bind TRACE | PII exposure/overhead |
| Provider | Hibernate upgrade | SQL/mapping/semantics changes |
| Multi-tenancy | Schema routing | Cross-tenant data access |

### 37.2. Một thay đổi nên có gì?

- Lý do và expected effect.
- Owner của setting.
- Baseline metrics.
- Change review.
- Test strategy.
- Deployment window/canary.
- Rollback plan.
- Post-deployment monitoring.
- Cách tránh drift giữa môi trường.

### 37.3. Đừng thay nhiều biến cùng lúc

Nâng Hibernate, đổi pool size, bật L2 cache và thay schema migration trong cùng release sẽ làm regression khó quy nguyên nhân. Tách thay đổi theo khả năng và rủi ro.

### 37.4. Configuration drift

Nếu staging/prod khác nhau mà không có diff kiểm soát, lỗi chỉ xuất hiện trên một môi trường. Dùng IaC, GitOps hoặc một hệ thống quản lý cấu hình có audit và diff theo policy.

## 38. Phát hiện một cấu hình sai: tình huống thực tế

Giả sử sau deploy ứng dụng báo:

```text
ERROR: relation "purchase_orders" does not exist
```

Những khả năng:

1. Migration chưa chạy.
2. Kết nối nhầm database.
3. `current_schema()` sai.
4. Naming strategy khác.
5. Table được tạo ở schema khác.
6. DB role không đủ quyền và error được translate không rõ.
7. App code mới yêu cầu table chưa có ở migration version hiện tại.
8. Một test đã dùng Hibernate `create` nhưng production không dùng.

### 38.1. Trình tự điều tra

**Bước 1:** Xác nhận effective profile, datasource, DB product/version và schema (không log secrets).

**Bước 2:** Kiểm tra migration history/version.

**Bước 3:** So sánh entity mapping với schema thực.

**Bước 4:** Xem DDL action và Hibernate-specific overrides có gây bất ngờ không.

**Bước 5:** Kiểm tra quyền của runtime DB role.

**Bước 6:** Chạy integration test trên DB container đã apply migrations cùng version.

**Bước 7:** Đưa ra migration/config fix và deploy có kiểm soát.

### 38.2. Không được “chữa” bằng hbm2ddl.auto=update trong prod

Điều đó có thể làm một môi trường chạy tạm nhưng che thiếu sót ở migration pipeline và tạo thay đổi schema không được review.

### 38.3. Ghi nhận incident

Sau sự cố, nên thêm một test/guardrail tương ứng, ví dụ startup schema version check, CI migration test hoặc policy ngăn DDL ở production.

## 39. Một ví dụ sai về cấu hình gắn cứng

```java
public final class BadPersistenceConfig {

    public static EntityManagerFactory emf() {
        Map<String, Object> props = new HashMap<>();

        props.put(
            "jakarta.persistence.jdbc.url",
            "jdbc:postgresql://prod-db:5432/orders"
        );
        props.put(
            "jakarta.persistence.jdbc.user",
            "admin"
        );
        props.put(
            "jakarta.persistence.jdbc.password",
            "hardcoded-secret"
        );
        props.put(
            "hibernate.hbm2ddl.auto",
            "update"
        );

        return Persistence.createEntityManagerFactory(
            "ordersPU",
            props
        );
    }
}
```

Đây là **anti-pattern** minh họa, không phải cấu hình được khuyến nghị.

### 39.1. Những vấn đề

- Source chứa production endpoint.
- Có hard-coded secret.
- Dùng admin account.
- Tự sửa schema.
- Không có profile separation.
- Không có validation DB identity.
- Không có fail-fast khi config missing.
- Tests có thể kết nối nhầm production.

### 39.2. Hướng sửa

- Lấy JDBC URL và credential từ runtime secret/config source.
- Dùng account có quyền tối thiểu.
- Cấm schema mutation ở runtime.
- Chạy migrations riêng.
- Test đúng DBMS/schema trên container.
- Có startup checks và effective config diagnostics đã redacted.

## 40. Một ví dụ tốt về trách nhiệm giữa code và deployment

```text
Source repository:
  entity mapping
  repository code
  persistence unit logical name
  default-safe JPA configuration
  versioned migrations
  config validation rules
  tests

Build artifact:
  application classes + provider + JDBC driver
  no production secrets
  no production hard-coded DB URL

Deployment environment:
  environment name
  DB endpoint
  runtime identity / secret references
  pool settings
  feature flags
  observability config

Migration pipeline:
  schema identity
  privileged migrator role
  Flyway/Liquibase migrations
  schema version checkpoint

Running application:
  least-privileged runtime role
  schema generation disabled
  readiness checks
  JPA EntityManagerFactory
  controlled transaction lifecycle
```

### 40.1. Tại sao một artifact cho nhiều môi trường có lợi?

Giảm nguy cơ “test một code artifact, deploy một artifact khác”. Khác biệt môi trường được nhìn thấy trong config, không qua các source code branches ẩn.

### 40.2. Có trường hợp cần artifacts khác không?

Có, ví dụ build khác vì platform/native dependencies hoặc compliance policy. Nhưng nên phân biệt artifact-specific requirements với việc nhúng secrets/cấu hình môi trường vào bytecode.

### 40.3. Tránh thay entity mappings giữa môi trường

Một `@Column` khác cho staging/prod khiến test trên staging không xác nhận production behavior. Nếu bắt buộc khác biệt DBMS, phải có compatibility matrix/tests rõ.

## 41. Bài tập thực hành

### Bài 1 — Persistence unit name

Dev dùng `ordersPU-dev`, staging `ordersPU-stage`, prod `ordersPU-prod`, nhưng entity classes giống nhau.

**Gợi ý:** Cân nhắc một logical PU `ordersPU` và khác biệt datasource/config ở runtime. Không buộc tên PU chứa environment khi không có lý do kiến trúc.

### Bài 2 — Secret trong persistence.xml

Một `persistence.xml` có password production.

**Đáp án:** Không phù hợp. Tách secret injection và không commit credentials.

### Bài 3 — JDBC URL thiếu

Prod thiếu `ORDERS_DB_URL`, app fallback về local H2.

**Đáp án:** Sai fail-closed behavior. Production phải fail fast, không tự đổi database.

### Bài 4 — JTA và EntityTransaction

Ứng dụng chạy PU JTA nhưng code gọi `em.getTransaction().begin()`.

**Đáp án:** Sai transaction model. Dùng container/JTA transaction boundaries thích hợp, không thao tác resource-local `EntityTransaction`.

### Bài 5 — Spring @Transactional

Một service có `@Transactional`. Team kết luận PU chắc chắn transaction-type=JTA.

**Đáp án:** Không. Spring có nhiều transaction managers, bao gồm local JPA transaction manager.

### Bài 6 — Migrations

CI chạy Flyway migrations nhưng production bật Hibernate `hbm2ddl.auto=update`.

**Đáp án:** Có hai schema owners gây drift. Production nên tắt ORM auto schema updates.

### Bài 7 — Hibernate validate

Team dùng `hibernate.hbm2ddl.auto=validate` và khẳng định mọi FK/index đều đúng.

**Đáp án:** Không đủ. Validation kiểm tra một phần schema; cần migration/constraint tests.

### Bài 8 — Pool capacity

10 pods × 30 max connections, DB max 200 connections.

**Đáp án:** Capacity có nguy cơ vượt DB limit chưa tính clients khác. Cần điều chỉnh pool/instance count hoặc DB capacity và quan sát workload.

### Bài 9 — H2 và PostgreSQL

Test dùng H2 nhưng production dùng PostgreSQL JSONB.

**Đáp án:** Dùng PostgreSQL container cho JSONB/dialect tests.

### Bài 10 — Schema mismatch

Application production báo table không tồn tại dù CI build xanh.

**Gợi ý:** Kiểm tra DB identity, search_path/schema, migrations, naming strategy và quyền runtime.

### Bài 11 — Logging

Prod bật `org.hibernate.orm.jdbc.bind=TRACE` trên dữ liệu khách hàng.

**Đáp án:** Rủi ro lộ PII/credentials và overhead. Tắt mặc định, dùng redaction/sampling/debug policy.

### Bài 12 — L2 cache

Integration test `flush/clear/find` luôn pass nhưng không có SELECT.

**Đáp án:** L2 cache có thể được sử dụng. Tắt/bypass nếu mục tiêu xác nhận database read.

### Bài 13 — Rotation

Secret manager đổi DB password nhưng pool vẫn có kết nối cũ.

**Đáp án:** Rotation cần kế hoạch refresh/recreate connections, không chỉ thay secret file.

### Bài 14 — Runtime role

Ứng dụng `orders-api` có quyền DROP TABLE.

**Đáp án:** Thu hẹp theo least privilege; tách migrator role.

### Bài 15 — Rolling deploy

Release mới rename column trực tiếp, khiến pods cũ lỗi SQL.

**Đáp án:** Dùng expand-and-contract, giữ schema tương thích trong cửa sổ chuyển đổi/rollback.

### Bài 16 — Read replica

Write trên primary rồi đọc ngay từ replica thấy dữ liệu cũ.

**Đáp án:** Có thể là replication lag; routing và consistency policy phải nêu rõ.

### Bài 17 — Multi-PU transaction

Service dùng ordersPU và analyticsPU, mỗi PU RESOURCE_LOCAL rồi muốn commit nguyên tử.

**Đáp án:** Không tự có atomic distributed transaction. Thiết kế JTA/XA hoặc outbox/saga tùy requirement.

### Bài 18 — Misrouted tenant

Tenant-A query chạy trên connection có schema context tenant-B.

**Đáp án:** Cần trusted tenant resolver và reset/scope pooled connection state; test cross-tenant isolation.

### Bài 19 — Config precedence

`application-prod.yml` có `ddl-auto=none` nhưng runtime env override thành `update`.

**Đáp án:** Effective configuration mới là nguồn thực tế; cần guardrails/validation và quyền DDL hạn chế.

### Bài 20 — Rollback schema

Một migration đã drop cột, team muốn rollback application cũ.

**Đáp án:** Có thể không rollback được nếu app cũ cần cột đó. Thiết kế backward-compatible expand/contract trước.

### Bài 21 — Provider upgrade

Nâng Hibernate major và thấy sequence IDs khác kỳ vọng.

**Gợi ý:** So sánh ID generators, schema sequence allocation, SQL behavior, provider docs và integration tests trên DBMS đích.

### Bài 22 — Migration from empty only

New schema migration pass trên database trắng nhưng production có dữ liệu cũ.

**Đáp án:** Thêm migration upgrade test với historical fixtures và backfill.

### Bài 23 — Health check

Service restart liên tục vì database outage tạm thời nhưng process vẫn khỏe.

**Gợi ý:** Tách readiness DB-dependent và liveness process-dependent theo deployment policy.

### Bài 24 — Staging data

Team clone production DB đầy PII vào staging container local.

**Đáp án:** Không nên. Dùng synthetic/anonymized fixtures và access/retention controls.

### Bài 25 — Multi-environment artifact

Team build riêng source code chỉ để thay JDBC URL.

**Gợi ý:** Giữ artifact giống nhau, inject URL/secret từ deployment; chỉ khác build khi thực sự cần platform-specific artifact.

## 42. Câu hỏi tự kiểm tra

**1. Persistence unit chứa những loại cấu hình nào?**

Tập entities/mappings, provider, transaction type, dữ liệu kết nối và JPA/provider properties.

**2. Tên persistence unit có cần mang tên môi trường không?**

Không bắt buộc; một logical name ổn định thường dễ vận hành hơn.

**3. Tại sao không để password production trong persistence.xml?**

Vì file thường được đóng gói và version control, dễ làm lộ secret.

**4. API Java SE để bootstrap PU là gì?**

`Persistence.createEntityManagerFactory(...)`.

**5. Có thể override JDBC properties lúc bootstrap không?**

Có thể dùng map properties tương ứng với Java SE bootstrap; behavior tổng thể cần đối chiếu runtime/provider.

**6. RESOURCE_LOCAL khác JTA?**

RESOURCE_LOCAL dùng application-managed `EntityTransaction`; JTA dùng transaction manager/container coordination.

**7. @Transactional của Spring có chắc là JTA không?**

Không.

**8. JTA DataSource khác non-JTA DataSource?**

Khác về enlistment/transaction integration theo runtime.

**9. Một EntityManagerFactory có nên tạo theo mỗi request?**

Thường không; tạo một lần theo application lifecycle.

**10. EntityManager có thread-safe để chia sẻ singleton không?**

Không nên chia sẻ nó đồng thời như một singleton.

**11. Những cấu hình nào phải khác theo môi trường?**

Ít nhất connection endpoint, credentials/identity, secrets, pool/caching/logging strategy khi cần.

**12. Những cấu hình nào nên ổn định theo release?**

Entity mapping, provider version, schema contract, ID strategy và những settings ảnh hưởng correctness.

**13. Migrations khác schema generation?**

Migrations quản lý thay đổi schema có version và rollout; schema generation không thay thế toàn bộ quy trình này.

**14. Production có nên dùng drop-and-create?**

Không trên DB có dữ liệu cần giữ; đó là destructive schema action.

**15. Hibernate ddl-auto=validate có thuộc Jakarta Persistence chuẩn không?**

Không.

**16. Hibernate jdbc.batch_size có thuộc JPA chuẩn không?**

Không.

**17. Spring datasource.url có thuộc JPA chuẩn không?**

Không, nó là Spring property.

**18. Vì sao effective config quan trọng hơn chỉ đọc YAML?**

Vì env, CLI, config server hoặc framework precedence có thể override.

**19. Vì sao không đặt production URL làm default fallback?**

Vì thiếu biến có thể vô tình kết nối production.

**20. Vì sao runtime account không nên có DDL privileges?**

Để hạn chế tác động của config bug/compromise và tách migration trách nhiệm.

**21. Flyway/Liquibase có thuộc JPA API không?**

Không.

**22. Staging có thể thay thế hoàn toàn production tests không?**

Không nếu data volume, topology, config hoặc traffic khác.

**23. Vì sao cần Testcontainers?**

Để kiểm tra JPA trên DBMS engine thật trong môi trường test cô lập.

**24. L1 và L2 cache ảnh hưởng test thế nào?**

Có thể che SQL reads và thay result/latency; phải kiểm soát khi cần.

**25. Pool max-size chọn theo gì?**

Workload, số instances, DB connection limits và performance measurements.

**26. Vì sao SQL bind TRACE nguy hiểm trên production?**

Có thể log PII/secrets và tạo overhead.

**27. Multi-PU có tự chia sẻ transaction atomic không?**

Không.

**28. Hibernate physical naming strategy đổi theo profile có rủi ro gì?**

Có thể sinh mapping SQL khác nhau giữa environments.

**29. Read replica có luôn thấy thay đổi vừa commit không?**

Không nếu replication asynchronous gây lag.

**30. Vì sao migration phải backward-compatible khi rolling deploy?**

Vì app cũ và mới có thể chạy song song trong thời gian chuyển đổi.

**31. Rollback app có tự rollback DDL không?**

Không.

**32. RLS tenant context có thể leak như thế nào?**

Session variable/schema context còn trên pooled connection nếu không reset/scope đúng.

**33. Test với runtime-like role có ích gì?**

Phát hiện thiếu grants hoặc RLS bypass khác với prod behavior.

**34. Khi startup database schema không khớp, nên bật Hibernate update để sửa không?**

Không theo quy trình migration production; tìm nguyên nhân và dùng migration/config fix.

**35. Nguyên tắc cốt lõi của quản lý PU giữa môi trường?**

Giữ một contract rõ, inject cấu hình theo môi trường, bảo vệ secrets, cấm DDL ngoài ý muốn, test effective runtime và quản lý schema bằng migrations có kiểm soát.

## 43. Kịch bản tổng hợp: triển khai orders-service từ local lên production

Giả sử ứng dụng Orders dùng Hibernate/JPA và PostgreSQL. Team có môi trường dev, CI, staging và production.

### 43.1. Giai đoạn local

Developer chạy PostgreSQL local hoặc container disposable.

```text
ordersPU
  ->
ORDERS_DB_URL=jdbc:postgresql://localhost:5432/orders_dev
  ->
Developer database
```

Các entity và migrations giống repository. Developer có thể bật SQL DEBUG trên synthetic data, pool nhỏ. Không nhúng production secrets.

### 43.2. Giai đoạn CI

Pipeline:

```text
Compile
   |
   v
Start PostgreSQL Testcontainers
   |
   v
Run Flyway/Liquibase migrations
   |
   v
Create ordersPU
   |
   v
JPA mapping + FK/UNIQUE/transaction tests
   |
   v
Migration upgrade fixtures tests
   |
   v
Build immutable artifact
```

CI phải kết nối DB container thông qua mapped URL, không phụ thuộc database máy người chạy.

### 43.3. Giai đoạn staging

Deploy immutable artifact với staging DB URL/credentials. Kiểm tra:

- Migration version.
- Provider/driver version.
- Transaction mode.
- Pool.
- RLS/tenant isolation nếu dùng.
- Các endpoint quan trọng.
- Rollout/rollback compatibility.
- Error handling và metrics.

### 43.4. Giai đoạn production

Migration job dùng privileged role chạy reviewed migrations trước rollout. Application role có quyền thấp, DDL off, startup validation kiểm tra schema/version rồi nhận traffic.

### 43.5. Giả sử production lỗi vì thiếu sequence

Startup/first persist báo:

```text
relation "product_id_seq" does not exist
```

Team cần xác minh:

1. Đúng production database/schema chưa?
2. `@SequenceGenerator(sequenceName="...")` khớp migration không?
3. Migration đã chạy chưa?
4. Runtime role có quyền dùng sequence không?
5. Schema search_path có đổi không?
6. Có bị config override hay provider upgrade tác động không?

**Không** đổi `ddl-auto=update` để ORM tự tạo sequence mà bỏ qua migration history.

### 43.6. Sau khi sửa

Thêm integration test migrations + ID generation và preflight check liên quan. Release tiếp theo sẽ không chỉ “chạy được trên local”, mà có bằng chứng contract trên DBMS đích.

## 44. Quy tắc thực hành cuối bài

1. **Dùng logical persistence unit name ổn định** nếu khác biệt môi trường chỉ là connection/runtime config.
2. **Phân biệt JPA standard properties, provider extensions và framework properties.**
3. **Tách secrets/DB endpoints khỏi source và build artifact.**
4. **Fail fast khi production config bắt buộc thiếu**, không fallback nguy hiểm.
5. **Chọn đúng RESOURCE_LOCAL hoặc JTA**, không trộn transaction APIs tùy tiện.
6. **Quản lý EntityManagerFactory/EntityManager lifecycle** theo runtime.
7. **Một chủ thể quản lý schema production**, ưu tiên versioned migrations.
8. **Tắt schema generation/destructive updates ở runtime production** và dùng role không có quyền DDL cần thiết.
9. **Chạy migrations và JPA tests trên DBMS thật** khi cần hành vi tương đương.
10. **Kiểm soát cache, dialect, naming strategy, ID generation** để tránh drift.
11. **Tính pool size theo toàn bộ instances và DB capacity**, không chỉ một JVM.
12. **Không bật raw SQL bind logging không kiểm soát** trên dữ liệu nhạy cảm.
13. **Xác nhận effective configuration và DB identity lúc khởi động** bằng diagnostics đã redacted.
14. **Thiết kế schema migration expand-and-contract** nếu old/new app versions cùng chạy.
15. **Rollback code không thay thế rollback schema plan.**
16. **Tách migration role và runtime role**, secrets và network theo môi trường.
17. **Kiểm thử multi-PU và multi-tenant routing** thay vì mặc định transaction/cache isolation đúng.
18. **Tách readiness khỏi liveness** và có error categorization cho connection/schema failures.
19. **Theo dõi regressions sau khi đổi provider/version hoặc tuning config.**
20. **Mọi thay đổi config quan trọng cần review, test, rollout và rollback plan.**

## 45. Kết luận

Quản lý cấu hình persistence unit giữa các môi trường không phải chỉ là thay `jdbc.url` từ localhost thành production hostname. Nó là quá trình duy trì **một hợp đồng persistence nhất quán** trong khi chủ động điều chỉnh connection, identity, transaction model, schema ownership, cache, performance tuning và observability cho từng môi trường.

Một thiết kế có thể vận hành tin cậy thường có những tính chất sau:

- Source và artifact không chứa production secrets.
- Tên PU, entity mappings và schema contract nhất quán.
- JDBC endpoints, users và secrets được cấp từ deployment.
- RESOURCE_LOCAL/JTA transactions phù hợp runtime, không lẫn semantics.
- Runtime production không tự sinh/sửa/drop schema; migration pipeline có quyền và lịch sử riêng.
- Test dùng DBMS đích khi cần xác nhận dialect, type, FK/UNIQUE, sequence, transaction và native SQL.
- Staging/production khác nhau có lý do rõ; effective config được xác nhận thay vì chỉ tin file YAML.
- Rolling deploy có compatibility window và hướng rollback ứng dụng an toàn.
- Connection pools, cache, SQL logs và provider-specific settings có baseline, kiểm soát và monitoring.
- Multi-PU/multi-tenant flows có test để tránh kết nối nhầm hoặc truy xuất sai dữ liệu.

Mục tiêu cuối cùng là để **cùng một ứng dụng JPA có thể được triển khai và di trú có kiểm soát**: mỗi môi trường nhận đúng database và quyền hạn, cùng tuân thủ schema contract, thất bại rõ khi cấu hình sai và không đặt dữ liệu đang vận hành vào rủi ro chỉ vì một property vô tình thay đổi.
