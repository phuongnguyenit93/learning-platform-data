# Shenandoah: concurrent marking, evacuation và cập nhật tham chiếu (Java 15 và Java hiện đại)

> **Mục tiêu:** Hiểu cơ chế của **Shenandoah Garbage Collector** khi tìm các đối tượng còn sống (*concurrent marking*), lựa chọn vùng cần dọn, **di chuyển các đối tượng đang sống trong lúc ứng dụng tiếp tục chạy** (*concurrent evacuation*) và **sửa các references trỏ tới vị trí cũ** (*concurrent update references*). Bài thuộc chủ đề **Shenandoah** của module **Java 15**, nhưng tập trung vào kiến thức **còn áp dụng với OpenJDK/Java hiện nay**: phân biệt Shenandoah **SATB single-generation** và **Generational Shenandoah** được chuẩn hóa từ JDK 25; tránh nhầm phase names/cờ của các bản cũ với hợp đồng API bất biến. Hai chương trình **Java 17+** ở dưới đã được biên dịch, chạy với Shenandoah và đối chiếu GC logs trên OpenJDK 24.

## 1. Vì sao Shenandoah cần marking, evacuation và update references?

Một garbage collector phải giải hai việc lớn:

1. **Xác định đối tượng nào còn có thể truy cập** từ chương trình, để không thu hồi một object vẫn đang dùng.
2. **Tái sử dụng heap space** mà các object không còn reachable đã chiếm; nếu bộ nhớ phân mảnh, có thể cần **di chuyển các object còn sống** để trả cả vùng về free pool.

Với nhiều collector, các pha trace/compact quan trọng có thể gây **Stop-The-World (STW) pause** dài, đặc biệt khi heap lớn và số references nhiều. Shenandoah là collector định hướng **độ trễ thấp**, đưa phần lớn việc marking, evacuation và reference updating sang **concurrent phases** chạy đồng thời với các **mutator threads** (threads thực thi code ứng dụng Java).

~~~text
Application / mutators: |---------------------------------------------|
GC controller:         |pause|mark concurrently|pause|evacuate|update refs|...
                                  ^                        ^
                                  |                        |
                          vẫn đọc/ghi objects      vẫn đọc/ghi objects
~~~

**Tính chất không thể nhầm:**

- **Concurrent** không có nghĩa không có STW pause. Shenandoah có các điểm đồng bộ hóa ngắn và có thể phải fallback sang các pha STW khi thiếu tài nguyên.
- **Evacuation** không phải “xóa vật thể chết”: nó **sao chép/di chuyển object còn sống** ra khỏi regions sẽ thu hồi.
- **Update references** không phải một API do lập trình viên gọi: JVM sửa hoặc điều hướng các references còn trỏ tới nơi cũ.
- **Java object identity được bảo toàn** khi collector di chuyển đối tượng. `==` và các quy tắc truy cập object vẫn đúng.
- **Low pause time** là mục tiêu/thuộc tính thiết kế, không có nghĩa mọi request có p99 latency thấp hoặc GC không tiêu thụ CPU/heap headroom.

Một service có rất nhiều allocations, heap lớn và yêu cầu giảm latency spikes do GC có thể cân nhắc Shenandoah. Nhưng mọi đánh giá hiệu năng phải dựa vào **GC pauses, allocation stalls, memory, CPU và application tail latency** của đúng workload.

## 2. Gắn đúng ngữ cảnh lịch sử Java 15 mà không dạy cấu hình lỗi thời

| Phiên bản | Mốc Shenandoah | Ý nghĩa khi đọc tài liệu |
| --- | --- | --- |
| **JDK 12** | **JEP 189** đưa Shenandoah vào OpenJDK ở trạng thái **experimental** | Một số tài liệu cũ yêu cầu `-XX:+UnlockExperimentalVMOptions`, hoặc nói về barriers và root scanning của bản đầu |
| **JDK 14–16** | Nhiều cải tiến concurrent roots, unloading, reference processing | Các chi tiết từng là STW có thể được chuyển sang concurrent theo phiên bản |
| **JDK 15** | Shenandoah có trong những OpenJDK distributions hỗ trợ; mô hình **SATB/non-generational** được dùng rộng rãi | Shenandoah **không phải tính năng vừa được tạo ra trong Java 15** |
| **JDK 24** | **JEP 404: Generational Shenandoah (Experimental)** | Generational mode của riêng phiên bản này còn cần opt-in cho experimental features |
| **JDK 25** | **JEP 521: Generational Shenandoah** trở thành **product feature** | Bật generational bằng `-XX:ShenandoahGCMode=generational` khi distribution hỗ trợ |
| **JDK 25/26/27** | Với tài liệu và cấu hình đã kiểm chứng, `satb` vẫn là mode **mặc định** của Shenandoah | Không suy diễn “đã có generational” thành “generational mặc định” |

**Phân biệt đặc biệt quan trọng với ZGC:** ZGC đã loại bỏ non-generational mode từ JDK 24; **Shenandoah không đi cùng lộ trình đó ở JDK 25**. Shenandoah vẫn có **SATB single-generation** làm mode mặc định và **generational** như một lựa chọn. Không lấy cờ/định nghĩa GC từ ZGC đặt sang Shenandoah.

### Cách bật thực dụng trên JDK 25+ có Shenandoah

~~~bash
java -XX:+UseShenandoahGC -Xms128m -Xmx512m -jar application.jar
~~~

Đây là ví dụ chọn Shenandoah, **mặc định SATB/single-generation** theo tài liệu hiện hành; heap sizes chỉ minh họa.

Nếu muốn chọn **Generational Shenandoah đã là product feature từ JDK 25**:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms128m -Xmx512m -jar application.jar
~~~

**Không cần** `-XX:+UnlockExperimentalVMOptions` cho generational Shenandoah ở **JDK 25+**. Với **JDK 24**, generational mode từng experimental và có yêu cầu riêng, nên không sao chép nguyên lệnh trên vào JDK 24 rồi khẳng định phải chạy được. Nếu JVM báo không nhận ra `UseShenandoahGC`, có thể **bản phân phối JDK không build collector này**: chọn distribution hỗ trợ hoặc collector khác theo yêu cầu, không tự tải lớp nội bộ hay “mở” Shenandoah bằng code Java.

**Lưu ý:** Mô hình chi tiết các pha ở mục 4–9 dùng **SATB, mark–evac–update** vì đây là flow rõ ràng và vẫn có trong Shenandoah hiện hành. Generational Shenandoah giữ nguyên mục tiêu concurrent low pause nhưng chia xử lý theo young/old generations; phase scheduling, heap layout và barriers có thể khác.

## 3. Vùng heap, GC roots và live set

Shenandoah quản lý heap thành các **regions**. Một region có thể chứa cả objects còn sống lẫn garbage; sau marking, collector ước tính lượng **live data**, chọn vùng phù hợp làm **collection set (cset)** để evacuation và thu hồi.

Sơ đồ reachability:

~~~text
GC roots
   |
   +--> static Holder[] ------------+
   |                                |
   |                       +--> Payload A ----> byte[]
   |                       +--> Payload B ----> byte[]
   |
   +--> stack/local reference ------> InFlightRequest
   |
   +--> JVM/JNI reachable handles --> NativeReferencedObject

