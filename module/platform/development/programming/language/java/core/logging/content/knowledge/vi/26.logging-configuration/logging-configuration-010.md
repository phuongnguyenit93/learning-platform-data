# Xử lý cấu hình sai trong Java Logging

## 1. Vì sao cấu hình logging sai là một lỗi vận hành nghiêm trọng?

**Cấu hình logging sai (logging misconfiguration)** là tình trạng ứng dụng không khởi tạo hoặc vận hành hệ thống ghi log theo chính sách mong muốn: không tìm thấy file cấu hình, chọn sai provider, khai báo level/filter/appender không hợp lệ, không có quyền ghi file, không gửi được log tới nơi nhận, hoặc cấu hình được nạp nhưng hành vi khác kỳ vọng.

Tác động trải từ **thiếu DEBUG khi điều tra lỗi** đến **mất toàn bộ nhật ký, ghi trùng, lộ thông tin nhạy cảm, startup thất bại hoặc ứng dụng chậm vì I/O**. Nguy hiểm nhất là kiểu lỗi “ứng dụng vẫn chạy bình thường” nhưng logging đã rơi vào no-op hoặc không có appender đích.

Cần phân biệt ba loại tình trạng:

1. **Không thể đọc/parse cấu hình:** file không tồn tại, XML/JSON/properties sai cú pháp, cấu hình thiếu thành phần bắt buộc.
2. **Nạp được nhưng không áp dụng đúng:** file khác được ưu tiên, thuộc tính viết sai tên hoặc bị framework bỏ qua, sai level/additivity, provider không tương thích.
3. **Cấu hình hợp lệ nhưng đích ghi hỏng:** không có quyền ghi thư mục, ổ đĩa đầy, endpoint mạng không truy cập được, hàng đợi async đầy hoặc bị discard.

Vì các logging framework không có chung chính sách xử lý lỗi, **không suy ra rằng việc khởi động thành công có nghĩa logging tốt**. Cần kiểm tra cả thông báo nội bộ của framework và sự hiện diện thực tế của log ở sink đích.

## 2. Nhận diện triệu chứng và nguyên nhân có khả năng

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng cần tìm |
| --- | --- | --- |
| Không thấy một dòng log nào | SLF4J không có provider, root/appender thiếu, level `OFF`, sink lỗi | Cảnh báo SLF4J; provider đang dùng; logger tree; phép ghi thử |
| Chỉ thấy WARN/ERROR | Logger level hoặc handler/appender threshold quá cao | Level hiệu lực trên logger, handler, filter và root |
| Log xuất hiện trên console dù cấu hình file | Nạp file cấu hình sai hoặc framework dùng cấu hình mặc định | Đường dẫn config, status lúc startup, classpath |
| Mỗi thông điệp xuất hiện hai lần | Logger truyền tới parent/root và cùng ghi ở nhiều appender | `additivity`, `useParentHandlers`, appender-ref |
| Có lỗi parse XML hoặc class appender | Cú pháp/tag/namespace, dependency hoặc tên class/plugin sai | Stack trace/status logger và vị trí khai báo |
| Không tạo được file log | Thư mục, quyền, mount, path, lock, quota/ổ đĩa | `IOException`, trạng thái filesystem và user chạy JVM |
| DEBUG có ở local nhưng không ở production | Profile/config override, root level và policy filter khác nhau | Config hiệu lực và environment variables |
| Sau reload cấu hình mới mất log | Reload không thành công, resource bị đóng sớm, provider không hỗ trợ cập nhật như giả định | Thông báo reload, smoke test trước/sau, rollback |
| Khi tải cao mất một phần log | Async queue đầy, policy discard/drop, sink quá chậm | Queue depth, drop counter, tốc độ sink, shutdown timeout |

**Một tình huống có thể có nhiều nguyên nhân.** Ví dụ “không thấy DEBUG” có thể do logger bị lọc trước khi tạo sự kiện, handler console lọc lần nữa, hoặc cả hai.

## 3. Nguyên tắc xử lý khi chính logging bị lỗi

