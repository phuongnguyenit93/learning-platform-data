# Thông điệp bản địa hóa qua ResourceBundle trong Java Logging

**ResourceBundle** cho phép tách nội dung thông điệp khỏi mã nguồn để ứng dụng chọn câu chữ theo **Locale**. Trong Java Logging (**java.util.logging**), logger có thể ghi một khóa thông điệp cùng tham số; formatter dùng ResourceBundle để chuyển khóa thành câu chữ đúng ngôn ngữ khi hiển thị log.

Cách này giúp một sự kiện nghiệp vụ có cùng ý nghĩa và mức log ở mọi ngôn ngữ, trong khi câu chữ có thể thay đổi theo người vận hành hoặc giao diện xem log. Với hệ thống cần phân tích tự động, nên giữ event key, logger name và level ổn định; bản dịch là lớp trình bày, không phải định danh sự kiện.

## 1. ResourceBundle giải quyết vấn đề gì?

Nếu viết trực tiếp câu chữ vào mã nguồn:

~~~java
logger.info("User signed in");
~~~

thì mọi nơi dùng thông điệp đó phải thay đổi mã khi cần thêm ngôn ngữ. Câu chữ cũng dễ bị sao chép khác nhau giữa các module.

ResourceBundle chuyển câu chữ thành dữ liệu bên ngoài:

~~~java
logger.logrb(
    Level.INFO,
    MyService.class.getName(),
    "login",
    bundle,
    "user.login",
    new Object[] {"An"}
);
~~~

Ở đây:

- **bundle** là bộ thông điệp cho một locale cụ thể.
- **user.login** là khóa ổn định trong file tài nguyên.
- **An** là tham số được chèn vào mẫu câu.
- **Level.INFO** và tên logger vẫn giữ nguyên dù thông điệp được dịch.

Mã nghiệp vụ phát ra cùng một sự kiện. Resource bundle quyết định câu chữ cho tiếng Việt, tiếng Anh hoặc locale khác.

## 2. Locale và quy tắc tìm bundle

Locale mô tả ngôn ngữ, vùng và có thể cả script hoặc biến thể. Nên dùng mã ngôn ngữ theo BCP 47:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale english = Locale.forLanguageTag("en-US");
~~~

Giả sử base name là **messages.LogMessages**, Java tìm các file theo quy ước:

~~~text
messages/
  LogMessages.properties
  LogMessages_vi.properties
  LogMessages_vi_VN.properties
  LogMessages_en.properties
~~~

Tên file được tạo từ base name và phần locale:

| File | Mục đích |
|---|---|
| LogMessages.properties | Bundle gốc, dùng làm fallback |
| LogMessages_vi.properties | Tiếng Việt nói chung |
| LogMessages_vi_VN.properties | Tiếng Việt cho Việt Nam |
| LogMessages_en.properties | Tiếng Anh |

Với locale **vi-VN**, Java thử bundle phù hợp cụ thể trước, sau đó lùi về locale ít cụ thể hơn như **vi**, rồi tới bundle gốc. Quy tắc candidate có thể bao gồm script và variant nếu locale có các thành phần đó.

Tạo bundle:

~~~java
ResourceBundle bundle =
    ResourceBundle.getBundle("messages.LogMessages", vietnamese);
~~~

**bundle.getLocale()** cho biết locale của bundle thực tế được chọn. Nếu chỉ có **LogMessages_vi.properties**, kết quả là locale **vi**, dù locale yêu cầu là **vi-VN**.

Nếu không có bundle phù hợp cho locale yêu cầu, cơ chế lookup còn có thể thử default locale của JVM trước khi dùng bundle gốc. Vì vậy, hãy cung cấp bundle gốc và các bản dịch cần thiết; đừng dựa vào default locale của máy chủ để quyết định ngôn ngữ nghiệp vụ.

## 3. Cấu trúc file properties và UTF-8

Một file gốc có thể là:

~~~properties
app.started=Application started.
user.login=User {0} signed in.
requests.processed=Processed {0} requests.
connection.closed=Connection closed: {0}
~~~

Bản tiếng Việt:

~~~properties
app.started=Ứng dụng đã khởi động.
user.login=Người dùng {0} đã đăng nhập.
requests.processed=Đã xử lý {0} yêu cầu.
~~~

Các điểm cần lưu ý:

- Mỗi dòng chứa một cặp key=value.
- Key nên ổn định, có ý nghĩa nghiệp vụ và không phụ thuộc ngôn ngữ.
- Giá trị là câu chữ được dịch; giữ nguyên placeholder như {0} và {1}.
- Dùng UTF-8 để lưu file, đặc biệt khi có dấu tiếng Việt.
- Tránh duplicate key vì giá trị được khai báo sau có thể thay thế giá trị trước.
- Dấu =, :, khoảng trắng đầu dòng, dấu # và ! có quy tắc escape riêng trong properties; nếu câu chữ có ký tự đặc biệt ở đầu hoặc cần xuống dòng, hãy escape đúng cú pháp.

Từ Java 9, properties bundle do ResourceBundle nạp mặc định dùng UTF-8. Điều này thuận tiện cho bản dịch Unicode mà không phải chuyển ký tự sang dạng \uXXXX. Quy tắc này áp dụng cho resource bundle properties; không được suy ra rằng mọi cách đọc file bằng Properties.load(InputStream) cũng tự động dùng UTF-8. Với Properties, encoding còn phụ thuộc overload: load(InputStream) có quy tắc riêng, còn load(Reader) dùng encoding của Reader.

## 4. Lấy thông điệp theo key

Ví dụ nạp bundle và đọc chuỗi:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
    ResourceBundle.getBundle("messages.LogMessages", locale);

String title = bundle.getString("app.started");
~~~

getString(key) tìm key trong bundle được chọn và các bundle cha theo fallback chain. Nếu key không có ở bundle cụ thể nhưng tồn tại trong bundle cha, giá trị cha được dùng.

Nếu key không tồn tại trong toàn bộ chuỗi, getString ném MissingResourceException. Đây thường là lỗi cấu hình hoặc lỗi đóng gói tài nguyên; không nên âm thầm thay bằng một chuỗi rỗng vì log có thể mất thông tin.

Có thể kiểm tra trước:

~~~java
if (bundle.containsKey("user.login")) {
    String pattern = bundle.getString("user.login");
}
~~~

Không nên gọi containsKey cho mọi thông điệp trong hot path nếu bundle và key đã được kiểm tra trong quá trình build/test. Tốt hơn là kiểm tra tính đầy đủ của các bundle khi đóng gói ứng dụng.

## 5. Tích hợp ResourceBundle với java.util.logging

Java Logging hỗ trợ resource bundle trực tiếp trên LogRecord.

### Dùng logrb với bundle cụ thể

Overload nhận ResourceBundle:

~~~java
logger.logrb(
    Level.INFO,
    MyService.class.getName(),
    "login",
    bundle,
    "user.login",
    new Object[] {"An"}
);
~~~

Các tham số gồm level, tên class nguồn, tên method nguồn, bundle, message key và danh sách tham số.

Khi handler dùng Formatter.formatMessage(record), formatter lấy key từ LogRecord, tra nội dung trong resource bundle rồi thay placeholder bằng các tham số. Ví dụ key user.login có thể được hiển thị thành:

~~~text
Người dùng An đã đăng nhập.
~~~

Dùng overload có bundle cụ thể hữu ích khi locale được chọn theo user, tenant hoặc request. Mỗi lần ghi log có thể mang bundle phù hợp mà không phải thay đổi locale mặc định toàn JVM.

### Gắn bundle name vào Logger

Có thể tạo logger với tên bundle:

~~~java
Logger logger =
    Logger.getLogger("com.example.account", "messages.LogMessages");
~~~

Sau đó các phương thức log thông thường có thể dùng message key của bundle gắn với logger:

~~~java
logger.log(Level.INFO, "user.login", new Object[] {"An"});
~~~

Cách này phù hợp khi một logger luôn sử dụng một bundle và locale theo cơ chế cấu hình của logging. Nếu cần chọn bundle theo locale tại từng lần ghi, logrb với đối tượng ResourceBundle tường minh dễ kiểm soát hơn.

### Formatter chịu trách nhiệm trình bày

LogRecord lưu message key, tham số và thông tin resource bundle. Formatter quyết định cách chuyển record thành văn bản.

Formatter đơn giản có thể dùng formatMessage:

~~~java
final class MessageOnlyFormatter extends java.util.logging.Formatter {
    @Override
    public String format(LogRecord record) {
        return formatMessage(record);
    }
}
~~~

Formatter mặc định của JDK cũng có cơ chế định dạng thông điệp qua resource bundle. Ứng dụng có thể tạo formatter riêng nếu cần thêm timestamp, logger name, thread, event id hoặc định dạng JSON.

Không nên tự gọi bundle.getString(key) ở mọi nơi rồi ghi chuỗi đã dịch nếu hệ thống logging đã có thể mang bundle và key trong LogRecord. Giữ record có đủ metadata giúp handler có thể chọn cách hiển thị hoặc xuất dữ liệu phù hợp.

