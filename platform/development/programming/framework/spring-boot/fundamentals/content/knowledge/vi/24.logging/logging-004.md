# TRACE, DEBUG, INFO, WARN, ERROR và chọn mức ghi log

Trong Spring Boot, log không chỉ là những dòng chữ xuất hiện trên terminal. Nó là nguồn thông tin quan trọng để hiểu **ứng dụng đang làm gì, điều gì đã xảy ra, vì sao có lỗi và mức độ ảnh hưởng ra sao**. Khi service có hàng nghìn request mỗi phút, đặt sai mức log có thể làm mất tín hiệu quan trọng trong “biển” thông báo, tăng chi phí lưu trữ, làm chậm hệ thống hoặc khiến đội vận hành nhầm một sự kiện bình thường thành sự cố nghiêm trọng.

Ngược lại, dùng log quá ít có thể khiến một lỗi chỉ xuất hiện ở production rất khó điều tra.

Spring Boot thường dùng **SLF4J** làm API ghi log trong code Java và, với các starter thông dụng, dùng **Logback** làm hệ thống thực thi phía sau. Năm mức mà lập trình viên gặp thường xuyên là:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Thứ tự này diễn tả **mức độ nghiêm trọng/ưu tiên của thông điệp**, không phải thời điểm xảy ra hoặc tốc độ của ứng dụng.

Bài học thuộc **Spring Boot Fundamentals → Logging**, tập trung vào cách hiểu từng mức log, cơ chế lọc theo ngưỡng, cách cấu hình theo package/class và cách chọn mức hợp lý dựa trên **mức độ bất thường, tác động và khả năng phục hồi**.

## 1. Log là gì và một bản ghi log nên trả lời điều gì?

Một bản ghi log là một sự kiện có thể đọc và truy vấn được, do ứng dụng hoặc hạ tầng sinh ra.

Ví dụ:

~~~text
2026-11-13 09:20:11.306  INFO  14322 --- [http-nio-8080-exec-2]
c.e.orders.OrderService : Created order orderId=ORD-1052 items=3

2026-11-13 09:20:13.481  WARN  14322 --- [http-nio-8080-exec-4]
c.e.payment.PaymentClient : Payment gateway timed out; retry=1

2026-11-13 09:20:18.005 ERROR  14322 --- [http-nio-8080-exec-4]
c.e.payment.PaymentClient : Payment failed after retries; orderId=ORD-1052
~~~

Log thường chứa:

- **Timestamp**: sự kiện xảy ra khi nào.
- **Level**: độ ưu tiên/quan trọng của thông điệp.
- **Logger name**: class hoặc nhóm phát thông điệp.
- **Thread**: luồng thực hiện, có ích khi điều tra concurrency.
- **Message**: sự kiện và bối cảnh liên quan.
- **Exception**: stack trace nếu có và được truyền đúng cho logger.
- **Correlation ID / trace ID** nếu hệ thống có cấu hình quan sát liên request.

Một log tốt giúp người đọc xác định **việc gì xảy ra, đối tượng nào liên quan, kết quả là gì và cần hành động hay không**, mà không buộc phải đọc mã nguồn ngay lập tức.

Tuy nhiên, một log không nhất thiết chứa tất cả các thông tin trên. Cấu trúc thực tế phụ thuộc cấu hình logging và mục đích sử dụng; ví dụ, console log trong môi trường phát triển có thể ngắn hơn log đưa vào hệ thống tập trung.

## 2. Năm mức log: thứ tự và ý nghĩa

| Mức | Mục đích chính | Người thường cần đọc |
|---|---|---|
| **TRACE** | Chi tiết cực nhỏ của luồng thực thi, bước trung gian và giá trị phục vụ điều tra sâu | Lập trình viên đang debug trường hợp cụ thể |
| **DEBUG** | Thông tin kỹ thuật cần khi phân tích hành vi, lựa chọn nhánh, tham số an toàn, trạng thái xử lý | Lập trình viên, người điều tra lỗi |
| **INFO** | Sự kiện hoạt động bình thường nhưng đáng biết ở mức vận hành | Lập trình viên, vận hành, quan sát hệ thống |
| **WARN** | Điều kiện bất thường hoặc rủi ro; ứng dụng vẫn có thể tiếp tục, nhưng đáng theo dõi | Vận hành và người phụ trách hệ thống |
| **ERROR** | Thao tác quan trọng thất bại, chức năng không hoàn thành hoặc có lỗi cần xử lý | Vận hành, người xử lý incident |

Đây là định hướng, không phải một bộ quy tắc cứng áp đặt cho mọi ứng dụng. Mức phù hợp phụ thuộc hợp đồng nghiệp vụ, tần suất sự kiện và khả năng phục hồi.

Ví dụ, cùng một lỗi mạng:

- Một request nền đầu tiên thất bại nhưng retry thành công có thể là **DEBUG** hoặc **WARN**, tùy mức độ hữu ích khi quan sát.
- Một API phải dùng fallback nhưng vẫn trả kết quả hợp lệ có thể là **WARN**.
- Một giao dịch thanh toán đã thất bại sau mọi phương án phục hồi có thể là **ERROR**.

**Mức log nên mô tả tác động cuối cùng lên hệ thống, không chỉ tên class exception.**

### 2.1. TRACE — mức chi tiết nhất

Dùng TRACE khi cần theo dõi các bước rất nhỏ mà bình thường không nên xuất hiện trong log:

~~~java
log.trace(
        "Matching rule id={} against candidate index={}",
        ruleId,
        candidateIndex
);
~~~

Những thông tin phù hợp:

- Các bước lặp trong một thuật toán.
- Trạng thái trung gian được chọn lọc.
- Số lần so khớp, vị trí con trỏ, nhánh xét điều kiện.
- Diễn tiến xử lý cần điều tra ở mức rất sâu.

Không nên ghi toàn bộ body request, dữ liệu người dùng, token hoặc cấu trúc chứa secret chỉ vì đang ở TRACE. **TRACE không được miễn các quy tắc bảo mật dữ liệu**.

TRACE thường tạo nhiều log hơn DEBUG và nên chỉ bật cho logger cần thiết trong một khoảng thời gian giới hạn.

### 2.2. DEBUG — thông tin để tìm hiểu quyết định của code

DEBUG tập trung vào **vì sao code chọn một hướng xử lý**:

~~~java
log.debug(
        "Selected pricing strategy={} for orderId={}",
        strategyName,
        orderId
);
~~~

Ví dụ khác:

~~~java
log.debug(
        "Cache lookup key={} hit={}",
        safeCacheKey,
        cacheHit
);
~~~

DEBUG phù hợp cho:

- Lựa chọn strategy/implementation.
- Một điều kiện nhánh quan trọng.
- Kết quả tra cứu cache hoặc metadata không nhạy cảm.
- Bối cảnh bổ sung trước khi gọi dịch vụ ngoài.
- Giá trị cấu hình đã được làm sạch khi cần điều tra.

Không nên ghi một dòng DEBUG cho từng bước nhỏ trong vòng lặp lớn nếu không thực sự có giá trị; đó có thể là TRACE hoặc nên chuyển thành metric tổng hợp.

### 2.3. INFO — sự kiện vận hành bình thường có ý nghĩa

INFO là mức thường được dùng làm ngưỡng mặc định của root logger trong ứng dụng Spring Boot điển hình.

Một log INFO tốt mô tả mốc có ý nghĩa:

~~~java
log.info(
        "Imported file fileId={} records={} durationMs={}",
        fileId,
        recordCount,
        durationMs
);
~~~

Có thể dùng INFO cho:

- Ứng dụng bắt đầu, hoàn tất bước startup hoặc shutdown.
- Một batch quan trọng hoàn thành.
- Một phiên xử lý dữ liệu được bắt đầu/hoàn tất.
- Một trạng thái nghiệp vụ quan trọng được chuyển đổi.
- Một thay đổi cấu hình vận hành không nhạy cảm được áp dụng.

Không nhất thiết mọi request hoặc mọi method call đều là INFO. Với ứng dụng có throughput lớn, ghi một dòng INFO cho từng lời gọi nhỏ có thể rất tốn kém. Những dữ liệu định lượng tổng hợp nên cân nhắc metrics.

### 2.4. WARN — bất thường nhưng vẫn còn đường xử lý