Logging là thành phần hạ tầng: nếu logger đang hỏng, việc gọi lại chính logger ấy để báo “logger hỏng” có thể không tạo ra chứng cứ. Vì vậy:

- Khi khởi tạo, **phát thông báo chẩn đoán tối thiểu qua `System.err` hoặc status logger độc lập**. Không dùng đây làm kênh log nghiệp vụ lâu dài; không in mật khẩu, token, chuỗi kết nối có credential.
- **Phân loại mức nghiêm trọng của yêu cầu log:** log debug thường có thể dùng cấu hình dự phòng; log audit hoặc bằng chứng bắt buộc thì không nên tiếp tục xử lý nghiệp vụ nếu chưa có kênh ghi đủ bảo đảm.
- **Không nuốt ngoại lệ cấu hình:** nếu chuyển sang fallback, phải có tín hiệu rõ ràng rằng chế độ degraded đang hoạt động và cần được sửa.
- **Kiểm tra đường đi thực tế của một event:** gọi logger → level/filter → appender/handler → file/stdout/network → collector. Bản ghi “đã gửi” không chứng minh collector đã lưu.
- **Giữ cấu hình đã chạy tốt để rollback:** nạp cấu hình mới trong môi trường thử nghiệm, kiểm tra log tối thiểu, rồi mới triển khai rộng.
- **Không tự động tắt logging** để “cứu” startup khi nghiệp vụ bắt buộc cần lịch sử hoạt động hoặc kiểm toán.

## 4. Quy trình điều tra từng bước

1. **Khoanh vùng:** biết chính xác JVM, bản build, phiên bản JDK, thư viện logging, container/pod, thời điểm phát sinh và sự kiện lẽ ra phải ghi.
2. **Xác định framework thật sự:** JUL (`java.util.logging`), SLF4J API trỏ tới Logback hoặc provider khác, Log4j 2 Core, hoặc bridge giữa các hệ. API `org.slf4j.Logger` không tự cho biết đích ghi đang dùng.
3. **Xác định file cấu hình đã được nạp:** đường dẫn theo JVM system property, classpath, profile, volume mount và quy tắc ưu tiên của framework. Không chỉ nhìn file trong repository.
4. **Bật chẩn đoán khởi tạo có kiểm soát:** dùng status/internal diagnostics của framework, đọc stderr của tiến trình lúc startup. Ghi lại các lỗi như class not found, missing appender, invalid level.
5. **Xác nhận logger và đích:** kiểm tra level hiệu lực, filters, additivity, root appender và quyền truy cập sink. Tạo một sự kiện thử có ID duy nhất, quan sát đúng nơi nhận.
6. **Chỉ sửa một nhóm nguyên nhân tại một thời điểm:** sửa file/provider hoặc quyền ghi, thử lại bằng cùng build và environment; tránh thay đổi đồng loạt khiến không biết nguyên nhân.
7. **Xác minh sau sửa:** có thông báo startup, ghi thử INFO/WARN/ERROR phù hợp, không ghi trùng, tải cao vẫn vận hành, restart/shutdown xử lý log tồn đọng.

Không dùng duy nhất `logger.isLoggable(Level.INFO)` hoặc `log.isDebugEnabled()` làm phép kiểm hoàn chỉnh: các API này chỉ đánh giá điều kiện level/filter trong phạm vi nhất định, không chứng minh file/mạng đã ghi thành công.

## 5. Java Util Logging (JUL): cấu hình hiệu lực và điểm dễ nhầm

JUL được cung cấp trong JDK qua `java.util.logging`. Cấu hình khởi tạo mặc định có thể đến từ file của JDK, hoặc từ file được chỉ định bằng JVM property:

~~~bash
java -Djava.util.logging.config.file=conf/jul.properties -cp out com.example.Main
~~~

Tham số `-D...` phải được truyền khi khởi chạy JVM (đặt trước tên lớp main). File `jul.properties` tối thiểu:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

Ở JUL, **logger level** và **handler level** đều có thể lọc thông điệp. Ví dụ logger cho phép `FINE` nhưng `ConsoleHandler.level=INFO` thì bản ghi `FINE` vẫn không được handler xuất ra. Logger con có thể kế thừa level từ logger cha; `setUseParentHandlers(false)` sẽ chặn truyền sự kiện lên handler của cha và có thể khiến log biến mất nếu logger con không có handler.

