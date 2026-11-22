# Tái sử dụng logger trong Java

## 1. Vì sao logger cần được tái sử dụng?

Khi một lớp Java xử lý nhiều yêu cầu liên tiếp hoặc đồng thời, nó thường phải ghi những sự kiện lặp lại về cùng một loại công việc: bắt đầu xử lý đơn hàng, cập nhật trạng thái, phát hiện đầu vào không hợp lệ, gọi dịch vụ bên ngoài hay xử lý ngoại lệ.

**Tái sử dụng logger** nghĩa là một lớp hoặc một thành phần dùng lại một đối tượng ghi log đã được xác định và cấu hình phù hợp, thay vì mỗi lần gọi phương thức lại tự tạo một logger, tự gắn handler/appender hoặc tự thiết lập lại đường ghi. Trong cách viết Java phổ biến, mỗi lớp có một logger được giữ bằng trường `private static final`:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

Đoạn mã này là **mẫu khai báo trong một lớp**, chưa phải chương trình độc lập. Nó dùng `java.util.logging.Logger` (JUL) có sẵn trong JDK.

Để hiểu đúng vấn đề, cần tách ba thứ:

- **Đối tượng logger**: đầu mối mà mã Java gọi `info`, `warning`, `log`... Nó thường có tên và các quy tắc lọc.
- **Handler/appender và cấu hình**: những thành phần quyết định sự kiện được chuyển tới console, file hoặc đích khác, có mức log và định dạng gì. Cấu hình này thường được thiết lập ở phạm vi ứng dụng.
- **Dữ liệu của lần xử lý**: mã yêu cầu, mã đơn hàng, người thao tác, kết quả, lỗi... Những giá trị này **thay đổi theo từng sự kiện**; chúng không được biến thành trạng thái dùng chung có thể bị luồng khác ghi đè.

Tái sử dụng logger đem lại tên nguồn log ổn định, cách cấu hình nhất quán và code ngắn gọn. Nó không có nghĩa là mọi lớp trong ứng dụng phải dùng một logger chung mang cùng một tên, cũng không có nghĩa mọi request phải dùng chung metadata.

## 2. Mô hình: nhiều đối tượng, một logger theo lớp

Một ứng dụng Java có thể tạo nhiều đối tượng `OrderService`. Nếu logger là trường `static final` của lớp, các đối tượng ấy cùng truy cập một logger:

```text
new OrderService() ──┐
                     ├──> OrderService.LOG ──> Handler / Appender ──> Đích log
new OrderService() ──┤
                     │
new OrderService() ──┘

new PaymentService() ───> PaymentService.LOG ──> Handler / Appender ──> Đích log
```

Đối tượng logger **có thể được dùng chung** trong khi mỗi lời gọi log vẫn tạo ra một sự kiện riêng với nội dung và ngữ cảnh riêng. Những logger thuộc các lớp khác nhau có thể dùng chung hệ thống handler/appender ở phía sau theo cấu hình; không cần mỗi lớp mở một file hay một kết nối riêng.

Cần nắm ba đặc điểm:

1. `static`: chỉ có một trường logger của **lớp** thay vì một trường được khởi tạo riêng cho từng thực thể.
2. `final`: trường không bị gán lại để trỏ sang một logger khác sau khi khởi tạo. Điều này **không** khiến bản thân đối tượng `Logger` bất biến; mức log, handler và filter vẫn có thể thay đổi bằng API hoặc cấu hình.
3. `private`: mã bên ngoài không trực tiếp thay đổi logger của lớp; lớp chỉ dùng nó để phát sự kiện. Tên `LOG` hay `LOGGER` là quy ước, không có tác động đến hoạt động của logging.

Trong mẫu `Logger.getLogger(OrderService.class.getName())`, tên logger thường là tên lớp đầy đủ (ví dụ `com.example.orders.OrderService`). Điều này giúp tìm bản ghi theo nơi phát sinh và hỗ trợ phân cấp logger bằng dấu chấm.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Chương trình dưới đây minh họa:

- Hai đối tượng `OrderService` dùng chung trường logger `static final`.
- `Logger.getLogger(...)` được gọi với cùng tên trong cùng một hệ thống JUL và nhận lại logger đã đăng ký khi logger đó còn tồn tại.
- Cấu hình `ConsoleHandler` được thực hiện **một lần ở điểm khởi động ví dụ**; mỗi lần xử lý đơn hàng chỉ ghi sự kiện.
- Thông tin `order_id` khác nhau giữa các lần gọi, dù logger là một đối tượng được chia sẻ.

