# ConsoleHandler trong Java Util Logging (JUL)

## 1. ConsoleHandler là gì và dùng để làm gì?

**ConsoleHandler** là một lớp trong gói **java.util.logging** của Java SE, dùng để đưa các bản ghi log do **Logger** phát sinh ra **luồng lỗi chuẩn (System.err)**. Nó là một implementation của **Handler** và kế thừa từ **StreamHandler**.

Khi chương trình chạy trên máy phát triển, terminal, máy chủ hoặc container, ConsoleHandler giúp người vận hành nhìn thấy thông tin về sự kiện, cảnh báo và lỗi ngay trong đầu ra tiến trình. Đây là một trong những Handler thông dụng nhất để bắt đầu học **Java Util Logging (JUL)** vì có sẵn trong JDK, không cần thêm dependency.

Ví dụ một bản ghi do ConsoleHandler kết hợp với formatter tùy chỉnh tạo ra:

~~~text
INFO | event=service.ready service=catalog
WARNING | event=inventory.slow dependency=stock
~~~

Đây là **định dạng minh họa do Formatter quy định**, không phải văn bản mặc định mà ConsoleHandler luôn xuất. Theo cấu hình JUL phổ biến, ConsoleHandler dùng **SimpleFormatter** và có thể bổ sung thời gian, tên nguồn, level cũng như chi tiết exception.

Ba điểm cần nhớ:

1. **Logger** quyết định một sự kiện logging có được chuyển tiếp hay không theo level và Filter.
2. **ConsoleHandler** là một đích nhận bản ghi: nó kiểm tra level/Filter riêng, sử dụng Formatter rồi ghi vào **System.err**.
3. **ConsoleHandler không tự đồng nghĩa với System.out**. Trong shell, stderr đôi khi hiển thị cùng cửa sổ với stdout, nhưng đây là hai luồng khác nhau, có thể được chuyển hướng độc lập.

INFO, WARNING và SEVERE là **mức độ của bản ghi**; ConsoleHandler là **thành phần xuất bản ghi**. Một ứng dụng có thể có nhiều Logger, mỗi Logger có thể đi tới ConsoleHandler và/hoặc các Handler khác.

## 2. ConsoleHandler ở đâu trong pipeline logging?

Kiến trúc đơn giản của JUL:

~~~text
Mã Java gọi logger.info(...), logger.warning(...), ...
                         |
                         v
                   Logger nguồn
              +--------------------+
              | Kiểm tra level     |
              | Logger Filter      |
              +--------------------+
                         |
                         v
                 Các Handler được gắn
                    /         \
                   /           \
          ConsoleHandler       FileHandler
          level + Filter       level + Filter
                |                   |
            Formatter           Formatter
                |                   |
            System.err            file
                   \
                    Có thể tới Handler của Logger cha
                    nếu useParentHandlers = true
~~~

Thứ tự cốt lõi khi một lời gọi logging trên Logger nguồn được xử lý:

1. Nếu **level hữu hiệu của Logger** chặn bản ghi, các Handler sẽ không nhận nó.
2. Nếu **Filter gắn ở Logger** từ chối, bản ghi cũng không được chuyển tiếp.
3. Từng **Handler** kiểm tra level và Filter của chính mình. ConsoleHandler ở WARNING sẽ bỏ INFO ngay cả khi Logger ở INFO hoặc ALL.
4. Nếu qua các điều kiện, ConsoleHandler sử dụng **Formatter** để chuyển **LogRecord** thành chuỗi văn bản và ghi vào stderr.
5. Nếu Logger bật **useParentHandlers**, bản ghi còn có thể được đưa tới các Handler trên Logger cha; những Handler đó áp dụng điều kiện riêng của chúng.

**Lưu ý về Logger cha:** khi một Logger con chuyển bản ghi tới Handler của Logger cha, JUL không mặc nhiên chạy lại level và Filter của mọi Logger cha. Do đó, muốn giới hạn một **đầu ra console chung**, hãy cấu hình level/Filter trên chính Handler nhận các bản ghi đó. Muốn giới hạn từ **nguồn phát sinh**, cấu hình Logger nguồn.

Một bản ghi có thể xuất trên console mà không xuất vào file, hoặc ngược lại, vì mỗi Handler có chính sách riêng.

## 3. Các lớp và API liên quan

