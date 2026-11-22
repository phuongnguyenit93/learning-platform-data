# Submit Runnable, Callable và lấy kết quả qua Future

Trong Java 21, `ExecutorService` nhận tác vụ qua `submit()` và trả về một đối tượng `Future` để theo dõi quá trình thực thi. `Runnable` phù hợp với tác vụ không cần trả kết quả; `Callable<V>` phù hợp khi tác vụ cần trả về giá trị kiểu `V` hoặc có thể ném checked exception.

`Future` cho phép luồng gọi chờ kết quả, kiểm tra trạng thái, đặt thời hạn chờ và yêu cầu hủy tác vụ. Hiểu rõ sự khác nhau giữa `Runnable`, `Callable` và các overload của `submit()` giúp tránh chặn luồng không cần thiết và xử lý lỗi đúng cách.

## 1. ExecutorService và submit()

`ExecutorService` tách việc mô tả tác vụ khỏi cách thực thi tác vụ. Caller gửi một `Runnable` hoặc `Callable` cho executor; executor quyết định khi nào và trên thread nào tác vụ được chạy. Phương thức `submit()` trả về `Future` đại diện cho kết quả hoặc trạng thái hoàn tất của tác vụ đó.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

static void runTask() throws Exception {
    try (ExecutorService executor = Executors.newFixedThreadPool(4)) {
        Future<?> future = executor.submit(() -> saveOrder());

        // Chờ tác vụ kết thúc.
        future.get();
    }
}

static void saveOrder() {
    System.out.println("Order saved");
}
```

`submit()` trả về sau khi tác vụ được tiếp nhận để thực thi; tác vụ có thể bắt đầu trước hoặc sau khi caller nhận được `Future`. `future.get()` chờ cho đến khi tác vụ hoàn tất. Trong ví dụ, `try-with-resources` đóng executor khi ra khỏi khối và chờ các tác vụ đã gửi hoàn tất.

Khác với `execute(Runnable)`, `submit()` trả về `Future`. Dùng `execute()` khi chỉ cần giao tác vụ và không cần handle để chờ hoặc lấy trạng thái; dùng `submit()` khi cần theo dõi kết quả, trạng thái hủy hoặc lỗi thông qua `Future`.

## 2. Submit Runnable: tác vụ không trả kết quả

`Runnable` khai báo phương thức `run()` không có giá trị trả về và không khai báo checked exception. Dùng `submit(Runnable)` khi caller chỉ cần biết tác vụ đã hoàn tất hay chưa, hoặc cần quan sát lỗi qua `Future`.

```java
Runnable saveTask = () -> saveOrder();
Future<?> saveFuture = executor.submit(saveTask);

// get() trả về null nếu Runnable kết thúc bình thường.
saveFuture.get();
```

Trong thực tế, có thể chỉ gọi `saveFuture.get();` và bỏ qua giá trị trả về. Kiểu `Future<?>` phản ánh rằng tác vụ `Runnable` không cung cấp kết quả hữu ích; nếu tác vụ kết thúc bình thường, `get()` trả về `null`.

Overload `submit(Runnable task, T result)` cho phép gắn một giá trị kết quả cố định với tác vụ. `Future.get()` trả về giá trị đó sau khi `Runnable` hoàn tất bình thường:

```java
Future<String> auditFuture = executor.submit(
        () -> writeAuditLog(),
        "AUDIT_WRITTEN");

String status = auditFuture.get(); // "AUDIT_WRITTEN"
```

Giá trị `"AUDIT_WRITTEN"` không phải dữ liệu được tính từ `Runnable`; nó là giá trị caller cung cấp trước. Nếu cần kết quả được tính trong lúc chạy, dùng `Callable<T>`.

## 3. Submit Callable: tác vụ có kết quả

`Callable<V>` khai báo phương thức `call()` trả về một giá trị kiểu `V` và có thể ném checked exception. Đây là lựa chọn phù hợp khi cần nhận dữ liệu do tác vụ tính toán hoặc đọc được.

```java
import java.util.concurrent.Callable;
import java.util.concurrent.Future;

