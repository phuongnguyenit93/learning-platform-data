# Rotation theo thời gian trong Java Logging

## 1. Khái niệm và mục đích

**Time-based log rotation** là cơ chế luân chuyển file log theo kỳ thời gian như giờ, ngày, tuần hoặc tháng. Thay vì để một file tăng vô hạn, backend chuyển dữ liệu của kỳ trước sang file lịch sử (archive), có thể nén, rồi tiếp tục ghi vào file hiện tại.

Ví dụ một dịch vụ ghi log theo ngày:

```text
logs/
├── application.log                   # File hiện hành
└── archive/
    ├── application.2026-11-07.log.gz
    ├── application.2026-11-08.log.gz
    └── application.2026-11-09.log.gz
```

Tên file và ngày trong sơ đồ là **minh họa**, không phải file chắc chắn có trong mọi lần chạy. Một cấu hình Logback thường giữ tên file hoạt động cố định, chẳng hạn `application.log`, trong khi các archive mang tên của kỳ thời gian đã hoàn tất.

Các mục tiêu phổ biến:

- Chia nhỏ log giúp tìm kiếm và chẩn đoán theo ngày/giờ.
- Hỗ trợ công cụ thu thập đọc file và chuyển log về hệ thống tập trung.
- Nén những file cũ để giảm dung lượng lưu trữ.
- Áp dụng chính sách **retention** và giới hạn tổng dung lượng.
- Tránh một file hoạt động tồn tại mãi và trở nên quá lớn.

**Cần phân biệt ba việc khác nhau:**

1. **Trigger:** khi nào một sự kiện log khiến appender quyết định cần rollover?
2. **Rollover:** đổi tên, chuyển file, mở file mới và nén archive ra sao?
3. **Retention/cleanup:** giữ file lịch sử bao lâu và khi nào xóa?

Đặt ngày vào tên file **không tự bảo đảm** file được xoay đúng thời điểm, được nén, có giới hạn kích thước hoặc được giữ đúng số ngày.

## 2. Rotation theo thời gian khác rotation theo dung lượng như thế nào?

| Chiến lược | Điều kiện thường dùng | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Time-based** | Sang kỳ giờ/ngày/tháng tiếp theo | Archive dễ xác định theo kỳ | Một kỳ tải cao có thể tạo file rất lớn |
| **Size-based** | File vượt ngưỡng dung lượng | Giới hạn kích thước file tốt hơn | Không tự nhóm file theo ngày |
| **Size-and-time-based** | Sang kỳ mới **hoặc** đạt ngưỡng file | Vừa nhóm theo kỳ vừa chia nhỏ tải cao | Có thể có nhiều archive cùng ngày |
| **External rotation** | Công cụ OS/scheduler/collector | Phù hợp pipeline có chính sách chung | Có thể xung đột file handle của appender trong JVM |

Ví dụ, bình thường dịch vụ tạo 50 MB log mỗi ngày nhưng ngày có sự cố tạo 4 GB. Nếu chỉ xoay theo ngày, file trong ngày có thể rất lớn. Khi yêu cầu vừa có **tên theo ngày** vừa tránh file lớn, có thể dùng Logback `SizeAndTimeBasedRollingPolicy`.

Nếu ứng dụng chỉ ghi vài KB/ngày, time-based thuần thường đủ và đơn giản hơn.

### Rotation không phải retention

- Rotation tạo **file lịch sử** hoặc chuyển sang file mới.
- Compression nén file lịch sử.
- Retention quyết định file lịch sử tồn tại bao lâu hoặc tổng dung lượng được phép.
- Archiving có thể chuyển lịch sử tới kho khác, nhưng không tự có trong mọi rolling policy.

Một cấu hình có rotation nhưng **không có retention** vẫn có thể làm ổ đĩa đầy sau thời gian dài.

## 3. Rollover theo thời gian diễn ra lúc nào?

Giả sử policy xoay theo ngày UTC và ứng dụng ghi:

```text
2026-11-09T23:59:58Z INFO event=order_received
2026-11-09T23:59:59Z INFO event=order_confirmed
2026-11-10T00:00:03Z WARN event=retry_scheduled
```

Trong một cấu hình phổ biến có file hiện hành cố định:

```text
Trước ngày mới:
  logs/application.log
      chứa dữ liệu của kỳ 2026-11-09

Khi xử lý log đầu tiên thuộc kỳ 2026-11-10:
  rollover logs/application.log
      -> logs/archive/application.2026-11-09.log.gz
  tiếp tục logs/application.log cho kỳ mới
      -> ghi event=retry_scheduled
```

