# Logger theo package trong Java

## 1. Logger theo package là gì?

Trong ứng dụng Java, mã thường được tổ chức theo các **package** như `com.example.catalog`, `com.example.orders`, `com.example.orders.internal`. Logging có thể đi theo chính cấu trúc này: tên logger thể hiện package (hoặc tên lớp thuộc package đó), nhờ đó người vận hành cấu hình mức ghi và điểm xuất bản ghi cho **một nhóm thành phần** thay vì phải chỉnh từng câu lệnh log.

Ví dụ, khi xử lý chậm ở phần đặt hàng, ta có thể tăng mức chi tiết của `com.example.orders` để quan sát các lớp trong nhánh đó, trong khi các package khác vẫn giữ mức `INFO`. Cách làm này giúp giảm nhiễu, tiết kiệm chi phí lưu log và khoanh vùng sự cố.

Hai cách đặt tên phổ biến:

```java
import java.util.logging.Logger;

// Một logger chung cho các lớp trong package:
Logger packageLogger = Logger.getLogger("com.example.orders");

// Một logger theo tên lớp, thường được khuyến nghị để biết nguồn cụ thể:
Logger classLogger = Logger.getLogger(OrderService.class.getName());
```

Đoạn trên chỉ minh họa cách đặt tên; `OrderService` là lớp giả định trong dự án, chưa phải chương trình Java độc lập.

Điều cần hiểu: **tên logger là một chuỗi định danh**, không phải một đối tượng Java `Package`. API `Logger.getLogger(String name)` không tự kiểm tra tên ấy có trùng package thật hay không. Nhà phát triển chọn quy ước “tên logger đi theo package”, còn hệ thống logging sử dụng cấu trúc tên để áp dụng cấu hình phân cấp. Với Java 9 trở lên, `OrderService.class.getPackageName()` lấy tên package thực tế của lớp; `OrderService.class.getName()` lấy tên đầy đủ của lớp, bao gồm package.

### Vì sao không dùng một logger duy nhất cho toàn ứng dụng?

Giả sử mọi lớp đều gọi `Logger.getLogger("application")`. Dòng thông báo có thể biết điều gì xảy ra, nhưng khó tách nguồn theo package. Khi muốn xem chi tiết riêng tính năng thanh toán, bật `FINE` cho logger chung sẽ làm các thành phần không liên quan cũng trở nên ồn ào.

Đặt tên phân cấp tạo một cây để **điều chỉnh đúng phạm vi**:

```text
com.example
├── com.example.orders
│   ├── com.example.orders.OrderService
│   └── com.example.orders.internal
│       └── com.example.orders.internal.StockChecker
└── com.example.payments
    └── com.example.payments.PaymentService
```

Tên lớp ở cuối cây chỉ xuất hiện như logger node nếu chương trình thực sự tạo logger mang tên ấy. Cây trên mô tả **quan hệ tên logger có thể dùng**, không khẳng định thư viện tự đăng ký tất cả package hay class của project.

## 2. Hai cách dùng: một logger cho package hoặc một logger cho lớp

| Tiêu chí | Logger theo package | Logger theo lớp |
| --- | --- | --- |
| Lấy tên | `Logger.getLogger(OrderService.class.getPackageName())` | `Logger.getLogger(OrderService.class.getName())` |
| Ví dụ tên | `com.example.orders` | `com.example.orders.OrderService` |
| Mục đích | Gom sự kiện của nhiều lớp cùng package | Ghi rõ nguồn lớp phát log |
| Cấu hình theo package | Áp dụng trực tiếp | Vẫn áp dụng nhờ quan hệ tên phân cấp |
| Đánh đổi | Ít phân biệt chính xác lớp trong trường logger | Nhiều logger name hơn nhưng linh hoạt hơn |

