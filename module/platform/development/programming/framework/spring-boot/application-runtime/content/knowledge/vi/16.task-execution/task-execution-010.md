# Ranh giới giữa quản lý vòng đời và thiết kế xử lý đồng thời chuyên sâu trong Spring Boot

## 1. Vấn đề: “Spring đã quản lý thread” không có nghĩa “chương trình đã đúng về concurrency”

Một ứng dụng Spring Boot có thể chạy tác vụ đồng thời bằng `@Async`, `@Scheduled`, `TaskExecutor`, `TaskScheduler`, `CompletableFuture`, `ExecutorService` hoặc một message consumer chạy nền. Spring giúp bạn **đăng ký thành phần, cấp phát executor, kích hoạt một số callback và đóng tài nguyên cùng `ApplicationContext`**. Nhưng Spring không tự động giải quyết mọi vấn đề phát sinh khi hai hoặc nhiều công việc chạm vào cùng dữ liệu.

Ví dụ đơn giản:

```java
private int total;

public void addOne() {
    total++;
}
```

Nếu hai task cùng gọi `addOne()`, biểu thức `total++` không phải một thao tác nguyên tử: nó gồm đọc, tính và ghi. Việc đặt class trong `@Service`, dùng `@Async` hoặc để Spring tự đóng executor **không** làm phép tăng này tự nhiên an toàn trước tranh chấp. Chương trình có thể bị **lost update** dù không rò rỉ thread và shutdown hoàn toàn sạch.

Ngược lại, bạn có thể dùng `AtomicInteger` để tăng đúng trong một JVM nhưng lại quên đóng worker khi dừng ứng dụng. Khi đó **logic đồng thời tại runtime** có thể đúng còn **quản lý vòng đời** lại sai.

Hai nhóm trách nhiệm phải được kiểm chứng độc lập:

- **Quản lý vòng đời (lifecycle management):** khi nào tài nguyên được tạo, start, nhận việc, dừng nhận việc, chờ hoàn thành, đóng và giải phóng.
- **Thiết kế xử lý đồng thời (concurrency design):** khi các task chạy xen kẽ, bất biến dữ liệu nào được giữ; ai sở hữu trạng thái; thứ tự nào phải được bảo đảm; quá tải xử lý ra sao; hủy, lỗi và retry có thể tạo kết quả gì.

**Nguyên tắc chính:** Spring quản lý *khung tồn tại và sử dụng tài nguyên*. Ứng dụng chịu trách nhiệm *tính đúng đắn của công việc chạy trên tài nguyên đó*. Hai phần cần phối hợp, nhưng không được coi một phần thay thế phần kia.

## 2. Bảng ranh giới trách nhiệm

| Câu hỏi | Lifecycle / Spring Boot hỗ trợ | Concurrency chuyên sâu vẫn phải thiết kế |
|---|---|---|
| Executor được tạo lúc nào? | `@Bean`, auto-configuration, init/destroy bean | Chọn đúng mô hình pool/worker và tài nguyên cho workload |
| Task được submit vào đâu? | `TaskExecutor`, `@Async`, `@Scheduled`, qualifiers | Phân phối, điều tiết tải, deadline và quyền sở hữu công việc |
| Bean bắt đầu hoạt động lúc nào? | `SmartLifecycle.start()`, `ApplicationRunner`, events | Khởi tạo shared state và công bố an toàn cho các luồng |
| Hai task cùng sửa dữ liệu? | Framework không tự thêm khóa nghiệp vụ | `synchronized`, lock, atomic, immutable data, actor hoặc transaction phù hợp |
| Task phải chạy theo thứ tự A rồi B? | Có thể chọn một executor/scheduler và phase start-stop | Ràng buộc happens-before, hàng đợi, completion dependency, xử lý reorder |
| Queue đầy thì sao? | Cấu hình capacity và rejection policy | Backpressure, chấp nhận từ chối, retry và kiểm soát mất việc |
| Task lỗi thì ai biết? | `Future`/`CompletableFuture`, handler cho `@Async` | Chính sách lỗi, idempotency, retry, dead-letter và quan sát |
| Context đang đóng thì sao? | `SmartLifecycle.stop(Runnable)`, destroy callbacks, shutdown timeout | Ngừng intake, drain/flush, cancellation và thứ tự đóng dependency |
| Đã nhận message thì phải xử lý đúng một lần? | Không có bảo đảm chỉ từ lifecycle của bean | Ack, checkpoint, deduplication, transactions và semantics broker |
| Chạy nhiều replicas có tránh đụng nhau không? | Mỗi instance có context và executor riêng | Lock phân tán, partition assignment, idempotency, fencing và lease |
| Bảo mật/ngữ cảnh request qua thread khác? | Có thể dùng `TaskDecorator` hoặc cơ chế propagation được cấu hình | Xác định context nào cần truyền, xóa đúng lúc và tránh rò rỉ dữ liệu |

Bảng này không nói Spring *không có công cụ concurrency*. Ngược lại, Spring cung cấp nhiều abstraction hữu ích. Ranh giới nằm ở chỗ **framework cung cấp cơ chế thực thi**, còn **nghiệp vụ quyết định cơ chế đó phải bảo toàn điều gì**.

## 3. Phân biệt các tầng xử lý trong một ứng dụng

Có thể hình dung bốn tầng từ ngoài vào trong:

```text
Tầng A — Quy trình của nền tảng
  JVM/process, container, orchestration, readiness, SIGTERM
                         |
Tầng B — Vòng đời Spring ApplicationContext
  bean creation, refresh, SmartLifecycle, @PreDestroy
                         |
Tầng C — Hạ tầng thực thi task
  TaskExecutor, ThreadPoolTaskExecutor, TaskScheduler, queue
                         |
Tầng D — Thuật toán và dữ liệu nghiệp vụ
  ordering, mutex/atomic, dedupe, retry, transaction, state machine
```

**Tầng A** có thể gửi `SIGTERM` và chờ JVM thoát; nó không hiểu một giao dịch nghiệp vụ đã commit chưa. **Tầng B** phát tín hiệu đóng context; nó không hiểu task nào phải được xử lý theo đúng thứ tự. **Tầng C** cung cấp worker threads và queue; nó không biết việc nhận hai lần cùng event có hợp lệ không. **Tầng D** mới là nơi định nghĩa bất biến và hậu quả khi công việc thất bại.

Một luồng shutdown sạch có thể lần lượt thông báo từ A xuống B và C, sau đó C cho D thời gian hoàn thành công việc. Nhưng nếu D không hỗ trợ cancellation, idempotency hoặc deadline, lifecycle chỉ có thể chờ đến hết một khoảng thời gian — **nó không thể tự làm logic nghiệp vụ an toàn**.

## 4. Các mốc Spring Boot ảnh hưởng đến task

Trong Spring Boot 3.3, một lần `SpringApplication.run(args)` đi qua các bước chính:

```text
Chuẩn bị Environment
       |
Tạo ApplicationContext và bean definitions
       |
refresh()
  +--> tạo những bean cần thiết
  +--> SmartLifecycle auto-start theo phase
       |
ApplicationStartedEvent
       |
ApplicationRunner / CommandLineRunner
       |
ApplicationReadyEvent
       |
ReadinessState.ACCEPTING_TRAFFIC (mặc định)
       |
Ứng dụng chạy
       |
ApplicationContext.close() / shutdown hook
  +--> stop SmartLifecycle theo phase
  +--> destroy bean, đóng resources
       |
JVM kết thúc (khi không còn non-daemon threads)
```