WARN biểu thị một điều kiện **đáng chú ý** nhưng chưa nhất thiết khiến thao tác thất bại hoàn toàn.

~~~java
log.warn(
        "Primary inventory provider unavailable; using cached data ageSeconds={}",
        cacheAgeSeconds
);
~~~

Ví dụ:

- Gọi nguồn chính thất bại nhưng fallback hợp lệ.
- Cấu hình sử dụng một tùy chọn sắp bị bỏ hỗ trợ.
- Queue gần đầy hoặc nguồn tài nguyên gần đạt ngưỡng.
- Retry xảy ra bất thường nhiều lần.
- Dữ liệu có thể xử lý được nhưng có sự sai khác cần theo dõi.

WARN không đồng nghĩa “có một exception bất kỳ”. Một trường hợp dữ liệu người dùng nhập sai nhưng được API xử lý đúng với HTTP 400 có thể là sự kiện bình thường, không cần WARN.

### 2.5. ERROR — chức năng đã thất bại hoặc sự cố có tác động

ERROR dùng khi thao tác quan trọng không thể hoàn tất hoặc hệ thống đang ở tình trạng lỗi cần được xử lý:

~~~java
log.error(
        "Failed to finalize invoice invoiceId={}",
        invoiceId,
        exception
);
~~~

Ví dụ:

- Giao dịch thất bại sau retry và không còn fallback.
- Lỗi không mong đợi làm request trả HTTP 500.
- Một công việc bắt buộc thất bại không thể phục hồi.
- Mất tính nhất quán dữ liệu hoặc tài nguyên thiết yếu không khả dụng.

Một thông điệp ERROR **không nhất thiết làm ứng dụng dừng**. Nó chỉ là mức log. Ngược lại, nếu không có ERROR được ghi thì cũng không chứng minh ứng dụng không bị lỗi.

## 3. Cơ chế lọc theo ngưỡng log

Một điều thường gây nhầm lẫn: cấu hình `INFO` không có nghĩa ứng dụng **chỉ ghi INFO**. Nó có nghĩa logger chấp nhận **INFO và những mức có độ ưu tiên cao hơn**.

Với năm mức SLF4J cơ bản:

~~~text
TRACE   DEBUG   INFO   WARN   ERROR
 1       2       3      4      5
                 ^
                 |
        Ngưỡng cấu hình: INFO
~~~

Khi ngưỡng là `INFO`, thông điệp `TRACE` và `DEBUG` thường không xuất hiện, còn `INFO`, `WARN` và `ERROR` được phép đi tiếp trong pipeline logging.

| Ngưỡng cấu hình | TRACE | DEBUG | INFO | WARN | ERROR |
|---|---|---|---|---|---|
| TRACE | Có | Có | Có | Có | Có |
| DEBUG | Không | Có | Có | Có | Có |
| INFO | Không | Không | Có | Có | Có |
| WARN | Không | Không | Không | Có | Có |
| ERROR | Không | Không | Không | Không | Có |

Bảng thể hiện **lọc theo mức tối thiểu** trong cấu hình thông thường. Backend logging có thể còn có filter, appender và điều kiện tùy chỉnh khiến một số bản ghi vẫn không được xuất ra dù vượt ngưỡng.

### Ví dụ ngưỡng INFO

Code:

~~~java
log.trace("Step 1");
log.debug("Step 2");
log.info("Step 3");
log.warn("Step 4");
log.error("Step 5");
~~~

Nếu logger có effective level là INFO và không có filter đặc biệt, kết quả thấy được:

~~~text
INFO  Step 3
WARN  Step 4
ERROR Step 5
~~~

Nếu đổi mức hiệu lực thành `DEBUG`:

~~~text
DEBUG Step 2
INFO  Step 3
WARN  Step 4
ERROR Step 5
~~~

Nếu đổi thành `ERROR`, chỉ còn dòng ERROR.

### “Mức ghi log” không phải dữ liệu được ghi ở mọi mức

Một số người sửa mọi lời gọi `log.debug(...)` thành `log.info(...)` chỉ để thấy chúng xuất hiện trong production. Điều đó làm mất sự phân loại. Cách đúng thường là:

1. Giữ nguyên mức log có ý nghĩa.
2. Tạm thời điều chỉnh cấu hình logger cụ thể.
3. Điều tra vấn đề.
4. Trả mức logger về cấu hình vận hành phù hợp.

Như vậy code không bị “ô nhiễm” bởi các log tạm thời không đúng ý nghĩa.

## 4. SLF4J, logger và backend trong Spring Boot

Trong code, thường import:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Tạo logger theo class:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

`Logger` ở đây là API của SLF4J. Ứng dụng gọi các phương thức:

~~~java
log.trace("...");
log.debug("...");
log.info("...");
log.warn("...");
log.error("...");
~~~

Phần backend như Logback quyết định cách áp dụng mức lọc, định dạng, ghi console/file, chuyển log tới appenders hoặc hệ thống thu thập.

Trong các dự án dùng những starter Spring Boot thông thường, dependency `spring-boot-starter-logging` thường đã có mặt và cung cấp Logback. Dự án cũng có thể được cấu hình để dùng backend khác, chẳng hạn Log4j2. Những nguyên tắc về năm mức SLF4J cơ bản vẫn áp dụng, nhưng cú pháp cấu hình nâng cao của backend có thể khác.

### Vì sao không nên viết System.out.println cho log nghiệp vụ?

~~~java
System.out.println("Order processed: " + orderId);
~~~

Cách này có thể xuất hiện trên console nhưng thiếu nhiều khả năng quản lý:

- Không có mức log tiêu chuẩn.
- Khó tắt riêng cho một package.
- Không tự kết hợp với pattern hoặc structured logging của backend.
- Khó thống nhất định dạng và chuyển tiếp log.
- Việc kiểm soát thông tin nhạy cảm khó nhất quán.

Nên dùng:

~~~java
log.info("Order processed orderId={}", orderId);
~~~

Điều này không có nghĩa `System.out` luôn bị cấm; nó vẫn hữu ích cho CLI output chủ động phục vụ người dùng. Nhưng với log vận hành của service, nên dùng API logging.

## 5. Ví dụ Spring Boot nhỏ có đủ năm mức log

Ví dụ sau có thể dùng trong một ứng dụng Spring Boot với SLF4J và logging backend đã được cấu hình. Ta tạo một runner sinh các sự kiện demo.

~~~java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoggingDemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingDemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(LoggingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demoLoggingLevels() {
        return args -> {
            log.trace("TRACE: inspecting a tiny internal step");
            log.debug("DEBUG: selected mode={}", "SAMPLE");
            log.info("INFO: demo startup task completed");
            log.warn("WARN: using a fallback configuration");

            try {
                Integer.parseInt("not-a-number");
            } catch (NumberFormatException exception) {
                log.error("ERROR: demo data cannot be parsed", exception);
            }
        };
    }
}
~~~

Một số điểm cần chú ý:

- Dòng TRACE và DEBUG có thể không hiển thị nếu mức hiệu lực là INFO.
- Dòng WARN ở đây mô phỏng một fallback; trong ứng dụng thật chỉ ghi khi fallback thực sự xảy ra.
- Dòng ERROR chỉ nhằm tạo tình huống học tập, không phải đề xuất ghi một ERROR cố định ở mỗi lần startup.
- Truyền `exception` cho logger giúp backend ghi stack trace, không chỉ message.

Nếu ứng dụng là API HTTP, không bắt buộc dùng runner; ví dụ dùng runner để người học quan sát ngay khi khởi động mà không phải tạo request.

### Chạy với mức mặc định

Trong một dự án Boot điển hình, mức root mặc định thường là INFO. Do đó ta nhìn thấy INFO, WARN và ERROR của runner.

### Bật DEBUG riêng cho package demo

Trong `application.properties`:

~~~properties
logging.level.com.example.logging=DEBUG
~~~

Khởi động lại ứng dụng sẽ thấy thêm DEBUG của các logger trong package này, trong khi TRACE vẫn thường bị lọc.

### Bật TRACE riêng cho package demo

~~~properties
logging.level.com.example.logging=TRACE
~~~

Lúc này cả năm mức của logger trong package được phép đi qua ngưỡng.

