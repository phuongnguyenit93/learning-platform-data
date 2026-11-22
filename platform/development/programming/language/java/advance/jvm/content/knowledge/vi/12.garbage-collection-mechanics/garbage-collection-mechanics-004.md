# Eden, Survivor và Old trong mô hình bộ thu gom rác theo thế hệ của JVM

Trong Java, phần lớn đối tượng được tạo ra, sử dụng trong thời gian ngắn rồi không còn được tham chiếu. Nhưng cũng có những đối tượng sống hàng phút hoặc hàng giờ: cache, connection pool, dữ liệu phiên, các cấu trúc nghiệp vụ lớn. **Generational garbage collection** tận dụng sự khác biệt về vòng đời này để thu gom hiệu quả: ưu tiên quét/thu hồi những đối tượng mới tạo thường chết sớm, và quản lý riêng những đối tượng đã sống qua nhiều lần thu gom.

Ở cách giải thích kinh điển, **young generation** gồm **Eden** và các **Survivor spaces**; **old generation** chứa những đối tượng đã tồn tại lâu hơn hoặc được cấp phát vào old theo chính sách collector. Từ đó có ba câu hỏi trọng tâm:

1. Đối tượng mới thường được tạo ở đâu và điều gì xảy ra khi Eden không còn đủ chỗ?
2. Khi còn sống sau Young GC, đối tượng chuyển tới Survivor hay Old? **Age**, **tenuring** và **promotion** khác gì nhau?
3. Vì sao **Eden/Survivor/Old trong HotSpot G1 Java 17 là vai trò của các regions**, không đơn giản là ba dải bộ nhớ cố định như nhiều sơ đồ cũ?

Bài học tập trung vào mô hình thế hệ và ứng dụng của nó trong **HotSpot G1 trên Java 17**, đồng thời chỉ rõ phần nào thuộc khái niệm chung, phần nào là implementation detail. Có sơ đồ, timeline, Java 17 chạy được, hướng dẫn GC logging, các sai lầm thường gặp và bài tập.

## 1. Tại sao cần thu gom theo thế hệ?

Một quan sát thực nghiệm thường gọi là **weak generational hypothesis**: nhiều object được tạo chỉ tồn tại rất ngắn, và nhiều object đã tồn tại lâu có xu hướng tiếp tục tồn tại. Đây là **xu hướng workload**, không phải quy luật “mọi object trẻ đều chết” hay “mọi object già đều bất tử”.

Ví dụ trong một web service:

| Object | Vòng đời thường gặp | Hệ quả cho GC |
| --- | --- | --- |
| `StringBuilder` tạm trong xử lý request | Một vài method calls | Có thể chết nhanh, đáng thu gom ở young |
| DTO giải mã JSON chỉ dùng trong một request | Từ vài ms đến vài giây | Có thể được thu gom sau khi response hoàn tất |
| Bản ghi cache có TTL | Nhiều requests | Có thể sống qua các lần Young GC |
| Map chứa trạng thái ứng dụng lâu dài | Phút/giờ hoặc suốt runtime | Thường vẫn reachable trong old |
| Object dùng trong bootstrap rồi bỏ | Dài/ngắn tùy ứng dụng | Không thể suy tuổi chỉ từ nơi source khởi tạo |

Thay vì mỗi lần bộ thu gom đều xử lý **toàn bộ heap** bất kể tỷ lệ sống, generational collector có thể xử lý **young** thường xuyên. Nó tìm những object trẻ còn reachable, chuyển/copy các object sống sang khu vực thích hợp và tái sử dụng phần lớn dung lượng Eden chứa object đã chết.

Đây là mô hình tối ưu, **không thay thế reachability analysis**. Một object “già” nhưng không còn reference vẫn là garbage, và một object mới nhưng được giữ bởi static field vẫn là live.

### 1.1. Object chết vì mất reachability, không phải vì “đến tuổi”

Một object chỉ được xem là có thể thu hồi khi không còn reachable từ những GC roots/đường tham chiếu mà collector phải xét. GC không xóa object chỉ vì nó đã “ở Eden đủ ba giây”.

- **Age** thường được dùng để quyết định **nơi giữ object còn sống** sau một lần young evacuation.
- **Reachability** dùng để quyết định **object còn sống hay là garbage**.
- **Wall-clock age** (số giây kể từ `new`) không phải trường `age` mà generational GC dựa vào khi tenuring.

Hai object tạo cùng thời điểm có thể được đối xử khác nhau nếu một object được giữ trong list lâu dài, còn object kia không còn reference.

## 2. Ba vai trò: Eden, Survivor, Old

| Vùng | Vai trò | Điều xảy ra thường thấy |
| --- | --- | --- |
| **Eden** | Nơi các object nhỏ mới tạo được cấp phát | Young GC thu gom Eden; object chết được bỏ, object sống được evacuate |
| **Survivor** | Giữ những object còn sống sau young collection nhưng chưa phải old | Object có thể tiếp tục sống qua nhiều young collections và tăng tuổi |
| **Old** | Giữ đối tượng đã được promoted, đối tượng được cấp phát đặc biệt vào old và một số object sống lâu | Old được đánh dấu/thu hồi qua những chu kỳ collection phù hợp; không phải vùng “GC không bao giờ đụng” |

Mô hình dễ nhớ:

```text
                     YOUNG GENERATION
            ┌──────────────────────────────┐
new objects │          EDEN                │
    ───────►│  allocation, many die young  │
            └────────────┬─────────────────┘
                         │ Young GC / evacuation
                  ┌──────┴──────────┐
             unreachable        reachable
                  │                  │
                  ▼                  ▼
              discard         SURVIVOR  (age tăng)
                                     │
                              còn trẻ / đủ chỗ
                                     │ tiếp tục Young GC
                                     ▼
                                  SURVIVOR
                                     │
                     đủ tuổi hoặc cần promote theo policy
                                     ▼
                            OLD GENERATION
                          (vẫn chịu GC khi cần)
```

