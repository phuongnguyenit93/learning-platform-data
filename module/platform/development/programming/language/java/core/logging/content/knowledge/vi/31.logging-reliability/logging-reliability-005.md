# Queue đầy trong Java Logging: xử lý bão hòa và bảo đảm độ tin cậy

## 1. Queue đầy là gì?

Trong **logging bất đồng bộ**, thread nghiệp vụ thường không tự ghi toàn bộ sự kiện xuống file hoặc mạng. Thay vào đó, nó tạo một log event và đưa vào **queue**, rồi một worker phía sau lấy sự kiện ra để ghi vào sink.

```text
Business threads           Logging thread              Destination
      |                          |                           |
      |---- create event ------->|                           |
      |---- enqueue ----------> [bounded queue]               |
      |                          |--- dequeue / format ------>|
      |                          |                           | file/stdout/network
      |
      +-- nếu queue đầy: chờ / bỏ log / timeout / fallback?
```

**Queue đầy (queue saturation)** xảy ra khi queue có giới hạn đã chứa tối đa số phần tử được phép, nên không thể nhận thêm sự kiện theo cách enqueue không chặn. Điều này thường do **tốc độ tạo log lớn hơn tốc độ tiêu thụ**, hoặc consumer bị đình trệ.

Trong bài toán **độ tin cậy logging**, cần đặt hai câu hỏi khác nhau:

1. Khi queue đầy, lời gọi log **có thể mất sự kiện hoặc làm chậm nghiệp vụ không**?
2. Nếu queue nhận được sự kiện, log **đã thực sự được ghi hoặc lưu bền vững chưa**?

Câu trả lời cho (2) **không mặc định là “có”**. Queue trong RAM chỉ là một vùng đệm; enqueue thành công không đồng nghĩa file đã ghi xong, collector đã xác nhận, hay sự kiện chịu được crash.

Queue đầy còn khác với:

- **Log bị lọc do level:** DEBUG bị tắt có thể khiến sự kiện không được tạo, không phải lỗi queue.
- **Sink lỗi:** file hoặc collector có thể lỗi dù queue chưa đầy; queue sẽ đầy nếu consumer không xử lý được đủ nhanh.
- **OutOfMemoryError:** queue hữu hạn có thể đầy trước khi hết heap. Queue không giới hạn lại dễ khiến tồn đọng tăng đến mức hết bộ nhớ.
- **Đĩa đầy:** đĩa chứa log hết dung lượng là một lỗi ở sink; nó có thể kéo theo queue đầy nhưng không phải cùng khái niệm.

## 2. Vì sao queue đầy và hậu quả là gì?

Các nguyên nhân thường gặp:

- Bùng nổ WARN/ERROR trong vòng retry hoặc exception lặp lại tạo quá nhiều sự kiện.
- Bật TRACE/DEBUG cho toàn dịch vụ ở production; từng request sinh nhiều log hơn dự kiến.
- Đường ghi file bị giới hạn I/O, rotation chậm, file system bị treo hoặc gần hết dung lượng.
- Log shipper / network / collector bị chậm, mất kết nối hoặc áp dụng rate limit.
- Worker logging tạm dừng vì CPU, GC, contention hoặc gặp lỗi không khôi phục.
- Một queue chung gom nhiều nguồn log; nguồn nhiễu chiếm hết chỗ của sự kiện quan trọng.

Hậu quả phụ thuộc chính sách khi enqueue:

| Trạng thái | Hành vi có thể xảy ra | Tác động |
| --- | --- | --- |
| Queue còn chỗ | Enqueue nhanh, worker ghi sau | Log có độ trễ; vẫn có rủi ro crash trước khi ghi |
| Queue đầy + producer chờ | Thread gọi logger đứng chờ | Tăng latency, chiếm thread, có thể lan sự cố sang API |
| Queue đầy + bỏ event | Lời gọi logger trả nhanh | Mất một phần log, có thể mất dữ liệu cần điều tra |
| Queue đầy + chờ có giới hạn | Chờ đến deadline rồi quyết định | Có ngân sách latency, nhưng vẫn cần cách xử lý timeout |
| Queue đầy + ghi đồng bộ dự phòng | Producer tự ghi ra sink | Có thể giữ thêm log; đường I/O chậm quay lại thread nghiệp vụ |
| Queue đầy + chuyển sang vùng đệm bền vững | Ghi qua một durable queue riêng | Tăng khả năng phục hồi, nhưng vẫn có chi phí và điểm giới hạn khác |

**Không có chính sách miễn phí:** cố tránh mất mọi sự kiện bằng cách chặn vô hạn có thể làm hỏng dịch vụ chính; cố giữ độ trễ bằng cách bỏ log có thể đánh mất dữ liệu quan trọng. Quyết định phải dựa trên SLO, mức quan trọng của log và năng lực sink.

## 3. Bài toán tốc độ: khi nào queue sẽ đầy?

