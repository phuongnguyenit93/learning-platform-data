# Shenandoah: Region, vùng dự phòng và tốc độ cấp phát trong Java 15+

## 1. Vấn đề cốt lõi: GC chạy đồng thời nhưng ứng dụng vẫn tiếp tục cấp phát

**Shenandoah GC** là bộ thu gom rác độ trễ thấp của HotSpot, dùng **các region** và thực hiện nhiều giai đoạn GC **đồng thời** với application threads (còn gọi là *mutator threads*). Shenandoah đã trở thành tính năng production từ **JDK 15** (JEP 379) và tiếp tục được phát triển trong các JDK hiện hành.

Ba khái niệm phải xem cùng nhau:

1. **Region:** đơn vị chia nhỏ heap và quản lý thu hồi/di chuyển object. Kích thước region do HotSpot lựa chọn theo heap, chế độ và implementation; nó **không phải kích thước từng object**.
2. **Vùng dự phòng (*reserve/headroom*):** khoảng không gian mà collector cần để **di chuyển object còn sống (evacuation)** và để mutator tiếp tục cấp phát khi GC đang chạy. Không phải toàn bộ free heap đều được tiêu theo một mục đích.
3. **Tốc độ cấp phát (*allocation rate*):** số byte mà application threads tạo ra mỗi đơn vị thời gian, kể cả các object rất nhanh chết. Nếu cấp phát quá nhanh so với khả năng reclaim của GC và không còn headroom, Shenandoah có thể phải **pacing**, hoặc rơi vào cơ chế recovery có pause dài hơn.

```text
Java application (mutators)
      |
      +---- cấp phát object mới (allocation) ----+
      |                                         |
      v                                         v
  Heap regions ---------------------------> vùng còn trống
      |                                         |
      +--- GC marking/evacuation/update --------+
                (nhiều bước concurrent)
                       |
                       +--> reclaim object chết
                       +--> cần chỗ nhận object sống khi di chuyển
                       +--> cần headroom cho allocation đang tiếp diễn
```

**Điểm phải nhớ:** một service chỉ có live set 1 GiB không có nghĩa `-Xmx1g` là đủ để Shenandoah chạy ổn định. Trong khi collector đang làm việc, application vẫn có thể tạo thêm hàng trăm MiB/giây, còn evacuation cần thêm nơi chứa các object còn sống. Ngược lại, **tổng byte đã từng cấp phát trong nhiều phút** có thể lớn gấp nhiều lần heap mà ứng dụng vẫn chạy tốt vì phần lớn object đã chết và được thu hồi kịp.

Mục tiêu bài học là hiểu và **đo lường** quan hệ này bằng log và ví dụ Java 17+, không áp dụng tùy tiện những công thức cố định hoặc các JVM flag cũ không được xác nhận ở bản JDK đích.

## 2. Region trong Shenandoah là gì?

Shenandoah chia Java heap thành các **vùng nhớ liên tiếp có kích thước xác định cho một lần chạy JVM**. Các region là đơn vị quan trọng khi collector đánh dấu, lựa chọn vùng có nhiều rác, di chuyển object sống, thu hồi không gian và quản lý vùng trống.

Các trạng thái/thuộc tính có ích khi đọc GC log hoặc tìm hiểu nội bộ Shenandoah:

| Khái niệm | Vai trò | Không nên hiểu nhầm |
|---|---|---|
| **Empty/free region** | Region chưa dùng, có thể cấp phát cho một mục đích mới | Không chắc mọi region trống đều được cấp phát ngay cho mutator vì có reserve |
| **Regular region** | Nơi chứa các object thông thường | Một region có thể chứa **nhiều object**, không phải “mỗi object một region” |
| **Humongous object/region** | Object quá lớn so với ngưỡng của region, có thể chiếm nhiều region liên tiếp | Không đồng nghĩa “large object = 1 region”; phần dư ở region cuối có thể gây fragmentation |
| **Collection set (CSet)** | Tập region GC chọn xử lý/evacuate trong một chu kỳ | GC không phải lúc nào cũng di chuyển mọi object trong heap |
| **Evacuation** | Chuyển các **object còn sống** từ các vùng được chọn sang nơi mới | Di chuyển cần thêm không gian; region có nhiều rác không đồng nghĩa toàn bộ bytes lập tức có thể dùng |
| **Reclaimed/free space** | Không gian được giải phóng sau khi region đủ điều kiện tái sử dụng | Không cộng trực tiếp mọi số “Free” trong log thành heap trống cho mutator |
| **Young/old affiliation** | Trong **generational Shenandoah**, region có liên hệ với thế hệ young/old | Không áp dụng cách phân young/old như thế cho `satb` single-generation |

Trong Shenandoah, một region có thể bị chọn vào **collection set** khi dự kiến thu hồi đủ rác để đáng chi phí di chuyển các object sống. Region có **ít garbage nhưng nhiều live bytes** có thể mang lại ít lợi ích do lượng evacuation lớn.

### 2.1. Region không được cấp riêng vĩnh viễn cho một Java thread

Có thể ứng dụng sử dụng TLAB (thread-local allocation buffer) để tăng hiệu quả cấp phát, nhưng TLAB là cơ chế cấp phát **bên trong heap**, khác với ý nghĩa của **region**. Đừng mô tả rằng “mỗi region được gán cho một application thread” hay “đổi số luồng sẽ tự đổi số region” như một quy tắc của Shenandoah.

### 2.2. Region size tùy heap và JVM

**Không hard-code** một kích thước region chung như 1 MiB hoặc 4 MiB cho mọi Shenandoah deployment. Trên môi trường thử **OpenJDK Zulu 24.0.2, Windows, HotSpot**, với:

```bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -Xlog:gc*=info -version
```

GC log khi chạy chương trình đầy đủ đã ghi:

```text
Heap Region Count: 1024
Heap Region Size: 256K
```

Trong ví dụ đó, `1024 × 256 KiB = 256 MiB`, phù hợp với heap maximum 256 MiB. Đây là **quan sát của một phiên bản/build và cặp giới hạn heap cụ thể**, không phải hằng số trong Java specification. Một service có `-Xmx8g`, một bản JDK khác hoặc cấu hình khác có thể dùng region size khác.

Cần phân biệt:

- **Reserved address space**: vùng địa chỉ ảo đã dự trữ cho heap.
- **Committed memory**: phần đã commit từ OS, dùng để chứa dữ liệu trong quy trình JVM.
- **Used/live bytes**: lượng heap đang chứa object, với live set là phần thực sự vẫn reachable.
- **Free space/region**: không gian có thể được collector phân phối nhưng có thể bị chia theo **quyền sử dụng** cho mutator và collector.

