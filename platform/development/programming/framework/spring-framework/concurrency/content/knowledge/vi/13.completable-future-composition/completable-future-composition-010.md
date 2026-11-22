# Tránh chờ tác vụ con trên chính nhóm luồng đã cạn

## 1. Vấn đề: parent giữ worker để chờ child cần chính worker ấy

Một lỗi concurrency khó thấy khi dùng Java `CompletableFuture` cùng Spring `ThreadPoolTaskExecutor` là **tác vụ cha (parent) đang chạy trên worker của pool, submit tác vụ con (child) vào cùng pool rồi gọi `Future.get()` hoặc `CompletableFuture.join()` để đợi con**. Nếu tất cả worker đều bị parent giữ, child nằm trong queue mà không có worker thực thi. Parent không kết thúc trước khi child xong; child không bắt đầu trước khi parent nhường worker.

Đây là **thread-pool starvation deadlock**: không có tiến triển vì tài nguyên thực thi đã bị chiếm hết bởi những công việc đang chờ công việc khác cần chính tài nguyên ấy. Không nhất thiết có `synchronized`, `ReentrantLock`, CPU cao hay lỗi trực tiếp từ JVM.

**Nguyên tắc chính:** khi đang giữ worker của executor, tránh chặn nó để đợi một Future mà việc hoàn tất phụ thuộc vào tác vụ chưa được chạy trong cùng executor. Hãy **diễn tả phụ thuộc bằng completion stages** như `thenApply`, `thenCompose` và `thenCombine`, để worker có thể trở lại nhận việc thay vì đợi đồng bộ.

Bài tập trung vào parent–child dependencies, cơ chế queue/core/max, cách Spring `@Async` có thể thêm tầng chờ ngầm, và biện pháp phòng tránh có thể kiểm chứng bằng Java 17+.

## 2. Cơ chế bế tắc qua sơ đồ một worker

Giả sử executor có một worker và hàng đợi đủ chỗ. Caller gửi parent, parent lại gửi child:

```text
Caller thread
    |
    +--- pool.submit(Parent) -----------+
                                         |
                                    Worker #1 chạy Parent
                                         |
                                         +-- submit(Child)
                                         |       |
                                         |       +--> Queue: [Child]
                                         |
                                         +-- Child.get() / Child.join()
                                                 |
                                                 +--> Worker #1 bị chặn
                                                         |
Child cần Worker #1 <------------------------------------+
    |
    +-- Child không thể bắt đầu, Parent không thể nhường worker
```

Đây là chu trình chờ có tính cấu trúc. Nếu Parent chỉ làm một phép tính dài, worker vẫn có thể tự hoàn tất. Nhưng nếu Parent đòi một Child đang xếp hàng mà chỉ chính worker này có thể thực thi, **tăng thời gian chờ sẽ không làm Child tự chạy**.

Với N worker:

```text
Worker #1 = Parent A  --> chờ Child A
Worker #2 = Parent B  --> chờ Child B
...
Worker #N = Parent N  --> chờ Child N

Queue = [Child A, Child B, ... Child N]
Không còn worker rảnh để xử lý queue.
```

Vì thế một thiết kế có vẻ ổn ở tải nhẹ (còn worker rảnh) có thể kẹt khi **số parent đồng thời đạt N**. Có thể tái hiện với 1, 2 hoặc nhiều worker, không nhất thiết pool thật sự rất nhỏ.

## 3. Chờ bên trong và chờ bên ngoài pool không giống nhau

`Future.get()` đợi kết quả, `CompletableFuture.join()` cũng có thể chặn. Điểm quyết định là **thread đang chờ có phải worker mà child cần hay không**.

