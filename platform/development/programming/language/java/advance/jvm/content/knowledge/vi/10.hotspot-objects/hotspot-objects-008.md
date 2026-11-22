# Tuổi thọ đối tượng, khả năng truy cập và giới hạn suy luận từ phạm vi biến

## 1. Vấn đề cốt lõi: biến hết phạm vi không phải lệnh hủy đối tượng

Xét đoạn Java:

```java
static void example() {
    Object item = new Object();
    System.out.println(item.getClass().getSimpleName());
} // item ra khỏi phạm vi
```

Dấu `}` cho biết **biến cục bộ `item` không còn sử dụng được bằng tên đó ở bên ngoài block**. Nó **không** phải câu lệnh “giải phóng ngay object”, không hứa garbage collector (GC) sẽ chạy đúng thời điểm này và không hứa vùng heap được trả về hệ điều hành sau khi method return.

Trong Java/JVM, điều cần phân biệt là:

1. **Scope của biến (lexical scope):** vùng mã nguồn nơi tên biến có thể được dùng.
2. **Lifetime của biến/slot:** cách compiler và JVM duy trì giá trị trong local variables, fields hoặc registers; không đồng nhất với dấu ngoặc source.
3. **Reachability của object:** còn cách nào để chương trình đang chạy tiếp tục truy cập object thông qua những reference hợp lệ hay không.
4. **Eligibility for reclamation:** object có thể được GC thu hồi theo các quy tắc quản lý reference và GC hay chưa.
5. **Thời điểm GC thực hiện thu hồi:** phụ thuộc runtime, chính sách GC, tài nguyên và hoạt động chương trình.
6. **Vòng đời resource ngoài heap:** file descriptor, socket, database connection, native handle… không tự được đóng đúng thời điểm chỉ vì Java object chứa reference tới resource không còn cần thiết.

**Kết luận:** `Object` có thể vẫn **reachable** sau khi biến local tạo nó đã ra khỏi scope nếu còn reference từ field, collection, callback hoặc thread. Và ngược lại, một object có thể được compiler/JIT coi là **không còn cần thiết** trước khi khối nguồn kết thúc nếu về sau không có hành vi quan sát được cần đến nó.

Đây là nền tảng để phân tích memory leak, class loader retention, vòng đời cache, `ThreadLocal`, `WeakReference`, `Cleaner` và lý do cần `Reference.reachabilityFence`.

## 2. JVM Specification bảo đảm điều gì?

Theo **JVMS `2.5.3 — Heap**, heap là vùng dữ liệu runtime dùng cho class instances và arrays. Quản lý/reclaim heap objects được thực hiện bằng một **automatic storage management system** thường gọi là garbage collector.

Đặc tả không bắt buộc:

- Một GC cụ thể như G1, ZGC hoặc Shenandoah.
- GC phải chạy sau khi rời khỏi scope.
- Một object phải tồn tại trong đúng một thế hệ heap.
- Mỗi lệnh `new` luôn tương ứng với một allocation vật lý phải quan sát được trong mọi tối ưu hóa.
- Thời điểm reclaimed memory sẽ được trả về OS.
- Java cung cấp toán tử `free(object)` để ứng dụng tự giải phóng heap object.

Điều mà ứng dụng có thể dựa vào là **ngữ nghĩa của chương trình** và **các guarantee trong Java/JVM APIs**, không phải lịch GC “dự kiến”.

### 2.1. Không nhầm lifetime với object identity

```java
Object a = new Object();
Object b = a;
a = null;
System.out.println(b != null); // true
```

Biến `a` không còn tham chiếu tới object, nhưng `b` vẫn giữ cùng object. Object không trở thành unreachable chỉ vì một trong nhiều biến đổi sang `null`.

Tương tự:

```java
Object x = new Object();
Object y = new Object();
x = y;
```

Sau phép gán `x = y`, object từng được `x` trỏ tới **có thể** trở thành không còn strong-reachable nếu không có reference khác. Object `y` trỏ tới vẫn có hai reference từ `x` và `y` trong ví dụ khái niệm. Việc nào được reclaim và khi nào phụ thuộc reachability và runtime, không phải “lúc phép gán xảy ra phải free ngay”.

### 2.2. Java không dùng reference counting thuần túy làm hợp đồng GC

Một vòng tham chiếu:

```java
class Node {
    Node next;
}

Node left = new Node();
Node right = new Node();
left.next = right;
right.next = left;
left = null;
right = null;
```

có thể trở thành **không reachable** từ mọi nguồn còn sống, dù hai `Node` còn trỏ lẫn nhau. GC có thể thu hồi toàn bộ vòng nếu không còn nguồn reference giữ nó và các điều kiện liên quan được thỏa.

**Số lượng reference giữa các object không đủ để quyết định object có “sống” hay không.** Quan trọng là khả năng tiếp cận từ những nguồn/root hợp lệ của runtime.

## 3. Lexical scope, local variables, frame và object không phải một thứ

Trong source code, block khai báo xác định tên biến được dùng ở đâu:

```java
void method() {
    {
        Object local = new Object();
        // Có thể viết local tại đây.
    }
    // Không thể viết local tại đây.
}
```

Sau block, viết `local` sẽ lỗi compile-time. Nhưng JVM bytecode không vận hành dựa trên một “dấu } sẽ giải phóng heap object”. Bytecode của phương thức có **local variable slots** và **operand stack** trong frame; compiler có thể sử dụng lại slot sau khi một giá trị không còn cần thiết.

Một `LocalVariableTable` (nếu được compiler xuất dưới dạng debug metadata) có thể mô tả phạm vi tên/offset để debugger hiển thị. Nó **không phải lệnh GC**; việc có hay không có bảng debug đó không quyết định object được reclaim.

### 3.1. Method return không đủ để kết luận object chết

```java
static Object create() {
    Object local = new Object();
    return local;
}

Object result = create();
```

Khi `create` return, local variable `local` của callee không còn trong frame active. Nhưng **object vẫn còn có thể được truy cập từ `result` của caller**. Nếu coi “method kết thúc tức là object chết”, ta đã nhầm lifetime của **frame/local name** với reachability của **heap object**.

### 3.2. Biến vẫn nằm trong scope nhưng object có thể không còn cần thiết

```java
static void process() {
    Object buffer = new Object();
    System.out.println(buffer.getClass());
    doIndependentWork();
    // block chưa đóng nhưng buffer không còn được dùng
}
```

Đoạn này **chỉ minh họa**, `doIndependentWork()` phải được định nghĩa trong một chương trình thực tế. Trên đường thực thi nhất định, compiler/JIT có thể phát hiện không còn thao tác nào cần `buffer` và giảm khoảng thời gian object được giữ strong-reachable.

JLS `12.6.1 nói rõ tối ưu hóa có thể rút ngắn thời gian reachability so với cách đọc ngây thơ “local còn trong phạm vi nên object sống tới hết block”. Một runtime không bắt buộc giữ object sống cho đến khi tên local không còn hợp lệ về mặt cú pháp.

