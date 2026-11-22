# DEBUG — Mức log chi tiết trong Java

## 1. DEBUG là gì?

**DEBUG** là mức log dành cho thông tin chi tiết giúp lập trình viên **hiểu chương trình đã đi qua những bước nào, chọn nhánh xử lý nào, trạng thái trung gian ra sao và vì sao một hành vi xảy ra**. DEBUG đặc biệt hữu ích khi điều tra lỗi khó tái hiện, kiểm tra giả thuyết về luồng thực thi hoặc phân tích sự tương tác giữa các thành phần.

Ví dụ các sự kiện thích hợp cho DEBUG:

~~~text
DEBUG service=pricing requestId=req-17 rule=member-discount matched=true
DEBUG service=pricing requestId=req-17 subtotal=100 discount=10 total=90
DEBUG service=inventory requestId=req-17 cache=miss fallback=database
~~~

Đây là các dòng **minh họa**, không phải output mặc định của một thư viện cụ thể. Chúng cho thấy DEBUG có thể ghi lại **quyết định và trạng thái trung gian** mà bình thường không cần xuất trong log vận hành.

DEBUG **không phải trình gỡ lỗi (debugger)**. Debugger có thể dừng chương trình, đặt breakpoint và xem biến tại thời điểm đang chạy. DEBUG là **mức độ của bản ghi log**: ứng dụng vẫn chạy bình thường và có thể phát sự kiện theo cấu hình ngay cả khi không gắn debugger.

DEBUG cũng **không tự động bật chế độ debug của JVM, không chạy từng dòng chậm hơn theo cơ chế đặc biệt, không sửa lỗi và không thay đổi logic nghiệp vụ**. Nó chỉ cho phép phát thêm những sự kiện logging được lập trình viên chủ động ghi ở mức đó (và được hệ thống logging cho qua).

## 2. DEBUG nằm ở đâu trong các log level?

Các thư viện logging phổ biến như **SLF4J kết hợp Logback** và **Log4j 2** thường dùng thứ tự tăng dần về mức nghiêm trọng:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Các tên và cách cấu hình phụ thuộc thư viện, nhưng nguyên tắc ngưỡng thường như sau:

| Ngưỡng được cấu hình | Các thông điệp thường được cho phép trong thang level trên |
| --- | --- |
| ERROR | ERROR |
| WARN | WARN, ERROR |
| INFO | INFO, WARN, ERROR |
| DEBUG | DEBUG, INFO, WARN, ERROR |
| TRACE | TRACE, DEBUG, INFO, WARN, ERROR |

Bảng giả định không có bộ lọc khác hoặc giới hạn ở appender. Khi cấu hình **INFO**, lệnh gọi debug(...) thông thường bị bỏ qua. Khi cấu hình **DEBUG**, các lệnh debug(...) trở nên đủ điều kiện xuất; ứng dụng vẫn cần appender và filter cho phép.

### Java chuẩn có level DEBUG không?

Trong **java.util.logging (JUL)**, API có sẵn của JDK, **không có hằng số java.util.logging.Level.DEBUG**. JUL dùng các mức như **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

Để học ý tưởng của DEBUG bằng JDK thuần, có thể dùng **Level.FINE** như mức gần tương đương cho các chi tiết phục vụ debug:

| Ý định | SLF4J/Logback thường dùng | JUL thường dùng |
| --- | --- | --- |
| Cột mốc vận hành | INFO | INFO |
| Chi tiết phục vụ tìm lỗi | DEBUG | FINE |
| Truy vết rất chi tiết | TRACE | FINER hoặc FINEST |
| Cảnh báo | WARN | WARNING |
| Lỗi nghiêm trọng | ERROR | SEVERE |

