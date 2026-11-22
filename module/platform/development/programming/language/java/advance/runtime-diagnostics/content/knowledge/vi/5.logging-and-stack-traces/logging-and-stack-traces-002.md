# 5.2. Ghi mức log, thread, thời gian và mã tương quan đủ để lần theo một thao tác

Một lỗi kiểu “đơn hàng không hoàn thành” thường đi qua nhiều lớp: HTTP gateway → ứng dụng Java → executor → dịch vụ kho → cơ sở dữ liệu → callback xử lý kết quả. Nếu nhật ký chỉ có những dòng như “start”, “processing”, “failed”, việc tìm **dòng nào thuộc cùng một thao tác** rất khó. Cần thiết kế mỗi bản ghi có bối cảnh đủ để trả lời: **chuyện gì xảy ra, khi nào, mức độ nào, trên thread nào và thuộc request/trace nào**.

Bài này thuộc nhóm **5. Nhật ký và stack trace**. Trọng tâm là lựa chọn **log level**, **timestamp**, **thread identity** và **correlation ID**; thực hành ghi một chuỗi sự kiện có thể ghép lại, kể cả khi công việc chuyển thread hoặc đi qua nhiều service. Java 17+ được dùng để minh họa cách tạo log có cấu trúc; SLF4J/MDC và trace context được giải thích riêng vì các thư viện này không thuộc JDK chuẩn.

## 1. Mô hình một sự kiện log có thể tìm và liên kết

Một bản ghi hữu ích không phải chỉ là câu văn. Nên có **trường ổn định** và giá trị có ý nghĩa:

| Trường | Mục đích | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| `timestamp` | Biết sự kiện xảy ra khi nào, sắp xếp gần đúng theo thời gian | `2026-10-29T08:15:30.123Z` | Ưu tiên UTC ISO-8601, ghi rõ timezone |
| `level` | Độ nghiêm trọng/ý nghĩa vận hành | `INFO`, `WARN`, `ERROR` | Mức phải phản ánh sự kiện, không theo cảm xúc người viết |
| `service` / `instance` / `version` | Biết dòng thuộc ứng dụng, pod và bản build nào | `order-api`, `pod-a`, `1.8.2` | Đặc biệt quan trọng trong hệ thống nhiều replica |
| `thread` | Thread JVM phát sinh bản ghi | `http-nio-8080-exec-7` | Thread tái sử dụng; **không phải request ID** |
| `correlationId` / `requestId` | Liên kết mọi sự kiện thuộc một thao tác/request nghiệp vụ | `req-7c41` | Cần được tạo/nhận ở ingress và truyền qua boundary |
| `traceId` / `spanId` | Liên kết logs với distributed trace và đoạn công việc | Mã theo trace context | Chỉ ghi khi có tracing/context hợp lệ |
| `event` / `operation` | Loại sự kiện ổn định để tìm kiếm, phân nhóm | `order.reserve.started` | Tên ổn định tốt hơn văn bản thay đổi tùy ý |
| `message` | Diễn giải ngắn gọn điều đã xảy ra | `inventory reservation failed` | Không chép nguyên dữ liệu nhạy cảm |
| `outcome` / `errorCode` / `durationMs` | Kết quả và tác động | `FAILED`, `INV_TIMEOUT`, `832` | Dùng đơn vị rõ ràng, log tại ranh giới công việc |
| `exception` / `stackTrace` | Bằng chứng đường gọi khi có lỗi | Loại exception và stack | Ghi đối tượng Throwable ở logging framework, tránh chỉ lưu message |

**Tập tối thiểu** cho log ứng dụng phục vụ chẩn đoán: `timestamp + level + service + event + thread + correlationId + message`. Thêm `traceId/spanId` khi đã có distributed tracing; thêm `durationMs` và `outcome` cho sự kiện kết thúc; thêm exception đúng cách cho lỗi. Các trường như `instance` và `version` có thể được gắn bởi collector/resource metadata thay vì lặp lại trong từng lời gọi log.

Ví dụ **JSON Lines minh họa** (mỗi dòng là một JSON object, không phải stdout cố định của chương trình bên dưới):