**Điểm dễ hiểu sai:** nhiều rolling appender thực hiện rollover **khi có sự kiện log đầu tiên sau ranh giới kỳ**, không có nghĩa chắc chắn 00:00 sẽ lập tức xuất hiện file nén.

Ví dụ, service không ghi gì từ 23:50 hôm trước đến 08:00 hôm sau thì rollover có thể diễn ra khi log ở 08:00 được xử lý. Việc nén/cleanup còn có thể được thực thi theo lịch nội bộ hoặc bất đồng bộ tùy backend/version.

Do đó, đừng viết kiểm thử yêu cầu đúng 00:00 phải có archive nếu policy được thiết kế dựa trên sự kiện. Nếu một hệ thống thật sự cần đóng file **theo lịch độc lập với lưu lượng log**, cần giải pháp có khả năng scheduling và phối hợp file handle phù hợp.

## 4. Múi giờ quyết định ranh giới của kỳ

Cùng một thời điểm nhưng ngày UTC và ngày địa phương có thể khác nhau:

```text
2026-11-09T16:59:59Z = 2026-11-09 23:59:59 Asia/Ho_Chi_Minh
2026-11-09T17:00:00Z = 2026-11-10 00:00:00 Asia/Ho_Chi_Minh
```

Nếu xoay theo **ngày Việt Nam**, boundary trong ví dụ ở 17:00 UTC; nếu xoay theo **ngày UTC**, boundary vào 00:00 UTC.

| Lựa chọn | Phù hợp | Cần kiểm tra |
|---|---|---|
| UTC | Hệ thống đa vùng, log tập trung | Người vận hành có thể tra cứu theo ngày địa phương khác |
| Múi giờ nghiệp vụ | Báo cáo/đối soát theo ngày địa phương | Mọi instance phải dùng cùng timezone |
| Timezone mặc định của JVM/server | Cấu hình nhanh | Có thể khác giữa IDE, máy chủ và container |

**Nên chọn timezone tường minh.** Chỉ thêm ngày vào `fileNamePattern` mà không kiểm tra timezone có thể khiến hai instance cùng ghi những ngày khác nhau theo tên file.

### 4.1. Chương trình Java 17 minh họa boundary, chạy không cần thư viện ngoài

Ví dụ sau dùng `Instant`, `ZoneId` và `LocalDate` để chứng minh hai ngày khác nhau. Nó **không tự tạo rolling file**; đây là bài kiểm chứng quy tắc thời gian trước khi chọn cấu hình logger.

Tạo file `RotationBoundaryDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public final class RotationBoundaryDemo {
    public static void main(String[] args) {
        Instant before = Instant.parse("2026-11-09T16:59:59Z");
        Instant after = Instant.parse("2026-11-09T17:00:00Z");

        ZoneId utc = ZoneOffset.UTC;
        ZoneId vn = ZoneId.of("Asia/Ho_Chi_Minh");

        display(before, utc, vn);
        display(after, utc, vn);
    }

    private static void display(
            Instant instant, ZoneId utc, ZoneId vn) {
        LocalDate utcDate = instant.atZone(utc).toLocalDate();
        LocalDate vnDate = instant.atZone(vn).toLocalDate();

        System.out.println("instant=" + instant
                + " UTC=" + utcDate
                + " VN=" + vnDate);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 RotationBoundaryDemo.java
java RotationBoundaryDemo
```

**Stdout chính xác:**

```text
instant=2026-11-09T16:59:59Z UTC=2026-11-09 VN=2026-11-09
instant=2026-11-09T17:00:00Z UTC=2026-11-09 VN=2026-11-10
```

Hai `Instant` nằm cạnh nhau một giây, nhưng ứng dụng xử lý ngày Việt Nam đã đổi ngày. Phần lớn hệ thống đa vùng chọn UTC cho lưu trữ/quan sát, rồi quy đổi khi hiển thị nghiệp vụ; nếu bắt buộc theo ngày địa phương, hãy tài liệu hóa rõ quy tắc.

### 4.2. Daylight saving time (DST)

Một số múi giờ thay đổi giờ mùa hè: ngày có thể dài 23 hoặc 25 giờ. Nếu xoay theo giờ địa phương, một nhãn giờ có thể bị bỏ qua hoặc lặp lại. Tên archive chỉ chứa ngày–giờ có thể khó phân biệt hai kỳ trùng nhãn.

Dùng UTC giúp tránh nhiều nhầm lẫn kiểu này. Nếu dùng timezone có DST, cần thử đúng ngày chuyển giờ, quy tắc đặt tên và hành vi backend; không giả định mọi ngày có 24 kỳ một giờ.

