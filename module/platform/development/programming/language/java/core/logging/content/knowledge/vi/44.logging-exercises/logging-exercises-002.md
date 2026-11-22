# Dự án thực hành: Cấu hình logger theo package trong Java 17

## 1. Mục tiêu và kết quả cần đạt

Một ứng dụng Java thực tế có nhiều package: xử lý đơn hàng, thanh toán, audit, tích hợp ngoài và hạ tầng. Mỗi nhóm cần mức logging khác nhau. Khi điều tra lỗi đơn hàng, ta có thể bật log chi tiết cho **package orders** mà không bật DEBUG toàn bộ JVM hoặc ghi thừa dữ liệu thanh toán.

Dự án này giúp bạn:

1. Xây dựng một project Java 17 với các package thực sự tách biệt.
2. Tạo logger bằng tên class đầy đủ để logger hierarchy khớp Java package.
3. Cấu hình level của root và từng package qua **config/logging.properties**.
4. Biên dịch/chạy bằng **javac/java**, không cần Maven hay thư viện ngoài.
5. Đọc output xác định và hiểu vì sao một số event được ghi, một số bị chặn.
6. Viết chương trình kiểm tra policy: logger level, inheritance, handler threshold.
7. Phân biệt **chọn mức log** với **định tuyến log**.
8. Tìm hiểu cách biểu diễn cùng chính sách bằng Logback, Log4j2 và Spring Boot.
9. Đánh giá lỗi phổ biến, tính bảo mật, hiệu năng, test isolation và quy trình thay đổi level an toàn.

**Chủ đề:** Cấu hình logger theo package. **Ngữ cảnh:** Dự án thực hành trong Java Core Logging. Toàn bộ project chính dùng **java.util.logging (JUL)** thuộc JDK. Các bản Logback/Log4j2/Spring Boot ở phần sau là **lựa chọn thay thế** cần dependency/backend tương ứng; không trộn syntax config của chúng vào dự án JUL.

## 2. Yêu cầu nghiệp vụ mô phỏng

Ứng dụng demo gọi ba service theo thứ tự:

~~~text
App
 |
 +-- OrderService.reserve("O-101")
 |     +-- FINE: order.reserve.validate
 |     +-- INFO: order.reserved
 |
 +-- PaymentService.authorize("O-101")
 |     +-- FINE: payment.authorize.start
 |     +-- INFO: payment.authorized
 |     +-- WARNING: payment.gateway.slow
 |
 +-- AuditService.record("O-101")
       +-- INFO: audit.recorded
~~~

Các thao tác chỉ **phát log minh họa**, không gọi database, không lưu transaction, không thực hiện giao dịch thanh toán hoặc audit thật.

Chính sách:

| Phạm vi logger | Mức áp dụng | Kỳ vọng |
| --- | --- | --- |
| Root logger | INFO | Mặc định ghi INFO trở lên. |
| demo.shop.orders | FINE | Ghi FINE và INFO để debug nghiệp vụ đơn hàng. |
| demo.shop.payments | WARNING | Chỉ ghi WARNING/SEVERE, chặn FINE và INFO. |
| demo.shop.audit | INFO | Ghi INFO audit event giả lập. |
| ConsoleHandler | ALL | Không chặn thêm event đã vượt qua logger nguồn. |

Sau khi chạy App, chúng ta muốn nhìn đúng bốn log events:

~~~text
FINE demo.shop.orders.OrderService order.reserve.validate orderId=O-101
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

Hai event từ PaymentService ở FINE và INFO **không xuất hiện** do package payments được đặt WARNING. Những kết quả này đến từ **cấu hình level**, không phải những lời gọi logger bị xóa khỏi code.

## 3. Kiến thức về logger hierarchy

### 3.1. Tên logger và tên package

Với Java, thực hành thường dùng:

~~~java
// Minh họa trong class có tên OrderService.
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(
                OrderService.class.getName());
~~~

Nếu tên class là **demo.shop.orders.OrderService**, logger tương ứng có tên **demo.shop.orders.OrderService**. Vì vậy, cấu hình level cho **demo.shop.orders** có thể được kế thừa.

Các logger được tổ chức theo chuỗi tên phân tách bằng dấu chấm:

~~~text
root
  |
  +-- demo
       |
       +-- shop
            |
            +-- orders           FINE
            |    +-- OrderService (kế thừa)
            |
            +-- payments         WARNING
            |    +-- PaymentService (kế thừa)
            |
            +-- audit            INFO
                 +-- AuditService (kế thừa)
~~~

Tên Java package và logger category không bị JVM ràng buộc tuyệt đối. Nếu một class trong package orders gọi Logger.getLogger("business"), logger tên business **không tự kế thừa** policy demo.shop.orders.

**Khuyến nghị:** tạo logger từ **Class.getName()** hoặc một naming convention nhất quán. Khi refactor package, cần review cả logging config để không còn rule sai tên.

### 3.2. Configured level và effective level

Một logger con không đặt level riêng có thể kế thừa mức từ cha gần nhất có level. Trong JUL, **Logger.getLevel() == null** thường có nghĩa logger kế thừa, **không phải OFF**.

Ví dụ root INFO, orders FINE, OrderService không override class-level: OrderService có **effective level FINE**. PaymentService kế thừa WARNING.

### 3.3. Các level cơ bản trong JUL