Lưu toàn bộ mã thành **`LoggerReuseDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerReuseDemo {
    private LoggerReuseDemo() {
    }

    static final class OrderService {
        private static final Logger LOG =
                Logger.getLogger(OrderService.class.getName());

        void submit(String orderId) {
            LOG.log(Level.INFO,
                    "event=order_submitted order_id={0}", orderId);
        }
    }

    public static void main(String[] args) {
        Logger configured =
                Logger.getLogger(OrderService.class.getName());
        configured.setUseParentHandlers(false);
        configured.setLevel(Level.INFO);

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
        configured.addHandler(console);

        try {
            OrderService first = new OrderService();
            OrderService second = new OrderService();

            first.submit("ORD-101");
            second.submit("ORD-202");

            Logger byNameAgain =
                    Logger.getLogger(OrderService.class.getName());
            System.out.println(
                    "sameNamedLogger=" + (configured == byNameAgain));
            System.out.println(
                    "sameClassLogger=" + (configured == OrderService.LOG));
        } finally {
            configured.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 LoggerReuseDemo.java
java LoggerReuseDemo
```

**Đầu ra stderr** (do `ConsoleHandler` mặc định dùng `System.err`, kể cả với `INFO`):

```text
INFO event=order_submitted order_id=ORD-101
INFO event=order_submitted order_id=ORD-202
```

**Đầu ra stdout** (do `System.out.println`):

```text
sameNamedLogger=true
sameClassLogger=true
```

Hai luồng stdout và stderr có thể được terminal trộn khi hiển thị; vì vậy không dựa vào thứ tự xen kẽ giữa **bốn dòng của hai luồng** để kiểm tra kết quả. Cách trình bày trên tách chúng theo nguồn phát.

### Vì sao kết quả là `true`?

- `configured` giữ một tham chiếu mạnh đến logger tên `LoggerReuseDemo$OrderService`. Sau đó `OrderService.LOG` yêu cầu logger bằng đúng tên đó, nên trong ngữ cảnh chạy ví dụ JUL trả về cùng đối tượng.
- `byNameAgain` gọi lại `Logger.getLogger` với cùng tên khi logger đã tồn tại và vẫn được giữ tham chiếu; nó nhận lại đối tượng đó.
- Các đối tượng `first` và `second` chỉ khác nhau ở trạng thái đối tượng `OrderService`, không sở hữu hai trường `LOG` riêng.
- Mỗi lần `submit` đưa `orderId` của **lần gọi hiện tại** vào bản ghi `LogRecord`; giá trị mã đơn hàng không nằm trong một biến `static` có thể bị ghi đè.

Lệnh `LOG.log(Level.INFO, "event=order_submitted order_id={0}", orderId)` dùng tham số định dạng của JUL. Bộ `Formatter` gọi `formatMessage(record)` để thay `{0}` bằng mã đơn hàng khi tạo chuỗi. Vì vậy kết quả không in nguyên văn `{0}`.

**Giới hạn ví dụ:** code chỉ mô phỏng gửi đơn hàng, không tương tác cơ sở dữ liệu. Handler được thiết lập bằng code cho dễ quan sát; trong ứng dụng thật nên quản lý cấu hình ở điểm khởi động/framework. Ví dụ này không chứng minh logger nào cũng là singleton toàn JVM hoặc có thể chia sẻ xuyên nhiều tiến trình.

## 4. `getLogger(name)` tái sử dụng như thế nào trong JUL?

`java.util.logging.Logger.getLogger(String name)` là API lấy một **logger có tên** thông qua hệ thống quản lý logger (`LogManager`). Khi một logger có tên ấy đã được đăng ký trong ngữ cảnh quản lý hiện hành và vẫn còn tồn tại, việc yêu cầu lại tên đó thường trả về cùng đối tượng.

Điều này khác với việc mỗi lần viết:

```java
Logger logger = Logger.getLogger("com.example.orders.OrderService");
```

sẽ chắc chắn tạo mới một logger. Câu lệnh gọi một phương thức tra cứu/lấy logger; không phải cú pháp khởi tạo `new Logger(...)`. Tuy nhiên, gọi tra cứu lặp đi lặp lại trong mọi phương thức vẫn làm code dài dòng và che khuất quy ước chọn tên lớp. Trường `static final` diễn đạt rõ rằng lớp muốn giữ và tái sử dụng một logger.

### Điểm cần nhớ về vòng đời

