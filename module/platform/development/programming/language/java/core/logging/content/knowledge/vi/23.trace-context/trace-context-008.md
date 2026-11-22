# Trace context không đầy đủ trong Java Core Logging

## Mục tiêu

Sau bài này, bạn có thể nhận biết một bản ghi log đang thiếu thông tin liên kết với trace, phân biệt sự cố ở tầng logging và tầng distributed tracing, tìm đúng điểm làm rơi ngữ cảnh khi xử lý bất đồng bộ, và sửa bằng cách truyền, kích hoạt, phục hồi ngữ cảnh theo vòng đời của tác vụ. Ví dụ chính dùng Java 17 và thư viện chuẩn để quan sát lỗi một cách độc lập; các đoạn tích hợp MDC/OpenTelemetry được ghi rõ là mã minh họa cho ứng dụng có thư viện tương ứng.

## 1. “Không đầy đủ” nghĩa là gì?

**Trace context** là thông tin dùng để liên hệ các thao tác thuộc cùng một yêu cầu hoặc luồng công việc. Một hệ thống có distributed tracing thường có những trường sau:

| Trường | Ý nghĩa | Khi nào cần |
| --- | --- | --- |
| **traceId** | Định danh chung cho toàn bộ trace; các span liên quan giữ cùng trace ID. | Cần khi muốn nối log với trace hoặc theo dõi một yêu cầu qua nhiều dịch vụ. |
| **spanId** | Định danh của span hiện hành. | Cần khi log phải gắn với một thao tác/span cụ thể. Span con có span ID mới. |
| **parent span** | Quan hệ cha–con giữa các span, thường nằm trong dữ liệu span thay vì mọi dòng log. | Cần để dựng đúng cây trace. Không nhất thiết là trường bắt buộc ở từng log. |
| **trace flags / sampling** | Cờ như sampled, phục vụ quyết định ghi nhận/thu thập trace. | Cần khi phân tích vì sao trace không xuất hiện ở backend. |
| **tracestate / baggage** | Metadata liên quan propagation; baggage mang các giá trị ứng dụng được chọn. | Tùy hệ thống, không phải điều kiện để mọi log được xem là đầy đủ. |

Một dòng log có **traceId** nhưng thiếu **spanId** là thiếu tương quan tới span nếu log xảy ra bên trong span đang hoạt động. Một luồng xử lý có traceId hoàn toàn khác ở dịch vụ kế tiếp là dấu hiệu đứt propagation. Ngược lại, log khi khởi động JVM, trong tác vụ nền độc lập hoặc trước khi tạo span có thể hợp lệ mà không có traceId/spanId.

Phân biệt ba thứ:

- **Trace context đang hoạt động**: ngữ cảnh được thư viện tracing giữ cho đơn vị thực thi hiện tại; dùng để tạo span con và inject context vào yêu cầu gửi đi.
- **MDC (Mapped Diagnostic Context)**: bản đồ khóa–giá trị mà framework logging như SLF4J/Logback dùng để thêm trường vào log của luồng đang chạy. MDC không tự tạo distributed trace.
- **Request/correlation ID**: ID riêng của ứng dụng để tìm log cùng yêu cầu; hữu ích nhưng không thay cho traceId/spanId hoặc quan hệ span cha–con.

Một hệ thống có thể truyền trace context đúng nhưng cấu hình formatter không đưa traceId vào log. Ngược lại, có thể sao chép đúng MDC sang luồng khác nhưng không kích hoạt tracing context; khi đó log trông có traceId còn span mới hoặc lời gọi HTTP tiếp theo vẫn mất liên kết.

## 2. Dấu hiệu và tác động

Ví dụ một yêu cầu đi qua API, tác vụ chạy trong thread pool và dịch vụ thanh toán:

~~~text
API            traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
async worker   traceId=-                                spanId=-
payment HTTP   traceId=a12c...                          spanId=...
~~~

