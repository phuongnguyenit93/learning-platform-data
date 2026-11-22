# GC xác định đối tượng còn truy cập được từ gốc như thế nào?

Trong Java, **garbage collector (GC)** không đơn giản xóa object sau khi một biến cục bộ kết thúc, cũng không chỉ đếm số reference trỏ vào object. Để xác định những object cần được giữ lại, các tracing collectors của JVM bắt đầu từ một tập **GC roots**, lần theo những đường tham chiếu có ý nghĩa giữ sống object và xây dựng tập đối tượng **reachable**. Những object không còn được giữ sống theo quy tắc reachability/reference processing có thể trở thành ứng viên thu hồi.

Đây là nền tảng của chủ đề **khả năng truy cập (reachability)**: phải phân biệt **reference tồn tại**, **reference còn sống về mặt chương trình**, **object reachable từ GC roots**, **object được xử lý theo weak/soft/phantom reference**, và **bộ nhớ thực sự đã được GC thu hồi**.

Điểm quan trọng ngay từ đầu:

- **Reachable** nghĩa là vẫn có đường giữ sống thích hợp từ một hoặc nhiều GC roots theo mô hình của collector.
- **Unreachable** không có nghĩa object được giải phóng ngay tại câu lệnh cuối cùng: GC chạy theo chính sách runtime, còn reference processing, finalization legacy và concurrency có những quy tắc bổ sung.
- **Chu trình reference không tự làm object sống mãi.** Hai object trỏ lẫn nhau nhưng không còn đường giữ sống từ root có thể được GC thu hồi.
- **Reference mạnh, mềm, yếu và phantom không mang cùng ý nghĩa giữ sống.** Nếu duyệt tất cả các cạnh mà không phân loại, bạn sẽ diễn giải sai các trường hợp dùng `WeakReference`, `SoftReference` hay `PhantomReference`.
- **GC roots thuộc trạng thái JVM**, không phải mọi biến từng xuất hiện trong source Java. JIT và liveness analysis có thể xác định reference nào thực sự còn cần để duy trì ngữ nghĩa.

Bài dùng Java 17+ cho ví dụ runnable và phân biệt **mô hình đồ thị để học** với **thuật toán/metadata cụ thể của HotSpot**. JVM Specification không bắt buộc mọi collector dùng một thuật toán marking hay một cấu trúc root table giống nhau.

## 1. Reachability là bài toán đồ thị

Hãy mô hình hóa các object trên heap thành **đỉnh** của một đồ thị. Một field kiểu reference hoặc một phần tử mảng chứa reference có thể tạo **cạnh** từ object đang chứa field/element tới object được trỏ tới.

```text
GC ROOTS
 ├── stack/local reference ──► A ─────► C ────► D
 └── static reference ───────► B ─────► C

                                 E ───► F
                                 ▲      │
                                 └──────┘
```

Trong đồ thị này, giả sử các mũi tên được vẽ là **strong reference edges**:

- **A, B** có đường bắt đầu từ root nên reachable.
- **C** reachable qua A hoặc B; **D** reachable qua C.
- **E và F** trỏ lẫn nhau nhưng không có đường từ root tới chúng. Chu trình E ↔ F không làm chúng reachable.
- Nếu sau đó mất cả hai cạnh A → C và B → C, C và D cũng không còn reachable từ các root **được vẽ**, trừ khi thực tế còn cạnh hoặc root khác chưa được thể hiện.

Đồ thị này là **ví dụ trừu tượng**, không phải ảnh chụp tất cả GC roots của một JVM. Một object vẫn có thể được giữ sống bởi references khác không nằm trong hình, như JNI global handle hoặc local reference còn được VM xem là live.

### Định nghĩa trực quan

Gọi **R** là tập GC roots, và **E** là tập các cạnh **strong references** giữa các object. Tập **strongly reachable** là các object có thể đi tới từ ít nhất một root bằng một chuỗi không hoặc nhiều cạnh có tính giữ sống mạnh.

Một cách mô tả thuật toán:

```text
worklist = các object tham chiếu trực tiếp bởi GC roots
marked   = tập rỗng

while worklist chưa rỗng:
    obj = lấy một object từ worklist
    if obj đã marked:
        tiếp tục
    thêm obj vào marked
    với mỗi strong reference từ obj:
        nếu referent khác null:
            đưa referent vào worklist

marked = tập strongly reachable trong mô hình snapshot này
```

Đây là **pseudocode**, không phải source Java độc lập hay mô tả một thuật toán duy nhất của mọi GC. Mục đích là **duyệt đồ thị có đánh dấu**. Nếu không có tập `marked`, một chu trình A → B → A có thể khiến phép duyệt lặp vô hạn.

### Vì sao không dùng reference counting thuần túy?

Một bộ đếm số reference đơn giản sẽ thấy E có một reference từ F và F có một reference từ E; cả hai có số đếm dương dù không còn root. **Tracing reachability** phân biệt được chu trình còn sống từ root và chu trình bị cô lập.

Không suy ra HotSpot chỉ đếm reference hay chỉ quét field lần lượt một lần: các collectors hiện đại có write barriers, concurrent phases, card tables/remembered sets và reference processing phục vụ tính đúng đắn lẫn hiệu năng.

## 2. GC roots là gì?

**GC root** là một điểm xuất phát mà collector có thể dùng để khám phá object còn cần giữ sống theo trạng thái thực thi JVM. Root thường không phải “object đầu tiên duy nhất”; hệ thống có thể có nhiều tập roots từ các vùng runtime khác nhau.

Những nhóm phổ biến trong HotSpot/JVM:

| Nguồn gốc root | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Live references trong Java thread stacks/frames** | Tham chiếu tới object còn cần cho method đang thực thi | Không phải mọi local variable từng tồn tại đều tiếp tục là root |
| **Static fields / runtime class state còn sống** | Cache object trong static field của một class còn được giữ sống phù hợp | Class loader/class metadata reachability có ảnh hưởng; không phải mọi class từng load được giữ mãi |
| **JNI handles** | JNI global references, một số JNI local references | JNI **weak global** có semantics khác strong JNI references |
| **VM-internal handles/structures** | Object dùng bởi hệ thống VM, runtime services, references đang xử lý | Danh sách chính xác phụ thuộc collector/implementation |
| **Các reference trong đường thực thi native/transition** | Object đã được đưa vào cơ chế JNI/runtime handle | Collector cần giải mã những references theo luật VM |
| **Một số root đặc biệt do collector theo dõi** | Structures phục vụ class unloading, reference processing, code metadata | Cách tổ chức phụ thuộc phiên bản HotSpot |

