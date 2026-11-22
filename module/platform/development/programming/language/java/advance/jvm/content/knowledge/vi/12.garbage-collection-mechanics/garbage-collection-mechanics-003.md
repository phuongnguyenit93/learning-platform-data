# Giả thuyết thế hệ: đối tượng sống ngắn, già hóa và chuyển thế hệ

## 1. Ý tưởng cốt lõi: “đa số object chết trẻ”

**Giả thuyết thế hệ** (*generational hypothesis*) là một quan sát thực nghiệm trên nhiều loại chương trình: **đa số objects được tạo có thời gian sống ngắn**, trong khi một phần nhỏ được giữ rất lâu. Chúng ta tạo iterator, temporary strings, request objects, buffer hay kết quả tính trung gian rất thường xuyên; nhiều object không còn reachable sau một thao tác ngắn. Các objects như application configuration, shared caches hợp lệ, sessions hoặc indexes có thể sống rất lâu.

**Generational garbage collection** dùng quan sát này để phân vùng quản lý heap theo tuổi thọ tương đối:

1. **Young generation** dành cho những objects mới hoặc chưa sống lâu qua nhiều lần young GC.
2. **Survivor** giữ các objects vẫn còn reachable sau một lần young GC để tránh đưa tất cả lên Old quá sớm.
3. **Old generation** quản lý phần dữ liệu đã sống đủ lâu hoặc được chuyển tới bởi chính sách collector.
4. **Promotion/tenuring** là quá trình đưa object còn sống từ Young sang Old.

Mục tiêu là thu gom thường xuyên ở nơi có nhiều rác và lượng dữ liệu còn sống tương đối nhỏ, thay vì bắt buộc quét mọi object của toàn heap cho mỗi temporary allocation.

**Điều phải nói rõ:** đây là **chiến lược của các garbage collectors**, không phải yêu cầu cứng của Java language hay JVMS rằng mọi JVM đều có Eden, Survivor và Old. **JVMS `2.5.3`** mô tả heap cho class instances/arrays và quản lý bộ nhớ tự động, còn tổ chức generations tùy VM và collector.

### Một giả thuyết chứ không phải lời hứa cho mọi ứng dụng

| Workload / object | Lifetime thường gặp | Ý nghĩa đối với generational GC |
| --- | --- | --- |
| Temporary string/iterator | Rất ngắn | Có thể chết trước young collection đầu tiên |
| DTO phục vụ request | Ngắn | Thường có nhiều cơ hội reclaim ở Young |
| Buffer của tác vụ bất đồng bộ | Trung bình | Có thể sống qua vài young collections |
| Một phần session/cache entries | Trung bình hoặc dài | Có thể già hóa rồi promotion |
| Configuration hoặc shared registry | Dài | Có thể góp vào old live-set |
| Cache không giới hạn giữ data lỗi thời | Quá dài so với nhu cầu thực tế | Có thể gây memory retention/old pressure |

Đây là các ví dụ về xu hướng, **không phải quy luật của class names**. Một `String` cũng có thể sống suốt vòng đời chương trình, còn một object `Session` có thể chết ngay.

## 2. Minh họa phân bố tuổi thọ

~~~text
Số objects có tuổi thọ tương ứng
  ^
  | #################
  | #################
  | ####################
  | ########################           ##
  | ################################ #######
  +---------------------------------------------------->
       rất ngắn              trung bình          rất dài
                         lifetime
~~~

Đây là **minh họa định tính**, không phải biểu đồ thống kê của ứng dụng cụ thể. Nguồn Oracle về *weak generational hypothesis* giải thích phần lớn objects thường chỉ sống trong giai đoạn rất ngắn, dù có workload có phân bố khác đáng kể.

**“Chết” về GC nghĩa là trở nên không còn reachable theo semantics phù hợp**, không phải đơn giản là source Java vừa chạy `obj = null` hoặc đi qua dấu `}`. Nếu object còn trong field, collection, task queue hoặc cache đang reachable, GC vẫn phải giữ nó. Ngược lại, ngay khi object unreachable, GC không nhất thiết chạy lập tức.

## 3. Heap thế hệ: Eden, Survivor và Old

Trong mô hình generational copying collector cổ điển:

~~~text
                    JAVA HEAP
