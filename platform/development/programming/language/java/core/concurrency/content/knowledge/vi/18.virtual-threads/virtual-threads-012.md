# Chẩn đoán Virtual Threads bằng thread dump và Java Flight Recorder (JFR)

Virtual Threads là luồng nhẹ do Java runtime quản lý, được chuẩn hóa trong **Java 21** (JEP 444). Chúng giúp mô hình *mỗi tác vụ có một thread* mở rộng tốt khi tác vụ thường xuyên chờ I/O. Tuy nhiên, “có rất nhiều virtual thread” không tự chứng minh ứng dụng hoạt động hiệu quả: các tác vụ vẫn có thể nghẽn vì tài nguyên hữu hạn, khóa, vòng chờ, CPU, hệ thống bên ngoài hoặc những đoạn thực thi khiến virtual thread không nhường được carrier.

Bài này hướng dẫn **chẩn đoán hoạt động của Virtual Threads trong Java nói chung** bằng hai công cụ sẵn có trong JDK:

- **Thread dump:** ảnh chụp các stack đang tồn tại tại một thời điểm, để trả lời “thread đang ở đâu, chờ gì, stack nào lặp lại?”.
- **Java Flight Recorder (JFR):** chuỗi sự kiện và số đo theo thời gian, để trả lời “bất thường xuất hiện khi nào, kéo dài bao lâu, tần suất thế nào, có pinning hay tranh chấp tài nguyên không?”.

Hai công cụ bổ sung cho nhau. Một dump đơn lẻ thường không đủ để kết luận về nguyên nhân hiệu năng; một JFR không được bật đúng event hoặc không thu đúng thời điểm cũng có thể bỏ lỡ dữ kiện.

## 1. Mô hình cần hiểu trước khi đọc dấu vết

**Virtual thread** là một đối tượng `Thread` thật trong API Java: có tên, stack, trạng thái, khả năng interrupt và stack trace. Khác platform thread gắn sát với OS thread, virtual thread được JVM **mount** lên một platform thread gọi là **carrier** khi cần chạy. Khi gặp thao tác chờ mà JVM hỗ trợ unmount, virtual thread có thể rời carrier và nhường carrier để chạy virtual thread khác.

Ví dụ, một virtual thread đang ở `CountDownLatch.await()` hoặc chờ network I/O không nhất thiết chiếm một OS thread suốt thời gian chờ. Điều này không có nghĩa việc chờ là miễn phí: hàng chục nghìn tác vụ cùng đợi một connection pool nhỏ vẫn gây độ trễ và backlog.

Phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa khi chẩn đoán |
|---|---|
| *Waiting/parked* | Thread chờ điều kiện hoặc kết quả; có thể là hành vi bình thường, cần nhìn stack và thời gian |
| *Blocked on monitor/lock* | Thread chưa giành được khóa; đo cạnh tranh khóa và xác định vùng khóa dài |
| *Carrier pinning* | Virtual thread gặp tình huống không thể unmount, khiến carrier bị giữ trong một khoảng thời gian |
| *Starvation / saturation* | Tác vụ không được tiến triển kịp vì CPU, scheduler hoặc một tài nguyên hữu hạn; cần chứng cứ vượt ra ngoài tên trạng thái thread |

**Một thread ở trạng thái `WAITING` không mặc nhiên là deadlock**, và một virtual thread `RUNNABLE` không mặc nhiên đang dùng CPU. Trạng thái là ảnh chụp JVM-level, phải gắn với stack, số liệu thời gian và tốc độ xử lý thực tế.

### Khác biệt theo phiên bản JDK: đặc biệt quan trọng với pinning

- **Java 21–23:** chờ hoặc blocking trong vùng `synchronized` có thể giữ virtual thread trên carrier. Vì vậy một thao tác I/O lâu trong monitor là nghi vấn pinning có giá trị.
- **Từ Java 24 (JEP 491):** JVM cải thiện `synchronized` để virtual thread có thể unmount trong các tình huống trước kia gây pinning vì monitor. Không kết luận “có synchronized ⇒ pinning” khi dùng JDK 24+.
- **Các phiên bản mới vẫn có trường hợp pinning khác**, điển hình có native/foreign call hoặc VM frame không thể nhường carrier. Phải dựa vào JFR và stack trên **đúng JDK đang chạy**.