### 3.3. Local variable slot còn giá trị cũ chưa chắc là strong GC root

JVM implementation/JIT có thể xác định những locals/registers đang **live** tại safepoint khác với việc một debugger có thể thấy một bit pattern cũ trong slot. Không được khẳng định “slot vẫn chứa reference cũ thì object chắc chắn được giữ sống” cho mọi tối ưu hóa của HotSpot.

Ngược lại, nếu object vẫn có reference từ field của object khác đang sống, local hết scope cũng không đủ để làm nó unreachable.

## 4. Khái niệm reachability: đi từ đâu tới object?

Để hiểu GC, hãy vẽ **đồ thị các object và reference**:

```text
Live roots / chương trình còn sống
             |
       +-----+------+
       |            |
  Static registry   Frame đang chạy
       |            |
       v            v
     List A        Service B
       |            |
       v            v
   Payload X      Request Y
       |
       v
   Payload Z
```

Nếu một object có thể được truy cập từ một nguồn đang sống thông qua chuỗi **strong references** hợp lệ, nó **strongly reachable**. Khi không còn đường strong-reference nào, nó có thể thuộc một mức reachability yếu hơn nếu được tham chiếu qua `SoftReference`, `WeakReference` hoặc `PhantomReference`, hoặc trở thành không reachable.

Đồ thị GC chính xác phụ thuộc implementation, các roots VM cần xét và các quy tắc reference-processing. Sơ đồ phục vụ phân tích, **không có nghĩa JLS liệt kê một bộ “GC roots” có cấu trúc dữ liệu cố định trên mọi JVM**.

### 4.1. Các nguồn thường có thể giữ object còn sống

Trong HotSpot, khi phân tích heap, những đường tham chiếu cần xem gồm:

- **Reference sống từ frame/thread:** tham số, local/register mà computation còn cần.
- **Static fields:** static reference của class đang tồn tại, theo class-loader identity.
- **Các object được root giữ trực tiếp/gián tiếp:** registries, singleton, caches, collections.
- **Thread và thread-associated state:** active tasks, thread locals, thread context class loaders, callback references.
- **JNI/native handles và các VM-managed references** trong những ngữ cảnh phù hợp.
- **Class loaders/class metadata và liên kết liên quan:** nhất là plugin/application servers.

Danh sách là **gợi ý chẩn đoán**, không phải định nghĩa độc quyền của mọi bộ GC. Tùy runtime, object graphs và root categories hiển thị trong heap dump có thể khác nhau.

### 4.2. “Không còn đường từ một biến local” chưa đủ

```java
static final java.util.List<Object> ITEMS =
        new java.util.ArrayList<>();

static void add() {
    Object local = new Object();
    ITEMS.add(local);
}
```

Đoạn code minh họa này yêu cầu đặt trong một class. Sau `add()` return, reference local mất đi, nhưng **ITEMS vẫn chứa object**. Nếu registry tồn tại lâu dài, object có thể tồn tại lâu dài.

Muốn bỏ một cạnh trong đồ thị, cần xóa khỏi collection phù hợp:

```java
ITEMS.clear();
```

Nhưng **clear không có nghĩa object phải được GC ngay**, vì object có thể còn reference khác và GC chưa cần chạy.

### 4.3. Closures và lambdas có thể giữ captures

```java
static Runnable task() {
    Object captured = new Object();
    return () -> System.out.println(captured.toString());
}
```

Sau `task()` return, lambda vẫn có thể giữ reference tới `captured`. Nó được sống tiếp cùng object callback nếu runtime cần giữ giá trị capture để bảo toàn hành vi. Nơi callback được đăng ký (executor, listener registry, timer) có thể kéo dài lifetime của object được capture.

Vì vậy **“biến local đã ra khỏi scope”** là một tín hiệu yếu trong điều tra memory retention.

## 5. Các mức reachability của `java.lang.ref`

Java SE cung cấp ba họ **reference objects đặc biệt**: soft, weak, phantom. Chúng cho phép tương tác có kiểm soát với GC. Java SE 17 `java.lang.ref` mô tả các mức reachability theo thứ tự từ mạnh tới yếu:

| Mức | Ý nghĩa khái quát | Tác động thực tế |
| --- | --- | --- |
| **Strongly reachable** | Có thể được truy cập mà không đi qua reference objects đặc biệt | Thông thường GC không thu hồi object khi vẫn cần theo strong path |
| **Softly reachable** | Không strong-reachable, nhưng có đường thông qua `SoftReference` | Collector có thể clear soft references để đáp ứng nhu cầu bộ nhớ |
| **Weakly reachable** | Không strong/soft, nhưng có đường qua `WeakReference` | Weak refs được xử lý/clear khi collector xác định referent weakly reachable |
| **Phantom reachable** | Không còn các mức mạnh hơn và đáp ứng quy tắc phantom reference | Được dùng với reference queue/cleanup, không cung cấp lại referent qua `get()` |
| **Unreachable** | Không còn đường reachability theo các mức trên | Có thể đủ điều kiện reclaim theo chính sách/chu kỳ GC |

**Cẩn thận về finalization:** những đặc tả lịch sử có điều kiện liên quan finalization khi giải thích phantom/unreachable. Finalization đã bị deprecated for removal và Java SE 26 cho phép implementations tắt nó; ứng dụng mới không nên thiết kế cleanup dựa trên finalizer.

### 5.1. Strong reference

```java
Object strong = new Object();
```

Khi `strong` là một reference còn cần thiết để tiếp tục computation, object được giữ reachable theo nghĩa thích hợp. Việc tên `strong` nằm trong một block **không tự quy định** nó phải tồn tại như GC root đến đúng cuối block; tình trạng live reference phụ thuộc đường thực thi và tối ưu hóa hợp lệ.

### 5.2. `SoftReference` không cho kết quả lúc nào bị xóa một cách cố định

```java
java.lang.ref.SoftReference<byte[]> soft =
        new java.lang.ref.SoftReference<>(new byte[1024]);
byte[] data = soft.get();
```

Đây là đoạn minh họa, không là chương trình độc lập. `soft.get()` có thể trả array hoặc `null` nếu soft reference đã bị clear theo chính sách GC. Không có hợp đồng Java rằng “soft reference chắc chắn sống tới khi heap free < 10%” hoặc “GC phải xóa tất cả soft refs ở mỗi collection”.

Soft references dùng cho **memory-sensitive caching**, nhưng cần kiểm thử thực tế và có fallback tái tạo dữ liệu. Đừng dựa vào soft refs làm nơi lưu thông tin bắt buộc không thể tạo lại.

### 5.3. `WeakReference` không tự giữ referent sống

```java
Object obj = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(obj);
```

Nếu chương trình còn giữ `obj` một cách cần thiết, referent có strong path. Khi strong path không còn, `weak` không tự bảo đảm referent sống mãi.

Quan trọng:

- `weak` chính nó là **reference object** có thể còn strongly reachable.
- `weak.get()` lấy referent nếu chưa bị clear; nếu đã clear thì trả `null`.
- **Thời điểm GC chạy, clear hoặc enqueue không được xác định bằng dấu `}` của source**.
- Không sử dụng `System.gc()` rồi assert “`weak.get() == null` phải đúng ngay” trong unit tests portable.

### 5.4. `PhantomReference` phục vụ cleanup notification, không đọc lại object

`PhantomReference<T>` được dùng với `ReferenceQueue<T>` và những cơ chế xử lý hậu reachability. `get()` của `PhantomReference` **luôn trả `null`**; không phải một cách lấy lại object sắp bị thu hồi.

Đừng dùng phantom reference như một “weak reference mạnh hơn một chút có thể dereference”. Nó được thiết kế cho notification/cleanup coordination.

## 6. `ReferenceQueue` giúp biết điều gì?

`ReferenceQueue` cho phép chương trình nhận những **reference objects** khi chúng được enqueue theo quy tắc xử lý reference của GC:

```java
java.lang.ref.ReferenceQueue<Object> queue =
        new java.lang.ref.ReferenceQueue<>();
Object target = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(target, queue);
```

Đây là đoạn minh họa để đặt trong method/class thích hợp. Khi GC xác định referent ở trạng thái phù hợp, weak reference có thể được clear và enqueue. Sau đó `queue.poll()` có thể trả một reference đang chờ, hoặc `null` nếu chưa có.

**Không suy luận `queue.poll() == null` nghĩa là target chắc chắn còn strongly reachable**: có thể GC chưa thực hiện reference processing, sự kiện enqueue chưa có, hoặc tình huống runtime khác. Thời điểm quan sát được không là đồng hồ đo lifetime chuẩn.

### 6.1. Vì sao không nên giữ strong referent trong cleanup registry?

Nếu bạn vừa tạo weak reference tới object vừa giữ **một strong reference khác tới đúng object đó** trong registry “để cleanup”, object vẫn có thể tồn tại mãi. Weak reference không vô hiệu hóa các strong paths khác.

Ví dụ nguy hiểm về ý tưởng:

```text
Registry
  +-- WeakReference(target)
  +-- StrongReference(target)    <-- vẫn giữ object sống
```

Khi debug weak-cache không giải phóng, hãy tìm những cạnh mạnh **ngoài chính WeakReference**.

## 7. Scope của một local và khoảng sống thực sự (*liveness*)

Một biến trong source có thể còn **đang in scope** nhưng compiler biết giá trị cuối cùng của nó đã được dùng:

```java
static void work() {
    byte[] temporary = new byte[1_000_000];
    use(temporary);
    expensiveCalculation();
}
```

Đây là minh họa, `use` và `expensiveCalculation` chưa được định nghĩa. Sau lần cuối cần `temporary`, compiler/JIT có thể giảm live range của reference. Object có thể được coi là không còn strongly reachable trước khi `work` kết thúc, miễn phép biến đổi hợp lệ về ngữ nghĩa.

Ngược lại, nếu `use` đưa `temporary` vào một shared registry, array vẫn có đường strong reference qua registry sau khi method return.

### 7.1. “Biến đã ra khỏi scope thì object eligible for GC” chỉ đúng có điều kiện

Đặt:

```java
static java.util.List<byte[]> storage = new java.util.ArrayList<>();

static void allocate() {
    byte[] buffer = new byte[1024];
    storage.add(buffer);
}
```

Tên `buffer` hết scope nhưng array **vẫn reachable từ `storage`** nếu registry còn sống và chưa bị gỡ bỏ.

Một cách giải thích chính xác phải là:

> Sau khi biến cục bộ không còn giữ một reference live, object **có thể** trở thành không còn strong-reachable, **nếu không còn strong paths nào khác**.

### 7.2. `local = null` có bắt buộc giảm memory không?

Không. Viết:

```java
Object item = new Object();
use(item);
item = null;
```

là một cách chủ động bỏ reference của local, nhưng:

- Compiler có thể đã biết reference hết live trước câu `item = null`.
- Object có thể vẫn được giữ bởi fields/caches/closures.
- Garbage collector có thể chưa chạy.
- Heap used sau đó có thể chưa giảm ngay, và heap committed có thể vẫn giữ để tái sử dụng.

Trong một số phương thức rất dài nơi local slot tồn tại lâu và compiler/interpreter giữ reference lâu hơn cần thiết, bỏ reference có thể có tác dụng ở một runtime cụ thể. Nhưng **đây không phải kỹ thuật bắt buộc hoặc bảo đảm portable**, càng không thay việc thiết kế vòng đời references đúng.

### 7.3. Debugger và tối ưu hóa có thể làm tình hình khó quan sát

Ở chế độ JIT, một biến mà source cho thấy còn trong scope có thể bị tối ưu hoặc không sẵn sàng để debugger đọc. Ngược lại, một giá trị có thể nằm trong local slot ở interpreter dù source name đã hết scope.

**Đừng suy đoán reachability chỉ từ ảnh chụp LocalVariableTable, stack trace hay vị trí dấu ngoặc nhọn.** Khi điều tra leak, cần heap dump, GC roots/path-to-root và cách objects được giữ thực sự.

## 8. `Reference.reachabilityFence`: yêu cầu rõ một điểm sử dụng cuối

`Reference.reachabilityFence(Object)` được thêm vào Java 9. Nó thiết lập một **điểm mà object phải được xem là strongly reachable ít nhất cho tới sau invocation**, theo hợp đồng API.

Ví dụ khái niệm:

```java
import java.lang.ref.Reference;

static void handle(NativeHandle handle) {
    long address = handle.address();
    nativeWork(address);
    Reference.reachabilityFence(handle);
}
```

Đây là **mã minh họa**, không là chương trình độc lập: `NativeHandle` và `nativeWork` cần định nghĩa phù hợp. Trong code kiểu này, native call có thể chỉ nhận một địa chỉ số `long` nên JVM không tự biết cần giữ Java wrapper `handle` sống qua toàn bộ thao tác chỉ từ việc nhìn giá trị `long`.

`Reference.reachabilityFence(handle)` biểu thị rằng wrapper object phải còn strongly reachable ít nhất tới sau lời gọi. Nó rất hữu ích ở đoạn code tích hợp native resources hoặc cleaning mechanisms khi object wrapper kiểm soát lifetime của native handle.

### 8.1. `reachabilityFence` không phải `free`

Những điều `reachabilityFence` **không làm**:

- Không ép garbage collector chạy.
- Không “pin” object ở một địa chỉ heap cố định.
- Không gia hạn lifetime vô hạn.
- Không bảo đảm tài nguyên native được đóng.
- Không tạo reference vĩnh viễn sau khi method return.

Nó ràng buộc compiler/runtime về **reachability cho đến một điểm chương trình**, không phải một API điều khiển GC schedule.

### 8.2. Đặt fence đúng vị trí

Nếu công việc với resource hoàn tất ở cuối block, fence nên xuất hiện **sau lần cuối công việc có thể cần resource**:

```text
sử dụng resource / gọi native
            |
            v
Reference.reachabilityFence(owner)
            |
            v
không cần giữ owner vì công việc ấy nữa
```

Đừng đặt fence ngay đầu method rồi kỳ vọng nó giữ object sống xuyên qua đoạn thao tác về sau. Fence cũng **không thay thế synchronization, ownership protocol hoặc explicit close** khi native resource được chia sẻ nhiều thread.

## 9. Vòng đời Java object và vòng đời external resource không đồng nhất

Tạo một Java object có thể đồng thời mở file/socket/native allocation:

```java
java.io.InputStream in =
        java.nio.file.Files.newInputStream(path);
```

Đây là đoạn minh họa, `path` phải được khai báo. Java reference tới stream là object ở heap, nhưng file descriptor/native handle liên quan có **vòng đời tài nguyên ngoài heap**.

Nếu biến `in` ra khỏi scope mà không đóng, không có bảo đảm hệ điều hành sẽ nhận lại file descriptor ngay. GC có thể không chạy kịp, cleaner/finalization (nếu có) không phải một cơ chế deterministic cleanup cho tài nguyên quan trọng.

### 9.1. `try-with-resources` là lựa chọn chính cho resource có thể đóng

```java
try (java.io.InputStream in =
         java.nio.file.Files.newInputStream(path)) {
    // Xử lý dữ liệu từ stream.
}
```

Compiler sắp xếp gọi `close()` khi rời try-with-resources theo quy tắc của Java, kể cả khi phần thân kết thúc bằng exception (và có cơ chế suppressed exceptions khi phù hợp).

Điều này **khác với** “object được GC”: resource được đóng **chủ động theo luồng điều khiển**, không đợi object unreachable.

### 9.2. `AutoCloseable` không có nghĩa heap object tự bị hủy

Một đối tượng `AutoCloseable` sau khi `close()` vẫn có thể còn reachable và vẫn có thể được truy cập (tùy API). `close` quản lý **resource lifecycle**, không phải “free Java object memory”.

Ngược lại, object có thể không còn reachable trước khi `close` được gọi nếu code dùng sai pattern. Cần thiết kế ownership rõ ràng.

## 10. `Cleaner` và `PhantomReference`: safety net, không thay explicit close

Java `Cleaner` quản lý cleaning actions gắn với reachability của object được đăng ký. Nó được dùng để hỗ trợ giải phóng resource khi caller quên close, nhưng **không bảo đảm thời điểm hành động cleanup sẽ diễn ra** trước khi process kết thúc hoặc trước một deadline nghiệp vụ.

### 10.1. Pattern đúng: action không giữ referent

Mẫu minh họa:

```java
import java.lang.ref.Cleaner;

final class ManagedHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private boolean cleaned;

        @Override
        public synchronized void run() {
            if (cleaned) return;
            cleaned = true;
            // Giải phóng native resource do State quản lý.
        }
    }

    private final State state = new State();
    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

    @Override
    public void close() {
        cleanable.clean(); // explicit cleanup, idempotent theo state
    }
}
```

Đây là **class minh họa**, không mở resource thật. Quan trọng nhất: `State` là static nested class, không vô tình capture `ManagedHandle.this`. Nếu cleaning action giữ strong reference tới referent, nó có thể làm referent **không bao giờ trở thành phantom reachable**, khiến cleanup không được kích hoạt bởi GC.

### 10.2. Điều `Cleaner` không cam kết

- Không cam kết callback chạy ngay sau dấu `}`.
- Không cam kết callback chạy trong một thời hạn cố định.
- Không cam kết callback chạy trước khi process bị kill.
- Không thay cơ chế quản lý transaction, lock hoặc filesystem sync.
- Không phù hợp để thực thi nghiệp vụ quan trọng mà thiếu cleanup sẽ gây mất tính đúng đắn.

Thiết kế nên đặt **`close()` làm đường chính**; Cleaner chỉ là lớp bảo vệ phụ khi phù hợp.

### 10.3. Không dùng `finalize` cho code mới

`Object.finalize()` đã bị deprecated for removal từ JDK 18 và JEP 421 mô tả lộ trình loại bỏ finalization. Java SE 26 cho phép implementations tắt finalization, nên không nên xây code mới dựa vào việc finalizer sẽ được chạy.

Những hạn chế của finalization gồm:

- Thời điểm và thread thực hiện không xác định.
- Cleanup có thể bị trì hoãn lâu hoặc không xảy ra trước khi JVM kết thúc.
- Code finalizer có thể gây vấn đề về concurrency/security.
- Có thể tạo hiện tượng resurrection hoặc giữ object lâu hơn dự kiến.
- Đường lỗi và phụ thuộc giữa finalizers khó kiểm soát.

Thay thế ưu tiên: **`AutoCloseable` + try-with-resources**; với trường hợp cần non-deterministic fallback thì `Cleaner` hoặc `PhantomReference` theo hướng dẫn API chính thức.

## 11. Ví dụ Java 17+ độc lập: scope kết thúc nhưng object vẫn còn dùng được

Tạo tệp **`ObjectReachabilityDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

public final class ObjectReachabilityDemo {
    private static final List<Object> REGISTRY = new ArrayList<>();

    static final class Ticket {
        final String name;
        Ticket(String name) { this.name = name; }
    }

    static Ticket makeTicket() {
        Ticket local = new Ticket("returned");
        return local;
    }

    static void saveFromBlock() {
        {
            Ticket local = new Ticket("stored");
            REGISTRY.add(local);
        }
    }

    static Runnable makeCallback() {
        Ticket captured = new Ticket("callback");
        return () -> System.out.println("captured: " + captured.name);
    }

    static final class Resource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) throw new IllegalStateException("closed");
            System.out.println("resource used");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("resource closed");
        }
    }

    public static void main(String[] args) {
        Ticket returned = makeTicket();
        System.out.println("returned local survives: " + returned.name);

        saveFromBlock();
        System.out.println("stored outside block: "
                + ((Ticket) REGISTRY.get(0)).name);

        Runnable callback = makeCallback();
        callback.run();

        try (Resource resource = new Resource()) {
            resource.use();
        }

        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);
        System.out.println("weak while strongly reachable: "
                + (weak.get() != null));
        Reference.reachabilityFence(strong);

        REGISTRY.clear();
        System.out.println("registry size after clear: " + REGISTRY.size());
        System.out.println("collection time: not guaranteed");
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac --release 17 ObjectReachabilityDemo.java
java ObjectReachabilityDemo
```

**Stdout chính xác:**

```text
returned local survives: returned
stored outside block: stored
captured: callback
resource used
resource closed
weak while strongly reachable: true
registry size after clear: 0
collection time: not guaranteed
```

Mã này được thiết kế **không phụ thuộc thời điểm GC**. Nó không assert rằng weak reference phải trở thành null sau `System.gc()` hay object đã bị reclaim ngay sau `REGISTRY.clear()`.

### 11.1. `returned local survives: returned`

