# Logger theo class trong Java

## 1. Logger theo class là gì?

**Logger theo class (class-specific logger)** là cách mỗi lớp Java sử dụng một đối tượng logger được đặt tên theo **tên đầy đủ của chính lớp đó**. Đây là một quy ước phổ biến để biết sự kiện log xuất phát từ thành phần nào, đồng thời cho phép cấu hình mức log theo lớp hoặc theo package.

Với Java Util Logging (**JUL**, thuộc JDK), cách khai báo quen thuộc là:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());
}
~~~

Nếu lớp nằm trong package **com.example.orders**, tên logger là **com.example.orders.OrderService**. Khi kiểm tra bản ghi, tên này giúp xác định nhanh lớp liên quan. Công cụ thu thập log có thể sử dụng nó để lọc, nhóm hoặc tìm kiếm.

Cần phân biệt: **“logger theo class” là quy ước đặt tên và sử dụng logger, không phải cơ chế tạo một file log riêng cho mỗi class**. Logger có thể cùng gửi bản ghi đến console, file, bộ thu thập tập trung hoặc Handler chung. Nơi ghi, định dạng và điều kiện lọc do cấu hình logging quyết định.

Ví dụ trong hệ thống đặt hàng:

| Class | Tên logger JUL thông thường | Các sự kiện có thể ghi |
| --- | --- | --- |
| **OrderService** | com.example.orders.OrderService | Tạo đơn, cập nhật trạng thái, xử lý thất bại |
| **PaymentClient** | com.example.payment.PaymentClient | Gọi cổng thanh toán, timeout, retry |
| **InventoryService** | com.example.inventory.InventoryService | Kiểm tra tồn kho, giữ hàng |
| **CheckoutController** | com.example.web.CheckoutController | Bắt đầu/kết thúc yêu cầu HTTP tại ranh giới xử lý |

Một hệ thống production thường có nhiều class và nhiều package, nên tên logger rõ ràng giúp điều tra mà không cần đọc lại mã nguồn để đoán nguồn phát sự kiện.

## 2. Tại sao nên dùng một logger đặt tên theo từng class?

### Xác định đúng nguồn phát sự kiện

So sánh hai bản ghi:

~~~text
INFO | Đã cập nhật trạng thái đơn hàng
INFO | com.example.orders.OrderService | Đã cập nhật trạng thái đơn hàng
~~~

Bản ghi thứ hai cung cấp **tên logger**; nhờ đó người đọc biết ngay thành phần liên quan. Tên logger do **Formatter/layout** quyết định có xuất ra hay không: việc khai báo logger theo class không tự động đảm bảo tên sẽ xuất hiện trong log.

### Điều chỉnh mức log chính xác

Có thể chỉ bật mức chi tiết cho **com.example.payment.PaymentClient** khi điều tra lỗi thanh toán, trong khi các logger còn lại vẫn ở INFO. Điều này giảm nhiễu và chi phí ghi log so với việc bật debug trên toàn ứng dụng.

### Quản lý cùng quy ước khi mở rộng dự án

Khi mọi class dùng tên từ **Class.getName()**, việc đổi package hoặc tên class thường cập nhật luôn tên logger sau khi biên dịch. Nhóm vận hành có thể tìm bản ghi theo tiền tố package hoặc logger cụ thể mà không phải duy trì một danh sách tên tùy tiện.

Tuy nhiên, **đổi tên class cũng có thể làm thay đổi tên logger**, ảnh hưởng đến quy tắc tìm kiếm, dashboard hoặc cấu hình mức log đang phụ thuộc vào tên cũ. Với những định danh log bắt buộc phải giữ ổn định lâu dài, nên bổ sung **mã sự kiện có cấu trúc** thay vì phụ thuộc duy nhất vào tên class.

### Không cần cấp phát logger cho từng object

Các instance của cùng một class thường có chung một **static final Logger**. Ví dụ tạo 1.000 đối tượng OrderService không cần khai báo 1.000 trường logger khác nhau. Logger đại diện cho **nhóm sự kiện của class**, còn dữ liệu gắn với từng request hoặc đối tượng được truyền vào nội dung/bối cảnh bản ghi khi cần.

## 3. Phân tích chính xác cú pháp JUL

