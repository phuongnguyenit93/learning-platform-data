# Logger là gì? — Java Core Logging

## 1. Khái niệm Logger

Trong Java, **Logger** là đối tượng mà mã nguồn dùng để **phát các bản ghi sự kiện (log event)** khi chương trình chạy. Thay vì in thông điệp tùy ý bằng System.out.println(...), lập trình viên gọi các phương thức của logger với **mức độ (level)** và thông tin mô tả để hệ thống logging có thể quyết định sự kiện nào cần ghi, trình bày ra sao và gửi đến đâu.

Ví dụ về ý định ghi log:

~~~text
INFO    Ứng dụng đã khởi động
WARNING Thiếu cấu hình tùy chọn; dùng giá trị mặc định
SEVERE  Không thể kết nối đến dịch vụ thanh toán
~~~

Đây là **thông điệp minh họa**, không phải output mặc định của Java: thông tin thời gian, tên lớp, thread, bố cục và đích xuất phụ thuộc vào cấu hình.

Một cách hiểu hữu ích:

- **Logging**: hoạt động ghi nhận các sự kiện trong suốt vòng đời ứng dụng.
- **Logger**: điểm truy cập (đối tượng/API) mà mã ứng dụng gọi để tạo sự kiện log.
- **Handler/Appender**: thành phần nhận sự kiện để xuất ra console, tệp hoặc hệ thống thu thập.
- **Formatter/Encoder**: thành phần quyết định cách biểu diễn thông tin sự kiện, chẳng hạn văn bản có thời gian hoặc JSON.

Logger **không phải nơi lưu trữ log**. Một lệnh gọi logger chỉ có thể dẫn đến dòng log thực tế khi sự kiện đi qua bộ lọc và có thành phần xuất phù hợp. Vì vậy, gọi LOGGER.info(...) chưa đủ để khẳng định log đã được ghi bền vững vào tệp hoặc dịch vụ bên ngoài.

## 2. Vì sao ứng dụng cần Logger?

Logger giúp tách **ý định quan sát của mã nguồn** khỏi **cách vận hành và lưu trữ log**:

1. **Phân mức sự kiện**: INFO cho cột mốc vận hành, WARNING cho tình huống bất thường, SEVERE cho lỗi nghiêm trọng; giảm tiếng ồn bằng cách không xuất chi tiết debug trong vận hành thông thường.
2. **Xác định nơi phát sinh**: logger thường mang tên lớp hoặc thành phần, giúp tìm nguồn sự kiện trong một codebase lớn.
3. **Thay đổi cấu hình mà không sửa lời gọi**: quản trị viên có thể điều chỉnh level, handler, formatter hoặc đích ghi tùy thư viện/framework.
4. **Giữ thông tin ngoại lệ**: logger có thể nhận một Throwable để hệ thống logging hiển thị stack trace và nguyên nhân lỗi.
5. **Hỗ trợ vận hành đa luồng, nhiều dịch vụ**: ngữ cảnh như request ID hoặc trace ID giúp đối chiếu các sự kiện liên quan.
6. **Hạn chế công việc không cần thiết**: API logging hỗ trợ kiểm tra level và tạo thông điệp lười (*lazy message evaluation*) trong một số trường hợp.

Dùng System.out.println(...) để thử nhanh trong một bài tập nhỏ không sai; tuy nhiên, khi cần phân mức, lọc, thu thập tập trung và thay đổi cấu hình, Logger phù hợp hơn.

## 3. Logger trong thư viện chuẩn Java

JDK tích hợp hệ thống **java.util.logging** (thường gọi **JUL**). Các lớp cốt lõi gồm:

| Thành phần | Vai trò |
| --- | --- |
| java.util.logging.Logger | Đối tượng ứng dụng gọi để phát log |
| java.util.logging.Level | Biểu diễn mức nghiêm trọng/độ chi tiết |
| java.util.logging.LogRecord | Chứa thông tin một sự kiện log như level, message, thời điểm, logger name, exception và tham số |
| java.util.logging.Handler | Nhận LogRecord rồi xuất đến một đích |
| java.util.logging.Formatter | Chuyển LogRecord thành chuỗi biểu diễn |
| java.util.logging.Filter | Quy tắc lọc bổ sung khi được cấu hình |
| java.util.logging.LogManager | Quản lý logger và cấu hình của JUL |

Trong mã ứng dụng, thường lấy một logger bằng tên lớp:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());
}
~~~

