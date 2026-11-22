# 12.10. Nhận diện collection, cache, listener, ThreadLocal hoặc class loader giữ dữ liệu

## 1. Mục tiêu và câu hỏi chẩn đoán

Khi heap liên tục tăng, điều quan trọng không chỉ là biết **lớp nào chiếm nhiều bộ nhớ**, mà phải chỉ ra **chuỗi tham chiếu nào đang giữ các đối tượng đáng lẽ đã hết vòng đời nghiệp vụ**. Năm nhóm thủ phạm thường gặp là collection, cache, listener, `ThreadLocal` và class loader. Chúng có đặc điểm chung: một đối tượng sống lâu hơn giữ tham chiếu mạnh đến dữ liệu thuộc một công việc, request, session hoặc lần triển khai đã kết thúc.

Sau bài học, bạn có thể:

- Đọc heap dump để đi từ đối tượng được giữ → container/registry → GC root, phân biệt **shallow heap**, **retained heap**, **incoming references**, **dominator**.
- Nhận diện năm kiểu giữ dữ liệu qua cấu trúc đồ thị tham chiếu, triệu chứng, bằng chứng và vòng đời sở hữu.
- Phân biệt “có nhiều đối tượng” với **memory leak thực sự**, đồng thời tránh quy kết mọi cache lớn hoặc class loader tồn tại là lỗi.
- Dùng Eclipse Memory Analyzer (MAT) tìm retained size, đường đến GC root, kiểm tra thread, class loader; so sánh snapshot trước/sau cleanup.
- Nêu biện pháp sửa tại **điểm tạo và giải phóng tham chiếu**, kiểm chứng rằng dữ liệu hết hạn có thể được thu gom.

Phạm vi là **Java heap dump và object retention**. Phần lớn metadata class nằm ở Metaspace (native memory), nên một dump heap có thể tìm thấy tham chiếu giữ loader nhưng không phản ánh toàn bộ byte Metaspace.

## 2. Nguyên lý: GC thu gom theo khả năng truy cập, không theo “đã dùng xong”

GC đánh dấu các đối tượng còn có thể truy cập từ **GC roots**, ví dụ tham chiếu trong stack của thread đang hoạt động, tham chiếu tĩnh của các class còn sống, tham chiếu JVM/native được đăng ký làm root. Nếu một đối tượng hết giá trị nghiệp vụ vẫn reachable từ root qua chuỗi strong references, GC không thể tự suy rằng lập trình viên muốn giải phóng nó.

Ví dụ luồng giữ dữ liệu:

~~~text
GC Root
  -> application singleton / class đang sống
  -> static Map<String, Report>
  -> HashMap table / Node
  -> value Report
  -> List<ReportRow>
  -> byte[] hoặc String[] / nhiều đối tượng nhỏ
~~~

Giả sử một báo cáo chỉ dùng trong một request nhưng được đưa vào map không có chính sách loại bỏ. Request kết thúc không thay đổi đường tham chiếu từ singleton đến báo cáo. Đây là **retention vượt quá vòng đời mong muốn**. Heap dump chứng minh đường giữ tại thời điểm chụp; để kết luận là “leak”, cần thêm bằng chứng rằng dữ liệu **đáng lẽ phải hết hạn** và vẫn tích lũy qua thời gian.

### Bốn khái niệm bắt buộc phân biệt

| Khái niệm | Ý nghĩa | Cách dùng đúng |
| --- | --- | --- |
| **Shallow heap** | Bộ nhớ của chính object (header và field; với array bao gồm phần tử của array) | Một `ArrayList` có shallow size nhỏ dù giữ hàng triệu entry |
| **Retained heap** | Bộ nhớ của object và mọi object khác sẽ trở nên không còn reachable nếu object đó được loại khỏi đồ thị (theo mô hình MAT) | Tìm nơi “giữ” cả một cụm dữ liệu |
| **Dominator** | Object X dominates Y khi mọi đường từ root đến Y đều đi qua X | `Dominator Tree` giúp tìm điểm tích tụ; cạnh cây dominator không nhất thiết là field reference thật |
| **Path to GC Roots** | Một hoặc nhiều chuỗi tham chiếu đi ngược từ suspect đến root | Giải thích **ai** giữ; kiểm tra thêm đường khác nếu tồn tại nhiều owner |

**Lưu ý:** một object lớn có thể được nhiều nơi tham chiếu nên retained size của từng nơi không cộng đơn giản bằng dung lượng object. “Shortest path to GC root” cung cấp manh mối, không nhất thiết duy nhất hoặc đủ để kết luận ownership. Hãy xem incoming references và nhiều đường giữ khi cần.

