# Định dạng thread trong Java Logging: thread name, thread ID và layout

Trong ứng dụng Java chạy đồng thời, nhiều luồng có thể phát log cùng lúc. **Định dạng thread** là cách đưa thông tin về luồng phát sự kiện — phổ biến nhất là **thread name**, đôi khi thêm **thread ID** — vào output của formatter/layout để người điều tra biết log xuất phát từ luồng nào.

Ví dụ:

```text
2026-11-09T08:15:12.038Z INFO  [http-nio-8080-exec-7] OrderController - request accepted
2026-11-09T08:15:12.041Z DEBUG [order-worker-2] InventoryService - reserve completed
```

Hai dòng trên chỉ là **dữ liệu minh họa**; thời gian, tên thread và lớp phụ thuộc chương trình. Thread metadata đặc biệt hữu ích khi kiểm tra thread pool, tác vụ nền, xử lý nhiều request đồng thời và lỗi race condition. Tuy nhiên, **thread không phải request**: một luồng có thể xử lý nhiều request lần lượt, còn một request có thể chuyển qua nhiều luồng. Vì vậy, thread name cần được kết hợp với `requestId`/`traceId` khi muốn truy dấu nghiệp vụ.

Bài này thuộc nhóm **Formatter và layout**. Mục tiêu là biết cách chèn tên/ID luồng trong JUL, Logback và Log4j 2; hiểu giá trị metadata được lấy tại thời điểm nào; lựa chọn tên thread có ích; kiểm tra output trong trường hợp đa luồng và bất đồng bộ; và tránh nhầm lẫn với MDC hay logger name.

## 1. Thread metadata nằm ở đâu trong một log event?

Một sự kiện logging có thể mang những thông tin:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Timestamp | Thời điểm phát sự kiện | `2026-11-09T08:15:12.038Z` |
| Level | Mức log | `INFO`, `DEBUG`, `WARN` |
| Logger name | Category/lớp phát log | `com.example.order.OrderService` |
| **Thread name** | Tên luồng liên quan đến sự kiện | `order-worker-2` |
| **Thread ID** | Định danh luồng trong JVM | `37` |
| Message | Nội dung sự kiện | `stage=reserved` |
| Throwable | Exception, stack trace nếu có | `IllegalStateException` |
| Context | Correlation ID, trace ID hoặc dữ liệu có cấu trúc | `requestId=req-17` |

Cần tách ba loại tên:

- **Logger name** trả lời: *lớp/category nào phát sự kiện?* Một lớp có thể được gọi từ nhiều thread.
- **Thread name/ID** trả lời: *luồng nào đã thực hiện phần mã phát log?* Một thread pool có thể tái sử dụng cùng thread cho nhiều request.
- **Request ID/trace ID** trả lời: *sự kiện này thuộc yêu cầu hoặc trace nào?* Một yêu cầu có thể qua nhiều thread và nhiều service.

Một formatter/layout tốt thể hiện các trường này riêng biệt. Không đặt tên logger động theo thread, không dùng thread ID thay correlation ID và không suy ra nguyên nhân race condition chỉ từ việc hai dòng có thread name khác nhau.

## 2. Thread name và thread ID khác nhau thế nào?

### Thread name

Java cho phép đọc tên luồng hiện tại:

```java
// Fragment trong một phương thức Java.
String name = Thread.currentThread().getName();
```

Đây là một chuỗi giúp con người nhận diện chức năng của luồng. Ví dụ một thread pool có thể dùng `payment-worker-1`, `payment-worker-2`, trong khi luồng chính thường mang tên `main`. Tên có thể do chương trình, framework hoặc `ThreadFactory` gán và **có thể thay đổi** bằng `setName(...)`. Không giả định tên luồng là duy nhất tuyệt đối, bất biến hoặc được kiểm soát bởi JVM trong mọi ứng dụng.

### Thread ID

Trên Java 17, có thể đọc ID bằng:

```java
// Fragment trên Java 17; id là long.
long id = Thread.currentThread().getId();
```

`Thread.getId()` trả ID của thread trong JVM. Nó không phải PID của tiến trình, không phải ID thread của hệ điều hành theo nghĩa được mọi hệ điều hành cung cấp, và **không phải khóa để nối log xuyên service hoặc qua các lần khởi động JVM**. Trong các phiên bản Java mới hơn có API `threadId()`; nếu dự án cố định Java 17, dùng API được Java 17 hỗ trợ.

**Đối với `java.util.logging.LogRecord`:** JDK 17 cung cấp `getLongThreadID()`, lấy ID của luồng đã phát sự kiện. API `getThreadID()` kiểu `int` đã bị đánh dấu deprecated từ Java 16 vì ID có thể là giá trị tổng hợp; với Java 17 nên ưu tiên `getLongThreadID()`.

```java
// Fragment bên trong Formatter.format(LogRecord record) ở Java 17.
long originThreadId = record.getLongThreadID();
```

ID trong `LogRecord` được gắn với nguồn phát event, không có nghĩa nó trùng ID native của OS. Với Logback và Log4j 2, thread information được lấy theo mô hình log event của backend; dùng conversion word đúng để formatter lấy **metadata của event** thay vì tự đọc thread đang chạy formatter khi xử lý bất đồng bộ.

## 3. Định dạng thread bằng Logback PatternLayout

Trong Logback classic, **`%thread`** và dạng rút gọn **`%t`** là conversion word để in **tên luồng phát sự kiện**. Ví dụ pattern:

```text
%d{HH:mm:ss.SSS} %-5level [thread=%thread] %logger{36} - %msg%n
```

Giải thích:

| Token | Tác dụng |
| --- | --- |
| `%d{HH:mm:ss.SSS}` | Thời gian theo mẫu; ví dụ đơn giản chưa có ngày/múi giờ |
| `%-5level` | Level căn trái với độ rộng tối thiểu 5 |
| `%thread` hoặc `%t` | Tên thread của log event |
| `%logger{36}` | Tên logger với độ dài hiển thị rút gọn khi cần |
| `%msg` | Message đã được formatter xử lý |
| `%n` | Ký tự kết thúc dòng theo môi trường |

### File Logback hoàn chỉnh