## 6. MessageFormat và tham số động

Thông điệp thường chứa dữ liệu thay đổi theo sự kiện:

~~~properties
user.login=Người dùng {0} đã đăng nhập.
file.deleted=Đã xóa tệp {0} khỏi thư mục {1}.
requests.processed=Đã xử lý {0} yêu cầu.
~~~

Ghi log với tham số:

~~~java
logger.logrb(
    Level.INFO,
    MyService.class.getName(),
    "login",
    bundle,
    "user.login",
    new Object[] {"An"}
);
~~~

Formatter.formatMessage dùng quy tắc MessageFormat khi record có tham số. Nếu tự định dạng ngoài logging, có thể tạo MessageFormat với locale cụ thể:

~~~java
MessageFormat format =
    new MessageFormat(bundle.getString("user.login"), locale);

String message = format.format(new Object[] {"An"});
~~~

Một số kiểu placeholder thường gặp:

| Placeholder | Ý nghĩa |
|---|---|
| {0} | Chèn đối số thứ nhất |
| {0,number} | Định dạng số |
| {0,number,integer} | Định dạng số nguyên |
| {0,date,short} | Định dạng ngày |
| {0,time,short} | Định dạng thời gian |
| {0,choice,...} | Chọn mẫu theo khoảng giá trị |

### Định dạng số và ngày theo locale

Không nên định dạng số hoặc ngày bằng nối chuỗi thủ công. Dùng formatter gắn với locale cần hiển thị:

~~~java
NumberFormat numbers = NumberFormat.getIntegerInstance(locale);
String countText = numbers.format(12500);
~~~

Nếu đưa chuỗi đã định dạng vào {0}, kết quả không phụ thuộc default locale của thread đang xử lý record. Trong formatter tùy chỉnh, có thể tạo MessageFormat(pattern, locale) để MessageFormat dùng đúng locale.

Đối với ngày/giờ, cân nhắc DateTimeFormatter cùng locale và ZoneId phù hợp. Locale quyết định cách trình bày; time zone quyết định thời điểm địa phương. Hai khái niệm này không thay thế nhau.

### Escape dấu nháy trong MessageFormat

MessageFormat dùng dấu nháy đơn để quote cú pháp đặc biệt. Muốn hiển thị dấu nháy đơn trong kết quả, cần viết hai dấu nháy đơn liên tiếp trong pattern:

~~~properties
quote.example=Người dùng ''{0}'' đã đăng nhập.
~~~

Khi dịch, không xóa hoặc đổi thứ tự placeholder tùy tiện. Translator có thể đổi thứ tự {0}, {1} theo ngữ pháp của ngôn ngữ, nhưng số lượng và ý nghĩa tham số phải được giữ đúng.

## 7. Fallback và tính đầy đủ của bản dịch

Giả sử bundle gốc có:

~~~properties
connection.closed=Connection closed: {0}
~~~

nhưng bundle tiếng Việt không khai báo key đó. Khi gọi bundle.getString("connection.closed"), Java tìm tiếp ở bundle cha và lấy câu tiếng Anh từ file gốc.

Fallback theo key giúp ứng dụng không thất bại chỉ vì một bản dịch thiếu. Tuy nhiên, nó có thể tạo log trộn nhiều ngôn ngữ trong cùng một phiên. Với ứng dụng vận hành, hãy kiểm tra độ đầy đủ của từng bundle và quyết định rõ key nào được phép fallback.

Một số nguyên tắc:

- Bundle gốc phải có đầy đủ các key chuẩn.
- Bản dịch nên được kiểm tra so với danh sách key gốc trong CI.
- Khi thiếu key, fallback phải được ghi nhận trong quá trình kiểm thử hoặc monitoring.
- Không dùng một câu dịch mặc định chung cho mọi key; nó làm mất ngữ nghĩa.
- Không để key thay đổi theo ngôn ngữ hoặc theo câu chữ đã dịch.

ResourceBundle được cache theo base name, locale và class loader/module. Không nên nạp lại bundle ở mọi lần ghi log. Khi cập nhật file tài nguyên lúc ứng dụng đang chạy, cần có chiến lược reload rõ ràng; ResourceBundle.clearCache() chỉ nên dùng khi thực sự cần làm mới cache, không gọi trong hot path.

## 8. Chọn locale cho log ở đâu?

Locale của log là quyết định kiến trúc. Một máy chủ có thể phục vụ nhiều người dùng với locale khác nhau, trong khi log vận hành thường được đọc bởi đội hỗ trợ ở một locale chung.

Các lựa chọn:

1. **Locale cố định theo dịch vụ:** log server luôn dùng một ngôn ngữ chuẩn để tìm kiếm và vận hành dễ dàng.
2. **Locale theo tenant hoặc user:** phù hợp khi log được trả về trong giao diện riêng của tenant/user; cần chọn bundle tường minh theo request.
3. **Locale theo người xem:** lưu event key và tham số, sau đó dịch ở dashboard. Đây thường là cách tốt khi cùng một log cần được xem bằng nhiều ngôn ngữ.

Không nên gọi Locale.setDefault() theo từng request. Đây là trạng thái toàn JVM và có thể ảnh hưởng thread khác, formatter khác và thư viện khác. Hãy truyền Locale hoặc ResourceBundle tường minh tới nơi cần định dạng.

## 9. Log có cấu trúc và thông điệp đã dịch

Thông điệp bản địa hóa không nên làm mất khả năng tìm kiếm và phân tích log.

Ví dụ, nếu chỉ lưu:

~~~text
Người dùng An đã đăng nhập.
~~~

hệ thống phân tích phải hiểu nhiều bản dịch của cùng một sự kiện. Tốt hơn là giữ event key ổn định:

~~~text
event=user.login
userId=...
locale=vi-VN
message=Người dùng An đã đăng nhập.
~~~

java.util.logging cung cấp LogRecord với level, logger name, source class/method, message, parameters, throwable và resource bundle. Handler tùy chỉnh có thể xuất các trường ổn định này sang JSON hoặc hệ thống tập trung.

Khuyến nghị:

- Giữ event key ổn định, ví dụ user.login, payment.declined.
- Giữ Level và logger name không phụ thuộc bản dịch.
- Đưa dữ liệu biến đổi vào parameters hoặc trường có cấu trúc.
- Chỉ dịch câu chữ ở lớp formatter hoặc giao diện xem log.
- Không đưa password, token, session secret hoặc dữ liệu cá nhân không cần thiết vào log.
- Không dùng câu chữ đã dịch làm khóa truy vấn chính.

Đối với log kỹ thuật và cảnh báo máy chủ, một ngôn ngữ chuẩn cùng event key ổn định thường giúp on-call, alerting và phân tích xuyên dịch vụ dễ hơn. Bản dịch có thể được tạo ở giao diện quản trị nếu cần.

## 10. Ứng dụng trong named module

Trong ứng dụng chạy trên classpath, file bundle thường được đặt theo đường dẫn tương ứng với base name, ví dụ messages/LogMessages_vi.properties.

Trong ứng dụng dùng Java Platform Module System, việc tìm tài nguyên còn chịu quy tắc đóng gói và encapsulation của module. Bundle nên được đặt trong module phù hợp với code gọi; khi cần cung cấp bundle từ module khác, có thể dùng SPI ResourceBundleProvider và khai báo uses/provides trong module-info.java.

Không nên giả định một resource bundle nhìn thấy trên classpath sẽ tự động được phát hiện giống hệt khi chuyển ứng dụng sang named module. Hãy kiểm thử đóng gói module và đường dẫn tài nguyên trong chính cấu hình triển khai.

## 11. Ví dụ Java chạy được: Java Logging với bundle tiếng Việt

Cấu trúc tệp:

~~~text
project/
  LocalizedLoggingExample.java
  messages/
    LogMessages.properties
    LogMessages_vi.properties
~~~

messages/LogMessages.properties:

~~~properties
app.started=Application started.
user.login=User {0} signed in.
requests.processed=Processed {0} requests.
connection.closed=Connection closed: {0}
~~~

messages/LogMessages_vi.properties:

~~~properties
app.started=Ứng dụng đã khởi động.
user.login=Người dùng {0} đã đăng nhập.
requests.processed=Đã xử lý {0} yêu cầu.
~~~

Chương trình LocalizedLoggingExample.java:

~~~java
import java.text.NumberFormat;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LocalizedLoggingExample {
    private static final class MessageOnlyFormatter
            extends java.util.logging.Formatter {
        @Override
        public String format(LogRecord record) {
            return formatMessage(record);
        }
    }

    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle =
            ResourceBundle.getBundle("messages.LogMessages", locale);

        Logger logger = Logger.getLogger("example.localized");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler handler = new Handler() {
            {
                setLevel(Level.ALL);
                setFormatter(new MessageOnlyFormatter());
            }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        logger.addHandler(handler);

        System.out.println(
            "bundle locale=" + bundle.getLocale().toLanguageTag()
        );

        logger.logrb(Level.INFO, LocalizedLoggingExample.class.getName(),
            "main", bundle, "app.started", new Object[0]);

        logger.logrb(Level.INFO, LocalizedLoggingExample.class.getName(),
            "main", bundle, "user.login", new Object[] {"An"});

        String formattedCount =
            NumberFormat.getIntegerInstance(locale).format(12500);
        logger.logrb(Level.INFO, LocalizedLoggingExample.class.getName(),
            "main", bundle, "requests.processed",
            new Object[] {formattedCount});

        logger.logrb(Level.INFO, LocalizedLoggingExample.class.getName(),
            "main", bundle, "connection.closed",
            new Object[] {"api.example.test"});
    }
}
~~~