## 5. JUL FileHandler có hỗ trợ time-based rotation không?

`java.util.logging.FileHandler` (JUL) được JDK cung cấp sẵn, chủ yếu hỗ trợ xoay theo **kích thước** và **số lượng file**, không có sẵn bộ policy xoay theo ngày/giờ giống Logback hoặc Log4j 2.

Ví dụ JUL:

```java
import java.util.logging.FileHandler;
import java.util.logging.SimpleFormatter;

FileHandler handler = new FileHandler(
        "logs/application.%g.%u.log",
        10_000_000,
        5,
        true);
handler.setFormatter(new SimpleFormatter());
```

Đây chỉ là **fragment Java**, chưa có class, imports đầy đủ và chưa bảo đảm thư mục `logs` tồn tại. Tham số `10_000_000` là ngưỡng byte, `5` là số file generation; không có tham số “xoay lúc 00:00”.

Nếu hệ thống đang dùng JUL mà cần xoay theo ngày, có thể cân nhắc:

- Chuyển sang backend có time-based rolling, dùng bridge/adapter nếu muốn giữ API phát log.
- Dùng cơ chế external rotation có tương thích với cách JUL giữ file handle.
- Tự viết handler và cơ chế lịch với `flush`, `close`, reopen, lock và failure handling; cách này tốn công kiểm thử.

**Không nên chỉ dùng scheduled task đổi tên file trong lúc FileHandler vẫn mở rồi coi như đã thực hiện rotation an toàn.** Trên một số hệ điều hành, handle có thể tiếp tục ghi vào file cũ; trên hệ khác đổi tên có thể lỗi hoặc phát sinh xung đột.

## 6. Logback TimeBasedRollingPolicy theo ngày UTC

Trong ứng dụng dùng **SLF4J API + Logback Classic backend**, `RollingFileAppender` kết hợp `TimeBasedRollingPolicy` là cách phổ biến để xoay file theo kỳ thời gian.

Ví dụ file `logback.xml`:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Đây là cấu hình Logback (không phải JUL hay Log4j 2). Phần tử quan trọng:

| Thành phần | Vai trò |
|---|---|
| `<file>logs/application.log</file>` | Tên file hiện hành cố định |
| `fileNamePattern` chứa `%d{yyyy-MM-dd,UTC}` | Định danh kỳ xoay theo **ngày UTC** |
| Hậu tố `.gz` | Nén file lưu trữ dạng gzip |
| `maxHistory=7` | Số kỳ lịch sử được giữ theo chính sách của Logback |
| `totalSizeCap=100MB` | Giới hạn dung lượng lịch sử qua cleanup |
| `cleanHistoryOnStart=true` | Dọn lịch sử khi appender/policy khởi động nếu phù hợp |
| `root level="INFO"` | Chọn mức log được phát, độc lập với lịch xoay |
| `encoder` | Quyết định định dạng text trong file |

Cấu hình dùng `%d{yyyy-MM-dd,UTC}` trong `fileNamePattern` để xác định kỳ theo UTC. Với các pattern có nhiều thành phần thời gian, cần xác định token nào điều khiển chu kỳ theo quy tắc Logback; ở đây chỉ có một token ngày nên rõ ràng.

### 6.1. File đang ghi và file archive

Khi có `<file>`:

- Trong kỳ, event ghi vào `logs/application.log`.
- Khi có event đầu tiên thuộc kỳ mới, backend có thể thực hiện rollover file active trước đó.
- Archive được đặt theo **kỳ trước**; sau đó log kỳ mới tiếp tục ở `logs/application.log`.
- Nén có thể cần thời gian; file `.gz` không nhất thiết xuất hiện tức thì lúc đồng hồ qua ranh giới.

Nếu không khai báo `<file>`, một số cấu hình Logback dùng tên file đang ghi được suy từ `fileNamePattern`. Khi đó behavior và cách collector bám đường dẫn khác đi; không tự áp dụng các giả định của cấu hình có file active cố định.

### 6.2. TimeBasedRollingPolicy không phải SizeBasedRollingPolicy

`TimeBasedRollingPolicy` thuần điều khiển theo thời gian. Nếu một kỳ có 2 GB log, cấu hình này **không tự chia file đó thành nhiều file 20 MB**. Muốn kết hợp kích thước, dùng policy khác phù hợp.

### 6.3. Chú ý retention

`maxHistory=7` là số **kỳ lịch sử**, không phải cam kết “file bị xóa ngay vào giây thứ 604.800”. Cleanup thường gắn với rollover/startup và có thể thực thi bất đồng bộ.

