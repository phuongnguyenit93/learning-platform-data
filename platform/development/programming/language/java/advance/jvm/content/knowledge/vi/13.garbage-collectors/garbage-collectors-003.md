# G1: heap chia vùng và lựa chọn tập vùng cần thu hồi

## 1. Vấn đề G1 muốn giải quyết

**Garbage-First Garbage Collector (G1 GC)** là một bộ thu gom rác trong HotSpot hướng tới cân bằng **throughput** và **pause-time goals** cho heap lớn hoặc workloads cần thời gian dừng dự đoán tốt. Thay vì coi heap là một vài dải vật lý lớn liên tiếp và mỗi lần chỉ chọn nguyên một dải, G1 **chia Java heap thành nhiều region có kích thước bằng nhau**. Các region có thể được gán vai trò Eden, Survivor, Old, Humongous hoặc Free, rồi được quản lý theo collection cycles.

Tên **Garbage-First** gợi ý ưu tiên: khi cần thu hồi Old, collector đánh giá **những region có hiệu quả reclaim cao** — nhiều memory có thể lấy lại so với chi phí phải xử lý — rồi chọn một **collection set (CSet)** phù hợp với mục tiêu pause time.

Bài này phân biệt:

1. **Heap regions** (đơn vị tổ chức/cấp phát/thu hồi) với **object** (đối tượng ứng dụng) và **Java generations** (vai trò quản lý Young/Old).
2. **Collection set (CSet)**: tập các source regions được chọn cho **evacuation/reclamation** trong một GC pause.
3. **Young-only collections** và **mixed collections**: khi nào CSet có Young, khi nào thêm Old candidates.
4. **Concurrent marking**, region liveness và cơ chế chọn **Old collection-set candidates** theo hiệu quả, liên kết tham chiếu và thời gian pause dự đoán.
5. **Remembered sets (RSets)** và **write barriers**: vì sao G1 có thể thu gom một số regions mà không cần quét lại toàn heap trong mỗi pause.
6. **Humongous regions**, evacuation failure, Full GC fallback, logging và các giới hạn khi đọc số region.
7. Ví dụ **Java 17+ chạy được**, có stdout xác định nhưng GC log/số region tùy thực tế.

