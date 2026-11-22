# Đánh dấu, quét, sao chép và nén: các cách xác định và thu hồi vùng nhớ trong JVM

Garbage Collector (GC) giúp Java thu hồi vùng nhớ của những object không còn cần được giữ sống theo **reachability**. Tuy nhiên, “GC chạy” không có nghĩa chỉ có một hành động xóa object: một collector có thể **đánh dấu (mark)** object còn sống, **quét (sweep)** các vùng không còn sử dụng, **sao chép (copy/evacuate)** object sống sang vùng khác, và/hoặc **nén (compact)** các object sống để giảm phân mảnh. Những thao tác có mục đích khác nhau và thường được kết hợp.

Bài giải thích chính xác các thuật toán cơ sở và tác động lên **liveness, allocation, fragmentation, reference updating, pause time, throughput**. Sau đó đối chiếu với cách HotSpot Java 17 sử dụng các cơ chế này ở **Serial, Parallel, G1, ZGC và Shenandoah**. Mục đích không phải suy ngược rằng “mỗi collector bằng đúng một thuật toán”, mà hiểu vì sao các collector lựa chọn phối hợp nhiều bước.

## 1. Hai câu hỏi khác nhau: còn sống hay cần chuyển chỗ?

GC phải giải quyết hai vấn đề liên quan nhưng không đồng nhất:

1. **Liveness/reachability:** object nào còn có thể được chương trình truy cập qua các reference hợp lệ và phải được bảo toàn?
2. **Reclamation/placement:** sau khi biết object nào cần giữ, làm sao tái sử dụng vùng nhớ bỏ trống và bố trí các object còn sống sao cho những lần cấp phát sau hiệu quả?

**Mark** chủ yếu giải câu hỏi thứ nhất. **Sweep**, **copy/evacuation** và **compaction** giải câu hỏi thứ hai theo những chiến lược khác nhau. Các thuật toán GC thực tế còn phải xử lý nhiều threads, references, class metadata, Java Memory Model, JNI, vùng nhớ lớn và chi phí runtime.

Giả sử một heap nhỏ đang giữ các object A, B, C, D:

```text
GC roots
   |
   v
   A ---> B ---> C         D (không còn đường từ root)
           ^
           |
           +---- A

A, B, C: reachable theo graph.
D: không reachable từ các roots được xét; có thể thu hồi.
```

Dù vòng tham chiếu xuất hiện trong graph, **tracing GC không coi chu trình là leak tự thân**. Nếu toàn bộ một nhóm object không còn đường đi từ GC roots, collector có thể reclaim nhóm đó. Ngược lại, cache chứa object không còn giá trị nghiệp vụ nhưng vẫn có strong reference từ static root thì GC không được tự coi nó là rác.

### Một số thuật ngữ nền tảng

| Thuật ngữ | Nghĩa trong bài |
| --- | --- |
| **GC root** | Điểm bắt đầu theo dõi reachability, chẳng hạn reference đang sống trong thread frame/VM structures hoặc static references phù hợp |
| **Live/reachable object** | Object cần được bảo toàn theo các quy tắc reachability tại GC phase được xét |
| **Garbage/dead object** | Object không còn reachable theo mô hình tracing và reference-processing tương ứng |
| **Object graph** | Các object là nodes, fields/array entries tham chiếu là edges |
| **Mark bit/mark bitmap** | Metadata dùng ghi nhận object đã được phát hiện còn sống |
| **Free list** | Danh sách/cấu trúc quản lý những khoảng trống có thể cấp phát |
| **Fragmentation** | Tổng dung lượng trống có thể đủ, nhưng bị chia thành các khoảng nhỏ gây khó cấp phát liên tục |
| **Evacuation/to-space** | Di chuyển/copy live objects khỏi một vùng đang collection tới vùng đích |
| **Forwarding information** | Ánh xạ vị trí object cũ sang vị trí mới để tránh copy lặp và giúp cập nhật references |
| **Write/load barrier** | Runtime/JIT instrumentation duy trì tính đúng của marking, remembered sets hoặc relocation |

Đừng đồng nhất **Java object identity** với **địa chỉ bộ nhớ**. Một object có thể đổi vị trí do GC nhưng `a == b` vẫn phải phản ánh cùng identity logic, và các fields phải giữ đúng ngữ nghĩa.

## 2. Reachability: bước quyết định object nào cần giữ

Một tracing collector bắt đầu ở **GC roots**, đi theo những reference edges thích hợp và phát hiện tập objects reachable. Những nguồn roots trong HotSpot thường gồm references còn sống ở **Java thread frames**, registers/JIT metadata, static fields, JNI handles và các cấu trúc runtime cần thiết.

Ví dụ:

```text
Root R1 --> A --> B --> C
            |
            +----> E

Root R2 --> B

D --> F     (không có đường từ roots vào D hoặc F)
```

Nếu chỉ xét **strong reachability** ở ví dụ đơn giản, tập được mark là **{A, B, C, E}**. Hai object D, F không có đường từ roots nên có thể reclaimed. B vẫn là **một object duy nhất**, dù có đường từ R1 và R2.

Trong GC thật còn có các **Reference** types như `WeakReference`, `SoftReference`, `PhantomReference` và quy tắc reference processing; vì vậy mô hình “đi theo mọi reference edge như nhau” chưa đủ cho toàn bộ JDK.

### Marking không nhất thiết đi qua mọi object theo một thứ tự

Các collector có thể thực hiện DFS, BFS, dùng marking stacks/queues, bitmaps, xử lý song song và tận dụng data structures của heap. **Thứ tự duyệt** không làm thay đổi tập reachable đúng, nhưng ảnh hưởng locality, work balancing, pause và concurrency overhead.

**Đã đánh dấu object** cũng không đồng nghĩa “đã thu hồi memory”: marking chỉ xác định một tập cần bảo toàn. Phải có bước reclaim/evacuate/compact hoặc cơ chế tương đương để dung lượng thật sự trở lại allocator.

## 3. Thuật toán đánh dấu (Mark): từ roots tới toàn bộ objects reachable

Mô hình đánh dấu đơn giản:

1. Chuẩn bị trạng thái mark cho các objects thuộc phạm vi GC.
2. Đưa GC roots vào hàng đợi/cấu trúc duyệt.
3. Lặp: lấy một reference, nếu object chưa được mark thì đánh dấu và duyệt các reference fields/array entries thích hợp.
4. Khi không còn node cần xử lý, tập objects đã mark là **live set** theo snapshot/model GC đang sử dụng.
5. Những object chưa mark có thể xử lý bằng sweep hoặc bị loại bỏ gián tiếp khi copying/compaction.