| Trường hợp | Đánh giá |
| --- | --- |
| Main/test thread bên ngoài pool gọi `future.get()`, worker của pool rảnh để hoàn tất task | Có thể hợp lệ ở ranh giới chờ có thời hạn; vẫn chặn main/test thread |
| HTTP thread gọi `get()` ngay sau submit | Có thể làm request chờ lâu; không nhất thiết làm cạn pool, nhưng phải kiểm soát SLO |
| Parent trong pool gọi `child.join()`, child chạy trong cùng pool đang đầy | Rủi ro starvation deadlock |
| Parent gọi `join()` trên một Future **đã hoàn tất** | Không phải đang đợi child chưa được chạy; thường trả về ngay |
| Parent đang ở pool A chờ task của pool B | Không tự tạo vòng chờ cùng pool, nhưng vẫn có thể gây cạn tài nguyên hoặc vòng phụ thuộc giữa A và B |
| Một callback đăng ký bằng `thenCompose` mà **không gọi blocking API** | Worker không bị giữ chỉ để đợi stage con |

Không có quy tắc “tất cả `join()` đều sai”. Quy tắc đúng là **không biến một worker cần thiết cho tiến trình hoàn tất thành thread đợi Future của tác vụ phụ thuộc chưa có worker**.

## 4. Ví dụ Java 17+ chạy được và không treo vô hạn

Ví dụ này cố ý dùng executor có **một worker**. Parent submit child rồi chờ child với timeout 100 ms. Vì child chưa thể chạy, parent nhận timeout. Khi parent thoát, child mới được chạy. Cuối chương trình, một workflow `thenCompose` chạy thành công trên **chính pool một worker đó** mà không cần nested blocking.

Tạo file `PoolStarvationDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public final class PoolStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        AtomicReference<Future<Integer>> childRef = new AtomicReference<>();

        try {
            Future<String> parent = pool.submit(() -> {
                Future<Integer> child = pool.submit(() -> 21 * 2);
                childRef.set(child);

                try {
                    child.get(100, TimeUnit.MILLISECONDS);
                    return "unexpected";
                } catch (TimeoutException ex) {
                    return "timed out";
                }
            });

            System.out.println("parent = " + parent.get());
            System.out.println("child = " + childRef.get().get());

            CompletableFuture<Integer> start =
                    CompletableFuture.supplyAsync(() -> 21, pool);

            CompletableFuture<Integer> composed =
                    start.thenCompose(n ->
                            CompletableFuture.supplyAsync(() -> n * 2, pool));

            System.out.println("composed = " + composed.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac PoolStarvationDemo.java
java PoolStarvationDemo
```

Stdout:

```text
parent = timed out
child = 42
composed = 42
```

Giải thích từng bước:

1. `Executors.newSingleThreadExecutor()` chỉ có một worker. Parent chạy đầu tiên.
2. Parent submit child vào chính pool. Child nằm ở queue vì worker đang bận chạy Parent.
3. Parent gọi `child.get(100, TimeUnit.MILLISECONDS)`; do không có worker nào chạy child, lượt chờ này timeout. Parent kết thúc và trả chuỗi `"timed out"`.
4. Khi worker rảnh, child được lấy khỏi queue, trả `42`. `childRef.get().get()` được gọi ở **main thread**, không giữ worker của pool.
5. Cuối cùng, `start` trả 21. `thenCompose` đăng ký một stage child trong cùng pool và trả quan hệ hoàn tất, **không ép worker đang thực thi continuation phải chặn đợi child**. Child sau đó chạy và cho kết quả 42. Main thread đọc kết quả bằng `composed.get()`.

Ví dụ đã được thực thi qua JShell trên JDK hiện có, xác nhận đúng ba dòng output. Trong chương trình độc lập, `shutdownNow()` dừng executor lúc thoát; trong Spring, không nên tự shutdown bean executor chia sẻ sau mỗi request.

**Phản ví dụ:** nếu bỏ timeout và thay bằng `child.get()` vô thời hạn trong Parent, cả Parent lẫn Child có thể chờ mãi. Không chạy biến thể đó trong CI nếu không có cơ chế kết thúc từ bên ngoài.

## 5. Nhận diện deadlock bằng đồ thị chờ và tài nguyên

Để phân tích một workflow, ghi ra:

```text
Parent P đang sở hữu worker W
P --------- chờ ----------> Future của Child C
C --------- cần ----------> worker thuộc Executor E
E --------- đã cấp -------> W cho P
```

