# Tránh tác vụ chặn hoặc xử lý quá nặng trong callback JFR EventStream (Java 14+)

## 1. Vấn đề: callback nhận sự kiện không phải nơi làm toàn bộ công việc

Java Flight Recorder (JFR) cung cấp dữ liệu sự kiện về hoạt động của JVM và những sự kiện do ứng dụng tự định nghĩa. Với `jdk.jfr.consumer.EventStream` và `jdk.jfr.consumer.RecordingStream`, ta đăng ký callback `onEvent(...)` để nhận từng `RecordedEvent` khi luồng đọc được dữ liệu.

Ví dụ tối giản:

```java
// Snippet bên trong try (RecordingStream stream = new RecordingStream()).
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));
stream.onEvent("jdk.CPULoad", event -> {
    System.out.println(event.getFloat("machineTotal"));
});
stream.startAsync();
```

Trong ví dụ nhỏ, in ra console trông vô hại. Nhưng nếu mỗi callback gọi API từ xa, ghi database, chờ khóa hoặc chạy thuật toán lớn, **thread tiêu thụ JFR event** phải đợi các tác vụ đó xong mới tiếp tục xử lý những callback tiếp theo.

Điều này đặc biệt quan trọng vì **`EventStream.startAsync()` thực hiện các action trên một thread riêng duy nhất** theo hợp đồng API hiện hành; nó **không tự mở một worker thread cho từng event**. Với `start()`, các action chạy **trên chính thread gọi `start()`**. Trong cả hai kiểu, callback chậm có thể làm quá trình xử lý sự kiện bị trì hoãn.

**Bài học:** Callback JFR nên **nhận – lọc – chụp dữ liệu cần thiết – chuyển giao nhanh**. Những thao tác có thể mất thời gian đáng kể hoặc chặn không dự đoán được nên được thực hiện bên ngoài callback, với hàng đợi có giới hạn, thread/worker riêng và chiến lược xử lý quá tải.

### Tính năng và phiên bản