## 3. Quy trình điều tra từ triệu chứng đến nguyên nhân

### Bước 1: Xác nhận hiện tượng tăng bộ nhớ

Quan sát cùng một loại tải trong vài chu kỳ: heap **used sau GC**, tốc độ tăng các live objects, GC frequency/pause, lượng request/session còn hoạt động, số entry trong cache, số lượng thread và số lần deploy. Heap lớn ngay sau cấp phát chưa chắc là leak; JVM có thể giữ heap **committed** để tái sử dụng dù live objects đã giảm.

Ví dụ: sau 10.000 request và khi mọi request hoàn thành, số `ReportContext` còn sống tăng từ 10 lên 10.010 và `Listener` tăng tương ứng. Mẫu hình này đáng điều tra hơn một lần snapshot với hàng nghìn object đang phục vụ 10.000 request **thật sự đang mở**.

### Bước 2: Chọn thời điểm lấy heap dump phù hợp

Trước hết xác minh PID JVM thật sự. Với HotSpot/JDK hỗ trợ `jcmd`:

~~~bash
# Thay <pid> bằng PID thật; chạy trên máy/namespace có quyền truy cập JVM
jcmd <pid> VM.version
jcmd <pid> GC.heap_info
jcmd <pid> GC.heap_dump /path/to/heap-before.hprof
~~~

`GC.heap_dump` tạo file HPROF của heap; trên các bản HotSpot hiện đại, mặc định nó yêu cầu full GC trừ khi dùng `-all`. Dump có thể gây pause, tốn I/O/disk và chứa dữ liệu nhạy cảm từ ứng dụng. Hãy chọn môi trường, cửa sổ và quyền truy cập phù hợp; dùng staging hoặc mẫu tái hiện được khi có thể. **Không bật `-all` để điều tra live-object leak nếu chưa hiểu rằng nó bao gồm cả object unreachable**; như vậy bạn có thể thấy “rác chưa dọn” nhưng tưởng là dữ liệu bị giữ.

Chụp snapshot trong trạng thái cần quan sát: sau khi workload đáng nghi đã kết thúc nhưng ứng dụng vẫn chạy; nếu muốn so sánh, giữ cùng JDK/cấu hình/tải và thời điểm tương ứng. Hai dump là bằng chứng hỗ trợ chứ không thể tự chứng minh leak khi workload khác nhau.

### Bước 3: Mở heap dump bằng Eclipse Memory Analyzer

1. **Overview / Leak Suspects Report**: dùng như điểm khởi đầu; báo cáo là heuristic, không phải phán quyết.
2. **Histogram**: tìm số instance và shallow size theo class; nhóm theo package hoặc **class loader** để nhận ra bản deploy cũ.
3. **Dominator Tree / Top Consumers**: tìm tập object giữ nhiều retained heap; mở theo cấp để xác định container hoặc cấu trúc tích tụ.
4. **Incoming References / Path to GC Roots**: từ một instance sống sai vòng đời, đi ngược đến root; chọn chế độ loại weak/soft/phantom references khi muốn tập trung vào đường giữ mạnh.
5. **Object Attributes / Collection Analysis**: đọc `size`, backing array, `Map.Node`, keys, cache entry, tên thread, thread-local value, callback/registry owner.
6. **Class Loader Explorer / Duplicate Classes**: xem loader nào định nghĩa class, số instance còn sống và liệu có loader cũ sau undeploy/redeploy.

Kết quả cần diễn đạt được thành một chuỗi cụ thể, ví dụ: “`ApplicationRegistry.listeners` (singleton ứng dụng) còn chứa `ExportListener` của phiên đã hủy; listener giữ `SessionContext`; ~18 MB object dưới context không còn được sử dụng.” Một màn hình histogram chỉ có `byte[]` lớn **chưa đủ**.

## 4. Dấu hiệu nhận diện năm nhóm giữ dữ liệu