Callable<Integer> calculateTask = () -> calculateTotal();
Future<Integer> totalFuture = executor.submit(calculateTask);

Integer total = totalFuture.get();
System.out.println("Total = " + total);
```

Có thể truyền trực tiếp lambda trả về giá trị vào `submit()` khi ngữ cảnh kiểu xác định rõ overload `Callable<T>`. Khai báo biến `Callable<T>` trước cũng giúp mã dễ đọc hơn khi có nhiều overload hoặc lambda phức tạp.

`Callable` có thể ném checked exception mà không cần tự bọc trong `try/catch` bên trong lambda:

```java
Callable<String> loadTask = () -> loadFromDatabase();
Future<String> dataFuture = executor.submit(loadTask);

String data = dataFuture.get();
```

Nếu `loadFromDatabase()` ném exception, `get()` sẽ báo tác vụ thất bại bằng `ExecutionException`; exception gốc có thể lấy qua `getCause()`.

## 4. Ba overload submit() cần phân biệt

| Cách gọi | Kiểu trả về | Kết quả từ `Future.get()` khi thành công |
|---|---|---|
| `submit(Runnable task)` | `Future<?>` | `null` |
| `submit(Runnable task, T result)` | `Future<T>` | Giá trị `result` caller truyền vào |
| `submit(Callable<T> task)` | `Future<T>` | Giá trị do `call()` trả về |

Chọn overload theo dữ liệu cần nhận lại. Đừng dùng `submit(Runnable, result)` để mô phỏng một phép tính có kết quả nếu chính tác vụ có thể trả về kết quả bằng `Callable`.

## 5. Future.get() chờ kết quả

`get()` là thao tác blocking: caller dừng tại lời gọi cho đến khi tác vụ hoàn tất. Nếu tác vụ đã xong, kết quả được trả về ngay; nếu chưa, caller chờ.

```java
import java.util.concurrent.Callable;

Callable<Integer> task = () -> calculateTotal();
Future<Integer> future = executor.submit(task);

// Các công việc khác có thể thực hiện trước khi cần kết quả.
prepareResponseMetadata();

int total = future.get(); // Chỉ chờ tại thời điểm cần total.
```

Không nên gọi `get()` ngay sau mỗi `submit()` nếu mục tiêu là chạy nhiều tác vụ song song nhưng caller lại chờ từng tác vụ trước khi gửi tác vụ tiếp theo. Hãy gửi các tác vụ cần chạy độc lập trước, sau đó lấy kết quả khi cần.

`Future` không cung cấp callback hoàn tất. Nếu cần xử lý kết quả theo kiểu continuation mà không chặn caller, có thể cân nhắc `CompletableFuture` hoặc API bất đồng bộ phù hợp.

## 6. Chờ có thời hạn với get(timeout, unit)

Overload `get(long timeout, TimeUnit unit)` chỉ chờ tối đa thời gian chỉ định. Nếu hết thời gian mà tác vụ chưa hoàn tất, phương thức ném `TimeoutException`.

```java
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

Callable<String> task = () -> loadFromService();
Future<String> future = executor.submit(task);

