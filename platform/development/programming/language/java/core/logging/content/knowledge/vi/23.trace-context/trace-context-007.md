# Sampling và log trong Trace Context (Java Core Logging)

## 1. Sampling giải quyết vấn đề gì?

Trong hệ thống có nhiều request và nhiều service, mỗi request có thể tạo hàng chục span và hàng trăm dòng log. Ghi và lưu mọi dữ liệu giúp quan sát chi tiết nhưng làm tăng chi phí CPU, truyền tải, lưu trữ, lập chỉ mục và truy vấn. **Sampling (lấy mẫu)** là chính sách chỉ giữ một phần dữ liệu quan sát, theo một tỷ lệ hoặc điều kiện được xác định trước.

Cần tách ba quyết định:

1. **Trace sampling:** trace/span nào được ghi và xuất đến hệ thống distributed tracing.
2. **Log level và log filtering:** sự kiện nào đáng tạo log theo mức `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` và các bộ lọc.
3. **Log sampling:** trong những sự kiện vốn được phép ghi, giữ bao nhiêu dòng (ví dụ 10% log INFO lặp lại của request thành công).

Ba quyết định này **không đồng nhất**. Trace bị bỏ mẫu vẫn có thể có log ERROR; trace được lấy mẫu không có nghĩa mọi dòng DEBUG đều phải xuất hiện. Ngược lại, log chứa `trace_id` không bảo đảm backend đang lưu được trace tương ứng.

Ví dụ: một service xử lý 100.000 request/phút, trung bình mỗi request sinh tám log INFO. Nếu giữ 10% nhóm log INFO theo request, lưu xấp xỉ 80.000 thay vì 800.000 log INFO/phút, trong khi vẫn giữ log lỗi theo chính sách riêng. Con số là kỳ vọng thống kê, không phải giới hạn cứng; chi phí tạo log và khả năng truy vết còn phụ thuộc nơi áp dụng bộ lọc.

## 2. Quan hệ giữa trace context và sampling

Một **trace** mô tả đường đi của một thao tác qua các service. **Span** là một công việc con trong trace. **Trace context** mang thông tin định danh và trạng thái quyết định lấy mẫu xuyên qua các lời gọi đồng bộ hoặc bất đồng bộ.

Các trường thường gặp:

| Trường | Ý nghĩa | Dùng trong log |
| --- | --- | --- |
| `trace_id` | Định danh toàn bộ trace, thường là 32 ký tự hex theo W3C Trace Context | Nối log của các service thuộc cùng request |
| `span_id` | Định danh span hiện tại, thường là 16 ký tự hex | Định vị công việc tạo ra log |
| `trace_flags` | Cờ truyền trong trace context; bit `sampled` biểu thị quyết định lấy mẫu được lan truyền | Có thể giúp giải thích vì sao trace có/không có dữ liệu |
| `request_id` / `correlation_id` | Định danh nghiệp vụ hoặc định danh request do ứng dụng đặt | Bổ trợ khi tracing không sẵn có |

Theo W3C, header sau là một `traceparent` hợp lệ về cấu trúc:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Bốn thành phần lần lượt là phiên bản, `trace-id`, `parent-id` và `trace-flags`. Ở đây `01` bật bit sampled; `00` không bật bit này. Đây là **tín hiệu trong ngữ cảnh**, không phải lời hứa chắc chắn rằng mọi span sẽ có mặt ở kho lưu trữ: exporter, Collector hoặc backend vẫn có thể lọc, từ chối hay làm mất dữ liệu.

Một quy trình chuẩn là: nhận request → trích xuất trace context từ header → chọn sampler phù hợp, tôn trọng parent khi cần → thực thi công việc, lan truyền context qua các tác vụ → ghi log với `trace_id`/`span_id` hợp lệ → xuất traces và logs qua pipeline riêng. Không đặt quyết định ghi mọi log dựa duy nhất vào `trace_flags.sampled`.

## 3. Các chiến lược lấy mẫu trace