| Level | intValue chuẩn | Ý nghĩa thường gặp |
| --- | ---: | --- |
| SEVERE | 1000 | Lỗi nghiêm trọng. |
| WARNING | 900 | Cảnh báo. |
| INFO | 800 | Thông tin hoạt động. |
| CONFIG | 700 | Thông tin cấu hình. |
| FINE | 500 | Chi tiết để gỡ lỗi. |
| FINER | 400 | Chi tiết sâu hơn. |
| FINEST | 300 | Chi tiết rất sâu. |
| OFF | Integer.MAX_VALUE | Tắt tại ngưỡng tương ứng. |
| ALL | Integer.MIN_VALUE | Cho phép tất cả tại ngưỡng tương ứng. |

FINE gần với DEBUG, WARNING gần với WARN, SEVERE gần với ERROR về mục đích. **Không mặc định mọi bridge JUL → SLF4J/Log4j2 có ánh xạ giống nhau** nếu chưa test provider thực.

### 3.4. Logger level khác Handler level

Đây là cơ chế quan trọng nhất:

~~~text
OrderService gọi LOG.fine(...)
            |
            v
Logger effective level FINE
    → chấp nhận event FINE
            |
            v
ConsoleHandler.level
    +-- ALL: nhận event FINE
    +-- INFO: loại event FINE
            |
            v
Formatter và stderr
~~~

Nếu logger nguồn đã nhận event, việc lan truyền lên parent handlers trong JUL **không nhất thiết dùng level của parent logger để lọc lại**. **Handler** vẫn có ngưỡng và Filter riêng. Vì vậy đặt root INFO không tự chặn mọi FINE từ package orders FINE nếu handler root đặt ALL.

Trong Logback cũng có điểm tương tự: một event DEBUG được logger con chấp nhận có thể đến appender root nhờ additivity dù root logger đặt INFO; threshold/filter của appender mới quyết định có lọc thêm hay không.

## 4. Cấu trúc project

Tạo thư mục **package-logger-demo**:

~~~text
package-logger-demo/
├── config/
│   └── logging.properties
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── shop/
│   │               ├── App.java
│   │               ├── orders/
│   │               │   └── OrderService.java
│   │               ├── payments/
│   │               │   └── PaymentService.java
│   │               └── audit/
│   │                   └── AuditService.java
│   └── test/
│       └── java/
│           └── demo/
│               └── shop/
│                   └── LogPolicyProbe.java
└── out/        (tạo trước khi biên dịch)
~~~

**Bốn source files trong main** tạo ứng dụng. **LogPolicyProbe.java** là test harness chạy bằng Java thuần, không cần JUnit. Mỗi dòng package phải khớp thư mục source.

Tất cả code dưới đây dùng JDK 17; phần level và handler được cấp qua file cấu hình để **không hard-code cấu hình runtime vào business methods**.

## 5. Tạo mã nguồn chính

### 5.1. App.java

Đường dẫn: **src/main/java/demo/shop/App.java**

~~~java
package demo.shop;

import demo.shop.audit.AuditService;
import demo.shop.orders.OrderService;
import demo.shop.payments.PaymentService;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        String orderId = "O-101";

        OrderService orders = new OrderService();
        PaymentService payments = new PaymentService();
        AuditService audit = new AuditService();

        orders.reserve(orderId);
        payments.authorize(orderId);
        audit.record(orderId);
    }
}
~~~

App không ghi System.out. Từng service chỉ dùng logger. Các lời gọi chạy **tuần tự một thread**, giúp output dễ dự đoán.

### 5.2. OrderService.java

Đường dẫn: **src/main/java/demo/shop/orders/OrderService.java**

~~~java
package demo.shop.orders;

import java.util.logging.Logger;

public final class OrderService {

    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void reserve(String orderId) {
        LOG.fine("order.reserve.validate orderId=" + orderId);
        LOG.info("order.reserved orderId=" + orderId);
    }
}
~~~

Khi package orders ở FINE, cả FINE và INFO được phép. Chúng là business/diagnostic events giả lập, không chứng minh có database commit.

### 5.3. PaymentService.java

Đường dẫn: **src/main/java/demo/shop/payments/PaymentService.java**

~~~java
package demo.shop.payments;

import java.util.logging.Logger;

public final class PaymentService {

    private static final Logger LOG =
            Logger.getLogger(PaymentService.class.getName());

    public void authorize(String orderId) {
        LOG.fine("payment.authorize.start orderId=" + orderId);
        LOG.info("payment.authorized orderId=" + orderId);
        LOG.warning("payment.gateway.slow orderId=" + orderId);
    }
}
~~~

Package payments ở WARNING nên FINE và INFO bị loại. WARNING có mặt trên terminal. Trong ứng dụng thật, ghi "gateway.slow" chỉ nên thực hiện khi đo được latency vượt ngưỡng, không phải phát WARNING ở mọi request.

### 5.4. AuditService.java

Đường dẫn: **src/main/java/demo/shop/audit/AuditService.java**

~~~java
package demo.shop.audit;

import java.util.logging.Logger;

public final class AuditService {

    private static final Logger LOG =
            Logger.getLogger(AuditService.class.getName());

    public void record(String orderId) {
        LOG.info("audit.recorded orderId=" + orderId);
    }
}
~~~

Đây **không phải audit store thực sự**. Một hệ thống yêu cầu audit bền vững, chống sửa đổi hoặc bảo đảm giao nhận cần hạ tầng chuyên biệt, không dựa duy nhất vào ConsoleHandler.

