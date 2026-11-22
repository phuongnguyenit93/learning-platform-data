# Rotation khi restart: quản lý file log qua nhiều lần chạy Java

## 1. Rotation khi restart là gì?

**Log rotation** (hay *rollover*) là quá trình chuyển file log đang được ghi thành **file lưu trữ (archive)** và tiếp tục ghi vào file mới hoặc file hoạt động khác. Mục đích là kiểm soát kích thước, tổ chức log theo thời gian và giúp áp dụng chính sách lưu giữ (*retention*).

**Rotation khi restart** là câu hỏi về trạng thái các file ấy khi một ứng dụng Java kết thúc rồi được khởi động lại:

- File log của lần chạy trước có còn không?
- JVM mới tiếp tục **append** vào file cũ, hay tạo một file mới?
- Có archive riêng cho mỗi lần restart không?
- Log của tiến trình bị crash có được giữ không?
- Khi nào rotation theo thời gian hoặc kích thước được thực hiện sau restart?
- Nếu nhiều instance chạy chồng nhau, ai được phép rotate file chung?

**Nguyên tắc quan trọng nhất: restart không tự động đồng nghĩa với rotate.** JVM không có quy tắc toàn cục buộc Log4j2, Logback hoặc JUL phải tạo archive mới sau mỗi lần khởi động. Hành vi phụ thuộc **backend, appender/handler, các triggering policy và trạng thái file**.

Ví dụ:

```text
Trước restart:
logs/
└── orders.log                (lần chạy thứ nhất)

Sau restart, nếu append và chưa có trigger:
logs/
└── orders.log                (lần chạy thứ nhất + thứ hai)

Sau restart, nếu chính sách startup rotation kích hoạt:
logs/
├── orders.log                (bản ghi của lần chạy thứ hai)
└── archive/
    └── orders-...log.gz      (log của lần chạy thứ nhất)
```

Hai kết quả trên đều có thể **đúng theo yêu cầu thiết kế**. Không nên tự thêm cơ chế xoay file nếu ứng dụng cần một file liên tục xuyên suốt nhiều phiên chạy, hoặc ngược lại, để file bị ghi đè khi cần lưu log chẩn đoán của lần crash trước.

## 2. Phân biệt append, truncate, rollover, retention và restart

| Khái niệm | Ý nghĩa | Có tạo archive có thể đọc lại không? |
| --- | --- | --- |
| **Restart** | Tiến trình Java cũ dừng, tiến trình mới bắt đầu | Không mặc định |
| **Append** | Mở file đang có và ghi tiếp vào cuối | Không |
| **Truncate / overwrite** | Cắt ngắn hoặc thay nội dung file đang có | Không bảo đảm; có thể mất log cũ |
| **Rollover / rotate** | Chuyển active file thành archive và dùng active file mới | Có nếu thao tác thành công |
| **Retention / cleanup** | Giữ/xóa/nén archive theo tuổi, số lượng, tổng dung lượng | Không phải hành động rotate |

Có thể hình dung:

```text
JVM dừng
  │
  ▼
File active vẫn ở filesystem?
  │
  ├── Không --> tạo file khi appender/handler bắt đầu ghi
  │
  └── Có
       │
       ├── Chế độ append và chưa đến điều kiện rotation
       │     └── Ghi thêm vào file cũ
       │
       ├── Có trigger startup / size / time hợp lệ
       │     └── Rollover --> archive + active file mới
       │
       └── Mở với chế độ ghi đè
             └── File cũ có thể bị truncate, không phải archive
```

**`append=true` không có nghĩa rotate.** Nó chỉ định hướng sử dụng file đang tồn tại. **`append=false` không phải “rotate on startup” an toàn**: chỉ dùng thuộc tính đó có thể làm dữ liệu phiên trước không còn trong file hiện tại mà cũng không được giữ trong archive.

Một file có tên mới hoặc file bị cắt ngắn sau restart **chưa chứng minh** đã có rollover thành công. Phải kiểm tra nội dung archive và chính sách retention.

## 3. Những kịch bản restart thường gặp

### 3.1. Restart trong cùng ngày, file còn nhỏ

Ứng dụng ghi log vào `logs/app.log`, dừng sau vài sự kiện rồi khởi động lại trong ngày. Nếu backend chỉ xoay theo kích thước 10 MB và file mới có 20 KB, một lần restart thường không đủ để kích hoạt chính sách. Với append, phiên mới nối thêm các record.

### 3.2. Restart sau một đêm

Ứng dụng dừng trước nửa đêm, khởi động lại sáng hôm sau. Nếu sử dụng time-based rolling theo ngày, **sự kiện đầu tiên** sau restart có thể kích hoạt xoay file thuộc kỳ cũ. Không phải vì “restart luôn rotate”; nguyên nhân là **ranh giới kỳ thời gian đã thay đổi**.

