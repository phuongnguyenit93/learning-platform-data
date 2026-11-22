# RejectedExecutionHandler và TaskRejectedException: xử lý khi executor không nhận thêm tác vụ

Trong ứng dụng Spring chạy đồng thời, **gửi một tác vụ tới executor không bảo đảm tác vụ luôn được chấp nhận**. Khi thread pool hết khả năng nhận công việc, hoặc đã dừng nhận tác vụ mới, lời gọi gửi việc có thể bị **rejected**. Ở tầng Java, **RejectedExecutionHandler** quyết định hành động khi **ThreadPoolExecutor** từ chối. Ở tầng Spring, **TaskRejectedException** là ngoại lệ thể hiện việc một **TaskExecutor** không chấp nhận một task theo hợp đồng Spring.

Chủ đề này thuộc nhóm **Quá tải và từ chối** của **Spring Framework - concurrency**. Sau bài học, bạn có thể xác định thời điểm rejection xảy ra, chọn chính sách phù hợp, phân biệt lỗi khi submit với lỗi trong task, tích hợp với **@Async**, kiểm thử overload một cách xác định và bảo vệ ứng dụng khỏi việc mất công việc âm thầm.

## 1. Vì sao một tác vụ bị từ chối?

Một thread pool có khả năng xử lý hữu hạn. Ví dụ, một service nhận nhiều yêu cầu tạo báo cáo, mỗi báo cáo chiếm worker và truy cập database trong vài giây. Nếu tốc độ gửi task lớn hơn tốc độ xử lý, hệ thống phải quyết định **xếp chờ, tạo thêm worker, chạy trên luồng gửi hay từ chối**.

**ThreadPoolExecutor** thường xem xét các bước chính:

1. Khi số worker đang có nhỏ hơn **corePoolSize**, cố tạo worker mới để thực thi task.
2. Khi đã có đủ core workers, cố đưa task vào **workQueue**.
3. Nếu không đưa được vào queue, cố tạo thêm worker đến **maximumPoolSize**.
4. Nếu vẫn không nhận được task, gọi **RejectedExecutionHandler**.
5. Executor đã **shutdown** cũng không còn chấp nhận task mới; lúc này rejection có thể xảy ra dù pool không bận.

~~~text
Caller -> execute(task)
               |
        Pool còn dưới core?
          | Có        | Không
          v           v
     Tạo worker    Thử queue.offer(task)
                      | Có chỗ       | Không nhận
                      v              v
                    Queue      Còn chỗ dưới max?
                                  | Có     | Không
                                  v        v
                             Tạo worker  REJECT
                                           |
                                 RejectedExecutionHandler
~~~

Đây là sơ đồ đơn giản của **đường nhận việc**, không mô tả tất cả kiểm tra cạnh tranh và shutdown trong triển khai JDK. Quan hệ giữa **corePoolSize**, **maxPoolSize**, **queueCapacity** rất quan trọng:

| Cấu hình | Hành vi dưới tải |
| --- | --- |
| Queue có giới hạn dương | Sau khi đủ core workers, task thường được xếp hàng; khi hàng đợi đầy mới mở rộng đến max. |
| Queue rất lớn/gần như vô hạn | Task tiếp tục nằm chờ, vì thế **maxPoolSize** có thể hiếm khi phát huy tác dụng. |
| **queueCapacity = 0** trong ThreadPoolTaskExecutor | Dùng **SynchronousQueue**, chuyển giao trực tiếp; không có vùng lưu task chờ. Khi không handoff được, thử tăng worker rồi reject. |
| Executor đã shutdown | Từ chối gửi mới theo chính sách hiện tại, bất kể nhìn thấy queue còn chỗ hay không. |

**Rejected không đồng nghĩa với task chạy thất bại.** Rejection xảy ra ở **ranh giới nhận công việc**: có thể task chưa từng được chạy. Lỗi nghiệp vụ bên trong worker là một sự kiện khác; hai tình huống cần xử lý và giám sát riêng.

## 2. RejectedExecutionHandler là hợp đồng của Java

Trong gói **java.util.concurrent**, giao diện **RejectedExecutionHandler** có một phương thức trừu tượng:

~~~java
void rejectedExecution(Runnable task, ThreadPoolExecutor executor);
~~~

Đây là **chữ ký rút gọn** dùng để giải thích API; kiểu thật được khai báo trong **java.util.concurrent.RejectedExecutionHandler** với tham số **Runnable r** và **ThreadPoolExecutor executor**.

Handler được **ThreadPoolExecutor** gọi khi nó không chấp nhận một task qua đường **execute**. Tùy handler, kết quả có thể là:

- **Ném ngoại lệ** để caller biết việc gửi bị từ chối.
- **Chạy task ngay trên luồng gọi** nhằm tạo áp lực ngược lên bên gửi.
- **Bỏ task**, có hoặc không loại một task khác, tùy chính sách.
- Thực thi **custom policy** do ứng dụng viết, nhưng policy phải quy định rõ hành vi, trách nhiệm với task/future và khả năng quan sát.

Đối tượng **Runnable** được đưa cho handler có thể là task gốc hoặc một wrapper như **FutureTask**, đặc biệt khi người gọi dùng **submit**. Vì vậy, tự viết handler mà âm thầm bỏ task có thể để lại một **Future không bao giờ hoàn tất**.

