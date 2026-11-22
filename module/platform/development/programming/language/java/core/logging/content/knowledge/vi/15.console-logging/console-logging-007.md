# Đồng bộ output trong Console logging của Java

## 1. Khái niệm và mục tiêu

**Đồng bộ output** (output synchronization) trong **Console logging** là cách điều phối những thread cùng ghi log ra console để **nội dung của mỗi bản ghi không bị xen lẫn bất ngờ**. Khi ứng dụng Java chạy nhiều tác vụ đồng thời, nhiều thread có thể gọi **System.out.print/println**, **System.err.print/println**, **Logger.info()**, hoặc ghi qua **ConsoleHandler/ConsoleAppender** của logging framework.

Ví dụ hai sự kiện dự kiến:

~~~text
INFO | worker=A | event=task.started
WARNING | worker=B | event=task.retry
~~~

Nếu một sự kiện bị chia thành nhiều lời gọi print riêng lẻ, kết quả *có thể* trở nên khó đọc:

~~~text
INFO | worker=WARNING | worker=B | event=task.retry
A | event=task.started
~~~

Đây là **minh họa khả năng interleaving**, không phải stdout bắt buộc xảy ra mỗi lần chạy. Nguyên nhân là nhiều thread được CPU lập lịch độc lập và có thể ghi giữa các thao tác của nhau.

Để thiết kế console logging đúng, phải phân biệt:

1. **Atomicity theo bản ghi:** từng thông điệp log được xuất nguyên vẹn, không bị trộn với phần của sự kiện khác.
2. **Mutual exclusion:** ở một thời điểm, chỉ một bên được quyền thực hiện thao tác ghi được bảo vệ.
3. **Ordering:** sự kiện nào được ghi trước sự kiện nào. Một lock tự nó **không quy định** thứ tự thread giành lock.
4. **Flushing:** đẩy bytes trong buffer tới tầng xuất phía dưới. Flush **không đồng nghĩa** atomicity hoặc durability.
5. **Durability:** bản ghi có còn sau crash, ngắt kết nối hay lỗi collector hay không.

**Synchronized, ordered và flushed là ba thuộc tính khác nhau.** Một hệ thống có dòng log nguyên vẹn nhưng thứ tự xen kẽ hoàn toàn hợp lệ khi các request chạy đồng thời.

## 2. stdout và stderr là hai luồng khác nhau

Java có hai luồng xuất chuẩn:

| Thành phần | Đích thông dụng | Đặc điểm |
| --- | --- | --- |
| **System.out** | stdout | Kết quả chương trình và output thông thường |
| **System.err** | stderr | Chẩn đoán và lỗi |
| **java.util.logging.ConsoleHandler** | **System.err** | Handler của JUL, mặc định SimpleFormatter |
| **Log4j 2 Console Appender** | SYSTEM_OUT hoặc SYSTEM_ERR | Chọn bằng target trong log4j2.xml |
| **Logback ConsoleAppender** | System.out hoặc System.err | Chọn bằng target trong logback.xml |
| **StreamHandler(System.out, formatter)** | stdout | Handler JUL với OutputStream được chọn |

Cả stdout và stderr có thể xuất hiện trong **cùng một terminal**, nhưng OS, IDE và container runtime có thể chuyển chúng tới **hai pipe hoặc collector khác nhau**. Việc màn hình hiển thị chung **không chứng minh chúng có cùng lock hoặc cùng thứ tự**.

Ví dụ:

~~~java
System.out.println("INFO | event=started");
System.err.println("WARNING | event=retry");
~~~

Mỗi câu lệnh là một thao tác trên stream tương ứng. Nếu nhiều thread cùng làm việc và công cụ bên ngoài ghép hai stream, thứ tự hiển thị có thể khác mong đợi. **Không thể khóa riêng System.out rồi tin rằng System.err cũng được bảo vệ.**

**Khuyến nghị:** chọn một pipeline/đích console nhất quán cho nhóm log mà bạn cần so sánh, bổ sung timestamp và correlation ID. Đừng xem thứ tự các dòng đã merge từ stdout/stderr là tổng thứ tự nghiệp vụ.

## 3. Vì sao log bị interleaving?

Các tình huống phổ biến:

- **Một bản ghi gồm nhiều lệnh print:** một thread in prefix, thread khác chen message vào trước khi thread đầu in suffix.
- **Formatter in nhiều dòng:** một stack trace hoặc block thông tin được xuất thành nhiều lời gọi và thread khác có thể chen giữa.
- **Nhiều writer độc lập:** code dùng System.out trong khi backend dùng ConsoleAppender hoặc StreamHandler khác.
- **Hai backend cùng ghi console:** mỗi backend có cơ chế đồng bộ riêng, không tự phối hợp trên một lock chung.
- **Nhiều process:** hai JVM hoặc tool khác cùng ghi tới một terminal/pipe.
- **stdout và stderr được merge:** collector/IDE có thể thêm buffering và làm thứ tự quan sát thay đổi.
- **Một log event mang dữ liệu mutable:** writer bất đồng bộ format muộn, dữ liệu đã bị thread khác sửa.
- **Thiếu định danh ngữ cảnh:** các dòng hoàn toàn nguyên vẹn nhưng người đọc nhầm thứ tự request A và B thành lỗi đồng bộ.

Ví dụ code có nguy cơ:

~~~java
System.out.print("INFO | worker=" + workerName);
System.out.println(" | event=" + eventName);
~~~

Đoạn trên là **snippet**, giả định hai biến đã có. Thread khác có thể chạy giữa hai lời gọi.

Cách đơn giản tốt hơn:

~~~java
String line = "INFO | worker=" + workerName
        + " | event=" + eventName;