### 3.3. Restart theo deploy

Service được restart để cập nhật phiên bản. Nếu yêu cầu mỗi bản deploy có file riêng, có thể chọn chính sách startup rotation hoặc đặt tên theo một **run/deployment ID** do hạ tầng cung cấp. Cần kiểm soát tên file, file archive và quyền thu thập.

### 3.4. JVM crash rồi được supervisor khởi động lại

File cũ có thể vẫn tồn tại nhưng không chứa mọi event cuối nếu log còn trong hàng đợi/buffer. Rollover khi start mới **không thể phục hồi** một `LogEvent` hoặc `Throwable` chưa từng được flush thành công trước khi tiến trình cũ chết.

### 3.5. Crash loop

Nếu service khởi động rồi crash hàng chục lần, startup rotation có thể tạo hàng chục archive nhỏ khi mỗi file đạt điều kiện. Phải giới hạn số file và dung lượng, đồng thời sửa nguyên nhân crash loop thay vì chỉ tăng retention.

### 3.6. Rolling deployment nhiều instance

Nếu instance A vẫn ghi file trong khi instance B khởi động cùng đường dẫn file, startup rotation của B có thể can thiệp file do A đang sử dụng. Trường hợp này cần **file per-instance** hoặc pipeline stdout/collector, không nên cho hai JVM độc lập tranh cùng active file nếu chưa có cơ chế phối hợp chuyên dụng.

## 4. Rotation dựa trên điều kiện gì?

Những cơ chế phổ biến trong backend Java:

| Chính sách | Khi nào có thể rollover? | Quan hệ với restart |
| --- | --- | --- |
| **Size-based** | File đạt/vượt điều kiện kích thước | Có thể diễn ra sau restart nếu file đã lớn hoặc khi ghi thêm |
| **Time-based** | Đến kỳ thời gian mới theo pattern/lịch | Sau restart có thể được kiểm tra tại event tiếp theo |
| **Startup-based** | Một phiên JVM mới phát hiện file cũ thỏa điều kiện | Chủ đích phục vụ việc rotate sau startup |
| **Manual/external** | Script hoặc tác vụ quản trị yêu cầu xoay | Có thể chạy trước startup, nhưng cần phối hợp backend |
| **Combined** | Một trong nhiều chính sách được thỏa | Cần xác định chính xác trigger nào gây rollover |

Nhiều triggering policy được đánh giá khi **có sự kiện log đến appender**. Vì vậy việc tiến trình start xong chưa chắc đã có archive mới, đặc biệt nếu chưa ghi record nào đạt điều kiện lọc.

Điều này có hai hệ quả:

- Nếu muốn kiểm chứng rotation sau restart, hãy phát một sự kiện `INFO`/`WARN` và xác nhận backend thực sự nhận nó.
- Không nên tạo startup log bằng cách in thẳng `System.out.println(...)` rồi mong RollingFile nhận được: lệnh này không đi qua Log4j2/Logback file appender.

## 5. Log4j2: OnStartupTriggeringPolicy là gì?

Trong **Apache Log4j2**, `RollingFile` appender có thể đi kèm `OnStartupTriggeringPolicy`. Chính sách này dùng để xác định tình huống nên rollover **file hiện tại tồn tại từ trước một JVM startup**.

Ví dụ một cấu hình chính sách:

```xml
<Policies>
    <OnStartupTriggeringPolicy minSize="1"/>
    <SizeBasedTriggeringPolicy size="1 MB"/>
</Policies>
```

Đây là mảnh XML của Log4j2, cần đặt trong `RollingFile` appender đã được khai báo đúng.

**Cơ chế cần nhớ:**

1. Appender khởi tạo, nhận đường dẫn active file và file pattern cho archive.
2. `OnStartupTriggeringPolicy` kiểm tra những điều kiện áp dụng cho file cũ, trong đó có **kích thước tối thiểu `minSize`** và thông tin thời gian so với thời điểm JVM mới bắt đầu.
3. Khi event đầu tiên đủ điều kiện tới appender, policy có thể yêu cầu rollover file trước đó.
4. File cũ được chuyển sang archive theo rollover strategy, sau đó event hiện tại được ghi vào active file.

**Nó không phải “cứ gọi main() là xoay”.** Gọi `main` hai lần trong cùng JVM, không có file cũ hoặc file quá nhỏ đều có thể không cho kết quả như hai lần khởi động tiến trình thực sự.

Tương tự, `OnStartupTriggeringPolicy` không có nhiệm vụ tự xóa log cũ. Việc **retention** là trách nhiệm của chiến lược lưu/xóa file được cấu hình riêng.

### Các thuộc tính liên quan

