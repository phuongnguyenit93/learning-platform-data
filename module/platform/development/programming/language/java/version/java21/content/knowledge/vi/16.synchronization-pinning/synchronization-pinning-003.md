# Pinning khi blocking trong synchronized trên JDK 21

Virtual thread được thiết kế để tạm dừng khi chờ I/O hoặc một thao tác blocking, rồi nhường carrier thread cho virtual thread khác chạy. Tuy nhiên, trên JDK 21, virtual thread không thể unmount khỏi carrier nếu nó bị block trong khi đang thực thi bên trong một `synchronized` block hoặc method. Trạng thái này gọi là *pinning*.

Pinning không làm chương trình sai về mặt đồng bộ, nhưng một carrier bị giữ bởi thao tác blocking sẽ không thể chạy virtual thread khác. Nếu việc này xảy ra thường xuyên và kéo dài, throughput có thể giảm và các virtual thread khác phải chờ carrier rảnh. Đây là hành vi cụ thể của runtime JDK 21; từ JDK 24, JEP 491 đã loại bỏ monitor-related pinning khi blocking trong `synchronized`. Vì vậy, cần đọc bài theo đúng phiên bản JVM đang triển khai.

## 1. Virtual thread và carrier thread

Virtual thread là đối tượng `Thread` được JVM lập lịch trên một tập platform thread. Platform thread đang thực thi virtual thread được gọi là *carrier thread*.

Khi virtual thread chạy, JVM mount nó lên một carrier. Nếu virtual thread thực hiện một thao tác blocking có thể unmount, JVM tạm dừng virtual thread và trả carrier về scheduler. Carrier đó có thể tiếp tục thực thi virtual thread khác trong lúc tác vụ đầu tiên chờ I/O.

```text
Virtual thread A chạy trên Carrier 1
             |
             v
       Gặp thao tác blocking
             |
             v
     Unmount khỏi Carrier 1
             |
             v
Carrier 1 được scheduler dùng cho Virtual thread B
             |
             v
Virtual thread A được mount lại khi có thể tiếp tục
```

Điểm quan trọng là số virtual thread có thể lớn hơn nhiều số carrier. Khả năng unmount khi blocking giúp một số lượng carrier hữu hạn phục vụ nhiều virtual thread đang chờ.

## 2. Pinning trong synchronized trên JDK 21 là gì?

Trên JDK 21, virtual thread bị pin vào carrier khi đang thực thi code bên trong `synchronized` block hoặc method. Nếu nó thực hiện một thao tác blocking tại thời điểm vẫn đang giữ monitor, virtual thread không thể unmount. Carrier thread cũng bị giữ trong thời gian chờ đó.

Ví dụ minh họa bằng `Thread.sleep`:

```java
final class ReportService {
    private final Object lock = new Object();

    void generate() throws InterruptedException {
        synchronized (lock) {
            // Virtual thread đang giữ monitor.
            // Trên JDK 21, sleep làm carrier bị giữ trong lúc chờ.
            Thread.sleep(2_000);
        }
    }
}

Thread.ofVirtual().start(() -> {
    try {
        new ReportService().generate();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
});
```

`Thread.sleep` chỉ dùng để minh họa một điểm blocking. Trong ứng dụng thực tế, tình huống đáng quan tâm thường là gọi I/O, chờ một dịch vụ từ xa, chờ một queue hoặc chờ một điều kiện trong khi vẫn giữ monitor.

Ví dụ cấu trúc dễ gây pinning trên JDK 21:

```java
synchronized (cacheLock) {
    // Giữ monitor trong toàn bộ thời gian gọi mạng.
    Response response = httpClient.send(request, bodyHandler);
    cache.put(request.uri(), response);
}
```

Nếu lời gọi mạng block, virtual thread vẫn giữ `cacheLock` và carrier không thể được giải phóng để chạy virtual thread khác. Nếu hàng trăm hoặc hàng nghìn tác vụ cùng đi qua đoạn này và chờ lâu, nhiều carrier có thể bị chiếm dụng.

Không phải cứ dùng `synchronized` là xảy ra vấn đề. Một critical section ngắn, chỉ đọc/ghi dữ liệu trong bộ nhớ và không chờ I/O thường không gây ảnh hưởng đáng kể. Điều cần chú ý là thao tác blocking diễn ra trong lúc virtual thread còn nằm bên trong vùng synchronized.

## 3. Vì sao pinning ảnh hưởng đến khả năng mở rộng?

Virtual thread giúp mở rộng concurrency bằng cách cho phép một carrier luân phiên chạy nhiều virtual thread. Pinning làm mất lợi ích này trong thời gian carrier bị giữ.