Dòng thứ hai mất thông tin trong log; dòng cuối minh họa dịch vụ downstream bắt đầu trace khác (giá trị rút gọn chỉ để minh họa, không phải trace ID hợp lệ để truyền qua mạng). Cả hai có thể khiến việc lần theo một request bị gián đoạn, nhưng phải kiểm tra riêng từng ranh giới mới biết có mất tracing context thật hay chỉ mất trường log.

Các biểu hiện thường gặp:

1. Log trong controller có traceId, nhưng log trong **ExecutorService**, **CompletableFuture**, callback, listener hoặc scheduler lại thiếu.
2. Trên cùng một request, các dòng log có traceId khác nhau hoặc có spanId không khớp span đang hoạt động.
3. Backend tracing hiển thị nhiều root span rời rạc thay vì một trace có quan hệ cha–con.
4. Span vẫn được ghi nhận nhưng log JSON không có trường tương quan; hoặc trường đã xuất hiện ở stdout nhưng mất trong pipeline thu thập.
5. Thread pool giữ lại traceId của request trước: đây là **rò rỉ context**, nguy hiểm hơn một giá trị trống vì nó liên kết nhầm log giữa các request.

Không kết luận “propagation hỏng” chỉ từ việc tìm traceId không thấy ở giao diện quan sát: trace có thể không được sample/export, timestamp có thể lệch, hoặc pipeline log có thể đổi tên/lọc trường.

## 3. Vì sao trace context bị thiếu?

| Điểm chuyển tiếp | Cơ chế gây thiếu | Cách xác minh |
| --- | --- | --- |
| **HTTP vào / message consumer** | Không extract header/metadata, header không hợp lệ hoặc middleware tracing không chạy. | Quan sát header hợp lệ ở ranh giới nhận, đối chiếu trace/span đang hoạt động ngay sau bước extract. |
| **Bắt đầu xử lý yêu cầu** | Tạo span nhưng không đặt context thành active, hoặc đóng scope trước khi log/chạy tác vụ. | Kiểm tra thời điểm tạo/kích hoạt/đóng span so với thời điểm ghi log. |
| **Đưa dữ liệu vào log** | MDC chưa được ánh xạ từ span hiện hành; logger pattern/JSON encoder không xuất trace_id hoặc span_id. | So sánh span đang active, MDC tại điểm log và payload log cuối cùng. |
| **Thread pool / async** | ThreadLocal hoặc MDC chỉ gắn với luồng hiện tại; task chạy trên luồng đã được tái sử dụng, không kế thừa context. | So sánh context tại lúc submit task và khi task thực sự chạy. |
| **HTTP ra / message producer** | Không inject trace context vào carrier, dùng propagator khác hoặc mất context trước lúc gửi. | Kiểm tra header/metadata thực sự được gửi và việc extract ở phía nhận. |
| **Collector / log pipeline** | Parser, transform hoặc mapping bỏ trường; log và trace bị lọc/sampling theo chính sách khác nhau. | Kiểm tra log thô tại ứng dụng, dữ liệu vào collector và bản ghi được index. |

Với truyền thông HTTP theo W3C Trace Context, header **traceparent** dạng thông dụng là:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các phần lần lượt là version, **trace-id** 32 chữ số hex, **parent-id** 16 chữ số hex và **trace-flags** hai chữ số hex. Trace ID/span ID hợp lệ không được toàn số 0; cờ **01** ở ví dụ biểu thị bit sampled được bật. Giá trị parent-id bên gửi là span ID của phía gửi; phía nhận có thể tạo span con với **spanId mới**, nhưng giữ cùng traceId và quan hệ cha–con. **tracestate** và **baggage** là các header bổ sung tùy trường hợp; thiếu chúng không mặc nhiên có nghĩa trace context bị hỏng.

Không nên tự ghép hoặc tự tin tưởng mọi giá trị header từ bên ngoài. Hãy dùng propagator tương thích với hệ tracing để extract/inject và áp dụng giới hạn kích thước, độ tin cậy cho dữ liệu đi kèm.