Trong `makeTicket()`, local `local` tồn tại trong một method frame và trả reference cho caller. Sau khi frame kết thúc, `returned` của caller vẫn trỏ tới cùng `Ticket`. Scope của biến `local` kết thúc **không hủy Ticket**.

### 11.2. `stored outside block: stored`

`saveFromBlock()` đặt Ticket vào `REGISTRY`, là static collection. Dù `local` không còn scope, registry vẫn có reference. Lúc `main` đọc `REGISTRY.get(0)`, object còn truy cập được.

Đây là ví dụ nhỏ của đường giữ object gây memory retention khi cache/listeners/registries lưu dữ liệu lâu hơn dự kiến.

### 11.3. `captured: callback`

`makeCallback()` trả lambda sử dụng `captured`. Callable object giữ dữ liệu cần thiết để thực hiện callback sau khi method đã return. Nếu callback còn sống thì object được capture có thể còn sống.

Khi đăng ký callbacks vào một event bus hoặc scheduler, hãy cân nhắc thời điểm **unsubscribe/cancel**, vì nếu registry giữ callback lâu dài thì các objects mà callback capture cũng có thể bị giữ lâu dài.

### 11.4. `resource used`, `resource closed`

Resource được mở theo ý tưởng, sử dụng trong try-with-resources, rồi `close()` được gọi có thể quan sát bằng dòng stdout. Đây là ví dụ về **deterministic release** của resource lifecycle; không phải sự kiện Java heap GC.

### 11.5. `weak while strongly reachable: true`

Trong vùng code có `strong` và lệnh `Reference.reachabilityFence(strong)` phía sau, object phải còn strongly reachable trong đoạn quan sát tương ứng. `weak.get()` trả referent chưa bị clear, nên dòng này là true.

Lưu ý `WeakReference` **không** tự khiến object tồn tại lâu hơn sau khi không còn strong path. Code không cố đo xem lúc nào GC sẽ clear weak reference.

### 11.6. `registry size after clear: 0`

`REGISTRY.clear()` làm danh sách không còn phần tử. Đây là điều có thể xác định bằng Java semantics. Nó **không chứng minh tất cả các Ticket objects đã bị reclaim**, vì object có thể được giữ ở nơi khác, và GC có thể chưa chạy.

## 12. Những minh họa không nên biến thành unit test có stdout cố định

Mô hình thử nhanh:

```java
Object o = new Object();
WeakReference<Object> ref = new WeakReference<>(o);
o = null;
System.gc();
System.out.println(ref.get() == null);
```

**Đây là ví dụ test không đáng tin, không phải bài thực hành chuẩn.** Dòng cuối có thể in true hoặc false tùy JIT, GC, heap pressure, timing và reachability. Không có đặc tả Java nói `System.gc()` buộc toàn bộ weak references được xử lý ngay trước dòng kế tiếp.

Một ví dụ sai khác:

```java
void test() {
    byte[] block = new byte[10_000_000];
} // Kết luận: heap used phải giảm đúng 10MB ngay đây.
```

Đây là lập luận **không hợp lệ**; collector có thể chưa reclaim, mức heap used/committed có độ nhiễu, object có overhead và runtime có thể tối ưu.

### 12.1. `System.gc()` là yêu cầu/hint không phải lịch bắt buộc

Tài liệu `System.gc()` mô tả việc **gợi ý** VM dành nỗ lực cho việc tái chế objects không còn dùng. VM có thể giới hạn/không thực hiện theo yêu cầu trong các cấu hình thích hợp; hiệu quả phụ thuộc collector/JVM.

Ngay cả khi GC chạy, điều đó không phải bằng chứng tất cả resources đã được đóng hay memory đã được trả cho OS.

### 12.2. Không dùng `Thread.sleep` để “chờ GC chắc chắn”

```java
System.gc();
Thread.sleep(1000);
// Không có guarantee object đã bị reclaim.
```

Một giây chỉ là thời gian chờ của thread. Nó không tạo guarantee về thời điểm collect, enqueue weak reference hoặc run Cleaner. Unit tests cần dựa trên **hành vi đã được đặc tả**, không phải timing hên xui.

## 13. ThreadLocal và thread pool: scope ngắn, retention dài

`ThreadLocal<T>` giữ dữ liệu gắn với **một thread** thay vì theo lexical scope của method gọi `set()`. Trong môi trường thread pool, các worker threads thường sống qua nhiều requests.

Ví dụ minh họa:

```java
private static final ThreadLocal<byte[]> BUFFER =
        new ThreadLocal<>();

static void handleRequest() {
    BUFFER.set(new byte[1024 * 1024]);
    try {
        // Xử lý request dùng BUFFER.get() khi cần.
    } finally {
        BUFFER.remove();
    }
}
```

Đoạn code **không độc lập**; cần đặt trong một class và có lời gọi thích hợp. Điểm học tập:

- Biến local trong `handleRequest()` biến mất sau return **không đảm bảo ThreadLocal value được xóa**.
- Thread pool worker tiếp tục sống có thể giữ entry/value giữa các requests.
- `BUFFER.remove()` tại `finally` là một chiến lược dọn dẹp phù hợp khi request kết thúc, nếu không có nhu cầu giữ lại state giữa requests.

Đừng suy luận “ThreadLocal key là weak reference nên mọi value được xóa ngay khi key không còn” — thread-local map entries/cleanup behavior và đường retention cụ thể cần phân tích theo runtime.

### 13.1. Các mẫu retention tương tự

- Global static collections giữ request contexts.
- Scheduled tasks chưa hủy giữ callbacks và captures.
- `CompletableFuture` chains giữ lambda closures hoặc intermediate results.
- Event listeners chưa unregister giữ owner objects.
- Thread context class loader giữ plugin loaders.
- Cache không giới hạn hoặc có policy eviction sai.
- Native references/JNI handles giữ Java objects hoặc native resources.

Trong mọi trường hợp, vấn đề không phải dấu ngoặc của biến mà là **cạnh reference nào còn tồn tại**.

## 14. Class loader và tuổi thọ của class metadata

Ở HotSpot, class metadata gắn với runtime class và class loader data. Một loader có thể định nghĩa nhiều classes; nếu host tiếp tục giữ loader hoặc classes/instances của nó reachable, việc **class unloading** có thể bị ngăn.

Ví dụ plugin:

```text
Host static registry
       |
       v
Listener (plugin class)
       |
       v
Plugin ClassLoader
       |
       v
Class metadata của plugin
```

Nếu plugin code trả về từ method và tất cả các local variables đã hết scope, nhưng host vẫn giữ listener, class loader vẫn có thể tồn tại lâu dài. Vì vậy **Metaspace growth** có thể liên quan đến object reachability trong heap và class loader retention.

Để gỡ plugin sạch, cần:
 
- Unregister listeners/callbacks.
- Cancel tasks/executors và giải phóng thread context class loaders phù hợp.
- Xóa cached plugin instances/references.
- Đóng resources của plugin theo ownership contract.
- Đảm bảo host không giữ reflection `Class`/`Method` hoặc closures khi không còn cần.

