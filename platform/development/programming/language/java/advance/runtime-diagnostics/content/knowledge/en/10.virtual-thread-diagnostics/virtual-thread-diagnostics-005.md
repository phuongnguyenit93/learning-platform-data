# 10.5 Chẩn đoán pinning trên Java 21 bằng JFR và `jdk.tracePinnedThreads`

**Phạm vi:** Java 21 (virtual threads đã là tính năng chính thức theo JEP 444). Bài này tập trung vào cách phát hiện, đọc bằng chứng và xử lý **carrier-thread pinning** khi virtual thread thực hiện thao tác chặn. Các lệnh quan sát và ví dụ được chọn theo hành vi của **JDK 21**, không suy diễn từ JDK mới hơn.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích được quan hệ giữa **virtual thread**, **carrier/platform thread**, thao tác **mount/unmount**, và vì sao pinning lâu/lặp lại có thể giảm khả năng mở rộng.
2. Nhận diện hai nguồn pinning chính trong Java 21: giữ monitor của `synchronized` và đang thực thi native/foreign frame khi chặn.
3. Thu thập bằng chứng bằng sự kiện JFR `jdk.VirtualThreadPinned` và stack trace từ `-Djdk.tracePinnedThreads=short|full`.
4. Đi từ stack trace đến đoạn mã cần sửa, xác minh trước/sau và tránh kết luận sai khi chỉ thấy `synchronized` hoặc khi không có event.

## 2. Pinning thực sự là gì?

Java 21 lập lịch virtual thread trên một tập nhỏ platform threads, gọi là **carrier threads**. Khi virtual thread gặp một thao tác chặn được JVM hỗ trợ (ví dụ `Thread.sleep` hoặc một số I/O), thông thường JVM **unmount** virtual thread: công việc đang đợi được tạm dừng, carrier được trả lại để chạy virtual thread khác. Sau khi có thể tiếp tục, virtual thread sẽ được **mount** lại; carrier lúc đó không nhất thiết là carrier cũ.

Trên Java 21, nếu một virtual thread **đang giữ monitor `synchronized`**, hoặc đang nằm trong **native method / foreign-function call**, nó có thể không unmount được khi phải chặn. Virtual thread lúc đó **pinned**: carrier phải chờ cùng nó. Nếu nhiều yêu cầu đồng thời cứ giữ carrier trong thời gian dài, số carrier sẵn sàng để chạy việc khác giảm, làm **throughput** và thời gian chờ của hệ thống xấu đi.

```text
Không pin:
virtual thread → bắt đầu chờ → unmount → carrier chạy việc khác → resume

Có pin trên Java 21:
virtual thread → giữ monitor / native frame → bắt đầu chờ
               → không unmount → carrier cũng phải chờ → giảm carrier rảnh
```

**Phân biệt ba khái niệm:**

- **Có `synchronized`** không đồng nghĩa ngay với sự cố: khóa ngắn, chỉ thao tác trong bộ nhớ hoặc rất ít gặp thường không đáng lo.
- **Pinning** là trạng thái không thể giải phóng carrier khi virtual thread chặn; tác hại phụ thuộc **thời lượng, tần suất, mức đồng thời và tải thực tế**.
- **Lock contention/deadlock** là vấn đề riêng. Nhiều thread tranh cùng một monitor có thể tuần tự hóa yêu cầu dù có hay không có pinning. Một event pinning không tự chứng minh deadlock.

Điều cốt lõi cần tìm là **blocking operation nằm ở đâu so với monitor/native frame**, không phải chỉ đếm số chỗ có từ khóa `synchronized`.

## 3. Hai kênh quan sát bổ sung cho nhau

| Công cụ | Bằng chứng chính | Dùng khi nào | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **JDK Flight Recorder (JFR)** | Event `jdk.VirtualThreadPinned`, thời điểm, thời lượng, virtual thread, stack trace | Thu thập theo cửa sổ tải thực tế; so sánh trước/sau | Mặc định chỉ ghi event có thời lượng đạt ngưỡng (thường **20 ms**); không có event không chứng minh tuyệt đối là không pin |
| **`jdk.tracePinnedThreads`** | Stack trace in khi virtual thread chặn trong trạng thái pinned; `full` tô rõ monitor/native frames | Khoanh vùng ngay đoạn mã trong Java 21 | Log có thể rất nhiều; không thay cho số liệu tần suất, throughput và JFR |
| **Thread dump / số liệu hệ thống** | Ngữ cảnh trạng thái thread, độ trễ, hàng đợi, CPU | Điều tra tình huống phức tạp | Không thay thế event pinning và dễ nhầm chờ I/O với pinning |

