# Executors.newThreadPerTaskExecutor với ThreadFactory

`Executors.newThreadPerTaskExecutor(ThreadFactory)` tạo một `ExecutorService` khởi chạy một thread mới cho mỗi task được gửi vào. Điểm khác biệt của API này là ứng dụng cung cấp `ThreadFactory` để quyết định loại thread và cấu hình thread được tạo. Factory có thể tạo platform thread hoặc virtual thread, tùy nhu cầu của workload.

Trong Java 21, API này hữu ích khi muốn giữ mô hình thread-per-task nhưng cần tùy chỉnh cách tạo thread, chẳng hạn đặt tên thread hoặc chọn virtual thread. Nếu muốn dùng virtual thread với cấu hình mặc định, có thể dùng trực tiếp `Executors.newVirtualThreadPerTaskExecutor()`. Hai API đều tạo thread mới cho từng task; chúng không tạo một pool worker để tái sử dụng thread.

## 1. API và cách hoạt động

Cú pháp:

```java
ThreadFactory factory = ...;

ExecutorService executor =
        Executors.newThreadPerTaskExecutor(factory);
```

Phương thức nhận một đối tượng `ThreadFactory`. Mỗi khi executor nhận task, nó yêu cầu factory tạo một thread để thực thi task đó. Executor chịu trách nhiệm khởi chạy thread và quản lý vòng đời thực thi.

Các điểm chính:

- Mỗi task được thực thi trên một thread mới do factory cung cấp.
- Số thread mà executor tạo ra không bị giới hạn bởi một pool size cố định.
- Loại thread phụ thuộc vào `ThreadFactory`: platform thread hoặc virtual thread.
- Executor không tái sử dụng thread đã chạy xong cho task tiếp theo.
- Việc giới hạn tài nguyên hoặc số task đang được tiếp nhận là trách nhiệm riêng của ứng dụng.

`ThreadFactory` thuộc package `java.util.concurrent`. Đây là một interface dùng để tạo thread cho task. Java cung cấp factory thông qua các builder của `Thread`, vì vậy thường không cần tự cài đặt interface này.

## 2. Tạo executor với virtual thread factory

Trong Java 21, có thể tạo virtual thread factory bằng `Thread.ofVirtual().factory()`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class Main {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual().factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {

            var first = executor.submit(() -> {
                System.out.println("Virtual? "
                        + Thread.currentThread().isVirtual());
                return "profile loaded";
            });

            var second = executor.submit(() -> "orders loaded");

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }
}
```

Mỗi lần gọi `submit` tạo một virtual thread mới. Trong ví dụ, `Thread.currentThread().isVirtual()` trả về `true` khi task chạy trên virtual thread.

Factory chỉ tạo thread theo cấu hình đã chọn; executor vẫn đảm nhiệm việc khởi chạy thread cho từng task. Không gọi `start()` bên trong factory. Hãy trả về thread mới ở trạng thái chưa chạy để executor quản lý quá trình thực thi.

## 3. Đặt tên virtual thread bằng ThreadFactory

Một lý do phổ biến để truyền factory riêng là đặt tên thread giúp quan sát log, thread dump và công cụ chẩn đoán dễ hơn.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class Main {
    public static void main(String[] args) {
        ThreadFactory factory = Thread.ofVirtual()
                .name("request-", 0)
                .factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {

            for (int i = 0; i < 3; i++) {
                executor.submit(() ->
                        System.out.println(Thread.currentThread().getName()));
            }
        }
    }
}
```

Với prefix `request-` và bộ đếm bắt đầu từ 0, các thread được tạo có tên như `request-0`, `request-1`, `request-2`. Mỗi task vẫn có một virtual thread riêng.

Đặt tên thread hữu ích cho quan sát và chẩn đoán, nhưng tên thread không phải cơ chế định danh nghiệp vụ. Nếu cần theo dõi request hoặc job xuyên qua nhiều thành phần, hãy dùng request ID hoặc job ID riêng trong logging/tracing context.

## 4. Dùng platform thread factory

