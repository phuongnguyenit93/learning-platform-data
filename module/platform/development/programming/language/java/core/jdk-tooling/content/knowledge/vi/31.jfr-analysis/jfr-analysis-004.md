# Phân tích Garbage Collection bằng JFR

**Java Flight Recorder (JFR)** thu thập sự kiện runtime của JVM theo dòng thời gian. Khi phân tích **Garbage Collection (GC)**, JFR cho biết collection nào đã chạy, nguyên nhân kích hoạt, thời gian, các pause của ứng dụng, pha concurrent, trạng thái heap trước/sau GC và áp lực allocation.

Phân tích GC bằng JFR giúp trả lời những câu hỏi thực tế: ứng dụng pause bao lâu, GC xảy ra thường xuyên đến mức nào, heap sau GC có tăng theo thời gian không, collector đang tốn thời gian ở pha nào và class/method nào tạo nhiều object. JFR cung cấp bằng chứng để điều tra; bản ghi không tự kết luận memory leak hoặc tự chọn cấu hình GC tối ưu.

## 1. JFR ghi nhận hoạt động GC như thế nào?

JFR ghi các event có timestamp, duration, thread, stack trace và những trường dữ liệu riêng của từng loại event. Event GC có thể được xem trên timeline bằng Java Mission Control (JMC) hoặc đọc từ command line bằng công cụ `jfr`.

Một GC cycle có thể gồm nhiều hoạt động:

- JVM quyết định cần collection và ghi nhận nguyên nhân.
- Collector thực hiện các pha chuẩn bị, đánh dấu, quét, copy/evacuate hoặc compact object.
- Một số pha cần dừng Java thread (stop-the-world pause).
- Một số pha chạy concurrent trong khi ứng dụng tiếp tục thực thi.
- JVM cập nhật heap summary và kết thúc collection.

Vì vậy, một GC cycle không nhất thiết chỉ có một pause. Đặc biệt với G1, ZGC và Shenandoah, cần phân biệt thời gian toàn bộ chu kỳ với thời gian ứng dụng thực sự bị dừng.

JFR giúp kết nối các event có cùng **GC ID** để xem một collection gồm những pha nào, heap thay đổi ra sao và pause dài nhất là bao nhiêu.

## 2. Những GC event quan trọng

Tên event và mức độ chi tiết phụ thuộc JDK, JVM vendor, collector và recording settings. Trên HotSpot JDK 24, các event thường hữu ích gồm:

| JFR event | Dữ liệu chính | Dùng để phân tích |
| --- | --- | --- |
| `jdk.GarbageCollection` | GC ID, collector name, cause, duration, sumOfPauses, longestPause | Tổng quan mỗi collection và pause liên quan |
| `jdk.GCHeapSummary` | GC ID, thời điểm Before GC/After GC, heap used và heap space | So sánh heap trước/sau collection |
| `jdk.GCPhasePause` | GC ID, tên pha và duration | Xác định các pha stop-the-world |
| `jdk.GCPhaseConcurrent` | GC ID, tên pha và duration | Xem công việc collector chạy concurrent |
| `jdk.ObjectAllocationSample` | Class object, sample weight, thread và stack trace | Tìm nơi tạo allocation pressure |
| `jdk.GCReferenceStatistics` | Loại reference và số lượng được xử lý | Điều tra chi phí xử lý Soft/Weak/Phantom reference |
| `jdk.TenuringDistribution` | Tuổi object và dung lượng theo tuổi | Theo dõi object sống qua nhiều young GC |
| `jdk.EvacuationInformation` | Region trong collection set, bytes copied, region freed | Điều tra evacuation của G1 |
| `jdk.AllocationRequiringGC` | Kích thước allocation và GC ID đang chờ | Tìm allocation phải chờ GC |
| `jdk.GCConfiguration` | Collector, số GC thread, pause target và cấu hình GC | Hiểu môi trường đang được ghi |
| `jdk.GCHeapConfiguration` | Heap min/initial/max và thông tin layout | Đối chiếu kết quả với giới hạn heap |

