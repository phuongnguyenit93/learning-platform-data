# Chu kỳ G1: young collection, concurrent marking và mixed collection

## 1. Bức tranh tổng thể

**G1 (Garbage-First Garbage Collector)** là bộ thu gom rác kiểu **generational, region-based** của HotSpot JVM. G1 hướng đến cân bằng thông lượng với độ trễ, đặc biệt khi ứng dụng có heap tương đối lớn và cần kiểm soát thời gian tạm dừng (*pause time*) ở mức mục tiêu mềm.

Điểm dễ nhầm nhất: **young collection**, **concurrent marking** và **mixed collection** không phải ba bộ thu gom riêng biệt. Chúng là những **hoạt động và pha khác nhau trong vòng đời của cùng một G1 collector**.

Một chu kỳ khái quát trên HotSpot/JDK 17:

```text
YOUNG-ONLY PHASE
    |
    +--> Normal Young GC (STW, parallel evacuation)
    |           |
    |           +--> objects sống: survivor hoặc promoted to old
    |           +--> các lần young GC có thể lặp nhiều lần
    |
    +--> Old occupancy/IHOP đạt ngưỡng thích hợp
                |
                v
         Concurrent Start
         (young GC + initial-mark work trong STW)
                |
                v
         Concurrent marking cycle
           ├── root-region scan / marking (ứng dụng vẫn chạy)
           ├── có thể xen kẽ Normal Young GCs (STW)
           ├── Remark (STW)
           ├── preparation work / rebuild candidates (concurrent)
           └── Cleanup (STW)
                |
                +--> Có đủ old regions đáng thu hồi?
                      |
                 +----+----+
                 |         |
                Không      Có
                 |         |
                 v         v
           Young-only   Prepare Mixed young GC
                             |
                             v
                      SPACE-RECLAMATION PHASE
                         Mixed GC (STW):
                         young + selected old regions
                             |
                         có thể lặp
                             |
                             v
                         Young-only
```

**Lưu ý:** đây là **luồng điển hình**, không phải thứ tự mọi dòng log bắt buộc xuất hiện. G1 có thể không đi vào mixed collections nếu không đủ old regions đáng thu hồi; một concurrent cycle có thể bị hủy/undo theo điều kiện; áp lực heap bất thường có thể dẫn đến evacuation failure hoặc Full GC fallback.

Theo hướng dẫn Oracle JDK 17, G1 nhìn ở mức cao gồm hai giai đoạn lặp lại: **Young-Only** và **Space-Reclamation**. Concurrent marking là hoạt động chuẩn bị thông tin liveness để giai đoạn thu hồi old regions tiếp theo quyết định đối tượng nào còn sống, region nào nên chọn.

### Mục tiêu học tập

Sau bài này bạn cần:

1. Giải thích **Eden, Survivor, Old, Humongous regions**, region sizing và collection set.
2. Phân biệt **Young GC**, **Concurrent Start**, **concurrent mark**, **Remark**, **Cleanup**, **Prepare Mixed** và **Mixed GC**.
3. Hiểu vì sao G1 có **cả STW pauses lẫn concurrent work**, và vì sao marking không trực tiếp thu hồi toàn bộ old regions.
4. Hiểu **IHOP**, adaptive marking start, SATB, remembered sets, evacuation/promotion và pause predictions.
5. Đọc được log `Pause Young (Normal)`, `Concurrent Start`, `Concurrent Mark Cycle`, `Pause Remark`, `Pause Cleanup`, `Prepare Mixed`, `Pause Young (Mixed)` trong những bản HotSpot hỗ trợ.
6. Phân biệt normal behavior với **evacuation failure, Full GC, humongous pressure, allocation stalls**.
7. Thực hành bằng Java 17+ nhưng không biến lịch GC hoặc số lần GC thành một kết quả stdout cố định.

## 2. G1 phân vùng heap thành các regions

Không giống mô hình sơ đồ chia heap thành một dải Eden/Survivor/Old nằm cố định liên tiếp, G1 chia heap thành **regions có cùng kích thước**. Những regions này được gán **vai trò logic** theo thời gian.

```text
Heap G1 (sơ đồ các region bằng nhau)

+------+-------+------+-------+------+-------+------+
| Eden | Old   | Free | Eden  | Old  | Surv. | Free |
+------+-------+------+-------+------+-------+------+
| Old  | Eden  | Free | Hum.  | Hum. | Old   | Eden |
+------+-------+------+-------+------+-------+------+

Eden / Survivor / Old = trạng thái/vai trò của các regions,
không phải nhất thiết là các đoạn liên tiếp trong không gian địa chỉ.
```

Các loại region quan trọng:

| Region | Vai trò |
| --- | --- |
| **Eden** | Cấp phát phần lớn objects mới trong trường hợp thông thường |
| **Survivor** | Nhận những objects còn sống sau young evacuation mà chưa cần promote |
| **Old** | Giữ những objects có tuổi thọ dài hơn/promoted; ứng viên cho mixed collection khi phù hợp |
| **Free** | Chưa dùng, có thể được G1 cấp cho vai trò khác |
| **Humongous** | Giữ object rất lớn, sử dụng một hoặc nhiều regions liên tiếp và được xử lý đặc biệt |

### 2.1. Region size

Trên HotSpot JDK 17, kích thước region thường được chọn tự động sao cho số regions khoảng 2.048, với kích thước power-of-two trong khoảng **1–32 MiB** theo các cờ/ergonomics của phiên bản này.

Ví dụ điều chỉnh thử nghiệm:

```bash
java -XX:+UseG1GC -XX:G1HeapRegionSize=2m -jar application.jar
```

`application.jar` là **placeholder** cho ứng dụng thực. Cờ `G1HeapRegionSize` là tùy chọn HotSpot, không phải hợp đồng của Java; giá trị hợp lệ và heuristics có thể khác ở JDK mới.

**Đừng mặc định 1 region = 1 MiB** cho mọi Java process. Dựa vào GC logs hoặc `PrintFlagsFinal` của JVM thực.

### 2.2. Vai trò region có thể thay đổi

Region được coi là Eden ở một thời điểm có thể được thu hồi và trở thành Free, rồi về sau được dùng làm Old. G1 quản lý các nhóm region theo nhu cầu; ý tưởng “một object ở vùng Eden cố định từ đầu đến cuối đời” không chính xác.

### 2.3. G1 vẫn là generational

Phần lớn objects mới được cấp phát trong young generation; những objects sống đủ lâu có thể được **promote** sang old. Vì phần lớn objects thường chết trẻ, thu gom young regions nhiều lần có thể rất hiệu quả. Old regions được xử lý theo những bước khác do chi phí xác định liveness và di chuyển old objects thường lớn hơn.

## 3. Normal Young GC — thu gom thế hệ trẻ

**Young collection** thường xảy ra khi G1 cần thu hồi các Eden regions để tiếp tục cấp phát. Hoạt động này chủ yếu là **stop-the-world (STW) evacuation pause**: ứng dụng dừng, nhiều GC workers có thể chạy song song để copy các objects còn sống.

```text
Trước young GC:
  Eden:    [live A] [dead x] [live B] [dead y]
  Survivor:[live C]
  Old:     [live O1]

STW young evacuation:
  Live A, B, C --> Survivor hoặc Old destination regions
  Dead x, y   --> không được copy

Sau young GC:
  Old Eden regions được trả về trạng thái có thể tái sử dụng
  Các đối tượng sống vẫn reachable qua references đã được cập nhật
```