Pinning kéo dài có thể hạn chế khả năng mở rộng, nhưng không đồng nghĩa chương trình sai về mặt chức năng. Một sự kiện ngắn, hiếm gặp có thể không phải vấn đề ưu tiên.

## 2. Khi nào dùng thread dump, khi nào dùng JFR?

| Câu hỏi | Thread dump | JFR |
|---|---|---|
| Những stack nào đang đợi tại thời điểm này? | Rất phù hợp | Có thể hỗ trợ qua event/stack sampling |
| Nhiều virtual thread đang chờ cùng semaphore, latch, I/O? | Tốt để tìm stack tương tự | Tốt để kiểm tra diễn biến và thời lượng |
| Vấn đề chỉ xảy ra trong vài giây rồi biến mất? | Dễ bỏ lỡ | Phù hợp nếu ghi đúng thời điểm |
| Pinning kéo dài hoặc lặp lại có thật không? | Chỉ gợi ý | Event `jdk.VirtualThreadPinned` là chứng cứ trực tiếp hơn |
| CPU cao, allocation, GC hoặc lock contention kéo dài? | Một phần | JFR có sự kiện/sampling tương ứng |
| Kết luận “bị deadlock”? | Cần nhiều mẫu và thông tin lock; dump mới có thể thiếu một phần | Cần tương quan thêm dữ liệu về khóa và tiến triển |

**Quy trình thường dùng:** xác định triệu chứng và thời điểm → chụp nhiều dump có khoảng cách → ghi JFR trong khoảng có tải → đối chiếu stack/event/tài nguyên → kiểm chứng giả thuyết bằng sửa đổi hoặc phép đo lặp lại.

## 3. Chuẩn bị môi trường và nhận diện JVM đúng

Yêu cầu tối thiểu:

- **JDK 21+** để có Virtual Threads bản chính thức; JDK được dùng để chạy và bộ công cụ `jcmd`/`jfr` nên tương thích với JVM đích.
- Quyền phù hợp để attach vào tiến trình Java. Trong container, cần chạy lệnh ở môi trường thấy được tiến trình JVM và có quyền attach tương ứng.
- Có đủ dung lượng cho file dump/JFR; với hàng trăm nghìn virtual thread, thread dump có thể lớn. Thu thập có kiểm soát thay vì lặp liên tục không giới hạn.

Liệt kê tiến trình mà `jcmd` nhìn thấy:

```bash
jcmd -l
```

Chọn **PID của đúng JVM ứng dụng**, sau đó kiểm tra các chẩn đoán mà JVM đó hỗ trợ:

```bash
jcmd <PID> help
jcmd <PID> help Thread.dump_to_file
jcmd <PID> help JFR.start
```

Trong các lệnh ở bài này, `<PID>` là ký hiệu thay thế bằng **số PID thực tế**, không nhập cả dấu ngoặc nhọn. Cú pháp tham số và thông tin được ghi có thể được cải thiện giữa các phiên bản JDK, vì vậy `jcmd <PID> help ...` là nguồn kiểm chứng trực tiếp cho JVM đang chạy.

## 4. Lấy thread dump có Virtual Threads

Dùng lệnh `Thread.dump_to_file`, được thiết kế để quan sát cả virtual threads:

```bash
jcmd <PID> Thread.dump_to_file vt-dump.txt
jcmd <PID> Thread.dump_to_file -format=json vt-dump.json
```

- Không chỉ định định dạng sẽ dùng kiểu văn bản mặc định của JDK đang chạy.
- `-format=json` phù hợp khi muốn phân tích bằng công cụ. Hình dạng/kiểu dữ liệu JSON có thể khác giữa các đời JDK; đừng xây parser dựa trên một ví dụ định dạng cố định.
- Đường dẫn file được hiểu **trong môi trường của tiến trình JVM đích**. Dùng đường dẫn tuyệt đối khi làm việc qua container, service hoặc các thư mục chạy khác nhau để tránh nhầm nơi lưu.
- Nên lưu **2–3 dump cách nhau vài giây** khi điều tra vấn đề kéo dài, rồi so sánh các stack tương tự. Mẫu lặp lại có giá trị hơn một ảnh chụp riêng lẻ.

Có thể dùng:

```bash
jcmd <PID> Thread.print -l
```

