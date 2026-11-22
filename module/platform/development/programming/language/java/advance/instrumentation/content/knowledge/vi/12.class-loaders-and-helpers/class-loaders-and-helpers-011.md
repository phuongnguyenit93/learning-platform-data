# Quản lý tham chiếu đến Class, ClassLoader và cache để không giữ bộ nạp đã hết vòng đời

> **Ý chính:** Trong Java instrumentation, việc lưu `Class<?>`, `ClassLoader`, `Method`, `MethodHandle` hay đối tượng ứng dụng trong một **cache/registry sống lâu hơn ứng dụng được instrument** có thể khiến bộ nạp lớp của phiên bản ứng dụng cũ không còn cơ hội được thu gom. Xóa một ứng dụng/plugin khỏi hệ thống không đủ nếu Java agent, transformer, thread, cache hoặc callback vẫn giữ đường tham chiếu mạnh đến các class do loader ấy định nghĩa. Muốn tránh *class loader leak*, hãy thiết kế vòng đời của **đối tượng được lưu**, **nơi lưu** và **cơ chế hủy đăng ký/giải phóng** đồng nhất với vòng đời của defining class loader.

Bài thuộc nhóm **Class loader và helper** của Java Advance – instrumentation. Ta sẽ giải thích đồ thị tham chiếu gây rò rỉ, lựa chọn cache phù hợp, bẫy `WeakHashMap`, cách dùng `ClassValue` và `WeakReference`/`ReferenceQueue`, cùng một thí nghiệm Java 17+ có Java agent thật. **Quan trọng:** Thí nghiệm chứng minh cấu trúc tham chiếu và hành vi cache bằng output xác định; nó **không tuyên bố GC chắc chắn đã unload class** sau khi gọi `clear()`.

## 1. Vòng đời class loader và vì sao agent dễ giữ nhầm

Một class Java được định danh ở runtime bởi **binary name và defining class loader**, không chỉ bởi tên dạng `com.example.PaymentService`. Hai plugin có thể cùng chứa `com.example.PaymentService` nhưng do hai class loader riêng định nghĩa, nên đó là **hai `Class<?>` khác nhau**.

Khi một plugin được redeploy:

~~~text
JVM / tiến trình vẫn sống
    |
    +-- Agent lâu dài, helper, metrics exporter, static registry
    |
    +-- Plugin version 1: PluginClassLoader@A --> các Class<?> của version 1
    |       |
    |       +-- sau undeploy: đáng lẽ có thể được thu hồi
    |
    +-- Plugin version 2: PluginClassLoader@B --> các Class<?> của version 2
            |
            +-- hoạt động bình thường
~~~

Nếu agent đặt `Class<?>` của version 1 vào một `static Map` và quên xóa, registry lâu dài trở thành **GC root chain** đi tới class của loader A. Class của loader A và bản thân loader có quan hệ giữ nhau trong mô hình JVM, khiến loader A và nhiều dữ liệu đi kèm có thể còn sống dù plugin A đã bị undeploy.

Điểm cần nhớ:

- **Một class chưa được unload không tự chứng minh có leak.** GC/class unloading có điều kiện về reachability và không nhất thiết diễn ra ngay khi undeploy.
- **Một vòng tham chiếu không tự là leak.** Ví dụ loader → class metadata → loader có thể được thu gom khi không còn đường tham chiếu mạnh từ các root đang sống.
- **Leak thực tế xuất hiện khi có root sống lâu** (agent, static cache, thread, global listener, native reference...) tiếp tục dẫn tới class/loader thuộc phiên bản cũ không còn cần thiết.
- **Class unloading không đồng nghĩa object cleanup tức thì.** Cần quản lý resource, thread, listener và cache của plugin; không chỉ trông chờ GC.

Đối với công cụ instrumentation, rủi ro tăng vì agent thường được JVM nạp sớm và **sống suốt tuổi thọ tiến trình**, trong khi ứng dụng hoặc plugin có vòng đời ngắn hơn. Cần xem agent là một bên **có thể vô tình sở hữu reference dài hạn** đến class loader mà nó chỉ định quan sát.

## 2. Những đường tham chiếu làm loader không được thu hồi

### 2.1. Một `Class<?>` làm key trong static cache

Ví dụ anti-pattern:

~~~java
// Mảnh minh họa trong agent, không phải chương trình độc lập.
private static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();

static void remember(Class<?> type, Metadata metadata) {
    CACHE.put(type, metadata);
}
~~~

Nếu class `type` do một plugin loader định nghĩa, map được giữ bởi agent có tuổi thọ JVM. Dù plugin xóa mọi reference của nó, **map vẫn giữ mạnh key `Class<?>`**. Chừng nào entry còn đó, JVM không thể coi `Class<?>` là không còn được tham chiếu theo cách thông thường.

Cùng một vấn đề xuất hiện với những key khác: `Map<ClassLoader, ...>`, `Set<ClassLoader>`, list các class đã transform, hoặc cache `Method` và `Constructor`. Method reflection gắn với declaring class; `MethodHandle`/lookup và các cấu trúc chứa method cũng phải được kiểm tra vì chúng có thể giữ class và loader.

~~~text
GC root (class của agent sống lâu)
    |
    v
static ConcurrentHashMap
    |
    +-- key Class<PluginClass>  <-- giữ tham chiếu mạnh
            |
            v
       defining PluginClassLoader
            |
            v
       các lớp/plugin metadata liên quan
~~~

**Sửa theo lifecycle:** không giữ entry mạnh vĩnh viễn; dùng cache theo class có hành vi phù hợp với unloading, hoặc gỡ entry theo sự kiện undeploy, hoặc giới hạn cache bằng chính sách rõ ràng. `CACHE.clear()` chỉ giải phóng đường tham chiếu của **cache đó**; nếu còn thread, registry hay cache khác giữ lớp, loader vẫn chưa đủ điều kiện unload.

### 2.2. Một `ClassLoader` làm key hoặc value