## 4. Ví dụ Java 17: mất ngữ cảnh khi chuyển sang thread pool

Ví dụ sau mô phỏng các trường tương quan của log bằng **ThreadLocal<Map>**. Nó **không tạo span OpenTelemetry** và **không truyền W3C traceparent**; mục đích là nhìn rõ nguyên nhân MDC/ThreadLocal biến mất khi task chạy ở luồng khác. Chương trình chạy độc lập, không cần dependency ngoài JDK.

Lưu thành **TraceContextDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TraceContextDemo {
    private static final ThreadLocal<Map<String, String>> CONTEXT =
            ThreadLocal.withInitial(HashMap::new);

    private static Runnable captureContext(Runnable task) {
        // Chụp một bản sao tại thời điểm gửi task.
        Map<String, String> captured = Map.copyOf(CONTEXT.get());

        return () -> {
            // Giữ context trước đó của luồng worker để phục hồi sau task.
            Map<String, String> previous = CONTEXT.get();
            CONTEXT.set(new HashMap<>(captured));
            try {
                task.run();
            } finally {
                if (previous.isEmpty()) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(previous);
                }
            }
        };
    }

    private static void log(String stage) {
        Map<String, String> data = CONTEXT.get();
        System.out.printf(
                "%s: traceId=%s spanId=%s%n",
                stage,
                data.getOrDefault("traceId", "-"),
                data.getOrDefault("spanId", "-")
        );
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CONTEXT.get().put(
                    "traceId", "4bf92f3577b34da6a3ce929d0e0e4736");
            CONTEXT.get().put("spanId", "00f067aa0ba902b7");

            pool.submit(() -> log("withoutPropagation")).get();
            pool.submit(captureContext(() -> log("withPropagation"))).get();
            pool.submit(() -> log("afterTask")).get();
        } finally {
            CONTEXT.remove();
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TraceContextDemo.java
java TraceContextDemo
~~~

Kết quả chuẩn:

~~~text
withoutPropagation: traceId=- spanId=-
withPropagation: traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
afterTask: traceId=- spanId=-
~~~

Giải thích:

- **withoutPropagation**: luồng main có dữ liệu, nhưng worker của pool có ThreadLocal riêng nên không thấy dữ liệu của main.
- **withPropagation**: hàm **captureContext** lấy snapshot ở thời điểm submit, đặt snapshot lên worker trong thời gian chạy task, rồi phục hồi context cũ ở **finally**, kể cả khi task ném exception.
- **afterTask**: worker không giữ dữ liệu của task trước. Điều này đặc biệt quan trọng vì pool tái sử dụng luồng cho nhiều request.

Đây là ví dụ về **ngữ cảnh log**. Khi ứng dụng thực sự tạo span cho công việc bất đồng bộ, span mới cần **spanId riêng** và tham chiếu đến span cha phù hợp. Việc chỉ sao chép hai chuỗi traceId/spanId trong ví dụ không thực hiện bước đó.

Lưu ý: **InheritableThreadLocal** không phải giải pháp tổng quát cho thread pool, vì worker thường được tạo từ trước rồi tái sử dụng; kế thừa lúc tạo thread không tương đương propagation theo từng task. Truyền ngữ cảnh lúc submit/chuyển giao tác vụ và dọn dẹp lúc kết thúc là cách kiểm soát đúng ranh giới.

## 5. Áp dụng vào logger và tracer thực tế

### 5.1. Với SLF4J MDC

MDC gắn với cơ chế logging của ứng dụng. Với một tác vụ chạy trong executor, bạn có thể chụp MDC ở nơi submit và đặt/khôi phục MDC quanh task:

~~~java
// Mã minh họa: ứng dụng đã có SLF4J, executor và task.
Map<String, String> capturedMdc = MDC.getCopyOfContextMap();

Runnable wrapped = () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (capturedMdc == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(capturedMdc);
        }
        task.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
};
executor.execute(wrapped);
~~~

