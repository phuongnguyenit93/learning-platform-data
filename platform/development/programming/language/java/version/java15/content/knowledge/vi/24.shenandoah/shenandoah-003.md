# Read barrier, write barrier và chi phí thực thi trong Shenandoah GC (Java 15+)

## 1. Tại sao Shenandoah phải có barrier?

**Shenandoah** là garbage collector hướng tới **độ trễ dừng ứng dụng thấp (low-pause GC)**. Điểm khác biệt quan trọng của nó là thực hiện nhiều công việc **marking, evacuation (di chuyển object) và cập nhật tham chiếu** cùng lúc với các luồng Java đang chạy (*concurrent with mutators*). Shenandoah đã được đưa thành tính năng production trong **Java 15** qua **JEP 379**, và vẫn được phát triển trong JDK hiện hành.

Concurrent GC đem lại lợi ích: bớt đưa toàn bộ công việc thu gom/di chuyển object vào một lần **stop-the-world (STW)** dài. Nhưng đồng thời đặt ra bài toán:

- Thread Java **đọc một tham chiếu** đúng lúc GC đang di chuyển object đó.
- Thread Java **ghi đè một tham chiếu** đúng lúc GC đang đánh dấu những object còn sống.
- Trong một collector **generational**, object cũ có thể bắt đầu **trỏ đến object trẻ** khi GC đang theo dõi vùng nhớ liên thế hệ.

Nếu không phối hợp, GC có thể bỏ sót object còn sống hoặc ứng dụng có thể truy cập phiên bản/tham chiếu không đúng trong lúc object được chuyển vị trí.

**Barrier** ở đây là một **đoạn logic bổ sung vào thao tác truy cập tham chiếu**, được JVM/compiler/runtime sử dụng để duy trì các bất biến của collector. Nó **không phải** đối tượng `java.util.concurrent.CyclicBarrier`, **không phải** lệnh Java mà lập trình viên phải gọi bằng tay, và **không đồng nghĩa** với memory fence của Java Memory Model.

Ba loại cần nhớ:

| Cơ chế | Thường gắn với thao tác nào? | Mục tiêu |
| --- | --- | --- |
| **Load-reference barrier (LRB)** — read/load barrier | **Đọc một object reference** | Giải quyết tham chiếu tới object đã/đang được chuyển khi concurrent evacuation |
| **SATB pre-write barrier** | **Trước khi ghi đè một object reference** | Giữ thông tin về tham chiếu cũ để concurrent marking không bỏ sót object theo snapshot |
| **Card-marking post-write barrier** — ở **generational Shenandoah** | **Sau thao tác ghi object reference** có liên quan | Theo dõi những liên kết **old → young** để young collection không bỏ sót object trẻ |

Ngoài ba loại trên, triển khai thực tế còn có xử lý đặc thù cho `CAS`, bulk copy/arraycopy, clone và Java reference objects. **Tập barrier được kích hoạt và cách tối ưu hóa phụ thuộc GC mode, pha GC, JIT, kiến trúc máy và bản JDK**; không nên hiểu bảng như “mọi đọc/ghi đều phải gọi đủ ba barrier”.

## 2. Ngữ cảnh: mutator, marking và evacuation

**Mutator** là luồng ứng dụng làm thay đổi heap: tạo object, đọc trường và gán tham chiếu. **Collector** thu hồi những object không còn reachable và có thể di chuyển object để tránh phân mảnh.

Sơ đồ khái niệm:

~~~text
                   Heap
            ┌──────────────────┐
Thread Java │ A ──next────► B  │
  (mutator) │              │   │
     │      │              ▼   │
     │      │ GC chọn B để chuyển
     │      │  B (from-space) ──► B' (to-space)
     │      └──────────────────┘
     │
     └─ đọc A.next đúng lúc B đang được relocate
              │
              ▼
       Load-reference barrier
       bảo đảm tiếp tục với tham chiếu phù hợp
~~~

Ở đây, `B` và `B'` chỉ là cách diễn đạt **vị trí cũ/vị trí mới của cùng một object logic**, không phải hai object nghiệp vụ độc lập. Chi tiết hiện thực forwarding, evacuation assistance, concurrent reference updating có thể thay đổi theo phiên bản Shenandoah.

**Mục tiêu chính xác của LRB** là bảo đảm mã Java nhận một reference phù hợp với bất biến của collector khi object có thể đã được chuyển. **Không được diễn giải rằng mọi lần đọc đều sao chép object**: hầu hết trường hợp rơi vào **fast path** khi reference không cần được sửa; slow path chỉ xảy ra trong điều kiện thích hợp.

Cùng lúc, nếu thread Java gán:

~~~java
holder.next = new Node(42);
~~~

thì GC có thể cần quan tâm **giá trị cũ của `holder.next`** để thực hiện SATB marking và, trong chế độ generational, quan tâm **liên kết mới** giữa object chứa trường với object được gán. Hai mục tiêu này giải thích vì sao có cả **pre-write** và **post-write barrier**.

## 3. Load-reference barrier: điều gì xảy ra khi đọc object reference?

### 3.1. Điểm chèn LRB

Khi code Java viết:

~~~java
Node next = current.next;
~~~

đó là **reference load** từ trường `next` (giả định `Node.next` có kiểu `Node`). Trong Shenandoah, JIT/runtime có thể chèn logic **load-reference barrier** để bảo đảm giá trị reference được sử dụng đúng khi GC đồng thời di chuyển object.

Pseudocode ở mức ý tưởng:

~~~text
rawRef = load(current.next)
next   = ShenandoahLoadReferenceBarrier(rawRef)
use(next)
~~~

**Đây là pseudocode**, không có public Java API tên `ShenandoahLoadReferenceBarrier` để gọi. Trình biên dịch có thể gộp, loại bỏ, hoãn hoặc chuyên biệt hóa barrier; đường đi thực tế không nhất thiết đúng ba lệnh trên.

Điểm phân biệt:

- **Reference load** như `current.next` hoặc `array[i]` của `Node[]` là đối tượng cần quan tâm.
- **Primitive load** như `current.id` kiểu `int` không tự trở thành LRB chỉ vì nó xuất hiện trong một vòng lặp.
- `String.length()`, phép cộng `int` và đọc CPU register không tương đương một lần load object reference từ heap.
- Một `Node` reference có thể được giữ sẵn trong register; JIT tối ưu toàn bộ vòng lặp nên số thao tác máy/barrier **không phải số dòng Java**.

### 3.2. Fast path và slow path

**Fast path** thường kiểm tra những điều kiện đủ để biết reference không cần xử lý phức tạp. Khi collector không ở pha liên quan, object không nằm trong nhóm đang di chuyển hoặc đã có reference hợp lệ, có thể tiếp tục nhanh.

**Slow path** chỉ đi vào khi cần xử lý reference liên quan object đang di chuyển, ví dụ tra cứu forwarding hoặc tham gia công việc xử lý theo implementation. Nó có thể tạo chi phí CPU và cache không nhỏ cho những truy cập nhất định.

~~~text
load reference
      │
      ▼
kiểm tra trạng thái/điều kiện GC
      │
      ├── fast path ──────────► dùng reference
      │
      └── slow path ──────────► resolve/handle moved object
                                      │
                                      ▼
                               dùng reference phù hợp
~~~

**Không coi LRB là “mỗi dereference đều tốn đúng X ns”.** Tần suất fast/slow path, cache locality, CPU branch prediction và tối ưu hóa JIT làm chi phí biến động theo workload và pha GC.

### 3.3. Vì sao không chỉ cập nhật tất cả reference bằng STW?

Một phương án thu gom truyền thống có thể dừng toàn bộ ứng dụng để di chuyển object và cập nhật các reference trước khi chạy tiếp. Shenandoah chọn nhiều thao tác **concurrent**, nên phải phối hợp với mutator khi ứng dụng vẫn đọc reference. LRB là một phần chi phí đổi lấy **thời gian STW ngắn hơn**.

Nó là một trade-off, không phải “miễn phí”: giảm pause có thể làm **throughput**, IPC hoặc băng thông bộ nhớ của ứng dụng bị ảnh hưởng. Cần đo cả request latency tail lẫn throughput/CPU trong điều kiện tải tương đương.

## 4. Write barrier kiểu SATB: giữ bất biến của concurrent marking

### 4.1. Snapshot-at-the-beginning

SATB viết tắt của **Snapshot-At-The-Beginning**. Trong lúc concurrent marking, collector cố bảo toàn logic truy vết object theo **một snapshot khái niệm tại đầu chu kỳ**.

Giả sử:

~~~text
Trước khi ghi:
holder.ref ──► OldObject

Thread Java:
holder.ref = NewObject

Sau khi ghi:
holder.ref ──► NewObject
~~~

Nếu collector chưa kịp xét `OldObject` mà application xóa tham chiếu cũ, GC có thể mất thông tin cần thiết để bảo toàn snapshot. **SATB pre-write barrier** có thể ghi nhận/đưa **giá trị reference cũ** vào cơ chế theo dõi phù hợp **trước thao tác ghi đè**.

Pseudocode:

~~~text
oldRef = load(holder.ref)
SATB_pre_write(oldRef)   // theo dõi ref cũ nếu marking đang cần
store(holder.ref, newRef)
~~~

Đây chỉ là **mô hình giải thích**. Không có public method Java tên `SATB_pre_write`; implementation dùng các điều kiện, buffer/thread-local queues và đường đi được tối ưu hóa. **Không nhất thiết mọi lần ghi `null`, ghi object mới hoặc ghi vào object mới tạo đều phải enqueue một reference**; JIT/collector có thể bỏ qua các trường hợp không cần thiết.

### 4.2. SATB quan tâm reference cũ, không phải chỉ reference mới

Đây là khác biệt quan trọng giữa:

- **SATB pre-write:** hỗ trợ **concurrent marking**, quan tâm **old value bị ghi đè**.
- **Card-marking post-write trong generational collector:** hỗ trợ **young collection**, quan tâm **quan hệ reference sau ghi**, đặc biệt old → young.

Trong cả hai trường hợp, `holder.ref = newRef` vẫn là **một thao tác gán của chương trình**. Các barrier chỉ là nghĩa vụ mà GC/JIT cần thực hiện để collector bảo toàn tính đúng đắn.

### 4.3. Vì sao pre-write barrier có overhead?

Các nguồn chi phí có thể gồm:

1. Đọc giá trị reference cũ trước khi store.
2. Kiểm tra xem pha marking có cần barrier hay không.
3. Chọn lọc giá trị như `null` hoặc trường hợp đã được xử lý.
4. Đưa reference cần giữ vào buffer/queue của GC.
5. Khi buffer đầy, phát sinh đường đi chậm hoặc công việc nền để xử lý queue.
6. Tạo thêm branch, load/store và pressure lên memory/cache.

**Không phải tất cả chi phí xuất hiện trên mỗi lần write.** Nếu không concurrent marking, một phần có thể đi theo fast path ngắn; compiler cũng có thể tối ưu trường hợp initializing stores hoặc code đủ đơn giản.

**Đừng nhầm SATB với Java `volatile`.** `volatile` cung cấp các ràng buộc visibility/happens-before theo Java Memory Model; SATB bảo toàn **bất biến reachability của GC**. Chúng có thể cùng tác động vào một field access nhưng giải quyết **hai vấn đề khác nhau**.

## 5. Generational Shenandoah: thêm card barrier cho old → young

### 5.1. Vì sao phải theo dõi tham chiếu liên thế hệ?

Một collector có thế hệ phân chia object vào **young** và **old** theo chính sách tuổi/thời gian sống. Khi thu gom young generation, collector không thể cứ coi mọi object old là không liên quan. Object old có thể giữ reference tới object young còn sống.