**Đừng lấy `Heap Region Count` nhân `Heap Region Size` để suy ra toàn bộ RAM vật lý đang bị tiêu thụ.** `-Xmx`, reserved space, committed heap, RSS và memory limit của container là các đại lượng khác nhau.

## 3. Humongous allocation và fragmentation

Một object lớn, chẳng hạn một `byte[]` dài nhiều MiB, có thể vượt ngưỡng cấp phát **regular** và được Shenandoah xem là **humongous**. Cách phân loại phụ thuộc region size, object header/alignment và quy tắc của collector. Trong Shenandoah, các object đủ lớn so với region có thể cần **nhiều region liên tiếp**.

Điều này dẫn tới những hiện tượng:

- Object có thể chiếm các region nhưng **không dùng hết region cuối**, tạo *internal fragmentation*.
- Có tổng free bytes lớn nhưng **không đủ chuỗi region trống liên tiếp** cho một humongous object.
- Cấu hình thay đổi heap/region size có thể làm cùng một kích thước mảng đi qua đường cấp phát khác.
- Rất nhiều array lớn và sống lâu có thể gây áp lực cho free-set, evacuation reserve và các đợt GC.

**Không khuyến nghị “tăng region size” chỉ vì thấy humongous allocations.** Trước hết đo size distribution của object, retention, GC log/heap profile và xem liệu có thể **stream, chunk hoặc tái sử dụng buffer đúng cách** không.

Ví dụ minh họa về vùng và fragmentation:

```text
Region size giả định: 256 KiB (một ví dụ)
Object size giả định: 600 KiB
→ có thể cần 3 region liên tiếp: 768 KiB không gian region
→ phần không dùng ở cuối region cuối là overhead phân mảnh

Đây là mô hình để hiểu vấn đề, KHÔNG phải contract
cho mọi heap/layout/version của Shenandoah.
```

Đừng biến phép tính ví dụ này thành quy tắc rằng mọi object 600 KiB đều chiếm đúng ba region ở mọi JDK.

## 4. Tại sao collector phải có vùng dự phòng?

Shenandoah thực hiện **concurrent evacuation** ở những chế độ phù hợp, nghĩa là nhiều object còn sống được di chuyển trong lúc application vẫn chạy. Việc di chuyển **không phải chỉ đánh dấu một vùng đã trống**: cần nơi để đặt bản sao của object sống trước khi vùng nguồn có thể được thu hồi an toàn.

Trong khi đó, **mutators tiếp tục cấp phát** object mới.

```text
Free heap / free-set (mô hình khái niệm)
|
+-- Headroom cho MUTATOR
|     Java code tiếp tục new object khi GC đang chạy
|
+-- Headroom / COLLECTOR RESERVE
|     nơi chứa object còn sống cần được evacuate
|
+-- Phần có thể không phân phối ngay do
      fragmentation / region state / GC phase
```

Vì vậy, **free bytes toàn heap** và **free bytes dùng ngay cho mutator** có thể không trùng nhau. Việc collector giữ một reserve **không phải “lãng phí bộ nhớ”**; nó giúp tránh tình huống mutator sử dụng hết chỗ trống trước khi GC kịp di chuyển object sống.

### 4.1. Ví dụ quan sát `Collector Reserve`

Với ví dụ Java 17 ở phần 10 và `-Xmx256m`, trên **OpenJDK Zulu 24.0.2** log từng có các trường như:

```text
Free: 243M, ... Mutator Free: 972 Collector Reserve: 13312K, ...
```

**Diễn giải:**

- `Free: 243M`: thông tin free-space được log ở thời điểm đó.
- `Mutator Free: 972`: trong cách ghi của bản Shenandoah thử, đây là **số lượng region free dành cho mutator**, **không phải 972 MiB**.
- `Collector Reserve: 13312K`: mức reserve được trình bày theo **KiB** tại thời điểm đó, **không phải 13.312% heap**, cũng không phải một giá trị mặc định áp dụng cho mọi JVM.
- `Max: 256K regular`: giới hạn kích thước contiguous regular allocation theo trạng thái free-set/log đang ghi, không phải `-Xmx`.

Nội dung, tên trường và đơn vị log có thể thay đổi giữa **SATB** và **generational Shenandoah**, phiên bản JDK và distribution. Đừng viết một parser cố định ghép cột theo khoảng trắng rồi coi thứ tự/nhãn log là API công khai bất biến.

**Đặc biệt:** reserve là một phần trong **quy hoạch GC**, không phải lời cam kết rằng một lệnh `new byte[13_312 * 1024]` chắc chắn thành công hoặc có thể chiếm toàn bộ collector reserve.

### 4.2. Collection set cần được định cỡ theo không gian evacuation

Giả sử một GC cycle chọn một collection set chứa:

```text
CSet total bytes = 100 MiB
   ├── live bytes    = 30 MiB
   └── garbage bytes = 70 MiB
```

GC có thể thu hồi khoảng 70 MiB **sau khi xử lý đúng quy tắc**, nhưng cần đủ không gian để chuyển phần **30 MiB live** (cùng với metadata/overhead, fragmentation và safety margin). Nếu headroom rất thấp, việc chọn CSet quá tham vọng có thể khiến **evacuation failure**.

Số này chỉ là ví dụ **khái niệm**, không phải phép tính chính xác của mọi cycle. Collector chọn CSet dựa vào heuristic, ước lượng live data, free-set và các ràng buộc khác.

### 4.3. Reserve không phải `-Xms` hay `-Xmx`

- `-Xmx`: giới hạn Java heap tối đa.
- `-Xms`: kích thước heap khởi tạo/tối thiểu theo chính sách JVM.
- **Evacuation/collector reserve**: phần headroom nội bộ Shenandoah duy trì để GC tiếp tục hoạt động.
- **Native memory headroom**: RAM ngoài Java heap như metaspace, thread stacks, direct buffers, JIT/code cache, GC metadata.

Đặt `-Xmx` sát container memory limit có thể khiến cả process bị **OOMKilled** vì native memory, dù Shenandoah có đủ collector reserve trong heap. Ngược lại, container còn nhiều RAM không tự cứu một JVM đang chạm `-Xmx` và thiếu region trống.

## 5. Tốc độ cấp phát (*allocation rate*) là gì?

**Allocation rate** là lượng object memory do ứng dụng yêu cầu cấp phát trên một khoảng thời gian:

```text
allocation_rate = total_allocated_bytes / elapsed_seconds
```

Ví dụ ứng dụng tạo tổng cộng **300 MiB** object mới trong **3 giây**:

```text
allocation_rate ≈ 100 MiB/s
```

