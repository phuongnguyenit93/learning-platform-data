# Đo và chẩn đoán thời gian GC pause

**GC pause time** là khoảng thời gian JVM tạm dừng các application thread để thực hiện một giai đoạn garbage collection cần stop-the-world (STW). Trong thời gian pause, request và worker thread của ứng dụng có thể không tiến triển, làm tăng latency hoặc khiến request vượt SLO.

Để chẩn đoán pause time, cần trả lời bốn câu hỏi:

1. Có bao nhiêu pause trong khoảng thời gian quan sát?
2. Mỗi pause kéo dài bao lâu, đặc biệt ở P95, P99 và mức lớn nhất?
3. Pause thuộc loại GC nào, do nguyên nhân gì và pha nào chiếm nhiều thời gian?
4. Pause có trùng với latency spike của ứng dụng hay không?

Các công cụ chính trong JDK:

- **JFR:** phân tích phân phối pause, GC phase, heap trước/sau và timeline.
- **Unified GC logging:** ghi từng lần GC cùng nguyên nhân, heap size, duration và safepoint.
- **jstat:** theo dõi số lần collection và thời gian tích lũy theo chu kỳ.
- **GarbageCollectorMXBean:** đọc collection count và collection time từ Java code.
- **JDK Mission Control (JMC):** mở recording, lọc event và đối chiếu với workload.

## 1. Phân biệt GC pause, GC cycle và concurrent work

Không phải toàn bộ thời gian garbage collection đều là pause.

### Stop-the-world pause

Trong STW pause, các application thread bị dừng tại safepoint trong khi JVM thực hiện một giai đoạn GC. Ví dụ với G1:

- Pause Young (Normal).
- Pause Young (Concurrent Start).
- Pause Young (Mixed).
- Pause Remark.
- Pause Cleanup.
- Pause Full.

Một pause có thể chỉ kéo dài vài millisecond, nhưng nếu xảy ra thường xuyên hoặc có tail latency lớn thì vẫn ảnh hưởng tới request.

### Concurrent GC phase

Một số collector thực hiện công việc GC đồng thời với application thread. Ví dụ G1 có concurrent marking và các pha concurrent khác. ZGC và Shenandoah cũng thực hiện phần lớn công việc trong khi ứng dụng tiếp tục chạy.

Concurrent phase có thể kéo dài hàng trăm millisecond hoặc lâu hơn mà không tương đương một STW pause cùng thời lượng. Vì vậy không lấy tổng duration của mọi GC cycle làm tổng pause time.

### GC cycle và pause event

Một GC cycle có thể gồm nhiều pha concurrent và nhiều pause. Ví dụ G1 marking cycle có thể có một pause khởi động, phần concurrent marking, pause remark và pause cleanup.

Trong JFR:

- jdk.GarbageCollection mô tả một collection event.
- jdk.GCPhasePause mô tả pause phase.
- jdk.GCPhasePauseLevel1, Level2 và các level khác mô tả các phase con.
- jdk.GCPhaseConcurrent mô tả phase concurrent.
- jdk.GCHeapSummary ghi heap summary trước hoặc sau GC.

Do đó số lượng jdk.GarbageCollection có thể khác số lượng jdk.GCPhasePause. Một collection có thể chứa nhiều pause event.

## 2. Những chỉ số pause time cần theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Pause count | Số lần STW pause trong khoảng quan sát |
| Total pause time | Tổng duration của các pause |
| Minimum | Pause ngắn nhất |
| Median / P50 | Một nửa số pause ngắn hơn hoặc bằng giá trị này |
| Average | Thời gian trung bình của pause |
| P90 / P95 | Tail latency của pause |
| P99 / P99.9 | Pause ở phần đuôi phân phối |
| Maximum | Pause dài nhất |
| GC cause | Nguyên nhân collection được kích hoạt |
| Heap before / after | Heap được sử dụng trước và sau collection |

### Vì sao cần xem percentile?

Average có thể che giấu một vài pause rất dài.

Ví dụ:

- 990 pause kéo dài 2 ms.
- 10 pause kéo dài 200 ms.

Average có thể vẫn tương đối thấp, nhưng 10 pause dài có thể làm request vượt timeout hoặc p99 latency tăng mạnh.

