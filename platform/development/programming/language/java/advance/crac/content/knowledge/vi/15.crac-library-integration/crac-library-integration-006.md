# Logging bất đồng bộ, metrics và tracing sau restore

Ứng dụng Java thường ghi log, thu thập metrics và gửi trace qua các thành phần chạy nền. Logger bất đồng bộ có queue và worker thread; metrics exporter có thể giữ connection, timer hoặc lịch push; tracing SDK thường có batch processor, buffer span và exporter tới collector. Những thành phần này giúp giảm chi phí trên request, nhưng trạng thái của chúng cũng bị ảnh hưởng khi tiến trình tạo checkpoint CRaC rồi restore sau một khoảng thời gian.

Một Java object vẫn tồn tại trong heap sau restore không có nghĩa worker thread, socket tới collector, file handle, timer hoặc credential mà object đang dùng vẫn hoạt động đúng. Queue có thể chứa event chưa gửi; exporter có thể đang giữ connection đã stale; span đang mở có thể đã vượt qua khoảng thời gian checkpoint; counter trong bộ nhớ có thể tiếp tục từ giá trị cũ hoặc bị nhân bản khi một checkpoint tạo nhiều replica.

Vì vậy, cần quản lý observability theo vòng đời CRaC. Trước checkpoint, dừng phát sinh công việc mới, drain request và background task, flush log/metrics/trace theo giới hạn thời gian, rồi chuẩn bị hoặc đóng các tài nguyên không thể giữ qua checkpoint. Sau restore, làm mới endpoint và credential, khởi động lại worker/exporter theo API được hỗ trợ, xác minh dữ liệu có thể được xuất và chỉ mở readiness khi ứng dụng đã sẵn sàng.

## 1. Ba tín hiệu observability có vòng đời khác nhau

Logging, metrics và tracing đều giúp quan sát ứng dụng, nhưng cách lưu và gửi dữ liệu khác nhau:

| Thành phần | Dữ liệu chính | Hoạt động bất đồng bộ thường gặp | Rủi ro sau restore |
|---|---|---|---|
| Logging | Event log, timestamp, level, MDC/context | Queue, async appender, worker thread, socket/file output | Log còn trong queue, appender worker không chạy, file/socket cũ, event bị gửi trùng hoặc mất |
| Metrics | Counter, gauge, timer, histogram | Scrape scheduler, push registry, exporter thread, aggregation window | Giá trị process cũ, counter regression, gauge tham chiếu object stale, push connection hết hạn |
| Tracing | Span, trace context, parent/child relationship | Batch span processor, exporter queue, worker thread, OTLP/HTTP/gRPC connection | Span chưa kết thúc, batch chưa export, exporter connection stale, context cũ kéo dài qua checkpoint |

Không nên xử lý cả ba bằng một lệnh `flush()` chung. Mỗi thư viện có API và semantics riêng. Hãy xác định chính xác thành phần nào đang sở hữu queue, worker, socket và registry; dùng CRaC integration chính thức nếu phiên bản thư viện có hỗ trợ.

## 2. Vì sao async logging cần được drain?

Với logging đồng bộ, lời gọi log thường ghi trực tiếp qua appender/output trước khi trả về. Với logging bất đồng bộ, lời gọi có thể chỉ đưa một event vào queue rồi trả về; worker thread sẽ ghi event sau đó.

```text
Request thread                 Async logger worker
     |                                  |
     |-- logger.info(event)             |
     |-- enqueue event ---------------->|
     |-- tiếp tục xử lý                 |-- dequeue
     |                                  |-- ghi file / gửi collector
```

Nếu checkpoint xảy ra khi queue còn event:

- Event có thể nằm trong heap và được phục hồi cùng queue.
- Worker thread hoặc trạng thái đồng bộ của logging framework có thể cần xử lý riêng theo runtime.
- File descriptor hoặc socket của appender có thể không còn hợp lệ.
- Event có timestamp cũ có thể được gửi sau restore, làm sai thứ tự quan sát.
- Nếu hệ thống bên ngoài đã nhận event nhưng ứng dụng chưa ghi nhận việc gửi thành công, retry có thể tạo duplicate.

Không phải mọi logging framework đều có cùng hành vi checkpoint/restore. Không giả định queue và worker tự tiếp tục đúng chỉ vì chúng là object Java. Trước checkpoint, hãy dừng log producer ở ranh giới an toàn, chờ queue được xử lý và gọi API flush/drain của framework.

