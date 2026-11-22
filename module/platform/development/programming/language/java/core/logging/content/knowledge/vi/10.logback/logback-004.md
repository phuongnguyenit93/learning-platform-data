# Encoder của Logback: chuyển sự kiện log thành dữ liệu đầu ra

## 1. Encoder trong Logback là gì?

Trong ứng dụng Java dùng **SLF4J + Logback**, mã nghiệp vụ thường gọi `logger.info(...)`, `logger.warn(...)` hoặc `logger.error(...)`. Một lời gọi như vậy không tự tạo ra dòng text hoàn chỉnh trong file. Logback cần quyết định sự kiện được ghi ở đâu và **biểu diễn sự kiện đó bằng những byte nào**.

**Encoder** là thành phần biến một sự kiện logging thành **dữ liệu byte có thể ghi ra đầu ra** (console, file hoặc output stream phù hợp). Với Logback Classic, dữ liệu đầu vào thường là `ILoggingEvent`: đối tượng chứa level, tên logger, thông điệp, thời gian, thread, MDC, Throwable và những thông tin khác.

Ví dụ ứng dụng phát:

```java
log.info("event=order.created order_id={}", "O-17");
```

Khi ứng dụng dùng `PatternLayoutEncoder` với pattern `%level|%logger{0}|%msg%n`, một dòng output có thể là:

```text
INFO|OrderService|event=order.created order_id=O-17
```

Ở đây:

- `%level` lấy mức log.
- `%logger{0}` lấy phần tên logger ngắn nhất theo quy tắc pattern.
- `%msg` lấy message đã được định dạng, bao gồm giá trị thay cho `{}`.
- `%n` thêm ký tự xuống dòng phù hợp hệ điều hành.

**Encoder không quyết định logger có được ghi hay không.** Level, filter và quan hệ logger cha–con tham gia quyết định sự kiện nào đi tới appender. Encoder xử lý **cách biểu diễn** của sự kiện đã được chấp nhận.

## 2. Encoder nằm ở đâu trong đường đi của log?

Một đường đi điển hình:

```text
Mã Java
  |
  | SLF4J: logger.info("order={}", orderId)
  v
Logger / mức log / filter
  |
  v
ILoggingEvent
  |
  v
Appender (ConsoleAppender, FileAppender, RollingFileAppender...)
  |
  +---- Encoder (PatternLayoutEncoder / encoder JSON tương thích)
  |           |
  |           v
  |       Các byte đã định dạng
  |
  v
Console / file / output stream
  |
  v
Collector hoặc hệ thống phân tích (nếu có)
```

Phân biệt các vai trò:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Logger` | Nhận lời gọi ghi log và xác định nguồn, mức hiệu lực | `com.example.order.OrderService` |
| `ILoggingEvent` | Mang thông tin của một lần ghi log | Level, message, arguments, Throwable, MDC |
| `Filter` | Chấp nhận hoặc từ chối sự kiện theo quy tắc | Chỉ chuyển `WARN` trở lên |
| `Appender` | Quản lý **đích ghi** và cơ chế xuất | `ConsoleAppender`, `FileAppender` |
| `Encoder` | Chuyển sự kiện thành **byte đầu ra** | `PatternLayoutEncoder` |
| `Layout` | Tạo biểu diễn văn bản từ sự kiện, thường được encoder sử dụng | `PatternLayout` |
| Collector | Thu thập, parse, lưu, định tuyến ở tầng ngoài JVM | Tác nhân đọc stdout của container |

Đặc biệt, **appender không phải encoder**. Đổi `ConsoleAppender` thành `FileAppender` thay đổi đích, nhưng cùng một encoder và pattern vẫn có thể tạo cùng một định dạng. Đổi encoder thay đổi định dạng mà không nhất thiết đổi đích.

Một appender có thể cung cấp cách encode hoặc cơ chế xuất riêng; bảng trên mô tả luồng phổ biến của các appender dựa trên output stream. Không phải mọi loại appender đều bắt buộc cấu hình cùng một kiểu encoder.

## 3. Encoder khác Layout ở điểm nào?

Trong Logback, `Layout` tập trung vào việc tạo một **chuỗi** từ sự kiện; `Encoder` biến sự kiện thành **byte** thích hợp để ghi ra stream. Với Logback Classic, `PatternLayout` sử dụng pattern để tạo văn bản, còn `PatternLayoutEncoder` là cách phổ biến để dùng pattern đó trong một `ConsoleAppender` hoặc `FileAppender`.

Có thể hình dung:

```text
ILoggingEvent
    |
    v
