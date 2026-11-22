# Mất log khi queue đầy trong logging bất đồng bộ (Java)

## 1. Vấn đề xảy ra ở đâu?

Logging bất đồng bộ (asynchronous logging) tách luồng xử lý nghiệp vụ khỏi thao tác xuất log: luồng ứng dụng tạo sự kiện log, đưa sự kiện vào bộ đệm có giới hạn; một hoặc nhiều worker đọc bộ đệm và ghi ra console, file hoặc dịch vụ tập trung.

~~~text
Luồng ứng dụng
      |
      v
  tạo LogEvent
      |
      v
  Queue / RingBuffer có giới hạn dung lượng
      |
      v
  Logging worker
      |
      v
  File / stdout / network / log collector
      |
      v
  Hệ thống tìm kiếm, lưu trữ log
~~~

Khi tốc độ tạo log vượt quá tốc độ tiêu thụ, số phần tử đang chờ tăng lên. Đến ngưỡng nhất định, logging framework phải quyết định **chặn luồng gọi, loại bỏ một số sự kiện hoặc dùng đường ghi thay thế**. Cách xử lý phụ thuộc framework và cấu hình; **queue đầy không mặc nhiên đồng nghĩa với mất log**.

Ví dụ: ứng dụng tạo 6.000 sự kiện/giây nhưng appender chỉ ghi được 4.000 sự kiện/giây. Nếu bộ đệm ban đầu trống và chứa được 8.000 sự kiện, backlog tăng xấp xỉ 2.000 sự kiện/giây. Sau khoảng 4 giây quá tải liên tục, queue có thể đầy. Đây là phép tính gần đúng, bỏ qua dao động tốc độ, chi phí tạo/ghi sự kiện và thời gian khởi động worker.

Trong thực tế còn có các cách mất log khác ngay cả khi queue chưa đầy: bộ lọc level, sampling, lỗi ghi file hoặc network, tiến trình chết đột ngột, chưa flush khi shutdown, collector bị nghẽn hoặc chính sách lưu trữ hết hạn. Vì vậy cần khoanh vùng đúng chặng xảy ra mất log.

## 2. Vì sao logging bất đồng bộ dễ nghẽn queue?

Queue có kích thước hữu hạn để tránh chiếm bộ nhớ không kiểm soát. Những tình huống thường gặp:

- **Burst:** lượng request hoặc exception tăng đột biến; tốc độ sản xuất log tăng cao trong vài giây.
- **Quá tải kéo dài:** tốc độ trung bình đưa log vào lớn hơn năng lực ghi thực tế; queue lớn đến đâu cũng sẽ đầy nếu tình trạng kéo dài.
- **Appender chậm:** ổ đĩa chậm, bộ lưu trữ đầy, stdout bị giữ lại, agent thu thập log bị nghẽn, network chập chờn.
- **Log quá nặng:** nhiều dòng DEBUG/TRACE, stack trace dài, chuyển đổi hoặc mã hóa JSON tốn CPU, tạo lượng lớn dữ liệu trên mỗi sự kiện.
- **Worker bị kẹt hoặc dừng:** lỗi I/O, deadlock, shutdown thiếu thời gian xả queue hoặc JVM bị kill.

Độ dài queue phản ánh **backlog** chứ không phải số log đã lưu bền vững. Thành công khi đưa một sự kiện vào queue chỉ có nghĩa logging worker có cơ hội xử lý nó sau này; chưa khẳng định sự kiện đã được ghi ra đích.

## 3. Bốn nhóm chính sách khi queue đầy

| Chính sách | Hành vi | Tác động chính |
| --- | --- | --- |
| **Block / backpressure** | Luồng gọi chờ đến khi có chỗ trong queue | Hạn chế drop do đầy queue, nhưng tăng latency và có thể kéo chậm request |
| **Drop / discard** | Bỏ sự kiện mới hoặc sự kiện theo mức ưu tiên | Giữ đường nghiệp vụ phản hồi nhanh hơn, nhưng mất dữ liệu quan sát |
| **Timed offer** | Đợi một thời hạn rồi trả về thất bại nếu vẫn đầy | Giới hạn thời gian chờ; vẫn phải xử lý trường hợp log bị từ chối |
| **Fallback / ghi đồng bộ** | Chuyển sự kiện sang appender dự phòng hoặc xử lý trên luồng gọi khi phù hợp | Có thể giữ log trong một số trường hợp, nhưng tăng chi phí và đích dự phòng cũng có thể lỗi |

