# Phân biệt container dùng chung với dữ liệu dùng chung

Một nhóm kiểm thử Spring Boot muốn suite chạy nhanh hơn nên sử dụng **một PostgreSQL Testcontainer cho nhiều test methods hoặc test classes**. Quyết định đó có thể hợp lý: khởi động database thường tốn thời gian, còn JUnit và Spring TestContext có cơ chế tái sử dụng tài nguyên. Tuy nhiên, sau khi chia sẻ container, một test `findAll()` bắt đầu trả hai bản ghi thay vì một, một test duplicate-key thất bại vì bản ghi cũ, hoặc một test chạy song song xóa data của test kia.

**Nguyên nhân cốt lõi:** *container dùng chung* là quyết định về **vòng đời hạ tầng**; *dữ liệu dùng chung* là quyết định về **trạng thái và quyền sở hữu dữ liệu**. Hai việc này không đồng nghĩa. Bạn có thể dùng chung một container PostgreSQL, Kafka hoặc Redis mà mọi test vẫn có dữ liệu độc lập, miễn thiết kế database/schema/namespace, fixture, transaction và cleanup đúng. Ngược lại, mỗi test có một object Java mới hoặc một Spring `ApplicationContext` mới chưa chắc dữ liệu external cũng đã sạch.

Bài Knowledge này thuộc nhóm **Testcontainers** của module **Spring Boot – testing**. Ví dụ thực hành dùng **Java 17+, Spring Boot 3.5.x, Testcontainers 1.21.x, JUnit Jupiter 5, Spring JDBC và PostgreSQL 16**. Nó cố ý cho **hai test classes dùng cùng một cấu hình container bean** nhưng không dựa vào dữ liệu của nhau: mỗi method sinh `owner_token` riêng, mọi query đều lọc đúng owner, và cleanup chỉ xóa rows mà method sở hữu.

> **Quy tắc cần nhớ:** **Chia sẻ tài nguyên hạ tầng để giảm chi phí; cô lập trạng thái thử nghiệm để giữ ý nghĩa assertion.** Khi test đỏ, phải biết đó là lỗi code được kiểm hay dữ liệu rò từ test khác.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Định nghĩa chính xác “chia sẻ container”, “chia sẻ database”, “chia sẻ schema”, “chia sẻ collection/topic/index”, “chia sẻ dữ liệu” và “chia sẻ Spring context”.
- Phân biệt `@Container static`, `@Container` instance, Spring-managed container bean, singleton container và reusable container experimental.
- Hiểu **container còn sống không đồng nghĩa dữ liệu đã reset**; context cache không phải công cụ reset database.
- Chọn mức cô lập **per row/owner, per schema, per database, per container** theo mức rủi ro.
- Viết test JDBC trên PostgreSQL Testcontainer dùng `owner_token` và composite unique constraint.
- Tạo fixture độc lập cho từng test, assert qua owner-filtered queries, cleanup có kiểm chứng.
- Giải thích tại sao `TRUNCATE`, `DROP SCHEMA`, `FLUSHDB` và xóa toàn topic/index có thể phá test khác khi hạ tầng được chia sẻ.
- Biết lúc nào `@Transactional` rollback giúp cô lập và khi nào nó **không rollback** write từ HTTP server thread hoặc hệ thống ngoài transaction.
- Nhận diện lỗi Spring context cache kết nối tới static Testcontainer đã bị JUnit stop.
- Thiết kế parallel-test strategy, resource locks, Docker/CI isolation và cleanup khi test bị crash.
- Dùng một ma trận để cân bằng startup time, test fidelity, risk, parallelism và độ dễ debug.

## 2. Hai câu hỏi cần tách biệt ngay từ đầu

**Câu hỏi A — Hạ tầng được quản lý và tái sử dụng thế nào?**

- Ai khởi động container: JUnit extension, Spring bean, singleton manual hay infrastructure dùng chung?
- Nó được start/stop khi nào: mỗi method, mỗi class, mỗi `ApplicationContext`, mỗi JVM, mỗi job CI?
- Ai lấy host/port/credentials: `@ServiceConnection`, `@DynamicPropertySource` hoặc manual JDBC URL?
- Một hay nhiều test classes cùng kết nối tới service instance đó?

**Câu hỏi B — Trạng thái từng test được bảo vệ thế nào?**

- Rows/keys/documents/topics nào thuộc một test cụ thể?
- Test có query toàn bảng/collection/keyspace hay luôn lọc đúng namespace không?
- Fixture có xung đột `UNIQUE`, idempotency key, consumer group, offset hay cache key không?
- Khi test fail/timeout hoặc chạy parallel, dữ liệu sẽ được cleanup ra sao?
- Có tác dụng phụ bất đồng bộ chạy sau khi method đã kết thúc không?

Câu hỏi A chủ yếu thuộc **lifecycle/performance**; câu hỏi B thuộc **correctness/isolation**. Một trả lời tốt cho A không tự giải quyết B.

## 3. Mô hình các lớp “dùng chung”

```text
JVM / Gradle test worker process
  |
  +-- Spring TestContext cache
  |     +-- ApplicationContext A
  |     |     +-- DataSource / connection pool
  |     |     +-- Spring-managed PostgreSQLContainer
  |     +-- ApplicationContext B (có thể riêng nếu config khác)
  |
  +-- Test class A
  |     +-- method A1: owner_token = run-A1
  |     +-- method A2: owner_token = run-A2
  |
  +-- Test class B
        +-- method B1: owner_token = run-B1

Docker daemon
  |
  +-- PostgreSQL container (một process DB)
        +-- database test_db
              +-- schema public
                    +-- table ledger_entries
                          +-- rows của run-A1
                          +-- rows của run-A2
                          +-- rows của run-B1

Một PostgreSQL process có thể chứa nhiều nhóm dữ liệu độc lập.
```

Trong sơ đồ, hai test classes *có thể* chia sẻ `ApplicationContext` và container nếu Spring TestContext cache nhận chúng là cùng configuration. Nhưng **không dựa vào cùng container ID/host port như assertion về dữ liệu**. Nếu hai classes tạo hai contexts khác nhau, mỗi context có thể có container riêng; thiết kế data isolation vẫn đúng.

### 3.1. Bảng những thứ dễ bị gọi nhầm là “shared”

| Thứ được chia sẻ | Điều thực sự dùng chung | Điều **không** tự xảy ra |
|---|---|---|
| Docker image cache | Image layers trên host | Không chia sẻ dữ liệu của running containers |
| Docker daemon | API/runtime tạo containers | Không có nghĩa mọi test dùng cùng một service instance |
| Một container | Process và storage của service bên trong | Không có nghĩa mọi test cùng một fixture/owner |
| Một database trong container | Tables, schemas, transactions | Không tự lọc queries theo test |
| Một Spring `ApplicationContext` | Beans/cache/connection pool | Không reset database giữa methods |
| Một Java test class instance | Fields trong instance | Không cô lập external state |
| Một JUnit static field | Reference trong JVM | Không tự reset rows/keys |
| Một Redis instance | Keyspace và TTL | Không ngăn keys của hai tests collision |
| Một Kafka broker | Topics/partitions/offset storage | Không ngăn consumer groups dùng chung |
| Một reusable container | Process giữa nhiều test runs | Không xóa dữ liệu giữa những lần chạy |

## 4. Ví dụ contamination: một container, hai test cùng đụng data

Test A:

```java
// PHẢN VÍ DỤ: data được ghi, không có scope và cleanup.
jdbc.update(
        "INSERT INTO accounts(external_id, balance) VALUES (?, ?)",
        "CUST-001", 100);
```

Test B:

```java
// PHẢN VÍ DỤ: giả định database luôn trống.
assertEquals(0L, jdbc.queryForObject(
        "SELECT COUNT(*) FROM accounts", Long.class));
```

Nếu A và B dùng một PostgreSQL container với database giống nhau, B phụ thuộc thứ tự chạy. Nếu cùng `external_id`, database UNIQUE constraint có thể báo duplicate-key. Nếu A/B chạy song song, một cleanup toàn bảng có thể xóa row ngay trước assertion của method kia.

**Không sửa bằng `@TestMethodOrder`** để “B luôn chạy trước A”. Test order không phải data isolation. Một bài test mạnh phải thể hiện:

- Dữ liệu của chính nó.
- Trạng thái khởi đầu của phạm vi đó.
- Query theo phạm vi đó.
- Hậu điều kiện và cleanup của phạm vi đó.
- Thất bại rõ khi DB/code phá invariant.

