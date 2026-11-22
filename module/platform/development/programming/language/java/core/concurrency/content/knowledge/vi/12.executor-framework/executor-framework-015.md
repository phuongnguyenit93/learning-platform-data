# Thứ tự tiếp nhận việc của ThreadPoolExecutor: core threads, queue, maximum và rejection

## 1. Vấn đề cần hiểu

Trong Java, khi gọi `ThreadPoolExecutor.execute(Runnable)`, executor phải quyết định một task mới sẽ được thực thi theo cách nào: giao cho **worker vừa tạo**, đưa vào **work queue**, tạo thêm worker khi queue không nhận được, hoặc gọi **RejectedExecutionHandler**.

Nhiều người nghĩ `corePoolSize=2, maximumPoolSize=8` nghĩa là executor sẽ chạy đồng thời 8 task ngay khi có 8 request. Điều đó thường **sai**: với work queue có khả năng nhận việc, sau khi đạt core pool size, executor **ưu tiên queue**, không ưu tiên mở rộng ngay đến maximum.

**Quy tắc ghi nhớ:**

~~~text
              execute(task)
                   │
       workerCount < corePoolSize?
            ┌──────┴──────┐
           CÓ           KHÔNG
            │              │
     tạo core worker   thử queue.offer(task)
     chạy task mới       ┌───┴─────┐
                       thành công  thất bại
                           │          │
                    kiểm tra lại     thử tạo worker
                    trạng thái pool  đến maximumPoolSize
                           │          ┌───┴────┐
                       queued      thành công  thất bại
                                      │         │
                                 chạy task     REJECT
~~~

Sơ đồ mô tả **đường quyết định phổ biến** và lược bỏ một số kiểm tra trạng thái đồng thời quan trọng. Thực tế, sau khi queue nhận task, executor **kiểm tra lại** xem pool có bị shutdown hay số worker đã trở về 0 không; nó có thể thu hồi task vừa queue để reject hoặc khởi tạo worker để bảo đảm tiến triển.

Sau bài này, bạn sẽ:

- Mô tả chính xác ba quy tắc **core → queue → maximum → rejection** của `ThreadPoolExecutor`.
- Phân biệt **worker count**, **active count**, **queue size**, **accepted**, **started** và **completed**; không nhầm tiến độ thực thi với quyết định tiếp nhận.
- Hiểu ảnh hưởng của `ArrayBlockingQueue`, `LinkedBlockingQueue`, `SynchronousQueue`, queue có/không giới hạn và các executor factories.
- Phân tích vì sao `maximumPoolSize` gần như không phát huy với unbounded queue nhưng lại quan trọng khi queue bounded hoặc direct handoff.
- Biết tại sao shutdown, racing updates và thất bại tạo worker có thể khiến task bị từ chối dù chỉ nhìn số thread và queue thấy còn chỗ.
- Chọn `AbortPolicy`, `CallerRunsPolicy`, `DiscardPolicy`, `DiscardOldestPolicy` theo yêu cầu không mất task và backpressure.
- Chạy các ví dụ Java 17+ có `CountDownLatch` kiểm soát trình tự, đưa ra stdout chính xác thay vì suy đoán theo `Thread.sleep`.
- Rà soát backlog, tail latency, shutdown, cancellation và nguy cơ starvation/deadlock.

**Phạm vi:** Java SE và Executor Framework, không bàn đến tích hợp framework. Các chương trình trong bài biên dịch bằng JDK 17+.

## 2. Cấu trúc tối thiểu của ThreadPoolExecutor

Constructor hay dùng:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2,                             // corePoolSize
        4,                             // maximumPoolSize
        30,                            // keepAliveTime
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(3),   // tối đa 3 task đang đợi
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

Đây là **đoạn mã minh họa trong method**, chưa phải chương trình độc lập. Caller phải quản lý vòng đời `pool` qua `shutdown()` và phương án chờ/hủy phù hợp.

Các thành phần quan trọng:

| Thành phần | Chức năng |
|---|---|
| `corePoolSize` | Ngưỡng worker mà executor **ưu tiên tạo** trước khi queue các task mới. |
| `maximumPoolSize` | Giới hạn tổng số workers khi queue không nhận thêm task. |
| `workQueue` | Nơi đợi của các task đã được nhận nhưng chưa bắt đầu chạy bởi worker. |
| `keepAliveTime` | Thời gian worker đủ điều kiện được giữ khi idle trước khi có thể bị thu hồi. |
| `ThreadFactory` | Tạo các Thread; có thể đặt tên, daemon, handler, v.v. |
| `RejectedExecutionHandler` | Xử lý task không được tiếp nhận do saturation, shutdown hoặc không thể tạo worker. |
| `execute(Runnable)` | Gửi task để thực hiện về sau, có thể tạo worker mới, enqueue hoặc reject. |

`corePoolSize` và `maximumPoolSize` không phải hai queue và không phải số request độc lập. `maximumPoolSize` là giới hạn **tổng** workers chứ không phải số workers cộng thêm vào core. Ví dụ core=2, max=4 nghĩa là tối đa 4 workers tổng cộng theo cấu hình, không phải 2+4=6.

### Điều kiện cấu hình

~~~text
0 <= corePoolSize <= maximumPoolSize
maximumPoolSize > 0
keepAliveTime >= 0
workQueue != null
~~~

Các tham số không hợp lệ có thể gây `IllegalArgumentException` hoặc `NullPointerException` khi tạo/cấu hình executor. Riêng bật `allowCoreThreadTimeOut(true)` đòi `keepAliveTime > 0`.

## 3. Quy tắc thứ nhất: worker count dưới corePoolSize

Khi executor đang ở trạng thái nhận việc và số workers thấp hơn corePoolSize, nó **ưu tiên thử tạo thêm worker** để chạy task vừa gửi, thay vì xếp task vào queue.

Giả sử cấu hình:

~~~text
corePoolSize = 2
maximumPoolSize = 4
queue capacity = 3
workerCount lúc đầu = 0
~~~

Khi lần lượt gọi `execute(task1)` và `execute(task2)`, nếu chưa có worker nào kết thúc hoặc thay đổi cấu hình:

- Task 1: tạo worker đầu tiên; worker này nhận task 1 làm công việc đầu tiên.
- Task 2: tạo worker thứ hai; worker nhận task 2.
- Queue vẫn trống ở hai lần submit đó vì pool còn dưới core.

**Điểm dễ nhầm:** quy tắc dựa trên **số worker hiện có**, không đơn thuần dựa trên `getActiveCount()`. Javadoc nêu rằng nếu còn dưới corePoolSize, executor ưu tiên thêm worker ngay cả khi có worker hiện tại đang idle. Do vậy không thể suy luận “có một worker idle thì chắc chắn task mới được đưa vào queue” khi tổng workers vẫn dưới core.

### Core workers được tạo lazily

Constructor thường **chưa tạo đủ** core workers ngay lập tức. Nếu cần có workers sẵn trước khi request đến:

~~~java
int started = pool.prestartAllCoreThreads();
~~~

`prestartAllCoreThreads()` trả số core workers mới được khởi chạy. `prestartCoreThread()` thử tạo một core worker còn thiếu. Đây là lựa chọn về khởi động nóng (warm start), không thay đổi quy tắc cơ bản của queue và maximum khi tải tới.

### CorePoolSize = 0

`corePoolSize=0` hợp lệ khi `maximumPoolSize>0`. Executor vẫn có cơ chế tạo worker xử lý công việc, kể cả trường hợp một task đã được queue nhưng chưa có worker. Không được đọc sơ đồ đơn giản theo kiểu “core=0 nên task chỉ queue mãi mà chẳng ai chạy”. Implementation có bước tái kiểm tra sau queue và tạo worker khi cần.

## 4. Quy tắc thứ hai: đạt core thì ưu tiên queue

Khi số workers đã đạt ít nhất corePoolSize, executor **thử đưa task vào work queue trước**, không tự tạo worker mới chỉ vì `workerCount < maximumPoolSize`.

Với core=2, max=4, bounded queue capacity=3 và **hai core workers đều đang xử lý công việc dài**, những task tiếp theo đến như sau:

~~~text
workers đang chạy: [task1, task2]
workQueue:         []

execute(task3) → workQueue.offer(task3) = true
workQueue:         [task3]

execute(task4) → workQueue.offer(task4) = true
workQueue:         [task3, task4]

execute(task5) → workQueue.offer(task5) = true
workQueue:         [task3, task4, task5]

workerCount vẫn có thể = 2 dù max = 4.
~~~

Đây chính là lý do **queue quyết định cách mở rộng**. Nếu queue còn nhận được task, pool thường không tăng worker count lên max.

**Queue chứa việc đang đợi, không chứa task đang chạy.** Khi worker lấy task3 ra khỏi queue, queue size giảm và task3 thành active. Không được coi queue size=0 là hệ thống không còn việc đang thực thi.

### Queue không phải cam kết thứ tự hoàn thành

Task3 có thể được submit và queue trước task6, nhưng task6 có thể được giao trực tiếp cho một extra worker khi queue đầy. Nếu task6 chạy nhanh, nó **có thể hoàn tất trước task3** đang chờ. Dù queue là FIFO, **toàn bộ pool không cung cấp FIFO completion order**. Các task đang chạy trên các worker khác nhau có thể kết thúc theo thứ tự bất kỳ.

Điều này ảnh hưởng rõ ràng tới ứng dụng đòi thứ tự xử lý theo một key, như xử lý update trạng thái một tài khoản. Nếu thứ tự là invariant nghiệp vụ, cần serialization hoặc ordering protocol riêng, không chỉ tin vào FIFO queue.

## 5. Quy tắc thứ ba: queue không nhận được mới thử tăng tới maximumPoolSize

Khi queue `offer(task)` thất bại, executor sẽ thử tạo worker mới chạy task đó với giới hạn `maximumPoolSize`.

Với ví dụ core=2, max=4, queue capacity=3 và các worker đang bận:

~~~text
Sau 5 task:
- worker 1: task1 (đang chạy)
- worker 2: task2 (đang chạy)
- queue: [task3, task4, task5] (đầy)

execute(task6):
- queue.offer(task6) → false
- workerCount=2 < max=4
- tạo extra worker 3, giao task6 làm task đầu tiên

execute(task7):
- queue vẫn đầy
- workerCount=3 < max=4
- tạo extra worker 4, giao task7 làm task đầu tiên
~~~

**Task6 và task7 có thể bắt đầu trước task3–5**, tùy scheduler và thời gian chạy. Extra worker được tạo vì queue không nhận được task; việc task được nhận trực tiếp không tự đảm bảo order với queued tasks cũ.

### MaximumPoolSize không quyết định có tạo worker nếu queue vẫn nhận

Nếu `maximumPoolSize=100` nhưng queue `offer` vẫn thành công, logic ưu tiên queue khiến pool không nhất thiết tạo worker thứ 3 khi core=2. Ngược lại, với `SynchronousQueue` không có chỗ giữ task, offer có thể thất bại ngay khi không có worker chờ handoff, khiến pool tạo thêm workers nhanh hơn.

**Không có một con số maximum “tối ưu” nếu chưa biết queue strategy và workload.**

## 6. Quy tắc thứ tư: không queue được và không thêm worker được thì reject

Khi cả hai điều kiện sau đồng thời đúng:

1. Work queue không nhận thêm task.
2. Không thể tạo thêm worker, chẳng hạn `workerCount >= maximumPoolSize`.

Executor sẽ chuyển task tới `RejectedExecutionHandler`.

