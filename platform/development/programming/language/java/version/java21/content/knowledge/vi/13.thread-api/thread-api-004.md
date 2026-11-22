# Đặt tên thread, số thứ tự và tạo ThreadFactory

Tên thread giúp nhận diện luồng thực thi trong log, debugger, thread dump và công cụ giám sát. Khi ứng dụng tạo nhiều worker, chỉ dùng tên mặc định thường khó biết thread nào thuộc nhóm xử lý nào. Java cung cấp Thread Builder và `ThreadFactory` để đặt tên nhất quán, thêm số thứ tự và đưa quy tắc tạo thread vào executor.

Trong Java 21, có thể tạo platform thread hoặc virtual thread bằng các builder `Thread.ofPlatform()` và `Thread.ofVirtual()`. Cả hai đều hỗ trợ đặt tên; builder còn có thể tạo một `ThreadFactory` dùng lại cho nhiều thread. Bài này tập trung vào cách đặt tên có quy tắc và tích hợp factory với `ExecutorService`.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đặt tên cho platform thread và virtual thread trước khi chúng chạy.
- Tạo tên có tiền tố và số thứ tự tăng dần bằng Thread Builder.
- Giải thích vai trò của `ThreadFactory` và vì sao factory trả về thread chưa được start.
- Truyền ThreadFactory vào executor để quản lý tên worker thống nhất.
- Chọn cách đặt tên phù hợp với thread pool và mô hình virtual thread per task.
- Tránh dùng tên thread làm định danh nghiệp vụ hoặc cơ chế đồng bộ.

## 1. Vì sao nên đặt tên thread?

Một ứng dụng server có thể có nhiều loại thread: xử lý HTTP request, ghi log, đồng bộ dữ liệu, chạy tác vụ nền hoặc giao tiếp với dịch vụ khác. Khi sự cố xảy ra, tên thread giúp nhận diện vai trò của thread trong các công cụ quan sát.

Ví dụ, các tên sau dễ đọc hơn một dãy tên mặc định:

```text
http-worker-1
http-worker-2
report-export-1
virtual-request-42
```

Tên thread hữu ích khi:

- Đọc log có in `Thread.currentThread().getName()`.
- Phân tích thread dump để tìm nhóm thread đang chờ hoặc bị block.
- Xem thread trong debugger hoặc profiler.
- Xác định executor nào đang chạy một tác vụ.
- Tìm lỗi chỉ xuất hiện ở một loại worker cụ thể.

Tên thread chỉ là thông tin chẩn đoán. Không nên dùng tên để quyết định quyền truy cập, trạng thái nghiệp vụ, thứ tự xử lý hoặc tính duy nhất của một request. Những mục đích đó cần ID và dữ liệu nghiệp vụ riêng.

## 2. Đặt tên cho thread trực tiếp bằng Thread Builder

Java 21 cung cấp hai builder chính:

- `Thread.ofPlatform()` tạo builder cho platform thread.
- `Thread.ofVirtual()` tạo builder cho virtual thread.

Đặt tên bằng `name(String)` rồi tạo và chạy thread bằng `start(Runnable)`:

```java
Thread worker = Thread.ofPlatform()
    .name("report-worker")
    .start(() -> {
        System.out.println(Thread.currentThread().getName());
        generateReport();
    });
```

Tên được thiết lập trước khi thread bắt đầu chạy. Cách này giúp tên đã đúng ngay từ những log đầu tiên của tác vụ.

Virtual thread cũng có thể được đặt tên tương tự:

```java
Thread requestThread = Thread.ofVirtual()
    .name("request-handler")
    .start(() -> handleRequest());
```

Không cần thay đổi cách đọc tên: cả platform thread và virtual thread đều có thể được quan sát bằng `Thread.currentThread().getName()`.

## 3. Tạo tên có tiền tố và số thứ tự