Không có chính sách nào tự bảo đảm vừa **không mất log** vừa **không ảnh hưởng độ trễ** khi lượng log vào cao hơn khả năng tiêu thụ trong thời gian dài. Nếu không được loại bỏ và không thể ghi nhanh hơn, áp lực phải tác động ngược trở lại producer.

Cần phân biệt ba thời điểm:

1. **Trước enqueue:** event có thể bị bỏ theo level/filter/sampling hoặc chính sách discard khi gần đầy.
2. **Lúc enqueue:** thao tác put có thể chờ; offer có thể trả về false; framework có thể chuyển sang fallback.
3. **Sau enqueue:** worker vẫn có thể gặp lỗi I/O, tiến trình dừng hoặc log collector không nhận được dữ liệu.

Không dùng số log hiển thị ở dashboard làm bằng chứng duy nhất để kết luận queue đầy; nên đo lượng event **được tạo, được chấp nhận, bị loại và thực sự đi tới đích**.

## 4. Ví dụ Java 17+: queue đầy và sự kiện bị loại bỏ

Ví dụ độc lập dưới đây dùng ArrayBlockingQueue để mô phỏng đúng hành vi của **chiến lược không chặn**: producer gọi offer(), nhận false khi queue hết chỗ và tăng bộ đếm dropped. Để kết quả tái lập được, bài kiểm thử chưa khởi chạy worker; đây là mô hình cơ chế queue, không phải bản triển khai logging production.

Tạo file **QueueOverflowDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueOverflowDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        int accepted = 0;
        int dropped = 0;

        for (String event : List.of("event-1", "event-2", "event-3")) {
            // offer() không chờ: trả về false khi queue đã đầy.
            if (queue.offer(event)) {
                accepted++;
            } else {
                dropped++;
            }
        }

        System.out.println("accepted=" + accepted + ", dropped=" + dropped);
        System.out.println("queue=" + queue);

        // Giả lập worker đã tiêu thụ một sự kiện.
        System.out.println("consumed=" + queue.poll());
        System.out.println("retry=" + queue.offer("event-4"));
        System.out.println("queue=" + queue);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac QueueOverflowDemo.java
java QueueOverflowDemo
~~~

Kết quả xác định của ví dụ:

~~~text
accepted=2, dropped=1
queue=[event-1, event-2]
consumed=event-1
retry=true
queue=[event-2, event-4]
~~~

Giải thích: queue có sức chứa hai phần tử nên event-1 và event-2 được nhận. Khi event-3 tới, offer trả về false: nếu producer bỏ qua giá trị này, **event-3 đã mất ngay tại điểm enqueue**. Sau khi tiêu thụ event-1, queue có một chỗ và nhận event-4. Lấy ra một phần tử **không khôi phục lại** event-3.

Đây cũng là lỗi hay gặp ở mã tự xây dựng: gọi queue.offer(event) nhưng bỏ qua kết quả trả về. Nếu chọn chính sách discard, bộ đếm sự kiện bị loại phải tăng chính xác ở nơi quyết định loại sự kiện.

## 5. So sánh offer(), put() và offer(timeout)

Với java.util.concurrent.BlockingQueue, các lựa chọn có ngữ nghĩa khác nhau:

~~~java
// A. Không chặn: false nếu đầy.
boolean accepted = queue.offer(event);

// B. Chặn cho đến khi có chỗ (hoặc bị interrupt).
queue.put(event);

