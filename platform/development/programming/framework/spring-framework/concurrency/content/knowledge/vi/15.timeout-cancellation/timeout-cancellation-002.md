# Future.get(timeout) không tự dừng công việc nền

Trong ứng dụng Spring Framework, một request có thể gửi tác vụ tạo báo cáo, gọi API ngoài hoặc xử lý dữ liệu vào `ExecutorService`/`ThreadPoolTaskExecutor`, rồi chờ kết quả bằng `Future.get(timeout, unit)`. Nếu hết thời gian chờ, Java ném `TimeoutException`. **Điều đó chỉ có nghĩa thread đang chờ chưa nhận được kết quả trong khoảng thời gian cho phép; nó không có nghĩa task đã bị hủy, worker đã dừng, hoặc tác động nghiệp vụ đã được hoàn tác.**

Đây là phân biệt cốt lõi trong nhóm **Hết hạn và hủy** của module **Spring Framework – concurrency**. Cần hiểu độc lập ba câu hỏi:

1. **Caller còn chờ hay đã ngừng chờ?** `Future.get(timeout)` kiểm soát thời gian chặn của caller.
2. **Future đang ở trạng thái gì?** Future có thể chưa hoàn tất, hoàn tất bình thường, hoàn tất lỗi hoặc bị hủy.
3. **Công việc thật trên worker đã dừng chưa?** Việc dừng cần cơ chế cancellation/interruption hợp tác và timeout ở từng tài nguyên; không được suy từ exception của caller.

Một hệ thống có thể trả response “hết thời gian chờ” trong khi worker vẫn gọi database, ghi file hoặc gửi email. Nếu client retry mà không có idempotency, tác động có thể xảy ra **hai lần**.

## 1. Mô hình thời gian: caller hết hạn trước, worker tiếp tục

```text
Thời gian ──────────────────────────────────────────────────────────────>

HTTP caller / main thread
  | submit(task)
  |--------------- Future<?> ----------------|
  | get(100, MILLISECONDS)
  |          └──── 100 ms ────> TimeoutException
  |                              |
  |                              └─ Caller tiếp tục / trả HTTP response
  |
Worker thread
  |        [chờ queue] [bắt đầu] [đang xử lý I/O ..................]
  |                                                        [ghi DB]
  |                                                          [xong]
  |
  +-- Timeout của caller KHÔNG tự gửi interrupt cho worker ----------+
```

Hai dòng thời gian **độc lập**:

- `get(timeout)` kết thúc việc **chờ kết quả** khi hết hạn.
- Task đã giao cho executor có thể vẫn **QUEUED** hoặc **RUNNING**.
- Worker có thể hoàn thành bình thường ngay sau lúc caller nhận `TimeoutException`.
- Task có thể thất bại sau timeout và không ai quan sát exception nếu hệ thống bỏ quên handle.
- Một task có thể đã tác động ra ngoài rồi, dù caller cho rằng request “thất bại”.

Vì vậy, phản hồi chính xác nên là **“đã hết thời gian chờ kết quả”**, không tự động là **“đã hủy công việc”** hoặc **“giao dịch không xảy ra”**.

## 2. Chính xác Future.get(timeout) bảo đảm điều gì?

API JDK:

```java
V get(long timeout, TimeUnit unit)
        throws InterruptedException,
               ExecutionException,
               TimeoutException;
```

Trên một `Future<V>`, lời gọi này **chờ tối đa khoảng thời gian được yêu cầu** để phép tính hoàn tất. Các khả năng:

| Kết quả từ `get(timeout)` | Ý nghĩa chắc chắn | Điều không nên suy ra |
| --- | --- | --- |
| Trả về giá trị `V` | Tính toán hoàn thành bình thường theo hợp đồng của Future | Mọi side effect bên ngoài đã durable nếu code chưa bảo đảm |
| `TimeoutException` | Không nhận được kết quả trong thời gian chờ | Task đã hủy/đã dừng/đã rollback |
| `ExecutionException` | Tác vụ hoàn tất ngoại lệ; exception gốc nằm trong `getCause()` | Task chưa từng thực hiện side effect |
| `InterruptedException` | **Thread đang chờ `get`** bị interrupt khi chờ | Worker đã tự động bị interrupt hoặc dừng |
| `CancellationException` | Future đã bị hủy theo trạng thái Future | Worker đã chắc chắn ngừng ngay tức khắc |

`Future.get()` không có timeout chờ cho đến khi kết quả sẵn có hoặc đường lỗi/interruption xảy ra. `Future.get(timeout, unit)` thay đổi **giới hạn đợi**, không thêm khả năng “kill task”.

**Lưu ý về timeout:** thời gian được tính cho bước chờ trên caller, không phải deadline thực thi của nghiệp vụ. Nếu task chờ trong executor queue 90 ms rồi bắt đầu chạy, `get(100ms)` có thể chỉ còn rất ít thời gian để thấy kết quả. Nếu task đã chạy 10 phút trước khi caller gọi `get(100ms)`, lệnh này chỉ chờ thêm tối đa khoảng 100 ms tại thời điểm gọi.

`get` là thao tác blocking. Nếu bị gọi ngay trên HTTP request thread, request thread có thể bị chiếm suốt khoảng timeout. Hãy chọn mô hình trả `CompletableFuture` trực tiếp, polling job status hoặc async HTTP response khi phù hợp.

### Ba trạng thái không giống nhau

```text
Caller wait state:  WAITING --timeout--> NOT_WAITING
Future state:       PENDING -----------→ PENDING / SUCCESS / FAILURE / CANCELLED
Worker state:       QUEUED ------------→ RUNNING --------→ TERMINATED
```

**Không có mũi tên tự động từ `TimeoutException` sang `CANCELLED`**. Chỉ có code chủ động hủy hoặc chính sách hệ thống khác mới có thể phát tín hiệu hủy, và ngay cả khi yêu cầu hủy đã được ghi nhận thì worker có thể không dừng tức thì.

## 3. Ví dụ Java 17 chạy độc lập: timeout rồi task vẫn hoàn thành