~~~java
private static final Logger LOGGER =
        Logger.getLogger(OrderService.class.getName());
~~~

Ý nghĩa của từng phần:

- **private:** Các lớp khác không truy cập trực tiếp trường logger; mỗi lớp quản lý cách phát sự kiện của nó. Có thể dùng phạm vi khác nếu kiến trúc thực sự cần, nhưng **private** là lựa chọn thông thường.
- **static:** Trường gắn với lớp, không tạo riêng cho mỗi instance. Các phương thức static cũng dùng được logger.
- **final:** Không gán lại biến tham chiếu sau khi khởi tạo. **final không có nghĩa logger bất biến**: cấp độ, Handler hoặc Filter vẫn có thể được cấu hình theo API.
- **Logger:** Kiểu **java.util.logging.Logger**, không phải **org.slf4j.Logger**.
- **Logger.getLogger(String name):** Lấy logger theo tên trong hệ thống quản lý JUL.
- **OrderService.class.getName():** Trả về tên đầy đủ của class, bao gồm package khi có. Với class lồng nhau, cách biểu diễn tên JVM có thể chứa ký tự **$**.

Trong JUL, phương thức **getLogger** nhận **String** cho cách gọi này. Cú pháp **Logger.getLogger(OrderService.class)** không phải overload tương ứng của JUL; cú pháp nhận trực tiếp **Class** là mẫu phổ biến của **SLF4J LoggerFactory**, được nói đến ở phần sau.

### getName() và getSimpleName() khác gì?

~~~java
String fullName = OrderService.class.getName();
String shortName = OrderService.class.getSimpleName();
~~~

Nếu OrderService ở package **com.example.orders**:

~~~text
fullName  = com.example.orders.OrderService
shortName = OrderService
~~~

**Nên dùng getName()** vì hai package hoàn toàn có thể cùng có một class tên OrderService. Nếu dùng getSimpleName(), chúng có thể vô tình dùng cùng một tên logger, mất ngữ cảnh package và khó cấu hình riêng.

### Logger gắn với class hay instance?

Trong phần lớn service/controller/repository, nên dùng **một logger static final cho mỗi class**:

~~~java
private static final Logger LOGGER =
        Logger.getLogger(MyService.class.getName());
~~~

Nếu một phương thức chỉ cần ghi sự kiện của MyService, không cần tạo logger mới mỗi lần gọi:

~~~java
public void process() {
    Logger logger = Logger.getLogger(MyService.class.getName());
    logger.info("Processing");
}
~~~

Đoạn thứ hai vẫn dùng API hợp lệ, nhưng gọi tra cứu logger lặp lại và không thể hiện rõ quy ước logger cố định của lớp. Nó thường không mang lại lợi ích. Tương tự, việc dùng **getClass().getName()** từ đối tượng có thể cho tên lớp con ở thời điểm chạy; đó là một lựa chọn kiến trúc riêng, không tự động tương đương với logger cố định của lớp khai báo.

## 4. Ví dụ Java 17 độc lập: hai class, hai mức log

Ví dụ sau dùng **java.util.logging** có sẵn trong JDK. Hai class có logger riêng theo tên class. Chương trình cố ý:

1. Đặt logger của **OrderService** ở mức **FINE** để hiện INFO và FINE.
2. Đặt logger của **PaymentClient** ở mức **WARNING** để chặn INFO nhưng cho WARNING đi qua.
3. Dùng **một ConsoleHandler chung**, định dạng tên logger, mức và thông điệp.
4. Tắt truyền log tới Handler cha **chỉ trong ví dụ** để tránh các dòng log mặc định làm thay đổi kết quả.

Tạo tệp **LoggerPerClassDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerPerClassDemo {
    public static void main(String[] args) {
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLoggerName()
                        + " | " + record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        configure(OrderService.LOGGER, Level.FINE, console);
        configure(PaymentClient.LOGGER, Level.WARNING, console);

        new OrderService().submit("ORD-42");
        new PaymentClient().charge("ORD-42");

        OrderService.LOGGER.removeHandler(console);
        PaymentClient.LOGGER.removeHandler(console);
        console.close();
    }

    private static void configure(Logger logger, Level level, Handler handler) {
        logger.setLevel(level);
        logger.setUseParentHandlers(false);
        logger.addHandler(handler);
    }
}

