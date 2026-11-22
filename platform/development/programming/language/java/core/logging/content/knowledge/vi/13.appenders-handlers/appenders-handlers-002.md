# Handler là gì trong Java Logging?

## 1. Khái niệm Handler

Trong **Java Util Logging (JUL)**, **Handler** là thành phần **tiếp nhận và xuất bản (publish) các bản ghi log** do Logger chuyển tới. Logger giúp mã Java tạo sự kiện; Handler quyết định đưa sự kiện đã được chấp nhận tới đâu và bằng cách nào, chẳng hạn console, tệp hoặc một hệ thống nhận log.

Các class quan trọng đều nằm trong package **java.util.logging** của JDK:

- **Logger:** Nơi ứng dụng gọi các phương thức như **info**, **warning**, **severe** hoặc **log** để phát một sự kiện.
- **LogRecord:** Đối tượng mang thông tin của sự kiện: level, message, logger name, timestamp, parameters, Throwable và một số metadata.
- **Handler:** Thành phần nhận LogRecord và thực hiện thao tác xuất bản.
- **Formatter:** Thành phần biến nội dung LogRecord thành cách trình bày phù hợp, chẳng hạn văn bản hoặc XML.
- **Filter:** Quy tắc bổ sung có thể chấp nhận hoặc loại bỏ một LogRecord.
- **LogManager:** Thành phần quản lý cấu hình logging và các logger trong JUL.

Có thể hình dung:

~~~text
Mã ứng dụng Java
    |
    | LOGGER.warning("Gateway slow")
    v
Logger
    | kiểm tra level và Logger Filter
    v
LogRecord
    |
    +-----------------------------+
    |                             |
    v                             v
ConsoleHandler                FileHandler
    | mức + Handler Filter        | mức + Handler Filter
    | Formatter                   | Formatter
    v                             v
Console (thường stderr)       File log
~~~

**Handler không phải exception handler.** Từ “handler” ở đây chỉ thành phần xử lý **bản ghi log**, không phải khối **catch (Exception e)** trong Java. Bắt và xử lý exception là quyết định của logic chương trình; Logger và Handler ghi lại sự kiện cần quan sát.

Ví dụ:

~~~java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger(MyService.class.getName());

LOGGER.info("Service started");
~~~

Đây là ví dụ minh họa hai câu lệnh trong đúng ngữ cảnh class/method, không phải tệp Java độc lập. Dòng **LOGGER.info(...)** phát một sự kiện; Handler nào thực sự xuất sự kiện phụ thuộc cấu hình Logger, các Handler được gắn, level và Filter.

## 2. Handler và Logger khác nhau như thế nào?

| Tiêu chí | Logger | Handler |
| --- | --- | --- |
| Trách nhiệm chính | Phát sự kiện và xác định category theo tên | Nhận sự kiện và ghi tới một đích cụ thể |
| Điểm ứng dụng thường gọi | LOGGER.info, LOGGER.warning, LOGGER.log... | Thường cấu hình lúc khởi động, ít gọi trực tiếp từ nghiệp vụ |
| Có level? | Có: ngưỡng hiệu lực của logger | Có: ngưỡng riêng của Handler |
| Có Filter? | Có thể có Logger Filter | Có thể có Handler Filter |
| Có Formatter? | Không phải nơi trực tiếp định dạng bản ghi | Có thể giữ Formatter để tạo output |
| Quan hệ phân cấp | Logger có cha/con theo tên | Handler được gắn vào Logger; không tự tạo cây logger |
| Có thể có nhiều? | Mỗi class/category có tên logger riêng | Một Logger có thể gắn nhiều Handler |
| Ví dụ | com.example.payment.PaymentClient | ConsoleHandler, FileHandler, Handler tùy biến |

Logger có thể phát một sự kiện đến nhiều Handler để cùng một LogRecord được ghi ra console **và** file. Ngược lại, nhiều Logger có thể chuyển bản ghi tới **cùng Handler**, chẳng hạn ConsoleHandler gắn với logger gốc.

**Một logger theo class không đồng nghĩa với một file theo class.** Các loggers trong nhiều package có thể dùng chung một Handler ghi ra console hoặc file; việc phân chia theo service, file hay môi trường là lựa chọn cấu hình.

Khi dùng Logback hoặc Log4j 2, các thành phần đích xuất thường được gọi là **Appender**. Chúng có vai trò tương tự Handler của JUL, nhưng **không phải cùng class hoặc API**. Không truyền một **java.util.logging.Handler** trực tiếp vào một Logback Logger rồi kỳ vọng hoạt động.

## 3. Các loại Handler có sẵn trong JUL

JDK cung cấp một số Handler thông dụng:

| Handler | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| **ConsoleHandler** | Xuất log ra console, thông thường **System.err** | Có mức lọc và Formatter; output có thể không trùng stdout của chương trình |
| **FileHandler** | Ghi LogRecord ra file, hỗ trợ pattern tên và xoay vòng file cơ bản | Có thể ném IOException khi mở file; cần đóng để giải phóng tài nguyên |
| **StreamHandler** | Ghi vào một OutputStream do ứng dụng cung cấp | Có buffering; cần lưu ý **flush** và quản lý vòng đời stream |
| **SocketHandler** | Gửi log qua kết nối socket theo định dạng được cấu hình | Phụ thuộc kết nối mạng; không tự thay thế một pipeline quan sát bền vững |
| **MemoryHandler** | Giữ tạm LogRecord trong bộ nhớ rồi đẩy tới Handler đích theo điều kiện | Hữu ích khi chỉ muốn xả bối cảnh khi có sự kiện đủ nghiêm trọng |

### ConsoleHandler

Đây là lựa chọn dễ dùng để học JUL và quan sát ứng dụng. Ví dụ:

~~~java
ConsoleHandler console = new ConsoleHandler();
console.setLevel(Level.INFO);
console.setFormatter(new SimpleFormatter());
logger.addHandler(console);
~~~

Đoạn mã minh họa giả định đã import các class, có biến **logger** phù hợp và có code giải phóng Handler. **ConsoleHandler mặc định ghi ra stderr**, không phải stdout. Vì vậy khi chạy Java, dòng **System.out.println(...)** và dòng ConsoleHandler có thể xuất hiện trên hai stream khác nhau. Nếu terminal gộp stdout/stderr, thứ tự hiển thị tương đối giữa hai stream không phải lúc nào cũng đáng tin để làm expected output.

### FileHandler

Ví dụ minh họa một FileHandler tối đa khoảng 1 MB mỗi file, giữ vòng ba file:

~~~java
FileHandler file = new FileHandler(
        "%h/app-%u.%g.log",
        1_000_000,
        3,
        true
);
file.setLevel(Level.WARNING);
file.setFormatter(new SimpleFormatter());
logger.addHandler(file);
~~~

Trong JUL, **%h** đại diện thư mục home, **%u** giúp phân biệt tên file khi cần tránh xung đột và **%g** là chỉ số vòng file. Số 1.000.000 ở constructor là giới hạn byte cho từng file theo cách FileHandler thực hiện; số 3 là số file trong vòng. **true** yêu cầu append nếu có thể, không đồng nghĩa dữ liệu log được lưu bền vững vô điều kiện.

**FileHandler không giống một hệ thống log rotation/retention production hoàn chỉnh.** Ứng dụng cần kiểm tra quyền ghi, dung lượng ổ đĩa, số tiến trình JVM, đường dẫn, mã hóa và pipeline thu thập tập trung. FileHandler có các cơ chế khóa file nhưng không nên cho nhiều tiến trình độc lập tranh chấp một đường dẫn một cách tùy tiện.

Nếu không đặt Formatter riêng, FileHandler thường dùng **XMLFormatter**, nên log có thể xuất ra XML chứ không phải từng dòng text đơn giản. Nếu muốn file text, chủ động cấu hình SimpleFormatter hoặc Formatter khác.

### StreamHandler và SocketHandler

**StreamHandler** phù hợp khi muốn ghi vào một OutputStream cụ thể, nhưng cần hiểu sự kiện có thể nằm trong buffer trước khi flush. Nếu stream thuộc quyền quản lý của phần khác, không nên close tùy tiện vì có thể đóng cả tài nguyên dùng chung.

**SocketHandler** đưa dữ liệu qua socket; mất kết nối hoặc lỗi đầu nhận có thể ảnh hưởng quá trình xuất log. Không xem SocketHandler mặc định là hàng đợi bảo đảm gửi lại sau khi process chết. Với ứng dụng cloud, thường nên dùng pipeline thu thập được nền tảng vận hành hỗ trợ và xem lại đặc tính mất log/backpressure.

### MemoryHandler

**MemoryHandler** lưu các bản ghi gần đây trong bộ đệm vòng, rồi có thể đẩy chúng qua một Handler đích khi gặp bản ghi đạt mức **pushLevel**. Điều này hữu ích khi muốn giữ bối cảnh chi tiết trước một sự kiện bất thường. MemoryHandler chỉ giữ số bản ghi theo dung lượng cấu hình, không bảo đảm lịch sử dài hạn hoặc dữ liệu vẫn tồn tại sau restart.

## 4. Cơ chế truyền log từ Logger tới Handler

Trong JUL, khi mã gọi:

~~~java
logger.warning("Dependency responded slowly");
~~~

quy trình khái quát là:

1. Logger xem **mức hiệu lực** của chính nó. Nếu mức của LogRecord quá thấp, Logger có thể không phát bản ghi.
2. Nếu đã có Filter được cấu hình tại Logger, Filter có thể từ chối bản ghi.
3. Logger chuyển LogRecord đến các Handler gắn trực tiếp với nó.
4. Tùy thuộc **useParentHandlers**, LogRecord tiếp tục được chuyển tới Handler của Logger cha và các tổ tiên.
5. Mỗi Handler có thể dùng **level**, **Filter** và cơ chế xử lý/Formatter riêng để quyết định có xuất bản ghi hay không.