Việc close một `URLClassLoader` không tự buộc VM unload class ngay. Class unloading cũng phụ thuộc GC, VM và reachability.

## 15. Phân biệt memory leak, retention mong muốn và object còn reachable

### 15.1. “Memory leak” trong Java thường có nghĩa gì?

Trong managed heap, một kiểu leak thường gặp là **các object không còn cần cho nghiệp vụ nhưng vẫn reachable qua references**. GC làm đúng: nó không thu hồi objects mà chương trình vẫn có đường sử dụng, dù về mặt thiết kế những references đáng ra nên được bỏ.

Ví dụ:

```java
static final java.util.List<byte[]> HISTORY =
        new java.util.ArrayList<>();

static void onRequest() {
    HISTORY.add(new byte[1024 * 1024]);
}
```

Đây là class fragment minh họa. Nếu gọi `onRequest()` liên tục mà `HISTORY` không giới hạn kích thước/không có eviction, heap có thể tăng cho đến `OutOfMemoryError`. Lỗi không nằm ở phạm vi local của `onRequest`; nó nằm ở **static root và collection retention**.

### 15.2. Reachable nhưng chưa chắc leak

Một cache có giới hạn, queue có consumers hoặc data store giữ objects theo nghiệp vụ có thể là **retention có chủ đích**. Không xem tất cả objects surviving GC là “memory leak”.

Điều tra cần trả lời:

1. Ai sở hữu object?
2. Có còn cần object cho công việc sau này không?
3. Chính sách eviction/release là gì?
4. Tăng trưởng có tỷ lệ với workload hợp lệ hay không?
5. Sau khi workload kết thúc, retained heap có giảm hoặc ổn định không?

### 15.3. Unreachable nhưng memory chưa giảm cũng chưa chắc leak

Nếu object không còn reachable nhưng GC chưa chạy, heap used có thể còn cao. Nếu GC đã reclaim, heap **committed** vẫn có thể được giữ để phục vụ allocations sau đó; RSS không nhất thiết giảm ngay.

Do vậy đừng chỉ nhìn **`Runtime.totalMemory()`** hoặc một biểu đồ RSS rồi kết luận object vẫn sống. Cần phân biệt allocated, live/retained, committed và resident.

## 16. Escape analysis, scalar replacement và giới hạn suy luận từ `new`

HotSpot có thể tối ưu allocation bằng các kỹ thuật như **escape analysis** và **scalar replacement** khi điều kiện cho phép:

```java
static int sumPoint() {
    Point p = new Point(3, 4);
    return p.x + p.y;
}
```

Đây là code minh họa, cần định nghĩa `Point`. Nếu compiler chứng minh object `p` không thoát khỏi method và các thao tác có thể được biểu diễn bằng scalar values, VM có thể tránh materialize một heap object đầy đủ trong một số đường thực thi.

Điều này không làm thay đổi logic: caller vẫn nhận tổng theo ngữ nghĩa Java. Nhưng nó cho thấy câu “mọi `new` luôn khiến heap usage tăng một số byte quan sát được” **không phải bảo đảm**.

### 16.1. Escape analysis không phải phép chứng minh business correctness

Tối ưu hóa cần bảo toàn ngữ nghĩa quan sát được. Nó không hứa sẽ xảy ra cho mọi object hoặc mọi JDK, cũng không tự ngăn leak khi ứng dụng thật sự lưu object vào static registry.

### 16.2. Object lifetime theo source khác lifetime theo runtime

Với tối ưu hóa, một object có thể:

- Được materialize ở heap.
- Bị loại bỏ allocation bằng scalar replacement khi phù hợp.
- Được giữ lại vì callback/field/GC root khác.
- Trở thành không còn cần sớm hơn dấu ngoặc nguồn.
- Được GC reclaim trong một chu kỳ về sau.

Vì vậy không thể suy ngược lịch GC từ cú pháp block hoặc thứ tự khai báo.

## 17. Kỹ thuật điều tra bằng GC logs, JFR và heap dump

Khi ứng dụng có memory pressure, cần **bằng chứng runtime** thay vì đoán phạm vi biến.

### 17.1. GC logging trong HotSpot

Ví dụ:

```bash
java -Xlog:gc* -jar application.jar
```

Đây là lệnh minh họa cho một JAR có thể chạy. HotSpot Unified Logging hỗ trợ các tags/levels tùy phiên bản. Logs giúp xem chu kỳ GC, heap occupancy và những thông tin collector cung cấp, nhưng **không tự chỉ ra reference edge nào giữ một object cụ thể**.

### 17.2. JFR: allocations và pressure

**Java Flight Recorder (JFR)** hỗ trợ quan sát allocation patterns, GC pauses, heap summaries và một số stack traces theo cấu hình recording. Các sự kiện cụ thể và sampling options khác nhau giữa JDK/build.

Dùng JFR để hỏi: “Ở đâu tạo nhiều objects?”, “Tốc độ allocation ra sao?”, “GC có theo kịp workload?”. Để hỏi “Ai vẫn giữ object lâu dài?”, có thể phải kết hợp heap dump hoặc công cụ phân tích retention.

### 17.3. Heap dump và path to GC root

Một công cụ như Eclipse Memory Analyzer hoặc trình phân tích heap dump có thể cho biết:

- **Shallow heap:** dung lượng của chính object.
- **Retained heap:** lượng memory mà đường retention của object có thể giữ theo phân tích dominator/reachability.
- **Paths to GC roots:** những đường tham chiếu qua đó object vẫn reachable.
- Số lượng instances theo class, collection entries, retained listeners và class loaders.

Ví dụ quy trình:

1. Chụp heap dump sau khi workload đã ổn định.
2. Lặp workload tạo nghi ngờ leak.
3. Chụp heap dump tiếp theo sau những GC/điều kiện phù hợp.
4. So sánh counts/retained sizes.
5. Kiểm tra paths to GC roots của nhóm objects tăng bất thường.
6. Xác định owner cần release trong code.

Heap dump chứa dữ liệu nhạy cảm có thể nằm trong objects, nên phải bảo vệ file, giới hạn quyền truy cập và xóa đúng quy trình. Việc chụp dump trên production có thể tốn disk, I/O, pause và memory; cần lên kế hoạch vận hành phù hợp.

### 17.4. `jcmd` trên HotSpot

Ví dụ chẩn đoán (thay PID cụ thể):

```bash
jcmd -l
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /path/to/heap.hprof
```

`<pid>` và đường dẫn là placeholders dùng khi thao tác thực tế, không phải lệnh đã chạy trên hệ thống người đọc. `GC.class_histogram` có thể tốn chi phí đáng kể và một số chế độ liên quan yêu cầu safepoint/GC; heap dump có thể rất lớn.

Không dùng histogram duy nhất để kết luận chính xác ai giữ object. Histogram nói **có bao nhiêu instances theo type**, còn path-to-root mới giúp trả lời **vì sao chúng còn reachable**.

## 18. Reachability và Java Memory Model trong concurrency