Pseudocode:

```text
mark(roots):
    worklist = roots
    while worklist is not empty:
        object = worklist.remove()
        if object == null or alreadyMarked(object):
            continue
        setMarked(object)
        for ref in strongReferencesFrom(object):
            worklist.add(ref)
```

Đây là **mã giả của tracing strong references**, không phải bộ thuật toán đầy đủ của JDK. GC thực còn có safepoints, object layouts, concurrent updates, reference processing, class unloading và loại roots khác.

### Ba màu: white, gray, black

Mô hình tri-color phổ biến trong giải thích marking:

- **White:** object chưa được phát hiện/đánh dấu.
- **Gray:** đã phát hiện nhưng chưa quét xong outgoing references.
- **Black:** đã quét xong outgoing references trong mô hình đang xét.

```text
Ban đầu:
  roots --> [A:GRAY] --> [B:WHITE] --> [C:WHITE]

Xử lý A:
  [A:BLACK] --> [B:GRAY] --> [C:WHITE]

Xử lý B:
  [A:BLACK] --> [B:BLACK] --> [C:GRAY]

Xử lý C:
  [A:BLACK] --> [B:BLACK] --> [C:BLACK]
```

**White không luôn nghĩa là garbage tại mọi thời điểm**: một object còn white trong lúc marking chưa hoàn tất có thể sẽ được phát hiện. Mô hình tri-color đặc biệt hữu ích để hiểu các **barriers**: khi Java threads sửa object graph đồng thời với marking, collector phải ngăn một live object bị bỏ lỡ.

## 4. Ví dụ Java 17: mô phỏng reachability bằng đồ thị

Tạo file độc lập **`TraceGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class TraceGraphDemo {
    static Set<String> mark(Map<String, List<String>> edges,
                            List<String> roots) {
        Set<String> marked = new HashSet<>();
        Deque<String> pending = new ArrayDeque<>(roots);

        while (!pending.isEmpty()) {
            String node = pending.pop();
            if (marked.add(node)) {
                for (String next : edges.getOrDefault(node, List.of())) {
                    pending.push(next);
                }
            }
        }
        return marked;
    }

    public static void main(String[] args) {
        Map<String, List<String>> graph = new HashMap<>();
        graph.put("A", Arrays.asList("B", "E"));
        graph.put("B", List.of("C"));
        graph.put("C", List.of("A")); // tạo chu trình
        graph.put("D", List.of("F"));
        graph.put("E", List.of());
        graph.put("F", List.of());

        Set<String> live = mark(graph, List.of("A"));
        Set<String> all = new TreeSet<>(graph.keySet());
        Set<String> unreachable = new TreeSet<>(all);
        unreachable.removeAll(live);

        System.out.println("live=" + new TreeSet<>(live));
        System.out.println("unreachable=" + unreachable);
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac --release 17 TraceGraphDemo.java
java TraceGraphDemo
```

**Stdout chính xác:**

```text
live=[A, B, C, E]
unreachable=[D, F]
```

- Marking từ root A đi qua B, C, E; chu trình A→B→C→A không gây lặp vô hạn vì `marked.add(node)` chỉ trả `true` lần đầu.
- D và F nằm trong graph nhưng không reachable từ root A được chọn.
- Đây là **bộ mô phỏng đồ thị**, **không thực hiện GC của HotSpot**. Các objects `HashMap`, `String`, `Set` do chương trình Java này tạo vẫn có reachability thực tế riêng; kết quả chỉ phản ánh quy tắc *mark từ tập roots do ví dụ định nghĩa*.
- Bài học: trước khi reclaim, phải xác định **đường reachable từ roots**, không đếm đơn thuần số object hoặc số reference cycles.

## 5. Mark–Sweep: đánh dấu rồi quét vùng không còn sử dụng

Thuật toán **mark-and-sweep** tách thành hai công đoạn chính:

1. **Mark:** xác định những objects reachable.
2. **Sweep:** duyệt vùng heap/phạm vi collection, nhận diện các allocations không được mark và đưa những khoảng nhớ đó vào free list/cấu trúc quản lý vùng trống; chuẩn bị trạng thái mark cho collection tiếp theo theo cách phù hợp.

Ví dụ một dãy allocations (mỗi ô là một block minh họa):

```text
Trước marking:
| A | B | C | D | E | F | G | H |

Sau marking:
| A*| B | C*| D | E*| F | G | H |
  * = reachable/live; B,D,F,G,H không reachable

Sau sweep:
| A | . | C | . | E | . | . | . |

Các free runs: [1 block], [1 block], [3 blocks].
A, C, E KHÔNG đổi vị trí trong mô hình non-moving mark-sweep.
```

### Ưu điểm

- Không bắt buộc copy các live objects; thuận lợi khi phần lớn heap đang **live**, nếu dùng một phương án non-moving.
- Có thể reclaim dead blocks và tái sử dụng mà không cần thêm một vùng to-space bằng kích thước tương đương toàn collection set.
- Khi object không bị dời, có thể tránh chi phí relocation/reference fix-up của giai đoạn ấy.

### Nhược điểm

- **External fragmentation:** những khoảng trống nhỏ rải rác khiến allocator không tìm được block đủ lớn dù **tổng** free bytes có thể nhiều.
- **Allocation complexity:** có thể cần free lists theo size, coalescing adjacent free blocks hoặc chiến lược allocator khác; không còn chỉ “bump pointer” trên một vùng liên tục.
- **Sweep cost:** cần duyệt allocations/metadata trong scope; nhiều dead blocks có thể làm công việc duyệt và quản lý free list đáng kể.
- **Có thể cần compaction sau đó:** ứng dụng có object lớn hoặc vùng nhớ cần liên tục có thể không sử dụng được dung lượng trống bị chia nhỏ.

Không suy “mark-sweep luôn có pause dài” hay “không thể concurrent”: có các thiết kế concurrent/parallel marking và sweeping. Thuật toán khái niệm **không quyết định duy nhất** cách triển khai lịch GC.

### Khi nào fragmentation thật sự quan trọng?

Giả sử heap mô phỏng có tổng cộng **4 đơn vị trống**, nhưng các free runs chỉ có độ dài 1, 1 và 2. Yêu cầu allocation một object kích thước **3 đơn vị liên tục** có thể **thất bại trong vùng ấy**, dù 4 đơn vị trống trên tổng. GC/allocator có thể tìm region khác, mở rộng heap, trigger collection/compaction hoặc báo lỗi nếu không có phương án.

Điều này khác **internal fragmentation**: cấp một block lớn hơn yêu cầu vì alignment/size classes, khiến phần memory nằm **bên trong block đã cấp** không được dùng hết.

