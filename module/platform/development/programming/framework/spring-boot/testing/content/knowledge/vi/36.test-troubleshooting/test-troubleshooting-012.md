# Test chỉ thất bại khi chạy cả suite hoặc trên CI

## 1. Hiện tượng: một test chạy riêng thì xanh, chạy cùng các test khác thì đỏ

Trong **Spring Boot - testing**, nhóm **Chẩn đoán lỗi kiểm thử**, câu hỏi cần trả lời không phải chỉ là “tại sao test đang fail?” mà là **“điều kiện nào chỉ xuất hiện khi chạy cả suite hoặc trên CI?”**. Nếu `OrderServiceTest` pass khi chọn riêng bằng `--tests` nhưng fail khi chạy `./gradlew test`, rất có thể test phụ thuộc vào một trạng thái hoặc môi trường mà khi chạy riêng không có.

Các ví dụ:

- Test A để lại một bản ghi trong database; test B mặc định bảng phải trống.
- Test class trước đã tăng counter trên một singleton Spring bean; class sau reuse cùng `ApplicationContext` và đọc counter đó.
- JUnit `@TestMethodOrder` vô tình che việc test B cần test A chạy trước.
- Một `@MockBean`/Mockito stub bị reset hoặc bị giữ state không như dự đoán khi Spring TestContext cache được reuse.
- Test gọi `@Async`/`CompletableFuture` rồi assert ngay, trước khi worker hoàn tất.
- Hai test classes dùng chung port, file, Redis key, Kafka topic hoặc container; chạy song song thì collision.
- Test method có `@Transactional` nên rollback, nhưng asynchronous work hoặc remote API thực hiện ngoài transaction và để lại side effect.
- CI dùng JDK, timezone, locale, OS, filesystem case sensitivity, dependency versions hoặc môi trường secrets khác laptop.
- Một test dùng `new Random()`, `Instant.now()`, `Thread.sleep` hoặc phụ thuộc thứ tự các threads.
- Spring context bị `@DirtiesContext` hoặc cache eviction đóng khi một test khác đang dùng.
- Gradle chia tests sang nhiều JVM forks; static state và Spring cache không chia sẻ như khi chạy IDE.
- Full suite kích hoạt một code path, rate limit, connection pool, timeout, memory pressure hoặc data volume mà test đơn lẻ không gặp.

**Mục tiêu:** thay “chạy lại đến khi xanh” bằng một quy trình điều tra có thể tái hiện: xác định **first failing test**, task/fork, nguồn dữ liệu, thứ tự chạy, concurrency và môi trường; thu bằng chứng; thu nhỏ tập tests gây lỗi; sửa đúng nơi làm rò state; sau đó xác nhận **cả test đơn lẻ và full suite**.

Bài có một dự án Java 17 + Spring Boot 3.3.0 + JUnit Jupiter + Spring JDBC/H2, gồm các tests **mặc định ổn định** thể hiện dọn dữ liệu, reset singleton state, commit/rollback, bean Clock giả và khả năng dùng context giữa test classes. Các anti-pattern gây flaky được đặt thành **snippet chẩn đoán, không chèn vào runnable suite**. Kết quả được mô tả là **expected**, không phải xác nhận đã chạy Gradle.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt lỗi **suite-only**, lỗi **CI-only**, lỗi **intermittent flaky**, lỗi do **test order** và lỗi do **parallelism**.
2. Tạo baseline đáng tin từ full suite, single test và pair tests, cùng exact command/commit/JDK.
3. Đọc Gradle/JUnit XML reports và phân biệt failed, skipped, aborted, no tests và build cache.
4. Phân biệt lỗi của test với Spring ApplicationContext startup failure và container readiness failure.
5. Hiểu Spring TestContext cache giữ lại singleton beans và không tự xóa application state.
6. Biết `@DirtiesContext` làm context bị close/evict nhưng không tự xóa dữ liệu external systems.
7. Dùng `@BeforeEach`/`@AfterEach` với cleanup đúng phạm vi, không phụ thuộc test method order.
8. Hiểu test-managed `@Transactional` và rollback mặc định, đặc biệt với background threads.
9. Phân biệt shared static fields, singletons, in-memory caches, database, filesystem và remote resources.
10. Biết cách giới hạn test data theo unique ID/namespace/transaction để chạy song song an toàn.
11. Dùng `@ResourceLock`/`@Execution(SAME_THREAD)` khi thật sự có shared resource và hiểu giới hạn mỗi JVM.
12. Phân biệt Gradle `maxParallelForks` với JUnit Jupiter parallel execution trong cùng JVM.
13. Tìm race condition mà không dùng `Thread.sleep` làm oracle.
14. Biết vì sao `ThreadLocalRandom`/`new Random()`, system clock và timezone có thể gây bất ổn.
15. Inject `Clock` và fixed time vào Spring tests; dùng PRNG có seed khi test cần replay dữ liệu.
16. Chẩn đoán lỗi chỉ xảy ra trên Linux/CI do case-sensitive paths, line endings, charset hoặc permissions.
17. Kiểm tra JDK vendor/version, Gradle wrapper, dependency lock/BOM, timezone, locale và CI service health.
18. Kiểm tra Hikari pool, socket/file handle, port binding, thread leak và shutdown lifecycle.
19. Biết cách thu nhỏ failing suite theo **test pairs/bisection** mà không kết luận quá sớm.
20. Dùng `--rerun-tasks`/`--no-build-cache` cho fresh execution, nhưng không lẫn với việc sửa flaky.
21. Biết vì sao chạy test riêng có thể thay đổi điều kiện lỗi và biến lỗi thành heisenbug.
22. Không đặt `@TestMethodOrder` để “chữa” một test phụ thuộc trạng thái không được định nghĩa.
23. Không dùng `@DirtiesContext` cho mọi test thay cho đúng DB/cache cleanup.
24. Phân biệt lỗi thiết lập môi trường CI với lỗi logic production khi app chạy tải lớn.
25. Thiết kế CI artifact chứa seed, test selector, tests executed, failure stack, logs và resource identifiers.
26. Viết regression test tái hiện failure thật và xác nhận fix bằng full suite nhiều lần khi cần.
27. Không khẳng định “đã chạy thành công” nếu chỉ mới biên soạn code và expected assertions.

## 3. Sơ đồ chẩn đoán

```text
Single test PASS, suite FAIL?
       |
       +-- Same commit/build inputs?
       |      -> Verify branch, JDK, dependencies, task.
       |
       +-- Fails only after another test?
       |      -> Shared static/singleton/DB/cache/file/mock state.
       |
       +-- Fails only with parallel enabled?
       |      -> Race, resource collision, context eviction.
       |
       +-- Fails only on CI OS/host?
       |      -> Time zone, locale, env vars, paths,
       |         startup readiness, CPU, ports, memory.
       |
       +-- Fails randomly even alone?
       |      -> Clock, PRNG, asynchronous timing,
       |         network/service nondeterminism.
       |
       +-- Fails after many tests?
       |      -> Connection/thread/file leak,
       |         resource exhaustion, eventual quotas.
       |
       +-- Changes when --tests selects subset?
              -> Test order, discovery/filter,
                 shared state or different context lifetime.
```

**Đừng sửa code ngay sau lần fail đầu tiên** khi chưa biết điều kiện tái hiện. Có thể failure chỉ là “không thể kết nối Redis” do service chưa sẵn sàng, hoặc “expected 0, actual 1” do test trước không dọn DB. Hai lỗi có cách xử lý hoàn toàn khác nhau.

## 4. Một lỗi có thể có nhiều chiều

| Kiểu lỗi | Khi test chạy một mình | Khi chạy suite | Khi chạy CI | Giả thuyết ban đầu |
| --- | --- | --- | --- | --- |
| Shared state pollution | Pass | Fail | Có thể fail | Static/bean/DB state rò |
| Method-order dependency | Pass nếu chạy theo đường riêng | Fail khi đổi thứ tự | Phụ thuộc order | Thiếu fixture setup |
| Parallel race | Thường pass | Fail ngẫu nhiên | CI nhiều cores dễ gặp | Unsynchronized state |
| Machine-dependent test | Pass local | Có thể pass local suite | Fail CI | TZ, locale, OS, JDK |
| Timeout under load | Pass | Fail gần ngưỡng | Fail CI chậm | Sleep/busy wait/IO |
| External service not ready | Pass nếu service đã khởi động | Fail theo startup order | Fail fresh CI | Readiness/health |
| TestContext mutation | Pass | Fail nếu reuse cached context | Tùy JVM | Singleton/context cache |
| Resource leak | Pass | Fail sau nhiều tests | Fail CI thời gian dài | Pools, threads, files |
| Random input | Pass hoặc fail tùy seed | Pass/fail | Khó tái hiện | Seed không được lưu |
| Wrong CI command | Pass local | Không liên quan | Tests skipped/not discovered | Task/filter/build setup |

Đây là **ma trận giả thuyết**, không phải chẩn đoán chắc chắn cho từng exception. Cần đo thêm bằng logs và test outputs.

## 5. Quy trình điều tra theo bằng chứng

### Bước 1: lưu môi trường thất bại

Ghi lại **exact Gradle/Maven command**, repository revision, OS, architecture, JDK vendor/version, Gradle wrapper, timezone, locale, Spring Boot/JUnit versions, CI image digest, profiles, secrets availability, test worker settings và service addresses. Giữ lại full stack trace đầu tiên thay vì chỉ dòng “There were failing tests”.

Ví dụ lệnh:

```bash
java -version
./gradlew --version
./gradlew test --info
```

Gradle 8.x có thể hiển thị `:test UP-TO-DATE`/`FROM-CACHE` nếu output cũ được reuse. Điều đó không tự chứng minh tests đã được thực thi trong lần gọi này. Khi cần **fresh reproduction**:

```bash
./gradlew test --rerun-tasks --no-build-cache --info
```

`--rerun-tasks` có thể làm nhiều tasks không cần thiết cũng chạy lại; dùng có mục đích chẩn đoán, không mặc định ép toàn bộ CI dùng suốt.

### Bước 2: chạy đúng một test