### Queue đầy và chính sách bỏ log

Async appender thường có giới hạn queue. Khi queue đầy, framework có thể block producer, giảm mức log, loại event hoặc áp dụng chính sách khác tùy cấu hình. Trong lúc chuẩn bị checkpoint, nếu worker không ghi được vì output bị lỗi, queue có thể tăng nhanh và làm drain timeout.

Với log audit hoặc log nghiệp vụ bắt buộc, không dựa vào một async queue trong heap như kho lưu trữ bền vững. Hãy dùng một cơ chế lưu trữ có xác nhận ghi, transaction/outbox hoặc hệ thống audit phù hợp. Log chẩn đoán có thể có chính sách drop có kiểm soát, nhưng cần metric đếm số event bị bỏ.

## 3. Trước checkpoint: dừng producer rồi flush log

Trình tự nên là:

1. Chuyển readiness sang refusing traffic và đóng admission gate.
2. Drain request, message handler và background job để không còn tạo log từ công việc nghiệp vụ mới.
3. Dừng scheduler/consumer phát sinh tác vụ mới.
4. Ghi một log thông báo bắt đầu chuẩn bị checkpoint.
5. Gọi API flush/drain của async logger và đợi trong deadline.
6. Nếu appender có socket/file handle không thể giữ an toàn, đóng theo lifecycle API và đánh dấu cần tạo lại sau restore.
7. Chỉ tiếp tục checkpoint khi các log quan trọng đã được xử lý hoặc chính sách lỗi đã được quyết định.

Không nên dừng logger quá sớm. Các callback CRaC hoặc thành phần phục hồi khác có thể cần ghi log khi xử lý lỗi. Nếu đóng hoàn toàn logging system, lỗi ở `afterRestore` có thể không được ghi nhận. Thường nên drain queue trước checkpoint, đóng riêng appender/network resource cần thiết nếu thư viện hỗ trợ, và giữ một fallback logger an toàn cho giai đoạn phục hồi.

### Ví dụ với Log4j2

Log4j2 có async logger và async appender với cơ chế queue/worker riêng. Cách quản lý phụ thuộc cách ứng dụng cấu hình async logger, `AsyncAppender`, context selector và phiên bản Log4j2. Khi tích hợp CRaC, ưu tiên module hoặc hướng dẫn CRaC do đúng phiên bản Log4j2 cung cấp nếu có.

Với một lifecycle manager tự quản lý, ý tưởng tổng quát là đợi các event được xử lý trước khi checkpoint:

```java
import java.time.Duration;

interface LoggingLifecycle {
    void stopAcceptingApplicationEvents();
    boolean awaitQueuesDrained(Duration timeout) throws InterruptedException;
    void flush() throws Exception;
    void closeCheckpointSensitiveOutputs() throws Exception;
    void reopenOutputs() throws Exception;
    void verifyWritable() throws Exception;
}
```

Đây là interface minh họa do ứng dụng định nghĩa, không phải API của Log4j2. Không gọi một phương thức nội bộ của framework bằng reflection chỉ vì nó có tên giống `flush`. Dùng API public và tài liệu của phiên bản cụ thể.

### Ví dụ với Logback

Logback có `LoggerContext` và appender lifecycle. `AsyncAppender` có queue và worker; khi dừng, cần cho worker hoàn tất việc ghi event theo cơ chế shutdown của framework. Không chỉ đóng output file trong khi async appender còn enqueue event.

Ví dụ khái niệm về điều phối context:

```java
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();

// Chỉ gọi stop/restart theo lifecycle đã thiết kế cho ứng dụng.
// LoggerContext.stop() dừng toàn bộ context và không phải thao tác
// flush nhẹ có thể gọi tùy ý trước mỗi checkpoint.
```

`LoggerContext.stop()` là thao tác dừng context, không nên dùng như lệnh flush chung nếu ứng dụng cần tiếp tục ghi log khi checkpoint bị hủy. Việc khởi động lại context và appender sau restore phải được kiểm chứng với cấu hình thực tế; nếu dùng Spring Boot logging initialization, hãy phối hợp với lifecycle của Spring thay vì tự tạo một context thứ hai.

## 4. File appender, socket appender và log collector

### File appender

