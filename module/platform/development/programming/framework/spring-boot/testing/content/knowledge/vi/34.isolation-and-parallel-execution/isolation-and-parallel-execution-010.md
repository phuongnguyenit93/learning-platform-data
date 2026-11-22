# Phát hiện test phụ thuộc thứ tự hoặc dữ liệu còn sót

Một bài test Spring Boot có thể **PASS khi chạy riêng nhưng FAIL khi chạy cả suite**, **PASS trên máy cá nhân nhưng flaky trên CI**, hoặc thay đổi kết quả khi JUnit chạy các test theo thứ tự khác. Nguyên nhân phổ biến không phải do assertions sai cú pháp, mà là **một test phụ thuộc vào trạng thái do test khác tạo ra**: hàng dữ liệu còn trong DB, singleton Spring bean chưa reset, static collection, system property, file tạm, mock stubbing, message chưa consume, clock hoặc task bất đồng bộ chưa hoàn tất.

Chủ đề của bài là **“Phát hiện test phụ thuộc thứ tự hoặc dữ liệu còn sót”**, thuộc nhóm **Cách ly và chạy song song** của **Spring Boot - testing**. Mục tiêu không chỉ là làm test xanh, mà là **chứng minh test độc lập, tái lập được, chạy lặp lại được và không phá dữ liệu của test khác**. Bài bao gồm triệu chứng, các cơ chế gây leak, cách phát hiện có thể tái lập với JUnit 5/Jupiter, phân biệt ngẫu nhiên thứ tự và concurrency, chiến lược setup/teardown, Spring TestContext cache, `@Transactional`/`@DirtiesContext`, trường hợp `REQUIRES_NEW` hoặc worker thread thoát khỏi rollback và một project **Java 17 + Spring Boot 3.5 + H2 JDBC + JUnit Jupiter** với test runnable.

> **Quy tắc nền tảng:** một test phải tự thiết lập mọi tiền điều kiện, chỉ assert trên dữ liệu thuộc quyền kiểm soát của nó, và dọn side effects trong phạm vi chính nó. Chạy test bằng `@Order` để nó xanh **không** đồng nghĩa đã sửa được phụ thuộc thứ tự.

## 1. Nhận diện triệu chứng của order-dependent tests

### 1.1. Những biểu hiện hay gặp

- Chạy `mvn -Dtest=OrderServiceTest test` PASS, chạy `mvn test` FAIL.
- Test A PASS nếu chạy trước B nhưng FAIL nếu chạy sau B.
- Lần chạy đầu PASS, chạy lại cùng JVM hoặc cùng CI worker FAIL do file/bảng/Redis key còn dữ liệu.
- Khi chạy song song, `count(*)` đổi thất thường dù test chỉ insert một bản ghi.
- Assertion mong một email/message nhưng nhận hai vì lần test trước chưa reset fake collector.
- Test tự tạo row ID cố định `"order-1"` và lượt sau báo duplicate key.
- `@Transactional` test tưởng DB tự rollback nhưng service dùng `REQUIRES_NEW` hoặc tác vụ `@Async` đã commit ở transaction khác.
- Test sử dụng `@TestInstance(PER_CLASS)` hoặc `static List` khiến state sống giữa nhiều test methods.
- Sau khi test fail, `@AfterEach` không dọn đúng resources; test tiếp theo nhận trạng thái bẩn.
- Một test gọi `@DirtiesContext` hoặc thay global configuration khiến test chạy song song bị mất context/bean, phát sinh lỗi không lặp ổn định.

Một lần chạy thành công **không chứng minh** test độc lập: có thể test chỉ may mắn có thứ tự phù hợp. Một lần chạy thất bại khi parallel **không chứng minh** lỗi nằm ở JUnit: thường có shared state hoặc race trong code/test fixtures.

### 1.2. Phân biệt các khái niệm

| Loại lỗi | Dấu hiệu | Ví dụ |
|---|---|---|
| **Order dependency** | Đổi thứ tự test khiến kết quả khác | B chỉ PASS nếu A đã insert fixture |
| **Residue/leaked state** | Test sau nhìn thấy dữ liệu test trước | Row cũ trong bảng, file chưa xóa |
| **Race condition** | Chạy concurrent làm kết quả thay đổi | Hai tests cùng clear/insert vào một bảng |
| **Timing flakiness** | Test assert trước khi async work kết thúc | Listener chưa append vào collector |
| **Environment dependence** | Test phụ thuộc timezone, locale, port, secrets, DB thật | Test chạy khác máy/CI |
| **Context cache contamination** | Singleton Spring bean reuse với state đã mutate | Map/cache service chưa reset |
| **Transaction boundary mismatch** | Test rollback không bao phủ side effects khác | `REQUIRES_NEW`, thread khác, HTTP server |
| **Non-deterministic fixture** | Random/time bị dùng không kiểm soát | Dữ liệu không có seed/correlation ID |

Cần chẩn đoán **bằng chứng và phạm vi** trước khi sửa. Nếu vấn đề là DB row còn sót, thay `@TestMethodOrder` không giúp; nếu lỗi do assertion trước khi async consumer hoàn tất, thêm sleep không bảo đảm ổn định.

## 2. Ví dụ tối thiểu: hai test cùng phụ thuộc một bảng

Một mẫu test **sai** (snippet để phân tích, **không thuộc runnable suite**):

```java
@SpringBootTest
class BadOrderTests {
    @Autowired JdbcTemplate jdbc;

    @Test
    void a_createsOrder() {
        jdbc.update(
            "INSERT INTO demo_order(order_id, run_key, order_state, quantity)"
            + " VALUES ('fixed-id', 'shared', 'NEW', 1)");
        assertEquals(1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_order",
                Long.class));
    }

    @Test
    void b_expectsEmptyDatabase() {
        assertEquals(0L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_order",
                Long.class));
    }
}
```

Trong một DB chung:
- Nếu `b_expectsEmptyDatabase` chạy **trước** A, nó có thể PASS.
- Nếu B chạy **sau** A, nó thường FAIL vì A không cleanup.
- Nếu có test C cùng insert thêm row, ngay cả A cũng có thể FAIL ở `COUNT(*)==1`.
- Nếu chạy suite lần thứ hai trên DB không reset, A có thể fail vì `fixed-id` đã tồn tại.

Không thể chữa bằng `@Order(1)` cho B, `@Order(2)` cho A: cách này chỉ **che** phụ thuộc và vẫn để data residue sau suite. Sửa đúng là **dùng dữ liệu được scope theo test ID, truy vấn đúng scope, và cleanup/rollback**.

Ví dụ biến đổi:

```java
String runKey = "run-" + UUID.randomUUID();
String orderId = "ord-" + UUID.randomUUID();

try {
    jdbc.update("""
        INSERT INTO demo_order
          (order_id, run_key, order_state, quantity)
        VALUES (?, ?, ?, ?)
        """, orderId, runKey, "NEW", 1);

    Long actual = jdbc.queryForObject("""
        SELECT COUNT(*) FROM demo_order WHERE run_key = ?
        """, Long.class, runKey);

    assertEquals(1L, actual);
} finally {
    jdbc.update(
        "DELETE FROM demo_order WHERE run_key = ?", runKey);
}
```

