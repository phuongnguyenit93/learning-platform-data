# queueCapacity bằng 0 và chuyển giao trực tiếp trong ThreadPoolTaskExecutor

Trong Spring Framework, **ThreadPoolTaskExecutor** là một bộ thực thi có nhóm luồng (thread pool) để chạy các tác vụ ngoài luồng gọi. Khi cấu hình **`queueCapacity = 0`**, executor **không tạo hàng đợi có khả năng lưu tác vụ đang chờ**. Thay vào đó, nó dùng cơ chế **chuyển giao trực tiếp (direct handoff)** thông qua `SynchronousQueue` của Java: tác vụ được chuyển ngay tới một worker đang sẵn sàng, hoặc executor cố gắng tạo thêm worker trong giới hạn `maxPoolSize`. Nếu không thể làm cả hai, tác vụ bị **từ chối** theo chính sách rejection.

Đây là một lựa chọn quan trọng trong nhóm **Nhóm luồng** của **Spring Framework - concurrency**, bởi một thay đổi nhỏ ở `queueCapacity` có thể làm thay đổi hoàn toàn đường đi của tác vụ, cách pool mở rộng và hành vi khi quá tải.

Các ý cần nắm:

- **`queueCapacity = 0` không có nghĩa là executor không thể nhận task.** Nó có nghĩa là không có chỗ *tích trữ* task trong hàng đợi.
- **Direct handoff không đồng nghĩa với mỗi task một thread mới.** `ThreadPoolTaskExecutor` vẫn **tái sử dụng worker** khi worker đã rảnh và sẵn sàng nhận task.
- **`corePoolSize`, `maxPoolSize` và rejection policy quyết định khi nào tăng số worker, khi nào từ chối.**
- Hàng đợi bằng 0 có thể giúp phát hiện quá tải sớm, nhưng nếu để `maxPoolSize` quá lớn thì vẫn có thể sinh rất nhiều platform threads.

## 1. ThreadPoolTaskExecutor dùng hàng đợi để làm gì?

`ThreadPoolTaskExecutor` của Spring bọc một `java.util.concurrent.ThreadPoolExecutor`. Một pool thường có ba thành phần:

1. **Worker threads:** các luồng có thể xử lý hết task này rồi đến task khác.
2. **Task queue:** nơi giữ các task đã được chấp nhận nhưng chưa có worker thực thi.
3. **Saturation/rejection policy:** quyết định làm gì khi không thể nhận thêm việc.

Các cấu hình liên quan:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `corePoolSize` | Ngưỡng số worker cốt lõi mà pool ưu tiên tạo để xử lý task khi cần. |
| `maxPoolSize` | Giới hạn trên số worker pool có thể tạo. |
| `queueCapacity` | Khả năng lưu các tác vụ chờ; **0** chọn cơ chế không lưu task vào queue. |
| `keepAliveSeconds` | Khoảng thời gian worker vượt core được phép nhàn rỗi trước khi bị thu hồi (theo cấu hình thông thường). |
| `RejectedExecutionHandler` | Cách xử lý khi pool không tiếp nhận task. |
| `threadNamePrefix` | Tiền tố tên worker, giúp quan sát khi log/debug. |

Với `queueCapacity > 0`, Spring tạo hàng đợi kiểu **`LinkedBlockingQueue`** có dung lượng tương ứng. Với `queueCapacity <= 0`, Spring tạo **`SynchronousQueue`**. Trong bài này ta xét trường hợp được yêu cầu: **`queueCapacity = 0`**.

Cần hiểu đúng một điểm: **giới hạn `maxPoolSize` không phải chỉ số worker luôn có sẵn**. Pool có thể chưa tạo đủ số worker tối đa. Việc mở rộng phụ thuộc core, hàng đợi, số worker hiện tại và thời điểm gửi tác vụ.

## 2. SynchronousQueue: hàng đợi không lưu phần tử

Tên `SynchronousQueue` dễ làm người học nghĩ rằng đó là một queue bình thường với kích thước bằng 0. Thực tế, nó là **điểm trao đổi trực tiếp** giữa một bên đưa phần tử vào và một bên nhận phần tử ra.

~~~text
Hàng đợi có chỗ chứa (ví dụ LinkedBlockingQueue)
Producer -> [ task A | task B | task C ] -> Worker
                    task có thể nằm chờ

Chuyển giao trực tiếp (SynchronousQueue)
Producer -- task A ----------------------> Worker đang chờ nhận
              không có ngăn chứa ở giữa