Các điều cần chẩn đoán:

- `java.util.logging.config.file` chỉ định sai path: quan sát lỗi startup và xác nhận file thực sự có mặt trong môi trường chạy.
- Sai tên lớp handler hoặc formatter: xem stderr/thông báo nội bộ JUL; không giả định ứng dụng luôn dừng.
- Cấu hình ghi vào `FileHandler`: xác nhận `java.util.logging.FileHandler.pattern`, thư mục cha, file lock và quyền ghi.
- Gọi `LogManager.getLogManager().readConfiguration(...)` giữa lúc ứng dụng đang chạy có thể **reset logger đã tồn tại**, khiến handler/level do code gắn vào bị thay đổi. Theo API Java 17, khi muốn cập nhật config, xem `updateConfiguration(...)` thay vì tùy tiện gọi `readConfiguration(...)` vào runtime.
- JUL không đảm bảo mọi thuộc tính viết sai sẽ được báo lỗi đủ để fail startup. Với cấu hình quan trọng do ứng dụng tự sở hữu, nên có lớp kiểm tra khóa và giá trị bắt buộc trước khi áp dụng.

Ví dụ kiểm tra cấu hình thuần JDK dưới đây cho thấy cách xử lý một giá trị không hợp lệ rõ ràng thay vì im lặng bỏ qua.

## 6. Ví dụ Java 17: kiểm tra cấu hình trước khi áp dụng

Ví dụ dùng **file thuộc tính do ứng dụng định nghĩa**, có khóa `app.level`. Đây không phải là cú pháp thay thế toàn bộ cấu hình JUL, mà là cách minh họa **validate → apply → báo lỗi fail-fast**. Chương trình không cần dependency ngoài JDK.

Tạo tệp **LoggingConfigDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingConfigDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingConfigDemo.class.getName());

    private static Level parseLevel(Properties props) {
        String raw = props.getProperty("app.level");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("app.level is required");
        }
        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "SEVERE" -> Level.SEVERE;
            case "WARNING" -> Level.WARNING;
            case "INFO" -> Level.INFO;
            case "CONFIG" -> Level.CONFIG;
            case "FINE" -> Level.FINE;
            case "FINER" -> Level.FINER;
            case "FINEST" -> Level.FINEST;
            default -> throw new IllegalArgumentException(
                    "unsupported app.level: " + raw);
        };
    }

    private static void startLogging(Level level) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(level);
        LOG.addHandler(handler);
        try {
            LOG.info("startup ok");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("CONFIG_ERROR expected one properties path");
            System.exit(2);
            return;
        }
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            Properties props = new Properties();
            props.load(input);
            Level level = parseLevel(props); // Kiểm tra trước khi áp dụng.
            startLogging(level);
            System.out.println("CONFIG_OK level=" + level.getName());
        } catch (IOException | IllegalArgumentException ex) {
            System.err.println("CONFIG_ERROR " + ex.getMessage());
            System.exit(2);
        }
    }
}
~~~

Tạo file **logging-good.properties**:

~~~properties
app.level=INFO
~~~

Và file **logging-bad.properties**:

~~~properties
app.level=VERBOSE
~~~

Biên dịch với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 LoggingConfigDemo.java
java LoggingConfigDemo logging-good.properties
~~~

**Trường hợp hợp lệ**, các stream có nội dung chính xác:

- Standard error (vì `ConsoleHandler` của JUL ghi ra stderr): `INFO startup ok`
- Standard output: `CONFIG_OK level=INFO`
- Exit code: `0`

Thử cấu hình sai:

~~~bash
java LoggingConfigDemo logging-bad.properties
~~~

**Trường hợp sai**: stderr là `CONFIG_ERROR unsupported app.level: VERBOSE`, không có dòng stdout và exit code là `2`. Chương trình cũng báo `app.level is required` nếu khóa không có hoặc rỗng.

**Giải thích cơ chế:**