**Không cần bật `logging.level.root=TRACE` trên toàn ứng dụng** chỉ để quan sát một class học tập. Bật root TRACE thường sinh rất nhiều thông điệp từ framework và thư viện.

## 6. Cấu hình logging.level trong application.properties

Spring Boot cho phép đặt mức log theo root, package hoặc logger name:

~~~properties
# Mức chung
logging.level.root=INFO

# Chỉ xem chi tiết từ mã của ứng dụng
logging.level.com.example.orders=DEBUG

# Giảm log ít quan trọng của một thư viện
logging.level.org.springframework.web=WARN

# Theo dõi chi tiết một logger cụ thể
logging.level.com.example.orders.OrderService=TRACE
~~~

Trong file thực tế, những dòng bắt đầu bằng `#` là comment của định dạng properties.

### Mức root

~~~properties
logging.level.root=INFO
~~~

Root logger là ngưỡng mặc định cho những logger không có thiết lập hiệu lực cụ thể hơn.

Ví dụ, khi root ở INFO, các logger không có override thường chỉ phát các bản ghi INFO trở lên.

### Mức theo package

~~~properties
logging.level.com.example.orders=DEBUG
~~~

Cấu hình này áp dụng cho logger trong namespace `com.example.orders` theo hệ phân cấp tên logger của backend. Vì logger được tạo từ class thường có tên đầy đủ của class, cấu hình package là cách điều chỉnh nhiều class liên quan cùng lúc.

Ví dụ:

~~~text
com.example.orders.OrderService        -> DEBUG
com.example.orders.OrderController     -> DEBUG
com.example.orders.internal.Validator  -> DEBUG
~~~

Các package khác như `com.example.payment` không bị thay đổi trực tiếp chỉ bởi rule `com.example.orders`.

### Mức theo class/logger cụ thể

~~~properties
logging.level.com.example.orders.OrderService=TRACE
~~~

Đây là tên logger đầy đủ nếu code dùng:

~~~java
LoggerFactory.getLogger(OrderService.class)
~~~

Nếu class cụ thể có mức TRACE, còn package cha là DEBUG, mức cấu hình cụ thể hơn thường thắng cho logger đó.

**Cấu hình logging theo class dựa vào tên logger, không dựa vào Spring bean name.** Một class có nhiều bean vẫn thường dùng cùng một logger nếu đều khai báo theo class ấy.

## 7. Cấu hình tương đương trong application.yml

Với YAML:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
    com.example.orders.OrderService: TRACE
~~~

Có thể đọc cấu trúc này như một map tên logger → mức log.

Khi config được đọc vào Spring `Environment`, những property tương ứng là:

~~~text
logging.level.root = INFO
logging.level.com.example.orders = DEBUG
logging.level.org.springframework.web = WARN
logging.level.com.example.orders.OrderService = TRACE
~~~

Lưu ý: case của logger name đầy đủ như `OrderService` có thể quan trọng. Không nên đổi tùy tiện tên class trong cấu hình thành chữ thường rồi giả định backend sẽ tự nhận dạng được.

### Có thể dùng tên log group

Nếu nhiều package liên quan cần điều chỉnh cùng nhau, Spring Boot hỗ trợ nhóm logger:

~~~properties
logging.group.billing=com.example.billing,com.example.payments
logging.level.billing=DEBUG
~~~

Điều này cho phép nhóm `billing` cùng thay đổi mức các logger được liệt kê mà không phải gõ từng package mỗi lần.

Các logger group mặc định và khả năng cấu hình chi tiết có thể khác tùy phiên bản Boot; với nhóm do ứng dụng tự định nghĩa như ví dụ, nên đặt tên có ý nghĩa và giới hạn đúng phần cần quan sát.

## 8. Cấu hình bằng command line và biến môi trường

Trong môi trường triển khai, không phải lúc nào cũng nên sửa `application.properties` rồi build lại JAR để tăng mức log.

### Command-line argument

Ví dụ:

~~~bash
java -jar app.jar --logging.level.com.example.orders=DEBUG
~~~

Hoặc:

~~~bash
java -jar app.jar --logging.level.root=WARN
~~~

Với một ứng dụng Spring Boot thông thường, tham số dòng lệnh có thể ghi đè giá trị tương ứng trong file application config. Điều này thuận tiện khi chạy lại một instance để điều tra.

### Biến môi trường

Với package viết hoàn toàn chữ thường, có thể dùng:

~~~bash
export LOGGING_LEVEL_ROOT=INFO
export LOGGING_LEVEL_COM_EXAMPLE_ORDERS=DEBUG
java -jar app.jar
~~~

Trên PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "INFO"
$env:LOGGING_LEVEL_COM_EXAMPLE_ORDERS = "DEBUG"
java -jar app.jar
~~~

**Lưu ý quan trọng với logger theo class:** khi dùng system environment variables, tên logger trong `logging.level` có thể bị chuyển về chữ thường bởi cơ chế binding map. Điều này thường không gây vấn đề cho package viết chữ thường, nhưng có thể không cấu hình đúng logger của một class cụ thể có chữ hoa như `OrderService`.

Khi cần mức log cho logger/class có phân biệt chữ hoa thường, ưu tiên `application.properties`, `application.yml`, command-line property hoặc `SPRING_APPLICATION_JSON` thay vì tự suy diễn một tên env.

Ví dụ trên Linux shell:

~~~bash
export SPRING_APPLICATION_JSON='{"logging":{"level":{"com.example.orders.OrderService":"TRACE"}}}'
java -jar app.jar
~~~

Các cách này giúp giữ nguyên tên logger cụ thể trong cấu hình.

### Cấu hình bên ngoài không đồng nghĩa thay đổi ngay lập tức

Nếu chỉnh một biến môi trường của shell **sau khi process Java đã chạy**, process thường không tự nhận giá trị mới. Không nên suy ra rằng thay đổi file hoặc environment luôn cập nhật effective level ngay lập tức.

Để thay đổi mức log trong một process đang chạy, cần cơ chế runtime được hỗ trợ riêng, chẳng hạn Actuator loggers endpoint, JMX hoặc khả năng cấu hình của backend.

## 9. Hiểu effective level và tính kế thừa

Trong nhiều backend logging, logger được tổ chức theo tên phân cấp. Một logger không có mức cấu hình riêng thường kế thừa mức hiệu lực từ một logger cha gần nhất, cuối cùng là root.

Giả sử:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.com.example.payment=WARN
~~~

Có thể hiểu kết quả:

| Logger name | Effective level trong ví dụ |
|---|---|
| `org.springframework.boot.StartupInfoLogger` | INFO, nếu không có override khác |
| `com.example.catalog.CatalogService` | DEBUG |
| `com.example.payment.PaymentService` | WARN |
| `com.example.payment.gateway.GatewayClient` | WARN |

Nếu viết:

~~~java
log.debug("Attempting payment");
~~~

trong `PaymentService`, thông điệp này thường bị lọc ở ngưỡng WARN, mặc dù logger cha `com.example` có ngưỡng DEBUG.

### Phân biệt ngưỡng logger và appender

Việc log có xuất hiện hay không không chỉ phụ thuộc ngưỡng. Ví dụ backend có thể có:

- Console appender chỉ ghi từ INFO trở lên.
- File appender chỉ ghi WARN/ERROR.
- Filter loại bỏ một tập message.
- Sampling hoặc forwarding policy trong hệ thống thu thập.

Vì vậy, khi một message “biến mất”, cần kiểm tra cả **effective logger level** và nơi nhận log, không chỉ property `logging.level.*`.

## 10. Cách chọn mức: hỏi về tác động trước

Một phương pháp thực dụng là trả lời lần lượt:

1. **Đây có phải lỗi làm thao tác không hoàn thành không?** Nếu có và không còn đường xử lý, thường là ERROR tại boundary phù hợp.
2. **Có bất thường ảnh hưởng độ tin cậy hoặc phải dùng fallback không?** Thường cân nhắc WARN.
3. **Đây có phải mốc hoạt động bình thường đáng quan sát không?** Nếu có, cân nhắc INFO.
4. **Đây là dữ liệu để lập trình viên hiểu một quyết định của code?** Dùng DEBUG.
5. **Đây là chi tiết rất nhỏ của quá trình xử lý?** Dùng TRACE.

