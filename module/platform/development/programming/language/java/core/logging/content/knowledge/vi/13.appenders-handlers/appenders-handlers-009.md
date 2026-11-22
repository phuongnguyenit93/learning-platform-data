# Appender theo level trong Java Logging

## 1. Appender theo level là gì?

**Appender theo level** là cách cấu hình để một đích ghi log chỉ nhận các sự kiện có mức nghiêm trọng nhất định. Trong một hệ thống Java, ta có thể muốn:

- `INFO` đi vào luồng log thông thường;
- `WARN` đi vào luồng cảnh báo;
- `ERROR` đi vào kênh điều tra lỗi;
- hoặc gom **tất cả sự kiện từ `WARN` trở lên** vào một nơi chuyên theo dõi rủi ro.

Chẳng hạn ứng dụng ghi:

```text
INFO  event=order.created orderId=ord-17
WARN  event=inventory.low sku=sku-9
ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
```

Thay vì để mọi Appender đều xuất cả ba dòng, ta gắn **bộ lọc theo level riêng trên từng Appender**. Appender `INFO_ONLY` chỉ xử lý dòng INFO, `WARN_ONLY` chỉ xử lý WARN, còn `ERROR_ONLY` chỉ xử lý ERROR.

Trong hệ sinh thái Java cần phân biệt:

1. **`Logger` quyết định sự kiện có được tạo/tiếp nhận theo level hiệu lực hay không.**
2. **`Appender` quyết định bản ghi đã được Logger chấp nhận sẽ được ghi ở đâu và theo điều kiện nào.**
3. **`Filter` gắn trên Appender quyết định chỉ nhận level chính xác, level tối thiểu hoặc điều kiện phức tạp hơn.**
4. **`Encoder`/`Layout` quyết định biểu diễn của sự kiện**, không quyết định đường đi theo level.
5. **`additivity` điều khiển việc chuyển event lên Appender của Logger tổ tiên**, có thể làm log trùng nếu cấu hình không chủ ý.

Bài tập trung vào **Logback với SLF4J**, vì ở Logback có các lớp `LevelFilter` và `ThresholdFilter` đặc trưng. Cuối bài đối chiếu với `java.util.logging.Handler` và lưu ý khi dùng backend khác. Ví dụ Java dùng JDK 17, SLF4J và Logback Classic.

## 2. Vị trí của Appender trong logging pipeline

Một mô hình thường gặp:

```text
Code ứng dụng:
logger.info(...), logger.warn(...), logger.error(...)
                       |
                       v
                SLF4J API
                       |
                       v
               Logback Logger
                 Kiểm tra level
                       |
                       v
                 LoggingEvent
                       |
          +------------+------------+
          |            |            |
          v            v            v
      INFO_ONLY     WARN_ONLY    ERROR_ONLY
      LevelFilter   LevelFilter  LevelFilter
          |            |            |
          v            v            v
      Encoder      Encoder      Encoder
          |            |            |
          +--------- các đích ghi ------> stdout / file / collector
```

Mỗi Appender **có bộ lọc và encoder riêng**. Ngay cả khi các Appender cùng được tham chiếu ở root, việc lọc level sẽ được xét trên từng Appender khi nó nhận một sự kiện.

Ví dụ: Logger `com.example.payment` có level hiệu lực `INFO`. Một lệnh `logger.debug("...")` bị loại ở Logger; nó **không thể được một Appender cho DEBUG “cứu lại”**. Một lệnh `logger.error("...")` được Logger chấp nhận; các Appender có thể nhận sự kiện nhưng bộ lọc ở từng Appender quyết định có xuất hay không.

**Nguyên tắc vận hành:** muốn log xuất ở một đích, phải có **cả Logger chấp nhận sự kiện và Appender nhận sự kiện**. Đừng chỉ nhìn một trong hai cấu hình.

## 3. Hệ thống level của Logback

Trong Logback Classic, các level thông dụng tăng dần về mức nghiêm trọng:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

`ALL` và `OFF` là các giá trị cấu hình đặc biệt cho phép mọi mức hoặc chặn mọi mức, không phải event level thông thường của lời gọi `trace/debug/info/warn/error`.

