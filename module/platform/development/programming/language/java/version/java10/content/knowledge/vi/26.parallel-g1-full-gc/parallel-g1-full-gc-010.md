# Phân tích tốc độ cấp phát, dữ liệu sống và áp lực bộ nhớ trong G1 GC (Java 10+)

## 1. Mục tiêu bài học

**G1 (Garbage-First Garbage Collector)** chia heap thành các **region**, ưu tiên thu hồi vùng chứa nhiều rác và cố cân bằng throughput với mục tiêu độ dài tạm dừng. Ở **Java 10**, **JEP 307 — Parallel Full GC for G1** làm đường **Full GC** của G1 thực thi **song song** thay vì chỉ một luồng như phiên bản trước, giúp giảm worst-case pause trong một số trường hợp phải thu gom toàn heap. Cơ chế này tiếp tục hiện diện trong các JDK hiện hành.

Nhưng một thay đổi về **thuật toán Full GC** không thể giải quyết nguyên nhân ứng dụng thiếu bộ nhớ:

- Full GC vẫn là **stop-the-world**, không phải concurrent GC.
- GC không thu hồi được đối tượng **còn reachable**.
- Nếu ứng dụng cấp phát quá nhanh, giữ nhiều đối tượng lâu hoặc tạo các mảng rất lớn, G1 vẫn có thể thiếu nơi chuyển đối tượng và bị buộc phải Full GC.
- Mục tiêu vận hành là **hạn chế cần Full GC**, không chỉ tăng số luồng khi Full GC đã xuất hiện.

Để chẩn đoán, phải phân tích ba góc nhìn:

1. **Allocation rate** — số byte đối tượng mới được cấp phát mỗi giây.
2. **Live data/live set** — những đối tượng vẫn còn sống và phải được giữ/di chuyển khi GC.
3. **Memory pressure** — áp lực thực lên young, old, vùng dự phòng để evacuate, thời gian concurrent marking và giới hạn heap/container.

Bài học dùng **Java 17+** để chạy code và các công cụ **Unified GC Logging, JFR, jcmd, jstat, MXBeans** đang được hỗ trợ. Những kiến thức về G1 ở Java 10 chỉ là bối cảnh phiên bản; không sử dụng các cờ logging cũ đã được thay thế.

Sau bài này, bạn sẽ biết phân biệt churn với retention, đọc dòng `Pause Full (G1 Compaction Pause)`, xem eden/survivor/old/humongous regions, phân tích evacuation failure, đánh giá khi nào tăng heap/giảm allocation có ích, và kiểm chứng bằng chương trình Java có đầu ra xác định.

## 2. G1 làm gì với một đối tượng mới?

Sơ đồ khái niệm:

~~~text
Ứng dụng tạo object
    |
    +--- object thường --------> Eden regions (young)
    |                                  |
    |                         Young GC (stop-the-world)
    |                           /                 \
    |                   Không còn sống          Còn sống
    |                      thu hồi             evacuate/copy
    |                                               |
    |                                      Survivor hoặc Old
    |
    +--- object humongous ---> Old/Humongous regions
                                           |
                                  Concurrent marking
                                           |
                                      Mixed GC
                                           |
                              Thu hồi old regions phù hợp
                                           |
                           Nếu thiếu chỗ để tiếp tục cấp phát
                                           |
                                   Full GC (fallback)
~~~

Các đối tượng thường được cấp phát tại **eden**. Ở young GC, G1 xử lý những region trẻ, copy các object còn sống vào survivor/old rồi có thể tái sử dụng các region nguồn. Những object chết không cần copy.

Khi lượng dữ liệu ở old tăng đủ nhiều, G1 bắt đầu **concurrent marking** để xác định các region già có tỷ lệ rác phù hợp; sau đó **mixed collections** có thể thu hồi old region từng bước thay vì đợi đến khi heap hết chỗ.

**Humongous object** là đối tượng có kích thước **lớn hơn hoặc bằng một nửa G1 region** theo định nghĩa JDK hiện hành. Chúng thường được cấp phát trực tiếp vào một chuỗi region liên tục trong old generation, không đi theo đường eden/survivor thông thường.

### Loại GC nào đang được nói đến?

| Loại / pha | Công việc chính | Có tạm dừng ứng dụng? |
| --- | --- | --- |
| **Young GC** | Evacuate young regions | Có, stop-the-world |
| **Concurrent marking** | Phân tích liveness của heap/old | Chủ yếu đồng thời; có các pha ngắn dừng ứng dụng |
| **Mixed GC** | Evacuate young cộng một số old region đã chọn | Có, stop-the-world theo từng bước |
| **Full GC** | Thu gom/nén toàn heap khi cần cứu vãn | Có, thường là pause nặng |

Đừng gộp **mixed** và **Full** chỉ vì cả hai có đụng tới old generation. Khi đo latency, hãy phân loại theo tên sự kiện trên log thay vì dùng từ “major GC” không có hợp đồng thống nhất giữa collector và công cụ.

## 3. G1 Full GC song song từ Java 10: đúng và sai

**JEP 307** song song hóa các công việc thích hợp trong đường Full GC của G1, làm giảm thời gian pause xấu nhất so với thuật toán Full GC đơn luồng trước đó. Khi dùng G1 trên Java hiện đại, các pha song song có thể sử dụng worker do JVM lựa chọn; `-XX:ParallelGCThreads` là một trong các cờ liên quan.

Ví dụ:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx128m -XX:ParallelGCThreads=4 -Xlog:gc* -cp classes G1PressureDemo retain
~~~