Nếu E đã cấp **toàn bộ** worker cho các parent đang chờ child, không có đường tiến triển. Điều này khác với task đang chạy chậm vì CPU hoặc I/O: với starvation deadlock, child có thể thậm chí chưa **bắt đầu**.

| Hiện tượng | Phân biệt |
| --- | --- |
| **Pool starvation** | Tác vụ đã xếp hàng nhưng không có worker khả dụng |
| **Pool-starvation deadlock** | Worker đang bị chiếm bởi task phải đợi công việc không thể chạy vì chính worker đó đang bị chiếm |
| **CPU saturation** | Worker đang tiến hành tính toán, CPU/quotas bị sử dụng gần hết |
| **Blocking I/O** | Worker có thể đang đợi DB/API; có thể tiến triển khi I/O kết thúc |
| **Lock deadlock** | Threads giữ khóa và chờ khóa của nhau; JVM có thể phát hiện một số monitor/ownable synchronizer cycles |
| **Rejection** | Pool/queue không nhận thêm task và có thể ném exception, không nhất thiết là chờ vô hạn |

Đừng dựa vào mỗi `Thread.State.WAITING`. Phải xác định **thread nào hoàn tất Future đó, task đó đang ở executor nào và điều kiện nào giúp nó có worker**.

## 6. ThreadPoolTaskExecutor: tại sao maxPoolSize không tự cứu được?

Spring `ThreadPoolTaskExecutor` dùng `ThreadPoolExecutor` JDK. Quy tắc nộp task thường là:

1. Khi số worker dưới `corePoolSize`, thêm worker.
2. Khi đạt core mà queue nhận được task, ưu tiên **enqueue**.
3. Chỉ khi queue không nhận được, tạo thêm worker tới `maxPoolSize`.
4. Nếu queue không nhận được và đã đạt max, task bị từ chối theo policy.

Ví dụ **mảnh cấu hình**:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(20);
executor.setQueueCapacity(1000);
```

Nếu hai worker lõi đang chạy hai parent và cả hai submit children rồi chờ, queue còn rất rộng sẽ nhận children, thay vì bắt buộc pool mở lên 20 worker. Vì thế **`maxPoolSize=20` không bảo đảm có 20 worker để giải cứu parent**.

Các cấu hình ảnh hưởng tới triệu chứng:

| Cấu hình | Khi core workers bận | Hệ quả với child |
| --- | --- | --- |
| `core=max=1`, queue có chỗ | Child chờ trong queue | Một parent chờ child có thể kẹt |
| `core=max=N`, queue có chỗ | Tất cả N parent có thể giữ N workers | N child chờ và có thể kẹt |
| `core<max`, queue rất lớn | Hệ thống ưu tiên enqueue | Max có thể hiếm khi được dùng |
| `queueCapacity=0`, max hữu hạn | Cố bàn giao trực tiếp hoặc tạo thêm worker | Child có thể chạy nếu còn worker; nếu đạt max có thể bị từ chối |
| Queue vô hạn/khổng lồ | Rất nhiều task tiếp tục được nhận | Backlog, memory/latency tăng và che giấu việc cạn worker |

Tăng `corePoolSize`, `maxPoolSize` hoặc giảm `queueCapacity` có thể làm vấn đề xuất hiện muộn hơn hoặc đổi thành rejection, nhưng **không sửa cấu trúc parent phải giữ worker để chờ child**. Với N worker, N parent đồng thời vẫn có thể tái tạo vòng chờ.

## 7. CompletableFuture giúp diễn tả phụ thuộc mà không chặn worker

Thay vì tạo child rồi lập tức `get()` trong parent, hãy xây dựng một **completion graph**. Các stage được kích hoạt khi điều kiện hoàn tất đã thỏa, không cần một worker ngồi đợi stage khác.

### thenApply: biến đổi giá trị

```java
CompletableFuture<Integer> doubled =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenApply(number -> number * 2);
```

Ở đây `thenApply` biến đổi kết quả 21 thành 42. Đây là **mảnh code** giả sử đã có biến `Executor executor`. Callback có thể chạy trên thread hoàn tất Future trước, hoặc thread gọi hoàn tất khác theo hợp đồng Java; không được mặc định nó chạy trên caller.

Dùng `thenApplyAsync(fn, executor)` khi muốn lập lịch rõ ràng cho callback. **Đừng** nhét một `join()` để chờ child chưa chạy trong callback ấy.

### thenCompose: bước tiếp theo trả một Future

```java
CompletableFuture<Integer> doubled =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenCompose(number ->
                        CompletableFuture.supplyAsync(
                                () -> number * 2, executor));
