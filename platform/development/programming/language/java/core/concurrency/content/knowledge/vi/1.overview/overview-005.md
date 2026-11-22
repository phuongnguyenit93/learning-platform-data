# Concurrency trong ứng dụng Java: use case và rủi ro

## 1. Vì sao ứng dụng Java cần concurrency?

**Concurrency (xử lý đồng thời)** là cách tổ chức nhiều công việc có thể cùng tiến triển trong một khoảng thời gian. Chúng có thể luân phiên trên một lõi CPU hoặc chạy thật sự cùng lúc trên nhiều lõi. **Parallelism (xử lý song song)** là trường hợp các công việc thực sự thực thi đồng thời; **asynchrony (bất đồng bộ)** là cách gọi công việc rồi nhận kết quả ở thời điểm khác, không bắt buộc tạo một luồng riêng hoặc chạy song song.

Ứng dụng thực tế thường xử lý nhiều yêu cầu, thao tác I/O và tác vụ nền. Nếu tất cả phải đợi nhau theo một chuỗi tuần tự, thời gian chờ mạng, đĩa hay cơ sở dữ liệu có thể khiến tài nguyên CPU bị nhàn rỗi. Concurrency cho phép công việc khác tiến triển trong lúc một công việc đang chờ; với bài toán tính toán có thể phân chia độc lập, parallelism còn giúp tận dụng nhiều lõi CPU.

Tuy nhiên, **thêm thread không tự động làm chương trình nhanh hơn**. Mức độ hữu ích phụ thuộc vào loại tác vụ, chi phí phối hợp, giới hạn tài nguyên và khả năng chịu tải của hệ thống phía sau.

### Thuật ngữ cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ Java |
| --- | --- | --- |
| Task | Đơn vị công việc có đầu vào/kết quả riêng | `Runnable`, `Callable<T>` |
| Thread | Luồng thực thi của JVM, có ngăn xếp và lịch chạy | `Thread` |
| Concurrency | Nhiều task có tiến triển đan xen | Executor chạy các request/task |
| Parallelism | Nhiều task thật sự chạy đồng thời trên các lõi | Xử lý nhiều phần dữ liệu độc lập |
| Asynchrony | Kết quả được xử lý sau khi công việc hoàn tất | `CompletableFuture`, callback |
| Thread safety | Tính đúng đắn khi đối tượng được dùng từ nhiều thread | Trạng thái bất biến, khóa, atomic |

Một công việc chờ I/O và một công việc tính toán là hai loại tải khác nhau. Không nên dùng chung một cấu hình concurrency cho mọi trường hợp.

## 2. Những use case phù hợp

### 2.1. Phục vụ nhiều yêu cầu độc lập

Ứng dụng mạng có thể nhận đồng thời nhiều kết nối, lời gọi hoặc thông điệp. Trong mô hình thread pool, các task xử lý độc lập được chuyển cho một số worker thread; worker hoàn tất công việc này rồi lấy công việc tiếp theo. Mục tiêu là **duy trì độ đáp ứng và thông lượng** khi nhiều người dùng cùng truy cập.

Điều kiện cần: dữ liệu chia sẻ phải an toàn, số task đang chờ phải được giới hạn, và tài nguyên phụ thuộc (kết nối mạng, database, API bên ngoài) phải chịu được tải tương ứng. Một hệ thống nhận 1.000 task không có nghĩa có thể đồng thời mở 1.000 kết nối tới mọi dịch vụ phụ thuộc.

### 2.2. Che thời gian chờ I/O

Đọc tệp, gọi HTTP, truy vấn dữ liệu hoặc đợi thông điệp thường mất thời gian vì I/O. Khi một task đang chờ, worker khác có thể phục vụ công việc khác. Ví dụ một trang tổng hợp thông tin độc lập từ dịch vụ A và B có thể thực hiện hai lời gọi cùng lúc rồi chờ cả hai.

