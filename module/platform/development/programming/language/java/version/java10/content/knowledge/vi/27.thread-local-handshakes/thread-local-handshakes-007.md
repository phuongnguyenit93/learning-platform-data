# Quan hệ giữa handshake, safepoint và độ trễ ứng dụng trong HotSpot

*Ngữ cảnh Java 10 — Handshake theo luồng. Bài Knowledge tập trung vào **Thread-Local Handshakes** của JEP 312, sự khác biệt với **global safepoint**, ảnh hưởng đến độ trễ và đuôi phân bố p95/p99/p99.9, cách xác minh trên HotSpot hiện hành. Phần kiến thức cốt lõi vẫn còn áp dụng trên Java 17+, Java 21, Java 25; các ví dụ dùng `javac --release 17`, không dựa vào tính năng đã bị loại bỏ.*

## 1. Câu trả lời ngắn: handshake không phải safepoint toàn cục

Trước khi có cơ chế handshake theo luồng, nhiều thao tác bảo trì/kiểm tra trạng thái của HotSpot cần yêu cầu toàn bộ các Java thread liên quan tiến đến một **global safepoint**. Trong khoảng thời gian đó, các thread đang thực thi Java phải đến trạng thái an toàn để VM thực hiện thao tác cần toàn cục.

**JEP 312 (Java 10)** bổ sung hạ tầng để HotSpot yêu cầu một hoặc nhiều **JavaThread cụ thể** thực thi một callback nội bộ tại trạng thái an toàn, **không nhất thiết phải đưa toàn bộ VM vào global safepoint**. Thread không phải mục tiêu có thể tiếp tục chạy; thread mục tiêu tiếp tục làm việc khi handshake dành cho nó đã hoàn tất.

Điều này giúp giảm phạm vi phải dừng khi một VM operation chỉ cần kiểm tra một thread. Nhưng tuyệt đối không được rút ra kết luận sai rằng:

- Java 10 trở lên **không còn safepoint toàn cục**.
- Một handshake **không gây tạm dừng** bất kỳ thread nào.
- Tất cả thao tác GC, deoptimization, class unloading hoặc stack tracing đều đã chuyển sang thread-local handshake.
- Ứng dụng sẽ tự động có p99/p99.9 nhỏ hơn trong **mọi workload**.
- Có thể gọi một public Java API `handshake(thread)` để điều khiển cơ chế này trực tiếp.

**Đúng hơn:** handshake giúp HotSpot giảm các thao tác cần phối hợp toàn cục **khi VM operation có thể được thực hiện theo từng thread**. Global safepoint vẫn tồn tại cho những thao tác cần trạng thái nhất quán ở phạm vi toàn VM, và độ trễ thực tế còn phụ thuộc GC, scheduler, lock contention, JNI/native, tài nguyên hệ thống, workload.

## 2. Khái niệm nền: JavaThread và safepoint

### 2.1. `JavaThread` trong HotSpot

Một `java.lang.Thread` là đối tượng cấp ngôn ngữ. HotSpot có cấu trúc nội bộ `JavaThread` đại diện cho luồng thực thi Java ở tầng VM. Khi bài này nói “handshake được thực hiện tại thread”, đó là **hạ tầng của HotSpot**, không phải một lời hứa rằng mọi thuộc tính của `Thread` hoặc mỗi virtual thread Java đều có đối tượng OS thread độc lập.

Các cơ chế điều phối nội bộ sử dụng trạng thái an toàn, điểm kiểm tra (*safepoint polling*) và quan hệ giữa thread đang thực thi Java với VM. Những chi tiết như vị trí poll, VM-thread assistance và điều kiện native/JNI phụ thuộc implementation và phiên bản.

### 2.2. Safepoint là gì?

Một **safepoint** là trạng thái/điểm mà HotSpot có đủ thông tin an toàn để thực hiện một số thao tác trên trạng thái thực thi Java. Với **global safepoint**, VM phối hợp để những Java thread liên quan đi tới trạng thái an toàn trước khi chạy một VM operation yêu cầu toàn cục.

Từ “stop-the-world” (STW) thường được dùng để mô tả khoảng thời gian các Java mutator thread bị ngừng tiến độ bình thường trong một số pha GC hoặc VM operation. **Không nên hiểu STW là đóng băng mọi thread hệ điều hành của tiến trình**: thread native, daemon/VM internal và các trạng thái đã an toàn có cách phối hợp khác nhau.

Ví dụ có thể cần global safepoint tùy GC/VM implementation:

- Pha GC yêu cầu dừng mutator, như một phần của quá trình thu gom.
- Một số thao tác xử lý cấu trúc lớp, stack, metadata hoặc VM operation toàn cục.
- Một số dạng thread dump hoặc coordination theo implementation cụ thể.

**Không phải mọi pha GC đều là global STW**, đặc biệt với bộ thu gom đồng thời. Cần quan sát log của đúng GC và đúng JDK.

### 2.3. Thread-local handshake là gì?

Thread-local handshake là hạ tầng HotSpot thực thi một callback/operation nội bộ **liên quan tới từng thread mục tiêu** khi trạng thái của thread đó phù hợp. Target có thể là một thread hoặc một tập thread.

- VM yêu cầu handshake với thread mục tiêu.
- Thread mục tiêu có thể tự xử lý khi tới poll, hoặc hoạt động có thể được thực hiện với sự hỗ trợ của VM thread khi target đang ở trạng thái an toàn phù hợp.
- Sau khi operation dành cho thread đó hoàn tất, thread có thể tiếp tục, **không buộc chờ toàn bộ các thread khác để thoát một global safepoint**, miễn VM operation cụ thể không yêu cầu sự phối hợp toàn cục khác.
- Thread ngoài tập mục tiêu không phải dừng chỉ vì handshake này.

Đây không phải một lệnh “pause” tùy ý như `Thread.suspend()` lịch sử, và cũng không phải một cơ chế synchronization để ứng dụng thay `Lock`, `CountDownLatch`, `volatile` hay memory model Java.

## 3. Sơ đồ thời gian: global safepoint và handshake

### 3.1. Global safepoint

~~~text
Thời gian →
Thread A:  chạy ──────┐ [tạm dừng] ┌────── chạy
Thread B:  chạy ─────┐│ [tạm dừng] │┌───── chạy
Thread C:  chạy ────┐││ [tạm dừng] ││┌──── chạy
                     ↓↓↓          ↑↑↑
VM:             đồng bộ  →  thao tác toàn cục  →  resume
~~~

Giải thích:

1. VM phát tín hiệu yêu cầu global safepoint.
2. Các Java thread liên quan đi đến trạng thái an toàn; không nhất thiết đến cùng một thời điểm.
3. Khi phối hợp đủ, VM thực thi thao tác toàn cục.
4. VM kết thúc safepoint, các Java thread có thể tiếp tục.

