# JFR: `VirtualThreadPinned`, `VirtualThreadSubmitFailed` và ngưỡng ghi sự kiện

## 1. Vì sao cần JFR khi dùng virtual threads?

**Java Flight Recorder (JFR)** là bộ ghi sự kiện chẩn đoán có sẵn trong JDK. Với **virtual threads** (chính thức từ Java 21), JFR giúp nhận biết các tình huống làm giảm khả năng mở rộng, đặc biệt:

- **`jdk.VirtualThreadPinned`**: virtual thread bị giữ trên một **carrier** (platform thread thực thi nó) trong lúc có thao tác chờ; carrier không thể được dùng cho virtual thread khác trong khoảng đó. Sự kiện được ghi khi điều kiện ghi được bật và thời lượng đạt ngưỡng.
- **`jdk.VirtualThreadSubmitFailed`**: Java runtime không thể submit công việc cần thiết để **khởi chạy hoặc tiếp tục chạy** một virtual thread, thường gợi ý sự cố tài nguyên hoặc scheduler. Đây là tín hiệu lỗi ở mức runtime, **không phải** ngoại lệ nghiệp vụ thông thường trong `Runnable`.
- **Ngưỡng `threshold`**: lọc các lần pinning ngắn trước khi ghi sự kiện. Ngưỡng giúp giảm nhiễu và chi phí ghi nhận; nó **không** thay đổi lịch chạy, không ngăn pinning và không tự chữa sự cố.

Đây là kiến thức về **Java/JVM concurrency thuần túy**. Ví dụ dùng `java.lang.Thread`, `jdk.jfr` và công cụ đi kèm JDK; không yêu cầu framework ứng dụng.

> **Nền tảng:** virtual thread được JDK lập lịch lên một hoặc nhiều platform thread gọi là *carrier*. Khi virtual thread chờ I/O có hỗ trợ, runtime thường có thể **unmount** nó để giải phóng carrier. *Pinning* xảy ra khi virtual thread không thể unmount trong lúc bị chặn; nếu kéo dài và lặp lại nhiều lần, carrier bị chiếm và throughput có thể giảm. Pinning tự nó không chứng minh ứng dụng bị deadlock hoặc sai logic.

## 2. Hai sự kiện JFR khác nhau như thế nào?

| Tiêu chí | `jdk.VirtualThreadPinned` | `jdk.VirtualThreadSubmitFailed` |
| --- | --- | --- |
| Phát hiện | Một lần **blocking while pinned** đủ dài để được ghi | Lỗi submit/tiếp tục thực thi virtual thread ở runtime |
| Ý nghĩa | Carrier không được giải phóng trong thời gian chờ | Runtime không lập lịch được một công việc virtual thread như mong muốn |
| Trạng thái mặc định trong cấu hình JFR `default.jfc` | **Bật**, ngưỡng thường là **20 ms** | **Bật** |
| Cần điều chỉnh `threshold`? | Có thể: 20 ms, 5 ms, 0 ms... | Không dùng ngưỡng thời lượng theo cách của pinned event |
| Có thể vắng mặt khi chạy bình thường? | Có: không có blocking pinning, hoặc dưới ngưỡng | Có: không xảy ra lỗi submit |
| Hướng điều tra | Call stack, blocking operation, JDK version, thư viện native, lượng carrier bị giữ | Tình trạng tài nguyên hệ thống/JVM, scheduler, số công việc chờ, lỗi liên quan |

Các event khác như `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` theo dõi thời điểm bắt đầu/kết thúc virtual thread nhưng **mặc định không bật** trong cấu hình điển hình, vì lượng virtual thread lớn có thể sinh nhiều sự kiện. `jdk.ThreadSleep`, `jdk.SocketRead`, `jdk.JavaMonitorEnter` cũng có thể hữu ích khi ghép bối cảnh; chúng **không đồng nghĩa** với pinning.

### 2.1. `VirtualThreadPinned` đo gì?

