# Giữ số file lịch sử khi Log Rotation trong Java

## 1. Ý nghĩa của việc giữ file log lịch sử

**Giữ số file lịch sử** là cách giới hạn dữ liệu log còn lại sau khi hệ thống **log rotation** chuyển từ file đang ghi sang file mới. File cũ giúp điều tra sự cố, nhưng nếu cứ tạo archive mà không dọn, dung lượng đĩa có thể tăng vô hạn. Mục tiêu là **giữ đủ dữ liệu có giá trị** trong phạm vi dung lượng, thời gian và chính sách bảo mật được cho phép.

Ví dụ một ứng dụng ghi luân phiên theo kích thước:

```text
logs/
  application.0.log   <- file hiện tại
  application.1.log   <- thế hệ trước
  application.2.log   <- thế hệ cũ hơn
```

Có ba file tổng cộng, nhưng chỉ **hai file lịch sử** bên cạnh file hiện tại. Nếu bạn nói “giữ ba backup” mà cấu hình “count=3” trong JUL, rất có thể đã sai một đơn vị.

Trong Java, cách cấu hình phụ thuộc **backend**:

- **JUL (`java.util.logging.FileHandler`):** `count` là tổng **số file trong vòng xoay**, bao gồm file hiện tại. `count=3` thường có các thế hệ 0, 1, 2 và tối đa hai thế hệ cũ.
- **Logback (`RollingFileAppender` kết hợp `TimeBasedRollingPolicy`):** `maxHistory` là **số kỳ thời gian archive muốn giữ** theo pattern. Với tên file theo ngày, `maxHistory=7` tương ứng bảy kỳ ngày, **không phải cam kết đúng bảy file trên disk ở mọi thời điểm**.
- **Logback với `SizeAndTimeBasedRollingPolicy`:** một ngày có thể sinh nhiều archive (`%i` tăng dần); `maxHistory=7` vẫn nói về bảy kỳ ngày, không phải bảy file.
- **`totalSizeCap` của Logback:** giới hạn **tổng dung lượng archive** do policy quản lý, không phải tổng dung lượng tuyệt đối của mọi log/file active/backup.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết phân biệt active file, generation, archive, số kỳ và dung lượng; cấu hình `FileHandler` trong Java 17; dùng `maxHistory`, `totalSizeCap`, `cleanHistoryOnStart` và `maxFileSize` của Logback; kiểm tra số file thực tế, vòng đời cleanup, lỗi hay gặp và thiết kế retention an toàn.

## 2. Các thuật ngữ chính

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Active log | File đang nhận event | `application.log`, `history.0.log` |
| Generation | Vị trí trong vòng xoay kích thước | Thế hệ `0`, `1`, `2` |
| Archive | File đã chuyển khỏi trạng thái active | `application.2026-01-12.log.gz` |
| Rotation trigger | Điều kiện chuyển file | Đạt giới hạn byte hoặc sang kỳ ngày mới |
| `count` | Số file trong vòng của JUL FileHandler | 3 file tổng cộng |
| `maxHistory` | Số kỳ archive của Logback | 7 kỳ ngày |
| `maxFileSize` | Mục tiêu kích thước từng file trong size-and-time policy | 20MB |
| `totalSizeCap` | Ngưỡng tổng dung lượng archive được Logback dọn | 1GB |
| Cleanup | Quá trình thực tế xóa archive cũ | Khi rollover hoặc khi startup theo cấu hình |
| Retention | Hợp đồng giữ dữ liệu theo thời gian/số lượng/dung lượng | 7 ngày, 1GB, 3 thế hệ |

**Phân biệt file và sự kiện:** Log rotation quản lý **file**. Nó không đảm bảo số event cần lưu, không đảm bảo event đã ghi bền vững, và không thay thế cơ chế audit có yêu cầu toàn vẹn.

**Phân biệt file cục bộ và bản sao:** Sau khi gửi log tới collector, archive local được xóa không có nghĩa bản sao trên OpenSearch, Loki, object storage hoặc backup cũng bị xóa. Chính sách retention phải bao quát mọi bản sao có liên quan.

