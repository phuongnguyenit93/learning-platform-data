# JUnit parallel execution và số worker của Gradle: cách ly kiểm thử Spring Boot đúng cách

## 1. Một cấu hình “chạy song song” có thể mang ba ý nghĩa khác nhau

Khi một dự án Spring Boot có hàng trăm bài kiểm thử, việc bật parallel execution thường giúp giảm tổng thời gian CI. Nhưng hai dự án cùng ghi “parallel=4” vẫn có thể có hành vi rất khác nhau: một dự án chạy bốn **JVM test processes**, một dự án chạy bốn **JUnit worker threads trong cùng một JVM**, còn dự án khác có thể kết hợp cả hai.

Vì vậy câu hỏi không phải chỉ là “có bật song song chưa?” mà là:

1. **Gradle được phép sử dụng tối đa bao nhiêu worker slots?** Điều này chịu ảnh hưởng của `--max-workers`/`org.gradle.workers.max`.
2. **Mỗi tác vụ Gradle `Test` được phép fork bao nhiêu JVM chạy test cùng lúc?** Điều này do `maxParallelForks` điều khiển, mặc định là 1.
3. **Trong mỗi JVM, JUnit Jupiter có cho phép những test classes/methods chạy đồng thời không?** Điều này do `junit.jupiter.execution.parallel.enabled`, execution modes và pool strategy điều khiển.
4. **Các tests đó có chia sẻ tài nguyên không?** `static` fields, Spring `ApplicationContext`, embedded database, schema, filesystem, Redis/Kafka, Testcontainers, ports, system properties hoặc một `@MockitoBean` là các ranh giới dễ xung đột.
5. **Nếu một nhóm không an toàn khi chạy song song, cô lập ở tầng nào?** `@Execution(SAME_THREAD)`, `@ResourceLock`, `@Isolated`, `@Tag("serial")` và một Gradle `Test` task riêng không có phạm vi giống nhau.

Bài học cung cấp **một chiến lược cấu hình, kiểm chứng và gỡ lỗi** cụ thể cho Java 17+, Spring Boot 3.5.x, JUnit Jupiter và Gradle. Phần thực hành có một dự án Gradle với hai nhóm: các kiểm thử độc lập được phép chạy song song, và một nhóm “serial” chạy trong một tác vụ Gradle riêng. Mã dùng state tách biệt, `@TempDir`, `@ResourceLock`, `@TestInstance(PER_CLASS)`, `@Execution`, `@Isolated` và Spring TestContext; không cần database, Docker hay service ngoài.

## 2. Ba tầng thực thi: Gradle → JVM test process → JUnit threads

```text
Gradle build / task graph
  |
  +-- Gradle worker slots (--max-workers, org.gradle.workers.max)
        |
        +-- Test task (ví dụ :app:test)
              |
              +-- forked test JVM A  [maxParallelForks của Test task]
              |      |
              |      +-- JUnit Platform / Jupiter engine
              |           +-- test class X
              |           +-- test class Y
              |           +-- method a, method b
              |                 threads theo Jupiter parallel config
              |
              +-- forked test JVM B
                     |
                     +-- JUnit Platform / Jupiter engine
                          +-- các test classes/methods khác

Một JVM khác  =>  heap/static fields/Spring ContextCache khác
Hai threads cùng JVM => có thể chia sẻ static fields và Spring context
Hai JVM khác nhau => vẫn có thể va chạm ở DB, Redis, file path, port...
```

**Những khác biệt không được phép bỏ qua:**

| Cấu hình | Cấp tác động | Tăng cái gì? | Không bảo đảm điều gì? |
|---|---|---|---|
| `--max-workers=4` | Gradle build | Giới hạn worker slots cho các tác vụ/workers của Gradle | Không tự làm một test method chạy cùng lúc với method khác |
| `--parallel` | Gradle multi-project scheduling | Các tác vụ của những projects khác nhau có thể chạy song song khi được phép | Không đồng nghĩa Jupiter method concurrency |
| `Test.maxParallelForks = 2` | Gradle `Test` task | Tối đa hai JVM test được fork đồng thời, chịu giới hạn tổng workers | Không điều khiển số JUnit threads bên trong từng JVM |
| `Test.forkEvery = 1` | Vòng đời JVM test | Fork mới sau mỗi test class, để cô lập state giữa các classes | Không làm test methods mặc định chạy concurrent |
| `junit.jupiter.execution.parallel.enabled=true` | JUnit Jupiter trong từng JVM | Bật hỗ trợ parallel execution | Chưa đủ nếu execution modes vẫn `same_thread` |
| `mode.default=concurrent` | JUnit methods/nodes | Cho phép thực thi đồng thời theo mode | Không tách heap, static state hay DB |
| `mode.classes.default=concurrent` | JUnit top-level test classes | Cho phép nhiều classes cùng được schedule | Không làm các methods trong một class mặc nhiên concurrent nếu mode methods là `same_thread` |
| `fixed.parallelism=2` | JUnit desired pool parallelism | Mục tiêu song song cho engine trong **một JVM** | Không phải `maxParallelForks`, không nhất thiết hard cap threads |
| `@ResourceLock` | JUnit execution plan | Khóa quyền dùng tài nguyên đặt tên giữa tests do cùng engine phối hợp | Không tạo distributed lock giữa **hai Gradle forked JVMs** |
| `@Isolated` | JUnit execution plan | Cô lập một test class khỏi tests khác trong cùng execution plan | Không tự ngăn JVM khác hay build khác dùng DB/file chung |

**Ví dụ tư duy:** Đặt `maxParallelForks=2` và Jupiter `fixed.parallelism=3` có thể cho phép hai JVM, mỗi JVM có các JUnit test nodes chạy đồng thời theo cấu hình ba threads. Không được mặc định rằng hệ thống luôn có chính xác `2 × 3 = 6` tests chạy cùng thời điểm: số classes sẵn sàng, resource locks, Gradle worker budget, CPU, JUnit fork-join compensation và kế hoạch thực thi đều ảnh hưởng. Đây là **hai giới hạn tại hai tầng khác nhau**, không phải một thuộc tính duy nhất.

## 3. Gradle --max-workers, --parallel và maxParallelForks

### 3.1. --max-workers: ngân sách worker cho cả build

Gradle CLI hỗ trợ:

```bash
./gradlew test --max-workers=4
```

hoặc trong `gradle.properties` của project:

```properties
org.gradle.workers.max=4
```

`--max-workers` đặt giới hạn worker slots mà Gradle dùng cho build. Giá trị mặc định thường dựa vào số processors có sẵn. Worker budget này dùng cho nhiều loại công việc, không chỉ test, như compilation, tasks có Worker API và test worker processes. Do đó không hợp lý khi suy luận “max-workers=4 thì chắc chắn có bốn test classes cùng chạy”.

**Lưu ý khi CLI ghi đè:** Nếu CI chạy `./gradlew test --max-workers=1`, `maxParallelForks=4` trong build script không buộc Gradle được phép chạy bốn JVM test cùng lúc. Effective concurrency bị ràng buộc bởi tổng worker budget của Gradle.

### 3.2. --parallel: song song các projects, không phải JUnit methods

```bash
./gradlew test --parallel --max-workers=4
```

Tùy project structure và task dependencies, Gradle có thể chạy `:module-a:test` và `:module-b:test` đồng thời. Trong một project đơn, `--parallel` **không** phải cách bật concurrent test methods trong cùng class.

`--parallel` còn có thể làm hai test tasks ở **hai modules khác nhau** cùng dùng chung PostgreSQL container, Redis database, Redis key prefix, mock server port hoặc Docker network. Vì vậy một nhóm tests `@Isolated` ở module A không tự khóa module B.

### 3.3. maxParallelForks: số JVM chạy test của một Test task

```groovy
tasks.named('test', Test) {
    maxParallelForks = 2
}
```

Đây là cấu hình Gradle Groovy DSL. Mặc định `maxParallelForks=1`. Khi giá trị lớn hơn 1, Gradle có thể phân phối test classes sang nhiều **forked test JVMs**.