File appender giữ file handle và có thể tham gia rotation. Sau restore, cần xác minh:

- File descriptor còn hợp lệ và trỏ tới đúng file.
- Log rotation không đổi tên hoặc thay file trong lúc tiến trình checkpoint.
- Quyền truy cập, mount và đường dẫn vẫn phù hợp.
- Không có hai appender cùng ghi một file theo cách gây interleaving hoặc duplicate.
- Buffer được flush trước khi đóng.

Nếu môi trường có thể thay mount hoặc file, đóng appender trước checkpoint rồi mở lại file theo lifecycle framework sau restore. Không tự gọi `close()` file descriptor bên dưới appender; appender cần tự quản lý buffer, lock và trạng thái rotation.

### Socket và network appender

Appender gửi log qua TCP, TLS, HTTP hoặc giao thức riêng có thể giữ socket tới collector. Trong lúc checkpoint, collector có thể restart, DNS đổi IP, certificate rotate hoặc idle timeout đóng connection.

Sau restore, hãy tạo lại network appender/client hoặc dùng cơ chế reconnect được hỗ trợ. Đọc lại endpoint và credential từ cấu hình hiện tại. Nếu appender có retry queue, xác định queue đó giữ event trong bao lâu và cách xử lý duplicate.

### Log event có timestamp cũ

Event được tạo trước checkpoint nhưng gửi sau restore cần giữ timestamp gốc của event, nếu framework ghi timestamp tại thời điểm tạo. Không thay timestamp để giả vờ event xảy ra sau restore. Có thể bổ sung metadata `restore_generation` hoặc instance incarnation để người vận hành phân biệt event được tạo trước và sau checkpoint.

## 5. Metrics: phân biệt counter, gauge, timer và histogram

Metrics registry thường giữ dữ liệu trong bộ nhớ. Khi restore, dữ liệu đó có thể tiếp tục từ snapshot checkpoint. Điều này hữu ích trong một số trường hợp nhưng cần hiểu semantics của từng loại meter.

| Loại meter | Ý nghĩa | Điều cần cân nhắc sau restore |
|---|---|---|
| Counter | Tổng số sự kiện tăng dần trong vòng đời meter | Giá trị có thể tiếp tục từ snapshot; backend có thể thấy counter regression hoặc reset tùy identity/restore |
| Gauge | Giá trị tức thời từ object hoặc callback | Callback có thể tham chiếu object cũ, cache stale hoặc pool đã đóng |
| Timer | Số lần và phân bố thời gian của operation | Sample đang chạy cần kết thúc/drain; accumulated statistics có thể giữ lại nhưng không đại diện khoảng thời gian bị checkpoint |
| Distribution summary/histogram | Phân bố giá trị hoặc bucket | Snapshot có thể giữ dữ liệu cũ; cần xác định window và semantics khi restore |
| Long task timer | Công việc đang chạy trong thời gian dài | Không nên để sample đại diện cho một operation bị gián đoạn qua checkpoint nếu nghiệp vụ không định nghĩa rõ |

### Counter không phải dữ liệu nghiệp vụ bền vững

Counter trong registry thường là số liệu observability theo process hoặc instance. Không dùng nó làm nguồn sự thật cho số đơn hàng, số tiền hoặc số giao dịch đã commit. Những dữ liệu nghiệp vụ đó phải được lưu trong database hoặc hệ thống ledger phù hợp.

Nếu checkpoint được restore cùng một instance identity, counter có thể tiếp tục từ giá trị cũ. Nếu backend đã scrape giá trị trước checkpoint, giá trị sau restore có thể thấp hơn do checkpoint được tạo trước lần scrape cuối; backend có thể hiểu đó là reset. Nếu một checkpoint được clone thành nhiều replica với cùng metric labels, nhiều tiến trình có thể xuất cùng một counter ban đầu và làm dữ liệu bị nhập nhằng.

Giải pháp là xác định rõ metric identity:

- Dùng nhãn service, environment, version và instance/pod theo mô hình backend.
- Mỗi incarnation cần có identity phù hợp để backend phân biệt tiến trình mới nếu semantics yêu cầu.
- Tránh thêm UUID không giới hạn vào mọi metric label vì cardinality có thể tăng nhanh; dùng label instance vốn đã được backend quản lý hoặc một chiến lược generation có retention.
- Dùng counter backend có khả năng nhận diện reset đúng cách.
- Dùng database/event store cho số liệu nghiệp vụ cần tính chính xác qua restart/restore.

