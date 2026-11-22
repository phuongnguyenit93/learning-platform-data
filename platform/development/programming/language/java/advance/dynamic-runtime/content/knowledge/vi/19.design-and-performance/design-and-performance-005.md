# 19.5 Sử dụng ClassValue và nhận diện tham chiếu giữ lớp hoặc bộ nạp lớp sống lâu

## 1. Bài toán: cache theo Class nhưng không giữ plugin/class loader mãi mãi

Khi viết reflection framework, serializer, dependency injector, ORM, dynamic dispatcher hoặc runtime biên dịch class lúc chạy, chương trình thường phải tính metadata một lần rồi tái sử dụng cho mỗi **`Class<?>`**:

- Danh sách field/method đã phân tích, kế hoạch serialize/deserialize.
- Các `MethodHandle` và `VarHandle` đã lookup.
- Bảng dispatch, accessor, converter hoặc schema.
- Cấu hình riêng cho một kiểu Java.

Cách trực giác là dùng một cache tĩnh:

```java
// Minh họa phản mẫu: biến global sống lâu hơn plugin class loader.
static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();
```

Nếu map này nằm trong class của **application loader** tồn tại suốt vòng đời tiến trình, mỗi `Class<?>` làm **key mạnh** có thể giữ lại defining class loader. Với hệ thống reload plugin, sau mỗi lần triển khai lại ta có một loader mới, dù cùng tên class. Cache global cũ giữ lại các `Class<?>` phiên bản cũ; số loaders/classes và metaspace có thể tiếp tục tăng.

Java cung cấp **`java.lang.ClassValue<T>`** để gắn giá trị được tính lười (lazy) với từng đối tượng `Class<?>`, mà không cần duy trì một map global chứa strong keys đến mọi class. Đây là công cụ đặc biệt hữu ích khi **class có thể được unload**.

**Cốt lõi bài học:** phải hiểu cả **cơ chế ClassValue** lẫn **đường tham chiếu giữ class/class loader sống**. Chỉ chuyển từ `Map<Class<?>,T>` sang `ClassValue<T>` không chữa được mọi memory leak; một thread, static singleton, listener hay value giữ tham chiếu ở nơi khác vẫn có thể ngăn unloading.

### Mục tiêu

Sau bài này bạn sẽ:

1. Dùng `ClassValue.computeValue`, `get`, `remove`; phân biệt lazy initialization, per-class identity, invalidation và thread-safety.
2. Hiểu tại sao `computeValue` **có thể chạy nhiều lần đồng thời** dù chỉ một kết quả được cài đặt cho cùng class, và vì sao không nên đặt side effect không lặp được trong đó.
3. So sánh strong `Map<Class<?>, ...>`, `WeakHashMap<Class<?>, ...>` và `ClassValue<T>` về khả năng giữ loader.
4. Nhận diện chuỗi **GC root → object mạnh → Class/instance/MethodHandle/ClassLoader → defining loader → metadata lớp**.
5. Chẩn đoán các bẫy phổ biến: thread context class loader, `ThreadLocal`, executor thread, callback/listener, static registry, class-keyed cache, method handles và cross-loader values.
6. Đọc được dấu hiệu bằng `jcmd VM.classloader_stats`, `VM.metaspace`, `GC.class_histogram`, heap dump, JFR/class unloading logs; không khẳng định unload chỉ vì `System.gc()`.
7. Thiết kế lifecycle rõ ràng khi unload/redeploy plugin hoặc sinh nhiều class động.

Bài dùng Java **17+** và ba ví dụ độc lập đã kiểm thử với `javac --release 17`.

## 2. Class identity, class loader và lý do rò rỉ liên quan

### 2.1. Một tên binary có thể đại diện nhiều Class objects

Với **named class**, JVM phân biệt runtime type bằng **binary name và defining class loader**. Ví dụ hai child loaders `L1` và `L2` cùng định nghĩa bytes có binary name `plugin.Widget`:

```text
Class<?> A = Class.forName("plugin.Widget", false, L1);
Class<?> B = Class.forName("plugin.Widget", false, L2);

A.getName().equals(B.getName())  -> true
A == B                           -> false
A.getClassLoader() == L1         -> true
B.getClassLoader() == L2         -> true
```

Đây là **sơ đồ minh họa**, không phải file Java độc lập. Hai class này có thể mang cùng tên nhưng khác class identity; chúng có metadata, static state, phương thức và quyền truy cập gắn với ngữ cảnh loader riêng.

Một cache key bằng **chuỗi tên class** có thể trộn lẫn hai version khác nhau và trả metadata sai. Một cache key bằng `Class<?>` giải quyết được tính đúng type, nhưng nếu cache ấy thuộc một root sống rất lâu và giữ **strong key**, nó lại có thể ngăn old loader được giải phóng.

### 2.2. GC root và đường giữ lớp sống

Một root như static field trong application class, live thread, JNI reference hoặc biến stack của thread đang chạy có thể gián tiếp giữ class loader:

```text
GC root: static field của application loader
        |
        v
ConcurrentHashMap<Class<?>, Metadata>
        |
        +--- strong key ---> Class<plugin.Widget> (loader L1)
                              |
                              v
                         defining loader L1
                              |
                              v
                       lớp/metadata của plugin
```

**Đây là retention path thực sự**, không chỉ là hiện tượng “Java cache chiếm bộ nhớ”. Class objects có liên hệ với defining class loader; khi một class loader còn reachable theo cơ chế JVM, các class mà nó định nghĩa thường không thể unload độc lập như mong đợi đối với một loader thông thường.

Lưu ý: chỉ vẽ chiều `Class → ClassLoader` là chưa đủ để phân tích mọi implementation; metadata/objects/class-loader data có cơ chế JVM nội bộ. Nhưng để **tìm root trong heap dump**, chuỗi từ static map hoặc thread đến một class/plugin loader là bằng chứng rất hữu ích.

### 2.3. Unloading khác GC của instance

- **Heap object GC:** một object instance không còn reachable có thể được thu hồi.
- **Class unloading:** JVM được phép thu hồi metadata của class khi điều kiện reachability và loading context thỏa mãn.
- **Class-loader unloading:** loader và các class/metadata liên quan có thể được thu hồi khi không còn các strong references giữ chúng, trừ các điều kiện nội bộ phù hợp.

Một plugin có thể không còn instance nghiệp vụ nào nhưng vẫn **không unload được** nếu còn `Class<?>` trong cache, một live thread do plugin tạo, `Thread.contextClassLoader`, method handle, callback hoặc thread-local value tham chiếu tới plugin. Vì vậy, nhìn heap instance count giảm **không đủ** để xác nhận giải phóng class loader/metaspace.