**Không nên lấy danh sách trên làm hợp đồng bất biến giữa các collectors.** Có những nguồn được một collector coi là root trực tiếp, và nguồn khác được xử lý qua metadata/remembered sets hoặc một pha quét liên quan. Quan trọng là **mọi object phải sống theo ngữ nghĩa chương trình đều được bảo vệ khỏi thu hồi sai**.

### 2.1. Live references trong stack

Ví dụ:

```java
static void printValue() {
    Object value = new Object();
    System.out.println(value);
}
```

Đây là một **method minh họa**, cần đặt trong class để biên dịch. Trong lúc `value` còn cần cho `println`, VM phải bảo toàn khả năng dùng object đúng ngữ nghĩa. Nhưng **không thể khẳng định biến `value` là GC root mạnh suốt toàn bộ thời gian method còn nằm trên call stack**.

JIT có thể xác định **điểm sử dụng cuối** của reference và tối ưu những liveness intervals. Sau lần dùng cuối, một object có thể trở nên không còn strongly reachable sớm hơn thời điểm block/method kết thúc, nếu điều đó bảo toàn semantics.

Vì vậy câu “local variable còn trong scope Java thì object chắc chắn không bao giờ được GC” là một **kết luận quá mạnh**. Java-level scope và liveness mà VM cần duy trì không đồng nhất.

### 2.2. Static fields và class loaders

```java
class Registry {
    static Object shared = new Object();
}
```

Khi `Registry` và runtime state của nó được giữ sống, `Registry.shared` có thể góp một **đường giữ sống** tới object. Nhưng static state không là “bộ nhớ bất tử” trong mọi trường hợp: khi một **defining class loader** và các class do nó định nghĩa đủ điều kiện unloading, metadata/static references liên quan cũng có thể được giải phóng theo quy tắc VM.

**Lỗi memory leak phổ biến:** static collection của một class sống lâu giữ reference mạnh tới nhiều object không còn cần dùng:

```java
static final java.util.List<Object> CACHE = new java.util.ArrayList<>();
```

Đây chỉ là field minh họa trong một class. Nếu ứng dụng cứ thêm items vào `CACHE` mà không loại bỏ, các phần tử có thể tiếp tục reachable dù nghiệp vụ đã “quên” chúng. GC không thể tự biết object nào đã hết giá trị nghiệp vụ khi vẫn còn đường strong reference từ root.

### 2.3. JNI global và weak global references

Native code thông qua JNI có thể giữ reference tới Java objects bằng các JNI handles. **Global reference mạnh** có thể góp phần giữ sống object, trong khi **weak global reference** được xử lý theo quy tắc weak reachability thích hợp.

Điểm quan trọng: nếu heap analyzer không thể chỉ ra một static field hay local Java cụ thể nhưng object vẫn reachable, cần cân nhắc **JNI handles**, runtime services, class loaders, thread locals và các nguồn ngoài những field source thông thường.

## 3. Khi duyệt, GC theo cạnh nào?

Với một object reachable, collector có thể nhận diện references trong:

- **Instance reference fields**, ví dụ `Node.next`.
- **Reference array elements**, ví dụ các vị trí của `Object[]`.
- **Các object được nhắc tới gián tiếp thông qua metadata/handles** theo cơ chế VM.
- **Một số cấu trúc đặc biệt** như `java.lang.ref.Reference` phải xử lý theo luật khác với một field mạnh thông thường.

Không phải mọi byte trong một object đều là pointer:

```java
class Holder {
    int count;
    long timestamp;
    Object value;
}
```

Trong ví dụ này, `count` và `timestamp` là dữ liệu primitive, không phải heap pointers mà GC được phép tùy ý diễn giải. `value` là một reference field và có thể đóng vai trò cạnh.

HotSpot dựa vào **metadata về layout** để biết vị trí chứa object references trong fields, arrays và runtime frames. JIT-compiled code còn cung cấp **oop maps** hoặc thông tin tương đương tại các điểm GC cần biết vị trí live references trong registers/stack. Điều đó cho phép precise GC khác với lối coi mọi word có hình dạng địa chỉ là một root chắc chắn.

### 3.1. Không phải “mọi reference đều mạnh”

`WeakReference`, `SoftReference` và `PhantomReference` là những đối tượng Java có field nội bộ liên hệ tới referent. Tuy nhiên collector **không được coi cạnh tới referent từ những đối tượng này giống hệt một ordinary strong field**.

Ví dụ:

```java
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(new Object());
```

Đây là đoạn trong method. Biến `weak` có thể còn strongly reachable, nhưng object **được `weak` tham chiếu tới** không vì thế tự có một strong path. Việc referent tồn tại tới lúc GC nào là chuyện khác, tùy còn đường strong/soft references ở nơi khác và timing GC.

Đừng lẫn **reference object** (`WeakReference` instance) với **referent** (object mà `get()` có thể trả về).

## 4. Marking: đánh dấu tập reachable

Một thuật toán tracing GC có thể chia công việc thành:

1. **Root discovery/scanning**: xác định các references xuất phát từ root set.
2. **Graph traversal**: lần theo những cạnh cần giữ sống, theo dõi objects đã thăm.
3. **Reference processing**: xử lý soft/weak/phantom references và các semantics đặc biệt.
4. **Reclamation**: cho phép tái sử dụng vùng nhớ của các objects không còn cần giữ sống, bằng sweep/copy/compaction hay cơ chế tương ứng.
5. **Cập nhật pointers/metadata khi di chuyển objects**: giữ các references còn sống trỏ đúng địa chỉ mới, nếu collector dùng moving/compacting collection.

Đây là **khung ý tưởng**, không phải thứ tự cứng của mọi JVM. Những pha có thể lồng nhau, chạy đồng thời hoặc khác nhau giữa Serial, Parallel, G1, ZGC, Shenandoah và các collectors khác.

### 4.1. Tri-color abstraction

Trong nhiều tài liệu, tracing được giải thích qua ba màu:

| Màu | Ý nghĩa trong mô hình |
| --- | --- |
| **White** | Chưa được phát hiện/đánh dấu |
| **Gray** | Đã được tìm thấy nhưng còn edges cần quét |
| **Black** | Đã quét xong các edges cần xem |

```text
Roots → GRAY
             │
             ▼
     lấy một gray object
             │
      khám phá children
             │
     white child → gray
             │
             ▼
   object vừa quét → black
```

Kết thúc tracing, những objects còn **white** trong tập đang được thu gom có thể trở thành ứng viên reclaim, **sau khi** thỏa các quy tắc reference processing, finalization legacy và collectors cụ thể.