```bash
./gradlew test --tests 'example.suite.OrderSuiteIsolationTest'
```

Nếu test class pass, thử chạy toàn suite. Nếu một method fail trong suite, chọn đúng FQN:

```bash
./gradlew test --tests \
  'example.suite.OrderSuiteIsolationTest.rollbackRemovesRowButMemoryStateRequiresReset'
```

**Chọn test đơn lẻ thay đổi nhiều thứ:** các classes khác không chạy, context có thể fresh, database rỗng, random draw khác, parallelism và memory load thấp hơn. Do đó “pass một mình” là **dấu hiệu cần khoanh vùng**, không chứng minh bản thân test đúng.

### Bước 3: tìm test gây pollution

Nếu A pass riêng và B pass riêng, nhưng A→B fail, kiểm tra:

- A tạo row/file/key nào chưa cleanup?
- A thay static `System.setProperty`/`TimeZone.setDefault`/`Locale.setDefault` mà chưa restore?
- A thay state singleton/cache/mocks của context share với B?
- A khởi động background thread, scheduled job hoặc async task chưa hoàn tất?
- A đóng/`@DirtiesContext` context/DB container B cần dùng?
- A để test clock/PRNG singleton ở state khác?
- A đổi external service, message offset hoặc port listener?

### Bước 4: tách sequential và parallel

Giữ **cùng test set** và cùng data, thử bật/tắt JUnit parallel và Gradle forks độc lập. Nếu chỉ fail khi parallel, tìm resource collisions/races. Nếu fail dù chạy tuần tự nhưng phụ thuộc class order, tìm state leak/cleanup thiếu.

### Bước 5: thu nhỏ reproducible set

Đừng chỉ chạy full 20 phút nhiều lần. Thu nhỏ bằng hai classes A/B hoặc một nhóm nhỏ (delta debugging/bisection). Nhưng phải giữ những điều kiện cần: same JVM/fork, same cache key, same database/container, đúng thứ tự hoặc parallel mode nếu lỗi phụ thuộc. Một subset bỏ mất class tạo pollution sẽ pass và khiến kết luận sai.

### Bước 6: sửa đúng nguyên nhân

Ví dụ test A quên xóa row, sửa fixture cleanup/transaction isolation; không thêm retry assertion ở test B. Nếu callback async chưa xong, dùng synchronization/await condition; không tăng `Thread.sleep` vô hạn.

### Bước 7: xác minh

Chạy lại **reduced reproducer** (đỏ trước, xanh sau), rồi **full suite**, rồi CI environment tương đương. Nếu bug race hiếm, chạy số lần có thể biện minh và thu result; không tuyên bố 100% hết lỗi chỉ vì một run xanh.

## 6. Spring TestContext cache và singleton state

Spring TestContext Framework cache `ApplicationContext` theo merged configuration. Hai test classes với `@SpringBootTest` tương đương có thể reuse **cùng bean graph**, bao gồm singletons, JPA/entity manager factories, caches, executors và DB connection pools.

```text
Class A -- @SpringBootTest(config X) ---+
                                       |
                                       v
                             ApplicationContext X
                             (singleton state, clients)
                                       ^
                                       |
Class B -- @SpringBootTest(config X) ---+
```

Nếu class A gọi `attemptCounter.increment()` mà không reset state, class B có thể thấy counter từ A, dù B tự khởi tạo test instance mới.

### 6.1. Context reuse không có nghĩa test state reset

Spring có thể tạo một instance JUnit test class mới cho mỗi test method, nhưng injected singleton bean vẫn đến từ cached context. Vì vậy code:

```java
@BeforeEach
void setUp() {
    // A new test object is not necessarily
    // a new Spring ApplicationContext.
}
```

không tự clear DB/Redis/bean state. Test phải quản lý dữ liệu ở đúng tầng.

### 6.2. Cache key khác làm kết quả thay đổi

Hai classes có `@ActiveProfiles`, inline properties, `@DynamicPropertySource`, `@MockBean`/`@SpyBean` trong Boot 3.3 hoặc test customizers khác nhau có thể tạo **hai contexts**, nên leak từ singleton này không sang singleton kia. Khi bạn đổi một annotation và lỗi biến mất, đừng kết luận fix: có thể bạn chỉ khiến Spring tạo context mới và che state pollution.

### 6.3. Context cache là per JVM

Static Spring TestContext cache không chia sẻ qua Gradle forks, IDE processes và CI shards. Một test pass khi chạy ở fork mới nhưng fail khi chạy nhiều classes trong cùng fork có thể là do context reuse. Nhưng đổi forks có thể chỉ che bug và tăng startup cost.

### 6.4. @DirtiesContext

`@DirtiesContext` đánh dấu context cần close/evict để lần sau load mới. Nó có ích nếu test thật sự thay đổi cấu hình/bean graph không thể reset, nhưng **không nên dùng làm phép dọn database mặc định**. DB ngoài process có thể còn rows dù context được recreate. Nhiều `@DirtiesContext` làm suite chậm, và parallel tests có thể gặp context bị close trong khi test khác vẫn đang dùng.

### 6.5. Cache eviction

Ngay cả không có `@DirtiesContext`, cache mặc định bounded LRU (mặc định tối đa 32 contexts). Khi suite tạo nhiều cache keys, một context có thể bị evict rồi load lại. Không hardcode “class A và B chắc chắn cùng instance” nếu giữa chúng đã có nhiều contexts khác và eviction. Khi chẩn đoán, xem DEBUG `org.springframework.test.context.cache`.

## 7. Test order dependency

Một anti-pattern:

```java
class BadOrderTests {

    static String lastReference;

    @Test
    void createReference() {
        lastReference = "ORDER-7";
    }

    @Test
    void useReference() {
        assertEquals("ORDER-7", lastReference);
    }
}
```

**Snippet cố ý sai, không thuộc runnable project.** Khi `useReference` chạy trước hoặc chạy một mình trong JVM mới, static field có thể null. Chạy theo một thứ tự cụ thể có thể xanh nhưng không độc lập.

**Cách sửa:** mỗi test tạo riêng fixture mà nó cần:

```java
class GoodOrderTests {

    @Test
    void usesOwnReference() {
        String reference = "ORDER-7";
        assertEquals("ORDER-7", reference);
    }
}
```

### 7.1. Vì sao không dùng @TestMethodOrder để chữa?

`@TestMethodOrder(MethodOrderer.OrderAnnotation.class)` có thể ép order để mô tả một workflow integration có chủ đích. Nhưng nó không làm tests độc lập và có thể gây suite-only failures khi chạy method riêng. Nếu test phụ thuộc một scenario trước đó, thường nên đặt **tất cả bước của scenario vào một test** hoặc dùng lifecycle của fixture rõ ràng.

### 7.2. @BeforeAll không phải @BeforeEach

`@BeforeAll` chỉ chạy một lần cho class/container, không reset state giữa methods. Nếu mỗi method cần DB rỗng, dùng `@BeforeEach` hoặc transaction rollback có kiểm soát. JUnit `@TestInstance(PER_CLASS)` dùng chung test instance; mutable instance fields cũng có thể gây leak khi chạy nhiều methods.

### 7.3. Random test order để phát hiện phụ thuộc

JUnit Jupiter có thể cấu hình method orderer:

```properties
junit.jupiter.testmethod.order.default = org.junit.jupiter.api.MethodOrderer$Random
```

Đây là **một cấu hình thử nghiệm**; khi đặt trong `junit-platform.properties`, method order có thể thay đổi. Nó giúp lộ phụ thuộc order, nhưng không thay thế fixture cleanup; cần ghi random order seed/runner information theo JUnit version nếu muốn replay chính xác.

## 8. @Transactional test và data isolation

Spring TestContext `@Transactional` trên test method/class tạo **test-managed transaction** thường rollback sau test, khi transaction manager phù hợp được phát hiện.

```java
@SpringBootTest
@Transactional
class TransactionalRepositoryTest {
    @Test
    void savesSomething() {
        repository.save(...);
        // By default test transaction rolls back.
    }
}
```

Snippet này chưa runnable vì thiếu repository và imports. Nó minh họa mặc định rollback trong Spring Test.

### 8.1. Rollback chỉ áp dụng đúng transaction boundary

Nếu code test gửi Kafka message, gọi REST service, ghi file, tạo Redis key hoặc chạy background thread với transaction khác, rollback JDBC/JPA của test **không tự hoàn tác side effects đó**. Một test có thể pass riêng nhưng để lại Redis key làm class tiếp theo fail.

### 8.2. @SpringBootTest RANDOM_PORT

Với server thật và HTTP client trong test, client/test thread transaction **không tự bao trùm server thread transaction**. Server xử lý request trong transaction riêng hoặc auto-commit. Vì vậy `@Transactional` trên JUnit test không bảo đảm dữ liệu mà HTTP handler ghi sẽ rollback cùng test. Cần cleanup/isolated database phù hợp.

### 8.3. @BeforeEach/@AfterEach và test-managed tx

Trong Spring TestContext transactional tests, JUnit `@BeforeEach`/`@AfterEach` thường chạy bên trong test-managed transaction. Nếu bạn cần dọn dữ liệu **ngoài** transaction để data cleanup được commit, dùng `@BeforeTransaction`/`@AfterTransaction` hoặc cơ chế fixture phù hợp; không đơn giản đặt `jdbc.deleteAll()` ở `@AfterEach` rồi cho rằng nó luôn đã commit.

### 8.4. @Sql

`@Sql` có thể chạy database setup/cleanup scripts và được điều khiển execution phase/transaction mode. Khi dùng shared DB và parallel tests, script `DELETE FROM orders` trên cùng bảng có thể xóa dữ liệu của test khác. Dùng per-test schema/namespace hoặc locking, không dựa vào thứ tự dọn dẹp mơ hồ.

### 8.5. Test không có @Transactional

Lab phía dưới **không đặt @Transactional lên JUnit test**. Service methods tự mở transaction. Điều này cho phép test đọc DB state đã commit/rollback **sau khi service call trở về**; `@BeforeEach`/`@AfterEach` dọn dữ liệu độc lập. Đây là lựa chọn minh họa rõ ownership của transaction.