như một nguồn bổ sung cho thông tin platform threads và lock, nhưng **không dùng riêng `Thread.print` để kết luận về tất cả virtual threads**. Virtual threads đang unmount có thể không hiện đầy đủ ở dạng dump truyền thống; mức độ thông tin về lock/monitor trong `Thread.dump_to_file` cũng phụ thuộc phiên bản JDK (đặc biệt các bản cũ).

### Đọc gì trong dump?

Theo thứ tự ưu tiên:

1. **Tên thread/stack phổ biến:** tìm các virtual threads cùng chờ tại một `CountDownLatch.await`, `Semaphore.acquire`, thao tác socket, `Future.get` hoặc `LockSupport.park`. Một stack trùng lặp với số lượng lớn có thể là nơi backlog tích tụ.
2. **Điểm chờ thật:** xem cả những frame ở phía trên (nơi đang đợi) lẫn frame ứng dụng ở dưới (tại sao tác vụ tới đây). Nên phân biệt thư viện runtime với chỗ gọi của ứng dụng.
3. **Sự thay đổi giữa các lần chụp:** nhiều thread cùng đứng nguyên tại một điểm trong các dump liên tiếp là tín hiệu nên tìm hiểu kỹ, nhưng vẫn chưa chứng minh deadlock.
4. **Carrier và platform threads:** nếu carrier bận CPU/blocked quá lâu, ghép với JFR để tìm điều gì giữ nó. Không nhầm tên carrier với danh tính công việc logic của virtual thread.
5. **Tài nguyên phụ thuộc:** nếu nhiều virtual threads đợi `Semaphore` hay pool, kiểm tra giới hạn pool, số tác vụ đang chạy, thời gian chờ và tốc độ giải phóng tài nguyên.

**Không có một “con số virtual threads tối đa tốt” chung cho mọi ứng dụng.** Cần xem throughput, p95/p99 latency, số request đang chờ, mức dùng CPU, số connection hữu hạn và tần suất timeout.

## 5. Bài thực hành Java 21+: tạo những virtual threads dễ quan sát

Lưu thành **`VirtualThreadDiagnosticsDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualThreadDiagnosticsDemo {
    public static void main(String[] args) throws InterruptedException {
        int count = 3;
        CountDownLatch allWaiting = new CountDownLatch(count);
        CountDownLatch release = new CountDownLatch(1);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < count; i++) {
                final int id = i;
                executor.submit(() -> {
                    Thread.currentThread().setName("diag-vt-" + id);
                    allWaiting.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            allWaiting.await();
            System.out.println("Virtual threads waiting: " + count);
            System.out.println("PID: " + ProcessHandle.current().pid());

            try {
                // Giữ tiến trình sống để thu thread dump và JFR từ cửa sổ khác.
                Thread.sleep(60_000);
            } finally {
                release.countDown();
            }
        }

        System.out.println("Finished");
    }
}
```

Biên dịch và chạy trong một terminal:

```bash
javac VirtualThreadDiagnosticsDemo.java
java VirtualThreadDiagnosticsDemo
```

**Ví dụ cấu trúc stdout** (PID khác nhau mỗi lần chạy):

```text
Virtual threads waiting: 3
PID: <PID-thuc-te>
Finished
```

Dòng `Finished` chỉ được in **sau khoảng 60 giây**, khi chương trình đã giải phóng `CountDownLatch` và các tác vụ hoàn tất. Từ một terminal khác, **trong khi chương trình đang ngủ**, thay PID vừa in vào:

```bash
jcmd <PID> Thread.dump_to_file -format=json vt-lab.json
jcmd <PID> Thread.dump_to_file vt-lab.txt
```

Mở file và tìm tên `diag-vt-0`, `diag-vt-1`, `diag-vt-2` cùng stack chờ `CountDownLatch.await` (các frame nội bộ khác có thể phụ thuộc JDK). Ba virtual threads này đang chờ một tín hiệu có chủ đích: **đây không phải deadlock hay pinning**.

Ví dụ sử dụng `Executors.newVirtualThreadPerTaskExecutor()`, **không tạo pool cố định các virtual threads**: executor cấp một virtual thread cho mỗi tác vụ. Việc giới hạn số tác vụ đang chạy phải được thực hiện theo nhu cầu tài nguyên thực (ví dụ semaphore cho kết nối hoặc dịch vụ ngoại vi), không phải bằng cách thay virtual threads thành một pool nhỏ cố định để che giấu số tác vụ tồn đọng.

