# Tham chiếu mạnh, mềm, yếu và ảo trong `java.lang.ref`

**Một đối tượng có còn được truy cập hay không** ảnh hưởng trực tiếp đến việc garbage collector (GC) có thể thu hồi nó. Nhưng “có một biến đang giữ reference” chưa đủ để kết luận object phải sống mãi: Java phân biệt **strong**, **soft**, **weak** và **phantom references**, với những quy tắc reachability khác nhau. Những cơ chế này quan trọng cho cache, bản đồ khóa yếu, canonicalization, quản lý metadata và dọn dẹp tài nguyên ngoài Java heap.

Bài thuộc mục **Khả năng truy cập** trong Java Advance – JVM. Mục tiêu là hiểu object graph dưới góc nhìn JVM, cách dùng `java.lang.ref` đúng hợp đồng Java 17, thời điểm `Reference.get()` trả `null`, vai trò `ReferenceQueue` và `Cleaner`, và những điều **không thể dự đoán chính xác** do GC là bất đồng bộ.

Đặc biệt phân biệt:

- **Strong reference** là reference thông thường mà code Java dùng; đối tượng còn strong-reachable **không bị thu hồi** chỉ vì GC chạy.
- **`SoftReference<T>`** cho phép đối tượng được giữ lại khi bộ nhớ phù hợp nhưng GC có thể xóa reference vì nhu cầu bộ nhớ; không phải hợp đồng cache có thời hạn giữ cố định.
- **`WeakReference<T>`** không giữ cho referent sống khi chỉ còn weak reachability; dùng cho metadata/canonical mappings và nền tảng của weak keys.
- **`PhantomReference<T>`** không cho lấy lại referent qua `get()`; phối hợp với `ReferenceQueue` để nhận tín hiệu phục vụ cleanup sau khi referent không còn được dùng.
- **`ReferenceQueue<T>`** chuyển thông tin về những **reference objects**, không trực tiếp “trả object đã chết”.
- **`Cleaner`** (Java 9+) xây trên phantom-reference processing để đăng ký hành động cleanup; **`AutoCloseable` và try-with-resources** vẫn nên là cách đóng tài nguyên đúng hạn.

## 1. Reachability: GC nhìn vào đồ thị tham chiếu, không nhìn tên biến

Để hiểu bốn mức reference, trước hết hình dung **GC roots**: những nguồn được JVM coi là điểm bắt đầu việc tìm object còn có thể được chương trình sử dụng, chẳng hạn Java thread-local state còn sống, static state phù hợp và các nguồn đặc biệt do VM/JNI quản lý.

```text
GC roots
   │
   ├── strong ──► User ──► strong ──► Address
   │
   └── strong ──► WeakReference ── weak ──► CachedObject
                                       │
                        không có strong path khác?
                                       │
                                GC có thể clear weak
```

Điều quan trọng là **loại cạnh trên đồ thị**. Một object `WeakReference` bản thân nó có thể đang được giữ bằng strong reference; nhưng liên kết từ `WeakReference` tới đối tượng đích (**referent**) lại có ngữ nghĩa **weak**. Giữ `WeakReference` trong một `static final` không tự biến referent thành strong-reachable.

Không phải tất cả các field trỏ tới object đều có loại `WeakReference`. Những biến/field/array elements chứa reference Java thông thường tạo strong edges, trừ khi API chứa chúng có đặc tả reachability đặc biệt.

### 1.1. “Strong reference” có phải một class không?

Không. Java không có `new StrongReference<>(obj)` trong `java.lang.ref`. “Strong reference” mô tả việc bạn **trực tiếp** có reference trong Java như:

```java
Object value = new Object();
Object alias = value;
```

Cả `value` và `alias` chứa reference thông thường tới cùng object. Nếu chúng còn thực sự được dùng, object không trở thành weakly reachable chỉ vì code cũng tạo một `WeakReference<>(value)`.

### 1.2. Không phải cứ ra khỏi dấu `}` là GC phải thu hồi

Một local variable hết lexical scope **không tạo mệnh lệnh GC**. JIT còn có thể xác định object không còn được dùng **sớm hơn** phần cuối scope, trong khi references ở field/static/stack khác có thể giữ object sống lâu hơn.

Không dựa vào phạm vi source đơn thuần để đo thời điểm enqueue hay kết thúc resource. Khi có việc quản lý tài nguyên với side effects quan sát được, `Reference.reachabilityFence` hoặc explicit close có thể quan trọng hơn tưởng tượng ban đầu.

## 2. Thứ tự strong → soft → weak → phantom → unreachable

Package specification Java 17 `java.lang.ref` mô tả các mức reachability theo thứ tự từ mạnh đến yếu:

| Mức | Điều kiện ý tưởng | Hệ quả chính |
| --- | --- | --- |
| **Strongly reachable** | Có đường đi từ thread/root mà **không traversing reference objects** theo định nghĩa reachability | GC không được thu hồi object chỉ vì đang chạy GC |
| **Softly reachable** | Không còn strong-reachable nhưng còn đường đi qua **soft reference** | GC có thể clear soft theo nhu cầu memory |
| **Weakly reachable** | Không còn strong/soft reachable nhưng còn đường qua **weak reference** | Khi GC xác định weak reachability, nó clear weak refs theo quy tắc |
| **Phantom reachable** | Không còn các mức trên, đã qua xử lý finalization theo định nghĩa và có phantom reference | Đủ điều kiện để phantom-reference processing và notification |
| **Unreachable** | Không thuộc các mức reachability trên | Có thể được GC thu hồi khi phù hợp |

Đây là **phân loại ở mức GC**, không phải các trạng thái do chương trình được quyền tự đặt bằng cách ghi enum vào object. Một referent chỉ còn weak-reachable có thể biến mất khỏi góc nhìn `WeakReference.get()` khi GC thực hiện reference processing.

### 2.1. Object chỉ có một “mức” tại một thời điểm theo con đường mạnh nhất

Giả sử một object có cả `SoftReference` và `WeakReference` trỏ tới nó:

```text
root ─► SoftReference ─soft─┐
                            ├──► Object
root ─► WeakReference ─weak─┘
```

