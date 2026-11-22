# Sự kiện JFR và vai trò quan sát hành vi JVM

## Mục tiêu

**Java Flight Recorder (JFR)** là cơ chế thu thập thông tin chẩn đoán và profiling được tích hợp trong JVM/JDK hiện đại. JFR biểu diễn quan sát dưới dạng **events (sự kiện)**: thời điểm hoạt động xảy ra, thời lượng nếu có, luồng liên quan, các trường dữ liệu bổ sung và đôi khi là stack trace. Những events này giúp kỹ sư hiểu JVM đang làm gì khi ứng dụng chạy, thay vì chỉ suy đoán từ mã nguồn hoặc chờ một lỗi xuất hiện.

Sau bài học, bạn sẽ có thể:

- Giải thích **JFR event** là gì, khác với Java event listener, application log, metric và exception như thế nào.
- Phân loại events về CPU, garbage collection (GC), memory allocation, thread synchronization, I/O và events do ứng dụng tự định nghĩa.
- Hiểu mối liên hệ **event type → event instance → recording/stream → file `.jfr` → phân tích**.
- Biết vai trò của timestamp, duration, threshold, period, sampling, thread và stack trace khi diễn giải số liệu.
- Dùng công cụ hiện hành `jcmd`, `jfr` và **JDK Mission Control (JMC)** để lấy bằng chứng trước khi tối ưu JVM.
- Tạo một custom event bằng `jdk.jfr.Event`, ghi vào recording, đọc lại bằng `RecordingFile`; biết khi nào dùng `RecordingStream` cho quan sát gần thời gian thực.
- Nhận diện giới hạn: event bị lọc, sampling không ghi mọi thao tác, overhead phụ thuộc cấu hình, dữ liệu có thể chứa thông tin nhạy cảm.
- Biên dịch và chạy chương trình Java 17+ có kết quả kiểm chứng được.

**Phạm vi phiên bản:** JFR đã thuộc OpenJDK từ Java 11 (JEP 328). Điểm đáng chú ý trong lộ trình **Java 14** là **JFR Event Streaming** (JEP 349), cung cấp API tiêu thụ dòng event trong khi JVM chạy. Các API `jdk.jfr`, `jdk.jfr.consumer`, `RecordingStream` và công cụ sử dụng ở đây vẫn hợp lệ với Java hiện đại. Ví dụ chạy trên **JDK 17 trở lên**, không cần tính năng preview.

## 1. JFR event là gì?

Một **event type** mô tả một loại hiện tượng có thể ghi nhận. Chẳng hạn:

- `jdk.GarbageCollection`: một hoạt động GC.
- `jdk.CPULoad`: một mẫu thống kê CPU.
- `jdk.ExecutionSample`: stack/trạng thái luồng được quan sát bởi cơ chế sampling.
- `jdk.JavaMonitorEnter`: thông tin liên quan đến việc chờ hoặc vào Java monitor, tùy threshold/cấu hình.
- `jdk.ThreadPark`: một luồng park/chờ theo các API liên quan.
- `jdk.SocketRead`, `jdk.FileRead`: hoạt động I/O thỏa điều kiện ghi sự kiện.

Khi hiện tượng xảy ra và loại event được bật trong một recording, JVM/JFR có thể tạo một **event instance** chứa dữ liệu quan sát. Tên event như `jdk.CPULoad` là tên logic của loại sự kiện, **không** phải lời gọi đến một hàm trong chương trình.

Một event thường có:

| Thuộc tính | Vai trò | Cách đọc đúng |
|---|---|---|
| **Event type/name** | Xác định loại hiện tượng | Ví dụ `jdk.GarbageCollection` khác `jdk.ExecutionSample`. |
| **Start time / timestamp** | Vị trí tương đối trên trục thời gian | Ghép với diễn biến độ trễ, traffic, deploy; xem độ chính xác và timezone công cụ. |
| **Duration** | Thời lượng nếu event đại diện một hoạt động có khoảng bắt đầu/kết thúc | Không phải mọi event đều có duration hữu ích; một event tức thời có thể có duration gần 0. |
| **Event thread** | Thread gắn với event, khi loại event ghi trường này | Giúp định vị ngữ cảnh nhưng không phải mọi loại event đều có cùng thông tin thread. |
| **Stack trace** | Ngữ cảnh đường gọi tại điểm thu thập, khi được bật/có sẵn | Không mặc định mọi event luôn có stack trace. |
| **Payload fields** | Tham số nghiệp vụ hoặc JVM: bytes, class, tên GC, IDs, v.v. | Mỗi event type có schema riêng; cần xem metadata. |
| **Category/label** | Metadata giúp tìm kiếm và trình bày trong công cụ | Không phải dấu hiệu rằng event tự động được bật. |

**Ví dụ tư duy:** `jdk.GarbageCollection` cho biết một GC có xảy ra trong khoảng quan sát; `jdk.ExecutionSample` cho biết một stack đã được **lấy mẫu** tại thời điểm nào đó. Hai loại event này có bản chất khác nhau: GC event có thể đại diện một hoạt động, còn một CPU/execution sample không phải bản ghi mọi lệnh CPU.

