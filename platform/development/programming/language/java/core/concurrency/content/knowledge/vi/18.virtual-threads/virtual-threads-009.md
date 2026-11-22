# Pinning với monitor/native code ở Java 21

> **Phạm vi:** Java SE 21, virtual threads theo JEP 444. Bài tập trung vào cơ chế JVM và các API đồng thời của Java; không bàn về cấu hình hay tích hợp của Spring.

## 1. Pinning là gì và vì sao cần quan tâm?

Virtual thread là một `java.lang.Thread` nhẹ, do JVM lập lịch. Khi chạy, virtual thread được **mount** lên một platform thread (thường gọi là **carrier thread**). Nhiều virtual thread có thể lần lượt sử dụng số carrier nhỏ hơn rất nhiều số lượng virtual thread. Mô hình này đặc biệt có lợi khi tác vụ phải đợi I/O: nếu thao tác chờ được JDK hỗ trợ, JVM có thể **unmount** virtual thread, giải phóng carrier để chạy tác vụ khác.

**Pinning** là tình huống virtual thread không thể unmount khỏi carrier trong một đoạn thực thi nhất định. Bản thân việc bị pin không gây lỗi về tính đúng đắn. Vấn đề xuất hiện khi virtual thread **chặn (block) trong lúc bị pin**: carrier cũng phải đứng chờ, làm giảm số carrier còn phục vụ những virtual thread khác.

Luồng bình thường khi đợi I/O:

~~~text
Virtual thread A ── chạy trên carrier #1 ── gặp điểm chờ
                                               ↓
                                    A unmount / chờ
Carrier #1 ── rảnh ── chạy virtual thread B, C, ...
                                               ↓
                                    I/O của A hoàn tất
Virtual thread A ── được mount lại lên một carrier sẵn có
~~~

Trường hợp bị pin:

~~~text
Virtual thread A ── đang ở trong monitor/native frame
             ↓
          gặp điểm chờ lâu
             ↓
A không thể unmount → carrier #1 cũng bị giữ lại trong lúc đợi
             ↓
Ít carrier hơn để chạy B, C, ... → throughput/latency có thể xấu đi
~~~

Ba khái niệm cần tách bạch:

- **Blocking**: tác vụ phải đợi một điều kiện, ví dụ `Thread.sleep`, socket I/O hoặc chờ khóa. Blocking không tự động có nghĩa là pinning; nhiều thao tác chờ có thể nhường carrier.
- **Pinning**: ràng buộc kỹ thuật khiến virtual thread không thể rời carrier tại thời điểm đó. Pinning chỉ thực sự đáng lo khi sự chờ đợi kéo dài hoặc lặp lại với tần suất lớn.
- **Lock contention/deadlock**: các vấn đề phối hợp truy cập tài nguyên. Thay cách khóa có thể giải quyết carrier pinning nhưng không tự động giải quyết tranh chấp khóa, deadlock, giới hạn kết nối hay các điểm nghẽn khác.

Virtual thread không làm CPU chạy nhanh hơn và không loại bỏ chi phí của một I/O chậm; lợi ích chủ yếu là giảm lượng OS thread phải đứng chờ.

## 2. Hai nguồn pinning quan trọng ở Java 21

### 2.1. `synchronized` và monitor của JVM

Ở JDK 21, khi virtual thread đang thực thi mã trong một phương thức hoặc khối `synchronized`, nó bị pin vào carrier. Nếu bên trong vùng giữ monitor xảy ra thao tác chờ được hỗ trợ unmount ở điều kiện bình thường, việc unmount **không thể diễn ra**; carrier bị giữ trong thời gian chờ.

Ví dụ:

~~~java
private final Object guard = new Object();

void updateAndWait() throws InterruptedException {
    synchronized (guard) {
        // Việc cập nhật trạng thái nhỏ thường không đáng lo.
        Thread.sleep(200); // Trên Java 21: chờ khi đang giữ monitor -> carrier bị pin.
    }
}
~~~

Đây là **đoạn minh họa trong một lớp**, không phải chương trình chạy độc lập. `Thread.sleep` mô phỏng thao tác chờ; trong ứng dụng thực, một lời gọi I/O chậm bên trong vùng `synchronized` có thể gây tác động tương tự.

