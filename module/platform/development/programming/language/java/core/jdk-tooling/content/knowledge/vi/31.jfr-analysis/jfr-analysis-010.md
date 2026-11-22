# Cách rút ra kết luận từ JFR recording

Java Flight Recorder (JFR) ghi lại các sự kiện runtime có timestamp, thời lượng, thread, stack trace và dữ liệu liên quan. Một recording có thể giúp giải thích vì sao ứng dụng chậm, CPU cao, GC tốn thời gian, thread chờ lock hoặc I/O kéo dài. Tuy nhiên, recording chỉ cung cấp bằng chứng trong khoảng thời gian và với tập event đã được bật. Muốn kết luận đáng tin cậy, cần xác định đúng triệu chứng, kiểm tra chất lượng dữ liệu, nối các event theo timeline và phân biệt quan sát trực tiếp với giả thuyết nguyên nhân.

Bài này dùng JDK 17 trở lên và JDK Mission Control (JMC). Nội dung hướng dẫn kiểm tra recording, đọc Automated Analysis Results, phân tích CPU, thread, lock, I/O, allocation và GC, so sánh với baseline, đánh giá giới hạn của sampling và viết một kết luận có thể kiểm chứng.

## 1. Recording cung cấp bằng chứng gì?

JFR thu thập các event do JVM và ứng dụng phát ra. Tùy cấu hình, event có thể mô tả:

- CPU load của JVM và máy; method samples và stack trace của thread đang chạy.
- Thread bị park, sleep, chờ monitor hoặc bị block khi lấy lock.
- Socket read/write và file read/write.
- Allocation sample và allocation liên quan TLAB.
- Garbage collection, các pha GC và pause.
- Exception/error được ném; thread start/end; class loading; safepoint.
- Custom event do ứng dụng tự định nghĩa và phát ra.

Mỗi event có thể có timestamp, duration, event thread, stack trace và các field riêng. Không phải event nào cũng có đủ mọi field; một số là event tức thời, một số có duration, một số là sample thống kê.

Một recording hữu ích để trả lời những câu hỏi có thể gắn với event đã thu thập:

- CPU tăng trong khoảng nào, thread nào có nhiều method sample?
- Thread quan trọng chờ lock hoặc socket trong bao lâu?
- GC pause chiếm bao nhiêu thời gian của cửa sổ quan sát?
- Class hoặc stack trace nào tạo nhiều allocation?
- Exception nào xuất hiện thường xuyên trong khoảng sự cố?

JFR không tự biết request nào bị chậm nếu ứng dụng không phát custom event hoặc không có tracing liên kết request. Nó cũng không chứng minh quan hệ nhân quả chỉ vì hai hiện tượng xuất hiện cùng thời điểm.

## 2. Xác định câu hỏi trước khi mở recording

Bắt đầu bằng cách ghi rõ triệu chứng và cửa sổ thời gian:

- Người dùng thấy latency tăng, throughput giảm hay request timeout?
- CPU cao ở JVM hay toàn bộ máy?
- Heap tăng, GC pause dài hay allocation rate cao?
- Thread bị block, chờ lock, chờ socket hay chờ queue?
- Sự cố bắt đầu và kết thúc vào thời điểm nào?
- Workload, traffic, batch size và cấu hình có thay đổi không?

| Triệu chứng | Câu hỏi phân tích đầu tiên |
|---|---|
| CPU cao | JVM có dùng CPU cao không? Thread/method nào được sample nhiều? |
| Request chậm | Thời gian nằm ở code, lock, socket, file I/O hay GC pause? |
| GC nhiều | Allocation rate cao, live set lớn hay pause từng GC quá dài? |
| Thread tăng | Thread nào được tạo, thread nào còn sống và chúng đang làm gì? |
| Timeout | Có event chờ I/O, lock, park hoặc custom request timeout cùng thời điểm không? |
| Lỗi tăng | Exception/error nào xuất hiện, ở thread và stack nào? |

Không bắt đầu bằng việc tìm một event bất thường rồi gán nó thành nguyên nhân. Trước tiên hãy xác định khoảng thời gian và tác động cần giải thích.

## 3. Kiểm tra recording trước khi diễn giải

Mở file trong JMC hoặc xem bằng công cụ dòng lệnh:

~~~powershell
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