Một chi tiết quan trọng: khi LogRecord đã được Logger con chấp nhận và chuyển lên các Handler của cha, **mức của Logger cha không nhất thiết được dùng để lọc lại bản ghi đó**. Tuy nhiên, level và Filter của **Handler trên cha** vẫn có thể loại bỏ nó.

Ví dụ:

~~~text
com.example.payment.PaymentClient  -> Logger level FINE
                  |
                  | Logger chấp nhận FINE
                  v
                 Root handler
                  |
                  +--> ConsoleHandler level INFO
                  |
                  +--> FileHandler level FINE
~~~

Ở ví dụ trên, bản ghi FINE có thể được FileHandler ghi nhận nhưng bị ConsoleHandler bỏ qua. Không thể kết luận “đã đặt Logger ở FINE nên mọi Handler sẽ ghi FINE”.

### Điều kiện tối thiểu để thấy một bản ghi

- Logger phát sự kiện ở mức được chấp nhận.
- Logger Filter không từ chối.
- Có tuyến đến một Handler phù hợp.
- Handler level cho phép sự kiện.
- Handler Filter không loại sự kiện.
- Đích output hoạt động và Formatter/encoder xử lý được.

Cấu hình Collector, mức lưu trữ hoặc giới hạn thu thập bên ngoài JVM còn có thể ảnh hưởng đến việc bản ghi xuất hiện trong dashboard.

## 5. Level của Handler

**Handler.setLevel(Level)** đặt ngưỡng tối thiểu mà Handler sẽ chấp nhận. Các mức chuẩn của JUL từ nghiêm trọng tới chi tiết là:

~~~text
SEVERE (1000)
WARNING (900)
INFO (800)
CONFIG (700)
FINE (500)
FINER (400)
FINEST (300)
~~~

Hai mức đặc biệt là **OFF** (từ chối tất cả theo ngưỡng thông thường) và **ALL** (cho phép mọi mức chuẩn theo ngưỡng). Level của Handler và Logger có nhiệm vụ riêng.

| Level ở Logger | Level ở Handler | Sự kiện | Có thể tới đích? |
| --- | --- | --- | --- |
| INFO | INFO | INFO | Có, nếu Filter/đích cho phép |
| INFO | ALL | FINE | Không, Logger đã chặn |
| FINE | INFO | FINE | Không, Handler chặn |
| FINE | FINE | FINE | Có, nếu Filter/đích cho phép |
| WARNING | FINE | INFO | Không, Logger chặn |
| ALL | WARNING | SEVERE | Có, nếu Filter/đích cho phép |

Bảng giả định không có các Filter khác và có một đường đến Handler tương ứng.

**Không nên chỉ tăng level Handler để bật debug.** Nếu Logger vẫn ở INFO, lời gọi logger.fine(...) không qua bước lọc đầu tiên. Ngược lại, Logger FINE nhưng Handler INFO cũng không đủ.

Mỗi Handler có thể có level khác nhau. Chẳng hạn console xuất INFO+, còn file hỗ trợ FINE để điều tra; hoặc Handler tập trung giữ các trường cấu trúc và Handler khác chỉ ghi cảnh báo. Quyết định này ảnh hưởng dung lượng, an toàn dữ liệu và cách truy cập log.

## 6. Filter và Formatter trong Handler

### Filter: chọn bản ghi theo quy tắc

Ngoài level, **Handler.setFilter(Filter)** cho phép một quy tắc như:
- Chỉ chấp nhận bản ghi thuộc một nhóm mã sự kiện.
- Bỏ sự kiện heartbeat quá thường xuyên.
- Cho phép một số loại sự kiện nhất định đi tới Handler chuyên biệt.

Ví dụ:

~~~java
handler.setFilter(record ->
        !record.getMessage().startsWith("NOISY_"));
~~~

Đây là đoạn minh họa, giả định message của các bản ghi đang xét khác null. Nó bỏ mọi bản ghi có message bắt đầu bằng **NOISY_**. Khi triển khai production cần xem xét xử lý message null, lỗi khi lọc và tác động đến khả năng điều tra.

**Không dùng Filter như giải pháp duy nhất để che secret** nếu log đã có thể tới Handler khác hoặc Collector khác. Cách an toàn hơn là không đưa dữ liệu nhạy cảm vào sự kiện ngay từ đầu.

### Formatter: quyết định hình thức xuất

**java.util.logging.Formatter** định nghĩa cách chuyển LogRecord thành chuỗi. Các Formatter có sẵn gồm:
- **SimpleFormatter:** Dạng text thích hợp để con người đọc, có thể chứa timestamp, level, message và exception theo pattern.
- **XMLFormatter:** Dạng XML, thường dùng trong FileHandler mặc định.