Đối tượng có thể được chia sẻ qua fields/queues giữa các threads. Tuy nhiên, **reachability không thay thế memory visibility hoặc synchronization**.

Ví dụ:

```java
class Holder {
    Object value;
}
```

Nếu thread A ghi `holder.value = object` và thread B đọc `holder.value` mà không có quan hệ happens-before hoặc synchronization phù hợp, chương trình có thể có data race. GC/JVM vẫn phải quản lý references an toàn theo runtime rules, nhưng điều đó **không làm việc công bố object trở thành thread-safe**.

Để chia sẻ đúng, dùng các cơ chế như:

- `final` fields với initialization discipline phù hợp.
- `volatile` references cho visibility khi thích hợp.
- `synchronized` hoặc locks.
- Concurrent collections, blocking queues.
- Các quy tắc safe publication theo Java Memory Model.

**GC giữ object sống** và **thread B nhìn thấy trạng thái object đúng** là hai vấn đề khác nhau. Không dùng “object còn reachable” làm bằng chứng dữ liệu trong fields đã được publish đúng.

### 18.1. Callback scheduling

Nếu một callback chạy async, callback có thể giữ các captured references đến khi task kết thúc hoặc bị cancel và được gỡ khỏi scheduler. Đây là một retention path độc lập với lexical scope của method tạo callback.

Ví dụ một tác vụ hẹn giờ không được hủy có thể giữ object graph trong nhiều giờ sau khi HTTP request gốc đã trả response.

## 19. Bảng phân loại các tình huống thường gặp

| Tình huống | Có thể suy luận chắc từ scope không? | Cách hiểu đúng |
| --- | --- | --- |
| Method trả object tạo trong local | **Không** thể kết luận object chết | Caller giữ returned reference |
| Local ra khỏi block nhưng static list vẫn chứa object | **Không** thể kết luận reclaim | Strong reference từ registry còn |
| Local vẫn trong block nhưng không còn dùng | **Không** chắc giữ object đến `}` | JIT có thể rút ngắn live range |
| `local = null` | **Không** ép collection | Chỉ bỏ một reference edge, còn edges khác có thể |
| `System.gc()` | **Không** guarantee mọi object được thu hồi ngay | GC scheduling/behavior phụ thuộc runtime |
| `WeakReference.get() == null` | Có thể biết weak referent đã bị clear | Không đo được thời gian chết chính xác hay external cleanup |
| `WeakReference.get() != null` | Có reference có thể lấy tại thời điểm đó | Không hứa referent tồn tại mãi sau khi không giữ strong reference |
| `PhantomReference.get()` | **Luôn null** | Dùng queue/cleanup, không dereference |
| `Reference.reachabilityFence(x)` | Có guarantee về live reachability qua call | Không tự close/free hoặc pin địa chỉ |
| `AutoCloseable.close()` | Resource cleanup theo contract của API | Java object có thể vẫn reachable sau close |
| `Cleaner` đăng ký action | Không hứa khi nào action tự chạy | Explicit close vẫn nên là đường chính |
| `ThreadLocal` trong thread pool | Scope request không quyết định retention | Thread lifetime/value removal quan trọng |
| Object cycle không có root | Có thể eligible for GC | Không phải do reference count > 0 mà bất tử |
| Static collection tăng mãi | Có khả năng retention/leak | Kiểm tra owner, eviction và path-to-root |
| Heap committed không giảm ngay | Không chứng minh leak | GC/allocator có thể giữ heap phục vụ tái sử dụng |

## 20. Những sai lầm phổ biến

### Sai lầm 1: “Hết scope là gọi destructor”
Java không có C++-style scope-bound destructor cho Java heap objects. Dấu đóng block điều khiển phạm vi biến, không trực tiếp reclaim heap memory. Với resources có thể đóng, dùng try-with-resources.

### Sai lầm 2: “`local = null` sẽ giảm RSS ngay”
Không. Object có thể còn references, GC có thể chưa chạy, heap committed có thể không trả OS.

### Sai lầm 3: “Nếu object còn trong scope, GC không được reclaim”
Không chính xác. Compiler/JIT có thể làm ngắn khoảng strong-reachability khi không còn computation cần object; `Reference.reachabilityFence` tồn tại chính để chỉ ra một use cuối khi cần.

### Sai lầm 4: “Có một vòng object tự tham chiếu nên GC không thu hồi”
Không. Nếu cả vòng không còn reachable qua roots thích hợp, tracing collector có thể reclaim các objects đó.

### Sai lầm 5: “`WeakReference` tự hủy object khi không còn references”
Không. WeakReference tham gia reference processing của collector; nó không gọi “delete object” tại một lệnh Java xác định.

### Sai lầm 6: “`SoftReference` có TTL do Java cố định”
Không. Soft reference clearing do VM/GC quyết định trong phạm vi đặc tả và memory pressure.

### Sai lầm 7: “`PhantomReference.get()` trả object lúc sắp chết”
Sai. `get()` trả null. Phantom references không dùng để resurrect/dereference object.

### Sai lầm 8: “`Cleaner` là bản thay thế deterministic cho `close`”
Sai. Cleaner không có deadline guarantee; nên ưu tiên explicit close.

### Sai lầm 9: “Finalizer sẽ được gọi chắc chắn trước process exit”
Sai. Finalization bị deprecated for removal, có thể bị tắt/loại bỏ và không cho guarantee về tiến độ cleanup cần thiết.

### Sai lầm 10: “Một static reference chỉ giữ object khi method đang chạy”
Sai. Static reference có thể giữ object qua rất nhiều requests, phụ thuộc class-loader lifetime và nơi nó được clear.

### Sai lầm 11: “ThreadLocal key weak nên value luôn tự mất”
Sai. ThreadLocal value retention trong thread pools cần xử lý tường minh; `remove()` trong `finally` là một cách thiết kế phù hợp.

### Sai lầm 12: “Memory leak trong Java nghĩa là GC không hoạt động”
Không. GC có thể hoạt động đúng nhưng không thể reclaim objects vẫn reachable vì ứng dụng giữ references không cần thiết.

### Sai lầm 13: “Heap dump chứa mọi object từng được tạo”
Không. Heap dump là snapshot của những objects được runtime ghi nhận theo cách dump cụ thể, không phải nhật ký đầy đủ allocations đã diễn ra.

### Sai lầm 14: “Chạy test 100 lần thấy weak ref clear là timing guarantee”
Không. GC và reference processing không có một deadline portable đơn giản tương ứng.

### Sai lầm 15: “`Reference.reachabilityFence` pin object ở một địa chỉ cố định”
Không. Nó bảo đảm reachability qua điểm gọi, không ngăn moving GC.

## 21. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Một local `User user` ra khỏi block, nhưng `cache.put(key, user)` đã chạy. Có thể kết luận User được GC ngay không?

**Đáp án:** Không. Cache vẫn có thể giữ reference mạnh tới User; cần xét đường tới root và eviction policy.

