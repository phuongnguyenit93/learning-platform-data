# Encoding file trong Java Logging

## 1. Encoding file là gì?

**Encoding file** là cách biến ký tự trong thông điệp log thành các byte được lưu trên đĩa. Trong Java, dữ liệu văn bản thường được xử lý dưới dạng **String**; khi một Logger phát sự kiện, Handler hoặc Appender chọn định dạng văn bản rồi ghi ra byte bằng một **Charset** như UTF-8.

Ví dụ thông điệp:

~~~text
INFO | Đăng nhập thành công ở Đà Nẵng 🌿
~~~

Thông điệp có thể được ghi chính xác vào file UTF-8, nhưng nếu người đọc mở nó bằng bảng mã không phù hợp, các dấu tiếng Việt có thể thành ký tự lạ. Hiện tượng này thường gọi là **mojibake**.

Lỗi encoding không chỉ làm log khó đọc. Nó còn có thể:
- Làm bộ máy tìm kiếm không tìm thấy đúng từ khóa hoặc tên.
- Làm parser CSV, JSON lines hoặc hệ thống thu thập log hiểu sai dữ liệu.
- Gây khác biệt giữa môi trường Windows, Linux, container và CI.
- Khiến việc so sánh snapshot, phân tích ngoại lệ hoặc đối chiếu nhiều dịch vụ trở nên không tin cậy.
- Dẫn tới mất ký tự nếu một bước decode hoặc encode âm thầm thay dữ liệu không hợp lệ.

**Mục tiêu:** Chọn bảng mã rõ ràng tại nơi **ghi**, bảo đảm nơi **đọc** dùng cùng bảng mã và kiểm tra cả **byte thực tế** lẫn **văn bản đọc lại**. Với file log text hiện đại, UTF-8 thường là lựa chọn phù hợp.

## 2. Charset, Formatter, Encoder và FileHandler

Cần phân biệt các tầng trong pipeline:

~~~text
Java String / Throwable / metadata
              |
              v
Logger phát sự kiện
              |
              v
LogRecord (JUL) hoặc logging event (backend khác)
              |
              v
Formatter / Layout -> tạo chuỗi đã trình bày
              |
              v
Charset Encoder -> chuyển ký tự thành byte
              |
              v
FileHandler / FileAppender -> ghi byte xuống file
              |
              v
File trên đĩa -> collector / decoder / parser -> nội dung đọc được
~~~

Trong thực tế, thứ tự gọi các lớp nội bộ khác nhau theo backend, nhưng **hai quyết định vẫn tách biệt**: định dạng thông điệp và mã hóa thành byte.

| Khái niệm | Vai trò |
| --- | --- |
| **String / Unicode** | Dữ liệu ký tự bên trong chương trình |
| **Charset** | Quy tắc ánh xạ giữa ký tự và byte, ví dụ UTF-8 |
| **Encoder** | Chuyển văn bản thành byte |
| **Decoder** | Chuyển byte trở lại thành văn bản |
| **Formatter (JUL)** | Tạo chuỗi hiển thị từ LogRecord |
| **Layout / Encoder (Logback, Log4j 2)** | Xác định cấu trúc sự kiện và có thể cấu hình Charset đầu ra |
| **Handler / Appender** | Chịu trách nhiệm ghi sự kiện ra đích, ví dụ file hoặc console |

**Encoding không phải encryption.** UTF-8 giúp ký tự được biểu diễn đúng, không che giấu hay mã hóa bảo mật dữ liệu. File log chứa token hoặc thông tin thanh toán vẫn cần redaction, phân quyền và bảo vệ lưu trữ.

## 3. Vì sao thường dùng UTF-8?

**UTF-8** là encoding Unicode sử dụng số byte thay đổi theo ký tự. Nó có nhiều lợi ích cho file log:

- Hỗ trợ chữ tiếng Việt, ký tự các ngôn ngữ khác và emoji.
- Phần ký tự ASCII thông dụng có biểu diễn byte giống ASCII.
- Phù hợp với JSON, nhiều parser, container log collector và công cụ vận hành.
- Giảm phụ thuộc vào locale hoặc code page hệ điều hành.
- Thuận tiện cho việc chuẩn hóa pipeline giữa nhiều dịch vụ.

Tuy nhiên, **một ký tự không nhất thiết bằng một byte**. Ví dụ:
- Ký tự ASCII thường là một byte UTF-8.
- Chữ tiếng Việt có dấu có thể cần nhiều byte.
- Một emoji như **🌿** được lưu bằng bốn byte UTF-8, nhưng trong Java String có thể cần hai đơn vị UTF-16.