Ví dụ tạo Formatter tùy biến:

~~~java
Formatter formatter = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | "
                + record.getLoggerName()
                + " | "
                + formatMessage(record)
                + System.lineSeparator();
    }
};
handler.setFormatter(formatter);
~~~

Đây là một đoạn code minh họa trong class có Handler hợp lệ. **formatMessage(record)** sử dụng cơ chế định dạng message và resource bundle/parameters mà Formatter kế thừa hỗ trợ, tốt hơn việc tự giả định mọi message đều là một chuỗi đã format.

Nếu muốn ghi **stack trace** hoặc JSON có cấu trúc, Formatter cần xử lý **record.getThrown()** và các trường liên quan. Không phải việc chọn một Formatter mới tự tạo các metadata như request ID hoặc trace ID; ứng dụng và môi trường tracing phải bổ sung ngữ cảnh đó đúng cách.

### Phân biệt cấp lọc và cấp định dạng

~~~text
Logger level / Logger Filter
        |
        v
Handler level / Handler Filter
        |
        v
Handler.publish()
        |
        v
Formatter
        |
        v
I/O hoặc hệ thống nhận log
~~~

Đây là mô hình khái quát. Với Handler tùy biến, **publish()** có thể tự quyết định khi nào gọi Formatter và có tự tôn trọng **isLoggable(record)** hay không. Không nên triển khai Handler rồi bỏ qua lọc level và Filter theo ý muốn.

## 7. Ví dụ Java 17 chạy độc lập: viết Handler tùy biến

Ví dụ này minh họa đầy đủ những trách nhiệm cốt lõi của Handler:

1. Logger có tên **demo.orders.OrderService** và được đặt **Level.FINE**.
2. Handler được đặt **Level.INFO** nên bỏ bản ghi FINE dù Logger chấp nhận.
3. Handler Filter bỏ sự kiện có message bắt đầu bằng **NOISY_**.
4. Formatter tùy biến in ra mức, tên Logger, message và **loại Throwable**.
5. Handler ghi ra **System.out** để đầu ra xác định, không phụ thuộc timestamp.
6. Tắt truyền lên Handler cha trong ví dụ để không bị thêm dòng mặc định.

Tạo tệp **HandlerDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class HandlerDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    public static void main(String[] args) {
        Handler output = new DeterministicHandler();
        output.setLevel(Level.INFO);
        output.setFilter(record ->
                !record.getMessage().startsWith("NOISY_"));

        LOG.setLevel(Level.FINE);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            LOG.fine("QUERY_DETAILS");
            LOG.info("SERVICE_READY");
            LOG.info("NOISY_HEARTBEAT");
            LOG.warning("DEPENDENCY_SLOW");
            LOG.log(
                    Level.SEVERE,
                    "ORDER_SAVE_FAILED",
                    new IllegalStateException("disk unavailable"));
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }

    private static final class DeterministicHandler extends Handler {
        private DeterministicHandler() {
            setFormatter(new Formatter() {
                @Override
                public String format(LogRecord record) {
                    String cause = record.getThrown() == null
                            ? ""
                            : " | cause="
                                + record.getThrown()
                                        .getClass()
                                        .getSimpleName();

                    return record.getLevel().getName()
                            + " | " + record.getLoggerName()
                            + " | " + formatMessage(record)
                            + cause;
                }
            });
        }

        @Override
        public synchronized void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.println(getFormatter().format(record));
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**, trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 HandlerDemo.java
java HandlerDemo
~~~

**Stdout chính xác của ví dụ:**

~~~text
INFO | demo.orders.OrderService | SERVICE_READY
WARNING | demo.orders.OrderService | DEPENDENCY_SLOW
SEVERE | demo.orders.OrderService | ORDER_SAVE_FAILED | cause=IllegalStateException
~~~

Giải thích từng sự kiện:

- **LOG.fine("QUERY_DETAILS")**: Logger FINE chấp nhận nhưng Handler INFO từ chối.
- **LOG.info("SERVICE_READY")**: Cả Logger và Handler chấp nhận; Filter không từ chối, vì vậy xuất một dòng INFO.
- **LOG.info("NOISY_HEARTBEAT")**: Level hợp lệ nhưng Filter của Handler từ chối; không có dòng output.
- **LOG.warning("DEPENDENCY_SLOW")**: WARNING được ghi bình thường.
- **LOG.log(Level.SEVERE, ..., Throwable)**: Handler nhận một LogRecord có **getThrown()**; Formatter chỉ in **IllegalStateException** cho ví dụ ngắn gọn.
- **setUseParentHandlers(false)**: Không chuyển LogRecord đến Handler của tổ tiên, tránh các dòng từ cấu hình mặc định ảnh hưởng đầu ra.
- **removeHandler(output)** và **close()**: Ngắt liên kết và thực hiện thao tác dọn dẹp cho Handler do demo sở hữu.

**Lưu ý về Throwable:** Khi gọi Logger.log(Level, String, Throwable), exception được gắn vào bản ghi để Formatter có thể in stack trace. Formatter trong ví dụ chỉ in tên kiểu để stdout ổn định; **nó không tự in stack trace đầy đủ**. Trong production nên xem xét cách ghi cause chain, stack trace, thông tin ngữ cảnh và giới hạn dữ liệu nhạy cảm.

Handler trên **không thay thế một ConsoleHandler production hoàn chỉnh**. Nó phục vụ minh họa filtering/formatting. Nếu Handler tùy biến mở file, socket hoặc queue, phải xử lý lỗi I/O, đóng tài nguyên, thread safety, chặn/đánh rơi bản ghi và theo dõi tình trạng của chính pipeline log.

## 8. Ba phương thức abstract của Handler

**java.util.logging.Handler** là lớp abstract. Khi tự tạo Handler, cần triển khai các phương thức chính sau:

### publish(LogRecord record)

~~~java
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }

    // Dinh dang va gui LogRecord den dich duoc chon.
}
~~~

