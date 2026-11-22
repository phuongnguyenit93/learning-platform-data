# Phân biệt giới hạn pinning của JDK 21 với cải tiến synchronized từ JDK 24

Virtual thread được đưa vào Java 21, nhưng cách JVM xử lý monitor trong `synchronized` đã được cải tiến ở JDK 24. Vì vậy, khi phân tích carrier pinning, phải xác định **JDK đang chạy ứng dụng**, không chỉ nhìn phiên bản Java mà mã nguồn nhắm đến.

Trong JDK 21, virtual thread có thể bị pin vào carrier khi thực hiện thao tác blocking bên trong `synchronized` block hoặc method. Từ JDK 24, JEP 491 cho phép virtual thread unmount khỏi carrier ngay cả khi đang giữ monitor. Cải tiến này loại bỏ nguồn pinning do monitor, nhưng không loại bỏ lock contention và không giải quyết mọi trường hợp pinning.

## 1. Vì sao phải phân biệt phiên bản JDK?

Java 21 là phiên bản đầu tiên phát hành Virtual Threads dưới dạng tính năng final (JEP 444). Ở phiên bản này, virtual thread thường có thể unmount khi chờ các thao tác blocking được JVM hỗ trợ. Tuy nhiên, nếu thao tác blocking xảy ra trong `synchronized` block hoặc method, virtual thread bị pin vào carrier.

JEP 491 được phát hành trong JDK 24. JEP này thay đổi cách JVM quản lý monitor để virtual thread có thể unmount khi bị block trong khi đang giữ monitor. Mã nguồn dùng `synchronized` không cần viết lại chỉ để nhận cải tiến này; hành vi phụ thuộc runtime JDK thực sự đang chạy.

| Runtime | Blocking trong `synchronized` | Native/foreign call có thể block |
|---|---|---|
| JDK 21 | Có thể pin virtual thread vào carrier | Có thể pin virtual thread vào carrier |
| JDK 22–23 | Vẫn có giới hạn monitor pinning như JDK 21 | Có thể pin virtual thread vào carrier |
| JDK 24 trở lên | Virtual thread có thể unmount khi block dù đang giữ monitor | Vẫn có thể pin virtual thread vào carrier |

JEP 491 thay đổi cơ chế thực thi của JVM, không thay đổi ý nghĩa đồng bộ của `synchronized`: tại một thời điểm vẫn chỉ có một thread sở hữu monitor và các thread khác vẫn phải chờ.

## 2. Hành vi trên JDK 21: blocking trong synchronized có thể giữ carrier

Ví dụ một tác vụ tải dữ liệu từ dịch vụ bên ngoài trong vùng `synchronized`:

```java
final class ConfigService {
    private final Object lock = new Object();

    String refresh() {
        synchronized (lock) {
            // Giả sử đây là lời gọi I/O blocking.
            return fetchRemoteConfiguration();
        }
    }
}
```

Khi virtual thread chạy `refresh()` trên JDK 21, nó sở hữu monitor `lock`. Nếu `fetchRemoteConfiguration()` chờ I/O trong khi vẫn ở trong vùng `synchronized`, virtual thread không thể unmount theo cơ chế thông thường. Carrier đang chạy nó bị giữ trong suốt thời gian blocking.

Điều này có thể làm giảm khả năng mở rộng khi nhiều virtual thread cùng thực hiện các tác vụ tương tự. Số virtual thread chờ có thể tăng lên, trong khi một phần carrier bị giữ bởi các tác vụ đang pinned.

Bản thân việc đi vào `synchronized` không đồng nghĩa carrier lập tức bị chiếm dụng vô ích. Nếu đoạn code ngắn và không có thao tác blocking, carrier vẫn đang thực thi công việc. Vấn đề xuất hiện khi virtual thread bị block trong lúc đang ở trạng thái pinned.

## 3. Hành vi từ JDK 24: có thể unmount khi đang giữ monitor

JEP 491 thay đổi cách JVM gắn quyền sở hữu monitor với virtual thread. Khi virtual thread bị block trong `synchronized`, JVM có thể unmount nó khỏi carrier mà vẫn bảo toàn quyền sở hữu monitor. Carrier được giải phóng để chạy virtual thread khác.

```text
JDK 21
Virtual thread V1 sở hữu monitor
        |
        +-- gọi I/O blocking trong synchronized
        |
        v
V1 bị pin vào carrier C1 trong lúc chờ
        |
        v
C1 chưa thể chạy virtual thread khác

JDK 24+
Virtual thread V1 sở hữu monitor
        |
        +-- gọi I/O blocking trong synchronized
        |
        v
V1 unmount khỏi carrier C1 trong lúc chờ
        |
        v
C1 có thể chạy virtual thread khác
        |
        v
I/O hoàn tất, V1 được mount lại và tiếp tục
```

