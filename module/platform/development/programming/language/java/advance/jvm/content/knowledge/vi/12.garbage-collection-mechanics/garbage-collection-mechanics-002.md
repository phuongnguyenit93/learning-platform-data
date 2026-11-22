# Phân mảnh bộ nhớ và đánh đổi giữa di chuyển đối tượng với chi phí cập nhật tham chiếu

## Mục tiêu bài học

Một Java heap có thể còn nhiều byte rảnh nhưng vẫn khó phục vụ một yêu cầu cấp phát mới nếu **các khoảng trống không phù hợp với kích thước hoặc chính sách của bộ cấp phát**. Đó là vấn đề **phân mảnh bộ nhớ** (*memory fragmentation*). Garbage collector (GC) có thể giảm phân mảnh bằng cách **di chuyển/thu gọn các đối tượng đang sống**, nhưng khi vị trí của một đối tượng thay đổi, runtime phải bảo đảm **mọi tham chiếu hợp lệ vẫn tìm đúng đối tượng ấy**. Việc sao chép dữ liệu, xác định vị trí mới, sửa hoặc điều hướng tham chiếu và đồng bộ với application threads tạo ra một đánh đổi thực sự về CPU, memory bandwidth, thời gian tạm dừng và mức headroom của heap.

Bài này đặt trọng tâm vào **cơ chế GC và HotSpot**, không đánh đồng Java reference với địa chỉ vật lý bất biến. Sau bài học, bạn có thể:

- Phân biệt **external fragmentation**, **internal fragmentation**, free-space topology, wasted capacity và tổng heap còn rảnh.
- Giải thích **mark–sweep**, **mark–compact**, **copying/evacuation** và cách mỗi chiến lược xử lý khoảng trống.
- Mô tả vì sao di chuyển một object buộc collector phải xử lý **root references, references trong objects và array elements**, đôi khi cả references bên ngoài vùng thu gom.
- Phân biệt **forwarding information**, relocation maps, barriers, remembered sets, card tables và GC-root metadata; không coi chúng là cùng một cơ chế.
- Hiểu tại sao **một object có rất nhiều references** có thể rẻ để copy payload nhưng đắt để duy trì reachability/references, trong khi **object rất lớn có ít references** có thể đắt để copy dù cập nhật tham chiếu ít.
- So sánh những hướng triển khai của **Serial/Parallel, G1, ZGC, Shenandoah** theo phiên bản và collector cụ thể.
- Hiểu trường hợp **G1 humongous objects**, vùng nhớ còn dư nhưng không sử dụng được, evacuation failure và Full GC.
- Dùng Java 17+ chạy mô phỏng compaction và ví dụ chứng minh aliasing/identity vẫn đúng, rồi đọc GC logs mà không dựa vào thời điểm GC không xác định.
- Đo đúng bằng **GC logs, JFR, jcmd, JDK Mission Control**, tránh xem heap usage cao là bằng chứng chắc chắn của fragmentation.

## 1. Từ đâu xuất hiện phân mảnh?

Giả sử một allocator có tám ô bằng nhau. Sau khi nhiều object được tạo rồi trở nên unreachable, sơ đồ giả lập có thể thành:

~~~text
Trước thu gom / sau khi xác định object đã chết:

index:  0   1   2   3   4   5   6   7
        +---+---+---+---+---+---+---+---+
state:  | A | . | B | . | C | . | D | . |
        +---+---+---+---+---+---+---+---+

A, B, C, D: object còn sống
.         : ô nhớ rảnh

Tổng trống: 4 ô
Khoảng trống liền nhau lớn nhất: 1 ô
Yêu cầu: cấp phát object cần 3 ô liền nhau
~~~

Đây là **mô hình khối nhớ giả lập**, không phải cách HotSpot bắt buộc phân bổ mọi object trong heap. Với allocator yêu cầu một vùng liền 3 ô, tổng 4 ô rảnh chưa đủ: **không có khoảng trống đủ dài**. Đó là ví dụ của **external fragmentation**.

Nếu di chuyển B, C, D sát A:

~~~text
Sau compaction:

index:  0   1   2   3   4   5   6   7
        +---+---+---+---+---+---+---+---+
state:  | A | B | C | D | . | . | . | . |
        +---+---+---+---+---+---+---+---+

Tổng trống: 4 ô (không đổi)
Khoảng trống liền nhau lớn nhất: 4 ô
Yêu cầu 3 ô bây giờ có thể đáp ứng
~~~

**Compaction không tự tạo thêm bytes rảnh từ hư không.** Nó **sắp xếp lại live objects** để gộp những khoảng trống thành các vùng thuận lợi cho allocation. Nếu các object được xác định chết từ trước và đã reclaim, tổng free bytes có thể giữ nguyên qua bước di chuyển; khác biệt nằm ở **hình dạng free space**.

### External fragmentation

Là tình trạng free space bị chia thành nhiều đoạn nhỏ hoặc thành các vùng không đáp ứng tiêu chí cấp phát. Trong một heap dùng **regions**, vấn đề còn liên quan đến khả năng tìm đủ contiguous regions, chính sách chọn region và số region bị giữ bởi live/pinned/humongous objects.

### Internal fragmentation

Là phần bytes bị tiêu thụ hoặc để trống **bên trong đơn vị allocation** dù không chứa dữ liệu hữu ích cho ứng dụng. Ví dụ:
- Padding do object alignment.
- Các slot bị dự trữ nhưng chưa dùng trong một block/array capacity.
- Phần dư của region cuối cùng được dành riêng cho một object lớn, không thể dùng cho object khác theo chính sách allocator đó.

**Không đồng nhất** mọi padding với external fragmentation. External là **khoảng trống giữa các allocations khó sử dụng**; internal là **phần dư trong allocation unit hoặc reserved region**.

### “Heap rảnh” có nhiều nghĩa

| Chỉ số | Nó nói gì | Điều chưa thể kết luận |
| --- | --- | --- |
| Committed heap − used heap | Khoảng chênh theo cách VM báo used/committed | Free slots có phù hợp một allocation lớn không? |
| Total free bytes trong một vùng | Tổng không gian chưa dùng | Có đủ contiguous space không? |
| Largest contiguous free block | Khối rảnh lớn nhất theo allocator | Có thể allocate sau GC/expansion hay không? |
| Number of free regions | Số regions hoàn toàn rảnh | Có đủ một dải regions liền cho humongous object? |
| Live-set size | Bao nhiêu memory phải giữ object sống | Bao nhiêu copy/update work cần làm? |
| Heap fragmentation metric của GC cụ thể | Mức rời rạc theo heuristic của collector | Có cùng nghĩa với metric collector khác không? |

Đừng dùng một số `Runtime.freeMemory()` để “chứng minh” heap fragmentation. API báo số liệu ở phạm vi runtime, không thể hiện chính xác free-block topology của mọi collector.

