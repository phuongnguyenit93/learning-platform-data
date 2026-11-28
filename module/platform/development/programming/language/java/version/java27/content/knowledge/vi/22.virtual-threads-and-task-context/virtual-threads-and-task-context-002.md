# Tạo virtual thread bằng builder và executor theo tác vụ trong Java 27

**Virtual thread** là một loại `Thread` được Java runtime quản lý, có chi phí tài nguyên thấp hơn nhiều trong những trường hợp điển hình so với việc tạo một platform thread riêng cho mỗi yêu cầu. Đây là nền tảng để tiếp tục viết code Java theo phong cách **một luồng thực thi tuần tự cho một tác vụ**, trong khi ứng dụng vẫn xử lý được rất nhiều tác vụ đang chờ I/O.

Trong **Java 27**, có hai cách tạo virtual thread rất đáng học:

1. **`Thread.ofVirtual()` và `Thread.Builder.OfVirtual`** — trực tiếp tạo một virtual thread, đặt tên, cấu hình và chủ động `start()`/`join()`.
2. **`Executors.newVirtualThreadPerTaskExecutor()`** — nhận các tác vụ và tạo **virtual thread mới cho mỗi tác vụ**, tích hợp `Future`, `submit`, `invokeAll` và vòng đời `ExecutorService`.

Bài học thuộc chương **Virtual threads và ngữ cảnh tác vụ** của module **Java 27 và các kiến thức liên quan**. Mọi ví dụ chính sử dụng API chuẩn đã ổn định, không cần `--enable-preview`. Trọng tâm là tạo, quản lý và chọn cách thực thi, không chỉ đơn giản gọi được phương thức.

## 1. Virtual thread giải quyết bài toán nào?

Với mô hình **platform thread**, phần lớn triển khai Java ánh xạ luồng Java tới luồng hệ điều hành. Số platform thread có thể tạo và duy trì bị giới hạn bởi bộ nhớ, stack, lịch trình của OS và tài nguyên máy.

Trong các ứng dụng **I/O-bound** như HTTP service, truy vấn database, gọi dịch vụ từ xa hoặc xử lý nhiều kết nối có thời gian chờ, mỗi tác vụ có thể tốn rất ít CPU nhưng bị chặn trong thời gian dài. Virtual thread cho phép Java runtime **tạm dừng một tác vụ đang chờ** và dành platform thread bên dưới cho tác vụ khác khi thao tác chặn hỗ trợ cơ chế này.

```text
Nhiều virtual threads (các tác vụ):
    VT-A ── chờ HTTP ────────────► chạy tiếp
    VT-B ── chờ database ──► chạy tiếp
    VT-C ── thực thi ──► chờ I/O ──► chạy tiếp

Một số ít platform threads (carriers):
    carrier-1: chạy A → chạy C → chạy B → ...
    carrier-2: chạy B → chạy A → ...
```

Sơ đồ chỉ minh họa. Runtime lựa chọn thời điểm gắn (*mount*) virtual thread lên carrier và tạm tháo (*unmount*) theo cơ chế scheduling; **không có bảo đảm một virtual thread luôn dùng cùng một carrier**.

Virtual threads rất hữu ích khi có **nhiều tác vụ phần lớn thời gian đang chờ**. Chúng **không làm CPU nhanh hơn**, không biến mã đồng bộ thành mã không chặn theo nghĩa của hệ điều hành, và không thay thế việc quản lý transaction, giới hạn kết nối, timeout hoặc đồng bộ dữ liệu.

### 1.1. Sự khác biệt quan trọng

| Đặc điểm | Platform thread | Virtual thread |
| --- | --- | --- |
| Đơn vị thực thi Java | `Thread` | `Thread` |
| Ai chủ yếu scheduling? | Hệ điều hành | Java runtime, chạy nhờ carrier platform threads |
| Chi phí cho số lượng lớn tác vụ chờ I/O | Thường cao hơn | Thường thấp hơn đáng kể |
| Thích hợp | CPU-bound và đa dạng tác vụ | Nhiều tác vụ độc lập, chủ yếu chờ I/O |
| Tương tác `Thread.currentThread()` | Trả platform thread hiện tại | Trả **virtual thread** hiện tại |
| Cơ chế chờ hoàn thành | `join()`, executor/Future | Cũng là `join()`, executor/Future |
| Có thread-local variables? | Có | Có, nhưng cần cân nhắc chi phí/ngữ cảnh |
| Có phải tài nguyên vô hạn? | Không | **Không**: mỗi task, stack, context và I/O vẫn tốn tài nguyên |

Đừng hình dung “virtual thread = platform thread bị chia nhỏ thành các slot cố định”. Virtual thread là đối tượng Thread với vòng đời riêng; carrier chỉ là tài nguyên runtime dùng để thực thi chúng.

## 2. Tạo nhanh một virtual thread bằng `Thread.ofVirtual().start(...)`

Dạng đơn giản nhất:

```java
public class FirstVirtualThread {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().start(() -> {
            System.out.println("Là virtual? "
                    + Thread.currentThread().isVirtual());
        });

        worker.join();
    }
}
```

Kết quả:

```text
Là virtual? true
```

Diễn giải:

1. `Thread.ofVirtual()` trả về một `Thread.Builder.OfVirtual`.
2. `start(Runnable task)` **tạo và bắt đầu** một virtual thread thực thi `task`.
3. `Thread.currentThread()` trong lambda trả về virtual thread đang thực thi, **không phải carrier thread**.
4. `isVirtual()` kiểm tra loại thread.
5. `worker.join()` làm thread gọi chờ tới khi `worker` kết thúc.

