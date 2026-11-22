# Stop-the-world và safepoint; phân biệt thời gian GC với tổng thời gian dừng

## 1. Tổng quan: GC, STW và safepoint không đồng nghĩa

Trong một JVM, **garbage collection (GC)** quản lý khả năng truy cập và thu hồi tài nguyên heap, **stop-the-world (STW)** mô tả khoảng thời gian các luồng Java liên quan phải ngừng thực thi mã ứng dụng thông thường để VM làm một operation, còn **safepoint** là cơ chế phối hợp đưa các luồng tới trạng thái an toàn cho những operation đó.

Phân biệt ba nhận xét:

- **Có GC nhưng không phải mọi thời gian GC đều STW.** Collector concurrent có thể mark hoặc thực hiện các phase khác khi application threads vẫn chạy.
- **Có safepoint nhưng không hề chạy GC.** VM có thể cần phối hợp global safepoint cho những tác vụ nội bộ khác, tùy JDK và implementation.
- **Có request latency tăng nhưng không phải do GC hay safepoint.** Lock, socket, CPU starvation, scheduling, I/O hoặc cgroup throttling có thể làm ứng dụng chậm.

Mục tiêu bài học là **phân biệt phạm vi những đồng hồ đo**: một dòng GC `Pause ... 0.5ms`, một dòng safepoint `Total: ... ns`, một biểu đồ GC CPU time và một request latency 120 ms **không tự động đo cùng một khoảng**.

> **Tư duy đúng:** cần hỏi mỗi metric ghi nhận **work của GC**, **wall-clock GC pause**, **thời gian tiến đến safepoint**, **tổng khoảng VM phối hợp dừng**, hay **thời gian end-to-end của người dùng**.

### Hai tình huống ngược nhau

**Trường hợp 1:** GC thực hiện công việc STW trong 2 ms, nhưng phải đợi Java threads đạt safe states tới 30 ms. JVM stop interval liên quan safepoint có thể dài hơn đáng kể 2 ms. Tối ưu thuật toán copy object có thể không giải quyết nút thắt **time to safepoint**.

**Trường hợp 2:** một concurrent GC cycle mất 500 ms wall-clock nhưng đa phần thời gian Java threads vẫn thực thi, chỉ có vài pause ngắn. Gọi cả 500 ms là “application stopped” sẽ sai.

## 2. Safepoint vận hành như thế nào?

JVM cần biết khi nào một thread đang ở trạng thái mà một số runtime operations có thể kiểm tra hoặc thay đổi object references, stacks, metadata và cấu trúc nội bộ một cách nhất quán. Trong HotSpot, compiled/interpreted code và thread transitions hỗ trợ các **safepoint polls** hoặc safe states thích hợp. Vị trí và chiến lược poll do JVM/JIT quyết định, không phải do source Java đặt thủ công ở từng dòng.

Một global safepoint có thể hình dung:

~~~text
              JVM yêu cầu global safepoint
                          |
           +--------------+---------------+
           |              |               |
 Thread A đang Java  Thread B đang Java  Thread C blocked/native
           |              |               |
     poll / safe     thêm vài lệnh        VM đánh giá
       state          rồi safe          safe state
           |              |               |
           +--------------+---------------+
                          |
                 Các điều kiện đạt
                          |
                 VM operation chạy
                          |
                  Java tiếp tục
~~~

Các luồng không nhất thiết cùng dừng trong một microsecond. Thread A có thể ngừng sớm rồi chờ thread B. Điều này là một phần lý do **reaching safepoint** có thể ảnh hưởng trải nghiệm của ứng dụng dù work ở safepoint tương đối ngắn.

**Phân biệt thêm:**

- Global safepoint là cơ chế phối hợp toàn cục đối với những Java threads cần thiết.
- Một số operation có thể dùng **thread-local handshake**, nhắm tới một hoặc nhiều threads thay vì tạo global pause.
- `Thread.sleep`, `Thread.yield`, `Thread.State.WAITING` không phải API cho Java developer tự buộc VM safepoint.
- Native OS threads không nhất thiết bị ngừng tuyệt đối chỉ vì các Java mutators đang STW. Native transitions và một số JNI critical regions có quy tắc riêng.