## 6. Cấu hình logging.properties

Đường dẫn: **config/logging.properties**

~~~properties
# Một ConsoleHandler gắn ở root logger.
handlers=java.util.logging.ConsoleHandler

# Mức mặc định cho các logger không override.
.level=INFO

# Handler nhận mọi event được phép từ logger nguồn.
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

# %4$s: level; %3$s: logger name; %5$s: message;
# %6$s: throwable; %n: newline.
java.util.logging.SimpleFormatter.format=%4$s %3$s %5$s%6$s%n

# Level riêng theo package.
demo.shop.orders.level=FINE
demo.shop.payments.level=WARNING
demo.shop.audit.level=INFO
~~~

Cách đọc file:

- **handlers** gắn ConsoleHandler vào root logger.
- **.level** là mức mặc định của root.
- **ConsoleHandler.level=ALL** ngăn handler loại thêm event FINE mà logger orders đã cho phép.
- **ConsoleHandler.formatter** chọn SimpleFormatter của JDK.
- **SimpleFormatter.format** cố định một dòng dạng level logger-name message, không có thời gian/hostname.
- Ba thuộc tính **demo.shop.<module>.level** quyết định ngưỡng theo namespace.

**Không nhầm các cú pháp:** JUL dùng FINE/WARNING/SEVERE. SLF4J/Logback dùng DEBUG/WARN/ERROR. Không thể thay FINE bằng DEBUG trong JUL logging.properties rồi mong JDK hiểu đúng.

### 6.1. Vì sao dùng SimpleFormatter và không để mặc định?

Formatter mặc định có thể in timestamp, source location và các chi tiết khác; điều này hữu ích trong production nhưng khó đưa ra output chính xác để học.

Ở project mẫu, định dạng **%4$s %3$s %5$s%6$s%n** dựa trên API SimpleFormatter: %4$s là log level, %3$s là logger name, %5$s là message đã định dạng, %6$s là Throwable và stack trace (nếu có), %n là xuống dòng. Ví dụ không phát Throwable nên mỗi event chỉ có một dòng.

Không dùng pattern này làm định dạng production bắt buộc: hệ thực nên có timestamp UTC, service/environment, correlation ID, event name, encoding/structured fields và quyền truy cập phù hợp.

### 6.2. ConsoleHandler ghi stderr

JUL ConsoleHandler xuất trên **System.err**. Vì thế bốn dòng trong hướng dẫn là **stderr**, không phải stdout. Nếu CI/test runner chỉ capture stdout, có thể không thấy chúng. Các bài test về level tốt hơn nên dùng in-memory Handler hoặc capture đúng stream.

## 7. Biên dịch và chạy project

Mở terminal tại thư mục **package-logger-demo**. Tạo out:

~~~bash
mkdir out
~~~

Biên dịch bốn file Java (một dòng; tránh phụ thuộc line-continuation của shell):

~~~bash
javac -encoding UTF-8 -d out src/main/java/demo/shop/App.java src/main/java/demo/shop/orders/OrderService.java src/main/java/demo/shop/payments/PaymentService.java src/main/java/demo/shop/audit/AuditService.java
~~~

Khởi động một JVM mới với file logging config được chỉ định tường minh:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties -cp out demo.shop.App
~~~

**Bốn dòng log dự kiến trên stderr:**

~~~text
FINE demo.shop.orders.OrderService order.reserve.validate orderId=O-101
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

Kết quả này giả định JDK 17+, chạy từ đúng thư mục gốc, logging.properties được nạp và không có system property bên ngoài ghi đè cấu hình formatter.

### 7.1. Giải thích output

- **orders FINE:** event order.reserve.validate được giữ.
- **orders INFO:** mức cao hơn FINE, được giữ.
- **payments FINE:** thấp hơn WARNING, bị loại.
- **payments INFO:** thấp hơn WARNING, bị loại.
- **payments WARNING:** đạt ngưỡng, được giữ.
- **audit INFO:** đạt ngưỡng INFO, được giữ.

Tổng cộng code gọi logger **sáu lần**, terminal có **bốn event**. Không phải PaymentService không chạy đến hai lệnh đầu; logger đã chặn chúng theo config.

### 7.2. Vì sao cần -Djava.util.logging.config.file?

JUL LogManager có cơ chế đọc properties cấu hình. Tham số JVM này trỏ tới file project thay vì phụ thuộc cấu hình mặc định trong JDK. Phải đặt **-D... trước tên main class**.

Chỉ biên dịch class files không đồng nghĩa Java tự tìm file config/logging.properties. Nếu app chạy trong IDE, hãy bảo đảm IDE dùng cùng working directory và JVM arguments.

### 7.3. Sửa properties có cần biên dịch lại không?

Không nhất thiết. Nếu chỉ đổi **logging.properties**, một JVM mới sẽ nạp cấu hình mới mà không cần biên dịch lại. Nếu đang chạy một ứng dụng lâu dài, sửa file trên disk **không mặc định tự hot-reload** vào LogManager; cần một cơ chế reload có kiểm soát hoặc restart.

Nếu sửa source Java hoặc đổi package, phải biên dịch lại và kiểm tra tên logger/config namespace.

## 8. Tạo test harness LogPolicyProbe.java

Đường dẫn: **src/test/java/demo/shop/LogPolicyProbe.java**

Chương trình này kiểm tra policy bằng hành vi thực của JUL:

- Logger orders cho phép FINE.
- Logger payments chặn INFO.
- Logger payments vẫn cho WARNING.
- Logger audit cho INFO.
- Handler WARNING chỉ capture WARNING khi logger orders phát FINE/INFO/WARNING.

Không dùng Java keyword assert vì nó mặc định có thể bị JVM bỏ qua nếu không bật -ea. Chương trình chủ động ném AssertionError khi điều kiện sai.

~~~java
package demo.shop;

import demo.shop.audit.AuditService;
import demo.shop.orders.OrderService;
import demo.shop.payments.PaymentService;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogPolicyProbe {

    private LogPolicyProbe() {
    }

    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    private static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Khong co I/O.
        }

        @Override
        public void close() {
            // Chi luu danh sach trong RAM.
        }

        List<String> captured() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Logger orders = Logger.getLogger(
                OrderService.class.getName());
        Logger payments = Logger.getLogger(
                PaymentService.class.getName());
        Logger audit = Logger.getLogger(
                AuditService.class.getName());

        check("orders FINE allowed",
                orders.isLoggable(Level.FINE));
        check("payments INFO blocked",
                !payments.isLoggable(Level.INFO));
        check("payments WARNING allowed",
                payments.isLoggable(Level.WARNING));
        check("audit INFO allowed",
                audit.isLoggable(Level.INFO));

        Logger ordersPackage = Logger.getLogger(
                "demo.shop.orders");
        boolean oldParentUse =
                ordersPackage.getUseParentHandlers();

        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.WARNING);
        ordersPackage.setUseParentHandlers(false);
        ordersPackage.addHandler(capture);

        try {
            orders.fine("probe.fine");
            orders.info("probe.info");
            orders.warning("probe.warning");

            check("handler WARNING filters",
                    capture.captured().equals(
                            List.of("WARNING:probe.warning")));
        } finally {
            ordersPackage.removeHandler(capture);
            capture.close();
            ordersPackage.setUseParentHandlers(oldParentUse);
        }

        System.out.println("ALL 5 CHECKS PASSED");
    }
}
~~~

### 8.1. Chạy test

Sau khi biên dịch phần main, biên dịch probe:

~~~bash
javac -encoding UTF-8 -cp out -d out src/test/java/demo/shop/LogPolicyProbe.java
java -Djava.util.logging.config.file=config/logging.properties -cp out demo.shop.LogPolicyProbe
~~~

**Stdout dự kiến:**

~~~text
PASS orders FINE allowed
PASS payments INFO blocked
PASS payments WARNING allowed
PASS audit INFO allowed
PASS handler WARNING filters
ALL 5 CHECKS PASSED
~~~

Probe không để event thử nghiệm tràn lên ConsoleHandler root: nó gắn một in-memory Handler ở logger package orders và tắt parent handlers của package này **trong phạm vi thử**, sau đó restore trạng thái trong finally.

### 8.2. Ý nghĩa từng điều kiện

| Điều kiện | Lớp cần kiểm tra |
| --- | --- |
| orders FINE allowed | Effective logger level của OrderService. |
| payments INFO blocked | Chính sách không cho INFO ở package payments. |
| payments WARNING allowed | Positive control: payments không bị OFF hoàn toàn. |
| audit INFO allowed | Package audit cho phép event nghiệp vụ INFO. |
| handler WARNING filters | Handler lọc thêm event đã được logger orders chấp nhận. |

Một test chỉ kiểm tra **Logger.getLevel()** của class có thể thất bại do getLevel()==null biểu thị kế thừa. **Logger.isLoggable** giúp kiểm tra kết quả cho phép tại logger, nhưng vẫn không bảo đảm Handler/Appender đã viết event. Bài test thứ năm bổ sung phần đó.

### 8.3. Test isolation

CaptureHandler là tài nguyên gắn vào **logger dùng chung theo tên**. Dù test này không sửa root, nó vẫn phải tháo Handler và restore useParentHandlers trong finally để tránh ảnh hưởng case khác. Trong test suite chạy song song, tránh thao tác cùng logger namespace từ nhiều test đồng thời.

## 9. Bài tập đổi level orders từ FINE sang INFO

Trong **config/logging.properties**, thay:

~~~properties
demo.shop.orders.level=INFO
~~~

Chạy App trong JVM mới. Dòng FINE của OrderService biến mất. Output còn:

~~~text
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

Chạy LogPolicyProbe sẽ **fail** tại điều kiện **orders FINE allowed**, đúng vì policy thực tế không còn khớp tiêu chí test baseline.

Nếu đây là thay đổi chủ đích và được phê duyệt, cần thay đổi test cùng policy mới. Không sửa test chỉ để che việc cấu hình vô tình mất DEBUG.

## 10. Bài tập đổi payments từ WARNING sang INFO

Thay trong config:

~~~properties
demo.shop.payments.level=INFO
~~~

Giữ orders FINE và audit INFO như ban đầu. Khi chạy App, dòng sau xuất hiện thêm trước WARNING:

~~~text
INFO demo.shop.payments.PaymentService payment.authorized orderId=O-101
~~~

Tổng log events sẽ là **năm**. FINE của payments vẫn bị chặn vì thấp hơn INFO. LogPolicyProbe sẽ fail ở điều kiện **payments INFO blocked**: test đang bảo vệ chính sách cũ là payments chỉ WARNING.

Trong hệ thống thực, một package không nên tự động bị đặt WARNING nếu điều đó làm mất business events quan trọng. Chọn level dựa trên chính sách vận hành chứ không áp dụng mẫu này một cách máy móc.

