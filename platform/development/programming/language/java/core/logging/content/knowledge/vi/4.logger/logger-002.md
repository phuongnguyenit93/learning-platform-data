# Tên logger trong Java

Trong hệ thống logging, **tên logger** (*logger name*, đôi khi gọi là *category*) là chuỗi định danh nguồn phát sinh một sự kiện log. Tên này giúp người đọc biết thông điệp đến từ khu vực nào của chương trình và cho phép cấu hình mức độ, bộ lọc hoặc nơi xuất log theo từng lớp, package hay nhóm chức năng. Tên logger là một phần metadata của bản ghi; nó không phải nội dung message, mức độ nghiêm trọng, tên tệp log hay mã định danh request.

Ví dụ, thông điệp `Order accepted` có thể được phát bởi logger mang tên `com.example.orders.OrderService`. Khi đọc dòng log, ta có thể phân biệt sự kiện đến từ xử lý đơn hàng hay từ `com.example.payments.PaymentService` ngay cả khi hai nơi dùng message tương tự.

## 1. Tên logger là gì và khác những thông tin còn lại ra sao?

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Logger name** | Định danh của logger phát sinh event. | `com.example.orders.OrderService` |
| **Logger** | Đối tượng/API dùng để phát sinh log; có thể lấy qua tên hoặc lớp. | `Logger.getLogger("com.example.orders.OrderService")` |
| **Message** | Mô tả sự kiện đã xảy ra. | `event=order.accepted orderId=42` |
| **Level** | Độ quan trọng hoặc mục đích chẩn đoán. | `INFO`, `WARNING`, `FINE` trong JUL |
| **Source class/method** | Metadata về lớp/phương thức nguồn, nếu framework thu thập được. | `OrderService.placeOrder`; không bắt buộc trùng tên logger. |
| **Thread / request ID** | Luồng thực thi hoặc ngữ cảnh một yêu cầu. | `worker-4`, `req-17`; nên là field riêng. |
| **Handler / appender** | Thành phần ghi event đến đầu ra; khác với tên logger. | `ConsoleHandler`, file appender |

Trong Java Util Logging (**JUL**, package `java.util.logging`), `Logger.getName()` trả về tên logger. Với logger được tạo bằng `Logger.getLogger(name)`, tên chính là chuỗi đã cung cấp. JUL cũng có logger gốc (*root logger*) với tên là chuỗi rỗng `""` và anonymous logger có tên `null`; hai trường hợp này không phải mẫu nên dùng cho logger nghiệp vụ thông thường.

Tên logger không chứng minh một lớp Java tương ứng thực sự tồn tại. Lệnh `Logger.getLogger("orders.payment")` hợp lệ dù dự án không có package hay class mang tên đó. Quy ước đặt tên theo package/class là quyết định thiết kế giúp tên rõ nghĩa và dễ cấu hình.

### Vì sao tên logger hữu ích?

- **Xác định nơi phát sinh:** khi thấy `com.example.orders.OrderService`, người bảo trì có điểm bắt đầu điều tra.
- **Phân vùng cấu hình:** có thể bật `FINE/DEBUG` cho một phần của ứng dụng mà không bật cho toàn hệ thống.
- **Lọc và tìm kiếm:** nhóm log theo package, thành phần hoặc service; đưa logger name vào formatter/JSON field.
- **Giữ ý nghĩa ổn định:** cùng một loại thành phần sử dụng một tên nhất quán qua các request; giá trị động nằm trong thuộc tính sự kiện.

## 2. Những chiến lược đặt tên phổ biến

### 2.1. Đặt tên theo tên đầy đủ của class

Đây là lựa chọn mặc định phù hợp với phần lớn mã ứng dụng. Nếu lớp nằm ở package `com.example.orders` và có tên `OrderService` thì tên logger là `com.example.orders.OrderService`.

Với JUL (có sẵn trong JDK), đoạn sau là **mẫu khai báo trong một lớp**, không phải chương trình độc lập:

```java
package com.example.orders;

import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void accept(String orderId) {
        LOG.info("event=order.accepted orderId=" + orderId);
    }
}
```

`OrderService.class.getName()` trả về tên nhị phân đầy đủ của lớp; với lớp trên là `com.example.orders.OrderService`. Cách viết này tránh lỗi gõ sai chuỗi khi đổi package, dễ tìm nguồn mã và nhất quán với thông lệ một logger cho một class. Trong code sản xuất, dữ liệu `orderId` cần được kiểm soát trước khi đưa vào log; có thể dùng overload nhận tham số thay vì nối chuỗi nếu muốn tránh dựng message không cần thiết.