try {
    String value = future.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException e) {
    System.out.println("Task has not completed within 2 seconds");
    // Tác vụ vẫn có thể tiếp tục chạy.
}
```

`TimeoutException` chỉ cho biết caller đã hết thời gian chờ. Nó không tự động hủy tác vụ. Nếu nghiệp vụ quyết định không cần kết quả nữa, caller có thể gọi `future.cancel(true)` hoặc áp dụng chính sách timeout riêng.

## 7. Hủy tác vụ bằng cancel()

`cancel(boolean mayInterruptIfRunning)` yêu cầu hủy tác vụ:

- `cancel(false)` không yêu cầu interrupt tác vụ đang chạy. Future có thể chuyển sang trạng thái cancelled trong khi phần code tác vụ vẫn tiếp tục chạy; nếu tác vụ chưa bắt đầu, executor sẽ không chạy nó.
- `cancel(true)` cho phép executor gửi interrupt đến thread đang chạy tác vụ nếu thread đã được xác định.
- Giá trị trả về `true` cho biết yêu cầu hủy được chấp nhận; `false` cho biết tác vụ không thể hủy theo trạng thái hiện tại, ví dụ đã hoàn tất hoặc đã bị hủy.
- Hủy bằng interrupt là hợp tác. Tác vụ cần sử dụng các thao tác blocking có hỗ trợ interrupt hoặc tự kiểm tra interrupt status.

```java
import java.util.concurrent.Callable;

Callable<String> task = () -> callRemoteService();
Future<String> future = executor.submit(task);

if (!future.isDone()) {
    boolean cancellationAccepted = future.cancel(true);
    System.out.println("Cancellation accepted: " + cancellationAccepted);
}

if (future.isCancelled()) {
    System.out.println("Task was cancelled");
}
```

Sau khi bị hủy, `get()` ném `CancellationException`. Không coi `cancel(true)` là bảo đảm tác vụ đã dừng ngay lập tức; code tác vụ có thể cần thời gian để nhận interrupt và dọn dẹp tài nguyên.

## 8. isDone() và isCancelled()

`Future` cung cấp hai phương thức kiểm tra trạng thái:

- `isDone()` trả về `true` khi tác vụ đã hoàn tất, kết thúc do exception hoặc đã bị hủy.
- `isCancelled()` trả về `true` nếu tác vụ đã bị hủy trước khi hoàn tất bình thường.

`isDone()` không đồng nghĩa tác vụ thành công. Muốn biết kết quả hoặc lỗi, hãy gọi `get()` và xử lý các exception tương ứng.

## 9. Xử lý InterruptedException và ExecutionException

`Future.get()` có thể ném ba exception quan trọng:

| Exception | Nguyên nhân | Cách xử lý |
|---|---|---|
| `InterruptedException` | Thread đang gọi `get()` bị interrupt trong lúc chờ | Dọn dẹp cần thiết; nếu không truyền exception lên caller, khôi phục interrupt status bằng `Thread.currentThread().interrupt()` |
| `ExecutionException` | Tác vụ kết thúc bằng exception | Kiểm tra `getCause()` để biết lỗi gốc |
| `CancellationException` | Future đã bị hủy | Xử lý theo luồng nghiệp vụ khi tác vụ không còn kết quả |

Ví dụ chuyển lỗi về caller:

```java
static int readTotal(Future<Integer> future) {
    try {
        return future.get();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Waiting for task was interrupted", e);
    } catch (java.util.concurrent.ExecutionException e) {
        throw new IllegalStateException("Task execution failed", e.getCause());
    }
}
```

`InterruptedException` nói về thread đang chờ, còn `ExecutionException` nói về lỗi xảy ra bên trong tác vụ. Hai trường hợp này cần được phân biệt để tránh nhầm lỗi của caller với lỗi của công việc nền.

## 10. Quản lý vòng đời ExecutorService

`ExecutorService` cần được đóng để ngừng nhận tác vụ mới và giải phóng tài nguyên thực thi. Trong Java 21, `ExecutorService` triển khai `AutoCloseable`, vì vậy có thể dùng `try-with-resources`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Callable;

static void executeAndCollect() throws Exception {
    try (ExecutorService executor = Executors.newFixedThreadPool(4)) {
        Future<?> save = executor.submit(() -> saveOrder());
        Callable<Integer> totalTask = () -> calculateTotal();
        Future<Integer> total = executor.submit(totalTask);
        Future<String> audit = executor.submit(() -> writeAuditLog(), "DONE");

        save.get();
        int amount = total.get();
        String auditStatus = audit.get();

        System.out.println(amount + " / " + auditStatus);
    }
}
```

