# Appender bất đồng bộ (Async Appender) trong Java Logging

## 1. Appender bất đồng bộ giải quyết vấn đề gì?

Trong Java Logging, một **appender** là thành phần nhận sự kiện log đã được tạo và đưa nó tới đích như console, file hoặc collector qua mạng. Tên **handler** thường xuất hiện trong `java.util.logging` (JUL), còn **appender** phổ biến ở Logback và Log4j 2. Dù tên gọi khác nhau, cả hai đều tham gia vào khâu xử lý và xuất bản ghi.

Với appender **đồng bộ (synchronous)**, thread đang chạy nghiệp vụ có thể trực tiếp thực hiện cả việc định dạng và ghi dữ liệu:

```text
Thread xử lý request
  |
  +-- xử lý đơn hàng
  +-- logger.info(...)
        |
        +-- kiểm tra level/filter
        +-- appender format message
        +-- ghi console/file/socket  [có thể phải chờ I/O]
        |
  +-- tiếp tục xử lý request
```

Trong mô hình **bất đồng bộ (asynchronous)**, lời gọi logging thường đưa sự kiện vào hàng đợi; một thread riêng lấy sự kiện ra và thực hiện công việc của appender đích:

```text
Thread xử lý request (producer)
  |
  +-- logger.info(...)
        |
        +-- kiểm tra level/filter
        +-- chuẩn bị/snapshot dữ liệu cần thiết
        +-- enqueue event vào hàng đợi
        |
  +-- tiếp tục xử lý request

                 Hàng đợi sự kiện
                  [A][B][C]...
                       |
                       v
                 Worker thread (consumer)
                       |
                       v
               File/Console/Collector
```

Mục tiêu là **giảm thời gian thread nghiệp vụ phải chờ công việc ghi log**, nhất là khi formatter hoặc I/O tốn thời gian. Tuy nhiên, chữ “async” **không có nghĩa logger không bao giờ chặn, mọi log chắc chắn được lưu, hay throughput luôn tốt hơn**. Hành vi thực tế phụ thuộc queue, chính sách quá tải, appender đích, cấu hình flush và quá trình tắt ứng dụng.

Một sự kiện log được **đưa vào queue thành công** vẫn có thể **chưa được ghi ra file/console**. Vì vậy cần phân biệt ba mốc:

1. **Logger nhận lời gọi** từ ứng dụng.
2. **Queue chấp nhận sự kiện** (có thể chặn hoặc bỏ nếu quá tải).
3. **Appender đích ghi hoặc chuyển tiếp sự kiện** (có thể lỗi, buffer hoặc mất kết nối).

Những mốc này là khác nhau; không thể dùng việc gọi `logger.info` thành công để khẳng định bản ghi đã lưu bền vững.

## 2. Appender đồng bộ và bất đồng bộ khác nhau như thế nào?

| Khía cạnh | Appender đồng bộ | Appender bất đồng bộ |
|---|---|---|
| Thread thực hiện I/O | Thường là thread phát log | Thường là worker thread riêng |
| Độ trễ lời gọi logging | Có thể gánh chi phí format/ghi | Thường thấp hơn khi queue còn chỗ và chỉ enqueue |
| Khi đích ghi rất chậm | Thread nghiệp vụ có thể chờ I/O | Queue tăng; sau đó producer có thể chặn hoặc sự kiện bị bỏ |
| Bộ nhớ | Không cần backlog lớn riêng | Có queue, event/metadata và nhu cầu theo dõi dung lượng |
| Khi process chết đột ngột | Có nguy cơ mất buffer hoặc ghi dang dở | Có thêm rủi ro mất các event đang chờ trong queue |
| Thứ tự | Theo luồng thực thi đồng bộ và cơ chế sink | Cần xét nhiều producer, worker, appender và collector |
| Quản lý shutdown | Vẫn cần flush/close phù hợp | Đặc biệt cần drain queue, flush và giới hạn chờ |
| Độ phức tạp | Thường đơn giản | Thêm queue policy, consumer lifecycle và monitoring |

**Khi nào có lợi?** Nếu request tạo nhiều log và sink (console trong container, file hoặc network) có độ trễ biến thiên, async appender có thể giúp giảm tác động trực tiếp tới latency của thread nghiệp vụ.

**Khi nào ít lợi?** Với lượng log thấp hoặc sink rất nhanh, việc thêm queue, scheduling và context snapshot có thể tạo overhead không cần thiết. Khi queue đầy liên tục, async chỉ **dời chỗ tắc nghẽn**, không xóa bỏ giới hạn I/O.

## 3. Cơ chế producer–queue–consumer

Một pipeline phổ biến có ba thành phần:

- **Producer:** thread ứng dụng gọi `log.info(...)`, `log.error(...)`... sau khi qua level/filter, backend tạo một log event và chuẩn bị dữ liệu cần giữ.
- **Queue:** bộ đệm hữu hạn chứa các event trong lúc đợi ghi, thường dùng cấu trúc thread-safe. Kích thước queue là giới hạn bộ nhớ/backlog cần quản lý, không phải “thêm càng lớn càng tốt”.
- **Consumer:** thread lấy event ra, chuyển tới appender được bọc hoặc backend đích; có thể format và ghi console/file/network.

Ví dụ:

```text
Peak: 1.000 events/s đến trong 3 giây
Sink: tối đa 600 events/s trong cùng giai đoạn

Tốc độ backlog tăng ≈ 400 events/s
Sau 3 giây, lượng tồn đọng lý thuyết ≈ 1.200 events
```

Con số chỉ **minh họa toán học với tốc độ không đổi**, chưa tính batching, producer block, discard, burst, overhead hay trường hợp queue đầy. Nếu queue đủ nhỏ, nó sẽ chạm ngưỡng trước khi đạt tồn đọng lý thuyết; khi đó chính sách quá tải quyết định có chặn hay bỏ event.

### Độ trễ và thông lượng

Async có thể giảm **thời gian đồng bộ ở call site**, nhưng không nhất thiết giảm **thời gian từ lúc sự kiện xảy ra tới lúc sự kiện xuất hiện ở collector**. Một queue dài có thể khiến event “đến muộn”.

Để đánh giá, nên đo ít nhất:

- p50/p95/p99 thời gian request có logging.
- Tổng events/s mà sink ghi được.
- Queue depth và remaining capacity theo thời gian.
- Số event bị bỏ (nếu backend có metrics/hook).
- Độ trễ event timestamp → thời điểm sink/collector nhận.
- CPU, heap, GC, I/O và hành vi khi tải đỉnh.

Đừng chỉ dựa vào kết quả một microbenchmark gọi `log.debug` với level đã tắt; kết quả đó không đo chi phí ghi log thực tế.

## 4. Logback AsyncAppender: thành phần và giới hạn

Trong Logback Classic, `ch.qos.logback.classic.AsyncAppender` là appender bất đồng bộ thường được dùng với SLF4J. Nó bọc một appender đích (ví dụ `ConsoleAppender` hoặc `RollingFileAppender`) rồi đưa log event qua hàng đợi cho worker thread xử lý.

Một topology hợp lệ:

```text
SLF4J API
    |
    v
Logback logger hierarchy
    |
    v
ASYNC appender
    |
    +-- queue
           |
           v
         worker
           |
           v
      CONSOLE appender
           |
           v
        stdout
```

Điều cần lưu ý:

1. `ASYNC` không tự ghi file/console: nó phải được gắn với **appender đích**.
2. Nếu root đồng thời tham chiếu trực tiếp `CONSOLE` và `ASYNC` (mà `ASYNC` cũng tham chiếu `CONSOLE`), một sự kiện có thể xuất **hai lần**.
3. Các phiên bản Logback Classic phổ biến hỗ trợ **một appender đích cho một AsyncAppender**; nếu muốn các đường ra riêng biệt, cần thiết kế routing/appenders tương ứng, không mặc định một async wrapper có thể gắn tùy ý nhiều đích.
4. `AsyncAppender` không biến message thành JSON, không tự sinh trace ID và không bảo đảm bền vững; các yêu cầu ấy nằm ở API tạo event, encoder và hệ thống thu thập.

## 5. Cấu hình Logback AsyncAppender

Ví dụ `logback.xml` dùng console appender ở phía dưới:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>64</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>0</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Đây là **cấu hình Logback Classic**, không phải cú pháp cho JUL `Handler`. Một số thuộc tính, giá trị mặc định và khả năng hỗ trợ thay đổi theo phiên bản; hãy đối chiếu manual của version đang dùng trước khi quyết định giá trị production.

### Ý nghĩa từng thuộc tính

| Thuộc tính | Vai trò | Lưu ý |
|---|---|---|
| `queueSize` | Giới hạn số event chờ trong queue | Tăng queue dùng thêm bộ nhớ và có thể kéo dài thời gian đến sink |
| `discardingThreshold` | Điều khiển ngưỡng mà những event được coi là ít quan trọng có thể bị bỏ | `0` tắt cơ chế bỏ có chọn lọc vì ngưỡng này; không tạo bảo đảm không mất log |
| `neverBlock` | Quyết định có tránh chặn producer khi queue đầy | `false` cho phép chờ queue; `true` có thể loại event khi không enqueue được |
| `maxFlushTime` | Thời gian chờ worker xử lý queue khi dừng appender, thường tính bằng ms | `0` trong Logback có nghĩa chờ không giới hạn khi stop; nếu sink treo có thể kẹt shutdown |
| `includeCallerData` | Có thu thêm thông tin nơi gọi (class/method/file/line) hay không | Thu stack/caller data tốn chi phí; không bật khi không cần |
| `appender-ref` | Chỉ định appender đích bên dưới | Nếu thiếu đích, sự kiện không có nơi để ghi như dự kiến |

Với `discardingThreshold`, Logback Classic coi những event mức thấp (thông thường TRACE/DEBUG/INFO) là ứng viên bỏ khi queue sắp đầy. Mục đích là ưu tiên các mức WARN/ERROR trong tình trạng quá tải; hành vi chính xác cần kiểm tra theo version/cấu hình. Đặt `discardingThreshold=0` **không biến queue thành kho lưu trữ bền vững**.

Với `neverBlock=false`, nếu queue đầy, thread phát log có thể **chờ** tới khi có chỗ. Điều này thường ưu tiên giữ event hơn so với cấu hình bỏ ngay, nhưng làm mất một phần lợi ích latency của async khi sink không theo kịp.