## 11. Bài tập Handler lọc log dù logger cho phép

Thay:

~~~properties
java.util.logging.ConsoleHandler.level=WARNING
~~~

Với các package levels baseline, ConsoleHandler chỉ nhận WARNING trở lên. Kết quả trên stderr là:

~~~text
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
~~~

Điều thú vị: **OrderService vẫn có logger FINE** và có thể tạo event FINE/INFO; **AuditService vẫn có logger INFO**; nhưng ConsoleHandler chặn những event này. Đây là ví dụ vì sao "logger có level FINE" không đồng nghĩa "console hiển thị FINE".

Nếu probe chạy, bốn kiểm tra isLoggable vẫn có thể PASS vì chúng quan sát **logger**, không phải ConsoleHandler. Test in-memory Handler WARNING cũng vẫn PASS vì dùng ngưỡng handler riêng.

## 12. Bài tập package không có cấu hình riêng

Giả sử tạo file mở rộng:

~~~java
package demo.shop.shipping;

import java.util.logging.Logger;

public final class ShippingService {
    private static final Logger LOG =
            Logger.getLogger(ShippingService.class.getName());

    public void ship(String orderId) {
        LOG.fine("shipping.check orderId=" + orderId);
        LOG.info("shipping.scheduled orderId=" + orderId);
    }
}
~~~

Đây là **bài tập bổ sung**, chưa được App baseline gọi. Nếu tạo file và gọi ship() sau khi biên dịch lại, logger thuộc **demo.shop.shipping** không có override sẽ kế thừa root INFO: shipping.check FINE bị chặn và shipping.scheduled INFO được ghi.

Nếu muốn debug riêng shipping, thêm:

~~~properties
demo.shop.shipping.level=FINE
~~~

Không nên đổi root FINE chỉ để debug shipping, vì làm tăng log chi tiết của nhiều package không liên quan.

## 13. Bài tập override tại mức class

Có khi chỉ một class cần debug:

~~~properties
demo.shop.orders.level=INFO
demo.shop.orders.OrderService.level=FINE
~~~

Khi đó OrderService có FINE, nhưng các class khác dưới demo.shop.orders không có override riêng tiếp tục kế thừa INFO. Đây là cách thu hẹp phạm vi hơn so với bật FINE cho toàn bộ package orders.

Một logger category tạo bằng literal string khác class name có thể không chịu rule này. Khi test fail, kiểm tra **logger.getName()** thực tế.

## 14. Phân biệt level và routing theo package

Cấu hình level:

~~~text
orders FINE    ──> quyết định event nào được phép
payments WARN  ──> quyết định event nào được phép
~~~

Định tuyến:

~~~text
orders events   ──> Console / orders.log / collector
payments events ──> Console / payments.log / collector
~~~

**Một property demo.shop.orders.level=FINE không tự tạo orders.log.** Nếu cần file riêng, phải tạo FileHandler hoặc appender tương ứng, gắn vào đúng logger/category và chọn parent propagation.

Với JUL:

- **Logger.setUseParentHandlers(true)**: có thể gửi event tới handlers của cha.
- **Logger.setUseParentHandlers(false)**: ngắt đường đi tới handlers của cha.
- Handler còn có **setLevel** và **Filter** riêng.
- Nếu tắt parent handlers mà không có handler thay thế, event có thể không đến đâu dù logger cho phép.
- Nếu gắn hai handlers cùng trỏ tới một sink và giữ parent propagation, có thể xuất log trùng.

Khi mở rộng bài thực hành sang file log, cần kiểm soát file path, rotation, permission, retention và close/flush. Không xem file appender là bảo đảm giao nhận exactly-once.

## 15. Log trùng: phân biệt hai nguyên nhân

**Nguyên nhân A — routing duplicate:** cùng một LogRecord đi qua hai handlers/appenders có chung output. Khắc phục bằng thiết kế hierarchy và parent propagation/additivity.

**Nguyên nhân B — code tạo nhiều events:** repository log ERROR rồi throw, service log ERROR rồi throw, controller lại log ERROR cùng exception. Đó là ba lời gọi logging riêng. Giảm additivity không tự giải quyết; cần xác định **một boundary sở hữu terminal failure log**.

Khi điều tra, dùng trace ID/request ID, logger name, event name và Throwable cause để xem là một event bị xuất hai lần hay nhiều event được tạo tại các tầng.

## 16. Mở rộng sang SLF4J + Logback

Trong nhiều ứng dụng Java, code dùng **SLF4J API** và backend **Logback**. Policy cùng ý tưởng nhưng tên level và file config khác:

- JUL dùng FINE, WARNING, SEVERE và logging.properties.
- Logback/SLF4J thường dùng DEBUG, WARN, ERROR và logback.xml.
- SLF4J LoggerFactory.getLogger(OrderService.class) tạo logger theo tên class.

Code minh họa khi project có SLF4J dependency:

~~~java
package demo.shop.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void reserve(String orderId) {
        LOG.debug("order.reserve.validate orderId={}", orderId);
        LOG.info("order.reserved orderId={}", orderId);
    }
}
~~~

Đây là **bản thay thế**, không dùng chung file class với bản JUL trong phần 5; cần SLF4J API và provider Logback tương thích.