PatternLayout: "INFO|OrderService|order=O-17\n"  (String)
    |
    v
PatternLayoutEncoder: encode theo UTF-8            (byte[])
    |
    v
Appender: ghi các byte vào stdout/file
```

`PatternLayoutEncoder` là lựa chọn chuẩn để định dạng văn bản thông qua các conversion word của Logback. Trong phần lớn bài toán logging console/file, bạn không cần tự xây dựng một `Layout` rồi bọc bằng `LayoutWrappingEncoder`. Khi phải tích hợp một layout tùy biến, lớp `LayoutWrappingEncoder` có thể dùng để nối một layout với luồng byte, nhưng cần hiểu chu kỳ khởi tạo và kiểu sự kiện.

### Tại sao không tự nối chuỗi ở mã nghiệp vụ?

Ví dụ không nên rải việc định dạng đầu ra ở các service:

```java
log.info("[" + Thread.currentThread().getName()
        + "] [" + System.currentTimeMillis()
        + "] order=" + orderId);
```

Đây là **đoạn minh họa**, giả sử `log` và `orderId` đã được khai báo. Cách đó khiến định dạng bị lặp, có thể tốn chi phí khi level bị tắt, khó đổi thành JSON và khó thống nhất timestamp/thread. Tốt hơn:

```java
log.info("event=order.created order_id={}", orderId);
```

Để encoder thêm mức, thời gian, tên logger và thread theo cấu hình. Mã nghiệp vụ nên tập trung vào **ý nghĩa sự kiện và các trường ngữ cảnh**, còn encoder quyết định **cách thể hiện**.

## 4. PatternLayoutEncoder và các conversion word quan trọng

Ví dụ cấu hình:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Giải thích những thành phần thường dùng:

| Conversion word | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `%d{HH:mm:ss.SSS}` | Thời gian của sự kiện theo pattern đã chọn | Thiếu ngày/múi giờ nếu chỉ dùng giờ trong ngày. |
| `%level` hoặc `%p` | Mức ghi log | `INFO`, `WARN`, `ERROR`... |
| `%-5level` | Căn trái tên mức trong độ rộng tối thiểu 5 ký tự | Giúp dòng text dễ nhìn. |
| `%thread` | Tên luồng | Có thể thay đổi giữa request hoặc lần chạy. |
| `%logger` | Tên logger | Có thể là tên lớp đầy đủ. |
| `%logger{36}` | Rút ngắn tên logger theo độ dài mục tiêu | Không phải ID duy nhất để phân biệt class. |
| `%logger{0}` | Biểu diễn ngắn, thường là phần cuối của logger name | Hữu ích để đọc nhanh; có thể mất thông tin package. |
| `%msg` hoặc `%message` | Message đã thay tham số | Không đồng nghĩa với JSON có trường riêng. |
| `%ex` | Thông tin ngoại lệ/stack trace khi sự kiện có Throwable | Cần kiểm tra output thực tế và bảo mật. |
| `%X{trace_id}` | Giá trị `trace_id` từ MDC khi có | Phải truyền MDC đúng ngữ cảnh. |
| `%n` | Xuống dòng theo môi trường | Thiếu `%n` có thể khiến các bản ghi dính liền. |
| `%kvp` | Cặp key-value gắn vào logging event trong phiên bản hỗ trợ | Cần cấu hình backend/phiên bản tương thích. |

**Pattern được phân tích bởi Logback**, không phải `String.format` hay `java.text.MessageFormat`. Dấu `{}` mà ứng dụng dùng để truyền đối số thuộc cơ chế **parameter substitution của SLF4J**; token `%msg` là điểm encoder lấy **thông điệp đã được format** từ sự kiện.

Ví dụ:

```java
log.warn("event=payment.retry attempt={}", 2);
```

Cùng một sự kiện này có thể được hiển thị khác nhau:

```text
WARN|event=payment.retry attempt=2
14:22:03.112 WARN [main] com.example.PaymentService - event=payment.retry attempt=2
```

Hai dòng trên chỉ là **minh họa của hai pattern khác nhau**, không phải kết quả chính xác của một lần chạy; timestamp và thread thực tế do runtime cung cấp. Nội dung nghiệp vụ giống nhau nhưng cách biểu diễn do encoder quyết định.

### Biểu diễn thời gian phải phù hợp mục tiêu

Pattern thời gian ngắn như `HH:mm:ss.SSS` tiện cho terminal, nhưng thiếu ngày và múi giờ khi tìm kiếm giữa nhiều hệ thống. Production nên dùng timestamp đầy đủ, có offset/múi giờ rõ ràng, hoặc để hệ thống thu thập ghi một trường thời gian chuẩn. Phải phân biệt **thời gian sự kiện xảy ra** và **thời gian collector nhận được**.

### `%logger{0}` và `%logger{36}` khác nhau

`%logger{0}` thường dùng để lấy phần tên cuối của logger; còn `%logger{36}` cố gắng rút ngắn biểu diễn tên đầy đủ về một độ dài mục tiêu theo quy tắc của PatternLayout. Hai chuyển đổi này không thể xem là cách định danh nguồn tuyệt đối. Khi phân tích log tập trung, nên giữ logger name đầy đủ trong dữ liệu có cấu trúc nếu cần truy nguồn chính xác.

## 5. Ví dụ Java 17 + Maven chạy được

Ví dụ dùng `SLF4J 2.x` với `Logback Classic 1.5.x`. Ta cấu hình một `ConsoleAppender` có `PatternLayoutEncoder`, chạy ba lời gọi logging và đối chiếu output có thể dự đoán.

Cấu trúc dự án:

```text
logback-encoder-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── edu/
        │       └── example/
        │           └── logging/
        │               └── EncoderDemo.java
        └── resources/
            └── logback.xml