**Không phải mọi TaskExecutor của Spring đều là ThreadPoolExecutor.** Ví dụ **SimpleAsyncTaskExecutor** có cơ chế giới hạn đồng thời riêng, không tự nhiên biến thành một pool dùng bốn rejection policy của JDK. Trong bài này, **RejectedExecutionHandler** chủ yếu áp dụng cho **ThreadPoolExecutor** và **ThreadPoolTaskExecutor** bọc nó; **TaskRejectedException** là khái niệm rộng hơn ở phía Spring.

## 3. Bốn chính sách rejection có sẵn trong ThreadPoolExecutor

JDK cung cấp bốn triển khai trực tiếp của **RejectedExecutionHandler**:

| Chính sách | Khi không chấp nhận task | Hệ quả cần cân nhắc |
| --- | --- | --- |
| **AbortPolicy** | Ném **RejectedExecutionException** | Rejection tường minh, caller có thể ghi nhận và trả lỗi/phản hồi phù hợp. Đây là mặc định của ThreadPoolExecutor. |
| **CallerRunsPolicy** | Nếu pool chưa shutdown, **luồng gọi execute tự chạy task** | Gây áp lực ngược bằng cách làm caller chậm lại; phá giả định phần việc luôn chạy trên worker khác. Nếu đã shutdown, task bị bỏ. |
| **DiscardPolicy** | Bỏ task và **không ném ngoại lệ** | Có thể mất việc âm thầm; **Future** của task bị bỏ có thể không bao giờ hoàn tất. |
| **DiscardOldestPolicy** | Nếu pool còn hoạt động, bỏ task đang chờ ở đầu queue rồi thử gửi task mới lần nữa | Có thể làm mất task cũ và để future của nó không hoàn tất; khi không có task chờ thích hợp, việc thử lại có thể tiếp tục thất bại. |

**AbortPolicy** thường là lựa chọn dễ kiểm soát nhất cho những tác vụ mà người gọi cần biết đã được nhận hay chưa. Người gọi có thể báo quá tải hoặc quyết định retry có giới hạn.

**CallerRunsPolicy** có ích khi chủ đích là cho bên gửi trả giá bằng thời gian thực thi, từ đó giảm tốc độ gửi task mới. Tuy nhiên, nó **có thể làm một HTTP request thread phải thực thi tác vụ dài**, ảnh hưởng latency hoặc làm sai giả định về MDC, transaction và ngữ cảnh luồng.

**DiscardPolicy** chỉ nên được cân nhắc khi task thực sự có thể bị bỏ **mà không ai chờ kết quả hay cần ghi nhận thành công**. Chẳng hạn, một số tín hiệu đo lường không quan trọng có thể bỏ có kiểm soát, nhưng task nghiệp vụ phải bảo đảm hoàn tất thì không phù hợp.

**DiscardOldestPolicy** không bảo đảm công bằng hay an toàn cho các task có Future. Bỏ task ở đầu hàng đợi có thể khiến Future tương ứng vẫn pending nếu không chủ động cancel. Với **SynchronousQueue** không có buffer, đừng giả định luôn có task cũ trong queue để loại; chính sách này đặc biệt khó lý giải ở cấu hình chuyển giao trực tiếp.

### Chính sách nào là mặc định?

Khi dùng **ThreadPoolExecutor** mà không chỉ định handler khác, JDK dùng **AbortPolicy**. **ThreadPoolTaskExecutor** của Spring cũng dựa trên cấu hình này ở tầng pool nếu ứng dụng không thay đổi handler. Khi tầng Java ném **RejectedExecutionException**, lớp Spring có thể chuyển thành **TaskRejectedException** theo hợp đồng **TaskExecutor**.

Chính sách có thể khác nếu dự án **tự cấu hình setRejectedExecutionHandler**, framework tích hợp cung cấp executor riêng hoặc có lớp wrapper khác. Khi phân tích lỗi thật, luôn xem cấu hình executor thực tế.

## 4. Ví dụ Java 17 chạy được: AbortPolicy và CallerRunsPolicy

Để không phụ thuộc may rủi của scheduler, ta dùng **CountDownLatch** giữ worker đang bận. Pool có **một worker**, **một chỗ queue**; task thứ ba sẽ bị từ chối. Sau đó đổi handler sang **CallerRunsPolicy** để kiểm tra task được thực hiện ngay ở thread gửi.

Lưu thành **RejectionPoliciesDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class RejectionPoliciesDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        Thread submittingThread = Thread.currentThread();

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker không khởi động");
            }

            // Worker thứ nhất đang bị giữ; task tiếp theo nằm trong queue.
            pool.execute(() -> { });

            System.out.println("Queue đã đầy: "
                    + (pool.getQueue().size() == 1));

            boolean aborted = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                aborted = true;
            }
            System.out.println("AbortPolicy từ chối: " + aborted);

            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.CallerRunsPolicy());

            AtomicBoolean ranOnCaller = new AtomicBoolean(false);
            pool.execute(() -> ranOnCaller.set(
                    Thread.currentThread() == submittingThread));

            System.out.println("CallerRuns trên luồng gửi: "
                    + ranOnCaller.get());
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 RejectionPoliciesDemo.java
java RejectionPoliciesDemo
~~~

**Stdout** trong điều kiện bình thường (worker khởi động trong 5 giây):