Với `neverBlock=true`, producer thường không chờ; nếu không đưa được sự kiện vào queue, backend có thể **bỏ event**, bao gồm cả event quan trọng nếu queue thực sự đầy. Vì vậy không nên bật chỉ vì muốn “logging không ảnh hưởng request” mà chưa chấp nhận rõ rủi ro mất dữ liệu.

## 6. Ví dụ Java 17+ chạy được: SLF4J + Logback AsyncAppender

Ví dụ dưới đây dùng **Java 17**, **Maven**, **SLF4J API** và **Logback Classic**. Mục tiêu: cho thấy thread nghiệp vụ phát sự kiện INFO/WARN, còn `ASYNC` đưa chúng tới console thông qua queue.

Với ba event, queue có đủ chỗ, `discardingThreshold=0` và `neverBlock=false`. Chương trình **dừng LoggerContext có chủ đích** để worker xử lý nốt queue trước khi process kết thúc bình thường. Ví dụ không mô phỏng crash hay ép queue đầy; những trường hợp đó không có output cố định.

### 6.1. Cấu trúc dự án

```text
async-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/AsyncAppenderDemo.java
        └── resources/
            └── logback.xml
```

### 6.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>async-appender-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
                <configuration>
                    <mainClass>com.example.logging.AsyncAppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` kéo theo các thành phần Logback/SLF4J thích hợp theo khai báo dependency của nó. Phiên bản trong `pom.xml` được cố định **chỉ để minh họa cách tái hiện bài học**, không phải tuyên bố đây là bản mới nhất. Ở dự án thực tế, hãy chọn phiên bản được hỗ trợ và đã kiểm tra security advisories/BOM.

### 6.3. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>64</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>0</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Chỉ có `ASYNC` được gắn vào root; `CONSOLE` là appender **đích của ASYNC**, không được gắn thêm trực tiếp vào root. Cấu hình này tránh nhân đôi output từ hai đường đi.

Đặt `maxFlushTime=0` cho demo để `stop` chờ worker rút hết queue; trong production cần cân nhắc thời gian shutdown hữu hạn nếu downstream có thể treo lâu.

### 6.4. Tệp `src/main/java/com/example/logging/AsyncAppenderDemo.java`

```java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AsyncAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(AsyncAppenderDemo.class);

    public static void main(String[] args) {
        LOG.info("event=order_accepted orderId={}", "ORD-7");
        LOG.warn("event=retry_scheduled attempt={}", 1);
        LOG.info("event=order_completed orderId={}", "ORD-7");

        // Khi ví dụ kết thúc bình thường, dừng context có chủ đích.
        // Việc stop giúp worker xử lý các event đã được enqueue.
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        context.stop();
    }
}
```

Đây là tệp Java **độc lập trong dự án Maven đã nêu**. Không biên dịch riêng chỉ với `javac` thiếu classpath vì `LoggerFactory` và `LoggerContext` đến từ dependency ngoài JDK.

### 6.5. Chạy bằng Maven

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Với appender console như trên, ba dòng **do Logback ghi ra stdout** trong lần chạy bình thường là:

```text
INFO AsyncAppenderDemo - event=order_accepted orderId=ORD-7
WARN AsyncAppenderDemo - event=retry_scheduled attempt=1
INFO AsyncAppenderDemo - event=order_completed orderId=ORD-7
```

Đây là nội dung message/event có thể kiểm tra; Maven có thể phát thêm thông báo của chính build tool nếu môi trường khác cấu hình. Thứ tự trên phản ánh **một producer, một async queue và một appender đích**. Khi có nhiều producer và nhiều đường output, không được coi đây là cam kết thứ tự toàn cục của một hệ thống phân tán.

### 6.6. Giải thích vì sao kết quả đúng

- Root logger ở `INFO` chấp nhận `INFO` và `WARN`; không có event DEBUG trong chương trình.
- Cả ba sự kiện được chuyển vào `ASYNC` thay vì gọi `CONSOLE` trực tiếp trên thread phát log.
- Queue 64 phần tử đủ cho ba sự kiện của demo, không cần mô phỏng overload.
- `discardingThreshold=0` ngăn cơ chế bỏ chọn lọc theo ngưỡng của AsyncAppender; `neverBlock=false` cho phép producer chờ nếu cần chỗ.
- `%logger{0}` hiển thị phần cuối của tên logger là `AsyncAppenderDemo`, trong khi tên đầy đủ của logger vẫn là `com.example.logging.AsyncAppenderDemo`.
- `context.stop()` gọi vòng đời stop của các appender, hỗ trợ xả queue và đóng đích ghi trong điều kiện bình thường. Việc stop có thể chờ và phụ thuộc trạng thái worker/sink; không phải cơ chế bảo toàn log khi tiến trình bị `kill -9` hoặc mất điện.
- `<target>System.out</target>` khiến sự kiện từ appender này ra **stdout**; đừng nhầm với `java.util.logging.ConsoleHandler` thường sử dụng stderr.

**Không cần gọi `Thread.sleep(...)` để “đợi log chạy xong”.** Sleep mang tính may rủi; dừng lifecycle và flush đúng cơ chế tốt hơn. Trong ứng dụng server dài hạn, thường để framework sở hữu `LoggerContext` và dừng nó ở giai đoạn shutdown hợp lệ; không stop context sau mỗi request.

## 7. Chính sách khi queue đầy: block hay drop?

Đây là quyết định quan trọng nhất khi vận hành async appender.

### 7.1. Ưu tiên giữ sự kiện — chấp nhận producer có thể bị chặn

Ví dụ Logback:

```xml
<queueSize>2048</queueSize>
<discardingThreshold>0</discardingThreshold>
<neverBlock>false</neverBlock>
```

Đây là **đoạn cấu hình tham khảo** nằm trong `<appender class="ch.qos.logback.classic.AsyncAppender">`, không phải file XML độc lập. Nó làm giảm nguy cơ mất log vì cơ chế ngưỡng discard; khi queue đầy, producer có thể chờ.

Trade-off: nếu đích ghi chậm liên tục, request threads có thể chặn ở lời gọi log và p99 latency tăng. Thiết lập này không bảo đảm log không mất khi crash, appender lỗi, collector mất kết nối hoặc chính sách khác làm bỏ sự kiện.

### 7.2. Ưu tiên latency của request — chấp nhận event có thể mất

Ví dụ:

```xml
<queueSize>2048</queueSize>
<neverBlock>true</neverBlock>
```

Khi queue không còn chỗ, chế độ này có thể bỏ event thay vì chặn producer. Vì thế ngay cả khi message ở mức ERROR/WARN, **không nên hứa chắc sự kiện được ghi**. Với log phục vụ điều tra thông thường, đây có thể là trade-off có chấp nhận được; với log bắt buộc phục vụ audit, billing hoặc security, phải đánh giá kỹ hơn và thường cần **pipeline bền vững chuyên biệt**.

### 7.3. Discard theo mức độ ưu tiên

Trong nhiều phiên bản Logback Classic, `AsyncAppender` coi TRACE/DEBUG/INFO là ít quan trọng hơn WARN/ERROR khi hàng đợi sắp đầy. `discardingThreshold` điều khiển ngưỡng bắt đầu bỏ những event này; cấu hình `0` tắt cơ chế bỏ vì ngưỡng đó.

Nhưng cần phân biệt:

- **Discard vì threshold**: bỏ một số event trước khi queue thật sự đầy theo chính sách backend.
- **Discard vì neverBlock**: khi không enqueue được do đầy, có thể bỏ sự kiện không phụ thuộc mức độ.
- **Mất khi shutdown/crash/downstream**: là rủi ro khác, không được xử lý chỉ bằng việc đặt threshold về 0.

Đừng chọn một cấu hình chỉ theo tên property. Hãy viết thành chính sách vận hành: **được phép mất loại event nào, khi nào chặn, timeout bao lâu, và sẽ cảnh báo bằng tín hiệu nào**.

## 8. Kích thước queue và backpressure

### 8.1. Queue lớn không tạo thông lượng vô hạn

Giả sử producer tạo 4.000 events/s nhưng sink chỉ xử lý 1.000 events/s, backlog sẽ tăng khoảng 3.000 events/s trong thời gian tải này tiếp diễn. Queue 12.000 phần tử trong mô hình lý tưởng sẽ đầy sau khoảng bốn giây nếu lúc đầu trống và không có thay đổi tốc độ.

Tăng queue chỉ **mua thêm thời gian trước khi chặn/drop**, đồng thời dùng thêm RAM và tăng khoảng cách giữa event timestamp với thời điểm ghi. Sự cố sink kéo dài sẽ lấp đầy cả queue lớn.

### 8.2. Chi phí bộ nhớ không chỉ là số phần tử

Mỗi log event có thể giữ message, arguments, `Throwable`, MDC/context và đối tượng liên quan. Một bản ghi exception lớn khác nhiều so với một message vài byte. Ước lượng queue memory bằng `queueSize × kích thước trung bình event` chỉ là bước đầu; phải đo heap allocation dưới tải đại diện.

Không nên dùng queue cực lớn để che giấu sink quá chậm. Cần giải quyết tốc độ sink, giảm log volume, sampling khi phù hợp, tối ưu encoder hoặc thiết kế pipeline tốt hơn.

### 8.3. Backpressure là quyết định kỹ thuật và nghiệp vụ

- **Block:** giúp hạn chế mất event do queue, nhưng ảnh hưởng ứng dụng.
- **Drop:** ưu tiên ứng dụng tiếp tục, nhưng giảm thông tin điều tra.
- **Sample:** ghi một phần sự kiện nhiều lần lặp; cần bảo vệ error/audit bắt buộc.
- **Spool/durable buffer:** yêu cầu một cơ chế bền vững riêng; không tự có trong queue in-memory của AsyncAppender.

Không có một quy tắc “luôn block” hay “luôn drop” cho mọi loại hệ thống. Với thanh toán, security audit hay sự kiện ảnh hưởng tài chính, có thể cần **transactional outbox, event store hoặc audit pipeline** thay vì phụ thuộc duy nhất vào log bất đồng bộ.

## 9. Mức log và filter vẫn hoạt động trước/giữa các tầng

AsyncAppender **không thay thế logger level**. Ví dụ:

```java
// Đoạn minh họa SLF4J:
LOG.debug("event=cache_probe key={}", key);
```

Nếu effective level của logger là INFO, sự kiện DEBUG thông thường bị loại trước khi tới AsyncAppender; nó không vào queue. Việc tăng `queueSize` không làm DEBUG xuất hiện.

Ngoài ra, filter trên logger/appender có thể loại sự kiện trước hoặc sau các bước khác tùy backend. Hãy kiểm tra topology thực:

```text
Logger level / filter
       |
       v