Lệnh summary cho biết thời gian recording, số lượng event theo loại và một số thông tin tổng quan. Lệnh metadata hiển thị event type cùng field được định nghĩa trong file.

Kiểm tra:

1. File có mở được và có chứa event không?
2. Thời gian bắt đầu/kết thúc có bao trùm khoảng xảy ra sự cố không?
3. Recording có bao gồm workload thực sự gặp vấn đề không?
4. Có event CPU, thread, lock, I/O, GC hoặc allocation phù hợp không?
5. Stack trace có được ghi cho event cần điều tra không?
6. Event threshold và sampling interval có phù hợp không?
7. Có khoảng trống do recording bị dừng, rotate hoặc thiếu dữ liệu không?
8. JVM version, GC, VM arguments và recording settings có khớp môi trường không?

Nếu recording bắt đầu sau khi sự cố kết thúc, nó không thể giải thích giai đoạn đó. Nếu event cần thiết bị tắt, việc không nhìn thấy event không chứng minh hiện tượng không xảy ra.

### 3.1. Đồng bộ timeline

Ghi lại thời gian bắt đầu/kết thúc recording, timezone nếu biết, uptime của JVM và thời điểm sự cố theo log/monitoring. Đồng bộ timeline giữa JFR, application log, reverse proxy, database và metrics.

Đánh dấu startup/warm-up, workload bình thường, batch hoặc traffic cao, cửa sổ sự cố và giai đoạn phục hồi. Một recording dài có thể chứa nhiều loại workload; hãy phân tích riêng cửa sổ có triệu chứng.

### 3.2. Kiểm tra event threshold

Nhiều event có duration threshold. Theo cấu hình phổ biến, nhiều Java Application event chỉ được ghi khi thời lượng vượt ngưỡng; tài liệu JDK 17 nêu ví dụ mặc định khoảng 20 ms cho nhiều loại event. Threshold có thể thay đổi trong recording settings.

Vì vậy:

- Không có monitor contention event không chứng minh không có lock wait ngắn.
- Không thấy socket read event không có nghĩa không có network I/O; thao tác ngắn có thể nằm dưới threshold hoặc event bị tắt.
- Hạ threshold có thể thu được nhiều event hơn nhưng làm tăng lượng dữ liệu và overhead.
- Khi cần điều tra wait ngắn, tạo recording ngắn với threshold thấp hơn và đo tác động.

Kiểm tra settings và metadata trước khi sử dụng số lượng event như bằng chứng phủ định.

## 4. Bắt đầu bằng Automated Analysis Results trong JMC

Trang **Automated Analysis Results** tổng hợp các dấu hiệu tiềm ẩn theo nhóm như Java Application, JVM Internals và Environment. Kết quả màu vàng/đỏ giúp ưu tiên điều tra; chúng là cảnh báo dựa trên dữ liệu đã ghi, không phải phán quyết tự động về nguyên nhân gốc.

Quy trình:

1. Mở file .jfr trong JMC.
2. Đọc Automated Analysis Results.
3. Ghi lại cảnh báo liên quan trực tiếp tới triệu chứng.
4. Mở trang chi tiết tương ứng từ Outline.
5. Chọn khoảng thời gian có dấu hiệu bất thường.
6. Xem event, thread, class, stack trace và duration gốc.
7. Đối chiếu với log và metrics độc lập.

Không chỉ đọc điểm màu. Hãy xác minh bằng event cụ thể, số lần, tổng duration, thời điểm và stack trace.

## 5. Kết luận về CPU và code execution

Khi CPU cao, phân biệt CPU của JVM với CPU toàn máy.

### 5.1. CPU load

Event jdk.CPULoad cung cấp thông tin CPU load của JVM và máy tại thời điểm sample:

- JVM load cao và machine load cao: JVM có thể là một nguồn sử dụng CPU đáng kể.
- JVM load thấp nhưng machine load cao: process khác có thể đang chiếm CPU.
- Cả hai thấp: triệu chứng CPU cao có thể không nằm trong cửa sổ recording hoặc đã kết thúc.

Đối chiếu với Task Manager, top, pidstat hoặc monitoring của host/container. Giá trị JFR là sample theo thời gian, không phải phép đo liên tục tuyệt đối.

### 5.2. Method samples và stack trace

