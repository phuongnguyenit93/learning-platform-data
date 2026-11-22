# Tạo và khởi chạy bằng Thread.startVirtualThread

Java 21 cung cấp phương thức tĩnh `Thread.startVirtualThread(Runnable task)` để tạo một virtual thread và bắt đầu chạy tác vụ ngay. Phương thức trả về đối tượng `Thread` đại diện cho virtual thread đã được khởi chạy, nhờ đó mã gọi có thể chờ hoàn tất bằng `join()`, kiểm tra trạng thái hoặc gửi yêu cầu ngắt bằng `interrupt()`.

Đây là cách ngắn gọn để chạy một tác vụ độc lập bằng virtual thread. API đã hoàn thiện trong Java 21 qua JEP 444 và không cần bật Preview.

## 1. Cú pháp và hành vi của startVirtualThread

Cú pháp:

```java
public static Thread startVirtualThread(Runnable task)
```

Phương thức nhận một `Runnable`, tạo virtual thread mới, lập lịch để chạy tác vụ rồi trả về đối tượng `Thread`. Khi phương thức trả về, thread đã được start; mã gọi không cần và không được gọi `start()` lần nữa trên đối tượng đó.

Ví dụ tối thiểu:

```java
public class StartVirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.startVirtualThread(() -> {
            System.out.println("Running in virtual thread: "
                    + Thread.currentThread().isVirtual());
            loadData();
        });

        worker.join();
        System.out.println("Worker finished");
    }

    private static void loadData() {
        System.out.println("Loading data...");
    }
}
```

`Thread.currentThread().isVirtual()` trả về `true` bên trong tác vụ. `join()` làm luồng gọi chờ cho đến khi virtual thread kết thúc. Nếu bỏ `join()` và luồng `main` kết thúc, JVM có thể thoát trong khi virtual thread vẫn đang chạy vì virtual thread là daemon thread.

## 2. startVirtualThread khác với gọi run()

`Thread.startVirtualThread(task)` tạo một thread riêng và khởi chạy tác vụ trên virtual thread đó. Gọi trực tiếp `task.run()` chỉ thực thi thân tác vụ trên thread hiện tại; nó không tạo thread mới.

```java
Runnable task = () -> {
    System.out.println(Thread.currentThread().isVirtual());
};

// Chạy task trên virtual thread mới.
Thread worker = Thread.startVirtualThread(task);

// Chờ thread đã được khởi chạy.
worker.join();
```

Không gọi `worker.start()` sau `startVirtualThread()`: thread đã được khởi chạy rồi, gọi `start()` lần nữa sẽ ném `IllegalThreadStateException`. Cũng không cần gọi `run()` trên đối tượng trả về để bắt đầu tác vụ.

## 3. Lưu Thread để quản lý vòng đời

Giá trị trả về là một `Thread` thông thường trong API Java. Ứng dụng có thể dùng nó để:

- `join()` chờ tác vụ hoàn tất.
- `isAlive()` kiểm tra thread còn đang chạy hay không.
- `interrupt()` yêu cầu thread dừng hoặc hủy thao tác có thể bị interrupt.
- `getName()` lấy tên thread để hỗ trợ log và chẩn đoán.
- `isVirtual()` xác nhận thread đó là virtual thread.

Ví dụ khởi chạy nhiều tác vụ và chờ tất cả hoàn tất:

```java
static void runTasks() throws InterruptedException {
    Thread first = Thread.startVirtualThread(() -> process("first"));
    Thread second = Thread.startVirtualThread(() -> process("second"));
    Thread third = Thread.startVirtualThread(() -> process("third"));

    first.join();
    second.join();
    third.join();
}

static void process(String taskName) {
    System.out.println("Processing " + taskName);
}
```

Các virtual thread có thể chạy đồng thời; không dựa vào thứ tự log để kết luận thứ tự hoàn tất. `join()` trên từng thread chỉ bảo đảm thread tương ứng đã kết thúc khi lời gọi trả về.