Để chứng minh mà không phụ thuộc tốc độ máy hay thread scheduler, hãy dùng `CountDownLatch`. Worker bắt đầu rồi đợi một latch; caller đợi `Future.get(50, MILLISECONDS)`. Vì latch **chưa được mở**, worker không thể hoàn tất trước timeout.

Tạo tệp **TimeoutDoesNotStopDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutDoesNotStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        AtomicBoolean businessEffect = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                allowFinish.await(); // Cố ý chưa cho worker hoàn tất
                businessEffect.set(true);
                return "report-saved";
            });

            started.await(); // Bảo đảm task đã bắt đầu

            try {
                future.get(50, TimeUnit.MILLISECONDS);
                throw new AssertionError("Task should still be waiting");
            } catch (TimeoutException expected) {
                System.out.println("wait timed out");
            }

            System.out.println("future done after timeout: "
                    + future.isDone());
            System.out.println("effect after timeout: "
                    + businessEffect.get());

            allowFinish.countDown(); // Worker giờ mới được hoàn tất
            System.out.println("later result: " + future.get());
            System.out.println("effect after release: "
                    + businessEffect.get());
        } finally {
            allowFinish.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TimeoutDoesNotStopDemo.java
java TimeoutDoesNotStopDemo
```

**Stdout xác định khi chương trình chạy bình thường:**

```text
wait timed out
future done after timeout: false
effect after timeout: false
later result: report-saved
effect after release: true
```

Giải thích từng bước:

1. `pool.submit` **chấp nhận** callable và trả về `Future<String>`, không đợi công việc hoàn tất.
2. `started.await()` chứng minh worker đã vào task; worker chờ `allowFinish.await()`. Đây là điểm đồng bộ có chủ đích, không phải giả định “ngủ 50 ms là đủ”.
3. `future.get(50, MILLISECONDS)` không có cách nhận result khi latch đang đóng, nên ném `TimeoutException`.
4. `Future.isDone()` vẫn `false` và cờ nghiệp vụ vẫn `false` vì worker chưa tới phần ghi kết quả.
5. Caller mở latch; **cùng task trước đó tiếp tục xử lý**, đặt cờ rồi trả `report-saved`.
6. `future.get()` lần hai nhận kết quả thành công. Không có task thứ hai nào được tạo bởi lần gọi `get` này.

**Không được suy từ demo rằng cứ timeout là `isDone() == false`.** Trong hệ thống thực, worker có thể hoàn tất **ngay sau** thời điểm `get` ném `TimeoutException` nhưng **trước** khi caller đọc `isDone()`, nên lần đọc có thể là `true`. Latch trong ví dụ cố ý loại bỏ race để cho thấy cơ chế.

Cờ `businessEffect` chỉ mô phỏng tác động trong bộ nhớ, không chứng minh database commit hay hệ thống bên ngoài đã thực hiện. Bài học là **quyền tiếp tục chạy của worker không biến mất vì caller dừng đợi**.

## 4. `get(timeout)`, `cancel(...)` và interrupt là ba thao tác khác nhau

Sau khi bắt `TimeoutException`, code có thể quyết định **không hủy** hoặc **yêu cầu hủy**. Lựa chọn này thuộc về chính sách nghiệp vụ.

```java
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Không có cancel tự động tại đây.
    // Nếu nghiệp vụ cho phép hủy:
    boolean requested = future.cancel(true);
    throw e;
}
```

Đây là **fragment**, không phải class độc lập: `future` phải được khởi tạo và method/caller phải khai báo hoặc xử lý exception. Quan trọng là dòng `future.cancel(true)` **do lập trình viên viết thêm**, không phải hành vi nằm bên trong `get(timeout)`.

### 4.1. `cancel(false)`

Đối với `FutureTask`/nhiều task do `ExecutorService.submit` tạo, `cancel(false)` có thể đánh dấu Future là **cancelled** mà **không phát interrupt** tới worker. Nếu task đang chạy, code có thể vẫn tiếp tục side effect dù người gọi nhìn thấy `future.isCancelled() == true`. Không được mô tả `cancel(false)` như một lệnh “dừng chắc chắn nếu chưa chạy và đợi chạy xong nếu đã chạy”.

### 4.2. `cancel(true)`

Với `FutureTask` chạy trong `ThreadPoolExecutor` thông thường, `cancel(true)` **cố yêu cầu interrupt** thread đang thực hiện task. Nhưng:

- Task có thể đã hoàn tất trước khi gọi cancel; khi đó `cancel` trả `false`.
- Nếu task đang chờ queue, cancellation có thể làm nó không cần chạy; việc xóa phần tử đã cancel khỏi queue phụ thuộc executor và chính sách cleanup.
- Nếu task đang chạy, interrupt là **tín hiệu hợp tác**, không phải cưỡng bức dừng JVM thread.
- `Thread.sleep`, `Object.wait`, `CountDownLatch.await` và nhiều blocking method của JDK có thể ném `InterruptedException`.
- Tác vụ CPU vòng lặp không kiểm tra trạng thái interrupt có thể tiếp tục chạy.
- Một số I/O/SDK không phản ứng với interrupt hoặc đã gửi tác động ra ngoài trước khi tín hiệu đến.
- `isCancelled() == true` và `isDone() == true` phản ánh trạng thái Future; **không phải bằng chứng worker vật lý đã chết hoặc mọi side effect đã hoàn tác**.

### 4.3. `Thread.interrupt()` không phải `Thread.stop()`

`Thread.interrupt()` đặt cờ interrupt hoặc khiến một blocking operation hỗ trợ interrupt ném `InterruptedException`. Nó không cưỡng chế hủy thread và không rollback transaction ở hệ thống khác.

`Thread.stop()` đã bị deprecated vì không an toàn; không sử dụng để “chữa timeout”. Cách đúng là **cooperative cancellation**: code định kỳ kiểm tra cờ, cấu hình timeout ở các API blocking, giải phóng tài nguyên trong `finally` và không bắt rồi nuốt interrupt.

## 5. Java 17 runnable: cancel(true) chỉ phát yêu cầu interrupt có hợp tác

Ví dụ này dùng một task cố ý chờ trên `CountDownLatch`, một operation **interruptible**. Chỉ khi worker nhận interrupt và chạy nhánh `catch`, ta mới có bằng chứng task đã quan sát tín hiệu.

Lưu thành **CooperativeCancelDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch observedInterrupt = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException ex) {
                    observedInterrupt.countDown();
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            boolean requested = future.cancel(true);
            observedInterrupt.await();

            System.out.println("cancel requested: " + requested);
            System.out.println("future cancelled: "
                    + future.isCancelled());
            System.out.println("worker observed interrupt: true");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CooperativeCancelDemo.java
java CooperativeCancelDemo
```