**Không bỏ `join()` trong ví dụ ngắn chỉ vì “thread nhẹ và chạy nhanh”.** Virtual threads là daemon threads; riêng chúng không giữ JVM còn chạy. Nếu `main` kết thúc và không có non-daemon threads khác, chương trình có thể thoát trước khi tác vụ virtual hoàn tất.

### 2.1. `Thread.startVirtualThread(...)`: cú pháp rút gọn

Java có factory tiện lợi:

```java
Thread task = Thread.startVirtualThread(() -> {
    System.out.println(Thread.currentThread().isVirtual());
});

task.join();
```

Dạng này phù hợp khi chỉ cần **khởi chạy ngay một tác vụ**, không cần cấu hình builder. Nó cũng trả về `Thread` để có thể `join` hoặc `interrupt`.

Không có “hồ chứa virtual thread” trong hai lệnh trên; mỗi lần gọi tạo một virtual thread mới cho tác vụ được cung cấp.

## 3. `unstarted(...)`: tạo trước, bắt đầu sau

Nếu muốn tạo đối tượng Thread trước khi lên lịch chạy:

```java
Runnable job = () -> System.out.println("Đang xử lý");

Thread worker = Thread.ofVirtual()
        .name("import-customer")
        .unstarted(job);

System.out.println(worker.getState()); // NEW
System.out.println(worker.isVirtual()); // true

worker.start();
worker.join();
```

Phân biệt:

| API | Khi trả về | Bước tiếp theo |
| --- | --- | --- |
| `Thread.ofVirtual().start(task)` | Virtual thread **đã được start** | Có thể `join()`, `interrupt()` |
| `Thread.ofVirtual().unstarted(task)` | Virtual thread ở trạng thái `NEW` | Phải gọi `start()` khi muốn chạy |
| `Thread.startVirtualThread(task)` | Virtual thread **đã được start** | Có thể `join()` |
| `ThreadFactory.newThread(task)` | Một thread **chưa start** | Cần gọi `start()` hoặc giao cho cơ chế quản lý thích hợp |

`Thread.start()` chỉ được gọi **một lần** cho một Thread. Nếu cố gọi lại sau khi thread đã được start, JVM ném `IllegalThreadStateException`, kể cả khi tác vụ đó đã kết thúc. Muốn chạy lại hành vi, hãy tạo **Thread mới**.

`unstarted` hữu ích khi code cần gắn metadata hoặc đăng ký đối tượng Thread trước khi bắt đầu. Với ứng dụng xử lý hàng loạt, thường nên giao lifecycle cho executor thay vì tự quản lý hàng nghìn đối tượng Thread.

## 4. Builder cho tên, factory và xử lý ngoại lệ

`Thread.ofVirtual()` tạo builder với các thao tác cấu hình hiện hành:

```java
Thread.Builder.OfVirtual builder = Thread.ofVirtual()
        .name("order-", 0)
        .inheritInheritableThreadLocals(false)
        .uncaughtExceptionHandler((thread, error) ->
                System.err.println(thread.getName() + ": " + error));
```

Các API chính:

| Builder method | Công dụng | Ghi chú |
| --- | --- | --- |
| `name("worker-a")` | Đặt tên cố định | Phù hợp một thread |
| `name("worker-", 0)` | Đặt tiền tố + bộ đếm | Những thread được builder/factory tạo có tên phân biệt |
| `inheritInheritableThreadLocals(false)` | Không kế thừa các giá trị `InheritableThreadLocal` ban đầu | Quan trọng khi không muốn mang context từ thread tạo |
| `uncaughtExceptionHandler(handler)` | Xử lý exception không được bắt từ `Runnable` | Độc lập với cơ chế báo lỗi qua `Future` |
| `start(task)` | Tạo và khởi chạy ngay | Trả `Thread` |
| `unstarted(task)` | Tạo nhưng chưa chạy | Trả `Thread` |
| `factory()` | Tạo `ThreadFactory` với cấu hình builder | Phù hợp cho executor tùy chỉnh |

### 4.1. Đặt tên để quan sát tác vụ

Virtual thread **không có tên mặc định**; `getName()` có thể trả chuỗi rỗng. Khi dùng log, stack trace hoặc công cụ chẩn đoán, tên có ý nghĩa sẽ giúp nhận diện tác vụ.

```java
Thread job = Thread.ofVirtual()
        .name("report-generator")
        .start(() -> System.out.println(Thread.currentThread().getName()));

job.join();
```

Kết quả:

```text
report-generator
```

Khi có nhiều tác vụ, dùng tiền tố và bộ đếm thay vì đặt cùng một tên cho tất cả:

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("request-", 1)
        .factory();

Thread first = factory.newThread(
        () -> System.out.println(Thread.currentThread().getName()));
Thread second = factory.newThread(
        () -> System.out.println(Thread.currentThread().getName()));

first.start();
second.start();

first.join();
second.join();
```

Hai thread có tên tương ứng `request-1` và `request-2`, nhưng **thứ tự in ra màn hình không được bảo đảm**. Factory được tạo từ builder là an toàn cho việc tạo thread từ nhiều luồng đồng thời; không cần tự đồng bộ chỉ để cấp tên theo bộ đếm của factory.

### 4.2. Uncaught exception handler không thay `Future.get()`

Khi trực tiếp khởi chạy `Runnable` và ngoại lệ không được bắt trong thân tác vụ, handler của thread có thể nhận ngoại lệ:

```java
Thread failed = Thread.ofVirtual()
        .name("failing-task")
        .uncaughtExceptionHandler((thread, error) ->
                System.out.println("Lỗi ở " + thread.getName()
                        + ": " + error.getMessage()))
        .start(() -> {
            throw new IllegalStateException("Không xử lý được");
        });