Điều này tạo **process isolation**:
- Mỗi JVM có heap, classloader, `static` fields và JVM system properties riêng.
- Spring TestContext cache của một JVM không dùng chung với JVM khác.
- Hai JVM có thể cùng truy cập **tài nguyên ngoài** như cùng database server/schema, filesystem, S3 bucket, message broker hoặc một TCP port cố định.
- Một số phần config như environment variables vẫn được kế thừa giống nhau, nên không tự tạo isolation cho tên database/schema.

**Cẩn trọng:** Việc chạy hai JVM không có nghĩa tất cả tài nguyên tự tách. Đây là lý do nhiều CI suite pass khi `maxParallelForks=1` nhưng fail khi nâng lên 4: các test cùng xóa bảng, dùng file cố định hoặc tranh cổng TCP.

### 3.4. forkEvery: số test classes trước khi recycle JVM

```groovy
tasks.named('test', Test) {
    forkEvery = 0
}
```

Trong Gradle, `forkEvery=0` là giá trị mặc định có nghĩa **không giới hạn số classes trước khi recycle JVM vì thuộc tính này**. `forkEvery=1` có nghĩa mỗi test class xong sẽ có JVM mới cho class tiếp theo. Dùng nó có thể cô lập `static` state hoặc memory leaks trong framework cũ nhưng rất tốn thời gian:
- JVM startup lặp lại.
- Spring context cache không còn tái sử dụng tốt giữa classes.
- Mỗi JVM phải nạp classpath lại, có thể init nhiều HTTP/JPA/Testcontainers clients.
- Khi test tải dữ liệu lớn, overall memory/CPU vẫn có thể cao do nhiều forks.

**Không** dùng `forkEvery=1` như “nút sửa mọi test flaky” nếu nguyên nhân thật là shared external database hoặc ports: nhiều JVM mới vẫn tranh tài nguyên đó.

### 3.5. org.gradle.test.worker nhận diện một test process

Gradle đặt JVM system property `org.gradle.test.worker` để phân biệt test worker processes. Có thể dùng nó để tạo tên file/thư mục test riêng:

```java
String workerId =
        System.getProperty("org.gradle.test.worker", "IDE");

System.out.println("worker=" + workerId
        + ", pid=" + ProcessHandle.current().pid()
        + ", thread=" + Thread.currentThread().getName());
```

Đây là fragment trong test; khi chạy qua IDE, property có thể không được đặt nên `IDE` là fallback. Trong Gradle, worker ID giúp phân biệt **test processes** chứ không phải test thread IDs. Không hard-code `worker=1` hoặc `worker=2` thành assertion, vì assignment và scheduling không phải business contract.

## 4. JUnit Jupiter song song được bật thế nào?

### 4.1. Bật engine chưa đủ để mọi test chạy concurrent

Tệp chuẩn:

```text
src/test/resources/junit-platform.properties
```

Một cấu hình cho phép concurrent methods và classes:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

JUnit Jupiter có execution modes:
- `SAME_THREAD`: node chạy trong cùng thread với parent node theo quy tắc engine.
- `CONCURRENT`: node được phép chạy đồng thời, trừ khi bị resource lock hoặc cấu hình khác giới hạn.

**Điểm quan trọng:** Mặc định Jupiter sequential/same-thread. Chỉ đặt `parallel.enabled=true` vẫn có thể không cho methods/classes chạy concurrent nếu default modes là `same_thread`.

### 4.2. Ba cách cấu hình thường gặp

| Mục tiêu | `mode.default` | `mode.classes.default` | Ý nghĩa |
|---|---|---|---|
| Tất cả tests mặc định sequential trong một JVM | `same_thread` | `same_thread` | Mặc định an toàn |
| Classes concurrent, methods trong mỗi class sequential | `same_thread` | `concurrent` | Thường là điểm khởi đầu tốt cho Spring integration tests đã cô lập |
| Classes sequential, methods trong một class concurrent | `concurrent` | `same_thread` | Phù hợp lớp test độc lập, không dùng shared mutable fixtures |
| Cả classes và methods concurrent | `concurrent` | `concurrent` | Đòi hỏi isolation cao nhất |

Bạn có thể ghi đè lựa chọn mặc định cho một class/method bằng `@Execution(ExecutionMode.CONCURRENT)` hoặc `@Execution(ExecutionMode.SAME_THREAD)`.

**Ngoại lệ quan trọng:** JUnit có hành vi mặc định riêng đối với test classes dùng `@TestInstance(PER_CLASS)` hoặc `@TestMethodOrder`; không nên chỉ nhìn mode default rồi kết luận các methods sẽ parallel. Nếu thật sự muốn concurrent ở một class `PER_CLASS`, annotate `@Execution(CONCURRENT)` và tự bảo đảm shared instance thread-safe. Đừng chạy `@TestMethodOrder` cùng concurrent methods khi test logic phụ thuộc thứ tự.

### 4.3. fixed và dynamic strategy

JUnit đọc các config parameters:

```properties
# Mục tiêu hai worker threads cho JUnit engine ở mỗi JVM
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2

# Dự án Java 17 có thể giới hạn kích thước pool
junit.jupiter.execution.parallel.config.fixed.max-pool-size=2
```

Hoặc:

```properties
junit.jupiter.execution.parallel.config.strategy=dynamic
junit.jupiter.execution.parallel.config.dynamic.factor=0.5
```

- `fixed`: yêu cầu desired parallelism rõ, phù hợp thử nghiệm CI có ngân sách CPU cố định.
- `dynamic`: tính theo processors có sẵn × factor; mặc định factor thường là 1.
- `custom`: cho phép một custom `ParallelExecutionConfigurationStrategy`; không cần cho đa số projects.

**Đừng nhầm parallelism với hard maximum concurrency.** JUnit Jupiter chạy trên nền `ForkJoinPool`; blocking/synchronization có thể khiến pool tạo thêm threads theo implementation. `fixed.max-pool-size` cung cấp thêm giới hạn khi cần, nhưng không biến một test đồng bộ hóa sai thành test an toàn. Quan sát mức thực thi trong CI thay vì khẳng định số threads luôn bằng một số tuyệt đối.

### 4.4. System properties, junit-platform.properties và overrides

JUnit Platform có các cách nhận configuration parameters: thông số từ Launcher request, JVM system properties, file `junit-platform.properties` trên test runtime classpath và defaults. Trong Gradle, một `Test` task có thể override cho nhóm tests:

```groovy
tasks.named('test', Test) {
    systemProperty 'junit.jupiter.execution.parallel.enabled', 'true'
}
```

Cách này hữu ích khi `serialTest` cần chạy cùng source set nhưng **tắt concurrency** mà không sửa file properties toàn suite. Cần lưu ý IDE có thể dùng JUnit launcher config khác Gradle; khi debug test concurrency, hãy ghi rõ lệnh/build task đã chạy.

## 5. Điều gì có thể chạy concurrent và điều gì cần khóa?

### 5.1. Test instance lifecycle và shared state

Với JUnit Jupiter mặc định `@TestInstance(PER_METHOD)`, mỗi test method dùng một instance test class riêng, nên instance fields không tự bị dùng chung giữa các methods. Nhưng **static fields, singletons, Spring beans, DB và external resources** vẫn chia sẻ.

Với `@TestInstance(PER_CLASS)`, một instance chứa nhiều test methods; nếu bật `@Execution(CONCURRENT)`, các instance fields sẽ bị truy cập đồng thời.

Ví dụ counter dùng sai:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class UnsafeCounterExample {
    int value = 0;

    @Test
    void a() { value++; }

    @Test
    void b() { value++; }
}
```

Đây là **anti-pattern minh họa**, không thuộc project runnable. `value++` gồm đọc, cộng và ghi, **không atomic**. Có thể mất update. Dùng `AtomicInteger`, immutable fixture, lock hoặc isolation phù hợp; tốt nhất tránh shared mutable state giữa tests.

### 5.2. @ResourceLock phối hợp việc dùng tài nguyên cùng JVM

JUnit cung cấp `@ResourceLock`:

```java
@Test
@ResourceLock(
    value = Resources.SYSTEM_PROPERTIES,
    mode = ResourceAccessMode.READ_WRITE)
