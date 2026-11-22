# Thu gom thoái lui và ảnh hưởng tới độ trễ trong Shenandoah GC

**Thu gom thoái lui** (*Degenerated GC*) trong Shenandoah là cơ chế **fallback sang một chu kỳ thu gom stop-the-world (STW)** khi tiến trình thu gom đồng thời (*concurrent GC*) không thể tiếp tục hoặc không thu hồi bộ nhớ kịp dưới một số điều kiện áp lực. Thay vì để ứng dụng tiếp tục cấp phát trong khi collector không có đủ không gian để tiến triển, JVM có thể **tạm dừng các luồng Java ứng dụng** và cố hoàn thành công việc GC trong điều kiện ít cạnh tranh hơn. Nếu bước thoái lui không tạo đủ tiến triển, hoặc vì điều kiện/heuristics khác, JVM có thể phải sử dụng **Full GC**.

Đây là bài thuộc nhóm **Shenandoah** trong module **Java 15**. Shenandoah được đưa thành tính năng production theo **JEP 379 ở OpenJDK 15** và tiếp tục được phát triển trong Java hiện đại. Tuy nhiên, **không phải mọi nhà phân phối/bản dựng JDK đều tích hợp Shenandoah**; cần kiểm tra runtime thật. Từ **JDK 25**, **Generational Shenandoah** được công bố qua **JEP 521**, trong đó cách tổ chức chu kỳ young/old khác Shenandoah non-generational truyền thống. Cơ chế Degenerated/Full fallback vẫn là chủ đề cần hiểu, nhưng chi tiết trigger, tên phase, counters và thông báo log **có thể khác theo JDK và mode**.

**Điểm quan trọng nhất:** Shenandoah được tối ưu cho **low-pause concurrent GC**, chứ **không cam kết mọi lần thu gom đều concurrent**. Khi có `Pause Degenerated GC`, ứng dụng đã đi vào một đường xử lý fallback dạng **STW**, có thể làm tăng **tail latency** (p95/p99/p99.9). Đây là tín hiệu cần điều tra, không phải mặc định một lỗi correctness hoặc bằng chứng chắc chắn có memory leak.

## 1. Shenandoah hoạt động bình thường như thế nào?

Một collector cần theo dõi các object còn **reachable** từ GC roots để thu hồi bộ nhớ của những object không còn được sử dụng. Trong ứng dụng Java đang chạy, các **mutator threads** liên tục tạo object và thay đổi tham chiếu. Shenandoah cố thực hiện phần lớn các công đoạn như **marking và evacuation/relocation** trong khi các mutators vẫn tiếp tục làm việc.

Mô hình ở mức khái niệm:

```text
Thời gian ------------------------------------------------------>

Java mutators:
  RUN --|pause|--------- RUN ----------|pause|-------- RUN ---->

Shenandoah:
        Initial Mark
             |
             +--- Concurrent Marking ------+
                                         Final Mark
                                             |
                                             +-- Concurrent Evacuation -----+
                                             |
                                             +-- hoàn thiện cập nhật tham chiếu/
                                                 reclaim theo mode và phiên bản
```

Sơ đồ là **minh họa**, không phải một chuỗi pha bắt buộc giống nhau cho mọi đời Shenandoah. Các mode generational và cách triển khai barrier/reference update có thể thay đổi. Điều bất biến là collector phải giữ **tính đúng đắn của object graph** khi GC và các luồng ứng dụng hoạt động chồng lấn.

Những điểm cần phân biệt:

- **Concurrent:** một pha GC chạy trong lúc các mutators **vẫn có thể thực thi**; collector dùng CPU và băng thông bộ nhớ cùng ứng dụng.
- **Parallel:** nhiều GC worker cùng làm việc, nhưng có thể là **trong một khoảng STW**; parallel không đồng nghĩa concurrent.
- **STW pause:** những luồng ứng dụng liên quan bị tạm dừng để JVM làm công việc cần trạng thái nhất quán.
- **Normal Shenandoah cycle:** có nhiều pha concurrent và một số pause đồng bộ ngắn.
- **Degenerated GC:** collector phải rời đường đi concurrent bình thường, thực hiện một đoạn/chu kỳ **STW** để cố tạo tiến triển.
- **Full GC:** đường thu gom toàn diện hơn, thường có chi phí latency cao hơn; dùng khi cần/các fallback trước không đủ hoặc theo lựa chọn của runtime.

Đừng cho rằng mọi phase bắt đầu bằng chữ `Pause` là lỗi. **Các pause ngắn trong normal cycle là bình thường**. Sự xuất hiện của **`Pause Degenerated GC`** mới là tín hiệu Shenandoah đã chuyển sang một đường fallback khác với chu kỳ concurrent bình thường.

## 2. Cơ chế thoái lui: từ concurrent đến Degenerated và có thể đến Full

Một nguyên nhân thường gặp là **allocation failure/pressure**: các mutator cần thêm vùng nhớ nhưng collector chưa kịp cung cấp không gian để đáp ứng. Có thể collector bắt đầu quá muộn, hoặc lưu lượng cấp phát tăng vọt, hoặc có quá nhiều object còn sống, hoặc collector thiếu CPU để chạy đồng thời đủ nhanh.

```text
     Shenandoah concurrent cycle
       marking / evacuation ...
                  |
                  v
    Ứng dụng tiếp tục cấp phát object
                  |
        Có đủ free/usable space?
           /                 \\
          Có                 Không
          |                    |
          v                    v
   Tiếp tục concurrent    Allocation failure/
       bình thường        concurrent cannot progress
                               |
                               v
                  Cân nhắc fallback theo heuristics
                       /                  \\
                      v                    v
              STW Degenerated GC      STW Full GC trực tiếp
                      |
               Tiến triển đủ?
                  /       \\
                Có        Không
                |           |
                v           v
            Quay lại     STW Full GC
            thực thi          |
            ứng dụng     Có đủ memory?
                              |
                   +----------+----------+
                   |                     |
                  Có                    Không
                   |                     |
                   v                     v
             Tiếp tục chạy        Có thể OutOfMemoryError
```