Quy tắc lựa chọn cơ bản của Logger: một lời gọi ở level `L` được chấp nhận khi `L` có độ nghiêm trọng ít nhất bằng level hiệu lực của Logger. Ví dụ:

| Level hiệu lực của Logger | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| `TRACE` | Có | Có | Có | Có | Có |
| `DEBUG` | Không | Có | Có | Có | Có |
| `INFO` | Không | Không | Có | Có | Có |
| `WARN` | Không | Không | Không | Có | Có |
| `ERROR` | Không | Không | Không | Không | Có |
| `OFF` | Không | Không | Không | Không | Không |

Bảng này mô tả **chấp nhận ở Logger**, chưa xét Appender hoặc Filter. Level của Logger cha nơi gắn Appender **không phải phép lọc lại các event đã được Logger con chấp nhận**. Một Logger con được đặt DEBUG riêng có thể gửi bản ghi DEBUG tới Appender gắn ở root INFO; muốn chặn DEBUG tại Appender đó, phải có bộ lọc thích hợp.

Khi nhiều Logger có tên phân cấp, level không đặt trực tiếp thường kế thừa level hiệu lực từ ancestor phù hợp. `additivity=true` cho phép event được chuyển tới Appender của ancestor. Đây là hai cơ chế riêng biệt.

## 4. Hai nhu cầu khác nhau: “đúng một level” và “từ một level trở lên”

Đây là câu hỏi đầu tiên cần trả lời trước khi viết XML.

### 4.1. Chỉ nhận đúng một level: `LevelFilter`

Nếu mục tiêu là **INFO đúng nghĩa**, không nhận WARN hoặc ERROR, dùng `ch.qos.logback.classic.filter.LevelFilter`:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

Đây là **mảnh cấu hình bên trong một Appender Logback**; nó không phải một file `logback.xml` độc lập.

- `level=INFO`: so khớp bằng nhau với level của event.
- `onMatch=ACCEPT`: cho qua event INFO ngay tại filter này.
- `onMismatch=DENY`: loại mọi level khác.
- `WARN` và `ERROR` **không** được nhận, dù chúng nghiêm trọng hơn INFO.

Bạn có thể dùng `LevelFilter` cho `WARN`, `ERROR`, `DEBUG` theo cách tương tự. Muốn loại mọi mức trừ ERROR, đặt `level=ERROR`.

### 4.2. Nhận một mức tối thiểu và các mức cao hơn: `ThresholdFilter`

Nếu yêu cầu là **WARN trở lên**, dùng `ch.qos.logback.classic.filter.ThresholdFilter`:

```xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
```

Đây cũng là **mảnh cấu hình bên trong Appender**. Quy tắc của `ThresholdFilter`:

- Event thấp hơn WARN, ví dụ INFO hoặc DEBUG: `DENY`.
- Event từ WARN trở lên, ví dụ WARN và ERROR: `NEUTRAL` để các filter tiếp theo vẫn có thể đánh giá.
- Nếu không có filter khác chặn, Appender sẽ ghi các event WARN/ERROR đã vượt qua level của Logger.

**Không nhầm:** `ThresholdFilter(WARN)` **không** có nghĩa “chỉ WARN”. Nó bao gồm `ERROR` và các event có level cao hơn WARN trong hệ Logback.

### 4.3. Bảng so sánh

Giả sử Logger nguồn được đặt `TRACE` để mọi lời gọi thông dụng có thể vào bộ lọc:

| Event | `LevelFilter(INFO)` chỉ INFO | `LevelFilter(ERROR)` chỉ ERROR | `ThresholdFilter(WARN)` |
| --- | --- | --- | --- |
| TRACE | Loại | Loại | Loại |
| DEBUG | Loại | Loại | Loại |
| INFO | Nhận | Loại | Loại |
| WARN | Loại | Loại | Nhận |
| ERROR | Loại | Nhận | Nhận |

Bảng nói “Nhận” với điều kiện **không có filter khác chặn**. Trong thực tế, Appender có thể không xuất vì chưa start, sai đích I/O, hoặc các filter khác được cấu hình sau đó.