Có thể hình dung:

~~~text
Sự kiện cần ghi
      |
      v
Thao tác quan trọng thất bại, không phục hồi được?
      | Có
      +------------------------------> ERROR
      |
      | Không
      v
Có bất thường, fallback hoặc rủi ro cần theo dõi?
      | Có
      +------------------------------> WARN
      |
      | Không
      v
Là mốc hoạt động bình thường đáng quan sát?
      | Có
      +------------------------------> INFO
      |
      | Không
      v
Giúp hiểu quyết định hoặc trạng thái xử lý?
      | Có
      +------------------------------> DEBUG
      |
      | Không
      v
Là chi tiết cực nhỏ khi cần điều tra sâu?
      | Có
      +------------------------------> TRACE
      |
      v
Không ghi log; dùng metric, trace hoặc bỏ sự kiện
~~~

Không bắt buộc mọi dòng code đều phải phát log. **Không ghi log** cũng là một lựa chọn đúng khi sự kiện không cung cấp thông tin mới hoặc đã được quan sát tốt bằng cơ chế khác.

### Ma trận các tình huống thường gặp

| Tình huống | Mức thường cân nhắc | Lý do |
|---|---|---|
| Ứng dụng đã khởi động và sẵn sàng | INFO | Mốc vận hành đáng biết |
| Một job định kỳ hoàn thành và có số lượng bản ghi xử lý | INFO | Kết quả của một đơn vị công việc |
| Chọn strategy tính giá theo loại khách hàng | DEBUG | Chi tiết quyết định kỹ thuật |
| Cache hit/miss của từng item trong luồng truy cập lớn | DEBUG/TRACE hoặc metric | Có thể rất nhiều log |
| Duyệt qua từng bước parser | TRACE | Chi tiết rất sâu |
| Dùng cache dự phòng vì provider chính chậm | WARN | Có suy giảm chất lượng hoặc fallback |
| Cấu hình deprecated nhưng vẫn hoạt động | WARN | Cần chủ động sửa |
| HTTP 400 do người dùng nhập sai dữ liệu dự kiến | Thường không WARN/ERROR | Hành vi dự kiến của API |
| Một lần retry thường gặp, cuối cùng thành công | DEBUG hoặc WARN có chọn lọc | Tùy mức bất thường và tần suất |
| Một giao dịch thất bại không còn fallback | ERROR | Không đạt kết quả yêu cầu |
| Job bắt buộc thất bại và sẽ dừng | ERROR | Sự cố có tác động |
| Bắt exception rồi xử lý hoàn toàn hợp lệ | DEBUG/INFO hoặc không ghi | Không còn lỗi chưa được xử lý |
| Lỗi code dẫn tới HTTP 500 | ERROR tại boundary | Lỗi hệ thống cần điều tra |
| Memory pressure đang tiến sát ngưỡng cảnh báo | WARN | Rủi ro đáng theo dõi |
| Lưu một dòng dữ liệu thông thường trong vòng lặp lớn | Không ghi hoặc TRACE | Giảm noise và chi phí |

Bảng là hướng dẫn. Một hoạt động có lưu lượng rất thấp và yêu cầu audit đặc biệt có thể cần thông tin khác so với một API có hàng triệu request. Hãy thống nhất chính sách log theo từng domain của hệ thống.

## 11. INFO không phải “ghi mọi việc bình thường”

Một anti-pattern hay gặp:

~~~java
log.info("Enter createOrder");
log.info("Validating order");
log.info("Calling repository");
log.info("Repository returned");
log.info("Mapping DTO");
log.info("Leaving createOrder");
~~~

Với nhiều request, các dòng này nhanh chóng che mất sự kiện có giá trị. Nếu cần theo dõi luồng method để điều tra một lỗi, chúng phù hợp hơn ở DEBUG/TRACE, hoặc có thể dùng distributed tracing.

Thay vào đó, log một kết quả có ý nghĩa:

~~~java
log.info(
        "Order created orderId={} itemCount={} durationMs={}",
        orderId,
        itemCount,
        durationMs
);
~~~

Nếu ứng dụng có throughput rất lớn, ngay cả log INFO per-request cũng có thể quá nhiều. Có thể chọn log theo mốc batch, sample hoặc sử dụng metrics tổng hợp tùy yêu cầu vận hành.

### Các ví dụ INFO phù hợp

- `"Catalog refresh completed items=2500 durationMs=1830"`
- `"Kafka consumer assigned partitions count=8"`
- `"Daily reconciliation finished matched=1200 mismatched=4"`
- `"Configuration reload completed version=7"`

Không ghi giá trị nhạy cảm hoặc object tùy ý chỉ để làm log “đầy đủ”.

## 12. WARN khác ERROR ở khả năng phục hồi

Hai đoạn code gần giống có thể phải dùng mức log khác nhau.

### Tình huống A: có fallback hợp lệ

~~~java
try {
    price = priceProvider.fetchLatestPrice(productId);
} catch (PriceProviderTimeoutException exception) {
    price = cachedPriceProvider.getValidPrice(productId);

    log.warn(
            "Price provider timed out; using valid cached price productId={}",
            productId
    );
}
~~~

Các class trên chỉ minh họa. Giả định fallback cung cấp dữ liệu còn hợp lệ theo chính sách nghiệp vụ.

Người dùng vẫn nhận kết quả hợp lệ, vì vậy WARN phù hợp để báo hệ thống hoạt động suy giảm. Không nhất thiết ghi stack trace đầy đủ cho mọi lỗi retry/fallback lặp lại hàng nghìn lần; có thể bổ sung metrics và log chi tiết chọn lọc.

### Tình huống B: không có fallback và request thất bại

~~~java
try {
    price = priceProvider.fetchLatestPrice(productId);
} catch (PriceProviderTimeoutException exception) {
    log.error(
            "Price lookup failed; no fallback productId=" + productId,
            exception
    );
    throw exception;
}
~~~

Ở đây operation không thể hoàn thành; ERROR có lý do hơn. Tuy nhiên, ví dụ cũng cho thấy một nguy cơ: nếu tầng controller advice **lại ghi ERROR cho cùng exception**, hệ thống có thể có hai hoặc nhiều stack trace giống nhau.

Một thiết kế production nên chọn **điểm chịu trách nhiệm ghi ERROR** rõ ràng, thường tại ranh giới xử lý request/job; tầng thấp hơn có thể giữ bối cảnh trong exception hoặc DEBUG thay vì ghi trùng.

### Quyết định dựa trên kết quả cuối

Với hệ thống có retry:

~~~text
Thử lần 1 thất bại
       |
       v
Retry lần 2 thành công ---> kết quả cuối thành công

=> Có thể ghi DEBUG về retry;
   nếu tỷ lệ retry bất thường, dùng WARN/metric.
~~~

Ngược lại:

~~~text
Thử lần 1 thất bại
       |
       v
Retry lần 2 thất bại
       |
       v
Retry lần 3 thất bại
       |
       v
Không có fallback ---> ERROR tại boundary
~~~

Không nên log ERROR cho mỗi lần thử nếu mỗi lỗi chỉ là một trạng thái trung gian đã có retry xử lý. Việc đó gây “bão ERROR” dù không có request nào thất bại cuối cùng.

## 13. Logging exception và stack trace

Một `Throwable` có nhiều thông tin hơn `getMessage()`:

- Loại exception.
- Message.
- Vị trí tạo và lan truyền lỗi qua stack trace.
- Chuỗi `getCause()`.
- Những exception bị suppress trong một số trường hợp.

### Sai lầm: chỉ ghi message

~~~java
catch (IOException exception) {
    log.error("Cannot import file: {}", exception.getMessage());
}
~~~

Dòng này thường làm mất stack trace và nguyên nhân lồng nhau. Message có thể ngắn hoặc trống, khiến việc điều tra khó khăn.

### Cách tốt hơn: đưa Throwable cho logger

~~~java
catch (IOException exception) {
    log.error("Cannot import file fileId=" + fileId, exception);
}
~~~

Hoặc:

~~~java
log.error(
        "Cannot import file fileId={}",
        fileId,
        exception
);
~~~

Các backend SLF4J thông thường nhận diện đối tượng `Throwable` ở cuối danh sách tham số để ghi exception. Nếu muốn cách rõ ràng, dùng overload `log.error(String, Throwable)` như ví dụ đầu.