Điều kiện quan trọng: hai lời gọi phải **độc lập về nghiệp vụ**. Nếu B cần kết quả A, khởi chạy B song song có thể sai thứ tự hoặc không mang lợi ích. Concurrency cũng không xóa giới hạn kết nối, rate limit, timeout hoặc dung lượng của dịch vụ đích.

### 2.3. Tách tác vụ nền khỏi đường xử lý chính

Ghi nhật ký có kiểm soát, tạo báo cáo, nén tệp, tạo thumbnail hoặc xử lý một hàng đợi là những ví dụ có thể đưa ra khỏi luồng xử lý tương tác. Mục tiêu là giảm thời gian người dùng phải đợi phần việc không cần hoàn thành ngay.

Cần quyết định rõ: tác vụ có được phép mất khi ứng dụng tắt không; có cần lưu bền vững, retry hay bảo đảm không xử lý hai lần không; khi báo lỗi thì ai theo dõi? Việc chỉ gọi `executor.submit(...)` không tạo ra cơ chế giao hàng bền vững. Đối với tác vụ quan trọng, phải thiết kế độ tin cậy ở mức hệ thống.

### 2.4. Pipeline và xử lý theo lô

Một pipeline có thể gồm nhận dữ liệu → xác thực → biến đổi → ghi kết quả. Các giai đoạn chạy đồng thời với một hàng đợi giới hạn, giúp cân bằng tốc độ giữa nguồn vào và đầu ra. Tác vụ phân tích nhiều tệp độc lập cũng có thể chia thành nhiều phần và gom kết quả.

Cần tránh trường hợp giai đoạn trước sinh dữ liệu nhanh hơn nhiều so với giai đoạn sau. Khi đó hàng đợi tăng, gây tốn RAM và độ trễ; giải pháp là **backpressure** hoặc chặn/từ chối bớt công việc, không phải tiếp tục thêm thread vô hạn.

### 2.5. Tính toán trên nhiều lõi CPU

Bài toán như phân tích tập dữ liệu lớn, mã hóa/biến đổi khối độc lập hoặc tính toán nhiều phần tử có thể chia task để dùng nhiều lõi. `ForkJoinPool`, `parallelStream()` hoặc executor thích hợp có thể hữu ích nếu mỗi task đủ lớn và không tranh chấp trạng thái.

Giới hạn tăng tốc: phần việc không thể song song hóa, chuyển đổi dữ liệu, cache/memory bandwidth, ghép kết quả, lock và context switch. Chia một phép tính rất nhỏ thành hàng nghìn task thường còn chậm hơn chạy tuần tự.

### 2.6. Lập lịch và xử lý sự kiện

`ScheduledExecutorService` phù hợp với công việc định kỳ hoặc trì hoãn trong tiến trình Java. Concurrency giúp xử lý nhiều sự kiện độc lập. Tuy nhiên lịch chạy trong JVM không thay thế lịch bền vững: tiến trình dừng thì lịch/tác vụ trong bộ nhớ cũng mất; tác vụ kéo dài có thể làm sai thời điểm chạy sau đó.

## 3. Khi nào nên chạy tuần tự?

Ưu tiên tuần tự nếu tác vụ nhỏ, phụ thuộc chặt chẽ theo thứ tự, cần một phép biến đổi đơn giản trên dữ liệu nhỏ, hoặc không có điểm chờ/khả năng tách việc đáng kể. Chạy tuần tự giúp giữ reasoning và xử lý lỗi đơn giản. Chỉ tăng concurrency sau khi có nhu cầu về **độ trễ, thông lượng hoặc độ đáp ứng** đo được.

Câu hỏi trước khi song song hóa:

1. Các task có thật sự độc lập và có kết quả hợp nhất rõ ràng không?
2. Tải chủ yếu là CPU hay chờ I/O? Có bao nhiêu tài nguyên hữu hạn phía sau?
3. Trạng thái nào được dùng chung, ai sở hữu, ai được ghi?
4. Có timeout, hủy, giới hạn hàng đợi và hành vi khi quá tải không?
5. Đã có phép đo so với phiên bản tuần tự trong cùng điều kiện chưa?

## 4. Các cơ chế Java thường dùng