**publish** chịu trách nhiệm xuất sự kiện. Với custom Handler, nên kiểm tra **isLoggable(record)** để tuân thủ level/filter hiện tại. Phải tránh gọi lại cùng Logger từ bên trong publish một cách không kiểm soát, vì có thể dẫn đến ghi log đệ quy.

Trong Handler gửi tới mạng, đích nhận có thể đang lỗi. Chính sách khi đó cần rõ ràng: bỏ bản ghi, chặn luồng, buffer, retry hay chuyển sang một đích khác. Không có một lựa chọn mặc định phù hợp với mọi yêu cầu.

### flush()

~~~java
@Override
public void flush() {
    // Day du lieu dang dem xuong dich neu co buffer.
}
~~~

**flush** yêu cầu hoàn tất việc đẩy dữ liệu đã đệm theo khả năng của Handler/đích. Với một Handler chỉ gọi System.out.println, flush có thể chỉ cần gọi **System.out.flush()**. Với file hoặc stream có buffer, flush giúp giảm dữ liệu còn tồn tại trong bộ đệm.

**flush không nhất thiết tương đương fsync hoặc cam kết bền vững trên ổ đĩa**. Cần phân biệt việc đẩy buffer của ứng dụng với đảm bảo dữ liệu đã được lưu không mất.

### close()

~~~java
@Override
public void close() {
    flush();
    // Dong tai nguyen ma Handler thuc su so huu.
}
~~~

**close** được dùng để kết thúc vòng đời và giải phóng tài nguyên, ví dụ file hoặc socket. Nếu Handler không sở hữu stream được truyền vào, việc đóng stream đó có thể gây lỗi cho thành phần khác. Quyết định ownership phải rõ ràng.

**Trong ứng dụng thật, việc close và loại Handler khỏi Logger cần được tổ chức ở lifecycle khởi động/tắt ứng dụng**, không gọi close sau mỗi lần phát log. Nếu dùng Handler chung được nhiều Logger tham chiếu, không đóng nó khi một request hoặc một object riêng lẻ kết thúc.

Các đoạn code trong mục này là **minh họa về phương thức**, không phải ba class hay chương trình Java chạy độc lập.

## 9. Handler level, Filter và Logger Filter phối hợp thế nào?

Một quy tắc đánh giá có thể biểu diễn:

~~~text
Record có level L
     |
     v
Logger.isLoggable(L)?
     | không -> loại
     v có
Logger Filter chấp nhận?
     | không -> loại
     v có
Tìm Handler gắn với Logger và các cha phù hợp
     |
     v
Tại mỗi Handler: isLoggable(record)?
     | không -> Handler đó không xuất
     v có
publish + Formatter + I/O
~~~

**Một Handler từ chối bản ghi không có nghĩa các Handler khác cũng phải từ chối.** Các Handler độc lập có level/filter riêng.

Ví dụ, giả sử root Logger có hai Handler:
- **CONSOLE** chấp nhận WARNING+.
- **FILE** chấp nhận FINE+.

Khi Logger con ở FINE ghi FINE, FILE có thể nhận còn CONSOLE có thể bỏ. Khi Logger con ở INFO, cả hai sẽ không nhận FINE vì bị chặn ngay trước bước dispatch.

**Filter không chỉ dựa vào level.** Nó có thể xét message, logger name, mã sự kiện, trạng thái exception hoặc trường bổ sung, nhưng phải tránh tạo điều kiện lọc khó hiểu khiến sự kiện bảo mật hoặc lỗi nghiêm trọng biến mất mà không được phát hiện.

## 10. Parent Handler và hiện tượng log trùng

JUL Logger có quan hệ cha/con theo không gian tên. Một Logger được đặt tên theo class như **com.example.orders.OrderService** thường có Logger cha ở cấp package hoặc root theo cấu trúc Logger đang tồn tại.