Một thread phản hồi chậm hoặc một tình huống JNI/native phức tạp có thể làm giai đoạn **reaching safepoint** lâu. Khi global safepoint đã được thiết lập, độ dài **at safepoint** còn tùy thao tác như GC.

### 3.2. Handshake chỉ nhắm một thread

~~~text
Thời gian →
Thread A:  chạy ────────────────────────────────── chạy
Thread B:  chạy ──[điểm an toàn: callback]───────── chạy
Thread C:  chạy ────────────────────────────────── chạy
VM:                yêu cầu B → callback B kết thúc
~~~

Với operation nhắm thread B, VM có thể không cần dừng A và C. Độ trễ của B vẫn có thể gồm thời gian đến trạng thái an toàn và thực thi callback, nhưng phạm vi ảnh hưởng ít hơn một global stop trong trường hợp phù hợp.

### 3.3. Handshake với nhiều thread

Một handshake operation có thể nhắm **nhiều thread**. Các thread có thể xử lý callback ở những thời điểm khác nhau và tiếp tục sau khi phần riêng hoàn tất; điều này khác với buộc tất cả đứng yên cùng lúc tại một global safepoint. Dù vậy, nếu toàn bộ workload hoặc VM operation cần phối hợp bổ sung, vẫn có thể có chi phí quan sát được.

**Không kết luận “handshake luôn chạy bất đồng bộ hoàn toàn”.** Có thao tác synchronous/asynchronous tùy hạ tầng và VM release, callback cần điều kiện an toàn, và bên yêu cầu có thể phải chờ hoàn tất.

## 4. Vì sao Java 10 (JEP 312) quan trọng?

JEP 312 **Thread-Local Handshakes**, được triển khai trong JDK 10, đặt mục tiêu cung cấp một cách làm rẻ hơn và có tính chọn lọc để thực hiện operation trên Java thread mà không cần mỗi lần đều đạt global VM safepoint.

Một số điểm quan trọng:

- JEP 312 là **thay đổi của JVM/HotSpot**, không mở rộng cú pháp Java hay thêm một phương thức công khai cho developer tự gọi handshake.
- Hạ tầng handshake mở ra cơ hội chuyển **những** VM operation trước đây cần toàn cục sang xử lý trên thread đích khi thích hợp.
- **Không phải tất cả VM operation đều chuyển được**: nếu thao tác cần trạng thái nhất quán toàn cục, global safepoint vẫn cần.
- Lợi ích tiềm năng là **giảm số lần hoặc phạm vi global pause** cho một số việc nội bộ, không bảo đảm giảm toàn bộ thời gian CPU của ứng dụng.

Các bài viết lịch sử thường nhắc tới **biased-lock revocation** là ví dụ hưởng lợi. Nhưng biased locking đã bị ngừng sử dụng/loại bỏ trong các HotSpot hiện đại; **không nên lấy việc bật/tắt biased locking hoặc flag legacy làm hướng dẫn thực hành ngày nay**. Điều còn giá trị là mô hình *per-thread VM operation* và cách quan sát nó.

## 5. Ba khái niệm latency phải tách bạch

Khi thấy request chậm, có ít nhất ba thứ khác nhau:

| Khía cạnh | Câu hỏi | Công cụ quan sát |
| --- | --- | --- |
| **Application latency** | Request/tác vụ mất bao lâu từ góc nhìn người dùng? | Server metrics, tracing, p50/p95/p99 |
| **Global safepoint pause** | HotSpot dừng tiến độ Java mutator bao lâu cho VM operation? | `-Xlog:safepoint=info`, JFR safepoint events |
| **Thread handshake cost** | Một target thread phải phối hợp/thi hành handshake mất bao lâu? | `-Xlog:handshake=info` nếu VM log operation đó, profiler phù hợp |

Ngoài ra, **GC pause** là một nhóm nguyên nhân của global stop, không đồng nhất với mọi safepoint. Một safepoint tên `ThreadDump` có thể không liên quan đến GC; một GC có thể có nhiều pha đồng thời và vài pha STW.

### 5.1. Độ trễ request không bằng tổng mọi safepoint trong JVM

Giả sử một safepoint kéo dài 8 ms, nhưng request đã kết thúc trước khi safepoint xảy ra. Request đó **không tự nhiên tăng 8 ms**.

Muốn đánh giá tác động latency phải xem **thời điểm chồng lấn**:

~~~text
Request X:    |---------- 20 ms ----------|
Global STW:               |--- 8 ms ---|
Request Y:    |-- 3 ms --|
~~~

Trong minh họa, X có thể bị ảnh hưởng bởi STW nếu luồng thực thi của X đang cần tiến triển trong khoảng đó; Y kết thúc trước nên không bị ảnh hưởng bởi pause này. Tác động thực tế còn do scheduling, chồng lấn thao tác khác và queueing; **không tự cộng thời lượng các event vào từng request** nếu không có correlation.

### 5.2. Handshake giảm phạm vi ảnh hưởng, không triệt tiêu chi phí

Đối với một operation nhắm vào worker B, thread B vẫn có thể phải dừng đủ lâu để xử lý nội bộ. Request đang chạy trên B có thể tăng latency, trong khi request trên A/C tiếp tục.

Nếu toàn bộ chương trình nghẽn CPU, lock hoặc I/O, handshake chọn lọc **không giải quyết các bottleneck đó**. Nó chỉ làm giảm nhu cầu dừng **những thread không liên quan** trong một số VM operation.

### 5.3. Tail latency dễ bị ảnh hưởng dù thời gian trung bình nhỏ

Một event 8 ms có thể không làm thay đổi nhiều mức trung bình của hàng triệu request, nhưng có thể đẩy một số request sang vùng p99 hoặc p99.9 nếu event chồng với critical path. Vì vậy cần đo **phân bố độ trễ**, không chỉ “trung bình JVM startup” hoặc một request duy nhất.

Tác động vẫn tùy:

- Tần suất và duration của pause/handshake.
- Số request đang chạy đồng thời.
- Cơ chế scheduler và queueing.
- Heap/GC algorithm, mức cấp phát và pressure.
- Thread pool saturation.
- Mức độ chồng lấn thực sự với request.
- Ngưỡng deadline/SLA/SLO của sản phẩm.

## 6. Ba pha trong safepoint log và cách hiểu

Trong một bản HotSpot hiện hành, log có thể chứa trường:

~~~text
Safepoint "G1CollectFull",
  Reaching safepoint: ... ns,
  At safepoint: ... ns,
  Leaving safepoint: ... ns,
  Total: ... ns
~~~

Giá trị cụ thể phụ thuộc lần chạy. Hiểu từng phần như sau:

1. **Reaching safepoint:** thời gian phối hợp để đưa các Java thread liên quan tới trạng thái an toàn.
2. **At safepoint:** thời gian thực hiện thao tác khi safepoint đã đạt.
3. **Leaving safepoint:** thời gian rời safepoint/cho phép các luồng tiếp tục theo implementation.
4. **Total:** tổng thời gian được HotSpot ghi nhận cho event tương ứng.