void updatesSystemProperty() {
    // Chỉ những tests trong cùng Jupiter execution plan
    // khai báo cùng resource lock được phối hợp.
}
```

Ở đây `Resources.SYSTEM_PROPERTIES` là tên resource chuẩn do JUnit cung cấp; `ResourceAccessMode.READ_WRITE` loại trừ những tests khác khai báo lock xung đột. `READ` cho phép nhiều readers chạy đồng thời, nhưng không cho writer cùng resource chạy song song.

**Khóa được áp dụng cả lifecycle callbacks** liên quan `@BeforeEach`/`@AfterEach` của test method. Nhưng đây chỉ là **JVM/engine-level coordination**, không phải file lock/DB lock xuyên JVMs.

Nếu Gradle `maxParallelForks=4`, bốn JVM độc lập **không phối hợp** `@ResourceLock("shared-db")` với nhau. Muốn độc quyền một PostgreSQL schema dùng chung, hãy tách test task/fork, dùng separate schemas/databases hoặc một external coordination mechanism có thật.

### 5.3. @Isolated có tác dụng đến đâu?

`@Isolated` trên một Jupiter test class yêu cầu nó được chạy tách khỏi các tests khác trong cùng **JUnit execution plan**. Nhưng:
- Không cấm Gradle tạo một forked JVM khác.
- Không khóa tasks của module khác khi `--parallel` đang bật.
- Không cấm một quy trình CI khác dùng cùng DB/schema.
- Không thay thế resource cleanup và transaction isolation.

Vì vậy `@Isolated` là công cụ hữu ích **ở JUnit layer**, còn một serial `Test` task có `maxParallelForks=1` và JUnit parallel disabled là lớp cô lập **ở Gradle task layer**.

### 5.4. @Execution(SAME_THREAD) chỉ giải quyết một phần

Một test class có:

```java
@Execution(ExecutionMode.SAME_THREAD)
class ClassWithSequentialMethods {
    // Methods của class này được schedule tuần tự
    // theo execution mode; classes khác vẫn có thể concurrent.
}
```

Đoạn này minh họa execution mode; không phải standalone Java file. Nó bảo vệ phương thức của **chính class** khỏi chạy đồng thời theo JUnit policy, nhưng **không** ngăn class khác trong cùng JVM hoặc fork khác xóa database/file của nó.

## 6. Spring TestContext cache và chạy song song

Spring Boot tests thường dùng `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` và các hỗ trợ từ Spring TestContext Framework. Nhiều test classes có context configuration giống nhau có thể chia sẻ một **cached ApplicationContext trong cùng JVM**.

Điều này giúp startup nhanh, nhưng mang theo rủi ro khi concurrent:
- Singleton beans có mutable fields có thể bị nhiều methods/classes gọi cùng lúc.
- In-memory caches, queues, static event probes và fake clocks có thể bị test này reset trong lúc test khác dùng.
- Một test gọi `@DirtiesContext` có thể đánh dấu context cũ đóng trong khi test khác dùng nó.
- Mockito overrides (`@MockitoBean`, `@MockitoSpyBean`) có thể có trạng thái stubbing/verification/reset không phù hợp dùng chung concurrent context.
- Shared embedded DB hoặc real DB schema có thể có rows bị delete/insert cạnh tranh.
- Cấu hình `@DynamicPropertySource`/Testcontainers có thể định hướng nhiều tests đến cùng host/port/schema.

Spring Framework **khuyến cáo tránh chạy song song** khi tests dùng `@DirtiesContext`, `@MockitoBean`/`@MockitoSpyBean`, phụ thuộc execution ordering hoặc thay đổi shared DB/files/broker. Đây là khuyến nghị dựa trên khả năng xảy ra race, không phải tuyên bố rằng mọi `@SpringBootTest` đều phải tuần tự. Với stateless singleton và data đã cô lập, parallel Spring tests hoàn toàn có thể hợp lệ.

### 6.1. Context cache nằm trong một JVM

```text
Gradle fork A: ApplicationContext cache A
  SpringContextSafeTest-1
  SpringContextSafeTest-2

Gradle fork B: ApplicationContext cache B
  AnotherSpringTest

Cache A và cache B không chia sẻ Java objects.
Database/server ngoài JVM vẫn có thể được cả hai dùng chung.
```

Nếu tăng `maxParallelForks`, số lần bootstrap các contexts tương tự có thể tăng, dẫn tới:
- CPU/memory spikes do nhiều Hibernate/JPA contexts.
- Nhiều Hikari pools cùng mở connections.
- Duplicate embedded Kafka/Redis/test servers.
- Testcontainers start/stop contention.
- Chạy **chậm hơn** dù nhiều forks vì hệ thống bị quá tải.

Không tối ưu chỉ theo CPU count; phải tính database connection limits, RAM, Docker resources và initialization cost.

### 6.2. @DirtiesContext trong concurrent suite

Một test dùng:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
```

yêu cầu Spring đóng/xóa context khi phù hợp. Nếu test khác đang dùng cùng cached context ở một thread khác, có thể gặp lỗi “ApplicationContext no longer active”. Spring docs khuyến nghị **loại các tests đó khỏi nhóm chạy song song**, hoặc thay state reset bằng cơ chế cô lập hẹp hơn.

`@DirtiesContext` không sửa lỗi shared external database hay filesystem; nó chỉ tác động lifecycle Spring context.

### 6.3. @MockitoBean và mock reset

Trong Boot 3.5 / Spring Framework 6.2, có `@MockitoBean`/`@MockitoSpyBean` cho test overrides. Nếu một cached context chứa mock và hai tests cùng stubbing/verify/reset mock đó, race condition có thể tạo false positives/false negatives. Đặt nhóm này vào serial task hoặc thiết kế test-specific context/fixtures phù hợp.

Không giả định `@MockitoBean` là một thread-local mock cho từng JUnit method. Nó là một bean override **trong ApplicationContext**.

### 6.4. @Transactional trong test không phải global isolation

Khi một Spring test method được đánh dấu `@Transactional`, TestContext mở **test-managed transaction** cho thread đang chạy và mặc định rollback. Hai tests concurrent có thể có hai transactions khác nhau, nhưng:
- Cả hai vẫn có thể dùng **cùng database/schema**.
- Unique constraints có thể xung đột nếu test rows dùng cùng business ID.
- `TRUNCATE`, DDL hoặc manual cleanup ngoài transaction có thể phá dữ liệu test khác.
- Thread phụ do `@Async` hoặc HTTP server thật **không tự tham gia** test thread transaction.
- `assertTimeoutPreemptively` có thể chạy đoạn test ở thread khác, bỏ transaction boundary và làm dữ liệu được commit ngoài dự định.

Đừng coi `@Transactional` là giấy phép chạy mọi DB test song song. Hãy dùng IDs riêng, schema/database riêng hoặc serial lane cho các tests thay đổi state toàn cục.

## 7. Chiến lược khuyến nghị trước khi bật parallel

Một quy trình nâng cấp có kiểm soát:

1. **Đo baseline tuần tự**: thời gian `test`, số test methods thực chạy, RAM/CPU peak và flakiness hiện có.
2. **Phân loại tests**: pure unit tests; Spring slice tests; full-context tests; shared external resources.
3. **Bật song song ở một tầng trước**: thường chạy classes concurrent nhưng methods cùng class sequential, hoặc Gradle forks 2 trong test độc lập.
4. **Cô lập tài nguyên dùng chung**: `@TempDir`, DB schema riêng, queue/topic prefix riêng, random port, test data unique.
5. **Tách serial lane**: `@DirtiesContext`/Mockito overrides, migrations/DDL, globally shared fixtures, ordered tests.
6. **Dùng @ResourceLock khi có ý nghĩa trong một JVM**; đừng coi nó là distributed lock.
7. **Kiểm chứng thực tế**: logs có worker ID/PID/thread name, Gradle/JUnit reports, repeated CI runs, CPU/RAM.
8. **Tăng concurrency dần**: 1→2 forks, 1→2 JUnit threads, đo hiệu quả/cost.
9. **Dừng tối ưu khi contention tăng**: nhiều forks hơn có thể làm DB pool, Testcontainers hoặc filesystem chậm hơn.
10. **Giữ khả năng debug tuần tự**: một task/lệnh có thể tắt parallel nhanh khi điều tra lỗi.

**Điểm quan trọng:** Không phải mục tiêu cuối cùng là bật concurrency tối đa. Mục tiêu là **giảm wall-clock time mà vẫn tin được kết quả và giữ test isolation**.

## 8. Dự án mẫu Java 17+ / Spring Boot 3.5 / Gradle

