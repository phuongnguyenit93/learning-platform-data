# Điểm mở rộng kiến trúc logging trong Java

## 1. Mục tiêu và phạm vi

Khi ứng dụng Java lớn dần, logging không chỉ là gọi một phương thức để in thông điệp. Hệ thống cần thay đổi **cách tạo sự kiện**, **lọc**, **bổ sung ngữ cảnh**, **định dạng**, **chuyển đến đích**, hoặc **xuất sang hệ thống quan sát** mà không viết lại nghiệp vụ. Những vị trí cho phép thay đổi hành vi có kiểm soát đó là **điểm mở rộng (extension points)** của kiến trúc logging.

Sau bài này, bạn có thể:

- Giải thích ranh giới giữa logging API/facade, provider/backend, logger, filter, handler/appender, formatter/encoder và pipeline thu thập.
- Chọn điểm mở rộng nhỏ nhất phù hợp cho yêu cầu mới, ví dụ định dạng JSON, ẩn dữ liệu nhạy cảm, đổi nơi gửi log hoặc bổ sung correlation ID.
- Tự xây dựng và chạy một extension cho **java.util.logging (JUL)** bằng Java 17+.
- Hiểu cách những ý tưởng tương tự xuất hiện trong **SLF4J**, **Logback**, **Log4j 2** và cơ chế **System.Logger** của JDK.
- Tránh các vấn đề về vòng lặp bridge, mất ngữ cảnh giữa các thread, lỗi trong sink, làm chậm request, trùng bản ghi và rò rỉ dữ liệu.

**Ngữ cảnh:** Đây là bài thuộc phần *Kiến trúc logging* của *Java Core Logging*. Trọng tâm là ranh giới và khả năng mở rộng của logging trong ứng dụng Java, không phải hướng dẫn dựng một hệ thống giám sát tập trung hoàn chỉnh.

## 2. Bản đồ kiến trúc: mở rộng ở đâu?

Một kiến trúc phổ biến có thể nhìn theo đường đi của một sự kiện:

~~~text
Business code
  |
  v
Logging API / facade             [1] Thay API ở ranh giới ứng dụng
  |
  v
Provider / logging backend       [2] Chọn implementation xử lý log
  |
  v
Logger + effective level         [3] Quy tắc chấp nhận log
  |
  +--> Context / attributes      [4] requestId, traceId, service...
  |
  v
Filter(s)                        [5] Chọn, loại, điều hướng sự kiện
  |
  v
Handler / Appender / Sink        [6] Gửi đến console, file, queue...
  |
  v
Formatter / Layout / Encoder     [7] Text, JSON, cấu trúc khác
  |
  v
Collector / Transport / Backend  [8] Thu thập, xử lý, lưu trữ, truy vấn
~~~

Sơ đồ biểu diễn **các vai trò**, không bắt buộc thứ tự thực thi của mọi framework. Ví dụ, formatter có thể được gọi bên trong handler; một số framework chạy filter ở nhiều giai đoạn, có xử lý bất đồng bộ hoặc routing appender. Bất kỳ quyết định tích hợp nào đều cần đối chiếu API và vòng đời thực tế của backend đang sử dụng.

**Nguyên tắc thiết kế:** mã nghiệp vụ chỉ nên cung cấp *sự kiện có ý nghĩa* và *ngữ cảnh được phép*. Việc chọn đích ghi, định dạng và chính sách lưu trữ nên đặt tại lớp logging hoặc hạ tầng. Thay đổi định dạng log không nên làm thay đổi thuật toán tạo đơn hàng.

## 3. Những điểm mở rộng chính và khi nào dùng

| Điểm mở rộng | Trách nhiệm | Ví dụ yêu cầu | Không nên dùng để |
| --- | --- | --- | --- |
| API / facade | Bề mặt gọi log ổn định cho mã ứng dụng | Các module dùng chung một API, đổi backend sau này | Chứa trực tiếp logic gửi HTTP hoặc kết nối kho log |
| Provider / backend | Hiện thực API, quản lý logger, cấu hình và pipeline | Chọn JUL, Logback hoặc Log4j 2 | Thay đổi ngữ nghĩa nghiệp vụ |
| Logger / level | Quyết định sự kiện nào đủ mức để xử lý | Bật DEBUG có kiểm soát cho một package | Lọc dữ liệu nhạy cảm theo từng field |
| Filter | Quy tắc chấp nhận hoặc loại bản ghi | Bỏ heartbeat, chỉ gửi audit events vào sink riêng | Thay đổi nội dung bản ghi phức tạp hoặc gọi dịch vụ ngoài |
| Formatter / layout / encoder | Biểu diễn dữ liệu thành byte/text/cấu trúc | JSON Lines theo schema của tổ chức | Quyết định giao dịch nghiệp vụ thành công hay thất bại |
| Handler / appender / sink | Ghi hoặc chuyển dữ liệu tới đích | File rotation, console, mạng, hàng đợi | Chứa truy vấn database phục vụ quyết định kinh doanh |
| Context propagation | Gắn và truyền correlation information | requestId, traceId qua executor/HTTP | Lưu dữ liệu toàn cục cho mọi request |
| Collector / exporter | Batch, retry, routing, xử lý và chuyển telemetry | Gửi log đến hệ lưu trữ tập trung | Sửa hoặc suy diễn sự kiện nghiệp vụ đã mất từ nguồn |

