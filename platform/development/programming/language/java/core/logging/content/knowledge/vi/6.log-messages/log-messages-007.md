# String concatenation khi tạo log message trong Java

## 1. String concatenation là gì và vì sao liên quan đến logging?

**String concatenation** là phép nối nhiều giá trị thành chuỗi, thường sử dụng toán tử `+`. Trong Java, khi một toán hạng của phép cộng là `String`, kết quả là một chuỗi nối các biểu diễn văn bản của hai toán hạng. Đây là cách tự nhiên để tạo thông điệp log chứa biến:

```java
String orderId = "O-17";
int attempts = 3;
String message = "orderId=" + orderId + ", attempts=" + attempts;
// Kết quả: "orderId=O-17, attempts=3"
```

Trong logging, ta hay gặp:

```java
// Minh họa bên trong một lớp đã có logger.
logger.debug("Loading order " + orderId);
logger.info("Order " + orderId + " accepted");
logger.warn("Payment retry count=" + attempts);
```

Điểm quan trọng nhất: **Java tính biểu thức nối chuỗi trước khi gọi phương thức logger**. Khi cấp độ log bị tắt, sự kiện có thể không được ghi nhưng chương trình vẫn đã tốn công tạo thông điệp, gọi hàm tạo dữ liệu, hoặc chuyển đối tượng thành chuỗi. Đây là lý do string concatenation thường được thảo luận cùng *log message*, *log level* và *hiệu năng*.

Nối chuỗi không phải hành vi sai trong mọi trường hợp. Với câu thông điệp ngắn, mức log đang bật hoặc đoạn code không nằm trên đường chạy nóng, `+` có thể đơn giản và hoàn toàn chấp nhận được. Cần hiểu **thời điểm tính toán**, **mức độ tốn kém của biểu thức** và **logging API đang dùng** trước khi quyết định tối ưu.

## 2. Cơ chế nối chuỗi trong Java

### 2.1. Toán tử + chuyển giá trị thành dạng văn bản

Một vài ví dụ có kết quả xác định:

```java
System.out.println("value=" + 10);        // value=10
System.out.println("value=" + true);      // value=true
System.out.println("value=" + (String) null); // value=null
System.out.println(1 + 2 + " items");     // 3 items
System.out.println("items=" + 1 + 2);     // items=12
```

Ở hai dòng cuối, quy tắc đánh giá từ trái sang phải làm kết quả khác nhau:

- `1 + 2 + " items"`: trước tiên `1 + 2` là phép cộng số học (3), sau đó nối với chuỗi.
- `"items=" + 1 + 2`: biểu thức bắt đầu bằng chuỗi, các phép `+` tiếp theo tạo chuỗi `items=1` rồi `items=12`.

Khi nối một object, Java dùng biểu diễn chuỗi của nó (về mặt ngữ nghĩa tương đương `String.valueOf(object)`); nếu giá trị null thì kết quả văn bản là `"null"`. Với object không null, phương thức `toString()` có thể được gọi. Điều này dẫn đến hai rủi ro đáng chú ý khi làm log: `toString()` có thể **tốn kém hoặc có tác dụng phụ**, và bản biểu diễn mặc định có thể **thiếu thông tin hữu ích hoặc tiết lộ dữ liệu**.

```java
// Nếu request.toString() serialize rất nhiều trường,
// công việc đó sẽ xảy ra khi tính chuỗi nối.
logger.debug("Incoming request: " + request);
```

Nếu `toString()` bị lỗi hoặc thực hiện thao tác ngoài dự kiến, lỗi có thể xảy ra ngay khi tạo biểu thức; không nên xem logging là thao tác luôn vô hại.

### 2.2. Java 17 không đồng nghĩa mỗi dấu + tạo một StringBuilder riêng

Tại mức ngôn ngữ, thứ tự đánh giá các toán hạng và kết quả nối chuỗi được quy định. **Cách sinh bytecode là chi tiết triển khai**. Với `javac` hiện đại, nhiều phép nối chuỗi dùng cơ chế `invokedynamic` và `java.lang.invoke.StringConcatFactory`; trình biên dịch/JVM có thể tối ưu cách cấp phát. Không nên khẳng định rằng mọi dấu `+` đều tạo một `new StringBuilder` hoặc luôn phát sinh một `String` trung gian độc lập.