| Thành phần | Vai trò | API thường dùng |
| --- | --- | --- |
| **Logger** | Nguồn tạo và chuyển tiếp log | Logger.getLogger(), info(), warning(), log(), addHandler() |
| **Level** | Mức độ của bản ghi và ngưỡng | Level.INFO, WARNING, SEVERE, FINE, ALL, OFF |
| **LogRecord** | Đối tượng mô tả một sự kiện | getLevel(), getMessage(), getThrown(), getLoggerName() |
| **Handler** | Abstraction nhận bản ghi và xuất ra đích | setLevel(), setFilter(), setFormatter(), publish() |
| **StreamHandler** | Handler ghi đến OutputStream | publish(), flush(), close() |
| **ConsoleHandler** | StreamHandler chuyên dùng cho console/stderr | new ConsoleHandler(), setLevel(), setFormatter() |
| **Formatter** | Chuyển LogRecord thành chuỗi hiển thị | format(LogRecord), formatMessage(LogRecord) |
| **SimpleFormatter** | Formatter dạng văn bản có sẵn | new SimpleFormatter() |
| **Filter** | Cho phép hoặc từ chối bản ghi | isLoggable(LogRecord) |
| **LogManager** | Quản lý cấu hình JUL | logging.properties, cấu hình Logger và Handler |

Constructor phổ biến:

~~~java
ConsoleHandler console = new ConsoleHandler();
~~~

Đây là **đoạn mã minh họa**; cần import **java.util.logging.ConsoleHandler** và đặt nó trong lớp/phương thức phù hợp.

**ConsoleHandler không phải công cụ ghi lệnh hoặc tương tác với terminal**. Nó nhận **LogRecord** và xuất theo một Formatter, đồng thời tuân theo các ngưỡng/Filter đã cấu hình.

## 4. ConsoleHandler mặc định ghi ra System.err

Một đặc tính thường gây nhầm lẫn: **ConsoleHandler xuất ra System.err, không phải System.out**. Cả hai có thể xuất hiện trong cùng cửa sổ terminal, nhưng chúng là các luồng khác nhau.

| Đặc điểm | System.out | System.err |
| --- | --- | --- |
| Mục đích thông dụng | Dữ liệu hoặc kết quả chính của chương trình | Chẩn đoán, cảnh báo, lỗi và thông tin vận hành |
| ConsoleHandler JUL | Không mặc định dùng | **Dùng mặc định** |
| StreamHandler tùy chỉnh | Có thể gắn tới đây | Cũng có thể gắn tới đây |
| Chuyển hướng shell | stdout (descriptor 1) | stderr (descriptor 2) |
| Xuất hiện ở terminal | Có thể cùng cửa sổ với stderr | Có thể cùng cửa sổ với stdout |

Ví dụ với một chương trình Java đã biên dịch:

~~~bash
java ConsoleHandlerDemo 2> application.err
~~~

Lệnh trên chuyển **stderr** của chương trình vào tệp **application.err** theo cú pháp redirection phổ biến của shell. Nếu chương trình chỉ xuất log bằng ConsoleHandler, bạn có thể thấy tệp chứa log trong khi stdout không chứa các dòng ấy. Đây là ví dụ về **chuyển hướng đầu ra**, không phải lời khuyên rằng mọi hệ thống production cần viết log vào tệp như vậy.

Không dựa vào việc console hiển thị cả hai luồng để khẳng định log đã xuất ra stdout. Trong test tự động, IDE, Docker hoặc hệ thống thu thập log, sự khác biệt stdout/stderr có thể quyết định nơi bản ghi được giữ và cách gán nhãn.

**Nếu yêu cầu thực sự là ghi sang stdout**, một giải pháp JUL là dùng **StreamHandler(System.out, formatter)** với cơ chế flush phù hợp. ConsoleHandler không có một setter công khai đơn giản để đổi đích System.err thành System.out; không nên giả vờ rằng **console.setOutputStream(System.out)** là API có thể gọi từ mã ứng dụng bất kỳ.

## 5. Cấu hình level: Logger và ConsoleHandler có hai ngưỡng

Theo mặc định của **ConsoleHandler**, giá trị cấu hình **java.util.logging.ConsoleHandler.level** là **INFO** nếu không có thuộc tính nào ghi đè. Đây là **ngưỡng của Handler**, không tự đặt ngưỡng cho mọi Logger trong ứng dụng.

Các mức chuẩn thông dụng:

| Mức JUL | Giá trị số | Nếu Handler ở INFO |
| --- | ---: | --- |
| SEVERE | 1000 | Được xem xét |
| WARNING | 900 | Được xem xét |
| INFO | 800 | Được xem xét |
| CONFIG | 700 | Bị chặn |
| FINE | 500 | Bị chặn |
| FINER | 400 | Bị chặn |
| FINEST | 300 | Bị chặn |

**Level.ALL** mở ngưỡng, còn **Level.OFF** tắt tại thành phần đó. Nếu chỉ đặt:

~~~java
console.setLevel(Level.FINE);
~~~

