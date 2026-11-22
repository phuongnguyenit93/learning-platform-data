# Log bị trùng trong Java Core Logging

## 1. Log bị trùng là gì và vì sao nguy hiểm?

**Log bị trùng (duplicate logging)** là tình trạng một sự kiện log được ghi hoặc thu thập nhiều lần ngoài chủ đích. Tác động gồm nhiễu khi debug, tăng I/O và chi phí lưu trữ, sai số khi đếm sự cố và cảnh báo, cũng như khả năng gửi dữ liệu tới một sink không phù hợp.

Cần phân biệt ba hiện tượng:

1. **Một sự kiện log thành nhiều bản sao:** code chỉ gọi `logger.error(...)` một lần nhưng appender/handler nhận event hai lần do cấu hình phân cấp, hoặc pipeline thu thập gửi lại cùng record.
2. **Nhiều sự kiện mô tả một failure:** repository ghi stack trace rồi rethrow; service và controller lại log cùng exception. Có nhiều lời gọi log khác nhau, nhưng chúng nói về một lần thất bại.
3. **Nghiệp vụ thực sự chạy lại:** retry, message redelivery hoặc scheduler chạy lại; có thể tạo các sự kiện log hợp lệ dù nội dung tương tự.

Hai dòng giống nhau không đủ kết luận bị trùng: hai request độc lập có thể gặp cùng lỗi. Ngược lại, ba dòng có message khác nhau có thể đều là log thừa cho một failure.

~~~text
12:30:01.123 [worker-1] ERROR Checkout - event=payment_failed orderId=42
12:30:01.123 [worker-1] ERROR Checkout - event=payment_failed orderId=42
~~~

Đây là **dấu hiệu nghi vấn**. Cần so sánh logger, thread, process, requestId, eventId và đường xuất/thu thập. Nếu một event được gửi đến console **và** file audit theo chủ đích, hai sink nhận nó không tự động là lỗi. Lỗi nằm ở việc cùng sink nhận lặp hoặc số liệu gộp không phân biệt nguồn.

## 2. Tìm tầng nhân bản trước khi sửa

Pipeline thông thường:

~~~text
Business code / library
    |
    v
SLF4J / Log4j API / java.util.logging
    |
    v
Logger level và hierarchy
    |
    +--> Appender/Handler A -> stdout/file
    |
    +--> Appender/Handler B -> stdout/file
                                |
                                v
                       Shipper / collector
                                |
                                v
                     Queue, batch, retry, exporter
                                |
                                v
                       Index / dashboard
~~~

Cách khoanh vùng:

- **Tại code:** đặt breakpoint ở lời gọi logger hoặc dùng test appender để kiểm tra có một hay nhiều `LogEvent` được phát.
- **Tại đầu ra nguyên bản:** xem stdout/file của **đúng một tiến trình hoặc pod**. Nếu ở đây đã trùng, ưu tiên kiểm tra logger, appender/handler và code ghi lỗi.
- **Tại collector:** nếu local một lần nhưng backend hai lần, xem receiver, hai đường stdout/file, checkpoint/offset, retry và các tuyến exporter hội tụ.
- **Tại dashboard:** nếu dữ liệu nguyên bản không trùng nhưng kết quả đếm bất thường, kiểm tra truy vấn gộp nhiều index/sink hoặc đếm log ERROR thay vì đếm request thất bại.
- **Tại nghiệp vụ:** nếu nhiều instance phát cùng event nghiệp vụ do message delivery lại, tìm cơ chế idempotency/retry chứ không chỉ tìm lỗi logging.

Ghi kèm `requestId`, `jobId`, `attempt`, `logger`, `instanceId` và `eventId` nếu hệ thống có contract tạo ID cho từng sự kiện log. `requestId` thường liên kết **nhiều** event của một request nên không thể dùng làm khóa duy nhất để dedup.

## 3. Logback: additivity khiến một event đi qua cùng appender hai lần

Trong Logback, logger có cây phân cấp theo tên package/class. Mặc định, event từ logger con được chuyển tới appender của chính nó **và** appender của tổ tiên; cơ chế này là **additivity**.

