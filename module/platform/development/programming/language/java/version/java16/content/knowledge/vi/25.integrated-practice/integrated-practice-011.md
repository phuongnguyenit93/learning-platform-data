# Dùng JFR, GC log và metaspace metrics để phân tích một workload thống nhất

Muốn tìm nguyên nhân một workload Java chậm hoặc tăng bộ nhớ, cần đọc JFR, GC log và số liệu Metaspace trên cùng tiến trình và cùng khoảng thời gian. JFR cho biết JVM và ứng dụng đang làm gì; GC log cho biết các chu kỳ thu gom, pause và safepoint; Metaspace metrics cho biết class metadata đang dùng bao nhiêu native memory và class loader nào đang giữ metadata. Ba nguồn bổ sung cho nhau, nhưng chỉ có giá trị khi có thể đối chiếu theo cùng một workload, cùng mốc thời gian và cùng giai đoạn tải.

Một snapshot Metaspace tại thời điểm cuối không đủ để kết luận có leak; một GC pause dài không tự chứng minh đó là nguyên nhân p99 tăng; một JFR recording không có allocation events cũng không chứng minh ứng dụng không cấp phát nhiều object. Cần thiết kế phép đo có baseline, warm-up, steady state, peak/burst và cooldown; sau đó ghép timeline, kiểm tra xu hướng và xác minh giả thuyết bằng một lần chạy có kiểm soát.

Bài học thuộc chương **Thực hành tổng hợp** của module **JAVA_VERSION_JAVA16**. Nội dung kết hợp các công cụ chuẩn của JDK như Java Flight Recorder, Unified Logging, jcmd và jfr; các công cụ này vẫn được dùng trong JDK hiện đại. Trọng tâm là phân tích một workload nhất quán, tránh các cách đo lỗi thời hoặc gây nhiễu như dựa vào một snapshot đơn lẻ hay ép GC trong lúc benchmark.

## 1. Vai trò của ba nguồn dữ liệu

| Nguồn | Cung cấp dữ liệu | Câu hỏi có thể trả lời |
| --- | --- | --- |
| JFR | Sự kiện có timestamp về GC, CPU, thread, allocation, lock, I/O, class loading và hoạt động JVM | Trong lúc workload chậm, thread đang chạy, chờ lock, chờ I/O hay chịu ảnh hưởng của GC? |
| GC log | Chu kỳ GC, nguyên nhân kích hoạt, pause duration, heap trước/sau GC, safepoint và thông tin GC theo collector | GC xảy ra khi nào, pause dài bao lâu, có thu hồi được bộ nhớ không? |
| Metaspace metrics | Used, committed, reserved, chunk/free-space và thống kê class loader | Class metadata tăng hay giảm? Loader nào giữ nhiều metadata? |

Không nguồn nào thay thế được hai nguồn còn lại:

- JFR cho bối cảnh ứng dụng và JVM nhưng event nào được ghi còn phụ thuộc cấu hình recording.
- GC log là nguồn trực tiếp để xem chu kỳ GC và pause; nó không giải thích đầy đủ request đang chờ database hoặc lock.
- jcmd VM.metaspace cho snapshot chi tiết Metaspace, nhưng một snapshot không cho biết xu hướng theo thời gian.

Để điều tra một vấn đề cụ thể, cần đối chiếu cả ba nguồn với request latency, throughput, error rate, CPU và memory metrics của hệ thống.

## 2. Thiết kế một workload thống nhất

Trước khi thu thập dữ liệu, định nghĩa một workload có thể lặp lại:

1. **Request mix:** endpoint hoặc tác vụ nào được gọi, tỷ lệ từng loại và kích thước dữ liệu.
2. **Concurrency:** số request đồng thời, worker pool, active thread và queue depth.
3. **Allocation profile:** workload tạo nhiều object ngắn hạn, object sống lâu, proxy hay class động.
4. **Class loader lifecycle:** có plugin, hot reload, application redeploy hoặc framework tạo class động không?
5. **Dependency:** database, cache, filesystem, network và các dịch vụ ngoài.
6. **Resource budget:** cùng JDK build, heap, CPU quota, RAM/container limit và cấu hình GC.
7. **Thời gian:** thời lượng warm-up, steady state, peak/burst và cooldown.

