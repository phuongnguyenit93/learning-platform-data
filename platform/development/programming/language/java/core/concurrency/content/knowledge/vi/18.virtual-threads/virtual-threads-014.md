# Thread.ofVirtual().unstarted(), ThreadFactory và vòng đời khởi chạy

## 1. Mục tiêu và bối cảnh

Virtual thread là `java.lang.Thread` do JVM quản lý lịch chạy, phù hợp với khối lượng công việc có nhiều tác vụ chờ I/O. Virtual thread được đưa vào Java như tính năng chính thức từ **Java 21** (JEP 444). Vì thế ví dụ chạy độc lập trong bài dùng **JDK 21 trở lên**, không yêu cầu `--enable-preview`. Đây là kiến thức concurrency thuần Java; tất cả thao tác đều dùng JDK, không phụ thuộc Spring hay cơ chế async của framework.

Câu hỏi trung tâm: **khi nào một virtual thread mới chỉ được tạo, khi nào nó thật sự được khởi chạy, và `ThreadFactory` đóng vai trò gì?**

Sau bài học, bạn có thể:

- Dùng `Thread.ofVirtual().unstarted(task)` để tạo một đối tượng `Thread` ở trạng thái `NEW`, rồi chủ động gọi `start()`.
- Phân biệt `unstarted(task)`, `start(task)`, `Thread.startVirtualThread(task)` và `ThreadFactory.newThread(task)`.
- Tạo `ThreadFactory` tái sử dụng từ `Thread.ofVirtual().factory()`, tùy chỉnh tên để quan sát được từng tác vụ.
- Theo dõi `NEW`, `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED` và `TERMINATED` mà không nhầm trạng thái Java với trạng thái chạy trên CPU.
- Quản lý vòng đời bằng `join()`, `interrupt()`, `Future` và executor; tránh quên `start()`, gọi `run()` trực tiếp hoặc để ứng dụng thoát trước khi tác vụ hoàn thành.

## 2. Virtual thread có gì khác platform thread?

`Thread.ofPlatform()` tạo builder cho **platform thread** thường gắn với luồng hệ điều hành. `Thread.ofVirtual()` tạo builder cho **virtual thread**: Java runtime có thể ghép nhiều virtual thread lên số lượng nhỏ hơn các platform thread dùng làm *carrier*. Khi virtual thread chờ tại những thao tác blocking hỗ trợ cơ chế này, JVM thường có thể tháo nó khỏi carrier để carrier phục vụ tác vụ khác.

Điểm cốt lõi: virtual thread vẫn là một `Thread` với `Runnable`, `start()`, `join()`, `interrupt()`, `getState()`, `isAlive()`, `ThreadLocal` và stack trace. Nó giúp lập trình theo kiểu tuần tự dễ đọc trong tác vụ chờ I/O, nhưng **không làm CPU-bound code chạy nhanh hơn một cách tự động**, không khiến lệnh blocking biến mất, và không bảo đảm thứ tự thực thi.

```java
Runnable task = () ->
        System.out.println(Thread.currentThread().isVirtual());

Thread virtual = Thread.ofVirtual().unstarted(task);
Thread platform = Thread.ofPlatform().unstarted(task);
```

Đoạn trên chỉ minh họa API, chưa khởi chạy hai thread. Cả hai đều chưa thực hiện `task`. `Thread.currentThread().isVirtual()` phải được kiểm tra **bên trong task đang chạy** nếu muốn quan sát loại thread thực thi, vì thread tạo task và thread chạy task có thể khác nhau.

Một virtual thread trên JDK 21 là **daemon thread**; không thể chuyển thành non-daemon để giữ JVM sống. Vì vậy một chương trình console cần `join()` hoặc cơ chế chờ hoàn tất có chủ đích. Đừng dựa vào việc JVM sẽ tự chờ những virtual thread chưa hoàn thành.

## 3. `Thread.ofVirtual().unstarted(task)`: tạo trước, chạy sau

```java
Runnable task = () -> System.out.println("work");
Thread worker = Thread.ofVirtual()
        .name("read-catalog")
        .unstarted(task);               // tạo Thread, chưa chạy Runnable
```

Ngay sau `unstarted`:

- `worker.isVirtual()` là `true`.
- `worker.getState()` là `Thread.State.NEW`.
- `worker.isAlive()` là `false`.
- Chưa có lời gọi `task.run()` từ thread này, và chưa có tác vụ nào được lịch chạy chỉ vì đối tượng `Thread` đã tồn tại.
- `worker.getName()` là `read-catalog`, tên được đặt để quan sát hoặc chẩn đoán.

Để đưa tác vụ vào lịch chạy:

```java
worker.start(); // chỉ được gọi một lần
worker.join();  // thread hiện tại đợi worker kết thúc
```

`start()` yêu cầu JVM bắt đầu thực thi `Runnable` trên **một thread riêng**; phương thức `start()` không có nghĩa phải chờ task kết thúc mới trả về. `join()` đợi cho thread kết thúc (hoặc bị ngắt khi thread đang đợi, tùy overload), nên phù hợp ở ranh giới cần kết quả.

**Không dùng `worker.run()` thay `worker.start()`.** Đối với virtual thread, gọi trực tiếp phương thức `Thread.run()` từ thread khác **không khởi chạy virtual thread**, và implementation mặc định của `Thread.run()` trên virtual thread không chạy task theo cách bạn mong đợi. Với platform thread, gọi trực tiếp `run()` cũng không tạo luồng độc lập, vì vậy nguyên tắc chung vẫn là gọi `start()` để tạo concurrency.

Một `Thread` chỉ được `start()` **tối đa một lần**. Gọi lần hai, kể cả sau `TERMINATED`, dẫn tới `IllegalThreadStateException`. Muốn chạy lại cùng logic, hãy tạo **một `Thread` mới** dùng cùng `Runnable` hoặc một task mới. Không thể tái sử dụng instance `Thread` đã kết thúc.

## 4. API nhanh để so sánh

| API | Kết quả tạo ra | Đã khởi chạy khi API trả về? | Khi nào dùng |
| --- | --- | --- | --- |
| `Thread.ofVirtual().unstarted(task)` | Một `Thread` virtual | **Chưa**; trạng thái `NEW` | Cần đặt tên/cấu hình và giữ quyền chủ động gọi `start()` |
| `Thread.ofVirtual().start(task)` | Một `Thread` virtual | **Đã yêu cầu khởi chạy** | Muốn tạo và start ngay |
| `Thread.startVirtualThread(task)` | Một `Thread` virtual | **Đã yêu cầu khởi chạy** | Viết ngắn, không cần tùy chỉnh builder |
| `Thread.ofVirtual().factory()` | Một `ThreadFactory` | Chưa có thread công việc | Muốn tạo nhiều thread theo cùng cấu hình |
| `factory.newThread(task)` với factory trên | Một `Thread` virtual | **Chưa**; cần gọi `start()` | Tạo từng thread thủ công hoặc giao cho executor |
| `Executors.newVirtualThreadPerTaskExecutor()` | `ExecutorService` | Task do executor nhận sẽ được executor khởi chạy | Tổ chức nhiều tác vụ, quản lý kết quả/hủy/đóng executor |

`Thread.ofVirtual().start(task)` về ý nghĩa tạo và khởi chạy tương đương việc tạo bằng `unstarted(task)` rồi gọi `start()`, nhưng bạn không có khoảng trống để quan sát/thiết lập một object chưa chạy. Cả hai cách đều không bảo đảm task đã **hoàn tất** khi lời gọi trả về.

`Thread.startVirtualThread(task)` là tiện ích tĩnh Java 21, tương đương `Thread.ofVirtual().start(task)`. Nó **không** trả về `Future`; để chờ task kết thúc, bạn có thể giữ `Thread` được trả về và `join()`.

## 5. `ThreadFactory`: chính sách tạo thread có thể tái sử dụng

`java.util.concurrent.ThreadFactory` là functional interface với phương thức `Thread newThread(Runnable runnable)`. Theo contract, factory tạo ra một **thread chưa start**, cho phép người gọi hoặc executor quyết định thời điểm chạy.

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("io-vt-", 0)
        .factory();

Thread t0 = factory.newThread(() -> downloadChunk());
Thread t1 = factory.newThread(() -> downloadChunk());