**Quan trọng:** G1 không bắt buộc “quét từng object rồi gọi destructor”. Đối tượng chết không cần được copy sang nơi mới; các source regions được lấy lại cho cấp phát khi quá trình collection hoàn tất.

### 3.1. Evacuation không phải chỉ xóa bộ nhớ

Để bảo toàn Java semantics, G1 phải:

- Nhận biết các references tới collection set.
- Xác định những objects còn sống phải được giữ.
- Copy live objects vào destination regions phù hợp.
- Cập nhật references theo quy tắc thuật toán.
- Đảm bảo các mutators tiếp tục thấy đúng objects sau pause.

Việc **evacuation/copying** cũng có tác dụng **compact** dữ liệu còn sống để lấy lại vùng trống.

### 3.2. Surviving và promotion

Một object sống qua young GC có thể được đưa vào survivor region; sau đủ tuổi hoặc trong điều kiện cụ thể, nó được **promote** sang old. Quyết định tùy age, tenuring distribution, survivor sizing và heap pressure, không phải quy luật “đúng N lần young GC là luôn lên old” cho mọi runtime.

### 3.3. Young GC vẫn xảy ra trong lúc concurrent marking

Marking thường nhằm chuẩn bị thu hồi old regions, nhưng ứng dụng vẫn tiếp tục cấp phát vào young. G1 có thể xen những **Normal Young GCs (STW)** trong thời gian concurrent marking chưa hoàn tất. Vì vậy không được nghĩ rằng “hễ G1 đang mark thì mọi young collection dừng lại cho tới cuối”.

### 3.4. Vì sao Young GC thường nhanh hơn thu gom toàn heap?

G1 xử lý một **collection set** được chọn, không buộc copy toàn bộ objects trong heap. G1 dùng các structures như **remembered sets** để theo dõi những references từ regions khác đi vào regions được thu gom, tránh phải quét mọi old object ở mỗi young pause.

Tuy nhiên young GC vẫn có thể dài nếu collection set lớn, số live objects cao, nhiều references cần xử lý, CPU hạn chế hoặc có những tình huống bất thường.

## 4. Collection Set (CSet) và remembered sets

**Collection Set — CSet** là tập **source regions** mà G1 dự định thu hồi trong một collection pause.

- Trong một **Normal Young GC**, CSet tập trung vào **young regions**; việc xử lý một số humongous objects có đường reclaim riêng tùy điều kiện.
- Trong **Mixed GC**, CSet có **young regions + một số old regions** được chọn từ danh sách ứng viên đã chuẩn bị sau marking.

Ví dụ:

```text
Normal Young CSet:
  {Eden-1, Eden-2, Survivor-3}

Mixed CSet:
  {Eden-4, Survivor-2, Old-7, Old-11}
```

Tên region và tập hợp trên chỉ minh họa. G1 quyết định thực tế theo heap state, prediction model và các giới hạn về pause.

### 4.1. Vì sao cần remembered sets?

Một old object có thể chứa field trỏ tới object trong young region:

```text
Old region R1       Young region R9
  [Service] --------> [Request]
```

Nếu young GC chỉ quét các references xuất phát từ young, nó có nguy cơ bỏ sót một object còn reachable từ old. G1 dùng các cơ chế theo dõi cross-region references, thường được giải thích bằng **remembered sets** và **card tables/write barriers**.

Nhờ remembered sets, G1 có thể xác định các incoming references quan trọng mà không phải quét toàn bộ old generation mỗi young collection.

### 4.2. Write barrier là gì?

Khi ứng dụng ghi một reference field, JIT/runtime có thể thực hiện thêm bookkeeping để phản ánh cập nhật đó vào hệ thống theo dõi GC. Đây là **write barrier** trong thuật toán của collector.

Một lệnh Java như:

```java
holder.child = newChild;
```

chỉ là minh họa trong một method với `holder`, `newChild` đã khai báo. Application programmer nhìn một phép gán reference; JVM có thể chạy thêm barrier code để quản lý remembered sets và concurrent marking.

**Không gộp mọi barrier thành một thứ:** G1 có các cơ chế khác nhau cho remembered set updates và SATB marking.

## 5. Khi nào G1 quyết định bắt đầu concurrent marking?

G1 không thu gom old regions bằng mixed collection chỉ vì ứng dụng vừa làm một young GC. Nó cần trước tiên đánh giá **liveness của old regions**, để biết những regions nào có nhiều rác đáng thu hồi.

Một dấu mốc quan trọng là **Initiating Heap Occupancy Threshold**, thường gọi **IHOP**.

### 5.1. IHOP không đơn giản là “45% toàn heap thì chắc chắn mark”

Trong hướng dẫn **Oracle JDK 17 G1**, G1 mặc định bật **Adaptive IHOP**. G1 thu thập dữ liệu về:

- Thời gian cần để hoàn tất một concurrent marking cycle.
- Tốc độ old generation occupancy tăng trong marking.
- Heap headroom/reserve và khả năng hoàn tất việc chuẩn bị old-reclamation trước khi thiếu chỗ.

Ban đầu, khi chưa đủ mẫu đo, cờ `InitiatingHeapOccupancyPercent` (giá trị khởi đầu thường 45) có thể được dùng như ngưỡng tính theo old generation theo cơ chế được mô tả. Sau đó G1 **điều chỉnh ngưỡng một cách thích nghi**.

```text
-XX:+G1UseAdaptiveIHOP
-XX:InitiatingHeapOccupancyPercent=45
```

Đây là **tùy chọn/giá trị minh họa cho HotSpot JDK 17**, không phải đề xuất luôn cố định 45%, và không nên diễn giải thành tỷ lệ của **mọi Java objects** trong toàn bộ heap ở mọi phiên bản.

Nếu tắt adaptive IHOP bằng `-XX:-G1UseAdaptiveIHOP`, cách dùng threshold trở nên cố định hơn theo giá trị cấu hình, nhưng rủi ro bắt đầu marking quá sớm/quá muộn cần được benchmark.

### 5.2. Tại sao bắt đầu sớm hay muộn quan trọng?

- **Bắt đầu quá muộn:** khi old occupancy tăng nhanh, marking chưa xong thì còn ít vùng trống để evacuation/promotion; dễ gặp pressure.
- **Bắt đầu quá sớm:** có thể tiêu tốn CPU cho concurrent work không cần thiết, giảm application throughput.
- **Adaptive IHOP:** cố gắng cân bằng việc bắt đầu đủ sớm dựa trên thời gian và tốc độ cấp phát đo được.

Hình dung:

```text
Old occupancy tăng ----------->
     mark start           mark complete        mixed reclaim
          |                    |                     |
          +--- concurrent -----+--- prepare ---------+

Nếu mark start quá sát mức heap đầy,
application có thể không còn đủ free regions để chờ kết thúc cycle.
```

Không có một threshold duy nhất tối ưu cho mọi workload hoặc mọi JDK.

## 6. Concurrent Start — bước giao giữa Young-Only và marking

Khi G1 nhận thấy đã đến thời điểm bắt đầu liveness analysis, nó có thể tổ chức một **Concurrent Start young collection**.

Đây là điểm học tập rất quan trọng:

> **Concurrent Start GC là một young GC pause (STW) thực hiện công việc mở đầu concurrent marking.** Từ “Concurrent” trong tên chỉ ra chu kỳ concurrent được kích hoạt, **không có nghĩa bản thân pause này chạy đồng thời với mutators**.

Một dòng log có thể mang tên:

```text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
```

hoặc tên cause khác phù hợp. Đây là **mẫu log minh họa**, không phải stdout hay lời hứa về event chắc chắn xuất hiện trong một chương trình nhỏ.

### 6.1. Initial-mark work

Concurrent Start thường được giải thích như một young evacuation kết hợp công việc **initial mark**. JVM thiết lập các trạng thái cần thiết để G1 bắt đầu truy vết old generation liveness sau đó.

Nếu chỉ thấy chữ `Pause Young (Concurrent Start)` trong log, không được suy ra rằng **old garbage đã được thu hồi** ngay tại pause ấy. Phần đánh dấu còn phải chạy, và mixed collection chỉ diễn ra khi có đủ thông tin/ứng viên phù hợp.

### 6.2. Một trigger đặc biệt: humongous allocation

Những objects rất lớn được G1 xử lý như **humongous objects**, có thể cấp phát trực tiếp vào old/humongous regions. G1 có thể kiểm tra IHOP khi cấp phát loại object này và khởi động concurrent cycle nếu điều kiện phù hợp.

Vì vậy log có thể cho thấy `G1 Humongous Allocation` làm cause của một young pause/concurrent start; không nên khẳng định mọi concurrent marking chỉ xuất phát từ một ordinary Eden allocation failure.

## 7. Root region scan và concurrent marking

Sau concurrent-start pause, G1 thực hiện một số hoạt động **đồng thời với application**, gồm quét các root regions cần thiết và concurrent marking.

### 7.1. Concurrent root-region scanning

Young survivor regions có thể chứa references tới old objects. Trong cơ chế của G1, việc quét survivor/root regions cần được phối hợp với young collection tiếp theo để duy trì liveness information chính xác.

Một sequence khái quát:

```text
Concurrent Start (STW)
      |
      v
Concurrent root region scan
      |
      v
Concurrent mark các reachable objects
      |
      v
Remark (STW)
```

**Không hiểu sơ đồ là “không có young GC xen giữa trong bất cứ đoạn nào”**; actual runtime scheduling và giới hạn giữa root region scan/young pause cần tuân theo thuật toán HotSpot.

### 7.2. Concurrent marking xác định điều gì?

Marking xác định các objects được coi là **live** theo invariant của thuật toán, đặc biệt phục vụ ước tính live bytes trong old regions. Sau marking, G1 biết những old regions nào có nhiều reclaimable space, và có thể quyết định tập ứng viên thu hồi.

**Marking không tự copy hoặc xóa hết old objects.** Một object “unmarked/dead” có thể vẫn nằm vật lý trong old region cho đến khi region được reclaim bằng cleanup hoặc evacuation theo cơ chế.

### 7.3. SATB — Snapshot-at-the-Beginning

G1 sử dụng một biến thể **snapshot-at-the-beginning (SATB)** cho concurrent marking. Trực giác:

1. G1 muốn duy trì một cách nhìn nhất quán về những reference có ý nghĩa tại đầu marking.
2. Mutators có thể đổi references trong khi GC đang chạy.
3. Write barriers ghi nhận những **giá trị reference cũ** bị overwrite ở những trường hợp cần theo dõi.
4. GC xử lý dữ liệu buffer/barrier tương ứng để không đánh mất liveness theo invariant snapshot.

Ví dụ minh họa:

```text
Trước mutation:
  A.child -> B

Mutator:
  A.child = C

SATB marking cần xử lý thông tin phù hợp về reference B
đã bị bỏ khỏi field trong lúc chu kỳ mark chạy.
```

**Không có nghĩa bất kỳ reference cũ nào cũng trở thành permanent GC root**, hoặc mọi write đều enqueue y hệt nhau. Đây là tóm tắt khái niệm; HotSpot tối ưu barrier và xử lý buffers theo trạng thái cụ thể.

### 7.4. Tại sao marking concurrent có CPU cost?

G1 phải truy vết data đồng thời với mutators, xử lý SATB buffers, remembered sets và việc thay đổi reference graph. Những CPU cycles này được dùng khi application còn chạy; do đó **latency do STW có thể tốt hơn nhưng throughput tổng có thể chịu chi phí**.

Không coi concurrent là “GC miễn phí”.

## 8. Remark — chốt thông tin marking trong STW

Khi phần concurrent marking chính gần hoàn tất, G1 thực hiện **Remark pause**. Đây là một **STW operation**.

Các hoạt động theo hướng dẫn G1 JDK 17 có thể gồm:

- Hoàn tất/chốt thông tin marking còn lại.
- Xử lý reference-processing toàn cục theo cơ chế JVM.
- Thực hiện class unloading theo điều kiện tương ứng.
- Reclaim một số regions đã trở thành hoàn toàn trống.
- Dọn/chuẩn bị một số internal data structures.

Một log minh họa:

```text
GC(17) Pause Remark 45M->45M(128M) 1.234ms
```

Các con số là **hoàn toàn minh họa**; thực tế JVM sẽ in occupancy, thời gian, tags và GC IDs khác nhau.

### 8.1. Remark có phải mixed collection không?

**Không.** Remark là bước hoàn tất đánh dấu và thực hiện xử lý liên quan, không phải một pause mixed evacuation thông thường của tập young + selected old regions.

Một số memory có thể được reclaim trong Remark/Cleanup đối với fully dead hoặc special regions, nhưng điều đó **không làm Remark trở thành một Mixed GC**.

### 8.2. Tại sao Remark cần STW?

Những bước hoàn tất/chốt nhất quán của concurrent marking và reference processing cần phối hợp ở những điểm mà VM quyết định dừng mutators. Dù marking đã chạy nhiều thời gian concurrently, quá trình vẫn có STW phases.

### 8.3. Remark kéo dài bất thường

Nếu `Pause Remark` lớn, điều tra reference processing, class unloading, số live references và workload liên quan. Không chỉ điều chỉnh `MaxGCPauseMillis` rồi kỳ vọng mọi remark sẽ giảm theo đúng tỷ lệ.

## 9. Cleanup — xác định có nên đi sang Space-Reclamation

Sau Remark, G1 tính toán/chuẩn bị những old-region candidates phù hợp; một số công việc được thực hiện concurrently. Sau đó có **Cleanup pause (STW)** để hoàn tất phần quyết định phục vụ thu hồi.

Sơ đồ:

```text
Concurrent marking
         |
         v
    Remark (STW)
         |
         +-- chuẩn bị/sắp xếp ứng viên thu hồi old regions
         |     (một số công việc có thể concurrent)
         v
    Cleanup (STW)
         |
         +--> mixed reclaim đủ lợi ích? --> Prepare Mixed
         |
         +--> không đáng thu hồi? -------> tiếp tục Young-Only
```

### 9.1. Vì sao không phải mọi marking cycle đều dẫn đến mixed collections?

Marking chỉ tạo **thông tin về liveness**. G1 còn phải đánh giá:

- Có bao nhiêu old regions đủ điều kiện làm candidates?
- Mỗi region còn bao nhiêu bytes sống, bao nhiêu reclaimable bytes?
- Chi phí evacuate live data so với lượng space lấy lại là bao nhiêu?
- Mục tiêu pause có cho phép thêm old regions vào CSet không?
- Heap đã có đủ free space hay chưa?