failed.join();
```

Kết quả:

```text
Lỗi ở failing-task: Không xử lý được
```

**Lưu ý:** `Thread.join()` chỉ chờ thread kết thúc, **không tự ném lại ngoại lệ** của thân tác vụ. Ngược lại, khi gửi `Callable` bằng `ExecutorService.submit(...)`, ngoại lệ thường được giữ trong `Future` và nhận qua `Future.get()` dưới dạng `ExecutionException`. Đừng giả định handler builder sẽ nhận mọi lỗi bên trong tác vụ do executor quản lý.

## 5. `ThreadFactory`: cầu nối giữa builder và framework

`ThreadFactory` là interface tạo thread theo cấu hình đã chọn. Factory không phải executor; bản thân nó **không nhận hàng đợi, không quản lý tác vụ và không tự khởi chạy thread**:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofVirtual()
        .name("db-io-", 0)
        .factory();

Thread worker = factory.newThread(() -> {
    System.out.println("Đọc dữ liệu");
});

worker.start();
worker.join();
```

Giá trị của factory là tách **cách tạo thread** khỏi **thành phần sử dụng thread**. Nó đặc biệt hữu ích khi framework hoặc executor có phương thức nhận `ThreadFactory`.

Khi cần một executor đặt tên virtual threads theo ý muốn, có thể truyền factory này vào `Executors.newThreadPerTaskExecutor(factory)`, thay vì tự quản lý nhiều `Thread`.

## 6. Executor theo tác vụ: `Executors.newVirtualThreadPerTaskExecutor()`

Đây là API quan trọng khi cần xử lý **nhiều tác vụ độc lập**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    executor.execute(() -> System.out.println("Task A"));
    executor.execute(() -> System.out.println("Task B"));
}
```

Mỗi tác vụ được executor chấp nhận sẽ được chạy bằng **một virtual thread mới**. Khi đóng executor bằng `try-with-resources`, chương trình tiến hành shutdown có trật tự và chờ các tác vụ đã gửi hoàn tất.

Hai điểm cần tránh nhầm:

- **Đây không phải pool** một số virtual threads cố định để tái sử dụng. Mỗi task có virtual thread riêng; executor không phải bộ đếm cố định worker threads.
- **Không có giới hạn số virtual threads do chính API này áp đặt.** Nếu gửi hàng triệu tác vụ đồng thời, ứng dụng vẫn có thể cạn RAM, connection pool, file descriptors hoặc giới hạn API bên ngoài.

### 6.1. So sánh với fixed thread pool

```java
ExecutorService platformPool = Executors.newFixedThreadPool(8);
ExecutorService virtualPerTask = Executors.newVirtualThreadPerTaskExecutor();
```

| Tiêu chí | `newFixedThreadPool(8)` | `newVirtualThreadPerTaskExecutor()` |
| --- | --- | --- |
| Mô hình chính | Tái sử dụng khoảng 8 worker platform threads | Virtual thread mới cho **từng** task |
| Số task đang chờ CPU/I/O trong executor | Task có thể xếp hàng đợi | Có thể tạo rất nhiều virtual threads cùng tồn tại |
| Giới hạn đồng thời mặc định | Số worker threads (8) | **Không bị giới hạn bởi một pool size** |
| Phù hợp điển hình | Công việc cần giới hạn số worker/CPU | Nhiều tác vụ độc lập chờ I/O |
| Vấn đề vẫn phải giải quyết | Queue, capacity, shutdown, lỗi | Tài nguyên đích, backpressure, timeout, shutdown, lỗi |

Không dùng `newFixedThreadPool(n, Thread.ofVirtual().factory())` như một “virtual thread pool” mặc định. Virtual threads được thiết kế để **không cần pool và tái sử dụng theo cách này**. Nếu cần giới hạn tác vụ, hãy đặt giới hạn ở **tài nguyên hoặc số công việc được nhận**, không tái tạo mô hình pool cố định chỉ vì đó là cách cũ.

## 7. `execute` và `submit`: theo dõi kết quả khác nhau

Với `ExecutorService`:

- `execute(Runnable)` gửi tác vụ `Runnable`, **không trả `Future`**.
- `submit(Runnable)` trả `Future<?>` để theo dõi hoàn tất/hủy; `get()` trả `null` khi tác vụ hoàn thành bình thường.
- `submit(Callable<T>)` trả `Future<T>`; `get()` trả kết quả hoặc báo lỗi.
- `invokeAll(...)` gửi một nhóm `Callable` và chờ toàn bộ nhóm hoàn tất (hoặc đến timeout ở overload tương ứng).

Ví dụ dùng `Callable`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<Integer> a = executor.submit(() -> 20 + 7);
    Future<String> b = executor.submit(
            () -> Thread.currentThread().isVirtual() ? "virtual" : "platform");

    System.out.println(a.get()); // 27
    System.out.println(b.get()); // virtual
}
```

Một `Callable<T>` được phép trả giá trị và khai báo checked exception. Phần thân có thể dùng các API blocking thông thường, nhưng phải tuân theo timeout, cancellation và những giới hạn tài nguyên thực tế.

### 7.1. `Future.get()` xử lý lỗi thế nào?

Nếu task ném exception, `Future.get()` ném `ExecutionException`, có thể lấy nguyên nhân qua `getCause()`:

```java
import java.util.concurrent.ExecutionException;

try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {

    var result = executor.submit(() -> {
        throw new IllegalStateException("Dữ liệu không hợp lệ");
    });

    try {
        result.get();
    } catch (ExecutionException error) {
        System.out.println(error.getCause().getMessage());
    }
}
```

Kết quả:

```text
Dữ liệu không hợp lệ
```

Nếu tác vụ bị hủy, `get()` có thể ném `CancellationException`. Nếu thread đang chờ `get()` bị interrupt, nó có thể ném `InterruptedException`. Phải xử lý đúng các nhánh này theo hợp đồng của tầng ứng dụng.

**Đừng gửi hàng loạt task bằng `submit` rồi bỏ luôn mọi `Future` khi việc biết task thất bại là quan trọng.** Exception có thể bị giữ trong kết quả nhưng không được quan sát.

## 8. Tạo executor theo tác vụ với builder tùy chỉnh

`newVirtualThreadPerTaskExecutor()` đủ cho đa số trường hợp. Khi muốn đặt tên hoặc cấu hình cách tạo virtual threads, dùng:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofVirtual()
        .name("http-request-", 0)
        .inheritInheritableThreadLocals(false)
        .factory();

try (ExecutorService executor =
             Executors.newThreadPerTaskExecutor(factory)) {

    var future = executor.submit(() ->
            Thread.currentThread().getName());

    System.out.println(future.get()); // http-request-0
}
```

Hai API hiện hành:

- `Executors.newVirtualThreadPerTaskExecutor()`: cấu hình sẵn factory tạo virtual thread.
- `Executors.newThreadPerTaskExecutor(ThreadFactory)`: nhận factory do người dùng cung cấp; factory tạo virtual thread thì **mỗi tác vụ vẫn dùng một virtual thread mới**.

Cả hai đều là **thread-per-task executor**, không phải pool tái sử dụng threads. Không có overload chính thức `newVirtualThreadPerTaskExecutor(factory)` — nếu cần custom factory, dùng `newThreadPerTaskExecutor(factory)`.

### 8.1. Dùng cùng executor trong một phạm vi công việc

```java
static java.util.List<String> fetchLabels(java.util.List<String> ids)
        throws Exception {

    try (var executor = java.util.concurrent.Executors
            .newVirtualThreadPerTaskExecutor()) {

        java.util.List<java.util.concurrent.Future<String>> futures =
                new java.util.ArrayList<>();

        for (String id : ids) {
            futures.add(executor.submit(() -> "label-" + id));
        }

        java.util.List<String> labels = new java.util.ArrayList<>();
        for (var future : futures) {
            labels.add(future.get());
        }

        return java.util.List.copyOf(labels);
    }
}
```

Đây là cách tổ chức dễ đọc khi có một nhóm task được sinh ra trong cùng phạm vi: khởi tạo executor, gửi task, lấy kết quả, tự động đóng executor.

Thứ tự **hoàn thành** task không được bảo đảm; ví dụ trên cố ý lấy `Future` theo thứ tự trong danh sách nên thứ tự **kết quả trả về** theo `ids`.

## 9. Đóng executor và kết thúc tác vụ

`ExecutorService` triển khai `AutoCloseable`, vì vậy API `close()` tương thích với `try-with-resources`:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> performWork());
} // Gọi close(); shutdown có trật tự và chờ kết thúc.
```

Trong Java 27, `ExecutorService.close()` bắt đầu shutdown có trật tự và **chờ các task đã gửi hoàn tất**. Nó không có nghĩa “ngay lập tức giết các thread” hoặc “mọi task tự động bị hủy khi rời scope”.

Các thao tác liên quan:

| API | Ý nghĩa |
| --- | --- |
| `shutdown()` | Ngừng nhận task mới; các task trước đó được phép hoàn tất |
| `shutdownNow()` | Cố gắng dừng task đang chạy (thường bằng interrupt), xử lý task chưa bắt đầu theo hợp đồng |
| `awaitTermination(timeout, unit)` | Chờ executor kết thúc tối đa khoảng thời gian đã cho |
| `close()` | Shutdown có trật tự và chờ hoàn tất |
| `isShutdown()` | Đã yêu cầu shutdown? |
| `isTerminated()` | Đã kết thúc sau shutdown? |

Lưu ý: nếu task không bao giờ hoàn tất hoặc không phản hồi interruption, `close()` có thể **chờ rất lâu**. Không dùng try-with-resources như một cơ chế timeout. Phải thiết kế timeout của I/O và cancellation của task riêng.

### 9.1. Hai giai đoạn shutdown khi executor sống lâu

Với service quản lý executor qua nhiều request, có thể dùng chiến lược:

1. Gọi `shutdown()` để ngừng nhận thêm task.
2. Chờ một khoảng hữu hạn bằng `awaitTermination`.
3. Nếu vượt hạn, gọi `shutdownNow()` và xử lý task còn lại.
4. Nếu thread đang chờ bị interrupt, khôi phục interrupt status sau khi thực hiện cleanup thích hợp.

Không nên tạo một executor **mới cho mỗi tác vụ đơn lẻ** khi bản thân service đã có phạm vi lifecycle hợp lý; có thể tái sử dụng **executor**, nhưng **không tái sử dụng virtual threads** của executor. Điểm khác nhau này giúp vừa quản lý vòng đời rõ ràng, vừa giữ semantics mỗi task một thread.

## 10. Cancellation và interruption là cơ chế hợp tác