Không reset mọi counter một cách máy móc. Nếu backend kỳ vọng counter liên tục theo instance, reset có thể gây sai; nếu instance mới được tạo, việc giữ counter snapshot có thể làm số liệu trùng. Hãy chọn semantics và identity nhất quán.

### Gauge phải trỏ tới trạng thái hiện tại

Gauge thường đọc giá trị từ một object khi backend scrape. Ví dụ, gauge active database connections có thể giữ reference tới pool cũ đã đóng. Sau restore, nếu pool mới được tạo nhưng gauge vẫn đọc pool cũ, metric sẽ sai hoặc gây exception.

Có thể dùng holder thay thế atomically:

```java
final class PoolMetricsState {
    private final AtomicReference<DataSourceMetricsView> current =
            new AtomicReference<>();

    void install(DataSourceMetricsView view) {
        current.set(view);
    }

    int activeConnections() {
        DataSourceMetricsView view = current.get();
        return view == null ? 0 : view.activeConnections();
    }
}
```

`DataSourceMetricsView` là abstraction do ứng dụng định nghĩa. Gauge nên đọc từ holder hiện tại thay vì giữ trực tiếp object pool đã bị thay thế. Khi pool mới sẵn sàng, cập nhật holder; khi pool đang phục hồi, có thể trả trạng thái unavailable hoặc giá trị phù hợp theo quy ước metric.

## 6. Pull metrics và push metrics sau restore

### Pull model: Prometheus scrape

Với pull model, Prometheus hoặc collector gọi endpoint metrics của ứng dụng. Không nhất thiết có một worker trong ứng dụng phải gửi metrics liên tục, nhưng web endpoint, registry và meter vẫn cần hoạt động.

Sau restore:

- Đảm bảo endpoint metrics được phục vụ bởi embedded server đã bind lại.
- Xác nhận registry chứa meter đúng và gauge trỏ tới object hiện tại.
- Xác định instance label có thay đổi theo incarnation hay không.
- Hiểu rằng scrape đầu tiên sau restore có thể thấy counter snapshot cũ.
- Tránh để một replica clone checkpoint dùng chung label khiến time series bị nhập nhằng.

Prometheus phân biệt time series theo metric name và labels. Nếu nhiều replica cùng xuất một series với cùng labels, dữ liệu có thể bị xung đột hoặc ghi đè tùy scrape target/configuration. Hãy dùng target/instance identity đúng với topology.

### Push model: registry gửi định kỳ

Một số registry push metrics theo chu kỳ tới backend. Chúng thường giữ scheduler, exporter client, socket hoặc authentication token. Trước checkpoint, dừng push schedule, flush lần cuối nếu API hỗ trợ và đóng exporter resource cần thiết. Sau restore, tạo exporter/client mới với endpoint và credential hiện tại, sau đó khởi động push schedule mới.

Không giả định một scheduler đã shutdown có thể khởi động lại. Nếu exporter đã đóng, thường cần tạo exporter/registry mới hoặc dùng lifecycle integration của thư viện. Cần bảo đảm không có hai scheduler push cùng một meter set sau restore.

### Micrometer

Micrometer cung cấp abstraction `MeterRegistry` và nhiều registry implementation. Cách phục hồi phụ thuộc registry cụ thể, ví dụ Prometheus pull registry, registry push hoặc vendor-specific registry. `MeterRegistry.close()` thường là thao tác đóng registry và có thể dừng publisher; không xem nó như một lệnh flush nhẹ có thể gọi rồi dùng lại cùng object.

Khi tự quản lý lifecycle:

- Xác định registry nào là pull và registry nào có worker push.
- Dừng scheduler/exporter trước checkpoint nếu cần.
- Giữ hoặc tái tạo meter theo semantics mong muốn.
- Rebind gauge sau khi pool/client được tạo lại.
- Tạo registry/exporter mới nếu implementation cũ đã close.
- Kiểm tra meter không bị đăng ký trùng khi ApplicationContext vẫn còn tồn tại.

Nếu Spring Boot hoặc Micrometer version đang dùng có CRaC integration, ưu tiên tích hợp đó. Không đăng ký thêm một resource tự đóng registry mà integration chính thức đã sở hữu.

## 7. Tracing: span đang mở và batch exporter

