# Đối tượng humongous, evacuation failure và Full GC trong G1

Trong HotSpot, **G1 (Garbage-First Garbage Collector)** quản lý Java heap dưới dạng nhiều vùng nhỏ gọi là **regions**. Thay vì luôn thu gom toàn heap, G1 ưu tiên các tập regions có khả năng thu hồi nhiều bộ nhớ trong thời gian tạm dừng phù hợp với mục tiêu độ trễ. Tuy nhiên, ba hiện tượng đặc biệt có thể khiến G1 phải làm nhiều việc hơn dự kiến:

- **Humongous objects**: đối tượng có kích thước lớn so với region, phải chiếm **một dãy regions liên tiếp** và được quản lý khác với object nhỏ trong Eden.
- **Evacuation failure / to-space exhausted**: khi G1 cố sao chép các object còn sống khỏi collection set nhưng **không có đủ vùng đích** để chuyển chúng tới.
- **Full GC**: một đường thu gom quy mô toàn heap, có thể gồm **in-place compaction**, thường mang tính dự phòng khi G1 không giải phóng đủ bộ nhớ bằng cơ chế young/mixed/concurrent bình thường.

Ba khái niệm có quan hệ nguyên nhân – hệ quả trong nhiều tình huống, nhưng **không đồng nghĩa**. Có humongous object không chắc xảy ra evacuation failure; có evacuation failure không chắc lập tức Full GC; và Full GC có thể xuất hiện vì các lý do khác.

Bài bám sát **HotSpot/OpenJDK Java 17** và tài liệu **Oracle Java SE 17 G1 Garbage Collector / G1 Tuning**. Những chính sách vùng nhớ và JVM options được nêu là **chi tiết triển khai/version-specific**, không phải yêu cầu bắt buộc của mọi JVM hay mọi release G1.

## 1. Ôn lại cấu trúc G1: heap gồm các regions

G1 phân Java heap thành những **regions có kích thước bằng nhau**. Kích thước region thường do JVM chọn dựa trên heap size, hoặc được cấu hình bằng `-XX:G1HeapRegionSize` trong giới hạn mà build hỗ trợ. Một region tại một thời điểm có vai trò như Eden, Survivor, Old, Free hoặc vùng dành cho humongous object.

```text
Java heap trong mô hình G1:

+---------+---------+---------+---------+---------+---------+
| Eden R0 | Eden R1 | Surv R2 | Old R3  | Free R4 | Free R5 |
+---------+---------+---------+---------+---------+---------+
| Old R6  | Hum S   | Hum C   | Free R9 | Old R10 | Free R11|
+---------+---------+---------+---------+---------+---------+

Hum S = StartsHumongous
Hum C = ContinuesHumongous

Mỗi ô minh họa một region bằng kích thước nhau.
Các loại region là vai trò logic, không bắt buộc nằm liền nhau
theo nhóm Eden/Survivor/Old.
```

G1 thường thu gom những **collection sets (CSet)** được chọn trong young/mixed collections:

1. Xác định tập regions cần collection.
2. Tìm các references tới objects trong CSet từ GC roots và từ các regions bên ngoài CSet; remembered sets/card tracking hỗ trợ phần việc này.
3. **Evacuate** (copy) những objects còn sống sang destination regions thích hợp.
4. Cập nhật/chuyển hướng các references để Java object identity và truy cập vẫn đúng.
5. Khi an toàn, reclaim các source regions đã được xử lý thành công.

Một điều quan trọng: **G1 concurrent marking** có thể chạy đồng thời với Java application threads để đánh giá liveness, nhưng **young/mixed evacuation của G1 Java 17 chủ yếu diễn ra trong stop-the-world pauses**. Đừng suy rằng “G1 concurrent” nghĩa mọi thao tác copy objects đều diễn ra concurrent như các collector thiết kế concurrent relocation.

## 2. Humongous object được xác định thế nào?

Theo tài liệu G1 của **Java 17**, một object có tổng kích thước **lớn hơn hoặc bằng một nửa kích thước một region** được phân loại là **humongous**.

```text
R = kích thước một G1 region

Nếu object size >= R/2
  => humongous object

Ví dụ R = 1 MiB:
  ngưỡng đối với tổng object size ≈ 512 KiB
```

**Chú ý:** kích thước được xét là **kích thước object trong heap**, gồm cả object header, alignment/padding thích hợp, không đơn giản là số bytes của payload array mà lập trình viên truyền vào `new byte[n]`. Vì thế `new byte[512 * 1024]` có thể vượt ngưỡng ngay cả khi payload bằng đúng 512 KiB. Không lấy độ dài array hay `String.length()` làm kích thước object chuẩn mà quên layout thực tế.

### Các ví dụ dễ xuất hiện humongous objects

- Một `byte[]` rất lớn dùng chứa ảnh, dữ liệu nén, file hoặc network payload được copy nguyên khối.
- Một `char[]`, `int[]`, `long[]` hoặc `Object[]` lớn.
- Một backing array lớn của collection hoặc buffer **trên Java heap**.
- Một object chứa vùng dữ liệu primitive lớn có kích thước vượt ngưỡng (trên thực tế Java object lớn thường là arrays).
- Những allocations trung gian trong serialization hoặc batch processing có payload rất lớn.

Không nhầm với **direct buffer backing memory**: `ByteBuffer.allocateDirect` có backing region ngoài Java heap theo API. Java wrapper của direct buffer vẫn là Java object, nhưng một native allocation lớn **không tự đồng nghĩa một G1 humongous Java heap object**.

## 3. Humongous được cấp phát vào đâu?

Một humongous object được G1 quản lý như một **chuỗi regions liên tiếp** trong vùng old-generation logic. G1 sử dụng loại regions:

- **`StartsHumongous`**: region đầu tiên chứa điểm bắt đầu của object.
- **`ContinuesHumongous`**: một hoặc nhiều regions nối tiếp dành cho phần còn lại nếu object lớn hơn một region.

Đối tượng bắt đầu từ đầu region đầu tiên. Nếu kích thước object không dùng hết region cuối, phần còn lại của region cuối **không thể được cấp phát cho một object khác** cho tới khi toàn bộ humongous object được reclaim.

```text
Giả sử region size = 1 MiB
Object H có tổng size ~1,25 MiB

+----------------------+----------------------+
| StartsHumongous      | ContinuesHumongous   |
| H chiếm đủ 1 MiB     | H dùng khoảng 0,25MiB|
|                      | còn ~0,75MiB không   |
|                      | dùng cho object khác |
+----------------------+----------------------+

Mỗi region = 1 MiB; đây là ví dụ làm tròn đơn giản.
```

Nếu size object là `S` và region size `R`, số regions cần ở mức mô hình:

```text
neededRegions = ceil(S / R)

reservedRegionBytesForObject = neededRegions * R
unusedTailBytes = reservedRegionBytesForObject - S
```

Công thức giúp hiểu **internal waste ở region cuối**, không phải thuật toán tính kích thước object của HotSpot trong mọi layout. Phần waste tăng đáng chú ý khi object chỉ lớn hơn một bội số nguyên của region size, ví dụ khoảng 1,01 MiB trong region 1 MiB cần 2 regions nhưng để trống gần 0,99 MiB cuối cùng.

### Humongous allocation không đi qua cùng đường Eden thông thường

Vì phải có chuỗi regions, allocation này được hạch toán trực tiếp ở old generation theo G1, thay vì đi qua vòng đời bình thường `Eden → Survivor → Old` của một object nhỏ. Do đó:

- Allocation rate của humongous objects có thể khiến **old occupancy tăng nhanh**.
- Những burst large arrays có thể ảnh hưởng **IHOP/concurrent marking**, ngay cả khi chúng rất ngắn hạn.
- Cần đo **kích thước và số lượng humongous objects**, không chỉ tổng allocation bytes/giây.

Một object được phân loại humongous không đồng nghĩa nó phải sống lâu về nghiệp vụ. Nó có thể được tạo, dùng trong vài milliseconds rồi bỏ, nhưng vẫn cần cơ chế reclaim riêng.

## 4. Hai dạng lãng phí bộ nhớ: unused tail và fragmentation giữa regions

**Thứ nhất: unused tail trong region cuối.** Phần chưa dùng của dãy humongous regions đã được gán cho object đó nhưng chưa được cấp cho object khác. Ví dụ object 1,1 MiB cần 2 regions 1 MiB và lãng phí khoảng 0,9 MiB (số mô hình).

**Thứ hai: fragmentation ở mức contiguous regions.** G1 cần tìm **một dãy regions trống liên tiếp** đủ dài để đặt humongous object. Tổng số free regions có thể lớn, nhưng nếu các free runs bị chia nhỏ, allocation lớn vẫn gặp trở ngại.

```text
Mỗi dấu . là 1 free region; X là region đã bị chiếm.

Heap regions theo thứ tự địa chỉ:

.. X . XX .... X .. X .

Free runs: độ dài 2, 1, 4, 2, 1
Tổng free regions = 10
Longest contiguous free run = 4

Object cần 5 regions liên tiếp:
  KHÔNG có free run đủ dài trong bố cục này,
  dù tổng free regions = 10.
```

Đây là ví dụ minh họa độc lập với một snapshot heap thực tế. G1 còn có các cơ chế recovery, concurrent reclamation và Full GC; không thể suy từ sơ đồ rằng VM chắc chắn lập tức ném OOME.

### Vì sao heap free không đảm bảo humongous allocation thành công?

`-Xmx - used` là tổng chênh lệch dung lượng, không phải phép đo “longest contiguous region run”. Một G1 heap có thể có **tổng free lớn** mà vẫn khó cấp phát một object cần nhiều regions liên tiếp. Đó là nguyên nhân một ứng dụng có thể chạm Full GC/OOME trước khi toàn heap dashboard báo 100% occupancy.

## 5. Java 17: tính ngưỡng và số vùng bằng mô hình xác định

Tạo file **`HumongousMath.java`**:

```java
public class HumongousMath {
    private static final long KIB = 1024L;
    private static final long MIB = 1024L * KIB;

    private static long regionsNeeded(long objectBytes, long regionBytes) {
        if (objectBytes <= 0 || regionBytes <= 0) {
            throw new IllegalArgumentException("positive sizes required");
        }
        return 1 + (objectBytes - 1) / regionBytes;
    }

    public static void main(String[] args) {
        long region = 1 * MIB;
        long threshold = region / 2;
        long object = MIB + 256 * KIB; // 1,25 MiB, gồm size giả định
        long regions = regionsNeeded(object, region);
        long tail = regions * region - object;

        System.out.println("regionKiB=" + region / KIB);
        System.out.println("thresholdKiB=" + threshold / KIB);
        System.out.println("objectKiB=" + object / KIB);
        System.out.println("humongous=" + (object >= threshold));
        System.out.println("regionsNeeded=" + regions);
        System.out.println("unusedTailKiB=" + tail / KIB);
    }
}
```

```bash
javac --release 17 HumongousMath.java
java HumongousMath
```

**Stdout chính xác:**

```text
regionKiB=1024
thresholdKiB=512
objectKiB=1280
humongous=true
regionsNeeded=2
unusedTailKiB=768
```

Chương trình chỉ mô phỏng **size đã biết**: nó không gọi API đo kích thước thực của object trên HotSpot. Dòng `object = MIB + 256 * KIB` là tổng object bytes **giả định**, không phải `new byte[...]` có chắc object size đúng bằng giá trị ấy.

### Tính theo payload thực tế cẩn thận ra sao?

Một `byte[]` có header, length field và alignment. Trên HotSpot, overhead phụ thuộc 32-/64-bit, compressed oops/class pointers, object alignment và runtime build. Nếu cần dự đoán class size sát thực tế, dùng profilers/diagnostics thích hợp và xác nhận với JVM đang chạy; không áp một con số header “16 bytes” cố định cho mọi cấu hình. Khi threshold quá gần payload, dùng vùng đệm an toàn hoặc đo bytecode/runtime để tránh nhầm side của ranh giới.

## 6. Thay đổi region size có tác động gì?

Flag HotSpot thường dùng:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC \
  -XX:G1HeapRegionSize=2m -jar app.jar