Các biểu thức chỉ gồm hằng chuỗi có thể được gộp ngay khi biên dịch:

```java
String fixed = "Order " + "accepted";
// Tương đương một hằng chuỗi "Order accepted" trong trường hợp này.
```

Vấn đề hiệu năng trong logging thường **không chỉ là số object do phép + tạo ra**, mà còn là công việc bắt buộc để tính các toán hạng, gọi phương thức, serialize dữ liệu và tạo chuỗi ngay cả khi bản ghi bị lọc.

## 3. Điều gì xảy ra khi log level không cho phép sự kiện?

Xét lời gọi:

```java
logger.debug("Order details: " + serialize(order));
```

Quy trình thường là:

```text
1. Java đánh giá serialize(order)
                  |
2. Java nối "Order details: " với kết quả
                  |
3. Gọi logger.debug(message)
                  |
4. Logger/backend kiểm tra DEBUG có được bật không
                  |
           +------+------+
           |             |
        Không bật      Được bật
           |             |
       Bỏ bản ghi     Filter, formatter,
                     appender/handler...
```

Kể cả nhánh “Không bật”, bước 1 và 2 **đã xảy ra**. Logging framework không thể quay ngược việc tạo thông điệp mà caller đã hoàn thành.

Ví dụ:

```java
// Đoạn minh họa có logger và phương thức buildReport().
logger.debug("Report: " + buildReport());
```

Nếu `buildReport()` duyệt hàng nghìn bản ghi, truy vấn từ xa hoặc serialize đối tượng lớn, chi phí đó vẫn phát sinh khi DEBUG bị tắt. Việc gọi truy vấn từ xa hoặc thay đổi trạng thái chỉ để chuẩn bị một dòng log là thiết kế dễ tạo lỗi.

**Phân biệt hai thời điểm:**

1. **Tính biểu thức ở caller:** Java thực hiện trước khi gọi logger. Với `+` hoặc `String.format(...)`, đây là xử lý chủ động.
2. **Formatter/encoder của backend:** có thể chỉ thực hiện sau khi logger chấp nhận event. Tùy framework và cấu hình, filter ở handler/appender còn có thể loại event sau thời điểm đó.

Một API trì hoãn tạo message thường tránh được nhiều chi phí khi **level của logger bị tắt**, nhưng không tự động đảm bảo tất cả chi phí đều biến mất khi một filter ở giai đoạn sau loại sự kiện.

## 4. Những cách tạo log message và độ “eager/lazy”

| Cách viết | Khi nào thông điệp/đối số được tính? | Lưu ý |
| --- | --- | --- |
| `logger.debug("id=" + id)` | Chuỗi nối được tính ở caller trước lời gọi. | Thường đơn giản với ID nhỏ, nhưng vẫn có chi phí khi DEBUG tắt. |
| `logger.debug("data=" + expensive())` | `expensive()` chạy trước lời gọi, dù DEBUG tắt. | Cần tránh trên đường chạy nóng. |
| `logger.debug("data={}", data)` trong SLF4J | Đánh giá biến `data` ở caller; việc định dạng message thường có thể trì hoãn đến lúc log được xử lý. | `toString()` có thể được tránh nếu level tắt; **không** có nghĩa phương thức tạo `data` được trì hoãn. |
| `logger.debug("data={}", expensive())` trong SLF4J | `expensive()` vẫn chạy trước lời gọi. | Placeholder không làm mọi đối số trở thành lazy. |
| `logger.atDebug().addArgument(() -> expensive()).log("data={}")` trong SLF4J 2.x | Supplier có thể được đánh giá khi event thực sự được xử lý; mức DEBUG tắt sẽ tránh tính supplier theo API fluent. | Cần SLF4J 2.x và backend tương thích; đây là đoạn mã minh họa. |
| `logger.log(Level.FINE, () -> "data=" + expensive())` trong JUL | `Supplier<String>` chỉ được gọi khi logger xử lý mức FINE. | Phù hợp Java 17 thuần JDK; filter ở handler phía sau vẫn có thể loại bản ghi. |
| `if (logger.isLoggable(Level.FINE)) { logger.fine("data=" + expensive()); }` | Tính biểu thức sau khi kiểm tra điều kiện level ở caller. | Rõ ràng nhưng lặp kiểm tra và không dự đoán mọi filter ở sink. |