~~~text
Queue đã đầy: true
AbortPolicy từ chối: true
CallerRuns trên luồng gửi: true
~~~

**Vì sao kết quả xác định?**

1. Task đầu tiên gọi **workerStarted.countDown()**, rồi chờ **releaseWorker**. Main đợi đến khi task đã chạy thực sự.
2. Pool chỉ có một worker và một vị trí queue. Khi task thứ hai được gửi, worker vẫn bị giữ, nên task đó chiếm vị trí queue.
3. Task thứ ba không thể tạo thêm worker vì **core=max=1** và không vào được queue. **AbortPolicy** ném ngoại lệ.
4. Ta thay handler thành **CallerRunsPolicy**. Một task tiếp theo gặp cùng trạng thái bão hòa; handler chạy lambda **ngay trên submittingThread**. So sánh danh tính Thread trả true.
5. **finally** mở latch, shutdown pool rồi chờ kết thúc để tránh giữ luồng nền sau ví dụ.

Chương trình kiểm tra **điều kiện cấu trúc và danh tính luồng**, không dựa vào in tên thread có thể thay đổi. Nếu test bị timeout trước khi worker khởi động, chương trình ném **IllegalStateException** thay vì khẳng định một stdout không đúng.

Đây là **ThreadPoolExecutor thuần Java** nên có thể dùng javac/java. Đối với **ThreadPoolTaskExecutor** của Spring, đường nhận task nền tương tự, nhưng ngoại lệ từ chối được biểu diễn theo hợp đồng Spring.

## 5. Tình huống khi submit Future: tránh chính sách bỏ tác vụ im lặng

Cần phân biệt **execute** và **submit**:

- **execute(Runnable)** chỉ gửi việc; nếu dùng AbortPolicy, rejection thường được ném ngay cho caller.
- **submit(Runnable/Callable)** tạo một **Future** đại diện cho kết quả, rồi gửi wrapper task tới executor. Rejection tại thời điểm gửi có thể xảy ra **trước khi submit trả về Future**.
- Nếu handler **im lặng bỏ task**, đường submit có thể vẫn trả về một Future đã được tạo nhưng **không có worker nào hoàn tất nó**.

Ví dụ minh họa trong một tình huống **pool đã bão hòa**:

~~~java
pool.setRejectedExecutionHandler(
        new ThreadPoolExecutor.DiscardPolicy());

java.util.concurrent.Future<?> future =
        pool.submit(() -> System.out.println("Công việc quan trọng"));
~~~

Đây là **đoạn mã minh họa**, giả sử **pool** là ThreadPoolExecutor đang chạy và đã đạt cả worker/queue limit; nó **không phải chương trình độc lập**. Ở tình huống này, DiscardPolicy có thể khiến submit trả về Future chưa hoàn tất; **future.get() có thể chờ vô hạn** do tác vụ không bao giờ được chạy. Nếu điều này đã xảy ra, cần chính sách cancel/timeout và xử lý xác thực trạng thái thực tế.

**Đừng dùng DiscardPolicy chỉ để “hết thấy lỗi rejection”**. Mất ngoại lệ không có nghĩa hệ thống đã xử lý công việc. Với tác vụ liên quan thanh toán, lưu dữ liệu hoặc thông báo phải bảo đảm, tính toàn vẹn nghiệp vụ đòi hỏi cơ chế tiếp nhận, trả lời, retry hoặc queue bền vững phù hợp.

Tương tự, **DiscardOldestPolicy** có thể làm task đã vào queue bị loại. Nếu task đó là wrapper của Future, code đợi nó có thể mắc kẹt trừ khi có logic cancel đúng cách. Các Javadoc mới cũng khuyến nghị cân nhắc hủy Future và ghi nhận việc loại task trong custom policy.

## 6. TaskRejectedException: ngoại lệ của hợp đồng Spring TaskExecutor

Spring cung cấp **org.springframework.core.task.TaskRejectedException**. Nó **kế thừa java.util.concurrent.RejectedExecutionException**, nên có thể được bắt cụ thể ở ứng dụng Spring hoặc bắt theo kiểu cha trong tích hợp chung với JDK executors.

~~~text
java.lang.RuntimeException
    |
    +-- RejectedExecutionException  (java.util.concurrent)
           |
           +-- TaskRejectedException  (org.springframework.core.task)
~~~

**Ý nghĩa:** một **TaskExecutor** của Spring đã không chấp nhận task được gửi. Đó là tín hiệu về **khả năng tiếp nhận công việc**, không phải một ngoại lệ nghiệp vụ xuất hiện trong task đã thực thi.

Các trường hợp thường dẫn tới lỗi:

- Pool worker đã đạt **maxPoolSize** và queue không nhận được thêm task.
- Executor đã **shutdown** hoặc không còn cho phép submit.
- Một implementation TaskExecutor khác có quy tắc quá tải riêng và biểu diễn việc từ chối qua TaskRejectedException.
- Chính sách rejection ở dưới ném **RejectedExecutionException**, được **ThreadPoolTaskExecutor** bọc theo hợp đồng Spring.

**Lưu ý về custom handler:** nếu handler được cài để **im lặng bỏ task** hoặc **thực thi task ở caller** và trả về bình thường, có thể **không có TaskRejectedException được ném**, dù đường rejection đã được kích hoạt. Nếu handler ném một runtime exception khác với RejectedExecutionException, không nên giả định Spring luôn chuyển mọi loại ngoại lệ đó thành TaskRejectedException.