**Mặc định**, sự kiện từ Logger con có thể tiếp tục được chuyển tới Handler của Logger cha. Điều này giúp cấu hình tập trung: ứng dụng chỉ gắn ConsoleHandler ở root, các Logger trong lớp nghiệp vụ dùng chung đường xuất.

Nhưng nó cũng gây log trùng nếu ta thêm Handler riêng vào Logger con mà không xem xét tuyến cha:

~~~java
Logger logger = Logger.getLogger("com.example.orders.OrderService");
logger.addHandler(new ConsoleHandler());
// Logger van cho phep chuyen record den Handler cua cha.
~~~

Đoạn trên có thể khiến một bản ghi xuất nhiều lần: một lần ở Handler vừa thêm và lần khác tại Handler của cha. Nó còn tạo một Handler mới mà không quản lý vòng đời. Không nên viết logic này trong constructor của mỗi service.

Có hai cách thiết kế:

**Cách A — Handler chung ở root/cha:** Giữ các Handler được cấu hình tập trung, Logger con chỉ phát sự kiện và điều chỉnh level khi cần.

**Cách B — Tuyến Handler riêng cho một nhánh:** Gắn đủ Handler phù hợp ở Logger con, và dùng:

~~~java
logger.setUseParentHandlers(false);
~~~

Đây là một phần cấu hình, không phải lệnh bảo đảm sẽ xuất log. Nếu tắt truyền lên cha mà **không có Handler hợp lệ ở logger con**, log có thể không tới đích nào.

Lưu ý: **setUseParentHandlers(false)** chỉ kiểm soát tuyến phát đến Handler tổ tiên; nó **không tự làm mất tính kế thừa level**. Logger vẫn có thể kế thừa level hiệu lực từ cha nếu được đặt **setLevel(null)**.

Trong nhiều ứng dụng production, cấu hình tập trung và hạn chế Handler tự phát sinh trong code nghiệp vụ sẽ dễ kiểm soát hơn.

## 11. Cấu hình Handler trong logging.properties

Không nhất thiết phải tạo mọi Handler bằng mã Java. JUL hỗ trợ nạp cấu hình từ file **logging.properties**.

Ví dụ:

~~~properties
# Handler chung duoc gan cho root
handlers = java.util.logging.ConsoleHandler

# Muc root logger
.level = INFO

# Muc va Formatter cua ConsoleHandler
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Bat FINE rieng cho mot class dang dieu tra
com.example.payment.PaymentClient.level = FINE

# Log cac class khac theo muc da ke thua
com.example.orders.OrderService.level = INFO
~~~

Ở đây:
- Root Logger có mức INFO.
- Handler Console được phép nhận FINE.
- Logger **com.example.payment.PaymentClient** được đặt FINE, nên log FINE của class đó có thể truyền lên ConsoleHandler.
- Logger **com.example.orders.OrderService** vẫn ở INFO nên không phát FINE.

Nếu đặt ConsoleHandler.level=INFO thay vì FINE, dù PaymentClient được đặt FINE thì ConsoleHandler có thể bỏ FINE. Điều này là nguyên nhân phổ biến khiến lập trình viên nghĩ mức logger không hoạt động.

Để tải file khi khởi động một chương trình Java đã biên dịch:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Đây là **mẫu lệnh cho ứng dụng có class com.example.Main trong thư mục out**, không phải lệnh chạy demo HandlerDemo. Đối với demo, cấu hình được thiết lập trực tiếp trong main để kết quả xác định.

Khi dùng **SLF4J + Logback** hoặc **Log4j 2**, file cấu hình tương ứng là logback.xml, log4j2.xml hoặc dạng được backend hỗ trợ; **logging.properties của JUL không mặc nhiên cấu hình các Appender trong backend đó**. Một ứng dụng sử dụng bridge có thể có hành vi khác, cần kiểm tra pipeline thực tế.

## 12. Handler và Appender: liên hệ trong các hệ logging Java

| Khía cạnh | JUL | Logback | Log4j 2 |
| --- | --- | --- | --- |
| API phát log phổ biến | java.util.logging.Logger | SLF4J Logger | Log4j API hoặc SLF4J qua provider |
| Thành phần đích ghi | Handler | Appender | Appender |
| Ví dụ đích console | ConsoleHandler | ConsoleAppender | Console Appender |
| Ví dụ ghi file | FileHandler | FileAppender/RollingFileAppender | File/RollingFile Appender |
| Định dạng | Formatter | Encoder/Layout/Pattern | Layout |
| Lọc | Logger/Handler Filter và level | Logger/Appender Filter và level | Logger/Appender Filters và level |
| Chuyển tới cha | useParentHandlers | additivity | additivity |
| Cấu hình điển hình | logging.properties | logback.xml | log4j2.xml |

