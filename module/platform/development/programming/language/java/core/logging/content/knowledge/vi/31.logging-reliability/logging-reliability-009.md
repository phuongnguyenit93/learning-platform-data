# Shutdown hook và độ tin cậy logging trong Java

## 1. Shutdown hook là gì và vì sao logging cần nó?

**Shutdown hook** là một `Thread` được đăng ký với JVM qua `Runtime.getRuntime().addShutdownHook(...)`. Khi JVM bắt đầu **quá trình shutdown có trật tự**, nó khởi chạy các hook đã đăng ký để ứng dụng có cơ hội dọn dẹp: ngừng nhận việc mới, xử lý dữ liệu đang chờ, đóng kết nối và **flush/close các thành phần logging**.

Trong hệ thống logging, một lời gọi như `logger.info("order created")` không phải lúc nào cũng đồng nghĩa dòng đó đã nằm an toàn trong file hoặc kho log từ xa. Tùy backend, dữ liệu có thể đang ở:

- Bộ đệm của handler/appender hoặc encoder.
- Hàng đợi của **asynchronous logging**, chưa đến lượt worker ghi.
- Bộ đệm I/O, socket hoặc kênh gửi qua mạng.
- Bộ nhớ của log collector trước khi được lưu bền vững.

Vì vậy, một shutdown hook có thể là **lớp bảo vệ cuối cùng trong quá trình tắt có kiểm soát**: yêu cầu ngừng tạo event mới, chờ một khoảng hợp lý cho queue thoát hết, flush và đóng các tài nguyên còn mở. Tuy nhiên, hook **không biến logging thành giao dịch bền vững** và không thay thế các cơ chế bảo đảm độ tin cậy trong quá trình chạy.

### Hai điểm phải phân biệt

1. **Graceful shutdown:** JVM có cơ hội chạy hook; hệ thống logging có thể hoàn tất những thao tác đang chờ nếu đủ thời gian và tài nguyên.
2. **Abrupt termination:** JVM hoặc máy chủ bị kết thúc đột ngột; hook có thể **không chạy**, và log đang ở buffer/queue có thể mất.

Mục tiêu của bài là dùng hook đúng lúc, tránh giả định quá mức về khả năng cứu log và thiết kế quy trình tắt ứng dụng có thể kiểm chứng.

## 2. Khi nào shutdown hook được chạy?

JVM bắt đầu shutdown có trật tự trong các tình huống điển hình sau:

- Không còn thread không phải daemon nào đang chạy, nên JVM kết thúc bình thường.
- Ứng dụng gọi `System.exit(status)` (nếu lệnh thực sự bắt đầu shutdown).
- Một số tín hiệu kết thúc do hệ điều hành gửi, ví dụ `SIGTERM` trên nền tảng/JVM có xử lý tín hiệu đó để bắt đầu shutdown.

Khi shutdown bắt đầu, các hook đã đăng ký được **khởi chạy đồng thời**, theo **thứ tự không được bảo đảm**. JVM chờ các hook kết thúc để hoàn tất chu trình shutdown có trật tự.

Không được cho rằng hook sẽ chạy trong các trường hợp như:

- `SIGKILL` (`kill -9`) trên hệ điều hành tương ứng.
- `Runtime.getRuntime().halt(...)`, vốn bỏ qua trình tự shutdown thông thường.
- Mất điện, máy chủ chết, tiến trình bị hủy cưỡng bức hoặc một số lỗi nghiêm trọng của JVM.
- Container bị nền tảng ép dừng sau khi hết thời gian ân hạn.

**Hệ quả:** shutdown hook là cơ chế *best effort* trong những lần JVM có thể tắt đúng quy trình, **không phải bảo đảm mọi sự kiện log sẽ tồn tại sau bất kỳ loại sự cố nào**.

### Vòng đời của một hook

~~~text
RUNNING
   |
   | JVM bat dau orderly shutdown
   v
START SHUTDOWN HOOKS (khong dam bao thu tu)
   |                 |
   |                 +--> Hook cho database / service khac
   |
   +--> Logging hook
           |
           +--> Khong tao log event moi neu khong can
           +--> Cho worker/queue theo gioi han thoi gian
           +--> Flush buffer va close appender/handler
           |
           v
      HOOK FINISHED
   |
   v
JVM hoan tat shutdown (neu khong bi cuong buc)
~~~