~~~text
Old generation              Young generation
┌───────────────┐           ┌───────────────┐
│ Parent (old)  │──child──►│ Child (young) │
└───────────────┘           └───────────────┘
            ▲
       Tham chiếu old → young phải được ghi nhận
       để young GC không bỏ sót Child
~~~

**Card table / remembered information** giúp collector biết những vùng old cần quan tâm, không quét lại toàn bộ heap old trong mỗi young collection.

**Post-write barrier** có thể đánh dấu (*dirty*) một card khi field reference vừa được ghi tạo liên kết có ý nghĩa old → young. Chi tiết sàng lọc object old/young, thời điểm đánh dấu và kích thước card là **implementation detail**, không phải contract Java SE.

Pseudocode:

~~~text
store(oldHolder.ref, youngTarget)
if (generationalShenandoah
    && holderIsOld
    && targetIsYoung
    && writeRequiresCardMark) {
    markDirtyCard(addressOf(oldHolder.ref))
}
~~~

Điều kiện trên chỉ mang tính mô tả. Không tự dùng kiểm tra “object già hay trẻ” từ code Java để viết GC barrier; JVM đã chịu trách nhiệm.

### 5.2. Cập nhật từ Java 15 đến JDK hiện hành

| Giai đoạn | Trạng thái đáng lưu ý | Cách hiểu còn áp dụng |
| --- | --- | --- |
| **JDK 15** — JEP 379 | Shenandoah được đưa thành collector **production**, có concurrent marking/evacuation | LRB và SATB là nền tảng của chế độ SATB/non-generational |
| **JDK 24** — JEP 404 | **Generational Shenandoah** lần đầu được tích hợp ở dạng **experimental** | Có thêm bài toán theo dõi tham chiếu liên thế hệ |
| **JDK 25** — JEP 521 | Generational Shenandoah được chuyển từ experimental thành **product feature** | Khi dùng chế độ generational, có thêm cơ chế **card-marking post-write** |
| **JDK hiện hành** | Có nhiều mode/flag theo version và vendor | Phải xác nhận mode đã chọn, không coi mọi Shenandoah đều là non-generational hoặc mọi bản build có cùng mặc định |

Trong tài liệu lệnh `java` của OpenJDK mới, tùy chọn `-XX:ShenandoahGCMode=satb` được mô tả là chế độ SATB single-generation; `-XX:ShenandoahGCMode=generational` là mode generational. **Không tự cho rằng generational là mặc định ở mọi bản JDK**; kiểm tra mô tả của JDK đang chạy. Các chế độ/mode có thể được cập nhật giữa các bản phát hành.

Tùy chọn minh họa với bản build có hỗ trợ:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -jar app.jar
~~~

Đây **không** phải lệnh chạy được độc lập nếu không có `app.jar`, và phù hợp với **JDK 25+ có triển khai chế độ generational**. Trên một bản JDK khác, tùy chọn có thể không được nhận; không tự thêm flag experimental/diagnostic khi chưa có tài liệu đúng phiên bản.

**Điểm cốt lõi của bài:** nếu so chi phí barrier của Shenandoah hiện đại với G1 hoặc phiên bản Shenandoah cũ, phải ghi rõ **JDK build, GC mode và pha GC**. Chế độ generational có những nghĩa vụ store barrier khác với chế độ SATB single-generation; nếu bỏ qua khác biệt này, so sánh overhead có thể sai.

## 6. Các đường truy cập đặc biệt: CAS, arraycopy, clone, reference objects

Không phải mọi reference write đều xuất phát từ một lệnh `obj.field = value` đơn giản. Ứng dụng còn có:

- **Atomic compare-and-set / compare-and-exchange** với trường object hoặc array element, ví dụ thông qua `VarHandle`.
- **`System.arraycopy`** khi sao chép mảng tham chiếu.
- **`Object.clone()`** và những hoạt động bulk reference-copy phù hợp.
- **`java.lang.ref.Reference`**: weak, soft, phantom references với quy tắc keep-alive/reachability riêng.

Đối với các trường hợp này, implementation Shenandoah còn có barrier/đường đi xử lý chuyên biệt để không bỏ qua tác động lên heap. Ví dụ, CAS có thể cần xử lý đúng reference cũ, reference mới và tính atomicity của thao tác, trong khi clone/arraycopy có thể cần làm việc theo **cả dải** thay vì một field riêng.

**Không tự suy diễn** một Java `compareAndSet` tương đương một pre-barrier và một post-barrier rời rạc theo số lần gọi. JVM có thể tối ưu, nội tuyến, triển khai atomic access khác biệt tùy CPU và pha collector.

Nguyên tắc đúng là **mã Java hợp lệ tiếp tục giữ đúng semantics của Java**, còn garbage collector/JIT chịu trách nhiệm chèn barrier cần thiết. Việc lập trình viên “tắt barrier” thông qua các diagnostic/experimental flags để tăng performance có thể **phá bất biến GC**, nên không phải biện pháp tuning production.

## 7. Chi phí thực thi của barrier đến từ đâu?

Một load/store trên object reference có thể kéo theo **fast-path checks** và đôi khi **slow-path work**. Các yếu tố quyết định cost:

| Yếu tố | Tác động tiềm năng | Cần đo gì? |
| --- | --- | --- |
| Tần suất reference loads | Pointer-chasing và truy cập đồ thị nhiều có thể gặp nhiều LRB | Throughput, CPU cycles, JIT hot paths |
| Tần suất reference overwrites | Những cập nhật reference có thể phát sinh SATB buffer work | Allocation/reference write rate, CPU |
| Generational old → young stores | Có thể làm bẩn card, tăng remembered tracking | Card/young GC activity, throughput |
| GC đang ở pha nào | Cùng code có thể đi fast/slow path khác nhau | GC timeline/logs, CPU |
| Object đang được relocate? | Slow path reference resolution có thể nhiều hơn | Evacuation activity, latency |
| Độ phân tán object trên heap | Pointer-chasing gây cache misses/NUMA pressure | Hardware perf counters nếu có, latency |
| JIT optimization | Escape analysis, inlining, elimination/hoisting, barrier specialization | Warm-up, compiler level, JFR/JIT tooling |
| Heap headroom và allocation | GC phải làm việc thường xuyên hơn hoặc stall | GC CPU, allocation stalls, heap occupancy |
| Hệ thống gần bão hòa | Chi phí CPU nhỏ cũng có thể tăng queue/tail mạnh | Offered RPS, queue depth, p99 |
| CPU quota hoặc contention | Collector và mutators cùng tranh CPU | cgroup throttling, CPU utilization |