### Java và Spring nhìn cùng một tình huống

| Tầng | Loại dùng | Kết quả khi AbortPolicy từ chối |
| --- | --- | --- |
| JDK ThreadPoolExecutor | RejectedExecutionHandler, RejectedExecutionException | **RejectedExecutionException** tại chỗ submit/execute. |
| Spring ThreadPoolTaskExecutor | setRejectedExecutionHandler, TaskRejectedException | **TaskRejectedException**, có thể mang nguyên nhân là RejectedExecutionException. |
| Spring @Async gọi qua proxy | Future/CompletableFuture + executor | Lời gọi submit qua proxy có thể **ném TaskRejectedException ngay**; nếu được nhận, lỗi trong worker có thể đến qua future. |

Bắt ngoại lệ này có ý nghĩa thực tế khi đặt giới hạn pool. Ví dụ API cần phân biệt “hệ thống quá bận để nhận việc mới” với “công việc được nhận rồi nhưng tính toán thất bại”.

## 7. Cấu hình ThreadPoolTaskExecutor và chính sách từ chối

Trong Spring, **ThreadPoolTaskExecutor** hỗ trợ cấu hình **corePoolSize**, **maxPoolSize**, **queueCapacity** và **setRejectedExecutionHandler(...)**. Phương thức đặt handler được kế thừa từ lớp hỗ trợ cấu hình executor của Spring.

Ví dụ đây là **các lớp trong ứng dụng có Spring Context**, không phải file độc lập chạy bằng javac trần.

**ReportExecutorConfig.java**:

~~~java
package example.concurrent;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ReportExecutorConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        // Spring khởi tạo bean và quản lý lifecycle của executor.
        return executor;
    }
}
~~~

Cấu hình này cho phép tối đa **4 worker** và một queue chờ tối đa **8 task**. Khi **2 core workers** bận, pool thường ưu tiên nhận task vào queue; khi queue đầy, pool mới thử tăng worker đến 4. Nếu toàn bộ khả năng nhận việc đã hết, **AbortPolicy** từ chối và Spring báo **TaskRejectedException** cho nơi submit.

**Đừng suy luận chỉ từ maxPoolSize=4 rằng pool luôn chạy đúng bốn worker.** Trong trạng thái tải bình thường, nó có thể chỉ có hai worker hoặc ít hơn; các thông số là ngưỡng, không phải cam kết số thread hiện diện mọi thời điểm.

**Điều kiện khai thác:** các con số **2/4/8** chỉ để minh họa. Với workload thật, cần cân nhắc CPU-bound/I/O-bound, thời gian task, queue wait, giới hạn connection pool và chính sách overload.

### Handler nhận task nào?

Handler nhận **Runnable** mà executor cố gửi. Nếu task đã được đóng gói bằng FutureTask, việc log mỗi task bằng **toString()** hoặc giữ task trong một tập riêng có thể tạo overhead/rò rỉ dữ liệu. Một custom handler nên làm công việc thật ngắn gọn, ghi nhận counter và đưa ra lựa chọn có thể kiểm chứng.

Ví dụ **đoạn mã cấu hình** để đếm và ném tiếp ngoại lệ:

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong rejectedCount = new AtomicLong();

executor.setRejectedExecutionHandler((task, pool) -> {
    rejectedCount.incrementAndGet();
    throw new RejectedExecutionException("Executor đã đầy hoặc dừng");
});
~~~

Đây là **đoạn minh họa bên trong lúc cấu hình executor** với biến **executor** đã có. Vì handler ném **RejectedExecutionException**, caller nhận được tín hiệu lỗi; lớp **ThreadPoolTaskExecutor** có thể bọc nó thành **TaskRejectedException**. Một counter đơn giản chỉ đo số lần handler bị gọi **trên instance đó** và không thay thế metrics có nhãn/mức tổng hợp phù hợp ở production.

## 8. Tích hợp với @Async: hai thời điểm thất bại khác nhau

Giả sử một bean thực thi báo cáo trên executor ở mục 7:

**ReportService.java**:

~~~java
package example.concurrent;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        if (reportId.isBlank()) {
            throw new IllegalArgumentException("reportId phải có dữ liệu");
        }
        return CompletableFuture.completedFuture("report:" + reportId);
    }
}
~~~

Một bean khác được Spring quản lý gọi phương thức này **qua proxy**:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.core.task.TaskRejectedException;

try {
    CompletableFuture<String> future = reportService.generate("r-17");

    future.whenComplete((value, error) -> {
        if (error == null) {
            System.out.println("Đã xong: " + value);
        } else {
            System.err.println("Task chạy lỗi: " + error.getMessage());
        }
    });
} catch (TaskRejectedException rejected) {
    System.err.println("Không thể nhận việc: "
            + rejected.getMessage());
}
~~~

Đây là **đoạn minh họa trong phương thức caller** đã inject ReportService; phần code Spring cần dependency và cấu hình bean phù hợp. Ví dụ này cho thấy:

**Trường hợp A — từ chối tại submit:** pool đầy hoặc đã dừng; lời gọi qua **@Async** có thể ném **TaskRejectedException** ngay trong luồng gọi. Chưa chắc có một **CompletableFuture** được trả về để gắn **exceptionally()** hay **whenComplete()**.