## 9. Mockito @MockBean và state giữa test methods

Trong Spring Boot 3.3, `@MockBean` thay một Spring bean bằng Mockito mock trong ApplicationContext. Tập mock definitions có thể tham gia context cache key; bean mocks có thể được reset bởi Spring Boot test support theo configuration/lifecycle.

Các bẫy:

- Test A stub mock, test B giả định stub đó vẫn còn.
- Test B verify interactions từ test A (nếu mock không reset như dự kiến).
- Một test tự gọi `Mockito.reset(mock)` khi test khác đang dùng cùng cached mock dưới parallel execution.
- Test cấu hình `@MockBean(reset=MockReset.NONE)` rồi quên tự reset.
- Dùng `@SpyBean` có trạng thái thật trong target object.
- `Mockito.when(...).thenReturn(...)` được đặt vào một `@BeforeAll` bất phù hợp với reset-per-method lifecycle.
- Nhiều test classes có mock definitions khác nhau, dẫn đến **nhiều contexts**, làm startup thay đổi.

### 9.1. Đừng bắt test này dùng stubbing của test khác

```java
@MockBean
PaymentClient paymentClient;

@BeforeEach
void stubGateway() {
    when(paymentClient.charge(any()))
            .thenReturn(new Receipt("ok"));
}
```

Đây là **snippet minh họa** (các types/Mockito imports chưa khai báo), không thuộc runnable lab. Nếu cần mock behavior cho mỗi test, đặt stubs trong lifecycle của chính test, không dựa test order. Với plain unit tests, ưu tiên `@Mock`/`@InjectMocks` hoặc tự tạo fake collaborator độc lập.

### 9.2. Không vội @DirtiesContext vì mock verify lỗi

Nếu lỗi chỉ là Mockito interactions/stubs bị giữ sai, sửa mock reset lifecycle và test isolation. `@DirtiesContext` có thể che bug nhưng làm context bootstrap lặp và không khắc phục external state.

### 9.3. Boot version boundary

Bài cố định Spring Boot 3.3. Các phiên bản mới hơn có `@MockitoBean`/`@MockitoSpyBean` trong Spring Framework. Không copy annotation/config behavior của Boot đời khác mà chưa xác minh version.

## 10. Parallel execution: hai loại song song khác nhau

### 10.1. JUnit Jupiter parallel trong cùng JVM

JUnit Jupiter mặc định chạy tuần tự nếu không bật parallel. Có thể bật:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
```

Đây là **cấu hình minh họa**; không được bật sẵn trong runnable project. Với parallel mode, các JUnit methods/classes có thể chạy trên nhiều threads trong **cùng JVM**, cùng dùng static variables và Spring context cache.

### 10.2. Gradle maxParallelForks

`maxParallelForks=2` tạo tối đa hai **test worker JVM processes** song song; mỗi JVM có static state và Spring TestContext cache riêng. Nó không giống JUnit thread-level parallelism.

- JUnit parallel: shared memory, có thể race trên static/bean fields.
- Gradle forks: tách JVM memory, nhưng vẫn có thể cùng đụng external DB, Redis, files, ports.
- CI shards: nhiều machines/containers; càng phải đảm bảo external resource namespaces.

### 10.3. @ResourceLock

JUnit Jupiter có `@ResourceLock` để phối hợp các tests **trong cùng một JUnit execution/JVM** khi chúng truy cập cùng shared resource:

```java
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class DatabaseIsolationTest {
    // Its @BeforeEach and @AfterEach participate
    // in the resource lock's protected lifecycle.
}
```

**Snippet**, imports/real tests ở runnable lab. Dùng cùng key trên những classes cần loại trừ truy cập song song vào một shared database. Lock không vượt qua Gradle forks/CI machines, nên external systems cần namespacing/isolated databases khi chạy multi-process.

### 10.4. @Execution(SAME_THREAD)

`@Execution(ExecutionMode.SAME_THREAD)` chỉ định execution mode của JUnit nodes, hữu ích trong một số test class phụ thuộc thread affinity. Nhưng nó **không đồng nghĩa global mutual exclusion** với mọi class khác. Với shared resource, dùng `@ResourceLock` hoặc isolation đúng provider. Không chỉ thay một annotation rồi cho rằng mọi race đã được chữa.

### 10.5. @DirtiesContext + parallel

Spring khuyến nghị cẩn thận/không parallel với tests có `@DirtiesContext`, `@MockBean`/`@SpyBean`, mutable shared services hoặc test order constraints. Nếu context đang được test A dùng mà thread khác evict/close, A có thể gặp “ApplicationContext no longer active” hoặc resource failure. Giải pháp là sửa lifecycle/serialization, không retry blind.

## 11. Race condition và lỗi khó tái hiện

Một anti-pattern:

```java
class UnsafeCounter {
    int count;

    void increment() {
        count++; // read-modify-write, not atomic
    }
}
```

Hai threads có thể đọc cùng giá trị cũ rồi cùng ghi giá trị mới, mất một lần increment. Khi chạy riêng/ít tải, timing có thể khiến bug không xuất hiện; trên CI tải cao hoặc parallel suite, lỗi lộ ra.

Cách sửa:

```java
class SafeCounter {
    private final AtomicInteger count =
            new AtomicInteger();