**Đây là đối chiếu về mục đích, không phải ánh xạ bảo đảm tương đương hoàn toàn**. Nếu ứng dụng sử dụng JUL, hãy gọi **LOGGER.fine(...)** hoặc **LOGGER.log(Level.FINE, ...)**; nếu dùng SLF4J, hãy gọi **logger.debug(...)**. Không viết **Level.DEBUG** trong mã JUL vì hằng số đó không tồn tại.

## 3. Khi nào nên ghi DEBUG?

DEBUG có giá trị nhất ở những điểm mà người đọc cần một **bằng chứng cụ thể về luồng và quyết định**:

1. **Chọn nhánh xử lý:** “Áp dụng rule giảm giá A vì loại đơn hàng X”.
2. **Gọi thành phần phụ thuộc:** “Cache miss, chuyển sang đọc database”, kèm tên tác vụ và ID tương quan.
3. **Biến đổi dữ liệu:** số bản ghi trước/sau khi lọc, điều kiện được áp dụng, kết quả tổng hợp an toàn để ghi.
4. **Vòng đời một thao tác phức tạp:** bắt đầu/hoàn thành từng giai đoạn có ý nghĩa, thời lượng một bước tốn thời gian.
5. **Điều tra lỗi theo giả thuyết:** ghi giá trị trạng thái tối thiểu cần phân biệt hai đường đi; có thể bật trong thời gian ngắn khi cần.
6. **Tích hợp hệ thống:** ghi mã phản hồi, số lần retry, timeout được chọn, circuit breaker state; tránh đưa nội dung nhạy cảm vào log.

Ví dụ:

~~~text
DEBUG component=payment requestId=req-22 attempt=2 retryDelayMs=200 reason=timeout
~~~

Thông điệp trên hữu ích để xem *vì sao hệ thống thử lại*; còn số lần retry mỗi phút, tỷ lệ timeout hoặc latency p95 nên được đo bằng **metric** để theo dõi xu hướng.

Không nên log tất cả biến cục bộ chỉ vì DEBUG đang bật. Một dòng DEBUG tốt cần gắn với **câu hỏi chẩn đoán cụ thể**; log lan man khiến sự kiện quan trọng bị chìm trong dữ liệu.

## 4. Cơ chế bật/tắt DEBUG

Cách hoạt động thường thấy:

~~~text
Mã ứng dụng: logger.debug("...")
                    |
                    v
             Logger xét level
                    |
          DEBUG có được chấp nhận?
             /               \
          không              có
           |                  |
       bỏ qua          tạo/chuyển log event
                              |
                              v
                     Appender và filter
                              |
                              v
                    Encoder/Formatter
                              |
                              v
                   Console / File / ...
~~~

Trong JUL, tên tương ứng là **Logger**, **Handler** và **Formatter**; trình tự và cách xét filter phụ thuộc cấu hình. Cùng một sự kiện còn có thể được chuyển tiếp lên logger cha, dẫn đến nhiều handler nhận bản ghi.

Ba khái niệm cần tách riêng:

- **Mức của sự kiện:** lệnh gọi DEBUG/FINE cho biết thông tin thuộc loại nào.
- **Ngưỡng của logger:** điều kiện đầu tiên để sự kiện được phát.
- **Ngưỡng/filter của handler hoặc appender:** quyết định sự kiện đã được phát có đi tới đích đó hay không.

Vì vậy, đặt logger ở DEBUG nhưng appender có filter chỉ cho INFO trở lên thì vẫn có thể **không thấy DEBUG**. Ngược lại, đặt appender rất chi tiết cũng không cứu được sự kiện đã bị logger lọc ngay từ đầu.

Mức log thường có thể cấu hình theo **package/tên logger**. Chẳng hạn chỉ bật DEBUG cho thành phần tính giá, trong khi các thành phần khác vẫn ở INFO. Đây là cách thu hẹp lượng log khi điều tra sự cố.

## 5. Ví dụ Java 17+ chạy được: minh họa DEBUG bằng JUL FINE

