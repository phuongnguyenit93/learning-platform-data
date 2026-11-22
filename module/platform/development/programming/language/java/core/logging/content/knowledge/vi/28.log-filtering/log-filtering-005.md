# Filter theo context trong Java Core Logging

## 1. Lọc log theo context là gì?

**Context-based filtering** là quyết định **giữ, bỏ hoặc định tuyến** một sự kiện log dựa vào các thuộc tính ngữ cảnh đi kèm với lần thực thi, thay vì chỉ dựa vào mức log (`INFO`, `DEBUG`, `ERROR`), tên logger hay nội dung thông điệp.

Ví dụ trong dịch vụ phục vụ nhiều tenant:

- `tenantId=tenant-a`: một bản ghi có thể được chuyển thêm vào file/chỉ mục riêng dành cho tenant A.
- `tenantId=tenant-b`: bản ghi không được đưa vào đầu ra riêng của tenant A.
- `requestId=req-42`: các bản ghi liên quan đến request 42 có thể được chọn để điều tra.
- `jobType=batch` hoặc `component=payment`: quyết định mức chi tiết, tuyến thu thập hoặc cảnh báo theo ngữ cảnh.
- `traceId=...` và `spanId=...`: liên kết các sự kiện trong cùng trace; việc có trace ID không tự nó cấp quyền truy cập vào dữ liệu log.

**Điểm cốt lõi:** context cần có mặt **khi sự kiện log được tạo và đi qua điểm lọc**. Nếu sự kiện được xử lý bất đồng bộ hoặc chuyển sang thread khác, phải hiểu rõ context được chụp và truyền ở đâu. Lọc sai có thể gây ra hai lỗi nghiêm trọng: log của tenant này đi vào đầu ra tenant khác, hoặc log lỗi quan trọng bị mất hoàn toàn.

Đừng nhầm bốn thao tác:

| Thao tác | Tiêu chí điển hình | Kết quả |
| --- | --- | --- |
| Chọn theo **logger level** | `com.example=INFO` | Bỏ DEBUG/TRACE không đủ mức; không phân biệt request/tenant |
| **Filter theo context** | `tenantId=tenant-a` | Chọn/loại event dựa trên metadata thuộc request, job, tenant |
| **Format / enrich** | `%X{requestId}` | Hiển thị/thêm field context; **không có nghĩa là đã lọc** |
| **Search/query sau khi thu thập** | `tenantId:"tenant-a"` trong log backend | Truy vấn các sự kiện đã được thu; không khôi phục log bị filter bỏ |

Cần phân biệt **lọc để giảm nhiễu**, **định tuyến theo context** và **phân quyền truy cập log**. Lọc ở ứng dụng chỉ là một phần của pipeline. Nếu yêu cầu cách ly dữ liệu tenant, phải có kiểm soát truy cập tại đích ghi/lưu trữ và không tin trực tiếp một tenant ID do client tự khai.

## 2. Context lấy từ đâu và cần chứa gì?

Trong Java dùng SLF4J/Logback, dữ liệu ngữ cảnh thường nằm trong **MDC (Mapped Diagnostic Context)**: một map `String → String` gắn với thread hiện tại. Log4j 2 có cơ chế tương ứng là **Thread Context Map** (`ThreadContext`). Các field từ tracing hoặc framework có thể được bổ sung qua bộ tích hợp riêng.

Ví dụ event (dạng minh họa):

~~~text
2026-11-10T09:41:00.120Z INFO  tenantId=tenant-a requestId=req-42 event=invoice_created
2026-11-10T09:41:00.121Z ERROR tenantId=tenant-b requestId=req-43 event=payment_failed
2026-11-10T09:41:00.125Z INFO  tenantId=tenant-a requestId=req-44 event=invoice_sent
~~~

Filter `tenantId == tenant-a` chọn hai dòng của A. `requestId` dùng để ghép theo request; **nó không thay thế tenantId** nếu quy tắc đích yêu cầu phân vùng tenant. Filter theo log message bằng `contains("tenant-a")` là không tin cậy: chuỗi đó có thể nằm trong văn bản tình cờ, bị format thay đổi, hoặc do dữ liệu người dùng chèn vào.