Monitor vẫn thuộc về V1 trong lúc V1 unmount. Vì vậy, thread khác muốn vào cùng vùng tới hạn vẫn phải đợi V1 thoát khỏi monitor. JEP 491 giải phóng carrier trong lúc chờ; nó không cho phép nhiều thread đồng thời đi vào cùng vùng `synchronized`.

## 4. Điều gì được cải thiện và điều gì vẫn còn?

| Hiện tượng | JDK 21 | JDK 24 trở lên sau JEP 491 |
|---|---|---|
| Virtual thread block trong `synchronized` | Có thể bị pin và giữ carrier | Có thể unmount trong khi vẫn giữ monitor |
| Nhiều thread tranh chấp cùng monitor | Các thread phải chờ monitor | Vẫn phải chờ monitor; contention vẫn tồn tại |
| Vùng tới hạn dài | Làm các thread khác chờ lâu; nếu block có thể giữ carrier | Vẫn làm các thread khác chờ lâu, dù carrier của thread đang chờ có thể được giải phóng |
| Blocking trong native method/foreign function | Có thể pin carrier | Vẫn có thể pin carrier |
| Tác vụ CPU-bound | Chiếm carrier trong lúc thực thi | Vẫn cần CPU và carrier trong lúc thực thi |

Do đó, JDK 24 cải thiện khả năng mở rộng của virtual thread khi blocking trong monitor. Nó không làm code trong vùng tới hạn chạy nhanh hơn, không giảm số lần tranh chấp lock và không biến thao tác blocking thành thao tác bất đồng bộ.

## 5. Lock contention vẫn cần được xử lý

Giả sử một virtual thread giữ monitor trong 2 giây để gọi dịch vụ mạng. Trên JDK 24, carrier có thể được giải phóng trong thời gian chờ, nhưng monitor vẫn bị giữ. Những virtual thread khác cần cùng monitor vẫn phải đợi cho đến khi tác vụ đầu tiên hoàn tất và nhả monitor.

Điều này có thể tạo hàng đợi dài và tăng latency dù carrier pinning đã được loại bỏ. Nếu thao tác I/O không cần nằm trong vùng tới hạn, hãy tách phần cập nhật trạng thái được bảo vệ khỏi phần gọi mạng:

```java
final class ConfigService {
    private final Object lock = new Object();
    private Config current;

    void refresh() {
        Config loaded = fetchRemoteConfiguration();

        synchronized (lock) {
            current = loaded;
        }
    }
}
```

Ví dụ này chỉ phù hợp nếu có thể tải dữ liệu trước rồi cập nhật trạng thái nguyên tử sau đó. Nếu nghiệp vụ yêu cầu giữ một invariant xuyên suốt cả thao tác tải, cần thiết kế lại đồng bộ cẩn thận; không chuyển I/O ra ngoài lock mà bỏ qua tính đúng đắn của dữ liệu.

## 6. Native method và foreign function vẫn là trường hợp cần chú ý

JEP 491 tập trung vào monitor pinning. Khi virtual thread đang thực thi native method hoặc foreign function, JVM vẫn có thể không unmount được virtual thread. Nếu lời gọi native/foreign đó block, carrier có thể bị giữ trong suốt thời gian gọi.

```java
Thread worker = Thread.startVirtualThread(() -> {
    // Giả sử nativeLibraryCall() có thể block.
    nativeLibraryCall();
});
```

Khi tích hợp thư viện native, driver hoặc thành phần gọi mã ngoài JVM, cần kiểm tra cách thư viện thực hiện I/O và blocking. Nếu có thể, ưu tiên API có tích hợp tốt với runtime Java hoặc cô lập phần gọi native có thể block trên platform thread được quản lý riêng.

Không kết luận rằng JDK 24 đã loại bỏ mọi carrier pinning. Cải tiến của JEP 491 loại bỏ nguyên nhân liên quan đến việc giữ monitor trong `synchronized`; các nguyên nhân khác vẫn cần được đánh giá theo runtime và thư viện cụ thể.

## 7. Có cần thay synchronized bằng ReentrantLock sau khi nâng cấp?

Không cần thay `synchronized` chỉ để tránh monitor pinning khi ứng dụng chạy JDK 24 trở lên. JEP 491 được thiết kế để cải thiện trực tiếp hành vi monitor mà không yêu cầu thay đổi mã nguồn.

`ReentrantLock` vẫn hữu ích khi cần các khả năng riêng như `tryLock()`, `lockInterruptibly()`, timeout khi lấy lock hoặc nhiều `Condition`. Nó không tự giải quyết contention: thread khác vẫn phải chờ khi lock đang được giữ.

