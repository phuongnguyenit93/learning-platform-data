# Độc lập theo phương thức, lớp, JVM và tài nguyên ngoài trong kiểm thử Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Cách ly và chạy song song  
> **Đề bài:** Độc lập theo phương thức, lớp, JVM và tài nguyên ngoài  
> **Mục tiêu:** Phân biệt chính xác bốn cấp độ isolation: test method, test class/Spring ApplicationContext, tiến trình JVM và database/broker/filesystem/external services. Xây dựng tests chạy ổn định khi thay đổi thứ tự hoặc bật JUnit parallelism; kiểm soát state, transaction, resource ownership, Spring TestContext cache, Testcontainers lifecycle và Maven Surefire forks. Ví dụ Java 17 + Spring Boot 3.5.0 + JUnit Jupiter + PostgreSQL Testcontainers.

## 1. Định nghĩa test độc lập: không dựa vào những gì test khác đã làm

Một test **độc lập** phải thỏa điều kiện sau:

- Setup của nó xác định đầy đủ preconditions cần thiết.
- Kết quả không phụ thuộc test nào chạy trước, chạy sau hoặc bị skip.
- Không có trạng thái không khai báo được dùng ngầm từ test khác.
- Test chỉ sửa các resources mình sở hữu hoặc có cơ chế đồng bộ khi phải chia sẻ.
- Cleanup không phá resources của test đang chạy song song.
- Khi thay test order, đổi thread count, đổi JVM fork hoặc đổi runner máy CI, hợp đồng vẫn được giữ — trừ khi suite được thiết kế và ghi rõ phạm vi serialization.
- Bất kỳ lỗi infrastructure (Docker không có, database container không start) đều được báo là lỗi môi trường, không gán là “business assertion pass”.

**Quan trọng:** “Chạy mỗi test trong một object Java mới” không đồng nghĩa “mỗi test có một database mới”. Bốn cấp độ dưới đây là những ranh giới khác nhau và có thể chồng lấn.

### 1.1. Bốn lớp cách ly

```text
Maven / CI job
│
├── Forked JVM #1                          [ranh giới JVM]
│   ├── JUnit test plan
│   │   ├── Class A                        [ranh giới lớp]
│   │   │   ├── method a()  test object A1 [ranh giới method]
│   │   │   └── method b()  test object A2
│   │   └── Class B
│   │       ├── method c()  test object B1
│   │       └── method d()  test object B2
│   └── Spring TestContext static cache
│       └── ApplicationContext X
│           ├── singleton Service bean
│           ├── CacheManager / DataSource
│           └── background listeners/schedulers
│
├── Forked JVM #2                          [static state khác]
│   └── Spring TestContext static cache #2
│
└── External resources                     [không tự chia theo JVM]
    ├── PostgreSQL database/schema/table/row
    ├── Redis DB/key namespace
    ├── RabbitMQ broker/vhost/queue/exchange
    ├── Kafka topic/consumer group
    ├── Filesystem/object store
    └── Remote HTTP sandbox
```

Hai JVM có **heap/static state riêng**, nhưng vẫn có thể cùng trỏ vào một PostgreSQL schema hoặc RabbitMQ queue. Hai test classes dùng **ApplicationContext khác nhau** vẫn có thể gây race nếu cùng xóa bảng dữ liệu. Hai test methods có object riêng vẫn có thể dùng chung singleton bean trong Spring context.

### 1.2. Ma trận khả năng chia sẻ

| Phạm vi | Thứ thường được tách | Thứ vẫn có thể bị chia sẻ |
| --- | --- | --- |
| Mỗi `@Test` method | Instance fields nếu JUnit `PER_METHOD` | `static`, singleton beans, System properties, files, DB, broker |
| Mỗi JUnit test class | Lifecycle `@BeforeAll`/`@AfterAll`, class-level fixtures | Spring cached context, static state cùng JVM, external resources |
| Mỗi Spring `ApplicationContext` | Bean instances của context đó | Static state JVM, OS ports, Redis/DB/broker, other contexts pointing same endpoints |
| Mỗi forked JVM | Heap, classloader, static cache và System properties của JVM đó | Database, broker, filesystem, ports, cloud APIs, test credentials |
| Mỗi Testcontainers container | Thường process/broker/database server riêng | Host filesystem, bind mounts, external network, image registry, global daemon |
| Mỗi DB schema/vhost/namespace | Dữ liệu trong phạm vi đã cô lập | DB instance capacity, global limits, permissions, network và shared services |
| Mỗi CI job | Workspace/runner tùy platform | Shared database, Docker daemon, artifact bucket, service account, staging |

**Kết luận của ma trận:** Muốn test độc lập phải kiểm soát **state + lifecycle + naming + cleanup** ở mọi lớp liên quan. Không có annotation đơn lẻ tự làm mọi tài nguyên độc lập.

## 2. Cách ly theo phương thức: JUnit Jupiter `PER_METHOD`

### 2.1. Mặc định của JUnit 5

Theo JUnit Jupiter, lifecycle mặc định là:

```java
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ExampleTest {
    // mỗi @Test có một instance mới của test class
}
```

Nếu không khai annotation, mặc định cũng là `PER_METHOD` trừ khi suite/config override default.

Ví dụ:

```java
class SafeInstanceStateTest {

    private final List<String> values = new ArrayList<>();

    @Test
    void firstMethod() {
        assertThat(values).isEmpty();
        values.add("first");
        assertThat(values).containsExactly("first");
    }

    @Test
    void secondMethod() {
        assertThat(values).isEmpty();
        values.add("second");
        assertThat(values).containsExactly("second");
    }
}
```

Đây là snippet; cần imports JUnit, AssertJ và `java.util`. Mỗi test có một `values` riêng, nên không cần dựa vào method order. Bản runnable với `@Execution(CONCURRENT)` ở phần 8.

### 2.2. `PER_METHOD` **không** tách static

Ví dụ **anti-pattern**:

```java
class BrokenStaticStateTest {

    private static final List<String> SHARED =
            new ArrayList<>();

    @Test
    void first() {
        SHARED.add("first");
        assertThat(SHARED).hasSize(1);
    }

    @Test
    void second() {
        SHARED.add("second");
        assertThat(SHARED).hasSize(1); // phụ thuộc thứ tự
    }
}
```

Nếu test đầu đã chạy, test sau sẽ thấy state cũ. Nếu chạy concurrent, `ArrayList` còn không thread-safe. `PER_METHOD` chỉ tạo **test object** mới; static fields thuộc classloader/JVM.

Giải pháp: dùng instance-local state, immutable shared fixtures hoặc reset có kỷ luật nếu resource bắt buộc shared. Tránh `static HashMap`/`static cache`/`static sequence counter` làm test fixture khi chưa định nghĩa concurrency và cleanup.

### 2.3. `PER_CLASS` có rủi ro gì?

Với:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassTest {
    private int counter;

    @Test void a() { counter++; }
    @Test void b() { counter++; }
}
```

Hai methods dùng **cùng instance**. Nếu test phụ thuộc `counter==1` thì thứ tự test trở thành input ẩn. Với parallel execution, mutable field có data races.

`PER_CLASS` hữu ích khi cần non-static `@BeforeAll`/`@AfterAll` hoặc fixture đắt tiền, nhưng phải:

- Reset trạng thái mỗi method (`@BeforeEach`) hoặc dùng immutable shared state.
- Đồng bộ nếu methods concurrent.
- Không dùng thứ tự test như một cách truyền dữ liệu giữa steps.
- Không tự bật concurrency nếu fixture không thread-safe.
- Ghi rõ sở hữu resource và teardown tại đúng lifecycle.

**Đừng nhầm:** `@BeforeEach` chạy trước mỗi method nhưng không đảm bảo xóa global database của test khác an toàn, đặc biệt khi methods/classes parallel.

### 2.4. Method parameter và `@TempDir`

JUnit cung cấp `@TempDir` để tạo thư mục tạm theo field/parameter declaration:

```java
@Test
void generateReport(@TempDir Path dir) throws IOException {
    Path report = dir.resolve("report.txt");
    Files.writeString(report, "ok");
    assertThat(Files.readString(report)).isEqualTo("ok");
}
```

Dùng temporary directory được JUnit quản lý tốt hơn viết mọi test vào `/tmp/report.txt` hoặc `C:\temp\report.txt`. Không dùng một tên tệp toàn cục khi jobs CI có thể chạy cùng runner/volume. Với external temp dirs ngoài JUnit, tạo unique path và cleanup theo ownership.

### 2.5. Phân biệt “tái sử dụng object” và “tái sử dụng side effect”

Ngay cả khi test object được tạo mới, những thứ sau có thể giữ nguyên:

- Spring singleton `@Service` hoặc `@Repository` trong cached `ApplicationContext`.
- In-memory cache của bean.
- Hikari connection pool và database persisted rows.
- RabbitMQ listener container hoặc scheduler thread.
- System property/TimeZone/Locale tĩnh của JVM.
- Redis keys/TTL, bucket files, test messages.

Việc gọi `new Service(...)` trong unit tests giúp kiểm soát state trong object ấy, nhưng không tự cô lập dependency static hoặc external client singleton.

## 3. Cách ly theo lớp: Spring TestContext cache không đồng nghĩa context mới mỗi class

### 3.1. Spring TestContext cache chia sẻ giữa classes

Spring Framework TestContext cache giữ `ApplicationContext` theo **khóa cấu hình**, gồm:

- `@ContextConfiguration` classes/locations, initializers, loaders.
- Active profiles (`@ActiveProfiles`).
- Test property sources và inline properties.
- Context customizers: Spring Boot test features, `@DynamicPropertySource`, `@MockitoBean`/bean overrides.
- Parent context, web resource base path và các cấu hình khác.

Hai test classes có configuration key tương đương **có thể reuse cùng một `ApplicationContext`** trong cùng JVM. Nó giúp suite nhanh hơn, nhưng singleton beans và background workers có thể tồn tại giữa classes.

Đừng giả định:

> “Class A kết thúc ⇒ Spring context đã đóng ⇒ singleton state sạch.”

Thực tế, cùng context có thể còn sống và được dùng bởi Class B. Ngay cả khi class B có test object mới, nó vẫn inject cùng bean singleton.

### 3.2. Test context **khác** cũng có thể dùng chung database

Hai lớp:

```java
@SpringBootTest(properties = "feature.alpha=true")
class ATest { }

