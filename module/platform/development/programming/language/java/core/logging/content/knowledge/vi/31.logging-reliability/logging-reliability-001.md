# Mất log trong Java: nguyên nhân, cách phát hiện và bảo vệ chuỗi ghi log

## 1. Mục tiêu bài học

**Mất log (log loss)** là tình huống một sự kiện lẽ ra phải được ghi nhận theo chính sách quan sát của hệ thống nhưng **không đến được điểm lưu trữ hoặc điểm truy vấn cần thiết**. Đây là vấn đề về **độ tin cậy logging**, không chỉ về số dòng xuất hiện trên terminal.

Ví dụ: ứng dụng đã phát sinh sự kiện thanh toán thất bại, logger đã nhận lời gọi ERROR, nhưng dashboard không có record tương ứng. Cần xác định event đã bị lọc ở JVM, bị rơi khi hàng đợi đầy, còn nằm trong bộ nhớ lúc JVM chết, không gửi được đến collector, bị loại khi index hay đơn giản là đang được tìm ở sai nơi.

Sau bài này bạn sẽ:

- Phân biệt **không tạo log, bị lọc có chủ đích, bị drop ngoài ý muốn, bị trễ và không tìm thấy log**.
- Hiểu các mốc của một event từ mã Java đến hệ thống lưu trữ và các giới hạn về độ bền dữ liệu.
- Nắm nguyên nhân thường gặp trong JUL, SLF4J/Logback, Log4j2, async logging, file, container và collector.
- Thực hành một chương trình Java 17 tái hiện **queue full → mất event** và so sánh với **backpressure + drain**.
- Thiết kế kiểm thử, metric, cảnh báo và quy trình điều tra khi nghi ngờ mất log.
- Chọn đúng mức bảo đảm cho log vận hành, log lỗi và sự kiện audit/kinh doanh quan trọng.

## 2. Trước tiên, xác định thế nào là "mất"

Không phải cứ thiếu một dòng log trong kết quả tìm kiếm là hệ thống đã làm mất dữ liệu. Có ít nhất sáu tình huống cần phân biệt:

| Tình huống | Bản chất | Có nhất thiết là mất log? |
| --- | --- | --- |
| Code chưa chạy đến lời gọi logger | Không phát sinh sự kiện. | Không. Điều tra đường thực thi nghiệp vụ. |
| DEBUG bị loại vì logger ở INFO | **Filtering** theo chính sách đã cấu hình. | Không, nếu đó là hành vi mong muốn. |
| Event được nhận nhưng queue đầy và drop | **Loss** ở bước enqueue / async appender. | Có, nếu chính sách yêu cầu giữ event đó. |
| Event đang nằm trong buffer, chưa export | **Delay / backlog**. | Chưa kết luận; có nguy cơ mất nếu bị dừng hoặc hết hạn. |
| Event đã ở storage nhưng truy vấn sai khoảng thời gian, tenant, index hoặc quyền | **Không quan sát thấy**. | Có thể không mất; cần xác minh ở tầng storage. |
| Event bị xóa sau retention hoặc sampling được phê duyệt | **Loại bỏ theo chính sách**. | Không phải lỗi kỹ thuật nếu vẫn đáp ứng hợp đồng dữ liệu. |

Trong một hệ thống thật, cần định nghĩa rõ **hợp đồng logging**: loại sự kiện nào được tạo, nơi nào phải nhận, độ trễ tối đa, retention và mức mất mát cho phép. Không có hợp đồng này, cùng một dòng bị thiếu có thể được coi là bình thường ở DEBUG nhưng là sự cố nghiêm trọng với audit.

**Ví dụ:** nếu production chủ động tắt TRACE, thiếu dòng TRACE không phải một sự cố. Nhưng nếu application đã phát sự kiện ERROR vào logger, backend được cấu hình phải gửi nó tới collector và event biến mất không rõ lý do, đó là vấn đề cần điều tra.

## 3. Chuỗi vận chuyển log: có thể mất ở đâu?

Một event điển hình qua các ranh giới sau:

~~~text
Business event xảy ra
    │
    ▼
Ứng dụng gọi logger?
    │
    ▼
Logger / filter / level có chấp nhận?
    │
    ▼
Logging backend tạo event
    │
    ├──── Đồng bộ ────────┐
    │                     │
    └──── Async queue ────┤
                          ▼
                   Appender / Handler
                          │
                          ▼
                   Console / File / Socket
                          │
                          ▼
             Runtime / Agent / Collector
                          │
                          ▼
                  Queue / Retry / Export
                          │
                          ▼
                 Storage / Index / Query
~~~

Mỗi mũi tên là một **ranh giới giao nhận**. "Logger.info() đã trả về" không chứng minh toàn bộ chuỗi đã thành công.

| Điểm kiểm tra | Câu hỏi | Nhóm lỗi thường gặp |
| --- | --- | --- |
| Business code | Nhánh code có chạy không? | Điều kiện if, exception/return sớm, sự kiện không thực sự xảy ra. |
| Logger API | Có provider/backend đúng không? | SLF4J không có provider, logger sai tên, level không cho qua. |
| Filter / configuration | Event được phép đi tiếp không? | Threshold, marker filter, custom filter, additivity, routing sai. |
| Async queue | Event có thực sự được nhận vào queue? | Queue full, discard policy, sampling, backpressure timeout. |
| Appender / handler | Backend ghi đích thành công không? | I/O lỗi, file không có quyền, disk full, formatter/encoder exception. |
| Process / container | Log đã được đưa ra stdout/file trước khi process chết chưa? | JVM crash, SIGKILL, OOM kill, buffer chưa drain. |
| Collector | Có nhận và xử lý record không? | Agent crash, receiver/pipeline tắt, parser fail, batching, retry hết hạn. |
| Storage | Có lưu và index record không? | Quota, index rejection, retention, sai tenant, trường timestamp không hợp lệ. |
| Truy vấn | Có đang tìm đúng nơi/đúng thời gian không? | Timezone, clock skew, index pattern, quyền truy cập, filter sai. |