## 3. JUL FileHandler: `count` tính cả file đang ghi

Java 17 có sẵn `java.util.logging.FileHandler`. Có thể khởi tạo với bốn tham số:

```java
FileHandler handler = new FileHandler(
        "logs/application.%g.log",
        1_000_000,
        3,
        false);
```

Đây là **mảnh Java**, giả định đã import `java.util.logging.FileHandler` và thư mục `logs` tồn tại. Ý nghĩa:

1. **`pattern`:** mẫu tên file; `%g` là vị trí generation.
2. **`limit`:** số byte xấp xỉ được ghi vào một file trước khi xoay vòng; 1.000.000 byte, không phải một triệu event.
3. **`count`:** tổng số file được sử dụng theo vòng; `count=3` là ba thế hệ, **không phải ba file cũ cộng một file hiện tại**.
4. **`append`:** có nối tiếp vào file hiện có khi mở hay không; giá trị `false` không bảo đảm dữ liệu từ những lần chạy trước còn nguyên.

### 3.1. Quan hệ giữa `count` và file lịch sử

| `count` của FileHandler | Số file trong vòng xoay | Số thế hệ cũ bên cạnh active |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |
| 5 | 5 | 4 |

Bảng giả định ứng dụng đã ghi đủ log để các generation được tạo, một FileHandler quản lý tập file không xung đột và không tính file lock hoặc file từ process khác.

Nếu yêu cầu là **“giữ ba file lịch sử và một file hiện tại”**, lựa chọn tương ứng ở JUL thường là **`count=4`**.

### 3.2. Cách xoay vòng theo kích thước

Giả sử có ba file:

```text
application.0.log   <- đang ghi
application.1.log   <- cũ
application.2.log   <- cũ nhất
```

Khi kích thước hiện tại đạt ngưỡng, FileHandler xoay các generation và mở thế hệ active mới. Thế hệ cũ nhất không còn được giữ trong vòng hữu hạn. Không nên dựa vào file thứ tự 0/1/2 để suy ra thời gian giữ chính xác, vì số event/ngày và kích thước từng event biến động.

`limit` là ngưỡng **xấp xỉ**: một record đủ lớn có thể làm file vượt giới hạn rồi mới thực hiện rollover. Dung lượng sử dụng của một vòng khoảng `count × limit`, **không phải quota filesystem cứng**; còn có file lock, metadata, file của Handler khác và các record vượt ngưỡng.

### 3.3. Pattern đặt tên file

JDK FileHandler cho phép một số token:

| Token | Chức năng |
| --- | --- |
| `%g` | Số generation 0, 1, 2, ... |
| `%u` | Số phân biệt khi gặp tên file đang bị chiếm |
| `%t` | Thư mục tạm của hệ thống |
| `%h` | Thư mục home người dùng |
| `%%` | Dấu phần trăm literal |

Ví dụ `history.%g.log` với `count=3` có thể tạo `history.0.log`, `history.1.log`, `history.2.log`. Nếu thiếu `%g` trong pattern mà count lớn hơn 1, FileHandler có cơ chế tự thêm generation vào tên file sinh ra.

`%u` có thể dùng để tránh xung đột khi nhiều Handler/process mở cùng một tên. Theo tài liệu JDK, cơ chế phân biệt bằng unique ID được bảo đảm tin cậy ở **local filesystem**, không phải phương án chia sẻ file chung một cách bền vững giữa nhiều JVM trên network filesystem.

### 3.4. Định dạng, level và vòng đời

FileHandler mặc định dùng `XMLFormatter` nếu không đổi cấu hình. Muốn log text dễ đọc, hãy gắn `SimpleFormatter` hoặc `Formatter` tùy chỉnh.