Đây là **đoạn minh họa đặt bên trong một lớp**, không có phương thức main nên không tự tạo output. Một logger gắn với tên lớp giúp dễ cấu hình theo package, ví dụ com.example.order, và dễ xác định nguồn khi đọc log.

### Vì sao dùng private static final?

- **private**: mỗi lớp giữ một điểm truy cập logging của chính mình.
- **static**: không cần tạo một logger mới cho từng đối tượng OrderService.
- **final**: tránh gán lại biến tham chiếu LOGGER ngoài ý muốn.
- **getLogger(OrderService.class.getName())**: đặt tên theo tên đầy đủ của lớp; đây là **quy ước hữu ích**, không phải điều kiện bắt buộc.

Một logger có thể được lấy bằng một tên chức năng như "com.example.payment" nếu dự án chủ động tổ chức như vậy. Tên logger không nhất thiết trùng với tên lớp, nhưng nên có quy ước nhất quán.

## 4. Logger tiếp nhận và xử lý một sự kiện như thế nào?

Sơ đồ khái quát với JUL:

~~~text
Mã Java: LOGGER.info("...")
            |
            v
         Logger
   (kiểm tra level/filter)
            |
     nếu được chấp nhận
            v
          LogRecord
            |
            v
      Handler/Filter
    (lọc, chọn đích xuất)
            |
            v
         Formatter
            |
            v
    Console / File / ...
~~~

Trong JUL, các handler của logger cha cũng có thể nhận bản ghi khi việc **chuyển tiếp lên cha** đang bật. Vì thế một sự kiện có thể được nhiều handler xuất ra nhiều đích, hoặc có thể bị xuất trùng nếu cấu hình không đúng.

Ví dụ về hai tầng lọc:

- Logger đặt **INFO**, handler đặt **FINE**: thông điệp FINE vẫn bị logger chặn; handler không thể khôi phục sự kiện đã bị loại trước đó.
- Logger đặt **FINE**, handler đặt **INFO**: logger cho phép FINE đi tiếp nhưng handler INFO có thể loại sự kiện FINE.
- Logger và handler đều đặt **FINE**: sự kiện FINE có thể được xuất, miễn không bị filter khác chặn.

**Logger quyết định sự kiện có được phát vào hệ thống logging hay không; handler quyết định cách xử lý sự kiện nhận được.** Trong JUL, level của logger cha phục vụ kế thừa ngưỡng cho logger con khi cần; nó không nhất thiết lọc lại mỗi LogRecord do logger con đã chấp nhận và chuyển tiếp lên các handler của cha.

## 5. Các mức log (level) trong JUL

Những level thường gặp, sắp xếp từ nghiêm trọng cao đến chi tiết thấp:

| Level | Khi nào thường sử dụng |
| --- | --- |
| SEVERE | Tác vụ quan trọng thất bại, chức năng không thể tiếp tục như mong đợi |
| WARNING | Trạng thái bất thường, rủi ro hoặc cần chú ý, có thể vẫn tiếp tục |
| INFO | Sự kiện vận hành chính: khởi động, hoàn tất một công việc quan trọng |
| CONFIG | Thông tin cấu hình cần phục vụ chẩn đoán |
| FINE | Chi tiết dùng khi tìm lỗi |
| FINER | Thêm chi tiết về các bước xử lý |
| FINEST | Mức chi tiết sâu nhất để truy vết kỹ |

**OFF** và **ALL** chủ yếu dùng để cấu hình ngưỡng ngừng hoặc cho phép toàn bộ sự kiện; không nên xem chúng là mức sự kiện nghiệp vụ dùng hằng ngày.

Một logger với ngưỡng **INFO** thông thường cho qua INFO, WARNING, SEVERE và chặn CONFIG, FINE, FINER, FINEST. Level chỉ phản ánh mức độ ghi log: **phát SEVERE không tự ném ngoại lệ hay dừng chương trình**; gọi WARNING cũng không tự phục hồi lỗi.

Ở các framework khác thường thấy các tên **ERROR, WARN, INFO, DEBUG, TRACE**. Có thể liên hệ khái niệm với SEVERE, WARNING, INFO, FINE, FINER/ FINEST của JUL, nhưng **không coi các giá trị này là cùng một API hoặc được ánh xạ hoàn toàn giống nhau ở mọi thư viện**.

## 6. Ví dụ Java 17+ chạy được: tạo, cấu hình và sử dụng Logger

