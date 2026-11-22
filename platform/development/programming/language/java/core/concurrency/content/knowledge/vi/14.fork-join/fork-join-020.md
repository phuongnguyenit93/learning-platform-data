# ForkJoinPool asyncMode: chế độ FIFO cho tác vụ kiểu sự kiện không join

## 1. Mục tiêu và phạm vi

Sau bài học này, bạn có thể:

- Giải thích **ForkJoinPool.asyncMode**, sự khác biệt giữa **LIFO mặc định** và **FIFO ở deque cục bộ** của ForkJoin worker.
- Phân biệt tác vụ được **fork từ worker**, tác vụ được **submit từ thread bên ngoài**, cơ chế **work stealing**, và tác vụ dạng **event không join**.
- Khởi tạo ForkJoinPool Java 17+ với asyncMode=true bằng constructor bốn tham số; biết kiểm tra bằng getAsyncMode().
- Nhận ra **FIFO local không phải FIFO toàn cục**, không bảo đảm thứ tự bắt đầu hay hoàn thành trong một pool có nhiều worker.
- Chọn giữa mô hình chia để trị có join và event-style task không join; tổ chức completion, báo lỗi và shutdown nếu parent không chờ từng child.
- Đánh giá chi phí tạo task, số tác vụ đang chờ, blocking, memory visibility, cancellation và những giả định về ThreadLocal.
- Biên dịch/chạy các ví dụ Java 17+ với stdout kiểm chứng được, phân biệt một phép thử có kiểm soát với kết quả benchmark.

Phạm vi là **Java concurrency nói chung**, trong chủ đề cha **Fork/Join**. Những API và cấu hình riêng của Spring được học trong chương khác.

## 2. ForkJoinPool và deque của worker

**ForkJoinPool** là một ExecutorService có cơ chế xử lý ForkJoinTask và **work stealing**. Những tác vụ có thể được chia từ tác vụ cha, đặt vào nơi worker có thể xử lý, hoặc bị worker khác đánh cắp khi họ cần công việc.

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| ForkJoinPool | Pool quản lý worker và tác vụ |
| ForkJoinWorkerThread | Worker chạy task của pool |
| ForkJoinTask<V> | Task có completion/result |
| RecursiveTask<V> | Task trả về kết quả |
| RecursiveAction | Task không trả kết quả |
| fork() | Cho phép một task con được thực thi bất đồng bộ |
| join() | Chờ và nhận kết quả của một task |
| work stealing | Worker rảnh lấy công việc từ worker khác |
| asyncMode | Cấu hình cách ưu tiên lấy task cục bộ kiểu event không join |

Một **task không bằng một thread**. Bốn worker có thể thực thi hàng nghìn task thông qua tái sử dụng thread. Tuy nhiên, task cũng có chi phí object, queue, fork/join và scheduling; đổi asyncMode không loại bỏ chi phí này.

~~~text
                      ForkJoinPool
                     /      |      \
                Worker 1  Worker 2  Worker 3
                 deque     deque     deque
                   |         |         |
                 local     local     local
                   +------ steal ------+

Một worker fork child -> child có thể vào deque local.
Một thread ngoài submit -> đường external submission.
~~~

Đây là sơ đồ trực giác, không phải mô hình cấu trúc bộ nhớ cố định mà JDK cam kết cho mọi phiên bản. Cần tập trung vào hợp đồng **mode cục bộ**, khả năng **stealing** và **completion**.

## 3. LIFO mặc định và FIFO trong asyncMode

Giả sử một task cha đang chạy trên worker W và lần lượt fork A, B, C:

~~~text
Parent trên Worker W:
  fork(A);
  fork(B);
  fork(C);

Những task local đang chờ:
  A | B | C
~~~

Trong tình huống các child vẫn ở deque local, chưa bị steal hoặc được join trực tiếp:

- **asyncMode=false:** worker ưu tiên theo kiểu **LIFO**; child mới fork nhất thường được lấy trước, ví dụ **C, B, A**.
- **asyncMode=true:** worker ưu tiên **FIFO** đối với task được fork mà **không join**; child cũ được lấy trước, ví dụ **A, B, C**.
- **Worker khác:** có thể steal task và chạy song song, không phải tuân thủ cùng thứ tự completion của worker W.

LIFO hữu ích với dạng cây chia để trị, nơi parent thường fork một child, tự compute nhánh còn lại rồi join. FIFO có thể phù hợp với **event-style forked tasks that are never joined**, tức task được dispatch và được giám sát riêng thay vì kết hợp vào return value trực tiếp của parent.

