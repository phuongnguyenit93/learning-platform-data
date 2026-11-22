# Chi phí MDC trong hiệu năng logging Java

## 1. MDC giải quyết vấn đề gì?

**Mapped Diagnostic Context (MDC)** là cơ chế gắn các cặp khóa–giá trị vào ngữ cảnh logging, thường là ngữ cảnh của thread hiện tại. Những trường như requestId, traceId hoặc jobId giúp tìm tất cả dòng log của cùng một tác vụ mà không phải truyền ID bằng tham số vào từng câu lệnh logger.

Ví dụ:

~~~text
INFO service=orders requestId=req-42 event=request_started
WARN service=orders requestId=req-42 event=payment_retry
INFO service=orders requestId=req-42 event=request_finished
~~~

Trong Java, SLF4J cung cấp API MDC, nhưng cách lưu trữ và xử lý dữ liệu cụ thể phụ thuộc logging provider như Logback, Log4j 2 hoặc adapter. MDC có thể đơn giản trong một request đồng bộ, nhưng gây thêm công việc khi ứng dụng có lượng log lớn, nhiều key, thread pool, CompletableFuture, virtual threads hoặc async appenders.

**Chi phí MDC** là phần CPU, allocation, bộ nhớ sống và kích thước log tăng thêm do việc tạo, cập nhật, sao chép, đọc, định dạng và dọn ngữ cảnh logging. Chi phí này phải được xem cùng với độ chính xác của log: bỏ MDC hoàn toàn có thể tiết kiệm vài thao tác nhưng khiến không thể truy tìm lỗi xuyên nhiều request.

Nội dung cần phân biệt rõ ba thành phần:

1. **Context operations:** put, get, remove, clear và copy map.
2. **Context propagation:** capture, activate và restore khi đổi thread hoặc executor.
3. **Log emission:** snapshot theo event, đọc MDC ở encoder, serialize JSON/text và vận chuyển log đến sink.

Một câu lệnh MDC.put nhanh trong thử nghiệm nhỏ không có nghĩa overhead tổng của MDC bằng không; ngược lại không thể quy mọi thời gian của logger hay I/O cho MDC.

## 2. Cơ chế chi phí của MDC

Trong nhiều implementation, MDC được quản lý qua ThreadLocal hoặc cấu trúc tương đương theo thread. Không nên đồng nhất API SLF4J với một HashMap cố định: provider và phiên bản có thể chọn mô hình copy-on-write, adapter khác hoặc cách xử lý bất đồng bộ khác.

| Thao tác | Tác dụng | Nguồn chi phí có thể có |
| --- | --- | --- |
| MDC.put(key, value) | Đặt hoặc ghi đè key | Lookup/cập nhật và đôi khi tạo bản sao/cấp phát nội bộ |
| MDC.get(key) | Đọc một key | Lookup context hiện tại |
| MDC.remove(key) | Xóa key | Cập nhật map/context hiện tại |
| MDC.clear() | Dọn toàn bộ MDC hiện tại | Cập nhật state và giới hạn vòng đời |
| MDC.getCopyOfContextMap() | Chụp snapshot map | Cấp phát và copy entry theo kích thước context |
| MDC.setContextMap(map) | Thay thế context từ snapshot | Copy/cập nhật map tùy provider |
| Pattern %X{requestId} | Đưa một key vào log | Lookup và format mỗi event được phát |
| JSON encoder xuất cả MDC | Serialize nhiều key/value | Byte output, escaping, buffer và chi phí collector |
| Async logging | Tạo event trên thread gọi rồi chuyển sang worker | Có thể phải capture MDC trước enqueue |

**Không phải mọi lời gọi put đều clone map** và **không phải mọi encoder đều đọc tất cả key**. Cách đo đúng là xác định provider/version, cấu hình appender/encoder rồi profiler trong ứng dụng thực tế.

MDC thường lưu các String. Snapshot map phổ biến sao chép cấu trúc map và tham chiếu key/value; nó không nhất thiết sao chép toàn bộ ký tự từng String. Tuy nhiên String mới do ứng dụng tự tạo, chẳng hạn request metadata hoặc một JSON lớn, vẫn làm tăng allocation. Chi phí copy map có thể xấp xỉ tăng theo số key, còn chi phí format phụ thuộc lượng dữ liệu thật được xuất.

