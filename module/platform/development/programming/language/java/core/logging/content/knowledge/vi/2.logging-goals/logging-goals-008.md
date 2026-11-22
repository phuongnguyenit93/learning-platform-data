# Phân biệt log và trace trong Java

## 1. Mục tiêu bài học

Trong quá trình vận hành ứng dụng Java, **log** giúp biết sự kiện nào đã xảy ra, còn **trace (tracing)** giúp tái hiện đường đi và thời gian xử lý của một tác vụ, đặc biệt khi tác vụ đi qua nhiều hàm, thread hoặc dịch vụ. Hai nguồn dữ liệu bổ sung cho nhau trong quan sát và chẩn đoán hệ thống.

Sau bài này, bạn cần phân biệt được:

- **Log record**: một bản ghi về sự kiện, tại một thời điểm hoặc điểm thực thi.
- **Distributed trace**: một chuỗi các thao tác liên quan đến cùng một yêu cầu/nghiệp vụ; mỗi thao tác thường được biểu diễn bằng một **span**.
- **Mức log TRACE** của một số logging framework: chỉ là mức độ chi tiết của bản ghi log, **không tự tạo distributed trace**.
- **Stack trace** của exception: danh sách lời gọi hàm dẫn đến một vị trí lỗi, **khác với distributed trace**.

Bài sử dụng Java 17 và `java.util.logging` (JUL) để minh họa log, sau đó mô phỏng span nhằm làm rõ dữ liệu trace. Phần span tự xây dựng trong ví dụ là **mô phỏng phục vụ học tập**, chưa phải hệ thống distributed tracing thực tế.

## 2. Log: một sự kiện được ghi lại

Logging ghi nhận những điều ứng dụng muốn thông báo: bắt đầu xử lý, đăng nhập thành công, truy vấn thất bại, cấu hình bị thiếu, hoặc exception. Một log thường gồm:

- **Timestamp**: thời điểm phát sinh bản ghi.
- **Severity/level**: ví dụ `INFO`, `WARNING`, `SEVERE` trong JUL.
- **Logger/source**: class hoặc thành phần phát log.
- **Message**: điều đã xảy ra, có thể kèm khóa–giá trị mang ngữ cảnh.
- **Exception**: loại lỗi, thông điệp và stack trace khi cần chẩn đoán.
- **Correlation fields**: `trace_id`, `span_id`, `request_id` nếu ứng dụng đã gắn.

Ví dụ một log có cấu trúc (dữ liệu minh họa):

```text
2026-11-09T10:15:31.240Z INFO  OrderService trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 message="Order accepted" order_id=815
2026-11-09T10:15:31.275Z ERROR PaymentClient trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 message="Payment request failed" error="timeout"
```

Hai dòng này là **hai sự kiện riêng lẻ**. Chúng cho biết đơn hàng đã được tiếp nhận và một lời gọi thanh toán gặp lỗi, nhưng bản thân các dòng chưa chứng minh toàn bộ chuỗi thao tác ở giữa, phần nào gọi phần nào hoặc mỗi phần tốn bao lâu. Các trường `trace_id` và `span_id` khiến chúng có thể được liên kết với trace khi hệ thống đã triển khai tracing.

Log có thể được phát ở bất kỳ điểm cần quan sát nào, với tần suất và độ chi tiết tùy cấu hình. Console và file là **đích ghi log**; thay đổi đích không biến log thành trace.

## 3. Trace: hành trình xử lý của một yêu cầu

Trong ngữ cảnh observability, **trace** biểu diễn đường đi của một thao tác từ lúc bắt đầu đến khi kết thúc. Một trace gồm nhiều **span** có quan hệ cha–con hoặc quan hệ liên kết, chẳng hạn:

```text
Trace: xử lý checkout (trace_id dùng chung)
└── HTTP POST /checkout                 185 ms  [span gốc]
    ├── validateCart                     12 ms
    ├── reserveInventory                 90 ms
    │   └── SQL UPDATE inventory         54 ms
    └── persistOrder                     65 ms
```