## 2. “Sự kiện” JFR không giống cơ chế gửi thông báo ứng dụng

### 2.1. Không phải Java event listener

Trong Swing/AWT, từ “event” thường gắn với xử lý click, keypress và callback. Trong event-driven application, có thể có domain event được gửi qua message broker. **JFR event** phục vụ trước hết cho **observability/diagnostics**, không phải cơ chế điều phối nghiệp vụ.

Ví dụ, khi tạo `OrderProcessed extends jdk.jfr.Event` rồi gọi `commit()`, thao tác đó **không** tự gửi email, không đẩy thông điệp Kafka và không bảo đảm một consumer nghiệp vụ đang nhận thông báo. Nó tạo dữ liệu chẩn đoán cho các JFR recordings đang cấu hình phù hợp.

### 2.2. Không phải application log

Log có thể nói “request A failed because X”, nhưng thường không mô tả đầy đủ JVM: GC, contention, JIT, heap allocation và phương thức đang chiếm CPU. JFR có thể cung cấp dữ liệu JVM cùng trục thời gian mà không yêu cầu đặt log ở mọi đoạn mã.

Ngược lại, JFR **không thay thế** log nghiệp vụ: thông điệp lỗi, correlation ID, trace ID, trạng thái yêu cầu và lý do từ business rule vẫn cần công cụ quan sát thích hợp.

### 2.3. Không phải metric tổng hợp

Metric như “CPU trung bình 65% trong 5 phút” là một phép **tổng hợp**. Event JFR là một đơn vị dữ liệu có thời điểm, metadata và các fields cho phép điều tra **vì sao** metric thay đổi.

Một dashboard có thể hiển thị GC pause tăng. JFR cho phép điều tra thời điểm và mẫu sự kiện GC/heap/threads tương ứng, với mức chi tiết phụ thuộc cấu hình thu thập.

### 2.4. Không phải full tracing mọi thao tác

Nhiều event bị giới hạn bởi **threshold**, **sampling**, **period** hoặc trạng thái **enabled**. Một khoảng thời gian không xuất hiện event **không chứng minh** không hề có hoạt động. Có thể hoạt động quá ngắn, không được bật, không nằm trong thời gian ghi, bị sampling bỏ qua hoặc dữ liệu đã bị xoay vòng.

**Ghi nhớ:** JFR cung cấp bằng chứng quan sát ở mức JVM, nhưng phải hiểu **cách dữ liệu được lấy mẫu/lọc** trước khi kết luận.

## 3. JFR giúp quan sát những gì trong JVM?

### 3.1. CPU và các phương thức tiêu tốn thời gian

Các event như `jdk.CPULoad` mô tả tải CPU theo thời gian; `jdk.ExecutionSample` cho biết những stack được lấy mẫu khi chương trình chạy.

Khi nhiều samples xuất hiện ở cùng một đường gọi, đó là **dấu hiệu** hot path đáng điều tra. Không có nghĩa “một lần xuất hiện = một lần hàm chạy” hay “phần trăm số sample = phần trăm CPU chính xác tuyệt đối” trong mọi tình huống.

Cần kiểm tra theo thread, tải hệ thống, thời lượng recording và cấu hình sample. Nếu ứng dụng chậm nhưng CPU thấp, nguyên nhân có thể là I/O, lock contention hoặc chờ dịch vụ khác, chứ không nhất thiết là vòng lặp tính toán chậm.

### 3.2. Garbage collection và bộ nhớ

JFR có events về GC, heap, allocation và cấu trúc bộ nhớ. Dữ liệu có thể giúp:

- Xác định GC pauses có trùng với đỉnh latency không.
- Quan sát tần suất GC/heap usage theo thời gian.
- Tìm đường gọi có xu hướng cấp phát nhiều đối tượng.
- Điều tra áp lực allocation, retention và khả năng memory leak khi kết hợp đúng công cụ.

**Phân biệt:** Allocation events không tự cho biết toàn bộ đối tượng nào vẫn đang sống; profiling allocation và phân tích retention/leak là hai góc nhìn khác nhau. Khi cần tìm GC roots, thao tác thu thập sâu có thể tốn chi phí hơn đáng kể.

### 3.3. Lock contention và chờ luồng

Events như `jdk.JavaMonitorEnter` hoặc `jdk.ThreadPark` có thể chỉ ra chỗ luồng chờ lock/park. Quan sát stack, thread và duration để phân biệt:

- **Tranh chấp lock** kéo dài.
- **Chờ có chủ ý** trong worker queue/scheduler.
- **Thread đang đợi I/O** hoặc dependency.

Không kết luận “mọi thread chờ là bug”. Một thread pool bình thường có thể dành nhiều thời gian ở trạng thái chờ công việc.

### 3.4. I/O và external dependencies