Không còn root path ----> UnreachablePayload (garbage candidate)
~~~

**Roots** có thể đến từ references trên thread stacks, static fields, JNI handles, compiled code/runtime structures và những nguồn phù hợp khác. **Marking** theo các references từ roots để xác định tập objects cần giữ lại trong một GC cycle.

- **Reachable:** có đường đi qua những strong references phù hợp tới roots, phải được bảo vệ khỏi reclamation sai.
- **Unreachable:** không còn đường từ roots, có thể thu hồi theo thời điểm GC quyết định, nhưng không có nghĩa bị xóa ngay sau `obj = null`.
- **Weak/soft/phantom references:** có reachability rules riêng; cần reference processing phù hợp. Không đồng nhất `WeakReference.get() == null` với toàn bộ marking/evacuation đã hoàn tất.
- **Region:** đơn vị GC quản lý, không phải Java class/object. Một region nhiều garbage thường là ứng viên để thu hồi/evacuate; không phải mọi region đều được compact trong mỗi cycle.

### Ví dụ về đồ thị đối tượng

~~~java
final class Node {
    Node next;
    final byte[] payload = new byte[8192];
}

Node head = new Node();
head.next = new Node(); // reachable qua head
head.next = null;       // nút cũ có thể trở thành unreachable
~~~

Đây là **đoạn minh họa trong method**, không phải chương trình độc lập. `head.next = null` làm một reference biến mất, nhưng collector có thể đang chạy concurrent với đoạn code đó; không có API đảm bảo object cũ được dọn ngay thời điểm dòng lệnh thực hiện.

## 4. Concurrent marking và nguyên lý SATB (Snapshot at the Beginning)

**Marking** theo dõi đồ thị objects còn reachable. Trong thế giới chỉ có một thread và dừng ứng dụng, việc duyệt cây references khá trực quan. Với Shenandoah, **mutator có thể thay đổi các cạnh trong đồ thị đúng lúc GC đang duyệt**.

Ví dụ:

~~~java
Holder holder = ...;
Payload oldValue = holder.current;
holder.current = new Payload(123);
~~~

Nếu GC chưa kịp đánh dấu `oldValue` mà mutator vừa ghi đè đường trỏ, collector có thể bỏ sót một object vốn thuộc **snapshot logic tại thời điểm bắt đầu cycle**. Shenandoah SATB duy trì invariant bằng **write barriers**: khi mutator ghi đè một reference, collector có thể ghi nhận **reference cũ** vào buffer/queue để hoàn tất trace phù hợp.

Mô hình SATB:

~~~text
Bắt đầu cycle:
    GC ghi nhận một snapshot logic của graph (SATB).
    Mutators vẫn thay đổi field references.

Mutator: old = holder.current
Mutator: holder.current = newValue
                  |
             SATB write barrier
                  |
             đưa old reference cần bảo toàn vào marking queue

GC threads:
    concurrent traverse roots + marking queues
    xử lý các references trước khi final mark kết thúc
~~~

**Giải thích chính xác:**

- SATB không có nghĩa HotSpot “copy toàn bộ heap thành snapshot vật lý”.
- Collector bảo toàn **tập reachable của snapshot theo thuật toán SATB** bằng bookkeeping, không dừng application trong toàn bộ marking.
- Barriers là **logic do JIT/JVM triển khai**, không phải `synchronized`, không phải `Lock` và không cần developer tự gọi.
- Một object vừa trở thành unreachable có thể **vẫn được giữ trong cycle hiện tại** do chính sách snapshot; collection sau mới thu hồi. Điều này là **tính đúng đắn**, không phải memory leak.
- Việc cấp phát object mới trong lúc marking đang diễn ra được collector/JVM xử lý theo invariant của chế độ; đừng suy từ mô hình khái niệm rằng object mới phải quét bằng một thứ tự cố định.

### Phân biệt SATB barrier và load-reference barrier

**SATB write barrier** hỗ trợ tính đúng đắn của **concurrent marking** khi reference cũ bị ghi đè. **Load reference barrier (LRB)** hỗ trợ tính đúng đắn của **concurrent evacuation/relocation** khi một reference trỏ tới object có thể đang được chuyển chỗ.

Hai barriers xử lý **hai tình huống khác nhau**. Chúng có thể cùng góp mặt trong Shenandoah SATB; trong generational mode còn có nhiều bookkeeping cho cross-generation references. Không dùng cụm “write barrier” để tự suy ra mục đích của mọi barrier.

## 5. Init Mark, Concurrent Mark và Final Mark — việc gì thực sự đang xảy ra?

Trong **SATB single-generation cycle**, cách đọc khái niệm:

| Phase / nhóm pha | Mutators có bị dừng? | Vai trò |
| --- | --- | --- |
| **Pause Init Mark** | **Có**, pause ngắn | Bắt đầu cycle, thiết lập trạng thái phù hợp cho marking |
| **Concurrent marking roots** | **Không** trong phần concurrent | Truy vết roots với cơ chế phối hợp/barriers của Shenandoah |
| **Concurrent marking** | **Không** trong phần concurrent | Duyệt graph, mark reachable objects |
| **Pause Final Mark** | **Có**, pause | Hoàn tất/trộn marking queues, xác nhận live set và chuẩn bị collection set |
| **Concurrent cleanup** | **Không** | Có thể thu hồi những regions không còn objects sống |
| **Concurrent evacuation** | **Không** trong phần chính | Di chuyển live objects khỏi regions đã chọn |
| **Pause Init Update Refs** | **Có**, rất ngắn trong flow có update refs | Chuyển/đồng bộ trạng thái trước pha sửa references |
| **Concurrent update references** | **Không** | Đi qua references cần cập nhật tới object locations mới |
| **Pause Final Update Refs** | **Có**, pause | Hoàn tất sửa roots/cho phép reclaim regions cũ an toàn |
| **Concurrent cleanup** | **Không** | Hoàn thành reclamation regions đã được di chuyển |

**Đây là một flow điển hình chứ không phải một lịch cố định.** Nếu collection set **không có region cần evacuation**, những phases evacuation/update-refs **có thể bị bỏ qua**. Một số releases có thêm/bớt subphases, tên log khác, root processing concurrent và fallback phases. Generational mode có young/old cycles với sequencing riêng.

**Không cộng toàn bộ `Concurrent marking 0.5ms` và `Concurrent evacuation 0.7ms` để bảo rằng application dừng ~1.2ms.** Chỉ các dòng `Pause ...` mới biểu diễn STW synchronization time theo ý nghĩa log.

## 6. Collection set: tại sao chỉ di chuyển một số regions?

Sau khi biết **live occupancy**, Shenandoah có thể chọn **collection set (cset)** chứa các regions giúp thu hồi nhiều memory sau khi chuyển lượng live data hợp lý.

~~~text
Region R1: [dead][dead][live A][dead][live B][dead]
Region R2: [live C][live D][live E][live F][live G]
Region R3: [dead][dead][dead][dead][dead]

Concurrent marking:
    R1 còn ít live bytes -> ứng viên evacuation.
    R2 nhiều live bytes -> có thể không đáng di chuyển ngay.
    R3 không còn live -> có thể reclaim trực tiếp.