Các thời lượng và tên thao tác ở trên chỉ minh họa. Trên hệ thống thực, có các span chạy **song song**, nên không cộng toàn bộ thời lượng span con để suy ra thời lượng span cha.

Một span thường mang:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `trace_id` | Định danh chung để nối các span thuộc cùng trace |
| `span_id` | Định danh riêng của một span |
| `parent_span_id` | ID của span cha nếu có; span gốc không có cha |
| Tên thao tác | Ví dụ `HTTP POST /checkout` hoặc `reserveInventory` |
| Thời điểm bắt đầu và duration | Biết thao tác bắt đầu lúc nào, kéo dài bao lâu |
| Status, attributes, events | Kết quả, thuộc tính kỹ thuật/nghiệp vụ và sự kiện trong span |

Với distributed tracing, ngữ cảnh trace cần đi theo request giữa các dịch vụ. Chẳng hạn Gateway, Order Service và Inventory Service đều có thể tạo span khác nhau nhưng giữ cùng `trace_id`. Hệ thống tracing tập hợp các span để hiển thị một timeline hoặc sơ đồ phụ thuộc.

Trace cho thấy **mối quan hệ và độ trễ** của các thao tác. Nó không có nhiệm vụ lưu tất cả sự kiện chi tiết như log. Span có thể chứa events, nhưng events không thay thế toàn bộ thông điệp log, stack trace hay thông tin nghiệp vụ mà đội vận hành cần.

## 4. So sánh trực tiếp log và trace

| Góc nhìn | Log | Trace |
| --- | --- | --- |
| Câu hỏi chính | **Điều gì đã xảy ra?** | **Yêu cầu đi qua đâu, theo quan hệ nào và mất bao lâu?** |
| Đơn vị dữ liệu | Một log record / sự kiện | Một span; nhiều span hợp thành trace |
| Trục thời gian | Thời điểm sự kiện; có thể kèm dữ liệu khác | Điểm bắt đầu, duration và quan hệ giữa các span |
| Quan hệ nhân quả | Không tự có; cần ngữ cảnh/ID để liên kết | Được mô tả bằng parent/child hoặc span links |
| Thông tin lỗi | Message, exception, stack trace, ngữ cảnh | Span lỗi, vị trí trong luồng xử lý, thời lượng; có thể kèm exception event |
| Tìm kiếm | Thường theo level, keyword, class, thời gian, request ID | Thường theo trace ID, tên thao tác, service, latency, status |
| Dung lượng | Phụ thuộc mức log và tần suất phát sự kiện | Phụ thuộc số span/attributes/events và chính sách sampling |
| Công cụ Java thường gặp | JUL, SLF4J + Logback/Log4j2 | OpenTelemetry API/SDK, agent và collector/backend tương thích |

**Không có quan hệ một–một bắt buộc**: một span có thể có nhiều log, không có log hoặc một log có thể xuất hiện ngoài mọi trace (ví dụ lúc ứng dụng khởi động). Cũng có trace được lưu nhưng log tương ứng bị lọc hoặc đã hết thời hạn lưu giữ.

### Ví dụ thực tế: lỗi thanh toán

Giả sử người dùng báo đơn hàng xử lý chậm rồi thất bại:

- **Log** của `PaymentClient` có thể cho biết timeout, endpoint, retry attempt và exception cụ thể.
- **Trace** có thể cho thấy request đi từ Gateway → Order Service → Payment Service, trong đó span gọi Payment Service chiếm phần lớn thời gian.
- **Kết hợp cả hai**: mở trace để xác định span chậm, lấy `trace_id`/`span_id` để tìm các log liên quan, rồi đọc exception và chi tiết retry nhằm xác định nguyên nhân.

Nếu chỉ nhìn log, nhiều request đồng thời có thể làm các dòng xen kẽ khó theo dõi; nếu chỉ nhìn trace, bạn có thể biết span nào chậm nhưng thiếu lý do nghiệp vụ hoặc stack trace cần để sửa lỗi.

