# Span ID trong Trace Context (Java Core Logging)

## 1. Span ID dùng để làm gì?

Trong một ứng dụng Java, một yêu cầu HTTP có thể đi qua controller, service, truy vấn cơ sở dữ liệu và các lời gọi sang dịch vụ khác. Nếu chỉ xem từng dòng log riêng lẻ, rất khó xác định thao tác nào thuộc cùng một yêu cầu. **Distributed tracing** mô hình hóa quá trình xử lý bằng các **trace** và **span**:

- **Trace** biểu diễn toàn bộ chuỗi công việc có liên quan; các span trong cùng trace dùng chung một **Trace ID**.
- **Span** biểu diễn một đơn vị công việc có điểm bắt đầu/kết thúc, chẳng hạn xử lý HTTP hoặc truy vấn SQL.
- **Span ID** định danh một span cụ thể trong trace. Khi đi vào một span con, Span ID thay đổi, còn Trace ID thường được giữ nguyên.
- **Parent Span ID** (nếu có) là Span ID của span cha. Nhờ quan hệ cha–con, hệ thống tracing dựng được cây lời gọi.

Ví dụ một yêu cầu tạo ba span:

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
└─ Gateway:       spanId=00f067aa0ba902b7   (root trong ví dụ)
   └─ OrderService: spanId=a3ce929d0e0e4736, parent=00f067aa0ba902b7
      └─ DB query:   spanId=b9c7c989f97918e1, parent=a3ce929d0e0e4736
~~~

Ba thao tác cùng thuộc một trace nhưng có ba Span ID khác nhau. Một dòng log gắn với span `DB query` có thể mang `traceId=4bf...` và `spanId=b9c...`, giúp tìm đúng đoạn xử lý thay vì chỉ biết toàn bộ yêu cầu.

## 2. Phân biệt Trace ID, Span ID và Parent Span ID

| Thuộc tính | Ý nghĩa | Phạm vi sử dụng |
| --- | --- | --- |
| Trace ID | Nhận diện toàn bộ trace | Giữ nguyên khi trace đi qua các span/dịch vụ liên quan |
| Span ID | Nhận diện **span hiện tại** | Một giá trị mới cho mỗi span mới |
| Parent Span ID | Chỉ ra span cha trực tiếp | Vắng mặt ở root span; giúp dựng quan hệ cha–con |
| Request ID / Correlation ID | Mã tương quan do ứng dụng hoặc hạ tầng quy định | Có thể hữu ích cho logging, nhưng không tự động thay thế Trace ID hoặc Span ID |

Trong ngữ cảnh W3C Trace Context, **Trace ID** là 16 byte (32 ký tự hex), còn **Span ID** là 8 byte (16 ký tự hex). Giá trị hex thường được biểu diễn bằng chữ thường; định danh toàn số 0 là không hợp lệ. Span ID cần có khả năng tránh trùng lặp trong trace; khi dùng tracing thật, hãy để SDK tạo ID phù hợp thay vì đặt cố định, tăng tuần tự hoặc suy ra từ dữ liệu người dùng.

Một span có thể ghi nhiều dòng log với **cùng Span ID**: ID chỉ thay đổi khi chuyển sang ngữ cảnh của một span khác, không phải mỗi lần gọi hàm log. Span ID cũng không phải Java thread ID: nhiều span có thể chạy lần lượt trên một thread và một span có thể cần mang ngữ cảnh qua các thread.

## 3. Span ID được truyền giữa các dịch vụ như thế nào?

W3C Trace Context quy định HTTP header `traceparent` theo dạng:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
~~~

Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- `00`: phiên bản định dạng header.
- `4bf92f3577b34da6a3ce929d0e0e4736`: Trace ID.
- `00f067aa0ba902b7`: **Span ID của phía gửi**; trường này được gọi là `parent-id` vì phía nhận sẽ dùng nó làm ID của span cha.
- `01`: cờ trace, trong đó bit sampling được bật.