`jdk.SocketRead`/`jdk.FileRead` và các events tương ứng giúp điều tra chờ đọc dữ liệu, số bytes, duration và stack khi được ghi nhận. Nếu hệ thống có request latency cao nhưng không có CPU spike, kiểm tra events I/O và trace của hệ thống ngoài có thể xác định nguồn nghẽn.

JFR không tự cung cấp mọi bối cảnh mạng: ví dụ một socket read chậm chưa chứng minh server từ xa sai; vẫn cần kết hợp network telemetry, request traces, logs và thông tin hạ tầng.

### 3.5. JVM runtime, thread và môi trường

Một recording có thể chứa thông tin JVM/version, flags, Java threads, class loading, JIT/compilation và trạng thái host. Điều này rất hữu ích khi lỗi chỉ xảy ra trên một môi trường triển khai hoặc sau một thay đổi cấu hình.

**Giới hạn:** Bộ event khả dụng và tên/fields chi tiết phụ thuộc JDK, nền tảng và cấu hình. Dùng `jfr metadata` trên chính file `.jfr` để xác nhận schema, không sao chép cứng một danh sách event từ bản JDK khác.

## 4. Luồng dữ liệu: event type → recording → phân tích

Hãy hình dung pipeline:

~~~text
Hoạt động JVM / Ứng dụng Java
            |
            v
   Event types và event instances
            |
            v
 Settings: enabled / threshold / period / stackTrace
            |
            v
      JFR recording buffer/repository
            |
           / \
          v   v
     File .jfr  RecordingStream/EventStream
          |             |
          v             v
   jfr CLI, JMC      Consumer xử lý sự kiện
       hoặc API       gần thời gian thực
            \         /
             v       v
      Chẩn đoán dựa trên bằng chứng
~~~

Đây là **sơ đồ khái niệm**, không phải lời khẳng định rằng event nào cũng đồng thời xuất hiện ở mọi recording hoặc stream. Một JVM có thể có nhiều recordings với những cấu hình khác nhau; bộ sự kiện quan sát được phụ thuộc từng recording và điều kiện thực tế.

### 4.1. Event type và event instance

- **Event type**: định nghĩa schema, tên, metadata và settings.
- **Event instance**: một lần ghi nhận của loại đó, với các giá trị fields và thời điểm cụ thể.
- **Recording**: phiên thu thập trong một khoảng thời gian, dựa trên những event types được bật/cấu hình.
- **File `.jfr`**: định dạng nhị phân lưu dữ liệu flight recording; không đọc như file log text thông thường.
- **Consumer**: `RecordingFile` đọc file; `RecordingStream`/`EventStream` nhận events trong lúc thu thập.

### 4.2. Dữ liệu chỉ có khi thỏa điều kiện ghi

Một event có thể không được ghi nếu:

1. Không có recording đang thu thập phù hợp.
2. Event type không được bật.
3. Duration ngắn hơn threshold của event trong cấu hình.
4. Nó là loại lấy mẫu/định kỳ và không rơi vào lúc thu thập.
5. Dữ liệu bị giới hạn bởi max age/size, rotation hoặc khoảng dump.

Do đó, **không tìm thấy event** phải được diễn giải là **“không có bằng chứng được ghi trong phạm vi này”**, không phải **“không có hiện tượng”**.

## 5. Cấu hình event: enabled, threshold, period và stack trace

Một event type có những settings phổ biến:

| Setting | Dùng để làm gì | Hệ quả khi thay đổi |
|---|---|---|
| `enabled` | Quyết định thu thập loại event hay không | Tắt event giảm dữ liệu, nhưng không thể phân tích hiện tượng bằng event đó. |
| `threshold` | Lọc events thời lượng ngắn hơn ngưỡng | Giảm số events; ngưỡng quá cao có thể bỏ lỡ nhiều thao tác ngắn cộng dồn. |
| `period` | Chỉ định nhịp đối với event định kỳ | Tần suất dày hơn cung cấp độ phân giải cao hơn nhưng tăng dữ liệu/chi phí. |
| `stackTrace` | Có ghi stack trace ở thời điểm phù hợp không | Stack hữu ích cho root cause nhưng tạo thêm dữ liệu và có chi phí. |

**Ví dụ:** Một recording có ngưỡng contention `20 ms` có thể không ghi lock waits `5 ms`, mặc dù nhiều lần chờ ngắn liên tục cũng gây ảnh hưởng. Khi nghi ngờ vấn đề ngắn và lặp lại, bạn có thể cân nhắc giảm threshold trong **một phiên ghi ngắn có kiểm soát**, rồi theo dõi overhead.

### 5.1. Hai cấu hình có sẵn

Trong JDK, hai cấu hình thường dùng là:

- **`default.jfc`**: tập sự kiện và settings cân bằng giữa khả năng điều tra và chi phí, phù hợp hơn với việc thu thập kéo dài hoặc liên tục.
- **`profile.jfc`**: thường bật nhiều dữ liệu chi tiết hơn, thích hợp cho **điều tra ngắn, có mục tiêu**, với overhead có thể cao hơn.