**Không đồng nhất các mốc:**

- `@PostConstruct` chạy khi **một bean** được khởi tạo, không chứng minh toàn ứng dụng Ready.
- `SmartLifecycle.start()` diễn ra theo điều phối lifecycle khi context refresh; thích hợp cho component hoạt động lâu dài.
- `ApplicationStartedEvent` được phát sau refresh nhưng trước các runner.
- `ApplicationRunner` và `CommandLineRunner` dành cho việc startup dùng bean đã có, phải hoàn thành trước Ready.
- `ApplicationReadyEvent` đến sau runners, **không** chứng minh mọi background task đã hoàn thành.
- `@PreDestroy` và `DisposableBean.destroy()` liên quan hủy bean; chúng không tự cung cấp một giao thức drain có thứ tự như `SmartLifecycle.stop(Runnable)`.

Một task tự submit trong runner mà không đợi kết quả vẫn có thể **tiếp tục chạy sau `ApplicationReadyEvent`**. Runner kết thúc không có nghĩa task nó vừa nộp đã xong. Nếu công việc là điều kiện để nhận traffic, runner phải đợi/kiểm tra hoàn tất theo deadline hợp lý hoặc dùng cơ chế readiness thích hợp.

## 5. @Async, TaskExecutor và @Scheduled làm được gì?

### 5.1. @Async là chuyển lời gọi sang executor

Spring Framework có annotation `@Async`, nhưng cần bật cơ chế async processing, thông thường bằng `@EnableAsync`. Khi một bean khác gọi **qua Spring proxy** vào phương thức `@Async` hợp lệ, Spring chuyển việc thực thi sang một executor:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
@Service
public class ReportService {

    @Async
    public CompletableFuture<String> build(String input) {
        return CompletableFuture.completedFuture(
                "report-for-" + input);
    }
}
```

Các đoạn trên là **mã tích hợp**, cần các imports Spring/Java, component scan và cấu hình executor phù hợp. Phương thức `@Async` trả `CompletableFuture` cho phép caller nhận kết quả/lỗi. Dù nội dung `build` rất nhanh, việc đổi sang luồng khác vẫn có overhead và không đem lại lợi ích tự động cho CPU-bound code.

Các điều **không** do `@Async` tự làm:

1. Không biến trường `int` dùng chung thành thread-safe.
2. Không giải quyết self-invocation: gọi `this.build(...)` trong cùng target sẽ bỏ qua proxy-based advice.
3. Không bảo đảm task sẽ hoàn thành trước `ApplicationReadyEvent`.
4. Không tự động bảo đảm propagation của mọi `ThreadLocal`, transaction hoặc security context.
5. Không tạo deadline, retry, idempotency hay thứ tự xử lý message nếu ứng dụng chưa thiết kế.
6. Không bảo đảm caller nhìn thấy exception nếu method `@Async` trả `void`: lỗi cần được xử lý qua `AsyncUncaughtExceptionHandler`/logging phù hợp; với future, caller cần kiểm tra completion.

### 5.2. TaskExecutor là cơ chế cấp luồng, không phải thuật toán

Spring `TaskExecutor` trừu tượng hóa việc gọi `execute(Runnable)`; `ThreadPoolTaskExecutor` cung cấp một pool có thể cấu hình. Spring Boot 3.3 có thể tự cấu hình `AsyncTaskExecutor` khi không có executor phù hợp do ứng dụng khai báo:

- Java 17 theo chế độ platform threads mặc định: thường dùng `ThreadPoolTaskExecutor`.
- Java 21+ với `spring.threads.virtual.enabled=true`: có thể dùng `SimpleAsyncTaskExecutor` dựa trên virtual threads.
- Tên bean, loại executor và việc tự động wiring cho `@Async`/Spring MVC/GraphQL có những quy tắc riêng khi ứng dụng tự khai báo một hoặc nhiều `Executor`; **không nên đoán từ tên “executor” chung**.

Ví dụ cấu hình pool của Spring Boot 3.3:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=32
spring.task.execution.thread-name-prefix=jobs-
```

Những thuộc tính này áp dụng cho **executor auto-configured phù hợp**, không phải mọi `ExecutorService` được tạo bằng `Executors.newFixedThreadPool`. Queue có giới hạn giúp dễ quan sát ngưỡng quá tải. Với `ThreadPoolExecutor`, pool có thể ưu tiên xếp việc vào queue sau khi đạt core size trước khi tăng đến max size, vì vậy **chỉ đặt max-size lớn không bảo đảm pool sẽ tăng nếu queue không giới hạn**.

### 5.3. @Scheduled quyết định lúc kích hoạt, không quyết định đồng thời an toàn

`@Scheduled` thường dùng cùng `@EnableScheduling`:

```java
@Component
public class PollingJob {

    @Scheduled(fixedDelay = 5000)
    public void poll() {
        // Bắt đầu một lần kiểm tra theo lịch.
    }
}
```

Đây là snippet tích hợp cần import và scheduling enabled. `fixedDelay` đặt khoảng chờ **sau khi một lần thực thi kết thúc** (đối với cơ chế scheduling đồng bộ thông thường); `fixedRate` diễn tả tần suất theo mốc thời gian. Nếu method lại tự submit công việc bất đồng bộ và trả về ngay, độ dài của **công việc thực** có thể không trùng thời điểm method lịch biểu kết thúc.

`@Scheduled` không tự cung cấp **distributed singleton**: hai replicas triển khai cùng ứng dụng có thể cùng chạy job theo lịch. Nếu việc chỉ được chạy một lần trong toàn hệ thống, cần điều phối phân tán hoặc dùng một job runner có cơ chế lease/leader election phù hợp.

## 6. Khi nào nên dùng SmartLifecycle?

`SmartLifecycle` phù hợp với **thành phần hoạt động lâu dài**, ví dụ một worker nhận message liên tục hoặc một consumer kết nối broker. Nó cung cấp:

```java
void start();
void stop();
void stop(Runnable callback);
boolean isRunning();
int getPhase();
boolean isAutoStartup();
```

Các chữ ký trên là danh sách khái niệm từ `SmartLifecycle`, `Lifecycle` và `Phased`. Không sao chép chúng thành một interface mới; sử dụng implementation Spring có sẵn.

Ý nghĩa:

- `start()` thiết lập tài nguyên và nhận việc; không nên chạy một vòng lặp vô hạn **ngay trên thread gọi start**.
- `isRunning()` phản ánh trạng thái để Spring điều phối, không phải một lock chống race.
- `getPhase()` điều khiển thứ tự: **start phase thấp trước cao; stop phase cao trước thấp**. `SmartLifecycle` mặc định dùng phase `Integer.MAX_VALUE`, nếu không có lý do cụ thể có thể giữ mặc định.
- `stop(Runnable)` cho phép dừng bất đồng bộ, nhưng **callback phải được gọi sau khi thực sự dừng**; nếu gọi sớm, Spring có thể đóng bean thấp phase mà worker vẫn dùng.

