# void phù hợp khi bên gọi không cần nhận kết quả trực tiếp

Trong lập trình bất đồng bộ với Spring Framework, có những công việc mà bên gọi chỉ cần **yêu cầu thực hiện**, không cần nhận trực tiếp giá trị kết quả từ lời gọi đó. Ví dụ: chủ động làm nóng một cache có thể tái tạo, thu thập một thống kê phụ trợ không ảnh hưởng giao dịch chính, hoặc cập nhật một thành phần phục vụ tối ưu hiệu năng. Với loại công việc phù hợp, một phương thức `@Async` có kiểu trả về `void` là lựa chọn đơn giản và rõ ý định.

Tuy nhiên, **`void` chỉ nói rằng phương thức không trả về giá trị**. Nó không có nghĩa phương thức tự chạy bất đồng bộ, đã hoàn thành thành công, có bảo đảm xử lý bền vững hay không thể phát sinh lỗi. Để thực thi bất đồng bộ bằng Spring, lời gọi phải đi qua cơ chế `@Async`/`TaskExecutor` đúng cách.

Bài học giải thích khi nào chọn `void`, nó khác `Future`/`CompletableFuture` ra sao, cách xử lý lỗi của `@Async void`, giới hạn vận hành và một ví dụ Java 17 chạy độc lập.

## 1. Hiểu đúng ý nghĩa của void

Phương thức Java thông thường:

~~~java
public void updateLocalState() {
    System.out.println("Updated");
}
~~~

không trả về một object kết quả. Nhưng **nó vẫn chạy đồng bộ** trên thread gọi cho đến khi method trở về hoặc ném exception. Chỉ đổi kiểu trả về sang `void` không tạo ra worker mới và không giảm thời gian chờ của caller.

Phương thức Spring:

~~~java
@Async("backgroundExecutor")
public void warmCache(String key) {
    // Công việc chạy trong executor nếu lời gọi được Spring intercept đúng cách.
}
~~~

là **đoạn minh họa đặt trong một Spring-managed bean**. Khi được gọi từ bên ngoài bean qua Spring proxy trong chế độ `@EnableAsync` phù hợp, interceptor đóng gói lời gọi thành task rồi gửi đến executor được chọn. Caller không nhận được `Future` từ method `void`, vì vậy không có handle trả về để `get()`, `join()`, `cancel()` hoặc đọc exception.

Có ba điều cần tách:

- **Không cần dữ liệu trả về:** caller không sử dụng giá trị tính toán của task. Đây là lý do hợp lệ để cân nhắc `void`.
- **Không cần biết khi nào kết thúc:** caller không cần chờ kết quả ngay trong luồng điều khiển hiện tại. Đây có thể là lý do thứ hai, nhưng hệ thống vẫn cần cách giám sát ở cấp vận hành.
- **Không cần đảm bảo xử lý:** là một yêu cầu **khác hẳn**. `@Async void` không tự quyết định độ bền, retry hay mức độ quan trọng của nhiệm vụ. Nghiệp vụ vẫn có thể cần cơ chế theo dõi, lưu trạng thái hoặc hàng đợi bền vững.

Từ “fire-and-forget” thường được dùng cho mô hình gọi rồi không chờ. Nó diễn tả hành vi của **caller**, không phải cam kết rằng task sẽ hoàn tất, lỗi được tự sửa hoặc công việc không thể mất.

## 2. Khi nào void là một lựa chọn phù hợp?

| Trường hợp | Mức độ phù hợp | Lý do |
| --- | --- | --- |
| Làm nóng cache có thể tạo lại khi cần | **Thường phù hợp** | Caller không cần giá trị trực tiếp, task có thể thử lại khi cần |
| Tính toán metadata phụ trợ, có thể bỏ qua khi quá tải | **Có thể phù hợp** | Không quyết định kết quả giao dịch chính, nhưng vẫn cần đo lỗi |
| Gửi thông báo không quan trọng, chấp nhận best-effort | **Có thể phù hợp** | API không cần đợi gửi xong; vẫn phải có chính sách lỗi, tải và retry |
| Ghi nhận một sự kiện kinh doanh bắt buộc lưu đầy đủ | **Không nên chỉ dựa vào @Async void in-memory** | Mất task khi crash/shutdown có thể gây sai nghiệp vụ |
| Thanh toán, trừ tiền, cập nhật tồn kho bắt buộc thành công | **Không phù hợp nếu chỉ gọi rồi bỏ qua** | Cần trạng thái, idempotency, retry có kiểm soát và khả năng xác nhận |
| Caller cần trả kết quả sau khi xử lý | **Không phù hợp** | Cần handle hoặc cơ chế trả trạng thái/kết quả khác |
| Caller cần nhận biết task lỗi hoặc hoàn tất | **Thường dùng CompletableFuture<Void> hay job id** | Không có dữ liệu nghiệp vụ trả về nhưng vẫn cần trạng thái hoàn thành |