AsyncAppender policy
       |
       v
Queue
       |
       v
Worker + destination appender/filter/encoder
```

Khi không thấy log, cần phân biệt **bị lọc từ đầu**, **bị drop do quá tải**, **chưa được consumer ghi**, hay **đã ghi nhưng collector không thu được**. Mỗi nguyên nhân có cách xử lý khác nhau.

## 10. MDC, thread name và caller data khi logging bất đồng bộ

### 10.1. Vì sao context cần được chụp trước khi đổi thread?

Với request thread, một event có thể có:

```text
logger=com.example.OrderService
thread=http-worker-12
traceId=trace-42
requestId=req-42
message=event=order_accepted
```

Sau khi enqueue, việc ghi thực tế diễn ra trên worker thread của appender, **khác** thread nghiệp vụ. Nếu formatter chỉ đọc `ThreadLocal` hoặc MDC hiện tại của worker tại lúc ghi, ngữ cảnh có thể trống hoặc sai.

Trong Logback Classic, `AsyncAppender` chuẩn chuẩn bị dữ liệu cho xử lý hoãn, bao gồm nội dung cần thiết của message và ngữ cảnh như MDC/thread name, trước khi chuyển sự kiện sang worker. Vì vậy pattern sử dụng MDC của Logback vẫn có thể làm việc với async appender **khi ứng dụng đã gắn MDC đúng trước lúc gọi logger**.

Ví dụ API MDC (SLF4J), **đoạn minh họa trong phương thức có `LOG`**:

```java
import org.slf4j.MDC;