**Không hiểu sơ đồ này là tất cả phiên bản luôn đi qua Degenerated trước Full.** Trong một số trường hợp, lựa chọn runtime có thể chuyển **trực tiếp** sang Full GC, ví dụ theo loại allocation failure, trạng thái heap hoặc quyết định của heuristics. Trên mode generational, đường đi có thể khác giữa young, old hoặc global collections.

### Degenerated GC thực sự làm gì?

Theo thiết kế Shenandoah, một **degenerated cycle** có thể tận dụng trạng thái/công việc đã có từ chu kỳ concurrent bị gián đoạn và **hoàn thành phần còn lại trong STW**. Tùy điểm bị gián đoạn, JVM cần hoàn tất các bước như tracing, evacuation, cập nhật tham chiếu hoặc cleanup. Việc không còn mutators cùng sửa heap giúp quá trình cứu vãn dễ có tiến triển hơn, nhưng **đổi lại các request Java phải tạm dừng**.

Một số **degeneration points** trong log hoặc mã nguồn Shenandoah có tên như:

| Điểm chuyển hướng | Ý nghĩa khái niệm |
| --- | --- |
| `Outside of Cycle` | Có áp lực cấp phát/cần xử lý khi chưa ở một điểm trong concurrent cycle |
| `Roots` | Cần xử lý tại giai đoạn liên quan roots |
| `Mark` | Chu kỳ đánh dấu không thể tiếp tục như dự kiến |
| `Evac` hoặc `Evacuation` | Vấn đề trong quá trình di chuyển object |
| `Update Refs` | Vấn đề khi cập nhật các tham chiếu sau relocation, nếu mode có pha đó |

Tên và sự hiện diện **phụ thuộc phiên bản/mode**; không phải JDK nào cũng có mọi tên trong bảng. Một log có `Outside of Cycle` không có nghĩa ứng dụng không hề có concurrent GC trước đó; nó mô tả **điểm xử lý failure** trong state machine.

### Degenerated khác Full GC ra sao?

- **Degenerated GC** là **đường fallback STW** nhằm cứu một chu kỳ thu gom hoặc xử lý allocation failure, có thể tận dụng công việc đã tiến hành. Nó vẫn có thể thất bại hoặc không thu hồi đủ.
- **Full GC** là đường xử lý khẩn cấp/toàn diện hơn, có thể làm nhiều công đoạn như marking và compaction trên phạm vi rộng hơn trong STW; thường đắt về latency hơn, nhưng **không có một thời lượng cố định**.
- **Không phải cứ có Degenerated GC là chắc chắn sau đó có Full GC**. Một degenerated collection có thể thành công và ứng dụng tiếp tục.
- **Không phải Full GC nào cũng do Degenerated GC thất bại**; loại trigger và chính sách collector khác nhau.

Vì cả hai đều mang tính STW trong ngữ cảnh này, **cả hai đều có thể phá vỡ mục tiêu độ trễ thấp**, nhưng quy mô ảnh hưởng phải đo trên workload thực tế.

## 3. Vì sao Shenandoah không theo kịp ứng dụng?

### 3.1. Heap headroom quá nhỏ

Một concurrent collector cần **không gian trống đủ lớn** để ứng dụng tiếp tục cấp phát trong khi GC đang đánh dấu/di chuyển và thu hồi object. Nếu `-Xmx` chỉ nhỉnh hơn lượng object còn sống, chỉ một allocation burst ngắn cũng có thể làm cạn phần có thể dùng.

Ví dụ giả định:

```text
Heap limit:        128 MiB
Live set:          100 MiB
Headroom lý thuyết: 28 MiB (chưa tính trạng thái GC/metadata)
Allocation burst:  300 MiB trong thời gian ngắn
```

Nếu collector không tạo lại không gian kịp, có thể xảy ra allocation failure và fallback. **Đây không phải công thức chính thức của Shenandoah**: không gian thực tế chịu ảnh hưởng các vùng heap, evacuation reserve, tốc độ GC, object sizes và trạng thái generational. Phép trừ đơn giản `Xmx - live set` chỉ là trực giác ban đầu.

### 3.2. Allocation rate quá cao

Ngay cả với live set ổn định, một ứng dụng có thể cấp phát hàng GiB object tạm mỗi giây do:

- Tạo nhiều `String`, array, DTO hoặc wrapper trong hot path.
- Deserialization/serialization không kiểm soát.
- Đọc một batch lớn rồi tạo toàn bộ object trung gian.
- Cache/stream pipeline tạo nhiều bản sao dữ liệu.
- Tăng concurrency, nhiều request cùng cấp phát và giữ temporary buffers.

Vấn đề ở đây không chỉ là **tổng số byte cấp phát**, mà là **tốc độ**, burst size và khoảng thời gian collector cần để hoàn tất chu kỳ.

### 3.3. Live set cao hoặc memory retention bất thường

Các object vẫn **reachable** sẽ không được GC thu hồi. Cache không giới hạn, queue không drain, collection giữ reference lâu, session leak hoặc listener không được deregister có thể khiến live set lớn.

Nếu sau các lần GC, mức heap baseline **tăng dần qua thời gian**, cần kiểm tra **retained paths/GC roots**, không chỉ tăng `-Xmx` hoặc đổi heuristics. Một collector có pause thấp không thể “chữa” một object vẫn được code giữ tham chiếu.

### 3.4. Evacuation reserve hoặc object đặc biệt tạo áp lực

Shenandoah có thể cần chỗ để **di chuyển các object còn sống** trong concurrent evacuation. Nếu không còn đủ vùng phù hợp để tiếp tục, collector có thể rơi vào đường failure/fallback. Những tình huống liên quan **humongous objects**, layout vùng nhớ hoặc fragmentation cũng cần được kiểm tra theo **phiên bản JVM cụ thể**.

Không nên xem mọi lần Degenerated GC đều do humongous objects hoặc fragmentation. Hãy kiểm tra heap regions, log causes và object allocation profile; tên/cách quản lý các vùng khác nhau giữa collector.

### 3.5. CPU cho concurrent GC bị thiếu