## 3. Chi phí đặt và dọn ngữ cảnh mỗi request

Một ứng dụng HTTP thường đặt requestId một lần ở request boundary, ghi nhiều log trong các service call, rồi dọn khi xử lý kết thúc.

Ví dụ SLF4J MDC dưới đây là **đoạn tích hợp**, cần SLF4J provider và phương thức processRequest của ứng dụng:

~~~java
import org.slf4j.MDC;

void handleRequest(String requestId) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        processRequest();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Ở đây việc get/put/remove xảy ra theo vòng đời một request, thường hợp lý hơn đặt và xóa requestId quanh mỗi log statement. Khối finally chạy cả khi có exception; khôi phục giá trị cũ giúp tránh làm sai scope lồng nhau.

Có ba lỗi vận hành cần tránh:

- **Không clear:** thread pool tái sử dụng thread nên request sau có thể bị gắn nhầm requestId của request trước, đồng thời giữ tham chiếu tới map lâu hơn.
- **Clear tất cả trong thư viện dùng chung:** MDC.clear() có thể xóa các trường traceId, tenant hoặc jobId do caller/framework sở hữu. Nên khôi phục đúng key mà scope quản lý.
- **Đặt MDC trong vòng lặp nóng:** nếu requestId không đổi, put/remove ở mỗi phần tử chỉ thêm chi phí. Đặt một scope bên ngoài vòng lặp, và thêm field chi tiết ở log event khi thật sự cần.

Một số ứng dụng sử dụng MDC.putCloseable để xóa key tự động. Tuy nhiên không nên giả định việc close sẽ **khôi phục giá trị cũ của cùng key** trong nested scope; cần biết semantics của API/provider hoặc tự lưu giá trị trước khi ghi đè.

## 4. Snapshot và propagation thường đắt hơn một lookup

MDC theo thread không tự chạy theo Runnable khi một tác vụ được chuyển từ caller sang thread pool. Muốn giữ requestId phải **capture** context ở caller, **activate** tại task, rồi **restore** context cũ của worker.

~~~text
HTTP thread: context(requestId=req-42)
    |
    | capture snapshot
    v
Executor queue: Runnable + snapshot
    |
    v
Worker thread: activate -> doWork -> restore
    |
    v
Worker nhận task khác: context đúng cho task mới
~~~

Nếu map có K key, một lần snapshot thường cần sao chép các entry của map, tức lượng công việc phụ thuộc K. Nếu mỗi request tạo H tác vụ con và mỗi task đều capture/restore toàn bộ context, tổng thao tác copy tăng theo số lần chuyển boundary.

**Số lượng task nhỏ là một yếu tố quan trọng.** Một request tạo 50 CompletableFuture nhỏ, mỗi future được bọc bằng nhiều decorator propagation, có thể thực hiện nhiều bản sao map hơn một request đồng bộ chỉ gắn MDC một lần. Không nên dùng số lượng request/giây làm biến giải thích duy nhất.

Đừng chụp MDC nhiều lần trong cùng một wrapper nếu đã có framework hoặc tracing library chuyên trách việc propagation. Mặt khác, không được bỏ context bắt buộc chỉ để giảm allocation; một phương án nhanh hơn nhưng làm log sai ID không phải tối ưu hợp lệ.

## 5. Mô hình chi phí tương đối

Có thể dùng mô hình sau để hiểu hướng tăng trưởng, **không coi đây là công thức tính nanosecond hoặc byte chính xác**:

| Ký hiệu | Đại lượng |
| --- | --- |
| R | Số request/job trong khoảng đo |
| K | Số key trung bình của một MDC map |
| H | Số lần cần capture/restore qua ranh giới thực thi mỗi job |
| L | Số log event thực sự được phát mỗi job |
| T | Số context/thread sống đồng thời |

Nếu một snapshot sao chép hầu hết K key, lượng entry cần sao chép trong khoảng đo có thể tăng theo **R × H × K**. Nếu encoder xuất toàn bộ MDC ở mỗi event, lượng field được serialize có thể tăng theo **R × L × K**. Bộ nhớ sống còn phụ thuộc T, kích thước value, khả năng chia sẻ String, cấu trúc map và thời gian giữ snapshot trong queue.