Một sai lầm điển hình: dùng `ThresholdFilter` với `INFO` cho file `info.log` rồi tưởng nó chỉ chứa INFO. Thực tế filter đó cho **INFO, WARN và ERROR** đi tiếp. Nếu bạn cần tách theo level chính xác, hãy dùng `LevelFilter`.

## 5. FilterReply: ACCEPT, DENY và NEUTRAL

Logback tổ chức các regular filter trên một Appender theo **thứ tự**. Mỗi filter có thể trả một trong ba kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| `DENY` | Loại event ngay tại Appender, không đánh giá tiếp các filter còn lại |
| `ACCEPT` | Chấp nhận ngay, dừng đánh giá các filter còn lại |
| `NEUTRAL` | Chưa quyết định, tiếp tục đánh giá các filter tiếp theo |

Nếu không có filter nào quyết định loại, Appender sẽ nhận event theo hành vi mặc định sau khi các điều kiện khác đã đạt.

Điều này quan trọng khi một Appender có **nhiều filter**. Nếu filter đầu tiên trả `ACCEPT`, filter sau sẽ không được hỏi, kể cả khi filter sau cần chặn một loại message hoặc áp điều kiện bổ sung.

Ví dụ nếu cần chỉ nhận INFO **nhưng còn phải đi qua filter an toàn khác**, có thể dùng:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>NEUTRAL</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

Khi event là INFO, bộ lọc này chưa chốt kết quả; filter phía sau vẫn có cơ hội xử lý. Khi event khác INFO, nó bị loại. Mẫu `ACCEPT/DENY` thích hợp cho **một filter duy nhất** và ví dụ độc lập, còn với chuỗi filter phải thiết kế thứ tự và kết quả rõ ràng.

Lưu ý: filter tại Appender chỉ kiểm soát **event đến Appender đó**; nó không thay thế các quy định bắt buộc về bảo mật dữ liệu ngay tại nơi tạo log.

## 6. Ví dụ phân tuyến theo level bằng nhiều Appender

Giả sử ứng dụng có các loại đích:

```text
                   Logger (INFO hoặc thấp hơn)
                              |
             +----------------+----------------+
             |                |                |
          INFO_ONLY        WARN_ONLY        ERROR_ONLY
        LevelFilter      LevelFilter      LevelFilter
          INFO            WARN             ERROR
             |                |                |
          Kênh INFO        Kênh WARN        Kênh ERROR
```

Một event ERROR chỉ vào `ERROR_ONLY`; nó không lọt vào `WARN_ONLY` nếu `WARN_ONLY` dùng `LevelFilter(WARN)`. Ngược lại, nếu `WARN_ONLY` chuyển thành `ThresholdFilter(WARN)`, một event ERROR sẽ xuất **ở cả WARN_PLUS lẫn ERROR_ONLY**. Đó có thể là chính sách cố ý (log lỗi đồng thời xuất ở kênh cảnh báo và kênh lỗi), nhưng nếu dùng cùng một đích thì rất dễ tạo các bản ghi trùng.

Có hai phong cách phân tuyến hợp lệ:

- **Các kênh loại trừ nhau:** INFO_ONLY, WARN_ONLY, ERROR_ONLY; mỗi event đúng một kênh tương ứng.
- **Các kênh lồng nhau:** APP_ALL nhận mọi event được Logger chấp nhận; ALERTS nhận WARN+; ERRORS nhận ERROR. Một lỗi có thể xuất tới ba đích vì đó là yêu cầu nghiệp vụ vận hành.

Không có quy tắc mọi event phải đi chính xác một Appender: số đích đúng phụ thuộc hợp đồng thu thập. Điều cần tránh là **trùng không chủ ý** do gắn một Appender nhiều lần, additivity, hoặc filter sai nghĩa.

## 7. Ví dụ Java 17 chạy được: INFO, WARN, ERROR đi ba kênh

Đây là **chương trình hoàn chỉnh** sử dụng SLF4J và Logback Classic. Ví dụ dùng **ba ConsoleAppender cùng ghi `System.out` chỉ để minh họa việc phân tuyến theo level bằng tiền tố `INFO_SINK`, `WARN_SINK`, `ERROR_SINK`**. Trong production, ba đích có thể là ba file/collector khác nhau, hoặc chỉ một đích JSON với field `level` để hệ thống tập trung tự phân luồng.