Không phải cứ virtual thread đang trong `synchronized` là một event sẽ xuất hiện. Để có một sự kiện `jdk.VirtualThreadPinned`, phải có thao tác **bị chặn trong trạng thái pinned**, JFR đang ghi, sự kiện được bật và thời lượng thỏa ngưỡng. Event thường gồm thời điểm, duration, thông tin thread và stack trace (nếu bật). **Tên trường bổ sung** như nguyên nhân pinning hoặc blocking operation có thể thay đổi theo JDK; kiểm tra schema qua `jfr metadata` thay vì hard-code mọi tên trường.

Một số tình huống thực tế:

1. Trên **JDK 21–23**, blocking I/O/`Thread.sleep` **bên trong** một `synchronized` lâu và thường xuyên có thể giữ carrier.
2. Native/foreign calls hoặc vùng VM không thể unmount virtual thread vẫn có thể gây pinning trên các JDK mới hơn.
3. Tranh chấp monitor, chờ khởi tạo lớp và các chi tiết runtime khác cần xem theo phiên bản và event thực tế.

**Thay đổi quan trọng từ JDK 24:** JEP 491 cải tiến cơ chế monitor để virtual thread có thể unmount trong phần lớn trường hợp blocking ở `synchronized`. Vì vậy, một ví dụ “`synchronized` + `sleep` tạo pinned event” có thể hoạt động trên JDK 21 nhưng **không còn tạo event** trên JDK 24+. JFR `VirtualThreadPinned` vẫn hữu ích cho các nguyên nhân pinning còn lại; không nên suy luận “không thấy sự kiện” nghĩa là không có bottleneck.

### 2.2. `VirtualThreadSubmitFailed` báo gì?

Đây là event về **việc submit virtual thread** vào cơ chế thực thi, gồm khi tạo mới hoặc khi virtual thread cần được tiếp tục sau trạng thái chờ. Nó phản ánh một nỗ lực submit thất bại, có thể do áp lực tài nguyên hoặc trạng thái scheduler. Khi gặp sự kiện này, hãy kiểm tra tài nguyên và bối cảnh cùng thời điểm; không thể kết luận nguyên nhân duy nhất chỉ từ tên event.

Phân biệt:

- Một task ném `IllegalArgumentException`/`IOException` rồi kết thúc: **không tự động** phát sinh `VirtualThreadSubmitFailed`.
- `Future.get()` trả `ExecutionException`: đây là đường truyền lỗi task; **không đồng nghĩa** với submit failure của runtime.
- Hết connection trong connection pool hoặc request timeout: có thể gây thất bại nghiệp vụ nhưng **không mặc nhiên** là event này.
- Không có `VirtualThreadSubmitFailed` trong recording: chỉ biết **không ghi nhận** sự kiện đó trong phạm vi và cấu hình đã ghi; không thể xác nhận mọi tài nguyên đều khỏe.

## 3. Ngưỡng `threshold`: hiểu đúng con số 20 ms

Trong các cấu hình JFR JDK thông dụng, `jdk.VirtualThreadPinned` được bật với **`threshold=20 ms`**. Điều này có nghĩa event ghi lại khi thời lượng blocking pinning **đủ dài để vượt qua bộ lọc ngưỡng**; không phải mọi đoạn code chạy trên virtual thread lâu hơn 20 ms đều tạo event.

Ví dụ minh họa:

| Thao tác | Thời lượng | Cấu hình ngưỡng 20 ms | Có khả năng thành `Pinned` event? |
| --- | ---: | ---: | --- |
| Virtual thread sleep 200 ms và unmount bình thường | 200 ms | 20 ms | **Không**, vì không bị pinned |
| Blocking while pinned 8 ms | 8 ms | 20 ms | **Không** vì dưới ngưỡng |
| Blocking while pinned 75 ms | 75 ms | 20 ms | **Có** nếu đang ghi và event được bật |
| Lỗi scheduler submit virtual thread | Không phải duration của pinning | Không áp dụng | `VirtualThreadSubmitFailed` có thể được ghi |