Đây **không** phải live-set growth rate. Nếu những object đó chết ngay, GC vẫn phải quản lý tốc độ allocation, nhưng live-set có thể gần như không tăng. Nếu cùng 300 MiB vẫn reachable, heap occupancy có thể tăng gần tương ứng (tùy overhead/alignment và những object khác).

| Đại lượng | Ý nghĩa | Dùng để làm gì? |
|---|---|---|
| **Allocation rate (MiB/s)** | Tổng byte object được tạo mỗi giây | Dự báo áp lực cấp phát trong một GC cycle |
| **Allocation burst/spike** | Tốc độ tăng cao trong khoảng ngắn | Cần headroom để hấp thụ đỉnh tải |
| **Live-set size** | Tổng dữ liệu còn reachable | Xác định bộ nhớ không thể thu hồi trong cycle hiện tại |
| **Reclaim rate** | Tốc độ GC giải phóng không gian tái sử dụng | So với áp lực cấp phát cùng kỳ |
| **Evacuation demand** | Số byte object sống cần được dời | Dự trù collector reserve và CPU/memory bandwidth |
| **Mutator utilization** | Thời gian CPU/tiến độ công việc của ứng dụng | Đánh giá trade-off GC concurrent/pacing |
| **GC cycle duration** | Thời gian từ bắt đầu đến hoàn tất cycle | Tính thời gian ứng dụng tiếp tục cấp phát trước khi có thêm free space |
| **Allocation stall/pacing time** | Thời gian application chờ khi cấp phát | Đo tác động latency dù pause GC ngắn |

**Đừng dùng `Runtime.totalMemory() - freeMemory()` chia cho thời gian** làm allocation rate. Biểu thức đó đo *heap used quan sát được*, bị ảnh hưởng GC/commit, không cộng các object đã cấp phát rồi chết giữa hai mẫu.

Trong production, có thể quan sát **thread allocation metrics**, JFR Allocation events, GC logs/telemetry và heap profiling phù hợp. Phần 10 có một phép thử **đếm byte[] đã yêu cầu tạo trong code** để minh họa rate; số đó **không đại diện toàn bộ allocations của JVM**.

## 6. Quan hệ giữa allocation rate, thời gian cycle và vùng dự phòng

Shenandoah cố hoàn tất concurrent GC trước khi mutators dùng hết vùng trống dành cho họ. Một mô hình suy nghĩ đơn giản:

```text
bytes cấp phát thêm trong chu kỳ
    ≈ allocation_rate × gc_cycle_duration

headroom cần thiết (xấp xỉ để lập kế hoạch)
    ≥ bytes ứng dụng có thể cấp phát khi GC chạy
      + evacuation/rebuild reserve cần thiết
      + safety margin cho bursts và fragmentation
```

**Đây là công thức trực giác, không phải thuật toán sizing chính xác của HotSpot.** Trong thực tế GC có thể reclaim được không gian ngay trong chu kỳ, allocation rate thay đổi, live-set biến động, promotion/humongous object có yêu cầu riêng và heuristic học từ lịch sử GC.

### 6.1. Ví dụ số có điều kiện

Giả sử trong một cửa sổ tải cao:

- Allocation rate: **120 MiB/s**.
- Một cycle cần **0,5 giây** để hoàn tất.
- Trong thời gian đó mutators có thể tạo khoảng **60 MiB** object.
- GC cần thêm khoảng **20 MiB** để evacuate object còn sống.
- Safety margin giả định **30 MiB**.

```text
Ví dụ nhu cầu headroom ≈ 60 + 20 + 30 = 110 MiB
```

Nếu chỉ còn 45 MiB headroom khả dụng khi bắt đầu cycle, workload **có nguy cơ** gặp pacing/stall/recovery, dù heap “đang mới dùng có vẻ chưa hết”. Nếu hệ thống tăng allocation lên **240 MiB/s** mà cycle duration không thay đổi, chỉ riêng lượng allocation trong cycle đã lên khoảng **120 MiB**.

**Không lấy 110 MiB làm giá trị cố định để cấu hình JVM**. Các con số evacuation và safety ở đây là giả định để giải thích; phải đo ứng dụng thật và quy mô tải đỉnh.

### 6.2. Tại sao tốc độ *đỉnh* quan trọng hơn trung bình?

Một service có average allocation rate 40 MiB/s nhưng spike 400 MiB/s trong 100 ms sẽ tạo khoảng **40 MiB** trong một đợt rất ngắn. Heuristic dựa vào lịch sử có thể cần **spike tolerance/headroom** để không bị bất ngờ.

Vì vậy khi benchmark, quan sát:

- **MiB/s trung bình theo phút** và theo cửa sổ ngắn.
- Cấp phát theo request, theo batch, theo thread và theo traffic burst.
- Thời gian concurrent mark/evac/update, số GC cycles.
- Pacing stalls và đợt GC bị chuyển sang recovery.
- Tương quan với p99/p99.9 latency và throughput.

Nếu chỉ tính average trong 10 phút, một spike gây GC failure có thể bị che hoàn toàn.

## 7. Shenandoah quyết định khi nào GC bắt đầu?

Collector dùng **heuristics** để cân bằng làm việc sớm hay muộn, kích thước collection set và việc giữ free heap/headroom. Theo tài liệu Java SE 26, có:

- **`-XX:ShenandoahGCHeuristics=adaptive`**: mặc định trong Shenandoah; ước tính từ lịch sử GC và lượng free để duy trì headroom cả khi GC đang chạy.
- **`static`**: khởi động cycle dựa vào free-space threshold cố định theo logic của heuristic đó.
- **`compact`**: thu gom thường xuyên hơn để reclaim kịp thời, có thể tốn CPU/throughput hơn.

**Quan trọng với bản mới:** trong **generational Shenandoah**, tài liệu JDK 26 ghi **chỉ hỗ trợ `adaptive`**. Không copy flag `static`/`compact` từ hướng dẫn cũ vào cấu hình generational rồi coi là chắc chắn hợp lệ.

Lệnh lựa chọn thông thường:

```bash
java -XX:+UseShenandoahGC -Xmx256m -cp . ShenandoahAllocationDemo
```

Với JDK 26, nếu chỉ bật `UseShenandoahGC` mà không chọn mode, theo `java` manual **mặc định `ShenandoahGCMode=satb`** (single-generation). Muốn dùng generational trên một **JDK 25+ HotSpot build hỗ trợ**, có thể yêu cầu:

```bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xmx256m -cp . ShenandoahAllocationDemo
```

Không giả định generational là mặc định của **JDK 26**; không suy diễn từ sự phát triển của **ZGC** sang Shenandoah. Cần kiểm tra đúng `java -version`, `VM.flags`, `-Xlog:gc+init` và tài liệu vendor.