Chương trình thiết kế đầu ra xác định, không in timestamp hoặc thread; code phát sự kiện tuần tự. Cấu hình root `INFO` chặn DEBUG trước khi đến Appender. Bộ lọc `LevelFilter` trên mỗi Appender xử lý **đúng một level**.

### 7.1. Cấu trúc dự án

```text
level-appender-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          LevelAppenderDemo.java
      resources/
        logback.xml
```

### 7.2. File `settings.gradle`

```groovy
rootProject.name = 'level-appender-demo'
```

### 7.3. File `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LevelAppenderDemo'
}
```

Các phiên bản được pin để dễ tái lập bài thực hành; **không phải khẳng định phiên bản mới nhất**. Trong dự án thật nên dùng phiên bản backend đã được kiểm thử, cập nhật bản vá bảo mật và đồng bộ SLF4J API/provider. Chỉ giữ **một** provider SLF4J trên runtime classpath.

### 7.4. File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="INFO_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>INFO_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARN_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>WARN</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>WARN_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERROR_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>ERROR_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INFO_ONLY"/>
        <appender-ref ref="WARN_ONLY"/>
        <appender-ref ref="ERROR_ONLY"/>
    </root>
</configuration>
```

File ở trên là **XML hoàn chỉnh**; cần đặt đúng tên `logback.xml` trong `src/main/resources` để có mặt trên runtime classpath. Không thêm một root appender thứ tư khi muốn đầu ra demo chính xác. Các encoder gắn trực tiếp với từng ConsoleAppender.

Ba Appender đều nhận cơ hội xử lý mỗi event **được Logger chấp nhận**, nhưng mỗi Appender chỉ xuất khi filter của riêng nó chấp nhận level. Vì vậy mỗi sự kiện INFO/WARN/ERROR xuất đúng một dòng.