**Không có hợp đồng rằng gọi `System.gc()` sẽ unload class ngay**; runtime có thể bỏ qua yêu cầu GC hoặc chọn thời điểm khác. Chỉ số metaspace chưa giảm sau một lần GC cũng **không tự chứng minh** leak, vì JVM có thể giữ vùng đã commit để tái sử dụng.

## 3. ClassValue<T> là gì?

`ClassValue<T>` là lớp abstract có từ Java 7, hỗ trợ **gắn một giá trị T với mỗi đối tượng Class** theo cách lazy. Bạn định nghĩa cách tính qua:

```java
ClassValue<Metadata> metadata = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return analyze(type);
    }
};
```

Đoạn này là **minh họa**, giả định `Metadata` và `analyze(Class<?>)` đã được định nghĩa. Mỗi khi cần metadata cho một class:

```java
Metadata info = metadata.get(SomeClass.class);
```

Về khái niệm, ta muốn:

```text
ClassValue<Metadata> METADATA
    get(Class A) ---> Metadata cho chính A
    get(Class B) ---> Metadata cho chính B
    get(Class A) ---> tái sử dụng Metadata đã gắn với A
```

Nhưng quan trọng là ta **không** tự đưa tất cả Class keys vào một `ConcurrentHashMap` global. API quản lý association trên mỗi `Class<?>`, phù hợp với các hệ thống có lifecycle classloader thay đổi.

### 3.1. Ba phương thức thiết yếu

| Phương thức | Ý nghĩa | Hành vi cần lưu ý |
| --- | --- | --- |
| `protected T computeValue(Class<?> type)` | Cách tính metadata khi chưa có association phù hợp. | Có thể chạy nhiều lần do race hoặc sau `remove`; exception không ghi value mới. |
| `T get(Class<?> type)` | Đọc value tương ứng với class; tính lazy nếu cần. | Cài đặt value **nguyên tử**; nhiều thread có thể tính nhưng một value thắng và được trả về. |
| `void remove(Class<?> type)` | Gỡ association của ClassValue này với **một class**. | Lần get sau có thể tính lại; cần cân nhắc race với get khác. |

`get(null)` và `remove(null)` ném `NullPointerException`. `type` có thể là **interface, array, primitive type** (ví dụ `int.class`) hoặc `void.class`, không chỉ các application classes thông thường.

Mỗi **đối tượng `ClassValue`** tạo một không gian association riêng. Hai ClassValue khác nhau có thể tính hai kinds metadata trên cùng `Class<?>` mà không chồng lẫn dữ liệu.

### 3.2. ClassValue không phải một Map tổng quát

Không có API public `put(class, value)`, `size()`, `entrySet()` hay `clearAll()`. ClassValue sinh value bằng `computeValue` và invalidates từng class qua `remove`. Nó tối ưu một trường hợp cụ thể: **memoization/caching per Class**.

Vì thế không chọn ClassValue khi nghiệp vụ cần liệt kê **tất cả classes từng xuất hiện**, thống kê global key count hoặc thực hiện atomic operations trên toàn bộ map. Với mục tiêu ấy cần registry riêng có lifecycle và retention policy rõ ràng — nhưng hãy tránh strong Class keys lâu dài nếu classes đến từ short-lived loaders.

## 4. Lazy initialization, value identity và invalidate

Khi `ClassValue.get(A.class)` lần đầu, `computeValue(A.class)` được gọi để tính value. Nếu thành công, API **cài đặt nguyên tử** association. Những lần `get(A.class)` sau thường trả lại **chính object T đã được cài** cho đến khi có `remove(A.class)`. Nếu `T` immutable thì pattern này đặc biệt dễ sử dụng.

`remove(A.class)` không sửa nội dung của value object đã được trả về trước đó. Nó chỉ bỏ association hiện hành trong ClassValue; code giữ một reference cũ vẫn có thể dùng value cũ. Lần `get(A.class)` sau sẽ tính một value khác (nếu `computeValue` tạo mới).

**Không** dùng `remove` như một phương thức đóng resources hoặc thu hồi các MethodHandles đang được người khác giữ: nó không gọi `close()` trên value, không xóa bản sao metadata ở map khác và không tự ngăn những thread đã lấy value trước đó tiếp tục sử dụng nó.

### 4.1. Ví dụ Java 17 số 1 — cache theo class và remove

Tạo file **`ClassValueBasicsDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueBasicsDemo {
    static final class Alpha { }
    static final class Beta { }

    record Metadata(String name, int generation) { }

    static final AtomicInteger BUILDS = new AtomicInteger();

    static final ClassValue<Metadata> INFO = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            return new Metadata(
                    type.getSimpleName(),
                    BUILDS.incrementAndGet());
        }
    };

    public static void main(String[] args) {
        Metadata first = INFO.get(Alpha.class);
        Metadata again = INFO.get(Alpha.class);

        System.out.println("first name: " + first.name());
        System.out.println("same value: " + (first == again));
        System.out.println("builds after repeated get: "
                + BUILDS.get());

        Metadata beta = INFO.get(Beta.class);
        System.out.println("beta name: " + beta.name());
        System.out.println("builds for two classes: "
                + BUILDS.get());

        INFO.remove(Alpha.class);
        Metadata refreshed = INFO.get(Alpha.class);
        System.out.println("after remove new instance: "
                + (refreshed != first));
        System.out.println("refreshed generation: "
                + refreshed.generation());
        System.out.println("beta unchanged: "
                + (INFO.get(Beta.class) == beta));

        try {
            INFO.get(null);
        } catch (NullPointerException expected) {
            System.out.println("null class: rejected");
        }

        System.out.println("primitive name: "
                + INFO.get(int.class).name());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ClassValueBasicsDemo.java
java ClassValueBasicsDemo
```

Stdout đã kiểm chứng:

```text
first name: Alpha
same value: true
builds after repeated get: 1
beta name: Beta
builds for two classes: 2
after remove new instance: true
refreshed generation: 3
beta unchanged: true
null class: rejected
primitive name: int
```

**Phân tích:**

1. Với lần get đầu của Alpha, `computeValue` tạo `Metadata("Alpha",1)`. Get lại không tính mới nên `first == again` trả true.
2. Beta có Class object riêng, dẫn đến một association riêng và lần tính thứ hai.
3. `INFO.remove(Alpha.class)` chỉ invalidate association cho Alpha. Lần get tiếp tạo Metadata mới (generation 3); Beta vẫn trả đúng object cũ.
4. `get(null)` báo `NullPointerException`; `int.class` cũng là key hợp lệ và có simple name `int`.
5. Output có số thứ tự cụ thể vì **ví dụ này chạy tuần tự trên một thread**. Không tổng quát hóa thành “computeValue luôn được gọi chính xác một lần trên mỗi Class” khi có concurrency.

### 4.2. Dùng nhiều ClassValue cho một Class