`totalSizeCap` giới hạn dung lượng lịch sử trong phạm vi policy; nó không phải quota cứng của filesystem hay đảm bảo file active không vượt ngưỡng. `cleanHistoryOnStart` giúp xử lý lịch sử khi chương trình ít hoạt động, nhưng không biến policy thành dịch vụ xóa theo lịch từng giây.

## 7. Ví dụ Maven + Java 17 chạy được với Logback daily rolling

Ví dụ này tạo file log thực sự bằng Logback và in ra một dòng stdout ổn định để kiểm chứng. Chỉ dùng **một chương trình nhỏ**, nên lần chạy đầu không nhất thiết có archive nén: để rollover theo ngày, cần thật sự có sự kiện ở **hai kỳ thời gian khác nhau**.

### 7.1. Cấu trúc thư mục

```text
daily-rotation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/DailyRotationDemo.java
        └── resources/
            └── logback.xml
```

### 7.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>daily-rotation-demo</artifactId>
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
                    <mainClass>com.example.logging.DailyRotationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` đưa backend/provider của Logback vào runtime và sử dụng SLF4J API phù hợp. Các version ở đây chỉ là **giá trị ví dụ cố định**, không phải thông báo mới nhất hay lựa chọn bảo mật mặc định. Dự án thực tế cần theo dõi các phiên bản được hỗ trợ và advisories.

### 7.3. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Ở đây appender chỉ **ghi file**, không gắn console appender. Vì vậy các lời gọi `LOG.info` không tự xuất ra stdout.

### 7.4. Tệp `src/main/java/com/example/logging/DailyRotationDemo.java`

```java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class DailyRotationDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(DailyRotationDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started service={}", "orders-api");
        LOG.debug("event=debug_probe");
        LOG.warn("event=dependency_slow attempts={}", 2);
        LOG.info("event=app_completed");

        // Demo kết thúc: flush/close appender bằng lifecycle chính thức.
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        context.stop();

        System.out.println("demo=completed emitted=3");
    }
}
```

Trong ứng dụng server thật, framework thường quản lý lifecycle của `LoggerContext`. **Không dừng logger context sau mỗi request**; chỉ làm như vậy trong demo đang kết thúc.

### 7.5. Chạy và kiểm tra đầu ra

Với JDK 17+, Maven và quyền tải dependencies, từ thư mục `daily-rotation-demo` chạy:

```bash
mvn -q compile exec:java
```

**Stdout do code Java phát**:

```text
demo=completed emitted=3
```

Maven có thể ghi thông báo của riêng công cụ nếu môi trường khác, nhưng dòng trên là nội dung do chương trình in.

Nếu cấu hình được nạp đúng, process có quyền ghi, bắt đầu trong thư mục mới chưa có file log và không gặp lỗi I/O, nội dung `logs/application.log`:

```text
INFO DailyRotationDemo - event=app_started service=orders-api
WARN DailyRotationDemo - event=dependency_slow attempts=2
INFO DailyRotationDemo - event=app_completed
```

`DEBUG` bị lọc bởi root INFO. `%logger{0}` hiển thị tên lớp ngắn, không thay đổi logger name đầy đủ được lưu trong event.

**Không kỳ vọng thấy file archive sau chạy một lần trong vài giây.** Vì chưa sang kỳ UTC mới, backend không có lý do rollover. Nếu muốn kiểm thử rollover đúng, tạo test tích hợp có kiểm soát thời gian và sự kiện hai kỳ; tránh thay đổi đồng hồ hệ thống production để ép kết quả.

## 8. Rotation theo giờ, tháng và kỳ thời gian khác

Trong Logback, chu kỳ thường được suy từ độ chính xác của `%d` trong `fileNamePattern`.

### 8.1. File theo giờ

```xml
<fileNamePattern>logs/archive/application.%d{yyyy-MM-dd_HH,UTC}.log.gz</fileNamePattern>
```

Đây là **fragment** bên trong `TimeBasedRollingPolicy`, không phải cấu hình đầy đủ. Pattern có giờ `HH` nên kỳ xoay theo giờ; có thể hợp lý khi lưu lượng log hằng ngày rất cao.

### 8.2. File theo tháng

```xml
<fileNamePattern>logs/archive/application.%d{yyyy-MM,UTC}.log.gz</fileNamePattern>
```

Pattern chính xác tới tháng cho kỳ xoay theo tháng. Cần cân nhắc một file theo tháng có thể quá lớn. Với nhiều lưu lượng, kết hợp size trigger hoặc dùng kỳ ngắn hơn.

### 8.3. Không nhầm format tên file với timestamp trong log message

`fileNamePattern` định nghĩa kỳ và tên archive. `encoder.pattern` có thể chứa `%d{...}` để hiển thị timestamp của mỗi event. Hai vị trí có thể cần timezone giống nhau, nhưng không phải cùng một thuộc tính và không thay thế cho nhau.

Nếu một collector dùng file name làm phân vùng và timestamps trong message làm bộ lọc truy vấn, hãy chuẩn hóa timezone cùng format.

## 9. Kết hợp theo ngày và theo dung lượng

Nếu một ngày có thể tạo rất nhiều log, sử dụng `SizeAndTimeBasedRollingPolicy` của Logback:

```xml
<rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>500MB</totalSizeCap>
</rollingPolicy>
```

Đây là fragment dùng thay `rollingPolicy` trong `RollingFileAppender` phù hợp.

| Thành phần | Tác dụng |
|---|---|
| `%d` | Tách archive theo kỳ ngày UTC |
| `%i` | Số thứ tự của nhiều file trong cùng kỳ |
| `maxFileSize` | Thêm trigger theo dung lượng file |
| `maxHistory` | Giới hạn các kỳ lịch sử |
| `totalSizeCap` | Giới hạn tổng dung lượng lịch sử thông qua cleanup |

Ví dụ output archive có thể như sau:

```text
application.2026-11-09.0.log.gz
application.2026-11-09.1.log.gz
application.2026-11-09.2.log.gz
```

Những tên đó minh họa việc dùng `%i`, không phải cam kết có ba file khi chạy demo.

**Đừng nhầm** `%i` của Logback với `%g` trong JUL FileHandler. Mỗi backend có cú pháp riêng. Nếu chỉ cần daily rolling, `TimeBasedRollingPolicy` đơn giản hơn và ít thứ phải điều chỉnh.

## 10. Log4j 2: TimeBasedTriggeringPolicy trong RollingFile

Log4j 2 sử dụng `RollingFile` appender với `TimeBasedTriggeringPolicy` để xác định thời điểm rollover theo file pattern.

Ví dụ cấu hình **`log4j2.xml`**, không phải `logback.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/application.log"
                     filePattern="logs/archive/application-%d{yyyy-MM-dd}.log.gz">
            <PatternLayout pattern="%level %c{1} - %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy
                        interval="1" modulate="true"/>
            </Policies>

            <DefaultRolloverStrategy>
                <Delete basePath="logs/archive" maxDepth="1">
                    <IfFileName glob="application-*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Muốn chạy cấu hình trên cần Log4j 2 Core, API/provider tương thích và quyền đọc/ghi/xóa trong các thư mục đã chọn. File config của Log4j 2 **không tương thích trực tiếp** với schema của Logback.