```java
handler.setLevel(java.util.logging.Level.INFO);
handler.setEncoding("UTF-8");
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

Đây là mảnh mã trên `handler` đã tạo. Level của **Logger** cũng phải cho event đi qua trước khi Handler lọc. Nếu Logger chặn FINE mà Handler cho phép FINE, bản ghi vẫn không xuất hiện.

Tạo Handler khi ứng dụng khởi tạo, không tạo mỗi request. Khi shutdown bình thường, nên tháo Handler khỏi Logger và gọi `close()` để giải phóng file handle/lock. `FileHandler` có thể sinh file `.lck` trong thời gian hoạt động; đó **không phải** một generation log lịch sử.

## 4. Ví dụ Java 17 chạy độc lập: giữ ba thế hệ file

Ví dụ này chạy bằng **JDK 17 thuần**, không cần Maven/Gradle hay thư viện ngoài. Nó tạo thư mục tạm mới, tránh dữ liệu cũ và xung đột tên; sử dụng ngưỡng nhỏ và nhiều event để chắc chắn phát sinh rollover; đóng FileHandler rồi kiểm tra các file thế hệ.

### 4.1. Tạo file `HistoryFilesDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class HistoryFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("jul-history-");

        int limitBytes = 128;
        int fileCount = 3;
        Logger logger = Logger.getLogger("demo.rotation.history");

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                directory.resolve("history.%g.log").toString(),
                limitBytes,
                fileCount,
                false);

        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            for (int i = 0; i < 40; i++) {
                logger.info("event=history.test index=" + i
                        + " payload=" + "X".repeat(100));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        int existing = 0;
        for (int generation = 0; generation < fileCount; generation++) {
            String name = "history." + generation + ".log";
            boolean present =
                    Files.isRegularFile(directory.resolve(name));
            if (present) {
                existing++;
            }
            System.out.println(name + "=" + present);
        }
        System.out.println("totalFiles=" + existing);
    }
}
```

### 4.2. Biên dịch và chạy

```bash
javac HistoryFilesDemo.java
java HistoryFilesDemo
```

**stdout chính xác khi chương trình có quyền ghi vào thư mục tạm trên local filesystem:**

```text
history.0.log=true
history.1.log=true
history.2.log=true
totalFiles=3
```

Đầu ra cố ý không in đường dẫn thư mục tạm ngẫu nhiên hay timestamp. Nó chỉ xác nhận **ba generation file hiện hữu**, không khẳng định số record trong mỗi file hoặc sự tồn tại của cả 40 event. Những record quá cũ được loại khỏi vòng xoay theo thiết kế.

### 4.3. Vì sao kết quả ổn định?

- `Files.createTempDirectory` tạo một thư mục mới, không chứa generation từ lần chạy cũ.
- `count=3` giới hạn bộ file theo các generation 0, 1, 2.
- Mỗi message có 100 chữ X và các trường khác, đủ lớn để liên tục vượt ngưỡng 128 byte; 40 message tạo nhiều lần rollover.
- Logger không chuyển log tới Handler của cha, nên stdout chỉ có phần kiểm tra file.
- Formatter tự viết không in header/footer XML.
- `handler.close()` được thực hiện trước khi kiểm tra file.

Nếu thư mục tạm không thể được tạo hoặc filesystem báo lỗi, chương trình có thể ném `IOException` thay vì in stdout mẫu; đây là điều kiện môi trường, không phải hành vi retention.

### 4.4. Thí nghiệm tiếp theo

- Đổi `fileCount` từ 3 sang 2: sau nhiều rollover có hai generation; chỉ còn một thế hệ cũ bên cạnh active.
- Đổi `fileCount` thành 5: tăng số vị trí, vì vậy dữ liệu cũ có thể tồn tại lâu hơn nếu volume tương tự.
- Tăng `limitBytes` thật lớn nhưng chỉ phát vài event: có thể **chưa tạo đủ số generation** để nhìn thấy đúng count file.
- Đổi `append=false` thành `append=true`: với một thư mục đã có log, hành vi mở/nối file và thời điểm rollover phải được kiểm tra riêng. Trong ví dụ tạo thư mục mới, khác biệt này không thể hiện đủ trường hợp restart.

## 5. Logback: `maxHistory` theo kỳ thời gian

Với **SLF4J + Logback Classic**, một kiểu cấu hình phổ biến là `RollingFileAppender` cùng `TimeBasedRollingPolicy`. Ví dụ **file `logback.xml` hoàn chỉnh**:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Đặt file trên runtime classpath của ứng dụng dùng Logback, ví dụ `src/main/resources/logback.xml`. Đây là cấu hình cho **Logback**, không dành cho JUL `FileHandler`. Cần bảo đảm ứng dụng chọn đúng backend SLF4J, đường dẫn có quyền ghi và Appender được khởi động thành công.

### 5.1. Ý nghĩa các tùy chọn

- `<file>logs/application.log</file>`: đường dẫn **file đang ghi**.
- `fileNamePattern` chứa `%d{yyyy-MM-dd}`: mỗi kỳ ngày có tên archive theo ngày; `.gz` kích hoạt nén theo cấu hình.
- `maxHistory=7`: giữ **bảy kỳ thời gian archive** theo lịch ngày. Không đọc nó như “bảy file, tính cả active”.
- `totalSizeCap=1GB`: giới hạn **tổng archive**; file active và bản sao ở hệ thống khác không được cộng như thể có chung một cap.
- `cleanHistoryOnStart=true`: chạy công việc xóa archive cũ khi Appender bắt đầu, hữu ích cho job chạy ngắn không đủ lâu để rollover.
- Encoder: chọn format nội dung; không quyết định số generation.

### 5.2. `maxHistory` không phải giới hạn số file vật lý cứng

Nếu dùng một archive theo ngày:

```text
logs/application.log
logs/archive/application.2026-01-11.log.gz
logs/archive/application.2026-01-12.log.gz
...
```

Trong trường hợp thông thường, bảy kỳ ngày có thể tương đương khoảng bảy archive bên cạnh active file. Nhưng hệ thống có thể chưa xóa file cũ vì cleanup chỉ chạy ở một số thời điểm, hoặc có nhiều archive trong cùng kỳ nếu dùng policy khác. Vì vậy **không viết kiểm thử “maxHistory=7 thì thư mục luôn có chính xác bảy file”**.

**Đặc biệt: `maxHistory=0` trong TimeBasedRollingPolicy không có nghĩa “giữ không file cũ”**. Nó **tắt việc loại archive theo giới hạn lịch sử**, nên archive có thể tích lũy nếu không có cleanup ngoài.

### 5.3. Khi nào Logback dọn file cũ?

Theo Logback, archive cleanup thông thường diễn ra **khi rollover**. Nếu ứng dụng dừng trước khi có rollover hoặc rất ít phát event, file cũ có thể chưa được dọn. `cleanHistoryOnStart=true` yêu cầu cleanup ngay khi Appender khởi động.

Quá trình xóa archive có thể **bất đồng bộ**, nên việc quan sát thư mục vào đúng một khoảnh khắc không phải bằng chứng policy không chạy. Đừng xóa ngay lập tức bằng script ngoài khi chưa hiểu Appender nào sở hữu file active/archive.

## 6. Giới hạn dung lượng bằng `totalSizeCap`

`maxHistory` giúp giới hạn **thời gian/kỳ**, nhưng một ngày cao điểm có thể ghi hàng GB. `totalSizeCap` bổ sung giới hạn tổng kích thước archive.

Ví dụ mảnh XML nằm bên trong `rollingPolicy`:

```xml
<maxHistory>14</maxHistory>
<totalSizeCap>2GB</totalSizeCap>
```

Điều này **không** đảm bảo luôn giữ đủ 14 ngày. Khi volume tăng, size cap có thể buộc Logback xóa những archive cũ hơn trước khi hết 14 kỳ. Logback áp điều kiện giới hạn lịch sử rồi điều kiện tổng dung lượng archive; `totalSizeCap` yêu cầu `maxHistory` cũng được đặt.

Cần phân biệt:

- **Archive total:** dữ liệu đã được rollover và thuộc rolling policy.
- **Active file:** file hiện tại có thể tăng trong kỳ và chưa được tính như archive.
- **File ngoài pattern:** file tạm, log của module khác, file do hệ điều hành tạo.
- **Collector/backup:** dữ liệu đã được sao sang hệ thống khác.

Vì vậy `totalSizeCap=1GB` không có nghĩa thư mục logs của toàn server được bảo đảm luôn dưới 1GB. Cần đặt cảnh báo dung lượng disk/volume ở cấp triển khai.

### 6.1. Mâu thuẫn giữa thời gian và dung lượng

Giả sử service ghi trung bình 500 MB/ngày. Muốn giữ 14 ngày thường cần một lượng lưu trữ lớn hơn 2GB nếu không tính nén/biến động. Nếu giới hạn archive là 2GB, retention thực tế có thể ngắn hơn nhiều.

Bạn phải chọn một chính sách có ưu tiên rõ: đủ ngày điều tra, dung lượng cố định, giảm volume log, tăng dung lượng hoặc chuyển archive sang kho khác. Không thể chỉ thay `maxHistory` mà giải quyết mọi ràng buộc.

## 7. SizeAndTimeBasedRollingPolicy: một ngày có thể có nhiều file

Khi cần giới hạn cả **kích thước từng file** và **chu kỳ ngày**, Logback hỗ trợ `SizeAndTimeBasedRollingPolicy`. Mảnh cấu hình thay thế cho `rollingPolicy` ở mục 5:

```xml
<rollingPolicy
      class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>1GB</totalSizeCap>
    <cleanHistoryOnStart>true</cleanHistoryOnStart>