Một state machine nên phân biệt ít nhất:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                  |
                  +-> FAILED
```

Trong đó **RUNNING** không có nghĩa tất cả dữ liệu nghiệp vụ đều hợp lệ; nó chỉ là trạng thái tài nguyên. Phải thiết kế rõ công việc được nhận ở `RUNNING`, cách từ chối tại `STOPPING`, và ai hoàn tất những task đang dở.

### Vì sao lifecycle phase không thay thế synchronization?

Giả sử Bean A phase 10 và Bean B phase 20. Spring start A trước B rồi stop B trước A. Điều đó **không** bảo đảm mọi method invocation từ B tới A sẽ không race nếu B tạo nhiều thread gọi A đồng thời. Phase chỉ điều phối **mốc start/stop của component**, không thêm mutual exclusion trong phương thức của A.

Một quan hệ `@DependsOn` cũng không cung cấp khóa cho dữ liệu mutable; nó chỉ tham gia dependency ordering. Đừng nhầm thứ tự khởi tạo bean với thứ tự thay đổi trạng thái giữa hai tasks.

## 7. Những bài toán concurrency nằm ngoài lifecycle

### 7.1. Atomicity: một thao tác nghiệp vụ có bị chia nhỏ không?

`counter++` là read-modify-write; hai thread có thể đọc cùng một giá trị rồi ghi đè kết quả nhau:

```text
Counter ban đầu = 5

Thread A đọc 5
Thread B đọc 5
Thread A ghi 6
Thread B ghi 6

Kết quả cuối = 6, trong khi cần 7
```

Có thể dùng `AtomicInteger.incrementAndGet()` cho một bộ đếm đơn giản trong một JVM:

```java
private final AtomicInteger counter = new AtomicInteger();

public int addOne() {
    return counter.incrementAndGet();
}
```

**Không được suy rộng** rằng mọi thao tác nhiều bước đã an toàn chỉ vì từng field là atomic. Ví dụ cần chuyển một lượng tiền từ hai số dư hoặc kiểm tra rồi cập nhật hai cấu trúc khác nhau: phải bảo toàn **bất biến toàn thao tác**, có thể cần lock, transaction hoặc mô hình sở hữu trạng thái khác.

### 7.2. Visibility: một thread có nhìn thấy cập nhật của thread khác?

Một cờ shutdown không được đồng bộ có thể bị đọc cũ:

```java
// Không phải ví dụ khuyến nghị khi chia sẻ qua các thread:
private boolean stopRequested;
```

Với cờ độc lập, `volatile boolean` hoặc `AtomicBoolean` giúp thiết lập visibility/happens-before phù hợp:

```java
private volatile boolean stopRequested;
```

Nhưng `volatile` **không** biến `count++` thành atomic. Một cấu trúc bất biến được truyền qua `BlockingQueue` hoặc `CompletableFuture` cũng có thể giúp thiết kế đường truyền dữ liệu có quan hệ đồng bộ rõ ràng.

### 7.3. Ordering: hoàn tất khác thứ tự submit

Với pool nhiều worker:

```text
submit A (mất 2 giây)
submit B (mất 20 ms)

Complete B
Complete A
```

Thứ tự submit **không** kéo theo thứ tự hoàn tất. Nếu nghiệp vụ đòi xử lý tuần tự theo `accountId` hoặc `aggregateId`, chọn một mô hình rõ ràng: single-consumer queue, partition theo key, per-key serial executor, hoặc lưu event với sequence/version kiểm tra khi xử lý. Không chỉ đặt `@Order` lên hai bean runner hoặc thay đổi lifecycle phase.

### 7.4. Deadlock: khóa hoặc Future chờ lẫn nhau

Hai task có thể giữ hai khóa theo thứ tự ngược nhau:

```text
Thread A: lock X -> đợi lock Y
Thread B: lock Y -> đợi lock X
```

Spring vẫn có thể tạo executor và đóng context theo đúng trình tự nhưng không sửa được vòng chờ này. Cần thiết kế **thứ tự lock nhất quán**, tránh giữ lock khi gọi I/O hoặc callback có thể re-enter và sử dụng timeout/cancellation thích hợp.

**Thread pool starvation deadlock** cũng có thể xảy ra nếu task trên pool một worker submit một task khác vào chính pool rồi gọi `future.get()` để chờ: worker duy nhất đang bị chặn, task được chờ không có thread để chạy. Đây là lỗi thiết kế điều phối công việc, không phải lỗi bean lifecycle.

### 7.5. Shared data: ConcurrentHashMap không biến mọi chuỗi thao tác thành atomic

`ConcurrentHashMap` an toàn cho các thao tác nhất định của map. Nhưng đoạn:

```java
if (!map.containsKey(key)) {
    map.put(key, newValue);
}
```

vẫn là **check-then-act** gồm hai lời gọi có thể bị xen vào giữa. Khi cần thêm nếu chưa tồn tại, dùng `putIfAbsent` hoặc `computeIfAbsent` phù hợp và hiểu semantics của mapping function. Với ràng buộc across nhiều tài nguyên, phải thiết kế bất biến rộng hơn.

## 8. Backpressure: queue không giới hạn có thể biến lỗi thành tăng bộ nhớ

Giả sử service nhận 1.000 task/giây nhưng executor xử lý trung bình 200 task/giây. Nếu queue không giới hạn, mỗi giây backlog có thể tăng khoảng 800 task, cuối cùng làm tăng latency, heap và rủi ro OOM.

`ThreadPoolTaskExecutor` cho phép điều chỉnh pool, queue capacity và rejection. Nhưng cấu hình queue **không tự quyết định chính sách nghiệp vụ** khi đầy:

| Chính sách | Ý nghĩa kỹ thuật | Điều cần quyết định |
|---|---|---|
| Reject nhanh | `RejectedExecutionException` hoặc `TaskRejectedException` tùy API | Caller retry lúc nào? Trả 429/503 hay lỗi nghiệp vụ? |
| Chờ capacity | Caller đợi cho đến khi có chỗ | Deadline tối đa và nguy cơ giữ hết request threads? |
| Caller-runs | Caller trực tiếp xử lý việc bị từ chối nếu policy hỗ trợ | Có chặn event loop hoặc làm timeout request không? |
| Drop | Bỏ một task khỏi queue hoặc không nhận task | Có quyền làm mất việc? Ai biết để phục hồi? |
| Persist ngoài JVM | Ghi vào broker/database rồi xử lý sau | Ack/transaction/deduplication và tính bền vững thế nào? |

Không có policy nào luôn tốt. Với xử lý email marketing có thể chấp nhận queue/retry; với thanh toán phải đặc biệt coi trọng idempotency và durability. Với UI request có deadline ngắn, chờ queue quá lâu có thể tệ hơn từ chối rõ ràng.

**Tách ba giới hạn**: số worker đồng thời, số task được xếp hàng và tổng thời gian từ submit đến completion. Một pool nhỏ nhưng queue lớn có thể trông “ổn định” khi CPU thấp mà latency vẫn không chấp nhận được.

## 9. Cancellation, interruption và deadline

Java cung cấp `Thread.interrupt()`, `Future.cancel(...)`, `ExecutorService.shutdown()`, `shutdownNow()` và `CompletableFuture`. Không một API nào trong số đó bảo đảm rằng một công việc bất kỳ sẽ lập tức ngừng và hoàn trả trạng thái như trước khi bắt đầu.

- `ExecutorService.shutdown()` ngừng nhận task mới, cho task đã nộp có cơ hội hoàn thành; nó **không đợi** completion.
- `awaitTermination(...)` chờ executor kết thúc đến một thời hạn cụ thể.
- `shutdownNow()` cố yêu cầu dừng các task đang chạy (thường bằng interrupt), trả những task chưa bắt đầu, nhưng không thể ép một task bỏ qua interrupt phải kết thúc.
- `Future.cancel(true)` yêu cầu hủy theo semantics của implementation; nó không phải rollback database.
- `CompletableFuture.cancel(...)` không nên được giả định tự ngắt một phép I/O bên dưới nếu implementation không liên kết cancellation đến resource thực.

Ví dụ một task tôn trọng interrupt:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát khỏi vòng và thực hiện cleanup thích hợp.
}
```

