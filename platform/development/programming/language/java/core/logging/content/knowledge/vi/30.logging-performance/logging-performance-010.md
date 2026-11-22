# Tối ưu hot path khi ghi logging trong Java

## 1. Tối ưu hot path nghĩa là gì?

**Hot path** là đoạn thực thi được gọi với tần suất cao hoặc trực tiếp quyết định độ trễ của một thao tác quan trọng: xử lý mỗi HTTP request, mỗi message từ queue, mỗi transaction, mỗi lần duyệt phần tử của vòng lặp lớn, hoặc một đoạn code nằm trong critical section. Nếu đoạn đó tạo log liên tục, chi phí nhỏ của một lần log có thể cộng dồn thành CPU, bộ nhớ cấp phát, GC, I/O, contention và độ trễ đuôi (p95/p99).

Trong Java, một lời gọi logger tưởng như đơn giản có thể phải:

1. Đánh giá tham số ở **call site** trước khi gọi API.
2. Kiểm tra mức log, bộ lọc và context.
3. Dựng thông điệp, chuyển object thành chuỗi, định dạng timestamp/exception.
4. Tạo log event, chụp MDC và metadata cần thiết.
5. Truyền vào appender/handler, đôi khi xếp hàng bất đồng bộ.
6. Serialize, encode rồi ghi console/file/network.
7. Chờ downstream hoặc chịu chính sách buffer khi tải tăng.

**Mục tiêu:** giảm chi phí trên đường thường xuyên mà vẫn giữ tính đúng đắn, khả năng chẩn đoán và tính bảo mật. Không đặt mục tiêu “xóa hết log” hay “async hóa mọi thứ” bằng mọi giá.

Sau bài này, bạn cần phân biệt **chi phí khi level tắt** và **chi phí khi level bật**, dùng lazy logging an toàn, hiểu tác động của sink và queue, biết lúc nào nên sampling/rate limiting, đồng thời đo kết quả theo throughput, allocation và latency thay vì chỉ nhìn vài dòng console.

## 2. Bắt đầu bằng mô hình chi phí

Hãy phân tách một sự kiện thành các phần:

~~~text
Code nghiệp vụ
   │
   ├─ Chuẩn bị tham số (có thể rất đắt)
   ├─ Kiểm tra logger/level
   ├─ Dựng sự kiện + context + exception
   ├─ Filter / layout / encoder
   ├─ Appender / Handler
   │    ├─ Ghi đồng bộ → I/O → stdout/file/socket
   │    └─ Enqueue async → queue → worker → I/O
   └─ Trả điều khiển cho luồng nghiệp vụ
~~~

Một cách suy nghĩ định tính:

~~~text
Tổng chi phí logging ≈
  số lần đi qua call site
  × (chi phí chuẩn bị luôn xảy ra
     + chi phí kiểm tra / tạo event khi có thể ghi)
  + chi phí ghi sink, tranh chấp và xử lý hàng đợi
~~~

Đây là **mô hình tư duy**, không phải công thức đo thời gian chính xác. Trong pipeline async, chi phí có thể chuyển sang worker/collector thay vì biến mất. CPU tổng và I/O vẫn tồn tại.

| Điều kiện | Chi phí thường còn tồn tại | Cần quan tâm |
| --- | --- | --- |
| DEBUG bị tắt | Tính các đối số Java trước lời gọi; nối chuỗi; tạo object nếu viết không đúng | Lazy evaluation, guard và tránh side effect |
| DEBUG bật nhưng event bị filter ở appender | Một phần thông điệp/event/context có thể đã được tạo | Đặt filter sớm khi phù hợp, đo theo backend cụ thể |
| INFO bật, console/file đồng bộ | Format, lock/synchronization, system call, flush, giới hạn downstream | Giảm số event, batch/async phù hợp, cải thiện sink |
| Async appender queue có chỗ | Tạo/chụp event, enqueue, đồng bộ producer–consumer | Allocation, queue capacity, thread context |
| Async queue đầy | Block, fallback, drop hoặc chính sách khác tùy backend | Tail latency, backpressure, mất event, metrics |
| Thu thập log tập trung | Network, serialize, collector, parsing, indexing | Dung lượng, cardinality, chi phí lưu trữ, retention |

Một mốc quan trọng: **logger thread-safe không có nghĩa một lời gọi logger là miễn phí**, và **log bất đồng bộ không đồng nghĩa không chặn hoặc không mất log**.

## 3. Nhận diện hot path trước khi sửa

Ví dụ các vị trí có nguy cơ cao:

~~~java
// Snippet trong một phương thức xử lý batch.
for (Order order : orders) {
    log.debug("order={} payload={}", order.id(), expensiveSerialize(order));
    process(order);
}
~~~

Đoạn trên là ví dụ SLF4J, không phải chương trình Java độc lập. Hàm expensiveSerialize(order) vẫn chạy **trước khi** log.debug nhận các đối số, ngay cả khi mức DEBUG đang tắt. Nếu vòng lặp có hàng trăm nghìn phần tử, chi phí này lớn hơn rất nhiều so với bản thân phép so sánh mức log.

Đoạn code cần xem xét còn gồm:

- Logging ở mọi lần duyệt collection hoặc từng byte/record/message.
- Logging trong synchronized/Lock đang nắm giữ; I/O có thể kéo dài thời gian giữ khóa.
- Logging trong retry loop, timeout loop hoặc lỗi có tần suất cao, gây **log storm**.
- toString() của object graph lớn, JSON serialization hoặc thu thập stack trace tốn kém.
- Mỗi event tạo nhiều trường metadata không cần thiết, hoặc cấu hình debug quá chi tiết.
- Gọi System.out.println trực tiếp nhiều lần trong path nóng.
- Tạo/flush file, HTTP request hoặc producer network mới trên từng event.