## 6. Mark–Compact: đánh dấu, tính vị trí mới và gom objects sống

**Mark-compact** bắt đầu bằng việc xác định live objects, rồi sắp xếp/di chuyển chúng theo một bố cục đích để tạo những khoảng free lớn và tương đối liên tục.

Một kiểu **sliding compaction** đơn giản:

```text
Trước:
| A*| . | C*| . | E*| . | . | . |
   ^      ^      ^
   live objects có các vị trí cũ khác nhau

Sau compact:
| A | C | E | . | . | . | . | . |
            ^  vùng free liên tục ở cuối

Mapping minh họa:
  A: old slot 0 -> new slot 0
  C: old slot 2 -> new slot 1
  E: old slot 4 -> new slot 2
```

Đối với object graph thật, một collector compaction có thể cần:

1. Xác định live objects và kích thước từng object.
2. Tính **destination address** và lưu forwarding/offset metadata phù hợp.
3. **Cập nhật references** từ GC roots, object fields, array elements và VM structures để chúng trỏ tới đích mới.
4. Di chuyển dữ liệu object theo thứ tự an toàn, bảo toàn Java object identity, monitor state, hash/metadata và field values.
5. Công bố vùng trống mới cho allocator, đồng bộ hóa và kết thúc phase theo invariant collector.

**Mark-compact không nhất thiết có một lần sweep đầy đủ trước khi copy**. Đó là nhóm thuật toán: mark xong có thể xác định destinations rồi slide/copy và lập vùng free, không buộc chạy riêng một phase free-list sweeping giống mark-sweep.

### Ưu điểm và trade-offs

- **Giảm external fragmentation:** tạo free regions lớn, giúp allocation nhanh và đều hơn.
- **Locality:** live objects được gom có thể cải thiện locality/TLB/cache behavior trong những trường hợp thích hợp.
- **Có chi phí relocation:** di chuyển bytes live và cập nhật references/metadata; trong một số workloads, đắt hơn non-moving sweep.
- **Pause/concurrency:** một implementation STW compact toàn heap có thể có pause lớn; những thuật toán concurrent/incremental làm giảm pause bằng cách bổ sung barriers và phức tạp.
- **Độ phức tạp thực** phụ thuộc live bytes, số reference edges, layout, barriers, parallelism và phần heap được chọn.

Đừng cho rằng mọi collector có nhãn “compacting” thực hiện **cùng một sliding algorithm**, hoặc rằng compact chỉ dùng khi heap hoàn toàn đầy.

## 7. Copying/Evacuation: giữ live objects bằng cách chuyển sang vùng đích

Một **copying collector** chọn một vùng nguồn (from-space/collection set), tìm các object còn sống và **copy** chúng sang **to-space/destination**. Sau đó, vùng nguồn có thể được reclaimed tương đối nhanh nếu toàn bộ references hợp lệ đã được điều phối.

```text
From-space trước GC:
| A*| B | C*| D | E*| F | ... |
   |      |      |
   +------+------+
          |
          v
To-space sau copying:
| A | C | E | free ........ |

From-space có thể được tái sử dụng khi relocation hoàn tất an toàn.
```

Cơ chế rất quen thuộc là **forwarding**:

```text
Root R1 ----> A_old
Root R2 ----> A_old

Lần đầu gặp A_old:
  copy A_old -> A_new
  forwarding(A_old) = A_new

Lần thứ hai gặp A_old:
  thấy forwarding đã tồn tại, KHÔNG tạo thêm một Java object A mới
  cập nhật/chuyển hướng R2 tới A_new

Cuối phase:
Root R1 ----> A_new
Root R2 ----> A_new
```

Về mặt Java, hai roots vẫn trỏ tới **cùng object A**. Forwarding pointers hay forwarding tables là **implementation details**, không phải Java fields được phép đọc trong source.

### Vì sao copying thu hút nhiều collectors?

- **Allocation sau copying** thường có thể dùng bump pointer trong vùng đích có không gian liên tục, giảm overhead allocator.
- Khi tỷ lệ object chết cao, lượng bytes phải copy là **live bytes**, thường ít hơn total allocated bytes của vùng.
- To-space có thể cho bố cục ít phân mảnh sau mỗi evacuation.
- Hợp với mô hình **generational hypothesis**: phần lớn objects được tạo trong thời gian ngắn có vòng đời ngắn, vì vậy young generation có live set tương đối nhỏ trong nhiều workloads.

### Nhược điểm và giới hạn

- Cần **đủ destination space** để đưa các live objects tới nơi ở mới; đây là tài nguyên không thể bỏ qua.
- Khi phần lớn objects còn sống, **copy cost** và destination space có thể rất lớn.
- Cần scan/cập nhật references, quản lý forwarding, synchronization giữa GC workers và tương tác với runtime/JIT/JNI.
- “Copy mọi object” không áp dụng: thường chỉ objects trong selected regions/young generation được xử lý; objects ở nơi khác có thể không đổi.
- Khi thiếu to-space, collector phải có cơ chế fallback/failure handling. Không thể giả định mọi evacuation luôn thành công.

Một copying collector kinh điển có thể dùng **hai semispaces**, luân phiên vai trò from/to. **G1 không phải mô hình hai nửa heap cố định**; nó chọn nhiều regions và evacuate tới những regions phù hợp. Đừng đồng nhất mọi copying implementation với “chỉ sử dụng 50% heap”.

## 8. Bảng đối chiếu ba cách thu hồi chính

| Thuộc tính | Mark–Sweep | Mark–Compact | Copy/Evacuation |
| --- | --- | --- | --- |
| Phân biệt live/dead | Mark reachable objects | Mark reachable objects | Discover/trace reachable objects trong source set |
| Xử lý dead space | Add free blocks vào allocator/free lists | Gom live objects, tạo free span(s) | Reclaim vùng nguồn sau khi evacuate |
| Object sống có bắt buộc move? | **Không** trong mô hình non-moving | **Có thể** move | **Có thể** move khi thuộc vùng được evacuate |
| External fragmentation | Có thể còn đáng kể | Thường giảm mạnh | Ít hơn trong vùng đích mới gom |
| Chi phí theo live bytes | Không cần copy live bytes | Có relocation/compaction work | Có copy/evacuation work |
| Extra destination space | Thường không cần equal-size to-space | Không nhất thiết cần full second space | Phải có space để chứa objects được copy |
| Reference fix-up | Không cần vì riêng non-moving sweep | Cần nếu objects move | Cần hoặc dùng forwarding/barriers thích hợp |
| Allocation strategy điển hình | Free lists/size classes | Bump pointer trên vùng free liên tục | Bump pointer trong to-space |
| Workload hợp lý | Live set lớn, hạn chế copy, chấp nhận/kiểm soát fragmentation | Cần chống fragmentation, muốn contiguous allocation | Vùng có nhiều dead objects, như young regions |
| Pause time | Phụ thuộc thiết kế/parallelism | Phụ thuộc amount move và thiết kế | Phụ thuộc live bytes, roots, edges, space, barriers |