Đây là **sơ đồ hành vi khái niệm**, không phải một bảo đảm đối tượng luôn tuần tự đi đúng `Eden → Survivor 1 → Survivor 2 → Old`. Có trường hợp đối tượng được promoted sớm hoặc vào old theo đường cấp phát đặc biệt.

### 2.1. Có phải mọi object Java đều cấp phát vào Eden?

**Không.** “Thông thường object được tạo trong Eden” là quy tắc mô hình, không phải hợp đồng áp dụng cho mọi collector và mọi allocation. Với HotSpot G1, đối tượng **humongous** được cấp phát trực tiếp vào các **old/humongous regions**. Ngoài ra, JIT có thể **scalar-replace** một số allocations nếu chứng minh object không escape; khi ấy source có `new` nhưng không nhất thiết có một heap object độc lập cần GC.

Không suy nơi cấp phát từ việc thấy từ khóa `new` trong Java source. Cần kiểm tra GC implementation, kích thước object, escape analysis và hoạt động runtime.

## 3. Eden: vùng tạo object và áp lực cấp phát

Nhiều allocations của Java threads trong HotSpot được tối ưu bằng **TLAB — Thread-Local Allocation Buffer**. Mỗi thread được cấp một buffer cấp phát nhỏ trong không gian young/eden phù hợp. Khi còn đủ chỗ, cấp phát object thường chỉ cần tăng một con trỏ, tránh phải khóa toàn bộ heap cho từng allocation.

```text
Heap young / Eden capacity
    ├─ TLAB của thread A: allocations nhanh của A
    ├─ TLAB của thread B: allocations nhanh của B
    └─ không gian bổ sung / slow-path allocations

Khi TLAB hết:
    thread thử refill/new TLAB hoặc allocation slow path;
    nếu không đủ vùng young thích hợp, JVM có thể cần GC.
```

**TLAB không phải một thế hệ GC riêng**, mà là cơ chế **tối ưu allocation**. Một object cấp phát vào TLAB không có “GC riêng cho thread A”. Các đối tượng vẫn thuộc các vùng của heap và được quản lý theo collector.

### 3.1. Eden đầy không đồng nghĩa toàn bộ heap hết bộ nhớ

Khi Eden/young allocation space bị tiêu thụ, collector có thể làm một **Young GC** để thu hồi rác trẻ và tạo thêm khả năng cấp phát. Nếu vẫn còn nhiều vùng old trống hoặc heap còn dư, việc Young GC xảy ra là bình thường, **không phải tự nó là memory leak hay OutOfMemoryError**.

Nếu application tạo nhiều object ngắn hạn, số lần Young GC có thể tăng. Điều cần đo là allocation rate, live set, pause times, throughput, old occupancy và SLA, không chỉ đếm số GC.

### 3.2. Có phải Eden cứ đạt đúng 100% là GC lập tức xảy ra?

Không nên suy một ngưỡng cố định. Young generation size có thể được collector điều chỉnh, TLAB refill và các allocation paths có chi phí/điều kiện khác nhau. G1 còn dùng **adaptive sizing** với mục tiêu pause time và capacity. Công thức “Eden 100% → một loại sự kiện duy nhất” chỉ hữu ích ở sơ đồ nhập môn, không phải một state machine tuyệt đối cho mọi tình huống HotSpot.

## 4. Survivor spaces: lưu object sống qua Young GC

Một Young GC cần phân biệt:

1. Object trong Eden/Survivor không còn reachable: thu hồi cùng source regions.
2. Object vẫn reachable nhưng chưa cần promoted: **copy/evacuate** sang Survivor regions mới.
3. Object vẫn reachable và đủ tuổi hoặc không phù hợp giữ trong survivor set: **promote** sang old regions theo policy.

Trong collector copying truyền thống, sách thường vẽ **Survivor S0 và S1** hay **From/To**: một vùng đóng vai trò nguồn, vùng kia nhận những object được copy; sau collection, vai trò hoán đổi.

```text
MÔ HÌNH HAI SURVIVOR SPACES (minh họa kinh điển)
Trước Young GC:
     Eden:     [A live][B dead][C live]
     From S0:  [D live][E dead]
     To S1:    [trống]

Young GC:
     A, C, D → To S1 nếu còn đủ điều kiện
     B, E    → garbage; không được copy
     Một số object sống đủ già → Old

Sau Young GC:
     From S0/Eden cũ được tái sử dụng
     S1 đóng vai trò survivor nguồn cho chu kỳ sau
```

**Cẩn thận với G1:** mô hình `S0/S1` giúp hiểu copying, nhưng G1 dùng **một tập survivor heap regions thay đổi theo từng collection**, không bắt buộc là đúng hai “khối không gian Survivor cố định” nằm kề nhau. Trên G1, tập young regions gồm Eden regions và Survivor regions; collector evacuate object sống vào những **new survivor regions** hoặc **old regions**.

### 4.1. Survivor chứa object sống, không chứa “object sắp chết”

Một object có thể ở Survivor vì nó **vẫn live** sau một đợt young collection. Không phải JVM biết trước object đó còn sống thêm bao lâu. Nếu không còn reachable trước collection kế tiếp, object sẽ không được copy nữa và dung lượng vùng chứa nó được thu hồi.

### 4.2. Survivor có cần hai vùng bằng nhau?

Không có quy tắc bắt buộc xuyên mọi collector. Ở sơ đồ copying đời cũ, From/To survivor spaces có thể được cấu hình theo tỷ lệ nhất định; với G1, số **regions** được dùng cho Eden và Survivor được điều chỉnh theo collector heuristics. Tuning flags như `SurvivorRatio`, `NewRatio` trong các tài liệu collectors khác **không nên áp dụng máy móc vào G1** như thể nó duy trì hai fixed semispaces giống nhau.

## 5. Age, tenuring threshold và promotion vào Old

Một object vừa tạo không có “đồng hồ Java” đo bao nhiêu giây để được chuyển vào Old. Generational collector thường theo dõi **tuổi sống sót qua young evacuations**.

Timeline lý tưởng:

```text
time t0: tạo Object X → Eden
young GC #1: X live → Survivor, tuổi tăng
young GC #2: X live → Survivor mới, tuổi tăng
young GC #3: X live → có thể promote vào Old
... nếu X trở nên unreachable, Old GC sẽ thu hồi về sau ...
```

Dòng “#3” ở sơ đồ là **giả định để học**, không phải giá trị threshold cố định của Java 17. G1 quyết định threshold và điểm đích tùy adaptive policy, survivor capacity, tuổi và các ràng buộc GC.

### 5.1. Tenuring threshold là gì?

**Tenuring** mô tả việc một object sống qua đủ young collections/đạt điều kiện để không ở survivor nữa. **Tenuring threshold** là ngưỡng tuổi mà collector dùng để quyết định promotion trong điều kiện phù hợp.

- **Maximum tenuring threshold** là mức giới hạn mà một số HotSpot collectors cho phép cấu hình qua `-XX:MaxTenuringThreshold`.
- **Desired/effective tenuring threshold** có thể **thay đổi theo workload** vì collector muốn khống chế lượng live bytes cần chứa ở Survivor.
- Nếu survivor capacity không đủ, object có thể được **promoted sớm hơn** ngưỡng tưởng tượng.
- Những “age” trong diagnostic logs là **GC age**, không phải số giây tuổi đời object hoặc một Java field công khai.

**Không có Java API chuẩn `getObjectGeneration(object)`** để hỏi chính xác object hiện ở Eden, Survivor hay Old.

### 5.2. Promotion không biến object thành GC root

Khi object chuyển từ Survivor sang Old:

- Identity theo Java (`==`, `equals`, `System.identityHashCode` semantics) phải tiếp tục đúng.
- Program references được cập nhật khi collector di chuyển/copy objects; code Java không được tự sửa pointers thủ công.
- Object vẫn có thể trở nên unreachable và được collector thu hồi về sau.
- Promotion là thay đổi **vùng quản lý heap**, không phải lời cam kết ứng dụng sẽ giữ object đó mãi.

### 5.3. Survivor overflow và premature promotion

Một ứng dụng có tỷ lệ đối tượng trẻ sống sót rất cao có thể tạo áp lực lên Survivor. Khi capacity survivor không đủ so với live set, collector có thể promote objects sớm.

Hệ quả: **old occupancy tăng nhanh** dù object mới tạo chưa sống lâu theo thời gian thực. Đây không nhất thiết là memory leak: có thể do allocation bursts, object retention tạm thời, survivor sizing hoặc cache giữ references lâu hơn dự kiến.

Chẩn đoán cần đặt các chỉ số song song: bytes promoted, survivor usage, old occupancy qua nhiều chu kỳ và object lifetime/retained references.

## 6. Old generation: lưu objects sống lâu nhưng vẫn thu gom

Old là nơi thường chứa các objects đã được promoted hoặc được cấp phát trực tiếp theo policy. **Old không đồng nghĩa “Permanent Generation” và cũng không phải Metaspace**.

| Khái niệm | Chứa gì? | GC có liên quan không? |
| --- | --- | --- |
| **Old generation** | Java heap objects trong những vùng thuộc old | **Có**; collector thực hiện marking/reclamation/evacuation tương ứng |
| **Metaspace** (HotSpot) | Class metadata trong native memory | Cơ chế quản lý/unloading riêng, không phải heap old |
| **Java static field** | Field thuộc class; giá trị reference có thể trỏ tới heap object | Object đích nằm trong heap theo chính sách collector; **không tự nằm ở old chỉ vì field static** |
| **GC roots** | Các nguồn root reachability | Không phải mọi GC root đều là heap object; roots giúp xác định objects live |

Ví dụ một `static List<byte[]> CACHE` có thể giữ các arrays sống qua nhiều young collections và cuối cùng chúng được promoted. Khi `CACHE.clear()` và không còn refs khác, chúng có thể trở thành garbage **dù đang ở old**.

### 6.1. Thu gom Old có nhất thiết là Full GC?

**Không.** Trong G1, có:

- Young-only evacuations chỉ tập trung young regions.
- **Mixed collections** xử lý young cùng **một tập old regions được chọn** sau khi có thông tin concurrent marking.
- **Full GC** là cơ chế tốn kém hơn, thường liên quan các tình huống không thể đáp ứng phân bổ/evacuation bằng quy trình thông thường; không phải mọi lần reclaim old đều là Full GC.

Không dùng “Major GC = Full GC = Mixed GC” như ba tên đồng nghĩa. Những thuật ngữ **minor/major** trong sách cũ không ánh xạ một-một vào toàn bộ pha GC của G1.

## 7. HotSpot G1: Eden/Survivor/Old là vai trò của heap REGIONS

**G1 (Garbage-First)** chia Java heap thành nhiều **regions** thường cùng kích cỡ trong một cấu hình. Các regions có thể được gán vai trò Eden, Survivor, Old, Humongous hoặc Free. Những regions thuộc cùng vai trò **không cần nằm liên tục cạnh nhau** như một dải young cố định.

```text
G1 heap gồm nhiều regions (sơ đồ minh họa, KHÔNG theo địa chỉ thật):
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│Eden  │Old   │Free  │Eden  │Surv. │Old   │Eden  │
├──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│Humong│Humong│Old   │Free  │Surv. │Eden  │Free  │
├──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│Old   │Eden  │Free  │Old   │Eden  │Free  │Old   │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┘

Young = tập Eden regions + Survivor regions.
Old   = tập Old regions (có cả cách quản lý humongous riêng).
Mỗi collection có thể thay đổi số regions và vai trò của chúng.
```

### 7.1. Young GC trong G1 thực sự làm gì?

Một **G1 Young GC** điển hình (stop-the-world evacuation pause):