**JUL có thể giữ tham chiếu yếu đối với logger có tên** trong bộ quản lý. Nếu mã ứng dụng không giữ tham chiếu mạnh và không còn thành phần nào tham chiếu logger ấy, đối tượng có thể được thu gom bộ nhớ; một lần `getLogger(name)` sau này có thể nhận một logger khác được tạo lại.

Vì vậy, nói “mọi lần `getLogger` với cùng tên mãi mãi trả về cùng một object trong suốt đời JVM” là quá mạnh. Quy tắc an toàn cho lớp thông thường là **giữ logger trong trường `static final`**. Điều này giúp giữ logger tồn tại theo vòng đời của lớp và tránh phụ thuộc vào chi tiết quản lý tham chiếu.

Thêm một số ranh giới:

- **Tên logger** là danh tính logic dùng trong hệ thống quản lý logger, không phải số định danh cho từng giao dịch.
- Trong cấu hình thông thường, tên logger là tên lớp đầy đủ; logger tên `a.b.Service` và `a.b.Repository` là hai tên khác nhau dù chúng có thể kế thừa cấu hình và dùng chung handler ở logger cha.
- Nếu ứng dụng dùng bộ quản lý logging đặc biệt, nhiều class loader hoặc cơ chế cách ly riêng, cách quản lý/đăng ký logger có thể khác. Không dựa vào phép so sánh `==` giữa mọi thành phần của một hệ thống phức tạp như một hợp đồng nghiệp vụ.
- `Logger.getAnonymousLogger()` tạo logger không tên, phù hợp với trường hợp đặc thù; nó không thực hiện cùng ý nghĩa tra cứu theo một tên ổn định như `getLogger(name)`.

## 5. Vì sao thường chọn **một logger theo lớp**?

Giả sử có `OrderService`, `PaymentService` và `OrderRepository`. Chúng có thể dùng chung cùng một đích ghi console, nhưng nên mang tên logger phân biệt:

```java
// Bên trong OrderService:
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());

// Bên trong PaymentService:
private static final Logger LOG =
        Logger.getLogger(PaymentService.class.getName());

// Bên trong OrderRepository:
private static final Logger LOG =
        Logger.getLogger(OrderRepository.class.getName());
```

Đây là **ba khai báo mẫu ở ba lớp khác nhau**, không phải một file Java có thể dán nguyên như trên để biên dịch.

Với logger theo lớp, người vận hành có thể đặt mức `FINE` cho `com.example.payment.PaymentService` khi điều tra lỗi mà không nhất thiết mở log chi tiết cho toàn bộ ứng dụng. Tên lớp cũng giúp nhận diện nguồn phát và phân tích các log có chung tiền tố package.

Không có quy tắc bắt buộc 100% logger phải đặt theo lớp. Một logger **theo nhóm sự kiện** như `com.example.business.audit` có thể hữu ích nếu nhóm đó có chính sách phân phối/giữ lại riêng. Tuy nhiên, khi đặt tên theo nhóm, phải giải thích rõ nơi phát sinh sự kiện và tránh làm mất khả năng biết lớp nào ghi log.

### Tránh tên logger theo từng đối tượng nghiệp vụ

Một cách làm kém phù hợp là tạo logger có tên động như `order.ORD-101`, `order.ORD-202` cho mỗi đơn hàng. Khi số đơn rất lớn, điều này làm nở không gian tên logger, khiến cấu hình và quản lý phức tạp; người vận hành cũng không còn lọc thuận tiện theo mã nguồn phát.

Để theo dõi từng đơn, hãy giữ logger của lớp và đưa **`order_id` vào trường của bản ghi log**:

```java
LOG.log(Level.INFO, "event=order_paid order_id={0}", orderId);
```

Khi có nhiều request xử lý cùng lúc, có thể bổ sung `correlation_id` hoặc `trace_id` tương ứng vào từng sự kiện. Tên logger mang ý nghĩa **nguồn phát**; mã yêu cầu/đối tượng mang ý nghĩa **ngữ cảnh lần xử lý**.

## 6. Dùng chung logger có an toàn với nhiều luồng không?

Logger thông thường của những framework Java phổ biến được thiết kế để nhiều luồng gọi cùng một đối tượng. JUL `Logger` cho phép gọi các phương thức ghi log đồng thời; với ví dụ ghi log của hai request:

```text
Thread-A: OrderService.submit("ORD-101") ──> OrderService.LOG
Thread-B: OrderService.submit("ORD-202") ──> OrderService.LOG
                                                |
                                                v
                                      Handler / Formatter / đích
```