Ví dụ này dùng **JUL**, không cần dependency ngoài JDK. Nó chủ động định dạng log và gửi ra stdout để bạn nhìn thấy chính xác kết quả, thay vì phụ thuộc cấu hình logging có sẵn trên máy.

Tạo tệp **LoggerDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(LoggerDemo.class.getName());

    public static void main(String[] args) {
        // Tránh handler của logger cha in thêm bản ghi.
        LOGGER.setUseParentHandlers(false);

        // Logger chỉ cho phép INFO và các mức nghiêm trọng hơn.
        LOGGER.setLevel(Level.INFO);

        // Handler xuất stdout với định dạng đơn giản, xác định.
        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        LOGGER.info("Ứng dụng đã khởi động");
        LOGGER.fine("Chi tiết debug sẽ bị lọc");
        LOGGER.log(Level.WARNING,
                "Thiếu cấu hình {0}; dùng giá trị mặc định", "theme");

        // StreamHandler có thể đệm dữ liệu trước khi ghi.
        stdout.flush();
    }
}
~~~

Biên dịch và chạy trong môi trường terminal hiển thị UTF-8, với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 LoggerDemo.java
java LoggerDemo
~~~

**Stdout chính xác** của chương trình (mỗi dòng kết thúc bằng newline):

~~~text
INFO | Ứng dụng đã khởi động
WARNING | Thiếu cấu hình theme; dùng giá trị mặc định
~~~

Vì sao chỉ có hai dòng?

1. **Logger.getLogger(LoggerDemo.class.getName())** lấy logger theo tên lớp.
2. **LOGGER.setLevel(Level.INFO)** chặn lời gọi LOGGER.fine(...), nên dòng debug không xuất hiện.
3. **stdout.setLevel(Level.INFO)** đặt ngưỡng cho handler tương ứng.
4. **setUseParentHandlers(false)** tránh logger cha tiếp tục xuất bản ghi bằng handler khác. Nếu không có dòng này, cấu hình mặc định của hệ thống có thể làm thông điệp xuất thêm ở stderr.
5. **Formatter.format(...)** quyết định chuỗi đầu ra gồm level, dấu phân cách và message; không in thời gian hay tên lớp để output dễ kiểm chứng.
6. Với **JUL**, chỗ giữ tham số thường dùng **{0}**, **{1}** theo quy tắc định dạng thông điệp của JUL; ví dụ trên biến {0} thành theme.
7. **StreamHandler.flush()** yêu cầu ghi phần dữ liệu đã đệm; dùng StreamHandler với System.out trong ví dụ để thấy output, không cần đóng System.out.

**Lưu ý:** đây là chủ động cấu hình một logger cho bài tập. Ứng dụng thực tế thường chọn cấu hình logging tập trung, giúp thay đổi level và đích ghi theo môi trường thay vì tạo handler trong từng phương thức nghiệp vụ.

## 7. Logger, handler và formatter khác nhau ra sao?

Hãy xem ba phát biểu sau:

- **Logger:** “Có sự kiện WARNING: thiếu cấu hình theme”.
- **Handler:** “Gửi sự kiện này ra console hoặc một tệp”.
- **Formatter:** “Hiển thị thành WARNING | Thiếu cấu hình theme; dùng giá trị mặc định”.

Một logger có thể gắn nhiều handler và các handler có thể chọn các đích khác nhau. Chẳng hạn console chỉ nhận INFO trở lên, tệp chẩn đoán có thể nhận FINE trở lên. Khi đó cần đặt ngưỡng logger đủ thấp để không loại FINE trước khi handler xử lý.

### ConsoleHandler mặc định ghi vào đâu?

Trong JUL, **ConsoleHandler mặc định ghi ra stderr**, khác với System.out.println(...) ghi ra stdout. Vì stdout và stderr là hai luồng riêng, thứ tự hiển thị khi chúng trộn trong terminal hoặc pipeline có thể gây nhầm lẫn. Ví dụ chạy được ở trên dùng **StreamHandler(System.out, ...)** để chủ động xuất stdout.

Trong môi trường container hoặc hệ thống thu thập tập trung, stdout và stderr đều có thể được thu thập theo cấu hình hạ tầng; không suy ra rằng log sẽ tự động nằm trong một file.

### Vì sao đôi khi một câu log xuất hiện hai lần?