```

### Bước 1: tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.example</groupId>
    <artifactId>logback-encoder-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` mang theo các phụ thuộc liên quan như `logback-core` và SLF4J API tương thích; không cần tạo thêm một cơ chế logging khác cho bài mẫu. Trong dự án lớn, cần quản lý phiên bản SLF4J và Logback cùng nhau để tránh xung đột provider/binding. Các phiên bản trong `pom.xml` chỉ là **một bộ phiên bản minh họa xác định**, không phải tuyên bố về phiên bản mới nhất.

### Bước 2: tạo `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Ý nghĩa:

1. `ConsoleAppender` ghi dữ liệu ra console (mặc định là stdout trong cấu hình này).
2. `PatternLayoutEncoder` quyết định mỗi sự kiện trở thành dòng byte theo pattern.
3. `%level|%logger{0}|%msg%n` cho đầu ra dễ đọc, không có timestamp để ví dụ ổn định.
4. `charset=UTF-8` bảo đảm cách mã hóa nhất quán cho ký tự tiếng Việt khi cần.
5. `root level="INFO"` cho phép các sự kiện `INFO`, `WARN`, `ERROR` đi qua.
6. Chỉ gắn một appender vào root và không gắn thêm cùng appender vào logger con nên không tạo trùng lặp từ cấu hình này.

### Bước 3: tạo `EncoderDemo.java`

```java
package edu.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class EncoderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(EncoderDemo.class);

    private EncoderDemo() {
    }

    public static void main(String[] args) {
        LOG.info("event=order.created order_id={}", "O-17");

        LOG.warn("event=payment.retry order_id={} attempt={}",
                "O-17", 2);

        LOG.info("event=checkout.completed outcome={}", "success");
    }
}
```

### Bước 4: biên dịch và chạy