@SpringBootTest(properties = "feature.alpha=false")
class BTest { }
```

có thể sinh hai Spring contexts khác nhau do inline properties khác nhau; nhưng nếu cả hai trỏ cùng `spring.datasource.url` thì vẫn truy cập cùng database. Không nhầm context uniqueness với external data isolation.

### 3.3. `@DirtiesContext`: phải dùng đúng mục đích

`@DirtiesContext` đánh dấu context đã bị thay đổi và cần loại khỏi cache/đóng, ví dụ:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest
class ContextMutatingTest { }
```

Nó có ích khi test sửa bean definitions, singleton application state khó reset, hoặc context phụ thuộc container test class đã dừng.

Nhưng:

- Nó tốn thời gian vì Spring phải reload context sau đó.
- Nó không rollback database khác JVM.
- Nó không xóa RabbitMQ/Redis/filesystem resources.
- Nó có thể gây lỗi cho test khác đang dùng context shared **nếu chạy song song**.
- Không nên đặt trên mọi test như một cách “làm sạch mọi thứ”.
- Nếu chỉ cần xóa một database row của test, cleanup scoped thường tốt hơn reload cả context.

Spring Framework 6.2 khuyến nghị **không parallelize** test classes dùng `@DirtiesContext`, `@MockitoBean`/`@MockitoSpyBean`, method order hoặc thay đổi state shared DB/broker/filesystem nếu không kiểm soát được cạnh tranh.

### 3.4. `@MockitoBean`, mock reset và parallel tests

Spring 6.2 giới thiệu `@MockitoBean`/`@MockitoSpyBean`. Khi hai test methods dùng một context/mock bean chung và cả hai cùng stub/verify/reset, chúng có thể can thiệp nhau. Mockito stubbing không phải “thread isolation”.

- Tách test scope hoặc dùng class-level serialization cho tests có shared mock beans.
- Ưu tiên pure unit tests với Mockito mocks được tạo riêng mỗi test method.
- Không cố đạt song song mọi test slices/full-context nếu mock lifecycle không bảo đảm.
- Không dùng `Thread.sleep` để mong hai tests tránh đụng nhau.

### 3.5. Bean singleton có mutable state cần được xem là shared resource

```java
@Service
class CounterService {
    private int counter;      // mutable singleton state
    void increment() { counter++; }
    int count() { return counter; }
}
```

Ngay cả khi JUnit tạo hai test objects, `CounterService` trong Spring context vẫn có thể là **một singleton**. Trên nhiều threads, `counter++` còn có data race. Giải pháp: thiết kế bean stateless hoặc thread-safe, đồng thời không dùng global counter làm test fixture trừ khi có isolation rõ.

## 4. Cách ly theo JVM: Surefire forks và giới hạn của static cache

### 4.1. Fork không giống thread

`forkCount` của Maven Surefire điều khiển số **JVM processes** tối đa chạy tests. `reuseForks` quyết định có tái sử dụng JVM giữa test classes không.

Ví dụ minh họa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
```

Ý nghĩa:

- `forkCount=1,reuseForks=true`: thường một test JVM được dùng lại giữa test classes trong module; Spring context cache có cơ hội phát huy.
- `forkCount=2,reuseForks=true`: tối đa hai test JVMs song song; mỗi fork có **static fields/context cache riêng**.
- `forkCount=1,reuseForks=false`: tạo fork JVM mới cho từng test class, cách ly process tốt hơn nhưng đắt.
- `forkCount=0`: tests chạy trong Maven JVM, có trade-off riêng về isolation/classloading và performance.
- `reuseForks=false` không làm database/broker shared biến mất; nó chỉ giảm sharing trong **JVM state**.

Spring Context cache là một static cache trong **mỗi JVM**, không phân tán qua các forks. Vì thế context khởi động lại khi test suite chia ra nhiều processes; tăng forks có thể tăng số DB connections, containers, startup jobs.

### 4.2. Chạy từ Maven command line

```bash
# Một fork JVM (đúng cấu hình pom của bài mẫu):
mvn -B -ntp test

# Một JVM mới cho mỗi test class:
mvn -B -ntp -DforkCount=1 -DreuseForks=false test

# Tối đa 2 JVM fork đồng thời:
mvn -B -ntp -DforkCount=2 -DreuseForks=true test
```

Các tham số trên là Surefire user properties; test engine bên trong mỗi fork vẫn tuân cấu hình `junit-platform.properties`. **Hai JVM riêng không thể dùng `@ResourceLock` để khóa chung một database row**. Muốn đồng bộ xuyên process, phải dùng namespace riêng hoặc một cơ chế coordination bên ngoài JVM.

### 4.3. System properties, JVM locale, timezone, security providers

Những đối tượng process-wide:

- `System.getProperties()`/`System.setProperty(...)`.
- `TimeZone.setDefault(...)`, `Locale.setDefault(...)`.
- Static caches/singletons, JVM shutdown hooks.
- Testcontainers singleton objects và Spring static TestContext cache.
- Classloader-specific registries.
- Port assignments/cached DNS/SSL context ở nhiều thư viện.

Khi tests cùng JVM, sửa những state này mà không restore có thể ảnh hưởng tests khác. Khi nhiều forks, những state trong JVM tách nhau, nhưng **OS ports/filesystem và external services vẫn shared**.

### 4.4. Ví dụ quan sát PID và static state

```java
package com.example.isolab;

import java.util.UUID;

public class ProcessProbe {

    private static final String STARTUP_TOKEN =
            UUID.randomUUID().toString();

    public static void main(String[] args) {
        System.out.println("pid=" +
                ProcessHandle.current().pid());
        System.out.println("token=" + STARTUP_TOKEN);
    }
}
```

Sau khi build:

```bash
mvn -B -ntp -DskipTests package