Có thể có một `ClassValue<SerializationPlan>` và một `ClassValue<DispatchTable>` độc lập cho cùng `Order.class`. Điều đó tốt hơn gom tất cả trường metadata vào một global Map rồi phải quản lý nhiều loại value trong cùng entry.

Với metadata phụ thuộc vào **cấu hình thay đổi theo thời gian**, ClassValue chỉ gắn value với `Class<?>`; nó **không tự biết** cấu hình bên ngoài đã đổi. Khi có sự kiện thay đổi config, cần invalidate association tương ứng bằng `remove(type)` (hoặc thiết kế versioning riêng), và quyết định những caller đang giữ metadata cũ sẽ xử lý thế nào.

## 5. Concurrency: computeValue có thể chạy nhiều lần

Theo Javadoc Java 17, khi nhiều thread đồng thời gọi `get(C)` trong lúc chưa có value:

- **Có thể có nhiều thread cùng gọi `computeValue(C)`**.
- Việc **install association** được thực hiện nguyên tử.
- Một computed value được chọn và trả về cho các competing readers; các value còn lại **có thể bị bỏ đi**.
- Khi không có `remove`, reader về sau đọc association đã được cài.
- Nếu `computeValue` ném exception trong lần get tương ứng, không có value được ghi vì lần tính lỗi ấy; các lần get khác vẫn có thể tính lại.

Do đó **không đặt side effect cần exactly-once** trong `computeValue`:

```java
// Phản mẫu minh họa trong computeValue:
// chargeCustomerCard(); // không được giả định chỉ chạy một lần!
// registerGlobalListener(); // có thể đăng ký lặp khi race
// startThread(); // có thể tạo thread "thừa" giữ class loader
```

Những việc như gọi API tính phí, đăng ký callback, mở native resource hoặc tạo thread cần lifecycle/transaction riêng. `computeValue` nên là phép dựng **metadata bất biến, có thể lặp**, không tác động đến trạng thái bên ngoài hoặc có cơ chế loại bỏ kết quả thừa nếu thật sự cần.

Đừng đánh đồng **atomic installation** với **single execution** của computation.

### 5.1. Ví dụ Java 17 số 2 — nhiều reader cùng nhận một value

Tạo file **`ClassValueConcurrentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueConcurrentDemo {
    static final class Target { }

    static final class Metadata {
        final int sequence;
        Metadata(int sequence) {
            this.sequence = sequence;
        }
    }

    static final AtomicInteger COMPUTATIONS = new AtomicInteger();

    static final ClassValue<Metadata> CACHE = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            int id = COMPUTATIONS.incrementAndGet();
            try {
                Thread.sleep(30);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            return new Metadata(id);
        }
    };

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Metadata>> futures = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    return CACHE.get(Target.class);
                }));
            }

            start.countDown();
            Metadata installed = futures.get(0).get();
            boolean allSame = true;

            for (Future<Metadata> future : futures) {
                allSame &= (future.get() == installed);
            }

            System.out.println("readers same published object: "
                    + allSame);
            System.out.println("subsequent get agrees: "
                    + (CACHE.get(Target.class) == installed));
            System.out.println("compute called at least once: "
                    + (COMPUTATIONS.get() >= 1));
            System.out.println("no remove occurred: true");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ClassValueConcurrentDemo.java
java ClassValueConcurrentDemo
```

Stdout đã kiểm chứng:

```text
readers same published object: true
subsequent get agrees: true
compute called at least once: true
no remove occurred: true
```

**Điểm cần lưu ý:**

- `CountDownLatch` giúp các thread bắt đầu gần nhau, còn `Thread.sleep(30)` là thao tác minh họa nhằm tăng cơ hội các computation chồng lấp; **không** phải một đồng bộ hóa bắt buộc của ClassValue và không bảo đảm số lần tính nào.
- Chương trình **không in số lần computeValue thực tế**, vì scheduler/JVM quyết định điều đó. Với ClassValue Java 17, nhiều computation cùng tranh cài value là trường hợp được phép.
- Không có `remove` đồng thời nên các `get(Target.class)` nhận cùng **installed object** theo contract.
- `ExecutorService` được shutdown trong `finally` để demo không để thread pool sống lâu ngoài ý muốn. Trong plugin framework, thread pool do plugin tạo nhưng không shutdown là một nguồn loader retention rất phổ biến.

### 5.2. remove trong cuộc đua với get

Giả sử `T1` bắt đầu `computeValue(C)` nhưng tạm dừng. `T2` tính và cài value `V1`, rồi một thread gọi `remove(C)`. Sau đó `T1` hoàn thành tính một value cũ `V0`. ClassValue phải tránh việc `V0` được cài lại như một kết quả hợp lệ của association sau lần remove mới nhất.

Javadoc Java 17 mô tả state/version và cơ chế **discard + retry** khi state đã đổi, nhằm tránh giá trị tính trong trạng thái cũ được ghi đè lên trạng thái mới. Không có nghĩa việc đọc metadata và trạng thái nghiệp vụ bên ngoài trở thành một transaction; `computeValue` vẫn phải quan sát/configure các dữ liệu phụ thuộc bằng synchronization thích hợp.

**Không gọi `remove` trong `computeValue` rồi giả định thứ tự đệ quy sẽ luôn được xử lý như ý.** Nếu computation làm `get` đệ quy trên cùng `ClassValue/Class` mà không có điểm dừng, nó có thể gây recursion vô hạn/stack overflow. Thiết kế graph tính metadata để tránh circular dependency hoặc có chiến lược khởi tạo rõ ràng.

## 6. Vì sao ClassValue thường phù hợp hơn strong static Map<Class<?>,T>?

### 6.1. Mẫu dễ giữ loader

Ví dụ một singleton của host trong application loader:

```java
static final ConcurrentMap<Class<?>, Metadata> GLOBAL =
        new ConcurrentHashMap<>();

Metadata metaFor(Class<?> type) {
    return GLOBAL.computeIfAbsent(type, this::analyze);
}
```

Đoạn này là **mã minh họa**, giả định có type `Metadata` và method `analyze`. Nếu key là một class của plugin loader L1, map của host giữ strong reference tới `Class<?>` đó, dù plugin manager đã ngừng dùng L1. Lần reload tạo loader L2 + class cùng tên, map có thêm entry mới vì `Class<?>` khác identity.

Nếu dùng key dạng `String` thì tránh giữ `Class<?>` bằng key, nhưng lại có thể **trộn metadata giữa hai phiên bản cùng tên**; còn value như `MethodHandle`/`Method` vẫn có thể giữ class/plugin loader. Chỉ đổi kiểu key không tự đảm bảo memory safety hoặc type correctness.

### 6.2. Mẫu ClassValue

