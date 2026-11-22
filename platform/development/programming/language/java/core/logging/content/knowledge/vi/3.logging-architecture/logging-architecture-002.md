# Logger tiếp nhận log trong kiến trúc Java Logging

## 1. Logger là điểm tiếp nhận sự kiện

Trong kiến trúc logging, **Logger** là đối tượng mà mã ứng dụng gọi khi muốn thông báo một sự kiện: thao tác bắt đầu, xử lý thành công, cảnh báo, lỗi, hoặc thông tin chẩn đoán. Logger nhận yêu cầu ghi log, kiểm tra xem sự kiện có được phép đi tiếp hay không, tạo hoặc tiếp nhận bản ghi log và chuyển bản ghi hợp lệ đến thành phần xử lý đầu ra.

Điểm cần phân biệt: **gọi logger không đồng nghĩa với log đã được ghi thành công ra file, console hoặc hệ thống tập trung**. Logger là cửa vào của pipeline; **Handler** trong `java.util.logging` (JUL), hoặc **Appender** trong nhiều logging backend khác, mới chịu trách nhiệm chuyển dữ liệu sang đích xuất. Formatter/Encoder quyết định cách biểu diễn. Logging bất đồng bộ, buffer, lỗi I/O và chính sách filter có thể làm bản ghi không xuất hiện ở đích.

Mô hình tổng quát:

```text
Mã ứng dụng (business logic)
        |
        | logger.info(...), logger.log(...)
        v
      Logger
        |-- Kiểm tra level hiệu lực của logger
        |-- Tạo/tiếp nhận LogRecord hoặc event tương đương
        |-- Kiểm tra Logger Filter (nếu có)
        v
   Handler/Appender (có thể nhiều đích)
        |-- Kiểm tra level/filter riêng
        |-- Formatter/Encoder
        v
 console / file / queue / hệ thống thu thập log
```

Trong **JUL**, một `LogRecord` có thể còn được chuyển đến handler của các logger cha nếu tính năng dùng parent handlers đang bật. Đây là **nhánh chuyển tiếp**, không phải một lần gọi logger mới từ ứng dụng. Thứ tự và cơ chế chính xác thay đổi giữa JUL, Logback, Log4j 2 và các backend khác; sơ đồ trên thể hiện các trách nhiệm chung, còn các ví dụ Java dưới đây sử dụng JUL tích hợp sẵn trong JDK 17.

**Khi nào cần hiểu Logger?** Khi không thấy log dù đã gọi `info()`, khi thấy một sự kiện bị ghi hai lần, khi muốn bật DEBUG/FINE cho đúng thành phần, khi log lẫn thông tin của nhiều request, hoặc khi cần bảo đảm logger không trở thành nút thắt hiệu năng.

## 2. Phân biệt các thành phần của pipeline

| Thành phần | Trách nhiệm chính | Câu hỏi nó trả lời |
| --- | --- | --- |
| Mã gọi logger | Xác định sự kiện nào đáng ghi, cấp độ và dữ liệu ngữ cảnh | “Điều gì vừa xảy ra?” |
| Logger | Tiếp nhận lời gọi, áp dụng điều kiện cho phép ghi, tạo/chuyển tiếp event | “Sự kiện này có được đưa vào luồng logging không?” |
| LogRecord/event | Mang nội dung, level, tham số, ngoại lệ và metadata | “Một sự kiện log bao gồm những gì?” |
| Filter | Chấp nhận hoặc loại bỏ một bản ghi theo quy tắc | “Bản ghi này có được thông qua không?” |
| Handler/Appender | Nhận event và xuất ra một hoặc nhiều đích | “Log sẽ được chuyển đi đâu?” |
| Formatter/Encoder | Chuyển event sang dòng text, JSON hoặc định dạng khác | “Log được biểu diễn như thế nào?” |
| Log collector/storage | Tiếp nhận, lưu, lập chỉ mục, tìm kiếm, áp dụng retention | “Tìm lại log ở đâu và giữ bao lâu?” |

