# Race condition khi ghi log trong ứng dụng Java đa luồng

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Java, nhiều thread có thể cùng ghi log vào console, file hoặc hệ thống tập trung. Khi quan sát thấy dòng log bị xen kẽ, dữ liệu trong log sai, thiếu dòng hoặc trace ID của request này xuất hiện trong request khác, rất dễ kết luận rằng “logger không thread-safe”. Kết luận đó có thể không chính xác: **có nhiều vùng cạnh tranh (race) khác nhau** trong quá trình tạo và ghi một sự kiện log.

Sau bài này, người học có thể phân biệt:

1. **Race trên trạng thái nghiệp vụ được đọc để tạo thông điệp:** logger có thể ghi đúng một snapshot đã sai hoặc không nhất quán.
2. **Race khi tự xây dựng/ghi một bản ghi log:** nhiều thread cùng thao tác một buffer, writer, formatter hoặc appender không đồng bộ làm nội dung xen lẫn, hỏng hoặc mất.
3. **Đảo thứ tự quan sát được:** các thread độc lập có thứ tự scheduling khác nhau; log bất đồng bộ có thể làm thời điểm ghi ra khác thời điểm tạo event. Đây chưa tự động là data race hay lỗi logger.
4. **Race của context:** thread pool/callback bất đồng bộ dùng MDC/ThreadLocal sai cách khiến log thiếu hoặc lẫn định danh request.

Mục tiêu là tạo **mỗi event log đầy đủ, có context đúng, lấy dữ liệu nhất quán và được ghi bằng cơ chế phù hợp**; không cố ép mọi thread phải xuất log theo một thứ tự toàn cục không tồn tại trong chương trình.

## 2. Bản chất race condition

Race condition là tình huống kết quả phụ thuộc vào thứ tự xen kẽ các thao tác của nhiều luồng thực thi. Trong Java cần tách các khái niệm:

- **Data race theo Java Memory Model:** có truy cập xung đột đến cùng biến chia sẻ, ít nhất một truy cập là ghi, và không có quan hệ happens-before cần thiết giữa chúng. Khi đó có vấn đề về visibility và tính đúng đắn.
- **Mất tính nguyên tử (lost update/check-then-act):** một thao tác logic gồm nhiều bước bị xen ngang. Ví dụ cả hai thread đọc counter=0 và cùng ghi counter=1 sau khi cộng 1, dù kỳ vọng tổng là 2.
- **Interleaving của nội dung log:** một event bị tự chia ra nhiều lần append/write và event khác lọt vào giữa.
- **Nondeterministic ordering:** hai event độc lập có thể hiển thị theo thứ tự A rồi B hoặc B rồi A; chỉ riêng điều này không chứng minh đã có race gây lỗi.

Ví dụ mã sau là phép đọc–sửa–ghi, **không nguyên tử**:

~~~java
int old = count;
count = old + 1;
logger.info("count=" + count);
~~~

Nếu count là trạng thái dùng chung không được bảo vệ, việc gọi logger.info không làm hai dòng trước trở nên thread-safe. Thậm chí mỗi lệnh ghi log là thread-safe thì thông điệp vẫn phản ánh giá trị bị mất cập nhật.

Quy tắc quan trọng của Java: một thread nhìn thấy tác động của thread khác một cách đáng tin cậy khi có cơ chế happens-before phù hợp, chẳng hạn synchronized/lock, volatile cho mục đích thích hợp, thao tác atomic hoặc giao tiếp qua cấu trúc concurrent. Chỉ “đặt logger.info giữa hai thao tác” không phải một giao thức đồng bộ ứng dụng.

## 3. Race có thể xuất hiện ở đâu trong pipeline ghi log?

Một bản ghi log thường đi qua chuỗi sau:

~~~text
Thread nghiệp vụ
  │
  ├─ Đọc đối tượng / biến dùng chung
  ├─ Tạo thông điệp, tham số và throwable
  ├─ Thu thập thread name / timestamp / MDC / trace context
  │
  └─ Logger API
       ├─ Kiểm tra level, filter
       ├─ Tạo event / định dạng
       ├─ Có thể đưa vào hàng đợi async
       └─ Appender / Handler / encoder
            └─ Console, file, socket, collector hoặc backend
~~~