~~~java
// Cũng là anti-pattern nếu map sống lâu hơn plugin:
private static final Map<ClassLoader, LoaderInfo> LOADERS = new HashMap<>();
~~~

Đây là **tham chiếu mạnh trực tiếp** đến loader qua key. Đổi key sang tên loader dạng `String` có thể bỏ đường tham chiếu trực tiếp nhưng **không giải quyết mọi vấn đề**: tên có thể không duy nhất, dữ liệu vẫn tăng vô hạn và value có thể tiếp tục giữ class/loader.

Một giá trị `LoaderInfo` có thể gián tiếp giữ loader qua `Class<?>`, `Method`, `ClassLoader`, một object của plugin, lambda đóng trên service plugin, class proxy, hoặc listener được khởi tạo từ plugin.

### 2.3. Transformer và callback được đăng ký suốt tuổi thọ JVM

~~~java
// Minh họa thiết kế có nguy cơ giữ loader:
final ClassLoader pluginLoader = discoverPluginLoader();
ClassFileTransformer transformer = new MyTransformer(pluginLoader);
instrumentation.addTransformer(transformer);
~~~

Nếu `MyTransformer` giữ mạnh `pluginLoader` trong field và registration của JVM còn giữ transformer, thì xóa các reference trong plugin **không gỡ được đường tham chiếu qua registration**.

Khi không cần transformer, hãy gỡ bằng **chính instance đã đăng ký**:

~~~java
boolean removed = instrumentation.removeTransformer(transformer);
~~~

Lưu ý:

- `removeTransformer` hủy một đăng ký tương ứng; nó **không tự hoàn nguyên bytecode của các class đã instrument**.
- Nếu cùng instance đã add nhiều lần, một lần remove chỉ gỡ registration khớp gần nhất. Tránh đăng ký trùng.
- Theo Javadoc, callback có thể vẫn xảy ra sau lệnh remove vì class loading diễn ra đồng thời. Transformer phải chịu được callback muộn.
- Nếu agent còn giữ reference đến transformer hay `pluginLoader` trong một static field/list, **chỉ gọi remove chưa đủ**; phải xóa cả field/list đó khi an toàn.

### 2.4. Thread, context class loader và thread-local

Không chỉ cache trực tiếp mới pin loader:

- Thread sống lâu có thể đang đặt `Thread.getContextClassLoader()` thành loader của plugin cũ. Ví dụ worker thread do framework tạo và được tái dùng sau undeploy.
- `ThreadLocal` trên executor thread còn giữ một object thuộc plugin sau khi request hoàn tất.
- Scheduled task, `ExecutorService`, listener, shutdown hook, exporter, metric callback, JMX MBean hoặc service registry vẫn giữ instance/class của plugin.
- Một callback mạnh được đăng ký ở singleton JVM-scope có thể giữ toàn bộ closure và class loader của plugin.

**Pattern khôi phục context loader** cho một tác vụ hữu hạn:

~~~java
// Minh họa đặt trong code đã biết appLoader và Runnable task:
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(appLoader);
    task.run();
} finally {
    current.setContextClassLoader(previous);
}
~~~

Nếu khởi tạo executor/thread riêng cho plugin, quản lý cả lifecycle và shutdown, không chỉ đổi TCCL. Với `ThreadLocal<T>`, gọi `remove()` trong `finally` sau phạm vi sử dụng. Khi giữ một reference đến object của plugin, hãy xem cả **chuỗi giá trị gián tiếp**, không chỉ kiểu field được khai báo.

## 3. Trong callback transformer, cái gì nên và không nên giữ?

Java 17+ cho phép override callback dạng:

~~~java
byte[] transform(Module module,
                 ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain domain,
                 byte[] classfileBuffer);
~~~

Đây là **chữ ký minh họa**, không phải file Java độc lập. Mọi tham số có ý nghĩa riêng:

| Tham số | Có thể dùng để làm gì trong callback? | Rủi ro nếu cache dài hạn |
| --- | --- | --- |
| `module` | Giới hạn module cần instrument | Giữ object module có thể kéo theo graph tới loader/runtime; phải xác minh |
| `loader` | Phân biệt class do bootstrap loader (`null`) và các defining loader khác | Strong reference tới plugin loader |
| `className` | Lọc tên lớp dạng internal name: `org/sample/Worker` | String bản thân không giữ loader nhưng **không đủ** để định danh class duy nhất |
| `classBeingRedefined` | Phân biệt class đang định nghĩa lần đầu (`null`) với class đã tồn tại (non-null) | Strong reference tới `Class<?>` của loader cũ |
| `domain` | Truy cập ngữ cảnh protection domain khi thật sự cần | Có thể giữ một phần object graph liên quan; không lưu vô hạn theo mặc định |
| `classfileBuffer` | Phân tích/sinh class bytes | Copy bytes không giữ `Class<?>` trực tiếp, nhưng có thể tốn heap lớn và lộ nội dung nếu cache vô hạn |

**Lọc sớm, xử lý ngắn, không tích trữ object sống dài hạn**:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
    if (className == null || !className.startsWith("org/sample/")) {
        return null;
    }
    // Dùng thông tin trong thời gian callback, không bỏ Class/loader vào global map.
    // Nếu không sinh bytecode mới, trả null.
    return null;
}
~~~

Mảnh callback này cần đặt trong lớp triển khai `ClassFileTransformer` cùng import phù hợp; nó không phải một chương trình độc lập. Nếu chỉ cần số lượt transform theo nhóm, bạn có thể tăng một counter theo **tên operation/namespace đã chuẩn hóa**, thay vì tạo `Map<ClassLoader,Class<?>>` dùng để đếm.

**Những điều dễ hiểu nhầm:**