thì ConsoleHandler sẽ cho FINE vượt qua **ngưỡng của Handler**. Nhưng nếu Logger nguồn vẫn đang ở INFO, bản ghi FINE đã bị Logger chặn từ trước nên ConsoleHandler không thể khôi phục.

Ví dụ:

~~~java
logger.setLevel(Level.FINE);
console.setLevel(Level.INFO);

logger.fine("event=cache.hit");       // Handler không xuất
logger.info("event=service.ready");   // Có thể xuất
logger.warning("event=storage.slow"); // Có thể xuất
~~~

Đây là **snippet minh họa**, giả định Logger đã gắn console và không có Filter loại bản ghi.

Muốn nhìn thấy cả FINE trên console, phải bảo đảm **Logger và Handler** đều cho mức đó qua:

~~~java
logger.setLevel(Level.FINE);
console.setLevel(Level.FINE);
~~~

Dù vượt ngưỡng, bản ghi vẫn có thể bị **Filter** từ chối hoặc lỗi ở đầu ra. Ngoài ra, Logger có thể thừa hưởng level hữu hiệu từ Logger cha khi **getLevel()** trả về null; kiểm tra mỗi Handler riêng khi điều tra log bị mất.

## 6. Formatter quyết định dòng chữ ConsoleHandler xuất

**ConsoleHandler chỉ là đích xuất**, còn **Formatter** quyết định hình thức của bản ghi. JUL thường dùng **SimpleFormatter** cho ConsoleHandler nếu không được cấu hình cách khác.

Một số khác biệt:

- **SimpleFormatter** hiển thị thông tin thời gian, nguồn và thông điệp theo format cấu hình; có thể hiển thị stack trace khi LogRecord có Throwable.
- **Formatter tùy chỉnh** có thể chỉ in event và level, hoặc đưa thêm định danh yêu cầu, thời gian UTC, tên service.
- Khi dùng **Formatter.formatMessage(record)**, các tham số JUL như **{0}**, **{1}** có thể được thay bằng giá trị trong LogRecord qua **MessageFormat**.
- Khi chỉ dùng **record.getMessage()** trong Formatter, chuỗi tham số có thể chưa được mở rộng.
- Khi thay formatter để đầu ra ngắn hơn, **đừng vô tình làm mất Throwable, cause chain hoặc các trường quan trọng**.

Ví dụ một Formatter tối giản:

~~~java
Formatter compact = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | " + formatMessage(record)
                + System.lineSeparator();
    }
};
console.setFormatter(compact);
~~~

Đây là **snippet**, giả định các import và biến **console** đã có. Formatter này chủ động bỏ thời điểm, tên nguồn và stack trace; nó phù hợp minh họa đầu ra cố định, **không nên dùng nguyên xi cho mọi trường hợp production**.

### Đầu ra mặc định có cố định không?

Không nên đoán exact output của SimpleFormatter trong mọi môi trường: nội dung có thể phụ thuộc **thời điểm, tên Logger/lớp/phương thức nguồn, locale, múi giờ và cấu hình format**. Khi muốn một bài thực hành có kết quả kiểm chứng chính xác, dùng Formatter đơn giản, không chứa giá trị biến thiên.

## 7. Ví dụ Java 17+ chạy độc lập với ConsoleHandler thật

Ví dụ này dùng **java.util.logging.ConsoleHandler** trực tiếp, thay vì giả lập console bằng println hoặc chỉ dùng StreamHandler. Nó minh họa:

- Logger có ngưỡng **FINE**.
- ConsoleHandler ban đầu có ngưỡng **INFO**, nên một bản ghi FINE không xuất.
- **Filter của ConsoleHandler** bỏ đúng sự kiện **health.ping**.
- Formatter in một dòng ngắn và xử lý tham số **{0}** của JUL.
- Khi nâng ngưỡng Handler lên WARNING, INFO không còn xuất nhưng WARNING vẫn đi qua.
- Log được ghi vào **stderr**; chương trình không chủ động ghi gì vào stdout.