    int increment() {
        return count.incrementAndGet();
    }
}
```

Đây là snippet, cần import `java.util.concurrent.atomic.AtomicInteger`. **AtomicInteger không tự chữa một compound business operation** gồm “kiểm tra tồn tại → insert → gửi message”; cần transaction/locking/idempotency phù hợp boundary.

### 11.1. Thread.sleep không đồng bộ các threads

```java
startAsyncJob();
Thread.sleep(100);
assertEquals("DONE", status());
```

Anti-pattern: 100ms là đoán. CI chậm có thể chưa xong, còn local nhanh thì pass. Hãy dùng `Future.get(timeout)`, `CompletableFuture.join()` với timeout, `CountDownLatch`, `Awaitility` hoặc virtual-time schedulers khi thích hợp.

### 11.2. Không dùng timeout vô hạn

Synchronization phải có **deadline hữu hạn** để suite không treo CI mãi. Nhưng timeout nên dựa vào SLO/test scale, không assert một response tuyệt đối phải dưới 1ms trên máy ảo. Dự án dùng 30 giây cho các tác vụ CPU nhỏ; đó là guard chống treo chứ không phải performance benchmark.

### 11.3. Race có thể vẫn bị che bởi synchronized tests

Nếu chuyển mọi test về sequential và lỗi biến mất, bạn đã xác định concurrency là một yếu tố. Nhưng production code vẫn có thể race. Cần kiểm tra thread safety của code được dùng đồng thời trong ứng dụng thật, không chỉ tắt parallel để có CI xanh.

## 12. File system, ports và môi trường CI

### 12.1. File paths và case sensitivity

Trên một số hệ điều hành/filesystem, `src/test/resources/Users.json` và `users.json` có thể coi là khác nhau; trên máy dev khác, mismatch bị che. Truy cập classpath resource nên dùng đúng **case của filename** và không dựa current working directory:

```java
try (InputStream in =
        getClass().getResourceAsStream(
                "/fixtures/users.json")) {
    assertNotNull(in);
}
```

Snippet cần imports và resource tồn tại; không thuộc lab runnable. Nếu CI báo null, kiểm tra file thực được package vào `build/resources/test`, không chỉ chỉnh đường dẫn bằng slash tùy tiện.

### 12.2. Line endings và charset

Windows thường CRLF, Linux LF. Test so raw file string có thể fail do line endings, encoding/default charset. Khi contract là text content không phụ thuộc newline, normalize có chủ đích. Khi test serialization/wire format có newline cố định, **assert đúng contract** và đọc bằng `StandardCharsets.UTF_8`.

### 12.3. Temp files

Đừng dùng tên chung `/tmp/test-output.json` cho mọi test. JUnit `@TempDir Path tempDir` tạo directory riêng cho test context; với multi-fork/external resource, vẫn cần tránh path collision nếu code tự tạo file bên ngoài tempDir.

### 12.4. Ports

Đặt server/test service vào cố định `8080`/`9092` có thể collision với test khác hoặc CI service. Dùng random port (`@SpringBootTest(webEnvironment=RANDOM_PORT)`) và inject actual local server port khi có HTTP tests; với Testcontainers dùng mapped port do runtime trả về.

### 12.5. Timezone, locale, date

`LocalDate.now()` lấy timezone mặc định của process. Một test assert “today equals ...” có thể fail gần midnight hoặc khi CI dùng UTC còn local dùng UTC+07. Inject `Clock` và `ZoneId`. Nếu test format numbers/currency, dùng `Locale` explicit.

### 12.6. Permissions và working directory

CI agent có thể chạy với user không có write permission dưới repository root, hoặc workspace là read-only. Dùng test-specific temp folders; chỉ ghi ra thư mục được phép, không sửa source files trong tests.

## 13. External dependencies và readiness

Một test có thể dùng Docker/Testcontainers, PostgreSQL, Redis, Kafka, LocalStack hoặc HTTP server. Local máy dev có container đang chạy từ trước; CI mới boot có thể cần thời gian health checks.

**Không dùng `Thread.sleep(10_000)` như readiness gate mặc định.** Dùng provider-specific waiting/health checks, e.g. Testcontainers `waitingFor(...)`, JDBC connection validation, HTTP health endpoint hoặc retry **có backoff và timeout hữu hạn**.

### 13.1. Testcontainers lifecycle

Khi sử dụng cached Spring context, container phải sống đủ lâu để clients trong context dùng được. Nếu container là per-class resource bị dừng sau test A, nhưng context được reuse bởi test B, client trong cache có thể trỏ vào mapped port đã chết. Thiết kế container lifecycle gắn với context/JVM hoặc có `@DirtiesContext` có chủ đích; không “giữ context” trỏ resource không còn sống.

### 13.2. Database schema/fixtures

H2 embedded và production PostgreSQL khác SQL dialect, transaction isolation và constraints. Một suite pass trên H2 không chứng minh concurrency behavior trên PostgreSQL. Khi lỗi chỉ xảy ra CI với database thật, chạy Testcontainers với provider/version tương đương, giữ migrations/fixtures ổn định.

### 13.3. Remote services và secrets

CI có thể thiếu credential/env var, proxy/network bị chặn, API rate-limited hoặc endpoint khác. Không làm test xanh bằng cách log raw tokens/credentials. Nếu test đúng nghĩa unit, mock/fake external dependency; nếu là integration, quản lý credentials, sandbox account và health/permission checks rõ ràng.

### 13.4. Port/mapped address của containers

Không hardcode host/port từ laptop. Dùng `@ServiceConnection` (Boot 3.1+) hoặc `@DynamicPropertySource`/container API đúng version, đồng thời kiểm soát context cache lifecycle.

## 14. JVM, Gradle, JUnit và profiles

Một suite chạy local có thể dùng JDK 17/Gradle 8.7, CI dùng JDK 21/Gradle version khác hoặc bật test parallel. Ngay cả với cùng source, behavior trong serialization, timezones, reflection/module access hoặc dependency resolution có thể khác.

Checklist môi trường:

```text
Commit SHA
JDK vendor + java -version
Gradle wrapper version
Spring Boot + Spring Framework + JUnit versions
OS/arch and container image digest
Default timezone and locale
JAVA_TOOL_OPTIONS / JVM args
Active Spring profiles
Gradle -P properties / --tests selectors
JUnit parallel configuration parameters
Gradle maxParallelForks + forkEvery
Datasource URL/schema/migration version
Docker engine + Testcontainers version
External service versions, ports, health
Filesystem permissions, path case, charset
Test source data and random seed
```

### 14.1. Gradle test JVM khác Gradle daemon JVM

Các system properties set trên Gradle process không nhất thiết tự truyền sang **forked test JVM** theo cách bạn mong đợi. Đặt test properties trên `Test` task:

```groovy
tasks.named('test', Test) {
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'junit.jupiter.execution.parallel.enabled',
            'false'
}
```

Snippet cấu hình minh họa; runnable `build.gradle` ở chương 16 có cấu hình tương đương. Nếu hệ thống yêu cầu local timezone cụ thể, truyền `ZoneId` vào business code thay vì ép timezone toàn JVM.

### 14.2. JUnit seeds

JUnit test method order có thể là deterministic nhưng không được business test phụ thuộc. Nếu dùng random order hoặc random fixture generator, lưu seed và command của lần fail. Seed không kiểm soát thread scheduling, network, DB state hoặc thứ tự test class trên mọi runner.

### 14.3. Module/test selector

`./gradlew :orders:test` không chạy tests ở `:billing:test`; `--tests` có thể chỉ chọn một subset. CI job “green” nhưng task không chạy hoặc mọi tests skipped là lỗi coverage khác, cần xem XML/report thực. Không trộn lỗi zero-tests với suite-only failures.

## 15. Thiết kế lab: tests ổn định nhưng vẫn cho thấy cơ chế gây rò state

Ta dựng:

1. Một Spring Boot app nhỏ với H2 in-memory và JDBC transactions.
2. `OrderStore` thao tác bảng `orders`.
3. `OrderService` thực hiện `@Transactional` commit/rollback.
4. `AttemptCounter` là singleton mutable state; tăng mỗi lần gọi service, **không rollback khi DB transaction rollback**.
5. `FixedClockTestConfig` là shared test configuration với `Clock.fixed`.
6. Hai `@SpringBootTest` test classes có **cùng cấu hình**, nên có thể reuse Spring context, nhưng mỗi class reset dữ liệu và counter ở `@BeforeEach`/`@AfterEach`.
7. Một plain JUnit class kiểm tra time/random/concurrency không cần Spring context.
8. `@ResourceLock("suite-lab-database")` bảo vệ access tới H2/bean state khi bật JUnit parallel trong một JVM.
9. No `@DirtiesContext` và no `@TestMethodOrder` trong runnable tests.
10. Mọi test độc lập; chạy một class hoặc cả suite đều có expected behavior như nhau.

**Lưu ý:** `@ResourceLock` chỉ đồng bộ các Jupiter tests cùng execution/JVM có cùng lock key; nó không bảo vệ external DB dùng chung bởi hai Gradle test worker JVMs. Lab dùng H2 in-memory và `maxParallelForks=1` để có baseline rõ. Khi triển khai project thật, phải cô lập external resources cấp process nếu chạy nhiều forks/shards.

## 16. Dự án runnable Java 17 + Spring Boot 3.3

### 16.1. Cây thư mục

```text
suite-isolation-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/suite/
    │   │   ├── SuiteLabApplication.java
    │   │   ├── Receipt.java
    │   │   ├── OrderStore.java
    │   │   ├── AttemptCounter.java
    │   │   └── OrderService.java
    │   └── resources/
    │       └── schema.sql
    └── test/java/example/suite/
        ├── FixedClockTestConfig.java
        ├── OrderSuiteIsolationTest.java
        ├── AnotherOrderSuiteTest.java
        └── PureIsolationTest.java
```

Không cần web server, Kafka, Redis hay Docker. Đây là H2/JdbcTemplate integration test với transaction manager thật và fixed test clock. Nếu project chưa có Gradle Wrapper, tạo wrapper bằng Gradle 8.7 hoặc phiên bản tương thích rồi commit wrapper files; `./gradlew` chỉ chạy khi wrapper đã có.

### 16.2. settings.gradle

```groovy
rootProject.name = 'suite-isolation-lab'
```

### 16.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    systemProperty 'user.timezone', 'UTC'
    systemProperty 'junit.jupiter.execution.parallel.enabled',
            providers.gradleProperty('junitParallel')
                    .orElse('false')
                    .get()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Phân tích:**

- `spring-boot-starter-jdbc` kích hoạt JDBC/JdbcTemplate/transaction support.
- H2 là runtime dependency; Boot auto-configures embedded DataSource nếu không có datasource khác.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, Mockito/AssertJ.
- `junit-platform-launcher` giúp tránh phụ thuộc launcher ngầm theo Gradle version.
- `useJUnitPlatform()` yêu cầu đúng engine.
- Mặc định `junitParallel=false` để baseline deterministic. Khi muốn thử JUnit parallel, chạy `-PjunitParallel=true`; nếu cần concurrent nodes thực sự, thêm Jupiter mode setting tương ứng (bật enabled một mình chưa chắc mọi test methods chạy concurrent).
- `maxParallelForks=1` và `forkEvery=0` giúp cùng một test worker JVM trong lab; khác với JUnit threads.
- `systemProperty user.timezone` áp dụng vào **test JVM**, không chỉ Gradle daemon.

## 17. SuiteLabApplication.java và schema.sql

### 17.1. SuiteLabApplication.java

**src/main/java/example/suite/SuiteLabApplication.java**

```java
package example.suite;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SuiteLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SuiteLabApplication.class, args);
    }

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

`Clock` là dependency explicit. Test có thể override thành frozen clock bằng `@TestConfiguration`; không cần sửa business code khi muốn giữ thời điểm ổn định. Dùng `Clock` giúp tránh test bị hỏng khi chạy gần nửa đêm hoặc khi timezone CI khác.

### 17.2. schema.sql

**src/main/resources/schema.sql**

```sql
create table if not exists orders (
    ref varchar(80) primary key
);
```

Spring Boot SQL initialization với embedded H2 tạo bảng lúc ApplicationContext khởi động. Lab sử dụng H2 nên cleanup là `DELETE FROM orders`, không có foreign key phức tạp. **Trong production DB**, migrations (Flyway/Liquibase), schemas và transactional isolation cần được quản lý riêng.

### 17.3. Vì sao bảng không chứa auto-generated IDs?

Tất cả tests dùng `ref` do test quyết định, giúp thấy rõ duplicate key và cleanup. Chúng ta muốn bài tập **test isolation**, không bị nhiễu bởi identity sequence của H2. Nếu production logic phụ thuộc generated IDs hoặc uniqueness, phải test riêng với provider thực.

## 18. Receipt.java và AttemptCounter.java

### 18.1. Receipt.java

**src/main/java/example/suite/Receipt.java**

```java
package example.suite;

import java.time.Instant;

public record Receipt(
        String ref,
        Instant createdAt) {}
```

Java 17 record immutable, giúp assertions bằng `assertEquals` và không có mutable shared DTO state.

### 18.2. AttemptCounter.java

**src/main/java/example/suite/AttemptCounter.java**

```java
package example.suite;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class AttemptCounter {

    private final AtomicInteger attempts =
            new AtomicInteger();

    public void mark() {
        attempts.incrementAndGet();
    }

    public int value() {
        return attempts.get();
    }

    public void reset() {
        attempts.set(0);
    }
}
```

`AttemptCounter` là singleton Spring-managed, cố ý có mutable state để mô phỏng metrics/in-memory state. Nó thread-safe ở cấp increment, nhưng **reset và increment từ independent tests có thể tạo race** nếu chạy parallel không có resource lock. Bộ test class ở lab bảo vệ bằng `@ResourceLock` và dùng sequential default.

**Điểm mấu chốt:** dữ liệu trong `AtomicInteger` không thuộc JDBC transaction; khi service rollback, value **không tự giảm**. Test phải reset ở fixture boundary nếu kỳ vọng bắt đầu từ 0.

## 19. OrderStore.java — JDBC repository

**src/main/java/example/suite/OrderStore.java**

```java
package example.suite;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String ref) {
        jdbc.update(
                "insert into orders(ref) values (?)",
                ref);
    }

    public int count() {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders",
                Integer.class);
        return count == null ? 0 : count;
    }

    public int countByRef(String ref) {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders where ref = ?",
                Integer.class,
                ref);
        return count == null ? 0 : count;
    }

    public void deleteAll() {
        jdbc.update("delete from orders");
    }
}
```

Dùng `JdbcTemplate` thay vì mock repository để kiểm tra **transaction rollback/commit thật trên H2**. Không dùng `@DataJpaTest` nên tránh test-managed rollback mặc định che mất commit boundary của service.

