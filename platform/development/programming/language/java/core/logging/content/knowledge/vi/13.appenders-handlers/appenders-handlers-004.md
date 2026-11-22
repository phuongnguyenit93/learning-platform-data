# File appender trong Java Logging

## 1. File appender là gì?

Trong kiến trúc **Appender và handler** của Java Core Logging, **file appender** là thành phần nhận các bản ghi log đã được hệ thống logging chấp nhận, chuyển chúng thành dữ liệu có định dạng và **ghi xuống một tệp**. Nó khác Console Appender/ConsoleHandler vốn ghi ra stdout hoặc stderr.

Ví dụ một file có thể chứa:

~~~text
INFO  event=service.ready service=catalog
INFO  event=order.accepted orderId=ORD-17 requestId=req-42
WARN  event=inventory.slow dependency=stock
~~~

Đây là các dòng minh họa, **không phải một định dạng mặc định chung** cho mọi thư viện Java.

Ba nhóm công nghệ thường gặp:

- **Log4j 2:** File Appender, RollingFile Appender và các biến thể của Log4j Core.
- **Logback:** FileAppender và RollingFileAppender, thường nằm dưới API gọi log của SLF4J.
- **java.util.logging (JUL):** dùng lớp **FileHandler**, một Handler có sẵn trong JDK. Nó thực hiện vai trò ghi file tương tự nhưng có API và cơ chế cấu hình riêng.

Một file appender **không tự quản lý toàn bộ logging**: Logger, Level, Filter, Layout/Encoder/Formatter, file manager và collector cùng quyết định bản ghi có thực sự tới file và được lưu hay không.

**Khi nên dùng:** ứng dụng cần tệp log cục bộ để điều tra, một agent phải tail file để gửi về hệ thống tập trung, hoặc chính sách triển khai yêu cầu lưu log trên volume riêng. Với ứng dụng chạy trong container đã có pipeline thu thập stdout/stderr, log file cục bộ có thể làm tăng công việc quản trị và khả năng mất log khi container biến mất.

## 2. Vị trí của file appender trong pipeline

~~~text
Mã ứng dụng
  logger.info("event=order.accepted ...")
                 |
                 v
           Logger / LoggerConfig
           kiểm tra level, Filter
                 |
        +--------+------------+
        |                     |
        v                     v
  Console Appender        File Appender
  Filter riêng            Filter riêng
        |                     |
  Layout/Encoder          Layout/Encoder
        |                     |
  stdout/stderr           FileOutputStream
                              |
                         filesystem
                              |
                         log collector
                         nếu có cấu hình
~~~

Phân biệt:

| Thành phần | Chức năng |
| --- | --- |
| **Logger** | Nhận lời gọi ghi log, xác định level và ngữ cảnh nguồn |
| **Level/Filter** | Cho qua hoặc loại các bản ghi theo quy tắc |
| **Appender/Handler** | Đưa bản ghi tới một đích cụ thể |
| **Layout/Encoder/Formatter** | Chuyển LogEvent/LogRecord thành chuỗi hoặc bytes |
| **File manager/stream** | Mở file, ghi, flush, quản lý tài nguyên |
| **Collector/agent** | Đọc file và gửi sang nền tảng lưu trữ nếu được triển khai |

Một sự kiện có thể được đưa đồng thời đến **Console** và **File**. Các Filter gắn riêng ở File có thể bỏ một số sự kiện mà Console vẫn ghi. Nếu **Logger đã chặn bản ghi**, Appender không thể khôi phục nó.

Ở những framework hỗ trợ Logger hierarchy, **additivity** hoặc Handler của Logger cha có thể đưa log tới nhiều nơi. Nếu file xuất các dòng trùng, cần kiểm tra các đường AppenderRef/Handler trước khi cho rằng ứng dụng gọi cùng lệnh log nhiều lần.

## 3. File Appender khác RollingFile Appender

**File Appender thông thường** ghi vào một file, có thể tiếp tục tăng dung lượng trong toàn bộ thời gian tiến trình chạy. **RollingFile Appender** bổ sung chính sách chuyển sang file mới và quản lý các file lưu trữ.

| Công nghệ | Loại | Có rolling tích hợp? |
| --- | --- | --- |
| Log4j 2 | File | Không |
| Log4j 2 | RollingFile | Có |
| Log4j 2 | RandomAccessFile | Không |
| Log4j 2 | RollingRandomAccessFile | Có |
| Logback | FileAppender | Không |
| Logback | RollingFileAppender | Có |
| JUL | FileHandler | Có chế độ luân phiên theo kích thước và số file |

