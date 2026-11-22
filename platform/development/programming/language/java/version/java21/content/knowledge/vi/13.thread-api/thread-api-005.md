# Thread.ofPlatform khi cần cấu hình platform thread

Java 21 cung cấp `Thread.ofPlatform()` để tạo platform thread bằng một builder. Builder cho phép đặt tên thread, cấu hình daemon, priority, thread group, stack size, chính sách kế thừa `InheritableThreadLocal` và bộ xử lý exception không được bắt. Từ cùng builder, có thể tạo và chạy thread ngay, tạo thread chưa chạy, hoặc tạo `ThreadFactory` để tích hợp với executor.

Platform thread vẫn cần thiết khi ứng dụng cần một thread gắn với tài nguyên hoặc hành vi của hệ điều hành, cần cấu hình các thuộc tính riêng của platform thread, hoặc cần dùng một nhóm worker có số lượng được kiểm soát. API builder này là API chính thức trong Java 21, không phải preview feature.

## 1. Platform thread là gì và khi nào nên dùng?

Platform thread là thread được JVM ánh xạ trực tiếp tới thread của hệ điều hành trong các triển khai JVM thông dụng. Hệ điều hành chịu trách nhiệm lập lịch thực thi platform thread. Mỗi platform thread thường cần tài nguyên native như stack và cấu trúc quản lý thread, vì vậy tạo số lượng rất lớn có thể tiêu tốn đáng kể bộ nhớ và tài nguyên hệ thống.

Các trường hợp phù hợp với platform thread:

- Một số lượng worker hữu hạn, được kiểm soát, chẳng hạn pool xử lý tác vụ CPU-bound.
- Tác vụ cần tương tác với API native hoặc thư viện phụ thuộc vào đặc tính của OS thread.
- Tác vụ cần cấu hình priority, daemon, thread group hoặc stack size của platform thread.
- Thread nền có vòng đời dài, có tên rõ ràng để theo dõi trong log, debugger và công cụ giám sát.
- Tích hợp với API hiện có nhận `ThreadFactory` và cần factory tạo platform thread theo cấu hình riêng.

Nếu ứng dụng cần chạy hàng chục nghìn tác vụ chờ I/O đồng thời, virtual thread thường là lựa chọn phù hợp hơn vì chi phí mỗi thread thấp hơn. Với tác vụ CPU-bound, virtual thread không làm tăng số lõi xử lý; một pool platform thread có kích thước hợp lý thường dễ kiểm soát hơn. Việc chọn loại thread cần dựa trên đặc điểm workload và yêu cầu tích hợp, không chỉ dựa trên số lượng thread mong muốn.

## 2. Tạo platform thread bằng Thread.ofPlatform

`Thread.ofPlatform()` trả về một `Thread.Builder.OfPlatform`. Có thể cấu hình builder rồi gọi `start(task)` để tạo và khởi chạy thread:

```java
Thread worker = Thread.ofPlatform()
        .name("report-worker")
        .start(() -> {
            System.out.println("Running on " + Thread.currentThread());
            generateReport();
        });
```

`start(Runnable)` tạo một thread mới và lập lịch để nó thực thi task. Phương thức trả về chính đối tượng `Thread` đã được khởi chạy; có thể dùng đối tượng này để gọi `join()`, `interrupt()`, kiểm tra trạng thái hoặc đọc tên thread.

Nếu muốn tạo thread trước rồi tự quyết định thời điểm chạy, dùng `unstarted(task)`:

```java
Thread worker = Thread.ofPlatform()
        .name("delayed-worker")
        .unstarted(() -> processBatch());

prepareResources();
worker.start();
```

`unstarted` chỉ tạo thread ở trạng thái chưa chạy. Task bắt đầu sau khi gọi `start()` trên đối tượng trả về. Một đối tượng `Thread` chỉ có thể được start một lần; nếu cần thực hiện task lần nữa, hãy tạo thread mới từ builder hoặc dùng executor.

## 3. Cấu hình các thuộc tính của platform thread

`Thread.Builder.OfPlatform` mở rộng `Thread.Builder` và cung cấp các cấu hình riêng cho platform thread. Các lời gọi cấu hình trả lại builder để có thể nối chuỗi.

### Đặt tên thread

Có thể đặt một tên cố định:

```java
Thread worker = Thread.ofPlatform()
        .name("image-processor")
        .start(() -> processImage());
```

Khi tạo nhiều thread cùng vai trò, dùng tên có prefix và bộ đếm:

```java
Thread.Builder.OfPlatform builder = Thread.ofPlatform()
        .name("image-worker-", 1);

Thread first = builder.start(() -> processImage("one.png"));
Thread second = builder.start(() -> processImage("two.png"));
```