**Tri-color là mô hình suy luận**, không bảo đảm mỗi collector có đúng ba bit màu vật lý được đặt trong mỗi object header. Có thể dùng mark bitmaps, remembered sets, queues và metadata phức tạp hơn.

### 4.2. DFS, BFS hay work stealing đều có thể đúng

Collector có thể dùng stack, queue, bitmap hoặc nhiều worklists song song để duyệt đồ thị. Thứ tự thăm A trước B hay B trước A không làm thay đổi tập reachable trong một **snapshot bất biến** nếu thuật toán hoàn chỉnh và xử lý chu trình đúng.

Với concurrent collectors, đồ thị **không bất biến** vì application threads (mutators) vẫn tạo/xóa refs. Khi đó cần cơ chế bổ sung để không bỏ sót các objects phải sống.

## 5. Stop-the-world và concurrent marking khác nhau như thế nào?

### Stop-the-world (STW)

Trong những pha STW, JVM tạm dừng application threads ở các điểm an toàn tương ứng để collector quan sát/truy cập trạng thái đủ nhất quán. Điều này làm dễ hình dung root scanning và một số thao tác di chuyển/cập nhật object graph.

Không phải mọi GC đều STW xuyên suốt toàn bộ chu kỳ. Nhiều collectors có một số pha STW ngắn và một số pha concurrent; độ dài pause phụ thuộc collector và workload.

### Concurrent marking

Trong concurrent marking, một hoặc nhiều GC threads quét đồ thị **trong khi mutator threads còn thay đổi references**. Điều đó tạo bài toán:

```text
Thời điểm 1:
Root → A → B

Đang mark thì application sửa:
Root → A
       A.child = null
Root → C (đối tượng mới được publish)
```

Nếu collector bỏ qua những thay đổi quan trọng, nó có thể bỏ sót object còn cần sống. Vì vậy các concurrent collectors sử dụng **barriers** và các luật về marking state để bảo đảm tính đúng đắn.

Hai ý tưởng tiêu biểu:

- **Snapshot-at-the-beginning (SATB):** theo dõi một cách thích hợp các references cũ khi application xóa/ghi đè cạnh, duy trì mô hình snapshot ban đầu theo invariants của collector.
- **Incremental-update:** ghi nhận các cạnh mới/changes cần xử lý để bảo toàn invariant khi object đã quét xong được cập nhật trỏ tới object chưa đánh dấu.

**Không nên nói tất cả JVM collectors dùng SATB hoặc tất cả đều dùng incremental-update cùng một cách.** Đây là hai họ kỹ thuật. Một collector có thể dùng nhiều barriers cho mục tiêu khác nhau (marking, card marking, relocation, load barrier...).

### 5.1. Write barrier là gì?

Một write barrier trong GC là đoạn cơ chế runtime được thực hiện quanh thao tác **ghi một reference** để cập nhật thông tin cho collector khi cần. Nó khác với Java memory-order barrier trong thảo luận JMM, dù tên tương tự.

Ví dụ source:

```java
a.next = b;
```

Compiler/JVM có thể thực hiện thao tác ghi reference cùng hoạt động barrier liên quan. **Barrier không phải một method Java source bắt buộc người lập trình phải tự gọi.** Nó có thể được JVM/JIT chèn vào machine code.

### 5.2. Load barriers và moving collectors

Một số collectors concurrent/moving dùng **load barriers** hoặc cơ chế đọc references đặc biệt để bảo đảm Java threads có reference hợp lệ trong khi objects di chuyển.

Đừng giả định bất kỳ reference nào cũng được cập nhật cùng cách: chiến lược VM có thể dùng forwarding pointers, colored pointers, relocation metadata hoặc phương án khác. Người viết Java chủ yếu cần tuân theo Java Memory Model và dùng các APIs chuẩn; không tự thao tác raw addresses.

## 6. Generational GC: quét gốc và nhớ cạnh từ vùng khác

Nhiều collectors chia heap thành vùng theo tuổi/lifetime (young/old generations hoặc regions). Một **young collection** không cần xem toàn bộ old generation như một root khổng lồ rồi quét mọi object sâu như full-heap traversal.

Vấn đề minh họa:

```text
Young region: Y
                 ▲
                 │
Old object O ────┘
```

Nếu object `O` ở vùng cũ giữ reference tới `Y` ở vùng trẻ, một collection chỉ tập trung vào young generation **không được bỏ qua cạnh O → Y** chỉ vì O nằm ngoài vùng đang thu gom.

**Remembered sets**, **card tables** và các cơ chế liên quan cho phép collector biết những vùng ngoài collection set có thể chứa references đi vào vùng cần thu gom. Chúng bổ sung cho root scanning.

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Collection set** | Những regions/generations đang được xử lý trong đợt thu gom phù hợp |
| **Remembered set** | Ghi nhớ references/locations từ ngoài vùng thu gom có thể trỏ vào vùng đó |
| **Card table** | Metadata thường dùng để theo dõi các vùng bộ nhớ đã bị ghi reference |
| **Post-write barrier** | Cơ chế đánh dấu/cập nhật metadata sau ghi phù hợp với collector |
| **Cross-generational reference** | Cạnh ví dụ old → young cần được tính khi thu gom young |

**Rút ra:** đồ thị reachable logic vẫn là nền tảng, nhưng collector tối ưu không nhất thiết quét **toàn bộ heap từ đầu** trong từng young GC. Nó sử dụng root set liên quan và metadata ghi nhớ các cạnh xuyên vùng.

## 7. Strong, soft, weak và phantom reachability

Java có API `java.lang.ref` để làm việc với những mức reference đặc biệt. Không thể thay chúng bằng một luật đơn giản “object nằm trên heap hoặc không”.

| Loại tham chiếu | Ý nghĩa khái quát | API ví dụ |
| --- | --- | --- |
| **Strong reference** | Đường tham chiếu thông thường có khả năng giữ object sống | `Object x = new Object()`, field, array element |
| **Soft reference** | Cho phép GC thu hồi referent theo chính sách, thường liên quan memory pressure | `SoftReference<T>` |
| **Weak reference** | Không ngăn việc collector thu hồi referent nếu chỉ còn weak reachability | `WeakReference<T>` |
| **Phantom reference** | Hỗ trợ theo dõi giai đoạn sau khi object không còn reachable ở mức mạnh hơn, thường đi với `ReferenceQueue` | `PhantomReference<T>` |
| **Finalizer legacy** | Cơ chế finalization lịch sử, không đáng tin cho quản lý tài nguyên | `finalize()` (deprecated từ Java 9; deprecated for removal từ JDK 18) |

### 7.1. Strong reference