```

`thenCompose` làm phẳng quan hệ Future lồng nhau và tạo stage đại diện cho kết quả child. Stage đầu hoàn tất và có thể giải phóng worker, trong khi stage con được thực thi sau đó. Nó không cần `child.join()` ngay trong callback.

**Sai cách:**

```java
CompletableFuture<Integer> wrong =
        CompletableFuture.supplyAsync(() -> 21, executor)
                .thenApply(number ->
                        CompletableFuture.supplyAsync(
                                () -> number * 2, executor).join());
```

Đây là **phản ví dụ**: `thenApply` chạy callback có `join()`. Nếu callback chạy trên worker của pool một thread thì child được submit vào queue trong khi callback tiếp tục giữ worker để chờ — lặp lại starvation. Đặt `join` sâu trong lambda không làm hành vi blocking biến mất.

### thenCombine: hai tác vụ độc lập

```java
CompletableFuture<Integer> base =
        CompletableFuture.supplyAsync(() -> 40, executor);
CompletableFuture<Integer> extra =
        CompletableFuture.supplyAsync(() -> 2, executor);

CompletableFuture<Integer> total =
        base.thenCombine(extra, Integer::sum);
```

Với một worker, base và extra có thể chạy lần lượt; phép kết hợp được đăng ký và chạy **sau khi cả hai hoàn tất**. Không có parent giữ worker rồi đứng đợi child.

### allOf: lỗi nằm ở nơi gọi join

`CompletableFuture.allOf(a,b,c)` trả Future tổng hợp mà không tự block. Tuy nhiên `allOf(a,b,c).join()` **có thể block** nếu gọi bên trong worker đang cần để a/b/c hoàn tất.

Nếu các Future thành phần đã được tổ chức hợp lý, có thể dùng:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
CompletableFuture<Result> combined =
        all.thenApply(ignored -> merge(a.join(), b.join()));
```

Đây là **mảnh minh họa**, giả sử `a`, `b` là các `CompletableFuture`, `Result` và `merge` đã được định nghĩa. Khi `all` hoàn tất bình thường, `a` và `b` đã có kết quả; hai `join()` trong callback chỉ lấy kết quả **đã sẵn sàng**, không chờ task chưa thể chạy. Nếu một stage thất bại thì `thenApply` không chạy; cần xử lý exceptional completion riêng.

**Kết luận:** `thenCompose` và `allOf` không tự giải quyết mọi phụ thuộc. Chúng an toàn theo hướng này khi continuation không tự chiếm worker để chờ một công việc chưa có worker.

## 8. Spring: service điều phối có thể trả CompletableFuture mà không cần @Async

Một cách cấu trúc rõ ràng là để service **xây chuỗi CompletionStage**, còn từng bước tốn thời gian được submit bằng `CompletableFuture.supplyAsync(..., executor)`. Method điều phối không nhất thiết cần `@Async`.

Bean executor (mảnh cấu hình Spring Framework cần import và đăng ký trong ApplicationContext):

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }
}
```

Service (mảnh tích hợp Spring, cần imports `@Service`, `@Qualifier`, `Executor`, `CompletableFuture`, `ThreadPoolTaskExecutor`):

```java
@Service
public class CalculationService {
    private final Executor workerPool;

    public CalculationService(
            @Qualifier("workerPool") ThreadPoolTaskExecutor workerPool) {
        this.workerPool = workerPool;
    }