~~~text
root (CONSOLE)
    |
    +-- com.example.orders (CONSOLE)
            |
            +-- CheckoutService -> logger.error(...)
~~~

Nếu `CONSOLE` được gắn cả tại `com.example.orders` và `root`, cùng event có thể tới console hai lần.

Ví dụ `logback.xml` **gây trùng**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG">
        <appender-ref ref="CONSOLE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Sửa theo hướng mặc định:** chỉ gắn `CONSOLE` ở root; logger con chỉnh level, không gắn lại appender:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Logger con cho phép event DEBUG và chuyển tới root appender theo additivity. Root `INFO` không đơn giản là một lần lọc mức khác áp lại cho event đã được cho phép tại logger con; filter/threshold riêng của appender vẫn có thể hạn chế output.

Nếu muốn **tách riêng** log một package vào file, có thể đặt `additivity="false"` rồi gắn appender riêng:

~~~xml
<!-- Snippet, cần định nghĩa ORDERS_FILE trong cấu hình đầy đủ. -->
<logger name="com.example.orders" level="DEBUG" additivity="false">
    <appender-ref ref="ORDERS_FILE"/>
</logger>
~~~

Đặt `additivity=false` mà **không có appender phù hợp** có thể làm log của nhánh biến mất. Vì vậy đừng tắt additivity trên mọi logger chỉ để che bản sao. Trường hợp một event có chủ đích đi vào hai sink **khác nhau** cần được giữ theo thiết kế.

## 4. Log4j 2: AppenderRef ở logger con và root

Log4j 2 có `AppenderRef` và `additivity` mặc định là `true`. Cấu hình `log4j2.xml` sau có cùng `CONSOLE` ở cả logger con và root:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.orders" level="debug">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Có hai giải pháp đúng tùy mục tiêu:

- Muốn dùng một console chung: **bỏ `AppenderRef` ở logger con**, chỉ giữ appender tại root và vẫn cấu hình `level="debug"` nếu cần.
- Muốn logger con tự ghi vào `CONSOLE`, không kế thừa từ root: đặt `additivity="false"` ở con **và** giữ `AppenderRef` tại con.

Ví dụ phần `Loggers` theo cách thứ hai (snippet thay trong file đầy đủ):

~~~xml
<Loggers>
    <Logger name="com.example.orders" level="debug" additivity="false">
        <AppenderRef ref="CONSOLE"/>
    </Logger>
    <Root level="info">
        <AppenderRef ref="CONSOLE"/>
    </Root>
</Loggers>
~~~

Kiểm tra cả trường hợp **hai appender khác tên nhưng cùng ghi một đích vật lý**. Khác tên appender không bảo đảm hai file/output thực sự độc lập. Khi dùng file audit hoặc appender riêng, lập bảng event nào cần tới đích nào rồi mới đổi additivity.

## 5. Java Util Logging (JUL): handler con và handler cha

Trong `java.util.logging`, `Logger` chuyển `LogRecord` đến handler của chính nó; mặc định còn chuyển đến handler của các logger cha qua `useParentHandlers=true`. Nếu cùng một `ConsoleHandler` hoặc handler tùy chỉnh được gắn ở con và cha, event có thể bị nhận hai lần.

Cách xử lý: xem `getHandlers()` ở logger con và tổ tiên; nếu root đã sở hữu console, thường không cần gắn thêm handler giống vậy ở con. Khi logger có đầu ra riêng, gắn handler có chủ đích rồi mới xét `setUseParentHandlers(false)`. Trong lifecycle, tránh gọi `addHandler(...)` lặp mỗi khi một component khởi tạo; dọn bằng `removeHandler(...)` và đóng handler khi không còn dùng.

### Ví dụ Java 17 hoàn chỉnh