## 2. Tại sao mark–sweep có thể để lại các lỗ?

Cơ chế **mark–sweep** cổ điển:

1. Bắt đầu từ **GC roots** và đánh dấu các objects reachable theo graph.
2. Quét vùng bộ nhớ/metadata cần xử lý.
3. Reclaim các object không còn live.
4. Giữ các live objects tại vị trí cũ.

Khi nhiều object chết nằm xen giữa những object sống, mark–sweep có thể để lại **nhiều free holes**.

~~~text
Trước:  [A][X][B][Y][C][Z][D]   X/Y/Z unreachable
Sweep:  [A][ ][B][ ][C][ ][D]

Live objects vẫn ở vị trí cũ.
Free list hoặc allocator cần quản lý các holes.
~~~

**Ưu điểm có điều kiện:** không phải copy toàn bộ live-object bytes chỉ để compact. Những object không được di chuyển không cần sửa reference vì địa chỉ của chúng giữ nguyên (bỏ qua những xử lý GC khác).

**Đổi lại:** allocator có thể phải dùng free lists, phân loại blocks, coalescing và gặp external fragmentation. Các kỹ thuật chống phân mảnh như gộp adjacent free blocks giúp ích, nhưng **không thể gộp qua một live object nằm giữa** nếu không di chuyển nó.

Không phải GC không di chuyển nào cũng luôn gặp fragmentation nghiêm trọng: allocator có thể dùng size classes, segregated free lists, region management, allocation policies và GC heuristics phù hợp. Cũng không phải một GC có giai đoạn sweeping thì chắc chắn “không compact ở nơi nào”.

## 3. Mark–compact: gộp free space bằng cách di chuyển live objects

**Mark–compact** thường gồm:
1. Xác định objects live.
2. Tính hoặc xác định vị trí đích cho các live objects.
3. Di chuyển object contents/metadata khi cần.
4. Bảo đảm references đang trỏ tới objects đó được đổi/điều hướng để trỏ đúng instance.
5. Có một vùng free space lớn hơn hoặc các vùng rảnh phù hợp sau compact.

~~~text
Before:
  root1 ----> [A @slot0]  [hole]  [B @slot2]  [hole]
                              \____________/
                               phân mảnh

Destination planning:
  A: slot0 -> slot0
  B: slot2 -> slot1

After:
  root1 ----> [A @slot0][B @slot1][free][free]
                           ^
                           |
                   old refs to B được xử lý
~~~

**Lợi ích:**
- Có thể giảm external fragmentation, giúp phục vụ yêu cầu allocation lớn.
- Sau compact, một dạng bump-pointer allocation có thể hiệu quả.
- Object locality có thể thay đổi theo hướng tích cực nếu allocator bố trí tốt, nhưng không hứa tất cả objects liên quan nằm cạnh nhau.

**Chi phí:**
- Đọc/ghi bytes của live objects cần di chuyển, tiêu thụ CPU và memory bandwidth.
- Tìm/ghi vị trí mới hoặc quản lý forwarding metadata.
- Xử lý các references tới objects đã di chuyển.
- Phối hợp với application threads, có thể cần **stop-the-world (STW)** hoặc barriers/handshakes đối với collector concurrent.
- Có thể cần vùng đích hoặc metadata phụ; thuật toán in-place và copying có chi phí memory headroom khác nhau.

**Không có một “số lần cập nhật references = số objects di chuyển” bắt buộc.** Một object được nhiều root/fields/array slots tham chiếu có thể có hàng triệu references. Collector phải bảo đảm mọi reference hợp lệ được giải quyết đúng, nhưng cách làm có thể là cập nhật từng slot, remap khi đọc, remembered sets hoặc cơ chế khác tùy GC.

## 4. Copying collection và evacuation

Một collector có thể chọn **copying/evacuation**: chuyển live objects từ các vùng nguồn sang các vùng đích khác, rồi **reclaim toàn bộ vùng nguồn** khi điều kiện an toàn thỏa mãn.

~~~text
Source region (CSet):             Destination region:

[A live][B dead][C live]  ==>    [A'][C'][free ...]
           |                        ^
           |                        |
           +-- nếu references trỏ A/C
               phải được chuyển hướng tới A'/C'
~~~

Lợi thế của evacuation:
- Để lại vùng nguồn trống hoàn toàn, phù hợp **region reuse**.
- Tránh giữ nhiều holes trong chính vùng nguồn được evacuate thành công.
- Có thể thu gom từng tập regions, thay vì luôn compact toàn heap.

Chi phí:
- **Copy live bytes** của các regions được chọn.
- **Destination space/headroom** để chứa live objects khi chúng đang được di chuyển.
- **Reference fixing/barrier work**.
- Có thể có **evacuation failure** nếu không đủ vùng đích hoặc bị giới hạn pinning/collector-specific constraints.
- Nếu selection kém và region rất nhiều live bytes, chi phí copy lớn nhưng dung lượng reclaim nhỏ.

### Tại sao “garbage-first” chú ý tỷ lệ garbage?

Giả sử hai regions có cùng size:
- Region P: chỉ 10% live, 90% garbage.
- Region Q: 95% live, 5% garbage.

Nếu evacuate P, collector phải copy ít live bytes và reclaim nhiều memory. Nếu evacuate Q, phải copy rất nhiều bytes để lấy lại ít free space. Đây là một tiêu chí trực giác khiến region-based collectors ưu tiên vùng **nhiều garbage và ít chi phí kết nối**. Quyết định thực tế vẫn dựa nhiều heuristic khác như reference scanning, pause targets và remembered-set cost.

## 5. Di chuyển object không được làm thay đổi identity

Trong Java source, một biến reference **không phải địa chỉ heap bất biến do ứng dụng quản lý**. Ví dụ:

~~~java
Person p = new Person();
Person alias = p;
System.out.println(p == alias); // true
~~~

Đây là đoạn minh họa cần class `Person` phù hợp. Nếu GC di chuyển object mà p và alias đang tham chiếu, Java vẫn phải quan sát **`p == alias` là true** sau khi collection, miễn không có phép gán lại biến làm thay đổi references.

Collector có thể đổi nơi lưu object vật lý từ “old address” sang “new address”, nhưng **logical object identity phải được bảo toàn**:
- Các reference comparisons/`==` cho cùng object vẫn đúng.
- `Object.equals` nếu không override vẫn có semantics identity.
- `System.identityHashCode(object)` phải nhất quán trong lifetime của object theo contract, không đơn giản “đổi vì địa chỉ di chuyển”.
- Monitor/lock state và object metadata phải giữ đúng semantics; cách bảo toàn thông tin phụ thuộc HotSpot/collector.
- Field contents phải được giữ đúng theo Java Memory Model và các quy tắc GC.

