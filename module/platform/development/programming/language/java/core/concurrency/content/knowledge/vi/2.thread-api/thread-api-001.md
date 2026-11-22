# Tạo thread bằng Thread và Runnable trong Java

## 1. Mục tiêu và bối cảnh

Sau bài học, bạn có thể:

- Tạo, đặt tên, khởi chạy và chờ kết thúc một thread bằng lớp **Thread** và giao diện **Runnable**.
- Phân biệt **gọi run()** với **gọi start()**, hiểu khi nào mã thực thi trên thread hiện tại hoặc thread mới.
- Chọn giữa kế thừa Thread, triển khai Runnable và lambda; hiểu quan hệ giữa **công việc** và **thread thực thi công việc**.
- Quản lý vòng đời cơ bản, xử lý ngắt bằng **interrupt()**, và nhận diện rủi ro khi nhiều thread chia sẻ dữ liệu.
- Đọc đúng kết quả chương trình có thread: thứ tự thực thi thường không được bảo đảm và kết quả phụ thuộc vào đồng bộ hóa.

Phạm vi là **Java concurrency nói chung** qua API nền tảng của JDK; không bàn đến cơ chế quản lý thread, tác vụ bất đồng bộ hay cấu hình của Spring.

Một **thread** là luồng thực thi độc lập trong cùng tiến trình Java. Các thread chia sẻ heap và các đối tượng dùng chung, nhưng mỗi thread có call stack riêng. Khi nhiều thread cùng tồn tại, các công việc có thể *xen kẽ* (concurrency); chúng có thể thực sự chạy *song song* (parallelism) nếu tài nguyên CPU và bộ lập lịch cho phép. Không thể suy ra thứ tự chạy từ thứ tự gọi **start()**.

## 2. Hai API cốt lõi: Thread và Runnable

**java.lang.Thread** biểu diễn một thread, cung cấp các thao tác như **start()**, **join()**, **interrupt()**, **isAlive()**, **getState()** và **getName()**. Khi gọi **start()** trên đối tượng Thread ở trạng thái NEW, JVM sắp xếp cho phương thức **run()** của thread đó chạy trên luồng thực thi mới. **start()** trở về mà không đợi công việc hoàn thành.

**java.lang.Runnable** là functional interface có đúng một phương thức trừu tượng:

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

Đây là hình thức rút gọn để diễn giải hợp đồng API; **java.lang.Runnable** đã có sẵn trong JDK, không cần khai báo lại. Một **Runnable** mô tả việc cần làm, nhưng tự nó **không tạo hoặc khởi động thread**. Ta đưa Runnable vào một Thread, rồi gọi **start()** trên Thread đó.

Sơ đồ quan hệ:

~~~text
Runnable task ──(truyền vào constructor)──> Thread worker
                                            │
                                         start()
                                            │
                                  thread mới gọi task.run()
~~~

Điểm cần nhớ: **Thread là phương tiện thực thi; Runnable là phần công việc**. Thread còn triển khai Runnable, vì thế có thể override **Thread.run()** để mô tả công việc trực tiếp.

## 3. Ba cách tạo và chạy thread

Ví dụ sau chạy độc lập trên **Java 17+** và minh họa cả ba cách: kế thừa Thread, triển khai Runnable, dùng lambda làm Runnable.

Tệp **ThreadCreationDemo.java**:

~~~java
public class ThreadCreationDemo {

    static class ByThread extends Thread {
        ByThread() {
            super("class-thread");
        }

        @Override
        public void run() {
            System.out.println(getName() + ": chạy bằng Thread");
        }
    }

