# Vòng đời commonPool và pool riêng: shutdown, close và awaitTermination

## 1. Tại sao vòng đời ForkJoinPool khác nhau giữa pool dùng chung và pool riêng?

`java.util.concurrent.ForkJoinPool` là một `ExecutorService` sử dụng work-stealing: các worker xử lý `ForkJoinTask`, có thể lấy thêm công việc từ queue của nhau và hỗ trợ các thuật toán chia để trị. Ngoài `fork()/join()`, ứng dụng còn có thể `execute()`, `submit()`, `invoke()` các tác vụ.

Có **hai loại đối tượng cần phân biệt**:

- `ForkJoinPool.commonPool()` là **pool dùng chung trong JVM**, có thể được nhiều thư viện và tác vụ khác nhau sử dụng. Code gọi phương thức chỉ *mượn* tài nguyên; không sở hữu vòng đời của nó.
- `new ForkJoinPool(parallelism)` tạo **pool riêng**. Thành phần tạo pool thường chịu trách nhiệm yêu cầu shutdown, chờ task kết thúc và giải phóng vòng đời đúng lúc.

Cùng là `ForkJoinPool`, nhưng `shutdown()`, `shutdownNow()`, `awaitTermination()`, `awaitQuiescence()` và `close()` có hệ quả **rất khác nhau** trên hai loại pool.

**Điểm trọng tâm:** `commonPool()` không bị shutdown bởi các lệnh shutdown thông thường; `close()` trên Java 21 cũng không đợi hay đóng common pool. Với **pool riêng**, `shutdown()` yêu cầu ngừng nhận việc, `awaitTermination()` chờ termination có hạn, còn `close()` trên JDK 21+ có thể đợi đến khi executor thực sự terminated.

Các ví dụ JDK cơ bản chạy với **Java 17+**; phần `close()` và try-with-resources cần **JDK 21+**. Nội dung là concurrency Java nói chung, không phụ thuộc framework.

## 2. Ba khái niệm: shutdown, terminated, quiescent

Trước khi chọn API, phải biết **đang chờ điều gì**:

| Trạng thái | Diễn giải | Tác động đối với task mới |
| --- | --- | --- |
| Running | Pool sẵn sàng nhận và thực thi việc | Có thể tiếp nhận task |
| Shutdown requested | Đã yêu cầu ngừng nhận việc; task đã nhận có thể vẫn chạy/chờ | Từ chối task mới |
| Terminated | Pool đã kết thúc vòng đời sau shutdown | Không chạy task mới |
| Quiescent | Pool **tạm rảnh**, không có task khả dụng cho worker hoặc đang được thực thi theo tiêu chí pool | Vẫn có thể nhận task mới nếu chưa shutdown |

**Quiescent khác terminated.** Pool có thể quiescent lúc 10:00 rồi nhận thêm task lúc 10:01. Một pool riêng đã terminated thì không thể được khởi động lại như instance cũ. Một Future cụ thể hoàn tất cũng không có nghĩa toàn pool terminated.

Vòng đời thường gặp của **pool riêng**:

```text
          RUNNING
             |
         shutdown()
             |
             v
   SHUTDOWN / DRAINING
   không nhận task mới
   task đã nhận được tiếp tục xử lý
             |
    không còn worker đang chạy
             |
             v
         TERMINATED
```

`shutdownNow()` có thể yêu cầu hủy sớm các task theo cơ chế best effort. Nhưng nó **không** tự đảm bảo mọi thread đang chạy bị dừng ngay.

## 3. Bảng API theo từng loại pool