Ví dụ kế hoạch một lần chạy:

| Giai đoạn | Thời lượng ví dụ | Hoạt động | Mục đích |
| --- | ---: | --- | --- |
| Startup | 2 phút | Khởi động ứng dụng, mở connection pool | Quan sát class loading và khởi tạo |
| Warm-up | 5 phút | Tăng tải từ từ tới mức bình thường | Ổn định JIT, cache và connection pool |
| Steady state | 10 phút | Giữ request rate và concurrency cố định | Lấy baseline ổn định |
| Peak | 5 phút | Tăng tải tới mức peak production | Quan sát GC, CPU và Metaspace dưới tải cao |
| Cooldown | 5 phút | Giảm tải về mức thấp | Kiểm tra xu hướng reclaim và class unloading |

Thời lượng chỉ là ví dụ. Chọn theo chu kỳ hoạt động thực tế của ứng dụng. Nếu vấn đề chỉ xuất hiện sau vài giờ hoặc sau nhiều lần redeploy, recording và workload phải đủ dài để bao phủ chu kỳ đó.

Giữ các yếu tố sau giống nhau giữa các lần chạy:

- Cùng application artifact và dependency.
- Cùng JDK vendor, version và build.
- Cùng heap, collector, CPU quota, RAM limit và container settings.
- Cùng dataset, request mix, arrival rate và số worker.
- Cùng cấu hình database/cache hoặc cùng môi trường phụ thuộc.
- Cùng cách bật JFR, GC logging và NMT nếu sử dụng.

Không thay collector, heap size, số worker và request mix cùng lúc. Khi cần so sánh hai cấu hình, thay một yếu tố mỗi lần để biết yếu tố nào tạo ra khác biệt.

## 3. Đồng bộ timeline giữa JFR, GC log và Metaspace

Đây là điều kiện quan trọng nhất để phân tích đúng. GC log có thể ghi cả wall-clock time và JVM uptime; JFR lưu timestamp cho từng event; snapshot jcmd cần được đánh dấu thời điểm thu thập.

Nên làm như sau:

- Bật GC log với decorator time và uptime.
- Bắt đầu JFR từ lúc JVM khởi động nếu cần quan sát startup; nếu attach sau đó, ghi rõ thời điểm recording bắt đầu.
- Ghi timestamp ISO-8601 trước mỗi lần chạy jcmd VM.metaspace.
- Ghi mốc bắt đầu/kết thúc warm-up, steady state, peak và cooldown.
- Đồng bộ đồng hồ máy chạy ứng dụng, load generator và hệ thống giám sát.
- Nếu ứng dụng có thể sửa code, phát một application log marker hoặc custom JFR event cho từng giai đoạn workload.

Ví dụ marker JFR cho giai đoạn:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.WorkloadPhase")
@Label("Workload phase")
@Category({"Application", "Workload"})
public final class WorkloadPhase extends Event {
    @Label("Run ID")
    String runId;

    @Label("Phase")
    String phase;

    @Label("Active workers")
    int activeWorkers;

    static void mark(String runId, String phase, int activeWorkers) {
        WorkloadPhase event = new WorkloadPhase();
        if (event.isEnabled()) {
            event.runId = runId;
            event.phase = phase;
            event.activeWorkers = activeWorkers;
            event.commit();
        }
    }
}
```

Gọi WorkloadPhase.mark(...) tại ranh giới các giai đoạn, ví dụ warmup, steady-state, peak và cooldown. Marker là instant event; nó giúp lọc timeline trong JFR, còn timestamp log của load generator vẫn cần được giữ để đối chiếu request metrics.

Nếu không thể thay đổi code, ghi cùng một runId và phase marker vào log ứng dụng/load generator với timestamp rõ ràng. Không dựa vào thời điểm người vận hành nhớ đã bấm nút bắt đầu.

## 4. Bật JFR từ lúc khởi động

JFR tích hợp trong JDK và ghi các event có timestamp. Có hai cấu hình dựng sẵn thường dùng:

| Cấu hình | Mục đích | Cách dùng |
| --- | --- | --- |
| default.jfc / settings=default | Recording liên tục với mức dữ liệu và overhead thấp | Theo dõi lâu dài, lưu dữ liệu để điều tra sau |
| profile.jfc / settings=profile | Thu thập nhiều sự kiện hơn, hữu ích khi profiling | Điều tra ngắn hạn hoặc workload thử nghiệm có kiểm soát |

Ví dụ khởi chạy workload với recording profile trong 30 phút, đủ bao phủ kế hoạch minh họa ở phần workload:

```bash
java \
  -XX:StartFlightRecording=name=workload,settings=profile,duration=30m,filename=workload.jfr \
  -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:NativeMemoryTracking=summary \
  -jar service.jar