~~~json
{"timestamp":"2026-10-29T08:15:30.120Z","level":"INFO","service":"order-api","thread":"http-worker-4","correlationId":"req-7c41","event":"order.accepted","orderRef":"ORD-42"}
{"timestamp":"2026-10-29T08:15:30.122Z","level":"INFO","service":"order-api","thread":"pool-2-thread-1","correlationId":"req-7c41","event":"inventory.reserve.started"}
{"timestamp":"2026-10-29T08:15:30.954Z","level":"WARN","service":"order-api","thread":"pool-2-thread-1","correlationId":"req-7c41","event":"inventory.reserve.timeout","durationMs":832,"errorCode":"INV_TIMEOUT"}
{"timestamp":"2026-10-29T08:15:30.958Z","level":"ERROR","service":"order-api","thread":"http-worker-4","correlationId":"req-7c41","event":"order.failed","outcome":"FAILED","durationMs":838,"errorCode":"INV_TIMEOUT"}
~~~

Bốn dòng cho thấy **cùng correlation ID** nhưng có **hai thread**. Nếu chỉ lọc theo tên thread, ta có thể bỏ sót một nửa thao tác hoặc trộn thêm request khác xử lý trên thread đó. Các timestamp cũng cho biết khoảng thời gian, nhưng quan hệ nhân quả chính xác nên được xác định thêm bằng event, parent-child span/trace hoặc business workflow, không suy từ thứ tự timestamp một mình.

## 2. Log level: ghi đủ tín hiệu và tránh nhiễu

Các framework dùng các tên level khác nhau. SLF4J/Logback/Log4j thường có `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`; Java Util Logging (JUL) dùng `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`. Đây là **hai thang đặt tên khác nhau**, không giả định có mapping một-một tuyệt đối cho mọi cấu hình bridge.

| Mức thường dùng ở SLF4J | Nên ghi gì | Ví dụ sự kiện |
| --- | --- | --- |
| **ERROR** | Thao tác đã thất bại hoặc hệ thống không thể hoàn thành trách nhiệm của nó, cần điều tra/xử lý | Không thể ghi đơn hàng sau khi hết retry có giới hạn |
| **WARN** | Tình trạng bất thường, vẫn có thể hồi phục/fallback, nguy cơ suy giảm nhưng chưa phải lỗi kết thúc | Dependency timeout ở lần thử đầu, fallback đang được dùng |
| **INFO** | Cột mốc nghiệp vụ/vòng đời quan trọng, ít biến động, hữu ích ở production | Nhận request, hoàn tất giao dịch, thay đổi trạng thái quan trọng |
| **DEBUG** | Chi tiết để tìm nguyên nhân trong một flow; có thể bật có chọn lọc | Chọn nhánh xử lý, cache miss, quyết định retry |
| **TRACE** | Thao tác rất chi tiết, có tần suất cao, chỉ bật khi thật sự cần | Các bước nội bộ nhỏ, từng nhánh xử lý |

**Nguyên tắc thực tế:**
- **Không log ERROR cho lỗi dự kiến** đã được xử lý đúng hợp đồng, chẳng hạn request không hợp lệ dẫn tới 400 như thiết kế. Có thể thống kê/lưu INFO/WARN tùy yêu cầu.
- **WARN** cho tình huống bất thường có thể hồi phục; nếu mỗi request bình thường đều phát WARN, cảnh báo sẽ trở nên vô nghĩa.
- **INFO** là dấu mốc tạo khả năng theo dõi ở mức vận hành, không phải in mọi vòng lặp.
- **DEBUG/TRACE** phải được kiểm soát về lưu lượng và thông tin nhạy cảm. Đặc biệt tránh log toàn bộ request/response body, token, cookie, credential hoặc thông tin cá nhân.
- **Một lỗi nên có một điểm ghi nhận chính** tại tầng sở hữu kết quả. Ném exception qua nhiều lớp mà lớp nào cũng log ERROR với stack trace sẽ tạo bản sao và nhiễu cảnh báo.

**Lọc theo level:** logger, handler/appender, filter và collector có thể có ngưỡng khác nhau. Việc gọi `logger.debug(...)` không đảm bảo có log được ghi ra khi DEBUG chưa bật. Khi thiếu dòng, kiểm tra cả ngưỡng tại logger lẫn output/collector, cấu hình sampling và việc drop khi pipeline quá tải.

**Lưu ý về stack trace:** nếu xảy ra lỗi thật, truyền **Throwable object** cho logging API để backend hiển thị exception class, message và stack/cause chain; chỉ gọi `exception.getMessage()` sẽ mất đường gọi. Cần liên kết stack trace với `correlationId`/`traceId` và event lỗi, đồng thời giới hạn dữ liệu nhạy cảm trong message.

## 3. Thời gian: timestamp sự kiện khác thời lượng