```java
static final ClassValue<Metadata> PER_CLASS = new ClassValue<>() {
    @Override protected Metadata computeValue(Class<?> type) {
        return analyze(type);
    }
};

Metadata metaFor(Class<?> type) {
    return PER_CLASS.get(type);
}
```

Đây cũng là **trích đoạn minh họa**. ClassValue gắn association với từng Class object, thay vì yêu cầu host giữ một Map mạnh toàn cục từ Class tới metadata. Nếu những references còn lại đến loader/class đã hết, ClassValue do host giữ không tự tạo ra cùng một **strong-key registry path** như ví dụ Map.

**Không kết luận tuyệt đối “dùng ClassValue thì không bao giờ có memory leak”**:

- Nếu một đối tượng global vẫn giữ `Class<?>`/`MethodHandle`/instance của plugin, loader vẫn có thể sống.
- Nếu chính object `ClassValue` hoặc subclass của nó do host lưu trong static field có một captured field trỏ thẳng đến plugin loader, bạn vẫn tạo đường retention khác.
- Value có thể giữ file handle, thread, timer, listener, connection hoặc MethodHandle; ClassValue không tự gọi `close()`, `removeListener()` hay shutdown executor.
- Nếu code mang metadata từ ClassValue rồi lưu vào một global list/map khác, global structure đó có thể trở thành root giữ plugin class.
- Khi class hiện còn reachable, value được ClassValue gắn với class cũng có thể sống; đây là **caching có chủ đích**, không mặc nhiên là leak.

Như vậy, lợi ích chính là **đúng kiểu theo Class identity và tránh strong-key global cache**. Không phải bộ thu gom tài nguyên hoặc lifecycle manager cho plugin.

## 7. WeakHashMap không phải giải pháp tự động

Một lựa chọn thường được đề xuất:

```java
static final Map<Class<?>, Metadata> CACHE =
        new WeakHashMap<>();
```

`WeakHashMap` dùng **weak keys**, nhưng **values được giữ mạnh**. Nếu value hoặc một object mà value trỏ tới lại **tham chiếu ngược về key `Class<?>`**, chuỗi từ root `WeakHashMap` qua strong value quay lại Class key vẫn tồn tại:

```text
GC root --> WeakHashMap
              |
              +-- strong VALUE --> Metadata
                                     |
                                     v
                                Class<plugin.Widget>  <-- weak KEY
                                     |
                                     v
                                 loader L1
```

Vì key vẫn reachable qua **value**, weak-key entry không bị dọn chỉ nhờ việc key trong map là weak. Tình huống này dễ gặp nếu `Metadata` chứa:

- `Class<?> targetClass`;
- `java.lang.reflect.Method` / `Field` / `Constructor` khai báo trong plugin class;
- `MethodHandle`/`MethodType` có tham số/return/declaring class của plugin;
- Một `ClassLoader`, object instance hoặc callback của plugin.

**Hệ quả:** `WeakHashMap<Class<?>, MethodHandle>` **có thể vẫn leak**, vì value MethodHandle có khả năng giữ Class/loader thông qua target và type. Phải kiểm tra **toàn bộ object graph** của value chứ không chỉ loại map.

Ngoài ra `WeakHashMap` không thread-safe theo mặc định. Chỉ bọc bằng synchronization không chữa được vòng tham chiếu `value → key`. Một số kiến trúc dùng weak references ở cả key/value hoặc reference queues, nhưng cần thiết kế phức tạp hơn và vẫn phải xử lý lifecycle của external resources.

## 8. Ví dụ Java 17 số 3 — hai loaders, ClassValue và strong/weak-key trap

Ví dụ này thực sự tạo **hai Class objects mang cùng binary name** từ bytes giống nhau, trong hai defining loaders khác nhau. Sau đó nó chỉ ra đường tham chiếu của global map và một bẫy weak-key value.

Tách compilation output của plugin khỏi classpath host là **bắt buộc** trong demo: nếu parent application class loader đã nhìn thấy `plugin.Widget`, parent-first delegation có thể trả class ở parent thay vì class mới do child loader định nghĩa.

### 8.1. Tệp `plugin/Widget.java`

```java
package plugin;

public class Widget {
    public String message() {
        return "ready";
    }
}
```

### 8.2. Tệp `RetentionGraphDemo.java`

```java
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class RetentionGraphDemo {
    private static final String NAME = "plugin.Widget";

    record Meta(String typeName, int methods) { }
    record Holder(Class<?> clazz) { }

    static final Map<Class<?>, Meta> GLOBAL = new HashMap<>();
    static final Map<Class<?>, Holder> WEAK_KEYS = new WeakHashMap<>();

    static final ClassValue<Meta> PER_CLASS = new ClassValue<>() {
        @Override
        protected Meta computeValue(Class<?> type) {
            return new Meta(type.getName(),
                    type.getDeclaredMethods().length);
        }
    };

    static final class BytesLoader extends ClassLoader {
        private final byte[] bytes;

        BytesLoader(ClassLoader parent, byte[] bytes) {
            super(parent);
            this.bytes = bytes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));

        Class<?> first = Class.forName(
                NAME, false,
                new BytesLoader(
                        RetentionGraphDemo.class.getClassLoader(), bytes));

        Class<?> second = Class.forName(
                NAME, false,
                new BytesLoader(
                        RetentionGraphDemo.class.getClassLoader(), bytes));

        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("different Class objects: "
                + (first != second));
        System.out.println("different defining loaders: "
                + (first.getClassLoader() != second.getClassLoader()));

        System.out.println("ClassValue stable per Class: "
                + (PER_CLASS.get(first) == PER_CLASS.get(first)));
        System.out.println("ClassValue independent per loader: "
                + (PER_CLASS.get(first) != PER_CLASS.get(second)));

        WeakReference<ClassLoader> probe =
                new WeakReference<>(first.getClassLoader());

        GLOBAL.put(first, PER_CLASS.get(first));
        System.out.println("global cache holds loader: "
                + (GLOBAL.keySet().iterator().next()
                        .getClassLoader() == probe.get()));

        WEAK_KEYS.put(first, new Holder(first));
        System.out.println("WeakHashMap value points to key: "
                + (WEAK_KEYS.get(first).clazz() == first));

        GLOBAL.clear();
        WEAK_KEYS.clear();
        System.out.println("explicit registries cleared: "
                + (GLOBAL.isEmpty() && WEAK_KEYS.isEmpty()));
        System.out.println("GC outcome tested: false");
    }
}
```

### 8.3. Biên dịch và chạy đúng classpath

Từ thư mục gốc chứa hai file trên:

```bash
javac -encoding UTF-8 --release 17 -d plugin-out plugin/Widget.java
javac -encoding UTF-8 --release 17 -d host-out RetentionGraphDemo.java
java -cp host-out RetentionGraphDemo plugin-out/plugin/Widget.class
```