| Công cụ | Vai trò | Lưu ý khi áp dụng |
| --- | --- | --- |
| `Thread` | Biểu diễn một luồng thực thi | Không tạo thread mới không giới hạn cho mỗi phần việc |
| `Runnable` / `Callable<V>` | Mô tả task; `Callable` trả kết quả hoặc ném exception | Ưu tiên tách task khỏi chính sách cấp phát thread |
| `ExecutorService` | Chạy và quản lý task qua executor | Phải đóng/shutdown có kiểm soát |
| `Future<V>` | Nhận kết quả, lỗi hoặc yêu cầu hủy | `get()` có thể chặn; cần timeout |
| `CompletableFuture` | Phối hợp kết quả bất đồng bộ | Các biến thể `Async` cần hiểu rõ executor sử dụng |
| `BlockingQueue` | Trao đổi dữ liệu giữa producer/consumer | Dùng capacity hữu hạn cho luồng dữ liệu cần backpressure |
| `synchronized` / `Lock` | Bảo vệ một bất biến chung | Giữ vùng khóa nhỏ, nhất quán thứ tự lấy khóa |
| `volatile` | Bảo đảm visibility và quan hệ thứ tự thích hợp cho một biến | Không biến `count++` thành atomic |
| `AtomicInteger` và họ atomic | Các thao tác atomic cho trạng thái đơn lẻ | Không tự bảo vệ bất biến liên quan nhiều biến |
| `ConcurrentHashMap` | Map hỗ trợ truy cập đồng thời | Chuỗi nhiều thao tác vẫn cần xem xét tính nguyên tử |
| `CountDownLatch` / `Semaphore` | Phối hợp hoàn tất / giới hạn số công việc vào vùng tài nguyên | Không dùng `Thread.sleep` để giả lập đồng bộ hóa |
| `ForkJoinPool` | Work-stealing cho task chia nhỏ, thường hướng CPU | Tránh chặn I/O kéo dài trong workload tính toán |
| Virtual threads (Java 21+) | Phục vụ nhiều task chờ I/O theo mô hình thread-per-task | Không làm CPU nhanh hơn; vẫn giới hạn tài nguyên ngoài JVM |

`ExecutorService`, `Future` và `CompletableFuture` đều dùng được ở Java 17. **Virtual threads là tính năng chính thức từ Java 21**; đoạn mã Java 17 bên dưới không phụ thuộc tính năng này.

## 5. Ví dụ 1 — nhiều task độc lập và gom kết quả an toàn (Java 17+)

Giả sử có ba tác vụ I/O độc lập; `Thread.sleep` chỉ **mô phỏng thời gian chờ** để ví dụ có thể chạy ở mọi máy, không phải cách thực hiện I/O thật.