Từ thư mục `logback-encoder-demo`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.example.logging.EncoderDemo
```

**Ba dòng log do ứng dụng phát, theo đúng pattern đã cấu hình:**

```text
INFO|EncoderDemo|event=order.created order_id=O-17
WARN|EncoderDemo|event=payment.retry order_id=O-17 attempt=2
INFO|EncoderDemo|event=checkout.completed outcome=success
```

Maven hoặc môi trường chạy có thể bổ sung dòng thông tin riêng; ba dòng trên là phần output ứng dụng mong đợi khi chỉ có cấu hình `logback.xml` này được nạp.

### Vì sao kết quả xuất hiện như vậy?

- `LoggerFactory.getLogger(EncoderDemo.class)` dùng tên logger `edu.example.logging.EncoderDemo`.
- `%logger{0}` chỉ hiển thị phần tên ngắn là `EncoderDemo`.
- `%msg` hiển thị message sau khi `"{}"` đã được thay bằng các đối số `"O-17"`, `2` và `"success"` tương ứng.
- `%level` in tên mức `INFO` hoặc `WARN`.
- `%n` ngăn các bản ghi nối vào cùng một dòng.
- Việc không xuất timestamp là **chủ ý của ví dụ học tập** để cho output cố định, không phải cấu hình khuyến nghị cho production.

Nếu sửa `<pattern>` thành `%level|%msg%n`, phần `EncoderDemo` sẽ biến mất khỏi đầu ra **mà không cần sửa mã Java**. Đây là lợi ích trọng tâm của encoder: **tách định dạng hiển thị khỏi mã nghiệp vụ**.

## 6. Charset, byte và xuống dòng: các lỗi nhỏ nhưng dễ gây sự cố

### 6.1. Tại sao cần chỉ rõ UTF-8?

Đầu vào của encoder là các giá trị chuỗi và thuộc tính sự kiện. Đầu ra cuối cùng được ghi ở dạng **byte**, nên bộ mã ký tự ảnh hưởng cách lưu chữ tiếng Việt, ký tự Unicode và ký tự đặc biệt.

Ví dụ message:

```text
Đã tạo đơn hàng
```

Nếu encoder dùng UTF-8 nhưng công cụ đọc file lại giải mã theo một bảng mã khác, người xem có thể thấy ký tự lỗi dù `logger.info(...)` được gọi đúng. Tốt nhất, các thành phần **encoder → file/stream → collector → giao diện tìm kiếm** thống nhất UTF-8.

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Thẻ `<charset>` nằm trong encoder, không phải thuộc tính nghiệp vụ của message. Khi xử lý JSON, encoder tương ứng cũng phải bảo đảm mã hóa và escape đúng.

### 6.2. Vì sao cần `%n`?

Nếu pattern là `%level|%msg` mà không có ký tự kết thúc dòng, các sự kiện liên tiếp có thể dính nhau:

```text
INFO|order.createdWARN|payment.retry
```

`%n` thêm dấu xuống dòng theo môi trường. Trong hệ thống tập trung, ranh giới từng bản ghi rất quan trọng để parser không gộp nhiều sự kiện hay tách sai một sự kiện.

Một số encoder hoặc giao thức có framing riêng, ví dụ mỗi JSON object trong một dòng hay từng message của mạng. Vì vậy, **không tùy tiện chèn `%n` vào mọi encoder nhị phân**, nhưng với `PatternLayoutEncoder` xuất text theo dòng, đây là lựa chọn thông dụng.

### 6.3. Message có xuống dòng thì sao?

Ngay cả khi pattern chỉ có một `%n` ở cuối, message hoặc stack trace có thể chứa **ký tự xuống dòng bên trong**. Một sự kiện có thể tạo nhiều dòng text. Nếu collector giả định “một dòng vật lý = một sự kiện”, cần cấu hình multiline hoặc dùng dạng có cấu trúc/escaping thích hợp.

Đừng tin rằng `%n` tự động đảm bảo mỗi sự kiện luôn gói trong đúng một dòng. Với log dạng JSON Lines, encoder cần escape các ký tự xuống dòng trong giá trị string để giữ mỗi JSON object trên một dòng hoàn chỉnh.

## 7. Encoder và Throwable/stack trace

Một lời gọi log có exception:

```java
try {
    paymentGateway.charge(orderId);
} catch (GatewayException failure) {
    log.error("event=payment.failed order_id={}", orderId, failure);
    throw failure;
}
```

Đoạn này là **minh họa** trong một lớp ứng dụng có `paymentGateway`, `GatewayException`, `log` và `orderId`. Nó không biên dịch độc lập nếu thiếu các lớp và biến tương ứng.

Logback có thể nhận thông tin ngoại lệ qua `ThrowableProxy` trong `ILoggingEvent`. Encoder text có thể xuất stack trace bằng conversion word như `%ex`, trong khi encoder có cấu trúc có thể lưu exception thành trường riêng. Chỉ so sánh `%msg` với Throwable là chưa đủ: message thường chỉ là thông tin tóm tắt, còn lỗi gốc cần loại exception, stack trace và chuỗi cause.

Ví dụ pattern thể hiện rõ trường và exception:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex</pattern>
    <charset>UTF-8</charset>
</encoder>
```

**Không nên chỉ dựa vào việc thêm `%ex` để kết luận mọi hệ thống đã có stack trace đầy đủ.** Hãy kiểm tra formatter đang hoạt động, cấu hình có giới hạn/truncate exception, việc thu thập multiline, quyền truy cập và khả năng exception message chứa bí mật.

Trong Logback Classic, pattern processing có thể **tự thêm trình chuyển đổi exception** trong một số trường hợp khi pattern chưa khai báo converter xử lý Throwable. Vì vậy, muốn kiểm soát chính xác đầu ra, hãy khai báo pattern có chủ đích và **kiểm tra log thật sau khi encode**, thay vì dự đoán rằng thiếu `%ex` luôn làm mất stack trace.

### Hạn chế ghi cùng exception ở mọi tầng