Stdout đã kiểm chứng:

```text
same binary name: true
different Class objects: true
different defining loaders: true
ClassValue stable per Class: true
ClassValue independent per loader: true
global cache holds loader: true
WeakHashMap value points to key: true
explicit registries cleared: true
GC outcome tested: false
```

**Những điều chương trình này chứng minh:**

1. Có thể định nghĩa hai class cùng binary name từ một file bytes bằng **hai child loaders khác nhau**. `Class<?>` của chúng khác identity.
2. `PER_CLASS.get(first)` và `PER_CLASS.get(second)` trả hai `Meta` độc lập; cùng class thì trả cùng object đã cache.
3. `GLOBAL.put(first, ...)` đặt một **strong key** là Class của loader thứ nhất vào static map của host. Lúc entry tồn tại, có đường mạnh từ static cache tới Class rồi tới loader.
4. `WeakReference<ClassLoader> probe` chỉ là quan sát phụ. So sánh `GLOBAL.keySet().iterator().next().getClassLoader() == probe.get()` chứng minh **cache đang giữ đường tới loader**, không cần ép GC hoặc đo thời gian.
5. `WEAK_KEYS.put(first, new Holder(first))` tạo value trỏ ngược về Class key. Đây là lý do **weak key không đủ** nếu value giữ key.
6. Hai registry được `clear()` ở cuối; chương trình **không assert loader đã bị thu hồi** vì các local variables `first`, `second`, `probe` và các trạng thái JVM khác vẫn có thể còn tham chiếu. Ngay cả sau khi local references hết scope, việc unload vẫn phụ thuộc GC/JVM.

### 8.4. Khác biệt giữa cleanup và chứng minh unload

`GLOBAL.clear()` là một thao tác cleanup hữu ích: nó bỏ **đường giữ mạnh của registry đó**. Nhưng chỉ một đường được bỏ chưa có nghĩa đã loại bỏ tất cả đường giữ từ GC roots khác. Bạn phải kiểm tra thread context class loader, callbacks, executors, ThreadLocal, registries và các MethodHandles còn được giữ.

Không nên thêm:

```java
// KHÔNG phải phép chứng minh unload:
System.gc();
// assert weakReference.get() == null;
```

Một lượt `System.gc()` không phải thời điểm unload đã được hứa hẹn. Nếu cần test loader leak, hãy thiết kế phép kiểm thử có baseline, vòng đời rõ ràng, reference probes và kiểm tra xác suất trong thời gian hữu hạn **như diagnostic**, nhưng không biến một kết quả GC không ổn định thành điều kiện correctness tất định.

## 9. Nhận diện những reference thực sự giữ loader sống

Không phải mọi leak đều nằm trong `Map<Class<?>,...>`. Dưới đây là những đường retention thường gặp trong runtime Java có hot reload:

| Nguồn giữ mạnh sống lâu | Đường tham chiếu đến plugin | Cách xử lý |
| --- | --- | --- |
| Static global map của host | Map key `Class<?>` hoặc value chứa `MethodHandle`/instance thuộc plugin. | Ưu tiên `ClassValue` cho metadata per Class; dùng cleanup registry khi unload. |
| `Thread.contextClassLoader` | Thread còn sống → TCCL → plugin loader. | Khôi phục TCCL ban đầu trong `finally`, tránh dùng plugin loader cho long-lived worker threads. |
| `ThreadLocalMap` của pool thread | Live thread → ThreadLocal value → plugin object/Class. | Gọi `ThreadLocal.remove()` ở đúng thread trong `finally`; dọn worker tasks. |
| Executor/Timer/Scheduled task | Live thread/queue → `Runnable`/`Callable`/lambda của plugin → class/loader. | Cancel tasks, shutdown executor, await termination, clear queues. |
| Listener/event bus | Host singleton → listener do plugin đăng ký → plugin instance/loader. | `unsubscribe`/unregister trong lifecycle stop. |
| JDBC DriverManager, logging bridge, MBeans/JMX | Registry toàn cục giữ callback/driver/class của plugin. | Deregister đúng API, ngừng services tại unload. |
| Static cache của thư viện thứ ba | Reflection/serializer metadata hoặc MethodHandles vẫn có plugin type. | Dùng API cache clear/invalidate của thư viện; kiểm tra scope của cache. |
| Method/Field/Constructor/MethodType/MethodHandle/CallSite | Object metadata/handle có thể chứa Class, target hoặc type của plugin. | Bỏ các references hoặc dùng cache gắn lifecycle; đừng chỉ xóa key rồi giữ value elsewhere. |
| `Class<?>`/instance trong public singleton | Host service giữ một object callback thực tế của plugin. | Tách lifecycle, release callback/instance khi plugin tắt. |
| Native/JNI/global reference | Native code tiếp tục giữ object/Class. | Giải phóng bằng giao thức native tương ứng. |

**Dòng quan trọng nhất khi đọc heap dump:** hãy đi từ object hoặc loader nghi ngờ đến **Path to GC Roots**, xem **đường strong reference cụ thể**, thay vì suy ra “ClassValue leak” chỉ từ việc hệ thống có ClassValue.

### 9.1. Thread context class loader (TCCL)

Một thread của host tồn tại xuyên nhiều lần reload có thể giữ plugin loader dù mọi static cache đã clear:

```java
// Đoạn minh họa khi có pluginLoader và Runnable action.
Thread worker = Thread.currentThread();
ClassLoader previous = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    action.run();
} finally {
    worker.setContextClassLoader(previous);
}
```

Điểm mấu chốt là **`finally`**. Nếu thiếu restoration, long-lived thread của pool có thể giữ loader của phiên bản plugin cũ vô thời hạn. Nếu `action` tạo thread mới, thread con có thể **kế thừa TCCL** và tiếp tục giữ loader; cần quản lý việc tạo thread và lifecycle riêng.

Việc khôi phục TCCL chỉ xử lý một đường giữ. Nếu `action` đã lưu một plugin instance vào static map host hoặc một ThreadLocal khác thì loader vẫn bị giữ.

### 9.2. ThreadLocal: weak key không giải quyết strong value

Bên trong `ThreadLocalMap`, key `ThreadLocal<?>` có cơ chế weak reference, nhưng **value** được giữ mạnh cho tới khi slot được dọn. Với long-lived threads, một value thuộc plugin có thể tồn tại lâu ngay cả khi key ThreadLocal không còn reachable.

Ví dụ một thread pool xử lý request bằng plugin object, lưu nó trong ThreadLocal rồi quên `remove()`, pool thread có thể tiếp tục giữ instance/class loader đến nhiều đợt deploy sau. Kết cấu an toàn là:

```java
// Trích đoạn với ThreadLocal<RequestContext> context:
context.set(requestContext);
try {
    processRequest();
} finally {
    context.remove();
}
```