**Đừng nhầm parameterized logging với lazy evaluation của mọi tham số.** Khác biệt nằm ở chỗ **trì hoãn định dạng thông điệp** và **trì hoãn gọi hàm tạo đối số**. Hai việc có thể được xử lý bằng các API khác nhau.

## 5. Ví dụ Java 17+ độc lập: phép + được tính khi log bị tắt

Ví dụ dùng `java.util.logging` (JUL), có sẵn trong JDK. Mục tiêu là quan sát số lần một hàm “đắt” được gọi với **nối chuỗi trực tiếp** so với **Supplier<String>**. Chương trình cố ý dùng bộ đếm đơn giản để có kết quả chính xác và không phụ thuộc thời gian chạy của máy.

Tạo file **`LoggingConcatDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingConcatDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.concat");

        // Chỉ ghi bằng handler riêng để có stdout ổn định,
        // không phát tán sang handler của logger cha.
        logger.setUseParentHandlers(false);
        for (Handler oldHandler : logger.getHandlers()) {
            logger.removeHandler(oldHandler);
        }

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        // INFO được bật; FINE thấp hơn INFO nên bị loại.
        logger.setLevel(Level.INFO);
        AtomicInteger calls = new AtomicInteger();

        System.out.println("FINE enabled: "
                + logger.isLoggable(Level.FINE));

        // Hàm expensiveValue() vẫn chạy trước logger.fine(...).
        logger.fine("EAGER value=" + expensiveValue(calls));
        System.out.println("Calls after concatenation: "
                + calls.get());

        // JUL chỉ gọi Supplier khi FINE được bật tại logger.
        logger.log(Level.FINE,
                () -> "LAZY value=" + expensiveValue(calls));
        System.out.println("Calls after disabled supplier: "
                + calls.get());

        // Thông điệp bình thường, level INFO đang bật.
        String orderId = "O-17";
        logger.info("Order " + orderId + " accepted");

        // Supplier INFO được gọi, làm bộ đếm tăng lên 2.
        logger.log(Level.INFO,
                () -> "LAZY value=" + expensiveValue(calls));
        System.out.println("Calls after enabled supplier: "
                + calls.get());
    }

    private static String expensiveValue(AtomicInteger calls) {
        return "value-" + calls.incrementAndGet();
    }
}
```

