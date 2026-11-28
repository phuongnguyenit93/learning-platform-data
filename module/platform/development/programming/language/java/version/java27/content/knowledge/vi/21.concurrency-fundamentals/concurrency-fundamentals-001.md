# Thread, tác vụ, trạng thái luồng và thread safety trong Java 27

**Lập trình đồng thời** (*concurrency*) cho phép một chương trình có nhiều công việc đang tiến triển trong cùng một khoảng thời gian. Java hỗ trợ mô hình này bằng `Thread`, các abstraction cho **tác vụ** như `Runnable`/`Callable`, và các API phối hợp trong `java.util.concurrent`. Điểm khó không chỉ là chạy nhiều công việc: khi chúng cùng truy cập dữ liệu, chương trình phải kiểm soát **an toàn luồng** (*thread safety*), tính hiển thị giữa luồng, thứ tự thực thi và hủy công việc.

Trong Java 27, cả **platform threads** và **virtual threads** đều là API Java SE chính thức. Bài này dùng các kiến thức còn áp dụng hiện nay, bao gồm virtual threads (ổn định từ Java 21), `ExecutorService` có thể đóng bằng `try-with-resources`, `AtomicInteger`, `synchronized`, `volatile` và Java Memory Model. Không cần bật preview để chạy những ví dụ hợp lệ được trình bày.

## 1. Concurrency, parallelism, thread và task khác nhau thế nào?

| Thuật ngữ | Ý nghĩa | Cần nhớ |
| --- | --- | --- |
| **Concurrency** | Nhiều công việc có tiến triển xen kẽ theo thời gian | Không bắt buộc nhiều việc chạy đúng cùng một thời điểm |
| **Parallelism** | Hai hoặc nhiều phần việc thực sự chạy cùng lúc trên nhiều tài nguyên xử lý | Phụ thuộc CPU, số lõi, runtime và cách điều phối |
| **Thread** | Luồng thực thi có call stack và trạng thái chạy riêng; đối tượng `java.lang.Thread` | Có thể là **platform** hoặc **virtual** thread |
| **Task** | Mô tả một đơn vị công việc, ví dụ lambda `Runnable` hoặc `Callable<Result>` | Một task không nhất thiết tương ứng với một thread tồn tại lâu dài |
| **Executor** | Thành phần nhận và điều phối task | Giúp tách phần viết nghiệp vụ khỏi cách quản lý thread |
| **Thread safety** | Thuộc tính bảo đảm hành vi đúng khi nhiều thread sử dụng đồng thời theo hợp đồng | Không đồng nghĩa “tốc độ nhanh hơn” hay “không bao giờ block” |

Ví dụ: một ứng dụng nhận 500 yêu cầu HTTP có thể có 500 **tác vụ** đang chờ I/O nhưng số thread đang chiếm CPU ở cùng một thời điểm rất ít. Ngược lại, xử lý 8 phần độc lập của một tính toán nặng CPU có thể chạy **song song** khi có đủ lõi xử lý.

**Nguyên tắc thiết kế:** trước hết xác định *công việc nào có thể độc lập*, *dữ liệu nào bị chia sẻ* và *ai chịu trách nhiệm đợi/hủy/thu hồi tài nguyên*, rồi mới chọn thread hoặc executor phù hợp.

## 2. Tạo và chạy thread trong Java 27

`Thread` đại diện cho một luồng thực thi. Khi gọi `start()` trên thread chưa chạy, Java lập lịch để thread đó thực hiện tác vụ. Không thể gọi `start()` hai lần trên cùng một `Thread`.

### 2.1. Platform thread

Một platform thread thường được gắn với một thread của hệ điều hành trong thời gian hoạt động. Với các tác vụ dài hạn hoặc những hệ thống có nhu cầu thread ở quy mô vừa phải, platform thread vẫn là lựa chọn hợp lệ.

```java
// File: PlatformThreadDemo.java
public class PlatformThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable task = () -> System.out.println(
                "Task đang chạy tại " + Thread.currentThread().getName());

        Thread worker = Thread.ofPlatform()
                .name("report-worker")
                .unstarted(task);

        System.out.println("Trước start: " + worker.getState()); // NEW

        worker.start();
        worker.join(); // Đợi worker kết thúc

        System.out.println("Sau join: " + worker.getState()); // TERMINATED
    }
}
```

Giải thích:

1. `Runnable` mô tả công việc, có method `run()`.
2. `Thread.ofPlatform().unstarted(task)` tạo một thread **chưa bắt đầu**, nên trạng thái ban đầu là `NEW`.
3. `worker.start()` yêu cầu thực thi bất đồng bộ, có thể chạy cùng lúc với main thread.
4. `worker.join()` khiến main thread **đợi worker kết thúc**; khi `join()` trả về bình thường, worker ở `TERMINATED`.
5. Không có bảo đảm thứ tự in giữa hai thread trừ những mốc được đồng bộ. `join()` ở đây chỉ giúp đảm bảo dòng “Sau join” được in sau khi worker hoàn tất.

**Không nhầm `run()` với `start()`.** Gọi `task.run()` chỉ thực thi method trên thread đang gọi; nó **không tạo thread mới**. Với một `Thread` đã gắn task, cũng không nên tự gọi `worker.run()` để mong sinh luồng. Đặc biệt, Java SE 27 mô tả gọi trực tiếp `run()` trên một **virtual thread** sẽ không thực thi task của virtual thread đó; hãy luôn dùng `start()` hoặc builder `start(task)`.

### 2.2. Virtual thread — luồng nhẹ dành cho nhiều tác vụ chờ I/O

Virtual threads là `Thread` được Java runtime lập lịch trên một tập platform threads gọi là *carriers*. Khi một virtual thread thực hiện thao tác chờ được runtime hỗ trợ, nó thường có thể **nhường carrier** cho công việc khác.