### 19.1. Shared in-memory H2 vẫn là shared state trong context

Nếu hai `@SpringBootTest` classes reuse cùng DataSource, chúng đọc/ghi cùng embedded H2. Dù mỗi class tạo JUnit test instance mới, DB vẫn còn data nếu không cleanup. Test order và class order có thể đổi khiến một test fail bất ngờ.

### 19.2. Cleanup an toàn khi nào?

`deleteAll()` dùng để dọn **toàn bộ** bảng trong lab sở hữu riêng. Trong ứng dụng lớn hoặc CI dùng shared external DB, không xóa toàn bảng của services/tests khác. Dùng schema/container per test worker, namespace rõ hoặc seeded IDs và targeted cleanup.

## 20. OrderService.java — giao dịch thật, counter không rollback

**src/main/java/example/suite/OrderService.java**

```java
package example.suite;

import java.time.Clock;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderStore store;
    private final AttemptCounter counter;
    private final Clock clock;

    public OrderService(
            OrderStore store,
            AttemptCounter counter,
            Clock clock) {
        this.store = store;
        this.counter = counter;
        this.clock = clock;
    }

    @Transactional
    public Receipt place(String ref) {
        return insertOnce(ref);
    }

    @Transactional
    public void placeAndFail(String ref) {
        insertOnce(ref);
        throw new IllegalStateException(
                "planned rollback");
    }

    private Receipt insertOnce(String ref) {
        if (ref == null || ref.isBlank()) {
            throw new IllegalArgumentException(
                    "ref must not be blank");
        }

        Objects.requireNonNull(clock);

        counter.mark();
        store.insert(ref);

        return new Receipt(
                ref,
                clock.instant());
    }
}
```

### 20.1. @Transactional đặt trên public methods

Tests inject `OrderService` bean và gọi public `place`/`placeAndFail` qua Spring AOP proxy. Spring JDBC transaction manager có thể mở transaction, commit khi method trả bình thường hoặc rollback khi unchecked exception propagate.

Private `insertOnce` chỉ là helper **được gọi bên trong transaction đã mở**; không giả định `@Transactional` trên private method/self-invocation tự hoạt động.

### 20.2. Rollback DB nhưng không rollback AtomicInteger

Trong `placeAndFail`:

1. Service mở JDBC transaction.
2. `counter.mark()` tăng singleton counter ngay.
3. `store.insert` gửi INSERT trong transaction.
4. `IllegalStateException` ném ra ngoài.
5. Transaction interceptor rollback JDBC row.
6. Counter vẫn ở giá trị 1 vì nó là memory state, không nằm trong transaction.

Bài học: nếu một test chỉ assert DB rollback mà không reset singleton state trước test tiếp theo, một suite khác có thể bị nhiễm trạng thái. Tương tự với files, Redis, logs, HTTP calls, background messages.

## 21. FixedClockTestConfig.java — một test bean dùng chung

**src/test/java/example/suite/FixedClockTestConfig.java**

```java
package example.suite;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfig {

    public static final Instant FIXED =
            Instant.parse("2026-11-08T03:00:00Z");

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                FIXED,
                ZoneOffset.UTC);
    }
}
```

Production configuration có `Clock.systemUTC()`; test config thêm một bean `@Primary` là `Clock.fixed`. Hai Spring integration test classes đều `@Import(FixedClockTestConfig.class)` với cùng `@SpringBootTest` config, giúp **cache key có cơ hội giống nhau** và cùng context được reuse. Dù vậy assertions không dựa vào context object identity hay class order.

### 21.1. Vì sao test config không được tạo riêng trong từng test class?

Nếu mỗi class dùng một nested `@TestConfiguration` khác nhau, các context customizers/configuration classes có thể khác, khiến Spring tạo contexts riêng. Điều đó sẽ che hiện tượng shared bean state. Một shared test config class làm ví dụ rõ hơn.

### 21.2. Tại sao không set System.currentTimeMillis?

Bạn không thể dễ dàng ép system clock toàn JVM từ Java test, và cách hack global time thường gây side effects. Inject `Clock` rồi tạo fixed Clock giúp tests ổn định và không ảnh hưởng test khác.

## 22. OrderSuiteIsolationTest.java — bốn Spring integration tests

**src/test/java/example/suite/OrderSuiteIsolationTest.java**

```java
package example.suite;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = SuiteLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(FixedClockTestConfig.class)
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class OrderSuiteIsolationTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderStore store;

    @Autowired
    AttemptCounter counter;

    @BeforeEach
    void cleanBefore() {
        store.deleteAll();
        counter.reset();
    }

    @AfterEach
    void cleanAfter() {
        store.deleteAll();
        counter.reset();
    }

    @Test
    void startsWithEmptyDatabaseAndCounter() {
        assertEquals(0, store.count());
        assertEquals(0, counter.value());
    }

    @Test
    void orderCreationCommitsAndUsesFixedClock() {
        Receipt receipt =
                service.place("ORDER-A");

        assertNotNull(receipt);
        assertEquals("ORDER-A", receipt.ref());

        assertEquals(
                FixedClockTestConfig.FIXED,
                receipt.createdAt());

        assertEquals(1, store.count());
        assertEquals(
                1,
                store.countByRef("ORDER-A"));
        assertEquals(1, counter.value());
    }

    @Test
    void rollbackRemovesRowButMemoryStateRequiresReset() {
        IllegalStateException ex =
                assertThrows(
                        IllegalStateException.class,
                        () -> service.placeAndFail(
                                "ORDER-ROLLBACK"));

        assertEquals(
                "planned rollback",
                ex.getMessage());

        assertEquals(
                0,
                store.countByRef("ORDER-ROLLBACK"));

        // JDBC rollback cannot undo a singleton counter.
        assertEquals(1, counter.value());
    }

    @Test
    void multipleCallsAreLocalToThisTestFixture() {
        service.place("ORDER-X");
        service.place("ORDER-Y");

        assertEquals(2, store.count());
        assertEquals(1, store.countByRef("ORDER-X"));
        assertEquals(1, store.countByRef("ORDER-Y"));
        assertEquals(2, counter.value());
    }
}
```

### 22.1. Tại sao @BeforeEach và @AfterEach đều dọn?

- `@BeforeEach` đảm bảo test **không phụ thuộc test trước đó** và có clean baseline.
- `@AfterEach` chủ động trả shared fixtures về trạng thái sạch cho test kế tiếp hoặc class khác.
- Nếu một test fail giữa method, Jupiter vẫn gọi `@AfterEach` khi lifecycle tiếp tục bình thường; nhưng process crash/kill có thể bỏ cleanup, vì vậy CI external resources vẫn cần namespace/TTL/teardown.
- Không có `@Transactional` trên JUnit method, nên `deleteAll()` ngoài service transaction có thể commit theo datasource auto-commit. Điều này khác với cleanup diễn ra trong test-managed transaction bị rollback.

### 22.2. Tại sao hai lần cleanup không phải lúc nào cũng là lựa chọn tốt nhất?

Trong DB thật có foreign keys, large tables hoặc parallel tests dùng common DB, full-table delete có thể gây xung đột và chậm. Hãy chọn **per-test schema/database/transaction isolation/targeted cleanup**. Lab sử dụng embedded H2 chỉ sở hữu bảng riêng nên mô hình dễ hiểu.

### 22.3. Vì sao test rollback mong counter=1?

Đó là assert **cố ý** để chỉ ra memory side effect không rollback. Fixture reset counter trước test tiếp theo nên class vẫn độc lập. Nếu bất kỳ test sau nào mong counter=0 nhưng thiếu setup, chạy suite có thể fail.

## 23. AnotherOrderSuiteTest.java — hai tests ở class khác

**src/test/java/example/suite/AnotherOrderSuiteTest.java**

```java
package example.suite;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = SuiteLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(FixedClockTestConfig.class)
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class AnotherOrderSuiteTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderStore store;

    @Autowired
    AttemptCounter counter;

    @BeforeEach
    void cleanBefore() {
        store.deleteAll();
        counter.reset();
    }

    @AfterEach
    void cleanAfter() {
        store.deleteAll();
        counter.reset();
    }

    @Test
    void anotherClassStillStartsWithCleanState() {
        assertEquals(0, store.count());
        assertEquals(0, counter.value());

        service.place("OTHER-A");

        assertEquals(1, store.count());
        assertEquals(1, counter.value());
    }

    @Test
    void duplicateKeyFailureDoesNotCorruptNextTest() {
        service.place("DUPLICATE");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> service.place("DUPLICATE"));

        assertEquals(
                1,
                store.countByRef("DUPLICATE"));

        // The second attempt incremented before DB rejected it.
        assertEquals(2, counter.value());
    }
}
```

### 23.1. Hai classes có thể reuse context

Hai classes có cùng `@SpringBootTest(classes=...)`, `@Import(FixedClockTestConfig.class)` và test bootstrap config. Trong cùng JVM nếu cache entry không bị evict/dirty, Spring TestContext có thể reuse context; dù vậy mỗi class sẽ reset bảng và counter ở test lifecycle.

Test **không assert thứ tự class A chạy trước class B**. Nếu Gradle sắp xếp B trước A, cả hai vẫn pass theo mục tiêu.

### 23.2. Duplicate-key test dạy điều gì?

`service.place("DUPLICATE")` đầu tiên commit. Lần thứ hai vi phạm primary key, Spring JDBC exception translation thường chuyển lỗi constraint của H2 thành `DataIntegrityViolationException` hoặc subclass (như `DuplicateKeyException`). Lần thứ hai rollback nhưng lần đầu vẫn còn; test assert DB có 1 row, counter có 2 attempts. Nếu assertion fail vì SQL exception translation của provider khác, cần test vendor cụ thể, không nuốt exception để xanh.

### 23.3. Vì sao không dùng @DirtiesContext cho class này?

Nó chỉ cần reset **DB row và bean counter**, không thay Spring bean definitions/configuration. Dùng dirty context sẽ startup lại datasource và mọi beans, giảm hiệu năng mà không giải quyết underlying design.

## 24. PureIsolationTest.java — ba unit tests không cần Spring