Giả sử scheduler có một số carrier hữu hạn. Nếu nhiều virtual thread cùng block khi đang giữ monitor:

1. Mỗi virtual thread bị pin giữ carrier hiện tại.
2. Các carrier đó không thể chuyển sang chạy virtual thread khác.
3. Virtual thread mới hoặc virtual thread đã sẵn sàng tiếp tục có thể phải chờ carrier rảnh.
4. Throughput giảm dù nhiều công việc thực tế chỉ đang chờ I/O.

JDK 21 không tự tăng parallelism của scheduler để bù cho carrier bị pin. Vì vậy, pinning thường xuyên và kéo dài có thể làm giảm khả năng phục vụ đồng thời. Đây là vấn đề hiệu năng và khả năng mở rộng, không phải lỗi cú pháp hay lỗi memory model của `synchronized`.

Pinning cũng không đồng nghĩa với deadlock. Nếu thao tác blocking cuối cùng hoàn tất, virtual thread có thể tiếp tục, thoát khỏi synchronized block và giải phóng carrier. Nhưng nếu các carrier đều bị giữ bởi những thao tác chờ lâu hoặc không có thời hạn, các virtual thread khác có thể gần như không có cơ hội chạy.

## 4. Phân biệt pinning với monitor contention

Monitor contention xảy ra khi một thread muốn vào `synchronized` block nhưng monitor đang được thread khác giữ. Pinning là trạng thái virtual thread không thể unmount khỏi carrier trong một số tình huống runtime.

Hai khái niệm có liên quan nhưng không giống nhau:

| Tình huống | Ý nghĩa |
|---|---|
| Nhiều thread lần lượt vào một synchronized block ngắn | Có contention, nhưng không nhất thiết tạo vấn đề pinning kéo dài |
| Virtual thread thực hiện I/O blocking trong khi đang giữ monitor trên JDK 21 | Virtual thread bị pin; carrier bị giữ trong thời gian blocking |
| Virtual thread chờ I/O ngoài synchronized block | Thông thường có thể unmount và trả carrier cho scheduler |
| Virtual thread chạy native method hoặc foreign function | Có thể bị pin theo cơ chế riêng, kể cả ngoài synchronized |

Đừng thay toàn bộ `synchronized` chỉ vì ứng dụng có virtual thread. Cần tìm đúng đường thực thi có blocking trong monitor và đo mức độ thường xuyên, thời gian pinning cũng như ảnh hưởng tới throughput.

## 5. Chẩn đoán pinning trên JDK 21

JDK 21 cung cấp hai cơ chế chính để quan sát pinning: system property `jdk.tracePinnedThreads` và JDK Flight Recorder (JFR).

### Dùng jdk.tracePinnedThreads

Khởi chạy ứng dụng với:

```bash
java -Djdk.tracePinnedThreads=full -jar application.jar
```

Hoặc giới hạn stack trace vào các frame liên quan:

```bash
java -Djdk.tracePinnedThreads=short -jar application.jar
```

Khi virtual thread block trong lúc bị pin, JDK có thể in stack trace để chỉ ra các frame liên quan, gồm frame đang giữ monitor. Dựa vào stack trace, lần ngược về đoạn code ứng dụng gọi I/O hoặc thao tác blocking trong synchronized.

`jdk.tracePinnedThreads` là công cụ chẩn đoán của JDK 21. Không nên coi đây là API ứng dụng hoặc dựa vào property này làm cơ chế giám sát lâu dài cho các JDK mới hơn.

### Dùng JDK Flight Recorder

JFR có event `jdk.VirtualThreadPinned`. Trên JDK 21, event này được bật mặc định với threshold 20 ms; event ghi nhận trường hợp virtual thread bị pin trong thời gian vượt threshold và carrier không được giải phóng.

Có thể khởi chạy recording cùng ứng dụng:

```bash
java -XX:StartFlightRecording:filename=virtual-threads.jfr,dumponexit=true \
     -jar application.jar
```

Sau khi recording được tạo, lọc event pinning:

```bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
```

Event giúp xác định thời điểm, thời lượng và stack trace của các trường hợp pinning vượt threshold. Một thao tác pinning rất ngắn có thể không xuất hiện nếu chưa vượt ngưỡng; vì vậy, không có event không chứng minh rằng ứng dụng chưa từng pin.

### Quy trình điều tra

1. Xác nhận tiến trình đang chạy đúng JDK 21, không chỉ kiểm tra phiên bản compiler.
2. Bật `jdk.tracePinnedThreads=full` trong môi trường tái hiện hoặc thu JFR khi tải thực tế.
3. Tìm stack trace có frame synchronized bao quanh thao tác blocking.
4. Xác định tần suất và thời lượng; ưu tiên đường code vừa thường xuyên vừa chờ lâu.
5. Thử thay đổi phạm vi lock hoặc cơ chế đồng bộ trong môi trường kiểm thử và so sánh throughput, latency, số carrier bị giữ.