Với **SLF4J**, mẫu thông dụng tương tự, nhưng cần có thư viện `slf4j-api` và một provider/backend phù hợp trong dependencies; đoạn sau **không biên dịch chỉ với JDK thuần**:

```java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accept(String orderId) {
        LOG.info("event=order.accepted orderId={}", orderId);
    }
}
```

Hai mẫu cố gắng đạt cùng một logger name khi lớp không bị thay đổi, nhưng **cú pháp message parameter khác nhau**: JUL thường dùng `{0}`, `{1}` còn SLF4J thường dùng `{}`. SLF4J là facade; cách ghi ra console/file, kế thừa cấu hình và bộ lọc thực tế do provider/backend quyết định.

### 2.2. Đặt tên theo package hoặc nhóm chức năng

Khi nhiều lớp cùng cần một nhóm log chung, có thể đặt tên ổn định như `com.example.orders`, `com.example.payments` hoặc `application.scheduling`:

```java
// Mẫu minh họa JUL, không phải chương trình độc lập.
java.util.logging.Logger orders =
        java.util.logging.Logger.getLogger("com.example.orders");
orders.info("event=order.batch_started");
```

Đặt tên theo nhóm hữu ích khi cấu hình theo phân hệ là ưu tiên chính. Đổi lại, nếu mọi lớp chỉ dùng `com.example.orders`, log sẽ khó nhận biết class cụ thể trừ khi có thêm `component`, source class hoặc trường khác. Với phần lớn ứng dụng, **đặt tên theo class và cấu hình theo prefix package** thường cân bằng tốt hơn.

Một tên category tùy biến như `security.authentication` hay `billing.audit` vẫn hợp lệ về mặt API, nhưng nó nên được tài liệu hóa và dùng nhất quán. Riêng các yêu cầu audit cần cơ chế lưu trữ và độ bền phù hợp; đặt tên logger có chữ `audit` không tự biến log thành audit trail đáng tin cậy.

### 2.3. Nên chọn kiểu nào?

| Nhu cầu | Tên gợi ý | Lưu ý |
| --- | --- | --- |
| Truy nguồn đến lớp cụ thể | `com.example.orders.OrderService` | Mặc định hợp lý, dùng `OrderService.class.getName()`. |
| Bật cấu hình cho nhiều lớp liên quan | Prefix `com.example.orders` | Giữ logger từng class; áp dụng cấu hình mức package. |
| Một sự kiện từ nhiều lớp cùng thuộc subsystem | `com.example.inventory` | Phải cân nhắc mất định danh class và bổ sung metadata. |
| Tìm request/order đang điều tra | Giữ logger name ổn định; ghi `requestId` / `orderId` vào event | Không tạo logger mới theo từng request hoặc ID. |

## 3. Tên logger và cấu trúc phân cấp

Nhiều hệ thống logging Java hỗ trợ đặt tên theo cấu trúc phân cấp, với dấu chấm phân cách các cấp.

```text
com
└── example
    ├── orders
    │   ├── OrderService
    │   └── OrderRepository
    └── payments
        └── PaymentService
```

Đây là **sơ đồ tên**, không phải cây kế thừa class Java. Tên `com.example.orders.OrderService` nằm dưới prefix `com.example.orders` theo quy ước. Các lớp không cần kế thừa nhau; tên chỉ là chuỗi định danh.

### Cụ thể trong java.util.logging

- JUL quản lý quan hệ *parent logger* giữa các logger có tên theo các prefix cách nhau bằng dấu chấm. Logger cha trực tiếp được chọn theo các logger hiện hữu trong `LogManager`; các mức trung gian không nhất thiết đều có đối tượng logger đang tồn tại.
- Mức hiệu lực (*effective level*) của một logger có level là `null` được tìm từ cha gần nhất có level xác định. Ví dụ, logger con có level `null` có thể dùng `INFO` do logger cha thiết lập.
- Khi `useParentHandlers=true` (mặc định cho logger thông thường), một record đã được logger con chấp nhận có thể được chuyển đến handler của logger cha, rồi tiếp tục đến các cha cao hơn, trừ khi bị chặn bởi cấu hình truyền lên.
- **Kế thừa level khác với chuyển record đến handler cha.** Gọi `setUseParentHandlers(false)` không có nghĩa là tắt kế thừa level.
- Handler cũng có mức lọc riêng. Một event bị loại ở logger sẽ không được “cứu lại” bởi handler có ngưỡng thấp hơn. Nếu record đến được handler, handler kiểm tra level/filter của nó.
- Nếu cả logger con và logger cha đều có handler, đồng thời bật truyền lên cha, có thể thấy một sự kiện xuất hiện **nhiều lần** tại các đầu ra tương tự.