| Chiến lược | Ra quyết định ở đâu/khi nào | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Head sampling** | Khi bắt đầu trace hoặc span tại SDK/ingress | Quyết định sớm, giảm lượng span phải ghi/xuất | Không biết trước request nào sẽ lỗi hoặc chậm; có thể bỏ sót trace quan trọng |
| **Parent-based head sampling** | Kế thừa quyết định parent, dùng chính sách gốc cho trace mới | Hạn chế tình trạng các service quyết định không nhất quán trong cùng trace | Phụ thuộc việc truyền context đúng; downstream khó tự phục hồi phần đã bị upstream bỏ |
| **Trace ID ratio-based** | Dùng phép phân phối ổn định trên trace ID để giữ một tỷ lệ, ví dụ 10% | Quyết định nhất quán hơn so với tung đồng xu riêng ở từng span | Tỷ lệ thống kê; không ưu tiên lỗi nếu chỉ chọn theo ID |
| **Tail sampling** | Sau khi Collector/bộ xử lý đã quan sát đủ span, trạng thái hoặc thời gian | Có thể ưu tiên trace lỗi, chậm, đường đi hiếm | Tốn bộ nhớ, băng thông và thời gian giữ dữ liệu; cần cấu hình thời gian chờ và phân phối trace phù hợp |

Với head sampling 10%, khoảng 10% trace gốc được chọn về mặt thống kê; **không phải đúng 1 trong 10 request bất kỳ**. Nếu lỗi chỉ xuất hiện trong 0,1% request, head sampling thuần tỷ lệ có thể bỏ lỡ nhiều trace lỗi. Tail sampling có thể giữ 100% trace lỗi và một tỷ lệ trace thành công, nhưng Collector chỉ làm được việc đó với các span thực sự được gửi tới nó. **Span bị SDK loại từ đầu không thể được tail sampler khôi phục.**

Trong OpenTelemetry Java SDK, một cấu hình head sampling thường có dạng minh họa sau (đoạn cấu hình, cần thư viện và toàn bộ thiết lập SDK của ứng dụng):

```java
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;

Sampler sampler = Sampler.parentBased(Sampler.traceIdRatioBased(0.10));
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .setSampler(sampler)
        .build();
```

`parentBased` giúp sử dụng quyết định từ parent khi có parent hợp lệ; `traceIdRatioBased(0.10)` dùng cho trace gốc mới theo tỷ lệ mục tiêu 10%. Đoạn trên không phải chương trình độc lập và chưa cấu hình exporter, processor hoặc vòng đời shutdown.

## 4. Các chiến lược lấy mẫu log

**Log level không phải sampling.** Tắt `DEBUG` là lọc theo mức, còn giữ 1/20 log INFO lặp lại là lấy mẫu. Có thể phối hợp:

- **Theo event/request:** giữ toàn bộ nhóm INFO chẩn đoán cho một tỷ lệ request dựa trên hash `trace_id`. Khi một request được chọn, các log INFO liên quan có cơ hội tạo thành câu chuyện đầy đủ.
- **Theo từng dòng:** giữ ngẫu nhiên 1/N log tương tự. Tiết kiệm đều nhưng có thể làm đứt chuỗi sự kiện trong cùng request.
- **Theo tốc độ:** giới hạn số log giống nhau mỗi giây, gộp các lần lặp thành thông báo có `suppressed_count` hoặc tổng số. Cần tránh che giấu một lỗi bùng phát.
- **Theo kết quả, loại sự kiện hoặc đối tượng:** giữ đầy đủ lỗi/chậm/bất thường; giảm INFO thành công lặp lại. Cần chú ý chi phí biết kết quả chỉ có sau khi request kết thúc.
- **Theo tenant hoặc endpoint:** phân bổ ngân sách log để một khách hàng/đường dẫn lưu lượng cao không chiếm toàn bộ dung lượng; chính sách phải được đo và công bố.

Đối với phân tích từng request, chọn mẫu **ổn định theo trace ID** thường dễ đọc hơn chọn độc lập mỗi dòng. Hash phải phân phối tốt trên định danh thực tế; trong môi trường nhiều service, cần thống nhất tỷ lệ, khóa/hash và vị trí áp dụng nếu muốn giữ cùng một tập request. Không dùng trực tiếp các ký tự đầu của ID làm thuật toán sản xuất nếu ID có cấu trúc hoặc không ngẫu nhiên.

Chính sách tham khảo (điều chỉnh theo SLA và quy định dữ liệu của hệ thống):