Tên trường, cách chi tiết hóa và độ chính xác có thể thay đổi theo JDK. Không được suy rằng toàn bộ `Total` là thời gian “chạy GC”, vì có thao tác safepoint khác và cả chi phí đồng bộ/thoát.

### 6.1. Time to safepoint (TTSP)

**TTSP** thường được dùng để nói thời gian từ khi yêu cầu global safepoint đến khi các thread đã phối hợp tới trạng thái cần thiết. Nếu một thread mất thời gian dài mới phản hồi:

- Tổng safepoint có thể dài dù chính VM operation ngắn.
- Thread khác có thể đã dừng chờ.
- Độ trễ đuôi của request có thể tăng.

Không quy mọi TTSP cao thành “GC thuật toán chậm”: trước hết cần phân biệt pha reaching với pha at-safepoint. JDK, native/JNI section và scheduling đều có thể ảnh hưởng.

### 6.2. Thời gian ở safepoint

`At safepoint` cao có thể do một thao tác VM toàn cục như một pha GC mất nhiều thời gian. Dữ liệu GC log, heap occupancy, allocation rate và loại collector sẽ giúp xác định nguyên nhân.

Nếu reaching rất nhỏ nhưng at lớn, việc tối ưu poll/handshake **không tự giải quyết thời gian thực hiện GC**.

### 6.3. Event quá ngắn vẫn có thể đáng quan sát

JFR hoặc log có thể dùng threshold khác nhau. Một event nhỏ hơn ngưỡng mặc định có thể không xuất hiện trong recording, nhưng không có nghĩa nó chưa xảy ra. Khi cần điều tra micro-pauses, dùng JFR settings phù hợp và cân nhắc chi phí thu thập dữ liệu.

## 7. Thread handshake có thể xuất hiện trong các thao tác nào?

Các loại VM operation liên quan tới trạng thái của một thread có thể tận dụng handshake khi triển khai HotSpot hỗ trợ. Ví dụ:

- Lấy stack thông tin của một thread phục vụ chẩn đoán.
- Một số thao tác VM cần phối hợp xử lý trạng thái thread đích.
- Các cơ chế nội bộ của runtime, profiling hoặc bảo trì thread state ở các bản JDK nhất định.

**Không có cam kết Java SE rằng `Thread.getStackTrace()` phải dùng thread-local handshake.** Đây là một minh họa quan sát **ở bản HotSpot cụ thể**. VM khác hoặc phiên bản khác có thể thực hiện bằng cơ chế khác.

Ngược lại, thread dump tổng thể có thể yêu cầu global safepoint trong một số HotSpot. Điều này cũng **không phải hợp đồng cố định cho mọi JDK và mọi API dump**.

### 7.1. Phân biệt với TLS/HTTP handshake

Từ “handshake” trong chủ đề này **không phải** TLS handshake (`SSLSocket`, HTTPS) hay handshake của network protocol. Các log `-Xlog:handshake` nói về **JVM thread-local handshake**. Đừng dùng `-Djavax.net.debug=ssl:handshake` để điều tra vấn đề JEP 312; cờ ấy thuộc TLS/JSSE.

### 7.2. Phân biệt với Java monitor/lock

Thread đang chờ `synchronized`, `ReentrantLock` hoặc `Thread.sleep` có thể tạo độ trễ ứng dụng nhưng không phải bản thân thread-local handshake. JFR `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` và `jdk.ThreadSleep` giúp điều tra các trạng thái này. Không vì thấy tên “thread” mà gộp tất cả vào safepoint.

## 8. Ví dụ chạy được trên Java 17+: log handshake và safepoint

Bài thực hành sau dùng hai worker thread, ghi nhận một số thao tác chẩn đoán, yêu cầu một GC minh họa và kiểm tra worker vẫn kết thúc an toàn.

**Giới hạn rõ ràng:** chương trình dùng các API Java công khai để **tạo tình huống có thể khiến HotSpot thực hiện handshake hoặc safepoint**. Nó **không** gọi trực tiếp một API handshake công khai (vì không có). Chúng ta dựa vào **log thực tế của JDK thử nghiệm** để kết luận VM dùng cơ chế gì trong run đó.

### 8.1. Chương trình hoàn chỉnh

~~~java
// File: SafepointHandshakeDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class SafepointHandshakeDemo {
    private static final AtomicBoolean RUNNING = new AtomicBoolean(true);
    private static final AtomicLong PROGRESS = new AtomicLong();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        Runnable busy = () -> {
            ready.countDown();
            while (RUNNING.get()) {
                PROGRESS.incrementAndGet();
            }
        };

        Thread first = new Thread(busy, "worker-one");
        Thread second = new Thread(busy, "worker-two");
        first.start();
        second.start();

        try {
            ready.await();
            System.out.println("workers ready = "
                    + (ready.getCount() == 0));
            Thread.sleep(100);

            System.out.println("worker stack visible = "
                    + (first.getStackTrace().length > 0));
            System.out.println("all thread stacks visible = "
                    + !Thread.getAllStackTraces().isEmpty());

            // Chỉ cho demo: có thể yêu cầu Full GC trong HotSpot mặc định.
            System.gc();
            System.out.println("explicit GC requested = true");
            Thread.sleep(100);
        } finally {
            RUNNING.set(false);
            first.join();
            second.join();
        }

        System.out.println("workers terminated = "
                + (!first.isAlive() && !second.isAlive()));
        System.out.println("workers made progress = "
                + (PROGRESS.get() > 0));
    }
}
~~~

**Vì sao dùng `AtomicBoolean` và `AtomicLong`?**

- `RUNNING` là tín hiệu dừng nhìn thấy an toàn giữa các worker và main thread.
- `PROGRESS` ghi nhận hoạt động worker mà không có data race.
- `CountDownLatch` làm main thread biết cả hai worker đã bắt đầu vòng lặp.
- `finally` đảm bảo dừng/join worker kể cả khi có lỗi ở phần giữa.
- `Thread.getStackTrace()` và `Thread.getAllStackTraces()` là thao tác chẩn đoán; không nên gọi liên tục trong đường request nhạy cảm về độ trễ.

Ứng dụng có hai vòng lặp hoạt động CPU ngắn để tạo một số Java thread đang thực thi. Không dùng vòng busy-spin kiểu này trong production; nó phục vụ phép thử ngắn và cố ý tiêu thụ CPU để quan sát VM.

### 8.2. Biên dịch

~~~bash
javac --release 17 SafepointHandshakeDemo.java
~~~

Chương trình dùng API Java 17 và cũ hơn, không cần thư viện bên ngoài.

### 8.3. Chạy với unified logging trên HotSpot

~~~bash
java -Xlog:handshake=info,safepoint=info,gc=info SafepointHandshakeDemo
~~~