- `fileName`: file đang ghi, ví dụ `logs/restart-demo.log`.
- `filePattern`: pattern archive, có thể gồm ngày/giờ, chỉ số `%i` và đuôi nén `.gz`.
- `append="true"`: ưu tiên nối vào file hiện tại khi được mở; không phải trigger.
- `minSize="1"`: tránh cố xoay file trống/quá nhỏ ở startup.
- `SizeBasedTriggeringPolicy`: chính sách kích thước bổ sung, hoạt động độc lập với restart.
- `DefaultRolloverStrategy max="10"`: điều khiển cửa sổ chỉ số/chiến lược archive; không trực tiếp nghĩa là giữ đúng mười ngày.

## 6. Ví dụ hoàn chỉnh Java 17 + Maven + Log4j2

Ta tạo ứng dụng có thể chạy **hai lần trong hai JVM khác nhau**. Lần thứ nhất ghi file, lần thứ hai dùng `OnStartupTriggeringPolicy` để thử xoay file cũ khi thỏa điều kiện.

### 6.1. Cấu trúc thư mục

```text
restart-rotation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── RestartRotationDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>restart-rotation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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

Version trong ví dụ được **ghim để minh họa một bộ dependency cụ thể**, không phải tuyên bố đó là phiên bản mới nhất hay an toàn nhất cho mọi hệ thống. Khi dùng thật, cần đồng bộ bản vá được duy trì của `log4j-api` và `log4j-core`.

### 6.3. Tệp src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="AppFile"
                     fileName="logs/restart-demo.log"
                     filePattern="logs/archive/restart-demo-%d{yyyy-MM-dd-HH-mm-ss}-%i.log.gz"
                     append="true">
            <PatternLayout pattern="%level | %msg%n"/>
            <Policies>
                <OnStartupTriggeringPolicy minSize="1"/>
                <SizeBasedTriggeringPolicy size="1 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="AppFile"/>
        </Root>
    </Loggers>
</Configuration>
```

Giải thích từng phần:

- **AppFile:** một `RollingFile` appender ghi vào `logs/restart-demo.log`.
- **filePattern:** thư mục archive có timestamp, chỉ số `%i` để phân biệt các lần rollover, và `.gz` để nén archive.
- **append=true:** không xóa nội dung chỉ vì mở file khi phiên mới chạy.
- **OnStartupTriggeringPolicy:** cho phép xoay file cũ sau startup khi đáp ứng điều kiện.
- **SizeBasedTriggeringPolicy:** vẫn xoay theo kích thước nếu ứng dụng chạy lâu.
- **DefaultRolloverStrategy:** quản lý tên/chỉ số archive; không thay thế retention theo tuổi.
- **Root INFO:** record INFO và WARN trong ví dụ được chuyển tới AppFile.

Không có Console appender. Vì vậy các dòng Log4j2 được gửi vào **file**, còn `System.out.println` trong `main` tạo stdout độc lập.

### 6.4. Tệp src/main/java/demo/RestartRotationDemo.java

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class RestartRotationDemo {
    private static final Logger LOG =
            LogManager.getLogger(RestartRotationDemo.class);

    public static void main(String[] args) {
        String runName = args.length > 0 ? args[0] : "unnamed";

        LOG.info("Started run {}", runName);
        LOG.warn("Diagnostic marker for {}", runName);

        System.out.println("run-finished:" + runName);
    }
}
```

Đây là **class Java độc lập** khi đặt trong dự án Maven ở trên. Không cần Spring Boot hoặc SLF4J để chạy mẫu.

### 6.5. Chạy lượt thứ nhất

Từ thư mục `restart-rotation-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RestartRotationDemo -Dexec.args=first
```

**Stdout của riêng mã ứng dụng, chính xác:**

```text
run-finished:first
```

Trên thư mục log sạch, file `logs/restart-demo.log` dự kiến có:

```text
INFO | Started run first
WARN | Diagnostic marker for first
```

Đây là **nội dung file**, không phải stdout. Maven hoặc plugin có thể ghi thêm thông báo riêng, nhưng ví dụ không có Log4j2 Console appender. Khi hết tiến trình thứ nhất, file đã có dữ liệu trước khi JVM thứ hai bắt đầu.

### 6.6. Chạy lượt thứ hai trong JVM mới

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RestartRotationDemo -Dexec.args=second
```

**Stdout của riêng chương trình:**

```text
run-finished:second
```

Nếu file từ lượt `first` còn tồn tại, không quá nhỏ và có timestamp phù hợp với điều kiện startup policy, sau khi event đầu tiên của lượt `second` đi vào appender:

1. Log4j2 chuyển file active của phiên trước vào `logs/archive/`.
2. Archive có tên theo `filePattern` và thường được nén `.gz`.
3. Log4j2 ghi sự kiện của lượt mới vào active file `logs/restart-demo.log`.

Khi rollover thành công, **active file mới** dự kiến có:

```text
INFO | Started run second
WARN | Diagnostic marker for second
```

Archive tương ứng với lượt `first` chứa hai dòng `Started run first` và `Diagnostic marker for first`.

Tên archive **không được cố định trong ví dụ** vì phụ thuộc thời điểm, filesystem và các lần chạy trước. Nếu file rỗng, timestamp không phù hợp, không có event hoặc config khác được nạp, có thể không thấy archive. Không tuyên bố mọi restart đều bảo đảm một file `.gz`.

### 6.7. Xem file và archive

Linux/macOS:

```bash
cat logs/restart-demo.log
ls -l logs/archive
```

PowerShell:

```powershell
Get-Content logs/restart-demo.log
Get-ChildItem logs/archive
```

Một file archive `.gz` cần được giải nén bằng công cụ phù hợp; `Get-Content` không tự giải nén. Khi dùng `gzip` trong shell POSIX, hãy chọn **đúng file thực tế** đã xuất hiện trong thư mục archive, không dùng tên giả định từ hướng dẫn.

**Kiểm thử đúng:** mỗi lệnh Maven ở trên phải được chạy trong một tiến trình riêng, không chỉ gọi lại method `main` trong cùng một JVM. Chính sách startup của Log4j2 dựa trên thời điểm JVM, còn đường dẫn file tương đối phụ thuộc **working directory**.

## 7. Đổi cấu hình để thấy restart không xoay file

Trong ví dụ Log4j2, chỉ thay `<Policies>` bằng:

```xml
<Policies>
    <SizeBasedTriggeringPolicy size="1 MB"/>
</Policies>
```

Giữ `append="true"`. Với các record rất ngắn của demo, sau khi chạy lượt `first` và `second`, file active thường vẫn dưới 1 MB và có thể chứa:

```text
INFO | Started run first
WARN | Diagnostic marker for first
INFO | Started run second
WARN | Diagnostic marker for second
```

Không có startup trigger, nên **không cần** có archive mới chỉ vì JVM thứ hai khởi động. Khi kích thước đủ lớn để thỏa policy, file mới được rollover.

Tuy nhiên, kết luận này chỉ đúng nếu không có trigger khác, cấu hình khác hoặc công cụ ngoài cùng xoay file. Một hệ thống đã dùng `TimeBasedTriggeringPolicy` vẫn có thể xoay khi qua ranh giới thời gian dù không có startup trigger.

Nếu thay `append="false"` để “chỉ có log mới”, file cũ có thể bị cắt ngắn và **mất nội dung cũ**, không tự được bảo toàn trong archive. Vì vậy **truncate không phải một kiểu rotation an toàn**.

## 8. TimeBasedTriggeringPolicy và restart sau một khoảng thời gian

Một cấu hình Log4j2 khác dùng **`TimeBasedTriggeringPolicy`**:

```xml
<RollingFile name="DailyFile"
             fileName="logs/app.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout pattern="%d{ISO8601} %level %msg%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
</RollingFile>
```

Đây là **mảnh cấu hình minh họa** cần đặt trong `<Appenders>` của một file Log4j2 đầy đủ. Nếu service dừng vào cuối ngày và khởi động lại vào ngày mới, record đầu tiên có thể kích hoạt rollover của file thuộc kỳ cũ. Điều kiện là **thời gian**, không phải sự tồn tại của một lần restart.

Những điều cần nhớ:

- Restart **trong cùng một kỳ** khi file vẫn nhỏ có thể không xoay.
- Restart **sang kỳ mới** có thể khiến file được xoay khi có log event.
- Thời gian không có hoạt động **không bắt buộc** sinh file trống cho từng ngày.
- Múi giờ, pattern `%d`, đồng hồ hệ thống và thời điểm đánh giá policy ảnh hưởng kết quả.
- Không mặc định rằng archive xuất hiện **ngay khi JVM vừa start** trước sự kiện log.

Để chẩn đoán vì sao có archive, cần phân biệt **startup trigger** với **size/time trigger** thay vì gọi chung là “restart rotation”.

## 9. Logback: RollingFileAppender khi ứng dụng khởi động lại

Trong hệ sinh thái **SLF4J + Logback Classic**, cơ chế rolling có tên và cú pháp riêng. Ví dụ file `logback.xml`:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders-service.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} %-5level %logger - %msg%n</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/orders.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

Phân biệt chính xác:

- `<append>true</append>`: nối file hiện có khi thích hợp, **không ép xoay file mỗi restart**.
- `SizeAndTimeBasedRollingPolicy`: xoay theo dung lượng và kỳ thời gian.
- `maxHistory`, `totalSizeCap`: thuộc chính sách lưu archive.
- `cleanHistoryOnStart`: cho phép thực hiện **dọn lịch sử** khi startup, **không đồng nghĩa** buộc archive active file mỗi lần start.