### Không suy diễn FIFO toàn hệ thống

Có ít nhất ba thứ tự khác nhau: **thứ tự fork**, **thứ tự bắt đầu chạy** và **thứ tự hoàn thành**. asyncMode chỉ tác động chính sách ưu tiên lấy task local trong pool; nó không biến cả ba thứ tự thành một.

Ví dụ A được bắt đầu trước B nhưng A mất 200 ms, B chỉ mất 2 ms; trong pool có hai worker, B vẫn có thể hoàn thành trước A.

## 4. Khởi tạo ForkJoinPool trong Java 17+

Constructor có bốn tham số:

~~~java
// Mảnh mã minh họa trong một class/method có import.
ForkJoinPool fifo = new ForkJoinPool(
        4,
        ForkJoinPool.defaultForkJoinWorkerThreadFactory,
        null,
        true
);
~~~

Các tham số:

| Tham số | Diễn giải |
| --- | --- |
| parallelism=4 | Mức parallelism mục tiêu; không phải cam kết đúng bốn thread luôn chạy |
| factory | Factory tạo ForkJoinWorkerThread; ở đây dùng mặc định |
| handler=null | Không chỉ định uncaught exception handler riêng cho worker |
| asyncMode=true | Chọn chính sách FIFO local cho tác vụ kiểu event không join |

Tạo mode mặc định:

~~~java
ForkJoinPool normal = new ForkJoinPool(4);
~~~

**new ForkJoinPool(4)** dùng asyncMode=false. API **getAsyncMode()** trả về cấu hình boolean của pool, không phải bằng chứng mọi task đã chạy theo FIFO global.

Không có setter thông dụng để đổi asyncMode của một pool đã tạo; nếu cần so sánh, tạo hai pool riêng có vòng đời rõ ràng. **ForkJoinPool.commonPool()** là pool chia sẻ; không tự suy diễn có thể bật FIFO cho nó bằng một setter hay tự shutdown nó khi xong một request.

### Liên hệ với asyncMode của constructor

Tên asyncMode không có nghĩa mọi submit trở thành nonblocking, task chạy song song tự động, hoặc toàn bộ queue có tính FIFO. Tác dụng cần quan tâm là **local scheduling mode** với nhóm task **forked, unjoined**.

## 5. Ví dụ 1: thấy LIFO/FIFO có kiểm soát

Để loại bỏ work stealing khỏi thí nghiệm, tạo pool với **parallelism=1**. Một parent được thực thi bởi worker duy nhất, fork A, B, C rồi kết thúc **không join**. Worker duy nhất sau đó xử lý child theo mode cục bộ.

Tệp **ForkJoinAsyncModeOrderDemo.java**:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;

public class ForkJoinAsyncModeOrderDemo {
    static String run(boolean asyncMode)
            throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(
                1,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                asyncMode
        );
        CountDownLatch done = new CountDownLatch(3);
        ConcurrentLinkedQueue<String> events =
                new ConcurrentLinkedQueue<>();