Nếu không có strong path, nó đang **softly reachable**, không phải weakly reachable, vì soft mạnh hơn weak. Điều đó có thể trì hoãn clear weak ref so với trường hợp chỉ có weak. Khi các soft references bị clear và không còn strong path, object có thể trở thành weakly reachable trong đợt xử lý phù hợp.

Ngược lại, nếu có strong path khác, soft và weak refs trỏ tới cùng object thường vẫn có thể `get()` trả object (nếu chưa bị chương trình chủ động `clear()`). Một soft/weak reference **không ép GC xóa** khi target vẫn đang strongly reachable.

### 2.2. Không có đồng hồ đếm ngược cho weak/soft

GC timing phụ thuộc heap pressure, collector, safepoints, optimization, reference processing, CPU và việc object còn reachable từ đâu. **Không có hợp đồng “weak bị clear sau N giây”** hoặc “soft sống đến lúc heap dùng hết 80%”. Những giả định như vậy khiến unit tests không ổn định và cache behavior khó dự đoán.

## 3. Strong reference: con đường giữ object sống thông thường

Các field, local variables, array elements và method parameters bình thường có thể giữ strong references khi thực sự là các nguồn reachable. Ví dụ:

```java
import java.lang.ref.WeakReference;

public class StrongExample {
    public static void main(String[] args) {
        Object target = new Object();               // strong
        WeakReference<Object> weak = new WeakReference<>(target);

        System.out.println("alive=" + (weak.get() == target));
        java.lang.ref.Reference.reachabilityFence(target);
    }
}
```

Chạy:

```bash
javac --release 17 StrongExample.java
java StrongExample
```

Stdout:

```text
alive=true
```

`target` là strong reference và được sử dụng ở phép so sánh; `reachabilityFence(target)` giữ mạnh reachability đến điểm gọi fence. GC không được clear weak reference đến target chỉ vì có một weak wrapper khi target vẫn còn strong-reachable.

### 3.1. Một biến Java có thể được tối ưu ra khỏi liveness

Ví dụ native handle gắn với một Java wrapper:

```java
long handle = resource.getNativeHandle();
useNativeHandle(handle);
// Không còn đọc field nào của resource.
```

JIT có thể xem `resource` không còn được dùng sau khi lấy `handle`, mặc dù công việc native còn dùng tài nguyên gắn với resource. Nếu `Cleaner` thu hồi tài nguyên quá sớm, mã native có thể dùng handle đã đóng.

Trong một thiết kế thích hợp, đặt `Reference.reachabilityFence(resource)` **sau thao tác cuối cần tài nguyên còn sống**:

```java
long handle = resource.getNativeHandle();
try {
    useNativeHandle(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(resource);
}
```

Đây là **snippet ý tưởng**, cần tự định nghĩa `resource` và `useNativeHandle`. Fence không thay close/locking của tài nguyên; nó chỉ bảo đảm strong reachability ít nhất cho tới vị trí gọi. `reachabilityFence` không yêu cầu GC chạy.

## 4. `SoftReference<T>`: cache có thể bị GC giải phóng theo memory demand

`SoftReference` phù hợp với ý tưởng **“giữ một giá trị khi còn chỗ, nhưng cho GC bỏ cache khi cần memory”**. Constructor phổ biến:

```java
SoftReference<Image> ref = new SoftReference<>(image);
Image cached = ref.get();
```

Đoạn này là **minh họa** vì cần class `Image` và biến `image` đã định nghĩa.

API:

- `new SoftReference<>(value)` tạo soft reference **không đăng ký queue**.
- `new SoftReference<>(value, queue)` đăng ký với `ReferenceQueue`.
- `ref.get()` trả referent khi còn tồn tại, hoặc `null` nếu reference đã bị clear bởi GC/code.
- `ref.clear()` chủ động clear; không có nghĩa GC đã quyết định memory pressure.
- Theo Java 17 Javadoc, các soft references còn trỏ tới **softly-reachable objects** được đảm bảo bị clear trước khi VM ném `OutOfMemoryError` theo cơ chế được nêu. Điều đó **không** hứa mọi loại OOME đều phòng được bằng soft cache; native memory, quá nhiều threads hay heap live set strong có thể vẫn gây OOME.

### 4.1. Ví dụ cache phải luôn có đường tái tạo

```java
import java.lang.ref.SoftReference;
import java.util.Objects;
import java.util.function.Supplier;

public class SoftCacheDemo {
    private static SoftReference<String> cached = new SoftReference<>(null);

    static String getOrLoad(Supplier<String> loader) {
        String result = cached.get();
        if (result == null) {
            result = Objects.requireNonNull(loader.get());
            cached = new SoftReference<>(result);
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("first=" + getOrLoad(() -> "DATA"));
        cached.clear();    // Xóa thủ công để test nhánh cache miss.
        System.out.println("second=" + getOrLoad(() -> "DATA"));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 SoftCacheDemo.java
java SoftCacheDemo
```

Stdout xác định:

```text
first=DATA
second=DATA
```

Đây là demo **single-threaded** cho nhánh hit/miss; code sử dụng `clear()` chủ động để tạo miss có kiểm soát, **không giả vờ mô phỏng quyết định memory pressure của GC**. Trong hệ thống nhiều threads, code phải đồng bộ/cache atomic để tránh duplicate loads và data races.

### 4.2. Vì sao `SoftReference` không nên là chiến lược cache mặc định?

- Chính sách xóa do JVM/collector quyết định; cache có thể giữ dữ liệu quá lâu hoặc mất dữ liệu đồng loạt khi memory pressure.
- Không có giới hạn dung lượng, TTL, eviction policy, hay nguyên tắc chọn least-recently-used ở mức Java API.
- Reconstruct value có thể tốn CPU/I/O và gây cache stampede khi nhiều giá trị bị clear.
- Soft refs cũng là **objects** và có chi phí lookup/reference processing.
- Một soft cache giữ nhiều dữ liệu sẽ thay đổi retained heap và GC activity.