Khi điều tra production, hãy xem P95, P99 và maximum cùng với pause count. So sánh các giá trị này với latency SLO của ứng dụng.

### Pause fraction

Có thể ước lượng tỷ lệ thời gian bị pause trong một recording:

\[
Pause\ fraction = \frac{Total\ pause\ time}{Recording\ wall\ time} \times 100
\]

Ví dụ recording dài 8 giây, tổng pause là 45.4 ms:

\[
\frac{45.4}{8000} \times 100 \approx 0.57\%
\]

Chỉ số này giúp so sánh mức pause tổng thể giữa các recording có cùng cách đo. Nó không thay thế P99 hoặc maximum: một pause duy nhất kéo dài 200 ms vẫn có thể làm hỏng một request dù pause fraction toàn cửa sổ thấp.

## 3. Đo pause time bằng Java Flight Recorder

JFR là công cụ phù hợp để phân tích pause distribution và GC phase.

Bắt đầu recording khi JVM khởi động:

~~~bash
java \
    -XX:StartFlightRecording=filename=gc.jfr,settings=profile,duration=60s,dumponexit=true \
    -jar app.jar
~~~

Hoặc bắt đầu recording trên JVM đang chạy:

~~~bash
jcmd -l

jcmd 12345 JFR.start name=GC settings=profile duration=60s filename=gc.jfr
~~~

Thay 12345 bằng PID của JVM cần theo dõi.

Kiểm tra recording:

~~~bash
jcmd 12345 JFR.check
~~~

Dump snapshot nếu recording vẫn đang chạy:

~~~bash
jcmd 12345 JFR.dump name=GC filename=gc-snapshot.jfr
~~~

Dừng recording:

~~~bash
jcmd 12345 JFR.stop name=GC
~~~

Các lệnh JFR trên cần Attach hoạt động và user có quyền truy cập process. Với production, chọn khoảng ghi phù hợp và đánh giá overhead của cấu hình profile.

### Xem summary

~~~bash
jfr summary gc.jfr
~~~

Tìm các event:

- jdk.GarbageCollection.
- jdk.GCPhasePause.
- jdk.GCPhasePauseLevel1.
- jdk.GCHeapSummary.
- jdk.GCPhaseConcurrent.

Summary cho biết event count và dung lượng. Nếu không có GC pause event, kiểm tra recording duration, settings, collector và thời điểm workload trước khi kết luận JVM không có pause.

### Xem phân phối pause

~~~bash
jfr view gc-pauses gc.jfr
~~~

View này tổng hợp:

- Total Pause Time.
- Number of Pauses.
- Minimum Pause Time.
- Median Pause Time.
- Average Pause Time.
- P90, P95, P99 và P99.9.
- Maximum Pause Time.

Ví dụ kết quả từ recording 8 giây trên JDK 24.0.2:

~~~text
GC Pauses
---------

Total Pause Time: 45.4 ms

Number of Pauses: 80

Minimum Pause Time: 0.409 ms

Median Pause Time: 0.517 ms

Average Pause Time: 0.568 ms

P90 Pause Time: 0.766 ms

P95 Pause Time: 0.843 ms

P99 Pause Time: 2.60 ms

P99.9% Pause Time: 2.60 ms

Maximum Pause Time: 2.60 ms
~~~

Đây là kết quả của workload lab tạo allocation liên tục với heap 32–64 MB và G1. Recording khác sẽ có pause count và percentile khác.

### Xem từng collection

~~~bash
jfr view gc gc.jfr
~~~

Bảng tổng hợp có thể hiển thị:

- GC ID.
- Start time.
- GC type.
- Heap before GC.
- Heap after GC.
- Longest pause.

Dùng bảng này để tìm collection có pause dài và xem heap có giảm sau GC hay không.

### Xem phase nào chiếm thời gian

~~~bash
jfr view gc-pause-phases gc.jfr
~~~

Ví dụ kết quả:

~~~text
GC Pause Phases