## 6. Cách giảm pinning trong ứng dụng chạy JDK 21

Mục tiêu là không giữ monitor trong lúc chờ một thao tác có thể kéo dài. Có một số cách triển khai, tùy theo invariant mà ứng dụng cần bảo vệ.

### Rút ngắn synchronized block

Nếu có thể, lấy snapshot dữ liệu cần thiết trong synchronized block, thực hiện I/O bên ngoài monitor, rồi đồng bộ lại để cập nhật trạng thái:

```java
final class ProfileService {
    private final Object lock = new Object();
    private Profile cachedProfile;

    Profile refresh() throws IOException {
        String userId;
        synchronized (lock) {
            userId = cachedProfile.userId();
        }

        // I/O thực hiện ngoài monitor.
        Profile fresh = loadFromRemoteService(userId);

        synchronized (lock) {
            cachedProfile = fresh;
            return cachedProfile;
        }
    }

    private Profile loadFromRemoteService(String userId) throws IOException {
        // Gọi dịch vụ từ xa.
        return fetchProfile(userId);
    }
}
```

Cách này tránh giữ `lock` trong thời gian gọi dịch vụ. Tuy nhiên, dữ liệu có thể thay đổi giữa hai vùng synchronized. Ứng dụng cần kiểm tra lại version, trạng thái hoặc điều kiện cập nhật trước khi ghi kết quả nếu có nhiều request đồng thời.

Không di chuyển I/O ra ngoài lock một cách máy móc nếu thao tác nghiệp vụ yêu cầu tính nguyên tử trên toàn bộ chuỗi đọc-gọi-cập nhật. Hãy xác định invariant trước khi thay đổi vùng đồng bộ.

### Dùng ReentrantLock khi cần giữ quyền khóa qua thao tác blocking

Nếu logic thực sự cần giữ khóa trong lúc thực hiện một thao tác blocking, trên JDK 21 có thể cân nhắc `ReentrantLock`. Khi virtual thread park trong lúc giữ `ReentrantLock`, cơ chế lock của `java.util.concurrent` cho phép virtual thread unmount khỏi carrier; điều này tránh monitor-related pinning của `synchronized`.

```java
import java.util.concurrent.locks.ReentrantLock;

final class RemoteUpdater {
    private final ReentrantLock lock = new ReentrantLock();

    void update() throws IOException {
        lock.lock();
        try {
            callBlockingService();
            updateLocalState();
        } finally {
            lock.unlock();
        }
    }

    private void callBlockingService() throws IOException {
        // I/O có thể block.
    }

    private void updateLocalState() {
        // Cập nhật dữ liệu được bảo vệ bởi lock.
    }
}
```

Luôn nhả lock trong `finally`. Nếu phù hợp với nghiệp vụ, dùng `lockInterruptibly()` để cho phép thread bị interrupt trong lúc chờ lấy lock. `ReentrantLock` không tự làm cho thao tác I/O có thể hủy; nó chỉ thay đổi cơ chế khóa để virtual thread có thể unmount khi park.

Chỉ thay `synchronized` ở những vị trí đã xác định là gây pinning đáng kể trên JDK 21. `synchronized` vẫn là cơ chế đồng bộ đơn giản, an toàn và phù hợp cho critical section ngắn.

### Dùng Semaphore để giới hạn truy cập tài nguyên

Nếu mục đích của synchronized block là giới hạn số lời gọi đồng thời tới một dịch vụ hoặc tài nguyên, `Semaphore` thường mô tả ý định rõ hơn việc giữ monitor trong toàn bộ thời gian I/O:

```java
import java.util.concurrent.Semaphore;

final class RemoteClient {
    private final Semaphore permits = new Semaphore(20);

    Response call(Request request) throws IOException, InterruptedException {
        permits.acquire();
        try {
            return sendRequest(request);
        } finally {
            permits.release();
        }
    }

    private Response sendRequest(Request request) throws IOException {
        // I/O có thể block.
        return performRemoteCall(request);
    }
}
```

Semaphore giới hạn số thao tác đồng thời mà không yêu cầu giữ object monitor qua I/O. Cần chọn số permit dựa trên giới hạn thật của dịch vụ hoặc connection pool. Nếu chỉ cần bảo vệ một cập nhật nhỏ trong bộ nhớ, synchronized hoặc lock đơn giản vẫn phù hợp hơn.