final class OrderService {
    static final Logger LOGGER = Logger.getLogger(OrderService.class.getName());

    void submit(String orderId) {
        LOGGER.info("Created order " + orderId);
        LOGGER.fine("Validation passed for " + orderId);
    }
}

final class PaymentClient {
    static final Logger LOGGER = Logger.getLogger(PaymentClient.class.getName());

    void charge(String orderId) {
        LOGGER.info("Starting payment for " + orderId);
        LOGGER.warning("Gateway responded slowly for " + orderId);
    }
}
~~~

Chạy với **JDK 17 trở lên**, ngay tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 LoggerPerClassDemo.java
java LoggerPerClassDemo
~~~

**Nội dung xuất ra stderr** (ConsoleHandler mặc định ghi vào stderr, không phải stdout):

~~~text
OrderService | INFO | Created order ORD-42
OrderService | FINE | Validation passed for ORD-42
PaymentClient | WARNING | Gateway responded slowly for ORD-42
~~~

Dòng **PaymentClient | INFO | Starting payment...** không xuất hiện vì mức **INFO** thấp hơn ngưỡng **WARNING** của logger PaymentClient.

Lưu ý về file Java: ví dụ có **một class public** là LoggerPerClassDemo; OrderService và PaymentClient là hai class không public cùng tệp nên có thể biên dịch trực tiếp bằng lệnh trên. Chúng nằm trong **default package** để demo chạy ngắn gọn; vì thế Formatter in tên logger là **OrderService** và **PaymentClient**. Trong dự án thực tế có khai báo package, **getName()** sẽ cho tên đầy đủ như **com.example.orders.OrderService**.

Mẫu code này cấu hình mức và Handler trực tiếp trong **main** để bảo đảm kết quả rõ ràng. Khi xây dựng ứng dụng thật, nên cấu hình logging tập trung và để từng class chỉ khai báo logger cùng các lời gọi log.

## 5. Logger theo class liên hệ với package và cấu hình cha như thế nào?

Trong JUL, tên logger tạo ra một **không gian tên phân cấp**. Ví dụ:

~~~text
com
  └── example
      ├── orders
      │   ├── OrderService
      │   └── OrderRepository
      └── payment
          └── PaymentClient
~~~

Các đường dẫn trên minh họa **tên logger phân tách bằng dấu chấm**, không phải cấu trúc cây class trong bộ nhớ. Logger cha của một logger có tên đầy đủ được xác định theo hệ thống logger hiện có; parent gần nhất có thể là một tên tiền tố hoặc logger gốc. Không phải mọi đoạn tiền tố đều bắt buộc tồn tại như một Logger riêng.

Khi một logger **không đặt mức riêng** (**setLevel(null)**), nó kế thừa mức hiệu lực từ Logger cha. Do đó có thể cấu hình chung theo package và chỉ ghi đè ở class đang cần điều tra.

Ví dụ ý tưởng (mã minh họa khi các class thuộc package tương ứng):

~~~java
Logger orders = Logger.getLogger("com.example.orders");
orders.setLevel(Level.INFO);

Logger orderService =
        Logger.getLogger("com.example.orders.OrderService");
orderService.setLevel(null); // Ke thua tu logger cha.

Logger orderRepository =
        Logger.getLogger("com.example.orders.OrderRepository");
orderRepository.setLevel(Level.FINE); // Ghi de cho class nay.
~~~

**Mức logger** và **mức Handler** là hai bộ lọc khác nhau. Để nhận được FINE, cả Logger và Handler đích đều phải cho phép FINE. Ví dụ đặt Logger ở FINE nhưng ConsoleHandler vẫn ở INFO thì bản ghi FINE vẫn có thể bị loại trước khi hiển thị.

### Vai trò của Handler cha

Theo cấu hình thường gặp, một logger có thể chuyển bản ghi tới Handler gắn với cha. Điều này cho phép dùng Handler cấu hình ở cấp toàn ứng dụng. Nếu gắn Handler vào logger con mà vẫn cho phép chuyển lên Handler cha, có thể có **hai bản ghi hiển thị** cho cùng một lần gọi.

Phương thức **logger.setUseParentHandlers(false)** ngăn việc chuyển bản ghi đến Handler của cha. Tuy nhiên:

- Nó **không tự thêm** một Handler mới.
- Nếu logger không có Handler phù hợp, bản ghi có thể không xuất hiện.
- Nó **không tắt việc kế thừa mức log** từ cha nếu mức của logger vẫn là **null**.
- Không nên tắt hàng loạt trong mã nghiệp vụ khi hệ thống đã có cơ chế cấu hình Handler tập trung.

Trong ví dụ độc lập ở trên, hai class cùng tham chiếu đến một Handler nhưng mỗi bản ghi chỉ được công bố từ logger của class tương ứng; chúng không chuyển log sang Handler cha nên không bị lặp.

## 6. Cấu hình mức log theo từng class trong thực tế

Với JUL, có thể đặt ngưỡng trong tệp **logging.properties**. Ví dụ dành cho một dự án có các class ở package **com.example.orders** và **com.example.payment**:

~~~properties
handlers = java.util.logging.ConsoleHandler

.level = INFO
java.util.logging.ConsoleHandler.level = FINE

com.example.orders.OrderService.level = FINE
com.example.payment.PaymentClient.level = WARNING
~~~

Ý nghĩa:

- **.level = INFO:** Mức mặc định của logger gốc.
- **ConsoleHandler.level = FINE:** Handler cho phép cả thông điệp FINE.
- **OrderService.level = FINE:** Có thể nhận thêm log FINE cho class này.
- **PaymentClient.level = WARNING:** Tập trung vào sự kiện WARNING và SEVERE của class đó.

JVM có thể tải cấu hình JUL từ tệp khi khởi động, chẳng hạn với ứng dụng có main class **com.example.Main** và output đã biên dịch ở thư mục **out**:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Lệnh này **minh họa cách nạp cấu hình cho một ứng dụng thực tế**, không phải lệnh chạy cho LoggerPerClassDemo, vì demo ở phần 4 chủ động đặt mức và Handler bằng mã. Trong ứng dụng dùng framework logging khác, cú pháp và cách nạp cấu hình có thể không giống JUL.

Ngoài cấu hình theo class, có thể cấu hình theo **package**, ví dụ mức log toàn bộ phần repository rồi ghi đè một class cụ thể. Với log cấu trúc hoặc log tập trung, có thể lọc bằng **loggerName** hoặc **class/package** nếu các trường đó được cấu hình xuất ra.

## 7. Dùng logger theo class để ghi lỗi đúng cách

Một logger theo class nên ghi **sự kiện mà class chịu trách nhiệm**, với ngữ cảnh đủ dùng để điều tra.

Ví dụ trong một phương thức của OrderService (đoạn này **không độc lập**, giả sử các biến và hàm đã được khai báo):

~~~java
LOGGER.log(Level.INFO, "Order accepted: id={0}", orderId);

try {
    persistOrder(orderId);
} catch (java.io.IOException e) {
    LOGGER.log(Level.SEVERE, "Could not persist order", e);
    throw e;
}
~~~

**Logger.log(Level, String, Object)** sử dụng tham số trong thông điệp, chẳng hạn placeholder **{0}** khi được Formatter hỗ trợ; **Logger.log(Level, String, Throwable)** gắn ngoại lệ vào LogRecord để Formatter có thể xuất stack trace. Chỉ ghi **e.getMessage()** thường không đủ dữ liệu chẩn đoán lỗi.

Cần chủ động quyết định **tầng nào ghi lỗi**: nếu cùng exception bị log ở DAO, Service và Controller rồi tiếp tục được ném lên, hệ thống có thể tạo ba bản ghi SEVERE cho một lỗi. Hãy ghi ở nơi có trách nhiệm xử lý hoặc ở ranh giới phù hợp, và tránh log lặp thiếu giá trị.

Với dữ liệu debug tốn chi phí tạo chuỗi, JUL hỗ trợ dạng **Supplier**:

~~~java
LOGGER.log(Level.FINE, () -> "Current cache size: " + expensiveCount());
~~~

Biểu thức tạo thông điệp chỉ được đánh giá khi Logger quyết định chấp nhận mức FINE; việc Handler có tiếp tục lọc bản ghi hay không là bước sau đó. Nếu muốn tính toán đắt tiền chỉ khi mức log được bật, cũng có thể dùng **LOGGER.isLoggable(Level.FINE)** để bao quanh công việc cần thiết.