### 7.5. File `src/main/java/demo/LevelAppenderDemo.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LevelAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LevelAppenderDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=diagnostic.hidden");
        LOG.info("event=order.created orderId={}", "ord-17");
        LOG.warn("event=inventory.low sku={}", "sku-9");
        LOG.error("event=payment.failed errorCode={}", "UPSTREAM_TIMEOUT");
    }
}
```

Không có import thuộc `ch.qos.logback` trong Java source: **SLF4J là facade**, Logback được lựa chọn qua dependency runtime. `{}` là placeholder tham số hóa của SLF4J, khác `{0}` trong API JUL/`MessageFormat`.

### 7.6. Biên dịch và chạy

Từ thư mục `level-appender-demo`, dùng JDK 17 và Gradle tương thích Java 17:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, có thể thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows. Ví dụ không bao gồm Gradle Wrapper; cần có Gradle và quyền truy cập Maven Central khi tải dependency ban đầu.

**stdout chính xác của mã ứng dụng với cấu hình trên:**

```text
INFO_SINK INFO event=order.created orderId=ord-17
WARN_SINK WARN event=inventory.low sku=sku-9
ERROR_SINK ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
```

Giải thích từng trường hợp:

1. `LOG.debug(...)` bị root level `INFO` loại ngay tại Logger. Không Appender nào thấy `DEBUG`.
2. `LOG.info(...)` đi tới cả ba Appender; chỉ `INFO_ONLY` có `LevelFilter(INFO)` chấp nhận.
3. `LOG.warn(...)` chỉ được `WARN_ONLY` chấp nhận vì đây là **khớp chính xác WARN**, không phải WARN+.
4. `LOG.error(...)` chỉ được `ERROR_ONLY` chấp nhận. Appender WARN_ONLY không nhận ERROR vì `LevelFilter` so khớp chính xác.
5. `%level`, `%msg`, `%n` trong `logback.xml` là conversion pattern của Logback, không phải cú pháp tham số hóa thông điệp của SLF4J.
6. Không có timestamp, thread hoặc Logger name trong pattern của demo, nên output trên không phụ thuộc đồng hồ hay tên thread. Thông báo tải dependency của Gradle hoặc warning từ công cụ build, nếu có, không phải stdout do chương trình này định nghĩa.

### 7.7. Thử thay đổi một điều kiện

**Thí nghiệm A:** đổi root từ `INFO` thành `DEBUG`. Khi đó lời gọi DEBUG được Logger chấp nhận, **nhưng không có Appender DEBUG_ONLY** trong XML nên nó vẫn không xuất. Điều này cho thấy **Logger chấp nhận event chưa đủ** để bắt buộc có đầu ra.

**Thí nghiệm B:** thay `WARN_ONLY` bằng `ThresholdFilter(WARN)` nhưng giữ `ERROR_ONLY`. Kết quả về mặt logic: event WARN xuất tại WARN_SINK; event ERROR xuất ở **cả WARN_SINK và ERROR_SINK**. Nếu cả hai là cùng stdout, sẽ thấy hai dòng cho một event ERROR. Điều này có thể đúng khi cần đồng thời hai kênh, nhưng là trùng không mong muốn nếu bạn định tách riêng.

**Thí nghiệm C:** giữ `LevelFilter(WARN)` nhưng đổi root thành `ERROR`. Khi ấy WARN bị loại ở Logger và Appender `WARN_ONLY` không thể khôi phục nó. Chỉ ERROR vẫn được gửi đi và nhận ở ERROR_ONLY.

## 8. Ví dụ khác: Appender chỉ nhận WARN và ERROR

Khi một công cụ giám sát cần kênh ALERTS chứa tất cả sự kiện `WARN` hoặc cao hơn, `ThresholdFilter` ngắn gọn hơn nhiều `LevelFilter` ghép lại:

```xml
<appender name="ALERTS" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.err</target>
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>
    <encoder>
        <pattern>ALERTS %level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Đây là **mảnh cấu hình Appender**, phải đặt trong `<configuration>` và được tham chiếu bởi Logger/root. Nếu gắn appender này cùng một Appender `ALL_EVENTS`, WARN/ERROR có thể xuất ở cả hai; không nhất thiết là lỗi, nếu ALL_EVENTS là log tổng và ALERTS là kênh cảnh báo.

Tương tự, muốn một file lưu từ `ERROR` trở lên, có thể dùng `ThresholdFilter(ERROR)`. Với các level phổ biến, kết quả tương đương chỉ ERROR; nhưng `LevelFilter(ERROR)` thể hiện rõ hơn yêu cầu **khớp chính xác**.

## 9. Appender theo level và phân tách file

Một thiết kế file log có thể là:

```text
logs/
  application.log   -> INFO, WARN, ERROR (nếu Logger chấp nhận)
  warnings.log      -> WARN, ERROR
  errors.log        -> ERROR
```

Trong trường hợp này:

- `APPLICATION`: Appender chung; nếu không có Filter, nhận các event đã qua Logger/đường chuyển tiếp.
- `WARNINGS`: Appender với `ThresholdFilter(WARN)`.
- `ERRORS`: Appender với `LevelFilter(ERROR)` hoặc `ThresholdFilter(ERROR)`.

**Hệ quả rõ ràng:** một sự kiện ERROR xuất trong ba file. Đây không phải “lỗi trùng” nếu mỗi file phục vụ mục đích khác nhau, nhưng tăng dung lượng và chi phí ingest. Khi collector đọc đồng thời cả ba file như ba nguồn sự kiện độc lập, hệ thống tập trung có thể **đếm một lỗi thành ba** nếu không thiết kế chống trùng. Hãy quyết định có thực sự cần nhiều file hay chỉ một JSON stream với trường level.

Khi dùng `RollingFileAppender`, Appender quản lý luân phiên và lịch sử file theo rolling policy, còn Filter theo level quyết định event nào vào file đó. Không dùng nhiều FileAppender độc lập ghi **cùng một file path** nếu không có thiết kế hỗ trợ ghi đồng thời; có thể gây xung đột file, lặp nội dung hoặc lỗi rollover.