**Giới hạn quan trọng:** G1 là một collector cụ thể của **HotSpot/OpenJDK**. JVMS `2.5.3 chỉ yêu cầu heap cho class instances/arrays và automatic storage management, không buộc mọi JVM phải dùng G1, region size hoặc CSet algorithm.

## 2. Heap regions: chia heap thành nhiều vùng bằng nhau

Oracle JDK 25 G1 guide mô tả heap được phân thành các **region có kích thước đồng đều**, mỗi region là một dải **virtual memory liên tục**. Các regions là đơn vị cơ sở mà G1 dùng để quản lý allocation/reclamation.

~~~text
Một heap minh họa được chia 12 regions bằng nhau:

+------+--------+--------+------+----------+-------+
| E    | Old    | Free   | S    | E        | Old   |
+------+--------+--------+------+----------+-------+
| E    | H-start| H-cont | Free | Survivor | Old   |
+------+--------+--------+------+----------+-------+

E      = Eden region
S      = Survivor region
Old    = Old region
H      = Humongous sequence (đối tượng rất lớn)
Free   = Region chưa được gán cho allocation hiện hành
~~~

Tất cả những ô đại diện **cùng một lượng địa chỉ virtual memory** ở mức region; trong sơ đồ text bề ngang ô không nhất thiết biểu diễn tỉ lệ chuẩn.

### Đặc điểm cần nhớ

- Một region có thể được gán vai trò **Eden**, **Survivor**, **Old**, **Humongous**, hoặc đang **free**, theo trạng thái collector.
- **Young generation** gồm **Eden và Survivor regions**; **Old generation** gồm các region Old và các phân loại đặc biệt phù hợp.
- Các Eden/Survivor/Old regions **không cần nằm liền kề** theo địa chỉ. G1 vẫn có thể coi những region rải rác là một young generation về mặt logic.
- **Region size bằng nhau trong một heap G1 cụ thể**; không có nghĩa mọi G1 process đều dùng một region size giống nhau.
- **Role của region không nhất thiết cố định suốt đời process**: sau khi được giải phóng, free region có thể được tái gán theo nhu cầu.
- Một region **không phải một object**: có thể chứa rất nhiều objects nhỏ, hoặc là một phần trong chuỗi Humongous.

### Kích thước region

HotSpot có tùy chọn `-XX:G1HeapRegionSize=...`. Oracle JDK 25 mô tả G1 chọn size theo ergonomics từ maximum heap, hướng tới khoảng **2.048 regions** trong điều kiện bình thường, và có ràng buộc kích thước hợp lệ phụ thuộc phiên bản. **Không học thuộc một con số region size như chân lý JVM.**

Ví dụ cấu hình:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC -Xlog:gc+init=info MyApplication
~~~

`MyApplication` là tên **mẫu**, phải thay bằng class ứng dụng thật. Logging khi khởi tạo có thể ghi **Heap Region Size** tùy version/tag. Để biết region size và các flags khả dụng, dùng `java -Xlog:help` và `java -XX:+PrintFlagsFinal -version` trên JVM đang chạy.

**Không tự đặt `G1HeapRegionSize` để “tăng tốc” nếu chưa kiểm tra** tác động tới số regions, remembered set granularity, waste, humongous threshold và pause behavior.

## 3. Region không phải generation và CSet không phải toàn heap

Ba khái niệm khác nhau:

| Khái niệm | Đơn vị/ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Region** | Một đơn vị heap memory kích thước đồng đều | Region số 17 |
| **Generation** | Nhóm logic các regions dựa trên vai trò/tuổi thọ | Eden + Survivor là Young |
| **Collection set (CSet)** | **Tập source regions** được G1 chọn cho một collection pause | Eden 10, Survivor 2, Old 3 trong mixed GC |

Một GC pause **không** có nghĩa toàn bộ Java heap nằm trong CSet. Đối với G1, **young-only CSet** tập trung young regions; còn **mixed CSet** chứa Young và một số Old regions được chọn.

~~~text
Heap hiện tại:
 [E1][E2][S1][O1][O2][O3][O4][FREE][FREE][H1]

Young-only CSet:  {E1, E2, S1}
Mixed CSet:       {E1, E2, S1, O2, O4}  (ví dụ minh họa)
Không trong CSet: O1, O3, H1, Free ...
~~~

**Tập trên là ví dụ giả định**, không phải quyết định cụ thể của G1. Các humongous regions có cách reclaim riêng và thường **không di chuyển như region thông thường**; đừng hiểu ký hiệu không nằm CSet là không bao giờ được GC thu hồi.

## 4. Evacuation: thu gom vùng được chọn bằng cách di chuyển object sống

Với những regions có thể evacuate, G1 dùng **copying/evacuation**: xác định **live objects** trong source regions, sao chép chúng tới các destination regions phù hợp, và cập nhật references cần thiết. Sau khi xử lý đúng, phần source regions có thể được giải phóng để tái sử dụng.

~~~text
Before G1 evacuation:

CSet source region R1
+-----------------------------------+
| A live | B dead | C live | D dead |
+-----------------------------------+

Destination region(s):
+-----------------------------------+
| A' live | C' live |    free ...   |
+-----------------------------------+

After references updated:
- References tới A chuyển tới A'
- References tới C chuyển tới C'
- R1 có thể trở thành free region
- B và D không cần sao chép
~~~

**Đây là sơ đồ lý thuyết.** Java program vẫn quan sát object identities đúng; GC có thể thay vị trí vật lý object mà không làm `a == b` hay hash/field semantics sai. Các memory barriers, forwarding metadata và cập nhật roots được HotSpot xử lý, không phải các phép gán phải tự viết trong source Java.

### Objects từ những nguồn khác nhau đi đâu?

Theo Oracle JDK 25 G1 guide:

- **Eden/Survivor live objects** có thể được đưa đến **Survivor hoặc Old**, phụ thuộc age/promotion policy.
- **Old live objects** được evacuate từ Old region sang **Old destination region**.
- **Humongous objects** có xử lý đặc thù; G1 thông thường không di chuyển chúng bằng evacuation như objects nhỏ, mà xác định khả năng sống và thu hồi khi không còn live theo cơ chế thích hợp.

**Evacuation không đồng nghĩa chỉ giữ lại object có field được đọc gần đây.** GC quyết định live theo reachability và runtime semantics, không dựa vào timestamps của application object.

## 5. Vì sao cần tập collection set?

Không thể lấy một old region bất kỳ và copy object trong đó mà bỏ qua những references trỏ tới nó từ thread stacks, static fields, code roots hoặc objects trong những regions khác. Collector phải có một tập nguồn được xác định cùng thông tin roots/references để bảo đảm toàn bộ object graph còn hợp lệ.

G1 dùng **CSet** để quyết định:

1. Những regions nào cần xem xét/reclaim trong collection hiện tại.
2. Những object nào còn live trong regions ấy.
3. Roots và **incoming references từ ngoài CSet** phải được cập nhật khi live objects di chuyển.
4. Thời gian pause dự đoán có vừa với pause target và các constraints collector hay không.
5. Khi nào nên dành thời gian cho additional **Old candidate regions** thay vì làm pause quá lâu.

Collection set giúp G1 thực hiện công việc **theo từng nhóm vùng**, thay vì thu gom toàn heap ở mọi lần pause.

### CSet là tập source regions, không phải nơi các object được copy tới

Trong source-oriented collection model:

~~~text
CSet (source):  E1, E2, S1, O3
                 |      |
                 v      v
Destination:    Survivor và Old regions mới/chỗ phù hợp

Kết quả: source regions thu hồi được (nếu evacuation thành công),
destination regions tiếp tục chứa objects còn sống.
~~~

**Đừng gọi destination region là “region nằm trong CSet cần thu” chỉ vì có object vừa mới được chuyển đến đó**. Trong tài liệu G1, CSet chỉ các source regions đang được chọn để evacuate/reclaim.

## 6. Thu gom Young trước: Young-only collection

Vì đa số objects mới có lifetime ngắn, G1 thường thực hiện **young-only GC pauses**. Young regions bao gồm Eden và Survivor thuộc current young generation.

Một đợt có thể diễn ra về mặt khái niệm:

1. Ứng dụng cấp phát object, dùng Eden regions/TLABs theo allocator.
2. Tài nguyên Eden gần đạt ngưỡng, VM bắt đầu một Young GC theo scheduling thích hợp.
3. G1 tạm dừng các application threads ở phase cần Stop-the-World.
4. Thu thập roots và **incoming references tới young collection set**.
5. Copy/evacuate live young objects sang Survivor hoặc Old theo age.
6. Giải phóng source Eden/Survivor regions tương ứng, cập nhật regions cho allocation tiếp.
7. Tiếp tục chương trình.

~~~text
Young collection:
  CSet = tất cả Young regions thích hợp cho lần thu gom đó

  Eden A      -> dead: reclaim, live: Survivor/Old
  Eden B      -> dead: reclaim, live: Survivor/Old
  Survivor C  -> live: Survivor/Old, dead: reclaim

  Old regions thông thường không ở trong CSet của young-only pause.
~~~

**Young-only GC không xóa mọi unreachable object ở Old.** Các region Old có thể chứa rác nhưng sẽ được reclaim trong những pha phù hợp. Vì vậy sau một young pause, heap/old occupancy không nhất thiết về mức thấp nhất.

### G1 điều chỉnh Young size theo mục tiêu pause

Kích thước Young (số Eden/Survivor regions) có thể được G1 **tự động điều chỉnh** dựa trên allocation rate, live bytes, chi phí evacuation và pause-time prediction. Điều đó tạo trade-off:

- Young lớn: thường giảm tần suất young GC, nhưng mỗi pause có thể cần xử lý nhiều live data.
- Young nhỏ: có thể pause ngắn hơn, nhưng thường cần GC thường xuyên hơn.
- Survivor pressure: nhiều live young có thể promotion sớm, khiến Old nhanh đầy.

Đừng ép Young size bằng các flags từ kinh nghiệm Java 8 nếu chưa biết collector/Java version hiện tại.

## 7. Từ Young-only sang Space-Reclamation/Mixed phase

G1 không chỉ thu dọn Young. Khi Old occupancy và tình trạng heap cho thấy cần lấy lại nhiều memory ở Old, G1 có thể bắt đầu **concurrent marking** để tìm những Old regions có live data ít và có thể reclaim hiệu quả.

Theo Oracle JDK 25 G1 guide, một chu trình lớn gồm:

~~~text
Young-Only Phase
  |
  +-- Các Young GC thường lệ
  |
  +-- Concurrent Start young collection
  |      bắt đầu concurrent marking
  |
  +-- Concurrent marking work (phần lớn khi app vẫn chạy)
  |
  +-- Remark pause (hoàn tất marking/reference processing)
  |
  +-- Cleanup pause (đánh giá candidate regions)
  |
  +-- Prepare Mixed young collection (khi phù hợp)
  v
Space-Reclamation Phase
  |
  +-- Mixed Collection 1: Young + một phần Old candidates
  +-- Mixed Collection 2: Young + thêm Old candidates
  +-- ...
  |
  +-- Kết thúc khi không còn candidates đủ hiệu quả hoặc policy dừng
  v
Quay lại Young-Only Phase
~~~

Sơ đồ là khái quát logic để học; số lượng/tên pauses phụ thuộc version và trạng thái VM. G1 có thể dùng Full GC fallback khi không đủ tiến độ thu hồi/không thể cấp phát theo các điều kiện cần thiết.

### Concurrent marking xác định thông tin gì?

- **Live data** trong các regions Old.
- Những regions có **nhiều reclaimable space** nếu evacuate.
- Thông tin reachability/connectivity cần cho đánh giá hiệu quả.
- Các candidates cho đợt mixed collections tiếp theo.

**Concurrent** không có nghĩa toàn bộ chu trình không có Stop-the-World pause. G1 vẫn có các **Remark, Cleanup và Evacuation pauses** cùng nhiều thành phần khác; concurrent marking chỉ nói một số pha làm việc song song khi ứng dụng chạy.

### Snapshot-at-the-Beginning (SATB)

Trong marking, G1 sử dụng kỹ thuật **SATB** để bảo vệ tính đúng của một snapshot logic về reachability. Những thay đổi references khi mutator chạy được ghi nhận nhờ barriers và collector processing phù hợp. Vì vậy không nên mô tả concurrent marking như một phép duyệt graph “đóng băng” không cần cập nhật.

**SATB marking và remembered-set maintenance có nhiệm vụ khác nhau**, dù đều liên quan GC barriers: một bên phục vụ marking snapshot, một bên giúp tìm incoming references/heap roots cho collection set.

## 8. Chọn Old regions: “Garbage-First” thực sự có nghĩa gì?

Đây là điểm cốt lõi của chủ đề: sau marking, G1 có dữ liệu để ước lượng **hiệu quả thu hồi** của những Old regions. Một region có nhiều bytes có thể reclaim và ít live data/cross-region work thường đáng chọn hơn region gần như đầy live objects.

G1 chọn **Old collection-set candidate regions** dựa trên lợi ích dự đoán, trong đó tính đến:

- **Reclaimable bytes/space**: lượng memory có thể lấy lại.
- **Live occupancy**: nhiều live bytes cần evacuate hơn thường làm tăng copy cost.
- **Connectivity/cross-region references**: nhiều incoming references có thể làm tăng remembered-set/heap-root processing.
- **Predicted pause time**: tổng công việc Young bắt buộc và Old candidates dự kiến có phù hợp mục tiêu pause.
- **Các heuristics tối thiểu/tùy chọn** để bảo đảm tiến độ và hạn chế chi phí.

Trong tài liệu Oracle JDK 25, các candidates có ít live data và ít kết nối được ưu tiên hơn candidates gần đầy hoặc chi phí scan cao. G1 không nhất thiết chọn **region có absolute garbage bytes nhiều nhất mà bỏ qua cost**.

### Ví dụ so sánh Old regions (giả định, không phải công thức HotSpot)

Giả sử mỗi region là 8 MiB:

| Old region | Live | Reclaimable | Chi phí evacuation dự đoán | Nhận định |
| --- | ---: | ---: | ---: | --- |
| A | 1 MiB | 7 MiB | 2 ms | Rất hứa hẹn |
| B | 6.5 MiB | 1.5 MiB | 8 ms | Ít hiệu quả |
| C | 2 MiB | 6 MiB | 3 ms | Hứa hẹn |
| D | 7.5 MiB | 0.5 MiB | 12 ms | Thường kém hấp dẫn |

Những số liệu này **do bài học đặt ra**, không phải dữ liệu G1 cụ thể, và chi phí thực tế không chỉ phụ thuộc live bytes. Hình dung: region A/C đem lại nhiều reclaimable bytes với chi phí thấp hơn B/D, nên thường phù hợp tinh thần garbage-first hơn.

**Không phải thuật toán là “sort một bảng theo garbage/live rồi lấy top K” đơn giản**. Oracle JDK 25 mô tả candidates có phân loại mandatory/optional, dự đoán pauses và policy space-reclamation phase; collector còn cân nhắc các giới hạn và số lượng cần xử lý mỗi lần.

## 9. CSet trong Mixed GC được xây dựng như thế nào?

**Mixed collection** là young collection **đồng thời thêm một số Old regions** đã được đánh giá là candidates.

~~~text
Young regions (bắt buộc theo young collection):
  E1 E2 E3 S1 S2

Old candidate regions sau concurrent marking:
  O7 O9 O14 O16 O21 ...

Ví dụ một Mixed CSet:
  {E1, E2, E3, S1, S2, O7, O14}

Các Old regions còn lại có thể để dành cho mixed pauses sau
hoặc không được chọn nếu cost/reclaim efficiency không đáng.
~~~

Các bước ở mức policy trong JDK 25:

1. **Chọn Young regions** theo young collection policy.
2. **Tính quỹ thời gian dự đoán còn lại** trong pause sau công việc Young và fixed/base costs.
3. **Chọn Old candidates tối thiểu (mandatory)** để bảo đảm tiến độ space reclamation, phân phối công việc dựa trên các cài đặt như `G1MixedGCCountTarget`.
4. **Thêm các Old candidates khác khi dự đoán vẫn còn thời gian**, có thể dùng **optional candidates** để khai thác khoảng còn lại.
5. **Dừng thêm** nếu dự đoán không còn khả năng phù hợp thời gian hoặc các tiêu chí hiệu quả/reclamation policy khác không cho phép.

Theo Oracle guide, G1 có cơ chế **initial pass** và những pass thêm cho **optional old regions** nếu còn thời gian pause dự kiến. Vì vậy CSet selection là một bài toán lợi ích/chi phí dưới pause budget, không phải một lệnh “GC toàn Old”.

### Mục tiêu pause là mục tiêu mềm

HotSpot có `-XX:MaxGCPauseMillis=...` để **đặt mục tiêu** cho G1. Đây **không phải deadline tuyệt đối** của mỗi GC pause. Một số tình huống như live-set tăng bất thường, many references, allocation pressure hoặc evacuation failure vẫn có thể khiến pause vượt mục tiêu.

Ví dụ:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 MyApplication
~~~

Lệnh là **mẫu**, không thể chạy nếu chưa có `MyApplication.class`. Giá trị `200` ở đây là target 200 ms, **không phải lời hứa “không bao giờ pause quá 200 ms”**.

## 10. Một bảng ví dụ chọn CSet theo pause budget

Hình dung G1 có pause target 40 ms, dự đoán Young work + fixed costs cần 20 ms; còn khoảng 20 ms cho Old candidates. Các số sau là **giả định thuần túy để học**, không phản ánh công thức/nội suy thật của G1:

| Candidate | Reclaimable memory | Cost ước tính |
| --- | ---: | ---: |
| Old A | 8 MiB | 7 ms |
| Old B | 3 MiB | 4 ms |
| Old C | 9 MiB | 13 ms |
| Old D | 0.5 MiB | 6 ms |

Một lựa chọn giả định là **A+B = 11 MiB reclaim với 11 ms**, có thể vẫn còn budget cho một số công việc khác; **A+C = 17 MiB với 20 ms** chạm giới hạn còn lại. Chọn tổ hợp nào còn phụ thuộc **mandatory candidates, connectivity, prediction uncertainty và policy**, không đơn giản là tối ưu một bài toán knapsack đúng số liệu này.

Bài học không yêu cầu bạn tự triển khai thuật toán chọn CSet y hệt HotSpot. Điều cần nhớ là G1 cố **tăng reclaim benefit trong quỹ pause dự đoán**, với nhiều tiêu chí thay vì chỉ xếp region theo số rác thô.

## 11. Remembered sets: tìm tham chiếu từ bên ngoài CSet

Giả sử G1 evacuate region R nhưng Old object ở region S không nằm trong CSet vẫn có field trỏ tới object X trong R:

~~~text
Region S (ngoài CSet)                 Region R (trong CSet)
+----------------------+              +----------------------+
| OtherObject          | -----------> | X (live object)      |
+----------------------+              +----------------------+

Evacuation:
  X được copy thành X' trong destination region.
  Reference ở S cần được cập nhật để trỏ tới X'.
~~~

Nếu collector không xem xét **incoming reference từ bên ngoài CSet**, nó có thể bỏ sót live object hoặc để lại reference không đúng sau moving GC. Quét toàn bộ heap trong mỗi partial collection thì mất ý nghĩa chọn một tập nhỏ regions.

**Remembered set (RSet)** lưu thông tin **vị trí từ bên ngoài có references trỏ vào CSet/regions**. Oracle JDK 25 mô tả RSet entries bằng **cards**, tức những vùng logic nhỏ của heap (mặc định thường 512 bytes theo phiên bản), thay vì một entry cho mọi pointer riêng lẻ.

### Granularity và trade-off

- Card-based representation giảm memory overhead.
- RSet entry cho vùng/card có thể là **xấp xỉ**, đòi kiểm tra references thực bên trong vùng.
- Gộp/bỏ trùng entries giúp giảm công việc root scanning.
- RSet cần được cập nhật hoặc xây dựng bằng barriers/refinement/rebuild theo phase.
- CSet càng lớn hoặc connectivity càng cao, công việc xử lý incoming references có thể tăng.

**RSets không phải Java `Set`, và không phải tập tất cả objects sống**. Đây là metadata nội bộ để hỗ trợ đúng đắn và hiệu quả của **partial region collection**.

### Merge Heap Roots

Oracle JDK 25 mô tả trong GC pause G1 có pha **Merge Heap Roots** để tạo một tập incoming heap roots thống nhất cho CSet từ remembered-set information, loại duplicates và chuẩn bị cho evacuation parallel work.

Một outline chu trình pause:

~~~text
Pre Evacuate Collection Set
    |
    v
Merge Heap Roots
    |
    v
Evacuate Collection Set
    |
    v
Post Evacuate Collection Set / Other work
    |
    v
Mutators tiếp tục chạy
~~~

Tên pha có thể thay đổi theo release/logger, nhưng chức năng chính không đổi: **chọn vùng**, **xác định roots/incoming references**, **copy live objects**, rồi **hoàn tất post-processing**.

## 12. Humongous objects: trường hợp ngoại lệ quan trọng

G1 gọi object rất lớn là **humongous** khi kích thước đạt ngưỡng theo region size (trong các G1 release thông thường, object lớn hơn **một nửa region size** đi vào đường humongous allocation).

Thay vì nằm giữa một Eden region thông thường, object humongous thường chiếm một hoặc nhiều **regions liên tiếp**:

~~~text
Region size giả định: 8 MiB

Object array kích thước khoảng 18 MiB:
+----------------+----------------+----------------+
| Humongous start| Humongous cont | Humongous cont |
|     object =====================================      |
+----------------+----------------+----------------+

Các regions này được gắn với chuỗi cấp phát object lớn.
~~~

**Dữ liệu 8/18 MiB là minh họa.** Object layout thực có header/alignment và cách GC tính kích thước; không dùng thông số giả định để khẳng định chính xác số vùng thực từ một array length.

### Vì sao humongous khác?

- G1 thường **không evacuate/move** humongous objects theo cách bình thường.
- Một object có thể giữ phần không dùng hết ở region cuối chuỗi cho tới khi object được reclaimed, dẫn tới internal fragmentation.
- Allocation humongous có thể đẩy nhanh nhu cầu concurrent marking hoặc GC tùy occupancy.
- Một số humongous objects, nhất là primitive arrays trong điều kiện hỗ trợ, có thể được **eagerly reclaimed** theo G1 policy.

**Không kết luận “humongous object bất tử”**, cũng không nói “mọi humongous object phải đợi Full GC”. Oracle hướng dẫn có các cơ chế reclamation ngoài Full GC tùy object và GC phase.

## 13. Evacuation failure và Full GC fallback

Một mixed/young collection dự kiến cần nơi để copy live objects. Nếu G1 không tìm được đủ destination space hoặc gặp tình huống collector-specific khác, **evacuation failure** có thể xảy ra.

Hệ quả có thể gồm:

- Không phải mọi source regions dự kiến đều được evacuate thành công.
- G1 phải dùng các cơ chế recovery/failure handling để bảo toàn object correctness.
- Có thể làm pause dài hơn, old regions tăng hoặc khiến G1 phải dùng cách thu gom nặng hơn.
- Trong tình huống nghiêm trọng, **Full GC** stop-the-world có thể được dùng như fallback để compact/recover memory.

**Không nói “mỗi evacuation failure = ngay lập tức OOME”**. OOME xảy ra khi VM không đáp ứng allocation yêu cầu sau những cơ chế hợp lệ; collector có thể recovery hoặc thu gom thêm.

### Vì sao cần reserve/to-space headroom?

Nếu CSet có nhiều live objects thì destination regions cần đủ chỗ. G1 có thể dành một phần headroom theo policy để giảm nguy cơ không thể evacuate trong pause. Khi tuning, old occupancy gần đầy, live-set rất lớn hoặc humongous allocations có thể làm vấn đề nghiêm trọng hơn.

Các flags về heap reserve/occupancy là **implementation tuning knobs**, không phải thứ phải chỉnh để giải thích nguyên lý chọn CSet; kiểm tra tài liệu version đang chạy trước khi thay đổi.

## 14. Chương trình Java 17+: tạo rác trẻ và giữ một số đối tượng

Bài thực hành không cố “ra lệnh” cho G1 chọn các region cụ thể — Java code **không có API chọn CSet**. Thay vào đó, nó tạo workload có temporary objects và một nhóm giữ sống, rồi quan sát GC log của HotSpot.

Tạo file **`G1RegionLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1RegionLab {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile Object latest;

    public static void main(String[] args) {
        for (int i = 0; i < 12; i++) {
            byte[] block = new byte[8192];
            block[0] = (byte) i;
            RETAINED.add(block);
        }

        int count = 0;
        for (int batch = 0; batch < 12; batch++) {
            for (int i = 0; i < 10_000; i++) {
                byte[] temporary = new byte[512];
                temporary[0] = (byte) i;
                latest = temporary;
                count++;
            }
        }

        latest = null;

        System.out.println("temporary-count=" + count);
        System.out.println("retained-count=" + RETAINED.size());
        System.out.println("retained-size=" + RETAINED.get(0).length);

        RETAINED.clear();
        System.out.println("after-clear=" + RETAINED.size());
        System.out.println("gc-regions-are-runtime-dependent");
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -g G1RegionLab.java
java G1RegionLab
~~~

**Stdout xác định nếu chương trình hoàn tất bình thường:**

~~~text
temporary-count=120000
retained-count=12
retained-size=8192
after-clear=0
gc-regions-are-runtime-dependent
~~~

**Giải thích:**

- `12 × 10_000 = 120_000` temporary arrays theo vòng lặp.
- `RETAINED` chứa 12 arrays, mỗi mảng 8192 bytes.
- `RETAINED.clear()` làm list rỗng, **không buộc garbage collector chạy ngay**.
- `latest` là volatile field giúp tạo đường tham chiếu có hiệu ứng quan sát trong execution, song không thể dùng output để xác nhận từng allocation path hay vị trí region cụ thể.
- Không có thread scheduling race trong stdout vì chỉ main thread in.
- Có thể có nhiều Young collections trong một lần chạy và khác nhau giữa các lần chạy, phụ thuộc heap/JVM/collector. **Không có số GC cố định cần xuất hiện.**

### Chạy với G1 và GC logging

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info G1RegionLab
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+heap=info G1RegionLab
~~~

Tổng temporary allocation theo mã có thể vượt 64 MiB qua thời gian, **không có nghĩa 64 MiB live objects cùng tồn tại**. Collector có thể reclaim phần không còn reachable để tiếp tục cấp phát. Nếu môi trường hạn chế hoặc JVM/OS khác biệt, dùng heap lớn hơn/thử workload nhỏ hơn trong test; **không cố ép OutOfMemoryError**.

**GC log không có stdout chính xác cố định.** Thời điểm GC, pause reason, số regions, timings và số bytes phụ thuộc trạng thái runtime. Chỉ năm dòng output của `G1RegionLab` là xác định khi hoàn tất bình thường.

## 15. Đọc G1 logs: cách nhìn region counts và CSet

HotSpot unified logging có các tag như `gc`, `gc+heap`, `gc+ergo+cset`. Dùng `java -Xlog:help` để kiểm tra tags/levels hỗ trợ.

~~~bash
java -Xlog:help
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info G1RegionLab
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+ergo+cset=debug G1RegionLab
~~~

### Mẫu logs về regions

Oracle JDK 25 docs đưa ví dụ log G1 có `Eden regions`, `Survivor regions`, `Old regions`. Một mẫu **giả định để giải thích**, không phải output chương trình này:

~~~text
[gc,heap] GC(12) Eden regions: 20->0(15)
[gc,heap] GC(12) Survivor regions: 2->4(5)
[gc,heap] GC(12) Old regions: 10->11
[gc]      GC(12) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

Đọc:

- `Eden regions: 20->0(15)`: số vùng Eden thay đổi qua GC cùng giá trị target liên quan. Không có nghĩa chỉ tạo 20 Java objects.
- `Survivor regions: 2->4(5)`: số regions vai trò Survivor thay đổi.
- `Old regions: 10->11`: số regions Old tăng một, **không phải một object** được promote.
- `Pause Young`: dọn Young; **không đồng nghĩa Full GC**.

Với workload nhỏ, bạn có thể **không gặp Mixed GC nào**. G1 chỉ bước vào space-reclamation/mixed phase khi marking và policy yêu cầu; đừng tạo một “expected mixed GC count” cố định cho file Java minh họa.

### CSet decision logs

Theo Oracle JDK 25 tuning guide, tag `gc+ergo+cset=debug` có thể cung cấp:

- Dự đoán **Young/Eden time** và **base time** trong pause.
- Thời gian dự đoán cho Old candidates **initial/optional**.
- Việc chọn số Old regions vào CSet trong mixed collections.

Ví dụ một mẫu hình thái dòng log (chỉ để minh họa cấu trúc, **không phải output dự đoán**):

~~~text
[gc,ergo,cset] Added young regions to CSet ... predicted eden time: ... target pause time: ...
[gc,ergo,cset] Finish choosing collection set old regions ... predicted initial time: ...
~~~

**Không tin rằng log đã liệt kê một object cụ thể được move**. `gc+ergo+cset` là collector ergonomics/decision logging ở mức region/CSet prediction; object-level movements không được trình bày đầy đủ bằng vài dòng này.

## 16. G1 pause goal, heap sizing và các flags đáng biết

| Flag (HotSpot) | Ý nghĩa tổng quan | Cảnh báo |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn G1 Collector | Chỉ dùng khi JVM hỗ trợ |
| `-XX:MaxGCPauseMillis=N` | Đặt **mục tiêu mềm** cho pause duration | Không bảo đảm mọi pause ≤N ms |
| `-XX:G1HeapRegionSize=...` | Chọn region size hợp lệ | Ảnh hưởng số regions, humongous threshold và overhead |
| `-XX:G1MixedGCCountTarget=...` | Ảnh hưởng mục tiêu phân phối old candidates qua nhiều mixed GCs | Không quy định chính xác số mixed pauses |
| `-XX:G1MixedGCLiveThresholdPercent=...` | Điều kiện về occupancy để xem xét old regions trong space-reclamation phase | Tăng/giảm có trade-off chi phí vs reclaim |
| `-XX:G1HeapWastePercent=...` | Policy để đánh giá còn đáng tiếp tục lấy lại Old space không | Không phải “tỷ lệ object leak” |
| `-XX:G1NewSizePercent`/`G1MaxNewSizePercent` | Giới hạn điều chỉnh Young theo policy | Không nên cố định nếu ergonomics hoạt động tốt |
| `-XX:+G1UseAdaptiveIHOP` | Adaptive initiating occupancy heuristic cho marking | Liên quan khi nào start marking, không chọn CSet trực tiếp |
| `-Xlog:gc+ergo+cset=debug` | Logging của việc G1 xây CSet | Nội dung phụ thuộc bản JDK/GC events |

**Không coi các giá trị mặc định là bất biến theo release.** Oracle JDK 25 docs có bảng flags cho đúng phiên bản; code HotSpot/JDK khác có thể khác. Kiểm tra thực tế bằng:

~~~bash
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

Một nguyên tắc: với G1, thông thường **bắt đầu bằng heap size, pause goal và workload measurements**; chỉ can thiệp các tuning flags tinh vi khi log cho thấy nguyên nhân. Tối ưu theo cảm tính dễ làm giảm throughput hoặc tăng pauses khác.

## 17. Khi Mixed GC quá chậm: nên điều tra ở đâu?

Oracle JDK 25 tuning guide khuyến nghị xem **predicted young time** so với **old-region contribution** trong `gc+ergo+cset=debug`:

1. **Nếu Young work chiếm chủ yếu**, cân nhắc Young sizing và survival rate; không đổ lỗi hết cho Old candidates.
2. **Nếu Old contribution lớn**, phân tích old region occupancy/connectivity và chiến lược trải công việc qua nhiều mixed collections.
3. **Nếu Merge Heap Roots/Scan Heap Roots tốn nhiều thời gian**, xem chi phí remembered sets/incoming cross-region references.
4. **Nếu Object Copy là phần lớn pause**, đo live bytes được evacuated, survivor/promotion pressure và collection-set size.
5. **Nếu humongous allocation nhiều**, xem kích thước arrays/objects và region-size trade-offs.
6. **Nếu Full GC xảy ra**, điều tra headroom/evacuation failure, Old live-set, allocation pattern và heap policy trước khi chỉnh flags.

**Giới hạn:** tuning để giảm pause có thể làm tăng tần suất pauses hoặc giảm throughput. Cần so sánh latency P95/P99, throughput, allocation rate, live-set và GC CPU theo workload nhất quán, không chỉ một pause ngắn.

## 18. Young-only, Mixed và Full GC: những ngộ nhận phổ biến

| Nhận định sai | Sửa lại |
| --- | --- |
| “G1 chia heap thành vùng với kích thước khác nhau theo generation.” | Regions **bằng nhau về size trong heap**, nhưng có roles khác nhau. |
| “Mọi Eden regions buộc phải liền nhau.” | G1 regions có thể rải rác. |
| “Mỗi region chứa đúng một Java object.” | Region thường chứa nhiều objects; humongous objects có thể chiếm nhiều regions. |
| “CSet là toàn heap.” | CSet là tập **source regions được chọn** cho GC pause hiện tại. |
| “Young-only CSet dọn mọi Old region.” | Không; Young-only xử lý young regions. |
| “Mixed GC chỉ thu Old, không thu Young.” | Mixed CSet gồm **Young + một số Old candidates**. |
| “Garbage-first nghĩa region có nhiều garbage bytes nhất luôn được chọn.” | Còn phải xét **live bytes, connectivity, efficiency, pause predictions và policy**. |
| “Tất cả Old regions được thu trong một Mixed GC.” | G1 chọn **subset** qua nhiều collections khi phù hợp. |
| “CSet selection không liên quan thời gian pause.” | G1 dùng pause-time predictions và mục tiêu mềm. |
| “`MaxGCPauseMillis=200` là deadline cứng.” | Là target, GC pauses vẫn có thể vượt. |
| “Concurrent marking nghĩa không có STW.” | G1 vẫn có Remark/Cleanup/Evacuation pauses. |
| “G1 không cần xem refs từ ngoài CSet.” | Phải dùng roots/RSet để bảo vệ live objects và cập nhật references. |
| “RSet là danh sách tất cả objects đang sống.” | Nó phục vụ **incoming reference locations**, không phải heap census. |
| “Region Old nhiều rác là chắc chắn đã reclaim ngay.” | Cần marking/candidate evaluation và collection thích hợp. |
| “Old regions: 10->11 nghĩa 1 object promotion.” | Logs đếm **regions**, không phải object count. |
| “Humongous objects luôn move như object nhỏ.” | G1 thường dùng xử lý/reclamation riêng, hạn chế move. |
| “Full GC diễn ra ở mọi mixed cycle.” | Là path khác/fallback, không phải default thường lệ. |
| “Ứng dụng Java gọi API để chọn CSet.” | CSet được HotSpot GC quyết định, không có Java API chuẩn cho việc này. |
| “GC log giống nhau trên Java 8, 17 và 25.” | Logging tags và G1 implementation thay đổi theo versions. |
| “Cứ giảm pause target là ứng dụng luôn nhanh hơn.” | Có trade-offs về throughput/frequency/overhead. |

## 19. Câu hỏi tự kiểm tra (có đáp án)

**1.** Một G1 heap region có thể giữ vai trò nào?  
**Đáp án:** Free, Eden, Survivor, Old hoặc special humongous role theo policy, và role có thể thay đổi khi region được thu hồi/tái gán.

**2.** CSet là tập gì?  
**Đáp án:** Tập **source regions** G1 chọn để xử lý/evacuate trong một collection pause; không phải toàn heap.

**3.** Young-only CSet thường có Old candidates không?  
**Đáp án:** Không theo chức năng young-only; G1 có thể làm các tác vụ concurrent/metadata ngoài evacuation như cần thiết, nhưng collection set young-only không phải mixed Old evacuation set.

**4.** Mixed CSet gồm những vùng nào?  
**Đáp án:** Young regions và một **subset Old candidates** được chọn theo policy.

**5.** G1 biết Old region nào đáng thu nhờ gì?  
**Đáp án:** Concurrent marking và metadata liveness/connectivity/reclaim efficiency; collector còn đánh giá predicted pause costs.

**6.** Nếu Object A trong region bị evacuate nhưng một object ngoài CSet trỏ tới A, có chuyện gì?  
**Đáp án:** G1 dùng roots/remembered-set information để tìm reference, giữ A live, copy nếu cần và cập nhật trỏ tới vị trí mới.

**7.** RSet là danh sách tất cả objects của region?  
**Đáp án:** Không. Nó ghi **incoming reference locations** phù hợp, thường theo cards.

**8.** Tại sao G1 không thu hết Old candidates trong một pause?  
**Đáp án:** Vì pause-time goal, prediction, reclaim-efficiency heuristics, mandatory/optional sets và policy phân chia công việc qua nhiều mixed collections.

**9.** Mỗi Old region có reclaimable space lớn nhất chắc luôn được chọn trước?  
**Đáp án:** Không. G1 xét nhiều yếu tố gồm chi phí copy/roots và liveness/connectivity.

**10.** `-XX:MaxGCPauseMillis=100` bảo đảm mọi GC dừng dưới 100 ms?  
**Đáp án:** Không; đây là mục tiêu mềm.

**11.** Một humongous object có luôn được evacuate như object nhỏ?  
**Đáp án:** Không. G1 dùng humongous allocation/reclamation riêng và hạn chế di chuyển.

**12.** Từ `Old regions: 10->11` có suy đúng một object được promote không?  
**Đáp án:** Không. Một region có nhiều objects, collector log không phải object-level count.

**13.** Một workload có `RETAINED.clear()` xong có buộc G1 GC tức thì không?  
**Đáp án:** Không. Mất reference không tạo deadline cho GC.

**14.** Dùng lệnh nào để nghiên cứu G1 CSet prediction trong HotSpot được hỗ trợ?  
**Đáp án:** Thử `-Xlog:gc+ergo+cset=debug` và kiểm tra `java -Xlog:help`; kết quả phụ thuộc có xảy ra mixed/young events tương ứng.

## 20. Nguồn tham khảo chính thức

- [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): heap layout/regions, young-only vs space-reclamation, CSet, RSets, humongous allocations, GC process và policy selection.
- [Oracle JDK 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): CSet candidate selection/pauses, tuning Young/Mixed/Old, `gc+ergo+cset` và G1 parameters.
- [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): ví dụ thống kê `Eden regions`, `Survivor regions`, `Old regions` trong GC logs.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis`, unified GC logging.
- [Oracle JDK 25 — Heap Sizing](https://docs.oracle.com/en/java/javase/25/gctuning/heap-sizing.html): các mục tiêu và cách VM điều chỉnh vùng heap.
- [JVMS Java SE 25 — 2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): vùng heap trừu tượng, không yêu cầu collector cụ thể.
- [OpenJDK JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248): bối cảnh G1 trở thành default trong HotSpot server configurations.
- [OpenJDK HotSpot G1 Sources](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/gc/g1): mã triển khai G1; nhánh master có thể khác phiên bản đang dùng.
- [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector](https://openjdk.org/jeps/318): nhắc rằng JVMS không bắt buộc cấu trúc GC generations như G1.

**Kết luận:** G1 chia heap thành **regions kích thước bằng nhau**, gán roles Young/Old/Humongous tùy trạng thái và **không yêu cầu regions cùng generation liền kề**. Trong một pause, **CSet xác định các source regions cần thu**, với **Young regions** trong young-only collections và thêm **một số Old candidates** trong mixed collections. “Garbage-first” nghĩa G1 cố tận dụng những vùng có **hiệu quả thu hồi cao** trong **quỹ pause dự đoán**, dựa vào concurrent marking, connectivity/remembered sets và collector ergonomics — không phải luôn quét cả heap hoặc chọn vùng đơn thuần theo dung lượng rác lớn nhất.