~~~

Đặc tính của `SynchronousQueue`:

- **Không có dung lượng lưu trữ nội bộ**; một task không thể nằm trong queue để chờ worker xuất hiện sau đó.
- Một thao tác `offer(task)` không chờ sẽ thành công chỉ khi có bên nhận phù hợp đang chờ để nhận task.
- Phương thức `size()` luôn là **0**; điều đó không nói rằng executor không có task đang chạy.
- `put(task)` của chính `SynchronousQueue` có thể chờ bên nhận, nhưng **đừng suy ra rằng `ThreadPoolTaskExecutor.execute()` sẽ dùng `put()` để chặn caller đến khi worker rảnh**. Với `ThreadPoolExecutor`, đường nhận task dùng `offer()` rồi xét tạo worker hoặc từ chối.

Vì vậy, `queueCapacity=0` làm mất **khả năng đệm task**, chứ không làm mất **khả năng xử lý task**. Một worker vừa hoàn tất việc có thể quay lại chờ nhận việc tiếp theo; lúc đó tác vụ mới được handoff trực tiếp và **worker cũ được tái sử dụng**.

## 3. Thuật toán nhận tác vụ: core → handoff → max → reject

Có thể hình dung đường đi của `ThreadPoolExecutor.execute(task)` như sau (lược bỏ các chi tiết khóa nội bộ và kiểm tra trạng thái shutdown):

~~~text
                          execute(task)
                                |
               Số worker hiện tại < corePoolSize?
                       /                  \
                     Có                  Không
                      |                     |
             Tạo worker mới          Thử offer(task)
             chạy task ngay          vào hàng đợi
                                           |
                           +---------------+--------------+
                           |                              |
                       Thành công                      Thất bại
                           |                              |
                 Worker sẽ nhận task       Số worker < maxPoolSize?
                                            /                \
                                          Có                Không
                                           |                   |
                                  Tạo worker mới            REJECT
                                  chạy task ngay
~~~

Với **`queueCapacity=0`**, bước `offer()` là một lần thử **chuyển giao trực tiếp** cho worker chờ nhận, không phải ghi vào buffer. Nếu không có worker nào có thể nhận ngay, pool thử **tạo thêm worker**. Khi đã chạm `maxPoolSize` mà không handoff được, tác vụ bị từ chối.

Đường đi còn phụ thuộc trạng thái pool: executor đã shutdown thì không nên nhận task mới; sau khi `offer()` thành công, ThreadPoolExecutor cũng kiểm tra lại tình trạng pool để tránh giữ task khi đã ngừng nhận việc. Đây là lý do sơ đồ chỉ mô tả quy tắc chủ đạo.

**Ví dụ cấu hình:** `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=0`. Giả sử mọi task giữ worker bận cho tới khi test chủ động giải phóng:

| Lần gửi | Trạng thái trước khi gửi | Kết quả |
| --- | --- | --- |
| Task 1 | Chưa có worker | Tạo worker #1 (core). |
| Task 2 | Có 1 worker đang bận | Tạo worker #2 (core). |
| Task 3 | Hai core worker đều bận; không handoff được | Tạo worker #3. |
| Task 4 | Ba worker đều bận; không handoff được | Tạo worker #4. |
| Task 5 | Cả 4 worker đều bận; không có buffer | **Reject** theo chính sách mặc định. |

Nếu worker #2 đã xong task và **đang chờ nhận việc** lúc Task 5 được gửi, tác vụ đó có thể được handoff trực tiếp cho worker #2; **không nhất thiết tạo thread thứ năm** và không nhất thiết reject. Kết luận luôn phụ thuộc **trạng thái lúc submit**.

## 4. Ví dụ Java 17 chạy độc lập: pool 2–4 worker và queue bằng 0

Ta có thể kiểm chứng chính xác cơ chế nền của Spring bằng API chuẩn Java. Vì `ThreadPoolTaskExecutor` bọc `ThreadPoolExecutor`, ví dụ này phản ánh đường nhận task cốt lõi khi Spring chọn `SynchronousQueue`.