Ví dụ này chỉ là cấu hình Logback; mã ứng dụng thường gọi `org.slf4j.Logger` và cần Logback provider tương thích trên runtime. Không dán `OnStartupTriggeringPolicy` của Log4j2 vào `logback.xml` rồi mong hoạt động.

### Nếu nhất thiết mỗi lần chạy một file trong Logback

Có thể chọn một cơ chế do môi trường kiểm soát, ví dụ **đặt fileName khác nhau cho từng run/deploy** bằng một run ID hoặc timestamp được chuẩn hóa:

```text
logs/orders-2026-11-09T2000Z-instance-a.log
logs/orders-2026-11-09T2100Z-instance-a.log
```

Hai tên trên chỉ minh họa **quy ước đặt file**, không phải hành vi tự động của file Logback đã cho. Việc biến cấu hình runtime thành các đường dẫn này cần thiết lập rõ và phải quản lý cleanup/collector. Một cách khác là thực hiện bước rotate bên ngoài **trước khi appender mới mở file**, nhưng cần tránh tiến trình cũ vẫn ghi vào đó.

## 10. JUL FileHandler: append khi restart và rotation theo size

JDK có `java.util.logging.FileHandler`, không cần thư viện logging bên ngoài. Constructor thường dùng:

```java
new FileHandler(pattern, limit, count, append)
```

Trong đó:

- `pattern`: tên/đường dẫn file, hỗ trợ `%g` (generation) và `%u` (unique number).
- `limit`: kích thước tối đa mục tiêu bằng byte.
- `count`: số file thế hệ được quản lý.
- `append`: có nối file đang có khi mở hay không.

`FileHandler` **không có plugin `OnStartupTriggeringPolicy` giống Log4j2**. Khi `append=true` và chưa đạt điều kiện kích thước, restart có thể tiếp tục ghi vào file cũ. Với `append=false`, cách mở file có thể làm mất nội dung cũ hoặc thực hiện luân chuyển theo implementation; **không được suy ra mỗi JVM start sẽ bảo toàn được một archive tách biệt theo lần chạy**.

### Chương trình Java 17 độc lập

Tạo file `JulRestartDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulRestartDemo {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        String runName = args.length == 0 ? "unnamed" : args[0];
        Logger logger = Logger.getLogger("demo.JulRestartDemo");
        Level oldLevel = logger.getLevel();
        boolean oldParents = logger.getUseParentHandlers();

        FileHandler file = new FileHandler(
                "logs/jul-restart-%g.log",
                1_000_000, 2, true);
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(file);

        try {
            logger.info("Start run " + runName);
            logger.warning("End run " + runName);
        } finally {
            logger.removeHandler(file);
            file.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldParents);
        }

        System.out.println("jul-run-finished:" + runName);
    }
}
```

Từ thư mục chứa file:

```bash
javac JulRestartDemo.java
java JulRestartDemo first
java JulRestartDemo second
```

**Stdout của hai lượt chạy:**

```text
jul-run-finished:first
jul-run-finished:second
```

Trong thư mục sạch và không có tranh chấp, file thường là `logs/jul-restart-0.log`, chứa:

```text
INFO | Start run first
WARNING | End run first
INFO | Start run second
WARNING | End run second
```

Nó **không cần rotate** chỉ vì JVM mới bắt đầu. File quá nhỏ để đến ngưỡng 1.000.000 byte, còn `append=true` cho phép ghi tiếp.

Tên thực tế có thể thay đổi nếu có xung đột tên, lock hoặc đã có thế hệ file cũ. `file.close()` đóng handler do chương trình tạo để giải phóng handle/lock. Không tạo `FileHandler` mới ở mỗi request, và không tháo handler dùng chung bừa bãi trên server đang xử lý nhiều thread.

## 11. Shutdown bình thường so với crash và dữ liệu chưa flush

Khi **shutdown bình thường**, logging backend có cơ hội:

- Ghi hết dữ liệu đang được xếp hàng hoặc buffer tùy implementation.
- Đóng file handle và giải phóng khóa.
- Hoàn tất những công việc rollover/compression đã được quản lý.
- Ghi sự kiện shutdown nếu logger còn hoạt động.

Khi **crash, kill đột ngột hoặc mất điện**, những công việc đó có thể **không hoàn tất**. Nếu một event mang `Throwable` đã được tạo trong bộ nhớ nhưng chưa được backend ghi bền vững, JVM mới khởi động **không thể khôi phục event ấy chỉ bằng cách rotate file cũ**.

Bởi vậy:

- Không mặc định archive sau restart chứa toàn bộ lỗi cuối của phiên trước.
- Không xóa active file cũ ngay đầu startup chỉ vì không có thông điệp shutdown.
- Với `AsyncAppender`/`AsyncLogger`, kiểm tra hàng đợi, backpressure và hành vi shutdown.
- Nếu log có giá trị audit hoặc cần bảo đảm không mất dữ liệu, dùng thiết kế lưu trữ phù hợp, không dựa duy nhất vào file logging.
- Khi muốn phân tích crash, lưu các event khởi động/dừng và run ID/instance ID an toàn để xác định ranh giới giữa các phiên.

**Rotation xử lý dữ liệu đã tồn tại trên filesystem; nó không phải cơ chế phục hồi transaction.**

## 12. Nhiều JVM dùng cùng file: rủi ro khi rolling deployment

Hãy hình dung tiến trình A vẫn hoạt động trong khi tiến trình B của cùng service khởi động:

```text
JVM A ─┐
       ├── logs/orders-service.log
JVM B ─┘
```

Nếu cả hai cùng mở một active file, rồi mỗi bên đánh giá rollover theo trạng thái riêng, có thể xảy ra tranh chấp khóa, rename archive trùng, ghi vào file cũ đã đổi tên hoặc mất log. Một ứng dụng thread-safe **trong một JVM** không đồng nghĩa an toàn **giữa hai JVM**.

Đặc biệt, nếu B có `OnStartupTriggeringPolicy`, nó có thể xem file đang được A dùng là file từ trước thời điểm B start rồi cố xoay file ấy.

Nên chọn:

```text
Phương án 1: file theo instance
JVM A ── logs/orders-instance-a.log
JVM B ── logs/orders-instance-b.log

Phương án 2: hạ tầng thu thập log
JVM A ── stdout ─┐
                 ├── Collector (service=orders, instance=A/B)
JVM B ── stdout ─┘
```

File name theo instance phải được tạo từ giá trị deployment **đáng tin**, không lấy trực tiếp từ user input. Khi dùng Docker/Kubernetes, stdout/stderr thường đơn giản hơn vì filesystem container có thể là tạm thời.

Nếu buộc dùng shared filesystem và multi-process appender chuyên dụng, phải hiểu chính xác tài liệu hỗ trợ/locking của backend đã chọn. Không giả định mọi `RollingFileAppender` đều an toàn khi nhiều JVM cùng ghi.

## 13. Công cụ logrotate bên ngoài và restart

Trong một số hệ thống Linux, **logrotate** hoặc script quản trị xoay file mà không thông qua logging backend. Hai chiến lược hay gặp:

1. **Rename rồi tạo file mới:** process Java có thể vẫn giữ descriptor của file cũ đã đổi tên và tiếp tục ghi vào nó nếu appender chưa được yêu cầu reopen.
2. **copytruncate:** sao chép active file sang archive rồi truncate file tại chỗ; có cửa sổ race khiến một số dòng phát sinh trong lúc copy/truncate bị bỏ sót hoặc trùng.

Nếu Log4j2/Logback đã tự rolling **và** logrotate cũng thao tác trên cùng active file, hai cơ chế có thể tranh nhau đổi tên, nén hoặc xóa archive. Điều đó tạo ra lỗi khó tái hiện, đặc biệt quanh thời điểm restart.

**Chọn một chủ thể chịu trách nhiệm rotation cho mỗi active file**, hoặc xây dựng cơ chế phối hợp đầy đủ đã kiểm chứng. Khi dùng script rotate trước startup, phải đảm bảo JVM cũ đã dừng và không còn dùng file đó, bước archive có thể phục hồi nếu lỗi, path có quyền ghi và collector còn đọc được log lịch sử.

Không tùy tiện dùng `mv` rồi nghĩ appender đang mở sẽ tự đổi sang file mới. Hành vi trên Unix và Windows có thể khác nhau do cách giữ handle/lock.

## 14. Retention: nếu restart liên tục thì sao?

Startup rotation có thể giúp tách log theo phiên, nhưng lại có thể tạo quá nhiều archive:

- Service restart một hai lần mỗi ngày: thường có thể quản lý được.
- Service crash liên tục: vài trăm lần start có thể tạo nhiều archive rất nhỏ.
- Mỗi lần deploy lại tạo run ID mới: cần quy tắc xóa log cũ và thu thập trước khi cleanup.

Đặt mục tiêu vận hành rõ:

| Câu hỏi | Cần quyết định |
| --- | --- |
| Giữ log bao lâu? | Thời gian retention |
| Giới hạn tổng archive? | Dung lượng tối đa, số lượng/tỷ lệ file |
| Có nén không? | Compression, CPU và độ trễ hoàn tất |
| Có xóa archive khi startup? | Chính sách dọn file và độ an toàn |
| Collector đã thu thập xong chưa? | Tương thích khi archive bị rename/xóa |
| Có phát hiện crash loop không? | Metric restart count và số file tăng |