**Các mức ngưỡng điển hình:**

- **20 ms:** điểm bắt đầu hợp lý để phát hiện pinning tương đối dài với nhiễu thấp (giá trị mặc định thường gặp).
- **5 ms:** tăng độ nhạy trong lần chẩn đoán ngắn, có thể tăng số lượng sự kiện và chi phí stack trace.
- **0 ms:** bỏ bộ lọc thời lượng; dễ có rất nhiều sự kiện. Chỉ dùng khi có mục tiêu đo cụ thể, thời gian đủ ngắn và theo dõi dung lượng/overhead.
- **Cao hơn 20 ms:** phù hợp khi chỉ muốn tìm các ca blocking dài nhất, nhưng sẽ bỏ sót nhiều ca ngắn cộng dồn.

`threshold` là **event setting**, không phải `period` hay `cutoff` của file JFR. `period` dành cho các event định kỳ; `maxsize`/`maxage` quản lý dung lượng/tuổi dữ liệu recording, không xác định mức duration cần để phát `VirtualThreadPinned`.

Không nên chuyển một event `duration=30 ms` thành kết luận rằng **người dùng bị chậm đúng 30 ms**: đó là khoảng thời gian gắn với event, còn độ trễ request có thể gồm nhiều thành phần khác.

## 4. Kiểm tra JDK và event schema trước khi phân tích

Các lệnh sau chạy từ JDK có công cụ `java`/`jfr`. Java 21+ được khuyến nghị cho virtual threads.

~~~bash
java -version
jfr help
jfr metadata --events jdk.VirtualThreadPinned
jfr metadata --events jdk.VirtualThreadSubmitFailed
~~~

`jfr metadata` in ra định nghĩa và các trường event mà **JDK hiện tại** biết. Trên các phiên bản JDK có bổ sung trường, đầu ra có thể khác. Nếu công cụ không tìm thấy một event, hãy kiểm tra JDK thực thi `jfr` có phải cùng bản với JVM tạo recording hay không. Với file `recording.jfr`, có thể tra metadata **của chính bản ghi**:

~~~bash
jfr metadata recording.jfr
~~~

Để xem cấu hình thực tế đang dùng, kiểm tra `$JAVA_HOME/lib/jfr/default.jfc` (Windows: `%JAVA_HOME%\lib\jfr\default.jfc`), hoặc cấu hình `.jfc` tùy chỉnh đã nạp. Giá trị mặc định có thể thay đổi giữa bản JDK/vendor/cấu hình; **không dùng giá trị 20 ms như quy luật bắt buộc của mọi recording**.

## 5. Ghi và đọc JFR bằng lệnh JDK

### 5.1. Khởi động ghi cùng chương trình

Ví dụ chương trình Java có main class `PinnedWorkloadDemo`, dùng cấu hình mặc định và ghi file khi JVM kết thúc:

~~~bash
java -XX:StartFlightRecording:settings=default,filename=vt-events.jfr,dumponexit=true PinnedWorkloadDemo
~~~

Khi JVM tắt bình thường, file `vt-events.jfr` chứa các event JFR đã ghi. Nếu khối công việc quá ngắn, ít mẫu hoặc không có sự kiện đủ ngưỡng, bản ghi có thể **không** chứa cả hai event đang tìm. Đường dẫn là tương đối theo thư mục làm việc hiện tại. Có thể dùng đường dẫn tuyệt đối khi triển khai thật.

Kiểm tra file và lọc sự kiện:

~~~bash
jfr summary vt-events.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

Nếu cần xem bối cảnh của các virtual thread:

~~~bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

Lưu ý: `Start` và `End` có thể không xuất hiện do mặc định tắt. `jfr print --events` là **bộ lọc hiển thị**, không thể hồi sinh event không được ghi từ đầu. Để xuất theo dạng máy đọc:

~~~bash
jfr print --json --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-events.jfr
~~~