    // Không gắn @Async lên phương thức chỉ xây completion graph.
    public CompletableFuture<Integer> calculate() {
        return CompletableFuture.supplyAsync(() -> 21, workerPool)
                .thenApplyAsync(number -> number * 2, workerPool);
    }
}
```

`calculate()` lập lịch hai stage và trả Future cho caller. Worker thứ nhất có thể hoàn thành stage đầu rồi nhận stage thứ hai. Không có parent đang chiếm worker chỉ để `join()` kết quả child.

Khi bước tiếp theo vốn là một API async thực sự, chẳng hạn HTTP client trả `CompletionStage<Response>`, sử dụng `thenCompose`:

```java
public CompletableFuture<Report> build(long id) {
    return CompletableFuture.supplyAsync(
                    () -> loadBase(id), workerPool)
            .thenCompose(base ->
                    remote.fetchAsync(base.externalId())
                            .thenApply(extra -> merge(base, extra)));
}
```

Đoạn này là **mảnh minh họa** cần `loadBase`, `remote.fetchAsync`, `merge` và `Report` trong ứng dụng. Điều kiện là `fetchAsync` không giấu một nested blocking trên chính pool cạn worker. Mọi API mang chữ Async đều cần kiểm tra implementation và executor thực tế.

**Lưu ý:** code trên không cần một `@Async` bao ngoài. Nếu phương thức orchestration gọi `join()` trong lambda, lỗi vẫn có thể xuất hiện dù method trả `CompletableFuture`.

## 9. Cạm bẫy Spring @Async: có thể có Future.get() ngầm trong interceptor

Một trường hợp đặc biệt quan trọng: code nghiệp vụ **không hề gọi `join()`**, nhưng cấu trúc vẫn tạo vòng chờ.

Trong Spring Framework **6.2.x** ở chế độ `@Async` proxy, `AsyncExecutionInterceptor` thực hiện lời gọi target trong một `Callable` được gửi tới executor. Nếu lời gọi target **trả một `Future`**, interceptor lấy giá trị của Future đó bằng `get()` để hoàn tất Future phía proxy. Điều này có thể khiến chính worker xử lý `@Async` **chờ một Future con chưa hoàn tất**.

**Mã phản ví dụ** (mảnh Spring-managed bean, không dùng làm thiết kế production):

```java
@Service
public class BadWorkflow {
    private final Executor workerPool;

    public BadWorkflow(@Qualifier("workerPool") Executor workerPool) {
        this.workerPool = workerPool;
    }

    @Async("workerPool")
    public CompletableFuture<Integer> calculateAsync() {
        return CompletableFuture.supplyAsync(() -> 42, workerPool);
    }
}
```

Nếu `workerPool` có một worker, queue nhận được child, caller gọi method qua Spring proxy và cơ chế Spring async tương ứng được bật:

```text
Caller -> @Async proxy -> submit wrapper
                                 |
                            Worker chạy wrapper
                                 |
                         Target.calculateAsync()
                                 |
                          supplyAsync(child)
                                 |
                          child nằm trong queue
                                 |
                     target trả CompletableFuture
                                 |
                    interceptor chờ future.get()
                                 |
                     Worker không rảnh để chạy child