Các công thức mô tả **xu hướng**. Provider có thể tối ưu việc copy, encoder có thể chỉ đọc hai trường, hoặc async appender chụp context ở thời điểm khác. GC, CPU cache, JIT và I/O làm chi phí thực tế khác xa một phép nhân đơn giản.

## 6. Ví dụ Java 17 chạy độc lập: bản sao context trong thread pool

Để nhìn rõ nơi phát sinh snapshot và cleanup, ví dụ sau mô phỏng một phần hành vi MDC bằng **ThreadLocal<Map<String,String>>** của JDK. Nó **không phải implementation SLF4J MDC**, vì vậy không dùng số đo của chương trình này làm benchmark về Logback hay Log4j 2.

Tạo file **MdcCostConceptDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MdcCostConceptDemo {
    private static final ThreadLocal<Map<String, String>> CONTEXT =
            ThreadLocal.withInitial(HashMap::new);

    private static String requestId() {
        return CONTEXT.get().getOrDefault("requestId", "<missing>");
    }

    private static void withSnapshot(
            Map<String, String> snapshot, Runnable task) {
        Map<String, String> previous = new HashMap<>(CONTEXT.get());
        CONTEXT.set(new HashMap<>(snapshot));
        try {
            task.run();
        } finally {
            if (previous.isEmpty()) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "log-worker-1"));
        try {
            CONTEXT.get().put("requestId", "req-42");
            System.out.println("main=" + requestId());

            pool.submit(() ->
                    System.out.println(
                            "worker-before=" + requestId())).get();

            Map<String, String> captured =
                    new HashMap<>(CONTEXT.get());
            pool.submit(() -> withSnapshot(captured, () ->
                    System.out.println(
                            "worker-with=" + requestId()))).get();

            pool.submit(() ->
                    System.out.println(
                            "worker-after=" + requestId())).get();

            System.out.println("main-after=" + requestId());
        } finally {
            CONTEXT.remove();
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MdcCostConceptDemo.java
java MdcCostConceptDemo
~~~

Stdout xác định khi chương trình chạy thành công:

~~~text
main=req-42
worker-before=<missing>
worker-with=req-42
worker-after=<missing>
main-after=req-42
~~~

Cách hiểu:

1. Context của thread main có requestId, nhưng worker thread chưa có nên in ra missing.
2. new HashMap<>(CONTEXT.get()) ở caller tạo bản sao context hiện tại.
3. withSnapshot tạo context cho worker từ snapshot, chạy task rồi restore/clear trong finally.
4. Task kế tiếp trên cùng worker không còn requestId cũ. Thread main vẫn có requestId ban đầu.
5. Future.get() giữa các submit bảo đảm thứ tự hiển thị trong ví dụ; các task song song thực tế có thể interleave.

Ví dụ này chứng minh **vị trí phải copy/restore**, không chứng minh MDC mất bao nhiêu microsecond. Console output, khởi tạo executor và JVM startup sẽ che lấp chi phí nhỏ của map operation.

## 7. Truyền MDC thật với SLF4J

Đoạn tích hợp sau sử dụng snapshot API của SLF4J. Các thành phần executor và processTask do ứng dụng cung cấp.

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> captured = MDC.getCopyOfContextMap();

executor.execute(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        processTask();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Những bước tạo overhead tùy adapter:

- Capture ở thread gửi lấy bản sao map, có thể phát sinh allocation.
- Worker lấy snapshot context trước đó để khôi phục chính xác sau task.
- setContextMap thay thế context hiện tại; chi phí tùy implementation và số key.
- Lambda giữ tham chiếu captured khi chờ queue, làm snapshot còn sống đến khi task xử lý hoặc bị hủy.
- Nếu nhiều wrapper context cùng bao task, số lần copy/restore có thể tăng không cần thiết.

Wrapper trên chỉ là **mẫu minh họa**, không phải lý do thay thế cơ chế propagation đã được cung cấp bởi Spring TaskDecorator, Micrometer Context Propagation, OpenTelemetry Context hoặc framework tương thích. Cần dùng cơ chế đúng với stack để giữ cả log correlation và span lifecycle khi ứng dụng có distributed tracing.

Nếu chỉ cần một requestId, có thể truyền tường minh một String thay vì cả map. Nhưng nếu hệ thống bắt buộc propagate trace/span/baggage theo chuẩn riêng, việc bỏ bớt key có thể làm mất ngữ cảnh quan trọng.

## 8. Logger tắt DEBUG vẫn có chi phí MDC?

Có. Nếu đoạn code luôn cập nhật MDC trước khi gọi logger, ví dụ:

~~~java
MDC.put("itemId", itemId);
logger.debug("Processing item {}", item);
MDC.remove("itemId");
~~~

thì put/remove vẫn xảy ra ngay cả khi logger không phát DEBUG event. **Tắt mức log thường giảm chi phí tạo/format/ghi event, nhưng không tự tắt các thao tác MDC mà ứng dụng đã thực thi.**

Nếu itemId chỉ phục vụ một DEBUG event tùy chọn, có thể cân nhắc không thực hiện toàn bộ công việc chuẩn bị khi mức log bị tắt, miễn code rõ ràng và không phải propagation bắt buộc. Nếu itemId là context thiết yếu cho các lỗi ở cùng scope, không được bỏ chỉ vì DEBUG tắt.

Cũng tránh eager serialization: tạo sẵn một String JSON lớn hoặc gọi toString phức tạp trước một câu lệnh debug có thể tốn CPU dù event không được phát. Dùng parameterized logging thích hợp và chỉ xây dữ liệu đắt tiền khi có lý do.

## 9. Encoder, số dòng log và chi phí downstream

Khi log event được phát, encoder có thể đọc MDC để xây text hoặc JSON. Ví dụ pattern Logback:

~~~text
%d{ISO8601} %-5level trace=%X{traceId} request=%X{requestId} %logger - %msg%n
~~~

Pattern trên chỉ cần một số key. Ngược lại, JSON encoder có thể xuất toàn bộ MDC map, làm mỗi event dài hơn và tăng công việc escaping/serialization, truyền mạng, parse/index và retention.

Các field phù hợp với MDC thường là:

| Field | Lưu ý |
| --- | --- |
| requestId, traceId, spanId | Ngắn, hỗ trợ correlation/tracing |
| jobId, workerId, attemptNo | Chỉ có khi xử lý job hoặc background task |
| service, version, environment | Nếu bất biến, thường nên cấu hình tại encoder/collector một lần |
| userId, tenant | Chỉ khi có chính sách dữ liệu cho phép |
| Payload, JWT, secret, full request body | Không đưa vào MDC |

Một requestId cardinality cao vẫn có ích trong **log và trace**, vì cần tìm theo ID. Không sử dụng requestId/traceId như label metric tổng hợp kiểu Prometheus counter/histogram, vì tập giá trị khổng lồ có thể làm tăng số chuỗi thời gian.

**Chi phí downstream có thể lớn hơn chi phí map lookup tại JVM.** Nếu mỗi event chứa nhiều trường không cần thiết, phí lưu trữ và truy vấn tăng dù CPU của MDC.put rất thấp. Vì vậy nên giảm cả số event, số field và kích thước value.

## 10. Async logging, snapshot và backpressure

Trong logger bất đồng bộ, thread tạo event và thread thực sự ghi ra stdout/file/network có thể khác nhau:

~~~text
Request thread
   |
   | logger.info/error
   | chụp event + context cần thiết
   v
Bounded async queue
   |
   v
Background logging worker -> encoder -> sink
~~~

Tùy provider, việc chuẩn bị event có thể snapshot MDC, thread name hoặc thông tin khác **ngay trên request thread trước khi enqueue**. Vì vậy bật async không tự xóa toàn bộ chi phí MDC của đường xử lý nóng.

Khi queue đầy, hệ thống phải có **backpressure policy**: block producer, bỏ một số loại event hoặc hành vi khác tùy cấu hình. Với Logback AsyncAppender, các tùy chọn như queueSize, discardingThreshold và neverBlock ảnh hưởng đến cách chặn/bỏ log; cần kiểm tra phiên bản và yêu cầu reliability thực tế.

Các yếu tố cần đo cùng MDC:

- Thời gian enqueue trên producer thread.
- Allocation khi capture context và tạo logging event.
- Độ dài queue, throughput, latency của encoder và log sink.
- Số event bị drop khi tải cao.
- Mức độ ảnh hưởng tới p95/p99 request latency.
- Khả năng flush khi graceful shutdown và lượng log có thể mất khi JVM bị kill.

Không dùng async diagnostic logging kiểu best effort làm nguồn ghi nhận duy nhất của audit hoặc giao dịch bắt buộc. Trường hợp yêu cầu durability phải có cơ chế lưu và xác nhận riêng.

## 11. Thread pool, cleanup và memory retention

Thread pool có worker sống lâu. Nếu MDC không được dọn sau request A, context có thể xuất hiện trong log của request B. Đây vừa là lỗi tính đúng, vừa có thể giữ các String/map tồn tại lâu hơn dự kiến.

Ví dụ nguy hiểm:

~~~text
worker-1 -> requestId=req-A -> task A kết thúc (quên clear)
worker-1 -> task B bắt đầu -> log vô tình vẫn là req-A
~~~

**Đây là context leakage.** Cách sửa là thiết lập scope rõ ràng và restore trong finally. Nếu một thư viện chỉ sở hữu requestId, đừng gọi MDC.clear để xóa luôn key của caller; lưu/khôi phục key riêng. Nếu worker boundary kiểm soát toàn context, có thể dùng snapshot toàn map.

InheritableThreadLocal cũng không phải cơ chế propagation an toàn cho thread pool: thread được tạo trước, rồi tái sử dụng giữa nhiều task, nên giá trị kế thừa lúc tạo thread không theo từng request.

Memory retention còn xuất hiện khi captured map được giữ trong các Runnable đang chờ queue. Khi queue dài, số snapshot và thời gian sống của chúng tăng. Nếu có nhiều field lớn, lượng heap còn sống có thể tăng dù request thread đã kết thúc.

## 12. Virtual threads trong Java 21+

Java 21+ hỗ trợ virtual threads có chi phí tạo/scheduling thấp hơn platform threads ở nhiều tác vụ I/O bound. Mỗi virtual thread vẫn có ThreadLocal riêng nếu ứng dụng sử dụng; đừng nghĩ nó luôn dùng chung MDC với carrier platform thread.

Nếu hệ thống tạo rất nhiều virtual threads đồng thời, mỗi context chứa map và nhiều key sẽ góp phần vào footprint tổng. Các callback hoặc virtual thread mới không tự có đầy đủ context theo mọi cơ chế; cần tuân theo propagation của framework.

Đoạn minh họa Java 21+, không phải chương trình đầy đủ:

~~~java
ThreadFactory factory =
        Thread.ofVirtual().name("request-vt-", 1).factory();
~~~

Đoạn này cần import java.util.concurrent.ThreadFactory. Nó chỉ đặt tên virtual thread, **không tạo MDC và không propagate MDC**. Với virtual threads, hãy đo số lượng context sống, allocated bytes, GC và độ chính xác của correlation dưới tải thật.

## 13. Đo overhead MDC bằng JMH và load test

### 13.1. Microbenchmark với JMH

Một phép đo đơn lẻ:

~~~java
long start = System.nanoTime();
MDC.put("requestId", "req-42");
long elapsed = System.nanoTime() - start;
~~~

không cho phép suy ra chi phí phổ quát. Đây là đoạn minh họa yêu cầu SLF4J. Kết quả bị ảnh hưởng bởi JIT warm-up, GC, CPU scheduling, clock resolution, compiler optimizations và trạng thái context.

Dùng **JMH** với warm-up/forks, tránh dead-code elimination và đo allocation khi cần. Thiết kế benchmark tách các nhóm:

1. put/get/remove với 1, 4, 16 key và giá trị có kích thước thực tế.
2. getCopyOfContextMap/setContextMap với các kích thước context.
3. Logger bị disable so với event thật sự được phát, giữ cố định số event.
4. Pattern chỉ xuất vài key so với JSON encoder xuất toàn map.
5. Sync appender so với async appender, giữ cùng sink và điều kiện tải.

Đo **ns/op, throughput/op, bytes allocated/op, GC count**, không chỉ một giá trị elapsed. Một benchmark rỗng ít khi giải thích đúng latency của request có database, HTTP và collector.

### 13.2. Load test end-to-end

Khi chạy tải giống production, giữ cố định request mix, log level, provider, encoder, appender, collector, máy chủ và workload. So sánh các kịch bản sau:

| Kịch bản | Nội dung thay đổi |
| --- | --- |
| Baseline | Không có MDC, cùng số log event |
| MDC nhỏ | 2–3 key cố định theo request |
| MDC lớn | Thêm nhiều key, giữ số event |
| Propagation | Giữ MDC nhỏ, thêm executor boundary |
| Async | Giữ workload, thay đổi đường appender |
| High volume | Tăng số event trong điều kiện có kiểm soát |

Đo **throughput, CPU, p50/p95/p99 latency, allocation rate, heap/GC pause, queue fullness, drop count, bytes log/sec và ingestion delay**. Java Flight Recorder (JFR) và profiler có thể giúp thấy stack liên quan đến MDCAdapter, map copy, String allocation, encoder và appenders.

**Không công bố một con số slowdown chung nếu chưa đo.** Một ứng dụng ít log, hai field MDC có thể khác hẳn service phát hàng nghìn event/giây với nhiều wrapper propagation.

## 14. Các phương án tối ưu đáng ưu tiên

**Giữ context nhỏ và ổn định:** dùng ID ngắn, có giá trị chẩn đoán; không đặt payload hoặc dữ liệu nhạy cảm. Nếu trường service/version là bất biến, gắn ở encoder/collector.

**Thiết lập ở boundary:** đặt requestId/jobId một lần, log nhiều lần rồi cleanup. Không put/remove trong hot loop khi context không đổi.

**Chỉ copy ở ranh giới thực thi cần thiết:** capture khi submit task, restore khi hoàn thành; ưu tiên một cơ chế propagation chính thức thay vì nhiều wrapper lồng nhau.

**Giảm volume trước khi tối ưu vi mô:** nếu I/O/encoder chiếm phần lớn CPU, bỏ log DEBUG/INFO không có giá trị và tổng kết theo batch thường hiệu quả hơn thay đổi một MDC lookup.

**Giữ tính đúng:** không bỏ field traceId, requestId bắt buộc; không làm mất correlation chỉ vì benchmark cải thiện vài phần trăm. Luôn kiểm thử concurrency, retry và cancellation.

**Kiểm soát downstream:** JSON encoder xuất đúng trường, giảm duplicate fields, giám sát async queue và collector, có chính sách backpressure/retention.

**Bảo mật:** không đưa token/password/Authorization header, dữ liệu cá nhân hoặc toàn bộ request vào MDC. Việc chuyển context qua nhiều tầng có thể đưa các trường đó ra nhiều sink hơn dự kiến.

## 15. Lỗi thường gặp và checklist

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| CPU tăng dù DEBUG tắt | put/copy MDC vẫn chạy hoặc eager serialization | Profile scope, đặt context ở boundary |
| GC tăng khi nhiều async task | Copy map và giữ snapshot trong queue | Giảm số key, tránh wrapper lồng nhau |
| Request B mang ID của A | Quên dọn context trên thread pool | Restore/clear trong finally |
| Async appender vẫn tốn CPU ở request | Event/MDC snapshot trước enqueue | Đo chi phí producer và consumer |
| Heap tăng với virtual threads | Nhiều context sống đồng thời | Giảm key/value size, đo allocation |
| Log mất traceId sau CompletableFuture | Không propagate context | Task decorator hoặc SDK phù hợp |
| Metric backend bùng cardinality | Dùng requestId/traceId làm metric label | Giữ ID động trong log/trace |
| Log thiếu thông tin sau tối ưu | Bỏ field hoặc dọn quá sớm | QA log correctness theo request/job |
| Alert/collector quá tải | Nhiều event hoặc encoder serialize tất cả key | Kiểm soát volume và schema |

Checklist trước khi kết luận đã tối ưu:

- Provider/version và cách MDC được dùng đã được xác định.
- Có baseline so sánh số key, số event và số lần propagation.
- Benchmark tách put/get/remove khỏi snapshot/format/sink.
- Load test xác nhận latency, CPU, allocation và log drop thực tế.
- Request/job ID không bị lẫn sau thread reuse, retry hoặc exception.
- MDC không chứa secret và không để dữ liệu tồn tại vượt quá scope.
- Logging pipeline vẫn cung cấp ngữ cảnh lỗi quan trọng cho vận hành.

**Ghi nhớ:** chi phí MDC phụ thuộc vào **số lần cập nhật context, kích thước map, tần suất snapshot khi đổi thread, số event đọc/serialize MDC và lượng context sống đồng thời**. Hãy giảm thao tác thừa mà vẫn bảo toàn thông tin truy vết, đo trong đúng logging stack và kiểm chứng trên tải production tương đương trước khi quyết định tối ưu.