Nếu việc thu hồi thêm không đem lại lợi ích tương xứng, G1 có thể **không thực hiện pha mixed**.

### 9.2. Cleanup và fully empty regions

Một region được xác định **không có live objects** có thể được reclaim tương đối rẻ. Điều này khác với old region vẫn còn live objects, vì muốn reclaim old region có live data thường phải **evacuate** những objects sống sang nơi khác.

## 10. Prepare Mixed young collection

Nếu G1 quyết định cần thu hồi old regions, Oracle mô tả giai đoạn young-only kết thúc bằng một lần **Prepare Mixed young collection**.

Điểm dễ nhầm:

- **Prepare Mixed** là một **young collection** mang ý nghĩa chuyển tiếp/chuẩn bị trước space reclamation.
- **Mixed GC** mới là những collections có CSet bao gồm **young + selected old regions**.

Tên có thể thấy trên HotSpot logs là:

```text
Pause Young (Prepare Mixed)
```

Đây là tên event kiểu mẫu, không phải stdout cố định.

### 10.1. Tại sao không chuyển thẳng mọi old region vào một Full GC?

Mục tiêu G1 là **thu hồi old regions tăng dần** thay vì nhất thiết dừng toàn bộ ứng dụng để xử lý hết old gen một lần. Khi thu hồi một nhóm old regions cùng young collections, G1 có thể phân bố chi phí qua nhiều pauses dựa vào prediction model.

Một bước chuyển tiếp giúp chuẩn bị trạng thái collection set và sizing theo chiến lược G1 của JDK tương ứng.

## 11. Mixed GC — thu gom young cộng một số old regions

**Mixed GC** được gọi là *mixed* vì nó kết hợp:

- Các **young regions** trong CSet, và
- Một số **old regions** mà marking/cleanup cho thấy có khả năng thu hồi memory hiệu quả.

Sơ đồ:

```text
Heap trước:
  Young regions:  Y1, Y2, S1
  Old candidates: O3 (20% live), O7 (40% live), O9 (90% live)
  Old others:     O1, O2, ...

Mixed CSet minh họa:
  {Y1, Y2, S1, O3, O7}

STW mixed evacuation:
  - Copy live objects từ Y1,Y2,S1 theo quy tắc young
  - Copy live objects còn tồn tại từ O3,O7 sang old destinations
  - Cập nhật references, trả các source regions đã evacuate thành free

O9: chưa chắc được chọn vì ít rác/tốn nhiều copy hơn.
```

Phần trăm và lựa chọn trên **chỉ là ví dụ**, không là kết quả do G1 bắt buộc chọn trong mọi trường hợp.

### 11.1. Mixed không đồng nghĩa “thu gom toàn bộ old gen”

Một Mixed GC chỉ chọn **một phần old regions** làm candidates để giữ pause phù hợp. Old regions không được chọn tiếp tục tồn tại; sau này chúng có thể là ứng viên cho những chu kỳ khác.

### 11.2. Mixed evacuation là STW

Dù old candidates được chọn dựa trên **concurrent marking**, **việc evacuate các regions trong một mixed collection là STW** trên HotSpot G1 JDK 17. Nhiều GC workers có thể chạy **song song với nhau** trong pause, nhưng application mutators bị dừng.

Vì vậy:

```text
Concurrent marking (ứng dụng vẫn chạy)
            ≠
Mixed evacuation (ứng dụng bị dừng trong pause)
```

### 11.3. Tại sao copy live old objects?

G1 muốn lấy lại cả region để dùng tiếp. Nếu old region chứa cả live và dead objects, việc copy những live objects sang nơi khác cho phép thu hồi toàn bộ source region theo cách compacting.

Nếu region có **rất nhiều live bytes**, chi phí copy lớn nhưng phần reclaimable nhỏ. G1 do đó thường ưu tiên regions có nhiều rác hơn, dẫn đến tên **Garbage First**.

### 11.4. Mixed collections có thể lặp nhiều lần

Một space-reclamation phase thường gồm **nhiều Mixed GCs**. G1 đánh giá số old candidates còn lại, pause prediction và tỷ lệ reclaimable memory để quyết định nên tiếp tục hay dừng.

Không có guarantee rằng mọi marking cycle đi kèm đúng 8 mixed collections; `G1MixedGCCountTarget` là **mục tiêu/heuristic** chứ không phải vòng lặp fixed 8 lần.

## 12. Lựa chọn old candidates và kinh tế của collection set

Sau marking, G1 có ước lượng **live occupancy** của old regions. Những regions có **ít live bytes** thường hấp dẫn vì có nhiều không gian rác có thể lấy lại với ít công việc copy.

### 12.1. Ví dụ hiệu quả vùng

Giả sử region size 2 MiB:

| Old region | Live bytes | Reclaimable bytes (xấp xỉ) | Trực giác |
| --- | ---: | ---: | --- |
| A | 0.2 MiB | 1.8 MiB | Rất đáng chọn nếu pause model cho phép |
| B | 0.8 MiB | 1.2 MiB | Đáng cân nhắc |
| C | 1.9 MiB | 0.1 MiB | Ít lợi ích, chi phí copy cao |

Bảng này là **ví dụ số học**, giả định vùng old không có những yếu tố accounting/representation đặc biệt và chỉ minh họa live/reclaimable ratio. Actual candidate selection còn có cost model, remembered sets và limits khác.

### 12.2. `G1MixedGCLiveThresholdPercent`

Trên HotSpot JDK 17, cờ này là một trong các ngưỡng xét **old region đủ điều kiện mixed collection** dựa trên occupancy. Ví dụ giá trị mặc định được tài liệu JDK 17 nêu là **85%**.

Không nên kết luận mọi old region có đúng 84% live chắc chắn vào CSet ngay. Nó còn phải đi qua candidate filtering, pause prediction và các giới hạn khác.

### 12.3. `G1MixedGCCountTarget`

Cờ này ảnh hưởng **mục tiêu số mixed pauses** dùng để xử lý các candidates sau marking. Tài liệu JDK 17 nêu mặc định thường là **8**.

Đặt một số nhỏ hơn có thể yêu cầu thu hồi nhiều old regions trong mỗi pause; điều đó có khả năng tăng pause cost. Nhưng kết quả thực còn phụ thuộc heap/candidates và policy.

### 12.4. `G1HeapWastePercent`

G1 có thể quyết định dừng space-reclamation nếu lượng reclaimable garbage còn lại trong candidates nhỏ hơn mức được coi là đáng xử lý so với heap. Tài liệu JDK 17 nêu mặc định **5%**.

Không hiểu “G1 cho phép 5% garbage toàn JVM rồi chắc chắn dừng GC”; đây là **ngưỡng/heuristic trong quyết định mixed candidate space reclamation**.

### 12.5. Pause prediction

G1 có một mô hình ước lượng thời gian xử lý young và optional old regions để chọn CSet phù hợp mục tiêu pause.

Cờ thường dùng:

```text
-XX:MaxGCPauseMillis=200
```

Đây là **pause goal mềm**; G1 không hứa mọi Young/Mixed/Remark/Cleanup pause sẽ luôn nhỏ hơn 200 ms. Overhead, live bytes, remembered-set processing, CPU throttling và bất thường có thể làm pause vượt mục tiêu.