1. JVM xác định tập regions cần thu gom (**collection set**, thường viết tắt `CSet`): các Eden regions và Survivor regions trước đó.
2. Tìm live objects trong tập đó, bao gồm việc xét refs từ roots **và references đi vào từ vùng ngoài CSet** theo remembered sets.
3. Evacuate/copy những object trẻ còn sống sang **new Survivor regions** hoặc **Old regions** dựa trên tuổi/collector policy.
4. Cập nhật các references thích hợp đến object mới được chuyển.
5. Toàn bộ source regions không còn chứa live objects cần giữ có thể được đưa về **Free** và cấp phát lại.
6. Collector điều chỉnh young size, survivor destinations và các chỉ tiêu pause cho những lần kế tiếp.

Với mô hình region-based này, việc thu gom young không cần “quét từng byte của toàn bộ Old” ở mỗi pause để tìm các tham chiếu cũ tới trẻ; G1 dùng remembered sets và write barriers để quản lý thông tin cross-region references. Điều đó là một phần quan trọng để generational collection an toàn.

### 7.2. Một object từ Old trỏ tới Young thì sao?

Ví dụ:

```java
static final java.util.List<Object> ROOTS =
        new java.util.ArrayList<>();

static void remember(Object obj) {
    ROOTS.add(obj);
}
```

Nếu `ROOTS` đã sống trong old và code ghi reference tới một object mới ở Eden, object trẻ **vẫn reachable** qua đường từ Old → Young. Young GC **phải tính tới reference này**, nếu không sẽ thu hồi sai object còn đang được ứng dụng dùng.

Các generational collectors áp dụng **write barriers**, card tables hoặc remembered-set mechanisms theo collector để nhận biết các references cần xét. **Barriers không phải `synchronized` hoặc CPU memory barrier trong Java source do developer phải gọi thủ công**; đây là công việc JVM/GC runtime phối hợp với compiled/interpreted code.

### 7.3. Young size trong G1 có cố định không?

G1 điều chỉnh số regions trong young generation theo pause target, live-data feedback và heap pressure. Điều chỉnh Eden/Survivor capacity giúp cân đối hai mục tiêu:

- Young generation quá nhỏ → young collections thường xuyên, throughput có thể giảm.
- Young generation quá lớn → một đợt evacuation có thể copy nhiều live bytes hơn, tăng pause duration và tốn temporary destination space.

Không có một tỷ lệ “Eden luôn 80% và Survivor mỗi bên 10%” bắt buộc trong G1 Java 17. Các tỷ lệ 8:1:1 phổ biến trong giáo trình chỉ là **ví dụ minh họa cho một số thiết lập/collectors cũ**, không phải hợp đồng của JVM.

## 8. G1 Mixed GC, concurrent marking và thu hồi old regions

Old objects vẫn cần được xem xét khi không còn reachable. G1 phối hợp nhiều pha:

```text
Young-only phase:
  Young GC → Young GC → ... 
              │
              ▼
Concurrent marking cycle (có các pause như initial mark/remark/cleanup)
              │
              ▼
Thu được thông tin live bytes / ứng viên old regions
              │
              ▼
Space-reclamation phase:
  Mixed GC #1: Young + một số Old regions
  Mixed GC #2: Young + một số Old regions
  ...
              │
              ▼
Quay về Young-only phase khi đã xử lý đủ candidate regions
```

**Concurrent marking không đồng nghĩa “old objects được copy ngay khi marking thread quét qua”**. Marking thu thập thông tin liveness cho việc chọn regions, còn evacuation/reclamation diễn ra ở những pha phù hợp. “Concurrent” cũng không có nghĩa toàn bộ G1 không có stop-the-world pauses: G1 vẫn có STW young/mixed evacuations và những pause đánh dấu cụ thể.

### 8.1. Vì sao Mixed GC gồm cả Young và Old?

G1 chọn thêm **một số Old regions đáng thu hồi** vào CSet của một collection đang xử lý Young. Nhờ vậy nó có thể thu hồi old incrementally thay vì buộc mỗi lần phải compact toàn bộ heap trong một Full GC.

Không phải mỗi mixed collection phải thu hồi toàn bộ Old. Chọn ít hay nhiều candidate regions còn liên quan pause target, expected reclaim và policies.

### 8.2. Full GC xuất hiện khi nào?

Trong HotSpot G1, **Full GC** thường là đường tốn kém hơn khi các cơ chế young/mixed/concurrent thông thường không còn tạo đủ tiến triển để đáp ứng allocation. Nó có thể gây pause lớn; cần xem **GC cause/logs** để phân biệt allocation failure, evacuation failure hoặc các điều kiện liên quan.

Một dòng “Old occupancy tăng” **không chứng minh Full GC chắc chắn xảy ra ngay**. Old occupancy là tín hiệu, không phải một câu lệnh GC bắt buộc.

## 9. Humongous objects: ngoại lệ quan trọng của con đường Eden → Survivor → Old

Với G1 Java 17, một object được coi là **humongous** khi kích thước của nó **từ một nửa region trở lên** theo định nghĩa tài liệu G1 (dựa trên region size). Những object này có đường allocation riêng, trực tiếp sử dụng các **humongous regions thuộc old generation**.

```text
Object bình thường, kích thước nhỏ:
    Eden → Survivor → Old (nếu sống/đủ điều kiện)

Object humongous, ví dụ big byte[]:
    cấp phát trực tiếp trong contiguous Humongous regions
    thuộc Old generation
    không bắt buộc đi qua Eden và Survivor
```

Hệ quả:

- Một object ở old **không nhất thiết đã sống qua nhiều Young GC**. Nó có thể được cấp phát trực tiếp theo kích cỡ.
- Humongous objects thường dùng nhiều regions liên tục, và dung lượng dư ở region cuối có thể không được dùng cho object khác cho tới khi reclaim.
- G1 có các đường thu hồi humongous objects tùy loại/điều kiện, bao gồm các cơ chế reclaim opportunistic và các pha marking/cleanup; không nên khẳng định “chỉ Full GC mới thu hồi humongous”.
- GC activity/old occupancy có thể tăng bất ngờ vì **mảng lớn** dù cache data không tồn tại lâu.

Ví dụ `new byte[10_000_000]` **có thể** là humongous tùy region size, heap/VM settings. Đừng khẳng định một kích cỡ cố định như “mọi mảng 1 MB đều là humongous”: ngưỡng là tương đối với **G1HeapRegionSize**. Object headers/alignment cũng ảnh hưởng kích thước tổng của object.

