# Mục tiêu giảm ảnh hưởng của một số thao tác quản trị JVM — Thread-Local Handshakes (Java 10+)

## 1. Bài toán: một thread cần được kiểm tra, vì sao các thread khác phải chờ?

Trong một JVM đang phục vụ hàng nghìn yêu cầu, đội vận hành đôi khi cần đọc trạng thái thread, quan sát stack, thu thập dữ liệu chẩn đoán hoặc thực hiện một thao tác nội bộ liên quan đến một thread cụ thể. Nếu JVM phải đưa **tất cả Java threads** tới một **global safepoint** mỗi khi có một công việc như vậy, các luồng không liên quan cũng bị tạm dừng.

Ví dụ ứng dụng có:

- Luồng A đang thực hiện nghiệp vụ xử lý thanh toán.
- Luồng B đang xử lý một request độc lập.
- Luồng C đang đợi trên lock hoặc I/O.
- Công cụ quản trị hoặc một cơ chế nội bộ JVM muốn kiểm tra trạng thái của **A**.

Với một thao tác thật sự chỉ cần trạng thái an toàn của A, việc buộc cả B và C chờ **có thể gây chi phí toàn JVM không cần thiết**. Đặc biệt trong hệ thống nhiều luồng, một số khoảng dừng ngắn nhưng thường xuyên có thể tạo **jitter** và tác động tới tail latency.

**JEP 312 — Thread-Local Handshakes** (được triển khai trong **Java 10**) bổ sung cơ chế vào **HotSpot JVM** để thực hiện những thao tác thích hợp trên **một Java thread hoặc một tập thread**, mà **không bắt buộc đưa toàn JVM vào global safepoint**. Hạ tầng này tạo điều kiện giảm phạm vi ảnh hưởng của một số thao tác quản trị, quan sát và xử lý nội bộ JVM trên các JDK hỗ trợ.

Điều quan trọng nhất cần nhớ:

> **JEP 312 cung cấp một khả năng ở bên trong HotSpot, không cam kết rằng mọi lệnh JMX, JVMTI, thread dump, GC hay công cụ chẩn đoán đều sẽ tránh global safepoint.**

### Mục tiêu của bài

Sau bài này bạn có thể:

1. Phân biệt **global safepoint** và **thread-local handshake**.
2. Giải thích vì sao giảm số thread bị phối hợp đồng bộ có thể giảm ảnh hưởng đến độ trễ ứng dụng.
3. Hiểu sơ lược **handshake request, polling, safe thread state** và cơ chế hoàn tất thao tác.
4. Phân biệt cơ sở hạ tầng HotSpot với **API Java SE/JMX** dùng để quan sát thread.
5. Hiểu các thao tác vẫn cần global coordination và vì sao lời hứa “zero Stop-The-World” là sai.
6. Đọc log `safepoint` và `handshake` trên đúng JDK, tránh khẳng định điều mà log không chứng minh.
7. Chạy chương trình **Java 21+** minh họa truy vấn riêng một platform thread và dump nhiều thread; đối chiếu với log JDK thử nghiệm.
8. Đánh giá hiệu quả đối với **p99/p99.9 latency**, độ dài/tần suất pause và chi phí profiler/JMX.
9. Hiểu giới hạn với **virtual threads** trên Java hiện đại, không lẫn một virtual thread với platform carrier thread.
10. Lập checklist chẩn đoán phù hợp production mà không dùng cờ/giải pháp legacy.

Bài bám vào **mô hình Java 10 và kiến thức còn áp dụng trong JDK hiện đại**; không đề xuất tắt handshake, bật lại tính năng locking đã lỗi thời, hoặc sử dụng API HotSpot nội bộ như một public API ứng dụng.

## 2. Safepoint là gì? Không phải mọi thread đều dừng theo cùng cách

Một **safepoint** là điểm/trạng thái mà JVM biết có thể thực hiện một số công việc nội bộ yêu cầu các điều kiện về stack, object references, deoptimization hoặc dữ liệu VM được nhất quán.

Ở **global safepoint**, HotSpot phối hợp để các **Java threads liên quan** không tiếp tục thực thi Java code tùy tiện trong lúc một VM operation cần trạng thái đồng bộ toàn cục.

### Đặc điểm

- Thread đang chạy Java code thường kiểm tra **safepoint poll** ở các vị trí do interpreter/JIT tạo.
- Thread ở trạng thái native, blocked hoặc VM state có cơ chế phối hợp khác nhau để bảo đảm an toàn khi vào/ra vùng liên quan.
- Sau khi các Java threads đạt điều kiện cần, VM thực hiện operation.
- Khi operation xong, các thread được phép tiếp tục.

Đây là một khái niệm của **HotSpot runtime**; nó không phải là `Thread.sleep()`, `Thread.join()` hay một loại `synchronized` block.

### Vì sao global safepoint có giá thành?

Một đợt global safepoint có thể có hai phần đáng chú ý:

1. **Time to safepoint (TTSP)**: thời gian phối hợp/đợi để các Java threads đạt trạng thái cần thiết.
2. **Time at safepoint**: thời gian xử lý VM operation khi điều kiện đồng bộ đã đạt.

Chi phí người dùng cảm nhận phụ thuộc tổng độ trễ, tần suất, số luồng bị tác động và hoạt động ứng dụng. Một thao tác nội bộ nhanh **không nhất thiết** tạo ra một pause ngắn nếu việc đưa các thread tới trạng thái an toàn tốn thời gian.

Log có thể hiển thị:

```text
Safepoint "ThreadDump", ... Reaching safepoint: ...,
At safepoint: ..., Total: ...
```

Tên event, các cột và mức chi tiết phụ thuộc HotSpot/JDK. Không đọc một giá trị "At safepoint" riêng lẻ như toàn bộ chi phí pause: cần xét cả giai đoạn **reaching** và **leaving**.

### Global safepoint không có nghĩa mọi native thread của hệ điều hành cùng bị dừng

Safepoint HotSpot phối hợp các Java threads và những trạng thái liên quan của chúng; những thread native không chạy Java hoặc các service thread VM có quy tắc riêng. Vì vậy câu “đóng băng toàn bộ OS process” là cách nói quá mức. Cách diễn đạt chuẩn hơn là **global safepoint chặn tiến độ thực thi Java của những thread liên quan trong phạm vi cần thiết**.

## 3. Thread-local handshake là gì?

**Thread-local handshake** cho phép một **VM operation** được áp dụng trên **thread mục tiêu** mà không nhất thiết cần các Java threads khác cùng tới global safepoint.

