# Khởi chạy một lần và lỗi khởi chạy lại thread trong Java

## 1. Quy tắc cốt lõi: một đối tượng Thread chỉ được start một lần

Trong Java, một đối tượng `java.lang.Thread` biểu diễn **một lần thực thi của một luồng**. Sau khi tạo:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
Thread worker = new Thread(() -> doWork(), "worker-1");
worker.start();
~~~

lời gọi `start()` yêu cầu JVM bắt đầu một luồng thực thi mới. Đến lượt được lập lịch, luồng đó chạy `run()`; khi `run()` kết thúc bình thường hoặc thoát vì một lỗi không được bắt, luồng đi tới trạng thái kết thúc.

**Cùng đối tượng `Thread` không thể được `start()` lần thứ hai**, kể cả khi công việc lần đầu đã hoàn tất, luồng đã được `join()`, hoặc người viết mã cố gắng “reset” trạng thái. Java ném `IllegalThreadStateException` khi cố khởi chạy lại đối tượng đã start. Muốn thực hiện công việc lần nữa, hãy **tạo một đối tượng `Thread` mới** hoặc gửi task mới cho một `ExecutorService` phù hợp.

Ba đối tượng khác nhau cần phân biệt:

- **Task**: công việc được mô tả bởi `Runnable` hoặc `Callable`; có thể được gọi hoặc gửi thực hiện nhiều lần nếu logic cho phép.
- **Thread object**: một phiên thực thi có vòng đời riêng, từ chưa chạy đến đã kết thúc; chỉ `start()` một lần.
- **Worker trong thread pool**: thread mà executor quản lý, có thể thực thi **nhiều task lần lượt** bằng vòng lặp nội bộ; điều này không đồng nghĩa với việc gọi `start()` lặp lại trên worker đó.

Quy tắc một lần áp dụng cho **đối tượng luồng**, không cấm tái sử dụng logic của task.

## 2. Đặt trong vòng đời Thread

`Thread.State` trong Java phân biệt sáu trạng thái quan sát được:

| Trạng thái | Ý nghĩa | Có thể gọi `start()`? |
| --- | --- | --- |
| `NEW` | Đối tượng thread đã được tạo nhưng chưa khởi chạy | Có, **một lần**, nếu chưa có lời gọi `start()` cạnh tranh |
| `RUNNABLE` | Luồng đang chạy hoặc sẵn sàng được CPU lập lịch | Không |
| `BLOCKED` | Luồng đợi để lấy monitor lock | Không |
| `WAITING` | Luồng chờ vô thời hạn một điều kiện/sự kiện phù hợp | Không |
| `TIMED_WAITING` | Luồng chờ với thời hạn, ví dụ `sleep` hoặc `join` có timeout | Không |
| `TERMINATED` | Luồng đã hoàn thành thực thi | Không |

Một đường đi đơn giản:

~~~text
new Thread(...)
      |
      v
     NEW
      |
    start()  [duy nhất một lần]
      |
      v
  RUNNABLE <----> BLOCKED / WAITING / TIMED_WAITING
      |
   run() kết thúc hoặc lỗi không được bắt
      |
      v
  TERMINATED
      |
  start() lần nữa -> IllegalThreadStateException
~~~

Bảng chỉ mô tả khả năng quan sát, không phải sơ đồ bắt buộc mỗi thread phải đi qua tất cả các trạng thái. Ví dụ thread có thể đi từ `RUNNABLE` tới `TERMINATED` mà không từng `WAITING`.

**Điểm rất dễ nhầm:** `TERMINATED` không tương đương `NEW`. Việc kết thúc chỉ nói rằng luồng thực thi cũ đã dừng; nó không đưa đối tượng trở lại trạng thái chưa được start. API không cung cấp thao tác hợp lệ nào để “reset” một `Thread` đã kết thúc.

Giá trị `getState()` là **ảnh chụp tại một thời điểm** và có thể thay đổi ngay sau khi đọc. Điều kiện `thread.getState() == Thread.State.NEW` không phải cơ chế phối hợp an toàn để cho nhiều thread cạnh tranh khởi chạy cùng một đối tượng.

## 3. Ví dụ 1 — start, join rồi start lại (Java 17+)

Tạo tệp `StartOnceDemo.java`:

~~~java
public class StartOnceDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = new Thread(() -> {
            System.out.println(
                "Running on " + Thread.currentThread().getName()
            );
        }, "report-worker-1");

        System.out.println("Before start: " + worker.getState());

        worker.start();
        worker.join();

        System.out.println("After join: " + worker.getState());

        try {
            worker.start(); // Cùng đối tượng: không được phép.
        } catch (IllegalThreadStateException ex) {
            System.out.println(
                "Second start failed: " + ex.getClass().getSimpleName()
            );
        }

        System.out.println("Finished");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac StartOnceDemo.java
java StartOnceDemo
~~~

Đầu ra chính xác:

~~~text
Before start: NEW
Running on report-worker-1
After join: TERMINATED
Second start failed: IllegalThreadStateException
Finished
~~~

Phân tích từng bước:

1. `new Thread(...)` chỉ tạo đối tượng, nên `getState()` trước khi gọi `start()` là `NEW`.
2. `start()` khởi tạo quá trình thực thi và trả về cho thread gọi; JVM quyết định thời điểm worker thực sự được chạy. Vì vậy không nên suy ra worker đã hoàn tất chỉ từ việc `start()` trả về.
3. `join()` trên `worker` khiến thread `main` chờ tới khi worker kết thúc; sau khi `join()` trả về bình thường, thread đã `TERMINATED`.
4. Gọi `worker.start()` lần nữa bị từ chối với `IllegalThreadStateException` dù `run()` trước đó không gặp lỗi.
5. `catch` minh họa cách phát hiện thao tác sai. Trong code thực tế, thiết kế nên **tránh gọi `start()` lần hai** thay vì thường xuyên dựa vào exception để điều khiển luồng.

`IllegalThreadStateException` là unchecked exception, nên compiler không bắt buộc khai báo `throws` cho nó. Phần `throws InterruptedException` trên `main` là vì `join()` có thể bị interrupt, **không phải** do `start()` lần hai.

### Vì sao `join()` không giúp khởi chạy lại?

`join()` chỉ chờ một thread kết thúc, không tạo thêm thread và không thay đổi lịch sử đã start của đối tượng. Gọi `join()` lần nữa trên một thread đã kết thúc chỉ trở về; điều này vẫn không cấp quyền `start()` lần nữa.

Ngược lại, gọi `join()` trên một thread **chưa từng start** có thể trở về ngay vì thread chưa sống. Vì thế không dùng `join()` như tín hiệu xác nhận công việc đã từng chạy thành công; phải biết rõ vòng đời và kênh kết quả của task.

## 4. `start()` và `run()` là hai thao tác khác nhau

Tên `run()` dễ khiến người học nghĩ có thể “chạy lại thread” bằng cách gọi trực tiếp. Thực tế:

- `thread.start()` yêu cầu tạo luồng thực thi độc lập; JVM sẽ gọi `run()` trong luồng đó. Chỉ được start một lần.
- `thread.run()` là **lời gọi phương thức Java bình thường**, chạy trên **thread đang gọi**; nó không tạo thread mới và tự nó không chuyển đối tượng từ `NEW` sang `RUNNABLE`.
- Gọi trực tiếp `run()` nhiều lần có thể lặp lại công việc ở thread gọi, nhưng **không phải** chạy lại phiên luồng đã start.

### Ví dụ 2 — so sánh bằng đúng thread thực thi (Java 17+)

Tạo tệp `RunVsStartDemo.java`:

~~~java
public class RunVsStartDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Thread caller = Thread.currentThread();

        Thread worker = new Thread(() -> {
            System.out.println(
                "Runs on caller: "
                    + (Thread.currentThread() == caller)
            );
        }, "actual-worker");

        worker.run();
        System.out.println(
            "State after direct run: " + worker.getState()
        );

        worker.start();
        worker.join();

        System.out.println(
            "State after start and join: " + worker.getState()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RunVsStartDemo.java
java RunVsStartDemo
~~~

Đầu ra chính xác:

~~~text
Runs on caller: true
State after direct run: NEW
Runs on caller: false
State after start and join: TERMINATED
~~~

Lần đầu, `worker.run()` được gọi như một phương thức và chạy trên thread `main`; sau lời gọi, đối tượng `worker` vẫn `NEW`. Lần sau, `worker.start()` khởi chạy thread thực sự mang tên `actual-worker`, nên phép so sánh với `caller` trả về `false`. Hai lần in được sắp theo thứ tự ổn định nhờ lời gọi trực tiếp đồng bộ và `join()`.

Một ví dụ `Runnable` đơn giản có thể thực thi nhiều lần nếu nội dung tác vụ phù hợp, nhưng không có nghĩa mỗi lần thực thi là một thread mới. Với tác vụ có side effect (ghi file, trừ số dư, gửi request), lặp lại `run()` còn có thể gây lặp xử lý nghiệp vụ.

## 5. Cách đúng để chạy cùng công việc lần nữa

### 5.1. Tạo một Thread mới cho mỗi lần thực thi

Bạn có thể tái sử dụng **đối tượng `Runnable`** khi nó không có trạng thái gây lỗi trong các lần chạy:

~~~java
// Minh họa ý tưởng; Runnable chỉ đọc, không sửa trạng thái dùng chung.
Runnable task = () -> System.out.println("A unit of work");

Thread first = new Thread(task, "job-1");
Thread second = new Thread(task, "job-2");

first.start();
second.start();
~~~

Đây là hai đối tượng `Thread` khác nhau. Mỗi đối tượng có quyền `start()` đúng một lần. Nếu muốn chạy **tuần tự** và tránh sự phụ thuộc vào lịch chạy, chờ `first.join()` trước khi `second.start()`.

### Ví dụ 3 — tạo thread mới ở mỗi lượt (Java 17+)

Tạo tệp `NewThreadPerRunDemo.java`:

~~~java
public class NewThreadPerRunDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Runnable task = () -> {
            System.out.println(
                "Executed by " + Thread.currentThread().getName()
            );
        };

        for (int i = 1; i <= 3; i++) {
            Thread worker = new Thread(task, "task-worker-" + i);
            worker.start();
            worker.join();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NewThreadPerRunDemo.java
java NewThreadPerRunDemo
~~~

Đầu ra chính xác:

~~~text
Executed by task-worker-1
Executed by task-worker-2
Executed by task-worker-3
~~~

Vòng lặp tạo **ba đối tượng thread mới**, mỗi đối tượng start một lần. `join()` trong vòng lặp buộc từng lượt hoàn tất rồi mới tới lượt kế tiếp, giúp thứ tự output xác định. Khi muốn concurrency thật sự giữa ba task, có thể khởi chạy cả ba trước rồi mới `join()` cả ba, nhưng thứ tự in lúc đó không cố định.

**Chi phí:** Tạo platform thread mới cho lượng lớn công việc ngắn có thể tốn thời gian, bộ nhớ ngăn xếp và chi phí lập lịch. Đừng dùng “tạo thread mới mỗi lần” làm chiến lược mặc định cho số lượng task rất lớn.

### 5.2. Dùng ExecutorService cho chuỗi task dài

`ExecutorService` nhận nhiều task và tự quản lý worker thread. Người gọi gửi task bằng `execute(...)` hoặc `submit(...)`; **không** tự gọi `start()` trên worker do executor nắm giữ.

Tạo tệp `RepeatedTasksDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RepeatedTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
            Executors.newSingleThreadExecutor(
                task -> new Thread(task, "queue-worker-1")
            );

        try {
            for (int i = 1; i <= 3; i++) {
                int taskId = i;

                Future<String> result = executor.submit(() ->
                    "Task " + taskId + " on "
                        + Thread.currentThread().getName()
                );

                System.out.println(result.get());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RepeatedTasksDemo.java
java RepeatedTasksDemo
~~~

Đầu ra chính xác khi task hoàn tất bình thường:

~~~text
Task 1 on queue-worker-1
Task 2 on queue-worker-1
Task 3 on queue-worker-1
~~~

Với `newSingleThreadExecutor`, các task thực thi tuần tự trên một worker nếu worker còn hoạt động bình thường. Worker có thể nhận **nhiều task qua vòng lặp của executor**, nhưng bản thân worker vẫn chỉ được `start()` một lần khi executor tạo ra nó.

- `submit(...)` trả về `Future` để lấy kết quả hoặc exception của task. `get()` chờ hoàn tất; code mẫu dùng `get()` để có thứ tự output xác định.
- Worker có thể được thay thế khi chết bất thường, vì vậy **không nên lấy một tên thread hoặc identity worker làm bảo đảm bất biến cho toàn bộ vòng đời ứng dụng**.
- `shutdown()` ngừng nhận task mới nhưng cho task đã nộp tiếp tục; `awaitTermination(...)` chờ có giới hạn; `shutdownNow()` chỉ yêu cầu ngắt các task chưa kết thúc.
- Sau khi executor bị shutdown, muốn gửi công việc mới cần một executor khác; gửi task vào executor đã shutdown thường bị `RejectedExecutionException`. Đây là **quy tắc vòng đời executor**, khác với `IllegalThreadStateException` của việc gọi `Thread.start()` lần hai.

### 5.3. Chọn cách nào?

| Nhu cầu | Cách chọn | Ghi chú |
| --- | --- | --- |
| Một thao tác đơn lẻ, muốn thấy cơ chế Thread | `new Thread(task)` rồi `start()` | Đơn giản để học, phải quản lý `join`/lỗi |
| Chạy lại một logic cụ thể | Tạo **Thread mới** dùng cùng `Runnable` an toàn | Không reuse đối tượng Thread cũ |
| Nhiều task liên tục, cần kiểm soát số worker | `ExecutorService` | Giới hạn concurrency, queue và shutdown |
| Một task thất bại nhưng cần biết nguyên nhân | `Future.get()`, quản lý lỗi task | Tránh suy ra thành công chỉ từ `join()` |
| Java 21+, nhiều tác vụ chờ I/O độc lập | Cân nhắc virtual thread per task | Vẫn chỉ start từng virtual thread một lần |

## 6. Nếu cố gọi start hai lần từ nhiều thread thì sao?

Một lỗi thực tế là có hai nơi cùng muốn khởi chạy một worker:

~~~java
// Minh họa không an toàn: hai caller cùng thao tác trên một đối tượng.
if (worker.getState() == Thread.State.NEW) {
    worker.start();
}
~~~

Ngay cả khi cả hai caller đều thấy trạng thái `NEW`, điều kiện `if` và lời gọi `start()` không tạo thành một phép kiểm tra–hành động nguyên tử. Caller thứ nhất có thể khởi chạy; caller thứ hai tiếp tục tới `start()` và nhận `IllegalThreadStateException`.

Các kiểm tra `!worker.isAlive()` cũng không xác định “có thể start” vì `isAlive() == false` có thể xảy ra khi thread **chưa từng start** hoặc **đã kết thúc**. Tương tự, `getState() == TERMINATED` chứng minh đã kết thúc nhưng **không** có nghĩa sẵn sàng chạy lại.

Thiết kế an toàn hơn:

1. Xác định thành phần **sở hữu** quyền tạo/khởi chạy thread (ví dụ đối tượng quản lý worker).
2. Đảm bảo quy trình khởi chạy được gọi tại một điểm được kiểm soát; không để nhiều caller tự kiểm tra trạng thái rồi cùng `start()`.
3. Nếu có yêu cầu “start nếu chưa start”, dùng đồng bộ hóa/`AtomicBoolean` để điều phối **quyền gọi start một lần**; giải pháp này không làm đối tượng thread trở nên có thể restart.
4. Nếu nghiệp vụ đòi hỏi “bấm Start nhiều lần sau mỗi lần Stop”, mỗi chu kỳ phải tạo **đối tượng thread mới**, khởi tạo lại trạng thái của job đúng cách và quản lý việc chờ chu kỳ cũ kết thúc.

Ví dụ mô hình vòng đời của một worker có thể nhận nhiều phiên chạy: một controller giữ trạng thái “đang chạy/đã dừng”, mỗi lần khởi động **tạo một Thread mới**, và khi dừng thì gửi tín hiệu hợp tác (như interrupt hoặc cờ dừng có đồng bộ) rồi đợi hoàn tất. Không dùng `Thread.stop()`: API này đã bị deprecated và vốn không an toàn vì có thể dừng thread tại điểm đang giữ bất biến/khóa.

## 7. Vì sao thread kết thúc không thể hồi sinh?

Một đối tượng `Thread` đã start gắn với một phiên thực thi, bao gồm ngăn xếp lời gọi, trạng thái tiến triển, thông tin lập lịch và quá trình hoàn tất. Java không định nghĩa một cách hợp lệ để tái tạo lại phiên thực thi ấy bằng cách gọi `start()` lần nữa.

Đừng nhầm việc **giữ lại đối tượng `Thread` trong một biến** với việc giữ lại năng lực thực thi của thread:

~~~java
// Minh họa: reference vẫn tồn tại nhưng phiên thực thi đã kết thúc.
Thread t = new Thread(() -> System.out.println("done"));
t.start();
t.join();

// t vẫn được tham chiếu, nhưng không thể t.start() lần nữa.
~~~

Tham chiếu `t` vẫn có ích cho việc quan sát tên, ID, trạng thái cuối, hoặc xác định thread đã hoàn tất. Nó không giữ một “nút chạy lại”. Mỗi lần chạy lại logic nhiệm vụ là một phiên thực thi mới.

Đặc biệt, nếu `run()` kết thúc do exception không được bắt, thread vẫn chấm dứt và vẫn không thể start lại. Cài `UncaughtExceptionHandler` chỉ giúp nhận biết/báo lỗi; handler **không** chuyển thread về `NEW`, không tự động sửa lỗi, không khởi chạy lại cùng đối tượng.

## 8. Thứ tự bộ nhớ, trạng thái và quan sát

Quy tắc một lần của `start()` còn liên hệ tới quan hệ **happens-before** trong Java Memory Model:

- Những hành động của một thread thực hiện **trước lời gọi `otherThread.start()`** happens-before các hành động do thread mới đó thực hiện.
- Khi một thread khác chờ `join()` hoàn tất thành công, những hành động của thread đã kết thúc happens-before các hành động tiếp theo của thread đã join. Nhờ vậy, sau khi `join()` bình thường, các cập nhật phù hợp từ worker đã được công bố để thread chờ quan sát.

Những bảo đảm đó giúp phối hợp giữa các phiên thực thi, nhưng **không** làm cho tất cả trạng thái chia sẻ trở thành thread-safe trong lúc nhiều thread đang chạy. Nếu hai worker cùng cập nhật một biến mutable, vẫn cần thiết kế đồng bộ phù hợp (khóa, atomic, bất biến, phân quyền sở hữu dữ liệu).

`getState()`, `isAlive()` và tên thread hữu ích cho debugging và kiểm tra vòng đời, nhưng không nên được dùng làm giao thức đồng bộ duy nhất. Trạng thái có thể thay đổi ngay sau khi quan sát. Với sản phẩm thực tế, một cấu trúc quản lý task/worker thường cần giao thức khởi động, hoàn thành, dừng và xử lý lỗi rõ ràng.

## 9. Phân biệt những lỗi liên quan

| Hành động | Điều xảy ra | Cách xử lý đúng |
| --- | --- | --- |
| Gọi `start()` lần đầu trên Thread `NEW` | Khởi động phiên thực thi | Chờ hoặc phối hợp với task khi cần |
| Gọi `start()` lần hai trên cùng Thread | `IllegalThreadStateException` | Tạo Thread mới hoặc dùng executor |
| Gọi `run()` trực tiếp trên đối tượng Thread | Chạy đồng bộ trong **caller** | Dùng `start()` nếu cần luồng mới |
| Gọi `start()` trên Thread đã `TERMINATED` | `IllegalThreadStateException` | Không reset thread; tạo phiên mới |
| Gọi `join()` nhiều lần sau khi kết thúc | Trả về, không khởi chạy lại | Dùng `join()` để chờ, không để restart |
| Gửi task vào executor đã shutdown | Thường `RejectedExecutionException` | Tạo hoặc giữ executor đang hoạt động |
| Gọi `Thread.start()` từ hai caller cạnh tranh | Chỉ một lần start hợp lệ; caller khác có thể nhận lỗi | Điều phối ownership và thao tác khởi động |
| Worker bị interrupt | Tín hiệu phối hợp; thread có thể tiếp tục hoặc kết thúc tùy code | Xử lý interrupt đúng hợp đồng, không xem là reset |
| Worker chết vì uncaught exception | Thread chấm dứt, không thể restart cùng đối tượng | Ghi lỗi, quyết định retry bằng task/thread mới |

### Lỗi thường gặp khi chữa `IllegalThreadStateException`

- **Đổi `start()` thành `run()`** để hết lỗi: code có thể chạy được nhưng sẽ chạy trong thread gọi, dễ làm mất tính đồng thời hoặc chặn đường xử lý chính.
- **Gọi `join()` trước lần start thứ hai**: `join()` không thay đổi quy tắc một lần.
- **Chỉ kiểm tra `isAlive()` trước khi start**: `false` không phân biệt `NEW` với `TERMINATED`.
- **Giữ một Thread trong field và gọi start mỗi khi nhận request**: mỗi request sau request đầu có nguy cơ ném lỗi; nên giữ task factory hoặc executor.
- **Tự retry `start()` trên cùng đối tượng trong vòng lặp catch**: ngoại lệ sẽ lặp lại vì đối tượng đã được start trước đó.
- **Quên kết thúc executor**: chuyển sang executor mà không có shutdown, giới hạn tài nguyên hay xử lý lỗi chỉ thay thế một lỗi vòng đời bằng vấn đề quản lý worker khác.

## 10. Java 21+ và virtual threads

Trong Java 21, virtual threads được chuẩn hóa thành tính năng chính thức. Dù rẻ hơn platform threads trong nhiều trường hợp chờ I/O, một virtual thread **vẫn là một `Thread` và vẫn chỉ start một lần**.

Ví dụ API Java 21+ (minh họa, không biên dịch trên JDK 17):

~~~java
Thread virtual = Thread.ofVirtual()
    .name("fetch-1")
    .unstarted(() -> System.out.println("fetching"));

virtual.start();
virtual.join();

// virtual.start(); // Sai: IllegalThreadStateException.
~~~

Nếu muốn thực hiện nhiều task độc lập, thông thường nên tạo virtual thread mới cho mỗi task, hoặc dùng cơ chế `Executors.newVirtualThreadPerTaskExecutor()` để giao việc; không tái sử dụng đối tượng virtual thread đã kết thúc.

Quy tắc này hoàn toàn thuộc Thread API của Java; không cần một framework nào để áp dụng.

## 11. Bài tập tự kiểm tra

**Bài 1 — nhận diện lỗi:**

~~~java
// Minh họa, không phải chương trình độc lập.
Thread t = new Thread(() -> System.out.println("hello"));
t.start();
t.join();
t.start();
~~~

Câu hỏi: lỗi xuất hiện ở đâu? **Đáp án:** ở `t.start()` thứ hai với `IllegalThreadStateException`; `join()` không đặt lại trạng thái.

**Bài 2 — lý giải trạng thái:** Một đối tượng `Thread` chưa từng được `start()` nhưng đã được gọi `run()` trực tiếp hai lần. Lúc này `getState()` của đối tượng đó là gì nếu không có thread nào khác gọi `start()`? **Đáp án:** `NEW`; hai lời gọi `run()` không tạo thread mới.

**Bài 3 — thiết kế retry:** Một tác vụ gửi dữ liệu thất bại và cần thử lại nếu an toàn về nghiệp vụ. Có nên giữ `Thread` cũ rồi `start()` lần nữa? **Đáp án:** không. Phải quyết định retry theo hợp đồng của tác vụ (idempotency, giới hạn lần thử, backoff, xử lý side effect), sau đó gửi **task** vào executor hoặc tạo **thread mới**. Lỗi nghiệp vụ và vòng đời thread là hai vấn đề riêng.

**Bài 4 — đọc mã:** Một ứng dụng kiểm tra `!thread.isAlive()` trước khi `start()`. Điều kiện đó có đủ bảo đảm không ném `IllegalThreadStateException`? **Đáp án:** không. `isAlive()` có thể `false` khi thread chưa start *hoặc* đã chấm dứt, và phép kiểm tra có thể bị race.

## 12. Checklist khi triển khai

- Phân biệt đúng **task có thể thực thi lại** và **Thread object chỉ được start một lần**.
- Chỉ gọi `start()` cho một Thread `NEW`, tại nơi sở hữu trách nhiệm khởi động.
- Dùng `join()` hoặc cơ chế phối hợp khác khi cần biết task đã kết thúc; quản lý lỗi qua kênh kết quả phù hợp.
- Không dùng `run()` như cách sửa lỗi `start()` lần hai.
- Muốn chạy lại, tạo một đối tượng Thread mới hoặc gửi task mới cho executor còn hoạt động.
- Không dựa riêng vào `getState()` hoặc `isAlive()` để điều phối nhiều caller.
- Thiết kế quản lý dừng, interrupt, thất bại và retry theo logic nghiệp vụ; không dùng `Thread.stop()`.
- Trong ứng dụng thực, đo concurrency, giới hạn tài nguyên và đóng executor đúng cách.

**Ghi nhớ:** Một `Thread` không phải đối tượng “chạy lại được”. `start()` chỉ hợp lệ một lần trong suốt vòng đời của **chính đối tượng đó**. Muốn lặp lại công việc, hãy quản lý và thực thi lại **task** qua một phiên thread mới hoặc qua executor.