Để chạy trực tiếp với JDK 17 trở lên **không cần dependency**, ví dụ sau dùng **java.util.logging.Level.FINE** thay cho ý tưởng DEBUG. Nó cố ý cho thấy sự kiện chi tiết bị ẩn khi ngưỡng là INFO và xuất hiện sau khi chuyển ngưỡng sang FINE.

Tạo tệp **DebugLevelDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class DebugLevelDemo {
    private static final Logger LOGGER =
            Logger.getLogger(DebugLevelDemo.class.getName());

    public static void main(String[] args) {
        // Dùng duy nhất handler ở dưới để kết quả không bị in trùng.
        LOGGER.setUseParentHandlers(false);

        // Ban đầu chỉ phát INFO và mức nghiêm trọng hơn.
        LOGGER.setLevel(Level.INFO);

        // Đích xuất stdout; handler phải cho phép cả FINE.
        Handler console = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        console.setLevel(Level.FINE);
        LOGGER.addHandler(console);

        LOGGER.info("Bắt đầu xử lý job-42");

        // Không xuất: logger đang ở INFO nên FINE bị loại.
        LOGGER.log(Level.FINE,
                () -> "jobId=job-42 branch=standard");

        // Bật mức chi tiết gần tương đương DEBUG.
        LOGGER.setLevel(Level.FINE);
        LOGGER.log(Level.FINE,
                () -> "jobId=job-42 base=100 discount=10");
        LOGGER.info("Hoàn tất job-42: total=90");

        // StreamHandler có buffer nên cần flush trong ví dụ ngắn.
        console.flush();
    }
}
~~~

Biên dịch và chạy trong terminal hỗ trợ UTF-8:

~~~bash
javac -encoding UTF-8 DebugLevelDemo.java
java DebugLevelDemo
~~~

**Stdout chính xác** của chương trình trong môi trường như mô tả:

~~~text
INFO | Bắt đầu xử lý job-42
FINE | jobId=job-42 base=100 discount=10
INFO | Hoàn tất job-42: total=90
~~~

Giải thích:

1. **LOGGER.setLevel(Level.INFO)** đặt ngưỡng ban đầu. Vì **FINE** thấp hơn INFO, thông điệp branch=standard không được phát.
2. **LOGGER.setLevel(Level.FINE)** cho phép sự kiện FINE ở các lời gọi tiếp theo. Không cần biên dịch lại chương trình để chuyển ngưỡng trong ví dụ.
3. **console.setLevel(Level.FINE)** làm handler chấp nhận FINE; nếu handler giữ INFO, dòng FINE vẫn có thể bị bỏ qua.
4. **LOGGER.setUseParentHandlers(false)** tránh việc các handler ở logger cha xuất thêm bản ghi, có thể với định dạng khác.
5. **StreamHandler(System.out, Formatter)** chủ động gửi log ra **stdout** và định dạng chỉ gồm level + message. **ConsoleHandler mặc định của JUL thường ghi ra stderr**, nên không nên mặc định hai cách cho ra cùng luồng đích.
6. **console.flush()** đẩy nội dung còn trong bộ đệm ra stdout để kết quả đầy đủ.
7. Lambda **() -> ...** là cách cung cấp thông điệp qua Supplier của JUL; nó hữu ích khi biểu thức tạo log tốn chi phí và level đang bị tắt.

Trong ứng dụng thực tế, level thường được cấu hình tập trung và thay đổi có kiểm soát theo môi trường. Ví dụ tự cấu hình một handler trong main chỉ để minh họa rõ từng thành phần.

## 6. DEBUG thật sự với SLF4J và Logback

Trong một dự án sử dụng **SLF4J** làm API và **Logback** làm backend, cách viết phổ biến là:

~~~java
// Đoạn mã minh họa đặt trong một lớp có biến orderId, ruleName.
// Cần SLF4J API và logging provider thích hợp trong dependencies.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PricingService.class);