**Bảng mô tả nguyên lý**, không phải benchmark hay bảo đảm một collector cụ thể luôn nhanh/chậm hơn collector khác. Một thiết kế hiện đại có thể kết hợp **concurrent mark + region evacuation + occasional full compact**, tùy phase.

## 9. Ví dụ Java 17: mô phỏng sweep và compact trên các slots

Tạo **`SweepCompactToy.java`**:

```java
import java.util.Arrays;

public class SweepCompactToy {
    static String[] sweep(String[] slots, boolean[] live) {
        String[] copy = slots.clone();
        for (int i = 0; i < copy.length; i++) {
            if (!live[i]) {
                copy[i] = null;
            }
        }
        return copy;
    }

    static String[] compact(String[] swept) {
        String[] result = new String[swept.length];
        int destination = 0;
        for (String item : swept) {
            if (item != null) {
                result[destination++] = item;
            }
        }
        return result;
    }

    public static void main(String[] args) {
        String[] slots = {"A", "B", "C", "D", "E", "F"};
        boolean[] live = {true, false, true, false, true, false};

        String[] swept = sweep(slots, live);
        String[] compacted = compact(swept);

        System.out.println("before=" + Arrays.toString(slots));
        System.out.println("swept=" + Arrays.toString(swept));
        System.out.println("compacted=" + Arrays.toString(compacted));
        System.out.println("freeAfterSweep=" + 3);
        System.out.println("largestFreeRunAfterSweep=" + 1);
        System.out.println("largestFreeRunAfterCompact=" + 3);
    }
}
```

```bash
javac --release 17 SweepCompactToy.java
java SweepCompactToy
```

**Stdout:**

```text
before=[A, B, C, D, E, F]
swept=[A, null, C, null, E, null]
compacted=[A, C, E, null, null, null]
freeAfterSweep=3
largestFreeRunAfterSweep=1
largestFreeRunAfterCompact=3
```

**Đây là mô phỏng bố cục**, không phải GC runtime: `String[]` và các String literals thực tế của Java program vẫn được GC quản lý riêng. Các biến `slots`, `swept` và `compacted` là ba Java arrays đang cùng tồn tại tại thời điểm in; không có thao tác di chuyển object vật lý của HotSpot ở đây.

Mô hình cho thấy **tổng số free blocks sau sweep là 3** nhưng bị chia ba vị trí rời rạc; sau compact cùng tổng free bằng 3 nhưng liên tục. Nó cũng cố ý bỏ qua việc thật sự cập nhật object-reference addresses vì các strings A/C/E chỉ là **nhãn block**.

## 10. Update references: di chuyển object không được đổi Java identity

Một object có thể được refer tới từ nhiều chỗ:

- Local variables/operand stacks/JIT registers còn live trong thread frames.
- Static fields của classes có owner còn sống.
- Fields của objects khác trong heap.
- Reference-array elements, collections.
- JNI handles và VM runtime structures.

Khi copy/compact object, GC phải bảo đảm mọi đường tham chiếu **còn sử dụng được** đi tới logical object đúng. Với stop-the-world collector, collector có thể cập nhật relevant slots trước khi mutator tiếp tục. Với concurrent relocating collector, forwarding/barriers có thể cho phép **lazy remapping**, nên chưa chắc mọi slot chứa representation địa chỉ mới đồng thời.

```text
Trước:
  root1 --> A@old
  root2 --> A@old
  B.ref --> A@old

Sau relocation:
  root1 --> A@new
  root2 --> A@new
  B.ref --> A@new

A vẫn là A: giữ fields, identity, locking semantics.
```

**`System.identityHashCode(A)` không phải raw address.** Nó không được phép đổi chỉ vì GC chuyển chỗ một object vẫn là object ấy. Hai object khác nhau cũng có thể trùng identity hash code, nên identity hash không phải unique ID vĩnh viễn.

Các thuật ngữ như compressed oops, object header/mark word, forwarding bits, barriers, remembered sets là **internal HotSpot**. Mã Java portable không được dựa vào layout pointer bits.

## 11. Generational GC: tại sao young/old thường có chính sách khác nhau?

Giả thuyết thiết kế phổ biến: **đa số object chết tương đối sớm**, trong khi một số object có tuổi thọ dài. Một generational collector thường tổ chức object lifetimes vào các vùng trẻ và già để collection hiệu quả.

Ví dụ luồng khái niệm:

```text
Allocation --> Eden (young)
                  |
                  | Young collection
                  v
            Survivor regions / copies
                  |
                  | qua ngưỡng tuổi / điều kiện collector
                  v
              Old regions

Young collection có thể thu gom nhiều objects chết nhanh.
Old collection xử lý objects sống lâu theo chính sách khác.
```

Không có quy tắc “mọi Java object luôn qua đúng N young GCs rồi mới promotion”. Ngưỡng tuổi, survivor size, promotion và object có được phân bổ thẳng vào một vùng khác hay không phụ thuộc GC và flags.

### Tại sao young generation hay dùng copying?

Nếu 100 MiB được tạo ra nhưng chỉ 5 MiB còn sống sau một young collection, copying khoảng 5 MiB có thể rẻ hơn việc phải quản lý hàng chục nghìn free blocks nhỏ. Tuy nhiên đây là **ví dụ giả định**, không phải con số/live ratio của Java mặc định.

### Old generation có phải luôn dùng mark-sweep?

Không. Từng collector chọn thuật toán; Serial Old/Parallel Old thường thực hiện **mark-compact** trong những tình huống phù hợp; G1 có **region evacuation** và full compaction fallback; ZGC/Shenandoah có **concurrent relocation**. Thuật ngữ “young = copying, old = mark-sweep” là đơn giản hóa quá mức đối với HotSpot hiện đại.

## 12. G1 Java 17: kết hợp marking, evacuation và compaction

G1 (Garbage-First) trên HotSpot chia heap thành **regions**. Eden, survivor và old là các tập regions logic; không nhất thiết là những khối địa chỉ lớn liền nhau. G1 được thiết kế để cân bằng throughput và pause-time goals bằng cách chỉ thu gom các **collection sets (CSet)** phù hợp.

Các hoạt động chính:

1. **Young evacuation pauses:** chọn young regions trong CSet, tìm roots và references vào CSet, copy live objects ra các destination regions, reclaim selected source regions.
2. **Concurrent marking:** theo dõi live data của old regions, giúp ước lượng nơi có nhiều reclaimable garbage.
3. **Mixed collections:** ngoài young regions, chọn thêm những old regions có lợi để evacuate.
4. **Fallback Full GC:** trong những tình huống memory pressure/không thể tiến triển, collector có thể cần một full-heap compaction STW, có pause dài hơn.
5. **Humongous allocations/regions:** objects rất lớn có chính sách riêng, không giống các young objects nhỏ; fragmentation theo regions và trigger cycles cần được theo dõi.

### G1 “mark” và “evacuate” không nhất thiết cùng lúc

- **Concurrent marking** đánh giá liveness để chọn regions và chuẩn bị collection.
- **Evacuation** copy live objects trong **STW pauses** của G1 Java 17 cho các selected regions.
- **Remembered sets/card barriers** giúp biết references **từ ngoài collection set vào trong**, giảm nhu cầu quét toàn bộ heap ở mỗi young pause.
- G1 marking dùng nguyên lý **Snapshot-At-The-Beginning (SATB)** và write barriers để duy trì một liveness snapshot thích hợp trong khi mutators chạy.

Đừng nói “vì G1 có concurrent marking nên G1 luôn concurrent-copying mọi object”. Đây là **hai công việc khác nhau**. Những object ở ngoài CSet thường không move trong pause ấy.

### Nhìn ví dụ region bố cục

```text
G1 heap (regions, không phải semispaces 50%-50%):

R0: Eden         [A* B C* D]   <- chọn vào CSet
R1: Survivor     [E* F G]      <- chọn vào CSet
R2: Old          [H I* J K*]  <- tùy young/mixed CSet
R3: Old          [L* M]        <- nằm ngoài CSet
R4: Free         [            ]
R5: Free         [            ]

Evacuate A,C,E... sang destination regions;
reclaim R0,R1 khi an toàn;
R3 không tự copy chỉ vì một young collection.
```

Vị trí và ngưỡng thực do G1 quyết định. Ký hiệu `*` là object live **trong ví dụ**, không phải dữ liệu heap dump thật.

### Evacuation failure

Nếu thiếu available to-space, G1 có thể gặp **evacuation failure**; collector phải duy trì reference correctness dù một số live objects không được copy như dự định. Sau đó có thể phát sinh memory pressure và một Full GC nếu không đủ tiến triển. Vì thế **reserve/headroom** là một yếu tố của vận hành GC, không chỉ “heap used chưa đầy là đủ”.

Theo Oracle G1 tuning guidance, policy luôn là **mục tiêu tối ưu**, không có bảo đảm mọi pause luôn thấp hơn một số mili giây đã cấu hình.

## 13. Các collectors khác trong HotSpot Java 17

| Collector | Lựa chọn cơ chế ở mức khái quát | Trade-off cần hiểu |
| --- | --- | --- |
| **Serial GC** (`-XX:+UseSerialGC`) | GC work chủ yếu một collector thread; young copying và old collection/compaction theo implementation | Đơn giản, phù hợp một số heaps nhỏ/CPU hạn chế; pause STW |
| **Parallel GC** (`-XX:+UseParallelGC`) | Các GC threads làm việc song song; young copying và old **parallel compaction** theo cấu hình chuẩn | Tối ưu throughput, có thể chấp nhận STW pauses |
| **G1 GC** (`-XX:+UseG1GC`) | Region-based concurrent marking + STW evacuation/mixed collections + fallback compaction | Cân bằng throughput/pause goals và memory overhead |
| **ZGC** (`-XX:+UseZGC`) | Concurrent marking/relocation với load barriers và runtime metadata đặc thù | Ưu tiên latency thấp, có overhead/throughput trade-offs |
| **Shenandoah** (`-XX:+UseShenandoahGC` trên distributions phù hợp) | Concurrent marking/evacuation, forwarding/barriers theo mode | Giảm pause, trade-offs về CPU/memory/availability theo build |

Đây là **tổng quan giáo dục** của Java 17, không hứa mỗi distribution JDK 17 đều bật/bundled tất cả collectors. **Java SE specification không bắt buộc collector cụ thể.**

**Quan trọng về phiên bản:** ZGC trong JDK 17 khác các kiến trúc **Generational ZGC** của các JDK mới hơn. Khi đọc tài liệu tuning hoặc báo cáo số liệu, giữ đúng cặp **JDK version + collector**; không lấy hành vi của bản mới áp nguyên cho Java 17.

### Đừng xếp collector theo “tốc độ tuyệt đối”

- Throughput: phần thời gian application code làm việc thay vì GC.
- Latency: độ dài/độ phân bố pauses ảnh hưởng request tail latency.
- CPU overhead: marking/evacuation/barriers/JIT work có thể tốn CPU ngay cả khi pause ngắn.
- Memory overhead: remembered sets, bitmap, to-space/headroom và metadata.
- Predictability: workload allocation rate/live-set size quyết định nhiều.

Một collector throughput cao có thể có long pauses; một collector low-latency có thể tiêu tốn thêm CPU/memory. Phải đo theo workload thực thay vì chọn chỉ qua tên thuật toán.

## 14. Concurrent marking cần barriers để bảo vệ tính đúng

Nếu GC marking diễn ra **đồng thời** với application threads (mutators), object graph có thể thay đổi giữa lúc một object được quét và lúc collector quét reference kế tiếp.

Ví dụ tri-color:

```text
A:BLACK  (đã scan xong)
B:GRAY   (đang chờ scan)
C:WHITE  (chưa được phát hiện)

Nếu mutator đổi reference graph khiến C chỉ reachable
từ A sau khi A đã BLACK, collector có nguy cơ bỏ sót C,
nếu không có barrier/invariant phù hợp.
```

Các collectors thường dùng **write barriers** để ghi nhận/điều chỉnh thay đổi reference fields:

- **Snapshot-At-The-Beginning (SATB)**: mô hình bảo vệ snapshot của objects còn sống tại một mốc thích hợp; ví dụ cần ghi nhận **old reference value** khi một edge bị thay thế để tránh làm mất dấu object snapshot-live.
- **Incremental update**: một nhóm thiết kế khác tập trung vào những edges mới hoặc object colors để giữ invariant của marking.
- **Card marking/remembered sets**: ghi nhận những heap cards/regions có reference changes, hữu ích cho generational/region collectors khi tìm cross-region edges.

**Không phải mọi write barrier làm cùng một việc**, và không phải mọi GC đều dùng toàn bộ ba cơ chế trên. G1 Java 17 dùng barrier infrastructure cho SATB marking và tracking remembered sets với các vai trò khác nhau.