Một số collector có event riêng, ví dụ `jdk.G1GarbageCollection`, `jdk.G1HeapSummary`, `jdk.YoungGarbageCollection`, `jdk.OldGarbageCollection`, hoặc event chi tiết của ZGC/Shenandoah. Không giả định tất cả event này đều tồn tại hoặc được bật trên mọi JDK.

Dùng metadata của chính JDK/recording để kiểm tra tên và field:

```bash
jfr metadata --events GarbageCollection,GCHeapSummary,GCPhasePause,GCPhaseConcurrent,ObjectAllocationSample
```

Nếu đã có file recording, có thể đọc metadata từ file đó:

```bash
jfr metadata --events GarbageCollection recording.jfr
```

## 3. Phân biệt GC duration và pause duration

Đây là điểm quan trọng nhất khi đọc JFR.

`jdk.GarbageCollection.duration` biểu diễn thời gian của event collection. Với collector có công việc concurrent, duration của một chu kỳ có thể dài hơn nhiều so với thời gian ứng dụng bị dừng.

Event `jdk.GarbageCollection` còn có hai field riêng:

- **`sumOfPauses`:** tổng thời gian Java execution bị pause trong collection đó.
- **`longestPause`:** pause đơn lẻ dài nhất trong collection đó.

`jdk.GCPhasePause` ghi thời lượng từng pha pause. `jdk.GCPhaseConcurrent` ghi các pha collector chạy concurrent; các pha này không đồng nghĩa ứng dụng bị dừng hoàn toàn.

Ví dụ với G1:

- Một chu kỳ old/concurrent GC có thể kéo dài nhiều giây.
- Trong chu kỳ đó, ứng dụng vẫn chạy trong các pha concurrent.
- Chu kỳ có thể chỉ chứa một vài pause ngắn.
- Do đó, nhìn `duration` rồi coi toàn bộ thời gian là application pause sẽ cho kết luận sai.

Khi điều tra latency, ưu tiên `sumOfPauses`, `longestPause`, các `GCPhasePause` và thống kê pause percentile. Dùng duration và `GCPhaseConcurrent` để hiểu thời gian collector làm việc nền.

## 4. Đọc GC ID và heap summary trước/sau GC

`jdk.GarbageCollection` có trường `gcId`. Các event phase và heap summary liên quan cũng có thể chứa cùng GC ID.

`jdk.GCHeapSummary` cung cấp:

- `when`: thời điểm summary, thường là `Before GC` hoặc `After GC`.
- `heapUsed`: số byte đang được sử dụng trong heap ở thời điểm event.
- `heapSpace`: thông tin vùng heap tương ứng.

Quy trình đọc:

1. Tìm một `jdk.GarbageCollection` có GC ID cần điều tra.
2. Ghi lại collector name, cause, duration, sumOfPauses và longestPause.
3. Lọc các `jdk.GCHeapSummary` cùng GC ID.
4. Ghép summary Before GC với After GC.
5. Xem các `GCPhasePause` và `GCPhaseConcurrent` cùng GC ID.
6. So sánh với các collection trước và sau trong recording.

Heap Before/After giúp quan sát xu hướng, nhưng không nên luôn lấy phép trừ hai giá trị để coi là số byte object đã được thu hồi chính xác. Với concurrent collector, allocation có thể diễn ra trong khi collection đang chạy; cách tính và thời điểm snapshot còn phụ thuộc collector.

Để đánh giá memory leak, quan sát mức heap sau GC qua nhiều chu kỳ dưới workload tương đương. Nếu baseline sau GC tăng dần, cần kiểm tra object retention bằng heap dump, JFR old-object sampling hoặc MAT.

## 5. Phân tích nguyên nhân kích hoạt GC

Trường `cause` của `jdk.GarbageCollection` cho biết lý do JVM kích hoạt collection. Giá trị cụ thể phụ thuộc collector và phiên bản JDK.

Một số nhóm nguyên nhân thường gặp:

| Nhóm nguyên nhân | Cách diễn giải |
| --- | --- |
| Allocation/evacuation pressure | Ứng dụng tạo object nhanh hoặc vùng cấp phát cần được thu hồi |
| System/explicit GC | Ứng dụng hoặc thư viện gọi `System.gc()`/`Runtime.gc()`; collector có thể xử lý theo cấu hình |
| Metadata/Metaspace threshold | JVM cần xử lý áp lực metadata/class loading |
| G1 humongous allocation | Allocation object lớn ảnh hưởng đến region của G1 |
| Diagnostic/last-ditch collection | JVM thực hiện collection trong một tình huống đặc biệt hoặc dưới áp lực tài nguyên |

Không kết luận chỉ từ chuỗi cause. Hãy kết hợp:

- Collector name và loại young/old/full collection.
- Heap trước/sau.
- Tần suất collection.
- Pause duration và phase.
- Allocation samples.
- GC configuration và heap max.
- Application workload tại cùng thời điểm.

Nếu cause là explicit GC lặp lại, tìm call site hoặc thư viện gọi GC trước khi cân nhắc thay đổi hành vi explicit GC. Không tắt `System.gc()` một cách máy móc khi chưa hiểu ứng dụng.

## 6. Đọc pause distribution thay vì chỉ nhìn trung bình

Một số liệu average thấp có thể che giấu một vài pause rất dài. Với ứng dụng nhạy latency, cần quan tâm phân vị và giá trị cực đại.

Các chỉ số nên theo dõi:

- **Pause count:** số pause trong khoảng ghi.
- **Total pause time:** tổng thời gian ứng dụng bị dừng do GC.
- **Minimum/median/average:** mức pause điển hình.
- **P90/P95/P99/P99.9:** đuôi phân phối, phản ánh các pause hiếm nhưng ảnh hưởng lớn.
- **Maximum pause:** pause dài nhất quan sát được.

Dùng view có sẵn:

```bash
jfr view gc-pauses gc-analysis.jfr
```

Một lần chạy kiểm thử trên HotSpot JDK 24.0.2 với workload allocation nhỏ và heap giới hạn cho kết quả minh họa:

```text
GC Pauses

Total Pause Time: 206 ms
Number of Pauses: 447
Minimum Pause Time: 0.00390 ms
Median Pause Time: 0.493 ms
Average Pause Time: 0.460 ms
P90 Pause Time: 0.970 ms
P95 Pause Time: 1.07 ms
P99 Pause Time: 1.27 ms
P99.9% Pause Time: 3.12 ms
Maximum Pause Time: 3.12 ms
```

Đây là số liệu của một lần chạy cụ thể, không phải mục tiêu hoặc giá trị chuẩn cho ứng dụng khác. Khi đánh giá production, dùng recording đủ dài và có workload đại diện.

Có thể tính tỷ lệ thời gian pause gần đúng:

`GC pause ratio (%) = total GC pause time / recording wall-clock duration × 100`

Tỷ lệ này thể hiện phần thời gian ứng dụng bị dừng bởi GC trong khoảng đo. Nó không phải CPU time mà GC worker đã sử dụng. Không cộng duration của các pha lồng nhau một cách thủ công vì có thể đếm trùng; ưu tiên thống kê `gc-pauses` hoặc field pause tổng hợp của GC event.

## 7. Dùng các JFR view có sẵn

JDK 24 cung cấp các view để tổng hợp event mà không cần tự parse file.

| View | Nội dung |
| --- | --- |
| `gc` | GC ID, loại collection, heap before/after và longest pause |
| `gc-pauses` | Tổng pause, count, median, average, percentile và maximum |
| `gc-parallel-phases` | Các pha GC parallel |
| `gc-concurrent-phases` | Các pha GC concurrent |
| `gc-cpu-time` | CPU time dành cho GC |
| `gc-references` | Thống kê xử lý reference |
| `gc-configuration` | Cấu hình collector |
| `heap-configuration` | Cấu hình heap |
| `safepoints` | Thống kê safepoint, hỗ trợ phân biệt pause GC với các safepoint khác |

Ví dụ:

```bash
jfr view gc gc-analysis.jfr
jfr view gc-pauses gc-analysis.jfr
jfr view gc-concurrent-phases gc-analysis.jfr
jfr view gc-parallel-phases gc-analysis.jfr
jfr view gc-cpu-time gc-analysis.jfr
jfr view gc-references gc-analysis.jfr
jfr view safepoints gc-analysis.jfr
```