Oracle mô tả cấu hình mặc định có **overhead thấp trong tình huống điển hình**, nhưng đây **không phải một giới hạn hiệu năng được đảm bảo** cho mọi ứng dụng, mọi JVM hoặc mọi cấu hình tùy biến. Khi điều chỉnh sampling, stack trace và threshold, hãy đo chi phí trong môi trường tương tự production.

## 6. Ví dụ Java 17+ hoàn chỉnh: định nghĩa, ghi và đọc custom JFR event

Bài thực hành dưới đây tạo một event riêng của ứng dụng để ghi nhận “đã xử lý đơn hàng”, rồi đọc đúng dữ liệu từ một file `.jfr`. Chúng ta dùng chính **API JFR trong JDK**, không cài thư viện ngoài.

### 6.1. Tạo tệp `JfrEventObservationDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrEventObservationDemo {
    @Name("demo.OrderProcessed")
    @Label("Order processed")
    @Category({"Demo", "Orders"})
    static class OrderProcessed extends Event {
        @Label("Order ID")
        String orderId;

        @Label("Units")
        int units;
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jfr-order-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                // Bật event cụ thể và cho phép cả sự kiện rất ngắn.
                recording.enable(OrderProcessed.class)
                         .withThreshold(Duration.ZERO);
                recording.start();

                OrderProcessed event = new OrderProcessed();
                event.orderId = "A-17";
                event.units = 3;

                event.begin();
                int total = event.units * 100;
                event.end();

                if (event.shouldCommit()) {
                    event.commit();
                }

                recording.stop();
                recording.dump(path);
                System.out.println("total=" + total);
            }

            int count = 0;
            try (RecordingFile file = new RecordingFile(path)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();

                    if ("demo.OrderProcessed".equals(
                            event.getEventType().getName())) {
                        count++;
                        System.out.println("event="
                                + event.getString("orderId")
                                + ", units=" + event.getInt("units"));
                    }
                }
            }
            System.out.println("matchedEvents=" + count);
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 JfrEventObservationDemo.java
java JfrEventObservationDemo
~~~

**Đầu ra đã được kiểm chứng bằng biên dịch và chạy thực tế:**

~~~text
total=300
event=A-17, units=3
matchedEvents=1
~~~

Giải thích từng phần:

1. `@Name("demo.OrderProcessed")` tạo **tên event type** để nhận diện khi đọc. Chọn tên ổn định, có namespace riêng để tránh nhầm với `jdk.*`.
2. `@Label` và `@Category` thêm metadata để hiển thị trong các công cụ.
3. `OrderProcessed extends Event` tạo một loại custom event. Hai fields `String` và `int` là loại dữ liệu được JFR hỗ trợ để ghi payload.
4. `Recording.enable(...).withThreshold(Duration.ZERO)` bật loại event này cho recording và không lọc các lần rất ngắn vì ngưỡng duration.
5. `recording.start()` bắt đầu phiên thu thập trước khi sự kiện được commit.
6. `event.begin()`, `event.end()` xác định khoảng thời gian cho event; `shouldCommit()` kiểm tra event hiện đủ điều kiện ghi hay không.
7. `event.commit()` gửi giá trị event vào cơ chế JFR. Nếu không có recording thích hợp, event không tự động tạo ra một file độc lập.
8. `recording.stop()` rồi `recording.dump(path)` ghi dữ liệu ra file `.jfr`.
9. `RecordingFile` duyệt events đã lưu, lọc đúng tên `demo.OrderProcessed`, đọc payload theo kiểu bằng `getString` và `getInt`.
10. `Files.deleteIfExists(path)` dọn file tạm sau ví dụ. Nếu bạn muốn mở file bằng JMC hoặc lệnh `jfr`, hãy lưu nó vào một đường dẫn cố định có kiểm soát và **không xóa** cho tới khi phân tích xong.

**Vì sao chỉ thấy một custom event?** Chương trình gọi `commit()` đúng một lần cho event đó, bật type trong recording và đặt threshold bằng 0. File `.jfr` có thể chứa thêm các loại events JVM khác; chương trình **lọc** nên chỉ đếm `demo.OrderProcessed`. Tổng `total=300` là phép tính nghiệp vụ minh họa, **không** được JFR tự đo hay tự viết vào event.

### 6.2. Các giới hạn của payload tùy chỉnh

Theo API `jdk.jfr.Event`, các fields sự kiện được ghi hỗ trợ các primitive types (`boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`) và một số reference types (`String`, `Thread`, `Class`).

Đừng tự cho rằng khai báo fields kiểu `List<Order>`, `Map` hoặc DTO tùy ý sẽ được JFR tự serialize. Các kiểu tham chiếu không được hỗ trợ có thể bị **bỏ qua** trong payload. Nếu cần biểu diễn dữ liệu phức tạp, chọn những fields phẳng, có nghĩa chẩn đoán, ưu tiên ID/counter/duration phù hợp và tránh đưa dữ liệu nhạy cảm vào recording.