</rollingPolicy>
```

Đây **chưa phải một `logback.xml` độc lập**, vì cần đặt trong Appender có encoder và tham chiếu từ Logger/root. Khi dùng size-and-time, **cả `%d` và `%i` đều cần** trong tên archive: `%d` là kỳ thời gian, `%i` là chỉ số archive trong kỳ đó.

Ví dụ khi ngày có nhiều event:

```text
application.2026-01-12.0.log.gz
application.2026-01-12.1.log.gz
application.2026-01-12.2.log.gz
application.2026-01-13.0.log.gz
application.2026-01-13.1.log.gz
```

Ở đây có **năm file archive nhưng chỉ hai kỳ ngày**. Nếu `maxHistory=7`, hệ thống có thể giữ nhiều file cho từng kỳ trong bảy kỳ, không giới hạn tổng số file ở bảy. `totalSizeCap` có thể xóa những archive cũ sớm hơn nếu tổng dữ liệu vượt hạn mức.

**Không mặc định dùng size-and-time cho mọi service:** rollover dựa vào kích thước thêm việc đổi tên file và nhiều archive, có chi phí/độ phức tạp. Nếu yêu cầu chỉ là giới hạn tổng archive theo ngày, TimeBasedRollingPolicy và totalSizeCap có thể đủ.

## 8. Phân biệt ba loại yêu cầu retention

| Yêu cầu | Cấu hình thường phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Có tối đa ba file xoay vòng, **gồm active** | JUL `count=3` | Không phải ba bản backup |
| Giữ ba file cũ bên cạnh một active | JUL `count=4` cho một Handler | Không phải giữ ba ngày |
| Giữ bảy kỳ archive theo ngày | Logback daily `maxHistory=7` | Không chắc có đúng bảy file trên disk |
| Archive tổng không quá khoảng 1GB | Logback `maxHistory` + `totalSizeCap=1GB` | Không bao gồm mọi file active/bản sao |
| Archive theo ngày, mỗi file không quá mức mục tiêu 20MB | Size-and-time + `maxFileSize=20MB` | Không chỉ một file/ngày |
| Giữ đầy đủ audit giao dịch theo quy định | Kho audit có độ bền/retention riêng | Rolling file không cung cấp đảm bảo giao dịch |

Trước khi đặt bất cứ con số nào, hãy hỏi: “Bao nhiêu file **tổng cộng**, bao nhiêu **file cũ**, bao nhiêu **kỳ ngày**, bao nhiêu **byte**, và bản sao nào được tính?”.

## 9. Ước lượng dung lượng trước khi triển khai

Một phép tính định hướng:

```text
Dung lượng log/ngày ≈ số event/ngày × kích thước trung bình/event
Số ngày theo archive cap ≈ dung lượng archive cho phép / dung lượng log/ngày
```

Ví dụ 200.000 event mỗi ngày, trung bình 500 byte/event:

```text
200.000 × 500 = 100.000.000 byte/ngày
```

Nếu có xấp xỉ 1GB archive (theo quy ước khoảng một tỷ byte) thì ở mức trung bình, dung lượng tương ứng cỡ **10 ngày** khi chưa tính nén và overhead. Đây chỉ là minh họa, không phải cam kết giữ mười ngày:

- Một exception stack trace có thể lớn hơn nhiều một dòng INFO.
- Mở DEBUG có thể tăng volume hàng chục lần.
- Dữ liệu log có tỷ lệ nén khác nhau.
- Giờ cao điểm/ngày cao điểm khác trung bình.
- File active chưa được tính vào archive cap.
- Log được nhân bản ở nhiều Appender/collector sẽ tiêu thụ thêm dung lượng.

Phải đo volume thực tế, dự trù headroom cho lúc tăng tải và đặt cảnh báo disk. Không dùng công thức trung bình để suy ra retention bắt buộc cho sự kiện audit.

## 10. Restart, lỗi I/O và cleanup không tức thời

### 10.1. Restart

Với JUL, `append` ảnh hưởng cách mở file đã có, và `count` điều khiển vòng file thế hệ. Kết quả sau restart còn phụ thuộc các file cũ, kích thước, file lock và tên path thực sự. Đừng kết luận một lần chạy ít log cho thấy retention không hoạt động vì chưa thấy đủ generation.

Với Logback, `cleanHistoryOnStart` hữu ích khi ứng dụng chạy ngắn; nếu tắt nó, cleanup thường chờ một rollover. Không dựa vào việc chỉ đổi config để bảo đảm file cũ bị xóa **ngay lập tức**.

### 10.2. Crash và shutdown đột ngột

Các event còn nằm trong buffer, async queue hoặc chưa kịp flush có thể mất khi process dừng không sạch. Archive có thể đang nén hoặc công việc dọn file chưa hoàn tất. `count`, `maxHistory` hay `totalSizeCap` **không đảm bảo mọi event được ghi bền vững**.

Nếu audit có yêu cầu độ bền/chống sửa đổi, cần hệ thống audit/storage có hợp đồng riêng, không chỉ gọi `logger.info()`.

### 10.3. Rotation của ứng dụng và rotation của hệ điều hành

Không để Logback/JUL **cùng lúc** tự xoay một file mà một công cụ như `logrotate` cũng rename/copytruncate file đó, trừ khi đã thiết kế và kiểm thử tương tác. Hai cơ chế có thể gây mất log, ghi vào file cũ hoặc trùng sự kiện ở collector. Nên có **một chủ thể quản lý rotation** của cùng đường stream.

Đối với container, thường đơn giản hơn nếu ứng dụng xuất stdout/stderr và để runtime/collector quản lý file của container. Khi đó retention chủ yếu thuộc nền tảng thu thập thay vì vô số FileHandler cục bộ.

## 11. Nhiều JVM hoặc nhiều module làm số file tăng

Một Handler có `count=3` không có nghĩa cả host chỉ có ba file. Nếu có ba JVM độc lập, mỗi JVM giữ ba generation:

```text
instance-A: 3 file
instance-B: 3 file
instance-C: 3 file
tổng:      9 file
```

Tương tự, nếu một ứng dụng có năm RollingFileAppender theo module, mỗi Appender quản lý lịch sử riêng. `maxHistory=7` là giá trị của **mỗi policy**, không phải tổng bảy archive của toàn ứng dụng.

### 11.1. Nhiều writer cùng một path

Nhiều process dùng cùng tên file có thể tranh chấp lock, rename và rotation. `%u` của FileHandler giúp tách một số tên file khi process khác đang dùng file nhưng không phải cách bảo đảm multi-process shared rotation trên mọi filesystem. Tách namespace theo instance hoặc dùng collector sẽ an toàn hơn.

### 11.2. Quyền truy cập và dữ liệu nhạy cảm

File log cũ vẫn có thể chứa dữ liệu mà ứng dụng đã ngừng ghi. Retention nên đi kèm:

- Allowlist field; không đưa mật khẩu/token/cookie/số thẻ nhạy cảm vào log.
- Quyền đọc file/archive theo nguyên tắc tối thiểu.
- Mã hóa và backup khi chính sách yêu cầu.
- Quy định xóa bản sao trong hệ thống tập trung.
- Escape message chứa newline/ký tự điều khiển để tránh log injection.
- Đường dẫn log cố định/tin cậy, không lấy input client để ghép path.

Xóa archive ở máy chủ không có nghĩa dữ liệu ở collector cũng tự bị xóa.

## 12. Giám sát retention trong thực tế

Một cấu hình hợp lệ chưa chứng minh log lịch sử được giữ/xóa đúng. Hãy kiểm chứng theo trình tự:

1. Xác định backend thật: JUL, Logback hay hệ khác; tránh áp nhầm cú pháp.
2. Xác định **active file**, archive, generation, lock và file của process khác.
3. Xem kích thước thật của các file, so với limit và dung lượng disk còn trống.
4. Tạo một workload test để kích hoạt ít nhất vài lần rollover.
5. Kiểm tra file thế hệ cuối cùng và cách file cũ bị thay thế.
6. Với Logback, kiểm tra `maxHistory` theo kỳ, không đơn thuần đếm số file.
7. Xác nhận cleanup khi rollover và khi startup nếu bật `cleanHistoryOnStart`.
8. Thử restart và kiểm tra file còn lại, hành vi append/rotation.
9. Kiểm tra collector theo dõi file sau rename và file nén, không double-ingest.
10. Đặt cảnh báo khi disk đầy, archive tăng bất thường hoặc cleanup báo lỗi.

Với hệ có nhiều bản sao, log retention phải được quản lý qua **toàn bộ đường đi**: ứng dụng → file/stream → agent → collector → kho lưu trữ và backup.

## 13. Lỗi phổ biến khi giữ số file lịch sử

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Muốn ba backup nhưng JUL chỉ còn hai file cũ | `count=3` tính cả active | Đặt `count=4` nếu muốn ba thế hệ cũ |
| JUL `count=3` mà thấy một file | Chưa có đủ rollover | Kiểm tra volume và `limit`, thử ghi thêm |
| FileHandler vượt limit vài byte | Limit là ngưỡng xấp xỉ | Dành headroom; đừng coi đó là quota cứng |
| Có `.lck` khi chương trình đang chạy | FileHandler sử dụng file lock | Không đếm lock như file lịch sử |
| Tên file JUL có generation/unique suffix lạ | Thiếu `%g` hoặc có xung đột kích hoạt `%u` | Kiểm tra pattern và process đang ghi |
| FileHandler tạo XML | Chưa thay XMLFormatter mặc định | Chọn SimpleFormatter/custom Formatter |
| Logback giữ hơn bảy file dù maxHistory=7 | Một kỳ có nhiều archive hoặc cleanup chưa chạy | Kiểm tra policy, `%d`/`%i`, lifecycle |
| `maxHistory=0` mà archive cứ tăng | Giá trị 0 tắt archive-removal theo lịch sử | Đặt giới hạn hữu hạn |
| Archive chưa đủ bảy kỳ đã bị xóa | `totalSizeCap` quá thấp hoặc cleanup khác | So sánh volume và size cap |
| Thư mục log vượt 1GB dù cap=1GB | File active/file khác nằm ngoài archive cap | Kiểm tra tổng disk, policy ownership |
| Một file bị nhiều process cùng xoay | Tranh chấp tên/path | Tách file theo instance hoặc stdout/collector |
| Restart làm file thay đổi bất ngờ | Append, rollover, startup cleanup khác dự tính | Thử cụ thể theo backend và phiên bản |
| File đã xóa nhưng disk chưa giải phóng | Process vẫn giữ file descriptor mở | Kiểm tra writer/OS và lifecycle |
| Collector mất/nhân đôi event khi rollover | Agent chưa xử lý rename/archive đúng | Kiểm tra offset, inode, rotation và nén |
| Không còn dữ liệu điều tra khi xảy ra sự cố | Retention ngắn hơn thời gian phát hiện | Tăng lưu trữ hoặc chuyển archive ra kho phù hợp |

**Quy trình gỡ lỗi:** kiểm tra cấu hình → logger/handler/appender đang hoạt động → file name pattern và working directory → trigger rollover → cleanup → filesystem/collector. Không thay nhiều biến cùng lúc, tránh làm mất dấu nguyên nhân.

## 14. Checklist trước khi áp dụng

- [ ] Đã xác định retention theo **file**, **bản lịch sử**, **kỳ ngày** hay **dung lượng**.
- [ ] Hiểu JUL `FileHandler.count` là **tổng file**, tính cả file đang ghi.
- [ ] Hiểu Logback `maxHistory` là số kỳ thời gian được giữ, không phải số file vật lý cứng.
- [ ] Chọn `limit` hoặc `maxFileSize` dựa trên volume thật, biết mức này không đảm bảo quota từng byte/event.
- [ ] Có `totalSizeCap` nếu cần giới hạn tổng archive và hiểu nó không bao gồm active/backup khác.
- [ ] Có chính sách `cleanHistoryOnStart` phù hợp với job ngắn và rollout thực tế.
- [ ] Kiểm tra fileNamePattern chứa token cần thiết: `%g` cho JUL, `%d` và `%i` cho size-and-time Logback.
- [ ] Phân biệt file active, archive, generation và lock.
- [ ] Có quyền ghi, đường dẫn tin cậy, dung lượng và giám sát đĩa.
- [ ] Không có hai cơ chế độc lập cùng xoay một đường dẫn không được thiết kế cho việc đó.
- [ ] Kiểm soát dữ liệu nhạy cảm, quyền đọc, mã hóa và retention bản sao.
- [ ] Đã thử nhiều lần rollover, restart, crash giả lập, volume tăng và collector tail.
- [ ] Không dùng file xoay vòng làm kho audit duy nhất nếu cần đảm bảo giao dịch.
- [ ] Có cảnh báo và hướng xử lý khi cleanup không chạy hoặc log mất trước thời hạn mong muốn.

### Tài liệu kỹ thuật chính thức

- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): pattern, limit, count, append, generation và lock.
- [Logback RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html): TimeBasedRollingPolicy, maxHistory, totalSizeCap, cleanHistoryOnStart và SizeAndTimeBasedRollingPolicy.
- [Logback Configuration](https://logback.qos.ch/manual/configuration.html): vòng đời Appender và cách nạp cấu hình.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade và lựa chọn backend.

**Kết luận:** Muốn **giữ số file lịch sử** đúng, trước hết phải chọn **đúng đơn vị**. Với JUL, `count=3` là **ba generation bao gồm active**, nên chỉ có hai file cũ bên cạnh. Với Logback theo thời gian, `maxHistory=7` nói về **bảy kỳ archive**, không hứa luôn đúng bảy file; `totalSizeCap` có thể giảm số archive được giữ khi dung lượng lớn. Đừng coi một giá trị cấu hình là bảo đảm tuyệt đối: hãy test rollover, startup cleanup, dung lượng, quyền truy cập, crash và collector thực tế.