JFR dùng method sampling để lấy stack của thread đang chạy code. Trong JMC, xem **Method Profiling**, **Hot Methods**, **Call Tree** hoặc trang Java Application tùy phiên bản.

Cách đọc:

1. Chọn khoảng thời gian CPU cao.
2. Xem method có số sample nổi bật.
3. Mở call tree để biết method đó được gọi từ luồng nào.
4. Tìm frame đầu tiên thuộc package ứng dụng.
5. Xem nhiều stack trace và thread, tránh tối ưu một method chỉ vì nó xuất hiện trong một sample.
6. Đối chiếu với workload và số request hoàn thành.

Method samples cho biết nơi thread được sample khi đang chạy. Chúng không trực tiếp cho biết thời gian chính xác của từng lời gọi method. Số sample ít làm kết luận kém ổn định.

### 5.3. CPU theo thread

Nếu event jdk.ThreadCPULoad có trong recording, dùng nó để xem thread nào có CPU load nổi bật. Kết hợp với method samples để xác định code chạy trên thread đó.

- Thread request worker có CPU load cao và call tree tập trung tại một method xử lý dữ liệu: method đó là ứng viên cần profile sâu.
- JVM CPU load thấp nhưng host load cao: kiểm tra process khác.
- Thread có ít method sample nhưng latency cao: thread có thể dành thời gian chờ lock/I/O thay vì chạy CPU.

Không kết luận thread CPU cao chỉ từ tổng số event; hãy xem khoảng thời gian, event type và sample coverage.

## 6. Kết luận về thread wait và synchronization

Thread có thể không chạy code vì đang chờ lock, park, sleep, queue hoặc một điều kiện khác.

| Event | Ý nghĩa |
|---|---|
| jdk.JavaMonitorEnter | Thread chờ vào intrinsic monitor, thường là synchronized |
| jdk.JavaMonitorWait | Thread gọi Object.wait() và chờ notification/timeout |
| jdk.ThreadPark | Thread park qua cơ chế như LockSupport/AQS |
| jdk.ThreadSleep | Thread ngủ bằng sleep |
| jdk.ThreadStart / jdk.ThreadEnd | Vòng đời thread |

### 6.1. Monitor enter và monitor wait

JavaMonitorEnter liên quan tới thời gian chờ lấy monitor. Nếu nhiều thread quan trọng cùng chờ một lock và tổng thời gian chờ lớn, critical section có thể gây bottleneck.

JavaMonitorWait liên quan tới Object.wait(). Đây là cơ chế chờ điều kiện; thread nhả monitor khi chờ và cần lấy lại monitor trước khi tiếp tục sau notification/timeout.

Không gộp hai loại event thành kết luận “lock bị giữ quá lâu”. Hãy đọc event type, monitor class/identity, thread và stack trace.

### 6.2. Xác định lock contention

Trong JMC, mở **Lock Instances** hoặc trang synchronization tương ứng:

1. Sắp xếp theo tổng thời gian blocked hoặc số lần contention.
2. Chọn lock instance có tác động lớn.
3. Xem thread chờ và stack trace của thread.
4. Tìm code ứng dụng đang giữ hoặc yêu cầu lock.
5. Kiểm tra critical section có chứa I/O, logging, xử lý dữ liệu lớn hoặc lời gọi chậm không.
6. So sánh với request latency trong cùng thời gian.

Nếu nhiều request thread cùng chờ một lock trong lúc throughput giảm, có bằng chứng cho thấy contention góp phần vào bottleneck. Cần xác định lock owner và đoạn code liên quan trước khi đề xuất thay đổi.

### 6.3. ThreadPark và thread pool

ThreadPark có thể xuất hiện khi thread chờ trong executor, queue, semaphore, future hoặc synchronizer. Park không tự động là lỗi; worker nhàn rỗi thường park để chờ task mới.

- Worker pool rảnh và chờ task: có thể bình thường.
- Tất cả worker park chờ một future mà task hoàn thành cần chính pool đó: có thể là starvation.
- Request thread park chờ queue hoặc semaphore trong lúc latency tăng: kiểm tra giới hạn concurrency và producer/consumer.
- Thread park chờ external response: liên kết với I/O hoặc timeout.

Một event park đơn lẻ không cho biết toàn bộ quan hệ phụ thuộc. Đối chiếu nhiều thread và thời điểm.