**Rolling** có thể dựa vào thời gian, kích thước hoặc cả hai; nó còn có thể nén file lịch sử và xóa theo chính sách lưu trữ. **Append** chỉ có nghĩa nối dữ liệu vào cuối file, **không đồng nghĩa rolling**.

Với Log4j 2, file appender có các biến thể File, RandomAccessFile và MemoryMappedFile với đặc tính I/O riêng. Không mặc định RandomAccessFile hoặc MemoryMappedFile luôn phù hợp hơn File: chi phí phụ thuộc buffer, kích thước thông điệp, filesystem, concurrency và yêu cầu vận hành.

## 4. append=true, append=false và rủi ro mất log

**append=true** thường có nghĩa **ghi thêm** vào file tồn tại khi được mở; **append=false** có thể truncate file cũ khi mở.

~~~text
File cũ:
INFO service.started run=1

Restart với append=true:
INFO service.started run=1
INFO service.started run=2

Restart với append=false:
INFO service.started run=2
~~~

Đây là sơ đồ hành vi khái niệm. Nếu có rolling, tên file hiện tại và file archive còn chịu ảnh hưởng policy riêng.

Một lỗi phổ biến là để **append=false** trên production rồi restart làm mất bản ghi trước đó. Ngược lại, **append=true** mà không có rotation có thể khiến file ngày càng lớn cho đến khi đầy disk.

**Cần quyết định đồng thời:** ghi thêm hay ghi đè, khi nào quay file, bao nhiêu file được giữ, nơi nào thu thập và lưu trữ lâu dài.

## 5. Đường dẫn file và quyền trên hệ điều hành

Ví dụ tên file:

~~~text
logs/application.log
/var/log/catalog/application.log
D:/logs/catalog/application.log
~~~

**Đường dẫn tương đối** như logs/application.log thường tính từ **working directory của JVM**. Chạy từ IDE, Maven, systemd hoặc container có thể cho kết quả khác. **Đường dẫn tuyệt đối** ổn định hơn về vị trí, nhưng đòi hỏi cấu hình phù hợp môi trường.

Các kiểm tra thiết yếu:

1. Process có quyền tạo và ghi file không?
2. Thư mục cha có tồn tại hoặc backend có thể tạo nó không?
3. Khi rolling, process có quyền đổi tên, nén, xóa archive không?
4. File nằm trên volume persistent hay trên filesystem ephemeral của container?
5. Có quota và cảnh báo khi dung lượng thấp không?
6. File permissions/owner đã hạn chế quyền đọc dữ liệu log chưa?
7. Đường dẫn có bị lấy trực tiếp từ input người dùng và gây **path traversal** không?
8. Nếu nhiều JVM ghi cùng một file, đã có phương án concurrency, lock và rollover an toàn chưa?

Log4j 2 File Appender có thể tạo thư mục cha khi cần, nhưng không áp giả định này cho mọi hệ thống. Với deployment, **cấu hình path qua environment hoặc deployment** thường an toàn hơn hard-code đường dẫn máy cá nhân vào code thư viện.

## 6. Layout, Encoder, Formatter và charset

Các framework dùng tên khác nhau:

| Nền tảng | Thành phần định dạng | Ví dụ |
| --- | --- | --- |
| Log4j 2 | **Layout** | PatternLayout, JsonTemplateLayout |
| Logback | **Encoder** | PatternLayoutEncoder, JSON encoder thích hợp |
| JUL | **Formatter** | XMLFormatter, SimpleFormatter, custom Formatter |

Dữ liệu có thể là text:

~~~text
2026-11-09T12:00:00Z INFO catalog event=order.accepted orderId=ORD-17
~~~

hoặc JSON:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "catalog",
  "event": "order.accepted",
  "orderId": "ORD-17"
}
~~~

**File appender không tự biến log thành JSON**; cần Layout/Encoder/Formatter hỗ trợ. Các khối trên chỉ là minh họa chứ không phải output mặc định.

Một bản ghi tốt thường có **timestamp, level, logger/service, event, requestId hoặc jobId, outcome, reasonCode** và thông tin Throwable nếu cần điều tra lỗi. Chọn **UTF-8** thống nhất với log collector để không bị hỏng tiếng Việt.

Dữ liệu người dùng chưa được làm sạch có thể chứa newline hoặc ký tự điều khiển gây **log injection**. Encoder cần escape dữ liệu thích hợp; không log secret, token hoặc payload nhạy cảm ngay từ nguồn.