Chọn các key có ý nghĩa ổn định: `tenantId`, `requestId`, `traceId`, `jobId`, `operation`. Giá trị phải đến từ ngữ cảnh đã xác thực/kiểm tra ở ranh giới hệ thống. Không đưa vào context password, token, cookie, mã truy cập, dữ liệu cá nhân nhạy cảm hoặc payload lớn. Chuẩn hóa ký tự điều khiển và giới hạn độ dài trường nhận từ bên ngoài.

MDC không phải kho dữ liệu nghiệp vụ bền vững hay cơ chế bảo mật. Nó giúp tạo bản ghi chẩn đoán; việc filter/định tuyến vẫn phải tuân theo chính sách an toàn thông tin của ứng dụng.

## 3. Filter nằm ở đâu trong pipeline?

Một đường đi phổ biến:

~~~text
logger.info(...)
    |
    v
[logger level / filter sớm] -> [tạo LogEvent + chụp context]
    |
    +--> [appender CONSOLE] --> log chung
    |
    +--> [filter tenantId] --> [appender TENANT_A] --> log chọn lọc
    |
    +--> [async queue] --> [worker ghi log] --> đích lưu trữ
~~~

Thứ tự thực tế phụ thuộc backend và nơi gắn filter. Với filter trước khi event được tạo, có thể giảm chi phí tạo/log event. Với filter tại appender, cùng một event có thể được **giữ ở console chung** nhưng **không xuất ở file riêng**.

Các framework như Logback và Log4j 2 có kết quả filter ba trạng thái:

| Kết quả | Ý nghĩa thực tế |
| --- | --- |
| `DENY` | Bỏ sự kiện tại điểm lọc tương ứng |
| `NEUTRAL` | Không đưa ra quyết định cuối; tiếp tục quy tắc/filter tiếp theo hoặc xử lý mặc định |
| `ACCEPT` | Chấp nhận tại giai đoạn lọc hiện tại, có thể bỏ qua những filter cùng giai đoạn |

**Không đồng nhất `ACCEPT` với “được ghi ở mọi appender” hoặc “bỏ qua mọi logger level”**: hiệu lực cụ thể tùy giai đoạn và backend. Chẳng hạn Logback turbo filter và Log4j 2 global filter có thể quyết định từ rất sớm; appender filter chỉ điều khiển appender tương ứng. Vì vậy, khi muốn cho qua một sink riêng, `onMatch=NEUTRAL` và `onMismatch=DENY` thường dễ dự đoán hơn ép `ACCEPT` trong nhiều tầng lọc.

Một quy tắc cần viết rõ cả ba trường hợp: **match**, **mismatch**, **missing/null context**. Với sink chỉ dành cho tenant A, không có `tenantId` nên được xem là **không hợp lệ cho sink đó**; nhưng không nên âm thầm xóa hết ERROR khỏi mọi sink.

## 4. Ví dụ Java 17 chạy độc lập: lọc theo thuộc tính nằm ngay trên LogRecord

`java.util.logging` (JUL) có interface `java.util.logging.Filter`, nhưng **không cung cấp MDC chuẩn giống SLF4J/Logback**. Ta có thể truyền snapshot context tường minh qua `LogRecord` và để handler đọc event đã có context. Mục tiêu ví dụ này là minh họa đúng nguyên lý: quyết định filter dựa vào **metadata được gắn với event**, không dựa vào chuỗi thông điệp hay ThreadLocal tại lúc writer chạy.