## 7. Kết luận về I/O và network

Các event thường dùng là jdk.SocketRead, jdk.SocketWrite, jdk.FileRead và jdk.FileWrite.

Trong JMC, mở **Socket I/O** hoặc **File I/O**. Xem thời lượng, số byte, địa chỉ/host hoặc file liên quan nếu event cung cấp, thread và stack trace.

- Socket read duration dài: thread chờ dữ liệu từ peer hoặc network path.
- Socket write duration dài: ghi dữ liệu bị chậm, peer đọc chậm hoặc buffer/network bị backpressure.
- File read/write kéo dài: storage, filesystem hoặc thao tác file có thể góp phần vào latency.
- Nhiều event cùng host/endpoint: kiểm tra dependency đó và thời gian tương ứng trong server-side metrics.

Không kết luận server từ xa chậm chỉ dựa vào socket read. Thời lượng có thể bao gồm thời gian chờ dữ liệu qua network, peer xử lý, congestion hoặc protocol behavior. Cần đối chiếu tracing, log của peer, network metrics và timeout.

Nếu không có I/O event, kiểm tra event có được bật và threshold có bỏ qua các thao tác ngắn hay không.

## 8. Kết luận về garbage collection

GC có thể ảnh hưởng hiệu năng theo hai cách chính: một lần GC có pause dài làm request bị dừng; hoặc tổng pause tích lũy lớn khiến ứng dụng mất nhiều thời gian không phục vụ công việc.

Các event hữu ích gồm jdk.GarbageCollection, jdk.GCPhasePause, event heap summary và allocation.

### 8.1. Xem GC pause, không chỉ GC duration

Nhiều collector thực hiện công việc concurrent trong khi application thread vẫn chạy. Tổng duration của một GC không nhất thiết bằng thời gian ứng dụng bị dừng.

Để đánh giá pause, xem jdk.GCPhasePause và tổng thời lượng pause theo từng GC ID. Trong JMC, mở trang **Garbage Collections** và biểu đồ pause/sum of pauses.

Theo dõi số lần GC, tổng pause trong cửa sổ quan sát, pause lớn nhất, GC type/cause, heap trước/sau GC nếu recording có dữ liệu, allocation rate và live set.

### 8.2. Diễn giải GC

| Quan sát | Giả thuyết cần kiểm chứng |
|---|---|
| Nhiều young GC, allocation rate cao | Nhiều object ngắn hạn làm tăng nhu cầu thu hồi |
| Một số pause dài bất thường | Pha GC cụ thể hoặc áp lực heap có thể ảnh hưởng latency |
| Full GC xuất hiện cùng heap pressure | JVM có thể thiếu khoảng trống hoặc cần thu hồi object sống lâu |
| Tổng pause lớn nhưng từng pause ngắn | Nhiều lần pause cộng dồn có thể ảnh hưởng throughput/latency |
| GC time thấp nhưng request vẫn chậm | Tìm lock, I/O, CPU, queue hoặc dependency khác |

Không tăng heap hoặc đổi collector ngay từ một recording. Trước tiên xác định pause có trùng với latency, live set có tăng, allocation rate có cao và cấu hình heap hiện tại ra sao.

### 8.3. Heap Statistics

Trong JDK 17, tùy chọn Heap Statistics có thể kích hoạt old GC ở đầu và cuối recording, tạo thêm pause và làm thay đổi chính hệ thống đang đo. Khi mục tiêu là đo latency/performance thông thường, tránh bật tính năng này trừ khi đang điều tra live set hoặc memory leak và đã chấp nhận tác động.

## 9. Kết luận về allocation và memory retention

Allocation event giúp tìm nơi tạo object; heap/old-object data giúp điều tra object còn sống.

Các event thường gặp là jdk.ObjectAllocationSample, jdk.ObjectAllocationInNewTLAB, jdk.ObjectAllocationOutsideTLAB, jdk.ThreadAllocationStatistics và jdk.OldObjectSample nếu được cấu hình và recording hỗ trợ.

Dùng JMC **TLAB Allocations** để xem allocation theo class, thread và stack trace. Với ObjectAllocationSample, field weight là lượng byte ước lượng mà sample đại diện; không đếm event như số object chính xác.