## 7. Cấu hình File Appender của Log4j 2

Nếu runtime thật sự dùng **Log4j Core**, tạo file **src/main/resources/log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE"
              fileName="logs/application.log"
              append="true"
              bufferedIo="true"
              immediateFlush="true">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %logger - %msg%n"
                charset="UTF-8"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Giải thích từng thành phần:

- **File** là plugin Appender của Log4j 2, tên **FILE** được Root Logger tham chiếu.
- **fileName** là đường dẫn file; với tên tương đối, cần xác định working directory.
- **append=true** ghi thêm vào file hiện có.
- **bufferedIo=true** dùng bộ đệm nhằm giảm số thao tác ghi.
- **immediateFlush=true** xả dữ liệu đã đệm sau event theo cơ chế backend, **không đảm bảo fsync/durability**.
- **PatternLayout** tạo thời gian, mức, tên Logger và thông điệp. Timestamp thực tế thay đổi nên không có một file output cố định trong ví dụ XML này.
- **Root level=info** chỉ cho các bản ghi đạt ngưỡng tới Appender. Filter khác vẫn có thể từ chối.
- XML không khai báo Console Appender nên không tự tạo log ứng dụng trên stdout.

Mã ứng dụng dùng Log4j API:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public class CatalogService {
    private static final Logger LOG =
            LogManager.getLogger(CatalogService.class);

    public void started() {
        LOG.info("event=service.ready service=catalog");
    }
}
~~~

Đây là **một lớp thành phần**, không có main() để chạy độc lập. Cần **log4j-api** khi biên dịch và **log4j-core** tương thích khi chạy để XML có hiệu lực.

### Các thuộc tính File Appender khác

- **createOnDemand:** có thể trì hoãn tạo file cho đến khi một event thực sự tới Appender.
- **bufferSize:** đặt kích thước bộ đệm.
- **ignoreExceptions:** mặc định thường true; khi lỗi ghi, backend có thể báo qua **Status Logger** thay vì ném vào mã nghiệp vụ.
- **locking:** áp dụng file lock khi cần, nhưng semantics phụ thuộc OS và có overhead.
- **filePermissions/fileOwner/fileGroup:** dùng được khi filesystem và quyền hệ thống hỗ trợ.

Chỉ File Appender như ví dụ trên sẽ không tự quay file theo ngày hoặc kích thước.

## 8. Cấu hình FileAppender trong Logback

Nếu ứng dụng dùng **SLF4J + Logback**, cấu hình phải dùng cú pháp Logback như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <immediateFlush>true</immediateFlush>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Khác biệt:

1. Logback dùng class **ch.qos.logback.core.FileAppender**, không phải plugin **File** của Log4j.
2. Đường dẫn khai báo qua **file**, không phải thuộc tính fileName.
3. Logback dùng **encoder** để chuyển event thành bytes; không copy cú pháp PatternLayout của Log4j.
4. **append** và **immediateFlush** quản lý cách ghi tương ứng với Logback.
5. **root level=INFO** và **appender-ref** xác định Logger nào đẩy event tới FILE.
6. FileAppender đơn thuần không tự rolling khi file lớn.

Mã SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accepted(String orderId) {
        LOG.info("event=order.accepted orderId={}", orderId);
    }
}
~~~

Đây là lớp component minh họa, không phải chương trình độc lập. Muốn thực sự ghi vào file phải có **provider Logback phù hợp ở runtime**, đúng file logback.xml và quyền ghi.

**Không thêm slf4j-simple vào ứng dụng đã dùng Logback** chỉ để có một đích ghi khác; thường nên dùng một provider và cấu hình thêm Appender bên trong backend đó.

## 9. Rolling file cho ứng dụng chạy lâu

Một service chạy liên tục nhiều ngày có thể tạo file lớn. **RollingFileAppender** được dùng để quản lý file hiện tại và file lịch sử theo các điều kiện:

- **Time-based:** quay file theo lịch hoặc ranh giới thời gian.
- **Size-based:** quay khi đạt ngưỡng kích thước.
- **Kết hợp:** giới hạn kích thước mỗi file trong từng chu kỳ thời gian.
- **Archive:** dùng pattern chứa ngày/chỉ số, có thể nén gzip.
- **Retention:** giới hạn lịch sử, tổng dung lượng hoặc tuổi file tùy backend.