1. `Properties.load(...)` đọc file từ đường dẫn CLI; lỗi thiếu file/không đọc được phát sinh `IOException`.
2. `parseLevel(...)` kiểm tra khóa bắt buộc và danh sách level do ứng dụng chấp nhận. `VERBOSE` không hợp lệ theo chính sách demo nên bị từ chối ngay.
3. Chỉ sau khi kiểm tra thành công mới tạo/gắn `ConsoleHandler`. `setUseParentHandlers(false)` ngăn log bị in thêm bởi root handler; handler level `ALL` tránh lọc lần thứ hai so với logger level đã chọn.
4. Khi lỗi, thông báo đi thẳng tới stderr mà không phụ thuộc logger đang được khởi tạo, và chương trình thoát với mã phi 0.
5. Handler được gỡ và đóng trong `finally` để ví dụ không giữ tài nguyên.

Ví dụ chỉ chứng minh kiểm tra một khóa cấu hình và xử lý sai level; ở ứng dụng thực, hãy kiểm tra các trường quan trọng khác như URL/đường dẫn sink, định dạng, quyền truy cập và compatibility. Vì log thử được ghi tại mức INFO, cấu hình `WARNING` sẽ lọc bản ghi thử; trong health check thực tế, nên phát sự kiện ở mức phù hợp hoặc kiểm tra logger level riêng.

Một chính sách hữu ích là: **không chấp nhận unknown keys với các cấu hình vận hành quan trọng do ứng dụng tự quản lý**, báo tên khóa sai và gợi ý khóa đúng. Các framework có thể chấp nhận/từ chối unknown keys khác nhau, nên validation phải phù hợp phiên bản và schema đang dùng.

## 7. SLF4J: lỗi thiếu provider hoặc nhiều provider

SLF4J là facade/API; nó cần một **provider** để ghi ra nơi nhận. Từ **SLF4J 2.x**, provider được phát hiện qua `ServiceLoader`. Hai trường hợp điển hình:

**Thiếu provider:**

~~~text
SLF4J: No SLF4J providers were found.
SLF4J: Defaulting to no-operation (NOP) logger implementation
~~~

Điều này có thể khiến ứng dụng vẫn chạy mà **không ghi log qua SLF4J**. Cách sửa là bổ sung **một provider phù hợp** (ví dụ Logback Classic tương thích với API đang chạy), sau đó xác minh bằng startup log và event thử.

**Nhiều provider/binding:** classpath có thể đồng thời chứa nhiều backend; SLF4J có thể cảnh báo và việc chọn provider không khớp mong đợi. Nên loại bỏ provider dư, thường chỉ giữ **một** backend để tránh mơ hồ.

**Sai phiên bản:** SLF4J 2.x không sử dụng kiểu `StaticLoggerBinder` của binding 1.7 theo cách cũ. Nếu đưa nhầm binding thời 1.7 vào ứng dụng SLF4J 2.x, backend có thể không được nhận diện.

Quy trình kiểm tra:

- Xác định phiên bản `slf4j-api` hiệu lực và provider trong runtime dependency tree, bao gồm transitive dependencies; chỉ nhìn `pom.xml` hoặc `build.gradle` trực tiếp có thể thiếu dependency từ thư viện khác.
- Đọc cảnh báo phát ra ở startup và xác nhận provider được chọn.
- Không khai báo provider ở library tái sử dụng nếu library chỉ cần SLF4J API; ứng dụng chủ nên quyết định backend.
- Sau sửa dependency, kiểm tra lại log thực tế, tránh khắc phục cảnh báo bằng cách thêm NOP provider khi mục tiêu là ghi log.

Các câu cảnh báo trên là mẫu thực tế được SLF4J công bố, không phải API chung cho mọi phiên bản.

## 8. Logback: đọc internal status và sửa appender sai

Nếu dùng **Logback Classic**, cấu hình thường nằm trong `logback.xml` hoặc được framework điều khiển bằng file khác. Ví dụ tối thiểu cho một backend console:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là cấu hình của ứng dụng đã có Logback dependency, không chạy bằng `java` thuần JDK. Các lỗi phổ biến:

- `<appender-ref ref="CONSOLE"/>` trỏ tới tên không tồn tại hoặc appender không khởi tạo được.
- Định nghĩa `FileAppender` với path không thể ghi; kiểm tra directory, quyền và lỗi I/O.
- Sai tên lớp appender/encoder, sai XML hoặc đặt file cấu hình ở vị trí không được nạp.
- Root level cho phép INFO nhưng logger con bị cấu hình `OFF`/`ERROR`; hoặc `additivity=false` trong khi logger con không tham chiếu appender.
- Hai appender cùng xử lý một event do cả logger con và root đều được cấu hình; cần xem cả additivity và tập tham chiếu.

**Bật thông tin chẩn đoán:** Logback có hệ thống internal status; nó tự in status khi gặp warning/error trong quá trình parse cấu hình, trừ một số trường hợp đã đăng ký status listener. Trong môi trường thử nghiệm, có thể thêm `debug="true"` vào phần tử `<configuration>` để nhận status chi tiết:

~~~xml
<configuration debug="true">
    <!-- Các appender, logger và root giữ như cấu hình đang kiểm tra. -->
</configuration>
~~~

Đừng để diagnostic quá chi tiết bật lâu trong production nếu có nguy cơ gây nhiễu hoặc lộ đường dẫn/nội dung cấu hình. Khắc phục warning/error bằng cách sửa **nguyên nhân**: đường dẫn, dependency, tên appender và tham chiếu.

**Reload cấu hình:** Logback có hỗ trợ scan/reconfigure tùy cấu hình và phiên bản. Khi cấu hình mới sai, cần xem status thông báo đang dùng cấu hình nào và chạy smoke test; không mặc định việc sửa file trên disk đồng nghĩa ứng dụng đã nạp thành công.

## 9. Log4j 2: status logger, đường dẫn cấu hình và plugin

Log4j 2 Core sử dụng hệ thống plugin để tạo appender, filter, layout và thành phần cấu hình. Một lỗi plugin hoặc thuộc tính có thể được ghi vào **Status Logger**, là logger nội bộ tách khỏi logger của ứng dụng.

Khi cần điều tra, khởi động tạm thời với:

~~~bash
java -Dlog4j2.debug=true -cp "app-and-dependencies/*" com.example.Main
~~~

`-Dlog4j2.debug=true` bật thông tin Status Logger ở mức chi tiết để thấy việc phát hiện/nạp cấu hình và lỗi nội bộ. Lệnh trên dùng tên classpath minh họa; phải thay bằng classpath và main class thực tế của ứng dụng. Log4j 2 cũng hỗ trợ thuộc tính `log4j2.statusLoggerLevel` để điều khiển mức status; trên các phiên bản mới, thuộc tính `status` trong thẻ `<Configuration>` đã deprecated từ 2.24.0. Nên cấu hình mức status bằng system property để có tác dụng ngay từ đầu startup.

Một file **log4j2.xml** console cơ bản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đây là cấu hình cần Log4j 2 Core, không áp dụng cho JUL/Logback. Có thể chỉ định file cấu hình riêng bằng property của Log4j 2:

~~~bash
java -Dlog4j2.configurationFile=conf/log4j2.xml -cp "app-and-dependencies/*" com.example.Main
~~~

Khi lỗi, hãy xác định:

1. Đang dùng Log4j 2 Core hay API được chuyển tiếp sang backend khác? Cấu hình Log4j 2 không điều khiển được một Logback backend chỉ vì ứng dụng import API khác.
2. Config file nào được Log4j phát hiện? Sai file extension, sai đường dẫn hoặc mount có thể khiến framework sử dụng mặc định hay fallback.
3. Có lỗi plugin/class/layout/appender trong Status Logger không?
4. `AppenderRef` có trỏ đúng appender đã định nghĩa không? Root/logger level và filter có chặn event trước khi tới appender không?
5. Nếu có `monitorInterval` để reload, việc reconfigure đã diễn ra và ứng dụng còn ghi log được không?

**Không sử dụng cấu hình Log4j 1.x như thể là Log4j 2.** Tên class, cấu trúc file và một số cơ chế tương thích không giống nhau. Xem đúng tài liệu theo phiên bản backend hiện có.