### 9.1. Humongous không đồng nghĩa Large Object Heap của .NET

Các nền tảng khác có cách quản lý large objects khác nhau. Trong Java G1, khái niệm humongous phụ thuộc region size và G1 collector policy. Không đem một ngưỡng của CLR hoặc thế hệ VM khác áp dụng trực tiếp vào HotSpot.

## 10. Từ mô hình tới số liệu: allocation rate, survival rate và promotion rate

Khi chẩn đoán generational GC, nên tách ba câu hỏi:

1. **Allocation rate:** ứng dụng tạo bao nhiêu bytes mới mỗi giây?
2. **Survival rate:** bao nhiêu bytes ở Young còn live sau collection?
3. **Promotion rate:** bao nhiêu bytes được chuyển sang Old qua các collections?

| Hiện tượng | Dấu hiệu hay gặp | Điều cần điều tra |
| --- | --- | --- |
| High allocation, low survival | Young collections thường xuyên; Eden giảm mạnh sau GC | Tạo nhiều đối tượng tạm, boxing, serialization, buffer copy |
| High survival | Survivor/Old destinations nhận nhiều live bytes | Live object graph, caches, queues, transaction lifetime |
| Premature promotion | Old usage tăng dù objects chưa tồn tại lâu trong workload | Survivor pressure, tenuring threshold, burst retention |
| Old không giảm qua mixed cycles | Long-lived live set hoặc GC chưa reclaim đủ | Retained references, heap size, marking, candidate reclaim |
| Humongous pressure | Old/humongous region usage tăng | Large arrays/strings, region size, data shape |
| Full GC hoặc evacuation failure | Pause lớn/không đủ evacuation destinations | Heap headroom, fragmentation, reserve, live set, workload |

**Đừng tối ưu chỉ bằng một con số “GC count”.** Một ứng dụng có nhiều Young GCs ngắn có thể đạt p99 latency tốt hơn ứng dụng có ít GCs nhưng pause dài. Cần đọc logs và kết quả latency/throughput của workload thật.

### 10.1. Allocation ≠ retained heap

Nếu code tạo 1 triệu objects nhỏ rồi mất hết references, tổng allocations có thể lớn trong khi heap live set sau GC rất nhỏ. Ngược lại, ít allocations nhưng một map toàn cục giữ vài GB dữ liệu có thể làm old occupancy cao.

Trình quản lý memory kiểu GC theo thế hệ dựa mạnh vào chênh lệch giữa **allocated bytes** và **live bytes**: phần không còn live trong Eden có thể tái sử dụng bằng cách giữ lại chỉ những object còn sống.

## 11. Chương trình Java 17: tạo allocation churn và giữ một tập object nhỏ

Tạo file **`GenerationalGcDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class GenerationalGcDemo {
    private static volatile List<byte[]> keepAlive;

    public static void main(String[] args) {
        Set<String> poolNames = new HashSet<>();
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            poolNames.add(pool.getName());
        }

        System.out.println("g1EdenPool=" + poolNames.contains("G1 Eden Space"));
        System.out.println("g1SurvivorPool=" +
                poolNames.contains("G1 Survivor Space"));
        System.out.println("g1OldPool=" + poolNames.contains("G1 Old Gen"));

        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 100_000; i++) {
            byte[] block = new byte[2048];
            block[0] = (byte) (i & 127);
            checksum += block[0] & 0xff;
            if (i % 5000 == 0) {
                retained.add(block);
            }
        }

        keepAlive = retained;
        System.out.println("retained=" + retained.size());
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("done");
    }
}
```

Biên dịch và chạy với **HotSpot Java 17 G1**:

```bash
javac --release 17 GenerationalGcDemo.java
java -XX:+UseG1GC -Xms64m -Xmx64m GenerationalGcDemo
```

**Stdout của mã ứng dụng trong môi trường HotSpot JDK 17 G1:**

```text
g1EdenPool=true
g1SurvivorPool=true
g1OldPool=true
retained=20
checksumPositive=true
done
```

### 11.1. Mã này chứng minh điều gì?

- Với **HotSpot JDK 17 G1**, `MemoryPoolMXBean` thường công bố pool names `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen`. Đây là tên **MXBean thuộc implementation**, không phải API requirement cho mọi JVM, collector hay phiên bản.
- Vòng lặp tạo 100.000 mảng `byte[2048]` ở Java source. Collector/JIT quyết định allocation path thực tế; không dùng vòng lặp để suy mỗi `new` chắc chắn tương ứng một vật thể cuối cùng trong heap.
- `retained` giữ **20 mảng** do điều kiện `i % 5000 == 0`; các mảng còn lại không được lưu ở collection đó. Compiler/JIT và các temporary references có thể ảnh hưởng liveness, nhưng có xu hướng tạo lượng lớn dữ liệu tạm.
- `checksumPositive=true` là phép kiểm tra kết quả độc lập với lịch GC, không đòi một số lần collection cụ thể.
- **Chương trình không in “Eden→Survivor→Old” cho từng object**; Java public API không cung cấp mapping generation per object.

### 11.2. Tại sao output không được ghi số lần Young GC?

GC có thể chạy nhiều/lần khác nhau tùy JDK build, heap sizing, CPU, JIT, TLAB và hệ điều hành. Nếu chúng ta in `MemoryPoolMXBean.getUsage()` hay `GarbageCollectorMXBean.getCollectionCount()`, số liệu không có stdout cố định. Bài này intentionally chỉ đưa những dòng có thể suy từ code và tên memory pools trong môi trường HotSpot G1 được chỉ định.

Ở collector khác, ba dòng `g1...Pool` có thể là `false`. Điều này **không** phủ định mô hình generational GC; chỉ cho thấy pool management interface khác nhau.

## 12. Quan sát Eden/Survivor/Old bằng GC logs trên HotSpot JDK 17

Dùng **Unified Logging** của HotSpot:

```bash
# Logging nhiều thông tin; output sẽ gồm GC logs và stdout ứng dụng.
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+age=trace,gc+heap=debug \
  GenerationalGcDemo
```

Lệnh viết theo cú pháp shell POSIX; trên Windows PowerShell có thể viết **một dòng**, bỏ dấu `\` cuối dòng:

```text
java -XX:+UseG1GC -Xms64m -Xmx64m -Xlog:gc*,gc+age=trace,gc+heap=debug GenerationalGcDemo
```

**Không có một stdout/stderr GC log cố định**. Các tag/tên trường và số liệu phụ thuộc JDK build, GC activity, heap size, lịch thực thi và log level. Có thể xuất hiện những thông tin kiểu:

```text
[info ][gc,heap] ... Eden regions: N->0(...)
[info ][gc,heap] ... Survivor regions: A->B(...)
[info ][gc,heap] ... Old regions: X->Y
[trace][gc,age ] ... age 1: ... bytes
```

Đây là **mẫu cách đọc log, không phải output thực tế của một lần chạy cụ thể**. Giá trị N, A, B, X, Y đều là ký hiệu minh họa. Đọc log theo **gc id** và thời điểm trước/sau, không ghép thông tin từ những GC events khác nhau thành một lần tưởng tượng.

### 12.1. Diễn giải một event Young GC

Nếu log ghi một event có ý nghĩa:

```text
Eden regions:       20->0
Survivor regions:    2->3
Old regions:        10->12
```

Đây là **ví dụ số liệu giả lập để luyện đọc**, không phải bảo đảm output của G1:

- Eden source regions đã được thu gom, thường về số lượng 0 trong old eden-set sau evacuation.
- Survivor destination-set dùng 3 regions ở cuối event; không thể suy “3 regions = 3 objects”.
- Old tăng từ 10 lên 12 regions có thể liên quan promotion/allocations và chính sách region, **không tự chứng minh memory leak**.
- Phải kết hợp event type, region size, live bytes/heap occupancy, thời điểm và allocation rate mới hiểu tác động tổng thể.

### 12.2. `gc+age=trace` nói gì?

Age table có thể thể hiện số bytes objects theo **tuổi GC** và thông tin desired survivor size/new threshold trong những bản HotSpot phù hợp. Ví dụ ý tưởng:

```text
age 1: ... bytes
age 2: ... bytes
new threshold ... 
```

**Age 2 không nghĩa object có tuổi đời hai giây.** Nó phản ánh việc object sống qua những lần young processing phù hợp theo collector. Log age table còn không phải thống kê tuổi cho **mọi old object** trong toàn heap. Tùy flags/version, một số dòng không xuất hiện nếu không có event hoặc level phù hợp.

### 12.3. Ghi GC log ra file thay vì màn hình

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
  -Xlog:gc*,gc+age=trace,gc+heap=debug:file=gc.log:time,uptime,level,tags \
  GenerationalGcDemo
```

Đây là syntax HotSpot Unified Logging trên Java 17: selector, output file và decorators. File `gc.log` được ghi ở thư mục làm việc; quản lý retention/log rotation của môi trường production cần cấu hình riêng. Đừng để `trace` logs dung lượng lớn chạy không giới hạn ở server bận.

### 12.4. So với tool `jstat`

HotSpot có `jstat -gc <pid> 1000` để quan sát thống kê GC/pool capacity/usage của **process đang chạy**. Nhưng demo ở mục 11 có thể hoàn tất nhanh nên không kịp lấy mẫu. Nếu muốn giám sát thật, dùng process/server sống đủ lâu; không kéo dài demo tùy tiện bằng sleep rồi tự cho rằng GC chắc chắn xảy ra.

Một số cột `jstat` được đặt tên theo generations cũ; cách diễn giải phải gắn với collector và version. Trong G1 nên ưu tiên GC logs và memory pool metrics đúng collector.

## 13. Đọc đúng “Minor”, “Major”, “Young”, “Mixed”, “Full”

Các tài liệu Java GC thường dùng từ:

| Thuật ngữ | Cách hiểu đúng trong bài |
| --- | --- |
| **Minor GC** | Thu gom young trong cách gọi phổ biến/truyền thống; không phải mọi collector dùng đúng tên event này |
| **Young GC** | Trong G1, young-only evacuation của Eden/Survivor regions |
| **Mixed GC** | Trong G1, collection có Young và một số Old regions phù hợp |
| **Major GC** | Thuật ngữ không thống nhất giữa collectors/tài liệu; cần xác định GC log event thực |
| **Full GC** | Một kiểu collection xử lý heap rộng hơn, thường có mức pause và cách thực hiện khác young/mixed; không đồng nhất với mixed |
| **Concurrent mark** | Pha tìm liveness, có phần chạy đồng thời; không có nghĩa thu hồi/copy mọi old region ngay |

Không rút gọn G1 thành “Minor GC chỉ trẻ, Major GC quét già mỗi khi Old đầy” như thể có đúng hai nút bấm. G1 thường xen kẽ Young GC, concurrent marking, mixed reclamation, và chỉ dùng Full GC trong một số điều kiện.

## 14. Tuning: ưu tiên hiểu collector trước khi chỉnh thế hệ

G1 được thiết kế để tự điều chỉnh nhiều thông số, đặc biệt là young generation size, nhằm đáp ứng **pause time goal** và cân bằng throughput.

Những knobs phổ biến trong HotSpot Java 17:

- `-XX:+UseG1GC`: chọn G1 khi muốn điều kiện thử nghiệm rõ ràng.
- `-Xms` / `-Xmx`: initial/maximum Java heap; ảnh hưởng headroom và tần suất GC.
- `-XX:MaxGCPauseMillis=<ms>`: **mục tiêu pause**, không phải hard deadline.
- `-XX:MaxTenuringThreshold=<n>`: giới hạn tuổi dùng trong chính sách tenuring khi phù hợp; không buộc mọi object “ở Survivor n lần rồi vào Old”.
- `-XX:G1HeapRegionSize=<bytes>`: thay region size, ảnh hưởng số regions và ngưỡng humongous; không chỉnh bừa để chữa mọi GC problem.