Tạo tệp `ConcurrentWorkDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentWorkDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        AtomicInteger completed = new AtomicInteger();

        try {
            List<Callable<String>> jobs = List.of(
                () -> {
                    Thread.sleep(80);
                    completed.incrementAndGet();
                    return "A";
                },
                () -> {
                    Thread.sleep(40);
                    completed.incrementAndGet();
                    return "B";
                },
                () -> {
                    Thread.sleep(60);
                    completed.incrementAndGet();
                    return "C";
                }
            );

            List<Future<String>> results = pool.invokeAll(jobs);
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
            System.out.println("Completed: " + completed.get());
        } finally {
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
javac ConcurrentWorkDemo.java
java ConcurrentWorkDemo
~~~

Đầu ra:

~~~text
A
B
C
Completed: 3
~~~

Giải thích:

- `invokeAll` gửi ba task rồi chờ chúng hoàn tất; danh sách `Future` trả về **theo thứ tự task đầu vào**, không theo thứ tự task hoàn thành. Vì vậy luôn in A, B, C nếu các task hoàn tất bình thường.
- `AtomicInteger.incrementAndGet()` tăng đếm nguyên tử; ba task không làm thất lạc lần cập nhật.
- `result.get()` lấy kết quả hoặc phát sinh `ExecutionException` nếu task lỗi. `invokeAll` bản này chờ vô thời hạn nếu task không kết thúc; cần timeout ở trường hợp có rủi ro kẹt.
- `shutdown()` ngừng nhận task mới, cho task đang có hoàn tất; `awaitTermination` chờ có giới hạn. `shutdownNow()` là yêu cầu ngắt/thu hồi task, **không bảo đảm** task bị dừng nếu nó bỏ qua interrupt.

Ví dụ này minh họa concurrency và phối hợp kết quả, chưa chứng minh rằng ứng dụng thực sẽ nhanh hơn. Muốn kiểm chứng, đo latency, throughput và mức tài nguyên với phiên bản tuần tự trên tải tương đương.

## 6. Rủi ro đúng đắn: shared mutable state

### 6.1. Race condition và mất cập nhật

Khi nhiều thread cùng đọc/ghi trạng thái có thể thay đổi mà không đồng bộ, kết quả có thể phụ thuộc thứ tự xen kẽ. Ví dụ thao tác `count++` gồm đọc giá trị cũ, cộng 1, ghi giá trị mới; hai thread có thể cùng đọc một giá trị và một lần cộng bị mất.

~~~java
// MINH HỌA lỗi; không phải chương trình độc lập.
int count = 0;
// Hai thread cùng chạy:
count++; // Không atomic và không bảo đảm thread-safe
~~~

Giải pháp tùy ngữ cảnh: tránh chia sẻ dữ liệu; dùng đối tượng bất biến; giới hạn quyền sở hữu một thread; hoặc bảo vệ cập nhật bằng `synchronized`, `Lock`, các lớp atomic. Không chọn công cụ chỉ theo tốc độ; trước tiên xác định **bất biến** phải luôn đúng (chẳng hạn tổng số dư hai tài khoản không đổi).

### 6.2. Visibility và Java Memory Model

Đôi khi thread A đã ghi nhưng thread B chưa quan sát được như kỳ vọng do tối ưu hóa compiler/JIT, cache và thiếu quan hệ đồng bộ. **Java Memory Model (JMM)** quy định các quan hệ **happens-before** để xác định khi nào hành động của thread này được bảo đảm nhìn thấy ở thread khác.

Các ví dụ quan trọng: unlock của monitor happens-before lần lock tiếp theo trên cùng monitor; một lần ghi `volatile` happens-before lần đọc tiếp theo của cùng biến đó theo thứ tự đồng bộ; các cơ chế executor/`Future` cũng có bảo đảm nhất định về việc công bố kết quả. `Thread.start()` và `Thread.join()` có các bảo đảm thứ tự tương ứng.

~~~java
// MINH HỌA: một cờ dừng đơn giản, chỉ có một biến trạng thái.
private volatile boolean running = true;

// Thread khác gọi:
void stop() {
    running = false;
}

// Worker kiểm tra:
void work() {
    while (running) {
        // Thực hiện công việc ngắn, có thể kiểm tra cờ đều đặn.
    }
}
~~~

`volatile` phù hợp cho cờ trạng thái đơn giản khi không có bất biến nhiều bước; nó **không** bảo đảm cập nhật gộp kiểu `balance = balance - amount` hoặc `count++`. Vòng lặp trống cũng có thể tiêu CPU: hệ thống thật thường dùng cơ chế chờ có thể bị ngắt hoặc tín hiệu phối hợp.

### 6.3. Atomicity chưa đủ cho bất biến nhiều biến

`AtomicInteger` làm một lần tăng atomic nhưng không tự bảo đảm rằng hai biến liên quan luôn nhất quán. Ví dụ chuyển tiền phải bảo vệ đồng thời kiểm tra đủ số dư, trừ tài khoản nguồn và cộng tài khoản đích theo một giao thức nhất quán. Tương tự, thao tác `containsKey` rồi `put` trên concurrent map vẫn có thể bị thread khác xen vào; cân nhắc `putIfAbsent`, `compute` hoặc transaction/lock thích hợp.

### 6.4. Đăng tải đối tượng không an toàn

Đưa tham chiếu tới một đối tượng đang khởi tạo dở cho thread khác, hoặc công bố cấu trúc có thể thay đổi mà thiếu đồng bộ, khiến thread đọc thấy trạng thái chưa đầy đủ. Ưu tiên khởi tạo xong trước khi chia sẻ, trường `final` phù hợp, giá trị bất biến và cấu trúc concurrent; không để `this` thoát khỏi constructor qua callback/thread tự chạy.

## 7. Rủi ro tiến triển: deadlock, livelock, starvation

**Deadlock:** các thread đợi vòng tròn nhau (A giữ khóa 1 cần khóa 2; B giữ khóa 2 cần khóa 1), không thread nào tiến triển. Cách phòng tránh: quy định thứ tự lấy khóa thống nhất, tránh giữ lock khi chờ mạng/I/O, giữ critical section ngắn, sử dụng `tryLock` với timeout khi phù hợp. Timeout giúp phát hiện hoặc phục hồi một số tình huống nhưng không tự sửa thứ tự khóa sai.

**Livelock:** các thread không bị chặn cứng nhưng liên tục nhường/đổi trạng thái cho nhau nên không có công việc hữu ích hoàn tất. Điều chỉnh chiến lược retry với backoff/jitter, đặt giới hạn và xem xét phân phối quyền tiến hành.

**Starvation:** một task liên tục không được cấp CPU/lock/worker vì task khác chiếm tài nguyên. Ví dụ task dài hoặc blocking làm ngập một pool nhỏ; các task khác cứ nằm trong hàng đợi. Cần phân loại workload, giới hạn thời lượng, cân bằng ưu tiên và đo queue wait time.

**Thread-pool deadlock:** task A chiếm worker duy nhất, gửi B vào **cùng pool** rồi gọi `B.get()`; B không có worker để chạy nên A chờ mãi. Tránh chờ một task phụ thuộc trên chính executor đã cạn worker; cân nhắc composition không blocking hoặc thiết kế lại phân rã công việc.

## 8. Rủi ro tài nguyên và khả năng chịu tải

### 8.1. Quá nhiều thread hoặc task

Thread nền tảng tiêu tốn bộ nhớ ngăn xếp và chi phí lập lịch. Khi số thread vượt nhu cầu, context switch và cạnh tranh khóa làm giảm thông lượng. Ngược lại, pool quá nhỏ cho các task chờ I/O có thể khiến hàng đợi tăng dù CPU còn rảnh.

**Queue không giới hạn** là rủi ro riêng: số worker cố định nhưng số task chờ có thể tăng theo tốc độ đầu vào; độ trễ và bộ nhớ phình ra, cuối cùng có thể gây `OutOfMemoryError`. Trong nhiều overload scenario, trả lỗi nhanh có kiểm soát tốt hơn tích lũy việc vô hạn.

### 8.2. Bounded queue và chính sách quá tải

Một cấu hình minh họa (không phải chương trình độc lập):

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 2,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(8),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Cần thêm import từ `java.util.concurrent` khi đưa đoạn trên vào chương trình. Trong trường hợp này, tối đa hai task được thực thi và tối đa tám task nằm chờ trong queue tại cùng thời điểm; khi bão hòa và không thể nhận thêm, `execute` có thể ném `RejectedExecutionException`. Phải thiết kế cách xử lý lỗi, retry có giới hạn hoặc backpressure ở phía gọi. `CallerRunsPolicy` có thể làm thread gửi task trực tiếp chạy task, từ đó gây chậm phía gửi; dùng nó chỉ sau khi hiểu thread gửi đang phục vụ việc gì.

Số worker và queue capacity là **tham số vận hành**, không có một bộ số đúng cho mọi ứng dụng. Đo các chỉ số: worker active, pool size, queue depth, queue wait time, rejection, thời gian task, CPU, bộ nhớ và latency đầu cuối.

### 8.3. Phụ thuộc bên ngoài là nút thắt

Tăng số task gọi một API có rate limit, database connection pool nhỏ hoặc ổ đĩa chậm thường chỉ tăng hàng chờ/timeout. Dùng `Semaphore` hoặc cơ chế tương tự để đặt giới hạn tác vụ đồng thời theo **năng lực của downstream**, đồng thời áp dụng connection timeout, request timeout và retry có backoff phù hợp. Không retry vô hạn trong cùng thread pool khi downstream đã quá tải.

### 8.4. Blocking lẫn vào CPU pool

Pool thiết kế cho tính toán trên CPU có thể bị cạn worker nếu các task bên trong chờ I/O lâu. Khi đó cả task CPU nhỏ cũng bị kẹt hàng đợi. Tách nhóm công việc theo loại tải và đo lường, hoặc chọn kiểu thực thi thích hợp. Với `CompletableFuture.supplyAsync(...)` không truyền executor, mặc định thường dùng `ForkJoinPool.commonPool()`; cần cân nhắc executor riêng cho công việc blocking để tránh gây ảnh hưởng tới các phần code khác.

## 9. Timeout, cancellation, interruption và lỗi

### 9.1. Timeout không đồng nghĩa dừng task

`Future.get(timeout, unit)` chỉ giới hạn **thời gian thread gọi chờ kết quả**. Nếu timeout, tác vụ phía sau vẫn có thể đang chạy. `cancel(true)` yêu cầu interrupt task đang chạy (nếu có); khả năng dừng phụ thuộc vào việc task có kiểm tra/truyền interrupt và API đang dùng có đáp ứng interrupt không.

Một mẫu minh họa xử lý timeout (Java 17+):

~~~java
import java.util.concurrent.*;

public class TimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        Future<String> future = pool.submit(() -> {
            Thread.sleep(1000);
            return "done";
        });

        try {
            System.out.println(future.get(50, TimeUnit.MILLISECONDS));
        } catch (TimeoutException ex) {
            future.cancel(true);
            System.out.println("Timed out; cancellation requested");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac TimeoutDemo.java
java TimeoutDemo
~~~

Khi task vẫn đang chờ `Thread.sleep(1000)`, đầu ra thường là:

~~~text
Timed out; cancellation requested
~~~

Đây là kết quả điển hình, **không phải cam kết tuyệt đối của lịch chạy**: sau một khoảng trì hoãn lập lịch bất thường, task có thể đã hoàn tất trước lúc thread gọi thực thi `get`. Thời gian và hành vi hủy trong chương trình thật cần được kiểm chứng. `shutdownNow()` cũng chỉ cố gắng interrupt, không phải thao tác giết thread cưỡng bức.

### 9.2. Xử lý interrupt đúng cách

Khi một thao tác chặn ném `InterruptedException`, thread đang được yêu cầu dừng/chuyển trạng thái. Nếu không thể ném tiếp exception, thường nên khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` rồi kết thúc công việc an toàn. Không nuốt interrupt và tiếp tục vòng lặp vô hạn.