| Loại dữ liệu | Chính sách khởi đầu | Lý do |
| --- | --- | --- |
| `DEBUG`/`TRACE` chi tiết | Tắt mặc định; bật có thời hạn cho phạm vi hẹp | Chi phí và rủi ro tiết lộ dữ liệu |
| `INFO` lặp lại ở request thành công | Lấy mẫu theo trace ID hoặc tổng hợp | Giảm nhiễu, vẫn khảo sát được luồng thông thường |
| `WARN`/`ERROR` có giá trị điều tra | Thường giữ đầy đủ, có cảnh báo về bùng nổ | Tránh mất tín hiệu hiếm và nguyên nhân sự cố |
| Audit, bảo mật, giao dịch bắt buộc | Theo yêu cầu toàn vẹn/retention riêng; không lấy mẫu tùy tiện | Có thể là bằng chứng hoặc dữ liệu phải lưu theo chính sách |
| Metrics tổng hợp | Thu thập độc lập với log sampling | Đo tỷ lệ lỗi/latency/traffic trên toàn bộ lưu lượng |

Không nhất thiết mọi `ERROR` đều phải chứa stack trace giống hệt nhau hàng triệu lần; có thể hạn chế phần dữ liệu lặp, tổng hợp hoặc tạo sự kiện đại diện theo chính sách đã duyệt. Tuy nhiên không để bộ lọc INFO thông thường vô tình che đi cảnh báo quan trọng.

## 5. Ví dụ Java 17 chạy độc lập: truyền context và lấy mẫu INFO

Ví dụ dùng API trong JDK để tập trung vào **nguyên lý**; nó không tạo span thực hoặc gửi dữ liệu tới OpenTelemetry. Hai request có `trace_id` và cờ `traceSampled` cố định. Bộ lọc INFO giữ khoảng 1/4 nhóm request dựa trên một phần ID chỉ để minh họa; ERROR luôn được in. `ThreadLocal` lưu context trong thread đang xử lý, còn `propagate` chụp context khi giao việc sang executor rồi khôi phục context cũ bằng `finally`.

Lưu tệp `SamplingLoggingDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SamplingLoggingDemo {
    private static final ThreadLocal<TraceCtx> CURRENT = new ThreadLocal<>();

    record TraceCtx(String traceId, String spanId, boolean traceSampled) {}

    private static void withContext(TraceCtx next, Runnable work) {
        TraceCtx previous = CURRENT.get();
        try {
            if (next == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(next);
            }
            work.run();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    private static Runnable propagate(Runnable task) {
        TraceCtx captured = CURRENT.get();
        return () -> withContext(captured, task);
    }

    private static boolean keepInfo(TraceCtx context) {
        long prefix = Long.parseUnsignedLong(
                context.traceId().substring(0, 8), 16);
        return prefix % 4 == 0;
    }

    private static void log(String level, String event) {
        TraceCtx context = CURRENT.get();
        if ("INFO".equals(level)
                && context != null
                && !keepInfo(context)) {
            return;
        }
        String traceId = context == null ? "-" : context.traceId();
        String spanId = context == null ? "-" : context.spanId();
        String sampled = context == null
                ? "-" : Boolean.toString(context.traceSampled());
        System.out.printf(
                "%s trace_id=%s span_id=%s trace_sampled=%s event=%s%n",
                level, traceId, spanId, sampled, event);
    }

    private static void handle(TraceCtx context, ExecutorService pool) {
        withContext(context, () -> {
            log("INFO", "start");
            CompletableFuture.runAsync(
                    propagate(() -> log("INFO", "async_work")), pool
            ).join();
            log("ERROR", "simulated_failure");
        });
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            handle(new TraceCtx(
                    "00000004000000000000000000000001",
                    "000000000000000a", false), pool);
            handle(new TraceCtx(
                    "00000005000000000000000000000002",
                    "000000000000000b", true), pool);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SamplingLoggingDemo.java
java SamplingLoggingDemo
```

Kết quả stdout (không bao gồm dấu nhắc lệnh):

```text
INFO trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=start
INFO trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=async_work
ERROR trace_id=00000004000000000000000000000001 span_id=000000000000000a trace_sampled=false event=simulated_failure
ERROR trace_id=00000005000000000000000000000002 span_id=000000000000000b trace_sampled=true event=simulated_failure
```