```

`app.jar` là JAR minh họa phải tồn tại; lệnh có line continuation theo shell Unix/Bash. Trên Windows PowerShell nên đặt một dòng hoặc đổi cú pháp xuống dòng phù hợp. Region size được G1/HotSpot giới hạn theo build; không chọn một giá trị tùy ý rồi giả định JVM luôn chấp nhận.

Nếu region size từ 1 MiB tăng lên 2 MiB, ngưỡng humongous tăng từ khoảng 512 KiB lên **1 MiB**. Một object có tổng size khoảng 768 KiB có thể:

- Là humongous khi regions 1 MiB.
- Trở thành regular object theo đường cấp phát thông thường khi regions 2 MiB.

**Nhưng không suy “region size càng lớn càng tốt”:**

- Region lớn hơn làm số regions ít hơn, giảm độ chi tiết khi G1 chọn collection sets.
- Lượng bytes/region lớn hơn có thể ảnh hưởng pause predictability, mixed collection flexibility, humongous tail waste với các kích thước khác, remembered-set behavior và fragmentation.
- Những object lớn hơn ngưỡng mới vẫn humongous.
- Tăng region size có thể gây trade-off trong nhiều workloads và với heap size khác nhau.

Điều chỉnh chỉ khi histogram cho thấy **rất nhiều allocations nằm ngay phía trên ngưỡng cũ**, và benchmark trên đúng JDK 17 build/workload chứng minh lợi ích.

## 7. Humongous reclamation: khi nào G1 lấy lại các regions?

Với G1 Java 17, những humongous objects không còn reachable có thể được reclaim thông qua:

1. **Cleanup sau concurrent marking** khi liveness cho phép và collector kết thúc cycle thích hợp.
2. **Eager reclaim** trong một số GC pauses đối với những **primitive arrays humongous** thỏa điều kiện collector xác định rằng chúng không còn được tham chiếu theo heuristic an toàn. Cơ chế này phụ thuộc flag `-XX:G1EagerReclaimHumongousObjects` và chính sách implementation.
3. **Full GC**, nếu đối tượng thực sự không còn cần giữ sống và collector thực hiện toàn-heap collection/fallback.

Không nói “G1 luôn phải đợi Full GC mới thu hồi humongous”. Cũng không nói “bỏ reference là region được free ngay”: một GC phase/cycle phải xác định an toàn để reclaim.

### Vì sao primitive arrays được chú ý?

Tài liệu Oracle Java 17 ghi nhận **eager reclamation** cho những humongous objects dạng **arrays of primitive types** (ví dụ `byte[]`, `int[]`). Vì các phần tử của primitive array **không phải Java object references**, thuật toán và việc xác định tính an toàn reclaim có thể đơn giản hơn một array chứa object references.

Tuy nhiên:

- Không hứa **mọi** primitive array không còn reachable sẽ được reclaim ngay pause gần nhất.
- Heuristic này phụ thuộc trạng thái references/regions và JVM build.
- `Object[]` humongous không nên được giả định có hành vi eager reclaim hoàn toàn giống `byte[]`.
- Dùng GC log để xác nhận reclaim thật, không dựa vào một `System.gc()` trong mã.

### Vì sao một humongous object có thể không được move?

G1 normally excludes humongous regions khỏi **young/mixed evacuation collection sets**: chúng được xử lý bằng cơ chế riêng, không copy mỗi lần Young GC như objects nhỏ trong Eden. Tài liệu G1 Java 17 mô tả chúng chủ yếu ở nguyên vị trí và các hạn chế của vùng liên tiếp, kể cả với Full GC. **Đừng khẳng định Full GC luôn sẽ dồn mọi humongous object sang vị trí mới để giải quyết fragmentation.** Chính sách di chuyển/fallback đặc biệt thay đổi theo JDK version và implementation; đánh giá đúng Java 17 build đang chạy.

## 8. Humongous allocation có thể thúc đẩy concurrent marking sớm

Trong G1, mỗi humongous allocation có thể kích hoạt kiểm tra **Initiating Heap Occupancy (IHOP)**. Nếu old/heap occupancy theo policy vượt ngưỡng và chưa có marking cycle phù hợp, G1 có thể bắt đầu một **Concurrent Start young collection** để khởi động concurrent marking.

Hệ quả:

- Một ứng dụng tạo nhiều large temporary arrays có thể tạo **nhiều yêu cầu marking** dù dữ liệu chết khá nhanh.
- Old region occupancy có thể tăng do humongous allocations trước khi reclamation kịp bắt nhịp.
- Marking dùng **Snapshot-At-The-Beginning (SATB)**; object đã sống tại đầu snapshot nhưng chết giữa cycle có thể vẫn được coi sống trong cycle đó, khiến reclaim chậm đến lần thích hợp sau.
- Allocation burst trong thời gian marking đang chạy vẫn có thể lấp thêm regions.

Điểm quan trọng về log: một message “Concurrent Start” gần humongous allocation là dấu hiệu có thể liên quan, **không phải bằng chứng mọi humongous allocation đều gây một new cycle**.

### IHOP và adaptive marking

G1 có thể tính ngưỡng bắt đầu marking theo những dự báo như tốc độ old allocation/promotion và thời gian marking cần. Tham số liên quan:

- `-XX:InitiatingHeapOccupancyPercent`
- `-XX:+G1UseAdaptiveIHOP` hoặc `-XX:-G1UseAdaptiveIHOP` theo điều chỉnh cụ thể
- `-XX:G1ReservePercent`
- `-XX:ConcGCThreads`

Không chỉnh tất cả flags theo một bảng chung. Nếu marking bắt đầu quá muộn so với **tốc độ old/humongous occupancy tăng**, G1 có thể chưa hoàn thành marking/mixed reclamation trước khi headroom cạn. Nhưng nếu bắt đầu quá sớm, có thể tốn thêm CPU/GC work và ảnh hưởng throughput.

## 9. Evacuation: vì sao cần to-space?

Trong một young/mixed GC, G1 thường di chuyển objects còn sống từ CSet đến **to-space** (destination regions) để source regions có thể được reclaim.

```text
Trước pause:

CSet:
  Eden R0  : 30 MiB allocated, 5 MiB live
  Eden R1  : 30 MiB allocated, 8 MiB live
  Old  R2  : 30 MiB allocated, 20 MiB live

Ngoài CSet:
  Free destination capacity (mô hình) = 40 MiB

