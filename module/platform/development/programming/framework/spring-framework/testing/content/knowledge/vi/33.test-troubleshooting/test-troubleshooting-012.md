# Timeout do tác vụ nền, khóa dữ liệu hoặc hạ tầng chưa sẵn sàng

Một integration test Spring có thể hết thời gian chờ dù logic nghiệp vụ không sai. Request có thể đang chờ một tác vụ `@Async` chưa hoàn tất, transaction có thể đang đợi khóa do test khác giữ, connection pool có thể hết connection, hoặc container đã chạy nhưng database/broker bên trong chưa sẵn sàng nhận request. Muốn xử lý đúng, cần xác định chính xác thao tác nào đang chờ và timeout thuộc tầng nào.

Thông báo `Timeout` chỉ cho biết một giới hạn thời gian đã bị vượt qua. Nó không tự giải thích nguyên nhân. Một timeout ở JUnit có thể là hệ quả của một query bị khóa; timeout lấy connection có thể là hệ quả của transaction trước chưa được đóng; timeout khi gửi message có thể xảy ra vì broker chưa ready hoặc consumer chưa nhận message. Hãy tìm điểm chờ đầu tiên và lần theo các dependency của nó.

## Phân biệt các tầng timeout

Một luồng xử lý có thể đi qua nhiều giới hạn thời gian độc lập:

```text
JUnit test timeout
    |
    +-- chờ Future / latch / Awaitility
    |       |
    |       +-- async executor queue và worker thread
    |               |
    |               +-- lấy connection từ pool
    |                       |
    |                       +-- chờ database lock / chạy query
    |
    +-- chờ container hoặc service readiness
            |
            +-- kết nối broker / HTTP service / database
```

| Tầng | Ví dụ | Điều đang bị giới hạn |
|---|---|---|
| Test framework | JUnit `@Timeout` | Tổng thời gian test method hoặc lifecycle callback |
| Đồng bộ async | `Future#get`, `CountDownLatch#await`, Awaitility | Thời gian chờ tác vụ hoặc điều kiện hoàn tất |
| Executor | Queue capacity, worker threads, task rejection | Khả năng nhận và thực thi task nền |
| Connection pool | Hikari `connectionTimeout` | Thời gian chờ lấy connection từ pool |
| Database lock | `lock_timeout`, lock wait timeout | Thời gian chờ transaction khác nhả khóa |
| Database statement | `statement_timeout`, query timeout | Thời gian chạy một câu SQL |
| Network client | Connect/read/response timeout | Thời gian thiết lập kết nối hoặc chờ phản hồi |
| Hạ tầng test | Testcontainers startup timeout, wait strategy | Thời gian chờ dịch vụ trong container sẵn sàng |
| Messaging | Consumer poll/processing timeout | Thời gian chờ message được nhận và xử lý |

Các giới hạn này không thay thế cho nhau. Tăng JUnit timeout từ 5 lên 60 giây có thể làm test đợi lâu hơn, nhưng không giải quyết được deadlock, executor bị nghẽn hoặc container chưa ready. Nên xác định tầng timeout trước khi điều chỉnh cấu hình.

## Đặt ngân sách thời gian theo tầng

Timeout nên phản ánh thời gian tối đa hợp lý của từng thao tác. Giới hạn bên trong cần đủ nhỏ để báo lỗi gần nguyên nhân, còn timeout tổng của test cần lớn hơn tổng các bước và có thời gian dự phòng cho assertion/cleanup.

Ví dụ một test cần khởi động container, gửi tác vụ async và đọc kết quả:

| Công đoạn | Giới hạn minh họa | Ý nghĩa |
|---|---:|---|
| Container startup/readiness | 90 giây | Cho phép image khởi động và health check thành công |
| Lấy connection | 3 giây | Phát hiện pool cạn hoặc datasource không kết nối được |
| Query/lock wait | 2 giây | Phát hiện query chờ quá lâu hoặc bị khóa |
| Async completion | 5 giây | Chờ tác vụ nền hoàn tất |
| Toàn bộ test | 15 giây sau khi context sẵn sàng | Chặn test treo và cho cleanup chạy |