Encoder chỉ biểu diễn những sự kiện đã phát. Nếu repository, service và controller cùng `log.error(...)` rồi ném lại một Throwable, encoder sẽ lần lượt format những sự kiện đó; nó **không biết ba bản ghi thuộc cùng một thất bại logic**.

Đặt quy tắc tại ranh giới chịu trách nhiệm xác nhận thất bại cuối, hoặc dùng mã sự kiện riêng nếu mỗi tầng thật sự ghi một loại sự kiện khác nhau. Kỹ thuật tránh log trùng nằm ở **thiết kế sự kiện, logger và appender**, không phải thay đổi pattern của encoder.

## 8. PatternLayoutEncoder so với JSON encoder

`PatternLayoutEncoder` thích hợp cho văn bản người đọc dễ hiểu, ví dụ:

```text
ERROR 2026-01-01T10:15:30Z payment.PaymentService - event=payment.failed order=O-17
```

Ở định dạng text, các trường như `order_id` hoặc `error_code` có thể nằm trong message và bộ thu thập phải parse nếu muốn truy vấn chúng. Một encoder JSON được cấu hình đúng có thể phát cấu trúc:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "message": "Không thể hoàn tất thanh toán",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "error_code": "GATEWAY_UNAVAILABLE",
  "trace_id": "tr-42"
}
```

Đây là **ví dụ về kết quả mong muốn**, không phải JSON đầu ra mặc định của `PatternLayoutEncoder`. Muốn có các trường JSON, cần dùng encoder hỗ trợ cấu trúc, truyền trường qua API/backend tương ứng và kiểm tra mapping tại collector.

### Có thể tự tạo JSON bằng pattern text không?

Về mặt kỹ thuật, ta có thể ghép chuỗi trông giống JSON:

```text
{"level":"INFO","message":"..."}
```

Nhưng cách ghép text thủ công dễ sai khi message chứa dấu nháy kép, dấu gạch chéo ngược, ký tự điều khiển, dấu xuống dòng hoặc dữ liệu Unicode. **Không nên dùng PatternLayoutEncoder làm bộ tạo JSON tổng quát bằng cách nối thô các trường**. Dùng encoder JSON chuyên dụng có quy tắc escape và kiểu dữ liệu đáng tin cậy.

### Chọn encoder JSON bằng cách nào?

Tùy phiên bản Logback và các module mở rộng, khả năng JSON có thể khác nhau. Một lựa chọn phổ biến trong nhiều dự án là thư viện **`logstash-logback-encoder`**, cung cấp `LogstashEncoder`. Ví dụ cấu hình chỉ có ý nghĩa khi ứng dụng đã thêm **dependency tương thích**:

```xml
<appender name="JSON_CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder" />
</appender>
```

Đây là đoạn cấu hình **minh họa để giải thích vị trí encoder JSON**, không phải cấu hình chạy độc lập của ví dụ Maven ở phần 5, vì `pom.xml` mẫu không khai báo thư viện mở rộng này. Không sao chép `LogstashEncoder` vào `logback.xml` của dự án nếu chưa thêm dependency tương thích; ứng dụng có thể báo không tìm thấy class và thất bại khởi tạo logging.

Dù dùng JSON encoder nào, hãy thử các giá trị có dấu nháy, Unicode, dấu xuống dòng, exception và trường null; sau đó parse kết quả bằng bộ đọc JSON để xác nhận dữ liệu còn nguyên và kiểu trường đúng như mong muốn.

### SLF4J 2.x key-value và MDC

Với `SLF4J 2.x`, mã có thể gửi cặp key-value qua fluent API:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .log("Đã tạo đơn hàng");
```

Đây là đoạn minh họa khi `log` và `orderId` đã tồn tại. Các cặp key-value chỉ xuất ở output nếu encoder/pattern hỗ trợ và được cấu hình tương ứng; **chúng không tự xuất thành JSON chỉ vì API đã gọi `addKeyValue`**.

`MDC` (Mapped Diagnostic Context) là ngữ cảnh dùng chung của luồng xử lý, ví dụ `trace_id` hoặc `request_id`. Với pattern text, Logback có thể đọc bằng `%X{trace_id}`. Khi dùng async hoặc chuyển luồng, phải bảo đảm ngữ cảnh được truyền và dọn đúng; nếu không, bản ghi có thể thiếu trace ID hoặc vô tình giữ giá trị từ request trước.

## 9. Đưa encoder vào ConsoleAppender, FileAppender và RollingFileAppender

Một ứng dụng có thể dùng nhiều appender, mỗi appender dùng encoder phù hợp với đích nhận.

Ví dụ văn bản có timestamp vào file:

```xml
<appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/app.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
        <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
```

Đây là **đoạn cấu hình appender**, chưa phải `logback.xml` hoàn chỉnh: muốn hoạt động cần gắn `<appender-ref ref="FILE" />` vào logger/root phù hợp trong tệp cấu hình và bảo đảm tiến trình có quyền ghi thư mục. Ví dụ này minh họa vị trí encoder và thuộc tính file, không hàm ý chính sách xoay vòng.

Với `RollingFileAppender`, phần **rolling policy** quyết định khi nào và bằng cách nào file được đổi tên/xoay vòng, còn **encoder** vẫn quyết định từng sự kiện biến thành những byte nào. Đừng cho rằng thêm `PatternLayoutEncoder` sẽ tự tạo file theo ngày hoặc giới hạn dung lượng. Log rotation là một vấn đề khác, cần `rollingPolicy` và các thành phần phù hợp.

### Có thể tái sử dụng một encoder giữa nhiều appender không?

Về mặt thiết kế, **mỗi appender thường nên có cấu hình encoder riêng** để giữ vòng đời và chính sách đầu ra rõ ràng, đặc biệt nếu hai kênh cần charset, pattern hoặc trường khác nhau. Các phiên bản API có thể cho phép tái sử dụng đối tượng encoder trong một số trường hợp, nhưng tránh phụ thuộc vào việc chia sẻ trạng thái giữa các appender nếu không hiểu rõ vòng đời và tính an toàn luồng.

Ví dụ, console cho người vận hành có thể dùng text ngắn, còn pipeline thu thập cần JSON một sự kiện mỗi dòng. Dùng cùng **mã Java phát log**, nhưng cấu hình **hai appender/encoder** khác nhau, với filter và quyền truy cập riêng.

### Lỗi thường gặp: cấu hình appender nhưng chưa gắn vào logger

Đã viết một appender với encoder đúng nhưng quên:

```xml
<root level="INFO">
    <appender-ref ref="FILE" />
</root>
```

thì không có đảm bảo rằng appender ấy nhận sự kiện. Encoder chỉ chạy khi có sự kiện thật sự đi tới appender. Tương tự, nếu mức ở logger hoặc filter loại sự kiện trước đó, thay đổi encoder sẽ không làm log “xuất hiện trở lại”.

## 10. Hiệu năng và độ tin cậy của quá trình encode

Việc encode không miễn phí: đọc MDC, định dạng ngày giờ, xây message, diễn giải exception, tạo JSON và chuyển Unicode thành byte đều tiêu tốn CPU/bộ nhớ. Chi phí đáng kể nhất thường đến từ **khối lượng log, stack trace lớn, I/O và luồng thu thập**, không phải chỉ từ vài token trong pattern.

Những khía cạnh cần cân nhắc:

1. **Mức log hợp lý:** tránh định dạng hàng triệu sự kiện DEBUG không cần thiết ở production. Log đã bị chặn tại logger sẽ không cần qua encoder.
2. **Pattern vừa đủ:** tên logger, timestamp, level, mã liên kết và thông điệp có ý nghĩa thường hữu ích hơn một pattern quá dài chứa nhiều trường đắt tiền.
3. **Exception có chủ đích:** stack trace dài có giá trị chẩn đoán nhưng tăng dung lượng; tránh ghi lặp ngoại lệ qua mọi tầng.
4. **Bất đồng bộ:** `AsyncAppender` có thể chuyển việc xử lý downstream khỏi thread nghiệp vụ. Thông thường nó bao quanh appender đích; encoder vẫn nằm ở appender ghi thật. Hàng đợi có thể đầy hoặc làm mất log khi dừng đột ngột, tùy chính sách.
5. **Flush và buffer:** encoder tạo byte; appender và stream chịu trách nhiệm ghi/flush/đóng theo vòng đời. Encoder không tự đảm bảo dữ liệu đã lưu bền vững.
6. **Framing:** định dạng line-delimited cần ranh giới bản ghi rõ, nhất là khi pipeline đọc stdout. Bản ghi nhiều dòng và JSON chưa escape dễ khiến collector parse sai.
7. **Concurrent logging:** nhiều thread cùng phát sự kiện; dùng encoder/appender đã được thư viện kiểm thử, không tự lưu trạng thái request vào biến dùng chung của encoder.
8. **Backpressure:** đầu ra chậm hoặc queue đầy có thể làm tăng latency hoặc bỏ log. Cần theo dõi tình trạng appender/collector, không chỉ kiểm tra mã Java gọi log.
9. **Chi phí lưu trữ:** mỗi trường thêm vào mọi bản ghi tần suất cao sẽ tăng dung lượng. Cân nhắc mức độ chi tiết, retention và nhu cầu truy vấn.
10. **Bản ghi quan trọng:** không lấy việc đã gọi `log.error` làm bảo đảm giao nhận. Với sự kiện audit hoặc nghiệp vụ đòi hỏi không mất dữ liệu, cần thiết kế cơ chế lưu/gửi đáng tin và đối soát riêng.