**Không nên kết luận rằng mọi `synchronized` đều xấu.** Một khối monitor chỉ cập nhật vài biến trong bộ nhớ và kết thúc rất nhanh ít khi tạo ra vấn đề đáng kể. Điều cần tìm là **blocking kéo dài hoặc xảy ra thường xuyên khi còn giữ monitor**. Phương thức `synchronized` có cùng vấn đề: phạm vi giữ monitor bao trùm thân phương thức, bao gồm cả các lời gọi gián tiếp có thể chặn.

Monitor vẫn đảm bảo các quy tắc mutual exclusion và happens-before thông thường. Pinning là đặc tính của cơ chế chạy virtual thread ở JDK 21, không làm thay đổi hợp đồng đồng bộ hóa hay tự nó tạo data race.

### 2.2. Native method và foreign function

JDK 21 cũng có thể pin virtual thread khi đang thực thi **native method** (ví dụ qua JNI) hoặc **foreign function** (giao diện gọi mã ngoài JVM). Khi mã native vẫn đang nằm trên stack, JVM không thể tùy ý tách continuation của virtual thread như với điểm chờ Java được hỗ trợ.

Ví dụ tình huống thực tế:

~~~text
Virtual thread
    └─ Java wrapper
         └─ JNI / foreign call
              └─ thư viện native đợi socket, khóa hoặc thiết bị 500 ms
                   └─ carrier bị chiếm trong thời gian chờ
~~~

Không phải cứ gọi một native method là ứng dụng gặp sự cố: một lời gọi native rất nhanh có thể gần như không đáng kể. Cần đo **thời lượng và tần suất chờ trong đoạn native**. Việc đổi monitor Java bên ngoài lời gọi JNI thành `ReentrantLock` không loại bỏ pinning do chính native frame.

Ở Java 21, Foreign Function & Memory API vẫn ở trạng thái **preview** (JEP 442); bài này chỉ xét bản chất tương tác native, không yêu cầu sử dụng API preview.

## 3. Vì sao pinning làm giảm khả năng mở rộng?

Giả sử bộ lập lịch có một số lượng carrier hữu hạn. Có nhiều virtual thread đang phục vụ các tác vụ I/O độc lập:

1. Nếu virtual thread chờ I/O và unmount thành công, carrier được sử dụng lại cho tác vụ khác; số tác vụ đang chờ có thể lớn hơn nhiều số OS thread.
2. Nếu mỗi tác vụ đi vào một monitor rồi chờ 200 ms khi bị pin, carrier phải chờ theo từng tác vụ.
3. Khi nhiều carrier cùng bị pin, các virtual thread khác có thể phải chờ đến lượt chạy, dù chúng không tranh chấp cùng một monitor hoặc tài nguyên.
4. Hệ quả có thể là giảm throughput, hàng đợi tăng, độ trễ ở phân vị cao tăng. Mức độ ảnh hưởng phụ thuộc tải, độ dài blocking, số carrier và các nút thắt khác.

**Lưu ý:** tăng số carrier hoặc thay đổi cấu hình scheduler không phải biện pháp chữa tận gốc. Tạo thêm OS thread có thể che giấu một phần triệu chứng và làm tăng tiêu thụ tài nguyên. Trước tiên hãy nhận diện đoạn blocking khi bị pin.

## 4. Ví dụ Java 21 chạy được: monitor so với `ReentrantLock`