java -cp target/classes com.example.isolab.ProcessProbe
java -cp target/classes com.example.isolab.ProcessProbe
```

Output format có dạng:

```text
pid=<OS-assigned process id>
token=<random UUID>
```

Hai lần gọi `java` khởi tạo JVM mới; PID/token khác nhau trong thực tế, nhưng **không hard-code số PID hoặc UUID**. Đây là minh họa process boundary, không phải một JUnit test. Không dùng kết quả ngẫu nhiên làm assertion tuyệt đối 100% độc nhất: uniqueness cần được thiết kế bằng UUID + constraints/namespace và xử lý collision theo policy khi có side effect quan trọng.

### 4.5. Dùng fork nhiều có thể làm suite tệ hơn

- Mỗi fork có thể nạp Spring context riêng, tăng RAM/CPU.
- Nếu mỗi fork start PostgreSQL/Rabbit containers, tăng áp lực Docker daemon/registry.
- Nếu mọi fork đều dùng cùng schema mà chạy `TRUNCATE tables` ở setup, tests có thể phá nhau.
- Static `@ResourceLock` và `@Isolated` chỉ hữu hiệu trong JUnit test plan tương ứng, **không xuyên forks**.
- `reuseForks=false` đôi khi che shared-static-state bug nhưng không giải quyết external race.
- Không dùng forks làm phương án chính để sửa test phụ thuộc dữ liệu production-like.

## 5. Cách ly tài nguyên ngoài: database, Redis, broker, file và HTTP

### 5.1. Những cách đạt isolation, từ mạnh đến yếu

| Chiến lược | Phạm vi | Ưu điểm | Trade-off |
| --- | --- | --- | --- |
| Container riêng mỗi test class | Broker/DB process/container | Không đụng dữ liệu class khác | Startup/RAM cao |
| Database/schema riêng mỗi worker | Namespace DB | Song song tốt, dễ cleanup | Cần cấp schema/migration riêng |
| Redis prefix/vhost/queue/topic riêng | Logical resource | Dùng chung service có kiểm soát | Cần kỷ luật naming + permission |
| UUID/request ID riêng mỗi test | Row/message/object | Nhẹ, không cần tạo database mới | Không cô lập global DDL/flush hoặc shared counters |
| Transaction rollback cho một test | Test-thread DB writes | Nhanh nếu thao tác cùng transaction | Không bao async threads/HTTP/REQUIRES_NEW/broker |
| Lock/serialization | Một shared resource | Giảm race khi không tách được | Tốc độ giảm, không chống cross-process nếu lock local |
| Chạy tuần tự toàn suite | Test plan | Dễ áp dụng tạm thời | Che phụ thuộc trạng thái và không chống CI forks/jobs |

**Ưu tiên:** Thiết kế tests dùng **unique resource namespace** và cleanup đúng owner; dùng transaction rollback đúng phạm vi; chỉ serialize khi isolation thực sự không thể làm được.

### 5.2. PostgreSQL: tránh `DELETE FROM table` không điều kiện

Anti-pattern:

```java
@BeforeEach
void reset() {
    jdbc.execute("TRUNCATE TABLE orders CASCADE");
}
```

Nếu Class A và Class B dùng chung database chạy parallel, Class A có thể truncate dữ liệu mà B vừa tạo. B thất bại dù business code đúng.

Tốt hơn:

```java
String id = "test-" + UUID.randomUUID();
service.create(id, "test-payload");
try {
    assertThat(service.exists(id)).isTrue();
}
finally {
    service.delete(id); // chỉ dữ liệu test này sở hữu
}
```

Trên database thật, dùng primary key/tenant key unique và xóa theo **đúng ID**, không global cleanup. Khi nhiều related tables, cleanup theo FK-aware strategy; an toàn hơn nữa là schema riêng cho mỗi CI worker.

Một `@Sql(scripts="cleanup.sql")` hay `@SqlConfig(transactionMode=ISOLATED)` có thể hữu ích nhưng phải hiểu nó chạy trong transaction nào. Script global truncate không trở nên parallel-safe chỉ vì được khai qua `@Sql`.

### 5.3. `@Transactional` trong tests: rollback có giới hạn

Spring TestContext với JUnit `@Transactional` method thường mở **test-managed transaction** trên test thread và rollback sau method:

```java
@Test
@Transactional
void insertsThenRollsBack() {
    notes.insert("unique-id", "alice", "hello");
    assertThat(notes.count("unique-id")).isEqualTo(1);
}
```

Khi test method xong, Spring rollback transaction mặc định. Nhưng:

- `@BeforeEach`/`@AfterEach` của **transactional test** thường chạy trong transaction ấy; `@BeforeAll`/`@AfterAll` không.
- `@Async`, scheduler, Rabbit/Kafka listeners và HTTP server request threads không tự tham gia test-managed transaction.
- Service dùng `REQUIRES_NEW` có thể commit ngoài transaction của test.
- `assertTimeoutPreemptively(...)` hoặc JUnit preemptive separate-thread timeout có thể chuyển test code sang thread khác, làm transaction không áp dụng.
- DB writes bên ngoài DataSource/transaction manager không rollback theo.
- Transaction không xóa object store, Redis keys hoặc broker messages.
- Một failed SQL statement có thể đánh dấu transaction rollback-only; test cleanup/queries sau đó cần thiết kế theo DB behavior.

**Không coi `@Transactional` là chiến lược cleanup duy nhất** cho workflow đa tài nguyên.

### 5.4. Kiểm tra rollback **sau** khi transaction kết thúc

Spring TestContext cung cấp `@AfterTransaction` để assert trạng thái database sau rollback/commit:

```java
@AfterTransaction
void afterTestTransaction() {
    // Đây là thời điểm test-managed transaction đã kết thúc
    // Có thể query DB để xác minh insert của test không tồn tại.
}
```

Ở project runnable có một test đi theo pattern này. Nó mạnh hơn chỉ nhìn kết quả trong transaction trước khi rollback, nhưng vẫn không chứng minh không có side effect trong broker/HTTP.

### 5.5. Redis: logical namespace và TTL

- Không dùng `FLUSHDB`/`FLUSHALL` trên Redis shared với test khác.
- Key nên có `app:testRunId:testId:tenantId:businessKey` hoặc namespace tương đương, tùy security contract.
- Cache prefix và tenant/user scope là hai yêu cầu khác nhau.
- Cleanup bằng key prefix **sở hữu riêng**, tránh dùng wildcard `KEYS *` trên cluster.
- Đừng tạo random prefix mỗi lần đọc mà không cùng cơ chế trong writer.
- TTL cho test entries giúp dọn rác nếu process crash, nhưng không thay explicit cleanup cho assertion isolation.
- Test TTL dùng bounded polling/Redis PTTL, không assert chính xác từng millisecond.
- Nếu test cache concurrent, tránh một test `cache.clear()` toàn cache của tenant khác.

### 5.6. RabbitMQ: queue/vhost/exchange và consumer cạnh tranh

Nếu hai consumer tests đọc cùng queue trên cùng broker, message của test A có thể được consumer B lấy trước. Test A timeout, test B nhận payload “sai”, rồi người viết test nghĩ routing bug.

Giải pháp:

- Queue/vhost namespace theo test class/job; kiểm tra broker policies cho tên động.
- Event ID/tenant ID độc nhất; consumer chỉ xử lý những events thuộc test.
- Khi cần kiểm tra routing, tạo binding riêng và đọc **đúng queue**.
- Không purge queue global trong `@BeforeEach`.
- Không dùng `RabbitTemplate.receiveAndConvert` của hai tests trên cùng queue song song nếu chúng muốn sở hữu message riêng.
- Publisher confirm, mandatory return và consumer ACK là những hợp đồng riêng; queue trống không chứng minh business side effect đã commit.
- Dead-letter queue/poison messages cũng phải có namespace và cleanup.

Với broker ephemeral container riêng class, có thể dùng tên cố định **trong container đó**; nếu dùng shared broker, phải dùng run-specific prefix. Không gửi message tới broker production.

### 5.7. Kafka: topic và consumer group

- Hai tests có cùng consumer group trên shared topic có thể bị rebalance/compete nhau.
- Dùng unique group ID/test namespace, isolate topics nếu phù hợp.
- Consumer offsets/retention tồn tại sau test và độc lập JVM process.
- Broker start/stop theo Testcontainers không có nghĩa consumer offset bị reset nếu state mount/cluster shared.
- Một test yêu cầu replay cần explicitly reset offset hoặc dùng new group ID, không dựa vào thứ tự class.
- Kafka embedded/broker containers có khác biệt semantics cần được ghi rõ.

### 5.8. Filesystem và object storage

- `@TempDir` cho file theo method, còn S3 bucket/object key phải có run namespace.
- Không dùng một filename như `output.csv` ở project root cho mọi test.
- Với filesystem cleanup, verify path nằm trong test-owned directory trước recursive delete.
- Nếu hai JVM cùng mount volume, local Java synchronized block không giải quyết collision.
- Dùng UUID-named directories và finally/teardown; TTL/lifecycle policy cho remote objects.
- Không xóa toàn bộ bucket để dọn một test.

### 5.9. HTTP stub và random ports

Dùng WireMock/MockWebServer/JDK HttpServer với port được chọn động:

```text
Test A: stub server at 127.0.0.1:<port-A>
Test B: stub server at 127.0.0.1:<port-B>
```

Không hard-code `8080`/`9999` khi chạy parallel. Nếu Spring context cache chứa HTTP client bean base URL cũ sau khi class A stop stub, class B có thể reuse stale client. Tách context đúng config, quản lý stub lifecycle theo context hoặc dùng `@DirtiesContext` có chủ đích và serialize những tests liên quan.

## 6. JUnit Jupiter parallel mode: bật đúng phạm vi, không phá isolation

### 6.1. Mặc định tuần tự, phải opt-in

JUnit Jupiter chạy tuần tự theo mặc định. Muốn song song phải bật:

```properties
junit.jupiter.execution.parallel.enabled=true
```

Nhưng chỉ bật flag đó **chưa chắc chạy methods đồng thời**. Còn phụ thuộc `mode.default`, `mode.classes.default` và `@Execution` annotations. Trong bài mẫu sẽ bật **classes concurrent**, methods mặc định same-thread, chỉ một vài pure unit classes opt-in concurrent.

### 6.2. Cấu hình cho mixed suite

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

Đây là một baseline thực dụng:

- Top-level test classes có thể chạy concurrent.
- Methods trong class mặc định chạy trên same thread theo cây thực thi của JUnit.
- Pure unit class có thể dùng `@Execution(CONCURRENT)` nếu không chia sẻ state.
- DB integration class dùng `@Isolated`/`@DirtiesContext` để tránh bị chạy đồng thời với classes khác trong cùng JUnit plan.
- JUnit fixed parallelism là mục tiêu concurrency level, không đảm bảo lúc nào đúng 4 threads đều active.
- Không giải quyết đồng bộ **giữa hai JVMs** do Maven forks.

### 6.3. `@ResourceLock` cho state trong JVM

Ví dụ hai tests thay System properties:

```java
@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyTest {

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void changesProperty() {
        String before = System.getProperty("lab.flag");
        try {
            System.setProperty("lab.flag", "on");
            assertThat(System.getProperty("lab.flag")).isEqualTo("on");
        }
        finally {
            if (before == null) {
                System.clearProperty("lab.flag");
            }
            else {
                System.setProperty("lab.flag", before);
            }
        }
    }
}
```

Đây là snippet; project runnable có class đầy đủ với hai methods và imports.

**Đặc tính:** `@ResourceLock` phối hợp các nodes JUnit tham gia cùng resource lock key trong test plan, kể cả lifecycle methods tương ứng. Nó không khóa process Java khác, OS file hoặc Redis global. Nếu một test khác không khai cùng lock mà cũng sửa property, lock không bảo vệ nó.

`ResourceAccessMode.READ` phù hợp cho multiple readers; `READ_WRITE` dành cho writer và ngăn conflicting operations trong engine. Tránh lạm dụng một lock global khiến cả suite bị serialize vô ích.

### 6.4. `@Isolated` ở test class

`@Isolated` của JUnit Jupiter ngăn class đó chạy song song với classes khác trong **cùng JUnit test plan**. Phù hợp khi class có Spring `@DirtiesContext` hoặc thay một shared resource khó cô lập.

Nhưng nó không có tác dụng lên **Maven Surefire fork khác** hoặc một CI job ở runner khác. Khi DB/broker shared giữa forks, cần external isolation hoặc phối hợp bên ngoài.

### 6.5. Cảnh báo với `@MockitoBean` và `@DirtiesContext`

Spring Framework 6.2 khuyến nghị tránh parallel tests dùng `@DirtiesContext`, bean overrides/mock hoặc làm thay đổi shared resources. Cấu hình JUnit classes concurrent **không có nghĩa mọi Spring Boot test class đều an toàn**. Chọn selective parallelism:

- Pure unit tests stateless: có thể chạy concurrent.
- JDBC tests dùng row namespaces: có thể parallel nếu connection/transaction/schema design đủ.
- Bean overrides hoặc dirty contexts: thường serialize.
- Shared broker queues, global DDL, scheduler startup: serialize hoặc refactor resource ownership.
- External cloud sandboxes: tách per-job namespace/account, không chỉ khóa trong JVM.

## 7. Testcontainers lifecycle và Spring context cache: một bẫy rất hay gặp

### 7.1. Static `@Container` sống theo test class

```java
@Testcontainers
@SpringBootTest
class PostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