Dự án dưới đây chủ đích phân biệt:
- Hai JVM forks của Gradle `test`.
- JUnit classes concurrent, methods mặc định same-thread; vài classes opt-in concurrent methods.
- Shared system properties được khóa bằng `@ResourceLock`.
- `@TestInstance(PER_CLASS)` dùng `AtomicInteger` an toàn.
- `@TempDir` tạo file per method thay vì một path dùng chung.
- `@SpringBootTest` với singleton stateless được phép concurrent.
- Một test dùng `@DirtiesContext` nằm ở Gradle task `serialTest` riêng.
- `org.gradle.test.worker`/PID để quan sát process isolation.

Cấu trúc:

```text
build.gradle
src/main/java/com/example/paralleldemo/
    ParallelDemoApplication.java
    MoneyCalculator.java
src/test/resources/
    junit-platform.properties
src/test/java/com/example/paralleldemo/
    ConcurrentMoneyTest.java
    SpringContextSafeTest.java
    ProtectedSystemPropertyTest.java
    PerClassSafeStateTest.java
    UniqueTempDirectoryTest.java
    GradleWorkerInfoTest.java
    IsolatedRuntimeTest.java
    SerialSpringContextTest.java
```

### 8.1. build.gradle: hai Test tasks với policy khác nhau

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    // Không chạy những tests đã đánh dấu serial trong lane này.
    useJUnitPlatform {
        excludeTags 'serial'
    }

    // Tối đa 2 forked test JVMs (chịu --max-workers).
    maxParallelForks = 2

    // Không recycle test JVM sau mỗi test class.
    forkEvery = 0

    // RAM budget áp dụng cho mỗi forked test JVM.
    maxHeapSize = '512m'

    testLogging {
        events 'failed'
    }
}

tasks.register('serialTest', Test) {
    description = 'Run tests with global/shared Spring state sequentially'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'serial'
    }

    // Mỗi lần chỉ một test JVM cho task serialTest.
    maxParallelForks = 1

    // Ghi đè junit-platform.properties trong JVM này.
    systemProperty(
        'junit.jupiter.execution.parallel.enabled', 'false')

    // Nếu check kéo cả test và serialTest, chạy serial sau test.
    shouldRunAfter tasks.named('test')

    testLogging {
        events 'failed'
    }
}

tasks.named('check') {
    dependsOn tasks.named('serialTest')
}
```

**Đọc kỹ:**
- `test` dùng tối đa 2 forks và loại test có `@Tag("serial")`.
- `serialTest` dùng chính output/classpath test source set, nhưng chỉ chọn tag `serial` và đặt `maxParallelForks=1`.
- `serialTest` **tắt Jupiter parallel trong JVM bằng system property**, không chỉ giảm forks.
- `check` chạy cả lane mặc định và `serialTest` theo dependency setup.
- `shouldRunAfter` là **ordering hint**, không phải distributed lock giữa các build hoặc các dự án khác.
- `maxHeapSize='512m'` áp dụng **cho từng JVM fork**, không phải tổng memory của mọi forks. Con số chỉ là demo, không phải sizing chuẩn cho mọi Spring app.

**Lưu ý với multi-project builds:** Nếu nhiều modules có test tasks và Gradle chạy `--parallel`, một `serialTest` ở module này không tự chặn `test` của module khác. Nếu các modules dùng một DB chung, tách environment/schemas hoặc kiểm soát task ordering/global CI concurrency theo đúng business need.

### 8.2. junit-platform.properties: JUnit parallelism trong từng fork

Tệp `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
junit.jupiter.execution.parallel.config.fixed.max-pool-size=2
```

Cấu hình này có nghĩa:
- Top-level test **classes** có thể concurrent.
- Các **methods trong cùng class** mặc định same-thread.
- Class muốn concurrent methods có thể thêm `@Execution(CONCURRENT)`.
- Desired JUnit parallelism trong mỗi JVM là 2; không liên quan tới `maxParallelForks=2`.
- `serialTest` ghi đè enabled thành false, vì vậy không dùng song song JUnit trong serial JVM.

Không đưa file này vào `src/main/resources`; nó thuộc test classpath. Khi chạy từ IDE với Launcher config khác, kiểm tra IDE có đang đọc đúng test resource không.

### 8.3. Spring Boot application

Tệp `src/main/java/com/example/paralleldemo/ParallelDemoApplication.java`:

```java
package com.example.paralleldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ParallelDemoApplication.class, args);
    }
}
```

Demo không có `starter-web` hay `starter-data-jpa`, vì vậy bootstrap Spring context nhẹ và không mở HTTP server hoặc database.

### 8.4. Stateless service: hợp lệ cho parallel tests

Tệp `src/main/java/com/example/paralleldemo/MoneyCalculator.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class MoneyCalculator {

    public BigDecimal afterDiscount(
            BigDecimal price,
            int percent) {

        Objects.requireNonNull(price, "price");

        if (price.signum() < 0) {
            throw new IllegalArgumentException(
                    "price must not be negative");
        }

        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100");
        }

        BigDecimal multiplier =
                BigDecimal.valueOf(100 - percent);

        return price.multiply(multiplier)
                .divide(
                    BigDecimal.valueOf(100),
                    2,
                    RoundingMode.HALF_UP);
    }
}
```

`MoneyCalculator` không có mutable instance field, không ghi DB/file và không dùng global mutable state. Các calls có inputs riêng nên có thể được thực thi đồng thời trên cùng Spring singleton một cách an toàn.

**Không biến test này thành benchmark:** BigDecimal tính toán rất nhanh, nên sự khác biệt thời gian do forks/threads có thể nhỏ hơn chi phí khởi động JVM. Mục đích là minh họa isolation và config, không đo performance.

## 9. JUnit classes thực tế

### 9.1. ConcurrentMoneyTest: opt-in concurrent methods không chia sẻ fixture

Tệp `src/test/java/com/example/paralleldemo/ConcurrentMoneyTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class ConcurrentMoneyTest {

    @Test
    void tenPercentDiscount() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThat(calculator.afterDiscount(
                new BigDecimal("100.00"), 10))
            .isEqualByComparingTo("90.00");
    }

    @Test
    void twentyFivePercentDiscount() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThat(calculator.afterDiscount(
                new BigDecimal("99.99"), 25))
            .isEqualByComparingTo("74.99");
    }

    @Test
    void rejectsInvalidPercent() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThrows(IllegalArgumentException.class,
            () -> calculator.afterDiscount(
                new BigDecimal("100.00"), 101));
    }
}
```

Có **3 tests**, mỗi method tạo calculator riêng và không truy cập shared state. `@Execution(CONCURRENT)` cho phép Jupiter schedule methods concurrent; nhưng không buộc cả ba chắc chắn chạy đồng thời trên một CI run — lịch thực tế còn tùy worker pool và engine.

### 9.2. SpringContextSafeTest: context dùng chung nhưng bean stateless

Tệp `src/test/java/com/example/paralleldemo/SpringContextSafeTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Execution(ExecutionMode.CONCURRENT)
class SpringContextSafeTest {

    @Autowired
    MoneyCalculator calculator;

    @Test
    void zeroDiscountPreservesAmount() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("19.50"), 0))
            .isEqualByComparingTo("19.50");
    }

    @Test
    void fullDiscountReturnsZero() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("19.50"), 100))
            .isEqualByComparingTo("0.00");
    }
}
```

Có **2 tests**. Trong **một JVM fork**, hai methods có thể chia sẻ cùng `ApplicationContext` và bean singleton. Vì service không lưu state, không cần `@DirtiesContext`. Trong **fork khác**, Gradle sẽ bootstrap context độc lập; một cached context không tự xuyên qua processes.

### 9.3. ProtectedSystemPropertyTest: @ResourceLock giải quyết shared JVM state

Tệp `src/test/java/com/example/paralleldemo/ProtectedSystemPropertyTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Execution(ExecutionMode.CONCURRENT)
class ProtectedSystemPropertyTest {

    private static final String KEY =
            "tutorial.parallel.mode";

