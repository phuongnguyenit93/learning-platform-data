# Đọc thông tin Thread hiện tại: currentThread(), name và ID trong Java

## Bạn sẽ học được gì?

Khi một đoạn mã chạy đồng thời với những đoạn mã khác, câu hỏi đầu tiên để hiểu hành vi của nó thường là **“Đoạn mã này đang chạy trên thread nào?”**. Java cung cấp đối tượng `Thread` mô tả thread đang thực thi. Từ đối tượng đó, ta có thể đọc **tên** (`name`) và **mã định danh thread** (`ID`), đưa vào log, kiểm tra khi debug hoặc phân biệt các luồng trong thí nghiệm concurrency.

Sau bài học, bạn có thể:
- Gọi đúng `Thread.currentThread()` để lấy thread thực sự đang chạy đoạn mã hiện tại.
- Đọc `getName()` và `getId()` trong Java 17; hiểu `threadId()` được bổ sung từ Java 19.
- Phân biệt **đối tượng Thread**, **tên có thể đổi**, **ID gắn với một thread**, và **một task/Runnable** có thể chạy trên nhiều thread vào các thời điểm khác nhau.
- Giải thích vì sao gọi trực tiếp `run()` khác với `start()` và vì sao code chạy trong thread pool phải tự xem `currentThread()`.
- Dùng các thông tin này an toàn cho logging và troubleshooting, không nhầm thread ID với process ID, ID thread của hệ điều hành hoặc ID của yêu cầu nghiệp vụ.

**Phạm vi:** Thread API và concurrency trong Java nói chung. Bài không đề cập đến thread pool hay asynchronous execution riêng của Spring vì các nội dung Spring đã có chương riêng.

## 1. “Thread hiện tại” là gì?

Một chương trình Java có thể có nhiều thread thực thi cùng lúc hoặc xen kẽ. Mỗi thread là một luồng thực thi riêng; nhưng **một phương thức không tự sở hữu một thread cố định**. Phương thức đó chạy trên thread đã gọi nó.

Ví dụ:

~~~text
main thread
   |
   +-- main() ------> call helper() ------> helper() chạy trong main thread
   |
   +-- start(worker)
          |
          +-- worker thread ------> call helper() --> helper() chạy trong worker thread
~~~

Cùng một phương thức `helper()`, nhưng kết quả `Thread.currentThread()` tùy vào **ngữ cảnh chạy tại đúng thời điểm gọi**.

Chữ “current” được xác định tại nơi lệnh được *thực thi*:
- Trong `main()` khi chương trình chạy bằng Java launcher thông thường, đó thường là thread tên `main`.
- Trong `Runnable` do một `Thread` mới khởi chạy bằng `start()`, đó là thread mới.
- Trong một task được thực thi bởi `ExecutorService`, đó là worker của executor đang chạy task.
- Trong đoạn mã được gọi trực tiếp bằng một lời gọi phương thức thông thường, đó vẫn là thread của người gọi.

Điều này rất quan trọng khi phân tích bug concurrency: nhìn vào tên class/method hoặc đối tượng `Runnable` không đủ để biết nó đang chạy trên thread nào.

## 2. Ba API quan trọng

| API | Kiểu trả về | Đọc thông tin gì? | Ghi nhớ |
| --- | --- | --- | --- |
| `Thread.currentThread()` | `Thread` | Tham chiếu đến thread đang thực thi lệnh | Phương thức **static**, không cần có sẵn đối tượng Thread |
| `Thread.currentThread().getName()` | `String` | Tên của thread hiện tại | Tên **không bảo đảm duy nhất** và có thể thay đổi |
| `Thread.currentThread().getId()` | `long` | ID của thread hiện tại trong Java 17 | ID được cấp lúc tạo thread, ổn định trong đời sống thread; có thể được tái sử dụng sau khi thread kết thúc |
| `Thread.currentThread().threadId()` | `long` | ID của thread hiện tại từ Java 19+ | Ưu tiên dùng trên JDK 19+; không khả dụng khi biên dịch với Java 17 |

Cú pháp cơ bản:

~~~java
Thread current = Thread.currentThread();
String name = current.getName();
long id = current.getId(); // Java 17: hợp lệ
~~~

- `current` là **tham chiếu tới đối tượng Thread hiện tại**, không tạo thread mới.
- `getName()` là phương thức instance: đọc tên của chính đối tượng `current`.
- `getId()` là phương thức instance: đọc một giá trị `long`, không phải `String`.
- Có thể viết gộp thành `Thread.currentThread().getName()`, nhưng lưu đối tượng vào biến giúp tránh lặp lời gọi và tiện đọc nhiều thuộc tính.