| API | Pool riêng | `ForkJoinPool.commonPool()` |
| --- | --- | --- |
| `shutdown()` | Khởi động orderly shutdown | **Không thay đổi execution state** |
| `shutdownNow()` | Cố hủy/stop task, không chờ đến khi mọi task dừng | **Không thay đổi execution state** |
| `isShutdown()` | True sau yêu cầu shutdown | Không đổi thành true chỉ vì thử shutdown |
| `isTerminated()` | True khi đã thực sự kết thúc | Không trở thành true do shutdown thông thường |
| `awaitTermination(timeout, unit)` | True nếu terminated, false nếu hết thời gian | Có hiệu ứng chờ quiescence nhưng **luôn trả false** |
| `awaitQuiescence(timeout, unit)` | Đợi hoặc hỗ trợ thực hiện task đến khi tạm quiescent | Cách phù hợp nếu muốn quan sát common pool tạm rảnh |
| `close()`, JDK 21+ | Shutdown rồi **chờ terminated**, không đặt timeout | **No-op và không chờ** |
| `submit(task)` sau shutdown/close | Bị từ chối | Vẫn sử dụng được sau các lời gọi no-op |

Bảng này là **đặc thù của `ForkJoinPool`**, không được áp nguyên xi cho mọi implementation của `ExecutorService`. Ví dụ, `ThreadPoolExecutor.shutdownNow()` có thể trả danh sách các Runnable còn chờ; `ForkJoinPool.shutdownNow()` được tài liệu hóa là **luôn trả danh sách rỗng**.

## 4. Common pool: JVM quản lý, ứng dụng không đóng được bằng shutdown

`ForkJoinPool.commonPool()` trả về common pool được tạo chung. Nó thường hỗ trợ tác vụ Fork/Join không gắn với pool riêng và nhiều cách dùng bất đồng bộ từ thư viện JDK. Các thành phần khác có thể đang cùng dùng nó.

Javadoc nói rõ:

- `shutdown()` trên common pool không ảnh hưởng đến trạng thái thực thi.
- `shutdownNow()` trên common pool không ảnh hưởng đến trạng thái thực thi.
- `close()` trên common pool, kể từ API hỗ trợ close, không làm gì và không chờ.
- `awaitTermination(...)` với common pool có cách đợi liên quan `awaitQuiescence`, **nhưng trả `false` trong mọi trường hợp**, bởi common pool không terminated theo quy trình shutdown thường.

Đó không phải lỗi trả về: **`false` từ awaitTermination(commonPool) không xác nhận task đang chạy**, và không được dùng để cảnh báo rằng một task cụ thể chưa hoàn tất. Nếu cần chờ đúng task, giữ `Future` của task ấy.

### Ví dụ Java 17+: common pool vẫn nhận task sau shutdown

Tạo file `CommonPoolLifecycle.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CommonPoolLifecycle {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();

        Future<Integer> first = common.submit(() -> 40 + 2);
        System.out.println("First: " + first.get());

        common.shutdown();
        System.out.println("Shutdown: " + common.isShutdown());

        boolean terminated =
                common.awaitTermination(0, TimeUnit.MILLISECONDS);
        System.out.println("awaitTermination: " + terminated);

        Future<Integer> second = common.submit(() -> 7);
        System.out.println("Second: " + second.get());
    }
}
```

Chạy trên JDK 17+ với common pool cấu hình thông thường:

```bash
javac CommonPoolLifecycle.java
java CommonPoolLifecycle
```

Đầu ra:

```text
First: 42
Shutdown: false
awaitTermination: false
Second: 7
```

`get()` đợi kết quả từng task. Lệnh `shutdown()` không tắt common pool; `awaitTermination(0, ...)` không báo true; lời gọi `submit` sau đó vẫn chạy được. Nếu JVM bị cấu hình không có worker common pool có khả năng tiến triển, cần xem lại thiết lập môi trường; demo giả định cấu hình mặc định thông thường.

**Kinh nghiệm:** không dùng commonPool để tạo một ranh giới “bắt đầu → chạy một lô → đóng pool”. Common pool không thuộc riêng lời gọi của bạn.

## 5. Pool riêng: shutdown() không tự chờ

Tạo một pool riêng:

```java
ForkJoinPool pool = new ForkJoinPool(2);
// ... submit công việc ...
pool.shutdown();
```

Đây là snippet, chưa có class hoặc import. `shutdown()` chỉ yêu cầu ngừng nhận task mới và cho phép task đã nhận tiếp tục chạy. Nó **không** tự đợi đến lúc mọi worker kết thúc.