Trên PowerShell Windows cũng có thể chạy một dòng tương tự, đặt flag trong dấu nháy nếu shell xử lý dấu đặc biệt:

~~~powershell
java '-Xlog:handshake=info,safepoint=info,gc=info' SafepointHandshakeDemo
~~~

Lựa chọn này sử dụng ba **tag log HotSpot**:

- `handshake`: thao tác thread-local handshake mà VM có log.
- `safepoint`: các global safepoint được VM ghi nhận.
- `gc`: một số thông tin GC, giúp gắn safepoint GC với hoạt động collector.

**Không có bảo đảm mỗi thao tác đều tạo một log dòng và thông báo tên giống nhau qua mọi JDK.** Nếu VM là implementation khác HotSpot, flag `-Xlog`/tag có thể không được hỗ trợ; kiểm tra `java -Xlog:help`.

### 8.4. Stdout ứng dụng được kiểm thử

Khi tách riêng các dòng do ứng dụng in (bỏ những dòng `[info][...]` của JVM), một lần chạy trên **HotSpot JDK 24, biên dịch `--release 17`** cho đúng:

~~~text
workers ready = true
worker stack visible = true
all thread stacks visible = true
explicit GC requested = true
workers terminated = true
workers made progress = true
~~~

Mỗi dòng mô tả **kết quả kiểm thử chương trình**, không phải số liệu latency. Các giá trị dạng boolean thuận tiện để kiểm tra rằng ví dụ thực thi đúng, thay vì hardcode duration phụ thuộc CPU/JDK.

### 8.5. Log VM thực tế — đọc theo ý nghĩa

Cùng lượt thử nghiệm trên có ba dấu hiệu đặc trưng, ví dụ sau chỉ giữ những phần thông tin chính:

~~~text
[info][handshake] Handshake "GetStackTraceClosure", Targeted threads: 1, ...
[info][safepoint] Safepoint "ThreadDump", ... Reaching safepoint: ... ns, At safepoint: ... ns, ...
[info][safepoint] Safepoint "G1CollectFull", ... Reaching safepoint: ... ns, At safepoint: ... ns, ...
~~~

Ba dòng ở trên là **bản lược phần biến thiên**, không phải output nguyên văn có thể dùng để so exact string; log thật có uptime, thời lượng và metadata động. Trong lần chạy thực:

- `first.getStackTrace()` dẫn tới `GetStackTraceClosure` với **Targeted threads: 1** dưới tag `handshake`.
- `Thread.getAllStackTraces()` được HotSpot xử lý qua global safepoint `ThreadDump` trong trường hợp thử nghiệm.
- `System.gc()` làm collector mặc định G1 phát sinh global safepoint `G1CollectFull` trong lần chạy ấy.

**Rất quan trọng:** Những phép ánh xạ trên là **quan sát của HotSpot/JDK 24**, không phải yêu cầu chuẩn Java SE. GC có thể khác, `System.gc()` có thể bị bỏ qua/cấu hình khác, và implementation khác có thể không dùng `ThreadDump` global safepoint cho cùng API.

### 8.6. Điều cần rút ra

Trên **cùng một JVM**, một yêu cầu nhắm **một thread** có thể dùng handshake, trong khi một yêu cầu cần trạng thái **nhiều thread** có thể cần global safepoint. Và cùng lúc đó GC vẫn có safepoint riêng.

Vì vậy câu “JEP 312 thay thế toàn bộ safepoint” bị chính ví dụ này bác bỏ: cả log handshake và log safepoint đều có thể xuất hiện trong cùng một chương trình.

## 9. Có thể dự đoán độ trễ từ demo này không?

**Không dùng thời gian chạy của demo để khẳng định một mức cải thiện p99.** Nó chứng minh **cơ chế quan sát được**, không phải benchmark về handshake.

Vì sao:

1. Hai worker có thể chạy trên những lõi CPU khác nhau hoặc cùng chia sẻ tài nguyên.
2. JVM startup/JIT warmup, GC, OS scheduler và trạng thái máy làm thay đổi thời gian.
3. `System.gc()` là một can thiệp chủ động, không đại diện tần suất GC của ứng dụng thực.
4. `Thread.getStackTrace()` là một public diagnostic call; VM implementation có thể thay cơ chế.
5. App loop ngắn không đại diện hệ thống nhiều request, network/DB và độ trễ hàng đợi.
6. Một log handshake có completion time nhỏ **không** thể quy trực tiếp thành phần tăng tương ứng của từng request.

Demo tốt cho **học và xác minh log**, chưa đủ cho nhận định hiệu năng sản phẩm. Đo tail latency cần workloads, metrics và phương pháp so sánh chuẩn hóa.

## 10. Hướng dẫn đọc log `-Xlog:safepoint` để tìm nguyên nhân pause

Tài liệu `java` JDK 17+ hỗ trợ unified logging:

~~~bash
java -Xlog:safepoint=info MyApp
~~~

Hoặc gộp GC:

~~~bash
java -Xlog:safepoint=info,gc*=info MyApp
~~~

Nếu cần chi tiết hơn trong một môi trường điều tra ngắn:

~~~bash
java -Xlog:safepoint*=debug,gc*=info MyApp
~~~

Dấu `*` trong unified logging chọn những tag set chứa tag yêu cầu, còn `+` chọn tập tag phối hợp. Kiểm tra `java -Xlog:help` trước khi bật ở production để tránh log quá nhiều hoặc chọn nhầm scope.

### 10.1. Chọn đúng trục thời gian

Khi điều tra request p99 tăng:

1. Lấy request timestamp chính xác từ service tracing/metrics.
2. Lấy safepoint log cùng time base và quy đổi epoch/uptime theo cấu hình logging.
3. Xem một request chậm có **chồng lấn** vào global safepoint thật không.
4. Phân biệt `Reaching`, `At` và `Leaving`.
5. Kết hợp GC log, JFR và thread stack để tìm nguyên nhân sâu.
6. Dùng nhiều request/sample để tránh kết luận từ một event đơn lẻ.

**Không tính tổng tất cả duration safepoint trong 1 phút rồi chia số request và tuyên bố đó là latency mỗi request.** Các event có thể chồng với nhiều request, ít request hoặc không trùng request nào.

### 10.2. Thấy nhiều `Safepoint "G1CollectFull"`

Kiểm tra nguyên nhân explicit GC, memory pressure, allocation rate, heap sizing, collector configuration và số lần Full GC. **Không nên tự động tắt GC hoặc đổi collector chỉ vì xuất hiện safepoint**: điều đó có thể tác động correctness/heap safety và sinh ra các vấn đề khác.

### 10.3. Reaching safepoint dài bất thường

Thăm dò:

- Thread nào đang khó đạt trạng thái an toàn theo log/tracing?
- Có native/JNI critical region, blocking hoặc scheduling đặc biệt không?
- Có VM operation nào thực sự yêu cầu global safepoint không?
- Có thay đổi JIT, CPU load hoặc agent/profiler mới không?