Biên dịch và chạy từ thư mục chứa file, bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 LoggingConcatDemo.java
java LoggingConcatDemo
```

**Stdout chính xác của lần chạy với code trên**:

```text
FINE enabled: false
Calls after concatenation: 1
Calls after disabled supplier: 1
INFO | Order O-17 accepted
INFO | LAZY value=value-2
Calls after enabled supplier: 2
```

Giải thích:

1. `Logger.setLevel(Level.INFO)` làm `logger.isLoggable(Level.FINE)` trả về `false`.
2. Biểu thức `"EAGER value=" + expensiveValue(calls)` được tính **trước** `logger.fine(...)`. Bộ đếm tăng từ 0 lên 1 dù không có dòng FINE nào xuất ra.
3. Với `logger.log(Level.FINE, Supplier<String>)`, JUL xác định FINE không được chấp nhận nên **không gọi supplier**. Bộ đếm vẫn là 1.
4. `logger.info(...)` phát bản ghi INFO nên handler xuất thông điệp đơn giản: `INFO | Order O-17 accepted`.
5. Supplier ở mức INFO được gọi; `expensiveValue(calls)` trả về `value-2`. Handler ghi dòng INFO và sau đó bộ đếm bằng 2.

**Giới hạn của ví dụ:** `expensiveValue` không thật sự nặng; nó chỉ đếm lời gọi để minh họa thời điểm đánh giá. Code dùng handler đồng bộ ghi stdout và không cấu hình collector, định dạng JSON, ứng dụng đa luồng hay persistence. Trong hệ thống thật, mục tiêu không phải luôn loại bỏ `+`, mà là tránh công việc không cần thiết ở log bị tắt, nhất là khi đối số đắt hoặc dễ có tác dụng phụ.

## 6. Cách khắc phục thứ nhất: kiểm tra level trước khi tính chuỗi

Nếu dùng JUL và muốn tính message thủ công:

```java
// Đoạn minh họa trong phương thức có logger, order và buildSummary.
// Cần định nghĩa các biến/hàm này trong ứng dụng thực tế.
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Order summary: " + buildSummary(order));
}
```

Lúc FINE bị tắt, `buildSummary(order)` không chạy. Nhược điểm là có thêm nhánh kiểm tra; nếu code dùng backend khác với tên level khác, phải gọi API tương ứng (ví dụ SLF4J `logger.isDebugEnabled()`).

Hai giới hạn quan trọng:

- **Kiểm tra level không thay thế bộ lọc ở sink:** nếu FINE được logger chấp nhận nhưng handler/appender phía sau loại sự kiện, đoạn code vẫn tính chuỗi.
- **Không tách check và log trên một cấu hình thay đổi liên tục rồi dựa vào chúng như một giao dịch nguyên tử:** mức log có thể đổi giữa hai thời điểm; đây chỉ là tối ưu, không phải cơ chế kiểm soát truy cập hay bằng chứng audit.

Khi caller bắt buộc phải tính một giá trị phục vụ nghiệp vụ độc lập với logging, không cần cố làm lazy một cách giả tạo: chỉ cần truyền giá trị đã có sẵn vào log. Tối ưu có ý nghĩa nhất khi xử lý bổ sung **chỉ tồn tại để phục vụ message**.

## 7. Cách khắc phục thứ hai: Supplier<String> trong java.util.logging

Từ các phiên bản Java hiện đại, JUL cung cấp overload:

```java
// Trong ứng dụng Java có logger và buildSummary(order).
logger.log(Level.FINE, () -> "Order summary: " + buildSummary(order));
```

Phần bên trong lambda là *công thức tạo message*, không phải kết quả chuỗi đã được tạo ngay. Khi logger không chấp nhận level FINE, supplier không cần được đánh giá. Ưu điểm là không phải viết `if` cho từng chỗ và giữ biểu thức message gần lời gọi logger.

Tuy nhiên, lambda **không tạo ra sự bảo đảm về mọi khâu**:

- Các biểu thức được tính khi **tạo đối tượng lambda** nằm ngoài thân lambda vẫn chạy ngay. Ví dụ `String s = buildSummary(order); logger.log(Level.FINE, () -> s);` đã gọi `buildSummary` trước.
- Supplier có thể chụp biến/đối tượng; nếu đối tượng bị thay đổi ở các thời điểm khác nhau, thông điệp phải phản ánh snapshot đúng mục đích. Không dựa vào trạng thái mutable khi callback có thể bị trì hoãn.
- Khi level được bật nhưng handler hoặc filter ở bước sau loại log, vẫn có thể tốn chi phí gọi supplier.
- Không đưa chức năng nghiệp vụ, cập nhật dữ liệu hoặc thao tác có tác dụng phụ vào supplier logging. Việc log bị tắt không được phép làm thay đổi kết quả xử lý nghiệp vụ.

Ngoài overload supplier, JUL cũng có logging theo tham số định dạng dạng `{0}`:

```java
// Đoạn minh họa trong ứng dụng có logger và các biến.
logger.log(Level.INFO,
        "Order {0} completed after {1} attempts",
        new Object[]{orderId, attempts});