**Stdout trong điều kiện demo bình thường:**

```text
cancel requested: true
future cancelled: true
worker observed interrupt: true
```

`started.await()` bảo đảm callable đã vào phần chờ trước khi main gọi `cancel(true)`. Trong executor mặc định này, `FutureTask` gửi interrupt tới runner. Khi `CountDownLatch.await()` bị interrupt, worker chạy `catch` và đánh dấu `observedInterrupt`; main chờ latch đó trước khi in. Vì vậy **không in “observed” chỉ dựa vào `isCancelled()`**.

Lưu ý demo **cố ý hợp tác với interrupt**. Nếu thay `neverReleased.await()` bằng một lời gọi thư viện không hỗ trợ interrupt, hoặc một vòng CPU vô hạn bỏ qua cờ interrupt, kết quả “worker observed interrupt” không còn được bảo đảm. Trong production nên tránh chờ vô hạn khi kiểm thử và thêm deadline/timeout test phù hợp.

### 5.1. Xử lý InterruptedException thế nào?

Code hay gặp:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    // Bắt rồi bỏ qua là nguy hiểm.
}
```

Nếu có thể truyền exception lên, cho method khai báo `throws InterruptedException`. Nếu phải bắt và không thể ném lại exception cùng loại, thường cần:

```java
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Dọn tài nguyên / ghi nhận trạng thái hủy phù hợp.
    return;
}
```

Đây là fragment nằm trong một method có return type phù hợp. **Khôi phục cờ interrupt** giúp tầng trên nhận thấy tín hiệu đã có; sau đó không tiếp tục chạy những side effect không cần thiết. Không biến mọi interrupt thành “nghiệp vụ thất bại vĩnh viễn” nếu đó là yêu cầu shutdown hợp lệ.

## 6. `CompletableFuture`: timeout/cancel còn có giới hạn riêng

`CompletableFuture` vừa triển khai `Future`, vừa là `CompletionStage`. Nó có các API timeout tiện dụng từ Java 9 trở lên, nhưng **không tự dừng supplier/worker bên dưới**.

| Cách dùng | Tác động lên việc chờ/trạng thái Future | Có tự interrupt worker không? |
| --- | --- | --- |
| `cf.get(100, MILLISECONDS)` | Caller chờ tối đa 100 ms; có thể ném `TimeoutException` | **Không** |
| `cf.orTimeout(100, MILLISECONDS)` | Sắp xếp để **chính cf** hoàn tất ngoại lệ `TimeoutException` nếu chưa xong khi tới hạn | **Không** |
| `cf.completeOnTimeout(fallback, 100, MILLISECONDS)` | Sắp xếp để **chính cf** hoàn tất bình thường bằng fallback nếu chưa xong | **Không** |
| `cf.cancel(true)` | Hoàn tất `cf` theo trạng thái cancellation nếu còn có thể | Với implementation `CompletableFuture` của JDK: **không** |
| `futureTask.cancel(true)` | Yêu cầu hủy FutureTask; có thể gửi interrupt runner | **Có thể gửi**, nhưng dừng là best effort |

Javadoc `CompletableFuture.cancel(boolean)` nói rõ `mayInterruptIfRunning` **không có tác dụng trong implementation này**, vì `CompletableFuture` không dùng interrupt để điều khiển xử lý. Đây là khác biệt quan trọng so với `FutureTask` từ `ExecutorService.submit(...)`.

### 6.1. `orTimeout` là “hết hạn kết quả”, không phải “dừng supplier”

```java
CompletableFuture<String> cf =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor);

cf.orTimeout(100, TimeUnit.MILLISECONDS);
```

Đây là fragment; `callSlowService` và `executor` phải tồn tại. Nếu supplier chưa xong sau 100 ms, `cf` được hoàn tất ngoại lệ vì timeout. **Supplier bên dưới vẫn có thể chạy và gây tác động ngoài**. Khi nó về kết quả muộn, nó không thể thay giá trị `cf` đã hoàn tất ngoại lệ.

Hệ quả: `cf.get()` sau đó có thể ném `ExecutionException` với cause là `TimeoutException`; khác với việc `get(100, MILLISECONDS)` trực tiếp ném `TimeoutException` do caller chờ quá hạn.

### 6.2. `completeOnTimeout` có thể che kết quả muộn

```java
CompletableFuture<String> cf =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor)
                .completeOnTimeout("cached-fallback", 100,
                        TimeUnit.MILLISECONDS);