`jfr view gc` giúp tìm collection bất thường. Sau đó chuyển sang `gc-pauses` để đánh giá tác động latency, hoặc `gc-concurrent-phases` để xem collector đã làm việc nền trong bao lâu.

## 8. Phân tích GC bằng jfr summary và jfr print

Bắt đầu bằng summary để biết recording có những event nào và số lượng từng loại:

```bash
jfr summary gc-analysis.jfr
```

Một số dòng có thể xuất hiện:

```text
Event Type                         Count
----------------------------------------
jdk.GCPhaseConcurrent               ...
jdk.GCHeapSummary                   ...
jdk.GCPhasePause                    ...
jdk.GarbageCollection               ...
jdk.ObjectAllocationSample          ...
jdk.YoungGarbageCollection          ...
jdk.OldGarbageCollection            ...
```

Số lượng event phase thường lớn hơn số collection. Một GC có thể tạo nhiều phase event, nhiều heap summary và nhiều event collector-specific. Không dùng tổng số `GCPhasePause` hoặc `GCPhaseConcurrent` để suy ra số chu kỳ GC.

In các event cần thiết:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.GCPhasePause,jdk.GCPhaseConcurrent gc-analysis.jfr
```

In allocation samples và stack trace:

```bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 32 gc-analysis.jfr
```

In event của một collector cụ thể khi JDK có hỗ trợ:

```bash
jfr print --events jdk.G1GarbageCollection,jdk.G1HeapSummary,jdk.EvacuationInformation gc-analysis.jfr
```

Có thể lọc theo category:

```bash
jfr print --categories "GC" gc-analysis.jfr
```

Dùng `jfr metadata --events <event-name>` để kiểm tra field và mô tả của event trên đúng JDK. Tên event và field có thể thay đổi theo phiên bản hoặc collector.

## 9. Phân tích allocation pressure

GC thường xuyên có thể do ứng dụng tạo nhiều object, kể cả khi không có memory leak.

`jdk.ObjectAllocationSample` là event lấy mẫu allocation. Các trường quan trọng:

- `objectClass`: class của object được sample.
- `weight`: dung lượng tương đối mà sample đại diện.
- `eventThread`: thread thực hiện allocation.
- `stackTrace`: call stack tại nơi sample được ghi.

Trường `weight` giúp tổng hợp thống kê allocation theo class, thread hoặc stack trace. Đây là mẫu có trọng số, không phải danh sách chính xác từng object được cấp phát.

Các view hữu ích:

```bash
jfr view allocation-by-class gc-analysis.jfr
jfr view allocation-by-site gc-analysis.jfr
jfr view allocation-by-thread gc-analysis.jfr
jfr view thread-allocation gc-analysis.jfr
```

Cách phân tích:

1. Tìm class có allocation weight cao.
2. Xem thread nào tạo nhiều allocation.
3. Mở allocation-by-site để tìm method và stack trace.
4. Đối chiếu thời điểm allocation với các young GC và pause.
5. Kiểm tra code tạo object trong loop, serialize/deserialize, logging, mapping hoặc tạo buffer.
6. Xem object có được giữ lại lâu hay chỉ tạo rồi thu hồi nhanh.

Allocation pressure và memory leak là hai vấn đề khác nhau. Một method có thể tạo hàng triệu object ngắn hạn nhưng heap sau GC vẫn ổn định. Ngược lại, một cache tạo ít object nhưng giữ chúng mãi có thể làm live set tăng dần.

## 10. Đọc tenuring, promotion và reference processing

Một số event chi tiết giúp hiểu object sống qua nhiều chu kỳ GC.

**`jdk.TenuringDistribution`** ghi tuổi object và dung lượng ở từng age. Nếu nhiều object sống qua young GC và được promote sang old generation, old gen có thể tăng nhanh hơn.

**`jdk.GCReferenceStatistics`** ghi số reference được xử lý theo loại. Reference processing có thể làm tăng thời gian GC khi ứng dụng sử dụng nhiều `SoftReference`, `WeakReference`, `PhantomReference` hoặc cấu trúc liên quan.

**`jdk.EvacuationInformation`** có thể cung cấp dữ liệu collection set, vùng được giải phóng và bytes copied, đặc biệt hữu ích với G1.

Khi thấy promotion tăng:

- Kiểm tra cache, session, queue và collection giữ object.
- So sánh old-gen occupancy sau các chu kỳ GC.
- Tìm object có tuổi cao hoặc retained size lớn.
- Kiểm tra object có được giữ bởi static field, listener, ThreadLocal hoặc reference chain không.

Khi thấy reference processing tăng:

- Xác định loại reference chiếm số lượng lớn.
- Kiểm tra thư viện/cache sử dụng reference.
- Đánh giá thời gian xử lý reference cùng pause phases.
- Không thay đổi loại reference chỉ dựa vào một event count.

Các event chi tiết có thể bị tắt trong recording settings hoặc không có trên collector đang chạy.

## 11. Nhận diện các mẫu GC thường gặp

### Young GC nhiều nhưng heap sau GC ổn định

Có thể ứng dụng đang có allocation rate cao nhưng object chủ yếu sống ngắn. Kiểm tra allocation-by-site, GC frequency và throughput trước khi thay đổi heap hoặc collector.

### Old Gen tăng sau nhiều chu kỳ

Nếu heap sau GC tăng đều trong workload tương tự, có thể live set đang lớn dần. Tìm class có allocation/retention bất thường và dùng heap dump hoặc old-object sampling để tìm đường tham chiếu.

### Pause dài hoặc P99 tăng

Kiểm tra GC ID có longest pause cao, cause, GCPhasePause và các phase con. Đối chiếu heap occupancy, promotion, evacuation và safepoints cùng thời điểm.

### Concurrent phase kéo dài nhưng pause ngắn

Collector có thể đang thực hiện nhiều công việc nền. Ứng dụng không nhất thiết bị pause trong toàn bộ khoảng đó. Kiểm tra GC CPU time, CPU saturation/throttling và thời gian concurrent phase.

### Full/old collection thường xuyên

Kiểm tra old-gen occupancy, allocation rate, promotion, heap max và GC cause. Một chu kỳ old collection không tự động có nghĩa memory leak.

### GC pause thấp nhưng latency ứng dụng vẫn cao

Nguyên nhân có thể nằm ở lock contention, I/O, scheduler, safepoint khác, CPU throttling hoặc dependency bên ngoài. Dùng thêm JFR thread, monitor, socket, file và safepoint events để tìm nguyên nhân.

## 12. Phân biệt allocation pressure và memory leak

| Dấu hiệu | Allocation pressure | Memory leak/retention |
| --- | --- | --- |
| Allocation samples | Cao | Có thể cao hoặc thấp |
| Young GC frequency | Có thể tăng | Có thể tăng |
| Heap sau GC | Thường ổn định khi workload ổn định | Có xu hướng tăng qua thời gian |
| Old Gen | Có thể ổn định | Có thể tăng liên tục |
| Object lifetime | Nhiều object ngắn hạn | Object không cần thiết vẫn reachable |
| Cách điều tra | Allocation-by-site/thread/class | Heap dump, old-object sample, GC roots |

Một quy trình phân biệt:

1. Thu JFR qua một khoảng workload đại diện.
2. So sánh allocation rate và GC frequency.
3. Theo dõi heap sau GC qua nhiều chu kỳ.
4. Nếu post-GC baseline ổn định, ưu tiên điều tra allocation pressure/throughput.
5. Nếu baseline tăng, kiểm tra class retained, old-object samples và heap dump.
6. Dùng MAT để xem dominator tree, retained size và path to GC roots.
7. Lặp lại recording sau khi sửa để xác minh.

JFR `ObjectAllocationSample` cho biết nơi tạo allocation; nó không tự chứng minh object còn sống. Muốn tìm object bị giữ lại, cần dữ liệu retention và reference graph.

## 13. Ghi JFR để phân tích GC

Liệt kê JVM:

```bash
jcmd -l
```

Kiểm tra trợ giúp command:

```bash
jcmd 18420 help JFR.start
```

Bắt đầu recording trong 60 giây:

```bash
jcmd 18420 JFR.start name=gc-analysis settings=profile duration=60s filename=/var/tmp/gc-analysis.jfr
```

Kiểm tra recording:

```bash
jcmd 18420 JFR.check name=gc-analysis
```

Khi hết thời lượng, JFR tự kết thúc và ghi file. Sau đó:

```bash
jfr summary /var/tmp/gc-analysis.jfr
jfr view gc /var/tmp/gc-analysis.jfr
jfr view gc-pauses /var/tmp/gc-analysis.jfr
```

Nếu muốn ghi liên tục và chủ động chụp snapshot:

```bash
jcmd 18420 JFR.start name=gc-live settings=default disk=true maxage=30m maxsize=256m
jcmd 18420 JFR.dump name=gc-live filename=/var/tmp/gc-snapshot.jfr
jcmd 18420 JFR.stop name=gc-live filename=/var/tmp/gc-final.jfr
```

`JFR.dump` xuất dữ liệu hiện có trong khi recording tiếp tục; `JFR.stop` kết thúc recording và ghi dữ liệu còn lại.

**Chọn settings:**

- `default.jfc`: thu thập tập event dựng sẵn với overhead thấp, phù hợp recording liên tục.
- `profile.jfc`: thu thập nhiều dữ liệu hơn, overhead cao hơn; dùng trong khoảng ngắn khi cần phân tích sâu.
- Có thể xem tùy chọn và event settings bằng `jcmd <pid> help JFR.start` và `jfr configure`.

`JFR.start` có Impact phụ thuộc settings. Đừng mặc định dùng profile recording liên tục trên production. Đặt `maxage` và `maxsize` khi cần giới hạn dữ liệu lưu trên disk.

Đường dẫn file nên là thư mục tồn tại và JVM có quyền ghi. Với command line `jcmd`, dùng đường dẫn đơn giản, không có khoảng trắng để tránh parser tách filename thành nhiều arguments.

## 14. Thu thập GC roots khi nghi ngờ memory leak

JFR có tùy chọn `path-to-gc-roots` để ghi đường tham chiếu tới GC roots cho object được theo dõi trong recording.

Ví dụ:

```bash
jcmd 18420 JFR.start name=gc-roots settings=profile path-to-gc-roots=true duration=60s filename=/var/tmp/gc-roots.jfr
```

Thông tin GC roots hữu ích khi điều tra vì sao object vẫn reachable. Tuy nhiên, việc thu thập path có thể tốn thời gian và tài nguyên. Chỉ bật khi đã có nghi ngờ memory leak và cần dữ liệu retention sâu hơn.

Không coi JFR path-to-GC-roots là thay thế hoàn toàn heap dump. Với object graph lớn hoặc cần xem retained size/dominator tree, heap dump và MAT vẫn là công cụ phù hợp.

## 15. Kết hợp JFR với GC unified logging

JFR phù hợp cho phân tích event, allocation, stack trace và timeline. GC log hữu ích khi cần log văn bản chi tiết, liên tục hoặc đối chiếu cấu hình collector.

Bật GC và safepoint logging khi khởi động JVM:

```bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