### Đoạn cấu hình RollingFile cho Log4j 2

~~~xml
<RollingFile name="ROLL"
             fileName="logs/application.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz"
             append="true">
    <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1"/>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
    <DefaultRolloverStrategy max="7"/>
</RollingFile>
~~~

Đặt đoạn trên trong **Appenders** của cấu hình Log4j 2 và tham chiếu tên ROLL ở **Loggers**. **DefaultRolloverStrategy max=7 không tự có nghĩa giữ đúng 7 ngày**; nó là giới hạn cửa sổ chỉ số theo chiến lược. Muốn xóa archive theo tuổi hoặc tổng dung lượng cần quy tắc retention khác phù hợp.

### Đoạn cấu hình RollingFile cho Logback

~~~xml
<appender name="ROLL"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

Đặt trong **configuration**, thêm root/appender-ref và kiểm tra policy/version Logback thực tế.

**Rolling không tự giải quyết mọi vấn đề retention.** Khi quay file, cần kiểm chứng tên archive, quyền tạo/xóa, cách agent tail file cũ, việc nén và hành vi sau restart. Hệ thống collector cũng phải theo được file mới để không làm mất chuỗi sự kiện.

## 10. FileAppender và logrotate ngoài tiến trình

Một File Appender có thể giữ file descriptor đã mở. Nếu chương trình bên ngoài đổi tên hoặc di chuyển file, ứng dụng có thể tiếp tục ghi vào đối tượng file cũ chứ không tự mở đường dẫn mới.

Tài liệu Apache Log4j 2 lưu ý File Appender **không cung cấp cơ chế buộc reopen file từ ứng dụng ngoài**. Phương pháp **copy-truncate** có thể làm mất event giữa thời điểm copy và truncate.

Hệ quả:

1. Ưu tiên dùng **RollingFileAppender của backend** nếu muốn appender tự quản lý rotation.
2. Không để **logrotate và RollingFileAppender cùng quản lý một file** trừ khi đã thiết kế, thử và chấp nhận hệ quả.
3. Nếu phải dùng rotation bên ngoài, cần chính sách reopen/copy-truncate rõ ràng, đánh giá mất hoặc trùng event.
4. Kiểm tra collector sử dụng inode/file identity, cách theo dõi file đã rename và lúc file bị truncate.

Một log file được quay vòng đúng ở phía writer chưa chắc đã được collector thu thập đầy đủ ở phía reader.

## 11. Buffering, immediateFlush và lưu bền

Một lời gọi log có thể qua nhiều bộ đệm:

~~~text
Ứng dụng -> LogEvent -> Appender/Handler
         -> buffer của framework
         -> OutputStream
         -> buffer filesystem của OS
         -> thiết bị lưu trữ
~~~

**Buffered I/O** gom nhiều bytes để giảm thao tác ghi nhỏ. **Flush** đẩy bytes đang đệm xuống tầng kế tiếp. **fsync/force** có mục tiêu đồng bộ dữ liệu ở mức khác, nhưng kết quả cuối còn phụ thuộc filesystem, mount và thiết bị.

**immediateFlush=true không có nghĩa bytes đã được ghi bền xuống ổ đĩa.** Đây là điểm quan trọng khi yêu cầu lưu log sau crash hoặc mất điện.

| Lựa chọn | Có lợi | Cần đánh đổi |
| --- | --- | --- |
| immediateFlush=true | Giảm dữ liệu lưu trong buffer backend | Có thể tốn I/O hơn |
| immediateFlush=false | Có thể tăng throughput | Có thể mất dữ liệu đệm khi shutdown không sạch |
| Buffer lớn | Gom nhiều event hơn | Dung lượng bộ nhớ và độ trễ flush |
| Async logging | Giảm công việc I/O trong thread nghiệp vụ | Queue đầy, shutdown, backpressure |
| File network volume | Chia sẻ dữ liệu qua host | Latency và consistency/locking phức tạp |

Nếu yêu cầu log lưu bền rất cao, không chỉ bật một cờ flush mà phải thiết kế cả **backend, OS, volume, collector, retry/backup** và kiểm thử trường hợp tiến trình chết đột ngột.

## 12. Ghi file từ nhiều thread và nhiều JVM

Một Appender thường được backend thiết kế để nhiều thread trong **cùng JVM** sử dụng. Nhưng điều này **không bảo đảm** hai process JVM cùng ghi hoặc rolling một file an toàn.

