# Bộ lọc log (Log Filter) trong kiến trúc Java Logging

## 1. Bộ lọc log là gì?

Trong hệ thống logging, **bộ lọc log (log filter)** là thành phần quyết định một bản ghi log đã được tạo có được đi tiếp tới nơi xuất log hay không. Bộ lọc nhận thông tin về sự kiện, áp dụng điều kiện, rồi trả lời **cho phép** hoặc **loại bỏ**.

Ví dụ: hệ thống sinh nhiều log về endpoint kiểm tra sức khỏe. Các bản ghi này có thể hữu ích khi chẩn đoán, nhưng nếu gửi hết vào kho log tập trung sẽ tạo nhiều nhiễu. Bộ lọc có thể bỏ các sự kiện định kỳ đã được xác định an toàn, trong khi vẫn giữ lỗi ứng dụng, kết quả nghiệp vụ và dấu hiệu bất thường.

Bộ lọc giúp:

- **Giảm nhiễu:** loại các sự kiện lặp hoặc thông tin chẩn đoán không cần cho một đầu ra cụ thể.
- **Kiểm soát lượng log:** tránh đẩy mọi bản ghi sang console, file hoặc hệ thống thu thập log.
- **Định tuyến theo đích:** một số sự kiện cần xuất ra nhiều đích, một số chỉ cần đích dành cho chẩn đoán.
- **Giữ tín hiệu có giá trị:** tập trung vào lỗi, thay đổi trạng thái và những diễn biến cần tìm kiếm.

Bộ lọc **không đồng nghĩa** với mức log. Level phân loại độ nghiêm trọng hoặc độ chi tiết; Filter diễn đạt thêm điều kiện, chẳng hạn loại sự kiện health-check, chỉ nhận bản ghi của một thành phần, hoặc chỉ cho một loại sự kiện đi vào một handler. Bộ lọc cũng **không tự che dữ liệu nhạy cảm**: việc bỏ toàn bộ bản ghi không thay cho thiết kế dữ liệu log an toàn.

## 2. Bộ lọc nằm ở đâu trong kiến trúc logging?

Với Java SE, API **java.util.logging (JUL)** cung cấp giao diện **java.util.logging.Filter**, có thể gắn ở **Logger** hoặc **Handler**.

~~~text
Mã ứng dụng
   |
   | logger.log(...) / logger.info(...)
   v
Logger nguồn phát sinh
   |
   +-- Kiểm tra mức log hữu hiệu của Logger
   |       Không đạt -> bỏ bản ghi
   |
   +-- Filter của Logger (nếu có)
   |       false -> bỏ bản ghi trước các Handler
   |
   +-- Handler A
   |      +-- kiểm tra level của Handler A
   |      +-- Filter của Handler A (nếu có)
   |      +-- Formatter -> console
   |
   +-- Handler B
   |      +-- kiểm tra level của Handler B
   |      +-- Filter của Handler B (nếu có)
   |      +-- Formatter -> file/collector
   |
   +-- Handler của Logger cha nếu useParentHandlers=true
          +-- kiểm tra level và Filter của mỗi Handler
          +-- Formatter -> đầu ra tương ứng
~~~

Ở sơ đồ trên, mỗi Handler có chính sách riêng, vì vậy một bản ghi có thể được Handler A ghi nhận nhưng bị Handler B loại bỏ.

Cần phân biệt rõ các điểm:

1. **Filter gắn vào Logger** kiểm soát bản ghi đi vào luồng xử lý của chính Logger được gọi. Nếu từ chối, các Handler nhận log từ lời gọi đó không nhận bản ghi.
2. **Filter gắn vào Handler** chỉ kiểm soát đầu ra của Handler tương ứng. Nó không tự chặn các Handler còn lại.
3. **Level của Logger** được kiểm tra trước khi bản ghi được chuyển xuống các Handler. Nếu Logger không cho INFO qua, việc đặt Handler ở mức ALL sẽ không khôi phục được bản ghi INFO.
4. **Level của Handler** là một ngưỡng riêng. Logger cho phép FINE nhưng Handler ở INFO thì bản ghi FINE vẫn không được Handler đó xuất.
5. Nếu **useParentHandlers=true**, bản ghi có thể được gửi thêm đến các Handler của các Logger cha. Khi chuyển bản ghi lên chuỗi Handler này, JUL không mặc nhiên gọi lại Filter của mỗi Logger cha như thể ứng dụng đã gọi log trên Logger cha; các Handler của cha áp dụng bộ lọc riêng của chúng.
6. Nếu gọi **logger.log(...)** trực tiếp trên một Logger cha thì Filter của Logger cha đó vẫn có tác dụng. Đừng nhầm điều này với việc truyền bản ghi của Logger con tới Handler của cha.