Gọi:

- `λ`: tốc độ producer tạo log (events/giây).
- `μ`: tốc độ worker và sink tiêu thụ log (events/giây).
- `C`: sức chứa queue (số event).
- `q₀`: số event đang có trong queue tại thời điểm bắt đầu.

Nếu `λ > μ` kéo dài, lượng tồn đọng có xu hướng tăng xấp xỉ:

```text
backlog tăng mỗi giây ≈ λ - μ
vị trí còn trống      ≈ C - q₀
thời gian tới khi đầy ≈ (C - q₀) / (λ - μ)
```

Ví dụ: queue có 4.000 vị trí, hiện giữ 1.000 event. Producer phát 1.200 event/giây, consumer ghi 900 event/giây. Số chỗ còn lại là 3.000; tồn đọng tăng khoảng 300 event/giây, nên **ước tính sau 10 giây** queue đầy nếu tình hình không đổi.

Đây là mô hình đơn giản; thực tế tốc độ thay đổi theo burst, loại sự kiện, kích thước stack trace, định dạng, GC và đường ghi. Nếu consumer liên tục không tiến triển (`μ ≈ 0`) thì queue sẽ đầy nhanh hơn.

**Tăng kích thước queue chỉ kéo dài thời gian trước khi bão hòa**, không chữa được tình trạng `λ > μ` lâu dài. Queue lớn cũng giữ nhiều đối tượng:

```text
bộ nhớ dữ liệu event ≈ số event trong queue × kích thước trung bình mỗi event
```

Ví dụ: 8.000 event × 1 KiB ≈ 7,8 MiB dữ liệu, **chưa kể overhead của đối tượng, tham chiếu, chuỗi và dữ liệu context**. Sự kiện có exception stack trace hoặc payload lớn có thể nặng hơn rất nhiều.

## 4. Java 17: mô phỏng queue đầy bằng ArrayBlockingQueue

Để hiểu đúng điều kiện đầy, bắt đầu với `ArrayBlockingQueue` có **sức chứa cố định**. Đây là chương trình độc lập chỉ mô phỏng bước producer enqueue và consumer dequeue, không phải một logging backend hoàn chỉnh.

Lưu tệp **`QueueFullDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueFullDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        boolean first = queue.offer("INFO app-started");
        boolean second = queue.offer("DEBUG cache-check");
        boolean third = queue.offer("WARN retry");

        System.out.println("first accepted: " + first);
        System.out.println("second accepted: " + second);
        System.out.println("third accepted: " + third);
        System.out.println("depth: " + queue.size());

        System.out.println("consumer 1: " + queue.poll());
        System.out.println("consumer 2: " + queue.poll());
        System.out.println("depth after drain: " + queue.size());
        System.out.println("retry accepted: " + queue.offer("WARN retry"));
    }
}
```

Biên dịch và chạy:

```bash
javac QueueFullDemo.java
java QueueFullDemo
```

Kết quả `stdout`:

```text
first accepted: true
second accepted: true
third accepted: false
depth: 2
consumer 1: INFO app-started
consumer 2: DEBUG cache-check
depth after drain: 0
retry accepted: true
```

Vì chỉ một thread thao tác, thứ tự kết quả **xác định**:

1. Queue 2 vị trí nhận hai event đầu.
2. Lần `offer` thứ ba trả về `false` ngay do queue đầy.
3. Consumer mô phỏng `poll()` lấy các event ra.
4. Sau khi có chỗ trống, `offer` mới được chấp nhận.

**Nếu bỏ qua `false`, event thứ ba bị mất ở phía producer.** Một logging system production cần định nghĩa rõ phải làm gì với event bị từ chối và đo số lượng bị bỏ. Không nên “thử lại vô hạn” mà không có giới hạn, vì sink nghẽn có thể khiến chính vòng retry tạo thêm tải.

Chương trình demo không chứng minh log được ghi xuống đĩa: `poll()` chỉ lấy chuỗi khỏi queue, và in ra terminal cũng không phải bảo đảm durability.

## 5. Các thao tác BlockingQueue và chính sách khi đầy

Java cung cấp nhiều API với semantics khác nhau:

| API | Khi queue đầy | Gợi ý sử dụng |
| --- | --- | --- |
| `offer(event)` | Trả `false` ngay | Non-blocking; phải đếm drop hoặc fallback |
| `put(event)` | Chặn cho tới khi có chỗ hoặc bị interrupt | Ưu tiên không bỏ do queue đầy, nhưng có thể kẹt request |
| `offer(event, timeout, unit)` | Đợi tối đa timeout rồi trả `false` nếu vẫn đầy | Có giới hạn latency; định nghĩa rõ policy khi hết hạn |
| `add(event)` | Ném `IllegalStateException` nếu đầy | Thường không phù hợp để mặc định viết log |
| `remainingCapacity()` | Trả snapshot số slot còn trống | Chỉ đo tham khảo, không thể thay thế kết quả enqueue |