GC concurrent **chia sẻ CPU** với mutators. Container chỉ có một lượng CPU nhỏ, cgroup throttling hoặc node bị tải cao có thể khiến GC threads không theo kịp:

- Concurrent phase dài ra, trong khi ứng dụng vẫn tiếp tục tạo object.
- Workload có nhiều threads có thể cạnh tranh CPU với collector.
- Một allocation spike gặp đúng lúc heap gần giới hạn làm failure dễ xảy ra hơn.
- Tăng số lượng GC threads thủ công không chắc giúp khi **tổng CPU quota vốn quá ít**.

Theo đó, quan sát **CPU throttling, GC phase durations, allocation rate và heap occupancy** cùng nhau tốt hơn kết luận từ một dòng `Pause Degenerated GC`.

## 4. Tác động đến p95/p99/p99.9 latency

**Latency của một request** gồm thời gian đợi hàng đợi, được scheduler chạy, thực hiện nghiệp vụ, truy cập mạng/database, cấp phát/GC và các pause khác. Một **STW Degenerated GC** có thể chặn những request đang chạy cùng lúc, tạo ra một khoảng gián đoạn và làm tail latency tăng.

Ví dụ khái niệm:

```text
Trạng thái bình thường:
  request A:  8ms
  request B: 11ms
  request C:  9ms

Xảy ra STW Degenerated GC 80ms khi request đang chạy:
  request A:  8ms + thời gian bị dừng
  request B: 11ms + thời gian bị dừng
  request C:  9ms + thời gian bị dừng

Nếu traffic tiếp tục đến:
  request mới có thể còn xếp hàng do threads không xử lý kịp
```

**80 ms ở đây là số giả định để giải thích**, không phải độ dài mặc định hay cam kết cho Shenandoah. Một degenerated event có thể rất ngắn hoặc dài tùy degeneration point, kích thước heap, live set, GC worker threads và CPU thực tế.

Có ba tác động cần tách:

1. **Pause trực tiếp:** các Java mutators không tiếp tục chạy trong khoảng STW.
2. **Queueing sau pause:** requests mới hoặc công việc đã xếp hàng có thể phải chờ thêm, khiến tail latency bị kéo dài ngay cả sau khi JVM tiếp tục chạy.
3. **Throughput/CPU cost:** GC fallback sử dụng GC workers và resource, có thể tạo áp lực thêm sau event; phía ứng dụng có thể đang cần bù backlog.

Vì vậy **không suy p99 trực tiếp bằng tổng số ms của GC pauses**. Phải đối chiếu các sự kiện theo thời gian với request traces/metrics. Nếu SLO ví dụ là p99 dưới 50 ms, một event STW tương đối dài có thể tạo SLO breach; nhưng mức độ còn phụ thuộc tần suất và bao nhiêu request bị ảnh hưởng.

### Độ trễ thấp không có nghĩa “không có STW”

Ngay cả chu kỳ Shenandoah concurrent bình thường có thể có những điểm pause ngắn để phối hợp. **Degenerated GC** là cơ chế **cứu vãn** khi collector không còn giữ được đường concurrent như dự kiến. Nó có thể làm giảm đặc tính low-pause tại thời điểm áp lực — chính là lúc ứng dụng có thể đang chịu tải cao.

**Sự kiện Degenerated GC không phải bug correctness mặc định:** đó là một quyết định bảo toàn hoạt động/tính đúng đắn của GC. Nhưng khi xuất hiện thường xuyên, nó là **dấu hiệu hiệu năng cần điều tra**.

## 5. Đọc đúng GC log: Pause Degenerated GC

Với HotSpot có tích hợp Shenandoah, có thể dùng **Unified GC Logging**:

```bash
java -XX:+UseShenandoahGC -Xms128m -Xmx512m \
     -Xlog:gc*:file=shenandoah.log:uptime,level,tags -jar service.jar
```

Đây là câu lệnh **minh họa cho Bash**. `service.jar` là tệp ứng dụng thực của bạn. Cờ `-Xmx512m` **không phải mức heap khuyến nghị cho mọi workload**. Trên PowerShell nên dùng một dòng hoặc cú pháp nối dòng đúng của PowerShell.

Trong log Shenandoah có thể gặp:

```text
[0.138s][info][gc          ] GC(8) Pause Degenerated GC (Outside of Cycle) 43M->41M(61M) 1.055ms
```

Dòng trên là **event completion từng quan sát trong một lần chạy JDK 24**, không phải ví dụ “cố định luôn xảy ra” của mọi bản JVM.

| Phần log | Ý nghĩa |
| --- | --- |
| `[0.138s]` | Thời điểm theo **JVM uptime** nếu dùng decorator `uptime` |
| `[info][gc]` | Level và tag; khoảng trắng padding phụ thuộc formatter |
| `GC(8)` | GC event/cycle ID trong log hiện tại |
| `Pause Degenerated GC` | **STW fallback event** của Shenandoah |
| `(Outside of Cycle)` | Điểm thoái lui như runtime ghi nhận |
| `43M->41M(61M)` | Thống kê heap usage trước/sau/capacity theo định dạng collector |
| `1.055ms` | Thời lượng event được ghi trong log, **không phải tổng request latency** |

Nếu `-Xmx64m` nhưng log hiển thị capacity như `(61M)`, đừng vội cho rằng JVM “bỏ qua Xmx”: các con số dung lượng/region trong log có thể phản ánh cách heap được bố trí và báo cáo ở bản dựng đó. Xem command line, `GC.heap_info` và các chỉ số runtime tương ứng.

### Có thể có nhiều dòng cùng tên cho một event

```text
[...][gc,start] GC(8) Pause Degenerated GC (Outside of Cycle)
[...][gc      ] GC(8) Pause Degenerated GC (Outside of Cycle) 43M->41M(61M) 1.055ms
[...][gc,stats] Pause Degenerated GC (G) ... us
```

Ba dòng trên **không nhất thiết tương ứng ba lần Degenerated GC**. Chúng là event start, event completion và thống kê theo collector. Nếu tìm kiếm mù:

```bash
grep -c "Pause Degenerated GC" shenandoah.log
```