    static class ByRunnable implements Runnable {
        @Override
        public void run() {
            System.out.println(
                Thread.currentThread().getName() + ": chạy bằng Runnable"
            );
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new ByThread();
        first.start();
        first.join();

        Thread second = new Thread(new ByRunnable(), "runnable-thread");
        second.start();
        second.join();

        Runnable task = () -> System.out.println(
            Thread.currentThread().getName() + ": chạy bằng lambda"
        );
        Thread third = new Thread(task, "lambda-thread");
        third.start();
        third.join();

        System.out.println("main: hoàn tất");
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ThreadCreationDemo.java
java ThreadCreationDemo
~~~

Kết quả khi terminal hiển thị Unicode đúng:

~~~text
class-thread: chạy bằng Thread
runnable-thread: chạy bằng Runnable
lambda-thread: chạy bằng lambda
main: hoàn tất
~~~

Ví dụ này có thứ tự kết quả xác định **vì mỗi lần start() đều được theo sau bởi join() trước khi bắt đầu thread tiếp theo**. Nếu khởi động cả ba thread trước rồi mới join, các dòng từ ba thread có thể xuất hiện theo nhiều thứ tự.

### 3.1. Kế thừa Thread

~~~java
class Worker extends Thread {
    @Override
    public void run() {
        // Công việc chạy khi gọi start() trên Worker.
    }
}

Thread worker = new Worker();
worker.start();
~~~

Đoạn trên minh họa cách dùng; lớp Worker chưa có phương thức **main()** để tự chạy như một ứng dụng độc lập. Cách này đơn giản khi cần một loại thread có hành vi riêng, nhưng gắn mã công việc với chính đối tượng Thread. Java chỉ hỗ trợ kế thừa một lớp, nên lớp đã **extends Thread** không thể extends một lớp khác.

### 3.2. Triển khai Runnable

~~~java
class ReportTask implements Runnable {
    @Override
    public void run() {
        System.out.println("Building report");
    }
}

Runnable task = new ReportTask();
Thread worker = new Thread(task, "report-worker");
worker.start();
~~~

Đây cũng là đoạn minh họa cần được đặt trong chương trình hợp lệ. Cách **implements Runnable** tách việc cần làm khỏi cách chạy nó; cùng một loại task có thể được dùng để tạo nhiều Thread. Một đối tượng Runnable cụ thể cũng có thể được truyền cho nhiều Thread, nhưng khi đó **trạng thái của chính đối tượng Runnable sẽ được chia sẻ**.

### 3.3. Lambda

Vì Runnable là functional interface, có thể viết ngắn gọn:

~~~java
Runnable task = () -> System.out.println(
    "Running on " + Thread.currentThread().getName()
);
Thread worker = new Thread(task, "lambda-worker");
worker.start();
~~~

Lambda phù hợp với công việc ngắn. Biến cục bộ được lambda capture phải là **final hoặc effectively final**; quy tắc này không làm đối tượng mutable được capture trở nên thread-safe.

### Chọn cách nào?

| Tiêu chí | extends Thread | implements Runnable / lambda |
| --- | --- | --- |
| Vai trò | Định nghĩa hành vi ngay trong lớp thread | Định nghĩa task độc lập |
| Khả năng tái sử dụng công việc | Gắn với Thread cụ thể | Có thể tạo nhiều Thread hoặc chuyển cho executor |
| Kế thừa lớp khác | Không thể extends thêm lớp khác | Có thể extends lớp khác |
| Dễ tách trách nhiệm | Thấp hơn | Cao hơn |
| Khuyến nghị mặc định | Khi thật sự cần tùy biến Thread | **Ưu tiên Runnable** cho tác vụ thông thường |

Cả hai con đường cuối cùng vẫn cần một **Thread.start()** để có thread mới khi dùng trực tiếp API cổ điển.

## 4. start() khác run() như thế nào?

**run() là lời gọi phương thức Java thông thường**. Khi gọi **worker.run()** trực tiếp, code chạy đồng bộ trên thread đang gọi; không có thread mới. **start()** mới yêu cầu JVM bắt đầu một thread khác và sau đó chạy **run()** trên thread đó.

Tệp **StartVsRunDemo.java**:

~~~java
public class StartVsRunDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
            () -> System.out.println(
                "task: " + Thread.currentThread().getName()
            ),
            "worker-1"
        );

        worker.run();   // Chạy trực tiếp trên main.
        worker.start(); // Bắt đầu thread mới.
        worker.join();  // Chờ worker kết thúc.
    }
}
~~~

~~~bash
javac -encoding UTF-8 StartVsRunDemo.java
java StartVsRunDemo
~~~

Stdout:

~~~text
task: main
task: worker-1
~~~

Có thể gọi **run()** trực tiếp nhiều lần giống một phương thức bình thường, nhưng **một đối tượng Thread chỉ được gọi start() một lần**. Gọi lại **start()** khi nó đã được khởi động, kể cả đã kết thúc, sẽ ném **IllegalThreadStateException**. Muốn chạy lại task, tạo **Thread mới**; không thể reset Thread cũ về NEW.

## 5. Vòng đời và điều phối thread

Một số trạng thái trả về bởi **Thread.getState()**:

| Trạng thái | Ý nghĩa thực tế |
| --- | --- |
| **NEW** | Đã tạo đối tượng Thread nhưng chưa gọi start(). |
| **RUNNABLE** | Đủ điều kiện chạy hoặc đang chạy trên JVM; không đồng nghĩa chắc chắn đang chiếm CPU. |
| **BLOCKED** | Chờ giành monitor lock khi đi vào khối/phương thức synchronized. |
| **WAITING** | Đang chờ không có giới hạn thời gian, ví dụ join() không timeout hoặc Object.wait() không timeout. |
| **TIMED_WAITING** | Đang chờ có thời hạn, ví dụ Thread.sleep(...) hoặc join(timeout). |
| **TERMINATED** | Phương thức run() đã kết thúc, do hoàn thành hoặc lỗi không được bắt. |

Luồng phổ biến:

~~~text
NEW --start()--> RUNNABLE --run() kết thúc--> TERMINATED
                     │
           có thể chuyển qua
           BLOCKED / WAITING / TIMED_WAITING
                     │
                 RUNNABLE
~~~

**getState() chỉ là ảnh chụp tức thời**, phù hợp cho quan sát hoặc chẩn đoán, không dùng để xây dựng giao thức đồng bộ. Bộ lập lịch không hứa thread nào sẽ chạy trước, chạy bao lâu, hoặc chạy song song.

**Thread.currentThread()** trả về đối tượng Thread đang thực thi mã, còn **getName()** hỗ trợ phân biệt thread trong log. Có thể đặt tên qua constructor hoặc **setName(...)**, tốt nhất trước **start()**. Tên giúp quan sát chứ không quyết định thứ tự lập lịch.

### Chờ kết thúc với join()

**join()** khiến thread gọi chờ thread đích hoàn thành. Với mã:

~~~java
Thread worker = new Thread(() -> doWork());
worker.start();
worker.join();
consumeResult();
~~~

Đây là ví dụ luồng điều khiển, trong đó **doWork()** và **consumeResult()** là phương thức giả định cần được định nghĩa. Sau khi **join() trả về bình thường do worker kết thúc**, các hiệu ứng bộ nhớ của worker xảy ra-before (happens-before) các thao tác tiếp theo của thread đã join. Không có nghĩa là mọi việc truy cập cùng một biến đều an toàn *trong khi cả hai thread đang chạy*.

**join()** có thể ném **InterruptedException** khi thread đang đợi bị ngắt. Bản có timeout, như **join(1000)**, có thể trở về khi worker vẫn còn sống: nếu cần chắc chắn đã kết thúc, kiểm tra **isAlive()** hoặc sử dụng giao thức chờ phù hợp.

## 6. Thread chia sẻ dữ liệu: nguy cơ race condition

Tạo nhiều thread không tự làm chương trình thread-safe. Các thread dùng chung heap, vì vậy phép tăng **count++** trên một biến thường gồm đọc, cộng, ghi; đây không phải một thao tác nguyên tử. Nếu hai thread cập nhật đồng thời mà không có đồng bộ hóa, có thể xảy ra **lost update** và vấn đề hiển thị bộ nhớ (*visibility*). Đánh dấu biến là **volatile** chỉ giải quyết một số yêu cầu hiển thị/thứ tự, **không biến count++ thành atomic**.

Ví dụ đúng với **AtomicInteger**, dùng chung một đối tượng Runnable:

Tệp **SharedCounterDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger total = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                total.incrementAndGet();
            }
        };

        Thread first = new Thread(increment, "counter-1");
        Thread second = new Thread(increment, "counter-2");

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("total=" + total.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedCounterDemo.java
java SharedCounterDemo
~~~

Stdout luôn là:

~~~text
total=20000
~~~

**Vì sao đúng?** Hai Thread chạy cùng một Runnable, cả hai capture cùng **AtomicInteger**. **incrementAndGet()** thực hiện tăng nguyên tử; **join()** bảo đảm main đợi cả hai thread kết thúc rồi mới đọc. Không được thay bằng **int[] total = {0}; total[0]++** và kỳ vọng luôn được 20.000: đó là data race.

Các cách bảo vệ trạng thái chia sẻ trong Java gồm **synchronized**, lock, atomic classes và các cấu trúc concurrent. Chọn cơ chế phù hợp với thao tác cần bảo vệ; **join()** chỉ giải quyết chờ hoàn thành và công bố kết quả khi thread kết thúc, không bảo vệ một chuỗi cập nhật đồng thời đang diễn ra.

## 7. Ngắt thread đúng cách với interrupt()

**interrupt()** gửi tín hiệu yêu cầu ngắt, **không ép buộc dừng thread ngay lập tức** và không thay thế cơ chế hủy an toàn. Mã đang chạy cần tự hợp tác bằng cách kiểm tra **isInterrupted()** hoặc phản ứng với **InterruptedException** ở các thao tác chờ có thể bị ngắt (như sleep, wait, join).

Tệp **InterruptDemo.java**:

~~~java
public class InterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException e) {
                // sleep() xóa trạng thái interrupt khi ném exception.
                Thread.currentThread().interrupt();
            }

            System.out.println(
                "worker interrupted: "
                    + Thread.currentThread().isInterrupted()
            );
        }, "interruptible-worker");

        worker.start();
        worker.interrupt();
        worker.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptDemo.java