Trong Docker/Kubernetes, thường nên xuất log ra stdout/stderr và để tầng nền tảng/collector đảm nhiệm việc thu gom, lưu trữ và phân luồng theo field `level`. Cấu hình mỗi mức severity thành một file cục bộ không phải luôn là lựa chọn tốt nhất.

## 10. Appender, logger hierarchy và additivity

Giả sử một Appender `ERROR_ONLY` được gắn ở root. Logger con `com.example.payment` mặc định có additivity, nên event ERROR của logger con (nếu được chấp nhận) có thể truyền lên Appender của root.

```text
root logger [INFO] -> ERROR_ONLY
    |
    +-- com.example [INHERITED]
         |
         +-- com.example.payment [DEBUG, additivity=true]
```

`com.example.payment` cho phép DEBUG/INFO/WARN/ERROR theo level riêng, nhưng Appender `ERROR_ONLY` tại root vẫn chỉ xuất ERROR. **Root đặt INFO không chặn lại DEBUG do logger con DEBUG phát**, nếu Appender tại root không có Filter thích hợp; chính bộ lọc của Appender là nơi kiểm soát đầu ra.

Nếu gắn `ERROR_ONLY` vào cả Logger con và root mà vẫn để additivity, **cùng một event ERROR có thể được Appender gọi hai lần** và xuất trùng. Để tránh:

- Chỉ gắn Appender dùng chung ở một vị trí trong cây Logger.
- Hoặc đặt `additivity="false"` ở Logger con khi nhánh đó có Appender riêng và thực sự không cần chuyển lên ancestor.
- Không tắt additivity một cách mù quáng: nếu Logger con không có Appender riêng, event có thể không còn đích xuất.

Ví dụ **mảnh cấu hình** trong một file `logback.xml`:

```xml
<logger name="com.example.payment" level="DEBUG" additivity="false">
    <appender-ref ref="PAYMENT_ERROR"/>
</logger>
```

Ở đây `PAYMENT_ERROR` phải là Appender đã được khai báo. Nếu chỉ có bộ lọc ERROR trong Appender, các event INFO/WARN do Logger con chấp nhận sẽ không in ra đâu trong nhánh này khi không có các Appender tương ứng. Vì vậy phải thiết kế **đầy đủ đường đi cho mọi level cần lưu**, không chỉ giải quyết trùng một level.

## 11. So sánh với java.util.logging Handler

Khi dùng **JUL (`java.util.logging`)** thay Logback, thuật ngữ phía đích là `Handler`. `Handler.setLevel(Level.WARNING)` đặt **ngưỡng tối thiểu** của Handler: nó chấp nhận WARNING và các mức nghiêm trọng hơn, nếu không có Filter khác chặn.

Ví dụ **mảnh mã minh họa**:

```java
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setLevel(java.util.logging.Level.WARNING);
```

Trong JUL, `WARNING` gần với khái niệm WARN của Logback, `SEVERE` gần với ERROR, nhưng hệ thống level và cách cấu hình **không giống nhau hoàn toàn**. Đừng bê nguyên XML `LevelFilter`/ `ThresholdFilter` của Logback sang `java.util.logging` hoặc giả định `Handler.setLevel(WARNING)` là “chỉ WARNING”.

Nếu muốn **chỉ đúng WARNING** ở Handler JUL, có thể kết hợp level và `Filter`:

```java
handler.setLevel(java.util.logging.Level.WARNING);
handler.setFilter(record ->
        record.getLevel().equals(java.util.logging.Level.WARNING));
```

Đây là **mảnh mã** gắn với `handler` đã khai báo; cần thêm Handler vào Logger hoặc LogManager phù hợp để log xuất hiện. Nó lọc đúng đối tượng `Level.WARNING`; nếu dự án dùng custom levels có cùng/severity tương đương, cần xác định rõ quy tắc so khớp.

Trong JUL, `Logger.setLevel(null)` nghĩa là kế thừa level hiệu lực từ parent, còn `setUseParentHandlers(false)` ngắt việc chuyển event tới Handler của parent. Chúng là các khái niệm gần với phần level inheritance/additivity của Logback nhưng **khác API và cấu hình**. Khi chạy SLF4J với Logback, không cấu hình Handler JUL rồi kỳ vọng nó điều khiển Appender Logback.