`ThreadFactory` không bắt buộc phải tạo virtual thread. Có thể dùng `Thread.ofPlatform().factory()` để tạo platform thread cho mỗi task:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class Main {
    public static void main(String[] args) {
        ThreadFactory factory = Thread.ofPlatform()
                .name("platform-task-", 0)
                .factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {

            executor.submit(() ->
                    System.out.println(Thread.currentThread()));
        }
    }
}
```

Trong trường hợp này, executor tạo một platform thread mới cho từng task. Cách làm có thể hữu ích khi cần hành vi của platform thread hoặc khi tích hợp với thành phần phụ thuộc vào platform thread. Tuy nhiên, tạo platform thread không giới hạn cho mỗi task có thể tiêu thụ nhiều tài nguyên hệ điều hành khi tải tăng cao.

Không nên chọn platform thread-per-task như một cách thay thế thread pool cho workload có số lượng task lớn. Nếu mục tiêu là xử lý đồng thời nhiều tác vụ blocking, virtual thread thường phù hợp hơn. Nếu mục tiêu là giới hạn mức song song CPU-bound, một executor có số platform worker được giới hạn thường phù hợp hơn.

## 5. So sánh với newVirtualThreadPerTaskExecutor

Java 21 cũng cung cấp `Executors.newVirtualThreadPerTaskExecutor()`. API này là cách thuận tiện để tạo executor chạy một virtual thread cho mỗi task mà không cần tự truyền factory.

Về cấu hình, nó tương đương với:

```java
Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().factory()
);
```

| API | Thread được tạo | Khi nên dùng |
|---|---|---|
| `newThreadPerTaskExecutor(factory)` | Theo loại thread do factory tạo | Cần chọn platform/virtual thread hoặc cấu hình factory |
| `newVirtualThreadPerTaskExecutor()` | Virtual thread | Muốn mô hình virtual thread-per-task mặc định |
| `newFixedThreadPool(n)` | Một số platform worker thread cố định theo mặc định | Cần giới hạn số worker chạy song song |

Nếu không cần tùy chỉnh factory, `newVirtualThreadPerTaskExecutor()` thường diễn đạt ý định rõ ràng hơn. Nếu cần đặt tên virtual thread hoặc cung cấp cấu hình factory riêng, `newThreadPerTaskExecutor(factory)` cho phép thực hiện điều đó.

Cả hai executor thread-per-task đều không giới hạn số thread theo một pool size. Không nên nhầm việc dùng `ExecutorService` với việc đang dùng thread pool: `ExecutorService` là abstraction quản lý việc thực thi task, còn chiến lược tạo và quản lý thread phụ thuộc implementation.

## 6. ThreadFactory có trách nhiệm gì?

`ThreadFactory` quyết định thread được tạo ra như thế nào. Factory có thể chọn loại thread và thiết lập một số thuộc tính trước khi thread được khởi chạy.

Ví dụ, factory tạo virtual thread có tên:

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("worker-", 1)
        .factory();
```

Một số thuộc tính có thể cấu hình thông qua `Thread.Builder` trước khi gọi `factory()`:

- Loại thread: `ofVirtual()` hoặc `ofPlatform()`.
- Tên thread: `name(prefix, start)` hoặc `name(name)`.
- Uncaught exception handler: `uncaughtExceptionHandler(...)`.
- Một số thuộc tính phù hợp khác được cung cấp bởi builder tương ứng.

Factory không phải nơi gửi task, chờ kết quả hay giới hạn concurrency. Những trách nhiệm đó thuộc executor hoặc cơ chế điều phối tải của ứng dụng.

Khi tự triển khai `ThreadFactory`, cần tuân thủ các nguyên tắc:

1. Tạo một đối tượng Thread mới cho mỗi lần được gọi.
2. Gắn đúng Runnable nhận được vào thread vừa tạo.
3. Trả về thread chưa được khởi chạy để executor gọi `start()`.
4. Không trả về cùng một thread cho nhiều task.
5. Không tự chạy task bên trong `newThread`; factory chỉ tạo thread.

Ví dụ factory tùy chỉnh đơn giản:

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

class NamedPlatformThreadFactory implements ThreadFactory {
    private final AtomicInteger sequence = new AtomicInteger();