- Với first definition, `classBeingRedefined == null` là bình thường; do đó không nên dựa vào nó để lấy `Class<?>`.
- `className` dùng dấu slash; `Class.getName()` dùng dấu chấm. Hai loader khác nhau có thể cùng nhận `className`, nên không dùng chuỗi làm danh tính lớp duy nhất khi thực sự cần class identity.
- `loader == null` thường có nghĩa defining loader là bootstrap loader, không phải luôn thiếu thông tin hay một lỗi.
- Không dùng `Class.forName` bừa bãi trong callback để "lấy Class" cho tên vừa thấy: nó có thể kích hoạt class loading, recursion và class loader leak nếu kết quả bị cache.
- Callback có thể chạy đồng thời, nên cache/counter phải thread-safe và có chính sách capacity. Dù dùng weak references, cần quản lý concurrency và cleanup.

## 4. `WeakHashMap`: weak key không cứu được value giữ ngược key

Một gợi ý hay gặp là thay `HashMap<ClassLoader, V>` bằng `WeakHashMap<ClassLoader, V>`. Cách này **chỉ đúng** nếu các **value không giữ mạnh loader key** (trực tiếp hoặc gián tiếp).

Ví dụ **sai**:

~~~java
// Sai khi map sống lâu hơn plugin:
Map<ClassLoader, Class<?>> cache = new WeakHashMap<>();
cache.put(pluginLoader, pluginClass);
~~~

Tại sao vẫn giữ loader? `WeakHashMap` chỉ giữ key qua weak reference, **nhưng giữ value bằng strong reference**. Vì `pluginClass.getClassLoader() == pluginLoader`, đường đi trở thành:

~~~text
GC root: Map được agent giữ
       |
       v
WeakHashMap.Entry
       |
       +-- weak key -----> pluginLoader   (không tính là đường mạnh)
       |
       +-- strong value -> Class<PluginClass>
                              |
                              v
                          pluginLoader   (đường mạnh!)
~~~

Do đó value → `Class<?>` → loader có thể khiến weak key **không bao giờ trở nên weakly reachable** trong lúc map còn giữ value. Cùng bẫy xảy ra nếu value là `Method`, `ClassLoader`, `Supplier` đóng trên plugin object, hoặc một `LoaderInfo` chứa lại class/loader.

Oracle JDK `WeakHashMap` Javadoc nêu rõ value được giữ mạnh và cảnh báo về value tham chiếu tới key. Khi muốn dùng weak map:

- Key có thể là loader nhưng value nên là số liệu/metadata độc lập, ví dụ `LongAdder` hay immutable value không chứa loader/class.
- Nếu value phải giữ class hoặc object của plugin, cân nhắc **weak value** và cơ chế chịu được việc cache entry biến mất; kiểm tra graph thực tế.
- `WeakHashMap` không tự đồng bộ. Có thể dùng `Collections.synchronizedMap`, và phải đồng bộ khi iterate; với throughput cao, cân nhắc cấu trúc khác có policy rõ.
- Việc key biến mất phụ thuộc **GC**, nên `map.size()` có thể thay đổi giữa hai lần đọc. Không lấy thời điểm xóa entry làm mốc callback hoặc shutdown deterministic.

**Vẫn chưa phải giải pháp hoàn chỉnh:** nếu một registry khác giữ plugin loader thì weak map không thể chủ động khiến loader được GC. Weak reference **không xóa** các đường strong reference bên ngoài.

## 5. `ClassValue<T>`: metadata gắn với chính class, không phải global strong map

Nếu cần cache **thông tin có phạm vi theo từng `Class<?>`**, Java 17 có `ClassValue<T>`. Đây là API để liên kết lazy-computed value với một class cụ thể, thay vì tự tạo `static Map<Class<?>, T>` giữ key mạnh.

Ví dụ:

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class PerClassCounters {
    private PerClassCounters() {}

    private static final ClassValue<LongAdder> COUNTS = new ClassValue<>() {
        @Override
        protected LongAdder computeValue(Class<?> type) {
            return new LongAdder();
        }
    };

    public static void count(Class<?> type) {
        COUNTS.get(type).increment();
    }

    public static long read(Class<?> type) {
        return COUNTS.get(type).sum();
    }

    public static void reset(Class<?> type) {
        COUNTS.remove(type);
    }
}
~~~

**Đây là một lớp Java có thể biên dịch** nhưng để chạy cần caller truyền `Class<?>` đích. `ClassValue.get(type)` tạo value theo class khi chưa có; `remove(type)` xóa association cho class đó, và `get` sau đó có thể tính lại.

Lợi ích về thiết kế:

- Không có một global `Map<Class<?>,...>` do bạn tự tạo để giữ mạnh mọi class từng quan sát.
- Hai class có cùng binary name nhưng do hai loader khác nhau định nghĩa nhận **hai value độc lập**.
- Không cần chọn một chuỗi ID giả định là duy nhất cho class loader khi dùng metadata nội bộ.
- Phù hợp với metadata theo class không cần liệt kê toàn bộ cache bằng một registry toàn cục.

**Không biến `ClassValue` thành lời hứa unload tự động:** vẫn cần bảo đảm không còn strong root khác giữ class/loader; giá trị `LongAdder` trong ví dụ không giữ loader, nhưng nếu bạn đồng thời đưa `Class<?>` vào static list, leak vẫn có thể tồn tại. `ClassValue` cũng không thay thế chính sách đóng resource thuộc plugin.

Lưu ý concurrency: nếu các thread cùng gọi `get`/`remove`, `computeValue` có thể được tính lại; thiết kế side effects trong `computeValue` hạn chế và tuân thủ contract. `ClassValue` rất hợp với **cache** gắn class, nhưng không phải API để enumerate tất cả plugin đang sống.

## 6. `WeakReference` và `ReferenceQueue` cho quan sát lifecycle

Khi cần **theo dõi một loader có thể được GC hay chưa** mà không tự pin loader, dùng weak reference:

~~~java
import java.lang.ref.WeakReference;

WeakReference<ClassLoader> watched = new WeakReference<>(pluginLoader);
// ... sau khi tất cả strong references được bỏ đi:
ClassLoader maybeAlive = watched.get(); // có thể null sau một GC phù hợp
~~~