bạn có thể **đếm thừa**. Để ước lượng số event hoàn tất từ format log đang dùng, lọc dòng có `GC(number)`, `Pause Degenerated GC` và duration kết thúc bằng `ms`:

```bash
grep -E 'GC\\([0-9]+\\) Pause Degenerated GC.*[0-9.]+ms$' shenandoah.log
grep -Ec 'GC\\([0-9]+\\) Pause Degenerated GC.*[0-9.]+ms$' shenandoah.log
```

Trên PowerShell:

```powershell
$hits = @(Get-Content shenandoah.log |
    Where-Object { $_ -match 'GC\\(\\d+\\) Pause Degenerated GC.*\\d+(?:\\.\\d+)?ms$' })
$hits.Count
$hits | Select-Object -First 5
```

**Đây là bộ lọc cho mẫu log đã nêu, không phải một API ổn định của Java.** Khi runtime thay đổi tên pha, có mode generational, log bị rotate hoặc dùng decorator/level khác, bạn cần kiểm tra/điều chỉnh parser. Một số Full GC event cũng có dòng start/completion/stats; phải phân biệt tương tự.

## 6. Phân biệt Normal, Degenerated và Full trong điều tra

| Loại GC | Có concurrent work? | STW và độ trễ | Khi nào đáng chú ý |
| --- | --- | --- | --- |
| **Normal Shenandoah cycle** | Phần lớn marking/evacuation concurrent | Có các điểm phối hợp ngắn | Baseline để so pause và throughput |
| **Degenerated GC** | Đường fallback, xử lý STW tại điểm thoái lui | Có thể dài hơn normal pause; phụ thuộc trạng thái và heap | Thấy thường xuyên → áp lực tài nguyên hoặc heuristics không theo kịp |
| **Full GC** | Đường khẩn cấp/toàn diện STW | Thường đáng lo nhất với tail latency; không có ngưỡng duration bất biến | Cần điều tra heap/live set và nguyên nhân không tiến triển |
| **OutOfMemoryError** | Không phải một loại GC | Allocation không đáp ứng được; ứng dụng có thể lỗi | Xác định heap vs metaspace vs direct/native |
| **OS/container OOM kill** | Không phải một loại GC | Process có thể bị kill đột ngột | Kiểm tra RSS/cgroup memory limit, không chỉ `-Xmx` |

### Dấu hiệu leo thang

Có thể gặp chuỗi:

```text
Concurrent collection bắt đầu muộn hoặc không theo kịp
  -> allocation failure
  -> Degenerated GC
  -> nếu degenerated vẫn không tạo đủ tiến triển
  -> Full GC
  -> nếu không thể đáp ứng yêu cầu cấp phát
  -> OutOfMemoryError
```

Đó là một **đường có thể xảy ra**, không phải mọi incident đều đầy đủ tất cả bước. Có trường hợp runtime dùng Full GC trực tiếp, hoặc thành công sau Degenerated và không xuất hiện Full, hoặc bị container kill vì memory ngoài heap mà không có Java OOME.

**Đừng chỉ tìm dòng Full GC.** Nếu Degenerated xảy ra liên tục nhưng không có Full, ứng dụng vẫn có thể phải chịu nhiều STW pauses làm p99 xấu đi đáng kể.

## 7. Java 17+ runnable lab: quan sát fallback mà không tự cài GC

Chương trình sau chỉ dùng API Java chuẩn để tạo **tải cấp phát ngắn hạn** và giữ lại một **cửa sổ object còn reachable**. JVM mới là nơi thực hiện Shenandoah; mã Java không gọi `System.gc()`, không can thiệp barrier hoặc bắt JVM chạy Degenerated GC.

**Mục đích:** quan sát sự khác nhau giữa tổng lượng object từng được cấp phát và live set, so sánh GC log khi thay đổi **heap headroom**. Một số lượt thử có thể có Degenerated GC, một số không. **Không có API public bảo đảm “cứ chạy đoạn này thì đúng N lần Degenerated GC”**.

Lưu thành file **`ShenandoahDegeneratedLab.java`** (UTF-8):

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class ShenandoahDegeneratedLab {
    private static final int BLOCK_SIZE = 16 * 1024;
    private static final int BLOCK_COUNT = 96_000;
    private static volatile byte[][] keepAlive;

    public static void main(String[] args) {
        int slots = Integer.getInteger("retainSlots", 1024);
        if (slots < 1 || slots > 3072) {
            throw new IllegalArgumentException("retainSlots must be 1..3072");
        }

        byte[][] window = new byte[slots][];
        long checksum = 0L;

        for (int i = 0; i < BLOCK_COUNT; i++) {
            byte[] block = new byte[BLOCK_SIZE];
            block[0] = (byte) i;
            window[i % slots] = block;
            checksum += block[0] & 0xff;
        }

        keepAlive = window;

        boolean shenandoahBean =
                ManagementFactory.getGarbageCollectorMXBeans()
                    .stream()
                    .map(GarbageCollectorMXBean::getName)
                    .anyMatch(n -> n.toLowerCase().contains("shenandoah"));

        System.out.println("requestedMiB=" +
                ((long) BLOCK_SIZE * BLOCK_COUNT / 1024 / 1024));
        System.out.println("windowMiB=" +
                ((long) BLOCK_SIZE * slots / 1024 / 1024));
        System.out.println("completedBlocks=" + BLOCK_COUNT);
        System.out.println("checksum=" + checksum);
        System.out.println("lastBlockSize=" +
                keepAlive[(BLOCK_COUNT - 1) % slots].length);
        System.out.println("shenandoahBean=" + shenandoahBean);
    }
}
```

### Tại sao chương trình này tạo pressure?

- `96_000 × 16 KiB = 1.500 MiB` là **tổng dung lượng payload mảng được yêu cầu cấp phát theo thời gian**, không phải dung lượng live cùng lúc.
- `-DretainSlots=2560` tạo một mảng gồm 2.560 vị trí, giữ các block mới nhất: khoảng **40 MiB payload** cộng overhead của các object và cấu trúc mảng.
- Mỗi lần thay thế `window[i % slots]`, block cũ có thể trở nên unreachable và đủ điều kiện để GC thu hồi.
- `checksum` buộc code sử dụng byte đầu mỗi block theo logic chương trình; object vẫn cần được cấp phát theo workload.
- `keepAlive` là field `volatile static` để giữ cửa sổ cuối còn reachable khi in kết quả.
- `GarbageCollectorMXBean` dùng để kiểm tra runtime có công bố bean chứa tên Shenandoah; đây là **chẩn đoán implementation-specific**, không phải phép chứng nhận mọi đặc tính GC.

**Thận trọng:** Đây là stress lab tạo 1.500 MiB allocations trong thời gian ngắn. Chỉ chạy trên môi trường thử nghiệm có giới hạn RAM/CPU phù hợp, **không chạy trong dịch vụ production**, không đặt `-Xmx` quá sát live set của một workload thực rồi mong không có OOME.

### Chạy và so sánh hai heap sizes

Biên dịch bằng JDK 17+ có hỗ trợ API chuẩn được dùng:

```bash
javac --release 17 -encoding UTF-8 ShenandoahDegeneratedLab.java
```

Lượt A với **heap maximum 64 MiB** và khoảng 40 MiB block payload được giữ:

```bash
java -Xms32m -Xmx64m -XX:+UseShenandoahGC -DretainSlots=2560 \
     -Xlog:gc*:file=shen-64.log:uptime,level,tags ShenandoahDegeneratedLab