**src/test/java/example/suite/PureIsolationTest.java**

```java
package example.suite;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Random;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PureIsolationTest {

    @Test
    void fixedClockMakesLocalDateIndependentOfCiZone() {
        Instant moment =
                Instant.parse("2026-12-31T23:30:00Z");

        Clock utc = Clock.fixed(
                moment, ZoneId.of("UTC"));

        Clock hcm = Clock.fixed(
                moment, ZoneId.of(
                        "Asia/Ho_Chi_Minh"));

        assertEquals(
                LocalDate.of(2026, 12, 31),
                LocalDate.now(utc));

        assertEquals(
                LocalDate.of(2027, 1, 1),
                LocalDate.now(hcm));
    }

    @Test
    void equalSeedsYieldEqualIndependentDraws() {
        Random left = new Random(314159L);
        Random right = new Random(314159L);

        for (int i = 0; i < 100; i++) {
            assertEquals(
                    left.nextInt(1_000_000),
                    right.nextInt(1_000_000));
        }
    }

    @Test
    void concurrentCounterUsesAtomicOperation()
            throws Exception {
        AtomicInteger total =
                new AtomicInteger();

        int workers = 4;
        int loops = 500;

        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start =
                new CountDownLatch(1);

        List<Future<?>> futures =
                new ArrayList<>();

        try {
            for (int worker = 0;
                    worker < workers;
                    worker++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    for (int i = 0; i < loops; i++) {
                        total.incrementAndGet();
                    }
                    return null;
                }));
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get(30, TimeUnit.SECONDS);
            }

            assertEquals(
                    workers * loops,
                    total.get());
        }
        finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

### 24.1. Ba tests độc lập và có oracle rõ

- `fixedClockMakesLocalDateIndependentOfCiZone`: cùng một Instant, hai explicit Zones cho hai dates dự kiến; không dựa timezone host.
- `equalSeedsYieldEqualIndependentDraws`: hai PRNG instances cùng seed và draw order cho cùng sequence; không share state across test threads.
- `concurrentCounterUsesAtomicOperation`: bốn worker tasks cùng tăng AtomicInteger; test dùng `Future.get(30s)` để chờ hoàn thành hoặc fail hữu hạn, không `Thread.sleep`. Nó kiểm tra safe code path, **không ép cố ý tạo race**.

### 24.2. 30 giây không phải SLA

Timeout 30s bảo vệ CI khỏi treo; đây không phải assertion “4 workers luôn phải xong trong 30ms”. Nếu CI quá tải tới mức 2.000 atomic increments mất hơn 30s, cần điều tra host contention/thread pool starvation thay vì tăng timeout vô hạn.

### 24.3. Vì sao không dùng shared static Random?

Nếu cùng một Random instance được nhiều tests/threads consume, case nào nhận draw #N phụ thuộc schedule. Ở test này Random được tạo **bên trong từng test method** và không rò ra ngoài.

## 25. Chạy bộ lab

Yêu cầu JDK 17, Gradle Wrapper tương thích Spring Boot 3.3 (ví dụ Gradle 8.7), Maven Central/dependencies cache. Dự án không cần Docker hay external DB.

### 25.1. Chạy unfiltered suite

```bash
./gradlew clean test
```

Hoặc Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

### 25.2. Chạy từng class

```bash
./gradlew test --tests example.suite.OrderSuiteIsolationTest
./gradlew test --tests example.suite.AnotherOrderSuiteTest
./gradlew test --tests example.suite.PureIsolationTest
```

### 25.3. Chạy đúng một failing method

```bash
./gradlew test --tests \
  'example.suite.OrderSuiteIsolationTest.rollbackRemovesRowButMemoryStateRequiresReset'
```

Trên Windows PowerShell tránh dùng shell backslash continuation như Bash; ghi một dòng hoặc dùng backtick PowerShell nếu cần. Chỉ chọn method làm test context/resource lifecycle khác với full suite, nên ghi cả hai commands khi báo lỗi.

### 25.4. Buộc fresh execution để chẩn đoán

```bash
./gradlew test --rerun-tasks --no-build-cache --info
```

Không dùng `--dry-run` để chứng minh tests thực thi; nó chỉ lập task plan.

### 25.5. Đọc JUnit XML/HTML

Gradle thường tạo:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

**Dự kiến 9 phương thức JUnit** ở ba classes:

| Class | @Test methods | Có Spring context? |
| --- | ---: | --- |
| `OrderSuiteIsolationTest` | 4 | Có |
| `AnotherOrderSuiteTest` | 2 | Có |
| `PureIsolationTest` | 3 | Không |
| **Tổng** | **9** | Theo class |

Không nói các tests đã PASS trước khi xem report thật. Nếu một CI job chạy chỉ hai classes qua filter, counts của job nhỏ hơn 9 theo đúng selection; phải ghi filter để không coi là “JUnit bỏ sót”.

### 25.6. Thử parallel trong sandbox

Để thử JUnit concurrency, có thể thêm test resource `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
```

Vì runnable `build.gradle` đang truyền system property `junit.jupiter.execution.parallel.enabled=false` mặc định, bạn **phải** override khi chạy:

```bash
./gradlew test -PjunitParallel=true --rerun-tasks
```

JUnit configuration parameters có precedence; JVM system property của test task có thể override file. Trước khi bật, xác nhận test resource lock và lifecycle. Hai Spring classes dùng cùng `@ResourceLock` nên không đồng thời xóa cùng bảng trong **một Jupiter execution**; unit tests không dùng DB và an toàn song song theo design.

**Không kết luận toàn CI multi-fork an toàn** chỉ từ bài lab: resource lock không vượt JVM boundaries.

## 26. Kiểm thử anti-pattern riêng, không trộn vào runnable suite

### 26.1. Static state leak

```java
class BadSuiteStateTest {
    static int count;

    @Test
    void testA() {
        count++;
    }

    @Test
    void testB() {
        assertEquals(0, count);
    }
}
```

Nếu test A chạy trước B trong cùng JVM, B fail. Nhưng Java/JUnit không bảo đảm thứ tự A/B khi không có order configuration, nên một full suite có thể fail ngẫu nhiên. **Đây là demo cố ý sai, không chép vào `src/test/java` của lab chính.**

Sửa bằng state local per test, `@BeforeEach` reset cho class sở hữu resource hoặc làm cả behavior trong một test có state rõ.

### 26.2. Mutable singleton state leak

```java
@SpringBootTest
class BadSpringStateTest {

    @Autowired AttemptCounter counter;

    @Test
    void assumesFreshApplicationContext() {
        assertEquals(0, counter.value());
    }
}
```

Nếu cùng cached context đã bị test khác tăng counter và không reset, assertion có thể fail khi chạy suite, nhưng pass đơn lẻ. Sửa fixture ownership; không thêm `@DirtiesContext` bừa bãi.

### 26.3. DB pollution

```java
@Test
void testA() {
    jdbc.update(
            "insert into orders(ref) values (?)",
            "DUP");
}