Hình dung đơn giản:

```text
Có 4 Java threads:

A: [thực thi] -> [poll / handshake A] -> [tiếp tục]
B: [thực thi] --------------------------> [tiếp tục]
C: [thực thi] --------------------------> [tiếp tục]
D: [chờ I/O] ---------------------------> [theo trạng thái riêng]

Handshake nhắm A:
  chỉ A cần phối hợp với operation cho A;
  không phải đưa B, C, D tới một global safepoint vì riêng operation đó.
```

Đây là **sơ đồ khái niệm**, không phải lời hứa rằng JVM không có một global safepoint khác xảy ra cùng thời gian.

### Cơ chế tổng quát

Trong implementation HotSpot, có thể tóm tắt quá trình:

1. Một thành phần JVM xác định operation có thể thực hiện ở phạm vi thread mục tiêu.
2. JVM đăng ký **handshake closure / request** cho thread đó.
3. Cơ chế **thread-local polling** khiến thread biết có công việc cần xử lý ở một trạng thái an toàn.
4. Operation được thực hiện khi các điều kiện về trạng thái thread được thỏa mãn. Tùy implementation và trạng thái thread, công việc có thể được thực hiện trong context thread đó hoặc được xử lý an toàn bởi một VM/helper thread; **không nhất thiết luôn chạy trực tiếp ở chính application thread**.
5. Sau khi operation của thread được hoàn tất, thread mục tiêu có thể tiếp tục; các thread khác **không phải chờ toàn JVM** chỉ vì handshake đó.

**Đừng suy rằng** một thread bất kỳ có thể gửi một `Runnable` Java tùy ý vào thread khác bằng một public method kiểu `Thread.handshake(callback)`. JEP 312 là hạ tầng **nội bộ JVM**, không bổ sung một API Java SE như vậy.

## 4. Global safepoint và handshake: khác nhau tại đâu?

| Thuộc tính | Global safepoint | Thread-local handshake |
| --- | --- | --- |
| Phạm vi đồng bộ | Các Java threads toàn JVM theo điều kiện operation | Một thread hoặc tập thread mục tiêu |
| Ai phải sẵn sàng? | Những Java threads liên quan đến global operation | Những thread được yêu cầu thao tác |
| Các thread không liên quan | Có thể bị chặn tiến độ Java trong safepoint | Không **bắt buộc** bị dừng chỉ vì handshake đó |
| Dữ liệu toàn JVM nhất quán tại cùng một điểm? | Phù hợp với nhiều operation cần global consistency | **Không tự bảo đảm** snapshot toàn JVM đồng thời |
| Độ trễ | Có chi phí đưa các thread tới điểm an toàn và làm operation | Có thể giảm phạm vi phối hợp khi operation local |
| Có thể vẫn phải chờ? | Có | Có — chờ thread mục tiêu đạt trạng thái phù hợp |
| Có giới hạn thời gian cứng? | Không | **Không** |
| Dùng trực tiếp qua public Java API? | Không phải một API application riêng | Không có public `Thread.handshake(...)` chuẩn |
| Áp dụng cho mọi VM operation? | Không nhất thiết cần mọi operation | **Chỉ những operation đã được JVM hỗ trợ** |

Trong một ứng dụng có rất nhiều thread, lợi ích kỳ vọng là giảm **blast radius**: không kéo các thread không liên quan vào một event chỉ cần phối hợp với A.

### Không phải một cơ chế scheduling tổng quát

Handshake không phải công cụ điều khiển việc thực thi code nghiệp vụ của thread khác như:

- `Thread.interrupt()`;
- `LockSupport.unpark(thread)`;
- Executor/Structured Concurrency;
- Một request gửi qua message queue.

Các công cụ trên phục vụ **cooperation trong ứng dụng**. Thread-local handshakes phục vụ **điều phối việc JVM thao tác an toàn trên trạng thái thread**.

## 5. JEP 312 thực sự mang lại điều gì ở Java 10?

JEP 312 được phát hành cùng **JDK 10** để tạo cơ sở hạ tầng **thực thi callback trên một thread mà không cần global VM safepoint**, theo điều kiện an toàn của HotSpot.

### Điểm cốt lõi

- Chuyển từ mô hình nhiều thao tác phải đồng bộ qua **global safepoint** sang khả năng **per-thread synchronization**.
- Bổ sung/chuẩn hóa cơ chế **poll theo thread** cho các thao tác cần handshake.
- Có thể yêu cầu thao tác trên **một** thread hoặc **nhiều** thread; mỗi thread hoàn tất công việc của mình khi đã đạt điều kiện, không nhất thiết cần giữ tất cả dừng chờ nhau suốt operation.
- Tạo nền tảng cho những cải tiến trong JVM và subsystem liên quan tới stack/GC/diagnostics ở các phiên bản sau.

### Một điều rất dễ hiểu sai

**JEP 312 là infrastructure enabler.** Việc JDK 10 có hạ tầng đó **không chứng minh mọi JMX/JVMTI operation ngay tại JDK 10 đã được viết lại để dùng handshake**.

Giữa hai ý sau có sự khác biệt lớn:

1. **JVM có khả năng** xử lý một operation thread-local mà không cần global safepoint.
2. **Một API hoặc công cụ cụ thể đang dùng khả năng đó** trong một bản HotSpot/JDK cụ thể.

Chỉ ý (1) là khẳng định tổng quát từ JEP 312. Ý (2) phải dựa trên implementation/tài liệu/log của thao tác cụ thể và phiên bản cụ thể.

Trong quá trình phát triển các bản JDK sau, cơ chế xử lý stack/GC concurrent, JVMTI và một số công việc nội bộ tiếp tục sử dụng cơ sở tương tự. Không biến tất cả ví dụ ở lịch sử phát triển thành danh sách **tính năng user-facing Java 10**.

## 6. Tại sao giảm ảnh hưởng của một số thao tác quản trị JVM có ý nghĩa?

Có bốn nhóm chi phí có thể được giảm khi operation được thiết kế phù hợp với per-thread handshake.

### 6.1. Giảm phạm vi những thread bị gián đoạn

Một công cụ chỉ cần thông tin về A. Nếu operation có thể được thực hiện bằng handshake với A, các thread B, C vẫn có cơ hội chạy bình thường. Điều này hữu ích trên server xử lý nhiều request độc lập, đặc biệt với ứng dụng có nhiều platform threads.

### 6.2. Giảm số global safepoints có thể tránh được

