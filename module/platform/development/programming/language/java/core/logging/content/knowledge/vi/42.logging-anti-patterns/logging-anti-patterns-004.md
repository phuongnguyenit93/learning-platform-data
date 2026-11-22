# Nối chuỗi không cần thiết trong Java Logging: vì sao chậm và cách sửa đúng

## 1. Anti-pattern cần nhận diện

**Nối chuỗi không cần thiết (unnecessary string concatenation)** trong logging xảy ra khi chương trình **tạo thông điệp hoặc tính dữ liệu phục vụ log trước khi biết sự kiện đó có được ghi hay không**. Ví dụ:

~~~java
// SLF4J/Log4j 2: anti-pattern.
log.debug("Order " + orderId + " state=" + state);
~~~

Ngay cả khi DEBUG bị tắt, Java vẫn phải **đánh giá đối số** cho lời gọi `log.debug(...)`. Biểu thức ghép chuỗi có thể chuyển các giá trị thành `String`, gọi `toString()` và tạo công việc không cần thiết. Nếu đoạn code chạy nhiều lần trong hot path, CPU/GC có thể tăng mà không đem lại log hữu ích.

Viết đúng hơn:

~~~java
// SLF4J/Log4j 2: truyền mẫu và đối số riêng.
log.debug("Order {} state={}", orderId, state);
~~~

Trong lời gọi sau, framework có cơ hội bỏ qua việc **định dạng** thông điệp khi DEBUG không được chấp nhận. Tuy nhiên, **các biểu thức tạo ra `orderId` và `state` vẫn phải được Java đánh giá**. Đây là điểm khác biệt quan trọng giữa *parameterized logging* và *lazy evaluation*.

Ví dụ tệ hơn:

~~~java
// expensiveSnapshot() chạy TRƯỚC lời gọi logger, dù DEBUG bị tắt.
log.debug("snapshot={}", expensiveSnapshot());
~~~

Muốn tránh gọi hàm đắt tiền khi level tắt, dùng `Supplier` hoặc guard phù hợp với API logging. Bài này phân biệt rõ ba vấn đề: **nối chuỗi**, **định dạng message**, và **tính đối số**.

## 2. Java đánh giá arguments trước khi gọi method

Quy tắc cơ bản của Java: trước khi một method được gọi, các biểu thức đối số phải được đánh giá theo thứ tự quy định. Vì vậy:

~~~java
log.debug("status=" + buildStatus());
~~~

về mặt thứ tự tính toán, có thể hình dung thành:

~~~java
String message = "status=" + buildStatus();
log.debug(message);
~~~

Dù bên trong `debug` kiểm tra level và trả về ngay, `buildStatus()` đã chạy. Điều này vẫn đúng nếu `buildStatus()` tốn CPU, truy vấn dữ liệu, có side effect hoặc có thể ném exception.

**Những điều không nên khẳng định tuyệt đối:**

- Không phải mọi dấu `+` đều tạo nhiều `StringBuilder` như thời Java cũ. Java 9+ có cơ chế tối ưu string concatenation thường dùng `invokedynamic`/`StringConcatFactory`; chi tiết do compiler/JIT quyết định.
- Với phép nối **toàn hằng số**, compiler có thể gộp thành một constant; đó thường **không** phải vấn đề.
- JIT có thể tối ưu một số allocation, nhưng không được tự ý bỏ những phép tính có hiệu ứng quan sát được như tăng counter, gọi I/O hoặc ném lỗi.
- “Có nối chuỗi” không tự chứng minh ứng dụng chậm đáng kể. Phải xem **tần suất, kích thước message, chi phí chuyển đổi và số event bị lọc**.

Anti-pattern thực sự là **tạo dữ liệu chỉ để log khi không cần nó**, chứ không phải cấm mọi toán tử `+` trong toàn bộ code Java.

## 3. Những tình huống dễ bị bỏ sót

| Code thường gặp | Việc xảy ra trước khi logger kiểm tra level | Rủi ro |
| --- | --- | --- |
| `log.debug("id=" + id)` | Nối chuỗi và chuyển `id` sang text | CPU/allocation khi DEBUG off |
| `log.debug("user={}", user.toString())` | Gọi `toString()` | Tạo chuỗi lớn, có thể lộ trường nhạy cảm |
| `log.debug("state={}", calculateState())` | Chạy `calculateState()` | Chi phí hoặc side effect dù event bị drop |
| `log.debug(String.format("n=%d", n))` | Format string trước | Locale/conversion/cấp phát không cần |
| `log.debug("json=" + serialize(dto))` | Serialize cả object | CPU, memory, exception và lộ dữ liệu |
| `log.trace("items=" + items.stream().map(...).toList())` | Chạy stream pipeline | Tính dữ liệu thừa, gây allocation |
| `log.info("report=" + new StringBuilder().append(...))` | Xây message sớm | Builder không làm logger lazy |
| `MDC.put("details", expensive())` | Tính và lưu thread context ngay | Log off vẫn tốn; context có thể bị lộ |
| `log.debug("size={}", size)` | Chỉ đọc một biến đơn giản | Thường nhẹ; tối ưu chủ yếu ở formatting |
| `log.debug("name={}", name)` | Truyền một `String` sẵn có | Trường hợp phù hợp parameterized logging |