Khi OrderService nhận header trên, một tracing SDK có thể tạo **server span mới** với Span ID `a3ce929d0e0e4736`, giữ Trace ID và liên kết parent tới `00f067aa0ba902b7`. Nếu OrderService gọi một dịch vụ downstream trong ngữ cảnh server span đó, header `traceparent` gửi đi chứa **Span ID hiện tại của OrderService**, không gửi lại ID của Gateway:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-a3ce929d0e0e4736-01
~~~

Không nên hiểu trường `parent-id` trong header là “Span ID của span hiện tại ở phía nhận”: phía nhận phải tạo hoặc chọn span của chính mình theo cách instrumentation vận hành. Header `tracestate` có thể bổ sung ngữ cảnh tracing theo nhà cung cấp, nhưng không thay thế `traceparent`. Sampling flag giúp trao đổi quyết định lấy mẫu; việc log có xuất hiện hoặc span có được export hay không còn phụ thuộc cấu hình logging/tracing.

## 4. Ví dụ Java 17 chạy độc lập: log theo span hiện tại

Ví dụ sau mô phỏng yêu cầu từ Gateway sang OrderService, rồi OrderService mở span con cho truy vấn DB. Nó dùng `ThreadLocal` để minh họa ngữ cảnh trong **cùng một thread**. Các ID cố định chỉ để kết quả dễ kiểm chứng; đây **không phải** tracer hay bộ sinh Span ID dùng trong production.

Tạo tệp `SpanIdDemo.java`:

~~~java
public class SpanIdDemo {
    private record SpanContext(
            String traceId, String spanId, String parentSpanId) {
    }

    private static final ThreadLocal<SpanContext> CURRENT = new ThreadLocal<>();

    private static void log(String message) {
        SpanContext current = CURRENT.get();
        System.out.printf(
                "traceId=%s spanId=%s parentSpanId=%s | %s%n",
                current.traceId(),
                current.spanId(),
                current.parentSpanId() == null ? "-" : current.parentSpanId(),
                message);
    }