### Thay encoder có làm thay đổi logic nghiệp vụ không?

Về nguyên tắc, encoder chỉ thay **cách biểu diễn**, không nên làm thay kết quả nghiệp vụ. Nhưng encoder được thực thi trong đường logging; cấu hình sai, converter lỗi hoặc serialize đối tượng phức tạp có thể ảnh hưởng tài nguyên và tốc độ. Không đặt tác vụ I/O phụ hoặc phép tính tốn kém không cần thiết vào custom converter/encoder.

## 11. Kiểm thử encoder trong ứng dụng Java

Một kiểm thử tốt nên tách hai mục tiêu:

### 11.1. Kiểm tra sự kiện trước khi encode

Có thể gắn `ListAppender<ILoggingEvent>` của Logback vào logger test để xác nhận:

- Level và logger name đúng.
- `getFormattedMessage()` đúng sau khi thay `{}`.
- `getThrowableProxy()` tồn tại khi cần stack trace.
- MDC hoặc key-value pair đúng ngữ cảnh.
- Một thất bại cuối không bị log trùng nhiều lần ngoài chủ đích.

`ListAppender` giúp kiểm tra sự kiện, **chưa chứng minh byte đầu ra** hay charset của encoder chính xác.

### 11.2. Kiểm tra byte thực sự được encoder tạo ra

Dùng một appender test có output stream trong bộ nhớ, gắn đúng encoder production rồi phát sự kiện mẫu. Đọc byte theo charset đã cấu hình, đối chiếu:

- Thứ tự level/logger/message và dấu phân cách.
- Xuống dòng theo chính sách.
- Chữ tiếng Việt và ký tự Unicode không bị hỏng.
- Giá trị chứa dấu nháy hoặc xuống dòng có được escape như định dạng yêu cầu không.
- Với JSON: có thể parse được và các trường có kiểu mong đợi.
- Với Throwable: stack trace/cause thể hiện theo hợp đồng.
- Không xuất secret hoặc dữ liệu giả cần che.

Đối với pattern có `%d`, `%thread` hoặc stack trace, tránh so sánh toàn bộ output với một chuỗi cố định dễ thay đổi; kiểm tra các thành phần ổn định hoặc dùng pattern kiểm tra phù hợp. Ví dụ ở phần 5 cố tình **loại timestamp** để stdout kiểm tra được một cách dễ dàng.

### 11.3. Kiểm tra tích hợp với collector

Sau khi ứng dụng phát log, xác nhận collector thật sự:

1. Nhận đúng output stream hoặc đường dẫn file.
2. Giải mã UTF-8 phù hợp.
3. Nhận đúng ranh giới bản ghi và xử lý multiline khi cần.
4. Parse chính xác `event_code`, `trace_id`, `error_code`.
5. Không làm mất, nhân đôi hoặc loại bỏ sự kiện ngoài quy tắc.
6. Có quyền truy cập và thời gian lưu phù hợp; không chứa dữ liệu bị cấm.

**Lưu ý:** thấy một dòng log ở console chưa chứng minh dòng đó có trong kho log tập trung. Ngược lại, một sự kiện hiện hai lần trong giao diện có thể do fan-out, additivity hoặc retry ở pipeline, không phải encoder “tự nhân đôi” thông điệp.