Với cache production cần quota/TTL/metrics/chủ động eviction, thường phù hợp hơn dùng cache có chính sách rõ (ví dụ bounded cache) thay vì giao toàn bộ quyết định cho soft reachability.

## 5. `WeakReference<T>`: không giữ referent sống

`WeakReference` thường dùng khi ứng dụng **muốn ghi nhớ một object chừng nào nơi khác vẫn dùng nó**; khi không còn strong/soft paths, GC có thể clear weak references theo quy tắc.

Ví dụ khái niệm:

```text
App ──strong──► WeakReference<W>
                     │
                   weak
                     │
                     ▼
                Widget@123

Nếu app không còn đường strong/soft tới Widget@123:
GC có thể phát hiện weak reachability và clear reference.
App vẫn giữ WeakReference object, nhưng get() về sau có thể là null.
```

### 5.1. Bài thử `WeakReference` không được dựa vào timing cố định

Một ví dụ được thấy nhiều:

```java
Object obj = new Object();
WeakReference<Object> weak = new WeakReference<>(obj);
obj = null;
System.gc();
System.out.println(weak.get());
```

Đây là **snippet KHÔNG có stdout cố định**. `System.gc()` là một lời yêu cầu, GC có thể không xảy ra ngay hoặc bị vô hiệu hóa; JIT liveness và references khác cũng ảnh hưởng. Kết quả có thể là `null` hoặc object theo thời điểm thực thi.

Đừng viết unit test kiểu `assertNull(weak.get())` sau một `System.gc()` duy nhất. Muốn kiểm tra logic khi referent biến mất, dùng `weak.clear()` để tạo tình huống deterministically hoặc tách phần queuing thành test phù hợp.

### 5.2. Atomic read pattern: luôn lưu kết quả `get()` vào strong local

```java
WeakReference<Resource> weak = obtainWeakRef();
Resource resource = weak.get();
if (resource != null) {
    resource.use();
}
```

Đây là **snippet minh họa**, `Resource`/`obtainWeakRef` cần được khai báo trong ứng dụng.

**Tại sao phải lưu local?** Nếu gọi `weak.get()` nhiều lần, lần đầu có thể trả object, lần sau có thể trả `null` khi referent chỉ còn weakly reachable giữa các lần. Lấy một lần vào local `resource` tạo strong reference trong thời gian nó cần được dùng theo semantics; có thể thêm `Reference.reachabilityFence(resource)` nếu công việc với tài nguyên nằm ngoài đường sử dụng Java mà optimizer khó quan sát.

Không viết:

```java
if (weak.get() != null) {
    weak.get().use();  // Rủi ro: get lần hai có thể là null.
}
```

`WeakReference` không cung cấp hợp đồng “giữa hai lệnh `get()` không bao giờ có GC”; dùng một strong local là cách đúng.

## 6. `WeakHashMap`: weak keys, nhưng values thường là strong

`java.util.WeakHashMap<K,V>` là ví dụ rất hữu ích của weak references:

- Map giữ các **keys bằng weak references**.
- Values được giữ bằng **strong references**.
- Key có thể bị GC loại bỏ nếu không còn ordinary strong/soft reachability từ các đường khác.
- Mapping có thể biến mất **dù code không gọi `remove`**, nên size/iteration có hành vi phụ thuộc GC.
- Map **không tự thread-safe**.
- `WeakHashMap` không phải `WeakReference` wrapping toàn bộ Map object; nó áp dụng weak semantics cho **keys**.

### 6.1. Ví dụ runnable có kết quả ổn định

Tạo file **`WeakMapDemo.java`**:

```java
import java.util.WeakHashMap;

public class WeakMapDemo {
    static class Key {
        final String code;
        Key(String code) { this.code = code; }
    }

    static class Value {
        final Key owner;  // Cố tình giữ strong reference ngược tới key.
        Value(Key owner) { this.owner = owner; }
    }

    public static void main(String[] args) {
        WeakHashMap<Key, Value> map = new WeakHashMap<>();
        Key key = new Key("A");
        map.put(key, new Value(key));

        key = null;  // Chỉ xóa strong local reference.
        System.out.println("size=" + map.size());
        map.clear();
        System.out.println("afterClear=" + map.size());
    }
}
```

Chạy:

```bash
javac --release 17 WeakMapDemo.java
java WeakMapDemo
```

Stdout xác định:

```text
size=1
afterClear=0
```

**Vì sao vẫn có 1 entry?** Map giữ `Value` mạnh; `Value.owner` lại giữ `Key` mạnh. Dù bản thân map dùng weak keys, graph có chuỗi:

```text
GC root → WeakHashMap → Value (strong)
                         │
                         └── owner (strong) → Key

WeakHashMap → weak key ──────────────► Key
```

Điều này ngăn key chỉ còn weakly reachable. Khi `map.clear()`, ứng dụng chủ động xóa mapping; output `0` không chứng minh GC đã xử lý key.

### 6.2. Trường hợp dễ tạo leak với weak-key map

Cache value thường có thể vô tình tham chiếu ngược về key, ví dụ value là `ListenerRegistration` giữ đối tượng listener cũng chính là key. Key vẫn reachable từ map value; mapping không tự biến mất.

Các giải pháp tùy thiết kế:

- Value chỉ lưu thông tin **không tham chiếu ngược tới key**.
- Dùng explicit `remove` khi vòng đời nghiệp vụ kết thúc.
- Nếu cần weak values thay vì weak keys, thiết kế riêng với `WeakReference<V>` hoặc cache library phù hợp.
- Nếu key là chuỗi literal/interned String, key có thể tồn tại lâu; weak key **không** có tác dụng như “TTL”.

## 7. `PhantomReference<T>`: nhận thông báo mà không lấy lại object

`PhantomReference` được thiết kế cho xử lý cuối vòng đời (post-mortem cleanup scheduling). Điểm khác rõ nhất so với soft/weak:

**`PhantomReference.get()` luôn trả `null`**, kể cả khi bạn vừa tạo reference trong lúc referent vẫn đang strongly reachable.

Phantom reference cần `ReferenceQueue` để có kênh nhận notification hữu ích:

```java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object target = new Object();
PhantomReference<Object> phantom = new PhantomReference<>(target, queue);
```

Với Java 17:

- `phantom.get() == null` luôn đúng.
- `phantom.refersTo(target)` có thể kiểm tra phantom reference hiện đang trỏ tới object `target` (phương thức `Reference.refersTo` có từ Java 16).
- Khi collector xác định object phantom-reachable theo định nghĩa và reference chưa bị clear, JVM có thể clear và enqueue phantom reference theo quy tắc.
- `queue.poll()` nhận **PhantomReference object**, không cho lấy lại referent đã không còn accessible qua `get()`.
- Nếu constructor nhận `queue = null`, reference sẽ **không được enqueue**.

### 7.1. Tại sao không cho `get()` đọc referent?

Nếu cho Java code lấy lại referent qua phantom reference, chính việc lấy nó có thể làm object strong-reachable trở lại và gây phức tạp cho cleanup. Bằng việc luôn trả `null`, phantom reference chỉ dùng như **tín hiệu vòng đời** chứ không làm “cửa sau” để truy cập lại object.

Chính vì thế, không thiết kế phantom cleanup action bằng cách:

```java
Object obj = phantom.get();
obj.close();    // Sai: get() luôn null.
```

Cần giữ **thông tin cleanup riêng biệt** (ví dụ file descriptor, native handle, id tài nguyên) mà không tạo strong path từ registry/callback về object được theo dõi.

### 7.2. Không nhầm Java 8 phantom reference rules với Java 17

Tài liệu Java 17 mô tả việc GC **clear phantom references** khi object phantom-reachable rồi enqueue đồng thời hoặc sau đó. Một số tài liệu rất cũ (trước thay đổi của JDK 9) nói phantom references không được tự clear khi enqueue; **không áp dụng nguyên xi mô tả legacy đó cho Java 17**.

Ngoài ra, ngữ nghĩa liên quan finalization không phải bảo đảm rằng mọi chương trình thực sự chạy finalizer đúng thời điểm. Finalization đã bị phản đối mạnh do khó dự đoán, rủi ro và thiết kế kế thừa; nên dùng `Cleaner` hoặc explicit resource management thay vì dựa vào `finalize()`.

## 8. Chương trình Java 17 đầy đủ so sánh bốn kiểu reference

Tạo file **`ReferenceKindsDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.SoftReference;
import java.lang.ref.WeakReference;

public class ReferenceKindsDemo {
    public static void main(String[] args) {
        Object target = new Object();         // Strong reference.
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        SoftReference<Object> soft = new SoftReference<>(target);
        WeakReference<Object> weak = new WeakReference<>(target);
        PhantomReference<Object> phantom =
                new PhantomReference<>(target, queue);

        System.out.println("soft.same=" + (soft.get() == target));
        System.out.println("weak.same=" + (weak.get() == target));
        System.out.println("phantom.null=" + (phantom.get() == null));
        System.out.println("phantom.refersTo=" + phantom.refersTo(target));

        // Giữ target mạnh reachable trong toàn bộ phần kiểm tra trên.
        Reference.reachabilityFence(target);

        // Tạo kịch bản đã clear mà KHÔNG phụ thuộc thời gian GC.
        weak.clear();
        soft.clear();
        System.out.println("weak.cleared=" + (weak.get() == null));
        System.out.println("soft.cleared=" + (soft.get() == null));
        System.out.println("queue.empty=" + (queue.poll() == null));
    }
}
```

Biên dịch/chạy JDK 17:

```bash
javac --release 17 ReferenceKindsDemo.java
java ReferenceKindsDemo
```

**Stdout xác định:**

```text
soft.same=true
weak.same=true
phantom.null=true
phantom.refersTo=true
weak.cleared=true
soft.cleared=true
queue.empty=true
```

Giải thích:

1. `target` được giữ mạnh tới `reachabilityFence`, nên `soft.get()` và `weak.get()` cùng trỏ object ấy khi kiểm tra.
2. `phantom.get()` là `null` **theo API contract**, không phải do GC đã thu hồi object.
3. `phantom.refersTo(target)` là `true` trước khi bị clear, vì nó trỏ tới object `target`.
4. `weak.clear()` và `soft.clear()` là **chủ động xóa**, không biểu thị GC quyết định hai referents đã unreachable.
5. `Reference.clear()` **không tự enqueue reference**, nên queue phantom vẫn trống trong ví dụ; target chưa có lý do để phantom-enqueue trước điểm fence. Không dùng kết quả này để suy GC sẽ luôn chạy vào thời điểm khác.

### 8.1. Bài thử `System.gc()` chỉ để quan sát, không được dùng như test chắc chắn

Có thể thử tạo rất nhiều objects ngắn hạn, bỏ strong refs rồi gọi `System.gc()` để quan sát `WeakReference.get()` hoặc queue. Nhưng:

- `System.gc()` là request/hint; JVM có quyền khác nhau về xử lý.
- Compiler có thể làm đối tượng hết strong reachability sớm hơn trực giác.
- Không có SLA GC hoàn tất trong 10 ms, 1 s hay số vòng lặp cố định.
- Queue notification có thể đến muộn hơn việc clearing references.
- Vì vậy ví dụ học có stdout cố định ở trên **chủ động dùng `clear()` và `reachabilityFence`**, thay vì cam kết lịch trình GC.

## 9. `ReferenceQueue<T>`: nhận reference đã đăng ký, không lấy object chết

Reference queue hỗ trợ lập trình **phản ứng** với những thay đổi reachability.

Constructor phổ biến:

```java
ReferenceQueue<Resource> queue = new ReferenceQueue<>();
WeakReference<Resource> ref = new WeakReference<>(resource, queue);
```

Đoạn trên là minh họa cần `Resource` và `resource` phù hợp. Queue nhận **reference object** sau khi được JVM enqueue; không phải queue chứa một bản sao referent.

Các API quan trọng của Java 17:

| API | Ý nghĩa |
| --- | --- |
| `new ReferenceQueue<T>()` | Tạo queue |
| `queue.poll()` | Lấy ngay một enqueued reference hoặc `null` nếu queue trống |
| `queue.remove()` | Chờ tới khi có reference, có thể bị interrupt |
| `queue.remove(timeout)` | Chờ tối đa timeout milliseconds, trả reference hoặc `null` |
| `new WeakReference<>(obj, queue)` | Đăng ký weak reference với queue |
| `new SoftReference<>(obj, queue)` | Đăng ký soft reference với queue |
| `new PhantomReference<>(obj, queue)` | Đăng ký phantom reference với queue |
| `ref.clear()` | Xóa referent, **không** tự enqueue |
| `ref.enqueue()` | **Chủ động** clear và enqueue reference đã đăng ký, nếu phù hợp |
| `ref.refersTo(obj)` | Kiểm tra identity của referent, kể cả với phantom reference |

Không phụ thuộc `Reference.isEnqueued()`: Java 17 đã **deprecated** method này vì hành vi/test race; dùng kết quả `poll`/`remove` và cấu trúc quản lý riêng.

### 9.1. Demo queue không phụ thuộc collector

Tạo file **`ReferenceQueueDemo.java`**:

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ReferenceQueueDemo {
    public static void main(String[] args) {
        Object target = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        WeakReference<Object> ref = new WeakReference<>(target, queue);

        System.out.println("before=" + (queue.poll() == null));
        System.out.println("manualEnqueue=" + ref.enqueue());
        System.out.println("cleared=" + (ref.get() == null));
        System.out.println("sameRef=" + (queue.poll() == ref));
        System.out.println("emptyAfterPoll=" + (queue.poll() == null));
        java.lang.ref.Reference.reachabilityFence(target);
    }
}
```

Lệnh:

```bash
javac --release 17 ReferenceQueueDemo.java
java ReferenceQueueDemo
```

Stdout:

```text
before=true
manualEnqueue=true
cleared=true
sameRef=true
emptyAfterPoll=true
```

Điểm cần nhấn mạnh: `ref.enqueue()` là **thao tác thủ công** để kiểm thử cơ chế queue, không mô phỏng collector thực sự đã xác nhận target weakly reachable. Việc `ref.get()==null` ở đây là kết quả explicit enqueue/clearing, dù `target` còn strongly reachable.

### 9.2. Phải giữ bản thân reference object sống

Package specification nhấn mạnh: `ReferenceQueue` **không tự theo dõi và giữ mọi reference đã đăng ký**. Nếu `WeakReference`/`PhantomReference` object trở nên unreachable trước khi GC muốn enqueue, ứng dụng **không còn gì để quan sát**.

Vì vậy code làm tracking thường phải giữ các reference objects trong một collection mạnh cho đến khi xử lý xong:

```java
ReferenceQueue<Resource> queue = new ReferenceQueue<>();
Set<PhantomReference<Resource>> liveRefs = new HashSet<>();
PhantomReference<Resource> ref = new PhantomReference<>(resource, queue);
liveRefs.add(ref);
```

Đây là **snippet**, cần các imports, `Resource` và biến `resource`. Khi lấy reference từ queue, chương trình tìm thông tin cleanup tương ứng, xóa entry khỏi `liveRefs` và thực hiện công việc tài nguyên (không gọi `get()` của phantom để lấy resource).

Cần rất cẩn thận: **map từ phantom ref sang cleanup state không được vô tình giữ strong reference tới referent** — nếu có, đối tượng sẽ không đến trạng thái phantom-reachable để kích hoạt cleanup.

## 10. `Cleaner`: thay vì tự quản lý phantom queue thấp cấp

`java.lang.ref.Cleaner` (Java 9+) quản lý **phantom references + reference queue + cleaning actions** để giảm boilerplate. `Cleaner.register(object, action)` trả về `Cleanable` có method `clean()`.

Theo Javadoc:

- Cleaning action có thể chạy **sau khi referent trở thành phantom-reachable**, trừ khi đã chạy bằng explicit `clean()`.
- Một action được chạy **tối đa một lần** qua Cleanable.
- Action **không được strong-capture object được đăng ký**; nếu bắt giữ chính object, object đó không còn phantom-reachable và automatic cleanup không diễn ra.
- Cleaner có thread riêng để chạy cleanup theo cấu hình; thời điểm automatic cleanup không bảo đảm và hành vi khi `System.exit` là implementation-specific.
- **Gọi `clean()` chủ động trong `close()`** là cách hữu ích, nhưng vẫn phải thiết kế resource lifetime/ownership chính xác.

### 10.1. Ví dụ `Cleaner` và `AutoCloseable` chạy được, không phụ thuộc GC

Tạo file **`CleanerDemo.java`**:

```java
import java.lang.ref.Cleaner;

public class CleanerDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        @Override
        public void run() {
            System.out.println("released");
        }
    }

    static final class Resource implements AutoCloseable {
        private final Cleaner.Cleanable cleanable =
                CLEANER.register(this, new State());

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("using");
        }
        System.out.println("closed");
    }
}
```

Chạy:

```bash
javac --release 17 CleanerDemo.java
java CleanerDemo
```

Stdout chính xác:

```text
using
released
closed
```

`Resource` được đóng **tường minh** bởi try-with-resources, nên `close()` gọi `cleanable.clean()` ở thời điểm rõ ràng và action in một lần. Không dùng thời điểm GC để quyết định stdout.

Chương trình chỉ **in một dòng giả lập cleanup**, không chứng minh việc giải phóng một socket/file descriptor thực. Trong production, `State` cần giữ resource state cần thiết (ví dụ native handle) và action an toàn, idempotent, không giữ strong reference tới `Resource`.

### 10.2. Sai lầm capture `this` trong cleaning action

**Sai**:

```java
cleanable = CLEANER.register(this, () -> closeNativeField());
```

Nếu lambda gọi instance method/field của object đang đăng ký, nó thường **capture `this`**. Cleaner giữ action, action giữ object, và object không thể phantom-reachable; automatic cleanup vì vậy không bao giờ chạy theo kỳ vọng.

**Đúng hơn**: tạo một `static` nested `State implements Runnable` chứa handle/metadata độc lập với owner; đăng ký `new State(handle)` và bảo đảm reference graph không dẫn ngược về owner.

### 10.3. Explicit resource management vẫn là chuẩn

`Cleaner` là cơ chế dự phòng hữu ích khi resource bị bỏ quên, **không thay thế**:

- `try-with-resources` cho stream, file, socket, DB connection và `AutoCloseable`.
- `finally` để giải phóng tài nguyên theo deterministic scope.
- Chính sách `close` idempotent/thread-safe và chuyển ownership được xác định rõ.
- Quản lý native handle sao cho không có use-after-close.

Chờ GC để đóng kết nối mạng có thể khiến file descriptors cạn trước khi collector quyết định xử lý. Không thiết kế business correctness phụ thuộc vào việc Cleaner phải chạy trước một deadline.

## 11. Sai lầm lớn: reference object còn sống không có nghĩa referent còn sống

Một trong những graph phổ biến:

```text
static Set<WeakReference<Client>> tracked
       │
       ├─ strong ──► WeakReference #1 ── weak ──► Client A
       ├─ strong ──► WeakReference #2 ── weak ──► Client B
       └─ strong ──► WeakReference #3 ── weak ──► Client C