Trong SLF4J, quan hệ category, effective level và cách truyền đến appender phụ thuộc backend (ví dụ Logback hoặc Log4j 2). Vì vậy không nên coi mọi chi tiết của JUL là hợp đồng áp dụng y nguyên cho mọi logger framework.

## 4. Ví dụ Java 17 chạy độc lập: tên logger, parent và mức hiệu lực

Chương trình dưới đây sử dụng **chỉ `java.util.logging` của JDK** để tạo một logger cha cho nhóm `demo.billing` và logger con có tên `demo.billing.InvoiceService`. Ta đặt level ở cha và để con kế thừa; handler in ra `System.out` qua một formatter cố định để stdout có thể kiểm chứng.

Lưu nguyên đoạn thành **`LoggerNameDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggerNameDemo {
    public static void main(String[] args) {
        // Tạo logger cha trước để quan hệ được xác định rõ.
        Logger billing = Logger.getLogger("demo.billing");
        Logger invoice = Logger.getLogger("demo.billing.InvoiceService");

        billing.setLevel(Level.INFO);
        billing.setUseParentHandlers(false);
        invoice.setLevel(null);           // Kế thừa mức từ logger cha.
        invoice.setUseParentHandlers(true);

        Handler output = new StreamHandler(
                System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName() + " "
                                + record.getLoggerName() + " "
                                + formatMessage(record)
                                + System.lineSeparator();
                    }
                }
        );
        output.setLevel(Level.ALL);
        billing.addHandler(output);

        System.out.println("childName=" + invoice.getName());
        System.out.println("parentName=" + invoice.getParent().getName());

        invoice.fine("event=invoice.validating"); // Bị loại ở ngưỡng INFO.
        invoice.log(Level.INFO, "event=invoice.created id={0}", "inv-42");
        billing.warning("event=invoice.queue_near_limit");

        output.flush();
        billing.removeHandler(output);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LoggerNameDemo.java
java LoggerNameDemo
```

**Standard output đúng theo mã trên:**

```text
childName=demo.billing.InvoiceService
parentName=demo.billing
INFO demo.billing.InvoiceService event=invoice.created id=inv-42
WARNING demo.billing event=invoice.queue_near_limit
```

Phân tích:

1. `invoice.getName()` trả đúng chuỗi được truyền vào `Logger.getLogger`. Nó không phụ thuộc tên class chứa lệnh gọi vì tên logger đã được chỉ định bằng chuỗi.
2. `invoice.getParent().getName()` là `demo.billing`, vì logger cha đã được tạo và còn được giữ tham chiếu. Kết quả cho thấy quan hệ tên logger, không phải quan hệ kế thừa `InvoiceService extends ...`.
3. `invoice.setLevel(null)` cho phép dùng level `INFO` từ cha. Sự kiện `FINE` không xuất hiện.
4. `invoice` không có handler trực tiếp; event `INFO` được chuyển đến handler gắn ở `billing` nhờ `setUseParentHandlers(true)`.
5. `billing.setUseParentHandlers(false)` ngăn việc tiếp tục đưa record đến handler của logger cấp cao hơn, giúp chương trình không in trùng do handler mặc định của hệ thống.
6. Formatter dùng `record.getLoggerName()` nên log cho biết **logger gốc phát ra sự kiện**, kể cả khi handler thực tế được gắn ở logger cha.
7. `formatMessage(record)` xử lý placeholder JUL `{0}` thành `inv-42`; `flush()` chuyển nội dung còn trong bộ đệm của `StreamHandler` ra stdout.

Trong dự án thực tế, formatter/handler và chính sách level thường được cấu hình ở lúc khởi động. Không nên tạo handler mới cho mỗi request như một thao tác logging thường ngày.

## 5. Đặt tên quyết định phạm vi cấu hình

Giả sử dự án có ba logger:

- `com.example.orders.OrderService`
- `com.example.orders.OrderRepository`
- `com.example.payments.PaymentService`

Một thiết lập tại prefix `com.example.orders` có thể dùng để mở chi tiết nhóm đơn hàng mà không làm đầy log của nhóm thanh toán. Nếu mỗi class được đặt tên tùy hứng, việc cấu hình theo package khó dự đoán và tìm kiếm log mất công hơn.