**Trường hợp B — task đã được nhận nhưng logic lỗi:** ví dụ reportId rỗng khiến worker ném **IllegalArgumentException**. Với return type **CompletableFuture**, caller quan sát lỗi qua future (như whenComplete, exceptionally hoặc join). Đây **không phải** rejection.

**Trường hợp C — thành công:** task được nhận, thực thi và future hoàn tất với giá trị **report:r-17**. Thứ tự in log giữa nhiều request/worker không được bảo đảm.

Phân biệt ba trường hợp này rất quan trọng khi báo lỗi cho caller hoặc tính retry. **Không nên xem mọi CompletionException/ExecutionException như overload**.

**@Async không tự xử lý overload thay bạn.** Trong mô hình proxy thông thường, lời gọi từ cùng object qua **this.generate(...)** bỏ qua interceptor, khiến hành vi chuyển luồng không như mong đợi. Muốn dùng @Async, phải bật **@EnableAsync** hoặc cấu hình tương đương và gọi qua Spring proxy. Nếu cấu hình **CallerRunsPolicy**, phương thức @Async thậm chí có thể chạy trong thread của caller khi pool bão hòa.

### Async void và xử lý lỗi

Với **@Async void**, caller không có Future để lấy ngoại lệ bên trong worker. Spring cung cấp cơ chế **AsyncUncaughtExceptionHandler** cho trường hợp này. Tuy nhiên, ngoại lệ từ chối **trước khi task được nhận** vẫn thuộc đường gửi việc; đừng chỉ trông vào handler xử lý lỗi từ worker.

Nếu nghiệp vụ cần biết kết quả, dùng **Future/CompletableFuture** có giám sát lỗi hoặc một cơ chế job bền vững phù hợp, thay vì gửi một void task rồi xem lời gọi trả về là cam kết thành công.

## 9. CallerRunsPolicy: backpressure nhưng có chi phí ngữ nghĩa

**CallerRunsPolicy** được dùng vì nó tương đối đơn giản: khi pool bão hòa và chưa shutdown, chính **luồng gọi execute** chạy task. Khi caller là HTTP request thread, điều đó có nghĩa lời gọi **execute** hoặc phương thức proxy **@Async** có thể kéo dài cho tới khi phần công việc hoàn thành.

~~~text
Trước khi bão hòa:
HTTP thread -> submit -> worker xử lý -> HTTP thread rảnh

Khi bão hòa với CallerRunsPolicy:
HTTP thread -> submit
             -> chạy cả task ngay trên HTTP thread
             -> submit trả về sau khi task hoàn tất
~~~

**Ưu điểm:** làm bên gửi chậm lại, giúp giảm tốc độ đưa thêm task mới và có thể tránh bỏ task ngay khi pool còn đang hoạt động.

**Đánh đổi:**

- Response latency của HTTP request có thể tăng mạnh; thậm chí dẫn tới cạn server request threads.
- Đoạn code dự kiến chạy ở background lại chạy cùng luồng với caller. Các giả định về **ThreadLocal**, MDC, transaction hoặc tracing phải được xem xét.
- Nếu task có lock hoặc phụ thuộc đồng bộ vào một tác vụ khác, việc chạy trực tiếp ở caller có thể gây nghẽn khó nhận biết.
- **Khi executor đã shutdown, CallerRunsPolicy không chạy task mà bỏ qua nó**. Vì vậy không được dùng policy này như bảo đảm mọi task sẽ được thực hiện.

**Không nên chọn CallerRunsPolicy chỉ vì muốn “không bao giờ reject”**. Nó tạo backpressure bằng chặn caller trong khi làm việc, có thể hợp lý cho worker producer nội bộ nhưng gây tác động lớn khi người gửi chính là request thread phục vụ người dùng.

## 10. Viết custom RejectedExecutionHandler có trách nhiệm

Handler tùy biến thường cần cho quan sát và điều phối overload. Một mẫu an toàn, dễ dự đoán là **ghi nhận reject rồi ném exception rõ ràng**, như ví dụ AtomicLong ở trên. Nếu muốn đưa task sang cơ chế khác, phải thiết kế hợp đồng tiếp nhận.

Các nguyên tắc quan trọng:

1. **Xác định task đã được tiếp nhận hay chưa.** Handler không được trả về bình thường và đồng thời âm thầm mất một job mà caller tin đã được nhận.
2. **Không chặn quá lâu trong handler.** Handler chạy trên luồng đang submit; đợi vô hạn để queue có chỗ hoặc retry liên tục có thể làm nghẽn request threads và gây deadlock.
3. **Tránh retry đệ quy vô giới hạn ngay trong handler.** Nếu pool vẫn đầy hoặc đã shutdown, lặp execute(task) liên tục có thể tạo vòng lặp không tiến triển.
4. **Giữ thao tác quan sát nhẹ.** Ghi counter, trạng thái pool và correlation ID phù hợp; tránh in dữ liệu nhạy cảm hoặc serialize cả Runnable/FutureTask vào log.
5. **Phân biệt shutdown với saturation.** Cùng một API rejection có thể được gọi trong hai nguyên nhân vận hành khác nhau; nên đọc trạng thái executor và lifecycle khi xử lý.
6. **Tính đến Future đã tồn tại.** Nếu một task bị loại khỏi queue, caller đang chờ Future cần nhận trạng thái cancel/failure tương ứng nếu policy cho phép.
7. **Giữ đúng chính sách tài nguyên.** Tự tạo thread vô hạn trong handler để tránh reject chỉ di chuyển điểm nghẽn ra khỏi pool.