```java
// File: VirtualThreadDemo.java
public class VirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.ofVirtual()
                .name("io-request")
                .start(() -> {
                    System.out.println(
                            "Virtual = " + Thread.currentThread().isVirtual());
                    try {
                        Thread.sleep(50);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });

        task.join();
    }
}
```

Ngoài builder, có thể dùng `Thread.startVirtualThread(runnable)` hoặc `Executors.newVirtualThreadPerTaskExecutor()`. Virtual threads là tính năng ổn định từ **Java 21**, nên không cần `--enable-preview` trong Java 27.

| Đặc tính | Platform thread | Virtual thread |
| --- | --- | --- |
| Lập lịch | Chủ yếu do hệ điều hành | Java runtime lập lịch qua carrier threads |
| Chi phí tài nguyên | Thường đắt hơn, dùng thread OS | Nhẹ hơn; phù hợp nhiều tác vụ chờ |
| Bài toán nên xem xét | Nhiệm vụ CPU, quản lý thread truyền thống, tác vụ chuyên biệt | Nhiều request/tác vụ chờ I/O blocking |
| Có phải `Thread`? | Có | Có |
| Có cùng yêu cầu thread safety với dữ liệu chung? | Có | **Có** |
| `isDaemon()` | Tùy cấu hình của platform thread | Virtual thread luôn là daemon |
| Bảo đảm code chạy nhanh hơn trên một CPU? | Không | **Không**; mục tiêu là mở rộng throughput khi chờ |

Virtual thread không làm phép toán CPU tự động nhanh hơn và **không biến ứng dụng có dữ liệu chung thiếu đồng bộ thành an toàn**. Virtual threads mặc định không giữ JVM sống khi các non-daemon threads đã kết thúc; hãy đợi hoặc quản lý vòng đời task rõ ràng.

**Java 27 và pinning:** một số hướng dẫn về JDK trước Java 24 khuyên thay tất cả `synchronized` vì virtual thread có thể bị *pinning* khi chờ trong monitor. Điều này đã thay đổi với **JEP 491 (JDK 24)**: `synchronized` không còn mặc nhiên gây pinning theo kiểu cũ. Việc thực thi mã `native` hoặc foreign function vẫn có thể khiến virtual thread bị pin, ảnh hưởng khả năng mở rộng. Hãy dựa vào tài liệu và công cụ chẩn đoán của JDK đang dùng, **không** thay `synchronized` bằng một loại lock khác chỉ vì lời khuyên lỗi thời.

### 2.3. Không pool virtual threads

Với virtual threads, mô hình được khuyến nghị là **một virtual thread cho mỗi task**, không phải một pool cố định các virtual thread. Nếu chỉ có tối đa 20 kết nối tới một API/DB, giới hạn số thao tác đang dùng tài nguyên bằng `Semaphore`, pool kết nối hay chính sách backpressure thích hợp, thay vì pool virtual threads để mô phỏng giới hạn tài nguyên.

Với platform threads, thread pool vẫn có ý nghĩa để kiểm soát chi phí thread OS và số task chạy đồng thời. Sự phân biệt này rất quan trọng khi chọn `ExecutorService`.

## 3. Runnable, Callable và ExecutorService: tách công việc khỏi thread

`Runnable` và `Callable<V>` đều biểu diễn công việc, không phải một thread cụ thể:

| Giao diện | Method | Kết quả | Checked exception |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | Không trả về giá trị | `run()` không khai báo `throws` checked exception |
| `Callable<V>` | `V call() throws Exception` | Trả kết quả kiểu `V` | Có thể ném checked exception |
| `Future<V>` | `get()`, `cancel(...)`, `isDone()` | Đại diện kết quả tác vụ đã gửi | `get()` có thể đợi và ném `ExecutionException`/`InterruptedException` |

Một `ExecutorService` nhận task và chịu trách nhiệm thực thi. Tùy implementation, nó có thể dùng pool platform threads hoặc tạo một virtual thread mới cho mỗi task.

### 3.1. Ví dụ hai tác vụ đồng thời có kết quả

```java
// File: ExecutorTasksDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorTasksDemo {
    static int slowSquare(int input) throws InterruptedException {
        Thread.sleep(30); // Mô phỏng thao tác đang chờ I/O
        return input * input;
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Future<Integer> a = executor.submit(() -> slowSquare(3));
            Future<Integer> b = executor.submit(() -> slowSquare(4));

            int total = a.get() + b.get();
            System.out.println(total); // 25
        }
    }
}
```

Trong ví dụ:

- Hai `Callable<Integer>` được gửi vào executor. Mỗi task có virtual thread riêng theo hợp đồng của `newVirtualThreadPerTaskExecutor()`.
- `submit` trả `Future<Integer>`. `Future.get()` chờ kết quả và truyền các lỗi phù hợp cho caller.
- `try-with-resources` đóng executor khi ra khỏi khối. `ExecutorService.close()` khởi tạo shutdown và **đợi các task hoàn tất** theo hợp đồng, không bỏ mặc các task sau khi thoát `main`.
- `slowSquare` chỉ mô phỏng độ trễ; thời gian hoàn tất thực tế và thứ tự chạy là không xác định.

Không cần `synchronized` cho hai task trên vì mỗi task dùng dữ liệu đầu vào riêng và trả kết quả độc lập; main thread chỉ cộng kết quả **sau `get()`**.

### 3.2. Chọn executor theo nhu cầu

