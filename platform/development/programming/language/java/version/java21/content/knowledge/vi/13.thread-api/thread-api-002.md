# `Thread.ofVirtual` và builder cho virtual thread

## 1. Tạo virtual thread bằng `Thread.ofVirtual()`

Trong Java 21, virtual thread là tính năng chính thức, không còn cần bật preview feature. API `Thread.ofVirtual()` cung cấp một builder để cấu hình và tạo virtual thread. Đây là cách tạo thread trực tiếp khi cần kiểm soát tên, chính sách kế thừa `InheritableThreadLocal` hoặc xử lý exception chưa được bắt trong task.

Ví dụ ngắn nhất:

```java
Thread thread = Thread.ofVirtual().start(() -> {
    System.out.println("Running in a virtual thread");
});

thread.join();
```

`Thread.ofVirtual()` trả về `Thread.Builder.OfVirtual`. Gọi `start(task)` tạo virtual thread và bắt đầu thực thi task, đồng thời trả về đối tượng `Thread` để chương trình có thể chờ, kiểm tra trạng thái hoặc thao tác theo API của `Thread`.

Virtual thread phù hợp với tác vụ có nhiều thời gian chờ, chẳng hạn I/O hoặc xử lý request đồng thời. JVM quản lý việc lập lịch virtual thread lên các platform thread (carrier thread). Ứng dụng không cần tự quản lý một platform thread riêng cho từng virtual thread.

## 2. `Thread.Builder.OfVirtual`

`Thread.Builder.OfVirtual` là kiểu builder chuyên dùng để tạo virtual thread. Có thể giữ builder trong một biến hoặc gọi nối tiếp các method cấu hình:

```java
Thread.Builder.OfVirtual builder = Thread.ofVirtual()
        .name("worker-", 1);

Thread first = builder.start(() -> process("first"));
Thread second = builder.start(() -> process("second"));
```

Builder có thể được dùng để tạo nhiều thread. Tuy nhiên, builder không thread-safe; không nên gọi đồng thời các method của cùng một builder từ nhiều thread khác nhau. Nếu cần tạo thread từ nhiều nơi, có thể tạo `ThreadFactory` bằng `factory()` rồi chia sẻ factory theo hợp đồng của ứng dụng.

Các method cấu hình trả về builder để có thể chain:

```java
Thread thread = Thread.ofVirtual()
        .name("report-worker")
        .inheritInheritableThreadLocals(false)
        .uncaughtExceptionHandler((t, error) ->
                System.err.println(t.getName() + " failed: " + error))
        .start(() -> generateReport());
```

Ví dụ đặt tên thread, tắt việc kế thừa `InheritableThreadLocal` và cài handler cho exception không được task bắt. Các tùy chọn này được áp dụng khi builder tạo thread.

## 3. Đặt tên virtual thread

Builder hỗ trợ hai cách đặt tên chính:

- `name(String name)`: đặt cùng một tên cố định cho thread được tạo từ builder.
- `name(String prefix, long start)`: đặt tên theo tiền tố cộng số thứ tự tăng dần, bắt đầu từ giá trị `start`.

Ví dụ với tên cố định:

```java
Thread thread = Thread.ofVirtual()
        .name("database-query")
        .start(() -> queryDatabase());

System.out.println(thread.getName()); // database-query
```

Ví dụ với prefix và counter:

```java
Thread.Builder.OfVirtual builder = Thread.ofVirtual()
        .name("request-", 1);

Thread a = builder.unstarted(() -> handleRequest("A"));
Thread b = builder.unstarted(() -> handleRequest("B"));

System.out.println(a.getName()); // request-1
System.out.println(b.getName()); // request-2

a.start();
b.start();
```

Cách đặt tên theo counter hữu ích khi cần phân biệt các tác vụ trong log, thread dump hoặc công cụ giám sát. Nếu dùng tên cố định cho nhiều thread, log có thể khó xác định thread nào phát ra thông tin.

Tên thread phục vụ quan sát và chẩn đoán. Không nên dùng tên làm định danh nghiệp vụ hoặc dựa vào tên để truyền dữ liệu giữa các thread.

## 4. `start`, `unstarted` và `factory`

Builder có ba cách tạo thread thường dùng:

| Method | Kết quả | Khi nào dùng |
|---|---|---|
| `start(task)` | Tạo thread và bắt đầu chạy ngay | Muốn khởi chạy task trực tiếp |
| `unstarted(task)` | Tạo thread nhưng chưa chạy | Muốn cấu hình hoặc quyết định thời điểm gọi `Thread.start()` |
| `factory()` | Tạo `ThreadFactory` dùng cấu hình builder | Muốn cung cấp cơ chế tạo thread cho API khác, chẳng hạn executor |