### Barriers của GC khác `volatile`/`synchronized`

- **GC barrier** là instrumentation của VM/JIT bảo vệ tracing/relocation invariant.
- **Java Memory Model barrier/synchronization** kiểm soát visibility và ordering giữa application threads.
- Hai hệ thống có thể cùng dùng các thao tác máy đặc thù, nhưng **mục đích/contract khác nhau**. Không bỏ `volatile` hoặc locks vì “GC cũng có barrier”.

### Concurrent relocation còn cần đúng target reference

Đối với ZGC/Shenandoah, khi object đang được di chuyển trong lúc mutator tiếp tục chạy, collector dùng **forwarding/remapping/load barriers** để bảo đảm việc truy cập tới đúng object. Do đó không thể dùng mô hình “STW sửa mọi references cùng một lần rồi mới resume” để giải thích toàn bộ concurrent relocation.

## 15. Stop-the-world, safepoints và GC phases

**Stop-the-world (STW)** nghĩa là các application threads tạm dừng ở những điểm/thời điểm VM yêu cầu để GC hoặc VM thực hiện công việc cần trạng thái heap/thread đủ nhất quán. GC không mặc định là một thread ngầm duy nhất chạy cạnh application.

Các dạng công việc trong một collection có thể gồm:

- Root enumeration/initial mark.
- Concurrent marking khi collector hỗ trợ.
- Reference processing.
- Evacuation/copying hoặc compaction.
- Root/reference fix-up, remapping.
- Remark/cleanup, class unloading và bookkeeping.

Một collector có thể vừa có **concurrent phases** vừa có **STW pauses**. Ví dụ G1 có concurrent marking và STW evacuation. ZGC thiết kế phần lớn công việc đắt tiền concurrent, nhưng không đồng nghĩa tuyệt đối không có pause nào.

**Safepoint pause không chỉ do GC.** JVM có thể cần safepoints/handshakes cho những hoạt động VM khác. Khi đọc log latency, xem loại VM operation, GC ID, elapsed time và ứng dụng đang chạy gì.

## 16. GC roots, reference types và quyết định giữ sống

Một tracing collector không thể coi **mọi edge** như strong reference thông thường. Java cung cấp reference objects với semantics riêng:

| Loại | Quy tắc liên quan | Tác dụng đến GC |
| --- | --- | --- |
| **Strong reference** | Reference thông thường từ fields/locals/arrays | Giữ referent reachable nếu đường từ roots hợp lệ |
| **SoftReference** | Referent có thể được GC clear theo memory sensitivity | Không phải TTL hay cache bound chính xác |
| **WeakReference** | Không giữ referent strong-live; có thể clear khi weakly reachable | Thích hợp cho một số lookup/canonicalization, không đảm bảo lúc clear |
| **PhantomReference** | Dùng cho cleanup lifecycle khi object đạt trạng thái tương ứng; `get()` luôn null | Không dùng đọc lại object như cache value |
| **JNI handles** | Có local/global/weak global semantics riêng | Native code phải theo contract để GC quản lý references |

### Clearing khác reclaiming và relocation

- **Mark:** xác định liveness theo reachability và những reference rules thích hợp.
- **Clear weak reference:** thay referent logic bằng null khi các điều kiện GC thỏa; không phải object bị copy sang nơi mới.
- **Reclaim dead object:** đưa memory của object không còn cần giữ về allocator.
- **Relocate live object:** đưa object còn sống tới location mới, giữ identity.

Đây là bốn hành động khác nhau. Thấy `weak.get() == null` không chứng minh “GC đã nén heap”; thấy output vẫn đúng cũng không chứng minh object thật đã được chuyển chỗ.

### Finalization và Cleaner

Không trông chờ finalizer để quản lý file/socket/database connections. Finalization có nhiều vấn đề và không có deadline rõ. Dùng `try-with-resources`, `AutoCloseable` hoặc lifecycle code tường minh; `Cleaner` là lựa chọn hạn chế cho fallback native cleanup khi thiết kế phù hợp. GC không phải service gọi `close()` vào đúng thời điểm nghiệp vụ yêu cầu.

## 17. Java 17: object identity được giữ bất chấp GC có di chuyển hay không

Tạo **`IdentityAcrossGc.java`**:

```java
import java.util.IdentityHashMap;

public class IdentityAcrossGc {
    static final class Node {
        final int id;
        Node child;

        Node(int id) {
            this.id = id;
        }
    }

    static volatile Object allocationSink;

    public static void main(String[] args) {
        Node parent = new Node(10);
        Node child = new Node(20);
        parent.child = child;

        Node alias = parent;
        Node[] roots = {parent};
        IdentityHashMap<Node, String> names = new IdentityHashMap<>();
        names.put(parent, "same-object");

        int hashBefore = System.identityHashCode(parent);

        for (int i = 0; i < 512; i++) {
            allocationSink = new byte[16 * 1024];
        }

        System.out.println("alias=" + (alias == parent));
        System.out.println("array=" + (roots[0] == parent));
        System.out.println("childId=" + parent.child.id);
        System.out.println("lookup=" + names.get(alias));
        System.out.println("hashStable="
                + (System.identityHashCode(parent) == hashBefore));
    }
}
```

```bash
javac --release 17 IdentityAcrossGc.java
java IdentityAcrossGc
```

**Stdout:**

```text
alias=true
array=true
childId=20
lookup=same-object
hashStable=true
```

Chương trình kiểm tra **Java reference semantics**, không phụ thuộc collector nào hoạt động. GC **có thể không chạy**, hoặc chạy nhưng object parent không nằm trong collection set; vòng tạo arrays **không chứng minh physical relocation**. `allocationSink` chỉ giữ một array được ghi gần nhất reachable thông qua static field volatile; compiler/GC vẫn có quyền tối ưu hợp lệ.

Nếu chạy với heap nhỏ và GC logging, có thể dễ quan sát một số collections, nhưng output cuối vẫn phải đúng miễn ứng dụng không gặp memory/resource errors. Không nên cố đọc address từ `System.identityHashCode`.

## 18. Tác động của live set, allocation rate và fragmentation

Một collector không chỉ chịu ảnh hưởng bởi **tổng heap size**. Đặc biệt quan trọng:

- **Live set size:** lượng bytes và objects cần bảo toàn sau marking. Copy/compact live set lớn có thể tốn nhiều công hơn.
- **Allocation rate:** số bytes được cấp theo thời gian. Allocation nhanh gây nhiều cycles/young pauses dù live set cuối không lớn.
- **Survival rate:** tỷ lệ objects còn sống khi collection xảy ra; quyết định copying cost.
- **Reference graph complexity:** số edges cần scan, pointer density và metadata.
- **Fragmentation:** có bao nhiêu free bytes **trong các spans đủ lớn**; nhiều free nhỏ có thể không giúp allocation một object lớn.
- **Headroom/to-space:** vùng đích có đủ chỗ cho surviving objects không?
- **Concurrency/CPU budget:** marking/relocation concurrent có tranh tài nguyên với application.
- **Collector tuning/ergonomics:** region sizes, generations, thresholds, pause goals, parallel threads.

### Ví dụ số giả định

Giả sử young regions có 300 MiB đã allocate và chỉ 20 MiB objects còn sống khi collection diễn ra. Copying 20 MiB có thể có lợi nếu overhead root scanning/barriers và destination space hợp lý.

Nếu một khác workload có 280 MiB objects còn sống trên 300 MiB, evacuation phải copy gần như toàn bộ live bytes; tương quan cost thay đổi. Không được biến ví dụ thành định luật “copy luôn nhanh hơn mark-sweep” hay “mark-compact luôn chậm nhất”.

### Fragmentation không đồng nghĩa OOME ngay lập tức

Allocator/collector có thể thử tìm nơi khác, reclaim, compact, expand committed heap hoặc fallback tùy implementation. Một `OutOfMemoryError` có thể do **thực sự thiếu free memory**, **không đủ contiguous regions/to-space**, **retained live set lớn**, metaspace/native memory hoặc giới hạn container. Phải đọc loại lỗi và log trước khi kết luận.

## 19. Xem GC logging trên HotSpot Java 17

Bật Unified Logging bằng `-Xlog`:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC -Xlog:gc IdentityAcrossGc
```

Với phân rã phases chi tiết hơn, trên build hỗ trợ tags/levels tương ứng:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC -Xlog:gc*,gc+phases=debug IdentityAcrossGc
```

**Không có stdout GC cố định**: số collections, thời điểm pause, phases và heap occupancy phụ thuộc workload, OS, collector, JIT và build. Chạy ví dụ với heap vừa đủ thậm chí **có thể không phát sinh GC event đáng kể**. Dùng log để tìm hành vi thực, không giả lập một trace rồi trình bày như đã đo.

Trong G1 GC logs, có thể thấy các thông tin về:

- Young/normal/mixed collections.
- Eden, survivor và old regions trước/sau.
- Evacuate Collection Set / merge heap roots, copy/scan phases, reference processing.
- Concurrent marking phases, Remark/Cleanup.
- Pause durations và memory occupancy.

Các tên logs thay đổi theo bản JDK. Lấy **ý nghĩa phases** và thực nghiệm đúng JVM đang dùng làm căn cứ, không viết parser quá cứng theo một chuỗi log duy nhất.