~~~java
// MINH HỌA bên trong một Runnable, không phải chương trình độc lập.
try {
    queue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

### 9.3. Lỗi trong task và phạm vi hủy

Với `submit`, exception trong task được giữ trong `Future` và thường được nhìn thấy qua `get()` dưới dạng `ExecutionException`; nếu bỏ qua `Future`, lỗi nghiệp vụ có thể không được xử lý như dự kiến. Với `CompletableFuture` cần quan sát nhánh exceptional và quyết định fallback hay lan truyền lỗi. Khi một nhánh của tập công việc thất bại, xác định các nhánh còn lại có nên bị hủy hay tiếp tục.

Không chỉ cấu hình timeout ở tầng gọi. Phải thống nhất **deadline toàn luồng xử lý** và ngân sách từng bước; ba lần chờ 5 giây nối tiếp có thể tạo độ trễ 15 giây. Retry phải hữu hạn, có điều kiện, và phù hợp với tính idempotent của tác vụ.

### 9.4. Dừng ứng dụng có kiểm soát

Khi ngừng nhận việc, nên chuyển executor sang `shutdown`, chờ các task hiện tại trong một giới hạn, rồi mới `shutdownNow` nếu cần. Cần biết tác vụ chưa hoàn tất có được lưu để chạy lại hay không. Không phụ thuộc vào việc dừng JVM sẽ tự hoàn thành hoặc lưu lại những task chỉ nằm trong bộ nhớ.

## 10. Thread safety, context và công việc phụ thuộc

Không phải mọi đối tượng Java đều an toàn khi được chia sẻ giữa các thread. Xem hợp đồng của API: nhiều kiểu như `String` là bất biến; các collection thông thường như `ArrayList` không bảo đảm thread-safe khi vừa đọc vừa sửa từ nhiều thread. Dùng cấu trúc concurrent hoặc giới hạn quyền truy cập phù hợp.

`ThreadLocal` gắn dữ liệu với **thread cụ thể**, không tự động truyền giá trị sang worker thread khác. Thread pool tái sử dụng worker, nên dữ liệu yêu cầu trước có thể vô tình còn lại nếu quên `remove()`. Với thông tin như correlation ID, user context hay locale, truyền tường minh qua tham số/context object hoặc dùng cơ chế propagation có hợp đồng rõ ràng; tuyệt đối không mặc định context của thread gọi sẽ tự đến task mới.

Tính đúng đắn còn phụ thuộc thứ tự nghiệp vụ: nếu tác vụ B cần tác vụ A hoàn thành thì phải biểu diễn dependency (chờ có giới hạn, ghép `CompletableFuture` hoặc pipeline tuần tự), không dựa vào thứ tự thread được lên lịch. Trong những thao tác có side effect (ghi file, gửi yêu cầu, cập nhật dữ liệu), retry/cancellation có thể tạo xử lý trùng; thiết kế idempotency và phạm vi giao dịch thích hợp.

## 11. Virtual threads trong Java 21+: nên dùng khi nào?

Virtual threads do JVM quản lý với chi phí tạo và đợi thấp hơn platform threads trong nhiều tác vụ blocking I/O. Chúng phù hợp khi muốn viết kiểu mã đồng bộ, dễ đọc, trong khi phải phục vụ số lượng lớn công việc thường xuyên **chờ I/O**.

Ví dụ ngắn dành riêng cho Java 21+ (mã minh họa API, không dành cho Java 17):

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> "result");
    System.out.println(future.get());
}
~~~

