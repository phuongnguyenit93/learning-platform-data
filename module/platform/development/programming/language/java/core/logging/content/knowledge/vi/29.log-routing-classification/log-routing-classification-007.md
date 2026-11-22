# Tách log theo tenant trong Java Core Logging

## 1. Bài toán: một ứng dụng, nhiều tenant, nhiều dòng log

Trong hệ thống **multi-tenant**, nhiều khách hàng/tổ chức (tenant) dùng chung một dịch vụ. Nếu log của các tenant trộn trong một luồng mà không có định danh đáng tin cậy, việc điều tra lỗi, áp chính sách lưu trữ, đối chiếu chi phí và cấp quyền xem log rất khó. **Tách log theo tenant** là gắn định danh tenant cho từng sự kiện, rồi **định tuyến hoặc phân vùng** sự kiện đến nơi lưu trữ phù hợp, sao cho khi cần có thể truy vấn riêng tenant A mà không trộn dữ liệu của B.

Ví dụ một tiến trình xử lý ba request:

~~~text
tenant=acme request=req-101 event=invoice_created
tenant=nova request=req-102 event=invoice_created
tenant=acme request=req-103 event=invoice_paid
~~~

Đầu ra mong muốn có thể là hai file riêng `acme.log` và `nova.log`, hai stream riêng, hai chỉ mục có kiểm soát quyền, hoặc **một luồng log có cấu trúc chứa `tenantId`** với chính sách phân vùng ở log collector. Không bắt buộc tạo một file vật lý cho mỗi tenant.

**Phân biệt ba thao tác:** gắn trường `tenantId` vào sự kiện là **enrichment**; quyết định sự kiện đi tới appender/stream nào là **routing**; loại bỏ event khỏi một sink không phù hợp là **filtering**. Hệ thống phân quyền tại nơi lưu trữ là lớp **access control** riêng. Bài học này tập trung vào *định tuyến và phân vùng log theo tenant* cùng các rủi ro khi vận hành.

## 2. Chọn mô hình tách log phù hợp

| Mô hình | Cách hoạt động | Khi phù hợp | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Luồng chung có cấu trúc** | Mọi event mang `tenantId`, collector/index hỗ trợ lọc và phân quyền | Nhiều tenant, hạ tầng container, hệ thống log tập trung | Nếu phân quyền query sai, log tenant khác vẫn có thể bị lộ |
| **Collector route theo tenant** | Ứng dụng ghi JSON/stdout; collector đẩy sang stream/index/bucket theo tenant | Cần tách lưu trữ nhưng muốn ứng dụng đơn giản | Cần bảo đảm collector không tin field chưa được xác thực, có retry và quan sát drop |
| **File riêng mỗi tenant** | Logger tạo hoặc chọn appender/file theo `tenantId` | Số tenant ít, giới hạn rõ, nhu cầu vận hành cụ thể | Nhiều file descriptor, chi phí rollover, tài nguyên tăng theo tenant, rủi ro đường dẫn |
| **Sink/triển khai riêng** | Mỗi tenant dùng tài nguyên logging độc lập | Ràng buộc cách ly hoặc tuân thủ cao | Tăng chi phí và độ phức tạp triển khai |

Với hệ thống có hàng trăm/hàng nghìn tenant, thường ưu tiên **structured log + collector + RBAC tại backend**. File riêng mỗi tenant là một lựa chọn thực tế cho số lượng tenant được quản lý chặt, không phải mặc định tối ưu. Không đánh đồng việc có file `acme.log` với việc file đã được mã hóa, bảo vệ quyền đọc, sao lưu và lưu giữ theo đúng cam kết.

### Luồng chung và luồng riêng cùng tồn tại

Một kiến trúc có thể gửi cùng event tới hai đích:

~~~text
Request / Job
   |
   v
Xác thực -> xác định tenant chuẩn -> gắn tenantId, requestId
   |
   v
LogEvent (metadata bất biến theo sự kiện)
   |
   +----> COMMON (log vận hành, quyền chỉ dành cho operator)
   |
   +----> ROUTER theo tenantId
                 |
                 +---- acme -> sink của acme
                 +---- nova -> sink của nova
                 +---- unknown/invalid -> sink cách ly/quarantine
~~~