Đây là **snippet tích hợp**; `doOneUnitOfWork()` phải tồn tại, có semantics về interruption và xử lý lỗi rõ ràng. Không dùng vòng vô hạn trong constructor hay `@PostConstruct`. Trong hệ thống thực, các lời gọi network/database còn cần timeout riêng; một timeout của `SmartLifecycle` **không tự hủy** HTTP request.

### Deadline toàn tuyến

Nếu request chỉ còn 1 giây cho toàn bộ xử lý mà bạn submit task mất tối đa 4 giây, caller có thể timeout trước khi task hoàn thành. Task tiếp tục chạy sau khi client đã bỏ đi, có thể ghi dữ liệu không mong muốn.

Một thiết kế tốt xác định:

1. Deadline tuyệt đối hoặc thời gian còn lại.
2. Queue wait tối đa.
3. Thời gian I/O và xử lý.
4. Cancellation có thể lan đến đâu.
5. Việc nào phải hoàn tất dù caller đã hủy (ví dụ commit có tính bền vững).
6. Cơ chế ghi nhận kết quả cuối và idempotency nếu client retry.

## 10. Transaction, ThreadLocal, MDC và SecurityContext

Một nguồn lỗi thực tế: ứng dụng giả định mọi thứ ở cùng request thread sẽ tự xuất hiện trong worker thread.

`@Transactional` theo mô hình Spring phổ biến gắn transaction context với **thread đang thực thi**. Khi từ một method transactional bạn submit một `Runnable` sang thread khác, **không được mặc định cho rằng transaction hiện tại được truyền sang worker**. Nếu worker thực hiện thao tác dữ liệu cần transaction, hãy xác định ranh giới transaction mới ở phía worker bằng bean/proxy phù hợp hoặc một thiết kế xử lý message riêng.

Tương tự:

- MDC/tracing context có thể dựa trên `ThreadLocal`. Chuyển thread mà không propagation có thể làm mất trace ID.
- Security context cần được truyền theo cơ chế bảo mật phù hợp nếu worker cần xác thực danh tính; không sao chép mọi thread-local một cách mù quáng.
- Request-scoped beans có thể không hợp lệ khi request đã kết thúc.
- `ThreadLocal` không được làm sạch đúng cách trong thread pool có thể gây **rò rỉ dữ liệu giữa request**.

Spring có `TaskDecorator` và những tích hợp tracing/security hữu ích, nhưng decorator chỉ giải quyết phần **chuyển ngữ cảnh đã định nghĩa**, không giải quyết race, retry hoặc invariant dữ liệu. Với tác vụ nền chạy lâu, cân nhắc truyền **context bất biến tối thiểu** như correlation ID, tenant ID, command ID hoặc business key qua tham số task thay vì mang toàn bộ request context.

## 11. Ví dụ Java 17 + Spring Boot 3.3: một worker do lifecycle quản lý, dữ liệu qua queue

Dự án mẫu này minh họa ranh giới bằng cách chủ động viết một component `SmartLifecycle` có **một worker thread**, hàng đợi hữu hạn và cơ chế đóng theo `stop(Runnable)`. Nó chỉ xử lý phép cộng số nguyên, không có database, network hoặc broker.

Ta cố tình không dùng `@Async` trong demo chính vì muốn làm rõ **hai trách nhiệm riêng**:

- Spring tạo, start và stop `ManagedQueueWorker`.
- Code của `ManagedQueueWorker` bảo toàn việc **nhận task/đóng intake** và **thứ tự xử lý** qua một queue duy nhất.

Với hệ thống production, nên cân nhắc dùng `ThreadPoolTaskExecutor`/`TaskScheduler` do Spring quản lý thay vì tự tạo thread. Demo không phải một bộ xử lý phân tán hoặc implementation hoàn chỉnh cho mọi tình huống crash/concurrent stop.

### 11.1. Cấu trúc project

```text
task-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/taskboundary/
    ├── TaskBoundaryApplication.java
    └── ManagedQueueWorker.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'task-boundary-demo'
```