Giải thích:

- `fileName` là file đang ghi.
- `filePattern` dùng ngày để tạo tên archive.
- `interval="1"` nghĩa là một đơn vị kỳ được suy từ pattern (ở đây là ngày).
- `modulate="true"` hướng kỳ kích hoạt tới ranh giới thời gian theo logic của policy, thay vì đơn giản cộng khoảng tính từ startup.
- `Delete` với `IfFileName` giới hạn file được xét; `IfLastModified age="P7D"` đặt điều kiện tuổi file theo thời lượng ISO-8601.
- Điều kiện cleanup chỉ là **ví dụ**; phải thử kỹ trên thư mục test trước khi triển khai vì có thể xóa dữ liệu thật.

**Đừng đồng nhất `age="P7D"` với `maxHistory=7` của Logback.** Một bên xét tuổi file, một bên là số kỳ lịch sử. Hành động cleanup có thể diễn ra khi rollover hoặc tại những mốc lifecycle khác; không phải cron xóa chính xác từng giây.

### 10.1. Múi giờ trong Log4j 2

Ví dụ trên **chưa chỉ định timezone riêng**, vì cú pháp date pattern và cơ chế rollover cần đối chiếu theo phiên bản Log4j 2 đang dùng. Khi muốn UTC hoặc local business time, hãy chọn cấu hình được version hỗ trợ và kiểm tra archive thực tế; không bê nguyên mọi chi tiết `%d{...,UTC}` của Logback sang Log4j 2 mà mặc định semantics giống hệt.

### 10.2. Khi nào dùng Log4j 2 thay Logback?

Nếu ứng dụng đã dùng Log4j 2, nên tận dụng `RollingFile` và policy tương ứng. Nếu đang dùng SLF4J + Logback ổn định, không bắt buộc đổi backend chỉ để có daily rolling. Việc đổi backend liên quan dependency/provider, file config, khả năng xuất Throwable, MDC và pipeline thu thập.