Những VM operations trước kia dùng global safepoint vì thiếu cơ chế local có thể được xem xét chuyển sang handshake. Khi thay được, số sự kiện cần đồng bộ toàn JVM có thể giảm. Nhưng **chỉ những operation được JVM thật sự chuyển đổi** mới mang lợi ích này.

### 6.3. Hạn chế jitter và một phần tail latency

Nếu request B bị gián đoạn bởi một safepoint chỉ phục vụ A, response time của B có thể tăng ngoài nhu cầu nghiệp vụ. Giảm những lần chặn vô ích có thể cải thiện **p99/p99.9** trong workload nhạy cảm; đây là **một khả năng cần đo**, không phải kết quả mặc định.

### 6.4. Tạo điều kiện cho observability và low-pause GC hiện đại

Một số cơ chế quan sát stack, JVMTI và garbage collector hiện đại cần phối hợp với thread để đọc/chỉnh trạng thái an toàn mà không chặn tất cả application threads. Thread-local handshakes và các cơ chế liên quan giúp mở đường cho những tối ưu như vậy.

Ví dụ trong lịch sử phát triển, JEP 376 (*ZGC: Concurrent Thread-Stack Processing*, JDK 16) chuyển thêm công việc xử lý stack liên quan GC sang hướng concurrent. Đây là **tính năng của các JDK sau**, không được nhầm rằng mọi collector Java 10 đã có mức độ concurrent như JDK hiện tại.

## 7. Handshake không biến mọi thao tác quản trị thành zero-pause

Các thao tác sau có thể yêu cầu sự nhất quán trên diện rộng hoặc những điều kiện mà một handshake thread đơn lẻ không đủ:

- Một số pha **Stop-The-World garbage collection**.
- Các VM operations cần đồng bộ dữ liệu toàn JVM.
- Các dạng class redefinition, deoptimization hoặc metadata maintenance tùy implementation.
- Heap inspection, heap dump và thread dump trong những đường triển khai nhất định.
- Một số hoạt động attach/diagnostic/safepoint cleanup.
- Công cụ lấy thông tin toàn cục và yêu cầu snapshot nhất quán ở một thời điểm.

**Không khẳng định bất kỳ operation nào trong danh sách trên _luôn_ cần global safepoint trên mọi JDK**. Điểm đúng là **không có bảo đảm chung rằng chúng đều có thể xử lý bằng một handshake một luồng**.

### Ví dụ thực nghiệm rất quan trọng