Một virtual thread vẫn hỗ trợ `interrupt()`. Interruption là **yêu cầu hủy hoặc dừng công việc**, không phải lệnh cưỡng bức bảo đảm task kết thúc tức thì.

```java
Thread worker = Thread.ofVirtual().start(() -> {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        System.out.println("Task được yêu cầu hủy");
    }
});

worker.interrupt();
worker.join();
```

Khi `Thread.sleep` đang chờ hoặc kiểm tra interruption, nó có thể ném `InterruptedException`. Code khôi phục interrupt status nếu tầng trên cần biết thread đã bị yêu cầu interrupt; ở đây task kết thúc bình thường sau khối `catch`.

Với `Future`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() -> {
        Thread.sleep(10_000);
        return "done";
    });

    try {
        System.out.println(future.get(100, TimeUnit.MILLISECONDS));
    } catch (TimeoutException timeout) {
        future.cancel(true); // Yêu cầu interrupt task.
        System.out.println("Đã quá hạn, yêu cầu hủy task");
    }
}
```

`get(timeout, unit)` chỉ giới hạn **thời gian thread gọi chờ kết quả**. Nó **không tự hủy task** khi hết hạn; chính ứng dụng phải quyết định có gọi `cancel(true)` và thu dọn tài nguyên hay không.

Nếu task đang thực hiện một thao tác không hỗ trợ interruption hoặc cố ý bỏ qua tín hiệu hủy, `cancel(true)` không bảo đảm tác vụ dừng ngay. Với HTTP/SQL/network calls, cần cấu hình **timeout tại API I/O tương ứng**, bên cạnh `Future.get(timeout, ...)`.

## 11. Virtual threads không thay thế giới hạn tài nguyên và backpressure

Ví dụ một dịch vụ có thể nhận 100.000 yêu cầu, nhưng connection pool chỉ cho phép 40 kết nối database. Nếu tạo 100.000 virtual threads cùng tranh chấp 40 kết nối, runtime có thể chịu được **nhiều tác vụ đang chờ**, nhưng database không thể phục vụ đồng thời 100.000 truy vấn.

**Virtual thread rẻ hơn platform thread không có nghĩa request hoặc I/O rẻ.** Những tài nguyên vẫn giới hạn:

- Database connections và số transaction đồng thời.
- API rate limits / số kết nối tới downstream service.
- Bộ nhớ ứng dụng và dữ liệu giữ trong mỗi tác vụ.
- File descriptors, sockets, heap, cache, thread-local objects.
- CPU thực tế và giới hạn queue của dịch vụ.

Có thể dùng `Semaphore` để giới hạn truy cập tài nguyên:

```java
import java.util.concurrent.Semaphore;

Semaphore dbSlots = new Semaphore(40);

String queryDatabase(String key) throws InterruptedException {
    dbSlots.acquire();
    try {
        return runDatabaseQuery(key);
    } finally {
        dbSlots.release();
    }
}
```

Đây là **đoạn minh họa** bên trong lớp có các thành phần tương ứng; `runDatabaseQuery` đại diện hàm thật và cần được cài đặt. Nếu `acquire()` bị interrupt trước khi lấy permit, code chưa vào `try` nên không giải phóng một permit không sở hữu. Khi đã lấy permit, `finally` bảo đảm trả permit.

Semaphore đặt **bên trong task** chỉ giới hạn số task thực sự vào database; nó **không giới hạn số virtual threads được tạo và đang chờ permit**. Khi luồng yêu cầu có thể tăng không kiểm soát, cần thêm **admission control/backpressure ở ranh giới nhận công việc**, queue có giới hạn, hoặc từ chối yêu cầu phù hợp với tải hệ thống.

Không pool virtual threads để giải quyết giới hạn database. Hãy pool và giới hạn đúng tài nguyên **database connections** hoặc số request được nhận.

## 12. Virtual thread phù hợp với blocking I/O, không phải phép tăng tốc CPU

Ví dụ điển hình:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var account = executor.submit(() -> loadAccountFromDatabase());
    var settings = executor.submit(() -> fetchSettingsOverHttp());

    return combine(account.get(), settings.get());
}
```

Đây là **pseudocode theo ngữ cảnh phương thức**: các hàm `loadAccountFromDatabase`, `fetchSettingsOverHttp` và `combine` cần được cài đặt. Nếu hai việc chờ I/O độc lập, chạy đồng thời có thể giảm thời gian chờ tổng thể; code vẫn viết theo kiểu blocking dễ hiểu.

Ngược lại, tác vụ **CPU-bound** kéo dài, ví dụ mã hóa video, tính toán ma trận, nén số liệu quy mô lớn, thường cần giới hạn parallelism theo CPU. Tạo vô số virtual threads không làm tăng số core và có thể thêm chi phí scheduling. Một executor có parallelism kiểm soát, thuật toán chia việc hoặc công cụ xử lý song song phù hợp có thể hiệu quả hơn.

Về thiết kế:

- **Thread-per-request** với virtual threads có thể đơn giản hóa ứng dụng chủ yếu đợi I/O.
- Giữ **timeouts, cancellation, resource caps và backpressure**.
- Đánh giá thực tế bằng latency, throughput, CPU, memory và số kết nối thay vì kết luận “virtual luôn nhanh hơn”.
- Các thư viện I/O cũ có thể không tận dụng tối đa khả năng unmount; cần thử trên workload và JDK thực tế.

## 13. Vấn đề carrier pinning trong Java 27