// Đến đây cả hai còn NEW; downloadChunk() là hàm minh họa.
t0.start();
t1.start();
```

Đây là **mảnh mã minh họa** vì `downloadChunk()` chưa được định nghĩa. Prefix cùng chỉ số bắt đầu `0` tạo tên `io-vt-0`, `io-vt-1`, ... cho những thread được factory cấp phát. `factory()` chụp cấu hình hiện tại của builder để tạo thread nhất quán. Factory trả về được thiết kế **thread-safe**, phù hợp cho nhiều caller; ngược lại, bản thân `Thread.Builder` không phải một đối tượng để nhiều thread cùng chỉnh cấu hình một cách tự do.

Factory do `Thread.ofVirtual().factory()` tạo sẽ trả virtual thread; `Executors.defaultThreadFactory()` là factory platform thread, vì vậy không được dùng thay nếu mục tiêu rõ ràng là virtual thread.

`ThreadFactory.newThread()` theo interface nói chung **có thể trả `null`** khi factory từ chối tạo thread; đây là khả năng của contract đối với factory tùy biến, không phải hành vi thông thường của factory JDK thu được từ `Thread.ofVirtual()`. Hãy xử lý phù hợp nếu nhận một factory do thư viện khác cung cấp.

### Cấu hình trên builder

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("request-", 100)
        .inheritInheritableThreadLocals(false)
        .uncaughtExceptionHandler((thread, failure) ->
                System.err.println(thread.getName() + ": "
                        + failure.getClass().getSimpleName()))
        .factory();
```

Các thiết lập có mục đích riêng:

- `name(prefix, start)` tạo tên theo bộ đếm. `name("fixed")` dùng một tên cố định cho các thread tạo ra từ cấu hình đó; nếu cần phân biệt hàng loạt thread, nên dùng tiền tố và chỉ số.
- `inheritInheritableThreadLocals(false)` ngăn kế thừa giá trị ban đầu của `InheritableThreadLocal` từ thread tạo; cân nhắc khi tránh rò rỉ context giữa tác vụ. `ThreadLocal` vẫn được virtual thread hỗ trợ, nhưng mỗi task không nên dựa vào giả định tất cả thread có cùng context.
- `uncaughtExceptionHandler(...)` dùng để quan sát exception không được xử lý trong task chạy trực tiếp trên thread. Cơ chế `Future`/executor có thể thu exception theo contract của nó, vì vậy không dựa duy nhất vào handler để thu kết quả.
- Virtual thread vốn là daemon và có các hạn chế riêng về priority; `Thread.Builder.OfVirtual` không có chuỗi tùy chỉnh daemon như `Thread.Builder.OfPlatform`.

Đừng tạo ra một factory mới trong mỗi vòng lặp chỉ để đánh số tên: cấu hình một lần rồi dùng lại giúp chính sách đặt tên và loại thread nhất quán.

## 6. Vòng đời: `NEW` → lịch chạy → `TERMINATED`

```text
ofVirtual().unstarted(task) hoặc factory.newThread(task)
                         |
                         v
                     NEW
                         |
                      start()
                         v
           RUNNABLE <----------+
               |               |
    đang chạy hoặc sẵn sàng    |
               |               |
               +--> WAITING ---+
               |      (join/park...)
               +--> TIMED_WAITING -+
               |      (sleep/đợi có hạn)
               +--> BLOCKED --------+
                      (chờ monitor)
               |
        Runnable kết thúc
        (bình thường hoặc ném lỗi)
               |
               v
           TERMINATED
```

Các trạng thái `Thread.State` là **ảnh chụp thời điểm**, không phải một luồng chuyển trạng thái bắt buộc đi qua mọi nút. Một virtual thread vừa được `start()` có thể vẫn được quan sát ở `RUNNABLE`, hoặc đã chạy xong rất nhanh và trở thành `TERMINATED`. `RUNNABLE` **không đồng nghĩa** chắc chắn đang chiếm CPU; đó là trạng thái Java bao gồm sẵn sàng chạy và đang chạy.

- `NEW`: đã tạo instance nhưng chưa `start()`.
- `RUNNABLE`: đủ điều kiện thực thi hoặc đang được thực thi, kể cả khi đang chờ được lịch trên carrier.
- `WAITING`: đợi vô thời hạn một sự kiện, chẳng hạn lời gọi chờ thích hợp.
- `TIMED_WAITING`: đợi có hạn thời gian, ví dụ `Thread.sleep(...)`.
- `BLOCKED`: đợi giành Java monitor khi vào vùng `synchronized` do thread khác nắm giữ.
- `TERMINATED`: `Runnable.run()` đã trả về hoặc thoát vì uncaught exception. Trạng thái này là cuối cùng đối với một instance thread.