Dùng `jfr summary` để biết có bao nhiêu event mỗi loại trong file. Dùng `jfr print` hoặc JDK Mission Control (JMC) để xem call stack, duration và thời điểm; ghép với CPU, socket, lock, GC và load cùng thời gian.

### 5.2. Ghi vào tiến trình đang chạy

Tìm process Java thích hợp:

~~~bash
jcmd -l
~~~

Ví dụ với PID thực tế **12345**:

~~~bash
jcmd 12345 JFR.start name=vt-diagnosis settings=default filename=vt-live.jfr
jcmd 12345 JFR.dump name=vt-diagnosis filename=vt-live.jfr
jcmd 12345 JFR.stop name=vt-diagnosis
~~~

PID chỉ là ví dụ. `JFR.start` bắt đầu recording trong JVM đích; `JFR.dump` lấy snapshot vào file; `JFR.stop` kết thúc recording. Để kiểm tra tham số tương ứng với JVM đang chạy, dùng:

~~~bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.check
~~~

Trước khi phân tích, xác định **khoảng thời gian** đã ghi trùng với lúc ứng dụng có vấn đề. Một file ghi sau khi sự cố kết thúc có thể không có event tương ứng.

## 6. Tùy chỉnh ngưỡng với `.jfc`

Từ JDK 19, công cụ `jfr configure` hỗ trợ tạo cấu hình mới dựa trên `default.jfc`. Ví dụ giảm ngưỡng `VirtualThreadPinned` từ 20 ms xuống **5 ms**, tiếp tục bật `VirtualThreadSubmitFailed` và giữ stack trace:

~~~bash
jfr configure --input default --output vt-5ms.jfc "jdk.VirtualThreadPinned#enabled=true" "jdk.VirtualThreadPinned#threshold=5ms" "jdk.VirtualThreadPinned#stackTrace=true" "jdk.VirtualThreadSubmitFailed#enabled=true"
~~~

Sau đó chạy:

~~~bash
java -XX:StartFlightRecording:settings=vt-5ms.jfc,filename=vt-5ms.jfr,dumponexit=true PinnedWorkloadDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-5ms.jfr
~~~

Nếu chỉ cần kiểm tra giá trị threshold, dùng `jfr help configure` và mở `vt-5ms.jfc`: phần tương ứng sẽ có dạng XML (trích đoạn **không phải** file đầy đủ):

~~~xml
<event name="jdk.VirtualThreadPinned">
  <setting name="enabled">true</setting>
  <setting name="stackTrace">true</setting>
  <setting name="threshold">5 ms</setting>
</event>
~~~

**Vì sao không cấu hình `VirtualThreadSubmitFailed#threshold`?** Submit failure là tín hiệu thất bại, không biểu diễn “blocking duration” cần lọc kiểu `VirtualThreadPinned`. Chỉ dùng các setting thực sự được event hỗ trợ. Có thể xem sự kiện và các setting hiện hữu trong `default.jfc` hoặc metadata. Việc sử dụng ngưỡng thấp với `VirtualThreadPinned` không làm lỗi submit xuất hiện nhiều hơn.

Cách đọc kết quả sau điều chỉnh:

1. Nếu ở ngưỡng 20 ms không thấy pinned event nhưng ở 5 ms thấy nhiều event 6–15 ms, chúng có thể là những lần pinning ngắn đã bị lọc trước đó.
2. Số event tăng sau khi hạ ngưỡng **không tự chứng minh** chương trình trở nên chậm hơn. Đó là thay đổi cách đo.
3. Để so sánh hai thời điểm, giữ cùng cấu hình, cùng JDK và workload tương đương. Không so sánh trực tiếp số raw events từ hai recording khác thời lượng hoặc ngưỡng.
4. Một event dài cũng chưa đủ chứng minh tác động throughput lớn; cần biết tần suất, số carrier bị chiếm, tình trạng scheduler và tải thực tế.

## 7. Ví dụ chạy được: minh họa pinning trên JDK 21–23