**JUL và SLF4J không cùng vai trò.** `java.util.logging.Logger` là logger thuộc API/triển khai JUL đi cùng JDK. `org.slf4j.Logger` thuộc **SLF4J**, một API facade; ứng dụng gọi SLF4J và backend được cấu hình (ví dụ Logback hoặc Log4j 2 qua binding/provider phù hợp) mới thực hiện pipeline tương ứng. Không mặc định mọi backend dùng `LogRecord`, `Handler` hoặc quy tắc level inheritance giống JUL.

Một cách chia trách nhiệm tốt là: code nghiệp vụ chọn **thông điệp và ngữ cảnh**, cấu hình logging chọn **mức, filter, định dạng và đích xuất**. Nhờ đó việc thay đổi file log hay cấu trúc JSON không buộc sửa toàn bộ code nghiệp vụ.

## 3. Quá trình Logger tiếp nhận một lời gọi

Ví dụ một phương thức xử lý thành công:

```java
logger.log(
        Level.INFO,
        "event=order.created orderId={0}",
        orderId
);
```

Đoạn trên là **một phần mã**, giả sử đã có biến `Logger logger` và `orderId`; ví dụ chương trình đầy đủ ở mục 7.

Đối với lời gọi thông thường trong JUL, có thể diễn giải lần lượt:

1. **Ứng dụng tạo yêu cầu ghi log:** chọn level, message hoặc message supplier, tham số, ngoại lệ nếu có. Các biểu thức Java được truyền làm đối số đã được đánh giá trước khi phương thức logger được gọi, trừ phần công việc được hoãn bằng `Supplier`.
2. **Logger kiểm tra level hiệu lực:** nếu level bị tắt, lời gọi kết thúc mà không xuất event. `isLoggable(Level)` giúp kiểm tra khả năng bật log theo mức, nhưng không bảo đảm các filter/handler phía sau sẽ chấp nhận.
3. **Tạo hoặc tiếp nhận `LogRecord`:** bản ghi có level, message, logger name và có thể có parameters, throwable, thông tin nguồn và thời gian. Với các overload khác nhau, thời điểm tạo bản ghi có thể khác nhau; không nên dựa vào việc mọi overload luôn tạo `LogRecord` trước hoặc sau đúng cùng một bước.
4. **Logger Filter (nếu cấu hình) quyết định tiếp tục hay bỏ:** đây là phép lọc bổ sung so với level.
5. **Phân phối tới các Handler:** mỗi handler tự kiểm tra level và filter rồi xuất hoặc bỏ bản ghi; logger có thể chuyển cùng bản ghi lên handler ở ancestor khi `useParentHandlers=true`.
6. **Formatter và đích xuất xử lý:** message pattern/parameters được định dạng, lỗi có thể kèm stack trace, dữ liệu được ghi/đưa vào buffer theo cơ chế handler. Thành công ở bước 1–5 chưa chứng minh đích lưu trữ đã nhận bền vững.

Có thể hình dung các nhánh lọc:

```text
logger.log(...)
    |
    v
Logger có cho phép level? -- không --> bỏ qua
    |
   có
    v
Logger Filter chấp nhận? -- không --> bỏ qua
    |
   có
    v
Handler A (level + filter) --> console
    |
    +--> Handler B (level + filter) --> file
    |
    +--> Các Handler ở logger cha (nếu bật)
```

Mỗi handler có thể có chính sách khác nhau: INFO trở lên trên console, WARNING trở lên vào một kênh cảnh báo, hoặc log có định dạng riêng cho hệ thống tập trung. Logger không cần tự mở file để thực hiện điều đó.

## 4. Level quyết định sự kiện có được tiếp nhận không

JUL định nghĩa những level phổ biến sau, từ nghiêm trọng hơn đến chi tiết hơn:

| Level | Ý nghĩa thường dùng |
| --- | --- |
| `SEVERE` | Lỗi nghiêm trọng có ảnh hưởng lớn |
| `WARNING` | Sự cố có thể phục hồi, nguy cơ hoặc hành vi bất thường |
| `INFO` | Sự kiện vận hành đáng quan tâm |
| `CONFIG` | Thông tin cấu hình, khởi tạo |
| `FINE` | Chi tiết phục vụ gỡ lỗi |
| `FINER` | Chi tiết hơn `FINE` |
| `FINEST` | Mức chi tiết nhất trong các mức thông dụng |

`OFF` tắt logging tại logger ở ngưỡng đó; `ALL` cho phép mọi level theo ngưỡng. JUL so sánh giá trị số của level: mức của sự kiện phải lớn hơn hoặc bằng ngưỡng hiệu lực để qua bước kiểm tra logger. Handler lại có **ngưỡng độc lập**.

Ví dụ:

```java
logger.setLevel(Level.INFO);
handler.setLevel(Level.WARNING);

logger.info("request.completed");      // Qua logger; handler này bỏ
logger.warning("dependency.timeout"); // Qua cả logger và handler
logger.fine("cache.hit");             // Logger bỏ trước khi tới handler
```

Đoạn mã minh họa cơ chế; không phải chương trình Java độc lập. Một lời gọi `logger.isLoggable(Level.INFO)` ở cấu hình trên có thể trả về `true` nhưng `INFO` vẫn không xuất hiện ở handler `WARNING`. Ngoài ra, logger filter và handler filter còn có thể loại bản ghi.

**Đổi level ở đúng nơi:** khi muốn xem `FINE` của một lớp, kiểm tra cả level logger, level handler/appender, filter, logger cha và đường chuyển tiếp. Chỉ tăng level ở một bên có thể chưa đủ. Tránh bật mức chi tiết nhất cho toàn ứng dụng lâu dài vì số lượng event, chi phí CPU, I/O và nguy cơ lộ dữ liệu.

## 5. Đặt tên, phân cấp và sử dụng Logger đúng phạm vi

Trong Java, cách phổ biến để xác định logger là dùng tên lớp:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

Đây là **đoạn mã minh họa trong lớp `OrderService`**, với import `java.util.logging.Logger`. Tên logger sẽ là tên đầy đủ của lớp, ví dụ `com.example.orders.OrderService`. Tên ổn định giúp lọc log theo package, lớp hoặc thành phần. Không nên đặt tên logger theo từng `requestId`, từng người dùng hay ID ngẫu nhiên vì gây khó cấu hình và tạo quá nhiều logger.

JUL tổ chức **logger có tên theo hệ phân cấp**. Ví dụ:

```text
""                             root logger
  com
    com.example
      com.example.orders
        com.example.orders.OrderService
```

Hệ phân cấp thực tế phụ thuộc các logger đã được tạo và quản lý trong `LogManager`; tên có dấu chấm giúp JUL xác định quan hệ ancestor gần nhất phù hợp.

Nếu `Logger` không tự đặt level (`setLevel(null)`), **ngưỡng level hiệu lực kế thừa từ logger cha gần nhất có level được đặt**, cuối cùng là root. Ví dụ độc lập về ý tưởng:

```java
Logger parent = Logger.getLogger("demo.orders");
parent.setLevel(Level.WARNING);

Logger child = Logger.getLogger("demo.orders.PaymentService");
child.setLevel(null); // Kế thừa WARNING
child.info("payment.started"); // Bị bỏ theo level hiệu lực
```

**Kế thừa level khác với chuyển tiếp tới handler cha.** Trong JUL:

- `setLevel(null)` ảnh hưởng level hiệu lực của logger.
- `setUseParentHandlers(false)` ngừng phân phối bản ghi tới các handler thuộc logger cha; nó **không tự ngắt kế thừa level**.
- Khi một logger con đã chấp nhận `LogRecord`, sự phân phối lên handler của logger cha không có nghĩa logger cha sẽ chạy lại mọi kiểm tra level/filter của chính nó. Handler được gắn ở logger cha vẫn áp dụng level/filter của **handler đó**.
- Logger cha có thể có handler mặc định của root. Nếu cùng một loại đầu ra được cấu hình ở logger con và logger cha, log có thể bị in lặp. Kiểm tra cây handler và `useParentHandlers` trước khi cho rằng code đã gọi log hai lần.

Một ứng dụng thường dùng logger theo lớp/thành phần và quản lý cấp độ/đầu ra ở cấu hình tập trung. Trong dự án sử dụng framework, tránh tự tạo handler riêng tại mọi lớp: việc này dễ sinh log trùng, file descriptor dư thừa và cấu hình khó kiểm soát.

## 6. Logger nhận những kiểu thông tin nào?

### 6.1. Message tĩnh và tham số

```java
logger.info("event=service.ready");
logger.log(Level.INFO, "event=task.finished taskId={0} durationMs={1}",
        new Object[] { taskId, elapsedMs });
```

Trong JUL, các mẫu `{0}`, `{1}` sử dụng quy tắc định dạng tham số của `java.text.MessageFormat` khi message được format bởi formatter phù hợp. Điều này **khác** cú pháp `{ }` phổ biến ở SLF4J. Kết quả cụ thể có thể phụ thuộc locale/formatter; sử dụng định dạng dữ liệu có cấu trúc khi cần tính máy đọc và ổn định xuyên locale.

Đừng trộn lẫn tham số định dạng với dữ liệu tùy ý không được kiểm soát. Khi cần hỗ trợ tìm kiếm tốt, ưu tiên những trường ổn định như `event=task.finished`, `taskId`, `outcome`, `durationMs`, `errorCode`.

### 6.2. Ngoại lệ và stack trace

```java
try {
    callDependency();
} catch (IOException ex) {
    logger.log(Level.WARNING,
            "event=dependency.failed operation=loadConfig", ex);
}
```

Đây là **đoạn mã trong một phương thức**, với `IOException`, `callDependency()` và logger được khai báo trong ngữ cảnh; không phải ví dụ chạy độc lập. Overload nhận `Throwable` lưu ngoại lệ trong bản ghi để handler/formatter có thể đưa loại lỗi và stack trace vào log. Không nên thay nó bằng `logger.warning(ex.getMessage())` rồi đánh mất ngữ cảnh gọi; cũng không in stack trace giống nhau ở mọi tầng nếu lỗi đã được log ở ranh giới chịu trách nhiệm.

Một `catch` chỉ để log rồi bỏ qua exception có thể khiến ứng dụng tiếp tục trong trạng thái lỗi. Phải quyết định rõ xử lý, retry, biến đổi lỗi hay ném tiếp dựa trên hợp đồng nghiệp vụ.

### 6.3. Supplier để hoãn tạo thông điệp

```java
logger.fine(() -> "state=" + expensiveSnapshot());
```

Khi level `FINE` **không được logger cho phép**, JUL không cần gọi `Supplier<String>` để tạo message. Trái lại:

```java
logger.fine("state=" + expensiveSnapshot());
```

thì `expensiveSnapshot()` đã được Java gọi trước `logger.fine(...)`, ngay cả khi log bị bỏ theo level. Supplier chỉ giúp hoãn **việc tạo thông điệp**; nó không hoãn những phép tính đã được thực hiện để tạo đối số từ trước. Cũng không nên hiểu rằng supplier chắc chắn không chạy nếu một **filter hoặc handler phía sau** loại bản ghi: supplier có thể được gọi sau khi qua kiểm tra level nhưng trước bước loại bỏ đó.

Thông điệp log nên tránh side effect; không cập nhật trạng thái nghiệp vụ, đếm giao dịch hoặc gọi API chỉ vì một nhánh log được bật. Nếu cần metadata có chi phí lớn, kiểm tra `isLoggable()` hoặc thiết kế dữ liệu đã có sẵn và hiểu rõ cả chi phí ở các bước sau.