Sự tương đồng là **vai trò kiến trúc**: Logger tạo sự kiện; Handler/Appender thực hiện tuyến xuất. Cơ chế hoạt động, lifecycle, cấu hình và khả năng mở rộng **không hoàn toàn giống nhau**.

Khi dự án đã thống nhất backend khác JUL, thường không nên thêm một JUL FileHandler vào từng class chỉ để ghi ra file riêng. Hãy sử dụng chính Appender của backend hoặc một bridge đúng hướng; nếu nhiều provider/bridge cùng hoạt động, sự kiện có thể bị ghi trùng hoặc đi sai tuyến.

## 13. Thiết kế Handler tùy biến cho production

Bài học chỉ cần hiểu Handler, nhưng trước khi viết custom Handler thật nên cân nhắc:

### 13.1. Tính đồng thời và vòng đời

Nhiều thread có thể gọi logger cùng lúc. Handler truy cập buffer, file hoặc socket phải xử lý **race condition**, tính nguyên tử của bản ghi, thứ tự sự kiện và thao tác shutdown. Dùng synchronized hoặc hàng đợi nội bộ tùy nhu cầu, nhưng cần cân bằng hiệu năng và blocking.

Nếu Handler ghi ra một file, quản lý việc mở/đóng tài nguyên trong lifecycle ứng dụng. Nếu sử dụng một Handler dùng chung cho nhiều Logger, không đóng nó từ một request riêng lẻ.

### 13.2. Không làm lỗi logging phá vỡ nghiệp vụ một cách vô tình

Một Handler tùy biến có thể gặp IOException, timeout hoặc encoder error. Cần chính sách rõ ràng khi ghi thất bại. JUL có **ErrorManager** để Handler báo lỗi trong quá trình xuất; nhiều Handler chuẩn dùng cơ chế này thay vì ném lỗi I/O tùy tiện vào đường xử lý nghiệp vụ.

Tuy nhiên, không nên tự động “nuốt” mọi lỗi trong một đường audit bắt buộc phải bền vững. Yêu cầu của audit có thể cần kiến trúc khác, chẳng hạn outbox, hàng đợi bền vững hoặc xác nhận ghi trước khi giao dịch hoàn thành.

**Tránh logging đệ quy:** Nếu publish gặp lỗi rồi tự gọi Logger đang dùng chính Handler đó, hệ thống có thể lặp vô hạn hoặc làm quá tải. Chọn cơ chế báo lỗi riêng được thiết kế để tránh vòng lặp.

### 13.3. Kiểm soát backpressure

Nếu đích ghi chậm hơn tốc độ sinh LogRecord:
- Ghi đồng bộ có thể làm tăng độ trễ nghiệp vụ.
- Ghi bất đồng bộ có thể làm queue đầy.
- Bỏ bớt log có thể mất bằng chứng quan trọng.
- Chặn producer có thể gây hiệu ứng dây chuyền.

Cần lựa chọn theo mục tiêu SLO, chi phí, loại sự kiện và yêu cầu tuân thủ. **Handler tùy biến không tự bảo đảm an toàn khi có tải lớn** chỉ vì đã implement publish, flush và close.

### 13.4. Dữ liệu nhạy cảm và cấu trúc log

Không ghi password, token, private key, cookie đăng nhập, payload chứa dữ liệu thanh toán hoặc dữ liệu cá nhân không cần thiết. Một custom Formatter có thể xuất ra JSON có cấu trúc, nhưng vẫn phải áp dụng redaction, phân quyền, retention và tránh nguy cơ log injection khi message chứa nội dung từ đầu vào không tin cậy.

Các trường hữu ích thường là **timestamp có múi giờ, level, service, logger_name, event_code, request_id/trace_id, operation, exception type và outcome**. Handler chỉ có thể xuất những trường đã có trong LogRecord hoặc được bổ sung hợp lệ; việc tạo Handler mới không tự tạo trace ID.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ Handler là catch exception | Nhầm logging với xử lý lỗi | Phân biệt LogRecord/Handler với try-catch |
| Đặt Logger FINE nhưng Handler INFO | Log FINE vẫn không hiển thị | Kiểm tra cả hai ngưỡng |
| Thêm ConsoleHandler trong mỗi constructor | Một Logger có thể gắn nhiều Handler, log trùng | Cấu hình Handler tập trung, quản lý lifecycle |
| Gắn Handler ở logger con nhưng vẫn truyền lên cha | Có thể in cùng sự kiện nhiều lần | Chọn root Handler chung hoặc tắt parent handler đúng chỗ |
| Tắt parent handlers rồi không thêm Handler | Sự kiện không tới đích dự kiến | Kiểm tra tuyến xuất và Handler gắn trực tiếp |
| Bỏ qua isLoggable trong custom publish | Không tôn trọng level hoặc Filter | Kiểm tra isLoggable(record) trước khi xuất |
| Chỉ dùng getMessage() khi cần stack trace | Mất Throwable trong output | Truyền Throwable và dùng Formatter phù hợp |
| Tưởng ConsoleHandler luôn là stdout | Khó kiểm tra kết quả trong terminal | Phân biệt stderr và stdout |
| Quên flush/close FileHandler | Dữ liệu còn đệm, tài nguyên không được giải phóng | Đóng Handler tại shutdown theo đúng ownership |
| Handler gửi mạng được xem là bền vững | Có thể mất log do mạng/process chết | Dùng pipeline có đảm bảo và theo dõi riêng |
| Ghi mọi thứ ở SEVERE | Nhiễu, sai tín hiệu sự cố | Chọn mức theo tác động; INFO/WARNING/FINE khi thích hợp |
| Đưa token hoặc payload nhạy cảm vào log | Rò rỉ dữ liệu | Loại bỏ/redact dữ liệu ngay tại điểm phát |
| Tạo tên Logger theo request ID | Cardinality lớn, khó quản lý | Logger theo class/package, request ID trong context |
| Dùng Handler JUL như Appender Logback | Không tương thích API/backend | Chọn đúng cơ chế cấu hình và bridge |