Selected cset:
    R1 -> evacuate live A và live B sang vị trí mới.
    R3 -> có thể thu hồi không cần copy object.
~~~

**Mục tiêu:** đổi công sức copying live objects lấy một lượng memory được reclaim và giảm fragmentation. Một cycle không nhất thiết phải di chuyển **mọi** object sống. Việc chọn cset phụ thuộc heuristics, free headroom, fragmentation và mức áp lực allocation.

### Vì sao cần extra memory khi evacuation?

Trong lúc copying, có thể tồn tại **bản cũ và bản mới** của một số objects cho đến khi forwarding/references được xử lý xong. Collector cần **to-space/free regions** để chuyển dữ liệu an toàn trong khi mutator vẫn allocate.

Nếu heap quá chật và tốc độ cấp phát lớn, Shenandoah có thể không hoàn tất cycle đúng thời gian hoặc thiếu to-space. Đây là một nguồn của **allocation failure, degenerated GC hoặc full GC fallback** và latency spikes; không phải vì marking/evacuation “không đồng thời”.

## 7. Concurrent evacuation và forwarding pointer

Khi collector di chuyển object `A` từ **from-space** đến **to-space**:

~~~text
Trước:
  object reference --> [ A at address OLD ]

Evacuation:
  1. Copy/live A sang [ A' at address NEW ].
  2. Ghi nhận forwarding từ OLD tới NEW.
  3. Mutator vẫn có thể giữ một reference đang chỉ đến OLD.

Load Reference Barrier:
  ref = holder.current
            |
            v
       đang dùng địa chỉ OLD?
            |
       tra forwarding / resolve new location
            |
            v
       trả về object A' hợp lệ

Sau:
  mọi đường truy cập được bảo toàn theo Java object semantics
~~~

Shenandoah dùng **forwarding information** và **load-reference barriers** (cùng coordination phù hợp) để mutators có thể đọc/ghi objects khi evacuation đang diễn ra.

### Vì sao không phải một cuộc đua “copy 2 object độc lập”?

Nếu hai threads (GC và application) cùng nhận thấy một object cần evacuation, implementation phải tránh **hai bản sao “chính thức” khác identity**. Collector dùng nguyên tử hóa/forwarding protocol theo cách phù hợp để bảo đảm chỉ một đích được công nhận. Chi tiết implementation có thể thay đổi qua phiên bản; developer không được dựa vào cấu trúc object header/forwarding pointer cụ thể như API.

**Java semantics không đổi:**

~~~java
Object x = new Object();
Object alias = x;

System.out.println(x == alias); // true
~~~

Sau bất kỳ GC relocation hợp lệ nào, **hai references vẫn mô tả cùng Java object**. Java không có public API portable để hỏi “physical address trước/sau” hoặc bảo đảm một object sẽ được relocate khi nào.

**Không viết code thay đổi raw addresses bằng `Unsafe`/JNI** để “hỗ trợ Shenandoah”. Những thao tác bypass object reference model có thể phá invariant của GC và an toàn bộ nhớ.

## 8. Concurrent update references: bước khác biệt cần hiểu

Sau evacuation, một số references trong heap/roots **vẫn có thể trỏ về vị trí cũ**. Load-reference barrier giúp các truy cập tức thời được **resolve** để application hoạt động đúng, nhưng collector còn cần dọn sạch các pointers cũ và thu hồi from-space an toàn.

Trong **SATB three-pass mark–evac–update**, **Concurrent Update References** quét các locations/references thuộc phạm vi cần xử lý, sửa references còn trỏ tới relocated objects sao cho chúng chỉ tới **to-space**. Đây là hoạt động **đồng thời với mutators** trong phần chính.

~~~text
Before evacuation:
  Holder1.child ------> Object A @ OLD
  Holder2.child ------> Object A @ OLD

During evacuation:
  Object A @ OLD ---> forwarding ---> Object A @ NEW

During concurrent update references:
  Holder1.child ------> Object A @ NEW
  Holder2.child ------> Object A @ NEW

Final update references:
  xử lý phần roots/states còn cần hoàn tất
  old regions có thể được reclaim an toàn
~~~

**Phân biệt ba khái niệm:**

- **Marking:** ai còn reachable?
- **Evacuation:** object còn sống đi tới vùng nhớ mới ở đâu?
- **Update references:** những fields/roots nào cần chuyển từ old location sang new location?

**Không nên bỏ qua update refs** khi giải thích SATB Shenandoah: dù forwarding barrier cho phép app đọc đúng trong lúc di chuyển, các old regions chỉ có thể trở thành free sau khi invariants phù hợp đã được hoàn tất.

**Nhưng cũng không nói rằng mọi generational cycle trên mọi JDK quét full heap theo cùng lịch.** Generational mode có chính sách/metadata riêng và phases tùy young/old; những mô tả cập nhật refs toàn heap xuất phát từ luồng SATB/single-gen.

## 9. Bốn pause thường thấy và lý do không gọi Shenandoah là “zero pause”

Ở mode SATB truyền thống, ta có thể gặp:

- **Pause Init Mark:** đồng bộ hóa để bắt đầu marking.
- **Pause Final Mark:** kết thúc marking/thiết lập collection set.
- **Pause Init Update Refs:** chuẩn bị chuyển sang update references sau evacuation.
- **Pause Final Update Refs:** kết thúc sửa references, recycle regions phù hợp.

Những phần nặng như **Concurrent marking**, **Concurrent evacuation** và **Concurrent update references** chạy song song với application. Do vậy độ lớn heap **không buộc** toàn bộ marking/movement thành một STW pause dài như một collector compacting thuần STW.

Tuy nhiên, pause thực tế có thể bị ảnh hưởng bởi:

- Số và loại roots cần đồng bộ hóa.
- Safepoint/handshake coordination, nmethods, references và class loading.
- Workload tạo ra quá nhiều objects live hoặc quá ít free/to-space.
- CPU scheduling, số GC threads, contention và kernel/system conditions.
- Một pha **degenerated/full GC** bất thường phải hoàn thành theo STW để bảo vệ correctness.

**Đừng bảo đảm pauses dưới 1ms tuyệt đối**. Độ trễ quan sát được trong service còn gồm cả allocation stalls, application locks, CPU saturation, I/O và container limits.

## 10. Generational Shenandoah (JDK 25+) khác SATB single-generation thế nào?

**JEP 521** làm Generational Shenandoah thành **product feature từ JDK 25**. Nó vẫn là concurrent low-pause collector nhưng chia objects thành **young** và **old generations** để thu hồi rác tồn tại ngắn hạn hiệu quả hơn.

| Tiêu chí | `satb` (mặc định theo docs JDK 25) | `generational` (product từ JDK 25) |
| --- | --- | --- |
| Các thế hệ | **Một generation** | **Young và old** |
| Khái niệm marker | SATB concurrent tracing | SATB/concurrent marking theo scope generation |
| Evacuation | Concurrent, dựa vào cset | Concurrent evacuation theo cycle/generation phù hợp |
| Update references | Luồng mark–evac–update rõ ràng | Có bookkeeping, barriers và strategies phù hợp nhiều generation |
| Cross-generation references | Không có old→young border | Phải duy trì thông tin các **old→young references** để young tracing không bỏ sót đối tượng |
| Heuristics | `adaptive` thường là mặc định; có thêm các lựa chọn khác | **`adaptive` là heuristics được hỗ trợ** trong tài liệu JDK 25 |
| Bật | `-XX:+UseShenandoahGC` | `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` |

### Tại sao có old → young remembered information?

~~~text
GC root ------> CachedState (old generation)
                        |
                        +----> FreshRequest (young generation)
~~~

Nếu young collection bỏ qua mọi old objects mà không nhớ **cross-generational edge** từ `CachedState` sang `FreshRequest`, nó có thể **nhầm FreshRequest thành garbage**, phá memory safety. Generational Shenandoah vì thế có barriers/remembered metadata liên quan để giữ thông tin cần thiết.

Điều này **không phải** public Java API; lập trình viên không cần phát hiện object thuộc generation nào bằng reflection. Hạn chế allocation pressure không cần thiết và đo kết quả GC thay vì cưỡng ép một object cụ thể vào young/old.

**Quan trọng về niên đại:** **JDK 24** có generational Shenandoah experimental (JEP 404); **JDK 25** có generational Shenandoah product (JEP 521). Không kết luận generational đã là default ở JDK 25: thông số `ShenandoahGCMode` mặc định là **`satb`** theo tài liệu JDK 25 đã đối chiếu. Tương lai có thể thay đổi, vì vậy luôn kiểm tra docs/flags của runtime triển khai.

## 11. Vì sao không phải GC cycle nào cũng có concurrent evacuation?

Một nhận định đặc biệt quan trọng khi nhìn log:

- **Marking** có thể nhận ra những regions đã trống hoặc hoàn toàn garbage.
- Collector có thể **thu hồi trực tiếp** những regions đó mà **không cần copy** object nào.
- Có cycle mà heuristics không chọn cset để di chuyển, vì lượng memory có thể lấy lại từ evacuation không xứng công sức hoặc điều kiện hiện tại không thích hợp.
- Khi **không có evacuation**, phases **Init/Concurrent/Final Update Refs** cũng có thể không xuất hiện trong log của cycle đó.
- **Không có chữ “Concurrent evacuation” trong một log** không chứng minh Shenandoah thiếu khả năng evacuation.

Trong quá trình thử, một workload chỉ thay references để tạo rất nhiều garbage ngắn hạn **đã ghi concurrent marking nhưng không xuất hiện evacuation/update refs**. Sau khi chỉnh workload để giữ **một số objects live xen lẫn garbage trong các regions**, logs đã hiện đủ **concurrent marking, concurrent evacuation và concurrent update references**.

**Bài học khi kiểm thử:** Muốn kiểm chứng phase thì phải tạo đúng workload/heap pressure; nhưng vẫn không nên assert **số lượng hay thứ tự GC phases** như hợp đồng của ứng dụng. Collector heuristics được quyền thay đổi quyết định để tối ưu hiệu năng.

## 12. Chương trình Java 17+ số 1: tạo mixed live/garbage và quan sát ba pha

Chương trình này tạo nhiều `Payload` 4 KiB nhưng chỉ giữ lại **mỗi object thứ 10** trong một array static. Các live objects xen lẫn short-lived garbage giúp heap có regions vừa sống vừa chết, thường tạo cơ hội cho evacuation.

Tạo **ShenandoahRelocationProbe.java**:

~~~java
import java.lang.management.ManagementFactory;

public class ShenandoahRelocationProbe {
    static final Payload[] retained = new Payload[6000];
    static volatile long checksum;

    static final class Payload {
        final int id;
        final byte[] bytes = new byte[4096];

        Payload(int id) {
            this.id = id;
            bytes[0] = (byte) id;
        }
    }

    public static void main(String[] args) {
        int kept = 0;

        for (int i = 0; i < 60000; i++) {
            Payload p = new Payload(i);
            checksum += p.bytes[0];
            if (i % 10 == 0) {
                retained[kept++] = p;
            }
        }

        int valid = 0;
        for (Payload p : retained) {
            if (p != null && p.bytes[0] == (byte) p.id) {
                valid++;
            }
        }

        System.out.println("retained=" + valid);
        System.out.println("checksumNonZero=" + (checksum != 0));
        System.out.println("usedHeapPositive="
                + (ManagementFactory.getMemoryMXBean()
                    .getHeapMemoryUsage().getUsed() > 0));
    }
}
~~~

Chạy bằng **Java 17+ runtime có hỗ trợ Shenandoah**:

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahRelocationProbe.java
java -XX:+UseShenandoahGC -Xms64m -Xmx128m -Xlog:gc*:file=shenandoah.log:uptime,level,tags ShenandoahRelocationProbe
~~~

**Stdout đã chạy thực tế trên OpenJDK/Zulu 24.0.2:**

~~~text
retained=6000
checksumNonZero=true
usedHeapPositive=true
~~~

**Kết quả đọc log của lần chạy đã kiểm chứng:**

~~~text
logLines=971
concurrentMarkSeen=True
concurrentEvacuationSeen=True
concurrentUpdateRefsSeen=True
initUpdateRefsSeen=True
finalUpdateRefsSeen=True
~~~

Năm dòng boolean kiểm tra log **là kết quả của script tìm phase names trong file**, không phải stdout do class Java trên in. Tên file và số dòng thay đổi tùy chạy; **không dùng `logLines=971` làm tiêu chí pass cố định**.

Một phần log đã quan sát:

~~~text
[0.008s][info][gc     ] Using Shenandoah
[0.063s][info][gc,start    ] GC(0) Pause Final Mark (unload classes)
[0.064s][info][gc          ] GC(0) Pause Final Mark (unload classes) 0.239ms
[0.064s][info][gc,start    ] GC(0) Concurrent evacuation
[0.065s][info][gc          ] GC(0) Concurrent evacuation 0.673ms
[0.065s][info][gc,start    ] GC(0) Pause Init Update Refs
[0.065s][info][gc          ] GC(0) Pause Init Update Refs 0.039ms
[0.065s][info][gc,start    ] GC(0) Concurrent update references
[0.065s][info][gc          ] GC(0) Concurrent update references 0.377ms
[0.065s][info][gc,start    ] GC(0) Pause Final Update Refs
[0.065s][info][gc          ] GC(0) Pause Final Update Refs 0.043ms
~~~

**Cách diễn giải đúng:**

- Có `Concurrent marking` trong file log, nghĩa là collector đã tracing live graph concurrently.
- `Concurrent evacuation` phản ánh movement/copying công việc của cycle, không phải STW pause 0.673 ms.
- `Concurrent update references` phản ánh việc sửa references concurrently, không phải STW pause 0.377 ms.
- `Pause Init Update Refs` 0.039 ms và `Pause Final Update Refs` 0.043 ms mới là **GC pauses theo phase names**.
- `retained=6000` xác nhận 6.000 Payload giữ trong array static lúc kiểm tra; không chứng minh **chính xác bao nhiêu object trong chúng đã di chuyển**, và cũng không đo GC effectiveness của production workload.

**Lưu ý triển khai:** Workload, CPU, JDK heuristics và độ lớn heap có thể khiến GC chạy khác. Nếu không thấy đủ ba phase ngay lần đầu, không có nghĩa bài toán hoặc mã sai. Có thể chạy lâu hơn/điều chỉnh heap headroom trong **môi trường thí nghiệm** hoặc kiểm tra thêm log; **không chỉnh `-Xmx` của production chỉ để ép log phải chứa tên phase**.

## 13. Chương trình Java 17+ số 2: giữ tính đúng đắn khi mutator đọc/ghi đồng thời

Ví dụ thứ hai tạo một thread **reader** và main thread liên tục **allocate + publish** `Payload` mới vào 64 holders. Reader kiểm tra data bất biến của payload đang reachable. Mục tiêu: cho thấy application Java tiếp tục đọc dữ liệu nhất quán **trong khi Shenandoah vận hành**, không khẳng định một object cụ thể vừa bị relocate.

Tạo **ShenandoahConcurrentDemo.java**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class ShenandoahConcurrentDemo {
    static final int ROOT_COUNT = 64;
    static final Holder[] roots = new Holder[ROOT_COUNT];

    static final class Holder {
        volatile Payload current;
    }

    static final class Payload {
        final int sequence;
        final byte[] data;

        Payload(int sequence) {
            this.sequence = sequence;
            this.data = new byte[8192];
            data[0] = (byte) sequence;
            data[data.length - 1] = (byte) (sequence ^ 0x5a);
        }

        boolean intact() {
            return data[0] == (byte) sequence
                    && data[data.length - 1]
                            == (byte) (sequence ^ 0x5a);
        }
    }

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < ROOT_COUNT; i++) {
            roots[i] = new Holder();
            roots[i].current = new Payload(i);
        }

        AtomicBoolean running = new AtomicBoolean(true);
        AtomicBoolean broken = new AtomicBoolean(false);
        AtomicLong observations = new AtomicLong();

        Thread reader = new Thread(() -> {
            while (running.get()) {
                for (Holder holder : roots) {
                    Payload snapshot = holder.current;
                    if (snapshot != null) {
                        if (!snapshot.intact()) {
                            broken.set(true);
                        }
                        observations.incrementAndGet();
                    }
                }
                Thread.onSpinWait();
            }
        }, "reader");

        reader.start();

        final int allocations = 30_000;
        for (int i = 0; i < allocations; i++) {
            roots[i % ROOT_COUNT].current =
                    new Payload(i + ROOT_COUNT);
            if (i % 1000 == 0) {
                Thread.yield();
            }
        }

        running.set(false);
        reader.join();

        int validRoots = 0;
        for (Holder holder : roots) {
            if (holder.current != null
                    && holder.current.intact()) {
                validRoots++;
            }
        }

        System.out.println("allocated=" + allocations);
        System.out.println("roots=" + ROOT_COUNT);
        System.out.println("validRoots=" + validRoots);
        System.out.println("readerObserved="
                + (observations.get() > 0));
        System.out.println("dataPreserved=" + !broken.get());

        boolean shenandoahBean = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getName().toLowerCase()
                    .contains("shenandoah")) {
                shenandoahBean = true;
            }
        }
        System.out.println("shenandoahBean=" + shenandoahBean);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahConcurrentDemo.java