MDC.put("requestId", "req-42");
try {
    LOG.info("event=order_accepted orderId={}", "ORD-7");
} finally {
    MDC.remove("requestId");
}
```

Trong `logback.xml` có thể dùng:

```xml
<pattern>%level requestId=%X{requestId} %logger{0} - %msg%n</pattern>
```

Với Logback + SLF4J phù hợp, async appender có thể xuất giá trị `req-42` đã được gắn với sự kiện dù caller đã dọn MDC trước khi worker thực sự ghi. Đây là **ví dụ về ngữ cảnh của log event**, không phải bằng chứng MDC tự lan qua các thread nghiệp vụ của ứng dụng.

### 10.2. MDC ở luồng nghiệp vụ khác là vấn đề riêng

Nếu mã nghiệp vụ chuyển sang `ExecutorService`, `CompletableFuture`, virtual threads hoặc callback, ứng dụng vẫn phải có chiến lược **truyền context giữa các task**. AsyncAppender chỉ hỗ trợ event logging sau khi event đã được tạo. Nó không tự chuyển request ID từ controller sang một tác vụ chạy trên thread khác.

Phải dọn MDC trong `finally`, đặc biệt với thread pool, để tránh thông tin request trước bị rò sang request sau.

### 10.3. Caller data

Các pattern gồm tên class, method, file, line tại nơi gọi có thể cần tìm stack frame. Trong Logback, `includeCallerData` của AsyncAppender thường **tắt mặc định** vì chi phí. Nếu bật:

```xml
<includeCallerData>true</includeCallerData>
```

backend sẽ thu caller data sớm để không gán nhầm worker appender làm nguồn. Nhưng việc thu stack có thể tăng CPU và latency tại thread phát log, làm giảm lợi ích async. Nếu không cần số dòng/method trong production, đừng bật chỉ để làm pattern dài hơn.

## 11. Throwable, stack trace và dữ liệu mutable

### 11.1. Giữ exception đúng cách

Với SLF4J:

```java
// Đoạn minh họa, error là Throwable bắt được:
LOG.error("event=order_save_failed orderId={}", orderId, error);
```

Đối tượng Throwable cuối thường được logger nhận diện làm cause trong các overload parameterized logging phù hợp. AsyncAppender chuyển event tới appender đích; encoder/layout của đích **phải có khả năng xuất exception** nếu muốn stack trace.

Không thay đối tượng exception bằng:

```java
LOG.error("save failed: {}", error.getMessage());
```

Dòng trên chỉ ghi text của message, có thể làm mất stack trace và cause chain. Một cấu hình async đúng cũng không thể tự khôi phục exception nếu mã ứng dụng chưa truyền nó vào event.

### 11.2. Mutable arguments

Đừng giả định truyền một đối tượng có thể thay đổi vào logger rồi sửa nó ngay sau lời gọi luôn cho output theo giá trị mới nhất hoặc cũ nhất một cách nhất quán. Các backend thường chuẩn bị/snapshot một số dữ liệu trước khi enqueue, nhưng không phải mọi kiểu đối tượng tùy biến đều được deep-copy.

Đối với thông tin quan trọng, ưu tiên các giá trị nguyên thủy, String, ID ổn định hoặc structured fields được snapshot có chủ đích. Không log cả entity chứa lazy fields hay bí mật chỉ vì “async sẽ xử lý giúp”.

### 11.3. Nguyên nhân lỗi và chi phí format

Stack trace dài hoặc JSON serialization có thể vẫn tốn CPU đáng kể. Async có thể chuyển một phần chi phí sang worker, nhưng việc tạo event, tính biểu thức đối số và chuẩn bị message/context **vẫn phát sinh ở phía caller** tùy backend. Không kết luận async làm `buildExpensivePayload()` trở thành lazy:

```java
// buildExpensivePayload() vẫn được Java gọi trước LOG.debug(...):
LOG.debug("payload={}", buildExpensivePayload());
```

Nếu DEBUG thường tắt, dùng guard hoặc API supplier/lazy phù hợp để hoãn biểu thức tốn kém; đó là vấn đề khác với appender bất đồng bộ.

## 12. Ghi log nhiều đích: thứ tự, trùng lặp và độ tin cậy

### 12.1. Một đường async tới một đích

Ví dụ trong `logback.xml`:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC"/>
</root>
```