Type              Name                     Average    P95    Longest Count   Total
----------------- ------------------------ --------- ------  -------- ----- -------
GC Phase Pause    GC Pause                  0.568 ms 0.843 ms 2.60 ms    80  45.4 ms
GC Phase Pause L1 Notify Soft/WeakReferences ...
GC Phase Pause L1 Notify PhantomReferences ...
~~~

Nếu một phase cụ thể chiếm phần lớn pause duration, cần xem collector, heap layout và nguyên nhân của phase đó. Không nên điều chỉnh GC flag chỉ dựa vào tên phase; cần đối chiếu với event và workload.

### Xem CPU time của GC

~~~bash
jfr view gc-cpu-time gc.jfr
~~~

View này tổng hợp CPU user time, system time, wall-clock time và GC count theo dữ liệu recording. CPU time của GC không đồng nghĩa với STW pause time: collector có thể dùng CPU trong concurrent phase khi ứng dụng vẫn đang chạy.

### In event để xem chi tiết

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary gc.jfr
~~~

Một event có thể có dạng:

~~~text
jdk.GCPhasePause {
  startTime = 20:21:49.726
  duration = 2.74 ms
  gcId = 1
  name = "GC Pause"
  eventThread = "VM Thread"
}

jdk.GarbageCollection {
  startTime = 20:21:49.726
  duration = 2.74 ms
  gcId = 1
  name = "G1New"
  cause = "G1 Humongous Allocation"
  sumOfPauses = 2.74 ms
  longestPause = 2.74 ms
}
~~~

Các field quan trọng:

- startTime: thời điểm bắt đầu.
- duration: thời lượng event.
- gcId: ID collection liên quan.
- name: loại collection hoặc phase.
- cause: nguyên nhân collection.
- sumOfPauses: tổng pause được ghi cho collection.
- longestPause: pause dài nhất trong collection.

Event GCHeapSummary có when = Before GC hoặc After GC và heapUsed tương ứng. Dùng hai event này để so sánh heap trước/sau.

## 4. Ghi GC log bằng Unified Logging

Unified Logging là cách chuẩn để ghi GC log trên JDK 9 trở lên. Với JDK 24, dùng tùy chọn -Xlog thay vì dựa vào các flag logging cũ.

Bật GC và safepoint log:

~~~bash
java \
    -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
    -jar app.jar
~~~

Ý nghĩa:

- gc*: các log tag liên quan tới garbage collection.
- safepoint: thông tin về safepoint và thời gian dừng thread.
- file=gc.log: ghi ra file.
- time: timestamp theo thời gian thực.
- uptime: thời gian kể từ khi JVM khởi động.
- level: mức log.
- tags: nhóm tag tạo ra dòng log.

Có thể xoay vòng file để tránh log tăng vô hạn:

~~~bash
java \
    -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
    -jar app.jar
~~~

Cú pháp xoay vòng đã được xác nhận trên JDK 24.0.2. Điều chỉnh số file và dung lượng theo chính sách lưu log.

### Đọc một dòng GC log

Ví dụ:

~~~text
[2026-11-10T20:25:06.973+0700][0.228s][info][gc]
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->4M(34M) 2.726ms
~~~

Diễn giải:

- Timestamp: thời điểm log.
- 0.228s: uptime của JVM tại thời điểm đó.
- GC(0): ID collection.
- Pause Young: loại pause.
- G1 Evacuation Pause: nguyên nhân/loại hoạt động G1.
- 18M->4M: heap used trước và sau collection.
- (34M): heap capacity tại thời điểm đó.
- 2.726ms: thời gian pause được ghi trong dòng kết thúc.

Đọc cặp dòng bắt đầu/kết thúc của cùng GC ID để xác định duration. Không cộng duration của các dòng phase con vào pause tổng nếu chúng đã nằm trong pause tổng, vì sẽ đếm trùng.

### Các mẫu log G1 thường gặp

| Log text | Ý nghĩa tổng quát |
|---|---|
| Pause Young (Normal) | Young collection bình thường |
| Pause Young (Concurrent Start) | Young pause khởi động concurrent marking |
| Pause Young (Mixed) | Collection có cả vùng young và old |
| Pause Remark | STW remark trong marking cycle |
| Pause Cleanup | STW cleanup ngắn |
| Pause Full | Full GC, thường cần điều tra kỹ |
| Concurrent Mark Cycle | Pha marking concurrent |
| Evacuation Failure | G1 không evacuation được một phần object như dự kiến |
| To-space exhausted | Không đủ vùng đích cho evacuation |
| G1 Humongous Allocation | Allocation object lớn kích hoạt hoạt động GC |