Đây là snippet yêu cầu `JdbcTemplate`, `UUID` và schema ở phần project. Nó minh họa **ownership**: test A chỉ đếm/xóa rows của mình; test B dùng run key khác không bị ảnh hưởng. `UUID` giúp ID không va chạm, nhưng **random ID không thay thế cleanup**: nếu mỗi lần chạy để lại một row mới, DB vẫn tăng vô hạn.

## 3. Phát hiện phụ thuộc thứ tự bằng JUnit Jupiter

### 3.1. JUnit không hứa default order theo tên

JUnit Jupiter mặc định dùng thứ tự **deterministic nhưng cố tình không hiển nhiên**; không nên dựa vào tên `testA` chạy trước `testB`. `@TestMethodOrder(MethodOrderer.OrderAnnotation.class)` và `@Order` có thể định thứ tự cho những workflow tests thật sự là scenario nhiều bước, nhưng dùng chúng để che dữ liệu chưa cleanup sẽ làm các tests thiếu độc lập.

```java
@TestMethodOrder(MethodOrderer.Random.class)
class IndependenceTest {
    @Test
    void createWithoutAssumingOtherTestsRan() {
        // tự seed fixture
    }

    @Test
    void queryWithoutAssumingOtherTestsHaveNotRun() {
        // query đúng dữ liệu thuộc test
    }
}
```

Đây là snippet minh họa; project runnable có test classes cụ thể. `MethodOrderer.Random` đổi thứ tự **methods trong một class** bằng seed có thể tái hiện. Để trộn **thứ tự test classes**, dùng `ClassOrderer.Random` ở JUnit Platform. Hai cơ chế khác nhau: thay method order không bảo đảm đổi class order.

### 3.2. Cố định seed để tái hiện

File `src/test/resources/junit-platform.properties` có thể có:

```properties
junit.jupiter.execution.order.random.seed=4232026
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
```

Seed **không phải bản sửa lỗi**; nó là **mã tái hiện lịch chạy**. Để tìm test phụ thuộc thứ tự, chạy lại suite với **nhiều seed**, giữ seed gây FAIL trong bug report/CI logs, rồi sửa fixture/cleanup. Một seed PASS không chứng minh tất cả permutations đều PASS.

Ví dụ lệnh Maven:

```bash
mvn test -Djunit.jupiter.execution.order.random.seed=41
mvn test -Djunit.jupiter.execution.order.random.seed=97
mvn test -Djunit.jupiter.execution.order.random.seed=4232026
```

`-D` được chuyển làm system/user properties phù hợp cho JUnit Platform khi dùng Maven Surefire tương thích. Nếu build riêng có cách truyền JUnit config khác, xác nhận seed thực sự xuất hiện trong test runtime trước khi dùng nó làm bằng chứng.

**Không đoán lỗi chỉ từ tên test xuất hiện trước:** một test A có thể gây leak trong external DB, rồi các test B/C/D đều FAIL. Cần tìm **test gây nhiễm (polluter)** và **test bị ảnh hưởng (victim)**; chúng không nhất thiết là hai test có tên gần nhau.

### 3.3. Chạy từng test, từng class và cả suite

Quy trình hữu ích:

1. Chạy test B nghi ngờ **một mình**.
2. Chạy A một mình rồi B một mình trong **hai tiến trình độc lập**; nếu DB ngoài vẫn giữ row, B có thể còn bị ảnh hưởng.
3. Chạy A và B **trong cùng JVM** theo hai thứ tự khác nhau để kiểm static/Spring context state.
4. Chạy **toàn suite với seed được log** để phát hiện polluter khác.
5. Chạy lặp nhiều lần, ở **CI-like concurrency** và trên data store được reset như production test environment.
6. Sau khi sửa, thêm regression assertions cho **trạng thái sạch trước và sau** scenario, không chỉ kiểm happy path.

Với Maven Surefire, `-Dtest=...` chọn class hoặc method (syntax tùy plugin version), nhưng mỗi lệnh `mvn test` thường khởi chạy vòng test process riêng. Điều đó hữu ích để cô lập, song cũng có thể **che static state leak** vốn chỉ xuất hiện khi hai classes cùng JVM.

### 3.4. Kiểm thứ tự không đồng nghĩa kiểm concurrency

Random method ordering chạy **tuần tự** có thể phát hiện A làm bẩn B. Nhưng hai methods viết vào cùng bảng mà chạy đồng thời cần **stress concurrent**, locking hoặc data isolation. Đừng vội bật random order và parallel toàn bộ cùng lúc vì sẽ khó phân biệt nguyên nhân.

Spring Framework 6.2 cảnh báo tránh chạy song song tùy tiện với tests dùng `@DirtiesContext`, shared external systems, mutable mocks và test-order coordination. Bài demo tách:
- Một suite mô phỏng **đảo thứ tự** chạy tuần tự.
- Một suite **cố ý opt-in parallel** chỉ dùng unique run keys và cleanup theo scope.

Với hệ production dùng DB thật, even nếu ID khác nhau, có thể còn shared sequences, locks, quotas, truncate, broker offsets hoặc cache toàn cục; phải kiểm đầy đủ trước khi cho chạy parallel.

## 4. Cách phát hiện residue trước khi thực hiện assertion

Thêm kiểm tra **baseline** đúng scope tại setup:

```java
@BeforeEach
void begin() {
    runKey = "run-" + UUID.randomUUID();
    assertThat(store.countByRunKey(runKey)).isZero();
}
```

Nếu bạn dùng một `runKey` cố định từ môi trường CI/build, kiểm baseline sẽ giúp phát hiện cleanup trước đó bị bỏ sót. Khi dùng UUID mới ở mỗi test, baseline kiểm rằng fixture chưa bị tạo nhầm trong scope đó nhưng **không chứng minh toàn bộ database không có rows sót**; vì vậy cần thêm **janitor/TTL/cleanup audit** cấp test environment để tìm residue toàn cục. Hai mục tiêu khác nhau:
- **Test isolation:** mỗi test chỉ thao tác rows của mình; truy vấn scoped, cleanup scoped.
- **Environment hygiene:** sau suite không còn fixtures với prefix/tag dành cho test, hoặc mọi fixture có TTL; đo tổng rows theo tag test namespace khi không có tests khác đang chạy.

Đừng assert `SELECT COUNT(*) FROM demo_order = 0` ở đầu mọi test nếu các tests khác có quyền ghi đồng thời. Global count không phân biệt dữ liệu của test khác, data seeding của schema, hoặc dữ liệu nền đã được định nghĩa.

### Dùng correlation/test-run ID

Ví dụ schema có các trường `order_id` và `run_key`:

```sql
SELECT COUNT(*) FROM demo_order WHERE run_key = ?;
DELETE FROM demo_order WHERE run_key = ?;
```

`run_key` thuộc mỗi test invocation, không phải “one key for the entire test suite” khi tests chạy song song. Nếu dùng `@RepeatedTest`, **mỗi repetition** cũng cần run key mới. Nếu test chạy retry do CI flakiness, mỗi retry cần cleanup các rows cũ và một ID dễ truy vết cho điều tra.

### Cleanup theo đúng phạm vi