**Timestamp** dùng để đối chiếu log giữa máy, truy vấn theo cửa sổ thời gian và xây dựng timeline. Ưu tiên:
- Dạng ISO-8601 UTC, ví dụ `2026-10-29T08:15:30.123Z`; giữ timezone/offset rõ ràng.
- Mức chính xác phù hợp hệ thống, thường milliseconds hoặc microseconds nếu công cụ hỗ trợ; đừng nhầm có nhiều chữ số với độ chính xác thật.
- Khi có collector, phân biệt **event timestamp** (lúc app phát sinh) và **ingestion timestamp** (lúc pipeline nhận) vì batching/network làm hai thời điểm khác nhau.
- Đồng bộ đồng hồ host/container bằng cơ chế hạ tầng. Clock skew giữa các máy có thể làm event ở downstream trông như xảy ra trước upstream.

**Duration** là độ dài khoảng đo. Với Java trong cùng JVM, đo duration bằng hiệu `System.nanoTime()` (đồng hồ đo khoảng thời gian) rồi chuyển đơn vị; không dùng hiệu `System.currentTimeMillis()` để benchmark ngắn vì wall clock có thể được điều chỉnh.

~~~java
long startNanos = System.nanoTime();
// Thao tác thực tế được bao trong khoảng đo.
long durationMs = java.util.concurrent.TimeUnit.NANOSECONDS
        .toMillis(System.nanoTime() - startNanos);
~~~

Đây là **đoạn mã minh họa cách đo**, không phải chương trình chạy độc lập. Đưa `durationMs` vào log kết thúc và phải nói rõ là **thời gian của đoạn nào**: end-to-end request, một lời gọi DB hay chờ lấy connection. Đừng cộng durations của các nhánh chạy song song như thể chúng tuần tự; dùng trace/span critical path khi cần.

Ví dụ:
- Request A vào lúc `08:00:00.000Z`, hoàn tất lúc `08:00:00.500Z`: elapsed khoảng 500 ms nếu đồng hồ tin cậy.
- Span gọi DB tốn 300 ms, span gọi cache 250 ms **có thể chạy song song**: không thể kết luận tổng request bằng 550 ms chỉ bằng phép cộng.
- Timestamp theo UTC giúp nối log đa vùng thời gian; duration trong một process vẫn nên lấy monotonic measurement.

## 4. Thread name là bối cảnh thực thi, không là mã tương quan

`Thread.currentThread().getName()` (Java 17+) cho biết tên thread hiện tại. Tên giúp kiểm tra:
- Tác vụ chạy trên HTTP worker, executor pool, scheduled task hay thread đặc biệt.
- Một thread có bị kẹt trong stack trace, lock contention hoặc queue không.
- Một thao tác có chuyển giữa các executor khác nhau không, qua nhiều event.

Nhưng **thread có thể phục vụ nhiều request liên tiếp** và một request có thể **chạy trên nhiều thread**. Với bất đồng bộ, callback, `CompletableFuture` hoặc reactive pipeline, thread ở sự kiện bắt đầu có thể khác thread ở sự kiện kết thúc. Vì vậy:
- Không tạo correlation ID bằng thread name/thread ID.
- Không lọc toàn bộ vấn đề theo thread name rồi tự cho rằng tất cả log thuộc một request.
- Nếu muốn liên hệ thread dump, lưu tên thread/identifier với timestamp và process identity, sau đó đối chiếu với event log.

Có thể tùy chỉnh tên thread theo cách có nghĩa cho vận hành, ví dụ `inventory-worker-2`, nhưng không nên nhúng mã request trực tiếp vào tên thread pool tái sử dụng: dễ bỏ sót cleanup và làm sai quan sát.

## 5. Correlation ID, request ID, trace ID và span ID

Các định danh này liên quan nhưng **không đồng nghĩa**:

| Định danh | Phạm vi | Tác dụng |
| --- | --- | --- |
| **correlationId** | Một thao tác/workflow được quy ước theo hệ thống | Tìm mọi log liên quan, có thể nối nhiều request/message |
| **requestId** | Một lần yêu cầu vào service/gateway | Phân biệt từng request, kể cả retry |
| **traceId** | Một distributed trace trải qua nhiều service và span | Liên kết logs với distributed tracing |
| **spanId** | Một công việc/đoạn trong trace | Gắn log vào đoạn xử lý cụ thể |
| **business reference** | Đơn hàng, giao dịch, message nghiệp vụ | Tra cứu theo đối tượng; không nhất thiết duy nhất cho mỗi lần thực thi |