Live bytes cần bảo toàn/có thể copy ~33 MiB.
Trong mô hình đơn giản này destination có vẻ đủ.
```

Các con số mô hình này không đại diện cho region size thật của G1, bởi nếu một region là 30 MiB thì phải xử lý theo quy tắc size của collector; chúng chỉ minh họa **dung lượng tập vùng**, không phải ba G1 regions kích thước 30 MiB của JVM thực.

Khi G1 chuyển objects, forwarding metadata bảo đảm hai references cùng trỏ tới một logical object tiếp tục tìm tới một destination hợp lệ, còn update/reference processing duy trì correctness trước khi application tiếp tục.

**To-space không phải một vùng RAM độc lập bên ngoài `-Xmx`.** Nó nằm trong heap regions được policy G1 sử dụng làm destination, và cần có **headroom** còn hiệu dụng.

### Live ratio quyết định copy pressure

Giả định trong một CSet đã có 300 MiB objects:

| Tình huống | Live bytes | Dead bytes | Survival ratio |
| --- | ---: | ---: | ---: |
| Young data chết nhanh | 30 MiB | 270 MiB | 10% |
| Nhiều objects sống lâu | 250 MiB | 50 MiB | 83,33% |

CSet thứ hai có thể cần bảo toàn/copy nhiều bytes hơn rất nhiều, ngay cả khi allocation volume trước GC tương đương. Điều này làm to-space pressure tăng, promotion lên old có thể nhiều hơn và evacuation pause có thể đắt hơn.

## 10. Evacuation failure / to-space exhausted thực chất là gì?

**Evacuation failure** xuất hiện khi G1 đang cố sao chép survivors/living objects khỏi CSet nhưng không có đủ **destination capacity** để copy tất cả. Dấu hiệu log trên nhiều HotSpot 17 builds là **`to-space exhausted`**.

Điểm cần phân biệt:

- **Có GC thành công về mặt tính đúng** không có nghĩa mọi object đã được copy đúng kế hoạch.
- G1 có thể đã chuyển **một số objects** trước khi phát hiện thiếu to-space.
- Những objects còn lại có thể được **giữ ở vị trí cũ**, kèm forwarding/self-forwarding hoặc cơ chế nội bộ phù hợp.
- G1 điều chỉnh các references và metadata để Java application vẫn truy cập đúng objects; nó không được để reference trỏ vào memory đã reclaim sai.
- Sau pause, application **có thể tiếp tục bình thường** nếu đủ khả năng hoạt động, dù event đã đánh dấu memory pressure.
- Nếu G1 không reclaim đủ nhanh hoặc to-space pressure tiếp tục, có thể tiến tới **Full GC**.

Oracle Java 17 mô tả evacuation failure như đường cố gắng hoàn tất collection hiện tại bằng cách giữ objects đã copy tại vị trí mới và **không copy** những objects chưa thể move, đồng thời sửa references giữa chúng.

### Timeline minh họa

```text
T0  Application liên tục allocate; old/humongous occupancy cao
T1  Young/mixed GC bắt đầu; CSet được chọn
T2  G1 scan roots, copy một số live objects thành công
T3  Destination/to-space không còn đáp ứng lượng copy cần
T4  Evacuation failure: phần chưa copy được giữ tại chỗ
    và reference/region metadata được sửa phù hợp
T5  JVM trở lại application nếu còn có thể tiến triển
T6  Nếu pressure kéo dài -> có thể cần Full GC
```

Không suy rằng GC failure ở T4 lập tức crash JVM hoặc luôn phải mở một Full GC ngay trong cùng pause. **Evacuation failure**, **Full GC** và **OutOfMemoryError** là các biến cố khác nhau.

## 11. Vì sao evacuation failure xảy ra khi heap chưa báo đầy 100%?

Các nguyên nhân có thể cùng xuất hiện:

1. **Live set/survival cao:** phải copy nhiều bytes hơn so với mô hình GC dự đoán.
2. **Old occupancy cao:** nhiều old regions đã giữ dữ liệu, làm free destination regions giảm.
3. **Marking/reclamation quá muộn:** concurrent marking chưa xong để bắt đầu mixed collections, nên old garbage chưa được reclaim đủ nhanh.
4. **Humongous object pressure:** nhiều vùng old bị humongous objects giữ; phần tail waste làm usable region space thấp hơn kỳ vọng.
5. **Region fragmentation:** các free runs đủ cho ordinary destination allocations có thể khác yêu cầu contiguous regions của humongous allocation; hai dạng áp lực cùng giảm lựa chọn của allocator.
6. **Allocation spikes:** tốc độ application tạo objects tăng mạnh hơn dự báo.
7. **Promotion pressure:** nhiều young survivors cần chỗ ở old.
8. **Heap sizing quá chặt:** application live set gần heap maximum, thiếu khoảng đệm cho GC và concurrent work.
9. **Reserve/ergonomics không phù hợp workload:** pause goal, adaptive IHOP hoặc free-region reserve chưa phản ánh bursts.
10. **Container/native pressure:** giới hạn tài nguyên OS/container có thể làm heap expansion hoặc runtime progress gặp khó, nhưng **đây không đồng nghĩa mọi OOMKilled đều do G1 to-space**.

Một con số `heap max - used` trên dashboard chỉ là tổng dung lượng. Nó không cung cấp ngay **free destination regions** hay lịch trình reclaim của collector.

## 12. `G1ReservePercent` giúp gì?

`-XX:G1ReservePercent=N` liên quan đến lượng heap mà G1 cố dự trữ dưới dạng **false ceiling** để giảm nguy cơ allocation/promotion/to-space failure.

Ví dụ lệnh thử nghiệm:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC \
  -XX:G1ReservePercent=15 -jar app.jar
```

Đây không phải 15% physical RAM mới được cấp ngoài `-Xmx`. Vùng dự phòng thuộc **heap management policy**, có thể làm giảm effective headroom mà application được khuyến khích dùng trước khi GC phản ứng.

**Trade-offs:**

- Dự phòng nhiều hơn có thể giảm nguy cơ thiếu destination cho một số patterns.
- Nhưng phần heap khả dụng để application tích lũy objects theo policy sẽ bị bó lại sớm hơn; điều này có thể làm GC chạy nhiều hơn nếu tổng heap không đổi.
- Thay đổi reserve có thể tương tác với **adaptive IHOP** và G1 heuristics.
- Không chọn giá trị chỉ vì thấy một cảnh báo; đo old occupancy, survived bytes, to-space failure frequency và throughput/p99 pauses.

Nếu toàn bộ **live data đã gần bằng heap maximum**, chỉnh reserve không tạo thêm physical heap capacity. Cần giảm retention/peak working set, điều chỉnh workload hoặc cân nhắc sizing heap/container sau khi chứng minh nhu cầu hợp lệ.

## 13. Full GC trong G1 là gì?

Khi G1 không còn đủ khả năng tiến triển bằng young/mixed collections và concurrent marking/reclamation, nó có thể chuyển sang **Full GC** như một phương án dự phòng.

Trong Java 17 G1, Full GC có thể thực hiện **in-place compaction trên phạm vi toàn heap** với stop-the-world pause lớn so với collection thông thường. Mục tiêu là reclaim những objects thực sự dead và tổ chức lại những vùng được phép thu gọn để tạo chỗ tiếp tục allocation.

**Full GC không phải “GC chạy nhanh hơn và xóa nhiều hơn một chút”.** Nó có thể:

- Duyệt liveness của lượng dữ liệu lớn hơn nhiều CSet thông thường.
- Tốn thời gian cập nhật/move/reorganize objects và metadata.
- Chặn application threads lâu hơn, tác động lớn tới tail latency.
- Vẫn **không thu hồi** được objects còn strongly reachable, dù nghiệp vụ đã hết cần.
- Vẫn **không bảo đảm** giải quyết một humongous contiguous-region allocation nếu các regions cần thiết không thể tạo ra trong tình huống đó.

### Full GC có luôn theo sau evacuation failure không?