Trong dự án đã có **Logback classic** làm backend, tạo `src/main/resources/logback.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [thread=%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là **toàn bộ một file cấu hình Logback**, không phải cấu hình Log4j 2 hay JUL. Code nghiệp vụ có thể tiếp tục khai báo logger SLF4J:

```java
// Fragment trong lớp đã có dependency SLF4J.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
```

`OrderService` là lớp minh họa. Khi `LOG.info(...)` được phát, Logback ghi thread name vào vị trí `%thread` theo cấu hình. **`LoggerFactory.getLogger` không tạo thread**; thread là luồng đang thực thi code phát log.

Ví dụ đầu ra:

```text
08:15:12.038 INFO  [thread=main] com.example.OrderService - application started
08:15:12.041 INFO  [thread=order-worker-1] com.example.OrderService - processing order
```

Các mốc thời gian chỉ minh họa. Pattern này không có timezone; trong production nên dùng timestamp đầy đủ có timezone hoặc structured logging phù hợp bộ thu thập. **Không mặc định Logback hỗ trợ cùng conversion word ID thread `%T` của Log4j 2**: `%thread` của Logback in *tên*, còn nhu cầu *ID* nên dùng cơ chế encoder/converter hoặc structured logging được version/backend đó hỗ trợ.

### Thêm request ID vào pattern Logback

```xml
<!-- Fragment bên trong <encoder> của Logback -->
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] requestId=%X{requestId} %logger{36} - %msg%n</pattern>
```

`%X{requestId}` đọc **MDC**, không phải ID thread. Nếu ứng dụng chưa đưa `requestId` vào MDC, trường có thể trống. Không lấy thread name để thay thế MDC chỉ vì request ID không xuất hiện.

## 4. Định dạng thread với Log4j 2 PatternLayout

Log4j 2 cũng có PatternLayout, nhưng **không nên suy ra mọi conversion word đều giống Logback**.

Các token phổ biến:

- **`%t`** hoặc `%thread`: **thread name** của sự kiện.
- **`%T`**, `%tid` hoặc `%threadId`: **thread ID** của sự kiện.
- **`%X{requestId}`**: giá trị `requestId` trong Thread Context Map, nếu có.
- **`%c`**, `%logger`: tên logger/category.
- **`%p`**, `%level`: mức log.
- **`%m`**, `%msg`: message.
- **`%n`**: newline.

Ví dụ **file `log4j2.xml` hoàn chỉnh**, khi dự án dùng Log4j 2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p [thread=%t tid=%T] requestId=%X{requestId} %c{1} - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

`%t` và `%T` ở đây đọc thread name và ID từ Log4j 2 event. `%X{requestId}` chỉ có dữ liệu nếu MDC/ThreadContext được quản lý đúng cách.

Ví dụ minh họa:

```text
08:15:12.038 INFO  [thread=order-worker-1 tid=37] requestId=req-17 OrderService - order created
```

Giá trị `tid=37` và thời gian chỉ là dữ liệu minh họa; ID thực tế sẽ khác theo JVM và luồng. Không viết unit test so sánh **một con số thread ID cố định** trừ khi chính test khởi tạo mô hình giả để kiểm soát giá trị.

### So sánh nhanh giữa backend

| Nhu cầu | Logback classic | Log4j 2 |
| --- | --- | --- |
| In thread name | `%thread`, `%t` | `%t`, `%thread` |
| In thread ID | Kiểm tra encoder/converter hỗ trợ của phiên bản; không áp dụng máy móc `%T` của Log4j | `%T`, `%tid`, `%threadId` |
| In request ID trong context | `%X{requestId}` (MDC) | `%X{requestId}` (ThreadContext Map) |
| Định dạng message | `%msg` | `%m` hoặc `%msg` |
| Tên logger | `%logger` | `%c` hoặc `%logger` |
| Config XML thường gặp | `logback.xml`, `logback-spring.xml` khi dùng Boot | `log4j2.xml`, `log4j2-spring.xml` khi có tích hợp Boot |

Không mang nguyên `<PatternLayout>` từ Log4j 2 sang XML của Logback, hoặc `<encoder>` Logback sang Log4j. Chúng là hai bộ cấu hình khác nhau dù một số conversion word trùng tên.

## 5. Java Util Logging (JUL): phải hiểu `LogRecord` và Formatter

Trong **JUL** (`java.util.logging`), `SimpleFormatter` hỗ trợ định dạng qua system property `java.util.logging.SimpleFormatter.format`, nhưng danh sách argument của format mặc định **không có trường thread name** để dùng như `%thread` của Logback. Muốn hiển thị thread theo định dạng riêng, có thể viết `java.util.logging.Formatter` và gắn vào `Handler`.

**`LogRecord` của Java 17 cung cấp `getLongThreadID()` nhưng không có getter chuẩn cho thread name.** Điều này đặc biệt quan trọng khi ghi bất đồng bộ:

- ID có thể được đọc từ `record.getLongThreadID()` dù formatter chạy ở thread khác.
- `Thread.currentThread().getName()` trong `Formatter.format` chỉ là tên của **thread đang gọi formatter**, **không luôn là thread đã phát event**.
- Với `ConsoleHandler` đồng bộ trong ví dụ dưới đây, formatter được thực thi cùng đường gọi log, nên có thể đọc tên thread hiện tại để minh họa.
- Nếu đưa event sang queue, trì hoãn format hoặc dùng handler bất đồng bộ, nên **chụp tên thread lúc phát event** vào metadata của record hoặc sử dụng backend có thread-name field của event; không thay bằng tên của worker tiêu thụ queue.

### Ví dụ chạy được với JDK 17

Lưu file **`ThreadFormatDemo.java`** (không có thư viện ngoài JDK):

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThreadFormatDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadFormatDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        String oldName = Thread.currentThread().getName();
        Thread.currentThread().setName("demo-main");

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " [thread="
                        + Thread.currentThread().getName()
                        + "] "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(console);

        try {
            LOG.info("stage=start");

            Thread worker = new Thread(
                    () -> LOG.info("stage=worker-done"),
                    "order-worker-1");

            worker.start();
            worker.join();

            LOG.info("stage=end");
        } finally {
            LOG.removeHandler(console);
            console.close();
            Thread.currentThread().setName(oldName);
        }

        System.out.println("completed=true");
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 ThreadFormatDemo.java
java ThreadFormatDemo
```

