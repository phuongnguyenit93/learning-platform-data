# Kế thừa cấu hình Logger trong Java Logging

## 1. Kế thừa cấu hình là gì?

Khi một ứng dụng Java có nhiều package và lớp, mỗi thành phần thường có Logger riêng để phân biệt nguồn phát sinh log. Việc cấu hình level hoặc đích ghi cho từng lớp sẽ khó duy trì nếu số lớp tăng lên hàng trăm. **Kế thừa cấu hình** cho phép Logger con dựa vào cấu hình của Logger cha ở những khía cạnh được thư viện logging hỗ trợ, nhờ đó có thể quản lý mức log chung theo một nhánh và chỉ ghi đè ở nơi thật sự cần.

Ví dụ, một hệ thống thanh toán có các Logger mang tên:

```text
""                                           (root logger)
└── com
    └── com.example
        └── com.example.payment
            ├── com.example.payment.InvoiceService
            └── com.example.payment.PaymentService
```

Nếu cấu hình mức `WARNING` tại `com.example.payment`, các Logger con chưa đặt level riêng thường kế thừa ngưỡng đó. Khi cần điều tra `PaymentService`, có thể đặt level riêng cho Logger này mà không tăng độ chi tiết toàn bộ ứng dụng.

**Điểm cốt lõi:** Trong `java.util.logging` (JUL), phải phân biệt **kế thừa level hiệu lực** và **chuyển bản ghi tới Handler của Logger cha**. Đó là hai cơ chế độc lập. Không phải mọi thuộc tính của Logger cha đều tự động được sao chép xuống Logger con.

Tài liệu tập trung vào `java.util.logging.Logger` có sẵn trong JDK 17+, đồng thời chỉ ra điểm tương đồng và giới hạn khi sử dụng SLF4J/Logback hoặc Log4j 2. Mọi ví dụ Java độc lập trong bài đều dùng JUL.

## 2. Hệ phân cấp Logger theo tên

Một cách tạo Logger phổ biến:

```java
Logger paymentLogger =
        Logger.getLogger("com.example.payment.PaymentService");
```

Đây là đoạn mã minh họa; cần import `java.util.logging.Logger`.

JUL tổ chức các Logger có tên theo cấu trúc phân cấp dùng dấu chấm (`.`). Khi tìm quan hệ cha–con, các Logger đã có trong `LogManager` quyết định ancestor gần nhất. Không bắt buộc mọi đoạn tên (`com`, `com.example`, ...) đều đang có một đối tượng Logger riêng. Nếu một Logger tổ tiên được tạo sau, quan hệ cha trực tiếp có thể được cập nhật phù hợp với hệ phân cấp.

`Logger.getParent()` trả Logger cha trực tiếp hiện tại. Logger gốc thường có tên rỗng `""`, được quản lý bởi `LogManager`; nó là điểm cuối của cây. Khi học cơ chế kế thừa, nên giữ tham chiếu đến các Logger cha dùng trong thí nghiệm, tránh phụ thuộc vào việc các Logger chỉ được giữ bằng tham chiếu yếu có tồn tại mãi hay không.

Một tên phân cấp giúp cấu hình tập trung theo module, nhưng **tên logger không phải tên request, người dùng hay giao dịch**. Các ID biến đổi liên tục nên nằm trong nội dung/metadata của log, không nên sinh Logger mới cho từng ID.

## 3. Level hiệu lực: phần kế thừa quan trọng nhất

### 3.1. `setLevel(null)` nghĩa là kế thừa

Trong JUL, `Logger.setLevel(Level)` đặt ngưỡng cho Logger. Nếu gọi:

```java
Logger parent = Logger.getLogger("com.example.payment");
Logger child = Logger.getLogger(
        "com.example.payment.PaymentService");

parent.setLevel(Level.WARNING);
child.setLevel(null);
```

thì Logger con không có ngưỡng riêng. Nó tìm Logger cha gần nhất có level khác `null` và dùng level đó làm **level hiệu lực**. Trong ví dụ, kết quả hiệu lực của `child` là `WARNING`.

Hệ quả:

```java
child.info("payment.started");       // Không qua ngưỡng WARNING
child.warning("payment.delayed");   // Qua ngưỡng WARNING
child.severe("payment.failed");     // Qua ngưỡng WARNING
```

Ba khối mã trên là các mảnh minh họa trong cùng ngữ cảnh, chưa phải một chương trình chạy độc lập.

Quy tắc tìm ngưỡng có thể viết:

```text
Logger đang ghi có level riêng?
  ├── Có  → dùng level đó làm level hiệu lực.
  └── Không (level == null)
         → hỏi Logger cha gần nhất
         → tiếp tục cho đến Logger có level khác null.
```

JUL định nghĩa root Logger có level xác định; mặc định thường là `INFO`, nhưng file cấu hình hoặc mã khởi tạo có thể thay đổi. Không suy ra mọi môi trường luôn dùng `INFO`.

### 3.2. `getLevel()` không trả "level đã kế thừa"

Đây là một nguồn nhầm lẫn thường gặp:

```java
child.setLevel(null);
System.out.println(child.getLevel()); // null
System.out.println(child.isLoggable(Level.INFO));    // false nếu cha WARNING
System.out.println(child.isLoggable(Level.WARNING)); // true nếu cha WARNING
```

`getLevel()` trả **giá trị được đặt trực tiếp trên Logger**, vì vậy `null` nghĩa là "đang kế thừa". Nó không trả đối tượng `Level.WARNING` đã được tính từ cha. `isLoggable(level)` phản ánh phép kiểm tra ngưỡng trên Logger hiện tại, phù hợp để xác định một mức có thể được chấp nhận hay không. Tuy nhiên, `isLoggable` **không bảo đảm log sẽ hiện ra**: Filter của Logger, Handler và thiết bị đầu ra còn có thể loại log.

### 3.3. Ghi đè cấu hình ở Logger con

Khi cần tăng mức chi tiết cho một lớp:

```java
child.setLevel(Level.FINE);
```

Logger con dùng `FINE` bất kể cha đang đặt `WARNING`. Các lời gọi `fine()`, `info()`, `warning()`, `severe()` có thể qua bước kiểm tra level trên Logger con.

Khi không cần cấu hình riêng nữa:

```java
child.setLevel(null);
```

Logger lại kế thừa level hiệu lực từ nhánh cha hiện tại. Nếu sau đó thay `parent.setLevel(Level.SEVERE)`, Logger con có level `null` sẽ sử dụng ngưỡng `SEVERE`; Logger con đã đặt `FINE` riêng vẫn dùng `FINE`.

`Level.ALL` và `Level.OFF` cũng là cấu hình tường minh, không có nghĩa kế thừa. `ALL` cho phép mọi mức đi qua phép kiểm tra ngưỡng; `OFF` tắt việc chấp nhận thông điệp ở Logger đang xét. Phải phân biệt "không cấu hình riêng" (`null`) với "cấu hình cho phép tất cả" (`ALL`).

| Level của con | Level của cha gần nhất | Level hiệu lực của con | Ý nghĩa |
| --- | --- | --- | --- |
| `null` | `WARNING` | `WARNING` | Kế thừa |
| `FINE` | `WARNING` | `FINE` | Con ghi đè |
| `null` | `null`, ông đặt `INFO` | `INFO` | Tìm tiếp ancestor |
| `OFF` | `FINE` | `OFF` | Con chủ động tắt |
| `ALL` | `WARNING` | `ALL` | Con chủ động chấp nhận mọi level |

### 3.4. Level được kiểm tra tại điểm phát sinh log

Trong JUL, khi code gọi `child.log(...)`, Logger con dùng **level hiệu lực của chính nó** để quyết định tạo/tiếp nhận bản ghi.

Nếu con có `FINE` và cha có `WARNING`, một bản ghi `FINE` đã được Logger con chấp nhận vẫn có thể được chuyển tới Handler gắn ở cha. Logger cha **không thực hiện lại** phép kiểm tra level của chính nó trên bản ghi do Logger con đã phát ra. Handler ở cha sẽ lọc theo level riêng của **Handler**.