| Nhu cầu | API thường phù hợp |
| --- | --- |
| Tác vụ độc lập, rất nhiều thao tác chờ I/O | `Executors.newVirtualThreadPerTaskExecutor()` |
| Giới hạn số platform threads thực thi cùng lúc | `Executors.newFixedThreadPool(n)` |
| Chạy việc theo lịch hoặc định kỳ | `ScheduledExecutorService` |
| Task nhỏ theo kiểu fork/join, chủ yếu CPU | `ForkJoinPool` hoặc executor được thiết kế cho workload CPU |
| Cần tự tinh chỉnh hàng chờ, từ chối, giới hạn tải | `ThreadPoolExecutor` hoặc kiến trúc backpressure cụ thể |

Không mặc định dùng `Executors.newCachedThreadPool()` để xử lý lưu lượng không giới hạn: số platform threads có thể tăng mạnh khi tải đến dồn dập. `newFixedThreadPool(n)` giới hạn **thread worker**, nhưng factory này dùng queue không giới hạn dung lượng; nó **không tự giải quyết backpressure**. Thiết kế sản xuất cần giới hạn tác vụ đang chờ, timeout, metric và phương án xử lý quá tải.

### 3.3. Exception trong tác vụ

Khi dùng `submit(Callable)` hoặc `submit(Runnable)`, lỗi từ task được truyền qua `Future.get()` dưới dạng `ExecutionException` (với nguyên nhân gốc trong `getCause()`). Nếu không gọi `get()` hoặc không quan sát kết quả, lỗi có thể bị bỏ sót.

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Integer> result = executor.submit(() -> {
        throw new IllegalArgumentException("bad input");
    });

    try {
        result.get();
    } catch (java.util.concurrent.ExecutionException e) {
        System.out.println(e.getCause().getMessage()); // bad input
    }
}
```

Đoạn trên là mảnh ví dụ cần đặt trong method khai báo `throws InterruptedException` (hoặc xử lý tương ứng). `execute(Runnable)` và `submit(...)` có cơ chế báo lỗi khác nhau; hãy thiết lập logging/quan sát lỗi cho từng mô hình thay vì kỳ vọng mọi exception đều tự xuất hiện trên main thread.

## 4. Vòng đời và sáu trạng thái Thread.State

`Thread.State` trong Java SE 27 có đúng **sáu trạng thái**:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `NEW` | Thread được tạo nhưng chưa gọi `start()` | `Thread.ofPlatform().unstarted(task)` |
| `RUNNABLE` | Thread đủ điều kiện chạy hoặc đang chạy trong JVM | Sau `start()`, khi không bị kẹt chờ theo các trạng thái Java |
| `BLOCKED` | Chờ lấy monitor lock để vào `synchronized` | Một thread đang giữ cùng monitor |
| `WAITING` | Đợi vô thời hạn cho sự kiện khác | `join()` không timeout, `Object.wait()`, `LockSupport.park()` |
| `TIMED_WAITING` | Đợi tối đa một khoảng thời gian | `Thread.sleep(...)`, `join(timeout)`, `Object.wait(timeout)` |
| `TERMINATED` | Method thực thi kết thúc bình thường hoặc bất thường | Task đã chạy xong và thread chết |

Sơ đồ diễn giải các **nhánh thường gặp**, không phải toàn bộ mọi chuyển trạng thái nội bộ:

```text
NEW --start()--> RUNNABLE --------------------> TERMINATED
                  │    ▲
                  │    │ monitor available / wakeup
                  ├--> BLOCKED      (đợi monitor)
                  ├--> WAITING      (join, wait, park)
                  └--> TIMED_WAITING (sleep, timed join/wait)
```

Những điều không nên hiểu sai:

1. `RUNNABLE` **không bảo đảm đang sử dụng CPU tại thời điểm gọi `getState()`**. Thread có thể đang được scheduler xếp hàng hoặc chờ tài nguyên của hệ điều hành.
2. `BLOCKED` không phải tên gọi tổng quát cho mọi kiểu I/O blocking. Trạng thái này dành cho tình huống đợi **monitor lock**.
3. `getState()` là một **ảnh quan sát tức thời**, được tài liệu thiết kế cho monitoring, **không** để viết thuật toán đồng bộ dựa vào việc canh trạng thái.
4. `WAITING` và `TIMED_WAITING` chỉ mô tả kiểu chờ theo Java; không cung cấp một thứ tự công bằng giữa các thread.
5. Với virtual threads, các trạng thái vẫn do `Thread.State` mô tả. Không suy luận rằng mỗi virtual thread chiếm riêng một OS thread hoặc mỗi thay đổi trạng thái phải phản ánh chính xác một thay đổi trạng thái OS.

### 4.1. Thử quan sát trạng thái một cách xác định

Chỉ hai mốc trước `start()` và sau `join()` mới có đầu ra đơn giản, dễ dự đoán:

```java
// File: ThreadStateDemo.java
public class ThreadStateDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofPlatform().unstarted(
            () -> System.out.println("Đang làm việc"));

        System.out.println(worker.getState()); // NEW
        worker.start();
        worker.join();
        System.out.println(worker.getState()); // TERMINATED
    }
}
```

Nếu quan sát `getState()` ngay sau `start()`, có thể thấy các trạng thái khác nhau tùy lịch thực thi. Không dùng `Thread.sleep(100)` để “ép” một thread khác đạt `BLOCKED`/`WAITING`: thời gian chờ **không** là cơ chế đồng bộ đáng tin cậy.

### 4.2. Thread không khởi động lại sau TERMINATED

```java
Thread task = Thread.ofPlatform().unstarted(() -> {});
task.start();
task.join();