### Công cụ quan sát khác

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jstat -gc <PID> 1000 5
```

`<PID>` là **placeholder process ID**, không phải một process đã xác minh. Các lệnh `jcmd`/`jstat` cần process Java đang chạy và đủ quyền; `IdentityAcrossGc` kết thúc rất nhanh nên thường không có PID để attach khi bạn thực thi lệnh về sau.

- `VM.flags` giúp biết cấu hình VM/GC.
- `GC.heap_info` báo trạng thái heap/collector theo implementation.
- `jstat -gc` cung cấp counters/occupancy/cycle stats theo collector/JDK.
- `jcmd` có thể có diagnostic commands khác; chạy `jcmd <PID> help` để biết những lệnh thực sự được hỗ trợ.

**Heap dump** có ích khi muốn biết vì sao object còn reachable, chứ không mô tả đầy đủ các bước copy/compact trong GC. **GC logs** cho biết collection hoạt động thế nào, chứ không chỉ ra độc nhất object nào là leak root.

## 20. Phân tích một tình huống chẩn đoán thực tế

Giả sử một service có:

- Heap configured maximum 2 GiB.
- GC log: young collections ngày càng dày, mixed cycles sau đó, thỉnh thoảng Full GC.
- Heap after-GC occupancy tăng từ 700 MiB lên 1,7 GiB dưới workload tương đương.
- Có thông báo evacuation failure/to-space pressure ở một số thời điểm.

Một quy trình hợp lý:

1. **Kiểm tra liveness/retention trước:** live set tăng do cache, listener, ThreadLocal, request queues hoặc data growth có chủ đích? Lấy histogram/heap dump khi an toàn.
2. **Đọc GC logs:** có phải allocation rate tăng, young survival rate tăng, promotion/old occupancy tăng không? Full GC xuất hiện vì vấn đề gì?
3. **Tìm fragmented/region pressure:** liệu collection sets còn đủ destination space để evacuate không? Có nhiều humongous allocations/regions không?
4. **Đánh giá policy GC:** collector/heap sizing/headroom phù hợp với pause goals và CPU/container budgets chưa?
5. **Sửa nguyên nhân ở application nếu live set không còn cần:** bounded cache, release listeners, remove ThreadLocal, shutdown resource owners.
6. **Kiểm tra lại cả throughput và latency:** sửa chỉ để hết `OutOfMemoryError` nhưng tăng pause lên vài giây có thể chưa đạt mục tiêu vận hành.

**Tăng `-Xmx` có thể trì hoãn tình huống thiếu chỗ**, nhưng nếu ứng dụng tiếp tục giữ vô hạn object, nó không sửa memory leak logic. Ngược lại, nếu live set hợp lệ và heap quá nhỏ, cần tính capacity/headroom thực sự và bộ nhớ ngoài heap trong container.

## 21. Mười lăm hiểu lầm cần tránh

| Hiểu lầm | Sự thật |
| --- | --- |
| “Mark tự giải phóng object” | Mark chỉ phân loại liveness; cần reclaim/evacuation/compaction |
| “Object không được mark tại mọi thời điểm là garbage” | Marking có các trạng thái trung gian; white có thể còn chưa scan |
| “Chu trình A↔B làm tracing GC không giải phóng được” | Chu trình không reachable từ roots vẫn có thể reclaim |
| “Mark-sweep luôn dồn các live objects sát nhau” | Non-moving sweep thường để lại holes và free lists |
| “Có tổng free lớn thì cấp được object lớn” | External fragmentation có thể không đủ contiguous space |
| “Copy phải sao chép toàn bộ heap” | Thường chỉ selected generation/regions, live objects |
| “Copying luôn phải giữ nửa heap trống” | Hai semispaces là một thiết kế; G1 dùng selected regions |
| “Compact là sweep nhưng xóa mạnh hơn” | Compact **di chuyển/gom live objects**, sweep chủ yếu reclaim dead blocks |
| “GC move object làm `==` hoặc identity hash thay đổi” | Java-visible object identity phải giữ nguyên |
| “Mọi GC Java 17 đều dùng cùng một thuật toán” | Serial, Parallel, G1, ZGC, Shenandoah phối hợp khác nhau |
| “G1 concurrent marking nghĩa G1 concurrent evacuation như ZGC” | G1 Java 17 evacuate CSet trong STW pauses chủ yếu |
| “GC write barrier bảo đảm Java application thread safety” | GC barrier khác `volatile`, locks và happens-before |
| “Một GC event chứng minh object X cụ thể đã move” | Không; collection scope/relocation cần bằng chứng sâu hơn |
| “Mark-compact luôn là Full GC” | Có compaction/evacuation theo regions hoặc phases tùy collector |
| “Heap used lớn là heap leak chắc chắn” | Cần post-GC live set, retention paths và workload evidence |

## 22. Checklist quyết định thuật toán và phân tích performance

Trước khi so một collector hay đọc một biểu đồ GC, tự hỏi:

1. Object graph gồm bao nhiêu **live bytes**? Có cache/registries cố giữ objects không?
2. Tỷ lệ objects chết ngay sau allocation là bao nhiêu?
3. Collection đang xử lý **toàn heap** hay **young/old selected regions**?
4. **Mark** diễn ra STW, parallel hay concurrent? Dùng barrier model gì?
5. Dead memory được reclaim bằng **sweep/free list**, **evacuation** hay **compact**?
6. Nếu relocate objects, collector tìm forwarding destination và **sửa/đọc references** bằng cách nào?
7. Có **to-space/headroom** đủ cho live objects không?
8. Fragmentation là **free blocks nhỏ**, **humongous regions**, alignment hay allocator metadata?
9. Phần lớn thời gian GC tiêu vào root scanning, reference processing, copy bytes hay compaction?
10. Mục tiêu cần tối ưu **throughput**, **p99 pause latency** hay footprint?
11. JVM/collector release có đúng Java 17 không? Tài liệu và flags có thuộc đúng bản đó không?
12. Kết luận được chứng minh bằng GC logs/JFR/benchmark trên workload thật hay chỉ bằng lý thuyết?

## 23. Câu hỏi tự kiểm tra

**Câu 1:** Một object A có đường đi từ GC root, object B không có. Marking dùng để xác định điều gì?

**Đáp:** A reachable theo roots được xét; B chưa thuộc tập live tương ứng và có thể được reclaim theo reference rules.

**Câu 2:** Sau mark-sweep, tổng trống 10 MiB nhưng không có free span nào lớn hơn 2 MiB. Request 4 MiB có chắc cấp phát thành công trong cùng vùng đó không?

**Không.** Nếu cần 4 MiB contiguous và không có vùng khác/compaction/expansion, external fragmentation gây khó cấp phát.

**Câu 3:** Điểm khác cốt lõi giữa mark-sweep và mark-compact?

Mark-sweep thường để live objects tại chỗ và đưa dead blocks vào allocator; mark-compact gom/move live objects để tạo free space liên tục.

**Câu 4:** Copying collector gặp hai roots cùng trỏ A. Có tạo hai object A mới không?

**Không được tạo hai Java object identity độc lập.** Forwarding/claim logic bảo đảm các reference cùng đến một logical destination.

**Câu 5:** Vì sao copying có thể hiệu quả cho young generation?

Vì trong nhiều workload nhiều objects chết nhanh; chỉ cần evacuate một live subset nhỏ, reclaimed source space nhanh và allocation đích có thể đơn giản.

**Câu 6:** G1 concurrent mark và G1 evacuation có phải cùng một phase?

**Không.** Concurrent marking chủ yếu đánh giá liveness; selected-region evacuation thường thực hiện trong STW collection pauses của G1 Java 17.

**Câu 7:** `IdentityAcrossGc` in toàn bộ `true` có chứng minh parent thật sự đã chuyển địa chỉ?

**Không.** Chương trình chỉ kiểm tra contract Java; GC có thể không chạy hoặc object không move.

**Câu 8:** GC write barrier có thay thế `synchronized` để ngăn data race không?

**Không.** GC barriers giữ collector invariants, Java concurrency cần JMM synchronization phù hợp.

**Câu 9:** ZGC và Shenandoah giúp concurrent relocation mà Java vẫn thấy đúng reference bằng cách nào?

Dùng kết hợp forwarding metadata và barriers/remapping theo thuật toán/phiên bản, thay vì yêu cầu mọi reference slot được eager fix-up trong một global STW pause.

**Câu 10:** Vì sao một Full GC có thể chậm dù phần lớn objects còn sống?

Vì tracing, cập nhật references và di chuyển/compact lượng live bytes lớn vẫn tốn công, nhất là khi thiếu memory headroom/parallelism.

## 24. Tài liệu tham khảo chuẩn

- [JVMS Java SE 17 — Run-Time Data Areas / Heap (`2.5.3`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap và quản lý objects theo đặc tả.
- [Java SE 17 Garbage Collection Tuning Guide — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC và lựa chọn collector.
- [Java SE 17 Garbage Collection Tuning Guide — G1 Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): regions, marking, evacuation, collection sets, compaction fallback, fragmentation.
- [Oracle — Garbage-First Garbage Collector Tuning](https://www.oracle.com/java/technologies/g1gc.html): evacuation, remembered sets và parallel copying theo mô hình G1.
- [JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333): concurrent marking/relocation, colored pointers/load barriers.
- [JEP 189 — Shenandoah: A Low-Pause-Time Garbage Collector](https://openjdk.org/jeps/189): concurrent evacuation và low-pause design.
- [Java SE 17 `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html), [`WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [`SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html), [`PhantomReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): reference reachability và clearing.
- [Java SE 17 `System.identityHashCode` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): identity không đồng nhất địa chỉ object.
- [Java SE 17 `jcmd` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [`jstat` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): heap diagnostics và GC counters.
- [Java SE 17 `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, GC/heap flags.

**Ghi nhớ:** **Mark** tìm objects cần giữ; **sweep** đưa dead blocks về vùng trống; **copy** di chuyển live objects sang vùng đích; **compact** gom objects sống để giảm phân mảnh. Không thuật toán nào là toàn bộ GC hiện đại: HotSpot phối hợp marking, reference processing, evacuation, forwarding, barriers và region/heap management theo từng collector. Hãy dựa vào **reachability, live-set size, fragmentation, memory headroom và GC phases thực tế** để giải thích vì sao một lần GC thu hồi hiệu quả hoặc gặp khó khăn.