@Test
void testB() {
    jdbc.update(
            "insert into orders(ref) values (?)",
            "DUP");
}
```

Nếu test-managed transactions/cleanup không được áp dụng, test sau gặp duplicate key. Giải pháp: unique per-test ref hoặc cleanup đúng boundary. Khi tests chạy trên shared external DB, dùng namespaces/schemas/containers riêng thay vì xóa bảng của nhau.

### 26.4. @Transactional false assurance

```java
@Transactional
@Test
void sendsHttpRequest() {
    httpClient.post("/orders", request);
}
```

Test thread transaction không bảo đảm HTTP server thread tham gia transaction đó. Server có thể commit row thật và để lại cho test sau. Bổ sung cleanup qua API/database isolation thay vì tin rollback test thread.

### 26.5. Await không đúng

```java
@Test
void badAsyncTest() {
    eventPublisher.publishEvent(new Event());
    assertEquals(1, asyncObserver.count());
}
```

Nếu listener chạy async, count có thể chưa tăng. Dùng `CountDownLatch`/Awaitility/CompletionStage được thiết kế bởi app và timeout hữu hạn; không thêm `Thread.sleep(2000)`.

### 26.6. Shared port

```java
@BeforeEach
void startServer() {
    server = new TestServer(8080);
    server.start();
}
```

Hai classes cùng bắt port 8080 trong CI parallel sẽ collision. Dùng port 0/random port và đọc port thực, hoặc chỉ chạy một shared server do suite owns và đảm bảo teardown/health.

## 27. Phân biệt leak và race bằng thí nghiệm có kiểm soát

| Thí nghiệm | Nếu fail | Nếu pass | Hạn chế |
| --- | --- | --- | --- |
| Chạy single method | Lỗi độc lập/pure/môi trường | Có thể cần pollution/order/load | Không chứng minh test đúng |
| Chạy pair A rồi B | B bị A ảnh hưởng có thể xảy ra | Có thể thiếu các prerequisites | Pair order cần cố định |
| Chạy full suite sequential | State leak/resource exhaust | Race có thể bị che | Không loại trừ CI env |
| Chạy full suite parallel | Race/collision/load | Race hiếm vẫn tồn tại | Không proof thread safety |
| Chạy một JVM fork | Context/static reuse tối đa | Có thể thay resource pressure | Không tương đương CI nhiều forks |
| Chạy nhiều forks | External collision/leak theo process | Static leak được che | Cache/process differs |
| Chạy CI container local | OS/JDK/config gần CI | Network/secret khác vẫn có | Không phải exact CI |
| Dùng fixed Clock + seed | Bớt random/time noise | Có thể còn DB/scheduling | Seed không đồng bộ threads |
| Reset DB/bean state | Nếu fix fail → state pollution | Có thể che nguyên nhân sâu hơn | Ensure cleanup scope proper |

Làm **một thay đổi mỗi lần**, ghi command và test counts. Đổi đồng thời Spring profile, JDK, parallel settings và test order rồi thấy xanh không thể chỉ ra root cause.

## 28. Điều tra lỗi chỉ xuất hiện sau nhiều tests

Khi suite fail gần cuối, sau hàng trăm methods, ngoài state leaks hãy kiểm tra **resource exhaustion**:

- Hikari connection pool connections không được trả, leak detection warning.
- HTTP clients và response bodies không đóng.
- ExecutorService threads không shutdown.
- Scheduled tasks vẫn chạy sau test.
- Files/InputStreams/socket handles không đóng.
- Testcontainers containers/services bị start/stop quá nhiều hoặc không dọn.
- Spring contexts quá nhiều do different profiles/@MockBean customizers hoặc @DirtiesContext.
- JVM heap/offheap pressure, GC pauses, native memory, file descriptors.
- Global caches/maps/listeners tăng không giới hạn.
- Broker consumer groups/Redis keys/sessions tăng across tests.
- Dynamic ports/ephemeral connections cạn trên CI host.

### 28.1. Không kết luận “memory leak” chỉ từ OutOfMemoryError

Có thể do heap size CI nhỏ hơn hoặc test fixture lớn. Đọc heap/GC diagnostics, process limits và number of contexts/resources. Tối ưu pool/cache sizes có thể cần, nhưng phải giữ fidelity of integration tests.

### 28.2. Logs nên có correlation

Ghi test class/method, thread name, process worker ID, container ID/port, datasource URL/schema và contextual request ID **test-only** để biết ai tạo resource. Không log customer PII, secrets hoặc credentials.

### 28.3. Hikari pool leak

Nếu app dùng HikariCP, có thể xem active/idle/pending connections metrics và tùy chọn leak detection threshold trong test profile. Cần tránh false positives khi CI bị pause/GC. Một connection “chưa trả trong N giây” là dấu hiệu, không tự xác nhận leak vĩnh viễn.

## 29. CI-specific mismatches

### 29.1. JDK/Gradle/dependency versions

Sử dụng Gradle Wrapper và Java toolchain, pin Spring Boot BOM/lock dependency versions khi thích hợp. Nếu CI dùng JDK khác để chạy Gradle daemon và toolchain, kiểm tra **JDK thực của test worker**. Không tin vào IDE Project SDK để mô tả CI.

### 29.2. Timezone/locale

Một instant UTC có thể là ngày hôm sau tại Asia/Ho_Chi_Minh; `LocalDate.now()` có thể khác. Inject `Clock`/`ZoneId`. Không test expected date bằng hardcoded “today” khi đồng hồ di chuyển.

### 29.3. OS và file paths

Linux case-sensitive paths; Windows thường khác. Mac có behavior khác theo filesystem. Dùng `ClassLoader.getResource(...)` với exact case, không trông cậy working directory.

### 29.4. Environment variables/profiles

Một CI profile có thể bật scheduler, auto migrations, external clients hoặc security filters mà laptop không có. Log **activeProfiles** và property names/sanitized values; không in raw secrets.

### 29.5. Container startup/readiness

CI fresh start dễ fail hơn local luôn có Docker service; dùng readiness/health checks, Testcontainers wait strategy đúng provider, xem image pull/network. Không chỉ tăng fixed sleep.

### 29.6. Clock speed và CPU quotas

CI chia sẻ CPU và có cold JIT/class loading khiến test timeouts ngắn dễ fail. Việc test method mất 200ms local và 2s CI không chứng minh business logic sai nếu test assert timing quá chặt. Khi performance là contract thật, dùng benchmark/SLO environment phù hợp, không dùng sleep-based unit test.

### 29.7. CI có thêm shards

Shards có thể chạy tasks khác nhau hoặc cùng external resource namespace, gây collision. Dùng per-shard schema/topic/Redis prefix; khi tổng hợp reports, tránh double count rerun attempts.

## 30. Bảng lỗi -> bước chẩn đoán

| Dấu hiệu | Giả thuyết chính | Evidence/giải pháp |
| --- | --- | --- |
| Expected zero, actual one | Previous test left DB/bean state | @BeforeEach, DB query, logs owner |
| Duplicate key only suite | Same test fixture ID reused | Per-test IDs/cleanup/schema |
| Mockito verify unexpected interactions | Mock state reused/reset wrong | @MockBean lifecycle, stubs local |
| ApplicationContext no longer active | @DirtiesContext/eviction parallel | Cache DEBUG logs, serialize/avoid dirty |
| Tests pass with @DirtiesContext | Hidden mutable state | Reset state properly, measure context cost |
| Connection refused after class A | Container closed but context cached | Align container/context lifecycle |
| Address already in use | Fixed port collisions | Random port, resource ownership |
| Timed out only CI | Sleep-based oracle/load/readiness | Await condition with finite timeout |
| Clock-related date mismatch | Default timezone/near midnight | Fixed Clock and ZoneId |
| Random failure differs every run | Unlogged seed/state | Per-test seed and replay |
| @Transactional test data leaks | Other thread/HTTP/external side effect | Test boundary, real cleanup |
| Wrong JSON path only Linux | Case-sensitive file path | Exact resource case, UTF-8 |
| Pass single, fail suite in same JVM | Static/context singleton shared | Isolation, fixture reset |
| Fail only with maxParallelForks>1 | External collisions/multiple JVMs | Per-worker namespace, logs |
| Fail only when JUnit parallel | Race in shared memory | @ResourceLock/atomic/immutable data |
| Fail after 300 methods | Resources exhausted | Pools, threads, descriptors, cache size |
| Different JDK on CI | Runtime semantics/tzdb/dependencies | java -version, Gradle toolchain |
| BUILD SUCCESSFUL but no tests | Filter/task skip/no discovery | XML counts/Gradle task |
| Failed to load ApplicationContext | Context configuration/dependency | Root cause exception, not test order alone |
| Error only on fresh CI | Service not ready/schema missing | Health checks/migrations |
| Flaky @Async event test | Assert before completion | Latch/CompletableFuture/Awaitility |
| Race disappears sequential | Concurrency factor identified | Fix thread safety, don't stop at workaround |

## 31. Failure artifact để người khác tái hiện

```yaml
# Template minh họa, không phải log một run thực.
repositoryRevision: "exact-commit-sha"
testTask: ":test"
failingTest: "example.suite.OrderSuiteIsolationTest.method"
failingCommand: "./gradlew test --rerun-tasks --no-build-cache"
minimalReproducer: "list the smallest test set and order"
jdk: "record java -version and test JVM toolchain"
gradle: "record wrapper version"
springBoot: "3.3.0"
junit: "resolved platform/Jupiter versions"
os: "record CI image digest and architecture"
timezone: "UTC"
locale: "explicit value"
profiles: "list active profiles; no secret values"
execution:
  maxParallelForks: 1
  forkEvery: 0
  junitParallel: false
  ciShard: "name or index"
externalResources:
  database: "sanitized url/schema/container image"
  broker: "sanitized topic and consumer group"
  serviceHealth: "health check summary"
random:
  seed: "record if used"
  scenarioIndex: "record if randomized"
failure:
  exceptionClass: "fully-qualified exception"
  expected: "expected outcome"
  actual: "observed outcome"
artifacts:
  - "JUnit XML"
  - "Gradle HTML report"
  - "sanitized test logs"
  - "thread dump or heap data if needed"