Đừng chỉ nhìn log application. Một lỗi ở exporter hoặc storage hoàn toàn có thể xảy ra sau khi ứng dụng đã ghi thành công ra stdout.

## 4. Những nguyên nhân mất log trong chính ứng dụng Java

### 4.1. Mức log và filter loại sự kiện

JUL có các level như SEVERE, WARNING, INFO, FINE; Logback/Log4j2 dùng ERROR, WARN, INFO, DEBUG, TRACE và các level riêng tùy backend. Nếu cấu hình root INFO, lời gọi DEBUG thường không tạo một event được chấp nhận. Đây là **lọc hợp lệ**, không phải queue đã làm mất dữ liệu.

Các trường hợp cần kiểm tra:

- Logger con có effective level thấp hơn/cao hơn root dự kiến.
- Logger level cho phép sự kiện nhưng handler/appender/filter tiếp tục chặn.
- Một custom filter loại event vì marker, message hoặc metadata.
- Tên logger không khớp package đã cấu hình.
- Config của dev/test và production khác nhau, profile không đúng.
- Event được tạo nhưng logger routing không có appender đích phù hợp.

**Phân biệt quan trọng:** nếu chính sách yêu cầu **WARN trở lên**, INFO bị lọc không phải lỗi. Nếu yêu cầu giữ ERROR nhưng custom filter loại ERROR do cấu hình sai, đây là **sự kiện bị mất ngoài ý muốn**.

### 4.2. SLF4J thiếu provider hoặc backend sai

SLF4J là facade/API, không phải nơi ghi log. Với SLF4J 2.x, nếu không có provider tương thích trên runtime classpath, SLF4J có thể cảnh báo và dùng NOP logger: lời gọi logger không tạo đầu ra hữu ích. Các ứng dụng có nhiều backend hoặc bridge xung đột cũng có thể định tuyến khác dự kiến.

Kiểm tra runtime dependencies, cảnh báo startup và provider được chọn. Đừng chỉ nhìn thấy dependency slf4j-api rồi kết luận hệ thống đã có FileAppender hoặc ConsoleAppender.

### 4.3. Không có appender/handler thực sự ghi

Một logger có thể chấp nhận event nhưng không có đích tiêu thụ. Ví dụ Logback/Log4j2 dùng additivity=false cho một package mà lại không gắn appender, hoặc JUL đặt useParentHandlers(false) rồi không gắn handler riêng. Kết quả: record không tới root appender/handler và cũng không có sink riêng.

Ngược lại, gắn cùng một appender ở nhiều cấp có thể tạo **log trùng**. Mất và trùng là hai lỗi khác nhau của routing; cả hai đều ảnh hưởng chất lượng điều tra sự cố.

### 4.4. Exception trong đường ghi log

Lỗi formatter, encoder, filesystem, network appender hoặc cấu hình layout có thể ngăn event được ghi. Một số backend báo lỗi bằng status logger hoặc error handler, không ném exception vào luồng nghiệp vụ. Vì thế việc ứng dụng tiếp tục chạy bình thường **không chứng minh logger vẫn hoạt động**.

Trong JUL, Handler có thể báo qua ErrorManager; với Logback/Log4j2, xem trạng thái nội bộ và log khởi động. Khi log pipeline đang lỗi, đừng phụ thuộc **chỉ** vào chính log pipeline đó để phát cảnh báo.

## 5. Async logging và queue full: điểm rơi phổ biến

Async logging tách luồng gọi logger khỏi luồng ghi. Event thường được đưa vào queue/buffer, rồi worker chuyển đến appender. Lợi ích là giảm độ trễ caller trong tình huống queue còn khả năng nhận. Đổi lại, event có thể chỉ tồn tại trong **RAM** trước khi được ghi xuống đích.

~~~text
Producer:  8.000 event/s ──┐
                          ▼
                    Bounded queue ── Worker: 5.000 event/s
                          │
                          ▼
               Backlog tăng 3.000 event/s
                          │
                          ▼
                      Queue đầy
                          │
       ┌──────────────────┼─────────────────┐
       ▼                  ▼                 ▼
     Block               Drop          Fallback
  caller chờ         bỏ một số event    ghi theo cách khác
~~~

Với tốc độ ví dụ ở trên, nếu khoảng tải kéo dài 4 giây và worker duy trì 5.000 event/s, backlog tăng **xấp xỉ (8.000 − 5.000) × 4 = 12.000 event**, chưa tính scheduling, sự biến thiên kích thước event và năng lực thực của sink. Queue nhỏ hơn có thể đầy trước khi burst kết thúc. Queue lớn hơn hấp thụ được burst lâu hơn, nhưng giữ nhiều dữ liệu trong RAM và tăng thời gian cần để drain khi shutdown.

Ba nhóm chính sách khi queue đầy:

| Chính sách | Hành vi | Ảnh hưởng độ tin cậy |
| --- | --- | --- |
| **Block / backpressure** | Caller đợi có chỗ trống. | Hạn chế mất event do full queue nhưng tăng request latency, có thể gây nghẽn. |
| **Drop / discard** | Bỏ một số event, đôi khi theo level. | Giữ application không bị chặn nhưng mất thông tin; cần đếm và cảnh báo. |
| **Fallback** | Một số backend chuyển sang xử lý đồng bộ hoặc hướng khác. | Có thể tránh bỏ event ở một số nhánh nhưng tăng latency, phức tạp thứ tự. |