**Stderr chính xác từ ba lời gọi JUL của chương trình:**

```text
INFO [thread=demo-main] stage=start
INFO [thread=order-worker-1] stage=worker-done
INFO [thread=demo-main] stage=end
```

**Stdout chính xác:**

```text
completed=true
```

Lệnh `Thread.currentThread().setName("demo-main")` giúp tên main thread **xác định trong ví dụ**; đây không phải khuyến nghị đổi tên thread main tùy tiện trong ứng dụng production. Thread thứ hai được tạo với tên rõ ràng; `join()` đảm bảo nó kết thúc trước lời gọi `stage=end`, nên thứ tự ba log trong ví dụ là có chủ đích.

**Vì sao dùng `LOG.setUseParentHandlers(false)`?** Để tránh các handler cha ghi thêm dòng và làm hỏng output mẫu. Trong ứng dụng thật, propagation tới root handler có thể là cách chuẩn để đưa log vào hệ thống tập trung; không vô hiệu hóa mặc định khi chưa xác định kiến trúc ghi log.

**Giới hạn lớn của ví dụ:** Formatter gọi `Thread.currentThread()`, hợp lý ở đây vì `ConsoleHandler` ghi đồng bộ ngay trên thread phát log. Nếu chuyển sang xử lý bất đồng bộ, formatter có thể ghi tên thread xử lý log thay vì thread nguồn. Khi đó cần snapshot metadata hoặc dùng backend có cơ chế capture thread event riêng.

### Khi chỉ cần thread ID nguồn ở JUL

Java 17 đã có API đọc ID từ `LogRecord`:

```java
// Fragment bên trong Formatter.format(LogRecord record).
long sourceThreadId = record.getLongThreadID();
String idField = "tid=" + sourceThreadId;
```

Đây là fragment, không phải chương trình độc lập. Có thể bổ sung `idField` vào chuỗi formatter để log ID của luồng phát event. Chú ý thread ID **không phải OS TID** và không thay được correlation ID.

### Vì sao không dùng `SimpleFormatter.format` để lấy tên thread?

`java.util.logging.SimpleFormatter.format` sử dụng các vị trí tham số được định nghĩa sẵn cho thời gian, nguồn phát, logger name, level, message và throwable. Nó **không phải** cùng cú pháp PatternLayout của Logback/Log4j 2; viết `%thread` vào system property của JUL không làm tên luồng xuất hiện đúng ý. Khi cần metadata thread theo format riêng, dùng custom Formatter, một encoder tích hợp hoặc chuyển sang hệ logging khác đã thiết kế field đó.

## 6. Đặt tên thread có ích để đọc log

Log có `[thread=pool-1-thread-7]` vẫn hữu ích hơn không có gì, nhưng `[thread=invoice-export-2]` có thể giúp người vận hành nhận diện chức năng nhanh hơn.

Một `ThreadFactory` có thể gán tên khi tạo worker thread:

```java
// Fragment trong phương thức có java.util.concurrent và AtomicInteger.
java.util.concurrent.atomic.AtomicInteger next =
        new java.util.concurrent.atomic.AtomicInteger();

java.util.concurrent.ThreadFactory factory = task ->
        new Thread(task, "invoice-worker-" + next.incrementAndGet());

java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(2, factory);
try {
    // Nộp tác vụ qua pool.submit(...) hoặc pool.execute(...).
} finally {
    pool.shutdown();
}
```

Đây là đoạn minh họa, không phải chương trình chạy độc lập và không có task thực tế được nộp. `shutdown()` chỉ yêu cầu executor không nhận task mới; ứng dụng cần quản lý chờ kết thúc hoặc chính sách hủy nếu nhiệm vụ còn chạy. Với một hệ thống production, có thể bổ sung uncaught-exception handler và quy tắc daemon theo yêu cầu vận hành.

**Quy tắc đặt tên nên áp dụng:**

- Dùng tiền tố phản ánh chức năng: `http-worker-`, `invoice-worker-`, `message-consumer-`.
- Dùng hậu tố chỉ số worker để dễ đọc: `invoice-worker-1`, `invoice-worker-2`.
- Giữ tên ngắn, ổn định, không chứa password, token, địa chỉ email, user ID hoặc dữ liệu riêng tư.
- Không đổi tên thread cho từng request nếu thread được tái sử dụng bởi pool; thay vào đó đưa request ID vào MDC/log event.
- Không giả định một thread name là duy nhất giữa nhiều JVM, container, lần deploy hoặc node.

**Không tự ý đổi tên thread do framework quản lý** nếu framework sử dụng tên cho metrics, điều tra hoặc convention. Có thể cấu hình thread factory/executor ngay tại điểm tạo pool thay vì đổi tên giữa chừng trong một request.

## 7. Thread pool: một thread có thể phục vụ nhiều request

Giả sử một HTTP server tái sử dụng `http-worker-7`:

```text
INFO [http-worker-7] requestId=req-101 event=accepted
INFO [http-worker-7] requestId=req-101 event=completed
INFO [http-worker-7] requestId=req-102 event=accepted
INFO [http-worker-7] requestId=req-102 event=failed
```

Các dòng trên là minh họa. Cả bốn event có thể đến từ **cùng một thread** nhưng **hai request khác nhau**. Nếu chỉ lọc theo thread name, bạn sẽ gom lẫn thông tin của `req-101` và `req-102`.

Ngược lại, một request có thể xử lý bất đồng bộ:

```text
INFO [http-worker-7]   requestId=req-103 event=request-started
INFO [db-worker-2]     requestId=req-103 event=sql-completed
INFO [http-worker-12]  requestId=req-103 event=response-sent
```

Lúc này, lọc theo thread name sẽ làm **mất các event của cùng một request**. Chọn `requestId` để nối luồng nghiệp vụ, còn thread name để thấy sự phân công và chuyển luồng.

Một số lỗi concurrency như deadlock, queue backlog hay starvation có thể có dấu hiệu trong thread name và stack trace, nhưng thread name đơn thuần **không chứng minh** hai thao tác thực thi đồng thời hoặc thứ tự trước–sau. Cần quan sát timestamp, event sequence, lock/wait state, metrics và thread dump khi điều tra sâu.

## 8. MDC/ThreadContext khác thread name

Trong ứng dụng dùng **SLF4J và backend hỗ trợ MDC**, có thể gắn correlation ID tạm thời trong phạm vi xử lý:

```java
// Fragment: requestId được tạo hoặc xác thực từ request.
org.slf4j.MDC.put("requestId", requestId);
try {
    handleRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

Đoạn trên giả định `handleRequest()` và `requestId` đã có, đồng thời ứng dụng có SLF4J API và backend/provider phù hợp.

Điểm cần nhớ:

- `%thread` đọc **thread name**; `%X{requestId}` đọc giá trị **MDC**.
- MDC không tự được in nếu pattern/encoder chưa tham chiếu nó.
- MDC thường gắn với **thread context**; thread pool tái sử dụng luồng nên phải dọn trong `finally` để không gắn request ID cũ cho task mới.
- Các tác vụ chuyển sang `ExecutorService`, `CompletableFuture`, reactive stream hoặc async callback **không phải lúc nào cũng tự truyền MDC**. Cần cơ chế context propagation tương thích framework.
- Trong Log4j 2, khái niệm tương ứng là `ThreadContext`; pattern có thể đọc context map bằng `%X{requestId}`.

**Sai lầm phổ biến:** Đọc `[thread=payment-worker-1]` và coi đó chính là `requestId`. Một worker thực hiện nhiều giao dịch liên tiếp; thread name không thay thế định danh yêu cầu.

### Thận trọng với virtual threads

Từ **Java 21**, Java hỗ trợ virtual threads theo cách chính thức. Mã chạy trên virtual thread có thể có cách đặt tên khác, và cấu hình mặc định có thể khiến tên thread không có nhiều thông tin. Nếu ứng dụng sử dụng virtual threads, đừng dựa vào tên của từng virtual thread để đại diện cho request hoặc transaction; số lượng thread có thể rất lớn. Nên ưu tiên structured logging và context/tracing rõ ràng, cùng encoder/backend đã được kiểm thử với môi trường Java đang sử dụng.

Ví dụ chính của bài dùng Java 17 **platform threads**, không sử dụng API virtual-thread không có trong JDK 17.

## 9. Khi logging bất đồng bộ: phải giữ thread phát event

Một hệ thống async logging thường có sơ đồ:

```text
order-worker-1
   |
   | logger.info(...)
   v
Log event (chứa metadata tại thời điểm phát)
   |
   v
Queue
   |
   v
async-logging-consumer
   |
   v
