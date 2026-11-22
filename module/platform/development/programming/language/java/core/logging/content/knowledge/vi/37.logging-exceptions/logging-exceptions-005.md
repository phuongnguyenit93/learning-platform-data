# Không ghi lỗi nhiều lần — Logging và exception trong Java

## 1. Hiện tượng một lỗi bị log lặp lại

Một request có thể đi qua controller, service, repository và error handler. Nếu **mỗi tầng bắt exception, ghi ERROR rồi ném tiếp**, cùng một thất bại xuất hiện nhiều lần trong log:

~~~text
ERROR Repository - Connection refused
java.sql.SQLException: connection refused
  ...

ERROR OrderService - Could not create order
java.sql.SQLException: connection refused
  ...

ERROR OrderController - Request failed
com.example.OrderCreationException: cannot create order
Caused by: java.sql.SQLException: connection refused
  ...

ERROR GlobalExceptionHandler - Internal server error
com.example.OrderCreationException: cannot create order
Caused by: java.sql.SQLException: connection refused
  ...
~~~

Trong tình huống trên, chỉ có **một lỗi kỹ thuật** và **một HTTP request thất bại**, nhưng có tới bốn logging events ở mức ERROR. Những hệ quả:

- Nhiễu điều tra: không phân biệt được một hay bốn sự cố.
- Alert/analytics đếm ERROR cao hơn số logical failures thực.
- Tăng CPU, bộ nhớ, I/O, dung lượng index và chi phí ingest vì một stack trace dài bị lặp.
- Dữ liệu cá nhân hoặc secret bị ghi nhiều lần nếu exception chứa thông tin nhạy cảm.
- Trách nhiệm xử lý mơ hồ: mọi tầng đều log, không tầng nào rõ ràng là nơi ghi nhận kết quả cuối.

**Giải pháp không phải tắt hết ERROR**, mà là thống nhất *ownership*: **mỗi thất bại logic có một tầng chịu trách nhiệm ghi kết quả**, các tầng ở dưới giữ context/cause hoặc thực hiện recovery mà không log lỗi giống nhau.

“Log once” không có nghĩa mọi request của hệ thống chỉ được ghi một dòng, hoặc một loại SQLException chỉ được ghi một lần trong ngày. Hai request độc lập cùng gặp lỗi là hai failures khác nhau; mỗi failure có thể có event riêng kèm requestId.

## 2. Logging event không đồng nghĩa một dòng văn bản

Một lần gọi logger.error(message, exception) có thể tạo **một event** nhưng pattern layout in thành nhiều dòng stack trace:

~~~text
ERROR requestId=req-42 code=ORDER_FAILED
com.example.OrderCreationException: cannot create order
    at com.example.OrderService.create(...)
Caused by: java.sql.SQLException: connection refused
    at com.example.Repository.save(...)
    ... 5 more
~~~

Dòng “Caused by” là chuỗi nguyên nhân thuộc **cùng một Throwable**, không phải lần log mới. Nếu grep và đếm theo số dòng ERROR/stacktrace mà không hiểu định dạng multiline, rất dễ báo sai.

Ngược lại, một event có thể được chuyển tới **console và file** có chủ đích. Hai bản ghi ở hai sink không phải lúc nào cũng là lỗi. Cần phân biệt ba hiện tượng:

| Tình huống | Bản chất | Điều cần kiểm tra |
| --- | --- | --- |
| Repository log rồi throw, handler lại log | Hai lần gọi logging API | Call-site và requestId |
| Cùng appender được gắn ở logger con và ROOT | Một event bị xuất lặp do additivity | Cấu hình logger/backend |
| Collector đọc từ hai nguồn hoặc retry | Bản ghi lặp sau khi rời JVM | Agent, retry, dedup và eventId |

Khi báo lỗi trùng, hãy hỏi **trùng sự kiện, trùng dòng hay trùng logical failure?** Ba vấn đề khác nhau và cách sửa cũng khác nhau.

## 3. Quy tắc “throw hoặc log” trong pipeline

Một quy tắc kỹ thuật hiệu quả:

- **Catch rồi rethrow** vì chưa xử lý được: thường không log ERROR tại đây.
- **Catch rồi wrap exception để thêm ngữ cảnh:** truyền original cause vào exception mới và ném tiếp, không log thêm.
- **Catch rồi thực hiện fallback thành công:** có thể ghi một WARN/metric khi cần quan sát sự suy giảm, không báo operation cuối cùng thất bại.
- **Catch để retry:** theo dõi từng attempt bằng metrics/tracing và mức DEBUG nếu cần; chỉ log ERROR khi operation cuối cùng thất bại ở boundary.
- **Catch để trả HTTP error, kết thúc job hoặc chuyển message sang DLQ:** thường là nơi ghi một terminal event với throwable và ngữ cảnh.
- **Lỗi validation/business expected:** không mặc định ERROR full stack trace; có thể dùng access log hoặc metric.
- **Không thể xử lý:** để exception lan tới tầng có chính sách phù hợp thay vì catch chỉ để log.

Ví dụ không tốt:

~~~java
// Fragment có repository, OrderCreationException từ ứng dụng.
try {
    repository.save(order);
} catch (SQLException ex) {
    log.error("Database failed", ex); // ERROR thứ nhất
    throw new OrderCreationException("Order failed", ex);
}

// Một nơi khác ở biên HTTP lại ghi:
log.error("Create order failed", ex); // ERROR thứ hai
~~~

Cách tốt hơn:

~~~java
// Service chuyển exception, giữ cause nhưng không log:
try {
    repository.save(order);
} catch (SQLException ex) {
    throw new OrderCreationException("Order failed", ex);
}

// Một boundary đã được chọn ghi kết quả thất bại:
log.error("Create order failed", ex);
~~~

Các fragment này minh họa **chính sách**, không phải chương trình Java độc lập; repository, order, exception và logger là biến/lớp của ứng dụng.

**Ngoại lệ của quy tắc:** một security audit event hoặc sự kiện nghiệp vụ độc lập có thể cần ghi nhận dù terminal boundary đã log ERROR. Chúng không phải hai bản stack trace giống nhau, mà có mục đích và chính sách lưu trữ khác nhau.

## 4. Một tầng chịu trách nhiệm kết quả cuối

Hãy chỉ định **owner** của log cho mỗi operation:

~~~text
HTTP request
    |
    v
Controller
    |
    v
Service  ------------> wrap exception + cause, không log
    |
    v
Repository ----------> throw SQLException, không log
    |
    v
@ExceptionHandler / request boundary
    |
    +--> 1 ERROR: requestId + code + exception
    |
    +--> Response 500 với mã lỗi an toàn
~~~

Tầng thấp bổ sung business context bằng exception hoặc kiểu kết quả có cấu trúc. Boundary ghi thông tin kết thúc khi biết operation thật sự thành công hay thất bại.

**Không phải lúc nào owner cũng là ControllerAdvice.** Nếu lỗi xảy ra ở scheduler, message consumer, HTTP gateway hoặc pipeline async, owner có thể là task runner, listener error handler hoặc một service đã thực sự khôi phục. Cần thiết kế nhất quán cho từng loại entry point.

Ví dụ nếu service gặp timeout nhưng dùng dữ liệu cache và vẫn trả HTTP 200:

~~~text
Remote API timeout
       |
Service dùng cache -> kết quả nghiệp vụ thành công
       |
       +--> metric fallback_total++
       +--> có thể WARN fallback=cache
       +--> KHÔNG bắt buộc ERROR stack trace vì request đã hồi phục
~~~

Nếu chưa log lỗi ở repository/service, nhưng error handler làm mất cause hoặc requestId, người điều tra sẽ thiếu dữ liệu. Vì vậy “không log ở tầng dưới” phải đi kèm **giữ nguyên exception chain** và structured context.

## 5. Bảng quyết định về logging exception

| Tình huống | Xử lý | Chính sách log hợp lý |
| --- | --- | --- |
| Repository phát lỗi, service sẽ throw tiếp | Propagate/wrap | Không ERROR ở tầng trung gian |
| Service wrap SQLException thành nghiệp vụ | Giữ cause | Không ghi lại cùng stack trace |
| HTTP 500 chưa phục hồi | Handler/boundary | Một ERROR với cause và requestId |
| Validation 400 | Trả lỗi cho client | Thường không ERROR full stack |
| Authentication/authorization denied | Áp dụng policy bảo mật | Security/audit event nếu cần; không log trùng |
| Timeout lần 1, còn retry | Metric/trace attempt | Tránh ERROR mỗi attempt |
| Hết retry | Throw exception tổng hợp có cause | Một terminal ERROR tại owner |
| Fallback cache thành công | Tiếp tục xử lý | WARN/metric theo mức độ degradation |
| Scheduled job thất bại | Job runner | Một terminal event có jobId |
| Message được chuyển DLQ | Consumer boundary | Một outcome event kèm messageId |
| Nhiều item độc lập lỗi trong batch | Batch policy | Summary hoặc per-item event có ID |
| Exception đang được xử lý trong CompletableFuture | Một completion handler | Tránh log ở cả callback và caller |