    private static void setAndRestore(String value) {
        String previous = System.getProperty(KEY);

        try {
            System.setProperty(KEY, value);
            assertEquals(value, System.getProperty(KEY));
        } finally {
            if (previous == null) {
                System.clearProperty(KEY);
            } else {
                System.setProperty(KEY, previous);
            }
        }
    }

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void firstChangeDoesNotOverlapLockedSecondChange() {
        setAndRestore("alpha");
    }

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void secondChangeDoesNotOverlapLockedFirstChange() {
        setAndRestore("beta");
    }
}
```

Có **2 tests**. Cả hai methods có cùng `READ_WRITE` lock trên `SYSTEM_PROPERTIES`, nên Jupiter không chạy chúng đồng thời trong **cùng engine execution plan**. Chúng cũng restore property trong `finally`, kể cả khi assertion fail.

**Không nên hiểu quá mức:** Hai tests có thể không chạy đồng thời vì scheduler, nên “pass” không chứng minh đã xảy ra một cuộc tranh chấp thực. Contract chính đến từ `@ResourceLock` của JUnit. Nếu có code ngoài JUnit hoặc một JVM Gradle fork khác ghi một external resource có cùng tên, lock này **không bảo vệ** resource đó.

### 9.4. PerClassSafeStateTest: PER_CLASS + concurrent cần state an toàn

Tệp `src/test/java/com/example/paralleldemo/PerClassSafeStateTest.java`:

```java
package com.example.paralleldemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class PerClassSafeStateTest {

    private final AtomicInteger calls = new AtomicInteger();

    @Test
    void firstMethodIncrementsAtomically() {
        assertTrue(calls.incrementAndGet() >= 1);
    }

    @Test
    void secondMethodIncrementsAtomically() {
        assertTrue(calls.incrementAndGet() >= 1);
    }

    @AfterAll
    void allConcurrentMethodsCompleted() {
        assertEquals(2, calls.get());
    }
}
```

Có **2 tests**. `PER_CLASS` dùng **một instance test class**; `@Execution(CONCURRENT)` cho phép methods chạy đồng thời, nên `AtomicInteger` đúng hơn `int`. `@AfterAll` không static được cho phép bởi `PER_CLASS`.

Không dùng `calls.get()==1` trong từng test vì thứ tự/lịch của hai methods không được bảo đảm; thay vào đó assert mỗi method tăng counter, rồi `@AfterAll` xác nhận tổng bằng 2.

### 9.5. UniqueTempDirectoryTest: dùng @TempDir thay vì file cố định

Tệp `src/test/java/com/example/paralleldemo/UniqueTempDirectoryTest.java`:

```java
package com.example.paralleldemo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Execution(ExecutionMode.CONCURRENT)
class UniqueTempDirectoryTest {

    @Test
    void firstFileIsInsideItsOwnTemporaryRoot(
            @TempDir Path directory) throws IOException {

        Path file = directory.resolve("result.txt");
        Files.writeString(file, "first");

        assertEquals("first", Files.readString(file));
    }

    @Test
    void secondFileIsInsideItsOwnTemporaryRoot(
            @TempDir Path directory) throws IOException {

        Path file = directory.resolve("result.txt");
        Files.writeString(file, "second");

        assertEquals("second", Files.readString(file));
    }
}
```

Có **2 tests**. Cả hai có tên `result.txt` nhưng mỗi method nhận một `@TempDir` root riêng. JUnit quản lý cleanup theo lifecycle và temp directory scope. Đây là cách an toàn hơn:

```java
Files.writeString(Path.of("build/result.txt"), "result");
```

Dòng cuối là **anti-pattern minh họa** nếu nhiều tests cùng dùng đường dẫn đó: nó có thể đụng độ không chỉ giữa threads mà cả hai JVM forks vì working directory của Gradle test task thường cùng project.

### 9.6. GradleWorkerInfoTest: nhận diện processes mà không giả định số workers

Tệp `src/test/java/com/example/paralleldemo/GradleWorkerInfoTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;

class GradleWorkerInfoTest {

    @Test
    void reportsProcessAndThreadIdentity() {
        String worker = System.getProperty(
                "org.gradle.test.worker", "IDE-or-non-Gradle");

        long pid = ProcessHandle.current().pid();
        String thread = Thread.currentThread().getName();

        assertFalse(worker.isBlank());
        assertFalse(thread.isBlank());

        System.out.printf(
            "worker=%s pid=%d thread=%s%n",
            worker, pid, thread);
    }
}
```

Có **1 test**. Đây là diagnostic logging, không phải cách ép số worker. Khi chạy `./gradlew test --info`, bạn có thể thấy Gradle khởi động các test processes; `org.gradle.test.worker` phân biệt process theo Gradle. `Thread.currentThread().getName()` phân biệt thread trong process; cùng một worker ID có thể in ra nhiều threads.

**Không viết expected stdout cố định**: PID, test worker ID, thread names và thứ tự test output thay đổi theo CI/IDE.

### 9.7. IsolatedRuntimeTest: @Isolated chỉ ở Jupiter layer

Tệp `src/test/java/com/example/paralleldemo/IsolatedRuntimeTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Isolated;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Isolated
class IsolatedRuntimeTest {