- **Nhiều thread, một Appender:** backend thường điều phối ghi nhưng vẫn cần benchmark latency.
- **Nhiều Appender cùng file:** dễ tạo bản ghi trùng hoặc xung đột cấu hình.
- **Hai JVM cùng file:** atomic append/locking phụ thuộc appender và hệ điều hành.
- **Nhiều pod cùng network filesystem:** thêm vấn đề lock qua mạng và rollover cạnh tranh.

Logback có **prudent mode** để hỗ trợ nhiều JVM dùng chung file theo cơ chế khóa, nhưng **có chi phí hiệu năng** và hạn chế khi dùng rolling/nén. Log4j 2 có tùy chọn **locking** cho File Appender, nhưng không xem advisory lock trên một số POSIX filesystem là đảm bảo mọi tiến trình đều tuân thủ.

Thiết kế thường dễ vận hành hơn là **file riêng theo instance** hoặc mỗi instance xuất stdout/stderr, sau đó collector hợp nhất theo service, instance, requestId và traceId.

## 13. JUL FileHandler: lựa chọn có sẵn trong JDK

**java.util.logging.FileHandler** là Handler ghi file của Java SE. Nó kế thừa **StreamHandler** và có thể ghi một file hoặc tập file luân phiên theo dung lượng.

Constructor minh họa:

~~~java
FileHandler oneFile = new FileHandler("logs/app.log", true);
FileHandler rotating = new FileHandler(
        "logs/app-%g.log", 10_000_000, 5, true);
~~~

Đây là snippet, không chạy riêng nếu thiếu import, xử lý IOException, thư mục và lệnh close().

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **pattern** | Mẫu tên file |
| **limit** | Ngưỡng bytes gần đúng của mỗi file |
| **count** | Số file luân phiên |
| **append** | Ghi thêm vào file hiện có |
| **level/filter** | Ngưỡng và quy tắc nhận bản ghi |
| **formatter** | Định dạng; mặc định **XMLFormatter** |
| **encoding** | Charset khi ghi |

Các token tên file của JUL:

- **%t**: thư mục temporary.
- **%h**: thư mục home của user.
- **%g**: generation number cho rotation.
- **%u**: unique number để tránh xung đột với file đang được sử dụng.
- **%%**: dấu % thực.

Khác RollingFileAppender của Logback/Log4j 2, FileHandler của JUL chỉ có rotation theo kích thước/số file theo cấu hình chuẩn. Nó không tự cung cấp mọi chính sách lịch, nén và giữ file lịch sử nâng cao.

## 14. Ví dụ Java 17+ chạy độc lập: ghi và đọc lại file log

Chương trình này chỉ cần **JDK**, không cần dependency bên ngoài. Nó dùng một thư mục tạm riêng để tránh ghi đè file của người dùng.

Mục tiêu:

1. Logger ở level ALL, Handler ở INFO.
2. Log FINE bị Handler chặn; INFO và WARNING được ghi.
3. Formatter có định dạng xác định và dùng **formatMessage(record)** cho tham số **{0}** của JUL.
4. Đóng FileHandler trước khi đọc lại dữ liệu.
5. Đọc file UTF-8, in nội dung ra stdout để kiểm chứng.

