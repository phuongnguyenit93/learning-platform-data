# Ngôn ngữ của message trong Java Core Logging

## 1. Ngôn ngữ của log message là gì?

Trong logging, **message** là phần diễn giải bằng ngôn ngữ tự nhiên về một sự kiện mà ứng dụng muốn ghi nhận. **Ngôn ngữ của message** có thể là tiếng Anh, tiếng Việt hoặc một ngôn ngữ khác, tùy người đọc, hệ thống vận hành và chính sách của dự án.

Ví dụ cùng một sự kiện:

~~~text
English: Order ORD-42 was created successfully
Tiếng Việt: Đơn hàng ORD-42 đã được tạo thành công
~~~

Hai câu khác ngôn ngữ nhưng cùng mô tả sự kiện **order.created**. Sự kiện không thay đổi khi dịch message. Đây là điểm quan trọng nhất khi thiết kế log: **ý nghĩa kỹ thuật và các trường định danh ổn định; phần văn bản phục vụ con người có thể được bản địa hóa khi cần**.

Bài học giúp bạn:

- Chọn ngôn ngữ nhất quán cho các message dùng để chẩn đoán ứng dụng Java.
- Phân biệt **log cho kỹ sư vận hành** với **thông báo cho người dùng** và nội dung đã được bản địa hóa.
- Thiết kế **event key/code**, message template và thuộc tính có cấu trúc để log vẫn tìm kiếm được dù văn bản thay đổi.
- Hiểu **Locale**, **ResourceBundle**, **LogRecord** và **Formatter.formatMessage** trong **java.util.logging (JUL)**.
- Viết và chạy một chương trình Java 17+ phát cùng một sự kiện với message tiếng Anh và tiếng Việt.
- Xử lý tham số, Unicode, fallback, exception, context đa luồng và những sai lầm khiến log khó phân tích.

**Phạm vi:** Bài thuộc nhóm **Log message** của **Java Core Logging**. Trọng tâm là ngôn ngữ của nội dung log và cách quản lý nó; không mở rộng thành một khóa học toàn bộ i18n giao diện hoặc cấu hình một observability backend cụ thể.

## 2. Cần phân biệt các loại ngôn ngữ trong một bản ghi

Một bản ghi log có thể chứa nhiều loại dữ liệu, nhưng không phải trường nào cũng được dịch.

Ví dụ dữ liệu log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order.created",
  "language": "vi-VN",
  "message": "Đơn hàng ORD-42 đã được tạo thành công",
  "order_id": "ORD-42",
  "request_id": "req-42"
}
~~~

| Thành phần | Nên quản lý thế nào? | Vì sao? |
| --- | --- | --- |
| **event = order.created** | Tên ổn định, không dịch theo locale | Dùng tìm kiếm, thống kê, liên kết với alert |
| **level = INFO** | Giá trị do logging API/backend định nghĩa | Không thay severity theo ngôn ngữ message |
| **service, request_id, order_id** | Tên field và định danh thống nhất | Truy vấn xuyên dịch vụ, đối chiếu request |
| **message** | Ngôn ngữ được chọn theo chính sách | Giúp người đọc hiểu sự kiện |
| **language/locale** | BCP 47 như en, vi-VN khi thực sự cần | Xác định bản dịch của message |
| **timestamp** | Mốc thời gian có timezone, thống nhất định dạng | Dùng so sánh, sắp xếp và điều tra |
| **error.type** | Mã/loại lỗi ổn định | Tổng hợp lỗi dù message khác nhau |

**Đừng dùng văn bản dịch làm khóa định danh duy nhất.** Nếu một câu đổi từ “Order created” thành “Created order” hoặc được dịch sang tiếng Việt, hệ thống tìm kiếm dựa trên toàn bộ câu sẽ bị phân mảnh. Event code **order.created** cho phép tìm cùng sự kiện bằng một điều kiện cố định.

### 2.1. Message chẩn đoán khác thông báo giao diện

Ba bề mặt thường bị nhầm:

1. **Operational log:** dành cho lập trình viên, SRE, đội hỗ trợ và hệ thống cảnh báo. Cần dễ tìm kiếm, có thông tin điều tra, không lộ dữ liệu nhạy cảm.
2. **User-facing message:** trả về giao diện web/mobile hoặc tài liệu hướng dẫn cho khách hàng. Thường cần dịch theo locale của người dùng và viết theo trải nghiệm sản phẩm.
3. **Audit/security event:** bản ghi kiểm toán cần cấu trúc, độ bền, quyền truy cập và chính sách lưu giữ riêng. Việc dịch nội dung không được phá vỡ các mã sự kiện phục vụ kiểm toán.

Ví dụ khi thanh toán bị từ chối:

~~~text
Log event: payment.rejected
Log message: Payment rejected by issuer; reason=do_not_honor
User message vi-VN: Không thể hoàn tất thanh toán. Vui lòng thử phương thức khác.
~~~

Không đưa nguyên log kỹ thuật hoặc stack trace cho người dùng cuối. Ngược lại, bản dịch giao diện thân thiện thường không đủ ngữ cảnh để kỹ sư chẩn đoán lỗi trong server.

## 3. Chọn tiếng Anh, tiếng Việt hay bản địa hóa theo locale?

Không có một quy tắc bắt buộc cho mọi dự án Java. Cần chọn dựa trên **người đọc** và **cách khai thác telemetry**.

### 3.1. Một ngôn ngữ chuẩn cho log vận hành

Với nhiều hệ thống có đội phát triển quốc tế, **tiếng Anh nhất quán** là lựa chọn thường gặp vì tên API, exception, công cụ tìm kiếm và tài liệu kỹ thuật thường dùng tiếng Anh. Trong nhóm vận hành nội bộ chỉ dùng tiếng Việt, việc sử dụng tiếng Việt thống nhất cũng có thể phù hợp.

Điều quan trọng hơn lựa chọn cụ thể là:

- Có **quy ước chung** cho message mới.
- Dùng từ vựng nghiệp vụ và tên hành động nhất quán.
- Không trộn ngẫu nhiên tiếng Anh/tiếng Việt cho cùng một loại event.
- Không tự động đổi ngôn ngữ log khi từng người dùng thay đổi ngôn ngữ giao diện nếu logs dùng cho truy vấn tập trung.
- Giữ event code và tên field ổn định để dữ liệu đa dịch vụ vẫn tương thích.