LOG.debug("orderId={} matchedRule={}", orderId, ruleName);
LOG.info("Đã hoàn tất tính giá cho orderId={}", orderId);
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập chỉ với JDK: cần khai báo lớp PricingService, các biến, và dependency SLF4J/backend. **{}** là placeholder theo quy ước của SLF4J, không phải cú pháp tham số **{0}** thường dùng trong JUL.

Với Logback, một cấu hình ví dụ trong tệp **logback.xml** nằm trên classpath:

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.pricing" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Ý nghĩa:

- Mã thuộc nhóm logger **com.example.pricing** có thể phát DEBUG.
- Các nhóm logger khác thường kế thừa ngưỡng **INFO** của root nếu không có cấu hình riêng.
- Appender STDOUT nhận sự kiện đã được chấp nhận và định dạng chúng. Mẫu này không thêm threshold filter riêng, nên DEBUG của nhóm pricing có thể được xuất qua appender gắn ở root.
- Cấu hình này chỉ có tác dụng khi dự án **thực sự đang dùng Logback** và tệp được tải đúng cách. Không áp dụng tệp logback.xml cho ứng dụng chỉ dùng JUL.

Một ứng dụng dùng Spring Boot có thể cung cấp cơ chế cấu hình level riêng; hãy kiểm tra framework/backend thực tế của dự án thay vì giả định tất cả đều đọc cùng tệp cấu hình.

### Bật DEBUG nhưng không thấy log: kiểm tra gì?

Kiểm tra theo thứ tự:

1. Trong mã có thật sự gọi **debug(...)** hoặc **Level.FINE** tại vị trí cần quan sát không?
2. Lời gọi có đi qua nhánh thực thi đó trong trường hợp đang kiểm tra không?
3. Level của **đúng tên logger/package** có chấp nhận DEBUG/FINE không?
4. Ngưỡng của handler/appender và các filter khác có chặn nó không?
5. Ứng dụng có tải đúng tệp hoặc biến cấu hình của **backend đang hoạt động** không?
6. Log được gửi ra console, stderr, file, container collector hay dịch vụ tập trung? Có thể bạn đang xem sai đích.
7. Có cơ chế lọc, sampling, buffer hoặc độ trễ thu thập ở nơi nhận không?

Lời gọi logger không bảo đảm bản ghi luôn hiện ra ở mọi nơi xem log.

## 7. Hiệu năng: level tắt vẫn có thể tốn chi phí

**Tắt DEBUG không có nghĩa là mọi phép tính tạo dữ liệu DEBUG đều miễn phí.** Trong Java, các biểu thức đối số được đánh giá *trước* khi phương thức được gọi.

Ví dụ minh họa (các biến và phương thức đã được định nghĩa ở nơi sử dụng):

~~~java
LOG.debug("Chi tiết đơn hàng: {}", expensiveSerialize(order));
~~~

Mặc dù backend có thể không xuất DEBUG, **expensiveSerialize(order)** vẫn được thực thi để tạo đối số cho lệnh gọi. Placeholder của SLF4J giúp tránh một phần chi phí dựng chuỗi/định dạng khi level tắt, **không trì hoãn việc đánh giá mọi biểu thức đối số**.

Với SLF4J, nếu việc tạo dữ liệu rất tốn kém, có thể kiểm tra:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("Chi tiết đơn hàng: {}", expensiveSerialize(order));
}
~~~

Với JUL, dùng Supplier hoặc kiểm tra level:

~~~java
LOGGER.log(Level.FINE,
        () -> "Chi tiết đơn hàng: " + expensiveSerialize(order));
~~~

Hai đoạn trên **chỉ minh họa cách dùng trong một lớp đã có logger, biến order và phương thức expensiveSerialize(...)**, không phải chương trình biên dịch độc lập. Trong JUL, supplier cho phép hoãn tạo message khi logger loại level; nếu dùng framework khác, hãy dùng cơ chế lazy logging tương ứng mà phiên bản đó hỗ trợ.

