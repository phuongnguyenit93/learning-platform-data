# Thứ tự nhận tác vụ trong nhóm luồng: tạo core thread, xếp hàng, mở rộng rồi từ chối

Khi gửi một tác vụ đến nhóm luồng (thread pool), việc có “còn chỗ” không chỉ phụ thuộc vào số luồng. Với cơ chế `ThreadPoolExecutor` của Java, cũng là nền tảng của `ThreadPoolTaskExecutor` trong Spring Framework, quyết định nhận tác vụ thường theo trình tự:

**Tạo worker trong giới hạn `corePoolSize` → thử đưa tác vụ vào queue → nếu không thể xếp hàng thì mở thêm worker đến `maxPoolSize` → nếu vẫn không nhận được thì áp dụng chính sách từ chối (rejection).**

Đây là **thứ tự ưu tiên khi nhận task**, không phải bốn giai đoạn bắt buộc mà mọi task phải đi qua. Một tác vụ được worker thực thi ngay có thể chưa từng nằm trong queue. Tác vụ khác có thể xếp hàng trong khi executor vẫn chưa dùng hết `maxPoolSize`.

Hiểu trình tự này giúp tránh lỗi cấu hình rất phổ biến: **tăng `maxPoolSize` nhưng không thấy pool mở thêm luồng vì queue vẫn còn chỗ**.

## 1. Những thành phần quyết định việc nhận tác vụ

Trong Java, `ThreadPoolExecutor` quản lý hai nơi đặt công việc:

- **Worker threads:** luồng thực sự lấy tác vụ và chạy `Runnable`/`Callable`. Một worker bận I/O hoặc chờ lock vẫn đang chiếm một vị trí thực thi.
- **Work queue:** nơi lưu tác vụ đã được executor chấp nhận nhưng chưa có worker lấy ra để chạy. Với queue có giới hạn, khi đầy, executor phải chọn phương án khác.
- **Rejection handler:** chính sách xử lý khi một tác vụ không được chấp nhận, chẳng hạn pool đã dừng hoặc số worker và queue đều không có khả năng nhận thêm.

Các tham số quan trọng:

| Tham số | Vai trò | Cần hiểu chính xác |
| --- | --- | --- |
| `corePoolSize` | Số worker lõi mà pool ưu tiên tạo khi có tác vụ mới | **Không có nghĩa** tất cả core threads đã tồn tại ngay lúc khởi tạo |
| `maxPoolSize` | Số worker tối đa pool được phép tạo | Chủ yếu phát huy tác dụng khi queue không nhận thêm task |
| `queueCapacity` | Số task tối đa được xếp chờ trong hàng đợi theo cấu hình Spring | Dương → bounded `LinkedBlockingQueue` (với dung lượng đã cho); bằng 0 → `SynchronousQueue` để bàn giao trực tiếp |
| `keepAliveSeconds` | Thời gian nhàn rỗi trước khi worker vượt core có thể được thu hồi | Mặc định không làm core worker hết hạn; có cấu hình cho phép core timeout |
| `RejectedExecutionHandler` | Hành vi khi không nhận được tác vụ | Từ chối không nhất thiết có nghĩa ném lỗi; tùy policy |
| Trạng thái executor | `RUNNING`, quá trình shutdown và trạng thái kết thúc | Pool đã shutdown có thể từ chối task **ngay cả khi chưa đầy** |

Trong `ThreadPoolExecutor` thuần Java, queue cụ thể được truyền qua constructor. Trong `ThreadPoolTaskExecutor` của Spring, `setQueueCapacity(...)` chọn kiểu queue: dung lượng **lớn hơn 0** tạo `LinkedBlockingQueue`; dung lượng **0 hoặc âm** tạo `SynchronousQueue` (thực tế nên dùng 0 để biểu đạt ý định bàn giao trực tiếp).

### Core threads có được tạo sẵn không?

Thông thường `ThreadPoolExecutor` tạo core workers **theo nhu cầu khi task đến**, không nhất thiết tạo đủ lúc khởi động. Có thể dùng `prestartCoreThread()`/`prestartAllCoreThreads()` trong Java, hoặc `setPrestartAllCoreThreads(true)` trong Spring, nếu cần tạo trước.