Mỗi lời gọi tạo một sự kiện riêng. **Tái sử dụng một logger không đồng nghĩa các request dùng chung một `LogRecord` hoặc biến `orderId`.** Các giá trị `orderId` là tham số riêng của từng lần gọi `submit`.

Tuy nhiên, còn hai điểm cần tách bạch:

1. **Tính an toàn của logger không biến mọi dữ liệu đi kèm thành an toàn.** Nếu bạn lưu request hiện tại vào một trường `static` có thể thay đổi, hai luồng vẫn có thể ghi đè nhau trước khi ghi log.
2. **Thứ tự log đa luồng không mặc nhiên phản ánh thứ tự nghiệp vụ tuyệt đối.** Các luồng chạy xen kẽ; handler bất đồng bộ, bộ thu mạng và hệ thống tìm kiếm có thể làm sự kiện đến chậm hoặc đổi thứ tự. Muốn truy vết chính xác nên ghi timestamp, định danh request và các dấu mốc nghiệp vụ phù hợp.

Custom `Handler`/`Appender` hoặc `Formatter` có trạng thái thay đổi được cần được thiết kế và kiểm tra an toàn luồng riêng. Đừng suy ra rằng mọi plugin hoặc bộ định dạng do nhóm phát triển viết đều an toàn chỉ vì logger được chia sẻ.

## 7. Sai lầm: nhét ngữ cảnh request vào trường `static`

Xem đoạn code **không nên dùng** sau:

```java
class BadOrderService {
    private static final Logger LOG =
            Logger.getLogger(BadOrderService.class.getName());

    private static String currentOrderId;

    void process(String orderId) {
        currentOrderId = orderId;
        // Luồng khác có thể thay currentOrderId trước câu lệnh này.
        LOG.info(() -> "Processing " + currentOrderId);
    }
}
```

Nếu request A đặt `currentOrderId="ORD-101"` rồi bị tạm dừng, request B có thể đặt `currentOrderId="ORD-202"`. Khi A tiếp tục ghi log, bản ghi của A có thể mang sai mã đơn hàng.

Cách đúng và đủ đơn giản là đưa ngữ cảnh của lần gọi vào **biến cục bộ hoặc tham số**:

```java
class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    void process(String orderId) {
        LOG.log(Level.INFO, "Processing order_id={0}", orderId);
    }
}
```

Hai đoạn trên là ví dụ lớp độc lập về thiết kế; nếu muốn chạy riêng, cần thêm khai báo `import java.util.logging.Logger;` và, với đoạn thứ hai, `import java.util.logging.Level;` cùng một điểm vào ứng dụng.

Đây là nguyên tắc cốt lõi:

- **Logger được dùng chung** theo lớp.
- **Thông tin sự kiện được cung cấp riêng** cho từng lần ghi.
- **Mức log và handler được cấu hình theo chính sách**, không thay đổi liên tục theo request.

Không viết `LOG.setLevel(...)`, `LOG.addHandler(...)` hay `LOG.setFilter(...)` trong mỗi lần gọi xử lý đơn hàng. Những thao tác này tác động lên cấu hình logger dùng chung, có thể ảnh hưởng các request khác và gây trùng log hoặc kết quả khó dự đoán.

## 8. Tái sử dụng logger và ngữ cảnh tương quan (MDC)

Trong các hệ thống web và microservice, một yêu cầu có thể được xử lý qua nhiều lớp, nhiều thread hoặc nhiều dịch vụ. Các trường như `request_id`, `correlation_id`, `trace_id` cho phép kết nối những bản ghi liên quan với nhau.

Một số framework hỗ trợ **Mapped Diagnostic Context (MDC)**: đặt các cặp khóa–giá trị trong ngữ cảnh thực thi, để các sự kiện log có thể tự nhận thêm metadata theo cấu hình formatter/appender.