Tên và thứ tự phase phụ thuộc collector và phiên bản JVM. Đọc log thực tế của collector đang chạy thay vì áp dụng nguyên xi diễn giải G1 cho ZGC hoặc Shenandoah.

## 5. GC pause và safepoint không hoàn toàn giống nhau

GC pause là khoảng dừng ứng dụng để thực hiện một pha GC. Safepoint là cơ chế JVM đưa các Java thread tới trạng thái an toàn để thực hiện một số thao tác nội bộ.

Có những safepoint không liên quan trực tiếp tới GC, ví dụ một số VM operation, deoptimization hoặc thao tác quản lý runtime.

Bật cả hai nhóm log:

~~~bash
-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags
~~~

Dòng safepoint có thể cho biết:

- Reaching safepoint: thời gian chờ các thread tới safepoint.
- At safepoint: thời gian thực hiện thao tác khi đã dừng thread.
- Leaving safepoint: thời gian đưa thread rời safepoint.
- Total: tổng thời gian của safepoint operation.

Nếu latency spike xảy ra nhưng không có GC pause tương ứng, kiểm tra safepoint log để xem JVM có dừng thread vì một VM operation khác hay không.

Không cộng toàn bộ safepoint duration vào GC pause time. Hãy phân loại theo operation và đối chiếu timestamp.

## 6. Theo dõi GC bằng jstat

jstat đọc các thống kê JVM từ performance data. Nó hữu ích khi cần xem xu hướng theo chu kỳ mà không phải mở JFR hoặc parse GC log.

### Xem GC utilization

~~~bash
jstat -gcutil 12345 1000 10
~~~

Lệnh lấy 10 mẫu, mỗi mẫu cách nhau 1 giây. Thay 12345 bằng PID.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| S0, S1 | Mức sử dụng survivor space |
| E | Mức sử dụng Eden |
| O | Mức sử dụng old generation |
| M | Mức sử dụng Metaspace |
| CCS | Mức sử dụng compressed class space |
| YGC | Số young GC |
| YGCT | Thời gian young GC tích lũy, giây |
| FGC | Số full GC |
| FGCT | Thời gian full GC tích lũy, giây |
| CGC | Số concurrent GC |
| CGCT | Thời gian concurrent GC tích lũy, giây |
| GCT | Tổng thời gian GC tích lũy, giây |

Ví dụ output:

~~~text
S0     S1     E      O      M     CCS    YGC     YGCT     FGC    FGCT     CGC    CGCT       GCT
-      83.33  0.00   11.82  60.95 15.69     15     0.007     0     0.000     0     0.000     0.007
-      83.33  6.25   11.82  60.95 15.69     22     0.009     0     0.000     0     0.000     0.009
-      83.33  0.00   11.82  60.95 15.69     29     0.012     0     0.000     0     0.000     0.012
~~~

Các cột thời gian là bộ đếm tích lũy. Lấy chênh lệch giữa các mẫu để xem thời gian GC tăng thêm trong cửa sổ quan sát.

jstat không cung cấp pause percentile như JFR. Nó cũng không cho biết đầy đủ từng pause duration hoặc stack/phase. Dùng nó để phát hiện tần suất và xu hướng, sau đó mở GC log hoặc JFR để tìm nguyên nhân.

### Xem GC cause

~~~bash
jstat -gccause 12345 1000 10
~~~

Lệnh bổ sung:

- LGCC: nguyên nhân GC gần nhất.
- GCC: nguyên nhân GC hiện tại hoặc trạng thái hiện tại.

Ví dụ cause có thể là G1 Evacuation Pause hoặc No GC. Giá trị phụ thuộc collector và thời điểm lấy mẫu.

## 7. Đọc collection metrics bằng GarbageCollectorMXBean

Java Management API cung cấp GarbageCollectorMXBean cho từng garbage collector.

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(gc.getName());
    System.out.println(gc.getCollectionCount());
    System.out.println(gc.getCollectionTime());
}
~~~

