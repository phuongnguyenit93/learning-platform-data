# Port, thread hoặc tài nguyên còn sống sau khi test kết thúc

## 1. Vì sao JUnit báo xanh nhưng tiến trình vẫn không thoát?

Bạn chạy `mvn test`. Trong IDE, test method đã hiện dấu tích xanh; vài giây sau Maven vẫn chưa trả prompt. Hoặc test thứ nhất mở một HTTP server trên cổng 8080; test thứ hai báo `Address already in use`. Hoặc CPU tiếp tục tăng dù JUnit đã chạy xong; console còn in log từ `@Scheduled`; PostgreSQL Testcontainers vẫn hiện running; một thử nghiệm khác kết nối nhầm WireMock server được tạo từ bài test trước.

Những triệu chứng này có thể đến từ **hai loại vòng đời khác nhau**:

- **Tài nguyên đang sống hợp lệ**: Spring TestContext **cache ApplicationContext giữa các test methods/classes**, nên embedded web server, Hikari pool, listener container hoặc executor là Spring bean vẫn hoạt động cho đến lúc context thực sự đóng. Test method kết thúc **không** có nghĩa context hoặc mọi Spring-managed resource phải đóng ngay.
- **Rò rỉ tài nguyên (leak)**: chính test hoặc application code khởi tạo `new ServerSocket`, `Executors.newSingleThreadExecutor()`, HTTP client, Scheduler, file stream, Thread hoặc Docker container rồi **không có owner/lifecycle/cleanup phù hợp**. Tài nguyên sống vượt quá thời gian được phép, làm suite nhiễm chéo hoặc giữ JVM không thoát.

Bài học thuộc nhóm **Chẩn đoán lỗi kiểm thử**. Mục tiêu là nhận diện đúng **tài nguyên nào còn sống, ai sở hữu, khi nào đáng lẽ phải đóng và bằng chứng nào xác nhận đã đóng** — thay vì chỉ thấy tên thread Tomcat/Hikari rồi kết luận “memory leak”.

### Sau bài học, bạn có thể

1. Phân biệt lifecycle của `@Test`, JUnit test class, Spring `ApplicationContext` được cache, JVM fork, Docker/Testcontainers resource và external service.
2. Nhận biết `BindException: Address already in use`, `Connection refused`, Surefire fork không thoát, hanging non-daemon threads và resource contention.
3. Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` đúng cách, không giữ cổng HTTP cố định giữa các integration test không tương thích.
4. Giải thích vì sao `@DirtiesContext` gây context close nhưng **không phải cơ chế cleanup tất cả tài nguyên** và không nên dùng đại trà.
5. Dùng Spring `@Bean` destroy callbacks, `@PreDestroy`, `DisposableBean`, `SmartLifecycle` và `ThreadPoolTaskExecutor` để quản lý resources.
6. Dùng Java `AutoCloseable`/try-with-resources, `ExecutorService.shutdown()`/`awaitTermination()` và `Future.get(timeout)` trong tests.
7. Phân biệt daemon/non-daemon thread, blocked thread, thread sống do context còn mở và thread thực sự bị leak.
8. Chẩn đoán bằng `jps`, `jcmd Thread.print`, `jstack`, `ss`, `lsof`, `netstat`, `Get-NetTCPConnection` hoặc JFR mà không phá chứng cứ.
9. Hiểu các bẫy của `@Async`, `@Scheduled`, Reactor Netty, servlet server, Hikari, Testcontainers, embedded Kafka/WireMock và file descriptors.
10. Viết regression test chứng minh cổng được giải phóng sau khi **context riêng** đóng, executor Spring bean được shutdown và socket do test sở hữu được đóng.
11. Không assert thread count toàn JVM phải bằng 0 hoặc “không còn cổng đang LISTEN” sau mọi `@Test`, bởi các thành phần khác có thể hợp lệ đang hoạt động.
12. Chạy một dự án **Java 17 + Spring Boot 3.5.16 + Maven + JUnit 5** có hai kiểu thử nghiệm: full Spring context và context/resource được tạo riêng để đóng chủ động.
13. Thiết kế CI diagnostics với timeout, thread dump, process owner/PID, resource close checks và vòng đời phù hợp.
14. Báo cáo đúng nguyên nhân thay vì tăng timeout, đổi port ngẫu nhiên hoặc `kill -9` làm workaround.

## 2. Bốn đồng hồ vòng đời phải vẽ rõ

~~~text
JVM / Maven Surefire fork
  |
  +-- JUnit test class A
  |     |
  |     +-- @BeforeAll
  |     +-- @BeforeEach -> @Test -> @AfterEach
  |     +-- ...
  |     +-- @AfterAll
  |
  +-- JUnit test class B
  |     |
  |     +-- @BeforeEach -> @Test -> @AfterEach
  |
  +-- Spring TestContext cache (per JVM)
  |     |
  |     +-- ApplicationContext key K
  |           |
  |           +-- embedded server / port
  |           +-- ThreadPoolTaskExecutor
  |           +-- HikariDataSource
  |           +-- listeners/schedulers
  |           +-- Spring-managed Testcontainers beans
  |
  +-- Unmanaged resources created by test/application
  |     |
  |     +-- new Thread(...)
  |     +-- Executors.newScheduledThreadPool(...)
  |     +-- new ServerSocket(...)
  |     +-- file stream / HTTP client / Process
  |
  +-- JVM exit / context cache shutdown hook
        |
        +-- cached contexts are closed
        +-- Spring-managed beans destroyed
        +-- remaining non-daemon/blocked/shutdown hooks
             may delay or interfere with termination
~~~

**Điểm mấu chốt:** `@AfterEach` chỉ bảo đảm những callback JUnit thuộc invocation đó đã hoàn tất theo lifecycle bình thường; nó **không** nói tất cả Spring singleton beans đã bị destroy. Spring TestContext cache giúp các test classes cùng configuration tiết kiệm startup; context có thể chỉ đóng do `@DirtiesContext`, LRU eviction hoặc JVM shutdown hook.

### 2.1. Owner và thời điểm giải phóng

| Resource | Owner thường gặp | Thời điểm giải phóng đúng | Dấu hiệu leak thực tế |
| --- | --- | --- | --- |
| `@TempDir` directory | JUnit | Theo extension/test scope | Tự giữ file handle; temp không xóa được |
| `ServerSocket` test tạo | Test method/fixture | `try-with-resources` hoặc `@AfterEach` | Port vẫn LISTEN sau khi fixture đóng |
| `ExecutorService` test tạo | Test fixture | `shutdown` và bounded await | Worker non-daemon còn sống sau test |
| `ThreadPoolTaskExecutor` Spring bean | ApplicationContext | Context close / Spring destroy lifecycle | Sau **context close** vẫn giữ worker threads |
| Embedded Tomcat/Jetty/Netty | ApplicationContext | Context close | Port còn LISTEN sau close và grace period |
| `HikariDataSource` | ApplicationContext | Bean destroy/context close | Pool threads/connections còn sau close |
| `@Scheduled` jobs | Scheduler + context | Scheduler stop/context close | Scheduled task vẫn tạo side effects khi không nên |
| Testcontainers `@Container` | JUnit extension | Per-method/per-class theo annotation | Container không stop theo JUnit lifecycle đã định |
| Testcontainers `@Bean` | Spring ApplicationContext | Khi context đóng | Container vẫn chạy sau context thật sự close |
| Testcontainers singleton thủ công | Test suite/JVM | Khi owner chủ động stop/JVM cleanup | Vượt quá owner lifetime hoặc phá shared tests |
| Reactor scheduler tạo bằng `Schedulers.new...` | Call site | `dispose()` đúng scope | Thread `reactor-*` do custom scheduler còn |
| HTTP client/socket pool | Library owner hoặc Spring bean | Client close/destroy | TCP connections/threads tồn sau close |
| JDBC `Connection` borrow | Caller/service | Return to pool sau operation | Pool exhausted, connection leak |
| Open file `InputStream` | Caller | Try-with-resources | File descriptor tăng qua nhiều tests |
| OS child process | Test/launcher | Process exit/destroy + bounded wait | Child PID chạy sau suite kết thúc |

Một resource có thể sống trong **application context cache** mà không phải leak. Kết luận phải so với **lifetime của owner**, không chỉ thời điểm kết thúc một test method.

### 2.2. “Test kết thúc” nghĩa là gì?

- **JUnit test method complete**: Assertions và callbacks của method đã kết thúc.
- **Test class complete**: `@AfterAll` đã chạy; Spring context **có thể** vẫn cached.
- **ApplicationContext closed**: Spring gọi stop/destroy lifecycle cho những beans do nó quản lý.
- **Surefire fork exited**: JVM fork đã dừng; không có Java threads của fork đó tiếp tục.
- **Docker container stopped**: Docker resource đã kết thúc; khác với Java wrapper object bị garbage-collected.
- **Network port released**: OS không còn listening socket trên địa chỉ/protocol/port đó; khác với đã stop test.

Khi debug, phải ghi rõ bạn đang kiểm điểm nào. “Port vẫn mở sau test method” có thể đúng; “port vẫn mở sau `context.close()` trong một isolated test” đáng điều tra.

## 3. Chẩn đoán nhanh theo triệu chứng

### 3.1. Maven test xong nhưng terminal vẫn đứng

Dấu hiệu:
- Surefire báo tests hoàn thành, nhưng build chưa exit.
- JVM vẫn có platform non-daemon threads.
- Stack dump có worker của `newSingleThreadExecutor`, scheduler hoặc shutdown hook chờ mãi.
- Một `@AfterAll` đang chặn vì `CountDownLatch.await()` không timeout.
- Thread join/future get không thời hạn.
- Một child process do test tạo vẫn hoạt động hoặc I/O stream chưa được drain.

**Không kết luận chỉ từ một thread:** Hikari housekeeper, Tomcat, JUnit, Attach Listener, ForkJoinPool, GC và test runner có thể có threads hợp lệ. Tập trung thread **non-daemon + owner + stack + thời điểm context close**.

Maven Surefire fork có cơ chế shutdown riêng; một số versions/configurations thực hiện forced halt sau khoảng chờ nhất định cho non-daemon threads. Vì thế rò rỉ có thể biểu hiện thành **khoảng chờ dài rồi fork bị buộc dừng** thay vì treo vô hạn. Không gọi “Maven đã tự thoát nên không leak”.

### 3.2. BindException hoặc Port already in use

Ví dụ:

~~~text
java.net.BindException: Address already in use: bind

org.springframework.boot.web.server.WebServerException:
  Unable to start embedded Tomcat
~~~

Có thể do:
- Một process khác đang listen cố định `server.port=8080`.
- Test A tạo server raw ở port đó rồi quên close.
- Spring context A còn cached nên port vẫn được sử dụng hợp lệ.
- Hai Spring contexts dùng `DEFINED_PORT` và chạy parallel.
- Test B cố tái sử dụng mapped Docker port/host port sai.
- Process từ IDE/build trước chưa dừng.

**Phải xác định owner PID và socket state** trước khi sửa. Chuyển sang random port giúp tránh collision giữa độc lập contexts, nhưng không giải phóng leak và không sửa owner lifecycle sai.

### 3.3. Connection refused sau một class

Đây có thể là **ngược lại** của leak: backend đã bị đóng quá sớm trong khi Spring context cache/client còn sống.

Ví dụ:
- JUnit `static @Container` được stop cuối class A.
- Spring TestContext giữ `DataSource` trong cached context sang class B.
- B dùng port cũ → `Connection refused`.

Khi tài nguyên dừng **sớm hơn** consumer, cần đồng bộ lifetime (Spring-managed Testcontainers `@Bean @ServiceConnection` hoặc owner singleton rõ); không phải chỉ thêm `shutdownNow`.

### 3.4. Log tiếp tục xuất hiện sau assertion

Có thể do:
- Scheduled job tự chạy.
- Async worker chưa xong.
- Listener Kafka/Rabbit đang xử lý messages.
- Delayed retry/backoff.
- Request đang in-flight.
- Context cached còn mở, nên scheduled components vẫn active.

Nếu behavior này **không** được cho phép trong test scope, dùng profile/config để disable scheduling, inject manual trigger, đợi worker completion hoặc đóng context riêng. Không giả định `@SpringBootTest` tự disable `@Scheduled`.

### 3.5. Một test pass riêng, fail khi chạy suite

Chủ yếu kiểm:
- Port cố định/shared singleton.
- Stateful static field và caches.
- Unmanaged executor từ test trước.
- Testcontainers per-class stop vs cached context.
- WireMock server lifecycle.
- `@DirtiesContext` từ class khác.
- Cleanup toàn bảng/Redis `FLUSHALL` trong parallel suite.
- Mock/stubbing thay thế bean trong shared Spring context.

Chạy class riêng có thể tạo JVM/context mới nên resource không còn. Vì thế có thể không tái hiện được lỗi cross-class.

## 4. Cổng mạng: hiểu đúng LISTEN, ESTABLISHED và TIME_WAIT

### 4.1. Server listening port

Một HTTP server thường bind cổng TCP trong trạng thái `LISTEN`. Khi server stop, listener socket phải đóng. Kiểm bằng:
- PID/socket owner;
- bind address (IPv4, IPv6, loopback hay all interfaces);
- protocol (TCP/UDP);
- port.

`127.0.0.1:8080` và `0.0.0.0:8080` có thể xung đột. IPv4/IPv6 dual-stack behavior còn tùy OS. Đừng chỉ tìm chuỗi “8080” rồi kết luận đúng process.

### 4.2. ESTABLISHED không đồng nghĩa listener còn mở

Các HTTP clients với keep-alive có thể duy trì `ESTABLISHED` connections. Khi server dừng hoặc kết nối đóng, sockets có thể chuyển qua `FIN_WAIT`, `CLOSE_WAIT`, `TIME_WAIT` theo TCP lifecycle.

Một socket `TIME_WAIT` còn xuất hiện trong `netstat` **không tự chứng minh** HTTP server đang LISTEN hoặc giữ Java thread leak. OS phải quản lý TCP connection teardown; có thể có cổng remote trùng số cần chẩn đoán.

### 4.3. Kiểm đúng địa chỉ và port

Ví dụ:

~~~text
Local Address        State          PID      Nhận định
127.0.0.1:18081      LISTEN         12345    Có listener trên loopback
0.0.0.0:18081        LISTEN         45678    Có listener mọi IPv4 interfaces
127.0.0.1:18081      TIME_WAIT      -        Connection cũ, không phải listener
127.0.0.1:54321      ESTABLISHED    12345    Client hoặc server connection
~~~

Đây là ví dụ minh họa, không phải output được đo. Nếu test thất bại do collision, xác định **PID của LISTEN endpoint**; sau đó đối chiếu command line/JVM identity.

### 4.4. Random port trong Spring Boot tests

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpTest {
    @LocalServerPort
    int port;
}
~~~

`RANDOM_PORT` yêu cầu OS chọn port khả dụng (thường Boot đặt `server.port=0` cho environment đó), tránh hard-code 8080. `@LocalServerPort` giúp đọc port thực. **Không** dùng giá trị từ static config hoặc đoán port.

Nhưng `RANDOM_PORT`:
- Không đảm bảo resource sẽ tự đóng cuối mỗi `@Test`.
- Không biến raw `new ServerSocket` của bạn thành Spring bean.
- Không sửa non-daemon executor leak.
- Không thay chính sách cleanup khi app tạo many background workers.
- Không loại khả năng resource exhaustion do tạo quá nhiều simultaneous contexts.

### 4.5. WebEnvironment và kết nối thực

| `@SpringBootTest` web environment | Embedded server? | Nhu cầu port |
| --- | --- | --- |
| `MOCK` (default) | Thường mock servlet/reactive web context, không bind HTTP socket | Không cần listener port |
| `RANDOM_PORT` | Có embedded server khi web stack phù hợp | OS cấp port động |
| `DEFINED_PORT` | Có embedded server tại configured port | Có thể va chạm |
| `NONE` | Non-web application context | Không có HTTP listener |

Một test chỉ kiểm service bean không cần HTTP port có thể dùng `NONE`; controller contract qua MockMvc thường dùng `@WebMvcTest`/`@AutoConfigureMockMvc`. Nếu cần HTTP/TCP behavior thật, `RANDOM_PORT` phù hợp.

### 4.6. Đừng dùng port 0 ngoài đúng vai trò

Port 0 có nghĩa “xin OS cấp cổng khả dụng” **khi bind server socket**, nhưng sau đó client phải lấy **port đã bind thật**, không kết nối tới `127.0.0.1:0`. Khi dùng Testcontainers, container internal port và mapped host port cũng khác nhau; cần dùng `getMappedPort`/service connection details.

## 5. Threads: điều gì giữ JVM sống?

### 5.1. Daemon vs non-daemon

Một Java platform thread có flag daemon:
- **Non-daemon thread** thường giữ JVM sống khi còn hoạt động, trừ khi process bị halt/kill hoặc shutdown procedure cưỡng chế.
- **Daemon thread** không tự giữ JVM sống; JVM có thể exit khi chỉ còn daemon threads.
- Tuy nhiên daemon không có nghĩa “đã cleanup”: daemon thread vẫn có thể giữ file/socket/DB state và mutate shared data trong suốt suite.

Dùng `Thread#setDaemon(true)` để che executor leak không phải cách sửa. Cần owner + stop/cancel + bounded await; daemon chỉ là một phần của deployment/termination policy.