Các trạng thái có thể xảy ra ngay sau `shutdown()`:

- `isShutdown() == true`.
- `isTerminated() == false` nếu task vẫn đang chạy/chờ.
- Một `Future.get()` có thể chờ kết quả của riêng task đó.
- `awaitTermination(timeout, unit)` mới là API chờ **trạng thái kết thúc của pool**.

### Ví dụ Java 17+: quan sát trước và sau khi pool kết thúc

Tạo file `PrivatePoolLifecycle.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PrivatePoolLifecycle {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> answer = pool.submit(() -> {
                started.countDown();
                release.await();
                return 42;
            });

            started.await();
            pool.shutdown();

            System.out.println("Shutdown: " + pool.isShutdown());
            System.out.println("Terminated before release: "
                    + pool.awaitTermination(0, TimeUnit.MILLISECONDS));

            release.countDown();
            System.out.println("Answer: " + answer.get());

            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool still running");
            }
            System.out.println("Terminated: " + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PrivatePoolLifecycle.java
java PrivatePoolLifecycle
```

Đầu ra khi worker hoàn thành bình thường, không bị interrupt:

```text
Shutdown: true
Terminated before release: false
Answer: 42
Terminated: true
```

Giải thích:

1. Worker đã chạy nhưng chờ `release.await()`, main xác nhận qua `started.await()`.
2. Main gọi `shutdown()`; pool chuyển sang trạng thái ngừng nhận task mới, nhưng worker vẫn chờ nên chưa terminated.
3. `awaitTermination(0, MILLISECONDS)` không thể trả true khi worker vẫn mắc ở cổng.
4. Main mở cổng, `Future.get()` nhận giá trị 42.
5. `awaitTermination(30, SECONDS)` đợi pool kết thúc; ví dụ chủ động ném lỗi nếu vượt thời gian, không ghi nhận sai trạng thái.
6. `finally` luôn mở cổng để không giữ worker chờ do một exception tại thread main.

**Không lấy `answer.get()` của một task làm bằng chứng toàn pool đã dừng** nếu còn nhiều task khác; đó là mục đích của `awaitTermination`. Thời gian 30 giây trong ví dụ là timeout kiểm tra, không phải bảo đảm cứng của scheduler hay hệ điều hành.

## 6. awaitTermination(): dùng đúng cho pool riêng đã yêu cầu shutdown

Dạng API:

```java
boolean terminated = pool.awaitTermination(5, TimeUnit.SECONDS);
```

Đây là snippet giả sử `pool` đã khai báo và phương thức bao quanh xử lý `InterruptedException`.

Với pool riêng:

- `true`: executor terminated trong quá trình chờ.
- `false`: hết thời gian cho phép nhưng không xác nhận được termination.
- `InterruptedException`: thread **đang gọi awaitTermination** bị interrupt; không được đánh đồng với task bị lỗi.
- Gọi `awaitTermination` **không khởi động shutdown**. Nếu pool vẫn running và không có nơi khác shutdown, nó có thể đợi tới timeout.
- Timeout chỉ giới hạn **việc chờ** của caller, không tự hủy task đang chạy.

Mẫu shutdown có hai giai đoạn:

```java
// Snippet: caller sở hữu pool riêng.
pool.shutdown();
try {
    if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            System.err.println("Pool still active");
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**Hai lần 2 giây là hai ngân sách riêng**; toàn quy trình có thể chờ gần 4 giây cộng chi phí xử lý. Nếu yêu cầu **một deadline chung**, đo thời gian đã qua bằng `System.nanoTime()` và truyền remaining time vào mỗi lần await.

### shutdownNow() trong ForkJoinPool có điểm khác

`ForkJoinPool.shutdownNow()` cố dừng task đang thực thi/hủy task chưa thực thi, nhưng **luôn trả List rỗng** theo hợp đồng. Do đó không dùng `shutdownNow().size()` để thống kê số task bị loại bỏ. Không có bảo đảm task đang block trong I/O không hỗ trợ interrupt sẽ dừng ngay.

`shutdownNow()` trả về cũng **không có nghĩa `isTerminated()` đã true**. Nếu cần chắc chắn, tiếp tục chờ `awaitTermination` với chính sách thời hạn cụ thể, và có cách cảnh báo nếu task không hợp tác cancellation.

Đừng gọi `shutdownNow` với **common pool** để “xả hàng đợi”; nó không tác động đến execution state của shared pool.

## 7. awaitQuiescence(): đợi tạm rảnh, không đóng pool

`ForkJoinPool.awaitQuiescence(timeout, unit)` đợi hoặc **hỗ trợ thực thi công việc** đến khi pool tạm quiescent, hoặc hết thời gian.

- `true`: xác nhận trạng thái quiescent theo hợp đồng tại một thời điểm.
- `false`: không đạt điều kiện quiescent trước giới hạn chờ.
- Không gọi shutdown, không thay thế trạng thái terminated.
- Khi được gọi từ một `ForkJoinTask` trong cùng pool, tác dụng tương đương `ForkJoinTask.helpQuiesce()`.
- Khi được gọi từ thread bên ngoài, caller có thể tham gia hỗ trợ thực thi task, không đơn thuần đứng chờ.
- Không khai báo `InterruptedException` giống `awaitTermination`.

**Quiescence chỉ là trạng thái tạm thời:** pool có thể nhận task mới ngay sau khi trở về true, nếu chưa shutdown.

### Java 17+: quiescent nhưng vẫn nhận task mới

Tạo file `QuiescenceDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;