### 4.1. Khởi chạy ngay với `start`

```java
Thread worker = Thread.ofVirtual()
        .name("worker")
        .start(() -> doWork());

worker.join();
```

`start` trả về thread đã được khởi chạy. Task có thể bắt đầu chạy ngay sau lời gọi này; không giả định task chỉ chạy sau khi method trả về hoặc sau khi thread gọi `join`.

### 4.2. Tạo trước, khởi chạy sau với `unstarted`

```java
Thread worker = Thread.ofVirtual()
        .name("delayed-worker")
        .unstarted(() -> doWork());

// Có thể thực hiện các bước chuẩn bị khác tại đây.
worker.start();
worker.join();
```

`unstarted` tạo thread ở trạng thái chưa bắt đầu. Gọi `start()` trên đối tượng thread để thực thi task. Một thread chỉ được start một lần; gọi `start()` lần thứ hai sẽ ném `IllegalThreadStateException`.

### 4.3. Tạo `ThreadFactory` với `factory`

`factory()` trả về một `ThreadFactory` tạo thread theo cấu hình của builder. Method `newThread(task)` của factory tạo thread chưa chạy; caller hoặc framework sẽ khởi chạy thread đó.

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("job-", 1)
        .factory();

Thread first = factory.newThread(() -> processJob(1));
Thread second = factory.newThread(() -> processJob(2));

first.start();
second.start();
```

Factory hữu ích khi API nhận một `ThreadFactory` thay vì nhận trực tiếp `Thread.Builder`. Cấu hình tên và handler được đặt một lần ở builder, sau đó dùng factory để tạo nhiều virtual thread.

## 5. Kế thừa `InheritableThreadLocal`

Theo mặc định, virtual thread kế thừa giá trị ban đầu của các `InheritableThreadLocal` từ thread tạo ra nó. Có thể tắt hành vi này bằng:

```java
Thread thread = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .start(() -> doWork());
```

Tùy chọn này chỉ điều khiển việc kế thừa **`InheritableThreadLocal`**. Nó không tự động sao chép mọi `ThreadLocal`, cũng không phải cơ chế truyền context tổng quát giữa các tác vụ.

Ví dụ:

```java
private static final InheritableThreadLocal<String> REQUEST_ID =
        new InheritableThreadLocal<>();

static void runRequest() throws InterruptedException {
    REQUEST_ID.set("req-42");

    Thread inherited = Thread.ofVirtual().start(() ->
            System.out.println(REQUEST_ID.get()));

    Thread isolated = Thread.ofVirtual()
            .inheritInheritableThreadLocals(false)
            .start(() -> System.out.println(REQUEST_ID.get()));

    // inherited thấy req-42; isolated nhận null nếu không tự thiết lập giá trị.
    inherited.join();
    isolated.join();
}
```

Trong ứng dụng thực tế, hãy cân nhắc dữ liệu nào cần kế thừa và vòng đời của dữ liệu đó. Kế thừa không thay thế cho việc thiết kế context rõ ràng; đặc biệt, không lưu trạng thái mutable dùng chung trong `InheritableThreadLocal` nếu nhiều tác vụ có thể truy cập đồng thời.

## 6. Xử lý exception chưa được bắt

`uncaughtExceptionHandler(handler)` cho phép cài `Thread.UncaughtExceptionHandler` cho các thread được tạo bởi builder. Handler được gọi khi task kết thúc do một exception thoát ra khỏi task mà không được bắt.

```java
Thread thread = Thread.ofVirtual()
        .name("payment-worker")
        .uncaughtExceptionHandler((t, error) -> {
            System.err.println("Thread: " + t.getName());
            error.printStackTrace();
        })
        .start(() -> {
            throw new IllegalStateException("Payment processing failed");
        });

thread.join();
```

Handler nhận hai đối số:

- `Thread t`: thread đã kết thúc bất thường.
- `Throwable error`: exception hoặc error chưa được task bắt.

Uncaught exception handler là điểm quan sát lỗi cuối cùng của thread. Nó không làm cho task tiếp tục chạy và cũng không tự chuyển exception về thread gọi `start()`. Nếu cần truyền kết quả hoặc lỗi về nơi điều phối task, hãy dùng abstraction phù hợp như `Future` thông qua `ExecutorService`.

Không nên chỉ ghi log rồi coi task là thành công. Ứng dụng cần xác định cách báo lỗi, retry hoặc hoàn tác theo nghiệp vụ ở tầng quản lý task.

## 7. Kết hợp builder với executor

Một ứng dụng có thể dùng `factory()` để truyền cấu hình virtual thread vào `Executors.newThreadPerTaskExecutor`. Executor này tạo một virtual thread mới cho mỗi task được submit; nó không phải pool tái sử dụng một nhóm virtual thread cố định.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofVirtual()
        .name("request-", 1)
        .factory();

try (ExecutorService executor =
             Executors.newThreadPerTaskExecutor(factory)) {
    executor.submit(() -> handleRequest("A"));
    executor.submit(() -> handleRequest("B"));
}
```