java -XX:+UseShenandoahGC -Xms64m -Xmx160m -Xlog:gc*:file=shenandoah.log:uptime,level,tags ShenandoahConcurrentDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK/Zulu 24.0.2:**

~~~text
allocated=30000
roots=64
validRoots=64
readerObserved=true
dataPreserved=true
shenandoahBean=true
~~~

### Vì sao `volatile` và atomic types có mặt?

- `Holder.current` là **volatile reference**: main thread công bố payload mới cho reader theo Java Memory Model, tránh data races ở tầng application.
- `Payload.sequence` và `Payload.data` được khởi tạo trong constructor và object được publish phù hợp; `intact()` kiểm tra hai bytes bất biến.
- `AtomicBoolean` và `AtomicLong` điều phối việc dừng reader và đếm observations không bị race.
- `volatile`/`Atomic*` ở đây **không triển khai Shenandoah GC barrier**; các GC barriers do JVM/JIT cung cấp tự động và độc lập với application synchronization.

**Không nhận nhầm công:** Nếu bỏ hết `volatile`/`Atomic*` và code có data race thì **Shenandoah không tự sửa lỗi multithreading của ứng dụng**. Shenandoah đảm bảo memory safety theo Java object model; JMM/synchronization vẫn là trách nhiệm người viết code.