public class QuiescenceDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);

        try {
            System.out.println("First: "
                    + pool.submit(() -> 1).get());

            boolean idle = pool.awaitQuiescence(5, TimeUnit.SECONDS);
            if (!idle) {
                throw new IllegalStateException("Pool did not become idle");
            }

            System.out.println("Quiescent: " + idle);
            System.out.println("Shutdown: " + pool.isShutdown());
            System.out.println("Second: "
                    + pool.submit(() -> 2).get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac QuiescenceDemo.java
java QuiescenceDemo
```

Đầu ra trong điều kiện pool hoàn tất bình thường:

```text
First: 1
Quiescent: true
Shutdown: false
Second: 2
```

Pool chỉ có hai task được gửi lần lượt; sau khi task đầu tiên xong, `awaitQuiescence` có thể quan sát rảnh. `isShutdown` vẫn false nên task thứ hai được nhận.

### Với commonPool: awaitQuiescence có nghĩa gì?

Do không thể shutdown common pool bằng API thông thường, `awaitQuiescence` có thể hữu ích khi muốn **đợi toàn common pool tạm rảnh**, ví dụ một ứng dụng muốn cho xử lý bất đồng bộ có cơ hội hoàn tất trước khi JVM thoát.

Nhưng common pool dùng chung: các thành phần khác vẫn có thể gửi thêm công việc, nên một lần quiescent **không xác nhận rằng nhóm task riêng của bạn có kết quả đúng**. Để đợi một nhóm task chính xác, giữ danh sách `Future` hoặc `ForkJoinTask` của nhóm đó và chờ từng đối tượng.

**Điều dễ mắc lỗi:** `commonPool().awaitTermination(1, SECONDS)` có thể đợi với hiệu ứng như `awaitQuiescence` nhưng **luôn trả false**. Đừng viết `if (!common.awaitTermination(...))` rồi kết luận chắc chắn còn task đang chạy. Hãy dùng đúng API theo câu hỏi muốn trả lời.

## 8. close() và try-with-resources kể từ JDK 19, thường dùng với Java 21+

Từ **Java 19**, `ExecutorService` kế thừa `AutoCloseable` và có `close()`. JDK 21 (LTS) hỗ trợ rõ cách viết pool trong try-with-resources; JDK 17 **chưa có** hợp đồng đó cho `ForkJoinPool`.

### Pool riêng: close() chờ termination

Với **pool riêng**, `close()`:

1. Yêu cầu orderly shutdown.
2. **Chờ đến khi executor terminated**, không có tham số timeout.
3. Nếu thread gọi bị interrupt khi đang đợi, chuyển sang nỗ lực stop như `shutdownNow()`.
4. Tiếp tục chờ các task đang thực thi dừng, sau đó **khôi phục interrupt status** cho caller trước khi trở về.

**Đừng hiểu close là “gọi shutdown rồi quay lại ngay”**. Nếu task chờ một tài nguyên không bao giờ sẵn sàng hoặc bỏ qua interrupt, close có thể chờ vô hạn. Try-with-resources bảo đảm lời gọi close diễn ra, chứ không bảo đảm giới hạn thời gian đóng.

### Java 21+: ví dụ đóng pool riêng theo scope

Tạo file `PrivateClose21.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class PrivateClose21 {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger count = new AtomicInteger();

        try (ForkJoinPool pool = new ForkJoinPool(1)) {
            pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    count.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("Inside try: " + count.get());
            release.countDown();
        }

        System.out.println("After close: " + count.get());
    }
}
```

Biên dịch/chạy bằng **JDK 21+**:

```bash
javac PrivateClose21.java
java PrivateClose21
```

Đầu ra:

```text
Inside try: 0
After close: 1
```

Cổng `started` xác nhận task đã bắt đầu, nhưng `release` vẫn đóng nên count là 0 khi in trong try. Main mở cổng trước khi rời scope. Khi thoát try, Java gọi `pool.close()` và chờ worker kết thúc; sau close giá trị là 1.

**Nguy cơ vòng chờ:** không đặt `release.countDown()` ở **sau khối try** nếu task đang đợi release. Khi ấy close chờ task, task chờ release, dòng phát tín hiệu không bao giờ chạy. Tương tự, không gọi close khi đang giữ lock mà task cần để kết thúc.

### Common pool: close() không chờ và không đóng

Với `ForkJoinPool.commonPool()`, JDK 21 ghi rõ `close()` **không tác động đến thực thi và không đợi**. Vì vậy:

```java
// Snippet JDK21+, KHÔNG phải barrier đợi task.
try (ForkJoinPool common = ForkJoinPool.commonPool()) {
    common.execute(() -> doWork());
}
// close() ở đây không đảm bảo doWork() đã xong.
```

`doWork()` chưa khai báo, nên đây chỉ là snippet. Không dùng try-with-resources đối với common pool để ngụ ý mình sở hữu/làm chủ vòng đời của nó.

### Java 21+: common pool vẫn dùng được sau close()

Tạo file `CommonClose21.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class CommonClose21 {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();
        common.close();

        System.out.println("Shutdown: " + common.isShutdown());
        Future<String> result = common.submit(() -> "still available");
        System.out.println("Result: " + result.get());
    }
}
```

Biên dịch/chạy bằng JDK 21+:

```bash
javac CommonClose21.java
java CommonClose21
```

Đầu ra trong cấu hình common pool thông thường:

```text
Shutdown: false
Result: still available
```

Ví dụ chứng minh close không đóng common pool. Trong ứng dụng thật, **không cần gọi close trên common pool**; thay vào đó, theo dõi kết quả công việc bằng Future của mình.

## 9. Common pool có daemon worker: task chưa xong có thể bị bỏ lại khi JVM thoát

Các worker của `ForkJoinPool` thông thường được khởi tạo dạng **daemon thread**. Khi không còn non-daemon thread, JVM có thể thoát mà **không chờ** daemon worker hoàn tất.

Vì vậy:

- Đừng submit công việc quan trọng vào common pool rồi để main trả về mà không có đồng bộ chờ.
- Nếu cần kết quả một task, dùng `Future.get()` hoặc `ForkJoinTask.join()`.
- Nếu cần kết quả một batch, dùng một danh sách Future, latch hoặc điều phối có hợp đồng rõ ràng.
- `awaitQuiescence` chỉ thông báo pool **tạm rảnh** tại một thời điểm, không ngăn thành phần khác submit thêm việc.
- Nếu cần isolation khỏi workload khác, dùng pool riêng và quản lý lifecycle của nó.

Với `CompletableFuture.supplyAsync(...)` không truyền executor, môi trường thông thường thường sử dụng common pool; tuy nhiên có trường hợp triển khai/cấu hình dùng chiến lược khác khi parallelism quá thấp. Không thiết kế dựa vào một số lượng thread hay tên worker cố định: cần dựa vào hợp đồng Future và executor đã chọn.

## 10. Chọn đúng API cho từng nhu cầu

| Nhu cầu | API nên ưu tiên | Lý do |
| --- | --- | --- |
| Đợi đúng một task | `Future.get()` hoặc `ForkJoinTask.join()` | Không ảnh hưởng task khác |
| Đợi một nhóm task của chính mình | Danh sách Future / `invokeAll` | Phạm vi batch xác định |
| Chờ pool riêng đã shutdown kết thúc | `shutdown()` + `awaitTermination(timeout, unit)` | Có deadline, có boolean |
| Đóng pool riêng do một scope sở hữu trên JDK 21+ | `close()` / try-with-resources | Shutdown + chờ termination |
| Đợi pool tạm rảnh mà vẫn tái sử dụng | `awaitQuiescence(timeout, unit)` | Không shutdown |
| Đợi common pool tạm rảnh | `commonPool().awaitQuiescence(...)` | Common không terminated theo shutdown thường |
| Muốn ngắt task trong pool riêng khi timeout | `shutdownNow()` sau graceful deadline | Best effort, tiếp tục theo dõi termination |
| Cần pool để có quyền shutdown độc lập | `new ForkJoinPool(...)` | Ownership riêng, không dùng common |

**Hạn chế:** `close()` không cung cấp timeout. Một yêu cầu “shutdown toàn hệ thống trong 5 giây” cần kế hoạch chờ có hạn, yêu cầu stop khi hết hạn và cách xử lý task không dừng; đóng scope bằng close có thể không đáp ứng SLA.

## 11. Timeout, interrupt và lỗi khi shutdown

### awaitTermination bị interrupt

`awaitTermination` khai báo `throws InterruptedException`. Nếu caller bị interrupt, nên truyền tiếp hoặc khôi phục cờ sau khi đã xử lý cleanup cần thiết. Một pattern trên pool riêng:

```java
// Snippet cho pool riêng, không dành cho common pool.
pool.shutdown();
try {
    if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

**Điều chưa được làm trong snippet:** nó không chờ thêm sau `shutdownNow()`. Production có thể cần `awaitTermination` lần hai với ngân sách riêng hoặc thời gian còn lại, ghi nhận task nào không phản hồi. Không được báo đã terminated chỉ vì `shutdownNow()` vừa trả về.

### close không ném InterruptedException

`ForkJoinPool.close()` trên JDK 21 không khai báo `InterruptedException`. Nếu caller bị interrupt khi đang đợi đóng **pool riêng**, close chuyển sang yêu cầu stop kiểu shutdownNow, tiếp tục chờ task đang chạy kết thúc rồi khôi phục interrupt status.

**Không bắt một InterruptedException chỉ quanh `close()`** khi không có lời gọi khác ném checked exception tương ứng; mã đó có thể không biên dịch vì catch không thể đạt tới.

### Task không hợp tác interruption

Một task CPU lặp vô hạn mà không kiểm tra cờ, một I/O call không có đường hủy hoặc một vòng lock deadlock có thể khiến pool không dừng dù đã shutdownNow. `close()` cũng có thể treo vì **không có timeout**.

Để xử lý, thiết kế task với điểm dừng an toàn, timeout I/O phù hợp, giải phóng tài nguyên trong `finally` và tránh chạy công việc blocking dài trong ForkJoin worker khi không cần thiết. Khi buộc phải chờ bên ngoài trong một ForkJoin algorithm, có thể cân nhắc `ForkJoinPool.ManagedBlocker` để pool biết việc chặn và cố bù worker; nó cũng không đảm bảo hết deadlock.

## 12. Khi nào không nên dùng common pool?

Common pool thuận tiện cho công việc ngắn, độc lập, không cần vòng đời riêng. Nhưng cần cân nhắc pool riêng nếu:

1. Có nhiều tác vụ **blocking I/O** hoặc task dài gây tranh tài nguyên với các thành phần khác.
2. Cần **isolation**, cấu hình parallelism, thread factory, hoặc giám sát workload cụ thể.
3. Muốn **shutdown và awaitTermination** thực sự chỉ với task thuộc thành phần mình.
4. Cần chính sách backpressure, admission hoặc timeout riêng.
5. Có SLA giới hạn thời gian dừng hoặc task cần vòng đời rõ ràng.

**Không nhất thiết mọi công việc phải dùng ForkJoinPool riêng**: nếu workload chủ yếu I/O blocking, một executor phù hợp với loại công việc có thể đơn giản hơn; trên JDK 21+ có thể cân nhắc virtual threads khi đúng trường hợp. Việc tạo pool riêng cũng tiêu thụ tài nguyên và cần shutdown, nên phải quản lý ownership nhất quán.

## 13. Debug pool “không chịu dừng”

Nếu pool riêng đã shutdown nhưng `isTerminated()` vẫn false sau timeout:

- Dùng thread dump/JFR để xem worker đang đợi lock, I/O, latch hay task khác.
- Xác định worker có **chờ task nằm trong chính pool nhỏ đó** không; đây có thể là thread starvation deadlock.
- Kiểm tra các lock do caller đang giữ trong lúc chờ termination.
- Xem task có xử lý `InterruptedException` và `isInterrupted()` hợp lý không.
- Xác định pool thực sự là **pool riêng** hay nhầm common pool.
- Đừng dùng `getQueuedTaskCount()` hoặc `getActiveThreadCount()` như một barrier đồng bộ; chúng là metric trạng thái/ước lượng thay đổi nhanh.
- Kiểm tra các task đã nộp có lỗi/cancellation; `isTerminated` chỉ nói vòng đời executor, không có nghĩa mọi nghiệp vụ thành công.
- Kiểm tra các resource mà worker sử dụng còn tồn tại cho đến khi worker đã dừng.

### Đừng giữ lock trong khi chờ pool

Ví dụ nguy hiểm:

```java
// Snippet ý tưởng: caller giữ lock X.
synchronized (resourceLock) {
    pool.shutdown();
    pool.awaitTermination(10, TimeUnit.SECONDS);
}
// Nếu worker cần resourceLock để hoàn tất, caller và worker đợi nhau.
```

Không phải file độc lập: `resourceLock` và `pool` chưa khai báo, ngoại lệ chưa xử lý. Đây là vòng chờ có thể phát sinh dù từng API riêng lẻ đều thread-safe. Phải cho worker khả năng giải phóng công việc trước khi caller bước vào wait.

## 14. Các hiểu nhầm phổ biến

1. **“`shutdown()` trên commonPool dừng công việc của mọi người.”** Sai: no-op với execution state.
2. **“`close()` của commonPool chờ mọi task.”** Sai: trên JDK 21 không chờ, không đóng.
3. **“`awaitTermination(commonPool)` trả false nghĩa chưa có task nào xong.”** Sai: luôn false theo hợp đồng, kể cả khi quiescent.
4. **“`awaitQuiescence` làm pool terminated.”** Sai: chỉ chờ tạm rảnh, không shutdown.
5. **“`shutdown()` trên pool riêng đã đợi mọi worker kết thúc.”** Sai: shutdown không phải awaitTermination.
6. **“`shutdownNow()` bảo đảm giết worker ngay.”** Sai: best effort.
7. **“`ForkJoinPool.shutdownNow()` trả danh sách task chờ.”** Sai: ForkJoinPool luôn trả List rỗng.
8. **“`isShutdown == true` nghĩa `isTerminated == true`.”** Sai: còn giai đoạn drain.
9. **“`Future.get()` của một task nghĩa toàn pool terminated.”** Sai: chỉ đợi task đó.
10. **“Common pool daemon worker sẽ giữ JVM chờ đến khi xong.”** Sai: daemon không giữ JVM sống.
11. **“Java 17 hỗ trợ try-with-resources cho ForkJoinPool.”** Sai: `AutoCloseable`/close qua ExecutorService có từ Java 19.
12. **“Close pool riêng có timeout mặc định.”** Sai: có thể chờ rất lâu nếu task không dừng.
13. **“Caller interrupt thì close ném `InterruptedException` ngay.”** Sai: close yêu cầu dừng, tiếp tục chờ và khôi phục cờ.
14. **“Quiescent true bảo đảm không còn task mới.”** Sai: nếu chưa shutdown thì vẫn có thể submit.
15. **“awaitTermination tự động yêu cầu shutdown.”** Sai: chỉ chờ, không khởi động shutdown.
16. **“Có pool riêng là đã xử lý data race.”** Sai: hai task cùng sửa shared mutable state vẫn cần đồng bộ.
17. **“Mỗi task nộp vào commonPool đều có một worker độc lập.”** Sai: pool điều phối task trên tập worker chia sẻ.
18. **“Chỉ cần tăng parallelism là chữa deadlock.”** Sai: vòng chờ khóa và phụ thuộc nghiệp vụ phải sửa ở thiết kế.

## 15. Checklist lựa chọn vòng đời

1. Xác định **pool là common hay riêng** trước khi gọi bất kỳ API shutdown nào.
2. Phân biệt nhu cầu **đợi một Future, batch, quiescence hay termination**.
3. Nếu sở hữu pool riêng, đặt shutdown trong lifecycle hoặc `finally` rõ ràng.
4. Khi cần deadline, dùng `awaitTermination(timeout)` và quyết định bước tiếp theo nếu false.
5. Không suy rằng `shutdownNow()` trả về nghĩa task đã dừng.
6. Trên JDK 21+, dùng `close()/try-with-resources` **chỉ với pool do scope sở hữu**, khi có thể chờ tới terminated.
7. Không dùng close/shutdown common pool làm barrier hoặc cleanup.
8. Nếu common pool đang dùng chung, đợi Future của task mình, không đợi “cả JVM” một cách mơ hồ.
9. Nếu dùng `awaitQuiescence`, nhớ đó là trạng thái tạm thời, có thể đổi ngay khi task mới tới.
10. Phân biệt lỗi task, cancellation và pool lifecycle; đọc kết quả qua Future.
11. Không giữ lock/tài nguyên mà worker cần trong khi awaitTermination/close.
12. Thiết kế task phản hồi interrupt và có timeout I/O khi cần.
13. Đo latency shutdown, số worker chờ, queue và thread dump thay vì suy từ một snapshot.
14. Kiểm thử quá trình shutdown khi vẫn có task chờ bằng latch/condition được điều phối rõ ràng.
15. Đảm bảo resource mà worker dùng chỉ đóng **sau khi** những worker liên quan đã ngừng sử dụng.

## 16. Tài liệu tham khảo chuẩn

- [ForkJoinPool API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [ExecutorService API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [ForkJoinTask API – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)

**Ghi nhớ:** `commonPool()` là tài nguyên chia sẻ nên `shutdown()`, `shutdownNow()` và `close()` **không làm nó dừng**; `awaitTermination` trên common luôn false. Dùng `awaitQuiescence` cho trạng thái tạm rảnh, hoặc Future khi cần kết quả task cụ thể. Với **ForkJoinPool riêng**, quản lý rõ owner và dùng `shutdown()` + `awaitTermination()` hoặc `close()` trên JDK 21+ để kết thúc vòng đời. Không nhầm việc yêu cầu dừng, trạng thái quiescent và terminated, cũng không coi shutdown là bảo đảm mọi tác vụ nghiệp vụ đều thành công.