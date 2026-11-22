# Chạy lặp, xáo trộn thứ tự và phân tích race condition

## 1. Vì sao test luôn xanh khi chạy riêng nhưng đỏ khi chạy cả suite?

Một test Spring Boot được chạy độc lập và PASS. Khi chạy cùng 200 tests khác, nó thỉnh thoảng FAIL; đổi thứ tự classes lại PASS; bật parallel execution khiến lỗi xuất hiện nhiều hơn. Đây là dấu hiệu quan trọng của **thiếu cách ly (test isolation), state leakage, bất đồng bộ chưa đồng bộ hóa hoặc race condition** — không phải lý do để thêm `Thread.sleep(3000)` rồi coi suite đã ổn.

Ba thao tác điều tra cơ bản phải được **phân biệt**:

1. **Chạy lặp (repetition)**: chạy cùng logic nhiều lần để phát hiện lỗi có tính xác suất, lỗi phụ thuộc thời gian, dữ liệu sót hoặc tài nguyên không cleanup. JUnit Jupiter dùng `@RepeatedTest`; CI còn có nhiều lần chạy cả Maven suite.
2. **Xáo trộn thứ tự (random ordering)**: thay thứ tự methods/classes để phát hiện test A vô tình tạo dữ liệu, cache, environment hoặc singleton state mà test B đang phụ thuộc. JUnit có `MethodOrderer.Random` và `ClassOrderer.Random`, Maven Surefire có `runOrder=random` ở tầng test class.
3. **Chạy song song (parallel execution)**: tạo các interleavings thật giữa threads/classes để lộ check-then-act, lost update, shared mutable state, connection pool exhaustion và tranh chấp dữ liệu. JUnit 5 dùng cấu hình `junit.jupiter.execution.parallel.*`, `@Execution`, `@ResourceLock` và `@Isolated`.

**Không phải cùng một công cụ:**
- Lặp 1.000 lần **tuần tự** không nhất thiết tạo hai threads cùng sửa một value.
- Xáo trộn thứ tự không tự làm xuất hiện simultaneous writes.
- Parallel execution không đảm bảo tạo đúng interleaving của bug hiếm.
- JUnit test method order không kiểm soát thứ tự thread scheduling hoặc thứ tự DB commit.
- Maven Surefire rerun failures làm bài test thất bại được chạy lại, **không chữa flaky test**.

Bài này nằm trong nhóm **Cách ly và chạy song song** của Spring Boot Testing. Trọng tâm là cách xác định **thứ gì đang shared, điều gì bị race, làm sao tái hiện chắc chắn, và bằng chứng nào xác nhận fix**. Phần lab là project độc lập **Java 17 / Spring Boot 3.5.16 / Maven / H2 / Spring JDBC / JUnit 5**, có các tests chứng minh lỗi **lost update** và hai cách sửa: atomic SQL update, optimistic compare-and-set (CAS). Hướng dẫn mở rộng áp dụng cho JPA `@Version`, PostgreSQL/Testcontainers, Kafka/Redis và TestContext cache.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **flaky test**, order-dependent test, data contamination, timeout và race condition.
- Sử dụng `@RepeatedTest`, `RepetitionInfo`, `failureThreshold` mà không hiểu sai lifecycle.
- Xáo trộn methods/classes bằng `MethodOrderer.Random`, `ClassOrderer.Random` và seed có thể phát lại.
- Dùng `junit-platform.properties` để chạy classes parallel nhưng giữ methods trong mỗi class sequential.
- Dùng `@ResourceLock`/`@Isolated` cho JVM resources có khả năng gây nhiễm chéo, hiểu giới hạn phạm vi engine.
- Không dùng `@TestMethodOrder(OrderAnnotation.class)` để che dependency giữa tests.
- Dùng `CountDownLatch`, `ExecutorService` và `Future.get(timeout)` để ép interleaving quan trọng **không cần sleep**.
- Chứng minh lost update với hai workers cùng đọc một giá trị rồi cùng ghi, không chỉ trông chờ scheduler may rủi.
- Phân biệt Java data race với database lost update, transaction isolation và optimistic locking.
- Đo lường các kết quả cần kiểm sau khi workers đã hoàn tất; không assert khi asynchronous actions vẫn chạy.
- Tránh test-level `@Transactional` che transaction commits hoặc làm thread khác không nhìn thấy fixture.
- Kiểm dữ liệu test theo IDs riêng; tránh cleanup toàn bảng trên DB/container dùng chung.
- Biết khi nào cần khóa tài nguyên, khi nào cần sửa production concurrency control, khi nào chỉ cần reset test fixture.
- Tái hiện lỗi từ seed, thread dump, correlation ID và CI artifacts; không báo PASS nếu mọi tests bị skip.
- Thiết kế chiến lược CI gồm smoke tests nhanh, randomized/parallel pass và stress/production-like suite.

## 2. Phân loại lỗi trước khi chọn công cụ

### 2.1. Flaky test là triệu chứng, không phải chẩn đoán

Flaky test là test có kết quả khác nhau khi code và contract được kỳ vọng không thay đổi. Nguyên nhân thường gặp:
- Race condition trong code nghiệp vụ hoặc trong test fixture.
- Global mutable singleton/static field hoặc Spring bean dùng chung.
- Database/Redis/broker state tồn dư từ một test khác.
- Test phụ thuộc method/class execution order.
- Read-before-commit và eventual consistency.
- Lỗi timeout/slow CI, container chưa ready hoặc connection pool cạn.
- Current time, timezone, random data hoặc UUID chưa được kiểm soát.
- `@DirtiesContext` làm context khác bị close khi đang sử dụng.
- Incorrect assumptions về transaction/thread boundary.
- Message consumer/subscriber A đọc mất event mà B đang đợi.
- Mock/shared stub setup bị test khác reset.
- File/temp directory/system property/environment state không được restore.

Một test có failure 1/1000 có thể là lỗi nghiêm trọng. Đừng đổi assertion yếu đi, tăng timeout không có căn cứ, hoặc bật retry để build xanh mà không tìm root cause.

### 2.2. Order dependency khác race

**Order dependency**: chạy A→B PASS, chạy B→A FAIL. Không cần hai tests overlap. Ví dụ:
- A tạo entity mà B không tự seed.
- A set System property `feature.enabled=true` và không restore.
- A populate Redis cache, B tưởng cache luôn warm.
- B giả định table sequence bắt đầu từ 1 nhưng A đã insert rows.
- A set static field đã bị B đọc lại.

**Race condition**: kết quả phụ thuộc interleaving của nhiều operations cạnh tranh. Ví dụ:
- Hai threads cùng đọc `balance=100` rồi ghi `balance=90`, làm mất một debit.
- Hai consumers cùng thấy `eventId` chưa tồn tại rồi đều xử lý side effect.
- Spring test class A xóa cache/singleton trong lúc B đang dùng.
- B đọc shared List khi A còn ghi.
- Một assertion kiểm DB trước khi async transaction commit.

Một lỗi có thể chứa **cả hai**: fixture state leak khiến xác suất race cao hơn.

### 2.3. Data race Java Memory Model vs transaction race

Trong Java, một **data race** liên quan accesses tới cùng memory location từ threads không được đồng bộ đúng, trong đó có ít nhất một write. Có thể dẫn tới stale visibility, lost increments hoặc các quan sát không hợp lý do Java Memory Model.

Trong database, race như **lost update** có thể xảy ra giữa nhiều transactions/clients dù Java thread-local state an toàn. Đây là vấn đề transaction isolation và concurrency control. Gắn `volatile` vào Java field **không sửa** lost update của hai JDBC connections. Tương tự, database unique constraint **không sửa** shared Java HashMap không thread-safe.

Phải xác định tài nguyên shared đang là:
- Java heap object;
- JDBC row/transaction;
- Redis key;
- Kafka consumer group/offset;
- filesystem path;
- HTTP session/cache;
- environment/System properties;
- Spring ApplicationContext/bean definition;
- external service quota.

### 2.4. False positive do assert quá sớm

~~~java
asyncService.schedule("operation-7");
assertThat(repository.findById("operation-7")).isEmpty();
~~~

Test có thể PASS trước khi worker thực sự chạy; vài mili giây sau worker tạo row. **Không có side effect tại thời điểm đọc** không chứng minh rằng side effect sẽ không xuất hiện. Cần completion signal hoặc observation window phù hợp contract. Với transactional operations, assertion quan trọng nhất thường nằm **sau** commit/rollback của tất cả workers liên quan.

## 3. Ba trục kiểm thử: repeat, shuffle, parallel

| Trục | Điều nó thay đổi | Bắt được loại bug nào? | Điều không chứng minh |
| --- | --- | --- | --- |
| `@RepeatedTest(n)` | Số lần cùng test chạy | Timing flake, state leak, occasional failure | Không tự tạo same-time race |
| Method order random | Thứ tự methods trong một class | Dependency vào fixture/shared state trong class | Không bắt buộc thay class order |
| Class order random | Thứ tự top-level classes | Dependency dữ liệu/cache/context giữa classes | Không áp thread scheduling |
| Surefire `runOrder=random` | Thứ tự test classes của Surefire | Class-level order dependence | Không trực tiếp random thứ tự Jupiter methods |
| Parallel classes | Nhiều classes có thể overlap | Shared DB/cache/singleton/global races | Không bảo đảm đúng micro-interleaving |
| Parallel methods | Nhiều methods cùng class overlap | Test instance/shared fixture races | Có thể phá fixture nếu chưa isolate |
| Explicit barrier | Ép một interleaving cụ thể | Lost update, check-then-act, TOCTOU | Không chứng minh mọi interleavings đã được kiểm |
| Stress/soak nhiều lần | Nhiều runs, load/time dài | Hiếm gặp, pool/resource leak | Không thay thế proof của invariant |

Chiến lược tốt: **tái hiện có kiểm soát trước**, sau đó random/parallel/regression lâu dài.

## 4. Chạy lặp trong JUnit Jupiter

### 4.1. @RepeatedTest và lifecycle

~~~java
@RepeatedTest(value = 20,
        name = "repetition {currentRepetition}/{totalRepetitions}")