java InterruptDemo
~~~

Stdout:

~~~text
worker interrupted: true
~~~

Kết quả này vẫn đúng nếu interrupt đến trước khi worker bắt đầu ngủ hoặc trong lúc ngủ. Nếu được ngắt trong **sleep()**, phương thức ném **InterruptedException** và xóa interrupt status; nhánh **catch** đặt lại cờ để không làm mất tín hiệu. Nếu cờ đã được đặt trước lần kiểm tra điều kiện, vòng lặp sẽ thoát. Trong thực tế, sau khi nhận yêu cầu ngắt, task nên giải phóng tài nguyên rồi kết thúc hợp tác; không nên tiếp tục vô hạn với cờ interrupt bị bỏ qua.

Lưu ý:

- **isInterrupted()** kiểm tra cờ của một Thread mà không xóa cờ.
- **Thread.interrupted()** là phương thức static: kiểm tra **và xóa** cờ của thread hiện tại; không dùng thay thế một cách vô ý.
- **InterruptedException** là checked exception. Phương thức **Runnable.run()** không khai báo checked exception, nên phải bắt trong run(), chuyển hóa phù hợp hoặc tổ chức lại phương thức.
- Khi bắt InterruptedException mà không thể xử lý đầy đủ, thực hành phổ biến là khôi phục cờ bằng **Thread.currentThread().interrupt()** rồi thoát hoặc chuyển quyền xử lý lên tầng phù hợp. Ở phương thức có **throws InterruptedException**, có thể để exception truyền lên thay vì nuốt lỗi.

## 8. Lỗi trong thread và vấn đề kết thúc chương trình

Một exception không được bắt trong **run()** kết thúc thread đó, và mặc định được báo qua uncaught-exception handler của thread/thread group. **join() không tự ném lại lỗi của worker trên main**. Nếu cần ghi nhận lỗi có kiểm soát, thiết lập handler trước khi start:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("task failed");
}, "failing-worker");

worker.setUncaughtExceptionHandler((thread, error) ->
    System.err.println(thread.getName() + ": " + error.getMessage())
);
worker.start();
~~~

Đoạn này minh họa callback xử lý lỗi và không có main() riêng. Handler phù hợp để quan sát, nhưng không có cơ chế mặc định chuyển kết quả/lỗi về người tạo thread. Với tác vụ cần **giá trị trả về** hoặc truyền exception có cấu trúc, xem **Callable/Future/ExecutorService** ở phần học tiếp theo: **Runnable.run() trả void** và không cho phép checked exception thoát trực tiếp.

Java có **user thread** (mặc định với thread thông thường) và **daemon thread**. JVM có thể kết thúc khi chỉ còn daemon threads; vì vậy không dùng daemon cho công việc mà bắt buộc phải hoàn thành như ghi dữ liệu quan trọng. Có thể gọi **setDaemon(true)** trước **start()**, nhưng gọi sau khi thread đã bắt đầu sẽ gây **IllegalThreadStateException**.

Không nên gọi **Thread.stop()**, **suspend()** hoặc **resume()** để điều khiển vòng đời: các API cũ đó không an toàn/đã bị loại bỏ hoặc deprecated tùy phiên bản JDK. Dùng cờ dừng có bảo đảm bộ nhớ, **interrupt()**, và quản lý tài nguyên có kiểm soát.

## 9. Khi nào nên tạo Thread trực tiếp?

Tạo Thread trực tiếp hữu ích khi học nguyên lý, chạy một tác vụ ngắn và số lượng thread nhỏ, có vòng đời rõ ràng. Trong ứng dụng có nhiều tác vụ, **một Thread cho mỗi request/tác vụ** có thể tạo quá nhiều platform threads, tăng chi phí stack, context switching và khó quản lý shutdown.

