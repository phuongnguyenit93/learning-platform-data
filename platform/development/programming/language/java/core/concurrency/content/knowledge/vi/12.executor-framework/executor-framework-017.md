# `prestartAllCoreThreads()` và `allowCoreThreadTimeOut()`: quản lý luồng lõi trong Java

`ThreadPoolExecutor` cho phép điều khiển số worker thread, hàng đợi công việc và cách thu hồi thread nhàn rỗi. Hai phương thức có tên dễ gây hiểu nhầm là **`prestartAllCoreThreads()`** và **`allowCoreThreadTimeOut(boolean)`**. Một phương thức chủ động khởi tạo các core worker **trước khi cần tới chúng**; phương thức kia cho phép ngay cả các core worker **chấm dứt sau khi nhàn rỗi đủ lâu**.

Chúng phục vụ hai nhu cầu có thể đối lập:

- **Giảm độ trễ tạo thread khi bắt đầu tải:** tạo trước worker bằng `prestartAllCoreThreads()`.
- **Giảm tài nguyên chiếm dụng trong giai đoạn ít việc:** cho phép core worker nghỉ hẳn bằng `allowCoreThreadTimeOut(true)`.

Không có cấu hình tốt nhất cho mọi ứng dụng. Một thread được prestart không có nghĩa đã xử lý task, và một core thread được phép timeout không có nghĩa nó sẽ chết đúng vào một mili-giây cố định. Bài học này giải thích hợp đồng Java SE, điều kiện sử dụng, chi phí, lỗi thường gặp và cách kiểm chứng bằng những chương trình Java 17+.

**Phạm vi:** nhóm **Executor Framework** trong **Java concurrency nói chung**. Bài chỉ dùng `java.util.concurrent.ThreadPoolExecutor` và các API Java SE; các chủ đề cấu hình executor riêng của Spring được để ở chương riêng.

## 1. Mô hình cơ bản của `ThreadPoolExecutor`

Một pool điển hình có bốn thành phần:

```text
              executor.execute(task)
                       |
                       v
             +-------------------+
             | ThreadPoolExecutor|
             +-------------------+
                       |
             +---------+----------+
             |                    |
       tạo worker           đưa vào workQueue
       khi cần               khi phù hợp
             |                    |
             v                    v
       +-----------+        +------------+
       | workers   | <----- | task queue |
       | (threads) |        +------------+
       +-----------+
             |
             v
         chạy task
             |
        chờ task kế tiếp
```

Một số thuộc tính quan trọng:

| Thuộc tính | Vai trò |
| --- | --- |
| `corePoolSize` | Ngưỡng số core worker mà pool ưu tiên tạo khi có công việc; **không phải lời hứa luôn giữ từng ấy thread sống** |
| `maximumPoolSize` | Giới hạn worker tối đa trong cấu hình |
| `keepAliveTime` | Khoảng idle được phép trước khi worker thuộc diện timeout có thể bị thu hồi |
| `workQueue` | Nơi chờ của task chưa có worker nhận |
| `ThreadFactory` | Cách tạo thread, tên, daemon status, handler... |
| `RejectedExecutionHandler` | Cách xử lý khi không nhận thêm task |
| `allowCoreThreadTimeOut` | Quy tắc liệu cả core worker cũng có thể timeout khi idle |

Đây là **cấu hình luồng thực thi**, không phải bảo đảm rằng mọi task sẽ bắt đầu trong một thời gian xác định. Lịch scheduler, độ dài queue, khả năng chặn trong task và tài nguyên máy đều ảnh hưởng độ trễ.

## 2. Phân biệt core thread và non-core thread

Trong `ThreadPoolExecutor`, "core" thường diễn tả **chính sách số lượng worker**. Không nên hình dung mỗi Java `Thread` có một thuộc tính bất biến tên "core" rồi giữ danh tính này suốt đời.

Theo mô hình cơ bản khi gọi `execute`:

1. Nếu số worker ít hơn `corePoolSize`, executor thường cố tạo worker mới cho task.
2. Khi số worker đã đạt ngưỡng core, executor thường cố **đưa task vào queue**.
3. Nếu queue không nhận được task (ví dụ bounded queue đầy), pool có thể cố tạo thêm worker đến `maximumPoolSize`.
4. Nếu không thể nhận thêm theo các quy tắc trên, task đi qua `RejectedExecutionHandler`.

Các thao tác kiểm tra trạng thái đồng thời có thể race với việc shutdown hoặc điều chỉnh cấu hình; `ThreadPoolExecutor` thực hiện thêm kiểm tra nội bộ. Vì thế bốn bước trên là **quy tắc hiểu và thiết kế**, không phải lời hứa thứ tự thực thi chính xác tới từng instruction.

Một cấu hình với **queue không giới hạn** (chẳng hạn `LinkedBlockingQueue` mặc định) thường khiến `maximumPoolSize` ít có cơ hội phát huy vì phần lớn task được xếp hàng sau khi pool đạt core. Ngược lại, với bounded queue nhỏ, pool có thể tăng worker vượt core khi queue đầy.

## 3. Core size không mặc định là số thread đã được tạo

Xét:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        3, 5, 30, TimeUnit.SECONDS,
        new LinkedBlockingQueue<Runnable>());