| Vị trí | Biểu hiện | Cách phòng tránh |
| --- | --- | --- |
| Đọc dữ liệu trước lệnh log | Giá trị đếm sai, các field không cùng phiên bản | Dùng AtomicInteger cho bộ đếm độc lập; lock hoặc immutable snapshot cho nhiều field phải nhất quán |
| Tự ghép chuỗi vào buffer chung | Hai bản ghi bị dính, thiếu ký tự hoặc xen dòng | Không chia event thành nhiều lệnh ghi độc lập; dùng logging framework và appender hỗ trợ concurrent writes |
| Formatter/encoder tự viết | Ngày giờ, StringBuilder hoặc cache dùng chung bị sai | Tránh shared mutable state; sử dụng DateTimeFormatter bất biến; đồng bộ phần state thực sự chia sẻ |
| Context gắn thread | Request A nhận request ID của B; thread khác không có context | Truyền context rõ ràng, khôi phục/clear trong finally |
| Async queue | Log xuất ra muộn, mất event khi queue đầy theo chính sách, khó suy diễn thứ tự | Hiểu chính sách queue/flush/shutdown; đo số log bị drop; giữ metadata thời điểm tạo event |
| Nhiều process cùng ghi file | Dòng chồng lên nhau hoặc rotation xung đột | Dùng cơ chế dành cho multi-process hoặc mỗi process ghi file/stream riêng và tổng hợp tập trung |

**Lưu ý:** SLF4J là logging facade; tính thread-safe cụ thể của việc ghi ra đích phụ thuộc logging provider, appender, encoder và cấu hình. Các logger/handler phổ biến được thiết kế để nhận lời gọi đồng thời, nhưng không thể suy từ điều đó rằng mọi custom appender, writer và đối tượng được log đều an toàn. Không chia sẻ một StringBuilder hoặc SimpleDateFormat tùy tiện giữa các thread.

## 4. Thực hành 1: logger ghi đúng, dữ liệu đem log vẫn sai

Đây là ví dụ Java 17 độc lập, chỉ dùng thư viện chuẩn JDK. Hai thread đều đọc biến đếm bằng 0 trước khi được phép ghi; mỗi thread sau đó thực hiện phép cộng không nguyên tử. AtomicInteger thực hiện cùng công việc theo cách an toàn.