### Không phải WARN nào cũng cần stack trace

Nếu một tình huống fallback là dự kiến và xảy ra tương đối nhiều, log WARN đầy đủ stack trace cho từng lần có thể quá tốn kém. Có thể ghi một message ngắn có mã sự kiện, retry count, thời gian xử lý, đồng thời có metric đo tần suất.

Ngược lại, với lỗi lần đầu xuất hiện hoặc lỗi khó tái tạo, stack trace là thông tin rất quan trọng.

### Tránh “log rồi throw” ở mọi tầng

Ví dụ anti-pattern:

~~~java
public Result process() {
    try {
        return repository.load();
    } catch (Exception exception) {
        log.error("Repository failed", exception);
        throw exception;
    }
}
~~~

Nếu service, controller và global exception handler đều làm tương tự, một failure có thể tạo nhiều bản ghi ERROR trùng lặp.

Nên phân trách nhiệm:

- Tầng thấp thêm bối cảnh bằng exception có ý nghĩa và giữ cause.
- Tầng quyết định fallback ghi WARN/DEBUG nếu cần.
- Tầng boundary quyết định kết quả cuối ghi ERROR một lần, nếu cần.
- Framework có thể đã ghi lỗi chưa bắt; cân nhắc tránh ghi trùng với cơ chế có sẵn.

Đừng làm mất stack trace gốc khi bọc exception:

~~~java
throw new IllegalStateException(
        "Cannot load catalog fileId=" + fileId,
        exception
);
~~~

Constructor có `cause` giữ thông tin nguyên nhân để người xử lý ở tầng trên đọc được.

## 14. Thông điệp log nên có cấu trúc và nhất quán

So sánh:

~~~java
log.error("Lỗi!");
~~~

với:

~~~java
log.error(
        "Payment reconciliation failed batchId={} processed={} rejected={}",
        batchId,
        processedCount,
        rejectedCount,
        exception
);
~~~

Thông điệp thứ hai giúp:

- Tìm kiếm theo hành động.
- Ghép với một đơn vị công việc cụ thể.
- Biết số lượng đã xử lý hoặc thất bại.
- Xem stack trace khi cần.

Dù vậy, chỉ log các trường **thật sự giúp chẩn đoán**. Nhiều trường không cần thiết làm log khó đọc và tăng chi phí lưu trữ.

### Ưu tiên key=value hoặc structured fields có quy ước

Một convention đơn giản:

~~~text
event=order_created orderId=ORD-1052 itemCount=3 durationMs=85
~~~

Khi dùng backend hỗ trợ JSON/structured logging, những trường này có thể trở thành field thực sự trong log event, giúp hệ thống phân tích thay vì phải parse chuỗi. Cách cấu hình structured logging phụ thuộc stack và phiên bản Spring Boot/backend; không nên mặc định rằng chỉ viết `key=value` sẽ tự tạo JSON fields.

Nên nhất quán các trường như `orderId`, `batchId`, `durationMs` thay vì đổi tên giữa các class thành `id`, `order_id` và `orderNumber` một cách tùy ý.

## 15. Parameterized logging để tránh ghép chuỗi không cần thiết

SLF4J hỗ trợ placeholder `{}`:

~~~java
log.debug(
        "Calculating price orderId={} itemCount={}",
        orderId,
        itemCount
);
~~~

Ưu điểm:

- Thông điệp thống nhất, dễ đọc.
- Tránh tạo string ghép vô ích trong một số trường hợp khi mức DEBUG đang bị tắt.
- Không cần gọi `String.format(...)` cho log đơn giản.

So sánh:

~~~java
// Ít nên dùng nếu DEBUG bị tắt phần lớn thời gian:
log.debug("Calculating price for " + orderId);

// Ưu tiên:
log.debug("Calculating price for {}", orderId);
~~~

**Một lưu ý quan trọng về hiệu năng:** Java vẫn đánh giá các biểu thức được truyền làm argument **trước khi gọi method**. Placeholder không tự ngăn một hàm tính toán nặng chạy.

Ví dụ:

~~~java
log.debug(
        "Full diagnostic snapshot={}",
        expensiveSnapshot()
);
~~~

`expensiveSnapshot()` vẫn chạy ngay cả khi DEBUG bị tắt.

Cách phù hợp:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Full diagnostic snapshot={}",
            expensiveSnapshot()
    );
}
~~~

Tương tự, có thể dùng `log.isTraceEnabled()` cho phép tính rất tốn kém chỉ phục vụ TRACE.

### Đừng lạm dụng kiểm tra isDebugEnabled()

Với một vài biến đã có sẵn:

~~~java
log.debug("Order id={} status={}", orderId, status);
~~~

thông thường không cần bao trong `if (log.isDebugEnabled())`. Kiểm tra riêng chỉ hữu ích khi việc tính argument, serialize object hoặc tạo dữ liệu chẩn đoán thực sự tốn kém.

## 16. Ví dụ service thực tế: chọn mức theo vòng đời một tác vụ

Giả sử ứng dụng cần nhập một file text, mỗi dòng tương ứng một record. Ta chỉ mô phỏng việc đếm dòng, không ghi từng bản ghi vào log.

~~~java
package com.example.imports;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class TextImportService {

    private static final Logger log =
            LoggerFactory.getLogger(TextImportService.class);

    public long countRecords(Path source, String importId)
            throws IOException {

        long startedAt = System.nanoTime();

        log.info("Text import started importId={}", importId);

        long count = 0;

        try (BufferedReader reader = Files.newBufferedReader(
                source, StandardCharsets.UTF_8)) {

            while (reader.readLine() != null) {
                count++;

                if (log.isTraceEnabled()) {
                    log.trace(
                            "Text import progress importId={} line={}",
                            importId,
                            count
                    );
                }
            }

            long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

            log.info(
                    "Text import completed importId={} records={} durationMs={}",
                    importId,
                    count,
                    durationMs
            );

            return count;
        } catch (IOException exception) {
            log.debug(
                    "Text import failed before completion importId={}",
                    importId,
                    exception
            );
            throw exception;
        }
    }
}
~~~

Trong ví dụ:

- **INFO** cho mốc import bắt đầu và kết thúc.
- **TRACE** cho chi tiết từng dòng, mặc định thường không hiển thị.
- **DEBUG** cho bối cảnh kỹ thuật tại tầng service khi exception sẽ được đưa lên caller.
- Caller hoặc boundary sẽ quyết định ghi WARN/ERROR dựa trên việc có thể phục hồi hay không.
- `try-with-resources` đóng `BufferedReader` sau khi đọc hoặc khi có lỗi.

Code dùng `Path` làm input cho tác vụ nhập file và không tự xác thực nguồn. Trong ứng dụng thật, cần kiểm tra quyền truy cập, kích thước và định dạng file trước khi đọc, nhất là khi path có nguồn gốc từ request.

### Nếu không cần TRACE từng dòng thì sao?

Trong file rất lớn, ngay cả code kiểm tra TRACE bên trong vòng lặp có thể là chi tiết không cần thiết. Có thể thay bằng metric hoặc log tiến độ theo batch:

~~~java
if (count % 10_000 == 0) {
    log.debug(
            "Text import progress importId={} records={}",
            importId,
            count
    );
}
~~~

Mức INFO hay DEBUG cho tiến độ phụ thuộc thời lượng job và nhu cầu vận hành. Nếu job xử lý hàng triệu dòng, ghi tiến độ mỗi 10.000 dòng vẫn có thể nhiều; cần chọn tần suất hợp lý.

## 17. Tránh dùng ERROR cho mọi HTTP 4xx

Trong REST API, một tình huống phổ biến là request không thỏa validation:

~~~text
POST /orders
HTTP 400 Bad Request
{"message":"quantity must be positive"}
~~~

Nếu client gửi input sai như một phần của hoạt động bình thường, không nhất thiết ghi:

~~~java
log.error("Invalid quantity", exception);
~~~

Với lưu lượng lớn, điều đó tạo nhiều ERROR không phản ánh lỗi máy chủ.

Có thể:

- Trả 400 với thông báo an toàn cho người dùng.
- Ghi DEBUG nếu cần chi tiết giúp điều tra.
- Đo tỷ lệ 4xx bằng HTTP metrics.
- Dùng logging/audit chuyên biệt nếu cần phát hiện hành vi lạm dụng.