### 6.3. `isEnabled()` và `shouldCommit()`

Hai phương thức không đồng nghĩa:

- `event.isEnabled()`: kiểm tra có ít nhất một recording quan tâm và type đang được bật hay không. Hữu ích trước khi thu thập dữ liệu tốn chi phí.
- `event.shouldCommit()`: kiểm tra event có thể thực sự được ghi, bao gồm điều kiện threshold. Khi event đo duration, thường gọi sau khi kết thúc phần đo.

Ví dụ minh họa khi payload cần tính toán đắt:

~~~java
// Đoạn trích minh họa trong phương thức.
OrderProcessed event = new OrderProcessed();
if (event.isEnabled()) {
    event.begin();
    // Thu thập dữ liệu cho event nếu thật sự đáng làm.
    event.orderId = orderId;
    event.units = units;
    event.end();

    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

Đoạn này cần `OrderProcessed` và các biến `orderId`, `units` từ ngữ cảnh chương trình thật. Không đưa logic nghiệp vụ quan trọng vào điều kiện `isEnabled()`: **chỉ phần đo đạc bổ sung** mới được bỏ qua khi recording tắt. Nếu chương trình chỉ xử lý đơn hàng khi JFR bật, đó là bug.

## 7. Quan sát JVM đang chạy bằng `jcmd` và phân tích file bằng `jfr`

Không nhất thiết phải thay đổi code để lấy nhiều loại event có sẵn của JVM.

Giả sử bạn có một JVM đang chạy và có quyền chẩn đoán tương ứng. Dùng các lệnh sau trong terminal với JDK tương thích:

~~~bash
# Liệt kê các Java process có thể thấy từ môi trường hiện tại.
jcmd -l

# Thay 12345 bằng PID thực sự của JVM muốn quan sát.
jcmd 12345 JFR.start name=observe settings=profile maxage=10m maxsize=256m

# Kiểm tra recording đang hoạt động.
jcmd 12345 JFR.check

# Trích dữ liệu hiện có ra file, recording vẫn tiếp tục chạy.
jcmd 12345 JFR.dump name=observe filename=observe.jfr

# Dừng recording khi không còn cần thiết.
jcmd 12345 JFR.stop name=observe

# Tổng hợp số lượng/loại events trong file.
jfr summary observe.jfr

# In một số event types đáng quan tâm.
jfr print --events jdk.GarbageCollection,jdk.JavaMonitorEnter observe.jfr

# Xem metadata và schema types trong file.
jfr metadata observe.jfr
~~~

Các lệnh là **quy trình vận hành minh họa**, không có stdout cố định: PID, dữ liệu runtime, quyền truy cập và cấu hình recording khác nhau theo môi trường.

**Phân biệt hai nhóm công cụ:**

- `jcmd <pid> JFR.start/check/dump/stop` điều khiển recording của **JVM đang chạy**. `JFR.dump` **không tự dừng** recording.
- `jfr summary/print/metadata <file>` làm việc với **file `.jfr` đã được tạo**. `summary` cho biết thống kê events, `print` in dữ liệu theo bộ lọc, `metadata` mô tả các event types/fields.

Nếu muốn một recording tự kết thúc sau khoảng xác định, có thể dùng:

~~~bash
jcmd 12345 JFR.start name=short settings=profile duration=60s filename=short.jfr
~~~

Nếu bắt đầu JVM mới bằng lệnh `java`, JDK cũng hỗ trợ cấu hình thu thập lúc khởi động, ví dụ:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,duration=60s -jar app.jar
~~~

**Lưu ý vận hành:** `app.jar` là ứng dụng ví dụ; các đường dẫn output phải có quyền ghi và đủ dung lượng. Attach bằng `jcmd` đòi JVM đang chạy và quyền của môi trường/OS phù hợp, thường cùng host và tài khoản vận hành. Không mặc định lệnh `jcmd -l` nhìn được mọi JVM trong container khác hoặc JVM bị giới hạn quyền attach.

**Lưu ý về `maxage`, `maxsize`:** Đây là giới hạn giữ dữ liệu theo thời gian/dung lượng cho recording; phải chọn phù hợp dung lượng đĩa và nhu cầu điều tra. Dù giới hạn như vậy, khi dump file có thể chỉ chứa **phần lịch sử còn lại**, không phải toàn bộ thời gian từ lúc JVM khởi động.

## 8. Quan sát gần thời gian thực với `RecordingStream` (Java 14+)

Một khả năng quan trọng của JFR trên Java 14+ là **đọc dòng events khi JVM vẫn đang chạy**, thay vì luôn phải dừng recording và mở file ở bước sau.

API `jdk.jfr.consumer.RecordingStream` có từ Java 14. Đoạn minh họa Java 17 sau nhận `jdk.CPULoad` trong khoảng 10 giây:

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

// Đoạn minh họa trong một phương thức throws InterruptedException.
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event);
    });

    stream.startAsync();
    Thread.sleep(10_000);
}
~~~