Một nguyên tắc hữu ích: **“không cần giá trị trả về” không đồng nghĩa “không cần trách nhiệm đối với kết quả.”** Với việc quan trọng, việc caller không đợi trực tiếp vẫn có thể kết hợp hàng đợi/job store và endpoint tra cứu trạng thái. Chọn `void` dựa vào hợp đồng cần có giữa caller và nhiệm vụ, không chỉ vì muốn API trả response nhanh.

## 3. So sánh void, Future và CompletableFuture

Trong Spring, phương thức có `@Async` thường khai báo kiểu trả về `void` hoặc một dạng `Future` như `CompletableFuture<T>`.

| Kiểu trả về của phương thức @Async | Caller nhận được gì? | Theo dõi hoàn tất/lỗi từ caller? | Khi thích hợp |
| --- | --- | --- | --- |
| `void` | Không có Future/result handle | **Không** qua return value; cần logging, handler hoặc trạng thái ngoài | Best-effort, caller không cần phản hồi trực tiếp |
| `Future<T>` | Future đại diện kết quả bất đồng bộ | `get()`, `isDone()`, `cancel()` | Cần biết hoàn tất/nhận kết quả, chấp nhận API Future |
| `CompletableFuture<T>` | Future có khả năng gắn callback và composition | `whenComplete`, `exceptionally`, `thenApply`… | Cần ghép các bước, xử lý lỗi bất đồng bộ |
| `CompletableFuture<Void>` | Không có dữ liệu nghiệp vụ nhưng có handle hoàn tất | **Có**, thông qua completion/exception của Future | Không cần payload nhưng vẫn cần biết thành công/thất bại |

Điểm dễ nhầm là `CompletableFuture<Void>` **không giống** `void`. Cả hai không trả dữ liệu nghiệp vụ, nhưng phương thức thứ nhất trả một **đối tượng biểu diễn trạng thái** cho caller.

Ví dụ Spring tích hợp:

~~~java
@Async("backgroundExecutor")
public CompletableFuture<Void> warmWithCompletion(String key) {
    // Thực hiện công việc trong worker.
    System.out.println("Warming: " + key);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **method minh họa**, không phải chương trình `javac` độc lập; phải đặt trong Spring-managed bean cùng cấu hình async. Với cách này, Spring proxy trả một `CompletableFuture<Void>` để caller theo dõi. Bên trong target method, `completedFuture(null)` là kết quả tạm thời sau khi phần công việc của method đã thực hiện; Spring proxy mới cung cấp future bất đồng bộ cho caller.

Nếu method chạy lỗi, caller có thể đăng ký:

~~~java
CompletableFuture<Void> result = worker.warmWithCompletion("catalog");
result.whenComplete((ignored, error) -> {
    if (error != null) {
        System.err.println("Background work failed: " + error);
    }
});
~~~

Đây cũng là **đoạn caller minh họa**, giả định `worker` là bean đã inject từ Spring. Vì yêu cầu là biết completion/error, dùng `CompletableFuture<Void>` hợp lý hơn `void` dù không có dữ liệu trả về.

### 3.1. TaskExecutor.execute(...) và ExecutorService.submit(...) không giống nhau

API Java nền tảng:

~~~java
executor.execute(runnable);             // Không trả handle: void
Future<?> future = service.submit(task); // Trả handle Future
~~~

Đây là **hai lời gọi minh họa**, cần có biến `executor` và `service` tương ứng. `execute(Runnable)` trả `void` theo hợp đồng của `Executor`. `submit(...)` của `ExecutorService` trả `Future`. Trong Spring, `TaskExecutor` tập trung vào `execute(...)`, còn một số extension như `AsyncTaskExecutor` hỗ trợ submit để caller nhận Future.

Với `execute`, task exception được quan sát theo cơ chế của executor/caller thread, không tự được đóng gói thành Future trả về. Với `submit`, exception thường được giữ trong `Future` và được bộc lộ khi caller gọi `get()`. Đừng suy ra hai API có cùng hành vi lỗi chỉ vì cả hai chạy trên thread pool.

## 4. Timeline: void không có nghĩa công việc đã xong

~~~text
HTTP thread                  Spring proxy / executor           Worker thread
    |                                  |                             |
    |-- cacheService.warm("A") ------->|                             |
    |                                  |-- nhận task / queue --------|
    |<-- lời gọi void trả về ----------|                             |
    |                                  |       chờ worker            |
    |-- trả HTTP response              |                             |
    |                                  |-- giao task ---------------->|
    |                                  |                         bắt đầu warm
    |                                  |                         thực thi
    |                                  |                         xong hoặc lỗi
~~~

Kịch bản trên giả định pool có queue và worker bận. Task cũng có thể bắt đầu **trước khi lời gọi `void` trên caller trả về** nếu executor có worker rảnh. Ngoài ra, với `SyncTaskExecutor`, task chạy đồng bộ; với chính sách `CallerRunsPolicy` khi quá tải, task có thể chạy trên caller.

Vì vậy câu chính xác là: **`@Async void` cho phép caller không cần chờ và không nhận trực tiếp kết quả hoàn tất nếu việc submit được xử lý bất đồng bộ**; không có bảo đảm “task chắc chắn bắt đầu sau khi caller trả về”.

Các mốc cần đo độc lập là `t_submit`, `t_start`, `t_finish`. Thời gian từ submit đến start có thể nằm trong queue. Nếu API trả nhanh mà queue chờ nhiều giây, điều đó vẫn ảnh hưởng tới tính kịp thời của xử lý, dù caller không nhận Future.

## 5. Java 17 chạy độc lập: execute trả void, worker vẫn chạy sau đó

Ví dụ dùng Java chuẩn để quan sát sự khác biệt, không cần Spring. Hai latch cho phép xác nhận task đã bắt đầu và giữ nó chưa thể kết thúc trước khi caller kiểm tra.

Tạo tệp **`VoidExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class VoidExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    System.out.println("3. Background task finished");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }
            System.out.println("1. execute() returned without a Future");
            System.out.println("2. Task finished? " + (finished.getCount() == 0));
            release.countDown();
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not finish");
            }
            System.out.println("4. Main observed completion with CountDownLatch");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 VoidExecutorDemo.java
java VoidExecutorDemo
~~~

Stdout **đã xác minh** khi biên dịch với `--release 17`:

~~~text
1. execute() returned without a Future
2. Task finished? false
3. Background task finished
4. Main observed completion with CountDownLatch
~~~

Giải thích:

1. `execute(...)` không trả `Future`; callback có thể đang thực thi hoặc chờ. Chương trình gọi `started.await(...)` để chắc chắn worker đã bắt đầu.
2. Worker đợi `release`; do đó tại thời điểm main in dòng thứ hai, task chắc chắn **chưa hoàn tất**.
3. Main mở latch; worker in thông báo và giảm `finished`.
4. Chỉ nhờ cơ chế đồng bộ được bổ sung có chủ đích (`finished.await(...)`), main mới xác minh được task đã kết thúc. **Đây không phải một kết quả mà `execute(void)` trả về.**

Ví dụ trình diễn một trường hợp caller chủ động **thêm cách theo dõi** dù API execute tự nó không có Future. Nếu caller không cần biết completion, nó có thể không chờ latch; nhưng trong bài test, latch giúp tạo kết quả xác định. `shutdownNow()` chỉ để giải phóng worker khi chương trình kết thúc, không phải cơ chế bảo đảm mọi tác vụ trong ứng dụng thật đã xử lý thành công.

## 6. Spring Framework: ví dụ @Async void với executor có giới hạn

Các tệp sau là **mã tích hợp** cho Java 17+, Spring Framework 6.x (hoặc ứng dụng Spring Boot tương thích) có `spring-context`, xử lý annotation và component scanning. Chúng **không biên dịch chỉ bằng một câu lệnh `javac` thiếu Spring dependencies**. Mỗi class ở một tệp có cùng tên trong package `example.concurrency`.

### 6.1. Cấu hình bật @Async và chọn executor

Tệp `AsyncConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Bean("bestEffortExecutor")
    public ThreadPoolTaskExecutor bestEffortExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("best-effort-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, args) ->
                System.err.println("Async void failed in "
                        + method.getName() + ": "
                        + exception.getClass().getSimpleName());
    }
}
~~~

Giải thích:

- `@EnableAsync` bật cơ chế interceptor cho `@Async` trong Spring ApplicationContext.
- `@Bean("bestEffortExecutor")` đặt tên rõ ràng. `@Async("bestEffortExecutor")` chọn bean này thay vì phụ thuộc vào default executor. Spring quản lý initialization/lifecycle của bean executor.
- `core=2`, `max=4`, `queueCapacity=20` là số minh họa. Sau core, executor thường ưu tiên enqueue. Pool bão hòa có thể từ chối task, không phải mọi lời gọi đều sẽ được nhận.
- `AbortPolicy` làm lỗi từ chối rõ ràng. Trong `ThreadPoolTaskExecutor`, ngoại lệ được bộc lộ theo hợp đồng Spring `TaskExecutor`, thường là `TaskRejectedException`.
- `getAsyncUncaughtExceptionHandler()` đăng ký **handler cho exception không được bắt trong target `@Async void`**. Ví dụ chỉ in tên method và loại lỗi; production nên dùng structured logging/metrics, phân loại mức độ và giới hạn dữ liệu nhạy cảm.