`COMMON` giúp điều tra sự cố startup, infrastructure hoặc request thiếu tenant. **Không cấp cho người dùng tenant quyền đọc COMMON** chỉ vì họ được xem log tenant riêng. Với sự kiện không thể xác định tenant, cần chính sách rõ ràng: đưa vào kênh nội bộ `unknown`, cảnh báo và điều tra; không tự động gán nó cho tenant mặc định.

## 3. Tenant ID phải đến từ đâu?

**Tenant ID dùng để routing phải được rút ra từ ngữ cảnh đã xác thực và được ứng dụng kiểm tra quyền.** Ví dụ: sau khi xác thực token, middleware liên kết principal với tenant được phép truy cập; worker đọc tenant từ thông tin job đã được kiểm tra; consumer thông điệp xác nhận quyền/nguồn thông điệp trước khi quyết định tenant.

Một HTTP header tự khai như `X-Tenant-Id: acme` hoặc query parameter `?tenant=nova` **không đủ tin cậy** để chọn file, bucket hoặc chỉ mục. Chỉ dùng chúng như input để kiểm tra, không coi là kết luận về tenant sở hữu event.

Phân biệt:

- **`tenantId`:** mã định danh tenant canonical, ổn định, có thể dùng làm routing key; hạn chế cardinality và chiều dài.
- **`requestId`/`jobId`:** định danh một lần xử lý để nối các log cùng request/job.
- **`traceId`/`spanId`:** liên kết trace phân tán; không thay thế `tenantId` khi phân vùng hay cấp quyền log.
- **`userId`:** cá nhân trong tenant; có thể nhạy cảm, không nên dùng làm tên file và thường không cần cho routing.

Nếu đưa tenant ID vào **tên file**, cần dùng mã nội bộ an toàn, có whitelist kiểu `[A-Za-z0-9_-]{1,40}` và giới hạn số lượng giá trị có thể tạo. Chặn đường dẫn tương đối (`..`), dấu phân cách, ký tự điều khiển, cú pháp nội suy, ký tự đặc biệt và chuỗi quá dài. Việc kiểm tra ký tự **không chứng minh caller có quyền tenant đó**; hai việc này phải làm riêng.

Quy tắc khi thiếu tenant cũng là một phần thiết kế: `unknown` không được đại diện cho một tenant có thật; nếu không đủ dữ liệu xác định tenant thì route nội bộ hoặc từ chối ghi vào sink tenant riêng.

## 4. Gắn tenant và request vào MDC theo đúng vòng đời

Với ứng dụng dùng **SLF4J + backend hỗ trợ MDC**, ta có thể gắn tenant vào `MDC (Mapped Diagnostic Context)` của thread phát log. Bên dưới là đoạn helper dành cho ứng dụng (phải có SLF4J và backend tương thích), **không phải chương trình chỉ dùng JDK**:

~~~java
import java.util.Map;
import java.util.Objects;
import org.slf4j.MDC;

public final class TenantLogScope {
    private TenantLogScope() {}

    public static void run(String authenticatedTenantId,
                           String requestId,
                           Runnable action) {
        Objects.requireNonNull(action, "action");

        // Kiểm tra format; quyền với tenant phải được xác minh trước đó.
        if (authenticatedTenantId == null ||
                !authenticatedTenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("invalid tenant id");
        }

        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("tenantId", authenticatedTenantId);
            if (requestId == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", requestId);
            }
            action.run();
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

Một nơi sử dụng sau khi đã **xác thực và ủy quyền** tenant:

~~~java
TenantLogScope.run(verifiedTenantId, requestId, () -> {
    logger.info("event=invoice_started invoiceId={}", invoiceId);
    performInvoiceWork();
    logger.info("event=invoice_finished invoiceId={}", invoiceId);
});
~~~

Đoạn gọi cần các biến `verifiedTenantId`, `requestId`, `logger`, `invoiceId` và hàm `performInvoiceWork()` do ứng dụng định nghĩa. Việc gắn `tenantId` vào MDC chỉ có ý nghĩa nếu backend **chụp MDC khi tạo LogEvent** hoặc có thiết kế propagation phù hợp; nó không tự tạo file riêng hay cấp quyền đọc file.

`finally` là bắt buộc khi thread server/worker được tái sử dụng. Ví dụ request A đặt `tenantId=acme`, nhưng sau khi xử lý quên cleanup; request B đi trên cùng thread có thể bị route nhầm vào `acme.log`. Mẫu trên lưu/khôi phục context trước đó để hỗ trợ việc gọi lồng nhau. Nếu application framework tự quản lý request scope, hãy xác minh ai chịu trách nhiệm dọn để không bỏ sót ở error path.

### Xử lý bất đồng bộ và thread pool

MDC thường gắn với **thread hiện tại**, nên một task được gửi vào `ExecutorService`, `CompletableFuture` hoặc callback có thể chạy ở thread khác không mang tenant của caller. Worker cũng có thể giữ MDC cũ nếu không được dọn.

Chụp snapshot ở **thread gửi task**, thiết lập trong worker, rồi khôi phục context ban đầu của worker:

~~~java
import java.util.Map;
import org.slf4j.MDC;

final class MdcPropagation {
    static Runnable wrap(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> prior = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (prior == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(prior);
                }
            }
        };
    }
}
~~~