- **Ưu tiên xóa theo run key/owner**, không `DELETE FROM demo_order` chung hoặc `TRUNCATE` trong parallel suite.
- Cleanup nằm trong `@AfterEach` cho mỗi test invocation, hoặc `finally` ngay tại scope tạo side effect bổ sung.
- Nếu test mở transaction và rollback, cần hiểu code có dùng **transaction khác** không.
- Nếu cleanup có thể fail, hãy để lỗi cleanup **làm test fail** chứ không âm thầm log rồi quên.
- Dữ liệu commit qua background threads/outbox/broker có thể cần cleanup ngoài test transaction.

## 5. Các nguồn gây phụ thuộc thứ tự bên ngoài JDBC

| State được chia sẻ | Ví dụ gây lỗi | Cách phát hiện và cô lập |
|---|---|---|
| `static Map`, static counter | Test A increment, test B expect 0 | Reproduce same JVM, reset/không dùng global mutable state |
| Spring singleton | Bean có `List`/`AtomicInteger` thay đổi | Reset có chủ đích, không mặc định context mới mỗi test |
| Mockito mock/spy | Stub và interactions từ test trước | Framework reset mocks/`Mockito.reset` đúng lifecycle |
| Database/JPA | Insert commit, `REQUIRES_NEW`, sequence | Scoped keys, rollback + cleanup, DB query |
| Redis/cache | Key sống sau test | Prefix theo run, TTL, delete own keys |
| Kafka/RabbitMQ | Consumer group/offset còn, duplicate events | Unique topic/group/id, ack và bounded waits |
| File/temp directory | File cố định `/tmp/report.csv` chưa xóa | JUnit `@TempDir`, cleanup, unique paths |
| OS process/port | Port cố định bị chiếm | Ephemeral port hoặc resource lock |
| System properties | Test đổi `user.timezone`, không restore | Lưu old value và restore trong finally, `@ResourceLock` |
| Locale/timezone/Clock | Test phụ thuộc giờ/ngày hiện tại | `Clock.fixed`, explicit `ZoneId`/`Locale` |
| ThreadLocal/SecurityContext | Context chưa clear sau async thread | Security listener/clear trong finally, context propagation |
| Executor/scheduler | Task sau test vẫn chạy/ghi dữ liệu | Await terminal stage, shutdown/cancel đúng |
| HTTP mock server | Stub/calls còn của test trước | Reset stubs + request journal mỗi test |
| Testcontainers | DB/container tái dùng, port đổi | Align lifecycle, cleanup schemas/test data |
| Browser cookies/localStorage | Phiên đăng nhập/cookies còn | Browser context riêng và logout/clear state |
| Dynamic properties | Supplier/container port đổi nhưng context cache reuse | `@DirtiesContext` nếu cần, hoặc container cố định vòng suite |

**Context cache không phải data cleanup.** Dù Spring TestContext có thể tạo lại context mới, một PostgreSQL/Redis external service vẫn giữ dữ liệu. Ngược lại, không nhất thiết cần context mới nếu singleton được reset đúng và DB fixture có transaction isolation.

## 6. `@Transactional` và giới hạn rollback trong Spring TestContext

Trong Spring Framework, với một test chạy `@Transactional` và có transaction manager, `TransactionalTestExecutionListener` bắt đầu **test-managed transaction** và thường **rollback cuối test**. Điều này hữu ích cho thao tác JDBC/JPA ở **cùng thread và transaction**.

Nhưng rollback không mặc nhiên bao phủ:

1. **`@Transactional(propagation=REQUIRES_NEW)`** trong bean service: method này chủ động có transaction mới, có thể **commit độc lập** với transaction ngoài.
2. **`@Async` hoặc worker thread riêng**: transaction context thường thread-bound; task ở thread khác có thể commit ngoài test transaction.
3. **HTTP thật qua `RANDOM_PORT`**: server xử lý request trên thread khác, có transaction riêng; test `@Transactional` không bảo đảm rollback requests.
4. **`assertTimeoutPreemptively`**: JUnit chạy executable ở thread khác, có thể thoát khỏi test-managed transaction do ThreadLocal binding. Spring docs cảnh báo rõ.
5. **External DB/broker**: viết Kafka, Redis hoặc S3 không rollback cùng JDBC transaction nếu không có coordination chuyên biệt.
6. **Commit có chủ đích**: `@Commit`, `@Rollback(false)` hoặc `TestTransaction.flagForCommit()` làm thay đổi rollback default.

```text
JUnit test thread          Spring service with REQUIRED
   |                               |
   +-- test transaction ---------> joins transaction
   |                               |
   +-- test ends/rollback ---------+ -> row chưa commit bị rollback

JUnit test thread          Service with REQUIRES_NEW
   |                               |
   +-- test transaction --> suspended
   |                               |
   +-- REQUIRES_NEW tx --> COMMIT riêng
   |
   +-- test rollback -> không undo transaction mới

JUnit test thread          @Async worker
   |                               |
   +-- test transaction --> không tự lan ThreadLocal
   |                               |
   +-- async worker --> có thể tự commit
```

Với `@JdbcTest` hoặc `@DataJpaTest`, các test slice thường có transaction rollback mặc định; nhưng test dùng full `@SpringBootTest` **không tự transaction** nếu không gắn `@Transactional`. Trong project runnable, integration test song song **không gắn `@Transactional`**, để mọi insert/commit rõ ràng và cleanup theo run key. Một test riêng dùng `TestTransaction` để quan sát rollback và thêm test `REQUIRES_NEW` để chứng minh boundary.

**Không chữa residue bằng `@Transactional` như một phép màu**: hãy kiểm đúng transaction manager, calling thread, propagation, DB connection, tests async và liệu operation cuối đã commit chưa. Trong `@Transactional` test, `@BeforeEach`/`@AfterEach` chạy trong test transaction; cleanup `DELETE` ở `@AfterEach` có thể cũng bị rollback, nên chưa chắc xóa được rows đã được commit bởi `REQUIRES_NEW`.

## 7. `@DirtiesContext` có phải cách khử dữ liệu còn sót?

`@DirtiesContext` báo Spring TestContext loại `ApplicationContext` khỏi static cache và tạo context mới khi cần. Điều đó có thể reset mutable Spring singleton, mock objects, context-level registries; nhưng:

- Không đảm bảo xóa rows **đã commit** trong DB bên ngoài.
- Không rollback messages đã gửi, files đã ghi hoặc remote API calls.
- Không đồng nghĩa xóa state static nằm ngoài Spring bean lifecycle.
- Làm suite **chậm** vì context startup lại; với nhiều beans/auto-config, chi phí đáng kể.
- Spring Framework 6.2 cảnh báo về chạy `@DirtiesContext` song song khi context bị đóng bởi thread khác.
- Không phải cách chữa lỗi test B phụ thuộc test A; cần tự thiết lập fixture.

Dùng `@DirtiesContext` khi test thật sự **làm hỏng configuration/bean state** không thể reset an toàn. Nếu nguyên nhân chỉ là row DB, ưu tiên transaction hoặc cleanup theo ID. Nếu một bean singleton có internal cache, cân nhắc API clear/reset trong test hoặc xây cache có policy invalidation đúng, thay vì ép mọi test tạo context mới.

## 8. Parallel execution: bật có chủ đích và định nghĩa resource ownership

### 8.1. Bật JUnit parallel không tự đảm bảo tests chạy parallel

Trong `junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread
```