## 8. Pacing, allocation failure và recovery

Khi allocation tăng quá nhanh, concurrent collector có thể **không kịp giải phóng đủ region**. Shenandoah có cơ chế phản ứng theo tình huống/mode; điều quan trọng là hiểu mức độ nghiêm trọng tăng dần.

### 8.1. Pacing: làm chậm cấp phát có kiểm soát

**Shenandoah pacing** có thể làm một application thread **đợi ngắn tại đường cấp phát** để GC có thêm thời gian hoàn tất, thay vì để mutator vét hết headroom.

```text
Allocation rate tăng / free headroom giảm
         |
         +--> Pacer điều tiết tiến độ mutator allocation
                   |
                   +--> GC tiếp tục làm việc concurrent
                   +--> nếu đủ headroom: tiếp tục bình thường
                   +--> nếu không đủ: nguy cơ allocation failure
```

Cơ chế này giảm rủi ro nghiêm trọng hơn, nhưng **pacing chính là một dạng độ trễ ở application thread**. Một dịch vụ có **GC pause rất thấp** vẫn có thể có latency spike do pacing.

Trong log OpenJDK 24 đã kiểm tra có dòng:

```text
Pacer for Idle. Initial: 5242K, Alloc Tax Rate: 1.0x
```

Cũng có các phase `Pacer for Mark`. Dòng này cho thấy cơ chế pacer được ghi log; **`Alloc Tax Rate` không phải đơn vị MiB/s của Java allocations**, nên không dùng con số `1.0x` để nói ứng dụng đang tạo 1 MiB/s.

### 8.2. Allocation failure và thu gom recovery

Khi free-set không còn đáp ứng được một yêu cầu cấp phát/evacuation, Shenandoah có thể phải chuyển sang **degenerated GC** (một bước recovery *stop-the-world* dùng lại tiến độ cycle đang có) và nếu không khôi phục được thì đến **Full GC**. Hành vi và thứ tự chính xác phụ thuộc mode/JDK/build, nên cần quan sát log của deployment thực.

Đây là tình trạng đáng điều tra:

- `-Xmx` thiếu headroom so với live-set và spikes.
- Concurrent GC không theo kịp do CPU quota hoặc allocation quá nhanh.
- Có nhiều object dài sống, collection set không thu hồi được nhiều.
- Humongous allocations/fragmentation và yêu cầu vùng liên tiếp.
- Unbounded queues, caches, retention hoặc memory leaks.

**Đừng xem Full GC là hoạt động Shenandoah bình thường cần xảy ra đều đặn.** Nếu degenerated/full xảy ra thường xuyên, kiểm tra workload và cấu hình thay vì chỉ tăng số GC threads hoặc giảm một threshold bất kỳ.

### 8.3. Pacing không đồng nghĩa GC pause

| Hiện tượng | Bản chất | Tín hiệu đo |
|---|---|---|
| **GC safepoint/pause** | JVM có giai đoạn dừng application threads | GC pause event/log, safepoint metrics |
| **Pacing delay** | Một luồng ứng dụng bị điều tiết khi allocation | Pacer/ergo log, latency và thread behavior |
| **Allocation failure** | Không có đủ vùng cấp phát phù hợp theo thời điểm | GC log với failure/recovery |
| **Degenerated GC** | Recovery stop-the-world | Event Degenerated, pause tăng |
| **Full GC** | Thu gom rộng hơn với pause lớn | Full GC logs và latency spike |
| **OOM / OOMKilled** | JVM heap hoặc tổng memory process/container cạn | Exception và OS/container event |

Thống kê **chỉ một cột GC pause time** không phản ánh đầy đủ chi phí pacing và thời gian ứng dụng không tiến triển.

## 9. Chọn JDK và mode hiện hành, không dùng tài liệu quá cũ

ZGC và Shenandoah là **hai collector khác nhau**. Việc ZGC generational trở thành mode duy nhất trên JDK 24 **không** có nghĩa Shenandoah cũng đã bỏ mode `satb`.

| Phiên bản/loại JVM | Diễn giải có thể áp dụng |
|---|---|
| **Java 15 HotSpot** | Shenandoah trở thành production (JEP 379); đây là bối cảnh lịch sử, không khuyến nghị deploy mới trên bản đã hết vòng đời |
| **JDK 17 LTS** | Shenandoah đang được sử dụng; tập mode/GC flags có thể khác JDK mới. Kiểm tra build/vendor |
| **JDK 21 LTS** | Hỗ trợ Shenandoah theo distribution; không tự áp dụng mọi tính năng generational đời mới |
| **JDK 24** | Bản Zulu/HotSpot đã thử chạy `UseShenandoahGC`, mặc định `ShenandoahGCMode=satb`; log quan sát region 256K khi `-Xmx256m` |
| **JDK 25/26 HotSpot hỗ trợ** | Generational Shenandoah là một mode production từ JDK 25 (JEP 521), có thể lựa chọn tường minh; **JDK 26 manual vẫn mặc định `satb`** |
| **JVM khác HotSpot** | Không được coi `-XX:+UseShenandoahGC` là JVM option portable |

Ví dụ kiểm tra mode thực:

```bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version
```

Tìm `ShenandoahGCMode`, `ShenandoahGCHeuristics`, `UseShenandoahGC` trong output. Có thể dùng:

```bash
java -XX:+UseShenandoahGC -Xlog:gc+init=info -version
```

Thông tin init log có thể ghi rõ mode/region size. Không cố ép **experimental generational flags của những bản preview cũ** vào các JDK đã có mode production, và không mặc định mọi distribution cùng hỗ trợ một mode chỉ dựa vào số phiên bản ngôn ngữ.

## 10. Ví dụ Java 17+ chạy được: tổng cấp phát, live set và rate

Ví dụ này được thiết kế để:

- Tạo một lượng **object ngắn sống có kiểm soát**: 3.072 mảng `byte[64 KiB]`, tổng **192 MiB** cấp phát qua thời gian.
- Giữ lại **192 mảng `byte[64 KiB]`** trong một `ArrayList`, tổng **12 MiB** dữ liệu payload vẫn reachable đến cuối main.
- Tổng **204 MiB** payload được cấp phát, nhưng **không** có nghĩa cùng lúc toàn bộ 204 MiB nằm trong heap.
- Tính **observed allocation rate** của riêng loop demo theo `System.nanoTime()`; phần đo có thể bật thêm bằng `-DshowRate=true`.
- Kiểm tra **tên GarbageCollectorMXBean có chứa “Shenandoah”** trên HotSpot build thử nghiệm.
- In **6 dòng output ổn định** khi không bật `showRate`.