Vì vậy **String.length() không phải kích thước file**. Khi tính dung lượng lưu trữ hoặc giới hạn xoay file, phải tính trên byte thực tế.

### Các charset khác

| Charset | Đặc tính | Rủi ro đối với log |
| --- | --- | --- |
| **UTF-8** | Unicode, phổ biến cho text/JSON | Cần reader decode cùng UTF-8 |
| **UTF-16LE / UTF-16BE** | Dựa trên hai byte cho nhiều code unit | Nhiều công cụ đọc dòng text giả định UTF-8 hoặc ASCII |
| **UTF-16** | Có quy tắc về thứ tự byte, có thể dùng BOM | Phải hiểu endian và khả năng hỗ trợ của reader |
| **ISO-8859-1** | Bảng mã một byte với tập ký tự hạn chế | Không biểu diễn đầy đủ tiếng Việt/emoji |
| **windows-1252** | Bảng mã legacy | Không phải UTF-8 và không bao phủ toàn Unicode |
| **Charset.defaultCharset()** | Charset mặc định tại runtime | Không phải hợp đồng portable cho mọi phiên bản Java và môi trường |

Khi làm việc với một file legacy đang ở charset cũ, phải xác định **charset thực sự** trước khi chuyển đổi. Chỉ “mở bằng UTF-8 rồi lưu lại” không thể khôi phục dữ liệu đã bị giải mã sai.

## 4. File logging trong Java Util Logging (JUL)

JUL có sẵn trong JDK, sử dụng **java.util.logging.Logger**, **LogRecord** và **FileHandler**. FileHandler nhận bản ghi, dùng Formatter tạo văn bản rồi ghi vào file.

Ví dụ cấu hình cơ bản:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.logging.FileHandler;
import java.util.logging.SimpleFormatter;

// Phan minh hoa dat trong method co xu ly IOException.
FileHandler file = new FileHandler("logs/application.log", true);
file.setEncoding(StandardCharsets.UTF_8.name());
file.setFormatter(new SimpleFormatter());
file.setLevel(java.util.logging.Level.INFO);
logger.addHandler(file);
~~~

Đoạn trên **không phải chương trình độc lập**. Nó giả định biến **logger** đã có, thư mục **logs** tồn tại và phương thức có xử lý IOException. Trong ứng dụng thật phải tháo Handler và **close()** lúc shutdown theo đúng vòng đời.

Ý nghĩa:
- **FileHandler(pattern, append):** Mở file theo tên hoặc pattern được chọn.
- **setEncoding("UTF-8"):** Cấu hình encoding cho dữ liệu xuất.
- **setFormatter(...):** Chọn cách trình bày bản ghi, độc lập với Charset.
- **setLevel(...):** Giới hạn mức sự kiện Handler nhận.
- **Logger.addHandler(...):** Nối nguồn phát với đích file.
- **Handler.close():** Kết thúc việc ghi, flush và giải phóng tài nguyên liên quan.

Nếu không chỉ định Formatter, **FileHandler thường dùng XMLFormatter**. Điều này giải thích vì sao người mới có thể thấy file XML thay vì log một dòng theo định dạng mong muốn. Đặt UTF-8 không chuyển XML thành văn bản một dòng; cần chọn Formatter thích hợp.

**Không đổi charset giữa chừng khi đang append cùng một file.** Nếu nửa đầu file là bảng mã A và nửa sau bảng mã B, reader thường không biết cần giải mã từng phần theo cách nào. Khi đổi encoding nên chuyển sang file mới hoặc dùng kế hoạch rotation/migration.

## 5. Ví dụ Java 17 chạy độc lập: ghi file UTF-8, kiểm tra bytes

Ví dụ sử dụng hoàn toàn thư viện JDK 17, không cần Maven hay dependency ngoài. Mã:

1. Tạo một thư mục tạm.
2. Tạo FileHandler ghi UTF-8 vào file trong thư mục.
3. Ghi chuỗi có tiếng Việt và emoji.
4. Đóng Handler rồi đọc byte đã lưu.
5. So sánh byte với UTF-8 expected.
6. Giải mã bằng **CharsetDecoder** ở chế độ báo lỗi nghiêm ngặt.
7. Kiểm tra đầu file không có UTF-8 BOM.
8. In kết quả dễ kiểm chứng, sau đó dọn file tạm.