Như trên, parallel engine được **enable**, nhưng default mode vẫn **SAME_THREAD**. Ta chỉ đánh dấu test class được thiết kế an toàn bằng `@Execution(ExecutionMode.CONCURRENT)`. Không cấu hình tất cả tests thành `concurrent` rồi hy vọng chúng tự xử lý shared state.

Theo hướng dẫn Spring Framework 6.2, không nên chạy parallel tùy tiện khi dùng `@DirtiesContext`, Mockito bean overrides/spy beans, các tests có dependency on execution order, hoặc thay đổi trạng thái shared database/broker/filesystem. Trong ví dụ giáo dục, suite JDBC parallel **chỉ thay đổi rows gắn runKey riêng, không có truncate/global clear**, nên cố ý minh họa một phạm vi sở hữu tối thiểu. Với dữ liệu ngoài có locks/sequences/broker/counters chung, vẫn cần đánh giá và có thể phải chạy tuần tự.

### 8.2. `@ResourceLock` với tài nguyên global

Ví dụ snippet:

```java
@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyTests {

    @Test
    @ResourceLock(
        value = "global-system-properties",
        mode = ResourceAccessMode.READ_WRITE)
    void changesProperty() {
        String before = System.getProperty("demo.flag");
        try {
            System.setProperty("demo.flag", "on");
            // assertion ở đây
        } finally {
            if (before == null) {
                System.clearProperty("demo.flag");
            } else {
                System.setProperty("demo.flag", before);
            }
        }
    }
}
```

Đây là snippet cần imports JUnit; không nằm trong runnable demo. `@ResourceLock` **phối hợp với các test cùng khai lock name**, không biến System properties thành thread-local và không ngăn code ngoài JUnit chạm tài nguyên. Với tests làm đổi shared global environment, chạy tuần tự/cô lập JVM thường đơn giản hơn.

### 8.3. `@Isolated`, `@TestInstance` và thứ tự

- `@Isolated` của JUnit Jupiter giúp một class chạy riêng với các tests trong cùng engine khi cần bảo vệ shared state.
- `@TestInstance(PER_METHOD)` (mặc định) tạo **test instance mới cho mỗi test method/invocation**; không reset Spring singletons hoặc DB.
- `@TestInstance(PER_CLASS)` dùng **một instance** nhiều methods; instance fields mutable có thể leak và phải xử lý concurrency.
- `@TestMethodOrder(OrderAnnotation.class)` chỉ phù hợp test **workflow có chủ đích**, nơi từng bước thật sự phụ thuộc trạng thái trước, không nên dùng cho mọi unit/integration test.
- `@RepeatedTest` chạy một method nhiều lần; mỗi repetition cần độc lập, không giả định data lần trước đã hoặc chưa tồn tại.
- `@TestFactory` dynamic tests có lifecycle khác `@Test` thông thường: `@BeforeEach`/`@AfterEach` áp cho factory method chứ không tự áp cho **từng dynamic child**. Thiết kế fixtures/cleanup trong từng dynamic executable nếu cần.
- JUnit random seed giúp tái hiện thứ tự, nhưng **parallel scheduling** có thể nondeterministic ngay với cùng seed; cần thêm logs về execution start/end và resource ownership.

## 9. Dự án runnable Java 17 + Spring Boot 3.5 + H2

Bộ demo gồm:

- `IsolationDemoApplication`: khởi tạo Spring Boot không cần web server.
- `demo_order` H2: hàng có khóa `order_id`, `run_key`, `order_state` và `quantity`.
- `OrderStore`: JDBC repository cho insert/find/count/update/delete **theo run key**.
- `OrderService`: business service tạo order ID mới và kiểm quantity.
- `CommittedWriter`: ví dụ service `REQUIRES_NEW` commit nằm ngoài rollback transaction ngoài.
- `OrderSensitivitySimulationTest`: unit tests mô phỏng deterministic case order-sensitivity và cách sửa.
- `ParallelJdbcIsolationTest`: integration tests có `@Execution(CONCURRENT)`, run key riêng, `@AfterEach` cleanup; có repeated test.
- `TransactionBoundaryTest`: explicit rollback, test-managed transaction, `REQUIRES_NEW` và rollback do exception.
- `junit-platform.properties`: class order random với seed cố định, mặc định tuần tự và opt-in concurrency.

**Các anti-pattern ở phần đầu không được đưa vào test suite runnable**, nên project có thể kỳ vọng PASS mà vẫn **chứng minh lỗi** bằng một simulation test có assertions mong đúng kết quả fail trước khi sửa.

### 9.1. Cây thư mục

```text
test-isolation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolation/
    │   │   ├── IsolationDemoApplication.java
    │   │   ├── OrderRow.java
    │   │   ├── OrderStore.java
    │   │   ├── OrderService.java
    │   │   └── CommittedWriter.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        ├── java/com/example/isolation/
        │   ├── OrderSensitivitySimulationTest.java
        │   ├── ParallelJdbcIsolationTest.java
        │   └── TransactionBoundaryTest.java
        └── resources/
            └── junit-platform.properties
```

### 9.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>test-isolation-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-jdbc` có `JdbcTemplate`/DataSource/transaction manager; H2 là embedded database; `spring-boot-starter-aop` làm rõ proxy interception cho `@Transactional` của service; `spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ. Parent Boot 3.5 quản lý dependency versions. Không cần Docker/HTTP server.

### 9.3. Main Spring Boot application

File **`src/main/java/com/example/isolation/IsolationDemoApplication.java`**:

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }
}
```

`@SpringBootTest(webEnvironment=NONE)` trong integration tests chỉ khởi tạo context và H2 DataSource, không mở servlet port. Các beans cùng package được component-scanned.

### 9.4. Schema SQL: H2 embedded

File **`src/main/resources/schema.sql`**:

```sql
CREATE TABLE demo_order (
    order_id VARCHAR(80) NOT NULL PRIMARY KEY,
    run_key VARCHAR(80) NOT NULL,
    order_state VARCHAR(24) NOT NULL,
    quantity INT NOT NULL
);

CREATE INDEX idx_demo_order_run_key
    ON demo_order(run_key);
```

Spring Boot mặc định thực thi `schema.sql` lúc init một embedded H2 DataSource. Dùng một cơ chế schema initialization; nếu dự án thật đã có Flyway/Liquibase thì **không trộn** với `schema.sql` mặc định tùy tiện. Bài không cần `data.sql`: mỗi test tự tạo data của riêng nó.

**Mục đích `run_key`:** một DB context có thể được cache/share qua các tests; mọi cleanup dựa trên `run_key` là local. `order_id` cũng unique theo UUID nên tránh duplicate key giữa hai tests ngay cả khi chạy parallel.

### 9.5. Value object

File **`src/main/java/com/example/isolation/OrderRow.java`**:

```java
package com.example.isolation;

public record OrderRow(
        String orderId,
        String runKey,
        String state,
        int quantity) {
}
```

Record Java 17 có equality và accessors deterministic. Test có thể assert cả object. Đây là row DTO của demo, không phải JPA entity; JDBC mapping explicit.

### 9.6. JDBC store với truy vấn và cleanup theo run key

File **`src/main/java/com/example/isolation/OrderStore.java`**:

```java
package com.example.isolation;

