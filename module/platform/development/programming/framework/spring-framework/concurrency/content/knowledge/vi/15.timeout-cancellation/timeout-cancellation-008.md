# Ngăn công việc hết giá trị tiếp tục tạo tác dụng phụ

## 1. Vấn đề: hết thời hạn không đồng nghĩa công việc đã dừng

Một ứng dụng Spring nhận yêu cầu tạo báo cáo, gửi email, cập nhật trạng thái đơn hàng hoặc gọi API thanh toán. Công việc chạy bất đồng bộ qua `@Async`, `Executor` hoặc `CompletableFuture`. Người dùng hủy, request hết timeout, hoặc yêu cầu mới thay thế yêu cầu cũ. **Worker cũ vẫn có thể đang chạy và thực hiện một tác dụng phụ**: ghi database, phát message, gửi email, gọi API ngoài, ghi file, thay đổi cache hoặc kích hoạt một thao tác không thể thu hồi.

Ví dụ:

1. 10:00:00, người dùng yêu cầu xuất báo cáo phiên bản 7. Worker A bắt đầu tính.
2. 10:00:02, người dùng đổi bộ lọc; phiên bản 8 thay thế phiên bản 7.
3. 10:00:03, controller đánh dấu request A đã hết thời hạn, hoặc future A hoàn tất với timeout.
4. 10:00:05, worker A hoàn tất tính toán và **ghi kết quả phiên bản 7 đè lên phiên bản 8**.

Việc caller không còn chờ A **không ngăn** A sửa trạng thái. Tương tự, nếu người dùng rời trang đặt hàng, điều đó không tự chứng minh đơn hàng hoặc thanh toán phải được hủy. Ứng dụng cần một **hợp đồng nghiệp vụ**: khi nào công việc được xem là hết giá trị, và tác dụng phụ nào phải được chặn.

**Mục tiêu sau bài học:**

- Phân biệt timeout khi chờ, trạng thái `CompletableFuture`, tín hiệu interrupt, lệnh hủy nghiệp vụ và việc đã thực sự chặn tác dụng phụ.
- Thiết kế `deadline`, cancellation token, revision/generation và quy tắc `latest-wins` khi phù hợp.
- Hiểu race condition giữa **kiểm tra còn hợp lệ** và **thực hiện side effect**.
- Bảo vệ ranh giới ghi bằng kiểm tra nguyên tử, optimistic locking, fencing token và idempotency.
- Biết giới hạn của `@Async`, `Future.cancel(true)`, `CompletableFuture.cancel(true)`, `orTimeout` và `get(timeout)`.
- Chọn cách xử lý side effect bên ngoài database: outbox, xác nhận token tại downstream, compensation hoặc báo trạng thái không chắc chắn.
- Viết và chạy các ví dụ Java 17+ có output xác định, kể cả tình huống sai do race.
- Test shutdown, retry, stale tasks và quan sát số lần tác dụng phụ bị chặn trong Spring.

Bài thuộc nhóm **Hết hạn và hủy** của chủ đề Spring Framework – concurrency. Trọng tâm không phải “cách làm future trả lỗi timeout”, mà là **cách bảo đảm công việc không còn quyền tạo tác dụng phụ sau khi mất hiệu lực theo chính sách đã định**.

## 2. Trước hết: phân biệt năm khái niệm

| Khái niệm | Ý nghĩa | Có tự ngăn tác dụng phụ về sau không? |
| --- | --- | --- |
| Caller hết thời gian đợi | `Future.get(timeout, unit)` không nhận kết quả trước deadline | **Không**; worker có thể tiếp tục |
| Future hoàn thành bất thường | `CompletableFuture.orTimeout` hoặc `completeExceptionally` thay đổi trạng thái future | **Không**; tác vụ nền có thể còn chạy |
| Yêu cầu hủy tính toán | `Future.cancel(true)` có thể cố interrupt; `CompletableFuture.cancel` có semantics riêng | **Không bảo đảm** dừng I/O, ngăn code tiếp tục hoặc rollback |
| Mất hiệu lực nghiệp vụ | Phiên bản cũ, yêu cầu mới thay thế, trạng thái job bị hủy, deadline nghiệp vụ đã qua | Cần **kiểm tra và thực thi quy tắc** tại đúng ranh giới |
| Tác dụng phụ đã commit/được gửi | DB commit, API bên ngoài chấp nhận lệnh, email được phát, message đã publish | Thường **không thể “unsend”**; cần chính sách, idempotency, compensation |

Một thao tác có thể **hết giá trị đối với giao diện** nhưng vẫn **phải hoàn tất về nghiệp vụ**. Ví dụ: HTTP timeout sau khi ngân hàng đã nhận yêu cầu chuyển tiền không cho phép tự phát lệnh chuyển tiền ngược hoặc gửi lại không có idempotency key. Định nghĩa “hết giá trị” phải theo domain, không chỉ theo deadline trình duyệt.

### 2.1. Những tác dụng phụ cần nhận diện

- **Trong JVM:** thay đổi bean singleton, cache, collection chia sẻ, ghi file tạm.
- **Trong database:** INSERT/UPDATE/DELETE, ghi trạng thái job, commit transaction.
- **Qua mạng:** gửi email, webhook, thông báo đẩy, gọi dịch vụ thanh toán, tạo đơn bên thứ ba.
- **Qua message broker:** publish event, gửi command hoặc xác nhận message.
- **Ngoài tiến trình:** chạy process, ghi lên object storage, tạo tài nguyên cloud.

Việc đặt một `if (cancelled) return;` trước mỗi thao tác có thể loại bỏ nhiều công việc vô ích. Nhưng nếu **hủy xảy ra sau lúc kiểm tra và trước lúc ghi**, tác dụng phụ vẫn có thể diễn ra. Đó là lỗ hổng check-then-act quan trọng nhất của bài này.

## 3. Mô hình trạng thái và định nghĩa “còn hợp lệ”

Không có một mô hình phù hợp mọi nghiệp vụ, nhưng nên ghi rõ một state machine. Ví dụ job tạo bản xem trước có thể là:

```text
PENDING ---> RUNNING ---> SUCCEEDED
   |            |   \----> FAILED
   |            |
   |            +-----> CANCEL_REQUESTED ---> CANCELLED
   |            |
   |            +-----> EXPIRED
   |
   +-----> CANCELLED / EXPIRED
```

Các mũi tên mang tính mô hình: trong hệ thống thật phải quyết định **cạnh tranh trạng thái** khi một thread đang commit thành công đúng lúc thread khác yêu cầu hủy. Không tự cho phép mọi trạng thái chuyển sang mọi trạng thái khác.

Một công việc chỉ được tạo tác dụng phụ khi tất cả điều kiện áp dụng đều đúng, ví dụ:

```text
job.state == RUNNING
AND job.generation == currentGeneration(resourceId)
AND job.deadline > authoritativeNow()
AND operationId chưa được áp dụng
AND business invariant vẫn đúng
```

Điều kiện `generation` thích hợp cho yêu cầu “chỉ kết quả mới nhất được phép ghi”. Điều kiện deadline thích hợp khi sau thời điểm đó kết quả không còn có ý nghĩa. Idempotency key áp dụng khi cùng một lệnh có thể được retry. Chúng giải quyết **các bài toán khác nhau**, không nên dùng thay nhau.

### 3.1. Ai quyết định hợp lệ?