Không dùng `getState()` để phối hợp chính xác giữa các thread: ngay sau khi đọc state, thread có thể chuyển trạng thái. Muốn xác nhận hoàn tất, dùng `join()`, `Future.get()`, `CountDownLatch` hay cơ chế đồng bộ phù hợp.

`isAlive()` trả `false` trước khi `start()` và sau khi hoàn tất, `true` trong quãng đời đã start nhưng chưa kết thúc. Do đó **chỉ `isAlive() == false` không đủ để kết luận task đã chạy xong**: nó cũng đúng đối với thread chưa từng start.

### Các mốc xảy ra trước về mặt bộ nhớ (happens-before)

Theo Java Memory Model:

- Các hành động trong thread tạo trước lời gọi `worker.start()` *happen-before* các hành động của thread mới sau khi được start.
- Mọi hành động của thread đã kết thúc *happen-before* một thread khác hoàn tất việc `join()` tương ứng thành công.

Nhờ vậy, `join()` vừa chờ kết thúc, vừa giúp thread gọi nhìn thấy những ghi nhớ hợp lệ của task trước khi kết thúc. Tuy nhiên, **không dùng kết luận này để bỏ qua đồng bộ** nếu nhiều thread đang ghi/đọc cùng trạng thái *trong lúc chúng còn chạy*. Khi có cập nhật song song, vẫn dùng `volatile`, atomic, lock hoặc cấu trúc dữ liệu thread-safe tùy trường hợp.

## 7. Ví dụ 1: tự khởi chạy và quan sát trạng thái, factory tạo tên

Chương trình chạy độc lập dưới đây cho thấy cả `unstarted()` và `ThreadFactory.newThread()` đều tạo thread ở trạng thái `NEW`. Nó cố ý `join()` trước khi in bước kế tiếp để output xác định được. Lưu thành tệp `VirtualThreadLifecycleDemo.java`:

```java
import java.util.concurrent.ThreadFactory;

public class VirtualThreadLifecycleDemo {
    private static final Runnable TASK = () -> {
        Thread current = Thread.currentThread();
        System.out.println("run=" + current.getName()
                + ", virtual=" + current.isVirtual());
    };

    public static void main(String[] args) throws InterruptedException {
        Thread manual = Thread.ofVirtual()
                .name("manual-vt")
                .unstarted(TASK);
        System.out.println("manual-before=" + manual.getState());
        System.out.println("manual-alive=" + manual.isAlive());
        manual.start();
        manual.join();
        System.out.println("manual-after=" + manual.getState());

        ThreadFactory factory = Thread.ofVirtual()
                .name("factory-vt-", 1)
                .factory();
        Thread first = factory.newThread(TASK);
        Thread second = factory.newThread(TASK);
        System.out.println("factory-before=" + first.getState()
                + "," + second.getState());
        first.start();
        first.join();
        second.start();
        second.join();
        System.out.println("factory-after=" + first.getState()
                + "," + second.getState());
    }
}
```

Biên dịch và chạy với JDK 21+:

```bash
javac VirtualThreadLifecycleDemo.java
java VirtualThreadLifecycleDemo
```

Kết quả:

```text
manual-before=NEW
manual-alive=false
run=manual-vt, virtual=true
manual-after=TERMINATED
factory-before=NEW,NEW
run=factory-vt-1, virtual=true
run=factory-vt-2, virtual=true
factory-after=TERMINATED,TERMINATED
```

Tại sao kết quả xác định?

1. `manual` mới được `unstarted()` nên ở `NEW` và `isAlive()` là `false`.
2. `manual.start()` kích hoạt task; `manual.join()` đợi task in dòng `run=...` trước khi main đọc `TERMINATED`.
3. `factory.newThread(TASK)` hai lần cấp hai thread chưa chạy, với tên theo bộ đếm bắt đầu từ `1`.
4. `first.start(); first.join(); second.start(); second.join();` làm hai dòng in của task có thứ tự rõ ràng. Nếu thay bằng `first.start(); second.start(); first.join(); second.join();`, **thứ tự hai dòng in không được bảo đảm** dù hai task đều chạy đúng.
5. Không có yêu cầu `--enable-preview` vì Virtual Threads đã chuẩn hóa từ Java 21.