## 5. JUnit `@Container` static: dùng chung **trong một test class**

Với Testcontainers **1.x**, JUnit 5 extension hoạt động như sau:

```java
@Testcontainers
class OrderJdbcTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void first() { /* ... */ }

    @Test
    void second() { /* ... */ }
}
```

Đây là snippet, không phải file runnable đầy đủ.

- `@Testcontainers` kích hoạt Jupiter extension.
- Static `@Container` được start trước các methods và stop sau class.
- Hai methods có thể truy cập **cùng instance PostgreSQL đang chạy**.
- **Rows, sequences, tables và cached database state không tự reset** giữa methods.
- Nếu A insert rồi commit, B có thể nhìn thấy row ấy cho đến khi bị xóa.
- JUnit tạo test object mới cho mỗi method theo mặc định **không làm database mới**.

**Bẫy:** `@Testcontainers` extension theo tài liệu chỉ được kiểm thử với test execution tuần tự; chạy parallel theo phương thức này không được bảo đảm và có thể có side effects bất ngờ. Nếu muốn parallel, phải thiết kế lifecycle/isolation riêng và đánh giá đầy đủ.

## 6. JUnit `@Container` instance: chi phí khác, vẫn phải hiểu DB

Với field **không static**:

```java
@Testcontainers
class ExpensivePerMethodTest {

    @Container
    final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void first() { /* ... */ }

    @Test
    void second() { /* ... */ }
}
```

Trong JUnit Jupiter test-instance lifecycle mặc định là `PER_METHOD`, extension khởi động/dừng container quanh từng method. Điều này thường giúp cô lập storage do mỗi method có container mới, nhưng:

- Startup chậm hơn rõ so với static container.
- Nếu test class dùng `@TestInstance(PER_CLASS)` hoặc lifecycle custom, phải xem extension behavior tương ứng.
- Một Spring context cache có thể giữ DataSource tới container đã stop nếu cấu hình không khớp.
- Container-per-method không bảo vệ những side effects **ngoài** container đó, như HTTP sandbox, filesystem hoặc shared bucket.
- Nếu bật reusable containers experimental, “stop” semantics có thể khác với container ephemeral.

**Không chọn instance container chỉ vì nghĩ “an toàn tuyệt đối”.** Nó là một lựa chọn isolation có chi phí, còn data ownership vẫn cần được hiểu.

## 7. Spring-managed container bean và context cache

Spring Boot 3.5 cho phép:

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Snippet trên cần imports `TestConfiguration`, `Bean`, `ServiceConnection` và `PostgreSQLContainer`. Khi container được quản lý như **Spring bean**, Boot start container trước các dependent beans và stop sau khi context teardown, nên lifecycle khớp với các connection pool/DataSource cần service này.

**Quan trọng:**

1. Bean được tạo một lần cho mỗi `ApplicationContext` tương ứng, không nhất thiết một lần cho cả JVM.
2. Spring TestContext **có cache** context; nhiều test classes cùng configuration key có thể reuse nó.
3. Nếu reuse context, container cũng được giữ sống cùng context.
4. Context cache không gọi `DELETE FROM` hay reset business fixtures giữa test methods.
5. Nếu context khác vì profile/properties/bean overrides, có thể có một container khác.

Đó là lựa chọn **lifecycle**, không phải chiến lược **data isolation**. Ta vẫn cần row/schema/database scopes hoặc cleanup.

### 7.1. `@ServiceConnection` có làm data sạch không?

Không. Nó cấp `JdbcConnectionDetails`/connection info cho Spring auto-configuration; nó không xóa rows. Với PostgreSQL typed container, Boot nhận ra service và kết nối qua host/port động. Nếu chọn `@DynamicPropertySource` thay thế, bạn phải tự đăng ký JDBC URL/user/password và bảo đảm container đã start; cơ chế này cũng không reset dữ liệu.

### 7.2. Lỗi static container + cached context

Một test class A dùng static `@Container`; JUnit stop container sau class A. Nhưng Spring `ApplicationContext` có thể vẫn nằm trong cache và được class B với cùng context config reuse. DataSource còn trỏ tới port của container đã stop; B gặp `Connection refused`. Đây là **lỗi lifecycle**, không phải data contamination. Spring Boot khuyến nghị container beans hoặc `@ImportTestcontainers` khi lifecycle cần đi cùng cached context.

## 8. Singleton container và reusable container: hai khái niệm khác

### 8.1. Singleton trong một JVM

Một base class có static field, khởi động container thủ công một lần rồi chia sẻ qua các subclasses:

```java
// Snippet không được đặt @Container và dùng JUnit extension
// nếu muốn tự quản lý singleton lifecycle.
abstract class SharedPostgresBase {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }
}
```

Pattern này có thể giảm số lần startup giữa test classes, nhưng yêu cầu quản lý lifecycle, data isolation và context cache cẩn thận. **Không đồng thời gắn `@Container`/`@Testcontainers` lên singleton manual**: JUnit extension có thể stop nó khi class đầu kết thúc.

### 8.2. Reusable container qua nhiều lần chạy test

Testcontainers có tính năng experimental `withReuse(true)`, opt-in bằng config riêng. Container có thể còn chạy giữa **nhiều JVM/test executions** thay vì bị dừng sau suite.

Điều này khác hoàn toàn với static `@Container` hoặc Spring context caching.

| Loại reuse | Phạm vi điển hình | Có giữ dữ liệu sang lần chạy sau? |
|---|---|---|
| Static `@Container` | Các methods trong cùng class | Trong lúc container còn sống |
| Spring bean container | Các tests dùng cùng cached context | Trong lúc cached context/container còn sống |
| Manual singleton | Nhiều classes trong một JVM | Trong lifecycle singleton |
| `withReuse(true)` experimental | Có thể qua nhiều process/test runs | **Có thể**, cần reset có chủ đích |
| Image layer cache | Nhiều image pulls/startups | Không phải dữ liệu runtime của container |

Tài liệu Testcontainers nêu reusable containers **không phù hợp cho CI**; có hạn chế cleanup/networking. Không bật tính năng experimental này như giải pháp chung để làm CI nhanh hơn. Nếu local development cho phép dùng reuse, hãy coi data cũ là khả năng thật, áp dụng namespace/reset và không đưa credential production vào container reusable.

## 9. Container dùng chung không phải một tập dữ liệu dùng chung

Có nhiều chiến lược cô lập một container:

```text
PostgreSQL container A
  ├── database class_one
  │     └── schema public
  │           └── rows của test group one
  ├── database class_two
  │     └── schema public
  │           └── rows của test group two
  └── database shared_test_db
        ├── schema it_a (test class A)
        ├── schema it_b (test class B)
        └── schema public
              └── ledger_entries
                    ├── owner_token a-...
                    └── owner_token b-...
```

Cùng container process nhưng **có thể tách database, schema hoặc rows**. Không nhất thiết phải chọn một strategy cho cả repository:

- Repository tests thường có thể dùng transaction rollback hoặc row-level data scope.
- Migration tests cần database/schema mới để bảo vệ DDL.
- Concurrency/locking tests đôi khi **cố ý** dùng chung table để thực sự quan sát tranh chấp.
- Tenant-isolation tests cần nhiều tenant trong cùng backend nhưng asserts phải phân biệt tenant.
- Chaos/restart tests có thể cần container độc lập để không làm rơi kết nối của suite khác.

## 10. Bốn mức cô lập dữ liệu trên một backend

| Mức | Ví dụ | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Per-row/test owner** | `owner_token`/`test_run_id` trong mỗi row | Rẻ, hỗ trợ nhiều tests trong một DB | Mọi read/write phải có scope; global DDL/truncate vẫn nguy hiểm |
| **Per-schema** | `it_a.ledger_entries`, `it_b.ledger_entries` | Tách tables/sequences và nhiều schema objects | Config `search_path`, migrations, permissions, connection pool phức tạp |
| **Per-database** | `db_test_a`, `db_test_b` trong một Postgres container | Tách catalog/schema/users rõ hơn | Cần tạo DB, migrations, DataSource riêng; vẫn share CPU/process |
| **Per-container** | Mỗi class/method có PostgreSQLContainer riêng | Cô lập service process/storage tốt nhất | Startup/RAM/disk/CI cost cao hơn |