JUnit Testcontainers extension start/stop static container theo **lifecycle test class**. Nhưng Spring TestContext có thể cache `ApplicationContext` tới sau class.

Ví dụ failure:

```text
Class A: starts container A → builds Spring context X → tests PASS
Class A ends: Testcontainers stops container A
Class B: context key matches → Spring reuses context X
Class B: DataSource still points to stopped container A → FAIL
```

**Quan trọng:** static field thuộc class không có nghĩa container tự sống đến hết JVM. Chính `@Container` lifecycle của Testcontainers extension quyết định stop sau class.

### 7.2. Ba chiến lược lifecycle có chủ đích

1. **Class-scoped container + `@DirtiesContext(AFTER_CLASS)`:** đơn giản khi một test class sở hữu container; đóng Spring context để không tái sử dụng stale DataSource.
2. **Spring-managed container bean:** khi context cần được cache qua nhiều test classes, để container lifecycle gắn với Spring context (theo Spring Boot `@ServiceConnection`/test configuration hỗ trợ).
3. **Suite-wide singleton container:** start thủ công, chia sẻ giữa classes và stop theo suite/JVM lifecycle; **không** vừa dùng singleton pattern vừa để `@Testcontainers @Container` extension stop sau mỗi class.

Chọn một cách; không trộn lifecycle ngầm. Testcontainers reusable containers không phải cách tự động sửa lỗi context cache, và không nên dùng với mandatory CI nếu cần môi trường sạch per job.

### 7.3. Spring Boot `@ServiceConnection` không tạo data isolation

`@ServiceConnection` làm connection details được suy ra từ container, tránh hard-code host/port/password. Nhưng hai tests dùng cùng `PostgreSQLContainer` vẫn có thể ghi cùng table/rows. Isolation dữ liệu là trách nhiệm riêng.

Test code nên assert record đúng ID, không “SELECT COUNT(*) FROM all_notes = 1” khi có thể có nhiều tests cùng insert.

## 8. Dự án Java 17 + Spring Boot 3.5.0 + PostgreSQL Testcontainers

Project hoàn chỉnh minh họa:

- `PER_METHOD` instance state và optional method-level parallel execution.
- `@TempDir` tạo filesystem scope theo method.
- `@ResourceLock` bảo vệ System properties trong JVM.
- Spring JDBC + Postgres real integration với unique rows/cleanup.
- `@Transactional` test rollback được xác nhận bằng `@AfterTransaction`.
- `@Isolated`/`@DirtiesContext` để giữ Testcontainers/context lifecycle đúng.
- Một chương trình Java `ProcessProbe` cho JVM boundaries.

**Tổng: 10 phương thức JUnit `@Test`** trong bốn test classes: 2 instance fields, 2 temp dirs, 2 JVM property resource locks, 4 DB integration. Không cần Redis, RabbitMQ, Kafka trong runnable sample; chúng được giải thích/đưa bài tập mở rộng theo đúng phạm vi tài nguyên ngoài.

### 8.1. Cấu trúc

```text
isolation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolab/
    │   │   ├── IsolationLabApplication.java
    │   │   ├── NoteService.java
    │   │   └── ProcessProbe.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        ├── resources/junit-platform.properties
        └── java/com/example/isolab/
            ├── MethodStateIsolationTest.java
            ├── TempDirectoryIsolationTest.java
            ├── SystemPropertyLockTest.java
            └── NoteStoreIntegrationTest.java
```

Mỗi `public` Java top-level class nằm trong file cùng tên, package `com.example.isolab`. Test source imports JUnit Jupiter 5/AssertJ và Spring Boot 3.5/Framework 6.2 đúng phiên bản.

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>isolation-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent quản lý versions tương thích; `spring-boot-starter-test` chứa Jupiter và AssertJ. Boot 3.5 BOM sử dụng Testcontainers 1.x, nên `org.testcontainers.containers.PostgreSQLContainer` và artifact `org.testcontainers:postgresql` là lựa chọn phù hợp; đừng trộn import/package từ Testcontainers 2.x nếu chưa thay BOM đồng bộ.

Không thêm một in-memory H2 rồi tuyên bố đã kiểm thử PostgreSQL transaction/constraints: integration test sử dụng PostgreSQL thật trong container.