### Nếu không tìm thấy thread trong dump

Kiểm tra trước tiên:

- Có chụp **trước khi chương trình kết thúc** không? Tác vụ đã xong thì thread sẽ biến mất.
- Có dùng đúng PID, đúng JVM và đúng file output không?
- Có dùng `Thread.dump_to_file` hay chỉ `Thread.print`?
- Có tìm theo tên thread và stack thay vì chỉ tìm trạng thái `RUNNABLE`/`WAITING` không?
- Dung lượng dump có bị công cụ đọc cắt ngắn không? Dùng công cụ mở file toàn vẹn hoặc trình phân tích phù hợp.

## 6. Thu Java Flight Recorder ngay trên JVM đang chạy

JFR là bộ ghi sự kiện/sampling tích hợp vào HotSpot/JDK, có thể thu thông tin về scheduling, blocking, CPU, allocation, GC, monitor contention và sự kiện riêng của virtual threads. JFR thường có overhead thấp khi dùng cấu hình phù hợp, nhưng **không phải mọi event đều bật sẵn**, và recording quá dài hoặc quá chi tiết có thể tiêu tốn tài nguyên.

Trong khoảng 60 giây mà chương trình demo đang sống, có thể chạy:

```bash
jcmd <PID> JFR.start name=vt-diagnostics settings=profile duration=20s filename=vt-diagnostics.jfr
jcmd <PID> JFR.check
```

Sau khi recording đủ thời lượng và file xuất hiện, xem tổng quan và event:

```bash
jfr summary vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

Nếu ghi một recording **không có thời hạn**, cần kiểm soát vòng đời của nó, chẳng hạn:

```bash
jcmd <PID> JFR.start name=vt-manual settings=default
jcmd <PID> JFR.dump name=vt-manual filename=vt-manual.jfr
jcmd <PID> JFR.stop name=vt-manual
```

Lệnh `JFR.dump` sao chép dữ liệu tại thời điểm yêu cầu; `JFR.stop` kết thúc recording. Nếu dùng `duration=20s` thì recording tự dừng theo thời lượng đã chỉ định. Với `JFR.start`, file `filename` được tạo bởi tiến trình JVM đích; nên dùng đường dẫn tuyệt đối để tránh nhầm working directory. Lệnh `jfr summary`/`jfr print` thực hiện trên máy có file JFR và công cụ JDK tương thích.

**Đừng chờ đợi demo ở mục 5 tự tạo ra `VirtualThreadPinned`.** Nó chỉ chờ `CountDownLatch` đúng cách; file JFR có thể không chứa một event pinning nào, và điều này là kết quả hợp lệ.

### Các event quan trọng cho Virtual Threads

| Event JFR | Khi nào có ích? | Ghi chú |
|---|---|---|
| `jdk.VirtualThreadPinned` | Nghi virtual thread giữ carrier khi blocking | Thường bật mặc định với ngưỡng 20 ms trong cấu hình JFR chuẩn; điều kiện phát sinh thay đổi theo JDK |
| `jdk.VirtualThreadSubmitFailed` | Nghi việc start/unpark virtual thread gặp vấn đề tài nguyên | Thường bật mặc định; cần xem nguyên nhân và thời điểm |
| `jdk.VirtualThreadStart` | Cần biết thời điểm tạo virtual thread, tốc độ khởi tạo | **Tắt mặc định**; bật có chọn lọc khi cần |
| `jdk.VirtualThreadEnd` | Cần biết vòng đời virtual thread, tốc độ hoàn tất | **Tắt mặc định**; bật có chọn lọc khi cần |
| `jdk.JavaMonitorEnter` / `jdk.JavaMonitorWait` | Nghi tranh chấp monitor hoặc thời gian chờ trên monitor | Kiểm tra cấu hình và threshold; không đồng nhất monitor contention với pinning |
| `jdk.ThreadPark` | Nghi các khoảng đợi/park kéo dài | Có thể giúp tìm thao tác chờ; xác minh event và threshold được bật trong recording |

Một lệnh in bốn event riêng của Virtual Threads (chỉ có kết quả khi các event đã thực sự được ghi):

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

Nếu không có `VirtualThreadStart` và `VirtualThreadEnd`, điều đó **không chứng minh không có virtual thread**: hai event này mặc định thường bị tắt. Muốn đo tạo/hủy thread, bật tường minh chúng thông qua JDK Mission Control, file cấu hình JFR tùy chỉnh hoặc API `jdk.jfr.Recording`, đồng thời cân nhắc overhead khi lượng thread rất lớn.

### Cách đọc một event pinning

Khi thấy `jdk.VirtualThreadPinned`, xem:

1. **Start time + duration:** có rơi đúng cửa sổ bị tăng latency không, mỗi lần kéo dài bao lâu?
2. **Stack trace:** frame ứng dụng nào dẫn tới thao tác blocking? Đừng chỉ dừng ở frame VM/`LockSupport`.
3. **Event thread và carrier** (nếu runtime/JFR ghi): xác định virtual thread và carrier liên quan.
4. **Tần suất và tổng ảnh hưởng:** hàng nghìn lần pinning trong hot path khác xa một lần ngắn khi khởi tạo.
5. **Phiên bản JDK:** trên Java 21–23 cần xem blocking nằm trong `synchronized`; trên Java 24+ phải điều tra loại pinning còn tồn tại và chính thông tin stack/event được ghi.

JFR ghi nhận **sự kiện vượt threshold**, không có nghĩa mọi thao tác blocking đều phải xuất hiện. Nếu tần suất sự kiện bằng 0, hãy kiểm tra cấu hình, threshold, thời gian ghi, tính khả dụng của event và phiên bản JVM trước khi loại bỏ giả thuyết.

## 7. Phân biệt chờ bình thường, lock contention, deadlock và pinning

### Tình huống A — Hàng nghìn virtual threads cùng đợi tài nguyên

**Hiện tượng:** latency tăng và thread dump lặp lại `Semaphore.acquire` hoặc vị trí lấy kết nối từ pool.

**Giả thuyết hợp lý:** số tác vụ đồng thời vượt năng lực cấp tài nguyên; thời gian đợi ở semaphore/pool dài hơn thời gian thực thi công việc.

**Cách xác minh:** thu 2–3 dump trong giai đoạn nghẽn; đo số connection đang sử dụng, hàng đợi, timeout và thời gian thực hiện truy vấn/remote I/O; ghi JFR để thấy các khoảng chờ và CPU. Đếm nhiều virtual thread đang `WAITING` chưa đủ kết luận scheduler lỗi hoặc JFR pinning.

**Hướng xử lý:** giới hạn concurrency theo tài nguyên thực, dùng timeout/cancellation rõ ràng, giảm thời gian giữ kết nối hoặc tối ưu hệ thống phụ thuộc. Giảm số carrier không làm tăng số connection thực tế.

### Tình huống B — Pinning trên Java 21–23

**Hiện tượng:** throughput giảm mạnh khi nhiều tác vụ thực hiện blocking I/O bên trong `synchronized`; JFR có nhiều `jdk.VirtualThreadPinned` với stack tương ứng.

**Giả thuyết:** virtual threads bị giữ trên carrier trong thời gian blocking, làm giảm số carrier sẵn sàng chạy tác vụ khác.

**Xử lý có điều kiện:** nếu khóa được dùng chỉ để bảo vệ trạng thái ngắn, hãy tách phần I/O lâu ra khỏi vùng `synchronized` nếu bảo đảm tính đúng đắn; hoặc cân nhắc `ReentrantLock` ở hot path có blocking, luôn dùng `unlock()` trong `finally`. Tránh máy móc đổi **tất cả** `synchronized` thành `ReentrantLock`. Nếu có thể, so sánh sau khi nâng JDK 24+ (JEP 491) vì cơ chế monitor đã thay đổi.

Mẫu minh họa ý tưởng (không phải chương trình độc lập):

```java
// Rủi ro trên JDK 21–23 nếu remoteCall() blocking lâu.
synchronized (guard) {
    remoteCall();
}