    @Override
    public Thread newThread(Runnable task) {
        return Thread.ofPlatform()
                .name("job-" + sequence.getAndIncrement())
                .unstarted(task);
    }
}
```

Có thể truyền factory này cho `newThreadPerTaskExecutor`:

```java
try (var executor = Executors.newThreadPerTaskExecutor(
        new NamedPlatformThreadFactory())) {
    executor.submit(() -> processJob());
}
```

Ví dụ trên cố ý dùng platform thread để minh họa factory tự triển khai. Trong ứng dụng có nhiều tác vụ blocking, hãy cân nhắc factory virtual thread để tránh tạo số lượng lớn platform thread.

## 7. Quản lý vòng đời executor

Executor được tạo bằng `newThreadPerTaskExecutor` vẫn là `ExecutorService`, vì vậy có thể gửi task bằng `execute` hoặc `submit`, lấy kết quả qua `Future`, và quản lý shutdown theo API chuẩn.

Với Java 21, có thể dùng try-with-resources:

```java
try (var executor = Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().name("io-", 0).factory())) {

    var result = executor.submit(() -> loadRemoteData());
    System.out.println(result.get());
}
```

Khi thoát khỏi khối try, `close()` đóng executor: ngừng nhận task mới và chờ các task đã gửi hoàn thành. Điều này giúp tránh để executor tiếp tục sống ngoài phạm vi công việc dự kiến.

Nếu cần quản lý shutdown tường minh, có thể dùng `shutdown()`, `awaitTermination(...)` và `shutdownNow()` theo chính sách dừng của ứng dụng. Việc hủy task qua `Future.cancel(true)` gửi interrupt tới thread thực thi; code task cần phản hồi interruption phù hợp.

Không nên tạo executor mới cho từng request nhỏ rồi bỏ quên không đóng. Hãy xác định phạm vi vòng đời hợp lý cho nhóm task và đóng executor khi nhóm công việc hoàn tất.

## 8. Thread-per-task không tự giới hạn tài nguyên

Executor này tạo một thread cho mỗi task, vì vậy số thread có thể tăng theo số task được gửi. ThreadFactory chỉ quyết định loại và cấu hình thread; nó không giới hạn số task đồng thời và không tạo backpressure.

Với virtual thread, chi phí mỗi thread thấp nhưng mỗi task vẫn có thể giữ bộ nhớ, socket, request body hoặc chờ tài nguyên bên ngoài. Với platform thread, việc tạo số lượng lớn thread còn tạo áp lực đáng kể hơn lên hệ điều hành.

Nếu cần giới hạn số thao tác truy cập database, dùng semaphore hoặc connection pool:

```java
import java.util.concurrent.Semaphore;

class DatabaseGateway {
    private final Semaphore permits = new Semaphore(12);

    String load(String id) throws InterruptedException {
        permits.acquire();
        try {
            return query(id);
        } finally {
            permits.release();
        }
    }