Không có mức tối ưu tuyệt đối. **Dùng mức rẻ nhất vẫn phát hiện đúng rủi ro**, nhưng không đánh đổi tính xác định để giảm vài giây startup.

### 10.1. Khi chỉ dùng row-level scope

Phù hợp khi:

- Tables/migrations giống nhau cho mọi test.
- Business queries có tenant/owner key rõ ràng.
- Không test destructive schema changes.
- Có thể xóa chính các rows đã tạo.
- Không có task background không lọc owner.
- Tests không cần một database hoàn toàn trống ở mức global.

**Không phù hợp** nếu test cố tình tạo/drop table, đổi indexes/roles/schema hoặc chạy migration destructive; những thao tác đó tác động toàn schema, không thể cô lập bằng `owner_token`.

## 11. Row-level scope: phải lọc ở cả đọc, ghi và cleanup

Đặt mỗi test method có token:

```java
String owner = "it-" + UUID.randomUUID();
```

Rồi repository:

```sql
INSERT INTO ledger_entries(owner_token, business_key, amount_minor)
VALUES (?, ?, ?);

SELECT COUNT(*) FROM ledger_entries
WHERE owner_token = ?;

DELETE FROM ledger_entries
WHERE owner_token = ?;
```

**Vì sao không chỉ dùng random ID?** Một test vẫn có thể gọi `SELECT COUNT(*) FROM ledger_entries` hoặc `findAll()` rồi kỳ vọng 1. Random primary key ngăn trùng ID, **không loại bỏ dữ liệu khác khỏi query toàn bảng**.

Một repository multi-tenant production cần enforce tenancy tại boundary thật, không chỉ trong test helpers. Ví dụ demo chủ đích nhận `owner_token` như một parameter để dễ quan sát. Nếu app production nhận tenant ID từ JWT/identity, phải test injection/authorization và tránh để client truyền token tùy ý nhằm truy cập dữ liệu tenant khác.

### 11.1. Composite uniqueness

Thay vì `UNIQUE(business_key)` trên toàn bảng, nếu nghiệp vụ cho phép cùng key ở các tenant độc lập:

```sql
CONSTRAINT uq_owner_business UNIQUE (owner_token, business_key)
```

Cùng `ORDER-1` của hai test/tenant khác nhau không xung đột. Tuy nhiên, **không sửa unique constraint production chỉ để test dễ hơn**. Nếu business key phải global unique, test nên sinh key riêng cho từng method hoặc dùng DB/schema isolation.

### 11.2. Token phải là dữ liệu thử nghiệm, không phải security boundary

`owner_token` là phương tiện gán ownership cho fixture. Nó không thay authentication hoặc Row-Level Security của PostgreSQL. Một SQL sai thiếu `WHERE` vẫn có thể đọc data khác; việc test pass vì đúng owner token không tự chứng minh authorization trên API production.

## 12. Per-schema isolation trên PostgreSQL

Có thể tạo schema mới:

```sql
CREATE SCHEMA it_run_a;
CREATE TABLE it_run_a.ledger_entries (...);
```

và để connection/test context dùng đúng `search_path`, Hibernate `default_schema` hoặc fully qualified table name.

**Nhưng:**

- DataSource connection pool có thể reuse sessions; thay `SET search_path` thủ công trong một test rồi không reset có thể rò schema sang test khác.
- Spring Boot `spring.sql.init.*`, Flyway/Liquibase và JPA defaults cần được trỏ đúng schema.
- Foreign keys, sequences, extensions và DB roles có thể nằm ở schema khác, không tự copy.
- `DROP SCHEMA ... CASCADE` là destructive operation; chỉ dùng schema do test sở hữu, sau khi đóng connections/jobs còn tham chiếu.

Một chiến lược ổn định là tạo **schema per test class/run trước khi xây context** và cấu hình connection initialization, rồi drop schema sau khi không còn active users. Không dùng chung một DataSource mà mỗi method đổi search_path trên connection pool toàn cục nếu không có kiểm soát mạnh.

## 13. Per-database isolation trong cùng một container

PostgreSQL process có thể phục vụ nhiều databases:

```sql
CREATE DATABASE it_run_a;
CREATE DATABASE it_run_b;
```

Mỗi database có catalog/schema/tables độc lập. Nhưng việc tạo database phải thực hiện trên connection administrative/test-only, không thể làm trong một transaction thông thường của PostgreSQL, và cần quyền phù hợp. Spring Boot DataSource phải trỏ vào đúng DB trước khi auto-config/migration chạy.

**Ưu điểm:** hai test classes có thể dùng cùng Postgres container nhưng mỗi class có DB riêng và schema migrations độc lập. **Chi phí:** tạo DB, migrate và quản lý connection pools; Postgres process/RAM/CPU vẫn shared.

Với Testcontainers `PostgreSQLContainer.withDatabaseName("name")`, thông thường bạn đang cấu hình **một database cho container đó**. Không nhầm rằng gọi `withDatabaseName` khác nhau trên cùng Java object sau start sẽ tự tạo database thứ hai. Muốn nhiều databases trong cùng container, cần setup SQL/cấu hình riêng một cách có chủ đích.

## 14. Per-container isolation: khi nào đáng chi phí?

Container riêng phù hợp cho:

- Tests thay đổi database roles/cluster config/extensions.
- Destructive migrations.
- Database restart/failure injection.
- Replication/network partition scenarios.
- Tests có global state khó scoped cleanup.
- Cần PostgreSQL versions khác nhau hoặc driver behavior khác nhau.
- Không thể đảm bảo shared backend có dữ liệu xác định.

Dùng container per **class** khi một class có nhiều methods cùng engine/version nhưng có cleanup độc lập. Dùng container per **method** khi mỗi method thực sự cần process/storage mới. **Không nên dùng container per method cho 100 bài test chỉ kiểm nghiệp vụ Java thuần**, vì suite sẽ rất chậm.

### 14.1. Một số dữ liệu sống ngoài PostgreSQL

Nếu service vừa ghi PostgreSQL vừa lưu Redis key hoặc publish Kafka event, container PostgreSQL riêng **không reset Redis/Kafka**. Tài nguyên cần isolation theo từng backend liên quan. “Mỗi test có Postgres container mới” không đồng nghĩa một end-to-end environment hoàn toàn mới.

## 15. Reset bằng `DELETE`, `TRUNCATE`, transaction rollback hay migrate?

| Cách | Cái được reset | Ưu điểm | Nguy cơ trong shared container |
|---|---|---|---|
| `DELETE ... WHERE owner_token=?` | Rows đúng owner | An toàn cho tests khác, dễ đọc | Cần track mọi bảng/foreign keys liên quan |
| `DELETE FROM table` | Mọi rows của table | Dễ trong DB dành riêng | Xóa data của test khác |
| `TRUNCATE table` | Toàn table, có thể reset identity | Nhanh cho dedicated DB | Phá concurrent tests; lock/schema effects |
| `@Transactional` JUnit rollback | Writes trong test-managed transaction | Nhanh với repository tests | Không bao cả HTTP/async/other services |
| `@Sql` setup/cleanup | Dữ liệu theo script | Rõ fixture | Script broad hoặc transaction phase sai |
| `DROP SCHEMA/DATABASE` | Schema/DB + metadata | Reset sâu | Chỉ an toàn với namespace riêng |
| Fresh container | Toàn service storage | Fidelity/isolation mạnh | Startup/resource cost |
| New random key/namespace | Các objects của test | Cho phép parallel tốt hơn | Orphans khi test bị kill nếu không teardown |

**Không chọn `TRUNCATE ... RESTART IDENTITY CASCADE` chỉ vì test cần count=0.** Nó thay đổi nhiều đối tượng, có thể chặn hoặc xóa dữ liệu thuộc test khác trong shared database. Nếu database chỉ thuộc class/run và không có concurrent user, TRUNCATE có thể hợp lý nhưng phải có policy xác nhận ownership.

## 16. `@Transactional` có giúp dữ liệu tự sạch không?

Spring TestContext mặc định rollback một test method có test-managed `@Transactional` sau khi method hoàn thành, khi transaction manager phù hợp tồn tại.

Ví dụ:

```java
// Snippet: test JDBC chạy trong cùng test-managed transaction.
@Test
@Transactional
void repositoryWritesAreRolledBack() {
    repository.insert(...);
    assertEquals(1L, repository.count(...));
}
```

**Giới hạn rất quan trọng:**