Một nguyên nhân điển hình là gắn handler riêng cho logger con nhưng vẫn bật chuyển tiếp đến handler của logger cha. Các cách xử lý gồm tổ chức handler ở cấp chung phù hợp, hoặc chỉ tắt chuyển tiếp khi thật sự muốn cô lập logger. Đừng thêm/tạo handler mới mỗi lần phương thức nghiệp vụ được gọi: điều đó dễ làm xuất trùng, rò tài nguyên và khiến cấu hình khó quản lý.

## 8. Khi nào nên viết LOGGER.info, warning, severe hoặc fine?

Cân nhắc **tác động của sự kiện đối với người vận hành**, thay vì chỉ dựa vào loại câu lệnh đang chạy:

~~~java
LOGGER.info("Dịch vụ đã sẵn sàng nhận yêu cầu");
LOGGER.warning("Không truy cập được cache; chuyển sang nguồn dữ liệu chính");
LOGGER.severe("Không thể khởi tạo kết nối bắt buộc");
LOGGER.fine("Đã chọn nhánh xử lý dự phòng");
~~~

Đây là các **lệnh minh họa**, không phải chương trình độc lập. Chúng sẽ chỉ xuất khi logger, handler và bộ lọc cho phép.

Một số nguyên tắc lựa chọn level:

- **INFO**: trạng thái/cột mốc giúp hiểu ứng dụng đang làm việc gì. Không biến INFO thành nhật ký từng bước nhỏ cho mỗi vòng lặp.
- **WARNING**: điều gì đó bất thường cần theo dõi nhưng hệ thống vẫn có thể xử lý hoặc phục hồi.
- **SEVERE**: lỗi có ảnh hưởng thực tế, thao tác thất bại hoặc tính năng không còn hoạt động đúng.
- **FINE/FINER/FINEST**: chi tiết phục vụ debug; có thể bật có chọn lọc trong thời gian điều tra.

Không có quy tắc rằng “cứ catch exception thì phải SEVERE”. Ví dụ dữ liệu đầu vào sai mà ứng dụng đã trả về lỗi hợp lệ có thể không phải sự cố nghiêm trọng của hạ tầng. Mức log phải phản ánh ngữ nghĩa sự kiện và quy ước của dự án.

## 9. Logger có thể ghi stack trace của ngoại lệ

Chỉ ghi thông điệp "Đã có lỗi" thường không đủ cho việc tìm nguyên nhân. JUL cho phép truyền một **Throwable** trực tiếp để handler/formatter phù hợp có thể biểu diễn stack trace.

Đoạn sau minh họa cách dùng bên trong một lớp có biến LOGGER:

~~~java
try {
    int amount = Integer.parseInt("abc");
    LOGGER.info("Đã đọc số tiền: " + amount);
} catch (NumberFormatException ex) {
    LOGGER.log(Level.WARNING, "Không thể chuyển dữ liệu sang số", ex);
}
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập với stdout xác định. Stack trace thực tế phụ thuộc vị trí dòng và formatter đang dùng. Trong ví dụ LoggerDemo ở mục 6, formatter chỉ trả về level và message, **không tự hiển thị stack trace** nếu bạn dùng lại chính formatter tối giản đó. Muốn hiển thị Throwable, hãy dùng formatter hỗ trợ hoặc bổ sung xử lý record.getThrown() phù hợp.

Khi bắt ngoại lệ, cần quyết định có xử lý được không. Tránh nhiều tầng đều log cùng một throwable rồi ném tiếp, dẫn đến nhiều dòng lỗi trùng lặp; nhưng cũng không nuốt ngoại lệ chỉ vì đã ghi log.

## 10. Tối ưu chi phí tạo thông điệp

Dù level FINE bị tắt, mã Java vẫn đánh giá đối số của phương thức trước khi gọi nó. Vì thế:

~~~java
LOGGER.fine("Chi tiết: " + createExpensiveDebugDescription());
~~~

Có thể **vẫn gọi createExpensiveDebugDescription()** ngay cả khi logger bỏ qua FINE. Đây chỉ là đoạn minh họa: phương thức đó cần được định nghĩa trong chương trình thật.

Một cách làm tốt hơn là dùng **Supplier<String>** được JUL hỗ trợ:

~~~java
LOGGER.log(Level.FINE,
        () -> "Chi tiết: " + createExpensiveDebugDescription());
~~~

Khi level không được logger chấp nhận, supplier không cần được thực thi để tạo thông điệp. Có thể kiểm tra tường minh nếu việc tạo dữ liệu debug tốn kém:

~~~java
if (LOGGER.isLoggable(Level.FINE)) {
    LOGGER.fine(createExpensiveDebugDescription());
}
~~~

Cần nhớ rằng một handler hoặc filter phía sau vẫn có thể loại log; **isLoggable(...) phản ánh ngưỡng và bộ lọc ở logger**, không cam kết sự kiện sẽ được lưu ở đích cuối.

Không đưa thao tác gây tác dụng phụ bắt buộc vào supplier log. Nếu level tắt, supplier sẽ không được thực thi và logic nghiệp vụ có thể không chạy như mong muốn.

## 11. Logger trong hệ thống nhiều luồng hoặc nhiều dịch vụ

Một logger tĩnh thường được nhiều luồng cùng sử dụng. Mã nên đưa thêm **ngữ cảnh đủ để truy tìm sự kiện** thay vì tạo một logger mới cho từng request.

Ví dụ thông điệp có cấu trúc bằng các cặp key=value:

~~~text
INFO service=order-api requestId=req-23 action=create-order result=success durationMs=41
WARNING service=order-api requestId=req-24 action=create-order result=retry cause=timeout
~~~

Đây là **thông điệp minh họa**. Trong hệ thống logging thực, ngữ cảnh có thể được đưa vào record, trường JSON, MDC của thư viện tương ứng hoặc một cơ chế context của framework. **java.util.logging.Logger không mặc nhiên có API MDC tương đương mọi framework**; cách mang request ID qua thread/async task cần tuân theo công cụ được chọn.

Ghi log nhiều luồng có thể xuất xen kẽ. Timestamp và correlation/trace ID giúp điều tra, nhưng không nên mặc định thứ tự các dòng log thu thập từ nhiều máy phản ánh đúng mọi quan hệ xảy ra trước/sau.

## 12. Logger trong JUL, SLF4J, Logback và Log4j 2

Từ **Logger** còn xuất hiện ở nhiều thư viện Java. Chúng cùng mục đích là làm điểm phát log, nhưng khác API và cách kết nối hệ thống xử lý.

| Thành phần | Logger đóng vai trò gì? |
| --- | --- |
| **java.util.logging (JUL)** | Logger là API thuộc JDK, kết hợp LogManager và Handler/Formatter của JUL |
| **SLF4J** | Logger là giao diện facade cho ứng dụng; provider/backend phù hợp thực hiện việc ghi |
| **Logback** | Hệ thống logging thường làm backend cho SLF4J, cung cấp logger, appender và encoder |
| **Log4j 2** | Có API logger và thành phần thực thi/configuration riêng; có thể tích hợp với SLF4J theo cấu hình phù hợp |

Ví dụ minh họa **SLF4J**:

~~~java
// Cần có dependency SLF4J và provider phù hợp.
// Đây không phải chương trình Java chạy độc lập chỉ với JDK.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(MyService.class);

LOG.info("Đã xử lý đơn hàng {}", orderId);
~~~

Với **SLF4J**, placeholder phổ biến là **{}**. Với lời gọi định dạng tham số trong **JUL** ở mục 6, dùng **{0}**. Tránh sao chép cú pháp logging từ framework này sang framework khác mà không kiểm tra API.

Trong dự án đã chọn framework logging, ưu tiên **cùng một cách lấy Logger và cùng một hệ cấu hình**. Không cài nhiều provider/backend hoặc bridge chồng chéo thiếu kiểm soát vì có thể tạo log trùng, nhầm mức hoặc vòng chuyển tiếp.

## 13. Quy tắc dùng Logger an toàn và dễ bảo trì