```

Ứng dụng **giữ wrapper refs mạnh** để theo dõi queue nhưng không vì thế bắt GC phải giữ Client objects sống. Nếu không có strong paths khác tới `Client B`, weak reference có thể bị clear. Điều này chính là mục tiêu của weak tracking.

Tuy nhiên nếu value trong side map, listener list hoặc cleanup state lại trỏ strong về Client, tình huống đổi thành:

```text
static trackingData ──strong──► CleanupState
                                   │
                                   └─strong──► Client B
```

Lúc này Client B vẫn strongly reachable dù có weak/phantom refs. Muốn tìm memory leak, **đọc toàn bộ incoming reference chains tới object**, không chỉ xem người viết đã dùng `WeakReference` ở một field.

## 12. Phân biệt `Reference.get()`, `clear()`, `enqueue()` và `refersTo()`

| Method | Soft/Weak | Phantom | Điều cần nhớ |
| --- | --- | --- | --- |
| `get()` | Trả referent hoặc `null` sau clear | **Luôn `null`** | Không chứng minh object bị thu hồi hay GC đã chạy |
| `refersTo(obj)` | So identity của referent theo API | Cũng hỗ trợ, Java 16+ | Dùng được khi phantom.get() không cho lấy object |
| `clear()` | Chủ động clear referent | Chủ động clear referent | Không enqueue khi gọi `clear()` |
| `enqueue()` | Chủ động clear và enqueue nếu reference đã đăng ký/phù hợp | Tương tự theo API chung | Manual action, không chứng minh collector phát hiện trạng thái |
| `queue.poll()` | Lấy reference đã enqueue | Lấy reference đã enqueue | Không lấy lại referent |
| `queue.remove(timeout)` | Chờ notification có giới hạn | Chờ notification có giới hạn | Có thể timeout, không bảo đảm event xảy ra |

**Không tự viết vòng chờ vô hạn**:

```java
while (weak.get() != null) {
    System.gc();
}
```

Đoạn trên có thể không kết thúc, đốt CPU, gây GC pressure và vẫn không chứng minh gì về thời điểm thu hồi. Các kiểm thử GC nên tách khỏi unit tests đòi deterministic stdout và phải có timeouts/chấp nhận bất định rõ ràng.

## 13. Một đối tượng có thể “sống lại” sau finalization không?

Trong cơ chế finalization lịch sử, một finalizer có thể tạo strong reference mới tới object, gây **resurrection**. Điều này phức tạp hóa reachability và lifecycle; Java finalization bị deprecated từ Java 9 và deprecated for removal bởi JEP 421 trong JDK 18, vì nhiều lý do an toàn/hiệu năng.

Với Java 17:

- Đừng thiết kế code mới dựa trên `Object.finalize()` hay một thứ tự gọi finalizers tự giả định.
- Chấp nhận rằng GC/ref-processing semantics chịu ảnh hưởng các trạng thái vòng đời được JVMS/Javadoc mô tả.
- `PhantomReference.get()` luôn `null` nên không cung cấp cách resurrect referent.
- `Cleaner` và `AutoCloseable` đáng tin cậy hơn về thiết kế, trong đó **explicit close** mới cung cấp thời điểm rõ ràng cho tài nguyên quan trọng.
- Khi đọc tài liệu Java 8, thận trọng với mô tả `PhantomReference` có thể khác phiên bản Java 17 về chuyện clear/enqueue.

Nếu chương trình chứa legacy finalization, cần kiểm tra các đường strong-reference resurrection trước khi giải thích vì sao một object vẫn tồn tại hoặc vì sao queue notification chậm.

## 14. Chẩn đoán thực tế: memory leak hay GC hợp lệ?

### 14.1. Sự khác nhau giữa GC không chạy và object còn strong-reachable

Nếu `WeakReference.get()` vẫn trả object, có thể là:

- Object thực sự có **strong path** từ static cache, thread, event listener hoặc JNI global reference.
- Có **soft reference** khác đang giữ object ở mức softly reachable.
- GC chưa thực hiện xử lý weak refs trong điều kiện thích hợp.
- Một strong local đã được tạo bởi `weak.get()` đang giữ object trong lúc nó được dùng.
- Test tự giữ object bằng biến/lambda/log statement để kiểm tra identity và vô tình ngăn collection.

Đừng kết luận “WeakReference bị bug” chỉ vì sau một lần `System.gc()` vẫn thấy `get() != null`.

### 14.2. Khi `WeakHashMap` không giảm kích thước

Kiểm tra:

- **Values → keys** reference cycles xuất phát từ map root.
- Keys có nằm trong static collection khác không?
- Keys có là String literal/interned values hoặc các objects sống lâu khác không?
- Code có giữ iterator/list snapshot và references tạm không?
- Có thực sự cần weak keys, hay nghiệp vụ cần explicit removal/TTL?

Ngay cả khi Map entries biến mất, điều đó không chứng minh không còn leak ở object khác. Memory leak analysis phải xem **retained paths** trong heap dump.

### 14.3. Công cụ Java 17 thường dùng

```bash
# Xem phiên bản JVM:
java -version