```java
Object keepAlive = new Object();
```

Reference `keepAlive` có ý nghĩa giữ sống object **khi chính reference đó thực sự live và nằm trên đường được VM coi là cần bảo toàn**. Không thể suy ra một biến đã gán nhưng không còn sử dụng sẽ giữ object tới hết method.

Ordinary strong paths là tuyến nền tảng của thuật toán marking được trình bày ở mục 1.

### 7.2. SoftReference

```java
java.lang.ref.SoftReference<byte[]> soft =
        new java.lang.ref.SoftReference<>(new byte[1_024]);
```

Một `SoftReference` cho phép GC đưa ra quyết định thu hồi referent theo chính sách. Soft references từng hay được dùng để làm caches, nhưng **không nên coi soft cache là cơ chế giới hạn memory chính xác hay giải pháp thay thế cache eviction có kiểm soát**.

Theo API, soft references tới các objects softly reachable có các bảo đảm xử lý liên quan tới `OutOfMemoryError` trong phạm vi được mô tả, nhưng không có cam kết “GC sẽ xóa soft refs theo thứ tự LRU rõ ràng” hoặc “soft.get() chắc chắn khác null nếu heap còn X MB”. Các heuristics cụ thể phụ thuộc implementation.

### 7.3. WeakReference

```java
Object strong = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(strong);
```

Khi `strong` còn là một strong path live tới object, weak referent không bị clear chỉ vì tồn tại `WeakReference`. Nếu toàn bộ strong paths mất và object chỉ còn weakly reachable (không có soft path mạnh hơn còn giữ nó), một GC thích hợp có thể **clear weak reference** và đưa nó vào queue theo luật.

Ví dụ có `strong = null` **không tự động khiến `weak.get() == null` ngay dòng sau**. GC có thể chưa chạy; JIT liveness và paths khác cũng ảnh hưởng.

`WeakHashMap` sử dụng weak references cho **keys**, hữu ích trong những tình huống liên kết metadata với keys mà không muốn map giữ chúng sống bằng key reference của chính map. Nhưng nếu value giữ strong reference trở lại key, key vẫn có thể sống qua đường map → value → key; thiết kế cache cần xem đồ thị thực tế.

### 7.4. PhantomReference

```java
java.lang.ref.ReferenceQueue<Object> queue =
        new java.lang.ref.ReferenceQueue<>();
java.lang.ref.PhantomReference<Object> phantom =
        new java.lang.ref.PhantomReference<>(new Object(), queue);
```

**`phantom.get()` luôn trả `null`**, bất kể referent đã đến giai đoạn nào. API này dùng với queue để theo dõi các sự kiện GC-reference processing theo quy tắc, thường làm nền cho cơ chế cleanup không phụ thuộc finalizer.

Không dùng phantom reference để “cứu” object trở lại sử dụng như strong reference. Khi cần giải phóng file/socket/native resource đúng lúc, ưu tiên **`AutoCloseable` / try-with-resources**. Cleaner/phantom cleanup là cơ chế dự phòng có tính bất định về thời điểm, không bảo đảm sẽ chạy trước khi tiến trình thoát.

### 7.5. Thứ bậc reachability là khái niệm tinh tế

Trong mô hình Java references, có các trạng thái như **strongly reachable**, **softly reachable**, **weakly reachable**, **phantom reachable** và **unreachable**, phụ thuộc còn đường mạnh hơn hay không. Đường đi qua một `SoftReference` hoặc `WeakReference` không có cùng ngữ nghĩa giữ sống với ordinary field.

Đây không phải một bảng “GC chắc chắn reclaim trong X mili-giây” cho từng loại. Collector còn phải xử lý queues, reference clearing, cleanup, finalization legacy và các điều kiện runtime.

## 8. ReferenceQueue: quan sát thông báo, không ép GC theo lịch

Một `ReferenceQueue` nhận những `Reference` objects đã được xử lý/enqueue theo quy tắc API. Nó hữu ích để ứng dụng biết rằng referent đã đạt trạng thái liên quan, nhưng **không là lịch định thời GC**.

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