### 5.1. Bỏ sự kiện mới: drop-new

```java
// Mã minh họa tích hợp: queue là BlockingQueue<LogEvent>,
// droppedEvents là counter và event là snapshot bất biến.
if (!queue.offer(event)) {
    droppedEvents.increment();
}
```

Ưu điểm: chi phí chờ thấp, queue không phát triển vô hạn. Nhược điểm: event quan trọng có thể mất, kể cả WARN/ERROR nếu tất cả dùng chung queue và không có cơ chế ưu tiên.

**Counter phải độc lập** với cùng pipeline logging đang bão hòa. Nếu dùng `logger.warn("Dropped event")` để đếm drop, cảnh báo có thể lại bị bỏ hoặc làm tình hình tệ hơn.

### 5.2. Chờ producer: block

```java
// Mã minh họa tích hợp, không tự chạy nếu thiếu queue/event.
try {
    queue.put(event);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Chính sách xử lý event chưa enqueue cần được quyết định rõ.
}
```

Điểm mạnh: giảm mất event vì queue tạm thời đầy khi consumer tiếp tục xử lý. Điểm yếu:

- Lời gọi logger chạy ở **request thread** có thể chặn khi giữ lock hoặc đang nằm trên đường request trọng yếu.
- Nhiều request bị block gây thiếu worker, timeout, retry và hiệu ứng dây chuyền.
- Nếu consumer vĩnh viễn không thể ghi hoặc đã ngừng, `put` có thể không tiến triển.
- `InterruptedException` không phải tình huống nên âm thầm nuốt; cần phục hồi cờ interrupt và xử lý event không được nhận.

### 5.3. Chờ có giới hạn: bounded wait

```java
// Đoạn tích hợp yêu cầu queue, event và droppedEvents.
try {
    boolean accepted =
            queue.offer(event, 20, TimeUnit.MILLISECONDS);
    if (!accepted) {
        droppedEvents.increment();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    droppedEvents.increment();
}
```

Cần import `java.util.concurrent.TimeUnit` và khai báo các biến theo hệ thống. **20 ms chỉ là ví dụ**, không phải ngưỡng khuyến nghị chung. Thời gian chờ cần nằm trong ngân sách p95/p99 của nghiệp vụ.

Lưu ý: tăng timeout không tăng throughput của sink. Timeout cũng không tạo guarantee rằng event đã ghi xong; nó chỉ giới hạn thời gian **đợi để vào queue**.

### 5.4. Không quyết định dựa trên kiểm tra `size()` rồi mới `put()`

Một sai lầm thường gặp:

```java
// Dễ xảy ra race khi có nhiều producer:
if (queue.remainingCapacity() > 0) {
    queue.put(event);
}
```

Sau khi kiểm tra, một producer khác có thể chiếm chỗ. `put` vẫn có thể chặn. Hãy dùng chính kết quả `offer`, `put` hoặc `offer(timeout)` để quyết định.

## 6. Java 17: minh họa `put()` phải đợi khi queue đầy

Ví dụ dưới tạo queue sức chứa 1, đặt sẵn một phần tử, rồi cho thread producer thứ hai dùng `put()`. Main giữ queue đầy cho tới khi nó `take()` phần tử đầu; chỉ sau đó producer mới có thể chèn sự kiện mới.

Lưu tệp **`BlockingQueueLogDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class BlockingQueueLogDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("INFO first");

        CountDownLatch producerStarted = new CountDownLatch(1);
        Thread producer = new Thread(() -> {
            try {
                producerStarted.countDown();
                queue.put("ERROR second");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "log-producer");

        producer.start();
        producerStarted.await();

        System.out.println("queue full: " + (queue.remainingCapacity() == 0));
        System.out.println("third accepted: " + queue.offer("DEBUG third"));

        String first = queue.take(); // Tạo chỗ cho producer đang chờ.
        producer.join();

        System.out.println("taken first: " + first);
        System.out.println("taken second: " + queue.take());
    }
}
```

Biên dịch và chạy:

```bash
javac BlockingQueueLogDemo.java
java BlockingQueueLogDemo
```

Kết quả `stdout` khi không bị interrupt từ bên ngoài:

```text
queue full: true
third accepted: false
taken first: INFO first
taken second: ERROR second
```

Ở đây `CountDownLatch` chỉ bảo đảm producer đã vào phần bắt đầu công việc; **không khẳng định scheduler đã đưa nó tới đúng lệnh `put`** trước khi main kiểm tra queue. Điều quan trọng vẫn được bảo đảm: queue ban đầu đầy, `offer("DEBUG third")` thất bại, và `ERROR second` chỉ có thể được chấp nhận sau `take()`. `join()` bảo đảm main không in phần tiếp theo trước khi producer hoàn tất.