**Không.** Tài liệu G1 Java 17 nêu G1 có thể tiếp tục chạy sau một evacuation failure nếu còn đủ memory và concurrent reclamation sớm giúp thu hồi được vùng trống. Full GC thường xuất hiện khi điều kiện xấu kéo dài hoặc allocation failure không còn đường tiến triển thích hợp.

### Full GC không luôn là dấu hiệu memory leak

Những nguyên nhân khác gồm:

- Heap genuinely too small cho legitimate live set/peak concurrency.
- Humongous allocation cần contiguous regions mà heap hiện không thể cung cấp.
- Concurrent marking không hoàn thành đủ sớm.
- Application hoặc công cụ chẩn đoán gọi `System.gc()` tùy flags.
- Bị cấu hình GC/logging hoặc workload burst quá nặng làm collector không giữ được reserve.

Cần đọc **GC cause** và **timeline**. Chỉ khi heap dump/path-to-GC-roots và post-GC live-set trend cho thấy object không còn giá trị vẫn được giữ mới nên kết luận logical memory leak.

## 14. Ba sự kiện khác nhau trên timeline

| Sự kiện | Đối tượng trực tiếp | Dấu hiệu chính | Có chắc Full GC ngay? |
| --- | --- | --- | --- |
| **Humongous allocation** | Một object size ≥ nửa region, cần contiguous old regions | `Humongous regions` tăng; đôi khi Concurrent Start | Không |
| **Evacuation failure** | Copy survivors/living objects của CSet thiếu destination | `to-space exhausted`/evacuation failure logs | Không |
| **Full GC** | Thu gom/compact phạm vi toàn heap theo policy fallback hoặc cause khác | `Pause Full` / compaction pause; pause dài | Bản thân là Full GC |

Một humongous burst có thể thúc đẩy marking sớm, giữ nhiều old regions, làm free headroom giảm, khiến G1 gặp to-space pressure. Nhưng đây chỉ là **một chuỗi nhân quả khả dĩ**, không phải quy luật “A ⇒ B ⇒ C”.

### Ví dụ mô hình không được nhầm

```text
Trường hợp A:
  Nhiều humongous byte[] được tạo nhưng bỏ sớm.
  Eager reclaim/cleanup kịp thời.
  => Có thể không hề evacuation failure hay Full GC.

Trường hợp B:
  Không có humongous object nào đáng kể.
  Cache giữ nhiều live objects; survivor/promotion cao.
  => Vẫn có thể thiếu to-space và Full GC.

Trường hợp C:
  Humongous allocations cần 5 contiguous regions,
  nhưng longest free run chỉ là 3 regions.
  => Có thể trigger GC/Full GC dù tổng free >= 5 regions.
```

## 15. Java 17: tính free-region runs bằng chương trình độc lập

Tạo file **`RegionRunDemo.java`**:

```java
public class RegionRunDemo {
    static int totalFree(boolean[] free) {
        int count = 0;
        for (boolean value : free) {
            if (value) {
                count++;
            }
        }
        return count;
    }

    static int longestRun(boolean[] free) {
        int current = 0;
        int best = 0;
        for (boolean value : free) {
            if (value) {
                current++;
                best = Math.max(best, current);
            } else {
                current = 0;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        boolean[] free = {
                true, true, false, true,
                false, false, true, true, true, true,
                false, true, true
        };

        int needed = 5;
        System.out.println("totalFree=" + totalFree(free));
        System.out.println("longestRun=" + longestRun(free));
        System.out.println("needed=" + needed);
        System.out.println("contiguousEnough=" + (longestRun(free) >= needed));
    }
}
```

```bash
javac --release 17 RegionRunDemo.java
java RegionRunDemo
```

**Stdout chính xác:**

```text
totalFree=9
longestRun=4
needed=5
contiguousEnough=false
```

Chương trình mô phỏng **availability của contiguous regions** bằng `boolean[]`; nó **không** đọc free-region list của G1 trong runtime. Có tổng 9 vùng rảnh nhưng free run dài nhất chỉ có 4, nên không xếp được yêu cầu 5 vùng liên tiếp trong mô hình. Các vùng mà G1 thực sự sử dụng có policy và metadata phức tạp hơn phép kiểm tra này.

## 16. Java 17: tạo áp lực humongous để quan sát GC logs

Tạo file **`HumongousPressureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HumongousPressureDemo {
    private static final int CHUNK_BYTES = 768 * 1024;
    private static final int ROUNDS = 32;
    private static final int PER_ROUND = 8;
    private static final int RETAIN_LIMIT = 8;

    static volatile int checksum;

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();

        for (int round = 0; round < ROUNDS; round++) {
            for (int i = 0; i < PER_ROUND; i++) {
                byte[] block = new byte[CHUNK_BYTES];
                block[0] = (byte) round;
                checksum += block[0];

                if (i < 2) {
                    retained.add(block);
                }
            }

            while (retained.size() > RETAIN_LIMIT) {
                retained.remove(0);
            }
        }

        System.out.println("arraysCreated=" + ROUNDS * PER_ROUND);
        System.out.println("nominalAllocatedMiB="
                + (long) ROUNDS * PER_ROUND * CHUNK_BYTES
                / (1024 * 1024));
        System.out.println("retainedArrays=" + retained.size());
        System.out.println("retainedNominalMiB="
                + (long) retained.size() * CHUNK_BYTES
                / (1024 * 1024));
        System.out.println("checksum=" + checksum);
    }
}
```

Biên dịch:

```bash
javac --release 17 HumongousPressureDemo.java
```

Chạy thử trên **HotSpot Java 17** với region size 1 MiB và heap giới hạn đủ cho workload ví dụ:

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -XX:G1HeapRegionSize=1m \
  -Xlog:gc*,gc+heap=info \
  HumongousPressureDemo