## 13. Young-only và Space-Reclamation: timeline phân biệt STW/concurrent

Một timeline học tập đầy đủ:

```text
T0           T1            T2             T3              T4          T5
|------------|-------------|--------------|---------------|-----------|---->

Application:
RUN       [STW] RUN    [STW] RUN       [STW] RUN       [STW] RUN  [STW]

G1:
Normal Young    Concurrent Start       Remark        Cleanup   Mixed #1
     ^          + initial mark             ^             ^        ^
     |               |                     |             |        |
  evacuate            +--- concurrent marking ---+        |      young+old
  young                           |                        |
                       normal young STW can interleave    Prepare Mixed
                                                        may precede Mixed
```

Sơ đồ là **mô hình logic**, không căn đúng thời gian và không liệt kê mọi pause. Thực tế có thể thấy **nhiều Normal Young GCs**, một hoặc nhiều mixed collections và các tác vụ concurrent work giữa các pauses.

Điều quan trọng khi đọc log:

- **Concurrent Mark Cycle**: có thể kéo dài theo wall-clock nhưng mutators vẫn chạy phần lớn thời gian.
- **Pause Young**: ứng dụng dừng trong khoảng pause dù GC work parallel.
- **Pause Remark / Cleanup**: có những STW pauses, nhưng marking work chính đã concurrent.
- **Pause Young (Mixed)**: young + selected old evacuation trong STW.

## 14. Humongous objects: lối đi riêng và tác động chu kỳ

G1 phân loại objects có kích thước **lớn hơn hoặc bằng một nửa region** là **humongous** trong mô hình HotSpot JDK 17.

Ví dụ nếu region size là 2 MiB, object có tổng kích thước khoảng từ 1 MiB trở lên có thể được coi là humongous, tùy accounting của header/array allocation.

### 14.1. Vì sao humongous objects đáng chú ý?

- Chúng thường được cấp phát trực tiếp vào **humongous old regions**.
- Một humongous object lớn có thể chiếm **nhiều contiguous regions**.
- Phần dư của region cuối có thể không dùng được cho allocation thông thường khi object vẫn còn.
- Việc cấp phát humongous objects có thể gây áp lực old occupancy và kích hoạt **Concurrent Start** sớm.
- G1 có quy tắc reclaim đặc biệt; một số humongous objects chết có thể được reclaim sớm trong young GC theo cơ chế eager reclaim.

### 14.2. Không giả định humongous luôn được di chuyển trong mixed

Trong mô tả HotSpot JDK 17, G1 **không di chuyển humongous objects** như việc evacuate ordinary young/old regions. Nó có thể reclaim vùng khi object không còn live theo đường phù hợp, với eager reclaim hoặc cleanup/Full GC paths theo khả năng VM.

Do đó, một chương trình tạo nhiều large arrays có thể có GC behavior rất khác so với hàng triệu objects nhỏ, kể cả tổng số byte tương tự.

### 14.3. Log cause

Ví dụ nhãn thường gặp:

```text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
```

Nếu thấy nhãn này, điều tra **kích thước allocations và region size** trước khi suy đoán G1 đang “chạy hỗn hợp” hay “collector bị lỗi”.

## 15. Khi nào một G1 cycle không đi qua mọi bước?

Các biểu đồ giáo trình thường vẽ đầy đủ **Young → Mark → Mixed → Young**, nhưng thực tế:

1. Ứng dụng có thể chỉ cần các young collections; old occupancy không đến ngưỡng kích hoạt mark.
2. Một concurrent start có thể bị **undo** khi VM nhận thấy không cần marking tiếp theo, tùy phiên bản/cấu hình.
3. Sau marking/cleanup, không có old candidates đủ lợi ích → **không vào mixed phase**.
4. Phần lớn vùng đã được reclaimed trong những bước xử lý đặc biệt/fully dead → mixed work ít hoặc không có.
5. **Allocation pressure** quá cao có thể làm marking và planned mixed reclamation không theo kịp, dẫn đến evacuation failure hoặc Full GC.
6. `System.gc()` hoặc JVM-specific triggers có thể tạo hành vi thu gom khác với vòng thường gặp.

**Không biến sơ đồ logic thành assertion “ứng dụng phải in đủ tất cả tên phase sau mỗi N allocations”.** Thuật toán là adaptive, dựa vào heap, data survival, JVM/JDK version và môi trường.

## 16. Evacuation failure và Full GC fallback

### 16.1. To-space pressure

Evacuation cần **free destination regions** để copy live objects. Nếu heap có quá nhiều live objects hoặc free headroom không đủ, G1 có thể không có chỗ cho một số objects khi evacuate.

Vấn đề có thể được mô tả là **evacuation failure**, hoặc trên một số bản HotSpot/logs lịch sử là `to-space exhausted`.

```text
CSet có nhiều live objects
           |
           v
Cần to-space để copy
           |
      đủ free regions?
        /         \
      có          không
      |             |
      v             v
  evacuate     evacuation failure handling,
  bình thường  có thể tăng GC overhead;
               nếu pressure tiếp tục -> Full GC/OOME
```

Điều này không chứng minh bytecode Java sai, mà thể hiện **capacity/GC headroom** không đủ cho trạng thái heap/workload tại thời điểm đó.

### 16.2. Full GC là đường dự phòng

Khi G1 không thể giải quyết pressure theo các bước thông thường, HotSpot có thể sử dụng **Full GC STW** để compact heap ở mức rộng hơn. Đây là đường fallback, không phải phần mixed collection “bắt buộc” của mọi chu kỳ.

**Full GC trên G1 không phải Mixed GC lớn hơn một chút**. Nó có mục tiêu và phạm vi khác, thường có rủi ro pause dài hơn.

### 16.3. Điều tra nguyên nhân

Khi logs cho thấy evacuation failure/Full GC/OOME:

- Xem live-set size và số old/humongous regions.
- Đo allocation/promotion rate.
- Kiểm tra heap headroom, `-Xmx`, container limit.
- Kiểm tra marking bắt đầu quá muộn hay concurrent work không theo kịp.
- Xem large arrays/humongous allocation.
- Tìm object retention/leaks, caches không bounded.
- Đọc pause/cause details theo phiên bản HotSpot thực tế.

**Tăng heap** có thể hợp lý khi workload cần dung lượng, nhưng **không sửa retention leak hoặc data structures không giới hạn**.

## 17. Đọc GC logs theo đúng pha

HotSpot JDK 17 sử dụng **Unified Logging**, ví dụ:

```bash
java -XX:+UseG1GC -Xlog:gc*=info -jar application.jar
```

Trong JAR ở đây, `application.jar` chỉ là placeholder. Chương trình runnable bên dưới sử dụng class file thay vì JAR.

### 17.1. Mẫu log khái niệm

```text
[info][gc] GC(1) Pause Young (Normal) (G1 Evacuation Pause) ...
[info][gc] GC(2) Pause Young (Concurrent Start) (G1 Evacuation Pause) ...
[info][gc] GC(3) Concurrent Mark Cycle
[info][gc] GC(3) Concurrent Scan Root Regions ...
[info][gc] GC(3) Concurrent Mark ...
[info][gc] GC(3) Pause Remark ...
[info][gc] GC(3) Pause Cleanup ...
[info][gc] GC(4) Pause Young (Prepare Mixed) ...
[info][gc] GC(5) Pause Young (Mixed) (G1 Evacuation Pause) ...
```