Distributed tracing thường tạo span cho request, database call, HTTP client và background job. OpenTelemetry SDK có thể dùng `BatchSpanProcessor` để giữ span trong queue rồi gửi theo batch qua exporter như OTLP.

```text
Request thread                 BatchSpanProcessor worker
     |                                  |
     |-- end(span)                      |
     |-- enqueue completed span ------->|
     |-- trả response                   |-- batch spans
                                        |-- export tới collector
```

Nếu checkpoint xảy ra khi span chưa kết thúc hoặc batch chưa được export:

- Span đang mở có thể đại diện cho operation kéo dài qua khoảng thời gian tiến trình không chạy.
- Queue có thể chứa span chưa gửi.
- Exporter có thể giữ gRPC/HTTP connection hoặc DNS state cũ.
- Batch worker có thể cần dừng và tạo lại.
- Trace context trong `ThreadLocal` hoặc executor task có thể không còn phù hợp khi công việc được resume sau restore.

Thông thường, hãy drain request và background task để span nghiệp vụ kết thúc trước checkpoint, sau đó gọi `forceFlush` với timeout. Không cố giữ một request span đang mở qua nhiều phút checkpoint trừ khi hệ thống tracing và nghiệp vụ có semantics rõ ràng cho operation bị tạm dừng.

### Force flush và shutdown là hai việc khác nhau

Trong OpenTelemetry Java SDK, `SdkTracerProvider.forceFlush()` yêu cầu các processor flush dữ liệu đã nhận vào exporter. `shutdown()` đóng provider và processor. Sau khi shutdown, không nên giả định cùng provider có thể được dùng lại.

Nếu cần đóng exporter/socket trước checkpoint, có thể phải tạo `SdkTracerProvider`, processor và exporter mới sau restore. Nếu chỉ force flush mà giữ exporter, vẫn cần kiểm tra connection sau restore hoặc dùng exporter có reconnect được hỗ trợ.

Ví dụ gọi flush có giới hạn:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

final class TracingLifecycle {
    private final SdkTracerProvider tracerProvider;

    TracingLifecycle(SdkTracerProvider tracerProvider) {
        this.tracerProvider = tracerProvider;
    }

    void flushBeforeCheckpoint(Duration timeout) {
        CompletableResultCode result = tracerProvider.forceFlush();
        boolean completed = result.join(
                timeout.toMillis(), TimeUnit.MILLISECONDS
        );
        if (!completed) {
            throw new IllegalStateException("Tracing flush timed out");
        }
        if (!result.isSuccess()) {
            throw new IllegalStateException("Tracing flush failed");
        }
    }
}
```

Đây là ví dụ API SDK minh họa. Cần xử lý kết quả timeout/failure theo phiên bản OpenTelemetry đang dùng và truyền lỗi lên callback nếu trace quan trọng không thể flush theo yêu cầu. Không chặn vô hạn trong callback.

### Không giữ ThreadLocal trace context cho công việc được resume

Trace context thường được truyền qua request header, context propagation hoặc task wrapper. Một `ThreadLocal` còn giữ context cũ trong heap không chứng minh context đó còn thuộc về công việc hiện tại sau restore.

Với công việc có thể tiếp tục sau checkpoint, hãy lưu trạng thái nghiệp vụ bền vững. Khi resume, có thể tạo span mới và dùng trace context cũ làm link nếu hệ thống đã lưu context theo cách được kiểm soát và semantics tracing cho phép. Không tiếp tục một span đã mở từ trước checkpoint chỉ để giữ một trace dài xuyên qua khoảng downtime.

Với message queue, trace context nên được truyền trong message header/metadata. Khi consumer xử lý lại message sau restore, tạo span mới theo context được truyền và idempotency của công việc.

## 8. Tích hợp OpenTelemetry SDK sau restore

Một mô hình lifecycle thường dùng:

### Trước checkpoint

1. Ngừng nhận request và trigger mới.
2. Drain request/background work để span nghiệp vụ hoàn tất.
3. Dừng tạo span mới từ scheduler/consumer.
4. Gọi `forceFlush()` cho tracer provider và đợi kết quả trong deadline.
5. Flush hoặc push metrics theo registry implementation.
6. Drain async logging queue và flush appender.
7. Nếu exporter cần đóng, shutdown theo API chính thức và đánh dấu cần tạo mới sau restore.

### Sau restore

1. Khởi tạo logging output đủ sớm để ghi nhận lỗi phục hồi.
2. Đọc lại endpoint, TLS certificate, token và cấu hình observability hiện tại.
3. Tạo lại network appender hoặc xác minh file appender.
4. Tạo lại metrics exporter/push scheduler nếu implementation cũ đã đóng; cập nhật gauge tới pool/client mới.
5. Tạo lại OpenTelemetry exporter, span processor và provider nếu đã shutdown.
6. Xuất một restore event/metric có incarnation ID mới.
7. Kiểm tra khả năng export tới collector.
8. Chuyển readiness sang accepting traffic.

Không cần tạo lại toàn bộ instrumentation API nếu framework cho phép giữ tracer/meter facade và thay provider theo một cơ chế được hỗ trợ. Nhưng không được thay provider tùy tiện nếu các bean đã giữ reference tới provider cũ. Hãy tạo lifecycle manager làm chủ provider và inject facade ổn định, hoặc khởi tạo ApplicationContext theo integration CRaC của framework.

## 9. Ví dụ CRaC resource điều phối observability

Các interface trong ví dụ là abstraction do ứng dụng định nghĩa. Chúng giúp tách logic CRaC khỏi API cụ thể của Logback, Log4j2, Micrometer hoặc OpenTelemetry.

```java
import java.time.Duration;