// task.start(); // IllegalThreadStateException
```

Nếu muốn chạy cùng một logic nhiều lần, tạo task mới và gửi lại qua executor, hoặc tạo đối tượng `Thread` mới. Không làm hệ thống phụ thuộc vào việc khởi động lại một Thread đã kết thúc.

## 5. Thread safety: vì sao chương trình có nhiều thread lại sai?

Ba vấn đề cốt lõi khi dùng mutable state chung:

- **Atomicity — tính nguyên tử:** phép toán có được xem là một hành động không thể bị chen ngang không? Ví dụ `count++` thực chất gồm đọc, cộng và ghi.
- **Visibility — tính hiển thị:** một thread có chắc nhìn thấy giá trị vừa được thread khác ghi không? Java Memory Model không bảo đảm việc truyền dữ liệu tự do qua các biến thường thiếu quan hệ đồng bộ.
- **Ordering — thứ tự quan sát:** compiler, CPU và JVM có thể sắp xếp lại các thao tác trong những giới hạn cho phép; logic nhiều thread phải dựa trên các quan hệ **happens-before** hợp lệ.

### 5.1. Data race với count++

Một counter thiếu bảo vệ:

```java
final class UnsafeCounter {
    int count;

    void increment() {
        count++; // đọc → cộng → ghi; không nguyên tử
    }

    int get() {
        return count;
    }
}
```

Giả sử hai thread cùng đọc `count = 5`, cả hai đều cộng thành `6` rồi ghi lại. Đúng ra sau hai increment phải là `7`, nhưng kết quả có thể chỉ là `6`. Đây là **lost update**, một dạng lỗi do data race.

```text
                Giá trị chung count = 5
Thread A: read 5 ── +1 ── write 6
Thread B:   read 5 ── +1 ── write 6
                                  └── Kết quả 6 thay vì 7
```

Một chương trình sai vẫn có thể **thỉnh thoảng** in đúng kết quả vì các thread được lập lịch khác nhau giữa các lần chạy. Thử chạy một ví dụ hàng trăm lần cũng không chứng minh một implementation thread-safe; phải suy luận theo hợp đồng đồng bộ.

### 5.2. Java Memory Model và happens-before

*Happens-before* mô tả khi nào các tác động ghi/đọc được bảo đảm về khả năng quan sát và thứ tự giữa các thread. Một số quan hệ quan trọng theo JLS `17.4.5 và API concurrency:

| Quan hệ | Điều được đảm bảo |
| --- | --- |
| Trong một thread | Các thao tác trước đó theo program order happens-before các thao tác sau của chính thread |
| `Thread.start()` | Các hành động xảy ra trước `start()` happens-before hành động trong thread được khởi chạy |
| `Thread.join()` thành công | Các hành động của thread đã kết thúc happens-before hành động sau thời điểm thread khác nhận biết kết thúc bằng `join()` |
| Monitor `synchronized` | Unlock một monitor happens-before lần lock tiếp theo trên **cùng monitor** |
| `volatile` | Write vào một biến volatile happens-before read sau đó trên **cùng biến** theo quy tắc đồng bộ |
| `Future.get()` | Hành động do task thực hiện happens-before hành động tiếp tục sau khi lấy kết quả qua `get()` |
| Hàng đợi / collection concurrent | Có bảo đảm bộ nhớ được mô tả riêng trong Javadoc của mỗi cấu trúc |

**Happens-before không phải “thread A chắc được scheduler chạy trước thread B”.** Nó mô tả các quan hệ đồng bộ giữa hành động. Ví dụ gọi `start()` tạo quan hệ memory visibility với task, nhưng thread được khởi chạy vẫn có thể phải đợi lịch CPU. Lỗi race không thể sửa bằng cách đơn thuần tăng thời gian `sleep`.

## 6. Chiến lược ưu tiên số một: hạn chế mutable state chia sẻ

Trước khi dùng lock, hãy cân nhắc thiết kế dữ liệu sao cho không phải tranh chấp:

1. **Immutable object:** record hoặc object với các thành phần bất biến, được khởi tạo hợp lệ và công bố an toàn.
2. **Thread confinement:** mỗi task sở hữu biến cục bộ hoặc collection riêng; chỉ trả kết quả khi xong.
3. **Message passing:** trao đổi phần tử qua một cấu trúc truyền dữ liệu có bảo đảm đồng bộ, ví dụ `BlockingQueue`.
4. **State ownership:** một thành phần duy nhất chịu trách nhiệm chỉnh sửa state; các thành phần khác gửi request hay đọc snapshot.

Ví dụ với record đơn giản:

```java
record InvoiceLine(String code, long quantity, long unitPriceCents) {
    long totalCents() {
        return Math.multiplyExact(quantity, unitPriceCents);
    }
}
```

`InvoiceLine` chỉ giữ `String` và các primitive bất biến. Nhiều thread có thể đọc cùng record sau khi nó được công bố an toàn mà không cần đồng bộ riêng cho việc đọc.

**Lưu ý:** record không tự biến mọi dữ liệu bên trong thành immutable. Nếu một component là `List<String>` mutable, có thể tạo bản sao phòng vệ bằng `List.copyOf` khi xây record. Với object chứa mutable state lồng sâu, cần kiểm tra mức độ bất biến của toàn bộ dữ liệu được chia sẻ.

### 6.1. Công bố đối tượng đúng cách

`final` field có các quy tắc hỗ trợ safe initialization theo JLS `17.5, nhưng không phải giấy phép để đưa một object chưa khởi tạo xong cho thread khác. Tránh để `this` *thoát ra ngoài* từ constructor, hoặc khởi chạy background thread trong constructor khiến nó đọc field trước khi invariant hoàn chỉnh.

Khi cần chia sẻ object sau khởi tạo, dùng cơ chế công bố có quan hệ happens-before rõ ràng như đưa vào concurrent queue, truyền vào thread trước `start()`, hoặc giữ trong state được đồng bộ hợp lệ.

## 7. Ba công cụ cơ bản cho state chung: synchronized, volatile, atomic

### 7.1. synchronized — bảo vệ invariant của một vùng code

`synchronized` dùng monitor để chỉ cho một thread giữ lock vào cùng thời điểm. Khi **mọi thao tác liên quan cùng một state** đều được bảo vệ qua đúng monitor, nó vừa bảo vệ atomicity của một đoạn lệnh, vừa bảo đảm visibility qua lần unlock/lock phù hợp.

```java
final class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Hai method `synchronized` trên instance ở ví dụ dùng **monitor của cùng object `SafeCounter`**. Nếu trong một method khác truy cập `count` mà không qua monitor/đồng bộ phù hợp, hợp đồng thread safety sẽ bị phá vỡ.