```

Lượt B với **heap maximum 256 MiB**, còn các tham số bài test giữ nguyên:

```bash
java -Xms32m -Xmx256m -XX:+UseShenandoahGC -DretainSlots=2560 \
     -Xlog:gc*:file=shen-256.log:uptime,level,tags ShenandoahDegeneratedLab
```

Các lệnh nhiều dòng dùng **Bash**. Trên PowerShell, dùng một dòng:

```powershell
javac --release 17 -encoding UTF-8 ShenandoahDegeneratedLab.java
java -Xms32m -Xmx64m -XX:+UseShenandoahGC -DretainSlots=2560 "-Xlog:gc*:file=shen-64.log:uptime,level,tags" ShenandoahDegeneratedLab
java -Xms32m -Xmx256m -XX:+UseShenandoahGC -DretainSlots=2560 "-Xlog:gc*:file=shen-256.log:uptime,level,tags" ShenandoahDegeneratedLab
```

Các lệnh giả định runtime **có Shenandoah**. Nếu JVM trả lỗi `Unrecognized VM option 'UseShenandoahGC'` hoặc `Shenandoah GC is not supported`, cần dùng một bản JDK/platform hỗ trợ; không nên sửa code Java bằng các cờ experimental cũ nếu không xác định đúng nguyên nhân.

### Stdout đã biên dịch và kiểm chứng trên JDK 24

**Cả hai lượt** với `-DretainSlots=2560` đều in:

```text
requestedMiB=1500
windowMiB=40
completedBlocks=96000
checksum=12240000
lastBlockSize=16384
shenandoahBean=true
```

Kết quả `shenandoahBean=true` đã quan sát trên **JDK 24 HotSpot có Shenandoah** trong lượt kiểm thử. Số lượng/names của MXBeans có thể khác trên bản dựng khác; **GC log** là bằng chứng trực tiếp hơn về collector và các pha.

### GC log cho thấy điều gì?

Trong **một lượt thử cụ thể** với JDK 24:

| Lượt | Max heap | Event `Pause Degenerated GC` hoàn tất trong log | `Pause Full` hoàn tất |
| --- | --- | --- | --- |
| A | 64 MiB | **8** | **0** |
| B | 256 MiB | **0** | **0** |

Một số dòng đã quan sát ở lượt A:

```text
[0.138s][info][gc] GC(8) Pause Degenerated GC (Outside of Cycle) 43M->41M(61M) 1.055ms
[0.159s][info][gc] GC(11) Pause Degenerated GC (Outside of Cycle) 42M->41M(61M) 1.326ms
```

**Đây là số liệu từ lần chạy thử đã kiểm tra, không phải expected stdout hay kết quả bất biến.** Ở lượt chạy khác, ngay với cùng cờ, JVM có thể ghi số Degenerated events khác hoặc không ghi event nào. Điều đó tùy tốc độ CPU, heap heuristics, JIT warmup, tải hệ thống, OS, JDK build và thời điểm các chu kỳ GC được kích hoạt. Bài lab **không khẳng định 64 MiB luôn degenerate** hay **256 MiB luôn không degenerate**.

Kết luận giới hạn nhưng hữu ích: trong lần thử này, **heap headroom thấp hơn đi kèm nhiều fallback STW hơn**, phù hợp cơ chế concurrent collection không theo kịp allocation pressure. Để kết luận tuning cho production cần lặp lại nhiều lần, warmup, tải đại diện và đo response latency thực tế.

### Vì sao không cố tạo Full GC cho bài lab?

Gây Full GC/OOME bằng cách giữ quá nhiều object trong heap nhỏ **không cần thiết để hiểu Degenerated GC**; nó dễ biến bài học thành một phép thử lỗi process. Thay vào đó, lab giữ khoảng 40 MiB payload trong heap 64 MiB để quan sát fallback trong một số lần chạy, vẫn có khả năng chương trình hoàn thành bình thường. Trong một môi trường khác, **OOME vẫn có thể xảy ra** nếu memory pressure vượt khả năng collector; đó là lý do cần môi trường thử nghiệm và log riêng.

## 8. Thực hành chẩn đoán theo thời gian

Một incident có p99 tăng nên được xử lý theo chuỗi bằng chứng:

**Bước 1 — Xác định collector và JDK.** Dùng `java -version`, lệnh khởi động JVM và dòng `Using Shenandoah` trong GC log. Nếu dùng Java 15, chú ý bản dựng JDK có tích hợp Shenandoah hay không. Nếu dùng JDK 25+ với mode generational, xác định mode thực tế thay vì áp đặt phase model cũ.

**Bước 2 — Xác nhận event.** Tìm **`Pause Degenerated GC`** và **`Pause Full`**, thời lượng, event ID, generation/cause nếu log có. Đừng dùng mỗi `GC Count` hoặc chỉ grep tên pha mà không bỏ các dòng start/stats trùng event.

**Bước 3 — Đối chiếu p99.** Đặt timestamp GC event gần với request trace/timing. Nếu có Degenerated pause 100 ms tại thời điểm requests bị chậm, đây là dấu hiệu mạnh; tuy nhiên phải xét cả queueing, CPU và downstream service. **Một lần trùng thời điểm không chứng minh quan hệ nhân quả hoàn toàn.**

**Bước 4 — Kiểm tra áp lực tài nguyên.** Đo heap used/committed/max, live set, allocation rate, size của object tạm, CPU throttling, container RSS và memory limit. Nếu bộ nhớ còn rất nhiều mà vẫn có Degenerated, tiếp tục điều tra cause/heuristics/version và runtime bugs thay vì mặc định chỉ thiếu Xmx.

**Bước 5 — Phân tích xu hướng.** Fallback chỉ xuất hiện khi startup hoặc spike hiếm gặp khác với **fallback dày đặc dưới steady load**. Cần phân biệt issue lặp với event ngẫu nhiên đơn lẻ.

**Bước 6 — Thử một biến một lúc.** Tăng heap trong memory budget, giảm allocation, giảm concurrency hoặc tăng CPU quota (nếu có thể), rồi so sánh **event count/duration, p95/p99 request, throughput và RSS**.

### Bộ metrics nên theo dõi

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| GC events | Degenerated/Full events, duration, cause | Có dùng đường STW fallback không; tốn bao lâu? |
| GC phases | Concurrent mark/evacuation timing, pause timing | Collector có theo kịp mutators không? |
| Heap | Live set, occupancy, free/committed/max, reserve | Có headroom thực sự không? |
| Allocation | MiB/s, spikes, object size histogram | Mutators tạo rác nhanh tới đâu? |
| CPU | Per-process CPU, GC threads, cgroup throttling | Collector có đủ CPU để chạy concurrent không? |
| Memory | RSS, native/direct memory, thread stacks | Có nguy cơ container OOM kill khi tăng Xmx không? |
| Application | Request p95/p99/p99.9, queue wait, error rate | STW ảnh hưởng khách hàng ở mức nào? |
| Stability | OOME, restarts, Full GC frequency | Fallback có đang tiến tới lỗi nặng hơn không? |

Dùng **JFR**, Unified GC logs, profiler và các chỉ số OS/container để có một bức tranh đầy đủ. Không bật mức logging cực chi tiết dài hạn mà chưa kiểm tra overhead, dung lượng log và yêu cầu bảo mật dữ liệu.

## 9. Cách giảm Degenerated GC theo thứ tự ưu tiên

### 9.1. Cấp đủ heap headroom

Với concurrent relocation, heap cần đủ dung lượng cho **live set + allocations đang tới + reserve/memory phục vụ quá trình GC**. Khi tăng `-Xmx`, GC có nhiều cơ hội hoàn thành chu kỳ concurrent trước khi ứng dụng hết không gian.

Tuy nhiên:

- `-Xmx` là giới hạn **Java heap**, không phải toàn bộ process RSS.
- Container vẫn cần memory cho native buffers, metaspace, code cache, thread stacks và JNI.
- Không đặt `-Xmx` sát hoặc vượt memory limit container để giải quyết một event thoái lui.
- Nếu live set tăng liên tục vì logic giữ tham chiếu, tăng heap chỉ hoãn thời điểm gặp áp lực.

Ví dụ tăng Xmx trong một experiment **chỉ là ví dụ**, không phải giá trị được khuyến nghị:

```bash
java -XX:+UseShenandoahGC -Xms256m -Xmx1g -jar service.jar
```

### 9.2. Giảm allocation rate và các burst

Profiling để tìm object allocations ở hot path:

- Giảm các bản sao mảng, string/JSON trung gian không cần thiết.
- Tránh unbounded queues, tập trung vào backpressure khi có traffic spike.
- Giới hạn concurrency khi mỗi request giữ nhiều object tạm cùng lúc.
- Sử dụng streaming/batching phù hợp thay vì giữ cả dataset lớn trong memory.
- Cân nhắc reuse buffer có kiểm soát, nhưng không tạo data races hoặc memory retention quá mức.

**Không tự chuyển mọi object sang direct/native memory** để “đỡ GC”: có thể chuyển pressure sang RSS/off-heap, khiến container OOM kill dù GC log đẹp.

### 9.3. Kiểm soát live set và memory retention

Tìm các object còn reachable mà nghiệp vụ không cần giữ:

- Cache không TTL/size bound.
- `Map`/`List` tăng mãi vì không cleanup.
- ThreadLocal hoặc listener có vòng đời dài hơn request.
- Queue không được consumer xử lý kịp.
- Dữ liệu per-request vô tình được giữ trong singleton.

Heap dump/retained-path analysis giúp tìm **GC roots** giữ object. GC không “dọn leak” nếu logic ứng dụng vẫn tham chiếu.

### 9.4. Bảo đảm CPU cho concurrent collection

Trong container, tăng heap có thể chưa đủ nếu GC không có thời gian chạy. Kiểm tra:

- CPU quota và thời gian cgroup throttling.
- Độ dài concurrent marking/evacuation phases.
- Số threads ứng dụng và context-switching.
- Node contention hoặc autoscaling khiến quá nhiều pods tranh CPU.

Tăng CPU, giảm mutator concurrency hoặc tối ưu allocation đôi khi giúp collector hoàn tất sớm hơn, giảm fallback. Điều chỉnh `-XX:ConcGCThreads` hoặc `-XX:ParallelGCThreads` là **tuning nâng cao**, có trade-off: tăng threads GC có thể chiếm CPU từ request handlers. **Đừng chọn một con số cố định theo blog cũ rồi áp dụng mọi máy**.

### 9.5. Xem lại lựa chọn mode/heuristics theo JDK

Một số cấu hình Shenandoah có heuristics và modes khác nhau, nhưng **tên option/behavior thay đổi theo JDK version và vendor**. Trong JDK 25 có hỗ trợ Generational Shenandoah, có thể thử:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational \
     -Xmx1g -jar service.jar
```