## 11. Retention và giới hạn dung lượng cần được thiết kế riêng

Một hệ thống có thể xoay file đều mỗi ngày nhưng vẫn làm đầy ổ nếu không có cleanup. Khi thiết kế cần nêu rõ:

1. Mỗi kỳ giữ bao nhiêu file và nén bằng định dạng nào?
2. Bao nhiêu **kỳ lịch sử** cần giữ? Bao nhiêu **ngày tuổi thực tế**?
3. Dung lượng tổng archive tối đa là bao nhiêu?
4. Xóa file cũ khi rollover, lúc startup hay theo một lịch độc lập?
5. Agent/collector đã ship xong dữ liệu trước khi file bị nén/xóa chưa?
6. Có yêu cầu audit, pháp lý hoặc điều tra cần lưu lâu hơn không?

### 11.1. maxHistory không phải đồng hồ đếm ngược chính xác

`maxHistory=7` trong Logback liên quan đến số kỳ lịch sử; cleanup thường được thực hiện theo sự kiện/lifecycle và có thể bất đồng bộ. Đừng hứa “đến đúng 00:00 thứ tám mọi file của bảy ngày trước đã bị xóa”.

`cleanHistoryOnStart=true` hữu ích cho ứng dụng không chạy liên tục, nhưng vẫn cần quyền xóa và phải kiểm thử khi thư mục chứa archive cũ từ nhiều instance/version.

### 11.2. totalSizeCap không giới hạn ngay kích cỡ file active

Chính sách `totalSizeCap` của Logback thường áp dụng cho archive được dọn sau khi xét lịch sử; nó không thay thế `maxFileSize` của policy kết hợp hoặc disk quota. Nếu lưu lượng đột biến xảy ra giữa kỳ, file active vẫn có thể rất lớn dù đã đặt `totalSizeCap`.

### 11.3. Retention không phải bảo đảm đã thu thập thành công

Một collector đọc file có thể bị dừng nhiều giờ. Nếu archive bị dọn trước khi collector bắt kịp, dữ liệu có thể mất khỏi hệ thống tập trung dù ứng dụng đã ghi xuống disk. Cần so sánh retention window với collector backlog, network downtime và quy trình restore.

**Không xóa file đang ghi**: chính sách Delete phải giới hạn vào archive và basePath chính xác. Wildcard quá rộng có thể xóa các file của service khác.

## 12. Nhiều JVM/instance và rotation cùng một đường dẫn

Không nên để nhiều tiến trình JVM/pod tự ý cùng ghi và rotate `logs/application.log` trên một shared folder. Rủi ro gồm:

- Cạnh tranh file lock hoặc handle.
- Rollover rename/compress ở hai process không đồng bộ.
- Một instance xóa archive mà instance khác vẫn cần.
- Collector bám nhầm inode/path, đọc trùng hoặc bỏ sót.
- File bị interleave hoặc mất dữ liệu khi rotate ngoài JVM.

Các phương án có kiểm soát:

- Mỗi instance có file/thư mục riêng, định danh instance ổn định.
- Hoặc các instance ghi stdout/stderr để platform và collector gom log tập trung.
- Hoặc dùng hệ thống logging được thiết kế và kiểm chứng cho multi-process.

Không dùng `requestId` làm tên file của từng request: sẽ tạo quá nhiều file, gây áp lực filesystem. Request/trace ID nên nằm trong **event context**.

## 13. Rotation và log shipper/collector

Một agent đọc file thường theo dõi offset/file identity. Khi rolling appender chuyển `application.log` thành archive rồi mở lại `application.log` mới, agent phải:

1. Đọc nốt nội dung file cũ khi cần.
2. Phát hiện file mới cùng path nhưng khác identity.
3. Không đọc lại dữ liệu đã ship.
4. Xử lý việc archive được nén hoặc xóa kịp thời.
5. Chịu được restart của agent lẫn ứng dụng.

Chính sách của các collectors khác nhau; không thể khẳng định mọi agent tự xử lý được file `.gz` hoặc mọi cách rename/copy-truncate.

**Không nên bật đồng thời rolling policy bên trong JVM và external `logrotate` trên cùng một file** nếu chưa có thiết kế phối hợp. Với rename, appender có thể giữ handle cũ; với copy-truncate, những dòng được ghi trong khoảng copy/truncate có thể bị mất hoặc nhân bản.

### Trong container có nên dùng file không?

Nhiều môi trường Kubernetes/container ưu tiên stdout/stderr để runtime xử lý rotation và agent thu thập. Điều đó giảm trách nhiệm quản lý file ở từng JVM, nhưng nền tảng vẫn có quota, buffer, retention và nguy cơ mất log.