1. Test-managed rollback không dọn dữ liệu do setup ngoài transaction hoặc background task khác commit.
2. Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP request được xử lý ở thread/transaction của server; transaction của JUnit client **không tự rollback** các writes server thực hiện.
3. Code dùng `REQUIRES_NEW` có thể commit riêng; test transaction không rollback transaction đó nếu nó thực sự commit.
4. Redis, Kafka, HTTP gateway, filesystem và email không tự tham gia JDBC transaction.
5. Sequence/identity có thể tăng dù insert rollback; không assert ID liên tục.
6. Test methods chỉ assert “DB trống sau test” không chứng minh service có `@Transactional` đúng: có thể là chính JUnit test đã rollback.

**Chọn rollback khi nó đúng ranh giới**, và chọn cleanup/namespace khi nó không đủ.

## 17. Spring `@DirtiesContext` không phải data reset chung

`@DirtiesContext` đánh dấu `ApplicationContext` không còn dùng để cache, dẫn tới teardown/rebuild khi phù hợp. Nó hữu ích nếu chính **context/beans** đã bị thay đổi không thể reset an toàn, nhưng không phải lệnh xóa database.

- Nếu PostgreSQL container là Spring bean và context bị đóng, container đó thường được stop; dữ liệu của container ephemeral có thể biến mất theo lifecycle.
- Nếu DB nằm trên một external instance, singleton manual hoặc reusable container, `@DirtiesContext` **không** xóa rows.
- Nếu bean container khác context vẫn đang được dùng, teardown có thể ảnh hưởng test đang chạy.
- Rebuild context liên tục tăng startup time và có thể che lỗi cleanup.

**Hỏi đúng:** Điều gì bị bẩn — Spring beans, database rows, static Java state hay container process? Reset đúng thứ đó, không gắn `@DirtiesContext` trên mọi test để hy vọng.

## 18. Parallel tests: isolation không tự xuất hiện nhờ UUID

Dùng `UUID.randomUUID()` làm owner giúp tránh collision, nhưng vẫn có những operations toàn cục:

- `DELETE FROM ledger_entries` không `WHERE`.
- `TRUNCATE ledger_entries` hoặc `DROP TABLE`.
- Index creation/drop, schema migration, role changes.
- Kafka topic delete, Redis `FLUSHDB`, Elasticsearch index delete.
- Cùng filesystem path hoặc shared test clock/static singleton.
- Background consumer/job không lọc owner.
- `@DirtiesContext` đóng context khi test khác còn sử dụng.

Spring TestContext có hướng dẫn thận trọng khi chạy song song tests làm thay đổi trạng thái **shared services**; JUnit Testcontainers extension cũng không bảo đảm parallel execution như một tính năng được hỗ trợ chung.

### 18.1. Ba lựa chọn để kiểm soát concurrency

1. **Per-method resource scope**: rows/keys/queues có namespace độc quyền.
2. **JUnit resource lock hoặc chạy tuần tự** cho tests động tới schema/global state.
3. **Per-container/per-schema sandbox** cho tests cần destructive operations.

Snippet khóa resource chung:

```java
// Snippet, cần imports JUnit resource locking:
@ResourceLock("postgres-schema-public")
class MigrationContractTest {
    // Tests tạo/drop index hoặc ALTER TABLE không được chạy đồng thời.
}
```

**Lưu ý:** `@ResourceLock` chỉ phối hợp tests trong scope/JVM mà JUnit điều phối bằng cùng resource name; nó **không khóa một CI job khác** hay một JVM khác. Nếu nhiều CI jobs chia sẻ DB, cần namespace/instance riêng hoặc phối hợp bên ngoài.

## 19. Bộ ví dụ runnable: cùng infrastructure, dữ liệu độc lập

Ta sẽ viết **một project Spring Boot nhỏ** để học cách chia sẻ container một cách an toàn. API domain là bảng `ledger_entries` với các trường:

- `id`: khóa identity do PostgreSQL sinh.
- `owner_token`: định danh fixture per test.
- `business_key`: khóa nghiệp vụ có thể giống nhau ở hai owners khác nhau.
- `amount_minor`: số nguyên dương.

Constraint:

```sql
UNIQUE(owner_token, business_key)
CHECK(amount_minor > 0)
```

Mục đích của composite UNIQUE là mô phỏng **hợp đồng namespace-scoped key**. Nếu sản phẩm thật yêu cầu `business_key` global unique, **đừng đổi constraint để test chạy**: thay vào đó sinh business key riêng hoặc dùng schema/database isolation.

**Hai test classes** dùng cùng cấu hình Spring `SharedPostgresTestConfig`. Mỗi method tạo owner riêng và cleanup theo owner. Chúng không cần chứng minh có cùng **container ID** mới chứng minh data isolation; chúng chứng minh rằng **khi infrastructure được dùng chung, queries và cleanup vẫn không làm lẫn data**.

### 19.1. Cây thư mục

```text
shared-container-isolated-data/
  settings.gradle
  build.gradle
  src/main/java/com/example/isolation/
    IsolationApplication.java
    LedgerRepository.java
  src/main/resources/
    schema.sql
  src/test/java/com/example/isolation/
    SharedPostgresTestConfig.java
    OwnedRowsSupport.java
    SharedContainerIsolationATest.java
    SharedContainerIsolationBTest.java
```

Tất cả file Java cùng package `com.example.isolation`. Các code block file đầy đủ ở phần 20–25; snippets ngoài nhóm này không phải file runnable độc lập.

## 20. Gradle: Spring Boot 3.5 + Testcontainers 1.x

**`settings.gradle`**

```groovy
rootProject.name = 'shared-container-isolated-data'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Điểm cần hiểu:** Với **container Spring bean**, code này **không cần** `org.testcontainers:junit-jupiter` vì **không dùng `@Testcontainers`/`@Container`**. Nếu chuyển sang JUnit extension như phần 5, phải thêm `testImplementation 'org.testcontainers:junit-jupiter'`.

Spring Boot 3.5 BOM quản lý dependencies Testcontainers 1.x; các tọa độ `org.testcontainers:postgresql` và package `org.testcontainers.containers.PostgreSQLContainer` là của nhánh này. Testcontainers 2.x đổi coordinates/module packages; không trộn nhánh 2.x với source import 1.x. `spring-boot-testcontainers` cung cấp `@ServiceConnection` và lifecycle bridge.

Bản demo không có PostgreSQL runtime driver cho `bootRun` ngoài test; nó nhằm mục tiêu **integration tests trong Gradle**. Một ứng dụng production phải thêm dependency driver/runtime và database configuration theo chính sách triển khai.

## 21. Application và database schema

**`src/main/java/com/example/isolation/IsolationApplication.java`**

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner_token VARCHAR(80) NOT NULL,
    business_key VARCHAR(80) NOT NULL,
    amount_minor BIGINT NOT NULL,
    CONSTRAINT ck_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT uq_owner_business UNIQUE (owner_token, business_key)
);

CREATE INDEX idx_ledger_owner ON ledger_entries(owner_token);
```

Test sẽ đặt `spring.sql.init.mode=always` để Spring Boot chạy script trên PostgreSQL external container. Mỗi new context/container của demo có database riêng được tạo lúc start, nên `CREATE TABLE` không cần `IF NOT EXISTS`; schema init phải fail rõ nếu bảng đã tồn tại bất ngờ. Nếu dự án dùng Flyway/Liquibase, hãy chạy **migration thật** thay vì song song quản lý thêm `schema.sql`.

**Không reset identity trong test** và không assert ID phải là 1. Sequence/identity có thể sinh khoảng trống do rollback/failed inserts.

## 22. Repository: lọc theo owner ở mọi query

**`src/main/java/com/example/isolation/LedgerRepository.java`**