Theo Java Memory Model, mọi hành động trước khi gọi `startVirtualThread` xảy ra-before các hành động trong virtual thread mới. Tương tự, các hành động trong thread xảy ra-before một thread khác phát hiện thread đó đã kết thúc, chẳng hạn khi `join()` trả về bình thường. Vì vậy, `join()` cũng là điểm đồng bộ để luồng gọi quan sát kết quả mà tác vụ đã ghi trước khi kết thúc.

## 4. Đặt tên virtual thread khi cần

`Thread.startVirtualThread(Runnable)` là phương thức tiện ích ngắn gọn và không nhận tham số đặt tên. Nếu cần đặt tên để theo dõi log hoặc thread dump, dùng virtual thread builder:

```java
Thread worker = Thread.ofVirtual()
        .name("order-loader")
        .start(() -> loadOrder(42));

worker.join();
```

`Thread.ofVirtual()` trả về builder cho virtual thread. Gọi `name(...)` cấu hình tên trước khi `start(...)` tạo và khởi chạy thread. Dùng builder khi cần cấu hình thêm; dùng `Thread.startVirtualThread(...)` khi chỉ cần tạo và chạy nhanh một `Runnable`.

## 5. Xử lý interruption

`interrupt()` gửi yêu cầu ngắt đến thread. Đây là tín hiệu hợp tác: tác vụ cần kiểm tra trạng thái interrupt hoặc xử lý `InterruptedException` từ các thao tác blocking có hỗ trợ interruption.

```java
static void runInterruptibleTask() throws InterruptedException {
    java.util.concurrent.CountDownLatch ready =
            new java.util.concurrent.CountDownLatch(1);
    Thread worker = Thread.startVirtualThread(() -> {
        try {
            ready.countDown();
            Thread.sleep(10_000);
            doSmallUnitOfWork();
        } catch (InterruptedException e) {
            // Sleep đã nhận yêu cầu interrupt và xóa interrupt status.
            releaseResources();
            Thread.currentThread().interrupt();
        }
    });

    // Ví dụ minh họa: yêu cầu dừng tác vụ.
    ready.await();
    worker.interrupt();
    worker.join();
}
```

Khi một phương thức ném `InterruptedException`, interrupt status thường đã được xóa. Nếu không thể truyền exception lên caller, mã xử lý thường khôi phục trạng thái bằng `Thread.currentThread().interrupt()` sau khi dọn dẹp. Không dùng interrupt như một cách buộc JVM dừng ngay lập tức một tác vụ không hợp tác.

## 6. Virtual thread là daemon thread

Virtual thread luôn là daemon thread. JVM không giữ tiến trình sống chỉ để chờ các daemon thread hoàn tất. Vì vậy, nếu `main` kết thúc và không còn platform thread không phải daemon nào đang chạy, JVM có thể bắt đầu shutdown dù virtual thread chưa hoàn thành.

```java
public static void main(String[] args) throws InterruptedException {
    Thread worker = Thread.startVirtualThread(() -> {
        performImportantWork();
    });

    worker.join(); // Chờ công việc quan trọng hoàn tất.
}
```

Giữ lại `Thread` và chờ bằng `join()` khi luồng gọi phải bảo đảm tác vụ hoàn tất. Trong ứng dụng server, vòng đời của platform thread phục vụ request thường đã được runtime quản lý; vẫn cần xác định rõ ai chịu trách nhiệm chờ, hủy và xử lý lỗi của tác vụ.

## 7. startVirtualThread chỉ nhận Runnable

`Runnable` không trả về giá trị. `startVirtualThread` trả về `Thread`, không phải `Future<T>`, nên không có phương thức `get()` để lấy kết quả tác vụ.

Nếu cần kết quả hoặc cần chuyển exception về luồng gọi, có thể dùng `CompletableFuture` cùng với `startVirtualThread`, hoặc dùng `ExecutorService` với `submit(Callable<T>)`.

Ví dụ với `CompletableFuture`: 