Trong lần thử với **Zulu OpenJDK 24.0.2 (HotSpot)**, việc gọi:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo one = bean.getThreadInfo(target.threadId(), 12);
```

**vẫn được log** thành một sự kiện safepoint `ThreadDump`. Lời gọi:

```java
ThreadInfo[] all = bean.dumpAllThreads(false, false);
```

cũng được log thành `ThreadDump` safepoint.

Điều này bác bỏ cách suy luận “vì `getThreadInfo` chỉ hỏi một thread nên chắc chắn nó dùng handshake và không cần Stop-The-World”. Sự khác biệt **API scope** và **implementation scope** phải được giữ rõ.

**Một phép đo của một JDK** không chứng minh mọi JDK đều xử lý y hệt; do đó khi đặt câu hỏi về performance hoặc “có STW không?”, phải đo trên runtime mục tiêu.

## 8. ThreadMXBean, JVMTI, JFR và Thread-Local Handshakes liên hệ thế nào?

Các từ này thường được nhắc gần nhau nhưng ở các tầng khác nhau.

| Công nghệ/API | Vai trò | Khả năng/giới hạn cần hiểu |
| --- | --- | --- |
| **JEP 312 / HotSpot Handshake** | Hạ tầng nội bộ VM cho per-thread operation | Không phải một Java SE callback API trực tiếp |
| **ThreadMXBean (JMX)** | Theo dõi/troubleshoot platform threads | Phương thức cụ thể có thể tốn chi phí; không mặc định dùng handshake |
| **JVMTI** | Native tooling interface cho agents/debugger/profiler | VM implementation có thể dùng handshake; quyền/callback và overhead tùy function |
| **Java Flight Recorder (JFR)** | Thu thập sự kiện runtime/profiling trên JVM hỗ trợ | Cấu hình event, sampling và buffer có overhead; không đồng nghĩa mọi event không safepoint |
| **jcmd/jstack thread dump** | Công cụ chẩn đoán tình trạng thread | Lệnh và implementation phụ thuộc JDK; không tự giả định dump là zero-pause |
| **GC logs** | Theo dõi collection events và pause | GC có những lý do riêng; không phải mọi safepoint là GC |

### Một thread dump không phải “Thread Handshake API”

Dù công cụ hiển thị stack một thread, VM có thể cần bước đồng bộ rộng hơn để lấy dữ liệu ổn định. Hãy phân biệt:

- **Người dùng yêu cầu thông tin của một thread**.
- **VM triển khai lời yêu cầu bằng phương pháp nào**.

Hai câu hỏi **không bắt buộc** có cùng câu trả lời.

### ThreadMXBean trong Java hiện đại và virtual threads

Trong Java SE 21+ với **virtual threads**, `ThreadMXBean` được tài liệu hóa là theo dõi **platform threads**, không cung cấp monitoring/management đầy đủ cho **virtual threads**. Các API như `getAllThreadIds()` và `dumpAllThreads(...)` không bao quát toàn bộ virtual threads.

Vì vậy demo của bài sử dụng `Thread.ofPlatform()` để xác định rõ phạm vi. Không gán mọi “Java thread” trong hệ thống virtual-thread-heavy cho đối tượng `ThreadMXBean`. Khi cần quan sát virtual threads, tham khảo công cụ/JFR và khả năng của JDK hiện hành.

### JFR: lựa chọn khi cần quan sát có kiểm soát

Với một hệ thống production, JFR có thể hỗ trợ thu thập sự kiện ở mức phù hợp với chi phí cho phép. Nhưng trước khi bật recording hoặc sampling dày, cần xem settings như event threshold, stack trace và chu kỳ thu thập. JFR không phải một phép đo miễn phí và **không tự chứng minh** JEP 312 đã được dùng trong từng đường code.

## 9. Những gì một handshake cần bảo đảm để VM vẫn đúng

Một handshake local **không phải thao tác được phép đọc tùy tiện bộ nhớ thread khi nó đang mutate**. JVM phải bảo đảm trạng thái phù hợp:

1. **Thread target an toàn tại thời điểm thao tác**. Ví dụ stack/frame đang được đọc phải ở trạng thái mà VM hiểu được.
2. **Không phá thứ tự và tính nhất quán của VM state** đối với từng operation.
3. **Xử lý transition** giữa Java/native/blocked/VM states theo quy tắc HotSpot.
4. **Bảo đảm tiến độ** phù hợp: thao tác có thể cần chờ target hoặc nhận trợ giúp của VM thread.
5. **Không đổi ngữ nghĩa Java program**. Một tối ưu nội bộ không được phép gây kết quả sai để đổi lấy độ trễ ngắn.
6. **Phối hợp với global safepoints khác** khi cần, không giả định hai cơ chế tách biệt tuyệt đối về mặt scheduling.

Một operation chỉ có thể chuyển sang thread-local handshake khi **đúng hợp đồng của operation đó**. Ví dụ một công việc cần nhìn thấy toàn bộ heap và tất cả root references tại cùng một trạng thái nhất quán không thể tự động được thay bằng “xử lý thread A” mà không thay đổi thiết kế thuật toán.

### Chờ đợi vẫn có thể xảy ra

Nếu target thread đang ở trạng thái cần phối hợp phức tạp, handshake có thể mất thời gian. Nó **không phải hard realtime deadline**, và không phải cơ chế “ngắt bất kỳ native call nào ngay lập tức”.

Do đó tránh ngôn ngữ như:

- “Handshake hoàn thành dưới 1 ms.”
- “Chỉ cần có JDK 10 là hết Stop-The-World.”
- “Mọi lệnh chẩn đoán trên một thread đều không ảnh hưởng request khác.”
- “Thread-local handshake chắc chắn nhanh hơn global safepoint trong mọi trường hợp.”

Các phát biểu đó vượt quá hợp đồng JEP 312.

## 10. Chương trình Java 21+ hoàn chỉnh: targeted inspection và all-thread dump

Để học khác biệt **phạm vi API** một cách an toàn, chương trình sau tạo **hai platform threads** độc lập. Cả hai chờ trên `CountDownLatch`. Main thread:

1. Chờ cả hai worker khởi động.
2. Hỏi thông tin stack của **chỉ target-worker**.
3. Hỏi một **thread dump** của tất cả live platform threads.
4. Kiểm tra các kết quả một cách không phụ thuộc thời gian chính xác.
5. Mở latch và `join()` để không bỏ lại worker.
6. Kiểm tra worker đã dừng.

**Cảnh báo:** Kết quả nhìn từ Java API **không đủ** để kết luận HotSpot đã dùng handshake hay safepoint. Phần sau sẽ bật VM logging để kiểm chứng implementation thực tế.

Tạo file **`ThreadHandshakeImpactDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public final class ThreadHandshakeImpactDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        Runnable waitingTask = () -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        };

        Thread target = Thread.ofPlatform().name("target-worker").start(waitingTask);
        Thread other = Thread.ofPlatform().name("other-worker").start(waitingTask);
        try {
            ready.await();

            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            ThreadInfo one = bean.getThreadInfo(target.threadId(), 12);
            if (one == null) throw new AssertionError("Target vanished unexpectedly");

            System.out.println("targetPresent=" + (one != null));
            System.out.println("targetNameCorrect=" +
                    "target-worker".equals(one.getThreadName()));
            System.out.println("targetStackPresent=" +
                    (one.getStackTrace().length > 0));

            ThreadInfo[] all = bean.dumpAllThreads(false, false);
            boolean containsTarget = Arrays.stream(all).anyMatch(
                    t -> t != null && t.getThreadId() == target.threadId());
            boolean containsOther = Arrays.stream(all).anyMatch(
                    t -> t != null && t.getThreadId() == other.threadId());

            System.out.println("allContainsTarget=" + containsTarget);
            System.out.println("allContainsOther=" + containsOther);
            System.out.println("targetAndOtherDifferentIds=" +
                    (target.threadId() != other.threadId()));
            System.out.println("stackDepthLimited=" +
                    (one.getStackTrace().length <= 12));
        } finally {
            release.countDown();
            target.join();
            other.join();
        }

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        System.out.println("targetGoneAfterJoin=" +
                (bean.getThreadInfo(target.threadId(), 4) == null));
        System.out.println("workersStopped=" +
                (!target.isAlive() && !other.isAlive()));
    }
}
```

### Vì sao code này dùng Java 21+ thay vì chỉ Java 10?

**Thread-local handshake xuất hiện trong HotSpot ở Java 10**, nhưng là hạ tầng **nội bộ**. Ví dụ dùng các API Java hiện đại:

- `Thread.ofPlatform()` để chỉ rõ worker là **platform thread**.
- `Thread.threadId()` thay cho cách truy xuất ID thread cũ đã có replacement.
- `ThreadMXBean` để minh họa request chẩn đoán có scope từng thread và nhiều thread.

`Thread.ofPlatform()` được chuẩn hóa với virtual threads ở Java 21; đó là lý do demo dùng `--release 21`. Chương trình **không gọi một internal handshake API** và **không yêu cầu máy cài Java 10**. Cách viết này đáp ứng yêu cầu chỉ sử dụng kiến thức còn áp dụng hiện nay.

### Biên dịch và chạy

```bash
javac --release 21 ThreadHandshakeImpactDemo.java
java ThreadHandshakeImpactDemo
```

**Stdout đã được biên dịch và chạy kiểm chứng trên Zulu OpenJDK 24.0.2:**

```text
targetPresent=true
targetNameCorrect=true
targetStackPresent=true
allContainsTarget=true
allContainsOther=true
targetAndOtherDifferentIds=true
stackDepthLimited=true
targetGoneAfterJoin=true
workersStopped=true
```

Giải thích:

- `targetPresent=true`: target vẫn sống khi đọc thông tin.
- `targetNameCorrect=true`: kết quả là thông tin của đúng platform thread.
- `targetStackPresent=true`: lấy được một số stack frames.
- `allContainsTarget/Other=true`: dump all live platform threads bao gồm hai worker.
- `targetAndOtherDifferentIds=true`: hai worker có thread IDs khác nhau.
- `stackDepthLimited=true`: yêu cầu tối đa 12 frames đã được tôn trọng.
- `targetGoneAfterJoin=true`: sau khi worker kết thúc, truy vấn ID không còn live trả null theo hợp đồng.
- `workersStopped=true`: không bỏ lại thread background.

Không có output số nano/millisecond cố định, vì sampling/pauses phụ thuộc hệ thống.

## 11. Bật HotSpot logging để thấy điểm khác nhau giữa mục tiêu và thực thi

Trên HotSpot hỗ trợ **Unified Logging**, có thể chạy:

```bash
java -Xlog:safepoint=info -cp . ThreadHandshakeImpactDemo
```

Với runtime hỗ trợ tag `handshake`, có thể thử:

```bash
java -Xlog:handshake=debug,safepoint=info -cp . ThreadHandshakeImpactDemo
```

**Không coi các tag/mức log là một public Java SE API ổn định tuyệt đối giữa mọi JVM**. Chúng thuộc HotSpot implementation. Kiểm tra tag được build đang dùng hỗ trợ:

```bash
java -Xlog:help
```

Và kiểm tra phiên bản JVM:

```bash
java --version
```

### Kết quả thực nghiệm: vẫn có safepoint

Với Zulu OpenJDK 24.0.2, output log cho chương trình trên chứa các dòng dạng:

```text
[info][safepoint] Safepoint "ThreadDump", ...
                   Reaching safepoint: 6000 ns, ...
                   Total: 50500 ns