- `EventStream` và `RecordingStream` xuất hiện từ **Java 14** qua [JEP 349 – JFR Event Streaming](https://openjdk.org/jeps/349), và vẫn là các API được hỗ trợ trong JDK hiện đại.
- Ví dụ của bài dùng Java 17+ với module chuẩn `jdk.jfr`, `java.util.concurrent` và cú pháp `record` đã ổn định. Không có preview flag hay kỹ thuật đã lỗi thời.
- Các tài liệu Oracle Java 17/25 đều mô tả `startAsync`, `onEvent`, `onError`, `setReuse` và lifecycle của stream. Một ứng dụng còn cần bản phân phối JVM có hỗ trợ JFR.

## 2. Callback JFR thực sự chạy ở đâu?

Sơ đồ luồng xử lý khái quát:

```text
Code trong JVM gọi Event.commit()
             |
             v
     JFR recording / repository
             |
             v
      EventStream tiêu thụ
             |
             v
    một thread xử lý action
             |
             +-- onEvent("name1", handler1)
             +-- onEvent("name2", handler2)
             +-- onFlush(...) / các action khác
             |
             v
        batch tiếp theo
```

JFR có thể đưa sự kiện tới consumer **theo từng batch**, sau khi dữ liệu được ghi/flush. Sự kiện không nhất thiết đến callback ngay tại thời điểm `Event.commit()` được gọi. Nếu callback phải chờ vài trăm mili-giây hoặc vài giây, thời gian đó chiếm chỗ trên tuyến tiêu thụ.

**Phân biệt chính xác:**

- **Thread sản sinh event:** thread đang chạy logic ứng dụng và gọi `Event.commit()`; nó không mặc nhiên là thread gọi callback.
- **Thread xử lý stream:** thread chạy các action đã đăng ký qua `onEvent`; `startAsync()` dùng một thread riêng, `start()` dùng thread hiện tại.
- **Worker xử lý nặng:** thread/executor do ứng dụng **tự thiết kế** để làm việc tốn thời gian sau khi đã lấy dữ liệu ra khỏi callback.

Callback chậm **không đồng nghĩa** tất cả thread ứng dụng sẽ bị chặn ngay, và cũng không có một cam kết rằng JFR sẽ “mất toàn bộ event” ngay lập tức. Hệ quả thực tế có thể là tăng **độ trễ tiêu thụ**, backlog, áp lực bộ nhớ/disk hoặc mất dữ liệu tùy cấu hình và giới hạn hệ thống. Khi đánh giá, phải đo đạc chứ không suy diễn một hậu quả cố định cho mọi JVM.

### So sánh `start()` và `startAsync()`

| Phương thức | Nơi chạy action | Hệ quả khi callback chậm |
| --- | --- | --- |
| `stream.start()` | Thread gọi `start()` | Lời gọi start không trở về khi stream còn chạy; callback chậm giữ thread này |
| `stream.startAsync()` | **Một thread riêng** tiêu thụ stream | Thread gọi tiếp tục làm việc, nhưng thread callback riêng vẫn bị chậm |
| `stream.onEvent(name, consumer)` | Chỉ đăng ký action | Không tự khởi chạy stream hoặc tạo worker cho mỗi event |

Không nên giải quyết callback chậm bằng suy luận rằng “đã gọi `startAsync()` thì toàn bộ callback tự động chạy song song”. **Bất đồng bộ với caller** không đồng nghĩa **song song mọi callback**.

## 3. Những thao tác không nên đặt trực tiếp trong `onEvent`

Trong callback, cần hạn chế những hành động có **độ trễ không giới hạn** hoặc nhiều biến động:

1. **I/O đồng bộ:** gọi HTTP, tải file, ghi database, gửi request mạng chờ phản hồi hoặc ghi log đồng bộ với chi phí lớn.
2. **Chờ:** `Thread.sleep`, `CountDownLatch.await`, `Future.get`/`join`, `wait` hoặc vòng chờ điều kiện mà không biết bao giờ thành công.
3. **Hàng đợi có thể chặn:** `BlockingQueue.put` hoặc `offer(item, timeout, unit)` khi hàng đợi đã đầy, nếu mục tiêu callback phải phản hồi nhanh.
4. **Khóa tranh chấp:** `synchronized` ở vùng tranh chấp lớn, lock được giữ lâu, hoặc phối hợp với một thread đang đợi stream xử lý xong.
5. **Xử lý CPU nặng:** parse một payload rất lớn, truy vấn nhiều dữ liệu phụ, sắp xếp/tổng hợp lớn, chuyển đổi dữ liệu phức tạp.
6. **Xuất tất cả event ra console:** `System.out.println` trong callback có thể thành nút thắt cổ chai khi event đến dày; I/O console không phải giải pháp telemetry hiệu năng cao.
7. **Quản lý lifecycle chờ đợi:** đặc biệt **`RecordingStream.stop()` bên trong callback**, vì Javadoc cảnh báo thao tác này có thể chặn stream **vô thời hạn**. Hãy để thread quản lý riêng quyết định dừng/đóng stream.

**Ví dụ cần tránh:**

```java
// Snippet: rất nguy hiểm nếu event xuất hiện nhiều.
stream.onEvent("lesson.TaskSample", event -> {
    String id = event.getString("taskId");
    database.save(id);            // I/O không đoán trước thời gian.
    remoteService.notify(id);     // Chờ mạng.
    Thread.sleep(1000);           // Chặn tuyến xử lý stream.
});
```

Đoạn này là **minh họa anti-pattern**, không phải source Java có thể biên dịch độc lập: nó giả định có `database`, `remoteService`, và `Thread.sleep` cần xử lý `InterruptedException`. Không sao chép như một hàm thực tế.

Không phải tất cả việc làm trong callback đều bị cấm. Đọc vài trường nhỏ bằng `event.getString(...)`/`getInt(...)`, so sánh nhanh, tăng counter nhẹ và đưa **snapshot nhỏ** vào queue thường là công việc hợp lý. Ngưỡng thế nào là “nhẹ” cần được kiểm nghiệm theo **tần suất event, tải, latency mục tiêu và môi trường JVM**.

## 4. Mô hình nên dùng: callback ngắn + hàng đợi có giới hạn + worker riêng

Một kiến trúc cơ bản:

```text
                  RecordingStream
                        |
                 onEvent(...) rất ngắn
                        |
              đọc / chụp trường cần thiết
                        |
                queue.offer(snapshot)
                      /     \
               nhận được     queue đầy
                   |             |
                   v             v
              bounded queue   tăng dropped
                   |
                   v
              worker thread
                   |
              xử lý tốn thời gian
               (I/O, tổng hợp...)
                   |
                   v
              kết quả / metric
```

**Chìa khóa:**

- **Callback không làm tác vụ dài.**
- **Hàng đợi có giới hạn dung lượng:** tránh chuyển nút thắt từ callback sang bộ nhớ không giới hạn.
- **`offer(item)` không đợi cho có ô trống:** nếu queue đầy, trả `false`; ứng dụng quyết định đếm mất mẫu, lấy mẫu ít hơn, gộp thống kê hoặc đưa cảnh báo. `ArrayBlockingQueue.offer` có thể cần một khóa ngắn nội bộ; “không chờ queue hết đầy” **không có nghĩa hoàn toàn lock-free**.
- **Worker** được phép làm việc chậm và phải có chiến lược timeout, retry, xử lý lỗi và dừng.
- **Không chuyển trực tiếp `RecordedEvent` sang worker** nếu stream có thể tái sử dụng object; hãy chụp các trường cần thiết ra object độc lập.

### Tại sao phải chụp dữ liệu thay vì đưa `RecordedEvent` vào queue?

Javadoc `EventStream` có quy tắc rất quan trọng: **mặc định một object `RecordedEvent` có thể được tái sử dụng để biểu diễn nhiều sự kiện khác nhau**. Khi bật `stream.setReuse(true)`, object được nhận trong callback **không được giữ tham chiếu để sử dụng sau khi callback kết thúc**. Nếu đưa chính `RecordedEvent` vào queue, worker có thể đọc nó sau khi stream tái sử dụng và nhận **dữ liệu của event khác**.

Cách đúng với dữ liệu đơn giản:

```java
// Một kiểu immutable dùng để sao chép dữ liệu trong callback.
record TaskData(String taskId, int amount) {}

// Trong callback onEvent:
TaskData snapshot = new TaskData(
        event.getString("taskId"),
        event.getInt("amount"));
queue.offer(snapshot);
```

Đoạn này là **snippet**, không phải chương trình đầy đủ: cần biến `event` và `queue`. `TaskData` chứa `String` bất biến và `int` nguyên thủy, vì vậy đã tách dữ liệu khỏi object JFR có thể tái sử dụng.

Đối với field mang dữ liệu có khả năng mutable (mảng, collection, object tùy chỉnh), **snapshot phải có chính sách sao chép phù hợp**; không được mặc định mọi object con là bất biến. Với dữ liệu nhiều trường, chỉ trích xuất những gì worker thực sự cần để tránh tăng overhead callback.

Có thể chọn `stream.setReuse(false)` để JFR tạo object event mới cho mỗi event. Nhưng lựa chọn này **tăng chi phí cấp phát** và không giải quyết hàng đợi vô hạn, logic xử lý nặng hoặc data transfer thiếu giới hạn. **Mặc định an toàn và hiệu quả thường là copy các giá trị nhỏ cần thiết**, kể cả khi có tùy chọn không tái sử dụng.

## 5. Chương trình Java 17+ hoàn chỉnh: JFR event thật, queue bounded, worker riêng

Ví dụ sau tạo một JFR event tùy chỉnh, nhận dữ liệu trong callback, chuyển dữ liệu qua **`ArrayBlockingQueue` dung lượng 32**, rồi dùng thread riêng để làm tác vụ giả lập mất 20 ms. Phần chờ là ở **worker**, không ở callback.

Chương trình tự kiểm tra rằng event thực sự được worker xử lý và thread callback khác worker thread. Nó có thời gian chờ hữu hạn thay vì đợi vô hạn; không phụ thuộc một lần commit sẽ được deliver ngay.

Tạo tệp **`JfrCallbackQueueDemo.java`**:

```java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class JfrCallbackQueueDemo {
    @Name("lesson.TaskSample")
    public static class TaskSample extends Event {
        public String taskId;
        public int amount;
    }

    record TaskData(String taskId, int amount) {}

    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<TaskData> queue = new ArrayBlockingQueue<>(32);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicBoolean running = new AtomicBoolean(true);
        AtomicReference<String> result = new AtomicReference<>();
        AtomicReference<Thread> callbackThread = new AtomicReference<>();
        AtomicReference<Throwable> callbackError = new AtomicReference<>();
        AtomicReference<Throwable> workerError = new AtomicReference<>();
        AtomicLong dropped = new AtomicLong();

        Thread worker = new Thread(() -> {
            try {
                while (running.get() || !queue.isEmpty()) {
                    TaskData task = queue.poll(100, TimeUnit.MILLISECONDS);
                    if (task == null) continue;

                    Thread.sleep(20); // Việc chậm nằm ngoài callback!
                    if ("JOB-42".equals(task.taskId())) {
                        result.set(task.taskId().toLowerCase(Locale.ROOT)
                                + ":" + task.amount());
                        completed.countDown();
                    }
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } catch (Throwable failure) {
                workerError.compareAndSet(null, failure);
                completed.countDown();
            }
        }, "jfr-work-queue-consumer");
        worker.start();

        try (RecordingStream stream = new RecordingStream()) {
            String eventName = EventType
                    .getEventType(TaskSample.class).getName();

            stream.enable(TaskSample.class).withoutThreshold();
            stream.setReuse(true);

            stream.onEvent(eventName, event -> {
                try {
                    callbackThread.set(Thread.currentThread());

                    // Sao chép ngay dữ liệu cần thiết.
                    TaskData snapshot = new TaskData(
                            event.getString("taskId"),
                            event.getInt("amount"));

                    // Không chờ queue có chỗ trống.
                    if (!queue.offer(snapshot)) {
                        dropped.incrementAndGet();
                    }
                } catch (Throwable failure) {
                    callbackError.compareAndSet(null, failure);
                }
            });

            stream.onError(error ->
                    callbackError.compareAndSet(null, error));
            stream.startAsync();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(12);

            while (completed.getCount() != 0
                    && System.nanoTime() < deadline
                    && callbackError.get() == null) {
                TaskSample e = new TaskSample();
                e.taskId = "JOB-42";
                e.amount = 7;
                e.commit();

                // Thread main chờ; callback JFR không chờ.
                completed.await(200, TimeUnit.MILLISECONDS);
            }

            if (callbackError.get() != null) {
                throw new AssertionError(
                        "JFR callback failed", callbackError.get());
            }
            if (workerError.get() != null) {
                throw new AssertionError(
                        "Worker failed", workerError.get());
            }
            if (completed.getCount() != 0) {
                throw new AssertionError(
                        "Timed out without a processed event");
            }
            if (callbackThread.get() == null
                    || callbackThread.get() == worker) {
                throw new AssertionError(
                        "Callback was not separated from worker");
            }
            if (!"job-42:7".equals(result.get())) {
                throw new AssertionError("Wrong worker output");
            }

            System.out.println("eventName=" + eventName);
            System.out.println("queueCapacity=32");
            System.out.println("offloaded=true");
            System.out.println("processed=" + result.get());
            System.out.println("callbackError=false");
            System.out.println("workerError=false");
        } finally {
            running.set(false);
            worker.interrupt();
            worker.join(2000);

            if (worker.isAlive()) {
                throw new AssertionError(
                        "Worker did not terminate");
            }
        }
    }
}
```

**Biên dịch và chạy** bằng JDK 17+ có hỗ trợ JFR:

```bash
javac --release 17 -encoding UTF-8 JfrCallbackQueueDemo.java
java JfrCallbackQueueDemo
```

**Standard output khi ví dụ chạy đạt:**

```text
eventName=lesson.TaskSample
queueCapacity=32
offloaded=true
processed=job-42:7
callbackError=false
workerError=false
```

Đây là output của những dòng `System.out.println` trong `main`, **không phải output tự động của logger JFR**. Chương trình sẽ ném `AssertionError` nếu không nhận được event trong thời hạn 12 giây, callback phát sinh lỗi, worker lỗi hoặc thread xử lý callback bị nhầm với worker.

### 5.1. Bật event, đăng ký handler và bắt đầu luồng

`@Name("lesson.TaskSample")` xác định tên loại event. `EventType.getEventType(...).getName()` lấy đúng tên này để dùng cho `onEvent(eventName, ...)`.

`stream.enable(TaskSample.class).withoutThreshold()` bật sự kiện tùy chỉnh và không dùng threshold thời lượng để bỏ qua những event cực ngắn. `startAsync()` bắt đầu tuyến xử lý trên một thread riêng.

Điều này là **bài demo**: với production, lựa chọn threshold và event type phải phù hợp lượng telemetry muốn thu. Không nên luôn bật `withoutThreshold()` cho mọi event tần suất cao nếu không có lý do.

### 5.2. Callback không lưu `RecordedEvent` mà chụp `TaskData`

```java
stream.onEvent(eventName, event -> {
    try {
        callbackThread.set(Thread.currentThread());

        TaskData snapshot = new TaskData(
                event.getString("taskId"),
                event.getInt("amount"));

        if (!queue.offer(snapshot)) {
            dropped.incrementAndGet();
        }
    } catch (Throwable failure) {
        callbackError.compareAndSet(null, failure);
    }
});
```

Đây là đoạn được trích lại từ chương trình đầy đủ. Trong callback:

1. Chỉ lấy tên task, lượng `amount` và thread callback.
2. Gói dữ liệu vào **`record TaskData`**, không giữ `RecordedEvent` sau callback khi `setReuse(true)`.
3. Gọi `queue.offer(snapshot)`, không gọi `put(snapshot)`. Queue đầy thì tăng bộ đếm `dropped`, **không đứng đợi worker giải phóng chỗ**.
4. Ghi nhận lỗi vào `AtomicReference` mà không thực hiện I/O hoặc logging nặng trong callback.

`dropped` được tạo để minh họa **chính sách mất mẫu có đo lường**. Bản demo không in số event bị bỏ, vì số này phụ thuộc số batch, thời điểm callback và tải JVM. Production cần xuất metric phù hợp theo chu kỳ **ngoài callback**, ví dụ số event được nhận, số đã xử lý, số bị bỏ và độ dài queue.

**Chi tiết độ phức tạp:** `ArrayBlockingQueue.offer` có đồng bộ nội bộ ngắn; nó không đợi queue có slot trống, nhưng không phải là primitive lock-free hoặc cam kết chạy với latency tuyệt đối không đổi trong mọi môi trường.

### 5.3. Worker là nơi thực hiện tác vụ chậm

Worker dùng `queue.poll(100, TimeUnit.MILLISECONDS)` và `Thread.sleep(20)` để giả lập tính toán/I/O tốn thời gian. Hai lời gọi **có thể chờ**, nhưng chúng nằm trong worker, không nằm trên tuyến tiêu thụ JFR.

Trong code ứng dụng thực tế, phần chậm có thể là ghi batch vào database, phân tích dữ liệu hoặc tổng hợp thống kê. Nếu task quan trọng, cần bổ sung timeout, retry có giới hạn, idempotency, chính sách lỗi và quản lý executor phù hợp.

`CountDownLatch` đồng bộ thread `main` với **worker đã xử lý ít nhất một task**. Các biến `AtomicReference` trao đổi kết quả/lỗi giữa các thread. Vòng lặp commit có deadline 12 giây để tránh kết luận sai chỉ vì sự kiện JFR chưa được flush ngay sau lần phát đầu tiên.

### 5.4. Dừng stream và worker đúng vòng đời

`RecordingStream` được đóng bằng `try-with-resources`. Sau đó khối `finally` đặt `running=false`, gọi `interrupt()` và `join(2000)` cho worker.

**Giới hạn của demo:** Khi shutdown, interrupt có thể khiến worker bỏ phần còn trong queue; bài thử chỉ yêu cầu xử lý được **một** sự kiện, không cam kết tiêu thụ tất cả dữ liệu đã phát. Với một pipeline không cho phép mất event, không thể sao chép nguyên chính sách shutdown của demo; cần cơ chế **dừng nhận → xử lý hết dữ liệu được chấp nhận → xác nhận đã hoàn thành → đóng tài nguyên** và timeout có kiểm soát, đồng thời chấp nhận đặc tính buffering/flush của JFR.

Javadoc `EventStream.close()` nói rõ **không bảo đảm tất cả action đã đăng ký hoàn tất trước khi close trả về**. Vì vậy, nếu ứng dụng cần bảo đảm đã xử lý xong, phải thiết kế cơ chế đồng bộ riêng; không lấy việc `close()` trả về làm bằng chứng đã hoàn tất mọi event.

## 6. Vì sao dùng queue bounded thay vì queue vô hạn?

Chuyển công việc khỏi callback giải quyết **blocking trực tiếp**, nhưng một queue không có giới hạn có thể khiến ứng dụng cạn heap nếu event đến nhanh hơn worker xử lý.

Gọi:

- `λ`: tốc độ event/giây đi vào queue sau lọc.
- `μ`: tốc độ worker có thể xử lý event/giây.
- `Q`: số phần tử đang chờ trong queue.

Khi **`λ > μ` kéo dài**, số phần tử chờ sẽ tăng; nếu queue không bị giới hạn, bộ nhớ tăng cho tới khi nguồn event giảm, worker nhanh hơn hoặc ứng dụng gặp vấn đề tài nguyên. Một queue bounded biến rủi ro đó thành **quyết định quá tải rõ ràng** khi queue đầy.

### Ba chiến lược khi queue đầy

| Chiến lược | Trong callback | Đổi lại |
| --- | --- | --- |
| **Bỏ event mới và tăng metric** | `if (!queue.offer(snapshot)) dropped.incrementAndGet();` | Mất một số telemetry nhưng callback không đợi slot |
| **Gộp số liệu** | Cập nhật counter/summary nhẹ | Giảm độ chi tiết, giữ trend hữu ích |
| **Điều tiết nguồn/thu hẹp sự kiện** | Cấu hình JFR event type, period, threshold ở tầng điều khiển | Có thể ít dữ liệu được ghi hơn, giảm overhead nguồn |

**Không nên mặc định dùng `queue.put(snapshot)`** trong callback khi queue đầy. `put` là lời gọi **có thể chặn cho tới khi có chỗ**, tức là chuyển vấn đề backlog thành **callback bị treo**.

Trong hệ thống có yêu cầu **không được mất bất kỳ event nghiệp vụ nào**, JFR streaming + một queue cố ý drop **không phải kênh nghiệp vụ đáng tin cậy duy nhất**. Hãy chọn cơ chế message/broker hoặc log giao dịch có xác nhận/độ bền phù hợp; JFR được thiết kế cho quan sát/chẩn đoán JVM. Nếu telemetry phải không mất mẫu, cần thiết kế durability, retry và end-to-end acknowledgment ngoài scope của callback JFR.

### Cân nhắc độ sâu queue

Không có con số “32”, “1.000” hay “10.000” đúng cho mọi ứng dụng. Chọn từ:

- Kích thước trung bình và đỉnh của snapshot (bytes/phần tử).
- Tốc độ event nhận trung bình và burst (`λ`).
- Tốc độ worker xử lý thực tế (`μ`), bao gồm thời gian chờ I/O.
- Giới hạn độ trễ chấp nhận được: queue lớn hơn có thể **tăng độ trễ sự kiện**.
- Bộ nhớ dành cho telemetry và các hệ thống khác trong JVM.
- Mức độ chấp nhận mất mẫu hoặc giữ dữ liệu tổng hợp khi quá tải.

Số queue chỉ là một phần. Chương trình cũng cần giám sát tốc độ nhận, tốc độ xử lý, độ trễ, tuổi phần tử lâu nhất và số event bị drop.

## 7. Tránh lỗi với `RecordedEvent` được tái sử dụng

Đây là một điểm khác biệt quan trọng giữa callback JFR và nhiều callback xử lý dữ liệu thông thường.

Theo Javadoc `EventStream`, cùng **một object `RecordedEvent`** có thể dùng đại diện cho nhiều event khác nhau, **kể cả được đưa vào nhiều action**. Khi `setReuse(true)`, object có thể được tái dùng sau khi action kết thúc.

**Anti-pattern:**

```java
// Snippet minh họa, KHÔNG an toàn khi stream cho phép reuse:
BlockingQueue<RecordedEvent> queue = ...;
stream.onEvent("lesson.TaskSample", event -> queue.offer(event));
```

Nếu worker đọc object sau khi callback return, nội dung có thể không còn thuộc event ban đầu. Đây không phải chỉ là vấn đề queue đầy hay race với tài nguyên bên ngoài; **chính object của API có thể bị tái sử dụng theo hợp đồng**.

**Đúng hơn:**

```java
// Snippet minh họa:
record TaskData(String taskId, int amount) {}

stream.onEvent("lesson.TaskSample", event -> {
    TaskData snapshot = new TaskData(
            event.getString("taskId"),
            event.getInt("amount"));
    queue.offer(snapshot);
});
```

Nếu muốn tham khảo một `RecordedEvent` sau callback, có thể đặt `setReuse(false)` để yêu cầu cấp phát object riêng cho mỗi event. Tuy nhiên, vẫn cần xem xét tính bất biến sâu của nội dung muốn giữ, áp lực heap, kích thước hàng đợi, vòng đời của stream và giới hạn số event. Đối với phần lớn callback chỉ cần vài trường, **snapshot tối thiểu** dễ kiểm soát hơn.

### Chụp dữ liệu giá trị nào?

- Trường primitive: `getInt`, `getLong`, `getBoolean`… để lưu giá trị đơn giản.
- Chuỗi hoặc tên loại event: `getString`, `getEventType().getName()` khi cần.
- Timestamp/duration: `getStartTime()`, `getEndTime()`, `getDuration()` khi bài toán cần đo đạc.
- Stack trace/cấu trúc phức tạp: chỉ lấy khi cần, vì đọc và sao chép nhiều đối tượng có thể đắt; không chuyển cả graph lớn qua queue nếu downstream chỉ cần counter.

Không cố gắng “serialize tất cả thuộc tính” của một `RecordedEvent` trong callback khi chỉ cần vài trường. Giảm công việc trong callback ngay từ khâu chọn event và chọn field.

## 8. Error handling trong callback và luồng xử lý ngoài

`EventStream.onError(Consumer<Throwable>)` cho phép đăng ký action khi một callback/stream phát sinh lỗi không mong đợi:

```java
// Snippet: AtomicReference<Throwable> error đã được khởi tạo.
stream.onError(cause -> error.compareAndSet(null, cause));
```

**Không đăng ký `onError`** thì mặc định JFR sẽ in ngoại lệ cùng backtrace ra `System.err`. Khi đã đăng ký handler, chương trình tự chịu trách nhiệm có chiến lược quan sát lỗi thích hợp. Javadoc còn cảnh báo **nếu chính error handler ném exception thì kết quả không được xác định**, nên action `onError` phải ngắn và đáng tin cậy.

Ví dụ hoàn chỉnh sử dụng:

```java
AtomicReference<Throwable> callbackError = new AtomicReference<>();
stream.onError(error ->
        callbackError.compareAndSet(null, error));
```

Đó chỉ là một **đường báo lỗi trong demo**. Production không nên chỉ giữ một `AtomicReference` rồi bỏ mặc nó; cần một kênh giám sát/lifecycle riêng để ghi hoặc cảnh báo, vẫn **giữ đối tượng `Throwable` và stack trace** thay vì chỉ `getMessage()`.

**Với worker xử lý nặng:** lỗi phát sinh trong worker **không nhất thiết đi qua `stream.onError`**, vì nó nằm ngoài callback JFR. Worker phải có handler, metric, retry và shutdown policy riêng. Demo có `workerError` và kiểm tra nó sau khi hoàn tất.

### Bắt `Throwable` trong callback có nên làm thường xuyên?

Mã demo bắt `Throwable` chỉ để **báo lỗi về main thread** một cách xác định trong bài thử. Trong ứng dụng sản xuất, bắt rộng như vậy cần cân nhắc vì `Throwable` còn bao gồm những `Error` nghiêm trọng (ví dụ vấn đề bộ nhớ). Thường nên để error handler của EventStream xử lý ngoại lệ callback hoặc bắt **những exception có thể khôi phục**, đồng thời giữ chính sách rõ ràng với lỗi không thể khôi phục.

**Tuyệt đối tránh** biến `onError` thành một callback mới làm network/database call kéo dài hoặc lại ném thêm exception.

## 9. Lifecycle: không gọi `RecordingStream.stop()` từ `onEvent`

Một trường hợp dễ gây treo:

```java
// Anti-pattern: đừng gọi stop() trong chính action của stream.
stream.onEvent("lesson.TaskSample", event -> {
    stream.stop();
});
```

Javadoc `RecordingStream.stop()` chỉ rõ phương thức này **dừng recording stream và chờ cho tất cả event đã được ghi được tiêu thụ**; gọi nó ngay từ một action như `onEvent` **có thể khiến stream bị chặn vô hạn**. Callback đang chờ stream xử lý xong, nhưng stream phải chờ callback hiện tại return: đây là dạng bế tắc cần tránh.

**Cách phù hợp hơn:** callback ghi một **cờ hoặc tín hiệu nhẹ**, rồi thread điều khiển bên ngoài callback quyết định khi nào `stop()`/`close()`. Chỉ thread quản lý mới cần thực hiện chờ.

```java
// Snippet: yêu cầu dừng từ callback.
AtomicBoolean stopRequested = new AtomicBoolean(false);
stream.onEvent("lesson.TaskSample", event -> {
    if (shouldStop(event)) {    // Giả định check này cực nhanh.
        stopRequested.set(true);
    }
});
// Thread quản lý định kỳ kiểm tra stopRequested rồi đóng stream.
// Không gọi stop() trực tiếp trong onEvent.
```

Snippet cần `stream`, `shouldStop` và thread quản lý đã được định nghĩa ở nơi khác. Trong một ứng dụng thực tế, có thể dùng `CountDownLatch` hoặc một notification channel ngoài callback thay cho polling.

**Khác biệt giữa `stop()` và `close()`:** `close()` yêu cầu dừng và giải phóng tài nguyên; theo `EventStream`, **không bảo đảm mọi action đã hoàn thành khi close trả về**. `stop()` có ý nghĩa chờ tiêu thụ các event của stream, vì vậy đặc biệt nguy hiểm nếu gọi từ chính thread đang tiêu thụ. Thiết kế lifecycle cần nêu rõ có muốn **drain dữ liệu** hay dừng nhanh.

## 10. Giảm lượng dữ liệu ngay tại nguồn

Offload không thay thế nhu cầu **bật đúng loại event và cấu hình ghi hợp lý**. Khi chỉ quan tâm một event:

```java
stream.enable("jdk.CPULoad")
      .withPeriod(java.time.Duration.ofSeconds(1));

stream.onEvent("jdk.CPULoad", event -> {
    // Xử lý rất ít; chuyển một snapshot sang pipeline khác nếu cần.
});
```

Một `onEvent("name", handler)` lọc theo tên sự kiện để stream chỉ gọi action tương ứng. Điều này có thể hiệu quả hơn việc `onEvent(event -> ...)` nhận tất cả rồi mới so sánh tên trong code.

Các biện pháp khác:

- **`enable(name/class)` chỉ khi cần**; tắt event không cần thiết bằng `disable`.
- **`withThreshold(Duration)`** nếu chỉ muốn event kéo dài đủ lâu; lưu ý không phải mọi event đều có ý nghĩa với duration.
- **`withPeriod(Duration)`** cho các event chu kỳ hỗ trợ cấu hình period.
- **`withoutStackTrace()`** khi stack trace không cần thiết và overhead của việc ghi stack đáng kể.
- Dùng `setOrdered(false)` **nếu không cần thứ tự theo thời gian** trong stream và API/đặc điểm dữ liệu phù hợp; sắp xếp sự kiện là một phần có thể tạo overhead.
- Với EventStream hỗ trợ `onMetadata`, có thể đăng ký callback theo tên loại event mà ứng dụng thực sự quan tâm; không xử lý toàn bộ nguồn khi yêu cầu chỉ một tập nhỏ.
- Đặt giới hạn lưu dữ liệu phù hợp với loại stream, đặc biệt khi recording chạy lâu.

**Không biến mọi event thành dữ liệu doanh nghiệp bắt buộc.** JFR là công cụ chẩn đoán/quan sát: những dữ liệu cực kỳ quan trọng cần audit/durability/đúng thứ tự có thể phải sử dụng một pipeline độc lập, có cam kết khác với JFR callback.

## 11. Khi nào được xử lý trực tiếp trong callback?

Không phải luôn cần lập thêm thread. Một callback ngắn có thể chỉ tăng counter:

```java
java.util.concurrent.atomic.LongAdder counter =
        new java.util.concurrent.atomic.LongAdder();

stream.onEvent("jdk.GarbageCollection", event -> counter.increment());
```

Đây là snippet với `stream` đã tồn tại. Nếu nhu cầu chỉ là đếm sự kiện và chi phí thực tế thấp, **gọi thẳng `increment()` có thể đơn giản và tốt hơn** so với cấp phát snapshot rồi enqueue. Không nên đưa mọi thứ vào queue chỉ vì có một callback.

Quyết định nên dựa vào đặc điểm công việc:

| Công việc | Thường có thể ở callback? | Ghi chú |
| --- | --- | --- |
| Đọc 1–3 trường đơn giản | Có | Tránh đọc dữ liệu phức tạp không cần |
| Tăng bộ đếm nhẹ | Có | Chọn primitive/metric phù hợp luồng |
| Thêm snapshot nhỏ vào queue bounded bằng `offer` | Có | Có chính sách khi queue đầy |
| Phân tích một object graph lớn | Nên offload | Callback có thể kéo dài |
| Chờ HTTP/database | Không nên | Thời gian phụ thuộc mạng và dịch vụ khác |
| `Thread.sleep` / `Future.get` / `BlockingQueue.put` | Không nên | Có thể chặn tuyến event |
| `System.out.println` cho mỗi event tần suất lớn | Không nên | Console I/O dễ trở thành bottleneck |
| Gọi `RecordingStream.stop()` | Không | Javadoc cảnh báo có thể chờ vô hạn trong action |
| Gửi batch đã sẵn sàng qua `onFlush` | Cần đánh giá kỹ | Hành động gửi vẫn nên nhẹ; batch callback cũng nằm trên tuyến xử lý stream |

Nếu callback cần thêm dữ liệu bên ngoài để ra quyết định, có thể đưa **ID và timestamp** vào worker rồi tra cứu sau. Tránh làm lookup I/O ngay tại thời điểm nhận JFR event.

## 12. Giám sát backlog và độ trễ để biết pipeline có nghẽn không

Thiết kế “queue bounded + worker” chưa đủ nếu không có số liệu để phát hiện overload.

**Các metric nên có:**

| Metric | Tại sao cần | Hành động khi xấu |
| --- | --- | --- |
| Tổng event callback nhận (`received`) | Biết lưu lượng đầu vào | Điều chỉnh loại/period/threshold |
| Tổng snapshot đưa vào queue (`accepted`) | Biết năng lực tiếp nhận | So với processed và dropped |
| Tổng snapshot bị từ chối (`dropped`) | Biết khi nào queue bị quá tải | Tối ưu worker, giảm rate, tăng sampling |
| `queue.size()` / capacity | Quan sát backlog gần hiện tại | Giới hạn và cảnh báo; không dựa vào một lần đọc duy nhất |
| Tuổi snapshot khi bắt đầu xử lý | Biết độ trễ hàng đợi | Giảm backlog hoặc thay chiến lược |
| Thời gian xử lý worker | Biết phần việc thật chiếm bao lâu | Phân tích chỗ chờ I/O/CPU |
| Lỗi callback/worker | Không mất lỗi âm thầm | Báo cáo Throwable và thiết lập policy |
| Event JFR thực sự ghi được | Phân biệt mất tại producer và drop của queue | Đối chiếu với nguồn trong khả năng quan sát |

Một metric `dropped` bằng 0 **không đủ chứng minh không mất event ở mọi tầng**. Nó chỉ nói queue do ứng dụng quản lý chưa từ chối snapshot được callback gửi vào. Nếu JFR không ghi event theo cấu hình, event chưa được flush hoặc stream chưa nhận event, queue không có cách nào tự đếm những event đó.

Một `queue.size()` nhỏ cũng không đảm bảo xử lý nhanh nếu worker bị kẹt tại một task đang chạy. Nên quan sát đồng thời backlog, độ trễ, throughput và lỗi.

## 13. Kiểm thử đúng bản chất bất đồng bộ của JFR

### 13.1. Đừng test bằng một lần `commit()` rồi `sleep(100)`

JFR event streaming thường giao event theo batch. Một testcase có:

```java
event.commit();
Thread.sleep(100);
assertTrue(received);
```

có thể thất bại dù code đúng, bởi stream chưa kịp nhận hoặc flush sự kiện. Ngoài ra, nếu không có synchronization, biến `received` viết ở thread khác có thể có vấn đề visibility.

Giải pháp trong chương trình đầy đủ:

- **`CountDownLatch`** để đợi worker đạt điều kiện kiểm thử.
- **`AtomicReference`** để chia sẻ kết quả/lỗi giữa các thread.
- **Deadline hữu hạn** để bài test không treo vô hạn.
- **Commit lặp có điều kiện** tới khi stream nhận một event phù hợp hoặc hết thời hạn.
- **Không in/so sánh số event commit cố định**, vì thời điểm callback có thể khác giữa máy và JDK.

### 13.2. Các ca kiểm thử quan trọng

1. **Không offload:** callback giả lập `sleep` có thể làm các callback kế tiếp chậm đáng kể; chỉ dùng trong benchmark có kiểm soát, không đưa vào production.
2. **Có offload:** callback chỉ tạo snapshot và `offer`, còn worker xử lý thật; kiểm tra nhận ít nhất một event đúng.
3. **Thread separation:** thread callback khác worker thread; xác nhận việc chờ diễn ra ngoài tuyến stream.
4. **Queue đầy:** cố ý cho worker chậm và phát nhiều event, kiểm tra `offer` thất bại theo thiết kế và `dropped` tăng; không đợi một số lượng drop bất biến khi JFR scheduling khác nhau.
5. **Reuse:** bật `setReuse(true)`, kiểm tra dữ liệu worker qua snapshot; không enqueue `RecordedEvent`.
6. **Lỗi callback:** xác nhận `onError` hoặc kênh lỗi được kiểm tra và không che stack trace.
7. **Lỗi worker:** worker fail không được coi như stream thành công; cần báo lỗi riêng.
8. **Shutdown:** dừng và giải phóng tài nguyên sau timeout/success; kiểm tra worker không còn sống nếu thiết kế yêu cầu.
9. **Sự kiện tần suất cao:** đo callback latency, backlog, allocated bytes và chi phí GC dưới tải thực.
10. **Multiple recordings:** kiểm thử khi có recording khác cũng bật loại event, để không nhầm rằng nguồn event/enable state thuộc duy nhất stream hiện tại.

### 13.3. Tình huống bắt buộc giữ tất cả event được nhận

Nếu ứng dụng cần bảo toàn **mọi snapshot đã được queue chấp nhận** khi shutdown, policy nên có các bước:

1. Ngăn **callback mới** tiếp tục đẩy item, bằng lifecycle có đồng bộ và ranh giới dừng rõ.
2. Cho worker **drain queue** thay vì interrupt ngay giữa task.
3. Giới hạn thời gian chờ dừng và định nghĩa rõ hành động khi vượt thời hạn (cảnh báo, lưu bền, báo lỗi, v.v.).
4. Chỉ xác nhận “hoàn tất” sau khi **worker đã xử lý xong** và những tác vụ downstream đã được xác nhận.
5. Theo dõi riêng dropped/rejected, vì ngay cả khi drain hết queue, những event bị từ chối trước đó không tự quay lại.

Chính sách này phức tạp hơn demo; không nên dùng `stream.close()` như một lời hứa tất cả action và dữ liệu đã hoàn tất, vì Javadoc nói ngược lại.

## 14. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi HTTP hoặc database trực tiếp trong `onEvent` | Callback bị chặn bởi dịch vụ ngoài | Chụp dữ liệu và offload sang worker |
| Dùng `queue.put` trong callback | Queue đầy khiến callback chờ | Dùng `offer` không chờ slot + overload policy |
| Dùng queue không giới hạn | Heap có thể tăng theo backlog | Queue bounded, metric và chính sách quá tải |
| Enqueue chính `RecordedEvent` khi reuse bật | Worker có thể đọc event đã bị tái sử dụng | Copy trường cần thiết sang snapshot |
| Nghĩ `startAsync` tạo một thread cho mỗi event | Callback vẫn chạy trên một tuyến tiêu thụ | Có worker/executor riêng |
| Gọi `stop()` bên trong callback | Có thể bị chặn vô hạn | Phát tín hiệu, dừng từ thread điều khiển |
| Cho rằng `close()` đồng nghĩa mọi callback đã xong | Có thể chưa drain hết action | Đồng bộ xử lý riêng khi cần |
| Ném exception trong `onError` | Hành vi không xác định theo API | Handler phải ngắn và đáng tin |
| Bắt lỗi worker nhưng không báo | Pipeline trông như thành công | Metric/handler lỗi worker độc lập |
| Ghi log đồng bộ mỗi event | I/O log thành bottleneck | Tổng hợp, sampling, đẩy metric theo chu kỳ |
| Đếm `dropped==0` là không mất dữ liệu | Không đo nguồn JFR và upstream | Đo từng tầng, phân biệt semantics |
| Chờ `Thread.sleep(100)` trong test rồi assert đã nhận | Flaky do batch/flush | Latch + deadline hữu hạn |
| Không đặt event threshold/period phù hợp | Producer tạo nhiều event hơn cần | Bật chọn lọc và điều chỉnh setting |
| Đưa snapshot chứa dữ liệu nhạy cảm vào queue/log | Rủi ro riêng tư/bảo mật | Chỉ lấy field cần, kiểm soát retention |

## 15. Checklist thiết kế một callback JFR tốt

- [ ] Có xác định **loại event và tần suất** thật sự cần quan sát?
- [ ] Chỉ đăng ký `onEvent(name,...)` cho event mong muốn, bật event và cấu hình threshold/period hợp lý?
- [ ] Callback có tránh **I/O chặn, sleep, wait, put, join, stop** không?
- [ ] Callback có **chụp dữ liệu giá trị nhỏ** thay vì giữ `RecordedEvent` sau khi return?
- [ ] Nếu offload, queue có **giới hạn dung lượng** và chiến lược overload rõ ràng?
- [ ] Worker có timeout, xử lý lỗi, tốc độ xử lý/latency metric và vòng đời độc lập?
- [ ] Có phân biệt `onError` của stream và lỗi của worker không?
- [ ] Có theo dõi queue size, accepted, processed, dropped và latency?
- [ ] Khi shutdown, có quyết định rõ **dừng nhanh hay drain hết dữ liệu**?
- [ ] Test có latch/deadline và xác nhận event thật, không chỉ kiểm tra chuỗi in?
- [ ] Có kiểm tra ảnh hưởng CPU, heap và GC khi tăng tần suất event?
- [ ] Event hoặc log có tránh tiết lộ dữ liệu nhạy cảm không?

### Câu hỏi tự kiểm tra

**1. Vì sao `startAsync` không giải quyết được callback chậm?** Vì action vẫn được chạy trên một thread tiêu thụ riêng. Nó chỉ tách việc tiêu thụ khỏi thread gọi, không tạo pool xử lý song song cho mọi event.

**2. Nếu `ArrayBlockingQueue.offer(snapshot)` trả `false`, có nên gọi `put(snapshot)` ngay không?** Không nên nếu ưu tiên callback không chặn: `put` có thể chờ queue có chỗ. Hãy thực hiện policy quá tải, chẳng hạn đếm drop, sampling hoặc điều tiết nguồn.

**3. Vì sao enqueue `RecordedEvent` có thể sai dù các field trông có vẻ là immutable?** Vì chính **object `RecordedEvent` được API tái sử dụng** để đại diện cho event khác sau khi callback kết thúc. Cần snapshot trường đã trích xuất hoặc dùng `setReuse(false)` với sự cân nhắc về chi phí.

**4. Có thể gọi `RecordingStream.stop()` khi nhận được event mong muốn ngay trong callback không?** Không nên. Javadoc cảnh báo có thể chặn vô hạn khi gọi stop từ action đang tiêu thụ. Nên gửi tín hiệu cho thread điều khiển bên ngoài callback.

**5. Đóng stream có chứng minh mọi event trước đó đã được xử lý không?** Không. `EventStream.close()` không bảo đảm tất cả action hoàn tất trước khi trả về. Khi cần tính hoàn tất, phải có đồng bộ và chính sách drain riêng.

**6. Khi nào không cần hàng đợi?** Khi callback thực sự chỉ thực hiện phép đọc nhỏ và cập nhật counter nhẹ, đã đo có độ trễ thấp. Không thêm kiến trúc offload nếu nó gây phức tạp và overhead hơn lợi ích.

## 16. Nguồn tài liệu chính thức, còn áp dụng

- [Oracle Java 25 API — EventStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `start()`, `startAsync()`, `onEvent`, `onError`, `setReuse`, `close`, batch delivery và xử lý event.
- [Oracle Java 25 API — RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): cấu hình `enable`, lifecycle, cảnh báo về `stop()` trong callback.
- [Oracle Java 17 API — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): xác nhận các API dùng được với Java 17.
- [Oracle Java 25 API — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): hàng đợi bounded, `offer`, `put` và ngữ nghĩa chờ khi đầy.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): nền tảng event streaming có từ Java 14.

**Ghi nhớ:** Callback JFR nên **xử lý nhanh, sao chép dữ liệu cần thiết và bàn giao an toàn**. Tránh I/O, chờ và tính toán lớn ngay trong `onEvent`; dùng **bounded queue + worker** khi thực sự cần offload. Đặc biệt, **không giữ `RecordedEvent` sau callback khi nó có thể được reuse** và **không gọi `RecordingStream.stop()` từ chính callback**.