Ví dụ này mô phỏng cơ chế **chặn người sản xuất**, không ghi log thực. Nó cho thấy “chọn block” có thể trì hoãn producer cho tới khi consumer giải phóng slot; thời gian chờ thực tế phụ thuộc tình trạng sink.

## 7. Các chính sách overflow và lựa chọn cho độ tin cậy

### 7.1. Drop-new

**Drop-new** từ chối event mới khi queue đầy. Có thể hợp lý với DEBUG/TRACE số lượng lớn nhưng nguy hiểm nếu tất cả sự kiện có cùng policy.

Ưu điểm: giữ độ trễ producer thấp. Đánh đổi: mất thông tin mới nhất, có thể bỏ cả sự kiện lỗi vừa phát sinh.

### 7.2. Drop-oldest

Một số thiết kế loại event cũ để nhường chỗ cho event mới. Cách này ưu tiên tính mới nhưng có thể xóa mất chuỗi sự kiện **dẫn tới lỗi**. `BlockingQueue` không tự cung cấp chính sách drop-oldest toàn cục chỉ qua `offer`; nếu triển khai, cần đồng bộ/race-safe để không làm sai ordering hay mất sự kiện ngoài ý muốn.

Không mặc định “bỏ cái cũ là an toàn”. Đặc biệt, audit hoặc log giao dịch có thể yêu cầu bảo toàn trình tự.

### 7.3. Discard theo mức hoặc sampling

Giảm tải trước khi hàng đợi đầy bằng cách tắt TRACE/DEBUG, sampling INFO nhiều lần lặp, giới hạn tần suất một mẫu lỗi hoặc tách các kênh có mức ưu tiên. Cần phân biệt **lọc có chủ đích** với **mất log do quá tải** để số liệu rõ ràng.

Log WARN/ERROR không được bảo vệ chỉ nhờ level cao nếu backend chọn drop mọi event khi queue đầy; phải hiểu cơ chế discarding và enqueue thực tế.

### 7.4. Synchronous fallback

Một số backend có chính sách khi không enqueue được thì **producer tự thực hiện ghi đồng bộ** hoặc chuyển sang appender khác. Điều này có thể cứu được một số log nhưng làm đường I/O chậm quay về thread nghiệp vụ. Nếu sink bị treo, “fallback” không còn là giải pháp nhanh.

Chỉ dùng khi biết rõ giới hạn chặn, xử lý lỗi sink, khả năng ghi trùng và lifecycle của appender phụ.

### 7.5. Durable buffer và queue riêng

Nếu một loại log **bắt buộc phải lưu** vì nghiệp vụ, bảo mật hoặc kiểm toán, không nên chỉ dựa vào queue in-memory của logging backend. Có thể cần:

- Bản ghi được persist cùng giao dịch hoặc qua transactional outbox khi phù hợp.
- Durable event queue có chính sách retry, acknowledgment, retention và hạn mức.
- Kiểm soát truy cập, bảo vệ tính toàn vẹn và quy trình đối soát.
- Chính sách xử lý khi chính kho lưu bền vững bị đầy hoặc không sẵn sàng.

Mỗi giải pháp đều có đánh đổi về độ trễ, phức tạp, ordering và chi phí. **Không tự hứa “exactly once”** chỉ vì có retry; retry có thể tạo bản sao trùng, cần ID và idempotency ở nơi nhận.

## 8. Logback AsyncAppender khi queue đầy

Với ứng dụng dùng **SLF4J + Logback Classic**, `ch.qos.logback.classic.AsyncAppender` đặt một hàng đợi có giới hạn trước appender thực sự ghi log. Các thuộc tính quan trọng liên quan đến độ tin cậy gồm:

- `queueSize`: số event tối đa trong queue.
- `discardingThreshold`: ngưỡng ít chỗ trống khiến Logback chủ động bỏ các event có mức ít quan trọng hơn theo chính sách mặc định của AsyncAppender Classic.
- `neverBlock`: quyết định hành vi enqueue có chờ khi queue đầy hay không.
- `maxFlushTime`: khoảng đợi tối đa cho worker xả queue khi appender dừng.
- `includeCallerData`: có thu thập caller data hay không, ảnh hưởng chi phí xử lý event.