## 8. Ví dụ 2: cấp `ThreadFactory` cho executor

Khi có nhiều task cùng loại, thường nên giao vòng đời thread cho `ExecutorService`. Executor gọi `ThreadFactory.newThread(task)` rồi **tự `start()`** thread vừa tạo: client không được start thủ công những thread do executor quản lý.

Lưu vào `VirtualThreadExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;

public class VirtualThreadExecutorDemo {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("task-", 0)
                .factory();
        try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
            Future<String> a = executor.submit(() -> Thread.currentThread().getName());
            Future<String> b = executor.submit(() -> Thread.currentThread().getName());
            System.out.println(a.get());
            System.out.println(b.get());
        }
    }
}
```

Chạy:

```bash
javac VirtualThreadExecutorDemo.java
java VirtualThreadExecutorDemo
```

Kết quả:

```text
task-0
task-1
```

Mỗi `submit()` tạo một task và executor dùng factory để tạo một virtual thread mới. Tên được gán khi tạo thread; hai task có thể chạy/hoàn tất theo thứ tự bất kỳ, nhưng thứ tự **in** trong ví dụ xác định vì main gọi `a.get()` rồi `b.get()`. `Future.get()` trả kết quả hoặc báo `ExecutionException` cho lỗi task, có thể ném `InterruptedException` nếu thread chờ bị ngắt.

Khối `try-with-resources` gọi `ExecutorService.close()` khi thoát; ở Java 21, thao tác đóng này chờ các task đã nộp hoàn tất theo contract. Nếu không cần đặt tên riêng, dùng tiện ích:

```java
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    // executor.submit(task) ...
}
```

Đây là **mảnh mã minh họa**: biến `task` và logic thu kết quả cần được định nghĩa theo bài toán. Cách này hợp với mô hình *một virtual thread cho mỗi task*; nó không tạo pool cố định gồm vài virtual thread để dùng lại. Nếu workload có hàng chục nghìn request I/O, vẫn phải giới hạn tài nguyên phía sau như kết nối cơ sở dữ liệu, số request đồng thời và quota API.

### Khi nào quản lý trực tiếp `Thread`, khi nào dùng executor?

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Một tác vụ đơn giản, muốn thấy chính xác `NEW` rồi `start()` | `Thread.ofVirtual().unstarted()` | Chủ động vòng đời và quan sát trạng thái |
| Một tác vụ chạy ngay, không cần kiểm soát lúc start | `Thread.ofVirtual().start()` | Ngắn gọn |
| Nhiều thread cùng cấu hình/tên | `ThreadFactory` | Tập trung cấu hình, caller quyết định khởi chạy |
| Nhiều task trả giá trị hoặc cần hủy/thu lỗi | `ExecutorService` với factory hoặc virtual-thread-per-task | Tích hợp `Future`, shutdown và quản lý task |
| Công việc chủ yếu CPU-bound | Thiết kế giới hạn song song theo CPU và tài nguyên | Virtual thread không tự tăng khả năng CPU |

## 9. `join()`, interrupt, timeout và lỗi trong task

### `join()` chờ hoàn tất nhưng không trả exception của task

`Thread.join()` đợi thread kết thúc; nó **không ném lại** exception do `Runnable` ở thread con ném. Nếu cần nhận dữ liệu/lỗi làm kết quả của một phép tính, hãy dùng `Callable` và `Future`, hoặc truyền kết quả qua kênh thread-safe. Với thread chạy trực tiếp, `UncaughtExceptionHandler` giúp ghi nhận lỗi không bắt được.

