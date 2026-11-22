# Phân biệt lock contention, blocking và carrier pinning

Khi chạy ứng dụng bằng virtual thread trên Java 21, ba hiện tượng thường bị nhầm lẫn là **lock contention**, **blocking** và **carrier pinning**. Chúng có liên quan nhưng mô tả những vấn đề khác nhau: contention nói về tranh chấp quyền truy cập tài nguyên đồng bộ, blocking nói về việc một thread phải chờ, còn pinning nói về việc virtual thread không thể tách khỏi carrier để nhường carrier cho tác vụ khác.

Phân biệt đúng ba khái niệm giúp xác định nguyên nhân làm giảm khả năng mở rộng. Một virtual thread chờ không nhất thiết làm một carrier bị giữ; carrier chỉ bị mất khả năng phục vụ virtual thread khác khi thao tác blocking xảy ra trong tình huống pinning hoặc trong một thao tác không thể unmount.

## 1. Ba khái niệm và mối quan hệ

| Khái niệm | Mô tả | Tác động chính |
|---|---|---|
| Lock contention | Nhiều thread cùng cần một lock; một thread giữ lock còn thread khác phải chờ | Tăng thời gian chờ và giảm mức song song của đoạn code được bảo vệ |
| Blocking | Thread tạm dừng vì chờ I/O, timer, lock, queue, semaphore hoặc điều kiện khác | Tác vụ chưa thể tiếp tục cho đến khi điều kiện chờ được giải quyết |
| Carrier pinning | Virtual thread không thể unmount khỏi carrier platform thread tại thời điểm đó | Nếu virtual thread bị block khi đang pinned, carrier cũng bị giữ và không thể chạy virtual thread khác |

Contention có thể dẫn đến blocking, nhưng không phải mọi blocking đều do lock contention. Pinning cũng không đồng nghĩa với contention: virtual thread có thể bị pinned khi đang thực thi trong vùng `synchronized` mà không hề có thread nào tranh chấp lock. Ngược lại, virtual thread có thể chờ lock qua cơ chế hỗ trợ unmount mà không giữ carrier trong lúc chờ.

## 2. Lock contention: nhiều thread tranh chấp cùng một lock

Lock contention xảy ra khi nhiều thread muốn vào vùng code được bảo vệ bởi cùng một lock. Chỉ thread nắm giữ lock mới được đi qua vùng tới hạn; các thread còn lại phải chờ cho đến khi lock được giải phóng.

```java
import java.util.concurrent.locks.ReentrantLock;

final class Inventory {
    private final ReentrantLock lock = new ReentrantLock();
    private int quantity = 100;

    void reserve(int amount) {
        lock.lock();
        try {
            if (quantity >= amount) {
                quantity -= amount;
            }
        } finally {
            lock.unlock();
        }
    }
}
```

Nếu nhiều virtual thread đồng thời gọi `reserve()`, chúng cạnh tranh trên cùng `ReentrantLock`. Việc chờ lock làm tăng latency; vùng tới hạn càng dài thì các thread khác càng phải chờ lâu.

Contention là vấn đề về mức độ tranh chấp và thời gian giữ lock. Dùng virtual thread không loại bỏ giới hạn tuần tự do một lock duy nhất tạo ra. Nếu vùng tới hạn bảo vệ một thao tác chậm như gọi HTTP hoặc truy vấn database, các thread khác có thể phải xếp hàng lâu.

## 3. Blocking: thread đang chờ một điều kiện

Blocking mô tả trạng thái chờ, không tự nói lên carrier có được giải phóng hay không. Một virtual thread có thể chờ `Thread.sleep`, blocking I/O, `BlockingQueue.take()` hoặc `LockSupport.park()`; với các thao tác được JVM và thư viện hỗ trợ, virtual thread thường được unmount khỏi carrier trong thời gian chờ.

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

static void consume(BlockingQueue<String> queue) throws InterruptedException {
    // Nếu queue rỗng, virtual thread chờ cho đến khi có phần tử.
    String message = queue.take();
    process(message);
}