**Tệp: RaceLogDemo.java**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class RaceLogDemo {
    private static final Logger LOG = Logger.getLogger("RaceLogDemo");

    public static void main(String[] args) throws InterruptedException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        // StreamHandler ghi ra stdout, định dạng cố định để dễ kiểm tra.
        StreamHandler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            demonstrateLostUpdate();
            demonstrateSplitLogRecord();
        } finally {
            handler.flush();
            LOG.removeHandler(handler);
        }
    }

    private static void demonstrateLostUpdate() throws InterruptedException {
        int[] unsafeCounter = {0};
        AtomicInteger atomicCounter = new AtomicInteger();

        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWrites = new CountDownLatch(1);

        Runnable task = () -> {
            int oldValue = unsafeCounter[0];
            bothHaveRead.countDown();

            try {
                allowWrites.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            unsafeCounter[0] = oldValue + 1;
            atomicCounter.incrementAndGet();
        };

        Thread t1 = new Thread(task, "worker-1");
        Thread t2 = new Thread(task, "worker-2");
        t1.start();
        t2.start();

        bothHaveRead.await();
        allowWrites.countDown();
        t1.join();
        t2.join();

        LOG.info("unsafeCounter=" + unsafeCounter[0]);
        LOG.info("atomicCounter=" + atomicCounter.get());
    }

    private static void demonstrateSplitLogRecord()
            throws InterruptedException {
        // Cố ý minh họa lỗi: một event bị ghi thành hai mảnh.
        StringBuilder sharedSink = new StringBuilder();
        CountDownLatch aWrotePrefix = new CountDownLatch(1);
        CountDownLatch bWroteLine = new CountDownLatch(1);

        Thread a = new Thread(() -> {
            sharedSink.append("A: begin ");
            aWrotePrefix.countDown();
            try {
                bWroteLine.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            sharedSink.append("end\n");
        }, "writer-A");

        Thread b = new Thread(() -> {
            try {
                aWrotePrefix.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            sharedSink.append("B: complete\n");
            bWroteLine.countDown();
        }, "writer-B");

        a.start();
        b.start();
        a.join();
        b.join();

        // Đổi newline thành chuỗi \n để hiện rõ ranh giới bản ghi.
        LOG.info("sharedSink=" + sharedSink.toString()
                .replace("\n", "\\n"));
    }
}
~~~

Chạy trong thư mục chứa tệp, với JDK 17 hoặc mới hơn:

~~~bash
javac RaceLogDemo.java
java RaceLogDemo
~~~

**Kết quả stdout:**

~~~text
unsafeCounter=1
atomicCounter=2
sharedSink=A: begin B: complete\nend\n
~~~

**Phân tích:**

- CountDownLatch bắt cả hai thread đọc unsafeCounter[0] trước khi một thread nào được ghi. Do đó cả hai ghi giá trị 1, mất một lần cập nhật. Thread chính gọi join() trước khi log, nên quan sát được kết quả cuối cùng. Đây là cách dựng lịch chạy có chủ đích để tái hiện lỗi; nếu bỏ latch, lỗi có thể lúc xuất hiện lúc không.
- AtomicInteger.incrementAndGet() là thao tác read-modify-write nguyên tử cho biến đó, nên kết quả bằng 2.
- Phần sharedSink cố ý tách một event của thread A thành hai append. Thread B hoàn tất một event xen vào giữa, tạo nội dung “A: begin B: complete\nend\n”. Các latch làm **interleaving giữa những bước ghép bản ghi** có thể tái hiện. Phần này chứng minh event không được tạo nguyên khối; bản thân nó không phải phép thử stress cho việc hai append đồng thời làm hỏng cấu trúc nội bộ StringBuilder.
- Trong demo, Logger chỉ được gọi từ main sau khi các thread đã join. Logger không gây ra hai lỗi phía trên; nó trung thực ghi lại dữ liệu sai do code ứng dụng tạo ra.

**Sửa đúng:** loại bỏ biến đếm int chia sẻ hoặc bảo vệ bằng lock chung, thay bằng AtomicInteger khi chỉ cần một biến đếm. Với log, mỗi event nên được tạo thành một đối tượng/sự kiện hoàn chỉnh và truyền cho logger bằng một lời gọi, dùng appender thread-safe; không để nhiều thread tự ghép chung một record qua nhiều append rời rạc.

## 5. Tạo log event nhất quán khi dữ liệu đang thay đổi

### 5.1. Một trường đếm: dùng atomic đúng mục đích

~~~java
AtomicInteger processed = new AtomicInteger();

int after = processed.incrementAndGet();
logger.info("processed=" + after);
~~~

Đoạn trên là snippet trong một phương thức có biến logger và processed đã khai báo. Giá trị after là kết quả chính xác của thao tác increment vừa thực hiện. Tuy nhiên, nhiều thread vẫn có thể **gọi logger theo thứ tự khác thứ tự increment**. Ví dụ thread A lấy after=1 rồi bị tạm dừng, thread B lấy after=2 và log trước. Nhìn log theo dòng in có thể thấy “2” trước “1”; điều đó tự nó không chứng minh AtomicInteger bị sai.

### 5.2. Nhiều trường liên quan: chụp snapshot dưới cùng cơ chế bảo vệ

Giả sử trạng thái đơn hàng gồm status và quantity phải được đọc từ **cùng phiên bản**. Đọc hai field qua hai lần gọi riêng biệt có thể thấy dữ liệu ghép từ hai lần cập nhật khác nhau.

~~~java
record OrderSnapshot(String status, int quantity) {}

final class OrderState {
    private String status = "NEW";
    private int quantity = 0;

    synchronized void update(String newStatus, int newQuantity) {
        status = newStatus;
        quantity = newQuantity;
    }

    synchronized OrderSnapshot snapshot() {
        return new OrderSnapshot(status, quantity);
    }
}
~~~

Ở nơi đã có state và logger:

~~~java
OrderSnapshot snapshot = state.snapshot();
logger.info("status=" + snapshot.status()
        + ", quantity=" + snapshot.quantity());
~~~

Đây là hai đoạn minh họa cần đặt trong ngữ cảnh một chương trình phù hợp. snapshot() đọc hai field bên trong **cùng khóa** mà update() dùng, trả về record bất biến. Có thể format và ghi log **sau khi nhả khóa**: giảm thời gian giữ lock và tránh gây chặn luồng nghiệp vụ do ghi console/file chậm.

Với yêu cầu nhất quán phức tạp hơn, có thể thiết kế state dưới dạng immutable object, thay cả tham chiếu một cách an toàn (ví dụ AtomicReference) và log bản snapshot đã chụp. Chỉ đánh dấu từng field là volatile không tự biến thao tác đọc nhiều field thành một snapshot nhất quán.

### 5.3. Tránh log tham chiếu mutable rồi mới định dạng

Một pipeline async có thể giữ lại tham số hoặc đối tượng cho đến lúc encoder xử lý. Nếu đối tượng đã thay đổi trước lúc định dạng, log có thể khác trạng thái tại thời điểm gọi API. Mức độ và thời điểm formatter đánh giá tham số tùy framework, cấu hình và kiểu event; không được mặc định mọi provider đều chụp sâu các đối tượng.

**Rủi ro:**

~~~java
logger.info("order=" + mutableOrder);
~~~

**Cách dễ kiểm soát hơn:**

~~~java
OrderSnapshot snapshot = state.snapshot();
logger.info("order status=" + snapshot.status()
        + ", quantity=" + snapshot.quantity());
~~~

Đọc snapshot an toàn, chuyển các giá trị cần log thành String/primitive/immutable DTO theo chính sách của ứng dụng, rồi bàn giao một event cho logger. Nếu dùng API supplier/lazy logging, nhớ rằng lambda có thể đọc biến/đối tượng mutable khi nó được gọi; một supplier không tự mang lại snapshot nhất quán. Có thể capture một giá trị bất biến trước khi tạo supplier.

## 6. Ghi log từ nhiều thread mà không làm vỡ record

### 6.1. Một lời gọi logger cho mỗi event

Nên dùng API của logging framework thay vì ghép nhiều mảnh vào một output stream dùng chung:

~~~java
// Các thread có thể gọi đồng thời trên logger được cấu hình đúng.
logger.info("worker=" + Thread.currentThread().getName()
        + " processed=" + processedId);
~~~

Đây là snippet trong method đã khai báo logger và processedId. Mỗi lần gọi biểu diễn một event hoàn chỉnh. Với SLF4J, cú pháp parameterized logging thường được dùng:

~~~java
// Ví dụ snippet SLF4J, cần dependency/backend tương ứng.
log.info("worker={} processed={}",
        Thread.currentThread().getName(), processedId);
~~~

Việc dùng placeholder giúp hoãn một phần chi phí định dạng khi level bị tắt, nhưng **không sửa lỗi đọc dữ liệu chung**. processedId phải được chụp đúng trước khi log.

Tránh cách ghi một event qua nhiều thao tác tách rời:

~~~java
// Minh họa lỗi: cùng một output bị nhiều thread sử dụng.
sharedWriter.write("order=" + orderId);
sharedWriter.write(" status=" + status);
sharedWriter.write("\n");
~~~

Nếu một thread khác ghi vào giữa, các mảnh có thể xen lẫn. Ngay cả khi từng write riêng lẻ được đồng bộ, **toàn bộ chuỗi ba write vẫn chưa được bảo vệ như một thao tác nguyên tử**. Thực tế nên gửi một event đầy đủ cho logger/appender hoặc, nếu bắt buộc dùng custom writer, bao toàn bộ thao tác logic trong cùng một cơ chế lock.

### 6.2. Nếu phải tự viết appender/handler

Chỉ khóa **phạm vi cần thiết** để bảo vệ các thành phần mutable dùng chung (writer, formatter, bộ đệm, trạng thái rotation). Ví dụ cấu trúc ý tưởng cho một sink in-memory:

~~~java
final class LineSink {
    private final StringBuilder buffer = new StringBuilder();

    public synchronized void appendLine(String line) {
        buffer.append(line).append('\n');
    }

    public synchronized String snapshot() {
        return buffer.toString();
    }
}
~~~

Lớp LineSink này có thể dùng trong một file Java 17 cùng tên nếu khai báo package-private; các phương thức đồng bộ bảo vệ toàn bộ lần thêm **một dòng**, còn snapshot() có cùng lock để đọc một bản sao nhất quán. Với nhu cầu thực tế, không nên tự triển khai file appender/rotation khi framework đã hỗ trợ.

Không đặt synchronized quanh toàn bộ quá trình xử lý HTTP/request chỉ để điều khiển thứ tự log; như vậy sẽ tuần tự hóa nghiệp vụ, tăng độ trễ và không giải quyết việc truyền context giữa service. Cũng tránh giữ application lock trong lúc gọi network/file logging nếu sink có thể block lâu hoặc gọi ngược vào code ứng dụng.

### 6.3. Một process khác cũng đang ghi file

Thread safety trong cùng JVM **không đồng nghĩa** an toàn khi nhiều JVM/process dùng chung một file. Rotation, rename, buffering, file lock và append semantics tùy filesystem/OS/provider. Cách dễ vận hành là để mỗi process ghi riêng ra stdout hoặc file riêng, rồi thu gom qua agent/collector. Nếu buộc phải chia sẻ file, dùng cơ chế multi-process được logging provider tài liệu hóa và kiểm thử trong môi trường thực tế.

## 7. Thứ tự log: điều gì được bảo đảm?

Xét hai thread:

~~~text
Thread A: update A1 → log A1 → update A2 → log A2
Thread B: update B1 → log B1
~~~

Nếu không có ràng buộc happens-before giữa A và B, output hoàn toàn có thể là:

~~~text
A1
B1
A2
~~~

hoặc:

~~~text
B1
A1
A2
~~~

Việc A1 xuất trước A2 thường phản ánh chương trình cùng thread gọi lần lượt trong trường hợp pipeline xử lý theo thứ tự, nhưng không được dùng ví dụ này để suy ra **bảo đảm thứ tự hiển thị toàn cục** của mọi appender/async pipeline. Thứ tự giữa hai thread độc lập không phải thứ tự nghiệp vụ đáng tin.

Cần phân biệt những mốc thời gian sau:

- Tạo event trong thread nghiệp vụ.
- Bàn giao event cho queue (nếu async).
- Worker lấy event khỏi queue.
- Formatter/encoder ghi bytes ra sink.
- Collector nhận và index event.

Timestamp thường dùng thời điểm tạo event, nhưng còn tùy provider và cấu hình. Đồng hồ giữa các máy có thể lệch; các timestamp bằng nhau hoặc rất gần nhau không cho phép suy ra quan hệ nhân quả. Muốn phân tích luồng xử lý, dùng trace ID/span ID hoặc ID tác vụ và các event nghiệp vụ có ý nghĩa; có thể gán sequence number theo phạm vi hẹp đã định nghĩa (ví dụ mỗi order) bằng bộ đếm atomic nếu yêu cầu.

**Một sequence number atomic cũng không buộc thứ tự dòng log tăng dần**: thread lấy số nhỏ vẫn có thể đến appender muộn hơn thread lấy số lớn.

## 8. MDC/ThreadLocal và nhầm request trong thread pool

MDC (Mapped Diagnostic Context) thường lưu các cặp key/value gắn với thread, ví dụ request_id, trace_id, user-safe-operation-id. Khi ExecutorService tái sử dụng thread, context của tác vụ trước có thể còn sót nếu quên cleanup. Ngược lại, context từ thread gọi không mặc định được chuyển sang thread worker.

Dưới đây là snippet dùng SLF4J MDC trong ứng dụng có SLF4J backend hỗ trợ MDC; không phải chương trình độc lập:

~~~java
import java.util.Map;
import org.slf4j.MDC;

// Ở thread tạo task:
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.execute(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null || captured.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        log.info("processing task");
    } finally {
        if (previous == null || previous.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Giải thích:

1. Chụp **bản sao** context ở thread gọi, trước lúc submit task.
2. Ở worker, lưu context cũ để không làm hỏng scope gọi lồng nhau.
3. Gắn context cần thiết, log, rồi phục hồi trong finally dù có exception.
4. Nếu context ban đầu rỗng, gọi clear để tránh giữ nhầm giá trị từ task trước.

Đối với hệ thống dùng OpenTelemetry, Reactor hay framework có cơ chế context propagation chính thức, ưu tiên cơ chế tương ứng thay vì tự bọc mỗi task. MDC không tự tạo span, không tự truyền traceparent sang service khác và không phải phương tiện bảo mật.

**Tình huống lỗi phổ biến:** request A xử lý trên worker-3 gắn request_id=A nhưng không dọn. Request B được lịch vào worker-3 và chỉ ghi log mà không set request_id; log của B mang nhãn A. Đây là sai lệch context do vòng đời thread và scope, không phải bằng chứng appender ghi trộn bytes.

## 9. Logging bất đồng bộ: hàng đợi, buffer và áp lực tải

Async logging thường tách luồng tạo event khỏi luồng ghi ra sink để giảm thời gian chờ I/O trong request path. Nó mang thêm các yếu tố cạnh tranh:

- **Queue capacity:** khi đầy, tùy provider/chính sách, producer có thể block, bỏ event, chạy đồng bộ hoặc áp dụng cơ chế khác. Không giả định “async luôn không mất log” hoặc “luôn drop”.
- **Tính nhất quán của event:** tham số mutable, exception, MDC cần được capture vào event đúng lúc theo hành vi backend. Không đoán provider giữ tham chiếu hay copy ở thời điểm nào nếu chưa kiểm tra.
- **Flush và shutdown:** lúc đóng ứng dụng phải cho worker ghi hết những event cần thiết theo khả năng và cấu hình của provider; không chỉ nhìn thấy logger.info trả về mà kết luận bytes đã ở đĩa/collector.
- **Ordering:** một queue FIFO đơn lẻ có thứ tự đối với các phần tử đã enqueue, nhưng các producer cạnh tranh không có một thứ tự “nghiệp vụ” toàn cục. Nhiều queue, partition, batched network transport hoặc collector càng không đảm bảo thứ tự hiển thị giống thời điểm từng thread gọi logger.
- **Backpressure:** cần quan sát queue utilization, dropped events, flush errors, độ trễ ghi, và quyết định cách xử lý log quan trọng theo mức độ ưu tiên.

Nếu yêu cầu nhật ký giao dịch bền vững, đúng thứ tự và không mất, **log thông thường không thay thế transaction log, outbox pattern hay audit store chuyên dụng**. Đó là một bài toán giao dịch và tính bền vững dữ liệu khác với log phục vụ vận hành.

## 10. Debug race condition khi ghi log

Khi thấy một hiện tượng bất thường, hãy phân loại trước khi sửa:

| Quan sát | Khả năng cần điều tra | Kiểm tra thực tế |
| --- | --- | --- |
| Hai request có cùng request_id không đúng | MDC rò rỉ giữa task hoặc ID được tái sử dụng | Gửi hai request liên tiếp trên pool size 1; log lúc bắt đầu/kết thúc scope |
| Counter trong log bị nhảy hoặc thấp hơn số tác vụ | Lost update hoặc snapshot không nhất quán | Kiểm tra phép tăng, synchronized/atomic và nơi chụp snapshot |
| Một dòng chứa một nửa dữ liệu của hai thread | Custom writer/appender ghép record qua nhiều write | Rà soát shared writer/buffer, giới hạn atomicity của mỗi event |
| Log ghi “2” trước “1” | Thread có số 2 chạy đến logger trước; async pipeline | Tách thứ tự cập nhật, enqueue, xuất ra và các ràng buộc happens-before |
| Log bị mất khi tải tăng | Queue đầy, filter, sampling, lỗi sink/collector | Kiểm tra cấu hình backend, dropped count, flush/error metrics |
| Dòng log bị xáo trộn lúc rotate file | Nhiều process/appender hoặc rotation không đồng bộ | Kiểm tra chủ sở hữu file, process count và hỗ trợ multi-process |
| Giá trị của object trong log khác lúc gọi logger | Mutable object bị thay đổi trước lúc format | Chụp immutable snapshot, kiểm tra thời điểm formatting của provider |

### Một quy trình điều tra hữu dụng

1. **Tái hiện có kiểm soát:** dùng CountDownLatch/CyclicBarrier để ép những interleaving đáng nghi; tránh chỉ dựa vào lỗi ngẫu nhiên khó lặp.
2. **Tách ba điểm đo:** trạng thái trước lúc tạo event, dữ liệu event được tạo, dữ liệu thực sự ở sink. Xác định lỗi xuất hiện ở bước nào.
3. **Xem đúng phần dùng chung:** biến đếm, object mutable, cache, formatter, writer, appender, queue, MDC/ThreadLocal; đừng thêm synchronized tràn lan.
4. **Kiểm tra happens-before:** join, Future.get, các concurrent collection, lock, atomic có dùng đúng ở cả đường đọc và đường ghi hay không.
5. **Giữ kích thước test nhỏ:** hai thread và một vài event rõ ràng thường đủ xác định nguyên nhân hơn hàng triệu dòng stress log.
6. **Thử với cấu hình production:** mức log, provider, appender async, chính sách overflow, rotation, collector và timeout có thể làm triệu chứng khác môi trường dev.

Stress test có thể phát hiện vấn đề nhưng **việc chạy một lần không thấy lỗi không chứng minh không có race**. Với bug đã có lịch xen kẽ xác định được, thiết kế test chủ động tái tạo quan hệ đó sẽ mạnh hơn việc chờ may rủi.

## 11. Thực hành phòng tránh trong dự án Java

**Dữ liệu và event:**

- Giữ các object có trạng thái chia sẻ dưới cơ chế đồng bộ phù hợp. Với nhiều thuộc tính phải nhất quán, dùng một immutable snapshot hoặc lock chung.
- Đưa toàn bộ nội dung cần log vào một event; không nối event bằng nhiều lệnh ghi vào sink chung mà thiếu bảo vệ.
- Tránh gọi toString() của object mutable phức tạp hoặc có side effect trong hot path; chọn các field ổn định và hạn chế dữ liệu nhạy cảm.
- Dùng structured logging để các thuộc tính như request_id, trace_id, thread, component và operation là các field riêng, thuận tiện cho phân tích.

**Cấu hình logger:**

- Dùng provider/appender được thiết kế cho concurrent logging và có chính sách hàng đợi, ghi file, rotation được tài liệu hóa.
- Coi custom appender, encoder, formatter là code đồng thời: thẩm tra các biến dùng chung và thời điểm tạo/copy event.
- Không nhầm **bảo đảm không trộn bytes của một event** với **bảo đảm thứ tự toàn cục của mọi event**.
- Khi async logging, đo lost/dropped events và độ trễ từ event đến sink; chủ động flush/shutdown đúng vòng đời ứng dụng.

**Thread và context:**

- Đặt context ở đầu scope, phục hồi/clear trong finally; bảo đảm task và callback bất đồng bộ mang đúng context.
- Dùng thread name và thread ID để hỗ trợ chẩn đoán, nhưng không dùng chúng như ID duy nhất cho request vì pool tái sử dụng thread.
- Không log bí mật, token hay dữ liệu cá nhân nhạy cảm trong MDC, exception message hoặc tham số.

## 12. Bài tập kiểm chứng

1. Chạy RaceLogDemo.java đúng như hướng dẫn và giải thích vì sao CountDownLatch giúp lỗi lost update tái hiện chắc chắn, còn AtomicInteger cho kết quả đúng.
2. Sửa demonstrateSplitLogRecord() để mỗi thread tạo một dòng hoàn chỉnh rồi gọi LineSink.appendLine(). Kiểm tra hai dòng độc lập không còn bị ghép mảnh, dù thứ tự A/B có thể thay đổi.
3. Tạo pool có một worker, xử lý request A rồi B; cố tình quên clear MDC và quan sát giá trị request_id bị dính. Sửa bằng try/finally và xác nhận B có ID riêng.
4. Tạo một tình huống dùng state gồm status và quantity; thực hiện update ở thread khác và so sánh log đọc từng field với log dùng snapshot() dưới cùng lock.
5. Với backend async thực tế, ghi rõ các cấu hình queue size, chính sách khi queue đầy, shutdown flush và giới hạn thứ tự; kiểm thử chỉ trong môi trường dành cho test để tránh ảnh hưởng log vận hành.

## 13. Ghi nhớ

“Race condition khi ghi log” không chỉ là hai thread cùng gọi logger.info. Vấn đề có thể nằm **trước logger** (đọc sai dữ liệu), **trong code tự ghi/định dạng event** (buffer hoặc appender chia sẻ), **trong context propagation** (MDC lẫn request), hoặc **sau khi enqueue** (bất đồng bộ và thứ tự xuất ra). Cách khắc phục phải khớp đúng nguyên nhân: atomic/lock/snapshot cho dữ liệu, event hoàn chỉnh và sink an toàn cho log, scope cleanup cho context và cấu hình queue/flush đúng cho async logging.

### Tài liệu tham khảo

- Java 17 java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java 17 StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- Java 17 CountDownLatch: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java 17 AtomicInteger: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Java 17 Memory Consistency Properties: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility
- SLF4J MDC API: https://www.slf4j.org/apidocs/org.slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