**Không đưa tác dụng phụ bắt buộc vào việc tạo message**. Ví dụ, không tăng bộ đếm nghiệp vụ, ghi database hoặc sửa trạng thái trong supplier chỉ vì muốn ghi DEBUG; khi DEBUG tắt, phần việc đó có thể không diễn ra.

### Nếu bật DEBUG trên production thì sao?

DEBUG có thể làm tăng:

- Lượng chuỗi được tạo và dữ liệu phải định dạng.
- Số sự kiện qua handler/appender, I/O và dung lượng lưu.
- Áp lực lên bộ đệm hoặc hàng đợi logging bất đồng bộ.
- Chi phí truyền, đánh chỉ mục và truy vấn ở hệ thống tập trung.
- Nguy cơ lộ thông tin nếu các thông điệp chi tiết chứa dữ liệu nhạy cảm.

Mức ảnh hưởng tùy lượng sự kiện, định dạng và cấu hình thực tế. Không có quy tắc cố định rằng DEBUG luôn làm ứng dụng chậm một tỷ lệ cụ thể. Hãy đo đạc và bật có chọn lọc.

## 8. Viết thông điệp DEBUG có ích

Một mẫu thực hành tốt là mô tả **đối tượng/tác vụ, bước xử lý, quyết định và kết quả** dưới dạng các trường nhất quán:

~~~text
DEBUG service=order requestId=req-43 stage=validate rule=stock-check result=passed
DEBUG service=order requestId=req-43 stage=price strategy=member subtotal=120 discount=20
DEBUG service=order requestId=req-43 stage=reserve-stock skuGroup=standard result=success
~~~

Khi đọc ba dòng này, bạn có thể thấy tiến trình của cùng request và nhánh xử lý đã chọn. Trong hệ thống nhiều dịch vụ, **trace ID** có thể liên kết các span và log tương ứng.

Các nguyên tắc:

- **Ưu tiên thông điệp có ý nghĩa**: “đã chọn chiến lược X vì Y” hữu dụng hơn “đến dòng 125”.
- **Dùng mã tương quan an toàn**: requestId/traceId có thể giúp tìm log liên quan. Không mặc định rằng mọi ID đều vô hại; áp dụng quy tắc dữ liệu nội bộ.
- **Giữ định dạng nhất quán**: dùng tên trường ổn định, đơn vị rõ ràng như durationMs, sizeBytes; structured logging có thể giúp truy vấn trường dễ hơn.
- **Đừng ghi nguyên đối tượng nếu không cần**: toString() có thể dài, đắt, thay đổi theo phiên bản hoặc vô tình chứa dữ liệu nhạy cảm.
- **Tránh ghi mỗi vòng lặp**: nếu có 100.000 phần tử, một dòng DEBUG cho mỗi phần tử tạo lượng dữ liệu lớn. Cân nhắc log ở mốc tổng hợp hoặc tại điểm bất thường.
- **Không dùng DEBUG để thay metric**: request rate, error rate, queue depth, latency percentile nên có số đo phù hợp; DEBUG phù hợp cho điều tra chi tiết từng tình huống.

### Dữ liệu tuyệt đối cần thận trọng

Không ghi mật khẩu, access token, session cookie, API key, private key, số thẻ hoặc nội dung cá nhân nhạy cảm ở dạng thô, **kể cả khi log chỉ ở DEBUG**. Log vẫn có thể được gửi đi, lưu trong backup, truy cập bởi người khác hoặc tồn tại sau khi tắt DEBUG.

Tránh log toàn bộ HTTP header/body, câu SQL chứa giá trị bí mật, đối tượng người dùng đầy đủ hoặc payload dịch vụ ngoài. Nếu cần một thuộc tính để điều tra, chỉ giữ phần tối thiểu, che dữ liệu nhạy cảm và tuân thủ chính sách lưu trữ.