Đây là **lựa chọn cho JDK 25+ có hỗ trợ mode đó**, không phải câu lệnh cho Java 15 hoặc JDK 17. Không giả định mode generational luôn có sẵn nếu JDK vendor không tích hợp Shenandoah. Trước khi thay mode ở production, chạy benchmark thực và kiểm tra logs/metrics; mode mới không phải biện pháp tự động loại bỏ mọi fallback.

Tránh cố vô hiệu hóa **Degenerated GC** chỉ để làm log biến mất: fallback là cơ chế giúp collector có cơ hội phục hồi. Nếu vô hiệu hóa hoặc điều chỉnh sai, có thể khiến hệ thống chuyển thẳng sang Full GC/OOME trong điều kiện pressure. Các flags nội bộ/experimental dành cho kiểm thử JVM không phải cách tuning ứng dụng thông thường.

## 10. Java 15, JDK 24 và JDK 25+: những mốc cần phân biệt

| Phiên bản | Trạng thái liên quan Shenandoah | Điều cần ghi nhớ |
| --- | --- | --- |
| **Java 15 — JEP 379** | Shenandoah trở thành tính năng production ở OpenJDK 15 | Chạy được nếu bản dựng/platform hỗ trợ; chủ yếu mô hình non-generational |
| **JDK 24 — JEP 404** | Generational Shenandoah được đưa vào thử nghiệm ở một số bản dựng theo JEP 404 | Khi sử dụng mode experimental phải theo đúng flag/version và giới hạn hỗ trợ |
| **JDK 25 — JEP 521** | Generational Shenandoah trở thành tính năng production | Có mode generational; tổ chức young/old và cơ chế fallback có thể khác |
| JDK hiện đại | Runtime và collector tiếp tục phát triển | Quan sát version thực; không bê nguyên output/flags từ JDK 15 sang JDK 25+ |