## 12. Filter theo level không phải giải pháp cho mọi loại routing

Bộ lọc level phù hợp để quyết định severity, nhưng đôi khi bài toán thực tế muốn:

- Chỉ gửi **ERROR của module thanh toán** tới kênh cảnh báo.
- Chỉ gửi event có `marker=AUDIT` hoặc `errorCode` thuộc nhóm quan trọng.
- Tách log theo `tenantId` an toàn hoặc `jobId`.
- Loại sự kiện chứa dữ liệu cần bảo vệ hoặc thuộc nguồn test không có giá trị.
- Bật sample/rate limit khi khối lượng log quá lớn.

Các nhu cầu này **không được giải quyết đầy đủ chỉ bằng `ThresholdFilter`**. Cần cân nhắc logger hierarchy, `EvaluatorFilter`, TurboFilter, marker, MDC, hoặc hệ thống collector/router chuyên dụng. Với Logback, các regular filter được gắn trên Appender; TurboFilter có vai trò khác ở tầng logging context. Cấu hình nâng cao cần được xác minh theo phiên bản Logback đang dùng.

Đặc biệt với dữ liệu nhạy cảm, **phải hạn chế ngay từ lúc tạo message/field**, không chỉ kỳ vọng một filter ở đích sẽ che mọi secret đã đưa vào log. Các exception message hoặc `toString()` có thể chứa token, cookie hoặc payload mà filter theo level không thể nhận biết.

## 13. Hiệu năng và khả năng mất log

Chia sự kiện theo level có thể giảm volume ở một số đích, nhưng không miễn phí:

1. **Logger vẫn phải xét level** trước khi event đến Appender.
2. Với mỗi event đã qua Logger, **mỗi Appender được tham chiếu** có thể đánh giá filter của nó.
3. Tạo nhiều Appender có thể tăng chi phí quản lý, encoder, I/O và cấu hình.
4. Nếu một event đi tới nhiều đích, tổng volume và chi phí ingest có thể tăng.
5. Với `AsyncAppender`, hàng đợi và chính sách discard/blocking có thể khiến một số event bị mất hoặc làm chậm thread phát log; không mặc định filter theo level sẽ bảo đảm lưu mọi WARN/ERROR.
6. Khi tiến trình crash hoặc filesystem đầy, một event vượt filter chưa chắc đã được ghi bền vững.

Nếu phải giảm chi phí INFO, không nên chỉ chuyển INFO sang một file khác rồi collector vẫn thu cả hai file. Hãy đặt chính sách logger/filter/collector tương thích mục tiêu. Đồng thời không vô tình loại toàn bộ WARN/ERROR phục vụ điều tra sự cố.

Đối với audit cần bền vững và đối soát giao dịch, một Appender thông thường không thay thế giải pháp lưu trữ có cam kết, phân quyền và chính sách chống sửa đổi.

## 14. Chẩn đoán lỗi khi Appender theo level không hoạt động

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Appender INFO không có log INFO | Logger đang ở WARN/ERROR, hoặc appender không được tham chiếu | Kiểm tra effective Logger level, `appender-ref`, filter |
| Appender INFO lại có ERROR | Dùng `ThresholdFilter(INFO)` thay vì `LevelFilter(INFO)` | Đổi sang LevelFilter khi muốn đúng INFO |
| Appender WARN nhận cả ERROR | Dùng `ThresholdFilter(WARN)` | Đây là hành vi dự kiến; nếu chỉ WARN thì dùng LevelFilter |
| Đã khai báo ERROR_ONLY nhưng không có ERROR | Logger tắt, filter khác chặn, cấu hình appender chưa active, I/O lỗi | Kiểm tra Logger, filter chain, appender lifecycle và đích |
| DEBUG không xuất dù có DEBUG_ONLY | Root hoặc Logger hiệu lực vẫn ở INFO | Bật DEBUG ở Logger nguồn, rồi kiểm tra Appender |
| Một event ERROR có hai dòng giống nhau | Hai Appender cùng đích, additivity hoặc tham chiếu trùng | Vẽ đường chuyển event, kiểm tra filter và target |
| Cùng appender xử lý quá nhiều message | Gắn appender ở root cho toàn bộ package | Tách logger hierarchy hoặc filter theo module/marker |
| Thêm filter khác nhưng không có hiệu lực | Filter đầu trả ACCEPT, chặn việc xét các filter sau | Kiểm tra thứ tự và `ACCEPT/NEUTRAL/DENY` |
| File trống khi dùng RollingFileAppender | Thiếu quyền ghi, appender không start, chưa đủ event hoặc rolling policy lỗi | Xem status nội bộ Logback, path, quyền ghi |
| Log bị gửi sai đích sau khi đổi framework | Runtime backend không phải Logback | Xác nhận SLF4J provider, starter và file config phù hợp |
| Log chỉ mất khi tải cao | Queue async, discard, backpressure hoặc collector quá tải | Kiểm tra queue, drop counter, shutdown và băng thông |