```

Đây là đoạn minh họa, cần import `ThreadPoolExecutor`, `TimeUnit` và `LinkedBlockingQueue` nếu đặt trong class.

Ngay sau constructor, với cấu hình mới không chạy task, `pool.getCorePoolSize()` là `3` nhưng `pool.getPoolSize()` thông thường là `0`. **Constructor không tự động tạo đủ ba worker**.

Nếu caller gửi task, pool có thể tạo core worker theo nhu cầu. Điều này tiết kiệm tài nguyên lúc mới khởi động, nhưng một vài task đầu có thể phải chịu thêm chi phí tạo thread và gọi `Thread.start()`.

`getCorePoolSize()` là **giá trị cấu hình**. `getPoolSize()` là **số worker hiện đang thuộc pool** tại thời điểm đo; `getActiveCount()` ước lượng số worker đang thực thi task. Ba số này không nên dùng thay cho nhau.

## 4. `prestartAllCoreThreads()` làm gì?

Chữ ký public:

```java
public int prestartAllCoreThreads()
```

Phương thức yêu cầu `ThreadPoolExecutor` **khởi động những core worker chưa có**, tối đa theo cấu hình core hiện tại, thay vì đợi task mới kích hoạt việc tạo worker.

**Giá trị trả về là số worker mới được khởi động bởi lần gọi đó**, không phải tổng worker đang chạy task. Ví dụ, pool mới có `corePoolSize == 3` thường có thể trả `3`. Lời gọi kế tiếp, khi ba worker ấy vẫn hiện diện, trả `0`.

Điều cần nhớ:

- `prestartAllCoreThreads()` **không** tự gọi `execute` hoặc tạo task nghiệp vụ.
- Nó **không** làm `maximumPoolSize` tăng, không tự tạo vượt giới hạn core.
- Nó có thể gọi `ThreadFactory` để tạo thread, dẫn đến chi phí lập tức lúc startup.
- Nó **không cam kết** các thread mới đã hoàn tất phần khởi tạo ứng dụng do task định nghĩa, hoặc đã chạy tới một checkpoint nghiệp vụ.
- Nếu cấu hình đồng thời thay đổi, pool đang shutdown hoặc `ThreadFactory` không tạo được thread như mong đợi, không nên suy ra rằng mọi lần gọi đều trả đúng `corePoolSize`.
- Giá trị trả về có thể bằng `0` khi pool đã có đủ worker hoặc không còn core worker thiếu để khởi động.

**Phân biệt prestart và warm-up:** prestart là khởi động worker của executor. Nếu task đầu cần kết nối, lazy class initialization, nạp cache hay mở tài nguyên, prestart **không tự làm** các bước đó. Warm-up nghiệp vụ cần task/khởi tạo riêng và phải có chính sách an toàn.

## 5. Ví dụ Java 17+: khởi động toàn bộ core worker

Lưu thành `PrestartAllCoreThreadsDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PrestartAllCoreThreadsDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2,
                30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<Runnable>());

        try {
            System.out.println("Before: " + pool.getPoolSize());

            int newlyStarted = pool.prestartAllCoreThreads();

            System.out.println("Started: " + newlyStarted);
            System.out.println("After: " + pool.getPoolSize());
            System.out.println("Second call: "
                    + pool.prestartAllCoreThreads());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PrestartAllCoreThreadsDemo.java
java PrestartAllCoreThreadsDemo
```

Stdout với executor hoạt động bình thường:

```text
Before: 0
Started: 2
After: 2
Second call: 0
```

**Phân tích:**

1. Pool vừa tạo, chưa có task, nên ban đầu chưa tạo worker.
2. `prestartAllCoreThreads()` tạo đủ hai core worker theo cấu hình. Chúng chủ yếu chờ lấy task từ work queue.
3. `getPoolSize()` lúc này phản ánh hai worker đã được thêm vào pool, **không có nghĩa hai worker đang chạy tác vụ**.
4. Vì không thay đổi core size và worker không được phép idle-timeout ở cấu hình mặc định, lời gọi thứ hai không cần tạo thêm.
5. `finally` thực hiện shutdown để ví dụ không giữ process sống bằng những worker nhàn rỗi.

Nếu `ThreadFactory` được tùy biến để từ chối tạo thread, hoặc pool bị thay đổi/shutdown từ bên ngoài, kết quả có thể khác. Ví dụ dùng executor mới, mặc định và chỉ một thread main quản lý cấu hình.

## 6. `prestartCoreThread()` khác `prestartAllCoreThreads()`

Ngoài phương thức tạo tất cả, còn có:

```java
public boolean prestartCoreThread()
```

Nó cố tạo **một** core worker nếu pool chưa có đủ, trả `true` khi một worker mới được tạo; nếu không tạo thêm, trả `false`. Đây là cách điều khiển mức tăng dần.

| API | Công việc | Giá trị trả về |
| --- | --- | --- |
| `prestartCoreThread()` | Thử tạo một core worker còn thiếu | `boolean` |
| `prestartAllCoreThreads()` | Cố tạo toàn bộ core worker còn thiếu | `int`: số worker mới |

Lưu thành `PrestartOneByOneDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PrestartOneByOneDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                3, 3,
                30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<Runnable>());
        try {
            System.out.println("First: " + pool.prestartCoreThread());
            System.out.println("Second: " + pool.prestartCoreThread());
            System.out.println("Third: " + pool.prestartCoreThread());
            System.out.println("Fourth: " + pool.prestartCoreThread());
            System.out.println("Remaining: "
                    + pool.prestartAllCoreThreads());
            System.out.println("Pool size: " + pool.getPoolSize());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac PrestartOneByOneDemo.java
java PrestartOneByOneDemo
```

Stdout:

```text
First: true
Second: true
Third: true
Fourth: false
Remaining: 0
Pool size: 3
```

Với pool mới, không có task, không có concurrent reconfiguration và core timeout đang tắt, ba lời gọi đầu lần lượt tạo worker; lời gọi thứ tư không còn vị trí core để tạo. Sau đó `prestartAllCoreThreads()` trả `0`.

## 7. `allowCoreThreadTimeOut(boolean)` thay đổi điều gì?

Chữ ký:

```java
public void allowCoreThreadTimeOut(boolean value)
```

Theo mặc định, **core worker không bị thu hồi chỉ vì đã idle quá `keepAliveTime`**, còn worker trên ngưỡng core được phép kết thúc sau khi idle đủ lâu. Khi bật:

```java
pool.allowCoreThreadTimeOut(true);
```

thì **core worker cũng áp dụng chính sách idle timeout**. Trong giai đoạn không có task, pool có thể giảm **tới 0 worker**, kể cả khi `corePoolSize` vẫn là số dương.

Một số hệ quả:

- `corePoolSize` **không tự đổi thành 0**; nó vẫn là cấu hình số core dùng khi tạo worker.
- Những worker không nhận thêm việc trong `keepAliveTime` có thể chấm dứt, tùy tiến độ thực thi và trạng thái pool.
- Khi có task mới, pool có thể tạo worker trở lại; lần tạo này lại mang chi phí khởi tạo thread.
- Không có bảo đảm "sau đúng 200 ms mọi core worker biến mất". Scheduler, lúc worker bắt đầu đợi queue, việc có task mới và cách triển khai đều ảnh hưởng thời điểm quan sát.
- Chỉ worker **idle** mới là đối tượng của chính sách thu hồi idle. Một task chạy lâu không bị phương thức này tự interrupt hoặc hủy.

Truy vấn cấu hình bằng:

```java
boolean enabled = pool.allowsCoreThreadTimeOut();
```

Đây là đoạn minh họa với `pool` là `ThreadPoolExecutor`. Phương thức truy vấn có tên **`allowsCoreThreadTimeOut()`**, không phải `isCoreThreadTimedOut()`.

## 8. Điều kiện bắt buộc: `keepAliveTime > 0`

`ThreadPoolExecutor` không cho bật core-thread timeout nếu thời gian keep-alive hiện tại **không dương**. Ví dụ:

```java
pool.allowCoreThreadTimeOut(true);
```

Nếu `pool` đang có `keepAliveTime == 0`, lời gọi trên ném **`IllegalArgumentException`**.

Vì thế, thứ tự cấu hình an toàn thường là:

```java
pool.setKeepAliveTime(250, TimeUnit.MILLISECONDS);
pool.allowCoreThreadTimeOut(true);
```

Hoặc ngay từ constructor, chọn keep-alive dương trước khi bật core timeout.

Một điểm tinh tế: khi core timeout **đang bật**, cố đặt keep-alive không dương bằng `setKeepAliveTime(...)` cũng không phù hợp và có thể bị từ chối theo hợp đồng. Nếu muốn trở về chính sách core không timeout, **tắt core timeout trước**, sau đó mới điều chỉnh keep-alive về 0 nếu thực sự cần.

**Mặc định `allowCoreThreadTimeOut(false)`** không có nghĩa giữ mọi thread bất chấp shutdown: shutdown, worker failure hoặc thay đổi cấu hình có thể dẫn đến worker rời pool. Nó chỉ nói rằng idle-timeout thông thường không áp dụng cho các core worker trong trạng thái pool đang vận hành.

## 9. Ví dụ Java 17+: cấu hình và kiểm tra lỗi keep-alive

Lưu thành `CoreThreadTimeOutValidationDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CoreThreadTimeOutValidationDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2,
                0, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<Runnable>());

        try {
            boolean rejected = false;
            try {
                pool.allowCoreThreadTimeOut(true);
            } catch (IllegalArgumentException e) {
                rejected = true;
            }

            System.out.println("Zero keepAlive rejected: " + rejected);

            pool.setKeepAliveTime(250, TimeUnit.MILLISECONDS);
            pool.allowCoreThreadTimeOut(true);

            System.out.println("Core timeout enabled: "
                    + pool.allowsCoreThreadTimeOut());
            System.out.println("KeepAlive ms: "
                    + pool.getKeepAliveTime(TimeUnit.MILLISECONDS));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac CoreThreadTimeOutValidationDemo.java
java CoreThreadTimeOutValidationDemo
```

Stdout chính xác:

```text
Zero keepAlive rejected: true
Core timeout enabled: true
KeepAlive ms: 250
```

Điều được chứng minh là **quy tắc cấu hình**, không phải đo thời điểm thread hết hạn. Ví dụ không prestart hoặc submit task, vì vậy `getPoolSize()` có thể vẫn là `0` trong suốt chương trình dù cấu hình core size là 2.

Chỉ bật core timeout cũng **không tự tạo worker**. Đây là điểm khác biệt trọng tâm với `prestartAllCoreThreads()`.

## 10. `keepAliveTime` có hiệu lực trong trường hợp nào?

Không phải đồng hồ đo tuổi đời của thread từ lúc được tạo. `keepAliveTime` liên quan đến thời gian **worker idle trong lúc chờ công việc mới**, với chính sách timeout hiện hành.

Xét ba worker của pool, không worker nào đang chạy task:

```text
corePoolSize = 2
maximumPoolSize = 4
keepAliveTime = 5 seconds

Pool có 3 workers, cả 3 đều idle:

Core timeout OFF:
  worker vượt ngưỡng core có thể hết hạn khi idle;
  pool thường giữ tối đa cấu hình core để chờ task.

Core timeout ON:
  mọi worker idle đều thuộc diện timeout;
  pool có thể giảm về 0 nếu không có task mới.
```

Đây là mô hình ý nghĩa, không phải mô tả một thứ tự giết thread cụ thể.

**Lưu ý giới hạn của timeout:**

- Nó **không** làm task đang chạy bị interrupt khi task vượt 5 giây.
- Nó **không** tương đương `Future.get(5, SECONDS)` hay deadline của request.
- Nó **không** giải phóng thread-local value do bạn cố giữ reference ở nơi khác.
- Nó chỉ liên quan đến **quản lý lifecycle worker nhàn rỗi** theo chính sách pool.

Vì vậy, không nên dùng `allowCoreThreadTimeOut(true)` như cơ chế timeout hoặc cancellation cho **tác vụ**.

## 11. Kết hợp prestart và core timeout có mâu thuẫn không?

**Không mâu thuẫn về API**, nhưng hai cơ chế đẩy vòng đời worker theo hai hướng:

```text
             prestartAllCoreThreads()
                       |
                       v
                tạo core workers
                       |
                 chưa có task
                       |
             chờ trên work queue
                       |
                +------+------+
                |             |
       core timeout OFF  core timeout ON
                |             |
       giữ worker idle   idle đủ lâu có thể retire
                |             |
           task mới?         task mới?
                |             |
           tái sử dụng     tạo worker lại nếu cần
```

Khi `allowCoreThreadTimeOut(true)` và keep-alive rất ngắn, những worker vừa prestart có thể hết hạn trước khi tải thực sự tới. Khi đó prestart **có thể không còn tiết kiệm chi phí tạo thread cho burst sau**.

Nếu mục tiêu là "luôn có hai worker sẵn", cấu hình cho phép core timeout về 0 **không thực hiện cam kết đó**. Nếu mục tiêu là "chỉ warm up ở đầu burst rồi cho nghỉ lúc im lặng", cấu hình prestart kết hợp core timeout có thể hợp lý, nhưng phải đánh giá **lúc nào prestart** và chi phí tạo/thu hồi thực tế.

## 12. Quan sát core worker thu hồi: đừng coi thời điểm là deterministic

Ta có thể tạo pool:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 2,
        150, TimeUnit.MILLISECONDS,
        new LinkedBlockingQueue<Runnable>());

pool.allowCoreThreadTimeOut(true);
pool.prestartAllCoreThreads();
```

Đây là đoạn minh họa, cần imports tương ứng.

Nếu **không có task**, hai worker idle có thể kết thúc sau khoảng keep-alive. Nhưng một đoạn:

```java
Thread.sleep(200);
System.out.println(pool.getPoolSize());
```

**không được tuyên bố luôn in 0** trong mọi lịch chạy/JVM. `sleep` của thread đo không bảo đảm hai worker đã thật sự chạy, vào trạng thái đợi và được scheduler thu hồi tại thời điểm main tỉnh lại.

### Chương trình quan sát có giới hạn thời gian

Lưu thành `ObserveCoreRetirementDemo.java`:

```java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ObserveCoreRetirementDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2,
                150, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<Runnable>());

        try {
            pool.allowCoreThreadTimeOut(true);
            int started = pool.prestartAllCoreThreads();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (pool.getPoolSize() != 0
                    && System.nanoTime() < deadline) {
                Thread.sleep(20);
            }

            System.out.println("Started initially: " + started);
            System.out.println("Retired within observation: "
                    + (pool.getPoolSize() == 0));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ObserveCoreRetirementDemo.java
java ObserveCoreRetirementDemo
```

**Đầu ra minh họa trong một lần chạy bình thường:**

```text
Started initially: 2
Retired within observation: true
```

Dòng thứ hai **không được cam kết tuyệt đối**: nếu thread chưa có thời gian chạy/retire trước deadline quan sát, kết quả có thể là `false`. Ví dụ dùng bounded polling chỉ để **quan sát**, không dùng nó làm bằng chứng tiến độ tuyệt đối hoặc cách phối hợp nghiệp vụ. Muốn chờ task hoàn tất, dùng `Future`/`CountDownLatch` thay vì polling số thread.

## 13. Bốn cấu hình thường gặp

Giả sử `corePoolSize > 0` và pool chưa shutdown:

| Prestart? | Core timeout? | Hành vi điển hình |
| --- | --- | --- |
| **Không** | **Không** | Worker được tạo dần khi có task; core worker thường ở lại khi idle |
| **Có** | **Không** | Tạo core worker lúc prestart; có worker nhàn rỗi sẵn để nhận task |
| **Không** | **Có** | Tạo worker khi có tải; cho phép core worker được thu hồi khi idle |
| **Có** | **Có** | Worker có sẵn ngay sau prestart nhưng có thể retire nếu burst không tới kịp |

Đây là tóm tắt **chính sách**, không phải lời bảo đảm số worker chính xác tại từng nanosecond. Còn phải xét `workQueue`, `ThreadFactory`, load, shutdown và điều chỉnh cấu hình động.

Một ví dụ workload:

- **Service có burst ngay sau startup và yêu cầu latency đầu tiên thấp:** cân nhắc prestart và không bật core timeout quá ngắn.
- **Batch processor chỉ thỉnh thoảng chạy:** có thể cho core timeout để không giữ idle thread mãi.
- **Ứng dụng tải liên tục:** nhiều thread đang bận; core timeout chỉ ảnh hưởng khi thực sự có giai đoạn nhàn rỗi.
- **Environment tài nguyên khắt khe:** không nên prestart rất nhiều core worker chỉ vì có CPU core; thread stack và scheduler vẫn có chi phí.
- **Executor chạy công việc blocking lâu:** giữ sẵn worker không giải quyết việc queue ùn ứ; cần sizing và giới hạn concurrency theo tải thực tế.

## 14. Queue quyết định liệu `maximumPoolSize` có phát huy

Một nhầm lẫn phổ biến: đặt `corePoolSize = 2`, `maximumPoolSize = 20` rồi dùng queue không giới hạn, tưởng khi 20 task tới, pool tự tạo 20 thread.

Trong cấu hình điển hình với `LinkedBlockingQueue` không giới hạn, sau khi tạo đủ core workers, phần lớn task mới sẽ được **xếp hàng**, chứ không kích hoạt tạo worker vượt core. `maximumPoolSize` chỉ phát huy khi pool không thể enqueue hoặc một tình huống nội bộ đặc biệt yêu cầu tạo worker.

Mặt khác, nếu dùng `ArrayBlockingQueue` có capacity nhỏ, task đến khi core workers bận và queue đầy có thể khiến pool tạo **non-core worker** cho đến max.

**Prestart core worker không làm thay đổi logic hàng đợi.** Nó chỉ tạo một số worker sớm hơn. Việc queue có giới hạn và rejection policy vẫn là quyết định quan trọng cho backpressure.

## 15. Ví dụ Java 17+: prestart không thay thế sizing theo queue

Lưu thành `QueueGrowthAfterPrestartDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueGrowthAfterPrestartDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 3,
                30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(1));

        CountDownLatch hold = new CountDownLatch(1);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch extraStarted = new CountDownLatch(1);

        try {
            System.out.println("Prestarted: "
                    + pool.prestartAllCoreThreads());

            pool.execute(() -> {
                firstStarted.countDown();
                await(hold);
            });

            firstStarted.await();

            pool.execute(() -> {
                // Đang chờ trong queue cho tới khi có worker rảnh.
            });

            pool.execute(() -> {
                extraStarted.countDown();
                await(hold);
            });

            extraStarted.await();

            System.out.println("Core size: " + pool.getCorePoolSize());
            System.out.println("Current workers: " + pool.getPoolSize());
            System.out.println("Queued tasks: "
                    + pool.getQueue().size());
        } finally {
            hold.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

```bash
javac QueueGrowthAfterPrestartDemo.java
java QueueGrowthAfterPrestartDemo
```

Stdout khi chạy bình thường:

```text
Prestarted: 1
Core size: 1
Current workers: 2
Queued tasks: 1
```

Giải thích lịch chạy có kiểm soát:

1. Pool có core size 1, max 3, queue capacity 1. `prestartAllCoreThreads` tạo một core worker.
2. Task thứ nhất chạy trên một worker và **đợi `hold`**, giữ worker đó bận. Main đợi `firstStarted` trước khi gửi task khác.
3. Task thứ hai được đưa vào queue duy nhất và không được lấy ra vì worker đầu đang chờ latch.
4. Queue đã đầy khi task thứ ba được submit; pool tạo thêm một worker (vượt core nhưng chưa chạm max 3) để chạy task đó. Task thứ ba cũng đợi `hold`.
5. Main đợi `extraStarted`, nên thời điểm in có hai worker đang bị chặn bởi latch và đúng một task nằm trong queue.
6. `finally` mở latch, cho các worker kết thúc, rồi shutdown executor.

**Không suy ra `prestartAllCoreThreads()` đã tạo worker thứ hai.** Nó chỉ tạo một core worker. Worker thứ hai được tạo do **queue đầy khi có task mới**, không phải do prestart.

## 16. Khi nào prestart giúp giảm latency?

Có hai nhóm chi phí cần phân biệt:

1. **Chi phí tạo worker**: `ThreadFactory.newThread`, khởi động thread, cấu trúc nội bộ của JVM và scheduler.
2. **Chi phí nghiệp vụ của task**: class loading, JIT, network handshake, đọc database, khởi tạo resource.

`prestartAllCoreThreads()` có thể chuyển một phần **chi phí nhóm 1** sang lúc startup. Nó không tự thực hiện nhóm 2.

Lợi ích có thể thấy khi:

- Những task đầu đến ngay sau startup và latency của chúng quan trọng.
- Pool có số core vừa phải; tạo thread upfront chấp nhận được.
- Có nhiệm vụ cần dùng `workQueue` đã được nạp trước khi worker bắt đầu đợi.
- Hệ thống muốn điều khiển thời điểm tạo worker trước khi mở nhận tải.

Nhưng **không có bảo đảm cứng** về thời gian task bắt đầu; core thread đã tạo vẫn cần được scheduler cấp CPU. Prestart không khắc phục CPU starvation, queue dài, deadlock hoặc task blocking.

## 17. Khi nào `allowCoreThreadTimeOut(true)` giúp tiết kiệm tài nguyên?

Một Java platform thread có chi phí quản lý, stack và tài nguyên scheduler. Pool giữ sẵn nhiều worker nhàn rỗi có thể lãng phí bộ nhớ trong hệ thống chỉ có các đợt tải ngắn.

Core timeout hữu ích hơn khi:

- Tải có **khoảng nghỉ đủ dài** để thu hồi worker.
- Thời gian khởi động lại worker ở burst sau **chấp nhận được**.
- Pool có core size dương nhưng không muốn giữ minimum idle threads quanh năm.
- Một ứng dụng có nhiều pool độc lập và muốn giảm tổng số idle thread.
- Môi trường chạy có giới hạn thread count/memory, nhưng vẫn cần pool phục vụ burst.

Đánh đổi:

- Task đến sau khi pool rỗng có thể phải chịu **cold thread creation**.
- Những burst ngắn cách nhau một khoảng lớn hơn keep-alive có thể làm thread liên tục được tạo và thu hồi (**churn**).
- Keep-alive quá ngắn có thể gây khó khăn cho latency tail và quan sát số thread.
- Thu hồi worker không phải phép đóng mọi resource do task tạo. Resource không được giải phóng đúng trong task có thể vẫn leak; `ThreadLocal` giữ dữ liệu theo vòng đời thread nhưng lifecycle và cleanup vẫn cần được thiết kế.

**Không tối ưu theo số thread nhỏ nhất bằng mọi giá.** Mục tiêu là độ trễ, throughput, memory footprint và khả năng phục hồi phù hợp workload.

## 18. Core timeout và task blocking: hiểu đúng biên giới

Nếu một worker đang thực hiện:

```java
queue.take(); // chờ lâu trong task nghiệp vụ
```

đây là **task đang chạy**, không phải "worker idle và chờ lấy task tiếp theo" của executor. `allowCoreThreadTimeOut(true)` **không tự interrupt tác vụ** hoặc đặt deadline cho lời gọi `queue.take()` bên trong task.

Điều tương tự áp dụng với:

- `Thread.sleep(60_000)` trong task.
- `Future.get()` trong task.
- Socket/database read đang block.
- Vòng lặp CPU vô hạn.
- Chờ monitor do application code tạo.

Core thread timeout quản lý thời gian **idle giữa các task**. Để giới hạn thời gian chờ của **task**, dùng timeout/cancellation của API nghiệp vụ hoặc `Future` kết hợp cooperative cancellation, chứ không dùng `keepAliveTime` của executor.

`ThreadPoolExecutor` cũng không tự tạo nhiều thread chỉ vì một core worker block trong `Future.get()`; hành vi tăng worker còn phụ thuộc queue/capacity như phần trước.

## 19. Quản lý runtime: `setCorePoolSize` và `setKeepAliveTime`

`ThreadPoolExecutor` cho thay đổi một số cấu hình khi pool còn chạy:

```java
pool.setCorePoolSize(4);
pool.setKeepAliveTime(2, TimeUnit.SECONDS);
pool.allowCoreThreadTimeOut(true);
```

Đây là đoạn minh họa, cần `pool` là `ThreadPoolExecutor` phù hợp.

**Lưu ý khi thay đổi động:**

- `setCorePoolSize` phải tôn trọng `maximumPoolSize`. Nếu core size vượt max, nhận `IllegalArgumentException`.
- Tăng core size có thể làm executor chủ động tạo thêm worker nhằm xử lý task đang chờ; không suy ra mọi thay đổi chỉ ảnh hưởng những task gửi sau đó.
- Giảm core size có thể khiến các worker vượt ngưỡng trở thành ứng viên thu hồi khi nhàn rỗi.
- Thay keep-alive hoặc bật/tắt core timeout có thể tác động cách các worker đang đợi queue được xử lý.
- Nếu core timeout đang bật, keep-alive phải dương. Đổi sang 0 cần tắt core timeout trước.
- Vì thao tác cấu hình có thể chạy đồng thời với submit/shutdown, các metric như `getPoolSize` và `getActiveCount` chỉ là snapshot gần đúng tại thời điểm đọc.

Không nên điều chỉnh pool mỗi vài mili-giây theo một metric duy nhất. Cần thiết kế chính sách ổn định, có hysteresis và quan sát chất lượng hệ thống thực tế nếu dùng adaptive sizing.

## 20. `corePoolSize == 0`: trường hợp đặc biệt

Một `ThreadPoolExecutor` có thể cấu hình `corePoolSize == 0` nếu thỏa các điều kiện constructor và `maximumPoolSize >= 1`.

Khi đó:

- `prestartAllCoreThreads()` **không có core worker nào để tạo**, nên thường trả `0`.
- Không nên dùng prestart như cách ép pool tạo một non-core worker khi core size bằng 0.
- Executor vẫn có thể tạo worker để xử lý những task được submit, theo logic queue và đảm bảo tiến độ của implementation.
- Nếu muốn giữ sẵn một worker khi không có task, cần cấu hình core size dương và chính sách timeout phù hợp.

Đây là cấu hình đặc thù. Không chọn `corePoolSize=0` và queue không giới hạn chỉ bằng suy đoán "mọi task sẽ không bao giờ chạy": implementation có cơ chế tránh để task bị bỏ chờ vô hạn chỉ vì không có worker. Hãy đọc hợp đồng `ThreadPoolExecutor.execute` và test bằng workload thực tế.

## 21. `prestartAllCoreThreads`, queue đã có việc và thay đổi thứ tự startup

Có trường hợp người lập trình tạo executor với một `BlockingQueue<Runnable>` đã chứa task trước khi pool bắt đầu xử lý. Javadoc của `ThreadPoolExecutor` có đề cập việc **prestart core threads** hữu ích khi dùng non-empty queue, để có worker lấy các task đang chờ.

Tuy vậy, hãy cẩn thận với cách đưa task vào queue:

- Gửi công việc qua `execute/submit` để executor kiểm soát chấp nhận task và thread creation.
- **Không trực tiếp thêm task vào `pool.getQueue()`** như một API lập lịch thông thường; điều đó bỏ qua logic rejection/sizing và không có lời hứa mọi task được quản lý như khi submit.
- Khi prestart, đảm bảo task lifecycle, shutdown và rejection được kiểm soát.
- Không nhầm `prestartAllCoreThreads` với `executor.submit`: prestart không trả `Future` cho công việc mới.

Nếu cần một pipeline bắt đầu xử lý chính xác tại mốc startup, thường rõ hơn là tạo executor, cấu hình, submit các task và dùng latch/barrier ở bên trong task để điều phối readiness.

## 22. `ThreadFactory` và chi phí của prestart

`ThreadPoolExecutor` dùng một `ThreadFactory` để tạo worker. Khi prestart, executor có thể gọi factory **trước khi bất kỳ task nghiệp vụ nào được submit**.

Các điều cần xem xét khi tùy biến factory:

- Đặt tên thread có ý nghĩa cho thread dump và profiler.
- Chọn daemon/non-daemon theo lifecycle phù hợp; không dựa vào daemon thread để thay shutdown đúng.
- Thiết lập `UncaughtExceptionHandler` phù hợp, nhưng nhớ executor có cách xử lý exception của task khác nhau giữa `execute` và `submit`.
- Không thực hiện blocking I/O hoặc callback phức tạp trong `ThreadFactory.newThread`.
- Không để factory trả `null` hoặc gây lỗi nếu ứng dụng vẫn giả định prestart luôn tạo đủ core threads.
- Tránh kích hoạt phụ thuộc vòng tròn: factory đợi task executor thực thi, trong khi executor đang chờ factory tạo worker.

Một ví dụ factory đặt tên, dùng cho pool có sẵn:

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

ThreadFactory factory = task -> {
    Thread thread = new Thread(task);
    thread.setName("worker-" + counter.incrementAndGet());
    return thread;
};
```

Đây là snippet minh họa, không có class `main`. Factory có thể giúp quan sát prestart thông qua tên thread. Nhưng đừng dựa vào việc thread đã có tên để khẳng định nó đã thực thi task đầu tiên.

## 23. Giám sát đúng metric, không chỉ `getPoolSize()`

Những method hữu ích của `ThreadPoolExecutor`:

| Method | Thông tin |
| --- | --- |
| `getCorePoolSize()` | Cấu hình core hiện tại |
| `getMaximumPoolSize()` | Cấu hình max hiện tại |
| `getPoolSize()` | Số worker hiện có trong pool tại thời điểm đọc |
| `getActiveCount()` | Số worker đang chạy task, mang tính ước lượng trong concurrent system |
| `getLargestPoolSize()` | Kích thước pool lớn nhất từng đạt từ khi tạo |
| `getQueue().size()` | Số task đang chờ trong queue tại thời điểm đo, không phải toàn bộ submitted tasks |
| `getTaskCount()` | Ước lượng tổng số task từng được lên lịch |
| `getCompletedTaskCount()` | Ước lượng số task đã hoàn tất |
| `getKeepAliveTime(unit)` | Giá trị keep-alive quy đổi sang đơn vị yêu cầu |
| `allowsCoreThreadTimeOut()` | Chính sách core timeout hiện hành |
| `isShutdown()` / `isTerminated()` | Trạng thái vòng đời executor |

Khi quyết định có prestart hoặc bật core timeout, nên đo ít nhất **latency các task đầu sau idle**, độ dài queue theo thời gian, số active workers, memory footprint, thread creation rate và mức sử dụng CPU.

**Không đồng nhất metric snapshot với một invariant liên thời gian.** Ví dụ `getPoolSize() == 0` ngay lúc quan sát không bảo đảm tới dòng tiếp theo pool vẫn trống. Không dùng nó để thực hiện protocol "chỉ submit khi có worker" — executor chịu trách nhiệm tạo worker khi tiếp nhận task phù hợp.

## 24. Shutdown và core worker: các chính sách timeout không thay lifecycle

Khi cần đóng pool:

```java
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
}
```

Đây là snippet minh họa, method bao phải xử lý/truyền `InterruptedException` từ `awaitTermination`.

- `shutdown()` từ chối công việc mới theo contract, cho phép task đã nhận tiếp tục.
- `shutdownNow()` **cố gắng** dừng task đang chạy (thường qua interrupt) và trả danh sách task chưa chạy; không bảo đảm mọi worker dừng tức thì.
- `awaitTermination(timeout, unit)` là **timeout của lần chờ termination**, không tự hủy task nếu trả `false`.
- `prestartAllCoreThreads` không phải lệnh "khởi động lại executor đã shutdown".
- `allowCoreThreadTimeOut(true)` không thay `shutdown()`: pool có thể vẫn nhận task mới và tạo worker trong tương lai dù hiện tại còn 0 thread.

**Không thể dùng core-thread timeout để đảm bảo mọi worker được giải phóng khi application kết thúc.** Shutdown và cleanup là một giao thức riêng, kể cả khi pool có thể co về 0 trong lúc vận hành.

## 25. Những lỗi dễ mắc

**1. "`corePoolSize=10` nghĩa là sau constructor có 10 threads."** Sai. Pool mặc định tạo worker theo nhu cầu; dùng prestart nếu cần tạo trước.

**2. "`prestartAllCoreThreads()` luôn trả core size."** Sai. Nó trả **số worker mới được khởi động trong lần gọi**, có thể là 0.

**3. "`prestartAllCoreThreads()` gửi task warm-up."** Sai. Nó tạo worker, không tự thực thi nghiệp vụ hay khởi tạo resource của application.

**4. "`allowCoreThreadTimeOut(true)` làm `corePoolSize=0`."** Sai. Cấu hình core giữ nguyên; chỉ idle core workers được phép retire.

**5. "Core timeout giết task chạy quá keep-alive."** Sai. Nó áp dụng khi worker **nhàn rỗi giữa các task**, không phải timeout của task.

**6. "Bật core timeout khi keepAlive bằng 0 vẫn hợp lệ."** Sai. Lời gọi ném `IllegalArgumentException`; đặt thời gian dương trước.

**7. "Sau đúng 100 ms pool chắc chắn còn 0 threads."** Sai. Thời điểm quan sát phụ thuộc scheduler, workers có đang idle hay không và timing của poll queue.

**8. "Prestart + core timeout là vô nghĩa."** Không hẳn; có thể prestart cho burst gần và thu hồi sau khoảng idle, nhưng phải benchmark churn/latency.

**9. "Prestart tạo đủ `maximumPoolSize` worker."** Sai. Nó chỉ cố tạo **core workers còn thiếu**; extra workers do workload và queue quyết định.

**10. "Queue không giới hạn sẽ tự tạo đến max khi queue dài."** Không theo quy tắc thông thường; sau ngưỡng core, pool có thể tiếp tục enqueue task.

**11. "`getPoolSize()` chứng minh pool sẵn sàng xử lý task trong deadline."** Không. Metric chỉ cho thấy số worker hiện diện, không bảo đảm scheduling hoặc free capacity.

**12. "Thread đã prestart thì task không còn latency cold-start."** Không chắc. Class loading, JIT, connection setup và resource initialization của task vẫn có thể xảy ra lần đầu.

**13. "`shutdownNow` sẽ luôn giết mọi thread lập tức."** Sai. Nó thường yêu cầu interrupt; task phải hợp tác và API blocking có hợp đồng riêng.

**14. "`ThreadFactory` có thể block tùy ý, không ảnh hưởng prestart."** Sai. Prestart gọi factory để tạo worker; chi phí hoặc lỗi factory ảnh hưởng quá trình này.

**15. "Cứ bật/tắt core timeout liên tục theo `getActiveCount()` là tối ưu."** Không có cơ sở. Metric là ước lượng; policy dao động có thể tăng churn và latency.

## 26. Chọn cấu hình theo mục tiêu vận hành

Trước khi viết:

```java
pool.prestartAllCoreThreads();
pool.allowCoreThreadTimeOut(true);
```

hãy trả lời các câu hỏi:

1. **Có cần worker sẵn ngay khi service bắt đầu nhận tải?** Nếu có, prestart có thể giảm chi phí khởi tạo core threads.
2. **Có thời gian idle dài không?** Nếu có, core timeout có thể tiết kiệm resource.
3. **Giá trị keepAlive có dương và đủ dài?** Quá ngắn gây tạo/hủy liên tục; quá dài giữ thread idle nhiều.
4. **Task đầu có khởi tạo thứ gì khác ngoài thread?** Prestart không thay warm-up nghiệp vụ.
5. **Task chủ yếu CPU-bound hay blocking I/O?** Sizing theo CPU/throughput khác nhau.
6. **Queue bounded hay unbounded?** Điều này quyết định áp lực queue và khả năng tăng vượt core.
7. **Có chính sách từ chối/backpressure không?** Prestart không loại bỏ quá tải.
8. **Task có thể giữ ThreadLocal hoặc resource riêng không?** Lập chính sách cleanup; worker retirement không thay cleanup nghiệp vụ.
9. **Ai sở hữu executor?** Shutdown đúng vòng đời, không chia sẻ một pool không kiểm soát rồi tự ý đóng.
10. **Đo hiệu quả bằng gì?** Startup latency, p95/p99 latency sau idle, queue depth, worker count, memory và thread creation.
11. **Có thay đổi cấu hình đồng thời không?** Test và monitor snapshot, tránh hứa độ lớn worker tại từng thời điểm.
12. **Có cần deadline task?** Dùng timeout/cancellation riêng; không dựa vào core keep-alive.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Tạo `ThreadPoolExecutor` core=4, max=8, không submit task. `getPoolSize()` có luôn bằng 4 sau constructor?

**Không.** Theo thiết kế thông thường pool tạo core worker khi có việc; ngay sau constructor thường có 0. Gọi `prestartAllCoreThreads()` để khởi động core workers trước.

**Câu 2.** `prestartAllCoreThreads()` được gọi hai lần trên pool core=3, không có task hay core timeout. Kết quả điển hình?

Lần đầu trả 3; lần hai trả 0. Giá trị trả về là **số worker mới của lần gọi**, không phải total pool size.

**Câu 3.** `prestartCoreThread()` trả `boolean` hay `int`?

Trả `boolean`. `prestartAllCoreThreads()` trả `int`.

**Câu 4.** Bật `allowCoreThreadTimeOut(true)` có làm task đang chạy quá 30 giây bị hủy?

Không. Core timeout chỉ áp dụng khi worker đang **idle chờ task**; task duration và cancellation là vấn đề riêng.

**Câu 5.** Có được gọi `allowCoreThreadTimeOut(true)` khi keepAlive bằng 0 không?

Không. API từ chối bằng `IllegalArgumentException`. Cần set keepAlive dương.

**Câu 6.** Sau khi bật core timeout, `corePoolSize` có tự thành 0 không?

Không. Giá trị cấu hình vẫn giữ nguyên; số worker thực tế **có thể** giảm về 0 khi idle đủ lâu.

**Câu 7.** Vì sao prestart cộng keepAlive rất ngắn có thể kém hiệu quả?

Worker được tạo sớm có thể hết hạn trước burst, buộc pool tạo lại khi task tới; gây thread churn và mất lợi ích prestart.

**Câu 8.** Đặt core=2, max=20, `LinkedBlockingQueue` không giới hạn có chắc pool tăng lên 20 khi tải cao không?

Không. Sau core, task thường được enqueue; max có thể ít được dùng nếu queue không đầy.

**Câu 9.** `getActiveCount()` bằng 0 có đồng nghĩa không có thread không?

Không. Worker có thể đang idle; cần phân biệt `getPoolSize()` với `getActiveCount()`.

**Câu 10.** `prestartAllCoreThreads()` có bảo đảm lazy database connection của task đã tạo không?

Không. Prestart tạo worker; resource do task khởi tạo chỉ được tạo khi code task thực sự chạy hoặc khi có warm-up riêng.

**Câu 11.** `allowCoreThreadTimeOut(true)` có thay `shutdown()` không?

Không. Pool có thể co về 0 lúc idle rồi lại tạo worker khi nhận task mới; shutdown mới chuyển vòng đời executor sang trạng thái không nhận task mới.

**Câu 12.** Nếu muốn prestart hai worker nhưng cũng muốn chúng có thể nghỉ hẳn khi idle, cần gì?

Đặt `corePoolSize >= 2`, chọn `keepAliveTime > 0`, bật core timeout theo policy và gọi prestart. Tuy nhiên phải chấp nhận worker có thể retire trước task mới, nên không thể đồng thời cam kết **luôn** có hai worker sẵn.

## 28. Tổng kết

- **`prestartAllCoreThreads()`** khởi động các core worker còn thiếu và trả **số worker mới khởi động**. Không tạo task, không tăng max size, không thay warm-up nghiệp vụ.
- **`prestartCoreThread()`** chỉ thử khởi động **một** core worker, trả `boolean`.
- **`allowCoreThreadTimeOut(true)`** cho phép **cả core worker** bị thu hồi khi idle lâu hơn keep-alive; pool có thể giảm về 0 dù core size vẫn dương.
- Core timeout yêu cầu **`keepAliveTime > 0`**. Khi không bật, core worker thường được giữ khi idle trong pool còn chạy.
- **Prestart** ưu tiên sẵn sàng/giảm một phần startup latency; **core timeout** ưu tiên tiết kiệm tài nguyên nhàn rỗi. Bật cả hai hợp lệ nhưng phải cân nhắc churn.
- **Queue và max size** ảnh hưởng việc tạo worker nhiều hơn khi tải tăng; prestart không thay logic enqueue/rejection.
- **Worker idle timeout khác task timeout/cancellation**. Một task block lâu không bị tự hủy vì đã quá keep-alive.
- **Vòng đời executor, shutdown, timeout, giám sát và resource cleanup** vẫn cần được thiết kế độc lập.

Khi tinh chỉnh `ThreadPoolExecutor`, hãy bắt đầu từ câu hỏi: **"Tôi muốn có thread sẵn để giảm latency ban đầu, hay muốn giải phóng idle threads sau khi tải giảm — và tải thực tế có đủ để đánh đổi chi phí tạo lại không?"**. Hai API giúp bạn điều chỉnh đúng mặt này, nhưng lựa chọn hiệu quả cần dựa trên workload, queue policy và đo đạc thay vì suy từ tên phương thức.