```

**Stdout do `System.out` viết, bỏ qua các dòng GC logging phụ thuộc runtime:**

```text
arraysCreated=256
nominalAllocatedMiB=192
retainedArrays=8
retainedNominalMiB=6
checksum=3968
```

Giải thích:

- `768 KiB` là payload của mỗi `byte[]`. Với G1 region 1 MiB, object size của array **lớn hơn** ngưỡng 512 KiB, vì thế rơi vào nhóm humongous trên configuration đã chọn.
- Chương trình tạo **256 arrays**, tổng **192 MiB payload danh nghĩa cộng dồn**, không có nghĩa heap cùng lúc chứa 192 MiB arrays.
- Mỗi round giữ 2 arrays; sau khi vượt 8 thì loại oldest. Kết thúc có 8 arrays trong `retained`, tổng payload của chúng là 6 MiB.
- `checksum` cộng giá trị đầu mỗi array theo `round`, 8 lần mỗi round: `8 × (0 + 1 + ... + 31) = 3968`.
- Vì vòng lặp tạo nhiều humongous arrays trên heap 64 MiB, GC activity có thể quan sát được, nhưng **số GC events, pauses, humongous region count và Full GC không có stdout cố định**.
- Ví dụ **không cố tạo OOME hoặc ép evacuation failure**. Việc chủ động khiến process rơi vào Full GC trong production không phải cách kiểm thử an toàn.

### Điều cần tìm trong log

Tìm các dòng tương tự dạng:

```text
Humongous regions: X->Y
Pause Young (Concurrent Start) ...
Concurrent Mark Cycle
Pause Remark ...
Pause Cleanup ...
```

`X` và `Y` là **biến minh họa**, không phải số đo được bịa từ một phiên chạy cụ thể. Tên events/format có thể khác tùy HotSpot build và logging level. Nếu không thấy một event mong đợi, không nên tự khẳng định “GC không hoạt động”; hãy xem JVM flags, actual region size, và code đã được chạy đúng phiên bản.

## 17. Humongous object phải đủ lớn tính cả array header

Một chương trình Java có thể biết số phần tử `byte[].length` nhưng **không** có standard API trực tiếp lấy exact HotSpot object size cho mọi JVM. Các công cụ như Java agents qua `Instrumentation.getObjectSize` có thể cung cấp size estimate theo API/implementation, nhưng không cần thiết cho bài kiểm thử cơ bản.

Ví dụ:

```java
byte[] imageBytes = new byte[768 * 1024];
System.out.println(imageBytes.length);
```

Đây là **Java snippet**, không phải file độc lập. `length` đúng bằng 786432, nhưng actual heap object size có overhead/alignment. Nếu threshold nằm sát payload, kiểm tra bằng runtime diagnostics thay vì cho rằng `new byte[512 * 1024]` có object size đúng 512 KiB.

### So sánh với object arrays

Một `Object[]` chứa 100.000 references có byte size phụ thuộc compressed oops/reference width, headers và alignment. Mảng có thể humongous dù **các objects mà nó tham chiếu** đều nhỏ; và có thể có `byte[]` humongous dù không có reference elements. Không cộng kích thước tất cả referenced objects rồi cho rằng array object tự nó humongous.

## 18. Full GC có giải quyết được fragmentation của humongous không?

Cần phân biệt **fragmentation của ordinary movable objects** và **contiguous-region pressure của humongous allocations**.

- Trong một số tình huống, Full GC compact những objects di chuyển được và có thể reclaim regions từ objects đã dead, tạo thêm free regions.
- Nhưng G1 Java 17 có những hạn chế đối với humongous objects; tài liệu Oracle 17 nhấn mạnh chúng không được di chuyển như ordinary evacuated objects và có thể còn gây fragmentation.
- Do đó **Full GC không luôn bảo đảm** tạo được một dãy contiguous regions đủ dài cho object humongous mới.
- Nếu đã Full GC mà vẫn không thể tìm dãy regions cần thiết, JVM có thể báo OOME/không thể hoàn tất allocation.

Đây là nguyên nhân không nên nói “heap còn N MiB free thì chắc chắn cấp phát được một `byte[N]`”. Vùng free có thể bị chia thành chunks mà allocator không dùng để tạo object lớn theo chính sách G1.

### Ví dụ hai heap có cùng free bytes

```text
R = 1 MiB, cần 5 contiguous regions

Heap A:
  ..XX.....XXX.
      ^^^^^
  Có free run >= 5 => mô hình đủ chỗ.

Heap B:
  ..XX..XX..XX..
  Có tổng free bytes tương tự,
  nhưng free runs phân tán => có thể không đủ.
```

Sơ đồ chỉ minh họa tính liên tục, không thay thế region allocator metadata của HotSpot.

## 19. Các loại áp lực G1 khác nhau cần xử lý khác nhau

| Triệu chứng | Cơ chế có thể liên quan | Cách xác minh |
| --- | --- | --- |
| `Humongous regions` tăng mạnh cùng large array allocations | Nhiều humongous objects hoặc live retention | GC heap logs, allocation profile, heap dump |
| `Humongous regions` giảm sau pauses/cleanup | Eager reclaim hoặc marking reclaim đã giải phóng được objects | Log trước–sau cùng GC IDs |
| Humongous allocations tạo liên tiếp Concurrent Start | IHOP threshold bị chạm nhiều lần hoặc occupancy old tăng | Concurrent marking timeline, log cause |
| `to-space exhausted` nhưng humongous ít | Survival/promotion cao, old occupancy cao, reserve thiếu | Evacuation phases và survivor/old regions |
| `Pause Full (Allocation Failure)` | G1 không tiến triển đủ qua young/mixed/concurrent reclamation | Full GC cause, event trước đó |
| Full GC mà old/live heap vẫn gần max | Retained graph lớn | Heap dump, retained size, GC roots |
| Full GC mà sau đó còn nhiều regions free nhưng humongous allocation fail | Không tìm được contiguous run thích hợp | Humongous sizes, region fragmentation và logs |
| Container bị OOMKilled nhưng heap used còn thấp | Process/native/cgroup pressure ngoài heap | Cgroup events, RSS, native memory |
| GC pauses dài, không có Full GC | Evacuation/reference-processing work lớn hoặc CPU contention | G1 phase logs, JFR, machine CPU |

**Đừng gộp “GC pressure” thành một nguyên nhân duy nhất.** Hành động hiệu quả phụ thuộc đâu là nút thắt: allocation volume, live data, contiguous old regions, to-space reserve hay tổng process/container memory.

## 20. GC logging và các lệnh chẩn đoán trên Java 17

Khi có server Java thật chạy đủ lâu, mở GC logging có chủ đích:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC \
  -Xlog:gc*,gc+heap=info,gc+phases=debug \
  -jar app.jar
```

Để ghi log ra file có rotation, có thể dùng cấu hình `-Xlog` phù hợp với build; tránh để GC log vô hạn làm đầy disk. Cần giữ đủ thời gian/timestamps để ghép các sự kiện với throughput, latency và OOME.