```java
package com.example.isolation;

import java.sql.PreparedStatement;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class LedgerRepository {

    private final JdbcTemplate jdbc;

    public LedgerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long create(
            String ownerToken,
            String businessKey,
            long amountMinor) {

        KeyHolder holder = new GeneratedKeyHolder();

        int changed = jdbc.update(connection -> {
            PreparedStatement statement =
                    connection.prepareStatement(
                            """
                            INSERT INTO ledger_entries
                                (owner_token, business_key, amount_minor)
                            VALUES (?, ?, ?)
                            """,
                            new String[] {"id"});
            statement.setString(1, ownerToken);
            statement.setString(2, businessKey);
            statement.setLong(3, amountMinor);
            return statement;
        }, holder);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Expected exactly one inserted row");
        }

        Number key = holder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "Database did not return generated key");
        }
        return key.longValue();
    }

    public long countByOwner(String ownerToken) {
        Long result = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM ledger_entries
                WHERE owner_token = ?
                """,
                Long.class, ownerToken);

        if (result == null) {
            throw new IllegalStateException(
                    "COUNT unexpectedly returned null");
        }
        return result;
    }

    public List<String> businessKeysByOwner(
            String ownerToken) {

        return jdbc.queryForList(
                """
                SELECT business_key FROM ledger_entries
                WHERE owner_token = ?
                ORDER BY business_key
                """,
                String.class, ownerToken);
    }

    public long totalAmountByOwner(String ownerToken) {
        Long value = jdbc.queryForObject(
                """
                SELECT COALESCE(SUM(amount_minor), 0)
                FROM ledger_entries
                WHERE owner_token = ?
                """,
                Long.class, ownerToken);

        if (value == null) {
            throw new IllegalStateException(
                    "SUM unexpectedly returned null");
        }
        return value;
    }

    public int deleteByOwner(String ownerToken) {
        return jdbc.update(
                """
                DELETE FROM ledger_entries
                WHERE owner_token = ?
                """,
                ownerToken);
    }
}
```

**Điểm cần học từ repository:**

- SQL values dùng `PreparedStatement`/bind parameters, không nối input vào SQL.
- `owner_token` xuất hiện trong mọi SELECT/DELETE của data fixture.
- `businessKeysByOwner` sort rõ để assertion không phụ thuộc thứ tự tự nhiên của database.
- `COUNT/SUM` chỉ được tính trong phạm vi owner, không phải toàn bảng.
- `deleteByOwner` không dùng `TRUNCATE`, `DELETE FROM ...` không WHERE hoặc drop table.
- Repository có thể dùng cho nhiều test methods dù DataSource và container được tái sử dụng.
- `GeneratedKeyHolder` nhận ID thật, không đoán identity bắt đầu tại 1.

Trong ứng dụng multi-tenant production, việc yêu cầu caller truyền `ownerToken` thủ công chưa đủ an toàn; có thể cần policy/auth context, Row-Level Security và review mọi query. Ở đây owner token là **dụng cụ test isolation**.

## 23. Container test config: một bean cho mỗi context

**`src/test/java/com/example/isolation/SharedPostgresTestConfig.java`**

```java
package com.example.isolation;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class SharedPostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("isolation_demo")
                .withUsername("test")
                .withPassword("test");
    }
}
```

**Tại sao đặt thành class riêng?**

- Hai test classes dùng `@Import(SharedPostgresTestConfig.class)`, giúp context configuration nhất quán và **có cơ hội cache/reuse cùng một context/container**.
- Boot nhận `@ServiceConnection` từ typed `PostgreSQLContainer<?>` và kết nối DataSource.
- Container lifecycle do Spring Boot quản lý cùng `ApplicationContext`.
- Không trộn JUnit `@Container` vào bean này; không để JUnit stop container khi một test class kết thúc mà context có thể còn trong cache.
- Database `isolation_demo` chỉ thuộc container ephemeral test, không trỏ production.
- Nếu cần cố tình test PostgreSQL 15/17 hoặc hai databases song song, tạo config khác và đánh giá lại context key/resource ownership.

**Không assert số lần start = 1 trên toàn suite**: một cache miss, forked JVM, khác profile hoặc context eviction có thể tạo thêm context và container. Test nên giữ nguyên ý nghĩa khi infrastructure được reuse **hoặc** khi mỗi context có service riêng.

## 24. Fixture helper: gắn ownership per method

**`src/test/java/com/example/isolation/OwnedRowsSupport.java`**

```java
package com.example.isolation;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;

import static org.junit.jupiter.api.Assertions.assertEquals;

public abstract class OwnedRowsSupport {

    @Autowired
    protected LedgerRepository ledger;

    // JUnit Jupiter mặc định tạo instance test class mới mỗi method.
    private final Set<String> ownedTokens = new HashSet<>();

    protected String newOwner() {
        String token = "it-" + UUID.randomUUID();
        ownedTokens.add(token);
        return token;
    }

    @AfterEach
    void deleteOnlyThisMethodData() {
        for (String owner : ownedTokens) {
            ledger.deleteByOwner(owner);
            assertEquals(0L, ledger.countByOwner(owner));
        }
    }
}
```

**Điểm đúng của cleanup:**

1. Owner được **ghi vào tracked set trước khi insert**, nên nếu INSERT thành công rồi assertion fail, teardown vẫn biết phạm vi phải dọn.
2. Nếu test tạo nhiều owners, helper dọn từng owner.
3. `DELETE` luôn dùng `WHERE owner_token = ?`.
4. `assertEquals(0L, countByOwner)` xác minh cleanup thực sự đã xóa data thuộc owner.
5. Nếu database lỗi lúc cleanup, `@AfterEach` không nuốt exception; test run báo failure.
6. Không có static `ownedTokens` dùng chung giữa classes; JUnit default `PER_METHOD` tạo một set mới mỗi test method.

**Giới hạn:** JVM kill/CI timeout có thể ngăn `@AfterEach`. Ephemeral container teardown, per-run database owner và janitor/TTL là lớp phòng vệ bổ sung. Nếu background job còn ghi vào cùng owner sau cleanup, cần dừng/chờ job trước khi xóa; trong demo không có async task.

## 25. Test class A: một container, hai owners độc lập

**`src/test/java/com/example/isolation/SharedContainerIsolationATest.java`**

```java
package com.example.isolation;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = IsolationApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(SharedPostgresTestConfig.class)
class SharedContainerIsolationATest extends OwnedRowsSupport {

    @Test
    void identicalBusinessKeyCanExistForDifferentOwners() {
        String a = newOwner();
        String b = newOwner();

        long idA = ledger.create(a, "ORDER-1", 10_000L);
        long idB = ledger.create(b, "ORDER-1", 20_000L);

        assertTrue(idA > 0);
        assertTrue(idB > 0);
        assertEquals(1L, ledger.countByOwner(a));
        assertEquals(1L, ledger.countByOwner(b));
        assertEquals(10_000L, ledger.totalAmountByOwner(a));
        assertEquals(20_000L, ledger.totalAmountByOwner(b));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(a));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(b));
    }

    @Test
    void duplicateBusinessKeyWithinOneOwnerIsRejected() {
        String owner = newOwner();

        ledger.create(owner, "ORDER-2", 5_000L);

        assertThrows(DuplicateKeyException.class,
                () -> ledger.create(owner, "ORDER-2", 7_000L));

        assertEquals(1L, ledger.countByOwner(owner));
        assertEquals(5_000L,
                ledger.totalAmountByOwner(owner));
    }
}
```

**Vì sao test A hữu ích?**

- Hai owners cùng dùng string `ORDER-1`, nhưng composite UNIQUE bảo vệ riêng theo owner.
- Không cần reset identity hoặc đoán ID.
- Test duplicate trong **cùng owner** phải fail đúng ràng buộc DB thật.
- `countByOwner` và `totalAmountByOwner` không nhìn dữ liệu của test B hay method khác.
- Teardown xóa rows của **a và b**, không chạm owner khác.
- Không khẳng định hai tests luôn chạy đồng thời; chúng được thiết kế để không phụ thuộc thứ tự.

**Một cảnh báo:** Nếu sản phẩm yêu cầu `ORDER-1` duy nhất trên toàn hệ thống, composite unique constraint này **không đúng business contract**. Bài học đang minh họa dữ liệu có namespace, không khuyến khích đổi schema product chỉ để test đỡ collision.

## 26. Test class B: tiếp tục dùng cùng config, không cần data của A

**`src/test/java/com/example/isolation/SharedContainerIsolationBTest.java`**

```java
package com.example.isolation;

import java.sql.Connection;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = IsolationApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(SharedPostgresTestConfig.class)
class SharedContainerIsolationBTest extends OwnedRowsSupport {

    @Autowired
    DataSource dataSource;

    @Test
    void freshOwnerStartsEmptyEvenWhenContainerIsRetained() {
        String owner = newOwner();

        // Không assert toàn table = 0;
        // chỉ assert namespace do method này sở hữu là trống.
        assertEquals(0L, ledger.countByOwner(owner));

        ledger.create(owner, "ORDER-1", 30_000L);

        assertEquals(1L, ledger.countByOwner(owner));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(owner));
    }

    @Test
    void deletingOneOwnerDoesNotDeleteAnotherOwner() {
        String first = newOwner();
        String second = newOwner();

        ledger.create(first, "X", 100L);
        ledger.create(second, "X", 200L);

        int deleted = ledger.deleteByOwner(first);

        assertEquals(1, deleted);
        assertEquals(0L, ledger.countByOwner(first));
        assertEquals(1L, ledger.countByOwner(second));
        assertEquals(200L,
                ledger.totalAmountByOwner(second));

        // @AfterEach sẽ xóa dữ liệu còn lại của second;
        // dọn first lần nữa là idempotent, không xóa owner khác.
    }

    @Test
    void datasourceReallyUsesPostgres() throws Exception {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }
}
```