Khi `close()` được gọi, executor ngừng nhận tác vụ mới và chờ các tác vụ đã được gửi hoàn tất theo cơ chế orderly shutdown. Nếu cần quản lý tường minh, `shutdown()` cũng ngừng nhận tác vụ mới nhưng cho phép tác vụ đã gửi chạy xong; `shutdownNow()` yêu cầu dừng các tác vụ đang chạy bằng interrupt và trả về các tác vụ chưa bắt đầu, nhưng không bảo đảm mọi tác vụ đều dừng tức thì.

## 11. Memory consistency khi dùng Future

Java Memory Model quy định quan hệ happens-before cho executor và future:

- Các hành động trong thread gửi tác vụ trước khi submit xảy ra-before các hành động của tác vụ đó.
- Các hành động trong tác vụ xảy ra-before các hành động tiếp theo sau khi thread khác lấy kết quả thành công qua `Future.get()`.

Vì vậy, `get()` vừa chờ kết quả vừa tạo điểm đồng bộ để caller quan sát các thay đổi mà tác vụ đã thực hiện trước khi hoàn tất. Không cần tự thêm cơ chế đồng bộ chỉ để truyền kết quả trả về qua `Future`; tuy nhiên, truy cập dữ liệu mutable được chia sẻ trong khi tác vụ vẫn đang chạy vẫn cần thiết kế đồng bộ phù hợp.

## 12. Dùng submit() với virtual-thread executor

Java 21 cung cấp `Executors.newVirtualThreadPerTaskExecutor()`. Executor này chạy mỗi tác vụ trên một virtual thread. Cách submit và lấy kết quả qua `Future` vẫn giống `ExecutorService` thông thường:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Callable;

static String loadWithVirtualThread() throws Exception {
    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        Callable<String> task = () -> loadFromService();
        Future<String> future = executor.submit(task);
        return future.get();
    }
}
```

Không tạo pool để tái sử dụng virtual thread. Nếu cần giới hạn số kết nối hoặc request đồng thời, hãy giới hạn tài nguyên đó bằng connection pool, semaphore hoặc backpressure thay vì giới hạn số virtual thread.

## 13. Chọn Runnable, Callable và Future

| Nhu cầu | Cách dùng |
|---|---|
| Chạy tác vụ không cần kết quả nhưng cần chờ hoàn tất hoặc phát hiện lỗi | `submit(Runnable)` và `Future<?>` |
| Chạy tác vụ không cần kết quả, nhưng muốn `get()` trả về một giá trị trạng thái cố định | `submit(Runnable, result)` |
| Tính hoặc tải một giá trị cần trả về caller | `submit(Callable<T>)` và `Future<T>` |
| Chờ tối đa một khoảng thời gian | `Future.get(timeout, unit)` |
| Yêu cầu hủy tác vụ | `Future.cancel(...)` và xử lý interrupt trong tác vụ |
| Xử lý nhiều tác vụ có thể blocking bằng virtual thread | `newVirtualThreadPerTaskExecutor()` cùng `submit()` |

## 14. Biên dịch với Java 21

Các API `ExecutorService`, `Runnable`, `Callable` và `Future` là API Java nền tảng. Trong Java 21, `ExecutorService` có thể dùng trực tiếp trong `try-with-resources`; không cần bật Preview.

```bash
javac --release 21 -d out src/FutureSubmitDemo.java
java -cp out FutureSubmitDemo
```

Đặt compiler release hoặc toolchain về Java 21 để kiểm tra mã nguồn theo đúng API mục tiêu. Không thêm `--enable-preview` cho các ví dụ trong bài.

## 15. Tài liệu tham khảo

- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 API — Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Runnable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html)