**Đây là mẫu tự viết để nhận diện từ khóa, KHÔNG PHẢI output thu được từ một lần chạy**. Trong HotSpot thật, GC IDs, timestamps, thứ tự tag lines và format phase có thể khác; các concurrent-phase logs và các young pauses có thể xen kẽ, không nhất thiết có đủ chín dòng trên.

### 17.2. Những câu hỏi nên đặt từ từng dòng

| Dòng/log pattern | Câu hỏi chẩn đoán |
| --- | --- |
| `Pause Young (Normal)` | Young CSet lớn không? Pause duration/evacuation cost ra sao? |
| `Pause Young (Concurrent Start)` | Marking cycle được khởi động do threshold/causes nào? |
| `Concurrent Scan Root Regions` | Root-region scanning mất bao lâu? |
| `Concurrent Mark` | GC marking workers có theo kịp mutators không? |
| `Pause Remark` | Finalization marking/reference processing/class unloading có tốn thời gian không? |
| `Pause Cleanup` | Old candidates còn đáng reclaim không? |
| `Pause Young (Prepare Mixed)` | G1 đang chuyển sang space reclamation? |
| `Pause Young (Mixed)` | Bao nhiêu old regions được chọn, được reclaim bao nhiêu? |
| `Pause Full` | Vì sao đường GC thông thường không đủ? |

Để xem memory theo regions, có thể bật các tags/levels phù hợp tùy HotSpot/JDK; trước tiên kiểm tra bằng:

```bash
java -Xlog:help
```

### 17.3. Đừng cộng nhầm concurrent time vào STW pause

Một log `Concurrent Mark Cycle 400ms` **không đồng nghĩa application bị dừng 400ms**. Phần lớn hoạt động có thể xảy ra khi mutators vẫn chạy.

Ngược lại, một `Pause Young (Mixed) 70ms` là pause cụ thể có thể góp phần vào request latency. Cần phân tích **STW pause distribution** và **application latency p95/p99**, không chỉ tổng GC cycle duration.

## 18. Ví dụ Java 17+ hoàn chỉnh: tạo áp lực GC, giữ một phần objects

Bài demo tạo nhiều byte arrays, giữ lại một số arrays để chúng vẫn reachable, đồng thời để phần lớn arrays trở thành ứng viên thu hồi. Nó giúp quan sát **Normal Young GCs** và, tùy heap/collector heuristics, những concurrent/mixed phases.

Tạo tệp **`G1CycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class G1CycleDemo {
    private static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 768; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;
            block[block.length - 1] = (byte) i;

            checksum += Byte.toUnsignedInt(block[0]);
            latest = block;

            if (i % 32 == 0) {
                survivors.add(block);
            }
        }

        long survivorSum = 0;
        for (byte[] block : survivors) {
            survivorSum += Byte.toUnsignedInt(block[0]);
        }

        System.out.println("iterations=" + 768);
        System.out.println("checksum=" + checksum);
        System.out.println("survivor arrays=" + survivors.size());
        System.out.println("survivor sample sum=" + survivorSum);
    }
}
```

### 18.1. Biên dịch và chạy

Cần **JDK 17+**; ví dụ đã được biên dịch bằng `javac --release 17` và chạy thành công trên một OpenJDK có hỗ trợ G1/Parallel.

```bash
javac --release 17 G1CycleDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC G1CycleDemo
```

**Stdout chính xác của riêng ứng dụng khi chạy bình thường:**

```text
iterations=768
checksum=97920
survivor arrays=24
survivor sample sum=2688
```

Giải thích toán học:

- Vòng lặp có 768 iterations, tức ba lần đi qua các giá trị `0..255` sau phép `& 0xff`.
- `checksum = 3 × (0 + 1 + ... + 255) = 97920`.
- Những `i` chia hết cho 32 nằm trong `0..767` là 24 giá trị.
- Mỗi nhóm `0,32,64,96,128,160,192,224` có tổng 896; lặp ba lần → `survivorSum = 2688`.

### 18.2. Vì sao dùng `volatile latest`?

Bản demo gán mỗi `block` vào một static volatile field `latest`. Điều đó tạo một thao tác có side effect phù hợp, làm workload không chỉ là các allocations mà JIT có thể dễ dàng nhận thấy “không quan sát được” rồi loại đi theo một số tối ưu. Các blocks cũ vẫn có thể trở thành garbage khi bị thay; chỉ những blocks đang được giữ trong list hoặc `latest` mới có các strong references rõ ràng từ đoạn code.

**Không khẳng định `volatile` đảm bảo mọi block sẽ đi qua old generation**. Những chính sách collector và JIT vẫn có quyền tối ưu những điều không ảnh hưởng Java semantics.

### 18.3. Tại sao không assert “phải có đúng một Mixed GC”?

Dù program tạo tổng khoảng 192 MiB byte-array payload trong nhiều vòng cấp phát, heap 64 MiB và một số survivors, G1 có thể chọn các đường thu gom khác nhau tùy:

- JDK version, heap region size, IHOP history.
- CPU speed và tốc độ vòng lặp.
- Allocation rate và lượng live data.
- Có bao nhiêu old regions đã hình thành.
- Concurrent marking có kịp hoàn tất không.
- Heuristics/humongous thresholds và GC logging configuration.

**G1 không cam kết xuất hiện mixed GC trong chương trình này.** Bài demo phục vụ quan sát, không ép phase bằng một assumption sai.

## 19. Thực hành đọc log G1 và so sánh với Parallel GC