- Allocation rate cao nhưng heap sau GC ổn định: có thể là nhiều object tạm thời.
- Allocation rate cao cùng nhiều young GC: allocation pressure có thể góp phần tăng GC work.
- Heap/live set tăng qua nhiều chu kỳ: cần điều tra object được giữ lại.
- Old object sample có đường tham chiếu dài hạn: lần theo GC roots để tìm chủ sở hữu.

Một allocation hotspot không chứng minh memory leak. Ngược lại, một leak có thể xuất phát từ object được tạo ít nhưng giữ lâu. Khi cần xác nhận retention, dùng heap dump và phân tích đường tham chiếu.

## 10. Kết luận về exception và error

Nếu recording có jdk.JavaExceptionThrow và jdk.JavaErrorThrow, hãy xem loại exception/error, thread, stack trace, timestamp và số lần xuất hiện.

Một exception được ném và bắt lại có thể là luồng điều khiển hợp lệ; không phải mọi exception đều là lỗi gây sự cố. Tập trung vào exception tăng đột biến đúng cửa sổ sự cố, cùng stack trace lặp lại, error liên quan resource exhaustion và exception đi cùng request failure/retry/timeout trong log.

JFR event không nhất thiết ghi đầy đủ message hoặc dữ liệu nghiệp vụ. Kết hợp application log, metrics và trace để biết tác động thực tế.

## 11. Đọc recording theo timeline

Một kết luận tốt nối các dấu hiệu theo thứ tự thời gian.

Ví dụ giả định:

1. Request rate tăng.
2. Allocation rate tăng trong các request worker.
3. Young GC xuất hiện dày hơn.
4. Tổng GC pause tăng trong cửa sổ latency cao.
5. Sau khi request rate giảm, allocation và GC activity cũng giảm.

Chuỗi này hỗ trợ giả thuyết workload tạo nhiều object làm tăng GC pressure. Để kết luận chắc hơn, so sánh cùng workload với baseline và kiểm tra allocation stack trace.

Ví dụ khác:

1. Request latency tăng.
2. Nhiều request worker chờ cùng monitor.
3. Lock instance có tổng blocked time cao.
4. Stack trace trỏ tới logging method trong synchronized section.
5. Sau khi thay đổi logging/critical section, recording mới cho thấy blocked time giảm.

Đây là bằng chứng mạnh hơn vì có mối liên hệ giữa thời điểm, lock, stack trace và thay đổi trước/sau. Dù vậy, vẫn cần kiểm tra throughput và latency để xác nhận cải thiện.

## 12. So sánh recording tốt và recording xấu

Nếu có thể, ghi một recording khi ứng dụng hoạt động bình thường và một recording khi triệu chứng xuất hiện. Giữ điều kiện gần giống nhau:

- Cùng phiên bản ứng dụng và JDK.
- Cùng GC và VM arguments.
- Cùng recording template và event threshold.
- Thời lượng tương đương.
- Workload, traffic và batch size tương đương.
- Cùng cách tính latency và throughput.

| Nhóm | Chỉ số cần so sánh |
|---|---|
| CPU | JVM/machine CPU load, method sample và thread CPU |
| Threads | Số thread, thread stall, park và monitor blocked duration |
| I/O | Số event, bytes, duration và endpoint/file |
| GC | Số lần GC, pause sum, max pause và heap trend |
| Allocation | Weighted bytes, class, thread và stack trace |
| Exceptions | Loại event, số lần và stack trace |
| Workload | Request rate, throughput, latency và thời điểm |

Không so sánh tổng byte hoặc số event nếu recording có thời lượng khác nhau. Dùng rate/second, tỷ lệ trên mỗi request hoặc delta trong cùng khoảng thời gian.

## 13. Dùng jfr để kiểm tra event từ terminal

Xem tổng quan và metadata:

~~~powershell
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

In các event CPU, thread, lock, I/O, GC và allocation có trong recording:

~~~powershell
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite,jdk.GarbageCollection,jdk.GCPhasePause,jdk.ObjectAllocationSample recording.jfr
~~~

In exception:

~~~powershell
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow recording.jfr
~~~

Lưu event đã lọc vào file:

~~~powershell
jfr print --events jdk.JavaMonitorEnter,jdk.SocketRead,jdk.GCPhasePause recording.jfr > selected-events.txt
~~~