Điểm cuối thường gây lỗi cấu hình: đặt một Filter lên Logger cha rồi cho rằng Filter ấy tự chặn toàn bộ log từ mọi Logger con. Muốn lọc chắc chắn tại **một đầu ra chung**, hãy gắn Filter lên Handler nhận các bản ghi đó; muốn lọc ngay từ **nguồn phát sinh**, gắn Filter tại Logger phù hợp.

## 3. Giao diện Filter và dữ liệu có thể kiểm tra

JUL định nghĩa Filter như một giao diện chức năng với một phương thức:

~~~java
public interface Filter {
    boolean isLoggable(java.util.logging.LogRecord record);
}
~~~

Đây là **chữ ký minh họa** của giao diện chuẩn; khi viết ứng dụng, hãy import **java.util.logging.Filter**, không cần tự khai báo lại giao diện này.

Giá trị trả về:

- **true**: bản ghi vượt qua bộ lọc tại điểm được gắn và có thể tiếp tục xử lý.
- **false**: bản ghi bị loại tại điểm đó.
- Vượt qua Filter **không bảo đảm** log đã xuất: còn ngưỡng level, các Handler, Filter khác, formatter, cấu hình đầu ra và khả năng ghi dữ liệu.

**LogRecord** chứa dữ liệu của một sự kiện logging. Các thuộc tính thường dùng:

| Thành phần | API JUL | Cách dùng |
| --- | --- | --- |
| Mức log | record.getLevel() | Kiểm tra INFO, WARNING, SEVERE, FINE... |
| Thông điệp gốc | record.getMessage() | Nhận dạng một tên sự kiện cố định |
| Tên Logger | record.getLoggerName() | Lọc theo component/package đã đặt tên |
| Tham số | record.getParameters() | Lấy ngữ cảnh cấu trúc mà ứng dụng truyền vào |
| Ngoại lệ đính kèm | record.getThrown() | Phân biệt bản ghi có Throwable hay không |
| Thời điểm | record.getInstant() | Thông tin thời điểm của bản ghi |
| Tên lớp và phương thức nguồn | record.getSourceClassName(), getSourceMethodName() | Có thể hữu ích nhưng không phải lúc nào cũng sẵn có hoặc rẻ để suy ra |

Chẳng hạn, một bộ lọc chỉ cho các bản ghi mức WARNING trở lên đi qua có thể viết:

~~~java
Filter warningsAndErrors = record ->
        record.getLevel().intValue() >= Level.WARNING.intValue();
~~~

Đây là **đoạn mã minh họa**, cần import Filter và Level, gắn nó vào Logger hoặc Handler. Trong thực tế, nếu chỉ cần ngưỡng WARNING thì **setLevel(Level.WARNING)** đơn giản và thường thích hợp hơn. Filter dành cho điều kiện bổ sung mà Level đơn thuần không biểu diễn được.

Một Filter tốt nên **nhanh, xác định, ít tác dụng phụ** và có chính sách khi thiếu trường dữ liệu. Không nên thực hiện truy vấn cơ sở dữ liệu, gọi mạng, hoặc ghi log khác ngay trong Filter; nếu Filter tự log qua cùng luồng, nó có thể gây đệ quy.

## 4. Level và Filter khác nhau thế nào?