Trước khi tối ưu, xác nhận bằng profiler, metrics và log rate rằng logging thực sự là bottleneck. Nếu phần lớn thời gian ở truy vấn database, việc thay một phép nối chuỗi trong logger có thể không làm p99 thay đổi đáng kể.

## 4. Quy tắc Java: đối số được đánh giá trước lời gọi

Đây là lỗi căn bản và dễ khắc phục nhất.

~~~java
// Sai khi DEBUG thường bị tắt:
log.debug("State = " + expensiveStateAsText());
log.debug("State = {}", expensiveStateAsText());
log.debug(String.format("State = %s", expensiveStateAsText()));
~~~

Cả ba cách đều gọi expensiveStateAsText() **trước** khi logger quyết định sự kiện có được ghi hay không.

Đặc biệt, cú pháp placeholder của SLF4J:

~~~java
log.debug("order={} status={}", orderId, status);
~~~

có thể tránh một số thao tác định dạng chuỗi khi mức log tắt. Tuy nhiên, nếu orderId hoặc status là **kết quả của hàm đắt tiền**, hàm đó vẫn được thực thi trước lời gọi. Placeholder không thay đổi quy tắc đánh giá đối số của Java.

### 4.1. Guard bằng isDebugEnabled / isLoggable

~~~java
// Snippet SLF4J
if (log.isDebugEnabled()) {
    log.debug("State = {}", expensiveStateAsText());
}
~~~

Guard hữu ích khi việc tính dữ liệu chỉ để log và tốn đáng kể CPU/I/O/allocation. Nếu đầu vào chỉ là primitive, String bất biến đã có sẵn hoặc một vài biến cục bộ, thêm guard vào mọi câu log có thể làm code dài mà không tạo lợi ích đo được.

Đừng để code nghiệp vụ phụ thuộc vào việc bật log:

~~~java
// Sai về tính đúng đắn: thay đổi trạng thái chỉ xảy ra khi DEBUG bật.
if (log.isDebugEnabled()) {
    log.debug("processed={}", processed.incrementAndGet());
}
~~~

Nếu DEBUG tắt, counter sẽ không tăng. Đưa phép cập nhật nghiệp vụ ra ngoài khối điều kiện, chụp giá trị rồi log nếu cần.

### 4.2. Supplier / lazy evaluation

Java Util Logging (JUL) hỗ trợ overload dùng Supplier<String>:

~~~java
// Snippet Java 17; logger là java.util.logging.Logger.
logger.log(java.util.logging.Level.FINE,
        () -> expensiveStateAsText());
~~~

Khi logger không cho phép mức FINE, supplier của message không phải được gọi. Nếu mức phù hợp, JDK có thể yêu cầu supplier tạo thông điệp rồi chuyển tới Handler. Lưu ý: **việc tạo lambda/capture biến vẫn có chi phí tiềm năng**; JIT có thể tối ưu một số trường hợp nhưng không được coi là không cấp phát trong mọi ứng dụng.

Trong SLF4J 2.x, fluent logging API hỗ trợ supplier cho argument:

~~~java
// Snippet SLF4J 2.x; cần dependency SLF4J 2.x và provider tương ứng.
log.atDebug()
   .setMessage("state={}")
   .addArgument(() -> expensiveStateAsText())
   .log();
~~~

Phần expensiveStateAsText() chỉ nên được gọi khi builder thực sự đánh giá argument. Đây không phải API của SLF4J 1.7; với bản 1.7 có thể dùng guard thay thế. Với Log4j 2, cũng có các overload dùng Supplier/lazy message tùy phiên bản; cần chọn API đúng của Log4j 2 đang chạy, không mặc định cú pháp SLF4J dùng được với mọi logger.

**Hãy phân biệt lazy message với lazy dữ liệu nghiệp vụ:** nếu supplier đọc một object mutable ở thời điểm khác, nội dung log có thể không phản ánh trạng thái mong muốn. Chụp snapshot bất biến trước khi tạo supplier nếu việc đọc phải nhất quán.

## 5. Chương trình Java 17 hoàn chỉnh: eager và lazy khi log bị tắt

Ví dụ này dùng **JUL có sẵn trong JDK**, không cần Maven hay SLF4J, và cố định mức INFO để quan sát chính xác số lần xây thông điệp.