+-------------------------------------------+--------------------+
| YOUNG GENERATION                          | OLD GENERATION     |
|                                           |                    |
| +---------------+ +----------+ +---------+| +----------------+ |
| | Eden          | | Survivor | |Survivor | | | Object đã sống| |
| | Object mới    | | From     | |To       | | | lâu/promoted   | |
| +---------------+ +----------+ +---------+| +----------------+ |
+-------------------------------------------+--------------------+

new -> Eden
Young GC: dead -> reclaim; live -> Survivor hoặc Old
Nhiều collection sống sót -> đủ điều kiện promotion -> Old
~~~

Trong các collector truyền thống dùng hai survivor spaces, chúng có thể đổi vai trò **From/To** sau GC. Nhưng **không phải mọi object phải ghé qua cả hai Survivor spaces** và không phải mọi collector có đúng hai khối Survivor liên tục.

### G1 trong HotSpot JDK 25

G1 là trường hợp cần phân biệt với sơ đồ cũ. G1 chia heap thành những **regions**, gán vai trò như Eden, Survivor, Old hoặc Humongous; các regions cùng generation **không bắt buộc liền kề** trong memory.

~~~text
Heap region sequence minh họa (không phải địa chỉ bắt buộc):

[Old][Free][Eden][Survivor][Eden][Old][Humongous][Survivor]
           \        |        /
                  YOUNG
~~~

Theo **Oracle JDK 25 G1 guide**, young objects còn sống có thể được copy từ Eden/Survivor sang **survivor hoặc old regions tùy tuổi**; những old objects thuộc collection set khi bị evacuate được chuyển theo quy tắc old regions. G1 dùng young-only phases và mixed collections, không đồng nhất young GC với full collection.

**Không đồng nhất “Old” với “Metaspace”:** Old generation trong bài này là **vùng Java object heap** của collector. Metaspace là chi tiết HotSpot về class metadata; chúng không phải một vùng.

## 4. Vì sao thu gom Young thường hiệu quả?

Giả sử có **100.000 objects** vừa được cấp phát và đến thời điểm young GC:

- 96.000 objects không còn reachable;
- 4.000 objects vẫn cần giữ.

Nếu collector chỉ phải copy/evacuate dữ liệu live phù hợp, phần rất lớn memory của nhóm object trẻ có thể được reclaim trong một đợt mà không bắt buộc quét/reclaim toàn bộ Old.

~~~text
100.000 objects mới
       |
       v
   Young GC
    /      \
dead       live
96.000     4.000
  |          |
reclaim   copy/evacuate -> Survivor hoặc Old
~~~

**Những số liệu này hoàn toàn giả định** để minh họa lợi ích của việc nhiều objects chết trẻ. Chi phí GC thực tế còn có roots, reference graphs, remembered sets, synchronization, stop-the-world/concurrent tasks và policies riêng.

Nếu workload có **survival rate cao**, young GC có thể phải copy nhiều live bytes, khiến giả thuyết thế hệ đem lại lợi ích thấp hơn. Vì vậy tuning phải bắt đầu bằng **allocation rate và survival rate đo được**, không phải dựa vào một tỉ lệ đẹp trên slide.

## 5. “Tuổi” của object trong GC là gì?

**Tuổi (age) của object** trong generational GC thường là thông tin về **số lần object đã sống sót qua những young collections phù hợp**. Nó **không phải** số giây/phút kể từ lúc `new`, không phải số vòng lặp hoặc số lần method được gọi.

Một diễn tiến minh họa:

~~~text
Lúc tạo X trong Eden:          age ~ 0
Young collection #1: X live -> Survivor, age tăng
Young collection #2: X live -> Survivor/Old, theo policy
Young collection #3: X live -> có thể promotion nếu đạt threshold
Old generation:             X vẫn có thể chết và được GC thu hồi sau
~~~

**Không được suy** “sau đúng 3 young collections mọi object đều chuyển Old”: ví dụ trên cố tình không gán threshold cố định. Số lần tăng age, thời điểm promotion và cách biểu diễn tuổi phụ thuộc collector.

### Phân biệt tuổi tính theo GC và thời gian đồng hồ

~~~text
Object A: sống 30 phút nhưng không có young GC trong thời gian đó.
Object B: sống 2 giây nhưng workload tạo nhiều temporary objects,
          làm xảy ra nhiều young collections và B sống qua tất cả.