| Khía cạnh | Level | Filter |
| --- | --- | --- |
| Câu hỏi | Bản ghi có đủ mức quan trọng để được xem xét? | Bản ghi này có thỏa điều kiện cụ thể không? |
| Tiêu chí chính | Thang mức đã xác định | Nội dung, nguồn phát, sự kiện, ngữ cảnh hoặc chính sách |
| JUL | Logger.setLevel(), Handler.setLevel() | Logger.setFilter(), Handler.setFilter() |
| Cách biểu đạt | Ví dụ nhận INFO trở lên | Ví dụ bỏ health.ping nhưng giữ INFO khác |
| Chi phí | So sánh ngưỡng đơn giản | Phụ thuộc logic bộ lọc |
| Phạm vi | Mỗi Logger/Handler có ngưỡng riêng | Mỗi Logger/Handler có Filter riêng |

Trong JUL, một số mức thông dụng theo độ chi tiết giảm dần là **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. Ngoài ra có **ALL** và **OFF** dành cho cấu hình ngưỡng. Đừng lấy giá trị số của mức log để suy diễn quy tắc nghiệp vụ: một sự kiện INFO có thể rất quan trọng cho việc hiểu kết quả, còn một WARNING cụ thể có thể là nhiễu của một môi trường thử nghiệm.

Ví dụ ý nghĩa cấu hình:

~~~text
Logger level = ALL
Logger Filter = bỏ sự kiện health.ping
Handler console level = INFO
Handler console Filter = bỏ nhóm INTERNAL

FINE cache.lookup       -> Logger cho qua -> Handler loại do level
INFO health.ping        -> Logger Filter loại
INFO cache.warmup       -> Logger cho qua -> Handler Filter loại
INFO order.created      -> Logger cho qua -> Handler cho qua
WARNING inventory.slow  -> Logger cho qua -> Handler cho qua
~~~

## 5. Ví dụ Java 17+ chạy độc lập: Filter ở Logger và Handler

Ví dụ dưới đây tạo các sự kiện có trường **event**, **requestId** và **category**. Ta dùng một **record Event** (Java 17 hỗ trợ) truyền qua **LogRecord.setParameters()**, nhờ vậy Filter của Handler kiểm tra loại sự kiện mà không phải dò chuỗi thông báo tự do.

Quy tắc:

- Logger bỏ sự kiện **health.ping**; các sự kiện khác có thể đi tiếp.
- Handler chỉ nhận bản ghi ở mức **INFO trở lên**.
- Handler bỏ nhóm **INTERNAL**.
- Formatter xuất một dòng cố định, giúp kiểm chứng chính xác kết quả.
- Handler xuất ra **stdout**; thông thường ConsoleHandler của JUL ghi ra **stderr** và có format khác.

Lưu toàn bộ chương trình dưới tên **LogFilterDemo.java**:

~~~java
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogFilterDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.filter");

    private enum Category {
        SYSTEM, BUSINESS, INTERNAL, DEPENDENCY
    }

    private record Event(String name, String requestId, Category category) {}

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Filter sourceFilter =
                record -> !"health.ping".equals(record.getMessage());
        LOG.setFilter(sourceFilter);

        Handler console = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                Event event = eventOf(record);
                if (event == null) {
                    return record.getLevel().getName() + " | "
                            + record.getMessage() + System.lineSeparator();
                }
                return record.getLevel().getName()
                        + " | event=" + event.name()
                        + " requestId=" + event.requestId()
                        + " category=" + event.category()
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        console.setLevel(Level.INFO);
        console.setFilter(record -> {
            Event event = eventOf(record);
            return event == null || event.category() != Category.INTERNAL;
        });
        LOG.addHandler(console);

        try {
            emit(Level.FINE, "cache.lookup", "req-42", Category.BUSINESS);
            emit(Level.INFO, "health.ping", "req-42", Category.SYSTEM);
            emit(Level.INFO, "cache.warmup", "job-7", Category.INTERNAL);
            emit(Level.INFO, "order.created", "req-42", Category.BUSINESS);
            emit(Level.WARNING, "inventory.slow", "req-42",
                    Category.DEPENDENCY);
        } finally {
            LOG.removeHandler(console);
            console.flush();
        }
    }

    private static void emit(
            Level level, String name, String requestId, Category category) {
        Event event = new Event(name, requestId, category);
        LogRecord record = new LogRecord(level, event.name());
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {event});
        LOG.log(record);
    }

    private static Event eventOf(LogRecord record) {
        Object[] parameters = record.getParameters();
        if (parameters != null && parameters.length == 1
                && parameters[0] instanceof Event event) {
            return event;
        }
        return null;
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac LogFilterDemo.java
java LogFilterDemo
~~~

**Stdout chính xác:**

~~~text
INFO | event=order.created requestId=req-42 category=BUSINESS
WARNING | event=inventory.slow requestId=req-42 category=DEPENDENCY
~~~

### Giải thích lần lượt từng bản ghi

| Lời gọi | Logger level | Logger Filter | Handler level | Handler Filter | Kết quả |
| --- | --- | --- | --- | --- | --- |
| FINE cache.lookup | Qua (ALL) | Qua | Không đạt INFO | Không cần kiểm tra tiếp | Không xuất |
| INFO health.ping | Qua | Từ chối theo event | Không nhận bản ghi | Không nhận bản ghi | Không xuất |
| INFO cache.warmup, INTERNAL | Qua | Qua | Qua | Từ chối INTERNAL | Không xuất |
| INFO order.created, BUSINESS | Qua | Qua | Qua | Qua | Xuất dòng INFO |
| WARNING inventory.slow, DEPENDENCY | Qua | Qua | Qua | Qua | Xuất dòng WARNING |

**Điểm kỹ thuật cần hiểu:**

1. **LOG.setUseParentHandlers(false)** ngăn các Handler của Logger cha xuất thêm bản ghi, giúp ví dụ có đúng một đích và tránh log trùng do kế thừa cấu hình.
2. **LOG.setLevel(Level.ALL)** chỉ mở ngưỡng của Logger. Nó không bỏ qua Filter, và không thay đổi ngưỡng của Handler.
3. **LOG.setFilter(sourceFilter)** áp dụng quy tắc loại tên sự kiện health.ping ở điểm phát sinh.
4. **console.setLevel(Level.INFO)** khiến FINE không được in ra, dù Logger cho phép mức FINE.
5. **console.setFilter(...)** loại bản ghi nhóm INTERNAL chỉ trên Handler console này. Nếu gắn thêm Handler khác, Handler đó sẽ có level và Filter riêng.
6. **LogRecord.setParameters()** chuyển một đối tượng Event vào bản ghi. Ví dụ dùng metadata có kiểu để trình diễn; đây không phải cơ chế structured logging JSON tự động có sẵn trong JUL.
7. **eventOf(record)** xử lý trường hợp không có Event và trả về null. Với log bên ngoài không theo định dạng của ứng dụng, chính sách trong ví dụ là cho qua Handler Filter; trong production phải lựa chọn rõ hành vi khi thiếu metadata.
8. Override **publish()** rồi gọi **flush()** giúp StreamHandler đẩy từng dòng ra stdout. StreamHandler thông thường có bộ đệm. Ví dụ không đóng handler đã dùng System.out vì việc đóng có thể đóng luôn luồng stdout của chương trình.
9. Formatter ở đây chủ động dựng một chuỗi dễ kiểm chứng, không dùng format ngày giờ phụ thuộc múi giờ hoặc định dạng mặc định của JUL. Vì vậy stdout ở trên ổn định.
10. Filter sử dụng bản ghi đã hình thành; đừng coi Filter là giải pháp tránh mọi chi phí dựng LogRecord hay đánh giá tham số. Ngưỡng Logger và API logging lazy khi thích hợp vẫn rất quan trọng cho hiệu năng.

## 6. Đặt Filter ở đâu cho đúng mục đích?

### Lọc tại Logger: giảm một loại sự kiện ngay từ nguồn

Ví dụ dịch vụ có Logger riêng cho heartbeat, có thể gắn Filter vào chính Logger phát ra sự kiện đó nếu tất cả đích đều không cần heartbeat. Đối với health check, đôi khi cách tốt nhất là **không tạo log INFO ngay từ đầu**, chỉ ghi trạng thái không khỏe hoặc tình huống bất thường. Khi ứng dụng vẫn phải ghi một số heartbeat cho mục đích khác, Filter giúp điều chỉnh ở runtime.

Dùng Logger Filter khi tiêu chí phải ảnh hưởng **mọi Handler nhận bản ghi từ lời gọi trên Logger nguồn đó**. Không giả định cấu hình trên một Logger cha tự lọc tất cả lời gọi được phát ra từ Logger con.

### Lọc tại Handler: mỗi nơi nhận log có chính sách riêng

Ví dụ:

~~~text
                       Logger xử lý đơn hàng
                                |
                     Filter ở Logger: cho qua
                                |
                +---------------+---------------+
                |                               |
          Console Handler                 File Handler
        level=WARNING                  level=INFO
        filter=mọi nhóm                 filter=bỏ nhóm INTERNAL
                |                               |
         Cảnh báo kỹ thuật                 Bản ghi vận hành
~~~

Cùng một bản ghi INFO nghiệp vụ có thể được lưu vào file nhưng không xuất trên console; một WARNING có thể đi tới cả hai đầu ra. **Handler Filter không thể làm cho Logger sinh lại bản ghi đã bị Logger level/Logger Filter loại trước đó.**

Đây là ví dụ kiến trúc, không phải một đoạn chương trình hoàn chỉnh.

### Định tuyến và lọc là hai việc khác nhau

Filter chỉ quyết định **cho qua hay từ chối**. Nó không tự chọn Handler mới, đổi level, biến đổi bản ghi hoặc chuyển bản ghi sang file khác. Muốn định tuyến vào nhiều đích, phải cấu hình các Handler và chính sách riêng, hoặc sử dụng logging framework/pipeline có chức năng routing tương ứng.

## 7. Những cách viết Filter thường gặp

Các đoạn sau là **mẫu minh họa**, không phải các chương trình độc lập. Chúng giả định đã import các kiểu cần thiết và có sẵn đối tượng Logger/Handler tương ứng.

**a) Lọc theo tên Logger**