```

Trong JUL, formatter phù hợp có thể dùng `java.text.MessageFormat` để thay `{0}`, `{1}` bằng các tham số trong `LogRecord`. Đó là cú pháp của **JUL/MessageFormat**, không phải placeholder `{}` của SLF4J. Việc tạo đối số `new Object[]{expensive()}` vẫn chạy `expensive()` ở caller; formatter chỉ có thể trì hoãn bước chuyển message sang dạng hiển thị.

Không sao chép placeholder giữa các API một cách máy móc: JUL `{0}`, SLF4J `{}` và `String.format` dùng các cơ chế khác nhau.

## 8. Cách khắc phục thứ ba: Parameterized logging trong SLF4J

Trong dự án đã có SLF4J và logging backend được cấu hình, cú pháp phổ biến là:

```java
// Minh họa ở một class có logger SLF4J.
logger.debug("Loading orderId={} from cache", orderId);
logger.info("Order {} accepted after {} attempts",
        orderId, attempts);
```

**Ý nghĩa:** lưu message template và các tham số tách biệt để backend xử lý định dạng. Khi DEBUG bị tắt, hệ thống thường tránh phải tạo chuỗi thông điệp cuối cùng và tránh nhiều công việc định dạng, đặc biệt là `toString()` của tham số chưa cần xuất. Trong nhiều trường hợp đây là lựa chọn dễ đọc và đủ tốt hơn `"id=" + orderId`.

Nhưng cần phân biệt rõ:

```java
// expensiveSerialize(order) VẪN chạy trước lời gọi.
logger.debug("Order detail={}", expensiveSerialize(order));

// Có thể tránh serialize khi DEBUG bị tắt,
// nếu dùng API fluent của SLF4J 2.x:
logger.atDebug()
        .addArgument(() -> expensiveSerialize(order))
        .log("Order detail={}");
```

Ở dòng đầu, placeholder trì hoãn **định dạng** message nhưng không trì hoãn **tính toán** tham số. Ở ví dụ fluent, `addArgument(Supplier<?>)` cho phép trì hoãn tính toán giá trị trong supplier khi mức DEBUG không được bật. Đây là cú pháp của **SLF4J 2.x**; các dự án dùng SLF4J 1.x không thể mặc định sử dụng API fluent.

Nếu một phương thức logging nhận đối số varargs, việc tạo mảng/đánh giá đối số vẫn xảy ra theo luật gọi hàm Java. Với khối lượng log lớn, các overload một hoặc hai tham số thường giúp backend giảm overhead so với việc tạo mảng varargs. Tuy nhiên, tác động thực tế phụ thuộc API và phiên bản: không nên đưa ra kết luận hiệu năng tuyệt đối mà chưa đo trên môi trường mục tiêu.

**Lưu ý về lỗi:** khi cần ghi exception, ưu tiên overload cho phép truyền `Throwable` để backend giữ stack trace đúng cách:

```java
// Minh họa trong catch có orderId và exception "ex".
logger.warn("Gateway timeout for orderId={}", orderId, ex);
```

Ở SLF4J, đối số cuối là `Throwable` được xử lý theo quy ước API khi thích hợp. Nối `"Gateway timeout: " + ex` thường chỉ cho bản mô tả `toString()` của exception, có thể **mất stack trace** và khiến việc điều tra khó hơn. Không in nội dung exception có chứa bí mật nếu chưa có chính sách kiểm soát.

## 9. String.format, StringBuilder và các phương án khác

### 9.1. String.format không tự làm logging “lazy”

```java
// String.format(...) tạo ra String trước khi gọi logger.
logger.debug(String.format(
        "Order %s completed after %d attempts",
        orderId, attempts));