Các method:

- getName(): tên collector.
- getCollectionCount(): số collection đã hoàn thành.
- getCollectionTime(): thời gian tích lũy trong collection, tính bằng milliseconds.

Giá trị -1 có nghĩa implementation không cung cấp metric đó. Collection count và collection time là bộ đếm tích lũy từ khi JVM khởi động.

**Giới hạn quan trọng:** getCollectionTime() là thời gian collection tích lũy do implementation cung cấp, không phải một bản ghi riêng cho từng STW pause và không cung cấp P95/P99. Với collector có concurrent work, không được mặc định coi giá trị này là tổng STW pause chính xác. Dùng nó để theo dõi xu hướng, còn pause distribution nên lấy từ JFR.

### Tính thời gian tích lũy trong một cửa sổ

Lấy count và time trước/sau một khoảng workload:

~~~java
long countDelta = countAfter - countBefore;
long collectionTimeDelta = timeAfter - timeBefore;
double gcTimeRatio =
        100.0 * collectionTimeDelta / wallTimeMillis;
~~~

Tỷ lệ này là ước lượng collection time so với wall time. Nếu các GC worker chạy song song hoặc collector làm việc concurrent, tổng collection time có thể không tương đương thời gian ứng dụng bị dừng.

## 8. Ví dụ Java 17+: đo collection count và time

Chương trình sau tạo allocation liên tục, chỉ giữ lại tám mảng byte gần nhất để tạo áp lực lên young generation. Nó đọc số liệu từ GarbageCollectorMXBean trước và sau workload.

### GcPauseDemo.java

~~~java
package com.example;

import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

public final class GcPauseDemo {
    private GcPauseDemo() { }

    public static void main(String[] args) throws Exception {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        long countBefore = total(collectors, true);
        long timeBefore = total(collectors, false);
        long wallBefore = System.nanoTime();

        Deque<byte[]> retained = new ArrayDeque<>();
        long end = System.nanoTime() + 8_000_000_000L;
        long allocations = 0;

        while (System.nanoTime() < end) {
            retained.addLast(new byte[256 * 1024]);

            if (retained.size() > 8) {
                retained.removeFirst();
            }

            allocations++;
            Thread.sleep(1);
        }

        long wallAfter = System.nanoTime();
        long countAfter = total(collectors, true);
        long timeAfter = total(collectors, false);

        long gcCount = countAfter - countBefore;
        long gcMillis = timeAfter - timeBefore;
        double wallMillis = (wallAfter - wallBefore) / 1_000_000.0;

        System.out.println("GC demo completed; allocations=" + allocations);
        System.out.println("GC count delta=" + gcCount);
        System.out.println("GC collection time delta ms=" + gcMillis);

        System.out.printf(
                "Approximate cumulative GC time / wall time=%.2f%%%n",
                wallMillis > 0 ? 100.0 * gcMillis / wallMillis : 0.0);

        for (GarbageCollectorMXBean gc : collectors) {
            System.out.println(gc.getName()
                    + " count=" + gc.getCollectionCount()
                    + " timeMs=" + gc.getCollectionTime());
        }
    }

    private static long total(
            List<GarbageCollectorMXBean> beans, boolean count) {
        long total = 0;

        for (GarbageCollectorMXBean bean : beans) {
            long value = count
                    ? bean.getCollectionCount()
                    : bean.getCollectionTime();

            if (value >= 0) {
                total += value;
            }
        }

        return total;
    }
}
~~~

### Biên dịch

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/GcPauseDemo.java
~~~

### Chạy với heap giới hạn

~~~bash
java -Xms32m -Xmx64m \
    -cp build/classes \
    com.example.GcPauseDemo
~~~

Output mẫu đã quan sát trên JDK 24.0.2:

~~~text
GC demo completed; allocations=3788
GC count delta=80
GC collection time delta ms=45
Approximate cumulative GC time / wall time=0.56%
G1 Young Generation count=81 timeMs=47
G1 Concurrent GC count=0 timeMs=0
G1 Old Generation count=0 timeMs=0
~~~