**Cách hiểu:**

1. `enable("jdk.CPULoad")` bật loại event đã có trong JVM hiện tại.
2. `withPeriod(Duration.ofSeconds(1))` cấu hình chu kỳ sự kiện phù hợp.
3. `onEvent(...)` đăng ký callback để xử lý những events xuất hiện.
4. `startAsync()` bắt đầu consumer trên thread khác, cho phép phương thức làm việc tiếp.
5. Rời `try-with-resources` sẽ đóng `RecordingStream` và giải phóng tài nguyên.

Output cố ý **không ghi số liệu mẫu** vì mức CPU, số lần callback và nội dung events phụ thuộc hệ thống thật. Không dùng một chuỗi stdout giả để khẳng định JFR luôn phát chính xác mười events sau mười giây. Đây là API **quan sát**, không phải đồng hồ định kỳ chính xác tuyệt đối.

**Lưu ý thực tế:** Callback được thực thi trên đường xử lý sự kiện; tránh tính toán tốn kém hoặc ghi log ồ ạt trong mỗi callback nếu không muốn ảnh hưởng tới bản thân việc quan sát. Nếu consumer xử lý chậm, cần tính tới buffer, độ trễ và chính sách sampling. `RecordingStream` không thay thế cho message broker phục vụ giao dịch.

## 9. Diễn giải dữ liệu đúng thay vì chỉ xem một event riêng lẻ

### Tình huống A — API tăng latency sau deployment

Giả sử dashboard cho thấy p95 latency tăng sau một bản phát hành.

Các bước điều tra hợp lý:

1. Xác nhận thời gian xảy ra và mức traffic.
2. Lấy recording đủ dài ở giai đoạn có triệu chứng.
3. So sánh `jdk.CPULoad` và các execution samples: JVM có đang bận CPU không?
4. Kiểm tra GC pauses, allocation pressure và biến động heap gần đỉnh latency.
5. Xem contention/I/O events và stack traces để tìm nơi chờ hoặc đường gọi phổ biến.
6. Đối chiếu logs/traces của yêu cầu tương ứng trước khi kết luận root cause.

**Ví dụ kết luận được hỗ trợ:** “Trong giai đoạn p95 tăng, các recording samples tập trung ở đường gọi xử lý ảnh và không có GC pauses lớn trùng thời điểm” là một **giả thuyết có căn cứ** để profile tiếp, không phải chứng cứ logic rằng chỉ có một nguyên nhân.

### Tình huống B — Ứng dụng có CPU cao nhưng không có exception

JFR có thể giúp quan sát đường gọi tiêu thụ CPU qua execution samples. Kiểm tra:

- Nhiều samples tập trung ở cùng thread/call tree?
- Đó là mã nghiệp vụ, serialization, regex, logging hay thư viện phụ thuộc?
- Thời gian recording đủ dài và workload có đại diện?
- Một request rất chậm nhưng hiếm gặp có bị sampling bỏ sót?

Sau đó thử đo benchmark/profile chuyên sâu hơn nếu cần. **Không** lấy event count chia cho tổng request để suy ra CPU mà không biết sampling model.

### Tình huống C — Thỉnh thoảng bị giật do GC hoặc lock

Một loạt pauses và lock waits có thể giải thích sự gián đoạn ngắn. Nhưng kết luận phải xét **timestamp, duration, threshold và stack trace**; nếu threshold quá cao, JFR không hiển thị nhiều lần chờ ngắn.

Có thể lặp lại một recording ngắn với cấu hình chi tiết hơn, đo overhead, rồi quay lại cấu hình mặc định. Không nên bật mọi event ở tần suất cao mãi trong production chỉ để “không bỏ sót”.

## 10. Hiểu giới hạn độ chính xác và overhead

### 10.1. Không có event không đồng nghĩa không có hoạt động

Có thể event không xuất hiện do bị tắt, chưa đủ threshold, sampling bỏ qua, recording kết thúc sớm, file đã xoay vòng hoặc hoạt động xảy ra ngoài cửa sổ quan sát. Khi cần dữ liệu chi tiết hơn, điều chỉnh cấu hình **có mục tiêu** và kiểm chứng lại.

### 10.2. Chi phí JFR thường thấp nhưng không miễn phí

Cấu hình mặc định được thiết kế để có overhead thấp; tài liệu Oracle nêu mức overhead **thường thấp trong trường hợp điển hình**, không phải một cam kết cứng. Các event có stack trace, sampling dày, threshold cực thấp hoặc payload rất lớn có thể làm tăng CPU, memory, disk I/O và dung lượng recording.

**Nguyên tắc vận hành:** Thu thập đúng loại event và thời lượng cần thiết. Đo overhead trên workload đại diện, đặt giới hạn dung lượng, không giữ profile recording liên tục vô thời hạn nếu không có lý do.

### 10.3. Events nhạy cảm về quyền riêng tư và bảo mật

JFR files có thể chứa:

- Tên class, method và stack traces.
- Tên threads, JVM properties, thông tin runtime/host.
- Đường dẫn file/socket hoặc metadata vận hành tùy event.
- Các **custom fields** do ứng dụng tự đặt, có thể vô tình chứa ID, nội dung dữ liệu người dùng hoặc secrets.

**Không** đưa mật khẩu, token, thông tin cá nhân hoặc payload nhạy cảm vào custom event. Hạn chế quyền truy cập `.jfr`, quản lý thời gian lưu, dùng quy trình chia sẻ và xóa phù hợp, kiểm tra nội dung trước khi gửi file cho bên thứ ba. Khi cần phân tích bên ngoài, ưu tiên lọc/ẩn danh dữ liệu theo chính sách tổ chức.

### 10.4. JFR không thay thế hệ thống quan sát khác

JFR là một mảnh trong **observability stack**. Kết hợp với metric, distributed traces, logs, thread dumps và heap analysis khi bài toán cần. Dữ liệu JFR thường mạnh nhất cho câu hỏi **JVM đang chạy như thế nào**, còn hành vi nghiệp vụ và các phụ thuộc phân tán cần dữ liệu ở tầng cao hơn.

## 11. Lỗi phổ biến

| Sai lầm | Hệ quả | Cách hiểu/sửa |
|---|---|---|
| Xem JFR event như event bus nghiệp vụ | Mong chờ xử lý giao dịch qua `commit()` | JFR event phục vụ recording/diagnostics, không đảm bảo giao hàng nghiệp vụ |
| Gọi `commit()` khi không có recording phù hợp rồi đòi có `.jfr` | Không có dữ liệu để đọc | Khởi động và bật event trong recording đúng thời điểm |
| Chỉ kiểm tra tên event, bỏ qua threshold/period | Có thể kết luận sai về số lần hoạt động | Xem event settings và metadata của file |
| Xem `jdk.ExecutionSample` như mỗi lần một hàm được gọi | Kết luận sai về call count/CPU chính xác | Hiểu đó là dữ liệu sampling, tổng hợp và kiểm tra thêm |
| Thấy không có lock event thì kết luận không có contention | Short waits có thể nằm dưới threshold | Cấu hình recording phù hợp và xét triệu chứng |
| Bật `profile` liên tục mà không giám sát | Tăng overhead/dung lượng | Dùng `default` khi thích hợp; profile ngắn có mục tiêu |
| Không giới hạn `maxage`/`maxsize` | Dữ liệu tích tụ hoặc mất lịch sử theo cách không dự kiến | Đặt retention phù hợp, kiểm tra dung lượng |
| Giả định mọi JFR event đều có stack trace | Không tìm được call site | Xem type/schema và setting `stackTrace` |
| Giả định custom event chứa arbitrary `List`/DTO được ghi | Payload có thể bị bỏ qua | Dùng các kiểu field JFR hỗ trợ |
| Gọi `shouldCommit()` trước khi đo duration rồi suy ra event chắc chắn sẽ được ghi | Threshold/duration chưa đúng thời điểm | Đánh giá sau `end()` nếu dùng duration |
| Xem `JFR.dump` như lệnh dừng | Recording vẫn chạy | Dùng `JFR.stop` khi muốn kết thúc |
| Chỉ đọc `jfr summary` rồi kết luận root cause | Summary là thống kê loại sự kiện, chưa có stack/time correlation | Dùng `jfr print`/JMC và xem events chi tiết |
| Thấy `.jfr` là “log vô hại” | Rò rỉ stack, paths hoặc custom payload | Bảo vệ quyền truy cập, lọc dữ liệu, retention |
| So sánh hai recordings có settings khác nhau như thể tương đương | Sample counts/threshold khác làm lệch kết luận | Ghi lại cấu hình, cửa sổ thời gian, workload khi so sánh |
| Kỳ vọng một output cố định từ `RecordingStream` `jdk.CPULoad` | Events/values phụ thuộc môi trường | Dùng minh họa không định sẵn stdout, test riêng logic nhận callback |

## 12. Quy trình ngắn để áp dụng JFR hiệu quả

1. **Đặt câu hỏi cụ thể**: CPU đang tiêu ở đâu? GC có trùng latency? Có lock contention? I/O nào đang chờ?
2. **Chọn cửa sổ thu thập** theo lúc triệu chứng xuất hiện; xác định PID/JVM.
3. **Chọn settings phù hợp**: `default` để quan sát ít overhead hoặc `profile` cho một đợt điều tra có giới hạn.
4. **Ghi dữ liệu bằng `jcmd` hoặc API**, xác nhận recording đã thực sự chạy.
5. **Dùng `jfr summary` và `jfr metadata`** để hiểu trong file có loại event gì và schema như thế nào.
6. **Đi sâu vào events** bằng `jfr print`/JMC, xem timestamp, duration, thread, stack và payload theo vấn đề.
7. **Đối chiếu logs/metrics/traces**; tránh kết luận từ một event không có ngữ cảnh.
8. **Điều chỉnh ngưỡng hoặc sampling nếu cần**, cân nhắc overhead và làm phép đo lại trên workload đại diện.
9. **Ghi kết luận có bằng chứng**: tên recording, JDK, settings, thời gian, triệu chứng, event types quan sát và giả thuyết kiểm chứng.
10. **Dọn recordings và bảo vệ dữ liệu**, tránh lưu file chẩn đoán chứa thông tin nhạy cảm quá lâu.