Vì vậy câu “tạo luồng cơ bản trước” nghĩa là **ưu tiên tạo worker trong giới hạn core khi nhận task mới và số worker hiện có còn thấp hơn core**, chứ không có nghĩa JVM phải tạo tất cả core workers ở thời điểm khởi tạo bean.

## 2. Thuật toán tiếp nhận task của ThreadPoolExecutor

Giả sử executor còn đang chạy và có `corePoolSize ≤ maxPoolSize`.

~~~text
             execute(task)
                    |
                    v
         pool còn dưới corePoolSize?
                /            \
              CÓ             KHÔNG
              |                |
     thử tạo core worker       v
        để chạy task       thử queue.offer(task)
              |             /           \
     tạo thành công?      THÀNH CÔNG    KHÔNG NHẬN
         /     \             |              |
        CÓ    KHÔNG          v              v
        |       |      kiểm tra lại     thử tạo worker
    đã nhận     +----> trạng thái       tới maxPoolSize
        |               executor         /       \
        v                   |         thành công thất bại
      chạy task        nếu shutdown          |        |
                       thì loại khỏi         v        v
                       queue và reject     chạy task reject
~~~

Sơ đồ là mô hình học tập của hàm `execute(...)`, bỏ qua một số nhánh kiểm tra cạnh tranh. Quy trình chính xác có kiểm tra lại trạng thái sau khi enqueue, bảo đảm có ít nhất một worker khi queue chứa việc mà worker count bằng 0, và xử lý cạnh tranh với shutdown. Không nên xem sơ đồ như một chuỗi thao tác nguyên tử, cố định cho mọi lần gọi đồng thời.

### Bước 1 — Ưu tiên tạo worker trong giới hạn core

Nếu số worker hiện có **nhỏ hơn `corePoolSize`**, executor cố tạo worker mới để chạy chính task vừa nhận. Quy tắc này được ưu tiên hơn xếp queue, **kể cả có worker khác đang rảnh** trong một số tình huống. Nếu tạo worker thành công, task được nhận và không cần thử xếp hàng.

Ví dụ core = 2, pool chưa có worker. Hai tác vụ tới khi tác vụ trước vẫn chạy: tác vụ thứ nhất làm pool tăng lên 1 worker; tác vụ thứ hai làm pool tăng lên 2 workers.

### Bước 2 — Khi đã tới core, ưu tiên xếp hàng

Nếu số worker đã đạt hoặc vượt core, executor gọi thao tác tương đương `workQueue.offer(task)` để **thử xếp hàng mà không chờ đến khi có chỗ**.

- Nếu queue nhận được task, task được chấp nhận và chờ worker lấy.
- Điều này xảy ra **trước** khi mở thêm worker đến max. Vì vậy pool có thể giữ 2 workers trong khi `maxPoolSize=20` và queue đang tích lũy hàng trăm task.
- Sau khi enqueue, executor cần kiểm tra lại trạng thái. Nếu một lệnh shutdown xảy ra đồng thời và task có thể được gỡ khỏi queue, executor sẽ từ chối task đó. Nếu pool không còn worker, nó phải cố khởi động worker để xử lý queue.

**“Đã enqueue” không bảo đảm task sẽ chạy ngay**, hoặc sẽ hoàn thành trước timeout của caller. Thời gian chờ queue phải được xem là một phần của độ trễ end-to-end.

### Bước 3 — Queue không nhận thì mới thử mở rộng đến max

Khi queue không thể nhận thêm (ví dụ queue bounded đã đầy hoặc `SynchronousQueue` không tìm được worker nhận bàn giao), executor thử tạo **non-core worker**, miễn tổng worker count còn dưới `maxPoolSize`.

Worker mới nhận luôn tác vụ vừa gửi. Các task cũ trong queue **không nhất thiết được xử lý trước task mới này**, bởi worker mở rộng có thể bắt đầu chạy task mới ngay, song song với các worker đang chạy. Không dựa vào tổng thứ tự hoàn tất theo thứ tự submit.