Cả hai cách đều có thể hợp lý. Trong dự án có nhiều lớp, một lựa chọn phổ biến là **mỗi lớp khai báo logger riêng theo tên lớp**, còn mức log được đặt ở **cấp package** qua cấu hình. Cách này có cả thông tin nguồn chi tiết và khả năng bật/tắt cho toàn bộ nhánh. Logger theo package đúng nghĩa hữu ích khi yêu cầu chỉ cần nhóm nguồn ở package, chẳng hạn trong một ví dụ hoặc thành phần nhỏ.

Với JUL (`java.util.logging`), ví dụ trong `com.example.orders`:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

Với SLF4J (API facade, cần dependency và backend phù hợp):

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
```

Hai đoạn là **minh họa đặt logger trong một lớp**; không biên dịch độc lập nếu thiếu phần khai báo lớp tương ứng. Với SLF4J, cấu hình logger thực tế do backend như Logback hoặc Log4j2 đảm nhận.

Không nên tạo tên logger từ request ID, user ID hay dữ liệu không giới hạn giá trị, ví dụ `Logger.getLogger("orders." + userId)`. Tên logger nên ổn định theo thành phần; correlation ID hoặc request ID thuộc về ngữ cảnh sự kiện, không phải tên logger.

## 3. Cơ chế phân cấp theo dấu chấm

Trong JUL, các logger có tên dạng phân cấp, dùng dấu chấm `.` để phân đoạn tên. Nếu `com.example.orders` có logger cha `com.example` đã tồn tại, logger con có thể kế thừa mức log từ cha. Đây là quan hệ **logger**, không phải quan hệ kế thừa lớp Java hay cấu trúc thư mục.

Ví dụ chính sách:

| Logger | Mức cấu hình | Mức hiệu lực điển hình |
| --- | --- | --- |
| `com.example` | `INFO` | `INFO` |
| `com.example.orders` | `null` (không đặt riêng) | `INFO` từ cha |
| `com.example.orders.internal` | `null` | `INFO` từ tổ tiên gần nhất có mức |
| `com.example.payments` | `WARNING` | `WARNING` |
| `com.example.payments.PaymentService` | `null` | `WARNING` từ cha |

Trong JUL, `logger.setLevel(null)` nghĩa là **kế thừa mức từ cha**, không phải cho phép mọi bản ghi. `Level.ALL` mới là mức cho phép tất cả các mức (ở bước kiểm tra level); `Level.OFF` dùng tắt logging tại logger đó.

Một cách tư duy:

```text
com.example                       INFO
  |
  +-- com.example.orders           (kế thừa INFO)
  |       |
  |       +-- .internal             (kế thừa INFO)
  |
  +-- com.example.payments         WARNING
```

Nếu thay mức của `com.example.orders` từ kế thừa sang `FINE`, các logger con không đặt mức riêng có thể bắt đầu tạo thêm bản ghi `FINE`. Điều đó **chưa bảo đảm sẽ thấy bản ghi ở console hoặc file**, vì nơi nhận log có thể có ngưỡng riêng.

### Mức log tại logger khác mức log tại handler

Có hai câu hỏi độc lập:

1. **Logger có chấp nhận tạo bản ghi không?** Ví dụ logger hiệu lực `INFO` sẽ chặn `FINE`.
2. **Handler/appender có ghi bản ghi đã được tạo không?** Ví dụ `ConsoleHandler` được đặt `WARNING` sẽ bỏ `INFO` ngay cả khi logger nguồn đã chấp nhận.

Trong JUL, khi bản ghi từ logger con đi tới các handler của logger cha, **mức của logger cha không được dùng để lọc lại bản ghi đã tạo**. Thay vào đó, ngưỡng và `Filter` trên từng handler quyết định việc xuất. Vì vậy, bản ghi `FINE` do một logger con đã bật `FINE` có thể đi tới handler cha đang cho `FINE`, dù logger cha đặt mức `INFO`. Đừng dựa vào ngưỡng logger cha như một lớp bảo vệ cuối cùng ở nơi ghi.

### Lan truyền và log trùng

JUL có `setUseParentHandlers(boolean)`; giá trị mặc định thường cho phép một bản ghi đi qua handler của logger hiện tại rồi lên các logger cha. Nếu gắn handler xuất console ở cả con lẫn cha, cùng một bản ghi có thể xuất hiện hai lần. Dùng `setUseParentHandlers(false)` ở đúng logger sẽ dừng gửi tiếp lên cha, nhưng cũng có thể làm mất bản sao lẽ ra được thu thập ở tuyến chung.

Trong Logback, khái niệm tương ứng thường được gọi là `additivity`. Cần kiểm tra cả **nơi gắn appender/handler** và **quy tắc lan truyền** khi gặp log trùng hoặc không thấy log.

## 4. Ví dụ Java 17 chạy được: nhiều package, một cấu hình chung

Ví dụ có ba nhánh package: `demo` (điểm cấu hình), `demo.orders` và package con `demo.orders.internal`, cùng `demo.payments`. Để quan sát chính xác, chương trình dùng một handler tự in một định dạng cố định ra stdout. Handler này chỉ phục vụ minh họa, không phải giải pháp logging production.

Tạo cấu trúc thư mục:

```text
src/
└── demo/
    ├── App.java
    ├── orders/
    │   ├── OrderService.java
    │   └── internal/
    │       └── StockChecker.java
    └── payments/
        └── PaymentService.java