Ví dụ ý tưởng với **SLF4J + một implementation có MDC tương thích** (không thuộc JDK chuẩn; cần dependency và cấu hình phù hợp):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderId, String correlationId) {
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlation_id", correlationId)) {
            LOG.info("event=order_submitted order_id={}", orderId);
        }
    }
}
```

Đoạn trên là **một đoạn lớp minh họa yêu cầu thư viện SLF4J**, không phải chương trình Java chạy chỉ bằng `javac` với JDK. `MDC.putCloseable` hỗ trợ khôi phục/xóa khóa vừa đặt khi kết thúc phạm vi `try` theo cách sử dụng của API; cơ chế MDC thực tế phụ thuộc implementation, còn việc xuất `correlation_id` trong log phụ thuộc formatter/encoder của hệ thống.

Các điểm phải nhớ khi dùng MDC:

- Logger vẫn là **`static final`**: không cần tạo logger mới cho mỗi request.
- Giá trị MDC thuộc **ngữ cảnh lần xử lý**, không phải thuộc logger; không đặt `correlation_id` bằng trường `static` của lớp.
- Trong môi trường dùng thread pool, cần **dọn dữ liệu theo phạm vi** sau khi request kết thúc; nếu không, một thread được tái sử dụng có thể mang metadata cũ.
- Khi xử lý bất đồng bộ hoặc chuyển qua thread, đừng giả định MDC tự lan truyền. Cần cơ chế truyền ngữ cảnh được framework/runtime hỗ trợ hoặc chuyển các trường tương quan một cách tường minh.
- Truyền mã tương quan qua mạng và ghi các trường an toàn theo chính sách; tránh đưa mật khẩu, token và dữ liệu cá nhân nhạy cảm vào MDC hoặc log.

Trong JUL cơ bản, có thể ghi thông tin tương quan dưới dạng tham số của `LogRecord` hoặc dùng bộ formatter/handler tích hợp với ngữ cảnh riêng. Không giả định JUL mặc định có cùng API `MDC` của SLF4J.

## 9. `private static final` và `private final`: chọn thế nào?

Hai mẫu dưới đây đều có thể hoạt động:

**Mẫu thường dùng: trường lớp**

```java
private static final Logger LOG =
        Logger.getLogger(InventoryService.class.getName());
```

**Mẫu trường đối tượng**

```java
private final Logger log =
        Logger.getLogger(InventoryService.class.getName());
```

Với mẫu trường đối tượng, mỗi instance giữ một trường tham chiếu của riêng nó, nhưng lời gọi `Logger.getLogger` với cùng tên có thể vẫn trả về **chính đối tượng logger đang tồn tại**, chứ không mặc nhiên tạo một logger khác cho từng instance. Sự khác nhau là **nơi giữ tham chiếu và lúc thực hiện việc tra cứu**.

Đối với lớp dịch vụ thông thường, `static final` thường đơn giản và rõ ràng hơn vì logger không phụ thuộc dữ liệu instance. Trường instance có lý khi logger là một dependency được cung cấp qua constructor trong trường hợp đặc thù, khi một thành phần cần chọn tên/implementation theo cấu hình instance hoặc khi xây dựng công cụ logging đặc biệt.

Một điểm dễ nhầm: nếu dùng `LoggerFactory.getLogger(getClass())` trong một lớp bị framework tạo proxy hoặc kế thừa, tên runtime class có thể khác lớp khai báo mà bạn mong muốn. Với logger ổn định theo lớp, dùng `SomeService.class` thường dễ dự đoán hơn. Nếu thiết kế logger theo từng subtype, cần chủ động kiểm soát quy ước tên và vòng đời.

Đừng chỉ áp dụng `static final` máy móc cho mọi biến có tên “logger”. Ví dụ một **appender kết nối mạng** hoặc **handler có trạng thái** có trách nhiệm và vòng đời tài nguyên khác logger; việc chia sẻ hay đóng tài nguyên ấy cần do cơ chế cấu hình của framework quản lý.

## 10. Tái sử dụng logger với SLF4J, Logback và Log4j 2

Mẫu dùng lại logger theo lớp không riêng gì JUL. Trong ứng dụng Java có backend logging qua SLF4J, ta thường gặp:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentId) {
        LOG.info("event=payment_authorization_requested payment_id={}",
                paymentId);
    }
}
```

Đây là **ví dụ lớp dùng thư viện ngoài**; muốn biên dịch/chạy phải cung cấp SLF4J API và backend phù hợp (ví dụ Logback), không thể chỉ dùng JDK 17 trần.

Ở ví dụ này:

- `LoggerFactory.getLogger(PaymentService.class)` lấy logger theo tên lớp thông qua hệ thống logging được cấu hình.
- `{}` là kiểu placeholder trong lời gọi SLF4J ở đây; nó **khác** mẫu `{0}`/`MessageFormat` trong JUL. Không tự đổi hai kiểu placeholder cho nhau.
- `static final` giữ một tham chiếu sử dụng lại giữa các lời gọi và giữa các instance của `PaymentService`.
- Logback/Log4j 2 và các implementation khác sẽ quyết định cách lọc, ghi vào appender, format và chuyển sự kiện; SLF4J là API log được mã nguồn gọi.