Có thể phân tích:

- Thời điểm GC và collector.
- Heap occupancy trước/sau collection.
- Các phase và pause.
- Safepoint synchronization.
- Thông tin region/evacuation của collector nếu được log.

JFR và GC log bổ sung cho nhau. Dùng JFR để lọc event và tìm stack trace; dùng GC log để đối chiếu chi tiết theo cấu hình unified logging.

## 16. Ví dụ thực hành Java 17: tạo allocation để phân tích GC

Ví dụ này tạo allocation ngắn hạn và giữ một số byte array trong danh sách có giới hạn. Mục tiêu là tạo GC activity có thể quan sát, không phải benchmark.

Tệp **`GcWorkload.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class GcWorkload {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[] transientArray;

    private GcWorkload() {
    }

    public static void main(String[] args) throws Exception {
        long deadline = System.nanoTime() + 11_000_000_000L;
        long allocations = 0;

        while (System.nanoTime() < deadline) {
            for (int i = 0; i < 24; i++) {
                transientArray = new byte[256 * 1024];
                transientArray[0] = (byte) i;
                allocations++;
            }

            RETAINED.addLast(new byte[1024 * 1024]);
            if (RETAINED.size() > 12) {
                RETAINED.removeFirst();
            }

            Thread.sleep(50);
        }

        System.out.println("allocations=" + allocations);
        System.out.println("retainedChunks=" + RETAINED.size());
    }
}
```