Lưu thành tệp **`DirectHandoffDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DirectHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2,
                4,
                30,
                TimeUnit.SECONDS,
                new SynchronousQueue<Runnable>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch started = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();

        Runnable heldTask = () -> {
            active.incrementAndGet();
            started.countDown();

            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            for (int i = 0; i < 4; i++) {
                pool.execute(heldTask);
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Không đủ worker khởi động trong thời hạn test");
            }

            System.out.println("Tác vụ đang chạy: " + active.get());

            boolean rejected = false;
            try {
                pool.execute(() -> {
                    // Tác vụ thứ năm sẽ không được chấp nhận khi cả bốn bận.
                });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Tác vụ thứ năm bị từ chối: " + rejected);
            System.out.println("Số phần tử đang đợi trong queue: "
                    + pool.getQueue().size());
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

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 DirectHandoffDemo.java
java DirectHandoffDemo
~~~

**Stdout** khi các worker khởi động thành công trong thời hạn test:

~~~text
Tác vụ đang chạy: 4
Tác vụ thứ năm bị từ chối: true
Số phần tử đang đợi trong queue: 0
~~~

Giải thích từng điểm:

1. **`CountDownLatch started`** buộc main chỉ kiểm tra sau khi cả bốn worker thực sự đã bắt đầu.
2. **`release`** giữ cả bốn worker bận. Vì vậy, không có worker đang chờ trong `SynchronousQueue` để nhận tác vụ thứ năm.
3. Pool đã đạt `maxPoolSize=4`, nên không thể tạo worker thứ năm; `AbortPolicy` ném `RejectedExecutionException`.
4. **`getQueue().size() == 0`** đúng bản chất của `SynchronousQueue`: không có phần tử lưu chờ. Nó **không phủ nhận** rằng bốn task đang thực thi.
5. `finally` luôn mở latch giải phóng worker và đóng pool. Dùng latch thay cho `Thread.sleep()` để tránh phụ thuộc lịch scheduler.

**Giới hạn của ví dụ:** đây là `java.util.concurrent.ThreadPoolExecutor` **thuần Java** để có thể chạy chỉ bằng `javac`/`java`. Trong ứng dụng Spring, `ThreadPoolTaskExecutor` sử dụng cùng cơ chế nền nhưng bao bọc API và ngoại lệ bằng lớp Spring. Phần tiếp theo cho thấy cấu hình Spring tương ứng.

## 5. Cấu hình ThreadPoolTaskExecutor trong Spring

Đây là một cấu hình mẫu cho ứng dụng có dependency **Spring Context**. Nó **không phải chương trình Java độc lập** chạy trực tiếp bằng `javac` khi không có Spring trong classpath.

**`DirectHandoffConfig.java`**:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class DirectHandoffConfig {
    @Bean("directHandoffExecutor")
    public ThreadPoolTaskExecutor directHandoffExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(0);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("direct-handoff-");

        return executor;
    }
}
~~~

Sau khi bean được khởi tạo, cấu hình cho phép pool bắt đầu từ **tối đa hai core workers**, mở rộng đến **bốn workers**, và không giữ task pending trong một queue có dung lượng dương. Những con số **2, 4, 30** chỉ để học; production phải đo tài nguyên và chọn giới hạn có chủ đích.

Có thể kiểm chứng cấu trúc queue bằng **đoạn mã Spring** sau (giả sử biến `executor` đã trỏ đến bean ở trên):

~~~java
import java.util.concurrent.SynchronousQueue;

boolean directHandoff =
        executor.getThreadPoolExecutor().getQueue()
                instanceof SynchronousQueue;

System.out.println(directHandoff); // true
~~~

Chỉ gọi `getThreadPoolExecutor()` khi `ThreadPoolTaskExecutor` đã được initialize. Đoạn này cho biết **kiểu queue** được cấu hình; nó không kiểm chứng riêng số task đã chạy hoặc hiệu suất.

### Vì sao phải đặt cả maxPoolSize?

Mặc định của `ThreadPoolTaskExecutor` là **core pool nhỏ, queue mặc định có dung lượng rất lớn, max pool rộng**. Nếu chỉ đổi `queueCapacity=0` mà giữ `maxPoolSize` mặc định rất lớn, executor có thể tạo **nhiều platform threads** trong đợt tải tăng. Không có buffer để hấp thụ burst, nhưng pool vẫn cố tăng worker cho tới khi vướng giới hạn.

Một cấu hình production cần giới hạn **`maxPoolSize` hữu hạn**, đồng thời lựa chọn rõ:

- Cho phép mức concurrent task tối đa bao nhiêu?
- Khi đầy thì trả lỗi ngay hay chạy task ở caller?
- Có cần chấp nhận task vào queue không, và queue được phép dài bao nhiêu?
- Một task chậm sẽ giữ worker và tài nguyên ngoài bao lâu?

**Không gán `maxPoolSize` bằng một số lớn chỉ để “tránh reject”.** Làm vậy có thể dời sự cố sang cạn thread, bộ nhớ hoặc kết nối downstream.

## 6. So sánh queueCapacity = 0 với queueCapacity > 0

Để thấy khác biệt, giữ **`corePoolSize=2`**, **`maxPoolSize=4`** và giả sử mỗi task đang chạy bị giữ cho đến khi ta chủ động thả:

| Lần gửi | `queueCapacity=0` | `queueCapacity=3` |
| --- | --- | --- |
| #1–#2 | Tạo hai core workers | Tạo hai core workers |
| #3 | Tạo worker #3 | Đặt vào queue |
| #4 | Tạo worker #4 | Đặt vào queue |
| #5 | **Reject** vì 4 worker đều bận | Đặt vào queue |
| #6 | — | Queue đã đầy, tạo worker #3 |
| #7 | — | Tạo worker #4 |
| #8 | — | **Reject** nếu các worker vẫn bận |

Đây là một **kịch bản giả lập với task luôn bận**, không phải một thứ tự bảo đảm của hệ thống khi task chạy nhanh. Khi worker giải phóng hoặc lịch xen kẽ khác, kết quả có thể khác.

Với hàng đợi có chỗ chứa, `ThreadPoolExecutor` thường **ưu tiên xếp queue sau khi đạt core**, rồi mới mở rộng số worker vượt core khi queue không nhận thêm. Với handoff bằng 0, không thể đệm task, nên khi core workers bận và không có worker chờ, pool mở rộng **sớm hơn** đến max.

Vì vậy:

- `queueCapacity=0` thường **tăng worker sớm** và **từ chối sớm** khi tất cả worker đều bận.
- `queueCapacity>0` có thể **làm mượt burst** bằng cách giữ task chờ, đổi lại chấp nhận **độ trễ trong queue** và chi phí lưu trữ.
- `queueCapacity` rất lớn có thể khiến `maxPoolSize` **hầu như không có cơ hội phát huy tác dụng**, vì task cứ được nhận vào queue thay vì kích hoạt tạo thêm non-core workers.
- **Không có một giá trị queueCapacity tốt cho mọi workload**. Cần dựa trên throughput, thời gian xử lý, SLA và giới hạn hệ thống phụ thuộc.

## 7. Khi nào worker được tái sử dụng dù queue bằng 0?

Một nhầm lẫn phổ biến là “hàng đợi không có chỗ chứa” đồng nghĩa “mỗi task phải tạo worker mới”. Với **ThreadPoolTaskExecutor**, worker xử lý xong task sẽ quay lại vòng lặp lấy task tiếp theo. Khi worker đang **chờ nhận** qua `SynchronousQueue`, producer có thể chuyển task mới trực tiếp cho worker đó.

~~~text
Task A ---> worker-1 ----> hoàn tất A
                             |
                             +--- chờ ở SynchronousQueue
                                          ^
                                          |
Task B -----------------------------------+
                  handoff trực tiếp
                                          |
                                cùng worker-1 chạy B
~~~

Vì vậy, **`queueCapacity=0` vẫn có thể tái sử dụng luồng**. Đây là khác biệt bản chất với **`SimpleAsyncTaskExecutor`**, vốn tạo luồng mới cho từng tác vụ thay vì duy trì worker pool.

Nếu có nhiều task đến đúng lúc không worker nào đang chờ, pool có thể cần tạo thêm thread (nếu dưới max) hoặc reject. Thời điểm giao việc ảnh hưởng đến việc nhận task, nhưng **không có queue lưu task để chờ** nếu không handoff ngay được.

**Phân biệt ba khái niệm:**

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Direct handoff** | Không giữ task trong queue, gửi trực tiếp cho worker có thể nhận ngay. |
| **Thread reuse** | Worker đã làm task trước có thể làm task tiếp theo. |
| **Thread per task** | Mỗi task có một thread mới, không tái sử dụng. |

`ThreadPoolTaskExecutor(queueCapacity=0)` kết hợp **direct handoff + thread reuse**; `SimpleAsyncTaskExecutor` có mô hình **thread per task**. Không nên thay thế khái niệm này bằng khái niệm kia.

## 8. Quá tải: TaskRejectedException và chính sách xử lý

Khi queue không nhận được task và pool đã đạt giới hạn worker, **rejection** xảy ra. `ThreadPoolExecutor` mặc định dùng **AbortPolicy**: ném `RejectedExecutionException`. Trong API `ThreadPoolTaskExecutor` của Spring, lỗi từ chối được biểu diễn thành **`TaskRejectedException`** (một ngoại lệ Spring của việc gửi task không được chấp nhận).

Đây là lỗi ở **thời điểm gửi task**, khác với lỗi xảy ra *bên trong* worker sau khi task đã chạy.

~~~text
Caller
  |
  +-- execute(task)
         |
         +-- accepted -> worker thực thi -> có thể lỗi nghiệp vụ
         |
         +-- rejected -> caller nhận lỗi ngay khi submit
~~~

Ứng dụng phải xác định quy tắc khi quá tải. Một số lựa chọn:

| Rejection policy | Hành vi | Điều cần cân nhắc |
| --- | --- | --- |
| **AbortPolicy** | Ném ngoại lệ khi không nhận được task | Rõ ràng, dễ ghi log/đếm và phản hồi quá tải |
| **CallerRunsPolicy** | Caller tự thực thi task nếu executor chưa shutdown | Tạo backpressure gián tiếp nhưng có thể **chặn request thread** và làm mất tính async của lời gọi |
| **DiscardPolicy** | Bỏ task theo chính sách của executor | Dễ mất công việc âm thầm, thường không phù hợp việc nghiệp vụ quan trọng |
| **DiscardOldestPolicy** | Thử loại task đầu queue rồi gửi lại | Không phù hợp để suy diễn như queue có dữ liệu khi đang dùng SynchronousQueue; nên tránh nếu không có lý do đã kiểm chứng |

Có thể đặt chính sách cho bean:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

Đây là **đoạn cấu hình minh họa**, cần gọi trước `initialize()`. **CallerRunsPolicy không miễn phí**: nếu một HTTP request đang gửi tác vụ và pool đã đầy, chính request thread có thể phải chạy toàn bộ tác vụ, kéo dài response latency và khiến cơ chế `@Async` không còn chạy trên worker ở lần đó. Nếu executor đã shutdown, chính sách này không bảo đảm sẽ thực thi task.

Khi muốn trả lời nhanh dưới tải cao, thường cần **thừa nhận overload và từ chối có chủ đích**: bắt ngoại lệ ở ranh giới hợp lý, giới hạn retry và trả thông tin thích hợp cho caller. Khi muốn xử lý hết công việc, cần bộ đệm/queue có giới hạn, retry riêng hoặc **durable queue** bên ngoài cho tác vụ có yêu cầu bền vững; đừng xem `ThreadPoolTaskExecutor` là hàng đợi durable.

## 9. Tích hợp với @Async

Trong Spring, một phương thức được đánh dấu **`@Async`** có thể được interceptor chuyển tới một executor. Để dùng đúng bean có queue bằng 0, chỉ định **tên executor** tường minh.

**Cấu hình** (cần Spring Context, và thường có trong ứng dụng Spring Boot):

~~~java
package example.concurrency;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncSupport {
}
~~~

**Service**:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BillingService {
    @Async("directHandoffExecutor")
    public CompletableFuture<Integer> computeTotal(int price, int fee) {
        int total = price + fee;
        return CompletableFuture.completedFuture(total);
    }
}
~~~

Nếu **một bean khác** gọi `billingService.computeTotal(100, 20)` qua Spring proxy và tác vụ được nhận, caller nhận một future. Khi hoàn tất thành công, future có kết quả **120**. Nếu caller gọi `join()` trước khi có kết quả thì caller vẫn chặn.

**Phân biệt lỗi hai thời điểm:**

- **Ngay khi gửi:** pool đầy, không có handoff, không thể thêm worker → lời gọi qua executor có thể ném `TaskRejectedException` tại ranh giới submit; caller cần xử lý riêng.
- **Sau khi được nhận:** logic bên trong `computeTotal` lỗi → future có thể hoàn tất exceptionally; caller xử lý qua `exceptionally`, `handle` hoặc `join`/`get`.

Những điều kiện của `@Async` vẫn áp dụng:

- Bật `@EnableAsync` hoặc cấu hình tương đương.
- Trong chế độ proxy thông thường, **self-invocation** như `this.computeTotal(...)` từ cùng bean **không đi qua proxy**, nên annotation không tạo việc chuyển luồng như mong đợi.
- `@Async` không có nghĩa **không bao giờ chặn**: nếu sử dụng CallerRunsPolicy, caller có thể phải thực thi task; nếu gọi `join()` thì caller đợi kết quả.
- Những giá trị gắn với thread (MDC, SecurityContext, transaction/request attributes) **không tự động bảo đảm được mang qua mọi executor**. Truyền dữ liệu nghiệp vụ dưới dạng tham số/snapshot, dùng cơ chế propagation được quản lý khi cần.

**Lưu ý:** ví dụ service trả `CompletableFuture.completedFuture(total)` vì bản thân phương thức đã được thực thi trong cơ chế `@Async`. Không cần khởi tạo thêm `supplyAsync` ở bên trong chỉ để tạo một tầng bất đồng bộ nữa.

## 10. Tác vụ phù hợp và cách chọn giới hạn

`queueCapacity=0` có thể phù hợp khi ưu tiên **không tích tụ backlog trong bộ nhớ** và muốn xác định giới hạn đồng thời rõ:

### Tác vụ CPU-bound

Ví dụ: nén, mã hóa, tính toán thuần CPU. Nếu CPU chỉ có một số core hữu hạn, tăng số worker quá cao không làm throughput tăng vô hạn. Một pool với **`maxPoolSize` xấp xỉ năng lực CPU phù hợp** và queue/rejection được đo lường có thể giữ tải ổn định. Handoff bằng 0 từ chối nhanh khi pool đầy, nhưng có thể từ chối những burst ngắn mà queue nhỏ lẽ ra hấp thụ được.

### Tác vụ I/O-bound

Ví dụ: gọi REST downstream, đọc DB hoặc storage. Worker thường chờ I/O; mức concurrency hữu ích có thể lớn hơn số core, nhưng **DB connection pool, HTTP connection limits và rate limit của downstream** là ràng buộc chính. Nếu `maxPoolSize=100` trong khi DB chỉ có 10 connection, tăng worker không tự tăng năng lực DB; ngược lại có thể làm tích tụ thêm tác vụ đang chờ connection.

### Công việc bắt buộc phải được xử lý

Nếu một task tương đương nghiệp vụ quan trọng (giao dịch, gửi thông báo phải bảo đảm, xử lý đơn hàng) thì **hàng đợi trong RAM của executor cũng không phải lưu trữ bền vững**. `queueCapacity=0` càng không có buffer. Khi cần tiếp nhận/ack và xử lý sau kể cả restart, hãy cân nhắc cơ chế job/queue bền vững có idempotency và retry phù hợp.

### Gợi ý lựa chọn

| Ưu tiên | Hướng xem xét |
| --- | --- |
| Từ chối sớm khi worker bận, không giữ backlog nội bộ | `queueCapacity=0`, max hữu hạn và rejection rõ ràng |
| Hấp thụ burst ngắn trong giới hạn chấp nhận được | `queueCapacity` dương, hữu hạn; theo dõi queue wait |
| Nhiều task CPU-bound có chi phí nhỏ | Worker pool được tái sử dụng, số worker phù hợp CPU |
| Nhiều task chặn I/O | Giới hạn theo tài nguyên đích; có thể xem xét virtual threads trên JDK hỗ trợ |
| Không được mất job | Hệ thống job queue bền vững, không dựa đơn độc vào executor nội bộ |

Không nên coi một giá trị cấu hình cụ thể là mặc định tốt cho mọi dự án; phải thử với tải đại diện.

## 11. Quan sát và giám sát khi queueCapacity=0

Vì `SynchronousQueue.size()` luôn trả **0**, chỉ nhìn `queueSize=0` sẽ dẫn đến nhận định sai rằng hệ thống không bận.

Theo dõi đồng thời:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `getPoolSize()` | Số worker hiện có trong pool. |
| `getActiveCount()` | Số worker đang thực thi task (snapshot tại thời điểm lấy số). |
| `getCorePoolSize()` / `getMaxPoolSize()` | Giới hạn cấu hình, dùng đối chiếu với active và pool size. |
| Rejected task count | Mức độ quá tải và công việc bị từ chối; cần instrumentation phù hợp để đếm. |
| Thời gian chạy task | Worker bận vì CPU hay đang chặn I/O? |
| Thời gian caller submit và response latency | Chính sách CallerRuns có làm caller chậm không? |
| Downstream saturation | Connection pool, timeout và các dịch vụ phụ thuộc đã đạt giới hạn chưa? |

**`queueSize=0` là thông tin về cấu trúc, không phải chứng nhận hệ thống khỏe.** Với handoff trực tiếp, chỉ số rejection và active/max thường có ích hơn chiều dài queue.

Ví dụ tình huống cần điều tra: pool size chạm 4/4, active 4/4, queueSize 0, và số lần reject tăng. Điều này **phù hợp với saturation trong direct handoff**, dù queue không hề tăng độ dài.

## 12. Kiểm thử hành vi queue bằng 0

Một kiểm thử đáng tin phải **giữ worker bận bằng synchronization primitive**, giống `DirectHandoffDemo`, thay vì gửi vài task thật nhanh rồi hy vọng scheduler tạo được race.

Quy trình thử với bean Spring:

1. Cấu hình pool **core=2, max=4, queue=0** với chính sách rejection đã biết.
2. Gửi bốn task chặn trên một `CountDownLatch`; dùng latch khác để xác nhận cả bốn đã bắt đầu.
3. Gửi task thứ năm trong khi bốn worker chắc chắn chưa kết thúc.
4. Với AbortPolicy, khẳng định lần gửi thứ năm bị từ chối bằng `TaskRejectedException` ở lớp Spring, hoặc `RejectedExecutionException` khi thử trực tiếp Java executor.
5. Giải phóng latch trong `finally`, đợi task kết thúc và shutdown pool; không để test treo.

Kiểm tra thêm việc **tái sử dụng thread** sau khi worker hoàn tất. Đừng khẳng định một tên worker cụ thể hoặc thứ tự nào chắc chắn được chọn; chỉ cần xác nhận một worker còn sống có thể nhận task kế tiếp khi sẵn sàng và hiểu tại sao điều đó có thể xảy ra.

Nếu muốn xác nhận Spring đã chọn đúng queue type, có thể truy vấn:

~~~java
boolean isDirect =
        executor.getThreadPoolExecutor().getQueue()
                instanceof java.util.concurrent.SynchronousQueue;
~~~

Đây là **đoạn minh họa trong scope có biến `executor` đã được khởi tạo**. Nó kiểm tra cấu hình thực tế, không thay thế bài test behavior.

**Đừng viết test chỉ assert `getQueueSize()==0`.** Kể cả khi pool đang đầy và reject mọi tác vụ tiếp theo, con số ấy vẫn bằng 0 với SynchronousQueue.

## 13. Các lỗi tư duy phổ biến

**“queueCapacity=0 là không có queue nên task nào cũng reject.”** Sai. Nếu worker nhận được ngay hoặc có thể tạo worker mới dưới max, task vẫn được chấp nhận.

**“Direct handoff luôn tạo thread mới.”** Sai. Worker pool có thể tái sử dụng worker rảnh; chỉ tạo thêm worker khi không handoff được và chưa chạm max.

**“Cấu hình maxPoolSize=4 nghĩa là luôn có bốn worker.”** Sai. Worker được tạo theo nhu cầu và chính sách pool; core/max là ngưỡng.

**“queueCapacity=0 giống SimpleAsyncTaskExecutor.”** Sai. Một bên là thread pool có thể tái sử dụng worker và SynchronousQueue, bên kia có mô hình tạo luồng mới cho từng task.

**“queueSize bằng 0 chứng minh không có backlog hoặc sự cố.”** Sai. Không có buffer nội bộ, nhưng bốn worker có thể đang nghẽn và caller có thể bị từ chối.

**“Đặt queueCapacity=0 là bật backpressure tự động bằng cách chặn caller.”** Sai. Với AbortPolicy mặc định, pool từ chối khi đầy; chỉ những chính sách cụ thể như CallerRuns mới khiến caller trực tiếp thực thi task.

**“Chỉ cần tăng maxPoolSize để hết reject.”** Rủi ro. Tăng không giới hạn số platform threads có thể đẩy sự cố sang OS hoặc downstream; cần chọn giới hạn theo khả năng hệ thống.

**“ThreadPoolTaskExecutor có queueCapacity=0 không thể nhận burst.”** Không hoàn toàn. Pool có thể tăng từ core tới max rất nhanh và tận dụng worker rảnh. Nhưng khi cả max workers đang bận, không có buffer để giữ thêm task.

**“@Async có nghĩa caller luôn trả về tức thì.”** Không tuyệt đối: caller có thể chịu chi phí submit, lỗi rejection, CallerRuns hoặc chờ qua future.

**“Không có queue nghĩa là không cần shutdown.”** Sai. Pool vẫn sở hữu worker threads và cần quản lý lifecycle, task duration và việc dừng nhận việc đúng cách.

## 14. Bài tập suy luận

**Bài 1.** Với `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=0`, cả bốn task đều đang chạy và không có worker rảnh. Gửi task thứ năm, dùng AbortPolicy mặc định. Điều gì xảy ra?

**Đáp án:** Không handoff được, không thể tạo worker thứ năm, nên **reject**.

**Bài 2.** Với cấu hình trên, worker #3 vừa hoàn tất và đang chờ task. Caller gửi một tác vụ. Có bắt buộc tạo worker mới không?

**Đáp án:** Không. Handoff trực tiếp có thể đưa task vào worker #3; worker đó được tái sử dụng.

**Bài 3.** `getQueueSize()` liên tục bằng 0, nhưng rejection tăng. Có mâu thuẫn không?

**Đáp án:** Không. SynchronousQueue không lưu task, còn pool có thể bận toàn bộ worker.

**Bài 4.** Đổi `queueCapacity` từ 0 sang 50, giữ core=2 và max=4. Pool còn luôn tăng đến 4 worker ngay khi task thứ ba tới không?

**Đáp án:** Không. Sau khi hai core workers bận, pool thường ưu tiên đưa task vào queue 50 chỗ; chỉ khi queue không nhận thêm mới xem xét tăng worker vượt core.

**Bài 5.** Tại sao `queueCapacity=0` không tương đương với `SimpleAsyncTaskExecutor`?

**Đáp án:** `ThreadPoolTaskExecutor` vẫn có pool, worker có thể được tái sử dụng. `SimpleAsyncTaskExecutor` tạo thread riêng cho từng task.

**Bài 6.** Nếu cấu hình **CallerRunsPolicy** và pool đã đầy, một phương thức `@Async` có chắc chạy ngoài request thread không?

**Đáp án:** Không. Chính request thread có thể thực thi task khi nhận rejection từ executor, ảnh hưởng trực tiếp tới response latency.

**Bài 7.** Có nên dùng `maxPoolSize` rất lớn để tránh rejection khi một database chỉ có 10 connections?

**Đáp án:** Không nên quyết định theo cách đó. Cần xác định mức đồng thời được phép với database, timeout và khả năng chờ/từ chối tại biên phù hợp.

## 15. Checklist triển khai thực tế

- [ ] Xác minh Spring bean thực sự có `queueCapacity=0` và sử dụng `SynchronousQueue`.
- [ ] Cấu hình `corePoolSize` và **`maxPoolSize` hữu hạn** theo workload.
- [ ] Xác định **rejection policy** và hành vi của caller khi pool đầy.
- [ ] Phân biệt rõ **không có buffer** với **không có khả năng nhận task**.
- [ ] Giới hạn tài nguyên downstream: DB/HTTP connections, timeouts, rate limits.
- [ ] Theo dõi `activeCount`, `poolSize`, rejections và task duration; không dựa riêng vào queue size.
- [ ] Kiểm thử bão hòa pool bằng latch và giải phóng/đóng executor đầy đủ.
- [ ] Với `@Async`, gọi qua Spring proxy và xử lý lỗi tại lúc submit riêng với lỗi trong future.
- [ ] Xem lại hành vi shutdown, tác vụ dài và lifecycle của ứng dụng.
- [ ] Đánh giá **queue dương hữu hạn** nếu workload có burst cần đệm ngắn.

## Tổng kết

**`queueCapacity=0` trong `ThreadPoolTaskExecutor` chọn `SynchronousQueue`: tác vụ được chuyển giao trực tiếp cho worker đang đợi, nếu không thì pool tăng worker tới `maxPoolSize`, và sau đó từ chối theo chính sách cấu hình.** Không có buffer lưu tác vụ chờ nhưng vẫn có **thread reuse** của pool. Hiệu quả của cấu hình này nằm ở việc kiểm soát mức đồng thời, độ trễ và quá tải một cách có chủ đích, chứ không nằm ở việc queue có độ dài bằng 0.

**Tài liệu tra cứu:** Spring Framework Javadoc của `ThreadPoolTaskExecutor` (`setQueueCapacity`, `createQueue`); Java SE Javadoc của `ThreadPoolExecutor`, `SynchronousQueue`, `RejectedExecutionHandler`; tài liệu Spring về Task Execution và `@Async`.