Đoạn này cần **org.slf4j.MDC**, **java.util.Map** và biến **executor/task** do ứng dụng cung cấp; nó không phải tệp Java độc lập. Đừng thay mã này cho framework đã tự propagation MDC/tracing nếu không biết cơ chế hiện hành, vì có thể tạo context chồng chéo hoặc ghi đè context hợp lệ.

MDC chỉ quyết định trường nào được đưa vào log. Nếu muốn trace xuyên dịch vụ, ứng dụng còn cần tracer, propagator và span context phù hợp. Tên khóa MDC (**trace_id**, **span_id**, **traceId**, **spanId**...) phải thống nhất với layout/encoder và truy vấn ở backend. Kiểm tra trường **ở log phát ra thực tế**, không chỉ kiểm tra MDC có giá trị trong debugger.

### 5.2. Với OpenTelemetry Context

Trong ứng dụng đã cấu hình OpenTelemetry Java, có thể bao một **Runnable** bằng context hiện hành trước khi chuyển cho executor:

~~~java
// Mã minh họa: có OpenTelemetry Context API và executor/task.
Runnable wrapped = io.opentelemetry.context.Context.current().wrap(task);
executor.execute(wrapped);
~~~

Bản wrapper giúp kích hoạt context đã capture trong lúc task chạy và khôi phục scope sau đó. Để log có traceId/spanId, cần thêm cấu hình **log correlation/MDC bridge** hoặc instrumentation tương ứng; **Context.wrap** tự nó không bảo đảm encoder sẽ in các trường. Với HTTP client/server hoặc message broker, dùng instrumentation/propagator để **extract ở phía nhận** và **inject ở phía gửi**, rồi tạo span con theo quy tắc tracing.

Nếu dùng **CompletableFuture.supplyAsync**, **thenApplyAsync** hoặc callback chuyển sang executor khác, kiểm tra từng ranh giới asynchronous. Context ở luồng gọi không tự xuất hiện ở mọi callback. Với framework reactive, hãy dùng cơ chế propagation của framework/instrumentation tương ứng; tránh dựa hoàn toàn vào ThreadLocal khi một tác vụ có thể đổi luồng.

### 5.3. Vòng đời đúng của context

~~~text
Nhận request/message
    → extract remote trace context (nếu có và hợp lệ)
    → tạo/kích hoạt span hiện hành
    → ánh xạ trace/span ID vào log nếu cần
    → capture context khi chuyển qua ranh giới async
    → kích hoạt tạm trong callback/worker, tạo span con khi phù hợp
    → inject context khi gọi dịch vụ hoặc phát message
    → đóng scope, phục hồi context cũ và dọn MDC
~~~

Dùng **try/finally** hoặc scope tự đóng để tránh rò rỉ. Với request mới không có upstream trace context, tracer có thể chủ động khởi tạo root trace mới; đó không phải lỗi. Với dữ liệu từ hệ thống không tin cậy, không cho phép baggage tùy ý trở thành trường log chứa token, mật khẩu hoặc thông tin nhạy cảm.

## 6. Chẩn đoán có hệ thống

Khi thấy log không có traceId hoặc spanId, thực hiện theo thứ tự sau để khoanh vùng lỗi:

1. **Đặt kỳ vọng đúng**: log có thực sự nằm trong một thao tác được trace không? Nếu là startup/scheduler độc lập, việc thiếu ID có thể bình thường.
2. **Kiểm tra tại nguồn**: tại chỗ ghi log, span context đang active và hợp lệ không? Nếu có mà log thiếu trường, tập trung vào bridge MDC/encoder.
3. **So sánh trước và sau async**: in hoặc kiểm tra ID ngay trước submit và bên trong Runnable/callback. Mất ID chỉ sau ranh giới này thường là lỗi propagation.
4. **Kiểm tra đầu mạng**: ở HTTP/message inbound, xác minh extract context; ở outbound, xác minh header/metadata đã inject. Đối chiếu traceId hai phía và span parent.
5. **Phân biệt propagation với sampling/export**: log có traceId không có nghĩa mọi span đều được thu thập; trace không hiển thị ở backend chưa đủ chứng minh propagation sai.
6. **Kiểm tra đường đi của log**: đối chiếu nội dung console/file → agent/collector → parsed fields → chỉ mục tìm kiếm/dashboard. Trường có thể bị đổi tên, loại bỏ hoặc sai kiểu.
7. **Kiểm tra rò rỉ**: sau task lỗi, cancel hoặc kết thúc request, chạy task độc lập trên cùng pool; nó không được mang traceId của request trước.