```

**Tệp `src/demo/App.java`** — chọn mức cho từng package và gắn handler tại logger `demo`:

```java
package demo;

import demo.orders.OrderService;
import demo.payments.PaymentService;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class App {
    public static void main(String[] args) {
        Logger appLogger = Logger.getLogger("demo");
        appLogger.setLevel(Level.INFO);
        appLogger.setUseParentHandlers(false);

        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.printf("%s %s - %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        record.getMessage());
            }

            @Override
            public void flush() {
                // Mỗi bản ghi được in trực tiếp trong ví dụ.
            }

            @Override
            public void close() {
                // Không đóng System.out vì handler không sở hữu nó.
            }
        };
        console.setLevel(Level.ALL);
        appLogger.addHandler(console);

        Logger ordersLogger = Logger.getLogger("demo.orders");
        ordersLogger.setLevel(null); // Kế thừa INFO từ "demo".

        Logger paymentsLogger = Logger.getLogger("demo.payments");
        paymentsLogger.setLevel(Level.WARNING);

        new OrderService().process();
        new PaymentService().process();

        appLogger.removeHandler(console);
        console.close();
    }
}
```

**Tệp `src/demo/orders/OrderService.java`** — logger dùng tên package thực tế:

```java
package demo.orders;

import demo.orders.internal.StockChecker;
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getPackageName());

    public void process() {
        LOG.info("order.created");
        new StockChecker().check();
        LOG.warning("order.delayed");
    }
}
```

**Tệp `src/demo/orders/internal/StockChecker.java`** — package con kế thừa cấu hình từ `demo.orders`:

```java
package demo.orders.internal;

import java.util.logging.Logger;

public class StockChecker {
    private static final Logger LOG =
            Logger.getLogger(StockChecker.class.getPackageName());

    public void check() {
        LOG.info("stock.available");
        LOG.fine("stock.debug");
    }
}
```

**Tệp `src/demo/payments/PaymentService.java`** — mức `INFO` sẽ bị chặn bởi mức `WARNING` của package:

```java
package demo.payments;

import java.util.logging.Logger;

public class PaymentService {
    private static final Logger LOG =
            Logger.getLogger(PaymentService.class.getPackageName());