**Stop-the-world không có nghĩa toàn bộ máy tính, kernel, native code, GC worker và mọi tiến trình khác bị đóng băng.** Nó là ràng buộc đối với hoạt động Java application theo giao thức runtime.

## 3. Phân rã một lần safepoint thành những khoảng đo

Trong một **timeline khái niệm**, ta có bốn mốc:

~~~text
        t_request              t_safe           t_work_end       t_resume
             |                    |                  |               |
             v                    v                  v               v
 Java đang chạy |--- phối hợp ----|--- VM work -------|-- hoàn tất ---| Java chạy
                 reaching/TTSP       at safepoint       leaving
             |<---------------- total safepoint --------------------->|
~~~

Ở các log HotSpot hiện đại, có thể gặp những trường:

- **Reaching safepoint:** khoảng phối hợp từ lúc bắt đầu yêu cầu đến khi các threads cần thiết ở safe states. Thường liên hệ với **time to safepoint (TTSP)**.
- **At safepoint:** elapsed interval khi VM ở điều kiện safepoint thực hiện operation và các phần overhead liên quan.
- **Leaving safepoint:** phần hoàn tất/cho phép Java thực thi tiếp.
- **Total:** phạm vi total safepoint theo timer của JVM và bản log đó.

Các mốc là mô hình để giải thích. **Không lấy nhãn của một bản HotSpot làm chuẩn JVM Specification cho mọi collector/JDK.**

### 3.1. Reaching safepoint không phải GC heap work

TTSP cao có thể do:

- Thread phản hồi safepoint poll chậm do compiled code hoặc native transition.
- Một luồng chưa được scheduler cấp CPU đủ kịp để đến safe state.
- CPU saturation, container CPU throttling hoặc concurrency quá cao.
- JNI critical region và các điều kiện đặc biệt ở runtime.
- Chi phí synchronization/coordinating giữa các threads.

Không kết luận “GC mark chậm” khi log cho biết hầu hết thời gian nằm ở **reaching**: GC work ở safepoint thậm chí còn chưa bắt đầu.

### 3.2. At safepoint không nhất thiết bằng GC elapsed

At-safepoint interval có thể gồm GC work thực sự cùng overhead VM operation, safepoint bookkeeping, preparation hoặc completion tương ứng. Một dòng GC summary có ranh giới timer riêng và có thể nhỏ hơn số **At safepoint** hoặc **Total**.

Nếu safepoint reason không liên quan GC, có thể có **At safepoint** đáng kể mà **không có GC pause work**.

### 3.3. Leaving safepoint chưa phải toàn bộ thời gian request phục hồi

VM hoàn tất handoff cho application threads không đảm bảo mọi thread được OS lên lịch thực thi ngay lập tức. CPU contention, ready queue và business code còn lại có thể kéo request ra xa mốc JVM báo `Total`.

Do đó **total safepoint wall time** khác **độ trễ tăng thêm do user/client quan sát**.

## 4. Mô hình toán học: chỉ cộng những khoảng cùng phạm vi

Nếu mọi mốc trên một monotonic clock:

~~~text
TTSP              = t_safe - t_request
GC_work_elapsed   = t_work_end - t_safe   (mô hình GC duy nhất đơn giản)
At_safepoint      = t_resume - t_safe
Total_safepoint   = t_resume - t_request
Request_latency   = t_response - t_request_start
~~~

Trong mô hình này, At-safepoint có thể lớn hơn `GC_work_elapsed` vì overhead sau khi GC algorithm hoàn tất. Request latency có thể gồm processing, queueing, I/O và những pauses khác.

**Không thể suy rộng:** một concurrent GC cycle có nhiều pause hoặc work song song không thể quy về đúng một `t_safe` và một `t_work_end`. Không được cộng các durations của nhiều GC worker threads thành elapsed duration khi chúng chạy đồng thời; đó có thể là **CPU time**.