Ngược lại, một HTTP 500 do lỗi code hoặc dependency không thể phục hồi thường là tín hiệu cần ghi ERROR ở ranh giới xử lý request, nếu framework hoặc hệ thống giám sát chưa ghi đủ thông tin.

### Không đồng nhất HTTP status và log level một cách máy móc

Một số ví dụ:

| HTTP status | Có bắt buộc log ERROR? | Nhận xét |
|---|---|---|
| 200 OK | Không | Có thể chỉ cần metrics |
| 400 Bad Request | Không | Input không hợp lệ có thể dự kiến |
| 401 Unauthorized | Không | Tùy audit/security policy |
| 404 Not Found | Không | Thường là kết quả hợp lệ |
| 429 Too Many Requests | Không | Thường theo dõi bằng metrics, có thể WARN khi ngưỡng bất thường |
| 500 Internal Server Error | Thường cân nhắc | Lỗi server cần điều tra |
| 503 Service Unavailable | Tùy nguyên nhân | Có thể do maintenance, readiness hoặc dependency outage |

Chọn mức dựa trên tác động và chính sách vận hành, không chỉ trên con số HTTP.

## 18. Trong production nên bật mức nào?

Không có một cấu hình đúng cho mọi hệ thống. Một lựa chọn ban đầu dễ vận hành thường là:

~~~properties
logging.level.root=INFO
logging.level.com.example=INFO
~~~

Khi cần điều tra một module:

~~~properties
logging.level.com.example.payments=DEBUG
~~~

Nếu một thư viện sinh quá nhiều dòng không cần thiết:

~~~properties
logging.level.org.springframework.web=WARN
~~~

Tuy nhiên, **không hạ mức cả một package chỉ để che đi vấn đề đang xảy ra**. Trước khi giảm log, cần biết thông điệp nào đang bị bỏ qua và nó có giá trị cảnh báo hay không.

### Cấu hình theo môi trường

Có thể dùng các file profile:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

Ví dụ `application-dev.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
~~~

Ví dụ `application-prod.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example: INFO
~~~

Khi profile tương ứng được kích hoạt, cấu hình theo profile được đưa vào hệ thống externalized configuration. Mức thực tế còn phụ thuộc nguồn cấu hình ưu tiên cao hơn như biến môi trường và command-line args.

### Đừng bật root TRACE trong production dài hạn

Bật TRACE toàn bộ hệ thống có thể:

- Sinh log cực lớn từ HTTP stack, ORM, database và thư viện.
- Làm tăng CPU, I/O và chi phí thu thập.
- Gây khó khăn cho tìm kiếm vì noise.
- Làm lộ metadata hay dữ liệu nhạy cảm khi thư viện ghi chi tiết.
- Gây áp lực cho collector hoặc hệ thống lưu trữ.

Nếu cần TRACE, nên chọn logger hẹp, giới hạn thời gian, giám sát lượng log và có kế hoạch tắt lại.

## 19. Thay đổi mức log lúc runtime

Khi production đang có sự cố, restart toàn bộ ứng dụng chỉ để bật DEBUG có thể không lý tưởng.

Nếu dự án có Spring Boot Actuator và cơ chế truy cập được cấu hình phù hợp, **loggers endpoint** có thể cho phép kiểm tra hoặc thay mức logger trong process đang chạy.

Ví dụ endpoint:

~~~text
GET /actuator/loggers
GET /actuator/loggers/com.example.payments
~~~

Trong cấu hình cho phép expose qua HTTP:

~~~properties
management.endpoints.web.exposure.include=health,info,loggers
~~~

Việc có thể truy cập và thay mức còn phụ thuộc phiên bản Spring Boot, thiết lập endpoint access và chính sách Spring Security của ứng dụng. Không nên xem một dòng `exposure.include` là đủ để bảo đảm mọi thao tác thay đổi log đều được phép.

Nếu write operation được cho phép và endpoint được bảo vệ phù hợp, một yêu cầu điều chỉnh thường có hình thức:

~~~http
POST /actuator/loggers/com.example.payments
Content-Type: application/json

{"configuredLevel":"DEBUG"}
~~~

Để trả logger về trạng thái không có mức cấu hình tường minh:

~~~http
POST /actuator/loggers/com.example.payments
Content-Type: application/json

{"configuredLevel":null}
~~~

Giá trị `null` ở đây có nghĩa bỏ mức đặt riêng cho logger, để nó kế thừa theo cấu hình hiệu lực phù hợp. Nó không nhất thiết đồng nghĩa “trở lại INFO” nếu package cha đang ở mức khác.

**Cảnh báo bảo mật:** endpoint thay đổi logger là khả năng quản trị có thể tăng lượng log đáng kể và làm lộ thông tin qua cấu hình log chi tiết. Không expose endpoint này công khai nếu không có xác thực, phân quyền và kiểm soát vận hành.

Đừng quên rằng thay đổi runtime có thể không được lưu bền vững qua restart, và các instance trong cùng một cluster có thể cần được cập nhật riêng hoặc thông qua cơ chế quản lý cấu hình tập trung.

## 20. Log volume, hiệu năng và chi phí

Chọn mức log không chỉ là chuyện nội dung. Nó còn ảnh hưởng đến lượng dữ liệu:

~~~text
10.000 request/phút
       x
5 dòng INFO/request
       =
50.000 dòng INFO/phút

Nếu mỗi dòng trung bình 500 byte:
50.000 x 500 = 25.000.000 byte/phút
~~~

Con số chỉ là ví dụ minh họa và chưa tính metadata bổ sung, index, replication, compression hoặc overhead của collector.

Bật DEBUG cho một thư viện nhiều hoạt động có thể tăng lượng log lớn hơn nhiều so với dự đoán.

Các cách kiểm soát:

1. Ghi **mốc có giá trị**, tránh log mỗi thao tác nhỏ ở INFO.
2. Dùng DEBUG/TRACE cho những chi tiết cần điều tra và thường để tắt.
3. Dùng metric cho số đếm, tỷ lệ, latency và phần trăm lỗi.
4. Dùng distributed trace để theo dõi luồng xuyên service.
5. Áp dụng sampling/aggregation phù hợp nếu công cụ thu thập hỗ trợ.
6. Giữ chính sách retention và phân quyền theo yêu cầu vận hành.
7. Không dùng log để thay thế dữ liệu nghiệp vụ bắt buộc phải được lưu có tính nhất quán.

### Log không thay thế metric

Nếu câu hỏi là “tỷ lệ request lỗi 5xx trong 5 phút qua là bao nhiêu?”, metric thường hiệu quả hơn việc quét hàng triệu log.

Nếu câu hỏi là “vì sao request có orderId cụ thể thất bại?”, log kèm correlation ID và stack trace có thể hữu ích hơn.

Nếu câu hỏi là “request đã đi qua những service nào, mất bao lâu ở từng bước?”, distributed tracing phù hợp hơn.

Ba công cụ có thể bổ sung nhau, không nên cố đẩy tất cả bài toán quan sát vào một mức log.

## 21. Log phải an toàn với dữ liệu nhạy cảm

Một lỗi nghiêm trọng là ghi toàn bộ request hoặc object:

~~~java
log.debug("Login request={}", loginRequest);
~~~

Nếu `loginRequest.toString()` chứa password hoặc token, giá trị đó có thể lọt vào log. Bật DEBUG để điều tra sẽ vô tình làm lộ dữ liệu nhạy cảm.

Không nên ghi:

- Password, refresh token, access token, API key.
- Cookie phiên hoặc header `Authorization`.
- Số thẻ thanh toán, mã bí mật hoặc private key.
- Thông tin cá nhân vượt quá mức cần thiết.
- Toàn bộ payload khi chứa dữ liệu nhạy cảm.
- Connection string có username/password.

Thay vì log cả request:

~~~java
log.debug(
        "Authentication attempt method={} clientId={}",
        authMethod,
        safeClientId
);
~~~

Một số trường định danh vẫn có thể là dữ liệu cá nhân hoặc nhạy cảm tùy bối cảnh, vì vậy cần áp dụng chính sách tối thiểu hóa, masking hoặc pseudonymization của hệ thống.