**Điểm bảo vệ:**

- B có thể chạy trước A, sau A hoặc riêng lẻ; không đọc fixtures A để pass.
- `freshOwnerStartsEmpty...` không nói global database trống; nó nói **owner của method này** trống.
- `deletingOneOwnerDoesNotDeleteAnotherOwner` chứng minh cleanup **có scope** thay vì xóa hết bảng.
- `datasourceReallyUsesPostgres` xác nhận DB engine là PostgreSQL, không phải H2 silently auto-replaced.
- Cả A và B có cấu hình context tương đương; Spring TestContext **có thể** reuse context/container, nhưng test correctness không phụ thuộc reuse có xảy ra.

**Không gắn `@DirtiesContext` hoặc `@TestMethodOrder` để ép kết quả.** Khi muốn quan sát reuse để tối ưu performance, dùng startup metrics/logs có kiểm soát; không biến số container start thành điều kiện dữ liệu nghiệp vụ.

## 27. Cách chạy và kết quả kỳ vọng

Sau khi cấu hình project và Docker Engine phù hợp:

```bash
docker version
docker info

./gradlew test --tests com.example.isolation.SharedContainerIsolationATest --tests com.example.isolation.SharedContainerIsolationBTest
```

Trên PowerShell:

```powershell
docker version
docker info

.\gradlew.bat test --tests com.example.isolation.SharedContainerIsolationATest --tests com.example.isolation.SharedContainerIsolationBTest
```

Kết quả dự kiến:

| Class | Số `@Test` | Điều kiểm |
|---|---:|---|
| `SharedContainerIsolationATest` | 2 | Hai owners cùng key; duplicate trong cùng owner |
| `SharedContainerIsolationBTest` | 3 | Namespace mới rỗng; cleanup có scope; PostgreSQL driver |
| **Tổng** | **5** | Chia sẻ infrastructure mà không dựa dữ liệu test khác |

Gradle dự kiến báo `BUILD SUCCESSFUL` khi mã, version, Docker runtime và image repository sẵn sàng. **Đây là kết quả dự kiến sau khi rà soát code, không phải tuyên bố đã chạy Docker/Gradle trên workspace của bạn.**

Không có stdout nghiệp vụ cố định. Docker container ID, mapped port, sequence values và log startup có thể khác nhau. JUnit report thường ở `build/reports/tests/test/index.html` và XML tại `build/test-results/test/` của module.

**Chạy thử riêng từng class, rồi chạy cùng suite:** cả hai trường hợp đều phải giữ các assertions đúng. Nếu chỉ chạy một class thì xanh nhưng chạy hai class đỏ, hãy điều tra **shared state, context cache, startup/teardown order** trước khi thêm test ordering.

## 28. Vì sao code này không dùng `@Transactional` trên test?

Ta muốn minh họa cleanup **tường minh theo owner token**, kể cả khi rows được commit. Nếu gắn `@Transactional` vào mọi test method, Spring TestContext có thể rollback rows sau method; bài học về ownership và cleanup sẽ khó quan sát hơn.

Điều này không có nghĩa test transactions là xấu. Trong một repository `@JdbcTest`, rollback mặc định thường hữu ích và nhanh. Nhưng phải phân biệt:

- Test đang **mượn transaction JUnit để dọn data**.
- Service thật có **@Transactional đúng boundary**.
- HTTP server/broker khác thread/process có transaction riêng.
- Redis/Kafka/Elasticsearch không tự rollback theo JDBC test.

Trong ví dụ, `LedgerRepository.create(...)` dùng connection từ Spring DataSource; ngoài test-managed transaction, một lệnh JDBC có thể commit theo auto-commit. `@AfterEach` xóa data theo owner. Điều này làm hành vi isolation quan sát được rõ và không phụ thuộc rollback ngầm.

### 28.1. Nếu muốn test transaction rollback thật

Viết một test service có `@Transactional`, gọi service qua Spring proxy, gây exception sau write thứ nhất, rồi query DB sau exception **ngoài test-managed transaction**. Đừng chỉ kiểm table trống sau một `@JdbcTest` vì rollback của JUnit có thể che lỗi của service.

## 29. Chạy song song: ví dụ đúng ở đâu, còn cần gì?

Row-level token giúp hai test methods có thể ghi cùng table mà ít collision hơn, nhưng **không tự bảo đảm suite parallel safe**:

- SQL global DDL/cleanup không được thực hiện đồng thời.
- Mọi query phải có owner-filter; repository methods khác không được dùng `findAll` cho assertions scoped.
- Nếu có unique constraints toàn table (ngoài owner key), random token chưa đủ.
- Test async/background workers phải propagate owner context hoặc dùng queue/job isolation.
- Container lifecycle phải còn hoạt động đến khi tất cả tasks đang dùng hoàn tất.
- JUnit/Spring/DB client có thể có cấu hình parallel-specific cần đánh giá.
- Không bật parallel execution của JUnit extension một cách thiếu kiểm soát — tài liệu Testcontainers nêu extension không bảo đảm hỗ trợ parallel execution chung.

**Chọn song song có chủ đích:** với các test chỉ đọc hoặc owner-scoped writes đơn giản, có thể cho phép nếu đã chứng minh không có global state. Với migration, truncate, broker topic deletion, context dirtying hoặc tests có locks shared, chạy tuần tự hoặc cấp sandbox riêng.

## 30. Data isolation trong MongoDB, Redis, Kafka và Elasticsearch

Container dùng chung vs dữ liệu dùng chung không chỉ là PostgreSQL.

### 30.1. MongoDB

**Dùng chung MongoDBContainer** có thể có nhiều databases/collections:

- Per-test database hoặc collection name.
- Document có `testRunId`/`ownerId`, query/delete theo scope.
- `dropCollection` xóa indexes của collection; nếu cần UNIQUE/TTL indexes, phải ensure lại.
- Dọn `remove(Query...)` giữ indexes; không dùng `dropDatabase()` trên shared DB.
- Mongo transactions cần replica set/config tương ứng và **không tự rollback với Spring JDBC transaction**.

### 30.2. Redis

**Dùng chung Redis instance** cần key namespace:

```text
it:orders:<run-id>:<test-id>:ORDER-1
it:orders:<run-id>:<test-id>:ORDER-2
```

- Track keys đã tạo và `DEL`/`UNLINK` đúng những keys đó.
- `SCAN` theo namespace riêng khi keys phát sinh động; hiểu scan không phải snapshot atomic.
- Không dùng `FLUSHDB`/`FLUSHALL` trên shared instance.
- TTL giúp hạn chế orphans, **không thay teardown**.
- Spring Cache key generators, background jobs và streams/consumer groups có thể tạo state ngoài keys thông thường.

### 30.3. Kafka

**Dùng chung Kafka broker** không có nghĩa dùng chung consumer group:

- Test topics/consumer groups nên có tên riêng khi offset/retention có thể ảnh hưởng.
- Một consumer group dùng chung sẽ chia partitions giữa consumers, khiến tests giành message.
- `auto.offset.reset` có ý nghĩa khi group chưa có committed offset; không phải lệnh reset toàn bộ broker.
- Tạo/xóa topic của test trong shared broker cần ownership rõ; delete topic toàn bộ không an toàn.
- Message còn sau test hoặc producer async có thể đưa events vào topic sau cleanup.
- Retry/idempotency/transaction semantics cần integration tests đúng Kafka version/config.

### 30.4. Elasticsearch/OpenSearch

- Dùng index names riêng theo run/test; không xóa `orders-*` quá rộng.
- Alias và mappings là shared metadata, phải có plan khi reset.
- Search near-real-time: cần refresh/eventual assertions thay vì `Thread.sleep` tùy tiện.
- Xóa document không tương đương xóa index + mapping.
- Index template/ILM có thể tự sinh thêm resources; cần inventory và cleanup đúng owner.