### 8.3. `application.properties`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always
```

`spring.sql.init.mode=always` cho phép chạy `schema.sql` trên database không embedded trong lab. Không sử dụng kiểu khởi tạo này một cách vô điều kiện trên production DB; ứng dụng thực nên dùng Flyway/Liquibase migrations với scope môi trường rõ ràng.

### 8.4. `schema.sql`

```sql
-- src/main/resources/schema.sql
CREATE TABLE test_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    owner_id VARCHAR(80) NOT NULL,
    content VARCHAR(200) NOT NULL
);
```

Test cases tạo ID có prefix và UUID; mỗi test chỉ xóa row thuộc ID mình tạo. Nếu hai test classes/forks cùng dùng một database thực, việc có unique PK và scoped cleanup là điều kiện cần để tránh row collisions; schema-level migrations và unique constraints còn cần test isolation riêng.

### 8.5. `IsolationLabApplication.java`

```java
// src/main/java/com/example/isolab/IsolationLabApplication.java
package com.example.isolab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }
}
```

Spring Boot JDBC auto-configuration tạo `DataSource`/`JdbcTemplate` dựa trên PostgreSQL connection details từ test container.

### 8.6. `NoteService.java`

```java
// src/main/java/com/example/isolab/NoteService.java
package com.example.isolab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class NoteService {

    private final JdbcTemplate jdbc;

    public NoteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            String id, String owner, String content) {
        jdbc.update(
                "INSERT INTO test_notes"
                        + "(note_id,owner_id,content) "
                        + "VALUES (?,?,?)",
                id, owner, content);
    }

    public String content(String id) {
        return jdbc.queryForObject(
                "SELECT content FROM test_notes "
                        + "WHERE note_id = ?",
                String.class,
                id);
    }

    public int countById(String id) {
        Integer n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM test_notes "
                        + "WHERE note_id = ?",
                Integer.class,
                id);
        return n == null ? 0 : n;
    }

    public void delete(String id) {
        jdbc.update(
                "DELETE FROM test_notes WHERE note_id = ?",
                id);
    }
}
```

Service không chứa mutable instance counter; mỗi JDBC method dùng query theo **exact row ID**. Test-managed transaction dùng Spring `DataSourceTransactionManager` do Boot JDBC auto-configure; nếu test `@Transactional` gọi service trên same thread, `JdbcTemplate` tham gia cùng thread-bound transaction.

### 8.7. `ProcessProbe.java`

```java
// src/main/java/com/example/isolab/ProcessProbe.java
package com.example.isolab;

import java.util.UUID;

public class ProcessProbe {

    private static final String STARTUP_TOKEN =
            UUID.randomUUID().toString();

    public static void main(String[] args) {
        System.out.println("pid=" +
                ProcessHandle.current().pid());
        System.out.println("token=" + STARTUP_TOKEN);
    }
}
```

Đây là chương trình Java độc lập giúp quan sát boundary của static state/JVM. Nó không nằm trong 10 JUnit tests, vì test không nên phụ thuộc PID/UUID cụ thể.

### 8.8. `junit-platform.properties`

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

Những class có `@Execution(CONCURRENT)` sẽ chủ động chạy methods concurrent. Integration class dùng `@Isolated` để không chạy song song với test classes khác **trong cùng JUnit plan**. Việc fork JVM vẫn do Maven Surefire quyết định.

## 9. Pure JUnit method isolation tests

### 9.1. `MethodStateIsolationTest.java`

```java
// src/test/java/com/example/isolab/MethodStateIsolationTest.java
package com.example.isolab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
@Execution(ExecutionMode.CONCURRENT)
class MethodStateIsolationTest {

    private final List<String> ownValues =
            new ArrayList<>();

    @Test
    void firstMethodOwnsIndependentList() {
        assertThat(ownValues).isEmpty();
        ownValues.add("first");
        assertThat(ownValues).containsExactly("first");
    }