Tệp **`DuplicateLogDemo.java`** chỉ dùng thư viện chuẩn. Nó cho thấy **một** event được ghi hai lần khi cùng handler được gắn ở cả cha và con.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DuplicateLogDemo {
    private static final class ListHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Không có I/O cần flush.
        }

        @Override
        public void close() {
            // Không có tài nguyên ngoài cần đóng.
        }

        int count() {
            return messages.size();
        }

        void clear() {
            messages.clear();
        }
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("lesson.duplicate");
        Logger child = Logger.getLogger("lesson.duplicate.orders");

        Level originalParentLevel = parent.getLevel();
        Level originalChildLevel = child.getLevel();
        boolean originalParentUse = parent.getUseParentHandlers();
        boolean originalChildUse = child.getUseParentHandlers();

        ListHandler sink = new ListHandler();
        sink.setLevel(Level.ALL);

        parent.setLevel(Level.ALL);
        child.setLevel(Level.ALL);
        parent.setUseParentHandlers(false); // Cô lập khỏi root.
        child.setUseParentHandlers(true);   // Cho phép đi lên parent.
        parent.addHandler(sink);
        child.addHandler(sink);             // Cấu hình sai: gắn hai chỗ.

        try {
            child.info("event=order_saved eventId=e-1");
            System.out.println("before=" + sink.count());

            child.removeHandler(sink);     // Sửa: chỉ parent giữ sink.
            sink.clear();

            child.info("event=order_saved eventId=e-2");
            System.out.println("after=" + sink.count());
        } finally {
            child.removeHandler(sink);
            parent.removeHandler(sink);
            child.setUseParentHandlers(originalChildUse);
            parent.setUseParentHandlers(originalParentUse);
            child.setLevel(originalChildLevel);
            parent.setLevel(originalParentLevel);
            sink.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DuplicateLogDemo.java
java DuplicateLogDemo
~~~

**Stdout xác định**:

~~~text
before=2
after=1
~~~

Lần đầu, `child.info(...)` tạo một `LogRecord` được chuyển đến `ListHandler` ở child rồi đến cùng handler ở parent, cho `before=2`. Sau khi bỏ handler ở child, event thứ hai chỉ đến qua parent, cho `after=1`. `parent.setUseParentHandlers(false)` ngăn handler root mặc định của máy ảnh hưởng kết quả. `finally` dọn handler và phục hồi cấu hình logger. Ví dụ chạy tuần tự để kết quả ổn định; thay cấu hình logger khi nhiều thread cùng dùng cần kiểm soát vòng đời.

Cơ chế nhận hai lần qua phân cấp đã được kiểm tra trong JShell với JDK; API sử dụng tương thích Java 17. Chương trình không cần thư viện logging bên ngoài.

## 6. Log cùng exception ở nhiều tầng

Ví dụ service gọi repository, repository gặp lỗi và vừa log vừa ném tiếp:

~~~java
// Snippet tại Repository:
catch (SQLException e) {
    log.error("database save failed", e);
    throw e;
}

// Snippet tại Service:
catch (SQLException e) {
    log.error("checkout failed", e);
    throw e;
}

// Snippet tại HTTP boundary:
catch (SQLException e) {
    log.error("request failed", e);
    return errorResponse();
}
~~~

Đây là **ba snippet minh họa**, chưa phải một chương trình Java độc lập. `log`, `errorResponse()` và các khối `try` tương ứng do ứng dụng định nghĩa. Một lỗi gốc có thể sinh **ba** `LogEvent` và ba stack trace. Nếu dashboard đếm mọi dòng ERROR, một request thất bại có thể thành ba “sự cố”.

Thường nên chọn **một boundary chịu trách nhiệm log lỗi cuối cùng**. Các tầng dưới có thể ném exception giàu ngữ cảnh mà không in lại stack trace. Nếu một tầng ghi sự kiện khác biệt như `retry_scheduled`, hãy log riêng sự kiện đó kèm `attempt` và level phù hợp.

~~~java
// Service: bổ sung thông tin và ném tiếp, không lặp stack trace.
throw new OrderPersistenceException("orderId=" + orderId, cause);

// Boundary: một lần ghi lỗi cuối cùng.
log.error("event=checkout_failed orderId={}", orderId, exception);
~~~

Đoạn trên cần class `OrderPersistenceException`, biến và logger của ứng dụng; không phải file runnable độc lập.

Một dạng trùng khác nằm **trong cùng một event**: code tự nối `exception.toString()`/stack trace vào message rồi cũng truyền throwable cho backend; encoder có thể in exception thêm lần nữa. Truyền đối tượng exception theo API logging, để backend định dạng stack trace. Tránh log cùng throwable ở mọi tầng chỉ vì mỗi tầng có `catch`.

## 7. Retry, Future và callback: hai dòng giống nhau có thể hợp lệ

Một operation logic có thể retry nhiều lần:

~~~text
event=payment_started orderId=42 attempt=1
event=payment_retry_scheduled orderId=42 attempt=1 reason=timeout
event=payment_started orderId=42 attempt=2
event=payment_succeeded orderId=42 attempt=2
~~~

Đây là **bốn sự kiện** của hai lần thử, không được dedup theo `orderId` hoặc message đơn thuần. Với message broker có at-least-once delivery, message có thể được giao lại khi ACK chưa được xác nhận. Nếu nghiệp vụ thật sự thực thi hai lần, phải thiết kế **idempotency** cho tác vụ; xóa bản sao log không sửa được giao dịch DB/tiền đã xử lý hai lần.

Với `ExecutorService.submit()`, exception từ task thường được giữ trong `Future`; caller gọi `Future.get()` có thể nhận `ExecutionException`, lỗi gốc ở `getCause()`. Nếu worker đã log exception rồi caller log lại đầy đủ sau `get()`, một failure có hai stack trace. Thống nhất nơi ghi lỗi: trong worker nếu nó chịu trách nhiệm xử lý, hoặc nơi lấy kết quả nếu caller chịu trách nhiệm.

Với `CompletableFuture`, callback `whenComplete`, `handle` và `exceptionally` có thể cùng nhìn thấy một failure. Nếu đặt `log.error(...)` ở tất cả callback mà không có thông tin mới, một lỗi bị lặp. Chỉ log ở ranh giới thích hợp và thêm trường `attempt`, `outcome` khi event khác nhau về nghĩa.

Các ID cần có contract rõ:

| Trường | Ý nghĩa | Có dùng làm khóa dedup event? |
| --- | --- | --- |
| `requestId` / `traceId` | Liên kết các bước trong request/trace | Không; mỗi request có nhiều event |
| `jobId` / `operationId` | Định danh thao tác logic | Không đủ; có thể có nhiều lần thử |
| `attempt` | Phân biệt lần chạy/retry | Cần đi kèm ID khác |
| `eventId` | Định danh riêng của event nguồn, giữ nguyên khi vận chuyển lại | Có thể, nếu uniqueness và retention được bảo đảm |
| `instanceId` / `podId` | Phân biệt nguồn phát | Hỗ trợ điều tra, không đủ một mình |

## 8. Trùng log ở collector hoặc hệ thống lưu trữ

Nếu console cục bộ chỉ có một dòng nhưng backend có hai bản sao, kiểm tra:

~~~text
App -> stdout ---> collector A --+
    -> app.log --> collector B --+--> cùng index

Collector -> gửi batch -> backend đã lưu -> ACK bị mất
          -> timeout / retry -> cùng batch được gửi lại
~~~

Các tình huống thường gặp:

1. Ứng dụng xuất cùng event ra stdout và file, hai nguồn được tail rồi nhập chung mà không gắn provenance.
2. Hai agent hoặc hai pipeline collector cùng đọc một file/receiver.
3. Batch đã được backend nhận nhưng phía gửi không thấy ACK, nên **retry** và có thể nhập lại.
4. Offset/file identity bị reset sau rotation, restart hoặc backfill, khiến một đoạn file được đọc lại.
5. Nhiều instance thực sự tạo event tương tự do message redelivery; cần phân biệt lỗi nghiệp vụ với lỗi ingest.

OpenTelemetry Collector hỗ trợ queue/retry qua một số exporter helper; hành vi phụ thuộc exporter, version, backpressure và đích. Retry cải thiện khả năng chuyển dữ liệu khi có lỗi tạm thời nhưng không tự đảm bảo ingest exactly-once. Nếu backend cho phép, có thể dùng **event ID ổn định** và idempotent ingest/dedup với thời hạn lưu ID được thiết kế. Không tắt retry chỉ để tránh trùng nếu điều đó tạo nguy cơ mất log quan trọng.

**Không loại mọi bản ghi có cùng text và timestamp làm tròn giây.** Hai request thật có thể xảy ra cùng giây và tạo message giống nhau. Khi thiếu eventId, tổ hợp timestamp, logger, thread, instance, requestId, exception signature chỉ cho ra **ứng viên** cần điều tra.

## 9. SLF4J provider và bridge có gây log trùng không?

SLF4J là API; Logback/Log4j 2 hoặc một provider khác thực hiện ghi. Runtime thường nên có **một SLF4J provider phù hợp**. Cảnh báo nhiều provider/binding là tín hiệu cần sửa classpath, nhưng **không tự chứng minh mỗi event được in bởi tất cả providers**; SLF4J có cơ chế chọn provider tùy phiên bản.

Bridge giúp chuyển JUL, Commons Logging hoặc Log4j API về backend trung tâm. Cài bridge ngược chiều không phù hợp có thể gây vòng chuyển tiếp, lỗi khởi tạo hoặc stack overflow. Cần kiểm tra từng thành phần trên runtime classpath:

- API nào phát log? `org.slf4j.Logger`, `org.apache.logging.log4j.Logger` hay `java.util.logging.Logger`?
- Backend nào active và file `logback.xml`, `logback-spring.xml`, `log4j2.xml` hoặc JUL properties nào được nạp?
- Dùng `mvn dependency:tree` hoặc `gradle dependencies --configuration runtimeClasspath` và `dependencyInsight` để tìm provider/bridge bị kéo vào qua transitive dependency.
- Đảm bảo mỗi nguồn có đường routing rõ, tránh vòng bridge hai chiều; kiểm tra lại bằng test appender sau thay đổi.

Không xóa ngẫu nhiên thư viện logging vì một JAR có thể là API, bridge hoặc backend cần thiết.

## 10. Kiểm thử và sửa đúng nguyên nhân

### Test ở đúng sink

Nên dùng test handler/appender in-memory để đếm **record nhận** thay vì chỉ mock số lần gọi logger:

1. Phát một event từ logger con, xác minh console chung nhận **đúng một** khi thiết kế yêu cầu một.
2. Nếu có file/audit sink riêng, xác minh mỗi sink nhận số event theo contract; `additivity=false` không làm mất ERROR/AUDIT.
3. Ném một exception qua repository → service → boundary, xác nhận số stack trace hợp chính sách.
4. Thử retry `attempt=1` và `attempt=2`, giữ cả hai event hợp lệ.
5. Thử `Future.get()` và `CompletableFuture` callback để phát hiện log cùng failure nhiều lần.
6. Thu stdout/file về collector, kiểm tra hai source có trùng nội dung trong cùng index không.
7. Mô phỏng retry batch, rotation, restart, hai collector, rồi xác minh eventId và trạng thái idempotent ingest nếu có.
8. Với nhiều thread, so sánh ID/tập event; không assert thứ tự log phụ thuộc scheduler.

### Quy trình điều tra ngắn

1. Chọn một event nghi trùng, ghi lại `timestamp`, `logger`, `thread`, `requestId`, `eventId`, `instance`, source.
2. Đếm bản ghi ở log nguyên bản của một process. Nếu trùng ngay tại nguồn, xem code và hierarchy.
3. Kiểm tra `AppenderRef`/`additivity` trong Logback/Log4j 2 hoặc `getHandlers()`/`useParentHandlers` ở JUL.
4. Nếu message khác nhau nhưng cùng failure, kiểm tra catch/rethrow, retry và callback.
5. Nếu local một lần, kiểm tra file/stdout có bị ship hai lần, receiver/exporter, checkpoint và retry.
6. Sửa ở môi trường test, đo số event tại từng sink; đảm bảo không mất log quan trọng.

## 11. Những “cách chữa” làm mất log

| Sửa vội | Hậu quả có thể xảy ra | Phương án đúng |
| --- | --- | --- |
| Tăng root level từ INFO lên ERROR | Ẩn INFO/DEBUG, hai ERROR vẫn trùng | Gỡ appender/handler gắn trùng |
| Đặt `additivity=false` cho toàn bộ logger con | Nhánh không có appender sẽ mất output | Chỉ tắt tại nhánh có sink riêng |
| Tắt console hoặc file vô điều kiện | Mất đầu ra vận hành/audit | Vẽ routing tới từng sink trước |
| Xóa bản ghi có cùng message | Gộp nhầm request/attempt thật | Dùng contract eventId và tiêu chí nghiệp vụ |
| Tắt retry collector | Giảm bản sao nhưng tăng mất dữ liệu | Idempotent ingest và retry có quan sát |
| Bỏ log exception ở mọi tầng | Mất thông tin failure cuối cùng | Chọn một boundary log stack trace |
| Sửa pattern timestamp/màu chữ | Thay hình thức chứ không thay số event | Test tại appender/handler |
| Loại backend/bridge tùy tiện | Làm hỏng logging của framework | Phân tích dependency tree |

Hai bản sao ở **hai đích khác nhau** theo thiết kế có thể cần giữ. Không lấy tổng số log của mọi sink làm số lần nghiệp vụ xảy ra khi cùng event được fan-out sang nhiều nơi.

## 12. Phân biệt record trùng và lần thử hợp lệ

~~~text
eventId=e-101 requestId=req-1 attempt=1 event=charge_failed
eventId=e-101 requestId=req-1 attempt=1 event=charge_failed
eventId=e-102 requestId=req-1 attempt=2 event=charge_failed
eventId=e-103 requestId=req-2 attempt=1 event=charge_failed
~~~

Nếu `eventId` được tạo duy nhất cho từng event tại nguồn và giữ nguyên qua transport, hai dòng `e-101` là ứng viên bản sao của cùng event; `e-102` là retry hợp lệ; `e-103` thuộc request khác. Việc kết luận vẫn phụ thuộc vào contract của event ID và nguồn ingest.

~~~text
event=dao_failed requestId=req-1 cause=timeout
event=service_failed requestId=req-1 cause=timeout
event=http_failed requestId=req-1 status=500 cause=timeout
~~~

Ba event khác nhau của **một chuỗi lỗi**. Muốn đo request thất bại, nên đếm dựa vào `http_failed` hoặc outcome của request, thay vì cộng mọi ERROR. Muốn đo số lần thử DB, dùng `attempt` và event tương ứng.

## 13. Checklist ghi nhớ

- Xác định đơn vị “trùng”: record, log call, failure, request hay attempt.
- Kiểm tra nguồn cục bộ trước, rồi appender/handler, collector và dashboard.
- Rà `additivity`, gắn AppenderRef, JUL parent handler và sink trỏ cùng đích.
- Chốt boundary chịu trách nhiệm ghi exception và phân biệt retry hợp lệ.
- Rà SLF4J provider/bridge, tránh vòng chuyển tiếp.
- Gắn eventId, requestId, attempt và instance khi cần; hiểu rõ ý nghĩa từng ID.
- Với pipeline có retry, kiểm tra checkpoint, nhiều source và idempotency của ingest.
- Kiểm thử số record tại sink và bảo toàn log ERROR/audit sau khi sửa.
- Không dedup bằng message thuần túy; không dùng log dedup để che nghiệp vụ bị thực thi hai lần.

**Nguyên tắc:** tìm **điểm đầu tiên làm số bản ghi tăng** và sửa ngay ở tầng đó. Như vậy có thể loại bản sao ngoài ý muốn mà vẫn giữ log của các request, retry và sự cố thực sự khác nhau.

### Tài liệu tham khảo chính thức

- Logback — [Appender additivity và cấu hình logger](https://logback.qos.ch/manual/configuration-xml.html), [Logger hierarchy](https://logback.qos.ch/manual/architecture.html).
- Apache Log4j 2 — [Configuration và additivity](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- Java SE 17 — [java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- SLF4J — [Cảnh báo provider/binding](https://www.slf4j.org/codes.html), [Manual](https://www.slf4j.org/manual.html).
- OpenTelemetry Collector — [Exporter queue/retry](https://github.com/open-telemetry/opentelemetry-collector/blob/main/exporter/exporterhelper/README.md), [Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/).