Khi một ứng dụng tạo nhiều thread cùng vai trò, tên nên có tiền tố chung và số thứ tự riêng. Thread Builder hỗ trợ trực tiếp bằng `name(String prefix, long start)`.

```java
Thread worker1 = Thread.ofPlatform()
    .name("image-worker-", 1)
    .start(() -> processImage("a.png"));

Thread worker2 = Thread.ofPlatform()
    .name("image-worker-", 1)
    .start(() -> processImage("b.png"));
```

Hai builder được tạo riêng và đều bắt đầu ở số 1, vì vậy ví dụ này có thể tạo ra hai thread trùng tên. Khi muốn một dãy tên không trùng trong cùng nhóm, hãy tạo một builder và dùng nó để tạo nhiều thread, hoặc tạo một factory từ builder đó.

Ví dụ dùng ThreadFactory:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory imageFactory = Thread.ofPlatform()
    .name("image-worker-", 1)
    .factory();

Thread worker1 = imageFactory.newThread(() -> processImage("a.png"));
Thread worker2 = imageFactory.newThread(() -> processImage("b.png"));

worker1.start();
worker2.start();
```

Các thread được tạo từ cùng factory lần lượt nhận tên `image-worker-1`, `image-worker-2`, ... . Factory giữ quy tắc đánh số trong quá trình tạo thread; mỗi lần gọi `newThread` tạo một thread mới chưa chạy.

### 3.1. Dãy số được tăng theo số thread được tạo

Số thứ tự trong tên phản ánh số thread mà builder/factory đã tạo, không phải số tác vụ mà thread thực hiện.

Ví dụ, một fixed thread pool có bốn worker có thể chạy hàng nghìn tác vụ nhưng vẫn chỉ dùng các thread mang tên `api-worker-1` đến `api-worker-4`. Các worker được tái sử dụng cho nhiều tác vụ.

Nếu tạo một thread mới cho mỗi tác vụ, mỗi thread mới sẽ nhận số thứ tự tiếp theo. Vì vậy, hãy chọn tiền tố tên theo đơn vị mà bạn muốn quan sát: nhóm worker, loại tác vụ hay thread-per-task.

### 3.2. Tránh trùng tên giữa các factory

Mỗi builder/factory có bộ đếm tên riêng. Nếu tạo hai factory cùng tiền tố và cùng số bắt đầu, chúng có thể tạo ra các thread trùng tên:

```java
ThreadFactory first = Thread.ofPlatform().name("worker-", 1).factory();
ThreadFactory second = Thread.ofPlatform().name("worker-", 1).factory();
```

Nếu các nhóm cần phân biệt trong log, dùng tiền tố khác nhau (`billing-worker-`, `search-worker-`) hoặc chia sẻ một bộ đếm khi thật sự cần một dãy tên chung. Không cần bảo đảm tên duy nhất toàn JVM nếu tên chỉ phục vụ chẩn đoán; điều quan trọng là tránh gây nhầm lẫn trong phạm vi vận hành.

## 4. ThreadFactory là gì?

`ThreadFactory` là interface trong `java.util.concurrent` có một phương thức:

```java
Thread newThread(Runnable task);
```

Nó đóng gói quy tắc tạo thread. Thành phần sử dụng factory không cần biết cách đặt tên, chọn platform hay virtual thread, cấu hình daemon hoặc gắn handler; nó chỉ yêu cầu factory tạo một thread để chạy tác vụ.

Một factory phải trả về thread mới ở trạng thái chưa được start. Executor sẽ quản lý thời điểm gọi `start()` và vòng đời worker. Không tự gọi `start()` bên trong `newThread`, vì như vậy thread có thể chạy trước khi executor hoàn tất việc quản lý nó.

Java có factory mặc định qua `Executors.defaultThreadFactory()`. Các phương thức tạo executor không nhận factory thường sử dụng factory mặc định phù hợp với executor. Khi cần quy tắc đặt tên riêng hoặc cấu hình thread riêng, truyền factory tường minh vào overload tương ứng.

## 5. Dùng ThreadFactory với ExecutorService

ExecutorService tách việc gửi tác vụ khỏi cách tạo và quản lý thread. Các factory method như `Executors.newFixedThreadPool` có overload nhận `ThreadFactory`.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory workerFactory = Thread.ofPlatform()
    .name("email-worker-", 1)
    .factory();

try (ExecutorService executor =
         Executors.newFixedThreadPool(3, workerFactory)) {
    for (int i = 1; i <= 6; i++) {
        int emailId = i;
        executor.submit(() -> {
            System.out.printf("%s xử lý email %d%n",
                Thread.currentThread().getName(), emailId);
            sendEmail(emailId);
        });
    }
}
```