**Tệp: LoggingHotPathDemo.java**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingHotPathDemo {
    private static final class CapturingHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        CapturingHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Các message được giữ sẵn trong bộ nhớ.
        }

        @Override
        public void close() {
            // Ví dụ không sở hữu tài nguyên ngoài.
        }

        List<String> messages() {
            return List.copyOf(messages);
        }
    }

    private static String buildMessage(
            AtomicInteger builds, String label) {
        builds.incrementAndGet();
        return "payload-" + label;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.hotpath");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        CapturingHandler handler = new CapturingHandler();
        logger.addHandler(handler);

        AtomicInteger builds = new AtomicInteger();

        try {
            // 1. Eager: dù FINE tắt, hàm vẫn chạy.
            logger.fine(buildMessage(builds, "eager-fine"));

            // 2. Lazy: FINE tắt, supplier không dựng message.
            logger.log(Level.FINE,
                    () -> buildMessage(builds, "lazy-fine"));

            // 3. Guard: FINE tắt, không gọi hàm tốn kém.
            if (logger.isLoggable(Level.FINE)) {
                logger.fine(buildMessage(builds, "guarded-fine"));
            }

            // 4. INFO bật, supplier được gọi một lần.
            logger.log(Level.INFO,
                    () -> buildMessage(builds, "lazy-info"));

            // 5. Thông điệp rẻ đã có sẵn.
            logger.info("READY");

            System.out.println("messageBuilds=" + builds.get());
            System.out.println(
                    "logEvents=" + handler.messages().size());
            for (String event : handler.messages()) {
                System.out.println("event=" + event);
            }
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 LoggingHotPathDemo.java
java LoggingHotPathDemo
~~~

**Stdout chính xác:**

~~~text
messageBuilds=2
logEvents=2
event=payload-lazy-info
event=READY
~~~

**Giải thích từng bước:**

1. FINE là mức chi tiết hơn INFO. Với logger ở INFO, sự kiện FINE không đi tới Handler. Nhưng Java đã thực thi buildMessage trong lời gọi logger.fine(...), nên builds tăng từ 0 lên 1.
2. Overload logger.log(Level.FINE, Supplier<String>) bỏ qua message supplier khi FINE bị tắt, nên không tăng builds.
3. Guard isLoggable(Level.FINE) cũng ngăn gọi buildMessage, nên không tăng builds.
4. INFO được bật; JUL gọi supplier và builds tăng lên 2. CapturingHandler nhận message payload-lazy-info.
5. INFO "READY" được tạo như một event thứ hai mà không gọi buildMessage.

CapturingHandler dùng bộ nhớ chỉ để **kiểm chứng chức năng và làm output ổn định**. Nó không mô phỏng chi phí formatter, console/file I/O hay concurrency của logging production. Kết quả chứng minh **số lần đánh giá thông điệp**, không chứng minh lazy luôn nhanh hơn guard theo nanosecond trong mọi JVM.

## 6. Chọn chiến lược log theo chi phí tính đối số

| Nội dung cần log | Gợi ý | Lý do |
| --- | --- | --- |
| Một String/primitive đã có | Dùng placeholder bình thường | Chi phí chuẩn bị nhỏ; code đơn giản |
| toString() hoặc serialize DTO lớn | Guard hay supplier | Tránh tạo chuỗi lớn khi level tắt |
| Truy vấn DB/HTTP chỉ để bổ sung log | Tránh làm trong log; cân nhắc loại bỏ | Không nên tạo I/O nghiệp vụ phụ chỉ để DEBUG |
| Stack trace từ exception đang có | Log exception có điều kiện và giới hạn tần suất | Format stack trace có thể tốn CPU/dung lượng; không mất thông tin quan trọng |
| Kết quả tính toán nghiệp vụ cần cho logic tiếp theo | Tính một lần, dùng lại | Không để việc bật log thay đổi logic |
| Tập field nhỏ, có cấu trúc | Structured/parameterized logging | Tránh parse chuỗi và giữ schema rõ ràng |
| Payload chứa dữ liệu nhạy cảm | Không log nguyên bản; dùng field allowlist | Cả hiệu năng và bảo mật |
| Số lượng event rất lớn, ít giá trị | Sampling/rate limiting có chủ đích | Giảm tổng số event sinh ra và truyền đi |

Không áp dụng một kỹ thuật đồng loạt. Khi supplier phức tạp hơn guard, hãy ưu tiên code dễ kiểm tra, rồi benchmark đúng workload.

## 7. Parameterized logging: hiểu chính xác điều nó tối ưu

Với SLF4J:

~~~java
// Snippet; giả sử orderId là String có sẵn.
log.debug("order_id={}", orderId);
~~~

Logger có thể tránh phần định dạng message khi mức DEBUG tắt. Nhưng:

~~~java
// Hàm vẫn được gọi trước khi logger kiểm tra level.
log.debug("order={}", serializeOrder(order));
~~~

không lazy. Một số logging backend có thể trì hoãn toString() của object được truyền trực tiếp, nhưng **đừng giả định mọi provider/async encoder có cùng thời điểm đánh giá**. Đặc biệt, truyền một đối tượng mutable tới async pipeline mà không chụp trạng thái có thể tạo thông điệp không nhất quán.

**Ví dụ giữ snapshot rẻ:**

~~~java
// Snippet Java 17 trong ngữ cảnh ứng dụng.
record OrderSnapshot(String id, String status, long amountMinor) {}

OrderSnapshot snapshot = state.snapshot(); // Đồng bộ đúng ở state.
log.debug("order_id={} status={} amount_minor={}",
        snapshot.id(), snapshot.status(), snapshot.amountMinor());
~~~

Ở đây state.snapshot() phải thực sự chụp một trạng thái nhất quán theo thiết kế ứng dụng. Nếu snapshot() đắt và chỉ dùng để debug, kiểm tra level trước khi gọi. Nếu snapshot cũng cần cho nghiệp vụ, tạo một lần rồi dùng lại. Không đưa lời gọi snapshot vào supplier nếu nó phải phản ánh **đúng thời điểm event được phát** và có thể chạy sau khi state thay đổi.

### String concatenation, String.format và JSON serialization

Tránh:

~~~java
log.debug("request=" + request + ", body=" + serialize(body));
log.debug(String.format("response=%s", serialize(response)));
~~~

Nếu DEBUG bị tắt, nối chuỗi và serialize vẫn có thể đã xảy ra. Ưu tiên:

~~~java
if (log.isDebugEnabled()) {
    log.debug("request_id={} response={}",
            requestId, serialize(response));
}
~~~

Ngay cả khi DEBUG bật, **không serialize payload lớn theo mặc định**. Chỉ lấy vài trường được cho phép như status, byte count, response type hoặc ID. Ghi mọi payload làm tăng CPU, GC, lưu trữ và rủi ro rò rỉ dữ liệu.

## 8. Mức log và chính sách cấu hình cho đường nóng

Một quy ước hữu ích:

- **TRACE:** chỉ dùng trong debug mục tiêu hẹp, có giới hạn thời gian.
- **DEBUG:** thông tin phát triển/chẩn đoán; tránh bật toàn cục ở production.
- **INFO:** cột mốc đáng chú ý, không phải mỗi vòng lặp nhỏ.
- **WARN/ERROR:** bất thường hoặc lỗi cần xử lý; cũng phải hạn chế log lặp hàng triệu lần cho cùng một sự cố.

Mức log thực tế phụ thuộc môi trường. Với Spring Boot:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders.internal=DEBUG
~~~

Đây là snippet Spring Boot properties, không áp dụng tự động cho ứng dụng JUL thuần. Level ở logger/appender và các filter có thể tương tác; cấu hình provider thực tế quyết định event có được ghi hay không.

Nếu một module hot path phát 100.000 DEBUG event/giây, chỉ bật DEBUG cho module đó trong 30 phút vẫn tạo lượng log đáng kể. Cần ước lượng log rate và dung lượng trước khi thay mức, không chỉ dựa vào tên level.

### Không dùng DEBUG như một điều kiện của logic nghiệp vụ

Sai:

~~~java
// KHÔNG làm: khi DEBUG tắt sẽ bỏ qua cập nhật.
if (log.isDebugEnabled()) {
    int newValue = processed.incrementAndGet();
    log.debug("processed={}", newValue);
}
~~~

Đúng hơn:

~~~java
int newValue = processed.incrementAndGet();
log.debug("processed={}", newValue);
~~~

Đây là các snippet, giả định processed và log đã khai báo. Nếu newValue không cần lưu cho nghiệp vụ và chỉ dùng trong log, có thể chọn chiến lược khác nhưng phép increment **phải luôn xảy ra** theo logic ứng dụng. Logging là hiệu ứng phụ quan sát, không nên là điều kiện để trạng thái ứng dụng thay đổi.

## 9. Ghi ít log hơn nhưng giữ được tín hiệu quan trọng

Khi log rate quá cao, tối ưu thông điệp từng dòng không đủ. Cần giảm số event được phát.

### 9.1. Không log tất cả lượt xử lý thành công

Thay vì INFO mỗi item:

~~~text
INFO processed item=1
INFO processed item=2
INFO processed item=3
...
~~~

có thể ghi một bản tổng kết theo batch:

~~~text
INFO batch_complete processed=1000 failed=0 elapsed_ms=280
~~~

Khi cần truy vết một item cụ thể, dùng trace ID, debug tạm thời hoặc sampling. Đừng thay thế tất cả kết quả nghiệp vụ cần kiểm toán bằng một counter nếu chúng phải được ghi nhận bền vững.

### 9.2. Sampling

Sampling lấy một phần event có chủ đích, ví dụ 1% request thành công. Có hai nhóm:

- **Random sampling:** mỗi event có xác suất được chọn. Tốt cho thống kê khối lượng lớn, nhưng một request riêng có thể chỉ có một phần dấu vết nếu các tầng quyết định khác nhau.
- **Deterministic sampling theo trace/request ID:** cùng ID đưa ra cùng kết quả chọn trong cùng một quy tắc; hữu ích để có lịch sử nhất quán hơn qua nhiều bước, nếu các service dùng logic chung.

Ví dụ snippet chọn một phần theo phép hash ổn định:

~~~java
// Minh họa: traceId đã được xác thực, không phải PII.
boolean keep = Math.floorMod(traceId.hashCode(), 100) == 0;
if (keep) {
    log.debug("trace_id={} detail={}", traceId, lightweightSummary);
}
~~~

Đây không phải bộ sampling chính xác 1% cho mọi tập dữ liệu (hash có thể phân bố lệch) và không bảo đảm các service sử dụng cùng hàm/quy tắc. Nếu trace tracing backend có cơ chế sampler, ưu tiên cơ chế đó để bảo toàn ngữ cảnh. **Không sample mù** các sự kiện bảo mật, audit, trạng thái cần theo dõi đầy đủ hay lỗi hiếm quan trọng.

### 9.3. Rate limiting và log storm

Một lỗi phụ thuộc bên ngoài có thể lặp hàng nghìn lần/giây. Việc ghi một ERROR với stack trace đầy đủ cho mỗi lần retry có thể làm hệ thống chậm thêm.

Giải pháp thường dùng:

- Ghi cảnh báo đầu tiên, sau đó tổng hợp số lần lặp trong một cửa sổ thời gian.
- Dùng filter/appender hỗ trợ rate limiting nếu backend cung cấp.
- Giữ metrics counter cho tổng lần lỗi và alerting, kể cả khi log chi tiết bị giới hạn.
- Ghi event khi trạng thái chuyển từ healthy sang unhealthy và khi hồi phục, thay vì spam cùng một thông điệp.

Chính sách hạn chế nên có **khóa nhóm ổn định** (error type, component) và giới hạn số khóa để tránh cardinality tăng không kiểm soát. Đừng gộp tất cả lỗi khác nhau vào một thông điệp "error happened" đến mức mất khả năng chẩn đoán.

## 10. Appender/Handler và I/O mới thường là nút thắt thực sự

Ngay cả khi định dạng nhanh, ghi console/file/socket vẫn chịu chi phí hệ điều hành và downstream. Khi nhiều thread cùng ghi một sink, framework có thể phải đồng bộ hoặc xếp hàng; chi phí lock contention và backpressure thường tăng mạnh dưới tải.

### 10.1. Không mở tài nguyên trên mỗi sự kiện

Tránh custom logging kiểu:

~~~java
// Anti-pattern minh họa, không phải chương trình độc lập.
try (FileWriter writer = new FileWriter("app.log", true)) {
    writer.write(message + "\n");
}
~~~

Mỗi event có thể mở/đóng file, tạo đối tượng, phát sinh system call và không có chính sách rotation/encoding đáng tin. Dùng appender do backend quản lý vòng đời, thiết lập buffer, rotation và quyền truy cập theo yêu cầu.

### 10.2. stdout trong container

Với Docker/Kubernetes, console logging tới stdout/stderr thường dễ tích hợp collector và tránh nhiều JVM tranh một file chia sẻ. Tuy nhiên stdout **không miễn phí**: runtime logging driver, pipe, node disk và collector đều có giới hạn throughput. Nếu appender cố flush liên tục hoặc sink chậm, latency có thể tăng.

Phân biệt:

- **Synchronous logging:** luồng nghiệp vụ có thể chờ ghi/flush theo hành vi appender.
- **Asynchronous logging:** luồng nghiệp vụ thường đưa event vào queue và trả về nhanh hơn trong điều kiện bình thường, nhưng producer vẫn tốn phí tạo event/enqueue và chịu chính sách khi queue đầy.
- **Remote logging trực tiếp:** một số appender gửi network trong path của request; nếu backend chậm, sự cố quan sát có thể lan thành sự cố ứng dụng. Nên cân nhắc collector/buffer tách rời theo kiến trúc.

### 10.3. Flush và độ bền

Không gọi flush/fsync trên mỗi event một cách máy móc chỉ vì muốn “an toàn”. Các mức bền vững khác nhau:

1. Event đã được gọi vào logger.
2. Event đã nằm trong queue/buffer.
3. Event đã được writer gửi tới stream/file.
4. Dữ liệu đã được OS hoặc remote collector tiếp nhận.
5. Backend lưu bền vững và truy vấn được.

Tùy backend, không có bảo đảm rằng mức 1 ngầm dẫn đến mức 5. Nếu cần nhật ký giao dịch không mất, nên thiết kế audit/outbox/event store phù hợp; log vận hành thông thường không thay thế nguồn sự thật giao dịch.

## 11. Async logging: giảm chờ I/O, không xóa chi phí

Async logging thường gồm producer từ các thread nghiệp vụ và worker tiêu thụ queue:

~~~text
Thread 1 ──► [log event] ┐
Thread 2 ──► [log event] ├─► queue/ring buffer ─► logging worker ─► sink
Thread N ──► [log event] ┘
                          ▲
                          └── sức chứa hữu hạn
~~~

**Lợi ích tiềm năng:** producer ít phải chờ I/O sink và có thể gom các thao tác ghi để giảm overhead. **Đánh đổi:** tăng footprint, queue processing, context handoff, độ trễ xuất hiện log và hành vi phức tạp khi đầy queue.

Kiểm tra chính xác các thông số:

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Queue/ring buffer capacity bao nhiêu? | Burst vượt sức chứa có thể đổi hành vi đột ngột |
| Khi đầy producer làm gì? | Block, drop, gọi đồng bộ, hoặc chính sách khác tùy provider |
| Một event chứa dữ liệu mutable không? | Formatter có thể chạy sau lúc state thay đổi |
| MDC/thread name/timestamp được capture khi nào? | Context phải phản ánh thread tạo event, không phải worker ghi |
| Shutdown chờ flush bao lâu? | Log còn trong queue có thể mất nếu tiến trình bị kill |
| Có metric queue depth/drop/block time không? | Không đo được thì khó biết trade-off thực tế |
| Có nhiều queue/partition không? | Không suy ra thứ tự hiển thị toàn cục từ thứ tự gọi log |

Với Logback, một số ứng dụng dùng AsyncAppender bao quanh appender khác. Với Log4j 2, có async appenders hoặc async loggers tùy kiến trúc/cấu hình. Chúng không đồng nhất về queue, overflow policy, discard threshold và thứ tự; phải đọc tài liệu **đúng phiên bản** và kiểm thử ở tải thực.

**Không sửa vấn đề log storm chỉ bằng cách tăng queue:** nếu downstream liên tục chậm hơn tốc độ tạo event, queue lớn chỉ kéo dài thời gian trước khi đầy và tăng bộ nhớ. Cần giảm tốc độ phát, điều chỉnh mức log, tối ưu sink hoặc mở rộng pipeline phù hợp.

## 12. Allocation, GC và biến động p99

Trong một hot path, mỗi event có thể tạo:

- String tạm do nối chuỗi, String.format hoặc toString.
- Array/varargs hay object wrapper cho placeholder.
- Immutable DTO/snapshot được dựng chỉ để log.
- Log event, key/value list, MDC map copy.
- JSON bytes, buffer, encoder allocations.
- Throwable stack trace hoặc chuỗi stack trace.
- Lambda/supplier object nếu capture dữ liệu và không được JVM khử cấp phát.

Một phép cấp phát nhỏ không nhất thiết là bottleneck: JVM tối ưu rất tốt nhiều object ngắn hạn. Nhưng ở hàng trăm nghìn event/giây, allocation rate và GC pressure có thể ảnh hưởng throughput và tail latency. Không kết luận tối ưu từ việc đếm số dòng code hay suy đoán JIT; đo allocation rate hoặc bytes/op khi có benchmark.

### 12.1. Thận trọng khi log collection và object graph

~~~java
// Snippet xấu với hot path nếu items rất lớn.
log.debug("items={}", items);
~~~

Nếu mức log bật, backend có thể gọi toString của collection, đi qua hàng nghìn phần tử, tạo chuỗi dài và lộ dữ liệu. Cách thường hợp lý hơn:

~~~java
log.debug("item_count={} batch_id={}", items.size(), batchId);
~~~

Nếu cần dữ liệu phần tử để chẩn đoán, chỉ chọn một số field an toàn hoặc sample giới hạn có mục đích. Không nên giữ reference mutable tới một list trong async log event rồi giả định giá trị được chụp ngay lúc gọi.

### 12.2. Throwable và stack trace

~~~java
// Snippet SLF4J: exception là Throwable đã có.
log.error("Failed to publish order_id={}", orderId, exception);
~~~

Khi một exception đã được tạo từ nghiệp vụ, truyền nó cho logger giúp backend định dạng stack trace khi sự kiện thực sự được ghi. Đừng tạo exception chỉ để lấy stack trace ở mỗi request thành công, như new Exception().getStackTrace(), nếu không có yêu cầu chẩn đoán cụ thể. Với lỗi lặp, dùng rate limiting và aggregate metrics thay vì log cùng stack trace liên tục.

Bảo đảm không nuốt exception hoặc thay đổi luồng điều khiển chỉ để cắt chi phí log. Quyết định xử lý lỗi thuộc logic ứng dụng, còn logging mô tả quyết định đó.

## 13. MDC, trace context và structured logging trên hot path

MDC (Mapped Diagnostic Context), ThreadLocal hoặc context propagation thường cung cấp trace_id, request_id, tenant-safe identifier và các trường metadata khác.

**Khuyến nghị:**

1. Đặt các trường ổn định ở **đầu request/task scope**, không gọi MDC.put/clear trên mỗi event nếu không cần.
2. Xóa hoặc phục hồi context trong finally khi thread pool tái sử dụng thread.
3. Truyền context tới async task đúng cơ chế của framework; MDC không tự lan qua thread mới.
4. Giới hạn kích thước và cardinality của map; không đưa payload lớn, token hay dữ liệu nhạy cảm vào context.
5. Để encoder/collector gắn metadata của process/pod nếu phù hợp, thay vì tự tạo lại mỗi câu log.

Ví dụ snippet SLF4J:

~~~java
// Trong một request scope; cần SLF4J backend hỗ trợ MDC.
try (org.slf4j.MDC.MDCCloseable ignored =
         org.slf4j.MDC.putCloseable("request_id", requestId)) {
    log.info("request accepted");
    doWork();
} // request_id được remove khi scope đóng.
~~~

Đoạn trên chỉ minh họa một scope đơn. Với scope lồng nhau hoặc khi key đã có giá trị cũ, việc remove đơn thuần không nhất thiết khôi phục giá trị trước đó; khi cần, chụp/restore map cũ trong finally. Cũng cần lưu ý provider MDC thực tế có thể có hành vi khác khi ứng dụng dùng bridge hoặc async logging.

### Structured logging có phải luôn nhanh hơn text?

Không thể kết luận chung. JSON encoder có thể giúp collector query rõ ràng và tránh regex parse, nhưng bản thân việc serialize JSON vẫn tiêu tốn CPU/bytes. Các encoder khác nhau có chi phí allocation, escape ký tự, timezone và xử lý throwable khác nhau.

Đo theo backend thực tế:

- Bytes/event, events/s và tốc độ nén.
- CPU ở producer, logging worker và collector.
- GC allocation, tail latency khi thay encoder/layout.
- Mức độ dễ query và sự ổn định schema.

Khi dùng field category=BUSINESS/TECHNICAL, đừng nhầm tối ưu hot path với việc bỏ schema quan trọng. Giảm số field không cần, nhưng giữ định danh giúp điều tra sự cố và sự kiện cần kiểm chứng.

## 14. Lock contention và tác động đến throughput

Logging có thể làm chậm path nhiều thread ngay cả khi không tốn CPU ở mỗi lệnh ghi, do phải chờ lock hoặc sink chung:

~~~text
worker-A ─┐
worker-B ─┼──► synchronized appender / shared output
worker-C ─┘               │
                           └── slow file / console / collector
~~~

Nếu một thread giữ application lock rồi gọi appender đồng bộ, thời gian chờ I/O có thể kéo dài thời gian giữ lock đó:

~~~java
// Snippet: không nên gọi log I/O chậm khi giữ lock nếu có thể tránh.
synchronized (stateLock) {
    updateState();
    log.info("state updated");
}
~~~

Khi logic cho phép, chụp dữ liệu cần log dưới lock, nhả lock rồi ghi event bên ngoài:

~~~java
String snapshot;
synchronized (stateLock) {
    updateState();
    snapshot = state.summary();
}
log.info("state={}", snapshot);
~~~

Đây là snippet; state.summary() phải tạo snapshot nhất quán, rẻ và an toàn theo thiết kế. Chuyển log ra ngoài lock có thể **đổi thứ tự log giữa các thread**. Không giả định thứ tự dòng log chính là thứ tự commit nghiệp vụ; nếu phải kiểm chứng thứ tự sự kiện, dùng sequence/event ID hoặc lưu sự kiện trong một cơ chế bền vững phù hợp.

Không thêm synchronized bao quanh mọi logger.info để ép log theo thứ tự toàn cục: có thể làm tuần tự hóa toàn bộ hot path và tăng p99.

## 15. Đo lường đúng: không benchmark bằng mắt

### 15.1. Bộ chỉ số nên theo dõi

| Chỉ số | Đo điều gì |
| --- | --- |
| Request throughput (RPS), messages/s | Hệ thống hoàn thành bao nhiêu công việc khi bật/tắt log |
| p50/p95/p99 latency | Phân phối thời gian đáp ứng, đặc biệt đuôi |
| CPU utilization, CPU profile | Thời gian vào formatting, encoder, I/O, lock |
| Allocation rate, bytes/op, GC pauses | Chi phí cấp phát và ảnh hưởng của GC |
| Log events/s, bytes/s | Tổng khối lượng log tạo và thu thập |
| Queue occupancy, dropped events, blocking time | Tình trạng backpressure/overflow của async pipeline |
| File/network sink throughput | Nút thắt ở disk/runtime/collector/backend |
| Tỷ lệ event lỗi có đủ context | Hiệu quả quan sát, không chỉ hiệu năng |

Chỉ tối ưu CPU của code logging mà làm rơi tất cả ERROR log không phải một cải tiến chấp nhận được. Hiệu năng phải được đánh giá **cùng yêu cầu độ tin cậy và khả năng vận hành**.

### 15.2. Dùng JMH cho microbenchmark

JMH phù hợp để so sánh chi phí call site, lazy vs eager, parameterized vs string concatenation dưới môi trường có kiểm soát. Một benchmark đúng thường cần:

- Warmup đủ cho JIT.
- Nhiều iteration và fork độc lập.
- Tham số thay đổi thực sự để tránh constant folding hoặc dead-code elimination.
- Backend/appender/level giống trường hợp cần so sánh.
- Tách disabled-level benchmark khỏi enabled-level benchmark.
- Đo throughput và allocation, không chỉ ns/op.
- Không đồng thời ghi console thật với khối lượng khổng lồ làm nhiễu phép đo.
- Kiểm tra correctness và các thông số GC/thread contention.

Có thể dùng JMH với dependency và plugin phù hợp dự án; đoạn ví dụ Java ở mục 5 **không phải benchmark JMH**. Đếm messageBuilds là cách chứng minh ngữ nghĩa lazy evaluation; không đo thực tế nanosecond.

### 15.3. Load test trong môi trường giống production

Microbenchmark không phản ánh đầy đủ p99 của ứng dụng thật. Kiểm thử ít nhất các chế độ:

| Kịch bản | Mục tiêu |
| --- | --- |
| INFO, tải bình thường | Đường cơ sở |
| DEBUG bị tắt, code eager | Phát hiện chi phí call site bị che giấu |
| DEBUG bị tắt, code lazy/guard | Đánh giá giảm CPU/allocation |
| DEBUG bật cho một package nóng | Xem tác động bật log phục vụ điều tra |
| Sink/collector chậm hoặc không khả dụng | Quan sát backpressure, dropped events, tail latency |
| Burst tải cao | Kiểm tra queue overflow/rotation |
| Shutdown/restart | Kiểm tra event quan trọng có flush được theo cấu hình |

Đổi **một biến mỗi lần**, giữ workload và phần cứng tương đương, ghi cả mức log và cấu hình backend để kết quả có thể tái lập. Benchmark với no-op appender thường cho thấy chi phí API/formatting, nhưng không cho biết chi phí của console/file/network thực tế. Ngược lại, benchmark chỉ bằng console có thể đo giới hạn của terminal hơn là logger.

## 16. Ví dụ chiến lược thay thế theo tình huống

### 16.1. Trước: mỗi item đều serialize nguyên object

~~~java
// Snippet SLF4J
for (Order item : batch) {
    log.debug("item JSON={}", expensiveSerialize(item));
    process(item);
}
~~~

**Sau:** dùng summary và chỉ serialize lúc thực sự cần:

~~~java
for (Order item : batch) {
    if (log.isDebugEnabled()) {
        log.debug("item_id={} payload={}",
                item.id(), expensiveSerializeSafeFields(item));
    }
    process(item);
}
log.info("batch_completed count={}", batch.size());
~~~

Nếu process(item) có thể thay đổi item, đặt logging trước hoặc sau phải có ý nghĩa chính xác. Chỉ log các field an toàn; đừng dùng serializeSafeFields như cách đặt tên đẹp cho việc ghi toàn bộ dữ liệu.

### 16.2. Trước: exception trùng lặp cho từng retry

~~~java
// Snippet: một cảnh báo lỗi lặp rất nhiều lần.
log.error("Remote unavailable, attempt={}", attempt, exception);
~~~

**Sau:** đếm bằng metrics (hoặc counter trong ứng dụng), log khi chuyển trạng thái, và định kỳ xuất summary có giới hạn. Vẫn giữ một số bản ghi đầy đủ theo chính sách; không che giấu sự cố kéo dài.

### 16.3. Trước: ghi file đồng bộ bên trong vùng khóa

~~~java
// Snippet
synchronized (lock) {
    update();
    log.info("updated={}", expensiveSnapshot());
}
~~~

**Sau:** chụp dữ liệu cần thiết, giải phóng khóa, rồi ghi log. Nhưng phải đảm bảo snapshot có cùng version với update nếu yêu cầu; không lấy lại các trường mutable sau khi nhả lock.

### 16.4. Trước: thêm MDC cho mỗi câu log

~~~java
// Snippet
for (Event event : events) {
    MDC.put("request_id", requestId);
    log.info("event={}", event.type());
    MDC.remove("request_id");
}
~~~

**Sau:** đặt MDC một lần cho request/task scope; giữ cleanup/restore đúng thời điểm và đừng giữ context lâu hơn phạm vi công việc.

## 17. Tối ưu theo phiên bản và môi trường runtime

| Runtime | Điều cần kiểm tra |
| --- | --- |
| JUL trong Java 17 | log(Level, Supplier<String>), isLoggable, cấu hình Handler, mức logger, ConsoleHandler thường ghi stderr |
| SLF4J 1.7 | Placeholder và isDebugEnabled; không có fluent supplier API kiểu SLF4J 2 |
| SLF4J 2.x | Fluent builder với Supplier argument, backend/provider tương thích |
| Logback | AsyncAppender, bộ lọc, pattern/encoder, mức logger, chính sách discard/queue phù hợp phiên bản |
| Log4j 2 | Async Logger/Async Appender, Supplier API, queue/ring buffer, chính sách khi đầy, context capture |
| Spring Boot | logging.level.* và backend thực tế, cấu hình logback-spring.xml/log4j2-spring.xml |
| Docker/Kubernetes | stdout/stderr, runtime buffer, rotation, collector, resource limits và backpressure |

Đặc biệt, thay dependency hoặc logging backend có thể đổi hành vi batching, default async policy và cách capture message/context. Một tối ưu đúng với provider này **không tự động đúng** với provider khác. Ghi lại phiên bản Java, provider và cấu hình benchmark để kiểm tra khi nâng cấp.

## 18. Những tối ưu dễ làm sai

1. **Đặt side effect trong argument log:** khi chuyển sang guard/supplier, logic nghiệp vụ có thể bị bỏ qua.
2. **Bật DEBUG toàn cục để điều tra một service:** tăng CPU, I/O và chi phí backend không cần thiết.
3. **Tin placeholder làm mọi tham số lazy:** Java vẫn đánh giá đối số trước khi gọi.
4. **Tin async không thể drop:** overflow policy quyết định event bị block, drop hay fallback.
5. **Tin log đã ghi là đã được lưu bền vững:** có thể mới vào queue/buffer.
6. **Giữ object mutable cho worker log định dạng sau:** nội dung có thể khác trạng thái lúc tạo event.
7. **Dùng no-op appender benchmark rồi suy ra p99 production:** không mô phỏng sink thật.
8. **Dùng synchronized bao mọi câu log:** biến logging thành bottleneck tuần tự.
9. **Tắt hết ERROR hoặc audit log để giảm tải:** làm mất tín hiệu hoặc vi phạm yêu cầu độ tin cậy.
10. **Ghi payload bí mật trong log:** tạo rủi ro bảo mật và tăng dung lượng.
11. **Chia file theo từng ID động:** tăng cardinality sink, file handle, rotation phức tạp.
12. **Quên tắt debug sau sự cố:** làm chi phí kéo dài và gây log storm.

## 19. Checklist tối ưu hot path trong dự án thật

**Trước khi sửa:**

- Chọn một hot path được profiler hoặc load test chứng minh đang bị ảnh hưởng.
- Đo baseline throughput, p95/p99, CPU, allocation, GC, log bytes/s.
- Kiểm tra level bật/tắt và vị trí thực thi đối số tốn kém.
- Xác định backend và appender đang chạy, thay vì chỉ dựa vào API SLF4J.

**Trong lúc sửa:**

- Đưa logic nghiệp vụ và side effect ra khỏi điều kiện logging.
- Dùng guard hoặc Supplier đúng API khi cần tính dữ liệu đắt chỉ để log.
- Giữ event nhỏ gọn, đủ context, không serialize payload nhạy cảm.
- Giảm số event trên vòng lặp nóng; dùng metrics, summary và sampling có kiểm soát.
- Tránh I/O dưới lock và tránh custom appender không được kiểm thử.
- Nếu dùng async, xác định capacity, overflow, capture context và shutdown flush.

**Sau khi sửa:**

- Test khi DEBUG tắt **và** khi DEBUG bật; xác minh logic nghiệp vụ không đổi.
- Kiểm tra message, trace ID, stack trace và dữ liệu quan trọng vẫn còn đủ.
- Chạy load test với sink/collector giống production, cả lúc tải bình thường và burst.
- So sánh p99, CPU, allocation, drop count; không chỉ xem một chỉ số đẹp.
- Đặt guardrail cho cấu hình debug và kế hoạch rollback.

## 20. Bài tập thực hành

### Bài 1. Đánh giá eager vs lazy

Chạy LoggingHotPathDemo.java ở mục 5. Giải thích vì sao hai sự kiện được ghi nhưng buildMessage được gọi hai lần, trong đó có một lần không tạo ra log record. Đổi mức logger thành FINE và dự đoán lại số lần đánh giá. Sau đó chạy và so sánh kết quả thực tế.

### Bài 2. Sửa vòng lặp nóng

Cho vòng lặp xử lý 100.000 item với serializeOrder(item) tốn thời gian. Viết ba phiên bản: nối chuỗi eager, placeholder với hàm expensive, và guard/lazy. Đặt DEBUG tắt và đo allocation/CPU; giải thích vì sao placeholder không tránh được hàm serialize.

### Bài 3. Kiểm thử khi sink bị chậm

Dùng ứng dụng thử có async appender và sink được kiểm soát để giả lập ghi chậm. Tăng tải cho đến khi queue tiến gần capacity. Thu thập queue depth, dropped events, request latency và kết quả shutdown flush. Giải thích tác động của chính sách overflow.

### Bài 4. Quyết định sampling

Một endpoint trả thành công 50.000 lần mỗi phút nhưng mỗi request tạo hai INFO log. Đề xuất thay đổi: summary/metrics, giữ ERROR và một phần debug theo trace ID. Chỉ rõ những sự kiện audit hoặc business-critical không được sample mù.

### Bài 5. Review đoạn code có lock

Tìm một đoạn synchronized chứa log tạo JSON lớn. Thiết kế snapshot an toàn, nhả lock trước khi serialize/ghi nếu yêu cầu nghiệp vụ cho phép. Đo p99 dưới nhiều thread và kiểm tra thứ tự log có thể thay đổi.

## 21. Tổng kết

Để tối ưu logging trong hot path Java, **đừng chỉ nhìn lời gọi logger**. Chi phí có thể phát sinh trước logger vì Java đánh giá đối số eager, ở encoder khi format hoặc cấp phát, ở appender khi tranh lock/I/O, và ở queue/collector khi downstream chậm. Dùng lazy Supplier/guard cho tham số tốn kém khi level tắt, giảm số event không cần, chọn format/sink phù hợp và kiểm soát async backpressure.

Tối ưu đúng phải giữ nguyên hành vi nghiệp vụ, context và log quan trọng. Đo mức cải thiện theo cả CPU, allocation, p95/p99, throughput **và** tỷ lệ mất log; không biến logging thành một nguồn sai lệch hoặc mất dữ liệu chỉ để đạt con số benchmark tốt hơn.

### Tài liệu tham khảo

- Oracle Java 17 – java.util.logging.Logger và overload Supplier: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Oracle Java 17 – Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J User Manual, parameterized và fluent logging API: https://www.slf4j.org/manual.html
- Logback Manual – Configuration: https://logback.qos.ch/manual/configuration.html
- Logback Manual – Appenders: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 – Performance: https://logging.apache.org/log4j/2.x/manual/performance.html
- Apache Log4j 2 – Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- OpenJDK Java Microbenchmark Harness: https://github.com/openjdk/jmh