~~~java
Filter serviceOnly = record -> {
    String name = record.getLoggerName();
    return name != null
            && (name.equals("com.example.orders")
                || name.startsWith("com.example.orders."));
};
~~~

Dùng dấu chấm sau tên package để tránh nhận nhầm tên bắt đầu giống nhau, chẳng hạn ordersLegacy. Trong trường hợp LogRecord được ứng dụng tạo thủ công, tên Logger có thể null nếu bên phát sinh không đặt tên; cần chủ động quyết định xử lý.

**b) Lọc theo tên event chính xác**

~~~java
Filter excludePing =
        record -> !"health.ping".equals(record.getMessage());
~~~

Nếu thông điệp chứa văn bản dịch qua ResourceBundle, tham số hoặc chuỗi tự do, việc dùng **getMessage()** để nhận dạng event có thể không ổn định. Nên dùng mã event do ứng dụng kiểm soát và mô hình metadata rõ ràng, như ví dụ Event ở trên.

**c) Lọc theo ngoại lệ đính kèm**

~~~java
Filter withThrowable = record -> record.getThrown() != null;
~~~

Bộ lọc này chỉ nhận bản ghi được tạo với **Throwable đính kèm vào LogRecord**. Một chuỗi message tự viết chữ "Exception" không làm cho getThrown() khác null. Không nên dùng chính sách chỉ nhận Throwable cho luồng nghiệp vụ, vì sẽ bỏ nhiều sự kiện có giá trị điều tra.

**d) Lọc theo nhóm sự kiện**

~~~java
Filter businessOrDependency = record -> {
    Event event = eventOf(record);
    return event != null
            && (event.category() == Category.BUSINESS
                || event.category() == Category.DEPENDENCY);
};
~~~

Đoạn này dựa vào các kiểu **Event, Category** và helper **eventOf** trong ví dụ LogFilterDemo. Nếu thiếu metadata, nó trả về false. Chính sách này khác với Handler Filter trong chương trình chính, vốn cho qua bản ghi không có Event; không có lựa chọn nào đúng cho mọi hệ thống.

## 8. Trình tự quyết định và lỗi dễ nhầm