Executor gọi factory khi cần tạo worker. Với fixed thread pool, một worker thường được tái sử dụng để chạy nhiều tác vụ. Tên vì thế mô tả worker thread chứ không mô tả email hoặc tác vụ riêng lẻ.

Từ Java 19, `ExecutorService` triển khai `AutoCloseable`; trong Java 21 có thể dùng try-with-resources như ví dụ trên. Khi đóng executor, nó ngừng nhận tác vụ mới và chờ các tác vụ đã gửi hoàn tất theo hợp đồng `close()`.

### 5.1. Đặt tên và cấu hình platform worker

Builder cho platform thread cho phép cấu hình thêm thuộc tính trước khi tạo factory, ví dụ daemon status hoặc uncaught exception handler:

```java
ThreadFactory backgroundFactory = Thread.ofPlatform()
    .name("cache-refresh-", 1)
    .daemon(true)
    .uncaughtExceptionHandler((thread, error) ->
        System.err.printf("Lỗi không được xử lý trên %s: %s%n",
            thread.getName(), error))
    .factory();
```

Chọn daemon status theo vòng đời ứng dụng. Daemon thread không giữ JVM sống khi các thread non-daemon đã kết thúc, vì vậy không dùng daemon thread cho tác vụ cần bảo đảm hoàn tất trước khi ứng dụng thoát.

Uncaught exception handler xử lý ngoại lệ thoát ra khỏi `run()` của thread. Với tác vụ gửi bằng `submit()`, executor thường giữ ngoại lệ trong `Future`; handler của thread không phải nơi nhận mọi exception của tác vụ. Hãy đọc kết quả `Future` hoặc dùng cơ chế xử lý lỗi của executor khi cần quan sát lỗi từ tác vụ.

## 6. Tạo ThreadFactory bằng AtomicLong khi cần quy tắc riêng

Thread Builder đã hỗ trợ tiền tố và số thứ tự. Nếu quy tắc đặt tên phức tạp hơn, có thể tự cài đặt `ThreadFactory` và dùng `AtomicLong` để tạo số thứ tự an toàn khi nhiều thread cùng yêu cầu tạo worker.

```java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicLong;

static ThreadFactory namedPlatformFactory(String prefix) {
    AtomicLong sequence = new AtomicLong(1);

    return task -> Thread.ofPlatform()
        .name(prefix + sequence.getAndIncrement())
        .unstarted(task);
}
```

Sử dụng:

```java
ThreadFactory factory = namedPlatformFactory("payment-worker-");

Thread first = factory.newThread(() -> processPayment("P-100"));
Thread second = factory.newThread(() -> processPayment("P-101"));

first.start();
second.start();
```

`AtomicLong` bảo đảm việc lấy số tăng dần là an toàn khi nhiều luồng gọi factory đồng thời. `unstarted(task)` tạo thread nhưng không chạy nó; bên gọi chịu trách nhiệm start thread. Trong executor, executor đảm nhiệm bước đó.

Chỉ nên tự cài factory khi có nhu cầu cụ thể như mã nhóm, định dạng tên riêng hoặc cấu hình phụ thuộc ứng dụng. Nếu chỉ cần tiền tố và số thứ tự, `Thread.ofPlatform().name(prefix, start).factory()` ngắn và ít mã hơn.