Biên dịch:

```bash
javac --release 17 GcWorkload.java
```

Chạy với G1 và heap giới hạn, đồng thời ghi JFR trong 8 giây:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -XX:StartFlightRecording=filename=gc-analysis.jfr,settings=profile,duration=8s GcWorkload
```

Hai dòng stdout của chương trình trong một lần chạy kiểm thử:

```text
allocations=5088
retainedChunks=12
```

Số allocation thực tế thay đổi theo tốc độ máy và lịch scheduling; danh sách retained được giới hạn ở 12 chunk.

Sau khi chương trình hoàn tất, phân tích file:

```bash
jfr summary gc-analysis.jfr
jfr view gc gc-analysis.jfr
jfr view gc-pauses gc-analysis.jfr
jfr view allocation-by-site gc-analysis.jfr
jfr view allocation-by-class gc-analysis.jfr
```

Tìm `byte[]` trong allocation view và kiểm tra stack trace có trỏ về `GcWorkload.main` hay không. Trong GC view, so sánh heap before/after và longest pause. Trong GC pauses view, xem percentile thay vì chỉ nhìn average.

Để xem event chi tiết:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.GCPhasePause,jdk.GCPhaseConcurrent,jdk.ObjectAllocationSample gc-analysis.jfr
```

Mở file `gc-analysis.jfr` bằng JMC để xem timeline, chọn một GC event và lần theo các phase cùng GC ID.