Một lỗi dễ gặp khi review: thấy dấu `{}` rồi kết luận mọi thứ đã lazy. Nếu argument vẫn là `repository.findAll()` hoặc `objectMapper.writeValueAsString(...)`, chi phí tính **đối số** có thể còn nguyên.

## 4. Chi phí không chỉ là một chuỗi bị bỏ đi

Một câu log không được xuất có thể vẫn tiêu tốn:

1. **CPU:** tính biểu thức, gọi `toString()`, format ngày/số, serialize JSON, sort/stream dữ liệu.
2. **Bộ nhớ tạm:** strings, arrays, wrapper objects và buffers; mức allocation thực tế phụ thuộc compiler/JIT.
3. **GC pressure:** nhiều object ngắn hạn có thể tăng số lần thu gom rác.
4. **I/O ngoài ý muốn:** nếu hàm dựng message đọc file, gọi API, database hoặc truy vấn trạng thái.
5. **Side effects:** tăng counter, mutate cache hoặc làm thay đổi state do một lời gọi “chỉ để debug”.
6. **Lỗi không đáng có:** hàm tính message ném exception dù logging level đang tắt.
7. **Lộ dữ liệu:** chuyển DTO/thông tin bí mật thành text ở tầng không được kiểm soát.

Trong code xử lý một request hiếm, chi phí một phép nối đơn giản có thể không đáng kể. Nhưng ở vòng lặp 100.000 events/giây, việc gọi serializer để rồi bỏ toàn bộ message là một vấn đề kiến trúc và hiệu năng.

**Phân biệt hai pha:** chuyển dữ liệu domain thành giá trị argument là trách nhiệm code Java; format template và render sang sink thuộc API/backend. Sửa pha sau bằng placeholder không tự giải quyết pha trước.

## 5. Trước và sau: SLF4J (Logback hoặc provider khác)

SLF4J dùng cú pháp `{}`. Ví dụ từ lời gọi bình thường:

~~~java
// BAD: ghép chuỗi trước lời gọi logger.
log.debug("order " + orderId + " status " + status);

// BETTER: truyền các giá trị đã có sẵn.
log.debug("order {} status {}", orderId, status);
~~~

Nếu DEBUG không được chấp nhận, phương án sau thường không cần dựng thông điệp đầy đủ. Nhưng:

~~~java
// STILL EAGER: queryState() vẫn chạy dù debug off.
log.debug("order status={}", queryState(orderId));
~~~

Với chi phí đắt, có thể guard:

~~~java
if (log.isDebugEnabled()) {
    String state = queryState(orderId);
    log.debug("order status={}", state);
}
~~~

Đây là các **đoạn minh họa**, không phải class Java độc lập: `log` là `org.slf4j.Logger` đã khởi tạo, các biến và hàm domain phải tồn tại.

**Giới hạn của guard:** `isDebugEnabled()` chủ yếu trả lời level tương ứng. Backend có thể còn filter theo marker/appender/sink và vẫn loại event sau đó; không được tuyên bố guard là một cơ chế “chỉ tính khi mọi filter cuối cùng chấp nhận”. Nó giúp tránh phần chi phí lớn khi level chắc chắn tắt.

**Đừng guard mọi dòng log.** Với một vài arguments rẻ, placeholder thường gọn, dễ đọc và hiệu quả đủ tốt. Guard hợp lý khi biểu thức rất tốn chi phí hoặc gây side effect không mong muốn.

## 6. SLF4J 2.x Fluent API: Supplier cho argument đắt

SLF4J 2.x cung cấp `LoggingEventBuilder`. Khi level tắt, builder trả về có hành vi không làm gì; API hỗ trợ `Supplier` cho các argument đắt:

~~~java
// SLF4J 2.x; giả định log và orderId đã có.
log.atDebug()
        .setMessage("order={} snapshot={}")
        .addArgument(orderId)
        .addArgument(() -> buildSnapshot(orderId))
        .log();
~~~

**Điểm then chốt:** `buildSnapshot(orderId)` nằm **bên trong lambda**, không được gọi ngay khi tạo argument. Khi event bị tắt, Supplier không cần tạo snapshot.

**Không nhầm hai đoạn sau:**

~~~java
// BAD: đã gọi hàm trước khi đưa vào builder.
log.atDebug().addArgument(buildSnapshot(orderId))
        .log("snapshot={}");

// GOOD: đưa Supplier vào builder.
log.atDebug().addArgument(() -> buildSnapshot(orderId))
        .log("snapshot={}");
~~~

Fluent API phải kết thúc bằng `log()`. Nếu chỉ gọi `atDebug().addArgument(...)` và quên `log()`, event không được phát ngay cả khi DEBUG bật.

Nhớ kiểm tra version và provider:

- `atDebug()`, `addArgument(Supplier<?>)` cần **SLF4J 2.x**, không áp dụng như nhau với SLF4J 1.7.
- Cú pháp `log.debug("snapshot={}", () -> expensive())` trong SLF4J classic **không mặc nhiên** làm argument trở thành Supplier được đánh giá muộn. Dùng API Fluent được hỗ trợ hoặc guard.
- Lazy không có nghĩa giá trị an toàn về bảo mật. Khi log được bật, Supplier vẫn có thể sinh secret/PII; phải dùng schema/redaction đúng policy.

## 7. JUL (java.util.logging): dùng `{0}` và Supplier

`java.util.logging.Logger` có sẵn trong JDK. JUL **không** dùng `{}` của SLF4J để format message; các formatter thông thường dùng `java.text.MessageFormat` với placeholders `{0}`, `{1}`...