void repeatInFreshFixture(RepetitionInfo repetition) {
    assertThat(repetition.getCurrentRepetition())
            .isBetween(1, 20);
}
~~~

Đây là snippet; cần imports JUnit và AssertJ. Mỗi repetition được JUnit Jupiter xử lý như một test invocation:
- Gọi `@BeforeEach` trước repetition.
- Gọi `@AfterEach` sau repetition.
- Parameter resolution/extensions vẫn hoạt động.
- Theo default `@TestInstance(PER_METHOD)`, có test instance mới cho mỗi invocation.
- Nếu test class dùng `@TestInstance(PER_CLASS)`, instance fields có thể tồn dư qua repetitions; phải reset hoặc thiết kế thread-safe.
- `@SpringBootTest` **không tạo ApplicationContext mới mỗi repetition**; Spring TestContext thường reuse context theo cache key.

Khi muốn cô lập dữ liệu, tạo fixture riêng ở `@BeforeEach` và cleanup trong `@AfterEach`. Không suy “test instance mới = DB sạch”.

### 4.2. RepetitionInfo

`RepetitionInfo` cho biết current/total repetitions và các thông tin về failure threshold theo JUnit version. Hữu ích để đưa số lần vào test display name/log. Không dùng repetition number làm **business idempotency key** nếu multiple test classes/forks có thể tạo cùng giá trị; ghép với unique namespace hoặc UUID khi cần.

### 4.3. failureThreshold

JUnit Jupiter 5.10+ có:

~~~java
@RepeatedTest(value = 100, failureThreshold = 1)
void stopAfterFirstRepro() {
    // ...
}
~~~

Nếu một repetition FAIL, các repetitions tiếp theo có thể được skip theo threshold. Cấu hình này tiện cho **triage**: chỉ cần một failure để xác định có lỗi. Với parallel repetitions, JUnit docs cảnh báo threshold khó được bảo đảm như sequential; nên dùng `@Execution(SAME_THREAD)` nếu dựa vào failure threshold.

Khi muốn đo tỷ lệ/độ ổn định qua mọi lần chạy, không set threshold = 1; để các repetitions chạy hết và thu reports. Một lần PASS sau FAIL không chứng minh bug tự hết.

### 4.4. Repetition không phải rerunFailingTestsCount

- `@RepeatedTest(20)`: **chủ động** chạy 20 invocations ngay cả khi test bình thường PASS.
- Surefire `rerunFailingTestsCount=2`: chỉ rerun **failures** theo provider/plugin; có thể đánh dấu flake trong report khi lần sau PASS.
- Loop trong code `for (i=0; i<100; i++) ...`: chỉ là một JUnit test method, lifecycle/fixture không tự reset mỗi iteration.

Trong CI, không dùng rerun failures để biến failure ban đầu thành “không sao”. Xem Surefire XML, `flake` count và giữ artifacts lần FAIL đầu.

### 4.5. Lặp lại một suite đầy đủ

~~~bash
mvn -q clean test
mvn -q test
mvn -q test
~~~

Ba lệnh là ba executions độc lập. Nếu Surefire dùng forked JVM, cached context/static state thay theo fork; external DB/container có thể tồn tại hay không tùy ownership. Dùng CI matrix/stress job để lặp nhiều runs, lưu seed/config và failure reports. Không diễn giải `mvn test` trên cùng working directory là môi trường luôn sạch nếu có state trong filesystem hoặc reusable containers.

## 5. Xáo trộn thứ tự để tìm dependency ngầm

### 5.1. Mặc định của JUnit không phải random mỗi run

JUnit Jupiter mặc định sắp xếp methods/classes bằng thuật toán **deterministic nhưng cố ý khó đoán**. Nó không cam kết alphabetic hoặc source order; mục đích là lặp lại được. Một số người tưởng Java reflection/source order là contract; giả định đó sai.

Khi muốn chủ động xáo trộn:

~~~java
@TestMethodOrder(MethodOrderer.Random.class)
class OrderIndependentTest {
    @Test void createsOwnFixture() { }
    @Test void readsOnlyOwnFixture() { }
}
~~~

Code trên là snippet. `MethodOrderer.Random` random thứ tự **methods trong class**; không đụng lịch chạy hai worker threads bên trong một method.

### 5.2. Random class order

Trong `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
~~~

Các cấu hình này random **test discovery order**, không biến `@Order` business processing thành thứ tự ngẫu nhiên. `ClassOrderer.Random` không bảo đảm classes được **bắt đầu thực tế** theo đúng thứ tự đã sort khi JUnit parallel scheduling được bật.

### 5.3. Seed tái hiện được

JUnit cung cấp:

~~~properties
junit.jupiter.execution.order.random.seed=4242026
~~~

Cùng seed + cùng test plan/discovery inputs thường tái hiện thứ tự pseudo-random. Nếu thêm/bớt/rename tests hoặc thay engine/version, đừng đòi cùng thứ tự tuyệt đối chỉ vì seed không đổi. Khi một CI job FAIL, lưu:
- Seed.
- Maven/Gradle command.
- JUnit version và discovery set.
- JVM/forks/parallelism.
- Test methods/classes thực thi.
- Relevant thread/request correlation and DB state.

Nếu không cấu hình seed, random orderer có thể chọn seed mặc định; hãy ghi lại seed được logging ở mức JUnit `CONFIG` nếu muốn replay.

### 5.4. Surefire runOrder khác Jupiter MethodOrderer

~~~bash
mvn -q -Dsurefire.runOrder=random test
~~~

`surefire.runOrder=random` yêu cầu Maven Surefire random hóa thứ tự test **classes** do plugin chạy. Thứ tự **methods** bên trong class là chuyện của JUnit Jupiter orderers.

Đừng viết `mvn -Dsurefire.runOrder=random` rồi tuyên bố đã xáo trộn mọi methods và interleavings. Khi dùng parallel forks, chính thứ tự bắt đầu thực tế còn phụ thuộc scheduler.

### 5.5. Không dùng @TestMethodOrder để che bug

Một test suite:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileWorkflowTest {
    @Test @Order(1) void createsRecord() { }
    @Test @Order(2) void updatesRecordFromPreviousTest() { }
    @Test @Order(3) void deletesRecordFromPreviousTest() { }
}
~~~

có thể là một **scenario workflow tích hợp có thứ tự chủ đích**, nhưng không phải ba independent tests. Nếu một test được chạy riêng thì thiếu prerequisite. Cách tốt hơn thường là **một test method** mô tả toàn bộ workflow, hoặc mỗi method tự tạo fixture/cleanup. Đừng dùng `@Order` để làm những tests vốn kỳ vọng độc lập phụ thuộc lẫn nhau.

### 5.6. Dấu hiệu của order-dependent test

- Test chỉ PASS khi một method khác chạy trước.
- Chạy với `-Dtest=MyTest#singleMethod` FAIL.
- Class B chỉ PASS sau class A.
- Thêm `@DirtiesContext` vào một class làm class khác PASS/FAIL khác.
- Đổi seed làm test luôn FAIL cho một thứ tự.
- Test mới tự tạo mock setup khi chạy suite nhưng khi chạy riêng thì stub không tồn tại.

Kiểm ngay static fields, Spring singleton bean state, DB/cache data, System properties, timezone, mocked beans và Spring TestContext cache.

## 6. Parallel execution trong JUnit 5

### 6.1. Bật hai cấu hình khác nhau

Để chạy **methods** và **classes** đồng thời:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
~~~

Nếu chỉ bật `enabled=true` mà không chọn execution mode thích hợp, các nodes vẫn có thể chạy sequential theo default `SAME_THREAD`.

Để **classes parallel nhưng methods trong mỗi class sequential**, mô hình dễ kiểm soát hơn:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=3
~~~

Trong lab, dùng cấu hình này. Hai test classes có thể chạy đồng thời nhưng mỗi class tự xử lý `@BeforeEach`/`@AfterEach` lần lượt. **Race test vẫn chủ động tạo hai application worker threads bên trong method**, nên không phụ thuộc việc Jupiter chạy methods song song.

### 6.2. @Execution

~~~java
@Execution(ExecutionMode.CONCURRENT)
class ParallelSafeTests {
    // Chỉ phù hợp nếu fixtures/data/beans thread-safe.
}
~~~

`@Execution` là control ở Jupiter test node. Không tự chuyển toàn ứng dụng Spring thành thread-safe. Phải bật parallel engine và chọn default/config hợp lệ.

Nếu một class cần giữ methods sequential:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class SharedFixtureTests {
}
~~~

Chỉ làm vậy khi contract có lý do; mục tiêu dài hạn vẫn là mỗi test độc lập. `@RepeatedTest` có `failureThreshold` nên thận trọng khi bật concurrent repetitions.

### 6.3. @ResourceLock

JUnit Jupiter `@ResourceLock` khai báo shared resource mà test tác động:

~~~java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
@Test
void changesPropertyTemporarily() {
    // write System.setProperty(...) và restore trong finally
}
~~~

- `READ_WRITE`: exclusive lock đối với những tests khai báo cùng resource key.
- `READ`: có thể cùng đọc với readers khác nhưng không với writers.
- Lock được Jupiter engine giữ qua `@BeforeEach`/test/`@AfterEach`, không chỉ body.
- Lock quản lý **đồng bộ giữa JUnit tests cùng engine và cùng resource naming contract**.
- Nó không khóa arbitrary application threads, processes/JVMs khác hoặc external actors. Nếu test khác đụng System properties nhưng không khai báo lock, bạn vẫn có race.

Có thể khai báo user-defined resource name:

~~~java
@ResourceLock(value = "test-db:shared-schema",
              mode = ResourceAccessMode.READ_WRITE)
class SharedSchemaExclusiveTests {
}
~~~

Code là snippet, không phải database-level advisory lock. Resource lock là coordination giữa tests, không thay database lock.

### 6.4. @Isolated

`@Isolated` chỉ định một test class cần chạy tách biệt với các classes khác trong **cùng JUnit engine execution**, hữu ích khi việc thay đổi global JVM state không thể chia thành resource keys hẹp. Nó làm giảm throughput, nên ưu tiên cô lập fixture hoặc `@ResourceLock` chính xác.