    public void process() {
        LOG.info("payment.started");
        LOG.warning("payment.retry");
    }
}
```

Từ thư mục chứa `src`, chạy bằng JDK 17 trở lên:

```bash
javac -d out src/demo/App.java src/demo/orders/OrderService.java src/demo/orders/internal/StockChecker.java src/demo/payments/PaymentService.java
java -cp out demo.App
```

**Stdout dự kiến:**

```text
INFO demo.orders - order.created
INFO demo.orders.internal - stock.available
WARNING demo.orders - order.delayed
WARNING demo.payments - payment.retry
```

Tại sao xuất hiện đúng bốn dòng?

1. `demo` có ngưỡng `INFO`. `demo.orders` không đặt ngưỡng riêng nên chấp nhận `INFO` và `WARNING`.
2. `demo.orders.internal` nằm trong nhánh đó và kế thừa `INFO`, do đó phát `stock.available` nhưng bỏ `stock.debug` ở mức `FINE`.
3. `demo.payments` đặt `WARNING` nên `payment.started` ở `INFO` bị bỏ ngay tại logger nguồn; `payment.retry` được giữ.
4. Handler tại `demo` được đặt `ALL` để không chặn thêm các bản ghi đã được logger chấp nhận. `appLogger.setUseParentHandlers(false)` giúp tránh xuất thêm qua handler của root logger JUL.
5. Mỗi lớp gọi `getPackageName()` để lấy đúng package của mình; khi nhiều lớp cùng package chọn cùng tên logger, chúng chia sẻ logger mang tên ấy.

Ví dụ trên cố ý không dùng timestamp vì mục tiêu là minh họa **quan hệ package → mức log → đầu ra có thể dự đoán**. Production nên dùng formatter có thời gian, logger name, level, ngữ cảnh liên kết và định dạng ổn định. Thực tế cũng cần xử lý đóng/flush bộ ghi, lỗi I/O và nhiều luồng đồng thời.

### Thử thay đổi có kiểm soát

Nếu đổi:

```java
ordersLogger.setLevel(Level.FINE);
```

thì `stock.debug` có thể xuất hiện do cả logger `demo.orders.internal` và handler `console` đều chấp nhận `FINE`. Lưu ý handler `demo` đang là `ALL`; **mức `INFO` của chính logger `demo` không lọc lại bản ghi `FINE` do logger con đã chấp nhận**, nên thay đổi này có tác dụng.

Nếu đổi:

```java
console.setLevel(Level.WARNING);
```

thì chỉ các bản ghi `WARNING` trong ví dụ được in, dù logger `demo.orders` vẫn có thể tạo `INFO`. Đây là minh họa sự khác nhau giữa **lọc tại nguồn** và **lọc tại nơi nhận**.

## 5. Cấu hình mức theo package trong hệ thống thực

Không nên để chính sách logging production cố định trong mã như `App.java` ở trên. Thay vào đó, mã nghiệp vụ thường khai báo logger một lần, còn ứng dụng triển khai chọn mức theo package bằng tệp cấu hình hoặc thông số lúc khởi động.

### 5.1. Ví dụ JUL bằng `logging.properties`

Đây là cấu hình cho **một ứng dụng JUL thông thường không có đoạn cấu hình bằng code ở phần 4**:

```properties
handlers=java.util.logging.ConsoleHandler

.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