Ghi file vẫn hợp lý với batch/desktop/legacy hoặc trường hợp cần file cục bộ; điều kiện là volume, quyền, collector và shutdown đã được thiết kế.

## 14. Async logging và time-based rolling

Khi bọc `RollingFileAppender` bên trong `AsyncAppender`, producer thường enqueue event, worker xử lý việc ghi file sau đó. Điều này có thể giảm latency của request nhưng tạo các câu hỏi:

- Event được tạo trước nửa đêm nhưng xử lý sau nửa đêm sẽ được ghi vào kỳ nào?
- Khi queue đầy, backend block hay drop?
- Khi dừng, worker đã flush hết queue trước khi rolling appender đóng chưa?
- Compression/cleanup đang chạy có được chờ hoặc theo dõi trạng thái không?
- Log file name và event timestamp có thể khác kỳ không?

Hành vi phụ thuộc backend/version/policy. **Không nên dùng tên archive làm nguồn duy nhất để suy thời gian sự kiện**, nhất là trong hệ thống async nhiều thread. Ghi timestamp đầy đủ trong event và truy vấn collector bằng trường thời gian được chuẩn hóa.

Async cũng không tự tạo durability. Event đã enqueue nhưng chưa ghi có thể mất khi process bị `kill -9` hoặc queue drop do quá tải. Nếu log dùng cho audit bắt buộc, cần pipeline bền vững riêng.

## 15. Bảo mật và khả năng chịu lỗi

Time-based rotation không tự giải quyết:

- Quyền ghi file, phân quyền đọc archive, mã hóa khi vận chuyển và lưu trữ.
- Disk full, quota, inode exhaustion, filesystem read-only hoặc mount lỗi.
- Thông tin nhạy cảm trong message, Throwable, MDC hoặc structured fields.
- Log injection bằng newline/control characters từ dữ liệu người dùng.
- Thất bại của compression, rename hoặc cleanup.
- Dữ liệu chưa flush, queue async chưa drain và collector chưa ship.

Hậu tố `.gz` chỉ là compression, **không phải mã hóa**. Tránh log password, token, session cookie, API key và dữ liệu nhạy cảm không cần thiết; dùng formatter/serializer escape dữ liệu không tin cậy.

Backend có thể báo lỗi nội bộ qua status/error handler thay vì ném exception ở mỗi `log.info(...)`. Cần monitoring pipeline và phân công trách nhiệm vận hành.

Đối với yêu cầu lưu vết bắt buộc, nhất là audit/giao dịch tài chính, file rolling chỉ là một kênh observability; không tự đáp ứng yêu cầu xác nhận bền vững, chống sửa đổi và exactly-once. Có thể cần database transaction, transactional outbox hoặc audit/event store chuyên biệt.

## 16. Kiểm thử time-based rotation

### 16.1. Test việc nạp cấu hình

Xác nhận backend thật là Logback, Log4j 2 hay JUL, file cấu hình đang được nạp, appender đã start, root level/filter cho qua event, đường dẫn có quyền ghi và không bị khóa.

Nếu logger đã filter hết events, sẽ không có dữ liệu đi tới rolling appender; không thể kết luận rotation lỗi chỉ từ việc chưa có archive.

### 16.2. Test hai kỳ thời gian

Trong môi trường test biệt lập có clock/test hook phù hợp với backend:

1. Ghi một event thuộc kỳ trước.
2. Đưa thời gian vượt ranh giới ngày/giờ một cách kiểm soát.
3. Ghi event thuộc kỳ sau.
4. Kiểm tra file active, archive, nội dung và tên kỳ.
5. Theo dõi compression/cleanup đến khi hoàn tất.
6. Kiểm tra file không bị mất hoặc nhân bản ngoài dự kiến.

Không chỉ chạy chương trình vài giây rồi khẳng định daily rotation phải xảy ra. Không tự ý đổi đồng hồ máy production để ép test vì ảnh hưởng timestamp, TLS, scheduler và transaction.

### 16.3. Test quá tải và restart

- Tạo nhiều log trong một ngày để xem có cần kết hợp size trigger không.
- Restart appender/JVM khi còn archive cũ để kiểm tra append và cleanup.
- Thử tình huống file không có quyền hoặc disk full trên môi trường test.
- Kiểm tra nhiều instance không cùng rotate một path.
- Dừng collector đủ lâu rồi cho hoạt động lại để xem có bỏ sót archive không.

### 16.4. Test timezone/DST