Nhập `java.util.concurrent.Executors` và `java.util.concurrent.Future` khi dùng đoạn mã trong một lớp hoàn chỉnh. Virtual threads không tăng số lõi, không làm một thuật toán CPU-bound nhanh hơn, và không tăng giới hạn số kết nối database/API. Đừng dùng pool số lượng nhỏ virtual threads như cơ chế chặn truy cập tài nguyên: dùng `Semaphore` hoặc giới hạn tài nguyên cụ thể. Cũng cần đo chi phí của blocking, pinning và mức độ tương thích của thư viện trên phiên bản JVM đang triển khai.

**Lưu ý phạm vi:** Các mẫu concurrency Java ở đây không phụ thuộc Spring; việc cấu hình executor/async trong Spring thuộc chương riêng.

## 12. Thiết kế, thử nghiệm và quan sát

### Thiết kế trước khi code

1. **Xác định mục tiêu đo được:** throughput, p95/p99 latency, số request đồng thời, hoặc thời gian hoàn thành batch.
2. **Phân loại task:** CPU-bound, I/O-bound, có blocking hay không, có thứ tự/phụ thuộc hay không.
3. **Liệt kê trạng thái chia sẻ:** đối tượng nào bất biến, đối tượng nào thuộc một thread, bất biến nào phải giữ bằng khóa/atomic/transaction.
4. **Đặt giới hạn:** worker concurrency, queue capacity, connection limits, deadline, retry budget và chính sách rejection.
5. **Xác định vòng đời:** task thành công, lỗi, timeout, interrupt, hủy, shutdown, restart và khả năng xử lý lại.
6. **Đo trên tải thực tế:** so sánh phiên bản tuần tự/đồng thời, theo dõi tài nguyên phía JVM và dịch vụ phụ thuộc.