### 5.2. ExecutorService tạo thủ công

Anti-pattern:

~~~java
@Test
void badExample() {
    ExecutorService executor =
            Executors.newSingleThreadExecutor();

    executor.submit(() -> {
        while (!Thread.currentThread().isInterrupted()) {
            // work
        }
    });

    // Không shutdown, không đợi task kết thúc.
}
~~~

Đây là **snippet phản ví dụ**, không thuộc project runnable. Với JDK17, `newSingleThreadExecutor` thường tạo non-daemon thread; nếu không shutdown và task không dừng, fork có thể kéo dài/không thoát như mong đợi. Một `Thread.sleep` hay `@AfterEach` ở test khác không tự dừng thread này.

Cách đúng:

~~~java
ExecutorService executor =
        Executors.newSingleThreadExecutor();

try {
    Future<String> future =
            executor.submit(() -> "done");

    String result = future.get(3, TimeUnit.SECONDS);
    assertThat(result).isEqualTo("done");
}
finally {
    executor.shutdown();
    if (!executor.awaitTermination(
            5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(
                5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "executor did not terminate");
        }
    }
}
~~~

Đây là snippet cần imports JUnit/AssertJ/concurrency phù hợp. Bản hoàn chỉnh nằm ở lab. Không gọi `shutdownNow` mà không xử lý interrupted tasks; method này yêu cầu tasks hợp tác interruption. Nếu task chặn native I/O hoặc không kiểm interruption, executor có thể không dừng đúng deadline.

### 5.3. Future.get timeout không thay executor cleanup

`future.get(3, SECONDS)` chỉ giới hạn thời gian chờ result. Nếu timeout, task vẫn có thể chạy. Phải cancel hoặc shutdown với policy, kiểm termination rồi mới cleanup fixture. Không dùng một future timeout như bằng chứng worker thực sự đã dừng.

### 5.4. ThreadFactory và naming

Tên thread giúp tìm owner:

~~~java
ThreadFactory factory = task -> {
    Thread thread =
            new Thread(task, "payment-test-worker");
    thread.setDaemon(false);
    return thread;
};
~~~

Snippet này chỉ tạo factory, chưa có executor. Trong production, dùng prefix theo component (`"invoice-worker-"`, `"sync-listener-"`) và metrics. Đừng đặt tên generic `Thread-1` khiến thread dump khó điều tra.

### 5.5. ThreadLocal và MDC leak

ThreadPool tái sử dụng threads. Nếu task set `ThreadLocal`/`MDC` mà không restore:
- Task B có thể thừa hưởng correlation ID của task A.
- Sensitive context có thể leak qua requests.
- Một thread đã shutdown rồi không còn chạy vẫn có thể giữ object reference cho đến khi giải phóng.

Dùng try/finally:
- Capture old context.
- Set context mới.
- Run task.
- Restore old context hoặc remove khi trước đó null.

Không coi một ThreadLocal leak là non-daemon hang; chúng là hai failure modes khác nhau, có thể cùng xảy ra.

### 5.6. Thread state cần đọc theo stack

Thread dump thường có:
- `RUNNABLE`: đang thực thi hoặc native IO.
- `WAITING`: chờ không thời hạn, ví dụ `LockSupport.park`.
- `TIMED_WAITING`: có timeout/sleep/park.
- `BLOCKED`: chờ intrinsic monitor.
- Native stack/selector: I/O.

Một worker thread đang `WAITING` trong queue của một **executor context còn sống** có thể là idle hợp lệ. Một worker `WAITING` dù owner đã close và policy yêu cầu terminate là vấn đề. Đọc thread names và stack cùng owner lifecycle, không chỉ một state.

## 6. Spring-managed executor và scheduler

### 6.1. ThreadPoolTaskExecutor là managed bean

Spring `ThreadPoolTaskExecutor` triển khai lifecycle và destruction hooks. Đăng ký bằng `@Bean` để Spring kiểm soát stop/shutdown khi context đóng:

~~~java
@Bean("diagnosticExecutor")
ThreadPoolTaskExecutor diagnosticExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setThreadNamePrefix("diag-managed-");
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(10);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(5);

    return executor;
}
~~~

Spring khởi tạo executor bean và gọi destroy lifecycle khi context đóng. `setWaitForTasksToCompleteOnShutdown(true)` ưu tiên hoàn thành queued/running tasks; `setAwaitTerminationSeconds(5)` giới hạn thời gian shutdown chờ. **Đây là trade-off, không phải công thức mọi hệ thống**:
- Có tasks cần hoàn thành vì đang persist critical work.
- Có tasks cần bị cancel sớm vì external dependency sắp đóng.
- Có tasks không bao giờ dừng thì chờ 5 giây không tự sửa bug.
- Với nhiều queue tasks, timeout phải phản ánh SLA và khả năng xử lý hết hàng đợi.
- Spring Framework 6.2 có thêm lifecycle phase/options ảnh hưởng early stop; kiểm config thực thay vì mặc định cho rằng scheduler đã dừng.

### 6.2. Spring Boot task execution auto-configuration

Spring Boot 3.5 có auto-configured `AsyncTaskExecutor` khi không có custom executor tương ứng. Khi đăng ký custom `Executor` bean, auto-config có thể back off. Nếu ứng dụng dùng Spring MVC asynchronous handling/WebFlux/GraphQL, Spring Boot có yêu cầu đặc biệt đối với bean tên `applicationTaskExecutor` trong một số đường tích hợp.

**Quan trọng:** Không chỉ tạo `@Bean ExecutorService` rồi tưởng Spring Boot `@Async` mặc định dùng đúng bean đó; resolution phụ thuộc `@EnableAsync`, `AsyncConfigurer`, bean name/type và Boot properties. Test nên assert task thực chạy trên executor/cấu hình kỳ vọng và shutdown behavior.

### 6.3. Spring task shutdown properties

Các properties như:

~~~properties
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
~~~

áp dụng cho **auto-configured task executor** tương ứng, không nhất thiết override một `ThreadPoolTaskExecutor` custom được tạo thủ công theo cách trong lab. Khi có custom bean, cấu hình trực tiếp bằng setter hoặc builder; tránh tin property luôn điều khiển mọi thread pool.

### 6.4. @Scheduled có thể chạy trong test

Nếu app có `@EnableScheduling` + `@Scheduled`:
- Scheduler được đăng ký trong context.
- `@SpringBootTest` có thể kích hoạt jobs thật.
- Context cached nên jobs còn chạy giữa test methods/classes.
- Job có thể mutate DB/cache đúng lúc test setup/teardown.
- Log có thể tiếp tục sau assertion.

Đây không tự là leak, nhưng có thể là **test isolation violation**. Thiết kế:
- Tách business job logic khỏi trigger.
- Test business job method bằng manual invocation.
- Gate `@EnableScheduling`/trigger config bằng profile/conditional property trong test.
- Với scheduler integration tests, dùng test-only config và completion latches/virtual clock nếu phù hợp.
- Đóng context/scheduler theo owner.

### 6.5. Profile dành riêng cho scheduling

Một mô hình:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("scheduled")
@EnableScheduling
class SchedulingConfiguration {
}
~~~

Đây là snippet cần imports tương ứng; không thuộc Maven lab chính. Khi dùng `@ActiveProfiles("test")` mà không có `scheduled`, scheduling infrastructure từ config này không bật. Nhưng nếu còn một `@EnableScheduling` khác hoặc bean tự start scheduler, bạn vẫn có jobs; kiểm toàn bộ config graph.