Đây chỉ là ví dụ; giá trị thực tế phải dựa trên SLA của test và môi trường CI. Không nên đặt các timeout bằng nhau một cách máy móc. Nếu timeout tổng nhỏ hơn timeout của một bước con, test framework có thể kết thúc trước khi bước con báo nguyên nhân cụ thể.

Đặc biệt, container startup thường xảy ra trước test method và có thể được dùng chung theo lifecycle/context. Không tính startup timeout như thể nó luôn nằm bên trong thời gian của method.

## Timeout do tác vụ nền chưa hoàn tất

Với `@Async`, `TaskExecutor`, `@Scheduled` hoặc message listener, lời gọi khởi chạy task có thể trả về trước khi công việc thực tế kết thúc. Test phải đợi một tín hiệu hoàn tất có ý nghĩa, thay vì giả định task đã xong ngay sau khi method launcher trả về.

### Dùng CompletableFuture thay vì Thread.sleep

Nếu phương thức async trả `CompletableFuture`, hãy chờ future với timeout hữu hạn:

```java
@Service
class ReportJob {

    @Async("reportExecutor")
    public CompletableFuture<Report> generate(long reportId) {
        Report report = reportService.generate(reportId);
        return CompletableFuture.completedFuture(report);
    }
}
```

Test phải lấy bean từ Spring context để lời gọi đi qua proxy `@Async`:

```java
@SpringBootTest
class ReportJobTest {

    @Autowired
    private ReportJob reportJob;

    @Test
    void completesReportWithinExpectedTime() throws Exception {
        Report report = reportJob.generate(42L)
                .get(5, TimeUnit.SECONDS);

        assertThat(report.getId()).isEqualTo(42L);
    }
}
```

`Future#get(timeout, unit)` trả kết quả khi task hoàn tất. Nếu quá thời gian, nó ném `TimeoutException`; nếu task thất bại, caller nhận `ExecutionException` và có thể đọc cause. Cách này vừa đồng bộ test với task vừa giữ được exception từ worker thread.

Không gọi trực tiếp `new ReportJob(...)` trong test nếu muốn xác nhận `@Async`. Annotation được thực thi qua Spring proxy; self-invocation hoặc gọi một object tự tạo có thể chạy đồng bộ.

### Dùng CountDownLatch khi task không trả Future

Với callback hoặc listener trả `void`, có thể dùng `CountDownLatch` để báo rằng một sự kiện đã xảy ra:

```java
@Test
void waitsUntilBackgroundHandlerFinishes() throws Exception {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    executor.execute(() -> {
        try {
            handler.process(message);
        } catch (Throwable ex) {
            failure.set(ex);
        } finally {
            completed.countDown();
        }
    });

    assertThat(completed.await(5, TimeUnit.SECONDS))
            .as("background handler should finish")
            .isTrue();
    assertThat(failure.get()).isNull();
}
```

Latch cần được giảm đếm trong `finally`, nếu không một exception trong task có thể khiến test chỉ chờ đến timeout mà không biết worker đã thất bại. Nếu cần kiểm tra kết quả, lưu kết quả vào `AtomicReference` hoặc dùng `CompletableFuture`.

### Dùng Awaitility cho trạng thái cuối cùng

Một số tác vụ không trả handle trực tiếp; chúng cập nhật database, cache hoặc trạng thái job. Có thể dùng Awaitility để chờ điều kiện cuối cùng:

```java
await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() ->
                assertThat(jobRepository.findStatus(jobId))
                        .isEqualTo(JobStatus.COMPLETED));
```

Awaitility lặp lại assertion đến khi thành công hoặc timeout. Nó phù hợp với trạng thái eventual consistency, nhưng điều kiện phải là tín hiệu hoàn tất rõ ràng. Không nên chờ một giá trị trung gian có thể xuất hiện trước khi toàn bộ tác vụ kết thúc.

Không đặt polling quá dày nếu mỗi lần kiểm tra tạo query nặng hoặc gây tải lên dịch vụ. Dùng khoảng polling hợp lý và timeout đủ để test ổn định trong môi trường CI.

### Phân biệt task đã được submit với task đã hoàn tất

Các trạng thái sau khác nhau:

1. Task đã được submit vào executor.
2. Task đã được lấy khỏi queue và bắt đầu chạy.
3. Task đã hoàn thành thành công hoặc thất bại.
4. Side effect của task đã commit và có thể quan sát từ transaction khác.

Một assertion xác nhận `executor.execute(...)` đã được gọi chỉ kiểm tra bước 1. Thread name hoặc latch ở đầu task có thể xác nhận bước 2. Future hoàn tất xác nhận bước 3. Nếu task ghi database, cần đọc lại sau commit bằng transaction mới để xác nhận bước 4.

### Executor queue hoặc thread pool bị nghẽn

Task có thể chưa bắt đầu vì executor đã dùng hết worker threads và queue đầy. Dấu hiệu thường gặp là:

- Future chưa hoàn tất, nhưng log trong thân task chưa xuất hiện.
- Active thread count đạt max pool size.
- Queue size tăng hoặc queue không còn capacity.
- Task bị từ chối với `TaskRejectedException` hoặc `RejectedExecutionException`.
- Các worker đều chờ database, HTTP call hoặc lock khác.

Khi test dùng `ThreadPoolTaskExecutor`, kiểm tra `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy và shutdown lifecycle. Không giải quyết bằng cách tăng test timeout nếu task chưa từng được chạy.

Trong test, có thể dùng executor nhỏ và có thể kiểm soát để tái hiện tình trạng queue đầy. Hãy xác nhận rejection policy và hành vi ứng dụng khi không thể nhận task. Với test thông thường, không nên tạo quá nhiều task song song vượt khả năng của executor chỉ để đợi chúng hoàn tất.

## Timeout do khóa dữ liệu hoặc transaction bị giữ

Database dùng khóa để bảo vệ dữ liệu khi nhiều transaction cùng đọc/ghi. Một transaction có thể phải đợi transaction khác commit hoặc rollback trước khi tiếp tục. Nếu transaction giữ khóa quá lâu, query hoặc request sẽ hết timeout dù database vẫn đang hoạt động.

### Pessimistic lock và lock wait

Với JPA, `LockModeType.PESSIMISTIC_WRITE` có thể yêu cầu database giữ khóa ghi trên row:

```java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select item from InventoryItem item where item.id = :id")
    Optional<InventoryItem> findForUpdate(@Param("id") long id);
}
```

Nếu transaction A đã khóa row, transaction B gọi `findForUpdate` có thể phải chờ. Test chạy đồng thời cần xác định rõ transaction nào giữ khóa và khi nào nó nhả khóa.

Không nên dùng một test method duy nhất với transaction bao quanh rồi mong một worker thread khác nhìn thấy thay đổi chưa commit. Transaction Spring thường gắn với thread hiện tại; worker thread có transaction riêng. Điều này có thể khiến worker bị block hoặc đọc trạng thái cũ.

### Deadlock khác lock wait timeout

| Hiện tượng | Ý nghĩa | Dấu hiệu |
|---|---|---|
| Lock wait timeout | Transaction chờ một khóa lâu hơn giới hạn | Một transaction giữ lock; transaction khác đang chờ |
| Deadlock | Các transaction chờ khóa của nhau tạo thành chu trình | Database phát hiện chu trình và hủy một transaction |
| Query timeout | Câu SQL chạy quá lâu, có thể do scan lớn hoặc chờ lock | Timeout của statement/client bị kích hoạt |
| Connection acquisition timeout | Không lấy được connection từ pool | Pool cạn hoặc connection không được trả lại |

Deadlock thường được database phát hiện và chọn một transaction làm victim. Lock wait timeout thường chỉ báo rằng thời gian chờ một khóa đã vượt ngưỡng. Cả hai đều có thể xuất hiện như lỗi persistence ở tầng Spring, nhưng cách khắc phục khác nhau.

### Tránh giữ transaction/lock trong lúc gọi dịch vụ ngoài

Một nguyên nhân phổ biến là transaction mở quá lâu:

```java
@Transactional
public void reserve(long itemId) {
    InventoryItem item = repository.findForUpdate(itemId).orElseThrow();
    paymentClient.authorize(item.getPrice()); // network call khi đang giữ lock
    item.decreaseAvailable();
}
```

Nếu HTTP call chậm, row lock có thể bị giữ trong toàn bộ thời gian chờ mạng. Những transaction khác cập nhật cùng row phải đợi, làm tăng lock contention.

Thiết kế tốt hơn thường là rút ngắn vùng transaction, kiểm tra điều kiện trước khi giữ lock nếu có thể, dùng reservation/state transition có thời hạn hoặc một quy trình saga/outbox phù hợp. Không thể đơn giản bỏ transaction nếu điều đó làm mất tính nhất quán; hãy xác định invariant nghiệp vụ trước khi thay đổi ranh giới commit.

### Test lock contention một cách xác định

Một concurrency test cần hai transaction và cơ chế phối hợp rõ ràng. Có thể dùng `CountDownLatch` để xác nhận transaction đầu đã giữ lock trước khi transaction thứ hai thử lấy lock. Test nên có timeout ở cả latch và thao tác database, và luôn giải phóng transaction trong `finally`.

Không dùng `Thread.sleep()` để hy vọng transaction A đã khóa row trước khi B chạy. Thay vào đó, transaction A báo tín hiệu ngay sau khi truy vấn khóa thành công; test chỉ khởi động B sau tín hiệu đó.

Khi kiểm thử lock timeout, đặt giới hạn lock wait nhỏ trong cấu hình riêng của test nếu database hỗ trợ. Không thay đổi timeout toàn cục của môi trường dùng chung. Xác nhận đúng exception/cause do driver hoặc ORM ném ra, vì exception wrapper có thể khác theo database và version.

### Optimistic locking và retry

Với `@Version`, Hibernate/JPA có thể phát hiện hai transaction cùng cập nhật một entity và một transaction ghi đè phiên bản cũ. Lỗi thường xuất hiện dưới dạng `OptimisticLockException` hoặc `ObjectOptimisticLockingFailureException`.

Đây không phải lock wait timeout. Database không nhất thiết phải chờ khóa lâu; thay vào đó, update không khớp version hiện tại. Nếu ứng dụng có retry, test cần xác nhận retry chỉ áp dụng cho lỗi có thể retry và số lần retry có giới hạn. Retry không phù hợp có thể biến một lỗi xung đột rõ ràng thành timeout kéo dài.

## Connection pool cạn hoặc connection không được trả lại

Spring Boot thường dùng HikariCP cho JDBC datasource. `connectionTimeout` là thời gian tối đa caller chờ lấy connection từ pool. Khi pool hết connection, log có thể cho biết pool đã active hết, idle bằng 0 và thread đang chờ.

Nguyên nhân thường gặp:

- Transaction bị giữ mở quá lâu.
- Connection hoặc JDBC resource không được đóng khi dùng API thủ công.
- Nhiều task async đồng thời đều cần database nhưng pool quá nhỏ.
- Test chạy song song vượt khả năng database/pool.
- Một task đang giữ connection trong khi chờ một tác vụ khác cần chính pool đó.

Ví dụ cấu hình pool trong test:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 3000
```