`synchronized` còn hữu ích với invariant nhiều field:

```java
final class Wallet {
    private long balanceCents;

    Wallet(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balanceCents = initialBalanceCents;
    }

    synchronized boolean withdraw(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (amountCents > balanceCents) {
            return false;
        }

        balanceCents -= amountCents;
        return true;
    }

    synchronized long balanceCents() {
        return balanceCents;
    }
}
```

Phép kiểm tra số dư và trừ số tiền nằm trong **cùng critical section**; nếu tách chúng thành hai bước riêng mà không đồng bộ toàn bộ, hai thread có thể cùng tiêu một khoản tiền. Đây là logic thread safety; logic nghiệp vụ thực còn cần lưu trữ/giao dịch bền vững, xác thực và xử lý retry.

### 7.2. volatile — bảo đảm visibility, không biến count++ thành nguyên tử

`volatile` thường phù hợp với **cờ trạng thái đơn lẻ** được đọc/ghi từ nhiều thread:

```java
final class StopSignal {
    private volatile boolean stopRequested;

    void requestStop() {
        stopRequested = true;
    }

    boolean shouldStop() {
        return stopRequested;
    }
}
```

Một thread ghi `requestStop()` và thread khác kiểm tra `shouldStop()` sẽ nhận bảo đảm visibility của biến volatile. Nhưng `volatile` **không biến một chuỗi read–modify–write thành atomic**:

```java
final class NotAnAtomicCounter {
    volatile int value;

    void increment() {
        value++; // VẪN có thể bị lost update
    }
}
```

Đừng tự tạo vòng `while (!stop) {}` để đợi vô hạn trong chương trình thực tế: đó là *busy-wait*, tốn CPU. Với tác vụ đang block, ưu tiên interrupt, `BlockingQueue`, `CountDownLatch` hoặc cơ chế báo hiệu phù hợp.

### 7.3. AtomicInteger — phép cộng/cập nhật một biến nguyên tử