Một virtual thread được **mounted** trên carrier khi chạy code. Trong nhiều blocking operations được hỗ trợ, runtime có thể **unmount** nó để giải phóng carrier. Nhưng có các tình huống virtual thread bị **pinned**, không thể được unmount khi đang chờ; điều này có thể làm giảm khả năng mở rộng.

**Kiến thức cần cập nhật:** Từ JDK 24, thay đổi theo JEP 491 cho phép virtual thread block trong các vùng `synchronized` thông thường mà **không còn pin carrier chỉ vì đang ở synchronized**. Vì vậy, khuyến nghị cũ “phải thay mọi `synchronized` bằng `ReentrantLock` để dùng virtual thread” **không còn đúng** với Java 27.

Pinning vẫn có thể xảy ra trong một số thao tác liên quan:

- Native methods hoặc foreign function calls.
- Một số thao tác VM/native hoặc những tình huống đặc thù được JDK ghi nhận.
- Những đoạn blocking không thể giải phóng carrier trong khi giữ trạng thái không unmount được.

Pinning **không nhất thiết là lỗi chức năng**; rủi ro chính là hiệu năng và khả năng mở rộng khi nhiều carrier bị giữ trong thời gian dài.

Cách làm phù hợp:

1. Ưu tiên API Java SE hiện hành, ít phụ thuộc native blocking.
2. Xem xét JFR event `jdk.VirtualThreadPinned` khi có dấu hiệu throughput giảm hoặc các yêu cầu bị treo.
3. Xác định stack trace và operation cụ thể trước khi sửa.
4. Không tự động thay toàn bộ synchronized, cũng không giả định mọi blocking operation đều unmount.

Những mô tả pinning từ các tài liệu **trước JDK 24** cần được đối chiếu với Java 27 trước khi áp dụng.

## 14. Ngữ cảnh tác vụ: ThreadLocal và InheritableThreadLocal

Virtual thread vẫn có khả năng dùng `ThreadLocal`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
```

Nếu một tác vụ gán giá trị:

```java
Thread worker = Thread.ofVirtual().start(() -> {
    REQUEST_ID.set("req-27");
    try {
        System.out.println(REQUEST_ID.get());
    } finally {
        REQUEST_ID.remove();
    }
});
worker.join();
```

Mỗi thread có giá trị local riêng. Việc `REQUEST_ID.set(...)` trong thread A **không tự lan** đến thread B. `ThreadLocal` không phải global map chung và không phải cơ chế tự động truyền mọi request context qua executor.

### 14.1. InheritableThreadLocal được kế thừa lúc tạo thread theo cấu hình

`InheritableThreadLocal` có thể sao chép/khởi tạo giá trị của parent thread **tại thời điểm tạo child thread** theo quy tắc API. Builder mặc định cho phép kế thừa; có thể tắt nếu không muốn mang theo context:

```java
Thread worker = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .start(() -> handleRequest());
```

Trong ứng dụng có nhiều tác vụ, **không mặc định suy ra mọi context** như security principal, transaction, trace span, locale đều tự xuất hiện đúng ở từng task. Việc truyền ngữ cảnh phụ thuộc loại context và cơ chế của framework; cần xác định rõ ai thiết lập, ai khôi phục và khi nào kết thúc.

### 14.2. Cân nhắc Scoped Values và truyền tham số tường minh

Với **ngữ cảnh chỉ đọc, có phạm vi động**, Java hiện đại có `ScopedValue` là API phù hợp trong những tình huống được thiết kế đúng. Phạm vi binding và quy tắc lan truyền sang các task con **không đồng nghĩa tự động với mọi `ExecutorService.submit`**. Nếu cần context cho một task, có thể truyền tham số tường minh hoặc tạo binding trong chính tác vụ theo quy tắc `ScopedValue`.

Ví dụ cách đơn giản, dễ kiểm soát nhất:

```java
record RequestContext(String requestId, String userId) {}

static String process(RequestContext context) {
    return "Đang xử lý " + context.requestId();
}

static void dispatch(ExecutorService executor, RequestContext context) {
    executor.submit(() -> process(context));
}
```

Dữ liệu context được đưa vào task qua đối số và capture; không phụ thuộc carrier thread hay thread-local của nơi gọi. `RequestContext` là một record, còn thread chạy task có thể là virtual thread.

**Lưu ý bộ nhớ:** Mỗi virtual thread có thể mang các đối tượng `ThreadLocal` và context riêng. Nếu tạo hàng trăm nghìn tác vụ, giữ một object nặng trong từng thread-local có thể làm mất lợi ích tiết kiệm tài nguyên. Tránh cache đối tượng lớn trong per-thread state một cách thiếu kiểm soát.

## 15. Quan sát và gỡ lỗi virtual threads

Thông tin hữu ích khi chẩn đoán:

- `Thread.currentThread().getName()` — tên thread khi đã cấu hình.
- `Thread.currentThread().isVirtual()` — xác định task chạy trên virtual thread.
- `Future.get()` — lấy kết quả/ngoại lệ task đã gửi.
- JDK Flight Recorder (JFR) — quan sát sự kiện runtime, pinning và các hoạt động liên quan.
- Thread dump/diagnostic tools phù hợp cho lượng lớn virtual threads.

Oracle Java 27 mô tả JFR events như:

| Sự kiện | Ý nghĩa |
| --- | --- |
| `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` | Thời điểm bắt đầu/kết thúc (không mặc định bật trong mọi cấu hình) |
| `jdk.VirtualThreadPinned` | Virtual thread bị pinned và giữ carrier vượt ngưỡng sự kiện |
| `jdk.VirtualThreadSubmitFailed` | Runtime không thể schedule/unpark virtual thread, có thể liên quan tài nguyên |

Không nên bật log cho **mỗi** virtual thread ở hệ thống throughput cao mà không đánh giá chi phí. Khi trace request, ưu tiên correlation ID và thông tin nghiệp vụ hơn việc coi tên Thread là định danh bền vững của người dùng.

## 16. Ví dụ Java 27 hoàn chỉnh: builder và executor per task

Tạo file `VirtualThreadCreationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;