**Đừng copy blind** một đoạn tuning cũ cho Serial/Parallel GC rồi áp vào G1. Chẳng hạn hình ảnh `Eden:S0:S1 = 8:1:1` chỉ là biểu diễn của một số collectors/thiết lập và có thể không phản ánh young region sizing adaptive của G1.

### 14.1. Cách thử nghiệm khi old tăng nhanh

1. Chụp cấu hình thực tế: JDK vendor/version, `java -version`, collector, heap size, CPU và GC logs.
2. Đo allocation throughput và tỷ lệ sống trẻ qua age/survivor information.
3. Kiểm tra promotion pressure và thời gian giữ references trong cache, queue, thread-local hoặc listeners.
4. Xem old occupancy **sau nhiều collections**, không đọc một snapshot đơn lẻ.
5. Nếu có humongous pressure, kiểm tra kích thước arrays và region sizes trước khi chỉnh `G1HeapRegionSize`.
6. Đối chiếu pause time (p95/p99), application throughput và CPU sử dụng.
7. Chỉ thay **một** nhóm tham số mỗi thí nghiệm rồi chạy lại cùng workload; ghi rõ kết quả.
8. Ưu tiên loại bỏ retention không cần thiết và allocation bùng nổ trong code trước khi ép các ngưỡng tenuring.

### 14.2. Khi nào old generation tăng là bình thường?

Sau startup hoặc warmup, những structures được khởi tạo một lần rồi giữ lâu (caches, class data structures, connection pools, compiled-code-related references) có thể làm old live set tăng và **ổn định**. Điều quan trọng là old retained memory có tăng không giới hạn theo traffic hay có đạt plateau.

Một đường old usage hình răng cưa với nhiều mixed GC không tự là leak. Cần phân biệt **lượng memory được committed/occupied** với **lượng live bytes không thể giải phóng**.

## 15. Không thể suy object age từ source code

Hai snippets:

```java
static byte[] permanentlyHeld = new byte[1024];

static void temporary() {
    byte[] tmp = new byte[1024];
    System.out.println(tmp.length);
}
```

Đều có `new byte[1024]`, nhưng:

- `permanentlyHeld` có static strong reference, có thể sống qua nhiều Young GCs và được promoted.
- `tmp` không còn needed sau method, có thể chết sớm hoặc JIT có thể tối ưu tùy phép sử dụng.
- Không có bảo đảm `permanentlyHeld` bắt đầu ở Eden trên mọi VM/GC/optimization.
- Nếu object static bị thay/xóa và không còn references khác, nó vẫn có thể trở thành garbage dù đã vào Old.

Điểm cốt lõi là **liveness và allocation path** của runtime chứ không phải tên biến.

### 15.1. Object được promoted rồi có thể quay lại Eden không?

Trong mô hình generational phổ biến, object đã ở Old **không được “trẻ hóa” trở lại Eden** chỉ vì ứng dụng cập nhật field hoặc tạo reference mới tới nó. Hãy coi promotion là một bước chuyển vùng quản lý đối tượng, không phải đếm ngược tuổi khi hết thời gian.

Tuy vậy, chi tiết di chuyển objects có thể khác giữa collectors. Không biến câu này thành một quy tắc ABI chung về địa chỉ object trên Java heap.

## 16. Các lỗi hiểu sai thường gặp

1. **“Young generation luôn chiếm đúng 1/3 heap.”** Sai; sizing tùy collector/config và G1 thường adaptive.
2. **“Eden, S0, S1 và Old luôn là bốn dải địa chỉ liên tục cố định.”** Sai với G1 region model.
3. **“Eden đầy thì chắc chắn OutOfMemoryError.”** Sai; Young GC có thể giải phóng space để cấp phát tiếp.
4. **“Mỗi object phải đi qua Survivor đúng hai lần trước khi Old.”** Sai; age threshold và survivor capacity thay đổi.
5. **“Age 3 nghĩa object đã sống ba giây.”** Sai; age liên quan số lần sống qua young processing.
6. **“Có strong reference thì object phải ở Old ngay.”** Sai; reachability và generation location khác nhau.
7. **“Object ở Old không bao giờ được GC.”** Sai; G1 mixed/other collection xử lý old.
8. **“Mixed GC chính là Full GC.”** Sai; mixed là evacuation young + một tập old regions.
9. **“Concurrent marking nghĩa toàn bộ GC không có pause.”** Sai; G1 vẫn có pauses STW.
10. **“Mọi object đều cấp phát vào Eden.”** Sai; G1 humongous objects vào old regions, JIT có thể loại bỏ allocation.
11. **“Một object ở Old chắc chắn đã rất già.”** Sai; có đường trực tiếp vào old.
12. **“Old tăng sau một GC = memory leak.”** Sai; có thể là promotion bình thường.
13. **“Số lần GC càng ít càng tốt.”** Không nhất thiết; phải cân bằng pause, throughput, live set và SLA.
14. **“Minor, Major và Full GC là thuật ngữ chuẩn giống nhau trên mọi VM.”** Sai; xem log và collector thực.
15. **“Tăng MaxTenuringThreshold luôn tốt hơn.”** Sai; giữ objects quá lâu ở survivor cũng tốn copy và pause.
16. **“Đặt survivor quá bé không có tác dụng phụ.”** Sai; có thể dẫn đến premature promotion và old pressure.
17. **“Object ở Survivor chắc chắn sắp chết.”** Sai; nó đang live tại thời điểm collection.
18. **“TLAB là một thế hệ mới giữa Eden và Survivor.”** Sai; TLAB là allocation optimization.
19. **“GC logs nói Eden regions=30 nghĩa 30 object.”** Sai; một region chứa nhiều objects.
20. **“Survivor region count tăng luôn chứng minh leak.”** Sai; có thể do current live set và adaptive sizing.
21. **“Static field luôn đặt object trong Old.”** Sai; reference origin không quy định chỗ cấp phát object.
22. **“Humongous object phải qua Eden rồi mới thăng cấp.”** Sai với G1.
23. **“G1HeapRegionSize không ảnh hưởng large object behavior.”** Sai; nó ảnh hưởng humongous threshold.
24. **“Bật `-Xlog:gc*=debug` sẽ tạo stdout giống hệt mọi máy.”** Sai; logs phụ thuộc JDK và workload.