Ví dụ tệp **`logging.properties`** cho JUL:

```properties
# Mức mặc định của logger gốc.
.level=INFO

# Chỉ logger thuộc nhóm orders cho phép thông tin chi tiết.
com.example.orders.level=FINE

# Một class cụ thể ghi từ INFO trở lên.
com.example.orders.OrderService.level=INFO

# Handler console phải cho phép mức FINE nếu muốn thấy FINE.
handlers=java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Có thể trỏ JUL đến tệp cấu hình khi khởi động một chương trình phù hợp bằng JVM option:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Lệnh trên **chỉ minh họa cách nạp cấu hình**, giả định đã biên dịch chương trình có class `com.example.Main`. Nó không phải lệnh để chạy `LoggerNameDemo` ở trên, bởi demo chủ động cấu hình level và handler của mình trong mã.

Một số điểm cần hiểu:

- `.level=INFO` là ngưỡng của root logger, không phải giá trị mặc định ép buộc mọi logger con.
- Logger `com.example.orders.OrderRepository` có thể dùng mức `FINE` nếu không tự đặt ngưỡng khác và thừa hưởng cấu hình prefix.
- Logger `com.example.orders.OrderService` được đặt `INFO` riêng, nên không in sự kiện `FINE` chỉ vì prefix orders cho phép FINE.
- Logger ở nhánh `com.example.payments` có thể giữ ngưỡng kế thừa `INFO`.
- Handler `ConsoleHandler` cũng có level và bộ lọc riêng. Nếu handler chỉ nhận `INFO` thì đặt logger thành `FINE` chưa đủ để thấy dòng FINE.
- Chính xác logger nào tồn tại, level nào được gán khi khởi tạo và output nào xuất hiện còn phụ thuộc thời điểm nạp cấu hình, handler và việc chương trình có thay đổi cấu hình lúc chạy hay không.

Với Logback/Log4j 2, cấu hình sử dụng định dạng và semantics của backend đó; không sao chép trực tiếp cú pháp `logging.properties` của JUL.

## 6. Những lỗi đặt tên logger thường gặp

### 6.1. Dùng tên ngắn làm mất namespace

```java
// Mẫu minh họa, giả sử lớp OrderService và Logger đã tồn tại.
Logger.getLogger(OrderService.class.getSimpleName());
```

`getSimpleName()` chỉ tạo `OrderService`. Nếu hai package đều có `OrderService`, các logger sẽ trùng tên và khó cấu hình độc lập. Dùng `OrderService.class.getName()` để lấy đầy đủ package; với nested class, Java binary name có thể chứa dấu `$` thay vì dấu chấm thông thường.

### 6.2. Sao chép tên logger từ lớp khác

```java
// Sai về nguồn gốc nếu đặt đoạn mã trong PaymentService:
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("com.example.orders.OrderService");
```

Log có thể xuất hiện dưới category sai, khiến việc tìm và bật level chẩn đoán không hiệu quả. Ưu tiên `PaymentService.class.getName()` trong chính class `PaymentService` hoặc giữ một tên category rõ ràng nếu thật sự chủ ý dùng chung.

### 6.3. Đưa dữ liệu thay đổi theo request vào tên

```java
// Không nên: sinh category theo từng đơn hàng.
Logger.getLogger("orders." + orderId);
```

Ví dụ trên chỉ là **đoạn minh họa**, giả sử `orderId` có sẵn. Tạo tên theo ID có thể làm số lượng logger/category tăng mạnh, gây khó cấu hình và quản lý, đồng thời có nguy cơ lộ định danh nhạy cảm.

Thay bằng tên logger ổn định, đưa ID vào record:

```java
// Minh họa JUL; logger cố định, dữ liệu động nằm trong thông điệp.
Logger orderLogger = Logger.getLogger("com.example.orders.OrderService");
orderLogger.log(java.util.logging.Level.INFO,
        "event=order.accepted orderId={0}", orderId);