# HotSpot heap class histogram tại thời điểm kiểm tra:
jcmd <pid> GC.class_histogram

# Khi được phép và môi trường phù hợp, tạo heap dump:
jcmd <pid> GC.heap_dump /path/to/heap.hprof

# Nhìn cờ VM thực tế đang dùng:
java -XX:+PrintFlagsFinal -version

# GC logging theo tag có sẵn trên bản HotSpot:
java -Xlog:gc*=info YourApp
```

Lưu ý:

- Heap dump/histogram có overhead lớn và có thể gây pause; chọn thời điểm và quyền truy cập phù hợp.
- Heap dump chứa object data **nhạy cảm**; không chia sẻ bừa.
- Không có một flag `-Xlog:weakreferencealways=true` chuẩn chung cho mọi JVM; xem các tags hỗ trợ của phiên bản VM thực tế nếu cần phân tích reference processing.
- `System.gc()` là request, không phải công cụ điều khiển lịch GC với deadline tuyệt đối.
- G1, ZGC, Shenandoah và các collectors/JDK releases có các chiến lược reference processing khác nhau; **public Javadoc semantics** vẫn là nguồn đáng dựa vào hơn một timing cụ thể của HotSpot.

## 15. Bảng chọn cơ chế theo bài toán

| Bài toán | Nên cân nhắc | Vì sao | Cần tránh |
| --- | --- | --- | --- |
| Dữ liệu nghiệp vụ đang dùng, bắt buộc còn tồn tại | **Strong reference** | Giữ object truy cập được khi cần | Đổi sang weak chỉ để “tiết kiệm RAM” |
| Cache tái tạo được, có thể mất khi thiếu memory | **SoftReference** hoặc cache có chính sách rõ | Soft cho GC cơ hội bỏ giá trị | Coi soft là TTL/eviction policy đáng tin |
| Map metadata đi theo vòng đời đối tượng key | **WeakHashMap** / weak keys | Không giữ keys chỉ vì metadata | Value giữ strong reference ngược tới key |
| Canonicalization không muốn giữ tất cả objects sống | **WeakReference** và bảng quản lý thích hợp | Canonical entries có thể bị bỏ | Trộn lẫn với `String.intern()` contract của JVM |
| Thông báo khi referent không còn accessible | **PhantomReference + ReferenceQueue** | Có tín hiệu cleanup mà không lấy lại object | `phantom.get()` hoặc action giữ strong referent |
| Cleanup tài nguyên native/file theo vòng đời | **AutoCloseable + try-with-resources**, có thể bổ sung Cleaner | Explicit close deterministic; Cleaner fallback | Đợi GC như chính sách đóng duy nhất |
| Thu hồi những native buffers do application quản lý | Explicit release, `Cleaner` khi phù hợp | Ownership rõ ràng | Trông GC tự `free` tùy tiện mọi native memory |
| Cache có TTL, LRU, metrics, max size | Bounded cache/explicit lifecycle | Có chính sách kiểm soát | Dùng soft refs như một cache framework đầy đủ |

Không có “loại reference tốt nhất”. Câu hỏi đầu tiên phải là **object cần sống vì lý do nghiệp vụ đến khi nào?** Sau đó mới chọn chính sách GC tương thích.

## 16. Các hiểu nhầm thường gặp

1. **“StrongReference là class trong `java.lang.ref`.”** Sai: strong reference là reference thông thường.
2. **“Có `WeakReference` trỏ tới object nghĩa là object sẽ bị GC ngay.”** Sai: strong/soft paths khác và GC timing quyết định.
3. **“Soft reference chỉ bị clear đúng lúc OOME.”** Sai: GC có thể xóa sớm tùy memory demand/policy.
4. **“Soft cache bảo đảm không bao giờ OOME.”** Sai: strong live data, native memory và nhiều nguyên nhân khác vẫn gây OOME.
5. **“WeakReference tự gọi `clear()` sau đúng N giây.”** Sai: không có thời gian cố định.
6. **“`System.gc()` chắc chắn clear hết weak refs trước khi trả về.”** Sai: không có timing guarantee như vậy.
7. **“`weak.get()` trả object thì cứ gọi lại bao nhiêu lần cũng an toàn.”** Sai: luôn giữ strong local trong lúc sử dụng.
8. **“`WeakHashMap` dùng weak cho cả keys và values.”** Sai: values thường là strong.
9. **“WeakHashMap luôn xóa key dù value trỏ ngược lại key.”** Sai: value có thể giữ strong path đến key.
10. **“`PhantomReference.get()` có lúc trả object trước GC.”** Sai: Java 17 luôn trả `null`.
11. **“Phantom reference giữ được resource để gọi `close()` khi GC tới.”** Sai: không lấy referent qua `get()`.
12. **“`ReferenceQueue` trả trực tiếp đối tượng đã thu hồi.”** Sai: queue chứa **reference objects**.
13. **“`clear()` và `enqueue()` là cùng một thao tác.”** Sai: clear riêng không enqueue.
14. **“Khi queue trống nghĩa là tất cả referents vẫn còn sống.”** Sai: có thể GC chưa enqueue, reference chưa đăng ký hoặc queue đã được đọc.
15. **“Không cần giữ reference wrapper vì queue tự giữ nó.”** Sai: phải đảm bảo reference object reachable.
16. **“Cleaner luôn chạy lúc JVM shutdown.”** Sai: không có guarantee.
17. **“Để lambda Cleaner capture `this` là tiện nhất.”** Sai: có thể giữ referent sống mãi.
18. **“Cleaner thay thế hoàn toàn `close()` và try-with-resources.”** Sai: cleanup do GC không có deadline.
19. **“Biến local hết scope nghĩa là resource luôn sống đến dấu ngoặc cuối.”** Sai: compiler/JIT liveness có thể kết thúc trước đó.
20. **“`reachabilityFence` là lệnh chạy GC.”** Sai: nó chỉ thiết lập strong-reachability đến điểm fence.
21. **“Dùng weak ref là cách sửa mọi memory leak.”** Sai: object graph có thể vẫn giữ strong paths khác.
22. **“JDK 8 và 17 có mọi chi tiết PhantomReference clearing giống nhau.”** Không đúng khi áp dụng các mô tả lịch sử; đọc docs đúng JDK.

## 17. Tự kiểm tra và đáp án

**Câu 1.** Nếu một object còn được tham chiếu qua một static field thông thường, một `WeakReference` trỏ tới nó có cho phép GC thu hồi object không?

**Đáp án:** Không chỉ vì weak wrapper. Static strong path còn sống khiến referent strongly reachable.

**Câu 2.** Có cả soft và weak refs cùng trỏ một object, nhưng không có strong path. Mức reachability là gì?

**Đáp án:** **Softly reachable**, vì soft mạnh hơn weak. GC có thể clear soft theo policy rồi xử lý trạng thái yếu hơn.

**Câu 3.** `SoftReference.get()` trả `null` nghĩa là OOME vừa xảy ra?

**Đáp án:** Không. Soft có thể bị clear trước OOME hoặc bị chương trình chủ động `clear()`.

**Câu 4.** `WeakReference.get()` có thể đang trả object, lần sau trả `null` không?

**Đáp án:** Có. Nếu không giữ strong reference tới referent giữa hai lần và GC xử lý, reference có thể bị clear.

**Câu 5.** Vì sao `WeakMapDemo` vẫn in `size=1` sau khi `key=null`?

**Đáp án:** Map giữ `Value` mạnh, `Value.owner` giữ key mạnh, nên weak key không phải đường sống duy nhất. `clear()` của map xóa entry chủ động.

**Câu 6.** `PhantomReference.get()` trả gì khi target còn mạnh reachable?

**Đáp án:** **`null`**, vì đó là contract cố định của `PhantomReference.get()` trong Java 17.

**Câu 7.** Tại sao phải giữ `PhantomReference` object trong một collection khi dùng `ReferenceQueue`?

**Đáp án:** Nếu wrapper reference object tự trở nên unreachable, chương trình có thể không nhận notification. Queue không tự quản lý strong registration cho mọi refs.

**Câu 8.** `Reference.clear()` có làm reference xuất hiện ngay trong queue không?

**Đáp án:** Không. `clear()` đơn lẻ không enqueue; `enqueue()` hoặc collector processing mới enqueue theo hợp đồng.

**Câu 9.** Trong `CleanerDemo`, vì sao stdout là deterministic mà không cần gọi `System.gc()`?

**Đáp án:** Vì try-with-resources gọi `Resource.close()`, và `close()` gọi `Cleanable.clean()` đồng bộ. Automatic GC cleanup chỉ là fallback.

**Câu 10.** Vì sao lambda cleanup `() -> closeNativeField()` có thể khiến Cleaner không bao giờ chạy tự động?

**Đáp án:** Nó thường capture `this` (owner), trong khi Cleaner giữ cleanup action mạnh, tạo strong path tới referent.

**Câu 11.** Khi native code dùng resource handle nhưng Java wrapper không còn được đọc, API nào có thể giúp duy trì strong reachability tới sau native call?

**Đáp án:** `Reference.reachabilityFence(wrapper)` đặt sau native operation, đúng nơi bảo đảm wrapper còn strongly reachable.

**Câu 12.** Dùng `WeakReference` có tự làm collection thread-safe không?

**Đáp án:** Không. Cấu trúc dữ liệu quản lý vẫn cần synchronization/concurrency policy riêng.

## 18. Tóm tắt bằng một sơ đồ

```text
Một object O trên heap
    ▲
    │
    ├── strong edge  → sống khi strong path còn
    │
    ├── soft edge    → GC có thể clear khi memory demand
    │
    ├── weak edge    → không giữ O sống sau khi hết strong/soft paths
    │
    └── phantom edge → chỉ thông báo lifecycle; get() luôn null