Lưu dưới tên **`ContextFilterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ContextFilterDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.context");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CollectingHandler tenantSink = new CollectingHandler();
        tenantSink.setLevel(Level.ALL);
        tenantSink.setFilter(new TenantFilter("tenant-a"));
        logger.addHandler(tenantSink);

        try {
            emit(logger, "tenant-a", "event=created");
            emit(logger, "tenant-b", "event=ignored");
            emit(logger, "tenant-a", "event=updated");

            for (String line : tenantSink.lines) {
                System.out.println(line);
            }
            System.out.println("count=" + tenantSink.lines.size());
        } finally {
            logger.removeHandler(tenantSink);
            tenantSink.close();
        }
    }

    private static void emit(Logger logger, String tenantId, String message) {
        LogRecord event = new LogRecord(Level.INFO, message);
        event.setLoggerName(logger.getName());

        // Snapshot cố định được gắn vào event, không đọc ThreadLocal về sau.
        event.setParameters(new Object[] { Map.of("tenantId", tenantId) });
        logger.log(event);
    }

    private static final class TenantFilter implements Filter {
        private final String allowedTenant;

        private TenantFilter(String allowedTenant) {
            this.allowedTenant = allowedTenant;
        }

        @Override
        public boolean isLoggable(LogRecord event) {
            Object[] parameters = event.getParameters();
            if (parameters == null || parameters.length == 0 ||
                    !(parameters[0] instanceof Map<?, ?> context)) {
                return false; // Không có context: từ chối ở sink riêng này.
            }
            return allowedTenant.equals(context.get("tenantId"));
        }
    }

    private static final class CollectingHandler extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord event) {
            if (!isLoggable(event)) {
                return;
            }
            Map<?, ?> context = (Map<?, ?>) event.getParameters()[0];
            lines.add("tenant=" + context.get("tenantId") +
                    " " + event.getMessage());
        }

        @Override
        public void flush() {
            // Không có I/O hoặc bộ đệm riêng trong ví dụ.
        }

        @Override
        public void close() {
            // Không có tài nguyên ngoài cần đóng.
        }
    }
}
~~~

Lệnh biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ContextFilterDemo.java
java ContextFilterDemo
~~~

**Stdout dự kiến chính xác**:

~~~text
tenant=tenant-a event=created
tenant=tenant-a event=updated
count=2
~~~

Giải thích:

1. Logger và handler đều cho qua mức `INFO`; việc event bị chọn/loại do **`TenantFilter`**. Nếu giảm logger level để chặn một event trước handler, filter không thể khôi phục event đó.
2. `emit(...)` đưa map bất biến của mỗi event vào `LogRecord.parameters`. Đây là **quy ước riêng của ví dụ**, không phải giao thức MDC chuẩn của JUL; formatter khác sẽ không tự hiểu key `tenantId`.
3. `Handler.isLoggable(...)` kiểm tra level và filter gắn với handler. Handler chỉ thêm message khi qua được cả hai.
4. Event của `tenant-b` không đến danh sách của tenant A; không có context cũng bị từ chối tại sink này.
5. Vì chương trình ghi đồng bộ và chỉ có một thread thực thi phát event, thứ tự các dòng thu được xác định. Khi chuyển sang async logging, cần bảo toàn context trên từng event trước khi đưa vào queue.

Ví dụ này cố ý dùng sink trong bộ nhớ để có stdout không phụ thuộc timestamp, console formatter hay backend ngoài. Trong ứng dụng thật, cấu hình để **giữ log lỗi quan trọng ở sink chung** bên cạnh sink có filter; không dùng một sink chọn lọc làm đầu ra vận hành duy nhất.

## 5. SLF4J MDC: tạo context đúng phạm vi

Với SLF4J và backend hỗ trợ MDC, code nghiệp vụ có thể thiết lập các key trước khi phát log. Đoạn minh họa sau cần `org.slf4j:slf4j-api` và backend tương thích; **không phải chương trình JDK độc lập**.

~~~java
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

final class InvoiceService {
    private static final Logger LOG =
            LoggerFactory.getLogger(InvoiceService.class);

    void process(String verifiedTenantId, String requestId) {
        // Phù hợp cả với lời gọi lồng nhau có MDC từ caller.
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("tenantId", verifiedTenantId);
            MDC.put("requestId", requestId);

            LOG.info("event=invoice_started");
            LOG.debug("event=invoice_validation_complete");
            LOG.info("event=invoice_succeeded");
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
~~~

Lưu ý: `verifiedTenantId` phải được xác định từ thông tin đã xác thực và được ứng dụng chấp nhận; không dùng trực tiếp một HTTP header tự khai cho quy tắc cách ly log. Ví dụ giả định `verifiedTenantId` và `requestId` không null theo hợp đồng caller. Nếu không có giá trị cần thiết, hãy chọn chính sách rõ ràng (từ chối xử lý, bỏ key hoặc đưa vào sink chung), thay vì âm thầm gắn giá trị sai.

- `MDC.put(...)` tác động vào context trên **thread hiện tại**.
- `MDC.getCopyOfContextMap()` giữ bản sao trạng thái trước đó; `finally` khôi phục để đoạn code lồng nhau không xóa MDC của caller.
- Với request độc lập trong servlet/worker thread tái sử dụng, bắt buộc có cơ chế dọn context sau khi request kết thúc, kể cả khi ném exception.
- Để hiển thị context, backend phải có layout/encoder thích hợp, ví dụ Logback `%X{tenantId}`, `%X{requestId}`. Việc xuất các trường này **không tự kích hoạt filter**.
- `MDC.putCloseable("key", value)` hỗ trợ dọn một key qua try-with-resources, nhưng API close **remove key**; khi cần bảo toàn context lồng nhau, snapshot/restore như trên diễn đạt mục tiêu rõ ràng hơn.

## 6. Logback: lọc theo MDC tại appender riêng

Logback Classic hỗ trợ **filter trên appender** nhận `ILoggingEvent`. Với sink riêng cho tenant A, ta viết một filter nhỏ đọc **MDC đã gắn với event** bằng `event.getMDCPropertyMap()`. Không cần lấy MDC đang tồn tại trên thread ghi file: async appender có thể xử lý event trên một worker khác.

Trong ứng dụng có Logback Classic, tạo class **`com.example.logging.TenantAppenderFilter`** (snippet phụ thuộc Logback):

~~~java
package com.example.logging;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class TenantAppenderFilter extends Filter<ILoggingEvent> {
    private String tenantId;

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (tenantId == null || tenantId.isBlank()) {
            return FilterReply.DENY;
        }
        String actual = event.getMDCPropertyMap().get("tenantId");
        return tenantId.equals(actual)
                ? FilterReply.NEUTRAL
                : FilterReply.DENY;
    }
}
~~~

Cấu hình **`logback.xml`** (giả định class trên có trên classpath và dùng phiên bản Logback tương thích):

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{24} tenant=%X{tenantId} request=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="TENANT_A" class="ch.qos.logback.core.FileAppender">
        <file>tenant-a.log</file>
        <append>true</append>
        <filter class="com.example.logging.TenantAppenderFilter">
            <tenantId>tenant-a</tenantId>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="TENANT_A"/>
    </root>
</configuration>
~~~

Luồng xử lý ở cấu hình này:

- Event có `tenantId=tenant-a`, mức `INFO` trở lên: ghi **console và file TENANT_A**.
- Event có `tenantId=tenant-b` hoặc không có key: vẫn ghi **console**, bị `DENY` ở **TENANT_A**.
- Event `DEBUG`: bị root `INFO` loại theo quy tắc mức log; filter trên TENANT_A không thể làm nó xuất hiện trở lại.
- Nếu trường `tenantId` thiếu, filter từ chối ở sink được chọn (fail-closed tại sink riêng). Console chung vẫn nhận log hợp lệ để điều tra lỗi thiết lập context.

Không viết một `TenantAppenderFilter` mới cho mọi tenant trong hệ thống có hàng nghìn tenant rồi tự tạo hàng nghìn file/appender: chi phí tài nguyên và quản lý trở nên lớn. Khi cần phân tách quy mô lớn, cân nhắc dùng một pipeline log có cấu trúc và cơ chế phân vùng, phân quyền tại hệ thống thu thập.

### Logback TurboFilter và phạm vi toàn cục

Logback còn có **turbo filter** chạy sớm hơn appender filter. Ví dụ bỏ các log được *đánh dấu rõ* là health check khỏi toàn bộ pipeline Logback:

~~~xml
<configuration>
    <turboFilter class="ch.qos.logback.classic.turbo.MDCFilter">
        <MDCKey>logCategory</MDCKey>
        <Value>routine-health-check</Value>
        <OnMatch>DENY</OnMatch>
        <OnMismatch>NEUTRAL</OnMismatch>
    </turboFilter>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%d %-5level %msg%n</pattern></encoder>
    </appender>
    <root level="INFO"><appender-ref ref="CONSOLE"/></root>
</configuration>
~~~

Đây là một **chính sách loại log toàn cục**: bất kỳ event nào có `logCategory=routine-health-check` có thể bị bỏ, kể cả event ERROR, nếu bạn áp dụng quy tắc không xét severity. Chỉ dùng khi chủ đích nghiệp vụ thật sự cho phép. Nếu mục tiêu chỉ giảm nhiễu ở một file hoặc alerting sink, hãy gắn filter ở sink đó. Tránh dùng `OnMatch=ACCEPT` khi muốn giữ nguyên hành vi logger level, vì filter chạy sớm có thể tương tác với lựa chọn mức log.

**Không dùng Janino expression evaluator trong cấu hình cũ mà không kiểm tra phiên bản.** Ở các phiên bản Logback mới, một số evaluator dựa trên Janino đã bị gỡ; filter typed như class ở trên giúp thể hiện logic rõ ràng và dễ kiểm thử hơn.

## 7. Log4j 2: ContextMapFilter tại appender

Log4j 2 có `ThreadContext` để gắn metadata và `ContextMapFilter` để đọc context map trên log event. Tùy chỗ đặt filter, Log4j 2 có thể lọc ở global/logger/appender reference/appender stage.

Ví dụ **`log4j2.xml`** chỉ đưa event của tenant A vào một file riêng, song song với console chung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level tenant=%X{tenantId} - %msg%n"/>
        </Console>

        <File name="TENANT_A" fileName="tenant-a.log">
            <ContextMapFilter onMatch="NEUTRAL" onMismatch="DENY">
                <KeyValuePair key="tenantId" value="tenant-a"/>
            </ContextMapFilter>
            <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="TENANT_A"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Ví dụ code dùng Log4j 2 API (không phải chương trình độc lập):

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.CloseableThreadContext;

final class PaymentProcessor {
    private static final Logger LOG =
            LogManager.getLogger(PaymentProcessor.class);

    void run(String verifiedTenantId) {
        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("tenantId", verifiedTenantId)) {
            LOG.info("event=payment_started");
            LOG.info("event=payment_completed");
        }
    }
}
~~~

Trong file filter trên, `onMatch=NEUTRAL` cho event khớp tiếp tục theo quy tắc bình thường, `onMismatch=DENY` loại event không thuộc A khỏi **File appender**. `KeyValuePair` kiểm tra metadata của event, không kiểm tra chuỗi `%msg`. Với nhiều cặp key/value, `operator="AND"` yêu cầu các điều kiện theo cơ chế filter phải khớp, `OR` cho phép khớp bất kỳ; cần hiểu quy tắc một key có nhiều giá trị trước khi áp dụng. Không mặc định `ContextMapFilter` là công cụ lọc trực tiếp một `MapMessage`: nó kiểm tra **context map**, còn `MapFilter` dành cho dữ liệu dạng map trên message.

Log4j 2 cũng có `DynamicThresholdFilter` để chọn **ngưỡng mức log dựa vào một key context**. Đây là mục tiêu khác so với chỉ định tuyến theo tenant. Ví dụ, có thể tạm chọn mức chi tiết cao hơn cho một nhóm request đang điều tra nhưng phải kiểm soát giới hạn thời gian và khối lượng log. Những filter chạy ở các stage khác nhau tương tác với logger level; cần thử kết quả thực tế với cấu hình backend đang triển khai.

## 8. Thread pool, async logging và rò rỉ context

**Một request có MDC không có nghĩa task trong `ExecutorService` tự mang MDC sang worker.** Thread pool tái sử dụng thread, do đó hai lỗi thường gặp là:

1. **Thiếu context:** request A có `tenantId=A`, nhưng worker không được thiết lập MDC. Appender filter không thấy A và bỏ event khỏi sink A.
2. **Sót context:** worker chạy task A đặt MDC nhưng không dọn; sau đó task B dùng lại thread có thể vô tình xuất `tenantId=A`. Lỗi này đặc biệt nguy hiểm với định tuyến log theo tenant.

Luôn chụp context **ở thread gửi việc** và đặt lại/dọn trong **mỗi lần thực thi task**. Mẫu dưới đây dùng SLF4J MDC, phù hợp với boundary của các **task độc lập**:

~~~java
import java.util.Map;
import org.slf4j.MDC;

final class MdcTaskWrapper {
    static Runnable wrap(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            try {
                MDC.clear();
                if (captured != null) {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                MDC.clear();
            }
        };
    }
}
~~~

Gọi `MdcTaskWrapper.wrap(...)` **ngay tại nơi submit**, lúc thread gọi còn có tenant/request context:

~~~java
executor.execute(MdcTaskWrapper.wrap(() ->
        logger.info("event=async_work_started")));
~~~

Đây là snippet yêu cầu biến `executor`/`logger` được khai báo trong ứng dụng. Nếu dùng `CompletableFuture`, scheduled executor, Reactor hoặc hệ thống messaging, mỗi biên giới bất đồng bộ có thể yêu cầu phương thức propagation riêng. **Không gọi `MDC.get(...)` ở thread writer async rồi tin đó là tenant của event**; hãy dùng context snapshot nằm trên event, như `ILoggingEvent.getMDCPropertyMap()` hoặc context data của Log4j 2.

Mẫu `finally MDC.clear()` thích hợp cho những task độc lập trên pool có chính sách mỗi task bắt đầu với context sạch. Nếu wrapper có thể chạy **lồng nhau** trên cùng thread với context đã thiết lập hợp lệ, hãy chụp và khôi phục map trước đó tại boundary thay vì luôn clear; thiết kế lifecycle phải nhất quán giữa các tầng.

## 9. Chính sách khi thiếu context, khi lỗi và khi có nhiều sink

Một thiết kế tốt nên ghi rõ bảng quyết định. Ví dụ hệ thống giữ console chung và file riêng cho tenant A:

| Sự kiện | Console chung | File TENANT_A | Lý do |
| --- | --- | --- | --- |
| `tenantId=A`, INFO | Giữ | Giữ | Đúng tenant được chọn |
| `tenantId=B`, INFO | Giữ | Bỏ | Không thuộc tenant A |
| Không có `tenantId`, WARN | Giữ | Bỏ | Chưa xác định tenant, còn cần chẩn đoán |
| `tenantId=A`, DEBUG; root=INFO | Bỏ | Bỏ | Bị logger level chặn trước filter appender |
| `tenantId=B`, ERROR | Giữ | Bỏ | Lỗi B không rò sang file riêng A |

Nếu một event chứa tenantId giả do client gửi lên, file lọc theo tenant có thể bị định tuyến sai. **Context filtering không phải ranh giới an toàn truy cập**. Chỉ gắn tenant ID sau xác thực và kiểm tra quyền; hệ thống tập trung vẫn phải enforce quyền truy vấn/retention phù hợp.

**Fail-closed** (thiếu tenant thì không đưa vào sink tenant) phù hợp cho đầu ra tenant-specific; **fail-open sang sink chung** để giữ log vận hành vẫn là quyết định riêng. Với audit/financial/security events, không được tùy tiện loại event vì thiếu metadata; cần kênh ghi bền vững và cơ chế cảnh báo khi context không hợp lệ.

Chú ý các trường hợp:

- **Exception:** ghi throwable ở cấp xử lý phù hợp; filter vẫn có thể bỏ exception nếu gắn toàn cục và không có context.
- **Thay tenant trong một request:** không sửa MDC tùy tiện rồi bỏ quên; scoped boundary và ID được xác thực giúp tránh log lẫn.
- **Thay đổi cấu hình khi runtime đang chạy:** tránh áp dụng rule thay đổi quá rộng mà không có test/rollback; mức log tăng có thể gây tải lớn.
- **Nhiều appender:** xác định event nào đi sink chung, sink theo tenant, audit sink và alert sink; đừng lặp cùng một exception không cần thiết.
- **Async appender:** nếu bộ lọc đặt sau queue, xử lý có thể muộn; cần bảo đảm event ghi nhận context trước khi rời producer. Filter theo context không thay thế backpressure và xử lý mất log do queue overflow.
- **Redaction:** filter quyết định bỏ/giữ nguyên event; nó **không tự che token, password hoặc PII** trong event được giữ. Redaction cần cơ chế riêng trước khi ghi hoặc ở encoder/pipeline thích hợp.

## 10. Kiểm thử filter theo context như thế nào?

Nên viết kiểm thử ở **điểm nhận log** (capturing appender/test handler) thay vì chỉ assert gọi `logger.info(...)`. Dữ liệu đầu vào tối thiểu:

1. Event match `tenantId=tenant-a`: sink TENANT_A nhận đúng một event.
2. Event mismatch `tenantId=tenant-b`: sink riêng không nhận; sink chung vẫn nhận khi level cho phép.
3. Event thiếu/null context: sink riêng từ chối theo chính sách; sink chung ghi diagnostic thích hợp.
4. Event dưới logger level: bị loại ngay cả khi tenant trùng; chứng minh logger level và appender filter là hai tầng khác nhau.
5. Thread pool **một worker**: chạy task A rồi B rồi task thiếu tenant; xác minh context của A không rò sang B, không rò sang task cuối.
6. Event async: tạo event khi tenant=A, rồi đổi MDC producer thành B trước khi writer xử lý; event cũ phải vẫn được xử lý với context A đã chụp.
7. Exception và shutdown: WARN/ERROR quan trọng vẫn có đường ghi đáng tin, kể cả khi sink tenant-specific từ chối.
8. Nhiều filter: đo thực tế kết quả `ACCEPT`/`DENY`/`NEUTRAL` ở đúng vị trí (global/logger/appender) và đối chiếu bảng quyết định đã duyệt.

Không assert thứ tự log giữa nhiều thread nếu scheduler không bảo đảm. Dùng `taskId`/`requestId` và mã event để đối chiếu. Với cấu hình XML của Logback/Log4j 2, test integration phải dùng đúng backend và version của ứng dụng, vì một file cấu hình đẹp nhưng không được load thì không có tác dụng.

### Các chỉ số nên theo dõi

Khi filter được dùng để giảm dung lượng hay định tuyến, hãy đo lượng log **trước và sau** từng rule, tần suất thiếu context, drop do queue, lỗi appender, số record ở sink chung và sink riêng. Nếu tăng đột ngột các event thiếu `tenantId`, đó có thể là lỗi truyền context trong async boundary, không phải lưu lượng hợp lệ đã giảm.

## 11. Lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh và sửa |
| --- | --- | --- |
| `%X{tenantId}` trống | Chưa đặt MDC, đang log ở thread khác hoặc context bị xóa sớm | Kiểm tra boundary và MDC snapshot từng task |
| Có tenant trong message nhưng filter không match | Filter đọc metadata, message chỉ là chuỗi | Gắn `tenantId` vào MDC/context map đúng cách |
| Log của A lọt file B | MDC sót trên thread pool hoặc tenant ID không đáng tin | Dọn trong finally, xác thực tenant và test tái sử dụng thread |
| Không thấy ERROR khi thiếu tenant | Đặt filter `DENY` quá rộng/toàn cục | Giữ sink chung đáng tin, chỉ lọc sink riêng |
| DEBUG mất dù tenant match | Logger level hoặc filter khác đã chặn | Kiểm tra cấu hình logger và mọi stage filter |
| Một event hiện nhiều lần | Appender bị gắn lặp hoặc additivity không chủ đích | Kiểm tra refs, logger parent và additivity |
| Filter không có tác dụng | Cấu hình không nạp, sai class/backend, sai key hoặc tên file | Kiểm tra startup diagnostics, classpath, effective config |
| Log xuất hiện sai tenant sau callback async | Callback không nhận context gốc | Truyền snapshot qua từng async boundary |
| Mất log khi queue đầy | Async appender có chính sách discard | Theo dõi drop/backpressure; không đổ lỗi tất cả cho context filter |
| Chọn tenant bằng `message.contains(...)` | Dựa vào chuỗi dễ thay đổi hoặc dữ liệu người dùng | Đổi sang field context có kiểm soát |

## 12. Quy trình áp dụng thực tế

Trước khi đưa filter theo context vào ứng dụng:

1. Định nghĩa rõ **mục tiêu**: bỏ log gây nhiễu, chọn log để debug hay định tuyến sang sink riêng; đừng dùng một cấu hình cho ba mục tiêu khác nhau.
2. Chọn **key và nguồn đáng tin**; chuẩn hóa field và quy tắc khi thiếu/mismatch.
3. Xác định **stage**: global/turbo để loại sớm, appender-level để tác động từng sink. Viết bảng quyết định gồm INFO/DEBUG/ERROR và từng giá trị context.
4. Đặt context trong phạm vi request/job; truyền và dọn qua mọi async boundary.
5. Giữ một **đường log chung/đường sự cố** theo chính sách hệ thống, đặc biệt với lỗi bất thường.
6. Dùng test nhỏ cho match/mismatch/missing, rồi test integration với backend thật và thread pool tái sử dụng.
7. Theo dõi số lượng log được nhận/bị bỏ, hiệu năng và khả năng cách ly truy vấn tại hệ thống thu thập.

**Ghi nhớ:** context filter dùng metadata của event để chọn log đúng ngữ cảnh. Lọc tại appender cho phép giữ một kênh log chung và thêm kênh chọn lọc. Giá trị MDC phải được thiết lập đúng, truyền qua async boundary và dọn sạch; filter không thay thế mức log, redaction hay kiểm soát quyền truy cập.

### Tài liệu tham khảo chính thức

- Logback — [Filters](https://logback.qos.ch/manual/filters.html) và [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html).
- Apache Log4j 2 — [Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) và [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Java 17 — [java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html), [Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).