Một phân biệt rất dễ nhầm:

~~~java
Thread worker = new Thread(() -> doSomething(), "worker-A");

String configuredName = worker.getName();          // Đọc đối tượng worker
String executingName = Thread.currentThread().getName(); // Đọc thread đang chạy lệnh này
~~~

Khi hai dòng trên thực thi ở `main()` trước khi gọi `worker.start()`, `configuredName` là `"worker-A"`, còn `executingName` thường là `"main"`. Việc *giữ tham chiếu tới* `worker` không khiến lệnh của người gọi chuyển sang chạy trong worker.

## 3. currentThread(): lấy đúng đối tượng đang thực thi

Khai báo API:

~~~java
public static native Thread currentThread();
~~~

Đây là chữ ký mang tính tham khảo ở mức Java API/JDK implementation; trong chương trình bạn chỉ cần **`Thread.currentThread()`**. Giá trị trả về mô tả thread đang thực thi. Kể cả khi gọi từ một phương thức `static`, một lambda, callback hoặc phương thức của object, thread hiện tại vẫn được xác định theo lời gọi lúc chạy.

### Ví dụ chạy được trên Java 17: main và worker

Tạo file **`ThreadIdentityDemo.java`**:

~~~java
public class ThreadIdentityDemo {

    private static void describe(String stage) {
        Thread current = Thread.currentThread();
        System.out.printf(
                "%s | name=%s | id=%d%n",
                stage, current.getName(), current.getId());
    }