```java
import java.util.concurrent.CompletableFuture;

static CompletableFuture<String> loadAsync() {
    CompletableFuture<String> result = new CompletableFuture<>();

    Thread.startVirtualThread(() -> {
        try {
            result.complete(loadFromService());
        } catch (Exception e) {
            result.completeExceptionally(e);
        }
    });

    return result;
}
```

Phương thức trả về `CompletableFuture` ngay sau khi khởi chạy virtual thread; caller có thể đăng ký continuation hoặc gọi `join()` tại nơi thực sự cần kết quả. `join()` của `CompletableFuture` chờ kết quả và truyền lỗi hoàn tất dưới dạng `CompletionException`. Với nhiều tác vụ cần quản lý cùng nhau, `Executors.newVirtualThreadPerTaskExecutor()` thường cung cấp cấu trúc vòng đời rõ ràng hơn.

## 8. Xử lý lỗi trong tác vụ

Exception không được bắt bên trong tác vụ sẽ làm virtual thread kết thúc bất thường và được chuyển đến uncaught exception handler của thread. `Thread.join()` chỉ chờ thread kết thúc; nó không ném lại exception đã xảy ra trong thread đó.

```java
Thread worker = Thread.startVirtualThread(() -> {
    throw new IllegalStateException("Cannot process request");
});

worker.join();
// join() hoàn tất khi worker kết thúc; exception của worker
// được xử lý bởi uncaught exception handler.
```

Với tác vụ nghiệp vụ, nên chủ động bắt và chuyển lỗi qua cơ chế kết quả phù hợp, ghi log theo ngữ cảnh hoặc hoàn tất một `CompletableFuture` exceptionally. Đừng cho rằng việc `join()` thành công có nghĩa thân tác vụ đã chạy thành công.

## 9. Những giới hạn và nguyên tắc sử dụng

- Tạo một virtual thread cho mỗi tác vụ độc lập; không tạo pool để tái sử dụng virtual thread.
- Dùng virtual thread chủ yếu cho workload có nhiều thời gian chờ I/O hoặc blocking operation tương thích.
- Virtual thread không làm phép tính CPU-bound chạy nhanh hơn và không tăng số lõi CPU.
- Giới hạn tài nguyên hữu hạn như database connection, API quota hoặc số request đồng thời bằng semaphore, connection pool hoặc backpressure; không dùng số lượng virtual thread làm giới hạn tài nguyên.
- Virtual thread luôn là daemon và có priority `NORM_PRIORITY`; không dùng priority để lập lịch hoặc điều khiển thứ tự tác vụ.
- Nếu cần cấu hình tên hoặc các thuộc tính builder trước khi start, dùng `Thread.ofVirtual()` thay cho phương thức tiện ích.

## 10. startVirtualThread và các API liên quan

| API | Mục đích |
|---|---|
| `Thread.startVirtualThread(Runnable)` | Tạo và khởi chạy ngay một virtual thread |
| `Thread.ofVirtual()` | Lấy builder để cấu hình virtual thread trước khi start |
| `Thread.isVirtual()` | Kiểm tra thread hiện tại hoặc một thread có phải virtual thread |
| `Thread.join()` | Chờ thread kết thúc |
| `Thread.interrupt()` | Gửi yêu cầu interrupt đến thread |
| `Executors.newVirtualThreadPerTaskExecutor()` | Tạo executor chạy mỗi task trên một virtual thread; phù hợp khi cần quản lý nhóm task |

## 11. Biên dịch với Java 21

`Thread.startVirtualThread(Runnable)` được cung cấp trong Java 21 và không phải API Preview. Biên dịch ví dụ với release 21:

```bash
javac --release 21 -d out src/StartVirtualThreadDemo.java
java -cp out StartVirtualThreadDemo
```

Đặt compiler release hoặc toolchain về Java 21 để bảo đảm API được kiểm tra theo đúng phiên bản mục tiêu. Không thêm `--enable-preview` cho virtual threads.

## 12. Tài liệu tham khảo

- [Java SE 21 API — Thread.startVirtualThread(Runnable)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#startVirtualThread(java.lang.Runnable))
- [Java SE 21 API — Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