static void example() {
    BlockingQueue<String> queue = new LinkedBlockingQueue<>();
    Thread consumer = Thread.startVirtualThread(() -> {
        try {
            consume(queue);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    });

    queue.add("order-42");
}
```

Khi `take()` phải chờ, virtual thread có thể nhường carrier để carrier chạy virtual thread khác. Khi phần tử xuất hiện, virtual thread được đánh thức và có thể được mount lên một carrier khả dụng. Đây là lý do blocking I/O tương thích với virtual thread có thể mở rộng tốt hơn mô hình một platform thread cho mỗi tác vụ.

Không phải mọi lời gọi blocking đều có thể unmount. Native method, foreign function hoặc thư viện thực hiện blocking theo cách không được runtime hỗ trợ có thể giữ carrier. Cần xem loại thao tác cụ thể thay vì kết luận chỉ từ việc code có chờ.

## 4. Carrier pinning: virtual thread không thể unmount

Carrier pinning xảy ra khi virtual thread phải tiếp tục gắn với carrier hiện tại. Trong Java 21, các trường hợp quan trọng gồm:

- Virtual thread đang thực thi bên trong một `synchronized` block hoặc `synchronized` method.
- Virtual thread đang thực thi native method hoặc foreign function.

Pinning tự nó không có nghĩa carrier đang bị block. Nếu virtual thread đang chạy một đoạn code ngắn, carrier vẫn đang thực thi công việc bình thường. Vấn đề về khả năng mở rộng xuất hiện khi virtual thread bị pinned rồi thực hiện thao tác blocking: virtual thread không thể unmount, vì vậy carrier cũng bị giữ trong thời gian chờ.

Ví dụ Java 21:

```java
final class RemoteConfig {
    private final Object lock = new Object();

    String refresh() {
        synchronized (lock) {
            // Giữ monitor trong khi gọi thao tác blocking.
            return callRemoteService();
        }
    }
}
```

Nếu `callRemoteService()` chờ mạng trong lúc virtual thread đang ở bên trong vùng `synchronized`, virtual thread bị pinned trên carrier trong thời gian blocking đó. Carrier không thể được tái sử dụng để chạy một virtual thread khác cho đến khi thao tác chờ kết thúc và virtual thread rời vùng pinned.

Đây là ví dụ cần chú ý khi chạy trên Java 21. Một vùng `synchronized` ngắn, không có blocking operation thường không gây vấn đề đáng kể; không cần loại bỏ `synchronized` khỏi mọi đoạn code chỉ vì ứng dụng dùng virtual thread.

## 5. Lock contention có luôn gây carrier pinning không?

Không nên đồng nhất hai hiện tượng. Contention cho biết một thread phải đợi lock; pinning cho biết virtual thread không thể unmount khỏi carrier. Tác động phụ thuộc cơ chế lock, loại thao tác chờ và phiên bản JDK.

Với `ReentrantLock`, cơ chế chờ dựa trên `LockSupport.park()` có thể cho phép virtual thread unmount trong lúc đợi lock. Do đó, nhiều virtual thread tranh chấp một `ReentrantLock` vẫn có thể gây latency và tuần tự hóa công việc, nhưng các thread đang chờ không nhất thiết giữ carrier.

Trong Java 21, monitor-based synchronization (`synchronized`) là một nguồn pinning cần kiểm tra. Đặc biệt, nếu code giữ monitor trong khi gọi I/O hoặc thao tác blocking khác, carrier có thể bị giữ. Khi thấy lock contention, hãy đo và xác định virtual thread có thực sự bị pinned hay không; chỉ số contention đơn lẻ không chứng minh carrier pinning.

## 6. So sánh synchronized và ReentrantLock trong Java 21

| Tiêu chí | `synchronized` trên Java 21 | `ReentrantLock` |
|---|---|---|
| Cơ chế | Monitor của JVM | Explicit lock trong `java.util.concurrent.locks` |
| Tranh chấp lock | Thread không nắm monitor phải chờ | Thread không nắm lock phải chờ |
| Khả năng unmount khi chờ | Có thể gặp pinning trong các tình huống monitor/synchronized của JDK 21 | Cơ chế chờ dựa trên park thường cho phép virtual thread unmount |
| Giải phóng lock | Tự động khi thoát khỏi synchronized block/method | Phải gọi `unlock()` trong `finally` |
| Nên chọn khi | Đoạn tới hạn ngắn, logic đơn giản, không có blocking lâu | Cần các khả năng như `tryLock`, `lockInterruptibly` hoặc cần tránh monitor pinning đã xác định trên JDK 21 |

Ví dụ dùng `ReentrantLock` để không giữ monitor trong lúc chờ dịch vụ:

```java
import java.util.concurrent.locks.ReentrantLock;

final class ConfigService {
    private final ReentrantLock lock = new ReentrantLock();

    String refresh() {
        lock.lock();
        try {
            return callRemoteService();
        } finally {
            lock.unlock();
        }
    }
}
```

`ReentrantLock` không làm mất contention. Nếu một thread giữ lock trong lúc gọi mạng, các thread khác vẫn phải chờ lock. Điểm khác biệt là virtual thread đang đợi lock có thể unmount qua cơ chế park; nhưng thread giữ lock vẫn đang thực hiện thao tác blocking và cần được thiết kế cẩn thận.

Không thay mọi `synchronized` bằng `ReentrantLock` theo kiểu máy móc. Việc chuyển đổi làm tăng trách nhiệm quản lý unlock và có thể thay đổi semantics. Chỉ cân nhắc khi đã xác định vấn đề pinning hoặc cần tính năng lock cụ thể.

## 7. Cách chẩn đoán carrier pinning

Đừng suy luận pinning chỉ từ số lượng virtual thread hoặc thời gian phản hồi tăng. Hãy thu thập bằng chứng từ runtime:

1. Ghi Java Flight Recorder (JFR) trong workload đại diện.
2. Kiểm tra event `jdk.VirtualThreadPinned` và stack trace đi kèm để xác định virtual thread bị pinned ở đâu.
3. Xem pinning có xảy ra trong `synchronized` block/method hay native/foreign call không.
4. Đối chiếu thời gian pinning với throughput, latency, mức sử dụng CPU và số carrier đang bận.
5. Thay đổi một vùng code cụ thể rồi chạy lại cùng workload để so sánh.

Ví dụ khởi chạy ứng dụng kèm JFR recording:

```bash
java -XX:StartFlightRecording=filename=virtual-threads.jfr,settings=profile,dumponexit=true -jar app.jar
```

Có thể xem các event pinning trong recording bằng công cụ `jfr`:

```bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
```

Event `jdk.VirtualThreadPinned` ghi nhận các trường hợp pinning đủ điều kiện theo cấu hình event; việc không thấy event không tự chứng minh rằng mọi loại blocking đều unmount được. Có thể cấu hình JFR để điều tra sâu hơn. Java 21 cũng có tùy chọn chẩn đoán `-Djdk.tracePinnedThreads=full` để in stack trace khi virtual thread bị pinned trong tình huống blocking. Đây là tùy chọn gắn với JDK 21; khi dùng JDK mới hơn, ưu tiên kiểm tra JFR và tài liệu chẩn đoán của đúng runtime thay vì giả định tùy chọn này còn tồn tại.

## 8. Phiên bản JDK ảnh hưởng đến monitor pinning

Phần `synchronized` ở trên mô tả hành vi của Java 21. Cần giữ rõ ranh giới phiên bản khi áp dụng vào môi trường hiện tại: từ JDK 24, JEP 491 đã thay đổi cơ chế để virtual thread có thể unmount khi bị block trong `synchronized` method hoặc block. Vì vậy, không nên áp dụng cảnh báo monitor pinning của Java 21 một cách nguyên xi cho JDK 24 trở lên.

Native method và foreign function vẫn có thể khiến virtual thread bị pinned. Khi nâng JDK, hãy kiểm tra tài liệu và JFR trên đúng runtime đang chạy thay vì dựa vào giả định từ Java 21.

## 9. Nguyên tắc thiết kế để giảm tác động

- Giữ vùng tới hạn ngắn; chỉ bảo vệ thao tác cập nhật trạng thái cần tính nguyên tử.
- Tránh gọi HTTP, truy vấn database, chờ queue hoặc sleep khi đang giữ monitor `synchronized` trên Java 21.
- Không thực hiện native/foreign call có thể block trong đường chạy virtual thread nếu có thể tránh được.
- Nếu cần chờ lock, cân nhắc lock API dựa trên park như `ReentrantLock`, sau khi kiểm tra yêu cầu đồng bộ và đo đạc thực tế.
- Tách lock contention khỏi carrier pinning trong dashboard và phân tích hiệu năng; một vấn đề làm tăng latency, vấn đề còn lại có thể chiếm carrier.
- Không dùng `Thread.sleep()` hoặc lock để điều tiết tài nguyên bên ngoài; dùng semaphore, connection pool hoặc cơ chế backpressure phù hợp.
- Đo trên đúng phiên bản JDK và workload production-like trước khi tối ưu.

## 10. Bảng nhận diện nhanh

| Dấu hiệu | Khả năng liên quan | Bước kiểm tra tiếp theo |
|---|---|---|
| Nhiều thread chờ cùng một lock; vùng tới hạn dài | Lock contention | Xác định lock owner và rút ngắn vùng tới hạn |
| Virtual thread chờ I/O hoặc queue, carrier được giải phóng | Blocking có thể unmount | Kiểm tra API blocking có được runtime hỗ trợ không |
| JFR ghi nhận `jdk.VirtualThreadPinned` với stack trace trong synchronized/native | Carrier pinning | Xem thao tác blocking nào xảy ra trong vùng pinned |
| Throughput thấp dù có nhiều virtual thread, một lock được dùng chung | Contention/serialization | Giảm phạm vi chia sẻ hoặc thay đổi thiết kế dữ liệu |
| Carrier bận lâu trong khi virtual thread đang chờ native call | Pinning do native/foreign call | Xem xét API thay thế hoặc cô lập thao tác trên platform thread |

## 11. Sử dụng và kiểm tra theo Java 21

Virtual threads là tính năng final trong Java 21 qua JEP 444. Có thể dùng `Thread.startVirtualThread`, `Executors.newVirtualThreadPerTaskExecutor`, `ReentrantLock` và JFR mà không cần bật Preview.

```bash
javac --release 21 -d out src/PinningDemo.java
java -XX:StartFlightRecording=filename=pinning.jfr,settings=profile,dumponexit=true -cp out PinningDemo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

Khi triển khai trên JDK mới hơn Java 21, cần kiểm tra thay đổi của runtime, đặc biệt thay đổi monitor pinning từ JDK 24. Không suy rộng một hành vi đặc thù Java 21 thành quy tắc cho mọi phiên bản Java.

## 12. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Java SE 21 API — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [Java SE 21 API — LockSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 — Java Flight Recorder Event Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/jfr/jfr-event-reference.html)