**Giới hạn:** `validRoots=64` và `dataPreserved=true` chỉ chứng minh phép kiểm thử application chạy đúng trên lần chạy này. Chúng **không tự chứng minh mỗi object đã bị evacuation** hoặc mọi lần chạy đều có đúng một chu kỳ GC. Muốn xem pha GC thì đối chiếu log `gc,phases`.

## 14. Đọc GC log: những gì được cam kết và những gì không

Với Unified JVM Logging:

~~~bash
java -XX:+UseShenandoahGC -Xms64m -Xmx128m -Xlog:gc*:file=shenandoah.log:uptime,level,tags ShenandoahRelocationProbe
~~~

Dùng bộ lọc **PowerShell**:

~~~powershell
Select-String -Path .\shenandoah.log -Pattern 'Using Shenandoah','Concurrent marking','Concurrent evacuation','Concurrent update references','Pause '
~~~

Hoặc **Linux/macOS**:

~~~bash
grep -E 'Using Shenandoah|Concurrent marking|Concurrent evacuation|Concurrent update references|Pause ' shenandoah.log
~~~

Khi đọc log:

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| `Using Shenandoah` | JVM đã thực sự chọn Shenandoah |
| `Pause Init Mark` | STW synchronization để bắt đầu marking |
| `Concurrent marking roots` | Root processing concurrent |
| `Concurrent marking` | Tracing live set khi application tiếp tục chạy |
| `Pause Final Mark` | Hoàn tất marking và chuẩn bị cset |
| `Concurrent evacuation` | Di chuyển live objects concurrently |
| `Pause Init Update Refs` | Đồng bộ ngắn trước reference updating |
| `Concurrent update references` | Sửa references cần thiết concurrently |
| `Pause Final Update Refs` | Hoàn tất/cơ hội reclaim from-space |
| `Degenerated GC` | Một chu kỳ bị đẩy sang chế độ STW fallback khi concurrent phase không đủ tiến độ |
| `Full GC` | Fallback stop-the-world/full collection, có thể tạo pause lớn |
| `Allocation Failure` | Dấu hiệu JVM thiếu available space khi allocate, cần xem nguyên nhân và pha GC |

**Không nhìn một dòng `Concurrent ... 20ms` rồi báo rằng STW pause dài 20ms**. Đây là GC work chồng lấn với application. Muốn đánh giá ảnh hưởng thời gian phản hồi, cần so với tracing/metrics của chính ứng dụng, CPU và số lần allocation stall/GC fallback.

**Log levels/tags và phase strings có thể đổi theo JDK mode/version.** Đừng viết code business đòi chính xác một chuỗi tên phase như một public API. Lệnh grep/Select-String trên chỉ phục vụ **thí nghiệm/học tập**, không phải hệ thống giám sát production có schema version độc lập.

## 15. Degenerated GC và Full GC: khi concurrent không kịp