Với Log4j 2 API dùng trực tiếp, mẫu tương tự là `private static final org.apache.logging.log4j.Logger LOG = org.apache.logging.log4j.LogManager.getLogger(PaymentService.class);`. Sự giống nhau về cách tổ chức code không đồng nghĩa các implementation có cơ chế đăng ký, cache, quản lý tham chiếu hay cấu hình hoàn toàn giống JUL.

**Không tạo nhiều backend logging riêng cho mỗi lớp chỉ để “tái sử dụng logger”.** Ứng dụng nên có chiến lược API/implementation nhất quán và cấu hình ở phạm vi thích hợp. Khi cần chuyển từ JUL sang SLF4J, phải đánh giá cách bridge và backend đang hoạt động để tránh vòng lặp chuyển tiếp, log trùng hoặc xung đột cấu hình.

## 11. Cấu hình handler/appender một lần, tránh log trùng

Một sai lầm phổ biến không nằm ở việc tạo logger, mà ở việc **mỗi lần xử lý đều gắn thêm handler**:

```java
// Ví dụ KHÔNG NÊN dùng trong mỗi request:
Logger log = Logger.getLogger("com.example.OrderService");
log.addHandler(new ConsoleHandler());
log.info("Processing");
```

Giả sử mã này chạy ba lần và các handler còn tồn tại, cùng một sự kiện ở lần thứ ba có thể được gửi đến ba ConsoleHandler đã gắn, cộng thêm handler của logger cha nếu cơ chế truyền sự kiện vẫn bật. Đầu ra bị nhân đôi/nhân ba; handler còn có thể giữ tài nguyên không được giải phóng.

Thiết kế tốt hơn là:

1. Cấu hình handler/appender, formatter, mức lọc, nơi ghi và chu kỳ lưu giữ trong **cấu hình ứng dụng hoặc giai đoạn khởi động**.
2. Giữ logger tại lớp với `static final`.
3. Trong phương thức xử lý, chỉ gọi `LOG.info(...)`, `LOG.warning(...)` hoặc các phương thức tương đương.
4. Khi tắt ứng dụng, để logging framework hoặc nơi sở hữu tài nguyên đóng handler/appender đúng vòng đời.

Đặc biệt với JUL, **logger có phân cấp**. Logger con có thể đẩy sự kiện lên handler của logger cha; nếu cùng lúc gắn handler cho cả hai, log có thể xuất hiện hai lần. Khi cần cấu hình độc lập, `setUseParentHandlers(false)` tắt truyền lên cha cho logger đó, nhưng nên áp dụng có chủ đích tại điểm cấu hình thay vì thêm vào mọi lớp một cách tùy tiện.

## 12. Tái sử dụng logger và chi phí ghi log

Một logger giữ lại trong trường `static final` giúp code không phải lặp tra cứu logger theo tên. Tuy nhiên, chi phí đáng quan tâm trong ứng dụng nhiều log thường đến từ **tạo thông điệp, chuyển đối tượng thành chuỗi, gọi formatter, ghi đĩa, mạng và lưu trữ**, không thể khẳng định mọi chương trình tăng hiệu năng rõ rệt chỉ nhờ thay `getLogger(...)` bằng một trường.

Hãy chú ý *đánh giá thông điệp* khi mức log đang tắt:

```java
// Cách thứ nhất: phép ghép chuỗi được thực hiện trước lời gọi.
LOG.fine("details=" + computeDetails());

// Cách thứ hai: JUL chỉ gọi Supplier nếu cần log ở mức này.
LOG.fine(() -> "details=" + computeDetails());
```

Đây là **hai cách gọi minh họa bên trong một lớp có LOG**. Cách thứ hai dùng `Supplier<String>` của JUL, hữu ích khi `computeDetails()` tốn chi phí và mức `FINE` có thể bị tắt.

Để sử dụng đúng:

- `Supplier` nên xây dựng **thông điệp**, không chứa side effect nghiệp vụ. Nếu log bị tắt, supplier có thể không được gọi.
- Không đặt thông tin nhạy cảm vào thông điệp chỉ vì nó được tạo trễ.
- Với SLF4J, các overload hỗ trợ tham số `{}` thường tránh định dạng thông điệp không cần thiết; nếu việc **tạo đối số** đã tốn chi phí thì phải cân nhắc thêm, vì đối số được đánh giá trước khi gọi phương thức.
- Không lấy việc tái sử dụng logger làm lý do bỏ chính sách sampling, quản lý cấp log hoặc dung lượng lưu trữ; một logger duy nhất vẫn có thể tạo lượng log rất lớn.

## 13. Vòng đời ứng dụng và những trường hợp đặc biệt