Các mảng `64 KiB` đủ nhỏ so với **region 256K quan sát được ở môi trường thử** để không chủ động minh họa humongous allocations. Với JDK/heap khác, ngưỡng object lớn vẫn có thể khác. `lastTemporary` là field `volatile`, khiến mảng cấp phát được publish ra ngoài vòng xử lý nhằm giảm khả năng JIT loại bỏ toàn bộ cấp phát như một biến local không quan sát được.

### 10.1. Source file `ShenandoahAllocationDemo.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class ShenandoahAllocationDemo {
    private static final int KIB = 1024;
    private static final int MIB = KIB * KIB;
    private static volatile byte[] lastTemporary;

    public static void main(String[] args) {
        boolean shenandoahActive = ManagementFactory
                .getGarbageCollectorMXBeans().stream()
                .map(GarbageCollectorMXBean::getName)
                .anyMatch(name -> name.toLowerCase(Locale.ROOT).contains("shenandoah"));

        int shortLivedBlocks = 3072;
        int retainedBlocks = 192;
        int bytesPerBlock = 64 * KIB;
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0L;
        long started = System.nanoTime();

        for (int i = 0; i < shortLivedBlocks; i++) {
            byte[] block = new byte[bytesPerBlock];
            block[0] = (byte) i;
            lastTemporary = block; // Ensures actual allocations remain observable.
            checksum += Byte.toUnsignedInt(block[0]);
        }

        for (int i = 0; i < retainedBlocks; i++) {
            byte[] block = new byte[bytesPerBlock];
            block[0] = (byte) i;
            retained.add(block); // A small, intentionally retained live set.
        }

        long elapsedNanos = System.nanoTime() - started;
        long totalBytes = (long) (shortLivedBlocks + retainedBlocks) * bytesPerBlock;
        double elapsedSeconds = Math.max(elapsedNanos / 1_000_000_000.0, 0.000_000_001);
        double observedRateMiBps = (totalBytes / (double) MIB) / elapsedSeconds;

        System.out.println("collectorIsShenandoah=" + shenandoahActive);
        System.out.println("shortLivedMiB=" + ((long) shortLivedBlocks * bytesPerBlock / MIB));
        System.out.println("retainedMiB=" + ((long) retainedBlocks * bytesPerBlock / MIB));
        System.out.println("totalAllocatedMiB=" + (totalBytes / MIB));
        System.out.println("allocationRatePositive=" + (observedRateMiBps > 0));
        System.out.println("checksum=" + checksum);

        if (Boolean.getBoolean("showRate")) {
            System.out.printf(Locale.ROOT, "observedAllocationRateMiBps=%.1f%n",
                    observedRateMiBps);
        }
        Reference.reachabilityFence(retained);
    }
}
```

Các API đều có trong **Java 17**. Chương trình **không gọi `System.gc()`** vì API đó không buộc một GC cycle nhất định phải bắt đầu/kết thúc và không cần thiết để kiểm thử phương thức cấp phát.

### 10.2. Compile và chạy

Tại thư mục chứa file (lưu UTF-8):

```bash
javac --release 17 -encoding UTF-8 ShenandoahAllocationDemo.java
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -cp . ShenandoahAllocationDemo
```

**Stdout chính xác đã kiểm chứng** trên **OpenJDK Zulu 24.0.2 Windows, HotSpot**:

```text
collectorIsShenandoah=true
shortLivedMiB=192
retainedMiB=12
totalAllocatedMiB=204
allocationRatePositive=true
checksum=391680
```

Giải thích:

- `collectorIsShenandoah=true`: tên của một GC MXBean chứa `Shenandoah`. Đây là phép kiểm tra **phù hợp với HotSpot đã thử**, không phải API bảo đảm mọi JVM dùng tên bean giống nhau.
- `shortLivedMiB=192`: `3072 × 64 KiB = 192 MiB`. Các mảng ngắn sống được thay trong `lastTemporary` và đủ điều kiện thu hồi khi không còn reachable.
- `retainedMiB=12`: `192 × 64 KiB = 12 MiB`; `List` còn giữ references đến các mảng. `Reference.reachabilityFence(retained)` đảm bảo list còn reachable tới thời điểm đó.
- `totalAllocatedMiB=204`: tổng **payload byte-array** do chính hai vòng lặp tạo. Không tính object headers, `ArrayList` internals, class/JIT overhead hay allocations từ thư viện/JVM.
- `allocationRatePositive=true`: phép đo trên khoảng thời gian dương trả một rate dương; không phải số benchmark chuẩn.
- `checksum=391680`: 3.072 vòng gồm 12 chu kỳ đủ 256 giá trị byte; `12 × (0 + 1 + ... + 255) = 391680`. Không thay đổi giữa hai lần chạy có cùng source code.

**Đừng hiểu 204 MiB là heap used ở cuối chương trình**. Nhiều mảng ngắn sống không còn reachable; heap occupancy còn phụ thuộc GC đã chạy đến phase nào và những object khác.

### 10.3. In tốc độ thực đo trong lần chạy

Chạy thêm property do demo định nghĩa:

```bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -DshowRate=true -cp . ShenandoahAllocationDemo
```

Output có **6 dòng trên**, cộng thêm dòng dạng:

```text
observedAllocationRateMiBps=2739.9
```

**Giá trị 2739.9 chỉ là kết quả của một lần chạy thực trên máy thử**, không phải output cần khớp, không phải throughput của Shenandoah hoặc một bảo đảm về tốc độ tối đa. Chạy lại có thể cao/thấp hơn do JIT warm-up, CPU, OS scheduling, nền tảng và số GC cycles. Đây cũng là **allocation rate đo từ số bytes do code chủ động cấp phát**, khác metrics allocation toàn tiến trình.

Cách tính nằm trong code:

```java
double elapsedSeconds = Math.max(elapsedNanos / 1_000_000_000.0, 0.000_000_001);
double observedRateMiBps = (totalBytes / (double) MIB) / elapsedSeconds;
```

Đoạn này là **trích đoạn minh họa** từ class, không có ý nghĩa độc lập nếu chưa khai báo biến. Đừng lấy một con số từ benchmark ngắn để sizing toàn bộ cluster. Cần chạy lâu hơn, warm-up, concurrency, payload thực tế và phân tích percentiles.

### 10.4. So với collector không phải Shenandoah

```bash
java -Xms64m -Xmx256m -cp . ShenandoahAllocationDemo
```

Trên JVM Zulu 24 đã thử, `collectorIsShenandoah=false`; các dòng số byte/checksum vẫn như trên. **Kết quả false không tự nói collector khác là G1 hay Serial**, chỉ nói demo không tìm thấy tên bean chứa Shenandoah.

GC được chọn khi **JVM khởi động**, không thể chuyển Shenandoah↔G1 giữa chừng bằng `System.setProperty`. Muốn so sánh, khởi động **hai tiến trình riêng** với cấu hình rõ, và đo latency/throughput với workload công bằng.

## 11. Đọc GC log: region, free-set, reserve và pacer

Với chương trình đã biên dịch, chạy và ghi log riêng:

```bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -Xlog:gc*=info:file=shenandoah-gc.log:uptime,level,tags -cp . ShenandoahAllocationDemo
```

Trong **PowerShell**:

```powershell
java '-XX:+UseShenandoahGC' '-Xms64m' '-Xmx256m' '-Xlog:gc*=info:file=shenandoah-gc.log:uptime,level,tags' -cp . ShenandoahAllocationDemo
```

GC log nằm trong file `shenandoah-gc.log` ở working directory; stdout của ứng dụng vẫn là 6 dòng như trên. Nếu JVM không có quyền ghi file log, phải cấp quyền/chọn đường dẫn phù hợp, **không tự coi GC không chạy**.

### 11.1. Các tín hiệu thực đã quan sát

Ở một lượt chạy trên **OpenJDK Zulu 24.0.2** log có các dòng (lược bớt timestamp và vài trường phụ):

```text
Using Shenandoah
Heap Region Count: 1024
Heap Region Size: 256K
Free: 243M, ... Mutator Free: 972 Collector Reserve: 13312K, ...
Pacer for Idle. Initial: 5242K, Alloc Tax Rate: 1.0x
```

Đây là **trích đoạn quan sát**, không phải một block liên tiếp nguyên văn của mọi lần chạy. Mỗi dòng thuộc **phase/level/tag khác nhau** trong GC log. Vui lòng phân biệt:

- `Heap Region Size: 256K`: đặc tính region của lần chạy đó.
- `Mutator Free: 972`: số region mutator free ở snapshot đó theo format HotSpot build thử nghiệm.
- `Collector Reserve: 13312K`: reserve cho collector ở thời điểm đó.
- `Pacer for Idle...`: thông tin pacing, không phải rate MiB/s của ứng dụng.
- `Using Shenandoah`: xác nhận runtime đã chọn collector.

Nếu tăng `-Xmx`, chạy một workload khác, đổi `ShenandoahGCMode` hoặc JDK, các số này **có thể thay đổi hoàn toàn**. Đừng đưa `Collector Reserve=13312K` thành mặc định production cho một heap 256 MiB ở bất kỳ bản JDK nào.

### 11.2. Những dòng cần tìm khi ứng dụng chậm

Trong log nhiều phiên bản Shenandoah, tìm các ý:

- **GC trigger / heuristics**: vì sao cycle bắt đầu (free threshold, learning, allocation pressure).
- **Concurrent marking**: collector đang đánh dấu reachable objects.
- **Collection set / evacuation**: vùng được chọn và lượng live cần di chuyển.
- **Free regions / reserve**: headroom cho mutator so với collector.
- **Pacing**: mutators có thể bị điều tiết khi allocation quá nhanh.
- **Allocation Failure / Degenerated / Full GC**: dấu hiệu collector không hoàn tất kịp với free space hiện có.
- **Humongous**: large objects, contiguous region demand và fragmentation.
- **Pause time / safepoint**: đo stop-the-world phases, tách khỏi thời gian chờ do pacing.

Bạn có thể dùng `-Xlog:help` để xem tag/level mà **JDK đang chạy thực sự hỗ trợ**:

```bash
java -Xlog:help
```

Không hard-code một tập tag từ JDK 15 rồi kết luận JDK 26 có format log giống hệt. Các ví dụ dùng **unified logging** hiện hành, không dùng các cờ `-XX:+PrintGCDetails` đời cũ.

### 11.3. Mức log và chi phí

`-Xlog:gc=info` thường gọn; `-Xlog:gc*=info` có thể tạo **nhiều thông tin** về init, free-set và ergonomics. Các mức `debug/trace` cần được dùng có chủ đích vì có thể tăng overhead, file size và thời gian xử lý log.

Trong production, cấu hình **log rotation/retention, disk quota, quyền đọc** và bảo vệ thông tin gián tiếp. Nếu chỉ cần chứng minh đang chạy Shenandoah, `-Xlog:gc=info` kết hợp `jcmd` thường đủ, không cần ghi file debug hàng gigabyte.

## 12. Đừng nhầm “free heap” với “free memory của OS”

Bộ nhớ nhìn từ Java có nhiều lớp:

```text
Cgroup / RAM của tiến trình
      |
      +-- Java heap (<= -Xmx)
      |       +-- used/live data
      |       +-- free regions/space
      |       +-- collector/mutator reserves bên trong heap
      |
      +-- native memory
              +-- metaspace/class metadata
              +-- code cache/JIT
              +-- thread stacks
              +-- direct buffers/JNI
              +-- GC native structures và các phần khác