## 10. Sai cấu hình level, filter và propagation: lỗi dễ chẩn đoán nhầm

Một sự kiện log có thể bị loại ở nhiều nơi khác nhau:

~~~text
Logger tại lớp nghiệp vụ
   │ logger level / filter
   ▼
Logger cha hoặc root (nếu propagation/additivity)
   │ root level / filter theo framework
   ▼
Handler/Appender
   │ handler/appender threshold / filter
   ▼
Layout / Encoder
   ▼
File / Console / Network
~~~

Điều cần nhớ:

- `DEBUG`/`FINE` có thể bị chặn trước khi event đến sink. Hạ level của appender **chưa đủ** nếu logger phía trước vẫn lọc.
- Trong JUL, `Logger.setUseParentHandlers(false)` chặn lan truyền tới handler của parent; trong Logback/Log4j 2, `additivity=false` có tác dụng tương tự ở mức liên kết tới logger cha, nhưng cú pháp khác nhau.
- Trùng log thường do cùng sự kiện đi qua **nhiều appender/handler**. Hãy xác định luồng đi của sự kiện trước khi xóa nhầm appender.
- Format/pattern lỗi có thể làm thiếu trường (timestamp, trace ID, MDC) dù event được ghi. Cần kiểm tra mã format và cấu hình context, không coi mọi trường rỗng là lỗi truyền event.
- Khi dùng async appender, producer enqueue thành công không đồng nghĩa sink nhận thành công; nếu queue đầy hoặc shutdown quá nhanh, log có thể bị mất vì chính sách backpressure/discard.

Ví dụ sai:

~~~properties
# JUL: root ghi INFO, ConsoleHandler chỉ ghi WARNING trở lên.
.level=INFO
java.util.logging.ConsoleHandler.level=WARNING
~~~

Nếu cần hiển thị INFO ở console thì phải đặt **cả hai** threshold cho phép INFO, với điều kiện ConsoleHandler đã thực sự được gắn vào root logger.

## 11. Lỗi đường dẫn và quyền ghi ở appender

Khi backend dùng file logging, các cấu hình tưởng hợp lệ vẫn có thể không tạo log:

- **Đường dẫn tương đối:** `logs/app.log` thường được giải theo working directory của tiến trình, có thể khác giữa IDE, service, cron và container.
- **Thư mục không tồn tại hoặc không có quyền:** user chạy JVM thiếu quyền tạo file/thư mục, cấu hình volume chỉ đọc, SELinux/AppArmor hoặc chính sách container cản trở.
- **Quota/ổ đĩa đầy:** appender khởi tạo thành công nhưng bắt đầu thất bại sau vài giờ; phải kiểm tra disk/quota và error channel của appender.
- **File lock/rotation:** nhiều JVM ghi vào một path hoặc rollover không tương thích gây tranh chấp, dữ liệu trộn/đổi tên file ngoài ý muốn.
- **Remote sink:** DNS, xác thực, chứng chỉ TLS, timeout, giới hạn hàng đợi làm cho việc gửi log thất bại sau khi đã parse cấu hình thành công.

Không chỉ kiểm tra `Files.isWritable(path)` trước startup: trạng thái quyền có thể thay đổi và phép kiểm trước không chứng minh thao tác mở/ghi thành công. Cần xử lý đúng ngoại lệ của thao tác I/O, thu nhận lỗi ở framework status logger, và có alert khi sink mất khả dụng.

Khi kiểm thử, phân biệt **dòng đã được ứng dụng phát**, **sự kiện backend chấp nhận** và **bản ghi đã xuất hiện ở hệ thống nhận**.

## 12. Fallback, rollback và reload có kiểm soát

Chiến lược xử lý tùy yêu cầu nghiệp vụ:

| Ngữ cảnh | Xử lý phù hợp |
| --- | --- |
| Công cụ local hoặc log chẩn đoán không bắt buộc | Có thể fallback sang console với cảnh báo rõ và nhãn degraded |
| Dịch vụ production cần chẩn đoán nhưng không yêu cầu audit bền vững | Giữ cấu hình tốt cuối cùng nếu được hỗ trợ; nếu không thể thì cân nhắc fail startup hoặc fallback theo chính sách vận hành |
| Hệ thống cần log kiểm toán bắt buộc | Không được âm thầm tiếp tục trong trạng thái mất kênh audit; fail closed hoặc dùng kênh ghi bền vững đã được thiết kế |
| Tải cao với async appender | Giám sát dropped events, queue depth, backpressure và drain/shutdown; fallback không tự chữa lỗi mất log đã xảy ra |
| Reload khi đang chạy | Validate config mới, kích hoạt theo cơ chế framework, phát event thử, kiểm tra output rồi rollback nếu không đạt |

Trong hệ thống yêu cầu sẵn sàng cao, **không tự động thử lại liên tục bằng vòng lặp không giới hạn** khi cấu hình không hợp lệ. Lỗi cú pháp sẽ không tự hết vì retry. Phân biệt lỗi **permanent** (sai key, sai XML, thiếu provider) với lỗi **transient** (remote sink tạm mất mạng) để quyết định retry/backoff.

Một quy trình triển khai an toàn:

1. Lint/parse và validate cấu hình trong CI trên đúng phiên bản logging framework của ứng dụng.
2. Kiểm tra dependency resolution và một bản ghi thử đi đến sink giả lập hoặc filesystem test.
3. Triển khai canary/rolling update nhỏ, quan sát internal status và tỷ lệ log xuất hiện.
4. Nếu lỗi, rollback cấu hình/build đã tốt; tránh chỉ sửa file của một replica rồi quên các replica khác.
5. Sau khắc phục, xác nhận số bản ghi bị thiếu (nếu có thể) và ghi nhận thời gian khoảng trống quan sát.

Không ghi mật khẩu hoặc nội dung secret trong thông báo invalid config, stack trace gửi ra nơi công cộng, hoặc full dump của mọi environment variable.

## 13. Kiểm thử tự động để phát hiện sai cấu hình sớm

Không nên chỉ kiểm tra file “có tồn tại”. Một bộ kiểm thử hữu ích bao gồm:

1. **Cấu hình hợp lệ:** ứng dụng khởi tạo logging, ghi INFO/WARN đúng sink, trường cấu trúc và format đúng kỳ vọng.
2. **Thiếu file:** nhận diện lỗi có ý nghĩa; nếu policy fail-fast thì tiến trình có exit code phi 0.
3. **Sai cú pháp:** XML sai thẻ, properties sai kiểu; status/internal error phải có chỉ báo, không lặng lẽ coi thành công.
4. **Sai level/key:** thuộc tính không thuộc whitelist hoặc bị viết nhầm cần bị phát hiện ở bước validate.
5. **Thiếu/nhiều provider SLF4J:** kiểm tra dependency tree và cảnh báo startup của backend thực tế.
6. **Không ghi được sink:** thử directory không có quyền, đầy quota hoặc mô phỏng IO error bằng test double; health signal phải cho thấy lỗi.
7. **Propagation/filter:** kiểm tra một event có đúng số lần xuất hiện, không bị lọc sai hoặc ghi trùng.
8. **Reload/rolling deployment:** kiểm tra cấu hình mới được áp dụng, rollback được và logger tiếp tục hoạt động khi tải có log đồng thời.
9. **Async và graceful shutdown:** kiểm tra sự kiện còn trong queue, chính sách discard, timeout và flush của appender.

Đối với kiểm thử file, dùng file/directory riêng từng test, xóa tài nguyên sau khi đóng appender, đừng phụ thuộc vào file log của máy nhà phát triển hoặc đường dẫn cố định dễ xung đột.

Có thể dùng **smoke event** có mã nhận diện duy nhất (ví dụ `event=logging_smoke_check` và `buildId`) để kiểm tra hành trình từ ứng dụng đến collector. Tách cấu hình kiểm tra và policy vận hành để không phát sinh thông tin nhạy cảm trong log.