API cấp cao hơn của Java có **ExecutorService** để quản lý việc gửi và thực thi tác vụ, **Future** để quan sát kết quả, và từ **Java 21** có **virtual threads** (ví dụ **Thread.ofVirtual().start(task)**). Đây là các bước phát triển trên kiến thức nền của **Thread** và **Runnable**, không thay đổi quy tắc rằng task cần được lên lịch thực thi và dữ liệu chia sẻ phải được bảo vệ. Bài hiện tại tập trung vào Thread truyền thống cùng Runnable.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| **new Thread(task)** đã tạo luồng chạy ngay | Mới tạo đối tượng ở trạng thái NEW; cần **start()**. |
| Gọi **run()** tạo thread mới | **run()** chạy trên thread gọi; **start()** mới khởi động thread mới. |
| Mỗi Runnable luôn tương ứng một thread | Runnable chỉ là task; có thể truyền một Runnable cho nhiều Thread, hoặc dùng cách thực thi khác. |
| **start()** chạy ngay lập tức và theo đúng thứ tự được gọi | JVM/OS quyết định lịch; không có cam kết thứ tự thực thi. |
| Sau **sleep(...)** thì thread khác chắc chắn chạy hoặc hoàn thành | sleep chỉ tạm dừng thread hiện tại, không cấp quyền/thứ tự cho thread khác. |
| **join()** tự làm mọi thao tác trên dữ liệu chia sẻ an toàn | join đợi kết thúc và cung cấp quan hệ happens-before khi hoàn thành; thao tác đồng thời vẫn cần đồng bộ hóa. |
| **volatile int count** làm **count++** atomic | volatile không biến chuỗi read-modify-write thành một thao tác nguyên tử. |
| **interrupt()** giết thread | interrupt chỉ yêu cầu ngắt; task phải xử lý tín hiệu hợp tác. |
| Exception trong worker tự được ném ra ở main | Lỗi không tự truyền qua **join()**. |
| Thread đã TERMINATED có thể **start()** lại | Mỗi đối tượng Thread chỉ start một lần. |

## 11. Checklist thực hành

1. Viết task trong **Runnable** (class hoặc lambda) khi không cần một lớp Thread chuyên biệt.
2. Tạo **new Thread(task, "tên-ý-nghĩa")**, rồi gọi **start()**; không gọi **run()** nếu muốn chạy trên thread khác.
3. Quyết định rõ ai chịu trách nhiệm chờ, hủy, theo dõi lỗi và giải phóng tài nguyên; dùng **join()** khi thật sự cần chờ hoàn thành.
4. Xác định đối tượng mutable nào bị nhiều thread chia sẻ. Dùng **synchronized**, **Lock**, **AtomicInteger** hoặc thiết kế không chia sẻ trạng thái tùy nhu cầu.
5. Khi công việc có thể bị hủy, xử lý **interrupt()** và **InterruptedException** hợp tác; tránh vòng lặp chờ bận, tránh bỏ qua ngắt.
6. Không viết chương trình dựa vào thứ tự các dòng log từ nhiều thread, thời gian **sleep()**, hoặc ảnh chụp **getState()**.

### Tự kiểm tra

**Câu 1.** Nếu viết **Thread t = new Thread(task); t.run();**, có thread mới không?  
**Trả lời:** Không. **task.run()** được thực hiện trên thread gọi **t.run()**.

**Câu 2.** Hai Thread nhận cùng một instance Runnable thì có cùng call stack không?  
**Trả lời:** Không. Mỗi thread có stack riêng, nhưng hai thread tham chiếu đến **cùng đối tượng Runnable** và các đối tượng chung mà task sử dụng.

**Câu 3.** Có được gọi **start()** trên cùng Thread sau khi **join()** xong không?  
**Trả lời:** Không. Tạo một Thread mới nếu cần chạy lại công việc.

**Câu 4.** Vì sao kết quả **count++** từ hai thread có thể sai ngay cả khi main gọi **join()** cả hai?  
**Trả lời:** Phép tăng không atomic nên hai thread có thể ghi đè cập nhật của nhau trước khi kết thúc. **join()** không sửa các cập nhật đã mất; dùng đồng bộ hóa hoặc phép tăng nguyên tử.

**Câu 5.** Khi worker đang **sleep()** bị ngắt, nên lưu ý điều gì?  
**Trả lời:** **sleep()** ném **InterruptedException** và xóa interrupt status; mã cần xử lý ngắt hợp tác, thường khôi phục cờ nếu không chuyển exception lên được, rồi thoát phù hợp.