**Không nhầm mốc của Shenandoah với ZGC.** ZGC có những JEP/version riêng; cách gọi fallback, event names và bộ flags không giống hoàn toàn. Một dòng `Allocation Stall` của ZGC không phải cùng một loại sự kiện với `Pause Degenerated GC` của Shenandoah.

## 11. Dấu hiệu thiếu tài nguyên và tình huống dễ nhầm

| Triệu chứng | Khả năng cần điều tra | Không nên kết luận ngay |
| --- | --- | --- |
| Degenerated events tăng khi QPS tăng | Allocation rate và headroom | “Shenandoah bị lỗi” |
| Degenerated + Full thường xuyên | Collector không tiến triển đủ dưới áp lực | “Thêm GC threads chắc chắn cứu được” |
| Live set sau GC tăng đều nhiều giờ | Retention leak/cache/queue | “Chỉ cần đổi collector” |
| Heap có chỗ nhưng concurrent phases dài | CPU quota/throttling, heuristics, object layout | “Không thể do GC” |
| Request p99 cao nhưng không có fallback | I/O, lock contention, CPU hoặc normal pauses | “Chắc chắn thiếu Xmx” |
| Process chết không có Java stacktrace | Container/OS OOM kill, native memory | “Lỗi luôn ở Java heap” |
| Log ghi `Pause Degenerated GC (Outside of Cycle)` | Đường fallback ở một điểm trạng thái collector | “Không có concurrent GC trước đó” |
| Có start/stats cùng tên với complete log | Nhiều dòng mô tả **một event** | “Mỗi dòng là một chu kỳ GC riêng” |

### Không trộn Degenerated GC với allocation stall

Một số collector khi không có đủ allocation space có thể ghi tên sự kiện **allocation stall** riêng. Trong Shenandoah, một **allocation failure** có thể kích hoạt **Degenerated GC** hoặc **Full GC**, nhưng **không được thay thế cách đọc log Shenandoah bằng bộ lọc sự kiện của ZGC**. Shenandoah fallback là một **STW collection event**; ZGC allocation stall là **luồng mutator chờ allocation**. Hai hiện tượng cùng có thể gây latency nhưng không phải cùng định danh hoặc cùng cơ chế.

## 12. Checklist vận hành khi thấy Pause Degenerated GC

- [ ] Xác nhận collector **thực sự là Shenandoah**, có hỗ trợ trên runtime đang chạy.
- [ ] Ghi lại **JDK version, vendor, OS, container limits** và cờ JVM.
- [ ] Ghi nhận các **completion events** `Pause Degenerated GC`, không đếm lẫn start/stats.
- [ ] Đọc **degeneration point**, GC ID và duration từ log, hiểu chúng phụ thuộc phiên bản.
- [ ] Kiểm tra có `Pause Full` hoặc `OutOfMemoryError` sau fallback không.
- [ ] Ghép event timestamps với **p95/p99 request và queue latency**.
- [ ] Đo heap live set, occupancy, available headroom và allocation rate.
- [ ] Đánh giá các object giữ lâu, cache/queue, humongous allocations nếu có.
- [ ] Đo CPU quota, throttling và thời gian collector chạy concurrent.
- [ ] So sánh memory `-Xmx` với **RSS/container memory limit**, dự phòng native overhead.
- [ ] Tối ưu allocation/retention trước khi đụng đến các heuristics khó kiểm soát.
- [ ] Đổi **một thông số mỗi lần**, A/B benchmark và giữ rollback.
- [ ] Nếu cần generational Shenandoah, dùng **JDK 25+ có hỗ trợ**, không chép cờ sang Java 15/17.
- [ ] Không tuyên bố “không có pause” chỉ vì dùng collector low-latency.
- [ ] Không dùng stress lab của bài trong production.

## 13. Các hiểu lầm phổ biến