Các bộ đếm và thời gian thay đổi theo JDK, collector, CPU và workload. Chương trình minh họa cách lấy collection metrics; nó không tự cung cấp P99 pause.

## 9. Lab đầy đủ: kết hợp Java, JFR và GC log

Dùng cùng GcPauseDemo để tạo recording và log:

~~~bash
java -Xms32m -Xmx64m \
    -XX:StartFlightRecording=filename=gc-pause.jfr,settings=profile,duration=8s,dumponexit=true \
    -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
    -cp build/classes \
    com.example.GcPauseDemo
~~~

Sau khi chương trình kết thúc, kiểm tra recording:

~~~bash
jfr summary gc-pause.jfr
jfr view gc-pauses gc-pause.jfr
jfr view gc-pause-phases gc-pause.jfr
jfr view gc gc-pause.jfr
~~~

Đọc log:

~~~bash
# Search for pause types and durations
grep -E "Pause Young|Pause Full|Pause Remark|Pause Cleanup" gc.log

# Search for safepoint details
grep -i "safepoint" gc.log
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
Select-String -Path .\gc.log -Pattern 'Pause Young|Pause Full|Pause Remark|Pause Cleanup'
Select-String -Path .\gc.log -Pattern 'Safepoint'
~~~

Kết quả JDK 24.0.2 trong lab:

- Recording dài 8 giây.
- 80 jdk.GarbageCollection events.
- 80 jdk.GCPhasePause events.
- Tổng pause time khoảng 45.4 ms.
- Median pause 0.517 ms.
- P95 pause 0.843 ms.
- P99 pause 2.60 ms.
- Maximum pause 2.60 ms.

Unified GC log cho thấy các pause Young của G1 cùng heap before/after và duration. Các số liệu này là một lần chạy minh họa, không phải ngưỡng chuẩn cho production.

## 10. Phân tích nguyên nhân pause dài

Khi tìm thấy một pause dài, không nên chỉ nhìn duration. Hãy kiểm tra GC cause, heap trước/sau, phase breakdown và allocation rate.

### Young GC xảy ra quá thường xuyên

Dấu hiệu:

- YGC tăng nhanh.
- JFR có nhiều pause Young.
- Eden đầy nhanh.
- Heap sau GC giảm nhưng allocation rate vẫn cao.

Hướng điều tra:

- Tìm allocation hot spot bằng JFR allocation events.
- Kiểm tra object tạm thời được tạo trong vòng lặp.
- Kiểm tra serialization, boxing, collection growth và buffer creation.
- Xem allocation rate và request throughput theo cùng timeline.

Không nhất thiết tăng heap là giải pháp. Nếu ứng dụng tạo quá nhiều object, tăng heap có thể chỉ kéo dài khoảng cách giữa các lần GC mà không giảm tổng allocation.

### Full GC hoặc pause rất dài

Dấu hiệu:

- Log có Pause Full.
- FGC hoặc FGCT tăng.
- JFR có maximum pause lớn.
- Heap sau GC vẫn cao hoặc giảm rất ít.

Kiểm tra:

- Live set có lớn gần bằng heap capacity không?
- Có memory leak hoặc cache không giới hạn không?
- Có allocation spike hoặc humongous object không?
- Có promotion pressure hoặc evacuation failure không?
- Có explicit GC từ ứng dụng/thư viện không?
- Có heap dump hoặc JFR recording đúng thời điểm không?

Full GC thường cần điều tra kỹ, nhưng không nên chỉ dựa vào tên event để kết luận nguyên nhân.

### G1 evacuation failure

Log có thể chứa:

- Evacuation Failure.
- To-space exhausted.

Đây là dấu hiệu G1 không có đủ vùng đích để evacuation một phần object. Kiểm tra heap pressure, live set, allocation rate, region availability và thời điểm mixed collection.

Đừng tăng pause target như cách xử lý duy nhất. Cần xác định vì sao heap không có đủ không gian cho hoạt động evacuation.

### Remark hoặc Cleanup pause

G1 concurrent marking có các pause Remark và Cleanup. Nếu các phase này chiếm phần lớn pause, xem GC pause phase breakdown và concurrent marking timeline. Tần suất và duration phụ thuộc heap, object graph, reference processing và workload.