Một `Thread` làm hook phải ở trạng thái **chưa được start** khi đăng ký. Không tự gọi `start()` cho thread đó trước, không đăng ký lại cùng đối tượng thread nhiều lần, và không dựa vào thứ tự thực thi giữa các hook. Khi shutdown đã bắt đầu, các thao tác đăng ký/hủy đăng ký hook có thể bị từ chối với `IllegalStateException`.

## 3. Ví dụ Java 17 độc lập: flush log khi JVM kết thúc

Để thấy rõ khác biệt giữa **tạo log event** và **ghi dữ liệu ra file**, ví dụ dưới đây cố ý dùng một `Handler` đơn giản lưu các message vào bộ đệm `StringBuilder`. Khi JVM shutdown, hook gọi `close()`, khiến handler ghi phần còn lại ra file.

Đây là ví dụ học tập về vòng đời logging; **không dùng handler tự viết này làm production logging backend**. Các backend thực tế thường đã có cơ chế buffering, flush và lifecycle riêng. Ví dụ vẫn dùng API chuẩn `java.util.logging` (JUL), chạy với **JDK 17 trở lên** mà không cần dependency khác.

Tạo tệp **`ShutdownHookLoggingDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ShutdownHookLoggingDemo {

    private static final class BufferedHandler extends Handler {
        private final Path target;
        private final StringBuilder pending = new StringBuilder();
        private boolean closed;

        BufferedHandler(Path target) {
            this.target = target;
            setLevel(Level.ALL);
        }

        @Override
        public synchronized void publish(LogRecord record) {
            if (closed || !isLoggable(record)) {
                return;
            }
            pending.append(record.getLevel().getName())
                    .append(": ")
                    .append(record.getMessage())
                    .append(System.lineSeparator());
        }

        @Override
        public synchronized void flush() {
            if (closed || pending.length() == 0) {
                return;
            }
            try {
                Files.writeString(
                        target,
                        pending.toString(),
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND);
                pending.setLength(0);
            } catch (IOException ex) {
                // Tranh goi nguoc vao logger trong luc shutdown.
                System.err.println("Log flush failed: " + ex.getMessage());
            }
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            flush();
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        Path output = Path.of("logs", "shutdown-hook.log");

        if (args.length == 1 && "verify".equals(args[0])) {
            Files.readAllLines(output, StandardCharsets.UTF_8)
                    .forEach(System.out::println);
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException("Usage: [verify]");
        }

        Files.createDirectories(output.getParent());
        Files.deleteIfExists(output);

        BufferedHandler handler = new BufferedHandler(output);
        Logger logger = Logger.getLogger("demo.shutdown.hook");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(handler);

        Runtime.getRuntime().addShutdownHook(
                new Thread(handler::close, "logging-shutdown-hook"));

        logger.info("service started");
        logger.warning("work pending");

        System.out.println("main finished");
        // JVM ket thuc binh thuong, hook flush bo dem.
    }
}
~~~

Biên dịch và chạy trong thư mục được phép tạo file:

~~~bash
javac ShutdownHookLoggingDemo.java
java ShutdownHookLoggingDemo
java ShutdownHookLoggingDemo verify
~~~

**Kết quả stdout ở lần chạy thứ nhất:**

~~~text
main finished
~~~

**Kết quả stdout ở lần chạy thứ hai** (`verify` đọc file sau khi JVM thứ nhất đã kết thúc):

~~~text
INFO: service started
WARNING: work pending
~~~

Tệp được tạo ở đường dẫn tương đối **`logs/shutdown-hook.log`**, tính từ working directory của tiến trình. Trong điều kiện thư mục có quyền ghi và shutdown bình thường, file chứa hai dòng như ở lần `verify`. Nếu không ghi được file, ví dụ sẽ báo lỗi trên stderr; khi đó không thể coi việc flush thành công.

### Giải thích chương trình

- `publish()` **chỉ thêm message vào bộ đệm**, chưa ghi ngay ra file. Vì vậy lời gọi `logger.info` thành công không đồng nghĩa file đã tồn tại.
- `BufferedHandler.flush()` ghi phần còn lại bằng `Files.writeString` rồi xóa bộ đệm nếu ghi thành công. Đây là thao tác ghi file thật, không phải một lời gọi `System.out`.
- `close()` gọi `flush()` rồi đánh dấu `closed`; gọi lại `close()` không tạo thêm bản ghi. **Tính idempotent** quan trọng vì nhiều thành phần quản lý vòng đời có thể cùng cố đóng handler.
- `synchronized` bảo vệ trạng thái `pending` và `closed` khi có lời gọi từ thread ghi log và thread shutdown. Nó không biến mọi file I/O thành an toàn tuyệt đối.
- Hook chỉ gọi **`handler.close()`**, không đi qua API logger để tránh tạo log mới trong lúc logging system đang đóng.
- Chế độ `verify` chạy bằng **một JVM mới** để đọc kết quả sau khi JVM cũ đã thoát; không có hook hay handler nào được đăng ký ở nhánh này.

**Giới hạn đáng lưu ý:** JUL có cơ chế shutdown nội bộ để đóng các handler thuộc `LogManager`. Trong một chương trình có dùng `Logger`, shutdown của JUL và hook tùy biến có thể cùng gọi `close()` theo thứ tự bất kỳ. Code trên cố ý thiết kế `close()` lặp lại an toàn, do đó file vẫn được ghi một lần trong tình huống bình thường. Ví dụ chứng minh **cách chuẩn bị cleanup ở thời điểm shutdown**, chứ không chứng minh rằng JUL cần một hook tùy biến để ghi được bất kỳ log nào.

## 4. Flush, close và độ bền dữ liệu không giống nhau

Ba khái niệm thường bị đánh đồng:

| Hành động | Ý nghĩa chính | Điều không nên suy ra |
| --- | --- | --- |
| **Flush** | Đẩy dữ liệu đang đệm xuống tầng đầu ra kế tiếp | Không bảo đảm dữ liệu đã được lưu bền vững trên thiết bị hoặc remote |
| **Close** | Kết thúc vòng đời tài nguyên; thường flush rồi đóng stream/socket/worker theo hợp đồng của thành phần | Không bảo đảm tất cả dữ liệu mạng đã đến đích hoặc mọi lỗi đã được xử lý |
| **Durability/acknowledgment** | Xác định dữ liệu được hệ thống lưu giữ theo một chính sách cụ thể | Không thể suy từ riêng lời gọi `logger.info` hay `close` |

Một backend bất đồng bộ có thể đặt event vào queue rồi trả về ngay. Hook gọi flush/stop có thể giúp worker chuyển dữ liệu từ queue sang file. Nhưng dữ liệu cũng có thể còn trong cache hệ điều hành, mạng đang gián đoạn hoặc collector chỉ nhận tạm thời rồi mới lưu.

Nếu log mang yêu cầu pháp lý hoặc tài chính về tính toàn vẹn, cần kiến trúc lưu trữ/ghi nhận riêng: xác định hệ thống nhận, cơ chế acknowledgment, lưu bền vững, retry, chống trùng và giám sát. **Không dùng shutdown hook làm bảo đảm duy nhất cho audit trail quan trọng.**

## 5. Thiết kế shutdown hook đúng cách

Một hook tốt thường có các đặc điểm sau:

1. **Đăng ký một lần**, khi tài nguyên logging đã sẵn sàng và trước thời điểm hệ thống có thể cần shutdown.
2. **Ngắn gọn, có giới hạn:** chỉ làm các thao tác đóng cần thiết; nếu phải chờ worker hoặc exporter, sử dụng timeout phù hợp.
3. **Idempotent:** cleanup gọi hai lần không làm hỏng trạng thái, không sinh log trùng và không cố dùng một tài nguyên đã đóng.
4. **Không sinh thêm log qua backend đang đóng:** khi cần thông báo lỗi cleanup, cân nhắc kênh chẩn đoán tối giản như `System.err` tùy ngữ cảnh.
5. **Bắt lỗi cục bộ:** ghi nhận IOException/InterruptedException thích hợp, tránh lỗi ở một bước khiến toàn bộ tài nguyên còn lại không được dọn.
6. **Không phụ thuộc thứ tự hook:** hook của logging không được giả định sẽ chạy sau mọi hook database, HTTP server hoặc scheduler.
7. **Không vô hạn chờ:** trong container hoặc service manager, nền tảng có thể cưỡng bức dừng khi vượt thời hạn.

Nếu ứng dụng cần ngừng xử lý request trước khi đóng logging, thiết kế lifecycle chủ động sẽ tốt hơn:

~~~text
Receive shutdown request
        |
        v
Stop accepting new work
        |
        v
Wait for in-flight work (bounded)
        |
        v
Stop producing new log events
        |
        v
Drain async logging queue
        |
        v
Flush/close logging backend
        |
        v
Exit process
~~~

Đây là **thứ tự mong muốn do bộ điều phối vòng đời ứng dụng quản lý**, không phải thứ tự tự động mà JVM áp đặt lên các shutdown hook. Nếu chỉ đăng ký nhiều hook riêng lẻ và hy vọng JVM chạy chúng lần lượt theo thứ tự, thiết kế có thể gặp race condition.

### Những điều không nên làm trong hook

- Không gọi `System.exit(...)` từ chính shutdown hook: JVM đã đang shutdown, lời gọi này có thể gây chờ không kết thúc.
- Không chờ vô thời hạn một thread đang giữ lock hoặc đang chờ chính hook hoàn thành.
- Không mở thêm một chuỗi logging/backend mới trong lúc phần còn lại đang đóng.
- Không làm tác vụ mạng dài không có timeout và không phụ thuộc vào tín hiệu shutdown lần thứ hai sẽ luôn giúp thoát.
- Không dùng `Thread.sleep` một khoảng cố định như cách “bảo đảm log đã flush”. Ngủ không chứng minh queue đã trống hoặc file đã đóng.

## 6. Async logging: có hook vẫn có thể mất log

Với logging bất đồng bộ, luồng sự kiện thường như sau:

~~~text
Worker thread: logger.info(event)
                      |
                      v
                   Async queue
                      |
                      v
                Background writer
                      |
                      v
              File / socket / collector
~~~

Khi nhận tín hiệu shutdown, vấn đề không chỉ là flush một `OutputStream`, mà còn là **drain các event đang chờ trong queue** và ngăn việc thread khác tiếp tục thêm event mãi mãi.

Các câu hỏi cần trả lời bằng tài liệu backend và bài kiểm thử:

- `stop()` hoặc `close()` có **chờ queue drain** hay chỉ từ chối event mới?
- Khi queue đầy, backend **block, drop hay chuyển sang ghi đồng bộ**?
- Có giới hạn chờ khi tắt không; hết thời hạn thì event còn lại được xử lý thế nào?
- Khi exporter qua mạng thất bại, có retry, timeout hoặc lưu trên đĩa tạm không?
- Hook có thể chạy đồng thời với shutdown của framework/backend khác không?
- Hệ thống thu thập đã xác nhận lưu event hay mới chỉ nhận qua socket?

**Nguyên tắc:** khi backend/framework đã quản lý shutdown logging, hãy ưu tiên cơ chế quản lý sẵn có và cấu hình timeout/queue của nó. Đăng ký thêm một hook gọi `stop()` trùng lặp có thể gây race hoặc đóng backend quá sớm nếu vòng đời không được thiết kế cẩn thận.

## 7. JUL, Logback, Log4j 2: không có một shutdown hook chung

### Java Util Logging (JUL)

Trong ứng dụng chỉ dùng JDK, `java.util.logging.LogManager` thường có cơ chế xử lý khi JVM shutdown để đóng các handler theo vòng đời của JUL. Với các `ConsoleHandler`/`FileHandler` tiêu chuẩn, **không mặc định phải viết thêm hook** chỉ để gọi close. Nếu ứng dụng tự tạo `Handler` và giữ buffer/queue riêng, phải xác định ai sở hữu tài nguyên và ai chịu trách nhiệm kết thúc nó.

Đặc biệt, nếu tạo thêm hook riêng, `LogManager` và hook đó có thể chạy đồng thời. Tài nguyên nên chịu được `close()` lặp lại hoặc có điều phối vòng đời rõ ràng.

### SLF4J với Logback

**SLF4J là facade API**, không chịu trách nhiệm chung cho mọi kiểu shutdown của logging backend. Logback có lifecycle cho logger context và appender; khi chạy trong framework như Spring Boot, framework thường quản lý khởi tạo và dừng logging.

Nếu tự kiểm soát lifecycle trong ứng dụng độc lập, cần dùng API stop/close được backend hỗ trợ thay vì đoán rằng đóng một SLF4J logger sẽ flush queue. **Không có phương thức `close()` chuẩn trên `org.slf4j.Logger`** để thay cho việc quản lý backend.

### Log4j 2

Log4j 2 có quản lý lifecycle và cơ chế shutdown được cấu hình ở backend/context. Với cấu hình async, cần kiểm tra chính sách dừng, timeout và khả năng chờ event đang chờ được xuất.

**Đừng thêm hook chồng lên hệ thống shutdown đã có** nếu không kiểm tra rõ phiên bản, cấu hình và thứ tự đóng. Khi tích hợp Spring Boot, Jakarta application server, container hoặc framework khác, ứng dụng có thể đã được cung cấp vòng đời graceful shutdown; điểm cleanup phù hợp có thể là lifecycle callback của framework chứ không phải hook JVM tự viết.

## 8. Shutdown hook và môi trường triển khai

### Chạy trực tiếp trên máy hoặc service

Trong chương trình CLI thông thường, JVM thoát sau khi thread không phải daemon cuối cùng kết thúc. Hook có thể hoạt động như ví dụ mục 3. Nếu Java chạy dưới service manager, nên kiểm tra cách service dừng tiến trình: hệ thống có gửi tín hiệu cho phép shutdown có trật tự hay chấm dứt cưỡng bức? Thời gian dọn dẹp có bị giới hạn không?

### Docker và Kubernetes

Trong hệ thống container, thông thường nền tảng yêu cầu tiến trình dừng trước rồi mới cưỡng bức kết thúc khi hết thời gian ân hạn. Với Linux/HotSpot, một tín hiệu kết thúc phù hợp như `SIGTERM` thường cho JVM cơ hội chạy hook; **không bảo đảm** nếu tín hiệu không đến được Java, runtime không xử lý như dự kiến hoặc hết thời gian grace.

Một tình huống phổ biến: container khởi chạy qua shell wrapper không chuyển tín hiệu đúng cách, nên Java không nhận yêu cầu dừng như mong đợi. Nên kiểm tra command/entrypoint, xử lý signal của process PID 1 và thời gian shutdown của nền tảng.

Với hệ thống có HTTP request đang xử lý, nên:

1. Rút instance khỏi luồng request mới hoặc ngừng nhận công việc.
2. Cho request đang chạy thời gian kết thúc có giới hạn.
3. Drain và đóng hệ thống logging.
4. Thoát tiến trình trước hạn chót của container/service manager.

Nếu hệ thống bị `SIGKILL` sau timeout, mọi hook còn chạy sẽ không có cơ hội hoàn thành. **Tăng timeout** chỉ hữu ích khi có giám sát và một thời gian chờ hợp lý; nó không bảo đảm dữ liệu sẽ được cứu trong trường hợp host chết.

## 9. Kiểm thử độ tin cậy khi shutdown

Không nên chỉ chạy một lần `System.exit(0)` rồi kết luận logging an toàn. Hãy thiết kế kiểm thử đủ sát hệ thống thực:

| Bài kiểm thử | Điều cần quan sát |
| --- | --- |
| Kết thúc bình thường | Hook chạy, queue được drain, handler/appender đóng |
| Có log ngay trước shutdown | Các event cuối có đến đích không |
| Dừng service/container bằng tín hiệu phù hợp | JVM có nhận tín hiệu và đủ grace time không |
| Backend async queue gần đầy | Event bị block/drop hay còn lại sau khi hết timeout |
| Đích file không ghi được | Lỗi flush có được phát hiện không; mất bao nhiêu event |
| Remote collector chậm hoặc không khả dụng | Timeout, retry và backpressure hoạt động thế nào |
| Có nhiều hook cùng tồn tại | Có phụ thuộc thứ tự hoặc deadlock do lock không |
| Cưỡng bức kill hoặc tắt máy đột ngột | Xác định giới hạn mất log và cơ chế bổ trợ |

**Ví dụ thực hành với code mục 3:** sau khi chạy `java ShutdownHookLoggingDemo`, chỉ chạy `java ShutdownHookLoggingDemo verify` **khi tiến trình thứ nhất đã thoát**. Việc đọc file trong lúc tiến trình đầu tiên vẫn chạy có thể chưa thấy log, vì buffer cố ý chưa được flush. Không xem đó là lỗi của logger; đó là đặc tính được cố ý dùng để minh họa.

Để kiểm thử `SIGKILL`, chỉ làm trong môi trường thử nghiệm cô lập: hành vi dự kiến là hook không chạy; không dùng trường hợp này để suy đoán rằng từng dòng log chắc chắn bị mất hay chắc chắn được giữ vì kết quả còn phụ thuộc backend và thời điểm ghi.

## 10. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Log cuối cùng mất khi JVM thoát | Buffered/async queue chưa flush hoặc chưa dừng | Kiểm tra lifecycle của backend và chính sách drain |
| Hook không chạy | Bị `SIGKILL`, `halt`, crash hoặc không có orderly shutdown | Dùng đường dừng có kiểm soát; thiết kế chịu mất log khi tắt đột ngột |
| Log vẫn thiếu dù hook đã chạy | Hết thời gian grace, đích ghi lỗi, network chưa xác nhận hoặc flush thất bại | Kiểm tra timeout, lỗi I/O và acknowledgment |
| Ứng dụng treo lúc shutdown | Hook chờ vô hạn, lock vòng hoặc worker chưa dừng | Giới hạn thời gian, sửa thứ tự dừng và tránh deadlock |
| Log/exception xuất hiện khi đóng logging | Hook khác vẫn tiếp tục phát event sau khi appender đóng | Điều phối ngừng tạo event trước khi đóng backend |
| Cùng một handler bị đóng nhiều lần | Hook tự viết trùng với cơ chế shutdown framework/JUL | Chỉ định một chủ thể sở hữu lifecycle; làm cleanup idempotent |
| Không thấy thông báo từ hook | Logging backend đã đóng hoặc không còn nhận event | Không phụ thuộc logger để báo lỗi ngay trong cleanup |
| File tồn tại nhưng collector thiếu event | Ghi ra file và chuyển lên collector là hai giai đoạn khác nhau | Giám sát pipeline và cơ chế xác nhận lưu |
| Log shutdown xuất hiện không theo thứ tự | Nhiều hook được khởi chạy đồng thời | Không dựa vào thứ tự hook; dùng ID/timestamp/context |
| Chương trình in xong `main finished` nhưng chưa có file | Bộ đệm chỉ ghi khi close lúc shutdown | Chờ JVM kết thúc rồi kiểm tra đích lưu |

## 11. Checklist trước khi đưa vào production

1. Xác định backend logging thực tế: JUL, Logback, Log4j 2 hoặc backend khác.
2. Kiểm tra backend/framework **đã có cơ chế shutdown hay chưa**, tránh đóng trùng.
3. Xác định event nào được ghi đồng bộ và event nào còn nằm trong queue/buffer.
4. Định nghĩa rõ thứ tự **ngừng nhận việc → kết thúc việc đang chạy → ngừng sinh log → drain → flush/close**.
5. Đặt timeout hợp lý, bảo vệ khỏi chờ vô hạn và kiểm tra tình huống exporter/file lỗi.
6. Bảo đảm cleanup có thể gọi lại mà không sinh bản ghi trùng hoặc lỗi nghiêm trọng.
7. Kiểm tra signal/entrypoint và giới hạn thời gian dừng trên môi trường triển khai.
8. Phân biệt “handler đã đóng” với “log đã được lưu bền vững tại hệ thống cuối”.
9. Có kế hoạch về rủi ro mất log khi kill cưỡng bức, crash hoặc mất điện.
10. Kiểm thử shutdown bình thường lẫn tình huống lỗi, đo lượng event bị mất thực tế.

### Tự kiểm tra kiến thức

**Câu 1.** `logger.info(...)` trả về thành công, liệu file chắc chắn đã có dòng log không?  
**Đáp:** Không. Dữ liệu có thể còn ở buffer hoặc queue.

**Câu 2.** Tại sao không nên đăng ký một hook cho HTTP server và một hook cho logging rồi cho rằng logging sẽ đóng sau HTTP?  
**Đáp:** JVM khởi chạy các hook theo thứ tự không bảo đảm; chúng có thể chạy đồng thời. Cần bộ điều phối vòng đời nếu có yêu cầu thứ tự.

**Câu 3.** Hook có cứu log khi tiến trình nhận `SIGKILL` không?  
**Đáp:** Không. Đó không phải orderly shutdown; phải dự phòng mất dữ liệu trước thời điểm bị kill.

**Câu 4.** `flush()` thành công có luôn nghĩa log đã tới hệ thống tìm kiếm trung tâm?  
**Đáp:** Không. Phải xem ý nghĩa của flush trong từng backend, đường mạng và cơ chế xác nhận ở collector.

**Câu 5.** Khi một framework đã dừng logging đúng vòng đời, có nên thêm hook riêng gọi close một lần nữa không?  
**Đáp:** Không mặc định. Chỉ thêm khi có nhu cầu và hiểu rõ khả năng race, ownership và hợp đồng lifecycle.

**Ghi nhớ:** Shutdown hook giúp dọn dẹp logging **trong những lần JVM có cơ hội tắt có trật tự**. Hãy sử dụng cơ chế shutdown của framework/backend trước, thiết kế đóng/flush có giới hạn và idempotent, điều phối ngừng sinh event trước khi ngừng hệ thống ghi, và luôn coi shutdown hook là biện pháp *best effort* chứ không phải bảo đảm không mất log.