Ví dụ cấu hình minh họa tại `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**Đây là ví dụ cấu hình cho dự án có Logback Classic tương thích**, không phải chương trình Java độc lập. Ý nghĩa:

1. Queue có **1024 event**, không phải 1024 bytes.
2. `discardingThreshold=0` tắt cơ chế **loại bỏ sớm** các event mức thấp theo ngưỡng không gian queue; không biến log thành dữ liệu bền vững.
3. `neverBlock=false` cho phép lời gọi logger **chặn khi queue thực sự đầy** cho tới khi còn chỗ. Đây là đánh đổi ưu tiên không loại do queue đầy trong điều kiện worker vẫn hoạt động.
4. `maxFlushTime=5000` đặt ngân sách đợi xả trong quá trình dừng appender là **5.000 ms**. Khi không kịp xả, vẫn có nguy cơ mất pending events. Với `maxFlushTime=0`, cơ chế shutdown của Logback đợi worker hoàn tất không giới hạn.
5. `includeCallerData=false` tránh chi phí thu thập nơi gọi log, không thay đổi chính sách đầy queue.

Ở Logback Classic, ngưỡng discarding mặc định thường liên quan **20% queue capacity**. Khi queue sắp đầy, Logback có thể bỏ các mức **TRACE/DEBUG/INFO** trước để ưu tiên mức cao hơn. Tuy nhiên:

- `discardingThreshold=0` chỉ vô hiệu hóa **bỏ sớm**, không chứng minh sẽ không bao giờ mất sự kiện.
- Nếu đặt `neverBlock=true`, enqueue khi queue đã đầy có thể bỏ **cả WARN/ERROR**. Do đó `neverBlock=true` ưu tiên latency hơn tính đầy đủ của log.
- `neverBlock=false` khi worker kẹt có thể gây **backpressure ngược về request thread**.
- Crash JVM, kill cưỡng bức, lỗi sink hoặc shutdown không đủ thời gian vẫn có thể làm mất dữ liệu chưa đến đích.
- Hành vi chi tiết cần kiểm chứng trên **phiên bản Logback và appender thực tế**.

Không có một tổ hợp `queueSize`/`neverBlock`/`maxFlushTime` đúng cho mọi hệ thống. Thí dụ log vận hành lưu lượng lớn có thể chấp nhận sampling/drop, còn audit cần một pipeline lưu bền vững riêng.

### 8.1. Khi bật neverBlock

Một cấu hình chọn latency thay vì chờ producer:

```xml
<!-- Đặt bên trong AsyncAppender ở trên. -->
<neverBlock>true</neverBlock>
```

Đây chỉ là **mảnh XML**. Khi queue đầy, producer có thể trả về nhanh hơn do không chờ slot, nhưng sự kiện không enqueue được có thể bị loại. Đừng coi việc phương thức logger trả về bình thường là bằng chứng log đã được ghi.

### 8.2. Logback có đảm bảo giữ ERROR không?

Không nên đưa ra cam kết tuyệt đối. Chính sách bỏ sớm có thể ưu tiên WARN/ERROR so với DEBUG/INFO, **nhưng** khi queue đầy và chọn `neverBlock=true`, một event mức cao vẫn có thể không được nhận. Với `neverBlock=false`, producer có thể bị chặn vô hạn khi consumer không tiến triển. Cả hai vẫn không chống được crash hay sự cố downstream.

Nếu ERROR phải được lưu phục vụ vận hành, kết hợp với metrics/alert độc lập và quy trình ghi sự kiện quan trọng ở kênh đáng tin cậy phù hợp, thay vì chỉ tin vào lựa chọn level.

## 9. Log4j 2 và các backend khác

**Log4j 2 Async Logger** và **Log4j 2 AsyncAppender** có các cơ chế bất đồng bộ và giới hạn nội bộ riêng. Ví dụ Async Logger thường dùng **ring buffer**; chính sách khi queue/ring buffer đầy có thể chọn chờ, chạy logging ở caller thread hoặc discard tùy cấu hình và phiên bản.

Khi điều tra Log4j 2:

1. Xác định thực tế đang dùng **Async Logger**, **AsyncAppender** hay kết hợp, vì hai loại không giống nhau.
2. Xem số phần tử/buffer capacity, queue-full policy, filter và ngưỡng discard của **đúng phiên bản**.
3. Kiểm tra một sự kiện được gọi từ thread nghiệp vụ có thể bị đẩy sang synchronous path khi quá tải hay không.
4. Kiểm thử throughput, độ trễ và số log thực sự đến sink; không suy luận từ tên “Async”.
5. Đánh giá shutdown và kết nối collector; một event ở ring buffer vẫn chưa được bảo đảm lưu bền vững.

Không sao chép `neverBlock`/`discardingThreshold` của Logback sang Log4j 2: các thuộc tính và cơ chế khác nhau. Với **`java.util.logging` (JUL)**, handler tiêu chuẩn thường xử lý đồng bộ theo thiết kế; chỉ khi ứng dụng hoặc thư viện bổ sung hàng đợi bất đồng bộ thì mới có khái niệm queue logging như trong bài.

## 10. “Đã enqueue” không đồng nghĩa “đã ghi”

Độ tin cậy của log có thể phân tầng:

```text
event created
    |
    v
accepted by in-memory queue
    |
    v
dequeued by logging worker
    |
    v
accepted by local file / stdout / network client
    |
    v
received by collector
    |
    v