Một task cũng có thể bị reject **khi executor đã shutdown**, dù queue còn chỗ hoặc worker count chưa max. Ngoài ra, việc `ThreadFactory` không tạo được Thread, hoặc resource exhaustion, có thể làm không thể tạo worker; không nên coi mọi rejection đều do queue đầy.

Ví dụ core=2, max=4, queue capacity=3:

| Task submit | Hai core và queue vẫn giữ việc | Quyết định thường gặp | Tổng worker | Queue size |
|---|---|---|---:|---:|
| 1 | Chưa có worker | Tạo core worker 1 | 1 | 0 |
| 2 | Task 1 còn chạy | Tạo core worker 2 | 2 | 0 |
| 3 | Hai workers bận | Queue | 2 | 1 |
| 4 | Hai workers bận | Queue | 2 | 2 |
| 5 | Hai workers bận | Queue đầy sau khi nhận task5 | 2 | 3 |
| 6 | Queue đã đầy | Tạo extra worker 3 | 3 | 3 |
| 7 | Queue đã đầy | Tạo extra worker 4 | 4 | 3 |
| 8 | Workers tối đa, queue đầy | Reject/handler | 4 | 3 |

Bảng này **chỉ chính xác dưới giả thiết** chưa task nào kết thúc hoặc được worker lấy ra khỏi queue trong lúc submit. Trong ứng dụng thật, một worker có thể hoàn tất task và lấy task đang chờ trước khi submit tiếp theo, làm thay đổi mọi giá trị. Vì vậy không suy quyết định thực tế **chỉ theo số thứ tự request**.

## 7. Sơ đồ ra quyết định đầy đủ hơn

~~~text
                          execute(command)
                                 |
                       command có null?
                         /             \
                        có             không
                        |                |
                NullPointerException   trạng thái/workerCount
                                         |
                           workerCount < core?
                           /                 \
                         có                  không
                         |                     |
                 addWorker(task, core=true)  pool RUNNING?
                         |                  /           \
                       thành công          có          không
                         |                 |             |
                       return           offer(queue)   không nhận task
                                         /    \
                                       được  không được
                                        |        |
                                RECHECK pool     addWorker(task,
                                  state/count    core=false, <=max)
                                     |               /     \
                           shutdown? 0 workers     được   lỗi
                             |          |           |      |
                        remove/reject  khởi tạo     return  reject
                                     worker nếu
                                     cần
                                        |
                                     return
~~~

Sơ đồ là **mô hình diễn giải** của contract, không phải implementation copy-paste dùng để tự viết executor. OpenJDK sử dụng các thao tác nguyên tử và bước kiểm tra lại để đối phó với thay đổi trạng thái ngay trong lúc quyết định.

### Vì sao cần recheck sau queue offer thành công?

Giả sử thread A kiểm tra pool vẫn RUNNING, sau đó queue.offer(task) thành công. Cùng lúc thread B gọi shutdown. Nếu A cứ trả về “đã nhận” mà không xét thay đổi trạng thái, có thể task nằm trong queue của pool không còn được phép nhận việc mới. Đó là lý do implementation tái kiểm tra `runState`: trong một số interleaving nó gỡ task khỏi queue và reject.

Ví dụ khác: queue nhận task nhưng số workers trở về 0 do timeout/lỗi. Executor cần bảo đảm một worker có thể tiếp tục lấy việc, thay vì để queue có task mà không có worker xử lý. Vì vậy có bước kiểm tra và tạo worker khi cần.

### “Đã được queue” không có nghĩa sẽ được chạy chính xác một lần trong mọi tình huống

Một task có thể:
- được nhận và bắt đầu;
- được queue nhưng sau đó bị `shutdownNow` thu hồi khi chưa chạy;
- bị xóa khỏi queue bởi caller có quyền quản lý tác vụ;
- bị hủy bằng `Future.cancel(...)` trước khi thực thi;
- chạy rồi ném exception (vẫn là lần thực thi đã được bắt đầu).

Đừng đồng nhất `execute` trả bình thường, `submit` trả `Future`, `Future.isDone()`, `Future.isCancelled()` và side effects hoàn tất. Cần một completion/acknowledgment protocol phù hợp nếu đây là công việc nghiệp vụ bắt buộc.

## 8. Ví dụ chạy độc lập 1: kiểm chứng core → queue → max → reject

Chương trình sau **không phụ thuộc vào Thread.sleep()**. Dùng `CountDownLatch` để giữ các workers đang bận cho tới khi main quan sát xong. Qua đó thứ tự admission có thể được xác nhận bằng số worker và kích cỡ queue.