Ví dụ file **src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.shop.orders" level="DEBUG"/>
    <logger name="demo.shop.payments" level="WARN"/>
    <logger name="demo.shop.audit" level="INFO"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Trong cấu hình này chỉ root gắn appender, các logger package để event đi tới root theo **additivity** mặc định. Logger orders DEBUG đã chấp nhận DEBUG event thì root INFO không tự lọc lại event ở bước appender propagation; nếu muốn console chỉ nhận INFO trở lên, đặt **ThresholdFilter** ở appender.

### 16.1. Logback additivity và bản ghi trùng

Nếu thêm appender CONSOLE cho logger orders mà root cũng gắn cùng CONSOLE, additivity=true có thể làm cùng event xuất hiện hai lần. Muốn tách routes, có thể đặt additivity=false **khi logger con có appender riêng**. Đừng đặt false mà quên appender, vì event sẽ không tiếp tục lên root.

**Effective level** và **additivity** là hai khái niệm khác nhau: một cái quyết định logger nguồn cho phép event, một cái quyết định appender inheritance.

## 17. Mở rộng sang Log4j2

Một ứng dụng có Log4j2 API/Core hoặc SLF4J provider phù hợp có thể dùng **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="demo.shop.orders" level="debug"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Logger name="demo.shop.payments" level="warn"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Logger name="demo.shop.audit" level="info"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Mỗi package logger có appender CONSOLE riêng và **additivity=false**, nên không truyền event lên root thêm lần nữa. Một phương án khác là chỉ gắn appender ở root và giữ additivity=true.

Không sao chép XML Logback sang Log4j2: LoggerConfig, AppenderRef, Filter và schema khác nhau. Cũng không kỳ vọng file Log4j2 điều khiển được JUL project nếu chưa dùng bridge/backend thích hợp.

## 18. Spring Boot: cấu hình theo package

Trong ứng dụng **Spring Boot**, có thể khai báo:

~~~properties
logging.level.root=INFO
logging.level.demo.shop.orders=DEBUG
logging.level.demo.shop.payments=WARN
logging.level.demo.shop.audit=INFO
~~~

Hoặc **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    demo.shop.orders: DEBUG
    demo.shop.payments: WARN
    demo.shop.audit: INFO
~~~

Đây là cấu hình dành cho **Spring Boot logging system**, không phải file JUL thuần ở phần 6. Spring Boot thường tích hợp logging backend và property sources theo profile, environment variables, command line và cấu hình runtime.

### 18.1. Dev/test/staging/prod

Một chính sách minh họa:

| Môi trường | Root | Orders | Payments |
| --- | --- | --- | --- |
| dev | INFO | DEBUG | INFO |
| test | INFO | DEBUG hoặc INFO có chủ đích | WARN |
| staging | INFO | INFO | WARN |
| prod | INFO | INFO | WARN |

Đây là gợi ý, **không phải mặc định bắt buộc**. Với event thanh toán quan trọng, không nên chặn toàn bộ INFO chỉ vì mẫu trên đặt WARN; phải chọn severity đúng nghiệp vụ.

### 18.2. Runtime overrides

Một biến môi trường như **LOGGING_LEVEL_ROOT** có thể thay mức root theo cơ chế cấu hình của Spring Boot. Actuator **/actuator/loggers**, nếu được cài và bật an toàn, có thể cho đọc/đổi logger levels lúc chạy.

Chỉ cho operator có quyền thay, ghi lại mức cũ và khôi phục sau khi điều tra. Không mở endpoint quản trị logging công khai; bật DEBUG hẹp và có thời hạn.

Một test chỉ đọc giá trị Environment property **không tự chứng minh** backend/appender thực đã xuất event đúng. Cần kiểm tra effective logger level và capture output.

## 19. Kiểm thử Logback/Log4j2 trong project thực

Với Logback + JUnit 5, có thể gắn **ListAppender** để bắt ILoggingEvent và assert:

- DEBUG xuất hiện khi orders DEBUG.
- DEBUG không xuất khi orders INFO.
- WARN/ERROR quan trọng vẫn còn.
- Logger name đúng package.
- Exception cause được giữ khi cần.
- Không có duplicate ngoài dự kiến.
- Gỡ appender và restore level ở finally.

Đoạn snippet (cần imports và dependencies JUnit/Logback):

~~~java
// Minh họa, không phải chương trình độc lập.
Logger logger = (Logger) LoggerFactory.getLogger(
        "demo.shop.orders.OrderService");

Level oldLevel = logger.getLevel();
ListAppender<ILoggingEvent> capture = new ListAppender<>();
capture.start();
logger.addAppender(capture);

try {
    logger.setLevel(Level.INFO);
    logger.debug("should-not-appear");
    logger.info("visible");
    // Assert capture.list có một INFO event, không có DEBUG.
} finally {
    logger.detachAppender(capture);
    capture.stop();
    logger.setLevel(oldLevel);
}
~~~

ListAppender in-memory không xác minh production FileAppender/ConsoleAppender hoặc collector; cần integration test riêng. Không chạy song song nhiều test cùng đổi level/root logging context mà thiếu isolation.

## 20. Structured logs, MDC và context

Một logger theo package giúp chọn level và routing, nhưng không tự cung cấp **trace ID, request ID hoặc business event ID**. Dữ liệu structured có thể như sau:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "service.name": "shop-service",
  "logger.name": "demo.shop.orders.OrderService",
  "severity_text": "INFO",
  "event": "order.reserved",
  "order_id": "O-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Đây là JSON minh họa, **không phải output mặc định của JUL SimpleFormatter**. Một hệ dùng OpenTelemetry/MDC cần propagate context qua threads/HTTP/messaging đúng cách.