```

`String.format` là công cụ tạo chuỗi có quy tắc formatter/locale; nó **không tự trì hoãn** chỉ vì được đặt trong lời gọi logger. Với log bị tắt, vẫn có chi phí phân tích định dạng và tạo kết quả. Trường hợp yêu cầu định dạng phức tạp có thể dùng ở vị trí thích hợp, nhưng nếu backend hỗ trợ placeholder thì thường nên ưu tiên API logging để tránh xử lý không cần thiết.

### 9.2. StringBuilder hữu ích khi tích lũy nhiều phần, không giải quyết tính eager

```java
// Minh họa không phải chương trình chạy độc lập.
StringBuilder details = new StringBuilder();
for (String item : items) {
    details.append(item).append(';');
}
logger.debug("items=" + details);
```

`StringBuilder` thích hợp khi một chuỗi được xây dựng qua vòng lặp có nhiều lần nối. Nhưng ở đây, việc duyệt `items` đã xảy ra **trước khi** backend xét level DEBUG. Nếu chuỗi chỉ dành cho log, đặt toàn bộ bước xây dựng vào nhánh có check level hoặc vào supplier thích hợp.

Không tự động đổi mọi `"a=" + x + ", b=" + y` thành `new StringBuilder()...`: trên Java 17, trình biên dịch/JVM đã có tối ưu nối chuỗi; mã phức tạp hơn có thể không có lợi.

### 9.3. Text block, join và JSON serializer cũng tuân theo thời điểm đánh giá

`String.join(...)`, `StringBuilder`, text block chứa dữ liệu cố định, hay serializer JSON đều phải được gọi ở một thời điểm cụ thể. Việc bọc một thao tác tốn kém trong API “dễ đọc” không có nghĩa nó là lazy. Nếu tạo JSON chứa toàn bộ object trước `logger.debug(...)`, công việc đó vẫn phát sinh ngay cả khi DEBUG bị tắt.

Để ghi structured log, nên dùng API/encoder thích hợp để giữ các trường như `event`, `orderId`, `elapsedMs` riêng biệt. Đừng chỉ nối thủ công một chuỗi có vẻ giống JSON rồi cho rằng nó đã được escape, phân tích và lập chỉ mục an toàn.

## 10. Hiệu năng: nên tối ưu khi nào?

Có ba nhóm chi phí khác nhau:

1. **Đánh giá các toán hạng:** gọi getter phức tạp, duyệt collection, serialize, chuẩn bị dữ liệu bổ sung, gọi `toString()`.
2. **Xây dựng thông điệp:** nối chuỗi, định dạng số, escape/encode, tạo object trung gian.
3. **Logging pipeline và I/O:** filter, buffer, khóa, format, ghi stdout/file/network, collector/storage; nhiều hệ thống thường bị chi phối bởi phần này hơn bản thân một phép nối đơn giản.

Cách kiểm tra có căn cứ:

- Tìm các vị trí log tần suất cao, đặc biệt DEBUG/TRACE trong vòng lặp hoặc request hot path.
- Xác định biểu thức chỉ để log nào đang tính toán tốn kém khi level bị tắt.
- Đo CPU, allocation, throughput và latency bằng profiler hoặc benchmark có warm-up phù hợp; không suy luận hiệu năng chỉ từ số ký tự `+`.
- Nếu chạy JMH, benchmark phải giữ giá trị kết quả được tiêu thụ đúng cách, tránh dead-code elimination và xét ảnh hưởng của JVM JIT/GC; so sánh phiên bản JDK, API và cấu hình backend thực sự dùng.
- Đặt mục tiêu dựa trên độ trễ và chi phí hệ thống; giữ message rõ nghĩa và hữu ích cho điều tra.

Một thông điệp kiểu `logger.info("orderId=" + id)` có thể hoàn toàn hợp lý ở nhánh ghi không thường xuyên, với ID đã có sẵn. Tối ưu có giá trị nhất thường là bỏ `serializeEverything(request)` khỏi DEBUG đang tắt, giảm log spam, hoặc chọn pipeline/sink phù hợp.

**Điểm dễ bỏ sót:** một supplier hoặc template có thể giảm chi phí khi level bị tắt, nhưng nếu INFO luôn bật và log phát rất nhiều, chi phí I/O và ingestion vẫn tồn tại. Khi đó phải xem lại chính sách log, tần suất, buffering và mô hình truy vấn.

## 11. Tính đúng đắn và an toàn của message quan trọng hơn tốc độ

### 11.1. Log injection từ ký tự điều khiển

Giả sử user nhập tên hiển thị có newline. Nếu ứng dụng nối trực tiếp:

```java
// Minh họa một pattern có rủi ro.
logger.info("Login attempt user=" + untrustedUserName);
```

Người nhập có thể chèn newline, ký tự điều khiển hoặc chuỗi giống prefix của một dòng log khác, khiến người đọc nhầm một sự kiện thành nhiều dòng. Placeholder không **tự bảo đảm** xử lý injection: cần encoder/layout có escaping, log có cấu trúc và kiểm soát input trước khi ghi. Với JSON Lines, serializer phải escape dấu nháy, backslash, newline và ký tự điều khiển đúng chuẩn.

### 11.2. Dữ liệu nhạy cảm

Không nối hoặc đưa trực tiếp mật khẩu, OTP, cookie, access token, refresh token, khóa bí mật hay body request nhạy cảm vào log. Cũng không dựa vào `toString()` của một object nghiệp vụ có thể chứa các trường này. Dùng allowlist trường, ID nội bộ được phép và redaction tại nguồn. Nếu cần hỗ trợ kiểm toán, ghi actor/action/outcome cùng mã định danh đã được xác thực và thiết kế kho audit riêng khi cần độ bền/tính toàn vẹn.

### 11.3. Tác dụng phụ và dữ liệu thay đổi

```java
// Đừng gọi phương thức có tác dụng phụ chỉ để làm message.
logger.debug("Next sequence=" + sequence.incrementAndGet());
```

Ở đây bộ đếm **tăng ngay cả khi DEBUG tắt**. Nếu chuyển sang supplier, bộ đếm có thể **không tăng** khi log bị tắt. Cả hai đều cho thấy việc cập nhật trạng thái nghiệp vụ không được phụ thuộc vào logging.

Với async logging, tham số object mutable có thể bị thay đổi trước khi formatter chạy. Nếu điều cần ghi là **giá trị tại thời điểm sự kiện**, hãy chọn snapshot nhỏ, bất biến, được phép ghi (ví dụ ID và trạng thái dạng chuỗi/enum) tại điểm tạo sự kiện. Không đưa object sống có dữ liệu nhạy cảm vào queue rồi kỳ vọng mọi backend sẽ chụp đúng trạng thái.

## 12. Một số tình huống trước – sau

**Trường hợp A: Debug bị tắt, cần tránh serialize tốn kém**

```java
// Trước: serialize vẫn chạy khi DEBUG tắt.
logger.debug("payload=" + expensiveSerialize(payload));