Lưu tệp **AdmissionOrderDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class AdmissionOrderDemo {
    private static Runnable blockingTask(
            CountDownLatch started,
            CountDownLatch release) {
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
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch coreStarted = new CountDownLatch(2);
        CountDownLatch extraStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(blockingTask(coreStarted, release)); // #1
            pool.execute(blockingTask(coreStarted, release)); // #2
            coreStarted.await();

            pool.execute(() -> { }); // #3: queue slot 1
            pool.execute(() -> { }); // #4: queue slot 2

            pool.execute(blockingTask(extraStarted, release)); // #5
            pool.execute(blockingTask(extraStarted, release)); // #6
            extraStarted.await();

            try {
                pool.execute(() -> { }); // #7: queue + workers full
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        System.out.println("completed=" + pool.getCompletedTaskCount());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac AdmissionOrderDemo.java
java AdmissionOrderDemo
~~~

**Stdout khi không có interrupt từ bên ngoài và các worker hoàn thành:**

~~~text
workers=4
queued=2
rejected=true
completed=6
~~~

Giải thích từng bước:

1. Task #1 và #2 khởi tạo hai core workers, rồi hai workers cùng chờ ở `release.await()`.
2. Main chỉ tiếp tục khi `coreStarted.await()` hoàn tất, bảo đảm hai workers đã bắt đầu và **chưa thể kết thúc** trước khi mở release.
3. Task #3 và #4 vào queue capacity 2. Vì cả hai core workers đang chờ release, chưa worker nào lấy hai task này.
4. Task #5 và #6 đến khi queue đầy. Pool tạo workers thứ ba và thứ tư, mỗi worker nhận task mới ngay rồi chờ release.
5. Main đợi cả hai extra workers báo đã bắt đầu, sau đó gửi task #7. Vì queue vẫn chứa #3/#4, bốn workers vẫn bị giữ bận, `AbortPolicy` ném `RejectedExecutionException`; main bắt và ghi true.
6. Trước khi release, các snapshot số lượng chắc chắn là **4 workers, 2 queued**, trong điều kiện ví dụ. Không giả định thứ tự worker name hoặc task finish.
7. Cuối cùng release cả bốn workers; #3 và #4 được xử lý rồi executor shutdown. Sáu task được chấp nhận và hoàn tất; #7 bị reject nên `getCompletedTaskCount()` là 6.

**Chú ý:** `getCompletedTaskCount()` được Javadoc mô tả là một giá trị **ước lượng** khi pool đang hoạt động, nhưng sau khi tất cả tasks chấp nhận hoàn tất và pool terminated, số lượng ở ví dụ này ổn định. Nếu `awaitTermination` không thành công trong 5 giây hoặc task bị interrupt ngoài dự kiến, không được hứa stdout y hệt.

### Vấn đề điều kiện khi demo có lỗi

Chương trình đã đặt `release.countDown()` trong `finally` để tránh giữ workers vĩnh viễn nếu một phép submit/rejection ngoài dự kiến làm main rời block. Trong code thực, còn phải log/propagate error và xử lý shutdown sao cho không làm mất dữ liệu cần hoàn thành.

## 9. Ví dụ chạy độc lập 2: unbounded queue làm maximum ít phát huy

Đối với `LinkedBlockingQueue<>` mặc định, hàng đợi có capacity danh nghĩa rất lớn. Sau khi đã có core worker và worker đó đang bận, task mới được queue thay vì tạo thêm workers tới max.

Lưu tệp **QueueFirstDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueFirstDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 10, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );

        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            running.await();

            pool.execute(() -> { });
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("core=" + pool.getCorePoolSize());
            System.out.println("max=" + pool.getMaximumPoolSize());
            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
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

Biên dịch và chạy:

~~~bash
javac QueueFirstDemo.java
java QueueFirstDemo
~~~

Stdout:

~~~text
core=1
max=10
workers=1
queued=3
~~~

Một worker lõi bị giữ bận trong khi ba task chờ. `max=10` **không buộc executor tạo thêm chín workers**, vì queue vẫn nhận task. Đây là nguyên nhân một pool có maximum lớn nhưng queue depth tăng, tail latency tăng và CPU có thể còn nhàn rỗi.

**Không coi unbounded queue là không có giới hạn tài nguyên.** `LinkedBlockingQueue<>` mặc định có capacity `Integer.MAX_VALUE`, nhưng task objects và queue nodes tiêu tốn heap. Trước khi đạt giới hạn danh nghĩa, ứng dụng có thể gặp memory pressure hoặc `OutOfMemoryError` nếu producer nhanh hơn consumer trong thời gian dài.

## 10. Ví dụ chạy độc lập 3: SynchronousQueue khiến pool mở rộng sớm

`SynchronousQueue` **không giữ các phần tử** như một queue thông thường. Một lần handoff thành công đòi một bên nhận đang chờ tương ứng. Khi pool có core worker bận và không worker nào chờ nhận task, `SynchronousQueue.offer(task)` không có chỗ chứa, khiến executor thử tạo thêm workers tới max.

Lưu **DirectHandoffDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class DirectHandoffDemo {
    private static Runnable blocked(
            CountDownLatch started,
            CountDownLatch release) {
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
                1, 2, 20, TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean thirdRejected = false;

        try {
            pool.execute(blocked(firstStarted, release));
            firstStarted.await();

            pool.execute(blocked(secondStarted, release));
            secondStarted.await();

            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                thirdRejected = true;
            }

            System.out.println("workers=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("thirdRejected=" + thirdRejected);
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

Lệnh:

~~~bash
javac DirectHandoffDemo.java
java DirectHandoffDemo
~~~

Stdout:

~~~text
workers=2
queued=0
thirdRejected=true
~~~

Vì `SynchronousQueue` không chứa backlog:
- Task đầu dùng core worker.
- Khi core bận, task thứ hai không handoff ngay được nên executor tạo extra worker đến max=2.
- Cả hai workers bận, task thứ ba không queue được và không thể tăng worker nữa: reject.
- `queue.size()` vẫn bằng **0**, không có nghĩa pool không bận. Nó là đặc điểm riêng của handoff queue.

**Không tùy tiện đặt maximumPoolSize cực lớn** để tránh rejection với SynchronousQueue: khi nhiều tác vụ blocking liên tiếp đến, pool có thể tạo quá nhiều platform threads và tiêu hao tài nguyên hệ thống.

## 11. Quy tắc queue thay đổi thế nào theo từng cấu trúc?

| Work queue | Có giữ backlog? | Khi đã có core workers và tất cả đều bận | Vai trò maximumPoolSize | Rủi ro |
|---|---|---|---|---|
| `LinkedBlockingQueue<>` không truyền capacity | Có, capacity danh nghĩa rất lớn | Task vào queue | Thường khó chạm tới max | Heap/backlog tăng không kiểm soát |
| `ArrayBlockingQueue<>(n)` | Có, tối đa n task chờ | Task vào queue cho tới khi đầy | Khi queue đầy mới mở rộng | Khi quá tải: rejection |
| `LinkedBlockingQueue<>(n)` | Có, tối đa n task chờ | Tương tự bounded queue | Khi queue đầy mới mở rộng | Cần sizing/backpressure |
| `SynchronousQueue<>` | Không chứa task chờ | Thử giao trực tiếp cho worker chờ; nếu không được thì tạo thêm worker | Tác động sớm | Worker growth, rejection nếu max nhỏ |
| `PriorityBlockingQueue<>` | Có, gần như unbounded mặc định | Queue theo priority policy | Thường không kích hoạt tăng tới max | Priority inversion/starvation, backlog |

Để hiểu executor, **luôn hỏi queue là gì và capacity bao nhiêu trước khi nhìn maximumPoolSize**.

### FIFO queue không đồng nghĩa FIFO toàn executor

Ngay cả với `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` tuân theo thứ tự queue của chúng, task được giao trực tiếp cho extra worker khi queue đầy có thể bắt đầu trước những task đang chờ. Sự phối hợp worker scheduling và thời gian xử lý khiến **completion order** độc lập với **submission order**. Không dùng pool chung làm FIFO transaction engine nếu nghiệp vụ đòi thứ tự tuyệt đối.

### Executors.newFixedThreadPool và newCachedThreadPool

- `Executors.newFixedThreadPool(n)` có cấu hình fixed worker count và queue không giới hạn thực tế: worker count có giới hạn, backlog có thể tăng.
- `Executors.newCachedThreadPool()` sử dụng direct handoff và có thể mở rộng số platform workers mạnh, thu hồi workers idle theo policy: không cung cấp một bounded concurrency limit phù hợp mọi workload.
- `Executors.newSingleThreadExecutor()` chạy một task mỗi lần theo thiết kế, nhưng vẫn cần quản lý hàng đợi và shutdown, và cũng không phải transaction log bền vững.
- `Executors.newWorkStealingPool(...)` thuộc mô hình khác, không nên giả định tuân đúng sơ đồ admission của một `ThreadPoolExecutor` tự cấu hình ở đây.
- Với Java 21+, `Executors.newVirtualThreadPerTaskExecutor()` dùng một virtual thread cho mỗi task; **không** điều tiết downstream concurrency chỉ nhờ core/max/queue như ThreadPoolExecutor platform worker pool.

## 12. Rejection là một hành động theo policy, không nhất thiết là exception

Khi không nhận được task, `ThreadPoolExecutor` gọi `RejectedExecutionHandler.rejectedExecution(task, executor)`. Các policy chuẩn:

| Policy | Khi pool đã saturate và còn RUNNING | Điều cần hiểu |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Mặc định; caller phải xử lý exception, retry có giới hạn hoặc thông báo quá tải. |
| `CallerRunsPolicy` | Caller của `execute` chạy task trực tiếp | Backpressure tự nhiên, nhưng có thể block caller; nếu executor đã shutdown, policy bỏ task. |
| `DiscardPolicy` | Bỏ task không báo lỗi | Nguy hiểm nếu task bắt buộc phải chạy; không có evidence hoàn thành. |
| `DiscardOldestPolicy` | Bỏ head của queue rồi thử gửi task mới | Có thể mất một task cũ; tương tác với priority queue rất dễ sai kỳ vọng. |

**Quy tắc đặc biệt:** `RejectedExecutionHandler` là extension point, nên một handler tùy biến có thể block, đưa vào kênh khác, ghi metric, throw hoặc làm nhiều việc khác. Vì thế không thể nói “mọi rejection chắc chắn throw exception”. Với `AbortPolicy` mặc định thì có exception; với `DiscardPolicy`, `execute` có thể return bình thường **dù task không được chạy**.

### Rejection cũng xuất hiện sau shutdown

~~~java
pool.shutdown();
pool.execute(() -> System.out.println("will not be accepted"));
~~~

Với AbortPolicy, `execute` ném `RejectedExecutionException` vì pool không còn nhận công việc mới, **không cần queue đã đầy**. Với CallerRunsPolicy, nếu executor đã shutdown, policy không chạy task trên caller. Vì vậy cần kiểm tra trạng thái lifecycle và policy, không suy tất cả rejection là saturation.

## 13. Ví dụ chạy độc lập 4: CallerRunsPolicy tạo backpressure

Giả sử pool chỉ có **một worker**, một slot queue, và task đầu đang giữ worker. Task thứ hai chiếm queue; task thứ ba khi submit bị reject theo nghĩa admission thông thường, nhưng CallerRunsPolicy **tự chạy ngay trong main**.

Lưu tệp **CallerRunsDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 10, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<String> thirdThread = new AtomicReference<>();

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workerStarted.await();

            pool.execute(() -> { }); // task 2 xếp hàng
            pool.execute(() ->
                    thirdThread.set(Thread.currentThread().getName()));

            System.out.println("thirdThread=" + thirdThread.get());
            System.out.println("queued=" + pool.getQueue().size());
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

Biên dịch/chạy:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Stdout khi chạy trực tiếp qua `java CallerRunsDemo` từ main thread mặc định:

~~~text
thirdThread=main
queued=1
~~~

Giải thích:
- Worker vẫn chờ `release`, task #2 đang queue.
- Task #3 đến khi không còn capacity; CallerRunsPolicy gọi `run()` của task ngay trên thread thực hiện `execute`, tức main.
- `thirdThread` được gán "main" trước khi `execute` trả về; không chờ worker.
- Queue vẫn chứa task #2, còn worker đầu chưa được release. Vì vậy số queued là 1.
- Nếu chạy main bằng một harness đổi tên thread, tên có thể khác; ngữ nghĩa ổn định là **thread thực hiện submit**.

**Lợi ích:** producer bị chậm lại vì phải tự xử lý task, tạo dạng backpressure. **Chi phí:** nếu caller là event-loop hoặc thread phục vụ request nhạy latency, nó có thể bị block rất lâu, gây xấu tail latency.

## 14. execute và submit khác nhau ở đâu trong tình huống này?

`ThreadPoolExecutor.execute(Runnable)` trực tiếp áp dụng chính sách admission/rejection.

Khi dùng `ExecutorService.submit(Callable)` hoặc `submit(Runnable)`:
- `submit` thường bọc công việc vào một `FutureTask`, rồi gửi thông qua `execute`.
- Nếu task được chấp nhận, `submit` trả `Future` để lấy kết quả/hủy.
- Nếu `AbortPolicy` reject, exception có thể được ném trong lúc submit và caller **không** có Future của task đã được nhận.
- Nếu handler **silently discard**, caller có thể nhận một Future không bao giờ được thực thi/xong theo đường bình thường; `Future.get()` có thể chờ mãi nếu không có cancellation/timeout.
- Với CallerRunsPolicy, tác vụ có thể chạy trên **thread gọi submit** trước khi `submit` trả.
- `Future.cancel(true)` chỉ yêu cầu hủy theo API; không cưỡng bức task đang làm side effect phải dừng.

**Không dùng `submit` làm bằng chứng task chắc chắn sẽ chạy.** Hãy xét cả handler, shutdown, queue removal và lifecycle. Nếu cần workload có tính bền vững, cần một lớp admission/acknowledgment rõ ràng hơn một queue chỉ nằm trong RAM.

### Exception của task

Với `execute`, exception chưa xử lý từ `Runnable.run()` có thể đi qua cơ chế uncaught-exception/worker lifecycle. Với `submit`, exception của `Callable/Runnable` thường được giữ trong `Future` và thể hiện khi `Future.get()` ném `ExecutionException`. Điều này **khác** rejection lúc submit. Đừng nhầm “task chạy rồi thất bại” với “task không được nhận vào executor”.

## 15. Những race thực tế mà sơ đồ đơn giản không vẽ hết

### 15.1. Shutdown xảy ra sau khi queue.offer thành công

Thread A nhận được true khi queue.offer. Thread B có thể gọi `shutdown()` gần như cùng lúc. Executor tái kiểm tra trạng thái và khi cần có thể **remove task vừa enqueue rồi reject**, thay vì để một task mới lọt qua thời điểm shutdown không hợp lệ.

Đó là lý do state check và admission phải dùng một giao thức đồng bộ/atomic ở mức implementation. Người viết ứng dụng không nên tự thay thế `execute` bằng:

~~~java
if (!pool.isShutdown()) {
    pool.getQueue().add(task); // KHÔNG PHẢI cách submit task chuẩn
}
~~~

Đoạn trên là minh họa **sai**. Giữa check và add, pool có thể shutdown; việc thao tác queue trực tiếp bỏ qua quá trình tạo worker và retry/rejection. Javadoc cũng không khuyến khích dùng `getQueue()` để điều khiển công việc thông thường, ngoại trừ monitoring/debugging hoặc một số thao tác quản trị có chủ đích.

### 15.2. Queue nhận task nhưng không còn worker

Nếu workers đã kết thúc do lỗi, timeout hoặc tình huống cạnh tranh, một lần queue.offer thành công không tự bảo đảm có ai đang tiêu thụ queue. Executor kiểm tra worker count và có thể tạo worker mới (kể cả khi corePoolSize=0) để tránh queue bị bỏ mặc.

### 15.3. ThreadFactory tạo worker thất bại

Nếu `ThreadFactory.newThread(...)` trả null hoặc không thể tạo thread do tài nguyên, việc addWorker có thể thất bại. Kết quả cuối có thể là rejection; **worker count còn dưới maximumPoolSize** không bảo đảm thread mới chắc chắn được tạo.

### 15.4. Metrics thay đổi giữa hai lần đọc

`getPoolSize()`, `getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()` không phải một snapshot transaction của executor. Trong khi bạn đo lần lượt, worker có thể vừa rời task, dequeued task mới hoặc bị thu hồi. Chúng hữu ích để monitoring, nhưng không nên dùng để tự viết một thuật toán check-then-act thay thế `execute`.

## 16. KeepAlive và core timeout tác động gì tới admission?

`keepAliveTime` không thay quy tắc cơ bản core → queue → max. Nó ảnh hưởng tới **số workers đang tồn tại** khi pool idle, từ đó có thể làm những lần execute sau thấy worker count thấp hơn core.

- Khi worker count lớn hơn corePoolSize, workers dư có thể bị thu hồi sau thời gian idle theo keepAlive policy.
- Mặc định core workers được giữ khi idle, trừ trường hợp shutdown, lỗi và lifecycle cần thay thế.
- `allowCoreThreadTimeOut(true)` cho phép ngay cả core workers bị thu hồi khi idle, với điều kiện keepAliveTime > 0.
- `prestartAllCoreThreads()` tạo sẵn core workers, làm thay đổi trạng thái ban đầu trước khi request đến.
- keepAlive **không** giới hạn thời gian một task chạy, **không** ép task đang block phải kết thúc khi quá hạn.

Do đó, “lần submit tiếp theo sẽ queue hay tạo core worker?” phụ thuộc worker count hiện thời, mà worker count chịu ảnh hưởng bởi prestart, timeout, lỗi worker và kích thước core được thay đổi động.

## 17. Vì sao ưu tiên queue trước extra workers có tradeoff?

Đây là chính sách thiết kế quan trọng của ThreadPoolExecutor, không phải chi tiết nhỏ.

**Ưu điểm khi queue vừa phải:**
- Hạn chế tạo platform threads quá nhanh.
- Tái sử dụng workers hiện có, có thể giảm overhead scheduling và memory stacks.
- Hấp thụ một burst ngắn khi tốc độ nhận việc tạm vượt tốc độ xử lý.

**Nhược điểm khi queue quá lớn:**
- Tasks phải chờ lâu trước khi bắt đầu dù maximumPoolSize còn cao.
- Memory giữ nhiều Runnable/FutureTask và dữ liệu capture; dễ tăng heap usage.
- Deadline đã hết khi task còn trong queue; task có thể trở thành việc vô ích.
- Độ trễ đuôi (p95/p99) xấu nhưng hệ thống không reject, khó phát hiện overload nếu chỉ nhìn error rate.

**Ưu điểm của queue nhỏ/direct handoff:**
- Khi workers bận, pool có thể thêm workers sớm hơn tới maximum.
- Capacity giới hạn và rejection dễ thấy hơn.

**Nhược điểm:**
- Dễ tạo nhiều threads, context switching, tăng tải downstream (DB, remote API, disk).
- Nếu max nhỏ và traffic burst, nhiều task có thể bị từ chối mặc dù burst chỉ diễn ra ngắn.
- Caller phải có protocol backpressure/retry/fallback chính xác.

Không có chiến lược nào tốt nhất mọi nơi. Chọn queue dựa trên throughput của consumer, deadline, memory budget, số tác vụ đến cùng lúc và ý nghĩa của rejection.

## 18. Thread-starvation deadlock khi task con bị queue

Một trường hợp nguy hiểm:

~~~text
core = maximum = 1
workQueue là unbounded

Worker duy nhất chạy task A
  A submit task B vào cùng pool → B vào queue
  A gọi futureB.get() → chờ B hoàn tất
  B đang queue, cần worker đang bị A giữ
=> không có worker rảnh để chạy B
=> A và B có thể chờ vô hạn
~~~

Tăng `maximumPoolSize` **không cứu được** nếu queue unbounded tiếp tục nhận task B, khiến pool không tạo extra worker. Vấn đề nằm ở **cấu trúc phụ thuộc công việc** và admission policy.

Giải pháp có thể là:
- Tránh task cha blocking đợi task con trong cùng fixed pool.
- Tách các loại việc có dependency khác nhau sang executors thích hợp.
- Thiết kế completion/composition không chặn worker đang giữ capacity.
- Đảm bảo không có vòng chờ tài nguyên, không dựa vào queue growth để giải quyết liveness.
- Sử dụng timeout ở chỗ thực sự chờ nếu có nhu cầu, nhưng timeout chỉ phát hiện/chấm dứt việc chờ, không tự làm hoàn thành task con.

## 19. Quan sát và giám sát admission trong production

Các metrics nên theo dõi:

| Metric | API/cách quan sát | Gợi ý |
|---|---|---|
| core size cấu hình | `getCorePoolSize()` | Ngưỡng trước queue. |
| max size cấu hình | `getMaximumPoolSize()` | Trần worker khi không queue được. |
| worker count hiện tại | `getPoolSize()` | Có thể khác core và max. |
| số workers đang chạy task | `getActiveCount()` | Ước lượng tại thời điểm đọc. |
| tasks đang queue | `getQueue().size()` | Không tính tác vụ đã được worker lấy. |
| task hoàn tất | `getCompletedTaskCount()` | Giá trị ước lượng khi còn hoạt động. |
| tổng số task | `getTaskCount()` | Ước lượng tasks đã submit/được xử lý theo metrics. |
| số workers lớn nhất từng có | `getLargestPoolSize()` | Giúp biết đã bao giờ chạm vùng extra chưa. |
| rejection count | Custom rejection handler/metric riêng | Cần tách saturation vs shutdown. |
| thời gian chờ queue | Timestamp admission/start có protocol đúng | Không lấy latency task bằng mỗi queue size. |

Các counters/metrics của ThreadPoolExecutor giúp **quan sát**, không làm cơ chế điều tiết đồng thời tự đúng. Một custom handler có thể ghi lại rejection, nhưng không được nuốt task bắt buộc mà caller vẫn tưởng nó đã được nhận.

### Ví dụ custom handler có ghi nhận và từ chối

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicLong;

final class CountingAbortHandler implements RejectedExecutionHandler {
    private final AtomicLong rejected = new AtomicLong();

    @Override
    public void rejectedExecution(Runnable task, ThreadPoolExecutor pool) {
        rejected.incrementAndGet();
        throw new RejectedExecutionException(
                "executor rejected task; shutdown=" + pool.isShutdown());
    }

    long rejectedCount() {
        return rejected.get();
    }
}
~~~

Đây là một **class Java hợp lệ nhưng chưa có main**. Khi đặt vào constructor executor, handler ghi nhận số lần rejection rồi ném exception để caller biết task **không được nhận**. Nếu cần phân loại nguyên nhân, đừng chỉ dựa vào snapshot `isShutdown()` vì trạng thái có thể đổi giữa quyết định reject và callback; kết hợp lifecycle logs và metrics có contract rõ hơn.

## 20. Đọc code nguồn OpenJDK: ba bước của execute

JDK thực tế diễn giải ý tưởng ở mức implementation với ba giai đoạn:

1. Nếu worker count dưới core, thử `addWorker(command, true)` và return khi thành công.
2. Nếu pool đang RUNNING, thử `workQueue.offer(command)`. Khi thành công, **tái kiểm tra trạng thái**: nếu pool không RUNNING nữa và xóa task được, reject; nếu vẫn thiếu worker, tạo worker để đảm bảo có consumer.
3. Nếu không enqueue được, thử `addWorker(command, false)` trong giới hạn max. Nếu không tạo được, gọi rejection.

**Đây là mô tả logic**, không phải bản sao mã nguồn hay triển khai để người học tự xây executor. Những kiểm tra CAS và runState của OpenJDK rất quan trọng để không có race giữa shutdown, queue, worker creation và thread failure.

Điểm tinh tế nhất là **return từ bước 2 không chỉ dựa trên một phép queue.offer()**. Bước double-check ngăn task bị bỏ mặc hoặc lọt vào trạng thái shutdown sai. Khi debug một trường hợp executor reject “bất thường”, cần nhớ trạng thái pool có thể đã thay đổi giữa các lần kiểm tra.

## 21. Checklist review cấu hình và logic tiếp nhận

1. **corePoolSize, maximumPoolSize hiện tại là bao nhiêu?** Đã xác minh maximum là tổng worker cap, không phải số extra riêng?
2. **Queue loại gì, capacity bao nhiêu?** `LinkedBlockingQueue<>` mặc định gần như unbounded, `ArrayBlockingQueue` bounded, `SynchronousQueue` không giữ backlog.
3. **Khi dưới core, có hiểu worker được tạo ưu tiên không?** Constructor mặc định không nhất thiết prestart.
4. **Sau khi đạt core, có hiểu queue được ưu tiên trước mở rộng không?** Đừng hứa max được dùng ngay khi task count tăng.
5. **Khi queue đầy, có tính max tổng cộng không?** Sau đó phải tính rejection.
6. **Rejection policy là gì?** Abort, CallerRuns, Discard, DiscardOldest hay custom? Caller có được báo rõ khi việc bị bỏ?
7. **Có shutdown đồng thời với submit không?** Nhớ executor có double-check sau enqueue và reject khi không còn RUNNING.
8. **Task có thể kết thúc trước khi submit hết batch không?** Đừng dự đoán states theo số thứ tự task nếu không có điều kiện điều khiển.
9. **Có task cha đợi task con trên cùng pool không?** Tránh thread-starvation deadlock.
10. **Queue retention bao lâu?** Deadline của task có thể đã hết trước khi bắt đầu.
11. **Có backpressure hoặc giới hạn producer không?** Không chọn unbounded queue chỉ để tránh rejection trước mắt.
12. **Có monitoring queue depth, active count, completed, rejection và tail latency?** Đã phân biệt metrics ước lượng với synchronization primitives?
13. **Timeout/cancel thuộc layer nào?** keepAlive không phải task timeout, Future.get(timeout) không tự hủy.
14. **Có shutdown/awaitTermination/cleanup đúng?** Sau shutdown, việc mới không được chấp nhận theo admission.
15. **Đã test overload với queue cố định chưa?** Dùng latch/handoff kiểm soát trình tự, không dựa sleep và đoán scheduler.

## 22. Bài tập tự kiểm tra

**Câu 1.** Pool core=2, max=8 và unbounded LinkedBlockingQueue. Hai core workers đang bận, 20 task đến thêm. Có chắc pool sẽ tạo đủ 8 workers không?

**Đáp án:** Không. Sau core, queue nhận được task; maximumPoolSize thường không có tác dụng khi queue còn capacity. Backlog tăng trong queue.

**Câu 2.** Pool core=2, max=4, queue capacity=2. Hai core đang bận, queue đã chứa hai tasks. Task tiếp theo được xử lý thế nào?

**Đáp án:** Queue offer thất bại; nếu pool còn RUNNING và tạo worker được, executor tạo worker thứ ba (extra) để chạy task mới.

**Câu 3.** Nếu pool đã có 4 workers đều bận và queue vẫn đầy, task mới sẽ làm gì?

**Đáp án:** Chuyển sang RejectedExecutionHandler. Với AbortPolicy, `RejectedExecutionException`; với CallerRunsPolicy khi pool chưa shutdown, caller chạy task.

**Câu 4.** Vì sao task được submit sau có thể chạy trước một task đang queue trước đó?

**Đáp án:** Khi queue đầy, executor có thể tạo extra worker chạy **task mới trực tiếp**. Task cũ tiếp tục đợi trong queue, nên không có bảo đảm FIFO cho toàn bộ start/completion order.

**Câu 5.** `SynchronousQueue` có chứa nhiều tasks đang đợi khi pool quá tải không?

**Đáp án:** Không. Đây là handoff queue không có storage capacity. Khi không handoff được, executor thử tạo worker đến max hoặc reject.

**Câu 6.** `ThreadPoolExecutor.execute` đã queue task, sao vẫn có thể reject?

**Đáp án:** Executor tái kiểm tra sau offer. Nếu pool shutdown trong lúc submit và task có thể bị remove, nó sẽ reject thay vì để task mới được giữ trái policy.

**Câu 7.** `getQueue().size() == 0` có chứng minh executor hoàn toàn idle không?

**Đáp án:** Không. Workers có thể đang xử lý tasks, đặc biệt với SynchronousQueue luôn không giữ backlog.

**Câu 8.** `submit` trả Future dưới DiscardPolicy có bảo đảm Future sẽ hoàn tất không?

**Đáp án:** Không. Handler có thể im lặng bỏ task; Future có thể không nhận trạng thái completion từ việc thực thi và caller chờ mãi nếu không có timeout/cancel.

**Câu 9.** Pool fixed một worker, task A submit B vào cùng pool rồi `Future.get()`; vì sao có thể deadlock?

**Đáp án:** A giữ worker duy nhất nhưng chờ B; B ở queue và không thể chạy vì không có worker rảnh. Đây là thread-starvation deadlock.

**Câu 10.** Một task bị reject do shutdown nhưng queue còn chỗ; có trái hợp đồng không?

**Đáp án:** Không. Executor không nhận công việc mới sau shutdown; rejection không chỉ xảy ra do saturation.

## 23. Tài liệu chính thức và đọc sâu

- **ThreadPoolExecutor — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **ThreadPoolExecutor (mã nguồn OpenJDK 21):** https://github.com/openjdk/jdk21/blob/master/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java
- **ExecutorService — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Executors — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- **ArrayBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **SynchronousQueue — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- **RejectedExecutionHandler — Java SE 21:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html

**Kết luận cốt lõi:** `ThreadPoolExecutor` không đi thẳng từ core lên maximum khi có task mới. Đường thông thường là **ưu tiên tạo workers khi dưới core, ưu tiên queue khi đã đạt core, thử tạo extra workers khi queue không nhận được, và cuối cùng giao cho rejection handler**. Để hiểu chính xác, phải tính cả **queue type/capacity, shutdown races, worker lifecycle và policy xử lý overload**. Task được nhận, task đã bắt đầu và task đã hoàn tất là ba mốc khác nhau.