### Các phép thử có giá trị

- Tạo nhiều task cập nhật cùng trạng thái và kiểm tra **bất biến** (không chỉ kiểm tra chương trình không ném exception).
- Dùng `CountDownLatch` hoặc barrier để chủ động cho các thread bắt đầu cùng lúc; lặp lại stress test với nhiều lịch xen kẽ.
- Mô phỏng dependency chậm, lỗi, timeout, queue đầy, task bị interrupt, shutdown giữa chừng; xác nhận fallback, số task còn lại và hành vi từ chối.
- Dùng phép đo đủ lâu với warm-up hợp lý của JVM; phân biệt latency, throughput và CPU, tránh suy kết luận hiệu năng chỉ từ một lần chạy.
- Với lỗi khó tái hiện, thu thập thread dump, Java Flight Recorder (JFR), log có correlation ID và các metric pool/queue/lock. Đọc thread state và lock owner để xác định chuỗi chờ.
- Tránh viết test dựa vào `Thread.sleep(100)` với giả định “đủ lâu thì thread khác chắc chắn xong”; scheduler không bảo đảm điều đó. Dùng primitive đồng bộ hoặc chờ có timeout.

### Dấu hiệu cần điều tra

| Hiện tượng | Giả thuyết cần kiểm tra | Hướng chẩn đoán |
| --- | --- | --- |
| Kết quả lúc đúng lúc sai | Race, công bố dữ liệu sai, bất biến không được bảo vệ | Stress test, rà soát shared mutable state/JMM |
| Request treo dù CPU thấp | Deadlock, phụ thuộc nội bộ pool, blocking downstream | Thread dump, call stack, lock/wait graph |
| Latency tăng dần theo tải | Queue không giới hạn, tài nguyên downstream bão hòa | Queue depth, wait time, connection-pool metrics |
| CPU cao nhưng throughput không tăng | Contention, context switch, retry loop/livelock | CPU profiling, JFR, retry counters |
| Task nền mất hoặc không báo lỗi | Future bị bỏ qua, shutdown đột ngột, job chỉ nằm trong RAM | Log lỗi, task lifecycle, thiết kế persistence |
| Dữ liệu request bị lẫn | ThreadLocal không dọn, trạng thái chia sẻ sai | Kiểm tra propagation và `remove()` |