**Không lấy `System.identityHashCode` làm địa chỉ RAM**, cũng không dùng `toString()` mặc định để đo vị trí object. Hash code không phải pointer; có thể trùng giữa objects khác nhau.

## 6. Những tham chiếu nào bị ảnh hưởng khi object di chuyển?

Một object đang được tham chiếu có thể có những đường đi đến từ:

- **Local variables/operand stack** trong các JVM frames của threads còn hoạt động.
- **Instance reference fields** của những objects khác.
- **Static reference fields** của class/interface runtime.
- **Reference-array elements**.
- **JNI/native handles** hoặc các roots/runtime references được VM quản lý.
- Các cấu trúc nội bộ GC/VM, code metadata và các loại references có contract riêng.

~~~text
Root: local r -----------+
                         |
Root: static cached -----+----> [Customer OLD]
                         |         |
Object A.ref ------------+         +--> [Address]
                         |
Array refs[19] ----------+

Di chuyển Customer OLD -> Customer NEW:

Root r ------------------+
                         |
static cached -----------+----> [Customer NEW]
                         |         |
Object A.ref ------------+         +--> [Address]
                         |
Array refs[19] ----------+
~~~

**Sơ đồ mô tả kết quả logic**, không buộc HotSpot cập nhật từng root/field ngay cùng một thời điểm. Một collector concurrent có thể tạm dùng forwarding metadata, load barriers, remapping và cơ chế đảm bảo mọi truy cập của mutator nhìn thấy object chính xác khi relocation đang diễn ra.

### Giá của reference update phụ thuộc graph

Nếu object X chỉ được tham chiếu bởi một reference trong root set, số logical references cần xử lý có thể nhỏ. Nếu X là “hot shared object” xuất hiện trong một triệu elements của arrays/collections, có thể có rất nhiều edges tới X. Collector vẫn phải bảo toàn aliasing sau relocation; có thể trả chi phí quét/cập nhật/remap tương ứng.

Do đó **số object di chuyển**, **bytes copy**, **số references/edges liên quan**, **cách references phân bố giữa regions** và **số roots** là những biến số khác nhau, ảnh hưởng khác nhau tới CPU và pause.

## 7. Forwarding: biết object đã chuyển từ đâu tới đâu

Để chuyển hướng references, một moving collector thường cần cách tìm **vị trí mới** từ **vị trí cũ**. Có nhiều chiến lược:
- Forwarding information được ghi hoặc mã hóa ở nơi thích hợp.
- Bảng ánh xạ/relocation metadata theo phạm vi collector.
- Tham chiếu có metadata hoặc dùng read/load barriers để chuyển đến đối tượng mới.
- Cập nhật reference slots vào lúc quét hoặc vào thời điểm mutator đọc reference.

Sơ đồ đơn giản:

~~~text
Old location -> New location

0x1000 -> 0x8000  (A moved)
0x2000 -> 0x8020  (B moved)
0x3000 -> 0x9000  (C moved)

reference slot holding old B
    |
    +--> forwarding/relocation info
                 |
                 v
         valid reference to new B
~~~

Đây là **địa chỉ giả lập**, không phải địa chỉ VM thật. Reference representation của HotSpot có thể dùng compressed oops hoặc metadata riêng; không dựa vào một pointer width duy nhất.

### Vì sao không thể chỉ copy object rồi bỏ qua references?

Nếu chỉ copy B sang một vị trí mới mà các references còn chỉ tới memory location cũ, những references đó có thể bị dangling hoặc chỉ vào storage đã được tái sử dụng. JVM cần một giao thức GC để mọi reference hợp lệ tiếp tục truy cập đúng B.

Điều đó **không đồng nghĩa API Java cho phép bạn thấy từng reference đang được sửa**. Moving GC là việc VM quản lý; source Java tiếp tục làm việc với object identity, không phải raw heap addresses.

### Forwarding chưa đủ cho concurrent collection

Khi application threads (mutators) vẫn chạy trong lúc collector di chuyển objects, có các race có thể xảy ra:
- Mutator đọc reference cũ ngay sau khi collector chuyển object.
- Mutator ghi field vào object đang hoặc đã di chuyển.
- Một root/reference được cập nhật đồng thời với GC.
- Reference nội bộ từ vùng không thu gom trỏ đến vùng đang evacuate.

Collector concurrent phải phối hợp bằng **barriers**, synchronization/handshakes, forwarding/remapping và ordering thích hợp. Chỉ tạo mapping old→new không đủ để chứng minh algorithm thread-safe.

## 8. Roots, oop maps, remembered sets và card tables khác nhau

Các thuật ngữ dễ bị nhập nhằng:

| Khái niệm | Mục đích chính | Không phải |
| --- | --- | --- |
| **GC roots** | Các điểm bắt đầu reachability như thread references, static roots, handles... | Danh sách mọi reference field trong heap. |
| **Oop maps/stack maps nội bộ** | Giúp VM nhận biết vị trí references trong compiled/interpreted frames ở những safepoints thích hợp | Java API công khai và cố định cho mọi collector. |
| **Forwarding information** | Xác định hoặc dẫn đến vị trí mới của object đã di chuyển | Tập hợp tất cả inbound reference edges. |
| **Card table** | Theo dõi các phần bộ nhớ mà writes có thể làm thay đổi quan hệ references | Danh sách chính xác từng reference riêng lẻ. |
| **Remembered set** | Tập vị trí/region có thể chứa references từ ngoài tới một vùng/các vùng cần thu gom | Công cụ tự sửa mọi references mà không cần scan. |
| **Read/load barrier** | Xử lý một số điều kiện GC khi mutator đọc reference, có thể liên quan relocation/remapping | Luôn có trên mọi collector, mọi JVM. |
| **Write barrier** | Hỗ trợ GC theo dõi updates khi mutator ghi refs, ví dụ marking hoặc region cross-refs | Không phải keyword `volatile` trong Java source. |

**Oop** là thuật ngữ HotSpot cho *ordinary object pointer* hoặc biểu diễn object reference. Oop maps phục vụ VM biết nơi nào cần xử lý như object refs khi quét stack, không đồng nghĩa source variable chắc chắn nằm ở một stack address cụ thể nếu JIT đã tối ưu.

### Remembered set giảm quét toàn heap như thế nào?

Giả sử G1 đang evacuate một **collection set (CSet)** gồm một số regions. References đến objects trong CSet có thể nằm ở:
- Roots/frames/static state.
- Chính các objects thuộc CSet.
- Các objects ở **regions ngoài CSet**.

Nếu muốn biết incoming references từ ngoài mà phải quét mọi object của toàn heap ở mỗi young GC, chi phí rất lớn. **Remembered sets/card marking** giúp giới hạn những vị trí cần xem, nhưng vẫn cần thực hiện work để định vị các slots/relationships thực sự.