ReferenceQueue:
    Weak/Soft/Phantom ref ──(enqueue khi phù hợp)──► Queue
                                                        │
                                              poll()/remove()
                                                        │
                                              xử lý reference object
                                              KHÔNG lấy lại referent

Cleaner:
    Phantom/reference processing + cleanup action
      ├─ auto cleanup: không bảo đảm thời điểm
      └─ explicit clean(): có thể chạy đúng lúc close()

Reference.reachabilityFence:
    Giữ strong reachability đến vị trí gọi,
    không buộc GC hay thay thế đóng tài nguyên.
```

**Ghi nhớ:** Strong refs dành cho đối tượng còn đang dùng; Soft refs có thể làm cache phụ thuộc memory demand; Weak refs thích hợp cho metadata/canonical mappings không được phép giữ object sống; Phantom refs là tín hiệu sau khi object không còn truy cập thông thường, **không phải cửa sau để gọi method của object**. `ReferenceQueue` liên kết reference wrappers với một kênh thông báo, `Cleaner` cung cấp abstraction cleanup, còn `try-with-resources` mới là cách đáng tin cậy để đóng tài nguyên theo thời gian xác định. Luôn phân biệt **reachability của referent**, **lifetime của reference object**, **lifetime của tài nguyên ngoài heap** và **thời điểm GC thực thi**.

### Tài liệu tham khảo chuẩn

- [Java SE 17 — `java.lang.ref` package / Reachability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): các mức strong, soft, weak, phantom và notification.
- [Java SE 17 — `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): `get`, `clear`, `enqueue`, `refersTo`, `reachabilityFence`.
- [Java SE 17 — `SoftReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): memory demand và OOME caveat.
- [Java SE 17 — `WeakReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): clear/enqueue semantics.
- [Java SE 17 — `PhantomReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): `get() == null` và phantom reachability.
- [Java SE 17 — `ReferenceQueue` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): polling và blocking notification.
- [Java SE 17 — `Cleaner` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom-backed cleanup và rủi ro action capture.
- [Java SE 17 — `WeakHashMap` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values, cycles.
- [JLS Java SE 17 — Finalization of Class Instances (§12.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6).
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421).