```

Lệnh trên:

- Bắt đầu JFR từ khi JVM khởi động và ghi ra workload.jfr.
- Ghi GC event và safepoint vào gc.log, có cả wall-clock time và uptime.
- Bật Native Memory Tracking ở mức summary để có thể lấy số liệu native memory bổ sung bằng jcmd.

profile.jfc thu thập nhiều dữ liệu hơn và có thể tạo overhead lớn hơn default.jfc. Dùng recording ngắn và đo overhead trước khi áp dụng cho production. Với recording liên tục, ưu tiên default.jfc; khi cần allocation profiling hoặc event chi tiết hơn, tạo recording profile ngắn hoặc custom JFC có phạm vi phù hợp.

Lưu ý: recording dùng default.jfc không mặc định cung cấp đầy đủ heap statistics hoặc allocation profiling. Nếu cần phân tích nơi cấp phát object, xác nhận event cần thiết đã bật trong cấu hình recording. Không kết luận “không có allocation” chỉ vì file JFR không chứa allocation event.

## 5. Bắt đầu JFR trên JVM đang chạy

Nếu không thể khởi động lại ứng dụng, có thể attach bằng jcmd. Trước tiên tìm PID:

```bash
jcmd -l
```

Bắt đầu recording có thời lượng:

```bash
jcmd <pid> JFR.start name=workload settings=profile duration=10m filename=workload.jfr
```

Kiểm tra trạng thái recording:

```bash
jcmd <pid> JFR.check
```

Nếu cần dump dữ liệu trước khi recording kết thúc:

```bash
jcmd <pid> JFR.dump name=workload filename=workload-partial.jfr
```

Hoặc dừng recording:

```bash
jcmd <pid> JFR.stop name=workload
```

Khi attach vào JVM đang chạy, dữ liệu trước thời điểm JFR.start không có trong recording mới. Nếu vấn đề nằm ở startup, class loading ban đầu hoặc warm-up, hãy khởi động recording cùng JVM hoặc dùng một continuous recording đã chạy từ trước.

jcmd cần chạy trên cùng máy và dưới cùng effective user/group đã khởi chạy JVM. Trong container, cần xác định PID trong đúng PID namespace và dùng JDK/tool phù hợp với tiến trình đích.

## 6. Cấu hình GC log bằng Unified Logging

Unified Logging là cách hiện hành để thu thập GC log trên JDK hiện đại:

```bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar service.jar
```

Có thể bật thêm chi tiết Metaspace trong một lần điều tra ngắn:

```bash
java -Xlog:gc*,gc+metaspace=debug,safepoint:file=gc-metaspace.log:time,uptime,level,tags -jar service.jar
```

Tag gc+metaspace giúp xem chi tiết liên quan Metaspace; mức debug có thể tạo nhiều log hơn, nên chỉ bật khi cần và theo dõi dung lượng file. Có thể giới hạn file bằng filecount và filesize như ví dụ trên.

Khi đọc GC log, thu thập:

- Thời điểm và duration của từng pause.
- Loại collector/event và nguyên nhân kích hoạt.
- Heap occupancy trước/sau GC.
- Khoảng cách giữa các chu kỳ và tần suất pause.
- Thời gian concurrent phase nếu collector ghi nhận.
- Safepoint synchronization và VM operation liên quan.
- Thông tin Metaspace nếu đã bật tag tương ứng.

Không chỉ đọc dòng pause dài nhất. Hãy đối chiếu toàn bộ cửa sổ thời gian với request latency và JFR để xác định pause có thực sự trùng với spike hay không.

## 7. Thu thập Metaspace metrics bằng jcmd

jcmd VM.metaspace cung cấp snapshot về Metaspace:

```bash
jcmd <pid> VM.metaspace basic=true scale=MB
```

Để xem phân bố theo class loader:

```bash
jcmd <pid> VM.metaspace show-loaders=true scale=MB
jcmd <pid> VM.classloader_stats
```

Các lệnh này giúp kiểm tra:

- used: phần metadata đang được sử dụng.
- committed: bộ nhớ đã commit và có thể được dùng để cấp phát.
- reserved: vùng địa chỉ ảo đã reserve, không đồng nghĩa với RAM vật lý đang sử dụng.
- Số lượng loader và lượng metadata gắn với từng loader.
- Chunk/free-list và khả năng tái sử dụng vùng nhớ khi cần xem sâu hơn.

VM.metaspace basic=true tạo bản tóm tắt cơ bản mà không cần safepoint. show-loaders=true và VM.classloader_stats hữu ích khi nghi ngờ loader tăng liên tục; output có thể lớn hơn khi ứng dụng có nhiều loader/class.

Đánh dấu thời điểm từng snapshot. Ví dụ trên PowerShell:

```powershell
Get-Date -Format o
jcmd 12345 VM.uptime
jcmd 12345 VM.metaspace basic=true scale=MB
jcmd 12345 VM.metaspace show-loaders=true scale=MB
jcmd 12345 VM.classloader_stats
```

Thay 12345 bằng PID thực tế. Lặp lại ở các mốc startup, sau warm-up, cuối steady state, giữa peak và sau cooldown. Nếu output quá lớn, chỉ lấy basic=true thường xuyên và lấy thống kê loader ở các mốc chẩn đoán đã định.

## 8. Bổ sung Native Memory Tracking khi cần

Metaspace là một phần native memory của JVM. Native Memory Tracking (NMT) giúp đối chiếu Metaspace với tổng native memory theo subsystem. NMT phải được bật khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar service.jar
```