class QueueExample {
    static void show() {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object value = new Object();
        WeakReference<Object> weak = new WeakReference<>(value, queue);

        System.out.println(weak.get() == value); // true tại thời điểm này
        value = null;

        // Không được khẳng định queue.poll() chắc chắn có kết quả ngay đây.
        System.out.println("GC timing is not deterministic");
    }
}
```

Đây là **class đầy đủ cú pháp** với static method `show()`, nhưng **không có main**. Hai dòng println bên trong minh họa cách dùng; để chạy độc lập cần gọi `QueueExample.show()` từ một main class.

**Hai điều khác nhau:** `weak.get()` có thể đã bị clear khi GC chạy; `queue.poll()` có thể chưa trả tham chiếu tương ứng vào đúng thời điểm bạn hỏi. Giữ `WeakReference` object mạnh khi muốn quan sát queue; bản thân reference object cũng có lifecycle riêng.

### Lưu ý về `System.gc()`

`System.gc()` về bản chất là **gợi ý/yêu cầu** đối với runtime, không phải hợp đồng cho phép test assert rằng ngay sau lời gọi, một object cụ thể đã được thu hồi. Có JVM flags/chế độ trong đó explicit GC bị bỏ qua hoặc xử lý khác. **Không dùng `Thread.sleep` + `System.gc` như một “đồng hồ chứng minh” reachability.**

## 9. Chu trình tham chiếu: điểm yếu của suy nghĩ theo reference count

Giả sử hai objects:

```java
class Node {
    Node next;
}
```

và trong method:

```java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
```

Đây là code minh họa trong một method. Khi **không còn strong path từ GC roots** tới a hay b, vòng a → b → a không đủ giúp chúng sống. Một tracing collector có thể không đánh dấu chúng trong lần tracing phù hợp.

Nhưng **đừng vội kết luận GC đã thu hồi ngay** khi viết:

```java
a = null;
b = null;
```

Việc gán null không tự tạo ra một GC cycle và cũng không chứng minh không có reference khác (static cache, JNI, thread-local, field của một object sống, v.v.). Điều kiện đủ để một object **có thể là rác** phải xét **toàn bộ root graph thực tế**, không chỉ hai biến trong đoạn code.

### Cycle reachable và unreachable khác nhau

```text
Case 1: ROOT → A → B → A  (cả A và B reachable)
Case 2:         A → B → A  (không có đường root nào, có thể reclaim)
```

Trong case 1, cycle vẫn sống vì có **một lối vào từ root**. Trong case 2, mọi object của cycle có thể là ứng viên thu hồi sau khi xử lý các loại reference đặc biệt phù hợp.

## 10. Ví dụ Java 17+ chạy được: mô phỏng graph tracing có chu trình

Chương trình sau **không tự gọi GC**. Nó mô phỏng thuật toán duyệt từ một tập roots **do người học lựa chọn**, để có output **chính xác và có thể kiểm chứng**, không phụ thuộc thời điểm collector chạy.

Tạo file **`ReachabilityGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public class ReachabilityGraphDemo {
    static final class Node {
        final String name;
        Node first;
        Node second;

        Node(String name) {
            this.name = name;
        }
    }

    static Set<Node> trace(Node... roots) {
        Set<Node> marked =
                Collections.newSetFromMap(new IdentityHashMap<Node, Boolean>());
        Deque<Node> worklist = new ArrayDeque<>();

        for (Node root : roots) {
            if (root != null) {
                worklist.addLast(root);
            }
        }

        while (!worklist.isEmpty()) {
            Node current = worklist.removeFirst();

            if (!marked.add(current)) {
                continue;
            }

            if (current.first != null) {
                worklist.addLast(current.first);
            }
            if (current.second != null) {
                worklist.addLast(current.second);
            }
        }
        return marked;
    }

    static void printMarked(Set<Node> marked) {
        List<String> names = new ArrayList<>();
        for (Node node : marked) {
            names.add(node.name);
        }
        Collections.sort(names);
        System.out.println("reachable (" + marked.size() + "): " + names);
    }

    public static void main(String[] args) {
        Node rootA = new Node("rootA");
        Node rootB = new Node("rootB");
        Node branch = new Node("branch");
        Node leaf = new Node("leaf");
        Node orphanA = new Node("orphanA");
        Node orphanB = new Node("orphanB");

        rootA.first = branch;
        rootB.first = branch;
        branch.first = leaf;
        leaf.first = rootA; // Chu trình reachable từ rootA/rootB.

        orphanA.first = orphanB;
        orphanB.first = orphanA; // Chu trình tách khỏi roots đã chọn.

        System.out.println("total modeled nodes: 6");
        Set<Node> firstPass = trace(rootA, rootB);
        printMarked(firstPass);
        System.out.println("outside selected roots: " + (6 - firstPass.size()));

        rootA.first = null;
        rootB.first = null;

        Set<Node> secondPass = trace(rootA, rootB);
        printMarked(secondPass);
        System.out.println("outside selected roots: " + (6 - secondPass.size()));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ReachabilityGraphDemo.java
java ReachabilityGraphDemo
```

**Standard output chính xác:**

```text
total modeled nodes: 6
reachable (4): [branch, leaf, rootA, rootB]
outside selected roots: 2
reachable (2): [rootA, rootB]
outside selected roots: 4
```

### Giải thích từng dòng

1. Chương trình tạo **sáu `Node` objects** trong đồ thị mô hình.
2. `trace(rootA, rootB)` có hai roots và tìm được `rootA`, `rootB`, `branch`, `leaf`, tức bốn nodes.
3. Chu trình `orphanA ↔ orphanB` không có cạnh từ hai roots đã chọn, nên hai nodes đó không được `trace` đánh dấu.
4. Gỡ hai cạnh `rootA.first` và `rootB.first`; lần tracing thứ hai chỉ tìm được hai roots. `branch`/`leaf` đã mất lối vào, và chu trình orphan vẫn không có lối vào.
5. Dùng `IdentityHashMap` để tập `marked` so **object identity (`==`)**. Đánh dấu GC theo object identity; không dùng `equals()` do application override để tự gom các object khác nhau thành một.
6. `Collections.sort(names)` làm output theo tên ổn định dù traversal order hoặc identity hash khác nhau.

**Cực kỳ quan trọng:** output `outside selected roots` có nghĩa **không reachable trong đồ thị `Node.first/second` từ hai roots mô phỏng**. Nó **KHÔNG** chứng minh HotSpot đã thật sự thu hồi object nào! Trong `main`, các local variables `branch`, `leaf`, `orphanA`, `orphanB` và tập `firstPass` có thể vẫn chứa references mà JVM phải xét tùy liveness. Mô phỏng cũng bỏ qua references trong `String name`, collection metadata và các roots khác.

Đây là lý do viết mô hình cho học tập và đo GC thực tế là **hai nhiệm vụ khác nhau**. Mô hình minh họa thuật toán chính xác trong phạm vi đồ thị đã định nghĩa; không tự xưng là một heap inspector.

### 10.1. Độ phức tạp của tracing

Nếu mỗi object được đánh dấu đúng một lần và mỗi strong reference edge được xét hữu hạn lần, phép duyệt đồ thị có độ phức tạp **O(V + E)** với V = số object vertices và E = số reference edges trong phạm vi duyệt. Bộ nhớ phụ thường phụ thuộc tập marked và worklist.

Ở JVM thực tế, chi phí còn có:

- **Root scanning** và metadata tìm references.
- **Barriers/remembered sets** khi concurrent hoặc generational.
- **Reference processing**, moving/compaction và pointer updates.
- **Load balancing/work stealing** giữa GC threads.
- **Object layout**, region selection, card scanning và fragmentation.

Không dùng O(V+E) để suy ra tất cả GC pause đều có cùng thời gian tuyến tính trên toàn heap: các collector tối ưu theo tập object/region cần xử lý, thực hiện song song hoặc concurrent, và chỉ một số pha mới STW.

## 11. `Reference.reachabilityFence`: giữ sống object tới điểm cần thiết

JDK cung cấp API **`Reference.reachabilityFence(Object)`** từ Java 9 để đảm bảo một object còn **strongly reachable** cho tới một điểm thực thi cụ thể, khi điều đó quan trọng cho an toàn resource/native code.

Ví dụ khái niệm:

```java
import java.lang.ref.Reference;

final class NativeResource {
    final long handle;

    NativeResource(long handle) {
        this.handle = handle;
    }

    void perform() {
        long h = handle;
        NativeApi.useHandle(h);
        Reference.reachabilityFence(this);
    }
}
```

**Đây là đoạn minh họa, chưa chạy độc lập**: `NativeApi` chưa được định nghĩa, và `handle` chỉ là đại diện cho tài nguyên native. Ý nghĩa:

- Trong đường thực thi, sau khi lấy `handle`, native code có thể đang sử dụng tài nguyên gắn với object.
- Không đủ an toàn để giả định receiver `this` tự động live đến hết method chỉ vì method chưa return.
- `reachabilityFence(this)` giúp bảo đảm receiver sống tới sau lời gọi native trong ngữ cảnh được yêu cầu.
- API **không yêu cầu GC thu hồi object ngay sau fence**, và cũng không thay thế quản lý vòng đời tài nguyên tường minh.

Nếu resource cần đóng đúng lúc, dùng `AutoCloseable`/try-with-resources vẫn là cách thiết kế ưu tiên.

## 12. Finalization và object resurrection: ngoại lệ lịch sử cần biết

Các lớp Java cũ đôi khi override `finalize()`. Trong những mô hình finalization legacy, finalizer có thể làm object **reachable trở lại** (resurrection), ví dụ gán `this` vào một static field. Vì thế sơ đồ “không strongly reachable thì chắc chắn giải phóng ngay” không đủ mô tả mọi pha xử lý.

Tuy nhiên:

- **Finalization bị deprecated từ Java 9 và deprecated for removal từ JDK 18**; không khuyến khích cơ chế này trong Java hiện đại.
- Không có bảo đảm finalizer sẽ chạy đúng lúc hoặc chắc chắn trước khi process thoát.
- Finalizer có rủi ro security, reliability, deadlocks và memory retention.
- Không nên viết ứng dụng mới dựa trên resurrection hay `System.gc()` để ép finalize.

Thay thế hợp lý là **explicit close**, `try-with-resources`, và **Cleaner/phantom-based cleanup** chỉ như cơ chế dự phòng khi cần. Cleaner cũng có tính bất định về thời điểm, và cleaning action không nên giữ strong reference ngược lại tới referent mà nó cần theo dõi.

Khi đọc tài liệu reachability rất cũ, hãy nhận biết luật **finalization queue** có thể làm collector phải giữ objects thêm thời gian; các JVM/JDK mới tiếp tục phát triển để loại bỏ đường khởi tạo finalizer không an toàn.

## 13. GC eligibility khác thời điểm thu hồi và thời điểm tái sử dụng bộ nhớ

Ba trạng thái dễ lẫn:

| Câu hỏi | Ý nghĩa |
| --- | --- |
| Object còn strongly reachable? | Có đường reference mạnh từ roots tới object tại trạng thái liên quan? |
| Object eligible for collection? | Có còn cần bảo toàn theo các quy tắc reachability/reference processing khác không? |
| Bộ nhớ đã được reclaim/reused? | Collector đã thực hiện pha cho phép tái sử dụng không gian phù hợp chưa? |

Một object không còn reachable có thể:

- Nằm ở vùng heap chưa được collection cycle nào xử lý.
- Đang chờ một số reference processing/cleanup theo semantics.
- Có memory space được collector đánh dấu có thể dùng lại nhưng không lập tức trả về OS.
- Được thu hồi trong một collection, nhưng **heap committed size** hoặc **process RSS** không giảm tương ứng ngay.

Vì vậy khi đo memory:

- `-Xmx` là giới hạn Java heap, **không** là số byte heap đang dùng.
- `used heap` không đồng nghĩa retained size của một object graph.
- `committed` và `reserved` khác nhau; OS RSS lại là metric khác.
- Object đã chết không chứng minh heap sẽ lập tức thu nhỏ.
- Một memory leak Java thường là **unintended reachability**, không phải GC “quên chạy”.

## 14. Memory leaks do đối tượng còn reachable ngoài ý muốn

Một tracing GC **không thể biết logic nghiệp vụ** rằng object đã “không còn cần nữa”. Nếu vẫn còn đường strong reference từ root, nó vẫn được giữ sống.

### 14.1. Static collections

```java
import java.util.ArrayList;
import java.util.List;

class Cache {
    static final List<byte[]> ITEMS = new ArrayList<>();

    static void add() {
        ITEMS.add(new byte[1024]);
    }
}
```

Đây là class minh họa; khi class/static state còn sống, mỗi `byte[]` được thêm vào list sẽ có strong path qua `ITEMS` → list backing array → phần tử, cho tới khi ứng dụng loại bỏ reference hoặc class được unload phù hợp.

Dùng cache có **giới hạn số entry, TTL, eviction/size policy** và cách đóng tài nguyên liên quan khi thực tế cần cache.

### 14.2. ThreadLocal không được cleanup

Một `ThreadLocal` có thể làm dữ liệu sống lâu vì thread trong thread pool vẫn tồn tại. Dù key có weak-reference semantics ở một số cấu trúc HotSpot/JDK implementation, các **values** có thể còn được giữ qua thread-local map cho tới khi entries được dọn.

Quy tắc lập trình an toàn khi dùng thread pools:

```java
private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

static void process() {
    try {
        CONTEXT.set("request");
        // xử lý request ...
    } finally {
        CONTEXT.remove();
    }
}
```

Đây là **đoạn đặt trong một class**, không có main. Dòng `remove()` giúp tránh rò state qua thread tái sử dụng. Không nhầm `ThreadLocal` với “dữ liệu tự hủy khi method kết thúc”.

### 14.3. Listener, callbacks, executors và queues

- Event publisher có thể giữ listener instances bằng strong references.
- Scheduled tasks/futures có thể giữ closures/objects được capture.
- Blocking queue có thể giữ các jobs, payloads hoặc responses chưa được drain.
- Long-lived class loaders có thể giữ classes/metadata và chuỗi object graphs liên quan.
- JNI global references giữ object khỏi GC dù Java source không còn biến được nhìn thấy.

**Tối ưu vấn đề reachability là cắt/giới hạn đường giữ sống không cần thiết**, chứ không cố gọi `System.gc()` liên tục.

## 15. Dùng heap dump và GC-root paths để debug leak

Các heap analyzers (ví dụ Eclipse Memory Analyzer, VisualVM hoặc tooling thích hợp) có thể giúp:

1. Chụp heap dump tại thời điểm cần điều tra.
2. Xác định classes có retained heap lớn hoặc tăng bất thường.
3. Chọn một object/cụm object nghi ngờ.
4. Xem **Paths to GC Roots** hoặc retained/dominator tree.
5. Đánh giá cạnh nào là **strong references** và những loại reference nào cần loại khỏi đường giữ sống để thấy nguyên nhân.
6. Xác định field, array element, static cache, ThreadLocal, listener, JNI handle hoặc class loader gây giữ object.
7. Sửa vòng đời references và đo lại sau một chu kỳ tải có thể so sánh.

### Paths to GC Roots trả lời câu hỏi gì?

Giả sử công cụ tìm thấy:

```text
GC Root: live application thread
  → Thread.threadLocals
  → ThreadLocalMap.Entry.value
  → RequestContext
  → byte[] payload
```

Đây là **đường giữ sống minh họa**, không phải kết quả bắt buộc trên mọi JDK. Nếu request đã kết thúc nhưng `RequestContext` vẫn ở thread-local value của worker thread, thì GC **đúng khi giữ nó**, vì vẫn có đường strong reference từ root.

Một cách sửa có cơ sở là thiết kế lifecycle: `ThreadLocal.remove()` trong `finally`, giới hạn queues/cache, unregister listeners, release JNI handles, close resources. **Không tùy tiện xóa reference còn đang cần cho thread khác**, vì điều đó có thể tạo race hoặc làm ứng dụng sai ngữ nghĩa.

### Dominator/retained size không đồng nhất với kích thước shallow

Một object có thể nhỏ nhưng **retain** rất nhiều objects khi nó là đường root duy nhất giữ chúng sống. Ví dụ static `Map` object shallow size có thể nhỏ, nhưng keys/values/arrays giữ hàng trăm MB. Phân tích retained size hoặc dominator tree giúp tìm “ai đang giữ ai”, chứ không chỉ bảng classes có nhiều instances.

## 16. GC log và các thước đo không thể thay thế graph analysis

Để hiểu tần suất collection, pause time và memory pressure, có thể bật logging phù hợp cho **HotSpot JDK 17+**:

```bash
java -Xlog:gc*:info -version
```

Lệnh trên chạy JVM để in version và GC-related messages tùy thời điểm; nó **không** tự tạo workload đáng kể hay cho sẵn một heap dump. Với chương trình mô phỏng bên trên:

```bash
java -Xlog:gc*:info ReachabilityGraphDemo
```

Nếu output gồm GC logs, số dòng/timing phụ thuộc VM, heap size và tải. **Không có cam kết chắc chắn phải xảy ra GC cycle trong bài demo nhỏ**. Do đó chỉ hai nhóm `println` của chương trình (mục 10) có stdout dự kiến ổn định khi chạy không bật logging.

Một số chẩn đoán JDK phổ biến:

```bash
jcmd -l
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID GC.heap_dump heap.hprof
```

Trong các lệnh trên, **`PID` là số tiến trình thật, phải thay bằng PID phù hợp**. Việc lấy class histogram/heap dump có thể tốn bộ nhớ, dung lượng đĩa hoặc gây pause lớn; chỉ thực hiện ở môi trường được phép. Các commands và tác dụng thực tế cần đối chiếu `jcmd PID help` của JVM đang chạy.

**GC logs cho biết khi nào collector làm việc và thống kê bộ nhớ; heap dump/root paths giúp chỉ ra tại sao object còn reachable.** Chúng giải quyết những câu hỏi khác nhau.

## 17. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Biến gán `null` là object được free ngay.” | Chỉ mất một đường tham chiếu; còn các paths khác và GC chưa chắc đã chạy |
| “Hai objects trỏ lẫn nhau sẽ không bao giờ bị GC.” | Tracing GC có thể thu hồi chu trình **không reachable từ roots** |
| “GC chỉ đếm số reference tới object.” | Tracing collectors phân tích **reachability từ roots**, có xử lý special references |
| “Mọi local variable trong Java scope đều là GC root đến hết method.” | Liveness/JIT optimizations có thể rút ngắn thời gian VM cần giữ object sống |
| “Mọi loaded class có static fields đều tồn tại đến khi process tắt.” | Class unloading/class-loader lifecycle có thể làm runtime classes không còn sống |
| “`WeakReference` giữ object mạnh như field thông thường.” | Weak reference không ngăn clearing khi object chỉ còn weakly reachable |
| “`weak.get() == null` ngay sau khi `strong = null`.” | Không có bảo đảm timing GC; paths khác cũng có thể giữ referent |
| “`System.gc()` chắc chắn dọn mọi object đã chết ngay.” | Không có bảo đảm như vậy và runtime có thể bỏ qua explicit GC |
| “`ReferenceQueue.poll()` chắc chắn báo event ngay sau khi bỏ strong ref.” | Queue phụ thuộc reference processing/enqueue và timing runtime |
| “PhantomReference.get() trả object để phục hồi.” | Nó **luôn trả null** |
| “Concurrent GC chỉ quét graph một lần mà không cần theo dõi writes.” | Concurrent collectors cần barriers/invariants cho graph đang thay đổi |
| “Young GC bỏ qua mọi old-to-young refs.” | Remembered sets/card tables hỗ trợ xử lý cross-generation edges |
| “GC thu hồi object thì RSS phải giảm ngay.” | Heap committed/reserved và RSS khác, collector có thể giữ vùng trống để tái sử dụng |
| “Đối tượng reachable nhưng không còn giá trị nghiệp vụ là rác mà GC phải tự hiểu.” | Nếu còn strong path, GC phải giữ nó; đây là nguyên nhân Java memory leaks phổ biến |
| “Heap dump tự giải thích leak mà không cần xét roots.” | Cần xem retaining paths, dominators và object lifecycle |
| “Một class trống không thể làm object khác sống.” | Object/class/static references/runtime handles có thể tham gia root graph tùy lifecycle |

## 18. Bài tập và lời giải

### Bài 1 — Chu trình không có đường từ root

```text
ROOT → A       B ↔ C
```

**Hỏi:** Nếu không có edges nào khác, B và C còn strongly reachable từ root không?  
**Đáp án:** Không. Chúng tạo chu trình tự cô lập; tracing từ ROOT chỉ tìm thấy A.

### Bài 2 — Chu trình vẫn reachable

```text
ROOT → A → B → C → B
```

**Hỏi:** B/C có thể xem là rác chỉ vì chúng tạo vòng?  
**Đáp án:** Không. ROOT có strong path qua A tới B/C.

### Bài 3 — Một object, hai root paths

```text
ROOT1 → A → X
ROOT2 → B → X
```

**Hỏi:** Bỏ cạnh `A → X` đã đủ làm X unreachable?  
**Đáp án:** Chưa, vì còn `ROOT2 → B → X`.

### Bài 4 — Local variable và scope

**Hỏi:** Kết thúc một block source Java có đảm bảo GC lập tức reclaim object từng được biến local tham chiếu?  
**Đáp án:** Không. Cần xét all strong paths, liveness và lịch GC; ngược lại, có khi VM không cần giữ object đến tận cuối block nếu reference không còn được sử dụng.

### Bài 5 — `WeakReference`

**Hỏi:** `WeakReference<Object> w = new WeakReference<>(o);` nếu `o` còn một strong root path thì GC có được clear weak referent chỉ vì `w` là weak?  
**Đáp án:** Không. Object vẫn strongly reachable qua đường mạnh.

### Bài 6 — Một weak reference là đường duy nhất

**Hỏi:** Khi object chỉ còn weakly reachable và collector xử lý weak references, `w.get()` có thể thành gì?  
**Đáp án:** `null`, khi weak reference được cleared theo quy tắc. Thời điểm cụ thể không thể bảo đảm từ một phép gán null trong source.

### Bài 7 — Phantom get

**Hỏi:** `PhantomReference.get()` dùng để lấy lại object cho cleanup được không?  
**Đáp án:** Không; `get()` luôn là `null`. Cleanup nên dùng resource state khác mà không giữ referent mạnh trở lại.

### Bài 8 — Static cache leak

**Hỏi:** Vì sao `static List<Object>` có thể giữ một triệu objects sống dù ứng dụng không xử lý chúng nữa?  
**Đáp án:** Khi class/static cache còn sống, list giữ strong refs tới elements; collector không biết hết giá trị nghiệp vụ. Cần eviction/remove và lifecycle hợp lý.

### Bài 9 — ThreadLocal

**Hỏi:** Sau mỗi request, worker thread trong pool vẫn tồn tại. Vì sao request context có thể chưa được GC?  
**Đáp án:** ThreadLocal values có thể còn reachable qua runtime thread/local map. Dùng `remove()` trong `finally` khi hết scope nghiệp vụ.

### Bài 10 — Young GC

**Hỏi:** Một object old-generation tham chiếu object young-generation. Young GC có thể coi young object unreachable chỉ vì root scan không đi qua toàn bộ old heap?  
**Đáp án:** Không. Collector phải xử lý các cross-generation references thích hợp, ví dụ qua remembered sets/card metadata.

### Bài 11 — Đồng thời thay đổi đồ thị

**Hỏi:** Trong concurrent marking, mutator thay references giữa lúc collector quét. Tại sao cần barriers?  
**Đáp án:** Để duy trì marking invariants và tránh bỏ sót objects cần sống khi graph thay đổi; cách dùng SATB/incremental-update tùy collector.

### Bài 12 — Heap size

**Hỏi:** Sau GC, 50 MB objects không còn reachable đã được reclaim nhưng JVM process RSS không giảm. Có chắc GC lỗi?  
**Đáp án:** Không. JVM có thể giữ committed heap/native pages để tái sử dụng; RSS và live-set không đồng nhất.

### Bài 13 — Identity hay equality?

**Hỏi:** Hai `Node` khác instances nhưng `equals()` trả `true`, collector có được coi là cùng một object?  
**Đáp án:** Không. GC phải quản lý **object identity**; phép so bằng application-defined `equals()` không biến hai allocations thành một.

### Bài 14 — Một root path thay đổi

**Hỏi:** Một listener được remove khỏi event bus nhưng vẫn còn trong scheduled task queue. Có eligible ngay không?  
**Đáp án:** Chưa đủ bằng chứng. Task queue có thể giữ strong path; cần xem tất cả root paths.

### Bài 15 — Finalizer và reachability

**Hỏi:** Có nên cài `finalize()` để bảo đảm native handle được đóng ngay khi object unreachable?  
**Đáp án:** Không. Finalization legacy không bảo đảm timing/hoàn tất và có thể gây resurrection; ưu tiên `AutoCloseable`/try-with-resources.

### Bài 16 — `reachabilityFence`

**Hỏi:** `Reference.reachabilityFence(obj)` có bắt GC dọn `obj` ngay sau lệnh không?  
**Đáp án:** Không. Nó giúp duy trì reachability tới điểm cần thiết; thời điểm reclaim vẫn phụ thuộc GC/runtime.

## 19. Checklist giải thích “vì sao object chưa bị GC”

1. Object có đang nằm trong static cache, collection, map hoặc backing array không?
2. Có Java thread còn giữ reference live hoặc `ThreadLocal` value không?
3. Có scheduled task, listener, callback hoặc future đang giữ closure/object không?
4. Có JNI global handle hoặc VM-internal handle liên quan không?
5. Có weak/soft/phantom reference nào khiến việc diễn giải paths cần đặc biệt không?
6. Có object nào khác trong graph còn strong edge tới nó không?
7. Có class loader/class metadata lifecycle khiến static state còn sống không?
8. Object chỉ **eligible** hay collector đã chạy cycle xử lý vùng đó?
9. Heap dump/histogram đang cho **shallow** hay **retained** size?
10. Công cụ đã tìm Paths to GC Roots, lọc weak/soft/phantom refs thích hợp chưa?
11. Collector đang dùng generational/concurrent scheme nào và logs cho thấy những pha nào?
12. Mục tiêu là sửa **unintended strong reachability** hay chỉ giảm committed heap/RSS?

## 20. Kết luận và tài liệu đối chiếu

Để hiểu vì sao Java GC giữ một object, hãy bắt đầu từ câu hỏi **“có đường tham chiếu giữ sống từ GC roots tới object này không?”**. Tracing collector đánh dấu object theo đồ thị thay vì dựa trên số references hoặc tuổi của biến Java. Chu trình không có root path có thể được thu hồi. Ngược lại, static caches, thread locals, JNI handles và listeners có thể vô tình tạo root paths lâu dài, khiến object vẫn sống mặc dù ứng dụng đã “xử lý xong”.

Đối với concurrent và generational collectors, mô hình cơ bản vẫn là reachability nhưng việc quét được tối ưu bằng **marking invariants, barriers, cards và remembered sets**. Với `SoftReference`, `WeakReference`, `PhantomReference` và cleanup, **cạnh tham chiếu không có cùng ngữ nghĩa** như strong field. “Không còn reachable” cũng khác “bộ nhớ đã được thu hồi ngay” và càng khác “RSS phải giảm tức thì”.

**Tài liệu chuẩn:**

- Java SE 17 — **`java.lang.ref` package**, mô tả các mức reachability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- Java SE 17 — **`Reference`** và `Reference.reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- Java SE 17 — **`WeakReference`**, **`SoftReference`**, **`PhantomReference`**, **`ReferenceQueue`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- OpenJDK **JEP 421 — Deprecate Finalization for Removal**: https://openjdk.org/jeps/421
- Oracle JDK 17 — **Garbage Collection Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17 — **jcmd utility**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Ghi nhớ:** GC không cần “xóa tất cả reference trong mọi object” trước khi thu hồi một chu trình. Nó cần xác định **tập object phải được giữ sống bắt đầu từ GC roots**, xử lý các loại reference đặc biệt và dùng thuật toán collector phù hợp để thu hồi vùng bộ nhớ có thể tái sử dụng. Khi debug heap, **Paths to GC Roots** là chiếc cầu nối giữa lý thuyết đồ thị và nguyên nhân object còn sống trong ứng dụng thật.