B có thể đã tích lũy age nhiều hơn A theo chính sách GC.
~~~

Đây là tình huống khái niệm; thời gian A/B không dự đoán được object location cụ thể.

| Khẳng định | Đúng không? |
| --- | --- |
| “Object sống 10 phút chắc chắn ở Old” | **Không** |
| “Object mới vài mili giây không thể được promotion” | **Không**, có trường hợp special policy/pressure |
| “Một object được promotion sẽ không còn bị GC” | **Sai**, Old vẫn được thu |
| “Tuổi tăng khi thread gọi `Thread.sleep`” | **Không trực tiếp** |
| “Object trẻ nhưng còn reachable sẽ bị reclaim như rác” | **Sai**, collector phải bảo vệ live objects |

## 6. Promotion / tenuring hoạt động như thế nào?

**Promotion** là chuyển một **live object** từ young generation sang old generation. Tùy collector, việc chuyển có thể được thực hiện qua object evacuation/copy, cập nhật references/barriers hoặc cơ chế tương đương.

Có ba nhóm nguyên nhân quan trọng:

1. **Age threshold:** object đã sống qua đủ những collections theo policy.
2. **Survivor capacity pressure:** survivor destination không đủ chỗ giữ tất cả live young objects; collector có thể promotion sớm.
3. **Collector-specific cases:** large/humongous allocations, GC ergonomics và các đường xử lý riêng có thể không theo hành trình Eden → Survivor → Old cổ điển.

### Ví dụ ngưỡng tuổi bằng 4 (chỉ để học)

| Sự kiện | Tuổi minh họa | Vị trí có thể có |
| --- | ---: | --- |
| Vừa tạo | 0 | Eden |
| Sống qua young GC 1 | 1 | Survivor |
| Sống qua young GC 2 | 2 | Survivor |
| Sống qua young GC 3 | 3 | Survivor |
| Sống qua young GC 4, thỏa threshold 4 | 4 | Old |

**Ngưỡng 4 là giả định cho ví dụ**, không phải giá trị mặc định của G1. Trong runtime thật, survivor pressure hoặc những quyết định policy khác có thể chuyển object sớm hơn.

### MaxTenuringThreshold có phải “đúng N lần GC”?

**Không.** Với các HotSpot collectors sử dụng age-based tenuring, cờ `-XX:MaxTenuringThreshold` là một **giới hạn trên cho ngưỡng** phù hợp, không buộc mọi object phải chờ đúng bằng giá trị ấy. Collector có thể chọn một **desired tenuring threshold** thấp hơn theo survivor occupancy và age distribution.

Ngoài ra, những collectors khác nhau có cơ chế tenuring và flags khác nhau. Một giá trị ở `-XX:+PrintFlagsFinal` không phải lời hứa rằng mọi object đều sống qua chừng ấy GC mới promotion.

## 7. Survivor space/region, dynamic threshold và promotion sớm

Giả sử tại young GC, tổng live young data cần giữ là 120 MiB nhưng phần survivor destination dự kiến chỉ đủ 32 MiB.

~~~text
Young live data:     120 MiB
Survivor capacity:    32 MiB
--------------------------------
Phần không phù hợp Survivor có thể cần vào Old hoặc
đi đường collector-specific khác.
~~~

Đây là số giả định. **Survivor không đủ không đồng nghĩa JVM lập tức OOME**: collector có thể promotion hoặc xử lý allocation qua đường khác nếu tổng heap/Old còn khả năng đáp ứng.

**Premature promotion** là chuyển nhiều objects sang Old trước mức age mong muốn, ví dụ do survival rate cao hoặc survivor không đủ. Tác động có thể gồm:

- Old occupancy tăng;
- tăng chi phí marking/mixed/old collection;
- những object tuổi trung bình chết trong Old trước khi chu kỳ Old reclaim phù hợp;
- tăng memory pressure và khó đáp ứng mục tiêu pause time.

**Không tự động kết luận đây là lỗi của collector.** Đôi khi promotion sớm là quyết định cần thiết để bảo đảm allocation progress, và điều chỉnh một flag không thay đổi profile sống của object thực tế.

## 8. Cross-generation references: Old → Young