Tùy kiến trúc, có thể dùng một `correlationId` bằng request ID ở ingress; nếu workflow có nhiều lần retry/request nối tiếp, cần thiết kế cách phân biệt từng attempt với correlation ID chung. Không thay thế correlation ID bằng userId, email hay số điện thoại: vừa có rủi ro bảo mật, vừa không duy nhất cho một thao tác.

**Trace context:** tiêu chuẩn W3C Trace Context định nghĩa header `traceparent` để mang trace ID/span parent ID và trace flags qua network; OpenTelemetry có thể gắn `TraceId` và `SpanId` trong log records. **TraceId** thường được biểu diễn 32 ký tự hex, **SpanId** 16 ký tự hex trong W3C format. Không tự điền một chuỗi ngẫu nhiên vào `traceId` nếu hệ thống thực tế chưa có span/context hợp lệ.

Ở biên hệ thống:
1. Nếu đã có correlation ID hợp lệ từ gateway/parent, tiếp tục sử dụng theo chính sách hệ thống; **validate độ dài và ký tự**, tránh log injection và chiếm tài nguyên.
2. Nếu không có ID hoặc giá trị không đáng tin, tạo ID mới bằng cơ chế phù hợp, chẳng hạn UUID cho correlation ID nội bộ.
3. Đưa ID vào context của request/job, thêm vào outgoing HTTP headers hoặc message metadata khi các thành phần cần tương quan.
4. Ở downstream, đọc/validate và nối theo chính sách trust boundary; gắn ID vào log cho các event liên quan.
5. Khi retry, có thể giữ correlation ID **chung**, đồng thời thêm `attempt` hoặc `requestId` riêng để phân biệt từng lần thử.

Không chấp nhận tùy tiện header client giả mạo làm dữ liệu xác thực/ủy quyền. ID chỉ phục vụ **quan sát và liên kết**, không được dùng làm bằng chứng danh tính hoặc quyền truy cập.

## 6. Chọn những điểm ghi log để lần theo một thao tác

Một flow điển hình:
1. **Ingress/accepted:** request/job được nhận; log INFO với ID, loại tác vụ, endpoint hoặc event nghiệp vụ, source.
2. **Dispatch/start:** ghi nhận bắt đầu xử lý, có thể gồm queue wait nếu đo được.
3. **Boundary quan trọng:** trước/sau gọi dependency, lấy connection, bắt đầu retry, fallback, publish message; nếu ghi thường xuyên, cân nhắc DEBUG với số liệu metric/tracing tương ứng.
4. **Failure:** WARN cho lỗi có thể hồi phục; ERROR cho kết quả thất bại. Ghi `errorCode` ổn định, Throwable hợp lệ và thông tin dependency liên quan.
5. **Completion:** INFO cho kết quả chính, `outcome`, `durationMs` của toàn flow, correlation ID; không log thừa mỗi bước nhỏ.

**Nguyên tắc cân bằng:** không phải ứng dụng nào cũng cần log INFO ở mọi request nếu traffic rất lớn. Có thể dùng access logs có cấu trúc, tracing và metrics để giữ tín hiệu cần thiết mà tránh log quá nhiều; chỉ tăng DEBUG/TRACE có mục tiêu khi điều tra.

### Quy ước tên event và trạng thái

Nên chọn những tên event ổn định, có nghĩa, ví dụ:
- `order.received`
- `order.inventory.reserve.start`
- `order.inventory.reserve.retry`
- `order.inventory.reserve.failure`
- `order.completed`

Tránh chỉ dùng một câu `message` tự do như “doing something” hoặc “failed again”. Nếu đổi câu chữ hoặc ngôn ngữ, trường `event` ổn định vẫn hỗ trợ query và dashboard. Phân biệt `outcome=SUCCESS/FAILED/CANCELLED` và `errorCode=...` là dữ liệu có cấu trúc, không phải văn bản phải regex để trích xuất.

## 7. Ví dụ Java 17 chạy độc lập, không cần thư viện ngoài

Java chuẩn có `java.util.logging` (JUL): `Logger`, `Level`, `LogRecord`, `Handler` và `Formatter`. Đoạn sau tạo **logger**, lưu metadata ở `LogRecord.parameters`, dùng `StreamHandler` để ghi ra stdout và một `Formatter` tường minh để trình bày bốn thông tin bắt buộc: **timestamp, level, thread, correlation ID**, cùng loại sự kiện và message.