    @Test
    void javaRuntimePropertyIsVisible() {
        assertNotNull(System.getProperty("java.version"));
    }
}
```

Có **1 test**. `@Isolated` minh họa policy rằng class này không chạy xen kẽ với classes khác **trong cùng Jupiter execution plan**. Nhưng do `maxParallelForks=2`, một Gradle fork khác vẫn có thể đang chạy tests ở cùng thời điểm. Nếu class cần độc quyền trên database/port ngoài JVM, chuyển vào serial task hoặc dùng isolation khác.

### 9.8. SerialSpringContextTest: tách khỏi lane parallel

Tệp `src/test/java/com/example/paralleldemo/SerialSpringContextTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("serial")
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SerialSpringContextTest {

    @Autowired
    MoneyCalculator calculator;

    @Test
    void testThatMarksContextDirtyRunsInSerialLane() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("10.00"), 20))
            .isEqualByComparingTo("8.00");
    }
}
```

Có **1 test**. Class được đánh dấu `@Tag("serial")`, nên:
- Tác vụ `test` mặc định **exclude** nó.
- Tác vụ `serialTest` **include** nó.
- `serialTest` có `maxParallelForks=1` và Jupiter parallel disabled.
- `@DirtiesContext` không đe dọa một cached context đang được dùng concurrent **trong cùng serial JVM**.

**Giới hạn cần hiểu:** Nếu chạy Gradle với nhiều modules hoặc một CI job khác đồng thời, serial lane của module này chưa có quyền khóa tài nguyên global. `@DirtiesContext` cũng không dọn external DB/schema, Kafka topic hay filesystem.

### 9.9. Đếm chính xác số test mẫu

| Class | Số @Test | Lane |
|---|---:|---|
| `ConcurrentMoneyTest` | 3 | `test` |
| `SpringContextSafeTest` | 2 | `test` |
| `ProtectedSystemPropertyTest` | 2 | `test` |
| `PerClassSafeStateTest` | 2 | `test` |
| `UniqueTempDirectoryTest` | 2 | `test` |
| `GradleWorkerInfoTest` | 1 | `test` |
| `IsolatedRuntimeTest` | 1 | `test` |
| `SerialSpringContextTest` | 1 | `serialTest` |
| **Tổng** | **14** | **13 + 1** |

Đây là số **test methods được viết trong mẫu**, không phải số tests đã được chạy trong một JVM. Kết quả thực chỉ được kết luận sau khi Gradle/JUnit discovery và reports xác nhận đúng count/pass/fail/skip.

## 10. Phân biệt “đồng thời thực sự” với “cho phép concurrent”

Có `@Execution(CONCURRENT)` và `fixed.parallelism=2` là cấu hình **cho phép** song song, không phải một assertion rằng hai methods chắc chắn chồng lấn thời gian trong lần chạy cụ thể.

### 10.1. Tránh test dựa vào Thread.sleep để chứng minh concurrency

Anti-pattern:

```java
long started = System.nanoTime();
Thread.sleep(100);
assertTrue(System.nanoTime() - started < 150_000_000L);
```

Đây là đoạn minh họa không phải test độc lập. Nó vừa không chứng minh có hai test methods concurrent, vừa phụ thuộc scheduler và CI load. Không nên lấy thời gian chạy một method làm chỉ báo chính xác của JUnit parallelism.

**Nếu mục tiêu là chứng minh hai methods có thể overlap trong một test class chẩn đoán**, có thể viết một probe chuyên biệt dùng `CountDownLatch`/barrier với **deadline** và chạy **riêng class đó**, khi đã cấp pool parallelism tối thiểu 2. Tuy nhiên:
- Đừng đặt một barrier bắt buộc giữa hai tests trong suite lớn mà CI có thể chạy với chỉ một thread.
- Đừng dùng một static barrier qua nhiều forked JVMs — static fields không chia sẻ giữa JVMs.
- Nếu một test fail trước khi báo latch, test còn lại phải có timeout hữu hạn.
- Chứng minh overlap không tự bảo đảm database/file isolation.

Trong phần runnable, các tests được thiết kế **không cần hai methods chạy cùng lúc để pass**. Đó là nguyên tắc reliability: test đúng bất kể hợp lệ scheduler chọn interleaving nào.

### 10.2. Cách xác nhận config thật đang dùng

- Đọc `junit-platform.properties` trên test runtime classpath.
- Xác nhận `useJUnitPlatform()` trong Gradle.
- Kiểm tra `@Execution`, `@ResourceLock`, `@Isolated` trên test classes.
- In/process diagnostic `org.gradle.test.worker`, PID và thread name khi cần.
- Đọc `--info`/Build Scan để thấy Gradle worker processes.
- Kiểm tra `maxParallelForks`, `--max-workers`, `--parallel`, `forkEvery` được set ở **task nào**.
- Dùng JUnit/Test execution reports và profiling thay vì suy ra từ thứ tự `System.out` (test stdout có thể được Gradle capture/reorder).

## 11. Các ví dụ failure do tài nguyên chia sẻ

### 11.1. Database cleanup race

Hai tests dùng cùng một H2/PostgreSQL schema:

```text
Test A: INSERT invoice id=A
Test B: DELETE FROM invoice
Test A: assert invoice A exists  --> FAIL
```

Một `@Transactional` trên test A không bảo vệ trước `DELETE`/DDL do test B thực hiện ngoài transaction và khác process, tùy isolation/DB semantics. Cách xử lý:
- Dùng **business IDs duy nhất theo test**.
- Dùng schema/database riêng cho từng test process khi tests không thể đồng tồn tại.
- Nếu dùng Testcontainers, kiểm soát container lifetime, ports và schema ownership.
- Không dùng truncate-all trước mỗi test khi chia sẻ DB.
- Cân nhắc serial lane cho migration/DDL/full reset.
- Đảm bảo cleanup không xóa dữ liệu của test khác.

### 11.2. Filesystem dùng path cố định

```java
Path report = Path.of("build/reports/current.json");
Files.writeString(report, json);
```

Đây là fragment minh họa: biến `json` cần tồn tại. Nếu hai forks viết cùng path, `@ResourceLock` trong từng JVM **không phối hợp** với nhau. Sửa bằng `@TempDir` hoặc đặt path chứa worker ID/test ID, và cleanup file scope tương ứng.

### 11.3. Fixed port và mock HTTP server

```text
Fork A: starts server port 8089 -> success
Fork B: starts server port 8089 -> BindException: address in use
```

Sử dụng `@SpringBootTest(webEnvironment=RANDOM_PORT)` khi cần HTTP server thật, hoặc cho embedded server/mock server bind port 0 rồi lấy assigned port. Không hard-code một port cho các forks; `@LocalServerPort`/DynamicPropertySource phải đưa đúng port được cấp vào client.

Nếu service ngoài test buộc cố định port, tách serial lane hoặc cấp unique port qua CI lease/worker configuration.

### 11.4. Testcontainers, Docker và JVM lifecycle

Một test container có static singleton trong **mỗi JVM** không phải singleton cho cả Gradle build. Với `maxParallelForks=4`, có thể bốn containers cùng khởi động:
- CPU/RAM/Docker pull tăng mạnh.
- DB pool/threads trên máy CI có thể quá tải.
- Fixed container name/network alias có thể xung đột.
- Container reuse có thể khiến state còn sót từ run trước.
- `@DynamicPropertySource` nhận endpoint từ container instance thuộc fork tương ứng; không hard-code endpoint cũ.

Khi dùng container dùng chung giữa tests trong một JVM, chỉ được parallel nếu state thực sự được cô lập. Khi muốn một container duy nhất cho mọi forks, cần external lease/schema partition — không giả định static field vượt được process boundary.

### 11.5. System properties, default Locale, Clock và TimeZone

System properties, global timezone hoặc JVM default locale là **shared mutable global state trong một JVM**. JUnit có sẵn resource keys như `Resources.SYSTEM_PROPERTIES`, `Resources.TIME_ZONE`, `Resources.LOCALE`. Dùng `@ResourceLock` phù hợp và restore state sau test.

Trong nhiều JVM forks, mỗi JVM có system properties riêng, nhưng external configuration files hoặc environment service vẫn dùng chung. Tránh set `TimeZone.setDefault(...)` trong một test concurrent chưa khóa.

### 11.6. Tests gọi HTTP và transactional rollback

Với `@SpringBootTest(RANDOM_PORT)`, HTTP server xử lý trên thread khác JUnit test thread. Transaction test-managed không tự bao phủ service transaction ở request thread, vì vậy writes có thể commit dù test `@Transactional` mặc định rollback. Trong suite parallel, điều đó dễ gây data bleed giữa tests nếu không cleanup thích hợp.

## 12. Tối ưu workers với CPU, RAM, DB pool và CI

Một cách ước lượng tài nguyên cho một project:

- `F` = số forked test JVMs thực tế của một Gradle `Test` task (không vượt `maxParallelForks` và Gradle scheduling budget).
- `P` = Jupiter desired parallelism trong từng JVM.
- `H` = heap max của từng test JVM.
- `C` = DB connections/pool capacity mà mỗi Spring context có thể giữ.

**Ước lượng sơ bộ:**
- JUnit nodes có thể chạy đồng thời tới mức **phụ thuộc F × P** nếu có đủ runnable tests, nhưng `P` không phải hard cap trong mọi tình huống, và còn nhiều tasks/forks khác.
- Heap allocations riêng của test JVMs có thể gần **F × H**, cộng metaspace, threads, native memory, Gradle daemon và Docker containers.
- Nếu mỗi fork khởi động một Spring application context có Hikari pool size tối đa `C`, tổng connection demand tiềm năng có thể gần **F × C** hoặc cao hơn nếu có nhiều contexts/clients.

Ví dụ cấu hình `maxParallelForks=2`, `maxHeapSize='512m'`, Jupiter fixed parallelism 2 chỉ là **tham số minh họa**, không bảo đảm RAM tổng bằng 1 GiB hay có đúng bốn test methods concurrent. Xem thực tế `-XX:ActiveProcessorCount`, container CPU quotas, memory limit, Spring context count và external DB connection limits.

### 12.1. Vì sao tăng forks đôi khi chậm hơn?

- JVM/Spring context startup bị lặp.
- Classpath scanning và Hibernate bootstrap tranh CPU.
- Mỗi fork tải cùng test fixtures.
- Docker/Testcontainers startup trùng nhau.
- PostgreSQL/Redis bị tranh lock/connection.
- GC tăng khi RAM thiếu.
- Disk I/O bottleneck khi ghi logs/test reports.

**Chiến lược:** chạy baseline 1 fork, 1 JUnit worker; tăng từng biến một, đo **median và p95** của thời gian suite và failures qua nhiều runs. Đừng chọn “số CPU cores” rồi nhân cả forks và threads bằng con số đó mà chưa kiểm tra resource costs.

### 12.2. Cấu hình CI theo môi trường

Local laptop mạnh có thể dùng 2 forks × 2 JUnit threads; CI runner nhỏ có thể cần 1 fork × 2 threads hoặc thậm chí tuần tự. Dùng Gradle properties để override:

```groovy
tasks.named('test', Test) {
    maxParallelForks = providers
            .gradleProperty('testForks')
            .map { it.toInteger() }
            .getOrElse(2)
}
```

Đây là **fragment thay thế** dòng `maxParallelForks=2` trong `build.gradle` ở trên; không thêm cả hai phiên bản cùng lúc. Chạy:

```bash
./gradlew test -PtestForks=1 --max-workers=2
```

Nếu muốn override JUnit parallelism mà không đổi resource file, có thể truyền JVM system properties vào Test task theo Gradle project property:

```groovy
tasks.named('test', Test) {
    systemProperty(
        'junit.jupiter.execution.parallel.config.fixed.parallelism',
        providers.gradleProperty('junitThreads')
            .getOrElse('2'))
}
```

Đây cũng là **fragment tùy chọn**, không có sẵn trong main build. Kiểm tra `@ResourceLock`/`@Isolated` vẫn áp dụng khi threads tăng; và không giả định Gradle CLI `-D...` luôn được chuyển vào test JVM nếu `Test` task chưa forward thuộc tính.

## 13. Cách chạy, kiểm tra số test methods và reports

Với project có Gradle wrapper hợp lệ:

### 13.1. Chạy lane parallel

Linux/macOS:

```bash
./gradlew test --max-workers=4
```

Windows PowerShell:

```powershell
.\gradlew.bat test --max-workers=4
```

Dự kiến `test` chọn **13 test methods** từ các classes không có tag serial. Vì đây là code mẫu chưa build, phải kiểm tra report để biết count thực tế. `maxParallelForks=2` là tối đa JVM test workers; số JVM thực có thể ít hơn nếu workload/worker budget nhỏ.

### 13.2. Chạy lane serial

```bash
./gradlew serialTest --max-workers=2
```

Windows:

```powershell
.\gradlew.bat serialTest --max-workers=2
```

`serialTest` chỉ chọn `@Tag("serial")`, tức **1 test method** trong project này. Nó được chạy với **một JVM và Jupiter parallel disabled**. Nếu có nhiều serial test classes, task vẫn xử lý tuần tự trong JVM theo execution mode (trừ khi một test tự tạo background threads, điều mà Jupiter không thể cấm).

### 13.3. Chạy cả hai lanes

```bash
./gradlew clean check --max-workers=4
```

`check` phụ thuộc `test` (do Java plugin) và `serialTest` (do build script), với `serialTest.shouldRunAfter(test)` để tránh trộn thời điểm của hai lanes trong project này. Tuy nhiên thứ tự giữa các subprojects khác vẫn chịu task graph/parallel scheduling.

Nếu debug tính tuần tự:

```bash
./gradlew clean check --max-workers=1 --no-parallel
```

Với lệnh trên, Gradle chỉ cấp một worker slot nên Gradle test forks không chạy nhiều JVM cùng lúc; **nhưng** `test` task vẫn có JUnit Jupiter parallel enabled và `fixed.parallelism=2` bên trong một JVM! Nếu cần tắt **cả Jupiter parallel**, dùng `serialTest` hoặc thêm override `systemProperty('junit.jupiter.execution.parallel.enabled','false')` trong một test task dành cho debug.

### 13.4. Chạy một class để chẩn đoán

```bash
./gradlew test --tests "com.example.paralleldemo.ConcurrentMoneyTest" --info
```

Hoặc:

```bash
./gradlew test --tests "com.example.paralleldemo.GradleWorkerInfoTest" --info
```

Chạy **một class** không thể dùng làm bằng chứng `maxParallelForks=2` đã tạo đúng hai JVMs: Gradle có thể cần chỉ một fork cho một class. Để quan sát nhiều worker IDs, cần đủ nhiều test classes và không bị tổng worker budget giới hạn.

### 13.5. Đọc đúng reports

- Gradle HTML report: `build/reports/tests/test/index.html`.
- Gradle XML results: `build/test-results/test/`.
- Serial lane report: `build/reports/tests/serialTest/index.html`.
- Serial lane XML: `build/test-results/serialTest/`.

Chỉ coi suite đã được thực thi khi reports xác nhận **test count, failures, skips** và task thực chạy. `BUILD SUCCESSFUL` nhưng `NO-SOURCE`, `UP-TO-DATE` không đủ chứng minh một test mới được chạy trong lần build hiện tại. Nếu build cache là chủ đích, phải hiểu đó là kết quả từ một run trước với input fingerprint phù hợp.

Không bịa một stdout “worker=1 pid=...” cố định: PID và worker IDs thay đổi.

## 14. Anti-patterns cần tránh

### 14.1. Bật --parallel rồi cho rằng JUnit methods concurrent

`--parallel` là Gradle project-level task scheduling. Jupiter cần cấu hình riêng hoặc `@Execution(CONCURRENT)`.

### 14.2. Chỉ đặt parallel.enabled=true

Nếu JUnit default execution modes vẫn `same_thread`, không có sự khác biệt như bạn mong đợi. Cần xác định rõ class/method modes và `fixed/dynamic` strategy.

### 14.3. Đặt maxParallelForks bằng availableProcessors cho mọi module

Điều này nhân JVM bootstrap, connection pools và Docker resources; tổng workers của Gradle có thể giới hạn, nhưng chi phí chạy nhiều processes vẫn lớn. Tuning theo profiling.

### 14.4. Dùng @ResourceLock("database") nhưng bật bốn Gradle forks

ResourceLock chỉ phối hợp trong JUnit engine của một JVM. Hai JVM khác nhau có hai lock managers độc lập. Với shared DB, dùng database/schema partition hoặc serial lane phù hợp.

### 14.5. Đánh dấu @Isolated rồi cho rằng toàn bộ CI build độc quyền

`@Isolated` không ngăn fork khác, module khác hoặc CI job khác. Phải cô lập tài nguyên ở tầng tương ứng.

### 14.6. Dùng forkEvery=1 để chữa data races

Thay JVM có thể ẩn static leaks nhưng không ngăn hai forks cùng chạm file/DB và làm suite rất chậm. Cần sửa root cause.

### 14.7. Shared static List/Map/Counter trong @Execution(CONCURRENT)

`ArrayList`, `HashMap` và `int++` không mặc nhiên thread-safe. Dùng immutable fixtures, `ConcurrentHashMap`, `AtomicInteger` hoặc `@ResourceLock` nếu thật sự phải chia sẻ.

### 14.8. @DirtiesContext / @MockitoBean trong parallel context tests

Spring TestContext docs khuyến nghị không chạy song song các tests dùng `@DirtiesContext` hoặc mock bean overrides khi có nguy cơ context cache/mock state race. Dùng serial lane hoặc thiết kế fixture riêng.

### 14.9. Test data có mã cố định

Nếu hai tests cùng `INSERT users(email='alice@example.test')`, unique constraint có thể khiến một test fail; nếu một test xóa bảng của test khác, failures phụ thuộc interleaving. Dùng per-test IDs hoặc schema isolation.

### 14.10. Chỉ dùng Thread.sleep để “đợi test kia”

`Thread.sleep(100)` làm test flaky và không tạo synchronization contract. Nếu cần test concurrency thực, dùng thread-safe probes, `CountDownLatch`, `CyclicBarrier` và timeouts có kiểm soát, không dựa vào tốc độ CPU.

## 15. Cách tìm nguyên nhân khi suite chỉ fail ở CI

| Dấu hiệu | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Pass khi chạy riêng, fail khi chạy toàn suite | Shared static state/context/file/DB | Chạy một JVM và so với nhiều forks, kiểm tra resource owner |
| Chỉ fail khi `maxParallelForks>1` | Cross-process collision | Xem DB schema, file path, port, container name |
| Chỉ fail khi Jupiter concurrent | Same-JVM race | Check static fields, singleton beans, shared mocks |
| `ApplicationContext no longer active` | @DirtiesContext/cache eviction concurrent | Tách serial lane, xem ContextCache logs |
| Mockito verification count thất thường | Shared mock/reset/stubbing race | Không concurrent cùng mock bean |
| Unique constraint violation ở CI | Tests cùng business ID/schema | Unique test fixtures/schema partition |
| FileNotFound/JSON bị ghi đè | Hai tests cùng filename | @TempDir/worker ID-based path |
| Address already in use | Mock server dùng fixed port | Port 0/RANDOM_PORT |
| JVMs tăng nhưng suite chậm hơn | Spring startup/GC/DB contention | Profile, giảm forks |
| Test container startup conflict | Nhiều forks khởi động container | Quản lý lifecycle, unique resources |
| @Transactional rollback không dọn data | HTTP/async thread khác transaction | Cleanup explicit, test DB isolation |
| Test classes không concurrent như mong muốn | mode.classes.default=same_thread | Xem Jupiter properties và @Execution |
| Methods trong class vẫn sequential | mode.default=same_thread hoặc PER_CLASS/order | Annotation class/test plan |
| @ResourceLock khiến test tuần tự | READ_WRITE lock xung đột | Dùng READ cho chỉ đọc, giảm critical section |
| Một Gradle worker ID xuất hiện nhiều lần | Nhiều test classes cùng một fork | Bình thường, không phải bug |
| Cùng PID nhưng thread names khác | Jupiter threads trong cùng JVM | Bình thường khi concurrency bật |
| Hai PID nhưng cùng file bị xóa | Locks chỉ bảo vệ trong từng JVM | Filesystem namespace/external coordination |
| `--max-workers=1` vẫn thấy hai JUnit threads | Worker budget khác JUnit thread count | Tắt Jupiter parallel riêng |
| Reports thiếu serial tests | test task exclude tag serial | Chạy check/serialTest riêng |
| JUnit tests skipped/NO-SOURCE | Test discovery/filtering sai | Kiểm tra task filters, classpath, XML reports |
| Hikari pool exhausted | Nhiều contexts/forks cùng mở connections | Giảm forks, dùng pool riêng/giảm max |
| Timeouts tăng khi parallel | CPU throttling, DB contention, GC | Điều chỉnh worker budget và timeouts theo load |

### 15.1. Một chuỗi debug đáng tin

1. Ghi chính xác Gradle command/CI environment.
2. Xác định `--max-workers`, `--parallel`, `maxParallelForks`, `forkEvery` của Test task.
3. Xác định JUnit parallel enabled, class/method modes, fixed/dynamic pool config.
4. Tìm test nào dùng `@DirtiesContext`, `@MockitoBean`, `@TestMethodOrder`, `@Isolated`, `@ResourceLock`.
5. Xác định tài nguyên **trong JVM** và tài nguyên **ngoài JVM** được chia sẻ.
6. Thử một JVM + Jupiter sequential để có baseline.
7. Chỉ bật JUnit concurrent, quan sát lỗi; sau đó chỉ tăng Gradle forks.
8. Dùng `org.gradle.test.worker`, PID và thread IDs để khoanh vùng tầng race.
9. Tách serial lane hoặc sửa isolation; không chỉ tăng `Thread.sleep`.
10. Chạy nhiều lần trên CI trước khi nâng concurrency lần nữa.

## 16. Các quy tắc quan trọng khi chạy song song ở cấp module

Nếu repository có `:core`, `:api`, `:integration`:
- Unit tests ở `:core` thường không cần Spring context và có thể parallel cao hơn.
- Slice tests ở `:api` có thể chạy classes concurrent nếu mock/fixtures không được chia sẻ nguy hiểm.
- `:integration` dùng PostgreSQL/Kafka/Redis/Testcontainers thường bị giới hạn bởi external resource và có thể cần serial lane hoặc per-worker schema.
- `--parallel` tạo concurrency **giữa Gradle projects**, nên tổng database/container load của toàn build không chỉ là `maxParallelForks` của một module.
- `maxParallelForks` có thể khác nhau theo task: `test`, `integrationTest`, `serialTest`.
- Nếu `check` phụ thuộc các test tasks ở nhiều modules, hãy thiết kế task graph/capacity budget thay vì dựa vào annotation JUnit để cô lập toàn hệ thống.

Một cấu hình phổ biến theo **chiến lược** (không phải hằng số khuyến nghị):
- Pure unit test: nhiều classes/methods concurrent.
- SpringBootTest không có shared mutable resource: ít forks, context cache reuse.
- DB/migration/consumer/port-dependent tests: isolated schema/container hoặc serial.
- Test load/performance: task riêng, không trộn vào suite correctness.
- Test thay default timezone/system properties: `@ResourceLock` và finally restore.

## 17. Checklist QA trước khi bật parallel trong dự án thật

- [ ] Biết rõ `--parallel` thuộc Gradle project task scheduling, không phải Jupiter mode.
- [ ] Biết rõ `--max-workers` giới hạn worker budget của Gradle.
- [ ] Biết `Test.maxParallelForks` là số forked JVM test processes, không phải threads.
- [ ] Biết `forkEvery` điều khiển JVM recycle, không phải parallelism.
- [ ] Biết `junit.jupiter.execution.parallel.enabled` và execution modes cần cấu hình riêng.
- [ ] Có lựa chọn fixed/dynamic parallelism theo CPU/RAM/cost thực tế.
- [ ] Không coi desired JUnit parallelism luôn là hard upper bound threads.
- [ ] Có `useJUnitPlatform()` cho Gradle Test task.
- [ ] Không dựa vào thứ tự thực thi không được JUnit bảo đảm.
- [ ] Có test-specific fixtures, tránh shared static mutable state.
- [ ] `PER_CLASS` concurrent chỉ dùng immutable/thread-safe fields.
- [ ] `@ResourceLock` chỉ được tin trong cùng JUnit execution plan.
- [ ] `@Isolated` không bị hiểu nhầm thành lock giữa các JVMs.
- [ ] `@TempDir` hoặc namespaced paths cho file output.
- [ ] Cơ sở dữ liệu có per-test data IDs/schema hoặc serial policy phù hợp.
- [ ] Mock server/WebServer dùng dynamic ports, không hard-code chung.
- [ ] Testcontainers resources được quản lý theo fork/task lifespan.
- [ ] `@DirtiesContext` và `@MockitoBean` không gây race với cached context.
- [ ] HTTP/async threads không bị giả định tham gia @Transactional của JUnit test.
- [ ] Có serial Gradle Test task cho tests có global/shared state.
- [ ] `@Tag("serial")` được include trong serial task và exclude khỏi main task.
- [ ] `check` thực sự chạy cả các lanes cần thiết.
- [ ] Không cho rằng `--max-workers=1` tự tắt Jupiter threads.
- [ ] Có logs worker ID/PID/thread để điều tra nếu CI flake.
- [ ] Đọc Gradle/JUnit reports kiểm tra số tests executed, failures và skips.
- [ ] Đo thời gian suite, CPU, RAM, DB connections khi tăng concurrency.
- [ ] Có cách quay lại sequential config để debug nhanh.

## 18. Tài liệu chính thức

- [JUnit Jupiter — Parallel Execution (JUnit 5)](https://docs.junit.org/5.14.2/writing-tests/parallel-execution): `parallel.enabled`, class/method modes, fixed/dynamic strategy, `@Execution`, `@ResourceLock`, `@Isolated`, `PER_CLASS`.
- [JUnit Jupiter — Test Instance Lifecycle](https://docs.junit.org/5.14.2/writing-tests/test-instance-lifecycle): `PER_METHOD` vs `PER_CLASS` và lifecycle.
- [JUnit Jupiter — Tagging and Filtering](https://docs.junit.org/5.14.2/writing-tests/tagging-and-filtering): `@Tag` và include/exclude filtering.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `maxParallelForks`, `forkEvery`, test worker property, reports.
- [Gradle — Test Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): `getMaxParallelForks`, `setMaxParallelForks`, fork semantics.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--parallel`, `--max-workers`.
- [Gradle — Build Performance](https://docs.gradle.org/current/userguide/performance.html): tuning test parallelism, profiling.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): Spring TestContext guidance on `@DirtiesContext`, Mockito overrides, shared state and context cache.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): `@Transactional`, rollback và thread boundaries.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slices, `@SpringBootTest`, TestContext.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.14.2/): test reports, build tool integration.

**Kết luận:** `JUnit parallel execution` và `Gradle maxParallelForks` là **hai tầng concurrency riêng**, còn `--max-workers` và `--parallel` thuộc scheduler của Gradle. Một cách thực hành an toàn là: bắt đầu với classes concurrent nhưng methods sequential, dùng `@Execution(CONCURRENT)` cho classes thật sự thread-safe, `@ResourceLock` cho tài nguyên dùng chung trong một JUnit plan, `@TempDir`/schema riêng cho tài nguyên ngoài JVM, và một `serialTest` task cho các cases có `@DirtiesContext`, mocks hoặc global state. Đo hiệu quả bằng Gradle/JUnit reports và tài nguyên CI thực tế, không suy đoán từ worker count hoặc việc một test tình cờ chạy nhanh hơn.