| Nhóm | Đường tham chiếu thường thấy | Dấu hiệu đáng ngờ | Câu hỏi xác minh |
| --- | --- | --- | --- |
| Collection | `static List/Map/Set -> backing array/entry -> value` | `size` tăng theo request/user/file đã xong; rất nhiều entry tương tự | Ai thêm, khi nào remove, collection sống bao lâu? |
| Cache | `singleton cache -> entry -> key/value` | Không giới hạn size/weight/TTL; value là đồ thị rất lớn; key không bao giờ bị loại | Key có cardinality vô hạn? Có eviction/expiry thật? |
| Listener | `event bus/registry -> callback -> captured owner/payload` | Listener đăng ký mỗi lần tạo màn hình/session, không unregister | Có cleanup theo lifecycle? Còn event consumer thật? |
| `ThreadLocal` | `live pooled Thread -> threadLocals -> Entry.value` | Request xong mà context nằm trên worker thread lâu dài | Có `remove()` trong `finally` trên chính thread set? |
| Class loader | `long-lived registry/thread -> plugin object/Class/TCCL -> old ClassLoader` | Nhiều loader cho cùng module qua các lần redeploy; class cũ không unload | Loader cũ còn được root nào giữ? Close resources và deregister đủ chưa? |

Các đường trên là **mẫu khái niệm**; cấu trúc field và hiển thị của MAT thay đổi theo JDK/framework. Đừng cố khớp một đường cố định cho tất cả dump.

### 4.1. Collection: container sống lâu giữ phần tử ngắn hạn

Tình huống: một service có `static final List<RequestInfo> HISTORY`, mỗi request hoàn thành lại `HISTORY.add(info)`, không bao giờ xóa. `ArrayList` chỉ quản lý tham chiếu, không hiểu bản ghi nào đã hết giá trị.

Trong dump, một số hàng triệu `RequestInfo` có thể được giữ qua:

~~~text
GC root -> class Service -> static HISTORY
         -> ArrayList.elementData -> RequestInfo -> request body / attachments
~~~

Những điều cần kiểm tra:

- `size` thực, số entry duy nhất, độ sâu đồ thị sau mỗi entry; top-level `ArrayList` nhỏ nhưng backing array và phần tử có thể lớn.
- Entry là dữ liệu cần thiết hay dữ liệu của request/session đã đóng? Có limit tổng số lượng/số byte/tuổi dữ liệu?
- `Map` có key là object nhiều dữ liệu, value lớn hoặc vòng reference ngoài ý muốn? Key và value đều có thể bị giữ.
- Có “remove khỏi map A” nhưng vẫn còn trong list B/queue C không? Một đường GC root còn tồn tại là đủ để giữ object.
- Với `ConcurrentHashMap`, `CopyOnWriteArrayList`, cache wrapper..., có thể cần mở nhiều tầng Node/table/wrapper; đừng dựa vào tên class wrapper như chủ thể thực sự.

**Sửa đúng:** gắn collection với lifetime phù hợp; remove trong `finally` hoặc callback đóng phiên; giới hạn lịch sử, dùng queue có dung lượng cố định và backpressure khi cần. Chuyển từ `List` sang `Set` không tự giải quyết leak nếu dữ liệu vẫn không được xóa.

### 4.2. Cache: lưu có mục đích, nhưng thiếu giới hạn hoặc chiến lược hết hạn

Cache hợp lệ được phép giữ các object sau request để tăng hit rate. Vì vậy **cache có retained heap cao chưa đủ kết luận leak**. Nghi vấn tăng khi key tăng mãi như `userId + timestamp`, value là graph lớn, TTL không hoạt động, không có size/weight limit hoặc cache chỉ xóa sau khi truy cập lại.

~~~text
GC root -> singleton CacheManager
         -> Map table -> Entry(key = unique-request-id, value = byte[])
~~~

Cần ghi lại hit/miss, entry count, estimated weight, eviction count và cấu hình TTL, maximum size/weight. **Maximum entry count** không tương đương **maximum bytes** nếu các entry có kích thước rất khác nhau. TTL chỉ quy định tính hợp lệ logic; thời điểm/chiến lược vật lý loại bỏ entry phụ thuộc implementation, có thể cần maintenance/eviction khi cache ít được truy cập.

Ví dụ giới hạn **số entry** trong `LinkedHashMap` đơn luồng; không phải cache đa luồng production hoàn chỉnh:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

class BoundedHistory {
    private final Map<String, byte[]> recent =
        new LinkedHashMap<String, byte[]>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, byte[]> eldest) {
                return size() > 100;
            }
        };
}
~~~

Cấu hình `accessOrder = true` hỗ trợ LRU, `removeEldestEntry` xóa entry cũ khi thêm entry mới; **không** tự dọn các nơi khác vẫn tham chiếu value. `LinkedHashMap` mặc định không thread-safe; ứng dụng nhiều thread nên dùng cache có eviction, weight/TTL, concurrency và monitoring thích hợp.