```

Cấu trúc này có thể kẹt dù method chỉ có `return CompletableFuture.supplyAsync(...)`. Đây là hành vi **được đối chiếu với bytecode `AsyncExecutionInterceptor` của Spring 6.2.9**: sau `MethodInvocation.proceed()`, nếu kết quả là `Future`, callable gọi `Future.get()`. Nó không phải quy tắc cho mọi cơ chế async bên ngoài Spring hay mọi phiên bản framework.

Cách sửa:

- **Tốt nhất cho composition:** method điều phối không có `@Async`, tự trả Future được ghép từ các stage và chọn executor tường minh như mục 8.
- **Nếu giữ `@Async`:** thực hiện tính toán ngay trên worker của method, rồi trả một Future **đã hoàn tất**, chẳng hạn `CompletableFuture.completedFuture(result)`. Không tạo Future con pending trên cùng pool rồi trả nó cho interceptor chờ.

```java
@Async("workerPool")
public CompletableFuture<Integer> calculateAsync() {
    int result = doCalculation(); // Đang chạy bên trong worker @Async.
    return CompletableFuture.completedFuture(result);
}
```

Đây là **mảnh method Spring**, cần định nghĩa `doCalculation()` và được gọi qua bean proxy. Khi result đã tính xong trước lúc method trả, interceptor không chờ một child chưa có worker.

**Hai cơ chế cần phân biệt:** `@Async` lập lịch nhờ **Spring proxy/advice**; `CompletableFuture.supplyAsync` lập lịch nhờ **JDK Executor**. Kết hợp cả hai mà không vẽ đường đi có thể vô tình tạo **hai tầng submit và một điểm chờ ẩn**.

## 10. Bảng quyết định khi code hiện có đang gọi get/join

| Đang làm gì? | Rủi ro | Điều chỉnh |
| --- | --- | --- |
| Parent trong pool gọi `child.get()` cùng pool | Rất cao khi mọi worker cùng bị chiếm | Trả stage và nối bằng `thenCompose` |
| Callback `thenApply` gọi `child.join()` | Có thể blocking trên thread hoàn tất stage | Dùng `thenCompose`, không chờ child trong callback |
| N task độc lập rồi gọi `allOf(...).join()` ngay trong worker pool ấy | Có thể giữ worker cần để chạy N task | Trả stage `allOf`, kết hợp sau completion |
| Controller gọi `future.get(timeout)` trên request thread | Không trực tiếp giữ worker pool, nhưng request bị block | Xét async HTTP/SLO; dùng deadline rõ |
| `@Async` trả Future con pending chạy cùng pool | Có thể bị interceptor chờ ngầm | Bỏ `@Async` ở orchestration hoặc trả Future đã hoàn tất trong target |
| Tăng max mà queue rất rộng | Có thể không tạo thêm worker | Kiểm tra core, queue, max theo thứ tự |
| Tách parent/child sang hai pool có giới hạn | Có thể loại vòng chờ cùng pool, nhưng chuyển điểm nghẽn | Xem queue, dependencies, overhead và tải đa tầng |
| Timeout rồi retry vô hạn | Có thể tạo thêm task/backlog | Retry có giới hạn, backoff, idempotency và overload control |

Việc tách executor có thể là giải pháp hợp lý nếu bắt buộc có thao tác chặn độc lập (ví dụ thư viện chỉ có blocking API), nhưng cần cấu hình đồng thời theo toàn bộ dependency: CPU, DB connection, memory, rate limit và network. **Không chọn unbounded threads chỉ để giấu cấu trúc sai**.

## 11. Timeout và cancellation không tự tháo được vòng chờ

`future.get(1, SECONDS)` có thể giải phóng parent sau 1 giây; ví dụ Java ở mục 4 cố ý dùng timeout để chương trình thoát. Nhưng nó chỉ **chặn tình huống treo vô hạn**, không làm mô hình submit child rồi đợi trên cùng pool trở thành tốt.

Với `CompletableFuture`:

- `orTimeout(timeout, unit)` khiến Future hoàn tất exceptional khi chưa xong đúng hạn, nhưng **không tự bảo đảm** worker, I/O hay dependency đã dừng.
- `completeOnTimeout(value, timeout, unit)` dùng giá trị fallback khi quá hạn, **không có nghĩa công việc nền đã ngừng**.
- `cancel(true)` của `CompletableFuture` không sử dụng flag để ngắt worker theo cách một số `FutureTask` có thể làm; hủy stage không nhất thiết hủy mọi tác vụ phụ thuộc.
- `get(timeout)` chỉ giới hạn **lượt chờ của caller**, không phải deadline thực thi toàn workflow.

Mọi giao thức có hủy/cancel nên tính đến tài nguyên đã giữ, side effects, idempotency và deadline của DB/HTTP client. Không nên dùng timeout như cách chính để chờ child khi toàn bộ worker đã cạn.

## 12. ForkJoinPool, commonPool và virtual threads: những ngoại lệ cần hiểu

`CompletableFuture.supplyAsync(supplier)` **không chỉ định executor** thì theo JDK 17 thường dùng `ForkJoinPool.commonPool()`, với ngoại lệ về parallelism và customization của framework/subclass. Việc child chạy trên một pool khác đôi khi khiến mẫu thử “không còn kẹt”, nhưng bạn có thể đã **chuyển tải sang common pool ngoài ý muốn**, làm mất kiểm soát queue/công suất/observability và context.

`ForkJoinPool` có cơ chế đặc thù như work stealing và có thể hỗ trợ một số trường hợp managed blocking; **không được suy ra** mọi kiểu blocking hoặc mọi dependency đều được pool tự mở đủ worker để phá chu trình. Một `ThreadPoolTaskExecutor` cố định thông thường không có cùng chính sách đó.

Virtual threads (JDK 21+ trong môi trường phù hợp) giúp giảm chi phí của nhiều task phải chặn, nhưng không sửa được một chu trình logic phụ thuộc kết quả, quota database hoặc giới hạn semaphore. Cần xác định **phần tài nguyên nào thực sự bị giữ** thay vì hy vọng thread model mới tự bảo đảm tiến triển.

## 13. Chẩn đoán trong Spring production

Quan sát một tập metric **trong cùng khoảng thời gian**:

| Dấu hiệu | Gợi ý | Việc cần làm |
| --- | --- | --- |
| `activeCount ≈ poolSize` lâu | Hầu hết worker đang bận hoặc chờ | Thread dump xem WAITING, TIMED_WAITING, I/O |
| Queue tăng, throughput hoàn tất gần bằng 0 | Task nằm chờ, worker không tiến triển | Tìm parent đang chờ Future được queue thực thi |
| CPU thấp, response timeout | Có thể blocking/lock/pool starvation | Xem stack `FutureTask.get`, `CompletableFuture.join` |
| maxPoolSize cao, pool không tăng beyond core | Queue có chỗ nên không mở worker vượt core | Kiểm tra `queueCapacity` thực tế |
| `TaskRejectedException` tăng | Chạm trần pool/queue hoặc executor shutdown | Phân biệt rejection với task nằm chờ |
| `@Async` method trả Future con pending | Có thể interceptor `get()` Future bên trong worker | Xác định executor của method và child |
| Log có submitted nhưng thiếu started | Child chưa được lấy khỏi queue | Ghép trace parent-child, đo queue wait |

Dùng `ThreadPoolTaskExecutor.getActiveCount()`, `getPoolSize()`, `getQueueSize()` cùng metric executor/Micrometer khi được instrument. Đây là snapshot, không phải chứng minh duy nhất. Kết hợp **thread dump**, trace/correlation ID, và danh sách Future phụ thuộc để biết ai chờ ai.

Cần chú ý: JVM deadlock detector chủ yếu hữu ích với monitor và một số lock; **thread-pool starvation deadlock có thể không hiện là một Java monitor deadlock**. Thread dump vẫn giúp thấy các worker cùng chờ `FutureTask.get` hoặc `CompletableFuture.waitingGet` trong lúc queue còn child chưa bắt đầu.

## 14. Kiểm thử tái hiện mà không để test suite treo

Một bài test tốt nên cố tình tạo điều kiện cạn worker nhưng có deadline:

1. Dùng executor cố định 1 hoặc 2 worker, queue đủ chỗ chứa children.
2. Cho mỗi worker chạy một parent, xác định parent thực sự đã vào task trước khi submit child; dùng `CountDownLatch` nếu cần phối hợp thứ tự.
3. Chờ child với **timeout nhỏ** chỉ để xác nhận điểm kẹt, không để test treo vĩnh viễn. Ghi nhận child đã submit nhưng chưa started.
4. Thoát hoặc hủy parent bằng cơ chế bên ngoài; xác nhận child có thể chạy sau khi worker được nhường.
5. Thay pattern bằng `thenCompose`/`thenApplyAsync`, chạy lại trên **cùng một pool một worker** và xác nhận workflow cuối hoàn tất.
6. Lặp với nhiều parent ngang hoặc vượt số worker, và cả tình huống queue đầy/rejection.
7. Có timeout cho test harness và cleanup trong `finally`. Không dùng `Thread.sleep()` ngẫu nhiên làm giả lập thứ tự thay cho latch/hook có kiểm soát.

Đánh giá đúng phải bao gồm **throughput hoàn tất**, thời gian chờ queue, số worker bận, p95/p99, lỗi và khả năng recovery. Một test chỉ qua khi ít tác vụ chưa đủ chứng minh cấu trúc an toàn.

## 15. Checklist code review

Trước khi merge workflow `CompletableFuture` hoặc `@Async`, hỏi:

1. Hàm nào chạy **trên worker của executor**?
2. Trong hàm ấy có `get`, `join`, `await` hoặc API chặn vì task khác không?
3. Task được đợi sẽ chạy ở **executor nào**? Có phải cùng pool hoặc một chuỗi pool phụ thuộc vòng?
4. Với mọi worker đều bận parent, child còn được cấp worker không?
5. Queue có chỗ khiến `maxPoolSize` không mở rộng hay không?
6. Phương thức `@Async` có trả một Future con **còn pending** chạy trên chính executor mà async interceptor đang dùng?
7. Có thể dùng `thenCompose`/`thenCombine`/`allOf` và trả **Future của toàn workflow** thay cho chờ đồng bộ?
8. Callback có xử lý CPU/I/O nặng hoặc lại submit+join trong cùng pool không?
9. Có đo queue, active workers, task started/completed và exception/rejection không?
10. Timeout/cancellation và resource cleanup có được thiết kế, không chỉ dùng để che starvation?

Đề bài không yêu cầu “không bao giờ chờ bất kỳ Future nào”: chờ ở **ranh giới điều phối bên ngoài** hoặc đọc Future đã hoàn tất có thể hợp lý. Mục tiêu là **không giữ tài nguyên cần thiết cho child tiến triển chỉ để đợi child ấy**.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Pool một worker, parent submit child vào chính pool rồi gọi `child.get()` vô hạn. Vì sao kẹt?  
**Đáp án:** Child xếp hàng nhưng chỉ có worker đang bị parent chiếm. Parent đợi child, child đợi worker.

**Câu 2.** `core=2`, `max=20`, `queueCapacity=1000`; hai parent cùng chờ hai child. Max=20 có đảm bảo cứu được không?  
**Đáp án:** Không. Khi queue còn chỗ, executor ưu tiên enqueue; pool có thể duy trì hai worker đang bị chặn.

**Câu 3.** Đổi `get()` sang `join()` có giải quyết blocking không?  
**Đáp án:** Không. `join` cũng chặn nếu stage chưa hoàn tất; chủ yếu khác loại exception.

**Câu 4.** Bước tiếp theo trả một `CompletableFuture<T>`. Chọn `thenApply` hay `thenCompose`?  
**Đáp án:** `thenCompose` để nối và làm phẳng stage bất đồng bộ, không cần `join` ở callback.

**Câu 5.** `@Async` method trả `CompletableFuture.supplyAsync(..., samePool)` có thể deadlock dù method không gọi `join`?  
**Đáp án:** Có. Với Spring proxy async 6.2.x, interceptor có thể gọi `Future.get()` trên Future target trả về trong worker của pool.

**Câu 6.** `CompletableFuture.allOf(a,b)` có chặn worker không?  
**Đáp án:** Không; nó trả stage tổng hợp. Nhưng gọi `allOf(a,b).join()` trong worker đang cần để a/b chạy thì có thể gây starvation.

**Câu 7.** Khi parent có `get(timeout)`, child chạy sau khi parent timeout, vấn đề đã được sửa chưa?  
**Đáp án:** Chưa. Timeout chỉ giúp parent nhường worker sau khi thất bại; mẫu phụ thuộc tài nguyên vẫn không an toàn.

**Ghi nhớ:** **Worker thực hiện việc; Future biểu diễn phụ thuộc; completion stages phối hợp kết quả.** Đừng để worker biến thành một thread đợi tác vụ con cần chính worker ấy mới bắt đầu. Trong Spring, hãy kiểm tra cả điểm chờ **ngầm trong `@Async` interceptor**, không chỉ `get/join` viết trực tiếp trong code.

### Tài liệu tham khảo

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — AsyncExecutionInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionInterceptor.html)