**Không khẳng định nguyên nhân chỉ từ một counter**. Cần correlation thread info, VM operation và workload.

### 10.4. Log handshake không có dòng

Không thấy `[handshake]` **không chứng minh handshakes đã bị vô hiệu hóa**. Có thể không phát sinh operation được log ở mức đó, khác JDK/implementation hoặc ngưỡng/option log khác.

Không dùng các flag tắt handshake hoặc safepoint mang tính thử nghiệm/lịch sử như một “mẹo tối ưu” khi chưa hiểu chính xác JVM đang dùng và các ràng buộc. Với JDK hiện đại, ưu tiên **quan sát** và loại bottleneck thực trước.

## 11. Java Flight Recorder (JFR): đo rộng hơn chỉ log

Unified logs phù hợp để thấy sự kiện safepoint/handshake khi VM có ghi. **JFR** giúp điều tra song song cả các nguyên nhân cấp application:

- `jdk.SafepointBegin` và các event safepoint liên quan khi được bật.
- `jdk.ExecuteVMOperation` để liên hệ VM operation.
- GC pause/heap events để đánh giá collection.
- `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`.
- `jdk.ThreadPark`, `jdk.ThreadSleep`.
- I/O events như `jdk.SocketRead` hoặc `jdk.FileRead`.
- CPU method sampling/profiling nếu workload thích hợp.

Tên event, trường dữ liệu, mặc định bật/tắt và threshold có thể khác giữa JDK/release/settings. **Một event vắng mặt không nhất thiết là sự kiện không hề xảy ra**.

### 11.1. Ghi một JFR recording trên JDK 17+

~~~bash
java -XX:StartFlightRecording=filename=run.jfr,settings=profile,dumponexit=true MyApp
~~~

Sau khi ứng dụng kết thúc:

~~~bash
jfr summary run.jfr
jfr print --events jdk.SafepointBegin,jdk.ExecuteVMOperation run.jfr
~~~

Các lệnh dùng tool `jfr` đi cùng JDK. Với chương trình demo của bài, có thể thay `MyApp` bằng `SafepointHandshakeDemo`. JFR sẽ tạo file khi recorder hoạt động và VM kết thúc phù hợp.

**Không bảo đảm recording ngắn sẽ có đủ safepoint events**: template có threshold, và thao tác có thể quá ngắn. Khi cần độ phân giải cao, chỉnh JFR configuration thận trọng và đo overhead. Đừng bật toàn bộ event thấp ngưỡng trên hệ thống production đông request trong thời gian dài chỉ để “đủ dữ liệu”.

### 11.2. Event `jdk.SafepointLatency` từ JDK 25

JDK 25 có **JEP 518 — JFR Cooperative Sampling** và event **`jdk.SafepointLatency`**. Nó đo **độ trễ để một thread đạt safepoint poll tiếp theo sau yêu cầu asynchronous sampling**, dùng để hiểu đặc điểm safepoint sampling; **không** đồng nghĩa tổng thời gian một global STW pause.

Trên **JDK 25+ có hỗ trợ event**, có thể bật:

~~~bash
java -XX:StartFlightRecording:jdk.SafepointLatency#enabled=true,filename=run.jfr MyApp
jfr print --events jdk.SafepointLatency run.jfr
~~~

**Không đưa lệnh này cho JDK 17 như một event chắc chắn tồn tại.** Nó là phần mở rộng JFR mới hơn, không phải API của JEP 312/Java 10. Trước khi dùng, xác nhận event được runtime cung cấp và phù hợp với JFR settings của JDK bạn triển khai.

### 11.3. Đọc JFR để phân biệt nguyên nhân

Nếu request chậm, so event:

- Safepoint/GC trùng thời gian?
- Thread chờ monitor hay park?
- Có SocketRead/SocketWrite lâu?
- CPU runnable liên tục?
- Có kỳ vọng thread-local handshake nhưng log lại cho thấy global VM operation?

Từ đó xây giả thuyết, thử thay đổi **một yếu tố**, đo lại. Không gán lỗi safepoint khi bằng chứng chỉ cho thấy ứng dụng chờ DB hoặc lock.

## 12. Ứng dụng nhiều thread: handshake giúp gì cho tail latency?

Giả sử một dịch vụ có 32 worker threads đang xử lý request. Một VM operation chỉ cần kiểm tra trạng thái worker `T7`.

**Nếu phải global safepoint** cho operation đó, các Java worker khác có thể chịu pause đồng thời. Khi nhiều request cùng chồng vào pause, hàng loạt request có thể tăng latency.

**Nếu operation có thể thread-local handshake nhắm T7**, các worker T1–T6, T8–T32 có thể tiếp tục chạy. Chỉ T7 và chi phí hạ tầng liên quan phải phối hợp trong operation ấy. Điều này tạo **khả năng** giảm số lượng request bị ảnh hưởng và độ rộng “stop-the-world”.

Nhưng không suy ra một công thức cố định:

~~~text
P99 mới = P99 cũ - thời lượng mỗi global safepoint
~~~

Công thức đó sai vì:

- Không phải mọi global safepoint trước đây đều được chuyển sang handshake.
- Request có thể không chồng với những event đó.
- Workload có nhiều nguyên nhân latency khác.
- Scheduler, lock contention, heap pressure và thread pool tác động phi tuyến.
- Handshake vẫn có chi phí của thread đích, có thể làm request ở T7 chậm hơn.

**Đánh giá đúng là thực nghiệm A/B** trên cùng runtime/workload và yêu cầu SLO, không lấy lợi ích lý thuyết làm số đo.

### 12.1. Ví dụ chiến lược đo p99

Chuẩn bị một kịch bản tải có:

~~~text
RPS mục tiêu:      cố định hoặc theo các mức được kiểm soát
Concurrency:       xác định theo traffic thực
Warmup:            đủ lâu để giảm sai lệch JIT/startup
Thời gian đo:      đủ lâu để có số lượng request có ý nghĩa ở p99.9
Metrics:           p50 / p95 / p99 / p99.9 + timeout/error rate
VM signals:        safepoint events, GC pause, handshake logs, CPU load
Environment:       cùng JDK/build, CPU, heap, container resources
~~~

Báo cáo nên có số lượng mẫu và confidence/biến thiên, không chỉ một giá trị percentile duy nhất. Với p99.9, **cỡ mẫu thấp** làm kết luận rất yếu.

## 13. GC vẫn có vai trò độc lập trong bài toán độ trễ

Thread-local handshake không thay thế bộ thu gom rác và không làm mọi GC phase trở thành concurrent.

Các collector khác nhau có profile khác nhau:

- Có collector với những pha STW đáng kể.
- Có collector cố gắng làm nhiều công việc đồng thời cùng Java mutator.
- Có pha vẫn cần stop/coordination, tùy loại GC, JDK và configuration.