Một biểu thức tư duy (không phải benchmark hoặc công thức JDK):

~~~text
application CPU cost ≈
    business logic cost
  + cost of reference/barrier fast paths that remain after JIT optimization
  + occasional barrier slow paths
  + costs of allocation/memory/cache/scheduling

end-to-end request latency =
    kết quả của toàn bộ đường xử lý + queueing,
    KHÔNG phải chỉ tổng barrier instructions
~~~

**Không có hằng số cố định** “một Shenandoah read barrier mất 2 ns” áp dụng mọi CPU/JDK/workload. Tùy bản phát hành, hình dạng code, tỷ lệ object relocate và hoạt động concurrent GC, overhead có thể thay đổi nhiều. Những bảng microbenchmark trên Internet nếu không công bố đầy đủ workload và JDK mode **không đủ cơ sở** để kết luận ứng dụng thật chậm bao nhiêu phần trăm.

### 7.1. Vì sao read-heavy và write-heavy có thể khác nhau?

Với code **duyệt một đồ thị object liên tục**, reference loads/branch/cache có thể là một phần đường nóng. Với code **thường xuyên gán lại object reference**, pre-write barrier và card-marking có thể quan trọng hơn. Nhưng không nên gắn nhãn từ tên phép toán:

- Một vòng lặp cộng số nguyên trong một `int[]` không phải một vòng lặp nhiều object-reference load.
- Một vòng lặp thao tác trên object được escape-analysis và scalar-replace có thể không còn số load/store heap như bạn tưởng.
- `Node next = node.next` có thể gây cache misses tốn hơn bản thân barrier.
- Một thread giữ các object trong heap không đủ lâu có thể không tạo nhiều công việc old → young, ngay cả khi source chứa nhiều `new`.

**Số lần truy cập tham chiếu viết trong code ≠ số barrier machine instructions thực thi sau JIT ≠ chi phí runtime**. Chỉ phép đo/profile trên workload thực mới giải quyết được ba tầng này.

## 8. JIT tối ưu barrier như thế nào?

JVM dùng C1/C2 (và các trình biên dịch khác tùy runtime) để biến bytecode thành machine code. Một số trường hợp tối ưu có thể:

1. Loại bỏ reference accesses không cần thiết do **escape analysis/scalar replacement**.
2. **Inline** truy cập và đơn giản hóa nhánh kiểm tra barrier.
3. Giảm bớt chi phí khi reference được chứng minh không nằm trong vùng cần xử lý.
4. Kết hợp hoặc hoãn các thao tác card-marking trong những trường hợp an toàn.
5. Chọn fast path/slow path phù hợp với collector state và runtime.
6. Có xử lý đặc thù đối với object initialization, arraycopy và CAS.

**Chi tiết cụ thể khác nhau theo phiên bản HotSpot, kiến trúc CPU và GC mode.** Không phải chương trình nào cũng được tối ưu tương tự, không phải một barrier sẽ luôn được loại bỏ, và không nên dùng một đoạn mã Java đọc được để dự đoán chính xác chuỗi instruction sau C2.

Để thấy chi phí thật, cần phối hợp **JMH** để tránh benchmark bị JIT tối ưu sạch, profiling CPU (JFR hoặc profiler phù hợp), GC logs và metric SLO. Việc tự tính `(end-start) / operations` trong một vòng ngắn thường chịu ảnh hưởng lớn từ warm-up, dead-code elimination và OS scheduling.

## 9. Ví dụ Java 15+ mô tả reference loads và reference stores

Bài tập sau dùng hai kiểu workload khác nhau:

1. **Đọc (read-heavy):** tạo một vòng liên kết 1.024 `Node`; duyệt vòng 32 lượt, mỗi lượt theo `Node.next` đến node tiếp theo và cộng `Node.id`.
2. **Ghi (write-heavy):** tạo 128 `holder`, mỗi holder có trường `next`; thực hiện 5 lượt gán reference mới, đọc reference cũ trước khi gán, kiểm tra checksum của các object bị thay thế.
3. In kết quả **xác định** để chứng minh semantics chương trình không đổi khi dùng G1 hoặc Shenandoah.

**Tuyệt đối không hiểu các biến `referenceLoads`/`referenceStores` là bộ đếm barrier nội bộ của JVM.** Chúng chỉ đếm **số lần thao tác logic trong code Java**. GC/JIT có thể thêm, bỏ hoặc kết hợp các barrier tương ứng; thực thi này cũng quá nhỏ để bảo đảm một chu kỳ GC xảy ra.

~~~text
Read path, một bước:
current ──next──► anotherNode
       └── Node.next là reference load

Write path, một bước:
holder.next: oldRef ──► newRef
             ▲          ▲
         old value    new reference store
         (SATB có thể cần giá trị cũ)
                    (generational card barrier có thể cần new link)
~~~

### Mã hoàn chỉnh

Lưu file đúng tên **`ShenandoahBarriersDemo.java`** bằng UTF-8:

~~~java
public class ShenandoahBarriersDemo {
    static final class Node {
        final int id;
        Node next;
        Node(int id) { this.id = id; }
    }