// Sau nếu dùng SLF4J 2.x:
logger.atDebug()
        .addArgument(() -> expensiveSerialize(payload))
        .log("payload={}");
```

Chỉ đưa dữ liệu an toàn đã được lọc vào `expensiveSerialize`; không serialize toàn bộ payload chứa bí mật chỉ vì có supplier.

**Trường hợp B: Log biến thông thường bằng SLF4J**

```java
// Trước: thông điệp được tạo ở caller.
logger.info("Loaded orderId=" + orderId + ", status=" + status);

// Sau: template dễ đọc và backend có thể trì hoãn format.
logger.info("Loaded orderId={}, status={}", orderId, status);
```

Nếu `orderId` và `status` đều là dữ liệu sẵn có, lợi ích chủ yếu là độ rõ ràng và khả năng tránh format khi level bị loại; không mặc định đây là cải thiện hiệu năng đáng kể ở mọi chương trình.

**Trường hợp C: Logging exception**

```java
// Trước: chỉ nối biểu diễn exception vào message.
logger.warn("Order failed: " + ex);

// Sau: SLF4J nhận Throwable để ghi dấu vết lỗi.
logger.warn("Order failed for orderId={}", orderId, ex);
```

**Trường hợp D: Java thuần JDK muốn tránh tạo message**

```java
// Trước: luôn tính toán tốn kém.
logger.fine("trace=" + buildTraceSummary());