## 17. Phân tích bằng Java Mission Control

Java Mission Control (JMC) cung cấp giao diện để mở file `.jfr` và phân tích event theo timeline.

Quy trình cơ bản:

1. Mở JMC và chọn recording.
2. Xem trang Garbage Collections để kiểm tra GC count, pause và heap.
3. Chọn một collection có longest pause cao.
4. Mở event details và xem cause, collector, GC ID.
5. Kiểm tra các pause/concurrent phases của cùng GC ID.
6. Chuyển sang Allocation để tìm class, thread và stack trace tạo nhiều object.
7. Đối chiếu heap before/after và xu hướng old generation.
8. Lưu nhận định cùng khoảng thời gian và workload đã ghi.

JMC hiển thị được nhiều event detail và biểu đồ liên kết. Tên trang và cách trình bày có thể khác theo phiên bản JMC. Các event không được bật trong recording sẽ không xuất hiện đầy đủ trong giao diện.

## 18. Những sai lầm thường gặp khi phân tích GC bằng JFR

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Coi `GarbageCollection.duration` là pause time | Duration có thể gồm cả concurrent work | Đọc `sumOfPauses`, `longestPause` và `GCPhasePause` |
| Chỉ xem average pause | Average che khuất tail latency | Xem P95/P99/P99.9 và maximum |
| Coi mỗi `GCPhasePause` là một GC cycle | Một cycle có thể có nhiều phase/pause | Dùng GC ID và `GarbageCollection` |
| Dùng số event phase làm GC count | Event phase có thể nhiều hơn collection | Dùng `jdk.GarbageCollection` hoặc `jfr view gc` |
| Coi allocation sample là số object chính xác | `ObjectAllocationSample` là thống kê có trọng số | Đọc sample weight và xem xu hướng theo class/site/thread |
| Kết luận leak từ heap tăng trước GC | Object chưa được thu hồi có thể vẫn nằm trong heap | So sánh post-GC baseline qua nhiều chu kỳ |
| Coi heap after GC là live set tuyệt đối | Collector và allocation concurrent ảnh hưởng snapshot | Đối chiếu heap summary, old-gen, retention và heap dump |
| Chỉ xem GC mà bỏ qua CPU | Concurrent GC có thể bị chậm do CPU contention/throttling | Xem GC CPU time, CPU load và safepoints |
| Dùng `profile` liên tục | Profile có overhead cao hơn default | Dùng default cho recording dài, profile cho khoảng ngắn |
| So sánh hai recording khác workload | Tải khác nhau làm GC metrics khác nhau | So sánh cùng workload, heap và môi trường |
| Tuning nhiều flag cùng lúc | Không xác định được thay đổi nào tạo tác động | Đổi từng yếu tố và đo lại |