    @Test
    void secondMethodOwnsIndependentList() {
        assertThat(ownValues).isEmpty();
        ownValues.add("second");
        assertThat(ownValues).containsExactly("second");
    }
}
```

**2 methods.** Vì `PER_METHOD` tạo test class instance mới, mỗi method dùng một `ArrayList` riêng. Dù JUnit chạy concurrent theo annotation, chúng không mutate cùng object.

**Không được thay bằng `static final List<String> ownValues`.** Nếu dùng static list, mỗi method cùng thay global state và test không còn độc lập. Một `final` trên reference không làm ArrayList trở thành immutable/thread-safe.

### 9.2. `TempDirectoryIsolationTest.java`

```java
// src/test/java/com/example/isolab/TempDirectoryIsolationTest.java
package com.example.isolab;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class TempDirectoryIsolationTest {

    @Test
    void firstReportIsWrittenInOwnDirectory(
            @TempDir Path dir) throws IOException {
        Path report = dir.resolve("report.txt");

        assertThat(Files.exists(report)).isFalse();
        Files.writeString(report, "report-one");

        assertThat(Files.readString(report))
                .isEqualTo("report-one");
    }

    @Test
    void secondReportIsIndependent(
            @TempDir Path dir) throws IOException {
        Path report = dir.resolve("report.txt");

        assertThat(Files.exists(report)).isFalse();
        Files.writeString(report, "report-two");

        assertThat(Files.readString(report))
                .isEqualTo("report-two");
    }
}
```

**2 methods.** Cả hai cùng dùng tên `report.txt` nhưng trong hai `@TempDir` scopes riêng, không clobber tệp của nhau. Đây là test isolation nhờ **resource naming**, không chỉ nhờ Java object instance.

JUnit quản lý lifecycle temporary folders. Với remote object store, cần tự thiết kế unique prefix/bucket scope và cleanup.

## 10. JVM-global state: khóa có chủ đích

### 10.1. `SystemPropertyLockTest.java`

```java
// src/test/java/com/example/isolab/SystemPropertyLockTest.java
package com.example.isolab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyLockTest {

    private static final String KEY =
            "isolation.lab.mode";

    private void withProperty(String expected) {
        String previous = System.getProperty(KEY);
        try {
            System.setProperty(KEY, expected);
            assertThat(System.getProperty(KEY))
                    .isEqualTo(expected);
        }
        finally {
            if (previous == null) {
                System.clearProperty(KEY);
            }
            else {
                System.setProperty(KEY, previous);
            }
        }
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void writerOneRestoresGlobalState() {
        withProperty("one");
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void writerTwoRestoresGlobalState() {
        withProperty("two");
    }
}
```

**2 methods.** `@ResourceLock` ngăn hai writers tham gia cùng JUnit lock chạy chồng nhau trên `System.properties`. `finally` trả lại previous value kể cả assertion fail. Đây là một lựa chọn khi state global **không tránh được**, không phải pattern khuyến khích thay System properties ở mọi unit test.

**Giới hạn quan trọng:**

- Lock chỉ phối hợp các tests khai đúng resource key trong **cùng test plan/engine**.
- Không bảo vệ code production thread hoặc unannotated test tự ý sửa property.
- Không bảo vệ giữa các Maven Surefire forks/JVMs; mỗi fork có bộ System properties riêng.
- Không khóa shared DB hoặc external broker.
- Nếu test ghi environment variable của OS process khác, Java ResourceLock không bảo vệ.
- Nếu test cần thay global timezone/locale/security provider, phải restore và khai resource lock riêng được toàn suite thống nhất.

## 11. PostgreSQL integration: row ownership, transaction và context lifetime

### 11.1. `NoteStoreIntegrationTest.java`

```java
// src/test/java/com/example/isolab/NoteStoreIntegrationTest.java
package com.example.isolab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Isolated
@Testcontainers
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class NoteStoreIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    NoteService notes;

    // Mỗi JUnit test method có test object riêng:
    private String ownedId;
    private String rolledBackId;

    private static String nextId() {
        return "test-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOnlyMyCommittedRow() {
        if (ownedId != null) {
            notes.delete(ownedId);
        }
    }

    @AfterTransaction
    void verifyRollbackAfterTransactionalTest() {
        if (rolledBackId != null) {
            assertThat(notes.countById(rolledBackId))
                    .isZero();
        }
    }

    @Test
    void firstMethodOwnsAUniqueCommittedRow() {
        ownedId = nextId();

        notes.insert(ownedId, "team-a", "first");

        assertThat(notes.countById(ownedId))
                .isEqualTo(1);
        assertThat(notes.content(ownedId))
                .isEqualTo("first");
    }

    @Test
    void secondMethodDoesNotDependOnFirst() {
        ownedId = nextId();

        notes.insert(ownedId, "team-b", "second");

        assertThat(notes.countById(ownedId))
                .isEqualTo(1);
        assertThat(notes.content(ownedId))
                .isEqualTo("second");
    }

    @Test
    @Transactional
    void insertionIsRolledBackBySpringTest() {
        rolledBackId = nextId();

        notes.insert(rolledBackId, "team-c", "tx");

        // Cùng test thread: thấy insert trong transaction.
        assertThat(notes.countById(rolledBackId))
                .isEqualTo(1);
        // Sau rollback, @AfterTransaction kiểm tra không còn row.
    }

    @Test
    void duplicateIdFailsWithoutOverwritingOwnedRow() {
        ownedId = nextId();

        notes.insert(ownedId, "team-d", "original");

        assertThatThrownBy(() ->
                notes.insert(ownedId, "team-e", "duplicate"))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(notes.content(ownedId))
                .isEqualTo("original");
    }
}
```

**4 integration methods** cùng Spring context và PostgreSQL container test-class-scoped:

- Mỗi method có UUID record ID, không dựa vào row của method trước.
- Hai nontransaction methods tạo committed rows và `@AfterEach` xóa **đúng ownedId**.
- Transaction method tạo một ID riêng và không gán `ownedId`; Spring tự rollback sau test method. `@AfterTransaction` query DB **sau rollback** để chứng minh row không tồn tại.
- Duplicate-key test chứng minh database thực bảo vệ primary key; không âm thầm overwrite.
- `@Isolated` ngăn class chạy song song với JUnit classes khác trong cùng test plan, vì nó dùng `@DirtiesContext` và class-scoped container lifecycle.
- `@DirtiesContext(AFTER_CLASS)` đóng Spring context khi class kết thúc để không reuse datasource tới stopped container.
- `@ServiceConnection` cung cấp mapped PostgreSQL JDBC connection details, không hard-code `localhost:5432`.

**Giới hạn:** Sample không chạy concurrent DB test methods vì Spring TestContext/`@DirtiesContext`/Testcontainers class lifecycle cần kiểm soát. Isolation bằng unique rows trong DB hỗ trợ refactor để parallelize an toàn, nhưng **chưa chứng minh toàn bộ class parallel-safe** khi có DDL, integration setup hay backend concurrency.

### 11.2. Vì sao không dùng `@BeforeEach DELETE FROM test_notes`?

Hai methods A/B có thể chạy đồng thời hoặc hai forks dùng chung DB. Nếu A setup xóa tất cả notes ngay sau khi B vừa insert fixture, B sẽ fail. Trong project, cleanup có điều kiện `ownedId != null` và `WHERE note_id = ?`; transaction method cleanup bằng rollback.

Nếu test suite dùng schema riêng per class, có thể reset schema trong ownership boundary đó, nhưng không có quyền global truncate database của CI job khác.

### 11.3. Vì sao `@Transactional` không đủ cho mọi test?

Ở method `insertionIsRolledBackBySpringTest`, SQL chạy trực tiếp trên **same thread**, cùng Spring test-managed transaction, nên rollback khả thi. Nhưng nếu method gọi:

```java
CompletableFuture.runAsync(() ->
        notes.insert("async-row", "x", "y")).join();
```

thì INSERT thực hiện ở thread khác, không tự nhận test transaction. Tương tự một real HTTP request vào `@SpringBootTest(webEnvironment=RANDOM_PORT)` chạy trên server thread, không rollback theo transaction của test client thread.

Đoạn trên là snippet **cố tình rủi ro**, không thuộc runnable test project. Khi cần test side effect async, dùng unique IDs, bounded wait và explicit test cleanup; không tin vào rollback của method cha.

### 11.4. Với JPA cần flush

Nếu dùng Spring Data JPA thay JdbcTemplate, `save()` có thể chưa gửi SQL cho database đến khi flush/commit. Một test assert in-memory entity rồi rollback có thể xanh giả dù constraint sai. Trong test cần `entityManager.flush()` hoặc repository `saveAndFlush()` khi muốn kiểm tra constraint thực; với `@AfterTransaction` còn cần biết transaction propagation phù hợp.

## 12. Chạy project, xác nhận tổng test count và JVM forks

### 12.1. Thứ tự thực hiện

```bash
java -version
mvn -version

# Pure unit JUnit tests, không cần Docker:
mvn -B -ntp -Dtest=MethodStateIsolationTest,TempDirectoryIsolationTest,SystemPropertyLockTest test

# Chạy PostgreSQL Testcontainers integration:
docker version
docker info
mvn -B -ntp -Dtest=NoteStoreIntegrationTest test

# Toàn bộ suite (10 JUnit methods):
mvn -B -ntp test

# Thử một fork khác cho từng test class:
mvn -B -ntp -DforkCount=1 -DreuseForks=false test
```

Khi đổi fork options, database integration test sẽ có một PostgreSQL container được khởi động trong fork chạy class đó. Nếu project thực có nhiều classes dùng shared broker/DB, fork-per-class chỉ thay JVM state; external isolation vẫn cần bảo đảm.

| Test class | `@Test` methods | Test scope | Có Docker? |
| --- | ---: | --- | --- |
| `MethodStateIsolationTest` | 2 | JUnit PER_METHOD, concurrent | Không |
| `TempDirectoryIsolationTest` | 2 | Filesystem @TempDir, concurrent | Không |
| `SystemPropertyLockTest` | 2 | System properties lock, JVM | Không |
| `NoteStoreIntegrationTest` | 4 | Spring/Postgres, isolated class | Có |
| **Tổng** | **10** | Bốn tầng isolation | Full suite có |

Các lệnh là hướng dẫn để người học **tự chạy**, không tuyên bố source đã được compile/test thực tế trong môi trường soạn bài. Stdout của Maven, PID, UUID, Docker container ID và startup time phụ thuộc host.

### 12.2. Đọc logs đúng mục tiêu

- JUnit/Surefire reports: `target/surefire-reports`.
- Spring context cache DEBUG: cấu hình `logging.level.org.springframework.test.context.cache=DEBUG` trong test env khi điều tra reuse/cost, tránh bật ồn ào vô thời hạn.
- Testcontainers logs: quan sát container start/stop, mapped ports.
- PostgreSQL: test-owned schema/rows; không print credentials.
- Maven fork count/process ID: cần phân biệt hai forks với hai threads cùng JVM.
- Đừng dựa vào thứ tự console log của concurrent tests để suy luận data integrity.

### 12.3. Cấu hình một bài chạy tuần tự để chẩn đoán

```bash
# Ví dụ override cấu hình JUnit Jupiter khi cần so sánh:
mvn -B -ntp -Djunit.jupiter.execution.parallel.enabled=false test
```

Nếu một test xanh khi parallel disabled nhưng đỏ khi enabled, nghi ngờ shared state/race. Nhưng “tắt parallel thì xanh” không phải sửa nguyên nhân. Điều tra lớp state, test fixture ownership, resource lock, container/cache lifecycle và transactional boundaries.

Với một số build/test engines, system-property override có thể cần cấu hình `configurationParameters` trong Surefire hoặc test resources cho phù hợp; hãy xác nhận JUnit thực sự nhận override, không suy từ command line.

## 13. Cách phân biệt một test “pass vì may mắn” với independent test

### 13.1. Test chạy theo thứ tự ngẫu nhiên

Một test phụ thuộc `@TestMethodOrder` để tạo state cho method sau không độc lập. Kiểm tra:

- Chạy method riêng qua `-Dtest=Class#method`.
- Chạy class riêng.
- Chạy toàn module.
- Đổi order (JUnit class/method order random) và nhiều seeds.
- Bật/tắt concurrency với phạm vi an toàn.
- Thay fork count.
- Chạy trên fresh CI runner.

Nếu test chỉ pass sau một test khác, đó thường là thiếu setup hoặc state leak.

### 13.2. Repeat có kiểm soát

Một flaky test có thể xanh 99 lần và đỏ 1 lần, do race cửa sổ ngắn. Chạy lặp ở CI test environment, lưu seed/stacktrace/timestamps khi fail, không đặt `Thread.sleep(500)` làm thuốc chữa chung.

### 13.3. Assert tín hiệu cụ thể, không assert shared global counter

Với message broker:

```text
Tốt: receive event có eventId được tạo bởi test này, đúng queue/vhost.
Yếu: queue depth tăng từ 0 thành 1 trên broker dùng chung.
Sai: dùng sleep 3s rồi assert "đã có message bất kỳ".
```

Với database:

```text
Tốt: SELECT ... WHERE id = :uniqueTestId
Yếu: SELECT COUNT(*) FROM orders = 1 trên schema shared
Sai: TRUNCATE orders trước mỗi test mà không có ownership
```

Với filesystem:

```text
Tốt: @TempDir / unique path per method
Yếu: ./target/output.json của tất cả test classes
Sai: xóa toàn bộ shared folder sau mỗi method
```

### 13.4. Kiểm tra cleanup thật

Một test có `@AfterEach` nhưng cleanup fail có thể làm test kế tiếp nhiễm state. Dùng `try/finally` cho tài nguyên tạo thủ công, assert cleanup ở những nơi cần guarantee, và log rõ resource ID/namespace (không lộ credentials).

Cleanup nên **idempotent**: gọi lại không phá dữ liệu khác. Khi resource owner không rõ hoặc cleanup thất bại, báo lỗi thực tế; không xóa rộng hơn để “cho sạch”.

## 14. Case studies: tại sao “run individually PASS, run all FAIL”?

### 14.1. Redis flush phá class khác

Class A gọi `FLUSHDB` để reset cache; Class B đang kiểm tra TTL trên cùng Redis DB. B fail vì key mất trước expiration.

**Cách sửa:** Testcontainers Redis riêng mỗi class hoặc unique app/run namespace, cleanup scoped key; không dùng global flush.

### 14.2. RabbitMQ queue bị “đánh cắp” message

Class A gửi payload tới `test.orders`; Class B cũng có listener cùng queue. A đợi message mà B đã consume. Tăng timeout không giải quyết routing cạnh tranh.

**Cách sửa:** Queue/vhost riêng, event correlation ID, hoặc tách tests consumer/routing theo ownership.

### 14.3. Spring singleton bị sửa trong class trước

Class A test thay `@Service` mutable field qua setter. Class B dùng cùng cached Spring context nên thấy field bị thay dù B có test instance mới.

**Cách sửa:** Thiết kế bean immutable/stateless, reset state có chủ đích, tách config/context nếu thực sự cần và không chạy song song với `@DirtiesContext`.

### 14.4. Static Testcontainers stop nhưng Spring cache reuse

Class A dừng `@Container` sau class. Class B Spring TestContext reuse context A nên DataSource trỏ port cũ. B fail connection refused ngay lúc query.

**Cách sửa:** Match lifetimes (class-scoped + dirty context, context-managed container bean hoặc suite singleton container start thủ công).

### 14.5. Hai JVMs cùng hard-code TCP port

Surefire `forkCount=2` và hai tests khởi động HTTP stub ở `localhost:9999`. Một JVM gặp bind error dù unit logic đúng.

**Cách sửa:** Port 0/dynamic URL, quản lý process lifecycle.

### 14.6. Hai jobs cùng xóa S3 bucket test

Mỗi CI job có JVM riêng và `@Isolated` nhưng cùng bucket `shared-test-bucket`. Job A teardown xóa objects của Job B.

**Cách sửa:** CI run ID prefix, IAM scoped policies, deletion chỉ theo owned prefix, không dùng global bucket cleanup.

### 14.7. Preemptive timeout làm transaction leak

JUnit method có `@Transactional` nhưng `assertTimeoutPreemptively(...)` chạy JDBC code trên thread khác; dữ liệu có thể commit ngoài test transaction.

**Cách sửa:** Bounded async logic với cleanup rõ; dùng `assertTimeout(...)` hoặc thread mode phù hợp khi cần test-managed transaction, hiểu semantics của test framework.

### 14.8. Parallel test với `@MockitoBean`

Hai methods share mock trong cached context. Method A đang verify call count, Method B `reset` hoặc stub khác. Test có thể fail không xác định.

**Cách sửa:** Serialize những methods/classes đó hoặc refactor sang pure unit mocks per method; không giả định Spring cache tự tạo mock riêng cho mỗi test object.

## 15. CI/CD: thiết kế test workers không giẫm lên nhau

### 15.1. Run ID + worker ID + test ID

Một pattern cho external names:

```text
runId     = CI_PIPELINE_ID / GitHub run_id hoặc UUID
workerId  = shard/fork/agent ID
testId    = UUID per method

postgres schema:   t_<runId>_<workerId>
redis key prefix:  it:<runId>:<workerId>:<testId>:
rabbit queue:      it.<runId>.<workerId>.<testId>.orders
kafka group:       it-<runId>-<workerId>-<testId>
s3 object prefix:  tests/<runId>/<workerId>/<testId>/
```

Ở code thực, normalize IDs theo naming rules/length limits và quyền của từng service. Đừng đưa full secrets, usernames, email hoặc access tokens vào resource names vì chúng có thể hiện trong logs/metrics.

Nếu dùng nhiều forks Maven, có thể truyền `${surefire.forkNumber}` qua Surefire system properties/argLine để tạo prefix riêng theo fork; `${surefire.forkNumber}` chỉ hữu ích khi plugin đang quản lý fork và không tự động cô lập mọi resources nếu app bỏ qua prefix.

### 15.2. CI runner resource budget

- `forkCount=N` × Spring contexts × DB pools có thể tạo rất nhiều connections.
- PostgreSQL container + JVM + Kafka/Rabbit VM có memory/CPU footprint đáng kể.
- Nhiều test classes cùng pull images có thể làm Docker daemon chậm.
- Testcontainers Ryuk/cleanup cần phù hợp quyền Docker API.
- Một test suite bị timeout vì môi trường quá tải không phải bằng chứng business isolation sai.
- Ưu tiên cap concurrency theo RAM/CPU/DB max connections, không chỉ theo số core.
- Test dùng external partner sandbox phải có rate limits và request budgets, không chạy 100 parallel calls vô điều kiện.

### 15.3. GitHub Actions minh họa

```yaml
name: Isolation Lab

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

Cấu hình này dùng Docker daemon của runner để khởi động PostgreSQL Testcontainers. Không hard-code mapped port hoặc thao tác shared production DB. Với untrusted PR, không mount privileged Docker socket dùng chung secrets nếu chưa có isolation policy.

Cần báo rõ UNIT PASS / INTEGRATION PASS / ENVIRONMENT FAILURE / SKIPPED; nếu Docker không available mà integration test bắt buộc bị bỏ qua, không được tự gọi toàn suite “PASS”.

### 15.4. Multi-module build, Maven `-T` và CI matrix

Cần phân biệt ba mức concurrency khác nhau:

1. **JUnit threads** trong một JVM/test engine.
2. **Maven Surefire JVM forks** trong một module.
3. **Maven -T parallel modules / CI jobs** trong nhiều processes/containers.

Một `@ResourceLock("database")` ở module A **không đồng bộ** với module B chạy JVM khác. Một static lock cũng không chống hai CI jobs cùng namespace. Đây là lý do các external resource names cần chứa run/shard scope và cleanup theo owner.

### 15.5. Test data tenancy và authorization

Khi dùng multi-tenant database, fixture ID ngẫu nhiên chưa đủ nếu query bỏ tenant filter. Cần unique tenant IDs/row-level security test fixtures và test cross-tenant isolation. Một test A không được xóa tất cả data tenant B bằng `DELETE ... WHERE tenant_id != ?` sai. Cách ly test resources và tenant authorization là những ranh giới khác nhau.

## 16. Anti-patterns cần tránh

| Anti-pattern | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Test method B đọc data từ method A | Thứ tự ẩn | Setup riêng, independent fixtures |
| `@TestMethodOrder` để ép pass | Che phụ thuộc | Refactor test contracts |
| `static Map` làm state fixture | Shared JVM | Instance-local state/immutable |
| `@TestInstance(PER_CLASS)` + mutable field không reset | Shared test object | PER_METHOD hoặc setup/locking |
| `@BeforeEach TRUNCATE` shared DB | Xóa test khác | Unique rows/schemas |
| `@AfterEach cache.clear()` shared Redis | Xóa entries test khác | Namespace-scoped eviction |
| `@TempDir` không dùng, ghi file cố định | Port/path collisions | Unique directory/path |
| Hard-code port 8080/5432/5672 | Collision/mapped-port sai | Random port/service connection |
| `@DirtiesContext` cho mọi test | Chậm, hazards khi parallel | Scoped state reset |
| `@MockitoBean` test concurrent reset mock | Stubbing races | Serialize or pure unit |
| `@Transactional` rollback mọi side effects | Thread/broker khác | Explicit cleanup/idempotency |
| `assertTimeoutPreemptively` trong test transaction | Thread-bound tx bị bypass | Same-thread deadline strategy |
| `@ResourceLock` mong khóa xuyên JVM | Chỉ JUnit engine | External coordination/namespaces |
| `@Isolated` mong khóa giữa CI jobs | Test plan scope | Per-job resources |
| Reuse Spring context với stopped Testcontainers | Connection refused | Align lifetimes |
| Reuse containers vô hạn trong CI | Rò fixture, stale state | Managed lifecycle, cleanup |
| Kiểm tra total table row count=1 | Shared data làm race | WHERE unique test ID |
| Fixed `Thread.sleep` cho async | Timing flaky | Bounded latches/await |
| Drop DB/bucket shared trong teardown | Phá tài nguyên ngoài phạm vi | Owner-only cleanup |
| “No Docker” được tính pass integration | False PASS | Environment failure explicit |

## 17. Bài tập thực hành

**Bài 1 — Phá `PER_METHOD` có kiểm soát.** Đổi `ownValues` thành static trong `MethodStateIsolationTest` và bật parallel. Quan sát các race/cross-test contamination. Sửa lại bằng instance field, không dựa vào thứ tự chạy.

**Bài 2 — `PER_CLASS`.** Dùng `@TestInstance(PER_CLASS)` trong một class demo khác. Tạo mutable counter rồi xác định cần reset ở đâu và vì sao concurrent methods phải có synchronization/ownership.

**Bài 3 — TempDir.** Thay `@TempDir` bằng `Path.of("target/report.txt")`, chạy tests concurrent, đánh giá data races. Khôi phục per-method temp directories.

**Bài 4 — System properties.** Bỏ `@ResourceLock` giữa hai tests sửa `isolation.lab.mode`, chạy stress; giải thích vì sao restore trong finally vẫn chưa đủ nếu cả hai threads cùng thay property.

**Bài 5 — Spring context cache.** Tạo hai `@SpringBootTest` classes có cùng context configuration, inject singleton bean với mutable field. Xác minh state có thể tồn tại giữa classes; không cho tests phụ thuộc vào chuyện test nào chạy trước.

**Bài 6 — Context lifetime.** Tạo thêm một test class dùng Spring context nhưng không quản lý PostgreSQL container. Quan sát lỗi reuse stale connection nếu class-scoped container đã stop. Chuyển sang container context-managed hoặc dùng `@DirtiesContext(AFTER_CLASS)` đúng chỗ.

**Bài 7 — Transaction rollback.** Chạy `NoteStoreIntegrationTest`, xác minh `@AfterTransaction` nhìn thấy row đã biến mất. Tạo thử một `CompletableFuture` ghi ngoài thread và thiết kế cleanup đúng.

**Bài 8 — Database collision.** Cho hai test methods dùng cùng `note_id="fixed-id"`, rồi chạy parallel; giải thích unique PK violation là dấu hiệu fixture collision, không phải business bug.

**Bài 9 — JVM forks.** So sánh `forkCount=1,reuseForks=true` với `forkCount=1,reuseForks=false` và `forkCount=2`. Quan sát PID/context startup count, giải thích vì sao static state được tách nhưng external resources không.

**Bài 10 — Redis cache.** Tạo hai tests cùng cache keys trên shared Redis, rồi thêm unique namespace; so sánh scoped delete với `FLUSHDB`.

**Bài 11 — RabbitMQ queue.** Tạo hai consumers trên cùng queue và chứng minh competing consumers có thể nhận events khác với kỳ vọng. Đổi sang test-specific queues/IDs.

**Bài 12 — CI shards.** Tạo naming scheme theo runId/shardId/testId, thử hai CI jobs song song và kiểm tra teardown không xóa objects của job khác.

## 18. Câu hỏi tự kiểm tra

**1.** JUnit Jupiter mặc định tạo test instance mới cho từng method không?  
**Đáp án:** Có, `PER_METHOD` mặc định (trừ khi config override).

**2.** `PER_METHOD` có tách static fields không?  
**Đáp án:** Không. Static state dùng chung classloader/JVM.

**3.** Hai Spring test classes có thể dùng chung singleton bean không?  
**Đáp án:** Có, nếu Spring TestContext cache reuse cùng ApplicationContext.

**4.** Hai `ApplicationContext` khác nhau có chắc dùng database riêng không?  
**Đáp án:** Không, connection details có thể trỏ cùng DB.

**5.** `@DirtiesContext` có xóa Redis/DB rows không?  
**Đáp án:** Không. Nó đánh dấu/đóng/reload Spring context.

**6.** `@ResourceLock` có khóa test trong hai Surefire JVM forks không?  
**Đáp án:** Không. Nó phối hợp trong phạm vi JUnit test plan/engine tương ứng.

**7.** `@Isolated` có chặn một CI job khác đang ghi cùng bucket không?  
**Đáp án:** Không.

**8.** `@Transactional` test có rollback commit từ `@Async` thread không?  
**Đáp án:** Không tự động, transaction state thường bound với test thread.

**9.** Vì sao `assertTimeoutPreemptively` nguy hiểm trong transactional test?  
**Đáp án:** Nó chạy code ở thread khác, có thể không tham gia test-managed transaction.

**10.** Vì sao static `@Container` có thể tạo stale datasource khi class sau reuse Spring context?  
**Đáp án:** JUnit extension stop container sau class nhưng Spring context có thể còn trong cache.

**11.** Nên dọn database rows theo ID riêng hay `TRUNCATE` global?  
**Đáp án:** Theo ID/namespace sở hữu riêng, nhất là khi parallel.

**12.** Nếu hai JVM có static state riêng thì RabbitMQ queue có được tách không?  
**Đáp án:** Không; đó là external resource và cần namespace/vhost/queue riêng.

**13.** JUnit parallel enabled có tự làm mọi tests chạy concurrent không?  
**Đáp án:** Không; execution mode/classes mode và annotations quyết định.

**14.** Đâu là bằng chứng mạnh nhất một test độc lập?  
**Đáp án:** Chạy riêng và trong suite dưới nhiều orders/concurrency/forks, cùng kết quả, với fixtures/cleanup scope đúng và không dựa vào test khác.

## 19. Checklist review isolation và parallel execution

- [ ] Mỗi test method tự thiết lập prerequisites, không dùng kết quả method trước.
- [ ] Test instance lifecycle rõ ràng: PER_METHOD/PER_CLASS.
- [ ] Mutable static state không dùng làm fixture ngầm.
- [ ] Spring singleton beans stateless/thread-safe hoặc có reset/ownership.
- [ ] Context cache key và active profiles/properties được hiểu đúng.
- [ ] `@DirtiesContext`/`@MockitoBean` tests không chạy parallel thiếu kiểm soát.
- [ ] Spring-managed transaction rollback chỉ được dùng trong đúng thread/propagation scope.
- [ ] Không dùng preemptive timeout trong transactional test nếu không hiểu thread semantics.
- [ ] Database fixtures có unique IDs/tenant scope và cleanup theo owner.
- [ ] Không global TRUNCATE/FLUSHDB/PURGE trên shared external resources.
- [ ] Redis prefix, broker vhost/queue, Kafka topic/group, object storage prefix có namespace riêng.
- [ ] Random ports hoặc Boot/Testcontainers `@ServiceConnection`, không hard-code localhost mapped ports.
- [ ] Temp files dùng `@TempDir` hoặc unique path.
- [ ] System properties/TimeZone/Locale modifications được restore và synchronized phù hợp.
- [ ] `@ResourceLock` không bị hiểu nhầm là distributed lock.
- [ ] `@Isolated` không bị hiểu nhầm là fork/CI job isolation.
- [ ] Maven Surefire `forkCount`/`reuseForks` và JUnit parallel modes được cấu hình có chủ đích.
- [ ] Spring Context cache lifetime khớp Testcontainers container lifetime.
- [ ] Testcontainers extensions không bị trộn với singleton container pattern sai lifecycle.
- [ ] CI run/shard identifiers được dùng cho external namespaces khi cần.
- [ ] Cleanup có `try/finally`/teardown đúng scope và không phá test khác.
- [ ] Async/background tasks được stop hoặc await bounded trước cleanup.
- [ ] Test count/skips/environment errors rõ ràng; không claim integration PASS khi Docker thiếu.
- [ ] Tests được chạy trong nhiều orders/shards khi điều tra flaky behavior.

## 20. Tài liệu chính thức

- [JUnit Jupiter 5.12 — Test Instance Lifecycle & Parallel Execution](https://docs.junit.org/5.12.0/user-guide/): `PER_METHOD`/`PER_CLASS`, parallel config, `@ResourceLock`, `@Isolated` và `@TempDir`.
- [Spring Framework 6.2 — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache theo context configuration, per JVM và `@DirtiesContext`.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): các trường hợp cần tránh parallel.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): rollback thread-bound và preemptive timeout warning.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): context lifecycle.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, context configuration.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và container lifecycle.
- [Testcontainers — Container Lifecycle Management](https://testcontainers.com/guides/testcontainers-container-lifecycle/): class scoped vs singleton vs cached Spring context.
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` static vs instance lifecycle.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): real PostgreSQL isolation tests.
- [Apache Maven Surefire — Fork Options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options.html): `forkCount` và `reuseForks`.
- [Apache Maven Surefire — Plugin Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo): user properties và fork behavior.
- [Spring Framework 6.2 — Bean Overrides in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): mocks, spies, context customization.
- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): `@Sql` và transactional modes.

**Kết luận:** Test độc lập không chỉ là “mỗi `@Test` có object mới”. Cần phân biệt instance fields, cached Spring context, static state trong mỗi JVM và tài nguyên ngoài được chia sẻ xuyên processes. Chọn unique test data/resources, ownership-based cleanup, transaction rollback trong đúng thread, selective parallelism và aligned Testcontainers/context lifecycle. `@ResourceLock` và `@Isolated` hữu ích trong phạm vi JUnit, nhưng không thể thay namespace hoặc locking bên ngoài cho hai JVM/CI jobs.