Tạo file **Utf8FileLoggingDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class Utf8FileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.file.Utf8FileLoggingDemo");

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("utf8-file-log-");
        Path path = dir.resolve("application.log");

        String message = "event=ORDER_CREATED text=Chào Đà Nẵng 🌿";
        String expected = "INFO | " + message + "\n";

        FileHandler file = new FileHandler(path.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record) + "\n";
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(file);

        try {
            LOG.info(message);
        } finally {
            LOG.removeHandler(file);
            file.close();
        }

        byte[] actualBytes = Files.readAllBytes(path);
        byte[] expectedBytes =
                expected.getBytes(StandardCharsets.UTF_8);

        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(actualBytes))
                .toString();

        boolean bom = actualBytes.length >= 3
                && (actualBytes[0] & 0xff) == 0xef
                && (actualBytes[1] & 0xff) == 0xbb
                && (actualBytes[2] & 0xff) == 0xbf;

        System.out.println(
                "UTF8_BYTES_MATCH="
                + Arrays.equals(actualBytes, expectedBytes));
        System.out.println(
                "DECODED_TEXT_MATCH=" + expected.equals(decoded));
        System.out.println("UTF8_BOM_PRESENT=" + bom);

        Files.deleteIfExists(path);
        Files.deleteIfExists(dir);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Utf8FileLoggingDemo.java
java Utf8FileLoggingDemo
~~~

**Stdout mong đợi:**

~~~text
UTF8_BYTES_MATCH=true
DECODED_TEXT_MATCH=true
UTF8_BOM_PRESENT=false
~~~

### Vì sao kết quả ổn định?

- Mã nguồn được **javac -encoding UTF-8** đọc đúng chữ tiếng Việt và emoji.
- FileHandler được chỉ định **UTF-8** riêng, không lệ thuộc default charset.
- Formatter tự viết chỉ xuất **INFO | message** và ký tự **LF**, không thêm timestamp biến thiên.
- Logger ở INFO và không truyền cho Handler cha, nên không có log mặc định xen vào stdout.
- FileHandler chỉ xuất ra file; ba dòng stdout là kết quả kiểm tra của chương trình.
- Close Handler trước khi đọc file để tránh nội dung còn đệm.
- So sánh từng byte giúp phát hiện encoding sai ngay cả khi editor có cơ chế tự sửa cách hiển thị.
- Decoder ở chế độ **REPORT** không âm thầm thay byte UTF-8 lỗi thành ký tự **�**.
- UTF-8 trong cấu hình này không sinh BOM nên kết quả **false**.
- Thư mục tạm làm cho ví dụ không cần đường dẫn cố định và không đụng file log của ứng dụng khác.

**Lưu ý:** Ví dụ có chủ đích ghi một dòng duy nhất. Trong môi trường production, Formatter thường còn có timestamp, logger name, thread, exception, request/trace ID; encoding và cách xác minh byte vẫn áp dụng tương tự.

## 6. UTF-8 qua logging.properties của JUL

Khi cấu hình JUL bằng tệp **logging.properties**, có thể đặt encoding cho FileHandler mà không cần gọi setEncoding trong từng class:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.pattern = logs/application-%u.%g.log
java.util.logging.FileHandler.limit = 10485760
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.level = INFO

java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format = %1$tFT%1$tT%1$tz | %4$s | %3$s | %5$s%6$s%n
~~~

Các thuộc tính ở đây là **cấu hình của java.util.logging**, không dùng cho Logback hoặc Log4j 2.

Giải thích:
- **FileHandler.encoding:** Charset được dùng khi ghi file.
- **FileHandler.formatter:** Lớp Formatter tạo nội dung LogRecord.
- **FileHandler.pattern:** Vị trí và mẫu tên file.
- **limit/count:** Giới hạn kích thước theo byte và số file trong vòng.
- **append:** Có thể ghi nối vào file, vì thế cần lưu ý file cũ phải có cùng format/charset.
- **SimpleFormatter.format:** Pattern nội dung, không quyết định encoding.

Đảm bảo đường dẫn **logs** có thể ghi hoặc thay bằng đường dẫn thích hợp với môi trường triển khai. Với ứng dụng đã biên dịch có class **com.example.Main**:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Đây là **lệnh mẫu**, không phải lệnh chạy Utf8FileLoggingDemo vốn tự tạo FileHandler trong code.

### Tại sao cần phân biệt Formatter và encoding?

Một file dùng SimpleFormatter có thể mã hóa UTF-8. Một file dùng XMLFormatter cũng có thể mã hóa UTF-8. Hai file **khác định dạng**, nhưng có cùng **charset**. Vì vậy khi gặp tiếng Việt sai dấu, hãy kiểm tra encoding trước khi thay toàn bộ Formatter.