import org.crac.Context;
import org.crac.Resource;

final class ObservabilityResource implements Resource {
    private final ApplicationWorkLifecycle work;
    private final LoggingLifecycle logging;
    private final MetricsLifecycle metrics;
    private final TracingLifecycle tracing;
    private final Duration flushTimeout;

    ObservabilityResource(
            ApplicationWorkLifecycle work,
            LoggingLifecycle logging,
            MetricsLifecycle metrics,
            TracingLifecycle tracing,
            Duration flushTimeout) {
        this.work = work;
        this.logging = logging;
        this.metrics = metrics;
        this.tracing = tracing;
        this.flushTimeout = flushTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        work.stopAcceptingNewWork();
        work.stopBackgroundTriggers();
        work.awaitInFlightWork(flushTimeout);

        tracing.forceFlush(flushTimeout);
        metrics.flushOrSnapshot(flushTimeout);
        logging.awaitQueuesDrained(flushTimeout);
        logging.flush();

        tracing.closeCheckpointSensitiveExporter();
        metrics.closeCheckpointSensitiveExporter();
        logging.closeCheckpointSensitiveOutputs();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        logging.reopenOutputs();
        logging.verifyWritable();

        metrics.recreateExportersAndRebindMeters();
        tracing.recreateExporterAndProcessor();

        metrics.verifyExport();
        tracing.verifyExport();
    }
}
```

Đây là sơ đồ tổ chức, không phải class có thể compile nguyên trạng vì các lifecycle interface là do ứng dụng cung cấp. Một triển khai thật cần mở lại admission gate và readiness sau khi web server, database và observability thiết yếu đều sẵn sàng. Nếu logging output chưa mở được, nên giữ fallback console/stderr hoặc cơ chế khẩn cấp để ghi lỗi thay vì mất toàn bộ thông tin phục hồi.

Thứ tự flush có thể cần điều chỉnh. Ví dụ, tracing exporter hoặc metrics exporter có thể ghi log; do đó nên drain công việc nghiệp vụ trước, flush tracing/metrics, rồi flush logging cuối cùng để thu cả log của quá trình export. Nếu framework quản lý lifecycle theo resource tree, hãy xác minh thứ tự callback của đúng runtime thay vì dựa vào thứ tự đăng ký ngẫu nhiên.

## 10. Timeout, lỗi flush và checkpoint bị hủy

Flush có thể thất bại vì collector không truy cập được, file system chậm, queue bị kẹt hoặc worker không thể kết thúc. Không nên chờ vô hạn trong `beforeCheckpoint`.

Một chính sách thực tế:

- Đặt timeout riêng cho drain work, trace flush, metrics export và logging drain.
- Ghi nhận số event/span còn pending và lỗi exporter.
- Nếu log audit hoặc trace bắt buộc phải được gửi trước checkpoint theo yêu cầu hệ thống, báo lỗi callback và từ chối checkpoint khi flush thất bại.
- Nếu log chẩn đoán có thể mất theo chính sách, ghi metric/drop counter và tiếp tục trong giới hạn đã định.
- Không nuốt lỗi rồi đánh dấu observability đã sẵn sàng.
- Nếu callback đã đóng exporter/appender rồi checkpoint attempt thất bại, cần khởi tạo lại chúng trên tiến trình tiếp tục chạy hoặc thay instance; không giả định `afterRestore` sẽ được gọi để rollback.

Timeout minh họa:

| Giai đoạn | Ngân sách ví dụ |
|---|---:|
| Drain request và background work | 20 giây |
| Flush trace batch | 5 giây |
| Flush metrics/exporter | 3 giây |
| Drain và flush async log | 5 giây |
| Đóng output cần thiết | 2 giây |
| Dự phòng checkpoint engine | 10 giây |

Các con số cần được đo trên môi trường thực tế. Không dành toàn bộ thời gian checkpoint cho logging/tracing rồi để request hoặc transaction chưa hoàn tất.

## 11. Metrics và tracing khi checkpoint được nhân bản thành nhiều replica

Một checkpoint có thể được dùng làm nguồn restore cho nhiều replica. Điều này đặc biệt quan trọng với observability vì registry, counter và context có thể được sao chép cùng heap.

### Metrics

- Mỗi replica cần có identity phù hợp trong labels/target metadata.
- Không để hai replica xuất cùng một time series với cùng labels nếu chúng là hai process độc lập.
- Counter trong checkpoint không phải tổng toàn cụm; không cộng dồn nó như dữ liệu nghiệp vụ.
- Gauge phải đọc trạng thái của pool/client riêng từng replica.
- Không giữ một cờ exporter leader trong heap làm cơ chế đảm bảo chỉ một replica push metrics.

### Tracing

- Mỗi replica tạo span riêng cho startup/restore và request mới.
- Không dùng một trace ID tĩnh được lưu trong checkpoint cho tất cả replica.
- Không chia sẻ một exporter instance hoặc credential gắn với process cũ nếu nó không hỗ trợ clone/restore.
- Nếu một công việc được resume trên một replica khác, dùng trace link/context bền vững phù hợp thay vì tiếp tục span trong heap của replica trước.

### Logging

- Gắn instance/incarnation metadata để phân biệt nguồn log.
- Tránh để nhiều replica cùng ghi vào một file local hoặc cùng dùng một identity appender nếu backend yêu cầu uniqueness.
- Có thể xuất event `process.restore` hoặc `application.restore` để phân biệt lần chạy mới.

## 12. Tạo restore marker và giữ timestamp chính xác

Một restore marker giúp phân biệt dữ liệu trước và sau checkpoint. Có thể ghi các trường như:

- `service.name`, `service.version` và `deployment.environment`.
- `instance.id` hoặc incarnation ID mới.
- `restore.generation` hoặc checkpoint attempt ID.
- `restore.started_at` và thời gian từ checkpoint nếu có nguồn timestamp đáng tin cậy.
- Kết quả reconnect exporter và trạng thái readiness.

Không sửa timestamp của log/span cũ. Event được tạo trước checkpoint phải giữ thời gian tạo thực tế; marker mới có timestamp sau restore. Nếu cần đo thời gian checkpoint, dùng timestamp bền vững từ controller hoặc metadata bên ngoài, không suy ra từ một clock monotonic đã lưu trong heap.

Không đưa checkpoint ID, instance ID hoặc trace ID có cardinality cao vào mọi metric label. Dùng log/tracing attributes hoặc resource attributes phù hợp; chỉ dùng metric labels khi backend và retention cho phép.

## 13. Quan sát tình trạng observability sau restore

Một ứng dụng có thể phục vụ request nhưng không gửi được telemetry. Hãy coi khả năng quan sát là một dependency vận hành và xác định mức độ bắt buộc:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Logging ready | Appender ghi được vào output dự kiến hoặc fallback | Có thể mở readiness nếu logging không phải dependency bắt buộc nghiêm ngặt |
| Metrics ready | Registry/exporter hoạt động, gauge gắn đúng object | Xác nhận scrape/push và identity |
| Tracing ready | Processor/exporter gửi được span | Kiểm tra batch queue và collector connection |
| Telemetry degraded | Một exporter tạm thời không truy cập được | Retry có giới hạn, ghi metric lỗi, giữ fallback log |
| Telemetry failed | Queue đầy hoặc không có output khả dụng | Tùy yêu cầu vận hành: giữ instance not ready hoặc cho chạy với cảnh báo rõ ràng |

Không phải hệ thống nào cũng cần từ chối toàn bộ traffic nếu tracing collector tạm thời không truy cập được. Hãy phân biệt telemetry là yêu cầu bắt buộc về audit/compliance hay chỉ là kênh chẩn đoán. Log audit có yêu cầu độ bền cao cần một cơ chế khác với debug log có thể drop.

## 14. Kịch bản kiểm thử

Hãy kiểm thử trên đúng JDK/CRaC runtime, logging framework, metrics registry, OpenTelemetry SDK, exporter và collector sẽ dùng trong production:

1. Ghi log bất đồng bộ liên tục, tạo checkpoint và xác nhận queue được drain hoặc checkpoint bị từ chối khi timeout.
2. Tắt log collector trước restore, xác nhận appender reconnect hoặc dùng fallback mà không làm mất toàn bộ log phục hồi.
3. Thay file log/rotation trong thời gian checkpoint, xác nhận file appender mở đúng file sau restore.
4. Kiểm tra counter trước và sau restore, xác nhận backend hiểu reset/instance identity đúng.
5. Kiểm tra gauge active connections sau khi pool được tạo lại, xác nhận gauge không tham chiếu pool cũ.
6. Tạo span và force flush trước checkpoint; xác nhận span đã hoàn tất và export được.
7. Làm OTLP collector không truy cập được, xác nhận flush timeout và chính sách checkpoint được thực thi đúng.
8. Restore sau khoảng downtime dài, xác nhận exporter tạo connection mới và trace context không bị giữ sai.
9. Restore cùng checkpoint thành nhiều replica, xác nhận metric labels và instance identity không xung đột.
10. Thử checkpoint attempt thất bại sau khi appender/exporter đã đóng, xác nhận tiến trình tiếp tục chạy có thể phục hồi telemetry.

## 15. Checklist triển khai

- [ ] Đã liệt kê async logger, appender queue, file/socket output và worker thread.
- [ ] Request và background work được drain trước khi flush telemetry.
- [ ] Async log queue được drain bằng API được hỗ trợ và có timeout.
- [ ] File/network appender được xác minh hoặc tạo lại sau restore.
- [ ] Log audit và log chẩn đoán có chính sách mất dữ liệu khác nhau, nếu cần.
- [ ] Đã xác định semantics counter, gauge, timer và histogram sau restore.
- [ ] Gauge được bind tới pool/client hiện tại, không giữ reference tới object cũ.
- [ ] Pull metrics endpoint hoạt động sau khi server bind lại; push exporter được tạo lại nếu đã shutdown.
- [ ] Counter và metric labels phân biệt đúng process/replica incarnation.
- [ ] Span nghiệp vụ được kết thúc và batch exporter được force flush trước checkpoint.
- [ ] Tracing exporter/processor được tạo lại nếu đã shutdown; không tái sử dụng provider đã đóng.
- [ ] Trace context của công việc resume được tạo hoặc liên kết lại theo semantics rõ ràng.
- [ ] Endpoint, TLS certificate và credential của collector được làm mới sau restore.
- [ ] Flush có timeout, lỗi được ghi nhận và có chính sách khi checkpoint attempt thất bại.
- [ ] Đã kiểm thử restore một replica và nhiều replica với collector bị gián đoạn.

## 16. Kết luận

Logging bất đồng bộ, metrics và tracing đều có trạng thái nền cần được quản lý qua CRaC. Async logger cần drain queue và phục hồi appender; metrics cần xác định semantics counter/gauge và tạo lại exporter nếu cần; tracing cần kết thúc span nghiệp vụ, force flush batch và khởi tạo lại exporter/processor khi provider đã shutdown.

Hãy dừng nguồn phát sinh telemetry mới bằng cách drain công việc ứng dụng, flush từng hệ thống theo API chính thức và đặt timeout rõ ràng trước checkpoint. Sau restore, làm mới endpoint/credential, rebind gauge, tạo lại worker/exporter đã đóng và phát restore marker với incarnation ID phù hợp. Chỉ mở readiness sau khi các kênh observability thiết yếu đã sẵn sàng hoặc đã áp dụng chính sách degraded mode được xác định trước.