- **Caller/UI:** có thể thông báo không còn cần kết quả, nhưng không nên tự là nguồn sự thật của giao dịch đã commit.
- **Service nghiệp vụ:** quyết định luật “job được commit khi nào”, quyền hủy và phản hồi khi conflict.
- **Database/authoritative store:** có thể giữ revision, state, deadline, idempotency key và đảm bảo thay đổi nguyên tử.
- **Downstream:** nếu tác dụng phụ xảy ra ngoài hệ thống, downstream cần một cách từ chối token cũ hoặc chấp nhận idempotency key khi có thể.
- **Worker:** kiểm tra sớm để tiết kiệm tài nguyên và kiểm tra lần cuối tại boundary commit; không tự dựa vào trạng thái cục bộ nếu hệ thống có nhiều replica.

Nếu nhiều request cập nhật cùng tài nguyên, một `AtomicBoolean` trong một worker **không đủ** để đồng bộ giữa các instance hay JVM restart. Cần lưu quyền thực thi và generation ở hệ thống dùng chung khi chính sách yêu cầu đồng bộ toàn cụm.

## 4. Timeout và hủy trong Java: hiểu đúng hợp đồng API

### 4.1. Future.get(timeout, unit)

`future.get(2, TimeUnit.SECONDS)` giới hạn **thời gian thread caller đợi**. Nếu quá hạn, nó ném `TimeoutException` cho caller; điều đó không đồng nghĩa task ngừng. Task vẫn có thể hoàn thành trong nền và gây tác dụng phụ.

Một ví dụ khái niệm:

```java
Future<?> task = executor.submit(() -> sendEmail());
try {
    task.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Chỉ biết caller đã đợi quá lâu.
    // sendEmail() có thể vẫn chạy hoặc đã gửi xong.
}
```

Đây là **fragment** cần định nghĩa executor/sendEmail, import Java và chính sách lỗi; không phải chương trình chạy độc lập. Để hủy task, bạn có thể **yêu cầu** `task.cancel(true)`, nhưng vẫn phải thiết kế kiểm tra nghiệp vụ, timeout của client và idempotency.

### 4.2. Future.cancel(true)

Hợp đồng `Future.cancel(boolean)` cho phép thử hủy task. Với một số implementation kiểu `FutureTask`, nếu task đang chạy và thread thực thi được biết, `cancel(true)` có thể gửi tín hiệu **interrupt**. Nó không phải cơ chế cưỡng chế giết thread: code có thể bỏ qua interrupt, I/O có thể không phản hồi, hoặc side effect đã xảy ra.

- Nếu task chưa chạy, việc cancel thành công có thể ngăn nó bắt đầu.
- Nếu task đang chạy, interrupt là tín hiệu **hợp tác**; không tự rollback transaction hay hủy một HTTP request đã được downstream xử lý.
- Sau khi một `Future` được đánh dấu cancelled, `get()` không còn là công cụ để chứng minh tác vụ vật lý đã dừng; với implementation chạy trong nền, cần theo dõi trạng thái dừng thực tế.
- Giá trị boolean trả về phụ thuộc implementation và race với completion; không dùng nó làm bằng chứng giao dịch đã bị đảo ngược.

### 4.3. CompletableFuture.cancel(true) có điểm đặc biệt

Theo Javadoc Java 17, `CompletableFuture.cancel(mayInterruptIfRunning)` hoàn thành future bằng `CancellationException` nếu chưa hoàn tất; **tham số `mayInterruptIfRunning` không có tác dụng với implementation này**, vì interrupt không được dùng để điều khiển computation.

Vì vậy:

```java
CompletableFuture<Result> stage =
        CompletableFuture.supplyAsync(() -> blockingCall(), executor);

stage.cancel(true);
```

là **fragment**, không bảo đảm `blockingCall()` bị interrupt, không bảo đảm HTTP/DB call được hủy, và không ngăn logic phía sau trong supplier nếu nó đã chạy. Muốn worker dừng hợp tác, cần tín hiệu riêng và kiểm tra tại các checkpoint; với effect quan trọng, cần **freshness guard ở commit**.

### 4.4. orTimeout và completeOnTimeout

`orTimeout(timeout, unit)` hoàn thành chính `CompletableFuture` bằng `TimeoutException` nếu nó chưa hoàn tất vào deadline. `completeOnTimeout(fallback, timeout, unit)` hoàn thành tương tự nhưng bằng một **giá trị fallback** nếu deadline thắng race. Cả hai không đồng nghĩa với việc worker nguồn bị dừng.

Cẩn thận với:

```java
CompletableFuture<Result> task = startAsync();
CompletableFuture<Result> timed = task.orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` trả về **chính** `CompletableFuture` đã gọi trong API Java thông thường; đừng suy ra nó tạo một wrapper độc lập để chỉ thay kết quả của caller. Future có thể bị đánh dấu timeout trong khi supplier đã được submit vẫn chạy.

`completeOnTimeout(defaultValue, ...)` còn có rủi ro khác: downstream callback dựa trên completion bình thường có thể chạy với **giá trị fallback**. Nếu callback dùng fallback để ghi business state, phải chắc chắn đó là hành vi được phép.

### 4.5. Bảng chọn hành vi

| Nhu cầu | Java API/cơ chế | Chú ý |
| --- | --- | --- |
| Caller không được chờ quá SLA | `get(timeout)` | Không dừng worker |
| Stage hoàn tất lỗi khi quá hạn | `orTimeout` | Không hủy tác dụng phụ |
| Stage trả fallback theo deadline | `completeOnTimeout` | Fallback có thể kích hoạt callback bình thường |
| Xin dừng tác vụ đã submit | `Future.cancel(true)` | Interrupt tùy implementation; cần hợp tác |
| Đánh dấu một `CompletableFuture` cancelled | `CompletableFuture.cancel(true)` | Không dùng interrupt điều khiển source |
| Dừng việc vô ích giữa các pha | Atomic cancellation flag / token + interrupt check | Chặn sớm, nhưng có check-then-act race |
| Ngăn ghi giá trị cũ trong DB | Conditional write/optimistic lock theo generation | Kiểm tra + thay đổi phải nguyên tử |
| Ngăn command cũ ở hệ ngoài | Downstream kiểm tra fencing token hoặc giao thức idempotent | Cần downstream hỗ trợ |
| Không được mất job khi restart | Durable queue/job store/outbox | Future trong RAM không đủ |

## 5. Ví dụ Java 17+: timeout đã xảy ra nhưng tác dụng phụ vẫn tiếp tục

Ví dụ cố ý biểu diễn **hành vi cần tránh**. Một worker chờ latch; main cho future timeout; sau đó main mở latch để worker thực hiện tác dụng phụ. Dùng latch giúp test có thứ tự rõ ràng, không dựa vào `Thread.sleep`.

Tệp `TimeoutStillRunsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class TimeoutStillRunsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger effects = new AtomicInteger();

        try {
            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                        effects.incrementAndGet();
                        return "stored";
                    }, executor);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            result.orTimeout(0, TimeUnit.MILLISECONDS);
            try {
                result.join();
            } catch (CompletionException ex) {
                System.out.println("future-error="
                        + ex.getCause().getClass().getSimpleName());
            }

            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not stop");
            }
            System.out.println("effects-after-timeout=" + effects.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TimeoutStillRunsDemo.java
java TimeoutStillRunsDemo
```

Stdout khi hoàn tất bình thường:

```text
future-error=TimeoutException
effects-after-timeout=1
```