**Bảo mật:** Không log password, token, API key, Cookie, raw request body hoặc thông tin thanh toán chỉ vì bật DEBUG/FINE cho package. DEBUG tắt production hôm nay có thể bật ngày mai. Dữ liệu không cần thiết phải bị loại ở **nguồn phát**, không chỉ nhờ filter ở collector.

Với input do client điều khiển, kiểm tra grammar và độ dài requestId/orderId, escape CRLF để tránh log injection. Tenant ID dùng cho quyền đọc/routing phải đến từ thông tin đã xác thực, không từ header tự khai.

## 21. Hiệu năng và độ tin cậy

Khi bật level FINE/DEBUG cho một package nhiều class, lượng log có thể tăng mạnh:

- Mỗi request qua nhiều methods và retries.
- Stack trace và JSON fields làm record lớn.
- Console/file/collector tăng CPU, disk I/O và network.
- Async queue có thể đầy, drop hoặc gây backpressure.
- Central log index tăng chi phí và độ trễ ingestion.

Nếu có 10.000 requests/giây và mỗi request tạo thêm 20 DEBUG records, đó là **200.000 records/giây** bổ sung trong mô hình đơn giản. Không nên bật debug rộng và lâu chỉ để điều tra một lỗi hẹp.

Một chính sách vận hành hợp lý:

1. Root INFO hoặc mức được duyệt.
2. Tăng mức chi tiết ở **một package/class cụ thể**.
3. Gắn thời hạn/điều kiện khôi phục.
4. Theo dõi rate/bytes, dropped events, queue và ingestion lag.
5. Không dùng log count làm số request tuyệt đối nếu pipeline có sampling/drop.
6. Không thay logging settings làm mất những security/audit events bắt buộc.
7. Xác minh appender/collector/storage và retention phù hợp.

## 22. Những lỗi hay gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đặt orders FINE vẫn không có FINE | ConsoleHandler còn INFO; config không nạp; sai logger name. | Kiểm tra JVM -D, handler level, isLoggable. |
| Logger.getLevel() trả null | Logger con kế thừa. | Test effective behavior, đừng coi null là OFF. |
| DEBUG xuất dù root INFO | Logger con override DEBUG và appender nhận qua propagation. | Xem effective level của logger nguồn. |
| Payments INFO vẫn xuất | Package rule sai tên hoặc class-level override. | Đối chiếu logger.getName và property. |
| Một log xuất hai lần | Parent handlers/additivity và nhiều appenders cùng sink. | Thiết kế lại routing, đếm per-sink. |
| Một package không có log | Tắt parent propagation mà thiếu handler riêng. | Gắn handler hoặc bật propagation. |
| File config không có tác dụng | Sai đường dẫn hoặc đang dùng backend khác. | Xác minh JVM args và logging provider. |
| Test chỉ capture stdout | JUL ConsoleHandler xuất stderr. | Dùng in-memory Handler hoặc stderr capture đúng. |
| Production vẫn nhiều DEBUG | Env/Actuator/runtime override hoặc class-specific level. | Xem cấu hình hiệu lực sau bootstrap. |
| Thay source package làm mất policy | Config namespace cũ. | Cập nhật package name và regression test. |
| App bị chậm sau bật FINE | Volume/encoder/collector quá tải. | Bật debug hẹp, đo rate/queue. |
| Log lộ token khi DEBUG | Code/encoder log dữ liệu thô. | Sửa nguồn, thêm sentinel security tests. |

### 22.1. Đừng chữa lỗi bằng root DEBUG

Nếu chỉ cần debug orders, đặt **demo.shop.orders.level=FINE** thay vì **.level=FINE**. Root FINE làm nhiều namespace không override phát log chi tiết và có thể gây quá tải hoặc rò dữ liệu từ thư viện.

### 22.2. Đừng dùng level để thay thế routing

Một package đặt DEBUG không tự tạo file riêng. Cần handler/appender và test output. Nếu muốn audit log bền vững, phải thiết kế thêm storage, integrity, access và retention; không thể đạt bằng một property level.

### 22.3. Đừng log rồi throw ở mọi tầng

Nếu repository, service và controller đều log ERROR cùng exception rồi rethrow, đó là nhiều events độc lập do code tạo ra, không phải lỗi additivity. Chọn boundary chịu trách nhiệm terminal error log, giữ cause/context và tránh duplication.

## 23. Ma trận kiểm thử hoàn chỉnh

| Kịch bản | Logger source | Handler/Appender | Kỳ vọng |
| --- | --- | --- | --- |
| Baseline orders | FINE | ALL | FINE/INFO xuất. |
| Baseline payments | WARNING | ALL | FINE/INFO không xuất; WARNING xuất. |
| Baseline audit | INFO | ALL | INFO xuất. |
| Orders chuyển INFO | INFO | ALL | FINE biến mất, INFO còn. |
| Payments chuyển INFO | INFO | ALL | INFO xuất thêm, FINE vẫn mất. |
| Console chuyển WARNING | Orders FINE | WARNING | FINE/INFO không ra console. |
| Package shipping không override | Kế thừa root INFO | ALL | Shipping INFO xuất, FINE không. |
| Class override FINE | Package INFO, class FINE | ALL | Chỉ class override phát FINE. |
| Parent propagation false | Logger có handler riêng | Handler kiểm soát | Không lên root, không mất nếu có đích. |
| Parent propagation false nhưng không handler | Logger cho phép | Không đích | Event không xuất dù level đúng. |
| Hai appender chung console | Logger cho phép | Duplicate routes | Phát hiện và sửa trùng. |
| Bật DEBUG trong test | Logger scope hẹp | Encoder thật | Không lộ secrets/PII. |
| Collector async/backpressure | Logger cho phép | Async pipeline | Có metric, test timeout/flush. |
| Spring Boot profile prod | Root INFO | Backend thật | Package levels đúng deployment. |