Đây là lý do một đích ghi vẫn có thể hiển thị `FINE` từ Logger con dù Logger cha đặt `WARNING`, miễn Handler nhận log có cho phép `FINE`.

## 4. Kế thừa level khác với chuyển tiếp tới Handler cha

Trong JUL, mỗi Logger có thể có Handler gắn trực tiếp. Sau khi một bản ghi được Logger con chấp nhận, nó có thể được đưa qua:

1. Các Handler gắn trực tiếp tại Logger con.
2. Các Handler gắn ở Logger cha.
3. Các Handler của những ancestor cao hơn, cho đến khi gặp ranh giới tắt chuyển tiếp hoặc cuối cây.

Cơ chế thứ hai và thứ ba gọi là **parent-handler propagation**. Mặc định `getUseParentHandlers()` thường là `true`.

Ví dụ:

```text
com.example.payment  [level=WARNING]
  └── Handler console [level=INFO]
      ▲
      | Bản ghi được chuyển lên nếu con bật useParentHandlers
      |
com.example.payment.PaymentService [level=FINE, không có Handler riêng]
      |
      +-- fine("details") --> qua ngưỡng FINE ở con
                              --> qua ngưỡng INFO của Handler? KHÔNG
      +-- info("done")   --> qua ngưỡng FINE ở con
                              --> qua ngưỡng INFO của Handler? CÓ
```

Trong sơ đồ, Handler nhận và tự lọc từng bản ghi. `FINE` bị Handler `INFO` loại. Khi đổi **chỉ Handler** sang `Level.ALL` hoặc `Level.FINE`, bản ghi `FINE` từ con mới có thể xuất hiện. Không cần đổi level của Logger cha.

### 4.1. `setUseParentHandlers(false)` không tắt kế thừa level

```java
child.setLevel(null);                 // Tiếp tục kế thừa level cha
child.setUseParentHandlers(false);   // Không chuyển bản ghi lên Handler cha
```

Hai lệnh có mục đích hoàn toàn khác nhau:

- `setLevel(null)`: lấy **ngưỡng level hiệu lực** từ ancestor.
- `setUseParentHandlers(false)`: ngừng chuyển **bản ghi đã được chấp nhận** lên Handler ancestor.

Nếu Logger con không có Handler gắn trực tiếp và tắt parent handlers, sự kiện có thể vượt qua level/filter của Logger nhưng **không có đích ghi nào nhận được**. Vì vậy, `isLoggable(Level.WARNING)` có thể trả `true` mà không hề thấy dòng `WARNING`.

### 4.2. Vì sao cùng một log xuất hiện hai lần?

Giả sử bạn gắn ConsoleHandler vào cả Logger con và Logger cha, đồng thời để `useParentHandlers=true` ở con. Một bản ghi có thể được xuất ra console **hai lần**: một bởi Handler riêng của con, một bởi Handler của cha.

Cách xử lý dựa trên cấu trúc mong muốn:

- Nếu cần một pipeline tập trung: gắn Handler vào ancestor/root và để logger con chuyển tiếp.
- Nếu một module có Handler/đích ghi riêng: gắn Handler tại module rồi cân nhắc `setUseParentHandlers(false)` ở ranh giới đó.
- Nếu cần gửi tới nhiều đích thật sự: cho phép nhiều Handler/Appender, nhưng đảm bảo việc lặp là có chủ đích.

Không sửa bằng cách vô hiệu hóa tất cả Handler trên root nếu ứng dụng khác còn dùng root. Hãy xác định Logger nào sở hữu Handler và ranh giới chuyển tiếp của nhánh đang lỗi.

## 5. Thuộc tính nào kế thừa, thuộc tính nào không?

Tên gọi "kế thừa cấu hình" dễ gây hiểu nhầm rằng mọi thuộc tính của Logger con là bản sao của cha. Với JUL, phân biệt như sau:

| Thuộc tính hoặc hành vi | Quy tắc trong JUL |
| --- | --- |
| Ngưỡng `Level` hiệu lực | **Có kế thừa** khi level đặt trực tiếp là `null` |
| `getLevel()` | Chỉ phản ánh level đặt trực tiếp, có thể là `null` |
| Handler gắn vào Logger cha | **Có thể nhận bản ghi từ con qua propagation**; không được sao chép thành Handler của con |
| `useParentHandlers` | Cờ riêng trên mỗi Logger; điều khiển chặng chuyển tiếp từ Logger đó |
| `Filter` gắn trên Logger cha | **Không tự động lọc** các bản ghi được phát trực tiếp bởi Logger con khi chuyển lên |
| Level/Filter của Handler cha | **Vẫn áp dụng** cho bản ghi chuyển từ Logger con tới Handler đó |
| Formatter/Encoder | Do Handler/đích ghi sở hữu; không có quy tắc "con tự sao chép Formatter của cha" |
| Tên Logger và metadata nguồn | Thuộc Logger/bản ghi phát sinh; khi chuyển tới Handler cha, bản ghi vẫn mang tên Logger đã phát log |

Với một `Logger Filter`, có thể hình dung:

```text
parent.setFilter(record -> false);

parent.warning("own event");  // Bị Filter của parent bỏ
child.warning("child event"); // Có thể vẫn tới Handler gắn trên parent
```

Ở đây giả sử `child` có ngưỡng phù hợp, Filter của con cho phép, `useParentHandlers=true`, Handler nhận `WARNING` và không có Filter khác chặn. **Filter gắn vào Logger cha chỉ lọc lời gọi được Logger cha tự tiếp nhận**, không tự chạy lại cho bản ghi Logger con truyền tới Handler của cha. Muốn lọc mọi event đi qua một đích dùng chung, đặt Filter tại **Handler** đó.

Một số logging backend ngoài JUL có quy tắc inheritance/additivity riêng và hỗ trợ marker, turbo filter hoặc bộ lọc nhiều cấp. Không nên suy đoán cấu hình JUL sẽ được áp dụng nguyên xi sang Logback/Log4j 2.

## 6. Luồng xử lý của một bản ghi với cấu hình kế thừa

Ví dụ nhánh có ba level:

```text
root Logger                         [level=INFO]
   |
   +-- com.example                  [level=null]
         |
         +-- com.example.payment    [level=WARNING]
               |
               +-- com.example.payment.PaymentService [level=null]
```

`PaymentService` có level hiệu lực `WARNING`. Một lời gọi `logger.info(...)` bị loại **ngay tại Logger phát sinh**. Một lời gọi `logger.warning(...)` được chấp nhận rồi có thể chuyển tới Handler của các Logger tổ tiên tùy cấu hình parent propagation.

Nếu đổi `PaymentService` thành `FINE`, các lời gọi `fine()` qua Logger con, nhưng đường đi ra console vẫn phụ thuộc mức trên ConsoleHandler. Vì vậy, để chẩn đoán thiếu log, nên đi theo trình tự:

```text
Mã thật sự gọi logger?
  -> Logger hiện tại đang dùng level hiệu lực nào?
  -> Filter tại Logger hiện tại có cho phép?
  -> Logger hiện tại có Handler riêng?
  -> useParentHandlers trên đường từ con lên cha có bật?
  -> Handler trên từng chặng có cho phép level và filter?
  -> Formatter, buffer, console/file/collector có xuất và lưu?
```

Đặt level `FINE` trên một Logger không thể buộc Handler có level `INFO` xuất các bản ghi `FINE`; đồng thời tăng level Handler cũng không thể khôi phục bản ghi mà Logger đã loại trước đó.

## 7. Ví dụ Java 17 có thể chạy: kế thừa, ghi đè và chuyển tiếp

Chương trình dưới đây dùng duy nhất JUL có sẵn trong JDK. Chúng ta tạo Logger cha `edu.example.billing` và Logger con `edu.example.billing.PaymentService`, gắn một Handler xuất ra **stdout**. Formatter được cố ý viết đơn giản để đầu ra có thể so sánh chính xác.

Chương trình minh họa năm điều:

1. Con có level `null` nên kế thừa `WARNING` của cha.
2. Con đặt level `FINE` riêng thì có thể phát log `FINE`, dù cha còn `WARNING`.
3. Filter `false` của Logger cha không ngăn bản ghi do con chuyển tới Handler cha.
4. Handler có level `SEVERE` sẽ bỏ `INFO` dù Logger con cho phép.
5. Tắt `useParentHandlers` ở con làm mất đường đến Handler cha, nhưng không làm mất level đã đặt của con.

Lưu tệp **`LoggerInheritanceDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class LoggerInheritanceDemo {
    public static void main(String[] args) {
        Logger parent = Logger.getLogger("edu.example.billing");
        Logger child =
                Logger.getLogger("edu.example.billing.PaymentService");

        Handler sink = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " logger=" + record.getLoggerName()
                        + " message=" + formatMessage(record)
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        sink.setLevel(Level.ALL);
        parent.setLevel(Level.WARNING);
        parent.setUseParentHandlers(false);
        parent.addHandler(sink);
        child.setLevel(null);
        child.setUseParentHandlers(true);

        try {
            System.out.println("stage1 info="
                    + child.isLoggable(Level.INFO)
                    + " warning=" + child.isLoggable(Level.WARNING));
            child.info("event=child.info");
            child.warning("event=child.warning");

            child.setLevel(Level.FINE);
            System.out.println("stage2 fine="
                    + child.isLoggable(Level.FINE));
            child.fine("event=child.fine");

            parent.setFilter(record -> false);
            child.warning("event=child.passesParentFilter");
            parent.warning("event=parent.blockedByFilter");
            parent.setFilter(null);

            sink.setLevel(Level.SEVERE);
            System.out.println("stage3 info="
                    + child.isLoggable(Level.INFO));
            child.info("event=child.filteredBySink");
            child.severe("event=child.severe");

            child.setUseParentHandlers(false);
            child.severe("event=child.notForwarded");
            System.out.println("stage4 parentHandlers="
                    + child.getUseParentHandlers());
        } finally {
            parent.removeHandler(sink);
            sink.flush();
            parent.setFilter(null);
            child.setUseParentHandlers(true);
            child.setLevel(null);
            parent.setUseParentHandlers(true);
            parent.setLevel(null);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LoggerInheritanceDemo.java
java LoggerInheritanceDemo
```

**stdout chính xác khi chạy chương trình:**

```text
stage1 info=false warning=true
WARNING logger=edu.example.billing.PaymentService message=event=child.warning
stage2 fine=true
FINE logger=edu.example.billing.PaymentService message=event=child.fine
WARNING logger=edu.example.billing.PaymentService message=event=child.passesParentFilter
stage3 info=true
SEVERE logger=edu.example.billing.PaymentService message=event=child.severe
stage4 parentHandlers=false
```

Giải thích các dòng output:

- `stage1`: con được đặt level `null`, nên `INFO` bị bỏ tại con; `WARNING` được đưa tới Handler cha.
- `stage2`: con có level riêng `FINE`; Filter Logger cha không ngăn bản ghi của con đi tới Handler cha. Ngược lại, lời gọi `parent.warning(...)` bị Filter của **parent** chặn, nên không có `event=parent.blockedByFilter`.
- `stage3`: `child.isLoggable(INFO)` vẫn `true` vì con đang dùng `FINE`, nhưng Handler đã đổi ngưỡng thành `SEVERE`; `INFO` không xuất hiện, `SEVERE` xuất hiện.
- `stage4`: con tắt `useParentHandlers`; vì con không có Handler riêng, `event=child.notForwarded` không được ghi ra stdout.

Lệnh `parent.setUseParentHandlers(false)` trong mã ngăn Handler của root in thêm bản ghi, nên output không lặp. `publish()` gọi `flush()` sau mỗi event để thứ tự các dòng dễ quan sát. Ví dụ không gọi `sink.close()` vì `StreamHandler` gắn trực tiếp với `System.out` có thể đóng luôn stdout khi đóng Handler. Chương trình dạng demo này chỉ chạy một lần; trong ứng dụng thật, Handler do hệ logging quản lý và phải được đóng/flush theo vòng đời thích hợp.