persisted / replicated / acknowledged according to the sink
```

Một tầng đã thành công **không tự chứng minh** các tầng sau thành công. Ví dụ:

- Logger chấp nhận event, sau đó JVM crash trước khi worker dequeue.
- Worker chuyển event sang `stdout`, nhưng container/process kết thúc và agent không kịp thu thập.
- HTTP client báo gửi thành công, nhưng collector chỉ nhận vào bộ nhớ, chưa ghi bền vững.
- Retry sau timeout có thể làm xuất hiện **bản ghi trùng** dù event ban đầu đã tới đích.

Với file, `write()` hoặc `flush()` cũng không tự động đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ trong mọi tình huống; cần phân biệt buffer user-space, OS page cache và cơ chế `fsync` khi yêu cầu durability thật sự.

**Mục tiêu bảo đảm cần được ghi rõ**: best-effort diagnostic logs, at-most-once, at-least-once với duplicate, hay quy trình kiểm toán bền vững. Không nên dùng chữ “đảm bảo không mất log” nếu thực tế chỉ có một in-memory queue và graceful shutdown.

## 11. Khi queue chứa nhiều mức log

Nếu tất cả log dùng chung một queue, DEBUG/INFO ồ ạt có thể chiếm chỗ của WARN/ERROR. Những chiến lược cần cân nhắc:

- Giảm level ở nguồn cho những logger quá nhiều event.
- Giới hạn sampling hoặc rate limit những thông điệp lặp lại.
- Dùng filter ưu tiên bỏ sự kiện ít quan trọng hơn trước khi bão hòa, theo khả năng backend.
- Tách audit/security sang một pipeline có queue và yêu cầu durability riêng.
- Tránh bùng nổ exception stack trace cùng một lỗi trong vòng retry.
- Đặt hạn mức rõ cho số event và kích thước event; một sự kiện lớn có thể gây áp lực bộ nhớ/I/O nhiều hơn hàng trăm sự kiện ngắn.

**Tách queue không tự tạo độ tin cậy tuyệt đối**: các queue vẫn có thể dùng chung JVM, ổ đĩa, network và collector. Cần kiểm tra chúng có thực sự độc lập ở những điểm thất bại quan trọng hay không.

Có thể ưu tiên log WARN/ERROR ở một kênh riêng, nhưng nếu chúng chứa dữ liệu bí mật thì vẫn cần bảo vệ thông tin trước khi đưa sang sink khác. Severity cao không bỏ qua yêu cầu privacy.

## 12. Monitoring: biết queue sắp đầy trước khi xảy ra mất log

Một hệ thống tốt cần đo không chỉ “có log hay không” mà còn quá trình sản xuất, xếp hàng và giao nhận:

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `logging_queue_depth` | Số event hiện đang chờ |
| `logging_queue_capacity` | Dung lượng queue hữu hạn |
| `logging_queue_utilization` | Tỷ lệ queue đang bị chiếm |
| `logging_events_enqueued_total` | Số event được queue chấp nhận |
| `logging_events_dropped_total{reason,level}` | Số event bị bỏ theo lý do/mức |
| `logging_enqueue_wait_seconds` | Thời gian producer đợi khi enqueue |
| `logging_sink_write_seconds` | Độ trễ ghi xuống sink |
| `logging_sink_failures_total` | Lỗi ghi/gửi tới sink |
| `logging_oldest_event_age_seconds` | Thời gian sự kiện lâu nhất còn đang đợi |
| `logging_worker_alive` | Tình trạng worker xử lý queue |

Đây là **tên metric đề xuất**, không phải metric mặc định của tất cả backend. Nếu framework không bộc lộ metric, cần instrument appender phù hợp hoặc quan sát ở collector. Tên nhãn metric nên hữu hạn như `route`, `level`, `reason`; tránh dùng message, request ID hoặc user ID làm label vì cardinality cao.

Các tín hiệu cần theo dõi cùng nhau:

1. Queue depth **tăng kéo dài** ngay cả sau khi lưu lượng trở lại bình thường.
2. Tỷ lệ utilization cao nhiều phút hoặc tăng nhanh bất thường.
3. Số drop tăng — đặc biệt ở WARN/ERROR, security hoặc audit.
4. p95/p99 enqueue wait tăng làm request latency tăng theo.
5. Sink errors, disk usage, collector lag hoặc network retry tăng.
6. Tuổi event trong queue tăng, tức log xuất hiện trễ hơn thời điểm nó xảy ra.
7. Worker không còn hoạt động hoặc backlog không giảm dù có tải thấp.

**Đừng dùng một logger đang nghẽn để xuất metric báo queue đầy**: thông báo cảnh báo đó có thể cũng bị chặn hoặc bỏ. Metric, health signal hoặc kênh quản trị phải có đường quan sát độc lập phù hợp.

## 13. Shutdown, crash và drain queue

### 13.1. Graceful shutdown

Khi dừng ứng dụng, một quy trình tốt thường cần:

1. Ngừng nhận thêm request mới hoặc chặn producer mới ở điểm phù hợp.
2. Cho các tác vụ đang chạy hoàn tất trong một khoảng hợp lý.
3. Thông báo logging worker dừng nhận thêm event theo chính sách có thứ tự.
4. Xả queue và flush/close sink do ứng dụng sở hữu.
5. Đặt timeout shutdown và theo dõi số event còn tồn đọng nếu không xả kịp.

Vòng đời cụ thể thuộc về framework/backend. Ví dụ với Logback, quá trình `LoggerContext.stop()` có thể tham gia dừng appenders; cần thực hiện qua lifecycle chuẩn của ứng dụng. Không gọi `System.exit()` tùy tiện trong lúc queue còn event rồi kỳ vọng tất cả log xuất hiện.

### 13.2. Trường hợp không thể bảo đảm drain

Một JVM bị `kill -9`, mất điện, OS crash, OOM nghiêm trọng hoặc container bị dừng cưỡng bức có thể **không chạy shutdown hook** và không drain queue. Vì vậy chính sách “block khi đầy + flush lúc tắt” vẫn không phải bảo đảm durability.

Nếu cần lưu dữ liệu giao dịch hoặc audit, thiết kế cơ chế ghi có xác nhận và khả năng khôi phục, không phụ thuộc hoàn toàn vào JVM memory.

### 13.3. Tránh dừng vô hạn

Đợi drain không giới hạn có thể giúp giảm mất pending events trong một số trường hợp, nhưng sink đang treo có thể khiến shutdown không kết thúc. SLO về tắt dịch vụ, orchestration timeout và chính sách lỗi cần thống nhất. Khi dừng cưỡng bức sau deadline, phải công khai rằng log tồn đọng có thể chưa được ghi.

## 14. Kiểm thử queue đầy và tình huống mất log

Kiểm thử trong môi trường không phải production hoặc trên sink mô phỏng chậm, có số liệu đối chiếu được:

| Ca thử | Điều cần chứng minh |
| --- | --- |
| Burst ngắn | Queue tăng rồi giảm; không gây hại tới latency vượt SLO |
| Tải cao kéo dài | Queue đầy sau một thời gian; policy block/drop/timeout đúng như thiết kế |
| Sink chậm 10× | Producer bị chặn bao lâu; log nào bị bỏ; recovery bao lâu |
| Sink hoàn toàn không nhận | Có báo lỗi, metric tăng và đường request có được bảo vệ không |
| DEBUG burst + ERROR | ERROR có được ưu tiên như chính sách đã cam kết không |
| Log level đổi runtime | Có tăng tải hoặc đầy queue ngoài dự kiến không |
| Shutdown bình thường | Các event chờ được drain trong ngân sách nào |
| Kill cưỡng bức | Xác định rõ mức mất dữ liệu và khả năng đối soát |
| Collector hồi phục | Có log trùng do retry, log out-of-order hoặc backlog bùng nổ không |

Một kịch bản thử thực tế:

1. Khởi chạy phiên bản thử với bounded queue nhỏ và đếm event bằng ID cố định.
2. Cho sink chạy chậm có kiểm soát; bơm một lượng event đã biết.
3. Ghi **số event producer tạo**, **số queue nhận**, **số bị bỏ**, **số sink xác nhận**, và **số bản ghi cuối thực sự tồn tại**.
4. Quan sát cả **latency request** lẫn **thời gian chờ enqueue**.
5. Cho sink khôi phục, đợi queue drain bằng tín hiệu đồng bộ/metric thật thay vì chỉ `Thread.sleep(...)` tùy ý.
6. So sánh số lượng, ID mất và ID trùng theo chính sách đã thiết kế.

Nếu không có bảo đảm thứ tự/atomic fan-out, mỗi route có thể nhận một tập sự kiện khác nhau. Đừng dùng “logger đã gọi 1.000 lần” làm bằng chứng “đã lưu 1.000 bản ghi”.

## 15. Quy trình ứng phó khi queue đầy trên production

Khi monitoring báo queue đang gần bão hòa:

1. **Khoanh vùng đích ghi:** kiểm tra disk latency/disk-full, stdout collector, network, agent, dịch vụ thu thập log và các lỗi gần thời điểm backlog bắt đầu.
2. **Xác định nguồn bùng log:** package nào nhiều INFO/DEBUG, lỗi retry có đang lặp và stack trace có phình lớn không.
3. **Đo mức ảnh hưởng tới nghiệp vụ:** p95/p99 latency, số request đang block ở logger, thread pool, CPU/GC và số drop.
4. **Giảm tải có kiểm soát:** điều chỉnh level của logger nhiễu, sampling/rate limit thông điệp lặp, sửa lỗi phát sinh log storm; ghi nhận thời điểm bật/tắt DEBUG.
5. **Khôi phục khả năng tiêu thụ:** xử lý disk/collector/network và điều chỉnh hạ tầng khi có căn cứ.
6. **Cân nhắc thay đổi overflow policy:** nếu block làm dịch vụ ngừng đáp ứng, lựa chọn thay thế phải được chấp nhận rõ ràng cùng rủi ro mất log.
7. **Đối soát sau sự cố:** ghi nhận cửa sổ thời gian thiếu log, route ảnh hưởng, số drop và yêu cầu bổ sung bằng chứng từ các nguồn độc lập.

Chỉ tăng `queueSize` tại chỗ thường là **biện pháp trì hoãn**, không giải quyết bottleneck kéo dài. Nếu chưa xác định được sink chậm ở đâu, queue lớn hơn có thể làm quá tải heap và che giấu sự cố lâu hơn.

## 16. Các sai lầm phổ biến

### “Queue đầy nghĩa là tất cả log đã bị mất”

Không nhất thiết. Với policy block, producer có thể đợi cho tới khi có slot. Với drop-new, chỉ các event không enqueue được bị loại; các event đang ở queue vẫn có thể được worker ghi. Cần đo theo từng loại hành vi.

### “Queue không giới hạn sẽ không bao giờ đầy nên an toàn”

Queue không giới hạn có thể tăng tới khi JVM thiếu bộ nhớ; không phải phương án độ tin cậy bền vững. Nên giới hạn capacity theo ngân sách RAM và xác định rõ overflow policy.

### “Block là không bao giờ mất log”

Block có thể ngăn drop do thiếu slot khi consumer còn hoạt động, nhưng không chống được process crash, disk failure, collector loss, forced shutdown hoặc exception trong consumer. Nó còn có thể gây nghẽn request.

### “neverBlock=true mà WARN/ERROR vẫn chắc chắn an toàn”

Không chính xác với Logback AsyncAppender khi queue đã đầy. Cơ chế bỏ sớm thường ưu tiên WARN/ERROR, nhưng policy enqueue không chặn vẫn có thể loại event mức cao.

### “Đã gọi logger là đã lưu”

Không đúng với async logging: một lời gọi có thể chỉ tạo event, hoặc bị filter bỏ trước khi queue nhận. Ngay cả enqueue thành công cũng chưa chứng minh durable storage.

### “Chỉ theo dõi queue size là đủ”

Queue size là snapshot. Số drop, thời gian enqueue, queue age, sink errors, rate và backlog recovery mới phản ánh được hậu quả. Một queue vừa rỗng có thể do sink khỏe hoặc do events đang bị bỏ từ sớm.

### “Đếm drop bằng chính appender đang lỗi”

Thông báo thống kê có thể lại bị mất và còn tạo thêm event. Hãy dùng counter/metric độc lập, có đường giám sát riêng.

### “Thêm retries vô hạn giúp tránh mất mọi log”

Retry vô hạn có thể làm queue tăng, gây duplicate, khiến request bị chặn và tạo thêm log lỗi. Cần retry budget, backoff, durable storage khi phù hợp và idempotency ở nơi nhận.

### “Một cấu hình phù hợp cho cả audit và debug”

Không phù hợp khi yêu cầu khác nhau. DEBUG có thể sampling/drop; audit có thể cần giao dịch, durability, retention, quyền truy cập và đối soát riêng.

## 17. Checklist thiết kế trước khi triển khai

- [ ] Xác định producer rate trung bình/đỉnh, tốc độ sink bền vững và kích thước event.
- [ ] Chọn queue **hữu hạn**, memory budget, giới hạn độ trễ và chính sách khi đầy.
- [ ] Làm rõ event nào được phép drop, event nào cần ưu tiên hoặc lưu bền vững.
- [ ] Kiểm tra backend/framework thực tế và semantic của `neverBlock`, discard, timeout, flush.
- [ ] Không để level DEBUG/INFO chiếm mất nguồn lực dành cho log nghiệp vụ quan trọng mà không có quyết định rõ.
- [ ] Gắn metrics: enqueued, dropped, queue depth, oldest age, enqueue latency, sink errors.
- [ ] Kiểm thử sink chậm, sink lỗi, bão hòa kéo dài, recovery, shutdown và kill cưỡng bức.
- [ ] Phân biệt accepted, written, acknowledged, durable; không hứa quá khả năng pipeline.
- [ ] Có runbook khôi phục và cách đối soát số lượng log thiếu/trùng sau sự cố.

**Kết luận:** Queue đầy là dấu hiệu **pipeline logging không theo kịp**. Để tăng độ tin cậy, không chỉ tăng sức chứa mà cần xác định chính sách rõ ràng cho từng loại event, đo số log bị chặn/bỏ, biết cách sink thất bại và kiểm chứng hành vi khi shutdown. Đối với dữ liệu bắt buộc lưu, **queue trong RAM của async logger không thể thay thế cơ chế ghi bền vững có xác nhận**.