Một hệ thống có nhiều instance nên tránh trường hợp mỗi máy tự xuất cùng một event bằng ngôn ngữ khác nhau chỉ do cấu hình mặc định của hệ điều hành/JVM.

### 3.2. Bản địa hóa message khi có nhu cầu thực tế

Localized logging có thể hữu ích khi log được hiển thị trực tiếp cho đội hỗ trợ theo từng thị trường, khi sản phẩm có bảng điều khiển đa ngôn ngữ hoặc khi có yêu cầu tài liệu/vận hành cụ thể.

Khi đó, nên lưu ít nhất:

- **event key/code** độc lập ngôn ngữ;
- **tham số có tên hoặc cấu trúc rõ ràng**;
- **locale của bản dịch**, nếu bản dịch được lưu như một phần sự kiện;
- **message đã render**, nếu cần để con người đọc ngay.

Có hai cách chính:

**Dịch lúc tạo log:** producer chọn locale, tra message template và ghi text cuối cùng. Dễ đọc tức thì nhưng có thể làm dữ liệu tập trung chứa nhiều ngôn ngữ.

**Dịch lúc hiển thị:** producer lưu event key và dữ liệu; giao diện xem log chọn ngôn ngữ rồi render message. Dễ đổi ngôn ngữ người đọc, nhưng yêu cầu hệ thống hiển thị có catalog bản dịch và cần kiểm soát phiên bản template.

Không nên dịch tự động ở collector như một bước duy nhất rồi xóa event code gốc: việc dịch có thể không chính xác, làm mất ý nghĩa kỹ thuật và khó truy vấn.

### 3.3. Một chính sách dễ vận hành

Một chính sách khả thi là:

- Log sản xuất dùng **một ngôn ngữ kỹ thuật chuẩn** cho phần message.
- Event code, thuộc tính, severity và lỗi kỹ thuật dùng schema ổn định.
- Thông báo cho người dùng được dịch **riêng**, theo locale của UI.
- Chỉ hỗ trợ message log đa ngôn ngữ khi có nhu cầu và kiểm thử cụ thể.
- Không sử dụng câu văn message như khóa duy nhất của dashboard hoặc cảnh báo.

Đây là gợi ý kiến trúc, không phải quy tắc cố định của Java.

## 4. Viết message rõ ràng và dễ dịch

Một message hữu ích phải giúp người vận hành biết **điều gì xảy ra**, **kết quả**, **đối tượng liên quan** và **hành động tiếp theo khi cần**.

Ví dụ kém:

~~~text
Error
Failed!!!
Something went wrong
Đã có lỗi xảy ra
Lỗi tại đây
~~~

Các câu trên thiếu đối tượng, bối cảnh hoặc nguyên nhân. Ví dụ tốt hơn:

~~~text
event=order.created orderId=ORD-42
event=payment.rejected reasonCode=do_not_honor
event=inventory.lookup_failed dependency=inventory-db errorType=TimeoutException
~~~

Nếu ứng dụng có cả message người đọc:

~~~text
English: Inventory lookup timed out after 250 ms
Tiếng Việt: Tra cứu tồn kho hết thời gian chờ sau 250 ms
~~~

**Quy tắc biên soạn:**

1. Dùng chủ thể và động từ rõ ràng, ví dụ “Order created”, “Connection timed out”, “Retry scheduled”.
2. Dùng thì/trạng thái nhất quán: **created** là hoàn thành; **creating** là đang tiến hành. Một câu dịch không được đổi ý nghĩa sự kiện.
3. Tránh message chỉ chứa cảm thán hoặc mức độ nghiêm trọng. Severity đã có trong trường level.
4. Viết template ổn định; đưa orderId, duration, reasonCode vào **tham số/field** thay vì tạo hàng nghìn câu hoàn toàn khác nhau.
5. Không cố dịch **class name, package name, exception type, HTTP status, traceId, metric name hoặc event key**. Đây là dữ liệu kỹ thuật, không phải câu văn thông thường.
6. Thống nhất thuật ngữ nghiệp vụ. Ví dụ *order* trong một hệ thống có thể là **đơn hàng**; không thay lúc thì “lệnh”, lúc thì “đặt hàng” nếu đó là cùng một khái niệm.
7. Đặt thông tin quan trọng ở field có thể truy vấn. Message giúp đọc nhanh; **schema và event ID** giúp truy vấn và automation.
8. Tránh thêm dấu câu tùy tiện gây khó grep; nếu muốn log text một dòng, kiểm soát newline và ký tự điều khiển của input.

### 4.1. Gắn level đúng ngữ nghĩa, không theo ngôn ngữ

Cùng một sự kiện được dịch sang hai ngôn ngữ vẫn phải có cùng severity, trừ khi chính hành vi nghiệp vụ khác:

~~~text
INFO  event=order.created message=Order created successfully
INFO  event=order.created message=Đơn hàng đã được tạo thành công
WARN  event=payment.rejected reasonCode=issuer_unavailable
~~~

Đừng tăng WARNING thành SEVERE vì một câu dịch nghe “nghiêm trọng” hơn. Cần căn cứ vào tác động vận hành, trạng thái phục hồi và chính sách của ứng dụng.

## 5. Java Locale và ResourceBundle

Java cung cấp cơ chế quốc tế hóa (i18n) thông qua các lớp **java.util.Locale** và **java.util.ResourceBundle**.

**Locale** mô tả bối cảnh ngôn ngữ/khu vực, ví dụ:

~~~java
Locale.ENGLISH;                // en
Locale.forLanguageTag("vi");   // vi
Locale.forLanguageTag("vi-VN"); // vi-VN
Locale.forLanguageTag("en-US"); // en-US
~~~

Đoạn trên chỉ minh họa các biểu thức Java, không phải chương trình có thể chạy độc lập. **Language tag** nên được chuẩn hóa, thường dùng BCP 47 như **en**, **vi** hoặc **vi-VN**.