### Concurrent GC tốn CPU nhưng pause ngắn

Nếu pause thấp nhưng CPU usage cao trong thời gian GC, collector có thể đang thực hiện nhiều concurrent work. Xem JFR gc-cpu-time, concurrent phases và process CPU. Giảm pause không nhất thiết đồng nghĩa giảm tổng CPU hoặc tăng throughput.

## 11. So sánh các garbage collector

Mỗi collector có mục tiêu và cấu trúc pause khác nhau.

| Collector | Đặc điểm khi phân tích pause |
|---|---|
| Serial GC | Collection chủ yếu STW, phù hợp workload nhỏ hoặc ít core |
| Parallel GC | STW collection sử dụng nhiều worker để tăng throughput |
| G1 GC | Young/mixed/full pause kết hợp concurrent marking |
| ZGC | Phần lớn công việc concurrent, vẫn có các pause ngắn |
| Shenandoah | Concurrent compaction, vẫn có các pause cần theo dõi |

Không so sánh trực tiếp pause duration giữa các collector nếu workload, heap, JDK, CPU quota và latency objective khác nhau.

Với ZGC hoặc Shenandoah, một số phase có thể khác tên và cách tổ chức. Dùng JFR metadata, GC log của đúng collector và tài liệu JDK đang chạy.

### Xem collector đang dùng

~~~bash
jcmd 12345 VM.flags
~~~

Tìm các flag như:

~~~text
-XX:+UseG1GC
-XX:+UseZGC
-XX:+UseShenandoahGC
-XX:+UseParallelGC
-XX:+UseSerialGC
~~~

Không mặc định rằng JVM đang chạy G1. Collector được chọn có thể phụ thuộc cấu hình startup, JDK và môi trường.

## 12. Điều chỉnh GC sau khi đã có dữ liệu

Chỉ điều chỉnh khi đã xác định được nguyên nhân và có baseline.

### Heap size

- Xms: initial heap size.
- Xmx: maximum heap size.

Tăng Xmx có thể giảm tần suất GC trong một số workload nhưng làm tăng memory footprint và không bảo đảm pause ngắn hơn. Heap lớn hơn có thể làm một số collection mất nhiều thời gian hơn.

### G1 pause target

~~~bash
-XX:MaxGCPauseMillis=200
~~~

Đây là mục tiêu mềm để G1 cân nhắc khi lập kế hoạch collection, không phải cam kết mọi pause luôn dưới 200 ms. Collector có thể ưu tiên throughput, heap occupancy và các điều kiện khác.

Giảm pause target có thể khiến G1 chọn collection nhỏ hơn hoặc thực hiện GC thường xuyên hơn. Hãy đo cả pause distribution, throughput và CPU sau khi thay đổi.

### Không ép GC để đo

Tránh dùng System.gc() hoặc jcmd GC.run trong lúc đang đo workload bình thường. Lệnh ép GC làm thay đổi hành vi của JVM và có thể tạo pause không đại diện cho production.

Chỉ dùng explicit GC trong một lab hoặc quy trình chẩn đoán có mục đích rõ ràng.

## 13. Đối chiếu GC pause với latency ứng dụng

GC pause có thể làm tất cả application thread bị dừng, nhưng request latency spike còn có thể đến từ lock, network, disk, scheduler hoặc CPU throttling.

Quy trình:

1. Ghi thời điểm request latency tăng từ APM/metrics.
2. Kiểm tra JFR recording có bao phủ thời điểm đó không.
3. Dùng gc-pauses để tìm pause dài hoặc tần suất tăng.
4. Đối chiếu timestamp và gcId trong event.
5. Xem GC cause và heap before/after.
6. Xem phase breakdown để tìm phần tốn thời gian.
7. Kiểm tra unified safepoint log nếu có khoảng dừng không liên quan GC.
8. Đối chiếu allocation rate, CPU load, thread và I/O.
9. Lặp lại dưới workload tương đương để xác nhận giả thuyết.

Một pause có thể trùng với một request chậm mà không phải nguyên nhân duy nhất. Cần xem request nào bị ảnh hưởng, mức pause xảy ra trong thời điểm nào và có những yếu tố đồng thời khác không.