Với bộ đếm độc lập không cần khóa bảo vệ invariant nhiều trường:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    int incrementAndGet() {
        return count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
```

`incrementAndGet()` bảo đảm phép tăng là atomic. Với tải ghi cạnh tranh lớn và mục tiêu thống kê tổng, có thể cân nhắc `LongAdder`:

```java
java.util.concurrent.atomic.LongAdder requests =
        new java.util.concurrent.atomic.LongAdder();

requests.increment();
long observed = requests.sum();
```

`LongAdder` hướng tới hiệu năng tốt khi nhiều thread cùng cập nhật, nhưng `sum()` **không phải snapshot nguyên tử** nếu vẫn đang có cập nhật đồng thời. Nếu phải bảo vệ invariant “giá trị này chính xác ngay thời điểm quyết định”, dùng một cơ chế có bảo đảm phù hợp hơn.

### 7.4. ReentrantLock — khi cần khóa có điều khiển rõ ràng

`ReentrantLock` bổ sung API như `tryLock()`, `lockInterruptibly()` và nhiều condition. Nếu sử dụng, **luôn unlock trong finally**:

```java
import java.util.concurrent.locks.ReentrantLock;

final class LockedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

Đừng dùng lock chỉ để “làm code nhanh hơn” khi không có nhu cầu. Dùng `synchronized` trước nếu nó đủ đơn giản và đúng; `ReentrantLock` hữu ích khi cần khả năng điều khiển nâng cao.

## 8. Ví dụ hoàn chỉnh: 4 tác vụ tăng bộ đếm an toàn

Đoạn chương trình sau dùng `ExecutorService`, `AtomicInteger` và `Future`. Dù thứ tự tăng giữa các worker không được xác định, **giá trị tổng sau khi tất cả kết thúc được bảo đảm**.

```java
// File: AtomicCounterDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws Exception {
        final int workers = 4;
        final int incrementsPerWorker = 10_000;
        AtomicInteger count = new AtomicInteger();

        try (ExecutorService executor = Executors.newFixedThreadPool(workers)) {
            List<Future<?>> futures = new ArrayList<>();

            for (int w = 0; w < workers; w++) {
                futures.add(executor.submit(() -> {
                    for (int i = 0; i < incrementsPerWorker; i++) {
                        count.incrementAndGet();
                    }
                }));
            }

            for (Future<?> future : futures) {
                future.get(); // Đợi và kiểm tra lỗi từ từng task
            }
        }

        System.out.println("Total = " + count.get()); // Total = 40000
    }
}
```

Nếu thay `AtomicInteger` bằng một `int` được bọc trong mutable holder và dùng `++` mà không bảo vệ, kết quả **có thể nhỏ hơn 40.000** do lost updates; đôi khi vẫn có thể bằng 40.000, nên không dùng “chạy một lần thấy đúng” làm bằng chứng an toàn.

Nếu tác vụ chủ yếu chờ I/O, ta có thể thay executor bằng `newVirtualThreadPerTaskExecutor()` mà **không thay đổi yêu cầu bảo vệ `count`**: loại thread không sửa được data race.

## 9. Phối hợp task bằng collection và đồng bộ cấp cao

Với nhiều loại bài toán, API concurrency cấp cao dễ hiểu và ít lỗi hơn việc tự dùng `wait()/notify()`:

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `BlockingQueue<E>` | Producer–consumer, đợi khi queue rỗng/đầy tùy implementation | Dùng queue **bounded** nếu cần backpressure |
| `ConcurrentHashMap<K,V>` | Map cho truy cập đồng thời | Dùng `compute`/`merge` cho cập nhật theo key; nhiều thao tác rời nhau chưa tạo transaction toàn Map |
| `CountDownLatch` | Đợi một số sự kiện hoàn tất | Một lần, không reset |
| `Semaphore` | Giới hạn số thao tác đồng thời tới tài nguyên khan hiếm | Cần cân bằng `acquire()/release()` |
| `CompletableFuture` | Kết hợp các kết quả async theo stage | Tránh block hoặc side effect không rõ, quản lý executor rõ |
| `Future` | Quan sát kết quả, đợi, hủy một task | `get()` có thể block và ném exception |

### 9.1. BlockingQueue giúp truyền dữ liệu có phối hợp

```java
// File: QueueHandoffDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class QueueHandoffDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Future<?> producer = executor.submit(() -> {
                queue.put("ready");
                return null;
            });

            Future<String> consumer = executor.submit(() -> {
                return queue.take();
            });

            producer.get();
            System.out.println(consumer.get()); // ready
        }
    }
}
```

`ArrayBlockingQueue<>(2)` có sức chứa tối đa hai phần tử; `put()` có thể đợi khi đầy, `take()` có thể đợi khi rỗng. Những method này có bảo đảm truyền dữ liệu/visibility theo hợp đồng của `BlockingQueue`, nên không cần tự thêm một lock để bảo vệ chính dữ liệu bên trong queue.

Chương trình demo giữ task nhỏ. Trong hệ thống thực tế, cần chính sách **dừng producer/consumer** khi chạy lâu, timeout và xử lý interrupt để không chờ vô hạn.

### 9.2. ConcurrentHashMap: cập nhật atomic theo key

```java
import java.util.concurrent.ConcurrentHashMap;

ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();

counts.merge("north", 1, Integer::sum);
counts.merge("north", 1, Integer::sum);

System.out.println(counts.get("north")); // 2
```

`merge` cho phép thực hiện cập nhật một key theo hợp đồng thread-safe của Map. Nhưng viết `if (map.get(key) == null) map.put(key, value)` thành hai thao tác rời có thể có race khi nhiều thread cùng cập nhật. `ConcurrentHashMap` không tự làm **mọi chuỗi nhiều lệnh** thành atomic transaction.

## 10. Interrupt và hủy tác vụ đúng cách

`Thread.interrupt()` là một **yêu cầu phối hợp**: nó đặt trạng thái interrupted hoặc khiến một số thao tác chờ phản ứng bằng `InterruptedException`. Nó **không phải** lệnh cưỡng bức thread dừng tức thì.

### 10.1. Đoạn ví dụ có thể chạy

```java
// File: CooperativeCancellationDemo.java
public class CooperativeCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    System.out.println("Working...");
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt(); // Giữ tín hiệu hủy
            } finally {
                System.out.println("Cleanup done");
            }
        });

        Thread.sleep(100);
        worker.interrupt();
        worker.join();
    }
}
```

Kết quả: `Cleanup done` luôn được in nếu worker chạy qua `finally`; dòng `Working...` có thể xuất hiện khác nhau tùy lịch chạy. Nếu interrupt đến trước khi worker bắt đầu chạy, `Thread.sleep` có thể ném ngay. Không dựa vào `sleep(100)` như cơ chế đồng bộ; nó chỉ giúp mô phỏng một chương trình muốn ngắt công việc.

Khi method `Thread.sleep`, `join` hoặc `BlockingQueue.take` ném `InterruptedException`, interrupted status của thread thường đã bị **xóa** trong thao tác báo lỗi. Nếu tầng hiện tại không ném tiếp `InterruptedException`, có thể **khôi phục cờ** bằng `Thread.currentThread().interrupt()` trước khi kết thúc/ủy quyền theo chính sách hủy. Không nuốt exception rồi lặp lại vô hạn.

### 10.2. Future.cancel(true) không bảo đảm dừng cưỡng bức

Với `Future<?> future`:

```java
boolean accepted = future.cancel(true);
```

`cancel(true)` **yêu cầu** hủy tác vụ, có thể interrupt thread đang chạy nếu implementation hỗ trợ. Nếu code không phản ứng với interrupt hoặc đang ở đoạn không thể ngắt, tác vụ có thể tiếp tục chạy một thời gian. `cancel(false)` tránh yêu cầu interrupt task đang chạy nhưng vẫn có thể hủy task chưa bắt đầu.

Đừng dùng các API dừng thread cưỡng bức đã bị đánh dấu không an toàn như `Thread.stop()`, `Thread.suspend()` hoặc `Thread.resume()` để quản lý tác vụ mới. Hãy xây cơ chế hủy hợp tác, timeout và giải phóng tài nguyên trong `finally`/try-with-resources.

### 10.3. Đừng dùng interrupt như tín hiệu dữ liệu nghiệp vụ

Interrupt thường dùng cho vòng đời/cancellation. Nếu muốn báo rằng “có một thông điệp mới”, gửi dữ liệu qua `BlockingQueue`, `Future` hoặc một tín hiệu đồng bộ phù hợp. Không dùng thread state, `sleep` hay interrupt để tự xây một giao thức thông điệp khó kiểm chứng.

## 11. Deadlock, starvation và thread safety không chỉ là synchronized

Một chương trình có thể không có data race rõ ràng nhưng vẫn **không có tiến triển**:

- **Deadlock:** các thread chờ nhau giữ lock, không ai có thể tiếp tục.
- **Starvation:** một thread/tác vụ thiếu cơ hội chạy hoặc lấy tài nguyên trong thời gian dài.
- **Livelock:** các thread liên tục phản ứng với nhau nhưng không hoàn thành mục tiêu.
- **Contention:** nhiều thread cạnh tranh cùng tài nguyên, làm giảm throughput.

Ví dụ mô hình deadlock:

```text
Thread A: đã khóa X, chờ Y
Thread B: đã khóa Y, chờ X

A ──đợi──> Y (do B giữ)
B ──đợi──> X (do A giữ)
⇒ không có tiến triển
```

Các biện pháp thiết kế:

1. Khi cần nhiều lock, lấy lock theo **một thứ tự toàn cục** nhất quán.
2. Thu nhỏ critical section; tránh gọi network I/O, callback của người dùng hoặc method có thể block rất lâu khi đang giữ lock nếu không cần.
3. Dùng timeout hoặc `tryLock` khi bài toán yêu cầu phát hiện nghẽn và thoát có kiểm soát.
4. Tránh lock lồng nhau nếu có thể thay bằng ownership hoặc thiết kế message passing.
5. Quan sát bằng thread dump, metric queue và JFR để xác định bottleneck thay vì thêm `sleep` tùy ý.

**Quan trọng:** `Thread.sleep` **không nhả monitor của `synchronized` đang giữ**. `Object.wait` nhả monitor theo quy tắc riêng nhưng cần được gọi khi sở hữu monitor và dùng vòng lặp kiểm tra điều kiện. Với code Java 27 mới, thường nên ưu tiên các abstraction như `BlockingQueue`/`CountDownLatch` hơn là tự viết wait/notify protocol trừ khi thực sự cần.

## 12. Virtual threads không giải quyết mọi bài toán concurrency

Virtual threads tăng khả năng xử lý **nhiều tác vụ chờ I/O**, nhưng không thay thế các nguyên tắc:

- **Dữ liệu chia sẻ:** virtual thread và platform thread đều cần synchronization/atomic/concurrent collections phù hợp.
- **Giới hạn tài nguyên:** tạo nhiều virtual threads không làm DB connection, API quota hay bộ nhớ trở nên vô hạn. Dùng `Semaphore` hoặc các giới hạn ứng dụng.
- **CPU-bound:** hàng triệu virtual threads cùng tính toán nặng CPU không khiến CPU có thêm lõi; song song hóa hợp lý theo số bộ xử lý mới có ích.
- **ThreadLocal:** có thể tồn tại với virtual threads nhưng mỗi virtual thread mang state riêng sẽ đắt khi số lượng tăng lớn; cân nhắc truyền tham số rõ ràng khi thích hợp.
- **Bảo vệ vòng đời:** virtual threads là daemon; đợi chúng bằng `join` hoặc quản lý qua executor/task scope có vòng đời rõ ràng.
- **Mã native/foreign:** có thể khiến virtual thread bị pin trong một số thao tác và giảm khả năng mở rộng.
- **Truy xuất lỗi:** đừng bỏ qua `Future` hoặc exception từ task.

**Kết luận thiết kế:** phân loại workload trước khi chọn số thread; dùng virtual threads cho nhiều tác vụ I/O blocking, còn dữ liệu chung vẫn cần những hợp đồng thread safety như trước.

## 13. Kiểm thử và quan sát lỗi concurrency

Lỗi concurrency có thể biến mất khi thêm `println` hoặc chạy debugger vì lịch thực thi thay đổi. Cách tiếp cận đáng tin cậy hơn:

1. Đọc và mô tả **invariant**: ví dụ “số dư không âm” hoặc “mỗi giao dịch chỉ được ghi một lần”.
2. Liệt kê mọi lối đọc/ghi dữ liệu mutable, đảm bảo chúng được bảo vệ bởi cùng chiến lược đồng bộ.
3. Dùng `Future.get()`, `join()`, `CountDownLatch` hoặc queue để điều phối test; **không dùng `sleep` làm bằng chứng hoàn tất**.
4. Khi test nhiều tác vụ, lưu lại exception và fail test nếu worker lỗi; đừng chỉ in log.
5. Tạo test stress với nhiều lần lặp, nhiều mức đồng thời và giá trị đầu vào khác nhau; kết quả đúng sau một vài lượt không chứng minh hết mọi race.
6. Đo hiệu năng với workload/CPU/I/O thực tế; tránh khẳng định virtual threads sẽ luôn nhanh hơn.
7. Sử dụng thread dump và Java Flight Recorder (JFR) để xem chờ lock, I/O và bottleneck; đọc trạng thái như tín hiệu quan sát, không như cơ chế điều phối.

### 13.1. getState và threadId trong chẩn đoán

`Thread.getState()` trả snapshot phục vụ monitoring. Trong Java hiện hành, `Thread.threadId()` là API thích hợp để đọc định danh thread; không nên ưu tiên `Thread.getId()` vì method này đã bị đánh dấu deprecated từ Java 19.

```java
Thread current = Thread.currentThread();
System.out.println(current.threadId());
System.out.println(current.getName());
System.out.println(current.getState());
System.out.println("Virtual = " + current.isVirtual());
```

Không dùng `threadId`, tên thread hay `getState()` làm khóa đồng bộ hoặc quyết định “task chắc đã xong”. Dùng `join`, `Future` hoặc một tín hiệu hoàn tất có quan hệ happens-before.

## 14. Bảng lỗi thường gặp trong Java 27

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gọi `run()` nhưng công việc không chạy đồng thời | `run` không thay cho `start` | Dùng `start`/builder `start`/executor |
| `IllegalThreadStateException` khi gọi `start()` | Một Thread chỉ bắt đầu được một lần | Tạo Thread mới hoặc gửi task mới |
| Đọc `RUNNABLE` nhưng không thấy CPU sử dụng | RUNNABLE không đồng nghĩa ngay lúc đó đang dùng CPU | Đọc `Thread.State` như snapshot JVM |
| Kết quả `count++` ít hơn mong đợi | Lost update do read–modify–write không atomic | Dùng `AtomicInteger`, `synchronized` hoặc lock |
| Đặt `volatile` lên counter nhưng vẫn mất increment | Volatile giải quyết visibility, không giải quyết compound atomicity | Dùng atomic update |
| Khóa một method nhưng method khác đọc/ghi trực tiếp | Không thống nhất bảo vệ state | Dùng cùng monitor/lock hoặc thiết kế immutable |
| `Thread.sleep(...)` dùng để chờ task kết thúc | Sleep chỉ trì hoãn caller | Dùng `join()` hoặc `Future.get()` |
| `Future.get()` treo rất lâu | Task chờ I/O/lock hoặc lỗi vòng đời | Dùng timeout, cancellation, metric và xem thread dump |
| Task bị hủy mà vẫn tiếp tục | Interrupt là tín hiệu hợp tác | Xử lý InterruptedException, kiểm tra cờ, cleanup |
| `catch (InterruptedException e) {}` | Nuốt tín hiệu ngắt | Ném tiếp hoặc khôi phục `Thread.currentThread().interrupt()` |
| Nhiều virtual threads nhưng DB vẫn nghẽn | Giới hạn tài nguyên ngoài CPU vẫn tồn tại | Giới hạn số kết nối/tác vụ đồng thời bằng Semaphore và pool kết nối |
| Code dùng virtual thread thay `synchronized` hàng loạt | Dựa vào tài liệu pinning trước JDK 24 | Dùng hướng dẫn Java 27/JEP 491, chỉ tối ưu khi có dữ liệu quan sát |
| Một Map là ConcurrentHashMap nhưng logic nhiều bước vẫn race | Thread-safe operation đơn lẻ không làm cả chuỗi thành atomic | Dùng `compute/merge` hoặc kiểm soát transaction/invariant |
| App kết thúc trước khi virtual task in kết quả | Virtual threads là daemon; không có chờ hoàn tất | `join` hoặc quản lý ExecutorService bằng try-with-resources |
| Không thấy exception của task đã `submit` | Kết quả Future bị bỏ qua | Gọi `get`/gắn cơ chế logging và xử lý lỗi |
| Deadlock vì lấy lock ngược thứ tự | Mỗi thread giữ lock và đợi lock kia | Quy ước thứ tự lock, tránh nested locks, thiết kế timeout |

## 15. Checklist trước khi đưa concurrent code vào production

- **Định nghĩa task và owner:** ai tạo, ai đợi hoàn tất, ai hủy và giải phóng tài nguyên?
- **Chọn loại thread đúng workload:** platform pool cho workload có số worker giới hạn; virtual per task cho nhiều thao tác chờ I/O.
- **Không lẫn thread với task:** ưu tiên khai báo `Runnable`/`Callable` và một executor phù hợp thay vì quản lý hàng nghìn Thread thủ công.
- **Hiểu sáu trạng thái:** `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`; không dùng `getState()` làm điều kiện đồng bộ.
- **Tách dữ liệu riêng trước:** dùng immutable records, local variables hoặc message passing khi có thể.
- **Bảo vệ mọi mutable state chia sẻ:** kiểm tra atomicity, visibility, ordering và các happens-before relations.
- **Chọn đúng công cụ:** `volatile` cho state đơn giản; atomic cho một biến; `synchronized`/`ReentrantLock` cho invariant; concurrent collection/queue cho truyền dữ liệu.
- **Không dùng sleep để chờ kết quả:** `join()`, `Future.get()`, `BlockingQueue` và `CountDownLatch` có hợp đồng cụ thể.
- **Xử lý interrupt hợp tác:** không nuốt `InterruptedException`, không dùng API dừng thread cưỡng bức.
- **Giới hạn tải:** queue/capacity/DB connections vẫn hữu hạn dù dùng virtual threads.
- **Theo dõi lỗi và tiến triển:** quan sát exception, deadlock, starvation, CPU, queue length và blocked time.
- **Kiểm thử có chủ đích:** test race, cancellation, timeout, cleanup, task lỗi và shutdown executor.
- **Theo tài liệu Java 27 hiện hành:** tránh áp dụng hướng dẫn cũ về virtual-thread pinning hoặc các API đã bị deprecated.

## Tài liệu tham khảo chính thức

- [`Thread` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html) — platform/virtual threads, `start`, `join`, interruption, `threadId` và life cycle.
- [`Thread.State` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.State.html) — sáu trạng thái JVM và ý nghĩa chính xác.
- [`Runnable` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runnable.html) — task không kết quả.
- [`Callable<V>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Callable.html) — task có kết quả và checked exceptions.
- [`ExecutorService` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html) — submit, shutdown/close, `Future` và quan hệ bộ nhớ.
- [`Executors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html) — factory platform/virtual thread executor.
- [`Future<V>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html) — completion, `get()`, hủy và error propagation.
- [`AtomicInteger` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html) — các cập nhật atomic của bộ đếm.
- [`ConcurrentHashMap` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) — các thao tác map đồng thời.
- [`CountDownLatch` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html) — phối hợp hoàn tất.
- [JLS Java SE 27 — Chapter 17: Threads and Locks](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html) — Java Memory Model, happens-before, synchronization và `final` field semantics.
- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — lựa chọn virtual threads, scheduling, throughput, pinning và tác vụ I/O.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — chuẩn hóa virtual threads từ Java 21.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — cải tiến monitor và virtual thread pinning được đưa vào JDK 24.