```

Ở các hệ thống hỗ trợ structured logging, nên dùng field `orderId` thực sự; correlation ID, trace ID hoặc dữ liệu theo request cần nằm trong context/attributes, **không nằm trong tên logger**. Dữ liệu người dùng phải được đánh giá mức nhạy cảm và xử lý an toàn trước khi log.

### 6.4. Dùng `getClass()` ở ngữ cảnh dễ thay đổi

Khi viết một base class, dùng `getClass().getName()` có thể lấy tên của subclass thực tế, proxy hoặc lớp runtime được sinh tự động, khiến category thay đổi ngoài ý định. Nếu muốn gắn logger với một class cố định, dùng `SomeService.class.getName()` trong chính class đó; nếu cần phân biệt các subclass, hãy thiết kế lựa chọn ấy một cách rõ ràng.

### 6.5. Thấy trùng log và cho rằng trùng tên

Hai logger có tên khác nhau vẫn có thể cùng chuyển record đến một handler cha. Nếu handler được gắn nhiều chỗ hoặc đồng thời xuất ra cùng sink, một sự kiện có thể bị in lặp. Kiểm tra cấu hình `useParentHandlers` trong JUL hoặc *additivity* của backend khác; **không cần đổi logger name chỉ để chữa lỗi handler**.

### 6.6. Bật DEBUG/FINE mà log vẫn không hiện

Việc lọc có thể xảy ra ở logger (bao gồm inherited level), handler/appender, filter, hoặc cấu hình đang nạp không phải file dự kiến. Kiểm tra đúng tên thực tế bằng `getName()`, level hiệu lực và nơi log được ghi. Đừng giả định vì tên có prefix `com.example.orders` thì mọi framework đều lập tức áp dụng cùng một kiểu cấu hình.

### 6.7. Đổi package/class nhưng quên cấu hình và truy vấn

Khi dùng tên class làm logger name, việc refactor `com.example.orders.OrderService` thành `com.example.checkout.OrderService` làm tên logger đổi theo. Điều này thường đúng mong muốn về tổ chức mã, nhưng bộ lọc trong cấu hình, dashboard, alert và saved search có thể cần được cập nhật. Trong các hệ thống cần phân nhóm lâu dài, lưu thêm một trường `component` hoặc `event` ổn định thay vì coi class name là khóa nghiệp vụ bất biến.

## 7. Cách lựa chọn và kiểm tra tên logger trong dự án

Khi bổ sung logger mới vào Java codebase, nên theo trình tự sau:

1. **Chọn nguồn định danh:** ưu tiên logger theo class qua `SomeClass.class.getName()` (JUL) hoặc `LoggerFactory.getLogger(SomeClass.class)` (SLF4J), trừ khi hệ thống chủ đích dùng category theo phân hệ.
2. **Giữ namespace có cấu trúc:** dùng package/class nhất quán, dễ lọc bằng prefix; tránh chuỗi ngẫu nhiên hoặc chỉ dùng simple class name.
3. **Tách danh tính logger khỏi dữ liệu sự kiện:** logger name mô tả *ai phát log*; `requestId`, `orderId` và `event` mô tả *sự kiện cụ thể*.
4. **Cấu hình có trọng tâm:** dùng level theo package để kiểm tra một thành phần; nếu cần thì ghi đè cho một class cụ thể.
5. **Kiểm chứng cả đầu ra:** đảm bảo formatter/encoder hiển thị logger name, level, timestamp và context hữu ích; xem xét handler/appender và khả năng nhân bản log.
6. **Kiểm tra sau refactor:** cập nhật tên trong cấu hình, dashboard, cảnh báo hoặc truy vấn nếu đường dẫn package/class thay đổi.
7. **Không dùng logger name cho dữ liệu nhạy cảm:** tránh ID cá nhân, token, query string hoặc các giá trị do request cung cấp.

### Tình huống tự kiểm tra

**Tình huống A.** `com.example.orders.OrderService` không in `FINE` dù đã cấu hình `com.example.orders.level=FINE`. Hãy kiểm tra logger con có đặt level riêng hay không, effective level là gì, handler có cho phép `FINE` hay không, và file cấu hình có đang được nạp không.

**Tình huống B.** Hai lớp `com.example.orders.OrderService` và `com.example.payments.OrderService` đều khai báo logger bằng `getSimpleName()`. Cả hai có thể mang tên `OrderService`; giải pháp là dùng `Class.getName()` để giữ đủ namespace.

**Tình huống C.** Một ứng dụng tạo `Logger.getLogger("orders." + requestId)` cho mỗi request. Nên giữ tên logger ổn định theo class/nhóm, chuyển request ID vào context hoặc trường của event, và kiểm soát dữ liệu nhạy cảm.

Tên logger được thiết kế tốt sẽ giúp log trả lời được câu hỏi **“thành phần nào phát sự kiện?”** một cách nhất quán, đồng thời tạo cấu trúc ổn định để lọc, định tuyến và cấu hình logging trong Java.