### Ví dụ con số giả định

| Đại lượng | Giá trị |
| --- | ---: |
| VM yêu cầu safepoint | 4.0 ms từ lúc request bắt đầu |
| Thread cuối tới trạng thái an toàn | 6.5 ms |
| GC work kết thúc | 13.0 ms |
| JVM cho phép Java tiếp tục | 14.0 ms |
| Request trả response | 23.5 ms |

Kết quả tính ra TTSP = **2.5 ms**, GC work = **6.5 ms**, At-safepoint = **7.5 ms**, Total-safepoint = **10.0 ms**, Request latency = **23.5 ms**. Đây không phải các giá trị “không khớp”; chúng là những khoảng đo khác nhau.

## 5. Chương trình Java 17 kiểm tra phép tính một cách xác định

Tạo file **`PauseBudgetDemo.java`**:

~~~java
import java.util.Locale;

public final class PauseBudgetDemo {
    static String ms(long micros) {
        return String.format(Locale.ROOT, "%.1f ms", micros / 1000.0);
    }

    public static void main(String[] args) {
        // Các mốc giả lập đều có đơn vị microseconds.
        long requestStart = 0;
        long safepointRequested = 4_000;
        long allThreadsSafe = 6_500;
        long gcWorkFinished = 13_000;
        long threadsResumed = 14_000;
        long requestFinished = 23_500;

        System.out.println("sync=" +
                ms(allThreadsSafe - safepointRequested));
        System.out.println("gcWork=" +
                ms(gcWorkFinished - allThreadsSafe));
        System.out.println("atSafepoint=" +
                ms(threadsResumed - allThreadsSafe));
        System.out.println("totalSafepoint=" +
                ms(threadsResumed - safepointRequested));
        System.out.println("requestLatency=" +
                ms(requestFinished - requestStart));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 PauseBudgetDemo.java
java PauseBudgetDemo
~~~

**Stdout đã biên dịch/chạy đối chiếu thực tế (JDK 24, target Java 17):**

~~~text
sync=2.5 ms
gcWork=6.5 ms
atSafepoint=7.5 ms
totalSafepoint=10.0 ms
requestLatency=23.5 ms
~~~

Điểm học tập:

1. `sync` là độ trễ phối hợp safepoint, **không tự là thời gian GC algorithm**.
2. `gcWork` đo một vùng work giả định duy nhất; không phải CPU time tổng của nhiều GC workers.
3. `atSafepoint` = 7.5 ms, lớn hơn GC work 1.0 ms do overhead giả định.
4. `totalSafepoint` = 10 ms cộng giai đoạn phối hợp với giai đoạn VM ở safepoint.
5. Request latency = 23.5 ms vì ngoài khoảng safepoint còn business processing/wait.

**Đây là chương trình giải tích các timestamps giả lập, không phải Java API đọc thời gian safepoint thực tế.** Để quan sát JVM thật, phải dùng logs/JFR ở các mục sau.

## 6. Stop-the-world trong các collector phổ biến

### Serial GC và Parallel GC

- Serial collector thực hiện những collection pauses cần dừng Java mutators; nó dùng ít GC worker hơn các collector song song.
- Parallel GC có thể sử dụng nhiều GC workers để thu gom **trong một STW pause**. Vì hoạt động song song, **tổng CPU time** của GC workers có thể **lớn hơn** wall-clock elapsed pause.
- Khi GC log ghi `User`, `Sys`, `Real` (tùy collector/level), `Real` phản ánh elapsed wall-clock theo phạm vi event, không giống phép cộng CPU time của nhiều cores.
- Một GC pause ngắn nhưng xảy ra thường xuyên vẫn có thể ảnh hưởng throughput; một pause hiếm và dài có thể ảnh hưởng tail latency.

### G1 GC

G1 dùng các evacuation pauses, đồng thời có nhiều bước concurrent như concurrent marking. Trên HotSpot/JDK 17, tùy workload bạn có thể thấy young/mixed pauses, remark/cleanup phases hoặc failure-related full collections.

**Không gọi toàn bộ thời gian concurrent marking là “application stopped”.** Java application có thể chạy trong phần lớn concurrent cycle. Đồng thời, concurrent GC vẫn có thể cạnh tranh CPU/memory bandwidth làm throughput/latency thay đổi mà không phải STW.

`-XX:MaxGCPauseMillis` là một **mục tiêu tuning tương ứng**, không phải hard deadline cho mọi GC event, safepoint hoặc request p99.

### ZGC và Shenandoah

Các concurrent low-latency collectors tìm cách dời nhiều GC work ra khỏi global STW và giảm những pauses cần thiết, nhưng không nên tuyên bố chúng **không bao giờ STW** hoặc không có operation safepoint khác.

Mức hỗ trợ, collector phases và flags khác nhau giữa JDK builds/versions; ví dụ một số distribution Java 17 không đóng gói Shenandoah. Hãy kiểm tra `java -version`, các flags và collector đang dùng trước khi so sánh.

### Concurrent GC có thể làm chậm dù pause log nhỏ

Nếu concurrent threads của collector dùng nhiều cores và memory bandwidth, business threads có thể chạy chậm hơn ngay cả khi stop interval ngắn. Khi p99 cao nhưng safepoint total thấp, điều tra **CPU contention, allocator pressure, work queues và system throttling** thay vì kết luận GC chắc chắn không liên quan.

## 7. Bài thực hành Java 17 tạo GC log và safepoint log thực tế

Tạo file **`GcTraceLab.java`**:

~~~java
import java.lang.ref.Reference;

public final class GcTraceLab {
    public static void main(String[] args) {
        byte[][] recent = new byte[4][];
        long allocated = 0;

        for (int i = 0; i < 240; i++) {
            recent[i % recent.length] = new byte[256 * 1024];
            allocated += recent[i % recent.length].length;

            if (i % 60 == 0) {
                System.out.println("phase=" + (i / 60));
            }
        }

        System.out.println("allocatedMiB=" +
                (allocated / (1024 * 1024)));

        Reference.reachabilityFence(recent);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 GcTraceLab.java
~~~

Với **HotSpot** và Bash/Linux/macOS, chạy bằng heap 32 MiB, Serial GC, ghi log vào file:

~~~bash
java -Xms32m -Xmx32m -XX:+UseSerialGC \
  '-Xlog:gc=info,safepoint=info:file=gc-safepoint.log:uptime,level,tags' \
  GcTraceLab
~~~

Trong PowerShell trên Windows, dùng một dòng:

~~~powershell
java -Xms32m -Xmx32m -XX:+UseSerialGC '-Xlog:gc=info,safepoint=info:file=gc-safepoint.log:uptime,level,tags' GcTraceLab
~~~

**Stdout của chương trình trong lần chạy bình thường:**

~~~text
phase=0
phase=1
phase=2
phase=3
allocatedMiB=60
~~~

Chương trình đã được **biên dịch bằng `javac --release 17` và chạy trên JDK 24** với các flags này, stdout đúng 5 dòng. Tổng phân bổ lũy kế = 240 × 256 KiB = 60 MiB; **không có nghĩa giữ đồng thời 60 MiB**, vì mảng `recent` có 4 slots liên tục thay bằng mảng mới.

**Các con số VM log không cố định:** số lần GC, loại pause, heap occupancy và durations tùy JDK, máy, collector và lần chạy. Việc ép Serial GC và heap nhỏ làm log dễ quan sát, không biến thời gian GC thành một kết quả xác định theo Java Specification.

### Một cặp GC và safepoint log quan sát thực tế

Trong một lần chạy JDK 24 đã nêu, file log có cặp:

~~~text
[0.032s][info][gc] GC(0) Pause Young (Allocation Failure) 9M->2M(30M) 0.496ms
[0.032s][info][safepoint] Safepoint "SerialCollectForAllocation", Time since last: 16604300 ns, Reaching safepoint: 7500 ns, At safepoint: 573500 ns, Leaving safepoint: 1400 ns, Total: 582400 ns
~~~

Phân tích:

- `GC(0)` cùng cause `Allocation Failure` gắn với một young collection cần STW.
- GC summary ghi **0.496 ms** theo phạm vi timer của GC summary.
- Safepoint line ghi `Reaching = 7500 ns` (**0.0075 ms**), `At = 573500 ns` (**0.5735 ms**), `Leaving = 1400 ns` (**0.0014 ms**), Total = **582400 ns = 0.5824 ms**.
- Trong event này, total safepoint **không bằng** GC summary duration; các timers bao phủ các phần khác nhau, không chứng minh metric bị hỏng.
- Đây là **một mẫu dữ liệu của HotSpot 24**, không phải format hoặc kết quả cố định của tất cả JDK 17, G1, ZGC hay một process production khác.

Cách đọc đúng: quan sát các **phase intervals liên hệ trong cùng timeline**; không lấy GC id bất kỳ ghép với safepoint ở thời điểm khác.

## 8. Công cụ `-Xlog`: GC và safepoint là hai nguồn đo

Unified Logging của HotSpot Java 17+:

~~~bash
java -Xlog:gc=info,safepoint=info Main
~~~

`Main` là **tên main class minh họa**, cần thay bằng class thực. Dùng `java -Xlog:help` để xem các tags/levels mà bản JVM cụ thể hỗ trợ.

| Cấu hình | Bạn quan sát được gì? |
| --- | --- |
| `-Xlog:gc=info` | GC cause/type, event summaries và một số elapsed pauses |
| `-Xlog:safepoint=info` | Safepoint operation name, reaching/at/leaving/total khi có trong format phiên bản đó |
| `-Xlog:gc*=debug` | Nhiều thông tin GC phases và subtags hơn, log có thể rất lớn |
| `-Xlog:safepoint=debug` | Chi tiết safepoint coordination ở mức cao hơn nếu JVM hỗ trợ |
| `-Xlog:gc+cpu=info` | Một số số liệu GC user/sys/real CPU nếu tag/event hỗ trợ |
| `-Xlog:help` | Xác minh tags, decorators và cú pháp trên runtime thật |

Một dòng GC summary có thể có format:

~~~text
[0.123s][info][gc] GC(7) Pause Young (...) 64M->19M(128M) 1.234ms
~~~

Dòng trên là **minh họa**, không phải stdout cố định. Đừng coi `1.234ms` là toàn bộ thời gian mọi request bị dừng, hay giả định GC events gồm chỉ một pause.

### Các bẫy khi đối chiếu

1. Đơn vị khác nhau: GC pause có thể in **ms**, safepoint fields có thể in **ns**; **1 ms = 1,000,000 ns**.
2. Concurrent phases chạy chồng lắp với Java work; không cộng wall time của chúng vào STW total.
3. Worker phase durations có thể chạy song song; **tổng work time** không bằng elapsed wall time.
4. GC event và safepoint event có identifiers khác nhau; ghép theo **operation cause, timestamp và timeline**, không ghép bừa theo thứ tự dòng nếu nhiều activities.
5. GC logging chi tiết cũng tạo overhead; benchmark cần cố định logging configuration giữa các lần.
6. `-Xlog` và GC tuning flags là HotSpot-specific tools; JVM khác có logging interface khác.
7. Dòng `GC Pause` không bao trọn công việc VM ở safepoint, và safepoint có thể không liên quan GC.

## 9. JFR, JMC và phân tích theo cùng trục thời gian

**Java Flight Recorder (JFR)** cung cấp events có timestamps và durations, hữu ích hơn việc chỉ nhìn một con số GC. Tên events hoặc threshold tùy cấu hình JDK, nhưng những nhóm thường quan tâm gồm:

- `jdk.GarbageCollection` và `jdk.GCPhasePause` cho GC events/phases.
- Safepoint-related events như `jdk.SafepointBegin`/`jdk.SafepointEnd` khi khả dụng và được bật.
- Một số VM operation, class loading, compilation, allocation và thread scheduling/park/monitor events.
- CPU, I/O và thread stacks giúp xác định các nguyên nhân ngoài GC.

**Không mặc định mọi event được bật bởi recording settings mặc định.** Phải kiểm tra JFR event settings của JDK đang chạy và biết duration field đo gì.

### Thu thập JFR

Khi khởi động application:

~~~bash
java '-XX:StartFlightRecording=filename=latency.jfr,duration=60s,settings=profile' -jar app.jar
~~~

`app.jar` chỉ là artifact minh họa, phải thay bằng file thực.

Khi đã có JVM PID thực, dùng `jcmd`:

~~~text
jcmd PID JFR.start name=Latency settings=profile
jcmd PID JFR.dump name=Latency filename=latency.jfr
jcmd PID JFR.stop name=Latency
~~~

Thay `PID` bằng số process ID; các lệnh cần quyền OS/JVM phù hợp. Có thể xem recording bằng JDK Mission Control (JMC) hoặc `jfr` CLI:

~~~bash
jfr summary latency.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause latency.jfr
~~~

JFR data có thể chứa method names, stack traces và thông tin nội bộ ứng dụng; hãy giữ file ở nơi được kiểm soát quyền truy cập.

### Vì sao cần app tracing đi cùng JFR?

Giả sử request mất 200 ms, trong khoảng đó có safepoint 4 ms nhưng 160 ms đang chờ database. Chỉ thấy GC 4 ms trùng thời điểm **không đủ** để quy toàn bộ request latency cho GC. Khi có request spans và JFR, bạn mới xác định critical path nào bị chặn.

## 10. Phân biệt GC CPU time, elapsed time và tổng application pause

**GC CPU time**: thời gian CPU mà GC threads tiêu thụ (tùy cách thống kê), có thể tổng hợp từ nhiều cores/threads. Khi bốn GC workers cùng chạy 5 ms CPU, tổng GC user CPU có thể gần **20 ms** trong khi elapsed pause xấp xỉ **5 ms** cộng overhead.

**GC wall elapsed time**: độ dài theo đồng hồ thực của một GC event, pause hoặc concurrent cycle, phụ thuộc loại event. Elapsed của concurrent cycle **không bằng** STW.

**Safepoint total elapsed**: từ mốc JVM yêu cầu tới completion/release theo timer của log, có thể bao gồm reaching và overhead, và có thể là **một VM operation không phải GC**.

**Application stopped time**: thời gian Java mutator progress bị dừng/giới hạn bởi những safepoints và hoạt động VM, được công cụ ghi theo phạm vi riêng.

**Request end-to-end latency**: gồm application compute, locks, queuing, network, downstream services, scheduling, concurrent CPU contention và những STW intervals nằm trên đường xử lý.

Những metric này không được dùng thay thế lẫn nhau.

| Câu hỏi | Số đo cần xem |
| --- | --- |
| GC work pause một event bao lâu? | GC pause summary/phase event |
| Đợi tất cả threads tới safe states bao lâu? | `Reaching safepoint`, TTSP |
| JVM ở global safepoint bao lâu? | `At safepoint` và `Total` |
| GC workers tốn bao nhiêu CPU? | GC user/sys CPU times |
| Người dùng cảm thấy chậm bao lâu? | Request latency tracing/p99 |
| Concurrent GC ảnh hưởng CPU/throughput? | CPU utilization, allocation rate, concurrent phases |
| Vì sao request pause trùng mốc GC? | Correlated GC + safepoint + JFR + request spans |

### P99 không thể suy ra bằng tổng GC time chia tổng uptime

Ví dụ tổng 300 ms STW trong một phút không nói chính xác p99 latency tăng mấy ms. Một pause 100 ms trúng request critical path có thể tác động tail latency rất khác 100 pauses x 1 ms phân bố rải rác. Cần histogram/distribution và khả năng overlap với requests.

## 11. Những nguyên nhân safepoint không phải GC

Không phải global safepoint nào cũng để thu gom rác. Trong HotSpot, tùy JVM version và cơ chế:

- Một số operations liên quan deoptimization hoặc management of compiled code.
- Một số class redefinition/instrumentation/tooling actions.
- Một số VM runtime maintenance tasks.
- Một số diagnostics cần nhất quán trên nhiều Java stacks/threads.

Nhiều operations hiện đại có thể dùng **thread-local handshake**, vì vậy không khẳng định rằng **mọi thread dump, mọi stack inspection hoặc mọi deoptimization** đều global STW. Hãy đọc **safepoint operation name** và JFR events của bản JVM thật.

Nếu safepoint 20 ms không thuộc GC, nó vẫn có thể ảnh hưởng throughput/latency, nhưng không được ghi nhận là “GC algorithm mất 20 ms”.

## 12. Chẩn đoán TTSP dài, GC dài và request latency dài

Một checklist phân nhánh ngắn:

**Trường hợp A — `Reaching safepoint` cao, GC summary thấp.** Điều tra phản hồi safepoint polls, native/JNI transitions, scheduling và CPU quota. Đừng vội tăng số GC threads.

**Trường hợp B — `At safepoint` cao, reaching thấp.** Xác định operation name. Nếu là GC, xem collector phases/root scanning, heap pressure, reference processing và evacuation; nếu là VM op khác, chuyển hướng tới operation tương ứng.

**Trường hợp C — GC CPU cao hơn GC wall elapsed.** Có thể do GC workers chạy parallel hoặc concurrent; không tính CPU user như elapsed pause.

**Trường hợp D — GC pause thấp, p99 vẫn cao.** Kiểm tra CPU contention do concurrent GC, locks, I/O, TCP/DB latency, OS scheduling, queue depth và safepoints khác.

**Trường hợp E — tổng safepoint thấp nhưng service throughput giảm.** Concurrent GC work cạnh tranh CPU/memory bandwidth; allocator churn và object allocation rate có thể gây pressure. Cần xem GC frequency và CPU utilization.

**Trường hợp F — một request rất chậm trùng nhiều safepoints.** Đối chiếu từng interval và request critical path, tránh cộng các khoảng trùng nhau hoặc cộng cả concurrent cycle.

### Một event mô phỏng TTSP gây chậm

~~~text
Reaching safepoint  = 41 ms
At safepoint        =  2 ms
Leaving safepoint   =  1 ms
Total               = 44 ms

GC work summary có thể chỉ ~1.6 ms.
~~~

Đây là **tình huống số giả định**. Dù GC algorithm chỉ hơn 1 ms, tổng khoảng VM safepoint có thể dài vì phối hợp threads. Không kết luận JVM đã “pause 44ms chỉ để quét object”.

### Một event mô phỏng non-GC safepoint

~~~text
Operation = VM maintenance (không phải GC)
Reaching  = 1 ms
At        = 30 ms
Leaving   = 1 ms
Total     = 32 ms
~~~

Đây cũng là **mô phỏng**, không phải tên event/format exact JDK. Dòng 32 ms có thể ảnh hưởng application latency nhưng không nên cộng vào **GC pause work**.

## 13. Những nhận định sai thường gặp

1. **“GC time = mọi thời gian Java application dừng.”** Sai; phải đọc phạm vi timer.
2. **“Safepoint chính là GC.”** Sai, VM có những safepoints vì operations khác.
3. **“GC concurrent toàn bộ thời gian là STW.”** Sai.
4. **“Stop-the-world làm mọi native OS thread dừng.”** Sai.
5. **“Tất cả Java threads dừng đúng cùng một nanosecond.”** Sai; có giai đoạn reaching/synchronization.
6. **“GC Pause 1 ms thì request p99 bị tăng tối đa 1 ms.”** Sai.
7. **“At safepoint không có overhead.”** Sai.
8. **“TTSP dài chứng minh GC mark chậm.”** Sai, GC work có thể chưa bắt đầu.
9. **“GC CPU time giống wall-clock pause.”** Sai với parallel/concurrent work.
10. **“Concurrent GC không ảnh hưởng latency.”** Sai, có cạnh tranh CPU/memory bandwidth.
11. **“ZGC không cần safepoint nào trong bất kỳ trường hợp nào.”** Không có bảo đảm như vậy.
12. **“MaxGCPauseMillis là giới hạn cứng của request latency.”** Sai.
13. **“Cộng tất cả GC worker thread durations là STW elapsed.”** Sai.
14. **“Một GC summary đủ giải thích HTTP 500 ms.”** Sai.
15. **“Có một safepoint thì mọi requests chậm đúng toàn bộ thời lượng đó.”** Sai, còn critical path.
16. **“Có GC concurrent 500 ms thì ứng dụng dừng 500 ms.”** Sai.
17. **“GC log và safepoint log phải có duration giống hệt.”** Sai.
18. **“Safepoint poll là câu lệnh Java có thể gọi thủ công.”** Sai.
19. **“Dòng Total 582400 ns bằng 582.4 ms.”** Sai: bằng 0.5824 ms.
20. **“Nếu GC không xuất hiện trong log, chắc không có nguyên nhân JVM nào khác.”** Sai.

## 14. Tự kiểm tra và đáp án

1. GC work 7 ms, reaching 3 ms, overhead còn lại 2 ms. Trong mô hình không trùng, total safepoint? **12 ms**.
2. G1 concurrent marking 400 ms, hai pauses 5 và 3 ms. Application có dừng 400 ms không? **Không**, concurrent phase không đồng nghĩa STW.
3. Bốn GC workers chạy đồng thời mỗi worker 5 ms CPU. Total CPU có thể ~20 ms, wall elapsed ~5 ms? **Có**, cộng overhead.
4. VM maintenance safepoint 12 ms có ghi là GC pause 12 ms không? **Không**.
5. Safepoint reaching 20 ms và GC work 1 ms có chứng minh GC algorithm tốn 21 ms không? **Không**.
6. Request 150 ms chồng lắp safepoint 2 ms có thể quy toàn bộ 150 ms cho GC không? **Không**.
7. Lệnh HotSpot cơ bản xem GC/safepoint? **`-Xlog:gc=info,safepoint=info`**.
8. 582400 nanoseconds bằng bao nhiêu milliseconds? **0.5824 ms**.
9. Mọi thread inspection hiện đại đều global safepoint? **Không**, có targeted handshakes.
10. Collector concurrent có thể gây CPU contention dù pause nhỏ? **Có**.
11. `MaxGCPauseMillis` là hard bound p99 latency? **Không**.
12. `System.gc()` luôn buộc STW GC ngay lập tức? **Không**; phụ thuộc VM/collector/flags.
13. Vì sao GC CPU user có thể cao hơn GC elapsed? **Song song nhiều GC workers**.
14. Nếu total safepoint cao hơn GC pause, cần xem gì? **Reaching/At/Leaving, operation name, timer boundary**.
15. Nếu safepoint operation không phải GC, có bỏ qua khi điều tra latency? **Không**, nhưng phân loại đúng là non-GC.

## 15. Nguồn tham khảo Java 17 và HotSpot

- Oracle JDK 17 `java` tool: Unified JVM Logging, `-Xlog`, tags và decorators: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 Garbage Collection Tuning Guide (Serial, Parallel, G1, low-latency collector): https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17 Diagnostic Tools (JFR/JMC, GC pause và troubleshooting): https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- JDK 17 `jcmd`, JFR.start/JFR.dump/JFR.stop: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- JDK 17 `jfr` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- JDK 17 Java Flight Recorder module documentation: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- JVM Specification 17, Runtime Data Areas: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5

**Kết luận:** **GC** là quá trình thu gom bộ nhớ; **STW** là khoảng application Java bị dừng/phối hợp; **safepoint** là cơ chế VM đưa các Java threads vào trạng thái an toàn khi cần. Số **GC pause** không tự bằng **total safepoint**, **GC CPU** không bằng **elapsed wall time**, và **request latency** còn chứa những nguyên nhân khác. Cần đọc đồng thời **GC logs**, **safepoint logs**, **JFR events** và **application tracing** theo cùng timeline, event, cause và đơn vị trước khi chẩn đoán hoặc tối ưu.