**ResourceBundle** là tập hợp bản dịch/giá trị được tra cứu theo **key** và **Locale**. Ví dụ catalog logic:

| Key | en | vi |
| --- | --- | --- |
| order.created | Order {0} was created successfully | Đơn hàng {0} đã được tạo thành công |
| order.rejected | Order {0} was rejected | Đơn hàng {0} đã bị từ chối |
| inventory.timeout | Inventory lookup timed out | Tra cứu tồn kho đã hết thời gian chờ |

Ở đây **{0}** là tham số theo cú pháp **java.text.MessageFormat**. Key và ý nghĩa của sự kiện giữ nguyên; catalog cung cấp câu văn phù hợp với locale.

ResourceBundle có thể được tạo bằng:

- **Tệp properties** trong classpath, chẳng hạn messages_en.properties và messages_vi.properties.
- **Lớp Java kế thừa ListResourceBundle**, phù hợp ví dụ độc lập hoặc tình huống cần quản lý bằng code.

Khi dùng **ResourceBundle.getBundle(baseName, locale)**, Java tìm bundle theo chuỗi candidate locale và cơ chế fallback của ResourceBundle. Không có bảo đảm rằng mọi key đều có bản dịch: có thể gặp **MissingResourceException** hoặc nhận giá trị fallback tùy cách tra cứu/cấu hình.

**Lưu ý:** Locale mặc định của JVM là trạng thái ở phạm vi process. Không sử dụng **Locale.setDefault(...)** cho từng request trong một máy chủ đa luồng để dịch riêng log; các request khác có thể chịu tác động ngoài ý muốn. Nếu cần điều khiển ngôn ngữ cụ thể, hãy truyền **Locale** rõ ràng đến nơi chọn template.

## 6. Cơ chế i18n của java.util.logging (JUL)

JUL có các thành phần sau liên quan đến ngôn ngữ message:

- **Logger:** nơi phát LogRecord; Logger có thể được gắn tên ResourceBundle ở cấp logger tùy API sử dụng.
- **LogRecord:** chứa level, message/key, parameters, Throwable và có thể chứa **ResourceBundle** cùng tên bundle.
- **ResourceBundle:** ánh xạ một key như order.created sang template tiếng Anh/tiếng Việt.
- **Formatter:** chuyển LogRecord thành text. **Formatter.formatMessage(record)** thực hiện tra cứu message bằng ResourceBundle có trên record và xử lý các tham số theo quy ước của JUL.
- **Handler:** xuất kết quả Formatter ra console, file hoặc đích khác.

Đường xử lý khái quát:

~~~text
Code phát event "order.created"
           |
           v
       LogRecord
  level=INFO
  message="order.created"
  parameters=["ORD-42"]
  resourceBundle=messages_vi
           |
           v
  Formatter.formatMessage(record)
  -> tìm "order.created" trong bundle
  -> lấy "Đơn hàng {0} đã được tạo thành công"
  -> thay tham số {0} bằng "ORD-42"
           |
           v
  "Đơn hàng ORD-42 đã được tạo thành công"
           |
           v
  Handler / console / file
~~~

**Phân biệt message key và message đã format:** Trong ví dụ, **record.getMessage()** vẫn là **order.created**; **formatMessage(record)** tạo ra câu văn đã dịch. Nếu chỉ ghi câu đã dịch mà không giữ key trong một field khác, việc truy vấn chung theo event sẽ khó hơn.

### 6.1. Gắn bundle cho Logger hoặc LogRecord

JUL có cách khai báo logger với tên bundle, chẳng hạn:

~~~java
Logger logger = Logger.getLogger("demo.orders", "messages");
~~~

Đoạn trên **cần catalog messages khả dụng trên classpath**; bản thân một dòng này không phải chương trình hoàn chỉnh. Khi dùng cách này, ứng dụng phải hiểu cách JUL tìm bundle và locale trong môi trường runtime. Một Logger dùng chung cho mọi request không nên được xử lý như một đối tượng “thay ngôn ngữ per request” bằng cách cấu hình lại toàn cục liên tục.

Để minh họa việc chọn **locale riêng cho từng event** và tránh ảnh hưởng đến Locale mặc định, chương trình ở mục sau tạo **LogRecord** rồi gắn ResourceBundle tương ứng. Cách này đặc biệt dễ kiểm chứng trong ví dụ Java Core; không có nghĩa mọi ứng dụng production phải tự khởi tạo LogRecord thủ công.

## 7. Ví dụ chạy độc lập Java 17+: cùng event, hai ngôn ngữ

Chương trình sau:

1. Dùng **một event key** ổn định: order.created.
2. Tạo hai **ListResourceBundle** cho **en** và **vi** trong cùng một tệp Java để có thể chạy ngay.
3. Tạo hai LogRecord INFO, mỗi record chứa **ResourceBundle** và tham số orderId.
4. Dùng **Formatter.formatMessage(record)** để lấy câu dịch.
5. In ra **event key, ngôn ngữ và message** nhằm thấy rõ phần ổn định và phần được bản địa hóa.

Tạo tệp **LogMessageLanguageDemo.java**, lưu mã nguồn bằng **UTF-8**:

~~~java
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogMessageLanguageDemo {
    private static final Logger LOG = Logger.getLogger("demo.language");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                String language = record.getResourceBundle().getLocale().getLanguage();
                return "event=" + record.getMessage()
                        + " lang=" + language
                        + " message=" + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            emit(Locale.ENGLISH, "ORD-42");
            emit(Locale.forLanguageTag("vi"), "ORD-42");
            handler.flush();
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    private static void emit(Locale locale, String orderId) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("LogMessageLanguageDemo$Messages", locale);
        LogRecord record = new LogRecord(Level.INFO, "order.created");
        record.setResourceBundle(bundle);
        record.setResourceBundleName(bundle.getBaseBundleName());
        record.setParameters(new Object[] {orderId});
        LOG.log(record);
    }

    public static class Messages_en extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                    {"order.created", "Order {0} was created successfully"}
            };
        }
    }

    public static class Messages_vi extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                    {"order.created", "Đơn hàng {0} đã được tạo thành công"}
            };
        }
    }
}
~~~