G1 dùng **post-write barrier** để theo dõi cross-region changes và duy trì remembered-set-related metadata theo thuật toán collector. Đây là **GC bookkeeping**, không phải application synchronization. Chi phí của nó tồn tại cả khi không diễn ra GC pause.

Không nói “remembered set chứa mọi vị trí chính xác và luôn update ref tự động”: các entries có thể là **coarse-grained card locations** và yêu cầu scan để tìm references cụ thể.

## 9. Ví dụ Java 17+: mô phỏng compaction và cập nhật tham chiếu

Để có kết quả tái lập được mà **không phụ thuộc GC timing**, ta tạo mô hình nhỏ:
- Một array `slots` mô phỏng tám ô heap; -1 là slot trống.
- `edges[i]` mô phỏng một reference từ object tại ô i tới ô khác.
- `roots` mô phỏng những vị trí root đang trỏ tới objects.
- `forward[oldIndex] = newIndex` là relocation table.
- Sau compact, phải sửa cả root indices và edges để giữ đúng đồ thị.

**Đây chỉ là mô hình thuật toán bằng Java**, không phải cách JVM phơi bày/sửa raw memory addresses.

Tạo file **`CompactionSimulation.java`**:

~~~java
import java.util.Arrays;

public class CompactionSimulation {
    static int largestRun(int[] slots) {
        int best = 0;
        int current = 0;
        for (int slot : slots) {
            if (slot == -1) {
                current++;
                best = Math.max(best, current);
            } else {
                current = 0;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        final int empty = -1;

        // Bốn live objects tại các index 0, 2, 4, 6.
        int[] slots = {10, empty, 20, empty,
                       30, empty, 40, empty};

        // Object tại 0 -> 4; object tại 2 -> 6.
        int[] edges = {4, empty, 6, empty,
                       empty, empty, empty, empty};

        // Hai root references, trỏ index 0 và index 4.
        int[] roots = {0, 4};

        System.out.println("before=" + Arrays.toString(slots));
        System.out.println("largestFreeBefore=" + largestRun(slots));

        int[] forward = new int[slots.length];
        Arrays.fill(forward, empty);

        int[] packed = new int[slots.length];
        int[] newEdges = new int[slots.length];
        Arrays.fill(packed, empty);
        Arrays.fill(newEdges, empty);

        int liveCount = 0;
        int movedCount = 0;

        // Bước 1: tính vị trí mới và chuyển dữ liệu.
        for (int oldIndex = 0; oldIndex < slots.length; oldIndex++) {
            if (slots[oldIndex] != empty) {
                forward[oldIndex] = liveCount;
                packed[liveCount] = slots[oldIndex];

                if (oldIndex != liveCount) {
                    movedCount++;
                }
                liveCount++;
            }
        }

        // Bước 2: sửa root references.
        for (int i = 0; i < roots.length; i++) {
            roots[i] = forward[roots[i]];
        }

        // Bước 3: sửa links bên trong object được chuyển.
        for (int oldIndex = 0; oldIndex < slots.length; oldIndex++) {
            if (slots[oldIndex] != empty) {
                int newIndex = forward[oldIndex];
                int oldTarget = edges[oldIndex];
                newEdges[newIndex] =
                        oldTarget == empty ? empty : forward[oldTarget];
            }
        }

        System.out.println("after=" + Arrays.toString(packed));
        System.out.println("roots=" + Arrays.toString(roots));
        System.out.println("links=" + Arrays.toString(
                Arrays.copyOf(newEdges, liveCount)));
        System.out.println("moved=" + movedCount);
        System.out.println("largestFreeAfter=" + largestRun(packed));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CompactionSimulation.java
java CompactionSimulation
~~~

**Stdout chính xác:**

~~~text
before=[10, -1, 20, -1, 30, -1, 40, -1]
largestFreeBefore=1
after=[10, 20, 30, 40, -1, -1, -1, -1]
roots=[0, 2]
links=[2, 3, -1, -1]
moved=3
largestFreeAfter=4
~~~

**Giải thích từng phần:**

1. Ban đầu có 4 empty slots nhưng largest contiguous free run chỉ dài 1.
2. `forward` nhận mappings 0→0, 2→1, 4→2, 6→3. Có **3 objects đổi vị trí**.
3. `roots` từ [0,4] thành **[0,2]** để root thứ hai vẫn trỏ đến object ID 30, không bị nhầm với object khác.
4. Edge của object ID 10 trước đây trỏ old index 4, nay phải trỏ **new index 2**. Edge của ID 20 trỏ old index 6, nay thành **new index 3**.
5. `links=[2,3,-1,-1]` cho thấy **reference updates** độc lập với việc copy dữ liệu.
6. Sau compact vẫn có 4 free slots, nhưng contiguous run dài 4, giúp phục vụ allocation mới cần ba ô.

**Cố ý không mô phỏng** GC roots thực, object identity metadata, concurrency/barriers, JNI handles, remembered sets, dynamic object sizes hoặc GC heuristics. Chương trình chỉ minh họa **logic old→new mapping và cập nhật edges**.

### “Quên update reference” là lỗi gì trong mô hình?

Nếu ta chuyển ID 30 từ index 4 sang index 2 nhưng giữ root value 4, root sẽ nhìn vào **slot trống** sau compact. Nếu giữ edge từ ID 10 tới index 4, đồ thị object logic đã bị hỏng. GC thật không được để Java program quan sát tình trạng sai này sau một collection hoàn tất.

## 10. Ví dụ Java 17+: identity không đổi khi GC hoạt động

Ứng dụng Java **không cần và không được** tự sửa reference values khi HotSpot di chuyển object. Một ví dụ kiểm tra semantics xác định:

Tạo file **`IdentityInvariantDemo.java`**:

~~~java
public class IdentityInvariantDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Node first = new Node("first");
        Node second = new Node("second");

        first.next = second;
        Node alias = first;

        // Không gọi System.gc(): bài kiểm tra không dựa GC timing.
        System.out.println("sameRoot=" + (first == alias));
        System.out.println("sameTarget=" + (first.next == second));

        first = null;
        System.out.println("aliasLabel=" + alias.label);
        System.out.println("linkedLabel=" + alias.next.label);
        System.out.println("sameTargetAfter=" + (alias.next == second));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 IdentityInvariantDemo.java
java IdentityInvariantDemo
~~~

**Stdout chính xác:**

~~~text
sameRoot=true
sameTarget=true
aliasLabel=first
linkedLabel=second
sameTargetAfter=true
~~~

Lưu ý:
- Dòng `first = null` chỉ thay đổi **một local reference**, không làm object first biến mất khi `alias` vẫn trỏ tới nó.
- Ngay cả khi một GC di chuyển objects ở thời điểm thích hợp, tính đúng đắn của references và comparisons phải được bảo toàn.
- Chạy chương trình này **không chứng minh đã có một GC hoặc một relocation xảy ra**. Nó chỉ kiểm tra semantics Java mà GC phải duy trì.

Không dùng `System.gc()` như bảo đảm sẽ có compact hay một object sẽ bị chuyển chỗ. Lời gọi này không hứa một GC cycle cụ thể, càng không hứa di chuyển một instance riêng.

## 11. Chi phí di chuyển: không chỉ số objects

Các chiều chi phí thường cần xét riêng:

| Đại lượng | Ảnh hưởng chủ yếu |
| --- | --- |
| **Bytes của live objects cần copy** | Memory bandwidth, CPU cycles, cache traffic |
| **Số object cần relocate** | Forwarding/relocation bookkeeping, header/metadata handling |
| **Số reference slots/root slots cần xử lý** | Scan, reference remapping, update work |
| **Số cross-region edges** | Remembered-set/card scanning hoặc overhead tương đương |
| **Tỷ lệ live trong vùng chọn** | Dung lượng reclaim trên mỗi byte copy |
| **GC-headroom/destination capacity** | Khả năng evacuation thành công và áp lực bộ nhớ |
| **Mutator write/read rate** | Barrier overhead và độ phức tạp khi GC chạy đồng thời |
| **Pinning/humongous regions** | Hạn chế khả năng di chuyển/reclaim một số vùng |
| **Pause-time/CPU budget** | Tập regions được chọn; mức concurrent work chấp nhận được |

### Hai tình huống đối lập

**Tình huống A: object lớn, ít inbound references.** Một `byte[]` nhiều MB có thể chỉ được một cache entry tham chiếu. Copy toàn bộ payload có chi phí memory bandwidth lớn; cập nhật một reference logic có thể tương đối rẻ.

**Tình huống B: object nhỏ, rất nhiều inbound references.** Một object vài chục bytes được hàng trăm nghìn array slots trỏ tới. Copy object payload rất rẻ, nhưng GC phải đảm bảo nhiều references vẫn đúng. Những thuật toán dùng remapping/barriers có thể trả chi phí theo cách khác so với cập nhật tất cả slots tại STW.

**Không tự khẳng định O(R) exact cho mọi GC:** một thuật toán trực tiếp quét và sửa tất cả inbound slots có work tỷ lệ với số slot xét; collector khác có thể lazy-fix và phân bổ chi phí qua mutator reads. Complexity và constant factors phụ thuộc implementation.

### Chi phí copy và locality

Di chuyển objects có thể cải thiện locality trong một số trường hợp nhưng cũng có thể:
- Làm tăng cache traffic và áp lực lên memory bandwidth.
- Gây dirtying nhiều memory pages.
- Gây page faults/memory commit nếu cần destination pages.
- Làm cache lines của dữ liệu cũ mất giá trị.
- Đòi hỏi synchronization/safepoints để các threads không thấy object sai trạng thái.

Không mặc định “compact luôn tăng tốc truy cập”: việc nhóm objects mới tốt đến đâu còn tùy collector, đường truy cập và workload.

## 12. G1: chọn regions để evacuation và compact từng phần

**G1 (Garbage-First)** là collector dạng **region-based, generational** trong HotSpot. Heap được chia thành các **regions**; eden/survivor/old là những tập regions theo vai trò, không bắt buộc mỗi generation là một dải địa chỉ vật lý liên tục.

Trong các young/mixed collections, G1 chọn **Collection Set (CSet)** gồm những regions mục tiêu rồi:
1. Xác định objects live phù hợp.
2. Copy/evacuate live objects từ CSet sang các destination regions thích hợp.
3. Xử lý references từ roots và ngoài CSet, sử dụng remembered-set/card tracking và mechanisms liên quan.
4. Sau evacuation thành công, **reclaim các source regions** để tái dùng.

Việc di chuyển live objects giúp compact vùng thu gom theo từng đợt. G1 cố cân bằng **dung lượng reclaim** và **pause-time target**, nhưng target chỉ là mục tiêu mềm, **không phải deadline cứng**.

### Một region nhiều live objects không phải ứng viên lý tưởng

Evacuate region 95% live đòi copy gần như cả region mà chỉ thu hồi ít garbage. Do đó collector dùng live fraction và connectivity/work prediction để đánh giá collection efficiency. Nếu heap luôn có rất nhiều long-lived objects, copy chúng trong mỗi lần collection cũng tốn kém.

### Remembered set là phần đánh đổi

G1 tránh quét toàn bộ heap khi collect một số regions, nhưng phải trả chi phí **duy trì và quét remembered sets**. Write barriers và card refinement có thể tăng CPU overhead ở application/GC threads. Một workload có nhiều cross-region references hoặc mutation dày đặc có thể làm tăng loại chi phí này.

### G1 evacuation failure

Khi destination space không đủ cho các objects cần chuyển hoặc có ràng buộc collector-specific, evacuation có thể thất bại. G1 có những đường xử lý failure và có thể dẫn đến **Full GC** với compaction đắt tiền nếu áp lực heap nghiêm trọng.

Đừng diễn giải mọi log có chữ “evacuation” là lỗi: **evacuation là hoạt động bình thường của G1**, còn `Evacuation Failure` mới là tín hiệu đáng điều tra.

## 13. Humongous objects: trường hợp phân mảnh đặc biệt của G1

Theo tài liệu G1, một object cỡ **bằng hoặc lớn hơn một nửa region** được xem là **humongous**. Nó thường được cấp vào một chuỗi **contiguous humongous regions** ở old generation, không di chuyển theo những evacuation pauses thông thường.

Ví dụ **minh họa** với region size 2 MiB:
- Threshold humongous khoảng 1 MiB (kích thước object thực tế đã gồm header/layout theo VM).
- Một object cỡ 1,1 MiB có thể chiếm trọn một region 2 MiB, làm phần dư gần 0,9 MiB khó dùng cho allocation thông thường trong region đó.
- Một object cỡ 2,1 MiB có thể cần hai contiguous regions, tổng 4 MiB; phần dư region cuối không được dùng như free region độc lập.
- Nhiều large arrays sống/chết xen kẽ có thể làm việc tìm contiguous humongous regions khó hơn dù heap còn dung lượng rảnh theo một số metric.

**Các con số chỉ là tính nhẩm minh họa**: kích thước object thực tế có header/alignment, vùng heap và policy có thể khác. Không thử biến ví dụ thành một công thức OOME cố định.

G1 thường chỉ reclaim humongous objects khi kết luận chúng đã chết theo cơ chế phù hợp; một số arrays có thể được **eager reclaim** theo heuristic. Humongous objects thường **không được copy trong evacuation thông thường**; di chuyển chúng là đường hiếm/last resort trong một số collection modes/versions.

**Trade-off:** không copy các arrays khổng lồ giúp giảm chi phí sao chép, nhưng có thể tăng **wasted region tail** và hạn chế compaction, dẫn đến áp lực free contiguous regions.

### Không nhầm với “Java heap còn 2 GiB trống, nên object 1 GiB chắc chắn cấp phát được”

Thành công còn phụ thuộc:
- `-Xmx`, committed/free heap thực tế.
- Số contiguous regions khả dụng, region size.
- Collector policy cho large allocations.
- Live-set occupancy, GC timing và native/OS constraints thích hợp.
- Memory headroom cho cả application allocations và GC work.

Một collector khác có thể xử lý very large objects khác G1; đừng áp quy tắc humongous của G1 cho mọi GC.

## 14. So sánh các hướng GC trong HotSpot

| Collector / thuật toán | Chiến lược liên quan di chuyển | Điểm mạnh | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Mark–sweep cổ điển** | Reclaim dead objects, có thể giữ live objects nguyên chỗ | Ít live-data copy | External fragmentation, free-list management |
| **Mark–compact** | Dồn live objects, sửa references | Gộp free space, giúp future allocations | Pause/copy/update work và metadata |
| **Copying / semi-space** | Copy live objects sang destination | Nguồn sau copy trở thành vùng trống lớn | Cần destination memory, copy live bytes |
| **Serial GC** | Young collection copying; old collection thường compact theo collector/version | Đơn giản, phù hợp workload nhỏ một số trường hợp | STW pauses, hạn chế parallelism |
| **Parallel GC** | Parallel young copying và old compaction ở những giai đoạn thích hợp | Ưu tiên throughput trên nhiều cores | Có STW và copy/update work |
| **G1** | Region evacuation/partial compaction, remembered sets | Balance throughput và pause-time, incremental regions | RSet/barrier overhead, humongous fragmentation, evacuation failure |
| **ZGC** | Concurrent marking/relocation với metadata/barriers theo phiên bản | Low pause targets trên heaps lớn | Concurrent CPU, barriers, allocation headroom, throughput trade-off |
| **Shenandoah** | Concurrent evacuation/compaction với barriers tùy phiên bản | Giảm lượng GC work trong STW | Concurrent CPU/bandwidth, barrier overhead, availability tùy OpenJDK build |

**Chú ý phiên bản:** không có một triển khai cố định trên mọi Java 17/21/26. Với ZGC, chi tiết chế độ generational và cách barriers/metadata thay đổi qua các bản JDK; với Shenandoah, tính khả dụng/flags thay đổi theo JDK distribution và release. Tránh nói “mọi collector concurrent đều không pause” hoặc “G1 không bao giờ di chuyển humongous object”.

### Stop-the-world và concurrent relocation

**STW moving collector** có thể dừng mutator threads khi cập nhật references để tránh races, đổi lại pause có thể tăng cùng live/edge workload. **Concurrent moving collector** cho phép nhiều công việc di chuyển diễn ra đồng thời với mutators, nhưng cần trả chi phí barriers/coordination và headroom, đồng thời vẫn có thể có những pauses ngắn.

Điều này không có nghĩa concurrent luôn nhanh hơn:
- **Throughput-oriented** workload có thể hưởng lợi từ những pause dài hơn nhưng tổng overhead thấp.
- **Latency-sensitive** service có thể ưu tiên concurrent collector dù cần CPU/memory hơn.
- Khi hệ thống đã gần 100% CPU hoặc heap quá chật, concurrent GC khó theo kịp tốc độ allocation.
- Tối ưu phải đo trên workload và SLA thật.

## 15. Pinning và những vùng không thể di chuyển ngay

Một số điều kiện runtime/native interoperability có thể khiến collector **không thể tự do di chuyển** một object hoặc vùng tại mọi thời điểm. Ví dụ các tình huống liên quan **JNI critical access** và pinning có thể tạo ràng buộc đến một array/object đang được native code truy cập.

Hậu quả tùy collector:
- Giữ object tại chỗ trong một collection phase.
- Bỏ qua hoặc trì hoãn evacuation đối với vùng liên quan.
- Phải xử lý references/memory theo con đường chậm khác.
- Khiến một số vùng ít khả năng trở thành free region ngay.

**Không khẳng định mọi JNI reference đều pin object**: JNI handles thường được VM quản lý, còn pinning cụ thể tùy API, collector và phiên bản. Chẳng hạn `GetPrimitiveArrayCritical` có contract đặc biệt; cách HotSpot thực hiện cần xét phiên bản/GC.

Không dùng địa chỉ của Java object như một pointer ổn định cho native code mà không theo đúng JNI/Panama/Memory API contract. Java references không phải một ABI thô cho phép giữ physical heap address qua GC tùy ý.

## 16. Phân mảnh, OOME và sự khác biệt với memory leak

Phân mảnh và leak có thể có triệu chứng gần nhau nhưng nguyên nhân khác:

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Live heap rất cao, nhiều objects vẫn reachable | Retention/leak hoặc dữ liệu hợp lệ lớn |
| Heap có free bytes nhưng một allocation lớn vẫn khó | Fragmentation, contiguous-region requirement, humongous allocation policy |
| GC liên tục và Full GC thường xuyên | Live-set cao, allocation rate cao, insufficient headroom, evacuation failure |
| Memory OS/RSS không giảm sau GC | Heap vẫn committed, native memory, collector uncommit policy; không đồng nghĩa leak |
| Pauses tăng khi live ratio cao | Copy/scan/reference update work hoặc collector heuristics khác |
| GC logs có humongous regions nhiều | Large-object pressure, wasted tail, allocation/fragmentation risk |
| Một object lớn giữ lại nhiều graph | Retained heap, không nhất thiết là external fragmentation |

**Memory leak (về mặt Java)** thường là tình huống references ngoài ý muốn giữ objects vẫn reachable. **Fragmentation** là vấn đề tổ chức free space hoặc internal waste, kể cả khi một số objects đã thực sự chết/reclaim.

Tăng `-Xmx` có thể giúp có thêm headroom, nhưng không nên xem đó là cách duy nhất hoặc luôn đúng. Nếu dữ liệu còn live quá lớn so với heap limit, compaction không giải quyết được vấn đề; muốn giảm live-set phải đổi ownership/lifetime/data representation hoặc heap budget.

## 17. Đo đúng bằng GC logs, JFR và công cụ HotSpot

Hãy bắt đầu bằng **kết quả đo chứ không bằng giả định phân mảnh**. Trên HotSpot Java 17+, có thể bật Unified GC Logging:

~~~bash
java -Xms256m -Xmx512m -Xlog:gc*:file=gc.log:time,uptime,level,tags CompactionSimulation
~~~

Lệnh minh họa cho ví dụ Java ở mục 9 sau khi đã biên dịch, chạy bằng classpath mặc định trong thư mục hiện hành. File `gc.log` và số liệu cụ thể phụ thuộc JVM/OS/heap/tải, **không có một output GC log cố định**. Một bài mô phỏng chỉ cấp phát ít memory có thể **không tạo GC event nào**, hoàn toàn bình thường.

### Những dấu hiệu trong G1 GC logs

| Nội dung log | Cách diễn giải thận trọng |
| --- | --- |
| `Pause Young (Normal) (G1 Evacuation Pause)` | Young evacuation hoạt động bình thường. |
| `Pause Young (Mixed)` | G1 có thể collect thêm old regions đã chọn. |
| `Evacuation Failure` | Collector gặp ràng buộc khi evacuate, cần xem headroom/pinning/collector-specific diagnostics. |
| `Pause Full (G1 Compaction Pause)` | Full heap compaction STW, thường cần điều tra nếu ảnh hưởng SLA. |
| Humongous region counters | Mức large-object pressure và occupancy theo log, không phải bằng chứng duy nhất của fragmentation. |
| Region/heap usage trước-sau GC | Gợi ý live-set và reclaim efficiency, không hiển thị toàn bộ object graph. |

**Tên tags và message** có thể thay đổi theo JDK/GC flags; không viết parser production dựa trên một đoạn log không được đặc tả ổn định, trừ khi kiểm soát build và có test.

### jcmd / JFR / JMC

Những lệnh ví dụ trên HotSpot hỗ trợ, thay `PID` bằng process ID thật:

~~~bash
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID JFR.start name=GCStudy settings=profile duration=60s filename=gc-study.jfr
jcmd PID JFR.check
~~~

- `GC.heap_info`: thông tin heap, không đảm bảo cung cấp một “fragmentation percentage” chung.
- `GC.class_histogram`: đếm classes/instances/bytes theo một thời điểm, không tự xác định free-block topology.
- **Java Flight Recorder (JFR)**: events về GC pauses, allocations và các hoạt động VM khi được bật theo cấu hình.
- **JDK Mission Control**: phân tích recordings phù hợp để tìm GC/heap/CPU hotspots.
- **Heap dump + dominator tree**: giúp tìm objects còn reachable và retainers, đặc biệt khi nghi leak hơn là fragmentation.

**Cảnh báo:** histogram, heap dump hoặc cấu hình recording có thể ảnh hưởng tải; heap dump chứa dữ liệu nhạy cảm của ứng dụng. Chỉ thu thập khi được phép và bảo vệ files.

### Ví dụ về trình tự phân tích sự cố

1. Xác định collector thật (G1/ZGC/Parallel/...) và JDK build.
2. Ghi `-Xms`, `-Xmx`, heap usage, allocation rate, live set, GC pause distribution.
3. Với G1, quan sát humongous regions, collection set, evacuation failure, Full GC và young/mixed cycles.
4. Nếu live set gần `-Xmx`, ưu tiên kiểm tra **retention** và heap headroom trước khi gọi là fragmentation.
5. Nếu phân mảnh/humongous nghiêm trọng, kiểm tra **kích thước large arrays**, ring buffers/caches và allocation size distribution.
6. Khi thử tùy chọn tuning, lưu baseline và so **throughput, p95/p99 latency, CPU GC overhead, RSS và OOME risk**.
7. Không thay nhiều JVM flags đồng thời nếu muốn biết thay đổi nào hiệu quả.

## 18. Những thước đo trade-off cần so sánh

Một collector hoặc cấu hình không chỉ có “GC pause time”. Cần nhìn đa mục tiêu:

| Mục tiêu | Điều có thể cải thiện | Đổi lại có thể phát sinh |
| --- | --- | --- |
| Ít phân mảnh | Copy/compact thường xuyên hơn | CPU/bandwidth, reference update work |
| Pauses ngắn | Concurrent relocation, chọn regions nhỏ | Barrier overhead, headroom, tổng CPU cao |
| Throughput cao | Ít barriers hơn, batch STW công việc | Pause tail lớn hơn |
| Heap nhỏ | Hạn chế headroom, giảm committed memory | Evacuation failures, allocation stalls, GC frequency |
| Cấp phát nhanh | TLAB/bump pointer, vùng rảnh lớn | Reserve/copy/GC overhead về sau |
| Giảm large object pressure | Reuse/batching/chunking phù hợp | Code complexity, dữ liệu có thể phải copy theo kiểu khác |
| Ít retention | Hạn chế root references/long-lived caches | Cache miss/application compute tăng |
| Tăng locality | Compact hoặc lưu dữ liệu liên tiếp | Copy cost và đổi representation |

**Không đánh đồng throughput với latency.** Một service có thể đạt throughput cao nhưng có những STW pauses dài gây p99 latency tệ. Một collector ít pause có thể tiêu tốn nhiều CPU và headroom hơn, làm throughput peak thấp hơn. Quyết định phải căn theo yêu cầu vận hành.

## 19. Ngộ nhận thường gặp

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “Tổng free bytes đủ thì allocation lớn chắc chắn thành công.” | Có thể cần một dải free space hoặc contiguous regions đủ lớn. |
| “GC thu gom objects chết sẽ tự động loại hết phân mảnh.” | Sweep reclaim khác compaction; collector policy có thể để lại holes/waste. |
| “Compaction làm tăng tổng bytes rảnh.” | Chủ yếu thay **hình dạng free space**; reclaim garbage là công việc liên quan nhưng khác. |
| “Di chuyển object chỉ cần copy bytes.” | References/roots/barriers/metadata phải giữ semantic integrity. |
| “Một object được move thì chỉ có một reference cần update.” | Có thể có nhiều aliases và inbound edges từ nhiều roots/fields/arrays. |
| “Mọi reference cập nhật bằng quét toàn heap STW.” | Tùy GC; có remembered sets, forwarding, barriers, concurrent remapping. |
| “G1 chỉ là mark–sweep không di chuyển.” | G1 dùng evacuation/copying live objects ở selected regions. |
| “G1 luôn di chuyển humongous objects như young objects.” | Humongous dùng contiguous regions và thường không được evacuate thông thường. |
| “G1 Evacuation Pause tức là GC lỗi.” | Evacuation là hoạt động bình thường; *Evacuation Failure* mới là tình huống cần xem. |
| “Moving GC làm thay đổi `System.identityHashCode`.” | Identity hash semantics phải được bảo toàn; hash không phải address. |
| “Java reference là địa chỉ heap người dùng giữ cố định.” | VM quản lý reference representation và object relocation. |
| “Remembered set là danh sách chính xác mọi reference slot.” | Có thể dùng coarse-grained card info cần scan thêm. |
| “Concurrent GC không cần stop-the-world bao giờ.” | Vẫn có safepoints/pauses/handshakes tùy collector, chỉ giảm công việc STW. |
| “GC càng compact mạnh thì throughput càng cao.” | Compact có copy/CPU/bandwidth/barrier costs; cần đo. |
| “Object nhỏ luôn rẻ vì chỉ cần copy vài bytes.” | Nhiều inbound refs/metadata và lượng object lớn vẫn tốn. |
| “Object lớn ít refs thì GC không tốn gì.” | Copy bytes lớn có thể rất đắt; G1 humongous còn có region waste. |
| “Heap usage cao là phân mảnh.” | Có thể là live-set hoặc retained objects; cần kiểm tra metrics. |
| “Đặt field null sẽ compact heap ngay.” | Chỉ cắt reference edge; GC scheduling/compaction không được hứa. |
| “Chạy `System.gc()` cho kết quả compaction cố định.” | Không có bảo đảm di chuyển object hoặc thời gian collection. |

## 20. Bài tập tư duy có lời giải

**Câu 1.** Heap có 200 MiB free rải đều thành 200 khoảng 1 MiB. Một allocator cần 8 MiB contiguous. Có đủ memory không?

**Đáp án:** **Không nhất thiết**. Tổng free lớn hơn yêu cầu nhưng không có đoạn 8 MiB. Điều này là ví dụ external fragmentation trong mô hình allocator cần contiguous block.

**Câu 2.** Compaction biến 200 MiB free phân tán thành một khoảng 200 MiB. Nó đã “thu hồi thêm 200 MiB” chưa?

**Đáp án:** Không. Nó **gộp free space**, không tự tăng free-byte count.

**Câu 3.** Khi GC chuyển B từ vị trí cũ sang mới, variable `x` và field `a.b` đều trỏ B. Chỉ sửa x đã đủ chưa?

**Đáp án:** Không, collector còn phải bảo đảm `a.b` tiếp tục trỏ đúng B, theo cách update/remap của collector.

**Câu 4.** Một object 8 KiB với một inbound reference và một object 32 byte với một triệu inbound references. Object nào “đắt để move” hơn?

**Đáp án:** Không thể kết luận chỉ từ size hoặc số references. Object 8 KiB đắt hơn về copy bytes, object 32 byte có thể đắt về reference processing; phụ thuộc GC và thuật toán.

**Câu 5.** Mark–sweep có thể để lại holes vì sao?

**Đáp án:** Nó có thể reclaim garbage nhưng để live objects tại chỗ, khiến free blocks xen kẽ object sống.

**Câu 6.** Evacuation giúp gộp free space bằng cách nào?

**Đáp án:** Copy live objects khỏi các source regions được chọn và reclaim toàn bộ source regions khi thành công.

**Câu 7.** G1 có phải STW toàn bộ concurrent marking không?

**Đáp án:** Không. G1 có những phases đồng thời với mutator, nhưng evacuation pauses là STW và Full GC có thể STW dài.

**Câu 8.** Remembered set của G1 phục vụ điều gì?

**Đáp án:** Giúp giới hạn việc tìm refs từ bên ngoài collection set vào các regions đang thu gom, thay vì quét mọi object của toàn heap tại mỗi pause.

**Câu 9.** Vì sao humongous object có thể làm tăng wasted capacity ở G1?

**Đáp án:** Nó chiếm một hoặc nhiều contiguous regions; phần dư của region cuối có thể không dùng được cho allocations khác đến khi object được reclaim.

**Câu 10.** Một chương trình in true từ `a == b` trước và sau GC có chứng minh GC không move object không?

**Đáp án:** Không. Identity được VM bảo toàn kể cả khi object đã move.

**Câu 11.** Collector concurrent giảm pause có phải miễn phí CPU?

**Đáp án:** Không. Barrier/coordination và công việc concurrent có thể tiêu tốn CPU, memory bandwidth và headroom.

**Câu 12.** Heap có live-set 95% limit nhưng ít holes. Vì sao vẫn có thể Full GC/OOME?

**Đáp án:** Không đủ reclaimable space hoặc destination/headroom cho allocation/evacuation, dù external fragmentation không phải nguyên nhân chính.

**Câu 13.** Khi muốn xác nhận một memory leak, class histogram đã đủ chưa?

**Đáp án:** Chưa. Histogram cho số lượng và bytes theo class, còn dominator tree/GC-root paths giúp xác định ai giữ references.

**Câu 14.** Có nên tự lấy địa chỉ object bằng kỹ thuật không chuẩn rồi giữ qua một moving GC?

**Đáp án:** Không. Java reference không phải physical pointer ổn định; cần dùng API/JNI/native interfaces đúng contract.

**Câu 15.** Với một region 2 MiB, object lớn hơn 1 MiB có thể rơi vào loại gì trong G1?

**Đáp án:** **Humongous**, vì kích thước đạt ít nhất nửa region; xử lý special allocation/evacuation phải xét G1 version và policy.

## 21. Bản đồ ghi nhớ

~~~text
               HEAP CÓ FREE SPACE
                         |
                  Free space rời rạc?
                   /             \
                 Có              Không
                 |                 |
        EXTERNAL FRAGMENTATION   Vẫn có thể thiếu
                 |               live/headroom
                 v
         CHỌN THUẬT TOÁN GC
            /            \
       NON-MOVING        MOVING
       mark/sweep      compact / copy
            |               |
       ít copy live      gộp free blocks /
       có thể để holes   reclaim source regions
                            |
                 +----------+-----------+
                 |          |           |
              Copy bytes  Forwarding  Update/remap refs
                 |          |           |
                 +----------+-----------+
                            |
               CPU / bandwidth / pause / headroom
                            |
        G1: regions + RSet + evacuation + humongous
        ZGC / Shenandoah: concurrent relocation + barriers
                            |
                  MEASURE, DO NOT GUESS
                            |
            GC logs + JFR + jcmd + heap dump
                            |
          throughput / p99 latency / GC CPU / RSS
~~~

**Điểm cốt lõi:** phân mảnh là vấn đề **tổ chức free space**, không nhất thiết là thiếu tổng bytes. Di chuyển objects có thể compact heap hoặc giải phóng nguyên regions, nhưng phải duy trì các references hợp lệ — qua update trực tiếp, forwarding, barriers hoặc cơ chế tương đương. Đánh đổi giữa **ít fragmentation** và **chi phí copy/reference handling, pauses, concurrent CPU, memory headroom** phụ thuộc loại GC và workload, nên luôn kiểm chứng trên HotSpot thật.

## Tài liệu chính thức

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [Oracle Java 21 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).
- [Oracle Java 21 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java 21 — Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html).
- [Oracle Java 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java 21 — The java Command, Unified GC Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [OpenJDK JEP 333 — ZGC](https://openjdk.org/jeps/333).
- [OpenJDK JEP 189 — Shenandoah GC](https://openjdk.org/jeps/189).