### TRACE không có quyền truy cập đặc biệt

Bật TRACE không làm thay đổi chính sách dữ liệu. Không nên đặt secret vào TRACE rồi cho rằng vì production thường tắt TRACE nên an toàn. Mức log có thể được bật lại khi điều tra, và log có thể được gửi tới nhiều hệ thống lưu trữ.

### Exception message cũng có thể lộ secret

Một thư viện có thể đưa URL có query parameter nhạy cảm hoặc nội dung phản hồi vào message của exception. Khi gửi exception sang hệ thống quan sát, cần xác định vùng tin cậy và cơ chế bảo vệ dữ liệu. Không ghi nguyên văn thông tin mà người dùng không được phép xem.

## 22. Correlation ID, trace ID và bối cảnh của log

Trong hệ thống nhiều request chạy đồng thời, chỉ biết timestamp và class name thường chưa đủ.

Ví dụ:

~~~text
INFO  Order validation started
INFO  Order validation started
ERROR Payment failed
INFO  Order validation completed
~~~

Nếu không có request ID, khó phân biệt dòng nào thuộc request nào.

Có thể thêm một correlation ID vào logging context bằng **MDC**:

~~~java
import org.slf4j.MDC;

String correlationId = "req-7fd91";

try {
    MDC.put("correlationId", correlationId);

    log.info("Validating order orderId={}", orderId);
    // Xử lý trong cùng thread.
} finally {
    MDC.remove("correlationId");
}
~~~

Trong Logback, console pattern có thể được cấu hình để in giá trị này, ví dụ:

~~~properties
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] [%X{correlationId}] %logger{36} - %msg%n
~~~

Khi đó log có thêm correlation ID nếu MDC key tồn tại trong thread.

**Lưu ý:** MDC theo thread không tự được truyền nguyên vẹn qua mọi lời gọi `@Async`, thread pool hoặc reactive pipeline. Khi xử lý bất đồng bộ, cần cơ chế truyền bối cảnh phù hợp. Đối với hệ thống đã dùng Micrometer Tracing hoặc OpenTelemetry, nên tận dụng trace/span context do stack quan sát cung cấp thay vì tự tạo nhiều cơ chế ID không đồng nhất.

Mức INFO/DEBUG/WARN/ERROR vẫn giữ nguyên ý nghĩa; correlation ID chỉ giúp nối các bản ghi thành luồng xử lý.

## 23. Logging trong tác vụ nền và startup

Không phải mọi log xuất hiện ở giai đoạn startup đều có cùng mức.

Ví dụ:

~~~java
@Component
public class CatalogWarmup implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogWarmup.class);

    @Override
    public void run(ApplicationArguments args) {
        log.info("Catalog warmup started");

        int imported = loadRequiredData();

        log.info("Catalog warmup completed records={}", imported);
    }

    private int loadRequiredData() {
        return 100;
    }
}
~~~

Đoạn minh họa dùng các type `ApplicationRunner` và `ApplicationArguments` của Spring Boot cùng `@Component` của Spring, giả định import tương ứng đã có.

Mốc bắt đầu và hoàn tất một bước khởi động bắt buộc thường phù hợp với INFO. Nếu nạp một file cấu hình tùy chọn không thành công nhưng có fallback hợp lệ, WARN có thể phù hợp. Nếu không thể khởi động vì dữ liệu bắt buộc không tồn tại, có thể ném exception để Boot xử lý startup failure và ghi lỗi ở boundary của startup.

**Không cần đặt ERROR mỗi khi bắt được exception rồi ngay lập tức ném lên tầng khác** nếu Spring Boot đã có cơ chế ghi failure đầy đủ. Dữ liệu quan trọng là thông điệp nguyên nhân rõ ràng và stack trace không bị mất.

Đối với scheduler hoặc batch, nên chọn mức dựa trên kết quả **một lần chạy**:

~~~text
Job started          -> INFO hoặc DEBUG
Job completed        -> INFO
Một phần tử bỏ qua    -> DEBUG, WARN nếu bất thường đáng chú ý
Một lần retry         -> DEBUG hoặc WARN
Job thất bại hoàn toàn -> ERROR tại boundary
~~~

Thêm `jobId`, số lượng đã xử lý và thời lượng để có bối cảnh điều tra.

## 24. Quy ước log cho nhiều nhóm trong một dự án

Một dự án có controller, service, repository và integration adapter có thể dùng chính sách nhất quán:

| Thành phần | Nội dung log thường hữu ích | Mức gợi ý |
|---|---|---|
| Controller/API boundary | Kết quả xử lý, lỗi không mong muốn | INFO có chọn lọc, ERROR tại boundary |
| Business service | Mốc nghiệp vụ, kết quả job, trạng thái quan trọng | INFO |
| Business service | Lựa chọn nhánh, bối cảnh kỹ thuật | DEBUG |
| Repository/data access | Query hoặc thao tác kỹ thuật khi điều tra | DEBUG/TRACE có kiểm soát |
| External adapter | Fallback, timeout bất thường | WARN |
| External adapter | Thất bại không phục hồi sau mọi phương án | ERROR tại boundary thích hợp |
| Scheduler/runner | Mốc bắt đầu/kết thúc, số lượng xử lý | INFO |
| Parser/algorithm | Bước xử lý rất nhỏ | TRACE |
| Security/audit pipeline | Sự kiện bảo mật theo chính sách riêng | Không quyết định chỉ bằng bảng này |

Một cách giúp thống nhất là quy định **chủ thể chịu trách nhiệm log lỗi cuối cùng**. Ví dụ, controller advice ghi ERROR cho HTTP 500 không mong muốn; các tầng thấp hơn thêm bối cảnh và giữ exception chain, thay vì tất cả đều ghi lỗi.

### Audit log khác application log thông thường

Các sự kiện như thay đổi quyền, giao dịch tài chính hoặc truy cập dữ liệu nhạy cảm có thể cần audit trail riêng với chính sách toàn vẹn, retention và truy cập nghiêm ngặt. Chúng không nên chỉ dựa trên việc root logger đang ở INFO hay WARN.

Một bản ghi audit có thể cần được lưu dù cấu hình logging kỹ thuật thay đổi. **Đừng dùng mức log như cơ chế duy nhất bảo đảm lưu sự kiện bắt buộc theo quy định.**

## 25. Các anti-pattern khi chọn mức log

### Anti-pattern 1: “Exception nào cũng ERROR”

Không đúng. Exception có thể chỉ là tín hiệu fallback hợp lệ, validation thất bại dự kiến hoặc một bước retry.

Hãy hỏi: **điều gì cuối cùng xảy ra với operation?**

### Anti-pattern 2: “Thấy lỗi production thì bật root TRACE mãi”

Không nên. Điều này tạo lượng log lớn và rủi ro lộ dữ liệu. Nên bật một logger cụ thể trong thời gian giới hạn, điều tra rồi tắt.

### Anti-pattern 3: “INFO cho mọi method call”

Không tốt cho hệ thống nhiều request. Chi tiết method thường thuộc DEBUG/TRACE, còn INFO dành cho mốc có ý nghĩa.

### Anti-pattern 4: “Chỉ ghi exception.getMessage()”

Có thể mất stack trace và cause. Khi cần điều tra lỗi thật, truyền `Throwable` cho logger theo cách đúng.

### Anti-pattern 5: “Ghép chuỗi và serialize object vô điều kiện”

Dù DEBUG/TRACE bị tắt, code vẫn có thể tính toán đối số tốn kém trước lời gọi. Dùng placeholder và guard nếu cần.

### Anti-pattern 6: “Log object nguyên vẹn để dễ debug”

Có thể ghi dữ liệu nhạy cảm, object rất lớn hoặc nội dung không ổn định do `toString()`. Chỉ ghi các field an toàn cần thiết.

### Anti-pattern 7: “Đã log ở repository thì service và controller cũng log ERROR”

Dẫn đến trùng lặp, khó xác định lỗi nào độc lập. Phân trách nhiệm ghi lỗi theo boundary.

### Anti-pattern 8: “DEBUG được bật thì code phải thay đổi hành vi”

Không nên. Cấu hình log chỉ phục vụ quan sát; không được làm thay đổi tính đúng đắn nghiệp vụ. Cẩn trọng với mã chỉ thực hiện một side effect trong nhánh `if (log.isDebugEnabled())`.