Shenandoah **không thể làm phép màu** nếu heap cực kỳ chật hoặc mutators allocate quá nhanh so với concurrent GC. Khi không có đủ memory để vừa giữ live set vừa evacuation và ứng dụng tiếp tục cấp phát:

~~~text
Application allocation pressure ↑
      |
      v
Shenandoah concurrent cycle đang chạy
      |
      +--> Còn đủ free headroom --> mark/evac/update xong
      |
      +--> Không kịp / to-space thấp / allocation failure
                   |
                   +--> Degenerated GC: hoàn tất phần việc còn lại STW
                   |
                   +--> Full GC nếu cần: thu hồi/compact mạnh hơn STW
                              |
                              +--> có thể OOME nếu live set vượt giới hạn
~~~

**Degenerated GC** là collector phải “tạm ngừng làm concurrent” trong một tình huống áp lực để hoàn tất công việc an toàn. **Full GC** là fallback nặng hơn, thường gây pause đáng kể. Một GC log có `Degenerated GC` hay `Full GC` **không nên được quảng bá là bằng chứng Shenandoah vẫn giữ pause siêu thấp ở mọi điều kiện**.

### Cách giảm rủi ro

- Bố trí **heap headroom** đủ cho live set, allocations đang diễn ra và copying trong evacuation.
- Kiểm tra **allocation rate** và các objects sống quá lâu như cache không giới hạn, leaks, retention bugs.
- Đo **CPU saturation** và số concurrent GC threads; nếu GC không có CPU, nó có thể không thu hồi kịp.
- Kiểm tra container/RSS limits, native memory, direct buffers và class metadata; `-Xmx` chỉ giới hạn Java heap, **không phải toàn bộ process RSS**.
- Không buộc `System.gc()` trong hot path để ép một chu kỳ; có thể gây công việc GC không mong muốn và không sửa nguyên nhân thiếu headroom.

## 16. Flags và tuning vẫn nên dùng trên JDK hỗ trợ Shenandoah

| Tùy chọn | Mục đích | Cảnh báo |
| --- | --- | --- |
| `-XX:+UseShenandoahGC` | Chọn Shenandoah | Một số vendor/build không có collector; kiểm tra runtime |
| `-XX:ShenandoahGCMode=satb` | Chọn SATB, single generation | Theo tài liệu JDK 25, `satb` là default |
| `-XX:ShenandoahGCMode=generational` | Chọn generational | **Product từ JDK 25**, cần build hỗ trợ |
| `-XX:ShenandoahGCHeuristics=adaptive` | Policy adaptive để quyết định chu kỳ/cset | Mặc định; trong generational mode đây là heuristics được hỗ trợ |
| `-Xms<size>` / `-Xmx<size>` | Heap min/initial và max | Điều chỉnh theo memory budget, live set và allocation pressure |
| `-XX:ConcGCThreads=<n>` | Giới hạn concurrent GC worker count | Tuning sâu; không chỉnh trước khi đo CPU/latency |
| `-Xlog:gc*` | Ghi Unified GC log | Log chi tiết có chi phí/dung lượng; chọn mục tiêu đo |
| `-XX:StartFlightRecording=...` | Thu thập JFR | Dùng khi cần phân tích allocation, pauses, CPU và safepoints |

**Không khuyến nghị cấu hình production phức tạp ngay từ đầu.** Một baseline phù hợp là:

~~~bash
java -XX:+UseShenandoahGC -Xmx2g -Xlog:gc*:file=gc.log:time,level,tags -jar application.jar
~~~

Con số `2g` chỉ minh họa; phải chọn theo hệ thống thực tế. Nếu đích cần generational và JDK 25+ có hỗ trợ, thêm `-XX:ShenandoahGCMode=generational` rồi **A/B benchmark** với SATB trong cùng JDK/build.

**Không đưa `-XX:+UnlockExperimentalVMOptions` vào lệnh “bắt buộc” của Shenandoah generational JDK25+** — yêu cầu đó thuộc JDK24 experimental. Với bản đã lên product, flag unlock có thể không cần và gây nhầm lẫn về trạng thái tính năng.

## 17. JMX, JFR, metrics ứng dụng và cách đo “GC có tốt không?”

**JMX** có thể cung cấp các `GarbageCollectorMXBean`:

~~~java
for (GarbageCollectorMXBean bean :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(bean.getName());
    System.out.println(bean.getCollectionCount());
}
~~~

Đoạn code trên đặt trong method có imports `java.lang.management.*`. Tên MXBeans và semantics (chu kỳ, pauses, mode) **phụ thuộc JDK/provider**. `getCollectionCount()` có thể trả **-1** nếu thông tin không hỗ trợ; đừng coi một bean có tên “Shenandoah” là đã hoàn tất evacuation trong mọi cycle.

**JFR** có thể bật qua:

~~~bash
java -XX:+UseShenandoahGC -Xmx1g -XX:StartFlightRecording=filename=shenandoah.jfr,settings=profile -jar application.jar
~~~

Dùng JDK Mission Control hoặc công cụ JFR để phân tích **GC phases, application allocations, CPU và latency**. Tên events và mức độ chi tiết có thể khác giữa distributions/JDK versions; cần test với JDK đang triển khai.

**Ứng dụng cần đo riêng:** p50/p95/p99/p99.9 request latency, throughput, CPU saturation, allocation rate, GC pauses, fallback full GCs và memory footprint. Dù `Pause Final Mark` chỉ vài trăm microseconds, ứng dụng vẫn có thể chậm vì network, disk I/O, locks, CPU contention hoặc allocation stalls.

**Mốc đo cốt lõi:** **Thời gian một concurrent phase ≠ thời gian dừng ứng dụng**. Không thể chọn GC tốt nhất chỉ bằng một screenshot về `Concurrent Mark 1.0ms`.

## 18. Reachability, weak references và thread stacks

Một phần của concurrent marking là xử lý **GC roots** và những references có semantics riêng:

- **Strong references** giữ objects reachable; GC không được reclaim objects sống.
- **WeakReference** không duy trì strong reachability; referent có thể clear theo GC và thời điểm không deterministic.
- **SoftReference/PhantomReference** có semantics khác; xử lý của GC phải tuân theo `java.lang.ref`.
- **ReferenceQueue** phục vụ protocol thông báo của reference API, **không phải nhật ký pha marking/evacuation**.
- **Concurrent root processing** giảm công việc STW cần làm cho thread stacks, compiled code và root sets khi implementation có hỗ trợ. Không nên rập khuôn rằng mọi root đều được scan dừng toàn bộ application như mô tả ở các bản Shenandoah đầu.

**Lập trình viên không nên dùng `finalize()`** để “quan sát Shenandoah”; finalization là cơ chế đã lỗi thời/đang bị loại bỏ. Với tài nguyên như file/sockets hãy dùng `AutoCloseable`/`try-with-resources`, khi cần phantom cleanup thì hiểu đúng `Cleaner` và resource ownership.

**`Reference.reachabilityFence(obj)`** hữu ích trong một số mã xử lý resource native để giữ strong reachability tới một điểm, nhưng **không pin physical address** và không tắt evacuation. Không dựa vào `WeakReference.get()==null` xảy ra trong số ms nhất định để assert “GC đã xong”.

## 19. So sánh Shenandoah với ZGC và các collectors khác