Một custom handler cũng có thể chuyển việc sang một hàng đợi bền vững, nhưng điều đó yêu cầu hợp đồng lưu trữ, xác nhận nhận việc, idempotency, retry và lỗi phù hợp. Đừng coi `execute()` trả về là bằng chứng task đã được ghi an toàn nếu việc ghi có thể thất bại.

## 11. Ứng dụng nên làm gì khi nhận TaskRejectedException?

Phản ứng phù hợp phụ thuộc mục tiêu của lời gọi.

| Loại tác vụ | Lựa chọn có thể phù hợp | Điều cần tránh |
| --- | --- | --- |
| Yêu cầu HTTP đồng bộ cần kết quả ngay | Trả lỗi quá tải có chủ đích, chẳng hạn **HTTP 503** khi service tạm không tiếp nhận được; có thể kèm Retry-After nếu thật sự biết thời điểm thử lại. | Giả vờ trả thành công khi task chưa được nhận. |
| API bị giới hạn theo quota hoặc rate limit | **HTTP 429** khi lý do là giới hạn tốc độ của caller, kèm chính sách retry rõ. | Dùng 429 thay cho mọi lỗi cạn tài nguyên không phân biệt nguyên nhân. |
| Job không được mất | Tiếp nhận qua queue/job store bền vững, có idempotency và trạng thái rõ. | Chỉ dùng DiscardPolicy hoặc in-memory executor như kho lưu trữ lâu dài. |
| Tác vụ best-effort | Có thể drop sau khi đo và giải thích chính sách mất dữ liệu chấp nhận được. | Để caller hiểu nhầm drop là hoàn tất. |
| Xử lý nội bộ với producer có thể chậm lại | Backpressure hoặc bounded retry, cân nhắc CallerRunsPolicy khi hợp đồng thread cho phép. | Vòng retry vô hạn, không có deadline. |

**HTTP 503/429 là lựa chọn ở tầng giao thức và nghiệp vụ**, không phải mã HTTP tự động được Spring gán cho mọi TaskRejectedException. Một ứng dụng có thể dùng **@ControllerAdvice**, exception mapping hoặc tầng API gateway để diễn dịch overload theo hợp đồng của mình. Không nên hứa một thời điểm retry chính xác nếu hệ thống không tính được.

Nếu request tạo job trả **202 Accepted**, chỉ trả 202 khi hệ thống thực sự **đã tiếp nhận công việc theo hợp đồng đã hứa**. Một lời gọi executor trong RAM bị reject không đủ điều kiện để xem là accepted.

## 12. Retry khi overload: phải hữu hạn và có chủ đích

Retry không phải lúc nào cũng đúng. Một task có thể bị reject do shutdown (retry vào cùng executor vô ích), do downstream quá tải, do cấu hình pool quá nhỏ hoặc do burst ngắn. **Retry đồng loạt và tức thì** khi toàn bộ caller cùng gặp reject thường làm hệ thống bận hơn.

Một chính sách retry có kiểm soát cần:

- **Giới hạn số lần** và tổng deadline.
- **Exponential backoff có jitter** khi thích hợp để tránh đám đông retry đồng thời.
- **Idempotency** cho thao tác có side effect: tạo đơn hàng, ghi hóa đơn, gửi thông báo không được nhân đôi sau retry.
- **Phân biệt lý do**: saturated tạm thời, executor đang shutdown, yêu cầu không hợp lệ và lỗi nghiệp vụ; không retry tất cả như nhau.
- **Nhìn tải toàn hệ thống**: retry thêm có thể chỉ làm nghẽn DB/external API, dù executor có nhận task ở lần sau.

Nếu chính handler tự sleep hoặc block để retry, thời gian ấy diễn ra trên **thread submit**, có thể là HTTP request thread. Thường nên đặt retry ở lớp orchestration/caller với deadline rõ, thay vì giấu nó trong RejectedExecutionHandler.

**Điểm mấu chốt:** retry chỉ là chiến lược gửi lại công việc, không bảo đảm xử lý đúng hoặc bền vững. Một hệ thống cần bảo đảm không mất job phải có cơ chế lưu công việc và xác nhận tiếp nhận đáng tin.

## 13. Giám sát overload và không nhầm các chỉ số

Chỉ số cần quan sát cho **ThreadPoolTaskExecutor**:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **getActiveCount()** | Số worker đang thực thi task tại thời điểm quan sát. |
| **getPoolSize()** | Số worker hiện có, không nhất thiết luôn bằng max. |
| **getCorePoolSize() / getMaxPoolSize()** | Các ngưỡng cấu hình để hiểu khả năng mở rộng. |
| **getQueueSize()** | Số task chờ trong queue, chỉ là snapshot tại thời điểm đọc. |
| **Rejected task count** | Cần tự đo hoặc dùng instrumentation phù hợp; tăng cho thấy submit không được chấp nhận theo chính sách ném lỗi. |
| **Task wait/run duration** | Phân biệt nghẽn do queue wait, do CPU hay I/O. |
| **HTTP latency, error rate, downstream saturation** | Kiểm tra tác động tới người dùng và dịch vụ phụ thuộc. |