## 7. Những trường hợp không được giải quyết chỉ bằng ReentrantLock

JDK 21 còn có pinning khi virtual thread chạy native method hoặc foreign function. Đây là nguyên nhân riêng, không phụ thuộc vào việc code có nằm trong synchronized block hay không.

Nếu stack trace cho thấy virtual thread bị pin trong JNI hoặc Foreign Function and Memory API, thay `synchronized` bằng `ReentrantLock` không giải quyết được frame native đang giữ carrier. Cần xem xét thời lượng lời gọi native, khả năng chia nhỏ hoặc chuyển lời gọi sang một nhóm platform thread được kiểm soát nếu thư viện native có thể block lâu.

Ngoài ra, pinning không phải nguyên nhân duy nhất khiến virtual thread không đạt throughput kỳ vọng. CPU-bound workload, lock contention, giới hạn connection pool, giới hạn dịch vụ từ xa hoặc I/O không có khả năng unmount cũng có thể tạo bottleneck. Luôn đối chiếu stack trace và số liệu trước khi thay đổi thiết kế đồng bộ.

## 8. Khác biệt từ JDK 24: synchronized không còn gây monitor-related pinning

JEP 491 (*Synchronize Virtual Threads without Pinning*) được tích hợp trong JDK 24. Thay đổi này cho phép virtual thread unmount khỏi carrier khi blocking trong `synchronized` block hoặc method, đồng thời giữ nguyên semantics đồng bộ của Java. Do đó, khuyến nghị thay `synchronized` bằng `ReentrantLock` chỉ để tránh monitor-related pinning không còn cần thiết trên JDK 24 trở lên.

| Runtime | Blocking trong synchronized | Nguyên nhân pinning còn được Oracle nêu |
|---|---|---|
| JDK 21 | Có thể pin virtual thread vào carrier | `synchronized`, native method và foreign function |
| JDK 22–23 | Vẫn có monitor-related pinning | `synchronized`, native method và foreign function |
| JDK 24 trở lên | Không còn pin chỉ vì đang giữ monitor trong `synchronized` | Native method và foreign function |

JEP 491 thay đổi cách runtime thực thi monitor để virtual thread có thể unmount; nó không loại bỏ mutual exclusion, reentrancy hay quan hệ happens-before của `synchronized`. Vì vậy, không cần viết lại các vùng synchronized đúng đắn chỉ vì nâng cấp JDK.

Điểm này cũng có nghĩa mã được biên dịch với `--release 21` nhưng chạy trên JDK 24+ sẽ nhận hành vi runtime mới. `--release 21` đặt mức API/ngôn ngữ/bytecode khi biên dịch; nó không khôi phục cơ chế pinning của runtime JDK 21. Khi điều tra production, hãy xác nhận JDK đang chạy tiến trình.

## 9. Checklist đánh giá pinning trên JDK 21

- [ ] Đã xác nhận ứng dụng thực sự chạy trên JDK 21.
- [ ] Đã xác định virtual thread có thực hiện blocking khi đang ở trong synchronized block/method hay không.
- [ ] Đã phân biệt monitor-related pinning với pinning trong native method/foreign function.
- [ ] Đã dùng `jdk.tracePinnedThreads` hoặc JFR để thu bằng chứng.
- [ ] Đã đánh giá tần suất và thời lượng, không chỉ dựa vào một stack trace đơn lẻ.
- [ ] Đã cân nhắc đưa I/O ra ngoài synchronized block khi invariant cho phép.
- [ ] Chỉ cân nhắc `ReentrantLock` khi cần giữ khóa qua blocking và pinning đã được xác nhận trên JDK 21.
- [ ] Đã cân nhắc Semaphore nếu mục tiêu thực sự là giới hạn concurrency tới một tài nguyên.
- [ ] Đã đo lại throughput và latency sau khi thay đổi.
- [ ] Đã kiểm tra runtime JDK khi triển khai; không áp dụng khuyến nghị JDK 21 cho JDK 24+ một cách máy móc.

## Tài liệu tham khảo

- [Virtual Threads — Java SE 21 Guide](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mount/unmount, các tình huống pinning trên JDK 21, chẩn đoán bằng JFR và `jdk.tracePinnedThreads`.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): thiết kế virtual thread, carrier thread, monitor pinning và giới hạn scheduler trong JDK 21.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi monitor implementation từ JDK 24 để virtual thread có thể unmount khi blocking trong synchronized.
- [Virtual Threads — Java SE 24 Guide](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html): mô tả pinning sau thay đổi JEP 491; native method và foreign function vẫn có thể pin virtual thread.
- [Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-24.html): xác nhận JEP 491 là thay đổi của JDK 24.