Không tăng `maximum-pool-size` ngay khi thấy timeout. Trước tiên kiểm tra active/idle/pending connections, transaction duration và số worker thread đang truy cập database. Tăng pool khi database không chịu được nhiều connection hơn có thể làm tình trạng xấu thêm.

Một deadlock ở tầng ứng dụng cũng có thể liên quan pool: task A giữ connection rồi đợi future B, trong khi B cần connection nhưng pool đã cạn. Tránh chờ task khác trong khi đang giữ transaction/connection nếu task đó cần cùng tài nguyên.

## Hạ tầng chưa sẵn sàng dù container đã chạy

Testcontainers có thể báo container đang chạy nhưng service bên trong chưa hoàn tất startup. Database có thể còn chạy recovery; broker có thể chưa tạo listener; HTTP service có thể chưa nạp cấu hình hoặc chưa kết nối được dependency của nó.

Phân biệt các trạng thái:

```text
Container created
      |
      v
Container process running
      |
      v
Port is listening
      |
      v
Service health check passes
      |
      v
Application-level operation succeeds
```

Một port mở chỉ chứng minh có process nhận TCP connection. Nó không chứng minh database đã nhận query, broker đã sẵn sàng nhận message hoặc ứng dụng phụ trợ đã load đầy đủ dữ liệu.