Xác định UTC hay local business time, chạy test quanh ngày đổi tháng/năm và DST nếu áp dụng. Kiểm tra cả timestamps trong log và ngày archive; không dựa vào timezone của terminal/IDE nếu server chạy khác.

## 17. Troubleshooting: vì sao không có archive theo ngày?

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Chạy 10 giây không thấy `.gz` | Chưa qua kỳ mới | Chờ boundary hoặc test có clock phù hợp |
| Qua nửa đêm vẫn chưa có archive | Chưa phát log sau boundary hoặc timezone khác | Kiểm tra event mới và cấu hình zone |
| Archive có tên ngày hôm qua | File thuộc kỳ vừa kết thúc | Đối chiếu timestamps, không tự coi là lỗi |
| File quá lớn trong một ngày | Chỉ có time trigger | Thêm size-and-time policy nếu cần |
| Nhiều file cùng một ngày | Có `%i` hoặc nhiều writers | Kiểm tra size trigger và instance |
| File cũ hơn 7 ngày vẫn còn | Cleanup phụ thuộc rollover/startup hoặc policy sai | Kiểm tra maxHistory/Delete/status |
| Không thấy file nén | Pattern thiếu `.gz`, compression chưa hoàn tất/lỗi | Kiểm tra log nội bộ backend |
| Lỗi xóa archive | Quyền, đường dẫn hoặc filter Delete sai | Kiểm tra basePath, glob và permissions |
| Mất dòng khi rollover | Collector chưa đọc hết, rotate ngoài JVM xung đột | Kiểm tra end-to-end file → shipper |
| Collector không thấy file mới | Không theo dõi file identity/scan interval | Cấu hình shipper cho rename/reopen |
| JUL không xoay theo ngày | FileHandler mặc định size/count | Dùng giải pháp time-based phù hợp |
| Nhầm Logback với Log4j 2 | Thẻ cấu hình không tương thích | Dùng đúng policy của backend |
| Disk full dù đặt cap | Cap chỉ cho lịch sử hoặc cleanup bị trễ | Bổ sung quota/monitoring/size trigger |
| File lock/rename thất bại | Nhiều process hoặc filesystem lỗi | Tách writer, kiểm tra quyền và status |

### Các bước chẩn đoán

1. Xác định logging API và backend ở runtime.
2. Xác định file config thật sự được nạp và appender đang được sử dụng.
3. Kiểm tra có event đủ level đi tới file sink chưa.
4. Kiểm tra kỳ được suy ra từ pattern và timezone.
5. Kiểm tra có event sau boundary chưa.
6. Xem trạng thái rolling/compression/cleanup và các lỗi I/O.
7. Kiểm tra collector/agent, inode, archive naming và retention.
8. Điều chỉnh theo bằng chứng, không chỉ đổi tên file rồi thử lại.

## 18. Checklist thiết kế và kết luận

- [ ] Chọn đúng backend; không trộn `TimeBasedRollingPolicy` của Logback với `TimeBasedTriggeringPolicy` của Log4j 2.
- [ ] Xác định rõ kỳ giờ/ngày/tháng và timezone UTC hoặc địa phương.
- [ ] Hiểu rollover có thể chỉ xảy ra khi có event sau boundary.
- [ ] Chọn tên file active cố định hoặc tên theo kỳ và xác nhận behavior.
- [ ] Nếu traffic biến động mạnh, cân nhắc policy kết hợp size-and-time.
- [ ] Định nghĩa compression, retention, tổng dung lượng và thời điểm cleanup.
- [ ] Không xóa archive trước khi collector đọc hết.
- [ ] Kiểm tra file lock, nhiều process, container filesystem và external rotation.
- [ ] Chuẩn hóa timestamp event; không dựa chỉ vào tên archive.
- [ ] Có theo dõi disk quota, collector lag và lỗi compression/cleanup.
- [ ] Kiểm thử boundary, DST, restart, shutdown, async queue và lỗi I/O.
- [ ] Bảo vệ dữ liệu nhạy cảm và tách audit store nếu cần durability.

**Kết luận:** rotation theo thời gian chia log thành các kỳ xác định để quản lý, nén và thu thập thuận tiện. Trong Java, `FileHandler` của JUL chủ yếu hỗ trợ size/count; Logback cung cấp `TimeBasedRollingPolicy` và `SizeAndTimeBasedRollingPolicy`; Log4j 2 dùng `TimeBasedTriggeringPolicy` trong `RollingFile`. Một giải pháp đúng phải nêu rõ **timezone, điều kiện trigger, tên file hiện hành, retention, nhiều writers và collector**; chỉ thêm ngày vào tên file là chưa đủ.