**Điểm đáng nhớ:** một bản ghi có thể vượt qua level của Logger con nhưng không tới đích ghi; và một bản ghi đã được con chấp nhận **không bị kiểm tra lại theo level hoặc Filter của Logger cha** khi truyền lên Handler của cha.

## 8. Đặt cấu hình theo package bằng `logging.properties`

Thay vì gọi `setLevel()` ở nhiều lớp, ứng dụng JUL có thể đưa ngưỡng vào file cấu hình. Ví dụ file `logging.properties`:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

com.example.payment.level = WARNING
com.example.payment.PaymentService.level = FINE
```

Để yêu cầu JVM dùng file này ngay khi hệ logging khởi tạo:

```bash
java -Djava.util.logging.config.file=logging.properties YourMainClass
```

`YourMainClass` ở đây là **tên lớp chính của ứng dụng bạn**, không phải lớp mẫu có sẵn trong bài. File cấu hình này là ví dụ triển khai ở ứng dụng phù hợp, không phải output của `LoggerInheritanceDemo` (demo chủ động đặt level và Handler trong mã).

Trong cấu hình trên:

- Root đặt `INFO`.
- Nhánh `com.example.payment` đặt `WARNING`.
- `PaymentService` đặt `FINE` riêng nên không bị giới hạn bởi ngưỡng Logger cha.
- ConsoleHandler cho phép tới `FINE`, vì vậy bản ghi `FINE` từ `PaymentService` có cơ hội xuất ra console khi không có filter khác chặn.

Khi muốn tất cả lớp con quay về chính sách nhánh cha, bỏ cấu hình level riêng của lớp con rồi áp dụng cấu hình theo cơ chế quản lý của ứng dụng. Trên chương trình đang chạy, hiệu lực thay đổi phụ thuộc khả năng nạp lại cấu hình của `LogManager`/framework và những thiết lập được code thực hiện sau đó; không mặc định sửa file là có hot reload.

Việc chọn `java.util.logging.config.file` cần diễn ra đủ sớm, thường qua tham số JVM trước khi logging được khởi tạo. Nếu Spring Boot hoặc framework khác đang cung cấp logging backend riêng, quản lý cấu hình theo **backend thực tế** thay vì mặc định file JUL này là nguồn cấu hình cuối cùng.

## 9. Khi dùng SLF4J, Logback hoặc Log4j 2

Java có nhiều tầng API/backend logging, cần định danh đúng cơ chế:

- **SLF4J** cung cấp `org.slf4j.Logger` dưới dạng facade. Chính backend được liên kết mới quyết định cấu hình level, logger hierarchy, appender và quy tắc phân phối event.
- **Logback** hỗ trợ logger phân cấp theo tên: khi level không đặt ở logger hiện tại, level hiệu lực lấy từ ancestor phù hợp. Appender additivity quyết định event có tiếp tục đi tới appender của ancestor hay không. Đây là khái niệm tương tự **level inheritance và handler propagation**, nhưng API và cách cấu hình khác JUL.
- **Log4j 2** sử dụng các `LoggerConfig` theo tên trong `Configuration`. Một Logger liên kết tới `LoggerConfig` phù hợp, và cơ chế additivity quy định luồng chuyển sự kiện tới các appender của logger config tổ tiên. Đừng mặc định từng Logger đối tượng trong Log4j 2 có một `setLevel(null)` hoạt động giống JUL.

Vì thế khi thấy `DEBUG` không xuất hiện trong ứng dụng dùng SLF4J, cần xác định backend và cấu hình thực tế, rồi xem đồng thời level hiệu lực, filter, additivity và level/filter của appender. Không sao chép nguyên các phương thức JUL vào mã dùng SLF4J.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| `getLevel()` trả `null` nên tưởng Logger bị tắt | `null` trong JUL có nghĩa kế thừa | Kiểm tra ancestor gần nhất và `isLoggable()` |
| Đặt `FINE` ở Logger con nhưng không thấy log | Handler vẫn ở `INFO`/`WARNING`, hoặc filter chặn | Kiểm tra level và filter của từng Handler trên đường phân phối |
| Đổi level cha nhưng một lớp con không thay đổi | Lớp con có level tường minh | Xem `getLevel()`; đặt lại `null` nếu thực sự muốn kế thừa |
| `isLoggable(INFO)=true` nhưng log im lặng | Không có Handler nhận được hoặc bị chặn ở Filter/Handler | Kiểm tra `getUseParentHandlers()`, Handler trực tiếp và ancestor |
| Log bị ghi hai lần | Handler ở cả con và cha, bật propagation | Giữ một đường xuất mặc định hoặc tắt additivity/parent handlers tại nhánh có đích riêng |
| Tắt parent handlers để tránh trùng nhưng mất toàn bộ log | Logger con không có Handler trực tiếp | Gắn Handler phù hợp hoặc khôi phục propagation sau khi xử lý trùng đúng nguyên nhân |
| Filter của cha không chặn log con | JUL không áp Filter của Logger cha lên event con khi truyền handler | Gắn filter tại Handler chung nếu muốn lọc mọi event đi qua đích này |
| Muốn bật log cho một package nhưng cả ứng dụng quá ồn | Thay đổi level ở root hoặc handler toàn cục | Cấu hình nhánh Logger cụ thể; kiểm soát chính sách của đích ghi |
| Cấu hình trong file có vẻ không tác dụng | File nạp sau logging init, code ghi đè hoặc backend khác xử lý | Xác nhận tham số JVM, thứ tự khởi tạo và backend thực tế |

### Quy trình điều tra khi log mất

1. Xác nhận ứng dụng thực sự chạy đến lời gọi logger.
2. Xác định **tên Logger** của lời gọi và cây ancestor đang có.
3. Tìm level đặt trực tiếp (`getLevel()`) và level hiệu lực; kiểm tra `isLoggable(level)`.
4. Xem Filter của Logger phát sinh sự kiện.
5. Liệt kê các Handler gắn trực tiếp và trạng thái `useParentHandlers` qua từng chặng.
6. Kiểm tra level/Filter của Handler, formatter, console/file và collector.
7. Nếu có hệ thống logging bất đồng bộ, kiểm tra queue, backpressure, flush/shutdown.

Quy trình này tách bạch việc event bị chặn **trước khi tạo/đưa vào pipeline** với việc event đã được Logger chấp nhận nhưng bị chặn **ở đường xuất**.

## 11. Checklist áp dụng vào dự án

- Đặt tên Logger ổn định theo lớp hoặc nhóm chức năng; không tạo Logger riêng cho mỗi request.
- Chọn level mặc định cho root và các nhánh quan trọng; ghi đè ở Logger con chỉ khi có lý do rõ ràng.
- Dùng `setLevel(null)` trong JUL khi muốn quay lại kế thừa; không nhầm với `ALL` hoặc `OFF`.
- Xác định vị trí sở hữu Handler/Appender và chính sách parent handlers/additivity để tránh log trùng hoặc không có đích.
- Đánh giá level và Filter trên **cả Logger phát sinh lẫn Handler nhận**, thay vì chỉ nhìn level của ancestor.
- Không giả định Logger Filter của cha là bộ lọc chung cho mọi event con; filter chung nên đặt tại chặng đầu ra phù hợp.
- Không bật `FINE`/DEBUG toàn hệ thống dài hạn chỉ để điều tra một lớp: có thể tăng chi phí, tạo log nhiễu và lộ dữ liệu.
- Chọn đúng API/backend đang chạy (JUL, SLF4J + Logback, Log4j 2) và kiểm tra kết quả thực bằng các sự kiện có mức khác nhau.
- Kiểm tra cả kịch bản logger con có level riêng, logger con kế thừa, Handler chặn, tắt propagation và Handler ở nhiều tầng.

**Kết luận:** Trong JUL, **level hiệu lực được kế thừa khi `Logger.getLevel() == null`**, còn **Handler của Logger cha nhận log do cơ chế chuyển tiếp `useParentHandlers`**. Phân biệt hai quy tắc này giúp cấu hình chính xác từng nhánh logger, tránh log trùng và lý giải vì sao cùng một sự kiện có thể bị loại ở Logger hoặc ở đích ghi.