Một yêu cầu có thể đụng nhiều lớp. Ví dụ **“ghi log JSON có traceId và gửi qua mạng”** cần ba phần khác nhau: tạo/truyền trace context, encoder JSON và cơ chế export/collection. Không nên viết tất cả trong một Formatter rồi gọi HTTP từ đó: Formatter cần dễ kiểm thử, còn mạng có timeout, retry, backpressure và shutdown riêng.

### 3.1. API/facade và provider

**API/facade** là hợp đồng mà phần lớn mã Java gọi. Nó nên ổn định để công cụ ghi log có thể được thay thế, cấu hình hoặc cập nhật theo nhu cầu vận hành. **Provider/backend** là nơi giải quyết các thao tác thực tế như lọc, định tuyến, định dạng, ghi file, batching.

- **JUL (java.util.logging):** có sẵn trong JDK, gồm Logger, LogRecord, Handler, Filter, Formatter, LogManager và ErrorManager. Phù hợp để hiểu cơ chế nền tảng mà không cần thư viện ngoài.
- **SLF4J:** facade phổ biến có API logging và MDC. **SLF4J 2.x** tìm provider tương thích khi chạy; cần tránh thiếu provider hoặc nhiều provider ngoài ý muốn. Phần ghi log thực tế do provider/backend đảm nhiệm.
- **Logback:** backend thường dùng với SLF4J, có appender, encoder/layout, filter, TurboFilter và cấu hình riêng.
- **Log4j 2:** có API, implementation và hệ plugin cho các thành phần như appender, filter, layout, lookup hoặc component khác; khi dùng kết hợp SLF4J cần chọn binding/bridge đúng chiều.
- **System.Logger:** API logging được cung cấp trong JDK từ Java 9. Cơ chế mở rộng nâng cao là **System.LoggerFinder**; triển khai provider cần xem xét lựa chọn provider, dịch vụ nạp lớp và khởi động JVM. Đây không phải đường mở rộng đầu tiên khi chỉ cần một sink hoặc formatter.

Tên và hành vi cụ thể của từng extension phụ thuộc framework và phiên bản. Một custom JUL Handler **không tự trở thành** một Logback Appender: hai bên tuân theo hợp đồng và vòng đời khác nhau.

### 3.2. Adapter và bridge cho nhiều API

Thư viện phụ thuộc có thể phát log qua những API khác nhau. **Adapter/bridge** chuyển một API về backend được chọn để tập trung cấu hình và collection. Dùng bridge khi thực sự có thư viện cần kết nối.

Ví dụ về hướng đi đúng cần thiết kế rõ:

~~~text
Application using SLF4J ----> one SLF4J provider/backend
Library using JUL ----------> carefully chosen JUL-to-backend bridge
                                      |
                                      v
                              one backend pipeline
~~~

**Tránh bridge vòng tròn** như JUL → SLF4J → JUL; log có thể quay lại điểm phát, gây lặp, tràn stack hoặc lỗi khó chẩn đoán. Không thêm đồng thời nhiều cách định tuyến ngược chiều chỉ vì từng thư viện đều có “bridge”. Kiểm tra dependency graph thực tế, provider được nạp lúc chạy và output một sự kiện mẫu.

## 4. Khả năng mở rộng của java.util.logging

JUL phân tách trách nhiệm khá rõ ràng. Hiểu các lớp sau giúp bạn đọc được cả kiến trúc của những logging backend khác.

### 4.1. Logger và hệ phân cấp

**Logger** nhận sự kiện từ mã ứng dụng. Các logger thường tạo một cây tên, ví dụ:

~~~text
(anonymous/root logger)
    |
    +--- com.example
             |
             +--- com.example.order
             |
             +--- com.example.payment
~~~

LogRecord phát ra từ logger con có thể được chuyển tới handler của logger cha nếu **useParentHandlers** được bật. Do đó một bản ghi có thể xuất hiện hai lần khi một handler riêng đã ghi rồi bản ghi lại tiếp tục lên root logger.

- **setLevel(Level.FINE)** tại logger điều khiển ngưỡng xử lý của chính logger; mức hiệu lực có thể kế thừa nếu chưa khai báo.
- **setUseParentHandlers(false)** ngăn forwarding lên các handler của cha, phù hợp khi cố ý tạo pipeline riêng.
- **addHandler/removeHandler** gắn hoặc tách đích xuất. Khi gắn tài nguyên như file/socket, cần quản lý thời điểm flush/close.