// Giải pháp chỉ hợp lệ khi việc gọi remoteCall() không cần giữ monitor:
// kiểm tra lại bất biến dữ liệu trước khi áp dụng.
synchronized (guard) {
    snapshot = buildSnapshot();
}
remoteCallWith(snapshot);
```

Không tách thao tác khỏi monitor khi yêu cầu đồng bộ của dữ liệu thực sự cần bảo vệ xuyên suốt giao dịch đó; tính đúng đắn quan trọng hơn một giả thuyết tối ưu.

### Tình huống C — Deadlock hoặc vòng chờ logic

**Hiện tượng:** nhiều stack giữ nguyên ở `Future.get`, `CountDownLatch.await` hoặc monitor qua các lần chụp; tác vụ không hoàn thành, các tín hiệu giải phóng không bao giờ xảy ra.

**Giả thuyết:** có vòng phụ thuộc, một stage đợi chính kết quả mình phải tạo, hoặc khóa bị giữ bởi tác vụ cũng đang chờ.

**Xác minh:** tái dựng đồ thị **ai đang đợi ai** từ mã và stack; đối chiếu thời điểm submit, complete và timeout; sử dụng thông tin monitor/lock bổ sung nếu có. Không suy luận deadlock chỉ từ một stack `WAITING`; nhiều tác vụ có thể đang chờ hợp lệ một latch chưa được giải phóng.

**Hướng xử lý:** loại bỏ vòng phụ thuộc, thiết kế tín hiệu release trong `finally`, bổ sung deadline và propagation của interrupt/cancellation khi đúng hợp đồng. Virtual Threads làm cho việc chờ rẻ hơn về OS threads, **không tự giải quyết deadlock logic**.

### Tình huống D — CPU cao, không thấy pinning

**Hiện tượng:** CPU gần tối đa, latency tăng; JFR sampling cho thấy nhiều frame tính toán; `VirtualThreadPinned` không nổi bật.

**Giả thuyết:** công việc tính toán thuần CPU đang dùng hết tài nguyên, hoặc GC/allocation tăng. Virtual threads không tạo thêm năng lực CPU và không giúp phép tính CPU-heavy chạy nhanh hơn chỉ nhờ đổi thread.

**Hướng xử lý:** dùng JFR CPU/profile, phân tích hot methods, allocation và GC; tách hoặc giới hạn tác vụ CPU-heavy; đo hiệu quả sau thay đổi.

## 8. Phân tích JFR sâu hơn bằng Java API

Ngoài `jfr summary` và `jfr print`, có thể đọc JFR bằng API `jdk.jfr.consumer.RecordingFile` trên JDK có module `jdk.jfr`. Ví dụ hoàn chỉnh sau đếm số event pinning **đã được ghi trong file**, không đoán số thread hiện hành.

Lưu thành **`CountPinnedEvents.java`**:

```java
import java.io.IOException;
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class CountPinnedEvents {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java CountPinnedEvents <file.jfr>");
            return;
        }

        long total = 0;
        try (RecordingFile recording =
                     new RecordingFile(Path.of(args[0]))) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                if ("jdk.VirtualThreadPinned"
                        .equals(event.getEventType().getName())) {
                    total++;
                }
            }
        }

        System.out.println("Recorded pinned events: " + total);
    }
}
```

Chạy bằng JDK 21+:

```bash
javac CountPinnedEvents.java
java CountPinnedEvents vt-diagnostics.jfr
```

Ví dụ, nếu file không chứa event pinning, stdout là:

```text
Recorded pinned events: 0
```

Con số có thể khác trên file thực tế; nó chỉ đếm những event JFR **đã phát sinh và được bật/ghi**, không đo mọi lần giữ monitor hay mọi thao tác I/O. Khi cần phân tích nhiều loại event, có thể mở file bằng **JDK Mission Control (JMC)** để lọc theo event type, duration, stack trace và liên hệ với CPU/lock/GC.

## 9. Quy trình chẩn đoán từng bước trong môi trường thực

**Bước 1 — Ghi nhận triệu chứng và cửa sổ thời gian.** Ví dụ “p99 tăng từ 100 ms lên 3 giây trong 15:20–15:25”, có timestamp, throughput, CPU, heap/GC, timeout, số tác vụ đang chờ và giới hạn kết nối. Nếu không có số đo nền, rất dễ nhầm thời gian chờ bình thường thành lỗi.

**Bước 2 — Xác định PID, phiên bản JVM, cấu hình chẩn đoán.** Dùng `java -version` với runtime thực tế, `jcmd -l` và `jcmd <PID> help`. Ghi rõ JDK 21–23 hay 24+ khi nghi pinning.

**Bước 3 — Chụp chuỗi thread dump.** Dùng `Thread.dump_to_file` (ưu tiên cả JSON và text nếu cần); tìm nhóm stack tương tự và quan sát thay đổi qua thời gian. Với tải cực lớn, cân nhắc kích thước dump và chi phí chụp.

**Bước 4 — Thu JFR phủ đúng lúc vấn đề.** Dùng `settings=profile` trong một khoảng ngắn có kiểm soát. Xem `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed`, CPU samples, monitor/park/GC events phù hợp. Bật thêm start/end nếu cần phân tích vòng đời virtual thread.

**Bước 5 — Đối chiếu ba lớp bằng chứng.** (a) stack tại điểm chờ, (b) event/duration/tần suất theo thời gian, (c) metric tài nguyên như CPU, connection pool, queue và latency. Một kết luận nguyên nhân chỉ mạnh khi giải thích được cả hiện tượng quan sát và thay đổi của metric.

**Bước 6 — Kiểm chứng sửa đổi.** Thay đúng nút thắt: monitor trên JDK cũ, pool quá nhỏ, timeout chưa rõ, blocking có vòng chờ hoặc đoạn CPU-heavy. Dùng cùng cách đo trên cùng tải để so sánh trước–sau; tránh “tối ưu” toàn bộ code chỉ vì thấy nhiều virtual threads.

## 10. Các bẫy chẩn đoán thường gặp

1. **Dùng `Thread.print` rồi tưởng đã thấy mọi virtual thread.** Với virtual threads cần `Thread.dump_to_file`; dùng dump truyền thống như bằng chứng bổ sung.
2. **Coi `WAITING` là deadlock.** Cần kiểm tra tác vụ nào sẽ giải phóng điều kiện, thời gian chờ và chuỗi dump.
3. **Thấy `synchronized` trên JDK 24+ là kết luận pinning.** JEP 491 đã thay đổi hành vi monitor; dùng version đúng và JFR event thực tế.
4. **Không có `jdk.VirtualThreadPinned` là khẳng định “không có vấn đề”.** Event có ngưỡng, có khoảng thời gian ghi và có điều kiện phụ thuộc JDK.
5. **Thấy vắng `VirtualThreadStart/End` là khẳng định không có virtual threads.** Hai event này thường bị tắt mặc định.
6. **Đếm virtual threads thay vì đo tài nguyên.** Hàng chục nghìn thread ngủ hợp lệ có thể ít nghiêm trọng hơn vài trăm tác vụ đợi pool đã cạn.
7. **Gán mọi chậm chạp cho scheduler.** CPU, GC, file descriptors, network và upstream/downstream timeout vẫn là những giới hạn thực.
8. **Thu quá muộn hoặc chụp duy nhất một dump.** Sự cố ngắn có thể đã qua; phải đặt recording đúng thời điểm và đối chiếu nhiều mẫu.
9. **Ghi file mà không tìm được trên máy.** `jcmd` ra lệnh cho JVM đích ghi file: thư mục làm việc/quyền ghi nằm ở môi trường JVM đó.
10. **Đưa dump/JFR lên nơi công khai vô ý.** Stack traces, class names, tham số JVM và chuỗi có trong recording có thể chứa thông tin vận hành nhạy cảm; giữ quyền truy cập phù hợp.

## 11. Tóm lược kiến thức và tài liệu chính thức

- **Thread dump** cho thấy virtual threads ở đâu tại thời điểm chụp; dùng `jcmd <PID> Thread.dump_to_file ...`, đọc stack theo ngữ cảnh và so sánh nhiều lần.
- **JFR** cho thấy sự kiện kéo dài theo thời gian; phân tích `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed` và các event CPU/lock/GC để kiểm tra giả thuyết.
- **Pinning khác với waiting** và phải xét **phiên bản JDK**: monitor pinning quan trọng ở Java 21–23, được cải thiện lớn từ Java 24; vẫn có các tình huống pinning khác.
- **Virtual Threads không tự chữa** deadlock, nghẽn pool, CPU saturation hoặc I/O chậm. Chẩn đoán đáng tin phải ghép dump, JFR và số liệu tài nguyên thực tế.

Tham khảo thêm:

- [Oracle: Virtual Threads (Java 21)](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Oracle: `jcmd` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