~~~java
// BAD: nối chuỗi trước khi gọi Logger.
LOG.fine("id=" + id + " state=" + state);

// BETTER: giữ template và parameters riêng.
LOG.log(java.util.logging.Level.FINE,
        "id={0} state={1}", new Object[]{id, state});
~~~

Nhưng nếu truyền một hàm trực tiếp:

~~~java
// EAGER: hàm đã chạy trước khi Logger.log nhận đối số.
LOG.log(java.util.logging.Level.FINE, "details={0}", expensiveDetails());
~~~

thì việc tính vẫn diễn ra lúc FINE tắt.

JUL có overload dùng `Supplier<String>`:

~~~java
// LAZY: chỉ tạo string nếu level được chấp nhận.
LOG.fine(() -> "details=" + expensiveDetails());

// Cũng hợp lệ:
LOG.log(java.util.logging.Level.FINE,
        () -> "details=" + expensiveDetails());
~~~

Các đoạn này giả định `LOG` kiểu `java.util.logging.Logger`. Ngoài việc lazy-build message, JUL còn overload `log(Level, Throwable, Supplier<String>)` giúp giữ exception dưới dạng `LogRecord.thrown`.

Đừng viết `LOG.log(Level.INFO, "id={}", id)` và trông chờ JUL thay `{}`; hãy dùng `{0}` theo quy tắc của JUL.

## 8. Ví dụ Java 17 chạy độc lập: chứng minh sự khác biệt

Ví dụ sau kiểm tra **hành vi có thể quan sát** thay vì đo thời gian: `expensiveSnapshot()` tăng counter mỗi lần nó thực sự được gọi. Test chạy hai giai đoạn: `FINE` bị tắt và sau đó được bật.