## 13. Bài tự kiểm tra

**Câu 1.** Một recording không có `jdk.JavaMonitorEnter` events. Có thể khẳng định ứng dụng không có bất kỳ tranh chấp monitor nào không?

**Đáp án:** Không. Event type có thể chưa bật, có threshold, contention xảy ra ngoài cửa sổ ghi hoặc chưa đủ dài để được lưu. Cần kiểm tra settings và thời gian thu thập.

**Câu 2.** Một kỹ sư gọi `new OrderProcessed().commit()` nhưng không chạy recording, rồi tìm file `.jfr`. Sai ở đâu?

**Đáp án:** `commit()` chỉ gửi event vào JFR khi có cơ chế thu thập phù hợp; nó không tự tạo file. Cần bắt đầu/bật recording, commit khi recording hoạt động và dump/stop theo quy trình.

**Câu 3.** `jdk.ExecutionSample` có ý nghĩa gì nếu một hàm xuất hiện trong nhiều samples?

**Đáp án:** Đó là tín hiệu hàm/đường gọi xuất hiện thường xuyên trong các thời điểm được lấy mẫu, có thể là hot path. Không được coi từng sample là một lời gọi hàm hay CPU time tuyệt đối.

**Câu 4.** `JFR.dump` và `JFR.stop` có giống nhau không?

**Đáp án:** Không. Dump ghi dữ liệu từ một recording đang chạy ra file trong khi recording có thể tiếp tục; stop kết thúc recording.

**Câu 5.** Vì sao `@Label`, `@Category` hữu ích nhưng chưa đủ để custom event xuất hiện trong file?

**Đáp án:** Chúng là metadata giúp đọc/hiển thị. Recording vẫn phải được bật, event type đáp ứng settings/threshold, và sự kiện phải được commit đúng thời gian.

**Câu 6.** Khi nào dùng `RecordingFile`, khi nào dùng `RecordingStream`?

**Đáp án:** `RecordingFile` đọc các events trong một file `.jfr` đã có; `RecordingStream` cho phép nhận events của JVM hiện tại gần thời gian thực. `RecordingStream` được giới thiệu từ Java 14 và vẫn là API hiện hành.

**Câu 7.** Thấy `profile.jfc` thu nhiều events hơn `default.jfc` thì có nên bật profile liên tục cho mọi JVM?

**Đáp án:** Không mặc định. Thu chi tiết hơn có thể tăng overhead, dung lượng và dữ liệu nhạy cảm. Dùng profile có mục tiêu, đo tác động và giới hạn retention.

**Câu 8.** Với custom event muốn lưu một đối tượng `List<Order>`, có nên thêm field như vậy rồi tin JFR sẽ serialize mọi phần tử không?

**Đáp án:** Không. API Event chỉ hỗ trợ một tập hợp kiểu field nhất định; arbitrary reference types không được JFR tự serialize. Hãy lưu fields phẳng cần thiết, chẳng hạn mã giao dịch không nhạy cảm, counter và duration.

## Tài liệu đối chiếu chính thức

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): nền tảng Flight Recorder trong OpenJDK (JDK 11).
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): phát triển khả năng xử lý dòng event từ JDK 14.
- [Oracle Java 17 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/17/jfapi/index.html): tổng quan API, events, recordings, cấu hình và streaming.
- [Java SE 17 API — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html): tạo, bắt đầu/kết thúc thời gian, commit, hỗ trợ field types.
- [Java SE 17 API — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event metadata và các settings `enabled`, `threshold`, `period`, `stackTrace`.
- [Java SE 17 API — `Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): lifecycle, cấu hình event, dump.
- [Java SE 17 API — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc và duyệt events từ file.
- [Java SE 17 API — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): tiêu thụ events gần thời gian thực; `Since: 14`.
- [Oracle Java 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): các lệnh `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle Java 17 — `jfr`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, `metadata` để phân tích file.
- [Oracle Java 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): điều tra CPU, memory, GC, locks và I/O từ recording.

**Ghi nhớ:** Một **JFR event** là **bằng chứng quan sát có cấu trúc về hành vi JVM hoặc ứng dụng**. Giá trị của JFR không nằm ở số lượng events thu được, mà ở khả năng kết hợp **event type, thời gian, duration, stack, sampling, cấu hình và dữ liệu hệ thống khác** để kiểm chứng giả thuyết. Hãy thu thập có mục tiêu, diễn giải đúng giới hạn của recording và bảo vệ dữ liệu chẩn đoán.