`@Isolated` không thay Docker namespaces, không bảo đảm không có JVM khác chạy, và không sửa race trong business code. Spring TestContext docs khuyến nghị không parallelize các tests dùng `@DirtiesContext` hoặc `@MockitoBean`/`@MockitoSpyBean`, cũng như tests sửa shared external services mà không isolate.

### 6.5. Class order + parallel scheduling

Khi bật random class order và parallel classes, thứ tự ban đầu được sắp nhưng **thời điểm class thực sự bắt đầu** do execution scheduler quyết định. Đừng assert “class A đã chạy trước class B” bằng cách quan sát một shared static boolean. Tests phải đúng dù start/finish interleave.

### 6.6. Số threads và CI resources

Cấu hình `fixed.parallelism=3` không có nghĩa chỉ có đúng ba threads toàn JVM. Spring applications/executors, Hikari housekeeper, Kafka listeners, JUnit worker pool và GC còn có threads khác. Hikari pool size/DB connection limits phải phù hợp; quá nhiều parallel tests có thể gây timeout do **resource contention** thay vì data race.

## 7. Những bẫy của Spring Boot khi chạy song song

### 7.1. ApplicationContext cache là shared state

`@SpringBootTest` có thể reuse cùng `ApplicationContext` giữa nhiều methods/classes. Điều này tốt cho hiệu năng nhưng:
- Singleton services có fields mutable.
- CacheManager/Redis caches giữ state.
- DataSource và pools dùng chung.
- @MockitoBean replacements có thể bị reset/changed.
- Embedded databases giữ rows nếu không rollback/cleanup.
- Testcontainers backends có thể phục vụ cùng lúc nhiều classes.

Spring Framework 6.2 có context cache static trong JVM, mặc định tối đa 32 contexts với LRU. Context cache hit không có nghĩa dữ liệu sạch. Và nhiều forks sẽ có nhiều static caches riêng.

### 7.2. @DirtiesContext không phải isolation mặc định

`@DirtiesContext` đánh dấu context cần loại khỏi cache/đóng. Nếu class A close context khi class B còn dùng nó parallel, B có thể thấy `ApplicationContext ... no longer active` hoặc client đã bị destroy. Spring docs cảnh báo nhóm tests này **không nên chạy parallel** nếu không có kiểm soát đặc biệt. Không thêm @DirtiesContext bừa để giải quyết data contamination.

### 7.3. @MockitoBean/@MockitoSpyBean và parallel tests

Trong Spring Framework 6.2, `@MockitoBean`/`@MockitoSpyBean` thay bean trong context. Mock reset/stubbing từ hai tests dùng cùng context có thể xung đột. Spring TestContext docs xếp các tests có bean overrides vào nhóm nên tránh parallel execution khi không có isolation. Với unit/slice tests, giảm full-context bean sharing hoặc tách configurations phù hợp.

### 7.4. Test-level @Transactional không bao phủ worker thread

Spring TestContext `@Transactional` trên test method thường mở **test-managed transaction** bind vào current thread, rollback khi test hoàn tất. Nếu test:
1. Insert fixture trong test transaction chưa commit.
2. Submit worker thread.
3. Worker chạy JDBC transaction **khác**.
4. Worker không thấy fixture chưa commit hoặc test rollback không undo worker changes.

Điều này không phải bug Java hay H2: transaction state của Spring JDBC imperative dùng `ThreadLocal`. Đừng kỳ vọng `@Transactional` tự propagate sang `ExecutorService`, `@Async` hoặc JUnit preemptive timeout thread.

Lab cố ý **không gắn `@Transactional` trên test class**, nên setup và cleanup commit thật; các workers đọc được ID đã seed.

### 7.5. Preemptive timeout càng dễ gây sai suy luận

Spring docs cảnh báo dùng `assertTimeoutPreemptively(...)` trong test-managed transaction có thể chạy test body trên thread khác không tham gia transaction ban đầu, nên writes không bị rollback như kỳ vọng. Khi test transaction semantics, ưu tiên bounded `Future.get(timeout)`/non-preemptive timeout với kiến trúc rõ, và kiểm committed state sau completion.

### 7.6. @Sql và database cleanup

`@Sql` rất tiện seed/cleanup, nhưng chạy `TRUNCATE all tables` trên DB shared khi classes parallel có thể xóa fixtures của test khác. Mỗi test nên sở hữu:
- Unique business key/namespace.
- Transaction boundary rõ.
- Setup có commit/visibility đúng.
- Targeted cleanup `WHERE id = ...`.
- Hoặc schema/database/container riêng cho test cần global reset.

Không dùng `@DirtiesContext` để thay cho DB isolation.

### 7.7. Testcontainers và shared infrastructure

Dùng chung PostgreSQL/Redis/Kafka có lợi cho hiệu năng, nhưng:
- Hai tests cùng topic/group/queue có thể nhận nhầm messages.
- Kafka offset từ test trước làm test sau bỏ mất event.
- Redis `FLUSHALL` phá test khác.
- Postgres unique key/sequence có state tồn dư.
- JUnit `static @Container` per-class có thể stop trước khi cached Spring context đóng.
- Docker startup/readiness chậm có thể gây timeout không liên quan business race.

Phân biệt **container lifetime**, **client connection lifetime**, **data isolation**, **JUnit class lifetime** và **Spring context lifetime**. Dùng Spring-managed container beans khi muốn context cache sống đồng bộ với backend.

## 8. Phân tích race condition bằng lịch thực thi

### 8.1. Lost update: trường hợp kinh điển

Ban đầu:

~~~text
counter = 0
~~~

Hai workers cùng gọi:

~~~text
read counter
compute counter + 1
write counter
~~~

Lịch thực thi tạo lỗi:

~~~text
Time    Worker A                    Worker B                Database
----    --------                    --------                --------
T0                                                          value = 0
T1      SELECT -> 0
T2                                  SELECT -> 0
T3      compute 1
T4                                  compute 1
T5      UPDATE value=1
T6                                  UPDATE value=1
T7                                                          value = 1 (sai)
~~~

Mong đợi sau hai operations là 2; thực tế 1. Test chạy tuần tự chỉ thấy 2, nên không phát hiện. Một barrier đặt **sau SELECT và trước UPDATE** có thể tạo đúng interleaving này một cách deterministic.

### 8.2. Check-then-act / TOCTOU

Ví dụ:

~~~java
if (!repository.existsById(operationId)) {
    externalGateway.charge(operationId);
    repository.saveReceipt(operationId);
}
~~~

Hai workers có thể cùng thấy `exists=false` rồi cùng charge. Đây là **time of check to time of use race**. Không giải quyết bằng `existsById` thêm một lần; cần atomic claim/unique constraint/idempotency key, và external payment/provider idempotency khi có side effect ngoài DB.

### 8.3. Read-modify-write của Java field

~~~java
private int counter;

void increment() {
    counter++;
}
~~~

`counter++` gồm read, compute, write; không atomic. Có thể dùng `AtomicInteger.incrementAndGet()` hoặc locking tùy invariant. `volatile int counter` chỉ giúp visibility, **không biến ++ thành atomic**. Test concurrency phải kiểm đúng Java heap resource, khác với JDBC example của lab.

### 8.4. ConcurrentMap không tự bảo vệ compound operation

~~~java
if (!map.containsKey(key)) {
    map.put(key, create());
}
~~~

Ngay cả khi map là `ConcurrentHashMap`, check-then-put ở hai operations riêng có race. Với contract phù hợp, `computeIfAbsent`/`putIfAbsent` có atomic mapping semantics hơn (lưu ý side effects và mapping function caveats). Tương tự Redis dùng `SET key value NX`/Lua transactions, database dùng unique index/CAS/upsert/locks.

### 8.5. Double publish, double charge, double ack

Two workers có thể:
- Cùng publish event.
- Cùng gửi email.
- Cùng cập nhật một inventory row.
- Cùng xử lý message redelivery.
- Cùng mark job DONE nhưng một path chưa hoàn tất side effects.

Tìm **business operation identity** cố định qua retries, một durable idempotency record và transaction boundary rõ. `synchronized` chỉ khóa trong một JVM nên không đủ cho multi-instance Spring Boot cluster.

### 8.6. Deadlock cũng là concurrency bug

Hai transactions cùng khóa A/B nhưng thứ tự trái nhau:
- Worker 1 lock row A rồi chờ B.
- Worker 2 lock row B rồi chờ A.

Database có thể chọn victim rollback một transaction. Test cần kiểm retry policy, lock ordering và bounded waits; không giả định tất cả concurrency failures chỉ gây lost update.

### 8.7. Race hay scheduling flake?

Nếu test fail vì chưa thấy event sau 50 ms, chưa biết đó là:
- Worker chưa chạy vì executor bận.
- Worker đã chạy và rollback.
- Message được gửi vào queue khác.
- Data race.
- Assertion đọc DB trước commit.
- Eventual consistency lag.

Dùng correlation ID/event ID, completion signals, logs/metrics đúng layer và kiểm durable state. Đừng gọi tất cả là “race” khi chưa có interleaving evidence.

## 9. Ép interleaving bằng CountDownLatch thay vì sleep

### 9.1. Barrier sau read

Một `CountDownLatch(2)` trong test đóng vai trò:
1. Worker A đọc giá trị hiện tại.
2. Worker B cũng đọc giá trị hiện tại.
3. Cả hai gọi `countDown()`.
4. Cả hai chờ `await(timeout)` tới khi đủ 2.
5. Chỉ lúc đó mới được UPDATE.

Với giá trị ban đầu 0, cả A và B đã cùng lưu local `before=0`, nên hai UPDATE sẽ ghi 1. Đây là **test của một interleaving cụ thể**, không dựa vào vận may scheduler.

### 9.2. Cần hai mức gate

- **Start gate**: dùng `ready=CountDownLatch(2)` + `start=CountDownLatch(1)` để đảm bảo hai tasks đã sẵn sàng trước khi bắt đầu.
- **After-read gate**: dùng `CountDownLatch(2)` để đảm bảo cả hai đã đọc cùng state trước write.

Không dùng shared mutable boolean non-volatile làm gate vì chính nó có thể là một Java data race. `CountDownLatch`/`CyclicBarrier`/`Phaser` có memory synchronization guarantees phù hợp.