Để kiểm tra một log không xuất hiện, hãy đi theo thứ tự:

1. Lời gọi logging có chạy thật không? Nếu dùng điều kiện bên ngoài hoặc một nhánh chưa tới, Filter không liên quan.
2. Logger phát sinh có đạt level không? Có bị thừa hưởng ngưỡng từ Logger cha không?
3. Logger phát sinh có Filter và Filter có trả về false không?
4. Bản ghi được chuyển tới Handler nào? **useParentHandlers** có cho phép gửi lên Handler của Logger cha không?
5. Handler tương ứng có level gì? Có Filter riêng và Filter ấy quyết định thế nào?
6. Handler có formatter, stream/file/collector hoạt động đúng không? Có lỗi ghi dữ liệu, buffering hoặc cấu hình đầu ra không?

**Ví dụ chẩn đoán:** ứng dụng đặt Logger level FINE, Handler level INFO và thêm Filter chấp nhận FINE. Khi log FINE biến mất, nguyên nhân là **Handler level**, không phải Filter. Ngược lại, khi INFO của health.ping biến mất trong chương trình mẫu, nguyên nhân là **Logger Filter**, dù Handler cho phép INFO.

Một lỗi khác là **lọc ở Logger rồi tưởng chỉ lọc một đích**. Khi cần bỏ sự kiện trên console nhưng vẫn lưu bản ghi vào file để điều tra, hãy đặt điều kiện ở Console Handler; đừng lọc tại Logger nguồn vì file cũng sẽ không có bản ghi đó.

## 9. Thiết kế bộ lọc an toàn và hiệu quả trong production

### Không làm mất bằng chứng quan trọng

Một quy tắc lọc bất cẩn có thể che dấu sự cố. Ví dụ lọc tất cả các sự kiện có đường dẫn chứa health sẽ vô tình bỏ cả log health endpoint thất bại. Nên lọc bằng **mã event cụ thể** và phân biệt heartbeat thành công với cảnh báo bất thường, thay vì dựa vào chuỗi chung chung.

Giữ log về lỗi nghiêm trọng, các thay đổi trạng thái cần điều tra và sự kiện an ninh theo chính sách tổ chức. Với **audit trail**, yêu cầu có thể bao gồm đầy đủ sự kiện, kiểm soát sửa đổi, lưu trữ và phân quyền; không nên dùng bộ lọc vận hành theo kiểu lấy mẫu để bỏ các bản ghi kiểm toán bắt buộc.

### Quy tắc cho bản ghi thiếu trường

Trước khi triển khai Filter, định nghĩa rõ:

- Nếu không có eventName/category/requestId, cho qua để không mất log hay từ chối để bảo vệ luồng đầu ra chuyên biệt?
- Nếu level là SEVERE nhưng category INTERNAL, có được bỏ không?
- Nếu một sự kiện mới xuất hiện sau khi nâng phiên bản, Filter có loại nhầm không?

**Fail-open** (thiếu metadata thì cho qua) giúp giảm nguy cơ mất log điều tra, nhưng có thể gây nhiễu. **Fail-closed** (thiếu metadata thì bỏ) hữu ích cho luồng chỉ nhận sự kiện hợp lệ, nhưng có nguy cơ bỏ sự kiện mới. Chọn theo mục đích của đích log, không dùng chung một chính sách mù quáng.

### Dữ liệu nhạy cảm và log injection

Filter có thể chặn **toàn bộ** bản ghi khi phát hiện một quy tắc, nhưng không tự xóa trường password hoặc token trong các bản ghi được chấp nhận. Không đưa bí mật hoặc payload nhạy cảm vào LogRecord ngay từ nguồn; dùng chính sách data minimization, masking và encoder thích hợp khi phải xuất dữ liệu có kiểm soát.

Tránh điều kiện lọc bằng cách ghép input người dùng chưa chuẩn hóa vào regex hoặc chuỗi thông báo, đặc biệt là các dữ liệu có ký tự điều khiển/xuống dòng. Dùng mã event cố định và xử lý escape ở formatter/encoder. Filter đơn thuần không chống được log injection nếu bản ghi được chấp nhận vẫn chứa nội dung độc hại.