### Dùng wait strategy thay vì sleep

Testcontainers hỗ trợ chờ theo port, log, HTTP endpoint và Docker health check. Ví dụ HTTP health endpoint:

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/report-service:1.4.2"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/actuator/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

Với database, ưu tiên module container chuyên dụng như `PostgreSQLContainer`, vì module đó có wait strategy phù hợp. Với service tùy chỉnh, chọn endpoint hoặc log chỉ xuất hiện khi service đã thực sự sẵn sàng.

Không làm như sau:

```java
container.start();
Thread.sleep(5000); // không bảo đảm service đã ready
```

Máy nhanh sẽ chờ dư; máy chậm có thể vẫn chưa sẵn sàng. Wait strategy có timeout cung cấp cả điều kiện hoàn tất và thông báo lỗi rõ hơn.

### Endpoint động và thứ tự khởi tạo Spring context

Container thường được map sang host port động. Không hardcode `localhost:5432` hoặc port mặc định nếu Testcontainers cấp port khác. Lấy endpoint qua API container và đăng ký vào Spring bằng `@DynamicPropertySource` hoặc `@ServiceConnection`:

```java
@Container
@ServiceConnection
static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine");
```

Hoặc:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Supplier phải trả về endpoint của container đang sống khi Spring tạo datasource. Nếu context được cache lâu hơn container, test sau có thể dùng context chứa URL của container đã dừng. Khi đó lỗi có thể xuất hiện ở test class khác dù cấu hình class đó trông giống hệt.

### Broker và consumer readiness

Broker sẵn sàng nhận connection không có nghĩa consumer đã subscribe, partition assignment đã hoàn tất hoặc listener container đã chạy. Nếu test publish message ngay sau khi context khởi động, message có thể đến trước khi consumer bắt đầu lắng nghe.

Hãy chờ một tín hiệu readiness cụ thể của consumer hoặc xác nhận subscription/assignment bằng API phù hợp. Với Kafka, có thể quan sát listener container và partition assignment; với RabbitMQ, kiểm tra queue/binding đã được tạo. Khi xác nhận message được xử lý, dùng correlation ID hoặc trạng thái cuối cùng có thể truy vấn.

Không chờ cố định vài giây sau khi publish. Hãy chờ điều kiện xử lý thành công bằng Awaitility hoặc latch có timeout.

## Chẩn đoán timeout theo dấu hiệu

| Dấu hiệu | Nguyên nhân có khả năng | Dữ liệu cần lấy |
|---|---|---|
| Future timeout nhưng task chưa log bắt đầu | Executor queue đầy, task bị reject hoặc proxy không dispatch | Executor active count, queue size, rejection log, thread name |
| Task bắt đầu nhưng không hoàn tất | Query, HTTP call, lock hoặc downstream call bị treo | Thread dump, log theo correlation ID, client timeout và DB activity |
| Hikari `Connection is not available` | Pool cạn hoặc connection bị giữ | Active/idle/pending, transaction duration, leak detection log |
| Query chờ lâu | Lock contention, scan lớn hoặc database quá tải | DB lock table, query plan, statement duration |
| Database connection refused ngay khi startup | Container/service chưa ready hoặc endpoint sai | Container logs, mapped port, JDBC URL, wait strategy |
| Consumer không nhận message | Listener chưa chạy, topic/queue sai hoặc offset/group không phù hợp | Listener state, topic/queue, partition assignment, consumer lag |
| Chỉ fail khi chạy song song | Data collision, shared lock, pool/executor capacity hoặc shared resource | Test isolation, worker count, DB locks, queue size |
| Lần đầu pass, test sau fail connection | Container đã dừng nhưng context cache còn dùng endpoint cũ | Container lifecycle và Spring context cache |
| JUnit `@Timeout` hết trước khi có lỗi cụ thể | Timeout tổng nhỏ hơn timeout bước con hoặc test bị block | Thread dump tại thời điểm timeout và timeout từng tầng |