## 12. Các lỗi cấu hình phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy log | Mức logger, filter, appender chưa được gắn | Kiểm tra logger → appender trước; encoder không tạo sự kiện. |
| Có log nhưng sai định dạng | Pattern sai, logback.xml khác đang được tải | Xác định cấu hình đang hoạt động và encoder của appender nhận sự kiện. |
| Tên logger quá dài hoặc quá ngắn | Sử dụng `%logger` hoặc `%logger{0}` không theo mục tiêu | Điều chỉnh conversion word, giữ tên đầy đủ khi cần. |
| Các dòng dính vào nhau | Thiếu `%n` trong pattern text | Thêm dấu xuống dòng theo chính sách định dạng. |
| Chữ tiếng Việt thành ký tự lỗi | Encoder và nơi đọc dùng charset khác nhau | Thống nhất UTF-8 xuyên suốt đường thu thập. |
| Stack trace không như mong đợi | Throwable không được truyền, pattern/encoder hoặc collector giới hạn | Xác minh event có Throwable, rồi kiểm tra formatter và multiline. |
| JSON không hợp lệ | Tự nối JSON bằng pattern text, không escape | Chuyển sang encoder JSON chuyên dụng và test parse. |
| Có cấu hình `LogstashEncoder` nhưng không chạy | Thiếu hoặc lệch phiên bản dependency | Kiểm tra JAR, classpath và tương thích Logback/SLF4J. |
| Dùng `%X{trace_id}` nhưng trống | MDC không được đặt/truyền theo luồng xử lý | Kiểm tra propagation và cleanup của MDC. |
| Log xuất hai lần | Appender ở logger con và root với additivity, hoặc collector gửi lại | Kiểm tra cấu hình route và đếm từng đích. |
| File lớn không xoay vòng | Dùng `FileAppender` hoặc thiếu rolling policy | Dùng `RollingFileAppender` cùng chính sách xoay vòng. |
| Không có trường key-value JSON | API fluent đã gắn trường nhưng encoder không xuất | Kiểm tra hỗ trợ và cấu hình encoder/provider. |

## 13. Bài tập vận dụng

**Bài 1.** Cho cấu hình encoder:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%level|%logger{0}|%msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Và một lời gọi:

```java
logger.warn("event=payment.retry attempt={}", 3);
```

Giả sử logger tên `com.example.payment.PaymentService`, hãy xác định phần output.

**Gợi ý:**

```text
WARN|PaymentService|event=payment.retry attempt=3
```

`%logger{0}` rút tên nguồn, `%msg` lấy message đã thay `{}`, `%n` thêm xuống dòng.

**Bài 2.** Nếu thay `<pattern>` thành `%msg%n` nhưng giữ nguyên mã nghiệp vụ, điều gì thay đổi?

**Gợi ý:** Output vẫn có message đã thay tham số, nhưng mất level và logger name từ đầu dòng. Quyết định sự kiện được tạo/nhận không mặc nhiên thay đổi, vì mức và appender không bị đổi.

**Bài 3.** Ứng dụng ghi tiếng Việt vào file, nhưng công cụ phân tích hiện ký tự lỗi. Thứ tự chẩn đoán nên là gì?

**Gợi ý:** Kiểm tra dữ liệu nguồn, charset của encoder, byte thực tế trong file, charset khi collector đọc/parse và cách giao diện hiển thị. Thống nhất UTF-8, không tự động sửa message nghiệp vụ khi vấn đề nằm ở khâu giải mã.

**Bài 4.** Một nhóm muốn đưa JSON vào collector, nên tự viết `<pattern>{"message":"%msg"}</pattern>` hay dùng JSON encoder?

**Gợi ý:** Nên dùng JSON encoder phù hợp. Message có dấu nháy, xuống dòng hoặc gạch chéo ngược có thể phá JSON tự ghép, và trường số có thể bị chuyển nhầm thành chuỗi. Kiểm thử parse JSON và kiểu dữ liệu tại đích.

**Bài 5.** Một exception đã được log đúng ở cấp `ERROR` nhưng không thấy stack trace ở hệ thống trung tâm. Có thể kết luận do encoder không?

**Gợi ý:** Chưa. Kiểm tra mã có truyền Throwable hay chỉ `getMessage()`, `ILoggingEvent` có Throwable, pattern/encoder có biểu diễn exception, collector có giữ multiline hoặc trường exception, và giao diện tìm kiếm có giới hạn dữ liệu không.

**Bài 6.** Với cùng một sự kiện, cần console text ngắn cho developer và JSON cho collector. Có nên viết hai lời gọi `log.info` trong mã nghiệp vụ?

**Gợi ý:** Thường **không**. Phát một sự kiện rồi cấu hình những appender/encoder riêng theo đích. Cần kiểm tra additivity và routing để không nhân đôi trong cùng kênh, đồng thời xác định trường nhạy cảm có được bảo vệ trên tất cả các đường đi không.

**Tự đánh giá:** Bạn hiểu encoder của Logback khi có thể giải thích chuỗi **`ILoggingEvent → Encoder → byte → Appender output`**, đọc và thay đổi `PatternLayoutEncoder`, phân biệt `{}` của SLF4J với `%msg` của Logback, biết lý do dùng UTF-8 và `%n`, xử lý exception, và xác minh output đã định dạng bằng test thay vì chỉ nhìn vào lời gọi logger.