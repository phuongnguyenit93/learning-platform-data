# Mức độ log trong Java

## 1. Mức độ log là gì?

**Mức độ log (logging level)** là nhãn thể hiện mức độ nghiêm trọng hoặc mức độ chi tiết của một sự kiện được ghi vào nhật ký ứng dụng. Mức log giúp người phát triển và người vận hành quyết định thông tin nào cần xuất hiện trong từng môi trường, từ thông báo lỗi quan trọng đến dấu vết thực thi rất chi tiết.

Ví dụ, cùng một ứng dụng đặt hàng có thể ghi:
- **ERROR / SEVERE:** Không thể ghi đơn hàng vì cơ sở dữ liệu không phản hồi.
- **WARN / WARNING:** Lần gọi dịch vụ thanh toán đầu tiên bị timeout nhưng lần thử lại đã thành công.
- **INFO:** Ứng dụng đã khởi động, hoặc đơn hàng đã chuyển sang trạng thái hoàn tất.
- **DEBUG / FINE:** Nhánh xử lý nào được chọn và số bản ghi được đọc.
- **TRACE / FINER / FINEST:** Các bước nội bộ và giá trị trung gian dùng khi điều tra lỗi khó.

Tên mức log phụ thuộc vào API hoặc framework. Java có sẵn **Java Util Logging (JUL)** trong gói **java.util.logging**. Các ứng dụng khác có thể ghi qua **SLF4J** rồi chuyển cho backend như Logback hoặc Log4j 2. Các bộ mức này gần nhau về mục đích nhưng không trùng tên và không có ánh xạ chính xác tuyệt đối.

## 2. Các mức trong java.util.logging

Lớp **java.util.logging.Level** định nghĩa các mức chuẩn theo thứ tự từ nghiêm trọng đến chi tiết. Mỗi mức có một giá trị số; số lớn hơn biểu thị mức ưu tiên cao hơn khi lọc log.

| Mức JUL | Giá trị | Ý nghĩa và cách dùng |
| --- | ---: | --- |
| **SEVERE** | 1000 | Lỗi nghiêm trọng: một thao tác quan trọng thất bại, dịch vụ hoặc thành phần không hoạt động đúng. |
| **WARNING** | 900 | Tình huống bất thường hoặc có nguy cơ, nhưng ứng dụng vẫn có thể tiếp tục hoặc phục hồi. |
| **INFO** | 800 | Sự kiện nghiệp vụ hay vòng đời đáng quan tâm trong vận hành thông thường. |
| **CONFIG** | 700 | Thông tin cấu hình có ích khi chẩn đoán, chẳng hạn chiến lược cache đã chọn; không ghi bí mật cấu hình. |
| **FINE** | 500 | Thông tin gỡ lỗi ở mức tương đối tổng quát. |
| **FINER** | 400 | Diễn tiến thực thi chi tiết hơn, chẳng hạn các bước trong thuật toán. |
| **FINEST** | 300 | Chi tiết rất nhỏ, chỉ nên bật có chọn lọc khi cần truy vết sâu. |
| **OFF** | 2147483647 | Giá trị đặc biệt dùng để tắt ghi log theo ngưỡng. |
| **ALL** | -2147483648 | Giá trị đặc biệt dùng để cho phép mọi mức chuẩn đi qua ngưỡng. |

**OFF** và **ALL** là các giá trị cấu hình, không phải hai loại sự kiện nghiệp vụ cần ghi thường xuyên. JUL còn cho phép định nghĩa **Level** tùy chỉnh; bảng trên trình bày các mức chuẩn.