### 30.5. Object storage và filesystem

Container riêng chưa chắc giúp nếu tests ghi vào bucket S3 shared hoặc local `/tmp/output.json`. Dùng prefix/path có run/test ID, xóa đúng objects/versions khi có versioning, và không dùng tài khoản production. Nếu nhiều tests viết cùng file, JVM object isolation hoàn toàn không giúp.

**Tổng quát:** “Shared infrastructure, isolated state” là một **nguyên tắc liên backend**, không phải một annotation riêng của Testcontainers.

## 31. Spring context caching: hiểu điều gì quyết định share

Spring TestContext cache key dựa trên nhiều thành phần, gồm:

- Configuration classes/locations.
- Context initializers, customizers và imported config.
- Active profiles và test properties.
- Dynamic property sources.
- Bean overrides/mocks và framework-specific customizers.
- Web context resource path và các thành phần khác trong context configuration.

Nếu hai test classes có cùng key, context có thể được reuse **trong cùng JVM/test suite**. Nếu chạy Gradle forked test processes, cache không chia sẻ giữa processes. Nếu cache bị eviction, context có thể bị đóng và dựng lại. Một test có `@DirtiesContext` cũng có thể làm context bị loại bỏ.

**Vì vậy không thiết kế correctness phụ thuộc việc context cache hit.** Nó là optimization và lifecycle mechanism. Dữ liệu test phải sạch ngay cả khi context mới, và độc lập ngay cả khi context được giữ từ class trước.

### 31.1. Test class khác mà vẫn trỏ container cũ?

Khi một class dùng static JUnit `@Container` và context được cache, sau khi JUnit stop container, class khác có thể nhận DataSource trỏ tới URL cũ và báo connection refused. Nếu dùng Spring bean container, lifetime theo context thường hợp hơn. Nhưng **đừng dùng @DirtiesContext bừa bãi** để xử lý mọi vấn đề; hãy chọn ownership/lifecycle rõ.

## 32. Cleanup khi test thất bại, JVM crash hoặc CI bị hủy

`@AfterEach` là bước bình thường của JUnit, nhưng không thể chạy nếu:

- JVM bị kill -9, máy mất điện hoặc runner bị hủy.
- Docker daemon/network mất kết nối đúng lúc teardown.
- Test treo/timeout và process không còn hoạt động.
- Một callback cleanup khác ném exception khiến chuỗi teardown bị gián đoạn.

Phòng vệ nhiều lớp:

1. **Per-test owner token** để xác định dữ liệu mồ côi.
2. **Per-run/database/container** để có thể dispose toàn phạm vi.
3. **Container resource reaper** và CI ephemeral runner lifecycle theo policy.
4. TTL/retention cho keys/data phụ trợ khi phù hợp.
5. Janitor job có allowlist chỉ xóa test namespace hết hạn.
6. Ghi cleanup failure rõ, không nuốt exception.
7. Không xóa data của test đang chạy bằng cleanup quá rộng.

**Không chạy `docker system prune -af` hay drop toàn cluster khi một test fail.** Xác định đúng Docker objects/DB resources thuộc run. Với service credentials, test-only quyền tối thiểu vẫn là rào chắn quan trọng nếu vô tình dùng sai connection string.

## 33. Khi nào dùng “shared fixture” có chủ đích?

Đôi khi nhiều tests cần cùng một **read-only fixture** lớn, ví dụ catalog sản phẩm tĩnh hoặc reference exchange rates. Nó có thể được seed một lần vào cùng container để giảm startup.

**Được chấp nhận khi:**

- Dữ liệu được xem là **immutable** trong các tests.
- Không test nào mutate/xóa fixture chung.
- Có version/schema/checksum rõ để biết fixture đúng.
- Các test methods vẫn viết data có owner namespace riêng.
- Việc seed trước các reads có lifecycle/ordering độc lập test order.

**Không chấp nhận khi:**

- Test A “setup” và test B phải chạy sau để dùng dữ liệu A.
- Một test xóa/sửa fixture read-only của suite.
- Fixture được update tự động từ actual response mỗi lần chạy.
- Source data chứa PII hoặc secrets production.
- Dùng một global counter/id khiến tests tranh nhau quyền sở hữu.

Với shared immutable fixture, có thể có cả **container share và data share có chủ đích**. Điều cần tránh là **shared mutable state không có owner hoặc hợp đồng rõ**.

## 34. Những anti-pattern nên loại bỏ

| Anti-pattern | Vì sao sai | Thay bằng |
|---|---|---|
| Static `@Container` nên database tự sạch | Static giữ container qua các methods | Transaction/row/schema cleanup |
| New JUnit test instance = new DB | Test instance chỉ là object Java | Per-test owner hoặc backend isolation |
| `@DirtiesContext` để xóa Redis/Postgres | Context không tự reset external shared state | Scoped delete/DB riêng |
| `TRUNCATE` sau mỗi method trong shared DB | Xóa rows của method khác | `DELETE WHERE owner_token=?` |
| `findAll()` rồi assert size==1 khi DB share | Đếm data của test khác | Query theo owner |
| `UUID` ở ID nhưng không scope query | Không ngăn toàn-table reads | Owner predicate trong mọi operation |
| Dùng unique key global cố định | Collision giữa runs | Unique test key hoặc DB riêng |
| Container reuse experimental trên CI | State tồn tại và cleanup không bảo đảm | Ephemeral containers trong CI |
| JUnit stop container, Spring cache còn dùng | Lifecycle mismatch | Spring-managed container bean |
| Gắn `@Transactional` lên test HTTP và tin server rollback | HTTP server thread/transaction khác | Explicit cleanup + assertion after server call |
| Coi transaction rollback dọn Kafka/Redis | Không cùng JDBC transaction | Backend-specific cleanup |
| Bật parallel rồi “fix” bằng sleep | Race vẫn tồn tại | Namespace/resource locks/per-container |
| Delete topic/index theo prefix rộng | Xóa tài nguyên của test khác | Exact owner-scoped names |
| Assert số container start == 1 để coi test pass | Cache/fork khác vẫn có thể đúng data contract | Đo metrics riêng; correctness độc lập |
| Dọn dữ liệu nhưng ignore exception | Contamination trôi sang test sau | Cleanup failure báo test fail |
| Database test dùng credentials production | Nguy cơ phá dữ liệu thật | Docker/test-only account/network |

## 35. Troubleshooting: xem lỗi thuộc lifecycle hay state

| Triệu chứng | Lớp lỗi | Cách điều tra |
|---|---|---|
| Chạy riêng pass, chạy suite fail vì extra rows | Data contamination | Query nào thiếu owner filter? |
| Duplicate key chỉ xuất hiện lần chạy thứ hai | Fixture/key collision | Unique constraints, cleanup, run IDs |
| Connection refused sau khi class A kết thúc | Lifecycle/context cache | Static JUnit container bị stop? |
| Spring context startup lặp nhiều lần | Context cache miss | Profile/properties/import/bean overrides |
| DataSource dùng H2 thay PostgreSQL | Auto-config | `@ServiceConnection` và JDBC driver |
| `relation does not exist` | Migration/init | `spring.sql.init.mode=always`, schema config |
| B xóa data khi A đang assert | Shared destructive cleanup | TRUNCATE/DELETE không WHERE/resource lock |
| Identity sequence tăng qua rollback | DB sequence behavior | Không assert contiguous IDs |
| CI parallel fail nhưng local tuần tự pass | Concurrency/state | Shared DB/topic/index/async writers |
| Kafka test không nhận event | Consumer group/offset | Group ID, topic, committed offsets |
| Redis cache hit không dự kiến | Shared key namespace | Key generator/prefix/TTL |
| Search document chưa xuất hiện | Eventual consistency | Refresh/eventual assertion |
| Hết test nhưng container còn chạy | Reuse/manual lifecycle | `withReuse`/resource reaper policy |
| Test xóa wrong database | Connection config sai | Test-only credentials, DB product, guard |
| @AfterEach không dọn khi process chết | Crash/lifecycle | Ephemeral disposal, janitor |
| Test bị chậm do per-method containers | Performance | Per-class/context container + scoped data |

### 35.1. Quy trình debug có thứ tự