## 15. Checklist khi cấu hình Handler

1. **Ứng dụng đang dùng JUL hay SLF4J/Logback/Log4j 2?** Xác định backend để chọn đúng Handler/Appender.
2. **Logger đặt tên hợp lý chưa?** Thường theo class/package, ví dụ com.example.orders.OrderService.
3. **Có Handler nào đang nhận bản ghi?** Kiểm tra Handler của logger trực tiếp và tổ tiên.
4. **Level của Logger/Handler phù hợp chưa?** Không quên bộ lọc ở cả hai nơi.
5. **Filter có loại sự kiện quan trọng không?** Đánh giá theo event code và kết quả nghiệp vụ.
6. **Formatter có đủ thông tin?** Timestamp, level, logger, message, exception và correlation khi cần.
7. **Có log trùng do parent handlers không?** Tránh gắn Handler lặp, hiểu useParentHandlers.
8. **Đích ghi hoạt động không?** Kiểm tra stderr/stdout, quyền file, đường dẫn, mạng và collector.
9. **Vòng đời Handler rõ ràng chưa?** Quy định ownership, flush, close và shutdown.
10. **Có đáp ứng yêu cầu production không?** Hiệu năng, concurrency, backpressure, bảo mật và retention.
11. **Đã thử kết quả trong môi trường chạy thật chưa?** Một bài test phải xác nhận đường đi LogRecord, không chỉ thấy Logger.info được gọi.

## 16. Câu hỏi tự kiểm tra

**1. Handler trong JUL làm gì?**  
Handler nhận LogRecord từ Logger và xuất bản ghi tới một đích, có thể dùng level, Filter và Formatter riêng.

**2. Logger.INFO, Handler.ALL có in FINE không?**  
Không. Logger đã chặn FINE từ trước.

**3. Logger.FINE, ConsoleHandler.INFO có in FINE không?**  
Không. Handler chặn, dù Logger đã cho phép.

**4. Vì sao bật useParentHandlers có thể làm log trùng?**  
Vì cùng LogRecord có thể đi qua Handler của logger con và Handler của tổ tiên; nếu cả hai đều xuất tới console, kết quả có thể bị in hai lần.

**5. ConsoleHandler mặc định in ra stdout hay stderr?**  
Thông thường là **stderr**. Nếu cần stdout cố định, có thể viết Handler tùy biến hoặc chọn backend hỗ trợ cấu hình đích console.

**6. Một Handler tự viết cần những phương thức nào?**  
Các phương thức abstract **publish(LogRecord), flush(), close()**; khi triển khai publish nên tôn trọng **isLoggable(record)**.

**7. setUseParentHandlers(false) có tắt kế thừa level từ cha không?**  
Không. Nó chỉ tắt đường chuyển bản ghi tới Handler tổ tiên; mức hiệu lực vẫn có thể kế thừa nếu Logger không đặt level trực tiếp.

**8. Handler có tự bảo đảm không mất log khi process crash không?**  
Không. Độ bền phụ thuộc đích ghi, buffer, flush, kiến trúc và các cam kết của hệ thống thu thập.

**9. Handler của JUL có phải là Appender của Logback không?**  
Không phải cùng API, dù cùng đảm nhiệm chức năng đưa sự kiện log đến đích.

**Ghi nhớ:** **Logger quyết định phát sự kiện; Handler quyết định xuất sự kiện đi đâu và theo cách nào.** Để log hoạt động đúng, cần hiểu đồng thời level, Filter, Formatter, tuyến Logger cha/con, vòng đời và đặc tính của đích ghi. Một Handler được cấu hình tốt giúp hệ thống Java có log đủ dùng để chẩn đoán mà không gây trùng lặp, mất dữ liệu hoặc tăng chi phí không kiểm soát.