    public static void main(String[] args) {
        final int ringSize = 1024;
        final int readRounds = 32;
        Node[] ring = new Node[ringSize];
        for (int i = 0; i < ringSize; i++) {
            ring[i] = new Node(i);
        }
        for (int i = 0; i < ringSize; i++) {
            ring[i].next = ring[(i + 1) % ringSize];
        }

        long readChecksum = 0;
        int referenceLoads = 0;
        boolean ringIsClosed = true;
        for (int round = 0; round < readRounds; round++) {
            Node current = ring[0];
            for (int i = 0; i < ringSize; i++) {
                readChecksum += current.id;
                current = current.next;
                referenceLoads++;
            }
            ringIsClosed &= current == ring[0];
        }

        final int holderCount = 128;
        final int writeRounds = 5;
        Node[] holders = new Node[holderCount];
        for (int i = 0; i < holderCount; i++) {
            holders[i] = new Node(i);
        }

        int referenceStores = 0;
        int overwrittenReferences = 0;
        long replacedSum = 0;
        for (int round = 0; round < writeRounds; round++) {
            for (int i = 0; i < holderCount; i++) {
                Node old = holders[i].next;
                if (old != null) {
                    overwrittenReferences++;
                    replacedSum += old.id;
                }
                holders[i].next = new Node(round * holderCount + i);
                referenceStores++;
            }
        }

        long finalTargetSum = 0;
        for (Node holder : holders) {
            finalTargetSum += holder.next.id;
        }

        System.out.println("ringSize=" + ringSize);
        System.out.println("referenceLoads=" + referenceLoads);
        System.out.println("readChecksum=" + readChecksum);
        System.out.println("ringIsClosed=" + ringIsClosed);
        System.out.println("referenceStores=" + referenceStores);
        System.out.println("overwrittenReferences=" + overwrittenReferences);
        System.out.println("replacedSum=" + replacedSum);
        System.out.println("finalTargetSum=" + finalTargetSum);
        System.out.println("checks=" +
                (ringIsClosed && referenceLoads == 32768
                 && readChecksum == 16760832L
                 && referenceStores == 640
                 && overwrittenReferences == 512
                 && replacedSum == 130816L
                 && finalTargetSum == 73664L));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 ShenandoahBarriersDemo.java
java -XX:+UseG1GC ShenandoahBarriersDemo.java
~~~

**Sửa lệnh chạy khi đã compile `.class`:** Sau lệnh `javac` ở trên, cách chạy chuẩn là:

~~~bash
java -XX:+UseG1GC ShenandoahBarriersDemo
java -XX:+UseShenandoahGC ShenandoahBarriersDemo
~~~

Cặp lệnh này yêu cầu bản JDK có cả G1 và Shenandoah; nếu Shenandoah không được build hỗ trợ, JVM sẽ báo không nhận collector. **Không phải lỗi của chương trình Java**. Đoạn lệnh nguồn file `java ... Demo.java` đầu tiên là cú pháp source-file mode của JVM, nhưng ở đây nên **ưu tiên chạy class đã compile** để nhất quán với `javac`.

Chương trình đã được biên dịch thành công bằng **`javac --release 15` và `javac --release 17`**, và đã chạy **trên JDK 24** với cả `-XX:+UseG1GC` và `-XX:+UseShenandoahGC`. Hai lần chạy cho **cùng stdout**:

~~~text
ringSize=1024
referenceLoads=32768
readChecksum=16760832
ringIsClosed=true
referenceStores=640
overwrittenReferences=512
replacedSum=130816
finalTargetSum=73664
checks=true
~~~

### Hiểu kết quả, không suy diễn quá mức

- `ringSize=1024`: graph gồm 1.024 node ở một vòng khép kín.
- `referenceLoads=32768`: 32 lượt × 1.024 lần `current.next`; đây là số lần logic **đọc reference trong Java**, **không** phải số slow-path LRB.
- `readChecksum=16760832`: mỗi lượt cộng `0+...+1023=523776`; 32 lượt cho tổng 16.760.832.
- `ringIsClosed=true`: sau đúng 1.024 cạnh, vòng quay lại node đầu tiên.
- `referenceStores=640`: 5 lượt × 128 holder được gán reference mới.
- `overwrittenReferences=512`: lượt đầu thay `null`, bốn lượt sau thay 128 reference đã tồn tại → 4×128.
- `replacedSum=130816`: tổng `id` của các reference bị thay theo logic ứng dụng; **không** phải số phần tử trong SATB queue của GC.
- `finalTargetSum=73664`: tổng ID của các object mới được giữ bởi holder sau lượt thứ năm.
- `checks=true`: cấu trúc graph/giá trị nhận được phù hợp với kỳ vọng.

**Cần hiểu đúng:** cùng stdout trên G1 và Shenandoah xác minh **tính đúng đắn hành vi Java**, không chứng minh hai GC có chi phí ngang nhau. Chương trình không in duration và không tạo GC đủ lâu để đo barrier overhead. Đó là chủ ý để stdout không gây ấn tượng “benchmark chuẩn” trong khi không đủ điều kiện.

### Lệnh nguồn và runtime phiên bản

Với Java 15+, `-XX:+UseShenandoahGC` chỉ **chọn collector** nếu bản build cung cấp. Không phải mọi vendor/JDK và nền tảng đều hỗ trợ như nhau. Kiểm tra nhanh:

~~~bash
java -version
java -XX:+UseShenandoahGC -version
~~~

Khi chạy bằng `-XX:+UseShenandoahGC`, cần nhớ **collector có thể không phát sinh collection** với dữ liệu vài nghìn object. Vì vậy không thể chỉ dựa vào `checks=true` để nói “đã đo LRB overhead”. Nó chỉ chứng minh workload tương thích ngữ nghĩa.

## 10. Thu thập GC logs, JFR và metric ứng dụng để thấy chi phí thật

### 10.1. Unified Logging

Trên HotSpot hiện hành, có thể bật log GC và safepoint:

~~~bash
java -XX:+UseShenandoahGC -Xlog:gc*,safepoint:file=shenandoah-gc.log:time,uptime,level,tags -jar app.jar
~~~

Đây là **lệnh minh họa cho một ứng dụng có file `app.jar`**, không phải file kèm sẵn trong bài. Cần điều chỉnh log retention/rotation theo khối lượng production.

GC log cho biết các chu kỳ, pause, concurrent phases, heap/regions và một số timing/cause **tùy collector/version/tag**. Nó thường **không** trực tiếp báo “mỗi lần đọc reference tốn đúng Y ns”:

1. Nhận diện collector, version, mode, heap sizing và JVM flags.
2. Tách các **STW pauses** khỏi các pha GC chạy concurrently.
3. Tìm những giai đoạn evacuation/update refs, marking, degeneration hoặc full GC nếu có.
4. Quan sát heap occupancy, allocation rate, GC cycle frequency và thread CPU.
5. Đối chiếu với throughput/latency của ứng dụng dưới cùng workload và thời gian.

Nếu chỉ so `GC pause max`, bạn có thể bỏ qua **CPU overhead của fast-path barriers** hoặc thời gian chạy concurrent phases. Ngược lại, GC log có nhiều event **không** có nghĩa mọi event là một khoản thời gian STW cộng dồn.

### 10.2. JFR

Một mẫu sử dụng JFR khi chạy ứng dụng:

~~~bash
java -XX:+UseShenandoahGC -XX:StartFlightRecording=filename=shenandoah.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Trong recording, phân tích CPU usage, allocation, thread scheduling/contending, GC phases và các request spans do ứng dụng ghi. JFR cho phép tương quan thời điểm, nhưng **không mặc nhiên có một event tên `jdk.ShenandoahBarrierCost`** hay một chỉ số nano-second trực tiếp cho từng load/write barrier.

**Chi phí thực tế** thường phải được suy ra từ **so sánh có kiểm soát** và profiling, không từ một counter barrier public Java API.

### 10.3. Đừng tắt barrier để “đo nhanh” trên hệ thống thật

Một số bản HotSpot có **diagnostic flags nội bộ** để kiểm thử barrier. Chúng **không phải** API tuning bền vững; có thể bị đổi tên/xóa và có thể làm hỏng tính đúng đắn collector nếu vô hiệu hóa barrier cần thiết.

**Không khuyến nghị bật/tắt `ShenandoahLoadRefBarrier`, `ShenandoahSATBBarrier` hoặc `ShenandoahCardBarrier` để tối ưu sản phẩm.** Muốn benchmark sự khác nhau, lựa chọn đúng collector/mode được hỗ trợ và dùng JMH/JFR, không dùng cờ phá cơ chế correctness của GC.

## 11. Đo overhead đúng: benchmark có đối chứng

Vấn đề không phải chỉ chạy một chương trình dưới hai GC rồi so đồng hồ. Benchmark barrier overhead dễ bị nhiễu:

- JIT warm-up và compilation ở những thời điểm khác nhau.
- GC không chạy trong thời gian đo, hoặc chỉ chạy ở một trong hai cấu hình.
- Allocation rate và live-set khác nhau giữa các lần chạy.
- Heap/memory headroom và CPU quota khác nhau.
- CPU frequency, cache, NUMA, page faults, OS scheduling và container throttling.
- Nhiều object được **escape-analysis** loại khỏi heap nên vòng lặp chẳng còn reference loads/writes thực như tưởng tượng.
- Microbenchmark quá ngắn, không che giấu kết quả, bị dead-code elimination hoặc constant folding.
- Một compiler khác nhau áp dụng barrier lowering/optimization khác nhau.

### 11.1. Cách thiết kế phép thử bằng JMH

Dùng **JMH (Java Microbenchmark Harness)** nếu thực sự cần đo những hot paths nhỏ; tạo ít nhất hai workload:

1. **Reference traversal**: vòng duyệt object graph có dữ liệu do JMH state cung cấp, giữ lại checksum bằng `Blackhole`.
2. **Reference mutation**: cập nhật `Node.next`/mảng object reference có kích thước và live-set được kiểm soát, không chỉ cấp phát object tạm rồi cho JIT loại hết.
3. Nếu cần, thêm workload **mixed read/write**, có phân bố giống production, và tách trường hợp nhiều young/old objects.

**Đây là thiết kế benchmark gợi ý**, không phải đoạn mã JMH chạy được khi thiếu dependency. Không đưa JMH vào Java standard library; nó là công cụ độc lập của OpenJDK, cần build dependency và runner tương ứng.

Ví dụ ma trận so sánh:

| Biến cần cố định/ghi lại | Vì sao |
| --- | --- |
| JDK version/build/vendor, architecture | Barrier lowering/JIT/collector thay đổi theo bản |
| GC collector và **Shenandoah mode** | SATB single-gen khác generational |
| `-Xms`/`-Xmx`, live set, allocation rate | Ảnh hưởng tần suất GC và stall |
| Thread count, workload size, object graph | Ảnh hưởng reference traffic và cache |
| Warmup, forks, iterations, CPU affinity | Giảm nhiễu JIT/OS |
| Throughput và CPU cycles | Đánh giá chi phí thực |
| GC STW pause, allocation stall, GC CPU | Đánh giá lợi ích latency/chi phí nền |
| Request latency p95/p99/p99.9 | Đánh giá SLO ở tải ứng dụng |
| Error/timeout rate, offered/completed RPS | Không để throughput sụt mà tưởng tail đã tốt |

Chọn baseline G1 hoặc một mode/collector khác **chỉ khi cùng workload và điều kiện**. Trong hệ thống có nhiều tenant/request, việc thay GC có thể cải thiện pause nhưng giảm throughput; giảm capacity có thể khiến **queue wait** và request tail tệ hơn.

### 11.2. Đừng kết luận chỉ từ nanoTime trong một vòng lặp

Ví dụ kiểu:

~~~java
long t0 = System.nanoTime();
// Vòng lặp nhỏ đọc/ghi field...
long nanos = System.nanoTime() - t0;
~~~

Đây là **mã minh họa không độc lập**. Nếu chưa có JMH hoặc phương pháp đo chống JIT/OS noise, kết quả không phải “giá read barrier” thuần túy.

Nếu muốn đo request latency, dùng `System.nanoTime()` cho **elapsed time trong cùng JVM**, nhưng phải đặt mốc ở **ranh giới request thật**, tính cả queue/downstream/response completion khi SLO yêu cầu. Không lấy giá trị `nanoTime()` tuyệt đối giữa các JVM khác nhau để đối chiếu; dùng timestamp và trace metadata.

## 12. Tác động đến p99 và throughput: một trade-off thực tế

Shenandoah hướng tới việc giảm thời gian ứng dụng phải **đứng yên** để GC; đổi lại có thể yêu cầu thêm công việc trong các **luồng ứng dụng đang chạy** (barrier fast paths) và trong các **GC concurrent threads**.

~~~text
Một Collector A:
  GC pause ngắn hơn
       ↓
  Một số hoạt động mutator có thêm barrier work
       ↓
  CPU/throughput có thể thay đổi
       ↓
  Khi gần bão hòa, queueing có thể thay đổi
       ↓
  Request p99/p99.9 cần được đo lại

Một Collector B:
  Throughput có thể tốt hơn trong workload khác
       ↓
  Nhưng GC pause tail có thể dài hơn
       ↓
  Request p99/p99.9 cũng phải đo lại
~~~

**Không tồn tại kết luận “Shenandoah luôn nhanh hơn G1” hoặc “Shenandoah luôn chậm hơn G1”**. Lựa chọn tối ưu phụ thuộc ứng dụng, JDK version, heap, CPU, tải, số lượng tham chiếu và độ quan trọng của độ trễ đuôi.

Phân biệt ba nhóm chỉ số:

| Chỉ số | Câu hỏi |
| --- | --- |
| **STW GC pause** | Một lần ứng dụng bị JVM tạm dừng bao lâu? |
| **Throughput / CPU cost** | Một giây xử lý được bao nhiêu công việc, tốn bao nhiêu CPU? |
| **Request tail latency** | 1%/0,1% yêu cầu chậm nhất mất bao lâu từ ranh giới đo đã định nghĩa? |

Một pause chỉ 2 ms **không bảo đảm** request p99 dưới 2 ms. Ngược lại, request p99 cao không đủ chứng minh do read/write barrier: có thể do DB, lock, network, scheduler hoặc queue.

## 13. Khi nào cần điều tra barrier overhead?

**Dấu hiệu có thể liên quan:**

- Giảm throughput/IPC khi bật Shenandoah so với cấu hình đối chứng, trong khi GC pause giảm.
- CPU tăng ở workload pointer-chasing hoặc reference mutation và không tăng tương ứng ở business logic.
- Thời gian xử lý trên CPU dài hơn dù số request, payload và downstream giống nhau.
- GC concurrent threads chiếm CPU lớn; mutator threads bị throttling hoặc thiếu CPU.
- Generational mode làm đổi chi phí reference writes ở workload nhiều old → young stores.
- Vòng lặp có nhiều allocation/reference accesses bị ảnh hưởng bởi heap headroom, GC cycle, chứ không chỉ duration pause.

**Nhưng những dấu hiệu này không phải chứng cứ kết luận.** Trước khi đổ lỗi cho barrier:

1. Kiểm tra source/object graph thực sự read-heavy/write-heavy hay chỉ là code CPU-bound khác.
2. Dùng profiler/JFR để xem phần CPU ở đâu; đo allocation rate, queueing, GC CPU và stalls.
3. So JDK/mode/heap/C2 warmup giống nhau.
4. Kiểm tra tải có sát capacity không; chỉ thêm vài % CPU có thể khuếch đại thành tail latency lớn.
5. Thử giải pháp hướng nghiệp vụ: giảm object churn, tránh allocation không cần, cải thiện locality, tối ưu data layout, hạn chế contention — nhưng **không** sửa dữ liệu/đồng bộ chỉ để “né barrier” nếu phá semantics.

**Không dùng `Unsafe`, JNI, off-heap hoặc tự gán pointer để lách GC barrier** như một mẹo tối ưu phổ thông. Điều đó đổi mô hình bộ nhớ/an toàn và có thể tạo lỗi nghiêm trọng. Off-heap/FFM có trade-off riêng, không phải phép sửa trực tiếp cho low-pause collector.

## 14. Lỗi hiểu nhầm thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “Read barrier là `synchronized` hoặc `CyclicBarrier`” | Đây là **GC runtime barrier**, không phải đồng bộ thread Java |
| “Mọi `int` load đều cần LRB” | LRB quan tâm **object reference loads**, không phải mọi primitive load |
| “Mỗi `node.next` Java chắc chắn tạo một lần LRB slow path” | JIT tối ưu; nhiều lần đi fast path, số barrier machine instructions phụ thuộc runtime |
| “LRB lúc nào cũng copy object” | Chỉ xử lý relocate trong trường hợp cần, không copy mỗi load |
| “SATB write barrier chỉ nhìn giá trị mới” | SATB **pre-write** quan tâm reference cũ bị ghi đè khi concurrent marking |
| “Card-marking là chính SATB” | Card barrier generational thường là **post-write** theo dõi old → young |
| “Shenandoah hiện nay luôn single-generation” | Generational Shenandoah đã là product feature ở JDK 25 |
| “Shenandoah JDK 15 đã có generational mode production” | Java 15 production cho Shenandoah; generational đến sau, experimental JDK 24/product JDK 25 |
| “Tắt một diagnostic barrier chắc chắn nhanh và an toàn” | Có thể phá bất biến collector; không làm ở production |
| “Số phép gán trong mã = số barrier thực tế” | JIT có thể remove/merge/hoist/specialize |
| “GC pause ngắn nghĩa là không có mutator overhead” | Barrier + concurrent GC vẫn dùng CPU/memory |
| “Đo một lần bằng nanoTime cho ra giá một barrier” | Bị JIT, OS, cache, GC và phương pháp đo chi phối |
| “Cùng stdout G1/Shenandoah chứng minh hiệu năng ngang nhau” | Chỉ chứng minh **semantics**; không có số liệu duration |
| “Cứ đổi GC là sửa được p99” | Đầu tiên cần xác định queue/CPU/downstream/GC root cause |
| “Card table mặc định có nghĩa mọi ghi là dirty-card” | Có các điều kiện và tối ưu theo mode/collector, không phải mọi write |

## 15. Checklist vận hành và tối ưu Shenandoah

**Trước khi đo:**

- [ ] Kiểm tra `java -version`, vendor, kiến trúc CPU và runtime có Shenandoah hay không.
- [ ] Ghi rõ collector và mode (`satb` hay `generational`) theo JDK thực tế.
- [ ] Dùng `-Xlog:gc*` và JFR theo chính sách logging; tách GC STW pauses với concurrent phases.
- [ ] Định nghĩa request latency SLO và thu p95/p99/p99.9 cùng error/timeout.
- [ ] Ghi `-Xms/-Xmx`, live set, allocation rate, CPU quota, container memory.
- [ ] Dùng benchmark có warm-up, forks, Blackhole và cỡ mẫu đủ nếu đo hot paths.
- [ ] Đảm bảo offered RPS/response size và backend latency tương đương khi so collector.
- [ ] Không bật diagnostic flag tắt barrier hay chạy production với cấu hình GC chưa được kiểm tra.

**Khi phát hiện chậm:**

- [ ] Phân biệt “mutator tốn CPU” với “STW pause dài” và “GC background CPU cao”.
- [ ] Kiểm tra tỷ lệ reference reads/writes, memory locality và khả năng JIT tối ưu.
- [ ] Quan sát allocation stalls, heap headroom, safepoint và thread scheduling.
- [ ] So collector/mode theo cùng workload; ghi cả throughput và request tail.
- [ ] Kiểm tra old → young write traffic nếu dùng generational mode.
- [ ] Tối ưu cấu trúc dữ liệu/giảm allocation nếu có bằng chứng, giữ semantics đúng.
- [ ] Chạy lại regression tests để chắc mọi kết quả nghiệp vụ vẫn đúng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Load-reference barrier dùng để giải quyết vấn đề chính nào trong Shenandoah?  
**Đáp án:** giữ reference phù hợp khi GC **đồng thời di chuyển object**; có fast/slow paths, không có nghĩa luôn copy object mỗi lần đọc.

**Câu 2.** SATB pre-write barrier thường theo dõi reference **cũ** hay **mới**?  
**Đáp án:** **reference cũ** bị ghi đè, khi concurrent marking cần bảo toàn snapshot.

**Câu 3.** Vì sao chế độ generational Shenandoah có thêm post-write card-marking?  
**Đáp án:** để theo dõi những liên kết **old → young**, giúp young collection không bỏ sót object trẻ được object già giữ tham chiếu.

**Câu 4.** Một vòng lặp đọc `int` liên tục có thể suy ra số LRB không?  
**Đáp án:** **Không**. LRB phục vụ object-reference loads, còn JIT có thể tối ưu hoặc loại bỏ những heap accesses khác.

**Câu 5.** Nếu chương trình ghi `referenceStores=640`, có nghĩa GC chạy đúng 640 SATB barriers?  
**Đáp án:** **Không**. Đây là đếm logic trong code Java; GC chỉ làm việc cần thiết theo pha, mode và tối ưu runtime.

**Câu 6.** Shenandoah generational lần đầu là product feature ở JDK nào?  
**Đáp án:** **JDK 25, JEP 521**. JDK 24 có bản experimental theo JEP 404; Java 15 đưa **Shenandoah collector** production theo JEP 379.

**Câu 7.** Tại sao GC max pause 3 ms vẫn có thể xuất hiện request p99 100 ms?  
**Đáp án:** request còn chịu queueing, CPU, downstream và chi phí concurrent/barrier; GC pause không phải giới hạn request latency.

**Câu 8.** Làm sao định lượng barrier overhead mà không gây ngộ nhận?  
**Đáp án:** dùng **benchmark có đối chứng** (JMH phù hợp, JIT warm-up, cùng workload/JDK/heap/CPU), profile CPU/GC và so request SLO; không lấy một lần `nanoTime` làm “giá một barrier”.

## 17. Tài liệu chính thức và nguồn hiện hành

- **OpenJDK JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production)**, Java 15: https://openjdk.org/jeps/379
- **OpenJDK JEP 404 — Generational Shenandoah (Experimental)**, JDK 24: https://openjdk.org/jeps/404
- **OpenJDK JEP 521 — Generational Shenandoah**, product feature từ JDK 25: https://openjdk.org/jeps/521
- **OpenJDK Shenandoah Wiki — Main**, kiến trúc collector và barrier/mode: https://wiki.openjdk.org/display/shenandoah/Main
- **OpenJDK HotSpot source — ShenandoahBarrierSet.inline.hpp**, các đường xử lý SATB/load-reference/card: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shenandoah/shenandoahBarrierSet.inline.hpp
- **OpenJDK HotSpot `java` launcher documentation**, mô tả mode `satb` và `generational`: https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md
- **Oracle Java SE 25 — The java Command**, cấu hình GC và `-Xlog`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **OpenJDK JMH — Java Microbenchmark Harness**, công cụ benchmark micro có warm-up/forks: https://github.com/openjdk/jmh
- **Red Hat Developer — Shenandoah GC in JDK 13: Load Reference Barriers**, nguồn giải thích lịch sử cơ chế LRB (không dùng để suy ra default mode JDK mới): https://developers.redhat.com/blog/2019/06/27/shenandoah-gc-in-jdk-13-part-1-load-reference-barriers