### 6.4. Ngữ cảnh tương quan của request/job

Logger nhận cùng lúc event và thông tin ngữ cảnh. Ví dụ một hệ thống có nhiều request song song:

```text
INFO event=request.start requestId=req-18 operation=checkout
INFO event=request.start requestId=req-19 operation=search
INFO event=request.end   requestId=req-18 outcome=success durationMs=24
INFO event=request.end   requestId=req-19 outcome=failed errorCode=UPSTREAM_TIMEOUT
```

`requestId` giúp ghép đúng sự kiện dù các log xen kẽ. Với hệ thống phân tán, thêm `traceId` và `spanId` theo chuẩn tracing được sử dụng. JUL không tự cung cấp một cơ chế MDC giống API thường thấy của SLF4J/Logback; có thể truyền context qua tham số, wrapper, `LogRecord` hoặc thư viện hỗ trợ phù hợp. Nếu một framework dùng MDC/ThreadLocal, **ngữ cảnh phải được truyền khi chuyển sang thread/executor khác và dọn sạch hoặc khôi phục ở cuối phạm vi** để tránh gán nhầm ID request cho tác vụ sau.

Dữ liệu có thể ghi vào log cần được chọn lọc. Không ghi mật khẩu, token, thông tin thẻ thanh toán, dữ liệu cá nhân hoặc toàn bộ request/response mặc định. `requestId`, mã lỗi, thời lượng và khóa nghiệp vụ được kiểm soát thường hữu ích hơn một payload lớn.

## 7. Ví dụ Java 17: quan sát Logger chấp nhận và bỏ sự kiện

Ví dụ dưới đây chạy độc lập chỉ với JDK, dùng `java.util.logging` để kiểm tra bốn tình huống:

1. `INFO` được nhận khi logger đặt `INFO`.
2. `FINE` bị bỏ khi level logger chưa cho phép, và message supplier không được gọi.
3. `INFO` bị loại bởi logger filter theo tiền tố `event=noise`.
4. `WARNING` được format bằng tham số; khi đổi logger sang `FINE`, bản ghi `FINE` được nhận.

Để đầu ra dự đoán được, chương trình gắn một `StreamHandler` ghi `System.out`, formatter in level và message, gọi `flush()` sau mỗi event và tắt chuyển tiếp tới handler của logger cha. Trong ứng dụng thật, cấu hình handler/formatter tập trung phù hợp hơn.

Lưu tệp **`LoggerReceptionDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class LoggerReceptionDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggerReceptionDemo.class.getName());

    public static void main(String[] args) {
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.setFilter(record ->
                !record.getMessage().startsWith("event=noise"));
        LOG.addHandler(output);

        AtomicInteger supplierCalls = new AtomicInteger();

        try {
            LOG.info("event=logger.ready");

            LOG.fine(() -> {
                supplierCalls.incrementAndGet();
                return "event=debug.suppressed";
            });

            LOG.info("event=noise.heartbeat");

            LOG.log(Level.WARNING, "event=retry attempt={0}", 2);
            LOG.info("event=supplier.counter count=" + supplierCalls.get());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "event=debug.accepted count="
                    + supplierCalls.incrementAndGet());
            LOG.info("event=supplier.counter count=" + supplierCalls.get());
        } finally {
            output.flush();
            LOG.removeHandler(output);
            LOG.setFilter(null);
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac LoggerReceptionDemo.java
java LoggerReceptionDemo
```

**stdout dự kiến chính xác trên chương trình này:**

```text
INFO event=logger.ready
WARNING event=retry attempt=2
INFO event=supplier.counter count=0
FINE event=debug.accepted count=1
INFO event=supplier.counter count=1
```

**Phân tích kết quả:**