Tạo file **UnnecessaryConcatenationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class UnnecessaryConcatenationDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.unnecessary.concat");
    private static final AtomicInteger SNAPSHOTS = new AtomicInteger();

    private static String expensiveSnapshot() {
        return "snapshot-" + SNAPSHOTS.incrementAndGet();
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);
        try {
            LOG.setLevel(Level.INFO); // FINE is disabled.
            LOG.fine("concat=" + expensiveSnapshot());
            LOG.log(Level.FINE, "param={0}", expensiveSnapshot());
            LOG.fine(() -> "lazy=" + expensiveSnapshot());
            if (LOG.isLoggable(Level.FINE)) {
                LOG.fine("guard=" + expensiveSnapshot());
            }
            System.out.println("afterDisabled=" + SNAPSHOTS.get());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "lazy=" + expensiveSnapshot());
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            System.out.println("afterEnabled=" + SNAPSHOTS.get());
        } finally {
            LOG.removeHandler(handler);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 17+**:

~~~bash
javac --release 17 UnnecessaryConcatenationDemo.java
java UnnecessaryConcatenationDemo
~~~

**Standard output (stdout) chính xác:**

~~~text
afterDisabled=2
afterEnabled=3
~~~

**Standard error (stderr) chính xác:**

~~~text
FINE lazy=snapshot-3
INFO order=ORD-42 state=PAID
~~~

**Exit code:** `0` trong điều kiện chạy bình thường.

Tại sao lại có kết quả này?

- Giai đoạn `LOG.setLevel(Level.INFO)`: `FINE` đang tắt.
- `"concat=" + expensiveSnapshot()` gọi hàm, counter từ 0 → 1; message bị bỏ.
- `LOG.log(Level.FINE, "param={0}", expensiveSnapshot())` cũng gọi hàm trước, counter 1 → 2; message vẫn bị bỏ.
- `LOG.fine(() -> "lazy=" + expensiveSnapshot())` nhận lambda; vì FINE tắt, Supplier không chạy, counter vẫn 2.
- Khối `if (LOG.isLoggable(Level.FINE))` bị bỏ qua; counter vẫn 2.
- Khi bật FINE, cùng kiểu Supplier chạy thật; counter 2 → 3 và dòng `FINE lazy=snapshot-3` xuất hiện trên stderr.
- Dòng `INFO order=ORD-42 state=PAID` dùng `{0}`/`{1}`, chứng minh tham số JUL được định dạng sau khi message đi tới formatter.
- `ConsoleHandler` ghi stderr; chương trình in counter bằng `System.out.println` nên xuất hiện ở stdout.

**Giới hạn của thí nghiệm:** Counter xác minh **hàm được gọi bao nhiêu lần**, không đo số byte cấp phát, tốc độ Java JIT, throughput hay kết quả benchmark. `expensiveSnapshot()` trong ví dụ chỉ tăng counter, không cố tình truy vấn DB hoặc làm chậm hệ thống.

## 9. Kiểm thử có chất lượng nên chứng minh điều gì?

Một bài unit test cho anti-pattern này cần:

1. Khi DEBUG/FINE tắt, Supplier hoặc guard **không** gọi hàm đắt.
2. Khi level bật, thông điệp có nội dung và tham số đúng.
3. Khi level tắt, không có event ở sink; nhưng test vẫn xác minh sink hoạt động bằng một sự kiện INFO khác.
4. Khi thêm level/filter, event đi qua đúng tuyến; không nhầm message template với rendered message.
5. Khi ghi exception, Throwable còn được gắn đúng cấu trúc, không bị chuyển thành text.
6. Không phát sinh log chứa secret giả khi bật debug.
7. Không gây side effect kinh doanh khi thay đổi logging level.

Với JUL, có thể dùng Handler in-memory thu `LogRecord`; kiểm tra `getMessage()` (template), `getParameters()` (arguments) và `Formatter.formatMessage(record)` (rendered message).

Với Logback Classic, dùng `ListAppender<ILoggingEvent>`; với Log4j 2 Core, bắt `LogEvent` hoặc output của layout. Test cùng lúc **positive event** và **negative event** tránh việc appender chưa hoạt động khiến test PASS giả.

Đừng chỉ assert `expensiveCalls==0` mà không bật thử logging: có thể vô tình tạo một logger luôn tắt, khiến cả test và hệ thống không quan sát được lỗi thật.

## 10. Log4j 2: parameterized logging và Supplier

Trong Log4j 2 API, tránh:

~~~java
// BAD: eager concatenation.
LOGGER.debug("User " + userId + " role " + lookupRole(userId));
~~~

Với dữ liệu rẻ đã có sẵn, dùng message parameters:

~~~java
LOGGER.debug("User {} role {}", userId, role);
~~~

Nếu `lookupRole(userId)` tốn chi phí, đừng gọi trực tiếp trước lời gọi logger:

~~~java
// BAD: lookupRole được đánh giá trước khi LOGGER.debug chạy.
LOGGER.debug("User {} role {}", userId, lookupRole(userId));
~~~

Log4j 2 hỗ trợ Supplier cho arguments ở API thích hợp:

~~~java
// Log4j 2; LOGGER là org.apache.logging.log4j.Logger đã khởi tạo.
LOGGER.debug("User {} role {}", () -> userId, () -> lookupRole(userId));
~~~

Đây là **snippet phụ thuộc thư viện Log4j 2**, không phải code chạy được chỉ với JDK. Theo tài liệu Log4j 2, Supplier giúp tránh tính argument đắt nếu sự kiện bị loại trước khi cần materialize. Hành vi cụ thể có thể phụ thuộc filter và kiểu Message dùng trong phiên bản đang chạy; không thay bằng API SLF4J mà chưa kiểm tra overload.

Nếu có điều kiện phức tạp, guard vẫn có thể hữu ích:

~~~java
if (LOGGER.isDebugEnabled()) {
    LOGGER.debug("Detailed snapshot={}", buildSnapshot());
}
~~~

Nhưng guard chủ yếu kiểm tra level. Một event có thể còn bị filter bởi marker, appender hoặc policy khác. Đừng dựa vào guard để bảo đảm “chỉ thực thi nếu mọi backend cuối đều chấp nhận”.

## 11. Parameterized logging khác lazy argument computation thế nào?

| Biểu thức | Nối/format trước lời gọi? | Hàm đắt chạy khi level tắt? | Nhận xét |
| --- | --- | --- | --- |
| `log.debug("x=" + x)` | Có thể thực hiện concatenation trước lời gọi | Không có hàm đắt nếu `x` đã là biến | Tránh khi chỉ để log; dùng placeholder |
| `log.debug("x={}", x)` | Backend có thể trì hoãn format | Không có hàm đắt nếu `x` đã có | Thường là lựa chọn mặc định |
| `log.debug("x={}", expensive())` | Template chưa format sớm | **Có** | Placeholder không trì hoãn argument |
| `log.debug("x={}", x.toString())` | `toString()` chạy sớm | **Có** | Truyền object đã xét an toàn hoặc Supplier |
| `log.atDebug().addArgument(() -> expensive()).log("x={}")` | Theo SLF4J 2 Fluent | **Không** khi level off | Deferred Supplier |
| `if (log.isDebugEnabled()) log.debug("x={}", expensive())` | Chỉ vào block khi enabled | **Không** khi level off | Guard hiệu quả cho level, không thay mọi filter |
| `LOG.fine(() -> "x=" + expensive())` | JUL dựng message khi enabled | **Không** khi FINE off | Supplier message |
| `LOG.log(Level.FINE, "x={0}", expensive())` | JUL message template riêng | **Có** | Eager argument |
| `log.debug(String.format("x=%s", x))` | `String.format` chạy sớm | Có thể tốn CPU/cấp phát | Không phù hợp khi chỉ phục vụ log |

**Hai mục tiêu khác nhau:**

- Nếu đối số đã có sẵn: dùng **parameterized logging** để tránh nối/format sớm.
- Nếu đối số chưa có và tốn chi phí: dùng **Supplier** hoặc **level guard**, tránh tính trước.
- Nếu đối số chứa bí mật: không đưa vào logger dù có lazy hay không; ưu tiên loại trường/mask từ nguồn.

## 12. `String.format`, `MessageFormat`, JSON serialization và `toString()`

Một số dạng “nối chuỗi không cần thiết” không chứa toán tử `+`:

~~~java
// BAD nếu dùng chỉ để DEBUG.
log.debug(String.format("batch=%d size=%d", batchNo, size));
log.debug("payload=" + mapper.writeValueAsString(dto));
log.debug("graph={}", domainGraph.toString());
log.debug("report={}", expensiveReport());
~~~

Các biến/hàm ở đây chỉ là ví dụ, cần được định nghĩa trong ứng dụng. `mapper.writeValueAsString` phụ thuộc Jackson và có thể ném exception; không phải API logging.

**Tác động:**

- `String.format` xây chuỗi **trước** lời gọi logger; có chi phí format/locale khác với pattern của backend.
- `MessageFormat.format(...)` cũng chạy ngay nếu bạn chủ động gọi trước.
- Serialize JSON một object lớn thường đắt hơn nối một vài số và còn có nguy cơ chứa PII.
- `toString()` có thể tự đi qua toàn bộ collection/domain graph, kích hoạt logic ngoài ý muốn hoặc vô tình chứa credential.
- `Arrays.toString`, `Collectors.joining` hay `StringBuilder` đều là tính toán sớm nếu chạy ngoài Supplier/guard.

Thay vì serialize raw DTO, log metadata đã chuẩn hóa như `eventCode`, `entityRef`, `fieldCount` hoặc `payloadBytes` theo chính sách. Chỉ bật full diagnostic ở môi trường và quyền thích hợp, có giới hạn kích thước.

## 13. Vì sao không nên dùng `StringBuilder` để “sửa” logging?

Đôi khi một code review thay:

~~~java
log.debug("id=" + id + " state=" + state);
~~~

bằng:

~~~java
log.debug(new StringBuilder()
        .append("id=").append(id)
        .append(" state=").append(state)
        .toString());
~~~

Cách này **không giải quyết anti-pattern**: `StringBuilder` vẫn được dựng và `toString()` vẫn được gọi trước khi `debug(...)` nhận đối số.

Với Java 17, compiler/JIT có thể tối ưu nối `+` rất tốt; `StringBuilder` thủ công thậm chí làm code dài và phức tạp hơn. Nên:

~~~java
log.debug("id={} state={}", id, state);
~~~

Nếu dữ liệu cần tính trước rất đắt, bổ sung Supplier/guard đúng framework. Không tự benchmark chỉ bằng một vòng lặp chưa warmup rồi kết luận `StringBuilder` nhanh/chậm hơn `+` trong mọi workload.

## 14. Tham số số, object, boxing và chi phí nhỏ

Dù parameterized logging giúp tránh **format string**, chi phí không nhất thiết bằng 0.

- Một số overload có thể dùng varargs `Object...` và mảng tạm.
- Primitive có thể bị boxing tùy overload và cách compiler/backend triển khai.
- Wrapper, marker, context hoặc logging event có thể vẫn được tạo khi level bật.
- Async appender có queue/ring buffer và overhead khi đẩy event.
- Một object argument có thể được giữ đến lúc formatter/encoder xử lý ở thời điểm muộn.

**Không tối ưu mù quáng một dòng `log.debug("count={}", count)`** nếu count đã có sẵn và profiler không cho thấy vấn đề. Tối ưu quan trọng thường là bỏ I/O, gọi service, serialize JSON hoặc duyệt collection chỉ vì log đang tắt.

Với log mức INFO/WARN luôn bật, parameterized logging vẫn có lợi về tính nhất quán message template và structured processing, nhưng backend thường vẫn phải materialize output ở một thời điểm.

## 15. Logging bất đồng bộ và object mutable

Parameterized logging có thể chuyển arguments cho backend trước khi message được render. Trong pipeline async, **cẩn thận với object mutable**:

~~~java
// Minh họa: payload có thể tiếp tục bị thay đổi sau khi enqueue event.
log.debug("payload={}", mutablePayload);
mutablePayload.clear();
~~~

Trong một số backend/layout, message có thể được format trước khi enqueue; ở số khác có thể xảy ra muộn hơn. Không dựa vào một giả định chung về **thời điểm `toString()` được gọi** cho mọi backend/version.

Hướng xử lý:

1. Nếu cần log giá trị tại một mốc nhất định, tạo **snapshot an toàn và bất biến**.
2. Nếu snapshot đắt, tạo trong Supplier/guard **khi phù hợp ngữ nghĩa event**.
3. Nếu xử lý đa luồng, không dùng lambda đọc một object mutable mà state có thể thay đổi trước khi evaluation.
4. Không truyền nguyên DTO chứa dữ liệu nhạy cảm vào async logger để trông chờ sink mask sau.
5. Benchmark và test với backend/config async thực, không chỉ mock logger.

**Lazy không tự bảo đảm snapshot semantics.** Việc trì hoãn quá muộn có thể làm message phản ánh state khác thời điểm sự kiện. Phải cân bằng độ chính xác quan sát và chi phí.

## 16. Exception và stack trace: đừng ghép Throwable thành text

Anti-pattern khác:

~~~java
// BAD: chuyển Throwable thành một chuỗi, có thể mất stack trace cấu trúc.
log.error("payment failed: " + exception);
~~~

Với SLF4J/Logback hoặc Log4j 2, ưu tiên để `Throwable` được truyền ở tham số/overload dành cho exception:

~~~java
// Các biến log, orderId, exception đã được khai báo.
log.error("payment failed for order={}", orderId, exception);
~~~

Thông thường backend nhận exception trong trường Throwable riêng, cho phép renderer xử lý stack trace và cause. Với JUL:

~~~java
LOG.log(java.util.logging.Level.SEVERE, "payment failed", exception);
~~~

Khi chỉ cần message sinh muộn cùng Throwable, JUL cũng có overload:

~~~java
LOG.log(java.util.logging.Level.SEVERE, exception,
        () -> "payment failed order=" + safeOrderRef);
~~~

Các đoạn trên dùng logger tương ứng và có biến an toàn. **Không** gọi `exception.getMessage()`, `exception.toString()` hay serialize toàn stack trace trước khi biết level; exception message cũng có thể chứa bí mật, URL có token hoặc dữ liệu cá nhân.

**Quan trọng:** Có log exception đầy đủ hay không là quyết định về bảo mật và vận hành. Nếu kênh phổ thông không được phép chứa thông tin nhạy cảm, dùng mã lỗi và một kênh điều tra hạn chế quyền. Không dùng lazy Supplier làm lý do để log dữ liệu cấm.

## 17. Structured logging: đừng đánh mất field bằng cách nối chuỗi

Nếu một hệ thống có Elasticsearch/OpenSearch, Loki hay OpenTelemetry Collector, chuỗi:

~~~text
"order=" + id + " state=" + state
~~~

thường kém hữu ích hơn sự kiện có field rõ. Structured logging giúp query theo **`event.code`, `order_ref`, `outcome`, `trace_id`** mà không cần regex cố tách text.

Ví dụ SLF4J 2 Fluent:

~~~java
log.atInfo()
        .addKeyValue("eventCode", "ORDER_PAID")
        .addKeyValue("orderRef", safeOrderRef)
        .addKeyValue("outcome", "SUCCESS")
        .log("order state changed");
~~~

Đây là snippet SLF4J 2.x. **Key-value có được xuất thành JSON field độc lập hay không phụ thuộc provider/layout**; cần kiểm tra encoder/backend. Không đưa secret vào `addKeyValue` hoặc MDC và giả định parser sẽ che chúng.

Nếu cần tính một object đắt cho structured field, hãy xem API Supplier/guard phù hợp và đánh giá mục đích. Tránh ghép tất cả fields thành một String `message` rồi cho rằng Collector sẽ parse ổn định mãi.

## 18. Bảo mật và log injection liên quan gì đến nối chuỗi?

Một hậu quả ngoài hiệu năng là khi nối chuỗi với dữ liệu **không tin cậy**:

~~~java
// Rủi ro: raw input có thể chứa CR/LF và làm giả dòng log.
log.info("login input=" + rawUserInput);
~~~

Nếu `rawUserInput` chứa newline, một text line log có thể bị tách thành nhiều dòng và đánh lừa người đọc hoặc parser. Với dữ liệu khác, `toString()` có thể lộ email, API key, password hoặc body request.

Ưu tiên:

- Không log password, OTP, session token, bearer token, API key hoặc private key.
- Dùng event code, reason code từ **allowlist** thay raw request.
- Dùng JSON encoder chuẩn và escape control chars.
- Giới hạn kích thước dữ liệu để tránh log amplification.
- Mask/loại dữ liệu nhạy cảm **trước** lời gọi logger; dùng redaction tại sink làm lớp phụ.
- Test với sentinel giả (ví dụ `TEST_SECRET_DO_NOT_LOG`) để khẳng định output không lộ.
- Đừng dùng nối chuỗi để “cứu” lỗi serialization bằng cách dump toàn bộ DTO.

Parameterized logging giảm thao tác tạo chuỗi sớm, nhưng **không tự làm dữ liệu trở nên an toàn**. Cần kiểm soát cả message, args, Throwable, MDC và các trường structured.

## 19. Tối ưu có đo lường: JFR, profiler và JMH

Chỉ nên ưu tiên tối ưu khi có bằng chứng về CPU, latency, allocation hoặc log volume.

**Cách làm thực tế:**

1. Xác định hot paths có nhiều lời gọi DEBUG/TRACE khi các level này thường tắt.
2. Dùng profiler/Java Flight Recorder (JFR) để xem thời gian ở `toString()`, JSON serialization, formatter, string concatenation và allocation pressure.
3. Bắt các trường hợp gọi hàm ngoài ý muốn bằng unit test counter như phần 8.
4. Dùng **JMH** để benchmark nhỏ, kiểm soát warmup, fork, JDK, logger backend, filter, mức log và sink.
5. So các biến thể **trong cùng điều kiện**: nối sớm, placeholders, guard, Supplier; đo cả enabled và disabled cases.
6. Tránh benchmark một vòng lặp mà JIT có thể loại bỏ toàn bộ tác vụ hoặc chỉ đo tốc độ `System.nanoTime()`.
7. Đánh giá throughput/latency của ứng dụng cuối, không tối ưu một logger làm khó bảo trì nếu lợi ích không đáng kể.

**Sai lầm trong benchmark:**

- Gửi log thật ra console khi đo logging disabled và active ở mức không tương đương.
- Không warmup/JIT, không kiểm soát GC hoặc terminal I/O.
- Đổi quá nhiều tham số cùng lúc (backend, appender, template, args).
- Chỉ đo thời gian nhưng bỏ qua số lần tính `expensive()` và allocation.
- Khẳng định “zero allocation” cho mọi máy từ một lần chạy.

Đối với Log4j 2, tài liệu về garbage-free logging khuyến nghị chỉ tối ưu sâu khi logging thực sự là bottleneck và nên đo lại giả định theo phiên bản/hệ thống.

## 20. Quy tắc chọn cách viết theo tình huống

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Một giá trị `String` đã có sẵn, DEBUG off | `log.debug("id={}", id)` | Không format sớm |
| Nhiều biến primitive/immutable | Template `{}` hoặc JUL `{0}` | Dễ đọc, nhất quán |
| Gọi DB/HTTP chỉ để log | Tránh gọi; chỉ thực hiện nếu thực sự cần và được phép | Logging không nên thêm I/O đắt |
| Dump collection lớn khi debug | Guard hoặc Supplier với giới hạn kích thước | Chỉ tính khi cần |
| Tạo JSON chỉ để log | Ưu tiên structured event, encoder backend | Giảm serialize thủ công |
| Cần lazy message ở JUL | `LOG.fine(() -> ... )` | JDK hỗ trợ trực tiếp |
| Cần lazy argument ở SLF4J 2 | Fluent `addArgument(() -> ...)` | Deferred Supplier được hỗ trợ |
| Cần lazy argument ở Log4j 2 | Supplier overload đúng API | Tránh eager expensive call |
| Throwable gắn với lỗi | Dùng overload/parameter Throwable | Giữ exception cấu trúc |
| Audit event bắt buộc | Recorder/pipeline theo chính sách audit | Không phụ thuộc DEBUG sampling |
| Dữ liệu nhạy cảm | Omit/mask/allowlist trước logger | Tối ưu không thay bảo mật |

**Ưu tiên đơn giản trước:** viết placeholder cho dữ liệu sẵn có, thêm Supplier/guard ở những biểu thức đắt tiền. Không biến toàn bộ codebase thành những lambda phức tạp chỉ để tiết kiệm một phép nối nhỏ.

## 21. Kiểm thử unit và kiểm tra static analysis

Một số tiêu chí review/code scanning hữu ích:

- Lời gọi `logger.debug/trace/fine` có chuỗi `"x=" + value` ngay trong đối số không?
- Có `String.format(...)`, `MessageFormat.format(...)` hoặc `JsonSerializer...` trong lời gọi log?
- Có `.toString()` hoặc phép nối `+` trên DTO/collection lớn?
- Có database/network call trong đối số log?
- Có điều kiện `isDebugEnabled` nhưng lại tính các giá trị **trước** khối `if`?
- Có lazy Supplier bị đặt sai, ví dụ `() -> alreadyComputedExpensiveString`?
- Có dùng JUL `{}` hoặc SLF4J `{0}` không tương thích template?
- Có logger facade đúng, provider/backend đúng phiên bản không?
- Có mất Throwable do nối thành text?
- Có raw PII hoặc secret đi vào message/args/MDC không?

Tooling như IntelliJ inspections, Sonar rules hay lint plugin có thể báo những lời gọi nối chuỗi vô ích, nhưng **static analysis không biết mọi side effect và quy tắc nghiệp vụ**. Kết hợp code review, test counter và profiling.

**Test đúng hướng:** một test xác nhận `expensiveCalls==0` khi DEBUG off, một test xác nhận đúng message khi DEBUG on, một privacy test xác nhận secret sentinel vắng mặt **trong event và sink**.

## 22. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “JDK 17 tối ưu `+` nên không sao” | JIT không được bỏ side effects của method tính đối số | Dùng placeholders/Supplier/guard |
| “Có `{}` là lazy toàn bộ” | Argument expression vẫn được Java đánh giá | `Supplier` hoặc `isDebugEnabled` |
| Chỉ đổi `+` thành `StringBuilder` | Vẫn dựng string trước call | Truyền template và args |
| Truyền `expensive()` trực tiếp vào SLF4J | Hàm chạy khi DEBUG off | SLF4J 2 Fluent Supplier hoặc guard |
| Dùng JUL `{}` | JUL formatter dùng `{0}` | Chọn đúng API |
| Tính snapshot trước `if` | Guard không bảo vệ phần tính đã chạy | Đưa tính toán vào trong guard |
| Chụp object mutable trong lambda | Giá trị có thể khác lúc log event | Snapshot bất biến khi cần |
| Quên `.log()` trong Fluent API | Không phát event | Kết thúc chain đúng |
| Dùng `getMessage()` để so text đã format ở JUL | `getMessage` giữ template | Dùng `Formatter.formatMessage` |
| Nối `exception` vào String | Có thể mất stack trace/Throwable field | Truyền exception bằng overload đúng |
| Dump raw object trong DEBUG | Khi bật DEBUG có thể lộ secret | Allowlist/mask dữ liệu |
| Guard mọi dòng log | Code rối, lợi ích nhỏ khi args rẻ | Tối ưu theo profiler |
| So tốc độ bằng một vòng lặp chưa warmup | JIT/GC ảnh hưởng kết quả | JMH và test end-to-end |
| Coi log disabled là không tốn một đồng nào | Vẫn có check-level/argument setup | Nhận diện giới hạn, đo khi cần |
| Tự giả định zero-GC từ placeholders | Tùy overload, backend và JIT | Đo allocation trên cấu hình thật |
| Tối ưu log nhưng làm sai nghiệp vụ | Side-effect/log timing thay đổi | Không đặt logic nghiệp vụ trong message expression |

## 23. Checklist áp dụng trước khi merge code

1. Có code log `"prefix" + value` chỉ để debug/trace không?
2. Message dùng template tương thích framework (JUL `{0}`, SLF4J/Log4j 2 `{}`) không?
3. Những argument có thực sự **đã được tính sẵn** hay đang gọi hàm tốn chi phí?
4. Với hàm đắt, có dùng Supplier/guard đúng API/version không?
5. Có tránh gọi DB/network hoặc serialize payload lớn chỉ để ghi log không?
6. Có tách chi phí tính domain dữ liệu cần thiết cho nghiệp vụ khỏi dữ liệu chỉ phục vụ log không?
7. Có kiểm tra logger/filter levels ở runtime và tránh disabled-event side effects không?
8. Có dùng overload Throwable thay vì nối exception thành text không?
9. Khi async, giá trị được snapshot đúng thời điểm và không bị mutable race không?
10. Dữ liệu được log có nằm trong danh sách cho phép, không lộ credentials/PII không?
11. Có assert template, formatted message, args, level và Supplier behavior khi test không?
12. Có benchmark/profiler trước khi tối ưu vi mô không?
13. Có phân biệt “ít nối chuỗi hơn” với “tối ưu tổng lượng log và I/O” không?
14. Có giữ code đơn giản và tránh tạo abstraction rườm rà chỉ để log một biến sẵn có không?

## 24. Bài tập và câu hỏi tự kiểm tra

**Bài tập A — nhận diện:** Với `DEBUG` tắt, đoạn nào vẫn gọi `createSnapshot()`?

~~~java
// SLF4J.
log.debug("snapshot=" + createSnapshot());       // A1
log.debug("snapshot={}", createSnapshot());       // A2
if (log.isDebugEnabled()) {
    log.debug("snapshot={}", createSnapshot());   // A3
}
log.atDebug().addArgument(() -> createSnapshot())
        .log("snapshot={}");                      // A4, SLF4J 2.x
~~~

**Đáp án:** A1 và A2 vẫn gọi. A3 tránh gọi vì guard false. A4 tránh gọi với Fluent Supplier khi level disabled. A3/A4 không đảm bảo bỏ tính nếu những filter khác ở tầng sau loại event.

**Bài tập B — sửa code:** Từ `LOG.fine("users=" + users.stream().map(...).toList())` hãy chọn một hướng an toàn:

- Nếu chỉ cần số lượng đã có sẵn, log `LOG.log(Level.FINE, "userCount={0}", count)`.
- Nếu thực sự cần danh sách và được phép, dùng `LOG.fine(() -> "users=" + safeSummary(users))` và giới hạn danh sách/độ dài.
- Không tạo full raw user records nếu chúng chứa PII. Trong môi trường async, snapshot nguồn dữ liệu phù hợp trước khi gửi đến worker.

**Bài tập C — chạy Java 17:** Thay `LOG.setLevel(Level.INFO)` trong chương trình ở phần 8 bằng `Level.FINE` ngay từ đầu. Dự đoán số lần `expensiveSnapshot()` và số dòng stderr. So với chạy gốc để hiểu khác nhau giữa gọi trực tiếp và Supplier.

**Bài tập D — đo lường:** Dùng profiler/JFR hoặc JMH trên ứng dụng giả lập nhiều lần gọi DEBUG bị tắt; so số lần `expensive()` chạy, allocations và throughput giữa nối chuỗi, placeholders, Supplier và guard. Không kết luận chỉ dựa vào một máy.

### Câu hỏi nhanh

1. Java có kiểm tra level logging trước khi tính argument của một method call không?
2. Parameterized logging có trì hoãn `expensive()` khi nó được truyền như một đối số thông thường không?
3. Vì sao compiler dùng `StringConcatFactory` không giải quyết mọi chi phí nối chuỗi ở log disabled?
4. JUL dùng `{0}` hay `{}` cho template thông thường?
5. SLF4J 2 hỗ trợ Supplier ở vị trí nào trong Fluent API?
6. Vì sao quên `.log()` khiến fluent builder không phát event?
7. Dùng `StringBuilder` có tự tạo lazy logging không?
8. Tại sao không nên assert mọi cách nối chuỗi tạo chính xác N allocations?
9. Khi xử lý exception, vì sao không nên nối `exception.toString()` vào message?
10. Khi log bật, lazy Supplier có tự bảo đảm không lộ PII không?
11. `isDebugEnabled()` có bảo đảm mọi appender filter cuối đều nhận event không?
12. Khi dùng AsyncAppender, vì sao cần cẩn thận với mutable arguments?

**Gợi ý:** (1) không; (2) không; (3) các hàm có side effects vẫn chạy trước lời gọi; (4) `{0}`; (5) `addArgument(() -> ...)`; (6) chưa commit event; (7) không; (8) compiler/JIT/backend khác nhau; (9) mất Throwable cấu trúc và có thể lộ secret; (10) không; (11) không; (12) event có thể được render muộn hơn state bị sửa.

## 25. Tài liệu chính thức để đọc tiếp

- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): level check, `log(Level, Supplier<String>)`, `fine(Supplier<String>)`, tham số và Throwable.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)` và `MessageFormat`.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message, arguments, Throwable và metadata.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): string concatenation và lưu ý implementation.
- [Java SE 17 — StringConcatFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): cơ chế tối ưu phép nối chuỗi trong JVM.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, Fluent API 2.x và Supplier arguments.
- [Apache Log4j 2 — Logging API](https://logging.apache.org/log4j/2.x/manual/api.html): tránh nối chuỗi, Supplier và lập trình logging đúng ngữ nghĩa.
- [Apache Log4j 2 — Garbage-free logging](https://logging.apache.org/log4j/2.x/manual/garbagefree.html): allocation, GC và lời khuyên tối ưu có đo lường.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): framework benchmark micro cho Java.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nhạy cảm, log injection và các yêu cầu bảo mật.