demo.orders.level=FINE
demo.payments.level=WARNING
```

Nếu gọi JVM với:

```bash
java -Djava.util.logging.config.file=logging.properties -cp out demo.App
```

thì **`demo.App` của phần 4 vẫn tự cấu hình logger, handler và mức**; đặc biệt, nó đặt `ordersLogger.setLevel(null)` và `paymentsLogger.setLevel(WARNING)`. Do đó câu lệnh trên không phải ví dụ dùng để quan sát riêng hiệu lực của tệp `logging.properties`. Muốn cấu hình hoàn toàn từ tệp, hãy dùng một ứng dụng không tự gắn handler hoặc ghi đè mức tương ứng. Đây là khác biệt quan trọng giữa cấu hình ngoài và cấu hình trong mã.

Trong `logging.properties`, `demo.orders.level=FINE` cho phép mã dưới nhánh đơn hàng phát log chi tiết; `ConsoleHandler.level=ALL` bảo đảm handler không lọc lại. Với nhiều handler, mỗi handler cần ngưỡng và formatter phù hợp với kênh nhận.

### 5.2. Ví dụ SLF4J + Logback

Với ứng dụng chọn SLF4J làm API và Logback làm backend, có thể đặt `logback.xml` theo ý tưởng tương tự:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG" />
    <logger name="com.example.payments" level="WARN" />

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Cấu hình trên minh họa:

- `com.example.orders` và các logger có tên con phù hợp có thể phát mức `DEBUG` trở lên, dù root đặt `INFO`. Khi sự kiện đã được tạo, mức root không mặc nhiên chặn lại trên đường truyền tới appender của root.
- `com.example.payments` và nhánh con chỉ phát `WARN` trở lên, trừ khi có logger con với cấu hình mức cụ thể hơn.
- Appender ở root dùng cho toàn ứng dụng; `<logger>` theo package chỉ thay đổi ngưỡng, không tự động tạo thêm tệp hay kênh log.
- Không gắn thêm cùng một appender vào logger con mà vẫn để `additivity=true` nếu không muốn cùng bản ghi bị gửi trùng.

Cấu hình Logback **không áp dụng trực tiếp** cho JUL; cần xác định API và backend thực sự đang chạy. Các mức có tên khác nhau giữa thư viện: JUL thường có `FINE` và `SEVERE`, còn SLF4J/Logback dùng `DEBUG` và `ERROR`. Không thay tên mức bằng cách đoán rằng mọi backend đều dùng chung cú pháp.

### 5.3. Tên package so với tên lớp

Nếu code dùng:

```java
Logger.getLogger(OrderService.class.getName());
```

và tên lớp là `com.example.orders.OrderService`, cấu hình cho `com.example.orders` vẫn có thể chi phối logger lớp thông qua cấu trúc tên phân cấp. Nhờ đó có thể bật chi tiết cho cả package, rồi giảm chi tiết riêng một lớp gây nhiễu nếu backend hỗ trợ cấu hình mức riêng theo tên lớp.

Nếu code lại dùng logger chung theo tên package `com.example.orders`, tất cả lớp chia sẻ tên đó; lúc này muốn cấu hình riêng theo **logger name** cho một lớp sẽ không phân biệt được lớp nào phát sự kiện. Có thể dùng trường nguồn khác khi cần, nhưng lựa chọn tên logger theo lớp thường rõ ràng hơn.

## 6. Tình huống thực tế: khoanh vùng lỗi bằng package

Giả sử hệ thống có các nhánh:

- `com.example.api`: tiếp nhận HTTP request.
- `com.example.orders`: kiểm tra và tạo đơn.
- `com.example.payments`: gọi dịch vụ thanh toán.
- `com.example.notifications`: gửi thông báo.

Mặc định production ghi `INFO` để theo dõi sự kiện chính, `WARN`/`ERROR` cho lỗi. Khi có lỗi thanh toán không thường xuyên, nhóm vận hành cần thêm ngữ cảnh từ các bước bên trong payment service.

Một quy trình xử lý có kiểm soát:

1. Xác định hiện tượng (tỷ lệ lỗi, khoảng thời gian, mã lỗi) và package chịu trách nhiệm gần nhất; ví dụ `com.example.payments`.
2. Tạm tăng độ chi tiết của riêng package đó nếu có cơ chế cấu hình thích hợp. Dùng ngưỡng `DEBUG` (Logback) hoặc `FINE` (JUL), không bật chi tiết toàn ứng dụng.
3. Ghi sự kiện có cấu trúc: `event`, `status`, `duration_ms`, `error_code`, `trace_id`. Tránh dữ liệu cá nhân, mật khẩu, token, nội dung thẻ và request body nhạy cảm.
4. Kiểm tra ngưỡng của **appender/handler** và pipeline thu thập: bật mức tại logger nhưng appender vẫn chặn thì log mới sẽ không tới nơi xem.
5. Sau khi tìm nguyên nhân, đưa mức về chính sách bình thường để tránh tăng khối lượng lưu trữ, tải CPU và nguy cơ lộ thông tin.
6. Đối chiếu các sự kiện cùng `trace_id` qua nhiều package; logging theo package hỗ trợ lọc nguồn, nhưng **không thay thế correlation ID** để nối một request xuyên các thành phần.

Việc tăng mức theo package có thể thực hiện bằng thay đổi cấu hình và triển khai lại, hoặc bằng cơ chế cập nhật động nếu framework/app hỗ trợ; không phải mọi runtime đều tự đọc lại tệp cấu hình. Kiểm chứng cơ chế làm mới cấu hình của hệ thống cụ thể trước khi áp dụng trong vận hành.

## 7. Những chi tiết dễ hiểu sai

### 7.1. Package trong mã không tự tạo cấu hình logger

Câu lệnh `package com.example.orders;` không mặc nhiên tạo logger và không phát bản ghi nào. Cần dùng API logging để nhận đối tượng logger, gọi các phương thức phát sự kiện và có backend/handler phù hợp. Trong JUL, các logger thường được lấy bằng `Logger.getLogger(...)`; với SLF4J, lấy qua `LoggerFactory`.

### 7.2. Quan hệ “cha–con” được xác định bằng tên

`com.example.orders.internal` có thể nằm dưới `com.example.orders` trong cây logger theo quy tắc dấu chấm, dù vị trí file Java vật lý khác nhau hoặc class được biên dịch từ nguồn sinh ra. Ngược lại, nếu đặt logger tên tùy ý như `billing.debug` trong lớp thuộc `com.example.orders` thì cấu hình `com.example.orders` không tự áp dụng cho logger `billing.debug`.

### 7.3. Logger theo package không tự bảo đảm mọi lớp đều phát log

Từng lớp vẫn phải dùng logger và gọi các mức phù hợp. Một class ném exception nhưng không có đường xử lý nào log exception thì chỉ nâng mức package sẽ không tạo ra bản ghi mới. Thêm quá nhiều log cũng không làm hệ thống “quan sát được tốt hơn” nếu nội dung thiếu ý nghĩa, trùng lặp hoặc lộ bí mật.

### 7.4. Java package khác Java module

Java Platform Module System (JPMS) có khái niệm module và package riêng. Cấu hình logger theo `com.example.orders` thông thường dựa trên **tên logger**, không tự phân chia theo `module-info.java` hay ranh giới module. Khi cần tách theo module/runtime/service, phải bổ sung ngữ cảnh hoặc chính sách thích hợp.

### 7.5. Đổi package có thể làm thay đổi nguồn log

Refactor lớp từ `com.example.orders` sang `com.example.checkout` khiến `getPackageName()` và `getName()` thay đổi. Cấu hình mức và bộ lọc dựa trên tên cũ có thể không còn áp dụng. Sau refactor, cập nhật cấu hình, dashboard, bộ lọc collector và phép kiểm thử liên quan.

### 7.6. Cẩn thận với package mặc định

Lớp không khai báo `package` ở *unnamed package* trả về chuỗi rỗng cho `getPackageName()`. Tránh dùng package mặc định trong ứng dụng thực tế vì tên logger rỗng và tổ chức namespace sẽ thiếu rõ ràng. Nên đặt tên package có quy ước ổn định.

### 7.7. Logger name không phải ranh giới bảo mật

Đổi tên logger hoặc tách package không ngăn ứng dụng khác đọc file log. Quyền truy cập, loại dữ liệu được ghi, chính sách giữ log và kiểm soát đường vận chuyển vẫn là các cơ chế bảo mật riêng. Đặc biệt, log kiểm toán không nên chỉ dựa vào tên package để đảm bảo tính toàn vẹn.

### 7.8. Tạo vô hạn logger theo dữ liệu động làm tăng chi phí

`Logger.getLogger("orders." + orderId)` tạo nhiều tên logger; ngoài khả năng làm khó cấu hình, còn gây tiêu thụ bộ nhớ/metadata ở backend và mất khả năng phân nhóm ổn định. Dùng `logger name` theo lớp hoặc package, đưa `orderId` vào ngữ cảnh sự kiện sau khi đánh giá vấn đề dữ liệu nhạy cảm.

## 8. Các lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Đã bật `FINE` cho package nhưng không thấy log | Logger con đặt mức cao hơn, handler giới hạn `INFO`, hoặc mã không phát `FINE` | Xem mức hiệu lực của logger nguồn, mức/filter của handler, cấu hình runtime đang tải. |
| Một log xuất hiện hai lần ở console | Handler tại cả logger con và cha, vẫn bật lan truyền | Xem `useParentHandlers` hoặc `additivity`, nơi appender/handler được gắn. |
| Bật chi tiết cho package A nhưng B cũng xuất rất nhiều log | Quy tắc đặt ở root, hoặc cả A và B dùng cùng tên logger chung | In logger name, kiểm tra đúng package và mức từng nhánh. |
| Log của lớp mới không theo cấu hình cũ | Tên package/class đã đổi hoặc logger dùng tên tự đặt | So sánh `getLogger(...)` trong code với tên ghi trong cấu hình. |
| Chỉ còn WARN trong file dù console có INFO | Đích file có mức/filter cao hơn | Kiểm tra từng handler/appender, không chỉ mức logger. |
| Log INFO của con vẫn tới handler cha có mức thấp | Logger con đã chấp nhận bản ghi, handler cha cho phép | Phân biệt mức logger cha với ngưỡng handler. |
| Bản ghi của package bị mất sau đổi cấu hình | Vô tình tắt lan truyền hoặc bỏ appender cần thiết | Kiểm thử đường đi của các mẫu log trước và sau triển khai. |

Một phép kiểm thử hữu ích là chuẩn bị ma trận **package × mức log × kênh đầu ra**. Tạo một vài bản ghi mẫu ở `FINE`, `INFO` và `WARNING` từ từng package; xác nhận chính xác dòng nào đi đến console, file hoặc collector. Đồng thời bảo đảm không còn nội dung nhạy cảm, và không có log bị ghi trùng ngoài chủ đích.

## 9. Bài tập vận dụng

Một ứng dụng dùng JUL và có các logger:

```text
app                 level = INFO, handler console level = ALL
app.catalog         level = null
app.catalog.cache   level = FINE
app.checkout        level = WARNING
```

Các logger con có `useParentHandlers=true`, còn `app` có `useParentHandlers=false`. Không có handler riêng tại logger con. Hãy xác định những dòng sau có đến console của `app` không:

| Nguồn | Mức log | Message |
| --- | --- | --- |
| `app.catalog` | `INFO` | `catalog.loaded` |
| `app.catalog` | `FINE` | `catalog.debug` |
| `app.catalog.cache` | `FINE` | `cache.miss` |
| `app.checkout` | `INFO` | `checkout.started` |
| `app.checkout` | `SEVERE` | `checkout.failed` |

**Đáp án:**

- `app.catalog / INFO`: **có**, vì kế thừa mức INFO từ `app` và handler nhận mọi mức.
- `app.catalog / FINE`: **không**, vì logger nguồn hiệu lực INFO nên không tạo bản ghi FINE.
- `app.catalog.cache / FINE`: **có**, vì logger con đặt mức FINE; handler cha cho ALL. Mức INFO của logger `app` không lọc lại bản ghi.
- `app.checkout / INFO`: **không**, vì logger checkout đặt WARNING.
- `app.checkout / SEVERE`: **có**, vì vượt ngưỡng WARNING và handler cho phép.

Nếu handler của `app` đổi thành `WARNING`, các dòng `INFO` và `FINE` kể trên sẽ không được in dù một số logger vẫn chấp nhận tạo chúng. Điều này cho thấy **cấu hình theo package chủ yếu điều khiển nguồn**, còn handler/appender và quy tắc lan truyền quyết định đầu ra cuối cùng.

Để tự kiểm tra, hãy trả lời bằng lời của mình: Vì sao chọn logger theo tên lớp vẫn cấu hình được theo package? Khi đổi tên package, những cấu hình nào cần xem lại? Và khi log “mất”, làm thế nào xác định nó bị chặn ở logger nguồn hay ở handler nơi nhận?