Không nên tạo logger mới cho từng request hoặc từng user. Thông thường logger có tên ổn định theo lớp/package; dữ liệu biến thiên như requestId nằm trong thuộc tính/context của từng sự kiện.

### 4.2. LogRecord: hợp đồng dữ liệu sự kiện

**LogRecord** mang level, message, thông tin nguồn, thời điểm, tham số, Throwable và các metadata do JUL cung cấp. Nó là đối tượng dữ liệu mà formatter, filter và handler nhận.

Các trường nên có ý nghĩa nhất quán. Một event như **order.failed** có thể kèm requestId, orderId phi nhạy cảm, loại lỗi và dữ liệu đủ để điều tra. Nếu bắt buộc xuất JSON thực thụ, cần một chiến lược định dạng và escape hợp lệ; ghép tay các field thành chuỗi không tự động trở thành structured logging.

**Một lưu ý:** không nên phụ thuộc vào việc Formatter luôn có thể lấy chính xác thông tin caller bằng reflection hoặc stack crawling; tính toán caller location có chi phí và có thể thay đổi theo cách log được gọi.

### 4.3. Handler: đích ghi và vòng đời

**Handler** là điểm mở rộng của JUL để quyết định một LogRecord được xử lý thế nào. Các phương thức chính:

~~~java
public abstract void publish(LogRecord record);
public abstract void flush();
public abstract void close();
~~~

Một Handler có thể ghi console, file, memory buffer hoặc chuyển bản ghi đến queue. Nếu viết Handler riêng, phải tính tới **thread safety**, tình huống nhiều thread gọi publish, cấu hình level/filter, xử lý lỗi I/O, flush, close và chính sách khi đích xuất chậm.

- **ConsoleHandler, FileHandler, StreamHandler** là những implementation có sẵn trong JUL.
- Handler có **Level** riêng, có thể cao hơn mức logger. Một record được logger chấp nhận chưa chắc qua được handler.
- Handler còn có **Filter**. Trong implementation tùy biến, nên gọi **isLoggable(record)** để tôn trọng cả level và filter thay vì kiểm tra message thủ công.
- Lỗi trong sink không được làm luồng nghiệp vụ lặp lại vô hạn hoặc tạo thêm log qua chính sink đang lỗi. JUL có **ErrorManager/reportError** để hỗ trợ báo lỗi bên trong Handler.

### 4.4. Filter: chính sách chọn sự kiện

**java.util.logging.Filter** là một interface chức năng:

~~~java
boolean isLoggable(LogRecord record);
~~~

Bộ lọc nên **nhanh, ổn định, không gây tác dụng phụ**. Một filter có thể:

- Chỉ nhận event có tên bắt đầu bằng **order.** cho audit sink.
- Bỏ bản ghi heartbeat quá thường xuyên khỏi một đích phụ.
- Áp dụng quy tắc lấy mẫu có chủ đích (nếu chính sách lưu giữ cho phép).
- Phân tuyến theo level hoặc metadata đã có.

Không nên dùng filter thay việc kiểm soát dữ liệu nhạy cảm từ nguồn. Record có thể đi tới các sink khác với filter khác nhau; nếu có PII, hãy bảo vệ dữ liệu ở nơi tạo sự kiện và tại pipeline được kiểm soát.

### 4.5. Formatter: cách biểu diễn, không phải đích gửi

**java.util.logging.Formatter** chuyển LogRecord thành chuỗi. Nó có thể tạo text một dòng hoặc một cấu trúc JSON được escape đúng. Định dạng nên được kiểm thử như một chức năng thuần túy; không tạo network request ngay trong format().

Trong một kiến trúc có nhiều sink, hai Handler có thể có Formatter khác nhau, ví dụ console dễ đọc và file JSON Lines. Nhưng hãy giữ **event name** và **metadata** nhất quán để tránh mỗi đích diễn giải sai ý nghĩa sự kiện.

Nếu tự viết JSON, phải xử lý ký tự điều khiển, dấu nháy, Unicode, newline và exception đúng cấu trúc; trong production, một encoder/thư viện đã kiểm thử thường an toàn hơn.

### 4.6. LogManager và cấu hình

**LogManager** quản lý cấu hình logging trong JUL. Những thiết lập thường gặp là tên handler, level, formatter và lựa chọn file cấu hình. Ví dụ một tệp **logging.properties**:

~~~properties
.level = INFO
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.order.level = FINE
~~~

Lệnh Java có thể chỉ định file này khi **khởi động JVM**:

~~~bash
java -Djava.util.logging.config.file=logging.properties Main
~~~