### 6.6. @Async và completion

`@Async` thường dispatch qua Spring proxy; self-invocation `this.asyncMethod()` có thể bypass advice và chạy đồng bộ. Khi test:
- Gọi qua Spring-managed proxy.
- Đợi `CompletableFuture`/`Future` hoàn thành với bounded timeout.
- Xác định executor owner.
- Đảm bảo pending work không tiếp tục mutate fixtures sau `@AfterEach`.
- Chỉ tắt scheduling khi scope không cần; không tắt toàn async infrastructure nếu đang kiểm nó.

### 6.7. SmartLifecycle và shutdown phases

Spring `SmartLifecycle` cho phép auto-start, stop callback và phase ordering. Khi context close, các phases có thứ tự nhằm dừng listeners/servers/executors/các beans phụ thuộc phù hợp; Spring Boot 3.5 graceful web shutdown tham gia quá trình này.

Tài nguyên custom như non-Spring-managed thread có thể **không được framework biết**. Muốn đúng lifecycle, đưa resource vào bean hoặc wrapper implement `AutoCloseable`/`DisposableBean`/`SmartLifecycle` với contract stop hữu hạn.

### 6.8. @PreDestroy / DisposableBean / @Bean(destroyMethod)

Ví dụ:

~~~java
@Component
public class PollingClient {

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor();

    @PreDestroy
    void close() {
        worker.shutdown();
        // Production code nên awaitTermination và handle timeout.
    }
}
~~~

Snippet này cần Jakarta `@PreDestroy` import và error handling. Tốt hơn là dùng executor managed bean thay vì tự tạo pool trong service, nhưng nếu API library đòi resource ownership, phải có destroy callback.

Một bean `AutoCloseable`:

~~~java
@Bean(destroyMethod = "close")
RemoteClient remoteClient() {
    return new RemoteClient(...);
}
~~~

Snippet giả định `RemoteClient` có `close()`. Spring có thể infer destroy method cho các kiểu phù hợp, nhưng khai báo explicit giúp owner rõ. **Đừng** đóng client chung từ `@AfterEach` khi nó là singleton vẫn được các test khác dùng.

## 7. Context cache và @DirtiesContext: hiểu trước khi kết luận leak

### 7.1. TestContext cache là chủ đích

Spring Framework 6.2 dùng static context cache trong JVM. Các test classes cùng configuration key có thể reuse context. Mặc định cache tối đa 32 contexts, eviction theo LRU.

Context có thể được đóng bởi:
1. `@DirtiesContext`.
2. LRU cache eviction.
3. JVM shutdown hook lúc suite process kết thúc.

Do đó:
- Test method A xong, Tomcat vẫn listen → **có thể bình thường** vì class B sẽ dùng lại context.
- Class A kết thúc, Hikari housekeeper vẫn xuất hiện → **có thể bình thường**.
- Context K thực sự close, mà các threads do K sở hữu vẫn sống vượt shutdown budget → cần điều tra.
- JVM không exit, dù chỉ còn resources không được Spring quản lý → cần điều tra owner khác.

### 7.2. @DirtiesContext chỉ khi context thực sự “dirty”

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest
class DedicatedDirtyContextTest {
}
~~~

Snippet này phù hợp khi test cố ý thay đổi context-wide state mà không thể reset an toàn. Nó **không phải bước teardown bắt buộc cho mọi @SpringBootTest**; lạm dụng làm suite chậm, container/pool/server khởi động lại nhiều lần, và có thể gây race với parallel tests đang share context.

Nó chỉ close **Spring context**; nếu test tạo raw `new ServerSocket`, `Executors.new...`, external process không phải bean, `@DirtiesContext` không tự gọi close cho resource đó.

### 7.3. Không tự gọi context.close() trên @Autowired shared context

Phản ví dụ:

~~~java
@Autowired
ConfigurableApplicationContext context;

@AfterEach
void cleanup() {
    context.close(); // Có thể phá TestContext cache của các tests khác.
}
~~~

Không làm vậy trong một shared `@SpringBootTest`. Nếu muốn kiểm shutdown/release port, tạo **programmatically owned context** riêng trong plain JUnit test và gọi `close()` trong `finally`; Maven lab có ví dụ chính xác.

### 7.4. @DirtiesContext và parallel tests

Spring Framework docs khuyến cáo thận trọng hoặc không parallelize tests dùng `@DirtiesContext`, bean overrides hoặc shared external systems mà không isolation. Nếu class A đóng context K trong khi class B sử dụng, B có thể báo `ApplicationContext ... no longer active`; đây là test topology race, không phải bằng chứng Tomcat leak.

### 7.5. Cache key khác → nhiều servers/pools

`@ActiveProfiles`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@MockitoBean`, web environment, imported config và parent context có thể tạo cache keys khác nhau. Một suite có nhiều contexts `RANDOM_PORT` có thể hợp lệ mở nhiều HTTP ports đồng thời; không áp yêu cầu “toàn JVM chỉ một listening port”.

Đo context cache hits/misses qua logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Đừng sửa cache maxSize để che một leaked raw socket. Quản lý lifetime/resource ownership là vấn đề riêng.

## 8. Chẩn đoán bằng công cụ OS và JVM

### 8.1. Bước đầu tiên: xác định PID của process test

Trên máy có JDK:

~~~bash
jps -lv

jcmd -l
~~~

`jps`/`jcmd -l` hiển thị Java processes khi quyền attach phù hợp. Nếu chạy Maven Surefire fork, PID Java test fork **có thể khác PID của Maven launcher**; hãy xem command line và parent process. Trong container/CI, phải chạy công cụ bên trong đúng namespace/PID visibility hoặc có quyền attach tương ứng.

Không giả định PID của một process cũ vẫn thuộc test mới: OS có thể reuse PID. Ghi timestamp và command line.

### 8.2. JVM thread dump

~~~bash
jcmd <PID> Thread.print
jstack <PID>
~~~

`<PID>` là ký hiệu chỗ cần thay bằng PID thực trong terminal, **không phải lệnh copy chạy nguyên xi**. Trong thực hành, dùng số PID cụ thể từ `jps`. Thu thread dump **trước khi kill**, tốt nhất 2–3 lần cách nhau để biết stack có tiến triển hay đứng mãi.

Tìm:
- Thread name prefix do ứng dụng đặt.
- `daemon` / thread state.
- `java.util.concurrent.ThreadPoolExecutor.getTask`.
- `ScheduledThreadPoolExecutor`.
- `CountDownLatch.await`, `FutureTask.get`, `LockSupport.park`.
- Netty event loop, Kafka consumer poll, Rabbit listener, Tomcat worker.
- Hikari housekeeper/connection adder.
- `SpringContextShutdownHook` đang chờ destroy bean.
- Test `@AfterAll`/`@AfterEach` chưa return.

Một stack dump không bảo đảm bạn biết owner; kết hợp Spring bean graph, application logs và resource creation stack/profiler khi cần.

### 8.3. Linux: kiểm listener theo port/PID

~~~bash
ss -ltnp

sudo lsof -nP -iTCP -sTCP:LISTEN

sudo lsof -nP -p 12345
~~~

Các lệnh lần lượt cho TCP listeners, process owners và file descriptors của PID cụ thể. `sudo` chỉ khi môi trường cho phép và bạn có quyền; không cần superuser nếu chỉ xem process của chính mình. Với Linux container/CI, namespace/network có thể làm một listener hiển thị khác giữa host và container.

Lọc một port bằng `ss -ltnp 'sport = :8080'` hoặc `lsof -nP -iTCP:8080 -sTCP:LISTEN`. Chỉ coi `LISTEN` là bằng chứng listener đang sống; `TIME_WAIT` cần đọc riêng.

### 8.4. macOS

~~~bash
lsof -nP -iTCP -sTCP:LISTEN

lsof -nP -iTCP:8080 -sTCP:LISTEN

ps -p 12345 -o pid,ppid,command
~~~

Kiểm port 8080 chỉ là ví dụ. Không xóa/kill process nếu chưa biết đó là app thử nghiệm do bạn sở hữu.

### 8.5. Windows PowerShell

~~~powershell
Get-NetTCPConnection -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess

Get-NetTCPConnection -LocalPort 8080 |
  Select-Object LocalAddress,LocalPort,State,OwningProcess

Get-Process -Id 12345

netstat -ano
tasklist /FI "PID eq 12345"
~~~

Nếu cần command line của process:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
  Select-Object ProcessId,ParentProcessId,CommandLine
~~~

Cổng/PID ví dụ phải thay theo kết quả máy. `Get-NetTCPConnection` có thể không có trên một số môi trường PowerShell/Windows cũ, khi đó `netstat -ano` vẫn hữu ích. Xác định process owner **trước khi** dùng `Stop-Process`; kill là giải pháp cấp cứu sau khi lưu evidence, không phải sửa code.

### 8.6. Linux /proc và file descriptors

~~~bash
ls -l /proc/12345/fd
cat /proc/12345/status
~~~

Đây là diagnostic cho Linux nếu permission cho phép. Số FD tăng qua nhiều repetitions có thể chỉ ra file/socket leak. Nhưng phải so baseline sau warm-up: JVM/Netty/Hikari hợp lệ tạo caches/pools rồi ổn định. Không lấy “một FD còn mở” làm bằng chứng leak.

### 8.7. JDK Flight Recorder / Mission Control

JFR có thể giúp điều tra:
- Thread starts/ends, lock contention.
- Socket read/write events.
- File read/write.
- Allocation pressure/GC.
- Execution hot spots.
- Shutdown latency.

Ví dụ tạo recording có giới hạn:

~~~bash
jcmd 12345 JFR.start name=test-leak settings=profile duration=60s filename=leak-check.jfr
~~~

File recording cần được bảo vệ vì có thể chứa thông tin runtime nhạy cảm. Không bật JFR profile nặng liên tục trong mọi CI job nếu chưa đo overhead; dùng trong reproduction environment. Java Flight Recorder thường hữu ích khi thread dump không đủ phân biệt work đang chạy với leak chậm qua nhiều classes.

### 8.8. JVM Memory không phải toàn bộ resource leak

Heap leak, thread leak, FD/socket leak, native/direct buffer leak và external Docker resource leak là các loại khác nhau:
- Heap usage tăng: heap dump/GC roots.
- Thread count tăng không giảm sau teardown: ThreadMXBean/dumps.
- Open file/socket FD tăng: OS lsof/handle tools.
- Direct memory tăng: Netty/JFR/native memory tracking khi bật.
- Database connections vượt giới hạn: Hikari/DB metrics.
- Docker containers tồn qua suite: Docker inspect/ps + owner.
- Port still listen: OS socket table + PID.

Đừng đánh đồng `OutOfMemoryError` với “quên ServerSocket.close” nếu chưa có evidence.

## 9. Test case phải quan sát đúng layer

### 9.1. Kiểm cổng đóng trong test tạo server riêng

Một test có thể:
1. Tạo Spring application context **riêng** với server `port=0`.
2. Lấy bound port thật.
3. Gửi HTTP request thử.
4. Gọi `context.close()` trong `finally`.
5. Kiểm port có thể được bind lại trên loopback.
6. Không sửa shared TestContext cache.

Đây là kiểm **sau owner close**, có ý nghĩa về lifecycle.

### 9.2. Kiểm cổng “đóng sau @Test” trên shared Spring context thường sai

~~~java
@SpringBootTest(webEnvironment = RANDOM_PORT)
class WrongAssumptionTest {
    @LocalServerPort
    int port;

    @AfterEach
    void assertPortIsClosed() {
        // Sai giả định: context vẫn cached khi method xong.
    }
}
~~~

Không đưa anti-pattern này vào lab. Một test khác cần context/web server đang sống; việc listener tiếp tục LISTEN sau method không là bug.

### 9.3. Assert “không còn thread” cần scope

Không nên:

~~~java
assertThat(Thread.activeCount()).isZero();
~~~

JVM và test runtime luôn có nhiều threads, phép đo này còn không đại diện toàn bộ JVM một cách đáng tin.

Nên:
- Đặt prefix thread của resource được test sở hữu.
- Kiểm executor `isShutdown` / `awaitTermination` khi owner close.
- Kiểm worker Future completed/cancelled.
- Nếu cần, kiểm thread name prefix không còn **sau await**, nhưng tránh dùng thread enumerations làm assertion duy nhất (thread có thể đổi lifecycle đúng lúc snapshot).
- Dùng stack dump để điều tra những threads persist bất thường.

### 9.4. Assert port bind lại cũng có caveat

Thử bind lại port cũ sau close là bằng chứng hữu ích **trong môi trường cô lập**. Tuy nhiên:
- Một process khác có thể chiếm port đúng giữa hai operations.
- Bind address khác nhau có thể cho kết quả khác.
- TCP TIME_WAIT của connections cũ có semantics hệ điều hành riêng.
- SO_REUSEADDR/SO_REUSEPORT có hành vi riêng theo OS.
- IPv4/IPv6 dual-stack có thể khiến một địa chỉ bind được nhưng địa chỉ khác không.

Trong lab, context chỉ bind `127.0.0.1`, socket probe cũng bind chính địa chỉ này, `setReuseAddress(true)` và test suite không chủ động chia sẻ port với process khác. Nếu điều kiện CI không ổn định, bổ sung OS listener/PID evidence thay vì coi một lần port rebind là phép chứng minh tuyệt đối.

### 9.5. Negative assertions cần completion signal

Một test như:

~~~java
assertThat(repository.findAll()).isEmpty();
~~~

ngay sau `executor.submit(...)` có thể PASS vì worker chưa ghi gì. Nếu requirement là “không có side effect sau cancel”, cần:
- Ngừng nguồn phát work.
- Cancel pending tasks nếu phù hợp.
- Đợi task termination/shutdown barrier.
- Sau đó assert final durable state.
- Với external eventual systems, có bounded observation window/settling semantics.

Đừng dùng `Thread.sleep(500)` thay synchronization.

## 10. Dự án Maven runnable: port và executor cleanup

### 10.1. Phạm vi lab

Dự án có ba nhóm kiểm thử:

1. **`RandomPortAndManagedTaskTest`**: `@SpringBootTest(RANDOM_PORT)` chứng minh một web server đang sống *hợp lệ trong cached context*, HTTP response đúng và executor bean hoàn tất task. **Không tự close** shared Spring context.
2. **`PortOnlyContextLifecycleTest`**: plain JUnit tạo một Spring web context riêng bằng `SpringApplicationBuilder`, xác nhận HTTP port hoạt động, rồi đóng context trong `finally` và thử bind lại port. Đồng thời kiểm try-with-resources cho raw `ServerSocket`.
3. **`ManagedResourcesLifecycleTest`**: plain JUnit tạo `AnnotationConfigApplicationContext` riêng chứa executor hoặc bean AutoCloseable socket; đóng context và verify shutdown/close. Thêm test tự quản lý ad-hoc `ExecutorService` và fixture temp directory.

Dự kiến **8 phương thức JUnit** với **không có deliberate hang/leak test trong default suite**. Mục tiêu là học cách tạo tài nguyên **có owner có thể kiểm soát**, không cố giữ một non-daemon thread sống vĩnh viễn để làm Maven treo. Các anti-pattern được trình bày dưới dạng snippets không thuộc project runnable.

### 10.2. Cây thư mục

~~~text
resource-lifecycle-diagnostics/
├── pom.xml
├── src/main/
│   ├── java/com/example/lifecycle/
│   │   ├── ResourceLifecycleApplication.java
│   │   ├── ProbeController.java
│   │   ├── ManagedExecutorConfiguration.java
│   │   └── ManagedJobService.java
│   └── resources/
│       └── application.properties
└── src/test/java/com/example/
    ├── lifecycle/
    │   └── RandomPortAndManagedTaskTest.java
    ├── portprobe/
    │   └── PortOnlyContextLifecycleTest.java
    └── resourcesprobe/
        └── ManagedResourcesLifecycleTest.java
~~~

**Vì sao test-only configs ở package khác?** `ResourceLifecycleApplication` scan `com.example.lifecycle`. Các `@Configuration` chỉ dành cho programmatic contexts nằm ở `com.example.portprobe` hoặc `com.example.resourcesprobe` để không vô tình được main application component scan, tránh tạo server/resource test-only trong shared `@SpringBootTest`.

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
  <artifactId>resource-lifecycle-diagnostics</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

Dependencies:
- `spring-boot-starter-web`: Spring MVC, embedded Tomcat và `RestClient`.
- `spring-boot-starter-test`: Spring Boot Test, JUnit Jupiter, AssertJ.
- Spring Context/task-execution classes theo Boot dependencies; không cần Spring Integration/Scheduling starter riêng cho `ThreadPoolTaskExecutor`.
- JDK17 provides `ServerSocket`, `ExecutorService`, `Future`, JMX diagnostics.
- Không có Docker/DB/service bên ngoài, để lifecycle test tập trung.

### 10.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=resource-lifecycle-diagnostics
spring.main.banner-mode=off

# Chỉ bind loopback cho bài học; RANDOM_PORT sẽ cấp port động.
server.address=127.0.0.1

# Không kích hoạt @EnableScheduling trong sample.
logging.level.com.example.lifecycle=INFO
~~~

Không đặt `server.port=8080`. `@SpringBootTest(webEnvironment=RANDOM_PORT)` chọn port động. Với context chương trình tự tạo, ta set `server.port=0` trong `SpringApplicationBuilder`. Việc bind loopback tránh vô ý expose test HTTP endpoint ra network interface khác.

### 10.5. ResourceLifecycleApplication.java

`src/main/java/com/example/lifecycle/ResourceLifecycleApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ResourceLifecycleApplication.class, args);
    }
}
~~~