## 14. Lỗi thường gặp khi đọc pause time

### Nhầm GC cycle duration với pause duration

Concurrent phase có thể chạy trong khi ứng dụng vẫn xử lý request. Dùng JFR gc-pauses hoặc GC log pause line để đo STW pause.

### Chỉ xem average

Average che giấu tail latency. Luôn xem P95, P99, maximum và số lượng pause.

### Cộng phase con hai lần

Một GC pause có thể có nhiều sub-phase. Không cộng duration của phase con vào tổng pause nếu tổng pause đã bao gồm chúng.

### Coi collection time MXBean là pause time chính xác

getCollectionTime() là số liệu tích lũy do collector cung cấp. Nó không cung cấp từng pause hoặc percentile. Dùng JFR để phân tích pause.

### Chỉ xem heap used sau GC

Heap after GC thấp không chứng minh không có pause dài. Cần đọc duration, phase và số lần collection.

### Không phân biệt Full GC với concurrent phase

Một concurrent cycle có thể dài nhưng application vẫn chạy trong nhiều phần của cycle. Tách concurrent phase khỏi STW pause.

### Không kiểm tra safepoint

Nếu ứng dụng pause nhưng không có GC pause tương ứng, xem safepoint log và VM operation.

### So sánh recording khác điều kiện

Khác heap size, collector, CPU, container quota hoặc workload làm cho pause metrics không thể so sánh trực tiếp.

## 15. Checklist chẩn đoán GC pause

- [ ] Xác định đúng PID và collector.
- [ ] Ghi nhận JDK version, heap size và CPU/container limit.
- [ ] Bật JFR hoặc unified GC log trong cửa sổ sự cố.
- [ ] Kiểm tra recording có đúng khoảng thời gian không.
- [ ] Xem pause count, total, median, P95, P99 và maximum.
- [ ] Phân biệt GC event, pause event và concurrent phase.
- [ ] Đọc GC cause và heap before/after.
- [ ] Kiểm tra GC pause phase breakdown.
- [ ] Kiểm tra YGC, FGC, CGC và thời gian tích lũy qua jstat.
- [ ] Đối chiếu collection metrics từ MXBean khi cần.
- [ ] Kiểm tra safepoint nếu latency spike không có GC pause.
- [ ] Đối chiếu pause với request latency và allocation rate.
- [ ] Xác định nguyên nhân trước khi đổi heap hoặc GC flags.
- [ ] Đo lại sau thay đổi bằng workload tương đương.

## 16. Các lệnh cần nhớ

~~~bash
# Start a JFR recording at JVM startup
java -XX:StartFlightRecording=filename=gc.jfr,settings=profile,duration=60s,dumponexit=true -jar app.jar

# Start a recording on an existing JVM
jcmd <pid> JFR.start name=GC settings=profile duration=60s filename=gc.jfr

# Check recording
jcmd <pid> JFR.check

# Dump and stop
jcmd <pid> JFR.dump name=GC filename=gc-snapshot.jfr
jcmd <pid> JFR.stop name=GC

# Pause distribution and phases
jfr view gc-pauses gc.jfr
jfr view gc-pause-phases gc.jfr
jfr view gc gc.jfr
jfr view gc-cpu-time gc.jfr

# Print detailed GC events
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary gc.jfr

# Unified GC and safepoint logging
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar

# Rotate GC logs
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar

# Sample GC utilization
jstat -gcutil <pid> 1000 10

# Sample GC causes
jstat -gccause <pid> 1000 10

# Inspect heap and collector flags
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
~~~

GC pause time cần được đọc như một phân phối theo thời gian, không phải một con số trung bình duy nhất. Dùng JFR để xem total, P95/P99, phase và heap before/after; dùng unified logging để xác định từng pause và safepoint; dùng jstat và MXBean để theo dõi xu hướng tích lũy. Sau khi tìm được nguyên nhân, hãy thay đổi cấu hình có mục tiêu và đo lại dưới workload tương đương.

## Tài liệu tham khảo

- [Java Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The jstat Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [GarbageCollectorMXBean — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Java HotSpot VM Options — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [JDK Troubleshooting Guide: Garbage Collection](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html)