System.out.println(line);
~~~

Tạo **cả dòng** rồi gọi println một lần giảm nguy cơ interleaving trong trường hợp dùng chung một PrintStream. Nhưng nó **không đặt thứ tự** các dòng giữa thread A và B, và không bảo vệ khỏi mọi writer khác không cùng cơ chế.

## 4. PrintStream.println() thread-safe đến đâu?

Trong Java 17, System.out và System.err là các **java.io.PrintStream**. Implementation JDK thông dụng đồng bộ nhiều thao tác khi ghi qua **cùng PrintStream**; vì vậy một lời gọi **println(String)** cho cả dòng thường là đơn vị in có tính nhất quán đối với những lời gọi khác trên chính đối tượng đó.

Giới hạn phải hiểu chính xác:

1. **Một lời gọi println không ghép nhiều lời gọi thành một transaction.** Việc in header, body, newline bằng ba câu lệnh vẫn có điểm chen giữa.
2. **Không có total order giữa hai thread** chỉ vì chúng đều gọi println; thread nào thực hiện trước phụ thuộc scheduling.
3. **System.out và System.err không dùng chung monitor bắt buộc.**
4. **System.setOut(...)** có thể thay PrintStream. Một lock trên PrintStream cũ không tự bảo vệ stream mới.
5. Writer hoặc thư viện dùng **OutputStream wrapper riêng** không nhất thiết cùng lock.
6. Một event nhiều dòng từ một Formatter không tự có cùng ranh giới atomic như một println đơn.
7. Nhiều **JVM/process** không chia sẻ đối tượng monitor Java.
8. Collector nhận bytes rồi chuyển, parse, gộp có thể làm thay đổi thứ tự hiển thị.
9. **PrintStream** thông thường không ném IOException trực tiếp khi ghi lỗi, mà có trạng thái lỗi có thể xem bằng **checkError()**. Đây không phải giải pháp bảo đảm lưu log.

**Không kết luận:** “println thread-safe nên toàn bộ console logging luôn có thứ tự, không mất log và không thể trộn”. Cần định nghĩa *đơn vị cần bảo vệ*, *phạm vi writer* và *điều kiện ordering*.

## 5. Mutual exclusion không tự tạo ordering

**Mutual exclusion** giải quyết “hai thread có cùng ghi trong vùng được bảo vệ hay không?”. **Ordering** giải quyết “event nào phải xảy ra trước event nào?”.

Ví dụ, với một lock:

~~~java
synchronized (CONSOLE_LOCK) {
    System.out.println(message);
}
~~~

Đây là snippet giả định có CONSOLE_LOCK và message. Hai thread dùng **cùng lock** không đồng thời ở trong vùng này, nhưng thread B hoàn toàn có thể lấy lock trước thread A. Ngay cả khi thread A được tạo trước, **start trước không đồng nghĩa print trước**.

Khi nghiệp vụ bắt buộc:

~~~text
event=task.started
event=task.completed
~~~

phải có quan hệ xử lý phù hợp: Thread B đợi một **CountDownLatch**, **Future**, queue hoặc tín hiệu hoàn tất từ bước A trước khi phát sự kiện B. Nếu task A và B thực sự độc lập, chúng có thể in xen kẽ một cách hợp lệ; nên dùng requestId và workerId để phân biệt.

| Mục tiêu | Cơ chế phù hợp |
| --- | --- |
| Không xen ký tự trong một thông điệp đơn | Xây trọn message; một writer/Printer an toàn |
| Không xen các dòng của một block | Cùng lock cho cả block hoặc queue event nguyên khối |
| Event B chỉ được tạo sau khi A xong | Latch/Future/barrier/quan hệ nghiệp vụ |
| Lưu thứ tự các event đã enqueue | Một queue và một consumer |
| Biết event của request nào | requestId/jobId/traceId |
| Dữ liệu đã ra khỏi buffer | flush()/policy của backend |
| Không mất log ở collector | Thiết kế lưu trữ, retry, shutdown và monitoring |

Một **lock không phải đồng hồ**, một **queue không phải transaction log**, và **flush không phải fsync**.

## 6. Phương án nhỏ gọn: một println cho mỗi event

Trong CLI hoặc ví dụ học tập, cách phù hợp thường là:

~~~java
String line = "INFO | requestId=" + requestId
        + " | event=order.accepted orderId=" + orderId;
System.out.println(line);
~~~

Đây là snippet cần các biến đã khai báo. Nếu số thread ít và cùng dùng System.out, nó đơn giản và ít cơ hội xen các mảnh riêng của một dòng.

**Không nên:**

~~~java
System.out.print("INFO | requestId=");
System.out.print(requestId);
System.out.println(" | event=order.accepted");
~~~

Ba câu lệnh không được bảo vệ thành một khối. Thread khác vẫn có thể chèn output giữa chúng.

Các giới hạn của phương án “một println”:

- Không giúp gộp **stack trace** được format thành nhiều dòng.
- Không có cơ chế level/filter hoặc lựa chọn output trong ứng dụng thực tế.
- Không giải quyết log từ **System.err**, nhiều backend hoặc nhiều process.
- Không tạo một thứ tự xác định giữa thread A/B.
- Không tự thêm timestamp, logger name, requestId hoặc quyền truy cập.

Khi ứng dụng lớn, hãy dùng logging framework thay vì rải System.out.println trong mọi lớp. Điều đó giúp giới hạn log volume, chọn level, Formatter/Encoder và đích xuất tập trung.

## 7. Dùng synchronized với một lock chung

Khi **bắt buộc ghi nhiều dòng như một đơn vị** do chính code ứng dụng kiểm soát, dùng một lock rõ phạm vi:

~~~java
private static final Object OUTPUT_LOCK = new Object();

static void printBlock(String title, String detail) {
    synchronized (OUTPUT_LOCK) {
        System.out.println(title);
        System.out.println(detail);
    }
}
~~~

Đây là snippet đặt trong một lớp Java, không phải chương trình độc lập.

Hai thread gọi **printBlock** đều lấy OUTPUT_LOCK trước khi in. Vì vậy chúng không chèn những lần in của **chính printBlock** vào giữa block của nhau.

Nhưng có những giới hạn:

- **Tất cả bên liên quan phải dùng cùng OUTPUT_LOCK**. Một nơi khác gọi System.out.println trực tiếp có thể in giữa hai dòng của block.
- Lock này không tự bảo vệ stderr hoặc Writer khác.
- Lock Java không đồng bộ các process khác nhau.
- Nếu System.out đã bị thay đổi thì vẫn phải đánh giá toàn bộ đường output.
- Đừng giữ lock trong khi **tính toán nặng, network call hoặc I/O ngoài cần thiết**.
- Tránh tự gọi Logger trong một vùng đang giữ lock nếu backend có lock riêng và có thể tạo **deadlock do thứ tự khóa**.
- Nếu log có traffic lớn, lock chung có thể trở thành **contention hotspot**.

Một phương án khác là **synchronized(System.out)**, nhưng nó phụ thuộc object stream hiện tại và các bên khác có dùng cùng monitor hay không. **Lock do ứng dụng sở hữu** diễn đạt phạm vi bảo vệ rõ hơn.

**Quy tắc:** nếu không kiểm soát tất cả writer, synchronized riêng trong một lớp chưa đủ. Hãy thống nhất logging pipeline hoặc lựa chọn một writer duy nhất.

## 8. Một console writer với BlockingQueue

Với nhiều producer, kiến trúc **nhiều thread tạo event, một thread ghi console** giúp tập trung đồng bộ:

~~~text
Producer A ---+
              |
Producer B ---+----> BlockingQueue<Event>
              |               |
Producer C ---+               v
                       console-writer
                             |
                             v
                        System.out
~~~

**Ưu điểm:**

- Mỗi event được tạo hoàn chỉnh rồi đặt vào queue.
- Producer không tự tranh quyền in ra console.
- Một consumer có thể xử lý lần lượt các event và format theo chuẩn chung.
- Có thể dùng **ArrayBlockingQueue** để giới hạn bộ nhớ.
- Dễ gắn metrics về queue depth, output latency và số event bị từ chối.
- Việc dừng writer có thể được quản lý tập trung.

**Nhược điểm:**

- **Queue đầy** cần backpressure hoặc chính sách discard rõ ràng.
- **put()** có thể chặn producer khi consumer không theo kịp.
- **offer()** có thể trả false; code không được bỏ qua kết quả nếu việc mất event là không thể chấp nhận.
- Process chết khi queue chưa drain có thể làm mất log.
- Producer thread có thể bị interrupt hoặc gặp lỗi, cần xử lý shutdown và tín hiệu hoàn tất.
- Thứ tự của hai producer là **thứ tự thực sự enqueue**, không phải thứ tự khởi tạo thread.
- Một writer vẫn không kiểm soát thư viện khác gọi System.err/println bên ngoài queue.

Trong production nên ưu tiên **Async Appender/AsyncLogger có sẵn** của backend phù hợp thay vì tự xây logging infrastructure, trừ khi có mục đích rất cụ thể.

## 9. Chương trình Java 17+ chạy độc lập: queue và writer thread

Ví dụ này dùng hai producer thread **A** và **B**, một writer thread, một queue có giới hạn và hai **CountDownLatch**. Latch giúp thứ tự ba event **xác định trong bài kiểm tra**; queue giúp từng event được in nguyên vẹn bởi một writer.