Không đưa **mật khẩu, token, khóa bí mật, toàn bộ request nhạy cảm hoặc thông tin cá nhân không cần thiết** vào log. Với hệ thống phân tán, nên có mã request/trace và mã sự kiện ổn định để điều tra, đồng thời tránh tạo logger với tên chứa ID riêng của từng request vì có thể tạo quá nhiều category và phá vỡ cách nhóm theo class.

## 8. So sánh với logger theo class bằng SLF4J

Nhiều ứng dụng Java hiện đại dùng **SLF4J** làm API logging, còn backend như **Logback** hoặc **Log4j 2** chịu trách nhiệm ghi log. Nguyên tắc logger theo class vẫn giữ nguyên, nhưng cú pháp khác JUL.

Ví dụ dùng SLF4J (đoạn minh họa yêu cầu **dependency SLF4J và backend logging**, không chạy độc lập chỉ với JDK):

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderId) {
        log.info("Created order {}", orderId);
        log.debug("Validated order {}", orderId);
    }
}
~~~

So sánh nhanh:

| Nội dung | JUL (JDK) | SLF4J |
| --- | --- | --- |
| Khai báo logger | **Logger.getLogger(OrderService.class.getName())** | **LoggerFactory.getLogger(OrderService.class)** |
| Kiểu logger | **java.util.logging.Logger** | **org.slf4j.Logger** |
| Mức chi tiết phổ biến | **FINE, FINER, FINEST** | **DEBUG, TRACE** |
| Mức lỗi | **SEVERE, WARNING** | **ERROR, WARN** |
| Tham số thông điệp | **{0}**, **{1}** khi định dạng theo JUL | Placeholder **{}** |
| Cấu hình đích ghi | Handler và Formatter của JUL | Backend và appender/layout tương ứng |

Không trộn **import java.util.logging.Logger** với **LoggerFactory.getLogger(Class)**, hoặc dùng placeholder **{}** của SLF4J trong JUL rồi kỳ vọng Formatter của JUL tự xử lý. Trong ứng dụng Spring Boot, hãy dùng API và backend đã được dự án chuẩn hóa; không thêm Handler JUL trong từng class nếu hệ thống đã thu thập log qua cấu hình chung.

## 9. Những lỗi thường gặp khi tạo logger theo class

### Sai 1: Dùng tên logger thủ công không đúng class

~~~java
// Hai class khac nhau lai cung dung chung mot ten category.
Logger logger = Logger.getLogger("CommonLogger");
~~~

Khi tất cả class cùng dùng **CommonLogger**, log mất khả năng lọc chính xác theo class. Chỉ dùng category chung khi đó là quyết định có chủ đích, chẳng hạn một luồng audit độc lập với class.

### Sai 2: Sử dụng getSimpleName() thay vì getName()

~~~java
Logger logger = Logger.getLogger(OrderService.class.getSimpleName());
~~~

Tên lớp ngắn có thể trùng giữa package khác nhau. Với logger đặt tên theo class, **class.getName()** thường an toàn và dễ định cấu hình hơn.

### Sai 3: Mỗi lần ghi log lại tạo một logger mới

~~~java
void process() {
    Logger logger = Logger.getLogger(OrderService.class.getName());
    logger.info("Processing");
}
~~~

Việc tra cứu theo tên không nhất thiết tạo một đối tượng mới mỗi lần, nhưng lặp lại thao tác không cần thiết. Một trường **private static final Logger** thể hiện rõ mục tiêu và giữ cách dùng ổn định.

### Sai 4: Tự thêm Handler ở mỗi constructor hoặc mỗi lần gọi

~~~java
OrderService() {
    LOGGER.addHandler(new ConsoleHandler());
}
~~~

Khi nhiều object được tạo, cùng một logger có thể bị gắn thêm nhiều Handler, khiến cùng thông điệp được ghi nhiều lần và tốn tài nguyên. Hãy quản lý Handler tập trung hoặc khởi tạo một lần tại điểm cấu hình có vòng đời rõ ràng.

### Sai 5: Chỉ đặt mức Logger rồi kỳ vọng thấy mọi log