        try {
            pool.execute(() -> {
                for (String value : new String[] {"A", "B", "C"}) {
                    ForkJoinTask.adapt(() -> {
                        events.add(value);
                        done.countDown();
                    }).fork();
                }
                // Parent không join các child.
            });

            done.await();
            return String.join("", events);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("default LIFO = " + run(false));
        System.out.println("async FIFO = " + run(true));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinAsyncModeOrderDemo.java
java ForkJoinAsyncModeOrderDemo
~~~

Stdout kỳ vọng trong điều kiện minh họa một worker:

~~~text
default LIFO = CBA
async FIFO = ABC
~~~

**Vì sao phép thử có ý nghĩa?**

1. Parent thực hiện cả ba lần fork trước khi kết thúc công việc của chính nó.
2. Không có worker thứ hai để steal và chạy child trước parent.
3. Lúc worker duy nhất chọn child, chúng đã cùng nằm trong deque local.
4. Default LIFO thường lấy C, B, A; mode FIFO lấy A, B, C.
5. CountDownLatch đợi đủ ba child, không dựa vào sleep hay một khoảng thời gian đoán trước.
6. ConcurrentLinkedQueue ghi kết quả an toàn; sau await main có thể ghép chuỗi.

**Không nâng kết quả một worker thành SLA:** trong pool nhiều worker, task có thể bị steal và chạy đồng thời; thứ tự hoàn thành không bảo đảm ABC ngay cả với asyncMode=true.

## 6. Fork và submit khác nhau

Khi task đang chạy **bên trong worker** gọi **ForkJoinTask.fork()**, task con gắn với cơ chế quản lý work của pool/worker, đặc biệt là deque local.

Khi **main/request thread gọi pool.submit()**, công việc đi vào đường **external submission**. Nó không thể mặc nhiên được xem là “A rồi B rồi C trong một deque local của thread main”. Các worker có thể nhận và chạy nhiều external tasks song song.

| Hành động | Nguồn | Có thể kết luận gì? |
| --- | --- | --- |
| Worker fork child | Worker của pool | Có thể tận dụng local queue và work stealing |
| Main submit Callable | Thread ngoài pool | Future để lấy kết quả; không có global FIFO completion |
| Parent join child | Task có dependency | Parent đợi/nhận kết quả child |
| Parent fork rồi quên child | Event không join | Phải có kênh completion/error riêng nếu quan trọng |

**FIFO cục bộ không phải FIFO của mọi lời gọi submit từ mọi producer.**

### Ví dụ 2: external submit, kết quả không phụ thuộc thứ tự chạy

Tệp **ForkJoinExternalSubmitDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class ForkJoinExternalSubmitDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                2,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        try {
            Future<Integer> a = pool.submit(() -> 20);
            Future<Integer> b = pool.submit(() -> 22);

            System.out.println("async = " + pool.getAsyncMode());
            System.out.println("sum = " + (a.get() + b.get()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinExternalSubmitDemo.java
java ForkJoinExternalSubmitDemo
~~~

Stdout:

~~~text
async = true
sum = 42
~~~

Hai Callable có thể bắt đầu theo các lịch khác nhau; ví dụ chỉ in **cấu hình pool** và **tổng kết quả** sau Future.get() nên stdout xác định. Caller gọi a.get() rồi b.get() không chứng minh B đã đợi A mới bắt đầu: cả hai đã được submit.

## 7. Không join vẫn phải biết lúc nào task hoàn tất

Pattern chia để trị cổ điển:

~~~text
parent -> fork(child) -> compute(other) -> join(child) -> combine
~~~

Pattern event-style:

~~~text
dispatcher -> fork(A), fork(B), fork(C) -> parent trở về
                                      |
                           children chạy/hoàn tất riêng
~~~

“Không join” có nghĩa **parent không trực tiếp đợi từng child**, không có nghĩa event đã hoàn tất khi fork() trả về. Nếu nghiệp vụ cần bảo đảm, phải có một giao thức:

- **CountDownLatch** khi biết N event và chỉ cần mốc hoàn tất.
- **Future** khi cần trả kết quả hoặc báo lỗi từng task.
- **Phaser** cho các nhóm task đăng ký động và các phase phức tạp hơn.
- **Queue/message completion** nếu cần chuyển kết quả đến consumer.
- **Ack, retry, idempotency hoặc persistent queue** nếu phải sống qua restart JVM.

**Đừng coi fire-and-forget là exactly-once execution.** Một task bị lỗi, JVM crash hoặc shutdown vẫn có thể làm mất side effect hay tạo trạng thái dở dang.

## 8. Ví dụ 3: unjoined events và kênh kết quả riêng

Parent fork ba event, trong đó event 2 cố tình thất bại. Parent không join, nhưng mỗi child xử lý lỗi và đếm completion trong finally. Bài học: FIFO không thay thế **completion/error reporting**.

Tệp **UnjoinedEventsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class UnjoinedEventsDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                2,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        CountDownLatch done = new CountDownLatch(3);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        try {
            pool.execute(() -> {
                for (int eventId = 1; eventId <= 3; eventId++) {
                    final int id = eventId;

                    ForkJoinTask.adapt(() -> {
                        try {
                            if (id == 2) {
                                throw new IllegalStateException("bad event");
                            }
                            success.incrementAndGet();
                        } catch (RuntimeException ex) {
                            failures.incrementAndGet();
                        } finally {
                            done.countDown();
                        }
                    }).fork();
                }
            });

            done.await();

            System.out.println("success = " + success.get());
            System.out.println("failure = " + failures.get());
            System.out.println("all observed = " + (done.getCount() == 0));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnjoinedEventsDemo.java
java UnjoinedEventsDemo
~~~

Stdout:

~~~text
success = 2
failure = 1
all observed = true
~~~

**Phân tích:**

1. Parent không giữ reference tới child và không join.
2. Mỗi child luôn gọi done.countDown() trong finally.
3. Child 2 bị exception có chủ đích, nhưng ghi nhận failures trong chính child.
4. AtomicInteger giúp thống kê chính xác khi nhiều worker chạy song song.
5. Main dùng done.await() để biết đủ ba task đã qua điểm completion.
6. Đầu ra chỉ phản ánh **tổng hợp**, không phụ thuộc thứ tự các event hoàn thành.

CountDownLatch chỉ báo **đủ số lần countDown**, không tự phân biệt thành công/lỗi. Nếu cần từng kết quả cụ thể, phải lưu result hoặc dùng Future/ack có trạng thái.

### Nếu child ném lỗi mà không catch?

ForkJoinTask lưu trạng thái exceptional completion theo hợp đồng. Parent đã bỏ reference và không join/get thì không tự nhận được exception, và không thể chắc hệ thống đã quan sát lỗi. **UncaughtExceptionHandler của worker không phải kênh báo lỗi duy nhất đáng tin** cho mọi lỗi từ ForkJoinTask.

Vì vậy event cần một error channel có kiểm soát, đặc biệt nếu có retry, cập nhật DB hoặc gọi dịch vụ ngoài.

## 9. asyncMode không vô hiệu hóa join

Một pool asyncMode=true vẫn có thể chạy **RecursiveTask** và dùng join bình thường. asyncMode không đổi phép tính hay mối phụ thuộc dữ liệu: **parent chỉ combine khi child đã hoàn tất**.

Mẫu chuẩn:

~~~java
// Mảnh minh họa trong compute() của RecursiveTask<Long>.
left.fork();
long rightResult = right.compute();
long leftResult = left.join();
return leftResult + rightResult;
~~~

Đoạn này giả định left/right là các RecursiveTask<Long> hợp lệ. **fork một nhánh, compute một nhánh, join** là idiom hữu ích để không enqueue mọi nhánh một cách không cần thiết.

**Không thiết kế thuật toán join dựa vào giả định deque sẽ luôn FIFO hoặc LIFO:** join có cơ chế hoàn tất dependency riêng và worker khác có thể steal.

### Ví dụ 4: kết quả join vẫn đúng ở cả hai mode

Tệp **ForkJoinJoinedSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinJoinedSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] values;
        private final int from;
        private final int to;

        SumTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= 16) {
                long result = 0;
                for (int i = from; i < to; i++) {
                    result += values[i];
                }
                return result;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long r = right.compute();
            return left.join() + r;
        }
    }

    static long run(boolean asyncMode, int[] values) {
        ForkJoinPool pool = new ForkJoinPool(
                3,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                asyncMode
        );
        try {
            return pool.invoke(new SumTask(values, 0, values.length));
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) {
        int[] values = new int[100];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }

        System.out.println("LIFO sum = " + run(false, values));
        System.out.println("FIFO sum = " + run(true, values));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinJoinedSumDemo.java
java ForkJoinJoinedSumDemo
~~~

Stdout:

~~~text
LIFO sum = 5050
FIFO sum = 5050
~~~

Tổng 1 đến 100 bằng 5050, bất kể hai pool chọn lịch chạy khác nhau. Ví dụ xác nhận **tính đúng đắn**, không chứng minh hai mode nhanh như nhau. Với thuật toán divide-and-conquer có join thường xuyên, hãy bắt đầu bằng mode mặc định rồi benchmark nếu cần.

## 10. Event ordering yêu cầu thiết kế riêng

Nếu bài toán đòi:

- Event A được commit trước B cho cùng account.
- Mọi biến mutable của một session chỉ được một owner sửa.
- Sau restart không được xử lý trùng event đã commit.
- Mọi consumer thấy một sequence tăng đúng thứ tự.

...thì **asyncMode=true không cung cấp các cam kết ấy**.

Các lựa chọn khác:

1. **Single-thread executor** để tuần tự hóa một luồng task trong một JVM.
2. **Partition-by-key**: mỗi key/partition có owner hoặc queue tuần tự, nhiều key khác nhau vẫn chạy song song.
3. **Sequence number và dependency**: task sau chỉ commit khi state của task trước đã được xác nhận.
4. **Persistent event queue** và idempotency key khi xử lý nhiều JVM/restart.
5. **BlockingQueue và consumer độc quyền** khi cần event-driven processing có ownership rõ.

Một single-thread executor có thể thực thi task theo thứ tự đưa vào queue, nhưng nếu nhiều producer submit đồng thời thì cần định nghĩa cách xác lập thứ tự nghiệp vụ. Nó cũng không tự đem lại durability qua restart.

## 11. Work stealing và sự khác biệt giữa start/completion

Trong pool nhiều worker, dù worker W chọn task A trước B theo FIFO local, worker X có thể steal B và chạy song song. Nếu B nhẹ hơn, B hoàn thành trước A.

~~~text
Worker W: bắt đầu A ---------[chạy lâu]----------> A done
Worker X: steal B --> B done
Thứ tự hoàn tất: B, rồi A.
~~~

Chính vì vậy:

- **Thứ tự fork** không đồng nghĩa **thứ tự bắt đầu**.
- **Thứ tự bắt đầu** không đồng nghĩa **thứ tự hoàn tất**.
- **Thứ tự hoàn tất** không đồng nghĩa **thứ tự commit side effect** nếu task còn làm I/O khác.
- **FIFO local** không đảm bảo latency hoặc fairness tuyệt đối.

Nếu muốn output theo thứ tự index trong khi xử lý song song, có thể lưu Future theo index, đợi tất cả rồi **thu kết quả theo index**. Nhưng việc thu theo thứ tự cũng không có nghĩa task đã chạy tuần tự.

## 12. ThreadLocal và thread affinity

Child task có thể chạy trên worker khác thread đã fork nó. Do đó:

- **ThreadLocal** gắn với thread thực thi, không gắn với task cha hay ForkJoinPool.
- Không kỳ vọng ThreadLocal của parent tự truyền tới child bị steal.
- Không dựa vào tên thread hoặc worker index làm thứ tự event.
- Task nên mang theo dữ liệu cần thiết, ưu tiên **immutable payload**.
- Nếu dùng ThreadLocal trong worker tái sử dụng, đặt/clear theo scope bằng try/finally khi thích hợp.
- Nếu task dùng shared mutable object, phải có atomic/lock/ownership thích hợp; asyncMode không tạo thread safety.

**Một child được fork không có quyền truy cập thread-confined state của parent** trừ khi thiết kế công bố/chuyển giao dữ liệu phù hợp.

## 13. Safe publication và Java Memory Model

Các task phải thấy đầu vào đã được chuẩn bị theo hợp đồng memory-consistency; việc giao task qua APIs đồng bộ của Executor/ForkJoin cung cấp các quan hệ cần thiết. Tuy nhiên nếu parent **tiếp tục sửa object mutable đồng thời với child**, việc fork không biến cập nhật tương lai thành atomic.

~~~text
Parent chuẩn bị payload
       |
       +-- fork/submit child
                |
                +-- child đọc payload đã công bố
                |
                +-- completion / join / Future.get / latch
                                      |
                                   reader dùng result
~~~

Trong ví dụ:

- **CountDownLatch.countDown()** trước **await() hoàn tất** tạo quan hệ happens-before theo contract.
- **AtomicInteger** cho phép nhiều worker ghi tổng số thành công/lỗi mà không mất lượt tăng.
- **ConcurrentLinkedQueue** cung cấp queue thread-safe.
- **join()/Future.get()** là các điểm completion có ngữ nghĩa đồng bộ hóa phù hợp để caller dùng kết quả.

Nếu từng child ghi vào vùng **không chồng lấn** của mảng rồi parent đọc sau khi đã join tất cả, có thể không cần khóa cho từng phần tử. Nếu hai child sửa **cùng phần tử**, phải có giao thức đồng bộ riêng.

## 14. Số lượng task, batching và backpressure

Một event dispatcher có thể fork hàng triệu task nhỏ:

~~~java
// Anti-pattern minh họa: không chạy vòng này.
for (;;) {
    ForkJoinTask.adapt(() -> processEvent()).fork();
}
~~~

Mảnh code giả định processEvent() được định nghĩa. Nếu sinh task nhanh hơn worker xử lý, lượng task outstanding và bộ nhớ có thể tăng rất lớn.

**FIFO không giảm số task hay allocation.** Cần:

- **Admission control** để giới hạn số event chưa được xử lý.
- **Batching** nếu mỗi event quá nhẹ: một task xử lý nhiều event.
- **Quota theo resource** (Semaphore, bounded queue, rate limit) nếu có dịch vụ ngoài giới hạn concurrency.
- **Error/cancel/timeout** rõ khi hệ thống quá tải.
- **Metric task age/queue backlog**, throughput, failure và tail latency.
- Chính sách xử lý khi task **không được nhận** hoặc bị hủy.

Một rủi ro đặc biệt: worker đang giữ hết tài nguyên rồi **blocking chờ permit** mà những task khác chỉ có thể release sau khi chạy, có thể tạo deadlock/starvation. Không dùng chờ vô thời hạn trong worker như một giải pháp backpressure ngây thơ.

## 15. Blocking I/O trong ForkJoinPool

ForkJoinPool có cơ chế hỗ trợ ForkJoinTask và work stealing, nhưng không có phép màu tự bù worker bị chặn vô hạn vì mọi loại I/O.

~~~java
// Mảnh minh họa: đọc mạng có thể block.
socket.read(buffer);
~~~

Nếu tác vụ thường xuyên block lâu:

- Có thể tách workload sang executor dành cho blocking I/O có giới hạn tài nguyên.
- Có thể cân nhắc **ForkJoinPool.managedBlock(ManagedBlocker)** khi có thể triển khai đúng giao thức và thực sự cần thông báo blocking cho pool.
- Không giả định asyncMode=true giải quyết vấn đề số worker không còn rảnh.
- Phải xem connection limits, deadline, cancellation, throughput và tác dụng tới commonPool.

**ManagedBlocker** có isReleasable() và block() theo hợp đồng; nó không đảm bảo mọi I/O đều hết chờ, không cung cấp transaction, và không tạo tài nguyên vô hạn.

## 16. Lifecycle, shutdown và cancellation

Với **pool riêng** do ứng dụng tạo:

| API | Diễn giải |
| --- | --- |
| shutdown() | Ngừng nhận task mới và tiến tới hoàn tất những task đã nhận |
| shutdownNow() | Cố dừng hoạt động, không đảm bảo cưỡng chế dừng task đang chạy |
| awaitTermination(timeout, unit) | Đợi pool terminated, trả boolean |
| isShutdown() | Quan sát đã yêu cầu shutdown chưa |
| isTerminated() | Quan sát pool đã chấm dứt chưa |
| ForkJoinTask.cancel(boolean) | Đánh dấu hủy task theo contract riêng của ForkJoinTask |

**ForkJoinTask.cancel(true)** không phải cam kết interrupt worker đang chạy. Với ForkJoinTask, boolean mayInterruptIfRunning không mang bảo đảm giống nhiều người suy từ tên tham số. Task dài cần cơ chế hủy hợp tác phù hợp.

Nếu parent fork child không join, phải xác định rõ lúc nào có thể shutdown. **Pool shutdown không phải một bản báo cáo thành công nghiệp vụ**. Với side effect quan trọng, cần ack/result riêng.

### Ví dụ 5: task đã được nhận trước shutdown vẫn có kết quả

Tệp **ForkJoinAsyncShutdownDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ForkJoinAsyncShutdownDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(
                1,
                ForkJoinPool.defaultForkJoinWorkerThreadFactory,
                null,
                true
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> a = pool.submit(() -> {
                started.countDown();
                release.await();
                return 20;
            });

            started.await();
            Future<Integer> b = pool.submit(() -> 22);

            pool.shutdown();
            release.countDown();

            int sum = a.get() + b.get();
            boolean terminated =
                    pool.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("sum = " + sum);
            System.out.println("terminated = " + terminated);
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinAsyncShutdownDemo.java
java ForkJoinAsyncShutdownDemo
~~~

Stdout nếu hai task hoàn tất trong điều kiện bình thường:

~~~text
sum = 42
terminated = true
~~~

Main đợi task a thực sự bắt đầu, submit b khi a đang đợi latch rồi shutdown. Hai task đã được nhận trước shutdown; main mở latch, lấy kết quả cả hai Future rồi đợi pool chấm dứt. Ví dụ không khẳng định external tasks đã bắt đầu theo thứ tự nào ngoài các điểm latch được xác định.

Nếu task bị block vô hạn hoặc JVM quá tải nặng, awaitTermination(5s) vẫn có thể trả false. Luôn kiểm tra boolean khi policy lifecycle yêu cầu.

## 17. So sánh ba lựa chọn

| Tiêu chí | ForkJoinPool mặc định | ForkJoinPool asyncMode=true | Single-thread executor |
| --- | --- | --- | --- |
| Local task scheduling | Thường **LIFO** | **FIFO** cho forked/unjoined task | Tuần tự qua một worker |
| Divide-and-conquer có join | Lựa chọn tự nhiên | Vẫn hợp lệ, không tự tốt hơn | Không tận dụng nhiều worker |
| Event-style không join | Có thể sử dụng | Mục tiêu phù hợp của asyncMode | Có thể phù hợp nếu cần tuần tự |
| Work stealing | Có | Có | Không theo mô hình ForkJoin |
| Global FIFO completion | Không | **Không** | Mỗi task chạy tuần tự; vẫn cần xác định order khi concurrent submit |
| Strict per-key owner | Cần thiết kế thêm | Cần thiết kế thêm | Có thể là nền tảng |
| Backpressure | Cần thiết kế | Cần thiết kế | Queue mặc định vẫn có thể lớn |
| Persistence qua restart | Không | Không | Không |

Một số event có thể độc lập tuyệt đối và được phép hoàn thành theo thứ tự bất kỳ: asyncMode đáng cân nhắc. Nếu một account phải được cập nhật theo chuỗi, **không** được thay lock/owner bằng FIFO local.

## 18. Debug và benchmark

### Điều cần đo

1. Throughput xử lý event hoặc task.
2. Latency từ lúc fork/submit tới lúc bắt đầu và tới lúc hoàn thành.
3. Tail latency p95/p99 và task tồn đọng lâu.
4. Mức parallelism thực, CPU utilization và blocking time.
5. Allocation rate, GC và số task đang chờ.
6. Steal count, queued-task estimate với giới hạn snapshot.
7. Tỷ lệ error, cancel, timeout và các ack còn pending.
8. Số event cần strict order nhưng thực tế bị lỗi ordering.

**getStealCount(), getQueuedTaskCount(), getActiveThreadCount()** là chỉ số chẩn đoán/ước lượng, không dùng chúng để chứng minh tất cả công việc đã hoàn tất hoặc làm kiểm tra điều kiện nghiệp vụ chính xác.

### Phương pháp so sánh

- Giữ cùng input, số worker, kích thước task và tốc độ producer.
- Đo riêng workload **forked events không join** và workload **recursive with join**; hai nhóm có thể hưởng lợi khác nhau.
- Warmup JVM/JIT, đo nhiều lượt; dùng JMH khi cần microbenchmark nghiêm túc.
- Không lấy một lần chạy nhanh hơn làm chứng cứ ưu thế tổng quát.
- Nếu có nhiều external submissions, phân tích đường submission riêng, không gán mọi thay đổi latency cho FIFO deque local.
- So với một mô hình serial owner hoặc queue thông thường khi đặc tả đòi ordering chặt.

**LIFO và FIFO đều có trade-off**, không có mode “tốt hơn mọi lúc”.

## 19. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng asyncMode=true = global FIFO | Có nhiều deque và work stealing | Chỉ suy luận local policy, thiết kế strict order riêng |
| Dùng FIFO để giữ mutable state chỉ một owner | Child có thể chạy trên nhiều worker | Owner/lock/partition thích hợp |
| Parent fork rồi return, coi mọi child đã xong | Fork không block đợi completion | Latch/Future/ack |
| Child lỗi nhưng không ai đọc kết quả | Không có error channel | Ghi nhận lỗi và trạng thái terminal |
| External submit từ main rồi kỳ vọng FIFO local | Không phải cùng worker-local fork | Tránh suy diễn ordering |
| Chỉ dựa vào ThreadLocal của parent | Child có thể bị steal | Chuyển context rõ ràng |
| Fork quá nhiều task cực nhỏ | Overhead/GC/queue lớn | Batch/cutoff/admission control |
| Chọn asyncMode để xử lý blocking I/O | FIFO không giải quyết worker bị block | Pool/mô hình blocking phù hợp |
| Không giới hạn event outstanding | Cạn memory hoặc latency cao | Quota/backpressure |
| Sử dụng commonPool và tự shutdown | Pool thuộc JVM chia sẻ | Sở hữu pool riêng nếu cần lifecycle |
| cancel(true) rồi coi task đã bị interrupt/dừng | ForkJoinTask có contract hủy riêng | Hủy hợp tác và xác nhận completion |
| Test 1 worker in ABC rồi áp dụng cho 4 worker | Stealing và concurrency thay đổi | Test invariants, không hứa global order |
| Xem getAsyncMode() là đo fairness | Chỉ là cấu hình boolean | Đo latency/queue age thực tế |
| Gọi Future.get() trong task cùng pool đang giữ tài nguyên child cần | Có thể tạo vòng chờ/starvation | Thiết kế dependency/lock ordering |

## 20. Checklist trước khi bật asyncMode

- [ ] Tác vụ có phải **event-style forked/unjoined** thật không?
- [ ] Parent có cần kết hợp kết quả child bằng join không?
- [ ] Có yêu cầu ordering tuyệt đối theo key hoặc commit sequence không?
- [ ] Có hiểu sự khác biệt giữa worker-local fork và external submit?
- [ ] Có tính đến nhiều worker, stealing và thời gian task khác nhau?
- [ ] Đã có kênh completion/error/ack khi không join?
- [ ] Đã giới hạn số tác vụ outstanding và chi phí mỗi task?
- [ ] Task có mutable state hoặc ThreadLocal không được công bố/chuyển giao đúng?
- [ ] Có đường shutdown/cancel và cleanup rõ ràng?
- [ ] Có test với parallelism=1 để minh họa mode, đồng thời test nhiều worker để chứng minh business invariants?
- [ ] Đã benchmark hai mode với workload thật và baseline phù hợp?
- [ ] Nếu cần durability qua JVM restart, có lưu việc và idempotency bên ngoài executor?

## 21. Tự kiểm tra

**1. asyncMode=false khác true thế nào?**  
False thiên về LIFO deque local; true thiên về FIFO cho những forked event tasks không join. Không mode nào cam kết global ordering.

**2. Tại sao ví dụ chỉ dùng một worker?**  
Để ba child chắc chắn còn trong deque local cho đến khi parent kết thúc, tránh worker khác steal/chạy song song.

**3. Khi có bốn worker, FIFO local có đảm bảo A hoàn tất trước B không?**  
Không. Các worker có thể thực thi song song và task có thời gian chạy khác nhau.

**4. Có thể dùng asyncMode=true cho RecursiveTask có join không?**  
Có. Nó không làm thuật toán đúng bị sai tự động, nhưng mode này không nhất thiết cải thiện performance của recursive join workloads.

**5. submit từ main có phải fork child vào deque local của worker main không?**  
Không. Main không phải ForkJoinWorkerThread của pool; external submit có đường điều phối riêng.

**6. Parent không join child thì biết child thành công bằng cách nào?**  
Cần Future/result, ack, latch kết hợp status, hoặc error channel. Fork chỉ đăng ký thực thi.

**7. FIFO local có thay một single-thread event loop đúng thứ tự không?**  
Không. Event loop/owner giải quyết một dạng ordering/ownership mà multiworker ForkJoinPool không tự cung cấp.

**8. Vì sao ThreadLocal có thể sai với forked events?**  
Task có thể bị worker khác steal; ThreadLocal gắn với thread, không với quan hệ parent-child.

**9. asyncMode có loại bỏ chi phí của hàng triệu task không?**  
Không. Cần batching, granularity và admission control.

**10. cancel(true) của ForkJoinTask có đảm bảo interrupt worker không?**  
Không. Hủy có hợp đồng riêng và không bảo đảm interrupt worker như suy đoán từ tên boolean.

**11. Khi nào FIFO local có thể được thử nghiệm?**  
Với nhiều task nhỏ độc lập được fork không join, khi muốn kiểm tra throughput/latency của chính sách worker-local.

**12. Nguyên tắc an toàn quan trọng nhất khi không join là gì?**  
Không bỏ quên completion, lỗi, backpressure và lifecycle của child; scheduling không thay thế correctness.

## 22. Kết luận

**ForkJoinPool asyncMode=true** chọn chính sách **FIFO cho deque cục bộ** của worker, phù hợp để cân nhắc đối với những tác vụ **event-style được fork mà không join trực tiếp**. Mặc định **asyncMode=false** thiên về **LIFO**, thường tự nhiên cho cây chia để trị cần join.

Tuy nhiên, FIFO cục bộ **không phải FIFO toàn cục**: còn có work stealing, nhiều worker, external submission, task durations và side effects. Cả hai mode đều phải được dùng với **giao thức completion/error rõ ràng, safe publication, kiểm soát số task, shutdown và hủy an toàn**.

Nếu cần xử lý event theo thứ tự nghiệp vụ chặt, hãy tạo **serial owner, queue theo key, dependency hoặc sequence protocol** thay vì dựa vào một boolean của scheduler. Nếu chỉ cần tối ưu event tasks độc lập, hãy thử mode phù hợp và **đo trên workload thật** trước khi kết luận.