Mức ERROR/WARN/INFO là **quy ước vận hành** chứ không phải phán quyết của Java. Nếu một lỗi tạm thời có ảnh hưởng nghiêm trọng hoặc nghĩa vụ security, team có thể cần ghi event khác; điểm chính vẫn là phân biệt **sự kiện độc lập với stack trace lặp**.

## 6. Ví dụ Java 17+ chạy độc lập: log đúng một lần

Ví dụ dùng **java.util.logging (JUL)** có sẵn trong JDK, không cần thư viện ngoài. Repository phát lỗi, service bọc bằng exception nghiệp vụ và giữ nguyên cause, endpoint xử lý cuối cùng. Một Handler trong bộ nhớ ghi lại các **LogRecord** để xác nhận số logging events.

Tạo file **LogOnceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogOnceDemo {
    static final Logger LOG =
            Logger.getLogger("demo.web.boundary");
    static final List<LogRecord> EVENTS = new ArrayList<>();

    static class OrderCreationException extends RuntimeException {
        OrderCreationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() {
        throw new IllegalStateException("database unavailable");
    }

    static String service() {
        try {
            return repository();
        } catch (IllegalStateException e) {
            // Không ghi log ở tầng trung gian.
            throw new OrderCreationException("cannot create order", e);
        }
    }

    static String endpoint() {
        try {
            return service();
        } catch (OrderCreationException e) {
            // Đây là duy nhất một terminal ERROR event.
            LOG.log(Level.SEVERE,
                    "requestId=req-42 action=CREATE_ORDER "
                    + "code=ORDER_FAILED", e);
            return "HTTP 500 requestId=req-42";
        }
    }

    public static void main(String[] args) {
        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord r) {
                if (isLoggable(r)) EVENTS.add(r);
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(memory);
        try {
            String response = endpoint();
            System.out.println("response=" + response);
            System.out.println("logCount=" + EVENTS.size());

            LogRecord event = EVENTS.get(0);
            System.out.println("level=" + event.getLevel());
            System.out.println("hasThrowable=" +
                    (event.getThrown() != null));
            System.out.println("rootCause=" +
                    event.getThrown().getCause()
                            .getClass().getSimpleName());
            System.out.println("message=" + event.getMessage());
        } finally {
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LogOnceDemo.java
java LogOnceDemo
~~~

Stdout đã được kiểm chứng:

~~~text
response=HTTP 500 requestId=req-42
logCount=1
level=SEVERE
hasThrowable=true
rootCause=IllegalStateException
message=requestId=req-42 action=CREATE_ORDER code=ORDER_FAILED
~~~

**Phân tích kết quả:** service tạo OrderCreationException với constructor (String, Throwable), nên cause vẫn là IllegalStateException. Chỉ endpoint gọi LOG.log(Level.SEVERE, message, e). Handler nhận đúng một LogRecord và getThrown() khác null. setUseParentHandlers(false) ngăn event được chuyển thêm lên handler cha trong ví dụ.

**Giới hạn:** endpoint() trả về chuỗi “HTTP 500 ...” để mô phỏng response, không phải server HTTP thật. Handler in-memory không đảm bảo độ bền log; ArrayList không phải bộ chứa thread-safe cho multi-thread test. Để kiểm thử production, cần test appender thích hợp, nhiều request concurrent, real web boundary và collector.

Với JUL custom Handler, publish() cần gọi isLoggable(record) để tôn trọng level/filter. Đếm **LogRecord** chứ không đếm số dòng stack trace.

## 7. Giữ cause và suppressed exception thay vì log ở từng tầng

Một Throwable trong Java có thể chứa:

- **Message:** mô tả tình huống, không nhất thiết đủ để điều tra.
- **Stack trace:** vị trí tạo và lan truyền lỗi.
- **Cause:** Throwable gây nên lỗi này, có thể tạo thành chuỗi nhiều tầng.
- **Suppressed exceptions:** các lỗi bổ sung, ví dụ khi try-with-resources đóng tài nguyên trong lúc exception khác được ném.

Nếu tầng service cần chuyển SQLException thành exception nghiệp vụ:

~~~java
// Fragment trong phương thức khai báo OrderCreationException.
catch (SQLException ex) {
    throw new OrderCreationException("Cannot create order", ex);
}
~~~

Lúc boundary ghi exception trên cùng, backend có thể hiển thị cả OrderCreationException và SQLException qua “Caused by”. Không cần log SQLException riêng tại repository chỉ để “khỏi mất stack trace”.

Sai lầm phổ biến:

~~~java
// SAI: mất nguyên nhân.
catch (SQLException ex) {
    throw new IllegalStateException(ex.getMessage());
}
~~~

Nên:

~~~java
// GIỮ CAUSE.
catch (SQLException ex) {
    throw new IllegalStateException("Order write failed", ex);
}
~~~

Khi chỉ muốn rethrow exception gốc, dùng throw ex; theo quy tắc catch/throws của Java. Không dùng ex.printStackTrace() rồi throw vì nó đưa một bản stack trace qua stderr bên ngoài framework logging.

Try-with-resources có thể tạo suppressed exceptions. Không tự log chúng một lượt nữa khi exception cha đã mang đủ getSuppressed(). Cần test pattern/encoder thực tế vì một số formatter có thể cắt bớt throwable theo cấu hình; vấn đề đó nên sửa ở **điểm xuất cuối**, không bằng việc rải các log thừa.

## 8. SLF4J và backend: ghi Throwable như một phần của event

Trong Spring Boot hoặc ứng dụng Java lớn, code thường dùng **SLF4J API** và backend Logback hoặc Log4j 2. Để ghi full exception, dùng overload nhận Throwable:

~~~java
// Fragment trong class có org.slf4j.Logger tên log.
log.error("Create order failed", exception);
~~~

Thông điệp đi kèm giúp người đọc hiểu operation đã thất bại, và Throwable cho backend xuất stack trace. Với parameterized logging, throwable thường được xử lý đặc biệt ở đối số cuối, nhưng cần kiểm tra **API/binding/backend và số placeholder** đúng phiên bản. Dùng overload rõ ràng khi chỉ cần một message và Throwable.

Với **SLF4J 2.x**, có fluent API:

~~~java
// Fragment dùng SLF4J 2.x.
log.atError()
   .addKeyValue("requestId", requestId)
   .addKeyValue("errorCode", "ORDER_FAILED")
   .setCause(exception)
   .log("Create order failed");
~~~

Đoạn trên tạo **một** event và thêm key-value/context. Phải gọi .log(...) để thực sự phát sự kiện. Việc backend hiển thị key-value như field có cấu trúc hay ghép vào message phụ thuộc cấu hình encoder/layout; cần đọc lại output.

Không nên viết:

~~~java
// Sai chiến lược: hai cơ chế phát thông tin cùng một lỗi.
exception.printStackTrace();
log.error("Create order failed", exception);
~~~

printStackTrace() có thể đưa dữ liệu trực tiếp vào stderr, bỏ qua filter, MDC và appender được quản lý. Nó còn có thể bị collector thu vào nguồn khác, khiến lỗi nhìn như hai sự kiện.

Ngoài việc giảm log lặp, phải bảo vệ dữ liệu: Throwable message từ JDBC, HTTP hoặc thư viện bên thứ ba có thể chứa query/input/URL nhạy cảm. Cần chọn trường an toàn, redaction và quyền truy cập thay vì trả chi tiết exception cho người gọi API.

## 9. Spring MVC: một global handler chịu trách nhiệm

Với Spring Web MVC, có thể dùng **@RestControllerAdvice** và **@ExceptionHandler** làm terminal boundary cho exception từ controller. Service bên dưới chỉ wrap/throw, không phát ERROR cho cùng logical failure.

Ví dụ **fragment** service (cần các lớp nghiệp vụ và Spring DataException tương ứng):

~~~java
public Order create(CreateCommand command) {
    try {
        return repository.save(command);
    } catch (DataAccessException ex) {
        throw new OrderCreationException("Cannot create order", ex);
    }
}
~~~

Handler tương ứng (cần Spring Web, SLF4J và biến log trong class):

~~~java
@ExceptionHandler(OrderCreationException.class)
public ResponseEntity<ProblemDetail> onOrderFailure(
        OrderCreationException ex,
        HttpServletRequest request) {

    String requestId =
            String.valueOf(request.getAttribute("requestId"));

    // Chỉ một điểm phát ERROR event cuối.
    log.error("Create order failed requestId=" + requestId, ex);

    ProblemDetail body =
            ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
    body.setTitle("Order creation failed");
    body.setDetail("The request could not be completed.");
    body.setProperty("requestId", requestId);

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(body);
}
~~~

Các đoạn trên là **minh họa tích hợp**, không phải chương trình chạy độc lập; handler cần nằm trong class @RestControllerAdvice và có imports, logger, dependency tương ứng. requestId phải do middleware hoặc filter đáng tin cậy gắn trước đó. Nếu request attribute trống, cần policy thay vì tùy tiện nhận header giả từ client.

Phải xác định rõ những đường khác như Spring Security, Servlet Filter, gateway hoặc proxy trả lỗi trước khi controller được gọi. Chúng có boundary riêng. Một lỗi HTTP 400/401/403 dự kiến không mặc nhiên cần stack trace ở ERROR.

**Tránh logging đa tầng qua framework:** controller catch rồi log, throw tiếp để @ExceptionHandler log, đồng thời AOP/interceptor/error tracking SDK cũng log. Hãy kiểm tra cả exception handler tự viết và cơ chế tự động của framework.

## 10. Retry: không log ERROR ở mọi attempt

Một dependency tạm mất kết nối có thể được retry 3 lần:

~~~text
attempt 1: timeout -> log ERROR
attempt 2: timeout -> log ERROR
attempt 3: timeout -> log ERROR
terminal request failed -> log ERROR
~~~

Bốn ERROR không nhất thiết có giá trị hơn một ERROR cuối với attempts=3 và cause đầy đủ. Cách tổ chức phù hợp:

~~~text
attempt 1: timeout -> retries_total++, tracing/DEBUG theo policy
attempt 2: timeout -> retries_total++, tracing/DEBUG theo policy
attempt 3: timeout -> hết retry, throw wrapper có cause
HTTP boundary: 1 ERROR outcome=FAILED attempts=3
~~~

Một đoạn logic mô phỏng (fragment, các lớp client/metrics là của ứng dụng):

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return client.call();
    } catch (TransientNetworkException ex) {
        retryCounter.increment();
        if (attempt == maxAttempts) {
            throw new DownstreamUnavailableException(
                    "Downstream failed after retry", ex);
        }
        // Backoff/jitter theo chính sách; không ERROR mỗi lần.
    }
}
~~~

Cần giới hạn deadline, xử lý interruption/cancellation, tránh retry thao tác không idempotent không có cơ chế nghiệp vụ thích hợp. Nếu retry thành công, operation có thể trả 200 và chỉ cần WARN hoặc metrics về việc fallback/retry.

**Một operation khác với một attempt.** Không dùng chung requestId/operationId làm lý do xóa toàn bộ tín hiệu của các request khác nhau. Nếu client retry HTTP request mới, đó có thể là một logical attempt khác và cần event kết quả riêng theo contract.

## 11. Batch, async task và message listener

### 11.1. Batch nhiều item

Một job có thể xử lý 100 item, hai item thất bại độc lập. Có thể có một log summary và số lỗi theo metric, hoặc một event cho mỗi item nếu đội vận hành cần xử lý từng bản ghi. Không mặc định “một job = một log lỗi”, vì làm vậy có thể mất bằng chứng của các lỗi độc lập.

### 11.2. CompletableFuture và ExecutorService

Exception phát trong worker thread có thể bị ghi ở whenComplete(), sau đó lại được catch và log tại join()/get(). Chọn một **terminal observer** chịu trách nhiệm log, và truyền correlation context qua thread pool đúng cách. Nếu tất cả bên đều nghĩ “tầng khác sẽ log”, có thể không còn event nào.

### 11.3. Scheduler và background worker

Không có HTTP boundary, nên scheduler/job runner thường cần xử lý lỗi cuối. Các service bên trong chỉ wrap cause, để scheduler log một event với jobId/runId/status và retry metadata nếu job thất bại thật.

### 11.4. Kafka/JMS/message broker

Message có thể được giao lại. Nếu listener, retry advice và dead-letter handler đều log ERROR stack trace của mỗi attempt, collector dễ bị nghẽn lúc downstream sự cố. Quy định owner ở **consumer outcome boundary**. Khi message vào DLQ, có thể cần một event kết quả với messageId và lý do, metric retry/deadLetter, không cần toàn bộ stack trace lặp mỗi lần.

### 11.5. Timeout và hủy tác vụ

Nếu upstream timeout trong khi downstream vẫn tiếp tục, hai sự kiện lỗi ở hai hệ thống có thể là hai hậu quả độc lập. Dùng traceId/spanId, requestId và operationId để liên kết trước khi quyết định chúng là duplicate. Khi bắt InterruptedException, cần tôn trọng cancellation/interruption theo thiết kế, không catch rồi im lặng tiếp tục vô hạn.

## 12. Logback additivity: một lời gọi vẫn có thể in hai bản

Có trường hợp code chỉ gọi logger.error một lần nhưng **cùng appender được tham chiếu ở logger con và ROOT**:

~~~xml
<!-- Fragment minh họa cấu hình dễ phát trùng CONSOLE. -->
<logger name="com.example.orders" level="INFO">
  <appender-ref ref="CONSOLE"/>
</logger>
<root level="INFO">
  <appender-ref ref="CONSOLE"/>
</root>
~~~

Với additivity mặc định, một event ở com.example.orders đi qua appender của logger con rồi còn lan lên ROOT. Nếu cả hai tham chiếu CONSOLE, event có thể xuất hai lần.

Cách đơn giản thường là chỉ gắn appender ở ROOT:

~~~xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>

  <logger name="com.example.orders" level="INFO"/>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Đây là cấu hình **logback.xml**. Nó chỉ gắn CONSOLE tại ROOT; event của logger con kế thừa đường xuất nếu đủ level.

Cách khác là gắn appender trực tiếp ở logger con rồi đặt **additivity="false"**, nhưng phải bảo đảm logger con có appender hợp lệ. Đặt additivity=false mà quên appender có thể **mất log**. Không sửa config chỉ để che lỗi rồi làm mất kênh audit hoặc file cần thiết.

Một event được fan-out **có chủ đích** sang FILE và CONSOLE là bình thường. Cần định nghĩa “không trùng” theo **cùng sink và cùng logical failure**, không phải “không được có bản ở nhiều sink”.

## 13. Log4j 2 và collector có thể trùng ở tầng khác

Log4j 2 cũng có LoggerConfig/AppenderRef và quy tắc additivity. Một file **log4j2.xml** minh họa chỉ gắn CONSOLE tại ROOT:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p %c - %m%n%throwable"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.orders" level="info"/>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Không sao chép class/element giữa Logback và Log4j 2; phải kiểm tra XML theo backend thực sự đang nạp. Nếu có thêm các AppenderRef ở logger con/cha, đọc cả additivity và filter để biết event được gửi bao nhiêu lần.

Ngoài JVM, **log shipper/collector** có thể gây duplicate nếu:

- đọc cùng stdout và file đã chứa bản sao của nó;
- forward qua hai pipeline tới cùng index;
- cơ chế retry at-least-once gửi lại cùng bản ghi sau mất ACK;
- cấu hình ingest nhiều lần hoặc replay từ archive.

Nếu local sink có một event nhưng dashboard có hai, điều tra **ingestion pipeline** thay vì thay đổi code service. Với eventId/correlationId, có thể tách bản sao do retry và các failures thật.

Đừng dùng filter theo message “loại lỗi giống nhau trong 60 giây” như giải pháp mặc định: hai request độc lập có cùng text SQLException vẫn cần được đếm đúng.

## 14. Ghi đủ thông tin trong một event cuối

Một terminal ERROR event hữu ích thường cần:

- **eventCode/errorCode:** mã ổn định (ORDER_FAILED, DEPENDENCY_TIMEOUT) thay vì chỉ Exception.toString().
- **requestId/traceId:** liên kết log qua các tầng/dịch vụ, có quyền truy vấn thích hợp.
- **operation/job/message ID:** xác định logical failure, phân biệt các task độc lập.
- **outcome:** FAILED, DEGRADED, RECOVERED tùy kết quả cuối.
- **attempt count** nếu có retry.
- **exception và cause chain:** đủ để tìm root cause, nhưng phải bảo vệ thông tin nhạy cảm.
- **service/environment/component:** biết nơi lỗi phát sinh và tầng đang log.

Ví dụ JSON minh họa:

~~~json
{
  "level": "ERROR",
  "service": "order-service",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "operation": "CREATE_ORDER",
  "errorCode": "ORDER_FAILED",
  "outcome": "FAILED",
  "attempts": 3,
  "exceptionType": "OrderCreationException",
  "rootCauseType": "SQLException"
}
~~~

Mã này chỉ là cấu trúc ví dụ, không phải một bản log thật. Trong triển khai, dùng encoder JSON/structured logging thay vì ghép JSON thủ công từ dữ liệu input. Không thêm email, token, password, số thẻ, cookie hoặc raw SQL parameter để “bổ sung context”.

Một requestId là mã tham chiếu, **không phải token truy cập log**. Không đặt requestId làm metric label không giới hạn vì cardinality lớn. Với client, chỉ trả errorCode, requestId và thông báo an toàn; không xuất nguyên stack trace.

## 15. Thay nhiều ERROR bằng metrics/tracing đúng mục đích

Giảm duplicate stack trace không đồng nghĩa mất khả năng đo lỗi. Mỗi tín hiệu có mục đích riêng:

| Tín hiệu | Giá trị |
| --- | --- |
| Một terminal ERROR | Chi tiết nguyên nhân và ngữ cảnh failure |
| WARN cho fallback | Cho biết hệ thống suy giảm nhưng có thể hồi phục |
| DEBUG cho attempt | Điều tra từng bước khi bật có kiểm soát |
| errors_total metric | Đếm số failures theo định nghĩa và errorCode |
| retries_total metric | Đếm retries mà không nhân stack trace |
| tracing spans | Thấy lỗi tại downstream và thời gian qua các chặng |
| audit/security event | Chứng cứ nghiệp vụ/bảo mật theo chính sách độc lập |

Ví dụ khi provider trả timeout 3 lần rồi request thất bại: retries_total có thể tăng 3, errors_total tăng 1 và một ERROR event có attempts=3. Nếu đã hồi phục ở lần 2 thì retries_total tăng, errors_total có thể không tăng theo định nghĩa terminal failure.

Metric phải có định nghĩa rõ và không được suy ra thuần túy từ số dòng log ERROR. Một stack trace có nhiều dòng, Logback additivity hoặc collector retry đều có thể làm sai số nếu đếm văn bản.

## 16. Kiểm thử log đúng một lần

Đừng dùng grep đếm số dòng vật lý. Với JUL, test Handler trong ví dụ ghi vào List<LogRecord> là cách minh họa. Trong Logback có thể dùng test appender/ILoggingEvent; trong Log4j 2 có test appender tương ứng. Với async backend phải đợi drain/flush đúng cách trước khi assert.

Ma trận gợi ý:

| Test case | Kết quả đúng |
| --- | --- |
| Repository lỗi, service wrap, boundary trả 500 | Một ERROR ở boundary, có full cause |
| Repository thành công | Không có ERROR |
| Service recovery thành công | Không có terminal ERROR, có metric/WARN nếu cần |
| Retry hai lần rồi thành công | Không có hai ERROR stack trace; metric retry tăng |
| Retry hết rồi thất bại | Một terminal ERROR có attempts và cause |
| Validation 400 | Không mặc định ERROR stack trace |
| Hai request cùng lỗi độc lập | Hai terminal failures với requestId khác nhau |
| Async callback rồi caller catch | Không bị log ở cả hai terminal points |
| Một logger call và additivity kép | Phân biệt event code với appender duplicate |
| Local log một, central log hai | Tìm vấn đề forwarding/ingest |
| Throwable có suppressed exceptions | Cause và suppressed được bảo toàn khi cần |
| Security/audit | Không bị xóa nhầm vì policy log-once |

Nên kiểm tra thêm việc không để exception message nhạy cảm xuất hiện trong log và HTTP response. Nếu log ERROR được gửi tới nhiều appender có chủ đích, test tại **tầng logging event** và kiểm tra từng sink riêng.

Không tạo một global Set<Throwable> hoặc Set<String> lưu những lỗi “đã log” để suppress mọi lỗi cùng message. Cách này có thể che failures mới, gây memory leak và làm metrics sai. **Thiết kế ownership ở boundary** là giải pháp bền vững hơn.

## 17. Chẩn đoán duplicate khi đang vận hành

Khi thấy nhiều ERROR giống nhau trong dashboard:

1. **Nhóm bằng requestId, traceId, jobId/messageId:** các log có thuộc cùng logical failure không?
2. **Kiểm tra call-site/logger name:** repository, service, controller, advice có log cùng throwable?
3. **Xem Throwable cause:** nhiều event cùng chain hay nhiều exceptions độc lập?
4. **Kiểm tra appender và additivity:** một event có xuất hai lần ở cùng local sink không?
5. **Kiểm tra fan-out:** FILE và CONSOLE cùng event có phải hành vi chủ đích không?
6. **So local với central:** nếu local một event, central hai thì tìm trong shipper, retry, collector.
7. **Xem retry policy:** có log ERROR trên từng attempt trước khi boundary log nữa không?
8. **Chỉ định một owner và sửa code:** bỏ catch-log-rethrow không cần, giữ cause và context.
9. **Kiểm thử lại:** đảm bảo errors_total, retry metric, tracing và audit không mất dữ liệu.
10. **Theo dõi sau thay đổi:** volume log giảm nhưng các logical failures thật vẫn nhìn thấy.

Một lỗi trùng có thể do **nhiều nguyên nhân cùng lúc**, ví dụ code log hai lần và collector retry thêm mỗi event. Trước khi thay config filter, cần biết duplication phát sinh ở lớp nào.

## 18. Các sai lầm phổ biến

**Catch–log–throw ở mọi tầng.** Mỗi layer muốn “không bỏ sót” nên phát ERROR, sau đó layer trên lại phát ERROR. Chọn terminal owner, giữ cause.

**printStackTrace() cộng logger.error(..., ex).** Hai đường xuất tạo bản sao, có thể bỏ qua MDC/format. Dùng logging framework nhất quán.

**Gói exception nhưng không truyền cause.** Làm mất root cause, khiến developer log tầng thấp để bù. Hãy truyền cause vào constructor của exception mới.

**Mọi 400/404 đều là ERROR stack trace.** Lỗi đầu vào dự kiến thường cần HTTP status, access log/metrics, không phải stack trace báo sự cố hệ thống.

**Mỗi retry là một ERROR độc lập.** Khi downstream lỗi kéo dài, hệ thống log ngập. Theo dõi attempts bằng metric/trace; quyết định terminal error dựa trên operation cuối.

**Dedupe chỉ bằng exception class/message.** Nhiều requests thật có cùng nguyên nhân. Suppress toàn cục sẽ làm méo error rate và ẩn mức độ sự cố.

**Dùng log.error("{}", ex) tùy tiện.** Với parameterized logging và backend khác nhau, exception có thể bị coi là argument thay vì Throwable. Dùng overload log.error("Operation failed", ex) rõ ràng hoặc fluent .setCause(ex) và kiểm tra output.

**Tắt additivity=false mà không gắn appender.** Có thể khiến logger không xuất gì. Sửa routing phải có test đúng đích nhận.

**Một lệnh log nhưng nhiều dòng stack trace = duplicate.** Không đúng; đếm event, không đếm line.

**Muốn giảm lỗi trùng nên tắt cả audit.** Audit có mục đích riêng và có thể phải lưu kể cả khi đã có ERROR. Không sửa policy bảo mật theo cách che kết quả.

## 19. Checklist trước khi đưa vào production

- [ ] Đã xác định mỗi operation có một owner cho terminal ERROR.
- [ ] Catch chỉ để wrap/rethrow không ghi ERROR trùng.
- [ ] Exception wrapper giữ cause và suppressed information khi phù hợp.
- [ ] Error handler không log thêm nếu một component khác đã là owner theo thiết kế.
- [ ] Lỗi expected như validation được xử lý đúng mức, không mặc định full stack.
- [ ] Retry attempts dùng metrics/trace/DEBUG phù hợp, không spam stack trace.
- [ ] Async, scheduler và consumer có boundary xử lý lỗi rõ ràng.
- [ ] Cấu hình Logback/Log4j 2 không tham chiếu cùng appender ở nhiều tầng ngoài ý muốn.
- [ ] Có kiểm tra collector forwarding/retry nếu dashboard thấy duplicate.
- [ ] Một terminal event có requestId/traceId, errorCode, outcome và Throwable.
- [ ] Không in secret, PII, raw request body hoặc stack trace ra client.
- [ ] Test đếm logging events, không đếm số dòng văn bản.
- [ ] Test hai failures độc lập vẫn được đếm đầy đủ.
- [ ] Metric error/retry và security audit không bị giảm nhầm.
- [ ] Có test sau thay đổi cấu hình routing và retry.

**Kết luận:** Muốn **không ghi lỗi nhiều lần**, hãy chọn tầng chịu trách nhiệm cho kết quả cuối, cho các tầng trung gian **giữ cause và ném tiếp thay vì log rồi ném**, ghi một event đủ thông tin tại boundary và dùng metrics/tracing cho các attempt. Đồng thời kiểm tra Logback/Log4j 2 additivity và pipeline collector, vì một event có thể bị nhân bản ngay cả khi code chỉ gọi logger một lần.

## 20. Tài liệu tham khảo

- [Oracle Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause chain, stack trace và suppressed exceptions.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): log(Level, String, Throwable) và Handler.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): logging exception kèm Throwable.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized và fluent API.
- [SLF4J LoggingEventBuilder](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): setCause và addKeyValue.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, appenders và additivity.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): throwable và MDC output.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): LoggerConfig và appender propagation.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): throwable rendering.
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): exception handling ở MVC.
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): xử lý exception dùng chung giữa các controller.