1. **Giữ Logger theo lớp/thành phần và đặt tên ổn định**. Trong ứng dụng đa module, tên logger có tổ chức giúp cấu hình theo package.
2. **Ghi sự kiện có ý nghĩa**: mô tả hành động, kết quả và ngữ cảnh cần thiết; ưu tiên mã yêu cầu hoặc mã lỗi ổn định nếu có.
3. **Không đưa bí mật vào log**: password, access token, API key, cookie phiên, số thẻ hoặc dữ liệu cá nhân nhạy cảm không nên xuất dưới dạng thô. Không mặc định log toàn bộ request/response body.
4. **Không lấy logging làm luồng điều khiển**: ghi SEVERE không thay exception handling; ứng dụng vẫn phải xử lý, trả lỗi hoặc dừng theo logic phù hợp.
5. **Không log quá nhiều**: vòng lặp lớn hay mỗi sự kiện thành công ở lưu lượng cao có thể gây chi phí I/O và lưu trữ. Dùng metrics khi cần đếm/tỷ lệ.
6. **Không phụ thuộc độ bền của log**: có thể mất log khi buffer chưa flush, đầu ra bị lỗi hoặc hệ thống nhận quá tải. Sự kiện nghiệp vụ bắt buộc phải được lưu đáng tin cậy cần cơ chế chuyên dụng.
7. **Chủ động quyết định level và handler**: cả hai lớp lọc phải được cấu hình phù hợp nếu muốn nhìn thấy chi tiết.
8. **Có chính sách retention và quyền truy cập**: log phục vụ chẩn đoán, nhưng cũng là dữ liệu cần bảo vệ.

## 14. Lỗi thường gặp khi dùng Logger

| Lỗi | Biểu hiện | Cách tránh |
| --- | --- | --- |
| Chỉ đặt logger FINE, handler vẫn INFO | Không thấy log FINE | Điều chỉnh ngưỡng phù hợp ở logger **và** handler |
| Logger con có handler riêng nhưng vẫn phát lên cha | Cùng một sự kiện xuất nhiều lần | Kiểm tra handler gắn ở đâu và useParentHandlers |
| Tạo handler trong mỗi request | Log trùng, rò tài nguyên, khó quản lý | Cấu hình logging một lần ở cấp khởi tạo |
| Ghi DEBUG/FINE ở tất cả mọi nơi trên production | Quá nhiều dữ liệu và chi phí | Bật chi tiết có chọn lọc |
| Gọi LOGGER.info với dữ liệu nhạy cảm | Lộ thông tin qua log | Loại bỏ, ẩn hoặc giảm độ chi tiết dữ liệu |
| Chỉ ghi ex.getMessage() | Thiếu stack trace/nguyên nhân | Truyền Throwable cho logging API khi cần |
| Nhầm LOGGER.severe với throw | Có log nhưng chương trình vẫn chạy | Xử lý lỗi bằng luồng điều khiển thích hợp |
| Nhầm JUL {0} với SLF4J {} | Thông điệp không được định dạng như mong đợi | Dùng đúng API và quy tắc tham số |
| Không flush StreamHandler trong ví dụ ngắn | Chạy xong nhưng chưa thấy output mong đợi | Flush khi cần; môi trường thật có chính sách buffer phù hợp |

## 15. Câu hỏi tự kiểm tra

**Câu 1. Logger có phải chính là file log không?**

Không. Logger là đối tượng/API phát sự kiện; Handler/Appender và đích xuất quyết định dữ liệu được gửi/lưu ở đâu.

**Câu 2. Logger ở INFO có xuất LOGGER.fine(...) không?**

Thông thường không, vì FINE thấp hơn ngưỡng INFO. Nâng level của handler không làm xuất một sự kiện đã bị logger loại bỏ.

**Câu 3. Tại sao một lời gọi LOGGER.warning(...) có thể xuất hai lần?**

Một nguyên nhân thường gặp là logger con có handler riêng đồng thời chuyển tiếp bản ghi lên handler của cha. Cần xem cấu hình handler và thuộc tính useParentHandlers.

**Câu 4. Vì sao nên truyền exception vào LOGGER.log(..., ex) khi điều tra lỗi?**

Để logging system có thể giữ stack trace và chuỗi nguyên nhân; chỉ có nội dung ex.getMessage() thường không đủ. Formatter phải hỗ trợ xuất throwable thì thông tin đó mới hiển thị trong log đầu ra.

**Câu 5. Nên dùng Logger hay System.out.println cho dự án Java?**

Logger thường là lựa chọn phù hợp vì có level, nguồn phát sinh và khả năng cấu hình đầu ra. System.out.println vẫn có thể hữu dụng cho chương trình rất nhỏ hoặc ví dụ console, nhưng không thay thế đầy đủ cơ chế logging của ứng dụng.

**Ghi nhớ:** **Logger là điểm phát bản ghi sự kiện từ mã Java.** Để sự kiện xuất hiện đúng nơi và đúng mức, phải hiểu **Logger → Level/Filter → Handler/Appender → Formatter → Đích ghi**, cùng quy tắc đặt tên, quản lý ngoại lệ và bảo vệ dữ liệu nhạy cảm.