import java.util.Objects;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            String orderId, String runKey,
            String state, int quantity) {

        jdbc.update("""
                INSERT INTO demo_order
                    (order_id, run_key, order_state, quantity)
                VALUES (?, ?, ?, ?)
                """, orderId, runKey, state, quantity);
    }

    public Optional<OrderRow> find(
            String runKey, String orderId) {

        return jdbc.query("""
                SELECT order_id, run_key, order_state, quantity
                FROM demo_order
                WHERE run_key = ? AND order_id = ?
                """,
                (rs, index) -> new OrderRow(
                        rs.getString("order_id"),
                        rs.getString("run_key"),
                        rs.getString("order_state"),
                        rs.getInt("quantity")),
                runKey, orderId)
                .stream()
                .findFirst();
    }

    public long countByRunKey(String runKey) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_order
                WHERE run_key = ?
                """, Long.class, runKey);
        return Objects.requireNonNull(count);
    }

    public int updateState(
            String runKey, String orderId, String state) {

        return jdbc.update("""
                UPDATE demo_order SET order_state = ?
                WHERE run_key = ? AND order_id = ?
                """, state, runKey, orderId);
    }

    public int deleteByRunKey(String runKey) {
        return jdbc.update("""
                DELETE FROM demo_order WHERE run_key = ?
                """, runKey);
    }
}
```

**Không có `DELETE FROM demo_order` không WHERE.** Test sẽ không xóa hàng của test khác. `find` cũng scope bằng `run_key` nên không “đọc nhầm” order có cùng business ID được phép ở một data model khác. Với production multi-tenancy cần luôn gắn tenant key/authorization vào SQL; `run_key` ở demo chỉ là test fixture ownership, không phải cơ chế bảo mật thực tế.

### 9.7. Service sinh unique ID và kiểm input

File **`src/main/java/com/example/isolation/OrderService.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    public String place(String runKey, int quantity) {
        if (runKey == null || runKey.isBlank()) {
            throw new IllegalArgumentException(
                    "runKey must be non-blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        String orderId = "ord-" + UUID.randomUUID();
        store.insert(orderId, runKey, "NEW", quantity);
        return orderId;
    }
}
```

Test kiểm ID được trả về bằng cách đọc row tương ứng, không giả lập một UUID cố định trên mọi test invocation. `UUID.randomUUID()` không tự là business idempotency key. Trong hệ thật có thể cần ID generator có thể inject hoặc idempotency key từ client; bài này dùng UUID chỉ để tránh collision của demo.

### 9.8. Service mở transaction mới

File **`src/main/java/com/example/isolation/CommittedWriter.java`**:

```java
package com.example.isolation;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CommittedWriter {

    private final OrderStore store;

    public CommittedWriter(OrderStore store) {
        this.store = store;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void insertCommitted(
            String runKey, String orderId) {

        store.insert(orderId, runKey, "NEW", 1);
    }
}
```

Lời gọi đi qua **Spring-managed bean proxy**, nên `REQUIRES_NEW` tạo transaction mới, tách khỏi transaction đã có ở caller. Nếu transaction mới commit, rollback transaction caller không tự xóa row. Test sẽ làm rõ điều này và dọn row trong `finally` để không để lại residue. Đây không phải khuyến cáo dùng `REQUIRES_NEW` cho mọi business method.

### 9.9. JUnit Platform configuration

File **`src/test/resources/junit-platform.properties`**:

```properties
# Trộn thứ tự test classes có thể tái hiện với seed này.
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed=4232026

# Bật engine parallel, mặc định vẫn chạy tuần tự.
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread

# Chỉ class có @Execution(CONCURRENT) tự opt-in parallel.
```

Lớp `OrderSensitivitySimulationTest` ở phần sau có `@TestMethodOrder(MethodOrderer.Random.class)`, nên các methods của nó cũng được xáo với seed. `ParallelJdbcIsolationTest` **không có `@TestMethodOrder`** mà chỉ opt-in `@Execution(CONCURRENT)`. Đây là chủ đích: Spring cảnh báo không nên trộn test-order coordination với parallel execution tùy tiện.

Seed là reproducibility aid, không bảo đảm OS/thread scheduling khi execution concurrent. Nếu CI chạy JVM forks khác, static context cache và DB có thể khác lifecycle; ghi lại seed, version, forks và test selection trong báo cáo flaky.

### 9.10. Unit tests: mô phỏng lỗi order dependency một cách an toàn

File **`src/test/java/com/example/isolation/OrderSensitivitySimulationTest.java`**:

```java
package com.example.isolation;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;

import static org.assertj.core.api.Assertions.assertThat;

@TestMethodOrder(MethodOrderer.Random.class)
class OrderSensitivitySimulationTest {

    // Synthetic suite: hai "test scenarios" cùng dùng một Set.
    // Không phải JUnit @Test methods thật sự phụ thuộc nhau.
    private static List<String> runBrokenSequence(
            List<String> sequence) {

        Set<String> database = new HashSet<>();
        List<String> failures = new ArrayList<>();

        for (String scenario : sequence) {
            switch (scenario) {
                case "writer" -> database.add("fixed-order");
                case "expectsEmpty" -> {
                    if (!database.isEmpty()) {
                        failures.add("expectsEmpty");
                    }
                }
                default -> throw new IllegalArgumentException(
                        "unknown scenario: " + scenario);
            }
        }
        return failures;
    }

    private static List<String> runWithFreshStatePerScenario(
            List<String> sequence) {

        List<String> failures = new ArrayList<>();

        for (String scenario : sequence) {
            Set<String> database = new HashSet<>();
            switch (scenario) {
                case "writer" -> database.add("fixed-order");
                case "expectsEmpty" -> {
                    if (!database.isEmpty()) {
                        failures.add("expectsEmpty");
                    }
                }
                default -> throw new IllegalArgumentException(
                        "unknown scenario: " + scenario);
            }
        }
        return failures;
    }

    @Test
    void reversedOrderExposesHiddenDependency() {
        assertThat(runBrokenSequence(
                List.of("expectsEmpty", "writer")))
                .isEmpty();

        assertThat(runBrokenSequence(
                List.of("writer", "expectsEmpty")))
                .containsExactly("expectsEmpty");
    }

    @Test
    void freshFixtureMakesBothOrdersIndependent() {
        assertThat(runWithFreshStatePerScenario(
                List.of("expectsEmpty", "writer")))
                .isEmpty();

        assertThat(runWithFreshStatePerScenario(
                List.of("writer", "expectsEmpty")))
                .isEmpty();
    }

    @Test
    void finallyRestoresOwnedMutableState() {
        Set<String> database = new HashSet<>();
        try {
            database.add("order-in-test");
            assertThat(database).containsExactly("order-in-test");
        } finally {
            database.clear();
        }
        assertThat(database).isEmpty();
    }
}
```

**3 `@Test`** đều PASS: test đầu xác nhận một **broken synthetic suite** cho kết quả phụ thuộc thứ tự, không tạo test thật thất bại ngẫu nhiên; test thứ hai cho thấy fixture mới cho từng scenario loại bỏ phụ thuộc; test thứ ba xác nhận `finally` cleanup. Cách này giúp bài giảng mô tả lỗi **có thể tái hiện** mà không khiến Maven project mặc định bị FAIL.

Đây là **mô phỏng in-memory**, không phải JDBC integration test; phần tiếp theo kiểm isolation thực sự trong DB.

### 9.11. Integration tests: per-invocation run key và parallel an toàn trong phạm vi demo

File **`src/test/java/com/example/isolation/ParallelJdbcIsolationTest.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ParallelJdbcIsolationTest {

    @Autowired
    private OrderStore store;

    @Autowired
    private OrderService service;

    private String runKey;

    @BeforeEach
    void prepareUniqueRun() {
        runKey = "run-" + UUID.randomUUID();
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @AfterEach
    void removeOnlyOwnRows() {
        store.deleteByRunKey(runKey);
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void oneOrderIsVisibleOnlyWithinItsRun() {
        String id = service.place(runKey, 2);

        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
        assertThat(store.find(runKey, id))
                .contains(new OrderRow(id, runKey, "NEW", 2));
    }

    @Test
    void twoOrdersProduceExactlyTwoScopedRows() {
        String first = service.place(runKey, 1);
        String second = service.place(runKey, 3);

        assertThat(first).isNotEqualTo(second);
        assertThat(store.countByRunKey(runKey)).isEqualTo(2L);
    }

    @Test
    void anotherRunCannotSeeTheCurrentOrders() {
        String id = service.place(runKey, 5);
        String otherRun = "other-" + UUID.randomUUID();

        assertThat(store.find(otherRun, id)).isEmpty();
        assertThat(store.countByRunKey(otherRun)).isZero();
    }

    @Test
    void lookingUpUnknownIdNeverFindsAnotherTestsRows() {
        String missing = "missing-" + UUID.randomUUID();

        assertThat(store.find(runKey, missing)).isEmpty();
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void updateUsesBothOrderIdAndRunKey() {
        String id = service.place(runKey, 2);
        String otherRun = "other-" + UUID.randomUUID();

        assertThat(store.updateState(
                otherRun, id, "DONE")).isZero();

        assertThat(store.updateState(
                runKey, id, "DONE")).isEqualTo(1);

        assertThat(store.find(runKey, id))
                .contains(new OrderRow(id, runKey, "DONE", 2));
    }

    @Test
    void invalidQuantityCannotLeaveAnyRecord() {
        assertThatThrownBy(() -> service.place(runKey, 0))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void duplicatePrimaryKeyFailsWithoutAddingAnotherRow() {
        String id = service.place(runKey, 4);

        assertThatThrownBy(() ->
                store.insert(id, runKey, "NEW", 4))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
    }

    @Test
    void cleanupOfOneRunDoesNotDeleteAnotherRun() {
        String otherRun = "other-" + UUID.randomUUID();
        try {
            String ownId = service.place(runKey, 1);
            String otherId = service.place(otherRun, 2);

            assertThat(store.deleteByRunKey(runKey))
                    .isEqualTo(1);
            assertThat(store.countByRunKey(runKey)).isZero();

            assertThat(store.find(otherRun, otherId))
                    .contains(new OrderRow(
                            otherId, otherRun, "NEW", 2));
            assertThat(store.find(runKey, ownId)).isEmpty();
        } finally {
            store.deleteByRunKey(otherRun);
        }
    }

    @Test
    void cleanupMayBeCalledMoreThanOnce() {
        service.place(runKey, 1);

        assertThat(store.deleteByRunKey(runKey)).isEqualTo(1);
        assertThat(store.deleteByRunKey(runKey)).isZero();
        // @AfterEach vẫn có thể cleanup an toàn.
    }

    @RepeatedTest(4)
    void repeatedRunUsesNewOwnerAndCanStartClean() {
        assertThat(store.countByRunKey(runKey)).isZero();
        String id = service.place(runKey, 1);

        assertThat(store.find(runKey, id)).isPresent();
        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
    }
}
```

**9 phương thức `@Test` + một `@RepeatedTest(4)`**: tổng **13 lần thực thi** trong class này. `@BeforeEach`/`@AfterEach` chạy cho **từng repetition**; class dùng `PER_METHOD` nên field `runKey` thuộc riêng mỗi test instance. Tất cả SQL reads/writes/deletes được scope theo ID unique; không dùng row IDs cố định, không reset toàn bộ bảng.

Các methods có thể chạy đồng thời vì đã opt-in `@Execution(CONCURRENT)` và JUnit parallel engine bật, nhưng **không bảo đảm đồng thời xảy ra trong mọi môi trường** (thread pool có thể nhỏ). Suite vẫn đúng nếu chạy tuần tự. Nếu ứng dụng real DB có global mutable state, triggers, sequences hay shared Kafka resources, không được suy rằng chỉ thêm UUID là đã đủ an toàn để bật concurrency.

**Vì sao `@AfterEach` không xóa dữ liệu của test khác?** Nó gọi `DELETE ... WHERE run_key = ?` chỉ với run key của method/repetition hiện tại, không phải `TRUNCATE`. Trong method kiểm hai runs, row thuộc `otherRun` được dọn trong `finally` riêng, tránh bỏ lại dữ liệu ngoài run key của fixture.

### 9.12. Integration tests: rollback, test transaction, REQUIRES_NEW

File **`src/test/java/com/example/isolation/TransactionBoundaryTest.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TransactionBoundaryTest {

    @Autowired
    private OrderStore store;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private CommittedWriter committedWriter;

    @Test
    void explicitRollbackRemovesUncommittedJdbCChanges() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            TransactionTemplate tx =
                    new TransactionTemplate(transactionManager);

            tx.executeWithoutResult(status -> {
                store.insert(id, run, "NEW", 1);
                assertThat(store.countByRunKey(run))
                        .isEqualTo(1L);
                status.setRollbackOnly();
            });

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            store.deleteByRunKey(run);
        }
    }

    @Test
    void requiresNewCommitSurvivesOuterRollback() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            TransactionTemplate outer =
                    new TransactionTemplate(transactionManager);

            outer.executeWithoutResult(status -> {
                committedWriter.insertCommitted(run, id);
                // Transaction của outer bị rollback;
                // REQUIRES_NEW đã commit riêng.
                status.setRollbackOnly();
            });

            assertThat(store.countByRunKey(run))
                    .isEqualTo(1L);
        } finally {
            // Dọn row đã COMMIT, không dựa vào rollback outer.
            store.deleteByRunKey(run);
        }
    }

    @Test
    @Transactional
    void testManagedRollbackCanBeVerifiedInSameMethod() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            assertThat(TestTransaction.isActive()).isTrue();
            store.insert(id, run, "NEW", 1);

            assertThat(store.countByRunKey(run))
                    .isEqualTo(1L);

            TestTransaction.flagForRollback();
            TestTransaction.end();

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            store.deleteByRunKey(run);
        }
    }

    @Test
    void unhandledExceptionRollsBackTransactionTemplate() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            assertThatThrownBy(() ->
                new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status -> {
                        store.insert(id, run, "NEW", 1);
                        throw new IllegalStateException(
                                "simulated-failure");
                    }))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessage("simulated-failure");

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            store.deleteByRunKey(run);
        }
    }
}
```

**4 phương thức `@Test`** này phân biệt:
- Rollback explicit trong `TransactionTemplate` → row biến mất.
- `REQUIRES_NEW` commit độc lập → vẫn còn row sau rollback transaction ngoài; `finally` cleanup ngoài transaction.
- Test-managed `@Transactional` và `TestTransaction.flagForRollback()/end()` → xác nhận rollback ngay **trong cùng test method**, không phụ thuộc một test khác chạy sau để kiểm dữ liệu.
- Exception thoát ra khỏi `TransactionTemplate` → rollback và row không còn.

**Tổng runnable suite:** 3 unit tests + 9 `@Test` JDBC + 4 repetitions + 4 transaction tests = **20 test invocations** (**16 methods gắn `@Test`, 1 method `@RepeatedTest(4)`**). Test liên quan commit/rollback đều có cleanup theo `run_key`; không dựa vào thứ tự các classes.

### 9.13. Chạy Maven

Cần **JDK 17+**, Maven, không cần Docker:

```bash
mvn test
mvn -Dtest=OrderSensitivitySimulationTest test
mvn -Dtest=ParallelJdbcIsolationTest test
mvn -Dtest=TransactionBoundaryTest test
```

Đổi seed để lặp với các orders:

```bash
mvn test -Djunit.jupiter.execution.order.random.seed=20261108
mvn test -Djunit.jupiter.execution.order.random.seed=91
mvn test -Djunit.jupiter.execution.order.random.seed=7
```

Kỳ vọng tất cả **20 test invocations** PASS trong môi trường phù hợp. Project dùng in-memory H2 tạo mới khi context được khởi động và mọi test cleanup dữ liệu của mình. **Không có stdout cố định** vì Maven/JUnit/Spring logs phụ thuộc môi trường và test scheduling. Mã được rà soát theo Java 17/JUnit Jupiter/Spring Boot 3.5, **không khẳng định đã thực thi Maven thực tế** trong quá trình viết bài.

Trong CI thực, hãy log **seed**, test selection, JVM forks, timezone, database version và thông tin failure đầu tiên, thay vì chỉ lưu screenshot cuối của BUILD FAILURE.

## 10. Đọc và phân tích thất bại theo ba phép thử

### 10.1. “PASS riêng, FAIL cùng suite”

Nghi ngờ:
- Context singleton từ test khác được reuse.
- Static/system property/file/DB còn state.
- Dữ liệu cố định trùng ID.
- Test ngoài Spring đã thay global object.
- Order test classes có thể liên quan.

Bằng chứng cần lấy:
- Test bị ảnh hưởng chạy riêng PASS.
- Cùng JVM chạy polluter trước victim FAIL.
- Sau khi reset đúng state, cặp polluter-victim PASS dù thứ tự đảo.
- Không dùng `@Order` làm bản vá nếu scenario không phải workflow.

### 10.2. “FAIL chỉ khi parallel”

Nghi ngờ:
- Hai tests `TRUNCATE`/`DELETE` cùng table.
- Một test clear singleton collector khi test kia đang chờ listener.
- Cả hai dùng `@MockBean`/`@MockitoBean` shared context và stubbing/verify cạnh tranh.
- Các tests ghi System properties hoặc dùng chung file.
- Race giữa DB transaction và async worker.
- Context `@DirtiesContext` bị đóng trong lúc test khác đang dùng.

Bằng chứng:
- Cùng seed chạy tuần tự PASS, parallel FAIL.
- Thêm logging test run key, thread name, operation ID, insert/delete timestamps đã sanitize.
- Tách resources hoặc dùng JUnit `@ResourceLock`/`@Isolated` (khi shared resource thực sự không thể phân chia).
- Đánh giá Spring TestContext parallel caveats trước khi bật trên toàn suite.

### 10.3. “FAIL sau khi chạy lại hoặc khi CI reuse môi trường”

Nghi ngờ:
- External DB/schema/Redis/volume reused.
- Không cleanup nếu test fail sớm.
- Testcontainers reusable volumes/data còn.
- File tạm nằm ngoài `@TempDir`.
- Broker topics/groups/offsets tái sử dụng.
- Clock/system property bị leak qua test JVM.

Bằng chứng:
- Liệt kê residue theo **test namespace** sau suite khi không có tests còn chạy.
- Lưu createdAt/runId của fixture để tìm owner tạo row.
- Thêm janitor xóa quá hạn theo TTL, không xóa data của pipeline khác đang chạy.
- Không dựa vào `schema.sql` của một **cached Spring context** như phép reset DB **giữa mọi tests**: script thường chạy tại startup, không trước mỗi method.

## 11. Các anti-pattern thường làm suite flaky

### 11.1. `@Order` chỉ để một test seed dữ liệu cho test khác

```java
@Test @Order(1) void createFixture() { ... }
@Test @Order(2) void queryFixture() { ... }
```

Đây chỉ là snippet anti-pattern, không chạy độc lập. Nếu hai test chỉ có ý nghĩa **cùng một workflow end-to-end**, nên gom thành **một `@Test` chứa các bước rõ ràng**, hoặc dùng lifecycle fixture chuyên dụng để test setup có chủ đích. Nếu mỗi method là một use case độc lập, không được dựa vào dữ liệu do method khác tạo.

### 11.2. `@BeforeAll` INSERT fixture rồi mọi test thay dữ liệu đó

Dữ liệu chung có thể bị một test update/delete và test khác thấy giá trị lạ, đặc biệt khi parallel. Dùng immutable shared fixture nếu thật sự bất biến, hoặc clone/seed data riêng từng method. Với `@BeforeAll` chạy trong test class lifecycle, không nên giả định transaction rollback per method bao phủ mọi setup class-level.

### 11.3. Dùng `SELECT COUNT(*)` trên toàn bảng

Khi test khác cùng DB insert rows, global count không đại diện cho test hiện tại. Dùng `WHERE run_key = ?`/tenant ID và assert đúng IDs. Nếu phải kiểm dữ liệu toàn hệ thống, test đó nên chạy ở **isolated database/schema/container** và được đánh dấu không parallel với tests dùng chung DB.

### 11.4. `@AfterEach` cleanup nhưng không đảm bảo chạy sau side effects bất đồng bộ

Test gọi `service.processAsync()` rồi return; `@AfterEach` xóa rows ngay, nhưng worker còn chạy và insert sau cleanup. Test tiếp theo thấy data từ “quá khứ”. Hãy **await terminal CompletableFuture** với timeout, kiểm lỗi, rồi cleanup. `Thread.sleep(100)` không phải synchronization guarantee.

### 11.5. Reset mọi table bằng `TRUNCATE`

`TRUNCATE` thường vượt khỏi row ownership, có thể khác semantics transaction tùy DB, và dễ phá parallel tests. Dùng cleanup scoped. Nếu mục tiêu là reset **toàn database**, tạo isolated schema/container cho riêng test class/suite và thực hiện reset khi không có worker khác đang dùng.

### 11.6. Chạy `assertTimeoutPreemptively` trong test @Transactional

Spring TestContext transaction thường bind vào thread hiện tại. Preemptive timeout có thể thực thi code trên thread khác và các inserts commit độc lập, không rollback cùng test thread. Dùng timeout ở JDBC/HTTP client/async future boundary hoặc `assertTimeout` có cân nhắc, không dựa vào preemptive test timeout như cơ chế transaction isolation.

### 11.7. Catch exception và bỏ qua lỗi cleanup

```java
@AfterEach
void cleanup() {
    try {
        repository.deleteTestData();
    } catch (Exception ignored) {
        // Sai: dữ liệu vẫn tồn tại nhưng test tiếp theo mới FAIL.
    }
}
```

Đây là anti-pattern: nếu cleanup fail, JUnit cần thấy lỗi, đồng thời hệ thống phải log enough context (test run ID, resource) để xác định residue. Không log secrets/PII.

### 11.8. Test mock stubs leak giữa các classes

Cùng Spring context có thể chứa Mockito bean overrides. Spring Framework TestContext có reset listener phù hợp, nhưng custom reset modes, manually-created mocks, static mocks hoặc background tasks có thể làm stubbing/calls lẫn nhau. Dùng mock scope/lifecycle đúng, tránh parallel tests shared mutable mocks và đừng thêm `@DirtiesContext` chỉ để chữa một lần quên reset.

### 11.9. Random test order được dùng như “fix”

Random seed chỉ giúp **lộ** dependency. Nếu một thứ tự PASS, test vẫn có thể FAIL ở permutation khác. Sau khi sửa, nên chạy nhiều seeds và parallel stress tests; giữ test fail seed trong regression ticket.

### 11.10. Thay context cache bằng khởi động ứng dụng mỗi test

Tắt reuse sẽ làm test rất chậm và có thể vẫn không xóa DB/Redis/broker/file. Cần xác định state có nằm trong context hay ngoài; không đánh đổi hiệu năng khi chỉ cần cleanup scoped. `@DirtiesContext` có thể là lựa chọn cuối khi test thực sự làm bẩn context không thể reset.

## 12. Test matrix phát hiện order dependence và residue

| Kịch bản | Môi trường | Expected/evidence |
|---|---|---|
| Một test chạy riêng | Fresh process/DB | PASS sau tự setup |
| Cùng class nhiều orders | `MethodOrderer.Random` với nhiều seeds | PASS ở mọi seed đã thử |
| Các classes nhiều orders | `ClassOrderer.Random` | Không test nào cần class khác chạy trước |
| Lặp một test | `@RepeatedTest`/Surefire rerun | Mỗi iteration có fixture riêng |
| Có một writer và một reader | Đảo hai scenarios | Không phụ thuộc thứ tự |
| DB có dữ liệu của test khác | Hai run keys khác nhau | Scoped query không lẫn |
| Hai tests insert song song | Distinct run keys, unique PKs | Không race/trùng dữ liệu |
| Cleanup của A | A và B cùng table | Chỉ rows của A bị xóa |
| Invalid command | Input không hợp lệ | Không row mới, không side effect |
| Duplicate business ID | Constraint/failure case | Không biến thành random collision |
| Test-managed rollback | Cùng thread + REQUIRED transaction | Row chưa commit biến mất |
| `REQUIRES_NEW` | Outer test rollback | Row đã commit còn, cleanup riêng |
| Async DB write | Worker thread khác | Await + cleanup sau completion |
| `@DirtiesContext` | Context-state mutation | Reload context chỉ khi thật cần |
| Mock reuse | Shared test context | Stubbing/interaction reset |
| External resources | Redis/Kafka/files/HTTP | IDs/cleanup/ack riêng |
| CI rerun same environment | Persistent DB/workspace | Không residue từ run cũ |
| CI parallel | Opt-in safe tests | Không global truncate, không shared mutable state |
| Context cache reuse | Same Spring configuration | Test độc lập dù beans reuse |

Nếu test cần “toàn bộ bảng trống” làm precondition nhưng DB đó được chia sẻ với nhiều tests, hãy đổi architecture: **isolated schema/container** hoặc chỉ tiêu hợp đồng **scoped-to-test**, không viết assertion ép môi trường chung phải trống.

## 13. Checklist QA trước khi bật parallel CI

- [ ] Mỗi test tự setup fixture; không cần test A/B khác chạy trước.
- [ ] Tôi chạy một test riêng, cả class và toàn suite để đối chiếu.
- [ ] Tôi đổi nhiều `MethodOrderer.Random` và `ClassOrderer.Random` seeds.
- [ ] Seed gây lỗi được lưu để tái hiện; không coi seed cố định là fix.
- [ ] Tôi phân biệt order dependency với concurrency race và async timing.
- [ ] Tôi biết các state chung: static, singleton, database, Redis, Kafka, files, mocks, properties.
- [ ] Test DB dùng test-run ID hoặc tenant ID riêng, không dùng cố định `"id=1"` cho mọi test.
- [ ] Mọi queries/assertions quan trọng được scope theo dữ liệu thuộc test.
- [ ] Cleanup xóa đúng rows/keys của test, **không global DELETE/TRUNCATE** trong parallel suite.
- [ ] `@BeforeEach` tạo run ID mới; `@AfterEach` cleanup mỗi invocation và không nuốt cleanup errors.
- [ ] `@RepeatedTest` cũng nhận fixture/run ID mới.
- [ ] Test không dựa vào mặc định transaction rollback của `@SpringBootTest` khi chưa @Transactional.
- [ ] Tôi đã kiểm các đường `REQUIRES_NEW`, `@Async`, HTTP server threads và external side effects.
- [ ] `@Transactional` test không dùng preemptive timeout làm operation thoát transaction.
- [ ] `TestTransaction` hoặc explicit transaction test chứng minh rollback trong **cùng test**, không phụ thuộc method khác.
- [ ] Không dùng `@DirtiesContext` thay cho cleanup DB/file/broker; biết context cache được chia sẻ.
- [ ] Không đặt `@MockitoBean`/`@DirtiesContext`/shared database tests vào parallel mode mà chưa đánh giá caveats.
- [ ] Nếu shared resource không tách được, sử dụng `@ResourceLock`/`@Isolated` hoặc chạy tuần tự.
- [ ] Tôi chờ mọi async work hoàn tất trước teardown và propagate errors về JUnit.
- [ ] Không dùng `Thread.sleep` để đoán worker đã chạy.
- [ ] Dữ liệu stale của CI được dọn bằng TTL/janitor đúng namespace ngoài giờ test chạy.
- [ ] Không log credentials, PII hoặc payload nhạy cảm khi chẩn đoán test residue.
- [ ] Tôi kiểm test invocation count, JUnit parallel configuration và Surefire forks thực tế.
- [ ] Test pass với nhiều seeds/chạy lại nhiều lần trên môi trường CI-like.
- [ ] Khi một run fail, báo cáo có polluter/victim hypothesis, run key, seed và cleanup evidence.

**Kết luận:** test phụ thuộc thứ tự hoặc còn dữ liệu sót có thể được phát hiện bằng **đảo thứ tự có seed tái hiện, chạy riêng so với toàn suite, kiểm baseline và dữ liệu thuộc riêng từng test**, rồi thêm stress concurrency có chủ đích. Cách sửa không phải đổi `@Order` hay bật `@DirtiesContext` hàng loạt, mà là **setup độc lập, state ownership rõ, transaction boundaries đúng, và teardown không bỏ sót side effects**. Một suite đáng tin là suite **không đổi kết quả chỉ vì một test khác vừa chạy trước đó**.

### Tài liệu chính thức

- [JUnit 5.12 — User Guide: Test Execution Order, Parallel Execution, @ResourceLock](https://docs.junit.org/5.12.0/user-guide/)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html)
- [Spring Boot 3.5 — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — SQL Databases and JdbcTemplate](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