Ngược lại, khi chuyển từ XML sang text trong cùng file append, nội dung có thể không còn tuân thủ một cấu trúc duy nhất. Nên dùng file mới hoặc rollover khi thay đổi format.

## 7. File encoding trong SLF4J + Logback

**SLF4J là API**, không tự quyết định byte của file. Với backend **Logback**, encoding thường được cấu hình tại **Encoder** của FileAppender hoặc RollingFileAppender.

Ví dụ **logback.xml**:

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

- **FileAppender** mở file đích.
- **PatternLayoutEncoder** tạo output text theo pattern.
- **charset=UTF-8** quyết định cách văn bản được biến thành byte.
- **root INFO** cho phép các sự kiện phù hợp đi vào appender.
- **%msg** chứa thông điệp và **%n** tạo xuống dòng.

File XML cần nằm trong runtime classpath và dự án phải có provider Logback tương thích. Đoạn cấu hình này không được áp dụng cho JUL thuần.

### RollingFileAppender và charset

Khi dùng **RollingFileAppender**, encoder vẫn quyết định charset. Việc một file được đổi tên hoặc nén **.gz** không tự biến UTF-8 thành một charset khác. Archive nén cần được giải nén trước khi đọc byte văn bản.

~~~xml
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <charset>UTF-8</charset>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
~~~

Đây là **một phần** cấu hình, cần gắn appender-ref vào root/logger thích hợp. Các con số chỉ là minh họa. Giới hạn kích thước dùng byte file, không phải String.length(). Trước khi đổi encoding của một appender đang append vào file cũ, nên triển khai theo ranh giới file/rollover mới để tránh trộn charset.

## 8. File encoding trong Log4j 2

Log4j 2 thường dùng **Layout** để định dạng và encode dữ liệu. Ví dụ **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE"
              fileName="logs/application.log"
              append="true">
            <PatternLayout
                charset="UTF-8"
                pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Có **hai khái niệm encoding**:

1. **XML declaration encoding="UTF-8":** Charset của chính tệp cấu hình XML.
2. **PatternLayout charset="UTF-8":** Charset của nội dung log được Layout gửi tới file.

**Chỉ lưu log4j2.xml dưới UTF-8 chưa bảo đảm file log đầu ra cũng là UTF-8.** Phải kiểm tra cấu hình Layout/Appender thực tế và bytes sau khi ghi.

Với một JSON layout, serializer có thể xuất một số ký tự dưới dạng escape Unicode hoặc ký tự UTF-8 trực tiếp. Đây là hai cách trình bày dữ liệu JSON có thể hợp lệ; đừng nhầm JSON escape với encoding của toàn bộ file.

## 9. Byte Order Mark (BOM) và UTF-8

**BOM** là dấu hiệu byte tùy chọn ở đầu một số file Unicode. UTF-8 BOM có dãy byte:

~~~text
EF BB BF
~~~

UTF-8 không cần BOM để xác định thứ tự byte vì bản thân UTF-8 không có chế độ endian như UTF-16LE/BE. Một số editor có thể thêm BOM, nhưng pipeline log dòng thường không cần nó.