`WeakHashMap` không phải “thuốc chữa leak” vạn năng: nó dựa trên weak **key**, trong khi value vẫn mạnh; nếu value tham chiếu ngược lại key, key có thể vẫn reachable. Chỉ đổi kiểu map khi ownership thực sự phù hợp với weak-reference semantics.

### 4.3. Listener và callback: đăng ký nhưng không hủy

Ví dụ một object view đăng ký callback với event bus toàn cục. Trong callback, lambda capture `this`, model, session hoặc mảng lớn. View bị đóng nhưng event bus vẫn giữ callback:

~~~text
GC root -> global EventBus
         -> listeners -> lambda/Listener
         -> captured ViewModel
         -> model -> session objects
~~~

Điều tra bằng cách tìm `EventBus`/`PropertyChangeSupport`/registry trong Dominator Tree hoặc incoming refs từ `ViewModel`. Kiểm tra listener count tăng theo mỗi lần mở/đóng view, có duplicate registrations, và liệu callback đã vô hiệu nhưng vẫn nằm trong registry.

Sửa bằng hợp đồng **subscribe/unsubscribe** rõ ràng. Đăng ký phải có lifecycle owner và token/callback đúng để remove, ví dụ (đoạn minh họa API giả định, không phải chương trình độc lập):

~~~java
Registration registration = eventBus.subscribe(event -> handle(event));
try {
    runScreenOrSession();
} finally {
    registration.close(); // Thực sự xóa callback khỏi registry
}
~~~

Nếu framework cung cấp `AutoCloseable`, `Disposable`, lifecycle hook hoặc quản lý subscription, dùng cơ chế đó. Một “listener yếu” chỉ phù hợp nếu event handler có thể tự mất; không tùy tiện chuyển mọi listener sang weak reference vì có thể khiến sự kiện hợp lệ bị bỏ lỡ.

### 4.4. ThreadLocal: value tồn tại theo vòng đời **thread**, không theo request

`ThreadLocal<T>` lưu giá trị riêng cho từng thread. Trong thread pool, thread có thể sống hàng giờ qua hàng nghìn request. Nếu task gọi `set(context)` nhưng quên `remove()`, context của request cũ có thể được giữ lâu sau khi request kết thúc hoặc rò sang task tiếp theo nếu code đọc lại cùng `ThreadLocal`.

~~~text
GC root -> live worker Thread
         -> Thread.threadLocals -> ThreadLocalMap.Entry
         -> Entry.value = RequestContext -> payload / User / buffer
~~~

Với implementation `ThreadLocalMap` của OpenJDK, **key là weak reference tới `ThreadLocal`, nhưng `Entry.value` vẫn là strong reference**. Một entry có key đã bị GC có thể trở thành “stale entry”; việc dọn stale entry diễn ra theo các thao tác của map và không bảo đảm tức thì. Vì vậy **không** xử lý leak bằng cách gán biến `ThreadLocal = null` hoặc trông chờ key yếu; xử lý đúng là gọi `remove()`.

Cách đặt trong `finally`, ngay **trên thread đã gọi `set`** (đoạn minh họa phương thức, cần định nghĩa `Request` và `handle` trong ứng dụng thực):

~~~java
private static final ThreadLocal<Request> CURRENT = new ThreadLocal<>();

void process(Request request) {
    CURRENT.set(request);
    try {
        handle(request);
    } finally {
        CURRENT.remove();
    }
}
~~~

Cần phân biệt:

- `remove()` trên thread A **không xóa** value mà thread B đã `set`.
- Chỉ gọi `set(null)` không thể hiện lifecycle rõ bằng `remove()`; với `ThreadLocalMap`, nên dùng `remove` để xóa entry.
- `InheritableThreadLocal` còn có thể lan trạng thái theo cơ chế tạo thread; executor/pool và asynchronous callbacks cần chính sách truyền/xóa context được thiết kế, không mặc định suy diễn rằng state theo request.
- ThreadLocal không thích hợp để truyền request context một cách tự động qua mọi coroutine/virtual thread/async task. Virtual thread thường có vòng đời ngắn, nhưng số lượng lớn value vẫn có thể tốn memory trong lúc chúng còn sống.
- Trong MAT, kiểm tra **thread còn sống**, tên pool, `threadLocals`, giá trị thực và lifecycle task. Một value của request đang chạy là bình thường; value của request đã kết thúc nhiều giờ thì đáng nghi.

### 4.5. Class loader: dữ liệu của lần deploy cũ không được giải phóng