    private String query(String id) {
        return "row-" + id;
    }
}
```

Khi dùng executor thread-per-task, mỗi task vẫn có thể được thực thi trên thread riêng; semaphore giới hạn số task đi vào đoạn truy cập database cùng lúc. Nếu cần giới hạn cả số task được tiếp nhận, hãy thiết kế admission control hoặc bounded queue ở tầng nhận công việc.

Không nên tạo một fixed pool gồm một số virtual thread worker chỉ để thay thế semaphore. Làm như vậy giới hạn tất cả task theo số worker, kể cả task không sử dụng tài nguyên đang cần bảo vệ.

## 9. Xử lý exception và theo dõi task

Khi dùng `submit`, executor trả về `Future`. Exception phát sinh trong task được lưu trong Future và được quan sát khi gọi `get()`:

```java
try (var executor = Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().factory())) {

    var result = executor.submit(() -> {
        throw new IllegalStateException("Không thể tải dữ liệu");
    });

    try {
        result.get();
    } catch (java.util.concurrent.ExecutionException ex) {
        System.err.println("Task thất bại: " + ex.getCause());
    }
}
```

Nếu dùng `execute(Runnable)`, task không có Future để lấy kết quả. Với thread factory có cấu hình uncaught exception handler, handler có thể nhận exception không được xử lý thoát ra khỏi task thread. Hãy chọn `submit` khi cần lấy kết quả hoặc quan sát exception thông qua Future.

ThreadFactory có thể cấu hình handler, nhưng handler không thay thế xử lý lỗi nghiệp vụ. Với `submit`, exception đã được giữ trong Future nên không nên kỳ vọng uncaught exception handler nhận exception đó. Ứng dụng cần đọc Future hoặc dùng cơ chế thu thập kết quả phù hợp để không bỏ sót lỗi.

## 10. Khi nào nên dùng newThreadPerTaskExecutor?

| Nhu cầu | Lựa chọn |
|---|---|
| Một task cần một virtual thread riêng và không cần cấu hình thêm | `newVirtualThreadPerTaskExecutor()` |
| Một task cần một virtual thread riêng, có tên hoặc handler tùy chỉnh | `newThreadPerTaskExecutor(Thread.ofVirtual()...factory())` |
| Một task cần platform thread riêng với cấu hình riêng | `newThreadPerTaskExecutor(Thread.ofPlatform()...factory())`, chỉ khi tải và tài nguyên cho phép |
| Cần giới hạn số platform worker cho CPU-bound task | Executor có số worker giới hạn |
| Cần giới hạn số truy cập database/API đồng thời | Thread-per-task kết hợp Semaphore, connection pool hoặc rate limiter |
| Cần giới hạn lượng task chờ được nhận | Admission control hoặc bounded queue |

## 11. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ `newThreadPerTaskExecutor` là thread pool | Nhầm ExecutorService với chiến lược worker pool | Nhớ rằng mỗi task nhận một thread mới |
| Factory tạo platform thread cho workload I/O rất lớn | Platform thread tiêu tốn tài nguyên hệ điều hành | Cân nhắc virtual thread factory |
| Factory trả lại cùng một Thread cho nhiều task | Một Thread không thể được khởi chạy lại sau khi kết thúc | Tạo thread mới cho mỗi lần gọi factory |
| Gọi `start()` bên trong factory | Executor cũng chịu trách nhiệm khởi chạy thread | Trả về thread chưa chạy |
| Nghĩ ThreadFactory giới hạn concurrency | Factory chỉ tạo và cấu hình thread | Dùng semaphore, admission control hoặc bounded queue |
| Không đóng executor | Task và thread có thể tồn tại ngoài phạm vi mong muốn | Dùng try-with-resources hoặc shutdown rõ ràng |
| Dùng uncaught exception handler để nhận lỗi từ mọi task submit | `submit` lưu exception trong Future | Kiểm tra Future hoặc thu thập kết quả task |

## 12. Quy tắc sử dụng trong Java 21

Khi sử dụng `Executors.newThreadPerTaskExecutor(ThreadFactory)`, hãy xác định trước loại thread cần dùng:

1. Chọn `Thread.ofVirtual().factory()` cho workload có nhiều task blocking và cần concurrency cao.
2. Chọn `Thread.ofPlatform().factory()` khi thực sự cần platform thread riêng cho mỗi task và đã tính đến giới hạn tài nguyên.
3. Dùng `Thread.Builder` để đặt tên hoặc cấu hình thread trước khi tạo factory.
4. Bảo đảm factory trả về một thread mới, chưa được khởi chạy cho mỗi task.
5. Dùng `newVirtualThreadPerTaskExecutor()` nếu không cần tùy chỉnh factory.
6. Giới hạn tài nguyên ở đúng điểm sử dụng bằng semaphore, connection pool hoặc rate limiter.
7. Quản lý vòng đời executor, Future và interruption rõ ràng.

`newThreadPerTaskExecutor(ThreadFactory)` tách biệt chính sách tạo thread khỏi logic thực thi task. Nhờ đó, cùng một mô hình executor có thể sử dụng platform thread hoặc virtual thread theo cấu hình factory. Trong Java 21, kết hợp API này với virtual thread factory là cách linh hoạt để áp dụng thread-per-task và vẫn giữ quyền kiểm soát tên cũng như một số thuộc tính của thread.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — Executors.newThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newThreadPerTaskExecutor(java.util.concurrent.ThreadFactory))
- [Oracle Java SE 21 API — ThreadFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html)
- [Oracle Java SE 21 API — Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html)
- [Oracle Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