Gọi `wrap(...)` tại thời điểm **submit**, khi caller còn ở đúng tenant scope:

~~~java
executor.execute(MdcPropagation.wrap(() ->
    logger.info("event=invoice_email_queued")));
~~~

Đây là snippet yêu cầu `executor` và `logger` có sẵn. Với task độc lập trên pool, cần bảo đảm context ban đầu của worker sạch; việc khôi phục `prior` của worker chỉ bảo toàn trạng thái, không chữa được một context cũ đã bị rò từ code khác. Cần đặt quy ước **không để lại MDC giữa các task độc lập** tại boundary của executor/framework. Với messaging hoặc scheduler, tenant phải được truyền trong envelope/job metadata đã xác thực; đừng dựa vào `InheritableThreadLocal` để truyền tenant theo từng task trong pool.

**Quan trọng khi async logging:** filter hoặc router chạy trong thread ghi log phải đọc **metadata của sự kiện** (event MDC/context map đã capture), không gọi `MDC.get("tenantId")` trên thread ghi và tưởng đó là tenant gốc.

## 5. Ví dụ Java 17 độc lập: định tuyến theo metadata của từng LogRecord

`java.util.logging` (JUL) thuộc JDK, không có MDC chuẩn giống Logback. Để học cơ chế routing mà **không cần dependency**, ví dụ này đặt một `TenantContext` lên từng `LogRecord`, rồi dùng `Handler` tự viết chọn sink trong bộ nhớ. Đây là cơ chế minh họa, không phải production file router. Nó cố tình dùng danh sách tenant được cho phép và giữ event thiếu tenant trong `unrouted`.