**Ứng dụng đơn giản:** trường `static final` được khởi tạo khi lớp được khởi tạo lần đầu; logger được sử dụng cho tới khi lớp và class loader của nó không còn được giữ. Không cần tạo/destroy logger cho từng đối tượng.

**Ứng dụng Spring hoặc ứng dụng có dependency injection:** logger theo lớp thường vẫn dùng `private static final`. Vòng đời bean, request scope hay singleton bean là khái niệm khác với trường `static`; kể cả bean được tạo lại, logger theo lớp vẫn có thể được dùng lại. Nếu framework logging có cấu hình tự động, không tự tạo thêm ConsoleHandler chỉ vì đã có logger.

**Thư viện dùng chung:** đặt tên logger theo package/lớp thư viện để ứng dụng sử dụng thư viện có thể lọc riêng. Tránh ép ứng dụng phải sử dụng file path hoặc endpoint cố định chỉ từ code thư viện.

**Ứng dụng plugin/class loader:** tên lớp đầy đủ có thể trùng giữa các loader hoặc có quy tắc cô lập khác nhau, tùy hệ thống logging. Không dùng giả định “tên lớp duy nhất toàn JVM” để thiết kế chia sẻ mutable state hay truy xuất dữ liệu ứng dụng.

**Tác vụ ngắn hoặc batch:** có thể chạy qua nhiều job nhưng cùng một process. Logger của lớp được tái sử dụng, còn mã `job_id` hoặc `batch_id` phải được cung cấp theo từng lượt chạy và dọn ngữ cảnh cẩn thận.

**Shutdown:** log đã phát ra có thể còn ở buffer của handler/appender. Việc đóng tài nguyên và flush cần do nơi sở hữu hệ thống logging quản lý. Không đóng một handler dùng chung khi **một request** hoàn tất: điều đó có thể cắt log của request khác.

## 14. Bảng so sánh các cách tổ chức logger

| Cách làm | Logger có được dùng lại? | Đánh giá |
| --- | --- | --- |
| `private static final Logger LOG = Logger.getLogger(MyClass.class.getName());` | Một trường theo lớp giữ tham chiếu ổn định | **Thường nên chọn** cho lớp Java thông thường dùng JUL |
| `private final Logger log = Logger.getLogger(MyClass.class.getName());` | Có thể cùng đối tượng có tên nhưng mỗi instance giữ tham chiếu và thực hiện tra cứu | Hợp lệ, nhưng thường không cần thiết nếu tên logger cố định |
| Gọi `Logger.getLogger(MyClass.class.getName())` ở mọi phương thức | Có thể lấy lại logger hiện có; không bảo đảm luôn tạo mới | Chạy được, khó duy trì quy ước và lặp logic |
| Một logger tên `"application"` cho tất cả lớp | Dùng chung logger có cùng tên | Có thể làm mất thông tin phân biệt nguồn phát; chỉ chọn khi có lý do |
| Logger tên `"order." + orderId` | Tạo không gian tên theo đối tượng nghiệp vụ | **Tránh**: dùng `order_id` trong bản ghi thay thế |
| Thêm `ConsoleHandler` trong mỗi request | Logger có thể dùng lại nhưng handler liên tục được gắn thêm | **Sai vòng đời**, dễ trùng log và lãng phí tài nguyên |
| Một logger theo lớp, metadata `request_id` theo lời gọi | Logger dùng chung, dữ liệu sự kiện tách riêng | **Phù hợp** cho hệ thống nhiều request đồng thời |

## 15. Lỗi thường gặp và cách sửa

**1. Tạo logger động theo mã đối tượng.** Dùng tên lớp ổn định và ghi mã đối tượng ở trường sự kiện. Tên logger không phải công cụ quản lý vòng đời của từng đơn hàng.

**2. Đồng nhất “tái sử dụng” với “singleton toàn hệ thống”.** Mẫu `static final` chỉ giữ một trường của một lớp. Mỗi lớp thường có logger riêng; các logger có thể cùng sử dụng backend và handler tùy cấu hình.

**3. Cho rằng `static final` làm logger bất biến.** Nó chỉ khóa phép gán lại trường. Đừng thay đổi level, handler, filter per request vì đó vẫn là trạng thái chia sẻ.

**4. Lưu `currentUser`, `currentOrderId` vào biến `static` để logger tự dùng.** Có nguy cơ trộn dữ liệu giữa các luồng. Truyền tham số trong lần log hoặc dùng ngữ cảnh theo request được quản lý và dọn sạch.