Mỗi class được nhận diện bởi **tên đầy đủ + class loader định nghĩa**, nên sau reload/redeploy có thể có nhiều class cùng tên được định nghĩa bởi các loader khác nhau. Trường hợp bình thường: loader cũ cùng các class và instance của nó trở nên unreachable khi plugin/ứng dụng con được unload, và JVM có thể thu gom/unload khi điều kiện phù hợp. Trường hợp leak: hệ thống sống lâu hơn vẫn giữ ít nhất một đối tượng của plugin cũ hoặc loader của nó.

Ví dụ đường giữ:

~~~text
GC root -> host application EventBus (loader sống lâu)
         -> listener instance của plugin v1
         -> plugin Class -> defining ClassLoader v1
         -> lớp, instance và metadata liên quan còn bị giữ
~~~

Các đường phổ biến khác: global cache chứa `Class<?>`/`Method`/`MethodHandle` hay object plugin, thread còn chạy do plugin tạo, scheduler/driver/MBean/registry chưa unregister, hoặc `Thread.contextClassLoader` trỏ đến loader cũ. **Static field của class do chính loader cũ nạp không tự nó tạo một external GC root vĩnh viễn**: cần tìm xem loader/class/instance còn reachable từ thành phần sống lâu nào.

Trong MAT, dùng **Class Loader Explorer**, nhóm Histogram theo class loader, **Duplicate Classes** và `Path to GC Roots` của loader/object thuộc loader cũ. Đối chiếu version/deploy time và kiểm tra có bao nhiêu loader đã lẽ ra phải chết. Một số bản sao class là hợp lệ trong kiến trúc plugin hoặc isolation; chỉ tăng số loader sau mỗi redeploy cùng đường root ngoài ý muốn mới là chứng cứ mạnh.

**Sửa:** tháo đăng ký listeners, scheduler, task, MBeans, JDBC drivers hoặc resource do plugin mở khi unload; dừng threads của plugin và khôi phục context class loader nếu đã thay; xóa global maps/callbacks giữ class hoặc instance; đóng `URLClassLoader` khi phù hợp. `URLClassLoader.close()` đóng tài nguyên loader mở (ví dụ JAR handles), **không cưỡng bức unload class** nếu object/class/loader vẫn còn reachable.

Lưu ý: Metaspace nằm ngoài Java heap. HPROF cho thấy dấu hiệu loader và object retention, nhưng không phải toàn bộ biểu đồ native memory. Đối chiếu NMT/JFR hoặc memory metrics phù hợp nếu nghi Metaspace tăng.

## 5. Bài thực hành Java 17+: tạo năm chuỗi giữ dữ liệu có chủ đích

Bài lab có hai tệp nguồn, không cần thư viện ngoài JDK. Nó chủ động giữ vài mảng byte để **dễ tìm đường trong heap dump**; đây là fixture chẩn đoán, không phải kiến trúc ứng dụng khuyến nghị. Tạo một thư mục làm việc mới và đặt hai tệp trong đó.

**Tệp `ExamplePlugin.java`** (chỉ được biên dịch vào `plugin-out/`, để class loader ứng dụng không nhìn thấy `ExamplePlugin.class` trực tiếp):

~~~java
public final class ExamplePlugin implements Runnable {
    private final byte[] payload = new byte[1_000_000];

    @Override
    public void run() {
        System.out.println("plugin bytes=" + payload.length);
    }
}
~~~

