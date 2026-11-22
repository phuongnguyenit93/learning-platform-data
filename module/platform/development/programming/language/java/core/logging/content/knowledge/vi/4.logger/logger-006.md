# Logger con trong Java Logging

Khi một ứng dụng có hàng chục package và hàng trăm lớp, cấu hình mức log cho từng lớp sẽ khó quản lý. **Logger con** (child logger) giải quyết việc này bằng cách đặt các logger vào **hệ phân cấp theo tên**, cho phép chúng kế thừa một số thiết lập từ logger cha và, tùy hệ thống logging, chuyển các sự kiện đã tạo đến nơi xuất log của cha.

Điểm quan trọng nhất: **kế thừa mức log** và **chuyển tiếp bản ghi tới handler/appender của cha** là hai cơ chế riêng. Hiểu rõ hai cơ chế này giúp bật DEBUG cho một nhóm lớp, giữ INFO cho phần còn lại và tránh log bị mất hoặc in nhiều lần.

## 1. Logger con là gì?

Một hệ phân cấp logger có thể có các tên:

~~~text
(root)
  |
  +-- com.example
        |
        +-- com.example.orders
              |
              +-- com.example.orders.payment
              |
              +-- com.example.orders.shipping
~~~

Trong ví dụ này, **com.example.orders.payment** là logger con của **com.example.orders** nếu backend hoặc JUL thiết lập đúng quan hệ cha–con; **com.example** là tổ tiên ở cấp cao hơn.

Tên có dấu chấm giúp biểu diễn ranh giới package hoặc component. Tuy nhiên:

- Quan hệ logger cha–con **không phải kế thừa lớp Java** bằng extends. Lớp PaymentService không cần extends OrderService để logger của nó nằm dưới namespace com.example.orders.
- Logger con cũng **không phải thread con** hay process con. Hai thread có thể cùng phát sự kiện qua một logger mang tên cố định.
- **Tiền tố chuỗi bất kỳ không đủ để làm cha**: com.example.order và com.example.orders là hai nhánh khác nhau. Hệ phân cấp dựa trên các thành phần tên được phân cách bởi dấu chấm.
- Không nhất thiết phải tạo một logger ứng với mỗi nút trong hình. Tùy framework, logger được nối với tổ tiên gần nhất tồn tại hoặc cấu hình gần nhất phù hợp.

Trong **java.util.logging (JUL)** của JDK, bạn có thể xem logger cha thực tế bằng **Logger.getParent()**. Một logger thường được tạo bằng **Logger.getLogger("tên")**; tên là danh tính logger và có thể được dùng để nhóm cấu hình.

Trong **SLF4J**, mã nguồn dùng facade **org.slf4j.Logger**, còn cách quản lý cây logger, mức kế thừa và điểm xuất là hành vi của implementation/backend, ví dụ Logback. Không có phương thức getParent() chung trên giao diện SLF4J Logger.

### Tên logger thường theo package hoặc lớp

Hai mẫu dùng phổ biến:

~~~java
// JUL: tên theo lớp
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(PaymentService.class.getName());
~~~

~~~java
// SLF4J: tên theo lớp (đoạn minh họa; cần slf4j-api)
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
~~~

Nếu PaymentService nằm trong package **com.example.orders.payment**, tên logger thường tương ứng với tên lớp đầy đủ **com.example.orders.payment.PaymentService**. Vì thế có thể cấu hình theo package để tác động đến các lớp bên dưới.

Đừng tạo logger mới với tên chứa requestId, orderId, userId hoặc timestamp. Những giá trị thay đổi theo mỗi yêu cầu nên là **ngữ cảnh của bản ghi**, không phải một phần tên logger: tên động làm tăng số logger cần quản lý và khiến cấu hình khó kiểm soát.

## 2. Cơ chế thứ nhất: kế thừa mức log (level inheritance)

Level quyết định sự kiện ở một mức nhất định có được logger chấp nhận hay không. Trong JUL, mỗi logger có thể mang một level riêng hoặc **null** để kế thừa level từ logger cha gần nhất có cấu hình level cụ thể.

Ví dụ:

~~~text
Logger "com.example.orders"          -> WARNING
           |
Logger "com.example.orders.payment"  -> null (kế thừa)
~~~

Khi logger payment gọi:

~~~java
child.info("request started");
child.warning("payment retry");
~~~

Logger con có **effective level = WARNING**. Sự kiện INFO bị loại ngay tại logger phát; WARNING được phép đi tiếp.

Nếu mã chạy:

~~~java
child.setLevel(java.util.logging.Level.FINE);
~~~

Logger con có ngưỡng riêng **FINE**, cho phép FINE, INFO, WARNING và các mức nghiêm trọng hơn. Logger cha vẫn có level WARNING; các logger khác có thể tiếp tục kế thừa WARNING.

Đối với JUL:

- **child.setLevel(null)**: xóa ghi đè level riêng, quay về kế thừa từ cha.
- **child.getLevel()**: trả về level được đặt trực tiếp; kết quả **null** không có nghĩa là logging bị tắt.
- **child.isLoggable(Level.INFO)**: cho biết INFO có được logger chấp nhận theo level hiện hành hay không.
- **Level.OFF**: tắt các mức thông thường ở logger; **Level.ALL** cho phép mọi mức đi qua bước kiểm tra level của logger, nhưng handler/filter phía sau vẫn có thể chặn.

Level điển hình của JUL theo thứ tự từ chi tiết đến nghiêm trọng gồm FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE. SLF4J/Logback thường dùng TRACE, DEBUG, INFO, WARN, ERROR. **Không trộn lẫn tên level của hai API** khi viết ví dụ hoặc cấu hình.

Trong Logback, logger con cũng có thể kế thừa level từ logger cha khi chưa chỉ định level riêng; việc đặt level cho package cho phép bật DEBUG có chọn lọc. Cơ chế API và tên hàm cấu hình khác với JUL.

## 3. Cơ chế thứ hai: chuyển tiếp log tới logger cha

Sau khi sự kiện được logger con chấp nhận, hệ thống có thể chuyển sự kiện đó tới handler/appender gắn với logger cha. Trong JUL, chức năng này được điều khiển bằng:

~~~java
child.setUseParentHandlers(true);  // chuyển tới handler của cha
child.setUseParentHandlers(false); // không chuyển tới handler của cha
~~~

Mặc định một JUL logger thông thường dùng handler của cha nếu không bị tắt. Một logger không gắn handler riêng vẫn có thể hiển thị log vì sự kiện được đưa lên handler của logger cha hoặc root logger.

**Đặc biệt quan trọng:** Trong JUL, khi sự kiện đi từ logger con lên handler của cha, **mức log và filter của logger cha không được kiểm tra lại cho sự kiện đã được con chấp nhận**. Handler nhận sự kiện sẽ tự kiểm tra level/filter **của handler**.

Ví dụ:

~~~text
parent logger level = WARNING
child logger level  = FINE
parent handler      = ALL
~~~

Một sự kiện FINE do **child** phát vẫn có thể tới **parent handler**, dù level của parent logger là WARNING. Ngược lại, nếu parent handler chỉ chấp nhận WARNING trở lên thì sự kiện FINE sẽ bị handler loại.

Quy tắc này khiến câu nói “mọi bản ghi của logger con phải đi qua ngưỡng level của logger cha một lần nữa” là **sai với JUL**. Cần tách rõ **ngưỡng tạo/chấp nhận sự kiện** và **ngưỡng ở đích nhận**.

Bảng tình huống:

| Cấu hình | child.info / child.fine | Kết quả kỳ vọng |
| --- | --- | --- |
| Parent WARNING; child kế thừa | INFO | Bị loại tại logger con, handler không nhận |
| Parent WARNING; child kế thừa | WARNING | Được nhận và có thể chuyển đến parent handler |
| Parent WARNING; child FINE; parent handler ALL | FINE | Được xuất ở parent handler |
| Parent WARNING; child FINE; parent handler WARNING | FINE | Qua được logger con nhưng bị parent handler chặn |
| Child FINE; không có handler riêng; tắt parent handlers | FINE | Được logger chấp nhận nhưng không có đích xuất |
| Child có handler riêng và vẫn chuyển tiếp cha | WARNING | Có thể xuất ở cả hai handler, tùy cấu hình |

**Chuyển tiếp handler không phải kế thừa level.** Tắt parent handlers không tự thay đổi effective level của logger con; đặt level FINE riêng không tự tắt việc chuyển tới handler cha.

## 4. Ví dụ hoàn chỉnh Java 17+: quan sát cả hai cơ chế

Chương trình dưới đây chỉ dùng **java.util.logging**, không cần dependency bên ngoài. Tạo hai logger cha và con, gắn một handler cho cha rồi thêm handler riêng cho con. Handler tùy chỉnh in lên **stdout** để kết quả ngắn, dễ kiểm tra; đây là lựa chọn của ví dụ, còn JUL ConsoleHandler mặc định ghi ra **stderr**.