Với file **JSON lines**, collector có thể mong dòng đầu bắt đầu ngay bằng byte của dấu **{**. Nếu BOM đứng trước dấu này, parser có thể không chấp nhận hoặc có thể thấy một ký tự U+FEFF ngoài dự kiến.

**Khuyến nghị thực tế:** Chọn **UTF-8 không BOM** cho log text/JSON lines, trừ khi hệ thống nhận yêu cầu một định dạng khác đã được tài liệu hóa. Đặc biệt **không tự thêm BOM mỗi khi append** hay mỗi khi khởi động lại: dấu BOM ở giữa file không còn là một chữ ký hợp lý của phần đầu.

Khi dùng PowerShell hoặc editor trên Windows để chuyển đổi file, cần kiểm tra cấu hình encoding của công cụ. Các phiên bản PowerShell có cách xử lý UTF-8 BOM khác nhau; đừng tin rằng file vẫn nguyên byte chỉ vì văn bản nhìn giống trước.

## 10. Source encoding, file log encoding và terminal encoding

Có ít nhất ba đích dễ bị nhầm:

~~~text
Source .java
   |
   | javac đọc theo source charset
   v
Java String trong bộ nhớ
   |
   +--> FileHandler/Encoder --> byte file log
   |
   +--> ConsoleAppender/System.out --> terminal
   |
   +--> Collector --> parser/index/storage
~~~

### Source code

Nếu Java source chứa dấu tiếng Việt, dùng **javac -encoding UTF-8** hoặc cấu hình Maven/Gradle compiler encoding. Việc này giúp compiler đọc đúng literal String.

### File log

Dùng **FileHandler.setEncoding("UTF-8")**, **Logback encoder charset** hoặc **Log4j 2 Layout charset**. Đây là hợp đồng byte của file.

### Terminal

Charset và font của terminal, cũng như các thuộc tính stdout/stderr, có thể khiến chữ hiển thị sai ngay cả khi file log hoàn toàn đúng UTF-8. **ConsoleHandler của JUL thường xuất stderr**, còn FileHandler không tự xuất console.

### Collector

Một collector có thể đọc file bằng parser, encoding hoặc cấu hình khác với chương trình ghi. Vì vậy kiểm tra trực tiếp trên file chưa đủ nếu hệ thống cần ingest log vào dashboard; phải thử toàn bộ pipeline.

### Java 17 và các phiên bản mới hơn

Ở **Java 17**, default charset có thể phụ thuộc môi trường. Từ **Java 18**, JEP 400 chuẩn hóa UTF-8 làm default charset cho nhiều API trong điều kiện tiêu chuẩn. Tuy nhiên, không nên dựa vào những mặc định đó để bỏ yêu cầu cấu hình file logging: ứng dụng dùng backend khác, collector ngoài JVM và các môi trường triển khai có thể có lựa chọn riêng.

**Không chỉ thêm tùy chọn JVM file.encoding rồi coi là đã xử lý mọi lỗi encoding.** Cấu hình tại nơi ghi file và xác nhận bytes vẫn là cách đáng tin cậy hơn.

## 11. Đọc lại file UTF-8 với Java 17

Đọc toàn bộ file text:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("logs/application.log");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là ví dụ ngắn đặt trong một method xử lý IOException, không phải chương trình độc lập.

Với file lớn, đọc theo dòng để tránh đưa toàn bộ nội dung vào RAM:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

Khi cần QA byte-level, có thể dùng **Files.readAllBytes(path)** nếu file thử đủ nhỏ, rồi so sánh với expected UTF-8 bytes.

### Vì sao strict decoder hữu ích?

~~~java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

Đoạn này giả định **bytes** và các import đã có; nó có thể ném **CharacterCodingException** khi byte không hợp lệ. Cách này phù hợp cho bài kiểm thử, chuyển đổi legacy và pipeline cần từ chối dữ liệu lỗi.

Ngược lại, khi dùng **new String(bytes, StandardCharsets.UTF_8)**, một số dãy byte không hợp lệ có thể bị thay bằng **replacement character**. Nếu chỉ kiểm tra “đọc được String”, chương trình có thể bỏ sót việc đã mất ký tự.

### Tránh default charset

~~~java
// Khong ro rang ve charset:
String unclear = new String(bytes);

// Ro rang va co the tai lap:
String explicit = new String(bytes, StandardCharsets.UTF_8);
~~~

Một lỗi phổ biến là code đọc file ở host A rồi ghi ở host B bằng default charset khác nhau. Nếu file là UTF-8, xác định UTF-8 ở cả điểm đọc lẫn ghi.

## 12. Newline, record boundary và log injection

Cùng là file UTF-8 nhưng newline có thể khác nhau:

~~~text
LF   = 0A
CRLF = 0D 0A
~~~

**System.lineSeparator()** dùng newline theo môi trường. Trong ví dụ Java 17 ở trên, Formatter cố định **\n** để kết quả byte giống nhau giữa hệ điều hành.

Các collector thường đọc log theo dòng. Nếu message chứa newline, tab hoặc các control character từ đầu vào không tin cậy, một sự kiện có thể bị tách thành nhiều dòng. Đây là vấn đề **record boundary/log injection**, không phải lỗi encoding.

Ví dụ input:

~~~text
Username: Minh
ERROR fake-event injected by input
~~~

Nếu ứng dụng ghi trực tiếp input vào message, dòng thứ hai có thể trông giống một sự kiện ERROR riêng. Cần dùng structured logging/JSON đúng chuẩn, escape hoặc sanitize các control character và không tạo JSON bằng nối chuỗi tùy tiện.

**UTF-8 đúng không tự xử lý log injection.** Encoding chỉ xác định byte, không đánh giá ý nghĩa hay độ tin cậy của nội dung.

## 13. Mojibake: tại sao file hợp lệ vẫn có thể sai nội dung?

Một byte stream UTF-8 có thể hợp lệ nhưng vẫn chứa dữ liệu đã hỏng **trước khi Logger nhận String**. Ví dụ HTTP client đọc sai charset của response, biến chữ tiếng Việt thành ký tự lạ, sau đó logger ghi nguyên String hỏng đó bằng UTF-8.

Điều này tạo ra hai loại lỗi khác nhau:

| Tình huống | Kiểm tra |
| --- | --- |
| Byte file không phải UTF-8 hợp lệ | Strict UTF-8 decoder sẽ báo lỗi |
| Byte file là UTF-8 hợp lệ nhưng nội dung sai | So sánh Unicode text với dữ liệu kỳ vọng ở nguồn phát |

Vì vậy QA tốt cần cả:
- **Bytes đúng UTF-8** so với chuỗi đầu vào gốc.
- **Text sau decode khớp** thông điệp đã được Logger định ghi.

Nếu dữ liệu đã bị chuyển thành replacement character, việc lưu lại bằng UTF-8 không thể tự khôi phục byte đã mất.

### Quy trình chẩn đoán

1. Xác định chính xác **writer**: backend JUL/Logback/Log4j 2, appender và Charset.
2. Lấy bản sao file ở dạng **bytes gốc** trước khi mở và lưu bằng editor.
3. Kiểm tra byte đầu, dấu BOM nếu có và decode UTF-8 ở chế độ REPORT.
4. Nếu file hợp lệ, kiểm tra String ngay **trước** khi logger được gọi.
5. Nếu String đã sai, kiểm tra database driver, HTTP, message queue hoặc file input.
6. Kiểm tra collector và dashboard có decode đúng Charset không.
7. Sửa tại đúng bước; tạo regression test có tiếng Việt và emoji.
8. Không tự rewrite file gốc nếu log đang dùng làm bằng chứng điều tra/audit.

Không thể luôn đoán charset nguồn chỉ từ vài ký tự lỗi. Nếu một file legacy có thể chứa nhiều encoding, cần điều tra và migration có kiểm soát.

## 14. Unicode normalization và tìm kiếm

Hai chuỗi hiển thị giống nhau chưa chắc giống code points. Một chữ có dấu có thể là ký tự dựng sẵn hoặc chữ cơ sở cộng dấu kết hợp. Cả hai đều có thể được ghi hợp lệ ở UTF-8 nhưng tạo byte khác nhau.

Java có **java.text.Normalizer**:

~~~java
String nfc = java.text.Normalizer.normalize(
        input,
        java.text.Normalizer.Form.NFC);
~~~

Đây là đoạn minh họa, yêu cầu biến input đã được khai báo.

**Normalization khác encoding.** UTF-8 không bắt buộc dùng một dạng Unicode normalization nhất định. Nếu cần tìm kiếm chuỗi có dấu nhất quán, có thể chuẩn hóa ở tầng indexing/query. Nhưng với log audit hoặc dữ liệu cần giữ nguyên bằng chứng, không nên thay đổi payload gốc một cách vô thức: giữ raw event nếu yêu cầu điều tra.

## 15. JSON lines và UTF-8

Nhiều pipeline logging production lưu một JSON object trên mỗi dòng:

~~~json
{"timestamp":"2026-11-09T12:34:56.789Z","level":"INFO","event_code":"ORDER_CREATED","message":"Đã tạo đơn ở Đà Nẵng"}
~~~

Một pipeline JSON lines tốt cần:
- File output là UTF-8 theo hợp đồng.
- Mỗi sự kiện được serialize thành JSON hợp lệ.
- Newline bên trong message được escape phù hợp thay vì tạo bản ghi mới.
- Dấu quote, backslash và control character được xử lý bằng serializer.
- Không có BOM ngoài quy ước.
- Timestamp, level, service, logger, trace ID và exception có schema rõ.
- Reader/collector dùng đúng charset, phân tích đủ field.
- Rotation/archive không làm mất hoặc trộn byte của một record.

**JSON escape và UTF-8 là hai tầng khác nhau.** Một ký tự có thể xuất hiện trực tiếp dưới dạng UTF-8 hoặc được serializer biểu diễn bằng escape Unicode; cả hai phải tuân thủ JSON parser và hợp đồng charset.

## 16. Rotation, nén và dung lượng file

Encoding có ảnh hưởng đến số byte và vì vậy ảnh hưởng tới giới hạn kích thước file.

Giả sử ứng dụng phát **1.000 sự kiện/giây**, kích thước trung bình **400 byte/sự kiện** sau khi encode:

~~~text
1.000 × 400 = 400.000 byte/giây
400.000 × 86.400 ≈ 34,56 GB/ngày dữ liệu thô
~~~

Đây là ước tính chưa tính metadata lưu trữ, indexing, sao chép hoặc nén. Với log nhiều tiếng Việt/emoji, số byte có thể khác đáng kể so với tính theo String.length().

Khi dùng FileHandler, RollingFileAppender hoặc RollingFile:
- Thiết kế quota và rotation dựa trên byte, retention và nhu cầu nghiệp vụ.
- Khi thay encoding, không append dữ liệu mới vào file có charset cũ.
- File archive **.gz** cần giải nén trước khi decode bytes thành text.
- Kiểm tra collector khi active file bị rename/truncate và một sự kiện đang được ghi.
- Giữ quyền file, thư mục, khóa và lifecycle phù hợp.
- Không coi việc đã chọn UTF-8 là đảm bảo chống mất log trong crash hoặc disk full.

## 17. Di trú file log legacy sang UTF-8

Quy trình:

1. Xác định charset cũ từ tài liệu, code writer hoặc bằng chứng kỹ thuật.
2. Bảo toàn file nguồn nguyên byte.
3. Decode theo charset nguồn với chính sách xử lý lỗi rõ ràng.
4. Encode lại sang UTF-8.
5. Kiểm tra tiếng Việt, dấu câu, ký tự đặc biệt và newline.
6. Kiểm thử parser/collector và báo cáo tìm kiếm.
7. Chuyển writer sang UTF-8 khi bắt đầu file mới hoặc sau rollover.
8. Ghi lại phương thức migration, nguồn dữ liệu và kết quả QA.

Ví dụ **chỉ dành cho file mà nguồn được xác định chính xác là windows-1252**:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("legacy.log");
Path target = Path.of("converted-utf8.log");

String text = Files.readString(
        source,
        Charset.forName("windows-1252"));
Files.writeString(target, text, StandardCharsets.UTF_8);
~~~

Đoạn này không phải chương trình độc lập và cần xử lý IOException. **Không dùng windows-1252 như một giả định cho toàn bộ dữ liệu cũ**, đặc biệt khi text có tiếng Việt. File lớn nên chuyển đổi theo luồng thay vì đọc hết vào bộ nhớ; tránh cắt rời chuỗi byte đa byte giữa hai chunk khi decode.

## 18. Kiểm thử file encoding trước khi đưa lên production

### A. Unit test

- Đưa chuỗi ASCII, tiếng Việt, ký tự CJK và emoji vào Formatter/Encoder.
- So sánh UTF-8 byte array với expected.
- Kiểm tra dấu kết thúc dòng và việc xử lý ký tự điều khiển.
- Bảo đảm không tự thêm BOM nếu hợp đồng cấm.

### B. Integration test

- Khởi động backend thật với cấu hình charset UTF-8.
- Ghi vào file tạm.
- Flush/close Handler/Appender đúng lifecycle.
- Đọc bytes, strict-decode và so sánh nội dung.
- Kiểm tra một Exception được format/ghi đúng khi dùng cùng Charset.
- Thử sau khi rollover hoặc restart trong môi trường giống production.

### C. End-to-end test với collector

- Cho agent đọc file UTF-8 vừa ghi.
- Xác minh message, logger name, level, timestamp, request ID và exception.
- Đảm bảo bộ tìm kiếm tìm được chuỗi tiếng Việt và emoji.
- Kiểm tra JSON parser, byte offset, newline và dữ liệu bị chia nhiều dòng.
- Kiểm tra retention, quyền đọc và các trường nhạy cảm không bị rò rỉ.

Đừng chỉ chụp terminal rồi kết luận file encoding PASS: terminal có thể hiển thị theo charset khác hoặc che lỗi byte bằng ký tự replacement.

## 19. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng default charset vì “máy nào cũng UTF-8” | Phụ thuộc JDK/host/tool | Chỉ định UTF-8 tại Handler/Encoder/Layout |
| Nhầm Formatter với encoding | Sửa pattern không hết lỗi dấu | Cấu hình cả bố cục và Charset |
| Đổi encoding XML config rồi tin rằng log file cũng đổi | Output vẫn theo charset appender | Kiểm tra Charset Layout/Encoder |
| Reader dùng một code page khác UTF-8 | Mojibake | Decode UTF-8 rõ ràng |
| Chỉ dùng String.length() để đo dung lượng | Ước lượng sai byte/quota | Tính byte sau encode |
| Chỉ thử ASCII | Không thấy lỗi tiếng Việt/emoji | Thêm dữ liệu đa ngôn ngữ |
| Dùng decoder thay byte hỏng im lặng | Mất dữ liệu không được phát hiện | Dùng REPORT trong QA |
| Ghi append sau khi đổi charset | Một file chứa nhiều charset | Rollover hoặc tạo file mới |
| Để BOM trong JSON lines không được hỗ trợ | Parser báo lỗi đầu file | Dùng UTF-8 không BOM theo hợp đồng |
| Đồng nhất encoding file và console | Sửa nhầm thành phần | Xác minh bytes riêng với terminal |
| Ghi raw newline từ input | Log injection, tách event | Structured logging và escaping |
| Tưởng UTF-8 là encryption | Rò rỉ dữ liệu | Redaction và phân quyền |
| Đọc file lớn bằng readAllBytes | Áp lực bộ nhớ | Stream/collector theo dòng |
| Tự đổi charset file gốc đang phục vụ audit | Mất chứng cứ | Giữ nguyên byte nguồn trước migration |
| Bỏ qua encoding của collector | Dashboard hiển thị sai | Kiểm thử end-to-end |

## 20. Checklist áp dụng Encoding file

1. Xác định đúng backend: **JUL**, **Logback**, **Log4j 2** hoặc backend khác.
2. Chọn hợp đồng charset, thường **UTF-8 không BOM** cho text/JSON lines.
3. Đặt **FileHandler.encoding=UTF-8** trong JUL, hoặc Encoder/Layout charset UTF-8 ở backend.
4. Phân biệt encoding của **source .java**, **file cấu hình XML**, **file log**, **terminal** và **collector**.
5. Kiểm tra văn bản tiếng Việt, emoji, dấu ngoặc kép, backslash, newline và các ký tự ngoài ASCII.
6. Đọc lại bytes bằng strict decoder và so với nội dung Unicode kỳ vọng.
7. Không trộn charset hoặc format khác nhau khi append vào cùng file.
8. Kiểm tra rotation, file archive, quyền ghi, quota và retention.
9. Dùng structured logging khi cần để giảm rủi ro log injection và lỗi parse.
10. Áp dụng redaction, phân quyền và chính sách bảo vệ dữ liệu; encoding không thay thế security.
11. Kiểm thử cả Windows/Linux, JDK sử dụng thực tế, CI và pipeline collector.
12. Xác minh dashboard có thể tìm kiếm/hiển thị đúng các ký tự tiếng Việt sau khi triển khai.

## 21. Câu hỏi tự kiểm tra

**1. Vì sao đổi Formatter không nhất thiết sửa lỗi tiếng Việt?**

Vì Formatter quyết định layout, còn Charset Encoder quyết định byte. Nếu reader dùng sai charset, nội dung vẫn hỏng.

**2. Cần cấu hình gì cho FileHandler JUL để ghi UTF-8?**

Dùng **setEncoding("UTF-8")** hoặc thuộc tính **java.util.logging.FileHandler.encoding = UTF-8**.

**3. Trong Logback, đặt charset ở đâu?**

Trong **encoder** của FileAppender/RollingFileAppender, ví dụ phần tử **charset** có giá trị UTF-8.

**4. Trong Log4j 2, encoding của XML header có phải encoding file log không?**

Không. XML header mô tả file cấu hình; phải xác định charset của Layout/Appender.

**5. Tại sao byte UTF-8 hợp lệ chưa chứng minh chuỗi được ghi đúng?**

Vì String có thể đã bị hỏng trước khi Logger nhận nó. Cần so sánh nội dung Unicode trước và sau khi ghi.

**6. Vì sao không nên thêm BOM khi append log?**

BOM chỉ có ý nghĩa như dấu hiệu ở đầu luồng; chèn vào giữa file có thể khiến parser thấy ký tự lạ.

**7. Vì sao emoji có thể làm String.length() khác số byte UTF-8?**

Java String dùng đơn vị UTF-16, còn UTF-8 dùng số byte biến thiên. Một emoji có thể gồm hai đơn vị UTF-16 và bốn byte UTF-8.

**8. Vì sao phải kiểm thử file và collector riêng?**

Vì writer có thể ghi đúng UTF-8 nhưng collector decode hoặc parse sai, khiến dashboard vẫn hỏng nội dung.

**Ghi nhớ:** Encoding file là hợp đồng **ký tự → byte → ký tự** giữa ứng dụng và toàn bộ pipeline quan sát. Hãy chọn **UTF-8 tường minh**, cấu hình tại đúng Handler/Encoder/Layout, kiểm tra bytes và text thực tế, tránh BOM hoặc charset pha trộn, đồng thời thử file rotation và collector để log tiếng Việt giữ nguyên ý nghĩa trên mọi môi trường.