| Tình huống | Hướng xử lý |
|---|---|
| Ứng dụng chạy JDK 21, blocking trong `synchronized` gây pinning đáng kể | Xem xét rút ngắn vùng monitor; nếu cần giữ lock qua blocking, đánh giá `ReentrantLock` và semantics đồng bộ |
| Ứng dụng chạy JDK 24+, chỉ lo monitor pinning | Không cần đổi `synchronized` chỉ vì lý do pinning; đo lại trên runtime mới |
| Lock contention cao trên JDK bất kỳ | Rút ngắn vùng tới hạn, giảm chia sẻ trạng thái hoặc thay đổi thiết kế đồng bộ |
| Blocking xảy ra trong native/foreign call | Kiểm tra thư viện/API và cân nhắc cô lập thao tác trên platform thread |
| Cần timeout hoặc thử lấy lock không chặn | Cân nhắc `ReentrantLock` vì API điều khiển lock, không phải chỉ vì virtual thread |

Khi dùng `ReentrantLock`, luôn gọi `unlock()` trong `finally`. Việc thay đổi lock primitive có thể ảnh hưởng đến tính công bằng, thứ tự, khả năng reentrancy và cách phối hợp với các thành phần đồng bộ khác.

## 8. Chẩn đoán đúng trên từng runtime

Phải ghi nhận phiên bản runtime trước khi phân tích sự kiện pinning. `--release 21` khi biên dịch chỉ đặt mức ngôn ngữ/API mục tiêu; nó không buộc ứng dụng chạy bằng JVM 21. Nếu bytecode được biên dịch với `--release 21` nhưng chạy trên JDK 24, hành vi virtual thread được quyết định bởi JDK 24.

Kiểm tra runtime đang chạy:

```bash
java -version
```

Ghi Java Flight Recorder để quan sát pinning trong workload đại diện:

```bash
java -XX:StartFlightRecording=filename=virtual-threads.jfr,settings=profile,dumponexit=true -jar app.jar
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
```

Khi đọc kết quả:

- Trên JDK 21, event `jdk.VirtualThreadPinned` có thể giúp phát hiện các lần pinning liên quan đến `synchronized` và native/foreign call.
- Trên JDK 24 trở lên, blocking trong `synchronized` không còn là nguyên nhân pinning theo cơ chế cũ; event còn hữu ích để điều tra các tình huống pinning khác, chẳng hạn native/foreign call.
- Xem stack trace, thời lượng và cấu hình event. Không thấy event không chứng minh ứng dụng không có contention hoặc không có blocking.
- Đối chiếu dữ liệu pinning với throughput, latency, CPU và thời gian chờ lock để xác định vấn đề thực tế.

Tùy chọn `-Djdk.tracePinnedThreads` thường được dùng để chẩn đoán ở JDK 21. Không dựa vào tùy chọn này như công cụ chẩn đoán chung cho JDK mới hơn; ưu tiên JFR và tài liệu đúng phiên bản runtime.

## 9. Lộ trình đánh giá khi nâng từ JDK 21 lên JDK 24+

1. Ghi lại workload, throughput, p95/p99 latency, CPU và số lượng tác vụ đồng thời trên JDK 21.
2. Dùng JFR xác định pinning có liên quan đến `synchronized` hay native/foreign call.
3. Chạy cùng workload trên JDK 24+ với cùng cấu hình tài nguyên và dữ liệu.
4. So sánh số event pinning, thời gian chờ lock, throughput và latency; xác nhận phần cải thiện đến từ runtime.
5. Nếu contention vẫn cao, tối ưu vùng tới hạn hoặc thiết kế dữ liệu độc lập với việc JEP 491 đã loại bỏ monitor pinning.
6. Nếu native/foreign call vẫn giữ carrier, đánh giá thư viện, API thay thế hoặc cách cô lập lời gọi.

Không nên thực hiện một đợt thay thế toàn bộ `synchronized` thành `ReentrantLock` chỉ vì nâng cấp JDK. Giữ nguyên cấu trúc đồng bộ đang đúng về mặt nghiệp vụ, sau đó dùng đo đạc để xác định nơi cần tối ưu.

## 10. Biên dịch và chạy

JEP 444 (Virtual Threads) đã final trong Java 21; JEP 491 (Synchronize Virtual Threads without Pinning) được tích hợp từ JDK 24. Cả hai đều là tính năng JVM đã hoàn thiện, không cần bật Preview.

```bash
javac --release 21 -d out src/SynchronizedVirtualThreadDemo.java
java -cp out SynchronizedVirtualThreadDemo
```

Để kiểm tra hiệu ứng của JEP 491, chạy cùng bytecode trên JDK 21 và JDK 24 trở lên, đồng thời xác nhận runtime bằng `java -version`. Việc đặt `--release 21` không làm runtime JDK 24 quay lại hành vi pinning monitor của JDK 21.

## 11. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [Java SE 21 — Java Flight Recorder Event Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/jfr/jfr-event-reference.html)