## 5. Ba cách dùng từ “trace” dễ gây nhầm

### 5.1. TRACE là một mức log

Trong SLF4J/Logback và một số framework khác, `TRACE` thường là mức log có độ chi tiết cao hơn `DEBUG`. Ví dụ với SLF4J (đây là **đoạn minh họa yêu cầu dependency SLF4J**, không phải chương trình Java độc lập):

```java
logger.trace("Entering calculateTotal, itemCount={}", itemCount);
logger.debug("Discount rule selected: {}", ruleName);
logger.info("Order calculation completed");
```

Lời gọi `logger.trace(...)` vẫn tạo **log record**. Chỉ bật mức TRACE **không tự động** tạo `trace_id`, span, timeline hay distributed tracing.

JUL `java.util.logging.Level` **không có hằng `TRACE`**. JUL dùng `FINE`, `FINER` và `FINEST` cho logging chi tiết; không áp dụng máy móc phép đổi tên hay coi các mức này hoàn toàn tương đương với cấu hình của mọi framework.

### 5.2. Stack trace là chuỗi lời gọi trong exception

`Exception` có stack trace cho biết các method nằm trên call stack tại nơi tạo hoặc ghi nhận throwable. Ví dụ:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex.printStackTrace();
}
```

`printStackTrace()` mặc định in exception và call stack vào `System.err`. Stack trace hữu ích để xác định vị trí lỗi trong mã Java, nhưng **không biểu diễn mọi thao tác xuyên nhiều dịch vụ** và thường không mang thời lượng từng bước. Trong ứng dụng có logging framework, nên log exception qua logger và dùng formatter hỗ trợ stack trace để có level và thông tin tương quan.

### 5.3. Distributed trace là chuỗi span

Distributed trace dùng `trace_id` để nối các span cùng yêu cầu và `span_id`/`parent_span_id` để tái hiện quan hệ thực thi. Đây là nghĩa của “tracing” trong hệ thống quan sát hiện đại. Một mức log tên TRACE, một stack trace và distributed trace có cùng chữ “trace” nhưng phục vụ mục đích khác nhau.

## 6. Ví dụ Java 17 chạy được: log sự kiện và mô phỏng hai span

Ví dụ dưới đây dùng thư viện có sẵn của JDK. Chương trình làm ba việc: phát log nghiệp vụ qua JUL; tạo hai bản ghi span giả lập cho `checkout` và `reserveStock`; in dữ liệu span để thấy quan hệ cha–con.

Tạo file `LogTraceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogTraceDemo {
    private static final Logger LOG =
            Logger.getLogger(LogTraceDemo.class.getName());
    private static final List<Span> SPANS = new ArrayList<>();

    record Span(String traceId, String spanId, String parentSpanId,
                String name, long startNanos, long durationNanos) {}

    private static String newId(int length) {
        return UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, length);
    }

    private static void log(String traceId, String spanId, String message) {
        LOG.info("trace_id=" + traceId
                + " span_id=" + spanId
                + " message=" + message);
    }

    private static void reserveStock(String traceId, String parentSpanId) {
        String spanId = newId(16);
        long started = System.nanoTime();
        try {
            log(traceId, spanId, "Checking stock");
            int available = 2;
            if (available == 0) {
                throw new IllegalStateException("Out of stock");
            }
            log(traceId, spanId, "Stock reserved");
        } finally {
            SPANS.add(new Span(
                    traceId, spanId, parentSpanId, "reserveStock",
                    started, System.nanoTime() - started));
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            String traceId = newId(32);
            String checkoutSpanId = newId(16);
            long started = System.nanoTime();

            try {
                log(traceId, checkoutSpanId, "Checkout started");
                reserveStock(traceId, checkoutSpanId);
                log(traceId, checkoutSpanId, "Checkout completed");
            } finally {
                SPANS.add(new Span(
                        traceId, checkoutSpanId, null, "checkout",
                        started, System.nanoTime() - started));
            }

            System.out.println("TRACE (local demo):");
            SPANS.stream()
                    .sorted(Comparator.comparingLong(Span::startNanos))
                    .forEach(span -> System.out.printf(
                            Locale.ROOT,
                            "name=%s trace_id=%s span_id=%s parent=%s "
                                    + "duration_ms=%.3f%n",
                            span.name(),
                            span.traceId(),
                            span.spanId(),
                            span.parentSpanId() == null
                                    ? "none" : span.parentSpanId(),
                            span.durationNanos() / 1_000_000.0));
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Chạy bằng Java 17 trở lên từ thư mục chứa file:

```bash
javac LogTraceDemo.java
java LogTraceDemo
```

**Điều quan sát được:**

1. JUL phát **bốn dòng INFO** có message lần lượt là `Checkout started`, `Checking stock`, `Stock reserved`, `Checkout completed`. Hai dòng ở `checkout` dùng `checkoutSpanId`; hai dòng `reserveStock` dùng span ID riêng.
2. Chương trình in **hai bản ghi span**: `checkout` có `parent=none`, còn `reserveStock` có `parent` bằng ID của `checkout`. Cả hai span mang **cùng một `trace_id`**.
3. `duration_ms` do `System.nanoTime()` đo nên thay đổi theo từng lần chạy; các ID sinh bằng `UUID` cũng khác nhau. Vì vậy **không có output số liệu/ID cố định** để so sánh nguyên văn.
4. `ConsoleHandler` của JUL phát log vào `System.err`, còn phần in span dùng `System.out`. Terminal thường hiển thị cả hai, nhưng khi redirect hoặc gộp hai luồng, thứ tự hiển thị giữa chúng có thể khác.

**Giới hạn quan trọng của ví dụ:** danh sách `SPANS` chỉ là dữ liệu trong bộ nhớ của **một tiến trình**. Việc tạo `Span` record và in ra console **không tự gửi trace cho Jaeger, Zipkin hay một collector**. Tracing thực tế cần instrumentation, context propagation, exporter/collector và backend. Trong ví dụ, `System.nanoTime()` phù hợp để đo **khoảng thời gian trôi qua trong một JVM**, không phải timestamp tuyệt đối dùng để hợp nhất dữ liệu giữa máy khác nhau. Logger/tracer ở hệ thống đa luồng còn cần cơ chế truyền context đúng theo thread/task.

## 7. Gắn log với trace qua context

Để kết hợp log và tracing, thông tin tương quan thường cần có trong cả hai loại dữ liệu:

```text
Request A
  trace_id = T
  span checkout = S1
      log: "Checkout started"  trace_id=T span_id=S1
      span reserveStock = S2, parent=S1
          log: "Stock reserved" trace_id=T span_id=S2
      log: "Checkout completed" trace_id=T span_id=S1
```

Ký hiệu `T`, `S1`, `S2` ở trên là ký hiệu giải thích, không phải định dạng ID gửi qua mạng. Từng span có ID riêng và cùng trace ID. Các log mang ID này có thể được tìm trong hệ thống lưu log để đi từ một span đang lỗi đến thông điệp chi tiết.

Với HTTP giữa các dịch vụ, tiêu chuẩn **W3C Trace Context** thường dùng header `traceparent` để mang thông tin trace. Ví dụ cú pháp hợp lệ:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Theo cú pháp phiên bản `00`, chuỗi gồm version, trace ID dạng 32 ký tự hex, parent ID dạng 16 ký tự hex và trace flags dạng hai ký tự hex. ID trong header là **span ID của bên gọi hiện tại**, không phải yêu cầu mọi dịch vụ cùng dùng một span ID; dịch vụ nhận tiếp tục trace ID và tạo span ID mới cho thao tác của mình. Flag lấy mẫu liên quan đến quyết định thu thập trace; không đồng nghĩa với việc mọi log của request được lưu.

Trong ứng dụng thật, nên để instrumentation/tracing SDK truyền context theo framework và giao thức thay vì tự nối chuỗi header một cách thủ công. Với thread pool, `CompletableFuture` hoặc gọi bất đồng bộ, context phải được truyền qua ranh giới tác vụ; dùng một biến global cho `trace_id` như ví dụ một request ở trên sẽ **không an toàn** nếu nhiều request chạy đồng thời. Context dạng request scope và công cụ hỗ trợ propagation giúp tránh trộn dữ liệu giữa người dùng.

`request_id` riêng của hệ thống có thể hữu ích để tìm log; nó **không nhất thiết** bằng `trace_id` của tracing. Nếu sử dụng cả hai, định nghĩa rõ phạm vi và cách ánh xạ.

## 8. Khi nào dùng log, trace, hoặc cả hai?

| Nhu cầu | Nên ưu tiên | Vì sao |
| --- | --- | --- |
| Biết tại sao dữ liệu đầu vào bị từ chối | Log có lý do kiểm tra hợp lệ | Chi tiết nghiệp vụ thường nằm ở thông điệp sự kiện |
| Tìm vị trí gây chậm giữa nhiều dịch vụ | Trace với duration của các span | Thấy được chuỗi gọi và độ trễ từng bước |
| Chẩn đoán exception trong một class Java | Log exception và stack trace | Có loại lỗi, method, vị trí mã |
| Một request đôi khi timeout nhưng khó tái hiện | Log có trace ID kết hợp trace | Theo được đường đi và đọc thông điệp ở span liên quan |
| Kiểm tra trình tự startup, shutdown, reload cấu hình | Log | Thường là sự kiện vòng đời, chưa gắn với HTTP trace |
| Hiểu quan hệ gọi cha–con của các service | Distributed trace | Có context và span hierarchy |
| Thống kê tỷ lệ lỗi hoặc độ trễ toàn hệ thống | Metrics, có thể kết hợp log và trace | Tránh quét toàn bộ log/trace cho mọi phép tổng hợp |

**Ví dụ hướng điều tra:**

Giả sử API trả HTTP 500. Trước tiên tìm log lỗi bằng thời điểm, service, request ID hoặc trace ID. Nếu có trace tương ứng, mở trace để thấy bước nào thất bại/chiếm thời gian. Từ span lỗi, dùng `trace_id` và `span_id` truy vấn log để đọc chi tiết exception. Kiểm tra mã nguồn, cấu hình và backend thực tế trước khi kết luận nguyên nhân. Một span được đánh dấu lỗi cho biết **nơi phát hiện lỗi trong luồng quan sát**, không tự chứng minh lỗi gốc bắt đầu ở span đó.

Đối với hệ thống nhỏ hoặc chương trình batch không gọi dịch vụ ngoài, logging có thể đã đủ cho nhiều bài toán. Tracing có giá trị rõ nhất khi cần quan sát **quan hệ giữa các thao tác**, sự phân tán giữa service hoặc việc chẩn đoán latency phức tạp.

## 9. Chi phí, sampling và quyền riêng tư

**Logging:**
- Level (INFO, WARNING, FINE...) giúp điều chỉnh độ chi tiết và dung lượng.
- Cần rotation, retention, quyền đọc file hoặc chính sách lưu trên nền tảng log.
- Ghi quá nhiều log trong đường xử lý nóng có thể tăng I/O, chi phí và làm loãng tín hiệu quan trọng.

**Tracing:**
- Mỗi request có thể sinh nhiều span; số span và attributes quyết định lượng dữ liệu thu thập.
- **Sampling** chỉ ghi hoặc xuất một phần trace để kiểm soát chi phí; tùy cách triển khai, trace của request cụ thể có thể không tồn tại trong backend dù ứng dụng vẫn chạy và vẫn có log.
- Sampling phải được phối hợp với nhu cầu tìm lỗi hiếm: nếu mẫu quá ít, trace quan trọng có thể không được thu thập. Kết luận “không có trace” **không đồng nghĩa** “không có request”.

**Cả hai:** không ghi token, mật khẩu, API key, số thẻ hoặc nội dung nhạy cảm. Cẩn thận với URL query string, request/response body, user ID và các span attributes có cardinality cao. Đặt giới hạn dung lượng, thời hạn lưu, quyền truy cập và cơ chế che dữ liệu trước khi đưa log/trace vào hệ thống tập trung.

## 10. Những sai lầm thường gặp

1. **Nhầm `logger.trace()` với distributed tracing:** đây chỉ là một mức ghi log. Muốn có span, cần instrumentation/tracing API thực sự.
2. **Nhầm stack trace với distributed trace:** stack trace mô tả call stack tại một điểm lỗi; distributed trace nối thao tác xuyên ranh giới hàm, tiến trình hoặc dịch vụ.
3. **Cho rằng mọi log có cùng trace ID đều là cùng một span:** trong một trace có thể có nhiều span ID; dùng cả hai trường để xác định đúng ngữ cảnh.
4. **Tạo trace ID mới ở mỗi service:** làm đứt mối liên kết liên dịch vụ. Cần nhận và truyền context; span ID mới dành cho span mới.
5. **Tự dùng biến static/global giữ context cho mọi request:** request đồng thời có thể ghi nhầm trace ID. Dùng request-scoped context được propagation đúng qua các tác vụ.
6. **Lấy thời gian của span con cộng lại để ra thời gian request:** span có thể lồng nhau hoặc chạy song song, gây đếm trùng. Cần xem waterfall/timeline và quan hệ dependency.
7. **Không thấy trace thì cho rằng không có request:** sampling, exporter lỗi hoặc backend retention có thể khiến trace không được lưu.
8. **Log chỉ có message mà thiếu correlation ID:** trong môi trường nhiều request, việc tìm log tương ứng với một span sẽ khó hơn đáng kể.
9. **Ghi exception nhưng formatter loại bỏ Throwable:** sẽ mất stack trace có ích; kiểm tra backend/formatter log.
10. **Thu thập mọi chi tiết mãi mãi:** dữ liệu log/trace quá lớn, tốn chi phí và làm tăng rủi ro lộ thông tin.

## 11. Tự kiểm tra hiểu biết

**Tình huống A:** Trong Logback, lập trình viên bật mức `TRACE` nhưng không có trace nào trong Jaeger. Vì sao?  
Vì mức TRACE chỉ điều khiển log record. Cần instrumentation, exporter và pipeline tracing để có distributed trace.

**Tình huống B:** Một trace có span `HTTP POST /checkout` kéo dài 400 ms và span `callPayment` kéo dài 350 ms. Điều này gợi ý gì?  
`callPayment` là bước chiếm phần lớn khoảng thời gian quan sát trong trace; cần xem timeline, spans liên quan và log lỗi để tìm nguyên nhân, chưa thể chỉ từ hai con số mà khẳng định dependency thanh toán có lỗi.

**Tình huống C:** Hai request chạy đồng thời tạo log đan xen trong một file. Làm sao theo dõi đúng một request?  
Gắn trường định danh tương quan (ưu tiên `trace_id` và `span_id` khi đã có tracing), rồi lọc log theo ID của request/span cần điều tra.

**Tình huống D:** Có log `NumberFormatException` và nhiều frame `at ...`. Đó có phải distributed trace?  
Không. Đó là stack trace của exception Java; nó chỉ giúp xác định call stack tại điểm lỗi.

**Ghi nhớ:** **Log mô tả sự kiện; trace mô tả quan hệ và thời lượng các thao tác trong một luồng xử lý**. Mức log TRACE và exception stack trace là hai khái niệm khác. Trong Java, phối hợp log có correlation ID với tracing đúng chuẩn giúp đi từ “điều gì xảy ra” đến “nó xảy ra ở bước nào và vì sao”.