Lấy snapshot:

```bash
jcmd <pid> VM.native_memory summary
```

Đặt baseline và xem chênh lệch:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT không thay thế VM.metaspace; nó cung cấp góc nhìn tổng thể native memory. NMT có overhead, vì vậy chỉ bật khi phép đo cần nó và ghi nhận việc bật NMT trong báo cáo. Không so sánh lượt chạy có NMT với lượt không NMT rồi quy mọi chênh lệch memory cho collector.

## 9. Phân tích JFR recording

Sau khi recording hoàn tất, xem tổng quan:

```bash
jfr summary workload.jfr
```

Lệnh này cho biết số lượng event theo loại và giúp xác nhận event cần thiết đã được ghi. Có thể in một số nhóm event:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary,jdk.ClassLoadingStatistics,jdk.ThreadAllocationStatistics workload.jfr
```

Các event hữu ích khi phân tích workload:

| Nhóm | Event thường gặp | Câu hỏi |
| --- | --- | --- |
| GC | jdk.GarbageCollection, jdk.GCPhasePause, jdk.GCHeapSummary | GC xảy ra lúc nào, pause bao lâu, heap thay đổi thế nào? |
| Class loading | jdk.ClassLoadingStatistics, jdk.ClassLoad, jdk.ClassUnload nếu có trong recording | Số class được nạp/unload có thay đổi theo workload không? |
| Allocation | jdk.ObjectAllocationSample, jdk.ObjectAllocationInNewTLAB, jdk.ObjectAllocationOutsideTLAB, jdk.ThreadAllocationStatistics khi được bật | Class/method nào tạo nhiều object? |
| CPU | jdk.CPULoad, jdk.ThreadCPULoad, jdk.ExecutionSample | JVM hoặc thread nào đang dùng CPU? |
| Synchronization | jdk.JavaMonitorEnter, jdk.JavaMonitorWait, jdk.ThreadPark | Thread chờ lock/park bao lâu? |
| I/O | jdk.SocketRead, jdk.SocketWrite, jdk.FileRead, jdk.FileWrite | Có thời gian chờ network hoặc filesystem đáng kể không? |

Event thực tế phụ thuộc JDK build và JFR settings. Dùng Event Browser trong JDK Mission Control hoặc jfr metadata workload.jfr để kiểm tra event có trong recording. Không giả định một event chắc chắn tồn tại hoặc được bật trong mọi cấu hình.

Nếu cần lọc event:

```bash
jfr print --events jdk.GCPhasePause workload.jfr
jfr print --events jdk.ThreadAllocationStatistics workload.jfr
jfr print --events jdk.JavaMonitorWait,jdk.ThreadPark workload.jfr
```

Với event duration, xem cả start time, duration, thread và stack trace. Một event không xuất hiện có thể do nó không được bật, ngưỡng duration cao hơn sự kiện thực tế hoặc workload không tạo ra tình huống đó.

## 10. Ghép ba nguồn theo một timeline

Sau khi thu thập, lập bảng timeline theo cùng runId và phase:

| Giai đoạn | Request metrics | JFR | GC log | Metaspace |
| --- | --- | --- | --- | --- |
| Startup | Thời gian khởi động, request chưa ổn định | Class loading, JIT, thread start | GC đầu tiên và heap init | Baseline used/committed/reserved |
| Warm-up | Latency và throughput đang ổn định dần | CPU, allocation, compilation | Tần suất GC và pause | Metadata tăng khi framework nạp class |
| Steady state | p50/p95/p99, throughput, error | Allocation, CPU, lock, I/O | Pause và reclaim | Used/committed và loader distribution |
| Peak | Tail latency và queue depth | CPU contention, allocation và thread stalls | GC cycle/pause khi tải cao | Metadata tăng thêm hay giữ ổn định |
| Cooldown | Latency sau khi giảm tải | Class unload và hoạt động thread | GC sau peak nếu tự nhiên xảy ra | Used có giảm không, committed có uncommit không |

Không cộng máy móc tổng duration của mọi event JFR với GC pause. Nhiều event có thể chồng lấp theo thời gian hoặc mô tả cùng một hoạt động ở mức chi tiết khác nhau. Hãy dùng timestamp và thread context để xác định quan hệ nhân quả.

## 11. Diễn giải Metaspace theo xu hướng

Một ví dụ snapshot minh họa:

| Mốc | Used | Committed | Reserved | Class loaders |
| --- | ---: | ---: | ---: | ---: |
| Sau startup | 80 MB | 112 MB | 256 MB | 45 |
| Sau warm-up | 105 MB | 144 MB | 256 MB | 48 |
| Cuối steady state | 108 MB | 144 MB | 256 MB | 48 |
| Cuối peak | 116 MB | 160 MB | 256 MB | 49 |
| Sau cooldown | 109 MB | 144 MB | 256 MB | 48 |

Các số liệu trên chỉ minh họa cách đọc xu hướng, không phải ngưỡng chuẩn cho ứng dụng. Ở ví dụ này, used tăng trong warm-up rồi tương đối ổn định; sau peak, metadata giảm một phần. Đây có thể là hành vi bình thường của ứng dụng nạp class theo nhu cầu.

Một tình huống đáng điều tra hơn là số loader và used tăng qua mỗi chu kỳ deploy/plugin reload mà không trở về mức ổn định. Hãy dùng VM.metaspace show-loaders=true và VM.classloader_stats để xác định loader nào tồn tại lâu. Sau đó kiểm tra thread context class loader, thread còn sống, ThreadLocal, static reference, cache và callback có giữ loader hay không.

Không yêu cầu committed hoặc RSS phải giảm ngay khi used giảm. Elastic Metaspace có thể giữ chunk trống để tái sử dụng rồi uncommit theo cơ chế quản lý bộ nhớ. reserved là vùng địa chỉ ảo, không phải số RAM vật lý đang tiêu thụ.

## 12. Đọc dấu hiệu GC cùng allocation và heap

| Quan sát | Khả năng | Kiểm tra tiếp |
| --- | --- | --- |
| GC pause trùng với request latency spike | Stop-the-world pause có thể góp phần làm chậm request | Đối chiếu timestamp, duration và số request bị ảnh hưởng |
| Pause thấp nhưng request p99 cao | Queue, CPU, lock, I/O hoặc downstream có thể là bottleneck | JFR thread stall, CPU, socket/database và application metrics |
| Allocation rate tăng mạnh trước GC dày | Workload tạo nhiều temporary object | JFR allocation events và stack trace |
| Heap sau GC vẫn tăng qua nhiều chu kỳ | Live set tăng hoặc object bị giữ tham chiếu | Heap analysis khi cần, object retention và cache |
| Metaspace used tăng cùng class loader count | Nạp class/loader mới theo workload hoặc loader leak | Class loading/unloading và loader statistics |
| Metaspace used giảm nhưng committed chưa giảm | Chunk trống được giữ để tái sử dụng hoặc chưa uncommit | Theo dõi nhiều snapshot và NMT |
| GC log cho thấy reclaim ít, JFR thấy allocation cao | Allocation pressure hoặc live set lớn | Allocation site, object lifetime và heap sizing |

Không dùng riêng một dấu hiệu để kết luận leak. Ví dụ, class count tăng trong startup/warm-up là bình thường; chỉ khi tăng không giới hạn qua các chu kỳ workload hoặc redeploy mới cần điều tra sâu.

## 13. Case study: workload chậm sau nhiều lần reload plugin

Một service xử lý request bình thường trong vài phút đầu. Sau mỗi lần reload plugin, Metaspace used tăng và p99 bắt đầu xấu đi. Nhóm vận hành thu thập JFR, GC log và Metaspace snapshots trong cùng một run.

Kết quả giả định:

- JFR cho thấy số class load tăng sau mỗi lần reload; class unload thấp hơn nhiều.
- VM.metaspace show-loaders=true cho thấy nhiều loader cũ vẫn tồn tại.
- GC log không cho thấy pause dài đủ để giải thích toàn bộ p99 increase.
- Request trace cho thấy một số worker giữ context class loader cũ sau khi plugin đã đóng.

Hướng xử lý:

1. Xác định thread hoặc object còn tham chiếu loader cũ.
2. Sửa lifecycle plugin để khôi phục/reset thread context class loader và dừng thread do plugin tạo.
3. Gỡ ThreadLocal, listener, callback và cache giữ class/plugin instance.
4. Chạy lại cùng workload và cùng số lần reload.
5. Xác nhận class unload tăng, loader count không tăng vô hạn và Metaspace used ổn định sau cooldown.

Case study này cho thấy GC log có thể xác nhận pause không phải nguyên nhân chính; JFR và Metaspace metrics giúp chuyển điều tra sang class loader lifecycle. Không tăng MaxMetaspaceSize trước khi kiểm tra nguyên nhân giữ loader.

## 14. Quy trình điều tra có thể lặp lại

1. **Ghi giả thuyết:** latency, allocation pressure, GC pause hay Metaspace/class loader tăng?
2. **Chốt workload:** request mix, concurrency, worker, dataset, dependency và thời gian.
3. **Bật công cụ:** JFR, GC/safepoint log và NMT nếu cần.
4. **Đánh dấu phase:** startup, warm-up, steady state, peak và cooldown.
5. **Lấy snapshots:** VM.metaspace và class loader stats tại các mốc đã định.
6. **Đọc recording:** kiểm tra jfr summary, GC, allocation, CPU, lock, I/O và class loading events.
7. **Ghép timeline:** đối chiếu JFR, GC log, Metaspace, request metrics và timestamp.
8. **Kiểm tra giả thuyết:** chỉ thay một yếu tố trong lần chạy tiếp theo.
9. **Xác nhận:** chạy lại cùng workload và kiểm tra p99, throughput, error rate, memory và xu hướng loader.

Giữ lại cấu hình JVM, JDK build, workload definition, log và recording cùng runId. Nhờ đó, một lần chạy sau có thể so sánh được với baseline.

## 15. Những lỗi đo lường cần tránh

- Thu JFR, GC log và Metaspace ở các tiến trình hoặc các lần chạy khác nhau rồi ghép như một timeline.
- So sánh snapshot trước warm-up của lần này với steady state của lần khác.
- Chỉ chụp một lần VM.metaspace rồi kết luận có memory leak.
- Dùng profile.jfc liên tục trong thời gian dài mà không đo overhead và dung lượng recording.
- Dùng default.jfc nhưng giả định đã có đầy đủ allocation/heap statistics.
- Gọi jcmd <pid> GC.run hoặc System.gc() trong workload benchmark, làm thay đổi hành vi cần quan sát.
- Dùng heap histogram/heap dump không đúng thời điểm mà không cân nhắc impact và pause.
- Nhầm reserved với RAM vật lý hoặc yêu cầu committed giảm ngay sau class unloading.
- Kết luận GC gây p99 tăng chỉ vì hai sự kiện xảy ra gần nhau mà chưa kiểm tra queue, lock, CPU và I/O.
- Bỏ qua timestamp, uptime, timezone hoặc clock skew giữa application và load generator.

## 16. Bài tập tự kiểm tra

Một service chạy workload cố định 30 phút. Sau warm-up, request p99 tăng dần. GC log cho thấy pause tương đối ổn định; JFR cho thấy class load tăng sau mỗi lần reload plugin; Metaspace snapshots cho thấy used và class loader count tiếp tục tăng qua ba chu kỳ reload. Sau cooldown, used chỉ giảm rất ít.

Hãy trả lời:

1. Vì sao chưa thể kết luận GC pause là nguyên nhân chính của p99 tăng?
2. JFR cần xem những nhóm event nào để xác định thread hoặc code giữ plugin loader?
3. Lệnh jcmd nào giúp xem Metaspace theo class loader?
4. Vì sao cần nhiều snapshot thay vì một lần đo?
5. Nếu used giảm nhưng committed không giảm ngay, có thể kết luận leak không?
6. Cần giữ những yếu tố nào giống nhau khi chạy lại sau khi sửa lifecycle plugin?

**Đáp án:**

1. GC pause ổn định không tương quan rõ với p99; cần kiểm tra CPU, lock, I/O, queue và plugin lifecycle.
2. Class loading/unloading, thread start/end, ThreadPark, monitor contention, allocation và execution samples; xem stack/thread context trong JFR.
3. jcmd <pid> VM.metaspace show-loaders=true scale=MB và jcmd <pid> VM.classloader_stats.
4. Nhiều snapshot cho thấy xu hướng theo warm-up, reload, peak và cooldown; một snapshot không chứng minh metadata có tiếp tục tăng hay không.
5. Không. Chunk trống có thể được giữ lại để tái sử dụng; cần xem used, committed, reserved và xu hướng qua thời gian.
6. Cùng JDK build, artifact, request mix, số lần reload, worker/concurrency, CPU/RAM, heap, dependency và cách bật JFR/GC/NMT.

## Ghi nhớ

**JFR, GC log và Metaspace metrics phải được thu thập trên cùng JVM và cùng workload timeline.** JFR giải thích hoạt động thread, allocation, class loading, lock và I/O; GC log xác định pause/cycle/safepoint; jcmd VM.metaspace và VM.classloader_stats cho biết xu hướng native class metadata và loader. Đồng bộ bằng timestamp, uptime và phase marker; đo từ startup qua warm-up, steady state, peak đến cooldown. Dựa trên nhiều snapshot và request metrics để kiểm chứng giả thuyết, không kết luận từ một pause hoặc một giá trị memory đơn lẻ.

## Tài liệu tham khảo

- [Oracle Java SE 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 26 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-configurations.html)
- [Oracle Java SE 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle Java SE 26 — The jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Oracle Java SE 26 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html)
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