Main app không tự tạo raw threads/sockets trong static initializer hoặc constructor. Những resources cần sở hữu được tạo qua Spring bean configuration.

### 10.6. ProbeController.java

`src/main/java/com/example/lifecycle/ProbeController.java`:

~~~java
package com.example.lifecycle;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public String probe() {
        return "PONG";
    }
}
~~~

Chỉ có một endpoint trả text. Lời gọi HTTP qua cổng thật giúp xác nhận server đã bind và DispatcherServlet xử lý request; không có DB/scheduler gây nhiễu.

### 10.7. ManagedExecutorConfiguration.java

`src/main/java/com/example/lifecycle/ManagedExecutorConfiguration.java`:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ManagedExecutorConfiguration {

    @Bean("diagnosticExecutor")
    ThreadPoolTaskExecutor diagnosticExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("diag-managed-");
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);

        // Chủ động hoàn tất queued/running tasks khi context đóng.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }
}
~~~

Lưu ý:
- `ThreadPoolTaskExecutor` là bean, được Spring initialize/destroy.
- Đặt thread-name prefix giúp nhìn thấy đúng owner khi dump.
- Queue capacity hữu hạn, tránh unbounded accumulation trong sample.
- Chờ tối đa 5 giây tại shutdown; production cần policy đúng SLA, tasks cần cooperatively cancellable nếu deadline bị vượt.
- Test `@SpringBootTest` không tự đóng context ở `@AfterEach`; executor vẫn hợp lệ sống cho context cached.
- Trong test dùng context riêng, Spring đóng bean khi `context.close()` và ta kiểm termination.

### 10.8. ManagedJobService.java

`src/main/java/com/example/lifecycle/ManagedJobService.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.Future;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ManagedJobService {

    private final ThreadPoolTaskExecutor executor;

    public ManagedJobService(
            @Qualifier("diagnosticExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Future<String> reportWorkerThread() {
        return executor.submit(
                () -> Thread.currentThread().getName());
    }
}
~~~

Đây là một service chạy một task ngắn; không dùng `@Async` vì muốn kiểm trực tiếp executor owner và completion. Tên thread cho phép test xác nhận task đã được dispatch vào managed pool.

### 10.9. RandomPortAndManagedTaskTest.java

`src/test/java/com/example/lifecycle/RandomPortAndManagedTaskTest.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ResourceLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomPortAndManagedTaskTest {

    @LocalServerPort
    int port;

    @Autowired
    ManagedJobService jobs;

    @Test
    void webServerIsLiveOnItsAssignedRandomPort() {
        assertThat(port).isBetween(1, 65535);

        RestClient client = RestClient.create(
                "http://127.0.0.1:" + port);

        String body = client.get()
                .uri("/probe")
                .retrieve()
                .body(String.class);

        assertThat(body).isEqualTo("PONG");
    }

    @Test
    void taskRunsOnManagedExecutorAndCompletes() throws Exception {
        String threadName = jobs.reportWorkerThread()
                .get(3, TimeUnit.SECONDS);

        assertThat(threadName)
                .startsWith("diag-managed-");
    }
}
~~~

**Điều được xác nhận:**
- Context load với real embedded servlet server ở dynamic port.
- HTTP request thật trả đúng response.
- Spring managed executor đã chạy task và future hoàn thành trong deadline.
- Không có lệnh đóng context ở test body/`@AfterEach` vì Spring TestContext sở hữu context cached.
- Test **không khẳng định** port và executor biến mất ngay sau test method; đó không phải contract của một cached `@SpringBootTest`.

`RestClient` trong sample dùng default HTTP request factory phù hợp classpath. Nếu ứng dụng thực dùng HTTP client khác có connection pool riêng, cần đăng ký/close pool đúng owner; test trên không chứng minh mọi custom client pools đã cleanup.

### 10.10. PortOnlyContextLifecycleTest.java

`src/test/java/com/example/portprobe/PortOnlyContextLifecycleTest.java`:

~~~java
package com.example.portprobe;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

class PortOnlyContextLifecycleTest {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class PortOnlyConfiguration {

        @Bean
        PortOnlyEndpoint portOnlyEndpoint() {
            return new PortOnlyEndpoint();
        }
    }

    @RestController
    static class PortOnlyEndpoint {

        @GetMapping("/probe")
        public String probe() {
            return "PONG";
        }
    }

    private static void canBindLoopbackPort(int port)
            throws IOException {

        try (ServerSocket verification = new ServerSocket()) {
            verification.setReuseAddress(true);
            verification.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port));

            assertThat(verification.isBound()).isTrue();
        }
    }

    @Test
    void explicitlyClosedSpringContextReleasesHttpListener() {
        int usedPort;

        ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        PortOnlyConfiguration.class)
                        .web(WebApplicationType.SERVLET)
                        .properties(
                                "server.address=127.0.0.1",
                                "server.port=0",
                                "spring.main.banner-mode=off")
                        .run();

        try {
            WebServerApplicationContext web =
                    (WebServerApplicationContext) context;

            usedPort = web.getWebServer().getPort();
            assertThat(usedPort).isBetween(1, 65535);

            RestClient client = RestClient.create(
                    "http://127.0.0.1:" + usedPort);

            assertThat(client.get()
                    .uri("/probe")
                    .retrieve()
                    .body(String.class))
                    .isEqualTo("PONG");
        }
        finally {
            // Owner của context riêng phải close, kể cả assertion fail.
            context.close();
        }

        // Sau khi owner close, listener port được giải phóng.
        // Thử cùng loopback address; không hard-code 8080.
        try {
            canBindLoopbackPort(usedPort);
        }
        catch (IOException problem) {
            throw new AssertionError(
                    "port still unavailable after context.close: "
                            + usedPort, problem);
        }
    }

    @Test
    void rawServerSocketUsesTryWithResources()
            throws Exception {

        int usedPort;

        try (ServerSocket socket = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            usedPort = socket.getLocalPort();
            assertThat(socket.isBound()).isTrue();
            assertThat(socket.isClosed()).isFalse();
        }

        canBindLoopbackPort(usedPort);
    }
}
~~~

**Điểm thực hành rất quan trọng:**
- Test này là **plain JUnit**, không gắn `@SpringBootTest` lên class; nó tự tạo một isolated Spring context và tự close.
- `PortOnlyConfiguration` ở package `com.example.portprobe` **ngoài scan root `com.example.lifecycle`**.
- Context dùng `@Configuration` + `@EnableAutoConfiguration` và `SpringApplicationBuilder.web(SERVLET)`; chỉ đăng ký controller do test sở hữu.
- Port 0 được OS map thành `usedPort`; không dùng fixed port.
- `finally` đảm bảo context được close khi HTTP assertion fail.
- Try bind lại cùng loopback: kiểm lifecycle sau owner close.
- Raw ServerSocket test dùng try-with-resources, rồi thử bind lại.

**Giới hạn:** Port rebind sau close có thể chịu ảnh hưởng OS port reuse/TIME_WAIT hoặc process ngoài suite bất ngờ bind cùng cổng. Nếu CI quá nhiễu, kết hợp `ss/lsof/Get-NetTCPConnection` và PID evidence; đừng thay test bằng fixed sleep hoặc assert tất cả OS sockets đã biến mất. Cũng không áp pattern `context.close()` này lên một `@Autowired` cached context của các SpringBootTest khác.