Nếu collector chỉ tập trung young objects, nó vẫn phải nhận ra **Old object đang giữ Young object**:

~~~text
OLD OBJECT                              YOUNG OBJECT
+----------------+                     +-----------------+
| SessionManager | ------------------> | NewSession      |
| currentSession |                     | still live      |
+----------------+                     +-----------------+
~~~

Young object **không được phép bị reclaim** vì một old object đang reachable trỏ tới nó. Để tránh phải duyệt toàn bộ old heap mỗi lần young GC, collector có các cơ chế như:

- **Write barriers**: JVM/JIT ghi nhận thông tin khi chương trình sửa reference fields.
- **Card table / remembered sets**: metadata giúp tìm những references trỏ tới young/collection set từ ngoài collection set.
- **Root scanning** và graph traversal theo thuật toán collector.

Trong **G1**, remembered sets dùng để ghi nhận vị trí ở ngoài collection set chứa references vào collection set, giúp duy trì chính xác live reachability khi evacuate Young.

**Không nhầm** write barrier với Java `synchronized` hoặc `volatile`. Write barrier là cơ chế implementation của collector; `synchronized`/`volatile` có vai trò thuộc Java Memory Model và điều khiển đồng bộ, dù VM có thể phối hợp nhiều cơ chế dưới machine code.

## 9. Young-only, mixed, old và full GC khác nhau

| Kiểu công việc | Ý nghĩa |
| --- | --- |
| **Young-only collection** | Thu gom young regions theo collection set thích hợp, copy giữ live objects |
| **Concurrent marking** | Xác định old live data/candidates, có các pha chạy đồng thời với ứng dụng tùy G1 |
| **G1 mixed collection** | Bao gồm Young và một số Old regions được chọn dựa trên hiệu quả reclaim |
| **Full GC** | Xử lý toàn heap theo đường collector tương ứng; thường có pause-cost lớn |
| **Generational ZGC/Shenandoah cycles** | Có young/old handling nhưng thuật toán/concurrency/logging khác G1 |

**Young GC không có nghĩa “xóa sạch mọi rác của JVM”**, và **promotion không có nghĩa một Full GC đã diễn ra**. Khi một object được promotion, nó vẫn đang live; về sau nếu trở thành unreachable, Old reclamation phù hợp mới có thể thu hồi.

Theo Oracle G1 tuning guide, G1 có young-only phase, concurrent mark và các mixed collections nhằm lấy lại Old regions hiệu quả. Dòng log “`Pause Young`” vì vậy không được đọc thành “`Full GC`”.

## 10. Ví dụ Java 17+: temporary objects và nhóm được giữ lại