### 9.3. Timeout hữu hạn và teardown

Mọi `await/get` cần timeout hữu hạn:
- Nếu worker throw trước khi count down, thread kia không treo mãi.
- Nếu CI thiếu CPU, test trả lỗi có thông điệp thay vì block vô hạn.
- `Future.get(timeout)` propagate failure thật từ worker.
- `ExecutorService` phải shutdown trong `finally`.
- Cleanup/connection release không diễn ra khi workers vẫn còn chạy.

Có thể dùng Awaitility để chờ **điều kiện eventual**, nhưng đừng dùng polling để ép two-read barrier chính xác. Barrier giúp tái hiện bug; polling giúp đợi state hội tụ.

### 9.4. Barrier có thể làm deadlock nếu đặt nhầm nơi

Nếu hai workers đang nằm trong **một khóa độc quyền** khi gặp barrier, worker A giữ lock và chờ B, B cần lock để tới barrier → deadlock/timed out. Đặt gate **trước** lấy lock hoặc tại boundary không giữ lock nếu mục tiêu là ép cả hai cùng đọc.

Lab dùng JDBC auto-commit cho `unsafeIncrement`, không mở outer transaction giữ lock qua barrier; H2 two SELECTs không tranh row write lock tại điểm đọc. Sau đó fixed SQL atomic update tự serialize đúng ở database.

## 10. Dự án Maven: tái hiện lost update và hai cách sửa

### 10.1. Mô hình

Một bảng `demo_counters` lưu `counter_id` và `current_value`. Có ba algorithms:

1. **Unsafe read-then-overwrite**: đọc `current_value`, gọi `afterReadGate.run()`, ghi `old+1`. Test ép cả hai workers đọc cùng 0 → final 1.
2. **Atomic SQL increment**: `UPDATE demo_counters SET current_value = current_value + 1 WHERE counter_id = ?`. Database thực hiện increment trong một SQL write operation, hai updates cùng ID → final 2 (khi không có lỗi connection/transaction khác).
3. **Optimistic compare-and-set**: đọc current, rồi `UPDATE ... WHERE current_value = expected`. Chỉ một worker thắng khi cả hai đọc 0. Caller thua phải reload/retry theo policy. Test kiểm đúng một success và sau một retry mới đạt 2.

Đây là database race. Nó không cố gắng chứng minh Java heap `AtomicInteger` hay production PostgreSQL isolation mode. Code production nên đặt concurrency invariant ở database/transaction boundary hoặc một distributed coordinator phù hợp, không chỉ phụ thuộc synchronized Java object.

### 10.2. Cây thư mục

~~~text
test-order-and-races-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/racelab/
│   │   ├── RaceLabApplication.java
│   │   ├── CounterRepository.java
│   │   └── CounterService.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/
    ├── java/com/example/racelab/
    │   ├── CounterRaceIntegrationTest.java
    │   ├── OrderIndependentIntegrationTest.java
    │   └── SystemPropertyIsolationTest.java
    └── resources/junit-platform.properties
~~~

`src/test/resources/junit-platform.properties` bật class-level parallel + random order để suite **thật sự** trải nghiệm hai trục này. Mỗi test method trong các Spring classes vẫn có fixture riêng, không dùng `@DirtiesContext`, không sửa mock bean toàn cục.

### 10.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>test-order-and-races-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
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
~~~

Maven parent quản lý Spring Framework, Spring JDBC, Hikari, H2, JUnit Jupiter, AssertJ và Surefire versions tương thích. Không cần `spring-boot-starter-web` vì lab không chạy HTTP server. JDK 17+ và Maven được yêu cầu; Docker không cần vì backend là H2 memory database.

### 10.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=test-order-and-races-lab
spring.main.web-application-type=none

spring.datasource.url=jdbc:h2:mem:race_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=6
spring.datasource.hikari.connection-timeout=10000

spring.sql.init.mode=always
~~~

Hikari pool size 6 đủ cho hai worker threads cộng main/test queries trong lab. Cấu hình H2 `DB_CLOSE_DELAY=-1` giữ in-memory DB sống trong JVM tới khi shutdown, **không làm tự sạch giữa test classes**. Đây là lý do mỗi fixture dùng UUID riêng.

H2 có concurrency/isolation khác PostgreSQL/MySQL. Dùng project này để học cơ chế và chứng minh SQL logic; nếu cần guarantee production DB, viết thêm Testcontainers integration với đúng RDBMS/schema/migration.

### 10.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS demo_counters (
    counter_id VARCHAR(90) PRIMARY KEY,
    current_value INTEGER NOT NULL
);
~~~

Primary key ngăn duplicate counter IDs. Nó **không** tự ngăn lost update nếu application đọc rồi overwrite một row không có CAS/lock. Đây là hai invariants khác nhau: uniqueness của row và correctness của updates.

### 10.6. RaceLabApplication.java

`src/main/java/com/example/racelab/RaceLabApplication.java`:

~~~java
package com.example.racelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RaceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RaceLabApplication.class, args);
    }
}
~~~

Class main là Spring Boot bootstrap. Không thêm `@EnableScheduling` hoặc `@Async` vào lab; các test tạo worker threads có chủ đích bằng `ExecutorService`.

### 10.7. CounterRepository.java

`src/main/java/com/example/racelab/CounterRepository.java`:

~~~java
package com.example.racelab;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CounterRepository {

    private final JdbcTemplate jdbc;

    public CounterRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String id, int initialValue) {
        jdbc.update(
                "INSERT INTO demo_counters "
                        + "(counter_id, current_value) "
                        + "VALUES (?, ?)",
                id, initialValue);
    }

    public int value(String id) {
        Integer current = jdbc.queryForObject(
                "SELECT current_value FROM demo_counters "
                        + "WHERE counter_id = ?",
                Integer.class,
                id);
        return Objects.requireNonNull(current);
    }

    public void overwrite(String id, int newValue) {
        int affected = jdbc.update(
                "UPDATE demo_counters SET current_value = ? "
                        + "WHERE counter_id = ?",
                newValue, id);
        if (affected != 1) {
            throw new IllegalArgumentException(
                    "Unknown counter: " + id);
        }
    }

    public int incrementAtomically(String id) {
        return jdbc.update(
                "UPDATE demo_counters "
                        + "SET current_value = current_value + 1 "
                        + "WHERE counter_id = ?",
                id);
    }

    public int compareAndSet(
            String id, int expected, int next) {
        return jdbc.update(
                "UPDATE demo_counters SET current_value = ? "
                        + "WHERE counter_id = ? AND current_value = ?",
                next, id, expected);
    }

    public void delete(String id) {
        jdbc.update(
                "DELETE FROM demo_counters WHERE counter_id = ?",
                id);
    }
}
~~~

Không có `@Transactional` ở repository/service. Trong lab, JdbcTemplate statements được thực thi theo JDBC auto-commit thông thường, giúp ta ép interleaving **giữa SELECT và UPDATE** mà không giữ transaction-level row lock qua barrier.

Trong một transaction thật, `SELECT ... FOR UPDATE` hoặc isolation/optimistic locking có thể thay behavior, nhưng chỉ thêm `@Transactional` thông thường không luôn là cách sửa lost update. Phải hiểu isolation của DB và conflict detection.

### 10.8. CounterService.java

`src/main/java/com/example/racelab/CounterService.java`:

~~~java
package com.example.racelab;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final CounterRepository counters;

    public CounterService(CounterRepository counters) {
        this.counters = counters;
    }

    /**
     * Cố ý chứa race để minh họa.
     * Không sử dụng read-then-overwrite này cho counter production.
     */
    public void unsafeIncrement(
            String id, Runnable afterReadGate) {

        int seen = counters.value(id);
        Objects.requireNonNull(afterReadGate).run();
        counters.overwrite(id, seen + 1);
    }

    /**
     * Một SQL operation cập nhật tại database.
     */
    public void atomicIncrement(String id) {
        int affected = counters.incrementAtomically(id);
        if (affected != 1) {
            throw new IllegalArgumentException(
                    "Unknown counter: " + id);
        }
    }

    /**
     * Compare-and-set một lần, caller thua conflict
     * sẽ nhận false để reload/retry ở boundary phù hợp.
     */
    public boolean compareAndSetIncrementOnce(
            String id, Runnable afterReadGate) {

        int seen = counters.value(id);
        Objects.requireNonNull(afterReadGate).run();
        return counters.compareAndSet(
                id, seen, seen + 1) == 1;
    }
}
~~~

**Điểm thiết kế:**
- `afterReadGate` là seam chủ động tạo interleaving trong test. Ở production không cần truyền gate; nếu vẫn giữ seam này, có thể tách implementation/failure hook để tránh API bị lộ test mechanics.
- Unsafe method cố ý không atomic.
- Atomic method để database tự tính `current_value + 1` trong write operation, không truyền stale `seen` từ application.
- CAS method dùng `WHERE current_value = expected`, trả false khi dữ liệu đã thay đổi kể từ lúc đọc; caller phải quyết định retry hoặc báo conflict.
- Không catch transaction/data access exceptions rồi tự xem operation thành công.

### 10.9. junit-platform.properties

`src/test/resources/junit-platform.properties`:

~~~properties
# Xáo trộn thứ tự methods/classes.
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random

# Cho phép các class khác nhau chạy song song,
# nhưng giữ methods trong từng class chạy tuần tự.
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=3
~~~

Một số lưu ý:
- Chưa pin seed, nên mỗi suite execution có thể chọn order khác.
- Có thể override seed bằng JVM/test execution configuration để replay.
- Random method ordering không chứng minh every possible order đã được thử.
- Parallel methods **không** được bật mặc định trong config này; race test tạo hai workers bên trong mỗi method.
- Spring tests dùng shared ApplicationContext/DB nhưng fixtures **mỗi method có ID riêng**.
- Test class nào sửa global resources phải dùng `@ResourceLock` hoặc isolation phù hợp.
- Nếu production CI không cho phép parallel tests dùng shared DB, tách class-level parallel suite khỏi tests mutation hoặc chuyển sang per-test schema/database.

### 10.10. CounterRaceIntegrationTest.java

`src/test/java/com/example/racelab/CounterRaceIntegrationTest.java`:

~~~java
package com.example.racelab;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
@TestMethodOrder(MethodOrderer.Random.class)
class CounterRaceIntegrationTest {

    @Autowired
    CounterRepository repository;

    @Autowired
    CounterService service;

    private String id;

    @BeforeEach
    void seedFreshCounter() {
        id = "race_" + UUID.randomUUID()
                .toString().replace("-", "");
        repository.insert(id, 0);
    }

    @AfterEach
    void cleanupOnlyThisCounter() {
        repository.delete(id);
    }

    /**
     * Ép hai workers đã đọc trước khi bất kỳ worker
     * nào được tiếp tục tới bước UPDATE.
     */
    private static final class TwoReaderBarrier
            implements Runnable {

        private final CountDownLatch bothRead =
                new CountDownLatch(2);

        @Override
        public void run() {
            bothRead.countDown();

            try {
                if (!bothRead.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "both-read gate timed out");
                }
            }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "interrupted waiting for both reads",
                        interrupted);
            }
        }
    }

    /**
     * Hai tasks cùng sẵn sàng trước khi bắt đầu.
     * Dùng Future.get(timeout) để propagate exceptions.
     * Không có Thread.sleep hoặc mutable boolean gate.
     */
    private List<Boolean> runTwo(
            Callable<Boolean> operation)
            throws Exception {

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Boolean> task = () -> {
            ready.countDown();

            if (!start.await(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "start gate timed out");
            }

            return operation.call();
        };

        Future<Boolean> first = pool.submit(task);
        Future<Boolean> second = pool.submit(task);

        try {
            assertThat(ready.await(
                    5, TimeUnit.SECONDS)).isTrue();

            start.countDown();

            return List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS));
        }
        finally {
            start.countDown();
            first.cancel(true);
            second.cancel(true);
            pool.shutdownNow();

            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS)).isTrue();
        }
    }

    @RepeatedTest(value = 12,
            name = "lost update repetition {currentRepetition}")
    void deliberatelyUnsafeReadModifyWriteLosesAnUpdate()
            throws Exception {

        TwoReaderBarrier barrier =
                new TwoReaderBarrier();

        List<Boolean> results = runTwo(() -> {
            service.unsafeIncrement(id, barrier);
            return true;
        });

        assertThat(results)
                .containsExactlyInAnyOrder(true, true);

        // Cả hai đã SELECT 0, cả hai UPDATE 1.
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @RepeatedTest(value = 12,
            name = "atomic update repetition {currentRepetition}")
    void atomicSqlUpdatePreservesBothIncrements()
            throws Exception {

        List<Boolean> results = runTwo(() -> {
            service.atomicIncrement(id);
            return true;
        });

        assertThat(results)
                .containsExactlyInAnyOrder(true, true);

        assertThat(repository.value(id)).isEqualTo(2);
    }

    @RepeatedTest(value = 10,
            name = "CAS repetition {currentRepetition}")
    void optimisticCasDetectsConflictAndRetrySucceeds()
            throws Exception {

        TwoReaderBarrier barrier =
                new TwoReaderBarrier();

        List<Boolean> results = runTwo(
                () -> service.compareAndSetIncrementOnce(
                        id, barrier));

        // Hai readers cùng thấy 0:
        // một CAS thành công, một CAS conflict.
        assertThat(results)
                .containsExactlyInAnyOrder(true, false);

        assertThat(repository.value(id)).isEqualTo(1);

        // Retry có read mới, không sử dụng stale value.
        boolean retryAccepted =
                service.compareAndSetIncrementOnce(
                        id, () -> { });

        assertThat(retryAccepted).isTrue();
        assertThat(repository.value(id)).isEqualTo(2);
    }

    @Test
    void singleThreadBaselineDoesNotRevealRace() {

        service.unsafeIncrement(id, () -> { });
        service.unsafeIncrement(id, () -> { });

        assertThat(repository.value(id)).isEqualTo(2);
    }

    @Test
    void atomicIncrementRejectsMissingCounter() {

        repository.delete(id);

        org.assertj.core.api.Assertions
                .assertThatThrownBy(
                        () -> service.atomicIncrement(id))
                .isInstanceOf(
                        IllegalArgumentException.class)
                .hasMessageContaining("Unknown counter");
    }
}
~~~

### 10.11. Vì sao code test này không bị flaky do bản thân fixture?

- `@BeforeEach` gọi trước **mỗi repetition** và tạo UUID khác, không reuse DB key giữa các iterations.
- `@AfterEach` chỉ delete đúng ID đã seed; không xóa global table.
- Test method không có `@Transactional`, nên fixture được commit trước worker threads thực thi.
- `runTwo` dùng two-thread pool, có bounded start gate và `Future.get`.
- `TwoReaderBarrier` đặt sau SELECT của **unsafe** và **CAS** paths, ép cùng seen value.
- SQL atomic update không cần after-read barrier; nó tự bảo vệ DB increment ở statement level.
- `List.of` nhận hai Boolean không-null, nên không bị null element exception.
- Sau khi futures hoàn tất, `repository.value` đọc final committed state.
- `finally` hủy/đóng executor, tránh tasks còn chạy khi cleanup.
- Các test classes khác dùng unique IDs, không ảnh hưởng row này.
- Chỉ có một số invariant cố ý “unsafe final=1” nhằm chứng minh bug; không xem đó là behavior nên đưa production.

### 10.12. Kết quả của mỗi nhóm

**Unsafe lost update** (12 repetitions):
- Hai workers đã đọc 0 nhờ barrier.
- Hai statements UPDATE đều ghi 1.
- Final value = 1 thay vì 2.
- Đây là **red flag được test cố ý tái hiện**, assertion `isEqualTo(1)` chỉ hợp lý trong **bài lab chẩn đoán**. Trong production regression tests, expected phải là business invariant 2 và implementation phải được sửa.

**Atomic SQL** (12 repetitions):
- Mỗi `UPDATE value=value+1` tăng một lần.
- Database serialize concurrent modifications đúng statement semantics.
- Final value = 2.
- Nếu DB unavailable/deadlock/transaction rollback, test nên fail thay vì coi operation đã thành công.

**CAS** (10 repetitions):
- Cả hai đọc cùng expected value 0.
- Một conditional UPDATE ảnh hưởng 1 row; worker còn lại ảnh hưởng 0 row.
- Không có silent lost update; caller thua nhận false.
- Sau khi retry với read mới, final = 2.
- **Không** khuyến nghị retry vòng lặp vô hạn trong production. Có max attempts, backoff và error policy khi contention cao.

**Sequential baseline**:
- Hai calls tuần tự của method unsafe vẫn tạo 2.
- Điều này giải thích vì sao chỉ test một thread không phát hiện race.

**Missing item**:
- Atomic method không silent PASS khi row không tồn tại; xác định contract thành exception.

### 10.13. OrderIndependentIntegrationTest.java

`src/test/java/com/example/racelab/OrderIndependentIntegrationTest.java`:

~~~java
package com.example.racelab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestMethodOrder(MethodOrderer.Random.class)
class OrderIndependentIntegrationTest {

    @Autowired
    CounterRepository repository;

    @Autowired
    CounterService service;

    private String id;

    @BeforeEach
    void createOwnedFixture() {
        id = "order_" + UUID.randomUUID()
                .toString().replace("-", "");
        repository.insert(id, 0);
    }

    @AfterEach
    void deleteOwnedFixture() {
        repository.delete(id);
    }

    @Test
    void freshFixtureAlwaysStartsAtZero() {
        assertThat(repository.value(id)).isZero();
    }

    @Test
    void independentMethodCanIncrementOwnFixture() {
        service.atomicIncrement(id);
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @Test
    void staleCasDoesNotOverwriteNewerValue() {
        int oldValue = repository.value(id);

        service.atomicIncrement(id);

        int updated = repository.compareAndSet(
                id, oldValue, oldValue + 1);

        assertThat(updated).isZero();
        assertThat(repository.value(id)).isEqualTo(1);
    }

    @Test
    void sequenceWithinSingleMethodIsAValidScenario() {
        // Hai thao tác có thứ tự THỰC SỰ thuộc một test.
        service.atomicIncrement(id);
        service.atomicIncrement(id);

        assertThat(repository.value(id)).isEqualTo(2);
    }
}
~~~

Mỗi method tự seed/cleanup, không dùng `@Order` để nhờ method khác làm prerequisite. Random method order có thể thay đổi mà mọi test vẫn có đúng fixture. Đây là ý nghĩa của **order independence**.

Nếu bạn cần scenario “create → update → delete”, đặt chuỗi trong **một test method** (như method cuối) hoặc dùng một fixture builder chủ động. Đừng tạo ba test methods phụ thuộc vào kết quả của nhau rồi ép `@Order(1,2,3)`.

### 10.14. SystemPropertyIsolationTest.java

`src/test/java/com/example/racelab/SystemPropertyIsolationTest.java`:

~~~java
package com.example.racelab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

class SystemPropertyIsolationTest {

    private static final String KEY =
            "racelab.synthetic.test.flag";