Một bảng kiểm thử hữu ích:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Log đồng bộ bên trong span | Có traceId hợp lệ và spanId của span hiện hành, nếu log correlation được bật. |
| Task trong executor được propagate | Cùng traceId với tác vụ cha; spanId phụ thuộc span đang active trong worker. |
| Task trong executor không được propagate | Thể hiện thiếu context như trường hợp lỗi của ví dụ; test phát hiện được khoảng trống này. |
| HTTP qua hai dịch vụ đã instrument | Giữ traceId; span phía nhận liên kết đúng parent, thường có spanId mới. |
| Root task độc lập không có remote parent | Có thể tạo trace mới hoặc không tạo trace, tùy cấu hình. |
| Task kế tiếp trên thread pool sau khi task trước hoàn tất | Không có dữ liệu MDC/ThreadLocal bị rò từ task trước. |
| Exception trong callback | Scope/MDC được phục hồi ở finally; trace lỗi vẫn liên kết nếu context còn hiệu lực. |
| Trace không được sample hoặc exporter lỗi | Có thể vẫn xuất ID trong log, nhưng span không nhất thiết có trong backend. |

Khi viết test, dùng ID cố định hợp lệ hoặc ID do tracer tạo, không dùng giá trị rút gọn kiểu “abc...” để kiểm tra validator W3C. Đối chiếu ID và quan hệ thực tế, không chỉ so chuỗi log có chứa từ “traceId”.

## 7. Những cách sửa dễ sai

- **Chỉ thêm traceId giả nếu thiếu**: khiến log trông đầy đủ nhưng không nối được trace hoặc dẫn tới nhầm request. Nên sửa nguồn tạo/propagate context.
- **Chỉ copy MDC rồi cho rằng distributed tracing đã được sửa**: MDC không tạo span, không inject header và không đảm bảo quan hệ cha–con.
- **Chỉ truyền ThreadLocal bằng InheritableThreadLocal**: không giải quyết đúng tái sử dụng worker và callback bất đồng bộ.
- **Không phục hồi context cũ trong finally**: làm rò traceId giữa các request trên pool, đặc biệt khi có exception.
- **Dùng cùng một spanId cho mọi thao tác**: làm mất ý nghĩa phân rã span; span con phải có ID riêng và parent phù hợp.
- **Suy ra lỗi propagation từ trace không xuất hiện trên UI**: cần loại trừ sampling, export và ingestion.
- **Log nguyên header/baggage không chọn lọc**: có thể phát tán dữ liệu nhạy cảm, tăng dung lượng log và khó kiểm soát cardinality.

## 8. Ghi nhớ

Một trace context được xem là “đủ” khi có **đúng các thông tin cần cho thao tác đang trace**, sống qua đúng các ranh giới xử lý và được ghi/hiển thị nhất quán. Muốn sửa lỗi, xác định nó rơi ở bước **extract → activate → async propagate → log correlation → inject → export/ingest**. Trong Java, ThreadLocal/MDC gắn với luồng nên cần capture, activate và restore theo từng task. Trong hệ có tracer, hãy dùng cơ chế propagation và scope của tracer để duy trì trace/span thật; kiểm thử cả việc **giữ context đúng** lẫn **không để context cũ rò sang tác vụ tiếp theo**.