public class VirtualThreadCreationDemo {

    static String simulateIo(int id) throws InterruptedException {
        // Mô phỏng tác vụ bị chặn trong lúc chờ I/O.
        Thread.sleep(30);

        Thread current = Thread.currentThread();
        return "task-" + id + " -> " + current.getName()
                + ", virtual=" + current.isVirtual();
    }

    public static void main(String[] args) throws Exception {
        // 1. Builder: tạo một virtual thread và khởi chạy ngay.
        Thread direct = Thread.ofVirtual()
                .name("direct")
                .start(() -> System.out.println(
                        "Builder -> " + Thread.currentThread().isVirtual()
                ));
        direct.join();

        // 2. Builder: tạo trước, bắt đầu sau.
        Thread delayed = Thread.ofVirtual()
                .name("delayed")
                .unstarted(() -> System.out.println(
                        "Unstarted -> " + Thread.currentThread().getName()
                ));
        delayed.start();
        delayed.join();

        // 3. Executor mặc định: một virtual thread mới cho mỗi task.
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Boolean> result = executor.submit(
                    () -> Thread.currentThread().isVirtual()
            );
            System.out.println("Executor -> " + result.get());
        }

        // 4. Executor tùy chỉnh dùng ThreadFactory của builder.
        ThreadFactory factory = Thread.ofVirtual()
                .name("io-worker-", 0)
                .inheritInheritableThreadLocals(false)
                .factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {

            List<Future<String>> futures = new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                int taskId = id;
                futures.add(executor.submit(() -> simulateIo(taskId)));
            }