```

`Runtime.getRuntime().maxMemory()` báo một giá trị **heap maximum**; `MemoryMXBean` và `MemoryPoolMXBean` giúp quan sát used/committed/max của các memory pool do JVM công bố. **Không có một standard Java Management API** bắt buộc mọi Shenandoah provider công bố riêng **Region Size** hoặc **Collector Reserve** theo một property bất biến. Những số đó thường phải lấy từ **GC init/free logs** hoặc tooling đặc thù VM.

Một container còn 200 MiB free memory không nói rằng Shenandoah có 200 MiB free heap: phần memory đó nằm **ngoài JVM**. Một `OutOfMemoryError: Java heap space` cũng không đồng nghĩa toàn bộ RAM máy đã hết.

Nếu `-Xmx` đặt quá gần memory limit của container, tổng RSS và native buffers có thể kích hoạt **OOMKilled** ngay cả khi collector đang có free regions. Cần để **native headroom** bên ngoài Java heap.

## 13. Ba tình huống cần đọc đúng

### Tình huống A — Allocation cao, live set thấp

Một HTTP endpoint tạo nhiều DTO, JSON trees hoặc buffer ngắn sống nhưng trả response nhanh:

- **Allocation rate** có thể rất cao (hàng trăm MiB/s).
- **Live set** lại có thể thấp.
- Shenandoah vẫn phải reclaim liên tục và có thể cần GC CPU đáng kể.
- Nếu rate có những spikes cao và headroom thiếu, vẫn có thể gặp pacing dù không có memory leak.

Hướng ưu tiên: đo phân bổ allocations, tránh tạo object không cần thiết, cân nhắc tái sử dụng buffer **nếu an toàn và đáng chi phí**, batch/stream payload và giữ headroom đủ.

### Tình huống B — Allocation vừa phải, live set tăng liên tục

Một cache không giới hạn hoặc queue giữ references lâu hơn dự kiến:

- Allocation rate có thể chỉ trung bình.
- Nhưng live set cứ tăng, free regions giảm.
- Evacuation/cset khó thu hồi nhiều byte vì nhiều object còn sống.
- Thêm GC workers không sửa được một memory leak hoặc cache chưa giới hạn.

Hướng ưu tiên: profile retention (JFR/heap dump có kiểm soát), đặt giới hạn cache/queue, chính sách eviction, giải phóng references, kiểm soát backpressure. Nếu **live set gần `-Xmx`**, mọi collector đều sẽ gặp khó khăn.

### Tình huống C — Humongous objects và fragmentation

Ứng dụng thường xuyên tạo các array lớn, ảnh/video buffers hoặc batch payload:

- Một allocation có thể cần nhiều region liên tiếp.
- Nội bộ region cuối có thể bị waste.
- Free-set có nhiều bytes nhưng không có vùng đủ liên tiếp hoặc dành đúng mục đích.

Hướng ưu tiên: đo object-size histogram, giảm object lớn đột biến, stream/chunk nếu nghiệp vụ phù hợp, đo `humongous`/fragmentation log. Không mặc định tăng `ShenandoahRegionSize` hoặc thay một option không có trong JDK hiện tại.

## 14. Cách xử lý khi gặp pacing hoặc allocation failure

**Trình tự điều tra ưu tiên** trước khi đụng tới flags chuyên sâu:

1. **Chốt đúng JVM đang chạy**: `java -version`, `-XX:+UseShenandoahGC`, mode `satb`/generational và `ShenandoahGCHeuristics`.
2. **Đọc GC log có cùng timestamp với latency spike**: có pacing, allocation failure, degenerated hoặc full GC không?
3. **Đo live set và allocation rate** bằng workload production-like; phân biệt peak và average.
4. **Xem heap headroom**: `-Xmx` có dư vùng cho cả concurrent allocations và collector evacuation không?
5. **Kiểm tra CPU quota/saturation**: collector concurrent cần CPU thực; hệ thống ép CPU có thể khiến cycle kéo dài.
6. **Đánh giá fragmentation/humongous allocations**: có large object bị giữ lâu hoặc gây allocation failure không?
7. **Kiểm tra native/container memory**: `-Xmx` cộng các vùng memory khác có vượt container limit không?
8. **Giảm allocation/retention trong code** nếu có thể, rồi mới cân nhắc tăng heap phù hợp ngân sách.
9. **Benchmark với một thay đổi mỗi lượt**; ghi lại config, GC logs, p95/p99/p99.9, throughput và memory footprint.
10. **Triển khai rollback có kiểm soát** nếu việc thay đổi collector/heap làm tình trạng tệ hơn.

Một **khoảng heap dự phòng cần thiết không thể xác định bằng phần trăm cố định** cho mọi ứng dụng. Nó phụ thuộc tốc độ cấp phát theo thời điểm, live set, thời gian GC cycle, spike rate, region utilization, fragmentation và concurrency.

### Một số flags có thể thấy trong tài liệu Shenandoah

`ShenandoahAllocSpikeFactor`, các free-space thresholds, `ShenandoahPacing`, `ShenandoahEvacReserve` là những tên đã xuất hiện trong tài liệu/đời implementation Shenandoah. **Không khuyến nghị chép nguyên dãy flags này vào startup**: chúng có thể khác phạm vi hỗ trợ, giá trị mặc định, trạng thái experimental/diagnostic, thậm chí không còn tồn tại ở một version/mode.

Bài tập vận hành phù hợp hiện tại là để **adaptive heuristics** tự điều phối trước, rồi kiểm tra flags **được JVM đích công bố**:

```bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version
```

Nếu cần một tuning knob chuyên sâu, đọc tài liệu/nguồn đúng **JDK build và mode** và xác minh bằng `-Xlog:gc*=info`. **Không** dùng `-XX:+UnlockExperimentalVMOptions` như một bước thông thường chỉ để chạy Shenandoah production; các đời thử nghiệm generational cũ không phải mặc định hiện nay.

## 15. Thí nghiệm nhỏ để thấy tác dụng của heap headroom

Vẫn dùng chương trình `ShenandoahAllocationDemo.java`, chạy từng **process riêng**:

```bash
# Baseline heap đủ rộng cho bài demo
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -cp . ShenandoahAllocationDemo