## Thu thập thread dump khi test bị treo

Thread dump giúp xác định thread đang chạy, chờ monitor, chờ condition hoặc bị block ở I/O. Khi test treo, lấy thread dump của JVM test trước khi process bị kill nếu có thể.

Những trạng thái đáng chú ý:

- `BLOCKED`: thread đang đợi monitor lock do thread khác giữ.
- `WAITING` hoặc `TIMED_WAITING`: thread đang chờ latch, future, condition, queue hoặc timer; cần xem stack frame để biết đang chờ gì.
- Stack frame JDBC: thread có thể đang đợi database/driver hoặc connection pool.
- Stack frame HTTP client: thread có thể đang đợi response hoặc socket read.
- `ThreadPoolExecutor.getTask`: worker đang chờ task; nếu không có worker active, task có thể chưa được submit hoặc queue rỗng.

Trong môi trường có thể dùng JDK tools, `jcmd <pid> Thread.print` hoặc `jstack <pid>` tạo thread dump. Nếu dùng CI, cấu hình lưu thread dump khi timeout hoặc khi test process sắp bị kết thúc. Đừng chỉ nhìn trạng thái thread; đọc stack trace để nối nó với task và resource cụ thể.

Nên gắn correlation ID/job ID vào log của task nền để ghép request ban đầu, lần submit, lúc worker bắt đầu và lúc hoàn tất. Điều này giúp phân biệt task chưa được schedule với task đã chạy nhưng bị kẹt ở một dependency.

## Kiểm tra database lock và query đang chờ

Khi nghi ngờ database lock, kiểm tra trực tiếp trạng thái database trong lúc test còn đang bị chặn. Với PostgreSQL, có thể xem session, query và lock wait qua `pg_stat_activity` và `pg_locks`:

```sql
select pid,
       state,
       wait_event_type,
       wait_event,
       now() - query_start as query_age,
       query
from pg_stat_activity
where datname = current_database()
order by query_start;
```

Để xem quan hệ blocker/waiter:

```sql
select waiting.pid as waiting_pid,
       waiting.query as waiting_query,
       blocking.pid as blocking_pid,
       blocking.query as blocking_query
from pg_stat_activity waiting
join pg_stat_activity blocking
  on blocking.pid = any(pg_blocking_pids(waiting.pid));
```

Query này dành cho PostgreSQL; quyền xem một số session có thể phụ thuộc role. Đối với MySQL, xem `performance_schema.data_locks`, `data_lock_waits` và `information_schema.innodb_trx`. Với database khác, dùng công cụ lock monitoring tương ứng.

Khi đã tìm thấy blocker, xác định transaction nào đang giữ khóa, nó bắt đầu từ test nào và có đang chờ một network call hoặc future khác không. Kết thúc transaction bị treo trong cleanup và rút ngắn vùng giữ lock. Không kill session tùy tiện trên database dùng chung; chỉ thực hiện trên database test được cô lập.

## Phân biệt timeout với deadlock và data race

Không phải mọi test concurrency thất bại đều là timeout:

| Lỗi | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Timeout | Một thao tác không hoàn tất trước deadline | Xác định điểm chờ và tầng timeout |
| Deadlock | Nhiều transaction/thread tạo chu trình chờ nhau | DB deadlock report hoặc thread dump; xem thứ tự lấy lock |
| Optimistic locking conflict | Version đã thay đổi trước khi update | Kiểm tra `@Version`, retry và concurrent writes |
| Unique constraint violation | Hai test/task tạo cùng khóa duy nhất | Kiểm tra fixture, namespace và test parallelism |
| Lost update | Một cập nhật ghi đè thay đổi khác | Kiểm tra transaction isolation và cơ chế locking |
| Data race trong memory | Nhiều thread truy cập state không được đồng bộ | Kiểm tra thread safety và visibility |

Timeout đôi khi chỉ là hệ quả của deadlock hoặc data race khiến điều kiện chờ không bao giờ đúng. Hãy giữ exception và log từ database/executor thay vì đổi timeout để che dấu hiệu.

## Transaction test và async worker là hai thread khác nhau