Tên được tạo bằng cách nối prefix với giá trị bộ đếm. Bộ đếm tăng sau mỗi lần builder tạo thread, giúp log dễ phân biệt worker. Với `ThreadFactory` được tạo từ builder này, factory có bản sao bộ đếm riêng bắt đầu từ giá trị hiện tại khi factory được tạo.

### Cấu hình daemon

Platform thread mặc định kế thừa trạng thái daemon từ thread tạo ra nó. Có thể đặt rõ trạng thái:

```java
Thread background = Thread.ofPlatform()
        .name("metrics-reporter")
        .daemon(true)
        .start(() -> reportMetrics());
```

Thread daemon không giữ JVM tiếp tục chạy khi tất cả thread non-daemon đã kết thúc. Vì vậy, chỉ dùng daemon cho công việc nền có thể bị dừng khi tiến trình thoát, chẳng hạn tác vụ giám sát phụ trợ. Với công việc cần hoàn tất hoặc cần đóng tài nguyên có trật tự, hãy dùng non-daemon thread và cơ chế shutdown/join rõ ràng.

`daemon()` không tham số là cách viết tắt của `daemon(true)`. Có thể dùng `daemon(false)` để yêu cầu thread non-daemon. Trạng thái daemon phải được thiết lập trước khi thread bắt đầu chạy.

### Cấu hình priority

`priority(int)` đặt priority trong phạm vi từ `Thread.MIN_PRIORITY` đến `Thread.MAX_PRIORITY`:

```java
Thread worker = Thread.ofPlatform()
        .name("maintenance-worker")
        .priority(Thread.NORM_PRIORITY)
        .start(() -> performMaintenance());
```

Priority mặc định được kế thừa từ thread tạo ra thread mới. Giá trị priority có thể ảnh hưởng cách JVM và hệ điều hành lập lịch, nhưng mức độ ảnh hưởng phụ thuộc nền tảng và môi trường chạy. Không dùng priority để bảo đảm thứ tự thực thi, fairness hoặc đồng bộ dữ liệu. Nếu truyền giá trị ngoài phạm vi hợp lệ, builder ném `IllegalArgumentException`.

### Chọn ThreadGroup

`group(ThreadGroup)` chỉ định nhóm cho platform thread:

```java
ThreadGroup group = new ThreadGroup("batch-workers");

Thread worker = Thread.ofPlatform()
        .group(group)
        .name("batch-worker")
        .start(() -> runBatch());
```

Nếu không chỉ định, thread thường kế thừa group từ thread tạo ra nó. `ThreadGroup` chủ yếu hữu ích khi tích hợp với hệ thống cũ hoặc công cụ quản lý thread đang dùng group; phần lớn ứng dụng hiện đại có thể quản lý worker bằng executor và `ThreadFactory` thay vì tự xây dựng cây group.

### Điều chỉnh stack size

`stackSize(long)` truyền kích thước stack mong muốn cho JVM khi tạo platform thread:

```java
Thread worker = Thread.ofPlatform()
        .name("deep-parser")
        .stackSize(2L * 1024 * 1024)
        .start(() -> parseDeepStructure());
```

Đơn vị là byte. Giá trị `0` được bỏ qua; giá trị âm gây `IllegalArgumentException`. Đây chỉ là gợi ý cho JVM: tác động phụ thuộc nền tảng, JVM có thể áp dụng giới hạn tối thiểu/tối đa hoặc không dùng đúng giá trị được yêu cầu. Không nên điều chỉnh stack size theo cảm tính; chỉ cân nhắc khi đã đo đạc workload, hiểu yêu cầu đệ quy và kiểm thử trên môi trường triển khai.

### Kiểm soát kế thừa InheritableThreadLocal

Theo mặc định, thread mới kế thừa giá trị khởi tạo của các biến `InheritableThreadLocal` từ thread tạo ra nó. Có thể tắt việc kế thừa này:

```java
Thread isolatedWorker = Thread.ofPlatform()
        .name("isolated-worker")
        .inheritInheritableThreadLocals(false)
        .start(() -> performIsolatedWork());
```

Tùy chọn này chỉ liên quan đến `InheritableThreadLocal`; nó không tự động sao chép hoặc xóa các `ThreadLocal` thông thường, cũng không phải cơ chế truyền context tổng quát. JDK mặc định kế thừa các giá trị ban đầu, bao gồm context class loader theo quy tắc kế thừa thread. Tắt kế thừa có thể ảnh hưởng thư viện đang trông đợi context được truyền xuống thread con, nên chỉ làm khi đã hiểu rõ context nào cần thiết.

### Xử lý exception không được bắt

`uncaughtExceptionHandler` đặt handler được gọi khi task kết thúc do một exception thoát khỏi `run()` mà không được bắt:

```java
Thread worker = Thread.ofPlatform()
        .name("import-worker")
        .uncaughtExceptionHandler((thread, error) -> {
            System.err.println("Thread failed: " + thread.getName());
            error.printStackTrace();
        })
        .start(() -> importData());
```

Handler này giúp ghi log hoặc phát tín hiệu giám sát cho lỗi không được xử lý. Nó không thay thế `try/catch` trong task, không xử lý exception đã được task bắt, và không tự khởi động lại công việc thất bại. Nếu cần retry hoặc quản lý kết quả tác vụ, hãy dùng cơ chế ở tầng ứng dụng hoặc `Future`/executor.

## 4. Bảng tóm tắt cấu hình

| Phương thức builder | Công dụng | Ghi chú |
|---|---|---|
| `name(String)` | Đặt tên thread | Hữu ích cho log và giám sát |
| `name(String, long)` | Đặt prefix và bộ đếm tên | Bộ đếm bắt đầu từ số không âm |
| `daemon(boolean)` / `daemon()` | Đặt daemon status | Mặc định kế thừa từ thread tạo |
| `priority(int)` | Đặt priority | Không bảo đảm thứ tự hoặc fairness |
| `group(ThreadGroup)` | Chọn thread group | Thường chỉ cần khi tích hợp hệ thống dùng group |
| `stackSize(long)` | Đưa ra gợi ý stack size | Phụ thuộc JVM và hệ điều hành |
| `inheritInheritableThreadLocals(boolean)` | Bật/tắt kế thừa InheritableThreadLocal | Mặc định là `true` |
| `uncaughtExceptionHandler(handler)` | Xử lý exception thoát khỏi task | Không thay thế xử lý lỗi nghiệp vụ |

Các thuộc tính không được đặt tường minh thường kế thừa giá trị mặc định hoặc giá trị từ thread tạo theo hợp đồng của `Thread`. Nếu cần hành vi ổn định giữa các môi trường, hãy đặt rõ các thuộc tính có ý nghĩa với ứng dụng thay vì dựa vào ngữ cảnh tạo thread.

## 5. Tạo ThreadFactory từ builder

Khi cần tạo nhiều platform thread theo cùng một cấu hình, có thể gọi `factory()`:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofPlatform()
        .name("api-worker-", 1)
        .daemon(false)
        .uncaughtExceptionHandler((thread, error) ->
                System.err.println(thread.getName() + ": " + error))
        .factory();

Thread first = factory.newThread(() -> handleRequest("A"));
Thread second = factory.newThread(() -> handleRequest("B"));

first.start();
second.start();
```

`factory()` tạo `ThreadFactory` áp dụng trạng thái builder tại thời điểm tạo factory. Factory trả về được thiết kế để có thể được nhiều thread gọi đồng thời. Mỗi lần `newThread(task)` tạo một thread mới nhưng chưa chạy; caller hoặc executor chịu trách nhiệm gọi `start()`.

### Kết hợp với ExecutorService

Nhiều API executor nhận `ThreadFactory`, cho phép cấu hình platform thread ở một nơi rồi dùng lại:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofPlatform()
        .name("report-pool-", 1)
        .daemon(false)
        .factory();

try (ExecutorService executor = Executors.newFixedThreadPool(4, factory)) {
    executor.submit(() -> generateReport("daily"));
    executor.submit(() -> generateReport("monthly"));
}
```

Executor quản lý việc tái sử dụng worker, hàng đợi và vòng đời thực thi; `ThreadFactory` chỉ quyết định cách tạo thread. `newFixedThreadPool` giới hạn số worker platform thread ở mức đã cấu hình. Nếu cần giới hạn cả số task đang chờ, phải chọn executor hoặc cơ chế backpressure phù hợp; kích thước pool cố định không tự giới hạn kích thước hàng đợi mặc định.

`ExecutorService` trong Java 21 hỗ trợ `AutoCloseable`, vì vậy có thể dùng try-with-resources để đóng executor và chờ các task đã được submit hoàn tất theo hợp đồng `close()`.

## 6. Chọn platform thread hay virtual thread

Java 21 cung cấp cả `Thread.ofPlatform()` và `Thread.ofVirtual()`. Hai builder có một số cấu hình chung như tên, `ThreadFactory`, uncaught exception handler và kế thừa `InheritableThreadLocal`, nhưng cấu hình riêng của platform thread không áp dụng cho virtual thread.

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Cần thread gắn với OS thread hoặc tương tác native | Platform thread |
| Cần đặt daemon, priority, thread group hoặc stack size | Platform thread |
| Cần số worker hữu hạn cho CPU-bound workload | Platform thread kết hợp executor có giới hạn |
| Cần rất nhiều task đồng thời, chủ yếu chờ I/O | Virtual thread |
| Cần tích hợp API nhận `ThreadFactory` nhưng muốn tạo platform worker | `Thread.ofPlatform().factory()` |