# Cấu hình heap nhỏ hơn, tăng áp lực reclaim (chỉ dùng lab)
java -XX:+UseShenandoahGC -Xms32m -Xmx128m -Xlog:gc=info -cp . ShenandoahAllocationDemo

# Cấu hình heap lớn hơn, cùng payload demo
java -XX:+UseShenandoahGC -Xms128m -Xmx512m -Xlog:gc=info -cp . ShenandoahAllocationDemo
```

**Các command không hứa output/GC cycles giống nhau.** Chúng chỉ thay đổi **headroom của heap** cho cùng workload; hãy so GC log/cycle counts/pacing và response time. Không cố tình đặt `-Xmx` đến mức gây memory pressure ngoài container lab, không dùng trên production.

Một số yếu tố gây nhiễu:

- JIT warm-up/class loading khiến chương trình ngắn không phải benchmark production.
- CPU load, NUMA/OS scheduling và page commit khác nhau.
- GC ergonomics có thể tự thay đổi region size/thời điểm GC khi `-Xmx` đổi.
- Quá nhiều stdout/GC log có thể làm thay đổi throughput.
- Object allocation trong `ArrayList`, JVM và thư viện không nằm trong số 204 MiB tự đếm.

Do đó **không diễn giải 2–3 lần chạy ngắn thành bằng chứng ZGC, Shenandoah hay G1 tốt hơn**. Nếu phải đưa ra quyết định sản xuất, dùng workload đo lường lặp lại với p99 latency, throughput, CPU, RSS, heap pressure và thống kê GC có ý nghĩa.

## 16. Lỗi phổ biến và hướng xử lý

| Hiện tượng | Cách hiểu có thể sai | Điều cần làm |
|---|---|---|
| `-XX:+UseShenandoahGC` không khởi động | “Java 17/21/25 nào cũng có” | Kiểm tra HotSpot/JDK vendor, OS/architecture và build thực |
| Log nói `Heap Region Size: 256K` | “Mọi Shenandoah region đều 256 KiB” | Kiểm tra heap size/JDK/mode của đúng process |
| `Mutator Free: 972` | “Còn 972 MiB free” | Đọc đơn vị; ở build thử đó là **số region** |
| `Collector Reserve: 13312K` | “Application được phép chiếm cả reserve” | Reserve dành cho GC/evacuation; không phải bộ đệm app |
| Heap used thấp nhưng pacing xảy ra | “Collector chắc chắn bị lỗi” | Đo allocation spikes, free-set, GC cycle time và CPU |
| GC pause thấp nhưng p99 request cao | “Không thể do GC” | Kiểm tra pacing/allocation stalls và các bottlenecks ngoài GC |
| Nhiều Full GC/Degenerated GC | “Shenandoah bình thường như vậy” | Điều tra headroom, retention, humongous, CPU quota và spikes |
| Nhiều object 64 KiB | “Mọi object luôn chiếm đúng 64 KiB trong heap” | Tính object header/alignment; JFR/GC log đo footprint thật |
| Tổng cấp phát 204 MiB, heap tối đa 256 MiB | “Cuối bài phải dùng 204 MiB heap” | Tổng cấp phát ≠ live set ≠ used cuối bài |
| `rateMiBps` ở hai lần khác nhau | “Code sai do số không cố định” | Rate là phép đo thời gian, phụ thuộc máy/JIT/GC/tải |
| `ShenandoahGCMode=generational` không chạy ở JDK cũ | “Bộ thu gom biến mất” | Dùng mode phù hợp JDK, kiểm tra JEP521/JDK25+ |
| Nghĩ JDK 26 chọn generational mặc định | Nhầm với ZGC hoặc đề xuất JDK mới | Java SE 26 manual ghi default `satb` |
| Parser không tìm ra field free/reserve | Log schema/tag thay đổi | Tìm version-specific log/metrics, không parse cố định |
| `-Xmx` bằng container memory limit | “Reserve nằm trong heap nên tổng RAM luôn an toàn” | Chừa native headroom ngoài heap và đo RSS |
| `System.gc()` không in event mong đợi | “Shenandoah không hoạt động” | Dùng GC startup log, `VM.flags`, MXBeans; không ép `System.gc()` |

**Một điều kiện lỗi không phải bằng chứng một nguyên nhân duy nhất**. Allocation failure có thể do retention, tốc độ cấp phát, fragmentation, CPU quota, policy/mode hoặc sự kết hợp nhiều yếu tố.

## 17. Kiểm thử và QA trước khi triển khai thực

- [ ] Kiểm tra JDK/vendor/VM **trong container/host thực**, đảm bảo `-XX:+UseShenandoahGC` được hỗ trợ.
- [ ] Chọn rõ mode; đối với JDK 26 **mặc định `satb`**, generational là lựa chọn tường minh trên build phù hợp.
- [ ] Kiểm tra `-XX:ShenandoahGCHeuristics=adaptive` và các flags đúng version; không copy experimental flags cũ.
- [ ] Ghi lại region size/count từ **GC init log**, không hard-code một con số.
- [ ] Đo **heap occupancy/live set**, tổng allocations và **allocation rate** ở tải cao.
- [ ] Đo **mutator free**, **collector reserve** và điều kiện free-set theo log mà JVM cung cấp.
- [ ] Tìm pacing, allocation failures, Degenerated/Full GC và gắn timestamp với p99 spikes.
- [ ] Kiểm tra humongous objects/fragmentation khi có nhiều mảng/buffer lớn.
- [ ] Đánh giá `-Xmx` headroom cho collector và cả **native/container memory**.
- [ ] Benchmark với nhiều concurrency levels và **bursty allocations**, không chỉ steady throughput.
- [ ] Theo dõi các percentiles của **latency ứng dụng**, CPU, throughput, lỗi và RSS.
- [ ] Có log rotation/retention phù hợp, không bật debug/trace GC vô hạn.
- [ ] Trong unit test, không đòi số GC cycles hoặc pause time **cố định**; kiểm tra invariants thay vì snapshot log.
- [ ] Test tính reproducible của chương trình bằng Java 17+`javac --release 17`, so 6 stdout lines xác định.
- [ ] Có rollback plan nếu mức tiêu thụ CPU/RAM hoặc latency không đạt mục tiêu.

## 18. Tóm tắt: Region + reserve + rate phải được nhìn cùng một bức tranh

**Region** là đơn vị quản lý heap của Shenandoah. Các region được chọn vào **collection set**, object sống có thể được **evacuate**, sau đó không gian vùng nguồn có thể được thu hồi. Vì GC concurrent làm việc **song song với mutator allocations**, Shenandoah cần có **headroom** cho cả application và collector reserve.

**Allocation rate** thể hiện bao nhiêu byte object mới được tạo mỗi giây, **không phải** live set tăng bao nhiêu. Khi rate hoặc spike quá lớn so với thời gian collector cần để reclaim/evacuate, ứng dụng có thể gặp **pacing**, và nghiêm trọng hơn là **allocation failures / degenerated / full GC**. Muốn khắc phục, đo đúng live set, rate, region utilization, reserve và CPU headroom trước khi chỉnh flags.

Với **JDK 26**, các lệnh cốt lõi hiện hành là:

```bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -Xlog:gc*=info:file=shenandoah-gc.log:uptime,level,tags -cp . ShenandoahAllocationDemo
```

Trên **OpenJDK Zulu 24.0.2**, ví dụ trong bài đã biên dịch thành công bằng `javac --release 17` và chạy thành công với Shenandoah. Các dòng `Region Size=256K`, `Collector Reserve=13312K` và `Pacer` là **quan sát hữu ích của môi trường thử nghiệm**, không phải tham số cố định trong Java. Khi đổi JDK, heap, mode hoặc OS, phải kiểm tra lại **GC logs và runtime flags**.

### Tài liệu chính thức và nguồn hiện hành

- [Oracle Java SE 26 — `java` command: ShenandoahGCMode/Heuristics, UseShenandoahGC, Xlog](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): source ưu tiên để xác nhận mode `satb`, generational và heuristic `adaptive` ở JDK 26.
- [OpenJDK JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): dấu mốc production từ JDK 15.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): tính năng generational chuyển sang production ở JDK 25.
- [OpenJDK Shenandoah — GC project wiki](https://wiki.openjdk.org/display/shenandoah/Main): giải thích region, heuristics, pacing, evacuation reserve và failure modes; **nhiều phần của wiki thuộc đời implementation cũ**, cần đối chiếu với manual JDK đích trước khi sao chép flags.
- [OpenJDK HotSpot — Shenandoah source code (FreeSet)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shenandoah/shenandoahFreeSet.cpp): cơ chế phân vùng free-set cho mutator/collector trong implementation mới.
- [Oracle Java SE 26 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html), [`ManagementFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): API quan sát GC trong Java.