```

Khi hết hạn, caller có thể thấy `"cached-fallback"` như một **giá trị kết quả thành công của Future**, nhưng supplier gốc chưa chắc dừng. Nếu supplier đang ghi dữ liệu, kết quả muộn vẫn có thể gây side effect. Do đó **không dùng fallback completion làm bằng chứng nghiệp vụ gốc đã được hủy**.

Một fallback hợp lệ phải được thiết kế theo domain: trả dữ liệu cache cũ cho read-only query có thể chấp nhận; “thu tiền thất bại nên thử lại” khi provider chưa xác định trạng thái là nguy hiểm.

### 6.3. Ví dụ mini về sự khác nhau của hai timeout

```java
CompletableFuture<String> pending = new CompletableFuture<>();
try {
    pending.get(10, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    System.out.println("caller timed out");
}
System.out.println("still pending: " + !pending.isDone());
```

Đây là **fragment** yêu cầu imports JDK. Vì `pending` không được hoàn tất bởi thread nào, dòng cuối là `still pending: true`. Nếu thay bằng `pending.orTimeout(10, TimeUnit.MILLISECONDS)` rồi đợi stage, chính future đó sẽ chuyển sang trạng thái hoàn tất **ngoại lệ**, nhưng không có worker nào bị ngắt vì ví dụ không hề có worker.

**Quy tắc nhớ:** `get(timeout)` là **timeout của phép đợi**, `orTimeout` là **timeout của kết quả Future**, cả hai khác với **timeout của operation thật**.

## 7. Bốn lớp timeout trong ứng dụng Spring

Đừng dùng một giá trị `1000 ms` rồi nghĩ nó kiểm soát được mọi thứ. Thường có ít nhất bốn lớp:

| Lớp | Ví dụ | Tài nguyên chịu tác động | Sau timeout điều gì có thể còn chạy? |
| --- | --- | --- | --- |
| HTTP client timeout | Client chờ response quá hạn | Phía client/người gọi | Server vẫn có thể xử lý request/job |
| HTTP async request timeout | Servlet async/MVC `DeferredResult`/`WebAsyncTask` | Vòng đời HTTP response | Work nền có thể tiếp tục nếu không nối cancellation |
| Future wait timeout | `future.get(200, MILLISECONDS)` | Thread đang chờ | Future task vẫn queued/running |
| Dependency operation timeout | JDBC query timeout, HTTP connect/read/response timeout | Lời gọi I/O cụ thể | Có thể còn logic cleanup/retry; tác động đã gửi có thể vẫn xảy ra |
| Job business deadline | Deadline kiểm tra trong worker/job store | Trạng thái và chính sách nghiệp vụ | Bước đã bắt đầu có thể cần reconciliation/compensation |

**Chúng không tự động kế thừa nhau.** HTTP client đóng kết nối không bảo đảm Spring chủ động hủy worker; `Future.get(timeout)` cũng không tự gắn timeout cho JDBC query hay HTTP client bên trong worker.

### 7.1. Nếu có HTTP request deadline

Một API được khách hàng chờ tối đa 2 giây không có nghĩa báo cáo 30 giây phải bị giết ở giây thứ hai. Có hai thiết kế khác nhau:

- **Xử lý đồng bộ có deadline:** giới hạn bước I/O, trả lỗi timeout theo hợp đồng, quyết định có yêu cầu hủy và giải phóng tài nguyên hay không.
- **Xử lý nền:** xác nhận job được tiếp nhận, trả HTTP **202 Accepted + job ID** và cung cấp endpoint trạng thái. HTTP response kết thúc nhưng job có thể tiếp tục; không phải sự cố.

Điểm bắt buộc là **truyền thông chính xác cho client**, vì “hết thời gian chờ response” khác “không có job”, và “job đã nhận” khác “job đã hoàn thành”.

### 7.2. Transaction timeout khác Future timeout

Với Spring `@Transactional`, transaction thường gắn với thread thực thi và điều khiển bởi transaction manager. Một caller đợi `Future.get(timeout)` bị timeout **không tự rollback transaction đang chạy ở một worker khác**. Ngược lại, transaction timeout có thể khiến hoạt động DB thất bại tại một điểm kiểm tra nhất định, nhưng không giải quyết mọi tác động lên dịch vụ ngoài.

Đừng dựa vào interrupt để đảo một giao dịch đã commit. Với nghiệp vụ nhiều hệ thống, cần idempotency, transaction boundary và compensation/reconciliation riêng.

## 8. Spring Boot 3.x: minh họa endpoint hết hạn đợi nhưng worker tiếp tục

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, dependency `spring-boot-starter-web`. Nó minh họa rõ:

- `ThreadPoolTaskExecutor` nhận tác vụ nền.
- Controller đợi kết quả tối đa **100 ms**.
- Nếu controller hết hạn đợi, nó trả **202 Accepted** kèm ID để tra cứu, **không gọi `cancel`**.
- Worker được mô phỏng mất **600 ms**, tiếp tục cập nhật trạng thái trong `ConcurrentHashMap`.
- Đây chỉ là **demo in-memory**, không có job store bền vững hay bảo đảm xử lý sau crash.

Đặt toàn bộ code vào **src/main/java/com/example/demo/TimeoutApplication.java**:

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class TimeoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}

@Service
class JobStates {
    private final ConcurrentMap<String, String> states =
            new ConcurrentHashMap<>();

    void set(String id, String state) {
        states.put(id, state);
    }

    String get(String id) {
        return states.get(id);
    }

    void remove(String id) {
        states.remove(id);
    }
}

@Service
class ReportWorker {
    private final JobStates jobs;

    ReportWorker(JobStates jobs) {
        this.jobs = jobs;
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String jobId) {
        jobs.set(jobId, "RUNNING");
        try {
            Thread.sleep(600); // Chỉ mô phỏng I/O blocking.
            jobs.set(jobId, "SUCCEEDED");
            return CompletableFuture.completedFuture("report:" + jobId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            jobs.set(jobId, "FAILED");
            return CompletableFuture.failedFuture(ex);
        }
    }
}

@RestController
class JobController {
    private final ReportWorker worker;
    private final JobStates jobs;

    JobController(ReportWorker worker, JobStates jobs) {
        this.worker = worker;
        this.jobs = jobs;
    }

    @PostMapping("/jobs")
    public ResponseEntity<?> submit() {
        String id = UUID.randomUUID().toString();
        jobs.set(id, "QUEUED");

        final CompletableFuture<String> result;
        try {
            result = worker.generate(id);
        } catch (TaskRejectedException rejected) {
            jobs.remove(id);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "executor_overloaded"));
        }

        try {
            String report = result.get(100, TimeUnit.MILLISECONDS);
            return ResponseEntity.ok(
                    Map.of("jobId", id, "state", "SUCCEEDED",
                            "result", report));
        } catch (TimeoutException timeout) {
            // Không gọi result.cancel(): worker vẫn có thể chạy.
            return ResponseEntity.accepted()
                    .location(URI.create("/jobs/" + id))
                    .body(Map.of("jobId", id, "state", "PROCESSING",
                            "statusUrl", "/jobs/" + id));
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("jobId", id, "error", "caller_interrupted"));
        } catch (ExecutionException failed) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("jobId", id, "error", "worker_failed"));
        }
    }

    @GetMapping("/jobs/{id}")
    public ResponseEntity<?> status(@PathVariable String id) {
        String state = jobs.get(id);
        if (state == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of("jobId", id, "state", state));
    }
}
```

Chạy bằng công cụ build Spring Boot của dự án:

```bash
./gradlew bootRun
curl -i -X POST http://localhost:8080/jobs
```

Trên Windows có thể dùng `gradlew.bat bootRun`. Vì worker giả lập ngủ 600 ms, còn caller đợi 100 ms, khi pool nhận task và JVM/scheduler hoạt động bình thường, endpoint thường trả:

```http
HTTP/1.1 202 Accepted
Location: /jobs/<id>

{"jobId":"<id>","state":"PROCESSING","statusUrl":"/jobs/<id>"}
```

**`<id>` là ký hiệu cho một UUID mới thực tế**, không phải chuỗi response cố định. Với overload, có thể trả 503; với tác vụ hoàn tất đủ nhanh trước thời gian chờ có thể trả 200. Sau khi dùng job ID thật gọi `GET /jobs/{id}`, trạng thái có thể là `QUEUED`, `RUNNING`, rồi `SUCCEEDED` khi worker kết thúc.

Ví dụ không tự bảo đảm task hoàn tất sau 600 ms tuyệt đối: `Thread.sleep(600)` chỉ chặn worker ít nhất khoảng thời gian đó theo điều kiện thực thi; worker còn có thể phải chờ queue và scheduling. **Đó chính là lý do API không nên hứa thời điểm hoàn thành chỉ từ timeout của caller.**

### 8.1. Các dòng code then chốt

```java
String report = result.get(100, TimeUnit.MILLISECONDS);
```

Dòng này **đợi Future trên controller thread**, nhưng không hủy khi đợi hết hạn.

```java
catch (TimeoutException timeout) {
    return ResponseEntity.accepted()
            .location(URI.create("/jobs/" + id))
            .body(Map.of("jobId", id, "state", "PROCESSING"));
}
```

Đây là fragment rút gọn. Nó trả thông điệp chính xác rằng job vẫn được xử lý, không nói “đã thất bại”. Worker đã được gửi vào pool sẽ chạy độc lập cho tới khi hoàn tất hoặc gặp lỗi khác.

```java
@Async("reportExecutor")
public CompletableFuture<String> generate(String jobId) {
    // ...
}
```

`@Async` chỉ có hiệu lực khi lời gọi đi qua **Spring proxy** (ở ví dụ, controller gọi bean `ReportWorker` khác). Nếu code trong chính `ReportWorker` gọi `this.generate(id)`, self-invocation thường bỏ qua proxy trong mode mặc định; khi đó không còn ranh giới executor như thiết kế.

### 8.2. Giới hạn bảo đảm của ví dụ Spring

Đây là bài demo, không phải nền tảng job production:

- `JobStates` là `ConcurrentHashMap` **trong RAM**, chỉ dùng trên một instance. Restart/crash làm mất trạng thái và task chưa hoàn tất; multi-replica không chia sẻ job.
- HTTP 202 trong demo chỉ xác nhận task được chấp nhận vào executor theo policy hiện tại, **không cam kết durable delivery**.
- Nếu request thread bị interrupt thay vì timeout, trạng thái job vẫn có thể tiếp tục được worker cập nhật. Cần chính sách cancel rõ ràng nếu muốn hủy.
- Worker chỉ mô phỏng việc xử lý bằng `sleep`; `SUCCEEDED` là thành công của demo chứ không chứng minh file báo cáo đã được lưu.
- `ThreadPoolTaskExecutor` cần sizing core/max/queue/rejection phù hợp, và nên quan sát số task accepted/completed/failed/rejected.
- Trong API thực, polling trạng thái cần authorization, retention/TTL, idempotency key và phương án phục hồi job stuck.

**Một ngoại lệ khác:** Một custom `RejectedExecutionHandler` như `CallerRunsPolicy` có thể khiến task chạy ngay trên caller khi pool quá tải. `@Async` không bảo đảm request thread luôn được trả lại nhanh trong mọi cấu hình; hãy hiểu policy executor đang sử dụng.

## 9. Nếu thực sự muốn dừng tác vụ sau timeout

Việc dừng yêu cầu thiết kế ở **nhiều cấp độ**, không chỉ thêm `get(timeout)`:

1. **Xác định có được hủy không.** Một thao tác gửi email best-effort có thể hủy trước khi gửi, nhưng xử lý thanh toán đã đến provider có thể phải đối soát trước khi đánh dấu hủy.
2. **Giữ handle tới task có thể yêu cầu cancel.** Với `ExecutorService.submit` là `Future` có thể gọi `cancel(true)`; với `CompletableFuture`, `cancel(true)` không tự interrupt supplier.
3. **Task hợp tác.** Kiểm tra cờ interrupt/deadline ở những điểm an toàn, thoát sớm khi phù hợp và cleanup trong `finally`.
4. **Đặt timeout cho từng blocking operation.** HTTP client connect/read timeout, JDBC query timeout, lock acquisition timeout hoặc các API theo deadline thực tế.
5. **Giảm rủi ro side effect một phần.** Ghi nhận idempotency key, transaction boundary, trạng thái trung gian và chương trình reconciliation.
6. **Phân biệt requested cancellation với confirmed stop.** Có thể có `CANCEL_REQUESTED` rồi `CANCELLED` chỉ khi worker xác nhận đã dừng ở điểm an toàn, hoặc `COMPLETED_AFTER_CANCEL_REQUEST` nếu không thể ngăn side effect.
7. **Theo dõi job còn chạy sau caller timeout.** Cần metric, log correlation ID, job store và công cụ vận hành.

### 9.1. Mẫu cooperative deadline trong task CPU-bound

Đây là một **fragment** minh họa sử dụng deadline dựa trên `System.nanoTime()`:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

for (WorkItem item : items) {
    if (Thread.currentThread().isInterrupted()) {
        throw new CancellationException("Interrupted");
    }
    if (System.nanoTime() - deadline >= 0) {
        throw new TimeoutException("Job deadline reached");
    }
    processOneItem(item);
}
```

Đoạn này không phải chương trình biên dịch độc lập: `WorkItem`, `items` và `processOneItem` cần được khai báo; method phải xử lý/kê khai `TimeoutException` và import các lớp `TimeUnit`, `CancellationException`. `System.nanoTime()` thích hợp đo **khoảng thời gian** hơn đồng hồ wall-clock khi tính deadline.

**Caveat:** kiểm tra deadline giữa các item chỉ có hiệu lực khi `processOneItem` trả quyền điều khiển. Nếu một lời gọi JDBC/HTTP blocking mắc kẹt, deadline trong vòng lặp không tự giải phóng worker. Phải đặt timeout ở thư viện I/O bên dưới.

### 9.2. Nếu task đang gọi hệ thống ngoài

Giả sử worker gọi cổng thanh toán, caller `get(1, SECONDS)` timeout. **Không kết luận giao dịch thất bại**. Có thể provider đã thực hiện request nhưng response bị mất. Nếu retry tạo transaction mới, có rủi ro thu tiền hai lần.

Thiết kế an toàn hơn:

- Dùng **idempotency key** ổn định cho yêu cầu logic.
- Query trạng thái cuối từ provider bằng transaction/reference ID.
- Chỉ đánh dấu `FAILED`/`SUCCEEDED` khi có chứng cứ theo hợp đồng.
- Nếu trạng thái không chắc chắn, ghi `UNKNOWN` hoặc `RECONCILING` thay vì đoán.
- Hạn chế retry, thêm backoff/jitter và tránh lặp side effect không idempotent.

Đây là lý do cancellation là **quyết định nghiệp vụ có tác động**, không phải một lệnh kỹ thuật tùy tiện trong mọi `catch (TimeoutException)`.

## 10. Hết thời gian chờ không đồng nghĩa task đã hỏng

Một task có thể rơi vào nhiều trạng thái khi caller dừng chờ:

| Lúc caller timeout | Điều có thể xảy ra tiếp | Hành động theo nhu cầu |
| --- | --- | --- |
| Task còn trong queue | Worker có thể lấy và chạy muộn | Poll status, deadline check trước khi bắt đầu |
| Task đang CPU-bound | Tiếp tục tính toán | Cooperative interrupt/deadline |
| Task đang đợi DB connection | Tiếp tục chờ tới khi có connection/timeout | Đặt timeout cho acquire/query; giới hạn concurrency |
| Task đang chờ API ngoài | Request có thể vẫn đi đến provider | Timeout client phù hợp, idempotency/reconciliation |
| Task vừa hoàn tất bình thường | `Future.isDone()` có thể chuyển true ngay sau timeout | Đọc lại result nếu contract cho phép, tránh tạo job trùng |
| Task đã lỗi trong worker | Future có thể hoàn tất ngoại lệ sau khi caller bỏ chờ | Quan sát Future callback/metrics/status |
| Task đã được yêu cầu cancel | Future có thể cancelled trước khi worker thực sự dừng | Theo dõi xác nhận từ worker |
| Application đang shutdown | Queue/task có thể bị gián đoạn theo lifecycle | Graceful shutdown và durable job processing |

Đừng tự gán trạng thái job `FAILED` khi chỉ có `TimeoutException` của **caller**; nếu cần một trạng thái, hãy dùng `WAIT_TIMEOUT` cho request/wait attempt, vẫn giữ job là `QUEUED`/`RUNNING`/`UNKNOWN` tùy sự thật.

## 11. Race condition khi cancel, kiểm tra trạng thái và retry

### 11.1. Race giữa timeout và completion

```text
T1: future.get(timeout) ném TimeoutException
T2: worker hoàn tất thành công
T1: kiểm tra future.isDone() -> true
```

Không mâu thuẫn: timeout chỉ mô tả tình trạng chưa có kết quả **trước mốc chờ**, còn kết quả có thể đến ngay sau đó. `isDone()` là một snapshot tại thời điểm đọc, không phải chứng cứ worker ở trạng thái đó lúc `get` vừa ném exception.

### 11.2. Race giữa cancel(true) và task hoàn tất

`Future.cancel(true)` trả `false` nếu task đã hoàn tất hoặc không thể hủy theo state machine. Nó có thể trả `true` trước khi worker kịp xử lý interrupt. Do đó, **giá trị return chỉ là kết quả yêu cầu cancellation ở cấp Future**, không phải thời điểm chính xác side effect đã dừng.

### 11.3. Retry sau HTTP timeout

Client không nhận response có thể gửi lại cùng request trong khi server đã nhận task lần đầu. Nếu thiếu request ID/idempotency key, cả hai job có thể chạy và cùng tạo side effect. Hệ thống nên lưu key cùng request hash, có unique constraint và trả lại job ID cũ nếu payload trùng.

### 11.4. Task hoàn tất sau khi request kết thúc

HTTP request-scoped objects, security context, MDC hoặc transaction của request thread có thể **không còn hiệu lực** khi worker tiếp tục. Không giữ tham chiếu mutable tới request/response để dùng sau timeout; truyền dữ liệu tối thiểu và có kiểm soát vào job, mở transaction mới khi cần và cleanup thread-local ở worker pool.

## 12. Phân biệt các API timeout/cancellation dễ nhầm

| API | Tác dụng chính | Điểm cần nhớ |
| --- | --- | --- |
| `Future.get(timeout, unit)` | Giới hạn thời gian chờ của **caller** | Không tự gọi cancel |
| `Future.cancel(true)` | Yêu cầu cancellation, có thể interrupt runner tùy implementation | Không bảo đảm ngừng side effect |
| `CompletableFuture.orTimeout(...)` | Đặt thời hạn kết quả của **CompletableFuture** | Không interrupt supplier |
| `CompletableFuture.completeOnTimeout(...)` | Hoàn tất CF bằng fallback nếu chưa xong | Work bên dưới vẫn có thể tiếp tục |
| `ExecutorService.invokeAll(tasks, timeout, unit)` | Chờ batch trong thời hạn; API **có cơ chế cancel các task chưa hoàn tất** khi hết hạn | Không giống `Future.get(timeout)`, nhưng cancellation vẫn best effort |
| `ExecutorService.shutdown()` | Ngừng nhận task mới, xử lý task đã gửi theo executor | Không phải hủy mọi task |
| `ExecutorService.shutdownNow()` | Cố dừng task đang chạy và trả task chưa bắt đầu | Dùng interrupt best effort; không ép dừng |
| `ExecutorService.awaitTermination(...)` | Chờ executor kết thúc tối đa khoảng thời gian | Không tự gửi cancel nếu chỉ đợi hết hạn |
| HTTP client read timeout | Giới hạn thời gian chờ I/O ở client | Server/provider có thể đã xử lý |
| Spring MVC async request timeout | Giới hạn vòng đời async HTTP response | Không tự bảo đảm background job dừng |

Điểm quan trọng: **không được đánh đồng tên cùng chứa “timeout”**. Có API giới hạn chờ, API hoàn tất trạng thái Future, API timeout I/O và API có hành vi cancellation riêng.

## 13. Lựa chọn kiến trúc khi công việc có thể lâu hơn request timeout

Nếu tạo báo cáo mất 30 giây nhưng reverse proxy cho phép HTTP request tối đa 5 giây, thay vì cho request gọi `get(5, SECONDS)` rồi báo lỗi mơ hồ, có thể dùng giao thức job nền:

```text
POST /jobs + Idempotency-Key
    |
    v
Xác thực, kiểm tra đầu vào
    |
    v
Ghi job vào DB / queue bền vững, commit
    |
    v
HTTP 202 + jobId + statusUrl
    |
    v
Worker riêng xử lý, retry theo chính sách
    |
    v
RUNNING → SUCCEEDED / FAILED / CANCELLED / RECONCILING
    |
    v
GET /jobs/{jobId} hoặc webhook để lấy kết quả cuối
```

**Lợi ích:**

- HTTP client không cần giữ một kết nối chờ toàn bộ xử lý.
- Job có trạng thái và ID độc lập với HTTP request.
- Mức độ bền vững tùy job store/queue đã chọn, không phụ thuộc RAM của một process.
- Client có thể retry request bằng idempotency key mà không tạo thêm job logic.
- Worker có thể xử lý retry, crash recovery và dead-letter riêng.
- Nếu muốn hủy, API `POST /jobs/{id}/cancel` có thể ghi `CANCEL_REQUESTED` và để worker xác nhận an toàn.

**Không hứa exactly-once side effects chỉ vì dùng queue.** Message broker có thể phát lại, nên worker cần idempotency và cơ chế reconciliation. 202 sau khi commit job bền vững là lời xác nhận **đã tiếp nhận bền vững**, không phải “nghiệp vụ xong”.

## 14. Các lỗi thường gặp

**Lỗi 1 — Bắt `TimeoutException` rồi ghi log “Task cancelled”.** Sai nếu không có yêu cầu hủy và xác nhận worker dừng. Chỉ biết caller hết thời gian chờ.

**Lỗi 2 — Đặt `get(100ms)` và nghĩ JDBC query cũng có timeout 100 ms.** Query có deadline riêng; cần cấu hình driver/query/transaction đúng.

**Lỗi 3 — Nghĩ Future chưa xong sau timeout sẽ bị GC và ngừng chạy.** Task đã được executor giữ và worker có thể tiếp tục; việc bỏ tham chiếu Future của caller không hủy task.

**Lỗi 4 — Gọi `cancel(true)` rồi tin mọi tác động đã đảo ngược.** Interrupt không phải rollback HTTP, database đã commit hay message đã gửi.

**Lỗi 5 — Bắt `InterruptedException` rồi im lặng tiếp tục.** Dễ bỏ qua shutdown/cancellation, khiến task giữ resource và tạo side effect sau khi đã yêu cầu dừng.

**Lỗi 6 — Dùng `CompletableFuture.cancel(true)` để “ép interrupt” supplier.** Tham số boolean không có tác dụng interrupt trong implementation CF của JDK.

**Lỗi 7 — Dùng `orTimeout` mà nghĩ backend I/O được hủy.** Nó hoàn tất CF ngoại lệ, không tự dừng supplier gốc.

**Lỗi 8 — Dùng `completeOnTimeout` với fallback và tuyên bố nghiệp vụ gốc thành công/thất bại.** Fallback chỉ là kết quả của Future theo contract hiện tại; work nền vẫn có thể tạo tác động.

**Lỗi 9 — Retry vô hạn sau timeout trên cùng operation không idempotent.** Có thể phát sinh hai lần gửi email, tạo file hoặc thanh toán.

**Lỗi 10 — Không phân biệt thời gian xếp hàng và thời gian chạy.** `get(timeout)` có thể hết hạn vì task chưa có worker, không phải logic bên trong task bị treo.

**Lỗi 11 — Chờ `Future.get(timeout)` trên thread của single-thread executor rồi cần một task khác trên cùng pool để hoàn tất.** Có thể starvation/deadlock; timeout giới hạn thời gian bị kẹt nhưng không sửa thiết kế phụ thuộc vòng.

**Lỗi 12 — Chỉ nhìn `future.isCancelled()` để kết luận worker đã dừng.** Cancellation state và thực tế worker rời code có thể khác nhau.

**Lỗi 13 — Không quản lý task lỗi muộn.** Caller đã timeout nhưng worker ném exception sau đó; cần callback/metric/job store để quan sát kết quả cuối.

**Lỗi 14 — Gắn trạng thái `FAILED` lên job chỉ vì client đóng kết nối.** Client timeout là góc nhìn từ caller, không tự có nghĩa job không thể tiếp tục.

**Lỗi 15 — Không dọn executor.** Pool dùng chung phải có lifecycle shutdown; trong Spring nên khai báo executor bean có tên và để context quản lý.

## 15. Checklist triển khai timeout an toàn

- [ ] Xác định **timeout của ai**: HTTP client, request server, `Future.get`, dependency I/O hay deadline nghiệp vụ.
- [ ] Sau `TimeoutException`, **không tự nhận định task đã dừng**; cần giữ handle/job ID và quan sát trạng thái.
- [ ] Quyết định có được phép yêu cầu hủy không, và ai có quyền hủy.
- [ ] Nếu yêu cầu hủy bằng `Future.cancel(true)`, task có **cooperative interrupt handling** và timeout cho blocking I/O.
- [ ] Nếu dùng `CompletableFuture.orTimeout/completeOnTimeout`, biết chúng quản lý **completion state**, không dừng supplier.
- [ ] Đặt transaction/commit, timeout của HTTP/JDBC/downstream và chính sách retry rõ ràng.
- [ ] Tránh retry tác động không idempotent; dùng idempotency key và reconciliation.
- [ ] Không chuyển job sang `FAILED` hay `CANCELLED` chỉ vì caller hết thời gian chờ.
- [ ] Với task dài, ưu tiên job store bền vững + HTTP 202 + status endpoint nếu hợp đồng cần.
- [ ] Theo dõi job chạy sau timeout, worker active, queue age, task duration, cancellation requested/confirmed, success/failure.
- [ ] Kiểm thử bằng `CountDownLatch` để loại bỏ timing ngẫu nhiên; kiểm thử riêng timeout, cancel(false), cancel(true), interrupt và shutdown.
- [ ] Kiểm tra việc cleanup thread-local, resource và exception khi request kết thúc trước background job.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `future.get(1, TimeUnit.SECONDS)` ném `TimeoutException`. Worker có bị interrupt tự động không?

**Đáp án:** Không. Caller đã ngừng chờ kết quả trong giới hạn một giây; worker có thể đang chạy hoặc vẫn chờ queue.

**Câu 2.** Ngay sau `TimeoutException`, `future.isDone()` trả `true`. Có mâu thuẫn không?

**Đáp án:** Không. Task có thể vừa hoàn tất ngay sau mốc timeout nhưng trước lần đọc `isDone()`. Cần phân biệt thời điểm hai phép quan sát.

**Câu 3.** `cancel(true)` trả `true`. Có thể khẳng định giao dịch ngoài đã được rollback không?

**Đáp án:** Không. Cancellation cấp Future không chứng minh worker đã dừng mọi bước hoặc provider/DB đã hoàn tác tác động.

**Câu 4.** Vì sao `CompletableFuture.cancel(true)` không tương đương `FutureTask.cancel(true)`?

**Đáp án:** Implementation `CompletableFuture` không dùng interrupt để điều khiển thực thi; `mayInterruptIfRunning` không có tác dụng. FutureTask có thể gửi interrupt tới runner nhưng cũng chỉ là tín hiệu hợp tác.

**Câu 5.** `cf.orTimeout(500, MILLISECONDS)` có bảo đảm HTTP call nằm trong supplier kết thúc sau 500 ms không?

**Đáp án:** Không. Nó chỉ có thể hoàn tất CF ngoại lệ nếu chưa xong; HTTP call cần timeout/cancellation của HTTP client riêng.

**Câu 6.** Một report job được nhận, caller timeout, rồi client retry ngay. Nguy cơ lớn nhất là gì?

**Đáp án:** Job cũ vẫn có thể chạy; retry có thể sinh job mới và side effect trùng. Dùng idempotency key, job ID và truy vấn trạng thái trước khi tạo thêm việc.

**Câu 7.** Nếu code bắt `InterruptedException` trong worker thì nên làm gì?

**Đáp án:** Thường phải dọn resource, tôn trọng yêu cầu hủy, truyền exception lên hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()` nếu không truyền tiếp được; không im lặng tiếp tục nghiệp vụ.

**Câu 8.** `ExecutorService.invokeAll(tasks, timeout, unit)` có hoàn toàn giống gọi `get(timeout)` trên từng Future không?

**Đáp án:** Không. `invokeAll` có timeout có quy tắc cancellation cho các task chưa hoàn tất khi thời hạn hết; `get(timeout)` của một Future chỉ giới hạn caller wait.

**Câu 9.** Khi HTTP response đã trả “timeout”, Spring transaction trong background worker có tự rollback không?

**Đáp án:** Không chỉ vì response timeout. Transaction boundary và quy tắc rollback của worker riêng; còn side effect ở service ngoài cần cơ chế đối soát/compensation.

**Câu 10.** Bằng chứng nào mạnh hơn `future.isCancelled()` khi cần xác minh worker ngừng an toàn?

**Đáp án:** Có tín hiệu trạng thái do worker cập nhật sau khi rời bước xử lý/cleanup, hoặc job store phản ánh `CANCELLED` theo state machine đã định nghĩa, cùng log/metric và đối soát các side effect.

## Kết luận

**`Future.get(timeout)` giới hạn thời gian caller chờ kết quả, không tự hủy công việc nền.** `TimeoutException` của caller, `Future.cancel(...)` và worker thực sự dừng là ba sự kiện khác nhau.

- Muốn **hết chờ**: dùng `get(timeout)` hoặc cơ chế HTTP timeout phù hợp.
- Muốn **yêu cầu hủy**: cần gọi API cancellation và làm cho task/operation hợp tác với interrupt/deadline.
- Muốn **biết job hoàn thành hay chưa**: dùng result/status/exception có thể quan sát.
- Muốn **đảm bảo không mất hoặc không lặp side effect**: cần job store, idempotency, transaction boundary và reconciliation ở tầng nghiệp vụ.

Đừng biến timeout của một thread thành tuyên bố rằng công việc, giao dịch hay tác động bên ngoài đã biến mất.

## Tài liệu tham khảo

1. Java SE 17 — `Future` (timed get, cancellation, `isDone`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
2. Java SE 17 — `CompletableFuture` (timeouts, `cancel`, execution policies): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
3. Java SE 17 — `ExecutorService` (`invokeAll` timeout, shutdown): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
4. Java SE 17 — `Thread` (interrupt semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
5. Spring Framework — `@Async` and task execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
7. HTTP Semantics — status 202 Accepted: https://httpwg.org/specs/rfc9110.html#status.202