    private void changeAndRestore(String value) {
        String previous = System.getProperty(KEY);

        try {
            System.setProperty(KEY, value);
            assertThat(System.getProperty(KEY))
                    .isEqualTo(value);
        }
        finally {
            if (previous == null) {
                System.clearProperty(KEY);
            }
            else {
                System.setProperty(KEY, previous);
            }
        }

        assertThat(System.getProperty(KEY))
                .isEqualTo(previous);
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void propertyWriterOneRestoresOriginalState() {
        changeAndRestore("writer-1");
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void propertyWriterTwoRestoresOriginalState() {
        changeAndRestore("writer-2");
    }
}
~~~

Hai methods cùng khai báo JUnit resource key cho System properties; engine không lên lịch chồng chéo conflicting accesses của chúng. `try/finally` restore state đúng kể cả nếu assertion throw. Lock không thay thế cleanup; cleanup không thay lock khi hai tests có thể cùng mutate resource.

`SystemPropertyIsolationTest` không có `@SpringBootTest` vì test một global JVM resource thuần. Không tạo ApplicationContext chỉ để minh họa `System.setProperty`.

### 10.15. Chạy project

Điều kiện: JDK 17+, Maven, dependencies có thể tải từ Maven repository hoặc cache.

~~~bash
mvn -q clean test

# Chỉ chạy race tests, gồm repeated invocations:
mvn -q -Dtest=CounterRaceIntegrationTest test

# Chạy order-isolation tests:
mvn -q -Dtest=OrderIndependentIntegrationTest test

# Thay seed để tái hiện random class/method order:
mvn -q -Djunit.jupiter.execution.order.random.seed=4242026 test

# Xáo thứ tự test classes do Maven Surefire điều phối:
mvn -q -Dsurefire.runOrder=random test

# Diagnostic reruns: không dùng để che failures trong CI.
mvn -q -Dsurefire.rerunFailingTestsCount=2 test
~~~

**Expected invocations trong suite mẫu:**
- `CounterRaceIntegrationTest`: `12 + 12 + 10` repeated invocations và 2 ordinary tests = **36 test invocations**.
- `OrderIndependentIntegrationTest`: **4** tests.
- `SystemPropertyIsolationTest`: **2** tests.
- Tổng **42 JUnit invocations** nếu mọi test được thực thi theo JUnit/Surefire configuration này, không bị skip và không có retry failure bổ sung.
- “Unsafe final=1” được assert cố ý để chứng minh race; regression production phải thay bằng expected final=2 sau fix.
- Cache/pool/backend giữa các classes chia sẻ Spring configuration nhưng DB keys không trùng.
- Surefire reports nằm trong `target/surefire-reports`.

**QA về thực thi:** Đây là mã dự kiến runnable và được rà soát về imports/API/logic. **Maven và 42 invocations chưa được thực thi trong lúc biên soạn**, nên các kết quả nêu trên là expected behavior, không phải một báo cáo test PASS đã quan sát.

### 10.16. Thực thi nhiều seeds trong CI

Muốn tìm order-dependent bugs, CI có thể tạo nhiều jobs/runs với seeds như 4242026, 4242027, 4242028 và ghi lại seed đã dùng. Mỗi job cần:
- Same code/commit.
- Same test subset và dependency versions.
- Known JVM/Surefire fork and parallel settings.
- Reports, logs và test event IDs.
- Mỗi test data set có namespace riêng.

Nếu muốn hàng chục runs, orchestrate qua CI matrix/driver scripts. Đừng copy một seed duy nhất làm bằng chứng đã bao phủ mọi permutations.

## 11. Đọc dấu vết race condition một cách có hệ thống

### 11.1. Bắt đầu bằng invariant

Với counter:
- Given initial = 0.
- Khi **hai successful increments** độc lập hoàn thành.
- Then final phải = 2.

Lỗi do update bị mất, không chỉ do “two tasks ran at same time”. Định nghĩa invariant theo nghiệp vụ trước khi instrument.

Với inventory:
- Available quantity không âm.
- Hai orders cạnh tranh một item chỉ một được reserve nếu tồn kho 1.

Với payments:
- Một operation ID không được capture hai lần.
- Retry cùng idempotency key trả cùng kết quả, payload conflict bị reject.

Với message consumer:
- Cùng eventId redelivery không tạo hai business effects.
- Offset/ack không commit trước khi DB commit nếu contract yêu cầu at-least-once.

### 11.2. Ghi event timeline

Lưu mỗi operation:
- Synthetic operation ID.
- Worker/thread name.
- Before value, after value.
- Transaction ID hoặc correlation.
- DB update row count.
- Start/finish/commit timestamps **dùng để chẩn đoán, không assert exact wall-clock**.
- Exception/timeout/rollback status.
- Test random seed, repetition number, concurrent pool size.

Ví dụ:

~~~text
case=lost-update seed=4242026 counterId=race_9
A READ 0
B READ 0
A gate passed
B gate passed
B UPDATE 1 affected=1
A UPDATE 1 affected=1
FINAL 1, expected invariant 2
~~~

Nên log **sau khi đã giữ an toàn cho thông tin nhạy cảm**. Không ghi password/authorization tokens/customer data thật vào test logs. Nhớ rằng log order từ nhiều threads có thể khác thực tế commit order do buffering.

### 11.3. Dùng thread dumps

Khi test hangs:
- Dump stack của executor worker threads.
- Xem `WAITING` trên CountDownLatch hoặc `BLOCKED`/lock wait.
- Xem transaction connection pool.
- Xem deadlock detection logs.
- Check timeout nào bị chạm đầu tiên.

Nếu worker A giữ row lock và chờ B tại barrier, B đang chờ lock nên không thể tới barrier — lỗi nằm ở **test synchronization design**, không nhất thiết ở business algorithm.

### 11.4. Chứng minh fix bằng negative và positive paths

Với CAS:
- Hai simultaneous updates: một thành công, một conflict được report.
- Conflict được retry với read mới: final 2.
- Không conflict: increment thành công ngay.
- Row không tồn tại: handle theo contract.
- Retry vượt budget: explicit failure, không infinite loop.
- Payload/time/restart: khi có requirement.

Với atomic SQL:
- Sequential và concurrent.
- N workers, final value = N.
- Transaction rollback case.
- Database-specific isolation/lock timeout.
- Production DB integration if critical.

### 11.5. Cân nhắc Jepsen/linearizability nâng cao

Với hệ thống phân tán quan trọng, lịch sử operations (invocation/response) có thể được kiểm bằng linearizability/concurrency model checking hoặc chaos/fault injection. Lab barrier chứng minh một interleaving cụ thể, **không phải hình thức chứng minh linearizable cho mọi lịch thực thi**.

## 12. Đừng nhầm phép sửa với che lỗi

### 12.1. Thread.sleep chỉ thay xác suất

~~~java
Thread.sleep(200);
assertThat(counter).isEqualTo(2);
~~~

Thêm 200 ms có thể làm test PASS trên laptop nhưng FAIL trên CI bận. Nó không tạo happens-before bảo đảm. Chọn completion signal và concurrency invariant.

### 12.2. Tăng timeout không sửa lost update

Nếu final=1 do overwrite, chờ thêm 30 giây vẫn là 1. Timeout tuning chỉ phù hợp khi vấn đề là resource readiness/latency có budget thực, không phải sai algorithm.

### 12.3. synchronized không bảo vệ nhiều service instances

~~~java
public synchronized void increment(String id) { ... }
~~~

Trong **một JVM và trên cùng object**, synchronized serialize code; trong Kubernetes hai instances có object/monitor khác nhau. Database/Redis/Kafka state vẫn shared. Dùng database atomic SQL, pessimistic/optimistic locking, unique constraints hoặc lease/fencing theo requirement.

### 12.4. volatile không làm compound operation atomic

`volatile int n` tăng visibility, không biến `n++` thành một operation atomic. Dùng `AtomicInteger` cho một counter in-memory hoặc lock để bảo vệ nhiều fields theo invariant. Không lẫn với SQL row concurrency.

### 12.5. Không chỉ dùng @Transactional

Một transaction bao quanh “SELECT→compute→UPDATE” không tự bảo đảm serializable invariant ở mọi isolation levels/databases. Với JPA:
- `@Version` optimistic locking kiểm conflict và yêu cầu transaction retry.
- `@Lock(PESSIMISTIC_WRITE)` có thể serialize row reads/writes.
- Atomic SQL update giảm cửa sổ lost update.
- DB unique index/constraints bảo vệ bất biến.
- Chọn isolation như SERIALIZABLE khi cần, và **handle serialization failures**.

### 12.6. Không bật @DirtiesContext trên mọi test

Với order dependency do global state, `@DirtiesContext` có thể giảm một triệu chứng nhưng làm mất cache reuse, suite chậm và vẫn không dọn Redis/Kafka/DB ngoài Spring context. Fix đúng là fixture isolation, state reset hoặc dedicated context/resource khi có lý do.

### 12.7. Không dùng @Order để ổn định những tests không độc lập

Ép method A chạy trước B có thể khiến build xanh, nhưng test B chạy riêng vẫn fail và parallel suite vẫn có conflict. Gộp scenario nếu thực sự cần thứ tự business, hoặc làm tests tự thiết lập prerequisites.

### 12.8. Không bật Surefire reruns để giấu flaky tests

`rerunFailingTestsCount=2` có thể giúp thu bằng chứng, nhưng nó không sửa bug và có thể làm build trông xanh dù lần đầu FAIL. Với module critical, cấu hình build fail khi flakes vượt budget và báo cáo rõ initial attempts.

### 12.9. Không xóa global DB table để “reset”

Nếu hai classes đang chạy trên shared database, `DELETE FROM all_records` từ test A có thể làm test B fail. Dùng unique IDs/tenant/schema, targeted cleanup, và resource lock chỉ khi thật sự không thể isolate.

### 12.10. Không assert toàn bộ list từ multiple threads theo insertion order

Một concurrent data structure có thể giữ tập đúng nhưng không guarantee order. Test contract nào cần ordering phải nêu mô hình ordering: per-key, per-partition, monotonic sequence, hoặc total order. Đừng vô tình dựa vào scheduler thread interleaving.

## 13. JPA @Version và optimistic locking trong bài toán thực

### 13.1. Entity version field

Một ứng dụng Spring Data JPA có thể dùng:

~~~java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private long version;

    private int available;

    // constructors/getters/behavior omitted for illustration
}
~~~

Đây là **snippet kiến trúc, không phải file trong Maven JDBC lab**. `@Version` giúp Hibernate đưa version check vào UPDATE. Khi hai transactions cùng đọc version 0, chỉ một transaction được phép update theo expected version; transaction còn lại có thể nhận optimistic locking exception ở flush/commit.

**Không** chỉ bắt exception rồi coi hai operations thành công. Nếu business muốn retry, bắt ở **transaction boundary bên ngoài** và mở transaction mới/reload state, giới hạn attempts.

### 13.2. Pessimistic locking

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findLocked(@Param("id") Long id);
~~~

Snippet này cần Spring Data JPA imports và repository definition thực. Lock phải được gọi trong transaction. Trong test hai workers:
- Không đặt CountDownLatch barrier **sau khi worker A đã giữ exclusive lock** rồi đòi worker B cũng đến được barrier.
- Dùng start gate trước lock.
- Assert kết quả sau commit.
- Test lock timeout/deadlock/retry đúng production DB.

### 13.3. Các isolation levels khác nhau

READ_COMMITTED, REPEATABLE_READ và SERIALIZABLE có semantics khác theo database implementation. Một H2 test có thể khác PostgreSQL/MySQL khi concurrent transactions chạy, đặc biệt về deadlocks, MVCC và serialization anomalies. Không tuyên bố H2 đã chứng minh PostgreSQL production guarantee chỉ từ một pass.

### 13.4. CAS trong SQL

Câu lệnh lab:

~~~sql
UPDATE demo_counters
SET current_value = :next
WHERE counter_id = :id
  AND current_value = :expected;
~~~

giúp phát hiện một row đã thay đổi từ lúc đọc. Khi `affectedRows=0`, có thể là conflict hoặc row không tồn tại; nếu cần phân biệt, query lại theo business contract. Với high contention, CAS retry có thể starve; cần budget/backoff/monitoring.

### 13.5. Composite invariants

Atomic increment một row không giải quyết invariant liên quan **hai rows** như chuyển tiền tài khoản A→B. Cần một transaction thích hợp, concurrency controls cho cả hai records và deadlock handling. Viết test contention ở đúng invariant, không lấy một counter demo làm bằng chứng cho mọi hệ thống.

## 14. Redis, messaging, HTTP clients và external concurrency

### 14.1. Redis key collisions

Hai test classes cùng dùng `cache:user:42`:
- A set value, B đọc value của A.
- A `FLUSHDB` trong teardown, B mất fixture.
- TTL test có thể bị data leak từ run trước.

Dùng unique namespace như `it:<runId>:<testId>:cache:user:42`; cleanup theo prefix/key được sở hữu, không xóa cả Redis instance shared.

### 14.2. Kafka groups và message redelivery

Hai listeners cùng consumer group có thể chia partitions, khiến test B không đọc message của mình. Offset commit và broker retention còn tồn tại giữa tests. Dùng unique topic/consumer group/eventId, isolate listener lifecycle, wait for assignment/acks và chống duplicate side effect. Parallel tests với shared Kafka phải kiểm cả sự phân tách dữ liệu lẫn kết quả business.

### 14.3. RabbitMQ queues

Hai tests cùng queue có thể cạnh tranh messages (competing consumers). Nếu test đòi fanout, cần separate queues và bindings. Dùng unique queue/exchange names, explicit cleanup, bounded awaiting, và không assume queue depth = 0 khi consumer chưa finished.

### 14.4. External HTTP stubs

Một WireMock server shared, test A reset all mappings trong lúc test B đang gửi request → 404 hoặc stub mismatch. Có thể:
- Per-test WireMock instance/port;
- Unique URL path/token/request ID;
- Resource lock khi bắt buộc dùng global stub;
- Separate contexts hoặc test extension lifecycle phù hợp.

Đừng gắn `@DirtiesContext` chỉ để chữa một mock server reset race nếu server thuộc một lifecycle khác.

### 14.5. Testcontainers reuse và schema

Một PostgreSQL container dùng chung không tự bảo đảm test isolation. Schema/test data phải được namespace. Container cũng không được stop trước các cached Spring clients. Khi stress tests restart DB container, dùng **dedicated context/container**, không phá shared infrastructure của suite.

### 14.6. Time and scheduler races

`@Scheduled` có thể chạy trong lúc test setup/cleanup khi scheduling vẫn enabled. Trong test:
- Tắt scheduled trigger qua profile hoặc inject fake trigger.
- Gọi job logic bằng public method thủ công.
- Dùng `Clock.fixed` khi kiểm time windows.
- Với `@Async`, dùng completion signal và bounded waits.
- Nếu business cần multi-instance scheduler, kiểm distributed lock/idempotency riêng.

## 15. Đọc kết quả từ Surefire và CI đúng cách

### 15.1. PASS nhưng retries đã xảy ra

Surefire có thể report một test là flake khi initial run FAIL rồi rerun PASS. Đừng chỉ xem exit code; cần:
- XML report với initial failures/rerun results.
- Flaky count.
- Actual number of invocations.
- Known seed/parallelism/forks.
- Thread dumps/logs của first failure.
- Correlation IDs/test data ID.
- Docker/DB/runtime versions.

### 15.2. Test failures với timeout

Một timeout có thể là:
- Pool size thấp hơn concurrency.
- Deadlock ở barrier do giữ DB lock.
- External service readiness.
- Slow CI resource contention.
- Actual infinite loop/deadlock.
- Assertion chờ một event chưa bao giờ được emit.

Log `start gate reached` và `after-read gate reached` bằng safe test IDs giúp phân loại. Không cứ tăng timeout từ 5s lên 300s mà không hiểu.

### 15.3. Không nhầm parallelism và test count

`@RepeatedTest(12)` chạy 12 invocations, dù là một source method. Surefire reports có thể biểu diễn repetitions bằng display names. Khi stress suite phân tán trên nhiều forks, số context/containers cũng khác. Báo cáo theo:
- Source methods.
- JUnit test invocations.
- Number of executions/seeds.
- Failures vs flakes vs skips.

### 15.4. Seed reproducibility không đủ khi race thật

Giữ seed chỉ giúp tái hiện random ordering của JUnit. Thread scheduling/DB transaction timing vẫn nondeterministic. Khi tái hiện race, dùng explicit barriers/failure gates hoặc replayable concurrency harness. Không kỳ vọng `-Dseed=4242026` sẽ tạo đúng same micro-interleaving trên mọi máy.

### 15.5. Trích báo cáo chất lượng

Một báo cáo phù hợp:
- “Randomized order 10 seeds, parallel classes=3, all 42 invocations per run, 0 failures/skips/flakes”.
- “Reproduced lost update deterministically 12/12 attempts with forced two-read gate”.
- “Atomic SQL fix final count 2 on every 12 attempts”.
- “CAS detected conflict in every forced interleaving; after retry final count 2”.
- “PostgreSQL Testcontainers confirmation still pending/was run with version X”.

Các câu có số liệu là **mẫu định dạng báo cáo**, không phải khẳng định chúng đã được đo trong lần viết tài liệu này.

## 16. Quy trình điều tra một flaky Spring Boot integration test

### Bước 1 — Khoanh vùng

- Chạy failing method đơn lẻ.
- Chạy nguyên class.
- Chạy suite theo thứ tự cố định.
- Lặp class 20–100 lần.
- Randomize method order và class order.
- Chạy parallel off/on.
- Ghi môi trường và số lần fail.

Nếu chỉ FAIL khi chạy sau class A, ưu tiên kiểm state leak/order dependency. Nếu FAIL khi chạy parallel, ưu tiên race/shared resource. Nếu FAIL sau 30 phút, ưu tiên resource leak/TTL/time.

### Bước 2 — Tìm shared mutable resources

Liệt kê:
- static fields/singletons.
- Spring cached beans.
- Mockito overrides.
- DB tables/sequence/transactions.
- Redis caches.
- Kafka groups/offsets/topics.
- Files/temp paths.
- System properties/default locale/timezone.
- Web server ports, WireMock stubs.
- Container lifecycle.
- Test executor/thread pool.

Với mỗi tài nguyên, hỏi “ai sở hữu, ai cleanup, ai còn dùng trong lúc cleanup?”.

### Bước 3 — Viết invariant

Ví dụ: “Hai successful increments phải cho final=2”, “Một event ID chỉ một durable receipt”, “Sau test A, mọi global properties trở lại previous values”, “Mỗi test chỉ xóa record của chính nó”.

Một failure log không đủ; cần một bất biến có thể assert bằng observed state.

### Bước 4 — Ép interleaving

- Start gate.
- After-read barrier.
- Failure injection tại transaction boundary.
- Controlled Fake Clock.
- Fake external API trả response theo latch.
- Queue test appender/callback để nhận completion.

Nếu không thể chứng minh một interleaving bằng test, ghi rõ test đang là probabilistic stress, tránh đặt tên như deterministic race reproduction.

### Bước 5 — Sửa ở đúng layer

- Java state: AtomicInteger/locks/immutable state.
- DB: atomic SQL, optimistic/pessimistic locking, transaction isolation/unique constraints.
- Broker: idempotent consumer/event IDs/delivery semantics.
- Test fixture: UUID/schema/targeted cleanup.
- Spring context: giảm shared mutable overrides, không @DirtiesContext tùy tiện.
- Global JVM state: restore + @ResourceLock.
- Async: future/latch/condition await.

### Bước 6 — Bảo vệ bằng regression suite

Giữ:
- Một deterministic interleaving test cho bug đã sửa.
- Một randomized order/parallel suite để tìm dependencies mới.
- Testcontainers production-like test nếu DB/broker semantics quan trọng.
- Monitoring test duration/flaky count trong CI.

Không giữ vĩnh viễn một test “đôi khi fail” như một phép thử sức bền khó debug mà không có owner/quarantine policy.

## 17. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| Test xanh một mình, đỏ trong suite | State leak/order dependency | Random order, tìm shared fixture |
| Test đổi kết quả khi seed khác | Phụ thuộc method/class order | Setup/cleanup độc lập |
| Bật parallel làm DB count sai | Lost update/unsafe cleanup | Atomic SQL/CAS + unique IDs |
| Two worker counter final=1 | Hai SELECT cùng 0 và overwrite | Read barrier, then fix atomic/CAS |
| CAS affectedRows=0 | Concurrent update hoặc row missing | Reload/retry hoặc báo conflict |
| @Transactional test không nhìn thấy worker row | Test fixture chưa commit/thread khác | Seed commit rõ, bỏ outer test tx |
| Test rollback nhưng DB còn data | Worker thread không thuộc test transaction | Query after workers/explicit cleanup |
| @DirtiesContext gây inactive context | Một test close shared cached context | Không parallelize đó/isolate |
| @MockitoBean stubbing bị đổi | Mock bean shared/reset trong concurrent tests | Separate context/sequential |
| @ResourceLock không cứu external race | Lock chỉ điều phối Jupiter participants | DB/external lock hoặc per-test namespace |
| @Isolated vẫn có duplicate DB | Các JVM/actors khác và business race | Backend idempotency/transaction control |
| CountDownLatch timeout | Worker không đến gate, blocked lock/pool | Thread dump/đặt gate đúng |
| Thread.sleep khiến flake giảm nhưng chưa hết | Timing race chưa được synchronize | Future/latch/barrier |
| Parallel class A xóa dữ liệu B | Global TRUNCATE/shared DB | Cleanup targeted IDs/schema |
| Kafka message bị test khác nhận | Shared topic/group/consumer | Unique topic/group/eventId |
| Redis test trả giá trị cũ | Shared keys/cache not reset | Unique prefix/TTL/cleanup |
| Spring context tạo lại liên tục | Profiles/mocks/properties/key khác | Inspect cache stats |
| Fork-per-class mất context reuse | JVM static cache không cross-process | Sửa Surefire fork policy nếu hợp lý |
| RerunFailingTestsCount làm build xanh | Failure bị report flake | Inspect XML/fail on flakes policy |
| Test reports có 0 executed | Tests skipped/discovery mismatch | Check Surefire executed counts |
| H2 test PASS nhưng PostgreSQL race FAIL | DB isolation/dialect khác | Testcontainers PostgreSQL |
| Context cache disabled không giải quyết bug | Race nằm trong external data | Fix true resource isolation |
| Deadlock giữa two-reader gate và row lock | Barrier đặt sau exclusive lock | Move gate trước lock |
| Scheduled job can thiệp fixture | Scheduling enabled trong test | Profile off/manual trigger |
| Test negative async PASS quá sớm | Worker chưa hoàn tất | Await completion/settling contract |
| Suite chạy chậm sau đổi isolation | @DirtiesContext nhiều/container restart | Measure startup/cache hit/miss |

## 18. Bài tập

1. Chạy `CounterRaceIntegrationTest`, giải thích tại sao intentionally unsafe increment luôn cho final 1 khi gate ép hai reads.
2. Bỏ `TwoReaderBarrier` rồi lặp 100 lần. Quan sát sự khác biệt giữa probabilistic và deterministic reproduction.
3. Thêm `Thread.sleep(20)` trước UPDATE trong một nhánh và giải thích vì sao đó không phải một fix.
4. Đổi `unsafeIncrement` sang `atomicIncrement` và thay expected final từ 1 sang 2 trong regression test production.
5. Thêm `@Transactional` vào unsafe method, quan sát behavior trong H2 rồi giải thích vì sao chưa đủ để suy production isolation guarantee.
6. Viết PostgreSQL Testcontainers variant của atomic/CAS tests và so sánh kết quả.
7. Thêm `@Version` JPA entity variant, kiểm một optimistic conflict và bounded retry.
8. Thêm pessimistic row lock variant; đặt barrier đúng vị trí để không tự deadlock.
9. Thêm 8 concurrent workers, kiểm final = 8 với atomic SQL update.
10. Tạo shared `static int` counter và test `++` với barrier, sửa bằng `AtomicInteger`.
11. Dùng `ConcurrentHashMap.putIfAbsent` cho duplicate operation ID, kiểm create-once semantics.
12. Thêm một duplicate payment-like operation với fake gateway, dùng stable idempotency key.
13. Thêm test có unique ID per method và `@AfterEach` targeted cleanup.
14. Thay targeted cleanup bằng `DELETE FROM demo_counters`, bật class parallel và quan sát nguy cơ nhiễm.
15. Thêm method A cố ý set System property và quên restore, dùng random order để phát hiện.
16. Thêm `@ResourceLock(Resources.SYSTEM_PROPERTIES)` và restore property bằng finally.
17. Tạo một class `@Isolated` để chạy operations thay global JVM locale; so sánh overhead.
18. Thêm `@DirtiesContext` vào class, bật parallel, quan sát cache behavior; không dùng setup này trong shared suite production.
19. Tạo test `@RepeatedTest(value=100,failureThreshold=1)`, giải thích reporting khi chạy concurrent repetitions.
20. Randomize classes/methods bằng properties; ghi lại seed của một failure để replay.
21. Chạy Maven Surefire `runOrder=random` và giải thích nó không random method order.
22. Bật `rerunFailingTestsCount=2`, đọc Surefire flaky results thay vì chỉ exit code.
23. Thay JUnit parallel config sang methods concurrent và xác định fixtures nào phải đổi.
24. Viết test có `CompletableFuture`/`Future.get(timeout)` cho một async service.
25. Gắn `@Transactional` vào test rồi seed fixture; chạy worker thread query và giải thích vì sao dữ liệu có thể chưa visible.
26. Dùng `Clock.fixed` để thay thời gian thật trong job expiry/retry tests.
27. Dùng JUnit `RepetitionInfo` để ghi attempt index và correlation ID trong failed run report.
28. Tạo test Kafka listener với unique group/eventId để chống redelivery và test order dependence.
29. Tạo Redis integration test với unique key prefix và targeted cleanup.
30. Bật Surefire multiple forks; giải thích static Spring TestContext cache và resource lock không đồng bộ cross-JVM.
31. Dùng thread dump để chẩn đoán test kẹt ở latch và phân biệt DB row lock.
32. Lập bảng các resources của module mình: owner, scope, mutable, cleanup, concurrency guard.
33. Viết ADR định nghĩa khi nào @ResourceLock được phép và khi nào phải dùng per-test DB/schema.
34. Thêm CI matrix với ít nhất ba seeds, parallelism 1/2/4; lưu seed/failures mà không masking.
35. Mở rộng stress suite chạy 1.000 operations với deadlock/retry metrics; đánh giá risk/latency, không tuyên bố linearizability từ một test.

## 19. Checklist review

- [ ] Đã định nghĩa invariant nghiệp vụ trước khi viết concurrency test?
- [ ] Đã phân biệt flaky order dependency vs actual race?
- [ ] Mỗi test/repetition có fixture độc lập?
- [ ] `@BeforeEach`/`@AfterEach` không phụ thuộc method order?
- [ ] Random order methods/classes được bật khi kiểm isolation?
- [ ] Seed được lưu để tái hiện failure?
- [ ] Không dùng `@Order` để che unintended dependencies?
- [ ] Có test chạy riêng, chạy class, chạy suite, chạy parallel?
- [ ] `@RepeatedTest` được dùng đúng lifecycle; không nhầm với Surefire reruns?
- [ ] Parallel config nêu rõ methods/classes modes và parallelism?
- [ ] `@ResourceLock` dùng key thống nhất cho global resources?
- [ ] Có hiểu `@Isolated` chỉ trong cùng engine/JVM?
- [ ] Không giả định @ResourceLock bảo vệ Java threads ngoài JUnit?
- [ ] Không parallelize @DirtiesContext/@MockitoBean shared context thiếu kiểm soát?
- [ ] Không dựa vào Spring context cache làm data reset?
- [ ] @Transactional test-level không che visibility/commit của worker thread?
- [ ] Có CountDownLatch/Phaser/barrier đặt đúng trước/giữa critical sections?
- [ ] Every wait/future có timeout hữu hạn?
- [ ] Executor/tasks được shutdown/await trước fixture cleanup?
- [ ] Không dùng Thread.sleep để cố đồng bộ hóa business outcome?
- [ ] Race test kiểm final durable DB state sau worker completion?
- [ ] Có concurrent lost update/retry conflict negative case?
- [ ] Fix ở đúng layer: atomic SQL/CAS/JPA @Version/lock/idempotency?
- [ ] Các transaction semantics được kiểm bằng production-like DB khi critical?
- [ ] Per-test IDs/namespaces và targeted cleanup thay global TRUNCATE/FLUSHALL?
- [ ] Kafka topic/group, Rabbit queue, Redis keys được isolate?
- [ ] Không có test-controlled scheduler/async worker còn chạy khi teardown?
- [ ] Logs có safe operation IDs và seed nhưng không có secrets/PII?
- [ ] Surefire reports hiển thị đủ test invocations, no silent skips/flakes?
- [ ] Có phân biệt CI rerun diagnostic với fix thật?
- [ ] Có stress/order matrix trong CI phù hợp budget?
- [ ] Không tuyên bố mọi interleavings đã được chứng minh từ một barrier test?

**Kết luận:** Đối với Spring Boot integration tests, **chạy lặp**, **đổi thứ tự** và **chạy song song** phải được sử dụng như ba phép thử bổ sung nhau. Repetition tìm lỗi thỉnh thoảng, random ordering tìm dependency ẩn giữa fixtures/classes, parallelism tìm tranh chấp tài nguyên; một race quan trọng nên được ép bằng barrier để có chứng cứ tái hiện. Khi phát hiện lỗi, sửa ở **đúng tài nguyên shared**: transaction/SQL/optimistic locking cho DB, synchronization đúng cho Java heap, idempotency cho broker/payment, namespace và cleanup cho test data, resource locks cho global JVM state. Kết quả đáng tin là invariant được kiểm **sau khi mọi operation hoàn tất**, có reproduction seed/trace và regression test — không phải một lần Maven chạy xanh nhờ may mắn hoặc auto-rerun.

## 20. Tài liệu chính thức

- JUnit Jupiter 5.12 — Repeated Tests, RepetitionInfo, failureThreshold: https://docs.junit.org/5.12.0/user-guide/#writing-tests-repeated-tests
- JUnit Jupiter 5.12 — Test Execution Order (MethodOrderer.Random, ClassOrderer.Random): https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-execution-order
- JUnit Jupiter 5.12 — Parallel Execution and @ResourceLock/@Isolated: https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution
- JUnit Jupiter 5.12 — Configuration Parameters: https://docs.junit.org/5.12.0/user-guide/#running-tests-config-params
- JUnit 5 API — MethodOrderer.Random, reproducible seed: https://docs.junit.org/5.12.0/api/org.junit.jupiter.api/org/junit/jupiter/api/MethodOrderer.Random.html
- Spring Framework 6.2 — Parallel Test Execution guidelines: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Framework 6.2 — TestContext Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — Test-managed Transaction and thread-local/preemptive timeout caveats: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — @Sql Test Data and Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.5 — Spring Boot Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Maven Surefire — Rerun failing tests: https://maven.apache.org/components/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html
- Maven Surefire — runOrder and forkCount/reuseForks: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Java SE 17 — CountDownLatch Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 — ExecutorService and Future: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