Một khi task đã vào queue, việc tăng max không tự động bắt pool đang chạy phải tạo thêm worker chỉ để rút ngắn queue; nó vẫn phụ thuộc vào đường đi tiếp nhận task, các cấu hình và hoạt động thực tế.

### Bước 4 — Không thể tạo worker/nhận queue thì reject

Nếu cả queue lẫn khả năng tăng worker đều không nhận task, executor gọi `RejectedExecutionHandler`. Ngoài ra, **task gửi sau khi executor đã shutdown cũng bị từ chối** dù số worker hoặc queue còn thấp hơn ngưỡng.

Với `AbortPolicy`, lời gọi `execute(task)` ném `RejectedExecutionException` ở Java. Trong `ThreadPoolTaskExecutor`, Spring thường chuyển tình huống từ chối thành `TaskRejectedException` theo hợp đồng `TaskExecutor`. Các policy khác có hành vi khác: chạy trên caller hoặc bỏ task, nên không thể suy ra “bị từ chối = chắc chắn có exception” trong mọi cấu hình.

## 3. Một ví dụ đếm từng task

Cho pool có:

~~~text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 2
~~~

Giả sử các task đủ lâu để **không task nào kết thúc trong lúc lần lượt gửi 7 task**. Không có worker được prestart.

| Task đến | Quyết định | Pool size sau khi nhận | Queue đang chờ |
| --- | --- | ---: | ---: |
| 1 | Tạo core worker #1 | 1 | 0 |
| 2 | Tạo core worker #2 | 2 | 0 |
| 3 | Đưa vào queue | 2 | 1 |
| 4 | Đưa vào queue | 2 | 2 |
| 5 | Queue đầy → tạo worker #3 | 3 | 2 |
| 6 | Queue đầy → tạo worker #4 | 4 | 2 |
| 7 | Queue đầy + đã đạt max → reject (nếu AbortPolicy) | 4 | 2 |

Ở thời điểm đó executor giữ 4 tác vụ đang chạy và 2 tác vụ chờ: **6 task được nhận, task thứ 7 bị từ chối**.

Đây là **kịch bản giả định tải giữ nguyên**, không phải thứ tự đếm bất biến trong mọi chương trình đa luồng. Nếu một worker hoàn thành và lấy task khỏi queue trước khi task tiếp theo được gửi, executor có thể tiếp tục enqueue hoặc bàn giao công việc mà không tăng pool/reject. Với submission đồng thời, pool size/queue size chỉ là snapshot.

### Hiểu đúng “năng lực nhận tối đa”

Với một pool đã bận hoàn toàn, queue có giới hạn dương `Q` và pool max `M`, số công việc có thể tồn tại đồng thời trong pool khoảng **M đang chạy + Q đang chờ**, *khi xét các task bị giữ đủ lâu và không có chuyển động khác*. Đây là giới hạn sức chứa tức thời, **không phải throughput mỗi giây**.

Năng lực hoàn tất còn phụ thuộc thời gian thực thi, CPU, I/O, tài nguyên kết nối và lock. Không thể suy ra “pool max 20 nên xử lý được 20.000 request/giây”.

## 4. Ví dụ Java 17 chạy độc lập, xác nhận đủ bốn bước

Ví dụ dùng `ThreadPoolExecutor` của JDK, có cùng quy tắc tiếp nhận tác vụ mà Spring `ThreadPoolTaskExecutor` bọc lại. Dùng `CountDownLatch` để giữ worker thứ nhất và thứ ba đang bận; nhờ đó các kết quả đếm không phụ thuộc tốc độ máy.