// C. Chờ tối đa 100 ms; false nếu hết thời gian mà vẫn đầy.
boolean acceptedInTime =
        queue.offer(event, 100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Đoạn trên chỉ minh họa ba phương thức trên biến queue và event đã có, **không phải chương trình biên dịch độc lập**. put() và offer(timeout) có thể ném InterruptedException; mã gọi cần xử lý đúng, thường khôi phục cờ ngắt với Thread.currentThread().interrupt() và dừng/chuyển trạng thái phù hợp. Không nuốt ngoại lệ ngắt rồi âm thầm tiếp tục.

Với logging production, cần cân nhắc:

- Block vô hạn có thể làm request chậm, timeout hoặc đình trệ nếu appender phía sau không bao giờ tiêu thụ tiếp; một số trường hợp logging đệ quy/cùng khóa có thể gây deadlock.
- Timed offer giới hạn thời gian chờ nhưng **vẫn có nhánh thất bại** cần đếm hoặc fallback.
- Drop giảm tác động lên request nhưng khiến mất dữ liệu truy vết, đặc biệt nguy hiểm nếu sự kiện quan trọng không được phân loại.
- Fallback đồng bộ chỉ giúp khi đích dự phòng còn hoạt động; ghi thành công vào một API appender cũng chưa chắc dữ liệu đã bền vững trên ổ đĩa hoặc máy chủ tập trung.

Không tự thay đổi cơ chế queue của framework chỉ vì ví dụ này: các thư viện logging có thêm chính sách theo mức độ log, bộ đệm chuyên dụng và quy trình shutdown riêng.

## 6. Logback AsyncAppender: log có thể bị loại ngay trước khi đầy

Với **Logback Classic AsyncAppender**, cần chú ý một điểm rất dễ bỏ sót: cấu hình mặc định có thể **loại TRACE, DEBUG và INFO khi queue chỉ còn dưới khoảng 20% chỗ trống**. Đây là chiến lược giảm áp lực trước khi queue đầy, không phải lỗi ngẫu nhiên của Java.

Các thuộc tính quan trọng:

| Thuộc tính Logback | Ý nghĩa |
| --- | --- |
| queueSize | Số event tối đa có thể chờ (mặc định 256) |
| discardingThreshold | Ngưỡng số chỗ còn lại để bắt đầu bỏ sự kiện mức thấp; đặt 0 để tắt hành vi loại sớm này |
| neverBlock | Mặc định false: khi queue đầy sẽ chặn luồng gọi; true: bỏ sự kiện khi không enqueue được |
| maxFlushTime | Thời gian chờ tối đa, tính bằng mili giây, cho worker xả queue khi stop; 0 là chờ không giới hạn |

Như vậy, chỉ đặt neverBlock=false **chưa đủ** để giữ các sự kiện INFO/DEBUG khi queue gần đầy; còn phải xem discardingThreshold.

Ví dụ **logback.xml** nhằm giảm mất log do chính sách queue trong ứng dụng chấp nhận backpressure:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>8192</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>10000</maxFlushTime>
    <appender-ref ref="FILE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

Điều kiện sử dụng: dự án đã có Logback Classic phù hợp trên classpath; đoạn XML là cấu hình framework, **không chạy bằng javac**. Đường dẫn logs/application.log cần có nơi lưu trữ và quyền ghi phù hợp. Root level INFO vẫn lọc DEBUG/TRACE từ đầu; discardingThreshold=0 **không bật lại** những mức log đã bị level filter tắt.

Cấu hình trên có nghĩa: không chủ động loại sự kiện mức thấp chỉ vì queue gần đầy; nếu đầy, producer chờ có chỗ. Tuy nhiên:

- Khi appender ghi chậm, thời gian xử lý request vẫn tăng.
- maxFlushTime=10000 cho tối đa khoảng 10 giây để xả lúc stop; hết hạn có thể còn log chưa ghi. Chọn giá trị theo thời gian graceful shutdown của hệ thống.
- Cấu hình không ngăn mất log khi process bị kill cưỡng bức, máy hỏng, file I/O thất bại hoặc bộ thu downstream lỗi.
- Nếu đặt neverBlock=true thì framework ưu tiên không chặn producer và **có thể mất event khi queue đầy**, kể cả nếu discardingThreshold=0.

Muốn kiểm tra nguyên nhân, xem cả log/status nội bộ của Logback, mức đầy queue, thời gian ghi của appender, quá trình shutdown và lượng dòng thực tế trên file.

## 7. Log4j 2: phân biệt Async Appender và Async Logger

Log4j 2 có hai kiểu bất đồng bộ khác nhau:

- **Async Appender** dùng queue để chuyển log sang các appender đích trên worker.
- **Async Logger** sử dụng cơ chế LMAX Disruptor/ring buffer. Các tên tham số cấu hình và tác động ở từng thành phần không hoàn toàn giống nhau.

Với **Log4j 2 Async Appender**, thuộc tính blocking mặc định là true; khi queue đầy, producer thường phải chờ theo chính sách queue. Nếu chọn blocking=false, Log4j 2 có thể chuyển event sang error appender khi được cấu hình; khi không có đường xử lý thay thế hữu hiệu thì log có thể mất. Có thể cấu hình bufferSize và errorRef tùy nhu cầu.

Ví dụ cấu hình Log4j 2 cho chế độ chặn khi queue đầy:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="FILE" fileName="logs/application.log">
      <PatternLayout pattern="%d{ISO8601} %-5p [%t] %c - %m%n"/>
    </File>
    <Async name="ASYNC" bufferSize="8192" blocking="true"
           shutdownTimeout="10000">
      <AppenderRef ref="FILE"/>
    </Async>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="ASYNC"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Đây là **log4j2.xml** dành cho dự án có Log4j 2 Core tương ứng. Không áp dụng các thuộc tính Logback như neverBlock hoặc discardingThreshold trực tiếp vào XML Log4j 2.

Log4j 2 còn hỗ trợ thuộc tính chung **log4j2.asyncQueueFullPolicy** cho các thành phần async. Theo tài liệu Log4j 2.x:

- **Default:** chặn luồng gọi khi queue đầy để chờ enqueue.
- **Discard:** loại sự kiện có độ ưu tiên không cao hơn mức cấu hình; **log4j2.discardThreshold** mặc định là INFO, nên TRACE/DEBUG/INFO có thể bị loại khi đầy.

Chỉ dùng Discard sau khi xác định rõ log nào có thể mất. Nếu thay đổi phiên bản lớn của Log4j, đối chiếu tên thuộc tính trong đúng tài liệu phiên bản đang chạy. Chính sách queue không xử lý được lỗi lưu file hoặc lỗi collector sau dequeue.

## 8. Chọn kích thước queue dựa trên tải thực tế

Tăng queueSize có thể hấp thụ một đợt burst nhưng **không làm tăng tốc độ ghi**. Công thức ước lượng thời gian lấp đầy khi tốc độ xấp xỉ ổn định:

~~~text
t_full ≈ (capacity - current_backlog) / (produced_per_second - consumed_per_second)
         (chỉ áp dụng khi produced_per_second > consumed_per_second)
~~~

Ví dụ capacity = 8.000 event, backlog ban đầu = 0, producer tạo 6.000/s và worker xử lý 4.000/s: khoảng 4 giây là queue đầy. Tăng capacity lên 16.000 cho khoảng 8 giây; nếu nút thắt vẫn tồn tại, sau 8 giây vẫn phải đối mặt với block/drop.

Cần đánh đổi:

- **Dung lượng bộ nhớ:** queue giữ tham chiếu và nội dung sự kiện; stack trace, message payload hoặc object tham chiếu có thể làm tiêu tốn nhiều heap hơn số lượng phần tử gợi ý.
- **Độ trễ quan sát:** queue lớn khiến log có thể đến hệ thống tìm kiếm muộn hơn khi backlog tăng.
- **Thời gian shutdown:** backlog lớn cần nhiều thời gian xả hơn.
- **Tài nguyên và mức log:** giảm DEBUG/TRACE ồn ào, giới hạn log trong vòng lặp và tránh lặp stack trace thường hữu ích hơn tăng queue vô hạn.

Muốn tăng năng lực tiêu thụ, đo nút thắt thực tế: encoder, disk, stdout, network, appender, collector hoặc backend. Có thể tối ưu định dạng, giảm log thừa, phân luồng log có mức ưu tiên khác nhau, cải thiện hạ tầng I/O hoặc chọn loại appender phù hợp.

## 9. Quan sát và cảnh báo trước khi mất log

Nên bổ sung telemetry độc lập với chính pipeline logging đang có nguy cơ quá tải. Nếu cảnh báo cũng chỉ ghi vào queue đang đầy thì bản thân thông báo cảnh báo có thể bị mất.

Những tín hiệu cần theo dõi:

| Tín hiệu | Diễn giải |
| --- | --- |
| Queue occupancy = size / capacity | Phần trăm queue đang sử dụng; theo dõi cả mức đỉnh |
| Enqueue reject / discarded events | Số event bị từ chối hoặc bị chính sách drop loại bỏ |
| Producer blocked duration | Thời gian thread chờ do backpressure |
| Appender errors / retries | Lỗi I/O, network, encoding và lần retry |
| Drain rate / backlog age | Tốc độ ghi và độ cũ của event đang chờ |
| Shutdown flush duration / remaining events | Khả năng xả log trong graceful shutdown |

Không giả định framework nào cũng có sẵn metric discarded_count: có thư viện chỉ cung cấp trạng thái hoặc số phần tử trong queue. Cần kiểm tra API, version và cách instrument thực tế. Nếu phải tự bao bọc đường enqueue, đặt counter ở nhánh **thực sự bỏ sự kiện**, tránh đếm sai event đã được fallback xử lý thành công.

Gợi ý cảnh báo: queue duy trì trên 70–80% trong một khoảng đo, discarded tăng khỏi 0, producer wait tăng mạnh hoặc appender phát sinh lỗi liên tục. Các ngưỡng này chỉ là điểm bắt đầu, phải hiệu chỉnh bằng tải và yêu cầu latency/SLO thực tế. Đặc biệt, khi Logback dùng chiến lược loại sớm mặc định, không nên đợi queue đạt 100% mới báo động.

## 10. Cách thử nghiệm mất log có kiểm soát

Chạy kiểm thử trên môi trường riêng, không cố tình làm quá tải pipeline log production:

1. **Thiết lập baseline:** biết rõ framework/version, queueSize, ngưỡng drop, blocking, mục tiêu ghi, thời gian shutdown và log level.
2. **Gắn ID tăng dần** vào từng event thử nghiệm (test-run-id + sequence number), đồng thời đo số event dự kiến tạo.
3. **Burst ngắn:** tạo log nhanh hơn worker trong vài giây; đo queue max, số lần reject/drop và độ trễ của lời gọi logging.
4. **Quá tải kéo dài:** duy trì tốc độ tạo log lớn hơn khả năng tiêu thụ, kiểm tra queue đạt trần và chính sách block/drop được kích hoạt như cấu hình.
5. **Làm chậm appender:** trong môi trường kiểm thử, mô phỏng ghi file/network chậm để xem nút thắt và áp lực dồn lên queue.
6. **Xả queue và shutdown:** dừng producer, cho worker tiêu thụ hết queue; thử graceful shutdown với timeout giới hạn và xác định event còn lại.
7. **Đối chiếu kết quả:** so khớp các sequence ID đã tạo với những ID được xác nhận ở đích (file/collector); phân biệt duplicate do retry và thiếu event thực sự. Không lấy thứ tự log bất đồng bộ làm tiêu chí duy nhất nếu pipeline có thể ghi hoặc nhập dữ liệu ngoài thứ tự.

Ví dụ kết luận đúng: "Trong lượt kiểm thử A đã tạo 100.000 event, 1.500 bị từ chối khi enqueue, 98.500 tới file và không còn event chờ" nếu có đủ bộ đếm và chứng cứ. Kết luận "mất 1.500 event vì Elasticsearch chỉ thấy 98.500" **chưa đủ** vì có thể còn chờ ingest, bị filter, trễ index hoặc nằm ngoài cửa sổ truy vấn.

## 11. Hướng xử lý theo mức độ quan trọng của log

**Log chẩn đoán thông thường (DEBUG/INFO):** Có thể chấp nhận drop có kiểm soát để bảo vệ độ trễ nghiệp vụ, nhưng cần đếm được lượng bị bỏ và điều chỉnh mức log. Nên ưu tiên giảm log vô ích và tối ưu appender trước khi tăng bộ nhớ.

**Log ERROR phục vụ điều tra sự cố:** Ưu tiên giữ lại, có thể dùng block/fallback hoặc luồng ưu tiên riêng. Tuy nhiên queue có thể bị nghẽn bởi lượng lớn error; không coi WARN/ERROR là tuyệt đối không thể mất chỉ vì framework mặc định ưu tiên chúng.

**Dữ liệu kiểm toán, thanh toán, giao dịch bắt buộc lưu:** Không dùng queue bất đồng bộ trong RAM làm nguồn duy nhất. Sử dụng cơ chế lưu bền vững phù hợp (giao dịch DB, transactional outbox, durable broker hoặc hệ thống audit chuyên dụng), kèm xác nhận, retry và xử lý trùng theo yêu cầu nghiệp vụ. Ghi log đồng bộ vào một appender thông thường cũng không tự bảo đảm durability end-to-end.

**Shutdown:** chủ động đóng LoggerContext/appender sau khi ngừng nhận công việc mới, dành đủ thời gian để xả queue theo thời gian graceful termination của container/service. Dù có shutdown hook vẫn phải tính tới kill -9, mất điện, OOM hoặc lỗi thiết bị. Khi đặt maxFlushTime vô hạn, hệ thống có thể không kết thúc đúng hạn nếu downstream bị kẹt; khi giới hạn quá ngắn, backlog có thể chưa được xả.

## 12. Các lỗi cấu hình và hiểu nhầm phổ biến

- **"Queue đầy chắc chắn mất log":** Sai; cấu hình block có thể chờ producer và giảm rủi ro drop vì queue đầy.
- **"Chưa đầy 100% thì không mất log":** Sai với các chính sách loại sớm, ví dụ Logback AsyncAppender mặc định bỏ TRACE/DEBUG/INFO khi sắp đầy.
- **"Tăng queue lên rất lớn sẽ hết mất log":** Chỉ kéo dài thời gian chịu burst; không giải quyết quá tải kéo dài và có thể tăng áp lực heap/GC.
- **"Không có dropped counter nghĩa là không drop":** Có thể thiếu instrument hoặc mất log ở worker, file, network hay collector.
- **"put thành công nghĩa là log đã lưu":** Chỉ xác nhận enqueue, chưa xác nhận sink đã ghi.
- **"Tắt discard là luôn tốt":** Backpressure có thể kéo dài response time, làm nghẽn request hoặc tăng nguy cơ deadlock trong một số luồng gọi.
- **"maxFlushTime đủ lớn bảo đảm không mất log":** Shutdown không sạch và lỗi I/O vẫn có thể mất sự kiện.
- **"Error log luôn phải dùng chung chính sách với DEBUG":** Nên phân loại mức độ quan trọng; dữ liệu bắt buộc bền vững cần kiến trúc lưu trữ riêng.

## 13. Checklist nghiệm thu

Một hệ thống logging bất đồng bộ được cấu hình có chủ đích khi trả lời rõ các câu hỏi:

- Queue hoặc ring buffer giới hạn bao nhiêu event, backlog và mức đỉnh thực tế là bao nhiêu?
- Khi gần đầy hoặc đầy, sự kiện nào bị drop, thread nào bị block, có fallback hay không?
- Các trường hợp ERROR, retry, shutdown và downstream outage được xử lý ra sao?
- Có quan sát được số event bị loại và latency vì backpressure mà không phụ thuộc vào chính queue đang nghẽn?
- Đã thử burst, quá tải kéo dài, appender chậm và shutdown, rồi đối chiếu sequence ID ở đích chưa?
- Đã tách dữ liệu audit bắt buộc lưu khỏi logging quan sát thông thường chưa?

**Kết luận:** Giảm mất log khi queue đầy phải kết hợp kiểm soát lượng log đầu vào, năng lực xử lý của appender, chính sách block/drop phù hợp và cơ chế quan sát. Cấu hình chống drop tại điểm enqueue chỉ giải quyết một chặng của đường đi log; yêu cầu không mất dữ liệu nghiêm ngặt cần cơ chế lưu bền vững riêng.

## Tài liệu tham khảo

- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queueSize, discardingThreshold, neverBlock, maxFlushTime và shutdown.
- [Apache Log4j 2 — Async Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): mô hình async logger, ring buffer, queue-full policy và trade-off.
- [Apache Log4j 2 — Delegating Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): Async Appender, blocking, bufferSize, errorRef, shutdownTimeout.