Trong Log4j2, `DefaultRolloverStrategy max="10"` không tự đồng nghĩa “chỉ giữ 10 ngày”. Trong Logback, `maxHistory`, `totalSizeCap` và `cleanHistoryOnStart` có ý nghĩa riêng. Cần kiểm chứng quy tắc dọn dữ liệu khi appender khởi động, khi rollover và khi đĩa gần đầy.

File log có thể chứa thông tin nhạy cảm, nên retention cần tuân thủ chính sách truy cập và xóa dữ liệu của hệ thống chứ không chỉ tối ưu đĩa.

## 15. Kiểm thử rotation khi restart như thế nào?

Hãy thử trong **thư mục demo riêng**, không xóa hoặc ghi đè log của production.

### Các ca kiểm thử có giá trị

| Trường hợp | Trạng thái trước khi khởi động | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Chạy lần đầu | Không có active file | Tạo file khi có event, thường không có archive cũ |
| Restart và append=true | Active file nhỏ, chưa có startup trigger | Record mới nối tiếp file cũ |
| Startup trigger | Active file của phiên trước, đủ size, mtime phù hợp | Sau event mới, active/archived file tách phiên |
| File rỗng | File active có 0 byte | Startup policy có thể không rollover |
| Restart sang kỳ mới | Time-based policy và file kỳ cũ | Xem thời điểm rollover được kiểm tra |
| Restart sau crash | File chỉ chứa một phần log | Không giả định event chưa flush tự phục hồi |
| Restart nhiều instance | Hai JVM có cùng đường dẫn | Xem xung đột, chuyển sang per-instance nếu cần |
| File không có quyền ghi | Archive directory bị hạn chế | Quan sát lỗi appender, không đánh dấu ghi thành công |

### Quy trình chẩn đoán từng bước

1. Xác định runtime dùng **Log4j2, Logback hay JUL**, không đoán theo tên dependency.
2. Xác nhận tệp `log4j2.xml`/`logback.xml`/`logging.properties` đang được nạp.
3. Kiểm tra `File` hay `RollingFile`, `append`, `fileName`, `filePattern` và các policy.
4. Xác định **working directory** của tiến trình và đường dẫn file thực.
5. Chạy phiên thứ nhất, phát log có marker rõ, đóng tiến trình bình thường.
6. Ghi lại **kích thước, mtime, nội dung active file**.
7. Chạy phiên thứ hai như **JVM mới**, phát event đạt level của logger/appender.
8. Kiểm tra active file, tên archive, nội dung archive sau khi giải nén, số file.
9. Xác định rollover do startup, size, time hay công cụ bên ngoài; không suy từ tên file duy nhất.
10. Kiểm tra lỗi quyền, khóa file, log status và hành vi collector trước khi kết luận PASS.

**Không cần gọi `System.exit(...)` giữa hai lần chạy trong cùng JVM để mô phỏng restart**; hãy thực sự khởi động hai tiến trình JVM riêng. Điều này đặc biệt quan trọng với `OnStartupTriggeringPolicy`.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Restart rồi file vẫn có log của phiên trước | append=true và chưa tới điều kiện rollover | Nếu muốn mỗi phiên một archive, cấu hình startup rotation thích hợp |
| Restart làm mất log cũ | append=false hoặc script xóa/truncate | Dùng cơ chế archive rõ ràng trước khi thay file |
| Có OnStartupTriggeringPolicy nhưng không có .gz | File rỗng/nhỏ, timestamp, chưa có event, sai config hoặc thiếu quyền | Kiểm tra minSize, mtime, active config và appender status |
| Time-based rollover đúng ngày nhưng không đúng lúc start | Policy được đánh giá khi có event hoặc theo cơ chế backend | Thử record đầu tiên và quan sát ranh giới kỳ |
| Mỗi deploy sinh quá nhiều archive | Restart thường xuyên và chính sách startup | Giảm số archive, retention/quota và xử lý nguyên nhân restart |
| File mới không xuất hiện | Đường dẫn sai, thiếu quyền, filter chặn log | Kiểm tra working directory, AppenderRef và permission |
| Đã sửa config nhưng hành vi không đổi | Ứng dụng nạp backend/file config khác | Kiểm tra runtime dependency/config thực |
| Hai JVM ghi file bị mất dòng | Dùng chung file và rollover không được phối hợp | File per-instance hoặc stdout/collector |
| logrotate đã đổi tên nhưng Java vẫn ghi file cũ | Appender còn giữ file handle | Thiết kế reopen hoặc để backend tự rollover |
| copytruncate gây thiếu dòng gần thời điểm rotate | Race của copy và truncate | Tránh phối hợp tùy tiện; chọn chiến lược phù hợp |
| Archive không có exception cuối trước crash | Event hoặc Throwable chưa được ghi/flush | Chấp nhận giới hạn log, dùng cơ chế độ bền phù hợp |
| cleanHistoryOnStart không tạo archive mới | Đây là cleanup, không phải startup trigger | Dùng cơ chế rotate riêng nếu cần |
| Không thấy DEBUG sau restart | Logger/appender filter vẫn chặn DEBUG | Kiểm tra ngưỡng ở cả hai tầng |
| File .gz chưa sẵn khi vừa rollover | Nén/rollover đang xử lý hoặc thất bại | Kiểm tra status và archive hoàn chỉnh trước khi đọc |