Biên dịch và chạy từ thư mục project với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all -d out LocalizedLoggingExample.java
cp -R messages out/
java -cp out LocalizedLoggingExample
~~~

Kết quả stdout chính xác:

~~~text
bundle locale=vi
Ứng dụng đã khởi động.
Người dùng An đã đăng nhập.
Đã xử lý 12.500 yêu cầu.
Connection closed: api.example.test
~~~

Giải thích:

1. Locale yêu cầu là vi-VN, nhưng chỉ có bundle LogMessages_vi.properties; vì vậy bundle.getLocale() trả về vi.
2. Logger tắt parent handlers để ví dụ chỉ in thông điệp, không thêm timestamp hoặc metadata của ConsoleHandler mặc định.
3. logrb nhận bundle tường minh và key; MessageOnlyFormatter dùng formatMessage để tra key và chèn tham số.
4. Số 12.500 được định dạng bằng NumberFormat với locale vi-VN trước khi truyền vào message. Điều này tránh phụ thuộc default locale của formatter.
5. Key connection.closed không có trong bundle tiếng Việt, nên ResourceBundle lấy giá trị từ bundle gốc. Đây là ví dụ fallback theo key; ứng dụng thực tế nên kiểm tra tính đầy đủ của bản dịch để tránh trộn ngôn ngữ ngoài ý muốn.

Ví dụ dùng logrb thay vì ghi câu đã dịch trực tiếp để LogRecord vẫn mang resource bundle và message key. Formatter quyết định câu chữ cuối cùng khi record được xuất.

## 12. Lỗi thường gặp

- **Ghi câu chữ trực tiếp ở mọi nơi:** khó dịch đồng nhất và khó thay đổi câu chữ.
- **Dùng câu đã dịch làm key:** key nên ổn định, độc lập ngôn ngữ.
- **Quên bundle gốc:** locale không có bản dịch có thể không tìm được resource phù hợp.
- **Thiếu key trong bundle cụ thể:** Java có thể lấy key từ bundle cha, dẫn tới log trộn ngôn ngữ.
- **Thay đổi placeholder khi dịch:** có thể gây lỗi định dạng hoặc hiển thị sai dữ liệu.
- **Nhầm ResourceBundle với Properties.load(InputStream):** quy tắc encoding không giống nhau; Java 9 UTF-8 default của ResourceBundle không làm mọi cách đọc Properties tự động thành UTF-8.
- **Gọi Locale.setDefault() trong request:** thay đổi trạng thái toàn JVM và ảnh hưởng thread khác.
- **Định dạng số theo locale mặc định của máy:** kết quả có thể khác locale mà người xem log yêu cầu.
- **Chỉ lưu câu đã dịch:** khó tổng hợp cùng sự kiện giữa nhiều ngôn ngữ; giữ event key và trường có cấu trúc.
- **Nạp bundle cho từng log record:** ResourceBundle có cache; không cần tự tạo lại hoặc clear cache trong hot path.
- **Dùng logrb nhưng formatter bỏ qua bundle:** record có bundle không đồng nghĩa mọi formatter tùy chỉnh tự động hiển thị đúng; formatter phải định dạng message từ LogRecord.
- **Đưa dữ liệu nhạy cảm vào placeholder:** bản dịch không làm dữ liệu log trở nên an toàn; vẫn cần chính sách redaction và kiểm soát truy cập.

## 13. Tài liệu tham khảo chính thức

- ResourceBundle — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html — bundle lookup, locale candidate, parent fallback, cache và ResourceBundleProvider.
- Logger — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html — logrb, logger resource bundle và ghi log với tham số.
- Formatter — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Formatter.html — formatMessage và cách formatter giải quyết bundle key.
- MessageFormat — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/MessageFormat.html — placeholder, number/date formatting và cú pháp pattern.
- JEP 226: UTF-8 Property Resource Bundles: https://openjdk.org/jeps/226 — thay đổi encoding mặc định cho properties resource bundles từ Java 9.