Nếu chính thread đang chờ `join()` bị interrupt, `join()` ném `InterruptedException`. Một mẫu phù hợp khi phương thức không thể ném tiếp là:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát hoặc chuyển điều khiển để caller quyết định.
}
```

Đây là mảnh mã trong ngữ cảnh có biến `worker`, không phải chương trình độc lập. Khôi phục cờ interrupt ngăn việc “nuốt” tín hiệu hủy. Không tiếp tục mặc định coi worker đã hoàn thành nếu `join()` bị ngắt trước khi nó kết thúc.

### `interrupt()` là yêu cầu hợp tác

```java
Thread worker = Thread.ofVirtual().start(() -> {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
});
worker.interrupt();
```

Mảnh mã trên yêu cầu thread ngủ nhận interrupt và thoát; `interrupt()` không ép task dừng ở mọi tình huống. Một vòng lặp tính toán không kiểm tra cờ interrupt hoặc tín hiệu dừng riêng có thể tiếp tục chạy. Khi dùng executor, `Future.cancel(true)` cố gắng gửi interrupt cho task đang chạy, nhưng không bảo đảm task sẽ dừng ngay.

`join(Duration)` chỉ có ở các bản Java mới hơn; để bảo đảm ví dụ tương thích Java 21, dùng `join(long millis)` hoặc `join(long millis, int nanos)` khi cần chờ có hạn. Sau lời gọi `join(timeout)`, phải đọc `isAlive()` nếu muốn biết task đã kết thúc hay chỉ hết thời gian chờ.

### Task lỗi: trạng thái thread vẫn kết thúc

Nếu `Runnable` ném exception không được xử lý, thread chuyển thành `TERMINATED`; exception được chuyển tới uncaught-exception handler phù hợp. `Thread.join()` vẫn chỉ là chờ, không đồng nghĩa kết quả thành công. Muốn bảo đảm caller có thông tin lỗi, ưu tiên `Future.get()` đối với task trong executor, hoặc thiết kế một kênh nhận lỗi rõ ràng cho quản lý thread thủ công.

## 10. Đặc điểm concurrency đáng chú ý

**Virtual thread không tự tạo structured concurrency.** Tự tạo nhiều thread rồi bỏ qua kết quả dẫn đến task lỗi không ai xử lý hoặc ứng dụng kết thúc giữa chừng. Với phạm vi nhỏ, giữ danh sách thread và `join()`; với tác vụ cần giá trị, chọn `ExecutorService` và đóng tài nguyên. Tránh tạo hàng nghìn task chỉ để chứng minh API có thể tạo được: số virtual thread nhiều không đồng nghĩa backend nhận được cùng số kết nối.

**Không dùng pool virtual thread cố định theo lối cũ như một cơ chế giới hạn I/O.** Virtual thread có chi phí tạo thấp và thường dùng theo mỗi task. Nếu giới hạn 20 request cùng lúc là yêu cầu nghiệp vụ, hãy giới hạn 20 *request hoặc tài nguyên*, chẳng hạn với `Semaphore` hoặc connection pool phù hợp. Dùng số worker thread thấp làm proxy cho giới hạn tài nguyên dễ khiến các task chờ chiếm hết worker.

**Synchronized, native và pinning thay đổi theo JDK.** Trong JDK 21, một số vùng `synchronized` hoặc lời gọi native có thể khiến virtual thread bị *pin* vào carrier khi blocking; việc này có thể hại throughput khi nhiều tác vụ cùng chờ. Các bản JDK mới có cải tiến cơ chế monitor; không nên áp dụng kết luận về pinning của một phiên bản cho mọi JDK. Hãy đo trên phiên bản đang chạy, giữ lock ngắn và tránh giữ lock khi thực hiện I/O lâu khi có thể. Pinning không thay đổi quy tắc `NEW/start/join/TERMINATED` của bài.

**Tên thread hỗ trợ chẩn đoán, không phải định danh nghiệp vụ.** Một task có thể có trace/correlation ID riêng; tên thread có thể trùng, thay đổi hoặc được cấp phát bởi factory. Đừng dùng tên để đồng bộ hay kiểm tra tính duy nhất của yêu cầu.

**Thời điểm tạo và thời điểm chạy khác nhau.** Ví dụ `inheritInheritableThreadLocals(...)` ảnh hưởng giá trị được kế thừa khi **tạo thread**, không phải mỗi lần scheduler gắn một virtual thread vào carrier. Một `ThreadLocal` của carrier không tự trở thành context của mọi virtual thread. Không lưu trạng thái per-request vào biến static dùng chung mà thiếu bảo vệ concurrency.

## 11. Những lỗi phổ biến

| Cách viết / giả định | Vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| `Thread.ofVirtual().unstarted(task)` rồi quên `start()` | Task không bao giờ chạy | Gọi `start()` đúng một lần; dùng `start(task)` nếu muốn chạy ngay |
| `factory.newThread(task)` và nghĩ task đã chạy | Factory chỉ tạo unstarted thread | Chủ động `start()` hoặc giao factory cho executor |
| Gọi `run()` thay `start()` | Không tạo luồng thực thi virtual riêng | Gọi `start()` |
| Gọi `start()` hai lần | `IllegalThreadStateException` | Tạo thread instance mới cho lần chạy tiếp theo |
| Kiểm tra `getState() == RUNNABLE` để chắc chắn task đã hoàn tất | State chỉ là ảnh chụp, có race | `join()` hoặc `Future.get()` |
| Chỉ gọi `isAlive() == false` | Không phân biệt `NEW` và `TERMINATED` | Theo dõi có start hay chưa và cơ chế completion rõ ràng |
| Chương trình main tạo virtual thread rồi thoát | Virtual thread là daemon, có thể không chạy xong | `join()` hoặc đóng executor đúng cách |
| `join()` xong cho rằng task không lỗi | `join()` không truyền exception của task | Dùng handler hoặc `Future` |
| Cho rằng mọi virtual thread đều chạy đồng thời trên CPU riêng | JVM chia sẻ carrier/scheduler | Hiểu đây là concurrency, không phải phép nhân số lõi |
| Tạo `ThreadFactory` chung nhưng tùy tiện chỉnh `Thread.Builder` đồng thời | Builder không thread-safe | Thiết lập builder trước, dùng factory đã tạo |
| Chặn I/O khi giữ monitor quá lâu | Tăng contention/pinning trên những JDK tương ứng | Rút ngắn vùng lock, đo và tối ưu nơi có vấn đề |

## 12. Tình huống tự kiểm tra

**Tình huống A.** Sau `Thread t = Thread.ofVirtual().unstarted(job);`, có thể khẳng định `job` đã chạy? **Không.** `t` còn `NEW` cho tới khi `start()` được gọi thành công.

**Tình huống B.** `ThreadFactory f = Thread.ofVirtual().factory(); Thread t = f.newThread(job);` thì ai gọi `start()`? **Caller** nếu tự quản lý; nếu giao factory cho `ExecutorService`, **executor** sẽ khởi chạy thread phục vụ task.

**Tình huống C.** Sau khi `t.join()` trả về bình thường, `t` có thể `start()` lại? **Không.** Thread instance đã được start không thể start lần hai.

**Tình huống D.** Hai tác vụ `factory.newThread(job)` được `start()` sát nhau; tên lần lượt là `job-1`, `job-2`. Tên nhỏ hơn có nhất thiết in kết quả trước? **Không.** Tên phản ánh thứ tự cấp phát thread, không quyết định lịch chạy.

**Tình huống E.** `Executors.newThreadPerTaskExecutor(factory)` dùng virtual factory có nhất thiết chỉ chạy một thread mỗi lúc? **Không.** Executor dạng này tạo thread mới cho mỗi task; số tác vụ chạy/chờ đồng thời phụ thuộc workload và tài nguyên.

**Tình huống F.** `Thread.State.TERMINATED` có nghĩa task chạy thành công? **Không.** Exception không được bắt cũng có thể làm task kết thúc.

## 13. Tài liệu chuẩn để tra cứu

- [Java SE 21 – Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): `unstarted`, `start`, `factory` và thuộc tính builder.
- [Java SE 21 – Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html): đặt tên, kế thừa thread-local và handler.
- [Java SE 21 – ThreadFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html): contract `newThread` trả thread chưa khởi chạy.
- [Java SE 21 – Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): vòng đời, `start`, `join`, `interrupt`, `isVirtual`.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): mục tiêu và thiết kế virtual threads.

Một cách tự kiểm tra hữu ích là tạo thread bằng `unstarted()`, quan sát `NEW`, gọi `start()`, rồi `join()` để quan sát `TERMINATED`. Khi mở rộng sang nhiều task, giữ đúng sự phân công trách nhiệm: **builder định cấu hình, factory tạo thread, caller hoặc executor khởi chạy, và cơ chế completion xác nhận kết thúc**.