- Dòng `event=logger.ready` qua được ngưỡng `INFO` và filter.
- Lời gọi `LOG.fine(...)` đầu tiên không qua level `INFO`, vì thế supplier không chạy, `supplierCalls` vẫn bằng `0`.
- `event=noise.heartbeat` đạt ngưỡng `INFO` nhưng bị logger filter chặn, nên không có dòng tương ứng.
- `WARNING` được chấp nhận và `Formatter.formatMessage` thay `{0}` bằng `2`.
- Khi đổi level sang `FINE`, lời gọi `fine(Supplier)` được nhận, supplier tăng bộ đếm lên `1`. Handler có level `ALL` nên in cả `FINE`.
- `setUseParentHandlers(false)` ngăn các console handler cha nhận lại bản ghi, giúp ví dụ không bị in trùng.
- `output.flush()` đẩy dữ liệu còn trong handler; ví dụ **không gọi `output.close()`** vì đóng một `StreamHandler` đang sở hữu `System.out` có thể đóng luôn stdout. Ứng dụng thực cần quản lý vòng đời handler theo backend.

Bạn có thể tự thay `output.setLevel(Level.ALL)` thành `output.setLevel(Level.WARNING)`: kết quả khi đó chỉ còn dòng `WARNING event=retry attempt=2`, vì mọi dòng `INFO` và `FINE` đều bị handler loại bỏ. Đây là cách quan sát trực tiếp rằng Logger chấp nhận log và Handler xuất log là **hai quyết định khác nhau**.

## 8. Logger, hiệu năng và đa luồng

### 8.1. Chi phí ghi log xuất hiện ở nhiều điểm

Ngay cả khi không xuất log, việc tạo đối số bằng nối chuỗi hoặc serialization trước lời gọi logger vẫn có chi phí. Khi được chấp nhận, event có thể tốn thêm CPU để tạo `LogRecord`, xác định thông tin caller, xử lý filter, format stack trace, tạo JSON, đồng bộ I/O hoặc đẩy vào queue. Tránh format đối tượng lớn, truy vấn thêm DB, gọi mạng hoặc đọc toàn bộ payload chỉ để log.

Dùng level hợp lý, message supplier khi thích hợp và các trường ngữ cảnh gọn. Nếu hệ thống có sampling/rate limit, áp dụng theo loại sự kiện và mức độ nghiêm trọng; **không được để việc giảm log che mất lỗi quan trọng hoặc dấu vết kiểm toán bắt buộc**.

### 8.2. Nhiều thread dùng chung Logger

Thông thường, **một logger theo lớp/thành phần được nhiều thread dùng chung**; không cần tạo logger mới cho mỗi request. JUL được thiết kế để hỗ trợ ghi log từ nhiều thread, nhưng thứ tự hoàn thành ở đầu ra không luôn phản ánh toàn bộ quan hệ nhân quả của chương trình, đặc biệt khi handler bất đồng bộ hoặc một sự kiện đi qua nhiều đích.

Đừng lấy thứ tự các dòng giữa hai request độc lập làm bằng chứng request nào hoàn thành trước khi thiếu ID/timestamp/trace. Khi tự viết Handler/Formatter, phải tính đến truy cập đồng thời và chính sách flush, đóng tài nguyên, lỗi ghi. Đối với logger bất đồng bộ, lời gọi trả về có thể chỉ cho biết event đã được nhận vào queue; queue đầy, bộ đệm mất hoặc crash vẫn có thể khiến log biến mất.

### 8.3. Logger không thay thế cơ chế xử lý lỗi

Một lời gọi `logger.severe(...)` **không tự sửa lỗi, retry, rollback, hay biến kết quả của phương thức thành thất bại**. Code nghiệp vụ cần quyết định luồng xử lý độc lập với việc log. Không ghi sự kiện “success” trước khi thao tác quan trọng thực sự hoàn tất; nếu có transaction, phân biệt thành công bước xử lý với commit thành công.