            // Lấy Future theo thứ tự gửi, dù thứ tự chạy không bảo đảm.
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 27 (không cần preview):

```bash
javac -encoding UTF-8 VirtualThreadCreationDemo.java
java VirtualThreadCreationDemo
```

Kết quả:

```text
Builder -> true
Unstarted -> delayed
Executor -> true
task-1 -> io-worker-0, virtual=true
task-2 -> io-worker-1, virtual=true
task-3 -> io-worker-2, virtual=true
```

Vì sao đầu ra trên ổn định theo **thứ tự các dòng được in**?

1. `direct.join()` làm thread main chờ tác vụ builder đầu tiên in xong trước khi đi tiếp.
2. `delayed.join()` chờ virtual thread tên `delayed` hoàn tất.
3. `Future.get()` chờ task executor mặc định hoàn tất và trả `Boolean.TRUE`.
4. Executor tùy chỉnh dùng `ThreadFactory` cấp tên theo thứ tự tạo thread.
5. Danh sách `Future` được duyệt **theo thứ tự submit**, vì vậy kết quả được in theo thứ tự task ID dù thời điểm từng task hoàn thành có thể khác nhau.

Chương trình không chứng minh task chạy trên carrier nào, và cũng không chứng minh ba task **luôn** thực thi đồng thời. Nó minh họa API và lifetime đúng mà không phụ thuộc vào timing scheduler.

## 17. Các lỗi thiết kế thường gặp

| Sai lầm | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| Tạo virtual thread rồi bỏ `join()` trong chương trình main ngắn | JVM có thể thoát khi chỉ còn daemon virtual threads | Dùng `join()` hoặc phạm vi executor có chờ hoàn tất |
| Gọi `start()` hai lần cùng một Thread | Ném `IllegalThreadStateException` | Tạo Thread mới cho lần chạy mới |
| Nghĩ `newVirtualThreadPerTaskExecutor()` là pool cố định | Không có reuse/giới hạn số worker theo task | Hiểu mỗi task một virtual thread |
| Pool virtual threads để hạn chế kết nối database | Giới hạn sai tài nguyên | Dùng connection pool, semaphore hoặc admission control |
| Dùng virtual threads cho phép tính CPU-bound khổng lồ | Không làm tăng core CPU | Giới hạn parallelism CPU phù hợp |
| Gọi `executor.submit(...)` nhưng bỏ mọi `Future` | Có thể không quan sát được exception trong task | Theo dõi Future/log hoặc cơ chế báo lỗi |
| Nghĩ `close()` sẽ hủy ngay các task | `close()` chờ shutdown có trật tự | Thiết kế timeout/cancellation riêng |
| Nghĩ `Future.get(timeout)` tự dừng task | Chỉ giới hạn thời gian chờ kết quả | Cân nhắc `cancel(true)` và I/O timeout |
| Giả định `cancel(true)` luôn dừng ngay | Interruption hợp tác | Code xử lý interrupt và giải phóng tài nguyên |
| Dùng `ThreadLocal` lớn cho mỗi request trong hàng trăm nghìn virtual threads | Tăng memory footprint | Chuyển context gọn/tường minh, hạn chế per-thread caches |
| Dựa vào carrier thread để nhận diện request | Một virtual thread có thể đổi carrier | Sử dụng request ID hoặc context của chính task |
| Tin rằng `synchronized` luôn pin virtual thread | Kết luận trước JDK 24 đã lỗi thời | Xem pinning hiện hành của JDK 27; phân tích JFR |
| Gửi vô hạn task vì virtual threads rẻ | Dễ cạn tài nguyên downstream và heap | Giới hạn công việc đầu vào, backpressure |
| Dùng tên thread làm định danh nghiệp vụ | Tên chỉ giúp debug, không phải ID bền vững | Dùng domain ID/request ID |
| Không xác định vòng đời của executor trong service | Task có thể tồn tại lâu, resource không được thu dọn | Quản lý lifecycle cùng application/service |

## 18. Chọn builder hay executor?

| Tình huống | Ưu tiên | Lý do |
| --- | --- | --- |
| Chạy một việc nhỏ rồi chờ hoàn thành | `Thread.ofVirtual().start(...)` + `join()` | Rõ ràng, ít tầng trừu tượng |
| Muốn tạo Thread trước, start sau | `unstarted(...)` | Chủ động trạng thái NEW và thời điểm start |
| Cần tên, handler, chính sách kế thừa inheritable locals | `Thread.ofVirtual()` builder | Cấu hình thread |
| Framework cần factory tạo thread | `Thread.ofVirtual().factory()` | Giao cách tạo thread cho framework |
| Có nhiều task độc lập, cần Future và xử lý lỗi | `Executors.newVirtualThreadPerTaskExecutor()` | Một virtual thread/task, quản lý kết quả |
| Cần nhiều task có tên theo prefix | `newThreadPerTaskExecutor(Thread.ofVirtual().name(...).factory())` | Executor cùng factory tùy chỉnh |
| Cần kết thúc khi nhóm việc xong | `try (ExecutorService e = ...)` | Vòng đời có shutdown và chờ |
| Cần giới hạn tải tới database/API bên ngoài | Semaphore/backpressure/resource pool phù hợp | Virtual thread không tự giới hạn I/O |
| Muốn giới hạn CPU parallelism | Executor/thiết kế song song giới hạn CPU | Nhiều virtual threads không tạo thêm core |

Một quy tắc đơn giản: **builder trả về Thread để bạn trực tiếp quản lý; executor nhận task và trả Future để bạn quản lý kết quả**. Cả hai tạo virtual threads nhưng có mức trừu tượng khác nhau.

## 19. Checklist trước khi triển khai production

1. **Tác vụ chủ yếu chờ I/O hay đốt CPU?** Dùng virtual threads trước hết cho nhiều tác vụ chờ.
2. **Mỗi tác vụ cần độc lập hay chia sẻ trạng thái?** Ưu tiên thông tin bất biến và tránh race conditions.
3. **Ai chịu trách nhiệm chờ hoàn tất?** Dùng `join`, `Future.get` hoặc cơ chế quản lý scope/executor.
4. **Ai đóng executor?** Xác định lifetime cùng service/request và shutdown khi không dùng.
5. **Task có thể thất bại?** Đọc `Future`/log và xác định chính sách retry, không nuốt lỗi.
6. **Task có thể treo?** Đặt timeout I/O, timeout chờ, cancellation và cleanup.
7. **Có giới hạn downstream?** Áp dụng semaphore/connection pool/rate limit và backpressure.
8. **Có phát sinh khối lượng task cực lớn?** Giám sát heap, sockets, queue/admission và memory per task.
9. **Có cần task context?** Truyền explicit context hoặc dùng cơ chế phù hợp; không dựa vào carrier.
10. **Có dùng InheritableThreadLocal?** Chỉ kế thừa khi thực sự mong muốn, cân nhắc `inheritInheritableThreadLocals(false)`.
11. **Có native/FFM blocking?** Theo dõi pinning bằng JFR khi có vấn đề throughput.
12. **Có đang áp dụng mẹo từ JDK cũ?** Kiểm tra lại: `synchronized` thông thường không còn là nguyên nhân pinning như trước JDK 24.
13. **Có cần tracing?** Đặt tên thread có ích nhưng dùng request ID cho tương quan log.
14. **Đã kiểm thử shutdown/hủy với task chậm?** Kiểm tra luồng lỗi và cleanup, không chỉ đường thành công.

**Ghi nhớ:** Trong Java 27, `Thread.ofVirtual()` là cách **tạo và cấu hình virtual thread trực tiếp**, còn `Executors.newVirtualThreadPerTaskExecutor()` là cách **chạy nhiều tác vụ, mỗi tác vụ một virtual thread**. Virtual thread làm cho việc chờ I/O có khả năng mở rộng tốt hơn; trách nhiệm quản lý tài nguyên, lỗi và vòng đời vẫn thuộc về ứng dụng.

## 20. Tài liệu chính thức Java SE 27

- [`java.lang.Thread` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html): virtual/platform threads, `ofVirtual`, `startVirtualThread`, `isVirtual`, interruption và daemon lifecycle.
- [`java.lang.Thread.Builder` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.Builder.html): `start`, `unstarted`, `factory`, tên và InheritableThreadLocal.
- [`java.lang.Thread.Builder.OfVirtual` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html): các thao tác cấu hình virtual threads.
- [`java.util.concurrent.Executors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`, `newThreadPerTaskExecutor` và `ThreadFactory`.
- [`java.util.concurrent.ExecutorService` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `close`, `shutdown`, `awaitTermination`.
- [`java.util.concurrent.Future` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): nhận kết quả, timeout và `cancel(true)`.
- [`java.util.concurrent.Semaphore` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn mức truy cập tài nguyên.
- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): hướng dẫn dùng virtual threads, scheduling, pinning và JFR.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): nền tảng thiết kế và mục tiêu thread-per-request với virtual threads.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi quan trọng từ JDK 24 về pinning và `synchronized`.