Đây là **mảnh minh họa**, chưa phải file độc lập. `watched.get() != null` có thể đơn giản vì **GC chưa thu gom**, chứ không nhất thiết là leak. `watched.get() == null` cho biết weak referent đã bị clear; nhưng đó không đồng nghĩa mọi file handle, exporter hay external resource của plugin đã cleanup.

Nếu cần nhận tín hiệu GC và dọn **metadata không tham chiếu ngược về loader**, có thể dùng `ReferenceQueue`:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

// Mảnh triển khai đặt trong một class registry:
private static final ReferenceQueue<ClassLoader> QUEUE = new ReferenceQueue<>();
private static final Map<Reference<? extends ClassLoader>, Integer> TAGS =
        new ConcurrentHashMap<>();

static void observeLoader(ClassLoader loader, int tag) {
    drain();
    TAGS.put(new WeakReference<>(loader, QUEUE), tag);
}

static void drain() {
    Reference<? extends ClassLoader> cleared;
    while ((cleared = QUEUE.poll()) != null) {
        TAGS.remove(cleared);
    }
}
~~~

**Đây là mảnh code đưa vào một class**, không phải chương trình đứng độc lập. Registry giữ mạnh **đối tượng `WeakReference`** để nó không biến mất trước khi được enqueue; `WeakReference` không giữ mạnh referent loader. `Integer tag` là dữ liệu độc lập, **không tham chiếu loader**. `drain()` cần được chạy theo chính sách phù hợp (sự kiện mới hoặc chu kỳ), vì queue không tự dọn `TAGS` nếu không poll.

**Không dùng `ReferenceQueue` làm cơ chế business cleanup bắt buộc:** GC có thể trì hoãn hoặc không chạy trong khoảng quan sát. Khi undeploy, hãy chủ động unregister listener, đóng executor, xóa cache và thu hồi resource. Reference queue chỉ hỗ trợ quan sát/dọn metadata phụ.

Một bẫy khác: sử dụng `ConcurrentHashMap<WeakReference<ClassLoader>, Value>` với những `WeakReference` mới tạo cho mỗi lần lookup **không có semantics lookup theo referent identity**. Weak reference mặc định có identity của chính đối tượng reference; muốn map weak-key lookup đúng phải có cấu trúc weak-key chuyên dụng, cleanup queue và xử lý race, không chỉ đổi kiểu của key.

## 7. Thí nghiệm Java 17+ có agent thật: hai loader, một tên class, hai kiểu cache

Mục tiêu của demo:

1. Hai defining class loader khác nhau định nghĩa class cùng tên `PluginTask`.
2. Transformer của agent quan sát **hai lần định nghĩa** nhưng **không lưu `ClassLoader`/`Class<?>`**.
3. `ClassValue` cung cấp trạng thái riêng cho mỗi `Class<?>`.
4. Một global strong map và một `WeakHashMap` được cố tình cấu hình sai cho thấy **các đường tham chiếu có nguy cơ pin loader**.
5. Cache và transformer được dọn theo lời gọi tường minh.

**Giới hạn của phép thử:** Chương trình **không dùng `System.gc()` làm điều kiện assert** và không tuyên bố class đã unload. Trong `main`, các biến local vẫn còn giữ object loader/class đến một số thời điểm; mục tiêu là chứng minh **cache graph và class identity**, không đo thời điểm GC.

### 7.1. Tệp `PluginTask.java`

~~~java
public final class PluginTask {
    public String run() { return "plugin"; }
}
~~~

Class này **không** được ứng dụng load bằng cách tham chiếu `PluginTask.class`. Chương trình đọc file `PluginTask.class` thành bytes, rồi tự định nghĩa cùng một binary name vào hai loader riêng.

### 7.2. Tệp `PluginObserver.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.LongAdder;

public final class PluginObserver implements ClassFileTransformer {
    private final LongAdder observations = new LongAdder();

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
        if (!"PluginTask".equals(className)) return null;
        observations.increment();
        System.out.println("observer=PluginTask");
        return null;
    }

    public long observations() { return observations.sum(); }
}
~~~

Transformer nhận `loader` nhưng **không đưa nó vào field/map**; chỉ đếm sự kiện bằng `LongAdder`. Trả `null` nghĩa là **không sửa bytecode**. Tên `PluginTask` trong callback là dạng JVM internal name (vì class ở default package nên không chứa dấu slash).

Trong agent production, không nên `System.out.println` từ mọi class-load callback vì dễ gây I/O chậm hoặc recursion. Demo chỉ in hai lần trên class cụ thể, mục tiêu là quan sát rõ ràng.

### 7.3. Tệp `ObserverAgent.java`

~~~java
import java.lang.instrument.Instrumentation;

public final class ObserverAgent {
    private static Instrumentation instrumentation;
    private static PluginObserver observer;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        observer = new PluginObserver();
        inst.addTransformer(observer);
        System.out.println("agent=registered");
    }

    public static long count() { return observer.observations(); }

    public static void stop() {
        System.out.println("observer-removed=" +
                instrumentation.removeTransformer(observer));
        observer = null;
    }
}
~~~

Một startup agent được nạp trước ứng dụng, đăng ký transformer trước khi hai plugin loader định nghĩa `PluginTask`. `stop()` gỡ đúng instance, sau đó xóa static reference của agent đến transformer. Trong demo chỉ có một lần đăng ký.

Nếu callback còn có thể đang chạy song song với `stop()`, việc set `observer = null` phải được quản lý cẩn thận ở hệ thống thực (ví dụ đồng bộ/in-flight accounting). Ở đây `main` chạy tuần tự và không còn lượt định nghĩa class mục tiêu khi gọi `stop()`.

### 7.4. Tệp `LoaderCacheDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.WeakHashMap;

public final class LoaderCacheDemo {
    private static final Map<Class<?>, String> BAD_CLASS_CACHE = new HashMap<>();
    private static final Map<ClassLoader, Class<?>> BAD_WEAK_KEY_CACHE = new WeakHashMap<>();