### Quy trình kiểm tra theo thứ tự

1. Xác định **backend thực sự hoạt động** (Logback hay JUL/Log4j 2).
2. Kiểm tra lời gọi log có chạy và **Logger hiệu lực có cho phép level**.
3. Kiểm tra event có đường tới Appender qua `appender-ref` và additivity.
4. Kiểm tra Filter: **exact-level hay threshold**, thứ tự `ACCEPT/NEUTRAL/DENY`.
5. Kiểm tra Appender đã start, encoder có hợp lệ, đích stdout/stderr/file/collector có hoạt động.
6. Chạy thử INFO, WARN, ERROR tách biệt; sau đó thử DEBUG và trường hợp có nhiều Appender.
7. Kiểm tra mô hình có trùng/mất log, được giám sát và chịu được tải.

Không thay quá nhiều thiết lập cùng lúc; ghi nhận input, log được mong đợi và output thực tế cho từng level để phát hiện chính xác tầng đang loại event.

## 15. Checklist áp dụng cho dự án

- [ ] Hiểu rõ yêu cầu là **một level chính xác** hay **từ một ngưỡng trở lên**.
- [ ] Dùng `LevelFilter` cho trường hợp chỉ INFO/WARN/ERROR; dùng `ThresholdFilter` cho WARN+ hoặc ERROR+.
- [ ] Xác nhận Logger hiệu lực chấp nhận những event dự kiến gửi Appender.
- [ ] Kiểm tra thứ tự các filter và phân biệt `DENY`, `NEUTRAL`, `ACCEPT`.
- [ ] Các Appender có `encoder` và `target` đúng, được tham chiếu bởi Logger/root.
- [ ] Không tham chiếu Appender ở nhiều tầng Logger nếu gây trùng không chủ ý.
- [ ] Nếu `additivity=false`, Logger con vẫn có đích phù hợp cho các level cần giữ.
- [ ] Phân biệt Logback Appender và JUL Handler; không pha trộn API/config một cách máy móc.
- [ ] Tránh ghi một event vào nhiều file trừ khi có lý do vận hành và quản lý chi phí rõ.
- [ ] Với container, cân nhắc xuất một stream có field severity thay vì nhiều file cục bộ.
- [ ] Kiểm tra INFO/WARN/ERROR, log bị loại, lỗi I/O và tình huống async dưới tải.
- [ ] Bảo vệ secret, giới hạn dữ liệu nhạy cảm và kiểm soát retention/collector.

### Tham khảo kỹ thuật

- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html): quy tắc `LevelFilter`, `ThresholdFilter` và thứ tự quyết định.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration-xml.html): Logger hierarchy, appender-ref và additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): vòng đời Appender, filter và encoder.
- [Java Platform — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): Handler level/filter trong JUL.

**Kết luận:** **Appender theo level** cho phép định tuyến sự kiện đã được Logger chấp nhận tới các đích khác nhau. Trong Logback, `LevelFilter` so khớp **chính xác một level**, còn `ThresholdFilter` cho qua **từ ngưỡng trở lên**. Kết hợp đúng Logger level, filter, additivity và đích xuất giúp tránh mất log, tránh trùng log và đảm bảo severity quan trọng đến đúng kênh giám sát.