```

**Không in secrets, access tokens, customer PII, private URLs có credentials hoặc full payment payload.** Nếu cần xác minh external services, log resource identifiers đã sanitize và correlation IDs an toàn.

## 32. Từ failure artifact đến regression test

1. Tái hiện trên commit cũ với exact test set.
2. Xác định state owner: static, singleton, DB, cache, file, external service hay scheduler.
3. Chứng minh trigger: một test trước tạo pollution hoặc một thread kết thúc muộn.
4. Sửa fixture/business implementation; không thay expected để test xanh giả.
5. Bổ sung **regression test** tái hiện behavior: ví dụ DB row không rò sang test tiếp theo hoặc async listener phải complete trước assertion.
6. Chạy isolated reproducer, cả hai orders A→B/B→A nếu phù hợp.
7. Chạy full suite sequential và parallel khi mục tiêu hỗ trợ parallel.
8. Chạy trong CI environment tương ứng.
9. Ghi actual counts, wall time và remaining risks.
10. Nếu cần, giữ failing seed/fixture snapshot trong regression corpus.

### 32.1. Khi nào rerun có ích?

Rerun giúp ước lượng tần suất failure và thu logs, nhưng **không tự là giải pháp**. Nếu 1/100 runs fail, 100 runs pass sau fix vẫn không chứng minh xác suất failure là zero; nó là bằng chứng tăng độ tin cậy trong điều kiện đã đo.

### 32.2. Khi nào phải chấp nhận test không parallel?

Một số integration tests thay đổi external shared state hoặc dùng engine/driver không hỗ trợ concurrency. Có thể serialize có chủ đích bằng task/resource lock nếu cost chấp nhận được. Điều đó khác với bỏ mặc race trong production service, nơi concurrent calls là hành vi hợp lệ phải kiểm chứng.

### 32.3. Khi nào dùng contract/integration tests riêng?

Nếu lỗi do Kafka ordering, database serializability, Redis TTL hoặc HTTP timeout, pure unit test có thể không đủ. Tách provider integration test với Testcontainers/embedded server và môi trường gần production, fixture có ownership rõ, để tái hiện đúng failure mode.

## 33. Bài tập thực hành

### Bài 1 — Kiểm tra baseline

Copy project runnable, tạo Gradle Wrapper, chạy `./gradlew clean test`. Đọc reports, ghi số tests executed/passed/failed/skipped **thực**. Không lấy expected 9 làm log đã quan sát nếu chưa chạy.

### Bài 2 — Quan sát Spring context reuse

Thêm DEBUG `logging.level.org.springframework.test.context.cache=DEBUG` trong test profile, chạy hai Spring test classes. Đọc hit/miss/cache size. Không đồng nhất cache hitCount với số test methods.

### Bài 3 — Xóa @BeforeEach reset

Trong sandbox, tạm bỏ `counter.reset()` ở một trong hai Spring test classes. Chạy class riêng và full suite, quan sát khi nào singleton state làm test phụ thuộc thứ tự. Khôi phục reset sau thí nghiệm.

### Bài 4 — Xóa DB cleanup

Tạm bỏ `store.deleteAll()` ở `@AfterEach`, chạy các tests dùng cùng ref và xem cleanup/duplicate-key issue. Hãy giữ H2 lab riêng; đừng làm trên shared staging database.

### Bài 5 — @DirtiesContext như workaround

Tạm đặt `@DirtiesContext` lên một class. So startup/misses và thấy context mới có thể che bean counter leak; sau đó khôi phục và fix bằng fixture reset.

### Bài 6 — Thêm một test class cùng config

Tạo class thứ ba với cùng `@SpringBootTest`/`@Import` nhưng reset đầy đủ. Thử chạy 3 classes theo thứ tự khác; không đặt dependency vào class trước.

### Bài 7 — Rollback side effect

Gọi `service.placeAndFail`, assert DB row count 0 nhưng memory counter 1. Giải thích vì sao rollback test transaction không reset memory.

### Bài 8 — @Transactional test

Thêm `@Transactional` trên một JUnit test trong sandbox, quan sát rollback và `@AfterEach` semantics. Bỏ annotation khi muốn assert service commit thật như lab.

### Bài 9 — JUnit parallel

Thêm `junit-platform.properties` cấu hình parallel, chạy `-PjunitParallel=true`. Giữ `@ResourceLock` cho DB tests, theo dõi shared resources khác.

### Bài 10 — Bỏ @ResourceLock

Trong sandbox, remove locks và chạy JUnit parallel nhiều lần. Nếu race không xuất hiện, **không** tuyên bố suite đã an toàn; cần chứng minh resource isolation hoặc thêm deterministic overlap control.

### Bài 11 — Gradle forks

Tăng `maxParallelForks` lên 2 trong sandbox, xem context cache mỗi worker riêng và external resource isolation. Không coi JUnit ResourceLock là cross-process lock.

### Bài 12 — Fixed timezone

Đổi Gradle test JVM timezone sang Asia/Ho_Chi_Minh, kiểm tra `PureIsolationTest` vẫn pass vì dùng explicit clocks. So với anti-pattern `LocalDate.now()`.

### Bài 13 — Case-sensitive resources

Đặt test resource `fixtures/sample.json`, truy cập `Fixtures/Sample.json` để thấy lỗi trên case-sensitive filesystem. Sửa exact path, không lạm dụng platform-specific workaround.

### Bài 14 — Async event

Tạo một test listener async có `CountDownLatch`; assert sau khi await completion. Thử anti-pattern dùng sleep ngắn và quan sát nguy cơ flaky, sau đó bỏ sleep.

### Bài 15 — Startup readiness

Tạo một integration test dùng container/HTTP test server; thêm health check có timeout. So với fixed sleep và đo sự ổn định trên CI.

### Bài 16 — Duplicate key

Chạy `duplicateKeyFailureDoesNotCorruptNextTest`; nếu provider exception translation khác H2, xác minh root exception đúng, không đổi expectation mù.

### Bài 17 — Random seed

Dùng seeded generator cho randomized fixture và log seed. Chạy lại cùng seed/algorithm/call order. Không dùng một static Random chia sẻ khi JUnit parallel.

### Bài 18 — Test pairs

Tạo một fixture A làm thay đổi một property/global static và quên restore, fixture B đọc. Reproduce A→B rồi sửa `try/finally` restore hoặc inject property thay global state.

### Bài 19 — Resource exhaustion

Tạo một executor per test trong sandbox mà không shutdown và chạy nhiều tests. Dùng thread dump để xác nhận leak, sau đó sửa `try/finally`/`@AfterEach`.

### Bài 20 — CI artifact

Cấu hình CI lưu Gradle JUnit XML/HTML và sanitized logs của failed test. Ghi exact command, seed, JDK, worker, external service health.

### Bài 21 — Điều tra Spring profiles

Chạy cùng test với hai profiles (một có scheduler, một không), ghi properties và background jobs. Đừng kết luận bug chỉ vì đổi profile làm test pass.

### Bài 22 — Testcontainers lifecycle

Quan sát một shared context giữ connection tới container đã dừng khi class A teardown. Thiết kế lifecycle theo context/JVM hoặc cô lập per class.

### Bài 23 — Rerun một class

Chạy `--tests example.suite.OrderSuiteIsolationTest` rồi full suite với same commit. So reports; không nhầm test selector làm khác lifecycle với run đầy đủ.

### Bài 24 — Lỗi CI only

Tạo matrix với OS/JDK/timezone/locale/forks phù hợp, thay từng biến. Ghi evidence thay vì đoán CI “chậm nên test fail”.

### Bài 25 — Regression trước/sau

Sau khi sửa một leak do test A, chạy A→B và B→A (nếu suite harness hỗ trợ), full suite và pipeline. Ghi số lần thử; đừng báo 100% chắc chắn từ một pass.

## 34. Checklist QA trước khi merge

- [ ] Có exact failing command, commit, JDK, task path, active profiles.
- [ ] Có JUnit XML/HTML reports, stack trace đầy đủ và test count thực.
- [ ] Đã phân biệt single-test, pair-test, suite-only, CI-only và intermittent.
- [ ] Mỗi test tự tạo dữ liệu/fixture nó cần, không phụ thuộc method order.
- [ ] Không dùng @TestMethodOrder để che state leakage ngoài workflow test rõ ràng.
- [ ] Static fields và singleton beans không giữ mutable state vượt test ngoài ý muốn.
- [ ] Shared Spring ApplicationContext không bị nhầm với fresh per-test context.
- [ ] @DirtiesContext chỉ dùng khi context thực sự dirty, không thay DB cleanup.
- [ ] Test-managed @Transactional và rollback boundary được hiểu đúng.
- [ ] HTTP/async/external calls không được giả định rollback theo test thread.
- [ ] Database rows/Redis keys/queues/files có ownership và cleanup rõ.
- [ ] Shared external DB không bị full-table delete từ parallel test khác.
- [ ] Mockito mocks/spies được reset/stub trong scope phù hợp.
- [ ] JUnit parallel và Gradle forks được kiểm soát độc lập.
- [ ] @ResourceLock/SAME_THREAD được dùng khi cần và đúng giới hạn cùng JVM.
- [ ] Không dùng Thread.sleep làm điều kiện đồng bộ async work.
- [ ] Background futures/executors được await/close với timeout hữu hạn.
- [ ] Test clock/ZoneId/Locale explicit, không phụ thuộc host midnight.
- [ ] Random seeds/algorithm/order được lưu khi cần replay.
- [ ] Filesystem resource path dùng đúng case và charset rõ.
- [ ] Network test dùng readiness/health, không sleep đoán.
- [ ] Ports/DB schemas/topics/Redis prefixes độc lập khi CI multi-fork/shards.
- [ ] Testcontainers lifecycle tương thích cached Spring contexts.
- [ ] Hikari/threads/file handles/resources không rò sau nhiều tests.
- [ ] CI secrets/external service values không bị log ra công khai.
- [ ] Gradle --rerun-tasks/--no-build-cache chỉ dùng khi cần fresh run.
- [ ] Mọi test failure được phân loại (assertion vs config vs discovery vs infra).
- [ ] Reduced reproducer đã fail trước fix và pass sau fix khi khả thi.
- [ ] Full suite và CI environment đã được xác minh sau sửa.
- [ ] Không tuyên bố tests thực thi/pass khi chỉ mới soạn ví dụ.

## 35. Quy tắc lựa chọn giải pháp

```text
Lỗi chỉ xảy ra trong suite/CI
     |
     +-- State từ test trước?
     |     -> Per-test fixtures, cleanup, immutable data,
     |        no global mutable state.
     |
     +-- Context reuse?
     |     -> Reset singleton/DB/cache; review @MockBean,
     |        @DirtiesContext only when truly needed.
     |
     +-- Transaction boundaries?
     |     -> Real DB commit/rollback test; async/HTTP
     |        effects need independent cleanup.
     |
     +-- Parallel execution?
     |     -> Resource isolation, JUnit @ResourceLock,
     |        atomic/locking, no shared external IDs.
     |
     +-- Time/random?
     |     -> Clock.fixed, ZoneId, per-case seed.
     |
     +-- CI environment mismatch?
     |     -> JDK/OS/locale/TZ/profiles/dependencies,
     |        resource readiness, permissions.
     |
     +-- Fail after many tests?
     |     -> Pools/threads/files/context cache exhaustion.
     |
     +-- Root cause still unclear?
           -> Capture artifacts, minimize test subset,
              change one variable, reproduce before fix.
```

**Kết luận:** Khi một test chỉ fail trong full suite hoặc trên CI, điều quan trọng nhất là **xác định state và boundary mà test đã không tự kiểm soát**. Spring context cache có thể reuse singletons; transactions không hoàn tác external/memory side effects; parallel JVMs/threads có thể gây race và resource collisions; CI có timezone, JDK, OS và timing khác. Một bộ test đáng tin phải tự chuẩn bị dữ liệu, cleanup đúng scope, dùng thời gian/ngẫu nhiên kiểm soát được và báo cáo đầy đủ điều kiện thực thi. Đừng đổi thứ tự tests, thêm sleep, tắt parallel hoặc lạm dụng @DirtiesContext chỉ để tạm làm build xanh mà không xử lý root cause.

## 36. Tài liệu chính thức

- Spring Framework — Context caching trong TestContext: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — @DirtiesContext: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework — Transaction management in tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — Parallel test execution: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers and service connections: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Gradle — Testing Java/JVM projects, maxParallelForks, forkEvery, filters: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Test task reference and test logging: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- JUnit 5 Jupiter — Writing tests, @ResourceLock, parallel execution: https://docs.junit.org/5.10.5/user-guide/index.html
- JUnit Jupiter — @ResourceLock API: https://junit.org/junit5/docs/5.10.5/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html
- JUnit Jupiter — ExecutionMode/parallel tests: https://junit.org/junit5/docs/5.10.5/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Execution.html
- Java 17 — Clock fixed/zone semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java 17 — AtomicInteger concurrency semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Java 17 — Random seeded sequences: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html
- HikariCP — Connection-pool configuration and leak detection: https://github.com/brettwooldridge/HikariCP