Các chuỗi đến từ nguồn không tin cậy có thể chứa ký tự xuống dòng hoặc chuỗi giả mạo bản ghi. Khi thiết kế structured logging hoặc formatter, cần xử lý đúng encoding/escaping để không làm sai lệch cách đọc log.

## 9. DEBUG trong hệ thống nhiều luồng và môi trường phân tán

Ứng dụng Java có thể xử lý nhiều yêu cầu đồng thời. DEBUG từ các thread khác nhau sẽ xen kẽ, ví dụ:

~~~text
DEBUG requestId=A stage=validate
DEBUG requestId=B stage=validate
DEBUG requestId=A stage=price
DEBUG requestId=B stage=price
~~~

Chỉ dựa vào thứ tự các dòng khó biết sự kiện nào thuộc request nào. Vì vậy, nên đưa **request ID hoặc trace ID nhất quán** vào ngữ cảnh; thư viện logging/framework có thể có MDC, ThreadContext hoặc context propagation tương ứng.

- **JUL Logger** không mặc nhiên có cùng API MDC như SLF4J/Logback.
- Nếu dùng thread pool, async task hoặc reactive pipeline, cần truyền ngữ cảnh phù hợp; không giả định ThreadLocal luôn tự đi theo công việc.
- Timestamp cần múi giờ/định dạng rõ ràng; các máy có thể có chênh lệch đồng hồ nên không suy ra trật tự toàn cục tuyệt đối từ một danh sách dòng.
- DEBUG có thể được bật theo service hoặc logger cần điều tra; khi muốn tương quan nhiều dịch vụ, phải thống nhất các ID và cách ghi ngữ cảnh.

Nếu một phần request chậm, **metric** hoặc **distributed trace** giúp xác định nơi cần tìm; DEBUG có thể làm rõ thêm lựa chọn nội bộ và trạng thái tại nơi đó.

## 10. Quy trình bật DEBUG khi điều tra sự cố

Giả sử metric báo timeout tăng ở service checkout, nhưng log INFO chưa đủ để biết nhánh retry nào được chọn.

1. **Xác định phạm vi**: dịch vụ, package/logger, cửa sổ thời gian và mẫu request cần quan sát.
2. **Xác nhận điểm ghi**: các lời gọi DEBUG hiện có có phản ánh nhánh retry và ngữ cảnh cần thiết không; tránh ghi bí mật.
3. **Bật DEBUG có chọn lọc** qua cơ chế cấu hình mà dự án hỗ trợ, giữ các thành phần còn lại ở INFO nếu phù hợp.
4. **Quan sát output thật**: kiểm tra logger, appender, filter, thời gian và ID; không mặc định sự kiện sẽ tới nơi thu thập.
5. **So khớp bằng chứng**: kết hợp DEBUG, log lỗi, metric và trace để xây giả thuyết nguyên nhân; không khẳng định nguyên nhân chỉ từ một dòng riêng lẻ.
6. **Tắt hoặc đưa level trở lại giá trị vận hành** sau khi thu thập đủ dữ liệu và xác minh tác động lưu lượng/chi phí.
7. **Giữ lại công cụ quan sát cần thiết**: nếu cùng một vấn đề thường xuyên khó chẩn đoán, cân nhắc bổ sung metric, tracing hoặc một log có nội dung tốt hơn thay vì để DEBUG toàn hệ thống suốt thời gian dài.

Một số thư viện cho phép thay đổi level lúc chạy, số khác cần nạp lại cấu hình hoặc khởi động lại. Quy trình phải dựa trên cách dự án thực sự cấu hình logging.