### Chi phí và khả năng chạy đồng thời

Trong ứng dụng nhiều request, Filter có thể được gọi thường xuyên và đồng thời. Vì vậy:

- Ưu tiên so sánh đơn giản trên mã sự kiện hoặc nhóm dữ liệu đã chuẩn hóa.
- Tránh truy vấn mạng, I/O, lock nặng, regex tốn thời gian và tính toán lớn trong isLoggable().
- Nếu dùng đếm hoặc sampling có trạng thái, phải kiểm soát thread-safety; phép tăng biến thường không an toàn khi nhiều thread cập nhật.
- Kiểm tra tính ổn định khi Filter bị gọi đồng thời; lý tưởng nhất là cấu hình bất biến và logic không có side effect.
- Lấy mẫu chỉ cho log lưu lượng lớn, ít giá trị cá thể. Không lấy mẫu bừa các cảnh báo hoặc lỗi cần điều tra từng sự kiện.
- Đừng log một thông điệp mới bên trong Filter để giải thích bản ghi bị bỏ: có thể tạo vòng lặp logging và làm chi phí tăng đột biến.

Nếu muốn giảm chi phí tạo thông điệp chẩn đoán, kiểm tra **level** trước khi xây thông điệp đắt tiền và dùng overload Supplier thích hợp, ví dụ **logger.fine(() -> expensiveDescription())**. Filter có thể được gọi sau bước tạo bản ghi; nó không thay thế hoàn toàn việc thiết kế logging tiết kiệm.

## 10. JUL Filter so với SLF4J, Logback và Log4j 2

Cần phân biệt **API** với **backend**:

| Công nghệ | Vai trò liên quan |
| --- | --- |
| java.util.logging (JUL) | API và implementation có sẵn trong Java SE; dùng Filter trên Logger/Handler |
| SLF4J | Facade để ứng dụng gọi logging; không có một quy tắc Filter backend-agnostic giống hệt JUL |
| Logback | Backend phổ biến khi dùng SLF4J; có Filter ở appender và TurboFilter ở context, với ngữ nghĩa riêng |
| Log4j 2 | API/backend có các bộ lọc ở nhiều vị trí như LoggerConfig và Appender, theo quy tắc ACCEPT/DENY/NEUTRAL của framework |
| Log collector/agent | Có thể lọc sau khi ứng dụng đã xuất log; không tiết kiệm hoàn toàn chi phí sinh và ghi bản ghi ban đầu |

Không mang nguyên API **Logger.setFilter(Filter)** của JUL sang ví dụ SLF4J/Logback hay Log4j 2 rồi kỳ vọng biên dịch. Khi sử dụng framework khác, phải kiểm tra cơ chế, thứ tự và vị trí áp dụng Filter của framework đó.

**Trường hợp thực tế:** một ứng dụng Spring Boot thường gọi logging qua SLF4J và dùng Logback theo cấu hình mặc định của nhiều phiên bản. Nếu muốn giảm log HTTP health check trong ứng dụng như vậy, phải xem Logger, appender/filter hoặc cấu hình HTTP access log đang thực sự phát bản ghi, thay vì thêm JUL Filter vào một Logger không nằm trong đường log thực tế.

## 11. Kiểm thử Filter như một chính sách vận hành

Một Filter tốt không chỉ có điều kiện đúng mà còn phải tránh bỏ nhầm những sự kiện quan trọng.

Dùng bảng kiểm thử nhỏ, rõ điều kiện đầu vào và kết quả kỳ vọng:

| Trường hợp | Mức | Event | Category | Kỳ vọng với chương trình mẫu |
| --- | --- | --- | --- | --- |
| Chi tiết cache | FINE | cache.lookup | BUSINESS | Không xuất do Handler level |
| Health check | INFO | health.ping | SYSTEM | Không xuất do Logger Filter |
| Công việc nội bộ | INFO | cache.warmup | INTERNAL | Không xuất do Handler Filter |
| Nghiệp vụ thành công | INFO | order.created | BUSINESS | Xuất |
| Phụ thuộc chậm | WARNING | inventory.slow | DEPENDENCY | Xuất |
| Bản ghi không có Event | INFO | unknown.message | không có | Formatter dùng nhánh fallback; các Filter mẫu cho qua |