## 7. Tạo ThreadFactory cho virtual thread

Virtual thread cũng hỗ trợ tên và factory:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory virtualFactory = Thread.ofVirtual()
    .name("request-", 1)
    .factory();
```

Factory này tạo virtual thread chưa start, có tên lần lượt `request-1`, `request-2`, ... . Có thể dùng với executor tạo một thread cho mỗi tác vụ:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
         Executors.newThreadPerTaskExecutor(virtualFactory)) {
    for (int i = 1; i <= 100; i++) {
        int requestId = i;
        executor.submit(() -> handleRequest(requestId));
    }
}
```

Mỗi tác vụ được chạy trên một virtual thread mới do factory tạo. Đây là mô hình phù hợp với tác vụ có nhiều thời gian chờ I/O và cần cách viết tuần tự dễ đọc.

Nếu không cần tên tùy chỉnh hoặc cấu hình factory riêng, Java 21 cung cấp `Executors.newVirtualThreadPerTaskExecutor()` như một lựa chọn ngắn gọn để tạo executor virtual-thread-per-task.

### 7.1. Virtual thread có một số giới hạn cấu hình riêng

Virtual thread luôn là daemon thread và có mức ưu tiên cố định. Không dùng cấu hình daemon hoặc priority để điều khiển lịch chạy virtual thread. Hãy quản lý vòng đời tác vụ qua `ExecutorService`, `Future`, cancellation và các cơ chế đồng bộ phù hợp.

Virtual thread được thiết kế theo mô hình một thread cho mỗi tác vụ; thông thường không cần tạo pool để tái sử dụng virtual thread. Nếu cần giới hạn số lượng truy cập đồng thời vào một tài nguyên, hãy giới hạn tài nguyên bằng semaphore hoặc cơ chế phù hợp thay vì cố định số virtual thread trong một pool.

## 8. So sánh các cách tạo thread và factory

| Cách làm | Kết quả | Khi nên dùng |
|---|---|---|
| `Thread.ofPlatform().name(...).start(task)` | Tạo và chạy một platform thread | Một thread độc lập có vòng đời rõ ràng |
| `Thread.ofVirtual().name(...).start(task)` | Tạo và chạy một virtual thread | Một tác vụ độc lập, thường chờ I/O |
| `Thread.ofPlatform().name(prefix, start).factory()` | Factory tạo platform thread có tên tuần tự | Executor dùng platform worker |
| `Thread.ofVirtual().name(prefix, start).factory()` | Factory tạo virtual thread có tên tuần tự | Executor thread-per-task tùy chỉnh |
| `Executors.defaultThreadFactory()` | Factory mặc định cho platform worker | Không cần quy tắc đặt tên hoặc cấu hình riêng |
| `Executors.newVirtualThreadPerTaskExecutor()` | Executor tạo virtual thread cho từng tác vụ | Dùng virtual thread mặc định của JDK 21 |

Không nên chọn platform hay virtual thread chỉ dựa trên tên. Quyết định cần dựa vào loại công việc, tương tác blocking, thư viện đang sử dụng, yêu cầu tài nguyên và mô hình quản lý concurrency của ứng dụng.

## 9. Quy tắc đặt tên thực tế

Một quy ước tên tốt thường có cấu trúc:

```text
<application-or-subsystem>-<role>-<sequence>
```

Ví dụ:

```text
orders-db-worker-1
orders-db-worker-2
report-export-1
http-request-virtual-15
```

Một số nguyên tắc nên áp dụng:

- Dùng tiền tố ngắn thể hiện subsystem hoặc vai trò của thread.
- Dùng cùng một quy ước cho các thread thuộc cùng nhóm.
- Dùng bộ đếm nếu cần phân biệt các thread được tạo từ cùng factory.
- Dùng tiền tố khác nhau cho các factory độc lập nếu log có thể xuất hiện đồng thời.
- Không đưa token, mật khẩu, dữ liệu cá nhân hoặc thông tin nhạy cảm vào tên thread.
- Không dùng tên thread làm khóa nghiệp vụ, ID request hoặc điều kiện đồng bộ.
- Đặt tên trước khi start để tránh log ban đầu xuất hiện với tên chưa đúng.
- Nhớ rằng worker trong pool được tái sử dụng; tên worker không phải tên task.

Nếu cần một ID kỹ thuật cho vòng đời thread, Java cung cấp `Thread.threadId()`. ID này khác với tên thread: tên là nhãn có thể cấu hình, còn thread ID là giá trị định danh do runtime cung cấp trong vòng đời thread. Không thay thế ID của request hoặc tác vụ bằng thread ID vì một thread pool worker có thể xử lý nhiều request khác nhau.

## 10. Kiểm tra và chẩn đoán

Khi tên thread không như mong đợi, kiểm tra theo thứ tự:

1. Xác định thread được tạo trực tiếp bằng builder hay do executor gọi `ThreadFactory`.
2. Kiểm tra factory có được tạo một lần và tái sử dụng hay mỗi lần lại tạo factory mới với cùng prefix/start.
3. Xác định bộ đếm đang đếm thread được tạo hay số tác vụ được gửi.
4. In `Thread.currentThread().getName()` bên trong tác vụ để xác nhận thread thực sự chạy tác vụ.
5. Kiểm tra executor có dùng overload nhận factory hay đang dùng factory mặc định.
6. Với virtual thread, xác nhận executor đang dùng factory virtual hoặc `newVirtualThreadPerTaskExecutor()`.

Ví dụ kiểm tra đơn giản:

```java
Runnable task = () -> {
    Thread current = Thread.currentThread();
    System.out.printf("name=%s, id=%d%n",
        current.getName(), current.threadId());
};

Thread.ofPlatform().name("diagnostic-worker").start(task);
Thread.ofVirtual().name("diagnostic-virtual").start(task);
```

Đầu ra cho thấy tên và ID của thread đang chạy. Giá trị ID cụ thể do runtime cấp và không nên được hard-code trong kiểm thử.

## 11. Nguyên tắc thiết kế

- Dùng Thread Builder để đặt tên ngay khi tạo thread.
- Dùng `name(prefix, start)` để tạo dãy tên tự động từ một builder hoặc factory dùng chung.
- Dùng `ThreadFactory` để đóng gói quy tắc tạo thread cho executor.
- Để factory trả về thread chưa start; executor hoặc bên gọi quản lý việc start.
- Dùng factory platform cho worker pool khi cần số lượng worker giới hạn.
- Dùng virtual thread per task cho tác vụ phù hợp; không tạo pool chỉ để tái sử dụng virtual thread.
- Dùng `AtomicLong` khi tự cài quy tắc đánh số cần an toàn luồng.
- Xem tên thread là thông tin chẩn đoán, không phải định danh nghiệp vụ hoặc cơ chế điều khiển chương trình.

Đặt tên thread và dùng `ThreadFactory` giúp thống nhất cách tạo worker trên toàn ứng dụng. Khi kết hợp Thread Builder với executor phù hợp, mã nguồn có thể giữ quy tắc đặt tên rõ ràng, hỗ trợ quan sát vận hành và phân biệt platform thread với virtual thread trong Java 21.

## Tài liệu tham khảo

- [Java SE 21 API — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): platform/virtual thread, Thread Builder, `threadId()` và tên thread.
- [Java SE 21 API — `Thread.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): `name`, `unstarted`, `start` và `factory`.
- [Java SE 21 API — `ThreadFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html): hợp đồng tạo thread cho executor.
- [Java SE 21 API — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): factory method cho executor và virtual-thread-per-task executor.
- [Java SE 21 API — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời executor và `close()`.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads được hoàn thiện trong Java 21.