Tương tự, yêu cầu kiểm toán (audit) có thể cần cơ chế lưu bền vững, bất biến và phân quyền riêng; không mặc định một logger ứng dụng thỏa mọi yêu cầu audit.

## 9. Chẩn đoán các hiện tượng thường gặp

| Triệu chứng | Kiểm tra theo thứ tự hợp lý |
| --- | --- |
| Đã gọi `logger.fine()` nhưng không thấy | Level hiệu lực của logger → logger filter → level/filter từng handler → parent handlers → đích xuất |
| `isLoggable(INFO)` trả `true` nhưng không có dòng | Logger filter, Handler filter/level, formatter, đích ghi, flush và cấu hình collector |
| Log xuất hiện hai lần | Có handler ở cả logger con và logger cha, hoặc cùng một handler/đích được cấu hình lặp |
| Log in ra stderr thay vì stdout | ConsoleHandler mặc định của JUL thường ghi stderr; kiểm tra handler được cấu hình thực tế |
| Gọi logger quá chậm | Nối chuỗi/serialization trước lời gọi, stack trace, formatter, ghi file/console đồng bộ, khóa và backpressure |
| Log từ hai request bị trộn | Bổ sung requestId/traceId; truyền ngữ cảnh qua thread/executor; phục hồi hoặc xóa context sau công việc |
| Chỉ thấy thông điệp lỗi, không có stack trace | Đã truyền `Throwable` vào overload thích hợp chưa; formatter/backend có xuất throwable không |
| Sự kiện biến mất khi tắt đột ngột | Bộ đệm handler/queue/collector, shutdown và flush; `SIGKILL`/crash không đảm bảo ghi hết |
| Log quá nhiều sau khi bật FINE | Thu hẹp logger name, level và thời gian bật; áp dụng sampling phù hợp, kiểm soát chi phí và bí mật |

Một cách điều tra thực tế là **đi dọc pipeline từ trái sang phải**: ứng dụng có thực hiện lời gọi → logger có chấp nhận level/filter → handler có nhận → formatter có tạo output → đầu ra/collector có lưu. Mỗi câu hỏi kiểm tra một ranh giới cụ thể thay vì tăng level của toàn bộ ứng dụng rồi hy vọng log xuất hiện.

## 10. Kiểm tra chất lượng thiết kế Logger

Khi rà soát một module logging, hãy đối chiếu các điểm sau:

- Logger có tên ổn định, thường theo package/lớp; không sinh logger với tên request/user động.
- Mã ứng dụng xác định đúng `event`, level, context, kết quả và nguyên nhân; không để logging gây side effect nghiệp vụ.
- Level hiệu lực, logger filter, handler level/filter và parent propagation đã được cấu hình theo nhu cầu.
- Mỗi log quan trọng có đường đi xác định tới đích ghi; việc logger nhận sự kiện không bị hiểu nhầm là sự kiện đã được lưu bền vững.
- Có `requestId`/`traceId` khi cần theo vết; ngữ cảnh không rò rỉ giữa các công việc bất đồng bộ.
- Ngoại lệ được ghi tại ranh giới thích hợp, kèm stack trace khi cần; tránh log trùng hoặc chỉ log rồi nuốt lỗi.
- Log không lộ thông tin nhạy cảm; mức chi tiết, sampling, retention và chi phí phù hợp.
- Có kiểm tra hành vi thực tế cho các trường hợp: level bị tắt, filter từ chối, handler từ chối, nhiều parent handlers, lỗi đầu ra, shutdown và nhiều thread.

**Kết luận:** Logger là **điểm tiếp nhận và quyết định tuyến đầu** của hệ thống logging. Hiểu rõ bước chấp nhận level, lọc event, tạo bản ghi và chuyển tới handler giúp cấu hình log đúng, giảm bản ghi dư thừa, tránh mất tín hiệu khi có sự cố và phân biệt rõ “ứng dụng đã gọi log” với “log đã đến nơi lưu trữ”.