Spring transaction thông thường được gắn với thread hiện tại. Một test method có `@Transactional` có thể mở transaction test-managed; khi gọi `@Async`, worker thread không tự động tham gia transaction đó.

Điều này dẫn đến một số tình huống:

- Test ghi dữ liệu nhưng chưa commit, sau đó async worker truy vấn dữ liệu đó và không nhìn thấy thay đổi chưa commit.
- Test giữ row lock đến khi method kết thúc, trong khi worker cần row đó và bị block.
- Test method chờ future hoàn tất, nhưng future đang chờ database lock do chính transaction test giữ.
- Test kết thúc và rollback transaction, trong khi worker vẫn chạy và tiếp tục thao tác trên dữ liệu đã bị rollback.

Một deadlock ở tầng ứng dụng có thể hình thành như sau:

```text
Test thread:
  mở transaction A
  khóa row X
  submit async task
  chờ Future hoàn tất
          |
          v
Worker thread:
  mở transaction B
  cần khóa row X
  chờ transaction A nhả khóa

Transaction A chỉ nhả khóa khi test thread hết chờ Future.
```

Đây là vòng chờ do thiết kế test tạo ra. Để xử lý, hãy commit transaction ghi trước khi worker đọc, không giữ lock trong khi chờ async task, hoặc thiết kế test dùng hai transaction với thứ tự rõ ràng. Nếu test cần kiểm tra dữ liệu sau commit, đọc bằng transaction mới sau khi transaction ghi kết thúc.

Với test HTTP qua `RANDOM_PORT`, request được xử lý trên server thread và có transaction riêng. `@Transactional` trên test không tự động rollback transaction của server. Cần cleanup dữ liệu đã commit hoặc dùng database/schema riêng.

## Test chạy song song và tranh chấp dữ liệu

Một test pass khi chạy riêng nhưng timeout khi chạy toàn suite có thể đang tranh chấp dữ liệu hoặc tài nguyên dùng chung:

- Hai test cập nhật cùng row và giữ lock chéo.
- Test dùng cùng email, username hoặc external reference có unique constraint.
- Nhiều test cùng dùng topic, consumer group, Redis key hoặc bucket prefix.
- Số worker test vượt khả năng connection pool hoặc executor.
- Container/service được chia sẻ nhưng một test reset state khi test khác đang dùng.

Giải pháp là cô lập dữ liệu và namespace theo test/worker, giảm mức song song nếu tài nguyên thực sự giới hạn, và tránh cleanup toàn cục trên tài nguyên dùng chung. Không nên tắt chạy song song vĩnh viễn chỉ để che một race condition; trước tiên cần xác định tài nguyên nào bị chia sẻ.

Khi test song song là yêu cầu, thiết kế fixture có ID duy nhất, transaction ngắn, lock order nhất quán và cleanup chỉ xóa dữ liệu thuộc test hiện tại. Với broker, tạo topic/group riêng hoặc dùng correlation key; với cache/storage, prefix key/bucket riêng.

## Retry có phải cách sửa timeout?

Retry hữu ích khi lỗi tạm thời và thao tác có thể lặp an toàn, ví dụ service khởi động chậm hoặc một request idempotent gặp lỗi mạng tạm thời. Retry không phù hợp để che:

- Deadlock do thứ tự lấy lock không nhất quán.
- Connection leak hoặc pool bị cạn.
- Executor không có worker khả dụng.
- Task bị submit nhiều lần và tạo side effect trùng.
- Test fixture dùng chung gây unique constraint conflict.
- Readiness không được cấu hình và service có thể không bao giờ sẵn sàng.

Nếu dùng retry, đặt số lần thử và tổng thời gian tối đa rõ ràng, dùng backoff phù hợp, ghi log attempt/cause, và bảo đảm operation idempotent hoặc có idempotency key. Test cần xác nhận retry dừng khi hết ngân sách và không tạo side effect trùng.

## Quy trình xử lý timeout trong Spring test