**Giải thích:** worker đã bắt đầu và chờ `release`, nên `orTimeout(0, ...)` có cơ hội hoàn thành future một cách bất thường trước khi worker tự chạy tiếp. Main quan sát `TimeoutException`; sau đó mới mở latch. Worker vẫn tăng `effects` vì không có guard nghiệp vụ nào trước tác dụng phụ. `executor.awaitTermination` giúp xác nhận side effect đã chạy xong trước lúc đọc counter.

Đây là chứng minh trực tiếp rằng **tình trạng future** không phải **quyền tạo tác dụng phụ**. Đừng chữa bằng cách chỉ thêm `exceptionally(...)` để future “không còn lỗi”; điều đó càng có thể che mất vấn đề.

## 6. Phòng tuyến thứ nhất: dừng hợp tác trước công việc không cần thiết

Một worker có thể thực hiện nhiều pha:

```text
received
  -> validate input
  -> load data
  -> compute result
  -> prepare change
  -> commit effect
```

Khi nhận thấy công việc hết giá trị, nên dừng càng sớm càng tốt:

1. Trước khi bắt đầu pha tốn CPU/I/O.
2. Sau khi một lời gọi chặn trở về.
3. Trước khi submit tác vụ phụ tiếp theo.
4. Sau khi nhận tín hiệu hủy từ caller/broker.
5. **Ngay tại ranh giới commit tác dụng phụ**, với cơ chế kiểm tra nguyên tử khi cần độ đúng cao.

Trong một JVM, token đơn giản có thể là `AtomicBoolean cancelled` hoặc `AtomicLong generation`. Worker có thể kiểm tra `Thread.currentThread().isInterrupted()` khi đang dùng interruption-based cancellation; khi bắt `InterruptedException`, thường cần thoát hợp tác và khôi phục trạng thái interrupt nếu code tiếp tục truyền tín hiệu.

### 6.1. Ví dụ Java 17+: token chặn công việc trước side effect