## 14. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| “App startup thành công nên log cũng đúng” | SLF4J NOP/provider mặc định hoặc sink hỏng vẫn có thể cho app chạy | Đọc internal status và xác nhận event ở sink |
| Dùng logger bị hỏng để báo lỗi logger | Mất luôn bằng chứng khởi tạo thất bại | Ghi cảnh báo tối thiểu qua stderr/status logger |
| Chỉ sửa level của root | Handler/appender filter vẫn chặn | Kiểm tra toàn bộ đường event |
| Giảm level production xuống TRACE vô hạn | Tăng tải, lộ dữ liệu, khó điều tra | Bật có thời hạn và rollback sau xử lý |
| Không kiểm tra classpath/transitive dependency | Nhiều provider hoặc sai phiên bản | Xem runtime dependency graph, chỉ giữ provider phù hợp |
| Đọc cấu hình trong repo mà bỏ qua môi trường chạy | Service nạp config khác, mount cũ hoặc profile override | Xác nhận đường dẫn config hiệu lực trong JVM |
| Bỏ qua error khi mở/ghi file | Log bị mất âm thầm | Báo lỗi IO, health metric, cảnh báo và fallback có chính sách |
| Tự reload JUL bằng `readConfiguration()` tùy tiện | Reset logger/handler đã tồn tại | Dùng API cập nhật thích hợp và kiểm tra tác động |
| Đóng appender khi còn worker async | Mất log tồn đọng | Dừng producer, drain queue, stop context theo lifecycle |
| Thêm NOP provider để ẩn warning | Cảnh báo biến mất nhưng ứng dụng không ghi log | Dùng provider thực sự ghi ra sink mong muốn |
| Coi flush là lưu bền vững | Crash/kill vẫn có thể mất dữ liệu | Dùng durable storage/ACK khi có yêu cầu độ bền |

## 15. Câu hỏi tự luyện và gợi ý đáp án

1. Một ứng dụng gọi `log.info(...)` bình thường nhưng không có log trong production. Vì sao chỉ kiểm tra `isInfoEnabled()` chưa đủ?
2. Khi dùng JUL, vì sao `.level=FINE` không đảm bảo `FINE` xuất hiện nếu `ConsoleHandler.level=WARNING`?
3. SLF4J 2.x cảnh báo “No SLF4J providers were found”. Điều này thường có nghĩa gì và phải kiểm tra gì tiếp?
4. Vì sao một logger bị `additivity=false` có thể im lặng khi nó không có appender riêng?
5. Logback và Log4j 2 có kênh nào để chẩn đoán lỗi khởi tạo mà không phụ thuộc logger ứng dụng?
6. Khi file log không tạo ra trong container, phải kiểm tra những gì ngoài cú pháp file XML?
7. Vì sao không nên dựa vào `Thread.sleep(...)` để xác nhận async logging đã ghi đủ?
8. Khi nào có thể fallback sang console, và khi nào cần fail startup?

**Gợi ý:** (1) event có thể bị chặn ở filter/appender/sink hoặc provider; (2) handler lọc lần nữa; (3) SLF4J có thể đang dùng NOP, cần thêm một provider phù hợp; (4) đã chặn truyền lên parent nên không còn đích; (5) Logback internal status, Log4j 2 Status Logger; (6) đường dẫn, working directory, quyền, disk/quota, mount, lock, network; (7) chờ một khoảng thời gian không tạo barrier/drain; (8) tùy chính sách nghiệp vụ và yêu cầu audit/durability.

## 16. Tài liệu tham khảo chính thức

- [JDK 17 — LogManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): nạp config JUL, `java.util.logging.config.file`, tác động của `readConfiguration()` và `updateConfiguration()`.
- [JDK 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): level, filter, handler và `setUseParentHandlers`.
- [SLF4J — Diagnostic messages](https://www.slf4j.org/codes.html): thiếu provider, nhiều provider, khác biệt giữa API 1.7 và 2.x.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): cú pháp cấu hình và internal status.
- [Logback — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, effective level và additivity.
- [Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html): `log4j2.debug`, `log4j2.statusLoggerLevel` và diagnostic startup.
- [Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): config file, root/logger/appender, plugin và reload.