1. **Xác định điểm chờ:** JUnit method, future/latch, executor, connection pool, SQL lock, network client hay container readiness.
2. **Đọc cause và log trước timeout:** tìm `TimeoutException`, `SQLTransient...`, `CannotGetJdbcConnectionException`, `TaskRejectedException`, HTTP timeout hoặc message của Testcontainers.
3. **Quan sát trạng thái lúc bị treo:** lấy thread dump, executor metrics, pool metrics, DB activity/locks hoặc container logs.
4. **Kiểm tra transaction boundary:** xem thread nào mở transaction, transaction nào giữ lock và worker có cần dữ liệu chưa commit không.
5. **Kiểm tra readiness và endpoint:** service đã health-ready chưa, port có phải mapped port hiện tại không, context cache có giữ endpoint cũ không.
6. **Điều chỉnh đúng tầng:** query timeout cho query, lock timeout cho lock wait, connection timeout cho pool, wait strategy cho container, future timeout cho async completion.
7. **Chạy lại test cô lập rồi chạy suite liên quan:** xác nhận lỗi gốc đã hết và không còn tranh chấp khi chạy song song.

## Bảng chẩn đoán nhanh

| Thông báo/dấu hiệu | Nguyên nhân cần nghĩ đến đầu tiên | Bằng chứng nên lấy |
|---|---|---|
| `TimeoutException` từ `Future.get` | Async task chưa hoàn tất hoặc chưa bắt đầu | Executor metrics, worker log, thread dump |
| Awaitility timeout | Điều kiện trạng thái chưa xảy ra | Giá trị hiện tại, polling exception, task/job status |
| `TaskRejectedException` | Executor queue/thread capacity hoặc shutdown | Pool size, queue capacity, lifecycle và rejection policy |
| `Connection is not available, request timed out` | Hikari pool cạn hoặc connection bị giữ | Active/idle/pending connections, leak detection, transaction duration |
| `Lock wait timeout exceeded` | Transaction khác đang giữ row/table lock | DB lock view, blocker session, transaction age |
| `Deadlock found` / deadlock detected | Chu trình chờ khóa giữa các transaction | Database deadlock report, thứ tự truy cập tài nguyên |
| `statement timeout` | Query quá lâu hoặc đang chờ lock | Query plan, DB activity, statement/lock timeout settings |
| Container startup timeout | Service trong container chưa ready hoặc wait condition sai | Container logs, health status, startup command |
| Connection refused ngay sau container start | Endpoint/port sai hoặc service chưa listen | Mapped port, wait strategy, service log |
| Consumer test timeout | Listener chưa subscribe hoặc message chưa được xử lý | Listener state, topic/queue, consumer lag, correlation ID |
| Chỉ timeout khi suite chạy song song | Tranh chấp dữ liệu hoặc cạn tài nguyên | Test isolation, pool/executor metrics, DB lock view |

## Nguyên tắc đặt timeout ổn định

- Đặt timeout hữu hạn ở mọi điểm chờ có thể treo: future, latch, Awaitility, network client và test framework.
- Dùng tín hiệu hoàn tất thực tế; tránh `Thread.sleep()` và các giả định dựa trên thời gian cố định.
- Phân biệt task được submit, task bắt đầu, task hoàn tất và side effect đã commit.
- Giữ transaction ngắn; không chờ network hoặc future trong khi đang giữ row lock/connection nếu worker cần chính tài nguyên đó.
- Dùng wait strategy theo readiness của dịch vụ, không chỉ kiểm tra container process đã chạy.
- Cô lập database row, topic, queue, cache key và object storage giữa các test song song.
- Thu thập thread dump, pool metrics, DB lock information và container logs khi timeout xảy ra.
- Chỉ tăng timeout khi thời gian hiện tại không phù hợp với SLA hợp lý; không dùng nó để che deadlock, leak hoặc readiness sai.

Khi một test hết thời gian, điều quan trọng là tìm được thành phần đang giữ hoặc chờ tài nguyên. Tách timeout theo tầng, đồng bộ tác vụ nền bằng future/latch, quan sát lock và connection pool, đồng thời chờ hạ tầng theo health condition giúp lỗi được định vị rõ ràng. Test sẽ ổn định hơn khi transaction ngắn, tài nguyên được cô lập và mọi thao tác chờ đều có điều kiện hoàn tất cùng giới hạn thời gian cụ thể.