Theo cấu hình JFR mặc định của **JDK 21**, `jdk.VirtualThreadPinned` được bật với ngưỡng **20 ms**. Hai event `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` mặc định **tắt** để tránh ghi lượng sự kiện rất lớn; `jdk.VirtualThreadSubmitFailed` mặc định bật. Không cần bật Start/End chỉ để điều tra pinning.

## 4. Bài thực hành chạy được trên Java 21

Tạo tệp **`PinningDemo.java`** với nội dung hoàn chỉnh sau. Hai đoạn đều chờ 250 ms; điểm khác nhau là cách quản lý vùng găng. Đoạn đầu cố tình chặn trong `synchronized`, đoạn sau dùng `ReentrantLock`.

```java
import java.util.concurrent.locks.ReentrantLock;

public class PinningDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    public static void main(String[] args) throws InterruptedException {
        Thread pinned = Thread.ofVirtual().name("pinned-demo").start(() -> {
            synchronized (MONITOR) {
                pause();
            }
        });
        pinned.join();
        System.out.println("synchronized: done");

        Thread withLock = Thread.ofVirtual().name("lock-demo").start(() -> {
            LOCK.lock();
            try {
                pause();
            } finally {
                LOCK.unlock();
            }
        });
        withLock.join();
        System.out.println("ReentrantLock: done");
    }

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }
}
```

Biên dịch và chạy trên **JDK 21**, không cần `--enable-preview`:

```bash
java -version
javac PinningDemo.java
java PinningDemo
```

**Hai dòng do chương trình tự in ra stdout** (bỏ qua thông tin phiên bản JVM và các thông báo từ công cụ nếu có):

```text
synchronized: done
ReentrantLock: done
```

Vì cả hai virtual thread được `join()` tuần tự, thứ tự hai dòng là cố định khi ví dụ hoàn tất bình thường. `Thread.sleep(250)` chỉ giả lập thao tác chặn dễ tái hiện; trong hệ thống thực tế thường là I/O, truy vấn DB hoặc lời gọi chờ khác. Đoạn `ReentrantLock` vẫn giữ khóa trong lúc ngủ, nhưng cơ chế khóa này cho phép virtual thread nhường carrier ở thời điểm chặn trên Java 21.

**Không dùng thời gian của chương trình hai tác vụ này để kết luận cải thiện throughput.** Nó là ví dụ để nhận diện event và stack; đo khả năng mở rộng phải dùng nhiều request đồng thời cùng workload thực tế.

## 5. Chẩn đoán bằng JFR trên Java 21

### 5.1. Ghi từ lúc khởi động ứng dụng

Chạy một bản ghi JFR, sau khi chương trình thoát JVM sẽ ghi tệp `pinning.jfr`:

```bash
java -XX:StartFlightRecording:filename=pinning.jfr,settings=default,dumponexit=true PinningDemo
```

Đọc nội dung bằng các công cụ đi kèm **cùng bộ JDK**:

```bash
jfr summary pinning.jfr
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

Kỳ vọng: ít nhất một `jdk.VirtualThreadPinned` ứng với `pinned-demo` trên bản dựng Java 21 phù hợp, vì virtual thread ngủ khoảng 250 ms trong monitor, vượt ngưỡng mặc định 20 ms. Số event, tên trường, stack frame nội bộ, thời lượng thực tế và thông điệp JFR có thể khác giữa bản dựng và lần chạy; **không gán một log giả lập là output chắc chắn**. Nếu bản ghi không có event, dùng mục 7 để kiểm tra phiên bản, cấu hình và phạm vi capture trước khi kết luận.

Khi đọc một event, chú ý:

- `duration`: thời gian thao tác chặn xảy ra trong trạng thái pinned, **không phải** tổng thời gian chạy request.
- `eventThread`: virtual thread của sự kiện; tên thread có thể giúp ghép với request/task.
- `stackTrace`: lần theo frame từ `Thread.sleep`/thao tác chặn về `PinningDemo.pause`, lambda chạy virtual thread và vị trí `synchronized`. Trong code thực tế, lần đến package của ứng dụng và thư viện liên quan.
- `startTime`: đối chiếu với khoảng tăng latency, giảm throughput hoặc tải cao.

Trong JDK 21, đừng đòi các trường giải thích nguyên nhân nâng cao được giới thiệu ở JDK mới hơn. Việc tìm **monitor giữ khi blocking** thường cần kết hợp stack JFR với `jdk.tracePinnedThreads=full` và mã nguồn.

### 5.2. Ghi trên JVM đang chạy

Tìm PID và ghi một cửa sổ tải đại diện (ứng dụng phải còn hoạt động trong thời gian ghi):

```bash
jcmd -l
jcmd <PID> JFR.start name=pinning settings=default duration=60s filename=pinning.jfr
```

Thay `<PID>` bằng mã tiến trình thực tế. Sau khi ghi hoàn tất, xem event:

```bash
jfr print --events jdk.VirtualThreadPinned pinning.jfr
```

Nếu cần điều tra kéo dài, có thể dùng `JFR.check`, `JFR.dump` theo hướng dẫn `jcmd` để kiểm tra và xuất một bản ghi đang chạy. Trên máy chủ cần giới hạn thời gian, dung lượng và bảo vệ tệp JFR vì stack trace có thể chứa thông tin vận hành nhạy cảm.

### 5.3. Phân tích đúng hiện tượng

Một event lâu vài trăm mili giây xuất hiện **một lần** ở thời điểm khởi động có thể không quan trọng. Hàng trăm event trong cùng đường xử lý request, đi kèm latency p95/p99 tăng dưới tải, là dấu hiệu cần ưu tiên. Hãy nhóm theo stack frame ứng dụng, so **số event theo thời gian**, **tổng/độ phân tán `duration`**, mức đồng thời và tác động đến throughput. Đừng cộng mọi `duration` để suy ra tổng thời gian dịch vụ bị nghẽn: nhiều event có thể chồng lấn.

## 6. Chẩn đoán bằng `jdk.tracePinnedThreads`

Tùy chọn này thuộc JVM của **Java 21**; hãy truyền **trước tên lớp hoặc `-jar`**, ngay từ lúc khởi động:

```bash
java -Djdk.tracePinnedThreads=short PinningDemo
java -Djdk.tracePinnedThreads=full PinningDemo
```

- `short` ưu tiên các frame có vấn đề, thích hợp để tìm nhanh điểm pinning.
- `full` in stack đầy đủ hơn, làm nổi bật các frame nắm **monitor** và **native frame**. Trong ví dụ, tìm `PinningDemo.pause` và vị trí lambda có `synchronized`.
- Phần trace của JVM là **đầu ra chẩn đoán bổ sung**, tách biệt hai dòng stdout nghiệp vụ ở mục 4. Không dựa vào thứ tự, số lượng trace hay số dòng cố định trong kiểm thử.

Để ghép với JFR trong **cùng lần chạy**, có thể dùng cả hai tùy chọn:

```bash
java -Djdk.tracePinnedThreads=full -XX:StartFlightRecording:filename=pinning.jfr,settings=default,dumponexit=true PinningDemo
```

Đọc trace để biết **đoạn mã/monitor** nào gây pinning; dùng JFR để biết **khi nào và dài bao lâu**. Stack trace in ra một lần không chứng minh rằng lỗi xảy ra thường xuyên; tương tự, thiếu dòng trace không loại trừ mọi dạng nghẽn carrier.

## 7. Quy trình điều tra một dịch vụ thực tế

1. **Khóa đúng phiên bản:** lấy `java -version` từ **JVM chạy service** (không chỉ JDK trên máy build). Xác nhận Java 21, virtual threads thực sự đang được tạo và workload phát sinh thao tác chặn.
2. **Đặt giả thuyết dựa trên triệu chứng:** khi nhiều request chờ I/O, throughput ngừng tăng hoặc p95/p99 xấu đi; ghi lại tải, CPU, số kết nối, DB pool và số request đang xử lý. Pinning là một giả thuyết, không phải kết luận mặc định.
3. **Ghi JFR trong khoảng tái hiện:** bật `jdk.VirtualThreadPinned` (mặc định bật ở 20 ms), chạy cửa sổ đủ dài bao trùm thời điểm sự cố; giữ bản baseline để so sánh.
4. **Nhóm event và xác định code path:** ưu tiên stack có `duration` lớn và xuất hiện nhiều lần. Tìm lời gọi chặn bên trong một `synchronized` method/block hoặc bên dưới native/foreign frame; xác định thư viện đang sở hữu đoạn đó.
5. **Tái hiện có kiểm soát:** nếu kiểm soát JVM Java 21, khởi chạy môi trường thử nghiệm với `-Djdk.tracePinnedThreads=full` để thấy monitor/native frame tại đúng call site. Chỉ bật mức log chi tiết trong phạm vi cần thiết.
6. **Sửa nguyên nhân có bằng chứng:** chuyển thao tác I/O ra ngoài phần giữ monitor khi bảo toàn được invariant; hoặc đổi monitor có blocking dài/thường xuyên sang `ReentrantLock` với `finally`; với native library, tìm cách không chặn trong callback/native frame hoặc nâng cấp thư viện.
7. **Đo lại cùng workload:** xác minh tính đúng đắn và đối chiếu JFR, số event, phân bố duration, throughput, latency và tài nguyên. Chỉ coi sửa chữa thành công khi nguy cơ pinning giảm **và** không làm hỏng đồng bộ/độ ổn định.

Ví dụ code cần kiểm tra là trường hợp sau:

```java
synchronized (guard) {
    // Có thể mất hàng trăm ms vì đợi mạng hoặc DB:
    callRemoteService();
}
```

Nếu lời gọi không cần nằm trong vùng găng, rút ngắn phạm vi `synchronized` là cách đơn giản nhất. Nếu cần một khóa bao quanh công việc chặn, một hướng thay thế trong Java 21:

```java
lock.lock();
try {
    callRemoteService();
} finally {
    lock.unlock();
}
```

Hai đoạn là **minh họa cấu trúc**, không phải chương trình Java độc lập. `guard`, `lock` và `callRemoteService` phải được định nghĩa trong ứng dụng. Phương án thay thế vẫn có thể gây **lock contention** và tuần tự hóa request, dù giảm pinning carrier. Khi đổi loại khóa, rà soát các đường đọc/ghi cùng dữ liệu, thứ tự acquire/release, ngoại lệ, `wait/notify` (nếu có phải thiết kế lại với `Condition`), và hợp đồng thread-safety của thư viện.

## 8. Khi JFR hoặc trace không cho thấy điều mong đợi

| Tình huống | Kiểm tra và cách hiểu |
| --- | --- |
| Không có `jdk.VirtualThreadPinned` | Xác nhận JDK **21**, recording đúng JVM/PID, thời gian ghi trùm workload, event bật và ngưỡng 20 ms. Pin ngắn hơn threshold có thể không xuất hiện. |
| Có `synchronized` nhưng không có event | Chưa chắc có thao tác chặn trong monitor; đoạn khóa rất ngắn không đáng báo động. Tìm đường thực thi thực tế. |
| Chỉ nhìn thấy `Thread.sleep` trong stack JFR | Lần ngược lên frame ứng dụng; dùng trace `full` để tìm monitor/native frame. `Thread.sleep` ở ngoài monitor bình thường có thể unmount. |
| `tracePinnedThreads` in nhiều dòng | Phân nhóm theo call site và tải, không thay log bằng số lượng tác vụ. Ghi trace dày đặc có thể gây nhiễu và ảnh hưởng hiệu năng. |
| Bản ghi có event nhưng latency vẫn tốt | Pinning không tự động thành sự cố. Ưu tiên theo tần suất, thời lượng và tác động đến carrier/throughput. |
| Sau khi đổi sang `ReentrantLock` vẫn chậm | Kiểm tra tranh khóa, downstream I/O, giới hạn DB pool, CPU, native frame và tài nguyên hệ thống. Chữa pinning không chữa mọi bottleneck. |
| Thử trên JDK 24+ không tái hiện ví dụ | **JEP 491** từ Java 24 thay đổi hành vi `synchronized` để tránh pinning dạng monitor; `jdk.tracePinnedThreads` không còn là công cụ áp dụng như trên Java 21. Dùng **JDK 21** đúng phạm vi bài học. |

Một lỗi suy luận đặc biệt phổ biến là trộn dữ liệu JFR **Java 24+** với hướng dẫn **Java 21**, rồi kỳ vọng cùng trường event hoặc cùng log pinning. Hãy ghi phiên bản JDK bên cạnh mọi bằng chứng.

## 9. Bài tập tự kiểm chứng

1. Chạy chương trình trên **Java 21** với `-Djdk.tracePinnedThreads=full`. Xác định frame của ứng dụng nắm monitor và thao tác `Thread.sleep` gây chặn. Đối chiếu bằng JFR.
2. Đổi thứ tự hai đoạn kiểm tra hoặc chạy riêng đoạn `ReentrantLock`, ghi lại event có liên quan; giải thích tại sao **không** có event là điều được kỳ vọng cho tình huống này.
3. Thử giảm `Thread.sleep(250)` xuống `Thread.sleep(5)`. Dự đoán JFR cấu hình mặc định có thể bỏ qua pin ngắn dưới 20 ms, trong khi trace có thể vẫn cho biết vị trí gây pinning. Giải thích vì sao một lần chạy không đủ làm bằng chứng thống kê.
4. Trong code của bạn, tìm một đường gọi I/O bên trong `synchronized`. Đề xuất thay đổi nhỏ nhất bảo toàn tính đúng đắn; đo p95/p99, throughput, số event trước/sau khi áp dụng dưới cùng cấu hình tải.

**Checklist hoàn thành:** biết version JVM; đã đọc `jdk.VirtualThreadPinned.duration`/stack; xác định được blocking nằm trong monitor/native frame; có bằng chứng về tần suất và tác động; bản sửa giữ đúng thread-safety; đo lại cùng workload.

## 10. Nguồn đối chiếu

- [Oracle Java 21 — Virtual Threads: scheduling, pinning, JFR và tracePinnedThreads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444)
- [Oracle Java 21 — `jcmd` diagnostics/JFR.start](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java 21 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [JEP 491 — khác biệt về monitor pinning từ Java 24](https://openjdk.org/jeps/491)