[info][safepoint] Safepoint "ThreadDump", ...
                   Reaching safepoint: 3700 ns, ...
                   Total: 60300 ns

[info][safepoint] Safepoint "ThreadDump", ...
                   Reaching safepoint: 4900 ns, ...
                   Total: 12100 ns
```

Đây là **trích đoạn đã lược bỏ timestamp** để dễ đọc. Ba dòng event được ghi nhận trong một lần chạy tương ứng các truy vấn `getThreadInfo(...)`, `dumpAllThreads(...)` và truy vấn sau khi worker kết thúc. Các con số chính xác **không phải kết quả được bảo đảm** trên những JDK hoặc workload khác.

**Kết luận đúng từ phép đo:**

1. Đã có những VM operations được log dưới tên **`ThreadDump`**.
2. Chúng xuất hiện dưới tag **`safepoint`**, nên không thể dùng demo này để khẳng định lời gọi quản trị đã tránh global safepoint.
3. Dù ứng dụng hỏi stack **chỉ một thread**, việc triển khai Java management API vẫn có thể chọn đường VM operation với safepoint.
4. JEP 312 nói về **khả năng cho operation thích hợp**, không nói mọi lời gọi `ThreadMXBean` chắc chắn dùng handshake.

**Kết luận không được phép từ phép đo:**

- “Thread-local handshakes không có tác dụng.”
- “Mọi JDK đều dùng global safepoint cho mọi `getThreadInfo()`.”
- “JDK mới không sử dụng handshake.”
- “Chỉ có ba global safepoint trong mọi lần chạy app.”
- “Một lần log nhỏ đã đo được mức cải thiện p99 production.”

Trong log `-Xlog:handshake=debug` của một run cụ thể có thể **không có dòng handshake nào** nếu code đang chạy không kích hoạt operation tương ứng ở mức logging đã chọn. Không thấy log handshake **không chứng minh** JVM thiếu hạ tầng đó.

## 12. Đọc log đúng cách: handshake và safepoint có thể cùng tồn tại

Một JVM hiện đại có thể vừa có cơ chế thread-local handshake, vừa dùng global safepoint trong những operation khác. Vì thế log:

```text
[info][safepoint] Safepoint "ThreadDump"
```

không mâu thuẫn với việc HotSpot hỗ trợ JEP 312.

### Cách tiếp cận chẩn đoán

1. Xác định **JDK vendor, feature/update/build** và chế độ chạy.
2. Kiểm tra `java -Xlog:help` để biết những tag/log levels được build hỗ trợ.
3. Bật log với mức phù hợp trong môi trường được kiểm soát.
4. Tạo thao tác cần khảo sát.
5. Xem có **safepoint** liên quan thời điểm thao tác không; nếu có, chú ý **reaching**, **at**, **leaving** và **total**.
6. Nếu có handshake events, xem phạm vi/tần suất và loại operation khi log thể hiện rõ.
7. Không suy kết quả từ một vài dòng bị lọc thiếu ngữ cảnh.
8. Đối chiếu với event GC, JFR, CPU scheduling và thời gian response.

### Có thể kết luận “không có global safepoint” chỉ từ một khoảng log trống không?

Không chắc. Việc không thấy dòng log có thể do:

- Tag/level chưa đủ.
- File log bị rotation hoặc không được thu đúng cách.
- Event xảy ra ngoài khoảng quan sát.
- Công cụ có internal implementation path khác.
- JVM đang chạy không phải tiến trình bạn tưởng.
- Operation hoàn thành quá nhanh hoặc không phát sinh theo điều kiện test.

Để đánh giá một API cụ thể có cần global safepoint không, kết hợp **tài liệu/implementation của đúng JDK** và đo lường có kiểm soát. Đừng dùng sự vắng mặt của một dòng log làm chứng cứ tuyệt đối.

## 13. Vì sao cần kiểm soát chi phí của profiling và thread dump?

Handshakes hướng tới giảm một số tác động toàn JVM, nhưng **management operations vẫn có overhead**.

Ví dụ:

- Lấy stack trace sâu đòi hỏi đọc/ghi lại các frames.
- Lấy all-thread dump tạo dữ liệu tỷ lệ với số platform threads và độ sâu stack.
- Truy vấn monitor/synchronizer ownership có thể tốn thêm công việc.
- Profiler sampling dày có thể tiêu tốn CPU và gây lock/VM contention.
- Việc ghi log rất nhiều dữ liệu có chi phí I/O và allocation của chính công cụ.
- Kích hoạt một số chế độ monitoring có thể thêm overhead theo dõi xuyên suốt vòng đời ứng dụng.

### Scope nhỏ hơn chưa chắc overhead tỷ lệ nhỏ hơn

Một truy vấn nhắm một thread **thường trả ít dữ liệu hơn** dump cả JVM, nhưng không có công thức đơn giản bảo đảm nó giảm pause theo cùng tỷ lệ. Chi phí synchronization có thể nằm ở một VM operation toàn cục, phần thu thập thông tin, hoặc formatting dữ liệu đầu ra.

Thay vì kết luận “giảm từ 100 thread xuống 1 thread là 100 lần nhanh hơn”, hãy đo:

- Thời gian của một lần gọi API.
- GC/safepoint pauses xảy ra gần thời điểm đó.
- Overhead CPU của profiler/JMX.
- Tổng số thread đang hoạt động.
- Request latency p95/p99/p99.9.
- Tốc độ sampling và tỷ lệ dữ liệu bị drop.

**Nguyên tắc:** Thu thập **đủ** thông tin để chẩn đoán, không bật mức sâu nhất với tần suất cao nhất nếu chưa có mục tiêu rõ ràng.

## 14. Cần phân biệt “bớt Stop-The-World” với “bảo đảm độ trễ”

Giả sử một hệ thống trước đây có một VM operation cần global safepoint chỉ để xử lý A. Nếu một implementation mới có thể dùng handshake chỉ với A, request B độc lập có cơ hội tiếp tục chạy thay vì bị chặn **vì riêng operation đó**.

Nhưng có nhiều nguồn trễ khác:

- GC stop-the-world phases.
- Thread scheduling và CPU throttling.
- Lock contention và blocking I/O.
- Allocation pressure, deoptimization, class loading.
- Native calls kéo dài.
- JVM compilation hoặc profiling overhead.
- Network, database và hạ tầng.

Do đó:

```text
Ít global safepoint vì một số operation
        ≠