Các lệnh JDK diagnostic thường dùng:

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
jstat -gc <PID> 1000 5
```

`<PID>` là placeholder process ID của JVM còn sống, không phải literal runnable PID. `app.jar` là placeholder tên application JAR. Lệnh `jstat` trả GC counters/heap utilization mà ý nghĩa có thể khác theo collector, không phải trực tiếp longest contiguous free region run.

### Cụ thể cần ghi lại gì?

- Java version/vendor/build, command-line flags, container limit.
- G1 region size thực tế (log lúc JVM startup).
- Heap used/committed/max và old/young region occupancy theo GC ID.
- `Humongous regions: X->Y` trước–sau pauses.
- G1 concurrent marking Start/Remark/Cleanup.
- Evacuation failure / to-space exhausted events.
- Full GC cause, duration, before–after occupancy.
- Allocation rate theo endpoints/batches; sizes của arrays/objects lớn.
- Post-GC live set/retention qua heap dump khi có nghi vấn.
- RSS/cgroup memory nếu process OOMKilled hoặc `-Xmx` chưa chạm.

### Heap dump khác GC log thế nào?

- **GC log:** thuật toán/collection phase, region occupancy, pauses và các failure events.
- **Heap dump:** object graph, shallow/retained size và paths to GC roots để biết ai giữ large arrays.
- **Allocation profiler/JFR:** method/stack trace đang cấp phát lượng lớn objects; cần lưu ý sampling/overhead và metrics semantics.

Không thể thay thế toàn bộ ba thứ chỉ bằng một con số `used heap`.

## 21. Một quy trình chẩn đoán Full GC trên G1

**Bước 1 — Xác nhận có thật Full GC.** Tìm log `Pause Full` và cause; không coi mọi `Pause Young` là Full GC.

**Bước 2 — Xem 1–5 phút sự kiện trước đó.** Có tăng `Humongous regions`, `to-space exhausted`, old occupancy, Concurrent Start lặp liên tục không? Có `System.gc()`/diagnostic tool ép GC không?

**Bước 3 — Phân biệt hai đường pressure.**

- **Humongous path:** nhiều large allocations, cần contiguous old regions, unused tails và fragmentation.
- **Evacuation path:** nhiều survivors/live bytes trong CSet, destination/to-space không đủ, marking/mixed reclamation chậm.

Chúng có thể đồng thời diễn ra và khuếch đại nhau.

**Bước 4 — Đo allocation sizes.** Nếu nhiều byte arrays vừa quá ngưỡng half-region, có thể cân nhắc giảm một allocation thành các chunks nhỏ hơn, đổi kiến trúc streaming hoặc đo region sizing. Không áp dụng nếu data model thật sự yêu cầu contiguous array.

**Bước 5 — Đo live set và root paths.** Nếu large arrays sống lâu do cache/request retention, GC flags không thể thu hồi chúng. Dùng heap dump và lifecycle analysis để sửa owner.

**Bước 6 — Kiểm tra marking cycle.** Marking bắt đầu đủ sớm để mixed collections reclaim old regions không? Adaptive IHOP có dự báo tốt trong burst pattern không?

**Bước 7 — Kiểm tra heap/GC reserve.** Free regions đủ cho evacuation/promotions không? Có thể cần tăng `-Xmx`, đổi reserve policy hoặc giảm peak concurrent workload — nhưng phải cân nhắc cgroup/native budget.

**Bước 8 — Thử từng thay đổi có đo lường.** Một thay đổi mỗi lần, chạy cùng workload, so before–after humongous region count, Full GC frequency, p99 pause, throughput, RSS và GC CPU.

**Bước 9 — Xác nhận regression.** Sau fix, large object count ổn định, không còn `to-space exhausted` trong điều kiện tải đã gây lỗi, Full GC không xuất hiện ngoài tình huống đã được giải thích.

**Bước 10 — Ghi rõ điều còn chưa chắc chắn.** Chỉ kết luận “đã hết memory leak” khi evidence về retained graph/lifecycle và theo dõi đủ dài hỗ trợ, không chỉ do một lần load test không OOME.

## 22. Ưu tiên sửa ứng dụng trước khi tinh chỉnh GC flags

### Giảm số large heap allocations

- **Streaming** thay vì đọc cả file/request vào một `byte[]` duy nhất khi semantics cho phép.
- Chia batch thành các chunks hợp lý, nhưng đừng tạo quá nhiều object nhỏ gây overhead không cần thiết.
- Sử dụng `InputStream`/`OutputStream` APIs để xử lý incremental khi có thể.
- Tránh `toByteArray()`/copies không cần thiết trong hot paths nếu payload rất lớn.
- Tránh cấp một `Object[]` có capacity vượt xa số entries dùng thực tế.
- Cân nhắc backpressure/giới hạn concurrency cho những batch giữ đồng thời nhiều buffers.
- Nếu buộc cần một large array, xét khoảng peak working set và memory budget thay vì ép chia.

### Giảm thời gian giữ large arrays

- Xóa entries khỏi caches đúng TTL/eviction policy.
- Hủy subscriptions/listeners giữ object graph chứa large arrays.
- Xóa `ThreadLocal` values khi task/request kết thúc.
- Dừng giữ batch buffers trong static fields/queues sau khi job hoàn thành.
- Đóng resources không còn dùng; nhớ Java heap reference removal không tự bảo đảm native resource closure.

### Cân nhắc ngoài-heap đúng trường hợp

Direct buffers hoặc memory-mapped files có thể giảm một số **Java heap humongous allocations**, nhưng:

- Chúng vẫn tiêu thụ native/process/cgroup memory.
- Wrapper/cleaner/lifecycle phải được quản lý đúng, tránh native leaks.
- Chúng không tự miễn phí, không tự làm throughput tốt hơn trong mọi workload.
- Một hệ thống đang container OOMKilled vì tổng memory không thể giải quyết chỉ bằng “chuyển sang off-heap” mà không có budget mới.

## 23. Khi nào cân nhắc `G1HeapRegionSize`, `G1ReservePercent` và IHOP?

| Tình huống có evidence | Hướng thử | Trade-off/chú ý |
| --- | --- | --- |
| Nhiều objects quanh threshold half-region | Thử region size lớn hơn trên đúng heap/JDK | G1 granularity, pause predictability, tail waste |
| Evacuation failure và thiếu destination headroom | Đánh giá reserve, total heap và live set | Reserve giảm effective allocation capacity |
| Old occupancy tăng nhanh, marking không kịp | Đánh giá adaptive IHOP, marking start timing, concurrent threads | Concurrent GC dùng CPU; cấu hình sớm quá cũng tốn |
| Full GC do large retained objects | Giảm retention/caches, cải thiện lifecycle | Tuning GC không giải quyết strong reachability |
| Burst tạo quá nhiều humongous arrays | Streaming, chunking, bounded concurrency | Code complexity và memory copies khác |
| Full GC sau allocation failure dù heap max chưa chạm | Đọc fragmentation/region topology, GC cause | Không đánh đồng free tổng và contiguous space |

**Tránh “chữa bằng một flag” khi chưa biết ràng buộc.** Ví dụ tăng `G1HeapRegionSize` có thể làm nhiều arrays trước kia humongous trở thành non-humongous, nhưng những arrays lớn hơn hoặc nhu cầu heap khác vẫn có thể gây fragmentation/evacuation pressure.

### Thứ tự tuning hợp lý

1. Xác minh GC mode/version và tính đúng của observability.
2. Tối ưu allocation sizes/retention nếu có bug rõ ràng.
3. Kiểm tra peak memory/concurrency/budget.
4. Thử heap sizing/reserve/region size khi có bằng chứng.
5. Đo lại latency/CPU/throughput/memory; rollback nếu trade-off xấu.

## 24. Mười sáu lỗi suy luận thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Humongous nghĩa object > 1 GiB” | Trong G1 ngưỡng liên quan **một nửa region**, thường rất thấp hơn 1 GiB |
| “Humongous là mọi object lưu trên old generation” | Humongous là phân loại theo size; old còn chứa objects thường |
| “Một humongous object dùng đúng kích thước bytes của nó” | Dùng số nguyên **contiguous regions**; vùng cuối có unused tail |
| “Tổng free regions đủ là cấp được bất kỳ large object” | Cần **contiguous run** thích hợp |
| “Humongous luôn nằm trong Eden trước rồi mới lên old” | G1 cấp trực tiếp vào old humongous regions |
| “Humongous object luôn cần Full GC mới reclaim” | Có marking cleanup và eager reclaim trong những điều kiện phù hợp |
| “Mọi primitive array được eager reclaim ngay khi scope kết thúc” | Reachability/GC phase quyết định; không có deadline như vậy |
| “G1 young GC luôn move humongous objects” | Humongous được xử lý đặc biệt, không theo normal CSet evacuation |
| “Evacuation failure nghĩa GC làm hỏng Java reference” | G1 fallback vẫn phải bảo toàn reference correctness |
| “To-space exhausted nghĩa heap used 100%” | Thiếu **destination capacity**, có thể trước khi metric báo max |
| “Evacuation failure luôn kích hoạt Full GC tức thì” | JVM có thể tiếp tục và reclaim trong chu kỳ về sau |
| “Full GC nghĩa mọi object đã được move và không còn fragmentation” | Không được bảo đảm, đặc biệt với humongous region constraints |
| “Full GC đồng nghĩa memory leak” | Có thể do live set hợp lệ, allocation burst, fragmentation hoặc external GC request |
| “`G1ReservePercent` cấp thêm memory ngoài `-Xmx`” | Là policy dự phòng trong heap, không tăng total heap capacity |
| “Tăng region size luôn tối ưu” | Có trade-offs và các size distribution khác nhau |
| “Tăng `-Xmx` luôn sửa lỗi” | Không sửa giữ sống vô hạn và phải cân nhắc container/native memory |

## 25. Câu hỏi tự kiểm tra

**Câu 1:** Với G1 region size 1 MiB, object có **tổng kích thước** 600 KiB có là humongous không?

**Có.** Ngưỡng là 512 KiB, và object 600 KiB dùng một humongous region (với unused tail).

**Câu 2:** Object tổng size 1,25 MiB trong region 1 MiB cần bao nhiêu regions, tail waste bao nhiêu?

**Hai regions**; mô hình unused tail là 0,75 MiB.

**Câu 3:** Heap có 20 free regions, nhưng free run dài nhất là 3. Có đủ cấp humongous object cần 5 contiguous regions ngay không?

**Không** trong bố cục mô phỏng ấy; tổng free không thể thay thế contiguous run.

**Câu 4:** Tại sao nhiều short-lived `byte[]` vẫn có thể gây old occupancy pressure trong G1?

Chúng có thể được cấp trực tiếp vào old humongous regions. Reclaim không nhất thiết đồng bộ với thời điểm ứng dụng bỏ references.

**Câu 5:** Evacuation failure là thất bại của mọi Java objects hay thất bại copy theo collection plan?

Là **không đủ to-space để copy tất cả objects dự định evacuate**; JVM vẫn phải bảo toàn Java object correctness.

**Câu 6:** Sau một evacuation failure, Full GC có chắc xuất hiện ngay không?

**Không.** G1 có thể cho mutator tiếp tục và hy vọng concurrent reclamation hoàn thành kịp.

**Câu 7:** Tại sao Full GC vẫn có thể không giải quyết một humongous allocation?

Vì fragmentation và hạn chế contiguous old regions/humongous movement có thể còn tồn tại, hoặc live data không thể reclaim.

**Câu 8:** `-XX:G1HeapRegionSize=2m` có thể giúp arrays khoảng 768 KiB tránh humongous không?

**Có thể**, vì ngưỡng tăng lên khoảng 1 MiB, nếu array size thật không vượt ngưỡng và flag được JVM chấp nhận.

**Câu 9:** `G1ReservePercent=15` có phải tăng `-Xmx` thêm 15% không?

**Không.** Nó điều chỉnh policy reserve trong heap.

**Câu 10:** Muốn chứng minh memory leak trong ứng dụng nhiều humongous arrays, chỉ nhìn `Humongous regions: X->Y` đủ chưa?

**Chưa.** Cần allocation profile, heap dump, retained owners và liveness/lifecycle evidence.

## 26. Tài liệu tham khảo Java 17

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): regions, humongous allocations, eager reclaim, marking và behavior khi thiếu space.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): phân tích Full GC, `to-space exhausted`, humongous fragmentation và G1 flags.
- [Oracle Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): các collectors và mục tiêu GC.
- [Oracle Java SE 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx`, `-Xms`, `-Xlog` và các flags được hỗ trợ bởi runtime.
- [Oracle Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.flags` và `GC.heap_info`.
- [Oracle Java SE 17 — `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory counters theo collector.
- [Oracle Java SE 17 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): phân biệt used, committed và max.
- [JVMS Java SE 17 — Heap (2.5.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): ngữ nghĩa heap GC tự quản lý.
- [Java SE 17 — `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): reference reachability và quá trình thu hồi.
- [OpenJDK — G1 GC overview](https://wiki.openjdk.org/display/HotSpot/Garbage+First+Garbage+Collector): tài liệu thiết kế và background G1; đối chiếu phiên bản trước khi dùng internal details.

**Ghi nhớ:** G1 coi object có **size từ nửa region** là humongous, cấp bằng **một dãy old regions liên tiếp**, nên có thể phát sinh **unused tail và contiguous-region fragmentation**. Trong các young/mixed pauses, G1 cần **to-space** để copy live objects; thiếu destination thì có thể **evacuation failure**, nhưng VM vẫn phải bảo toàn references và có thể tiếp tục. Nếu old/humongous pressure kéo dài, G1 có thể đi tới **Full GC**, vốn tốn kém và không chắc giải quyết được thiếu contiguous regions. Muốn điều tra đúng phải xem **allocation sizes, live set, GC logs, regions, marking timeline, headroom và retained references**, thay vì chỉ đọc một số heap-used.