Điểm cần nhớ:

1. **Một global safepoint có thể do GC, nhưng không nhất thiết do GC.**
2. **Một GC cycle có thể gồm nhiều pha**, không phải một safepoint duy nhất.
3. **Thread-local handshakes không cam kết loại bỏ toàn bộ GC pauses.**
4. **JFR/GC logs** cho phép đối chiếu nguyên nhân cụ thể thay vì dự đoán từ tên thuật ngữ.

Ví dụ một JDK đã được cấu hình bỏ qua `System.gc()` thì demo có thể không tạo `G1CollectFull`. Trong trường hợp đó **đừng sửa mã production để ép Full GC chỉ để quan sát safepoint**; dùng workload test hợp lý hoặc đọc events thực tế mà ứng dụng tạo ra.

## 14. Safepoint polling và khả năng phản hồi của thread

Handshake và global safepoint đều liên quan đến cơ chế VM nhận biết thread ở trạng thái an toàn. JIT compiler có thể đặt các safepoint polls trong luồng thực thi mã, và việc đi từ Java sang native/blocked state có quy tắc khác nhau.

Điều này giải thích vì sao:

- Một thread cần **thời gian để tiến tới điểm thích hợp**.
- Một operation target một thread vẫn có thể bị chậm bởi trạng thái của chính thread ấy.
- Một thread đang ở trạng thái VM xem là an toàn có thể được xử lý khác so với thread đang liên tục chạy bytecode/JIT-compiled Java.
- Vị trí poll và cơ chế của HotSpot có thể được cải thiện qua JDK releases.

**Không** khuyên developer chèn vô số `Thread.yield()`, `Thread.sleep(0)` hoặc `System.gc()` để “tạo safepoint”. Những thao tác này không phải giải pháp chắc chắn cho TTSP và có thể làm hiệu năng tệ đi hoặc tạo side effects. Đúng hơn, hãy quan sát hiện tượng và nguyên nhân gốc bằng VM logs/profiling.

### 14.1. Thread-native / JNI caveat

Một thread trong JNI critical region hoặc trạng thái native đặc biệt có thể ảnh hưởng cách VM thu trạng thái an toàn và thời gian coordination. Không có một công thức đơn giản “native luôn chặn global safepoint” hay “native không bao giờ gây trễ”.

Dùng log `safepoint`, VM-level diagnostics và thông tin native stack khi phù hợp; tránh suy diễn từ mỗi `Thread.State` Java rằng thread đang “ở safepoint” hay “không ở safepoint”.

## 15. Cách phân biệt ba tình huống thực tế

| Quan sát | Diễn giải có thể | Bước kiểm tra |
| --- | --- | --- |
| Log `Handshake "...", Targeted threads: 1` | VM operation chọn một thread đích | Đối chiếu tên operation và workload; không coi là global STW |
| Log `Safepoint "ThreadDump"` | Trong runtime ấy, VM tạo global safepoint phục vụ thread dump | Xem frequency/duration và nguồn gọi |
| Log `Safepoint "G1CollectFull"` | Full GC trên G1 gây global safepoint | Xem GC cause, heap/allocations |
| Safepoint `Reaching` dài | Thread khó phối hợp đến trạng thái an toàn hoặc vấn đề scheduling | Dùng JFR, threads, JNI/VM logs |
| Safepoint `At` dài | VM operation/GC pha STW dài | Xem GC/VM operation details |
| Handshake completion time dài | Target/VM coordination có chi phí | Điều tra target và tần suất; không suy ngay GC |
| p99 tăng nhưng log safepoint ngắn | Có thể do queue, locks, I/O, CPU, downstream | Xem distributed tracing/JFR contention |
| Không có handshake log | Chưa có bằng chứng cụ thể về handshake đã log | Kiểm tra mức log, workload, JDK; không khẳng định disabled |
| JFR có event `ThreadPark` dài | Thread park/wait, không nhất thiết safepoint | Xem stack, lock, caller |
| GC pause giảm nhưng p99 vẫn lớn | Đã giảm một nguyên nhân nhưng bottleneck khác còn | Lập biểu đồ theo request và event time |

**Cảnh báo về đo lường:** tên event/log có thể đổi theo implementation. Bài này sử dụng ví dụ **HotSpot JDK 24** và tài liệu Java17/25; đừng viết alert production chỉ dựa vào một câu log nguyên văn của một JDK duy nhất mà không có kiểm thử nâng cấp.

## 16. Handshake và virtual threads trên JDK 21+

JDK 21 chuẩn hóa **virtual threads** qua JEP 444. Một ứng dụng có thể có rất nhiều virtual threads được thực thi bởi một số platform/carrier threads. Không nên đồng nhất:

~~~text
1 virtual thread == 1 OS thread == 1 HotSpot JavaThread
~~~

Phát biểu đó không đúng trong mô hình virtual-thread scheduling.

JEP 312 mô tả **hạ tầng HotSpot JavaThread**. Cách các VM operations, stack walking, carrier threads và virtual thread continuations tương tác là chi tiết implementation có thể thay đổi qua JDK. Khi đo latency cho ứng dụng virtual-thread:

- Đo request/task latency theo đúng cấu trúc concurrency của application.
- Tách pinning/blocking, scheduler và queueing khỏi safepoint/handshake.
- Dùng JFR/VM logs đúng version.
- Không coi một event handshake nhắm “một JavaThread” là bằng chứng nó chỉ ảnh hưởng đúng một **logical virtual-thread request** trong mọi trường hợp.

**Không** sử dụng các ví dụ biased locking/Thread.suspend lịch sử để thay cho mô hình concurrency hiện hành.

## 17. Tối ưu hóa thực tế khi thấy độ trễ cao

### 17.1. Bước 1: Xác nhận hiện tượng

Ghi một baseline với request latency percentiles, throughput, error/timeout, CPU, heap, GC, safepoint và thread-level contention. Nếu ứng dụng ổn định, chưa có lý do chỉnh VM flag.

### 17.2. Bước 2: Phân nhóm latency

- GC/VM global pauses có chồng thời gian request?
- Thread chạy hay chờ CPU?
- Monitor/lock contention?
- Network/DB/I/O?
- Thread pool/queue saturation?
- JVM/JIT warmup hoặc dynamic classloading?

Không có một “JVM flag thần kỳ” chữa tất cả.

### 17.3. Bước 3: Xem có operation thread-local hay không

Bật log `handshake` phù hợp, xác định operation tương ứng và thời gian. Nếu VM đã dùng handshake cho một tác vụ, thay đổi code chỉ nhằm “bật handshake” thường không có ý nghĩa.

### 17.4. Bước 4: Giảm nguyên nhân được chứng minh

Ví dụ:

- Nếu Full GC nhiều: xem allocation rate, heap sizing, collector và explicit GC configuration.
- Nếu blocking: giảm lock contention hoặc cải thiện thiết kế synchronization.
- Nếu network: kiểm tra downstream latency, connection pool và timeout.
- Nếu VM operation thread dump bị gọi liên tục: kiểm tra cơ chế giám sát/profiler và tần suất diagnostic requests.
- Nếu safepoint reaching dài: phân tích thread/JNI/VM operation cụ thể.

**Không tắt quan sát/diagnostics hoàn toàn** chỉ để làm log “ít hơn”; chỉnh tần suất và overhead theo yêu cầu vận hành.

### 17.5. Bước 5: A/B và tái kiểm thử

Chỉ công bố cải thiện khi so trên môi trường tương đương, có repeated runs và số liệu khách quan. Khi nâng JDK, GC hoặc profiler, chạy lại baseline vì cơ chế VM đã đổi.

## 18. Sai lầm thường gặp

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Java 10 xóa global safepoints.” | Không. JEP 312 bổ sung khả năng handshake theo thread. |
| “Handshake luôn không pause gì.” | Target thread có thể phải phối hợp/thực thi callback tại trạng thái an toàn. |
| “Mọi GC đều thread-local.” | Không; còn các global safepoints và STW phases. |
| “Bất cứ thread dump nào cũng global safepoint.” | Phụ thuộc API, JDK và implementation; kiểm chứng bằng log. |
| “`Thread.getStackTrace()` được Java SE bảo đảm dùng JEP 312.” | Không; việc nó dùng handshake trong JDK24 chỉ là quan sát. |
| “Có handshake log nghĩa là mọi thread đang stop.” | Không; log có thể nhắm một thread. |
| “Global safepoint là tất cả OS threads đóng băng.” | Là phối hợp trạng thái Java mutator; VM/native internal states có chi tiết riêng. |
| “TTSP và thời gian GC bằng nhau.” | Reaching safepoint khác với time at safepoint và GC phase. |
| “Safepoint có duration 8 ms thì mọi request chậm thêm 8 ms.” | Chỉ những request có critical path chồng vào pause mới có thể bị tác động trực tiếp; còn queueing. |
| “Handshake tự giảm p99 cho mọi workload.” | Chỉ tiềm năng giảm phạm vi một số operation; phải benchmark. |
| “`System.gc()` luôn tạo Full GC.” | Phụ thuộc GC/JVM flags; chỉ dùng như can thiệp demo có kiểm soát. |
| “`-Djavax.net.debug=ssl:handshake` dùng để xem JEP 312.” | Đây là TLS handshake, không phải JVM thread handshake. |
| “Chỉ cần bật `-Xlog:handshake` là đo đầy đủ mọi request stall.” | Cần kết hợp request tracing, GC, JFR và contention. |
| “Thiếu JFR event tức không có safepoint.” | Threshold/recording settings có thể lọc event. |
| “`jdk.SafepointLatency` tồn tại từ Java 10.” | Event mới hơn trong JDK 25/JEP 518; không đồng nghĩa total STW pause. |
| “Thêm `Thread.yield` luôn sửa TTSP.” | Không có bảo đảm, thường gây nhiễu hoặc giảm hiệu năng. |
| “Biased-lock tuning là lời khuyên hiện đại cho handshake.” | Đây là bối cảnh lịch sử; không nên áp dụng flag legacy trong Java hiện hành. |
| “Mỗi virtual thread là một OS thread mục tiêu handshake.” | Virtual threads không ánh xạ 1–1 sang OS threads. |
| “Nhìn GC log không có STW thì application không có stall.” | Lock, I/O, CPU, scheduling và VM operations khác vẫn có thể gây chậm. |
| “Một kết quả chạy trên JDK24 là hợp đồng của Java SE.” | Internal implementation và log format có thể đổi. |

## 19. Bài tập có đáp án

### Bài 1 — Sự khác biệt cốt lõi

**Hỏi:** Global safepoint và thread-local handshake khác nhau ở đâu?

**Đáp án:** Global safepoint cần phối hợp toàn bộ các Java threads liên quan để thực thi VM operation toàn cục; handshake có thể nhắm một/một nhóm thread ở trạng thái an toàn mà không yêu cầu toàn bộ VM dừng đồng thời.

### Bài 2 — JEP và release

**Hỏi:** JEP nào giới thiệu thread-local handshakes và từ JDK nào?

**Đáp án:** **JEP 312**, tích hợp trong **JDK 10**. Đây là cải tiến VM internal, không phải cú pháp Java mới.

### Bài 3 — Public API

**Hỏi:** Java có `Thread.handshake()` công khai để developer tự yêu cầu không?

**Đáp án:** Không có public Java SE API như vậy. JVM thực hiện handshake nội bộ cho các operation được triển khai.

### Bài 4 — Dừng một thread

**Hỏi:** Một VM operation chỉ cần trạng thái thread B. Tại sao handshake có lợi?

**Đáp án:** Có thể hoàn tất trên B mà không bắt A/C đứng yên trong global safepoint; giảm phạm vi ảnh hưởng.

### Bài 5 — GC còn safepoint

**Hỏi:** Có handshake rồi có thể xóa tất cả global safepoint không?

**Đáp án:** Không. Những operation yêu cầu nhất quán toàn cục, bao gồm một số pha GC, vẫn có thể cần global safepoint.

### Bài 6 — Log handshake

~~~text
Handshake "GetStackTraceClosure", Targeted threads: 1
~~~

**Hỏi:** Có thể kết luận mọi worker bị STW không?

**Đáp án:** Không. Log chỉ ra một target thread của handshake đó. Muốn biết global safepoint có xảy ra không phải xem log safepoint riêng.

### Bài 7 — Log safepoint

~~~text
Safepoint "G1CollectFull", Reaching safepoint: ..., At safepoint: ...
~~~

**Hỏi:** Giai đoạn nào liên quan đến phối hợp tới trạng thái an toàn?

**Đáp án:** **Reaching safepoint**. **At safepoint** là giai đoạn ở trạng thái safepoint thực hiện operation; không gộp hai phần.

### Bài 8 — Quan sát trong JDK24

**Hỏi:** Trong demo đã thử, `first.getStackTrace()` và `Thread.getAllStackTraces()` dùng cơ chế gì?

**Đáp án:** Lần thử HotSpot JDK24 cho `GetStackTraceClosure` handshake 1 thread và global safepoint `ThreadDump` tương ứng. Đây là quan sát implementation, không phải contract của API.

### Bài 9 — Request không chồng pause

**Hỏi:** Safepoint 10 ms xảy ra sau khi request đã xong. Có tự cộng 10 ms vào request đó không?

**Đáp án:** Không. Cần correlation theo thời gian/critical path.

### Bài 10 — p99

**Hỏi:** Vì sao giảm một số global safepoint có thể giúp tail latency hơn là trung bình?

**Đáp án:** Pause ngắn nhưng đồng loạt có thể đẩy một phần request sang tail, trong khi trung bình trên số lượng lớn request ít thay đổi. Kết quả thực tế tùy workload và phải đo.