Giải thích:

1. Trace thứ nhất có tiền tố `00000004` nên `4 % 4 == 0`: hai INFO được giữ, **dù** `traceSampled=false`.
2. Trace thứ hai có tiền tố `00000005` nên INFO bị lọc, **dù** `traceSampled=true`.
3. Cả hai ERROR vẫn xuất hiện. Đây là sự kiện lỗi **giả lập để minh họa log**, chương trình không ném exception.
4. Trong tác vụ chạy trên thread của pool, `propagate` chuyển trace context tới điểm ghi log. Sau khi task kết thúc, `finally` trả lại context cũ để không rò rỉ sang request khác.

Ví dụ cố ý dùng prefix và các ID định sẵn để stdout có thể kiểm chứng. **Ứng dụng thật** phải sử dụng ID hợp lệ và thuật toán hash ổn định trên toàn ID (hoặc chính sách của SDK/Collector), đồng thời dùng cơ chế propagation do thư viện tracing hỗ trợ thay vì tự thiết kế hệ thống distributed tracing từ `ThreadLocal`.

## 6. Triển khai với SLF4J, MDC và OpenTelemetry

Trong Java, log thường được phát qua SLF4J cùng Logback/Log4j2 hoặc một backend khác. **MDC (Mapped Diagnostic Context)** thêm thông tin ngữ cảnh vào từng log event, ví dụ `trace_id` và `span_id`. MDC thường gắn với thread, vì vậy không mặc nhiên đi theo `CompletableFuture`, executor hoặc callback; các nền tảng tracing có cơ chế context propagation/instrumentation để giải quyết việc này.

Với ứng dụng đã instrument bằng OpenTelemetry, nên ưu tiên tính năng gắn trace/span ID và context propagation của stack đang dùng. Đoạn mã sau chỉ minh họa cách đọc span hiện tại và thêm hai trường MDC trong phạm vi một log; nó cần phụ thuộc OpenTelemetry API, SLF4J và logger có sẵn:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

SpanContext spanContext = Span.current().getSpanContext();
if (spanContext.isValid()) {
    try (MDC.MDCCloseable trace = MDC.putCloseable(
                 "trace_id", spanContext.getTraceId());
         MDC.MDCCloseable span = MDC.putCloseable(
                 "span_id", spanContext.getSpanId())) {
        logger.info("Order processed");
    }
}
```

Chỉ thêm ID khi context hợp lệ; cấu hình encoder/layout để các trường MDC thực sự được xuất trong log JSON hoặc text. `MDCCloseable` giúp dọn giá trị sau log, tránh giữ thông tin từ request trước trên thread dùng lại. Nếu agent/instrumentation đã tự chèn trace context, không chèn lặp hoặc tạo các khóa xung đột.

Phải làm rõ vị trí sampler trong pipeline:

```text
HTTP/gRPC request
  -> extract/propagate trace context
  -> application + spans
       |-> trace SDK/exporter -> (head/tail sampling) -> trace backend
       |-> logger/MDC -> level/filter/log sampling -> log backend
  -> metrics (đếm đầy đủ traffic, lỗi, độ trễ)