Tạo tệp **`PoolAdmissionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolAdmissionDemo {
    private static Runnable hold(CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            pool.execute(hold(firstStarted, release));
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task 1 did not start");
            }
            System.out.printf("task 1: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            pool.execute(() -> { });
            System.out.printf("task 2: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            pool.execute(hold(thirdStarted, release));
            if (!thirdStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task 3 did not start");
            }
            System.out.printf("task 3: workers=%d, queue=%d%n",
                    pool.getPoolSize(), pool.getQueue().size());

            try {
                pool.execute(() -> { });
                System.out.println("task 4: accepted");
            } catch (RejectedExecutionException expected) {
                System.out.println("task 4: rejected");
            }
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 PoolAdmissionDemo.java
java PoolAdmissionDemo
~~~

**Stdout chính xác** của ví dụ (đã kiểm tra với JDK 21 biên dịch ở mức `--release 17`):

~~~text
task 1: workers=1, queue=0
task 2: workers=1, queue=1
task 3: workers=2, queue=1
task 4: rejected
~~~

Giải thích:

1. **Task 1:** pool đang có 0 worker, nhỏ hơn core=1, nên tạo worker đầu tiên. Latch `firstStarted` xác nhận task đã bắt đầu, sau đó nó chờ `release`.
2. **Task 2:** pool đã đạt core và worker đang chờ latch, nên task thứ hai vào queue có capacity=1; nó chưa chạy.
3. **Task 3:** queue đã đầy, pool còn dưới max=2, nên tạo worker thứ hai cho task mới. `thirdStarted` xác nhận worker thứ hai cũng đã bắt đầu và đang chờ.
4. **Task 4:** queue vẫn đầy và cả hai workers đã tồn tại, nên `AbortPolicy` ném exception; chương trình in `rejected`.
5. Khối `finally` mở latch để các task đã nhận có thể thoát rồi đóng pool. Không để các worker bị chặn vô hạn trong ứng dụng thật.

Điểm quan trọng là **task 2 xếp queue trước task 3 nhưng task 3 lại được worker #2 chạy ngay**. Do đó thứ tự *được tiếp nhận* không đồng nghĩa với thứ tự *bắt đầu*, *hoàn thành* hay *được commit xuống database*.

## 5. Hành vi thay đổi theo kiểu queue

### 5.1. Queue có giới hạn dương (bounded queue)

Ví dụ:

~~~java
new ThreadPoolExecutor(
    2, 4, 60, TimeUnit.SECONDS,
    new java.util.concurrent.ArrayBlockingQueue<>(10)
);
~~~

Đây là **biểu thức Java minh họa khởi tạo**, chưa phải một chương trình độc lập; cần import `ThreadPoolExecutor` và `TimeUnit` nếu đặt trong tệp khác.

Với task chạy đủ lâu, hai workers đầu tiên được tạo tới core=2, mười task tiếp theo có thể được xếp vào queue, sau đó pool mới mở tới max=4; khi bão hòa sẽ từ chối theo handler. Queue hữu hạn giúp tạo giới hạn chờ và tạo tín hiệu quá tải sớm hơn, nhưng không tự quyết định số giới hạn phù hợp: queue quá lớn vẫn có thể làm timeout tích tụ.

### 5.2. Queue rất lớn hoặc “không giới hạn thực tế”

Ví dụ Spring:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(100);
executor.setQueueCapacity(Integer.MAX_VALUE);
~~~

Đây là các **lệnh cấu hình bên trong bean `ThreadPoolTaskExecutor` đã tạo**, không phải chương trình độc lập.

Khi đã có 2 workers, queue cực lớn sẽ tiếp tục nhận task, thường **không đầy trong tải thực tế**, do đó pool hầu như không có lý do tăng từ 2 lên 100. “Max bằng 100” không có nghĩa có 100 workers; nó chỉ là trần *khi điều kiện tăng workers xảy ra*. Không gọi `Integer.MAX_VALUE` là bộ nhớ vô hạn: mỗi task vẫn chiếm heap và có thể dẫn đến cạn bộ nhớ/độ trễ trước khi queue đạt mức số học đó.

Cấu hình mặc định trực tiếp của `ThreadPoolTaskExecutor` trong Spring Framework 6.x là core=1, max=`Integer.MAX_VALUE`, queueCapacity=`Integer.MAX_VALUE`. Điều này thường hoạt động gần như một worker xử lý, các task bổ sung đi vào queue. **Không nhầm mặc định của class này với các mặc định/auto-configuration theo phiên bản của Spring Boot.**

### 5.3. `queueCapacity=0`: bàn giao trực tiếp, không giữ task chờ

Trong Spring:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(0);
~~~

`ThreadPoolTaskExecutor` chọn `SynchronousQueue`. Đây không phải queue cho phép tích trữ 0 hoặc nhiều task theo cách `LinkedBlockingQueue`; nó là **điểm bàn giao trực tiếp**: thao tác `offer` thành công khi có một worker sẵn sàng nhận ngay.

Nếu các workers đang bận và không có worker nhận bàn giao, executor thử tăng pool từ core lên max. Nếu đã tới max mà vẫn không thể bàn giao, task bị từ chối. Cấu hình này giúp không tích backlog trong executor queue nhưng có thể làm số worker tăng nhanh khi workload tăng đột ngột; **phải giới hạn max và cân nhắc downstream**.

### 5.4. Fixed-size pool và core=0

- Nếu `corePoolSize == maxPoolSize`, pool không có vùng mở rộng bổ sung sau core; khi tất cả workers bận, task phải đợi trong queue hoặc bị từ chối.
- Nếu `corePoolSize=0` và `maxPoolSize>0`, pool không có core workers. Cơ chế queue và việc bảo đảm có worker khi queue chứa task có thể khiến đường đi khác với ví dụ core dương; không suy diễn “không có worker nào sẽ chạy”.
- `allowCoreThreadTimeOut(true)` có thể làm core workers cũng được thu hồi sau thời gian nhàn rỗi. `prestartAllCoreThreads(true)` làm pool tạo trước core workers; hai cấu hình này ảnh hưởng trạng thái worker theo thời gian nhưng không đảo nguyên tắc ưu tiên core/queue/max lúc tiếp nhận.

| Chiến lược | Ưu điểm | Rủi ro cần cân nhắc |
| --- | --- | --- |
| Bounded queue | Hữu hạn backlog, tạo cơ hội mở rộng pool sau khi queue đầy, giúp thể hiện quá tải | Queue quá lớn gây đợi lâu; quá nhỏ gây reject sớm |
| Gần như unbounded queue | Hấp thụ burst mà không reject sớm | Dễ tích tụ task, tăng latency/bộ nhớ; max ít được dùng |
| SynchronousQueue | Bàn giao ngay, không giữ backlog ở executor queue | Worker tăng nhanh; reject khi không thể nhận; phụ thuộc nặng vào downstream |
| Fixed-size pool | Giới hạn concurrency dễ hiểu | Khi tasks chặn lâu, queue và thời gian chờ có thể tăng |

## 6. Spring Framework: cấu hình ThreadPoolTaskExecutor đúng ý đồ

`ThreadPoolTaskExecutor` là bean Spring quản lý `ThreadPoolExecutor`. Khi ứng dụng dùng `@Async`, có thể định tuyến tác vụ đến bean đã cấu hình rõ ràng, tránh dựa vào executor mặc định.

Ví dụ **mã tích hợp trong Spring Framework 6.x / Spring Boot 3.x với Java 17+**, cần dependencies Spring và component scanning; không phải tệp chạy trực tiếp bằng `javac` đơn lẻ.

Tệp `ConcurrencyConfig.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ConcurrencyConfig {
    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("bounded-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Tệp `ReportService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("boundedExecutor")
    public CompletableFuture<String> export(String reportId) {
        // Minh họa; I/O thật cần timeout và xử lý lỗi phù hợp.
        return CompletableFuture.completedFuture("exported:" + reportId);
    }
}
~~~

Khi một bean khác gọi `reportService.export("R1")` **qua Spring proxy**, Spring gửi công việc đến `boundedExecutor`. Nếu các worker và queue chưa đạt giới hạn, task được nhận theo thứ tự core → queue → tăng tới max. Nếu đã bão hòa, lời submit có thể gây `TaskRejectedException` theo API Spring, kể cả khi method đã khai báo trả về `CompletableFuture`. Cần xử lý cả **lỗi submit ngay tại caller** lẫn **lỗi phát sinh trong lúc công việc chạy**.

Lưu ý:

- `@EnableAsync` là điều kiện bật xử lý annotation; gọi `this.export(...)` từ chính đối tượng trong chế độ proxy mặc định sẽ không kích hoạt `@Async` theo cách mong đợi.
- `@Async` không xóa giới hạn pool, queue, connection pool hay CPU. Nó chỉ chuyển công việc sang cơ chế thực thi đã chọn.
- Những con số 2/4/10 chỉ để minh họa thứ tự; chọn giá trị theo đo đạc workload, không đưa nguyên vào sản phẩm nếu chưa xác nhận năng lực hệ thống.
- Trong lifecycle của Spring, bean executor được Spring quản lý để khởi tạo và đóng. Nếu tự tạo Java executor trong nghiệp vụ, phải quản lý shutdown và task còn chờ.
- Khi một tác vụ trong executor lại gửi tác vụ con **cùng executor** rồi chờ bằng `Future.get()`/`join()`, có thể tạo **thread-pool starvation**: workers đều chờ trong khi tasks con bị kẹt ở queue. Tăng max chỉ có thể che triệu chứng trong một tình huống, không sửa phụ thuộc vòng.

### 6.1. “Tôi đã tăng max lên 50 mà active chỉ có 2”

Kiểm tra trước `queueCapacity`, queue depth, `corePoolSize`, `getPoolSize()` và `getActiveCount()`. Nếu queue vẫn nhận task, theo thuật toán pool **ưu tiên enqueue**, nên max có thể chưa phát huy tác dụng. Phải nhìn cả tốc độ đến, thời gian chạy, queue wait và năng lực downstream.

Cũng cần phân biệt:

- `getPoolSize()`: số worker hiện đang tồn tại.
- `getActiveCount()`: ước lượng số worker đang thực thi task.
- `getQueueSize()`: số task đang chờ trong queue (trên các phiên bản Spring hỗ trợ).
- `getCorePoolSize()` và `getMaxPoolSize()`: giới hạn cấu hình, **không phải số worker đang có**.

Đừng dựa vào một snapshot để kết luận pool “lỗi”; cần quan sát biến thiên theo thời gian, throughput, p95/p99 và rejection.

## 7. Chính sách từ chối: bước cuối có nhiều cách xử lý

Trong Java `ThreadPoolExecutor` có bốn policy phổ biến. Spring cho phép cấu hình `RejectedExecutionHandler` tương ứng:

| Policy | Khi quá tải | Ý nghĩa vận hành |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` (trong Spring có thể được biểu diễn là `TaskRejectedException`) | Dễ quan sát quá tải và trả phản hồi cho caller |
| `CallerRunsPolicy` | Nếu pool chưa shutdown, **thread gọi `execute` tự chạy task** | Tạo backpressure tự nhiên, nhưng caller bị chặn và độ trễ caller tăng |
| `DiscardPolicy` | Bỏ task mà không báo lỗi qua chính policy | Rất nguy hiểm khi nghiệp vụ cần đảm bảo xử lý; task có thể mất im lặng |
| `DiscardOldestPolicy` | Bỏ task đầu queue rồi thử nhận task mới nếu pool chưa shutdown | Có thể làm mất tác vụ chờ lâu nhất, phá kỳ vọng FIFO và làm các Future chờ không hoàn tất |

**Không mặc nhiên coi CallerRunsPolicy là “async an toàn”.** Nếu caller là HTTP request thread, nó có thể bị buộc chạy cả tác vụ nền. Nếu caller là Reactor event-loop, có thể chặn event loop và ảnh hưởng nhiều request. Với task có side effect hoặc đòi hỏi bảo đảm delivery, cần xác định rõ lúc nào được drop, retry, từ chối hay lưu vào queue bền vững.

Nếu yêu cầu tính đúng đắn quan trọng, `AbortPolicy` cộng với xử lý lỗi submit có thể dễ giám sát hơn chính sách bỏ việc. Đổi policy **không làm tăng năng lực thực sự** của CPU, database hay dịch vụ ngoài.

### Phản hồi khi executor không nhận thêm task

Tùy kiến trúc ứng dụng, có thể:

1. Trả lỗi/response quá tải phù hợp ở biên request thay vì treo chờ vô hạn.
2. Giới hạn số task đang xử lý (*bulkhead* / semaphore) trước khi submit.
3. Dùng timeout và cancellation có kiểm soát; `Future.get(timeout)` chỉ dừng thời gian caller chờ, không tự bảo đảm task nền đã dừng.
4. Nếu nghiệp vụ bắt buộc xử lý sau, ghi công việc vào **hàng đợi bền vững** có ACK/retry/idempotency thay vì chỉ tăng queue in-memory của executor.
5. Cân nhắc retry có backoff và jitter ở nơi được phép, tránh gửi ồ ạt khi downstream vừa suy yếu.

## 8. Vì sao thứ tự này quan trọng đối với độ trễ và tài nguyên?

### 8.1. Queue lớn chưa chắc là điều tốt

Queue giảm nguy cơ rejection khi có burst ngắn, nhưng khi tốc độ gửi task lớn hơn tốc độ hoàn thành trong thời gian dài, backlog tăng và **độ trễ queue** tăng. Tác vụ “được nhận” chưa chắc còn giá trị khi nó bắt đầu chạy: request từ lâu đã timeout, người dùng đã hủy thao tác hoặc dữ liệu nghiệp vụ đã đổi.

Không điều chỉnh queue chỉ để làm rejection về 0. Một hệ thống báo “đã nhận” nhưng giữ task hàng phút có thể tệ hơn hệ thống từ chối sớm và rõ ràng.

### 8.2. Max threads không phải throughput

Giả sử mỗi task dùng một database connection trong 200 ms và pool DB chỉ có 10 connection. Trong điều kiện lý tưởng, giới hạn bước DB có thể xấp xỉ 10 / 0,2 = **50 lần/giây** nếu các điều kiện khác không phải nút thắt. Nâng `maxPoolSize` từ 16 lên 160 không tạo thêm connection; nhiều worker mới có thể chỉ chờ DB. Phép tính là **minh họa giới hạn lý tưởng**, không phải đo throughput ứng dụng thật.

CPU-bound thường giới hạn ở số lõi CPU hữu dụng; I/O-bound có thể hưởng lợi từ concurrency cao hơn, nhưng phải kiểm tra timeout, connection limits, memory và downstream. Tăng thread quá mức cũng làm tăng chi phí lập lịch, stack/native memory, tranh chấp lock và context switching.

### 8.3. Thứ tự tiếp nhận không bảo đảm FIFO hoàn tất

Ngay cả khi queue là FIFO, task mới có thể được worker non-core xử lý ngay khi queue đầy, trong khi task cũ vẫn chờ. Nhiều workers xử lý song song có thời gian chạy khác nhau. Vì vậy:

- Không dựa vào thứ tự submit để bảo đảm thứ tự cập nhật trạng thái.
- Nếu nghiệp vụ cần ordering theo khóa (ví dụ cùng một customerId), thiết kế xử lý tuần tự theo key, partition hoặc trạng thái có kiểm soát.
- Nếu cần chính xác một lần xử lý theo nghiệp vụ, executor in-memory tự nó không cung cấp durability hoặc exactly-once.

## 9. Checklist chẩn đoán khi pool bão hòa

Khi gặp timeout, queue tăng hoặc bị reject, thu thập **đồng thời**:

| Câu hỏi | Bằng chứng |
| --- | --- |
| Bao nhiêu worker tồn tại/đang bận? | `poolSize`, `activeCount`, thread dump |
| Task đang nằm ở đâu? | Số task chờ, tuổi task trong queue, thời gian xử lý |
| Vì sao pool không tăng? | Core/max/queueCapacity, queue có đầy không, policy có giới hạn gì |
| Vì sao worker bận quá lâu? | Stack: CPU, chờ lock, HTTP, DB, `Future.get()` |
| Vì sao task bị từ chối? | Executor saturation, shutdown, rejection count, log/trace |
| Tăng luồng có giúp không? | Đo throughput, p95/p99, CPU, DB connections và backend latency trước/sau |

Thực hiện phân tích theo nguyên nhân:

1. Xác nhận chính xác bean executor mà request/`@Async` đang dùng; tránh đo nhầm pool.
2. Kiểm tra giá trị `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection policy **đang có hiệu lực**.
3. Xem worker stack và thời gian task chờ queue. Nếu workers đều chặn I/O/DB, tìm giới hạn downstream trước.
4. Phân biệt pool đã shutdown với pool đang saturation; cả hai có thể làm task bị reject nhưng cách khắc phục khác nhau.
5. Đặt concurrency budget, queue bound, timeout và phương án quá tải; kiểm chứng bằng thử tải tăng dần và tải kéo dài.
6. Sau mỗi thay đổi, so sánh completion rate, p95/p99, timeout, rejection, số connection và tài nguyên.

Một số lỗi thường gặp:

- **Hiểu sai:** “Đặt max=100 là mọi lúc sẽ có tối đa 100 task được chạy ngay.” **Đúng:** sau core, queue thường được ưu tiên; max chỉ là trần khi pool phải mở rộng.
- **Hiểu sai:** “Queue capacity=0 nghĩa là executor luôn từ chối.” **Đúng:** `SynchronousQueue` có thể bàn giao cho worker đang chờ hoặc làm pool mở rộng đến max.
- **Hiểu sai:** “Tác vụ bị reject chắc chắn đã chạy một phần.” **Đúng:** `AbortPolicy` từ chối task trước khi nó được thực thi theo lời submit đó.
- **Hiểu sai:** “Không có rejection nghĩa là hệ thống khỏe.” **Đúng:** queue lớn có thể che giấu backlog và đẩy lỗi thành timeout/memory pressure.
- **Hiểu sai:** “Shutdown chỉ là giải phóng worker.” **Đúng:** shutdown thay đổi việc chấp nhận task mới; những lời submit mới có thể bị từ chối kể cả còn capacity.

## 10. Bài tập suy luận và đáp án

**Câu 1.** Cấu hình core=3, max=8, queueCapacity=100. Có 3 worker đang bận; tác vụ thứ tư thường được tiếp nhận ở đâu?

**Đáp án:** vào queue, vì đã đạt core và queue vẫn còn chỗ. Không tự tăng ngay lên 4 workers.

**Câu 2.** Cấu hình core=2, max=4, queueCapacity=2. Bốn task đang chạy hoặc chờ như bảng ở mục 3; task thứ năm được tiếp nhận thế nào?

**Đáp án:** sau task 1–2 tạo core và task 3–4 vào queue, task 5 làm queue offer thất bại nên pool thử tạo worker #3 (chưa đạt max).

**Câu 3.** Nếu task thứ bảy bị từ chối với cấu hình ở câu 2, có thể kết luận luôn rằng pool đã shutdown?

**Đáp án:** không. Với 4 workers bận và 2 task queue, pool đang bão hòa cũng dẫn tới rejection. Cần kiểm tra trạng thái và metrics.

**Câu 4.** Vì sao queueCapacity=`Integer.MAX_VALUE` làm maxPoolSize thường không phát huy tác dụng?

**Đáp án:** sau core, queue gần như luôn nhận được task, nên nhánh “queue không thể nhận → tạo non-core worker” hiếm khi xảy ra.

**Câu 5.** `CallerRunsPolicy` giúp giảm số task bị bỏ như thế nào và đổi lại điều gì?

**Đáp án:** caller tự thực thi task nếu pool còn chạy, khiến tốc độ submit giảm. Đổi lại caller bị block và có thể làm tăng latency hoặc chặn request/event-loop thread.

**Câu 6.** Nếu tăng `maxPoolSize` mà throughput không đổi, cần kiểm tra điều gì?

**Đáp án:** có thể queue chưa đầy nên max chưa sử dụng; hoặc nút thắt là DB/HTTP connections, CPU, lock hay backend. So sánh queue wait, active/pool size và latency downstream.

**Câu 7.** Task thứ ba được worker mới chạy trước task thứ hai đang xếp queue có vi phạm FIFO không?

**Đáp án:** không. Queue nội bộ có thể FIFO cho những task đã **nằm trong queue**, nhưng task thứ ba được giao trực tiếp cho non-core worker nên không phải chờ sau task thứ hai.

## 11. Tài liệu tham khảo

- Oracle Java SE 17 — `ThreadPoolExecutor` (core size, queueing, rejection): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `BlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Oracle Java SE 17 — `SynchronousQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- Spring Framework 6.x — `ThreadPoolTaskExecutor` API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