### 10.11. ManagedResourcesLifecycleTest.java

`src/test/java/com/example/resourcesprobe/ManagedResourcesLifecycleTest.java`:

~~~java
package com.example.resourcesprobe;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class ManagedResourcesLifecycleTest {

    @Configuration(proxyBeanMethods = false)
    static class WorkerOnlyConfiguration {

        @Bean
        ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();

            executor.setThreadNamePrefix("owned-worker-");
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);

            return executor;
        }
    }

    static final class PortLease implements AutoCloseable {

        private final ServerSocket socket;

        PortLease() throws IOException {
            this.socket = new ServerSocket(
                    0, 50, InetAddress.getLoopbackAddress());
        }

        int port() {
            return socket.getLocalPort();
        }

        boolean isClosed() {
            return socket.isClosed();
        }

        @Override
        public void close() throws IOException {
            socket.close();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PortOnlyResourceConfiguration {

        @Bean(destroyMethod = "close")
        PortLease portLease() throws IOException {
            return new PortLease();
        }
    }

    private static void canBindLoopbackPort(int port)
            throws IOException {
        try (ServerSocket verification = new ServerSocket()) {
            verification.setReuseAddress(true);
            verification.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port));

            assertThat(verification.isBound()).isTrue();
        }
    }

    @Test
    void executorBeanIsShutdownWhenItsContextCloses()
            throws Exception {

        ThreadPoolTaskExecutor executor;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             WorkerOnlyConfiguration.class)) {

            executor = context.getBean(
                    ThreadPoolTaskExecutor.class);

            Future<String> result = executor.submit(
                    () -> Thread.currentThread().getName());

            assertThat(result.get(3, TimeUnit.SECONDS))
                    .startsWith("owned-worker-");
        }

        // Context đã close -> Spring destroyed executor bean.
        assertThat(executor.getThreadPoolExecutor().isShutdown())
                .isTrue();

        assertThat(executor.getThreadPoolExecutor()
                .awaitTermination(5, TimeUnit.SECONDS))
                .isTrue();
    }

    @Test
    void autoCloseableBeanClosesOwnedServerSocket()
            throws Exception {

        PortLease owned;
        int usedPort;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PortOnlyResourceConfiguration.class)) {

            owned = context.getBean(PortLease.class);
            usedPort = owned.port();

            assertThat(owned.isClosed()).isFalse();
        }

        assertThat(owned.isClosed()).isTrue();
        canBindLoopbackPort(usedPort);
    }

    @Test
    void adHocExecutorIsAlwaysShutdownInFinally()
            throws Exception {

        ExecutorService worker =
                Executors.newSingleThreadExecutor(task -> {
                    Thread t = new Thread(
                            task, "ad-hoc-test-owned");
                    t.setDaemon(false);
                    return t;
                });

        try {
            Future<String> future = worker.submit(
                    () -> Thread.currentThread().getName());

            assertThat(future.get(3, TimeUnit.SECONDS))
                    .isEqualTo("ad-hoc-test-owned");
        }
        finally {
            worker.shutdown();

            if (!worker.awaitTermination(
                    5, TimeUnit.SECONDS)) {

                worker.shutdownNow();

                if (!worker.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "test executor did not terminate");
                }
            }
        }

        assertThat(worker.isTerminated()).isTrue();
    }

    @Test
    void temporaryFileFixtureBelongsToThisTest(
            @TempDir Path temporaryDirectory)
            throws IOException {

        Path file = temporaryDirectory.resolve(
                "diagnostic-marker.txt");

        Files.writeString(file, "owned-by-current-test");

        assertThat(Files.readString(file))
                .isEqualTo("owned-by-current-test");

        assertThat(Files.exists(file)).isTrue();
        // @TempDir extension dọn thư mục sau test lifecycle.
    }
}
~~~

### 10.12. Giải thích nhóm ManagedResources tests

**Executor bean shutdown:**
- Tạo riêng một `AnnotationConfigApplicationContext`, không dùng shared TestContext cache.
- Spring khởi tạo `ThreadPoolTaskExecutor`.
- Gửi một task, đợi kết quả bằng `Future.get(timeout)`.
- Context được đóng nhờ try-with-resources.
- Kiểm `isShutdown` và `awaitTermination`, tức **đo executor owner đã kết thúc**; không assert toàn JVM hết threads.

**PortLease AutoCloseable:**
- `PortLease` sở hữu `ServerSocket`.
- Bean đăng ký bằng `@Bean(destroyMethod="close")`.
- Sau context close, xác nhận socket đã đóng và port có thể bind lại.
- Nếu bạn tạo `new PortLease()` bên ngoài Spring mà quên close, context không thể tự quản lý đối tượng ấy.

**Ad-hoc ExecutorService:**
- Không có Spring bean nào sở hữu pool.
- Chính test method phải shutdown trong finally.
- Dùng task ngắn, bounded get, graceful shutdown và fallback `shutdownNow`.
- Sau teardown verify `isTerminated`, để không thừa non-daemon worker.

**@TempDir:**
- JUnit sở hữu thư mục tạm.
- Files API viết/đọc file xong không giữ stream mở.
- JUnit extension cleanup sau invocation.
- Không cố kiểm directory đã bị xóa ngay **trong test body**, vì vòng đời cleanup nằm sau body.

### 10.13. Tổng hợp những điều lab không tuyên bố

Lab **không** chứng minh:
- Mọi thread Spring Boot/Tomcat/Hikari đều phải biến mất ngay sau một `@Test`.
- Mọi OS TCP state (TIME_WAIT) phải biến mất ngay khi server close.
- PostgreSQL/Redis/Kafka pool lifecycle giống H2/simple executor.
- Một `@DirtiesContext` sẽ dọn raw sockets/threads ngoài Spring.
- Một JUnit pass có nghĩa production shutdown graceful với in-flight requests trong mọi deployment.
- JVM sẽ exit ngay cả khi test tạo non-daemon thread ngoài context và không shutdown.
- Servlet/Netty graceful shutdown behavior giống hệt nhau giữa web servers.
- Docker Testcontainers đã được kiểm; project không dùng Docker.

Để kiểm production listener shutdown, connection pools, Kafka consumers, Reactor event loops hoặc WebFlux, mở rộng setup đúng backend rồi viết tests tại boundary tương ứng.

### 10.14. Chạy Maven

Từ thư mục `resource-lifecycle-diagnostics`:

~~~bash
mvn -q clean test

mvn -q -Dtest=RandomPortAndManagedTaskTest test

mvn -q -Dtest=PortOnlyContextLifecycleTest test

mvn -q -Dtest=ManagedResourcesLifecycleTest test
~~~

Dự kiến:
- `RandomPortAndManagedTaskTest`: **2** methods.
- `PortOnlyContextLifecycleTest`: **2** methods.
- `ManagedResourcesLifecycleTest`: **4** methods.
- Tổng **8 JUnit test methods**.

Khi chạy thật, kiểm Maven exit code, số tests executed/skipped/failures và Surefire reports trong `target/surefire-reports`. Spring application context test có thể còn cached giữa methods; phần test-only contexts tự close rõ ràng.

**Trạng thái xác minh:** Code/project được thiết kế theo API Java17, Spring Boot3.5.16, Spring Framework6.2/JUnit5 và đã rà soát cấu trúc; **Maven chưa được thực thi** trong lúc biên soạn bài Knowledge này. Vì vậy những assertions/kết quả nêu là mục tiêu dự kiến, không phải số liệu PASS đã quan sát từ CI.

### 10.15. Không cố làm suite treo để “thấy leak”

Nếu muốn nghiên cứu non-daemon executor leak:
- Đặt anti-pattern trong **dedicated fork/process** có timeout và automatic teardown.
- Thu thread dump trước khi hard-stop.
- Không đưa test cố ý tạo infinite thread vào default Maven suite.
- Không gọi `Runtime.halt` từ test chạy chung với đội.
- Không stop resource của class khác hoặc shared cached context.

Một bài học về leak không nên tự gây leak cho toàn bộ môi trường học.

## 11. Khi nào dùng @PreDestroy, DisposableBean, SmartLifecycle?

### 11.1. @PreDestroy

Phù hợp cleanup nhẹ của một bean:
- Close socket/client.
- Cancel subscription.
- Stop resource heartbeat.
- Flush/tidy locally owned buffer.
- Restore owned global resource nếu được thiết kế trong bean.

~~~java
@Component
class SubscriptionOwner {

    private final AutoCloseable subscription;

    SubscriptionOwner(AutoCloseable subscription) {
        this.subscription = subscription;
    }

    @PreDestroy
    void close() throws Exception {
        subscription.close();
    }
}
~~~

Đây là snippet cần imports/bean binding phù hợp. **Không** dùng chung một subscription bean với nhiều owners rồi mỗi owner đều close dẫn tới double close/mất resource của bean khác. Ownership nên duy nhất hoặc close idempotent.

### 11.2. DisposableBean

~~~java
class LegacyClientOwner implements DisposableBean {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @Override
    public void destroy() throws Exception {
        executor.shutdown();
        if (!executor.awaitTermination(
                5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }
}
~~~

Snippet minh họa cần imports; nếu `awaitTermination` vẫn false sau force shutdown, nên log failure/propagate theo policy. `DisposableBean` làm Spring gọi destroy khi bean thuộc context bị đóng; nhưng Java object được tạo ngoài Spring không được quản lý. Với modern code, `@Bean(destroyMethod="close")`/AutoCloseable thường ít coupling hơn.

### 11.3. SmartLifecycle

Dùng khi resource cần phase ordering và asynchronous stop callback:

~~~java
class ConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start consumer
    }