```

Thứ tự và vị trí cụ thể khác nhau theo stack. Nếu dùng log sampling tại ứng dụng, log bị bỏ sẽ không truyền qua network; nếu lọc ở collector/backend, ứng dụng vẫn có thể chịu chi phí tạo và truyền log. Ghi log với tham số, ví dụ `logger.debug("id={}", id)`, để tránh nối chuỗi không cần thiết; những phép tính đắt tiền để dựng payload vẫn nên đặt sau kiểm tra điều kiện ghi log khi phù hợp.

## 7. Thiết kế chính sách không làm mất khả năng điều tra

Một chính sách hữu dụng phải trả lời được:

1. **Cái gì được giữ chắc chắn?** Thông thường là tín hiệu lỗi nghiêm trọng, audit bắt buộc, phát hiện bảo mật, sự cố thanh toán hoặc sự kiện có yêu cầu lưu trữ riêng.
2. **Cái gì có thể giảm?** INFO thành công lặp lại, thông tin chẩn đoán tần suất cao, bản sao stack trace không bổ sung ý nghĩa.
3. **Lấy mẫu ở đâu?** Trong SDK/logger, gateway/Collector hay backend? Quyết định này ảnh hưởng chi phí trước và sau điểm lọc.
4. **Lấy mẫu theo đơn vị nào?** Theo request/trace, event, endpoint, tenant hay giới hạn tốc độ. Quy tắc phải không phá vỡ liên kết log với context.
5. **Có đo mức mất mát không?** Theo dõi số log/span bị lọc, lượng xuất, lỗi exporter, quota, độ trễ và tỷ lệ error từ metrics độc lập.

Lỗi thiết kế thường gặp và cách sửa:

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ ghi log khi `spanContext.isSampled()` | Có thể mất ERROR của request không được lấy mẫu trace | Đặt chính sách log theo severity và mục tiêu điều tra, độc lập với sampled flag |
| Mỗi service quyết định sampling tùy ý | Trace/log đứt đoạn khó đối chiếu | Propagate parent context và thống nhất chính sách theo trace ID |
| Dùng tail sampling sau head sampling đã loại span | Không thể cứu các trace lỗi đã mất từ nguồn | Đảm bảo dữ liệu cần tail decision đi đến bộ xử lý tail |
| Quên truyền context qua executor | Log bất đồng bộ mất `trace_id` hoặc mang ID sai | Dùng context-aware executor/instrumentation; luôn khôi phục ngữ cảnh |
| Dùng hash/seed không ổn định hoặc lấy mẫu từng log độc lập | Khó tái hiện quyết định, mất chuỗi INFO liên quan | Dùng hàm hash và chính sách nhất quán; cân nhắc lấy mẫu theo request |
| Dựa vào log đã sampling để tính tỷ lệ lỗi | Chỉ số bị sai lệch vì tập mẫu | Đo traffic, error, latency bằng metrics độc lập |
| Đưa token, mật khẩu, nội dung nhạy cảm vào MDC/baggage | Rò rỉ hoặc lan truyền dữ liệu ngoài ý muốn | Chỉ đưa định danh an toàn; lọc dữ liệu và thiết lập retention |
| Biến `trace_id` thành nhãn của metric | Cardinality rất cao, chi phí lớn | Giữ trace ID trong log/trace; metric dùng nhãn hữu hạn |

Với một request không có trace được lưu, `trace_id` trong log vẫn có ích để tập hợp sự kiện. Giao diện tra cứu trace có thể trả “not found” vì trace không được chọn, mất tại exporter, vượt quota hoặc chưa được ingest. Vì vậy, cần các trường như service, environment, severity, timestamp, `trace_id`, `span_id` (khi hợp lệ) và request/operation name để tìm từ log mà không phụ thuộc trace backend.

## 8. Kiểm chứng trong môi trường thật

Thiết lập bộ tình huống tối thiểu: request thành công có và không được chọn trace; request lỗi/timeout; request đi qua nhiều service; tác vụ bất đồng bộ trên thread pool; request không có incoming `traceparent`; lượng request lớn gây nhiều log giống nhau. Kiểm tra:

- Log vẫn có `trace_id`/`span_id` đúng khi ngữ cảnh hợp lệ; ID không bị lẫn giữa request trong thread pool.
- Tỷ lệ trace/log đạt **xấp xỉ** mục tiêu trên mẫu đủ lớn; tình huống lỗi quan trọng không bị lọc bởi chính sách INFO.
- Log WARN/ERROR, audit và metrics tuân theo retention/bảo mật riêng; không dựa vào trace sampling để quyết định toàn bộ.
- Truy vấn log theo trace ID vẫn hoạt động kể cả khi trace không tồn tại trong backend; khi trace có mặt, timestamp và span ID khớp logic.
- Dashboard có chỉ số dropped events, sampling rate, exporter failures và giới hạn dung lượng để điều chỉnh chính sách dựa trên dữ liệu.

**Ghi nhớ:** trace sampling kiểm soát lượng dữ liệu tracing, log sampling kiểm soát dòng log, còn trace context giúp liên kết cả hai. Giảm dữ liệu có chọn lọc nhưng giữ ID tương quan, tín hiệu lỗi quan trọng, bảo vệ dữ liệu và metrics đầy đủ mới tạo được hệ quan sát vừa tiết kiệm vừa điều tra được.