| Câu hỏi | Shenandoah | ZGC | G1 / throughput-oriented GC |
| --- | --- | --- | --- |
| Mục tiêu nổi bật | Concurrent compacting, low pauses | Concurrent compacting, low pauses | Cân bằng throughput/pauses theo chiến lược riêng |
| Marking concurrent? | Có | Có | Tùy pha/collector |
| Relocation concurrent? | Có trong Shenandoah normal cycle | Có | G1 compaction thường thực hiện trong các evacuation pauses |
| Cơ chế reference correctness | Forwarding, load-reference barriers, SATB/store barriers | Colored pointers, barriers/forwarding | Barriers/remembered sets, pause/concurrent strategies khác |
| Generational trên JDK25? | **Có, mode opt-in; default SATB** | **Có, mode còn lại từ JDK24** | G1 đã là generational |
| Có thể STW fallback khi thiếu tài nguyên? | Có | Có cơ chế stalls/fallback riêng | Có |
| Có đảm bảo p99 thấp? | **Không, phải đo workload thật** | **Không** | **Không** |

**Không kết luận một collector luôn thắng**. Shenandoah có performance tradeoffs khác ZGC, G1; tùy Java vendor, CPU, heap, live set, ứng dụng và mục tiêu. Những bit-layout/barrier details là implementation internals, không phải Java-language ABI.

**Không lấy cờ riêng của ZGC đưa sang Shenandoah:** `-XX:+UseZGC` khác `-XX:+UseShenandoahGC`; `ShenandoahGCMode=generational` dành cho Shenandoah; không có cơ sở coi chúng có cùng flags/timeline.

## 20. Những hiểu nhầm phổ biến (và cách sửa)

1. **“Shenandoah được thêm lần đầu ở Java 15.”** Sai: JEP189 ở JDK12; Java15 chỉ là một mốc trong lịch sử phát triển.
2. **“Trên JDK25, Shenandoah generational đã là mặc định.”** Sai theo tài liệu hiện hành: mặc định `satb`; generational là opt-in product mode.
3. **“JDK24 generational mode đã là product.”** Sai: JEP404 ở JDK24 là experimental; JEP521 JDK25 mới product.
4. **“Shenandoah = ZGC nên các cờ giống nhau.”** Sai: hai collectors khác implementation và lộ trình generational.
5. **“Concurrent marking chỉ là một tên khác của Full GC.”** Sai: marking là tracing trong một normal cycle, phần lớn concurrent.
6. **“Marking dọn object chết ngay khi thấy.”** Sai: marking xác định reachability; reclamation tùy cleanup/evacuation.
7. **“SATB là chụp bản sao toàn heap vào RAM.”** Sai: snapshot logic + barrier bookkeeping.
8. **“Không cần barrier vì Java có GC tự động.”** Sai: barriers là một phần quan trọng giúp GC chạy concurrent đúng.
9. **“Load reference barrier giống synchronized.”** Sai: GC barrier không bảo đảm data race freedom theo Java Memory Model.
10. **“Evacuation = xóa garbage.”** Sai: evacuation di chuyển **live objects** để thu hồi regions.
11. **“Shenandoah di chuyển toàn bộ objects mỗi cycle.”** Sai: chọn cset theo heuristics, có khi không cần evacuation.
12. **“Update references xảy ra trước khi có object ở to-space.”** Sai: diễn giải đúng mark → cset → evac → update refs, với coordination phù hợp.
13. **“Có forwarding nên không cần cập nhật references.”** Sai với luồng SATB three-pass; forwarding hỗ trợ truy cập đúng, còn update refs giúp hoàn tất remapping/reclaim.
14. **“Thời gian concurrent phase là STW pause.”** Sai: chỉ các phases “Pause” mới thể hiện GC STW intervals.
15. **“Đã concurrent thì không bao giờ có stop-the-world.”** Sai: Init/Final Mark, Init/Final Update Refs và fallback có pauses.
16. **“Không thấy Concurrent evacuation trong một log nghĩa là GC bị lỗi.”** Sai: collector có thể không chọn cset trong cycle đó.
17. **“Generational young collection không cần quan tâm old objects.”** Sai: old→young edges phải được theo dõi để bảo toàn reachable young objects.
18. **“Đọc/ghi object concurrent qua multiple threads sẽ luôn đúng vì Shenandoah.”** Sai: `volatile`/locks/atomics vẫn cần theo JMM.
19. **“GC di chuyển object khiến `x == alias` thành false.”** Sai: Java object identity được giữ.
20. **“Có thể ghi nhớ địa chỉ object bằng `Unsafe` rồi reuse sau GC.”** Sai: không portable, nguy hiểm, phá memory safety.
21. **“`System.gc()` chắc chắn khiến object X được relocate.”** Sai: runtime quyết định.
22. **“Full GC không xảy ra với Shenandoah.”** Sai: fallback có thể khi thiếu memory/to-space.
23. **“Pause dưới 1ms thì application p99 chắc chắn dưới 1ms.”** Sai: còn allocation stalls/CPU/I/O/locks.
24. **“Tăng `ConcGCThreads` luôn cải thiện độ trễ.”** Sai: GC threads tranh CPU với mutators, cần đo.
25. **“`-Xmx` là toàn bộ RSS của JVM.”** Sai: còn non-heap/native memory.
26. **“Bean name trong JMX là hằng Java API.”** Sai: tên GC beans phụ thuộc VM/version.
27. **“G1, Shenandoah, ZGC có cùng semantics về evacuation.”** Sai: chúng chia sẻ mục tiêu memory reclamation nhưng có algorithms, pauses và barriers khác.
28. **“Lệnh chạy có cờ `UseShenandoahGC` thì mọi JDK đều nhận.”** Sai: distribution có thể không build Shenandoah.
29. **“Có live object sau test nghĩa là nó chắc chắn đã relocate.”** Sai: object vẫn reachable không chứng minh vị trí nội bộ.
30. **“Dùng cờ experimental từ JDK24 cho production JDK25 là cách đúng.”** Sai: chọn các product flags phù hợp bản đang chạy và verify documentation.

## 21. Checklist đánh giá một GC cycle và ứng dụng

| Câu hỏi | Cần kiểm tra |
| --- | --- |
| Runtime thực sự dùng Shenandoah? | Log `Using Shenandoah`, flags của đúng process |
| Java version/vendor? | `java -version`, support matrix của distribution |
| Mode hiện tại? | `ShenandoahGCMode=satb` hay `generational` |
| Có GC roots/live set lớn? | JFR/JMX/heap analysis đúng mục tiêu |
| Có Concurrent Mark? | Log marking; phân biệt STW và concurrent |
| Có selected cset/evacuation? | Log evacuation nếu cycle cần; không ép phải có |
| Có Update References? | Log when evacuation/update flow exists |
| Có Allocation Failure / Degenerated / Full GC? | Điều tra heap headroom và allocation rate |
| Pause distribution? | Theo `Pause ...` events, không cộng toàn bộ GC elapsed |
| Application p99 và throughput? | Metrics của service, không dựa riêng GC log |
| CPU headroom? | GC threads vs mutators và nền tảng/container |
| Heap sizing? | `-Xms/-Xmx`, actual live set, allocation bursts, native memory |
| Concurrent reader/writer có data race? | Java Memory Model, publish/reference ownership đúng |
| JDK nâng phiên bản? | Re-run A/B, không hardcode tên phases và bean names |
| Mode unsupported? | Fail rõ ràng, không âm thầm chọn collector khác mà không theo policy |