1. **Xác định backend thật:** in/kiểm `DatabaseMetaData.getDatabaseProductName()`, database name, không xuất credential.
2. **Xác định lifecycle container:** JUnit static, instance, bean hay manual singleton?
3. **Xác định context cache:** cấu hình tests có cùng key không, context có còn sống không?
4. **Xác định owner:** mỗi record/queue/key thuộc method/run nào?
5. **Xem queries và cleanup:** chỗ nào thiếu WHERE/namespace?
6. **Xem transaction:** JUnit rollback có áp dụng cho đường code chạy không?
7. **Kiểm parallel/background tasks:** có writer còn chạy sau method không?
8. **Kiểm migration/index:** có global DDL ảnh hưởng tất cả tests không?
9. **Chạy cả class/suite thay vì chỉ một method:** nếu khác, báo shared state.
10. **Sửa isolation**, không chỉ thêm test ordering/sleep hoặc tăng timeout.

## 36. Bài tập thực hành

### Bài A — một container cho cả test class

Một test class có static `@Container PostgreSQLContainer`, hai methods cùng insert `external_id="ORDER-1"`. Test thứ hai báo duplicate key. Vì sao? Hãy nêu ba hướng sửa mà không biến test thành ordered integration scenario.

**Đáp án định hướng:** Static container giữ DB giữa methods. Dùng per-test key/owner token, rollback transaction hoặc database/schema riêng; cleanup đúng scope.

### Bài B — Spring context cache

Class A nạp `@SpringBootTest` với static `@Container`. Sau A, JUnit stop container. Class B dùng context được cache và gặp connection refused. Đây là “shared data” hay “shared lifecycle” bug?

**Đáp án:** Lifecycle mismatch. Dùng Spring-managed container bean hoặc `@ImportTestcontainers` khi context cần dùng lâu hơn class A.

### Bài C — two tenants, one table

Tenant A và B đều có `business_key=ORDER-1`. Nếu contract cho phép trùng giữa tenants, UNIQUE nào hợp lý? Nếu business key bắt buộc global unique, có được sửa DB constraint chỉ để test pass không?

**Đáp án:** Composite unique `(tenant_id,business_key)` nếu domain cho phép. Nếu global unique, giữ constraint và sinh test keys riêng hoặc chọn per-schema/database.

### Bài D — cleanup `TRUNCATE`

Hai test chạy parallel trên cùng Postgres container. Test A vừa insert, test B gọi `TRUNCATE ledger_entries` trong `@AfterEach`. Điều gì có thể xảy ra?

**Đáp án:** B xóa data của A; A có thể fail hoặc bị block bởi locks. Dùng per-owner delete, resource lock hoặc backend riêng.

### Bài E — context mới có giải quyết contamination?

Một test gọi `@DirtiesContext` và sử dụng PostgreSQL external shared instance. Context mới có đồng nghĩa mọi rows cũ đã bị xóa?

**Đáp án:** Không. Context restart không tự xóa external DB. Cần scoped cleanup hoặc DB/schema độc quyền.

### Bài F — test HTTP và `@Transactional`

JUnit client test gắn `@Transactional` rồi POST `/api/orders` tới Spring Boot RANDOM_PORT server. Sau method, record vẫn tồn tại. Có phải Spring rollback bị bug?

**Đáp án:** Không nhất thiết. Server request xử lý trong thread/transaction riêng; JUnit test transaction không bao response-side writes.

### Bài G — shared Redis

Một Redis container được share giữa nhiều classes. Test A gọi `FLUSHDB` để reset, test B mất session key. Hãy đề xuất key namespace và teardown phù hợp.

**Đáp án:** Prefix theo run/test, track owned keys, `DEL` theo đúng list hoặc SCAN trong namespace riêng; tránh FLUSHDB/FLUSHALL.

### Bài H — Kafka offsets

Hai tests dùng cùng topic và `group.id=integration`, chạy đồng thời. Một test không nhận đủ events. Nguyên nhân và hướng cô lập?

**Đáp án:** Consumers cùng group có thể chia partitions/offset state. Dùng group/topic riêng, kiểm offset và producer lifecycle; không xóa topic shared đang được test khác dùng.

### Bài I — reusable container giữa hai Gradle runs

Developer bật `withReuse(true)`, hôm sau test count=0 fail dù code chưa đổi. Vì sao? Có nên bật reuse trên CI?

**Đáp án:** Reusable container có thể giữ data qua runs. Tài liệu Testcontainers nêu reuse experimental không phù hợp CI; local cần reset/namespace rõ.

### Bài J — đánh giá công bằng chi phí

Một nhóm có 500 repository tests. Per-method Postgres container mất nhiều thời gian; shared context/container nhanh nhưng dễ contamination. Hãy đề xuất mô hình gồm slices/transaction rollback/owner scopes và một vài tests per-container cho migrations. Bạn sẽ đo metric gì để chứng minh improvement?

**Gợi ý:** Thời gian startup, total suite time, flaky failures, false positives, resource usage, context cache hit rate và data isolation violations.

## 37. Checklist cuối bài

- [ ] Tôi phân biệt **chia sẻ container** với **chia sẻ mutable data**.
- [ ] Tôi biết ai start/stop container: JUnit, Spring bean, manual singleton hay reuse experimental.
- [ ] Nếu container static `@Container`, tôi hiểu DB rows không reset giữa methods.
- [ ] Nếu dùng Spring-managed container, tôi hiểu lifetime theo `ApplicationContext`.
- [ ] Nếu context được cache, tôi không dựa vào context restart để reset database.
- [ ] Không có DataSource trỏ tới JUnit container đã bị stop.
- [ ] Spring Boot `@ServiceConnection` dùng để kết nối, không tự cleanup data.
- [ ] Mỗi test có namespace/owner/fixture độc lập.
- [ ] Mọi query và cleanup có đúng predicate theo owner khi dùng chung bảng.
- [ ] UNIQUE constraints phản ánh business domain, không bị nới lỏng chỉ cho test.
- [ ] Tôi không assert row counts toàn DB khi DB có thể chứa data của tests khác.
- [ ] Tôi không dựa vào ID/sequence bắt đầu từ 1 hay liên tục.
- [ ] Cleanup chỉ xóa resources thuộc test và verify hậu điều kiện.
- [ ] Cleanup error khiến test run fail, không bị ignore.
- [ ] Per-schema/per-database/per-container isolation được chọn khi có DDL/destructive operations.
- [ ] Test transactions chỉ dùng cho writes trong boundary rollback thực sự bao phủ.
- [ ] HTTP RANDOM_PORT/async/Redis/Kafka writes có chiến lược cleanup riêng.
- [ ] Tests chạy độc lập, không phụ thuộc `@TestMethodOrder`.
- [ ] Parallel execution có resource ownership/locks rõ ràng.
- [ ] Reusable container experimental không được bật tự tiện trên CI.
- [ ] CI/Docker runner có quota, quyền hạn và cleanup policy an toàn.
- [ ] Tôi biết cùng một JVM và forked JVM ảnh hưởng Spring context cache thế nào.
- [ ] Nếu test dùng Mongo/Redis/Kafka/search, tôi tách cả collection/key/topic/index metadata phù hợp.
- [ ] Không có broad `TRUNCATE`/`FLUSHDB`/`DROP SCHEMA` trên backend shared.
- [ ] Test dùng credentials và endpoints chỉ thuộc môi trường test.
- [ ] Kết luận kiểm thử dựa trên business/db assertions, không dựa container được start bao nhiêu lần.

**Kết luận:** **Container là đơn vị hạ tầng; test data là đơn vị trạng thái và ownership.** Testcontainers có thể chia sẻ một PostgreSQL/Redis/Kafka process để tiết kiệm thời gian startup, nhưng mọi test vẫn phải nhận diện fixture của chính mình, query đúng scope, xử lý transaction và cleanup an toàn. Spring context cache, static `@Container`, singleton và reusable containers là những cơ chế **lifecycle khác nhau**, không phải phép màu reset dữ liệu. Hãy chọn row/schema/database/container isolation theo rủi ro và không để một test phá môi trường của test khác.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testcontainers, Spring-managed container beans, JUnit extension, service connections và lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Testcontainers — JUnit Jupiter static/instance `@Container` và giới hạn parallel execution: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Manual container lifecycle và singleton pattern: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/
- Testcontainers — Reusable Containers (experimental, không phù hợp CI): https://java.testcontainers.org/features/reuse/
- Spring Framework — TestContext caching và context cache keys: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Parallel Test Execution guidelines: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html
- Spring Framework — Test-managed transactions/rollback rules: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- PostgreSQL — Schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