Biên dịch với mục tiêu Java 17, chỉ định encoding để ký tự tiếng Việt trong source được đọc đúng:

~~~bash
javac --release 17 -encoding UTF-8 LogMessageLanguageDemo.java
java LogMessageLanguageDemo
~~~

**stdout đã kiểm tra bằng chạy chương trình** (hai dòng):

~~~text
event=order.created lang=en message=Order ORD-42 was created successfully
event=order.created lang=vi message=Đơn hàng ORD-42 đã được tạo thành công
~~~

### 7.1. Giải thích các điểm quan trọng

**Cùng event key.** Hai record có cùng **record.getMessage() == "order.created"** và cùng severity INFO. Mã định danh này không đổi dù người đọc muốn ngôn ngữ nào.

**Bundle được chọn tường minh.** Hàm **emit(locale, orderId)** gọi **ResourceBundle.getBundle** với locale truyền vào; chương trình không thay Locale mặc định của JVM. Đây là điểm quan trọng khi nhiều request có bối cảnh ngôn ngữ khác nhau.

**ResourceBundle gắn trên từng LogRecord.** **setResourceBundle(bundle)** cho Formatter biết nơi tra câu dịch. **setResourceBundleName(...)** cung cấp tên catalog và metadata tương ứng; việc gắn trực tiếp bundle làm ví dụ tự chứa và dễ kiểm soát.

**Formatter giữ cả key và câu dịch.** **record.getMessage()** được dùng làm event; **formatMessage(record)** lấy câu văn đã dịch và thay tham số. Nếu bỏ event key, hệ thống thu log chỉ còn chuỗi phụ thuộc ngôn ngữ và dễ bị phân mảnh.

**StreamHandler cần flush.** StreamHandler có thể buffer output, vì vậy ví dụ gọi **handler.flush()** trước khi hoàn tất, giúp hai dòng xuất ra stdout theo thứ tự dự kiến. **setUseParentHandlers(false)** tránh in thêm bản ghi bởi Handler của Logger cha, vốn có thể dùng stderr/format khác.

**Một tệp Java.** Tên base bundle có ký tự **$** vì các lớp Messages_en và Messages_vi là **nested public static classes** bên trong LogMessageLanguageDemo. Đây là mẹo để bài tập chỉ cần một tệp nguồn. Trong dự án thật, tệp properties hoặc catalog riêng thường dễ bảo trì bản dịch hơn.

### 7.2. Đầu ra được chọn theo môi trường và policy

Ví dụ in cả hai ngôn ngữ để chứng minh i18n hoạt động; production thường không cần **nhân đôi mỗi event thành hai dòng**. Hãy chọn một trong các chính sách đã thiết kế: một ngôn ngữ chuẩn, message theo locale cụ thể, hoặc lưu key/attributes rồi dịch khi hiển thị.

Custom Formatter trong ví dụ chỉ thể hiện cơ chế. Nó giả định record có bundle; một formatter production phải xử lý an toàn record không có bundle, lỗi tra key và các trường hợp đầu vào không chuẩn. Dùng encoder/formatter đáng tin cậy để bảo đảm encoding, escaping, metadata và exception đúng.

## 8. Quản lý bản dịch bằng properties trong dự án thực tế

Nếu muốn tách code và bản dịch, có thể đặt những tệp sau **trên classpath**:

**messages_en.properties**

~~~properties
order.created=Order {0} was created successfully
order.rejected=Order {0} was rejected
~~~

**messages_vi.properties**

~~~properties
order.created=Đơn hàng {0} đã được tạo thành công
order.rejected=Đơn hàng {0} đã bị từ chối
~~~

Trong code, gọi:

~~~java
ResourceBundle en = ResourceBundle.getBundle("messages", Locale.ENGLISH);
ResourceBundle vi = ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi"));
~~~

Các đoạn code trên giả định hai tệp properties đã được đóng gói đúng ở classpath. Nếu muốn hỗ trợ fallback rõ ràng khi thiếu bản dịch, thường nên có **messages.properties** làm bundle gốc với nội dung mặc định. Cần kiểm thử logic fallback và key thiếu trong chính môi trường ứng dụng.

**Lưu ý encoding:** Với **ResourceBundle dựa trên PropertyResourceBundle trên JDK 9+**, cơ chế đọc file properties mặc định hỗ trợ UTF-8 theo quy tắc của JDK (có fallback ISO-8859-1 trong những trường hợp tương ứng). Điều này **khác** với một số API đọc Properties kiểu cũ, ví dụ **Properties.load(InputStream)** vẫn giải mã theo ISO-8859-1. Không suy ra rằng mọi chương trình đọc file .properties đều xử lý tiếng Việt giống nhau. Giữ file UTF-8, kiểm thử ký tự có dấu khi build và chạy thật; khi đọc bằng **Reader**, chọn charset tường minh.

**Bản dịch không chỉ là thay từ.** Một câu tiếng Việt có thể đảo vị trí tham số so với tiếng Anh. Dùng key và placeholder đánh số để mỗi locale có thể sắp xếp câu đúng ngữ pháp.

Ví dụ:

~~~text
en: Customer {0} requested product {1}
vi: Khách hàng {0} yêu cầu sản phẩm {1}
~~~

Nếu ngôn ngữ khác cần đảo chủ thể/tân ngữ, template có thể dùng **{1}** trước **{0}** mà không cần đổi thứ tự dữ liệu trong code. Key và danh sách tham số phải có hợp đồng rõ để người dịch không nhầm giá trị.

## 9. Placeholder và việc định dạng theo ngôn ngữ

### 9.1. JUL sử dụng MessageFormat cho tham số trong message

Trong ví dụ, template dùng **{0}**:

~~~text
order.created = Order {0} was created successfully
~~~

Formatter của JUL có **formatMessage(LogRecord)**: nó tra bundle của record và áp dụng định dạng tham số phù hợp cho message. Các giá trị parameter được truyền qua **LogRecord.setParameters(...)** hoặc các overload logging tương ứng.

Cần chú ý:

- **{0}**, **{1}** là placeholder của **java.text.MessageFormat**.
- **{0,number}**, **{0,date}** là dạng formatting có quy tắc và chịu ảnh hưởng của locale tại lúc format.
- Dấu **apostrophe (')** có ý nghĩa quote trong pattern MessageFormat; khi cần apostrophe như ký tự thật, thường phải dùng **hai dấu liên tiếp ('')**.
- Dấu ngoặc nhọn trong literal cần được escape/quote đúng theo MessageFormat.
- Không dùng dữ liệu không tin cậy làm **pattern** trực tiếp; giữ pattern do ứng dụng/catalog quản lý.
- Có thể kiểm thử template với tham số kiểu String, Number, Date, null và dữ liệu Unicode để tránh bất ngờ.

**Một tinh tế quan trọng:** **Locale của ResourceBundle dùng để chọn bản dịch không đồng nghĩa mọi định dạng số/ngày sẽ tự động dùng locale đó**. Với cơ chế chuẩn của JUL, Formatter.formatMessage sử dụng MessageFormat theo cách triển khai JDK; việc định dạng số/ngày có thể dựa vào **default FORMAT locale**, thay vì locale của bundle bạn đã truyền. Nếu message phải thể hiện tiền tệ, ngày giờ hoặc số theo một locale xác định, hãy chủ động dùng **MessageFormat(pattern, locale)** hoặc formatter có contract rõ ràng, đồng thời kiểm thử kết quả.

Trong log phục vụ phân tích máy, thường tốt hơn khi ghi thời gian, số lượng, duration và currency vào **field có kiểu/đơn vị rõ ràng**, tránh phụ thuộc dấu chấm/phẩy của một ngôn ngữ.

### 9.2. Không nhầm cú pháp của JUL với SLF4J

Cú pháp parameterization không đồng nhất giữa framework:

| Cơ chế | Ví dụ template | Ghi nhớ |
| --- | --- | --- |
| **JUL + MessageFormat** | Order {0} created | Chỉ số tham số bắt đầu từ 0 |
| **SLF4J** | Order {} created | Placeholder theo thứ tự tham số, không tự dịch message |
| **String.format** | Order %s created | Cú pháp printf; locale có thể ảnh hưởng định dạng |
| **MessageFormat(pattern, locale)** | Total: {0,number} | Locale được truyền rõ cho formatter |

Đoạn mã minh họa sử dụng **SLF4J** (cần thư viện SLF4J và provider tương thích, không thể chạy chỉ với JDK):

~~~java
logger.info("Order {} created", orderId);
~~~

Đây là **parameterized logging**, không tự động là **localized logging**. Nếu muốn bản dịch trong hệ SLF4J/Logback/Log4j 2, hãy xác định ở đâu tra bản dịch và sử dụng đúng formatter/encoder của hệ đó. Không chuyển nguyên pattern **{0}** của MessageFormat sang API **{}** rồi kỳ vọng kết quả giống hệt.

## 10. Message có cấu trúc giúp độc lập ngôn ngữ

Khi message thay đổi theo locale, cách tốt nhất để tránh phụ thuộc vào câu văn là dùng **structured logging** hoặc ít nhất có event code và thuộc tính ổn định.

Ví dụ hai record:

~~~json
{
  "level": "INFO",
  "event": "order.created",
  "language": "en",
  "message": "Order ORD-42 was created successfully",
  "order_id": "ORD-42"
}
~~~

~~~json
{
  "level": "INFO",
  "event": "order.created",
  "language": "vi",
  "message": "Đơn hàng ORD-42 đã được tạo thành công",
  "order_id": "ORD-42"
}
~~~

Hai record có thể được nhóm bằng **event = order.created**. Nếu hệ thống chỉ có trường message mà không có event code, truy vấn phải tìm hai câu hoặc viết rule dễ vỡ dựa vào text.

Trong production, event code thường đủ để tra cứu và thống kê. Một message tiếng Anh/Việt cụ thể có thể được tạo khi người vận hành mở log chi tiết.

**Gợi ý schema:**

- **event**: mã ổn định như order.created, order.rejected, inventory.timeout.
- **message**: câu văn cho người đọc, có thể được dịch.
- **message_key**: nếu cần một key dịch riêng với event code.
- **language** hoặc **locale**: chỉ khi ứng dụng thực sự có message đa ngôn ngữ và cần phân biệt bản dịch.
- **service, environment, version**: vị trí sự kiện phát sinh.
- **request_id, trace_id, span_id**: thuộc tính liên kết nếu có instrumentation tương ứng.
- **error.type, reason_code**: giá trị được chuẩn hóa phục vụ tìm kiếm.

Đặt tên field nhất quán theo schema của hệ thống. Không tự phát sinh tên field bằng cách dịch sang tiếng Việt hoặc sử dụng tên enum khác nhau giữa các ngôn ngữ.

### 10.1. Vì sao không nên parse message để lấy dữ liệu?

Giả sử hệ thống dùng regex để bóc orderId từ:

~~~text
Order ORD-42 was created successfully
~~~

Khi dịch thành:

~~~text
Đơn hàng ORD-42 đã được tạo thành công
~~~

Regex có thể không khớp. Nếu message thay đổi dấu câu hoặc trật tự từ, regex lại hỏng. **order_id = ORD-42** là thuộc tính ổn định, không phụ thuộc bản dịch. Đây cũng là lý do nên đính kèm mã sự kiện khi cảnh báo và dựng dashboard.

## 11. Unicode, dấu tiếng Việt và encoding đầu cuối

Message đa ngôn ngữ chỉ hữu ích nếu ký tự Unicode được bảo toàn từ nơi phát tới nơi đọc. Các lỗi phổ biến gồm chữ tiếng Việt biến thành **????**, ký tự dạng **Ã** do giải mã sai, ký tự bị mất khi ghi file, hoặc log nhiều dòng bị chia không đúng.

Đường đi cần kiểm tra:

~~~text
Java source / ResourceBundle (Unicode)
       |
       v
Java String / LogRecord
       |
       v
Formatter / Encoder
       |
       v
Console / file (charset)
       |
       v
Log agent / collector / transport
       |
       v
Storage / search UI
~~~

Một vài lưu ý:

1. **Java String là Unicode** ở mức mô hình dữ liệu; điều này không bảo đảm console, file hoặc hệ thu log đang mã hóa/giải mã đúng.
2. Dùng **UTF-8** nhất quán cho source/catalog và cấu hình encoder/sink khi có lựa chọn charset.
3. Khi compile nguồn Java chứa tiếng Việt trên nhiều hệ điều hành, chỉ định **javac -encoding UTF-8**, như ví dụ thực hành.
4. Không kết luận text hỏng ở ứng dụng chỉ vì console hiển thị sai; có thể vấn đề nằm ở terminal, font, charset đầu ra hoặc collector. Kiểm tra từng lớp.
5. Khi search, một ký tự có dấu có thể được biểu diễn theo nhiều chuỗi Unicode tương đương (ví dụ dạng tổ hợp). Cân nhắc **Unicode normalization** trong pipeline tìm kiếm nếu hệ thống có yêu cầu đó; đừng tự động thay nội dung nghiệp vụ hoặc ID không được phép.
6. Một bản ghi text phải xử lý newline/ký tự điều khiển từ input để tránh **log injection**. JSON encoder cần escape hợp lệ, không ghép chuỗi thủ công rồi gọi đó là JSON.
7. **Không chuẩn hóa/chuyển mã bí mật hoặc thông tin cá nhân vào log chỉ để dễ debug.** Kiểm soát dữ liệu được phép trước khi tạo message.

## 12. Locale trong ứng dụng đa luồng và đa dịch vụ

Trong ứng dụng server, mỗi request có thể mang locale khác nhau. Nếu đổi **Locale.setDefault(...)** theo từng request, đó là thay đổi trạng thái toàn JVM và có thể ảnh hưởng đồng thời đến formatting ở các request khác.

Lựa chọn an toàn hơn là:

1. Quyết định **chính sách ngôn ngữ của log** ở cấp ứng dụng/dịch vụ, thường là một ngôn ngữ thống nhất.
2. Nếu event cần bản dịch riêng, truyền **Locale** tới hàm chọn ResourceBundle hoặc render message thay vì thay Locale mặc định.
3. Khi làm việc với **ExecutorService, CompletableFuture, virtual threads** hoặc pipeline async, truyền context cần thiết tường minh hoặc dùng cơ chế context propagation có hợp đồng rõ.
4. Tránh giữ Locale của người dùng trong ThreadLocal mà không dọn; thread pool có thể tái sử dụng luồng và vô tình mang locale của request trước.
5. Giữ **event key và structured attributes** xuyên dịch vụ. Service A sử dụng tiếng Việt và service B dùng tiếng Anh vẫn phải có event code/traceId liên kết đúng nếu hệ thống có truy vết.

**Không nên sử dụng Accept-Language hoặc user locale để quyết định ngôn ngữ toàn bộ log backend** nếu đội vận hành kỳ vọng một ngôn ngữ duy nhất. Accept-Language có ích cho nội dung trả về người dùng; log phục vụ điều tra có thể có chính sách khác.

### 12.1. Truyền locale không đồng nghĩa truyền trace context

Locale giúp chọn bản dịch. **requestId, traceId, spanId** giúp liên kết sự kiện. Hai loại context có mục đích khác nhau; không dùng locale làm ID hay tạo correlation ID từ câu văn đã dịch.

Khi gửi một tác vụ sang thread khác, hệ thống cần xác định rõ:
- Có thật sự cần locale của người dùng ở tác vụ này không?
- Event code và request/trace context có được truyền đúng không?
- Message được render lúc tạo event hay lúc xử lý bởi async appender?
- Nếu locale thay đổi sau khi record được tạo, backend có còn render nhất quán không?

Việc xác định **thời điểm chọn bản dịch** giúp tránh trường hợp log từ cùng request xuất nhiều ngôn ngữ bất ngờ.

## 13. Exception message, stack trace và ngôn ngữ

Một exception Java có **getMessage()** và **getLocalizedMessage()**. Nhưng đừng giả định mọi exception đều có bản dịch: mặc định, nhiều exception trả cùng một nội dung cho cả hai phương thức; các thư viện có thể chọn cách riêng.

Khi ghi lỗi, hãy ưu tiên:
- **Loại lỗi ổn định** (class name/error code).
- **Ngữ cảnh có ích** (operation, dependency, requestId).
- **Throwable/stack trace** khi cần để điều tra và khi chính sách dữ liệu cho phép.
- **Message đã chuẩn hóa** cho người vận hành.
- **User-facing message** được dịch riêng, không dùng nguyên exception kỹ thuật làm câu hiển thị.

Ví dụ minh họa log dùng JUL:

~~~java
// Minh họa trong một phương thức đã có biến logger và exception error.
logger.log(Level.WARNING, "event=inventory.lookup_failed", error);
~~~

Overload trên giữ Throwable trong LogRecord để Handler/Formatter có thể biểu diễn stack trace theo cấu hình. Đây không phải chương trình độc lập; cần biến **logger**, **error** và import JUL trong bối cảnh phù hợp.

**Không dịch tên class/method trong stack trace.** Những định danh đó phải phản ánh code thật để tra nguồn, xác định phiên bản và điều tra.

**Cảnh giác dữ liệu nhạy cảm:** exception message của thư viện có thể chứa URL, query, token, payload hoặc dữ liệu người dùng. Dịch một câu không làm nó tự động an toàn để ghi log.

## 14. Fallback, phiên bản bản dịch và tính nhất quán

Một hệ thống i18n cần kế hoạch cho những trường hợp thiếu bản dịch:

- **Thiếu locale:** lựa chọn bundle gốc/ngôn ngữ chuẩn theo chính sách.
- **Thiếu key:** không nên để toàn bộ luồng xử lý nghiệp vụ thất bại chỉ vì một câu log; cần test catalog và xử lý lỗi phù hợp ở tầng logging.
- **Thiếu parameter:** tránh template chỉ hiển thị “{1}” hoặc đưa thông tin sai vị trí.
- **Sửa wording:** câu có thể đổi nhưng event code và schema nên giữ ổn định nếu ngữ nghĩa không đổi.
- **Đổi ý nghĩa:** nếu “order.created” trước đây là đơn tạm, nay là đơn đã thanh toán, đó là thay đổi semantic contract; cân nhắc một event key mới thay vì chỉ đổi bản dịch.
- **Triển khai nhiều phiên bản:** service cũ/mới có thể có wording khác nhau. Truy vấn theo event code, service version và thuộc tính ổn định.

**Fallback của ResourceBundle** có logic riêng: theo candidate locale, root bundle và trong một số đường tìm kiếm có thể sử dụng default locale JVM. Đừng giả định rằng một locale không có bản dịch sẽ luôn quay về tiếng Anh nếu chưa cấu hình catalog và chưa kiểm thử. Catalog gốc như **messages.properties** và các bài test từng language tag giúp phát hiện sớm trường hợp này.

Tổ chức nên có quy trình kiểm tra rằng:
- Mỗi key quan trọng có các bản dịch cần thiết.
- Số lượng placeholder và kiểu tham số nhất quán.
- Bản dịch không vô tình thay đổi ý nghĩa lỗi/sự kiện.
- Wording mới không ảnh hưởng tới dashboard, alert hoặc parser.
- Các tệp translation được đóng gói đúng và hiển thị Unicode chính xác.

## 15. Quan hệ giữa message language và SLF4J/Logback/Log4j 2

Trong hệ sinh thái Java, logging API và backend có thể khác JUL:

**SLF4J** là facade: lời gọi **logger.info("Order {} created", id)** được parameterize. Nó không mặc định tra ResourceBundle hay tự dịch nội dung theo locale. Muốn i18n, ứng dụng/cấu hình phải thiết kế một bước chọn message template, rồi dùng đúng API để log hoặc giữ event/attributes.

**Logback/Log4j 2** có encoder/layout/filter/appender hoặc cơ chế tương tự; chúng có thể xuất JSON/structured fields. Nếu dùng backend như vậy, nên tận dụng structured logging thay vì bắt buộc mỗi bản dịch vào một message text rồi parse ngược.

Một luồng có thể là:

~~~text
Business code: eventKey + structured attributes
                    |
                    v
      Logging facade/provider/backend
                    |
         +----------+------------+
         |                       |
         v                       v
  Canonical event fields   Human-readable message
         |                (theo policy/locale)
         +-----------+-----------+
                     |
                     v
               Encoder / sink
                     |
                     v
              Log storage/search
~~~

**Không lẫn lộn hai khái niệm:** *parameterization* là đưa giá trị vào template để tạo câu văn; *localization* là chọn template phù hợp ngôn ngữ. Một hệ thống có thể parameterize nhưng hoàn toàn không localized. Một hệ thống cũng có thể localized mà vẫn giữ event code gốc.

Khi đổi backend, đừng giả định phương thức formatMessage của JUL hay cú pháp {0} sẽ tự hoạt động tương tự với SLF4J. Hãy kiểm tra API, dependency/provider và hợp đồng formatter thực tế.

## 16. Kiểm thử chất lượng message và bản dịch

Các bài kiểm tra có giá trị gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Cùng eventKey với locale en và vi | Event key, level và ID giống nhau; message được dịch đúng |
| Message có tham số | Giá trị nằm đúng placeholder, không bị mất hoặc đảo sai |
| Thiếu một locale | Fallback theo chính sách, có kiểm thử |
| Thiếu message key | Xử lý được, phát hiện thiếu translation trong QA |
| Có dấu tiếng Việt | UTF-8 được giữ nguyên qua formatter và sink |
| Có dấu nháy, dấu ngoặc nhọn | MessageFormat được escape đúng |
| Có newline hoặc ký tự điều khiển từ input | Không làm hỏng cấu trúc log hay tạo bản ghi giả |
| Nhiều request khác locale chạy đồng thời | Không rò locale giữa các request |
| Thay wording tiếng Anh hoặc tiếng Việt | Dashboard vẫn query theo event code và field |
| Exception có nội dung nhạy cảm | Log bị loại/redact dữ liệu theo policy |

**Kiểm thử end-to-end** nếu dùng collection tập trung: đừng chỉ kiểm tra Java String trong unit test. Cần xác nhận message tiếng Việt qua console/file, agent, transport và giao diện tìm kiếm không bị sai mã hóa; các điều kiện truy vấn dựa trên event code vẫn tìm được đầy đủ event.

**Lưu ý stdout:** Chương trình Java ở mục 7 dùng Handler gửi tới stdout và flush; điều này tạo output xác định cho bài thực hành. Một ConsoleHandler JUL mặc định thường ghi ra stderr và có format khác. Khi chuyển ví dụ sang ConsoleHandler, hãy kỳ vọng output khác do cấu hình chứ không mặc định là lỗi dịch.

## 17. Những sai lầm thường gặp

### Sai lầm 1 — Dịch cả event code

**Sai:** Ở locale vi, đổi event từ order.created thành donhang.datao.  
**Hệ quả:** Dashboard, alert và truy vấn cross-service không còn chung một khóa.  
**Đúng:** Giữ **order.created** cố định; dịch trường **message**.

### Sai lầm 2 — Dùng câu log như một khóa phân loại

**Sai:** Rule “contains Order was created” để thống kê thành công.  
**Hệ quả:** Khi dịch hoặc đổi câu văn, kết quả thống kê sai.  
**Đúng:** Dùng **event**, **status** và structured attributes.

### Sai lầm 3 — Tưởng SLF4J {} tự dịch

**Sai:** Thay “Order {} created” bằng một key rồi kỳ vọng provider tự tìm tiếng Việt.  
**Đúng:** SLF4J parameterization và ResourceBundle localization là hai việc khác nhau; cần cấu hình hoặc code tra template tường minh.

### Sai lầm 4 — Thay Locale mặc định theo request

**Sai:** Mỗi HTTP request gọi Locale.setDefault(userLocale).  
**Hệ quả:** Yêu cầu đồng thời có thể ảnh hưởng lẫn nhau.  
**Đúng:** Truyền Locale tới logic dịch hoặc dùng catalog được chọn theo scope có kiểm soát.

### Sai lầm 5 — Tin rằng ResourceBundle locale tự kiểm soát số/ngày

**Sai:** Thấy bundle vi rồi kết luận các placeholder ngày/số chắc chắn có định dạng vi-VN.  
**Đúng:** Xác định formatter và Locale dùng để format các kiểu dữ liệu đó; truyền locale tường minh nếu cần.

### Sai lầm 6 — Quên UTF-8 ở một mắt xích

**Sai:** Source tiếng Việt đúng nhưng output sau collector thành ký tự rác; cho rằng ResourceBundle thiếu key.  
**Đúng:** Kiểm tra encoding của source, resource file, build, handler, terminal, transport và storage.

### Sai lầm 7 — Dùng message người dùng thay cho log kỹ thuật

**Sai:** Server chỉ ghi “Không thể thanh toán” và không có error code, requestId hoặc dependency.  
**Đúng:** User message thân thiện được dịch riêng; log kỹ thuật giữ sự kiện, kết quả và ngữ cảnh có ích.

### Sai lầm 8 — Dịch exception/class name và che mất nguyên nhân

**Sai:** Chỉ lưu câu văn đã dịch rồi bỏ thông tin exception type và cause.  
**Đúng:** Giữ mã lỗi, loại exception, bối cảnh và stack trace khi cần và khi chính sách cho phép.

### Sai lầm 9 — Mặc định phát nhiều bản dịch cho mỗi event

**Sai:** Mỗi request ghi đồng thời bản tiếng Anh và tiếng Việt vào log production.  
**Hệ quả:** Volume tăng, dễ đếm trùng, thứ tự và correlation khó hiểu.  
**Đúng:** Chọn chính sách rõ ràng, có thể lưu key và render bản dịch khi xem.

### Sai lầm 10 — Đưa nội dung không tin cậy vào template

**Sai:** Dùng raw input làm MessageFormat pattern hoặc ghép newline từ user vào text log.  
**Đúng:** Template do ứng dụng quản lý; dữ liệu biến thiên chỉ là tham số/field đã kiểm soát và escape.

## 18. Bài thực hành và câu hỏi tự đánh giá

**Bài thực hành A — Thêm ngôn ngữ thứ ba.** Trong chương trình Java, thêm catalog **Messages_fr** hoặc một bundle khác và gọi **emit(Locale.forLanguageTag("fr"), "ORD-42")**. Kiểm tra event key **order.created** vẫn giống hai dòng trước. Bài này cần bạn tự cung cấp bản dịch phù hợp, không suy diễn dịch thuật từ event code.

**Bài thực hành B — Kiểm tra missing key.** Thêm event **order.rejected** nhưng chưa có bản dịch trong một bundle. Quan sát cách ResourceBundle/JUL xử lý rồi thiết kế một kiểm tra catalog để phát hiện thiếu key ở bước build/test.

**Bài thực hành C — Chọn policy.** Một hệ thống gồm ba service, một ở Việt Nam, một ở Singapore, một ở Mỹ cùng ghi log. Đề xuất ngôn ngữ vận hành, chuẩn event code, field names, locale handling và cách bản địa hóa user-facing messages mà vẫn truy vấn theo một event duy nhất.

**Bài thực hành D — Tham số số/ngày.** Tạo template chứa {0,number} và thử format theo en-US/vi-VN bằng MessageFormat với Locale tường minh. So sánh với formatMessage(record) mặc định trong JUL để hiểu phạm vi của bundle locale.

**Bài thực hành E — Tạo structured event.** Từ câu tiếng Việt “Đơn hàng ORD-42 đã được tạo thành công”, tách thành các field **event**, **order_id**, **level**, **message** và **language**. Chứng minh một truy vấn theo event vẫn đúng khi đổi ngôn ngữ.

### Câu hỏi kiểm tra

**1. Có nên dịch event code order.created thành mã tiếng Việt không?**  
Không. Event code là hợp đồng kỹ thuật ổn định; dịch message và giữ code.

**2. Vì sao message tiếng Anh có thể xuất dù request gửi locale vi-VN?**  
Vì log có thể dùng ngôn ngữ chuẩn, ResourceBundle có fallback, app chưa truyền locale hoặc Formatter/backend không thực hiện bản địa hóa như mong đợi. Cần kiểm tra code và cấu hình thực tế.

**3. JUL hỗ trợ dịch message bằng những thành phần nào?**  
ResourceBundle chứa template; LogRecord giữ message key/parameters/bundle; Formatter.formatMessage có thể tra bản dịch và định dạng tham số.

**4. Một câu dịch đổi thứ tự {0} và {1} có bắt buộc đổi code phát log không?**  
Không, nếu contract tham số giữ nguyên và template đặt placeholder đúng vị trí.

**5. Tại sao thay Locale.setDefault theo từng request là nguy hiểm?**  
Đây là trạng thái chung cho JVM, có thể ảnh hưởng request khác và các thao tác format chạy đồng thời.

**6. Vì sao không thể chỉ dựa vào message text để cảnh báo?**  
Nội dung có thể thay đổi khi bản dịch, wording hoặc định dạng thay đổi. Dùng event ID, level và field ổn định.

**7. Message tiếng Việt bị lỗi dấu thì nên kiểm tra đâu?**  
Xét lần lượt file nguồn/catalog, charset lúc compile/read, formatter/handler, terminal, collector, storage và UI tìm kiếm.

## 19. Kết luận

**Ngôn ngữ của log message là một quyết định về người đọc và vận hành**, không phải thuộc tính làm thay đổi bản chất của sự kiện. Java hỗ trợ bản địa hóa thông qua **Locale**, **ResourceBundle** và cơ chế định dạng của JUL, nhưng việc dịch cần được thiết kế cùng **event key**, **schema**, **tham số**, **encoding** và **chính sách locale**.

Bài tập Java 17 cho thấy cùng **order.created** có thể xuất câu tiếng Anh hoặc tiếng Việt, trong khi mã sự kiện và định danh đơn hàng không đổi. Một kiến trúc log dễ bảo trì thường giữ dữ liệu kỹ thuật ổn định, chọn ngôn ngữ message có chủ đích và luôn kiểm thử trường hợp thiếu bản dịch, Unicode và dữ liệu đến được đích quan sát.