**Tệp `LeakRetentionLab.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LeakRetentionLab {
    static final List<byte[]> COLLECTION = new ArrayList<>();
    static final Map<String, byte[]> CACHE = new HashMap<>();
    static final List<Runnable> LISTENERS = new ArrayList<>();
    static final ThreadLocal<byte[]> LOCAL = new ThreadLocal<>();

    private static void registerLambdaListener() {
        byte[] captured = new byte[2_000_000];
        LISTENERS.add(() -> System.out.println("listener bytes=" + captured.length));
    }

    private static void registerPluginListener() throws Exception {
        URL pluginDir = Path.of("plugin-out").toAbsolutePath().toUri().toURL();

        // Loader con nạp ExamplePlugin. Host giữ Runnable trong static registry.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginDir },
                LeakRetentionLab.class.getClassLoader())) {
            Class<?> type = Class.forName("ExamplePlugin", true, loader);
            LISTENERS.add((Runnable) type.getDeclaredConstructor().newInstance());
        }
        // close() đã xong, nhưng LISTENERS vẫn giữ instance của plugin.
    }

    public static void main(String[] args) throws Exception {
        long pauseMs = args.length == 0 ? 60_000L : Long.parseLong(args[0]);

        COLLECTION.add(new byte[3_000_000]);
        CACHE.put("historical-report", new byte[4_000_000]);
        registerLambdaListener();
        registerPluginListener();

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Task kết thúc nhưng worker thread sống trong pool:
            pool.submit(() -> LOCAL.set(new byte[5_000_000])).get();

            System.out.println("BEFORE_CLEANUP pid=" + ProcessHandle.current().pid());
            Thread.sleep(pauseMs); // Chụp heap-before.hprof trong khoảng này.
        } finally {
            // remove() phải chạy trên chính worker thread đã set().
            pool.submit(LOCAL::remove).get();
            pool.shutdown();
            COLLECTION.clear();
            CACHE.clear();
            LISTENERS.clear();
        }

        System.out.println("AFTER_CLEANUP pid=" + ProcessHandle.current().pid());
        Thread.sleep(pauseMs); // Có thể chụp heap-after.hprof.
    }
}
~~~

Biên dịch/chạy trong thư mục đó:

~~~bash
mkdir plugin-out
javac -d plugin-out ExamplePlugin.java
javac LeakRetentionLab.java
java -cp . LeakRetentionLab
~~~

Dòng output có dạng dưới đây; PID là **giá trị thật thay đổi theo lần chạy**:

~~~text
BEFORE_CLEANUP pid=<pid thực tế>
AFTER_CLEANUP pid=<pid thực tế>
~~~

Hai dòng in ra cách nhau khoảng 60 giây khi dùng tham số mặc định. Dùng `java -cp . LeakRetentionLab 10` để smoke test nhanh (10 ms mỗi pha); khi cần dump, dùng thời gian đủ dài, ví dụ `60000`. Không gọi `run()` của listener/plugin nên chúng không in thêm text.

Trong terminal khác, khi đã thấy `BEFORE_CLEANUP`:

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap-before.hprof
~~~

Khi đã thấy `AFTER_CLEANUP` (và JVM vẫn sống):

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap-after.hprof
~~~

Nếu JDK và điều kiện GC cho phép, dump sau cleanup có thể cho thấy các object fixture đã không còn reachable. Tuy nhiên **không cam kết** giảm chính xác 15 MB hay class loader sẽ unload ngay: dung lượng thật còn có overhead; GC timing, Java stack và JVM implementation có thể ảnh hưởng snapshot. Tệp dump phải đủ chỗ và thao tác có thể gây pause.

**Vì sao lab phù hợp để truy ngược:**

| Dữ liệu | Root/đường giữ trong pha trước cleanup | Hành động cleanup |
| --- | --- | --- |
| `3_000_000` byte | Static `COLLECTION -> ArrayList.elementData -> byte[]` | `COLLECTION.clear()` |
| `4_000_000` byte | Static `CACHE -> HashMap.Node -> byte[]` | `CACHE.clear()` |
| `2_000_000` byte | Static `LISTENERS -> lambda -> captured byte[]` | `LISTENERS.clear()` |
| `5_000_000` byte | Live executor worker `Thread -> threadLocals -> Entry.value` | `LOCAL.remove()` trong chính worker |
| Plugin `1_000_000` byte | Host `LISTENERS -> ExamplePlugin instance -> Class/loader` | Remove listener; loader đã close resources |

Điểm mấu chốt của plugin: `ExamplePlugin.class` chỉ nằm trong `plugin-out`; chương trình host phải chạy với classpath chỉ gồm `.`. Nếu trước đó bạn có `ExamplePlugin.class` ngay trong thư mục host hoặc thêm `plugin-out` vào classpath, parent loader có thể nạp class và bài test không còn tái hiện quan hệ child loader mong muốn. Hãy bắt đầu từ thư mục sạch.

## 6. Đọc kết quả lab và thu thập bằng chứng không nhầm lẫn

**Collection/cache:** tìm các byte arrays có kích thước gần đúng với fixture, chọn instance rồi xem **incoming references**. Với collection, đi đến `ArrayList.elementData` rồi static `COLLECTION`; với cache, đi qua `HashMap.Node.value` đến static `CACHE`. Histogram chỉ hiển thị nhiều `byte[]` mà không nói nó thuộc vùng nào. `Retained heap` giúp lượng hóa phần dữ liệu phụ thuộc vào container, nhưng có thể khác dung lượng mảng vì các đường tham chiếu khác nhau.

**Listener:** tìm mảng `2_000_000` byte, xem lambda class và field capture; tiếp tục đến `LISTENERS`. Cần truy tận owner của registry, vì xóa biến local `captured` sau khi tạo lambda không xóa tham chiếu nằm trong callback.

**ThreadLocal:** tìm mảng `5_000_000` byte, kiểm tra `Thread -> threadLocals -> Entry.value` và executor thread còn sống. Không nhầm nó với dữ liệu có trên local stack của task đã kết thúc; chính worker thread và `ThreadLocalMap` giữ value khi không remove.

**Class loader:** xem `ExamplePlugin` trong Histogram theo class loader hoặc `Class Loader Explorer`. Truy từ instance trong `LISTENERS` đến class do `URLClassLoader` định nghĩa. Sau khi registry xóa callback và không còn đường root khác, loader cũ có điều kiện trở thành collectible; việc nó đã đóng JAR **không** chứng minh class có thể unload ngay. Một đường khác từ `Thread.contextClassLoader` hoặc một registry khác (nếu ứng dụng thật có) vẫn có thể giữ loader.

**So sánh trước/sau:** kiểm tra số lượng class/instance tương ứng và các root paths biến mất sau khi cleanup. Nếu vẫn thấy đối tượng ở dump sau, điều tra mọi đường mạnh còn tồn tại và local references tạm thời. So sánh “heap size” tổng đơn thuần không đủ để đánh giá thay đổi của 5 nhóm. Hãy đối chiếu retained set và vòng đời nghiệp vụ.

Một cách ghi bằng chứng ngắn gọn, đủ để chuyển cho người sửa:

~~~text
Suspect: 1_200 ReportContext giữ sau khi batch kết thúc
Expected lifetime: một batch; actual: tồn tại >30 phút
Retainer: AppCache.entries -> HashMap.Node.value -> ReportContext
GC root: application singleton class
Growth: +200 ReportContext sau mỗi batch mới, không giảm sau cleanup
Likely cause: cache key theo batchId nhưng thiếu invalidation/eviction
Fix hypothesis: remove batchId cuối batch + bound maximum weight
Validation: run cùng workload, kiểm tra entry count và dump sau GC
~~~

Số liệu trong biểu mẫu này là **ví dụ minh họa**, không phải kết quả của lab hoặc một hệ thống thực tế.

## 7. Những trường hợp dễ chẩn đoán sai

| Quan sát | Kết luận vội cần tránh | Bằng chứng bổ sung |
| --- | --- | --- |
| `HashMap` retained heap lớn | “Mọi cache đều leak” | Cache có limit, TTL/eviction, tỷ lệ hit và số entry ổn định khi tải ổn định không? |
| `byte[]` rất nhiều | “byte[] là nguyên nhân gốc” | Ai giữ byte[]? Ảnh/file/network payload nào đang hợp lệ? |
| `ArrayList` chưa rỗng | “Request đã xong nên List phải rỗng” | Collection có phải history/audit/queue hợp lệ không? Có TTL và SLA không? |
| Một `ThreadLocalMap` giữ context | “Cứ có ThreadLocal là leak” | Context có thuộc task đang chạy không? Thread có được tái sử dụng lâu không? |
| Nhiều class cùng tên | “Chắc chắn class loader leak” | Có phân vùng plugin hợp lệ không? Loader bản cũ còn sau undeploy không? |
| `Metaspace` tăng | “Heap dump phải chứa đủ byte Metaspace” | Loader graph + NMT/JFR/process native memory; heap chỉ là một phần bức tranh |
| Heap used chưa giảm sau `clear` | “GC không giải phóng” | Đang xem used hay committed? Có đường giữ khác? Có GC tương ứng chưa? |
| GC root là thread | “Thread đó luôn là thủ phạm” | Stack local chỉ tạm thời hay ThreadLocal/task registry giữ xuyên request? |

**GC path có nhiều loại reference.** MAT thường cho tùy chọn loại weak/soft/phantom khi tìm đường. Một weak reference duy nhất không đủ chứng minh object bị giữ mạnh. Ngược lại, “soft reference” có chính sách thu gom theo áp lực memory; không dùng như hợp đồng TTL và không lấy sự hiện diện của nó làm bằng chứng duy nhất. Kiểm tra tất cả strong paths và xác nhận liệu một đường được loại có làm mất retainability hay không.

**Heap dump có tính thời điểm.** Báo cáo Leak Suspects dựa trên snapshot và dominance, không biết khi nào object được tạo hoặc business event nào đã kết thúc. Nhiều snapshot cùng metadata, allocation profiling/JFR, số request và counters ứng dụng giúp xác nhận xu hướng. Khi cần bằng chứng leak rất khó tái hiện, hãy đưa timeline vào báo cáo thay vì khẳng định từ một ảnh.

## 8. Quy tắc sửa tại đúng vòng đời

Đừng bắt đầu bằng `System.gc()` hoặc tăng `-Xmx` để “sửa leak”. Hai biện pháp đó không xóa một tham chiếu mạnh còn reachable. Hãy xử lý trong mã tạo ownership:

1. **Collection:** ai `add` phải xác định điều kiện `remove/clear`; bounded queue hoặc retention policy cho dữ liệu lịch sử.
2. **Cache:** giới hạn size **và/hoặc weight**, expiry, invalidation khi sự kiện thay đổi; đo kích thước và eviction. Tránh cache theo key có cardinality vô hạn.
3. **Listener:** đăng ký một lần đúng phạm vi, lưu token, unregister ở `close`/`dispose`/`finally`; tránh lambda capture cả object lớn khi chỉ cần một ID bất biến nhỏ.
4. **ThreadLocal:** set và remove theo cùng task, cùng thread; luôn dùng `try/finally`; audit thư viện ngầm ghi request context vào pooled thread.
5. **Class loader:** khi undeploy, tháo registry/callbacks, hủy scheduled jobs, dừng threads plugin, xóa caches tham chiếu `Class`/`Method`/instance, khôi phục TCCL nếu thay; đóng loader/resources và kiểm tra unload eligibility.

Sau khi sửa, chạy **cùng kịch bản**: lặp tạo/sử dụng/đóng 100 hoặc 1.000 session/plugin/task; đo số object còn sống sau mỗi chu kỳ và retained heap của owner; chụp heap dump ở trạng thái ổn định. Kỳ vọng **plateau** hoặc giảm sau cleanup, không tăng theo số chu kỳ đã hoàn tất. Nếu ứng dụng chứa long-lived caches hợp lệ, ghi rõ upper bound mong đợi và so với số thực.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Trong MAT, `ArrayList` shallow heap chỉ vài chục byte nhưng retained heap hàng trăm MB. Vì sao? Vì container qua backing array đang giữ đồ thị object con; phải xem root path và business lifetime trước khi gọi là leak.

**Câu 2.** Một `Map<SessionId, SessionData>` tăng không ngừng, dù session hết hạn. Tìm ở đâu? Kiểm tra entry count, TTL/eviction thực, chuỗi singleton → map → value và có invalidate theo session-close không.

**Câu 3.** Listener bị unsubscribe nhưng view model vẫn sống. Điều gì tiếp theo? Tìm **các** incoming references và root paths khác, gồm scheduler, cache, callback khác, stack đang chạy, thread/task registry; unsubscribe một nơi không bảo đảm không còn reference nào.

**Câu 4.** `ThreadLocal` được tạo bằng biến local, rồi biến local hết scope. Value có chắc được dọn? Không. Trong OpenJDK, key weak nhưng value strong có thể tồn tại trong stale entry của thread còn sống. Dùng `remove()` trên đúng thread khi kết thúc request.

**Câu 5.** Đã gọi `URLClassLoader.close()` nhưng MAT vẫn thấy `PluginV1`. Có phải JVM lỗi không? Không. Close giải phóng tài nguyên I/O; cần loại bỏ mọi root path đến loader/class/instance trước khi class unloading có thể diễn ra.

**Câu 6.** Heap dump sau cleanup vẫn có object nhưng `GC.heap_dump -all` đã được dùng. Kết luận nào cần sửa? Dump bao gồm cả unreachable, không thể dựa vào sự hiện diện thuần túy của object để suy “root vẫn giữ”; hãy xác minh reachability và lựa chọn dump.

**Câu 7.** Sau ba vòng deploy, 3 class loader chứa cùng class name xuất hiện. Chứng minh leak thế nào? Xác định loader nào thuộc phiên đã undeploy, xem path to GC roots, instance nào của phiên cũ được giữ, rồi theo dõi sau cleanup/GC; không quy kết chỉ từ duplicate classes.

## Tài liệu đối chiếu

- Eclipse MAT: [Basic Tutorial — Histogram, Dominator Tree, Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html).
- Eclipse MAT: [Finding Memory Leak — quy trình và truy vấn](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html).
- Eclipse MAT: [Analyzing Class Loader](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/analyzingclassloader.html) và [Duplicate Classes](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/duplicate_classes.html).
- Oracle Java SE 25: [ThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html) — vòng đời và `remove()`.
- OpenJDK: [ThreadLocalMap implementation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/ThreadLocal.java) — weak key, strong value và stale entries của implementation hiện tại.
- Oracle Java SE 25: [jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — `GC.heap_dump`, `-all` và tác động vận hành.