**Câu 2.** `method()` trả về object vừa tạo. Sau khi method kết thúc, object có bắt buộc mất đi không?

**Đáp án:** Không. Caller nhận reference và có thể tiếp tục dùng object.

**Câu 3.** Một object không còn được dùng sau dòng 20, nhưng biến khai báo ở đầu method và dấu `}` ở dòng 200. Có bảo đảm object sống đến dòng 200 không?

**Đáp án:** Không. Compiler/JIT có thể kết thúc live range sớm hơn khi hợp lệ. Không suy lifetime từ lexical scope.

**Câu 4.** Viết `x = null; System.gc();` có chứng minh object của x đã bị thu hồi ngay không?

**Đáp án:** Không. Còn references khác có thể có; `System.gc()` không cho guarantee như vậy.

**Câu 5.** Hai Nodes giữ references lẫn nhau nhưng không còn root path nào. Có thể eligible for GC không?

**Đáp án:** Có. Cyclic references không tự giữ object sống nếu toàn bộ vòng không reachable từ roots.

**Câu 6.** `WeakReference` được dùng làm key trong một map, nhưng value của map giữ strong reference ngược tới key. Vấn đề gì có thể có?

**Đáp án:** Một strong path thông qua value có thể làm key vẫn reachable, ngăn GC-based cleanup như kỳ vọng. Cần phân tích reference graph của toàn map.

**Câu 7.** `SoftReference.get()` trả null trong một lần chạy; lần sau có bắt buộc null ở cùng lượng heap free không?

**Đáp án:** Không. Clearing policy/timing phụ thuộc collector và runtime.

**Câu 8.** Khi nào dùng `Reference.reachabilityFence(owner)`?

**Đáp án:** Khi cần bảo đảm owner wrapper còn strongly reachable cho đến sau một đoạn công việc, đặc biệt native-resource code có thể chỉ sử dụng địa chỉ/handle tách khỏi Java reference.

**Câu 9.** `reachabilityFence` có thay `close()` được không?

**Đáp án:** Không. Nó không giải phóng resources; nó chỉ bảo đảm reachability tại điểm gọi.

**Câu 10.** Vì sao nên dùng try-with-resources cho file stream?

**Đáp án:** Vì cần deterministic close theo điều khiển chương trình, không đợi GC quyết định khi nào resource wrapper unreachable.

**Câu 11.** `ThreadLocal` giữ byte array giữa những HTTP requests trên cùng worker thread. Có thể sửa bằng cách nào?

**Đáp án:** Dùng `try/finally` với `ThreadLocal.remove()` nếu scope dữ liệu chỉ trong request; tránh giữ object graph quá lâu.

**Câu 12.** Object được in trong heap dump có nghĩa bị memory leak?

**Đáp án:** Không. Có thể là live data hợp lệ. Cần xem ownership, retained size, path to root và growth trend.

**Câu 13.** Một object có `final` field giữ reference tới child. Điều này có nghĩa child sống mãi?

**Đáp án:** Không. Child có thể được giữ khi parent reachable; nếu toàn bộ parent-child graph không còn reachable, `final` không làm nó bất tử.

**Câu 14.** Có nên kiểm tra GC bằng assert `weak.get() == null` sau `Thread.sleep(500)`?

**Đáp án:** Không. Đây là test phụ thuộc timing, không có guarantee portable.

**Câu 15.** Tăng `-Xmx` chữa được mọi memory leak?

**Đáp án:** Không. Nó có thể trì hoãn OOME cho một retention problem nhưng không sửa đường giữ object. Native memory/resource leaks còn là vấn đề khác.

## 22. Checklist phân tích tuổi thọ đối tượng trong dự án thực tế

1. Xác định **object nào** đang cần quản lý và “không còn cần” nghĩa gì theo nghiệp vụ.
2. Phân biệt **source scope**, **reference liveness** và **heap reachability**.
3. Vẽ **strong reference paths** từ các owners/roots.
4. Kiểm tra static registries, caches, listeners, callbacks, ThreadLocals, executors, class loaders.
5. Xác định explicit ownership/release APIs: `remove`, `clear`, `cancel`, `close`.
6. Với resources, dùng try-with-resources và xác định đường exception handling.
7. Với weak/soft/phantom references, đừng dựa vào timing/số lượng GC runs.
8. Với Cleaner, bảo đảm cleaning action không vô tình capture referent; đừng coi nó là cleanup chính.
9. Nếu native resource wrapper có thời gian sống nhạy cảm, nghiên cứu `Reference.reachabilityFence` đúng vị trí.
10. Dùng heap dumps/JFR/GC logs theo đúng mục đích; bảo vệ dữ liệu nhạy cảm.
11. So sánh memory trend qua nhiều workload/GC, không một snapshot đơn.
12. Kiểm tra cả Java heap, Metaspace, thread stacks và native resources khi RSS tăng.
13. Không dùng `System.gc()`, `finalize` hoặc `Thread.sleep` như lifecycle design.
14. Kiểm thử các đường hủy đăng ký listener, đóng pool/executor, plugin unload và ứng dụng shutdown.
15. Tách **correctness**, **resource safety** và **performance** thành những yêu cầu quan sát độc lập.

### Tóm tắt

```text
Source variable scope
     |  quy định chỗ dùng được tên biến
     X  KHÔNG phải lifetime contract cho heap object
     |
     v
Reference graph (strong / soft / weak / phantom)
     |
     v
Object reachability theo VM/reference processing
     |
     v
Eligible for reclamation khi đủ điều kiện
     |
     v
GC có thể reclaim theo runtime schedule

Ngoài ra:
  AutoCloseable / try-with-resources
       → deterministic resource cleanup
  Reference.reachabilityFence
       → bảo đảm strong reachability tới một điểm
  WeakReference / Cleaner
       → tương tác GC, không có deadline thu hồi
```

**Bài học cần giữ:** **Không được suy thời điểm object chết hoặc được thu hồi chỉ từ phạm vi của biến Java.** Hãy phân tích đồ thị tham chiếu, phạm vi sống thực, hành vi tối ưu hóa và hợp đồng reference/GC của JVM. Với tài nguyên quan trọng, quản lý vòng đời chủ động thay vì chờ collector.

### Tài liệu chính thức

- [JVMS `2.5.3 — Heap (Java SE 26)](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html#jvms-2.5.3): heap objects và automatic storage management.
- [JLS `12.6.1 — Implementing Finalization (Java SE 26)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.6.1): reachability, optimizer có thể giảm live references, lịch sử finalization.
- [java.lang.ref — Package Specification (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): các mức reachability và ý nghĩa của soft/weak/phantom references.
- [Reference.reachabilityFence (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): bảo đảm reachability tới một điểm cụ thể.
- [Cleaner (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleaning actions và hạn chế non-deterministic cleanup.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): vì sao không xây lifecycle mới trên `finalize`.
- [JLS `14 — Blocks and Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html): scope và control flow ở Java source.
- [Oracle JDK 17 — HotSpot GC Tuning, Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): soft, weak, phantom references và cơ chế GC.