Lưu toàn bộ mã dưới tên **FileLogDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileLogDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.file");

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("file-log-demo-");
        Path file = dir.resolve("application.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        FileHandler handler = new FileHandler(file.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(handler);
        try {
            LOG.fine("event=cache.hit");
            LOG.info("event=service.ready service=catalog");
            LOG.log(Level.INFO,
                    "event=order.accepted orderId={0}", "ORD-17");
            LOG.warning("event=inventory.slow dependency=stock");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        List<String> lines =
                Files.readAllLines(file, StandardCharsets.UTF_8);
        System.out.println("records=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac FileLogDemo.java
java FileLogDemo
~~~

**Stdout chính xác**:

~~~text
records=3
INFO | event=service.ready service=catalog
INFO | event=order.accepted orderId=ORD-17
WARNING | event=inventory.slow dependency=stock
~~~

### Giải thích từng kết quả

1. **Files.createTempDirectory()** tạo thư mục mới; tên thực tế biến thiên nhưng không xuất ra stdout nên không ảnh hưởng các dòng expected.
2. **LOG.setUseParentHandlers(false)** ngăn Handler trên Logger cha in thêm một bản ghi lên stderr.
3. **LOG.setLevel(Level.ALL)** cho FINE qua bước kiểm tra của Logger.
4. **handler.setLevel(Level.INFO)** chặn FINE nhưng cho INFO/WARNING đi vào file.
5. **formatMessage(record)** thay **{0}** bằng **ORD-17**; đây là cú pháp tham số của JUL, không phải placeholder **{}** của SLF4J.
6. **setEncoding("UTF-8")** kết hợp **StandardCharsets.UTF_8** giúp writer và reader đồng nhất charset.
7. **handler.close()** flush và đóng file/giải phóng tài nguyên trước khi Files.readAllLines() đọc.
8. **records=3** vì có hai INFO và một WARNING; FINE bị loại bởi FileHandler.
9. Ba dòng INFO/WARNING trên stdout là do vòng for **in nội dung file vừa đọc**. Bản thân FileHandler không viết ra stdout.
10. Ví dụ để nguyên file tạm để người học có thể mở xem. Trong test thực tế cần cleanup sau khi handler đã được đóng.

Muốn kiểm chứng khác biệt về level, thử đổi **handler.setLevel(Level.WARNING)**. Khi đó file chỉ chứa WARNING dù Logger vẫn ở ALL.

## 15. Cấu hình JUL bằng logging.properties

Trong ứng dụng dùng JUL và không tự thay thế Handler bằng code, có thể khai báo:

~~~properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.pattern=logs/application-%u.%g.log
java.util.logging.FileHandler.limit=10000000
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
~~~

Khởi động ứng dụng đã biên dịch và có lớp main **com.example.Main**:

~~~bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
~~~

Đây là mẫu khởi động ứng dụng riêng, **không phải lệnh chạy FileLogDemo**. FileLogDemo cố ý tạo FileHandler riêng, tắt Handler cha và dùng Formatter cố định.

Lưu ý:

- **handlers** chỉ định Handler của Logger gốc theo cấu hình LogManager.
- **.level** của root và **FileHandler.level** của Handler là hai ngưỡng riêng.
- **pattern** có **%u/%g** để xử lý unique filename và generation khi rotating.
- **limit/count** làm file quay vòng khi gần ngưỡng bytes; không phải retention theo ngày.
- **append=true** giữ file cũ theo cơ chế FileHandler.
- **SimpleFormatter** thay XMLFormatter mặc định; output có timestamp/nguồn có thể thay đổi.
- Đường dẫn **logs/** phải phù hợp working directory và quyền ghi của process.
- Cấu hình được đọc khi LogManager khởi tạo; framework hoặc code ứng dụng có thể ghi đè.

Không đưa các thuộc tính JUL FileHandler vào logback.xml hoặc log4j2.xml: tên key, API và cách xử lý khác nhau.

## 16. Exception và stack trace trong file

Một bản ghi lỗi nên giữ **Throwable** để backend có thể in stack trace và cause chain:

**Log4j 2 / SLF4J:**

~~~java
try {
    persistOrder(orderId);
} catch (RuntimeException ex) {
    LOG.error("event=order.persist.failed orderId={}", orderId, ex);
    throw ex;
}
~~~

**JUL:**

~~~java
logger.log(Level.SEVERE,
        "event=order.persist.failed orderId=" + orderId, ex);
~~~

Đây là snippet phụ thuộc biến/phương thức đã khai báo. Nếu chỉ dùng **ex.getMessage()**, bản ghi thường không có full stack trace và cause chain. Tuy nhiên **truyền Throwable cũng chưa đủ** nếu Layout/Encoder/Formatter được chọn cố tình bỏ thông tin exception.

Nếu file log có stack trace nhiều dòng, collector cần hiểu **multiline** hoặc dùng encoder có trường exception thích hợp. Không nên log cùng một stack trace ở repository, service rồi controller nếu cả ba chỉ rethrow một lỗi; một lỗi sẽ bị đếm thành nhiều sự cố.

## 17. Lỗi ghi file và giám sát

| Sự cố | Dấu hiệu và hệ quả |
| --- | --- |
| Permission denied | Không tạo/mở được file |
| Disk full hoặc quota | Appender không thể ghi thêm |
| Filesystem read-only | Ghi file bị chặn sau một thay đổi deployment |
| Archive path sai | Rollover/nén không thành công |
| File descriptor cũ | Sau rename bên ngoài, writer có thể không ghi file tên mới |
| Process chết đột ngột | Bytes chưa flush hoặc queue async chưa drain có thể mất |
| Nhiều process cùng file | Race/lock và rotation có thể gây lỗi |
| Collector không tail đúng | Thiếu/trùng log trong hệ tập trung |

Với Log4j 2, **ignoreExceptions** thường mặc định **true**: lỗi ghi file có thể được báo qua **Status Logger** thay vì ném ngược tới câu lệnh LOG.info(). Nhờ đó việc ghi log không nhất thiết làm request thất bại, nhưng người vận hành cũng có thể không phát hiện hệ thống đang mất log nếu không giám sát backend.

Với JUL, **Handler.ErrorManager** là cơ chế xử lý/report lỗi I/O; không mặc định logger.info() luôn ném IOException khi disk full.

**Cần kiểm tra end-to-end:** phát một event với mã xác định, đọc file tại đúng đường dẫn và xác nhận collector thu được nó. File hiện hữu không chứng minh pipeline còn hoạt động.

## 18. File appender trên container và hệ nhiều instance

Với service có nhiều replica:

- Để mỗi instance **ghi file riêng**, hoặc xuất stdout/stderr riêng để platform thu thập.
- Không giả định một volume chung và append=true đủ an toàn cho nhiều JVM.
- Nếu dùng network filesystem, đánh giá lock, latency, consistency và rollover trên đúng môi trường.
- Với container có filesystem tạm, file có thể biến mất sau restart hoặc thay pod.
- Nếu log được gửi cả console và file, collector có thể đọc hai nguồn và **đếm trùng**.
- Thiết kế event, requestId/traceId và instance ID để có thể tìm log xuyên service.
- Kiểm thử shutdown khi ứng dụng có Async Appender hoặc buffer lớn.

Trong nhiều triển khai container, **Console Appender + collector của platform** đơn giản hơn quản lý file cục bộ. File appender vẫn phù hợp khi có yêu cầu riêng, nhưng cần bảo đảm log file thực sự được mount/thu thập hoặc lưu trữ theo chính sách.

## 19. Bảo mật, chi phí và retention

File log thường được lưu và sao lưu nhiều lần, nên phải kiểm soát dữ liệu:

1. Không ghi **password, token, cookie, API key**, thông tin thẻ hoặc payload nhạy cảm.
2. Tránh để file trong web root hoặc thư mục có quyền đọc rộng.
3. Dùng **permission/owner** phù hợp cho file hiện tại, archive và backup.
4. Áp dụng **retention** và giám sát dung lượng, tránh đầy đĩa từ log lưu lượng lớn.
5. Ghi **event name ổn định** và ID cần thiết thay vì cả object dữ liệu người dùng.
6. Escape newline/control character để giảm rủi ro **log injection**.
7. Xem xét việc exception message của thư viện có thể chứa dữ liệu nội bộ.
8. Đừng dùng Filter như cơ chế che bí mật duy nhất; bản ghi được giữ vẫn có thể lộ thông tin.
9. Với audit trail có yêu cầu pháp lý, cần thiết kế tính đầy đủ, toàn vẹn và chống chỉnh sửa, không mặc định file appender cung cấp sẵn.
10. Theo dõi chi phí file/collector/backup và đặt giới hạn phù hợp với tải.

**File log không tự an toàn chỉ vì nằm trên ổ đĩa nội bộ.** Phải quản lý quyền truy cập và vòng đời dữ liệu ở mọi nơi bản ghi được sao chép.

## 20. Troubleshooting theo hiện tượng

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy file | Sai path, sai backend, createOnDemand hoặc config không nạp | Kiểm tra working directory và appender runtime |
| File rỗng | Logger/Filter không đưa event tới file | Kiểm tra level, filter và AppenderRef |
| Chỉ thấy ERROR/WARN | Ngưỡng cao hoặc Filter từ chối INFO | Kiểm tra tất cả stage |
| File ở vị trí lạ | Relative path | Xác minh cwd của JVM |
| Restart làm mất log cũ | append=false | Đổi cấu hình khi muốn giữ lịch sử |
| File lớn không ngừng | FileAppender không rolling | Dùng RollingFile/retention |
| Log trùng | Additivity/nhiều appender/collector đọc kép | Kiểm tra đường đi |
| Stack trace biến mất | Chỉ log message hoặc formatter bỏ Throwable | Dùng overload nhận Throwable |
| Tiếng Việt bị lỗi | Charset writer/reader khác nhau | Kiểm tra UTF-8 đầu-cuối |
| Chạy IDE được, service không được | Quyền process, mount, cwd khác | Chạy test dưới user service |
| Rollover không chạy | Sai policy, archive path/permission | Kiểm tra config và diagnostics |
| Sau logrotate file mới rỗng | Writer giữ descriptor cũ | Kiểm tra cơ chế reopen/rolling |
| Sau crash thiếu log cuối | Buffer/async chưa flush | Kiểm tra chính sách flush và shutdown |
| Không có lỗi Java dù file không ghi | Appender báo qua Status Logger | Quan sát diagnostics của backend |

**Trình tự khắc phục gợi ý:** xác minh backend → sự kiện thật sự được gọi → Logger level/Filter → AppenderRef/Handler → đường dẫn và quyền ghi → encoding/Formatter → Status Logger/ErrorManager → rolling và collector.

## 21. Những nhầm lẫn thường gặp

**1. FileAppender tự động giới hạn dung lượng.** Không đúng với FileAppender thông thường; cần RollingFile hoặc giải pháp quản trị bên ngoài.

**2. append=true nghĩa là rolling.** Không; append chỉ nối dữ liệu khi mở file.

**3. flush đồng nghĩa fsync.** Không; bytes có thể mới ở OS cache.

**4. Hai JVM cùng ghi vào một file là an toàn mặc định.** Cần hiểu khóa và filesystem; thường file riêng mỗi instance dễ kiểm soát hơn.

**5. Chỉ cần file tồn tại là logging hoạt động.** File có thể rỗng hoặc đã ngừng nhận dữ liệu.

**6. Logback XML và Log4j XML có thể thay thế nhau.** Không; chúng có cấu trúc, class, encoder/layout khác nhau.

**7. Có File Appender là tự có JSON.** Không; JSON phụ thuộc Layout/Encoder phù hợp.

**8. Throwable chỉ cần được nối vào message.** Không; cần truyền Throwable đúng API và formatter xuất nó.

**9. Logrotate ngoài tiến trình luôn an toàn.** Không; rename/copy-truncate có thể làm mất hoặc giữ file descriptor cũ.

**10. Log file nội bộ không chứa thông tin nhạy cảm.** Có thể có; cần data minimization, phân quyền và retention.

## 22. Checklist triển khai File Appender

1. **Xác định backend:** Log4j 2, Logback hay JUL và file cấu hình thực sự được tải.
2. **Chọn đường dẫn:** làm rõ cwd, mount, owner, quyền tạo/ghi/xóa file.
3. **Đặt append đúng:** tránh truncate không chủ đích sau restart.
4. **Chọn rolling/retention:** biết khi nào quay file và bao nhiêu lịch sử được giữ.
5. **Cấu hình Level/Filter:** kiểm tra nguồn Logger và điểm nhận.
6. **Chọn định dạng:** timestamp, level, event, context ID và Throwable nếu cần.
7. **Thống nhất charset:** UTF-8 từ writer tới collector.
8. **Đo I/O:** buffer, immediateFlush, async và độ trễ thực tế.
9. **Tránh tranh chấp:** nhiều JVM/pod phải có đường ghi và rotation an toàn.
10. **Giám sát lỗi:** disk/quota/permission/Status Logger và trạng thái collector.
11. **Bảo vệ dữ liệu:** không log secret, kiểm soát archive/backup/retention.
12. **Test end-to-end:** ghi sự kiện, readback file, thử restart/rollover/crash phù hợp.

**Kết luận:** **File appender** là mắt xích ghi các sự kiện đã qua Logger/Filter vào hệ thống file. Sử dụng đúng đòi hỏi hiểu **Logger → Appender/Handler → Layout/Encoder/Formatter → file**, phân biệt **append và rolling**, và nhớ rằng **flush không bảo đảm lưu bền**. Đó là nền tảng để log có thể phục vụ điều tra, không làm đầy đĩa và không tạo rủi ro dữ liệu.

## 23. Tài liệu tham khảo chính thức

- [Apache Log4j 2 — File appenders](https://logging.apache.org/log4j/2.x/manual/appenders/file.html): File/RandomAccessFile, append, buffering, locking.
- [Apache Log4j 2 — Rolling file appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): RollingFile, TriggeringPolicy và rollover.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): buffering, immediateFlush và ignoreExceptions.
- [Logback — Console and File appenders](https://logback.qos.ch/manual/appenders-console-file.html): FileAppender, encoder, append, prudent.
- [Logback — Rolling File appenders](https://logback.qos.ch/manual/appenders-rolling.html): RollingFileAppender và retention.
- [Oracle Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): FileHandler, pattern, limit/count, Formatter và API.