// Sau: dùng JUL Supplier<String>.
logger.log(Level.FINE, () -> "trace=" + buildTraceSummary());
```

Các đoạn trong mục này chỉ **minh họa vị trí code trong ứng dụng**, không phải chương trình chạy độc lập. Các ví dụ SLF4J cần đúng dependency, backend và khai báo logger của ứng dụng; ví dụ JUL cần logger của JUL.

## 13. Kiểm thử hành vi và hiệu năng

Không chỉ kiểm tra output; cần xác nhận cả **có hay không có đánh giá biểu thức**:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| DEBUG/FINE bị tắt với biểu thức nối chuỗi gọi hàm | Hàm vẫn chạy theo quy tắc đánh giá tham số của Java, dù không có bản ghi. |
| DEBUG/FINE bị tắt với supplier hợp lệ | Supplier không thực thi tại bước logger khi level bị tắt. |
| INFO bật với supplier | Message được tạo và có thể xuất tại handler phù hợp. |
| Logger bật nhưng handler/appender filter | Sự kiện vẫn có thể bị loại; tránh khẳng định supplier sẽ luôn không chạy. |
| Dữ liệu chứa dấu nháy, backslash, newline | Định dạng xuất đúng chuẩn; không tạo bản ghi giả hoặc làm vỡ JSON. |
| Object có `toString()` nặng | Đo thời điểm `toString()` chạy dưới từng kiểu API và cấu hình. |
| Object mutable khi logging async | Giá trị được ghi đáp ứng yêu cầu snapshot/event-time, không rò dữ liệu bất ngờ. |
| Exception | Backend giữ stack trace khi API hỗ trợ và không tiết lộ bí mật. |
| Benchmark hot path | Đo allocation/CPU/latency cùng level, backend và sink phù hợp; tránh đo một trường hợp không đại diện. |

Có thể tạo một counter như ví dụ ở mục 5 để chứng minh side effect. Với test chuyên nghiệp, dùng logger/backend test appender hoặc một `Handler` thử nghiệm thu thập bản ghi, tránh phụ thuộc timestamp và nội dung console mặc định vốn có thể thay đổi theo cấu hình.

## 14. Lỗi phổ biến và checklist áp dụng

Những lỗi cần tránh:

- Tin rằng `logger.debug("x=" + expensive())` sẽ bỏ qua `expensive()` khi DEBUG tắt.
- Tin rằng SLF4J `logger.debug("x={}", expensive())` là lazy đối với lời gọi `expensive()`.
- Coi mọi dấu `+` là cực kỳ chậm, bỏ qua tối ưu của Java 17 và bottleneck thật trong I/O.
- Tự nối hàng loạt giá trị không có nhãn/trường, khiến log khó tìm hoặc khó hiểu.
- Dùng `String.format(...)` trong DEBUG đang tắt và tưởng formatter chỉ chạy sau log-level check.
- Đổi `+` thành `StringBuilder` nhưng vẫn xây dựng toàn bộ message trước khi logger được gọi.
- Nhầm JUL `{0}` với SLF4J `{}` hoặc với `String.format("%s")`.
- Nối exception bằng `+` rồi làm mất stack trace cần điều tra.
- Chụp hoặc chuyển object mutable vào logging async mà không xác định event-time snapshot.
- Ghi bí mật hoặc dữ liệu không escape vào text/JSON log; placeholder không phải cơ chế bảo mật.
- Đặt tác dụng phụ nghiệp vụ trong biểu thức chỉ dành cho log.

**Checklist khi viết một log message:**

1. Chọn level phù hợp và xác định thông điệp có thực sự hữu ích ở mức đó.
2. Đánh giá liệu các toán hạng được dùng cho nghiệp vụ hay chỉ được tính để ghi log.
3. Với SLF4J, ưu tiên template `{}` cho các biến sẵn có; với xử lý đắt, cân nhắc Supplier/fluent API của phiên bản đang dùng.
4. Với JUL, dùng `Supplier<String>` hoặc `isLoggable(...)` khi muốn trì hoãn tạo chuỗi.
5. Ghi trường có ý nghĩa: event, outcome, ID được phép, correlation ID; giữ ngoại lệ theo cách backend hỗ trợ.
6. Kiểm soát dữ liệu nhạy cảm, escape ký tự nguy hiểm và giữ message/event schema ổn định.
7. Đo và kiểm thử ở nơi thật sự có chi phí: hot path, mức log bị tắt, logger/filter/sink, async và I/O.

**Ghi nhớ:** phép `+` trong Java là phép nối chuỗi hợp lệ và thường tiện dụng. Trong logging, điều cần hiểu là **phép nối và các hàm tạo đối số được thực thi trước lời gọi logger**; hãy dùng parameterized logging hoặc cách tạo thông điệp có trì hoãn khi cần tránh chi phí, đồng thời giữ bản ghi rõ nghĩa, an toàn và dễ truy vết.