Tạo file **`GenerationalWorkload.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenerationalWorkload {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile Object lastPublished;

    public static void main(String[] args) {
        // Có một nhóm mảng được giữ reachable bởi static list.
        for (int i = 0; i < 16; i++) {
            byte[] array = new byte[4096];
            array[0] = 1;
            RETAINED.add(array);
        }

        int created = 0;

        // Nhiều mảng tạm, chỉ reference cuối gần nhất được giữ bởi
        // volatile field; các mảng trước đó có thể trở thành unreachable.
        for (int batch = 0; batch < 24; batch++) {
            for (int j = 0; j < 8192; j++) {
                byte[] temporary = new byte[1024];
                temporary[0] = (byte) (j & 127);
                lastPublished = temporary;
                created++;
            }
        }

        lastPublished = null;
        System.out.println("temporary-created=" + created);
        System.out.println("retained-count=" + RETAINED.size());
        System.out.println("retained-length=" + RETAINED.get(0).length);

        RETAINED.clear();
        System.out.println("after-clear=" + RETAINED.size());
        System.out.println("gc-timing-not-guaranteed");
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -g GenerationalWorkload.java
java GenerationalWorkload
~~~

**Stdout chính xác trong điều kiện chạy bình thường:**

~~~text
temporary-created=196608
retained-count=16
retained-length=4096
after-clear=0
gc-timing-not-guaranteed
~~~

Vì:

- `24 × 8192 = 196608`;
- Có 16 retained arrays dài 4096;
- `RETAINED.clear()` đặt kích thước list về 0 theo API;
- Không có phép đo GC trong những dòng output trên.

### Ví dụ chứng minh điều gì và không chứng minh điều gì?

**Chứng minh:** chương trình tạo rất nhiều nhu cầu cấp phát tạm thời, đồng thời chủ động giữ một nhóm objects reachable trong list. Sau khi bỏ references từ list, GC **vẫn không có deadline** phải thu hồi objects.

**Không chứng minh:** object cụ thể nào đã được promotion ở lần GC bao nhiêu, current tenuring threshold bằng mấy, số object nằm ở Survivor/Old, hoặc HotSpot có chạy một mã lệnh cấp phát nhất định. Những thông tin đó là collector/runtime-specific.

`lastPublished` là volatile field để tạo đường escape quan sát được cho temporary arrays, hạn chế tối ưu xóa sạch allocations; nhưng đừng suy có tương ứng 1:1 tuyệt đối giữa mỗi biểu thức `new` trong source và một allocation event profiler nhìn thấy, vì JIT/collector có thể tối ưu.

## 11. Quan sát GC trên HotSpot: phải tách program stdout và diagnostics

Thử trên HotSpot (ví dụ JDK 17/21/25 phù hợp):

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc=info GenerationalWorkload
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+heap=info GenerationalWorkload
~~~

Program stdout vẫn có **năm dòng xác định** nêu trên. Nhưng **GC logs không có output cố định**: số GC, timestamps, số regions, bytes trước/sau pause phụ thuộc JDK/heap/JIT/CPU/collector/workload.

Với workload trên, tổng bytes temporary allocations theo logic vượt giới hạn heap 64 MiB trong một lần chạy, nhưng nhiều objects có thể trở nên unreachable và được reclaim; **`-Xmx64m` không phải giới hạn tổng lượng bytes có thể allocate cộng dồn**. Nếu máy/VM không phù hợp, điều chỉnh heap lên mức an toàn hoặc bỏ flags; không cố ép gây OOME trên môi trường dùng chung.

### Đọc G1 region logs

Ví dụ một đoạn **minh họa**, không phải output được bảo đảm:

~~~text
[gc,heap] GC(12) Eden regions: 20->0(15)
[gc,heap] GC(12) Survivor regions: 2->4(5)
[gc,heap] GC(12) Old regions: 10->11
[gc]      GC(12) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

- `Eden regions`: region counts trước/sau collection và mục tiêu phân vùng tiếp theo theo format log.
- `Survivor regions`: lượng regions được gán survivor role thay đổi khi live objects được evacuated.
- `Old regions`: thông tin region count, **không phải số lượng individual objects được promotion**.
- `Pause Young`: nhãn G1 young collection, **không phải Full GC**.

G1 region sizes và vùng Young không nhất thiết nằm liên tiếp trong address space.

## 12. Quan sát tuổi và ngưỡng tenuring

HotSpot unified logging cho phép các tag GC liên quan age trên phiên bản/collector hỗ trợ:

~~~bash
java -Xlog:help
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+age=debug GenerationalWorkload
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc+age=trace GenerationalWorkload
~~~

Có thể thấy:

- **Desired survivor size**: kích thước survivor mà policy nhắm tới.
- **New threshold / desired tenuring threshold**: ngưỡng tuổi hiện hành, có thể thấp hơn maximum.
- **Age distribution**: lượng bytes sống thuộc các nhóm age.
- **Total**: số bytes cộng dồn đến một nhóm age trong mẫu log.

Một output **giả định hoàn toàn để dạy cách đọc**:

~~~text
[gc,age] Desired survivor size 2097152 bytes, new threshold 5 (max threshold 15)
[gc,age] - age   1: 800000 bytes, 800000 total
[gc,age] - age   2: 420000 bytes, 1220000 total
[gc,age] - age   3: 160000 bytes, 1380000 total
~~~

Điều quan trọng:

- `threshold 5` **không** đồng nhất với `max 15`.
- `age 1: 800000 bytes` **không** có nghĩa “800000 objects”.
- Age table đo đặc tính live survivor data theo collector, không chỉ ra source variable nào đã già.
- Nếu một workload ngắn/collector khác không phát sinh các dòng này, kiểm tra `-Xlog:help` và version thay vì bịa logs.

Có thể xem flags:

~~~bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

Tìm `MaxTenuringThreshold`, `TargetSurvivorRatio` và các parameters liên quan trong output phù hợp. Không tự thay đổi production flags chỉ vì một giá trị trông “nhỏ”: adaptive policies có thể đã lựa chọn thích hợp với workload.

## 13. Vì sao Old → Young references làm GC phức tạp hơn?

Tưởng tượng young GC không xử lý Old → Young references:

~~~text
Old Object (reachable) --> Young Object (không có local var nào khác)
~~~

Một thuật toán chỉ thấy young local roots mà quên cross-generation edge có thể kết luận sai Young object là garbage. Vì vậy generational collector phải duy trì metadata/algorithms phát hiện những edges phù hợp.

**G1 remembered sets** ghi nhận những tham chiếu **từ ngoài collection set trỏ vào collection set**, giúp xử lý tập vùng nhỏ hơn toàn heap. Update references có thể dùng write barriers, dirty cards và concurrent refinement tùy collector.

Đó là phần **giá phải trả** để thu gom Young hiệu quả. Không được trình bày rằng young GC là “không cần quan sát Old dưới bất kỳ hình thức nào”.

## 14. Large/humongous objects và những ngoại lệ

Không phải mọi object trải qua đúng hành trình:

~~~text
Eden -> Survivor S0 -> Survivor S1 -> Old
~~~

G1 có **humongous objects** chiếm một số lượng regions theo các quy tắc riêng. Một số large objects/arrays có thể được phân bổ và xử lý trực tiếp trong vùng đặc biệt thay vì bắt đầu bằng Eden rồi increment age thông thường.

Các trường hợp promotion sớm cũng có thể đến từ Survivor capacity; và một optimized method có `new` trên bytecode nhưng JIT escape analysis/scalar replacement loại heap allocation vật lý. Vì vậy **đừng đếm Java `new` statements rồi suy chính xác số object ở Eden hoặc Old**.

## 15. Generational collectors khác nhau không dùng cùng policy

| Collector | Đặc trưng đáng nhớ |
| --- | --- |
| **Serial GC** | Mô hình generational Eden/Survivor/Old tương đối trực quan |
| **Parallel GC** | Generational collector tập trung throughput; có ergonomics/adaptive sizing |
| **G1 GC** | Dùng heap regions, young-only và mixed collection sets, remembered sets |
| **Generational ZGC** | Low-latency concurrent generational collector, policy/barrier/age khác G1 |
| **Generational Shenandoah** | Chế độ generational trên phiên bản/cấu hình phù hợp, nhiều pha concurrent |
| **Non-generational collectors/modes** | Không nhất thiết dùng Young/Old hoặc tenuring giống ví dụ |
| **Epsilon GC** | No-op collector, không reclaim objects; dành cho thí nghiệm chuyên biệt |

Theo các release JDK hiện đại, **ZGC đã có generational mode** và trên JDK 25 dùng generational mode; Generational Shenandoah có trong các bản JDK phù hợp. Tuy nhiên không đồng nghĩa các flags `MaxTenuringThreshold` hoặc logging `gc+age` có ý nghĩa giống nhau trên tất cả những collectors này.

**Không suy từ tài liệu Java 8 rằng G1 của Java 25 phải có hai Survivor spaces vật lý liền kề**. Hãy chọn đúng phiên bản Oracle/OpenJDK GC guide cho môi trường đang chạy.

## 16. Tuning phải dựa trên phân bố lifetime thật

Khi gặp nhiều young GCs hoặc old occupancy tăng nhanh, kiểm tra:

1. **Allocation rate** (bytes/s), **young GC frequency**, pause time, application throughput và heap size.
2. **Survival rate** qua young collections và **promotion rate**.
3. **Old live-set** sau các old/mixed collections; có đang tăng theo tải tương đương không?
4. **Survivor occupancy** và **desired tenuring threshold** qua age logs.
5. **Object graph và owners**: cache, long-lived sessions, queues, thread-locals, listeners, unbounded maps.
6. **Humongous allocation**/collector-specific constraints.
7. **Phiên bản JDK/collector/flags** và khác biệt khi thử cấu hình.

Một bảng trade-offs:

| Thay đổi | Lợi ích có thể | Rủi ro |
| --- | --- | --- |
| Young capacity lớn hơn | Có thể giảm số young GCs | Có thể tăng live bytes cần xử lý; Old capacity giảm nếu heap fixed |
| Survivor capacity lớn hơn | Giảm promotion sớm trong một số trường hợp | Lấy bớt young capacity dành cho Eden |
| Tenuring threshold khác | Ảnh hưởng thời gian young objects chuyển Old | Có thể tăng copy cost hoặc old pressure |
| Heap lớn hơn | Thêm allocation headroom | Không sửa retention/leak tự động |
| Giảm object allocations không cần thiết | Giảm GC pressure | Có thể hy sinh code clarity nếu tối ưu thiếu benchmark |
| Giải phóng cache entries đúng lifecycle | Giảm live-set/old pressure | Cần bảo đảm correctness và cache policy |

**Không có “ngưỡng tenuring chuẩn cho mọi ứng dụng”.** Garbage collectors hiện đại có nhiều ergonomic decisions tự động; thay flags chỉ nên thực hiện sau khi đo workload tái tạo tương đương.

## 17. Vì sao promotion rate cao chưa chắc là memory leak?

Nếu ứng dụng có nhiều objects **medium-lived hợp lệ**, chúng có thể sống qua vài young GCs rồi lên Old trước khi trở thành unreachable. Ngoài ra, Survivor capacity pressure có thể promote sớm. Vì vậy promotion rate cao **không tự chứng minh leak**.

Memory leak về mặt ứng dụng thường là **retention không mong muốn**:

~~~text
Static Cache -> Map -> Session -> Large Object Graph
                     ^
              request đã kết thúc,
              nhưng cache vẫn giữ reference
~~~

Trong tình huống đó, GC **không thể thu hồi object còn reachable** chỉ vì nó ở Young hay Old. Cách sửa là làm rõ ownership/eviction, xóa entries không cần, unregister listeners hoặc đóng resources đúng lifecycle. Không có `MaxTenuringThreshold` nào giúp GC xóa an toàn một object vẫn còn được chương trình sử dụng.

Khi đánh giá leak, xem **live-set sau nhiều GC cycles** và các đường từ GC roots tới retained objects, không chỉ nhìn tổng allocated bytes. Một chương trình tạo nhiều temporary objects có thể tạo tổng allocation cực lớn nhưng live-set vẫn nhỏ.

## 18. Những ngộ nhận cần sửa

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Mọi Java object chết trẻ.” | Là xu hướng thực nghiệm trong nhiều workloads, không phải bảo đảm |
| “JVMS bắt buộc có Eden/Survivor/Old.” | Đây là thiết kế GC implementation |
| “Age là số giây kể từ `new`.” | Thường dựa trên survival qua collections |
| “Mỗi young GC mọi live object tăng tuổi đúng một theo mọi collector.” | Phụ thuộc loại collection/policy |
| “`MaxTenuringThreshold=15` buộc đủ 15 GCs.” | Có dynamic threshold, survivor pressure và ngoại lệ |
| “Survivor đầy lập tức gây OOME.” | Có thể promotion hoặc đường xử lý khác |
| “Promotion là thu gom object.” | Promotion **giữ** live object và chuyển generation |
| “Object được promotion sẽ không bao giờ bị GC.” | Old objects vẫn có thể reclaimed về sau |
| “Young GC đồng nghĩa Full GC.” | Young-only không xử lý toàn bộ heap |
| “Old region tăng 1 nghĩa một object được promote.” | Region count không phải object count |
| “G1 có hai Survivor spaces contiguous cứng.” | G1 dùng survivor regions phân bố trong heap |
| “Young GC hoàn toàn không cần xét Old references.” | Cross-generation references phải được bảo vệ |
| “GC tạo ra thread-safety cho các references.” | Không; JMM và đồng bộ là chủ đề khác |
| “`System.gc()` sẽ tăng tuổi/promotion object theo ý muốn.” | Không có guarantee về GC/promotion timing |
| “Mọi collector có cùng age log format/threshold.” | Collector-specific implementation |
| “Promotion rate cao luôn là leak.” | Có thể lifetime profile hợp lệ hoặc premature promotion |
| “Cứ `new` là một vật thể heap thật.” | JIT có thể loại allocation |
| “Chỉnh GC flags đủ sửa static cache leak.” | Không, phải sửa object retention |
| “Generational hypothesis bảo đảm young GC luôn nhanh.” | Phụ thuộc survival rate và heap dynamics |

## 19. Câu hỏi ôn tập có đáp án

**1.** Giả thuyết thế hệ mô tả điều gì?  
**Đáp án:** Trong nhiều workloads, phần lớn objects không sống lâu, tạo cơ sở để thu gom Young thường xuyên.

**2.** Object ở Survivor có nghĩa nó đã tồn tại bao nhiêu giây?  
**Đáp án:** Không thể suy chỉ từ vị trí; age thường theo những lần young collection phù hợp.

**3.** Promotion xảy ra khi nào?  
**Đáp án:** Khi live object thỏa age threshold hoặc các điều kiện survivor capacity/collector policy khác.

**4.** Object ở Old là bất tử?  
**Đáp án:** Không. Nếu không còn reachable, nó có thể reclaimed trong old/mixed/full hoặc collector-specific cycles.

**5.** Vì sao Old → Young reference cần được ghi nhận?  
**Đáp án:** Nếu bỏ sót, young GC có thể thu nhầm Young object vẫn được Old object giữ sống.

**6.** `MaxTenuringThreshold=15` có nghĩa mọi object phải qua đúng 15 collections?  
**Đáp án:** Không; đó là giới hạn chính sách khi collector áp dụng, với desired threshold và các nhánh promotion khác.

**7.** G1 có một Eden vật lý liền kề mọi Survivor regions?  
**Đáp án:** Không. G1 phân vùng heap thành regions có vai trò khác nhau và không bắt buộc liền kề.

**8.** `Old regions: 10->11` cho biết có đúng một object được promotion?  
**Đáp án:** Không. Một region chứa nhiều objects.

**9.** `System.gc()` có bảo đảm tạo young GC và làm một object tăng age?  
**Đáp án:** Không.

**10.** Nếu static cache giữ object quá lâu, sửa gì trước?  
**Đáp án:** Xác định ownership và eviction/release, thay vì chỉ chỉnh tenuring threshold.

**11.** Young allocation rate lớn nhưng Old live-set nhỏ có thể là trường hợp bình thường?  
**Đáp án:** Có, nhiều temporary objects nhanh chết tạo tổng allocated bytes lớn nhưng ít retained objects.

**12.** Tại sao không so G1 age logs trực tiếp với Generational ZGC?  
**Đáp án:** Collector implementations và log semantics khác nhau.

## 20. Nguồn tham khảo đáng tin cậy

- [JVMS Java SE 25 — `2.5.3` Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): heap và storage management, không quy định một chiến lược generations cố định.
- [Oracle Java 8 — Generations / Weak Generational Hypothesis](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/gctuning/generations.html): nguồn kinh điển “most objects die young”; **mô tả layout/collector mang tính lịch sử**.
- [Oracle JDK 25 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): Eden/Survivor/Old regions, age-based promotion, remembered sets, young/mixed phases.
- [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): giải thích cách đọc G1 region logs.
- [Oracle JDK 25 — Factors Affecting GC Performance](https://docs.oracle.com/en/java/javase/25/gctuning/factors-affecting-garbage-collection-performance.html): survivor sizing, thresholds và tuning trade-offs.
- [Oracle JDK 25 — java Command / Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xlog:gc+age=debug/trace` và các flags chẩn đoán.
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): ý nghĩa phân thế hệ trong low-latency ZGC.
- [OpenJDK JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474): chế độ generational ZGC ở releases liên quan.
- [OpenJDK JEP 490 — Remove Non-Generational ZGC](https://openjdk.org/jeps/490): lộ trình loại non-generational mode.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): generational Shenandoah và giới hạn phiên bản.
- [OpenJDK HotSpot — gc_globals.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp): các cờ age/tenuring của HotSpot; mã master có thể khác phiên bản chạy thực.

**Ghi nhớ:** đối tượng mới thường được quản lý ở **Young**; đa số chết trước khi cần giữ lâu; những object còn reachable có thể ở **Survivor**, tăng **GC age**, rồi **promotion** sang **Old** khi policy yêu cầu. **Tuổi không phải thời gian đồng hồ, ngưỡng có thể động, G1 dùng regions chứ không bắt buộc các spaces liền nhau, Old vẫn được GC, và mọi kết luận về performance/retention phải dựa trên dữ liệu workload thật.**