| Hiểu lầm | Kết luận đúng |
| --- | --- |
| Shenandoah luôn thu gom concurrent nên không thể STW | **Sai:** có các pause thường và fallback STW Degenerated/Full |
| Degenerated GC là cùng việc với normal concurrent cycle | Không: nó là **đường fallback** khi concurrent không thể tiến triển như dự kiến |
| Degenerated GC luôn phải kéo theo Full GC | **Sai:** có thể hoàn thành thành công và quay lại ứng dụng |
| Full GC luôn do Degenerated vừa thất bại | **Sai:** có trường hợp Full trực tiếp theo trigger/heuristics |
| Có một event Degenerated là chắc chắn memory leak | **Sai:** spike và thiếu headroom/CPU cũng có thể gây |
| Tất cả Pause Degenerated GC dài đúng 100 ms | Không có duration cố định; phụ thuộc điểm thoái lui và workload |
| Log có 3 dòng Pause Degenerated tức 3 lần fallback | Một event có thể có start, completion và stats |
| `-Xmx` bằng live set là đủ cho concurrent GC | Cần **headroom** cho allocation và evacuation/GC progress |
| Cứ tăng số GC threads sẽ giảm latency | Có thể làm GC tranh CPU với mutators nhiều hơn |
| Thay GC thì những object còn reachable được dọn | GC không thể thu hồi object mà code vẫn giữ tham chiếu |
| JDK nào cũng hỗ trợ `-XX:+UseShenandoahGC` | Hỗ trợ tùy bản dựng/vendor/platform |
| `ShenandoahGCMode=generational` có sẵn từ Java 15 | Không: generational Shenandoah là bước phát triển sau, production từ JDK 25 |
| Lượt lab 64 MiB luôn có 8 Degenerated events | Con số **không deterministic** và chỉ đúng cho một lần thử |
| Chỉ nhìn độ dài pause đủ kết luận request p99 | Cần event timing, queueing, tracing và system metrics |

## 14. Bài tập và đáp án

**Câu 1.** Tại sao collector được quảng bá là low-pause concurrent vẫn có thể xuất hiện `Pause Degenerated GC`?

**Câu 2.** Một log có `Pause Degenerated GC (Outside of Cycle) 43M->41M(61M) 1.055ms`. Ý nghĩa `1.055ms` là gì? Có thể kết luận request p99 bằng 1.055 ms không?

**Câu 3.** Một ứng dụng có live set 1.9 GiB và đặt `-Xmx2g`, đồng thời allocation rate rất cao. Vì sao vẫn có nguy cơ fallback?

**Câu 4.** Có thể coi mọi dòng chứa `Pause Degenerated GC` là một event riêng không?

**Câu 5.** Lượt A heap 64 MiB có Degenerated GC, lượt B heap 256 MiB không có trong cùng bài lab. Kết luận nào là hợp lý và kết luận nào quá mức?

**Câu 6.** Một hệ thống thường xuyên có cả `Pause Degenerated GC` và `Pause Full`. Nên điều tra gì?

**Câu 7.** CPU quota chỉ 1 core nhưng application có nhiều worker threads và GC concurrent phases rất dài. Tăng `ConcGCThreads` lên 16 có luôn đúng không?

**Câu 8.** Một cache giữ hàng triệu object không được dùng nhưng vẫn reachable. Shenandoah có thu hồi chúng chỉ vì xuất hiện Degenerated GC không?

**Câu 9.** Một team đang dùng JDK 17 và copy `-XX:ShenandoahGCMode=generational` từ hướng dẫn JDK 25. Đúng không?

**Câu 10.** Vì sao không nên cố ép Full GC/OOME để minh họa mỗi lần Degenerated GC trong môi trường dịch vụ?

**Đáp án:**

1. Vì collector vẫn có thể không theo kịp allocation pressure hoặc gặp điều kiện khiến chu kỳ concurrent không tiến triển; runtime chuyển sang fallback STW.
2. Đó là **thời lượng GC event** được ghi; không phải tổng request latency hoặc p99. Cần đối chiếu theo thời gian với request metrics.
3. Headroom rất ít để ứng dụng tiếp tục cấp phát trong lúc GC đang làm marking/evacuation; allocation burst có thể làm cạn không gian.
4. Không. Một event có thể có nhiều dòng `gc,start`, `gc` completion và `gc,stats`; phải lọc đúng.
5. Hợp lý: **headroom có liên hệ với số fallback trong lượt thử ấy**. Quá mức: “64 MiB chắc chắn có 8 lần” hoặc “256 MiB bảo đảm không bao giờ degenerate”.
6. Kiểm tra live set, allocation rate, heap headroom, evacuation reserves, CPU throttling, object retention, GC cause và phiên bản JVM.
7. Không. Nếu tổng CPU hạn chế, nhiều GC threads hơn có thể làm tăng contention và giảm throughput; phải đo CPU, GC progress và app latency.
8. Không. GC chỉ thu hồi object **không còn reachable**, dù là normal, Degenerated hay Full.
9. Không. Mode generational được đưa thành production ở JDK 25; cần dùng đúng phiên bản/nhà phân phối và flags được hỗ trợ.
10. Vì có thể khiến JVM mất khả năng phục vụ, lỗi nghiệp vụ hoặc restart; bài lab chỉ cần chứng minh đường fallback và giải thích áp lực bộ nhớ.

## Tài liệu tham khảo còn áp dụng

- [OpenJDK — JEP 379: Shenandoah (Production)](https://openjdk.org/jeps/379): Shenandoah trở thành tính năng production trong Java 15.
- [OpenJDK Wiki — Shenandoah GC](https://wiki.openjdk.org/display/shenandoah/Main): concurrency, Degenerated/Full GC, nguyên nhân và định hướng tuning.
- [OpenJDK — JEP 404: Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): quá trình phát triển generational mode trước khi thành production.
- [OpenJDK — JEP 521: Generational Shenandoah](https://openjdk.org/jeps/521): generational mode được đưa thành tính năng production ở JDK 25.
- [Red Hat — OpenJDK 25 release notes, Generational Shenandoah](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): xác nhận cấu hình generational trên bản dựng hỗ trợ.
- [Oracle Java SE 25 — java Command / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog`, `-Xms`, `-Xmx` và phạm vi các cờ HotSpot.
- [OpenJDK Shenandoah source — DegeneratedGC](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shenandoah/shenandoahDegeneratedGC.cpp): mã nguồn state machine/fallback của Shenandoah phiên bản phát triển hiện hành; đọc theo đúng revision khi phân tích production.
- [Oracle Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): giao diện JMX kiểm tra những counters GC mà runtime công bố.