**5. Mỗi instance thêm một handler vào logger có tên giống nhau.** Logger tồn tại lâu hơn instance trong nhiều cấu hình; handler cộng dồn và bản ghi bị nhân đôi. Cấu hình một lần tại điểm quản lý logging.

**6. Nhầm placeholder của JUL với SLF4J.** JUL dùng `{0}` khi formatter xử lý tham số; SLF4J thường dùng `{}`. Trộn hai kiểu có thể khiến log hiện placeholder nguyên văn.

**7. Cho rằng cùng logger bảo đảm log luôn theo đúng thứ tự.** Với nhiều thread và collector bất đồng bộ, sự kiện có thể xen kẽ hoặc đến khác thứ tự. Thêm mã tương quan và thời gian có múi giờ, đối chiếu trạng thái chính thức khi cần.

**8. Bỏ qua vòng đời của MDC.** Nếu MDC tồn tại trên thread của thread pool nhưng không dọn khi kết thúc request, metadata của request trước có thể xuất hiện ở request sau.

**9. Phụ thuộc vào logger còn tồn tại mãi chỉ nhờ `getLogger(name)`.** Với JUL, tham chiếu yếu của `LogManager` khiến logger không có tham chiếu mạnh có thể bị thu gom. Giữ một tham chiếu phù hợp như trường `static final`.

**10. Tối ưu tra cứu logger nhưng log quá nhiều nội dung nhạy cảm.** Bảo vệ dữ liệu, chọn mức log và kiểm soát số lượng bản ghi quan trọng hơn việc tiết kiệm một vài lần gọi phương thức lấy logger.

## 16. Tự kiểm tra kiến thức

1. **Hai đối tượng `OrderService` có `private static final Logger LOG`. Chúng có hai logger khác nhau không?** Không: chúng truy cập cùng trường `LOG` của lớp; các lời gọi log vẫn tạo sự kiện riêng.
2. **`Logger.getLogger("x.y.Service")` được gọi hai lần có luôn tạo hai đối tượng không?** Không. Khi logger có tên ấy còn tồn tại và được quản lý trong cùng ngữ cảnh JUL, lời gọi sau có thể trả về logger hiện có; trong ví dụ chạy, nó là cùng đối tượng.
3. **Vì sao nên giữ logger JUL bằng trường `static final`?** Dùng lại một tham chiếu ổn định, giữ đúng tên nguồn phát và tránh phụ thuộc vào việc bộ quản lý còn giữ đối tượng bằng tham chiếu yếu.
4. **Có nên tạo logger tên `order.ORD-101` để tra riêng đơn hàng?** Thường không. Hãy dùng tên logger theo lớp và trường `order_id=ORD-101` trong sự kiện.
5. **Logger dùng chung có làm `correlation_id` giống nhau trên mọi request không?** Không. Mã tương quan là dữ liệu theo request, phải được gắn riêng vào mỗi luồng xử lý/sự kiện.
6. **Nếu gắn ConsoleHandler mỗi lần một phương thức chạy, điều gì có thể xảy ra?** Handler cộng dồn, sự kiện xuất nhiều lần và tài nguyên khó quản lý. Hãy cấu hình ở mức ứng dụng.
7. **`static final Logger` có bảo đảm mức log không thể đổi không?** Không. `final` không làm đối tượng Logger bất biến; cấu hình logger vẫn có thể thay đổi.
8. **Vì sao trong ví dụ Java có hai dòng stderr và hai dòng stdout riêng?** `ConsoleHandler` ghi thông điệp JUL ra stderr; `System.out.println` in kết quả so sánh tham chiếu ra stdout. Thứ tự hai luồng khi terminal trộn không phải một bảo đảm.
9. **Đặt `MDC.putCloseable` có thay logger mới cho request không?** Không. Nó chỉ quản lý metadata theo phạm vi thực thi; logger theo lớp tiếp tục được dùng lại.
10. **Khi mức `FINE` tắt, vì sao `LOG.fine(() -> computeDetails())` có ích?** Supplier có thể không được gọi, tránh chi phí tạo thông điệp; không dùng supplier để thực hiện nghiệp vụ có side effect.

**Ghi nhớ:** mã nguồn thường **giữ một logger có tên theo lớp**, dùng lại logger khi có nhiều đối tượng và nhiều lần xử lý, cấu hình handler/appender ở vòng đời ứng dụng và đưa **ngữ cảnh động vào từng bản ghi**. Tái sử dụng logger giúp logging nhất quán; tính đúng đắn và an toàn của thông tin log còn phụ thuộc vào cách truyền tham số, quản lý ngữ cảnh request và thiết kế đích ghi.