Khi bổ sung một Logger con hoặc Handler mới, hãy kiểm tra thêm **phạm vi kế thừa Handler**. Một Filter hoạt động trên Handler console chưa chắc đã được áp dụng trên Handler file. Và một Filter đặt ở Logger cha không được mặc nhiên áp dụng lên bản ghi phát sinh từ Logger con khi bản ghi chỉ được truyền tới Handler của Logger cha.

Nên đo lại lượng log, chi phí và khả năng truy vết sau khi bật Filter. Nếu giảm được số dòng nhưng không còn giải thích được nguyên nhân một yêu cầu thất bại, chính sách lọc chưa đạt mục tiêu.

## 12. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ Filter và Level là một | Không tìm ra vì sao log bị bỏ | Kiểm tra cả level và Filter trên Logger/Handler |
| Đặt Handler level ALL để cứu log đã bị Logger chặn | Log vẫn mất | Chỉnh mức hoặc Filter của Logger nguồn |
| Chỉ đặt Filter trên Logger cha | Log từ Logger con vẫn có thể tới Handler cha | Gắn Filter tại nguồn cần lọc hoặc trên Handler chung |
| Đặt Filter trên Logger nguồn khi chỉ muốn lọc console | File và các Handler khác cùng mất log | Lọc riêng Console Handler |
| Dựa vào chuỗi văn bản tùy ý | Điều kiện dễ hỏng khi đổi thông điệp/ngôn ngữ | Dùng mã event và metadata ổn định |
| Bỏ mọi log có chữ "health" | Có thể che lỗi health check | Chỉ lọc sự kiện thành công cụ thể |
| Lọc bỏ WARNING/SEVERE theo nhóm nội bộ một cách máy móc | Mất cảnh báo cần điều tra | Quy định ngoại lệ giữ lỗi nghiêm trọng và audit bắt buộc |
| Coi Filter là bộ che bí mật | Log được cho qua vẫn chứa dữ liệu nhạy cảm | Giảm dữ liệu tại nguồn và dùng encoder/masking phù hợp |
| Thực hiện I/O hoặc log trong isLoggable() | Chậm, đệ quy hoặc lỗi khó chẩn đoán | Giữ Filter đơn giản, nhanh, không side effect |
| Không thử nhiều Handler hoặc Logger con | Chính sách hoạt động khác dự kiến | Kiểm tra ma trận Logger/Handler/Filter và đường truyền tới Logger cha |

## 13. Checklist khi triển khai Bộ lọc log

1. Xác định **đích ghi log** và lý do cần loại sự kiện: console, file, collector, hay tất cả.
2. Phân loại tín hiệu cần giữ: kết quả nghiệp vụ, lỗi kỹ thuật, cảnh báo, sự kiện bảo mật và audit.
3. Chọn **Level** cho ngưỡng đơn giản, chọn **Filter** khi cần điều kiện theo event/metadata.
4. Quyết định đặt Filter tại **Logger nguồn** hay **Handler cụ thể**; kiểm tra **useParentHandlers**.
5. Dùng tên event ổn định và thông tin cấu trúc; có chính sách rõ ràng khi bản ghi thiếu trường.
6. Giữ Filter nhẹ, thread-safe, không I/O và không ghi log vòng lại.
7. Thử cả sự kiện được giữ và bị bỏ; xác minh bằng đầu ra thực tế của từng Handler.
8. Đo lượng log và kiểm tra xem vẫn truy vết được yêu cầu thất bại hoặc sự kiện quan trọng hay không.
9. Xem lại quy tắc lọc khi thêm endpoint, thay Logger, thêm Handler hoặc đổi logging backend.

**Kết luận:** Bộ lọc log là một mắt xích trong pipeline logging, quyết định bản ghi nào được đi tới đích. Hiểu rõ ranh giới **Logger Filter → Handler level/Filter → Formatter/đầu ra** giúp loại nhiễu mà vẫn giữ dữ liệu quan trọng để vận hành và điều tra sự cố.