**`build.gradle` (Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}
```

Không cần Spring Web, actuator hoặc thư viện thứ ba. Nếu dùng `./gradlew`, project cần Gradle Wrapper đã được tạo từ Spring Initializr hoặc một Gradle tương thích; riêng file `build.gradle` không tự tạo script Wrapper.

### 11.2. Worker: quản lý tiếp nhận công việc và trạng thái

**`src/main/java/com/example/taskboundary/ManagedQueueWorker.java`:**

```java
package com.example.taskboundary;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class ManagedQueueWorker implements SmartLifecycle {

    private record Job(int delta, CompletableFuture<Integer> answer) {}

    private static final Job END = new Job(0, null);

    private final BlockingQueue<Job> queue = new ArrayBlockingQueue<>(4);
    private final Object gate = new Object();
    private final AtomicInteger total = new AtomicInteger();

    private volatile boolean running;
    private boolean accepting;
    private Thread workerThread;

    @Override
    public void start() {
        synchronized (gate) {
            if (running) {
                return;
            }

            Thread newWorker =
                    new Thread(this::consume, "counter-worker");
            newWorker.start();

            workerThread = newWorker;
            accepting = true;
            running = true;
            System.out.println("START worker");
        }
    }

    public CompletableFuture<Integer> add(int delta) {
        CompletableFuture<Integer> answer = new CompletableFuture<>();

        synchronized (gate) {
            if (!accepting) {
                answer.completeExceptionally(
                        new IllegalStateException("worker not accepting"));
                return answer;
            }

            if (!queue.offer(new Job(delta, answer))) {
                answer.completeExceptionally(
                        new RejectedExecutionException("queue full"));
            }
        }

        return answer;
    }

    private void consume() {
        try {
            while (true) {
                Job job = queue.take();

                if (job == END) {
                    return;
                }

                // Chỉ một consumer xử lý từng Job theo FIFO.
                int value = total.addAndGet(job.delta());
                job.answer().complete(value);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            // Nếu worker thoát bất thường, không để Future chờ mãi.
            Job pending;
            while ((pending = queue.poll()) != null) {
                if (pending != END) {
                    pending.answer().completeExceptionally(
                            new IllegalStateException("worker stopped"));
                }
            }
        }
    }

    public int total() {
        return total.get();
    }

    @Override
    public void stop(Runnable callback) {
        synchronized (gate) {
            accepting = false;
            if (!running) {
                callback.run();
                return;
            }
        }

        // Không chặn luồng lifecycle bằng một tác vụ drain dài.
        Thread closer = new Thread(() -> {
            boolean interrupted = false;

            // Bỏ END vào SAU tất cả Job đã nhận.
            for (;;) {
                try {
                    queue.put(END);
                    break;
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }

            // Chỉ báo kết thúc sau khi worker thật sự thoát.
            for (;;) {
                try {
                    workerThread.join();
                    break;
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }

            running = false;
            System.out.println("STOP worker drained");

            if (interrupted) {
                Thread.currentThread().interrupt();
            }
            callback.run();
        }, "counter-closer");

        closer.start();
    }

    @Override
    public void stop() {
        // Hỗ trợ caller muốn dừng đồng bộ qua Lifecycle.stop().
        CountDownLatch completed = new CountDownLatch(1);
        stop(completed::countDown);

        boolean interrupted = false;
        for (;;) {
            try {
                completed.await();
                break;
            } catch (InterruptedException ex) {
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

**Phân tích những ranh giới quan trọng:**

1. `@Component` đăng ký component; `SmartLifecycle.start()` được Spring gọi trong refresh khi bean đủ điều kiện tự start.
2. `ArrayBlockingQueue<>(4)` đặt giới hạn queue ở 4 job, không tăng vô hạn bộ nhớ.
3. `synchronized(gate)` bảo vệ **quyết định nhận job** cùng thao tác đặt job vào queue. Nếu chỉ kiểm tra `accepting` bên ngoài lock rồi `offer` sau, có thể xảy ra race giữa shutdown và submit.
4. `BlockingQueue` cung cấp cơ chế đồng bộ khi truyền job từ producer sang consumer. `AtomicInteger` bảo đảm phép tăng và khả năng đọc an toàn từ thread khác; ở đây một consumer cũng làm thứ tự kết quả dễ hiểu hơn.
5. `CompletableFuture<Integer>` báo kết quả hoặc lỗi. Khi queue đầy, method **trả một future đã thất bại**, không âm thầm bỏ task.
6. `stop(Runnable)` đóng intake trước, sau đó đợi worker xử lý những job đã nhận rồi mới gọi callback. Spring có thể chờ callback trước khi dừng phase thấp hơn.
7. `stop()` riêng hỗ trợ caller muốn dừng đồng bộ; `LifecycleProcessor` gọi **overload có callback** với `SmartLifecycle`.
8. `isRunning()` vẫn `true` trong lúc đang drain, chỉ chuyển `false` sau khi worker đã kết thúc; trạng thái `accepting` là một quy tắc riêng.
9. `getPhase() = 100` chỉ điều phối lifecycle với các bean khác nếu có; nó **không** quyết định thứ tự của job trong queue.

**Giới hạn được khai báo rõ:** ví dụ được thiết kế cho **một lần start rồi một lần đóng context**. Nó chưa chống các yêu cầu `stop(Runnable)` đồng thời, chưa restart worker sau khi STOPPED, không có deadline/cancellation cấp I/O và không có durable queue. Ở production cần state machine (`NEW/RUNNING/STOPPING/STOPPED`), đăng ký callback cho nhiều caller, logic khôi phục khi worker chết, kiểm soát deadline và cơ chế persistence nếu cần. Không dùng demo làm message broker thu nhỏ.

**Trường hợp bất thường cần lưu ý:** nếu worker thread thoát ngoài dự kiến, `finally` làm thất bại những job còn nằm trong queue; job đang xử lý phải có cơ chế `completeExceptionally` nếu phát sinh lỗi chưa được bắt. Trong demo phép cộng không ném lỗi thực tế. Với nghiệp vụ thật, hãy bao từng job bằng `try/catch` phù hợp và hoàn tất future trên mọi đường, đồng thời ghi nhận task đã bị mất khi process chết.

### 11.3. Lớp khởi động và runner để kiểm chứng

**`src/main/java/com/example/taskboundary/TaskBoundaryApplication.java`:**

```java
package com.example.taskboundary;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TaskBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(TaskBoundaryApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: close requested");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner showBoundary(ManagedQueueWorker worker) {
        return arguments -> {
            CompletableFuture<Integer> first = worker.add(2);
            CompletableFuture<Integer> second = worker.add(3);

            System.out.println(
                    "RESULT first = "
                    + first.get(3, TimeUnit.SECONDS));

            System.out.println(
                    "RESULT second = "
                    + second.get(3, TimeUnit.SECONDS));

            System.out.println("TOTAL = " + worker.total());
        };
    }
}
```

`ApplicationRunner` được gọi **sau khi context refresh** và trước `ApplicationReadyEvent`. Đến thời điểm runner submit task, `ManagedQueueWorker` đã được auto-start theo `SmartLifecycle`. Runner **đợi kết quả** bằng `Future.get(timeout)`, vì trong demo ta muốn hoàn tất hai phép tính trước khi coi giai đoạn chạy thử kết thúc.

Nếu bỏ những lệnh `get(...)` mà chỉ submit rồi return, runner có thể kết thúc trước task. Khi đó `ApplicationReadyEvent` có thể tới khi worker vẫn đang xử lý. Điều này cho thấy **lifecycle không tự chờ tất cả công việc** nếu người viết không đặt điều kiện completion thích hợp.

### 11.4. Chạy dự án

Nếu đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ví dụ cố tình không chạy HTTP server nên `try-with-resources` đóng context khi `run(args)` hoàn thành. **Đừng tự đóng context ngay sau startup trong Web service thực**, vì nó sẽ ngừng phục vụ request.

Khi Spring Boot/Gradle in thêm banner và log, **các dòng do chương trình này tự in** có thứ tự kỳ vọng:

```text
START worker
RESULT first = 2
RESULT second = 5
TOTAL = 5
MAIN: close requested
STOP worker drained
MAIN: context closed
```

Không được dùng kết quả này để suy ra mọi pool nhiều thread sẽ luôn trả `first` rồi `second` theo thứ tự. Đây là kết quả của **một consumer** đọc từ `BlockingQueue` theo FIFO và `AtomicInteger.addAndGet`. Việc `MAIN: context closed` đến sau `STOP worker drained` là nhờ Spring phối hợp lifecycle callback; còn các số 2, 5 là do **logic concurrency và toán học của worker**, không phải do framework tự tính.

### 11.5. Thí nghiệm: queue đầy

Trong runner, thử submit nhiều job mà không đợi từng future, ví dụ 20 lần. Vì queue chỉ có 4 ô và worker chỉ có một thread, tùy tốc độ máy có thể thấy một số future thất bại với `RejectedExecutionException`. **Số lượng task bị từ chối không cố định**; việc worker lấy job từ queue tạo race với producer.

Khi thử, phải gọi `get`/`join` hoặc quan sát completion cho từng future và ghi nhận lỗi thay vì bỏ qua. Không gắn assertion rằng “task thứ 5 luôn thất bại”: thời điểm worker dequeue khác nhau giữa các lần chạy. Khi cần test backpressure chính xác, dùng barrier/latch kiểm soát consumer thay vì đợi kết quả ngẫu nhiên.

### 11.6. Thí nghiệm: cố tình bỏ khóa gate

Nếu chuyển việc kiểm tra `accepting` ra ngoài `synchronized(gate)` và thực hiện `queue.offer(...)` sau đó, producer có thể kiểm tra `accepting=true`, bị scheduler tạm dừng, rồi shutdown đã đưa sentinel vào queue trước khi producer gửi job. Khi producer quay lại, job có thể nằm **sau** `END` và không được xử lý.

Đây là race giữa **quy trình đóng intake (lifecycle)** và **quy tắc nhận task (concurrency)**. Dùng synchronized hoặc một state machine atomic bao trọn điều kiện và enqueue là trách nhiệm của chính ứng dụng; riêng `SmartLifecycle` không tự bảo vệ thao tác này.

## 12. Vì sao demo không phải một framework concurrency production?

Đây là chủ đích của bài. Nắm được ranh giới nghĩa là biết **demo đã giải quyết gì và chưa giải quyết gì**.

**Demo giải quyết:**

- Một context khởi tạo và đóng worker theo lifecycle.
- Một hàng đợi có giới hạn; có kết quả hoặc từ chối rõ ràng.
- Một consumer xử lý tuần tự nên có thứ tự FIFO cho các job đã nhận.
- Một bộ đếm cập nhật atomic.
- Dừng tiếp nhận task trước khi đưa `END` và chờ worker kết thúc trước callback.

**Demo chưa giải quyết:**

- Process crash, `kill -9`, mất điện, restart: job trong bộ nhớ sẽ mất.
- Task thực hiện I/O vô hạn hoặc không phản ứng interruption.
- Nhiều caller đồng thời gọi stop/start/restart.
- Exactly-once cho dữ liệu ngoài JVM.
- Transaction bao trọn “nhận message → xử lý → ghi kết quả → ack”.
- Deadline và retry có backoff, jitter, retry budget.
- Chuỗi phụ thuộc nhiều executor/connection theo phase.
- Quy tắc quản lý tenant, authorization và trace context.
- Phân phối task qua nhiều replicas.
- Báo động theo latency, backlog, tuổi task, lỗi async và resource saturation.

Không nên “mở rộng demo” bằng cách chỉ thêm vài `Thread.sleep` và coi nó là hàng đợi bền vững. Khi yêu cầu thay đổi, có thể cần dùng thư viện concurrency chuyên dụng, Spring Integration/Batch, message broker hoặc một kiến trúc worker tách biệt.

## 13. Chọn công cụ theo bài toán thay vì theo annotation

| Bài toán | Lựa chọn thường phù hợp | Lưu ý ranh giới |
|---|---|---|
| Một phép tính độc lập trả kết quả cho caller | `CompletableFuture`/`TaskExecutor` | Cần timeout, exception propagation, tránh chia sẻ mutable state |
| Tác vụ nền theo lịch trong một instance | `@Scheduled` + `TaskScheduler` | Nếu nhiều replicas, scheduling không tự bảo đảm chạy một lần toàn cluster |
| Đổi lời gọi service thành async | `@EnableAsync` + `@Async` | Proxy/self-invocation, executor và context propagation phải đúng |
| Thành phần chạy dài suốt đời ứng dụng | `SmartLifecycle` | Start/stop/phase/callback phải đúng; nội bộ vẫn cần concurrency safety |
| Pool xử lý tác vụ với giới hạn capacity | `ThreadPoolTaskExecutor` | Chọn queue/rejection/backpressure theo SLA |
| Duy trì trạng thái mutable tuần tự | Actor/single-consumer/partition theo key | Queue phải giới hạn, có stop, biết khi nào công việc được xác nhận |
| Tăng counter trong một JVM | `AtomicInteger`/`LongAdder` tùy mục đích | Không đủ cho giao dịch hoặc số đếm phân tán |
| Cập nhật nhiều giá trị phải bất biến nhất quán | Lock, transaction, immutable snapshot | Không thể thay bằng nhiều atomic fields độc lập |
| Xử lý message có thể được gửi lại | Broker + idempotent consumer + dedupe/ack | Lifecycle không tạo exactly-once toàn hệ thống |
| Job dài cần restart/retry/checkpoint | Batch/job framework, checkpoint bền vững | Không nên chỉ chạy một vòng lặp vô hạn trong runner |
| Luồng I/O blocking cực nhiều | Có thể cân nhắc virtual threads Java 21+ | Không tự bỏ nhu cầu giới hạn tài nguyên, deadline hoặc xử lý race |

**Đừng tùy tiện đổi mọi việc thành `@Async`.** Bất đồng bộ có chi phí quan sát, xử lý lỗi và vận hành. Nếu thao tác rất nhỏ, chạy đồng bộ có thể đơn giản và dễ đúng hơn. Dùng concurrency khi workload, độ trễ, throughput hoặc isolation thực sự cần.

## 14. Virtual threads trong Spring Boot 3.3: đổi cách chạy, không đổi nghĩa vụ thiết kế

Nếu chạy **Java 21 trở lên**, có thể bật:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.3 có thể cấu hình `SimpleAsyncTaskExecutor` và `SimpleAsyncTaskScheduler` sử dụng virtual threads. Cấu hình pool như `spring.task.execution.pool.max-size` không có ý nghĩa tương tự với một executor tạo virtual thread cho tác vụ; hãy kiểm tra loại executor đang dùng.

Virtual threads giúp nhiều tác vụ **blocking I/O** có thể sử dụng tài nguyên thread hiệu quả hơn trong một số workload, nhưng:

- Không làm `counter++` thành atomic.
- Không biến hai transaction thành một giao dịch phân tán.
- Không bảo đảm task có thứ tự hoàn tất theo thứ tự submit.
- Không tạo queue capacity tự động hoặc quota cho remote service.
- Không thay thế backpressure và connection limits.
- Không làm một API bên ngoài có timeout nếu bản thân API không hỗ trợ/được cấu hình.
- Có thể gặp các vấn đề hiệu năng khi bị pinning trong một số đường sử dụng đồng bộ hoặc native operations; cần đo trên workload thật.

**Điểm vận hành:** virtual threads là daemon threads. Với ứng dụng chỉ chạy scheduling/background work và không còn non-daemon threads giữ JVM sống, tiến trình có thể thoát; Spring Boot 3.3 có `spring.main.keep-alive=true` để hỗ trợ các tình huống phù hợp. Điều này là **quản lý vòng đời tiến trình**, tách biệt khỏi bất biến của code đang chạy trên virtual thread.

Đừng chuyển project Java 17 sang virtual threads bằng cách chỉ đặt property: tính năng này yêu cầu Java 21+.

## 15. Shutdown trong thực tế: stop, drain và kết thúc cưỡng bức

Một shutdown đáng tin cậy thường gồm:

```text
SIGTERM hoặc yêu cầu đóng context
         |
Đánh dấu instance không tiếp tục nhận traffic mới
         |
Ngừng intake message/request/task mới
         |
Cho tác vụ đang xử lý thời gian hoàn thành
         |
Ghi/flush kết quả, ack có kiểm soát
         |
Đóng executor, scheduler, broker connection, client
         |
Thông báo completion cho LifecycleProcessor
         |
Đóng những dependency còn lại, kết thúc JVM
```

Thứ tự cụ thể phụ thuộc kiến trúc. `SmartLifecycle.getPhase()` hỗ trợ cho **các component trong cùng context**: start phase thấp trước cao, stop cao trước thấp. Nhưng nó không điều khiển những nguồn gửi message bên ngoài hay bảo đảm load balancer đã ngừng routing ngay tức thì.

Spring Boot 3.3 có cấu hình:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` hướng tới Web server tích hợp; `spring.lifecycle.timeout-per-shutdown-phase` đặt thời hạn cho mỗi phase lifecycle. Hai thuộc tính này **không tự làm message consumer của bạn có khả năng drain**. Ngoài ra, deadline của Kubernetes/OS/container có thể ngắn hơn tổng các phase. Nếu bị `SIGKILL`/`kill -9`, Java shutdown callbacks không được bảo đảm chạy.

Với executor do Spring quản lý, còn có những lựa chọn như `setWaitForTasksToCompleteOnShutdown`, `setAwaitTerminationSeconds` hoặc các property cấu hình executor tương ứng. **Phải đọc semantics theo đúng Spring Framework 6.1 / Boot 3.3**: một số lựa chọn chuyển từ coordinated lifecycle stop sang chờ trong giai đoạn destroy, ảnh hưởng việc dependency nào còn sống khi task hoàn tất. Không copy một property rồi tuyên bố mọi task chắc chắn được xử lý xong.

### Ranh giới của timeout

Timeout của Spring là giới hạn **Spring chờ**, không phải timer tự động rollback trạng thái nghiệp vụ hoặc cưỡng bức chấm dứt mọi thread. Nếu task đang bị kẹt ở network I/O và bỏ qua interruption, Spring có thể hết thời gian đợi rồi tiếp tục close bean khác. Khi đó task còn chạy có thể chạm vào dependency đã bị đóng.

Do đó cần timeout ở nhiều lớp: queue admission, task deadline, network client, executor termination và orchestrator grace period. Chúng phải có quan hệ thời gian hợp lý, không phải mỗi lớp chọn ngẫu nhiên một giá trị.

## 16. Nhiều instances: lifecycle riêng của từng JVM không bảo đảm exactly-once

Một ứng dụng Spring Boot chạy ba replicas có ba `ApplicationContext`, ba bộ lifecycle và có thể ba executor/scheduler. Mỗi replica **có thể tự chạy** `@Scheduled` job hoặc consumer của nó. Việc start/stop đúng ở từng replica không đủ để bảo đảm một giao dịch toàn cluster thực hiện đúng một lần.

Phân biệt những khái niệm:

- **At-most-once:** có thể mất message nhưng tránh xử lý lại trong một số cơ chế.
- **At-least-once:** có thể nhận và xử lý lại; cần idempotency/deduplication.
- **Exactly-once effect:** cần xác định chính xác phạm vi (broker, DB, API ngoài) và giao thức giao dịch/khóa/idempotency tương ứng; **không có từ `@Async` hay `SmartLifecycle`**.
- **Order theo partition/key:** broker có thể bảo đảm thứ tự trong partition nhất định, nhưng code nhiều worker còn có thể làm reorder khi xử lý hoàn tất.
- **Shutdown/rebalance:** instance cũ phải ngừng intake/ack đúng thời điểm; instance mới cần tiếp quản checkpoint/lease để không bỏ hoặc xử lý lặp ngoài chính sách.

Một ví dụ về idempotency: lưu khóa `eventId` với unique constraint trước/đồng thời ghi kết quả nghiệp vụ theo transaction thích hợp. Chỉ dùng `ConcurrentHashMap` trong RAM để nhớ ID không giải quyết trùng khi restart hoặc replica khác xử lý cùng ID.

## 17. Kiểm chứng hai nhóm trách nhiệm bằng hai nhóm kiểm thử

### 17.1. Kiểm thử lifecycle

- Component có được tạo thành bean và start ở mốc cần thiết không?
- `start()` có idempotent nếu bị gọi lại không?
- Khi đóng context, component có ngừng nhận task mới không?
- `stop(Runnable)` có callback **sau khi drain xong**, không sớm/không bị quên?
- Bean ở phase cao có ngừng trước dependency ở phase thấp không?
- Khi timeout, service có log trạng thái unfinished work không?
- Có leak non-daemon thread khiến JVM không thoát không?

### 17.2. Kiểm thử concurrency

- Nhiều producer submit đồng thời có làm mất/nhân đôi task không?
- Shared data có giữ invariant khi interleaving khác nhau không?
- Queue đầy thì caller nhìn thấy lỗi hoặc backpressure gì?
- Cancellation và exception có được truyền tới người cần biết không?
- Hai nhiệm vụ cùng key có bị đảo thứ tự không?
- Khi retry, kết quả có bị ghi lặp không?
- Có deadlock/starvation khi pool nhỏ và task chờ lẫn nhau không?
- Có mất transaction/security/tracing context khi đổi thread không?

Hai bộ test trên **khác mục đích**. Không kết luận “thread-safe” chỉ vì integration test khởi động/đóng context thành công; không kết luận “shutdown sạch” chỉ vì unit test `AtomicInteger` pass.

### Dùng công cụ đồng bộ thay vì đoán bằng Thread.sleep

Trong test concurrency, `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc `CompletableFuture` giúp tạo điểm giao nhau giữa các thread có kiểm soát. `Thread.sleep(50)` không bảo đảm hai thread thật sự đã đi qua một điểm cụ thể; test có thể pass vì máy chạy nhanh, fail vì tải máy khác.

Ví dụ snippet kiểm tra completion:

```java
CompletableFuture<Integer> result = worker.add(4);

try {
    int value = result.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException ex) {
    // Có deadline nhưng phải quyết định có hủy công việc hay không.
}
```

Đây là **đoạn kiểm thử tích hợp**, cần `worker`, imports `CompletableFuture`, `TimeUnit` và `TimeoutException`, đồng thời xử lý những checked exceptions khác theo phương thức test. Timeout tại caller không tự đảm bảo task ngừng; khi cần phải gửi cancellation vào đúng worker/resource.

## 18. Những lỗi tư duy phổ biến

| Khẳng định sai | Vì sao sai | Điều cần kiểm chứng |
|---|---|---|
| “Đã dùng `@Async` thì thread-safe” | Annotation chỉ thay đổi nơi thực thi | Shared state và happens-before |
| “`@Scheduled` bảo đảm một job toàn cluster” | Mỗi instance có thể có scheduler riêng | Distributed lock/lease, partition assignment |
| “`ThreadPoolTaskExecutor` tự không mất task” | Queue có giới hạn, shutdown/crash có thể bỏ task | Rejection, durability, ack/retry |
| “`shutdown()` tức là mọi task đã xong” | Nó chỉ ngừng nhận task mới | `awaitTermination`/completion status |
| “`stop(Runnable)` gọi callback ngay là đúng” | Worker có thể vẫn đang flush | Callback sau thực tế drain |
| “Đã gọi callback thì không thể deadlock” | Deadlock nằm trong thuật toán task/lock | Lock order, pool starvation |
| “`volatile` bảo vệ mọi phép cập nhật” | Visibility khác atomicity | `Atomic*`, lock, immutable state |
| “`ConcurrentHashMap` làm cả transaction nghiệp vụ atomic” | Nhiều thao tác liên tiếp vẫn có race | Composite invariants và transaction |
| “`ApplicationReadyEvent` = mọi background task hoàn thành” | Task có thể chưa được đợi | Future/completion hoặc readiness riêng |
| “`@Transactional` tự truyền sang thread async” | Transaction thread-bound thông thường | Ranh giới transaction ở worker |
| “Thêm virtual threads giải quyết backpressure” | Số kết nối và capacity ngoài JVM vẫn hữu hạn | Giới hạn tài nguyên, admission control |
| “Phase của SmartLifecycle quyết định thứ tự task” | Phase chỉ sắp start/stop component | Serial queue, dependency completion |
| “Timeout của Spring buộc worker dừng” | Thread/I/O có thể bỏ qua interrupt | Deadline tài nguyên, force-close, recovery |
| “Một lần test pass là không có race” | Interleaving không bảo đảm tái diễn | Stress test, deterministic synchronization |
| “Dùng sleep để chờ init là đủ” | Sleep không tạo phụ thuộc có nghĩa | Latch/future/callback và trạng thái rõ ràng |

## 19. Bài thực hành

**Bài 1 — nhận diện boundary.** Chạy project phần 11. Phân loại từng dòng stdout: dòng nào do lifecycle điều phối và dòng nào do thuật toán queue/counter? Giải thích tại sao `START worker` không liên quan trực tiếp tới tính atomic của `TOTAL`.

**Bài 2 — tăng độ đồng thời phía producer.** Tạo 4 producer threads cùng gọi `worker.add(1)`. Chờ mọi future theo deadline. Dự kiến tổng đúng bằng số job thực sự được nhận và xử lý; phải ghi nhận những job bị từ chối nếu queue đầy. Không mặc định tất cả đều thành công vì hệ thống có một consumer.

**Bài 3 — bỏ gate.** Tạo một bản test riêng bỏ khóa bao quanh kiểm tra `accepting` và `queue.offer(...)`. Dùng latch để ép shutdown xen vào giữa hai thao tác, rồi quan sát nguy cơ job được enqueue sau sentinel. Khôi phục khóa và giải thích vì sao lifecycle callback một mình không sửa lỗi.

**Bài 4 — cho một job xử lý chậm.** Mô phỏng trong consumer bằng một thao tác chờ có giới hạn; gọi close khi job chưa xong. Đo xem callback stop đến khi nào. Không dùng ví dụ này làm khẳng định mọi task production được drain.

**Bài 5 — thêm rejected future.** Làm đầy queue bằng cách tạm chặn consumer tại một latch và submit nhiều job. Kiểm tra future của job từ chối hoàn tất exceptional với `RejectedExecutionException`, không bị “mất im lặng”.

**Bài 6 — counter không atomic.** Tạo một test Java thuần với nhiều threads dùng `int counter++` rồi so với `AtomicInteger.incrementAndGet()`. Lưu ý test race có thể tình cờ cho kết quả đúng ở một lần chạy; dùng lặp lại và giải thích memory model, không chỉ dựa trên một stdout.

**Bài 7 — Future và deadline.** Thử `get(1, TimeUnit.MILLISECONDS)` với một task làm chậm có kiểm soát. Giải thích vì sao caller timeout không đồng nghĩa task đã dừng. Đề xuất cơ chế cancel/deadline ở worker.

**Bài 8 — tự gọi @Async.** Tạo hai bean, một bean chứa `@Async` method và bean kia là caller. So sánh lời gọi qua proxy với `this.method()` trong cùng target. Cần bật `@EnableAsync` và quan sát thread names, exception handling.

**Bài 9 — hai replicas.** Giả sử hai ứng dụng đều chạy `@Scheduled(fixedRate=1000)` để cập nhật cùng bảng. Thiết kế phương án tránh ghi trùng: lease, partition hoặc chuyển sang job service; mô tả khi một instance chết giữa commit và ack thì dữ liệu có thể ở trạng thái nào.

**Bài 10 — review một thiết kế production.** Với một consumer nhận message, database và REST client, ghi rõ: (a) worker/pool lifecycle; (b) queue capacity; (c) transaction boundaries; (d) deadline; (e) duplicate handling; (f) recovery sau crash; (g) metrics; (h) thứ tự dừng dependency. Nếu chỉ có `@Async` và `@PreDestroy`, thiết kế vẫn còn nhiều câu hỏi cần giải đáp.

### Câu hỏi tự đánh giá

1. Vì sao `@Async` không làm `counter++` an toàn?
2. `SmartLifecycle.getPhase()` quản lý thứ tự điều gì? Nó có bảo đảm FIFO completion của mọi task không?
3. Nếu task được submit trong runner nhưng không await, `ApplicationReadyEvent` có thể xảy ra trước completion không?
4. `ExecutorService.shutdown()` khác `awaitTermination(...)` và `shutdownNow()` ở điểm nào?
5. Vì sao cần một cơ chế atomic bao quanh việc kiểm tra “đang nhận việc” và enqueue?
6. Khi queue đầy, tại sao trả lỗi rõ ràng thường tốt hơn mất task im lặng?
7. Vì sao `@Transactional` ở request thread không nên được giả định tự truyền sang worker?
8. Virtual threads Java 21+ có thay thế giới hạn kết nối, timeout và backpressure không?
9. Nếu process chết trước khi ack message, lifecycle shutdown callback có chạy chắc chắn không?
10. Cần những kiểm thử khác nhau nào để chứng minh **shutdown đúng** và **thuật toán đồng thời đúng**?

## 20. Tóm tắt thiết kế

Khi cần làm việc với luồng và tác vụ trong Spring Boot, hãy bắt đầu bằng hai bộ câu hỏi tách biệt:

**Lifecycle:** ai tạo executor/worker? Khi nào start? Khi nào ngừng intake? Ai chờ drain? Callback và phase nào quyết định đóng dependency? Nếu JVM bị tắt cưỡng bức thì khôi phục ra sao?

**Concurrency:** trạng thái nào được chia sẻ? Thao tác nào phải atomic? Thứ tự nào bắt buộc? Queue đầy thì sao? Task timeout/hủy/exception sẽ xảy ra gì? Nếu nhận lại message hoặc chạy hai replicas, có ghi trùng hoặc mất dữ liệu không?

Spring Boot 3.3 giúp bạn cấu hình executor/scheduler và gắn lifecycle với context. Nhưng **khả năng được tạo và đóng đúng không tự chứng minh logic xử lý đồng thời đúng**. Một thiết kế có chất lượng phải hoàn thành cả hai phần: tài nguyên được quản lý tốt, và invariant dữ liệu được bảo vệ khi task chạy xen kẽ, quá tải, bị hủy, restart hoặc phân tán qua nhiều tiến trình.

### Tài liệu chính thức

- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — SpringApplication lifecycle/events/runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — SmartLifecycle Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.1/integration/scheduling.html
- Spring Framework 6.1 — ThreadPoolTaskExecutor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java 17 — java.util.concurrent package overview: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html