## 22. Bài tập thực hành có tiêu chí đạt

**Bài 1 — Đúng timeline.** Ghi lại JEP189, JEP404 và JEP521 theo JDK12, JDK24 và JDK25. **Đạt** khi phân biệt experimental vs product và không nói generational mặc định ở JDK25.

**Bài 2 — Roots và reachability.** Vẽ đồ thị `Holder[]` → `Payload` → `byte[]` và một Payload không còn reference. **Đạt** khi biết object không còn reachable chỉ là *candidate* để reclaim, không được thu hồi trước khi an toàn.

**Bài 3 — SATB.** Một mutator thay `holder.current=another` giữa marking. **Đạt** khi giải thích vì sao collector cần ghi nhận **old reference** của snapshot logic thay vì chỉ xem value mới.

**Bài 4 — Marking vs evacuation.** Cho một region chứa 80% garbage và 20% live objects. **Đạt** khi mô tả marking xác định live set, còn evacuation chuyển live objects ra để reclaim region.

**Bài 5 — Forwarding.** Một thread giữ reference tới object đang được di chuyển. **Đạt** khi giải thích load-reference barrier/forwarding giữ Java reference hợp lệ và identity không đổi.

**Bài 6 — Update refs.** Sau khi copy object từ OLD sang NEW, hai fields vẫn trỏ OLD. **Đạt** khi mô tả concurrent reference updating và final coordination trước khi tái sử dụng from-space.

**Bài 7 — Đọc log thực.** Chạy `ShenandoahRelocationProbe` với `-Xlog:gc*`. **Đạt** khi tìm tên marking, evacuation, update references, và phân biệt từng concurrent duration với pause duration.

**Bài 8 — Không có evacuation.** Cho một test chỉ tạo garbage hoàn toàn unreachable, không còn live objects xen kẽ. **Đạt** khi hiểu cycle có thể reclaim trực tiếp hoặc không có cset, không thể assert mọi GC cycle đều có evacuation.

**Bài 9 — Concurrent reader.** Chạy `ShenandoahConcurrentDemo` và quan sát `dataPreserved=true`. **Đạt** khi chỉ ra vai trò `volatile`/atomics của ứng dụng, không gán chúng thành GC barriers.

**Bài 10 — Failover.** Tăng retained live set tới gần `-Xmx` trong môi trường thí nghiệm có giới hạn. **Đạt** khi nhận diện nguy cơ allocation failures, degenerated/full GC hoặc OOME, không cố ép production tương tự.

**Bài 11 — Mode generational.** Trên JDK25+ có Shenandoah, chạy lần lượt `satb` và `generational`. **Đạt** khi biết mode generational đã production và thử benchmark theo cùng workload/settings.

**Bài 12 — Old→young edge.** Một old cache field giữ young object. **Đạt** khi giải thích remembered metadata/barriers trong generational collector bảo vệ young object reachable.

**Bài 13 — Heap headroom.** So hai thử nghiệm ở `-Xmx128m` và `-Xmx256m` với cùng live set. **Đạt** khi báo cycles, pauses, fallback, throughput và memory footprint thay vì kết luận heap lớn nhất luôn tốt.

**Bài 14 — GC vs application latency.** Một sample có Pause Final Mark 0.2ms nhưng service p99 150ms. **Đạt** khi xem CPU contention, allocation stalls, locks/I/O và traces trước khi đổ lỗi hoàn toàn cho GC pause.

**Bài 15 — Root liveness.** Phân biệt strong, weak và phantom references; thử `WeakReference` trong unit test. **Đạt** khi không assert GC phải clear referent trong thời gian cố định.

**Bài 16 — Nâng JDK.** Một báo cáo cũ cho rằng mode generational Shenandoah đang experimental từ Java24. **Đạt** khi cập nhật JDK25 JEP521 product, kiểm tra mode còn mặc định SATB và không giữ cờ experimental trong lệnh JDK25.

**Bài 17 — Tuning an toàn.** Thiết kế A/B giữa G1, Shenandoah SATB và Shenandoah generational trên cùng JDK25 build. **Đạt** khi báo p99, CPU, GC pauses, allocation stalls, RSS, throughput và error rate, không so chỉ bằng một GC cycle đơn lẻ.

## 23. Nguồn chính thức và tài liệu còn hữu ích

- [JEP 189 — Shenandoah: A Low-Pause-Time Garbage Collector (Experimental)](https://openjdk.org/jeps/189): lịch sử đưa Shenandoah vào OpenJDK từ JDK12.
- [OpenJDK Shenandoah Wiki — Main](https://wiki.openjdk.org/display/shenandoah/Main): mô tả SATB cycle gồm concurrent mark, evacuation và update references, cset, forwarding/barriers, pauses và fallback. **Tài liệu có phần mô tả kiến trúc lịch sử; không lấy mọi tên phase/bits cố định cho các JDK sau.**
- [JEP 404 — Generational Shenandoah (Experimental), JDK24](https://openjdk.org/jeps/404): bước thử nghiệm nhiều generations.
- [JEP 521 — Generational Shenandoah, JDK25](https://openjdk.org/jeps/521): chuyển generational mode thành product feature.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseShenandoahGC`, `-XX:ShenandoahGCMode=satb/generational` và heuristics. **Lệnh trên chỉ có hiệu lực nếu Java build có Shenandoah.**
- [Inside Java — What's New in JDK25](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): ghi rõ Generational Shenandoah production ở JDK25.
- [Red Hat — OpenJDK 25 release notes](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): lệnh opt-in product generational, mốc JDK24 experimental.
- [OpenJDK/Shenandoah source](https://github.com/openjdk/shenandoah): triển khai concurrent marking, evacuation, update references, barriers, generational mode; **không phải public Java API contract**.
- [Red Hat Developer — Concurrent Reference Processing](https://developers.redhat.com/articles/2021/05/20/shenandoah-garbage-collection-openjdk-16-concurrent-reference-processing): hiểu concurrent reference processing và load-reference barrier, có lưu ý mốc JDK.
- [Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): API nhận diện GC beans và quan sát cycles/counts.
- [Java SE 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap memory usage, dữ liệu quản lý JVM.

**Ghi nhớ:** Trong Shenandoah, **concurrent marking** tìm live objects trên đồ thị references, **concurrent evacuation** di chuyển objects sống để reclaim heap regions, và **concurrent update references** điều chỉnh các pointers còn trỏ tới vị trí cũ để có thể thu hồi from-space. **SATB write barriers** bảo toàn snapshot logic khi Java code thay references; **load-reference barriers/forwarding** giữ object access đúng trong lúc di chuyển. Những phases concurrent **không phải STW pauses**, và có cycle không cần evacuation. **JDK25+ có generational Shenandoah product opt-in**, trong khi SATB vẫn là mode mặc định theo docs đã kiểm chứng. Chỉ quyết định bật/tune GC sau khi đo **application latency, heap headroom, CPU và GC fallback** trong đúng môi trường.