**Positive và negative assertions phải đi cùng nhau.** Một test chỉ bảo đảm "DEBUG không có" có thể PASS giả khi toàn bộ logging đã tắt; test phải chứng minh một event WARNING/INFO hợp lệ vẫn đến sink.

## 24. Checklist review trước khi hoàn thành

- [ ] Tạo đủ **App, OrderService, PaymentService, AuditService** trong package đúng.
- [ ] Đặt **config/logging.properties** ở đường dẫn được JVM đọc.
- [ ] Logger sử dụng Class.getName() để đồng bộ với package.
- [ ] Root INFO và các package FINE/WARNING/INFO theo policy baseline.
- [ ] ConsoleHandler ALL để không lọc nhầm FINE.
- [ ] Biên dịch được bằng JDK 17, không cần dependency.
- [ ] Chạy App nhận bốn log events trên stderr.
- [ ] Biên dịch và chạy LogPolicyProbe nhận năm PASS trên stdout.
- [ ] Đã thử đổi level orders, payments và handler threshold.
- [ ] Biết hiệu lực của class override và package inheritance.
- [ ] Không nhầm configured level null với OFF.
- [ ] Không để duplicate handler/appender hoặc mất đích vì additivity.
- [ ] Không nhầm config JUL với Logback/Log4j2/Spring Boot.
- [ ] Test cleanup mức log/handler/MDC khi thao tác động.
- [ ] Không log secret, token, raw header/body khi tăng DEBUG.
- [ ] Có chính sách volume/retention, kiểm tra async/collector nếu đưa production.

## 25. Bài tập tự luyện

1. Chạy App và giải thích vì sao code có sáu lời gọi logger nhưng chỉ bốn dòng.
2. Chạy LogPolicyProbe và cho biết mỗi điều kiện bảo vệ policy nào.
3. Thay orders FINE thành INFO, dự đoán và kiểm chứng log biến mất.
4. Thay payments WARNING thành INFO, dự đoán và kiểm chứng log xuất thêm.
5. Đặt ConsoleHandler WARNING; vì sao isLoggable(FINE) ở orders vẫn true?
6. Bỏ override audit; nó có ghi INFO do root INFO không?
7. Thêm ShippingService, thử kế thừa root INFO rồi override FINE riêng.
8. Chỉ bật FINE cho OrderService, còn lớp OrderValidator ở package orders vẫn INFO.
9. Thiết kế FileHandler cho orders, giữ console root, kiểm tra log trùng.
10. Chuyển project sang SLF4J/Logback, dùng logback.xml với DEBUG orders và WARN payments.
11. Thực hiện tương tự với Log4j2 và giải thích AppenderRef/additivity.
12. Tạo application-dev/prod.properties trong Spring Boot và smoke test effective levels.
13. Viết test với dummy token ở request object, bật DEBUG trong môi trường cô lập và chứng minh token không được log.
14. Đặt giới hạn thời gian phiên debug package rồi khôi phục cấu hình và quan sát log volume.
15. Phân biệt event tạo ra ở logger với event đã được collector index.

## 26. Tổng kết

**Cấu hình logger theo package** cho phép tăng mức quan sát ở một nhóm code mà không làm toàn bộ ứng dụng phát log chi tiết. Dự án Java 17 dùng **JUL** thể hiện đầy đủ chuỗi **logger name → hierarchy → effective level → Handler threshold → Formatter → stderr**. File logging.properties thay đổi hành vi runtime mà không sửa business methods.

Ba điểm cần nhớ:

1. **Cấu hình logger theo package chọn event nào được phép ghi.** Logger con có thể kế thừa hoặc override mức cha.
2. **Handler/appender/filter và propagation quyết định event đi tới đâu.** Một event đã được logger cho phép vẫn có thể bị chặn ở đích, hoặc xuất trùng do nhiều routes.
3. **Kiểm thử phải bao phủ cả chiều cho phép và chiều bị loại**, cleanup trạng thái, kiểm tra quyền riêng tư và xác minh cấu hình backend thực.

Cùng tư duy này áp dụng được cho **SLF4J/Logback, Log4j2 và Spring Boot**, nhưng phải dùng đúng level names, config format, backend dependencies và quyền vận hành. Dự án thực hành là nền tảng trước khi mở rộng sang tách file log, collector, tracing, test production profiles và điều khiển logger động.

### Tài liệu tham khảo chính thức

- Java SE 17 — Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java SE 17 — LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Java SE 17 — Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Java SE 17 — Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Java SE 17 — ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Java SE 17 — SimpleFormatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- Logback Architecture — hierarchy/additivity: https://logback.qos.ch/manual/architecture.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Logback Filters: https://logback.qos.ch/manual/filters.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 Filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- SLF4J Manual: https://www.slf4j.org/manual.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Actuator loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html