**Queue size bằng 0 không có nghĩa hệ thống khỏe.** Với **SynchronousQueue** được chọn bởi queueCapacity=0, hàng đợi **không tích trữ task**, trong khi toàn bộ worker vẫn có thể bận và handler reject các task mới.

**Count rejection phải hiểu theo policy.** Với CallerRunsPolicy, handler có thể được gọi nhưng task vẫn được chạy trên caller; với DiscardPolicy, task bị bỏ mà không có ngoại lệ. Vì vậy, nên tách các chỉ số **submission attempts, accepted, caller-runs, rejected-with-error, discarded** nếu ứng dụng cần đo chính xác.

**Không dùng riêng thông điệp exception để phân biệt nguyên nhân.** Kiểm tra trạng thái **isShutdown()** của executor nền khi cần, nhưng một snapshot trạng thái là quan sát thời điểm, không phải sự chứng minh tuyệt đối về nguyên nhân giữa các luồng cạnh tranh.

### Quan sát qua JDK underlying executor

Đoạn Spring sau giả sử một **ThreadPoolTaskExecutor đã initialize**:

~~~java
java.util.concurrent.ThreadPoolExecutor delegate =
        executor.getThreadPoolExecutor();

System.out.println("shutdown=" + delegate.isShutdown());
System.out.println("active=" + executor.getActiveCount());
System.out.println("pool=" + executor.getPoolSize());
System.out.println("queue=" + executor.getQueueSize());
~~~

Đây là **đoạn minh họa trong phương thức có biến executor hợp lệ**, không phải chương trình độc lập. Những số đo có thể thay đổi ngay sau khi đọc; chỉ dùng để định hướng kiểm tra cùng log/metrics liên quan.

## 14. Kiểm thử rejection đáng tin

Để kiểm tra handler, không nên chạy vài task ngẫu nhiên rồi dựa vào **Thread.sleep()** với hy vọng chúng tình cờ bão hòa pool. Có thể tạo tình huống điều phối bằng **CountDownLatch**:

1. Cấu hình **corePoolSize=1, maxPoolSize=1, queueCapacity=1** và AbortPolicy.
2. Gửi task A; dùng latch đợi A đã bắt đầu, rồi giữ A không kết thúc.
3. Gửi task B vào queue; xác nhận queue đã nhận B.
4. Gửi task C; khẳng định caller nhận **TaskRejectedException** tại Spring hoặc **RejectedExecutionException** ở JDK.
5. Đổi policy có chủ đích sang CallerRunsPolicy trong test riêng; assert Runnable được thực thi trên **đúng thread đang gửi task**.
6. Nếu thử shutdown, gọi shutdown trước khi gửi thêm task; assert hành vi theo handler, không suy luận từ tình trạng queue.
7. Trong **finally**, giải phóng latch và đóng executor, tránh treo suite hoặc rò rỉ worker threads.

**Cần test cả Future** khi handler có thể bỏ task: nếu cố tình dùng policy drop, phải kiểm chứng có cơ chế cancel/fail cho Future hoặc caller không chờ Future đó. Test chỉ assert “execute không ném ngoại lệ” là chưa chứng minh công việc đã được thực hiện.

**Các tình huống biên**: task lỗi sau khi được chấp nhận, ứng dụng đóng context trong lúc submit, pool full nhưng một worker vừa rảnh, và một request thread bị kéo sang CallerRuns. Mỗi tình huống kiểm tra một hành vi khác nhau.

## 15. Những nhầm lẫn phổ biến

**“TaskRejectedException có nghĩa task đã chạy và phát sinh exception.”** Sai. Nó thường biểu thị **tác vụ không được chấp nhận để thực thi**.

**“RejectedExecutionHandler luôn ném ngoại lệ.”** Sai. Chỉ handler như AbortPolicy ném; CallerRunsPolicy có thể chạy task, DiscardPolicy có thể bỏ task im lặng.

**“Thêm maxPoolSize là chắc chắn không bị từ chối.”** Sai. Nếu queue/pool vẫn bão hòa hoặc executor đã shutdown thì vẫn reject; max quá lớn còn có rủi ro tài nguyên.

**“queueCapacity lớn khiến maxPoolSize luôn tăng khi bận.”** Sai. Pool thường xếp queue sau khi đủ core, và chỉ thử tạo thêm worker khi queue không nhận được nữa.

**“CallerRunsPolicy vẫn là async.”** Không bảo đảm. Khi bão hòa, task có thể chạy đồng bộ trên thread đang submit.

**“Nếu executor đã shutdown, CallerRunsPolicy vẫn chạy để cứu việc.”** Sai. Theo JDK, nó bỏ task khi executor đã shutdown.

**“Dùng DiscardPolicy để hệ thống không còn lỗi.”** Sai. Chỉ mất tín hiệu từ chối, và có nguy cơ làm Future chờ mãi hoặc mất dữ liệu.

**“TaskRejectedException là con trực tiếp của RuntimeException, không liên quan ngoại lệ JDK.”** Sai. Nó **kế thừa RejectedExecutionException** và có thể được bắt qua kiểu cha.