## 13. Sai lầm phổ biến và checklist cuối

- **“Càng nhiều thread càng nhanh”** — sai khi overhead, lock contention và downstream limit chiếm ưu thế.
- **“Dùng volatile là thread-safe”** — sai với cập nhật gộp hoặc bất biến nhiều biến.
- **“Collection concurrent làm toàn bộ luồng nghiệp vụ atomic”** — sai nếu nghiệp vụ gồm nhiều thao tác độc lập.
- **“get(timeout) sẽ giết task”** — sai; chỉ giới hạn thời gian chờ của caller.
- **“Đã submit thì tự động có retry/durability”** — sai; in-memory executor không bảo đảm lưu bền.
- **“Executor tự quản lý vòng đời”** — sai; ứng dụng phải định nghĩa shutdown và quan sát lỗi.
- **“Virtual threads giải quyết mọi bài toán concurrency”** — sai; race, deadlock và giới hạn tài nguyên vẫn tồn tại.

Trước khi đưa concurrency vào production, hãy xác nhận: task độc lập ở mức nghiệp vụ; shared state có cơ chế bảo vệ rõ ràng; queue/worker/downstream được giới hạn; mọi lời gọi chờ có deadline; lỗi và interrupt được xử lý; shutdown có kế hoạch; chỉ số hiệu năng và dấu hiệu nghẽn có thể quan sát được.

**Kết luận học tập:** Concurrency là công cụ cải thiện độ đáp ứng và khả năng sử dụng tài nguyên khi nhiều công việc có thể tiến triển độc lập. Giá trị lớn nhất đến từ việc **chọn đúng use case, xác định đúng giới hạn, và bảo toàn tính đúng đắn dưới mọi thứ tự thực thi**.