Một số nguyên tắc chọn mức:
- Một yêu cầu bị từ chối **đúng theo quy tắc nghiệp vụ** không tự động là lỗi nghiêm trọng. Có thể dùng INFO, FINE hoặc không ghi, tùy nhu cầu quan sát.
- Một lỗi có thể **phục hồi được** thường phù hợp với WARNING; lỗi khiến chức năng thiết yếu thất bại thường phù hợp với SEVERE.
- Dữ liệu debug chi tiết không nên dồn vào INFO chỉ để dễ nhìn thấy: điều đó làm giảm giá trị của log vận hành và tăng chi phí lưu trữ.
- Lựa chọn mức phải nhất quán theo tác động thực tế. Không phân loại mọi ngoại lệ thành SEVERE chỉ vì chúng là exception.

## 3. Cơ chế lọc theo ngưỡng

Khi đặt ngưỡng log của JUL thành một mức, những sự kiện có mức **bằng hoặc cao hơn ngưỡng** mới đủ điều kiện được ghi.

| Ngưỡng của Logger | Các mức chuẩn có thể đi qua bộ lọc Logger |
| --- | --- |
| **WARNING** | WARNING, SEVERE |
| **INFO** | INFO, WARNING, SEVERE |
| **CONFIG** | CONFIG, INFO, WARNING, SEVERE |
| **FINE** | FINE, CONFIG, INFO, WARNING, SEVERE |
| **FINER** | FINER, FINE, CONFIG, INFO, WARNING, SEVERE |
| **FINEST** hoặc **ALL** | Tất cả bảy mức thông thường |
| **OFF** | Không ghi sự kiện thông thường |

Mô hình JUL có **hai nơi lọc quan trọng**:

1. **Logger** quyết định có tạo và công bố bản ghi ở mức được yêu cầu hay không. Khi gọi **logger.setLevel(null)**, Logger kế thừa mức hiệu lực từ Logger cha.
2. **Handler** nhận bản ghi được truyền tới nó, rồi áp dụng ngưỡng và bộ lọc của chính nó trước khi xuất ra console, file hoặc đích khác.

Vì vậy, bật **FINE** ở Logger chưa đảm bảo dòng FINE xuất hiện: nếu **ConsoleHandler** vẫn có ngưỡng **INFO**, Handler có thể loại bỏ bản ghi đó. Bản ghi cũng có thể bị loại bởi **Filter** hay do cấu hình tuyến Handler. Trong thực tế, khi “không thấy log debug”, hãy kiểm tra cả Logger, Handler và việc Logger có truyền bản ghi lên Logger cha hay không.

## 4. Ví dụ Java 17 chạy độc lập