`ASYNC` bọc `CONSOLE`; event có **một đường**. Nếu thêm:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC"/>
    <appender-ref ref="CONSOLE"/>
</root>
```

trong khi `ASYNC` vẫn bọc `CONSOLE`, cùng event có thể đi qua hai đường và xuất hai lần. Đây là lỗi topology, không phải do gọi `LOG.info` hai lần.

### 12.2. Nhiều appender/queue không tạo thứ tự toàn cục

Một queue FIFO thường giữ thứ tự **đưa vào queue đó**. Nhưng nếu nhiều request threads ghi xen kẽ, thứ tự nhập queue phản ánh lịch thực thi thực tế, không phải thứ tự nghiệp vụ của các request.

Với hai async appenders có queue/worker riêng, console và file có thể nhận event theo thời gian khác nhau. Collector phân tán cũng có batching và retry. Khi cần điều tra trình tự, ghi **event timestamp, traceId/requestId, attempt, sequence ID** khi nghiệp vụ cần; không dựa hoàn toàn vào thứ tự dòng xuất hiện trong file.

### 12.3. Không nhầm “đã enqueue” với “đã lưu”

Queue của Logback AsyncAppender ở trong bộ nhớ JVM. Nếu process bị kill cưỡng bức, node mất điện hoặc container bị xóa mà không cho shutdown hợp lệ, những event còn trong queue có thể mất. Ngay cả khi worker đã chuyển record cho appender file, OS còn có page cache và cơ chế flush riêng.

Nếu nghiệp vụ thật sự cần cam kết bền vững hoặc exactly-once, không dùng async appender in-memory làm nguồn chân lý duy nhất. Cân nhắc transactional outbox, append-only durable event log, database transaction hoặc kiến trúc audit phù hợp.

## 13. Shutdown và flush: nơi dễ mất log nhất

Khi ứng dụng dừng, hãy xác định cơ chế quản lý vòng đời logging:

1. Ứng dụng ngừng nhận công việc mới khi thích hợp.
2. Các task nghiệp vụ được yêu cầu hoàn thành/dừng theo chính sách.
3. Logging context hoặc appender nhận tín hiệu `stop`.
4. Worker có cơ hội rút queue, chuyển event tới appender đích và flush/close.
5. Process kết thúc trong khoảng thời gian cho phép.

Ví dụ mục 6 gọi:

```java
LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();
context.stop();
```

Đây là logic shutdown chủ đích của **demo Logback**, không phải mẫu phải chèn sau mỗi method nghiệp vụ. Trong Spring Boot hoặc framework, lifecycle logging thường được framework quản lý; đừng tự dừng context ở giữa vòng đời server.

`maxFlushTime` điều khiển thời gian chờ khi dừng trong Logback AsyncAppender. Giá trị `0` đợi không giới hạn và có thể làm shutdown treo nếu appender đích bị kẹt; một giá trị dương đặt giới hạn chờ, nhưng khi quá hạn còn queue, một số event có thể chưa được xuất. Cần cân nhắc:

- Shutdown grace period của container/orchestrator.
- Độ trễ file/network sink và lượng backlog tối đa.
- Số event có thể mất nếu process bị buộc kết thúc.
- Khả năng flush của appender đích; không phải mọi network sink tự cung cấp durability.
- Quan sát số event chưa xử lý khi shutdown và báo cáo lỗi phù hợp.

Không dùng `Thread.sleep(1000)` như một “bảo đảm flush”: nếu backlog lớn hoặc sink chậm, một giây không có ý nghĩa chắc chắn.

## 14. AsyncAppender của Logback và async logging trong Log4j 2

Logback AsyncAppender và các cơ chế async trong Log4j 2 cùng mục tiêu giảm công việc trên caller nhưng **không phải cùng class hay cùng cấu hình**.

### 14.1. Logback AsyncAppender

- Bọc một appender đích và dùng queue/worker.
- Cấu hình thường nằm trong `logback.xml`/`logback-spring.xml` (tùy ứng dụng).
- Có các tham số liên quan queue size, discarding threshold, neverBlock, shutdown và caller data.
- Khi dùng trong Spring Boot, cần phân biệt backend Logback thực tế với các starter/logging system đã được framework chọn.

### 14.2. Log4j 2 AsyncAppender

Log4j 2 cung cấp **AsyncAppender** bọc các appender khác theo cơ chế riêng. Ví dụ **fragment cấu hình Log4j 2**, không phải file đầy đủ:

```xml
<Async name="ASYNC">
    <AppenderRef ref="CONSOLE"/>