`AsyncConfigurer` được xử lý sớm trong bootstrap; ví dụ không inject các bean phức tạp vào handler. Nếu ứng dụng cần logger hoặc hệ thống cảnh báo, triển khai nhất quán với lifecycle của Spring. Chỉ nên có cấu hình async toàn cục có chủ đích, tránh nhiều cấu hình cùng tranh quyền quyết định handler.

### 6.2. Service không cần trả kết quả trực tiếp

Tệp `CacheWarmService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CacheWarmService {
    private final ConcurrentMap<String, Boolean> warmed =
            new ConcurrentHashMap<>();

    @Async("bestEffortExecutor")
    public void warm(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Cache key must not be blank");
        }
        // Mô phỏng công việc làm nóng cache có thể tạo lại.
        warmed.put(key, Boolean.TRUE);
    }

    public boolean isWarm(String key) {
        return Boolean.TRUE.equals(warmed.get(key));
    }
}
~~~

Đây là ví dụ đơn giản có thể biên dịch **trong ứng dụng Spring đã khai báo dependencies**, nhưng không đại diện cho một hệ thống cache nhiều node. Map chỉ nằm trong bộ nhớ **một application instance**. Nghiệp vụ thực tế có thể gọi repository hoặc cache backend, dùng timeout khi có I/O và tuân theo chính sách retry/overload của hệ thống.

Khi bean khác gọi `cacheWarmService.warm("catalog")` qua Spring proxy:

1. Spring submit lời gọi vào `bestEffortExecutor`.
2. Caller không nhận một `Future` vì chữ ký là `void`.
3. Worker có thể thực thi ngay hoặc phải chờ queue.
4. Khi chạy, `warm(...)` cập nhật map. Caller không được thông báo trực tiếp khi nó xong.
5. Nếu `key` không hợp lệ khiến method ném exception **trong worker**, exception được chuyển đến `AsyncUncaughtExceptionHandler` thay vì quay về stack của caller sau khi đã gửi task thành công.

Method `isWarm(...)` chỉ nhằm minh họa một **kênh kiểm tra trạng thái riêng**, không phải một acknowledgment tự động của phương thức `void`. Trong hệ thống thật, cần phân biệt rõ trạng thái chưa nhận, đang đợi, đang chạy, thành công và thất bại nếu trạng thái đó là một yêu cầu nghiệp vụ.

### 6.3. Caller từ controller và ý nghĩa của HTTP 202

Tệp `CacheWarmController.java` (cần Spring Web MVC):

~~~java
package example.concurrency;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cache")
public class CacheWarmController {
    private final CacheWarmService cacheWarmService;

    public CacheWarmController(CacheWarmService cacheWarmService) {
        this.cacheWarmService = cacheWarmService;
    }

    @PostMapping("/warm/{key}")
    public ResponseEntity<Void> requestWarm(@PathVariable String key) {
        if (key.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        try {
            cacheWarmService.warm(key);
            return ResponseEntity.accepted().build();
        } catch (TaskRejectedException ex) {
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).build();
        }
    }
}
~~~

Điều quan trọng là **controller gọi một bean khác**; lời gọi đi qua Spring proxy của `CacheWarmService`. `202 Accepted` ở đây chỉ mô tả việc **yêu cầu đã được submit thành công theo cơ chế executor trong bộ nhớ**. Không hứa “cache đã được làm nóng” hoặc “công việc chắc chắn sẽ sống qua restart”.

Cần ghi nhớ ranh giới của ví dụ:

- Bắt `TaskRejectedException` ở caller nhằm xử lý lỗi **trước/khi nhận task** do executor không còn khả năng tiếp nhận. Tùy cấu hình executor/rejection policy, một số cơ chế có thể chạy task trên caller hoặc bỏ task mà không ném lỗi; phải chọn policy có chủ đích.
- Nếu worker được nhận nhưng sau đó ném exception, HTTP response **đã gửi không tự đổi thành 500**. Trường hợp đó được quan sát bởi handler hoặc kênh trạng thái độc lập.
- Việc `warm(...)` hoàn tất rất nhanh có thể xảy ra **trước khi controller trả 202**, nhưng lời gọi `void` không cung cấp bảo đảm đó.
- Nếu nghiệp vụ đòi hỏi chỉ trả 202 sau khi công việc đã được lưu bền vững, controller phải ghi vào queue/job store bền vững trước, rồi mới xác nhận theo hợp đồng API.

Đối với bài toán cache ấm có thể tái tạo, cách thực hiện best-effort này hợp lý về mặt minh họa. Không dùng nó nguyên xi cho thanh toán, audit bắt buộc hoặc tác vụ không được phép mất.

## 7. Lỗi ở @Async void đi đâu?

Đây là khác biệt kỹ thuật quan trọng nhất giữa `void` và `Future` khi thiết kế hợp đồng trả về.

### 7.1. Exception bên trong worker không tự quay lại caller

Ví dụ:

~~~java
@Async("bestEffortExecutor")
public void sendBestEffort(String id) {
    throw new IllegalStateException("Simulated background failure");
}
~~~

Đây là một **method minh họa** đặt trong bean Spring, không phải class hoàn chỉnh độc lập. Nếu được gọi qua proxy và executor nhận task, exception xảy ra **trên worker**. Caller đã đi tiếp nên không thể dùng `try/catch` quanh lời gọi để đón exception thực thi đó như lỗi đồng bộ.

Với phương thức `@Async` trả `Future`, exception thực thi có thể được biểu diễn qua Future để caller quan sát bằng `get()` hoặc callback. Với `void`, Spring hỗ trợ `AsyncUncaughtExceptionHandler`. Nếu không cấu hình riêng, handler mặc định của Spring ghi log exception; nó không biến lời gọi thành Future.

### 7.2. Hai loại lỗi phải có kênh xử lý riêng

| Lỗi | Xảy ra ở đâu? | Caller có thể xử lý như thế nào? |
| --- | --- | --- |
| Dữ liệu đầu vào không hợp lệ trước khi submit | Thread caller, nếu validate ở biên | Trả 400/validation error đồng bộ |
| Executor từ chối task lúc submit | Lời gọi qua Spring proxy, trước khi công việc được nhận | Catch `TaskRejectedException` nếu policy ném lỗi; trả 503/throttle |
| Lỗi nghiệp vụ trong phương thức `@Async void` | Worker sau khi đã nhận task | Handler/log/metrics, retry hoặc trạng thái độc lập; không thể đổi response đã trả |
| JVM chết hoặc instance bị terminate sau khi nhận task | Ngoài đường exception bình thường của method | Khôi phục công việc từ job store/queue bền vững nếu nghiệp vụ cần |
| Task bị gián đoạn do shutdown/cancellation | Trong quá trình chạy/đóng pool tùy cấu hình | Xử lý interruption và quyết định task cần được retry/khôi phục không |

Cần phân biệt lỗi từ task **đã được nhận** và lỗi **không được nhận**. `AsyncUncaughtExceptionHandler` xử lý exception chưa được bắt từ phương thức `@Async void`; không phải hệ thống thay thế cho mọi trường hợp pool bị reject, crash hoặc task chưa bao giờ được chạy.

### 7.3. Handler không phải cơ chế retry tự động

Handler nhận thông tin exception, `Method` và arguments. Nó có thể log, phát tín hiệu metric hoặc gửi cảnh báo qua hệ thống riêng. **Nó không tự chạy lại method** và không bảo đảm công việc được xử lý thành công.

Nếu tự implement retry, phải xem xét idempotency, số lần thử, backoff/jitter, timeout và nguy cơ tạo bão retry khi downstream lỗi. Nếu handler gửi tiếp việc sang cùng một executor đang bão hòa, nó có thể làm quá tải nặng hơn.

Không in nguyên arguments trong log/alert một cách mặc định: chúng có thể chứa email, token, dữ liệu cá nhân hoặc payload lớn. Trong ví dụ ở mục 6, handler chỉ ghi tên method và loại exception để giữ minh họa gọn.

## 8. Những trường hợp void không đáp ứng đủ yêu cầu

### 8.1. Cần biết thành công/thất bại dù không cần payload

Dùng `CompletableFuture<Void>`. Caller có thể:

~~~java
CompletableFuture<Void> future = worker.warmWithCompletion("catalog");
future.whenComplete((unused, error) -> {
    if (error != null) {
        System.err.println("Warm failed: " + error);
    } else {
        System.out.println("Warm completed");
    }
});
~~~

Đoạn này giả định method và bean `worker` ở mục 3. Nếu `future.join()` hoặc `get()` ngay, caller bị chặn tới khi xong. Không cần chặn nếu chỉ muốn gắn callback; đó là lợi ích quan trọng của completion stage.

### 8.2. Cần hủy công việc

`@Async void` không trả handle để caller gọi `cancel(...)` trên chính invocation đó. Nếu hợp đồng cần hủy, có thể dùng `Future`/`CompletableFuture`, hoặc một job id và cơ chế hủy riêng. Ngay cả khi có Future, `cancel(true)` chỉ yêu cầu ngắt khi task và thư viện hỗ trợ; không tự hoàn tác side effect đã xảy ra.

### 8.3. Cần trạng thái liên tục hoặc kết quả sau này

Không nhất thiết phải chờ trong HTTP request, nhưng có thể trả job id và để khách hàng gọi endpoint kiểm tra trạng thái. Khi đó hệ thống cần lưu ít nhất `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` (và trạng thái hủy nếu có), cùng thời điểm, lỗi và quy tắc giữ thông tin. Job id và job store là hợp đồng nghiệp vụ độc lập với return type của method worker.

### 8.4. Công việc không được phép mất

Một executor in-memory chỉ nhận task vào worker/queue của process. Nếu JVM crash hoặc app bị kill trước khi task chạy xong, lời gọi `void` không có cơ chế khôi phục tự động. Với công việc bắt buộc thực hiện, cần cân nhắc queue bền vững, transactional outbox, job store, retry/idempotency và cơ chế phục hồi rõ ràng.

Không nên gọi `void` là “không an toàn” theo bản thân kiểu dữ liệu: một worker `void` vẫn có thể đọc từ queue bền vững do thành phần khác điều phối. Vấn đề là **người gọi không có return handle**, còn độ tin cậy phụ thuộc toàn bộ kiến trúc.

## 9. Sai lầm về proxy, transaction và ngữ cảnh thread

### 9.1. Self-invocation khiến @Async không được áp dụng

Trong cấu hình proxy mặc định:

~~~java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Lời gọi nội bộ, thường KHÔNG đi qua @Async proxy.
    }

    @Async("bestEffortExecutor")
    public void inner() {
        System.out.println("Inside worker?");
    }
}
~~~

Đây là **đoạn mã minh họa trong Spring**, với imports tương ứng. Việc `outer()` gọi trực tiếp `inner()` trên cùng instance thường bỏ qua proxy. `inner()` có thể chạy đồng bộ trên caller dù được đánh dấu `@Async`. Cách thông thường là tách method async sang một bean khác và gọi thông qua bean đã được Spring quản lý, như `CacheWarmController → CacheWarmService` ở trên.

Không dùng `@Async` trên lifecycle callback như `@PostConstruct` với kỳ vọng Spring sẽ tự chạy nền theo cách thông thường. Nếu cần kích hoạt công việc sau startup, bố trí một bean điều phối khác và xem xét lifecycle/readiness phù hợp.

### 9.2. Context của thread không tự được chuyển sang worker

Một số thông tin trong Spring ứng dụng gắn với thread hiện tại, chẳng hạn transaction context, request context, MDC hoặc security context. Khi `@Async` chuyển sang worker khác, **không được mặc định** coi chúng tự động được chuyển đầy đủ và an toàn.

Ví dụ caller đang trong transaction không có nghĩa transaction thread-bound của caller tự động tiếp tục ở worker. Nếu công việc async cần transaction riêng, thiết kế ranh giới transaction **trong chính luồng xử lý async** bằng cấu hình Spring phù hợp. Với trace/MDC, có thể dùng task decorator hoặc cơ chế context propagation đã được thư viện xác định.

### 9.3. Kiểu void không bảo đảm chạy ngoài caller

`TaskExecutor` có các implementation khác nhau. `SyncTaskExecutor` chạy đồng bộ trên thread gọi. `CallerRunsPolicy` của `ThreadPoolExecutor` có thể chạy task trên caller khi pool bão hòa và chưa shutdown, thay vì từ chối.

Vì thế “dùng `void` để giảm latency” chỉ đúng nếu đường thực thi được cấu hình thực sự phù hợp và không chặn caller. Đo latency request, thời gian submit, active workers và queue wait để kiểm chứng.

## 10. Theo dõi công việc void trong môi trường vận hành

Dù caller không cần nhận kết quả, hệ thống vẫn nên biết task đã thực sự được xử lý hay chưa. Một tập quan sát cơ bản:

| Chỉ số/thông tin | Nơi đo | Ý nghĩa |
| --- | --- | --- |
| Số lời gọi submit | Biên caller | Có bao nhiêu yêu cầu xử lý nền |
| Số lần submit bị từ chối | Biên proxy/executor | Phát hiện quá tải hoặc shutdown |
| Thời gian chờ queue | Từ lúc nhận đến khi worker bắt đầu | Đo độ trễ trước khi xử lý thật |
| Số task đang chạy, queue depth, pool size | Executor | Giới hạn concurrency và backlog |
| Thời gian thực thi | Worker bắt đầu → kết thúc | Phát hiện I/O chậm hoặc contention |
| Số task thành công/thất bại | Trong method, handler hoặc hệ thống job | Phân biệt “được nhận” và “xử lý xong” |
| Correlation/job id | Caller và worker | Ghép log/trace của một tác vụ |
| Shutdown/timeout/retry | Lifecycle và downstream | Phát hiện việc bị cắt ngang hoặc lặp lại |

Với `ThreadPoolTaskExecutor`, có thể theo dõi `getActiveCount()`, `getPoolSize()`, `getQueueSize()` (ở phiên bản Spring hỗ trợ) và các metric được instrument tương ứng. Chỉ nhìn số task submit không thể kết luận số task đã hoàn tất.

Khi thiết lập metrics, nên chọn tên rõ: `submitted_total`, `accepted_total`, `rejected_total`, `started_total`, `completed_total`, `failed_total`. Đây là **tên metric gợi ý cho ứng dụng**, không phải danh sách API metric mặc định do Spring tự xuất ra.

### 10.1. Shutdown và triển khai lại

Khi application context đóng, executor có lifecycle shutdown theo cấu hình của phiên bản Spring. Thời gian chờ task, hành vi nhận task mới và việc ngắt tác vụ cần được chọn phù hợp với yêu cầu. Không kết luận “đã submit thì task chắc chắn hoàn tất trước pod restart”.

Nếu task chỉ là cache warm có thể làm lại, mất một lượt khi shutdown có thể chấp nhận được. Nếu task bắt buộc, dùng cơ chế bền vững hơn thay vì chỉ kéo dài thời gian chờ đóng pool.

## 11. Kiểm thử @Async void đúng cách

Vì caller không có Future, test kiểm tra được completion cần một **tín hiệu đồng bộ hoặc spy/collaborator có chủ đích**:

1. Dùng test ApplicationContext thật có `@EnableAsync` và executor được chọn; gọi method thông qua bean proxy, không gọi `new Service()`.
2. Inject một cộng tác viên kiểm thử (hoặc latch) để xác nhận target method đã chạy; dùng timeout hữu hạn khi chờ để test không treo vô hạn.
3. Kiểm tra nhánh thành công và nhánh exception của method `void`; với exception, xác minh handler được gọi hoặc metric lỗi tăng. Không chờ `try/catch` của caller thấy lỗi phát sinh trên worker.
4. Mô phỏng executor không nhận thêm task để kiểm tra chính sách rejection ở caller. Không cần tạo tải lớn tùy tiện; một executor có giới hạn nhỏ với latch đủ tái hiện.
5. Kiểm tra shutdown/restart nếu hệ thống có yêu cầu không mất việc; test đơn vị của service không chứng minh được độ bền của queue.

Nếu test dùng `SyncTaskExecutor`, code có thể chạy ngay trên thread test. Điều đó hữu ích để kiểm tra logic đơn giản nhưng **không kiểm chứng được hành vi queue và timing của async thật**. Nên có integration test riêng cho đường đi qua proxy và executor.

## 12. Những hiểu nhầm cần tránh

**“Method trả void nên chạy nền.”** Sai. `void` chỉ là kiểu trả về; cần cấu hình executor và interception đúng nếu muốn bất đồng bộ.

**“Không có Future nghĩa là task chắc chắn không lỗi.”** Sai. Exception trong worker vẫn xảy ra; với `@Async void` cần handler/log/metrics hoặc cơ chế nghiệp vụ riêng.

**“Caller bắt `Exception` quanh method @Async void là bắt hết lỗi.”** Sai. Caller thường chỉ bắt được lỗi xảy ra ở bước gửi, ví dụ rejection; lỗi thực thi sau khi task được nhận đi theo đường xử lý async.

**“Trả HTTP 202 nghĩa là task đã xử lý thành công.”** Sai. Cần phân biệt đã nhận với hoàn tất, và in-memory submit với durable acceptance.

**“Không có dữ liệu cần trả thì phải dùng void.”** Không bắt buộc. `CompletableFuture<Void>` tốt hơn nếu caller cần thông tin hoàn tất, exception hoặc cơ chế kết hợp thêm tác vụ.

**“@Async trong cùng bean vẫn chạy async khi gọi this.method().”** Sai trong proxy mode mặc định; lời gọi nội bộ không đi qua proxy.

**“void fire-and-forget không cần logging hoặc retry.”** Sai. Yêu cầu xử lý lỗi phụ thuộc nghiệp vụ; không nhận kết quả trực tiếp vẫn cần khả năng quan sát và chính sách quá tải.

**“Có thể hủy một invocation @Async void bằng Future.”** Không có Future trả về từ method `void`; cần thiết kế handle riêng hoặc chuyển sang Future nếu hợp đồng yêu cầu hủy.

**“Mọi task gửi vào executor đều chạy ngay.”** Sai. Queue, core/max, CPU/I/O và tài nguyên downstream quyết định thời điểm thực sự bắt đầu.

## 13. Tình huống lựa chọn theo yêu cầu nghiệp vụ

Một sản phẩm có chức năng tạo báo cáo và muốn gọi thêm tác vụ phụ:

- **Làm nóng cache dữ liệu báo cáo đã có thể sinh lại:** caller không cần biết kết quả ngay, thất bại có thể được ghi metric và thử lại ở lượt sau. `@Async void` là phương án hợp lý nếu đã kiểm soát executor và hiểu rủi ro mất task.
- **Tạo file báo cáo người dùng sẽ tải xuống:** caller cần biết report id, trạng thái và link khi hoàn thành. Chỉ `@Async void` không đủ hợp đồng. Có thể dùng job id/status store, hoặc `CompletableFuture<Report>` cho workflow trong cùng process.
- **Gửi biên lai giao dịch bắt buộc:** caller có thể không cần chờ email gửi xong, nhưng hệ thống phải biết biên lai nào chưa gửi và phải retry. Queue bền vững/outbox với trạng thái và idempotency phù hợp hơn một lời gọi `@Async void` thuần trong bộ nhớ.
- **Cập nhật counter phụ trợ với sai số nhỏ được chấp nhận:** `void` có thể đáp ứng nếu metric thất bại được theo dõi và tốc độ gửi task không vượt năng lực của pool.

Quy tắc ra quyết định:

~~~text
Caller có cần kết quả nghiệp vụ ngay?
    |
    +-- Có --> Future<T> / CompletableFuture<T> hoặc xử lý đồng bộ phù hợp
    |
    +-- Không --> Có cần biết completion/error/cancel qua return handle?
                     |
                     +-- Có --> CompletableFuture<Void> / job id + trạng thái
                     |
                     +-- Không --> Công việc có được phép best-effort/làm lại?
                                      |
                                      +-- Có --> @Async void + handler + metrics
                                      |
                                      +-- Không --> Thiết kế tiếp nhận bền vững,
                                                   retry/idempotency và trạng thái
~~~

Đây là sơ đồ chọn hợp đồng, không phải luật của một framework. Cùng một nghiệp vụ có thể chọn mô hình khác tùy SLA, mức độ quan trọng và cách hệ thống đã lưu task.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một phương thức Java trả `void` có mặc nhiên bất đồng bộ không?

**Đáp án:** không. Kiểu `void` không tạo thread và không tách lời gọi. Trong Spring cần cơ chế `@Async` và executor được cấu hình, caller phải đi qua interceptor/proxy.

**Câu 2.** Caller gọi `@Async void warm()` và lời gọi trả về. Có biết việc làm nóng đã thành công chưa?

**Đáp án:** không. Chỉ biết lời gọi đã trở về; nếu task được submit, nó có thể đang queue, chạy hoặc đã xong. Muốn biết thành công cần kênh quan sát khác hoặc Future.

**Câu 3.** Tại sao `CompletableFuture<Void>` đôi khi tốt hơn `void` dù không trả payload?

**Đáp án:** Future cung cấp handle để theo dõi hoàn tất, lỗi, gắn callback và yêu cầu hủy khi hỗ trợ.

**Câu 4.** Exception ném từ target `@Async void` được truyền đến controller qua `try/catch` không?

**Đáp án:** không theo đường đồng bộ sau khi task đã được submit thành công. Spring dùng `AsyncUncaughtExceptionHandler` cho exception không bắt từ method `void`; rejection ở bước submit là chuyện riêng.

**Câu 5.** Nếu pool bão hòa, phương thức `@Async void` luôn trả bình thường không?

**Đáp án:** không. Với `AbortPolicy`, submit có thể thất bại và Spring có thể ném `TaskRejectedException` tại caller.

**Câu 6.** Vì sao không dùng `@Async void` in-memory đơn thuần để bảo đảm thanh toán được xử lý?

**Đáp án:** vì không có hợp đồng kết quả trực tiếp hoặc bảo đảm bền vững; crash có thể làm mất task. Cần trạng thái, idempotency, retry và tiếp nhận bền vững phù hợp.

**Câu 7.** Trong ví dụ Java 17, nhờ đâu main biết task đã hoàn tất dù `execute` trả `void`?

**Đáp án:** nhờ `CountDownLatch finished` được bổ sung riêng và `await(...)`. Đó không phải giá trị trả về của `execute`.

**Câu 8.** Có nên đo số task thành công bằng số lời gọi `@Async void` ở caller không?

**Đáp án:** không. Cần tách submitted, rejected, started, completed và failed; caller chỉ đo được một phần đường đi.

## 15. Tài liệu tham khảo

- Spring Framework — Task Execution and Scheduling, `@Async` và xử lý exception: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 API — `@Async` và các kiểu trả về được hỗ trợ: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework 6.2 API — `@EnableAsync`, `AsyncConfigurer`, xử lý lỗi `void` và proxy: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.2 API — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ExecutorService` và `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