    public static void main(String[] args) {
        // Span của OrderService: cùng trace, parent là Gateway.
        SpanContext server = new SpanContext(
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "a3ce929d0e0e4736",
                "00f067aa0ba902b7");

        CURRENT.set(server);
        try {
            log("HTTP GET /orders");

            // Span con dùng traceId cũ nhưng có spanId và parent mới.
            SpanContext dbQuery = new SpanContext(
                    server.traceId(),
                    "b9c7c989f97918e1",
                    server.spanId());

            CURRENT.set(dbQuery);
            try {
                log("SELECT orders");
            } finally {
                CURRENT.set(server); // Khôi phục context của span cha.
            }

            log("HTTP 200");
        } finally {
            CURRENT.remove(); // Không rò rỉ context sang tác vụ kế tiếp.
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SpanIdDemo.java
java SpanIdDemo
~~~

Stdout chính xác:

~~~text
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=a3ce929d0e0e4736 parentSpanId=00f067aa0ba902b7 | HTTP GET /orders
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=b9c7c989f97918e1 parentSpanId=a3ce929d0e0e4736 | SELECT orders
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=a3ce929d0e0e4736 parentSpanId=00f067aa0ba902b7 | HTTP 200
~~~

**Điểm cần quan sát:** dòng log truy vấn DB có Span ID riêng và trỏ về span của OrderService. Dòng HTTP 200 quay lại Span ID của OrderService sau khi khôi phục context. Ví dụ chỉ quản lý ngữ cảnh phục vụ logging; muốn có biểu đồ trace, thời lượng span, sự kiện và export sang backend cần dùng instrumentation/tracing SDK thực sự.

## 5. Lấy Span ID trong ứng dụng Java thực tế

Với ứng dụng đã tích hợp **OpenTelemetry API/SDK** hoặc Java agent và có span hợp lệ đang active, có thể đọc ngữ cảnh như sau. Đây là **đoạn mã tích hợp**, không phải chương trình Java độc lập như ví dụ ở mục 4; project phải có dependency và cấu hình OpenTelemetry phù hợp.

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

SpanContext context = Span.current().getSpanContext();
if (context.isValid()) {
    String traceId = context.getTraceId();
    String spanId = context.getSpanId();
    // Đưa hai ID vào structured log hoặc logging context đang dùng.
}
~~~

`Span.current()` lấy span từ **context đang active**, nên gọi nó ngoài span hợp lệ có thể trả về context không hợp lệ. Kiểm tra `isValid()` trước khi sử dụng ID. Tracing SDK/instrumentation thường chịu trách nhiệm tạo span, gắn quan hệ cha–con và kết thúc span; log chỉ đọc thông tin đang được gắn với quá trình thực thi.

Với **SLF4J + Logback**, có thể đưa `trace_id` và `span_id` vào MDC (Mapped Diagnostic Context) để log pattern hoặc JSON encoder xuất chúng cùng message. Ví dụ mẫu pattern `%X{trace_id}` và `%X{span_id}` **chỉ có giá trị khi integration đã thực sự ghi hai khóa đó vào MDC**; tên khóa phụ thuộc thư viện/cấu hình. Không mặc định rằng chỉ thêm pattern là OpenTelemetry sẽ tự hoạt động.

Khi dùng thread pool, `CompletableFuture`, reactive pipeline hoặc coroutine/fiber tương đương, ngữ cảnh có thể không tự chuyển theo luồng thực thi. Cần cơ chế propagation của framework/instrumentation; không truyền ngầm `ThreadLocal` sang thread khác, và luôn khôi phục/dọn logging context tại ranh giới tác vụ để tránh gắn nhầm Span ID của request trước.

## 6. Các lỗi thường gặp khi đọc log theo Span ID

1. **Nhầm Trace ID với Span ID.** Một trace có nhiều span; chỉ lọc theo Trace ID cho toàn bộ hành trình, sau đó dùng Span ID để khoanh vùng một thao tác.
2. **Sinh Span ID cho từng dòng log.** Các log trong cùng một span phải giữ Span ID hiện tại; tạo ID mới khi tạo span mới, không phải khi in log.
3. **Gán cùng một Span ID cho nhiều span khác nhau.** Điều này phá quan hệ truy vết. Hãy dùng bộ sinh ID của SDK và bảo đảm mỗi span mới nhận ID riêng.
4. **Không propagate context khi gọi dịch vụ khác.** Trace ID thay đổi hoặc parent bị đứt khiến cây trace không liên tục. Kiểm tra việc inject/extract `traceparent` qua HTTP/messaging.
5. **Mất hoặc rò ngữ cảnh khi đổi thread.** Log thiếu ID hoặc ghi ID của request khác. Kiểm tra context propagation và các khối `finally`/scope đóng đúng.
6. **Coi Span ID trong log là bằng chứng có trace trong backend.** Log có thể chỉ chứa mã tương quan, trong khi span không được tạo/export, sampling loại bỏ hoặc exporter gặp lỗi. Cần kiểm tra telemetry pipeline riêng.
7. **Tin vào `traceparent` không hợp lệ.** Khi tự xử lý protocol, cần tuân thủ kiểm tra độ dài, hex và quy tắc ID khác 0; tốt nhất để instrumentation chuẩn xử lý. Không đặt thông tin nhạy cảm, mã người dùng hay token vào ID.

## 7. Cách tự kiểm tra khi điều tra một request

Giả sử ba log có cùng Trace ID; hai log đầu có `spanId=A`, log thứ ba có `spanId=B` và `parentSpanId=A`. Kết luận hợp lý là log thứ ba thuộc **span con của A**, không phải một trace độc lập. Nếu Trace ID khác, chúng không thuộc cùng trace theo các định danh đang quan sát, dù request URL hoặc thời gian tương tự nhau.

Khi log có Span ID nhưng không thấy span trên giao diện tracing, lần lượt kiểm tra: span có được tạo và kết thúc chưa, exporter có gửi thành công không, sampling có lưu trace đó không, và log đang đọc có lấy đúng active context không. Cách này giúp phân biệt lỗi **logging correlation** với lỗi **trace collection**.

**Ghi nhớ:** Trace ID trả lời “toàn bộ hành trình nào?”, Span ID trả lời “đang ở thao tác nào?”, còn Parent Span ID trả lời “thao tác này do span nào gọi?”. Ba khái niệm kết hợp giúp đọc log theo đúng cấu trúc của một distributed trace.