Không có chính sách nào tự bảo đảm chống được mất log do JVM crash, disk lỗi hoặc collector không nhận. Đặc biệt, **queue.put thành công chỉ bảo đảm event đã được nhận vào queue trong bộ nhớ**, chưa chứng minh event bền vững.

### 5.1. Logback AsyncAppender

Logback Classic cung cấp AsyncAppender và các thuộc tính:

- **queueSize**: sức chứa hàng đợi.
- **discardingThreshold**: ngưỡng kích hoạt loại bỏ một số sự kiện mức thấp theo chính sách của AsyncAppender. Cơ chế mặc định có thể loại TRACE/DEBUG/INFO khi queue gần đầy.
- **neverBlock**: nếu bật true, ứng dụng tránh chờ queue đầy nhưng có thể bỏ message; false thường block khi đầy.
- **maxFlushTime**: thời gian tối đa chờ xử lý event còn tồn lúc dừng appender; nếu quá hạn, record chưa xử lý có thể bị bỏ.

Ví dụ minh họa trong dự án đã dùng Logback, đoạn **logback.xml** sau ưu tiên **không cố ý loại event do cơ chế discard của AsyncAppender**, chấp nhận blocking và giới hạn thời gian chờ shutdown:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Giải thích:

1. **discardingThreshold=0** vô hiệu hóa cơ chế loại sự kiện mức thấp theo ngưỡng gần đầy của AsyncAppender này; không loại bỏ những rủi ro mất ở các tầng khác.
2. **neverBlock=false** cho phép caller chờ khi queue đầy. Nếu sink không theo kịp, latency nghiệp vụ vẫn có thể tăng.
3. **maxFlushTime=5000** cho worker khoảng 5 giây để hoàn thành khi dừng context. Nếu còn backlog sau khoảng chờ, log vẫn có thể mất; đặt thời gian này theo giới hạn shutdown thực tế.
4. **FILE** phụ thuộc filesystem và quyền ghi; AsyncAppender không tự sửa được lỗi disk full, file permission hoặc container bị kill.
5. Root chỉ gắn **ASYNC**, tránh vô tình gắn thêm FILE trực tiếp ở root và tạo hai đường ghi trùng.

Đây không phải cấu hình bảo đảm lưu trữ bền vững tuyệt đối. Production cần cân nhắc rolling/retention và collector. Các mặc định/cú pháp có thể khác phiên bản Logback; đọc tài liệu và thử với bản đang chạy.

### 5.2. Log4j2 Async Logger/Async Appender

Log4j2 có **Async Appender** và **Async Logger**; cơ chế triển khai khác nhau, nhưng đều có thể chịu tình huống sinh log nhanh hơn khả năng appender/sink. Với Log4j2 hiện đại, thuộc tính **log4j2.asyncQueueFullPolicy** có các lựa chọn điển hình:

- **Default**: chờ khi không còn chỗ enqueue theo chính sách mặc định; không đồng nghĩa không thể mất do sự cố khác.
- **Discard**: khi queue đầy, bỏ các event có severity không vượt quá ngưỡng **log4j2.discardThreshold**; ngưỡng minh họa thông dụng là INFO.

Không thể kết luận “ERROR không bao giờ mất” chỉ vì một chính sách drop ưu tiên giữ level cao. Event vẫn có thể mất sau enqueue, lúc shutdown, ở exporter hoặc storage. Đọc chính sách queue-full theo **phiên bản Log4j2** đang dùng, kiểm tra status logger và đo dưới sustained overload.

## 6. Ví dụ Java 17 độc lập: queue đầy làm rơi event

Chương trình sau cố ý dùng **ArrayBlockingQueue** sức chứa 2 và gửi 3 event **trước khi worker đọc**. Khi dùng **offer**, event thứ ba bị từ chối mà không chặn caller. Phần thứ hai dùng **put** cùng sức chứa và worker chạy nền: caller có thể phải chờ, nhưng cả ba event được xử lý trước khi chương trình kết thúc.

Đây là **mô hình học** về queue/backpressure, không phải một thư viện logging production. Worker ghi kết quả vào một danh sách trong RAM thay vì disk, để minh họa rõ **drop ở queue** mà không nhầm với lỗi filesystem.