Layout/encoder -> file/console
```

Câu hỏi quan trọng: **pattern hiển thị thread của người phát event hay của worker đang ghi log?** Với Logback/Log4j 2, các trường thread của log event được thiết kế để mô tả nguồn phát khi backend capture event đúng cách, kể cả khi layout được áp dụng ở bước sau. Tuy nhiên, cần kiểm tra implementation, event snapshot, deferred processing và async appender đang dùng.

Nếu tự viết custom formatter kiểu:

```java
// Không dùng để suy luận thread nguồn ở một formatter bất đồng bộ.
String name = Thread.currentThread().getName();
```

thì `name` có thể là `async-logging-consumer`, **không phải** `order-worker-1`. Trong JUL, nếu chỉ cần ID nguồn, `LogRecord.getLongThreadID()` cung cấp metadata của event. Nếu cần **tên nguồn**, phải chụp khi phát log và lưu cùng record/structured event, hoặc dùng backend đã có field này.

Ngoài thread metadata, async logging còn cần quan tâm queue capacity, thứ tự, batching, flush/shutdown, hành vi khi queue đầy và chính sách drop/backpressure. Một pattern có thread name đúng không bảo đảm log không mất trong quá trình kết thúc tiến trình.

### Thread name và stack trace có liên hệ gì?

Stack trace trong exception mô tả các frame nơi exception được tạo/ném hoặc được lưu lại, trong khi thread name của event cho biết thread **phát log**. Nếu exception được bắt ở một thread rồi chuyển qua thread khác để xử lý, hai thông tin này có thể không trùng ngữ cảnh thời gian. Khi phân tích, cần xem cause chain, điểm log, request ID và quan hệ tác vụ — không dựa vào tên thread để suy ra stack trace được tạo trên cùng một thread.

## 10. Định dạng thread trong structured JSON logging

Với log tập trung, JSON thường phù hợp hơn một pattern text khó parse. Ví dụ minh họa một event:

```json
{
  "timestamp": "2026-11-09T08:15:12.038Z",
  "level": "INFO",
  "logger": "com.example.order.OrderService",
  "thread": {
    "name": "order-worker-1",
    "id": 37
  },
  "requestId": "req-17",
  "event": "order_reserved",
  "message": "Inventory reservation completed"
}
```

Đây là **JSON minh họa**, không phải output từ `ThreadFormatDemo`. Giá trị ID thực của thread sẽ khác; field schema phụ thuộc encoder và chuẩn logging của dự án. Các backend/encoder có thể dùng `thread_name`, `thread.name`, `threadId` hoặc key khác. **Không giả định mọi backend tạo cùng một JSON schema** chỉ vì PatternLayout có `%thread`.

Ưu điểm của structured logging:

1. Tách thread name/ID thành field riêng để truy vấn.
2. Không phải dựa vào regex để cắt `[thread=...]` từ một chuỗi.
3. Có thể lọc đồng thời theo `service`, `logger`, `thread.name` và `requestId`.
4. Encoder chuẩn sẽ xử lý escaping cần thiết cho giá trị string.

Nếu collector xử lý từng dòng, nhiều hệ thống chọn **mỗi event là một JSON object trên một dòng**. Pretty-printed JSON nhiều dòng có thể cần cấu hình multiline collector; không suy ra một log event bằng một dòng vật lý khi formatter đã thêm newline trong message hoặc stack trace.

Dù dùng JSON, không đưa dữ liệu nhạy cảm như token, password hay cookie phiên vào thread name/MDC. Thread metadata không cần chứa danh tính người dùng.

## 11. Những lỗi thường gặp khi định dạng thread

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không thấy tên thread | Pattern chưa dùng `%thread` hoặc backend khác đang hoạt động | Kiểm tra file config, provider/backend và layout thực |
| Logback hiển thị `%T` hoặc parser error | Dùng token ID thread của Log4j 2 trong Logback | Dùng `%thread` cho tên; chọn encoder/converter ID phù hợp |
| Log4j 2 không hiển thị ID | Pattern dùng `%t` cho tên chứ không dùng `%T` | Kiểm tra `%T`/`%threadId` và phiên bản backend |
| JUL ghi nguyên chuỗi `%thread` | JUL SimpleFormatter không dùng PatternLayout giống Logback | Viết Formatter hoặc chọn backend khác |
| Log ghi `async-consumer` thay vì tên nguồn | Custom formatter đọc `Thread.currentThread()` trên thread ghi | Capture thread tại thời điểm phát event |
| Nhiều request có cùng thread name | Thread pool tái sử dụng worker | Dùng `requestId`/trace ID để nối nghiệp vụ |
| Cùng request có nhiều thread name | Task chuyển executor/async | Truyền correlation context giữa các thread |
| MDC giữ ID từ request cũ | Không dọn `ThreadLocal`/MDC sau xử lý | Dọn trong `finally`, kiểm tra worker reuse |
| Log thiếu request ID dù có `%thread` | Thread field và MDC là hai nguồn dữ liệu khác | Điền MDC và tham chiếu `%X{requestId}` |
| Thread ID không trùng số của OS tool | JVM ID không nhất thiết là native TID | Không đối chiếu trực tiếp mà không có mapping |
| Thread name bị đổi giữa hai bản ghi | Thread bị rename hoặc nhiều JVM dùng cùng tên | Xem timestamp, thread ID, service/instance |
| Log file bị nhân đôi khi thêm pattern | Có hai appender hoặc additivity/propagation | Kiểm tra cấu hình đường đi logger → appender |
| Ghi log có nhưng quá chậm | Format tốn CPU, I/O, stack trace hoặc flush quá nhiều | Giảm event không cần, chọn async/encoder phù hợp và đo đạc |

**Lỗi mang tính khái niệm thường gặp nhất:** Nghĩ rằng thread name luôn định danh một request. Đó là một công cụ điều tra **đường thực thi**, không phải correlation key duy nhất cho hoạt động nghiệp vụ.

## 12. Kiểm thử formatter/layout trong hệ thống thực

Khi cấu hình thread pattern, nên xác minh bằng ít nhất những trường hợp:

1. **Thread main:** một event phát ở thread chính, tên xuất hiện trong pattern.
2. **Thread có tên rõ ràng:** một event từ `new Thread(task, "order-worker-1")`; pattern ghi đúng nguồn.
3. **Thread pool tái sử dụng:** hai task khác nhau chạy trên cùng worker; `requestId` khác dù thread name giống.
4. **Chuyển thread:** một request đi qua hai executor; correlation ID không mất.
5. **Exception:** stack trace được giữ, thread metadata gắn vào event đúng.
6. **Async appender:** field thread là nguồn phát thay vì thread consumer.
7. **Structured encoder:** thread name/ID được ghi vào key mong đợi, có escaping chuẩn.
8. **Bảo mật:** không có dữ liệu bí mật trong thread name hoặc context.
9. **Backend thật:** Logback hoặc Log4j 2 đang được chọn đúng như cấu hình; không chỉ có SLF4J API nhưng thiếu provider.
10. **Đích thu thập:** stdout/stderr, file và collector nhận đúng field, không cắt message hoặc gộp sai record.

Ví dụ kiểm chứng bằng cách nhìn log:

```text
INFO [thread=order-worker-1] requestId=req-17 event=started
INFO [thread=order-worker-1] requestId=req-18 event=started
INFO [thread=order-worker-2] requestId=req-17 event=completed
```

Đây là dữ liệu minh họa. Nếu một truy vấn muốn biết tiến trình request `req-17`, chọn `requestId=req-17` sẽ tìm được cả event ở worker-1 lẫn worker-2; lọc `order-worker-1` sẽ bỏ sót event cuối và lấy nhầm một phần `req-18`.

## 13. Checklist khi đưa định dạng thread vào production

- **Có mục đích rõ:** thread name phục vụ chẩn đoán concurrency, thread pool, thread dump; request ID phục vụ tương quan nghiệp vụ.
- **Pattern đúng backend:** Logback dùng `%thread`/`%t`; Log4j 2 dùng `%t` cho tên và `%T` cho ID; JUL cần cơ chế khác.
- **Capture đúng thời điểm:** nếu async, không đọc `Thread.currentThread()` ở consumer formatter rồi coi đó là origin thread.
- **Tên thread có ích:** dùng ThreadFactory/điểm tạo executor, tránh tên động theo người dùng hay transaction.
- **Giữ metadata khác:** timestamp đủ timezone, level, logger, exception và correlation ID khi cần.
- **Định dạng dễ thu thập:** backend/encoder và collector thống nhất cách mã hóa, escape và cắt dòng.
- **Xem xét virtual threads:** khi nâng JVM và mô hình thread, kiểm tra lại tính hữu ích của thread name.
- **Bảo mật và hiệu năng:** không đưa secret/PII vào thread name hoặc MDC; đo overhead của layout và số lượng event.
- **Kiểm tra thực tế:** thử ít nhất main thread, named worker, executor reuse, cross-thread và async logger ở staging.

**Kết luận:** “Định dạng thread” là việc đưa **metadata của luồng phát sự kiện** vào formatter/layout. Thread name giúp nhìn ra luồng thực thi; thread ID có thể hỗ trợ đối chiếu nội bộ trong JVM; nhưng cả hai **không thay thế request ID hay trace ID**. Chọn đúng conversion word theo Logback/Log4j 2 hoặc tự xử lý JUL, đồng thời bảo toàn thread metadata trước khi log qua queue, sẽ tạo ra những bản ghi đáng tin khi điều tra ứng dụng Java chạy đồng thời.

## Tài liệu chính thức để đối chiếu

- Oracle Java 17, `LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Oracle Java 17, `Thread`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Logback, `PatternLayout`: https://logback.qos.ch/manual/layouts.html
- Apache Log4j 2, `PatternLayout`: https://logging.apache.org/log4j/2.x/manual/pattern-layout.html