Một event type không có trong recording sẽ không tạo ra bằng chứng khi in. Hãy dùng summary và metadata để kiểm tra event type thực tế trước khi lọc. Với recording lớn, lọc theo event cần thiết hoặc dùng JMC để lọc theo thời gian và điều kiện.

## 14. Ví dụ thực hành: tạo recording có CPU, lock và allocation

Tạo file RecordingConclusionDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class RecordingConclusionDemo {
    private static final Object LOCK = new Object();
    private static volatile byte[] lastBuffer;
    private static int criticalSections;

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        for (int worker = 0; worker < 4; worker++) {
            final int workerId = worker;
            tasks.add(pool.submit(() -> {
                try {
                    start.await();
                    for (int i = 0; i < 6; i++) {
                        synchronized (LOCK) {
                            Thread.sleep(30);
                            criticalSections++;
                        }
                        byte[] buffer = new byte[512 + (i * 16)];
                        buffer[0] = (byte) workerId;
                        lastBuffer = buffer;
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get();
        }
        pool.shutdown();

        long checksum = 0;
        for (int i = 0; i < 5_000_000; i++) {
            checksum += (i * 31L) % 97;
        }
        lastBuffer = new byte[(int) (checksum % 4096) + 1];

        for (int i = 0; i < 100_000; i++) {
            byte[] temporary = new byte[256 + (i & 1023)];
            temporary[0] = (byte) i;
            lastBuffer = temporary;
        }

        System.out.println("Workers completed: 4");
        System.out.println("Critical sections: " + criticalSections);
        System.out.println("Allocation loop completed: 100000");

        // Giữ JVM sống để recording đủ thời gian thu thập event.
        Thread.sleep(22_000);
    }
}
~~~

Chương trình cố ý tạo ba kiểu hoạt động:

- Bốn worker tranh chấp cùng một monitor; sleep trong synchronized chỉ để tạo lock wait có thể quan sát, không phải mẫu code production.
- Vòng lặp checksum tạo một đoạn code tính toán để method sampling có cơ hội quan sát.
- Vòng lặp array tạo allocation; biến volatile giữ tham chiếu mới nhất để tránh toàn bộ object bị tối ưu như dữ liệu không quan sát được.

Biên dịch:

~~~powershell
javac RecordingConclusionDemo.java
~~~

Chạy và ghi JFR 20 giây:

~~~powershell
java -XX:StartFlightRecording=name=conclusion,settings=profile,duration=20s,filename=conclusion.jfr RecordingConclusionDemo
~~~

Các dòng stdout do chương trình in sau khi worker hoàn thành:

~~~text
Workers completed: 4
Critical sections: 24
Allocation loop completed: 100000
~~~

JVM có thể in thêm thông báo khởi tạo recording tùy bản JDK. Các event thực tế và sample count phụ thuộc runtime, máy và JFR settings; không kỳ vọng output event giống hệt giữa các lần chạy.

Sau khi recording hoàn tất:

~~~powershell
jfr summary conclusion.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ExecutionSample,jdk.ObjectAllocationSample conclusion.jfr
~~~

Mở file conclusion.jfr trong JMC:

1. Tìm Lock Instances để kiểm tra monitor wait.
2. Tìm Method Profiling để xem method được sample trong workload checksum.
3. Tìm TLAB Allocations để xem allocation của array.
4. So sánh timestamp của các event với giai đoạn worker chạy và giai đoạn main thread chờ.
5. Viết kết luận riêng cho từng tín hiệu và ghi rõ event/stack hỗ trợ kết luận đó.

Nếu một loại event không xuất hiện, kiểm tra recording settings, threshold và thời điểm workload. Không bịa kết quả dựa trên output kỳ vọng của ví dụ.

## 15. Phân biệt quan sát, diễn giải và nguyên nhân

Khi viết kết luận, tách ba cấp độ:

| Cấp độ | Ví dụ |
|---|---|
| Quan sát | Trong cửa sổ 14:02–14:04, request worker có nhiều JavaMonitorEnter duration dài trên cùng monitor. |
| Diễn giải | Các worker phải chờ cùng critical section; contention có thể làm tăng thời gian xử lý request. |
| Nguyên nhân đã xác nhận | Stack trace và source cho thấy critical section giữ lock trong lúc ghi log đồng bộ; thay đổi được đo lại và blocked duration giảm. |

Observation là điều recording trực tiếp cho thấy. Interpretation là ý nghĩa có thể rút ra từ event. Root cause cần thêm bằng chứng như source code, log, dependency metrics, heap/reference analysis hoặc thử nghiệm trước/sau.

Dùng từ ngữ phù hợp với độ chắc chắn:

- **Đã quan sát:** event và metric có trong recording.
- **Có khả năng:** bằng chứng phù hợp nhưng còn giả thuyết khác.
- **Chưa đủ dữ liệu:** event thiếu, thời gian không khớp hoặc workload không đại diện.
- **Đã xác nhận:** có bằng chứng độc lập hoặc thử nghiệm tái hiện/xác minh.

Không dùng “JFR chứng minh” khi recording chỉ cho thấy hai event xuất hiện cùng thời điểm.

## 16. Mẫu viết kết luận từ recording

Một báo cáo ngắn, có thể kiểm chứng, nên gồm:

~~~text
1. Phạm vi
   - File recording:
   - JDK/VM:
   - Thời gian ghi:
   - Workload và triệu chứng:

2. Chất lượng dữ liệu
   - Event cần thiết có/không:
   - Stack trace có/không:
   - Threshold/template:
   - Khoảng thời gian bị thiếu:

3. Quan sát
   - Metric/event:
   - Timestamp:
   - Duration/count/weight:
   - Thread/class/stack liên quan:

4. Diễn giải
   - Điều recording hỗ trợ:
   - Giả thuyết còn lại:
   - Bằng chứng chưa có:

5. Kết luận và độ tin cậy
   - Kết luận:
   - Mức tin cậy: cao / trung bình / thấp
   - Lý do:

6. Bước kiểm chứng
   - Log/metric/source cần đối chiếu:
   - Thử nghiệm hoặc recording tiếp theo:
   - Chỉ số thành công:
~~~

Ví dụ kết luận có cơ sở:

> Trong cửa sổ 14:02–14:04, nhiều request worker ghi nhận thời gian chờ monitor trên cùng lock instance. Stack trace của các event tập trung tại OrderService.updateCache(). Điều này cho thấy contention ở critical section có khả năng góp phần làm tăng latency. Recording chưa xác định được toàn bộ thời gian lock owner giữ monitor; cần kiểm tra source và ghi thêm một recording khi workload tương đương để xác nhận sau khi thay đổi.

Ví dụ này ghi rõ phạm vi, event, stack trace, mức chắc chắn và phần cần xác minh tiếp.

## 17. Những giới hạn cần ghi vào kết luận

- JFR chỉ ghi các event được bật và không thể khôi phục event đã bỏ lỡ.
- Event threshold có thể bỏ qua thao tác ngắn.
- Method profiling là sampling, không phải trace mọi lời gọi method.
- Allocation sample có weight ước lượng, không phải danh sách đầy đủ object.
- Recording không có custom request event có thể không liên kết trực tiếp với request/trace ID.
- Một recording có thể không bao trùm thời điểm bắt đầu hoặc kết thúc triệu chứng.
- Event trùng thời điểm không chứng minh quan hệ nhân quả.
- JMC Automated Analysis Results đưa ra cảnh báo/gợi ý; người phân tích cần xác minh event gốc.
- Workload, JVM flags, JDK, GC và môi trường khác nhau làm kết quả khó so sánh.
- Recording có thể có overhead và dung lượng đáng kể tùy event settings.

Với performance recording tiêu chuẩn, Oracle nêu overhead thường thấp trong nhiều ứng dụng; tuy nhiên phải đo trên workload thật. Heap Statistics có thể kích hoạt old GC ở đầu/cuối recording và gây pause đáng kể, nên không bật khi mục tiêu là đo latency thông thường.

## 18. Lỗi thường gặp khi rút kết luận

| Sai lầm | Vì sao sai | Cách khắc phục |
|---|---|---|
| Không thấy event nên kết luận không có vấn đề | Event có thể bị tắt hoặc dưới threshold | Kiểm tra event settings và threshold |
| Xem method có nhiều sample là method chậm nhất tuyệt đối | Sampling không đo chính xác duration từng lời gọi | Dùng sample để xếp hạng hotspot, sau đó profile/benchmark |
| GC duration bằng application pause | Nhiều GC phase chạy concurrent | Xem GCPhasePause và tổng pause |
| Allocation nhiều đồng nghĩa memory leak | Object tạm thời có thể được thu hồi nhanh | Đối chiếu heap sau GC và retained objects |
| ThreadPark luôn là thread bị treo | Worker nhàn rỗi thường park bình thường | Đọc stack, thread role và timeline |
| SocketRead dài chứng minh server remote chậm | Duration bao gồm nhiều yếu tố network/peer | Đối chiếu log/metrics hai đầu và tracing |
| Một recording đủ để chứng minh regression | Có thể khác workload, settings hoặc thời điểm | Ghi baseline và bad run trong điều kiện tương đương |
| Sửa nhiều thứ cùng lúc rồi ghi nhận cải thiện | Không xác định được thay đổi nào tạo hiệu quả | Thay đổi từng yếu tố và đo lại |

## 19. Quy trình điều tra từ đầu đến cuối

1. Viết câu hỏi và triệu chứng có thể đo được.
2. Xác định PID, JDK, GC, VM arguments và workload.
3. Tạo recording bao trùm cửa sổ sự cố với event settings phù hợp.
4. Chạy jfr summary và kiểm tra metadata/event coverage.
5. Mở JMC và đọc Automated Analysis Results.
6. Chọn trang phù hợp: CPU/method, Threads, Locks, Socket/File I/O, GC hoặc Allocation.
7. Ghi lại timestamp, event type, duration/count/weight, thread và stack trace.
8. Nối event theo timeline và đối chiếu với request rate, latency, log, host/container metrics.
9. Viết riêng observation, interpretation, root-cause hypothesis và confidence.
10. Xác định bằng chứng còn thiếu và tạo thử nghiệm/recording để kiểm chứng.
11. Thay đổi một yếu tố có kiểm soát.
12. Ghi lại recording sau thay đổi với workload và settings tương đương.
13. So sánh các chỉ số trước/sau và xác nhận tác động tới latency, throughput, CPU, GC hoặc contention.
14. Lưu recording và báo cáo trong nơi có quyền truy cập phù hợp.

## 20. Checklist kết luận từ JFR recording

- [ ] Câu hỏi điều tra và triệu chứng đã được xác định.
- [ ] Recording bao trùm đúng cửa sổ sự cố và workload đại diện.
- [ ] Đã ghi JDK, VM, GC, template và thời gian recording.
- [ ] Đã kiểm tra jfr summary và event metadata.
- [ ] Đã xác nhận event cần thiết và stack trace có trong file.
- [ ] Đã xem threshold và giới hạn sampling.
- [ ] Đã đọc Automated Analysis Results rồi xác minh event gốc.
- [ ] Đã kiểm tra CPU/method samples nếu nghi ngờ code execution.
- [ ] Đã kiểm tra thread, monitor, park và lock instance.
- [ ] Đã kiểm tra socket/file I/O nếu nghi ngờ dependency.
- [ ] Đã kiểm tra GC pause riêng với GC duration.
- [ ] Đã phân biệt allocation pressure với retained heap.
- [ ] Đã nối các event theo timeline và workload.
- [ ] Đã tách observation, interpretation và root cause.
- [ ] Đã ghi mức độ tin cậy và dữ liệu còn thiếu.
- [ ] Đã đề xuất bước kiểm chứng có thể đo được.
- [ ] Đã so sánh recording trước/sau trong điều kiện tương đương.
- [ ] Đã bảo vệ recording và redact thông tin nhạy cảm trước khi chia sẻ.

Một kết luận JFR tốt luôn chỉ ra recording đã ghi gì, ở thời điểm nào, trên thread/stack nào và điều đó hỗ trợ giả thuyết nào. Dùng CPU samples, thread stalls, lock, I/O, GC pause và allocation để xác định nơi cần điều tra; đối chiếu workload và baseline trước khi gọi đó là nguyên nhân. Ghi rõ giới hạn event/sampling, mức tin cậy và phép đo tiếp theo để biến kết luận thành một giả thuyết có thể kiểm chứng.

## Tài liệu tham khảo

- Oracle, Java SE 17 Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle, Java SE 17 Diagnostic Tools — Analyze a Flight Recording: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle, Java SE 17 — The jfr Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