## 11. Những lỗi phổ biến với DEBUG

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Gọi JUL Level.DEBUG | Lỗi biên dịch vì JUL không có hằng số đó | Dùng Level.FINE cho mục đích gần tương đương |
| Nhầm DEBUG với trình debugger | Hiểu sai tác động của level log | Phân biệt log sự kiện với breakpoint và xem biến |
| Chỉ chỉnh logger mà quên handler/appender | Không thấy log chi tiết | Kiểm tra cả ngưỡng và bộ lọc ở đích |
| Bật DEBUG toàn ứng dụng quá lâu | Nhiều log, chi phí cao, khó tìm lỗi | Bật theo package/service, thời gian phù hợp |
| Ghi toàn bộ đối tượng hoặc payload | Dữ liệu quá lớn, có thể lộ bí mật | Chỉ ghi trường cần thiết, che dữ liệu nhạy cảm |
| Ghép chuỗi đắt tiền trước khi gọi debug | Vẫn tốn CPU khi DEBUG bị tắt | Dùng placeholder, kiểm tra level và lazy logging phù hợp |
| Dùng DEBUG cho từng vòng lặp không kiểm soát | Khối lượng bản ghi tăng rất nhanh | Log theo giai đoạn, tình huống bất thường hoặc lấy mẫu |
| Ghi DEBUG rồi mong chương trình tự xử lý lỗi | Lỗi vẫn tồn tại, luồng thực thi không đổi | Dùng exception handling và logic nghiệp vụ đúng |
| Không có request ID giữa nhiều thread | Không phân biệt được các sự kiện liên quan | Thêm ngữ cảnh tương quan có kiểm soát |
| Coi DEBUG là nguồn duy nhất đo hiệu năng | Khó theo dõi xu hướng và percentile | Kết hợp metric và tracing |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng dùng SLF4J, logger được cấu hình ở INFO. Lệnh gọi logger.debug(...) có thường xuất không?

**Đáp án:** Không. DEBUG thấp hơn INFO nên thường bị lọc ở logger. Muốn thấy DEBUG cần cấu hình ngưỡng thích hợp và bảo đảm appender/filter nhận nó.

**Câu 2.** Trong Java 17 chỉ dùng java.util.logging, nên gọi Level.DEBUG hay Level.FINE?

**Đáp án:** JUL không có Level.DEBUG; dùng **Level.FINE** cho các thông tin chi tiết gần tương đương mục đích DEBUG.

**Câu 3.** Vì sao LOG.debug("data={}", expensiveSerialize(data)) vẫn có thể tốn CPU khi DEBUG tắt?

**Đáp án:** Java đánh giá **expensiveSerialize(data)** trước khi gọi debug(...). Placeholder không trì hoãn mọi biểu thức đối số. Dùng guard hoặc lazy logging khi phần tính toán tốn kém.

**Câu 4.** Khi cần biết p95 latency và tỷ lệ lỗi trong 5 phút, có nên chỉ bật DEBUG?

**Đáp án:** Không. **Metric** phù hợp hơn cho tỷ lệ và phân bố thời gian; DEBUG bổ sung chi tiết hành vi khi cần tìm nguyên nhân.

**Câu 5.** Có thể ghi access token ở DEBUG vì production đang để INFO không?

**Đáp án:** Không. Level có thể thay đổi, log có thể bị thu thập/lưu ngoài ý muốn. Không ghi bí mật trong bất kỳ mức log nào.

**Câu 6.** Một logger đã bật DEBUG, nhưng không có bản ghi nào xuất hiện ở console. Có chắc mã chưa chạy tới dòng debug không?

**Đáp án:** Chưa chắc. Phải kiểm tra tên logger, ngưỡng appender/handler, filter, cấu hình backend, đích xuất và cơ chế đệm/thu thập.

**Ghi nhớ:** **DEBUG là mức log dành cho chi tiết chẩn đoán**, thường bị tắt trong cấu hình INFO và được bật có chọn lọc khi điều tra. Trong **SLF4J/Logback** dùng debug(...); trong **JUL của JDK** dùng FINE cho mục đích gần tương đương. Hãy ghi những quyết định và trạng thái có ý nghĩa, bảo vệ dữ liệu nhạy cảm và kiểm soát chi phí khi bật log chi tiết.