    private static final ClassValue<Stats> PER_CLASS_STATS = new ClassValue<>() {
        @Override
        protected Stats computeValue(Class<?> type) { return new Stats(); }
    };

    private static final class Stats { int observations; }

    private static final class PluginLoader extends ClassLoader {
        PluginLoader() { super(null); }
        Class<?> definePlugin(byte[] bytes) {
            return defineClass("PluginTask", bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("PluginTask.class"));
        PluginLoader loaderA = new PluginLoader();
        PluginLoader loaderB = new PluginLoader();
        Class<?> classA = loaderA.definePlugin(bytes);
        Class<?> classB = loaderB.definePlugin(bytes);

        System.out.println("same-binary-name=" + classA.getName().equals(classB.getName()));
        System.out.println("same-class=" + (classA == classB));
        System.out.println("loader-a-matches=" + (classA.getClassLoader() == loaderA));
        System.out.println("agent-observations=" + ObserverAgent.count());

        PER_CLASS_STATS.get(classA).observations++;
        PER_CLASS_STATS.get(classB).observations += 2;
        System.out.println("per-class-counts=" +
                PER_CLASS_STATS.get(classA).observations + "," +
                PER_CLASS_STATS.get(classB).observations);
        BAD_CLASS_CACHE.put(classA, "metadata");
        BAD_WEAK_KEY_CACHE.put(loaderB, classB);
        System.out.println("strong-class-key-present=" +
                BAD_CLASS_CACHE.containsKey(classA));
        System.out.println("weak-value-references-key-loader=" +
                (BAD_WEAK_KEY_CACHE.get(loaderB).getClassLoader() == loaderB));

        BAD_CLASS_CACHE.clear();
        BAD_WEAK_KEY_CACHE.clear();
        System.out.println("cache-cleared=" +
                (BAD_CLASS_CACHE.isEmpty() && BAD_WEAK_KEY_CACHE.isEmpty()));
        ObserverAgent.stop();
    }
}
~~~

**Điểm cần phân tích kỹ:**

- `PluginLoader() { super(null); }` chỉ dùng bootstrap loader làm parent cho demo; `PluginTask` chỉ phụ thuộc các class core JDK, nên class được định nghĩa từ bytes có thể chạy. Đây **không phải mẫu class loading khuyến nghị cho ứng dụng lớn**.
- `definePlugin(byte[])` gọi `ClassLoader.defineClass("PluginTask",...)`, tạo `Class<?>` thuộc **đúng instance loader**.
- `classA` và `classB` có **cùng binary name nhưng khác class identity**.
- `PER_CLASS_STATS` là `ClassValue`, giá trị `Stats` không chứa class hay loader; hai class khác nhau có count độc lập.
- `BAD_CLASS_CACHE` là cache sai nếu sống qua undeploy. Key `Class<?>` được giữ mạnh.
- `BAD_WEAK_KEY_CACHE` thể hiện **bẫy weak key → strong value → defining loader**. Chương trình in kiểm tra đường tham chiếu, không chạy benchmark GC.
- Hai lời gọi `clear()` là cleanup chủ động. Output `cache-cleared=true` chỉ nói hai map đã trống, **không chứng minh loader đã được GC**, vì các biến local hay nơi khác vẫn có thể giữ reference.

### 7.5. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: ObserverAgent
~~~

Bài không yêu cầu `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`, vì transformer chỉ quan sát **lần định nghĩa đầu** của hai class. Lưu manifest có dấu xuống dòng cuối.

### 7.6. Biên dịch và chạy

Tạo năm file trong cùng thư mục:

~~~text
demo/
  PluginTask.java
  PluginObserver.java
  ObserverAgent.java
  LoaderCacheDemo.java
  agent.mf
~~~

Sơ đồ ở trên gồm **bốn Java source và một manifest**. Biên dịch và đóng gói:

~~~bash
javac --release 17 PluginTask.java PluginObserver.java ObserverAgent.java LoaderCacheDemo.java

jar --create --file observer-agent.jar --manifest agent.mf ObserverAgent.class PluginObserver.class

java -javaagent:observer-agent.jar LoaderCacheDemo
~~~

**Stdout được kiểm chứng với `javac --release 17` trên OpenJDK 24:**

~~~text
agent=registered
observer=PluginTask
observer=PluginTask
same-binary-name=true
same-class=false
loader-a-matches=true
agent-observations=2
per-class-counts=1,2
strong-class-key-present=true
weak-value-references-key-loader=true
cache-cleared=true
observer-removed=true
~~~

### 7.7. Kết quả nói lên điều gì — và chưa nói lên điều gì?

| Output | Kết luận có cơ sở | Điều không được kết luận |
| --- | --- | --- |
| `observer=PluginTask` xuất hiện hai lần | Hai class definition được transformer quan sát | Có bao nhiêu GC đã xảy ra |
| `same-binary-name=true` | Hai class có cùng tên `PluginTask` | Hai class có thể thay thế instance/`Class<?>` cho nhau |
| `same-class=false` | `classA` và `classB` là hai đối tượng `Class<?>` khác nhau | Một loader đã bị unload |
| `per-class-counts=1,2` | `ClassValue` tách dữ liệu theo class identity | `ClassValue` tự giải quyết mọi tham chiếu trong ứng dụng |
| `strong-class-key-present=true` | Global map giữ strong reference tới `classA` | Heap chỉ có một đường root |
| `weak-value-references-key-loader=true` | Strong value của weak map có đường trở lại chính key loader | `WeakHashMap` đã bảo vệ được bộ nạp khỏi leak |
| `cache-cleared=true` | Hai cache được dọn chủ động | GC chắc chắn đã thu hồi class/loader |
| `observer-removed=true` | Registration của transformer đã bị gỡ | Lớp nào từng instrument đã bị hoàn tác |

**Tại sao không gọi `System.gc()` để in "unloaded=true"?** Vì `System.gc()` chỉ là một yêu cầu gợi ý GC, không phải API cam kết class unloading. Việc JIT giữ local reference, một thread khác sử dụng loader, JVM trì hoãn unloading hoặc GC flag có thể làm kết quả khác nhau. Một bài kiểm tra đúng phải phân biệt **"không còn strong root sau teardown"** với **"GC đã hoàn thành class unloading"**.

## 8. Thiết kế cache phù hợp theo nhu cầu thực tế

| Nhu cầu | Lựa chọn phù hợp hơn | Điều kiện/giới hạn |
| --- | --- | --- |
| Metadata thuộc riêng một `Class<?>` | `ClassValue<V>` | Không tự tạo global strong key map; value nên ít side effects, không pin loader qua root khác |
| Counters theo **tên operation** với tập nhãn nhỏ | `ConcurrentHashMap<String, LongAdder>` có chính sách capacity | Không nhầm tên class với class identity; tránh cardinality vô hạn |
| Metadata theo loader, value không giữ ngược loader | `WeakHashMap<ClassLoader, SimpleMetadata>` hoặc cache weak-key đúng chuẩn | Kiểm tra value graph, synchronization và cleanup |
| Theo dõi GC của loader | `WeakReference<ClassLoader>` + `ReferenceQueue` | Tín hiệu không deterministic; không phải cơ chế cleanup bắt buộc |
| Cache reflection/method handles cho plugin | Cache do chính plugin sở hữu hoặc cùng lifecycle, đóng khi undeploy | Agent-wide strong cache đến `Method`/`MethodHandle` có thể pin loader |
| Cache bytecode theo tên class | Cache giới hạn dung lượng và thời gian, key đủ scope | Bytes tốn heap, không giữ Class trực tiếp; tránh nhầm hai loader cùng tên |
| Trường hợp cần cache strong để vận hành | Map theo **deployment scope** có `close()/clear()` | Cần teardown chắc chắn trong mọi nhánh success/failure/redeploy |

Đừng chọn loại cache chỉ theo tiêu chí "nhanh nhất" mà bỏ qua **ai sở hữu cache và ai biết khi nào class loader hết vòng đời**. Một cache strong sống trong class của chính plugin thường hết tuổi thọ cùng loader nếu không còn đường root bên ngoài. Chính cache ấy nếu được đặt vào một singleton/agent JVM-scope sẽ có vòng đời khác hoàn toàn.

### Cache scoped, đóng chủ động

Một mẫu đơn giản cho cache theo deployment:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class DeploymentCache implements AutoCloseable {
    private final Map<String, String> settings = new HashMap<>();

    public void put(String name, String value) {
        settings.put(name, value);
    }

    public String get(String name) {
        return settings.get(name);
    }

    @Override
    public void close() {
        settings.clear();
    }
}
~~~

Đây là class Java biên dịch được, nhưng chỉ phát huy ý nghĩa nếu **chính owner** gọi `close()` và **giải phóng reference tới cả `DeploymentCache`** lúc undeploy. Nếu cache cần chứa `Class<?>` hay object của plugin, đặt nó trong cùng lifecycle và dọn mọi reference ngoài phạm vi ấy. `AutoCloseable` không làm GC tự động; nó chỉ tạo hợp đồng cleanup.

## 9. Quy trình teardown an toàn cho agent và plugin

Khi một deployment/plugin kết thúc, cần kiểm tra từng lớp ownership:

1. **Dừng nguồn sự kiện mới**: ngừng nhận request/job, dừng đăng ký callback hoặc service listener thuộc plugin; tránh callback mới bắt đầu dùng state đang đóng.
2. **Gỡ instrumentation registration** không còn cần: gọi `Instrumentation.removeTransformer(transformer)` bằng đúng instance; quản lý các callback có thể còn đang chạy sau remove.
3. **Dừng thread và scheduler** do plugin/agent tạo, chờ bounded termination; không để thread phụ thuộc loader cũ tồn tại vô hạn.
4. **Xóa `ThreadLocal` và khôi phục TCCL** tại điểm ownership đúng. Với thread pool chia sẻ, đặt/restore TCCL theo phạm vi task, không đơn giản kill thread của pool chung.
5. **Unregister external registry**: JMX MBeans, listeners, hooks, exporter callbacks, service registrations, shutdown hooks thuộc plugin khi thích hợp.
6. **Close resources**: file handle/JAR, network clients, thread pools, class loader loại `URLClassLoader` nếu ứng dụng sở hữu (gọi `close()` để đóng resource JAR, lưu ý close **không bảo đảm unload**).
7. **Xóa cache theo deployment**: không để value/reflection handle/`Class<?>`/`ClassLoader` của deployment cũ trong global singleton, đồng thời giải phóng các lambda/callback chứa nó.
8. **Bỏ reference đến context và loader** sau cleanup, nhưng không làm thay đổi các references còn cần cho request đang chạy. Kiểm tra cả root từ agent, application server và code native.
9. **Quan sát sau một hoặc nhiều chu kỳ GC** nếu cần bằng heap dump, class loader statistics và `-Xlog:class+unload`; hiểu đó là quan sát implementation, không phải cam kết đồng bộ GC.

Không nên chỉ thực hiện bước "cache.clear" trong khi thread plugin vẫn còn chạy hoặc static listener vẫn nhận callbacks; như vậy vừa không giải quyết leak, vừa có thể phát sinh race và `NullPointerException`.

### Một phương án callback không lưu loader lâu dài

~~~java
// Mảnh minh họa trong ClassFileTransformer:
if (!"com/acme/PluginEndpoint".equals(className)) {
    return null;
}
// Số liệu tổng hợp với nhãn cố định; không đưa loader vào field/static map.
PLUGIN_ENDPOINT_DEFINITIONS.increment();
return null;
~~~

Nếu cần định danh theo deployment cho diagnostics, có thể gán một **deployment ID ngắn hạn, được giải phóng khi undeploy**; không dùng `System.identityHashCode(loader)` như một khóa toàn cục chắc chắn duy nhất theo thời gian (giá trị có thể trùng và không mang ownership semantics).

## 10. Chẩn đoán class loader leak bằng bằng chứng thay vì đoán GC

### 10.1. Quan sát số lượng loader và metaspace

Với HotSpot/OpenJDK tương thích, các lệnh hữu ích:

~~~bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace
~~~

`<pid>` ở đây là **placeholder trong lệnh mẫu**, không phải ký hiệu shell để copy nguyên xi; thay bằng PID tiến trình Java thực tế. Các lệnh phụ thuộc JVM/JDK đang dùng và quyền attach tới tiến trình, và output cấu trúc có thể khác nhau giữa các bản.

Khi điều tra redeploy:

- Ghi **baseline** số loader trước deployment; redeploy nhiều lần với cùng thao tác.
- Chụp `VM.classloader_stats` sau mỗi lần teardown và sau các cơ hội GC đủ điều kiện; so sánh loader count, số class và footprint.
- Quan sát `VM.metaspace` hoặc metric liên quan, nhưng **metaspace tăng không tự chứng minh một loader leak**; JVM có thể giữ committed memory để tái sử dụng.
- Đừng lấy số class loaded toàn JVM làm chỉ số duy nhất. Một hệ thống có dynamic proxy, reflection, lambda, JIT, hidden classes có thể nạp class mới bình thường.

Có thể bật unified logging của HotSpot để quan sát class unloading:

~~~bash
java -Xlog:class+unload=info -javaagent:agent.jar -jar application.jar
~~~

Đây là **lệnh mẫu production**, không phải lệnh chạy của demo ở phần 7. Khi biết rõ JVM hỗ trợ unified logging, sự kiện class unload chứng minh sự kiện đã xảy ra; **không thấy event ngay** không chứng minh chắc chắn leak.

### 10.2. Heap dump và GC roots

Nếu sau nhiều redeploy vẫn tồn tại nhiều loader thuộc phiên bản cũ, lấy heap dump/flight recording theo quy trình an toàn và xem **retained paths tới GC roots**:

~~~text
JVM static root
  -> AgentRegistry
  -> HashMap entry
  -> java.lang.Class<OldPlugin>
  -> OldPluginClassLoader
~~~

Hoặc:

~~~text
Worker Thread (sống lâu)
  -> contextClassLoader
  -> OldPluginClassLoader
~~~

Hoặc:

~~~text
System listener registry
  -> callback/lambda của plugin
  -> plugin object
  -> OldPluginClassLoader
~~~

Heap dump có thể lớn, làm tăng pause/memory/disk I/O và chứa dữ liệu nhạy cảm; chỉ lấy khi được cho phép, có đủ dung lượng và chính sách bảo vệ dữ liệu. Công cụ phân tích heap có thể giúp phân biệt **retained bytes** với **shallow size** và chỉ ra chính reference nào phải xóa. Không mặc định xóa một loader chỉ vì thấy nó tồn tại trong heap dump: xác minh đó thực sự là loader của deployment đã kết thúc.

### 10.3. Một phép thử GC có ý nghĩa hơn `System.gc()` đơn lẻ

Để test cơ chế unload trong môi trường riêng:

- Định nghĩa plugin bằng một loader tách biệt, chạy tác vụ rồi **hoàn tất lifecycle** của plugin.
- Hủy đăng ký callback/transformer, đóng resource, xóa cache và rời scope chứa các biến local mạnh.
- Giữ **`WeakReference<ClassLoader>`** làm quan sát, nhưng không giữ thêm `Class<?>`/loader trong static cache hoặc closure.
- Cho JVM có cơ hội GC ở môi trường test, kết hợp logs/statistics/weak-reference observations.
- Nếu weak reference chưa clear, đọc GC roots để tìm người giữ. **Không dùng timeout ngắn** để khẳng định chương trình đúng/sai tuyệt đối vì GC/class unloading không có thời hạn API cam kết.

Mục tiêu cuối cùng là **không còn strong reference path không mong muốn từ root đến loader đã hết vòng đời**, chứ không phải "GC nhất định phải diễn ra sau 100 ms".

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| "Dùng `WeakHashMap` thì loader chắc chắn unload." | Value được giữ mạnh; value có thể trỏ ngược key qua `Class<?>` | Kiểm tra đầy đủ graph key/value; weak value hoặc metadata không có loader ref |
| "Lưu `Class<?>` an toàn hơn lưu `ClassLoader`." | `Class<?>` của plugin vẫn gắn với defining loader | Tránh giữ cả hai trong long-lived global cache |
| "Cache chỉ lưu `Method` nên không giữ class." | Method reflection tham chiếu declaring class | Cache theo deployment hoặc metadata không sở hữu method |
| "Agent chỉ giữ transformer, không giữ loader." | Transformer có thể đóng trên loader, helper, lookup hoặc plugin object | Kiểm tra captured state; remove registration và xóa strong references |
| "`removeTransformer` là đủ để xóa agent." | Chỉ gỡ callback; bytecode, threads, metrics export và refs khác còn | Teardown đủ tài nguyên, không nhầm với unload/revert |
| "Class loader đã đóng file JAR tức là đã unload." | `URLClassLoader.close()` đóng resource tìm class, không bảo đảm class/loader GC | Đóng rồi bỏ refs; quan sát class unloading |
| "Hai class cùng tên là cùng một class." | Defining loader tạo danh tính thứ hai | Kiểm tra `Class.getClassLoader()`/module, không cache theo tên duy nhất |
| "`ClassValue` khiến mọi leak biến mất." | External roots có thể giữ loader bất kể cache per-class | Đánh giá toàn bộ GC root chain |
| "Không có sự kiện class unload là chắc chắn leak." | GC/class unloading không bắt buộc theo thời gian cố định | So sánh qua nhiều cycle, dùng heap analysis |
| "Gọi `System.gc()` xong weak reference còn thì lỗi." | `System.gc()` không là đồng bộ/hợp đồng bắt buộc unload | Không assert timing; tìm đường mạnh nếu có bằng chứng tồn tại kéo dài |
| "Cache theo tên class không bao giờ sai." | Hai loader có thể nạp cùng binary name; dữ liệu có thể bị trộn | Gắn ownership theo deployment hoặc per-class identity phù hợp |
| "Đếm mỗi callback thì cần giữ mọi `Class<?>`." | Đếm sự kiện không cần strong class map | Counter có nhãn thấp, không lưu loader/Class nếu không dùng |
| "Đóng plugin sẽ tự giải phóng `ThreadLocal`." | Thread pool chung có thể sống sau plugin và giữ value cũ | `ThreadLocal.remove()` và TCCL restoration trong `finally` |
| "ClassValue có thể enumerate toàn bộ các class đang cache." | `ClassValue` thiết kế per-type lazy association, không phải global key listing | Dùng telemetry giới hạn và ownership khác cho discovery |

## 12. Checklist thiết kế cho một Java agent dùng với hot deployment

- [ ] Có phân biệt **binary class name** với **class identity = name + defining loader**?
- [ ] Những `Class<?>`/`ClassLoader`/`Method`/`MethodHandle` được giữ **ở đâu**, bởi root nào, trong bao lâu?
- [ ] Cache thuộc agent sống lâu hay thuộc deployment ngắn hạn? Ai có quyền/lifecycle để dọn cache?
- [ ] Transformer có giữ plugin loader ở field, closure hoặc helper không?
- [ ] Có `removeTransformer` bằng **đúng instance**, đồng thời chờ/cho phép callback đang in-flight?
- [ ] Có hạn chế lưu object từ `transform(Module, ClassLoader, ..., Class<?>, ...)` không cần thiết?
- [ ] `WeakHashMap` value có strong reference quay lại key không? Có kiểm tra nested objects/lambda không?
- [ ] Metadata theo class có thể dùng `ClassValue` thay static strong `Map<Class<?>, V>` không?
- [ ] Registry yếu dùng `ReferenceQueue` có chính sách poll/drain và không phụ thuộc GC để business cleanup?
- [ ] Thread pools, TCCL, `ThreadLocal`, listener, MBean, exporter, scheduled tasks đã được dọn?
- [ ] `URLClassLoader`/resource được đóng khi owner thực sự kết thúc, không nhầm close với unload?
- [ ] Log/metric label có đủ để phân biệt deployment mà không lưu strong loader reference hay cardinality vô hạn?
- [ ] Có test nhiều vòng redeploy và so sánh classloader count, heap retained paths, metaspace, class unload logs?
- [ ] Có ghi nhận rằng **GC nondeterministic** và `System.gc()` không bảo đảm class unloading?
- [ ] Có kế hoạch rollback nếu một helper/agent class bị thiếu dẫn đến `NoClassDefFoundError` sau undeploy?

### Tình huống kiểm tra hiểu biết

**1.** Một agent static `ConcurrentHashMap<Class<?>, Metadata>` chứa entry của plugin cũ, nhưng ứng dụng đã xóa instance và gọi `URLClassLoader.close()`. Có thể có class loader leak không?

**Đáp án:** Có. Class object vẫn được giữ mạnh bởi static map của agent; close resource không loại bỏ GC root path đó.

**2.** Dùng `WeakHashMap<ClassLoader, Class<?>>`, key yếu, value là class được chính loader key định nghĩa. Có an toàn không?

**Đáp án:** Không. `Class<?>` value được map giữ mạnh và có đường tham chiếu tới loader key; key khó/không thể trở thành weakly reachable khi entry vẫn tồn tại.

**3.** Hai loader A/B tạo class có cùng tên, dùng `ClassValue<Counter>`. Counter có thể độc lập không?

**Đáp án:** Có. Hai đối tượng `Class<?>` khác nhau sẽ có associated value riêng. Đây là lý do dùng `ClassValue` cho metadata per-class phù hợp hơn cache có key chỉ là binary name.

**4.** Đã gỡ transformer, xóa map; nhưng thread của plugin vẫn đặt TCCL tới loader cũ. Có thể unload chưa?

**Đáp án:** Không nên kỳ vọng. Thread còn sống và giữ context loader tạo đường strong reference khác; phải quản lý TCCL và lifecycle của thread.

**5.** `WeakReference.get() != null` sau một lần `System.gc()`. Có thể kết luận leak chắc chắn?

**Đáp án:** Không. Cần kiểm tra GC có đủ cơ hội chạy không, scope còn local refs không, JIT/VM có giữ tạm references không, và tìm GC root path thật trong heap dump nếu triệu chứng kéo dài.

**6.** `removeTransformer(t) == true` và `cache.clear()` có đồng nghĩa instrumentation bytecode trong class đã load bị gỡ không?

**Đáp án:** Không. Gỡ transformer chỉ hủy đăng ký callback; class definition đã đổi có thể tiếp tục được sử dụng. Bài toán **hủy tham chiếu** và bài toán **hoàn nguyên bytecode** là hai việc độc lập.

**Kết luận:** Trong instrumentation, điều quan trọng không chỉ là *"agent giữ dữ liệu gì"* mà là *"dữ liệu đó sống lâu đến khi nào, ai còn giữ nó và nó dẫn tới class loader nào"*. Cache theo class phải tôn trọng vòng đời class; cache theo loader phải không tạo đường tham chiếu ngược từ value; và teardown phải chủ động dọn các root sống lâu. Chỉ khi loại bỏ những đường tham chiếu mạnh không còn cần thiết, JVM **mới có cơ hội** unload bộ nạp lớp cũ ở một chu kỳ GC phù hợp.

### Tài liệu chính thức

- [Java SE 17 — `ClassValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): associated value theo từng class, `get`/`computeValue`/`remove`.
- [Java SE 17 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): key yếu, value mạnh và bẫy value giữ ngược key.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html) và [`ReferenceQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): weak reachability và notification queue.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `addTransformer`, `removeTransformer` và contract callback đồng thời.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback và class loader identity khi transform.
- [JDK 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`.