Lưu thành **LostLogsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class LostLogsDemo {
    private static final String STOP = "<STOP>";

    public static void main(String[] args) throws InterruptedException {
        // Phan 1: thu ghi 3 su kien truoc khi worker bat dau.
        BlockingQueue<String> dropping = new ArrayBlockingQueue<>(2);
        List<String> dropWritten = new ArrayList<>();
        int attempted = 0;
        int accepted = 0;

        for (String event : List.of("A", "B", "C")) {
            attempted++;
            if (dropping.offer(event)) {
                accepted++;
            }
        }

        final int acceptedCount = accepted;
        Thread dropWorker = new Thread(() -> {
            try {
                for (int i = 0; i < acceptedCount; i++) {
                    dropWritten.add(dropping.take());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "drop-worker");
        dropWorker.start();
        dropWorker.join();

        System.out.println("DROP: attempted=" + attempted
                + " accepted=" + accepted
                + " dropped=" + (attempted - accepted));
        System.out.println("DROP: written=" + dropWritten);

        // Phan 2: block producer thay vi loai su kien khi queue day.
        BlockingQueue<String> blocking = new ArrayBlockingQueue<>(2);
        List<String> blockWritten = new ArrayList<>();

        blocking.put("A");
        blocking.put("B");

        Thread blockWorker = new Thread(() -> {
            try {
                while (true) {
                    String event = blocking.take();
                    if (STOP.equals(event)) {
                        break;
                    }
                    blockWritten.add(event);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "block-worker");
        blockWorker.start();

        blocking.put("C");       // Co the doi den khi worker lay event.
        blocking.put(STOP);      // Bao worker dung sau khi xu ly C.
        blockWorker.join();      // Chi in ket qua sau khi worker da dung.

        System.out.println("BLOCK: written=" + blockWritten);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**, không cần dependency bên ngoài:

~~~bash
javac LostLogsDemo.java
java LostLogsDemo
~~~

**stdout xác định** khi chạy bình thường:

~~~text
DROP: attempted=3 accepted=2 dropped=1
DROP: written=[A, B]
BLOCK: written=[A, B, C]
~~~

Giải thích tại sao kết quả ổn định:

- Ở phần **DROP**, worker chỉ khởi động **sau khi** ba lần offer kết thúc, nên queue sức chứa 2 chắc chắn chỉ nhận A và B; C bị từ chối.
- Phần **BLOCK** có worker bắt đầu trước khi producer gửi C và sentinel STOP. Nếu queue còn đầy, put(C) sẽ chờ; worker lấy event sẽ giải phóng chỗ. FIFO bảo đảm worker nhận A, B, C rồi STOP.
- **join()** bảo đảm main chỉ đọc hai danh sách sau khi worker đã xử lý xong nên không phụ thuộc thứ tự in của các thread.
- Sentinel STOP chỉ được tạo bởi chương trình; nếu message thực tế có thể trùng sentinel, phải dùng kiểu event riêng hoặc cơ chế shutdown an toàn hơn.
- Mã không mô phỏng crash, fsync, retry, disk hay collector. Phần BLOCK cho thấy không làm rơi do queue full trong tình huống bình thường, **không chứng minh durability**.

Thử đổi **offer** ở phần DROP thành **put** khi worker **chưa được khởi động**: với queue sức chứa 2, lệnh put thứ ba có thể chờ mãi vì không ai tiêu thụ. Đây là một nguy cơ của blocking policy khi không có consumer hoặc consumer đã chết. Trong logging framework thực tế, cần theo dõi sức khỏe worker và bounded shutdown, không dựa duy nhất vào “never drop”.

## 7. Flush, close và shutdown không đồng nghĩa đã lưu bền vững

Trong ứng dụng Java, có nhiều mức hoàn thành:

~~~text
Event được tạo
    ↓
Vào async queue trong RAM
    ↓
Worker lấy event
    ↓
Appender.write() / stream.write()
    ↓
Flush buffer ở lớp thư viện/OS
    ↓
Filesystem/collector nhận dữ liệu
    ↓
Lưu bền vững, index và cho phép query
~~~

**Flush** thường có nghĩa đẩy dữ liệu khỏi bộ đệm tương ứng của tầng gọi, không nhất thiết đã ghi vật lý xuống disk hoặc đã được backend trung tâm lưu an toàn. **Close** thường flush và giải phóng tài nguyên của stream/handler, nhưng vẫn không là bảo đảm end-to-end. Với JUL FileHandler, mỗi record được flush theo hành vi triển khai được JDK mô tả, song crash của OS/disk hoặc log shipper vẫn có thể gây thất lạc sau đó.

### 7.1. Graceful shutdown

Khi dịch vụ dừng bình thường:

1. Ngừng nhận request/tác vụ mới, hoặc kiểm soát giai đoạn sinh log mới.
2. Hoàn tất tác vụ đang chạy; nếu có worker async, để nó drain queue trong thời gian cho phép.
3. Gọi cơ chế stop/close của logging backend đúng lifecycle framework.
4. Chờ khoảng thời gian cần thiết trước khi process kết thúc.
5. Theo dõi số event còn trong queue, thời gian flush và lỗi sink nếu backend có telemetry.

**Không** gọi System.exit đột ngột để “làm mới logger” giữa một request. Trong Spring Boot, để application context và logging system đóng theo lifecycle của framework thay vì tự đóng backend giữa lúc các thread còn sử dụng.

### 7.2. Những tình huống shutdown không cứu được

- **SIGKILL**, Runtime.halt, mất điện hoặc JVM crash nghiêm trọng có thể bỏ qua shutdown hook.
- **OOM kill** hoặc container bị kết thúc cưỡng bức có thể hủy queue chưa drain.
- Shutdown grace period quá ngắn so với backlog.
- Sink bị treo, queue không thể drain, hoặc worker log gặp lỗi I/O.
- File log mới nằm trên storage tạm/ephemeral và bị xóa khi container thay thế.

Vì vậy **maxFlushTime lớn** hay **shutdown hook** chỉ giảm nguy cơ, không thay thế chiến lược durability nếu sự kiện có yêu cầu bảo toàn cao.

## 8. File log, rotation và hệ điều hành

Ở tầng file, log có thể bị mất hoặc không quan sát được bởi:

- **Không có quyền ghi** vào thư mục, đĩa đầy, quota đầy, file handle hỏng.
- FileHandler/appender tạo file ở **working directory khác dự kiến**.
- Appender ghi đúng file, nhưng agent chỉ đọc stdout hoặc một glob khác.
- **Rotation** đổi tên file rồi xóa/archive trước khi shipper đọc hết, hoặc shipper không theo kịp.
- File được ghi trong **container filesystem tạm thời** và mất khi pod/container bị thay.
- Log file bị truncate, xóa hoặc ghi đè do cấu hình append=false.
- Parser/shipper có giới hạn kích thước dòng và bỏ bớt event rất dài.

**Logback RollingFileAppender**, JUL FileHandler rotation và các công cụ rotation bên ngoài có cách phối hợp khác nhau. Không cấu hình hai cơ chế cùng tự xoay một file mà chưa hiểu sự tương tác; rủi ro là ghi sai inode, thiếu đoạn cuối hoặc có file đã xoá khi shipper chưa đọc.

Trong container, nhiều kiến trúc ưu tiên ghi **stdout/stderr** rồi cho nền tảng thu thập. Nhưng stdout cũng có buffer/đường thu riêng; Docker/Kubernetes runtime, log driver và collector có thể bị quá tải hoặc cấu hình retention khác nhau. Chuyển sang console không tự biến log thành “không thể mất”.

### Đường dẫn tương đối và stdout/stderr

Ví dụ ứng dụng ghi **logs/application.log** trong IDE có thể tạo file ở thư mục project; khi chạy service, đường dẫn đó có thể trỏ sang thư mục làm việc khác. JUL ConsoleHandler thường ghi **System.err**, trong khi appender console của backend khác có thể chọn stdout. Tìm log ở sai stream cũng gây cảm giác log đã biến mất.

## 9. Log pipeline phân tán: collector, retry và storage

Một pipeline thường gồm agent/receiver, processor, exporter và nơi lưu. Ví dụ OpenTelemetry Collector có các thành phần được cấu hình theo pipeline; **khai báo một receiver nhưng không gắn nó vào service pipeline** không làm receiver thực sự xử lý dữ liệu.

Các nguyên nhân thường gặp:

| Tầng | Ví dụ sự cố | Hậu quả |
| --- | --- | --- |
| Agent/file tailer | Sai path, thiếu permission, không theo được rotation. | Một số dòng chưa từng được agent đọc. |
| Receiver | Sai protocol/port, pipeline chưa bật, quá tải. | Collector không nhận hoặc từ chối record. |
| Processor | Filter/drop/sampling, parser lỗi, memory protection. | Record bị loại hoặc chuyển đổi ngoài dự kiến. |
| Queue | Hết sức chứa, không có persistent storage, process chết. | Record chưa export có thể mất. |
| Exporter | Network lỗi, auth fail, retry hết hạn, backend chậm. | Record tồn đọng rồi có thể bị drop. |
| Storage/indexer | Quota, reject, TTL/retention, lỗi mapping/timestamp. | Không query được hoặc dữ liệu bị bỏ. |

**Retry** giảm nguy cơ thất lạc do lỗi tạm thời nhưng không miễn phí: nếu retry quá lâu, queue đầy; nếu retry quá ngắn, lỗi mạng ngắn có thể gây drop. Nếu backend đã nhận event nhưng ACK bị mất và exporter gửi lại, có thể xảy ra **duplicate**. Tùy thiết kế, hệ thống có thể có cơ chế at-least-once, best-effort hoặc tương đương; đừng tự khẳng định end-to-end exactly-once.

OpenTelemetry Collector có hướng dẫn sử dụng **sending queue, retry_on_failure và tùy chọn persistent storage** cho exporter phù hợp. Cần kiểm tra phiên bản và exporter thực tế: bật queue trong RAM giúp chịu outage ngắn nhưng không bảo toàn queue qua crash; bật persistent queue cũng phụ thuộc disk còn hoạt động và chưa vượt quota.

**Những metric đáng kiểm tra** nếu dùng collector hỗ trợ chúng: queue size/capacity, enqueue failed log records, receiver accepted/refused, exporter sent/send failed và lỗi retry. Tên metric cụ thể có thể thay đổi theo bản Collector/component; tra tài liệu và quan sát telemetry thực tế.

## 10. Không tìm thấy log chưa chắc đã mất

Một event có thể đã được lưu nhưng không xuất hiện trong dashboard vì:

1. **Khoảng thời gian tìm kiếm sai:** event timestamp khác ingest timestamp; timezone không giống nhau; clock skew làm record lọt ra ngoài cửa sổ truy vấn.
2. **Tìm sai log stream/index/tenant:** ứng dụng gửi theo environment, service hoặc namespace khác.
3. **Logger/trace fields khác kỳ vọng:** traceId chưa được propagate qua thread pool; tìm traceId sẽ không thấy event không có field này, dù record vẫn ở storage.
4. **Index lag:** record đã được nhận nhưng chưa queryable.
5. **Retention:** event đã từng có nhưng đã bị xóa theo TTL.
6. **Quyền truy vấn:** tài khoản không có quyền xem một tenant/index nhất định.
7. **Parser thay đổi fields:** event có message nhưng field level/logger_name đổi tên hoặc nằm trong raw payload.
8. **Truncation/chunking:** message lớn bị chia hoặc cắt, nên truy vấn một chuỗi đầy đủ thất bại.

Một quy trình chẩn đoán hữu ích:

~~~text
Không thấy event trong dashboard
      │
      ├─ Tìm theo service + event_id + cửa sổ thời gian rộng hơn?
      ├─ Tìm ở raw stream/ingest timestamp thay vì chỉ parsed fields?
      ├─ Agent có đọc được file/stdout chứa event?
      ├─ Collector có nhận và export record?
      └─ Storage có xác nhận ingest/index và quyền truy vấn?
~~~

Chỉ kết luận mất khi bằng chứng chỉ ra event phải có nhưng **không tồn tại tại mốc đã cam kết** hoặc bị drop ở tầng được xác nhận. Không nên chỉ dựa vào một truy vấn âm tính.

## 11. Phát hiện mất log bằng telemetry và đối chiếu

### 11.1. Theo dõi các mốc nhận/chuyển sự kiện

Một mô hình đo:

~~~text
Produced → Accepted → Enqueued → Written → Collected → Indexed
    P          A          Q          W          C          I
~~~

Các biến ở đây là **mốc khái niệm**, không phải metric mà mọi thư viện đều cung cấp. Mỗi mốc cần được đo một cách có thể kiểm tra:

- **Produced**: code thực sự gọi logging hoặc tạo event nghiệp vụ.
- **Accepted**: logger/filters chấp nhận; các level bị lọc theo policy được thống kê riêng nếu cần.
- **Enqueued**: event được đưa vào async queue.
- **Written**: appender báo thành công tại điểm mà backend định nghĩa.
- **Collected**: agent/collector nhận record.
- **Indexed**: backend lưu/index để truy vấn theo SLA.

Không trừ máy móc **P − I** rồi tuyên bố đó là số log mất. Các tầng là bất đồng bộ, có cửa sổ thời gian, batch/retry, duplicate và sampling. Cần chuẩn hóa cùng phạm vi event, cùng cửa sổ và có độ trễ bù phù hợp.

### 11.2. Metric và cảnh báo cần có

| Metric hoặc tín hiệu | Giá trị |
| --- | --- |
| Async queue occupancy / capacity | Phát hiện backlog và nguy cơ queue full. |
| Dropped/discarded event count theo level/reason | Biết log bị loại, đánh giá mức nghiêm trọng. |
| Enqueue block duration | Đo tác động lên latency nghiệp vụ khi không drop. |
| Appender error count/status | Phát hiện sink I/O lỗi, encoder/rotation thất bại. |
| Collector accepted/refused, exporter send failed | Định vị lỗi giữa ingest và export. |
| Retry queue size, age, oldest item | Phát hiện outage kéo dài hơn khả năng chịu đựng. |
| Process restarts / OOM kills / shutdown duration | Liên hệ với sự kiện còn trong RAM khi dừng. |
| Disk usage, quota, file permission errors | Phát hiện file log không ghi được. |
| Delay giữa event timestamp và ingest/index timestamp | Phân biệt log đến trễ với log mất. |

Đặt cảnh báo theo **tỉ lệ và thời gian**, ví dụ dropped WARN/ERROR khác 0 trong cửa sổ được phê duyệt, retry queue >80% trong 5 phút, collector exporter failures kéo dài, hoặc log ingestion bất ngờ rơi về 0 trong lúc traffic vẫn bình thường. Các ngưỡng chỉ là ví dụ: phải hiệu chỉnh theo workload và SLO.

**Lưu ý:** nếu hệ thống logging hỏng, cảnh báo chỉ được ghi bằng chính logger có thể không đến nơi. Nên có metric/health check hoặc kênh giám sát độc lập với đường ghi log đang theo dõi.

### 11.3. Event ID và kiểm tra completeness

Với một tập event kiểm thử xác định, gán **event_id** duy nhất và cho từng event đi qua toàn bộ pipeline. Sau khi chờ đủ ingestion delay, đếm:

- Bao nhiêu ID được tạo theo test.
- Bao nhiêu ID có mặt ở sink chính.
- ID nào thiếu (gap) và ID nào có nhiều hơn một bản (duplicate).
- Missing/duplicate có trùng với overload, restart hay collector error không.

Test phải giới hạn dữ liệu thử nghiệm, không dùng secret hoặc PII thật. Nếu hệ thống có sampling/drop có chủ đích, chỉ đưa các event được **cam kết phải giữ** vào phép so khớp.

## 12. Kiểm thử sự cố chủ động (failure injection)

| Tình huống thử | Mục đích | Kết quả cần xác minh |
| --- | --- | --- |
| Bình thường, queue thoáng | Thiết lập baseline. | Log đúng level/đích; độ trễ trong SLO. |
| Burst ngắn vượt tốc độ sink | Kiểm tra buffering. | Queue tăng và hồi phục; biết chính sách khi đầy. |
| Overload kéo dài | Kiểm tra giới hạn thực. | Block/drop/fallback đúng policy, không xảy ra mất âm thầm. |
| Dừng graceful khi còn backlog | Kiểm tra drain. | Event còn lại xử lý trong grace period; có telemetry. |
| Termination cưỡng bức trong test | Hiểu giới hạn RAM queue. | Nhận diện log có thể mất, không mặc định zero-loss. |
| Disk full / đường dẫn không có quyền ghi | Kiểm tra appender error. | Có tín hiệu lỗi và hành vi fallback đúng thiết kế. |
| Collector/network offline rồi phục hồi | Kiểm tra retry. | Không drop sớm ngoài chính sách; queue hồi phục. |
| Collector crash không persistent queue | Kiểm tra durability. | Có thể mất phần còn trong RAM; số lượng được đo. |
| Rotation/retention dưới tải | Kiểm tra file tailer. | Không bỏ sót đoạn trước/sau rotate ngoài chính sách. |
| Truy vấn sai timezone/index | Tránh chẩn đoán nhầm. | Có thể tìm lại event qua raw timestamp/sink đúng. |
| Nhiều producer/multiple workers | Kiểm tra ordering. | Không giả định thứ tự toàn cục; event_id vẫn truy vết được. |
| Log message cực dài | Kiểm tra truncation/parser. | Biết giới hạn kích thước và xử lý record lớn. |

Chỉ gây lỗi trong môi trường thử nghiệm được cô lập. Không tắt collector hoặc làm đầy disk production để "thử". Dùng dữ liệu giả, gắn test run ID và dọn log thử theo retention.

## 13. Khắc phục theo vị trí phát hiện lỗi

### 13.1. Nếu mất từ logger/filter

- Kiểm tra effective level của logger và handler/appender/filter.
- Xác định backend/provider thực tế, không chỉnh XML của một thư viện không được runtime dùng.
- Kiểm tra additivity/useParentHandlers và có appender thực sự.
- Sửa policy ở đúng package/logger, không tăng root DEBUG vô hạn.
- Viết test cho các event WARN/ERROR cam kết phải được giữ.

### 13.2. Nếu mất ở async queue

- Đo tốc độ producer, throughput consumer, queue occupancy, dropped count.
- Kiểm tra neverBlock, discardingThreshold, queue-full policy và số lượng worker theo backend.
- Nếu ưu tiên giữ event, chọn backpressure có giới hạn chấp nhận được; theo dõi latency.
- Giảm volume log ở nguồn: bỏ message dư thừa, sampling có chủ đích, đặt level hợp lý; không dùng queue vô hạn.
- Cải thiện sink throughput hoặc pipeline, thay vì chỉ tăng queue size.
- Quản lý lifecycle startup/shutdown và kiểm thử stop dưới backlog.

### 13.3. Nếu mất tại file/console

- Xác nhận đường dẫn, filesystem, quyền ghi, disk/quota, working directory.
- Xem status/error handler của backend.
- Kiểm tra rotation, retention và file shipper có theo kịp.
- Kiểm tra stdout/stderr và runtime log driver.
- Bảo đảm không đóng appender khi tác vụ vẫn đang sử dụng nó.

### 13.4. Nếu mất ở collector/storage

- Kiểm tra receiver pipeline, parser/filter, queue/retry settings và exporter errors.
- Xác nhận endpoint, auth, network, namespace, index và mapping.
- Theo dõi tình trạng collector quá tải và mức sử dụng bộ nhớ/disk.
- Xem chính sách retry và persistent queue khi cần chịu outage; hiểu rõ trường hợp vẫn có thể drop.
- Dùng event_id để xác định mất ở biên nào thay vì chuyển trách nhiệm qua các nhóm chỉ dựa vào log vắng mặt.

## 14. Mức bảo đảm cần thiết theo loại sự kiện

Không phải mọi log có cùng giá trị nghiệp vụ. Một gợi ý phân loại:

| Loại dữ liệu | Chính sách phù hợp |
| --- | --- |
| TRACE/DEBUG chi tiết | Có thể cho phép sampling/drop nếu vận hành chấp thuận; phải minh bạch. |
| INFO vận hành | Đặt mục tiêu completeness và latency phù hợp; giám sát backlog/drop. |
| WARN/ERROR | Ưu tiên giữ cao hơn; theo dõi loss hoặc sink failure, không coi mọi ERROR là tự động bền vững. |
| Security audit | Cần chính sách kiểm soát truy cập, tính toàn vẹn và retention theo quy định; không phụ thuộc queue RAM thông thường. |
| Event ảnh hưởng tiền, giao dịch, thay đổi trạng thái | Lưu ở nguồn dữ liệu nghiệp vụ có tính bền vững/atomicity phù hợp; log chỉ là một góc quan sát. |

**Quan trọng:** nếu việc **không mất event** là yêu cầu nghiệp vụ cứng, không nên dựa duy nhất vào logger. Ví dụ một đơn hàng đã ghi thành công nhưng sự kiện gửi downstream bắt buộc phải được giao: sử dụng bảng sự kiện bền vững, transactional outbox hoặc cơ chế event store/message broker có acknowledgement, retry, idempotency và quy tắc xử lý lỗi rõ ràng.

Một thiết kế phổ biến:

~~~text
Transaction nghiệp vụ
      │
      ├── cập nhật trạng thái trong DB
      └── ghi outbox event trong cùng transaction
                    │
                    ▼
            Worker đọc outbox
                    │
                    ▼
          Publish + ACK/retry
                    │
                    ▼
          Consumer idempotent
~~~

Ngay cả mô hình này cần xử lý retry/duplicate và lỗi hạ tầng, nhưng nó đưa cam kết giao dữ liệu quan trọng ra khỏi đường logging best-effort. Không dùng một dòng INFO trong file làm bằng chứng duy nhất cho sự kiện tài chính hoặc audit có nghĩa vụ lưu giữ.

## 15. Tình huống điều tra: log ERROR biến mất sau deploy

Một dịch vụ Java vừa deploy có tăng tỷ lệ lỗi HTTP 500 nhưng dashboard không thấy ERROR tương ứng.

### Bước 1: kiểm tra tín hiệu độc lập

Xác nhận HTTP 500 thực sự tăng qua metric request (không chỉ dựa vào log). Tìm một request có request ID/trace ID thử nghiệm. Kiểm tra code path có phát sự kiện ERROR hay không.

### Bước 2: kiểm tra trong JVM

- Backend/provider sau deploy có thay đổi không?
- Effective level ở logger class/package là gì?
- Có filter mới, additivity=false hoặc appender bị bỏ khỏi root?
- Async appender có drop hay backlog không?
- File/console có error status không?

### Bước 3: kiểm tra process

Deployment có restart/OOM kill không? Container có ghi stdout/stderr đúng nơi collector đọc không? Appender file có đang ghi trong ephemeral directory không? Shutdown grace period có đủ drain backlog không?

### Bước 4: kiểm tra collector và storage

Collector có tăng rejected/enqueue failed/send failed không? Retry queue có đầy? Pipeline exporter có bật? Backend có trả lỗi auth/quota? Tìm theo ingest timestamp và raw stream, không chỉ theo traceId hoặc event timestamp.

### Bước 5: khoanh vùng và cải thiện

Nếu mất do queue full, có thể sửa queue policy hoặc tăng sink capacity; nếu mất do cấu hình, sửa đúng backend/route; nếu không mất mà tìm sai nơi, sửa trường/index/query. Sau khi phục hồi, bổ sung test hoặc metric tại **biên đã hỏng** để phát hiện sớm trong lần deploy sau.

Tránh bật DEBUG toàn production để tìm một event ERROR: việc đó có thể làm tăng tải logging và khiến queue full nghiêm trọng hơn.

## 16. Các hiểu lầm phổ biến

1. **"Logger.info() trả về nghĩa là log đã được lưu."** Sai. Nó có thể chưa vượt khỏi RAM hoặc chưa được collector nhận.
2. **"Async logging luôn không làm rơi log."** Sai. Chính sách queue full và shutdown quyết định nhiều rủi ro.
3. **"Chỉ cần tăng queue size thật lớn là hết mất."** Sai. Nếu producer nhanh hơn consumer lâu dài, mọi queue hữu hạn đều đầy; RAM và thời gian drain cũng tăng.
4. **"maxFlushTime cao bảo đảm không mất khi process bị kill."** Sai. SIGKILL/crash có thể không chạy shutdown.
5. **"ERROR luôn được giữ."** Sai. Một số policy ưu tiên nhưng không đảm bảo qua mọi tầng.
6. **"Không thấy record trong dashboard tức là đã mất."** Sai. Có thể tìm sai index, timezone, field, quyền hoặc chưa index kịp.
7. **"Flush tương đương fsync và lưu bền vững end-to-end."** Sai. Mỗi tầng có ý nghĩa flush/ACK khác nhau.
8. **"Collector có retry thì không bao giờ drop."** Sai. Queue có giới hạn, retry có thể hết hạn, disk vẫn có thể lỗi.
9. **"Gửi lại nhiều lần là exactly-once."** Sai. Retry có thể tạo duplicate nếu không có idempotency/đánh dấu nhận.
10. **"Logfile riêng là nơi lưu audit an toàn."** Sai. Audit cần chính sách storage, quyền, retention và toàn vẹn tương ứng.
11. **"Tắt một level là mất log ngoài ý muốn."** Sai nếu filtering là chính sách đã thống nhất.
12. **"Ứng dụng không crash nên logging chắc chắn hoạt động."** Sai. Appender có thể lỗi âm thầm hoặc pipeline downstream ngừng nhận.

## 17. Bài tập tự luyện

**Bài 1 — Bounded queue.** Chạy LostLogsDemo.java, đổi capacity từ 2 thành 3 và dự đoán dòng DROP thay đổi ra sao. Giải thích vì sao phần BLOCK vẫn nhận đủ sự kiện.

**Bài 2 — Giao nhận.** Vẽ pipeline của một ứng dụng Spring Boot dùng Logback AsyncAppender → stdout → collector → storage. Gắn vào từng mốc bằng chứng quan sát được (metric, status, một event ID).

**Bài 3 — Shutdown.** Thiết kế bài test dừng ứng dụng khi còn backlog. Bạn đo số pending, số đã gửi và tổng thời gian drain như thế nào? Điều gì có thể xảy ra khi container bị kill cưỡng bức?

**Bài 4 — Mất hay tìm nhầm?** Một log không hiện theo traceId nhưng tìm thấy bằng raw message tại cùng timestamp. Hãy xác định đây có phải queue drop không; kiểm tra MDC propagation và parser trước khi kết luận.

**Bài 5 — Sự kiện bắt buộc.** Chọn ví dụ một event thay đổi trạng thái đơn hàng không được phép biến mất. Phân tích vì sao log file/async logger không đủ và đề xuất cơ chế outbox/ACK/idempotency.

**Bài 6 — Failure injection.** Trong môi trường test, giả lập collector unreachable trong thời gian ngắn rồi phục hồi. Theo dõi queue, retry, accepted/sent và event IDs để xác định có drop thực sự hay không.

## 18. Tổng kết

Mất log là một **sự cố ở chuỗi vận chuyển thông tin**, không phải lúc nào cũng là lỗi của một câu lệnh logger. Cần xác minh từng ranh giới từ **code → level/filter → async queue → appender → stdout/file → collector → storage → query**, phân biệt **drop thật** với **delay, filtering có chủ đích và truy vấn sai**.

Ba thói quen quan trọng nhất:

1. **Định nghĩa hợp đồng theo loại event:** sự kiện nào có thể drop, sự kiện nào cần giữ và nơi nào phải nhận.
2. **Đo được đường đi và tình trạng lỗi:** queue occupancy, discarded count, appender errors, collector retry/export, độ trễ ingest, event ID kiểm thử.
3. **Thiết kế phục hồi có kiểm chứng:** backpressure/drop policy rõ ràng, shutdown drain, kiểm thử overload/crash và lưu bền vững riêng cho event nghiệp vụ thật sự quan trọng.

### Tài liệu tham khảo kỹ thuật

- Logback — AsyncAppender, queue, discardingThreshold, neverBlock, maxFlushTime: https://logback.qos.ch/manual/appenders-async-sift.html
- Log4j2 — Asynchronous Loggers và trade-offs: https://logging.apache.org/log4j/2.x/manual/async.html
- Log4j2 — Configuration properties và asyncQueueFullPolicy: https://logging.apache.org/log4j/2.x/manual/systemproperties.html
- Oracle Java SE 17 — FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java SE 17 — ArrayBlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- OpenTelemetry Collector — Troubleshooting: https://opentelemetry.io/docs/collector/troubleshooting/
- OpenTelemetry Collector — Resiliency: https://opentelemetry.io/docs/collector/resiliency/