Lưu file **ConsoleHandlerDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ConsoleHandlerDemo {
    private static final Logger LOG =
            Logger.getLogger(ConsoleHandlerDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);

        Filter excludeHealthyPing =
                record -> !"health.ping".equals(record.getMessage());
        console.setFilter(excludeHealthyPing);

        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(console);
        try {
            LOG.fine("event=cache.lookup");
            LOG.info("health.ping");
            LOG.info("event=service.ready service=catalog");
            LOG.log(Level.INFO,
                    "event=job.completed jobId={0}", "job-42");
            LOG.warning("event=inventory.slow dependency=stock");

            console.setLevel(Level.WARNING);
            LOG.info("event=job.queued jobId=job-43");
            LOG.warning("event=inventory.retry attempt=2");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
~~~

Dùng **JDK 17 trở lên**, biên dịch và chạy:

~~~bash
javac ConsoleHandlerDemo.java
java ConsoleHandlerDemo
~~~

**Đầu ra stderr chính xác về các dòng và thứ tự** (không có dữ liệu do chương trình in vào stdout):

~~~text
INFO | event=service.ready service=catalog
INFO | event=job.completed jobId=job-42
WARNING | event=inventory.slow dependency=stock
WARNING | event=inventory.retry attempt=2
~~~

### Giải thích từng lời gọi

| Lời gọi | Logger FINE | Handler level | Handler Filter | Kết quả |
| --- | --- | --- | --- | --- |
| FINE event=cache.lookup | Qua | INFO → chặn | Không cần xét tiếp | Không in |
| INFO health.ping | Qua | INFO → qua | Loại đúng health.ping | Không in |
| INFO service.ready | Qua | INFO → qua | Cho qua | In INFO |
| INFO job.completed, tham số {0} | Qua | INFO → qua | Cho qua | In INFO đã thay job-42 |
| WARNING inventory.slow | Qua | INFO → qua | Cho qua | In WARNING |
| INFO job.queued | Qua | WARNING → chặn | Không cần xét tiếp | Không in |
| WARNING inventory.retry | Qua | WARNING → qua | Cho qua | In WARNING |

**Tại sao ví dụ có đầu ra ổn định?**

1. **LOG.setUseParentHandlers(false)** tránh handler trên Logger cha ghi trùng ra stderr.
2. **LOG.setLevel(Level.FINE)** cho phép FINE qua ngưỡng Logger, làm rõ rằng bản ghi đầu tiên bị **Handler**, không phải Logger, loại bỏ.
3. **console.setLevel(Level.INFO)** và **console.setFilter(...)** là hai điều kiện độc lập. Một bản ghi phải vượt cả hai.
4. **new ConsoleHandler()** vẫn ghi ra stderr. Đổi Formatter không chuyển đích sang stdout.
5. **formatMessage(record)** thay **{0}** bằng **job-42** trong thông điệp thứ hai được xuất. Với JUL, tham số dạng **{0}** khác placeholder **{}** thường thấy của SLF4J.
6. ConsoleHandler **flush sau khi publish** theo hành vi của lớp; không cần override publish() như thường làm với một StreamHandler minh họa tự tạo.
7. **console.close()** của ConsoleHandler được thiết kế để flush nhưng **không đóng System.err**; removeHandler() trước khi đóng giúp tháo Handler khỏi Logger nguồn.
8. Formatter dùng **System.lineSeparator()**, vì vậy ký tự xuống dòng theo nền tảng có thể khác nhau, nhưng **nội dung bốn dòng** phía trên vẫn giữ nguyên.
9. Ví dụ không sử dụng đồng hồ, Thread, dữ liệu người dùng hoặc random nên không có phần giá trị biến thiên trong thông điệp.

Chỉ cần JDK; không dùng Maven, Gradle hoặc thư viện logging bên ngoài để chạy chương trình này.

## 8. ConsoleHandler, StreamHandler và FileHandler khác nhau thế nào?

| Tiêu chí | ConsoleHandler | StreamHandler | FileHandler |
| --- | --- | --- | --- |
| Đích mặc định/đích thiết kế | System.err | OutputStream được cấu hình | Tệp log |
| Có sẵn trong Java SE | Có | Có | Có |
| Có level/Filter/Formatter | Có | Có | Có |
| Ghi stdout trực tiếp từ mã thông thường | Không phải mục tiêu mặc định | Có thể qua constructor nhận System.out | Không |
| Flush sau mỗi publish | Có, theo implementation của ConsoleHandler | Không nên mặc định kỳ vọng nếu không chủ động flush | Theo cơ chế của FileHandler |
| Đóng đích khi close | ConsoleHandler không đóng System.err | close() có thể đóng OutputStream | Đóng stream/file đang quản lý |
| Use case | Chẩn đoán trên terminal, stderr của tiến trình | Ghi tới một stream cụ thể | Lưu log vào tệp có cấu hình riêng |

**Không dùng System.out.println() thay ConsoleHandler** cho log ứng dụng: println không có Level, Filter, Formatter, Logger hierarchy hay cơ chế thu thập thống nhất. Dùng JUL giúp kiểm soát mức log và mục đích xuất mà không trộn log vận hành với dữ liệu đầu ra của chương trình.

Nếu dùng **StreamHandler(System.out, formatter)**, hãy hiểu rằng StreamHandler có bộ đệm và **close() có thể đóng luôn System.out**. Có thể chủ động flush hoặc thiết kế Handler phù hợp vòng đời tiến trình; đừng sao chép bừa logic **close()** của ConsoleHandler sang StreamHandler.

FileHandler là công cụ JUL khác cho tệp và rotation, nhưng nó không bảo đảm một chính sách lưu log tập trung hoàn chỉnh. Trong hệ thống container, nhiều đội ngũ chọn stdout/stderr rồi để runtime/collector tiếp nhận; phải cấu hình theo môi trường thực tế.

## 9. Cấu hình ConsoleHandler bằng logging.properties

JUL có thể đọc cấu hình qua **LogManager** từ tệp properties khi khởi tạo. Với chương trình sử dụng cấu hình JUL mặc định và **không tự ghi đè Logger/Handler trong mã**, một tệp **logging.properties** điển hình:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding=UTF-8
~~~

Ý nghĩa:

- **handlers=java.util.logging.ConsoleHandler**: cấu hình một ConsoleHandler tại Logger gốc.
- **.level=INFO**: đặt level ở Logger gốc; các Logger không có level riêng có thể thừa hưởng mức hữu hiệu này.
- **java.util.logging.ConsoleHandler.level=INFO**: đặt ngưỡng riêng của ConsoleHandler.
- **java.util.logging.ConsoleHandler.formatter=...SimpleFormatter**: chọn Formatter có sẵn của JUL.
- **java.util.logging.ConsoleHandler.encoding=UTF-8**: chỉ định bảng mã đầu ra nếu môi trường đích phù hợp; phải kiểm tra trình xem log cũng đọc đúng encoding.

Giả sử ứng dụng có class chính đã biên dịch là **com.example.Main**, có thể khởi động với:

~~~bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
~~~

Đây là **ví dụ lệnh khởi động một ứng dụng có lớp com.example.Main**, không phải lệnh chạy ví dụ ConsoleHandlerDemo. **ConsoleHandlerDemo** cố ý tạo Handler riêng, gắn Formatter/Filter riêng và tắt Handler cha, nên cấu hình root ConsoleHandler trong logging.properties không quyết định đầu ra ví dụ đó.

### Lọc logger cụ thể qua properties

Một Logger tên **com.example.orders** có thể được cấu hình ngưỡng:

~~~properties
com.example.orders.level=FINE
~~~

Nhưng nếu ConsoleHandler vẫn ở INFO, các bản ghi FINE của com.example.orders có thể vẫn không xuất tại Handler đó. Muốn chúng hiện lên console, cần đặt level thích hợp trên **cả nguồn phát và Handler nhận**, cùng các Filter liên quan.

### Tùy chỉnh mẫu hiển thị của SimpleFormatter

Có thể cấu hình chuỗi định dạng của SimpleFormatter bằng thuộc tính **java.util.logging.SimpleFormatter.format**, ví dụ:

~~~properties
java.util.logging.SimpleFormatter.format=%4$s: %5$s%6$s%n
~~~

Trong mẫu định dạng này, **%4$s** là level, **%5$s** là thông điệp đã được format và **%6$s** là chuỗi Throwable/stack trace nếu có; **%n** là xuống dòng theo nền tảng. Đây là cú pháp formatter của JUL qua **String.format**, không phải cú pháp tham số log **{0}**.

Kiểm tra phiên bản JDK/thiết lập logging đang chạy khi thay đổi thuộc tính format; đừng sao chép một mẫu sai khiến mất Throwable hoặc mất dòng xuống hàng.

## 10. Ghi exception với ConsoleHandler

Một lỗi nghiêm trọng nên ghi bằng overload nhận **Throwable**, để Formatter có thể thấy exception và cause chain.

~~~java
// Snippet bên trong khối catch đã có biến exception và requestId.
LOG.log(Level.SEVERE,
        "event=order.persist.failed requestId=" + requestId,
        exception);
~~~

Cách này gắn Throwable vào **LogRecord.getThrown()**, thay vì chỉ nối exception.getMessage() thành chuỗi. Nếu ConsoleHandler dùng SimpleFormatter, đầu ra thường có stack trace của Throwable và các khối **Caused by:**; nội dung cụ thể phụ thuộc ngoại lệ và formatter.

**Lưu ý quan trọng về ví dụ chạy độc lập ở mục 7:** Formatter tùy chỉnh tại đó chỉ in level + message, **không in record.getThrown()**. Nếu chép nguyên formatter ấy vào ứng dụng production để ghi SEVERE, bạn có thể mất stack trace dù đã gọi LOG.log(Level.SEVERE, message, exception) đúng cách. Hãy chọn SimpleFormatter hoặc encoder được thiết kế hiển thị đầy đủ Throwable khi log lỗi.

Không ghi stack trace ở mọi tầng:

~~~text
Repository bắt lỗi, bọc và ném tiếp
    -> Service bổ sung ngữ cảnh, ném tiếp
        -> API/job boundary biết kết quả cuối
            -> ghi một log lỗi chính kèm Throwable
~~~

Đây là nguyên tắc hướng dẫn, không phải cấm mọi log trung gian: ghi thêm khi có thông tin vận hành mới (ví dụ retry, fallback) nhưng tránh nhân bản cùng stack trace như nhiều sự cố độc lập.

Không đưa bí mật, token, password, dữ liệu tài khoản hoặc request body nhạy cảm vào thông điệp, kể cả ở log lỗi; exception.getMessage() của thư viện cũng có thể mang dữ liệu không phù hợp để lưu lâu dài.

## 11. Filter ở ConsoleHandler và điểm khác với Filter ở Logger

**Filter** là quy tắc nhận hoặc bỏ một LogRecord cụ thể:

~~~java
console.setFilter(record ->
        !"health.ping".equals(record.getMessage()));
~~~

Đoạn này minh họa Filter loại đúng sự kiện health.ping khi bản ghi đi đến ConsoleHandler. Nếu hệ thống còn FileHandler, FileHandler có thể vẫn lưu health.ping tùy điều kiện riêng. Ngược lại:

~~~java
logger.setFilter(record ->
        !"health.ping".equals(record.getMessage()));
~~~

Đoạn thứ hai áp dụng quy tắc tại Logger nguồn, có thể ngăn health.ping tới **mọi Handler** được Logger đó chuyển tiếp. Các snippet giả định có biến tương ứng.

| Nhu cầu | Nơi đặt điều kiện thích hợp |
| --- | --- |
| Bỏ log heartbeat trên console, vẫn cần file điều tra | Filter của ConsoleHandler |
| Không phát bản ghi từ một Logger nguồn tới bất kỳ Handler nào | Filter của Logger nguồn |
| Chỉ bỏ bản ghi FINE vì quá chi tiết | Dùng level INFO của Logger/Handler |
| Lọc log của toàn bộ hệ thống tại một đầu ra chung | Filter của Handler chung, cùng các điều kiện liên quan |
| Loại dữ liệu bí mật khỏi mọi log | Giảm/che dữ liệu ngay tại nguồn và dùng encoder phù hợp; Filter đơn thuần không đủ |

**Cẩn thận:** một Filter bỏ tất cả sự kiện có chữ “health” có thể vô tình loại cả cảnh báo **health.failed**. Hãy dùng **mã sự kiện ổn định** và điều kiện rõ ràng. Khi một LogRecord thiếu metadata, chính sách cho qua hay từ chối phải được quyết định có chủ đích.

Filter cũng nên nhanh, thread-safe và tránh I/O/logging đệ quy ngay trong **isLoggable()**. ConsoleHandler có thể được sử dụng bởi nhiều thread; không giả định quy tắc Filter có trạng thái sẽ tự an toàn khi concurrent.

## 12. Chống log trùng do Logger hierarchy

Giả sử một Logger con có ConsoleHandler, còn Logger gốc cũng có ConsoleHandler:

~~~text
Logger "com.example.orders"
  +-- ConsoleHandler riêng
  |
  +-- useParentHandlers=true
       |
       +-- Root Logger
            +-- ConsoleHandler chung
~~~

Một lời gọi INFO trên Logger con có thể được **hai Handler** ghi ra stderr, khiến bạn thấy một sự kiện hai lần. Đây không nhất thiết là lỗi do Java gọi logging hai lần, mà có thể là cùng một LogRecord được xuất qua hai đường Handler.

Giải pháp theo nhu cầu:

- Nếu chỉ muốn sử dụng cấu hình tập trung ở root, **không gắn thêm Handler riêng** vào Logger con.
- Nếu Logger con cần Handler chuyên biệt và không muốn truyền lên root, dùng **logger.setUseParentHandlers(false)**.
- Nếu chủ động cần nhiều đích, để useParentHandlers=true nhưng điều chỉnh cấu hình để tránh cùng một đích nhận trùng ngoài ý muốn.

**Đừng vội tắt toàn bộ Handler cha trong một ứng dụng đang chạy** nếu chính sách vận hành dựa vào nó. Xác định đường đi của bản ghi và Handler chịu trách nhiệm thu thập trước, rồi quyết định nơi đặt level/Filter.

Một Logger có thể được tạo nhiều lần bằng **Logger.getLogger(name)** trong cùng JVM; việc gọi **addHandler()** lặp lại trong mã khởi tạo không được thiết kế cẩn thận cũng có thể khiến Handler trùng. Tổ chức cấu hình logging tập trung và dọn handler được tạo riêng khi hết vòng đời.

## 13. Khi nào ConsoleHandler phù hợp cho production?

ConsoleHandler thường phù hợp cho **ứng dụng chạy bằng dòng lệnh, dịch vụ trên máy chủ và container** nếu nền tảng thu thập **stderr**. Tuy vậy, “có dòng log trên terminal” chưa bảo đảm hệ thống vận hành đã quan sát được nó.

Khi triển khai cần kiểm tra:

1. **Môi trường thu thập:** platform có nhận stderr không? Có phân biệt stdout và stderr? Có giữ log khi container khởi động lại không?
2. **Định dạng:** SimpleFormatter có đủ thông tin event, requestId, service, level và exception chưa? Nếu cần JSON, JUL cần Formatter/encoder phù hợp.
3. **Thời gian:** timestamp có định dạng nhất quán, ưu tiên UTC khi lưu tập trung; chú ý timezone của máy nếu dùng SimpleFormatter.
4. **Dung lượng:** INFO/DEBUG quá nhiều có thể tăng chi phí ingest và ảnh hưởng I/O. Chỉ bật mức chẩn đoán chi tiết khi cần.
5. **Hiệu năng:** ConsoleHandler ghi đồng bộ ra một OutputStream; đầu ra chậm có thể làm tăng thời gian xử lý. Khi tải lớn, cần đánh giá chiến lược logging và collector.
6. **Bảo mật:** tránh thông tin cá nhân, credentials, token và stack trace ngoài vùng có quyền truy cập phù hợp. Áp dụng retention và phân quyền rõ ràng.
7. **Khả năng truy vết:** thêm requestId/jobId và mã sự kiện ổn định; bản thân ConsoleHandler không tự sinh traceId hoặc truyền MDC qua nhiều thread.
8. **Khả năng mất log:** nếu tiến trình hoặc collector bị lỗi, vẫn có thể mất bản ghi. ConsoleHandler flush sau publish không đồng nghĩa đảm bảo lưu bền trong hệ thống bên ngoài.
9. **Tính tương thích framework:** nếu app dùng SLF4J + Logback hoặc Log4j 2, hãy kiểm tra backend thật đang xử lý sự kiện; gắn JUL ConsoleHandler vào một Logger không được dùng sẽ không giải quyết vấn đề.
10. **Vòng đời tài nguyên:** gắn Handler một lần theo cấu hình, quản lý thay đổi cấu hình và tránh thêm Handler trùng sau mỗi request.

Trong dịch vụ có lưu lượng lớn, một event ghi cho từng phần tử xử lý có thể gây tắc nghẽn stderr. Dùng mức chi tiết thấp hơn, thống kê metric hoặc tổng hợp theo batch khi thích hợp, nhưng không bỏ log lỗi/audit bắt buộc chỉ để giảm lượng bản ghi.

## 14. Troubleshooting: vì sao ConsoleHandler không thấy log?

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| logger.info() chạy nhưng không in gì | Logger đang ở WARNING/SEVERE | Kiểm tra level hữu hiệu của Logger |
| Logger cho FINE nhưng không có FINE trên console | ConsoleHandler vẫn ở INFO | Đặt cả Logger và Handler ở FINE khi cần |
| Chỉ một số sự kiện không thấy | Logger Filter hoặc Handler Filter từ chối | Kiểm tra điều kiện event và metadata |
| Log xuất hai lần | Handler ở Logger con và root cùng ghi | Kiểm tra addHandler() và useParentHandlers |
| Unit test kiểm stdout thấy rỗng | ConsoleHandler ghi stderr | Bắt đúng stderr hoặc dùng Handler thích hợp |
| Log hiển thị format khó đọc | SimpleFormatter/formatter config khác kỳ vọng | Kiểm tra formatter và thuộc tính format |
| Đổi logging.properties mà chương trình không thay | File không được LogManager nạp hoặc mã ghi đè | Kiểm tra JVM property, thời điểm tải, đường dẫn |
| Log có {0} nguyên văn | Formatter không formatMessage hoặc tham số chưa được cung cấp | Kiểm tra Logger.log và Formatter |
| Log lỗi không có stack trace | Chỉ nối exception.getMessage() hoặc Formatter bỏ Throwable | Truyền Throwable và dùng Formatter có hỗ trợ |
| Tiếng Việt bị lỗi dấu | Encoding của handler, terminal hoặc collector không khớp | Kiểm tra encoding end-to-end |
| Console đứng/chậm khi log nhiều | Ghi đồng bộ và stream/collector chậm | Đo khối lượng log và I/O, giảm mức nhiễu |
| Không thấy log trên log platform | Collector không nhận stderr hoặc cấu hình thu thập sai | Xem cấu hình container/host/agent |

### Các bước kiểm tra theo thứ tự

1. Xác minh mã chạy đến lời gọi logger.info()/warning()/log().
2. Xác minh Logger đúng tên, đúng level hữu hiệu, không bị Filter từ chối.
3. Kiểm tra Handler có được gắn trực tiếp hoặc nhận qua Logger cha không.
4. Kiểm tra **ConsoleHandler level** và Filter của Handler.
5. Xác minh **System.err** thực sự được IDE/shell/container hiển thị hoặc thu thập.
6. Kiểm tra Formatter, encoding và việc Throwable có được đưa vào LogRecord.
7. Kiểm tra LogManager hoặc logging backend có ghi đè cấu hình không.

Nên thử một bản ghi INFO và một WARNING với tên event cố định để biết ngưỡng nào đang hoạt động, rồi mới bật thêm log chi tiết.

## 15. Những lỗi thiết kế thường gặp

**Lỗi 1 — Coi console là stdout.** Điều này khiến test bắt sai stream hoặc gửi log tới sai collector. Cách sửa: hiểu ConsoleHandler mặc định ghi **System.err**, chọn Handler đúng với chính sách đầu ra.

**Lỗi 2 — Chỉ đặt level cho Logger.** Ví dụ Logger FINE và Handler INFO vẫn bỏ FINE. Cách sửa: kiểm tra cả **Logger level + Handler level**, cùng các Filter.

**Lỗi 3 — Gắn thêm ConsoleHandler khi root đã có.** Hệ quả là log trùng và chi phí tăng. Cách sửa: xem cấu trúc Handler, quyết định dùng cấu hình tập trung hay Handler riêng.

**Lỗi 4 — Tự xây Formatter quá tối giản.** Có thể mất timestamp, source và Throwable. Cách sửa: dùng SimpleFormatter hoặc Formatter được thiết kế đáp ứng nhu cầu điều tra, test cả exception cause chain.

**Lỗi 5 — Dùng logger.info() cho mọi vòng lặp.** Gây tràn stderr, khó tìm cảnh báo, có thể ảnh hưởng tốc độ xử lý. Cách sửa: log mốc quan trọng, đưa chi tiết xuống FINE/metric khi hợp lý.

**Lỗi 6 — Ghi dữ liệu nhạy cảm.** stderr thường được thu thập và lưu dài hạn. Cách sửa: che hoặc tránh ghi thông tin bí mật ngay từ nguồn, không tin rằng Filter sẽ loại mọi dữ liệu nguy hiểm.

**Lỗi 7 — Lẫn API JUL với SLF4J.** JUL dùng ConsoleHandler và định dạng tham số như **{0}**; SLF4J thường dùng **{}** và backend/appender. Cách sửa: xác định logging backend của ứng dụng trước khi cấu hình.

**Lỗi 8 — Coi flush là lưu bền.** ConsoleHandler flush stream sau khi publish, nhưng dữ liệu vẫn có thể mất ở môi trường thu thập. Cách sửa: kiểm tra collector, lưu trữ, cảnh báo và retention theo mục tiêu vận hành.

## 16. Checklist áp dụng ConsoleHandler

1. Xác định app thực sự dùng **JUL** hay một logging backend khác.
2. Xác định đích mong muốn: **System.err**, tệp hay hệ thống thu thập tập trung.
3. Cấu hình **Logger level** và **ConsoleHandler level** để sự kiện cần thiết được đi qua.
4. Chỉ đặt **Filter** khi cần điều kiện theo event hoặc metadata; không dùng Filter để thay ngưỡng level đơn giản.
5. Chọn **Formatter** đủ level, timestamp, nguồn, ngữ cảnh và Throwable cho môi trường thực tế.
6. Kiểm tra **useParentHandlers** và số Handler để tránh log trùng.
7. Thử INFO, WARNING, FINE và trường hợp ngoại lệ; quan sát đúng **stderr**.
8. Kiểm tra cấu hình **logging.properties**, encoding và sự khác biệt giữa môi trường phát triển/production.
9. Đo lưu lượng log, chi phí I/O, bảo vệ dữ liệu và kiểm tra collector nhận được các bản ghi cần thiết.
10. Giữ tập sự kiện quan trọng, có thể tìm kiếm và liên kết bằng requestId/jobId khi hệ thống xử lý đồng thời.

**Kết luận:** ConsoleHandler là Handler có sẵn của **Java Util Logging**, ghi bản ghi qua Formatter vào **System.err**. Dùng đúng **Logger → level/Filter → ConsoleHandler → Formatter → stderr**, hiểu việc chuyển log tới Handler cha và kiểm thử đầu ra thực tế sẽ giúp quan sát ứng dụng Java hiệu quả, dễ cấu hình và hạn chế log trùng hoặc mất thông tin quan trọng.