### Bài 11 — Safepoint reaching dài

**Hỏi:** Reaching 20 ms, at-safepoint 1 ms. Có thể nói GC work chắc chắn 21 ms không?

**Đáp án:** Không. 20 ms là thời gian coordination, 1 ms là ở safepoint cho VM operation; cần xem operation và nguyên nhân reaching.

### Bài 12 — Handshake không có log

**Hỏi:** Không thấy `[handshake]` có phải JEP 312 bị tắt không?

**Đáp án:** Không đủ dữ kiện. Có thể không có operation ghi log ở mức được chọn, hoặc JDK dùng cách log khác. Kiểm tra `java -Xlog:help` và điều kiện thử.

### Bài 13 — JFR event

**Hỏi:** `jdk.SafepointLatency` trong JDK25 là tổng thời gian STW của global safepoint?

**Đáp án:** Không. Event đo độ trễ thread đạt poll sau async sampling interrupt (JEP 518), khác tổng một global pause.

### Bài 14 — ThreadPark

**Hỏi:** Một request chậm vì thread bị park 500 ms. Đây có chắc chắn là safepoint không?

**Đáp án:** Không. Park có thể do đồng bộ, chờ queue hoặc condition; xem JFR/thread stacks.

### Bài 15 — System.gc

**Hỏi:** Có nên thêm `System.gc()` vào request path để tạo điểm an toàn?

**Đáp án:** Không. Nó có thể gây GC pause/độ trễ và không phải phương thức tuning handshake.

### Bài 16 — Biased locking

**Hỏi:** Có nên bật biased-lock flag lịch sử để “hưởng lợi JEP 312” trên JDK mới?

**Đáp án:** Không. Đó là ví dụ lịch sử của JEP 312; biased locking không còn là kỹ thuật tuning phù hợp trong các HotSpot hiện đại.

### Bài 17 — Virtual threads

**Hỏi:** Có thể coi mỗi virtual thread trên JDK21 là một OS thread được handshake riêng?

**Đáp án:** Không. Virtual threads dùng mô hình scheduling khác; cần phân biệt logical tasks, carrier/platform threads và VM operations.

### Bài 18 — Phương pháp đánh giá

**Hỏi:** Một benchmark chỉ đo trung bình request đã đủ khẳng định JEP 312 cải thiện latency?

**Đáp án:** Không. Đo p50/p95/p99/p99.9, sample size, CPU, GC, safepoint logs, handshake logs, correlation với request và repeated runs.

## 20. Checklist khi review và điều tra latency

- [ ] Đã biết JDK vendor/version và GC đang dùng chưa?
- [ ] Có phân biệt thread-local handshake với global safepoint không?
- [ ] Có hiểu handshake target thread vẫn phải xử lý callback ở trạng thái an toàn không?
- [ ] Có tránh nói Java10 loại bỏ toàn bộ STW/GC safepoint không?
- [ ] Có xác nhận handshake là cơ chế HotSpot internal, không phải API thread synchronization không?
- [ ] Có tránh nhầm VM handshake với TLS handshake không?
- [ ] Có ghi nhận p95/p99 và error/timeout thay vì chỉ mean không?
- [ ] Có correlation thời gian safepoint với request chậm không?
- [ ] Có đọc đủ Reaching/At/Leaving và phân biệt TTSP với GC work không?
- [ ] Có kiểm tra `-Xlog:safepoint`, `-Xlog:handshake` và GC tags trên runtime đích không?
- [ ] Có dùng JFR để điều tra monitor/park/I/O khi safepoint không giải thích được latency không?
- [ ] Có lưu ý threshold/cấu hình JFR có thể bỏ qua event nhỏ không?
- [ ] Có xem xét global `ThreadDump` hoặc thao tác chẩn đoán bị gọi quá thường xuyên không?
- [ ] Có kiểm soát overhead của profiler/diagnostics và log volume không?
- [ ] Có tránh dùng `Thread.yield`/`System.gc` như “cách sửa TTSP” không?
- [ ] Có hiểu JNI/native/scheduler có thể ảnh hưởng safepoint coordination không?
- [ ] Có đối chiếu các GC phases và không gộp mọi GC thành STW không?
- [ ] Với virtual threads, có phân biệt task và carrier/platform thread không?
- [ ] Có kiểm tra khả năng hỗ trợ `jdk.SafepointLatency` chỉ trên JDK25+ không?
- [ ] Có xem kết quả từ một JDK HotSpot là quan sát, không phải Java SE contract chung không?
- [ ] Có chạy benchmark workload thật, warmup, lặp đủ mẫu trước khi kết luận không?

## 21. Tài liệu chính thức còn áp dụng

- [JEP 312 — Thread-Local Handshakes (JDK 10)](https://openjdk.org/jeps/312): động cơ đưa callback tới những Java thread cụ thể mà không cần global VM safepoint, mô hình operation.
- [JDK 17 — `java` launcher và unified logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): cú pháp `-Xlog`, tag `safepoint`, cách xem `java -Xlog:help`.
- [JDK 25 — `java` launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): tiếp tục hỗ trợ unified logging và các tuỳ chọn chẩn đoán hiện đại.
- [Oracle JDK 17 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): đọc JFR cho CPU, monitor, park, file/socket I/O và những nguồn latency khác.
- [JDK Flight Recorder — `jfr` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): in danh sách event, xem tóm tắt, xử lý recording.
- [JEP 518 — JFR Cooperative Sampling (JDK 25)](https://openjdk.org/jeps/518): thêm event `jdk.SafepointLatency` liên quan độ trễ tới poll trong async sampling, **khác** total STW pause.
- [JDK 25 migration — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận JFR Cooperative Sampling được bổ sung ở JDK 25.
- [JEP 444 — Virtual Threads (JDK 21)](https://openjdk.org/jeps/444): hiểu sự khác biệt logical virtual threads và platform/carrier threads.
- [OpenJDK scalability slides — JEP 312 overview](https://cr.openjdk.org/~redestad/slides/openjdk-scalability.pdf): ví dụ nguyên lý handshake thực hiện per-thread operation, thread hoàn tất phần riêng rồi tiếp tục.

**Ghi nhớ:** **Global safepoint** phối hợp trạng thái an toàn ở phạm vi VM cho thao tác toàn cục; **thread-local handshake** của Java 10 cho phép HotSpot thực hiện những thao tác nội bộ trên **thread đích** mà không nhất thiết dừng mọi Java thread. Điều này có thể giảm pause lan rộng và giúp tail latency cho một số workload, **không thay thế GC safepoint và không bảo đảm p99 luôn giảm**. Dùng `-Xlog:handshake`, `-Xlog:safepoint`, GC logs, JFR và request tracing để phân biệt cơ chế thực tế và đo ảnh hưởng, thay vì suy đoán từ tên gọi.