Để stdout có thể tái hiện chính xác trong bài học, ví dụ dùng **`Clock.fixed`** với thời điểm cố định; production phải dùng đồng hồ thực như `Clock.systemUTC()` hoặc nguồn timestamp do logging framework quản lý. Đây là **minh họa giáo dục**; trong production nên dùng structured JSON encoder của framework để escape nội dung và gắn metadata chuẩn.

Tạo tệp **CorrelatedLoggingDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class CorrelatedLoggingDemo {
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-10-29T08:00:00Z"),
            ZoneOffset.UTC
    );
    private static final Logger LOG = Logger.getLogger("order.demo");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                Object[] p = record.getParameters();
                return "%s level=%s thread=%s correlationId=%s event=%s message=\"%s\"%n"
                        .formatted(
                                p[0],
                                record.getLevel().getName(),
                                p[1],
                                p[2],
                                p[3],
                                record.getMessage()
                        );
            }
        };

        StreamHandler handler = new StreamHandler(System.out, formatter);
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        String correlationId = "req-42";
        emit(Level.INFO, correlationId, "order.received", "begin");
        emit(Level.WARNING, correlationId, "inventory.retry", "retry scheduled");
        emit(Level.INFO, correlationId, "order.completed", "success");

        handler.flush();
    }

    private static void emit(
            Level level, String correlationId, String event, String message) {
        LogRecord record = new LogRecord(level, message);
        record.setParameters(new Object[] {
                Instant.now(CLOCK),
                Thread.currentThread().getName(),
                correlationId,
                event
        });
        LOG.log(record);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng **JDK 17+**:

~~~bash
javac CorrelatedLoggingDemo.java
java CorrelatedLoggingDemo
~~~

**Stdout chính xác** (ba log có cùng correlation ID, thread là `main`, clock được cố định trong ví dụ):

~~~text
2026-10-29T08:00:00Z level=INFO thread=main correlationId=req-42 event=order.received message="begin"
2026-10-29T08:00:00Z level=WARNING thread=main correlationId=req-42 event=inventory.retry message="retry scheduled"
2026-10-29T08:00:00Z level=INFO thread=main correlationId=req-42 event=order.completed message="success"
~~~

**Đọc kết quả:**
- Dù thông điệp khác nhau, cả ba sự kiện cùng `correlationId=req-42`, nên có thể nhóm thành một flow.
- `level=WARNING` là cách đặt tên **của JUL**; nhiều framework khác dùng `WARN`.
- `thread=main` đúng vì ví dụ chạy đồng bộ trong main thread; các ví dụ async có thể đổi thread nhưng vẫn phải giữ correlation ID.
- Timestamp giống nhau do `Clock.fixed` **chỉ phục vụ kiểm tra có thể tái lập**, không đại diện thời gian thực của production.
- `LogRecord.parameters` được dùng để mang metadata trong bài học; trong sản xuất, backend JSON encoder hoặc typed key-value API phù hợp sẽ an toàn hơn cách ghép chuỗi thủ công.

**Điều chưa được ví dụ này làm:** truyền context qua thread/service, lưu exception stack trace, khử dữ liệu nhạy cảm, logging bất đồng bộ, sampling, hoặc tự động ghi trace ID. Các tác vụ đó cần logging framework, tracing instrumentation và chính sách hệ thống tương ứng, sẽ được áp dụng ở các mục tiếp.

## 8. MDC với SLF4J/Logback: gắn ID vào mọi log của một luồng

Trong ứng dụng Java thường dùng `org.slf4j.MDC` (Mapped Diagnostic Context) để đặt metadata theo context thực thi. Framework/encoder phù hợp có thể đọc MDC và thêm vào log mà không cần truyền `correlationId` vào từng lời gọi.

Đoạn mã **minh họa cách dùng SLF4J**, **không chạy độc lập** vì cần dependency SLF4J, backend hỗ trợ như Logback và biến `log`/`correlationId` trong ứng dụng:

~~~java
import org.slf4j.MDC;

// Đầu vào giả định đã được xác minh và chuẩn hóa.
String previous = MDC.get("correlationId");
MDC.put("correlationId", correlationId);
try {
    log.info("order.received");
    performOrderWork();
    log.info("order.completed");
} catch (RuntimeException ex) {
    log.error("order.failed errorCode=ORDER_FAILURE", ex);
    throw ex;
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
~~~

**Vì sao phải dùng `finally`?** Thread pool tái sử dụng thread cho request sau. Nếu không xóa hoặc khôi phục MDC, request tiếp theo có thể bị gắn nhầm ID của request trước, làm timeline sai và rò bối cảnh giữa các người dùng. Đoạn trên giữ lại giá trị MDC cũ trong trường hợp nested call; với một request boundary hoàn toàn độc lập, nhiều hệ thống chọn clear toàn bộ context ở đầu/cuối theo quy ước thống nhất.

**Lưu ý thiết yếu:** chỉ gọi `MDC.put(...)` chưa đảm bảo ID xuất hiện trong output. Pattern/JSON encoder của backend phải được cấu hình thêm trường MDC, ví dụ khái niệm `correlationId` trong Logback pattern là `%X{correlationId}`. Nếu encoder/collector bỏ trường hoặc đặt tên khác, log vẫn thiếu ID dù MDC đã được gán.

### Khi công việc chuyển sang thread khác

MDC thường gắn với thread context, không mặc định tự theo qua `ExecutorService`, `CompletableFuture` hoặc mọi reactive pipeline. Cần capture và khôi phục context một cách có chủ đích hoặc dùng integration của framework/observability agent.

Đoạn sau **minh họa tại một call site**, giả định đã có `ExecutorService executor`, `org.slf4j.MDC` và logger `log`:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        log.info("inventory.reserve.started");
        // Xử lý công việc của thao tác hiện tại.
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Ở đây **snapshot của parent** được chuyển vào worker, rồi **context cũ của worker** được khôi phục khi thoát. Có thể có context khác ngoài MDC (ví dụ OpenTelemetry Context, security context) cần cơ chế propagation riêng; chỉ sao chép MDC **không đủ** để duy trì active trace span. Nếu framework đã cung cấp task decorator/instrumentation, nên dùng cơ chế được hỗ trợ của framework để tránh quên ở một nhánh async.

Với reactive pipelines hoặc virtual threads (JDK 21+), đừng mặc định `ThreadLocal`/MDC truyền đúng qua các lần đổi executor. Truyền ngữ cảnh theo mô hình context của framework, dùng integration có kiểm chứng và kiểm tra log ở từng async boundary.

## 9. Distributed tracing: liên kết log qua nhiều service

Một correlation ID riêng của ứng dụng có thể đủ để tìm tất cả bản ghi theo một workflow. Khi có tracing, nên liên kết thêm:
- **`traceId`** giữ nguyên trong toàn distributed trace.
- **`spanId`** thay đổi theo từng đoạn công việc/operation.
- **`service.name`** xác định service sở hữu log.
- **`correlationId`** có thể tồn tại song song, đặc biệt khi nghiệp vụ kéo dài qua nhiều message hoặc trace riêng biệt.

OpenTelemetry định nghĩa **log correlation** qua thời gian, execution context và resource attributes; log records có thể mang `TraceId`/`SpanId` để nhảy từ log sang trace tương ứng. Điều kiện là **trace context được truyền đúng** qua function/thread và HTTP/message boundaries, và logging backend/exporter thực sự gắn các trường đó.

### Minh họa một thao tác đi qua hai service

~~~text
Request POST /orders
  |
  | correlationId=req-42
  | traceId=4f... (cùng trace)
  v
order-api
  |  event=order.received
  |  spanId=aa... (span order)
  |
  +---- gọi inventory-api (HTTP context propagation) ---->
            event=inventory.reserve.started
            traceId=4f... (cùng trace)
            spanId=bb... (span inventory)
            |
            +---- event=inventory.reserve.completed
  |
  v
order-api
  event=order.completed
~~~

Các ID bị rút gọn trong sơ đồ **chỉ minh họa**, không phải định dạng W3C hợp lệ để truyền trên mạng. Cần lấy ID thật từ active tracing context, không tự dựng lại span ID bằng thread name. Nếu mất `traceparent` hoặc context ở async boundary, logs downstream có thể không chứa trace ID hoặc thuộc trace khác; correlation ID riêng có thể giúp điều tra nhưng không thay cho propagation chính xác.

**Không dùng correlation ID làm nhãn metric có cardinality cao** cho từng request; log field có thể phục vụ truy vấn chi tiết, còn metrics thường dùng nhãn có tập giá trị nhỏ như route, outcome, status class.

## 10. Giữ log có cấu trúc, an toàn và chi phí hợp lý

**Cấu trúc:** mỗi sự kiện một object JSON hợp lệ (JSON Lines) là lựa chọn thông dụng khi có hệ thống tìm kiếm log. Khai báo tên trường, kiểu dữ liệu và đơn vị nhất quán: `durationMs` là số, `level` là enum/chuỗi, `timestamp` là ISO timestamp, `event` là tên ổn định. Không để người viết tự ghép JSON không escape từ user input.

**Mã tương quan:** tạo ID không trùng theo phạm vi hệ thống; nếu nhận qua header cần giới hạn ký tự/độ dài và chống newline/control character. Chỉ đưa ID sang downstream theo hợp đồng. Không biến ID thành quyền truy cập hoặc identifier chứa thông tin cá nhân.

**Bảo mật và dữ liệu nhạy cảm:** không log access token, password, session cookie, private key, full payment card, raw authentication headers hoặc request body nhạy cảm. Chỉ log các business fields tối thiểu đã cho phép, có masking/redaction và giới hạn quyền xem. Stack trace có thể chứa path, user input, query text hoặc context nhạy cảm; đánh giá trước khi export/chia sẻ.

**Log injection:** dữ liệu do client gửi có thể chứa newline hoặc ký tự điều khiển làm giả dòng log khi output text thuần. Dùng structured logger/encoder escape đúng chuẩn; tránh đưa nguyên chuỗi user input vào `message`.

**Tần suất và hiệu năng:** log DEBUG/TRACE trong vòng lặp hot path gây CPU, allocation và I/O; log pipeline async có thể drop khi queue đầy. Nên dựa vào metrics để theo dõi tỷ lệ, logs để giải thích sự kiện, trace để nối critical path. Khi điều tra, tăng mức log có chọn lọc và hạ lại sau khi thu đủ bằng chứng.

**Không ghi trùng exception:** nếu tầng thấp chỉ ném exception và tầng trên chịu trách nhiệm quyết định outcome, hãy cân nhắc log ERROR ở tầng quyết định, đồng thời giữ cause chain. Nếu tầng thấp cần ghi WARN để mô tả retry, event và errorCode riêng sẽ giúp tránh hiểu hai log là hai sự cố độc lập.

## 11. Quy trình lần theo một thao tác từ log

Giả sử người dùng nói “Đơn hàng ORD-42 báo lỗi lúc 15:15”. Quy trình chẩn đoán:

1. **Chốt phạm vi:** timezone, khoảng thời gian, môi trường, service, version, endpoint, business reference hoặc correlation ID từ response/gateway. Đừng lấy thời gian mơ hồ “khoảng chiều” làm mốc duy nhất.
2. **Tìm request/correlation ID:** query log ingress theo business reference đã cho phép; nếu có ID từ response header, tra trực tiếp. Không tìm theo thread name trước.
3. **Nhóm theo ID:** gom log across services, instance và worker thread, sắp xếp theo event timestamp. Dùng trace/span parent-child để xác định thứ tự nhân quả khi clocks lệch hoặc events chạy song song.
4. **Tìm mốc start, boundary, error và end:** event nào thiếu? Request đã xếp hàng, gửi tới dependency, có retry/fallback, hay bị timeout ở đâu?
5. **So duration và outcome:** duration tổng của request, queue wait, dependency call, timeout, attempt count. Không cộng các span chồng lấn để suy tổng latency.
6. **Đọc stack trace đúng event:** kiểm tra exception type/cause chain, nơi ném và sự kiện đầu tiên có ý nghĩa; không mặc định dòng ERROR cuối cùng là nguyên nhân gốc.
7. **Đối chiếu nguồn khác:** metrics, distributed trace, thread dump, GC log, dependency/server logs và deployment timeline khi cần.
8. **Kết luận có căn cứ:** viết “request req-42 timeout khi gọi inventory sau 832 ms, order-api trả lỗi ở 838 ms” nếu log/trace chứng minh; tránh “DB bị lỗi” khi chưa có bằng chứng.

**Ví dụ phân biệt:**
- Log `order.received` ở thread `http-4`, `inventory.reserve.started` ở `pool-2-thread-1` và `order.failed` ở `http-4` vẫn cùng một workflow nếu ID trùng và được propagate đúng.
- Hai request khác nhau chạy liên tiếp trên `http-4` không phải cùng thao tác dù thread name bằng nhau.
- Một `ERROR` ở tầng dưới có thể được retry thành công ở tầng trên; outcome cuối cần xác nhận từ completion log, không dừng ở lỗi đầu.

## 12. Các lỗi phổ biến và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách cải thiện |
| --- | --- | --- |
| Log chỉ có message, không có ID | Không có contract trường log hoặc formatter thiếu | Gắn ID tại ingress; thêm vào encoder và log boundary |
| ID biến mất khi qua executor | MDC/trace context không được propagate | Dùng task decorator/context wrapper/instrumentation; kiểm thử async boundary |
| Request mới mang ID request cũ | Quên cleanup ThreadLocal/MDC trong thread pool | `try/finally` khôi phục hoặc clear theo contract |
| Cùng ID mà timestamp “đi ngược” | Clock skew, async batching, ingestion delay | Dùng UTC/event timestamp, span relationships và monotonic durations |
| Có quá nhiều ERROR cho một exception | Mỗi tầng catch lại log rồi rethrow | Chỉ log outcome tại tầng chịu trách nhiệm; phân biệt WARN retry |
| Thiếu log DEBUG | Ngưỡng logger/appender, filter/sampling hoặc pipeline drop | Kiểm tra effective level và toàn đường xuất log |
| Không có stack trace trong log ERROR | Chỉ log `e.getMessage()` thay cho Throwable | Truyền Throwable object cho framework |
| Chỉ lọc thread, bỏ sót nửa flow | Request async chuyển thread | Nhóm theo correlation/trace ID, thread chỉ là phụ trợ |
| JSON parse fail hoặc log bị tách dòng | Gắn user input bằng string concatenation | Dùng encoder escape đúng và hạn chế raw input |
| Truy vấn log quá tốn kém | Volume lớn, giữ quá lâu, field không nhất quán | Giảm log tần suất cao, chuẩn hóa schema, retention/sampling có mục đích |
| Log chứa password/token | Ghi nguyên request/headers hoặc exception context | Redaction, allowlist fields, kiểm tra quyền/retention |
| Không khớp giữa log và trace | trace context không được truyền hoặc không inject vào logger | Kiểm tra `traceparent` và integration, thêm traceId/spanId hợp lệ |

## 13. Checklist kiểm thử khả năng tương quan

Trước khi coi logging của một service là đủ dùng cho chẩn đoán, thử một request có mã tương quan đã biết và xác minh:

1. **Level:** INFO cho các mốc chính; WARN/ERROR đúng mức; DEBUG chỉ xuất hiện khi được bật.
2. **Timestamp:** UTC có offset, đủ độ phân giải; bản ghi có event time và duration đo đúng đơn vị.
3. **Thread:** log thể hiện thread phát sinh; flow đổi executor vẫn giữ cùng correlation ID.
4. **Correlation ID:** tạo tại ingress khi thiếu; validate khi nhận; mọi boundary liên quan đều gắn đúng; request khác không bị dính ID cũ.
5. **Trace:** nếu có instrumentation, `traceId` nối qua services và `spanId` phản ánh span thực tế.
6. **Lifecycle:** tìm được event accepted/started, dependency/retry, failure hoặc completed và thời gian xử lý.
7. **Exception:** lỗi kết thúc có `errorCode` ổn định và Throwable stack/cause chain khi cần.
8. **Structured output:** parser/collector đọc được fields; dữ liệu người dùng được escape, secrets đã được loại bỏ.
9. **Tải:** kiểm tra tỷ lệ drop khi log volume cao; không biến DEBUG thành bottleneck.
10. **Truy vấn thực tế:** từ một correlation ID có thể tìm đủ event qua nhiều thread và nhiều service, rồi viết kết luận có timestamp và bằng chứng.

**Ghi nhớ:** **timestamp** trả lời *khi nào*; **level** trả lời *cần chú ý đến mức nào*; **thread** trả lời *ở đâu trong JVM thực thi*; **correlationId/traceId** trả lời *thuộc thao tác nào*. Để lần theo một thao tác đầy đủ, hãy gắn cùng ID vào các mốc quan trọng từ ingress đến completion, truyền context qua mọi boundary và luôn ghi outcome, duration và exception đúng cách. Không một trường đơn lẻ nào thay thế được toàn bộ bối cảnh.

### Tài liệu tham khảo

- Java SE 17, `java.util.logging` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html
- Java SE 17, `StreamHandler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J, Mapped Diagnostic Context: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- OpenTelemetry Logs Specification, Log Correlation: https://opentelemetry.io/docs/specs/otel/logs/
- W3C Trace Context: https://www.w3.org/TR/trace-context/

Các ví dụ định dạng, event và ID trong bài mang tính minh họa; khi triển khai cần dùng logging backend, tracing integration và chính sách bảo vệ dữ liệu phù hợp với hệ thống thực.