    @Override
    public void stop(Runnable callback) {
        try {
            // stop consumer và đợi in-flight work theo deadline
            running = false;
        }
        finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

Đây là snippet **chỉ minh họa lifecycle contract**, không phải production-ready consumer (chưa có actual consumer instance hoặc async completion). Với real client, callback chỉ nên được gọi khi shutdown phase thực sự hoàn tất hoặc có failure/timeout policy được xử lý; gọi callback sớm có thể khiến Spring destroy backend trước khi work xong.

Spring Boot graceful web shutdown dựa trên lifecycle phases; muốn clients đóng trước servers/brokers thì thiết kế dependencies/phases phù hợp, không đoán class declaration order.

### 11.4. ContextClosedEvent

`@EventListener(ContextClosedEvent.class)` có thể dùng để quan sát context bắt đầu đóng hoặc signal shutdown. Nhưng nếu tạo resource ở một static singleton bên ngoài Spring, event listener chỉ dừng nó khi thực sự được nạp vào context owner; không nên register nhiều listeners cùng stop một global resource đang phục vụ contexts khác.

### 11.5. Close order và dependent resources

Nếu background worker cần database để flush last message:
- Dừng việc nhận thêm tasks.
- Đợi in-flight workers.
- Close producer/client.
- Close database pool.
- Stop backing Testcontainers service.
- Cuối cùng release OS socket/process.

Trong Spring, dependency relationships/lifecycle phases giúp đạt ordering, nhưng custom ad-hoc threads có thể chạy ngoài sự kiểm soát. Đây là lý do nên inject **managed executor** thay vì gọi `new Thread` từ service.

## 12. Các tài nguyên phổ biến dễ bị bỏ quên

### 12.1. HikariDataSource / JDBC Connection

Lỗi thường gặp:
- Test code gọi `dataSource.getConnection()` rồi không `close()`.
- Context cached giữ pool hợp lệ, người học hiểu nhầm `HikariPool-1 housekeeper` là leak.
- Test tự tạo thêm `HikariDataSource` bằng `new` mà không gọi `close()`.
- Transaction bị treo và giữ physical connection quá lâu.
- Integration test với pool size 2 chạy 10 workers → timeout do contention.

Sửa:
- JDBC code dùng `JdbcTemplate` hoặc try-with-resources cho borrowed `Connection`.
- HikariDataSource là Spring bean nếu context sở hữu, để Spring destroy khi context close.
- Nếu pool do test tạo raw, test có trách nhiệm `close()`.
- Đo Hikari active/idle/pending/total connections và leakDetectionThreshold **khi cần chẩn đoán**, không coi setting leak detection là fix.
- Không đóng shared pooled DataSource từ một `@AfterEach`.

### 12.2. HTTP client và connection pool

Một HTTP client có connection pooling hoặc dispatcher threads:
- Apache HttpClient CloseableHttpClient cần close theo owner.
- OkHttpClient có Dispatcher/ConnectionPool cần shutdown/evict theo API và ownership phù hợp.
- Reactor Netty HttpClient có resources/event loops; custom ConnectionProvider/LoopResources phải dispose khi owned.
- Java `HttpClient` và Spring `RestClient` dùng request factory implementation cụ thể; không suy một close policy chung cho mọi factory.

Nếu client được tạo mỗi test:
- Tạo trong fixture.
- Close đúng API nếu client là Closeable.
- Đợi in-flight calls hoàn tất/cancel.
- Chỉ sau đó khẳng định threads/sockets được release.

Nếu client là singleton Spring bean, đóng theo bean lifecycle, không đóng sau mỗi method nếu context còn dùng.

### 12.3. Reactor scheduler

Phản ví dụ:

~~~java
Scheduler scheduler =
        Schedulers.newBoundedElastic(
                2, 100, "test-reactor-owned");

// Thiếu scheduler.dispose().
~~~

Snippet này cần Reactor dependency/imports, không thuộc Maven lab servlet. Với custom scheduler do test tạo:
- `dispose()` khi kết thúc scope.
- Nếu cần, verify disposal/termination theo Reactor API/version.
- Đừng gọi `Schedulers.shutdownNow()` toàn JVM để cleanup một scheduler test: nó có thể ảnh hưởng app/tests khác đang dùng global schedulers.
- Nếu resource là Reactor Netty loop/container-managed, kiểm owner tương ứng.

### 12.4. Servlet server và keep-alive

Embedded Tomcat/Jetty/Undertow phục vụ:
- Listener socket.
- Worker/event threads.
- Persistent HTTP connections.
- Graceful shutdown deadline.
- In-flight requests.

Khi Spring context close, Boot3.5 graceful shutdown được hỗ trợ và bật mặc định trên các embedded servers. Nó dừng nhận requests mới và cho in-flight work thời gian hoàn tất theo `spring.lifecycle.timeout-per-shutdown-phase`. Không coi vài milliseconds/seconds chuyển trạng thái bình thường trong grace period là leak.

### 12.5. Netty event loops

WebFlux/Reactor Netty dùng event-loop threads; có thể còn hiện tên `reactor-http-nio-*` khi context hoặc global Reactor resources vẫn sống. Phân biệt:
- Global Reactor resources được framework reuse;
- Custom `LoopResources`/`ConnectionProvider` do test tạo;
- In-flight TCP connections;
- Context/client resources chưa dispose.

Không gọi shutdown global schedulers trong một test độc lập nếu suite còn sử dụng chúng. Dùng test-scoped owner hoặc đúng context lifecycle.

### 12.6. Kafka/RabbitMQ listeners

Listener containers và consumer threads có thể chạy sau test method nếu context còn active:
- Kafka `@KafkaListener` có thể consume message test khác.
- Rabbit listener có thể drain queue.
- Auto-startup behavior từ config/profiles cần kiểm.
- Commit/ack/delivery asynchronous có thể tiếp tục sau assertion.

Khi test business logic thuần, tắt listener auto-start hoặc dùng profile. Khi test listener, dùng unique group/topic/queue, bounded waits và cleanup sau worker completion. Đóng consumer factories/listeners theo context; tránh class A stop shared broker khi class B còn dùng.

### 12.7. Testcontainers + context cache

Hai ownership models:
- JUnit `@Testcontainers` + `@Container`: lifecycle per-method/per-class.
- Spring Boot3.5 `@TestConfiguration @Bean @ServiceConnection`: container Spring-managed, lifecycle theo `ApplicationContext`.

Khi context được cache, Spring-managed container tránh “JUnit stop DB trước Spring DataSource”. Nếu dùng suite-level singleton container, không gắn `@Container` để JUnit stop class-level; xác định cleanup tại JVM/test-run owner. Reusable containers qua runs không thích hợp cho CI state isolation mặc định.

Không kết luận Docker container còn running sau class là leak nếu nó được Spring context cache quản lý và còn phục vụ tests khác.

### 12.8. WireMock / MockWebServer / embedded HTTP

Một WireMockServer tự tạo:

~~~java
WireMockServer server =
        new WireMockServer(options().dynamicPort());
server.start();

try {
    // exercise HTTP client using server.baseUrl()
}
finally {
    server.stop();
}
~~~

Snippet cần WireMock dependency và imports; không thuộc project Maven tối giản. Nếu server được tạo bởi JUnit extension đã quản lý lifecycle, đừng tự stop hai lần hay dùng port cố định vô cớ. Nếu Spring client bean dùng URL của server, đừng stop mock server trước khi client được done/context closed.

### 12.9. File handles và @TempDir

~~~java
try (InputStream stream =
             Files.newInputStream(path)) {
    // read
}
~~~

Không đóng stream có thể làm `@TempDir` cleanup thất bại, đặc biệt trên Windows nơi file lock semantics khác Unix. Dùng Files helper methods/try-with-resources; nếu mở ZIP filesystem, watch service, memory-mapped file hoặc Channel, đảm bảo close đúng API. Một path bị giữ bởi test process khác thì JUnit không tự sở hữu handle đó.

### 12.10. OS process tạo từ test

~~~java
Process process = new ProcessBuilder(
        "some-command").start();

try {
    // bounded interaction / drain output
}
finally {
    process.destroy();
    if (!process.waitFor(5, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor(5, TimeUnit.SECONDS);
    }
}
~~~

Snippet này là khung minh họa; chương trình `some-command` không tồn tại mặc định và không được chạy trong lab. Với OS child process phải:
- Tránh deadlock do không đọc stdout/stderr.
- Chờ exit trong deadline.
- Quản lý child processes do chương trình spawn tiếp.
- Không kill PID không thuộc test.
- Không gọi `destroyForcibly` trước khi thu diagnostic logs nếu đang điều tra.

### 12.11. File watcher / native library resources

`WatchService`, native handles, sockets, timers, compression streams hoặc RocksDB environments có thể giữ OS resources mà Java heap snapshot không cho thấy ngay. Dùng explicit close trong owner, monitor file descriptor count/native memory, và test nhiều lifecycle cycles để phát hiện leak tích lũy.

## 13. Vì sao test suites không ổn định khi có resource leak?

### 13.1. Leak tăng theo số lần chạy

Ví dụ mỗi test mở một `ExecutorService` 2 threads không shutdown:
- Sau 1 test, không thấy rõ.
- Sau 100 tests, 200 threads.
- CPU/context switching/memory tăng.
- Test chạy lâu hoặc JVM cannot create native thread.
- Surefire fork có thể chờ/halt ở cuối.

Một single test pass không chứng minh không leak. Cần repeated test/lifecycle loops và so **resource count sau owner close**.

### 13.2. Cổng cố định gây order dependence

Class A khởi động Tomcat port 8080 và giữ context cached; class B có khác cache key cũng cố port 8080 → bind conflict. Chạy B riêng PASS; chạy suite FAIL. Fix đúng:
- Dùng `RANDOM_PORT` cho tests không cần known port.
- Nếu test cần fixed port (external contract), isolate ownership/sequence/port allocation.
- Không đóng shared context bằng tay chỉ để class B chiếm cổng.
- Không xóa stale process của người khác mà chưa xác định owner.

### 13.3. Thread từ test trước mutate state của test sau

Bài A:
- Submit async write.
- Không đợi completion.
- `@AfterEach` delete fixture.

Bài B:
- Dùng cùng test database.
- Gặp row bất ngờ từ background worker của A.

Ở đây root bug là **work chưa hoàn tất trước cleanup**, không nhất thiết non-daemon JVM hang. Sửa bằng Future completion, listener acknowledgment/explicit barrier và namespace dữ liệu.

### 13.4. Context caching có thể che leak

Một executor bean hợp lệ sống trong context cache; nếu test leak tasks (mỗi test submit infinite job) thì sau 200 tests, queue đầy dù số threads không tăng nhiều. Cần kiểm:
- Queue depth/active count.
- Accepted/rejected tasks.
- Pending futures.
- Task deadlines.
- Cleanup per test.
- Context close behavior.

Một thread count ổn định không chứng minh executor không leak queued tasks.

### 13.5. Testcontainers resource starvation

Một suite tạo một PostgreSQL container **cho mỗi test method** hoặc tạo mỗi context mới bằng unique properties có thể cạn:
- Docker RAM/CPU.
- Container/network IDs.
- File descriptors.
- Database connections.
- CI run time.

Dùng context cache, Spring-managed containers, grouping và unique test data IDs khi có thể; nhưng không chia sẻ data không kiểm soát chỉ để tiết kiệm startup.

## 14. Graceful shutdown: đúng thời điểm và giới hạn

### 14.1. Spring Boot 3.5 web shutdown

Spring Boot 3.5 bật graceful shutdown mặc định cho embedded web servers được hỗ trợ. Khi application context đóng, web server tham gia `SmartLifecycle` stopping phase. Chính sách thời gian:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Ví dụ trên dành cho môi trường muốn có 20 giây cho phase. Trong unit/integration test nhỏ, không kéo grace period dài vô nghĩa; production cần thời gian đủ cho in-flight requests/side effects theo SLO.

`server.shutdown=immediate` đổi policy nhưng không tự giải quyết leak custom executor/socket. Dùng immediate shutdown chỉ khi requirement phù hợp, không để che test hang.

### 14.2. Shutdown hook không phải @AfterAll

Spring JVM shutdown hook xử lý context còn mở khi JVM kết thúc, nhưng `@AfterAll` chạy **trước** JVM shutdown hook nếu suite kết thúc bình thường. Một test muốn assert context resources đã đóng phải **tự tạo context riêng và close chủ động**, hoặc dùng dedicated lifecycle integration scenario.

### 14.3. Shutdown order của dependency graph

Nếu executor task đang dùng database khi context đóng:
- Một executor tắt/đợi tasks đúng thời điểm giúp task hoàn tất trước pool DB destroy.
- Nhưng nếu tasks bỏ qua interruption hoặc deadline vượt, cleanup có thể fail.
- Đừng để `@PreDestroy` block vô thời hạn.
- Với message consumers, stop nhận work mới trước; cho in-flight xử lý xong; rồi close clients/backends.

Spring-managed Testcontainers beans được Boot start trước dependent beans và stop sau khi dependent beans được destroy; dùng đúng owner để tránh client dùng backend đã chết.

### 14.4. Bounded awaits phải có policy

Ba chiến lược:
- **Graceful**: reject new work, complete queued/in-flight tasks within deadline.
- **Fast cancel**: interrupt/cancel tasks và roll back/reconcile partial work.
- **Drain and persist**: checkpoint work durable để restart resume.

Không có một `shutdownNow()` chung đảm bảo consistency. Chọn theo tính chất work và test cả failure-between-steps nếu quan trọng.

## 15. Dùng JUnit lifecycle đúng cách

### 15.1. @BeforeEach / @AfterEach

Tài nguyên sở hữu **mỗi method**:
- Tạo trong `@BeforeEach` hoặc trong test body.
- Cleanup trong `@AfterEach` hoặc try-with-resources.
- Use unique IDs/temp paths.
- Không ghi đè static resource shared với class khác.
- Đảm bảo background work complete trước cleanup.

JUnit callback thường chạy kể cả test assertion ném exception, nhưng không bảo đảm khi JVM/process bị force-kill, OS crash hoặc một infinite hang ngăn lifecycle đi tiếp.

### 15.2. @BeforeAll / @AfterAll

Tài nguyên sở hữu **test class**:
- Có thể start trong `@BeforeAll`.
- Stop trong `@AfterAll`.
- Với `@TestInstance(PER_CLASS)`/static lifecycle, quản lý field access đúng.
- Không stop resource Spring-managed **đang còn phục vụ cached context** ở class khác.

Một static `@Container` của JUnit có owner khác Spring TestContext cache. Đừng nhầm static field với lifetime toàn JVM.

### 15.3. Extensions và CloseableResource

JUnit 5 có extension store/resources có lifecycle theo store scope; một extension có thể lưu test resource và cleanup theo scope. Khi dùng custom extension:
- Xác định root/class/method store.
- Đảm bảo close callback được đăng ký và chạy.
- Tránh tạo nhiều clients nhưng chỉ một được dọn.
- Với context cached, không tự close resource mà Spring bean còn dùng.

### 15.4. @ResourceLock và parallel tests

`@ResourceLock` giúp JUnit điều phối tests cùng engine khi cùng resource key, ví dụ System properties/global port registry. Nó không khóa:
- Process/JVM khác.
- Docker host port thực sự.
- Arbitrary worker threads ngoài JUnit.
- Một Spring singleton shared đang bị background job truy cập.

Dùng resource lock khi test phải mutate global state; ưu tiên per-test unique ports/IDs tránh global shared state.

### 15.5. @Timeout và preemptive pitfalls

JUnit `@Timeout` có thể phát hiện method treo và tạo thread dump theo configuration. Nhưng timeout không tự bảo đảm:
- Task con đã dừng.
- Executor đã shutdown.
- DB transaction của worker rollback.
- Network client đóng.
- `@AfterEach` không còn race với worker.

Spring test-managed `@Transactional` dùng thread-bound context; preemptive timeout/executions ở thread khác có thể làm business operations thoát khỏi test transaction. Dùng bound completion/wait đúng boundary.

## 16. Chẩn đoán qua Spring Boot logs và actuator

### 16.1. Những log nên theo dõi

- `Tomcat started on port ...` hoặc server startup info.
- `Stopping service [Tomcat]` / web server shutdown.
- Hikari pool starting/closed.
- Task executor initializing/shutting down.
- Listener container start/stop.
- Testcontainers container id/start/stop.
- Spring TestContext cache hits/misses.
- Errors trong `@PreDestroy` hoặc shutdown callback.
- Surefire fork exit / elapsed duration.

Không assert exact log text/timestamp của framework như business contract; dùng logs để điều tra lifecycle.

### 16.2. Actuator metrics

Nếu project có Spring Boot Actuator/Micrometer:
- `jvm.threads.live`.
- Executor active/queued/completed metrics (nếu bind/observed).
- Hikari connections active/idle/pending/timeout.
- HTTP server connections/requests.
- Container/broker client metrics.
- Process open file descriptors trên OS/JVM hỗ trợ.

Các metrics có thể còn nonzero khi context đang sống hợp lệ. Đo **trend và sau owner close**; không yêu cầu thread count 0 trong test JVM.

### 16.3. Java ThreadMXBean

~~~java
ThreadMXBean mxBean =
        ManagementFactory.getThreadMXBean();

long[] threadIds = mxBean.getAllThreadIds();
ThreadInfo[] infos =
        mxBean.getThreadInfo(threadIds, 100);
~~~

Snippet cần imports `java.lang.management.*`. Nó cho snapshot threads/stack depths; không gồm mọi resource. Có thể gắn named thread prefix để lọc. Tránh assertion exact số threads JVM, vì JIT/GC/framework threads có thể thay đổi hợp lệ.

### 16.4. Leak trend test

Nếu một resource owner có start/close API:
- Warm up backend/context.
- Đo baseline threads/FD/connection pool.
- Lặp create→use→close 20–100 lần với unique IDs.
- Sau mỗi close, await termination.
- Assert no active owned resources/ports, not global count exact.
- Thu metrics/traces nếu trend tăng.
- Không tạo resource vô hạn trong default CI job.

Đây là **test vòng đời**, không phải memory benchmark chính xác. Với container-heavy resources, giảm repetitions và dùng dedicated CI job.

## 17. Cấu hình Maven Surefire và fork behavior

### 17.1. Surefire có thể tách process test

Surefire có `forkCount` và `reuseForks`; khi forked:
- Spring static TestContext cache nằm **trong fork JVM**, không share qua forks.
- Threads sống trong fork đó; Maven launcher ở PID khác.
- Một Docker container/process bên ngoài có thể sống vượt fork tùy owner.
- Shutdown hooks chạy lúc JVM thoát nếu không bị hard kill.
- Forced shutdown/timeout policy có thể làm log thiếu phần destroy cuối.

Lưu fork configuration trong bug report. “Sau @Test JVM không thoát” cần xác định **fork process nào**.

### 17.2. forkedProcessExitTimeoutInSeconds

Surefire có cấu hình giới hạn thời gian chờ forked JVM exit, ví dụ:

~~~xml
<configuration>
  <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
</configuration>
~~~

Đây là snippet thuộc `maven-surefire-plugin`, không phải `spring-boot-maven-plugin`. Một forced halt sau timeout **không chứng minh cleanup đúng**. Nó là safety mechanism tránh CI treo mãi; cần thu thread dumps, sửa owner và verify test/resource termination.

### 17.3. Rerun failures không chữa leak

`rerunFailingTestsCount` có thể rerun method sau fail, nhưng resource từ lần trước vẫn sống nếu cùng fork/context và cleanup không đúng. Khi rerun lần hai PASS, first failure vẫn là diagnostic evidence. Không dùng rerun làm workaround vĩnh viễn.

### 17.4. Process exit code và tests executed

Một suite báo exit code 0 có thể:
- Tất cả tests thực sự pass.
- Một số tests bị disabled/skipped.
- Fork bị timeout/forced cleanup theo plugin policy.
- External Docker resources vẫn chạy ngoài JVM.
- Một test fail ban đầu nhưng rerun pass (báo flake).

Kiểm Surefire XML counts, flake logs và resource owner sau build. Đừng kết luận toàn bộ port/thread/resource lifecycle đúng từ exit code duy nhất.

### 17.5. CI isolation

Với shared runner:
- Dùng dynamic ports.
- Dùng unique file/temp names.
- Namespace Docker containers/networks nếu cần.
- Dùng process-level clean-up hooks cho child processes do job sở hữu.
- Không stop unrelated processes vì port bị chiếm.
- Tránh reuse durable external DB state không kiểm soát.
- Có timeout hợp lý để giới hạn test run, thu diagnostics trước hard stop.

## 18. Các lỗi cụ thể và phương án sửa

### 18.1. TestPort 8080 xung đột

**Sai**:

~~~properties
server.port=8080
~~~

trong nhiều full integration tests với different contexts chạy song song. **Đúng khi không có requirement fixed port**: dùng `RANDOM_PORT`/`server.port=0`, inject actual port. Nếu cần fixed port, serialize ownership hoặc dedicated environment.

### 18.2. Test tự stop embedded server dù Spring còn dùng

**Sai**: gọi `webServer.stop()` từ một `@AfterEach` trong `@SpringBootTest(RANDOM_PORT)`; class khác reuse context và thấy port chết trong khi application beans/cache vẫn active.

**Đúng**: Để Spring quản lý server theo context; nếu cần test shutdown, tạo context riêng và close nó, hoặc dùng dedicated `@DirtiesContext` class không parallelize/shared.

### 18.3. Executor không shutdown

**Sai**:

~~~java
static final ExecutorService EXECUTOR =
        Executors.newFixedThreadPool(4);
~~~

trong utility class mà không có end-of-suite owner. Nó có thể tồn tại lâu và giữ non-daemon threads. **Đúng**: inject managed Spring `ThreadPoolTaskExecutor` hoặc tạo trong test scope với `finally`/`@AfterAll` shutdown+bounded await.

### 18.4. ScheduledExecutorService không shutdown

`Executors.newSingleThreadScheduledExecutor()` tạo thread và giữ scheduled tasks trong queue. Dừng scheduling mới, cancel periodic futures và shutdown scheduler đúng owner. Với Spring `ThreadPoolTaskScheduler`, để context quản lý và cấu hình shutdown policies.

### 18.5. @PreDestroy log lỗi nhưng bị bỏ qua

Nếu cleanup code ném exception, Spring có thể log warning và tiếp tục destroy các beans. Test có thể PASS mặc dù resource leaked. Trong lifecycle test quan trọng, assert **post-close state** và capture cleanup errors; đừng chỉ chờ context close không throw.

### 18.6. Hikari pool still running

Nếu context cached còn active thì bình thường. Nếu `DataSource` test tự tạo bằng `new HikariDataSource()` mà không close, đó là leak. Phân biệt bean ID/name và owner.

### 18.7. WireMock still listening

Nếu WireMock server là JUnit extension scoped class/root thì có thể còn sống cho scope đó. Nếu test tự gọi `server.start()` rồi không `server.stop()`, đó là leak. Dùng dynamic port và cleanup đúng scope; không reset mappings shared trong lúc parallel tests đang request.

### 18.8. Testcontainers Docker resource tồn dư

Nếu container thuộc cached context thì có thể được stop sau context close. Nếu manual singleton dùng cùng JVM, Docker cleanup theo singleton owner. Nếu reuse được bật qua runs local, container có thể cố ý tiếp tục chạy. Cần biết owner/policy trước khi gọi `docker stop`; **không** stop resource đang được suite khác sử dụng.

### 18.9. Reactor Netty scheduler còn tồn

Một custom Scheduler/LoopResources do test tạo mà không dispose có thể leak threads. Global reactor resources do framework quản lý có thể phục vụ nhiều contexts. Chỉ dispose resource do test own, không tắt global scheduler tùy tiện.

### 18.10. File có thể không xóa trên Windows

Nếu test giữ `FileInputStream`/`FileChannel` mở, `@TempDir` cleanup có thể fail vì Windows file locks. Dùng try-with-resources và dọn work complete trước khi test method return. Không hack retry deletion bằng sleep vô hạn.

### 18.11. SQL pool exhaustion

Hikari pending connections tăng có thể do chưa `Connection.close()`, transaction giữ lâu, pool size quá thấp hoặc DB down. Log metrics/stack của borrower, phân biệt leak với legitimate contention. Tăng pool size chỉ hợp lý sau khi root cause đã rõ.

### 18.12. JUnit @Timeout tạo thread khác

Với test transactions/worker threads, preemptive timeouts có thể khiến ThreadLocal context không propagate. Đảm bảo shutdown/transaction assertions sau completion và test exception stage rõ ràng.

### 18.13. Child processes orphan

Nếu test dùng `ProcessBuilder` để khởi động server process, chỉ destroy parent process có thể chưa stop children. Phải quản lý process tree/ownership theo OS, terminate gracefully, bounded wait và emergency force, không kill process có PID trùng vì reuse sau đó.

### 18.14. Logs sau test không chứng minh “leak”

Nếu một cached context vẫn chứa `@Scheduled` job hợp lệ, log có thể xuất hiện giữa tests. Điều cần hỏi là liệu job **được phép chạy trong test environment** hay không; nếu không, disable trigger/profile hoặc isolate. Không ép tất cả logs ngừng ngay sau `@Test`.

## 19. Bảng troubleshooting

| Hiện tượng | Nguyên nhân có thể | Bằng chứng cần thu | Fix đúng hướng |
| --- | --- | --- | --- |
| `Address already in use` | Fixed port hoặc socket không close | PID, LISTEN address, context key | RANDOM_PORT / close owner |
| Port mở sau method | Cached Spring context | TestContext cache stats | Không coi leak nếu context sống |
| Port mở sau explicit context.close | Listener/custom socket chưa close | OS PID/port + bean lifecycle | Fix destroy callback |
| Maven test xanh nhưng fork chờ | Non-daemon worker, shutdown hook | jcmd Thread.print | shutdown/await task |
| Worker thread WAITING | Idle managed executor hoặc leak | Owner + stack + context state | Chỉ xử lý nếu vượt lifetime |
| Executor queue tăng | Tasks không drain/completion | Queue/active metrics | Bounded queue + task completion |
| Scheduled logs sau test | Scheduler còn active | @EnableScheduling/profile/context | Disable/manual trigger |
| DB connection refused class sau | Container stopped sớm | Docker port/lifecycle + context cache | Managed Testcontainers |
| Hikari pool threads còn | Context cached hoặc pool raw không close | Bean ownership + Hikari metrics | Đúng scope close |
| Too many open files | Unclosed channels/sockets | lsof /proc/fd trend | try-with-resources |
| TempDir cleanup error | Stream/lock còn | file owner/Windows handles | close file resources |
| Test A làm B fail | Background work, stale shared state | Future completion / event timeline | Await + unique fixture |
| Reactor threads còn | Custom scheduler chưa dispose | Thread names + scheduler owner | dispose owned scheduler |
| Kafka consumer còn active | Listener trong context cached | Listener lifecycle, group/topic | Stop/namespace |
| WireMock port collision | Static server per class không stop | PID/port + JUnit extension scope | dynamic port/afterAll |
| @DirtiesContext làm test khác fail | Context closed during parallel use | TestContext logs | isolate/avoid parallel |
| Docker resources tăng | New container mỗi context | docker ps + context count | share with clear lifetime |
| Build xanh do skipped tests | No integration tests executed | Surefire reports | enforce executed count |
| Timeout cao vẫn fail | Owner leak/port wrong | Thread/port ownership | fix code, not timeout |
| Forced fork halt | Non-daemon/shutdown hook | Surefire shutdown logs | correct cleanup |
| Port TIME_WAIT | TCP teardown bình thường | socket STATE | Không coi là listener |
| Port rebind test flaky | OS reuse/external process race | binding address/PID | isolate + evidence |
| Cross-process tests xung đột | Global fixed port/shared resource | CI job PID/namespace | unique ports/resources |
| Shutdown close throws | Destroy callback lỗi | logs + post-close state | repair idempotent cleanup |
| JVM memory tăng | Heap/native leak hoặc retained data | JFR/heap/FD/threads | isolate actual resource type |

## 20. Quy trình điều tra từng bước

### Bước 1 — Định nghĩa expected lifetime

Điền vào bảng:

~~~text
Resource: port 18081 / thread diag-managed-1 / datasource...
Created by: test method? Spring bean? JUnit extension? Docker?
Used until: end of method? end of class? context close? JVM exit?
Close owner: who calls close/shutdown/stop?
Evidence: PID, thread dump, bean name, ContextClosedEvent?
Expected state after owner closes: ...
~~~

Không có định nghĩa owner thì không thể kết luận leak một cách khoa học.

### Bước 2 — Tái hiện trong scope hẹp

- Chạy test một mình.
- Chạy class.
- Chạy hai classes theo thứ tự.
- Chạy suite random/parallel nếu lỗi chỉ xuất hiện khi overlap.
- Ghi cổng động, context cache key, thread prefix, PID.
- Chỉ dùng test data synthetic, tránh production endpoints.

### Bước 3 — Xác định resource owner

- Java try-with-resources hay Spring bean?
- Testcontainers JUnit extension hay bean container?
- Executor do `@Async` infrastructure tạo hay `Executors.new...`?
- Context cached đang còn active?
- File stream có được close trước cleanup?
- OS process có là child của test process?

### Bước 4 — Thu diagnostics trước khi stop

- jcmd Thread.print.
- ss/lsof/netstat/Get-NetTCPConnection.
- Hikari/executor metrics.
- TestContext cache DEBUG logs.
- Maven Surefire/fork logs.
- Docker inspect/ps nếu liên quan.
- Socket state LISTEN vs TIME_WAIT.
- Root exception stack trace.

### Bước 5 — Sửa tại đúng owner

- Test-owned resource: `try-with-resources`/`finally`/`@AfterEach`.
- Class-owned resource: `@AfterAll`/JUnit extension close scope.
- Spring bean: `@PreDestroy`/`@Bean(destroyMethod)`/managed executor.
- ApplicationContext: close khi đúng test scenario; không tự đóng shared cached context.
- External container/broker: stop theo owner và chỉ khi consumers đã đóng.
- Background task: bounded completion/cancel + idempotent cleanup.

### Bước 6 — Kiểm fix bằng post-close assertion

- Context riêng closed: listener port released theo cùng address.
- Executor bean destroyed: `isShutdown`/`awaitTermination`.
- Ad-hoc pool: no pending work, `isTerminated`.
- Socket/stream: close state và resource có thể tái sử dụng.
- Data fixture: không bị worker mutate sau cleanup.
- Suite: không còn cross-class collision/hang.

### Bước 7 — Bảo vệ regression

- Thêm lifecycle test vào CI.
- Chạy nhiều lần nếu lỗi sporadic.
- Không bắt tất cả JVM threads/sockets phải bằng 0.
- Không dùng fixed sleep.
- Đo performance/resource trend.
- Ghi rõ unavoidable OS/window/network caveats.
- Đừng chỉ chấp nhận “mvn test PASS” nếu timeout/fork halt/skip che vấn đề.

## 21. Bài tập

1. Chạy `RandomPortAndManagedTaskTest`; lấy `@LocalServerPort` và xác định port thật.
2. Thử dùng `DEFINED_PORT` với `server.port=8080` trong hai contexts rồi phân tích collision; không giữ cấu hình này trong CI shared.
3. Dùng `ss -ltnp` hoặc `Get-NetTCPConnection` tìm PID của listener do test sở hữu.
4. Chạy `PortOnlyContextLifecycleTest` và giải thích vì sao context phải được tạo riêng.
5. Bỏ `context.close()` trong một nhánh thử nghiệm isolated, xem socket còn LISTEN; phục hồi cleanup ngay sau điều tra.
6. Đặt `server.address=127.0.0.1` và so với `0.0.0.0`, xem khác biệt socket binding/visibility.
7. Dùng `ServerSocket(0)` để OS cấp port, log actual port, verify close/rebind.
8. Chạy `ManagedResourcesLifecycleTest`, kiểm `ThreadPoolTaskExecutor` isShutdown sau context close.
9. Thêm một task có `CountDownLatch` chờ hữu hạn; quan sát shutdown với `setWaitForTasksToCompleteOnShutdown(true)`.
10. Thử task không xử lý interruption trong một **dedicated bounded process**, chụp thread dump; không đưa infinite task vào default suite.
11. Tạo `ExecutorService` trong test rồi shutdown bằng `finally`; kiểm `awaitTermination`.
12. Thay bằng `shutdownNow` sớm, giải thích những tasks có thể bị cancel và business side effects.
13. Tạo một `@Bean(destroyMethod="close")` sở hữu `ServerSocket`, verify socket closed sau context close.
14. Thêm `@PreDestroy` cho một custom client, kiểm close idempotent.
15. Thiết kế `SmartLifecycle` wrapper cho một message consumer, xác định phase và completion callback.
16. Bật `@EnableScheduling` ở profile riêng, quan sát background log trong cached context.
17. Tắt scheduler trigger trong test profile, gọi job method thủ công và assert DB state.
18. Thêm `@Async` service và `CompletableFuture`, dùng bounded await trước test cleanup.
19. Thử class `@DirtiesContext(AFTER_CLASS)`, đo context startup cost và listener stop; không chạy parallel với class dùng same context.
20. So sánh một Spring-managed Testcontainers bean với JUnit `static @Container` về close order.
21. Tạo một HikariDataSource raw test-owned, verify close khi fixture kết thúc.
22. Tạo JDBC `Connection` với try-with-resources và kiểm pool active count sau operation.
23. Viết test mở file handle trong `@TempDir` rồi quên close trong nhánh học tập; thử cleanup trên Windows và sửa.
24. Dùng `jcmd Thread.print` tìm thread tên `ad-hoc-test-owned` trong lúc task chạy; sau cleanup xác nhận không còn hoạt động.
25. Chạy JFR 60 giây khi leak reproduce; so thread starts/ends trước/sau.
26. Phân biệt một socket `TIME_WAIT` với `LISTEN` trên output `netstat`.
27. Thử một WireMockServer dynamic port và stop trong `@AfterAll` đúng class owner.
28. Với Redis/Kafka shared container, dùng unique key/topic/group và đóng listeners/clients theo scope.
29. Chạy Maven Surefire với nhiều forks; giải thích context cache per-JVM và OS process/PID differences.
30. Kiểm Surefire shutdown timeout config, báo cáo forced process halt thay vì coi nó là PASS cleanup.
31. Thêm metrics cho executor active/queued tasks và Hikari active/idle connections.
32. Chạy lifecycle create/use/close 50 lần với một test-owned resource nhỏ, đo FD/thread trend.
33. Viết một ADR xác định owner và teardown của mọi external client/scheduler/socket trong module.
34. Review một test `Thread.sleep(3000)` rồi assert negative async outcome; thay bằng completion signal.
35. Thu thập bug report gồm PID, port state, thread stack, context key, owner lifetime và fix verification.

## 22. Checklist trước khi merge

- [ ] Đã phân biệt method ended, class ended, context closed và JVM exit?
- [ ] Mỗi resource có một owner và shutdown policy xác định?
- [ ] Spring TestContext cache có thể giữ resource hợp lệ giữa tests?
- [ ] Không assert port/thread mất ngay khi một `@SpringBootTest` method kết thúc?
- [ ] Embedded server tests dùng `RANDOM_PORT` nếu không cần fixed port?
- [ ] Không hard-code host port của Testcontainers?
- [ ] Có kiểm bind address và TCP state LISTEN vs TIME_WAIT?
- [ ] Port collision đã xác định PID owner trước khi kill?
- [ ] Không đóng shared cached context trong `@AfterEach`?
- [ ] Nếu cần kiểm server shutdown, đã tạo isolated context và close đúng?
- [ ] Java `ServerSocket`/file streams có try-with-resources?
- [ ] `ExecutorService` test-created được shutdown/awaitTermination với deadline?
- [ ] Futures/tasks được await/cancel trước fixture cleanup?
- [ ] Không dùng `Thread.sleep` để giả đồng bộ hóa?
- [ ] Threads có prefix giúp tìm owner trong jcmd/stack dump?
- [ ] Không dùng daemon flag như một cách sửa resource leak?
- [ ] Spring `ThreadPoolTaskExecutor` bean có shutdown policy phù hợp?
- [ ] `@PreDestroy`/`DisposableBean`/`destroyMethod` được dùng đúng owner?
- [ ] `SmartLifecycle` stop order không phá dependent resources?
- [ ] `@Scheduled` có được disable/gate nếu test không cần?
- [ ] `@Async` có completion signal/timeout/exception handling?
- [ ] HikariDataSource/JDBC connections được close đúng scope?
- [ ] HTTP client/Reactor scheduler/broker listener được close/dispose khi owned?
- [ ] Testcontainers lifecycle phù hợp Spring context cache?
- [ ] Không dùng `@DirtiesContext` đại trà để chữa symptom?
- [ ] Parallel tests không cleanup global shared resources của nhau?
- [ ] Có snapshot jcmd/OS ports/FD khi debug hang thực?
- [ ] Có phân biệt live JVM thread với OS child process/Docker resource?
- [ ] Không lộ secrets/customer data trong thread dumps/logs/artifacts?
- [ ] CI không che leak bằng forced fork halt hoặc all tests skipped?
- [ ] Có test post-close state thay vì chỉ log “closing”?
- [ ] Maven/Surefire executed counts và actual results được xác nhận khi chạy?
- [ ] Có regression test bảo vệ failure mode đã tìm ra?
- [ ] Không biến một test học lifecycle thành deliberate infinite hang của toàn suite?

**Kết luận:** Một port, thread hoặc connection còn tồn tại **sau một test method** chưa đủ để gọi là leak. Spring Boot/Spring TestContext cố ý cache `ApplicationContext` và giữ server, executor, DataSource và listeners sống để test khác dùng lại. Leak thật là tài nguyên sống **vượt lifetime của owner hoặc thiếu đường close/destroy**. Cách debug đúng là xác định owner → xác định expected release point → chụp port/PID/thread/resource evidence → sửa lifecycle của owner → verify sau close. Với resource test-owned, dùng try-with-resources/finally; với Spring-managed beans, dùng lifecycle/destroy callbacks; với async, dùng bounded waits và completion signals; với embedded server, ưu tiên random port và context-scoped shutdown. Đừng tăng timeout, gọi kill, bật daemon, lạm dụng `@DirtiesContext` hay chờ bằng sleep để che thiết kế ownership sai.

## 23. Tài liệu chính thức

- Spring Framework 6.2 — TestContext Context Caching (scope, default 32, LRU, shutdown hook): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — @DirtiesContext semantics and context close: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — Parallel Test Execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.5 — Testing Spring Boot Applications, RANDOM_PORT and @LocalServerPort: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Graceful Web Server Shutdown and lifecycle timeout: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — Task Execution and Scheduling / shutdown configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Testcontainers, managed @Bean + @ServiceConnection lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — ThreadPoolTaskExecutor API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — ExecutorConfigurationSupport shutdown/await policies: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Framework 6.2 — SmartLifecycle API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Java SE 17 — ExecutorService shutdown and awaitTermination: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — ServerSocket and AutoCloseable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java SE 17 — ThreadMXBean and thread inspection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- JDK — jcmd diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- JDK — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/
- Maven Surefire — Forked JVM Shutdown, forced exit timeout: https://maven.apache.org/surefire/maven-surefire-plugin/examples/shutdown.html
- Maven Surefire — Fork options and parallel execution: https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- JUnit Jupiter 5 — Test lifecycle and @TempDir: https://docs.junit.org/5.12.0/user-guide/#writing-tests-built-in-extensions-TempDirectory
- Testcontainers Java — JUnit 5 lifecycle: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — Singleton Containers: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/#singleton-containers