Tạo tệp **`PinningJava21Demo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class PinningJava21Demo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    public static void main(String[] args) throws InterruptedException {
        Thread monitorThread = Thread.ofVirtual()
                .name("monitor-demo")
                .start(() -> {
                    synchronized (MONITOR) {
                        pause(150);
                    }
                });
        monitorThread.join();

        Thread lockThread = Thread.ofVirtual()
                .name("reentrant-lock-demo")
                .start(() -> {
                    LOCK.lock();
                    try {
                        pause(150);
                    } finally {
                        LOCK.unlock();
                    }
                });
        lockThread.join();

        System.out.println("Hoàn tất hai ví dụ");
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Tác vụ bị ngắt", ex);
        }
    }
}
~~~

Biên dịch và chạy với **JDK 21** (không cần `--enable-preview`):

~~~bash
javac PinningJava21Demo.java
java PinningJava21Demo
~~~

Đầu ra chuẩn của chương trình nếu không bị ngắt:

~~~text
Hoàn tất hai ví dụ
~~~

Giải thích:

- `Thread.ofVirtual().start(...)` tạo và khởi động virtual thread. `join()` giúp chương trình đợi mỗi đoạn demo hoàn tất.
- Đoạn thứ nhất giữ **intrinsic monitor** trong khi `Thread.sleep(150)`. Trên Java 21, đây là ví dụ minh họa pinning: thao tác ngủ không thể nhường carrier do đang ở trong vùng `synchronized`.
- Đoạn thứ hai giữ **`ReentrantLock`** trong khi ngủ. `Thread.sleep` có thể unmount virtual thread theo cơ chế bình thường vì việc giữ `ReentrantLock` tự nó không pin carrier như monitor ở Java 21.
- `finally` bảo đảm mở khóa ngay cả khi logic trong vùng khóa ném ngoại lệ. Nếu bỏ `unlock()` có thể gây kẹt khóa logic.
- Đây là **demo cơ chế**, không phải benchmark: hai tác vụ chạy lần lượt và có thể kết thúc với thời gian gần nhau. Khác biệt nằm ở carrier được giải phóng khi chờ, không phải ở số mili giây ngủ hay dòng stdout.

Thực tế, dùng `ReentrantLock` vẫn phải giữ tính đúng đắn của critical section; việc unmount virtual thread không có nghĩa là lock đã được thả. Các tác vụ khác cần chính lock đó vẫn phải đợi.

## 5. Quan sát pinning bằng công cụ JDK 21

### 5.1. Stack trace: `jdk.tracePinnedThreads`

Chạy trên JDK 21:

~~~bash
java -Djdk.tracePinnedThreads=full PinningJava21Demo
~~~

JDK có thể in stack trace khi virtual thread thực hiện thao tác blocking trong trạng thái pinned, làm nổi bật các frame native và frame giữ monitor. Cần xem các frame gần dòng `synchronized`/`pause` của demo; **không nên cố định chính xác stack trace**, vì tên frame, dòng nguồn và thứ tự có thể khác theo bản JDK.

Chế độ ngắn:

~~~bash
java -Djdk.tracePinnedThreads=short PinningJava21Demo
~~~

- `full`: nhiều frame, hữu ích để tìm đường gọi đầy đủ và điểm giữ monitor.
- `short`: thông tin ngắn hơn, hữu ích để sàng lọc nhanh.
- Thuộc tính này phục vụ chẩn đoán Java 21; không nên giả định hành vi hay khả năng hỗ trợ của nó hoàn toàn giống nhau trên mọi JDK đời sau.

**Quan trọng:** không thấy stack trace không chứng minh ứng dụng không có vấn đề hiệu năng. Một số tình huống không chạm điểm chờ, chỉ xảy ra dưới tải hoặc không được công cụ này ghi nhận theo cách bạn mong đợi.

### 5.2. Java Flight Recorder: `jdk.VirtualThreadPinned`

Thu thập JFR khi chạy demo:

~~~bash
java -XX:StartFlightRecording=filename=pinning.jfr,dumponexit=true PinningJava21Demo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

Trong JDK 21, sự kiện `jdk.VirtualThreadPinned` được bật mặc định với **ngưỡng thời lượng 20 ms** trong cấu hình ghi thông dụng. Nó ghi nhận một virtual thread bị pin lâu hơn ngưỡng trong thao tác chờ. Với đoạn ngủ 150 ms bên trong monitor, demo được thiết kế để vượt ngưỡng này; sự xuất hiện cụ thể của sự kiện còn tùy môi trường ghi nhận và cấu hình JFR.

Khi đọc sự kiện, quan tâm đến thời lượng, thời điểm, virtual thread liên quan và stack trace. Đối chiếu stack trace với vị trí giữ monitor hoặc lời gọi native. Có thể lọc và phân tích JFR bằng JDK Mission Control khi cần xem toàn bộ mẫu tải.

Nếu không có sự kiện, hãy kiểm tra recording thực sự được tạo, cấu hình sự kiện/ngưỡng và workload có đi qua nhánh blocking hay không. Đừng diễn giải một lần chạy ngắn, ít tải là bằng chứng hệ thống không bao giờ pin.

### 5.3. Đo tác động, không chỉ đếm sự kiện

Trong môi trường kiểm thử mô phỏng lưu lượng thực, nên đánh giá đồng thời:

- **Tần suất/thời lượng pinning**: sự kiện xảy ra ở đâu, có lặp thường xuyên và dài không.
- **Khả năng phục vụ**: throughput, độ trễ trung bình, p95/p99 và các đợt tăng bất thường.
- **Carrier và hàng đợi**: có nhiều tác vụ chờ cơ hội chạy khi số carrier hữu hạn không.
- **Nút thắt độc lập**: DB connection pool, giới hạn socket/file descriptor, khóa chung, downstream API chậm hoặc CPU bão hòa.

Chỉ sửa chỗ pinning thật sự ảnh hưởng thay vì làm một cuộc thay thế `synchronized` trên toàn dự án.

## 6. Cách khắc phục đúng theo nguyên nhân

### Cách 1: Chuyển I/O ra ngoài vùng `synchronized` khi giữ được bất biến

Ví dụ ý tưởng trước–sau (đây là **mã minh họa**, cần thích nghi với tính nhất quán của trạng thái trong ứng dụng cụ thể):

~~~java
// Trước: I/O chậm nằm trong monitor.
synchronized (guard) {
    updateState();
    sendSlowRequest();
}

// Sau: chỉ bảo vệ thao tác trên state, thực hiện I/O ở ngoài.
synchronized (guard) {
    updateState();
}
sendSlowRequest();
~~~

Cách sau giảm thời gian giữ monitor và tránh pinning do monitor trong lúc I/O, nhưng **chỉ hợp lệ nếu quy tắc nghiệp vụ không yêu cầu update và send phải nguyên tử với nhau**. Nếu cần bảo đảm giao dịch, thứ tự, snapshot dữ liệu hoặc chống race, hãy thiết kế cơ chế phù hợp (snapshot, queue, state machine, v.v.); không tự ý di chuyển lời gọi khỏi critical section.

### Cách 2: Thay monitor cần bao bọc blocking bằng `ReentrantLock`

~~~java
// Minh họa bên trong một lớp có field lock là ReentrantLock.
lock.lock();
try {
    blockingOperation();
} finally {
    lock.unlock();
}
~~~

`ReentrantLock` cho phép virtual thread chờ ở một số điểm blocking mà không bị pin bởi **intrinsic monitor**; đây là biện pháp được tài liệu Java 21 khuyến nghị cho vùng khóa có blocking dài và thường xuyên.

Nhưng cần rà soát hợp đồng trước khi đổi:

- `synchronized` tự nhả monitor khi thoát scope; `ReentrantLock` cần `unlock()` trong `finally`.
- `wait()/notify()/notifyAll()` gắn với intrinsic monitor; không thể sao chép nguyên xi. Với lock tường minh, cơ chế chờ/tín hiệu tương ứng là `Condition` và phải thiết kế lại điều kiện chờ đúng.
- Khóa reentrant không giải quyết tình trạng tranh chấp cùng tài nguyên: nhiều virtual thread cùng cần một lock vẫn phải xếp hàng.
- Không giữ lock qua I/O nếu có thể tổ chức lại công việc an toàn và đơn giản hơn.

### Cách 3: Đối với native/JNI/foreign calls, xử lý nguyên nhân trong lời gọi ngoài JVM

Nếu thư viện native thường xuyên chặn lâu:

1. Đo thời gian trong lời gọi native và tìm phiên bản API không blocking/asynchronous nếu có.
2. Tránh giữ thêm các monitor Java qua lời gọi khi không cần.
3. Cân nhắc chuyển công việc native blocking sang **một nhóm platform thread có giới hạn** hoặc một thành phần chuyên trách có kiểm soát tải, nếu chưa thể thay đổi API. Cách này cô lập nhu cầu OS thread, **không biến lời gọi native thành non-blocking**.
4. Giới hạn số tác vụ đồng thời theo năng lực native resource; xử lý timeout, cancellation và backpressure theo hợp đồng API.

Thay `synchronized` thành `ReentrantLock` ở một wrapper **không tự loại bỏ native pinning**. Tương tự, tăng số lượng virtual thread không làm thư viện native có thêm tài nguyên.

### Cách 4: Cân nhắc phiên bản JDK khi có điều kiện

**JDK 21–23** có giới hạn pinning liên quan đến monitor như mô tả ở trên. **JDK 24** đưa vào **JEP 491 — Synchronize Virtual Threads without Pinning**: virtual thread có thể nhả carrier khi chặn trong nhiều tình huống `synchronized` mà JDK 21 phải pin.

Điều này **không xóa mọi nguồn pinning**: tương tác native/foreign và các tình huống JVM khác vẫn phải được kiểm tra. Khi ứng dụng thực tế phải chạy trên **Java 21**, phải chẩn đoán và xử lý theo hành vi Java 21; không áp dụng ngược kỳ vọng của JDK 24.

## 7. Những hiểu lầm và lỗi thường gặp

| Nhận định sai | Cách hiểu đúng ở Java 21 |
|---|---|
| “Dùng `synchronized` là virtual threads bị hỏng.” | Monitor vẫn đúng về đồng bộ; điều đáng lo là virtual thread block **lâu/thường xuyên** khi pinned. |
| “Bất cứ lệnh blocking nào cũng pin.” | Nhiều thao tác blocking được JDK hỗ trợ unmount virtual thread; pinning phụ thuộc ngữ cảnh monitor/native. |
| “`ReentrantLock` làm tất cả các thread dùng khóa chạy song song.” | Lock vẫn loại trừ lẫn nhau. Chỉ carrier có thể được giải phóng khi virtual thread block ở điểm hỗ trợ. |
| “Đổi wrapper Java sang `ReentrantLock` sửa được pinning của JNI.” | Native frame còn tồn tại có thể tiếp tục pin; phải xem lời gọi native và cách thực thi của nó. |
| “Không có `jdk.VirtualThreadPinned` tức là không có pinning.” | Event có ngưỡng, cấu hình và phụ thuộc tải; vắng event không đồng nghĩa không có mọi pinning. |
| “Tăng số virtual thread là tự động tăng throughput.” | Carrier, CPU, khóa, connection pool và downstream vẫn là giới hạn thực; cần đo dưới tải. |
| “Java 24 hết mọi vấn đề carrier pinning.” | JEP 491 xử lý pinning do monitor; vẫn còn các trường hợp khác, nhất là native/foreign. |

## 8. Quy trình kiểm tra một hệ thống Java 21

1. **Xác nhận runtime thực tế** bằng `java -version`. Không diễn giải hành vi Java 21 từ kết quả chạy trên JDK 24+.
2. **Tìm vị trí nghi ngờ**: `synchronized` methods/blocks bao quanh socket/DB/file I/O, sleep hoặc lời gọi native có thể chặn.
3. **Tái hiện bằng workload thực tế**; bật JFR và, khi cần, `-Djdk.tracePinnedThreads=full` để liên kết sự kiện với stack.
4. **Ưu tiên theo tác động**: số lần pin, thời gian giữ carrier và ảnh hưởng tới p95/p99/throughput.
5. **Sửa nhỏ nhất mà vẫn đúng semantics**: thu gọn phạm vi monitor, chuyển I/O ra ngoài khi an toàn, dùng `ReentrantLock` đúng cách hoặc cô lập native blocking.
6. **Đo lại và kiểm tra tính đúng đắn đồng thời**: dữ liệu chia sẻ, thứ tự thao tác, race conditions, thời gian chờ, timeout, giới hạn tài nguyên. Chỉ kết luận cải thiện khi số liệu sau thay đổi xác nhận.

## 9. Ghi nhớ

**Pinning không phải deadlock và cũng không phải lỗi của `Thread.sleep` hay `synchronized` nói riêng.** Trên Java 21, nó là hệ quả của việc virtual thread không thể unmount khi nằm trong một số ngữ cảnh giữ monitor hoặc native frame. Nếu ngữ cảnh đó còn bao quanh một điểm blocking dài, carrier bị giữ chờ, làm mất lợi thế mở rộng số tác vụ I/O của virtual threads.

Tập trung vào **blocking trong vùng có pinning**, chứng minh bằng JFR/trace, và sửa theo ràng buộc đồng bộ hóa của chương trình. Các vùng `synchronized` ngắn, thuần in-memory thường có thể giữ nguyên.

## Tài liệu tham khảo

- [JEP 444 — Virtual Threads, chuẩn hóa trong JDK 21](https://openjdk.org/jeps/444).
- [Oracle Java SE 21 — Virtual Threads: scheduling, pinning và diagnostics](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491).
- [Dev.java — Virtual Threads, giới hạn pinning theo phiên bản JDK](https://dev.java/learn/new-features/virtual-threads/).