- `-XX:+UseG1GC`: chọn G1 rõ ràng.
- `-Xms`/`-Xmx`: giới hạn heap; đây là số byte **heap**, không phải toàn bộ bộ nhớ tiến trình.
- `-XX:ParallelGCThreads`: số worker cho những công việc GC song song, **không riêng** Full GC.
- `-Xlog:gc*`: quan sát các sự kiện GC hiện hành.

**Không được suy ra rằng câu lệnh trên chắc chắn tạo Full GC.** G1 có thể hoàn tất chương trình chỉ với young GC hoặc không có GC đáng kể tùy runtime/workload.

Song song hóa **không**:

- Biến Full GC thành concurrent process.
- Tạo thêm heap vượt `-Xmx`.
- Giải phóng đối tượng còn được giữ bởi cache, queue, static map.
- Bảo đảm pause dưới một thời hạn cứng.
- Làm toàn bộ GC khác trở thành “chạy bao nhiêu thread cũng nhanh”.

Mục tiêu đúng: hiểu vì sao G1 phải dừng để compact **toàn bộ heap** và làm giảm nhu cầu đó.

## 4. Allocation rate — đo tốc độ tạo object, không đo tăng heap used

**Tốc độ cấp phát** được định nghĩa:

~~~text
allocationRate = allocatedBytesInWindow / elapsedSeconds
~~~

Ví dụ ứng dụng tạo **2 GiB đối tượng trong 10 giây**:

~~~text
2 × 1024 MiB / 10 s = 204.8 MiB/s
~~~

Đây là **tổng byte đã cấp phát** trong cửa sổ, kể cả những đối tượng bị thu hồi ngay sau đó. Không lấy chênh lệch hai ảnh chụp `heap used` thay cho tổng cấp phát.

Một trường hợp giả định:

~~~text
Tại t=0: heap used = 200 MiB
Trong 10 s: tạo 2048 MiB đối tượng
Trong 10 s: nhiều đợt GC thu hồi 1950 MiB
Tại t=10: heap used ≈ 298 MiB
~~~

Dù used tăng khoảng 98 MiB, tổng allocation vẫn là khoảng 2048 MiB. Những con số trên chỉ minh họa, chưa tính các tương tác khác.

### Thread-local allocation buffers (TLAB)

Đa số các object nhỏ được cấp phát qua **TLAB** để hạn chế đồng bộ. Object lớn hoặc trường hợp đặc thù có thể nằm ngoài TLAB. Khi đo per-thread allocation, cần hiểu:

- Số byte **cấp phát** không đồng nghĩa số byte **còn sống**.
- Kết quả allocation từ một thread thường cần tính chênh lệch theo thời gian.
- Event JFR `jdk.ObjectAllocationSample` lấy mẫu, không phải ghi lại từng allocation.
- Một số event JFR theo TLAB cũng có chính sách lấy mẫu/gắn sự kiện đặc thù, không được đếm trực tiếp thành toàn bộ byte thực một cách ngây thơ.

Cách tìm **class/stack gây allocation cao** là dùng JFR/JDK Mission Control. Nếu cần tổng byte theo thread, xem `jdk.ThreadAllocationStatistics` hoặc `com.sun.management.ThreadMXBean` trong môi trường HotSpot có hỗ trợ; bảo đảm đối chiếu rõ thời gian và phạm vi đo.

## 5. Live set — điều gì thực sự còn sống?

**Live object** là đối tượng mà GC đánh giá vẫn reachable từ **GC roots** (thread stacks, static fields, JNI roots và những nguồn tham chiếu liên quan). Chúng không được thu hồi khi vẫn còn được dùng theo reachability semantics.

Ví dụ trong một phương thức:

~~~java
byte[] payload = new byte[4096];
cache.put("request", payload);
~~~

Nếu `cache` giữ tham chiếu lâu dài, mảng có thể còn sống qua nhiều GC. Nếu cache loại bỏ entry và không còn root nào giữ nó, mảng có thể đủ điều kiện thu hồi.

Phân biệt bốn thuật ngữ:

| Thuật ngữ | Nghĩa | Lưu ý |
| --- | --- | --- |
| **Allocated bytes** | Tổng số byte được cấp phát trong một khoảng thời gian | Có thể lớn hơn nhiều so với heap size |
| **Live set** | Những dữ liệu cần giữ vì còn reachable | Không đọc trực tiếp từ một mẫu young-GC log |
| **Occupied/used heap** | Byte đang chiếm dụng theo phép đo JVM tại một thời điểm | Có thể chứa rác ở old chưa được thu hồi |
| **Retained size** | Dung lượng bị giữ lại qua tham chiếu tới một object/root cụ thể | Dùng khi phân tích leak với heap dump/dominator tree |

Một số liệu `heap used after Young GC` **không phải live set chính xác của toàn heap**: old generation có thể vẫn chứa object không còn reachable nhưng chưa được mixed/full GC thu hồi.

### Sự khác nhau giữa leak và cache warm-up

- **Cache warm-up:** live baseline tăng một thời gian rồi đạt giới hạn ổn định đúng thiết kế.
- **Memory leak/retention bất thường:** số object còn giữ tăng không cần thiết hoặc không quay về mức mong muốn, kể cả khi workload đã ổn định.
- **Temporary backlog:** queue tăng trong một burst rồi giảm khi consumer xử lý xong; nếu backlog không giảm có thể trở thành áp lực lâu dài.

Một lần Full GC **không đủ** để khẳng định leak. Cần theo dõi **xu hướng qua nhiều chu kỳ**, cộng với heap dump/GC roots và hành vi ứng dụng.

## 6. Memory pressure không chỉ bằng phần trăm heap used

Áp lực bộ nhớ của G1 đến từ **kết hợp nhiều yếu tố**:

1. **Live-set floor:** bao nhiêu object thật sự phải giữ.
2. **Allocation rate:** young regions lấp đầy nhanh đến mức nào.
3. **Promotion/old allocation rate:** old regions bị dùng nhanh bao nhiêu.
4. **Free regions để evacuation:** có đủ chỗ copy live objects ra khỏi region nguồn?
5. **Marking duration:** concurrent marking có xong trước lúc old quá chật?
6. **Humongous fragmentation:** có đủ các region **liên tiếp** cho object lớn?
7. **Tài nguyên CPU:** marking/evacuation có đủ CPU, hay bị throttling?
8. **Heap size và container limit:** `-Xmx` cùng các vùng native/metadata còn nằm trong ngân sách thực tế không?

Một heap 80% đã ổn định có thể chưa khẩn cấp bằng heap 65% đang tăng nhanh với eviction/backpressure thất bại. Luôn đọc **đường xu hướng**, không dựa vào một con số “used 80%” để tự kết luận.

### Heap tối đa, committed và RSS khác nhau

~~~text
max heap       giới hạn Java heap do -Xmx
committed heap bộ nhớ heap được JVM yêu cầu/commit
used heap      bộ nhớ chiếm dụng tại thời điểm đo
process RSS    bộ nhớ resident của toàn tiến trình, kể cả phần ngoài heap
~~~

Tăng `-Xmx` có thể giúp GC có nhiều chỗ hơn, nhưng nếu container memory quá nhỏ, JVM có thể bị hệ điều hành giết vì **native/total RSS**, ngay cả khi chưa ném `java.lang.OutOfMemoryError: Java heap space`.

## 7. Survival và promotion: tại sao dữ liệu sống mới gây áp lực old

Sau young GC:

- Object chết trong eden → region có thể tái sử dụng.
- Object sống → copy sang survivor, hoặc **promote** sang old tùy tuổi/kích cỡ/quyết định của G1.
- Object humongous → thường cấp phát trực tiếp qua old/humongous regions.

Hai đại lượng khái niệm:

~~~text
survivalRatio ≈ survivingBytesYoung / relevantYoungBytes
promotionRate ≈ promotedBytes / elapsedSeconds
~~~

**Đây không phải công thức luôn có thể điền thẳng từ một dòng GC log.** G1 có adaptive sizing và những lần GC/region với tập collection khác nhau. Muốn nói “promotion X MiB/s” cần quan sát dữ liệu có semantics phù hợp hoặc profiler đo đúng.

Ví dụ hai workload có cùng allocation 200 MiB/s:

| Đặc trưng | A: dữ liệu ngắn hạn | B: nhiều retention |
| --- | --- | --- |
| Allocation rate | 200 MiB/s | 200 MiB/s |
| Đối tượng chết ở young | Nhiều | Ít hơn |
| Survival/promotion | Thường thấp | Có thể cao |
| Old occupancy | Có thể ổn định | Có thể tăng dần |
| Rủi ro Full GC | Không tự phát sinh chỉ vì allocation cao | Tăng nếu reclaim không theo kịp |

**High allocation ≠ memory leak.** Nhưng allocation lớn có thể tạo nhiều young pauses, tăng CPU GC, ảnh hưởng throughput dù old ổn định. Cần đánh giá **latency và throughput** cùng memory pressure.

## 8. G1 marking, mixed GC và thời gian chờ

G1 không nhất thiết thu hồi old ngay khi object old trở thành rác. Nó thực hiện **concurrent marking** để xác định old regions nào đáng thu hồi, rồi thu gom chúng trong các **mixed GC**.

Quy trình khái niệm:

~~~text
Old occupancy tăng
       |
       v
Đạt ngưỡng khởi động marking (IHOP)
       |
       v
Concurrent Start → Concurrent Marking → Remark/Cleanup
       |
       v
Space-Reclamation phase (mixed collections)
       |
       v
Old regions có nhiều rác được thu hồi
~~~

**IHOP (Initiating Heap Occupancy Percent)** có cơ chế điều chỉnh **adaptive** theo hành vi workload trong JDK hiện hành. Nếu app chuyển đột ngột sang lưu dữ liệu lâu hơn hoặc tạo humongous objects, ngưỡng dự đoán có thể không theo kịp.

Nếu lượng object đi vào old tăng nhanh khi marking chưa xong, G1 có thể thiếu chỗ để evacuate và rơi vào Full GC.

**Không nên phản xạ tắt adaptive IHOP hoặc giảm ngưỡng thủ công** chỉ sau một lần GC bất thường. Hãy xác nhận timeline: marking bắt đầu khi nào, chạy bao lâu, tăng old/humongous ở đâu, có bị thiếu CPU không.

## 9. Humongous objects và fragmentation

Trong G1 hiện hành, object có kích thước **ít nhất một nửa G1 region** được coi là **humongous**.

Ví dụ region size 2 MiB: object thực kích thước khoảng 1 MiB trở lên có thể thuộc nhóm humongous. Kích thước object thật gồm header và alignment, không chỉ `byte[].length`.

Đặc điểm cần nhớ:

- Humongous object thường nằm trong **một chuỗi region liên tiếp** của old.
- Phần trống ở region cuối có thể bị lãng phí trong lúc object còn sống.
- Trong các pha thu gom bình thường, G1 thường không di chuyển chúng như object nhỏ; có các cơ chế reclaim đặc biệt.
- Cấp phát humongous có thể kích hoạt GC sớm khi vượt các ngưỡng quan sát.
- Thậm chí còn free heap tổng thể vẫn có thể không đủ **region liên tiếp** cho allocation mới.

Vì vậy khi gặp Full GC + `Humongous regions` tăng cao, hãy tìm những nơi cấp phát:

- `byte[]`/char buffer rất lớn.
- Đọc toàn bộ file/image/JSON payload khổng lồ thay vì streaming.
- Nén/giải nén tạo một buffer nguyên khối.
- Gom toàn bộ kết quả truy vấn thành một mảng lớn.

`-XX:G1HeapRegionSize` là một lựa chọn tuning cần cân nhắc **sau khi có dữ liệu**. Region lớn hơn có thể giảm số object được xếp humongous, nhưng thay đổi nhiều chi phí GC khác; không phải giải pháp mặc định thay cho sửa allocation.

## 10. Evacuation failure và Full GC

Trong young/mixed GC, G1 phải di chuyển **live objects** sang region đích. Khi không thể hoàn thành việc di chuyển, có thể thấy log dạng:

~~~text
Evacuation Failure: Allocation
Evacuation Failure: Pinned
Evacuation Failure: Allocation/Pinned
~~~

Trong tài liệu G1 hiện đại:

- **Allocation:** không có đủ vùng nhớ đích phù hợp để move object.
- **Pinned:** một số object bị cố định, chẳng hạn do native/JNI, không thể di chuyển tại thời điểm đó.

Đây là mô tả **trên JDK hiện hành**; không suy ngược rằng mọi chi tiết về `Pinned` đã có ở Java 10. Đối với chủ đề **G1 Full GC song song Java 10**, điều cần phân tích là liệu ứng dụng và G1 có đủ chỗ và tốc độ để thu hồi bộ nhớ **trước khi cần Full GC** không.

Một dòng Full GC thường có dấu:

~~~text
Pause Full (G1 Compaction Pause)
~~~

Full GC có thể xuất hiện sau evacuation failure, nhưng **không phải lúc nào cũng do allocation failure**: `System.gc()` hoặc công cụ ngoài có thể yêu cầu collection. Cần xem **GC cause và chuỗi sự kiện trước đó**, không kết luận từ một dòng đơn lẻ.

## 11. Đọc GC log: không nhầm occupancy với allocation

Một tập dòng **minh họa format**, không phải log của chương trình bên dưới:

~~~text
[3.50s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 220M->90M(512M) 14.2ms
[5.80s][info][gc] GC(13) Pause Young (Concurrent Start) (G1 Evacuation Pause) 310M->150M(512M) 17.0ms
[9.20s][info][gc] GC(18) Pause Young (Mixed) (G1 Evacuation Pause) 360M->190M(512M) 28.3ms
~~~

Cụm `220M->90M(512M)` chỉ **heap used trước → sau GC**, cùng kích thước heap mà log hiển thị; nó **không** đồng nghĩa:

- Tổng byte app đã cấp phát kể từ lần GC trước là 130 MiB.
- Dữ liệu sống toàn heap chính xác bằng 90 MiB.
- 130 MiB đều đã là object không còn reachable từ lâu.
- Full GC đã diễn ra (dòng trên thực ra là young GC).

Nếu muốn hiểu hiệu quả young/mixed GC, xem loại GC, mục tiêu, before/after, collection set, survivor/old/humongous regions và xu hướng nhiều lần GC.

### Các region trước/sau GC

Ví dụ minh họa:

~~~text
Eden regions:       35->0(40)
Survivor regions:    4->6(8)
Old regions:       110->112
Humongous regions:  8->8
~~~

- Eden vùng nguồn có thể được giải phóng sau young GC.
- Survivor/old có thể thay đổi do đối tượng được copy/promote.
- Humongous regions cho biết **số vùng được dùng cho đối tượng rất lớn**.

**Không lấy `Old regions: 110->112` để suy ra đúng hai region byte promotion.** Region count không phải một bộ đếm promotion bytes thuần túy; tác động của reclaim/chuyển vai trò và thời gian GC cần được xét.

## 12. Bộ công cụ chẩn đoán Java 17+

### 12.1. Unified GC Logging

Bật log có thông tin GC và heap:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx128m -Xlog:gc*,gc+heap=debug:file=gc.log:time,uptime,level,tags -cp classes G1PressureDemo churn
~~~

`-Xlog:gc*` ghi những sự kiện GC hiện hành. `gc+heap=debug` cung cấp thông tin region/heap chi tiết hơn trong phạm vi JVM hỗ trợ.

Nếu cần điều tra chuyên sâu hơn, dùng `-Xlog:gc*=debug` **tạm thời**, thu thập đúng cửa sổ lỗi rồi hạ mức log. Debug/trace GC có thể tạo file lớn và làm tăng overhead.

Không sử dụng các cờ legacy như `-XX:+PrintGCDetails` hoặc `-Xloggc:` như hướng dẫn mới; Unified Logging `-Xlog` là cách phù hợp.

### 12.2. jcmd và jstat

Với PID của JVM đang chạy:

~~~bash
jcmd <pid> GC.heap_info
jstat -gcutil <pid> 1000 10
~~~

- `GC.heap_info` phản ánh trạng thái heap tại thời điểm đọc, không phải live-set chính xác.
- `jstat -gcutil` lấy **10 mẫu cách nhau 1000 ms** để xem utilization/counter.
- Nếu chạy trong container, quyền attach, PID namespace và security configuration có thể hạn chế kết nối.

Không ép `jcmd <pid> GC.run` trên production chỉ để tạo một Full GC cho dễ đo — có thể gây pause lớn, thay đổi chính workload đang điều tra.

### 12.3. Java Flight Recorder (JFR)

Trên JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=allocation-profile settings=profile duration=60s filename=allocation.jfr
~~~

Sau khi có file `allocation.jfr`, phân tích bằng **JDK Mission Control**. Một số event hữu ích:

- `jdk.ThreadAllocationStatistics`: lượng allocation của các thread theo thời gian.
- `jdk.ObjectAllocationSample`: mẫu object allocation để tìm class/stack.
- `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB`: tín hiệu allocation trong/ngoài TLAB theo recording settings.
- `jdk.GarbageCollection` và `jdk.GCHeapSummary`: kết nối events GC với trạng thái heap.

**Lưu ý:** không phải mọi event đều bật trong mọi `.jfc` profile, và có event **sampling**. Đếm số event hay cộng kích thước của một mẫu chưa chắc bằng tổng allocation bytes thực. Với câu hỏi “đo chính xác bao nhiêu byte/giây”, phải chọn đúng metric có hợp đồng phù hợp.

### 12.4. MXBeans và heap dump

`MemoryMXBean` cung cấp used/committed/max của heap tại một thời điểm, `GarbageCollectorMXBean` cung cấp collection counts/times khi được hỗ trợ. Chúng không thay cho per-thread allocation counters.

Heap dump + **dominator tree** giúp xác định retained size và đường giữ tham chiếu từ GC roots; cần bảo vệ file dump vì nó có thể chứa **dữ liệu nhạy cảm** và tạo overhead đáng kể.

## 13. Chương trình Java 17+ phân biệt churn với retention

Chương trình sau chủ động tạo **cùng số byte payload** ở cả hai chế độ, nhưng chỉ một chế độ giữ một phần mảng trong một `List`:

- **churn**: tạo nhiều mảng, không đưa vào danh sách giữ lâu.
- **retain**: giữ 1/8 mảng mỗi batch, nên có thêm nhiều mảng vẫn reachable ở cuối phương thức.

Một trường `volatile` giữ ít nhất một mảng và giúp tránh tối ưu hóa loại bỏ các allocation không dùng.

Lưu file **G1PressureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1PressureDemo {
    private static volatile byte[] last;

    private static void run(String scenario) {
        boolean retain = "retain".equals(scenario);
        int batches = 6;
        int perBatch = 2048;
        int bytesPerArray = 4096;

        List<byte[]> held = new ArrayList<>();
        long requestedPayload = 0L;

        for (int batch = 0; batch < batches; batch++) {
            for (int i = 0; i < perBatch; i++) {
                byte[] block = new byte[bytesPerArray];
                block[0] = (byte) (batch + i);
                requestedPayload += block.length;

                if (retain && i % 8 == 0) {
                    held.add(block);
                } else {
                    last = block;
                }
            }
        }

        System.out.println("scenario: " + scenario);
        System.out.println("requested payload: "
                + requestedPayload / (1024 * 1024) + " MiB");
        System.out.println("retained arrays: " + held.size());
        System.out.println("retained payload: "
                + (held.size() * (long) bytesPerArray)
                / (1024 * 1024) + " MiB");
        System.out.println("last array bytes: " + last.length);
    }

    public static void main(String[] args) {
        String scenario = args.length == 0
                ? "churn" : args[0];

        if (!scenario.equals("churn")
                && !scenario.equals("retain")) {
            throw new IllegalArgumentException(
                    "Use churn or retain"
            );
        }

        run(scenario);
    }
}
~~~

Biên dịch:

~~~bash
mkdir classes
javac -d classes G1PressureDemo.java
~~~

Chạy trên JDK 17+:

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx64m -cp classes G1PressureDemo churn
java -XX:+UseG1GC -Xms64m -Xmx64m -cp classes G1PressureDemo retain
~~~

**Stdout chế độ churn:**

~~~text
scenario: churn
requested payload: 48 MiB
retained arrays: 0
retained payload: 0 MiB
last array bytes: 4096
~~~

**Stdout chế độ retain:**

~~~text
scenario: retain
requested payload: 48 MiB
retained arrays: 1536
retained payload: 6 MiB
last array bytes: 4096
~~~

Đầu ra logic đã được kiểm chứng bằng JDK. Nó **không** bao gồm dòng GC log; số sự kiện GC tùy runtime.

### Giải thích chi tiết

1. **6 × 2048 × 4096 byte = 48 MiB payload** là lượng mảng mà chương trình chủ động yêu cầu, bằng nhau ở hai chế độ.
2. `churn`: không giữ mảng trong `List`, nhưng `last` vẫn giữ một mảng. Vì vậy `retained arrays: 0` **không** có nghĩa toàn heap có 0 object sống.
3. `retain`: mỗi batch giữ 256 mảng → **1536 mảng**, tổng payload **6 MiB**.
4. `requested payload` **không phải số byte cấp phát JVM tuyệt đối**: object headers, alignment, backing array của `List` và các object runtime cũng chiếm bộ nhớ.
5. `retained payload` **không phải live set toàn heap**, chỉ là payload của các mảng được `held` giữ ở thời điểm in.
6. Thí nghiệm không chủ ý tạo Full GC; điều quan trọng là **cùng allocation khác retention**.

### Ghi log khi chạy hai chế độ

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx64m -Xlog:gc*,gc+heap=debug:file=churn-gc.log:time,uptime,level,tags -cp classes G1PressureDemo churn
java -XX:+UseG1GC -Xms64m -Xmx64m -Xlog:gc*,gc+heap=debug:file=retain-gc.log:time,uptime,level,tags -cp classes G1PressureDemo retain
~~~

So sánh loại GC, used heap trước/sau, old/humongous regions và pause. Vì chương trình nhỏ/chạy nhanh, log có thể không thể hiện đầy đủ áp lực old hoặc thậm chí không có Full GC. **Không cố tạo memory exhaustion bằng cách tăng vô hạn loop**; bài toán sản xuất cần workload đại diện, dài hơn và có giới hạn tài nguyên kiểm soát.

## 14. Một ví dụ định lượng: cùng allocation, old tăng khác nhau

Giả sử hai ứng dụng xử lý cùng số lượng request và đều tạo **6 GiB object trong 30 giây**.

~~~text
Allocation rate = 6 × 1024 MiB / 30 s = 204.8 MiB/s
~~~

Thông tin thu sau các chu kỳ GC **tương đương về trạng thái**:

| Chỉ số | Churn | Retention |
| --- | --- | --- |
| Allocation rate | 204.8 MiB/s | 204.8 MiB/s |
| Live baseline đầu cửa sổ (ước lượng) | 400 MiB | 400 MiB |
| Live baseline cuối cửa sổ (ước lượng) | 410 MiB | 700 MiB |
| Thay đổi live baseline | +10 MiB | +300 MiB |
| Diễn giải | Có thể gần ổn định | Phải điều tra retention |

Con số minh họa chỉ giúp suy luận. Live baseline **không** được phép ước lượng bằng một chênh lệch ngẫu nhiên giữa hai lần young GC khi old garbage chưa được thu hồi.

**Kết luận:** cùng byte cấp phát nhưng nếu nhiều object còn sống thì chi phí copy, promotion và old pressure có thể lớn hơn. Đó là lý do phải đo **live set và allocation rate cùng nhau**.

### Ước lượng thời gian còn chỗ — chỉ dùng như heuristic

~~~text
netGrowthRate ≈ (comparableLiveBaseline2 - comparableLiveBaseline1) / Δt
headroom ≈ Xmx - relevantOccupiedBytes - reserve
runway ≈ headroom / netGrowthRate, nếu netGrowthRate > 0
~~~

Đừng trình bày runway là số giây chắc chắn trước OOM: marking, reclamation, thay đổi tải, fragmentation/humongous, committed vs max, container limits và khả năng cấp phát có thể làm mô hình sai. Dùng như một **tín hiệu cảnh báo sớm** khi kết hợp thêm xu hướng khác.

## 15. Quy trình phân tích Full GC từng bước

**Bước 1 — xác nhận môi trường.** Thu JDK/vendor build, GC collector, heap flags, số CPU, memory limits, request throughput, thời gian lỗi.

**Bước 2 — bật log vừa đủ.** `-Xlog:gc*` và `gc+heap` là điểm bắt đầu tốt. Lưu timestamp để nối với request latency.

**Bước 3 — đo allocation rate.** Ưu tiên JFR/per-thread allocation counters. Ghi rõ đơn vị byte/s và cửa sổ đo.

**Bước 4 — xem post-GC occupancy.** Quan sát old regions và used heap sau **nhiều chu kỳ mixed/concurrent reclaim**; không gọi đó là live set chính xác nếu thiếu bằng chứng.

**Bước 5 — đo survival/promotion.** Xem log age/survivor, nguồn giữ object và old pressure. Phân biệt cache warm-up, backlog và leak.

**Bước 6 — kiểm tra humongous.** Tìm `Humongous regions: X->Y`, mảng lớn, big buffers và nhu cầu region liên tiếp.

**Bước 7 — kiểm tra Full GC cause.** Có `Evacuation Failure: Allocation`, `Pinned`, marking chưa kịp, hay `System.gc()`?

**Bước 8 — chỉnh một yếu tố rồi đo lại.** Ưu tiên thay đổi code, hạn chế cache/queue, tránh buffer quá lớn, xem lại heap budget. Chỉ thử cờ GC nâng cao nếu có giả thuyết đo được.

Nếu vấn đề là **stop-the-world pause kéo dài**, điều tra cả CPU throttling, hoạt động I/O log, safepoint và các pha xử lý reference thay vì chỉ tăng GC thread count.

## 16. Dấu hiệu tình huống và cách điều tra

| Hiện tượng quan sát | Giả thuyết | Kiểm tra tiếp |
| --- | --- | --- |
| Allocation cao, old ổn định | Nhiều object sống ngắn | JFR allocation hotspots, young pause cost |
| Old tăng rồi ổn định | Cache warm-up hợp lệ | TTL/eviction/maximum size, thời gian quan sát |
| Old tăng mãi qua nhiều mixed cycles | Retention/leak | Heap dump, dominator tree, GC roots |
| Old tăng cùng queue depth | Producer nhanh hơn consumer | Backpressure và queue metrics |
| `Humongous regions` tăng cao | Các mảng/buffer quá lớn | JFR class/stack, kích thước payload |
| Evacuation failure Allocation | Thiếu region đích | Live set, reserve, heap, promotion |
| Evacuation failure Pinned | Có object bị pin trong tương tác native | JNI/GC cause, runtime support |
| Full GC vì `System.gc()` | Có tác nhân yêu cầu GC | Truy vết code/tool/agent |
| Heap used thấp nhưng process RSS cao | Native/off-heap memory pressure | NMT, direct buffers, metaspace, threads |
| Pause dài nhưng old không tăng | CPU, phase cost, live copying, OS/I/O | `gc+phases`, `gc+cpu`, CPU quota |

Một **heap dump đơn lẻ** không chứng minh leak. Nên so retained size qua thời gian, sau các cửa sổ tải tương đương, và xác định **đường tham chiếu** từ GC roots tới các object đáng nghi.

## 17. Vì sao GC tuning không phải bước đầu tiên?

Theo hướng dẫn G1 của Oracle JDK 25, thường nên bắt đầu với **mặc định**, chỉ điều chỉnh heap size và pause target khi cần. G1 có cơ chế tự điều chỉnh **young generation size** để đáp ứng mục tiêu pause; cố định `-Xmn`/young quá chặt có thể làm mất sự linh hoạt đó.

Một số cờ có thể hữu ích **khi có bằng chứng**:

~~~text
-Xmx                        Giới hạn Java heap
-XX:MaxGCPauseMillis        Soft goal cho thời gian pause
-XX:G1ReservePercent        Dự phòng region để giảm thiếu chỗ
-XX:ConcGCThreads           Tài nguyên concurrent marking
-XX:G1HeapRegionSize        Kích cỡ region/ảnh hưởng humongous
-XX:ParallelGCThreads       Worker cho pha GC song song
~~~

### Ví dụ lựa chọn dựa trên triệu chứng

- **Allocation cao nhưng hầu hết chết sớm:** giảm object churn, boxing, copy buffer, không vội tăng heap chỉ vì allocation rate.
- **Old live set hợp lệ gần đầy:** xem tăng heap trong giới hạn host, giảm retention, chia tải; thêm GC workers **không tạo được free heap**.
- **Concurrent marking bị trễ:** kiểm tra CPU/time, tốc độ vào old, reserved regions; mới cân nhắc `ConcGCThreads`, `G1ReservePercent` hoặc IHOP.
- **Humongous fragmentation:** giảm mảng lớn/chuyển streaming; có thể đánh giá region size bằng benchmark.
- **Full GC do explicit GC:** tìm và loại bỏ nguồn gọi nếu phù hợp, không đổ mọi lỗi cho allocation.

**Không** bật tất cả các cờ ở trên cùng lúc: bạn sẽ khó biết thay đổi nào có ích hoặc gây tác dụng phụ. Tham số `MaxGCPauseMillis` là **mục tiêu** chứ không phải SLA hard guarantee; đặt quá thấp có thể tăng tần suất thu gom, làm giảm throughput.

## 18. Java heap và bộ nhớ native trong container

Một tiến trình còn dùng memory ngoài heap:

- Metaspace/class metadata.
- Thread stacks.
- Direct buffers, memory-mapped files.
- Code cache và JIT/compiler data.
- GC bookkeeping, JNI/native libraries.

Nếu container OOM-kill mà heap used vẫn không cao, hãy xem **RSS, cgroup memory limit và native allocations**. Đừng tăng `-Xmx` vì nó có thể làm ít chỗ hơn cho native memory.

Native Memory Tracking có thể giúp:

~~~bash
java -XX:NativeMemoryTracking=summary -XX:+UseG1GC -Xmx128m -cp classes G1PressureDemo churn
~~~

Trong tiến trình đang chạy với NMT được bật:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT có overhead và không theo dõi toàn bộ native allocations của mọi thư viện. Bật có kiểm soát, chú ý bảo vệ thông tin diagnostics.

## 19. Cách xây dashboard/cảnh báo G1 hữu ích

Theo dõi ít nhất:

1. **Heap used/committed/max**, Old/Humongous regions.
2. Allocation rate và nguồn allocation theo thread/class.
3. Promotion hoặc dữ liệu survival phù hợp với collector.
4. Số young/mixed/full GC và pause p95/p99.
5. Tổng thời gian GC/GC overhead và CPU GC.
6. Concurrent marking, evacuation failures và các nguyên nhân.
7. Request rate, p95/p99 latency, queue length, cache size.
8. Container RSS/limit, CPU throttling và JDK build.

Cảnh báo nên xét **nhiều chỉ số đồng thời**: old baseline tăng liên tục + humongous tăng + evacuation failures có ý nghĩa hơn một mẫu heap 80% đơn lẻ.

**Đặt tên metric đúng semantics**: `heapUsedAfterYoungGc` không được dán nhãn `liveSetExact`. Khi đổi collector hoặc JDK, cần kiểm tra lại ý nghĩa/định dạng telemetry.

## 20. Lỗi suy luận thường gặp

| Hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Full GC song song thì không còn pause.” | Vẫn stop-the-world. | Phân tích nguồn pressure; đo pause. |
| “Allocation cao là leak.” | Nhiều object có thể chết sớm. | Đo survival/old/live baseline. |
| “Heap used tăng 50 MiB là đã cấp phát đúng 50 MiB.” | Có GC trong cửa sổ đo. | Dùng JFR/per-thread allocation stats. |
| “Sau young GC, used heap là live set chính xác.” | Old có thể chứa rác chưa thu hồi. | Quan sát marking/mixed và heap dumps phù hợp. |
| “Full GC luôn do G1 thiếu worker.” | Có thể thiếu vùng đích, humongous hoặc explicit GC. | Đọc GC cause. |
| “Old regions tăng 2 nghĩa promote đúng 2 region byte.” | Region count không phải metric promoted bytes. | Kết hợp nhiều nguồn. |
| “Còn free heap nghĩa chắc còn chỗ cho mảng rất lớn.” | Humongous cần region liên tiếp. | Xem fragmentation/region layout. |
| “`-Xmx` bằng toàn memory process.” | Còn native memory. | Đo RSS/NMT/cgroup. |
| “Dùng `-Xmn` cố định giúp G1 tự tối ưu.” | Có thể cản adaptive young sizing. | Ưu tiên ergonomics. |
| “JFR allocation sample đếm được mọi object.” | Có sampling và cấu hình khác nhau. | Đọc event semantics. |
| “Một lần Full GC chứng minh leak.” | Có nhiều nguyên nhân, gồm `System.gc()`. | Xem chuỗi thời gian và GC roots. |
| “Gọi `System.gc()` thêm sẽ giải quyết Full GC.” | Tăng pause, không sửa retention. | Tìm và sửa nguồn gốc. |
| “Tăng `ParallelGCThreads` luôn cải thiện.” | CPU contention và overhead. | Benchmark một thay đổi tại một thời điểm. |

## 21. Câu hỏi tự kiểm tra

### Câu 1 — tính năng Java 10

**Hỏi:** JEP 307 biến Full GC của G1 thành concurrent hay song song?

**Đáp án:** **Song song hóa Full GC**; ứng dụng vẫn bị dừng trong Full GC.

### Câu 2 — allocation rate

Ứng dụng tạo 2 GiB object trong 10 giây, nhưng heap used chỉ tăng 100 MiB. Allocation rate ước tính từ dữ liệu cấp phát là bao nhiêu?

**Đáp án:** **204.8 MiB/s**, không phải 10 MiB/s. Used heap là số net occupancy sau GC.

### Câu 3 — cùng allocation, khác dữ liệu sống

Hai workload đều tạo 48 MiB payload; một workload giữ 6 MiB payload trong list, workload còn lại không giữ trong list. Có thể kết luận cùng old pressure không?

**Đáp án:** **Không.** Survival/promotion phụ thuộc các tham chiếu và thời điểm GC; lượng giữ khác nhau có thể tạo áp lực old khác nhau.

### Câu 4 — đọc heap log

Log `Pause Young ... 300M->110M(512M)`. Có thể khẳng định live set toàn heap chính xác bằng 110 MiB không?

**Đáp án:** **Không.** Old regions có thể còn rác chưa được reclaim.

### Câu 5 — humongous

Nếu region size là 2 MiB, object thực kích thước 1 MiB thuộc loại gì?

**Đáp án:** Theo ngưỡng hiện hành **≥ nửa region**, là humongous (tùy kích thước object gồm header/alignment).

### Câu 6 — Full GC cause

Thấy `Pause Full (G1 Compaction Pause)` sau `Evacuation Failure: Allocation`. Nên làm gì trước?

**Đáp án:** Kiểm tra old/humongous, live set, allocation/promotion, dự phòng evacuation và concurrent marking; không chỉ tăng GC workers.

### Câu 7 — cache

Cache tăng occupancy trong giai đoạn warm-up rồi ổn định. Có chứng minh leak không?

**Đáp án:** Không. Cần quan sát khi tải ổn định, TTL/eviction và retained references.

### Câu 8 — JFR

`jdk.ObjectAllocationSample` có 100 event của `byte[]`. Có thể khẳng định chỉ có 100 mảng được cấp phát không?

**Đáp án:** Không. Event mẫu không phải toàn bộ allocation.

### Câu 9 — đầu ra Java

Chương trình `G1PressureDemo retain` in bao nhiêu mảng giữ lại và MiB payload?

**Đáp án:** **1536 mảng, 6 MiB payload**; số này chưa tính headers và object ngoài List.

### Câu 10 — tăng GC workers

Nếu old live set gần bằng `-Xmx` và thật sự cần giữ lâu, tăng `ParallelGCThreads` có làm sống sót ít byte hơn không?

**Đáp án:** **Không.** GC không thể thu hồi những object còn reachable; phải thay ngân sách heap hoặc retention policy của ứng dụng.

## 22. Checklist điều tra production

- [ ] Xác minh **G1**, JDK version, `-Xms`, `-Xmx`, CPU và container memory limit.
- [ ] Có GC log đủ dài, phân biệt young/mixed/Full và cause.
- [ ] Có allocation rate hoặc JFR allocation profile với semantics rõ ràng.
- [ ] Theo dõi old/humongous và post-GC baseline qua nhiều chu kỳ phù hợp.
- [ ] Xem survival/promotion, thời gian marking, evacuation failures.
- [ ] Kiểm tra cache, queues, TTL, backlog và các tham chiếu giữ object.
- [ ] Phân biệt heap pressure với native/off-heap/container memory.
- [ ] Đánh giá ứng dụng có phát sinh `System.gc()` hay tác vụ ngoài yêu cầu GC.
- [ ] Không force Full GC chỉ để quan sát ở production.
- [ ] Có số đo latency/throughput trước và sau mỗi thay đổi.
- [ ] Không bật nhiều cờ tuning cùng lúc khi chưa hiểu nguyên nhân.

## 23. Tóm tắt và tài liệu tham khảo

- **JDK 10 — JEP 307:** Full GC của G1 được **song song hóa** để giảm worst-case pause, nhưng vẫn **stop-the-world**.
- **Allocation rate** phản ánh byte được tạo trong thời gian; **không thể đo bằng chênh lệch heap used**.
- **Live data** là object còn reachable; heap used sau young GC có thể còn old garbage.
- **Promotion rate**, **old occupancy**, **humongous regions** và **marking progress** quyết định rủi ro Full GC nhiều hơn chỉ allocation rate.
- Khi thiếu chỗ evacuation hoặc concurrent mark/mixed không theo kịp, G1 có thể fallback về Full GC.
- **GC log + JFR + tiến triển live/old + workload** cho góc nhìn đáng tin hơn một flag tuning hoặc snapshot.
- Ưu tiên giảm retention không cần thiết, tối ưu allocation hotspots và heap budget trước khi chỉnh các cờ G1 nâng cao.

Tài liệu chính thức vẫn áp dụng:

1. [OpenJDK — JEP 307: Parallel Full GC for G1](https://openjdk.org/jeps/307).
2. [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html).
3. [Oracle JDK 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html).
4. [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html).
5. [Oracle JDK 25 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
6. [Oracle JDK 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html).
7. [Oracle JDK 25 — `java` launcher / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
8. [Oracle JDK 26 — G1 và evacuation failure](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html).

**Kết luận:** Muốn tìm nguyên nhân Full GC, hãy trả lời **ba câu hỏi cùng lúc**: app tạo đối tượng **nhanh đến đâu**, giữ lại **bao nhiêu dữ liệu sống**, và G1 còn **đủ thời gian cùng region đích** để reclaim/evacuate hay không. Full GC song song từ Java 10 chỉ giúp xử lý tình huống cuối tốt hơn; giảm nguyên nhân gây áp lực mới là tối ưu bền vững.