### Anti-pattern 9: “Không có ERROR nghĩa là hệ thống khỏe mạnh”

Có thể code chưa ghi log đúng, collector bị lỗi hoặc ứng dụng đang không nhận traffic. Cần phối hợp health checks, metrics, tracing và alerting.

### Anti-pattern 10: “ERROR được ghi thì phải restart server”

Không. ERROR là mức ưu tiên của thông điệp, không phải một lệnh điều khiển lifecycle. Quyết định restart phụ thuộc health state và chính sách vận hành.

## 26. Bài tập thực hành

### Bài tập 1: Quan sát ngưỡng lọc

Tạo code:

~~~java
log.trace("trace-message");
log.debug("debug-message");
log.info("info-message");
log.warn("warn-message");
log.error("error-message");
~~~

Lần lượt cấu hình logger của class ở mức TRACE, DEBUG, INFO, WARN và ERROR. Ghi lại những message xuất hiện.

Kết quả mong đợi theo ngưỡng đơn giản:

| Effective level | Các message xuất hiện |
|---|---|
| TRACE | TRACE, DEBUG, INFO, WARN, ERROR |
| DEBUG | DEBUG, INFO, WARN, ERROR |
| INFO | INFO, WARN, ERROR |
| WARN | WARN, ERROR |
| ERROR | ERROR |

### Bài tập 2: Giới hạn DEBUG vào một package

Giả sử ứng dụng có:

~~~text
com.example.catalog.CatalogService
com.example.payment.PaymentService
com.example.payment.GatewayClient
~~~

Yêu cầu: giữ INFO chung, nhưng xem DEBUG trong module payment.

Gợi ý:

~~~properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
~~~

Sau đó quan sát log của CatalogService so với PaymentService. Không cần đổi tất cả lời gọi thành INFO.

### Bài tập 3: Chọn mức theo tác động

Hãy chọn TRACE/DEBUG/INFO/WARN/ERROR hoặc không ghi cho từng trường hợp:

1. Một job nạp dữ liệu hoàn thành 20.000 bản ghi.
2. Một payment attempt thất bại nhưng retry đã thành công.
3. Một parser duyệt qua 500.000 ký tự.
4. Một request dữ liệu sai trả HTTP 400 đúng hợp đồng.
5. Không tạo được invoice và không có fallback.
6. Một dịch vụ ngoài chậm, ứng dụng dùng cache vẫn còn hiệu lực.
7. Một service chọn implementation `RuleA` cho một loại input.

Gợi ý:

- (1) INFO cho kết quả job.
- (2) DEBUG; cân nhắc WARN nếu việc retry là bất thường cần theo dõi.
- (3) TRACE chọn lọc hoặc không ghi; tránh log mỗi ký tự trong production.
- (4) Thường không ERROR; metrics hoặc DEBUG có chọn lọc.
- (5) ERROR tại boundary.
- (6) WARN cho suy giảm có fallback.
- (7) DEBUG cho quyết định kỹ thuật.

### Bài tập 4: Sửa code ghi exception

Đoạn chưa tối ưu:

~~~java
catch (IOException exception) {
    log.error("Read failed: " + exception.getMessage());
    throw new RuntimeException("Read failed");
}
~~~

Hãy sửa để bảo toàn cause và không ghi trùng ERROR ở nhiều tầng:

~~~java
catch (IOException exception) {
    throw new IllegalStateException(
            "Unable to read input fileId=" + fileId,
            exception
    );
}
~~~

Sau đó chọn một điểm boundary thích hợp để ghi:

~~~java
log.error("Import request failed", exception);
~~~

Điều quan trọng là không mất exception chain và tránh sinh nhiều bản ghi giống nhau.

### Bài tập 5: Tối ưu DEBUG nặng

Đoạn này có vấn đề gì?

~~~java
log.debug("Snapshot={}", objectMapper.writeValueAsString(hugeObject));
~~~

Dù logger có tắt DEBUG, phép serialize vẫn có thể chạy và tốn tài nguyên. Có thể dùng:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Snapshot={}",
            objectMapper.writeValueAsString(safeDiagnosticObject)
    );
}
~~~

Trong đó `safeDiagnosticObject` phải là dữ liệu đã được giảm dung lượng và loại bỏ các field nhạy cảm. Không biến tính năng DEBUG thành đường xuất dữ liệu riêng vượt chính sách bảo mật.

### Bài tập 6: Cấu hình theo class trong environment

Muốn bật TRACE riêng cho:

~~~text
com.example.orders.OrderService
~~~

Hãy giải thích tại sao tên biến môi trường với toàn chữ hoa và underscore có thể không giữ đúng case của class logger, rồi chọn một cách cấu hình đáng tin cậy hơn, chẳng hạn:

~~~properties
logging.level.com.example.orders.OrderService=TRACE
~~~

Hoặc:

~~~bash
java -jar app.jar --logging.level.com.example.orders.OrderService=TRACE
~~~

Nếu dùng Actuator loggers endpoint, cần kiểm tra effective level và quyền truy cập của endpoint.

## 27. Checklist thiết kế chính sách logging cho dự án

Trước khi thống nhất logging guideline, đội phát triển nên làm rõ:

1. **Mốc vận hành nào xứng đáng INFO?** Ví dụ startup ready, batch completed, cấu hình reload.
2. **Tín hiệu bất thường nào cần WARN?** Ví dụ fallback, retry cao, tài nguyên gần cạn.
3. **Lỗi nào phải ERROR?** Ví dụ request/job thất bại cuối cùng không có đường phục hồi.
4. **Ai chịu trách nhiệm log exception cuối cùng?** Tránh lặp stack trace ở mọi tầng.
5. **Có cần TRACE/DEBUG cho module nào?** Mặc định tắt, bật khi điều tra.
6. **Những dữ liệu nào tuyệt đối không được ghi?** Định nghĩa danh sách nhạy cảm và chính sách masking.
7. **Các field dùng để liên kết log là gì?** Ví dụ requestId, traceId, orderId an toàn.
8. **Mức log có thể thay đổi như thế nào?** File/profile, command line, môi trường, Actuator có bảo vệ.
9. **Sản lượng log và retention được kiểm soát ra sao?** Dùng metric cho đại lượng lặp lại.
10. **Đã phối hợp với metrics, tracing và audit chưa?** Không coi log là công cụ duy nhất.

Một cấu hình điểm bắt đầu có thể là:

~~~properties
# Ứng dụng thông thường
logging.level.root=INFO

# Module cần điều tra tạm thời
logging.level.com.example.orders=DEBUG

# Tùy chọn: giảm các thông tin framework không cần thiết
logging.level.org.springframework.web=WARN
~~~

Nên điều chỉnh theo số liệu và nhu cầu thực tế, không sao chép nguyên xi mọi dòng cho tất cả service.

## Kết luận

Năm mức log cơ bản trong Spring Boot/SLF4J có thứ tự:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

- **TRACE**: chi tiết rất sâu của luồng thực thi.
- **DEBUG**: thông tin kỹ thuật để tìm nguyên nhân và hiểu các quyết định của code.
- **INFO**: các mốc vận hành bình thường có ý nghĩa.
- **WARN**: tình huống bất thường, suy giảm hoặc rủi ro nhưng vẫn có thể xử lý.
- **ERROR**: thao tác quan trọng thất bại hoặc sự cố không phục hồi ở ranh giới phù hợp.

Cấu hình một logger ở mức `INFO` thường vẫn cho phép `WARN` và `ERROR`, nhưng lọc `DEBUG` và `TRACE`. Spring Boot cho phép điều chỉnh bằng `logging.level.root`, `logging.level.<package>` hoặc tên logger cụ thể, trong file cấu hình, command line và một số nguồn externalized configuration khác.

Quan trọng nhất, **chọn mức log dựa trên ý nghĩa và tác động của sự kiện**, không chỉ dựa vào việc code có exception hay không. Ghi đủ bối cảnh nhưng không lặp lỗi, dùng parameterized logging hợp lý, bảo vệ dữ liệu nhạy cảm và kết hợp logs với metrics/tracing để ứng dụng vừa dễ vận hành vừa có chi phí quan sát chấp nhận được.