## 17. Tự kiểm tra có đáp án

**Câu 1.** Tại sao GC theo thế hệ thường xử lý Eden thường xuyên hơn Old?

**Đáp án:** Nhiều objects mới tạo chết sớm, nên thu gom young có thể lấy lại nhiều dung lượng với chi phí quét/copy live objects thấp hơn so với xử lý mọi old data ở mỗi event.

**Câu 2.** Một object ở Eden còn reachable qua static list khi Young GC xảy ra. Điều gì có thể xảy ra?

**Đáp án:** Nó được giữ lại bằng evacuation/copy, thường sang Survivor hoặc Old theo age/policy. Không bị xóa chỉ vì nằm trong Eden.

**Câu 3.** Age của object từ 1 lên 2 nghĩa là gì?

**Đáp án:** Trong mô hình young copying, nó đã sống qua thêm một lần xử lý/evacuation young phù hợp; không phải tự cộng một giây tuổi đời.

**Câu 4.** Survivor không đủ chỗ cho object còn live thì sao?

**Đáp án:** Collector có thể promote sớm vào Old hoặc áp dụng cơ chế khác theo policy, nếu có đủ vùng đích phù hợp.

**Câu 5.** G1 có đúng hai Survivor memory blocks cố định không?

**Đáp án:** Không. G1 quản lý survivor **regions** thuộc young set, có thể thay đổi số lượng/vị trí theo cycles. S0/S1 là sơ đồ kinh điển giúp hiểu việc copying.

**Câu 6.** Vì sao G1 cần remembered sets/write barriers?

**Đáp án:** Young GC phải thấy các references từ những regions **ngoài CSet** vào những objects trong CSet để không thu hồi nhầm objects vẫn reachable, ví dụ Old → Young.

**Câu 7.** Mixed GC khác Full GC thế nào?

**Đáp án:** G1 mixed thu gom young và **một số old regions** dựa trên selection, trong khi Full GC là đường thu gom rộng/tốn kém hơn và không đồng nghĩa với mixed.

**Câu 8.** Vì sao một mảng `byte[]` lớn có thể vào Old ngay?

**Đáp án:** Nếu được G1 coi là **humongous** theo kích thước tương đối với region (từ nửa region trở lên), nó dùng humongous regions thuộc old generation.

**Câu 9.** `-XX:MaxGCPauseMillis=100` có bảo đảm mọi GC dưới 100 ms không?

**Đáp án:** Không. Đây là mục tiêu để G1 heuristic điều chỉnh collection set/young size, không phải SLA cứng.

**Câu 10.** Vì sao `GenerationalGcDemo` chỉ in 20 retained arrays dù loop chạy 100.000 lần?

**Đáp án:** Điều kiện `i % 5000 == 0` đúng cho `i = 0, 5000, ..., 95000`, tức 20 lần. Các arrays còn lại không được thêm vào `retained`.

**Câu 11.** Sau khi loại hết references tới cache objects trong Old, chúng có bị thu hồi ngay không?

**Đáp án:** Không có bảo đảm ngay lập tức; chúng có thể được reclaim trong những collections phù hợp về sau. Old không bất tử, nhưng GC scheduling không deterministic.

**Câu 12.** Có thể khẳng định một class field khai báo `static final` khiến object của nó được cấp phát Old từ đầu không?

**Đáp án:** Không. Static strong reachability làm object có khả năng sống lâu, không tự quyết định generation/location của allocation.

## 18. Tổng kết

```text
Most new heap objects
       │
       ▼
     EDEN
       │
       ▼ Young GC
 ┌─────┴─────────────┐
 │ unreachable       │ still reachable
 ▼                   ▼
reclaim          SURVIVOR
                    │
                    ├── live qua young evacuations
                    │      → age tăng, có thể copy tiếp
                    │
                    ├── đủ điều kiện promote
                    │      → OLD
                    │
                    └── unreachable lần sau
                           → reclaim
                            
OLD:
  - không đồng nghĩa immortal
  - G1 concurrent marking + mixed reclamation
  - special path cho humongous allocations
  - Full GC chỉ khi phù hợp các tình huống runtime

G1:
  Eden/Survivor/Old = vai trò của REGIONS;
  không phải ba dải địa chỉ bất biến.
```

**Ghi nhớ:** Eden là nơi thường đón allocations mới; Survivor giữ live young objects qua những lần young collections; Old giữ long-lived/promoted objects và một số object được cấp phát đặc biệt. **Promotion do GC age, survivor capacity và collector heuristics chi phối**, không theo số giây kể từ `new`. Với **G1 Java 17**, ba vai trò này được xây trên **regions** thay đổi linh hoạt; G1 có young-only collections, concurrent marking, mixed collections và những cơ chế thu hồi đặc biệt cho humongous/old. Để tối ưu đúng, hãy nhìn **allocation rate, survival/promotion rates, retained heap, pauses và GC logs**, thay vì cố đoán tuổi đối tượng từ source code.

### Tài liệu tham khảo chuẩn

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): young/old regions, copying, humongous và GC cycles.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector-tuning.html): adaptive sizing và tuning recommendations.
- [Oracle Java SE 17 — HotSpot GC Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): thế hệ GC và collector-specific behavior.
- [Oracle — Garbage First GC Tuning](https://www.oracle.com/java/technologies/g1gc.html): phân biệt young/mixed/concurrent marking và tenuring.
- [Oracle JDK 17 `java` launcher manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `UseG1GC`, `Xms`/`Xmx`, `Xlog` và HotSpot flags.
- [Oracle JDK 17 `jstat` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): thống kê GC/memory pools.
- [Java SE 17 — `MemoryPoolMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): Java management API cho memory pools.