### 19.1. Chạy G1 với GC logs

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info G1CycleDemo
```

Quan sát:

- Startup có cho biết `Using G1` không?
- Có bao nhiêu `Pause Young (Normal)`?
- Có xuất hiện `Concurrent Start` hay không?
- Nếu xuất hiện, có `Remark` và `Cleanup` sau đó không?
- Nếu có `Mixed`, old regions được reclaim trong pause nào?
- Có `Full GC` hoặc `Evacuation Failure` không?

**GC log output không cố định** theo workload/timing, nên không có “stdout chính xác” cho các dòng runtime. Chỉ bốn dòng `G1CycleDemo` in ra là deterministic.

### 19.2. Chạy Parallel GC cùng workload

```bash
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info G1CycleDemo
```

Parallel GC có cách tổ chức phases khác G1. Nó chủ yếu thực hiện collection work bằng nhiều GC workers trong STW pauses, không cùng chu kỳ Young-Only → Concurrent Mark → Mixed của G1.

Mục tiêu so sánh:

- Application checksum **giống nhau**, chứng minh GC không thay Java program semantics.
- Collector events/logs **khác nhau**.
- Pause distributions, CPU, throughput có thể khác.

**Đừng gán nhãn “Parallel GC = Mixed G1”** chỉ vì cả hai cùng có nhiều GC worker threads.

### 19.3. So sánh qua nhiều runs

Một benchmark đáng tin cần warm-up, cố định heap, CPU quota và JDK build, ghi nhiều runs. Một lần chạy không đủ chứng minh collector nào nhanh hơn cho mọi trường hợp.

Với bài học này, điều quan trọng là **đọc đúng các pha của G1**, không dùng microbenchmark quá ngắn để kết luận production GC choice.

## 20. Cách xem chi tiết G1 bằng các tùy chọn HotSpot

Một số cờ phù hợp với JDK 17:

```text
-XX:+UseG1GC
-XX:MaxGCPauseMillis=200
-XX:G1HeapRegionSize=2m
-XX:InitiatingHeapOccupancyPercent=45
-XX:+G1UseAdaptiveIHOP
-XX:G1MixedGCCountTarget=8
-XX:G1HeapWastePercent=5
-XX:G1ReservePercent=10
-XX:ParallelGCThreads=<n>
-XX:ConcGCThreads=<n>
```

**Không ghép tất cả các flag thành “bộ tối ưu mặc định”.** Bảng trên là danh sách tham khảo; một vài flag có thể cần kiểm tra tính khả dụng/quy tắc ở từng build. `<n>` là placeholder chứ không phải số hợp lệ để copy nguyên văn.

### 20.1. Đặc tính các cờ

| Flag | Hướng tác động | Rủi ro nếu sửa mù |
| --- | --- | --- |
| `MaxGCPauseMillis` | Mục tiêu dự báo pause của G1 | Đặt quá thấp có thể tăng số GC và CPU overhead |
| `G1HeapRegionSize` | Kích thước regions | Thay đổi humongous threshold, overhead/cardinality |
| `InitiatingHeapOccupancyPercent` | Giá trị mốc khởi phát marking, đặc biệt lúc chưa đủ samples | Cấu hình không phù hợp có thể dẫn tới start quá sớm/muộn |
| `G1UseAdaptiveIHOP` | G1 tự thích nghi thời điểm khởi phát mark | Tắt khi chưa hiểu workload làm mất tuning tự động |
| `G1MixedGCCountTarget` | Mục tiêu số mixed collections/cycle | Ít phases hơn có thể cần thu hồi nhiều old regions mỗi pause |
| `G1HeapWastePercent` | Ngưỡng lợi ích còn lại để tiếp tục old reclamation | Có thể làm quá nhiều/ít mixed work |
| `G1ReservePercent` | Reserve/headroom giúp tránh thiếu destination space | Giữ reserve quá nhiều có thể giảm effective heap capacity |
| `ParallelGCThreads` | Số workers trong parallel GC pauses | Nhiều threads hơn không bảo đảm pause giảm theo tỷ lệ |
| `ConcGCThreads` | Workers cho concurrent work | Quá nhiều lấy CPU của application; quá ít có thể mark không kịp |

### 20.2. Quy trình tuning an toàn

1. Bắt đầu từ HotSpot G1 defaults nếu chưa có bằng chứng cần sửa.
2. Thu GC logs/JFR và thông số ứng dụng thực.
3. Xem vấn đề nằm ở **young STW**, **mixed STW**, **remark/cleanup**, hay **marking không theo kịp**.
4. Đo allocation rate, live set, promotion, old occupancy, humongous objects.
5. Chỉ thay một nhóm ít flag có giả thuyết rõ, so sánh trước/sau.
6. Kiểm tra request latency và throughput, không chỉ pause goal.
7. Giữ cùng workload và resource limits; tránh thay nhiều biến cùng lúc.

## 21. Những sai lầm thường gặp khi học chu kỳ G1

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “G1 chia heap thành Eden/Survivor/Old là ba vùng địa chỉ cố định.” | G1 dùng các regions có cùng size, gán vai trò logic có thể thay đổi. |
| “Normal Young GC thu gom cả old regions.” | Normal young collection chủ yếu evacuate young CSet; old regions được đưa vào selected mixed CSet ở pha khác. |
| “Concurrent Start pause chạy concurrent với application.” | Đó là **STW young pause** khởi động concurrent marking. |
| “Concurrent marking là copy old objects sang vùng khác.” | Marking đo liveness; việc evacuate selected old regions xảy ra trong mixed pauses. |
| “G1 không có STW vì có concurrent mark.” | Young/mixed/remark/cleanup có STW pauses. |
| “Remark và Cleanup đều là Mixed GC.” | Chúng là những bước riêng của marking/transition. |
| “Mỗi marking cycle đều phải có mixed GC.” | Không; tùy ứng viên old regions, reclaimable space và policy. |
| “Mixed thu gom toàn bộ old generation.” | Mixed chỉ thêm **một phần selected old regions** vào CSet. |
| “Mixed GC diễn ra concurrently với mutators.” | Việc evacuate CSet trong mixed là **STW** của G1 JDK 17. |
| “G1MixedGCCountTarget=8 nghĩa bắt buộc 8 mixed collections.” | Đó là mục tiêu/heuristic, không số lần cố định. |
| “IHOP luôn là 45% toàn heap ở mọi JDK.” | JDK 17 có Adaptive IHOP và tính ngưỡng theo old-gen occupancy model. |
| “G1HeapWastePercent 5 nghĩa luôn để đúng 5% objects chết.” | Đó là policy threshold cho lợi ích old reclamation, không một bất biến heap. |
| “Một region 90% live chắc chắn sẽ được chọn vào mixed.” | High live occupancy có thể làm region không đủ điều kiện hoặc tốn công hơn lợi ích. |
| “Mỗi Young GC nhất định promote đúng một tỷ lệ object.” | Promotion phụ thuộc tuổi, survivor sizing và heap state. |
| “Humongous objects được evacuate như arrays nhỏ.” | G1 xử lý humongous đặc biệt, thường không di chuyển như ordinary evacuated regions. |
| “Một GC cycle elapsed 1 giây là ứng dụng dừng 1 giây.” | Concurrent phase elapsed time khác STW pause. |
| “`MaxGCPauseMillis` là SLA cứng.” | Là pause goal mềm, không guarantee. |
| “G1 sẽ không bao giờ Full GC.” | Full GC fallback có thể xảy ra trong memory pressure. |
| “Bật nhiều GC workers luôn giúp nhanh.” | CPU, overhead, memory bandwidth và cgroup quota giới hạn hiệu quả. |
| “GC logs của hai JVM phải có cùng event count.” | GC ergonomics/timings không được Java Specification cố định. |

## 22. Bài tập tự kiểm tra có đáp án

**Câu 1.** G1 làm gì trong một Normal Young GC?

**Đáp án:** Evacuate live objects từ young collection set trong STW pause bằng GC workers, đưa survivors/promotion tới destination regions và reclaim source young regions.

**Câu 2.** Young GC có bắt buộc concurrent với application vì dùng nhiều GC workers không?

**Đáp án:** Không. Nhiều workers có thể chạy parallel trong **STW**, còn mutators bị dừng.

**Câu 3.** Concurrent Start có nghĩa old regions được mixed-evacuate ngay chưa?

**Đáp án:** Chưa. Đó là một young pause có initial-mark work, khởi động concurrent marking để xác định old liveness trước khi chọn candidates.

**Câu 4.** Concurrent marking chạy cùng mutators thì G1 dựa vào cơ chế nào để xử lý reference updates?

**Đáp án:** Một họ cơ chế có SATB marking/write barriers và các cấu trúc metadata, theo thuật toán cụ thể của G1.

**Câu 5.** Remark là STW hay concurrent?

**Đáp án:** Remark là một **STW pause** dùng hoàn tất việc marking và những hoạt động xử lý liên quan.

**Câu 6.** Cleanup có luôn dẫn tới Mixed GC không?

**Đáp án:** Không. G1 có thể kết luận không đủ reclaimable old regions đáng thu hồi, do đó quay lại young-only.

**Câu 7.** Prepare Mixed khác Mixed GC thế nào?

**Đáp án:** Prepare Mixed là young collection chuyển tiếp khi G1 sắp vào space-reclamation phase; Mixed GC thực sự có young + selected old regions trong CSet.

**Câu 8.** Tại sao G1 ưu tiên old regions ít live bytes?

**Đáp án:** Vì chúng có nhiều reclaimable garbage tương đối với chi phí copy live data, nên thường hiệu quả hơn để reclaim.

**Câu 9.** Mixed evacuation có chạy concurrent với mutators trên HotSpot G1 JDK 17 không?

**Đáp án:** Không. Nó là **STW evacuation pause**, dù nhiều GC workers có thể chạy parallel.

**Câu 10.** Vì sao marking không tự reclaim mọi old regions?

**Đáp án:** Marking xác định liveness/candidates. Old regions còn live objects cần thu hồi bằng cách di chuyển live data trong các bước eviction/evacuation phù hợp.

**Câu 11.** `G1MixedGCCountTarget=8` có cam kết đúng tám Mixed GCs mỗi chu kỳ không?

**Đáp án:** Không. Đây là mục tiêu policy; số thực phụ thuộc candidates, pause predictions và heap state.

**Câu 12.** Vì sao ứng dụng còn chạy lúc concurrent mark nhưng vẫn có thể xuất hiện young STW pauses?

**Đáp án:** Young allocations tiếp tục diễn ra; young collections có thể xen kẽ trong khi concurrent marking chưa hoàn tất.

**Câu 13.** G1 dùng remembered sets để làm gì?

**Đáp án:** Theo dõi cross-region references cần thiết, giúp collect selected regions mà không phải quét toàn bộ heap mỗi lần.

**Câu 14.** Nếu một object lớn hơn nửa region, G1 gọi nó là gì?

**Đáp án:** *Humongous object* (trên HotSpot G1 JDK 17, ngưỡng lớn hơn hoặc bằng nửa region), với allocation/reclamation đặc biệt.

**Câu 15.** Evacuation failure có thể dẫn đến hiện tượng gì?

**Đáp án:** G1 không có đủ destination space để copy một số live objects; collector xử lý failure, có thể tăng GC cost, và nếu memory pressure kéo dài có thể dẫn tới Full GC/OOME.

**Câu 16.** Một dòng `Concurrent Mark Cycle 500ms` có thể coi là pause 500ms không?

**Đáp án:** Không. Cần tách elapsed time của concurrent work khỏi STW pauses riêng.

**Câu 17.** Vì sao ví dụ Java cùng checksum nhưng GC logs khác giữa các lần chạy?

**Đáp án:** Java semantics bắt buộc kết quả logic phù hợp, còn heuristics/timing/số GC events phụ thuộc collector và môi trường.

**Câu 18.** Khi nào có thể bắt đầu mixed collections mà không có concurrent marking thông thường trước?

**Đáp án:** Trong đường G1 thông thường của JDK 17, old candidates phục vụ mixed cần thông tin liveness chuẩn bị bởi concurrent cycle; các đường GC đặc biệt/fallback khác **không nên gọi nhầm là mixed phase bình thường**.

**Câu 19.** Nếu G1 Full GC xuất hiện thường xuyên, bước đầu nên kiểm tra gì?

**Đáp án:** Heap pressure, live-set size, humongous allocations, marking start, promotion/evacuation headroom và leaks trước khi chỉ đổi một flag ngẫu nhiên.

**Câu 20.** Vì sao giảm `MaxGCPauseMillis` quá thấp có thể giảm throughput?

**Đáp án:** Mục tiêu pause quá chặt có thể khiến G1 tổ chức những collections nhỏ/nhiều hơn và tăng GC overhead; cần đo workload thật.

## 23. Checklist đọc chu kỳ G1 trên hệ thống thực

1. Xác nhận runtime thật sự dùng G1 qua startup logs/flags.
2. Ghi lại JDK build, `-Xms`, `-Xmx`, CPU quota, region size.
3. Phân loại GC events thành **Normal Young**, **Concurrent Start**, **Remark**, **Cleanup**, **Prepare Mixed** và **Mixed**.
4. Phân biệt **STW pause duration** với **concurrent phase elapsed time**.
5. Theo dõi old occupancy/IHOP và thời điểm bắt đầu marking.
6. Kiểm tra những young pauses xen giữa concurrent marking.
7. Xem candidate old regions và lượng memory reclaimed ở mixed phase.
8. Theo dõi pause p95/p99/max lẫn application request latency p99.
9. Kiểm tra CPU usage của concurrent GC workers và mutators.
10. Xem số live bytes, survivor/promotion, to-space headroom.
11. Tìm humongous allocations nếu có long pauses hoặc early marking.
12. Điều tra evacuation failure và Full GC fallback thay vì coi chúng là normal mixed steps.
13. Không khẳng định mixed phải xuất hiện trong mỗi lần chạy chương trình.
14. Ghi rõ các cờ tùy chỉnh; nếu không có nhu cầu, dùng ergonomic defaults trước.
15. Khi benchmark, cố định workload, heap/JDK, CPU limits và lặp nhiều runs.

### Tóm tắt và sơ đồ nhớ nhanh

```text
NORMAL YOUNG GC      : STW; evacuate young; có thể promote sang old
CONCURRENT START     : Young STW pause khởi động marking
CONCURRENT MARKING   : đánh dấu old liveness với mutators còn chạy
REMARK               : STW; hoàn tất marking, reference/class processing
CLEANUP              : STW; đánh giá và hoàn tất candidates old regions
PREPARE MIXED        : Young GC chuyển tiếp, nếu chuẩn bị vào mixed phase
MIXED GC             : STW; evacuate young + selected old regions
BACK TO YOUNG-ONLY   : hoàn tất old reclamation đáng làm