Lưu file **`TenantRoutingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class TenantRoutingDemo {
    private static final Set<String> ALLOWED = Set.of("acme", "nova");

    record TenantContext(String tenantId, String requestId) {}

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.tenant.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        TenantHandler handler = new TenantHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            emit(logger, "acme", "req-101", "invoice_created");
            emit(logger, "nova", "req-102", "invoice_created");
            emit(logger, "acme", "req-103", "invoice_paid");
            emit(logger, null, "req-104", "tenant_missing");
            handler.printAll();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }

    private static void emit(Logger logger, String tenantId,
                             String requestId, String name) {
        LogRecord record = new LogRecord(Level.INFO, "event=" + name);
        record.setLoggerName(logger.getName());
        // Quy ước của demo: snapshot context nằm trên chính event.
        record.setParameters(new Object[] {
                new TenantContext(tenantId, requestId)
        });
        logger.log(record);
    }

    private static final class TenantHandler extends Handler {
        private final Map<String, List<String>> buckets =
                new LinkedHashMap<>();

        TenantHandler() {
            buckets.put("acme", new ArrayList<>());
            buckets.put("nova", new ArrayList<>());
            buckets.put("unrouted", new ArrayList<>());
        }

        @Override
        public synchronized void publish(LogRecord event) {
            if (!isLoggable(event)) {
                return;
            }

            Object[] parameters = event.getParameters();
            if (parameters == null || parameters.length != 1 ||
                    !(parameters[0] instanceof TenantContext ctx)) {
                buckets.get("unrouted").add("invalid_context");
                return;
            }

            String tenant = ctx.tenantId();
            String target = tenant != null && ALLOWED.contains(tenant)
                    ? tenant : "unrouted";
            buckets.get(target).add("requestId=" + ctx.requestId()
                    + " " + event.getMessage());
        }

        synchronized void printAll() {
            for (String target : List.of("acme", "nova", "unrouted")) {
                System.out.println(target + ": " + buckets.get(target));
            }
        }

        @Override
        public void flush() {
            // Bộ nhớ, không có buffer I/O cần flush.
        }

        @Override
        public void close() {
            // Bộ nhớ, không có tài nguyên ngoài cần đóng.
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TenantRoutingDemo.java
java TenantRoutingDemo
~~~

**Stdout xác định** với chương trình ở trên:

~~~text
acme: [requestId=req-101 event=invoice_created, requestId=req-103 event=invoice_paid]
nova: [requestId=req-102 event=invoice_created]
unrouted: [requestId=req-104 event=tenant_missing]
~~~

Giải thích:

1. `emit(...)` gắn một `TenantContext` vào **chính `LogRecord`** bằng `setParameters(...)`. Đây là hợp đồng của demo, **không phải MDC chuẩn của JUL**; formatter/handler khác không tự hiểu kiểu record này.
2. `TenantHandler` quyết định đích dựa vào `ctx.tenantId()`; không parse message `"event=..."`. Sự kiện của `acme` không được thêm vào list của `nova`.
3. Tenant thiếu hoặc không có trong allowlist đi vào `unrouted`, không tự tạo một sink tùy ý.
4. Vì demo tạo event tuần tự và handler trong bộ nhớ, thứ tự các phần tử xác định. Với producer đa luồng, cần thiết kế thứ tự, đồng bộ và I/O phù hợp.
5. `Logger.setUseParentHandlers(false)` ngăn log demo truyền tới handler của root và in trùng hoặc làm stdout/stderr thay đổi. `handler.isLoggable(event)` vẫn áp dụng level và filter của handler nếu có.

Bài học chính của ví dụ là **tách routing key khỏi nội dung chuỗi log**, chụp nó theo từng event, đưa event vào sink đã kiểm soát và có đường xử lý `unknown`. Ở production, backend logging thực tế đã cung cấp appender/router, retry, rolling và lifecycle; không nên sao chép handler trong bộ nhớ này để ghi file nghiệp vụ.

## 6. Logback: dùng SiftingAppender tạo file theo tenant

Với **SLF4J + Logback Classic**, `SiftingAppender` có thể chọn appender con dựa trên một MDC key. Khi giá trị `tenantId` xuất hiện lần đầu, nó tạo appender cho tenant đó theo mẫu trong `<sift>`. Những lần log sau với cùng key có thể dùng lại appender còn sống.

Ví dụ **`logback.xml`** (ứng dụng phải sử dụng Logback; tenant ID đầu vào phải qua bước xác thực và kiểm tra ký tự ở phần 3):

~~~xml
<configuration>
    <appender name="COMMON" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} request=%X{requestId} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="BY_TENANT"
              class="ch.qos.logback.classic.sift.SiftingAppender">
        <timeout>10 minutes</timeout>
        <maxAppenderCount>32</maxAppenderCount>
        <discriminator>
            <key>tenantId</key>
            <defaultValue>unknown</defaultValue>
        </discriminator>
        <sift>
            <appender name="FILE-${tenantId}"
                      class="ch.qos.logback.core.rolling.RollingFileAppender">
                <file>logs/tenants/${tenantId}.log</file>
                <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
                    <fileNamePattern>logs/tenants/${tenantId}.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
                    <maxFileSize>10MB</maxFileSize>
                    <maxHistory>7</maxHistory>
                    <totalSizeCap>100MB</totalSizeCap>
                </rollingPolicy>
                <encoder>
                    <pattern>%d{ISO8601} %-5level tenant=%X{tenantId} request=%X{requestId} - %msg%n</pattern>
                </encoder>
            </appender>
        </sift>
    </appender>

    <root level="INFO">
        <appender-ref ref="COMMON"/>
        <appender-ref ref="BY_TENANT"/>
    </root>
</configuration>
~~~

**Cấu hình này minh họa file-per-tenant cho số tenant được kiểm soát**; các giới hạn là ví dụ, phải chọn dựa vào tải và chính sách lưu trữ. Với MDC `tenantId=acme`, file active `logs/tenants/acme.log` sẽ được dùng. Với MDC `tenantId=nova`, dữ liệu đi `nova.log`. Khi key thiếu, `MDCBasedDiscriminator` dùng `defaultValue=unknown` và có thể tạo `unknown.log`; **chỉ cấp quyền nội bộ** cho file này.

- `<sift>` là mẫu tạo **appender con**; tên, file và rolling policy phải khác nhau theo key. `${tenantId}` trong XML là biến được `SiftingAppender` export sau khi chọn discriminator.
- `timeout` đóng appender con lâu không hoạt động; quá nhỏ gây tạo/đóng liên tục, quá lớn giữ nhiều file descriptor.
- `maxAppenderCount` giới hạn số appender con cùng tồn tại. Đây **không phải** mức đảm bảo số tenant tổng cộng, tổng dung lượng disk hoặc không mất log.
- `maxHistory` và `totalSizeCap` thuộc rolling policy của **mỗi appender con**. Nếu có 100 tenant thì disk không mặc nhiên bị giới hạn ở 100MB toàn hệ thống; còn phải có quota/retention toàn cục và giám sát.
- `COMMON` nhận toàn bộ event đáp ứng root level; `BY_TENANT` route thêm bản sao đến file riêng. Hai sink phục vụ mục đích khác nhau, cần chính sách truy cập khác nhau.
- `SiftingAppender` không phải cơ chế xác thực tenant; khi MDC sai thì nó có thể route sai. Không xây tên file từ HTTP header chưa xác thực.

**Lưu ý bảo mật quan trọng:** một số phiên bản Logback đã thay đổi cách `MDCBasedDiscriminator` xử lý giá trị MDC không an toàn. Dù thư viện có chặn một số ký tự đường dẫn ở bản mới, ứng dụng vẫn phải xác thực tenant, dùng mã nội bộ đã chuẩn hóa, cập nhật phiên bản có bản vá và hạn chế danh sách route hợp lệ. Không dựa vào sanitization của logging framework như ranh giới cách ly dữ liệu. <https://logback.qos.ch/news.html>

### Khi nào không nên dùng SiftingAppender?

Nếu mỗi tenant mới tạo một file/encoder/rolling policy, quá nhiều tenant làm tăng số handle, heap, metadata và I/O. `maxAppenderCount` thấp có thể gây churn khi lưu lượng từ hàng trăm tenant xen kẽ; timeout cao lại giữ nhiều appender mở. Đối với quy mô lớn, dùng structured JSON với `tenantId` rồi tách ở collector/backend thường dễ mở rộng hơn. Trong container có filesystem tạm, tách file trong container còn đòi hỏi sidecar/shipper, volume và chính sách dọn file rõ ràng.

## 7. Log4j 2: RoutingAppender theo ThreadContext

**Log4j 2** dùng `ThreadContext` để đưa metadata vào log event. `RoutingAppender` có thể chọn một appender dựa trên context key, tạo appender động bên trong `Route` và dọn appender ít dùng bằng `IdlePurgePolicy`.

Ví dụ **`log4j2.xml`** chỉ minh họa định tuyến bằng `File`. Nếu triển khai thật phải bổ sung rolling/retention, quyền file và giám sát I/O:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="COMMON" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
        </Console>

        <Routing name="BY_TENANT">
            <Routes pattern="$${ctx:tenantId:-unknown}">
                <Route>
                    <File name="FILE-${ctx:tenantId:-unknown}"
                          fileName="logs/tenants/${ctx:tenantId:-unknown}.log"
                          append="true">
                        <PatternLayout pattern="%d{ISO8601} %-5level tenant=%X{tenantId} - %msg%n"/>
                    </File>
                </Route>
            </Routes>
            <IdlePurgePolicy timeToLive="10" timeUnit="MINUTES"/>
        </Routing>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="COMMON"/>
            <AppenderRef ref="BY_TENANT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Giải thích hai cách nội suy:** `$${ctx:tenantId:-unknown}` trong `Routes.pattern` phải được trì hoãn để tính theo **từng LogEvent**, còn `${ctx:tenantId:-unknown}` trong định nghĩa appender con của `Route` được nội suy khi appender đó được tạo. `IdlePurgePolicy` giúp dừng appender ít dùng; nó không đảm bảo file đã được chuyển đi hoặc được xóa theo retention.

Đoạn code Log4j 2 API cần `log4j-api` và backend Log4j Core tương thích (**không phải chương trình JDK độc lập**):

~~~java
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

final class TenantProcessor {
    private static final Logger LOG = LogManager.getLogger(TenantProcessor.class);

    void process(String verifiedTenantId, String jobId) {
        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("tenantId", verifiedTenantId)
                                           .put("jobId", jobId)) {
            LOG.info("event=job_started");
            LOG.info("event=job_completed");
        }
    }
}
~~~

`verifiedTenantId` phải qua xác thực, kiểm tra ký tự và allowlist nếu dùng để tạo đường dẫn. `CloseableThreadContext` giúp giới hạn thời gian tồn tại của những key được đặt trong phạm vi này, nhưng vẫn phải kiểm tra hành vi cho ngữ cảnh lồng nhau và async. Nếu code gửi task sang thread khác, truyền metadata ở task boundary; không giả định `ThreadContext` tự truyền.

Khi muốn ít tenant cố định, có thể dùng các `Route key="..." ref="..."` trỏ đến appender cấu hình sẵn. Khi số tenant thay đổi, route động dễ dùng nhưng cần giới hạn key, lifecycle và tài nguyên. Đọc tài liệu đúng version Log4j 2: <https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html>.

## 8. Kiến trúc quy mô lớn: tách ở collector thay vì tạo file động

Hệ thống container/microservice thường ghi **một luồng JSON có trường `tenantId`** ra stdout hoặc transport chung có kiểm soát. Log collector nhận bản ghi rồi có thể phân vùng sang index/stream/bucket hoặc giữ chung và áp dụng chính sách truy vấn theo tenant.

Ví dụ JSON minh họa:

~~~json
{
  "timestamp": "2026-11-10T09:40:00Z",
  "level": "INFO",
  "service": "billing",
  "tenantId": "acme",
  "requestId": "req-101",
  "event": "invoice_created",
  "invoiceId": "inv-2042"
}
~~~

Ưu điểm là format và vận chuyển nhất quán, không tạo hàng nghìn file/appender ở JVM, dễ quản lý retention, quota và tìm kiếm. Nhưng cần cấu hình đường đi chính xác:

1. **Producer** gắn `tenantId` đã xác thực vào event, giữ schema/key ổn định, có exception stack trace hợp lý.
2. **Collector** parse dữ liệu, chuẩn hóa hoặc kiểm tra định dạng tenant, có tuyến `unknown/quarantine`. Không tin mù quáng tất cả field do bất kỳ producer nào có thể gửi.
3. **Router/indexer** phân vùng theo tenant hoặc lập chỉ mục trường `tenantId`. Khi có quyền truy cập riêng cho tenant, chính sách truy vấn phải được thực thi **phía máy chủ**, không chỉ đặt filter mặc định ở giao diện.
4. **Storage** áp retention, encryption, access control, audit truy cập và hạn mức của từng tenant theo hợp đồng.
5. **Observability** đo backlog, số event bị drop/retry, mức sử dụng đích, số event `unknown` và số tenant active.

**Cardinality:** gắn `tenantId` vào **trường log** thường hợp lý; đưa từng `tenantId` vào nhãn metrics, partition hoặc index vật lý có thể gây bùng nổ cardinality/tài nguyên. Lựa chọn partition cần căn cứ số tenant và tốc độ log, không suy diễn cứ tenant là cần index riêng.

**Noisy neighbor:** tenant phát hàng triệu dòng DEBUG có thể chiếm băng thông/dung lượng và ảnh hưởng tenant khác. Có thể áp quota hoặc sampling với log chẩn đoán, nhưng không âm thầm sample/drop log audit bắt buộc. Dự trù backpressure, retry và alert khi pipeline quá tải.

## 9. Cách ly dữ liệu: routing đúng chưa đủ

Tách log phục vụ vận hành thường đi kèm yêu cầu bảo mật. Kiểm soát ít nhất các lớp sau:

| Lớp | Rủi ro nếu thiếu | Biện pháp |
| --- | --- | --- |
| Xác thực tenant | Client giả tenant để ghi nhầm sink | Canonical tenant ID từ principal/job đã xác thực, kiểm tra quyền |
| Truyền context | MDC thiếu hoặc sót ở thread pool | Scoped context; capture/restore qua async; test reuse |
| Đường dẫn / route key | Path traversal, route explosion | Whitelist mã nội bộ, chống `..`/separator/interpolation, giới hạn tenant |
| Log payload | Token, mật khẩu, PII bị ghi | Data minimization/redaction trước log, không log toàn bộ body |
| Storage | Người dùng tenant A đọc được log B | RBAC/ACL server-side, encryption, audit, policy riêng |
| Retention | Dữ liệu lưu quá lâu hoặc chiếm hết disk | TTL/rolling/quota/cap theo đúng scope, giám sát tổng dung lượng |
| Hệ thống tập trung | Nhầm index hoặc filter UI dễ bị bỏ qua | Enforce policy ở storage/API; thử cross-tenant access |
| Pipeline lỗi | Event bị bỏ hoặc nằm trong dead letter | Alert, retry, quarantine, reconciliation phù hợp loại log |

Không coi việc kiểm tra `tenantId` ở logging code là ranh giới bảo mật độc lập. Đặc biệt, log **có thể chứa dữ liệu của tenant khác trong payload** nếu code nghiệp vụ vô tình đưa chúng vào message; routing đúng theo metadata cũng không sửa được nội dung sai. Cần kết hợp review dữ liệu được log, kiểm thử truy cập và chính sách lưu trữ.

Log hệ thống như startup, GC, connection pool hoặc stack trace trước khi có request thường không có tenant. Chúng thuộc kênh nội bộ chung, không nên ép vào sink một tenant cụ thể. Nếu một sự kiện thuộc nhiều tenant, hãy định nghĩa chủ sở hữu/quan hệ rõ ràng thay vì đoán từ thread hiện tại.

## 10. Test tách log theo tenant

Đừng chỉ kiểm tra một dòng `logger.info(...)` được gọi; kiểm thử phải quan sát **đích thật**: appender nhận event nào, file/stream nào được tạo, tenant nào có thể đọc dữ liệu đó.

### Bảng test tối thiểu

| Test | Input / tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| A và B luân phiên | `acme`, `nova`, `acme` | Sink A nhận đúng hai event A; B nhận đúng một event B |
| Thiếu tenant | Event không có `tenantId` | Đi `unknown` nội bộ hoặc bị xử lý theo chính sách; không đi ngẫu nhiên vào A/B |
| Tenant lạ | `tenantId=not-allowed` | Không tự tạo sink/file ngoài allowlist nếu policy cấm |
| Tenant giả từ client | Header tự khai trái quyền principal | Bị từ chối/không điều khiển routing |
| Thread pool reuse | Một worker chạy task A rồi B | Không có MDC của A trong event B |
| Async logging | MDC của producer đổi sau khi event A đã enqueue | Event A vẫn route theo context A đã capture |
| Exception path | Task A ném exception | Context được dọn/khôi phục; stack trace được ghi đúng nơi |
| File rollover | Sinh đủ log để rotate | Tệp active/archive đúng tenant; retention/cap hiệu quả |
| Quá nhiều tenant | Tải nhiều key hoặc tenant giả | Không tăng không giới hạn file descriptor và disk |
| Truy cập sink | User A yêu cầu xem sink B | Bị từ chối bởi backend, kể cả bỏ filter UI |
| Quá tải collector | Queue đầy, đích tạm lỗi | Drop/retry/quarantine đo được, có cảnh báo |

Với test đa luồng, dùng `requestId`/`jobId` để so sánh tập event; không assert thứ tự giữa các thread nếu executor không bảo đảm. Đo số lượng event **được nhận** và **được ghi thành công** riêng, vì async queue có thể mất hoặc trì hoãn log. Khi test phân quyền, xác minh cả API/query ở backend, không chỉ nội dung tên file.

### Kịch bản kiểm thử thủ công

1. Gửi request hợp lệ của tenant A và B với ID khác nhau; xem COMMON và hai sink tenant.
2. Gửi request không có tenant, tenant không hợp lệ và tenant cố giả danh B; xác minh fail-closed tại sink riêng.
3. Chạy một pool 1 worker với các task `A → B → missing`, ép callback/exception, rồi xem event thuộc đúng tenant.
4. Bật lượng log đủ tạo rotation và số tenant đủ thử giới hạn appender. Đo thời gian tạo file, số handle và disk.
5. Thu log qua collector đến backend; thử tài khoản tenant A truy vấn dữ liệu B, xác nhận bị chặn ở server.
6. Dừng ứng dụng khi có backlog và kiểm tra những log đã enqueue có được drain theo chính sách hay không.

## 11. Các lỗi vận hành phổ biến

**Lỗi 1 – dựa vào `Thread.currentThread().getName()` để suy ra tenant.** Pool tái sử dụng thread, mỗi worker chạy request của nhiều tenant. Cần metadata riêng cho từng event.

**Lỗi 2 – quên đặt hoặc dọn MDC.** Log không có tenant bị gom vào `unknown`, hoặc log B bị gắn tenant A do context cũ. Cần setup/cleanup tại boundary và propagation qua async.

**Lỗi 3 – dùng tenant ID từ client trong đường dẫn file.** Giá trị có ký tự đặc biệt có thể tạo đường dẫn ngoài dự kiến, khiến route lỗi hoặc tiêu tốn tài nguyên. Phải xác thực tenant và dùng key ổn định đã giới hạn.

**Lỗi 4 – tạo một appender/file cho từng tenant vô hạn.** Tăng file descriptor, số archive và chi phí rollover. Dùng `timeout`/`maxAppenderCount` và giới hạn tenant; cân nhắc collector tập trung.

**Lỗi 5 – coi sink riêng là bảo mật tuyệt đối.** Nếu COMMON hoặc backend index chung ai cũng đọc được, cách ly file riêng chưa đủ. Dùng RBAC/ACL và kiểm tra payload.

**Lỗi 6 – lọc mất log hệ thống và ERROR.** Những event trước khi có tenant không nên bị loại khỏi kênh vận hành. Cần `unknown/quarantine` nội bộ và alert khi tăng bất thường.

**Lỗi 7 – ghi cùng lỗi nhiều lần.** Một exception xuất ở COMMON và sink tenant có thể là **hai bản sao ở hai đích** theo thiết kế; khác với việc service/controller log nguyên stack trace lặp lại trong cùng sink. Khi tính số lỗi, dùng event ID và mô hình duplicate-aware.

**Lỗi 8 – bỏ qua lỗi và thời hạn của async queue.** Logging API trả về không chắc sự kiện đã được đẩy đến disk/collector. Shutdown graceful, kiểm tra backlog và giám sát drop.

**Lỗi 9 – cho rằng quy tắc retention trong child rolling appender là tổng quota.** Mỗi tenant có thể có `totalSizeCap` riêng; muốn quota tổng cần giám sát hoặc chính sách lưu trữ bổ sung.

**Lỗi 10 – xóa/đổi tên tenant nhưng không xử lý log cũ.** Chính sách lưu giữ, legal hold, quyền truy vấn và tên partition cần được quản lý theo vòng đời tenant, không tự xóa log khi tên tenant thay đổi nếu có nghĩa vụ lưu trữ.

## 12. Checklist triển khai

- Xác định mục tiêu tách vật lý hay logic, số tenant dự kiến, lượng log/tenant, giới hạn mở file và yêu cầu retention.
- Chọn tenant canonical từ ngữ cảnh đã xác thực; định nghĩa format/allowlist, đường xử lý tenant thiếu và policy cho log hệ thống.
- Gắn tenant vào **event metadata**; truyền context qua request, job, thread pool và async boundary, luôn cleanup.
- Chọn routing ở appender hay collector; giữ COMMON nội bộ cho điều tra sự cố, xác định appender nào có thể nhìn thấy event.
- Nếu dùng file per tenant, cấu hình rollover, appender timeout, tài nguyên, file permissions, storage quota và shipper.
- Áp redaction và phân quyền query/storage; không đưa secret vào MDC/message, không tin UI filter.
- Viết test A/B/missing, concurrency, path injection, high-cardinality, sink failure và truy cập chéo tenant.
- Theo dõi tenant active, unknown events, drop/retry, disk/handle, chi phí và độ trễ shutdown.

**Điểm cần nhớ:** tách log theo tenant chỉ đáng tin khi **tenant được xác thực**, **metadata được giữ nguyên theo sự kiện**, **route xử lý cả trường hợp thiếu/sai**, và **quyền truy cập được thực thi tại nơi lưu trữ**. Với quy mô lớn, một luồng log có cấu trúc rồi tách ở collector thường dễ vận hành hơn hàng nghìn file động; với quy mô nhỏ và yêu cầu file riêng, `SiftingAppender`/`RoutingAppender` hữu ích nếu kiểm soát đúng lifecycle và bảo mật.

### Tài liệu tham khảo

- Logback Manual — [SiftingAppender, MDC discriminator, timeout, maxAppenderCount](https://logback.qos.ch/manual/appenders-async-sift.html) và [RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html).
- Logback — [MDC](https://logback.qos.ch/manual/mdc.html); [thông báo phiên bản và bản vá](https://logback.qos.ch/news.html).
- Log4j 2 — [RoutingAppender và IdlePurgePolicy](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html); [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Java 17 — [java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html).