Ví dụ này có một virtual thread gọi `Thread.sleep(120)` khi đang giữ monitor `synchronized`. **Trên JDK 21–23**, đây là tình huống điển hình tạo `jdk.VirtualThreadPinned` vượt ngưỡng 20 ms. **Trên JDK 24+**, monitor được cải tiến nên ví dụ thường không còn gây pinning; đó là hành vi đúng theo phiên bản, không phải lỗi ghi JFR.

Lưu tệp **`PinnedWorkloadDemo.java`**:

~~~java
public class PinnedWorkloadDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-pinning-demo")
                .start(() -> {
                    synchronized (LOCK) {
                        try {
                            Thread.sleep(120);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }
                });

        worker.join();
        System.out.println("Workload completed");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PinnedWorkloadDemo.java
java -XX:StartFlightRecording:settings=default,filename=vt-demo.jfr,dumponexit=true PinnedWorkloadDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-demo.jfr
~~~

**Stdout do chương trình Java tạo ra**, không tính thông báo khởi tạo JFR từ JVM:

~~~text
Workload completed
~~~

JVM có thể in thêm các dòng `[info][jfr]`; thông tin này thay đổi theo phiên bản. Kết quả `jfr print` không có stdout cố định:

- Trên **JDK 21–23**, nếu JFR đã ghi đúng thời gian và event đủ ngưỡng, sẽ thường có bản ghi `jdk.VirtualThreadPinned` với stack trace trỏ về `PinnedWorkloadDemo`.
- Trên **JDK 24+**, không nên chờ event chỉ từ `synchronized` trong ví dụ này.
- `jdk.VirtualThreadSubmitFailed` hầu như sẽ **không xuất hiện** trong ví dụ bình thường; không cố tình gây lỗi thiếu tài nguyên để tạo sự kiện.

**Tại sao `Thread.sleep(120)` một mình không đủ?** Virtual thread có thể unmount khi sleep thông thường. Trong ví dụ, điều quyết định trên JDK 21–23 là sleep diễn ra **khi đang giữ Java monitor**. Không đánh đồng duration của `Thread.sleep` với `VirtualThreadPinned`.

## 8. Tạo JFR recording bằng API Java (điều chỉnh ngưỡng trong code)

Nếu cần tự động hóa chẩn đoán trên JVM của chương trình, dùng API `jdk.jfr.Recording`. Ví dụ sau bật cả hai event, đặt `VirtualThreadPinned` ngưỡng **5 ms**, ghi `vt-api.jfr` rồi dừng sau khi worker kết thúc. Không phụ thuộc vào CLI `jfr configure`.

Lưu thành **`VirtualThreadJfrApiDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public class VirtualThreadJfrApiDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("vt-api.jfr");
        Object lock = new Object();

        try (Recording recording = new Recording()) {
            recording.enable("jdk.VirtualThreadPinned")
                    .withThreshold(Duration.ofMillis(5))
                    .withStackTrace();
            recording.enable("jdk.VirtualThreadSubmitFailed")
                    .withStackTrace();

            recording.start();

            Thread worker = Thread.ofVirtual().start(() -> {
                synchronized (lock) {
                    try {
                        Thread.sleep(80);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            });

            worker.join();
            recording.stop();
            recording.dump(output);
        }

        System.out.println("JFR file exists: " + Files.exists(output));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 VirtualThreadJfrApiDemo.java
java VirtualThreadJfrApiDemo
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-api.jfr
~~~

**Stdout chính từ Java** khi có quyền ghi file vào thư mục hiện tại:

~~~text
JFR file exists: true
~~~

`recording.enable(...).withThreshold(...)` là cấu hình event cho recording này, không đổi vĩnh viễn default của JVM. `recording.stop()` trước `dump()` đảm bảo khoảng ghi kết thúc; `try-with-resources` đóng tài nguyên. File vẫn có thể không chứa `VirtualThreadPinned` trên JDK 24+ hoặc nếu JVM không có điều kiện ghi event; `Files.exists` chỉ kiểm tra file được tạo, **không** xác nhận pinning đã xảy ra.

Để biết những event đã thực sự có trong file, dùng `jfr summary vt-api.jfr`. Có thể viết bộ đọc riêng bằng `jdk.jfr.consumer.RecordingFile`, nhưng `jfr print` thường dễ hơn cho lần điều tra đầu.

## 9. Cách điều tra khi sự kiện xuất hiện

### 9.1. Khi thấy `jdk.VirtualThreadPinned`

1. **Xác nhận JDK và cấu hình JFR:** phiên bản/vendor, `enabled`, `threshold`, `stackTrace`, khoảng thời gian đo.
2. **Tìm hotspot:** nhóm sự kiện theo stack trace và blocking operation; ưu tiên đoạn gọi lặp lại nhiều lần và thời lượng lớn, thay vì chỉ sửa một event dài hiếm gặp.
3. **Xem carrier đang giữ tài nguyên:** có bao nhiêu virtual thread chờ trong thời điểm peak, số carrier đang bận, độ trễ request và throughput. Một stack trace chỉ là điểm xuất phát để kiểm tra mã.
4. **Phân biệt nguyên nhân theo JDK:** trên JDK 21–23, xem blocking trong monitor; trên JDK 24+, xem native/foreign calls, VM frames, các trường hợp đặc biệt.
5. **Giảm tác động đúng chỗ:** thu hẹp synchronized section, tránh blocking I/O khi đang giữ monitor trên JDK cũ, hoặc thay bằng khóa `ReentrantLock` khi semantics phù hợp. Với native calls, kiểm tra thư viện và kiến trúc gọi thay vì mặc định chỉ sửa `synchronized`.
6. **Đo lại** với cùng workload/cấu hình JFR; kiểm tra throughput, latency, CPU, GC và số event, thay vì chỉ xem số stack traces giảm.

Ví dụ **trước–sau có điều kiện trên JDK 21–23** (đoạn mã minh họa nằm trong phương thức, không phải file độc lập):

~~~java
// Trước: pinning có thể xảy ra khi blocking I/O trong monitor.
synchronized (lock) {
    readFromRemoteService(); // giả định đây là blocking I/O
}

// Sau: nếu logic cho phép, làm I/O ngoài critical section.
var data = readFromRemoteService();
synchronized (lock) {
    updateSharedState(data);
}
~~~

Hai bản **không tự động tương đương về mặt đồng bộ**: nếu phải bảo đảm dữ liệu không đổi giữa thao tác đọc và cập nhật, cần thiết kế giao thức đồng bộ khác. Không di chuyển I/O tùy tiện làm sai bất biến dữ liệu. Một `ReentrantLock` cũng vẫn có thể gây contention; mục tiêu là tránh giữ carrier và giảm thời gian giữ khóa, chứ không phải loại bỏ mọi khóa.

### 9.2. Khi thấy `jdk.VirtualThreadSubmitFailed`

1. Đọc toàn bộ event ở **cùng thời điểm**, stack trace và thông tin thêm nếu có; không đoán tên trường khác nhau giữa các bản JDK.
2. Kiểm tra CPU, RAM/heap, native memory, cgroup/container limits, số platform threads, process limits, cường độ khởi tạo/đánh thức virtual thread.
3. Ghép với `OutOfMemoryError`, sự cố scheduler, JVM logs và các cảnh báo liên quan. Có thể thất bại do tài nguyên, nhưng event tự nó **chưa chứng minh** heap OOM.
4. Kiểm tra thiết kế tải: số request đến, fan-out, công việc CPU-bound kéo dài, tần suất retry; áp dụng backpressure và giới hạn **tài nguyên đích** như database connections hoặc remote API concurrency.
5. Nếu submit failure xảy ra trong production, ưu tiên phân tích và tái hiện có kiểm soát; **không** thử cố tình cạn kiệt tài nguyên máy thật chỉ để tạo JFR event.

Đừng coi `VirtualThreadSubmitFailed` giống `RejectedExecutionException` của một `ThreadPoolExecutor` do người dùng cấu hình. Chúng liên quan những đường xử lý khác nhau; cần dựa trên bằng chứng của JVM và code ứng dụng.

### 9.3. Khi không thấy cả hai event

Kiểm tra tuần tự:

- JVM có bật recording và ghi đúng đoạn thời gian xảy ra sự cố không?
- File có event khác trong `jfr summary` không?
- `VirtualThreadPinned` có bật, `stackTrace` có bật, ngưỡng có đang quá cao không?
- Trên JDK 24+, testcase cũ dùng `synchronized` có còn tạo pinning không?
- Event `VirtualThreadSubmitFailed` có thể thật sự không xảy ra, dù request application thất bại.
- Workload có nút thắt khác: saturated database, socket timeout, CPU, blocking I/O không liên quan pinning, monitor contention thông thường, queue, GC?

**Không có event ≠ không có vấn đề.** JFR chỉ phản ánh sự kiện được cấu hình và thực sự ghi nhận trong cửa sổ quan sát.

## 10. Quan sát bổ sung và tính thực tiễn

Để xem virtual thread trong tiến trình đang chạy, JDK có thể hỗ trợ:

~~~bash
jcmd 12345 Thread.dump_to_file -format=json vt-threads.json
~~~

Thay PID bằng tiến trình thật. Thread dump có ích để xem các virtual thread đang chờ; nó là **ảnh chụp trạng thái**, còn JFR tập hợp sự kiện theo thời gian. Trên các JDK có hỗ trợ, có thể tham khảo thêm:

~~~bash
jcmd 12345 Thread.vthread_scheduler
jcmd 12345 Thread.vthread_pollers
~~~

Các diagnostic command có thể thay đổi theo phiên bản; dùng `jcmd 12345 help` để biết những lệnh JVM thực sự hỗ trợ.

Không nên bật đồng loạt `VirtualThreadStart`/`VirtualThreadEnd` cho hệ thống tạo rất nhiều virtual thread suốt thời gian dài mà không đo overhead và kích thước recording. Với `VirtualThreadPinned` cũng vậy, khi giảm `threshold` hãy ưu tiên **recording ngắn có mục đích** và điều chỉnh `maxsize`/`maxage` theo tài nguyên sẵn có.

### Checklist trước khi kết luận

- [ ] Đã ghi lại JDK version/vendor và chế độ recording.
- [ ] Đã biết `VirtualThreadPinned` có bật và ngưỡng thực tế; không suy từ giá trị mặc định nếu có custom `.jfc`.
- [ ] Đã phân biệt event duration với request latency và hiện tượng pinning với blocking thông thường.
- [ ] Đã kiểm tra thay đổi JEP 491 cho JDK 24+.
- [ ] Đã phân biệt submit failure của virtual-thread scheduler với exception nghiệp vụ.
- [ ] Đã đọc event trong ngữ cảnh thời gian, stack trace, CPU, scheduler, tài nguyên và cường độ workload.
- [ ] Khi sửa code, đã chạy lại benchmark/workload so sánh với cùng cấu hình đo.

## 11. Tài liệu chính thức

- [Oracle Java 21: Virtual Threads và JFR events](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — trạng thái mặc định và ngưỡng 20 ms.
- [Oracle Java 24: Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html) — hành vi pinning mới khi sử dụng monitor.
- [Oracle Java 26: Virtual Threads và ví dụ JFR events](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html) — cách đọc blocking operation, pinned reason và các thao tác chẩn đoán.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — thiết kế và các JFR event liên quan.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — cải tiến `synchronized` từ JDK 24.
- [`jdk.jfr` package documentation (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — `enabled`, `threshold` và `stackTrace`.
- [JDK 21 `jfr` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `jfr configure`, `summary`, `metadata` và `print`.