CẢNH BÁO:
- Không phải mỗi cycle có đầy đủ mọi event.
- G1 có cả parallel STW workers và concurrent marking workers.
- Mixed GC không phải Full GC và không xử lý mọi old region.
```

**Thông điệp cốt lõi:** G1 thu gom young regions thường xuyên, đánh dấu old liveness phần lớn **đồng thời với ứng dụng**, rồi nếu có lợi ích sẽ đưa **một phần old regions** vào các **STW mixed evacuations**. Hiểu đúng sự chuyển pha này giúp đọc GC logs, lý giải thời gian pause và chọn hướng tuning mà không đánh đồng marking với reclamation.

### Tài liệu chính thức

- [Oracle JDK 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): Young-Only, Concurrent Start, Remark, Cleanup, Prepare Mixed và Space-Reclamation phases.
- [Oracle JDK 17 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector-tuning.html): pause goals, log analysis và common performance issues.
- [Oracle JDK 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): HotSpot GC options và Unified Logging.
- [Oracle JDK 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): lựa chọn Serial, Parallel, G1, ZGC theo workload.
- [OpenJDK JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): G1 là default server-class GC trong các cấu hình HotSpot phù hợp từ JDK 9.
- [OpenJDK JEP 156 — G1 GC: Reduce contention in remembered set maintenance](https://openjdk.org/jeps/156): góc nhìn engineering về remembered sets.
- [JVMS 2.5.3 — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): JVM quy định automatic storage management nhưng không bắt buộc collector cụ thể.