Toàn bộ application không còn STW
        ≠
Mọi API quản trị non-blocking
        ≠
p99 latency được bảo đảm dưới X ms
```

Một lần handshake cũng có thể phải **đợi target** và tạm dừng target trong một khoảng. Lợi ích cần nhìn cả **độ dài** lẫn **số thread bị tác động**, chứ không chỉ đếm các loại event.

## 15. Virtual threads trong Java 21+: đừng nhầm phạm vi thread

Java hiện đại có **virtual threads**, là abstraction được JVM quản lý và có thể mount/unmount trên platform carrier threads. Điều này khiến từ “thread” có nhiều lớp nghĩa hơn so với mã ứng dụng chỉ dùng platform threads.

### Những điểm cần giữ rõ

1. Hạ tầng HotSpot handshake xử lý những trạng thái thread nội bộ và các platform/JavaThreads phù hợp; **không tự suy** mỗi virtual thread là một platform JavaThread độc lập.
2. `ThreadMXBean` trong JDK hiện hành tập trung vào **platform threads**, không gồm tất cả virtual threads trong `dumpAllThreads`.
3. Một JVM có hàng trăm nghìn virtual threads không đồng nghĩa một thao tác global safepoint phải dừng hàng trăm nghìn platform carrier threads theo cùng mô hình “mỗi request một OS thread”.
4. Trạng thái stack của virtual thread có thể đang mounted hoặc unmounted, ảnh hưởng cách công cụ quan sát nó.
5. Đừng dùng số lượng `ThreadMXBean.getThreadCount()` như tổng số virtual + platform threads.
6. Muốn quan sát virtual threads, kiểm tra những công cụ/JFR thread dump capabilities phù hợp phiên bản Java, thay vì áp phương pháp thread management của Java 10 một cách máy móc.

Bài demo chọn `Thread.ofPlatform()` nhằm loại bỏ nhập nhằng. Trong ứng dụng Java 21+ thực tế, cần xác định công cụ giám sát đang thu thập **platform threads**, **virtual threads** hay cả hai.

## 16. Nếu đang điều tra p99 tăng sau khi bật monitoring

Một quy trình điều tra hiệu quả:

### Bước 1 — ghi lại bối cảnh

- JDK vendor, feature/update/build.
- OS, container CPU quota, memory limit.
- Số platform và virtual threads theo công cụ thích hợp.
- Tốc độ request, allocation, GC, CPU/lock contention.

### Bước 2 — xác nhận hoạt động quản trị

- JMX polling interval.
- Profiler sampling interval và stack depth.
- Thread dumps, heap dumps, JFR recordings.
- Attach tools/diagnostic commands có chạy định kỳ không.

### Bước 3 — ghi thời gian

Dùng timestamps của GC/safepoint/JFR events kết hợp request traces. Cùng một thời điểm chậm chưa đủ để khẳng định nguyên nhân, nhưng giúp khoanh vùng kiểm chứng.

### Bước 4 — đo tác động ở tải đại diện

So sánh:

- **Monitoring off**.
- **Monitoring on, tần suất hiện tại**.
- **Monitoring on, tần suất/stack depth giảm**.

Giữ JDK, CPU quota, workload, heap và dependency tương tự. Đo p99/p99.9 và CPU overhead trên nhiều lần chạy.

### Bước 5 — chọn giải pháp cụ thể

Nếu nguyên nhân thực sự là thao tác quản trị có chi phí cao:

- Giảm tần suất polling hoặc stack capture.
- Giới hạn phạm vi và độ sâu thu thập.
- Sử dụng cấu hình JFR phù hợp mục tiêu điều tra khi khả thi.
- Nâng lên JDK/vendor build được hỗ trợ, có implementation và cải tiến chẩn đoán thích hợp.
- Tham khảo hướng dẫn của profiler vendor và áp dụng giảm overhead đã được kiểm chứng.

**Không sửa JVM internals hoặc ép một private handshake API bằng reflection** để “tự xử lý” vấn đề: đó là cách làm không ổn định, khó tương thích và có thể ảnh hưởng an toàn VM.

## 17. Những giới hạn của một phép benchmark handshakes

Khó thiết kế một benchmark public Java thuần túy để so sánh trực tiếp:

```text
Một operation HotSpot dùng handshake
vs
Cùng operation HotSpot bắt buộc global safepoint
```

vì application Java **không có API chuẩn** để ra lệnh HotSpot thực hiện cùng một internal operation bằng hai mode handshake/safepoint tùy ý. Hơn nữa, các cờ nội bộ từng có trong giai đoạn phát triển JEP không phải interface ổn định để dùng ở JDK hiện đại.

Đo hai lời gọi khác nhau như `getThreadInfo` và `dumpAllThreads` **không thể quy toàn bộ chênh lệch** cho handshake vì phạm vi dữ liệu và đường triển khai đã khác nhau.

### Thiết kế kết quả có trách nhiệm

Nếu bạn khảo sát tác động của tooling đối với production, ghi rõ:

```text
JDK vendor/build: <thông tin đã đo>
Workload: <mô tả rõ>
Platform thread count: <đo thực>
Virtual thread count: <công cụ hỗ trợ>
Tooling operation: <API/command>
Sampling rate / stack depth: <cấu hình>
Safepoint events and total time: <đo thực>
Handshake logging: <nếu JDK hỗ trợ và có kết quả>
Request p99/p99.9: <đo thực>
CPU/GC/lock metrics: <đo thực>
Conclusion and limitations: <nhận định đúng bằng chứng>
```

Đây là **mẫu báo cáo**, không phải số liệu thực của một ứng dụng cụ thể. Không điền các con số đoán.

### Khi nào có thể nói “giảm ảnh hưởng”?

Chỉ khi so sánh có đối chứng cho thấy:

- Tần suất/chi phí global safepoints giảm trong trường hợp được khảo sát.
- Những thread không liên quan bị gián đoạn ít hơn, hoặc tail latency tốt hơn.
- Không gây overhead CPU/memory/throughput quá lớn ở nơi khác.
- Điều kiện test phù hợp với môi trường vận hành.

JEP 312 giải thích **cơ hội kiến trúc**, còn workload và VM cụ thể quyết định **mức lợi ích thực**.

## 18. Các anti-pattern cần tránh

**Sai lầm 1 — “Java 10 có thread-local handshake nên JVM không còn global safepoint.”**

Sai. GC và các VM operations khác vẫn có thể cần global synchronization.

**Sai lầm 2 — “Gọi `getThreadInfo(id)` chắc chắn là một handshake.”**

Sai. Demo trên Zulu JDK 24.0.2 cho thấy `ThreadDump` global safepoint vẫn được ghi nhận trong phép thử.

**Sai lầm 3 — “Một thread dump nhẹ thì mọi thread chắc chắn không bị ảnh hưởng.”**

Sai. Cost tùy implementation và yêu cầu snapshot; không mặc định zero-pause.

**Sai lầm 4 — “Handshakes là phương thức public của Thread.”**

Sai. Hạ tầng nằm trong HotSpot; không có API Java SE `Thread.handshake(callback)`.

**Sai lầm 5 — “Handshake luôn callback trực tiếp vào target thread như Runnable thường.”**

Sai. HotSpot có cơ chế xử lý an toàn theo trạng thái thread; callback ở đây là VM-level operation, không phải Java business callback.

**Sai lầm 6 — “Handshake không bao giờ phải chờ.”**

Sai. Target cần đạt trạng thái phù hợp và có chi phí coordination.

**Sai lầm 7 — “Giảm global safepoints đồng nghĩa tăng throughput chắc chắn.”**

Sai. Tùy overhead mới, workload và tài nguyên CPU; phải đo.

**Sai lầm 8 — “Đổi TCCL hoặc dùng ThreadLocal<T> là kích hoạt handshake.”**

Sai. Thread context class loader và `ThreadLocal` dữ liệu ứng dụng **không phải** thread-local handshake của HotSpot.

**Sai lầm 9 — “JFR thì chắc chắn mọi event không safepoint.”**

Sai. JFR có nhiều loại event và cơ chế thu thập, overhead khác nhau.

**Sai lầm 10 — “ThreadMXBean thống kê mọi virtual thread.”**

Sai. Trên Java hiện đại, ThreadMXBean theo dõi platform threads.

**Sai lầm 11 — “Safepoint chỉ xảy ra khi GC.”**

Sai. Thread dump, deoptimization, VM housekeeping và những operation khác có thể tạo safepoint.

**Sai lầm 12 — “Chỉ cần thấy một dòng log `handshake` là chứng minh mọi thao tác quản trị đã tránh STW.”**

Sai. Cần xác định operation, thread scope và đối chiếu safepoint log/timing.

**Sai lầm 13 — “Không thấy log safepoint là bằng chứng tuyệt đối không có pause.”**

Sai. Phụ thuộc logging settings và phạm vi đo; có các nguồn latency khác.

**Sai lầm 14 — “Cứ bật profiler sampling tần suất cao là không đáng kể vì có JEP 312.”**

Sai. Profiling, allocation và ghi dữ liệu vẫn có overhead.

**Sai lầm 15 — “Dùng cờ VM handshakes từ tài liệu Java 10 cũ là phương án tối ưu hiện đại.”**

Sai. Không lấy internal/diagnostic flags từ giai đoạn phát triển JEP làm cấu hình production.

**Sai lầm 16 — “JEP 312 yêu cầu thay code ứng dụng bằng handshake.”**

Sai. Nó cải thiện implementation JVM, không bắt người phát triển gọi một API mới.

## 19. Checklist cho lập trình viên và người vận hành

- [ ] Hiểu global safepoint và per-thread handshake giải quyết **hai loại điều kiện phối hợp khác nhau**.
- [ ] Không đánh đồng thread-local handshakes với `ThreadLocal<T>` hoặc scheduling trong Executor.
- [ ] Biết JEP 312 được đưa vào **Java 10**, nhưng là hạ tầng HotSpot nội bộ.
- [ ] Không coi mọi JMX/JVMTI/JFR operation mặc định đã dùng handshakes.
- [ ] Khi test, kiểm tra JDK vendor/build thực tế bằng `java --version`.
- [ ] Xem những logging tags thực tế được hỗ trợ qua `java -Xlog:help`.
- [ ] Có dữ liệu `safepoint` cho workload có vấn đề, không suy từ code API.
- [ ] Khi có `ThreadDump` safepoint, phân tích time to safepoint và at safepoint.
- [ ] Không xem một snapshot stack là phép đo miễn phí hoặc global atomic snapshot mặc định.
- [ ] Phân biệt platform với virtual threads khi phân tích `ThreadMXBean`.
- [ ] Thiết lập sampling rate/stack depth phù hợp khi bật profiling.
- [ ] Không gọi heap/thread dumps liên tục chỉ để thử khả năng chịu tải.
- [ ] Đo cả tần suất pause, tổng thời gian pause, CPU overhead và p99/p99.9.
- [ ] Kiểm soát container CPU quotas và các biến môi trường khi so sánh.
- [ ] Đọc tài liệu chính thức của **đúng JDK** trước khi dùng cờ VM.
- [ ] Không dựa vào những tính năng quản trị/locking đã bị loại bỏ ở JDK mới.
- [ ] Đánh giá tác động thực tế trước khi tuyên bố giảm độ trễ.
- [ ] Không dùng reflection hoặc API HotSpot nội bộ để tự gửi handshake.
- [ ] Khi nâng JDK, chạy lại regression/performance test, không mặc định các internal paths giữ nguyên.

## 20. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** JEP nào đưa Thread-Local Handshakes vào Java 10?

**Đáp án:** **JEP 312 — Thread-Local Handshakes**.

**Câu 2.** Mục tiêu nổi bật của cơ chế này là gì?

**Đáp án:** Cho phép JVM thực hiện một số per-thread operations ở trạng thái an toàn **không cần global safepoint**, qua đó giảm phạm vi gián đoạn và có cơ hội cải thiện latency.

**Câu 3.** Java 10 có public `Thread.handshake(Runnable)` để ứng dụng gọi không?

**Đáp án:** Không. Thread-local handshake thuộc hạ tầng nội bộ HotSpot; không phải một public Java SE callback API.

**Câu 4.** Safepoint và handshake khác gì về phạm vi đồng bộ?

**Đáp án:** Global safepoint phối hợp các Java threads toàn VM phù hợp operation; handshake có thể nhắm một thread hoặc tập thread không cần dừng toàn VM chỉ vì operation đó.

**Câu 5.** Handshake có chắc chắn hoàn thành tức thì không?

**Đáp án:** Không. JVM vẫn phải chờ/truy cập trạng thái an toàn của thread mục tiêu; không có hard deadline được cam kết.

**Câu 6.** Có phải từ Java 10 toàn bộ garbage collection không còn STW?

**Đáp án:** Không. Nhiều collector và các pha GC/VM operations vẫn có những lần tạm dừng theo thiết kế.

**Câu 7.** Vì sao một lời gọi `getThreadInfo(id)` không đủ chứng minh JVM đã dùng handshake?

**Đáp án:** API chỉ mô tả dữ liệu được trả, không cam kết cách HotSpot phối hợp internals; trong ví dụ chạy trên JDK 24.0.2, JVM vẫn ghi `ThreadDump` safepoint.

**Câu 8.** `dumpAllThreads(false,false)` của ThreadMXBean có thể bao gồm mọi virtual thread không?

**Đáp án:** Không. ThreadMXBean tập trung vào **platform threads**, không bao quát tất cả virtual threads hiện đại.

**Câu 9.** Khi muốn biết một thao tác có tạo safepoint không, nên dùng gì?

**Đáp án:** Kiểm tra `-Xlog:safepoint=info` (hoặc mức phù hợp), đọc `java -Xlog:help` và phân tích log trên đúng runtime/workload.

**Câu 10.** Chỉ thấy log `handshake` có bảo đảm mọi JVM operation đều không dừng ứng dụng không?

**Đáp án:** Không. Handshake và global safepoint có thể cùng tồn tại; phải xác định operation cụ thể.

**Câu 11.** Có cần sửa Java business code để dùng JEP 312 không?

**Đáp án:** Không. Đây là thay đổi infrastructure JVM. Ứng dụng chỉ hưởng lợi nếu đường VM/tooling thực tế có sử dụng khả năng này.

**Câu 12.** Một công cụ sampling 1.000 lần/giây có thể tạo overhead dù HotSpot hỗ trợ handshakes không?

**Đáp án:** Có. Stack walking, event recording, allocation và CPU cost vẫn tồn tại; cần chọn sampling rate phù hợp.

**Câu 13.** Vì sao p99 có thể tăng dù average response time gần như không đổi?

**Đáp án:** Các khoảng dừng hoặc event chi phí cao có thể tác động một số yêu cầu rất chậm, ảnh hưởng đuôi phân bố nhiều hơn trung bình.

**Câu 14.** Đổi `ThreadLocal<T>` trong code có giúp giảm global safepoint trực tiếp không?

**Đáp án:** Không. ThreadLocal lưu dữ liệu ứng dụng theo thread; nó không điều khiển cơ chế handshake VM.

**Câu 15.** Cơ chế handshakes có cho phép bỏ bytecode verification hoặc memory safety để lấy hiệu năng không?

**Đáp án:** Không. Các operation vẫn phải thỏa điều kiện an toàn của JVM và giữ nguyên ngữ nghĩa Java.

**Câu 16.** Nếu log thử nghiệm trên JDK A cho thấy safepoint, có kết luận JDK B sẽ luôn giống vậy không?

**Đáp án:** Không. HotSpot paths có thể thay đổi; cần kiểm chứng runtime cụ thể.

**Câu 17.** Vì sao một thao tác cần snapshot nhất quán toàn VM không thể mặc định thay bằng handshake một thread?

**Đáp án:** Một thread đơn lẻ không cung cấp sự nhất quán toàn cục cần thiết; thuật toán/VM operation phải được thiết kế phù hợp.

**Câu 18.** Những dữ liệu nào giúp đánh giá “giảm ảnh hưởng của thao tác quản trị JVM”?

**Đáp án:** Safepoint/handshake logs, chi phí API, profiling CPU, số lượng thread, tần suất thao tác, p99/p99.9 request latency và điều kiện workload.

## 21. Tài liệu chính thức hiện hành và liên quan

1. [OpenJDK — JEP 312: Thread-Local Handshakes](https://openjdk.org/jeps/312): mục tiêu và hạ tầng per-thread operations từ Java 10.
2. [OpenJDK — JEP 376: ZGC — Concurrent Thread-Stack Processing](https://openjdk.org/jeps/376): ví dụ hướng phát triển xử lý thread stacks theo cách concurrent trong JDK sau.
3. [Java SE 25 — ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): getThreadInfo, dumpAllThreads, giới hạn với virtual threads và lưu ý về chi phí.
4. [Java SE 25 — ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html): thông tin snapshot của platform threads.
5. [Java SE 25 — Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `Thread.ofPlatform()`, `threadId()`, và phân biệt platform/virtual thread.
6. [Java SE 25 — The java Command / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog:help`, `-Xlog:safepoint=info` và các tag HotSpot hiện hành.
7. [OpenJDK — Current HotSpot handshake.cpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.cpp): mã nguồn để hiểu cơ chế xử lý handshake theo implementation hiện tại; **không** phải public Java API.
8. [Oracle Inside Java — The Arrival of Java 16](https://inside.java/2021/03/16/the-arrival-of-java16/): bối cảnh JEP 376 và xử lý stack concurrent.
9. [OpenJDK — JVM Tool Interface Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): giới hạn/khả năng các JVMTI operations của tooling.

**Kết luận:** JEP 312 (Java 10) bổ sung **Thread-Local Handshakes** để một số thao tác nội bộ JVM có thể chỉ phối hợp với thread mục tiêu, **không cần buộc toàn JVM vào global safepoint**. Mục tiêu là giảm phạm vi ảnh hưởng và độ trễ do những thao tác có thể xử lý cục bộ. Tuy nhiên, đây là **khả năng hạ tầng của HotSpot**, không phải lời hứa rằng mọi ThreadMXBean/JVMTI/JFR/GC operation đều tránh STW. Đánh giá đúng phải kết hợp kiến thức JEP với **GC/safepoint/handshake logs và số liệu latency trên JDK đang chạy**, thay vì suy diễn từ tên API.