</Async>
```

Những tên class, attribute, queue size, blocking và failover có semantics của Log4j 2; không mang nguyên các thẻ `<discardingThreshold>` hay `<neverBlock>` của Logback vào XML Log4j 2.

### 14.3. Log4j 2 AsyncLogger

Log4j 2 còn có **AsyncLogger**, một hướng kiến trúc khác với việc chỉ bọc appender. Async logger có thể dựa trên hệ thống ring buffer/Disruptor và yêu cầu cấu hình/dependency thích hợp theo version. Cần phân biệt:

- AsyncAppender: logger phát event vào appender async, nơi đó chuyển xuống appender đích.
- AsyncLogger: phần xử lý logging bất đồng bộ được tích hợp ở cấp logger/context theo kiến trúc riêng.

Không mặc định “AsyncLogger luôn nhanh hơn AsyncAppender”; cần đo cả workload, contention, format, sink, garbage, queue/ring buffer và chính sách quá tải.

### 14.4. JUL Handler

`java.util.logging` có `Handler`, `ConsoleHandler`, `FileHandler`, `MemoryHandler` và khả năng tự viết handler. **JUL chuẩn không cung cấp một generic AsyncAppender với cùng API/cấu hình như Logback**. Có thể tạo handler dùng queue/worker hoặc dùng thư viện/bridge để tận dụng backend async.

`MemoryHandler` của JUL giữ record trong bộ nhớ và đẩy tới handler đích khi có điều kiện; nó **không phải thay thế trực tiếp** cho worker queue async appender có producer/consumer riêng. Việc dùng tên “memory” không tạo ra non-blocking semantics.

## 15. Bảo mật khi logging bất đồng bộ

Async logging không tự xóa dữ liệu nhạy cảm. Password, access token, API key, session cookie, thông tin thẻ, email hoặc payload có thể tồn tại trong message, exception, arguments hay MDC.

Vì queue giữ event trong RAM cho tới khi worker ghi, dữ liệu nhạy cảm cũng có thể tồn tại trong **bộ nhớ chờ**, bên cạnh file/collector khi đã xuất. Không đưa dữ liệu nhạy cảm vào log, kiểm soát nơi gửi, quyền truy cập và retention.

Dữ liệu từ người dùng có thể chứa newline/control characters; placeholder `{}` không phải cơ chế escape chống log injection. Nếu xuất JSON, dùng encoder/serializer chuẩn để escape đúng. Với các bản ghi bắt buộc của hệ thống an ninh hoặc kiểm toán, quy định riêng về tính toàn vẹn, durability và truy vết; đừng phụ thuộc vào queue async in-memory mà không có đánh giá rủi ro.

Một điểm khác: khi queue đầy và `neverBlock=true`, even ERROR có thể bị bỏ. Với sự kiện cần chứng cứ bảo mật, phải bảo đảm đường đi riêng đáp ứng mức độ bền vững, không chỉ đặt level cao.

## 16. Kiểm thử thực tế trước khi bật production

### 16.1. Test khi tải bình thường

Phát một số lượng event kiểm soát, kiểm tra message, exception, MDC, stdout/file, level và thứ tự trong tình huống một producer. Với ví dụ ở mục 6, sau `context.stop()` kỳ vọng đủ ba event đã được enqueue.

### 16.2. Test burst làm queue đầy

Tạo tải lớn hơn tốc độ xử lý sink trong môi trường test, dùng queue nhỏ và một appender đích chậm có kiểm soát. Đo số event tạo, số event được ghi, producer latency và thời gian queue phục hồi.

Kỳ vọng **không nên là output cố định** vì thread scheduling phụ thuộc máy, hệ điều hành và sink. Mục tiêu là xác minh chính sách chặn/drop đúng như thiết kế và thu được telemetry cần thiết.

### 16.3. Test shutdown hợp lệ và shutdown cưỡng bức

Với backlog chưa rút hết, so sánh:

- `context.stop()` theo lifecycle bình thường.
- Shutdown với thời gian chờ ngắn hơn backlog cần xử lý.
- Process bị terminate cưỡng bức hoặc container hết grace period.

Đừng kích hoạt thử nghiệm crash trên hệ thống production nếu không có kế hoạch an toàn. Kiểm tra mất log và báo cáo risk acceptance cho từng loại sự kiện.

### 16.4. Test context và exception

- Bật `%X{requestId}` trong pattern khi ứng dụng đã gắn MDC; bảo đảm đúng ID ở các event dù worker ghi sau.
- Kiểm tra không có context rò giữa request threads.
- Ghi một exception thật sự, xác minh stack trace/cause được encoder xuất.
- Đánh giá `includeCallerData=true` nếu cần class/method/line; đo overhead.

### 16.5. Test downstream lỗi

Dùng đích ghi bị chậm, lỗi ghi hoặc tạm mất kết nối (ở môi trường test). Xác minh appender xử lý lỗi thế nào, có queue backlog/drop, có đưa lỗi ra status/metrics và có khiến request threads bị chặn không.

**Lưu ý:** không phải mọi backend đưa trực tiếp counter discarded events ra cùng một API. Có thể cần status listener, monitoring hook, appender wrapper hoặc metrics integration phù hợp phiên bản.

## 17. Troubleshooting: không thấy log hoặc ứng dụng chậm sau khi bật async

| Hiện tượng | Nguyên nhân cần xem | Cách xác minh/khắc phục |
|---|---|---|
| INFO/DEBUG biến mất khi tải lớn | Discarding threshold đang ưu tiên WARN/ERROR | Kiểm tra chính sách discard và queue pressure |
| Kể cả ERROR biến mất | Queue đầy + `neverBlock=true`, crash hoặc sink lỗi | Kiểm tra drop policy, stop, downstream và risk level |
| Request chậm dù đã bật async | Queue đầy làm producer block, hoặc việc chuẩn bị event quá nặng | Đo queue depth, p99, caller data, arguments và sink throughput |
| Shutdown quá lâu | `maxFlushTime=0` đợi vô hạn, sink chậm/hung | Xem graceful timeout và đặt policy phù hợp |
| Log mất lúc dừng | Chưa stop/flush, timeout ngắn hoặc terminate cưỡng bức | Thiết kế lifecycle và kiểm tra backlog |
| Log trùng hai lần | Root gắn cả `ASYNC` và `CONSOLE`, additivity khác | Kiểm tra toàn bộ graph appenders |
| Không có `requestId` | MDC không được gán trước log, context không truyền qua task | Kiểm tra gắn và dọn MDC trong business thread |
| Caller class/line sai hoặc thiếu | Caller data không được capture ở producer | Kiểm tra pattern và `includeCallerData` |
| Thứ tự log lạ | Nhiều producer/queue/worker/collector | Dựa thêm timestamp, traceId và sequence theo nghiệp vụ |
| Stack trace bị thiếu | Chỉ log `error.getMessage()` hoặc encoder bỏ Throwable | Truyền Throwable và kiểm tra layout |
| JSON không parse được | Tự nối chuỗi, message chứa ký tự đặc biệt | Dùng structured encoder/serializer |
| Không thấy DEBUG | Effective logger level/filter loại trước queue | Kiểm tra level và appender filter |
| Heap tăng đột biến | Queue lớn, event/Throwable/payload giữ nhiều memory | Đo allocations, giảm payload và cân lại queue |
| Log không tới collector dù stdout có | Agent/collector sau appender lỗi | Kiểm tra pipeline và delivery end-to-end |

## 18. Checklist thiết kế và vận hành

Trước khi chọn async appender, hãy trả lời:

1. **Bottleneck thật nằm ở đâu?** Logging I/O, encode JSON, flush file, network hay CPU xử lý nghiệp vụ?
2. **Mức độ ưu tiên là gì?** Giảm p99 latency hay giữ lại nhiều event nhất trong mọi tải?
3. **Queue hữu hạn bao nhiêu?** Có tính đến memory footprint của event và thời gian drain khi shutdown?
4. **Khi đầy sẽ làm gì?** Block, drop theo level, drop tất cả khi `neverBlock`, sample hay dùng cơ chế durable khác?
5. **Cấu hình nào được triển khai?** `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, `includeCallerData` có được hiểu đúng?
6. **Appender đích là gì?** Console, rolling file, socket/collector; có thêm điểm buffer hoặc mất log ngoài queue không?
7. **Log có bị ghi trùng?** Chỉ gắn `ASYNC` tại root khi nó đã bọc `CONSOLE`; kiểm tra additivity.
8. **Đã bảo toàn ngữ cảnh chưa?** MDC, traceId, thread name, exception; caller data có cần không?
9. **Có cơ chế shutdown hợp lệ không?** Ai stop logging context, grace period, flush timeout và cách báo backlog chưa xử lý?
10. **Đã kiểm thử quá tải và lỗi downstream chưa?** Không suy từ demo queue ba event ra độ tin cậy production.
11. **Có nguy cơ chứa bí mật không?** Message/Throwable/MDC và retention phải được kiểm soát cả trong RAM và ở sink.
12. **Có telemetry và ngưỡng cảnh báo không?** Queue depth, dropped event, sink failure, request latency và collector lag.
13. **Có yêu cầu audit/durability cao không?** Nếu có, dùng kiến trúc bền vững, không coi queue in-memory là nguồn dữ liệu duy nhất.

## 19. Kết luận

**Appender bất đồng bộ** tách thread phát log khỏi phần lớn công việc ghi log bằng một hàng đợi và worker riêng. Nó có thể cải thiện độ trễ request khi I/O logging chậm, nhưng đánh đổi bằng **backlog, sử dụng bộ nhớ, khả năng chặn hoặc bỏ sự kiện khi quá tải và rủi ro mất bản ghi khi shutdown/crash**.

Trong Logback, `AsyncAppender` phù hợp khi đã hiểu `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, dữ liệu MDC/caller và appender đích. Trong Log4j 2, cần phân biệt `AsyncAppender` với `AsyncLogger`; với JUL, không mặc định có cùng một async appender built-in. Hãy đo và kiểm thử toàn bộ pipeline thay vì chỉ bật async rồi giả định mọi log sẽ đến nơi an toàn.