**LOGGER.setLevel(Level.FINE)** chưa đủ nếu ConsoleHandler vẫn ở INFO. Hãy kiểm tra cả ngưỡng Logger, Handler, Filter và cấu hình truyền lên cha.

### Sai 6: Tắt Handler cha nhưng không thêm Handler riêng

Sau **setUseParentHandlers(false)**, bản ghi không được truyền tới Handler của cha. Nếu không có Handler của logger con, log có thể không hiển thị. Thay đổi tuyến xử lý chỉ khi thực sự hiểu cấu hình logging đang hoạt động.

### Sai 7: Ghi mọi thông tin ở SEVERE/ERROR

Không phải mọi ngoại lệ hay nhánh code đều là sự cố vận hành. Dùng INFO cho sự kiện quan trọng thông thường, WARNING cho bất thường có thể phục hồi, SEVERE cho thất bại nghiêm trọng; FINE cho chẩn đoán. Chọn mức theo tác động và chính sách dự án.

### Sai 8: Cho rằng logger theo class bảo đảm nhìn thấy tên class trong output

Logger có tên đúng nhưng Formatter/layout có thể chỉ hiển thị message. Muốn thấy tên category, cần cấu hình trường **loggerName** hoặc pattern tương ứng ở nơi xuất log.

## 10. Lựa chọn thiết kế cho dự án nhiều lớp

Một hướng tổ chức dễ duy trì:

1. **Mỗi class dùng logger riêng theo Class.getName() hoặc LoggerFactory.getLogger(Class).** Duy trì cùng API logging trong toàn dự án.
2. **Cấu hình các Handler/appender tập trung.** Các class nghiệp vụ chỉ phát sự kiện; cấu hình mức, nơi xuất và định dạng do phần khởi động hoặc hệ thống logging đảm trách.
3. **Bật chi tiết có chọn lọc.** Khi xảy ra lỗi, tăng mức cho một package hoặc class cần điều tra thay vì bật debug toàn hệ thống.
4. **Dùng thông điệp có cấu trúc và ngữ cảnh.** Tên logger giúp xác định class, nhưng không thay thế ID request, mã sự kiện hoặc stack trace khi cần.
5. **Kiểm soát mức độ chi tiết và dữ liệu nhạy cảm.** Tính đến hiệu năng, dung lượng lưu, môi trường production và quyền truy cập.

Ví dụ: khi **PaymentClient** bị timeout, không nhất thiết phải bật FINE cho toàn bộ ứng dụng. Có thể chỉ cho phép log chi tiết của **com.example.payment.PaymentClient**, quan sát các lỗi trong thời gian ngắn, tìm nguyên nhân rồi trả lại ngưỡng bình thường khi đã xử lý xong.

## 11. Câu hỏi tự kiểm tra

1. **Vì sao nên dùng Class.getName() khi đặt tên logger?** Để lấy tên class có package, hạn chế trùng tên và hỗ trợ cấu hình theo class/package.
2. **static final Logger có nghĩa mỗi instance sở hữu logger riêng không?** Không. Trường static gắn với class và được dùng chung; final ngăn gán lại tham chiếu.
3. **Có phải một logger theo class sẽ ghi vào một file theo class không?** Không. Đích ghi do Handler/appender và cấu hình quyết định.
4. **Vì sao Logger ở FINE vẫn có thể không hiện bản ghi FINE?** Vì Handler hoặc Filter có thể chặn, hoặc tuyến truyền bản ghi không tới đích dự kiến.
5. **Tại sao không nên addHandler trong constructor?** Vì nhiều lần tạo object có thể gắn nhiều Handler lên cùng logger và làm ghi trùng.
6. **Cú pháp JUL và SLF4J lấy logger theo class có giống nhau không?** Không. JUL thường dùng **Logger.getLogger(MyClass.class.getName())**; SLF4J thường dùng **LoggerFactory.getLogger(MyClass.class)**.

**Ghi nhớ:** Logger theo class giúp bản ghi có nguồn phát rõ ràng, dễ lọc theo tên lớp hoặc package và thống nhất cách ghi log trong dự án Java. Sử dụng logger **static final** theo tên đầy đủ của class, quản lý Handler ở nơi cấu hình chung và chọn mức log phù hợp sẽ tạo nền tảng logging dễ mở rộng và dễ chẩn đoán.