Không nên tạo một platform thread mới cho mọi request nếu lượng request có thể tăng không giới hạn. Khi cần concurrency cao cho tác vụ blocking, virtual thread thường giảm chi phí quản lý thread; khi cần giới hạn tài nguyên hoặc chạy tác vụ CPU-bound, executor có số worker hữu hạn giúp kiểm soát tải.

## 7. Vòng đời, interrupt và phối hợp kết thúc

Platform thread được khởi chạy bằng `start()` và kết thúc khi task hoàn tất hoặc thread thoát khỏi `run()`. Để đợi thread hoàn tất, dùng `join()`:

```java
Thread worker = Thread.ofPlatform()
        .name("file-writer")
        .start(() -> writeFile());

try {
    worker.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Chuyển yêu cầu hủy hoặc kết thúc lên tầng gọi.
}
```

Nếu cần yêu cầu task dừng, dùng `interrupt()` và thiết kế task kiểm tra/truyền tiếp trạng thái interrupt tại các điểm phù hợp. Interrupt là tín hiệu hợp tác, không phải lệnh buộc thread dừng ngay. Các thao tác như `Thread.stop`, `suspend` và `resume` không phải cách quản lý vòng đời thread hiện đại và không nên dùng.

Với tác vụ được quản lý bởi executor, ưu tiên dùng `Future`, `ExecutorService.shutdown()`/`shutdownNow()` và quy trình đóng executor phù hợp thay vì tự điều khiển từng worker thread.

## 8. Lỗi cấu hình thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| JVM thoát trước khi task nền hoàn tất | Thread được đặt daemon trong khi công việc cần hoàn thành | Dùng non-daemon thread và đóng/join có kiểm soát |
| Log khó xác định worker nào gây lỗi | Không đặt tên hoặc nhiều thread có tên khó phân biệt | Dùng `name(prefix, start)` |
| Kỳ vọng priority quyết định thứ tự | Priority phụ thuộc scheduler và nền tảng | Dùng queue, lock, semaphore hoặc executor để biểu diễn thứ tự/đồng bộ |
| Stack overflow vẫn xảy ra dù đã đặt stack size | JVM/OS có thể bỏ qua hoặc điều chỉnh gợi ý stack | Đo đạc và kiểm thử trên JVM/OS triển khai; giảm đệ quy khi có thể |
| Context không xuất hiện trong thread mới | Đã tắt kế thừa `InheritableThreadLocal` hoặc context dùng cơ chế khác | Xác định loại context và truyền tường minh khi cần |
| Exception task không được log như mong đợi | Exception đã bị bắt trong task hoặc handler chưa được gắn cho thread | Xử lý lỗi trong task hoặc cấu hình uncaught handler đúng nơi |
| Tạo quá nhiều native thread | Tạo platform thread không giới hạn cho workload có concurrency cao | Dùng pool có giới hạn hoặc đánh giá virtual thread |

## 9. Checklist cấu hình platform thread

- [ ] Đã xác định yêu cầu thực sự cần platform thread thay vì virtual thread.
- [ ] Đã dùng `Thread.ofPlatform()` để tạo builder.
- [ ] Đặt tên thread rõ ràng, đặc biệt với nhiều worker cùng vai trò.
- [ ] Đã chọn daemon/non-daemon theo yêu cầu vòng đời task.
- [ ] Không dựa vào priority để bảo đảm thứ tự hoặc đồng bộ.
- [ ] Chỉ điều chỉnh stack size khi đã đo đạc và kiểm thử trên nền tảng đích.
- [ ] Đã hiểu tác động của việc kế thừa `InheritableThreadLocal`.
- [ ] Đã cấu hình uncaught exception handler nếu cần giám sát lỗi thoát khỏi task.
- [ ] Dùng `ThreadFactory` và executor khi cần tái sử dụng cấu hình hoặc quản lý nhiều worker.
- [ ] Có quy trình interrupt, join hoặc shutdown để kết thúc task có trật tự.

## Tài liệu tham khảo

- [Thread — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `Thread.ofPlatform()`, vòng đời thread, platform thread và virtual thread.
- [Thread.Builder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): cấu hình tên, kế thừa `InheritableThreadLocal`, uncaught exception handler, `start`, `unstarted` và `factory`.
- [Thread.Builder.OfPlatform — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfPlatform.html): cấu hình daemon, priority, group và stack size.
- [ThreadFactory — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html): hợp đồng tạo thread cho executor và các API concurrency.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý vòng đời executor, submit task và đóng executor.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): bối cảnh lựa chọn virtual thread và mối quan hệ với platform thread trong Java 21.