Đây là ví dụ cấu hình minh họa; Main cần là một lớp đã biên dịch trong ứng dụng thực tế. Ngưỡng tại logger và handler phải phối hợp: **com.example.order.level=FINE** chưa đủ để thấy FINE ở console nếu ConsoleHandler vẫn là INFO. Việc thay cấu hình khi ứng dụng đang chạy cần hiểu cách reload/reconfiguration của giải pháp sử dụng và tác động tới các Handler hiện có.

## 5. Ví dụ hoàn chỉnh: mở rộng Filter, Formatter và Handler trên Java 17+

Ví dụ sau dùng **chỉ JDK**, không cần Maven, Gradle hoặc SLF4J. Mục tiêu là tạo một pipeline riêng:

1. **Logger** cho phép mức FINE trở lên.
2. **Handler** chỉ nhận INFO trở lên.
3. **Filter** chỉ nhận sự kiện có tên bắt đầu bằng order.
4. **Formatter** xuất level, event, requestId, orderId và loại exception.
5. **Handler** đưa kết quả ra stdout. Trong ứng dụng thật, sink có thể là file/queue/collector, còn cơ chế tương tự.

Tạo tệp **LoggingExtensionPointsDemo.java**:

~~~java
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingExtensionPointsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.order");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Handler sink = new StdoutHandler();
        sink.setLevel(Level.INFO);
        sink.setFilter(record -> record.getMessage().startsWith("order."));
        sink.setFormatter(new EventFormatter());
        logger.addHandler(sink);

        try {
            logger.fine("order.debug");  // Rejected by handler level.
            logger.info("health.ping");  // Rejected by handler filter.

            LogRecord ok = new LogRecord(Level.INFO, "order.created");
            ok.setParameters(new Object[] {"req-42", "A-100"});
            logger.log(ok);

            LogRecord failed = new LogRecord(Level.WARNING, "order.failed");
            failed.setParameters(new Object[] {"req-43", "A-101"});
            failed.setThrown(new IllegalStateException("payment unavailable"));
            logger.log(failed);
            sink.flush();
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] args = record.getParameters();
            String requestId = args != null && args.length > 0 ? String.valueOf(args[0]) : "-";
            String orderId = args != null && args.length > 1 ? String.valueOf(args[1]) : "-";
            String event = record.getMessage();
            String line = record.getLevel().getName() + " event=" + event
                    + " requestId=" + requestId + " orderId=" + orderId;
            if (record.getThrown() != null) {
                line += " error=" + record.getThrown().getClass().getSimpleName();
            }
            return line + System.lineSeparator();
        }
    }

    private static final class StdoutHandler extends Handler {
        private boolean closed;

        @Override
        public synchronized void publish(LogRecord record) {
            if (!closed && isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
        }

        @Override
        public synchronized void flush() {
            System.out.flush();
        }

        @Override
        public synchronized void close() {
            flush();
            closed = true;
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 LoggingExtensionPointsDemo.java
java LoggingExtensionPointsDemo
~~~

Kết quả **stdout chính xác** (đã kiểm chứng bằng chạy thực tế):

~~~text
INFO event=order.created requestId=req-42 orderId=A-100
WARNING event=order.failed requestId=req-43 orderId=A-101 error=IllegalStateException
~~~

**Vì sao chỉ có hai dòng?**

- **order.debug** ở FINE vượt qua level của Logger nhưng **không qua level INFO của Handler**.
- **health.ping** ở INFO qua Handler level nhưng **bị Filter loại** do message không bắt đầu bằng order.
- **order.created** và **order.failed** thỏa cả level và Filter; EventFormatter đọc parameters và Throwable để tạo text có cấu trúc dễ tìm kiếm.
- **setUseParentHandlers(false)** tránh ghi lặp qua handler của logger cha.
- **removeHandler + close** cho thấy điểm cần dọn tài nguyên khi lifecycle kết thúc.

**Giới hạn cố ý của demo:** chương trình không tích hợp framework, không xuất JSON, không truyền distributed trace và không có xử lý lỗi I/O. Các field được ghép thành text đơn giản từ dữ liệu đã biết; nếu đưa input không tin cậy vào formatter thật, phải escape/validate đúng để tránh log injection. **StdoutHandler** chỉ minh họa hợp đồng của Handler; production nên dùng sink có sẵn hoặc handler được thiết kế đầy đủ về concurrency, xử lý lỗi, backpressure, flush và shutdown. Không lấy ví dụ tối giản này làm logging framework mới.

### 5.1. Thử thay đổi từng điểm mở rộng

Có thể tự thí nghiệm một thay đổi mỗi lần:

- Đổi **sink.setLevel(Level.FINE)**: event order.debug xuất hiện, bởi filter vẫn chấp nhận tiền tố order.
- Giữ Handler INFO nhưng đổi filter thành chỉ chấp nhận event bắt đầu bằng **order.failed**: output chỉ còn bản ghi WARNING.
- Đổi **EventFormatter** để thêm tên logger và timestamp: thông tin xuất thay đổi, nhưng mã phát event không đổi.
- Bật **setUseParentHandlers(true)**: cần xét handler của logger cha; kết quả có thể bị ghi lặp hoặc xuất thêm ra stderr tùy cấu hình môi trường.

Đây là cách kiểm tra ranh giới tốt: đổi một chính sách có phạm vi hẹp và quan sát bản ghi ở lớp tương ứng.

## 6. Cùng ý tưởng trong SLF4J, Logback và Log4j 2

Trong dự án dùng facade, mã ứng dụng thường chỉ biết API:

~~~java
// Minh họa; cần dependency SLF4J và provider phù hợp.
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG = LoggerFactory.getLogger(OrderService.class);

    public void complete(String orderId) {
        LOG.info("event=order.completed orderId={}", orderId);
    }
}
~~~

Đoạn này là *mảnh code tích hợp*, không phải ứng dụng độc lập chạy chỉ với JDK. Cú pháp **{}** là placeholder tham số của SLF4J; nó giúp hoãn việc định dạng đến thời điểm backend cần xử lý theo cách API/provider hỗ trợ.

Ranh giới triển khai thường gặp:

~~~text
Application -> SLF4J API
                 |
                 v
          selected provider
                 |
       +---------+----------+
       |                    |
  policy/filter         context / MDC
       |                    |
       +---------+----------+
                 |
           Appender / sink
                 |
           Encoder / layout
~~~

- **Logback:** custom Appender khi cần đích mới; encoder/layout khi cần biểu diễn mới; filter/TurboFilter khi cần loại hoặc chấp nhận sự kiện tại điểm phù hợp. Không viết custom appender chỉ để đổi định dạng console nếu cấu hình encoder có sẵn đáp ứng.
- **Log4j 2:** hệ plugin cho phép xây dựng Appender, Layout, Filter và các thành phần được framework khám phá theo cơ chế tương ứng. Hãy tuân thủ hợp đồng plugin, cấu hình và vòng đời của chính phiên bản đang dùng.
- **SLF4J:** facade làm hợp đồng gọi log; nó không phải nơi bạn viết logic I/O của backend. Việc thay provider cần cấu hình dependency/runtime nhất quán.

**Câu hỏi kiến trúc cần trả lời trước khi thêm extension:** Backend hiện tại đã hỗ trợ sẵn JSON encoder, rolling file, async appender, filtering hoặc routing chưa? Nếu có, ưu tiên cấu hình thành phần được hỗ trợ. Custom code cần thiết khi có yêu cầu thật sự khác biệt, vì mỗi extension tự viết là một thành phần phải kiểm thử, giám sát và duy trì qua nâng cấp.

## 7. Điểm mở rộng ngữ cảnh: MDC và correlation ID

Một event riêng lẻ rất khó điều tra nếu không biết nó thuộc request hay tác vụ nào. Ngữ cảnh phổ biến gồm **requestId, traceId, spanId, service.name, môi trường và phiên bản ứng dụng**. Đây là trách nhiệm xuyên suốt các lớp, không chỉ formatter.

Với SLF4J, **MDC** là API để gắn cặp key–value vào logging context hiện tại. Mảnh code sau cần SLF4J và backend hỗ trợ context:

~~~java
import org.slf4j.MDC;

// requestId phải được tạo/kiểm tra ở ranh giới nhận request.
try (MDC.MDCCloseable ignored = MDC.putCloseable("requestId", requestId)) {
    processOrder();
}
~~~

Provider/encoder phải được cấu hình để thực sự xuất requestId; việc đặt MDC không đồng nghĩa mọi output đều có trường đó. Khi xử lý kết thúc, context cần được dọn để thread tái sử dụng không giữ ID của request khác.

**Concurrency là điểm dễ sai nhất.** MDC có thể gắn với ngữ cảnh thread; chuyển sang ExecutorService, CompletableFuture, scheduler hoặc các mô hình xử lý khác có thể làm mất hoặc lẫn context nếu hệ thống không propagate đúng cách. Cần cơ chế truyền context phù hợp với ứng dụng, thư viện và mô hình thread đang dùng. Không coi **ThreadLocal** là kho context an toàn cho toàn bộ tác vụ phân tán.

**Distributed tracing** truyền trace context giữa các tiến trình. Ví dụ HTTP có thể dùng chuẩn **W3C Trace Context (traceparent)**. OpenTelemetry Java có các cơ chế instrumentation và context propagation; nếu chọn stack này, cần kết nối exporter và log integration đúng để đưa traceId/spanId vào log. Một log có traceId **không bảo đảm** bản trace đã được lưu: sampling, exporter hoặc network có thể khiến nó không có trong backend.

**Phân biệt:**
- **requestId**: thường là ID request ở tầng ứng dụng/gateway, phục vụ đối chiếu log.
- **traceId**: ID của trace trải dài nhiều span/service.
- **spanId**: ID của công đoạn hiện tại trong trace.

Các ID này có thể được dùng để liên kết, nhưng không được mặc định thay thế lẫn nhau. Chỉ ghi các ID và thuộc tính không vi phạm chính sách dữ liệu của tổ chức.

## 8. Mở rộng đầu ra và pipeline ngoài JVM

Không phải mọi yêu cầu đều nên giải quyết trong logging backend của JVM. Có thể tách lớp vận chuyển/biến đổi telemetry:

~~~text
Service A      Service B
    |              |
    +-- stdout ----+------> Agent / Collector
    |              |                |
    +-- metrics ---+                +--> Route / Batch / Retry
    |              |                |
    +-- spans -----+                +--> Observability backend
~~~

**Khi nào nên xử lý ở ứng dụng?**
- Định nghĩa event name, severity, semantic fields và context nghiệp vụ.
- Đảm bảo dữ liệu nhạy cảm không được sinh ra như telemetry ngoài ý muốn.
- Thêm instrumentation theo ranh giới giao dịch, request và dependency.

**Khi nào nên xử lý ở collector/pipeline?**
- Định tuyến theo môi trường/dịch vụ, chọn backend, buffering/batching, chuyển giao qua mạng.
- Bổ sung tài nguyên kỹ thuật chung (nếu đáng tin cậy), giảm lưu lượng hoặc thực hiện transformation được phê duyệt.
- Quản lý thất bại exporter và quan sát sức khỏe của đường vận chuyển telemetry.

Một collector không thể khôi phục context đã thiếu hoàn toàn ở nguồn. Ngược lại, mỗi request nghiệp vụ cũng không nên trực tiếp mở kết nối HTTP tới hệ thống lưu trữ log rồi retry không giới hạn. Sự tách biệt này giúp giảm phụ thuộc giữa ứng dụng và hạ tầng quan sát.

## 9. Những hợp đồng cần giữ khi tự viết extension

### 9.1. Hiệu năng và chính sách khi đích xuất chậm

Synchronous Handler/Appender chạy trên luồng phát log có thể làm tăng latency request. Nếu sink ghi file chậm hoặc mạng không sẵn sàng, thao tác logging có thể kéo dài, chặn luồng hoặc thất bại. Async queue giảm tác động trong một số trường hợp, nhưng mang rủi ro **queue đầy**, **dropped records**, **mất bản ghi khi process chết** và **thứ tự ghi khác với thứ tự xử lý**.

Trước khi dùng async, cần quyết định rõ:
- Queue có kích thước bao nhiêu, điều gì xảy ra khi đầy: block, drop, spill hay fail?
- Khi shutdown có flush/drain với thời hạn hợp lý không?
- Có metrics cho số bản ghi bị bỏ, độ sâu queue và lỗi exporter không?
- Dữ liệu audit bắt buộc có yêu cầu độ bền riêng không?

Không khẳng định “async luôn nhanh hơn” nếu workload nhỏ, tốc độ xử lý cao hoặc chính sách block khi queue đầy chưa được đo.

### 9.2. Xử lý lỗi bên trong extension

Tuyệt đối tránh tình huống handler gặp lỗi rồi dùng **chính logger đang trục trặc** để ghi tiếp lỗi đó; dễ tạo recursion vô hạn. Một extension đúng nên:

- Tuân thủ cơ chế báo lỗi của backend (với JUL có **ErrorManager** và helper **reportError** trong Handler).
- Không nuốt lỗi một cách vô điều kiện khi nghiệp vụ có yêu cầu bảo toàn sự kiện.
- Đóng file/socket/queue khi stop; dọn thread nền; flush đúng lúc.
- Kiểm tra tình huống mất kết nối, disk full, encoding error, startup/reconfiguration và shutdown.
- Không làm hỏng đường xử lý nghiệp vụ chỉ do thay đổi logging, trừ khi có yêu cầu độ bền/hợp đồng audit được thiết kế rõ.

### 9.3. Schema và khả năng tương thích

Khi thay formatter/encoder, phải giữ hợp đồng dữ liệu cho downstream consumers: event name, trường bắt buộc, kiểu dữ liệu, đơn vị đo và dấu thời gian.

Ví dụ, đổi **duration_ms** thành **duration_ns** mà không thay tên field và parser có thể làm sai dashboard gấp một triệu lần. Đổi severity từ **WARNING** sang **WARN** cũng có thể làm hỏng rule nếu công cụ lọc theo giá trị cố định. Nếu schema thay đổi đáng kể, cần quản lý phiên bản và phối hợp nơi tiêu thụ dữ liệu.

### 9.4. Bảo mật và kiểm soát cardinality

- Không ghi mật khẩu, bearer token, cookie, khóa bí mật, payment credentials hoặc toàn bộ payload nhạy cảm.
- Nếu dùng JSON, cần escaping hợp lệ; nếu dùng text, phải kiểm soát newline, ký tự điều khiển và những trường do người dùng cung cấp để hạn chế **log injection**.
- Cẩn thận với MDC và exception message: chúng cũng có thể chứa dữ liệu riêng tư.
- Tránh đưa requestId/userId/raw URL có ID vào nhãn metrics có cardinality cao. Các ID đó có thể phù hợp hơn với log/traces đã kiểm soát quyền truy cập.
- Hạn chế quyền truy cập log, đặt retention phù hợp và bảo vệ dữ liệu trong transport/storage.

## 10. Chọn điểm mở rộng theo yêu cầu cụ thể

| Yêu cầu | Điểm mở rộng phù hợp | Kiểm chứng quan trọng |
| --- | --- | --- |
| Chuyển log console text sang JSON | Encoder/Formatter/Layout | JSON hợp lệ, field types, escape, một event/một dòng |
| Ghi thêm file riêng cho event audit | Handler/Appender + filter/routing | Không rò event ngoài audit, file lifecycle và retention |
| Chỉ bật debug cho package điều tra | Logger level + handler/backend config | Event có xuất ở đúng sink, không gây lũ log |
| Mã nguồn không phụ thuộc backend | Facade/API | Runtime chỉ có provider phù hợp, không lặp bridge |
| Bổ sung requestId vào tất cả bước xử lý | Context + propagation + encoder | ID đúng qua thread, không rò sang request khác |
| Gửi log qua mạng nhưng không làm chậm request | Appender/collector + buffering policy | Backpressure, retry, drop metrics, graceful shutdown |
| Loại event heartbeat khỏi sink phụ | Filter tại đúng sink | Event khác giữ nguyên, sink chính vẫn phù hợp |
| Kết nối thư viện JUL vào backend chung | Bridge một chiều được hỗ trợ | Không vòng lặp, không bản ghi trùng |
| Giảm nội dung nhạy cảm | Không phát sinh tại nguồn + redaction an toàn | Dữ liệu thật không xuất hiện ở mọi đích, kể cả lỗi |
| Thêm loại log event mới | Mã nghiệp vụ định nghĩa event và thuộc tính | Ý nghĩa sự kiện, schema và severity thống nhất |

**Quy tắc thực dụng:** Nếu chỉ cần thay đổi *cách nhìn* dữ liệu, bắt đầu từ formatter/encoder. Nếu thay đổi *nơi dữ liệu đi*, bắt đầu từ handler/appender/pipeline. Nếu thay đổi *dữ liệu nào được nhận*, xem level/filter. Nếu thay đổi *ngữ cảnh của dữ liệu*, xem instrumentation và propagation. Nếu thay đổi *hợp đồng mà business code gọi*, xem facade/provider.

## 11. Quy trình thiết kế, kiểm thử và triển khai extension

Một extension tốt cần có hợp đồng rõ trước khi viết code.

**Bước 1 — Xác định ranh giới.** Viết rõ input (LogRecord/log event), output (bytes/file/network), chính sách level, filter, metadata, exception, ownership và điều kiện thất bại.

**Bước 2 — Kiểm tra khả năng cấu hình có sẵn.** Nếu backend đã hỗ trợ rolling file, JSON encoder, HTTP exporter hoặc async appender tin cậy, ưu tiên tái sử dụng. Chỉ tạo custom extension khi yêu cầu cần một hành vi riêng.

**Bước 3 — Tách phần thuần túy khỏi I/O.** Formatter, validation schema và lọc đơn giản nên dễ test bằng input cố định; network/file operations có lifecycle và failure policy riêng.

**Bước 4 — Kiểm thử chức năng.** Với JUL, tạo LogRecord có Level, message, parameters và Throwable rồi xác nhận Filter, Formatter, Handler; kiểm tra trường null, Unicode, dấu nháy, newline và log trùng.

**Bước 5 — Kiểm thử tình huống vận hành.** Giả lập sink không sẵn sàng, queue đầy, nhiều thread, ứng dụng shutdown và cấu hình thay đổi. Kiểm tra không recursion hoặc memory leak; đo latency/tốc độ và mức cấp phát khi log volume cao.

**Bước 6 — Kiểm thử tích hợp.** Kiểm tra dependency runtime có đúng provider, bridge hoạt động một chiều, level thực tế của logger/handler và structured fields đến được backend; quan sát một trace/request mẫu end-to-end khi có correlation.

**Bước 7 — Triển khai có thể đảo ngược.** Cho phép thay cấu hình hoặc tắt extension khi cần; theo dõi dropped logs, queue depth, lỗi formatter/exporter và tác động CPU/memory. Không đánh đổi độ ổn định nghiệp vụ lấy telemetry dư thừa.

Một checklist QA nhỏ:

- Cùng một event xuất đúng số lần, đúng severity, đúng destination.
- Không có PII/token, không xuất chuỗi điều khiển độc hại chưa xử lý.
- Output có thể parse và schema đúng với pipeline downstream.
- Đã xét concurrency, exception, flush/close và trường hợp sink chết.
- RequestId/traceId đi đúng các bước được kỳ vọng.
- Có thể thay đổi chính sách mà không sửa phần lõi nghiệp vụ.

## 12. Các sai lầm hay gặp

**Sai lầm 1: “Muốn JSON thì viết handler ghi HTTP.”** Một Formatter/Encoder tốt xử lý biểu diễn; Appender/Collector xử lý I/O và vận chuyển. Trộn chúng sẽ khiến formatter khó test, xử lý lỗi phức tạp và dễ làm chậm request.

**Sai lầm 2: “Đã set logger FINE thì mọi FINE sẽ xuất.”** Handler cũng có level và filter. Ví dụ chạy độc lập ở mục 5 chứng minh record FINE bị handler INFO loại.

**Sai lầm 3: “Thêm nhiều bridge để gom log cho chắc.”** Bridge hai chiều có thể tạo vòng lặp; nhiều provider hoặc backend cùng nhận một event có thể tạo bản ghi trùng. Dùng một sơ đồ luồng rõ ràng và kiểm tra dependency runtime.

**Sai lầm 4: “Context của request luôn có ở luồng con.”** Executor/async có thể mất context. Cần propagation có kiểm soát và dọn context sau khi xử lý.

**Sai lầm 5: “Handler lỗi thì cứ log ERROR bên trong nó.”** Nếu thông điệp lỗi lại đi vào chính handler hỏng, hệ thống có thể lặp không dứt. Dùng error handling của framework và chính sách fallback an toàn.

**Sai lầm 6: “Filter là hàng rào bảo mật toàn bộ log.”** Một record có thể tới nhiều sink. Giảm thiểu dữ liệu nhạy cảm ngay từ nguồn, kết hợp kiểm soát ở mọi đoạn pipeline.

**Sai lầm 7: “Tất cả message nên thành một field text.”** Không có schema ổn định, các công cụ sẽ khó tìm kiếm/nhóm. Nên tách event, severity, service, requestId và error attributes khi phù hợp.

## 13. Bài thực hành tự đánh giá

1. Trong demo, vì sao **order.debug** không xuất hiện dù Logger được đặt ở FINE? Muốn in nó nhưng vẫn không in health.ping thì đổi đúng thuộc tính nào?
2. Nếu một bản ghi xuất hai lần khi cấu hình thêm console handler, hãy giải thích quan hệ giữa Logger con, parent handlers và việc gắn nhiều sink.
3. Một ứng dụng muốn cả console dễ đọc và file JSON. Bạn chọn một hay hai Handler? Mỗi đích cần gì để ghi cùng schema sự kiện mà có biểu diễn khác nhau?
4. Dịch vụ bị treo khi hệ lưu trữ log ngừng nhận dữ liệu. Hãy xác định lớp cần điều tra, chỉ số cần đo và chính sách khi queue đầy.
5. Nếu đổi backend từ JUL sang Logback, những phần nào của business code có thể cần chỉnh khi mã đang dùng JUL trực tiếp? Việc dùng một facade chung sẽ giảm phạm vi thay đổi ra sao?
6. Thiết kế log event **payment.rejected** gồm tên event ổn định, requestId, reason code phi nhạy cảm, severity phù hợp và exception nếu có. Nêu cách kiểm thử để không lộ token/card data.

**Gợi ý đáp án:**

- (1) Handler ở INFO loại FINE. Đổi **sink.setLevel(Level.FINE)**; filter vẫn chỉ giữ các event bắt đầu bằng order.
- (2) Logger con có thể chuyển record lên các Handler ở cha; phải kiểm tra **useParentHandlers** và danh sách Handler đã đăng ký.
- (3) Thường có hai destination/Appender/Handler (console và file), mỗi đích chọn formatter/encoder phù hợp; event semantics phải thống nhất.
- (4) Kiểm tra Appender/Handler, exporter hoặc collector; theo dõi blocked time, queue depth, dropped records và retries; chọn policy backpressure phù hợp cam kết dữ liệu.
- (5) Mã gọi JUL trực tiếp có thể cần adapter/migration khi muốn facade khác; mã gọi một facade ổn định giảm phụ thuộc ứng dụng vào backend.
- (6) Không ghi payment credentials, không đưa nguyên payload vào exception message; kiểm thử cả input nguy hiểm/newline và mọi output sink.

**Điểm cần ghi nhớ:** kiến trúc logging mở rộng tốt khi các lớp **phát sự kiện**, **chọn sự kiện**, **bổ sung ngữ cảnh**, **định dạng**, **ghi ra đích** và **vận chuyển** có ranh giới riêng. Cùng một event nghiệp vụ có thể đi tới nhiều nơi và nhiều định dạng, trong khi code nghiệp vụ vẫn giữ nguyên ý nghĩa và độ ổn định.