Tệp `CooperativeGuardDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CooperativeGuardDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean obsolete = new AtomicBoolean(false);
        AtomicInteger effects = new AtomicInteger();

        try {
            Future<Boolean> job = executor.submit(() -> {
                started.countDown();
                release.await();
                if (obsolete.get()) {
                    return false; // Không ghi khi yêu cầu đã bị thay thế.
                }
                effects.incrementAndGet();
                return true;
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker not started");
            }

            obsolete.set(true);
            release.countDown();

            System.out.println("applied=" +
                    job.get(5, TimeUnit.SECONDS));
            System.out.println("effects=" + effects.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

```bash
javac CooperativeGuardDemo.java
java CooperativeGuardDemo
```

Output:

```text
applied=false
effects=0
```

Khi main đã đặt `obsolete=true` trước lúc mở latch, worker nhận tín hiệu và bỏ qua tác dụng phụ. `AtomicBoolean` bảo đảm visibility/atomicity của biến trạng thái trong một JVM.

**Giới hạn:** nếu main đặt `obsolete=true` **sau lúc worker kiểm tra** nhưng **trước lúc worker `incrementAndGet()`**, side effect vẫn có thể xảy ra. Một boolean guard làm giảm công việc thừa, nhưng chưa phải bảo đảm tuyệt đối cho điều kiện “không ghi sau khi đã hết giá trị”.

### 6.2. Ví dụ Java 17+: Future.cancel(true) và interruption hợp tác

Tệp `InterruptCooperationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class InterruptCooperationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicInteger effects = new AtomicInteger();

        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                    effects.incrementAndGet();
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker not started");
            }

            boolean accepted = task.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("interrupt not observed");
            }

            System.out.println("cancel-accepted=" + accepted);
            System.out.println("interrupt-seen=" + sawInterrupt.get());
            System.out.println("effects=" + effects.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac InterruptCooperationDemo.java
java InterruptCooperationDemo
```

Output khi không có tác động interrupt ngoài chương trình:

```text
cancel-accepted=true
interrupt-seen=true
effects=0
```

Ở đây `Future` từ `ExecutorService.submit` có thể interrupt worker đang chờ `CountDownLatch.await()`; worker **chủ động** xử lý `InterruptedException` và không thực hiện effect. Nó minh họa interruption hợp tác, **không** chứng minh mọi JDBC/HTTP call đều có thể ngắt hoặc mọi `CompletableFuture.cancel(true)` đều gửi interrupt.

## 7. Lỗ hổng check-then-act: kiểm tra đúng nhưng ghi vẫn sai

Trường hợp nguy hiểm hơn:

```java
if (generation.get() == expectedGeneration) {
    // Task có thể bị thay thế ngay tại đây.
    writeResult();
}
```

Hai thao tác **đọc trạng thái** và **ghi tác dụng phụ** là hai sự kiện khác nhau. Thread khác có thể hủy/thay thế ở giữa. `AtomicLong` giúp đọc generation một cách atomic và có visibility, nhưng **không tự biến** cả hai thao tác thành một transaction.

### 7.1. Ví dụ Java 17+: tái hiện race bằng latch

Tệp `CheckThenActRaceDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CheckThenActRaceDemo {
    public static void main(String[] args) throws Exception {
        AtomicLong generation = new AtomicLong(1);
        AtomicInteger effects = new AtomicInteger();
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch continueTask = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            long capturedGeneration = generation.get();

            Future<Boolean> stale = executor.submit(() -> {
                if (generation.get() != capturedGeneration) {
                    return false;
                }
                checked.countDown();
                continueTask.await();
                effects.incrementAndGet();
                return true;
            });

            if (!checked.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("not checked");
            }

            generation.incrementAndGet(); // Yêu cầu mới đã thay thế.
            continueTask.countDown();

            System.out.println("stale-applied=" +
                    stale.get(5, TimeUnit.SECONDS));
            System.out.println("effects=" + effects.get());
        } finally {
            continueTask.countDown();
            executor.shutdownNow();
        }
    }
}
```

```bash
javac CheckThenActRaceDemo.java
java CheckThenActRaceDemo
```

Output:

```text
stale-applied=true
effects=1
```

Lịch đã được điều phối: worker kiểm tra generation 1; main nâng lên 2; worker mới chạy tiếp và ghi. Worker “đã kiểm tra” nhưng **kết luận hợp lệ không còn đúng tại thời điểm effect**.

**Bài học:** các checkpoint trước pha tốn CPU/I/O tốt cho hiệu năng; đối với effect ảnh hưởng đúng/sai nghiệp vụ, phải có **quy tắc nguyên tử tại ranh giới tác dụng phụ**, hoặc một hợp đồng downstream có khả năng từ chối token cũ. Không coi nhiều `if` rời rạc là một transaction.

## 8. Fencing token, generation và kiểm tra nguyên tử tại commit

Một giải pháp thông dụng cho “chỉ công việc mới nhất được phép ghi” là **generation** (còn gọi revision/epoch/fencing token). Mỗi khi yêu cầu mới thay thế yêu cầu cũ, authoritative store tăng generation. Worker mang generation đã cấp lúc bắt đầu. Trước khi áp dụng effect, nơi **sở hữu dữ liệu** chỉ cho phép token trùng generation hiện tại.

### 8.1. Vì sao fencing token tốt hơn một cờ cancelled đơn giản?

| Cơ chế | Có tác dụng gì? | Giới hạn |
| --- | --- | --- |
| `AtomicBoolean cancelled` trong worker | Dừng sớm cùng JVM | Không tự đồng bộ nhiều process; check-then-act race |
| `AtomicLong generation` trong process | Phát hiện kết quả cũ khi cùng process quản lý tài nguyên | Restart/replica khác có trạng thái riêng; vẫn phải commit atomic |
| Generation lưu DB | Token dùng chung giữa replica/restart | Cần transaction/conditional update chuẩn |
| Fencing token downstream kiểm tra | Downstream từ chối command từ owner/lease cũ | Chỉ hiệu lực nếu downstream **thực sự kiểm tra** token |
| Idempotency key | Chặn tác động lặp của **cùng lệnh** | Không tự chặn **lệnh cũ nhưng khác ID** |
| Business deadline/state | Chặn tác động sau thời điểm/trạng thái quy định | Phải kiểm tra ở nguồn có thẩm quyền và cùng ranh giới commit |

Một token nên tăng đơn điệu hoặc tuân theo thứ tự phiên bản mà hệ thống có thể xác minh. Không dùng timestamp từ clock mỗi instance như một thứ tự tuyệt đối nếu các clock có thể lệch, và không reset token tùy tiện sau JVM restart khi worker cũ vẫn có thể đến muộn.

### 8.2. Ví dụ Java 17+: atomic gate mô phỏng bằng synchronized

Tệp `AtomicFencingDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class AtomicFencingDemo {
    static final class Store {
        private long generation = 1;
        private int effectCount;
        private final Set<String> completedIds = new HashSet<>();

        synchronized long current() {
            return generation;
        }

        synchronized long supersede() {
            return ++generation;
        }

        synchronized String commit(long token, String operationId) {
            if (token != generation) {
                return "STALE";
            }
            if (!completedIds.add(operationId)) {
                return "DUPLICATE";
            }
            effectCount++;
            return "APPLIED";
        }

        synchronized int effects() {
            return effectCount;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        long oldToken = store.current();
        long currentToken = store.supersede();

        System.out.println("old=" +
                store.commit(oldToken, "old-command"));
        System.out.println("current=" +
                store.commit(currentToken, "new-command"));
        System.out.println("retry=" +
                store.commit(currentToken, "new-command"));
        System.out.println("effects=" + store.effects());
    }
}
```

```bash
javac AtomicFencingDemo.java
java AtomicFencingDemo
```

Output:

```text
old=STALE
current=APPLIED
retry=DUPLICATE
effects=1
```

Toàn bộ `current/supersede/commit` được đồng bộ hóa trên một `Store`; trong `commit`, **kiểm tra token + kiểm tra duplicate + áp dụng effect** xảy ra trong cùng một critical section. Một thread khác không thể chèn `supersede` vào khoảng giữa check và effect của `commit` trên instance đó.

**Giới hạn phải nhớ:** code này **chỉ** bảo đảm trong một JVM và với một `Store` duy nhất. Trong ứng dụng Spring có nhiều replica, database hoặc durable state store phải thực thi cơ chế tương đương. Nếu effect là gửi email bên ngoài, không thể giữ Java `synchronized` mà kết luận email sẽ bị từ chối sau hủy ở hệ bên kia.

### 8.3. Chọn điểm tuyến tính hóa (linearization point)

Khi commit và cancel xảy ra đồng thời, cần định nghĩa cái nào thắng:

- Nếu **cancel được commit trước**, mọi effect dùng token cũ phải bị từ chối.
- Nếu **effect được commit trước**, lệnh hủy đến muộn có thể báo “quá muộn để hủy”; không được tuyên bố rollback đã xảy ra.
- Nếu nghiệp vụ bắt buộc “hủy trước một mốc” chứ không phải trước commit, phải lưu/đánh giá deadline tại authoritative boundary.
- Nếu có công việc chạy nhiều phút, đừng khóa toàn bộ pipeline; chỉ bảo vệ **bước chuyển trạng thái/tác dụng phụ** bằng transaction có thời gian ngắn, rồi thiết kế những bước I/O bên ngoài.

Đây là chính sách về **thứ tự quyền lực của state transition**, không phải yêu cầu đảm bảo scheduler chạy theo thứ tự thời gian tường đồng hồ.

## 9. Cài đặt trong database: conditional write và optimistic locking

Với hệ nhiều instance, cơ chế mạnh hơn là một lệnh database làm **kiểm tra và thay đổi cùng lúc**. Ví dụ tư duy SQL (minh họa kiểu PostgreSQL; cần schema, index, transaction và mapping trạng thái cụ thể):

```sql
UPDATE report_jobs
SET state = 'READY',
    result_ref = :result_ref
WHERE job_id = :job_id
  AND generation = :expected_generation
  AND state = 'RUNNING'
  AND expires_at > CURRENT_TIMESTAMP;
```

Đọc số hàng được cập nhật:

- **1 hàng:** tại thời điểm lệnh UPDATE được database thực thi theo transaction semantics phù hợp, điều kiện hiện hợp lệ và effect trong DB được áp dụng.
- **0 hàng:** có thể job đã bị hủy/thay thế, hết hạn, hoàn tất ở nơi khác hoặc không tồn tại. Không retry vô điều kiện cùng dữ liệu cũ; phân loại nguyên nhân theo nghiệp vụ.
- **Lỗi database/transaction:** trạng thái có thể chưa được commit; theo dõi transaction outcome và idempotency trước khi retry.

Với ranh giới phức tạp, dùng `@Version`/optimistic locking của JPA hoặc custom repository conditional update. Không thực hiện `SELECT status`, đợi vài giây, rồi `UPDATE` không có điều kiện: đó là check-then-act race.

### 9.1. Khi cần ghi cả trạng thái và outbox

Nếu tác dụng phụ là gửi event cho dịch vụ khác, có thể ghi **state transition + outbox record** trong **cùng database transaction**:

```text
BEGIN TRANSACTION
    UPDATE job WHERE generation = expected AND state = RUNNING;
    nếu updatedRows != 1 -> ROLLBACK và báo STALE/EXPIRED;
    INSERT outbox(eventId, operationId, generation, payload);
COMMIT
```

Đây là **pseudocode**, không phải SQL chạy độc lập. Dùng unique constraint/idempotency key cho event hoặc operation ID để hạn chế duplicate. Worker phát event từ outbox có retry và trạng thái giao nhận rõ.

**Cực kỳ quan trọng:** transaction bảo đảm **ghi trạng thái + outbox cùng commit**; nó **không** bảo đảm downstream **không nhận event cũ** nếu job bị thay thế **sau khi outbox đã commit**. Nếu chính sách nói “lệnh cũ không được tác động bên ngoài sau khi một yêu cầu mới đã thắng”, consumer/downstream cần thêm generation/fencing kiểm tra tại điểm **chấp nhận effect**. Một lần kiểm tra ở publisher trước khi gửi vẫn có check-send race.

### 9.2. Fencing token tại downstream

Ví dụ dịch vụ nhận command cập nhật cache/tài nguyên:

```text
Command:
  resourceId = report-42
  generation = 18
  operationId = update-report-42-18

Downstream:
  nếu generation < currentGeneration(resourceId): REJECT_STALE
  nếu operationId đã được áp dụng: DEDUPLICATE
  ngược lại: áp dụng và lưu generation/operationId NGUYÊN TỬ
```

Downstream phải duy trì trạng thái authoritative mà nó có thể kiểm tra. Nếu nó chỉ tin vào một trường `generation` được truyền nhưng không lưu và so sánh, token **không hề ngăn** stale request.

**Điểm khác với idempotency:** command phiên bản 17 và command phiên bản 18 có **operationId khác nhau**. Idempotency giúp không chạy hai lần lệnh 17, nhưng chỉ **fencing** mới giúp không áp dụng lệnh 17 **sau** khi phiên bản 18 đã được công nhận là mới hơn.

## 10. Spring @Async: tách chuẩn bị kết quả và ranh giới side effect

Trong Spring, `@Async` thường được áp dụng qua proxy khi có `@EnableAsync` và method được gọi qua Spring-managed bean. Controller có thể nhận `CompletableFuture` rất sớm, trong khi worker vẫn đang làm việc.

Để tránh stale side effect, nên tách:

1. **Worker/compute:** đọc input immutable, tính kết quả hoặc tạo payload; kiểm tra cancel/deadline định kỳ.
2. **Commit service:** kiểm tra generation/state/deadline một cách **nguyên tử** và ghi business state/outbox trong transaction.
3. **Delivery worker/downstream:** xử lý external side effect với idempotency, fencing và retry phù hợp.
4. **Caller/status API:** phân biệt `SUCCEEDED`, `SKIPPED_STALE`, `CANCELLED`, `TIMED_OUT`, `FAILED`, `UNKNOWN` thay vì chỉ dùng boolean `done`.

### 10.1. Mẫu chia service (snippet Spring, không phải file javac độc lập)

```java
// File trong project Spring: ReportWorker.java
@Service
public class ReportWorker {
    private final ReportCommitService commitService;

    public ReportWorker(ReportCommitService commitService) {
        this.commitService = commitService;
    }

    @Async("reportExecutor")
    public CompletableFuture<CommitOutcome> generate(
            ReportCommand command) {
        // Input nên là immutable snapshot.
        // Tác vụ tính toán có thể kiểm tra token để dừng sớm.
        String preparedResult = calculate(command);

        // Service khác sở hữu transaction/conditional update.
        CommitOutcome outcome = commitService.applyIfCurrent(
                command.jobId(),
                command.generation(),
                preparedResult);

        return CompletableFuture.completedFuture(outcome);
    }
}
```

Đoạn trên là **fragment thiết kế**, cần định nghĩa `ReportCommand`, `CommitOutcome`, `calculate`, các imports, bean `reportExecutor` và repository. Không copy y nguyên rồi mong biên dịch.

Một phần của `ReportCommitService` có thể được thiết kế theo hướng:

```java
@Service
public class ReportCommitService {
    private final ReportRepository repository;
    private final OutboxRepository outbox;

    public ReportCommitService(
            ReportRepository repository,
            OutboxRepository outbox) {
        this.repository = repository;
        this.outbox = outbox;
    }

    @Transactional
    public CommitOutcome applyIfCurrent(
            long jobId, long generation, String result) {

        int updated = repository.writeIfRunningAndCurrent(
                jobId, generation, result);
        if (updated == 0) {
            return CommitOutcome.SKIPPED_STALE;
        }

        outbox.addForCommittedResult(jobId, generation);
        return CommitOutcome.APPLIED;
    }
}
```

Các tên repository/enum ở đây được dùng để minh họa **hợp đồng**, không phải API Spring có sẵn. Repository phải thực hiện update có điều kiện nguyên tử; outbox phải dùng **cùng transaction** với update và có unique constraint thích hợp. `@Transactional` phải được intercept đúng, ví dụ method được gọi từ bean khác qua Spring-managed proxy. Nếu Spring transaction không thực sự áp dụng, “ghi job + outbox cùng transaction” có thể là lời hứa sai.

**Không đặt** `@Transactional` lên một private method rồi gọi bằng `this.applyIfCurrent(...)` từ chính bean và cho rằng transaction proxy đã được áp dụng trong cấu hình proxy mặc định.

### 10.2. Trong controller, timeout không phải lệnh hủy thanh toán

Đối với tạo báo cáo best-effort, request timeout có thể đánh dấu job `EXPIRED` và hủy worker nếu hợp đồng cho phép. Nhưng với thanh toán, nhận timeout từ API bên ngoài có thể là **UNKNOWN**: downstream đã commit nhưng response bị mất. Khi đó cần truy vấn trạng thái bằng operation ID, không tạo giao dịch trùng hoặc tự tuyên bố hủy thành công.

Một quy tắc an toàn:

- **Bước chuẩn bị** có thể bỏ khi không còn cần.
- **Bước đã commit** cần được công nhận, đối soát hoặc compensation theo luật nghiệp vụ.
- **Bước ngoài hệ thống đang “in flight”** có thể có kết quả không biết ngay; không làm lại vô điều kiện.

### 10.3. @Async, CompletableFuture và cancellation

Khi method Spring `@Async` trả `CompletableFuture<T>`, caller có một future đại diện cho invocation. Việc gọi `future.cancel(true)` không tự tạo một business cancellation token bền vững. Ngữ nghĩa interruption của một executor-specific `Future` cũng không được suy từ API `CompletableFuture.cancel`.

Thiết kế rõ ràng hơn là cho caller gọi một **cancel command** có hiệu lực nghiệp vụ, ví dụ thay `RUNNING` thành `CANCEL_REQUESTED` hoặc tăng generation trong database. Worker kiểm tra token để dừng sớm, còn commit service kiểm tra authoritative state tại ranh giới effect.

## 11. Deadline: đồng hồ nào và ai có quyền đánh giá?

Có hai loại deadline:

- **Local elapsed-time deadline:** dùng `System.nanoTime()` hoặc `Duration` để tính thời gian trôi qua **trong cùng JVM**, không phụ thuộc điều chỉnh wall clock. Ví dụ budget tính toán 200 ms.
- **Business expiration timestamp:** dùng một `Instant`/timestamp lưu bền vững và nguồn thời gian authoritative, thường đánh giá ở database hoặc service sở hữu state. Dùng cho job qua nhiều replica/restart.

Ví dụ một checkpoint local (Java fragment):

```java
long deadlineNanos =
        System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(200);

if (System.nanoTime() - deadlineNanos >= 0) {
    // Đã hết budget local; nên dừng pha chuẩn bị.
}
```

Đây là minh họa với budget nhỏ hợp lý; chọn cách so sánh và xử lý overflow phù hợp với thời lượng thực tế. Giá trị `System.nanoTime()` chỉ dùng đo **khoảng cách thời gian**, không phải epoch timestamp để ghi DB hay so sánh giữa hai JVM.

Dùng `Instant.now()` trong từng worker của các replica để quyết định commit có thể tạo khác biệt khi clock lệch. Nếu yêu cầu tuyệt đối tại database boundary, dùng thời gian của database trong **cùng câu lệnh/transaction** bảo vệ effect và xác định quy tắc với commit gần ranh giới deadline.

### 11.1. Truyền deadline đến các bước tiếp theo

Nếu một request có deadline tổng 2 giây, không nên cho mỗi HTTP client retry thêm 2 giây độc lập và tạo tổng thời gian 10 giây. Truyền budget còn lại hoặc absolute deadline có nguồn thời gian rõ tới các tầng xử lý; client connect/read/total timeout phải nằm trong budget phù hợp.

Hết budget trước khi gọi API ngoài thì nên skip khi policy cho phép. Nếu API đã được gửi, timeout không đủ để biết nó có áp dụng side effect hay không; cần operation ID và reconciliation.

## 12. Không áp dụng “chỉ việc mới nhất” cho mọi nghiệp vụ

Latest-wins thích hợp cho **preview, search suggestions, render ảnh tạm, dự đoán thay đổi UI, kết quả tính toán cũ có thể bỏ**. Nó không mặc nhiên thích hợp cho các lệnh **ghi nhận trách nhiệm, đặt hàng, tính phí, gửi giao dịch**.

| Nghiệp vụ | Có thể hủy bỏ công việc cũ? | Chính sách thường cần |
| --- | --- | --- |
| Gợi ý tìm kiếm | Có, theo session/query version | Generation/sequence theo session; không render response cũ |
| Preview PDF chưa được xuất bản | Thường có | Skip nếu phiên bản cũ; commit theo revision |
| Tính toán chỉ để hiển thị dashboard | Có khi dữ liệu cũ không còn cần | Cancellation token + latest-wins cache update |
| Gửi thông báo marketing best-effort | Phụ thuộc opt-out và cửa sổ gửi | Kiểm tra consent/expiry ngay tại delivery; idempotency |
| Gửi email hóa đơn bắt buộc | Không thể tùy tiện bỏ nếu đã phát sinh hóa đơn | Durable job, audit trạng thái, idempotent delivery |
| Thanh toán/chuyển tiền | Không suy từ HTTP timeout | Command ID bền vững, truy vấn trạng thái, reconciliation |
| Cập nhật trạng thái đơn hàng | Chỉ khi invariant cho phép | Optimistic lock/version, state machine, transaction |
| Audit bắt buộc | Không thể bỏ vì caller đã rời trang | Persist event/outbox trước khi xác nhận |

**Nguyên tắc:** trước khi chặn stale side effect, phải xác định “stale” dựa trên luật domain. Một nhiệm vụ bị timeout ở UI không đồng nghĩa quyền thực hiện nghiệp vụ đã hết.

## 13. External side effect: tại sao không thể bảo đảm bằng if(cancelled)?

Giả sử worker gửi request HTTP tới dịch vụ ngoài:

```text
Worker          Local DB          External API
  |
  | check generation=8
  |-------------------------> (chưa có effect)
  |
  |                        hủy/thay thế lên generation=9
  |
  | HTTP POST(generation=8) ---------------------->
  |                                              ghi effect
```

Dù local database đã lưu generation 9 trước HTTP POST, một lần kiểm tra local trước POST không thể ngăn API bên ngoài xử lý phiên bản 8. **Ranh giới cuối cùng kiểm soát effect là nơi chấp nhận effect**.

Các chiến lược tùy khả năng downstream:

1. **Downstream có fencing/version check:** truyền resource ID và generation; bên nhận atomic check token và thay đổi state. Đây là cách mạnh khi cần từ chối stale command.
2. **Downstream có idempotency key:** bảo vệ khỏi duplicate retry; vẫn cần business ordering/version nếu lệnh cũ khác ID không được phép ghi.
3. **Transactional outbox + consumer:** bảo đảm giao message gắn transaction nội bộ; chưa tự loại bỏ stale delivery sau khi outbox commit.
4. **Reservation/prepare-commit protocol:** nếu API hỗ trợ đặt chỗ và xác nhận, quy định thời điểm lệnh có hiệu lực và cách hủy reservation.
5. **Compensation/reconciliation:** khi effect đã diễn ra hoặc không biết trạng thái, dùng nghiệp vụ hoàn tác/đối soát; không giả vờ có atomic rollback qua HTTP.
6. **Thiết kế không phát effect nếu quá hạn** bằng cách để nơi gửi/quyết định cuối cùng kiểm tra policy, với hiểu biết rằng một effect đã được phía ngoài chấp nhận có thể không thể thu hồi.

Không giữ DB lock trong thời gian dài quanh HTTP call chỉ để hy vọng tránh mọi race: lock có thể làm cạn connection, deadlock, và không tạo transaction phân tán với API ngoài. Muốn bảo đảm toàn cục, cần protocol toàn cục hoặc chấp nhận trạng thái có thể đối soát.

## 14. Trạng thái hủy: phản hồi trung thực với caller

Một API hỗ trợ hủy không nên luôn trả “đã hủy thành công” chỉ vì đã nhận request cancel. Có thể có các kết quả:

- `CANCEL_REQUESTED`: đã ghi nhận mong muốn dừng; worker/downstream chưa xác nhận.
- `CANCELLED`: quy tắc nghiệp vụ xác nhận không còn effect tương lai được phép, với phạm vi được bảo đảm.
- `TOO_LATE`: effect đã commit trước khi cancel.
- `NOT_FOUND` hoặc `ALREADY_TERMINAL`: không có job hoặc job đã kết thúc.
- `UNKNOWN`: request bên ngoài đã gửi nhưng chưa biết outcome.
- `REJECTED_STALE`: command cũ bị authoritative boundary từ chối.
- `EXPIRED`: hết hạn theo nguồn thời gian và chính sách đã định.

Ví dụ response JSON minh họa (schema do ứng dụng thiết kế):

```json
{
  "jobId": "report-42",
  "status": "CANCEL_REQUESTED",
  "generation": 9,
  "effectCommitted": false
}
```

Không suy từ `effectCommitted=false` tại một thời điểm rằng không có effect ở hệ ngoài đang in-flight. Với các hệ thống có side effect quan trọng, endpoint trạng thái cần dựa vào operation ID và state bền vững.

### 14.1. Idempotent cancel và retry

Lệnh cancel thường nên có tính idempotent: gửi lại cùng một yêu cầu cancel không tạo tác dụng phụ mới. Nhưng **cancel** và **commit** cạnh tranh nên kết quả có thể khác tùy thứ tự được chốt trong authoritative store. Client cần xử lý `TOO_LATE`/`ALREADY_TERMINAL` thay vì retry vô hạn.

## 15. Kết hợp với CompletableFuture pipeline và callbacks

Một lỗi dễ bỏ sót là source đã bị timeout nhưng callback độc lập còn chạy:

```java
CompletableFuture<Result> source = runAsync();
CompletableFuture<Void> audit =
        source.thenAcceptAsync(result -> persist(result), auditExecutor);
```

Đây là fragment. Nếu `source` được `orTimeout` **trước khi** complete bình thường, callback `thenAccept` phụ thuộc **normal completion** sẽ bị bỏ qua. Nhưng **nếu callback đã được kích hoạt/nộp trước khi timeout/hủy**, việc cancel một future liên quan không phải bảo đảm callback đã chạy sẽ bị interrupt hoặc không còn side effect.

Ngoài ra, callback có thể được gắn trên **future khác**, dùng manual `complete`, hoặc tạo một command riêng trước timeout. Vì vậy không được coi `thenAccept` normal-only là cơ chế bảo vệ commit duy nhất.

**Mẫu an toàn hơn:**

```java
CompletableFuture<Outcome> pipeline =
        source.thenApplyAsync(result ->
                commitService.applyIfCurrent(
                        jobId, expectedGeneration, result),
                commitExecutor);

return pipeline;
```

Fragment này chỉ đúng nếu `applyIfCurrent` **thực hiện kiểm tra nguyên tử tại boundary**; lời gọi method tên như vậy không tự đảm bảo điều kiện. Việc dùng `thenApplyAsync` chỉ giúp chọn executor cho bước commit, không biến một câu `if` thông thường thành transaction.

### 15.1. Cancellation của downstream và upstream không đối xứng

Hủy dependent future không luôn hủy computation upstream; hủy source không bảo đảm interrupt một callback đã chạy. Với pipeline có nhiều nhánh, mỗi nhánh có thể có trạng thái riêng. Cần giữ **operation context** chứa job ID, generation và deadline, đồng thời mỗi side-effect boundary kiểm tra quyền thực hiện của chính nó.

### 15.2. Reactor/WebFlux và timeout

Trong mô hình reactive, các operator `timeout`/cancellation phát tín hiệu dừng subscription phù hợp; nhưng **không bảo đảm rollback side effect** đã chạy hoặc khiến mọi thư viện ngoại vi lập tức dừng. Blocking client được offload lên worker có thể tiếp tục làm việc nếu cancellation chưa được API hỗ trợ. Bảo vệ bằng cùng nguyên tắc: idempotency, business state, fencing/conditional commit tại nơi effect được thực hiện.

## 16. Chiến lược triển khai trong Spring có nhiều replica

Một kiến trúc tham khảo:

```text
HTTP Controller
    |
    | create/cancel/replace command
    v
Job Application Service --transaction--> DB: state, generation, deadline
    |
    | enqueue job ID + expected generation
    v
Durable Queue ---------------------> Worker Instance A/B/C
                                         |
                                         | prepare/compute
                                         | cooperative stop checks
                                         v
                                   Commit Service
                                         |
                                         | conditional UPDATE + outbox
                                         v
                                 authoritative DB
                                         |
                                         v
                                   Outbox Delivery
                                         |
                                         | operationId + fencing token
                                         v
                                Downstream acceptance gate
```

Không phải mọi ứng dụng cần đầy đủ queue/outbox; bài toán preview đơn giản trong một JVM có thể dùng local token và versioned cache write. Nhưng **mức bảo đảm phải khớp rủi ro**. Khi có nhiều replica, dùng `AtomicBoolean` ở từng pod không đủ cho một global latest-wins invariant.

### 16.1. Quy tắc ownership

- Controller chỉ yêu cầu hủy; không tự nhận quyền ghi một trạng thái terminal sai.
- Job service/DB làm nguồn sự thật về state/generation.
- Worker có thể bỏ công việc sớm để tiết kiệm tài nguyên, nhưng không tự quyết định last-write-wins bằng timestamp cục bộ.
- Commit service kiểm tra state/revision cùng transaction.
- Downstream kiểm tra token hoặc idempotency theo hợp đồng; nếu không hỗ trợ, phải thiết kế reconciliation/compensation.
- Scheduler/retry controller không phát lại stale command vô điều kiện.

### 16.2. @Transactional và @Async

`@Async` thường đưa method sang worker thread; transaction trong caller thread không tự theo sang worker. `@Transactional` cần được đặt trên boundary chạy đúng thread và được Spring AOP intercept qua bean reference. Tránh `this.commit()` trong cùng bean nếu đang dựa vào proxy transaction mặc định.

Khi exception xảy ra, phải xác định transaction đã rollback hay đã commit trước khi retry; chỉ quan sát `CompletableFuture.isCompletedExceptionally()` không đủ để kết luận effect ngoài hệ thống chưa xảy ra.

### 16.3. Graceful shutdown

Khi ứng dụng nhận SIGTERM/đóng Spring context:

1. Ngừng nhận job mới, cập nhật readiness nếu thích hợp.
2. Đánh dấu worker lease/cancel intent theo hợp đồng nếu không thể hoàn thành trong grace period.
3. Yêu cầu task kiểm tra interruption/token ở checkpoint.
4. Đợi những commit quan trọng trong giới hạn thời gian cho phép.
5. Dựa vào job store/queue để phục hồi công việc chưa xác nhận, với idempotency và fencing để ngăn owner cũ ghi muộn.
6. Không hứa một in-memory `Future` sẽ tồn tại sau khi process chết.

Nếu task bắt buộc được xử lý sau restart, không tạo một công việc chỉ bằng `executor.execute(...)` rồi trả HTTP `202 Accepted` trước khi có ghi nhận bền vững.

## 17. Quan sát và cảnh báo: đo effect chứ không chỉ đo Future

Các metric cần phân biệt:

| Metric/log | Mục đích |
| --- | --- |
| `jobs_expired_total` | Bao nhiêu job hết business deadline |
| `cancel_requested_total` | Bao nhiêu lệnh hủy được tiếp nhận |
| `tasks_interrupt_observed_total` | Bao nhiêu task thực sự ghi nhận tín hiệu interrupt |
| `effects_skipped_stale_total` | Bao nhiêu commit bị từ chối do generation/state cũ |
| `effects_applied_total` | Bao nhiêu effect được authoritative boundary chấp nhận |
| `effects_duplicate_total` | Bao nhiêu command trùng operationId đã bị dedup |
| `effects_after_expiration_total` | Theo chính sách, có effect nào được phép chấp nhận sau expiry? Nếu không, phải cảnh báo |
| `inflight_external_unknown` | Bao nhiêu external operations đang chưa đối soát outcome |
| `queue_wait`, `active_workers`, `rejects` | Tác dụng của quá tải lên deadline/cancellation |

Log nên chứa **job ID, operation ID, resource ID dạng an toàn, generation, expected/current version, deadline, trạng thái trước/sau, lý do skip**. Không ghi thông tin cá nhân nhạy cảm hoặc payload thanh toán toàn phần vào log.

Cần kiểm soát cardinality trong metrics: không dùng mỗi job ID thành một metrics label. Giữ ID trong structured logs/traces, còn metrics labels nên là tập giá trị hữu hạn như `status`, `executor` và `operationType`.

## 18. Kiểm thử race, hết hạn và tác dụng phụ

Trước khi đưa vào production, phải test **chính trường hợp cạnh tranh**:

1. **Timeout trước khi worker bắt đầu:** task có được skip không? Queue đã có task cũ có bị discard hợp lý không?
2. **Hủy giữa pha tính toán:** worker phát hiện token và không gọi downstream.
3. **Hủy ngay sau check trước effect:** tái hiện bằng latch như `CheckThenActRaceDemo`; giải pháp thật phải chặn được ở commit.
4. **Commit thắng trước cancel:** API cancel phải trả trạng thái đúng (`TOO_LATE` hoặc equivalent), không giả vờ rollback.
5. **Cancel thắng trước commit:** conditional write trả 0 rows; không có outbox effect mới.
6. **Thử lại cùng operationId:** idempotency/dedup không tạo effect thứ hai.
7. **Lệnh cũ đến sau lệnh mới:** downstream fencing từ chối token cũ.
8. **Worker chết và restart:** job được phục hồi theo policy, lease/token của worker cũ không còn hiệu lực.
9. **Tác vụ I/O không phản hồi interrupt:** timeout chỉ tác động caller hay thật sự hủy remote operation? Ghi rõ kết quả UNKNOWN khi cần.
10. **Nhiều replica:** hai worker với cùng hoặc khác generation không ghi đè kết quả hợp lệ.
11. **Clock lệch:** DB authoritative time vẫn đánh giá expiry nhất quán.
12. **Mất response sau effect:** retry không nhân đôi effect nhờ idempotency/reconciliation.

### 18.1. Unit test không thay thế integration test

Các ví dụ với `AtomicLong`/`synchronized` kiểm thử ý tưởng trong **một JVM**. Cần integration test cho câu UPDATE có điều kiện (số hàng cập nhật), transaction rollback, unique constraint, outbox và hành vi database isolation. Có thể dùng Testcontainers hoặc database test environment để chạy đúng engine cần triển khai.

Đối với external API, cần contract test bằng fake/server có hỗ trợ idempotency/fencing, và fault injection ở điểm “request đã nhận nhưng response thất lạc”. Không dùng `Thread.sleep` làm phương pháp duy nhất để tạo race; dùng latch/barrier và deadline có timeout.

### 18.2. Tiêu chí đúng về mặt nghiệp vụ

Một hệ thống không được xem là đúng chỉ vì test cho thấy `cancelledFuture.isCancelled() == true`. Cần chứng minh invariant, ví dụ:

- Với tài nguyên `report-42`, một commit thành công phải mang **current generation tại linearization point**.
- Không có hai commit khác nhau cho cùng `operationId`.
- Khi cancel được chốt trước commit, worker cũ không tạo DB effect.
- Nếu external effect đã được chấp nhận trước cancel, hệ thống trả trạng thái đúng và không “hủy giả”.
- Khi có trạng thái UNKNOWN, có cơ chế đối soát mà không phát lại lệnh nguy hiểm.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “Future timeout là worker dừng” | Timeout thường chỉ tác động waiting/completion | Kiểm tra task và bảo vệ effect |
| “`CompletableFuture.cancel(true)` luôn interrupt” | Javadoc nói flag interrupt không điều khiển implementation này | Token hợp tác + authoritative gate |
| “Thêm `if (!cancelled)` trước ghi là đủ” | Check-then-act race | Atomic conditional commit / fencing |
| “`AtomicBoolean` đủ cho Kubernetes nhiều pod” | Mỗi pod có trạng thái riêng | Shared authoritative state/generation |
| “Idempotency key chặn mọi stale command” | Lệnh cũ khác ID vẫn có thể thắng | Kiểm tra version/fencing bên nhận |
| “Outbox bảo đảm event cũ không phát” | Outbox đảm bảo giao sau commit, không tự kiểm tra freshness tại downstream | Consumer/downstream gate hoặc policy chấp nhận event đã commit |
| “Đã gọi HTTP rồi vẫn rollback được bằng cancel” | API ngoài có thể đã áp dụng side effect | Idempotency, reconciliation, compensation |
| “Có @Transactional trên method nào cũng atomic” | Self-invocation/proxy boundary và transaction scope có thể sai | Bean riêng, verify transaction và SQL |
| “UI rời trang thì hủy luôn thanh toán” | UI timeout không nói gì về business commit | Phân biệt UNKNOWN, TOO_LATE, CANCELLED |
| “Retry đến khi thành công” | Nhân đôi tác dụng phụ, gửi lệnh cũ | Bounded retry, idempotency, generation |
| “Dùng deadline theo local clock cho toàn cụm” | Clock lệch và restart | Authoritative timestamp ở shared store |
| “Task bị reject thì bỏ qua lặng lẽ” | Mất công việc hoặc trạng thái sai | Return error, durable enqueue hoặc explicit policy |

## 20. Bài tập ứng dụng: tạo báo cáo chỉ cho phép phiên bản mới nhất

Giả sử người dùng liên tục thay đổi bộ lọc báo cáo. Hệ thống có nhiều replica Spring Boot, worker có thể chạy lâu và kết quả sẽ được ghi vào DB và phát event để cập nhật màn hình.

**Yêu cầu thiết kế:**

1. Đặt tên tài nguyên `reportId`, operation ID và generation. Khi request mới đến, tăng generation trong DB và đánh dấu generation cũ stale.
2. Worker nhận immutable command chứa `reportId` + `generation` + deadline. Trong pha tính toán, kiểm tra tín hiệu hủy để dừng sớm.
3. Khi tính xong, dùng conditional UPDATE trên `reportId` và `generation`, với trạng thái/expiry thích hợp. Nếu 0 rows, trả `SKIPPED_STALE` và **không** phát effect.
4. Nếu UPDATE thành công, ghi outbox trong cùng transaction. Tạo unique idempotency key cho event.
5. Consumer chỉ gửi event tới nơi có chính sách version/fencing rõ; nếu UI chỉ cần bản mới nhất, giao thức nhận có thể từ chối message version thấp hơn bản đã công nhận.
6. Khi caller timeout, không chỉ gọi `future.cancel(true)` rồi xóa job state; phải persist/sắp xếp policy hủy.
7. Khi hai worker cùng commit, integration test xác nhận chỉ bản được phép cập nhật và không có outbox trùng.
8. Khi cancel đến sau DB commit, phản hồi rõ `TOO_LATE` hoặc trạng thái equivalent; đừng xóa audit trail.
9. Khi upstream/downstream không đáp ứng, sử dụng timeout, bounded retry, metric và đối soát UNKNOWN.
10. Thực hiện load test burst, executor shutdown và rolling restart; đo stale skips, effects applied và queue wait.

### 20.1. Checklist tự đánh giá

- [ ] Tôi phân biệt được caller timeout và worker thực sự dừng.
- [ ] Tôi hiểu `CompletableFuture.cancel(true)` không cưỡng chế interrupt nguồn đang chạy.
- [ ] Tôi biết cách dùng cooperative token/interrupt tại các checkpoint để giảm công việc lãng phí.
- [ ] Tôi có thể tái hiện check-then-act race bằng latch.
- [ ] Tôi hiểu vì sao kiểm tra và commit phải atomic khi cần bảo đảm không có stale effect.
- [ ] Tôi biết generation/fencing khác idempotency key ở mục tiêu nào.
- [ ] Tôi biết dùng optimistic locking/conditional UPDATE khi nhiều replica cùng ghi.
- [ ] Tôi hiểu hạn chế của outbox và local pre-send check đối với external side effect.
- [ ] Tôi biết phân biệt CANCEL_REQUESTED, CANCELLED, TOO_LATE và UNKNOWN.
- [ ] Tôi không tự hủy giao dịch quan trọng chỉ vì HTTP/UI timeout.
- [ ] Tôi kiểm chứng Spring `@Async`, `@Transactional`, executor và context đúng nơi chạy.
- [ ] Tôi có test cho cancel-before-commit, commit-before-cancel, retry và restart.
- [ ] Tôi quan sát được tác dụng phụ thật, không chỉ trạng thái future.

**Kết luận:** để **ngăn công việc hết giá trị tiếp tục tạo tác dụng phụ**, cần nhiều lớp: dừng hợp tác để tiết kiệm tài nguyên, **định nghĩa hiệu lực nghiệp vụ**, và **thực thi kiểm tra nguyên tử ở ranh giới chấp nhận effect**. Timeout/cancel chỉ thay đổi quyền chờ hoặc gửi tín hiệu dừng; chúng không xóa tác dụng phụ đã commit. Đối với hệ phân tán, generation/fencing, idempotency, transaction/outbox và reconciliation phải được thiết kế theo **mức bảo đảm thực tế** của từng hệ thống.

## 21. Tài liệu chính thức

- Java SE 17 — [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, `cancel` và cancellation contract.
- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel`, `orTimeout`, `completeOnTimeout`, dependent stages và exceptional completion.
- Java SE 17 — [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ các bước trong test concurrency.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor`, async method return type và exception handling.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): ranh giới `@Transactional` và nguyên tắc áp dụng transaction advice.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): lý do self-invocation có thể bỏ qua advice.

Thực hành trên Java 17+ và đối chiếu với phiên bản Spring, DB engine và downstream thực tế. Các đoạn SQL và Spring trong bài được ghi rõ là **mẫu thiết kế**, không phải API có sẵn hoặc giao dịch phân tán tự động.