Lưu dưới tên **ConsoleOutputSyncDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public final class ConsoleOutputSyncDemo {
    private record Event(String message, boolean stop) {}

    private static final BlockingQueue<Event> EVENTS =
            new ArrayBlockingQueue<>(8);

    private static final CountDownLatch FIRST =
            new CountDownLatch(1);
    private static final CountDownLatch SECOND =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread writer = new Thread(() -> {
            try {
                while (true) {
                    Event event = EVENTS.take();
                    if (event.stop()) {
                        return;
                    }
                    System.out.println(event.message());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "console-writer");

        Thread producerA = new Thread(() -> {
            try {
                EVENTS.put(new Event(
                        "INFO | worker=A | event=task.started", false));
                FIRST.countDown();

                SECOND.await();
                EVENTS.put(new Event(
                        "INFO | worker=A | event=task.completed", false));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer-A");

        Thread producerB = new Thread(() -> {
            try {
                FIRST.await();
                EVENTS.put(new Event(
                        "WARNING | worker=B | event=task.retry", false));
                SECOND.countDown();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer-B");

        writer.start();
        producerA.start();
        producerB.start();

        producerA.join();
        producerB.join();
        EVENTS.put(new Event("", true));
        writer.join();

        System.out.println("records=3");
    }
}
~~~

### Biên dịch và chạy

Với JDK 17 hoặc mới hơn:

~~~bash
javac ConsoleOutputSyncDemo.java
java ConsoleOutputSyncDemo
~~~

**Stdout chính xác ở điều kiện chạy bình thường:**

~~~text
INFO | worker=A | event=task.started
WARNING | worker=B | event=task.retry
INFO | worker=A | event=task.completed
records=3
~~~

Chương trình không chủ động in gì lên stderr. Nhãn INFO/WARNING là **chuỗi message mô phỏng log**, không phải Level thực của JUL. Chương trình cần JDK thuần, không có Maven hay dependency ngoài.

### Phân tích kết quả

1. Producer A đưa **task.started** vào queue trước khi gọi **FIRST.countDown()**.
2. Producer B chỉ tiếp tục sau **FIRST.await()**, nên event **task.retry** được enqueue sau task.started.
3. Producer B gọi **SECOND.countDown()** sau khi đã enqueue task.retry.
4. Producer A chờ **SECOND.await()**, nên chỉ enqueue task.completed sau task.retry.
5. **ArrayBlockingQueue** giữ thứ tự những phần tử đã đưa vào; writer lấy từng event và in một lần.
6. Main gọi **join()** hai producer để biết chúng đã kết thúc, rồi mới enqueue event kết thúc.
7. Writer gặp event có **stop=true** mới kết thúc. Main join writer, sau đó in records=3.
8. Vì ranh giới thứ tự được tạo bởi latch, scheduler có chạy A/B xen kẽ kiểu nào thì ba event vẫn được enqueue theo thứ tự trên.
9. Khi bỏ latch, những event của các producer có thể đến queue theo thứ tự khác; writer vẫn in từng event nguyên vẹn.
10. Queue có dung lượng **8**, không tăng RAM vô hạn. Khi đầy, **put() chờ**; đây là backpressure, cần được quản trị ở ứng dụng thật.

**Giới hạn của demo:** nếu thread bị interrupt hoặc writer gặp lỗi bất thường, catch khôi phục interrupt flag nhưng không hoàn thiện một protocol báo lỗi/phát tín hiệu cho thread còn lại. Production phải có quản lý failure, timeout, finally, monitoring và shutdown. **Đừng sao chép ví dụ học tập như một logging backend production hoàn chỉnh.**

## 10. So sánh ba chiến lược

| Phương án | Atomicity trong phạm vi hợp tác | Ordering | Độ phức tạp | Khi phù hợp |
| --- | --- | --- | --- | --- |
| Một println cho toàn message | Đơn vị lời gọi trên cùng PrintStream JDK | Không cố định giữa threads | Thấp | CLI, ví dụ nhỏ |
| synchronized trên lock chung | Cả block nếu mọi writer cùng lock | Theo thứ tự lấy lock, không theo nghiệp vụ | Vừa | Code tự quản lý nhiều lần in |
| Một writer thread + queue | Mỗi event qua queue được writer xử lý tuần tự | Theo thứ tự enqueue | Cao hơn | Nhiều producer/async output |
| Console Appender/Handler chuẩn | Tùy implementation/backend được hỗ trợ | Không tự tạo total order đa thread | Cấu hình tập trung | Phần lớn ứng dụng thực tế |

**Không nên tạo một queue riêng cho từng module** rồi để nhiều writer cùng ghi ra System.out: khi đó bạn quay lại vấn đề nhiều đích ghi độc lập. Một backend có thể cung cấp nhiều Appender có chủ đích, nhưng mỗi đích cần được hiểu và kiểm thử.

## 11. Console logging với java.util.logging

**java.util.logging.Logger** có API được Java SE thiết kế an toàn khi gọi từ nhiều thread. Điều này cho phép nhiều thread sử dụng cùng Logger mà không phải đặt **synchronized** quanh mỗi lệnh info()/warning().

**ConsoleHandler** trong JUL kế thừa StreamHandler và xuất LogRecord tới **System.err**. Nó kiểm tra level, Filter và dùng Formatter khi publish. **StreamHandler** cung cấp thao tác flush/close cho OutputStream được cấu hình.

Ví dụ tệp **logging.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

Đây là mẫu cấu hình JUL của một ứng dụng; không phải cấu hình của chương trình ConsoleOutputSyncDemo, vì demo dùng PrintStream/BlockingQueue trực tiếp.

Trong một ứng dụng JUL, có thể gọi:

~~~java
logger.log(Level.WARNING,
        "event=inventory.retry attempt={0}", 2);
~~~

Đoạn là snippet, giả định biến logger và import Level đã có.

**Điều Logger thread-safe không có nghĩa:**

- Các thread phát log theo một thứ tự toàn cục cố định.
- Tự viết Formatter với mutable state luôn thread-safe.
- Stack trace multiline tự được collector gộp thành một event.
- Hai Handler cùng ghi stderr sẽ có cùng lock do ứng dụng tự tạo.
- Log đã đến đích lưu bền ngay khi method logger.log() trả về.

**Tránh gắn nhiều ConsoleHandler trùng:** Logger con có Handler riêng và Logger cha cũng có Handler có thể xuất cùng LogRecord hai lần khi **useParentHandlers=true**. Kiểm tra đường logger hierarchy trước khi nghi ngờ lỗi interleaving.

## 12. Custom Handler hoặc Formatter cần được thiết kế thread-safe

Khi tự viết **Handler**, **Appender** hoặc **Formatter** có trạng thái, cần xác định đồng bộ ở đâu và tránh deadlock.

Một Formatter ngắn minh họa:

~~~java
Formatter compact = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | " + formatMessage(record)
                + System.lineSeparator();
    }
};
~~~

Đây là snippet với import java.util.logging.Formatter và LogRecord; biến compact là một Formatter, **không phải chương trình chạy riêng**. Nó không in timestamp hay Throwable nên không phù hợp nguyên xi cho hệ thống cần stack trace.

Checklist với thành phần custom:

1. Nếu giữ **counter, cache, StringBuilder hoặc buffer mutable**, có biện pháp bảo vệ trạng thái khi nhiều thread gọi không?
2. Có format **nguyên event** thành một vùng dữ liệu trước khi gửi tới stream không?
3. Có tôn trọng **isLoggable(record)**, level, Filter và formatter contract không?
4. Nếu in nhiều dòng, có đảm bảo dùng cơ chế xuất phù hợp của backend không?
5. Có phát log đệ quy bên trong Handler/Filter làm vòng lặp logging không?
6. Có dùng lock theo thứ tự cố định để tránh deadlock không?
7. Có quản lý vòng đời **flush(), close(), shutdown** đúng không?
8. Có tránh đóng **System.out/System.err** khi Handler không sở hữu hai stream này không?
9. Có test nhiều thread và exception multiline không?
10. Có giám sát lỗi output thay vì bỏ qua không?

Không phải mọi component logging đều dùng cùng một lock toàn JVM. Tốt nhất tránh tự thay implementation của backend nếu một Handler/Appender chuẩn đã đáp ứng yêu cầu.

## 13. Console Appender của Log4j 2

Log4j Core cung cấp **Console Appender**. Ví dụ **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level [%t] %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

- **target=SYSTEM_OUT** chọn stdout; có thể dùng **SYSTEM_ERR** nếu cần.
- **PatternLayout** định dạng timestamp, level, thread name, logger name và message.
- **Root level=info** lọc mức DEBUG/TRACE.
- Đây là cấu hình Logger/Appender của Log4j 2, **không phải JUL ConsoleHandler**.
- Các sự kiện từ nhiều thread được backend nhận nhưng vẫn có thể xuất theo thứ tự khác nhau giữa các lần chạy.
- Nếu dùng AsyncLogger/AsyncAppender, cần hiểu hàng đợi và flushing/shutdown của Log4j 2.

**Không cố dùng synchronized trong code nghiệp vụ quanh mỗi lời gọi log** nếu backend đã quản lý writing và khóa của mình. Lock của bạn không tự đồng bộ Appender khác, còn có thể gây contention.

## 14. Console Appender của Logback

Ứng dụng dùng **SLF4J + Logback** có thể khai báo **logback.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Đặc điểm:

- ConsoleAppender nhận LogEvent và ghi tới stream được chọn.
- **Encoder** tạo format; không dùng cú pháp **PatternLayout** của Log4j 2 cho Logback.
- Nhờ cách gọi API thống nhất của SLF4J, nhiều module có thể dùng chung cấu hình.
- Nếu ứng dụng có nhiều provider SLF4J, cần giải quyết xung đột dependency trước.
- **MDC** và thread name có thể làm log nhiều thread dễ đọc, nhưng phải cấu hình pattern/encoder phù hợp.

**SLF4J là facade**, còn Logback/Log4j 2 là các backend có trách nhiệm thực thi output. Không xem việc gọi LoggerFactory là đủ để có một console writer nếu runtime chưa có provider.

## 15. Synchronous và asynchronous logging

**Synchronous logging** thường khiến thread gọi logger tham gia đường định dạng/ghi của Appender, và có thể chờ output. **Asynchronous logging** đặt event vào queue/ring buffer rồi để worker thread xử lý sau.

| Khía cạnh | Synchronous | Asynchronous |
| --- | --- | --- |
| Chi phí trong thread nghiệp vụ | Có thể bị ảnh hưởng bởi console I/O | Thường nhỏ hơn khi queue còn chỗ |
| Nơi thực hiện I/O | Đường xử lý đồng bộ của backend | Worker riêng |
| Queue | Có thể không cần | Cần và phải quản trị |
| Khi console chậm | Thread gọi có thể chậm | Queue tăng, sau đó block/drop/fallback |
| Shutdown | Ít bước drain hơn | Cần drain và dừng worker |
| Lỗi output | Có thể gần thread gọi hơn | Có thể được báo trễ |
| Thứ tự giữa nhiều producer | Theo thực tế lập lịch | Theo thứ tự enqueue và cách backend xử lý |
| Đảm bảo không mất log | Không mặc định | Không mặc định |

Log4j 2 có **AsyncLogger** và **AsyncAppender**, còn Logback có **AsyncAppender**. Chúng có cách xử lý queue, mức log và lỗi riêng; không lấy chính sách của backend này gán cho backend khác.

**Queue đầy:** có thể chặn producer, đổi đường xử lý hoặc bỏ event theo chính sách. Nếu log liên quan bảo mật, kiểm toán hoặc giao dịch quan trọng, phải xác định rõ có được phép discard không.

**Mutable arguments:** một LogEvent có thể được format sau khi method logging trả về. Không sửa những object mutable được gắn làm message/context theo cách không có snapshot hoặc hợp đồng thread-safety.

**Một worker writer giúp tuần tự hóa đường output của chính nó**, không có nghĩa nó sẽ giữ đúng thứ tự nhân quả của toàn bộ hệ phân tán.

## 16. Flush không đồng nghĩa synchronized

Một lỗi thường thấy là thêm **System.out.flush()** để tránh log bị trộn:

~~~java
System.out.print("INFO | ");
System.out.flush();
System.out.println("event=started");
~~~

Đây là snippet minh họa **cách hiểu sai**. Flush chỉ yêu cầu đẩy dữ liệu đã đệm xuống tầng dưới; thread khác vẫn có thể ghi giữa print và println.

Phân biệt:

- **Atomicity:** bản ghi có thể bị chen vào giữa hay không.
- **Flushing:** dữ liệu còn trong buffer Java/backend hay đã được đẩy xuống stream bên dưới.
- **Ordering:** bản ghi nào được enqueue, format hoặc ghi trước.
- **Durability:** collector/đích có giữ được dữ liệu sau crash hay không.

Một PrintStream có thể bật autoFlush trong một số điều kiện như println, nhưng **không nên suy ra rằng tất cả terminal, pipe, collector và log store đã đồng bộ trên ổ đĩa**.

JUL **ConsoleHandler** flush theo cơ chế của nó. JUL **StreamHandler** có **flush()** riêng và **close()** có thể đóng OutputStream, nên cẩn thận khi truyền System.out vào StreamHandler tự tạo.

Một logger có thể ghi đúng và flush thành công nhưng log collector vẫn mất bản ghi do pipe đóng, hàng đợi collector quá tải hoặc mất kết nối. Nếu có yêu cầu durability, phải giám sát pipeline và thiết kế retry/lưu trữ phù hợp.

## 17. Stack trace nhiều dòng và đồng bộ output

Khi một exception xảy ra, log có thể chứa nhiều dòng:

~~~text
ERROR | event=order.persist.failed requestId=req-42
java.lang.IllegalStateException: storage unavailable
    at example.OrderService.save(OrderService.java:42)
Caused by: java.io.IOException: connection reset
    at example.StorageClient.write(StorageClient.java:27)
~~~

Đây là **stack trace minh họa**, không phải kết quả của một lần chạy chương trình thật. Nếu một Formatter tự in từng frame bằng những thao tác riêng không được đồng bộ, thread khác có thể chen giữa các frame.

**Thực hành tốt:**

1. Truyền **Throwable** đúng API, ví dụ JUL **logger.log(Level.SEVERE, message, ex)**, hoặc SLF4J/Log4j 2 **LOG.error("event=order.failed id={}", id, ex)**.
2. Để Formatter/Encoder có hỗ trợ exception tạo một event nhất quán.
3. Nếu collector coi mỗi dòng là một log event, cấu hình **multiline parsing** hoặc structured exception fields.
4. Nếu JSON chứa newline, phải **escape** đúng để không tạo nhiều bản ghi sai.
5. Tránh **log cùng Throwable ở mọi tầng rồi rethrow**, vì một sự cố bị đếm thành nhiều lỗi.
6. Thử đồng thời nhiều exception và xác minh collector không trộn cause chain của hai request.
7. Bổ sung requestId/thread/service cho mỗi event để điều tra dễ hơn.

**Đồng bộ output trong JVM** và **gộp stack trace tại collector** là hai bài toán riêng. Đừng dùng kết quả nhìn thấy trên terminal để suy ra parser của log platform sẽ nhận đúng.

## 18. Thứ tự log và correlation context

Một trường hợp nhiều request:

~~~text
INFO | worker=A | requestId=req-10 | event=order.started
INFO | worker=B | requestId=req-11 | event=order.started
INFO | worker=B | requestId=req-11 | event=order.completed
INFO | worker=A | requestId=req-10 | event=order.completed
~~~

Bốn dòng trên **không bị trộn**, nhưng chúng xen kẽ theo thời gian xử lý độc lập. Đây là kết quả concurrency bình thường.

Thông tin hữu ích:

| Trường | Mục tiêu |
| --- | --- |
| timestamp | Thời điểm gần đúng của event |
| level | INFO/WARN/ERROR hoặc hệ mức của backend |
| service/instance | Nguồn trong hệ nhiều process |
| thread | Thread phát sinh sự kiện |
| requestId/jobId | Liên kết các dòng thuộc cùng luồng nghiệp vụ |
| traceId/spanId | Nối với distributed tracing khi đã tích hợp |
| event | Tên hành vi ổn định |
| outcome/reasonCode | Kết quả hoặc nguyên nhân nghiệp vụ |
| sequence | Thứ tự trong phạm vi được định nghĩa rõ |

**Timestamp không tự là total order** giữa nhiều máy do sai số đồng hồ, việc format/queue trễ và ingestion. Sequence number cũng chỉ có ý nghĩa trong phạm vi do hệ thống cấp phát; sequence ở mỗi process không tự tạo thứ tự toàn hệ thống.

Trong framework dùng SLF4J, **MDC** có thể gắn requestId:

~~~java
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", requestId)) {
    LOG.info("event=order.accepted orderId={}", orderId);
}
~~~

Đây là snippet, giả định biến đã có. MDC thường gắn với context trên thread và **không tự truyền qua mọi thread pool/CompletableFuture hoặc dịch vụ**. Nếu dùng thread pool, cần truyền context rõ ràng và dọn sau request để log của request B không mang ID request A.

**Đồng bộ output** giữ dòng nguyên vẹn; **correlation** giúp xác định quan hệ giữa các dòng. Cả hai cần có khi hệ thống xử lý concurrent.

## 19. Khi nhiều process/container cùng ghi log

Một **synchronized lock** của Java chỉ áp dụng trong **một JVM**. Nó không thể áp đặt thứ tự lên hai JVM, hai container hoặc các process khác.

Trong môi trường thực:

- Nhiều process có thể cùng ghi lên terminal hoặc pipe; độ nguyên tử của thao tác write phụ thuộc OS và cách thư viện thực sự ghi bytes.
- Với pipe POSIX, khái niệm **PIPE_BUF** giới hạn một số bảo đảm ghi nguyên tử, nhưng không chứng minh một LogEvent Java luôn tương ứng đúng một system call.
- stdout và stderr thường được collector thu thập riêng và merge theo timestamp hoặc ingestion time.
- Container có thể bị kill trước khi async queue drain hoặc collector nhận hết.
- Những dòng log quá dài có thể bị runtime chia hoặc cắt theo giới hạn platform.
- Một service với nhiều replica không có một queue/writer chung trên toàn cụm.
- Nếu xuất cùng event ra file và console rồi collector nhận cả hai, có thể có duplicate event.
- Không bảo đảm thứ tự toàn cục chỉ bằng việc mỗi JVM đã synchronized.

**Đừng dùng thứ tự console text làm protocol phối hợp nghiệp vụ.** Nếu yêu cầu “A phải commit trước B”, dùng transaction, queue, lock/coordination cấp hệ thống hoặc cơ chế event có sequence/offset đáng tin cậy, rồi ghi log để quan sát.

## 20. Hiệu năng, lock contention và bảo mật

Console logging có thể trở thành điểm nghẽn nếu hàng nghìn thread cùng ghi:

- Một lock chung có thể khiến thread nghiệp vụ chờ nhau.
- Console/collector có thể chậm, làm kéo dài thời gian giữ lock.
- Logging quá chi tiết trong vòng lặp làm tăng I/O, object allocation và GC.
- Async queue giảm độ trễ ngắn hạn nhưng sẽ đầy nếu tốc độ tạo event liên tục lớn hơn tốc độ ghi.
- Một queue không giới hạn có thể ăn hết RAM; dùng bounded queue và chính sách phù hợp.
- Stack trace và structured JSON lớn làm tăng chi phí format và ingest.
- Filter/Formatter tự viết không thread-safe có thể tạo lỗi dữ liệu khó tái hiện.
- Tạo quá nhiều Logger/Appender/Handler cho từng request có thể tạo contention và duplicate.

Ngoài concurrency còn có bảo mật:

1. **Không log token, mật khẩu, cookie, private key, dữ liệu thẻ** hoặc payload người dùng không cần thiết.
2. Input có newline/control character có thể gây **log injection**; cần escaping và formatter thích hợp.
3. Console log thường được nền tảng thu thập, có thể giữ trong kho lâu hơn mong đợi.
4. Quản lý **retention**, quyền truy cập, backup và khả năng xóa theo chính sách.
5. Không dùng đường log làm nơi chứa mọi thông tin debug khi chỉ cần metric tổng hợp.
6. Dùng eventName ổn định và context ID phù hợp thay vì in toàn bộ object.
7. Nếu có yêu cầu audit, không mặc định async queue hoặc console output đã có độ bền và toàn vẹn cần thiết.

**Hãy benchmark trên hệ thống thật** trước khi chuyển tất cả synchronous logger sang async. Log volume, mức tải, giới hạn queue, p95/p99 latency và collector lag quan trọng hơn giả định “async luôn nhanh”.

## 21. Kiểm thử đồng bộ output

Một test concurrency không nên assert những thứ không có bảo đảm.

**Test tính nguyên vẹn bản ghi:**

- Mỗi thread phát eventId hoặc workerId/sequence riêng.
- Dùng nhiều thread và một số lượng event biết trước.
- Kiểm tra từng dòng đều có prefix/body của **một event duy nhất**.
- Kiểm tra số event không thiếu/trùng trong điều kiện policy không chủ động discard.
- Thử Unicode tiếng Việt, message dài, exception multiline và output có nhiều ký tự điều khiển.
- Thử các trường hợp nhiều Logger/Handler/Appender.

**Test ordering:**

- Nếu không có happens-before, chỉ assert **tập các event** hoặc thứ tự riêng trong từng producer khi được bảo đảm, không assert toàn thứ tự thread A/B.
- Nếu cần thứ tự xác định, dùng **CountDownLatch**, Future, join hoặc sequence protocol.
- Đừng dùng **Thread.sleep(...)** làm phương pháp chính tạo thứ tự; nó không bảo đảm scheduler chạy đúng theo dự đoán.
- Với async, chờ backend **shutdown/drain** đúng API trước khi so khớp output.

**Test stdout và stderr:**

- Capture hai stream riêng để biết nơi event thật sự được xuất.
- Cẩn thận với **System.setOut/System.setErr** trong unit test chạy song song vì đây là trạng thái toàn JVM.
- Xác minh hành vi khi collector merge stream, vì nó có thể làm thứ tự quan sát khác thứ tự gọi trong code.
- Với JUL, nhớ ConsoleHandler thường ghi stderr; với Log4j/Logback, xác minh target cấu hình.

**Test failure/backpressure:**

- Thử queue đầy, consumer dừng, thread bị interrupt và shutdown.
- Kiểm tra metrics về log dropped hoặc output errors.
- Đo throughput/latency khi console chậm, thay vì chỉ nhìn log đúng trong điều kiện ít traffic.

Demo ConsoleOutputSyncDemo ở mục 9 có expected stdout xác định vì các latch thiết lập quan hệ thứ tự. Điều này **không chứng minh** mọi chương trình concurrent đều có thứ tự cố định.

## 22. Những vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Hai message dính chung một dòng | Ghép message bằng nhiều lệnh print | Tạo thông điệp hoàn chỉnh, một writer hoặc lock chung |
| Prefix thread A, phần cuối thread B | Hai thao tác ghi xen nhau | Khóa toàn bộ block hoặc dùng queue |
| Các dòng nguyên vẹn nhưng thứ tự đổi | Scheduler khác nhau | Dùng context ID; áp happens-before nếu thực sự cần |
| Log stdout/stderr đảo thứ tự | Hai stream được collector merge | Kiểm tra riêng từng stream |
| Logger log hai lần | Handler cha/con, additivity, nhiều provider | Kiểm tra đường Appender/Handler |
| Stack trace bị tách thành nhiều event | Collector thiếu multiline handling | Dùng multiline parser/structured exception |
| Writer thread bị kẹt | Console chậm hoặc queue/lock deadlock | Đo contention, backpressure và shutdown |
| Queue tăng RAM | Unbounded queue và writer chậm | Bounded queue, metrics, overflow policy |
| Log cuối biến mất khi dừng | Async queue chưa drain hoặc stream chưa flush | Shutdown backend theo API và giám sát |
| Test bất ổn | Assert ordering không có quan hệ đồng bộ | Dùng latch/join/Future hoặc sửa expectation |
| RequestId bị lẫn giữa request | MDC/ThreadLocal không dọn | Context propagation và cleanup |
| Đã flush nhưng collector không thấy | Flush không bảo đảm delivery | Kiểm tra pipe/collector/retention |
| Tiếng Việt sai dấu | Charset bị lệch | Đồng nhất UTF-8 đầu-cuối |
| Formatter tự viết ra sai dữ liệu | Mutable state không thread-safe | Thiết kế stateless hoặc đồng bộ đúng |
| Log có thông tin bí mật | In payload/exceptions thô | Giảm dữ liệu và escaping |

**Quy trình điều tra:** xác định stream → xác định backend → xem số writer và cách format → xem lock/queue → đánh giá yêu cầu ordering → kiểm tra collector/multiline → đọc metrics/errors.

## 23. Những nhầm lẫn cần tránh

**1. “Có synchronized là event B sẽ đến sau A.”** Không. Lock loại cạnh tranh đồng thời nhưng không quy định thread nào lấy lock trước.

**2. “Mỗi println là một transaction gồm mọi dòng.”** Không. Một message nhiều dòng hoặc nhiều lời gọi cần cơ chế phối hợp khác.

**3. “System.out và System.err là cùng một stream.”** Không. Chúng có thể cùng màn hình nhưng được thu thập/merge riêng.

**4. “Thêm System.out.flush() giải quyết interleaving.”** Không. Flush chỉ xả buffer.

**5. “Async logging không bao giờ mất log.”** Không. Queue đầy, process kill hoặc lỗi collector có thể gây mất bản ghi.

**6. “Các dòng phải đúng thứ tự start thread.”** Không. Start không tạo lịch ghi console cố định giữa các thread.

**7. “Logger thread-safe nghĩa mọi Formatter custom cũng thread-safe.”** Không. State của Formatter/Handler custom cần được quản lý riêng.

**8. “Một lock bảo vệ mọi thư viện in console.”** Không. Chỉ những bên cùng lock mới phối hợp.

**9. “Timestamp luôn thể hiện thứ tự chính xác toàn hệ thống.”** Không. Có clock skew, buffering và delayed ingest.

**10. “Stack trace nhiều dòng luôn được collector nhận như một record.”** Không. Phải hỗ trợ multiline hoặc structured logging.

**11. “Không thấy exception trong log là do synchronized.”** Có thể Formatter đã bỏ Throwable hoặc filter/level chặn.

**12. “Console log không cần bảo mật.”** Không. Nó thường được collector lưu và nhiều người truy cập; cần data minimization và phân quyền.

## 24. Checklist triển khai

1. Xác định **đơn vị cần bảo vệ**: một dòng, một LogEvent hay một stack trace nhiều dòng.
2. Xác định **đích thực tế**: stdout, stderr hoặc hai stream.
3. Chọn **một logging backend chính**, tránh PrintStream trực tiếp và nhiều provider không cần thiết.
4. Xây **event hoàn chỉnh** trước khi xuất; nếu phải in nhiều lần, dùng lock chung hoặc writer duy nhất.
5. Nếu dùng **synchronized**, bảo đảm mọi writer liên quan thực sự cùng lock.
6. Nếu dùng **BlockingQueue**, chọn bounded capacity, overflow/backpressure, shutdown và error handling.
7. Nếu cần thứ tự, thiết lập **happens-before/sequence** ở nơi sự kiện được tạo/enqueue.
8. Thêm requestId/jobId/thread/service; truyền context qua thread pool và dọn MDC.
9. Bảo đảm Formatter/Encoder có xử lý Throwable và multiline đúng.
10. Hiểu **flush khác delivery/durability**; kiểm tra collector và shutdown.
11. Kiểm tra duplicate do Logger hierarchy, Handler và additivity.
12. Test với nhiều thread, nhiều stream, output dài và môi trường container thật.
13. Giảm volume, đo contention, queue depth, p95/p99 và dropped events.
14. Không log bí mật; thống nhất charset, escaping, retention và phân quyền.

**Kết luận:** **Đồng bộ output** trong console logging giữ mỗi bản ghi rõ ràng khi nhiều thread cùng phát sự kiện. Nhưng **atomicity**, **ordering**, **flushing** và **durability** là những yêu cầu khác nhau. Với demo đơn giản, một println cho cả thông điệp thường là đủ; với hệ thống production, nên dùng **Console Appender/Handler được backend quản lý** hoặc **một pipeline writer/queue có chính sách rõ ràng**, và dùng correlation ID thay vì dựa vào thứ tự hiển thị của log.

## 25. Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): println, autoFlush và checkError.
- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): API Logger được dùng trong nhiều thread.
- [Oracle Java SE 17 — ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): xuất System.err và vòng đời Handler.
- [Oracle Java SE 17 — StreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html): Formatter, publish, flush và close.
- [Oracle Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp happens-before giữa thread.
- [Oracle Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): queue đa thread.
- [Apache Log4j 2 — Console Appender](https://logging.apache.org/log4j/2.x/manual/appenders/console.html): target và Layout.
- [Apache Log4j 2 — Asynchronous logging](https://logging.apache.org/log4j/2.x/manual/async.html): trade-off của async logger/queue.
- [Logback — ConsoleAppender](https://logback.qos.ch/manual/appenders-console-file.html): console target, encoder và hành vi output.