Cả `requestContext` và `processRequest()` đều được giả định đã định nghĩa trong ứng dụng. Gọi `remove` trong **đúng thread** đã `set`; việc thread khác xóa ThreadLocal của nó không giải quyết entry nằm trên worker thread cũ.

### 9.3. MethodHandle và dynamic runtime caches

Một cache kiểu `ConcurrentMap<String, MethodHandle>` có thể trông vô hại vì key chỉ là String. Nhưng value là MethodHandle liên kết đến method của plugin hoặc có `MethodType` chứa tham số/return type từ plugin. Như vậy host singleton → MethodHandle → class/plugin loader vẫn có thể là đường mạnh.

Tương tự, một `MutableCallSite`/`VolatileCallSite` được host giữ có thể đang trỏ tới target mới hoặc cũ là MethodHandle của plugin. Ngay cả sau khi thay target, nếu còn snapshot `getTarget()` cũ lưu trong list/diagnostic callback, loader cũ vẫn được giữ. Đừng suy rằng đổi key của map là đủ: phải xác minh **giá trị và toàn bộ đồ thị reference**.

## 10. ClassValue không quản lý lifecycle của resources thay bạn

`ClassValue.remove(type)` làm mất association để lần get sau có thể tính lại. Nó **không** gọi `close()`, shutdown thread, unsubscribe listener, flush database connection hay xóa class references ở những registries khác.

Vì thế nên tách hai trách nhiệm:

**Metadata cache thuần:**

```java
record AccessPlan(String typeName, int methodCount) { }

static final ClassValue<AccessPlan> ACCESS_PLANS = new ClassValue<>() {
    @Override protected AccessPlan computeValue(Class<?> type) {
        return new AccessPlan(type.getName(),
                type.getDeclaredMethods().length);
    }
};
```

Nếu value bất biến và không sở hữu external resources, ClassValue là lựa chọn tự nhiên.

**Resource owner có vòng đời:**

```java
// Đây là sơ đồ API minh họa, không phải class độc lập:
plugin.start();             // tạo subscriptions/threads/connections
try {
    usePlugin(plugin);
} finally {
    plugin.stop();          // phải đóng / hủy đăng ký tại owner
    // nếu giữ Class<?> đã biết và muốn invalidate metadata:
    // ACCESS_PLANS.remove(pluginClass);
}
```

Với resources có `close`, cần giữ owner rõ ràng. Không trông chờ value “tự close” khi class được unload hoặc khi `ClassValue` bị GC.

**Vì sao?** `ClassValue` quản lý association metadata. GC thu hồi bộ nhớ khi không còn reachable, nhưng việc đóng network socket/file/JDBC session hoặc hủy subscription là **quy trình ứng dụng có thứ tự**, không thể suy ra chỉ từ reachability.

## 11. Khi nào nên dùng ClassValue và khi nào không?

| Nhu cầu | Lựa chọn và lý do |
| --- | --- |
| Metadata chỉ phụ thuộc `Class<?>`, lặp lại nhiều lần | **ClassValue**: per-class lazy value, không dùng strong global Class key registry. |
| Lookup reflection/MethodHandle theo class của plugin | **ClassValue** có thể thích hợp; value có thể chứa handles liên quan đến chính class nhưng không được đưa sang global cache khác. |
| Cần query tổng số classes đang cache hoặc scan tất cả entries | ClassValue **không có iteration/size API**; dùng registry riêng với retention policy rõ. |
| Metadata phụ thuộc cả Class và cấu hình/tenant/version | ClassValue có thể giữ một cache nhỏ theo version cho class, nhưng invalidate/versioning phải tự thiết kế; tránh giữ tenants/versions không giới hạn. |
| Cần memoize theo object instance, không phải class | ClassValue **không** phải object-key cache; chọn API thích hợp (ví dụ `WeakHashMap<Object,...>` nếu value graph an toàn). |
| Logic `computeValue` đăng ký side effects hoặc cấp resource | Phải chuyển những side effects sang lifecycle quản lý rõ; `computeValue` có thể chạy lặp khi race. |
| Plugin loader được thay thế định kỳ | ClassValue giúp giảm một đường retention; vẫn cần shutdown tasks/threads, clear registries và phát hiện GC roots còn giữ loader. |
| Bảo đảm cleanup tại một thời điểm chính xác | Không dùng `System.gc()`/ClassValue như scheduler cleanup. Gọi `close`/`removeListener`/`shutdown` chủ động. |

### 11.1. ClassValue không thay đổi quyền truy cập Reflection/Lookup

Nếu value được tính bằng `MethodHandles.Lookup.findVirtual`, `findStatic`, `privateLookupIn` hoặc `unreflect`, nó chỉ có thể tạo handle theo quyền của Lookup hợp lệ. ClassValue **không cấp thêm access privilege**, và metadata được cache có thể mang capability truy cập đến method/field.

Tránh đưa metadata có MethodHandles private ra ngoài plugin boundary nếu consumer không có quyền sử dụng chúng. ClassValue bảo vệ **cách cache theo class**, không phải ranh giới bảo mật.

### 11.2. Hiệu năng

ClassValue được thiết kế cho truy cập per-class tương đối hiệu quả. Nhưng không nên hứa rằng nó “luôn nhanh hơn ConcurrentHashMap” trong mọi workload. Chi phí tính metadata có thể lớn; hot path nên tái sử dụng association đã có, tránh `remove` liên tục khiến recomputation xảy ra.

Nếu cần benchmark, dùng JMH với warmup và so sánh:

- Lần get đầu tiên (cold compute);
- Các lần get sau (warm cached access);
- Truy cập đồng thời;
- Có/không có invalidate;
- Tác động tới class unloading/memory khi tạo và bỏ nhiều child loaders.

**Điều quan trọng hơn một vài nanosecond:** đúng class identity và không giữ hàng trăm class loaders cũ lâu không cần thiết.

## 12. Chẩn đoán giữ class loader bằng công cụ JDK 17

Đo theo **nhiều vòng tải/reload có kiểm soát** thay vì chỉ một ảnh chụp. Phân biệt số lượng class đang loaded, class đã unloaded, heap object count, metaspace committed/used và số loader của plugin cụ thể.

### 12.1. jcmd: xem class loaders, metaspace và heap histogram

Trong môi trường có quyền attach phù hợp, dùng process ID thực:

```bash
jcmd -l
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.metaspace
jcmd 12345 GC.class_histogram
```

`12345` chỉ là **PID minh họa**, phải thay bằng PID của JVM cần chẩn đoán. Các câu lệnh trên không phải output demo cố định. `jcmd` thường cần cùng host/user và quyền attach tương ứng; một số runtime image/container có thể không tích hợp đầy đủ công cụ.