Tạo tệp **ChildLoggerDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ChildLoggerDemo {
    private static final class NamedHandler extends Handler {
        private final String name;

        NamedHandler(String name) {
            this.name = name;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(name + " | " + record.getLevel().getName()
                        + " | " + record.getMessage());
            }
        }

        @Override
        public void flush() {}

        @Override
        public void close() {}
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("demo.orders");
        Logger child = Logger.getLogger("demo.orders.payment");

        parent.setUseParentHandlers(false);
        parent.setLevel(Level.WARNING);
        parent.addHandler(new NamedHandler("PARENT"));

        child.setLevel(null);
        System.out.println("parent=" + child.getParent().getName());

        child.info("inherited INFO");
        child.warning("inherited WARNING");

        child.setLevel(Level.FINE);
        child.fine("child FINE");

        child.addHandler(new NamedHandler("CHILD"));
        child.warning("two destinations");

        child.setUseParentHandlers(false);
        child.warning("local only");
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac ChildLoggerDemo.java
java ChildLoggerDemo
~~~

Kết quả **stdout chính xác**:

~~~text
parent=demo.orders
PARENT | WARNING | inherited WARNING
PARENT | FINE | child FINE
CHILD | WARNING | two destinations
PARENT | WARNING | two destinations
CHILD | WARNING | local only
~~~

### Phân tích từng bước

**Bước 1 — Xác lập quan hệ cha–con.** Logger demo.orders được tạo trước demo.orders.payment. Hàm child.getParent().getName() xác nhận cha trực tiếp trong ví dụ là demo.orders. Trong JUL, cha trực tiếp thực tế có thể là logger tổ tiên gần nhất đang tồn tại.

**Bước 2 — Kế thừa level.** parent có level WARNING, còn child.setLevel(null) để kế thừa. Vì vậy child.info("inherited INFO") không sinh bản ghi xuất, nhưng child.warning("inherited WARNING") xuất qua handler của cha.

**Bước 3 — Override mức log tại con.** Sau child.setLevel(Level.FINE), child.fine("child FINE") được chấp nhận. Dù parent logger đặt WARNING, handler PARENT vẫn xuất FINE vì handler này nhận mức ALL; logger cha không lọc lại sự kiện đến từ con.

**Bước 4 — Có hai đích xuất.** child.addHandler(...) thêm handler CHILD. Theo mặc định con vẫn chuyển sự kiện lên cha, nên câu "two destinations" được xuất một lần bởi CHILD và một lần bởi PARENT. Đây là hai handler cùng thấy một log event; trong ứng dụng thực tế có thể trở thành **log trùng** nếu cả hai handler ghi đến cùng đích.

**Bước 5 — Ngắt chuyển tiếp.** child.setUseParentHandlers(false) khiến "local only" chỉ tới handler CHILD. Level FINE ở child vẫn giữ nguyên.

Ví dụ cố tình cấu hình trong main để người học nhìn thấy các bước. Trong ứng dụng lớn, nên thiết lập handler/level tập trung ở startup hoặc file cấu hình thay vì lặp cấu hình ở từng lớp; việc thêm handler nhiều lần qua các lần khởi tạo có thể gây log trùng.

## 5. Cấu hình phân cấp bằng logging.properties của JUL

Với JUL, có thể đặt mức log cho namespace mà không sửa code của từng lớp. Ví dụ tệp **logging.properties** độc lập:

~~~properties
# Handler của root logger
handlers = java.util.logging.ConsoleHandler

# Mức mặc định tại root
.level = INFO

# Cho phép ConsoleHandler hiển thị cả FINE
java.util.logging.ConsoleHandler.level = ALL

# Phần lớn ứng dụng orders chỉ cần WARNING
com.example.orders.level = WARNING

# Riêng nhóm payment cần log chi tiết hơn
com.example.orders.payment.level = FINE
~~~

Khi ứng dụng thực sự tạo logger theo những tên này, logger cấp payment nhận mức FINE riêng, còn các logger khác dưới com.example.orders có thể kế thừa WARNING nếu không đặt level khác. Root handler nhận các sự kiện được chuyển tiếp tới nó và tự lọc theo cấu hình ALL.

JUL đọc file cấu hình tại thời điểm khởi tạo LogManager khi chỉ định JVM property:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

Đây là cách chạy minh họa cho một chương trình **MyApplication** đã được biên dịch, không phải lệnh dành cho ChildLoggerDemo ở phần trên: chương trình đó chủ động đặt lại level và handler trong main nên sẽ lấn một phần thiết lập từ properties.

Cần chú ý:

- Tên package trong file cấu hình phải khớp với tên logger thực sự dùng ở mã.
- Một logger có level riêng **không tiếp tục tự động kế thừa level** của cha cho tới khi level riêng được đưa về null.
- **Handler có ngưỡng riêng**. Bật FINE ở child nhưng giữ ConsoleHandler ở INFO có thể khiến FINE không xuất hiện.
- Một logger có thể nhận log thông qua handler của root ngay cả khi nó không có handler riêng; không nhất thiết phải gắn một ConsoleHandler vào từng logger.
- Cấu hình có thể được quản lý bởi framework hoặc container đang chạy; xác định file thực sự được nạp trước khi sửa.

## 6. Logger con khi dùng SLF4J và Logback

SLF4J là **facade**: ứng dụng gọi org.slf4j.Logger; việc tổ chức hierarchy, cấu hình level và appender thuộc về backend được chọn. **Logback** là backend phổ biến cung cấp cơ chế logger theo tên phân cấp.

Ví dụ những lời gọi trong các lớp có tên:

~~~text
com.example.orders.OrderService
com.example.orders.payment.PaymentService
com.example.orders.payment.RetryPolicy
com.example.orders.shipping.ShippingService
~~~

Có thể cấu hình toàn bộ nhóm orders ở INFO nhưng riêng payment ở DEBUG. Một tệp **logback.xml** minh họa:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{60} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="INFO"/>
    <logger name="com.example.orders.payment" level="DEBUG"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ý nghĩa:

- Logger có tên dưới **com.example.orders**, nếu không có level cụ thể hơn, dùng ngưỡng INFO.
- Logger có tên dưới **com.example.orders.payment**, nếu không bị ghi đè tiếp, dùng DEBUG.
- Root có level WARN cho sự kiện **phát trực tiếp từ logger kế thừa level root**. Root appender vẫn có thể xuất một sự kiện DEBUG đã được logger payment chấp nhận và chuyển tiếp tới root, vì level ở root logger không được áp lại trong lúc chuyển sự kiện qua appender hierarchy của Logback.
- Nếu appender có ThresholdFilter hoặc filter khác, sự kiện vẫn có thể bị chặn ở đó.

Ví dụ trên chỉ cần **một appender ở root** để nhận sự kiện từ các logger con qua cơ chế mặc định **additivity = true**. Đây là đoạn cấu hình minh họa Logback; dự án phải có SLF4J API và backend/provider Logback tương thích.

### Khi nào cần additivity="false"?

Giả sử appender CONSOLE đã được gắn vào root, nhưng bạn lại gắn **cùng appender** vào logger payment:

~~~xml
<logger name="com.example.orders.payment" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>
~~~

Nếu giữ additivity mặc định, một log event do payment phát có thể đi qua appender tại payment rồi tiếp tục tới appender ở root, dẫn đến hai dòng giống nhau trên console. Khi muốn logger payment xuất tại appender riêng và **không chuyển tiếp tới ancestor appenders**, cấu hình:

~~~xml
<logger name="com.example.orders.payment"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="CONSOLE"/>
</logger>
~~~

Hai đoạn trên là **các phương án thay thế**, không đặt đồng thời trong cùng file cấu hình. Khi dùng additivity=false, phải bảo đảm logger đó có đường xuất log phù hợp; nếu không có appender trực tiếp hoặc đường xuất khác, sự kiện có thể không tới nơi nào.

Trong Logback, **additivity** kiểm soát việc chuyển sự kiện đến appender ở logger cha. Nó không đồng nghĩa với việc tắt kế thừa level. Một logger không đặt level riêng vẫn có thể kế thừa level từ cha dù additivity=false.

## 7. JUL, Logback, Log4j 2: tương đồng và khác nhau

| Khía cạnh | JUL | SLF4J + Logback | Log4j 2 |
| --- | --- | --- | --- |
| Đối tượng logger mã nguồn thường dùng | java.util.logging.Logger | org.slf4j.Logger | org.apache.logging.log4j.Logger, hoặc SLF4J qua adapter |
| Cấp tên logger | Các tên phân cấp bằng dấu chấm | Các tên logger phân cấp bằng dấu chấm trong Logback | LoggerConfig có thể phù hợp theo tên/namespace; xử lý thông qua cấu hình |
| Kế thừa level | setLevel(null) kế thừa parent | Logger không đặt level riêng kế thừa mức hiệu lực theo hierarchy | Level hiệu lực dựa trên LoggerConfig phù hợp |
| Đích xuất | Handler | Appender | Appender |
| Chuyển lên cha | setUseParentHandlers(boolean) | additivity | additivity trong LoggerConfig |
| Xem cha qua facade? | JUL có getParent() | SLF4J API không có getParent() chung | Không đồng nhất với JUL getParent() |

Đừng suy luận rằng hai API có cùng mã nguồn cấu hình. Chẳng hạn **setUseParentHandlers(false)** là phương thức JUL, còn **additivity=false** là tùy chọn trong backend như Logback/Log4j 2; chức năng cùng liên quan đến routing nhưng không hoán đổi cú pháp.

Với Log4j 2, hãy phân biệt **Logger** dùng trong mã nguồn và **LoggerConfig** được backend dùng để áp dụng level, filter và appender theo tên. Không giả định một đối tượng Logger Java bắt buộc có đối tượng Logger cha trực tiếp như JUL; một LoggerConfig có thể được nhiều logger name sử dụng. Backend vẫn cung cấp cách đặt mức và đích xuất theo namespace.

SLF4J bản thân là facade; nếu không có provider/backend hợp lệ ở runtime, các lời gọi log có thể không đến đích dự kiến. Sửa cấu hình hierarchy không khắc phục được thiếu backend hoặc xung đột provider.

## 8. Dùng logger con trong ứng dụng thật

### Giảm mức log chi tiết mà không sửa toàn bộ ứng dụng

Khi chỉ muốn điều tra một cụm mã, ví dụ payment:

1. Đặt mức mặc định ở mức phù hợp cho ứng dụng, như INFO.
2. Bật DEBUG/FINE **cho namespace payment**, không bật toàn bộ ứng dụng.
3. Giữ appender/handler có ngưỡng đủ thấp để sự kiện chi tiết tới được đích quan sát.
4. Hoàn nguyên level sau khi kết thúc điều tra để tránh log quá nhiều, tốn I/O và lộ dữ liệu không cần thiết.

Đây là lợi ích vận hành điển hình của hierarchy: thay đổi ở một package mà không cần sửa từng câu lệnh log trong nhiều lớp.

### Tách đích ghi log theo thành phần

Một logger con có thể gắn appender riêng cho audit kỹ thuật, tác vụ batch hoặc module cần điều tra. Khi đó phải quyết định rõ log có tiếp tục đi lên root hay không.

Nếu mục tiêu là có **cả bản ghi tập trung lẫn bản ghi riêng**, có thể cố tình để additivity=true và gắn hai appender đến **hai đích khác nhau**. Nếu hai appender cùng trỏ tới một file/console, sự kiện có thể bị lặp. Cần thử với một sự kiện thật để xác nhận mỗi đích nhận đúng số dòng.

Đối với dữ liệu cần bảo đảm kiểm toán hoặc lưu bền vững, chỉ tạo logger con với tên audit **không đủ** để mang lại cam kết lưu trữ. Phải thiết kế thêm cơ chế audit, phân quyền và bảo đảm dữ liệu tương ứng.

### Quan hệ với MDC và correlation ID

Logger con dùng để **phân loại nguồn mã**; correlation ID dùng để **liên hệ các bản ghi của cùng yêu cầu**. Không thay requestId bằng tên logger động.

Ví dụ một yêu cầu đi qua ba logger:

~~~text
com.example.orders.OrderController
com.example.orders.OrderService
com.example.orders.payment.PaymentGatewayClient
~~~

Mỗi logger vẫn giữ tên ổn định theo lớp, còn requestId/traceId được đặt trong ngữ cảnh bản ghi. Khi truy vấn, lọc theo requestId để xem xuyên suốt các logger; lọc theo namespace để xem hành vi của một nhóm mã.

## 9. Lỗi thường gặp với logger con

| Biểu hiện | Lý do có thể xảy ra | Cách kiểm tra |
| --- | --- | --- |
| Đã đặt parent INFO nhưng child không in DEBUG | Child vẫn kế thừa INFO, hoặc handler/appender đang lọc DEBUG | Kiểm tra effective level ở child, ngưỡng handler/appender và filter |
| Child có level FINE nhưng không thấy dòng FINE | Handler cấp cha đang đặt INFO/WARNING, hoặc parent routing bị tắt | Kiểm tra child.isLoggable, handler level và setUseParentHandlers |
| Bản ghi FINE xuất qua parent dù parent WARNING | Child chấp nhận FINE; parent handler đang cho phép FINE | Đây có thể là hành vi đúng: parent logger level không lọc lại sự kiện đã được con chấp nhận |
| Một sự kiện xuất hai lần | Child và parent cùng có handler/appender dẫn tới cùng đích | Kiểm tra JUL parent handlers hoặc Logback additivity và danh sách appender |
| Thêm additivity=false khiến log mất | Logger con không có appender riêng phù hợp | Gắn appender cần thiết hoặc cho phép chuyển tiếp về cha |
| Cấu hình theo package không tác dụng | Tên logger trong mã không khớp namespace cấu hình | Kiểm tra Logger.getName() hoặc logger name hiển thị trên log |
| Gọi getParent() trên SLF4J Logger không biên dịch | SLF4J facade không công bố API đó | Chỉ dùng getParent() trên java.util.logging.Logger; kiểm tra hierarchy qua backend |
| Log bất thường sau khi thêm bridge | Cùng sự kiện được đưa qua nhiều tuyến hoặc bridge vòng lặp | Xem sơ đồ chuyển tiếp JUL/SLF4J/Log4j 2 và dependency runtime |
| Đặt tên logger theo user/request khiến hệ thống khó quản lý | Tạo quá nhiều tên logger động | Giữ logger theo lớp/package; đưa ID vào structured fields/MDC |

Không nên xử lý hiện tượng log trùng bằng cách tùy tiện nâng level từ INFO lên ERROR. Điều đó che các sự kiện hữu ích mà không sửa đường chuyển tiếp gây lặp.

## 10. Bài tập suy luận

Giả sử có các thiết lập JUL:

~~~text
Parent:      app.orders, level = INFO
Child:       app.orders.payment, level = null
Handler cha: level = WARNING
Child:       useParentHandlers = true, không có handler riêng
~~~

Hỏi:

1. Child gọi info("created") có được logger chấp nhận không? Có xuất ở handler cha không?
2. Child gọi warning("retry") có xuất không?
3. Sau child.setLevel(Level.FINE), child gọi fine("debug") có xuất không?
4. Nếu đổi handler cha sang Level.ALL, kết quả câu 3 thay đổi thế nào?
5. Nếu child.setUseParentHandlers(false) mà không có handler riêng, điều gì xảy ra với WARNING?

**Đáp án kèm nguyên nhân:**

1. INFO được child chấp nhận vì kế thừa INFO, **nhưng không xuất** vì handler cha yêu cầu WARNING.
2. WARNING được child và handler cha chấp nhận, nên **xuất**.
3. FINE được child chấp nhận sau override nhưng bị **handler cha chặn** tại ngưỡng WARNING.
4. FINE **xuất** khi handler cho phép ALL; mức INFO ở parent logger không lọc lại sự kiện của child.
5. WARNING vẫn có thể được child chấp nhận về mặt level nhưng **không còn đích xuất** trong cấu hình này.

Bài tập cho thấy phải kiểm tra **cả điều kiện chấp nhận sự kiện và tuyến đến handler**, không chỉ kiểm tra thuộc tính level.

## 11. Quy tắc thực hành

Khi thiết kế logger con:

- Dùng tên ổn định theo package/lớp; thống nhất cách đặt tên giữa các module.
- Đặt level mặc định ở mức namespace cha; chỉ override ở namespace con có nhu cầu đặc biệt.
- Phân biệt rõ **level inheritance** và **event propagation** khi phân tích sự kiện không xuất hoặc xuất trùng.
- Kiểm tra ngưỡng/filter của handler/appender và additivity, không suy diễn chỉ từ level của root.
- Nếu framework đã quản lý backend và hierarchy, ưu tiên file cấu hình của framework thay vì thêm handler vào từng lớp.
- Giữ log chứa ngữ cảnh hữu ích nhưng không ghi thông tin bí mật; correlation ID thuộc nội dung/context, không thuộc logger name.
- Khi cần xác nhận hành vi, phát một sự kiện thử ở nhiều mức khác nhau và kiểm tra **đích thực sự nhận**.

**Ghi nhớ:** Logger con giúp nhóm và điều khiển log theo namespace. Một logger con có thể **kế thừa level** từ cha hoặc **đặt level riêng**, đồng thời có thể **chuyển sự kiện tới handler/appender của cha** hoặc ngắt chuyển tiếp. Hai quyết định này độc lập và kết quả cuối cùng còn phụ thuộc filter cùng nơi xuất log.