    public static void main(String[] args) throws InterruptedException {
        Thread mainThread = Thread.currentThread();

        // Đặt tên rõ ràng để kết quả demo không phụ thuộc tên mặc định.
        String previousName = mainThread.getName();
        mainThread.setName("lesson-main");

        try {
            describe("main");

            Thread worker = new Thread(() -> {
                Thread executing = Thread.currentThread();

                describe("worker");
                System.out.println(
                        "worker-is-main=" + (executing == mainThread));
            }, "lesson-worker");

            // ID được cấp khi tạo Thread; chưa cần gọi start().
            System.out.println("before-start-id=" + worker.getId());

            worker.start();
            worker.join(); // Chờ worker kết thúc trước khi kiểm tra tiếp.

            System.out.println(
                    "ids-differ=" + (mainThread.getId() != worker.getId()));
        } finally {
            mainThread.setName(previousName);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThreadIdentityDemo.java
java ThreadIdentityDemo
~~~

Đầu ra có **đúng thứ tự dòng** như sau, nhưng giá trị ID thực tế phụ thuộc lần chạy/JVM:

~~~text
main | name=lesson-main | id=<MAIN_ID>
before-start-id=<WORKER_ID>
worker | name=lesson-worker | id=<WORKER_ID>
worker-is-main=false
ids-differ=true
~~~

Ở đây `<MAIN_ID>` và `<WORKER_ID>` là **ký hiệu thay cho số `long` được in thật**, không phải văn bản Java in ra nguyên xi. Hai nơi hiển thị `<WORKER_ID>` là **cùng một ID**: Java cấp ID khi đối tượng worker được tạo, và ID ấy không đổi trong suốt vòng đời thread. Tại thời điểm chương trình chạy, `mainThread` và `worker` là hai thread khác nhau đang tồn tại, nên có ID khác nhau.

Vì sao ví dụ đáng tin cậy?
1. `mainThread.setName("lesson-main")` cho tên đã biết trước, rồi khôi phục tên trong `finally`.
2. Worker được tạo với tên `"lesson-worker"`; trong lambda, `currentThread()` trỏ đến worker thực thi.
3. `worker.start()` khởi chạy worker. `join()` khiến thread main chờ worker hoàn thành, nhờ đó hai dòng cuối của worker xuất hiện trước `ids-differ=true`.
4. Không dự đoán hoặc hard-code số ID; ID được JVM cấp và có thể khác giữa các lần chạy.

**Lưu ý:** trong ví dụ này không có hai thread cùng lúc ghi vào một biến dữ liệu chung không được đồng bộ. Kết quả từ worker được ghi ra console, còn `join()` giúp main đợi kết thúc. Trong ứng dụng thật, nếu chia sẻ dữ liệu giữa các thread, chỉ biết tên/ID không thay thế các cơ chế đồng bộ và bảo đảm visibility.

## 4. Thread name: nhãn dễ đọc, không phải định danh duy nhất

### 4.1. Tên có thể đến từ đâu?

Với platform thread truyền thống, bạn có thể:
- Đặt tên lúc tạo: `new Thread(task, "worker-orders")`.
- Đổi tên về sau: `thread.setName("worker-payments")`.
- Đọc tên: `thread.getName()`.
- Để JVM tự tạo một tên khi không chỉ định; **không nên phụ thuộc vào mẫu tên sinh tự động trong logic chương trình**.

Ví dụ:

~~~java
Thread thread = new Thread(() -> {
    System.out.println(Thread.currentThread().getName());
}, "report-worker");
thread.start();
thread.join();
~~~

Khi đặt đoạn này trong phương thức có `throws InterruptedException` hoặc bắt exception tương ứng, kết quả là:

~~~text
report-worker
~~~

Tên là nhãn hỗ trợ quan sát; Java **không yêu cầu tên khác nhau**. Hai thread khác nhau hoàn toàn có thể cùng tên `"report-worker"`. Vì vậy không được dùng `getName()` như khóa unique trong `Map` lưu trạng thái thread, càng không dùng tên để chứng minh “hai công việc chạy chung một thread”.

### 4.2. Đổi tên không đổi thread hoặc ID

~~~java
Thread current = Thread.currentThread();
long idBefore = current.getId();
String oldName = current.getName();

try {
    current.setName("diagnostic-worker");
    System.out.println(current.getName());           // diagnostic-worker
    System.out.println(idBefore == current.getId()); // true
} finally {
    current.setName(oldName);
}
~~~

Đổi tên **không** tạo thread mới và **không** thay ID. Một task chạy trong pool có thể tạm đổi tên để dễ debug, nhưng việc đổi tên worker dùng chung dễ làm tên sai ngữ cảnh ở task kế tiếp nếu không khôi phục. Trong ứng dụng lớn, hãy đặt tên worker bằng `ThreadFactory` khi tạo pool; ID nghiệp vụ của task/request nên được ghi riêng trong log.

Tên một thread có thể thay đổi đồng thời với lúc thread khác đọc nó; đừng dựa vào tên làm cơ chế đồng bộ hoặc để ra quyết định correctness.

### 4.3. Phân biệt tên thread và tên công việc

Giả sử một worker tên `"pool-worker-2"` lần lượt xử lý request A, B và C:

~~~text
Thread: pool-worker-2 (ID cố định khi thread còn sống)
  |
  +-- request A
  +-- request B
  +-- request C
~~~

Tên/ID trong log có thể giống nhau qua cả ba request; điều đó **không** có nghĩa các request là một. Ngược lại, một thao tác nghiệp vụ có thể chuyển qua nhiều thread ở các giai đoạn khác nhau. Muốn theo dấu thao tác, hãy thêm **requestId/taskId/correlationId** độc lập với tên/ID thread.

## 5. Thread ID: giá trị nào, độ duy nhất đến đâu?

Trong Java 17, phương thức chính là:

~~~java
long id = Thread.currentThread().getId();
~~~

Theo đặc tả Java 17, ID:
- Là số nguyên dương kiểu `long` do JVM cấp khi một `Thread` được tạo.
- **Không đổi trong đời sống của chính Thread đó.**
- **Duy nhất giữa các thread trong suốt thời gian chúng còn sống đồng thời** theo bảo đảm ID thread.
- Có thể được **tái sử dụng** sau khi một thread kết thúc.

Vì có thể tái sử dụng, **không dùng riêng ID làm khóa lâu dài** cho bản ghi giám sát qua nhiều lần chạy chương trình, hay làm ID nghiệp vụ trong database.

Cần phân biệt rõ:

| Giá trị | Ví dụ cách lấy | Ý nghĩa |
| --- | --- | --- |
| Java thread ID | `Thread.currentThread().getId()` / `threadId()` | Định danh thread trong JVM |
| Java thread name | `Thread.currentThread().getName()` | Nhãn có thể sửa; không unique |
| Process ID (PID) | `ProcessHandle.current().pid()` | Định danh **tiến trình** JVM ở cấp hệ điều hành |
| Native/OS thread ID | API/công cụ hệ điều hành hoặc profiler | Định danh thread phía OS, **không bảo đảm bằng** Java thread ID |
| Request/task ID | Định danh do ứng dụng cấp | Định danh *công việc nghiệp vụ*, độc lập thread |

Khi đọc thread dump hay JFR, các công cụ có thể dùng nhiều loại ID hoặc cách biểu diễn khác nhau. Hãy đọc nhãn cột thay vì mặc định tất cả ID đều là kết quả `Thread.getId()`. ID là công cụ nhận diện thời điểm quan sát, **không tiết lộ** thread đang chờ, đang chạy, daemon hay mức ưu tiên; muốn kiểm tra thuộc tính đó phải dùng API và phép quan sát tương ứng.

## 6. Quan trọng: gọi run() không đồng nghĩa tạo thread mới

`worker.run()` gọi phương thức ngay trên caller, nên `Thread.currentThread()` trong task vẫn là **thread đang gọi**; `worker.getName()` chỉ là tên của đối tượng được tạo. Chỉ `worker.start()` mới khởi động thread mới. Đoạn sau minh họa bên trong một phương thức đã khai báo `throws InterruptedException`:

~~~java
Thread worker = new Thread(
        () -> System.out.println(Thread.currentThread().getName()),
        "new-worker");
worker.start();
worker.join();
~~~

Kết quả là `new-worker`; nếu gọi `run()` trực tiếp từ main thay vì `start()`, output sẽ là `main`. Vì bài này tập trung vào **nhận diện thread**, phần giải thích sâu về trạng thái, happens-before và exception được trình bày tại bài **Phân biệt gọi start() và run()**.

## 7. Đọc tên và ID khi chạy task qua ExecutorService

Trong chương trình thực tế, một `Runnable` hay `Callable` có thể được gửi đến pool và được worker thực thi sau đó. **Task không phải thread**. Vì vậy, giá trị tên/ID mà bạn đọc từ thread gọi `submit()` không chỉ ra worker nào sẽ chạy task.

Ví dụ Java 17 với pool hai worker, được đặt tên khi tạo bằng `ThreadFactory`:

Tạo file **`PoolIdentityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolIdentityDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger sequence = new AtomicInteger();

        ExecutorService pool = Executors.newFixedThreadPool(
                2,
                runnable -> new Thread(
                        runnable,
                        "lesson-pool-" + sequence.incrementAndGet())
        );

        try {
            List<Future<String>> results = new ArrayList<>();

            for (int taskNo = 1; taskNo <= 4; taskNo++) {
                final int taskId = taskNo;
                results.add(pool.submit(() -> {
                    Thread worker = Thread.currentThread();

                    return "task=" + taskId
                            + ", worker=" + worker.getName()
                            + ", javaThreadId=" + worker.getId();
                }));
            }

            // Đọc kết quả theo thứ tự submit, dù worker xử lý xen kẽ.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PoolIdentityDemo.java
java PoolIdentityDemo
~~~

Chương trình in bốn dòng tương ứng `task=1`, `task=2`, `task=3`, `task=4` theo **thứ tự lấy `Future`**, ví dụ một lượt chạy có thể trông như sau:

~~~text
task=1, worker=lesson-pool-1, javaThreadId=21
task=2, worker=lesson-pool-2, javaThreadId=22
task=3, worker=lesson-pool-1, javaThreadId=21
task=4, worker=lesson-pool-2, javaThreadId=22
~~~

**Đây là đầu ra minh họa, không phải stdout cố định.** JVM có thể chọn worker khác cho từng task và cấp ID khác `21`, `22`; thời điểm worker được tạo/lịch thực thi không được cố định. Ngay cả khi chỉ có một worker chạy đủ nhanh, kết quả từ cả bốn task cũng có thể mang cùng tên/ID worker.

Những điều chắc chắn trong ví dụ:
- Có **bốn kết quả** và thứ tự hiển thị theo `Future` trong list, nhờ vòng lặp đọc `result.get()`.
- Mỗi kết quả được tạo **bên trong task**, nên `Thread.currentThread()` trả về worker thật đang thực thi task đó.
- Với hai worker trong pool, tối đa hai worker chạy task đồng thời trong tình huống này; không bảo đảm chính xác hai worker sẽ được tạo.
- `ThreadFactory` đặt tên giúp log dễ đọc; `AtomicInteger` cấp suffix tăng dần một cách an toàn khi tạo worker. Số suffix không phải thread ID JVM.
- Pool được shutdown; `Future.get()` có thể ném exception nếu task thất bại. Ví dụ cố ý chờ hoàn tất để thí nghiệm dễ kiểm tra.

**Quy tắc:** muốn biết *task đang chạy ở đâu*, hãy gọi `Thread.currentThread()` **bên trong task**, không phải tại nơi tạo `Runnable` hoặc gửi `submit()`.

## 8. Khác biệt phiên bản Java: getId(), threadId() và virtual threads

Bài mẫu dùng Java 17 để biên dịch dễ dàng. Trên các JDK hiện đại, cần để ý:

| Phiên bản | API ID có thể dùng | Diễn giải |
| --- | --- | --- |
| Java 17 | `getId()` | Hợp lệ, chưa bị đánh dấu deprecated ở Java 17 |
| Java 19+ | `threadId()` (khuyến nghị), `getId()` (deprecated từ 19) | `threadId()` là `final` và phản ánh ID thread; `getId()` không phải `final`, có thể bị subclass override |
| Java 21+ | `threadId()` áp dụng cho cả platform và virtual thread | `currentThread()` trong virtual thread trả về **đối tượng virtual thread đang chạy**, không phải carrier platform thread |

Trong code chỉ nhắm Java 21+, cách đọc ID rõ ràng là:

~~~java
Thread current = Thread.currentThread();
long id = current.threadId(); // Java 19+
System.out.println(current.getName() + " #" + id);
~~~

**Không dán đoạn `threadId()` này vào chương trình biên dịch bằng `--release 17`:** phương thức chưa tồn tại trong Java 17.

Với virtual threads (ổn định từ Java 21), tên mặc định có thể là chuỗi rỗng `""` nếu bạn không đặt; `getName()` không tự nhiên cho nhãn kiểu `"Thread-..."`. Có thể đặt tên bằng builder dành cho virtual thread. Dù virtual thread được JVM lên lịch qua carrier platform threads, `Thread.currentThread()` trong mã virtual thread vẫn là virtual thread. Java thread ID là identity Java; đừng tự suy ra carrier hoặc OS thread ID từ nó.

Nếu phải hỗ trợ cả Java 17 lẫn Java 21 bằng **cùng một binary biên dịch cho 17**, dùng `getId()` với hiểu biết về deprecation ở các JDK mới; không dùng phương thức `threadId()` chưa có trong classpath API Java 17.

## 9. Cách áp dụng trong log và điều tra vấn đề

Một dòng log tối thiểu hữu ích có thể chứa:

~~~text
2026-10-28T10:15:30Z level=INFO threadName=lesson-pool-1 javaThreadId=21 taskId=job-42 action=parse-start
~~~

Các giá trị trên **chỉ là ví dụ định dạng**, không phải log được tạo từ chương trình phía trên. Khi quan sát nhiều thread:

1. **Thread name** cho biết nhãn dễ đọc, thường hữu ích để tìm nhóm worker.
2. **Java thread ID** giúp phân biệt các thread trùng tên khi chúng còn sống, nhưng không nên lưu làm identity xuyên nhiều tiến trình hoặc lâu dài sau khi thread đã kết thúc.
3. **Task ID** gắn các dòng log của cùng một công việc, kể cả công việc chuyển từ worker này sang worker khác.
4. **Timestamp và sự kiện** cho biết thứ tự quan sát; ID không cho biết thời gian tạo hoặc thứ tự hoàn tất.
5. **Exception/stack trace và trạng thái thread** mới là bằng chứng để điều tra block, deadlock hoặc lỗi; tên và ID một mình không xác định được nguyên nhân.

Trong code đa luồng, `System.out.println` từ các thread có thể xuất hiện theo thứ tự khác nhau; không giả định thứ tự từ tốc độ CPU hay số ID. Ví dụ trên đã dùng `join()` hoặc vòng lặp `Future.get()` để kiểm soát điểm chờ và thứ tự **hiển thị kết quả**, không giả định thứ tự **thực thi** của worker.

### Khi đặt tên thread

Một tên hữu ích nên mô tả vai trò ổn định của worker (ví dụ `"file-reader-1"`, `"metrics-poller-2"`), có suffix nếu cần đọc log. Tránh nhét mật khẩu, token hoặc dữ liệu cá nhân vào tên thread vì tên có thể xuất hiện trong log, thread dump và giao diện chẩn đoán. Đối với ID yêu cầu có thể thay đổi theo task, dùng field log riêng.

## 10. Các lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `Thread.currentThread()` tạo thread mới | Đây là static accessor cho thread **đang chạy** | Muốn chạy thread mới phải tạo và `start()` (hoặc dùng executor) |
| `worker.getName()` luôn cho biết thread đang chạy đoạn mã | Nó chỉ đọc đối tượng `worker` | Gọi `Thread.currentThread().getName()` tại chỗ code thực thi |
| Gọi `worker.run()` là chạy song song | `run()` trực tiếp là lời gọi phương thức bình thường | `start()` mới yêu cầu một thread thực thi riêng |
| Tên thread là duy nhất | Java cho phép tên trùng và đổi tên | Dùng đối tượng hoặc ID khi nhận diện thread đang sống; dùng ID nghiệp vụ cho task |
| Java thread ID = OS thread ID = PID | Ba loại định danh khác nhau | Gắn nhãn rõ `javaThreadId`, `pid`, `nativeThreadId` |
| Thread ID tăng đều theo thứ tự xử lý | ID được cấp khi tạo, lịch thực thi độc lập | Không suy luận thứ tự chạy/hoàn tất từ ID |
| Tăng thread ID nghĩa là thread chạy nhanh hơn | ID không phải phép đo hiệu năng | Muốn đo latency/throughput phải có đồng hồ và metric riêng |
| Task chạy ở một thread cố định | Executor có thể dùng nhiều worker qua các lần submit | Đọc identity ngay trong task và gắn correlation ID riêng |
| Gọi `threadId()` khi dùng Java 17 | API mới có từ Java 19 | Java 17 dùng `getId()` |
| Dùng tên/ID để điều khiển synchronization | Metadata không thay thế quan hệ happens-before | Dùng `join()`, lock, atomic/concurrent utilities đúng mục đích |

## 11. Bài tập tự kiểm tra

**Bài 1 — Nhận diện caller:** Tạo một `Runnable` in `Thread.currentThread().getName()`, gọi `run()` trực tiếp rồi truyền cùng `Runnable` vào `new Thread(r, "demo-worker")` và `start()`. Vì sao hai lần có thể in hai tên khác nhau? (`run()` trực tiếp chạy trên caller; `start()` tạo đường thực thi của worker.)

**Bài 2 — Tên trùng nhau:** Tạo hai đối tượng `Thread` đều có tên `"reader"`; mỗi thread in tên và ID của chính nó. Kết luận được gì? (Tên có thể trùng, ID khác trong thời gian cùng sống; muốn đảm bảo hai thread đang cùng sống trong thí nghiệm, dùng đồng bộ thích hợp.)

**Bài 3 — ID trước và sau start:** Đọc `getId()` sau khi tạo nhưng trước `start()`, rồi đọc tiếp sau `join()` trên chính đối tượng. Giá trị có thay đổi không? (Không; ID được cấp lúc tạo và không đổi trong vòng đời đối tượng.)

**Bài 4 — Task khác worker:** Submit bốn task vào pool hai worker, log `taskId`, `getName()`, `getId()` **bên trong từng task**. Nếu hai task in cùng Java thread ID, có thể kết luận chúng là cùng một task không? (Không; worker có thể được tái sử dụng để chạy nhiều task.)

**Bài 5 — Tương thích JDK:** Code dùng `Thread.currentThread().threadId()` chạy khi build với Java 21 nhưng lỗi biên dịch khi build với `javac --release 17`. Hãy giải thích. (Phương thức `threadId()` xuất hiện từ Java 19; Java 17 dùng `getId()`.)

## Ghi nhớ

- `Thread.currentThread()` xác định **thread đang thực thi đoạn mã tại thời điểm gọi**.
- `getName()` cung cấp **nhãn dễ đọc**, có thể trùng hoặc đổi tên.
- `getId()` trên Java 17 / `threadId()` trên Java 19+ cung cấp **ID do JVM cấp**, ổn định trong đời sống của thread và không phải ID công việc hay OS/PID.
- Trong executor, cần lấy current thread **bên trong task**, đồng thời dùng task/request ID riêng để theo dõi nghiệp vụ.
- Các giá trị identity hỗ trợ debug; **không chứng minh thứ tự chạy, khả năng đồng bộ hoặc hiệu năng**.

### Tài liệu API

- [Java SE 17 — java.lang.Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `currentThread()`, `getName()`, `getId()`, `start()`, `join()`.
- [Java SE 21 — java.lang.Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `threadId()`, `getId()` deprecation, virtual thread behavior.