- `VM.classloader_stats`: số classes và metadata theo class loader; hữu ích để thấy nhiều loader của các version plugin cùng tồn tại.
- `VM.metaspace`: thống kê vùng metadata class; cần nhìn xu hướng và sự phân biệt **reserved/committed/used**, không chỉ một con số.
- `GC.class_histogram`: số instances/heap bytes theo kiểu; giúp tìm metadata, thread objects và registries phình lớn. Histogram **không tự chỉ ra GC root path**.
- `jcmd 12345 help VM.classloader_stats`: xem help cụ thể nếu build JVM có khác biệt.

Một heap dump có thể dùng để tìm đường giữ mạnh:

```bash
jcmd 12345 GC.heap_dump filename=heap.hprof
```

**Cảnh báo:** heap dump có thể lớn, nhạy cảm (chứa secrets, personal data) và ảnh hưởng latency/GC của tiến trình. Chỉ thực hiện trong môi trường được phép, có đủ dung lượng và chính sách bảo mật của file dump.

### 12.2. Class-loading / unloading logs

Khi khởi động JVM hỗ trợ Unified Logging (HotSpot Java 17), có thể quan sát sự kiện nạp và tháo lớp:

```bash
java -Xlog:class+load=info,class+unload=info MyApp
```

Đây là **lệnh mẫu** cho một ứng dụng tên `MyApp`, không phải output bài demo; cần cấu hình classpath/module path phù hợp. Lượng log class load có thể lớn. Việc không thấy sự kiện unload trong một khoảng ngắn không chứng minh leak; class/loader có thể còn reachable hợp lệ, GC chưa thu gom hoặc JVM chưa chọn thực hiện unloading.

### 12.3. Java Flight Recorder và JDK Mission Control

Với JVM hỗ trợ JFR, có thể bật recording có profile settings:

```bash
jcmd 12345 JFR.start name=LoaderAudit settings=profile duration=60s filename=loader.jfr
jcmd 12345 JFR.check
```

Chương trình cần chạy đủ lâu để thu sự kiện trong khoảng recording; tên sự kiện được ghi và cấu hình JFR phụ thuộc profile/JVM. JFR/JDK Mission Control cho phép xem số class loaded/unloaded, allocation và thread activity theo thời gian khi các event tương ứng được bật. Dùng JFR để **quan sát xu hướng** và ghép với heap retention graph, không tuyên bố một recording tự động xác định nguyên nhân leak.

### 12.4. Native Memory Tracking (NMT)

Trên HotSpot, khi cần phân biệt heap và native memory (đặc biệt metaspace), có thể bật NMT **khi khởi động**:

```bash
java -XX:NativeMemoryTracking=summary MyApp
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

NMT có overhead và có thể cần JVM/build hỗ trợ. Nó cho thấy phân loại native memory như Class/Metaspace, nhưng không thay heap dump cho mục tiêu **“ai đang giữ một particular ClassLoader reachable?”**. NMT growth là dấu hiệu cần điều tra, không tự chứng minh leak object graph.

### 12.5. Heap dump: từ loader đến GC roots

Trong Eclipse Memory Analyzer (MAT) hoặc công cụ tương tự:

1. Tìm các instances class loader của plugin: `URLClassLoader` hoặc subclass custom như `PluginClassLoader`.
2. Nhóm theo class loader/class histogram; xem số classes/retained size của từng loader.
3. Chọn loader của một plugin version đã stop và dùng **Path to GC Roots** / shortest strong paths.
4. Xác định root còn sống: static map host, live thread, ThreadLocal, TCCL, listener registry, MethodHandle, JNI global, service registry...
5. Đối chiếu với lifecycle stop/unregister thực tế.
6. Sửa **đường giữ root** rồi kiểm tra lại trong workload nhiều vòng redeploy.

Đừng chỉ tìm tên class `PluginClassLoader` và kết luận nó leak khi thấy một instance. Nếu plugin **đang chạy**, loader còn sống là hợp lệ. Ngược lại, nếu nhiều loaders của những version đã dừng còn reachable từ root rất lâu, đó là bằng chứng mạnh hơn.

## 13. Quy trình điều tra thực tế: loader sống sau khi plugin đã dừng

Giả sử ứng dụng reload một plugin 20 lần, mỗi lần tạo loader mới, nhưng metaspace và số plugin loaders vẫn tăng.

**Bước 1 — xác nhận thực sự có nhiều loader:** dùng `VM.classloader_stats`, số class loaded/unloaded và tên loader/version. Phân biệt một loader tải thêm nhiều classes với **nhiều loaders** cùng mang classes giống tên.

**Bước 2 — xem cache metadata:** tìm static `Map<Class<?>,...>`, map key string nhưng value giữ `MethodHandle`, `MethodType`, `Field`/`Method` hoặc instance plugin. Nếu metadata chỉ là per-class derived data, cân nhắc ClassValue và loại bỏ strong-key map.

**Bước 3 — xem threads:** xác định thread pool, scheduled tasks, TCCL, thread locals. Một scheduled callback của plugin có thể sống dù registry metadata đã clear.

**Bước 4 — xem registries:** unsubscribe listeners, deregister drivers, MBeans, logging hooks và các service callbacks do plugin cũ cung cấp.

**Bước 5 — xem value graph:** kể cả với `WeakHashMap<Class<?>, Metadata>`, value có thể giữ Class key. Nếu metadata được đặt trong `ClassValue` **và** một list global khác, list ấy vẫn là root giữ loader.

**Bước 6 — sửa và đo lại:** xác định một protocol stop trong đó plugin ngừng nhận requests, kết thúc async work, hủy registrations, restore TCCL, clear registries, bỏ strong refs cuối. Chạy lại nhiều reload cycles và so sánh xu hướng classes/loaders/metaspace với baseline.

**Bước 7 — không giả định GC tức thì:** tính đúng của cleanup là **không còn đường giữ root không cần thiết**; unloading xảy ra khi JVM và GC cho phép. Nếu cần proof mạnh, dùng heap dump/reachability analysis cùng logs và thời gian đủ dài.

### 13.1. Cần phân biệt “leak” với cache được dự định giữ

Một class-loader manager có thể cố ý giữ các loader đã tạo để phục vụ hot rollback/versioned requests. Khi đó tăng metaspace là **retention có chủ đích**, nhưng vẫn phải có giới hạn dung lượng/version và policy eviction. Điều tra bắt đầu bằng câu hỏi “loader này có còn được yêu cầu không?” trước khi gọi nó là leak.

Một ClassValue cache có thể giữ một đối tượng Metadata rất lớn khi Class vẫn được sử dụng. Đó có thể là **memory bloat** cần tối ưu value, dù không phải class-loader leak. Phải tách **lớp không unload được vì root**, **value quá lớn** và **class load rate quá cao**.

## 14. Checklist thiết kế hệ thống lâu sống

- [ ] Cache metadata per `Class<?>` dùng `ClassValue<T>` khi phù hợp, không đặt strong keys Class vào static Map không có lifecycle.
- [ ] `computeValue` có semantics tính lặp an toàn, không thực hiện side effect phải exactly-once.
- [ ] Metadata value lý tưởng là immutable; nếu chứa MethodHandle/Class khác, kiểm tra class-loader provenance.
- [ ] Khi cấu hình thay đổi, xác định cách invalidate/version và ai được tiếp tục dùng value cũ.
- [ ] Plugin stop đóng thread pools, tasks, sockets, class-specific resources và unregister callbacks/listeners.
- [ ] Worker threads restore `Thread.contextClassLoader` và dọn `ThreadLocal` đúng thread.
- [ ] Không giữ plugin instances/classes trong global singletons hoặc diagnostics buffers mãi mãi.
- [ ] Không dùng `WeakHashMap` như một chứng chỉ memory-safety nếu value có thể tham chiếu key.
- [ ] Class loader của version cũ không bị giữ bởi MethodHandle, CallSite, MethodType, proxy hoặc cached reflection members ở host.
- [ ] Có metrics class-loading/unloading, metaspace, plugin loader count; điều tra bằng heap root paths khi thấy growth.
- [ ] GC/unloading không được test theo kiểu buộc `System.gc()` rồi assert weak reference đã null.
- [ ] Không dùng ClassValue/weak references để thay thế explicit cleanup và quyền truy cập an toàn.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao `static Map<Class<?>,Metadata>` trong application singleton có thể giữ loader của plugin cũ sống?**

Vì key `Class<?>` được map giữ mạnh. Một Class object thuộc plugin giữ liên hệ đến defining loader, tạo đường retention từ GC root của singleton tới loader, dù plugin manager đã dừng version đó.

**2. `ClassValue` khác gì `ConcurrentHashMap<Class<?>,Metadata>`?**

Nó gắn association trên cơ sở Class qua API lazy `computeValue/get/remove` mà không buộc ứng dụng giữ một global map với strong Class keys. Nó không có iteration/size/put như map thông thường và không tự dọn resources bên ngoài.

**3. `computeValue` có chạy đúng một lần trên mỗi Class không?**

Không được giả định. Nhiều thread có thể cùng compute và chỉ một value được publish; `remove` cũng có thể khiến compute chạy lại. Các side effects trong computation phải chịu được việc lặp.

**4. `remove(Class)` có giải phóng mọi metadata đang được người khác dùng và đóng file/socket không?**

Không. Nó invalidate association của một ClassValue với Class đó. References đã trả về vẫn tồn tại, và lifecycle external resources cần được quản lý độc lập.

**5. Vì sao dùng `WeakHashMap<Class<?>,Metadata>` vẫn có nguy cơ leak?**

Key là weak, nhưng value được giữ mạnh. Nếu Metadata chứa `Class<?>` key hoặc MethodHandle trỏ tới chính class đó, strong path `map → value → key → loader` vẫn giữ class/loader sống.

**6. Nếu hai child loaders tạo cùng `plugin.Widget`, ClassValue có nhầm metadata của chúng không?**

Không. Hai `Class<?>` khác nhau, dù chuỗi binary name giống nhau; ClassValue association theo Class identity. Trong demo, metadata mỗi loader là object riêng.

**7. ThreadLocal có weak key thì sao còn giữ plugin loader?**

Vì `ThreadLocalMap` có thể giữ value mạnh trên live pool thread; value là plugin object hoặc chứa Class/loader. Cần `remove()` đúng thread và lifecycle cleanup.

**8. Dùng `System.gc()` một lần rồi thấy `WeakReference<ClassLoader>.get()!=null` có chứng minh leak không?**

Không. GC/unloading không phải synchronous contract. Cần xác định root path/lifecycle, theo dõi xu hướng sau nhiều vòng tải và điều tra bằng heap dump/JFR/jcmd.

**9. Những công cụ nào giúp tìm loader retention?**

`jcmd VM.classloader_stats` để thấy loaders/classes, `VM.metaspace` cho metadata memory, `GC.class_histogram` cho heap objects, JFR/logs cho load/unload trends; **heap dump với Path to GC Roots** là cách tìm strong retention paths trực tiếp.

**10. ClassValue có phải giải pháp đúng khi toàn bộ metadata phụ thuộc cả `Class<?>` và tenant đang thay đổi không?**

Nó chỉ khóa theo Class. Bạn phải tự mô hình hóa tenant/config/version trong value và invalidation, hoặc chọn cache khác có lifecycle rõ. Nếu dùng ClassValue rồi giữ tất cả tenants mãi mãi trong value, vẫn có thể gây memory bloat.

## 16. Tóm tắt

- **ClassValue<T>** phù hợp với metadata cache **lazy theo Class identity** và tránh strong global `Class<?>` keys.
- **`get`** tính/cài association khi cần; **`computeValue` có thể chạy nhiều lần** dưới race, nhưng giá trị được cài đặt được quan sát nhất quán theo contract; **`remove`** invalidate association để lần get sau tính lại.
- **Class loader leak là câu chuyện reachability:** tìm chuỗi từ **GC roots** tới `Class<?>`, loader, instance hoặc MethodHandle thuộc plugin, thay vì chỉ nhìn tên class hoặc một chỉ số metaspace.
- **WeakHashMap không đảm bảo hết leak** nếu strong values tham chiếu ngược keys; ThreadLocal và TCCL là hai nguồn giữ loader quan trọng.
- **ClassValue không auto-close resources**, không xóa listeners, không ngừng thread pools và không chặn mọi paths khác.
- **Kiểm thử/class unloading không tất định theo một System.gc**; quan sát bằng `jcmd`, JFR, class unloading logs, heap dump và **Path to GC Roots** khi có dấu hiệu retention.
- **Thiết kế tốt cần cả cache đúng kiểu và lifecycle đúng:** metadata per Class, explicit cleanup, bounded registries, controlled thread contexts và monitoring.

### Tài liệu tham khảo chính thức — Java SE 17

- [ClassValue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): contract `computeValue`, `get`, `remove`, atomic installation, tranh chấp và invalidation.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): identity, `getClassLoader`, class metadata.
- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, nạp/định nghĩa lớp.
- [WeakHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values và nguy cơ value gián tiếp giữ key.
- [ThreadLocal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `set/get/remove`, lifecycle thread-local values.
- [Java SE 17 Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): `jcmd`, class loading stats, metaspace/NMT, JFR, heap dumps.
- [Java SE 17 Troubleshooting Guide — Diagnosing Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-guide.pdf): class-loader statistics và điều tra retention.