## 17. Bảo mật và vận hành

- Không thử truncate/rotate bằng cách xóa file log thật của người dùng hoặc hệ thống production.
- Cấp quyền tạo/ghi/rename/archive cho đúng service account; không chạy đặc quyền cao chỉ để bỏ qua permission.
- Không đặt path archive theo request ID hoặc user input không tin cậy, tránh path traversal.
- Không ghi password, cookie, token, API key hoặc PII vào log dù file có rotation.
- Kiểm tra dữ liệu nhạy cảm trong stack trace và thông điệp của `Throwable`.
- Theo dõi filesystem, lỗi appender, số archive, số lần restart và backlog collector.
- Chọn file theo instance nếu có nhiều JVM; đừng để startup trigger của tiến trình mới xoay file của tiến trình cũ.
- Nếu có rolling file và công cụ xoay bên ngoài, chọn một owner hoặc phối hợp được kiểm chứng.
- Đừng coi retention bằng số file là chính sách audit an toàn nếu chưa xác định độ bền, tính toàn vẹn và thời gian giữ dữ liệu.
- Với container, cân nhắc stdout/stderr và collector để giảm phụ thuộc vào filesystem có thể mất khi restart/redeploy.

## 18. Bài tập tự kiểm tra

**Câu 1.** `append=true` có buộc tạo archive sau mỗi JVM restart không?  
**Đáp án:** Không. Nó điều khiển việc ghi tiếp vào file; muốn rotate phải có trigger/chính sách phù hợp.

**Câu 2.** Vì sao `append=false` không tương đương rotation an toàn?  
**Đáp án:** File có thể bị ghi đè/cắt ngắn mà không có archive bảo toàn log cũ.

**Câu 3.** Log4j2 `OnStartupTriggeringPolicy` kiểm tra điều gì?  
**Đáp án:** Các điều kiện để rollover file cũ khi JVM đã bắt đầu phiên mới, trong đó có kích thước tối thiểu và thông tin thời gian/file. Không phải mọi restart đều chắc chắn tạo archive.

**Câu 4.** Vì sao phải chạy hai lệnh `java` hoặc hai lần chạy Maven riêng khi thử?  
**Đáp án:** Vì startup policy liên quan tới thời điểm một **JVM mới** khởi động; gọi lại `main` trong JVM cũ không tương đương.

**Câu 5.** `cleanHistoryOnStart` trong Logback có ý nghĩa gì?  
**Đáp án:** Dọn lịch sử archive khi startup theo rolling policy, không phải lệnh tạo archive của active file mỗi lần start.

**Câu 6.** Time-based policy có thể rollover sau restart khi nào?  
**Đáp án:** Khi đã qua ranh giới kỳ và policy được đánh giá, thường tại event tiếp theo; không nhất thiết lúc JVM vừa start.

**Câu 7.** Nếu JVM bị kill khi AsyncAppender còn event trong queue, JVM mới có khôi phục chúng nhờ rotation không?  
**Đáp án:** Không có bảo đảm. Rotation chỉ xử lý file đã được ghi, không tái tạo event chưa flush.

**Câu 8.** Vì sao không cho hai JVM cùng sử dụng một active RollingFile tùy tiện?  
**Đáp án:** Có nguy cơ tranh khóa, ghi xen kẽ, rollover/rename trùng hoặc log bị mất.

**Câu 9.** `DefaultRolloverStrategy max="10"` có nghĩa giữ đúng 10 ngày không?  
**Đáp án:** Không. Nó là tham số chiến lược rollover/chỉ số, không tự tương đương retention theo ngày.

**Câu 10.** Nếu sau restart xuất hiện archive, làm sao phân biệt do OnStartup hay do size/time?  
**Đáp án:** Kiểm tra cấu hình active, trạng thái file, kích thước, timestamp và event đã kích hoạt; thử tách từng policy trong môi trường kiểm soát.

**Ghi nhớ:** **Restart không tự động là rotation.** Phân biệt **append – truncate – rollover – retention**, hiểu các policy của Log4j2/Logback/JUL và thử bằng **hai JVM thật**. Bảo toàn dữ liệu cũ, quản lý archive/retention và tách file theo instance là những yếu tố thiết yếu để log còn hữu ích sau restart.