## 19. Quy trình điều tra GC trong production

1. Xác định triệu chứng: latency spike, CPU cao, heap tăng, GC quá thường xuyên hay OutOfMemoryError.
2. Ghi lại JDK version, collector, heap min/max, container limit và workload.
3. Bắt đầu recording bằng `default` hoặc `profile` theo thời lượng phù hợp.
4. Kiểm tra `jfr summary` để xác nhận recording có GC events.
5. Dùng `jfr view gc` để tìm collection bất thường và heap before/after.
6. Dùng `jfr view gc-pauses` để xem pause count, P95/P99 và maximum.
7. Dùng `gc-concurrent-phases` và `gc-cpu-time` để đánh giá công việc nền.
8. Dùng allocation-by-site/class/thread để tìm nguồn allocation pressure.
9. Kiểm tra cause, tenuring, reference processing và collector-specific events.
10. Nếu post-GC live set tăng, cân nhắc old-object sampling hoặc heap dump/MAT.
11. Đối chiếu GC events với application latency, CPU, safepoint, log và deployment.
12. Đề xuất một thay đổi có giả thuyết rõ ràng, đo lại dưới cùng workload và so sánh trước/sau.
13. Bảo vệ file `.jfr`, GC log và heap dump; xóa hoặc lưu theo retention policy.

Không thay đổi collector hoặc heap flags chỉ vì một lần pause cao. Trước tiên cần biết vấn đề đến từ allocation rate, live set, pause phase, CPU contention hay cấu hình tài nguyên.

## 20. Ghi nhớ

- JFR ghi nhận GC event theo timeline và liên kết các pha bằng GC ID.
- `jdk.GarbageCollection` cho biết collector, cause, duration, sumOfPauses và longestPause.
- `jdk.GCHeapSummary` ghi heap before/after; `GCPhasePause` và `GCPhaseConcurrent` phân biệt công việc dừng ứng dụng với công việc nền.
- `jfr view gc` tổng hợp collection; `jfr view gc-pauses` cung cấp pause distribution và percentile.
- Dùng P95/P99/maximum khi điều tra latency; không chỉ nhìn average.
- `ObjectAllocationSample` có trọng số và stack trace, hữu ích để tìm allocation pressure nhưng không chứng minh object bị giữ lại.
- `TenuringDistribution`, `GCReferenceStatistics` và `EvacuationInformation` giúp điều tra promotion, reference processing và G1 evacuation.
- Heap after GC tăng qua nhiều chu kỳ có thể là dấu hiệu retention; cần heap dump/GC roots để xác định nguyên nhân.
- `default.jfc` phù hợp recording dài với overhead thấp; `profile.jfc` thu thập nhiều dữ liệu hơn nhưng overhead cao hơn.
- Kết hợp JFR, JMC, GC unified logging, heap dump và metrics để có kết luận đáng tin cậy.
- Đánh giá thay đổi GC bằng workload tương đương và thay đổi từng yếu tố một.

Phân tích Garbage Collection bằng JFR giúp bạn chuyển từ nhận xét “GC chạy nhiều” sang bằng chứng cụ thể về cause, pause percentile, heap trend, allocation site và các pha collector. Từ đó có thể xác định đúng hướng điều tra và cải thiện latency/throughput dựa trên dữ liệu đo được.

## Tài liệu tham khảo

- [Java Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- [JFR Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [jcmd Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Garbage-First Garbage Collector Tuning — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html)