Tạo tệp **LoggingLevelsDemo.java** theo mã sau. Ví dụ chủ động tắt Handler của Logger cha, đặt mức Logger thành **FINE**, cho Handler nhận **ALL**, và dùng formatter đơn giản để kết quả ổn định giữa các lần chạy.

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingLevelsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(LoggingLevelsDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        logger.severe("Không thể lưu cấu hình");
        logger.warning("Kết nối đang chậm");
        logger.info("Ứng dụng sẵn sàng");
        logger.config("Chế độ kiểm tra đã tắt");
        logger.fine("Đã tải 3 bản ghi");
        logger.finer("Chi tiết vòng lặp");
        logger.finest("Giá trị tại từng bước");

        handler.flush();
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LoggingLevelsDemo.java
java LoggingLevelsDemo
~~~

Nội dung hiển thị trên **stderr** (ConsoleHandler mặc định ghi ra stderr, không phải stdout):

~~~text
SEVERE | Không thể lưu cấu hình
WARNING | Kết nối đang chậm
INFO | Ứng dụng sẵn sàng
CONFIG | Chế độ kiểm tra đã tắt
FINE | Đã tải 3 bản ghi
~~~

Hai lời gọi **finer** và **finest** không xuất hiện vì thấp hơn ngưỡng **FINE** của Logger. Nếu đổi thành **logger.setLevel(Level.WARNING)**, chỉ còn hai dòng SEVERE và WARNING. Nếu giữ Logger ở FINE nhưng đổi thành **handler.setLevel(Level.WARNING)**, kết quả cũng chỉ còn hai dòng đó. Ví dụ kiểm chứng được rằng một bản ghi phải vượt qua cả ngưỡng Logger và ngưỡng Handler.

Để tránh nhiều Handler ghi trùng một thông điệp, cần hiểu ý nghĩa của **setUseParentHandlers(false)**: Logger trong ví dụ tự xuất log qua Handler vừa thêm, thay vì tiếp tục chuyển bản ghi lên Handler của Logger cha. Trong ứng dụng thực tế, cấu hình tập trung thường được ưu tiên hơn việc tự tạo Handler ở nhiều lớp.

## 5. Chọn mức log trong tình huống thực tế

| Tình huống | Mức gợi ý | Lý do |
| --- | --- | --- |
| Không thể hoàn tất giao dịch vì hệ thống lưu trữ bị lỗi | SEVERE / ERROR | Chức năng quan trọng đã thất bại và cần được điều tra. |
| Dịch vụ phụ chậm nhưng có phương án dự phòng thành công | WARNING / WARN | Bất thường đáng theo dõi, song luồng chính vẫn hoạt động. |
| Server khởi động thành công, job định kỳ hoàn tất | INFO | Cột mốc vận hành có giá trị ở môi trường production. |
| Ghi nhận chiến lược cấu hình hoặc chế độ chạy đã được chọn | CONFIG (JUL) | Hữu ích để hiểu cách ứng dụng được thiết lập; tránh dữ liệu nhạy cảm. |
| Biết nhánh xử lý hoặc cache hit/miss khi chẩn đoán | FINE / DEBUG | Chi tiết chỉ nên xuất hiện khi cần điều tra. |
| Theo dõi từng bước parse, từng nhánh nội bộ rất nhỏ | FINER–FINEST / TRACE | Số lượng lớn, có thể tốn CPU, I/O và dung lượng lưu trữ. |

Đây là **quy ước khuyến nghị**, không phải quy tắc cứng. Ví dụ, một lỗi từ client do nhập sai dữ liệu có thể là sự kiện bình thường; việc ghi nó ở ERROR với lưu lượng cao sẽ tạo nhiều cảnh báo không cần thiết. Ngược lại, một sự kiện hiếm nhưng cho biết mất dữ liệu phải được ghi ở mức nổi bật.

**Không sử dụng log như cơ chế xử lý lỗi.** Log hỗ trợ quan sát; ứng dụng vẫn phải xử lý exception, trả mã lỗi thích hợp, retry hoặc rollback theo đúng thiết kế. Một lỗi đã được xử lý ở tầng dưới có thể chỉ cần ghi một lần ở ranh giới chịu trách nhiệm, tránh cùng một exception xuất hiện nhiều lần trong hệ thống.

## 6. Ghi log có tham số, ngoại lệ và chi phí tạo thông điệp

Trong JUL, dùng phương thức **logger.log** để chỉ rõ mức log, truyền tham số hoặc đính kèm nguyên nhân lỗi. Ví dụ sau là **đoạn minh họa trong một phương thức đã có Logger**, không phải chương trình độc lập:

~~~java
logger.log(Level.INFO, "Đang xử lý đơn hàng {0}", orderId);

try {
    readConfiguration();
} catch (java.io.IOException e) {
    logger.log(Level.SEVERE, "Không thể đọc cấu hình", e);
}
~~~

Tham số **orderId** sẽ được định dạng theo cơ chế của JUL khi Formatter hỗ trợ. Khi truyền **Throwable** vào overload phù hợp, bản ghi giữ được stack trace; việc nó được hiển thị như thế nào còn phụ thuộc Formatter. Không nên chỉ ghi **e.getMessage()** nếu đang cần nguyên nhân, vị trí và stack trace để chẩn đoán.

Với thông điệp có phép tính tốn kém, hãy tránh tạo chuỗi trước khi hệ thống xác định mức đó có được bật. Java hỗ trợ **Supplier** cho log lazy:

~~~java
logger.log(Level.FINE, () -> "Số phần tử: " + expensiveCount());
~~~

Ở lời gọi này, **expensiveCount()** chỉ được đánh giá khi JUL quyết định mức FINE có thể được ghi tại Logger. Cách tương đương là kiểm tra **logger.isLoggable(Level.FINE)** trước một khối debug phức tạp. Cần nhớ rằng ngưỡng Handler hoặc Filter vẫn có thể loại sự kiện sau bước này; log lazy không thay thế việc thiết kế ngưỡng phù hợp. Các đoạn trên minh họa API và giả định các biến/hàm liên quan đã tồn tại.

## 7. JUL và SLF4J/Logback khác nhau thế nào?

Trong nhiều dự án Java, mã nghiệp vụ sử dụng **SLF4J** như một API thống nhất; một hệ thống logging thực tế (thường là Logback hoặc Log4j 2) xử lý việc lọc, định dạng và đưa log tới nơi lưu trữ. SLF4J phổ biến với năm mức sau, từ nghiêm trọng đến chi tiết:

**ERROR → WARN → INFO → DEBUG → TRACE**

Có thể dùng bảng đối chiếu **theo ý nghĩa**, không coi là quy tắc mapping bắt buộc:

| JUL | SLF4J thường dùng | Ghi chú |
| --- | --- | --- |
| SEVERE | ERROR | Lỗi cần chú ý. |
| WARNING | WARN | Tình huống bất thường hoặc nguy cơ. |
| INFO | INFO | Thông tin vận hành bình thường. |
| CONFIG, FINE | DEBUG (gần đúng) | Không có mức CONFIG riêng trong SLF4J; ánh xạ thật do bridge/backend quyết định. |
| FINER, FINEST | TRACE (gần đúng) | Chỉ là so sánh về độ chi tiết. |

SLF4J không định nghĩa mức **FATAL** riêng trong API phổ biến; một số framework khác, chẳng hạn Log4j 2, có các mức bổ sung. **Không mặc định rằng mọi cầu nối JUL–SLF4J đều áp dụng bảng trên đúng từng dòng.** Khi cấu hình bridge, hãy kiểm tra mapping và ngưỡng thực tế của thư viện.

Ví dụ cú pháp SLF4J trong một lớp đã có Logger (minh họa, **cần có dependency SLF4J và backend**):

~~~java
log.error("Không thể lưu đơn hàng {}", orderId, exception);
log.warn("Thanh toán chậm, requestId={}", requestId);
log.info("Job hoàn tất: {} bản ghi", count);
log.debug("Kết quả cache: {}", cacheResult);
log.trace("Đang xét phần tử index={}", index);
~~~

Phương thức kiểu này thường dùng placeholder **{}** để tách dữ liệu khỏi chuỗi mẫu. Đây không phải cú pháp định dạng của JUL; JUL dùng phương pháp tham số khác, chẳng hạn **{0}** trong thông điệp được Formatter hỗ trợ. Không trộn lẫn hai kiểu placeholder.

## 8. Cấu hình ngưỡng log trong ứng dụng

Trong JUL, ngoài cách gọi **setLevel** ở mã, có thể cấu hình bằng tệp properties được JVM tải khi khởi động. Ví dụ tệp **logging.properties**:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = ALL
com.example.service.level = FINE
~~~

Chạy ứng dụng có package tương ứng:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Ý nghĩa: ngưỡng Logger gốc là INFO; các Logger dưới tên **com.example.service** có thể bật FINE; ConsoleHandler được đặt ALL để không chặn các bản ghi FINE mà Logger con cho qua. Hãy dùng tên Logger/package thực tế của dự án và đảm bảo classpath cùng tên lớp chính phù hợp. Lệnh trên là mẫu cấu hình, **không phải lệnh chạy chương trình LoggingLevelsDemo phía trước** vì chương trình demo chủ động tự cài đặt Logger và Handler.

Với Logback hoặc Log4j 2, file cấu hình và cú pháp khác JUL; các khái niệm vẫn tương tự: ngưỡng Logger và bộ xuất log (appender), tuyến truyền bản ghi, bộ lọc, formatter/layout và nơi nhận log. Một môi trường thường bắt đầu từ **INFO**, chỉ bật DEBUG/TRACE cho thành phần cần chẩn đoán và trong thời gian phù hợp. Mức mặc định thực tế phụ thuộc cấu hình của framework và ứng dụng, nên không nên dựa vào giả định khi vận hành.

## 9. Những lỗi phổ biến cần tránh

1. **Nhầm ERROR/WARN/DEBUG với hằng số của JUL.** JUL dùng SEVERE/WARNING/FINE..., còn ERROR/WARN/DEBUG thường gặp trong SLF4J và framework liên quan.
2. **Chỉ chỉnh Logger mà quên Handler/appender.** Một ngưỡng cao hơn ở tầng xuất log vẫn có thể chặn bản ghi.
3. **Ghi mọi bước ở INFO hoặc SEVERE.** Điều này làm mất tín hiệu của lỗi thực sự và gây bùng nổ dữ liệu log.
4. **Bật FINEST/TRACE toàn hệ thống lâu dài.** Có thể ảnh hưởng hiệu năng, chi phí và làm lộ thông tin không cần thiết.
5. **Ghi thông tin nhạy cảm.** Không đưa mật khẩu, token, khóa bí mật, dữ liệu cá nhân hoặc toàn bộ request/response nhạy cảm vào log, bất kể mức nào.
6. **Log rồi ném lại cùng một exception qua nhiều tầng.** Dễ tạo bản ghi trùng lặp, khó đếm sự cố. Chọn tầng chịu trách nhiệm ghi lỗi và giữ nguyên stack trace khi cần.
7. **Ghép chuỗi đắt tiền trước khi kiểm tra ngưỡng.** Dùng API tham số, Supplier hoặc kiểm tra **isLoggable** khi phù hợp.
8. **Không gắn ngữ cảnh có thể truy vết.** Khi cần, thêm mã yêu cầu, mã thao tác, tên thành phần và kết quả; tránh định danh nhạy cảm hoặc dữ liệu có độ chi tiết quá mức.

## 10. Tự kiểm tra kiến thức

- Nếu Logger ở **Level.INFO** và ConsoleHandler ở **Level.FINE**, thông điệp FINE có xuất hiện không? **Không**, vì Logger đã chặn nó trước.
- Nếu Logger ở **Level.FINE** và ConsoleHandler ở **Level.WARNING**, thông điệp INFO có xuất hiện không? **Không**, vì Handler chặn.
- Khi ứng dụng xử lý thành công một lần retry sau timeout, dùng WARNING hay SEVERE? **Thường là WARNING**, vì có bất thường nhưng đã phục hồi; lựa chọn cuối cùng phụ thuộc mức độ ảnh hưởng.
- Muốn xem những bước rất chi tiết của thuật toán trong JUL thì chọn gì? **FINER/FINEST** ở Logger **và** cấu hình Handler cho phép các mức đó.
- Khi dùng SLF4J, mức nào tương ứng với việc chẩn đoán phổ biến? **DEBUG**; dùng **TRACE** khi cần chi tiết sâu hơn.

**Ghi nhớ:** Mức log là công cụ để điều chỉnh lượng thông tin theo mức độ nghiêm trọng và nhu cầu điều tra. Chọn đúng mức ở điểm phát sinh sự kiện, cấu hình đủ các tầng lọc và bảo vệ dữ liệu trong log sẽ giúp hệ thống vừa dễ vận hành, vừa dễ gỡ lỗi.