**“Chỉ bắt lỗi trong CompletableFuture.exceptionally() là đã xử lý rejection.”** Sai. Rejection ngay tại thời điểm gọi @Async có thể xảy ra **trước khi có future để gắn handler**.

**“Queue rỗng tức là executor còn khỏe.”** Sai. Với direct handoff queue bằng 0, pool có thể bão hòa và reject dù queueSize luôn 0.

**“Task submit trả về nghĩa là đã lưu job bền vững.”** Sai. Executor in-memory không phải transactional/durable job queue.

**“Mọi TaskExecutor đều hỗ trợ bốn handler chuẩn của ThreadPoolExecutor.”** Sai. API handler này thuộc JDK ThreadPoolExecutor; từng implementation Spring có cơ chế riêng.

## 16. Bài tập tự kiểm tra

**Câu 1.** Với pool core=2, max=4, queueCapacity=2, tất cả bốn worker đều bận và queue có hai task. Gửi thêm một task với AbortPolicy. Kết quả?

**Đáp án:** Không vào queue và không tạo worker được, nên task bị reject. Dưới JDK là **RejectedExecutionException**, dưới **ThreadPoolTaskExecutor** thường là **TaskRejectedException**.

**Câu 2.** Pool còn nhiều chỗ nhưng đã shutdown. Gửi task mới có được chấp nhận không?

**Đáp án:** Không. Shutdown là một lý do rejection độc lập với saturation.

**Câu 3.** AbortPolicy so với CallerRunsPolicy khác nhau ở đâu?

**Đáp án:** AbortPolicy **ném lỗi** khi không nhận task; CallerRunsPolicy **chạy task trên caller nếu executor chưa shutdown**, từ đó có thể làm caller chậm và phá ranh giới thread.

**Câu 4.** Nếu handler dùng DiscardPolicy và caller nhận một Future, có thể gọi get() vô hạn không?

**Đáp án:** Có thể, khi wrapper task bị bỏ mà Future không được hoàn tất hoặc cancel. Không dùng policy này cho công việc mà caller cần biết kết quả.

**Câu 5.** Lỗi trong phương thức @Async sau khi task đã được nhận có phải TaskRejectedException không?

**Đáp án:** Thông thường không. Đó là lỗi chạy task, được đưa vào Future/CompletableFuture theo kiểu trả về. TaskRejectedException thuộc đường không tiếp nhận task.

**Câu 6.** QueueSize=0 và số lần rejection tăng có mâu thuẫn không?

**Đáp án:** Không, nhất là với SynchronousQueue có queueCapacity=0.

**Câu 7.** Một service trả 202 Accepted sau khi executor ném TaskRejectedException. Có hợp lý không?

**Đáp án:** Không nếu 202 được hiểu là job đã được tiếp nhận, vì task thực tế chưa được nhận. Phải sửa hợp đồng tiếp nhận hoặc cơ chế lưu công việc.

**Câu 8.** Có thể bắt TaskRejectedException bằng catch(RejectedExecutionException e) không?

**Đáp án:** Có, vì TaskRejectedException kế thừa RejectedExecutionException. Trong Spring, bắt kiểu cụ thể thường giúp truyền đạt rõ mục đích.

## 17. Checklist vận hành

- [ ] Xác định đúng executor được dùng ở từng điểm submit và bean @Async.
- [ ] Biết **corePoolSize**, **maxPoolSize**, **queueCapacity** và rejection handler thực tế.
- [ ] Tính đến **shutdown** như một nguyên nhân rejection.
- [ ] Quyết định rõ hành vi **Abort**, **CallerRuns** hoặc chính sách khác trước khi đưa production.
- [ ] Nếu có Future, bảo đảm không mất task âm thầm khiến caller chờ không giới hạn.
- [ ] Ở điểm @Async, xử lý **TaskRejectedException tại submit** khác với **exceptional completion của future**.
- [ ] Giữ retry hữu hạn, có deadline, idempotency và backoff thích hợp.
- [ ] Chọn phản hồi quá tải/API status code đúng ngữ nghĩa (ví dụ 503 hoặc 429 theo nguyên nhân).
- [ ] Theo dõi pool/queue saturation, rejection, task duration và downstream resources.
- [ ] Kiểm thử bằng latch, kiểm tra cả trường hợp worker bận và executor shutdown.
- [ ] Xác định rõ những task **phải được lưu bền vững** trước khi thông báo tiếp nhận thành công.

## Kết luận

**RejectedExecutionHandler** là nơi **ThreadPoolExecutor quyết định hành động khi không nhận thêm task**; lựa chọn này có thể ném lỗi, chạy task trên caller hoặc bỏ task. **TaskRejectedException** là cách Spring báo rằng **TaskExecutor không tiếp nhận tác vụ**, và nó kế thừa **RejectedExecutionException** của Java. Với **ThreadPoolTaskExecutor**, **AbortPolicy** cùng pool/queue hữu hạn và quan sát overload là điểm khởi đầu dễ kiểm soát. Khi kết hợp **@Async**, luôn tách **lỗi ở thời điểm submit** khỏi **lỗi khi task đang chạy**, đồng thời thiết kế chính sách phản hồi/retry không làm mất công việc hoặc che giấu quá tải.

**Tài liệu API tham khảo:** [Java 17 ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html), [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html), [Spring TaskRejectedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html).