Khi dùng try-with-resources, `close()` chờ các task đã được submit hoàn tất theo hợp đồng của `ExecutorService`, rồi đóng executor. Trong ứng dụng server, vòng đời executor thường được quản lý ở cấp thành phần hoặc ứng dụng thay vì tạo một executor mới cho từng request.

Lưu ý: khi dùng `submit`, executor thường bọc task trong một `FutureTask` để lưu kết quả hoặc exception. Vì exception của task được giữ trong `Future`, nó không thoát khỏi `run()` của thread và `uncaughtExceptionHandler` thường không được gọi cho lỗi đó. Hãy kiểm tra `Future.get()` hoặc dùng cơ chế thu thập kết quả phù hợp để quan sát lỗi của task được submit.

Nếu không cần tùy chỉnh thread name hoặc handler, Java 21 cũng có `Executors.newVirtualThreadPerTaskExecutor()` như một factory tiện dụng. Dùng `Thread.ofVirtual().factory()` khi muốn kiểm soát cấu hình thread được tạo.

## 8. Những điểm riêng của virtual thread cần nhớ

- Virtual thread là daemon thread; chúng không giữ JVM sống khi mọi platform thread không-daemon đã kết thúc.
- Virtual thread không phải tài nguyên cần gom vào một pool nhỏ để tái sử dụng. Mô hình thông dụng là tạo một virtual thread cho mỗi task.
- `Thread.Builder.OfVirtual` chỉ cung cấp các tùy chọn phù hợp với virtual thread; không có các cấu hình riêng của platform thread như stack size hoặc lựa chọn daemon.
- Tên thread, uncaught exception handler và chính sách kế thừa `InheritableThreadLocal` có thể được thiết lập qua builder.
- Virtual thread vẫn tuân theo vòng đời thread: thread mới, được start, chạy và kết thúc; một thread không thể start nhiều lần.
- Không dùng `Thread.sleep` hoặc thao tác blocking như cách điều phối task nếu có abstraction cấp cao hơn phù hợp; virtual thread giúp blocking trở nên rẻ hơn nhưng không loại bỏ nhu cầu quản lý timeout, cancellation và giới hạn tài nguyên bên ngoài.

## 9. Chọn cách tạo virtual thread

| Nhu cầu | Cách dùng |
|---|---|
| Chạy một task ngay | `Thread.ofVirtual().start(task)` |
| Tạo thread nhưng quyết định thời điểm chạy sau | `Thread.ofVirtual().unstarted(task)` |
| Đặt tên cố định | `.name("worker")` |
| Tạo tên duy nhất theo prefix | `.name("worker-", 1)` |
| Không kế thừa `InheritableThreadLocal` | `.inheritInheritableThreadLocals(false)` |
| Ghi nhận lỗi không được bắt | `.uncaughtExceptionHandler(handler)` |
| Cung cấp thread factory cho executor | `.factory()` |
| Tạo một virtual thread cho mỗi task | `Executors.newThreadPerTaskExecutor(factory)` hoặc `Executors.newVirtualThreadPerTaskExecutor()` |

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `ofVirtual`, `Thread.Builder`, `Thread.Builder.OfVirtual` và vòng đời thread.
- [Java SE 21 API — `Thread.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): cấu hình tên, kế thừa thread-local, handler, `start`, `unstarted` và `factory`.
- [Java SE 21 API — `ThreadFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html): hợp đồng tạo thread cho executor và API đồng thời.
- [Java SE 21 API — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): các executor tạo virtual thread theo từng task.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): thiết kế và trạng thái chính thức của virtual thread trong Java 21.

`Thread.ofVirtual()` là điểm bắt đầu để cấu hình virtual thread bằng builder. Dùng `start` khi cần chạy ngay, `unstarted` khi muốn tự quyết định thời điểm chạy và `factory` khi tích hợp với executor hoặc API cần `ThreadFactory`. Hãy đặt tên dễ quan sát, xác định rõ chính sách kế thừa context và cài uncaught exception handler phù hợp với cách ứng dụng theo dõi lỗi.
