# Rò rỉ bộ nhớ Java khi đối tượng vẫn được giữ bởi cache, listener hoặc ThreadLocal

Java có Garbage Collector (GC), nhưng **có GC không đồng nghĩa ứng dụng không thể bị rò rỉ bộ nhớ**. GC thu hồi những object **không còn reachable theo các quy tắc reachability**; nó không thể tự kết luận rằng một object tuy còn đường tham chiếu mạnh nhưng đã **hết giá trị nghiệp vụ**. Nếu một cache không có giới hạn, một listener không được hủy đăng ký hoặc một `ThreadLocal` giữ dữ liệu qua hàng nghìn request, object vẫn có thể reachable và liên tục tiêu thụ heap.

Bài học đặt trong chủ đề **khả năng truy cập (reachability)** trên JVM, dùng **Java 17** cho code và API. Cần phân biệt rõ **memory leak logic** (object không còn cần nhưng vẫn bị giữ sống), **allocation nhiều nhưng đã thu hồi**, **cache cố ý giữ dữ liệu**, và **native memory leak**. Các ví dụ tập trung vào ba nguồn giữ tham chiếu phổ biến: **cache, listener, ThreadLocal**; sau đó trình bày cách tìm **path to GC roots**, đọc heap dump và thiết kế vòng đời giải phóng tài nguyên.

**Thông điệp chính:** khi điều tra rò rỉ bộ nhớ Java, đừng chỉ hỏi “object nào tăng?”; hãy hỏi thêm **“ai đang giữ reference tới object đó và tại sao đường giữ sống ấy chưa được cắt?”**

## 1. Khả năng truy cập là cơ chế quyết định điều gì có thể bị thu gom

Trong mô hình heap của JVM, objects và arrays có thể tham chiếu lẫn nhau. GC nhận diện objects cần giữ dựa vào một tập **GC roots** và những đường tham chiếu hợp lệ đi từ roots vào object graph.

```text
GC root: static field APP_CACHE
    |
    v
ConcurrentHashMap
    |
    v
Map entry -> CachedResult -> List -> byte[] rất lớn
                 ^
                 |
            nghiệp vụ đã hết cần, nhưng cache chưa xóa entry

GC vẫn nhìn thấy một đường tham chiếu mạnh từ root đến byte[].
Vì thế byte[] và các object trên đường giữ sống chưa thể được
thu hồi chỉ vì ứng dụng "không còn dùng" chúng nữa.
```

Một **strong reference** là tham chiếu thông thường, ví dụ field `Object value`, một phần tử trong `List` hay value trong `Map`. Các sources giữ sống thường gặp gồm:

- Static fields của các class còn sống, như `static final Map`, singleton, registries.
- Local variables/operand-stack references của **active thread frames**, trong khoảng mà VM thực sự còn xem chúng live.
- Instance fields và array elements được truy cập qua các object reachable khác.
- Những cấu trúc VM/JNI handles theo semantics tương ứng.
- Objects gắn với threads sống lâu, bao gồm các entries trong thread-local map.

**Object graph chứa chu trình không tự tạo memory leak.** Nếu `A.next = B` và `B.next = A` nhưng không có đường giữ sống từ GC roots tới A/B, tracing GC vẫn có thể thu gom cả chu trình. Java GC không phụ thuộc vào việc bạn chủ động phá mọi vòng reference như một hệ thống reference counting đơn giản.

### “Reachable” khác “còn có ích”

| Tình trạng | Reachability | Kết quả mong đợi |
| --- | --- | --- |
| Đối tượng đang phục vụ request | Reachable và còn cần | Giữ lại |
| Kết quả cache nằm trong chính sách size/TTL | Reachable và được phép giữ | Có thể giữ, đây không tự là leak |
| Listener của màn hình đã đóng nhưng vẫn được event bus giữ | Reachable, hết vòng đời sử dụng | **Logical memory leak** |
| Giá trị của request cũ trong thread pool worker `ThreadLocal` | Reachable qua thread đang sống, không còn cần | **Logical memory leak**, có thể thêm lỗi dữ liệu |
| Object không còn đường strong reachability | Có thể trở nên collectible theo quy tắc reference processing | GC có thể thu hồi khi thích hợp, **không có thời điểm bảo đảm** |

Không dùng việc `System.gc()` trả về để chứng minh một object đã được thu hồi; `System.gc()` chỉ là yêu cầu thực hiện GC và VM không cam kết thu hồi object nào ngay lập tức.

## 2. Bốn thuật ngữ quan trọng: allocation, retention, reachability, leak

1. **Allocation:** JVM tạo objects/arrays cho tính toán. Một ứng dụng xử lý nhiều request có thể allocate rất nhanh nhưng GC cũng có thể thu hồi nhanh.
2. **Retention:** các references giữ một tập objects sống qua thời gian. Một object nhỏ có thể giữ nguyên cả một cây dữ liệu lớn bên dưới.
3. **Reachability:** tồn tại hoặc không tồn tại đường đi từ GC roots qua các reference edges theo mô hình reachability.
4. **Memory leak logic:** giữ lại objects **không còn cần thiết** lâu hơn vòng đời thiết kế, thường khiến lượng memory cần giữ liên tục tăng hoặc không trở về mức kỳ vọng.

Không có một công thức “used heap lớn = leak”. Trong một JVM dùng GC, có thể quan sát heap usage dạng **răng cưa**: used tăng do allocations rồi giảm sau các lần collection. Nếu mức **post-GC live set** sau các workload tương đương cứ tăng và không ổn định, đó là dấu hiệu cần điều tra retention.

**Ngược lại, không có `OutOfMemoryError` cũng không chứng minh không có leak**: leak nhỏ có thể tích tụ nhiều ngày, hoặc vẫn nằm dưới heap limit tại thời điểm quan sát.

## 3. GC roots, paths và retained size

Xét sơ đồ:

```text
Root 1: Application.CACHE
   |
   +--> CacheEntry("account-1")
            |
            +--> Report
                  |
                  +--> List<Attachment>
                           |
                           +--> Attachment[1] --> byte[5 MiB]
                           +--> Attachment[2] --> byte[8 MiB]

Root 2: Worker Thread
   |
   +--> ThreadLocalMap
             |
             +--> RequestContext --> Report
```

Nếu cùng một `Report` reachable qua **hai đường**, xóa một cache entry **chưa đủ** thu hồi Report vì `ThreadLocalMap` vẫn giữ đường còn lại. Đây là lý do công cụ heap dump cho phép xem **Path to GC Roots**, **incoming references**, **dominator tree** và **retained size**.

Phân biệt kích thước:

- **Shallow size:** kích thước trực tiếp của object đó, không tính các objects nó tham chiếu.
- **Retained size:** tổng memory sẽ có khả năng được giải phóng về reachability nếu object này và các objects mà nó **giữ sống độc quyền** không còn reachable, theo mô hình dominator của heap snapshot.
- Một `HashMap` entry chỉ tốn ít byte shallow nhưng có thể giữ cả graph hàng chục MiB qua `value`.
- Nếu một object còn đường khác từ GC roots, nó **không nhất thiết** nằm trong retained set độc quyền của cache entry đang xét.

**Mối liên hệ cần nhớ:** trong việc tìm leak, object tăng nhanh quan trọng, nhưng **object/root nào giữ chúng lại** mới chỉ ra vị trí cần sửa. `byte[]` lớn không có nghĩa `byte[]` là thành phần lập trình lỗi.

### Cẩn trọng về thời điểm snapshot

Một heap dump là **ảnh chụp tại thời điểm cụ thể**, không tự chứng minh một object đã hết giá trị nghiệp vụ. Một cache đúng thiết kế cũng có thể có retained size lớn. Cần đặt dữ liệu vào bối cảnh lifecycle, lượng request, cache hit rate, cardinality và khoảng thời gian từ lúc object được tạo.

## 4. Nguồn leak thứ nhất: cache không có giới hạn hoặc không có cơ chế hết hạn

Một cache là cơ chế giữ objects **có chủ đích** để tái sử dụng. Nó trở thành leak khi chính sách giữ vượt khỏi nhu cầu ứng dụng, ví dụ:

- `static Map<String, Payload> CACHE` không có giới hạn kích thước.
- Mỗi request tạo key mới nên cache entry **không bao giờ được truy cập lại**, nhưng cũng không bao giờ bị xóa.
- Có TTL trên giấy nhưng không có hành động expire/cleanup thực tế, hoặc eviction chỉ chạy khi có thao tác mới.
- Cache key giữ toàn bộ request/session/context thay vì chỉ một định danh nhỏ, tạo đường giữ sống ngoài dự đoán.
- Cache value giữ object graph lớn: images, buffers, documents, response bodies, class loaders.
- Cache phân vùng theo tenant/user nhưng không gỡ entries khi tenant/user/session hết vòng đời.
- Một cache dùng cho “tối ưu” bị coi thành kho lưu trữ vĩnh viễn mà không có memory budget.

### Mẫu code không nên đưa vào production nếu cardinality tăng không giới hạn

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

class UnboundedCache {
    private static final Map<String, byte[]> CACHE =
            new ConcurrentHashMap<>();

    static void remember(String requestId, byte[] payload) {
        CACHE.put(requestId, payload);
    }
}
```

Đây là **class minh họa**, không có `main`. Nếu `requestId` luôn mới, map giữ mỗi `byte[]` vì static field `CACHE` là một đường root/owner sống dài. `ConcurrentHashMap` giải quyết **thread safety của map**, **không giải quyết giới hạn bộ nhớ**.

Một lần gọi `CACHE.clear()` có thể cắt đường giữ sống qua cache, nhưng không bảo đảm ngay sau lời gọi heap used hoặc RSS giảm tương ứng: vẫn có thể còn references khác và GC/heap commitment có cơ chế riêng.

### Cache đúng cần chính sách quản lý vòng đời

Có thể kết hợp:

- **Maximum entry count**: số entries không vượt quá một giới hạn.
- **Maximum weight**: budget theo ước lượng bytes/cost của value, phù hợp hơn khi kích thước entry chênh lệch lớn.
- **Time-based expiry**: expire after write/access nếu hợp lý với nghiệp vụ; không dùng TTL thay cho capacity bound một cách máy móc.
- **Eviction policy**: LRU/LFU/segmented, dựa vào hit/miss và workload.
- **Invalidation** khi thay đổi dữ liệu hoặc kết thúc session/tenant.
- **Explicit cleanup** cho value sở hữu resources như file handles/native buffers, vì xóa reference không phải là lời gọi `close()`.
- **Metrics**: cache entry count, estimated size/weight, eviction count, hit ratio, estimated retained bytes và phân vùng owner.

Một bounded cache có thể sử dụng memory đáng kể vì đó là **hành vi mong muốn**. Tính đúng là giữ trong budget và không tiếp tục tích tụ vô hạn.

## 5. Ví dụ Java 17 chạy được: bounded LRU cache bằng LinkedHashMap

Tạo file **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {

    static final class LruCache<K, V> extends LinkedHashMap<K, V> {
        private final int capacity;

        LruCache(int capacity) {
            super(16, 0.75f, true); // access-order
            if (capacity < 1) {
                throw new IllegalArgumentException("capacity");
            }
            this.capacity = capacity;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            return size() > capacity;
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> cache = new LruCache<>(3);

        cache.put(1, "one");
        cache.put(2, "two");
        cache.put(3, "three");

        cache.get(1);           // 1 là entry vừa được dùng gần nhất
        cache.put(4, "four");   // loại bỏ entry 2 (cũ nhất)

        System.out.println("size=" + cache.size());
        System.out.println("keys=" + cache.keySet());
        System.out.println("contains2=" + cache.containsKey(2));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 BoundedCacheDemo.java
java BoundedCacheDemo
```

**Stdout chính xác:**

```text
size=3
keys=[3, 1, 4]
contains2=false
```

Vì `LinkedHashMap` được bật **access-order**, lời gọi `get(1)` chuyển key 1 thành mới dùng gần nhất. Thêm key 4 khiến map loại key 2; thứ tự còn lại là `3, 1, 4`.

**Giới hạn của ví dụ:** `LinkedHashMap` ở đây **không thread-safe**; chỉ dùng minh họa eviction trong một thread. Ứng dụng đồng thời nên chọn cache implementation/concurrency policy phù hợp (hoặc đồng bộ đầy đủ). `removeEldestEntry` dùng **số entries**, không theo số byte, và không tự có TTL/async cleanup hay eviction callbacks. Không suy rằng mỗi cache nên tự viết một `LinkedHashMap` trong production; có thể dùng thư viện cache chuyên dụng với policy/metrics rõ ràng.

### Tại sao LRU không phải lời giải duy nhất?

- Một entry `byte[200 MiB]` và một entry `byte[2 KiB]` cùng tính là một entry; giới hạn count có thể không đủ.
- Nếu key cardinality khổng lồ, eviction liên tục gây churn/GC pressure ngay cả khi không leak.
- Dữ liệu nghiệp vụ có deadline hết hạn, security/PII retention và invalidation riêng; LRU chỉ điều khiển **độ gần đây của truy cập**, không tự thỏa chính sách retention.
- Cache nằm trong singleton/static và tồn tại suốt process thường **không tự giải phóng** khi một màn hình/session đóng, trừ khi key và eviction/lifecycle được thiết kế tương ứng.

## 6. Weak/soft references có giúp cache tự giải phóng không?

`java.lang.ref.WeakReference` và `SoftReference` có semantics riêng, nhưng chúng **không** tự biến mọi cache thành bounded cache đúng.

- **WeakReference:** khi referent chỉ còn weakly reachable theo quy tắc reference processing, GC có thể clear weak reference; thời điểm GC không xác định. Dùng khi muốn không giữ đối tượng sống chỉ vì reference yếu.
- **SoftReference:** referent có thể được giữ lâu hơn trong một số điều kiện memory, nhưng chính sách clearing phụ thuộc implementation/pressure. Không xem SoftReference là SLA, TTL, capacity bound hoặc giải pháp tổng quát để tránh OOME.
- **PhantomReference:** chủ yếu hỗ trợ cơ chế theo dõi cleanup sau trạng thái reachability thích hợp; `get()` không cho object để dùng như cache value.

### Cạm bẫy của WeakHashMap

`WeakHashMap` giữ **weak keys**, nhưng **values thông thường vẫn là strong references** từ map. Nếu value giữ một reference mạnh quay trở lại chính key (trực tiếp hoặc gián tiếp), key có thể vẫn reachable qua `map → value → key`, vì thế entry **không tự biến mất như dự kiến**.

```text
WeakHashMap
   | strong
   v
 value
   | strong
   v
 key <--- weak edge --- map's weak-key entry

Đường map -> value -> key là strong, nên key vẫn reachable.
```

Đừng dựa vào một test kiểu `System.gc(); assert(map.isEmpty())`: GC không có thời điểm thực thi được bảo đảm, và WeakHashMap có thể expunge stale entries trong các thao tác nội bộ. Nếu mục đích là “cache chỉ dùng đến 64 MiB”, cách rõ ràng hơn là **maximum weight + eviction**.

## 7. Nguồn leak thứ hai: listener/observer không được hủy đăng ký

Trong mô hình Observer/EventBus, một publisher sống dài giữ danh sách callbacks/listeners. Nếu listener là instance method reference hoặc lambda **capture** object của view/controller/request, publisher có thể vô tình giữ toàn bộ object graph ấy.

```text
GC root
    |
    v
Application singleton EventBus
    |
    v
List<Listener>
    |
    v
listener (ví dụ: controller::onEvent)
    |
    v
Controller đã đóng
    |
    +--> ViewModel --> List lớn --> images/buffers
    +--> UserSession
    +--> các closures và objects khác
```

Người dùng đã đóng màn hình, nhưng EventBus chưa remove listener. **Controller vẫn reachable**, nên GC không thể biết controller không còn được sử dụng.

Cần nhớ:

- **Lambda capture là reference retention**: `event -> controller.handle(event)` giữ `controller` nếu lambda object còn sống. Method reference `controller::handle` cũng có thể giữ receiver.
- Nếu listener là một anonymous inner class, nó có thể giữ reference tới enclosing instance tùy trường hợp.
- Nếu event bus lưu listener trong static field hoặc application-scope singleton, owner thường sống lâu hơn UI component hoặc request.
- Có thể leak **không chỉ memory**: listener cũ vẫn nhận event, thực hiện side effects lặp lại, ghi dữ liệu vào view đã đóng.

### Nguyên tắc vòng đời

**Subscription phải đi cùng một phương thức unsubscribe/close rõ ràng.** Khi một component đăng ký listener, nó nên giữ token/subscription handle để hủy đăng ký ở `close()`, `dispose()`, `onStop` hoặc lifecycle hook tương ứng.

Không phải “xóa biến local listener” là đủ: khi publisher đang giữ strong reference, listener vẫn sống. Phải cắt **đường giữ sống từ publisher**.

## 8. Ví dụ Java 17: listener subscription có thể đóng

Tạo file **`ListenerLifecycleDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {

    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new CopyOnWriteArrayList<>();

        Subscription subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return new Subscription(this, listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }

        private void unsubscribe(Consumer<String> listener) {
            listeners.remove(listener);
        }
    }

    static final class Subscription implements AutoCloseable {
        private final EventBus bus;
        private final Consumer<String> listener;
        private boolean closed;

        Subscription(EventBus bus, Consumer<String> listener) {
            this.bus = bus;
            this.listener = listener;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.unsubscribe(listener);
            }
        }
    }

    static final class Screen {
        private final String name;

        Screen(String name) {
            this.name = name;
        }

        void onEvent(String event) {
            System.out.println(name + ":" + event);
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();
        Screen screen = new Screen("screen-A");

        try (Subscription subscription =
                     bus.subscribe(screen::onEvent)) {
            bus.publish("open");
            System.out.println("during=" + bus.listenerCount());
        }

        bus.publish("after-close");
        System.out.println("after=" + bus.listenerCount());
    }
}
```

```bash
javac --release 17 ListenerLifecycleDemo.java
java ListenerLifecycleDemo
```

**Stdout chính xác:**

```text
screen-A:open
during=1
after=0
```

Sau `try-with-resources`, `Subscription.close()` xóa listener khỏi EventBus; `publish("after-close")` không còn gọi Screen. Đây là cách **cắt đường giữ sống từ publisher**.

**Phạm vi giới hạn của mẫu:** nó chỉ minh họa vòng đời cơ bản trong một thread. Trong ứng dụng concurrent thật, `Subscription.close()` cần được thiết kế thread-safe/idempotent, và việc remove callback không nhất thiết hủy một callback đang được thực thi trong snapshot của `CopyOnWriteArrayList`. Vì vậy lifecycle/race semantics phải được định nghĩa rõ. Một `Subscription` do chính component còn giữ cũng có thể chứa listener reference, nhưng khi component và subscription đều không còn reachable qua owner dài hạn, chúng có thể được GC xử lý.

### Một số tình huống listener tương tự

- Listeners của Swing/JavaFX, event emitters hoặc message buses sống dài hơn view.
- Application event handlers đăng ký mỗi lần start nhưng không deregister khi shutdown/reload.
- Reactive streams có `subscribe()` trả về subscription/disposable nhưng chủ sở hữu không hủy.
- Callbacks vào web socket/session mà connection manager giữ lại sau disconnect.
- Watchers/observers/callbacks mang theo closures capture cả context nặng.

Giải pháp không phải luôn dùng `WeakReference` cho listener. Weak listener có thể bị thu gom **quá sớm** nếu phía subscriber không có owner strong rõ ràng; cũng có thể khiến lifecycle không quan sát được. Ưu tiên **explicit subscribe/unsubscribe** khi hợp đồng cho phép.

## 9. Nguồn leak thứ ba: ThreadLocal trong thread pool

`ThreadLocal<T>` cung cấp giá trị **riêng theo từng thread**. Điểm dễ gây nhầm: object `ThreadLocal` không phải nơi chứa một bản value chung cho tất cả threads; mỗi `Thread` có cấu trúc thread-local entries tương ứng.

Trong thread pool, worker thread có thể sống **lâu hơn hàng nghìn request**. Nếu request đặt dữ liệu vào `ThreadLocal` rồi không `remove()`, worker tiếp tục giữ value sau khi request đã kết thúc.

```text
ExecutorService
    |
    v
Worker Thread (vẫn sống)
    |
    v
threadLocals / ThreadLocalMap
    |
    v
Entry.value (strong reference)
    |
    v
RequestContext
    |
    +--> User / token / session metadata
    +--> buffers / parsed request / classloader-related references
```

Hai hệ quả:

1. **Memory retention:** objects thuộc request cũ không thể thu gom nếu vẫn được ThreadLocal entry giữ mạnh.
2. **Context contamination:** task mới được chạy trên **cùng worker** có thể đọc thấy giá trị của request cũ, nếu code không khởi tạo hoặc xóa context đúng cách. Điều này còn nguy hiểm về an toàn dữ liệu giữa requests.

### Các điểm kỹ thuật cần nắm

- `ThreadLocal.set(value)` ghi value cho **thread hiện tại**.
- `ThreadLocal.get()` đọc value gắn với thread hiện tại, có thể trả `null` nếu chưa gán và không có `initialValue` khác.
- `ThreadLocal.remove()` xóa giá trị gắn với **thread hiện tại** cho key ấy.
- `ThreadLocalMap` trên HotSpot thường dùng **weak reference cho key `ThreadLocal`** và **strong reference cho value**. Key bị GC clear không đồng nghĩa value lập tức biến mất: stale entry có thể còn đó cho đến khi map cleanup thực hiện.
- Khi `ThreadLocal` được giữ trong `static final`, key vẫn có thể sống dài; nếu không `remove()`, value vẫn được worker giữ đến lúc bị thay/xóa hoặc worker kết thúc.
- `ThreadLocal` **không phải cơ chế truyền context an toàn giữa các threads**. Các asynchronous continuations có thể chạy trên thread khác hoặc thread cũ được tái sử dụng.

### Quy tắc thực tế

Luôn đặt `remove()` trong `finally` tại **ranh giới sở hữu vòng đời dữ liệu**, nhất là khi dữ liệu thuộc request/transaction/task:

```java
CONTEXT.set(context);
try {
    processRequest();
} finally {
    CONTEXT.remove();
}
```

Đây là **fragment minh họa**; `CONTEXT`, `context`, `processRequest()` thuộc code ứng dụng, không phải file Java độc lập. Nếu cần khôi phục một context đã tồn tại vì nested operation, phải thiết kế policy restore phù hợp thay vì luôn xóa mù quáng. Với nhiều values, xóa tất cả ThreadLocals thuộc phạm vi task và đóng resources trước khi trả worker về pool.

## 10. Ví dụ Java 17 xác định: cùng worker nhưng không rò context

Tạo file **`ThreadLocalCleanupDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> first = pool.submit(() -> {
                REQUEST_ID.set("request-A");
                try {
                    System.out.println("first=" + REQUEST_ID.get());
                } finally {
                    REQUEST_ID.remove();
                }
            });
            first.get();

            Future<?> second = pool.submit(() -> {
                System.out.println("second=" + REQUEST_ID.get());
            });
            second.get();
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

**Stdout chính xác trong đường chạy thành công:**

```text
first=request-A
second=null
```

`newSingleThreadExecutor()` đảm bảo các tasks đã nộp được xử lý tuần tự trên **một worker** (trong đường chạy thông thường, nếu worker không cần thay thế vì failure). `first.get()` hoàn thành trước `second`, và `remove()` xóa giá trị từ worker trong `finally`. Vì vậy request thứ hai không thấy `request-A`.

Nếu bỏ `REQUEST_ID.remove()`, cùng worker có thể in `second=request-A`, minh họa sự rò context. **Không dùng output `null` để chứng minh object đã được GC thu hồi**; demo chỉ chứng minh một reference path đã bị xóa ở ThreadLocal.

### Những điều `remove()` chưa giải quyết

- Một `RequestContext` còn được static cache hoặc listener giữ lại vẫn reachable.
- Một resource trong value như database connection cần được **đóng/return pool** riêng; chỉ `remove()` không tự đóng resource.
- `InheritableThreadLocal` có semantics truyền dữ liệu sang threads con tại thời điểm thích hợp; nó **không** phải cơ chế propagate request state thích hợp cho thread pool được tạo lâu trước request.
- Nếu dùng `CompletableFuture`, scheduler hoặc reactive programming, các callbacks có thể chạy trên những threads khác nhau; thiết kế context propagation tường minh thay vì giả định cùng một thread.

## 11. Vì sao key yếu của ThreadLocalMap vẫn có thể leak value?

Một hiểu lầm là “`ThreadLocalMap` dùng weak key nên giá trị sẽ tự thu hồi nếu key mất”. Thực tế, nếu key `ThreadLocal` không còn strong reference từ ứng dụng, entry có thể có dạng:

```text
Worker Thread (sống dài)
    |
    v
ThreadLocalMap
    |
    v
Entry
    key   = null  (weak key đã được clear)
    value = RequestContext (strong reference)
                |
                v
             graph lớn
```

HotSpot có cơ chế **expunge stale entries** khi truy cập/sửa map thích hợp, nhưng **không được mặc định việc clear weak key sẽ tức khắc xóa value**. Một worker idle lâu hoặc hoạt động theo pattern nhất định có thể giữ stale values lâu hơn mong đợi.

Chỉ tạo `new ThreadLocal<>()` trong mỗi request mà không giữ key và không gọi `remove()` còn làm tình huống khó chẩn đoán hơn. Vì thế:

- Với ThreadLocal thuộc task, giữ reference tới key trong scope đủ để gọi `remove()`.
- Dùng `try/finally` kể cả khi code ném exception.
- Tránh value chứa cả object graph lớn khi chỉ cần một ID nhỏ.
- Chọn ranh giới cleanup ở request/task filter/interceptor, không phân tán nhiều nơi.
- Kiểm tra thread pool/task wrapper của framework có tự dọn context hay chưa; đừng đoán.

**Ghi chú về Java 17:** ví dụ dùng platform threads và `ThreadLocal` truyền thống. Virtual threads đã có những thay đổi nền tảng ở các JDK sau; không lấy giả thiết áp dụng cho một phiên bản mới để giải thích nguyên văn runtime Java 17.

## 12. Static fields, singleton và class loader cũng có thể giữ sống dữ liệu

Một static field có thể là owner hợp lệ của cache/event bus. Trong JVM, việc giữ sống không đơn giản là “mọi static field của mọi class tồn tại vĩnh viễn”, vì lifecycle của class loader và khả năng unloading cũng quan trọng.

Ví dụ tình huống web application/plugin reload:

```text
GC root trong host (thread/pool/singleton)
    |
    v
Listener hoặc ThreadLocal value
    |
    v
Object từ plugin class
    |
    v
Plugin's defining ClassLoader
    |
    v
Class metadata và object graph liên quan
```

Nếu host vẫn giữ một object do plugin class loader định nghĩa, class loader ấy có thể **không đủ điều kiện được thu gom/unload**, dẫn tới tăng heap và class metadata/metaspace qua nhiều lần reload.

Điều này không có nghĩa “ClassLoader nào còn object thì chắc chắn class không bao giờ unload” ở mọi collector/runtime; nó chỉ mô tả **một đường retention điển hình** cần kiểm tra trong heap dump và class unloading metrics.

### Những nguồn giữ class loader ngoài dự đoán

- Worker thread giữ `ThreadLocal` value thuộc web app cũ.
- Thread Context ClassLoader (TCCL) vẫn trỏ đến loader plugin đã unload về nghiệp vụ.
- Static global registry hoặc listener bus của host giữ callbacks từ plugin.
- Scheduler/timer/task queue còn pending tasks capture class/plugin objects.
- JNI global references hoặc caches ngoài JVM giữ handles/lifecycle tương ứng.
- Logging/metrics adapters tạo registrations mà plugin không unregister khi shutdown.

Giải pháp phải bắt đầu từ **owner có vòng đời dài hơn**. Thường cần deregister/unsubscribe, cancel tasks, shutdown thread pools thuộc plugin, reset TCCL, remove ThreadLocals, đóng resources và tránh giữ Class/Method/MethodHandle/plugin instances quá lâu trong global caches.

## 13. Phân biệt memory leak với resource leak và cache hữu ích

Một object chưa được GC thu hồi không tự chứng minh chương trình sai. Ví dụ:

| Tình huống | Có thực sự là leak? | Bằng chứng cần thêm |
| --- | --- | --- |
| Cache chứa 10.000 entries nhưng giới hạn đúng 10.000 và hit rate cao | Chưa thể kết luận | Budget, hit rate, giá trị cache mang lại |
| Cache user/session tăng theo thời gian dù users đã logout | Rất đáng nghi | Key cardinality, eviction/TTL/invalidation |
| Listener list tăng theo số lần mở rồi đóng màn hình | Rất đáng nghi | Registration lifecycle và path tới publisher |
| Thread pool dùng 50 workers, mỗi worker giữ context cũ | Đáng nghi | ThreadLocalMap values, request boundary cleanup |
| Heap used tăng trước GC rồi giảm về baseline sau GC | Có thể bình thường | Post-GC live set và throughput/latency |
| Native direct buffers không được giải phóng đúng lifetime | Có thể là native resource retention | Native memory/JFR/NMT/OS metrics; heap dump có thể chỉ thấy wrapper |
| Objects ở cache đúng TTL nhưng heap committed không giảm | Không đủ kết luận leak | Heap used sau GC, GC uncommit policy, RSS |

**Rò rỉ file descriptor/socket không nhất thiết là rò rỉ heap.** Có khi một Java object giữ native resource và cần `close()` ngay cả khi GC về sau có thể thu hồi wrapper. Dùng `try-with-resources`/explicit lifecycle cho các resource như streams, database connections, response bodies và sockets; không trông chờ finalizer hoặc GC để hoàn tất nghiệp vụ giải phóng.

## 14. Chẩn đoán: dấu hiệu đúng là xu hướng retained heap sau GC

Khi ứng dụng chậm đi hoặc báo `OutOfMemoryError: Java heap space`, đừng lập tức quy nguyên nhân cho cache hay GC. Quy trình nên kết hợp:

1. **Xác định triệu chứng và scope:** heap OOME, `GC overhead limit exceeded`, metaspace OOME, direct/native memory pressure, hay container OOMKilled?
2. **Ghi version và collector:** `java -version`, flags `-Xms`, `-Xmx`, collector và workload khi lỗi xuất hiện.
3. **Theo dõi heap occupancy qua thời gian:** so các điểm tương đương về workload và các số đo sau GC khi có thể.
4. **Nhìn số lượng objects theo class** qua class histogram ở những thời điểm phù hợp.
5. **Lấy heap dump khi đủ quyền và tài nguyên** rồi xem retained size, dominator tree và GC roots.
6. **Truy ngược đến owner:** static cache, event bus, thread, ThreadLocalMap, scheduler hoặc class loader.
7. **Đối chiếu với lifecycle:** object có đáng lẽ biến mất sau logout, response completion, component close hay plugin unload?
8. **Sửa chỗ giữ reference**, thêm giới hạn/cleanup, viết regression test và theo dõi lại trên workload tương đương.

Một snapshot chỉ cho biết tại thời điểm đó objects nào được giữ. **Leak kết luận tốt hơn qua biến thiên và nghiệp vụ**, ví dụ cùng một thử nghiệm “mở/đóng 1.000 màn hình” lặp lại mà số listeners/retained controllers không trở về baseline.

### Heap used chưa chắc là live set

Ở giữa hai lần GC, heap có thể chứa các objects đã không còn reachable nhưng chưa reclaimed. Vì vậy:

- Heap used cao không tự chứng minh có strong references tới toàn bộ những bytes đã allocated.
- Post-GC occupancy có thể hữu ích, nhưng cách collector thu gom và timestamp metrics cần được hiểu đúng.
- Heap committed và process RSS có thể không giảm ngay dù leak đã được sửa, do JVM giữ memory để tái sử dụng hoặc OS/JVM không uncommit ngay.
- NMT/RSS/direct memory numbers thuộc phạm vi khác; không dùng `-Xmx` như giới hạn tổng memory của Java process.

## 15. Dùng jcmd, histogram và heap dump trên Java 17

Một số lệnh hữu ích trên JDK có công cụ `jcmd`:

```bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap-issue.hprof
```

**Lưu ý:** `<PID>` và `/path/to/heap-issue.hprof` là **placeholder**, không phải một PID hoặc đường dẫn được xác minh tồn tại. Các lệnh histogram/heap dump có thể **tốn CPU, memory, disk, tạo pause hoặc ảnh hưởng production**; cần chốt quyền, dung lượng disk, bảo mật dữ liệu và thời điểm chạy.

- **`GC.heap_info`:** xem thông tin heap/GC tùy JVM.
- **`GC.class_histogram`:** thống kê số lượng và shallow bytes theo class tại thời điểm quan sát. Không cho biết ai giữ object hoặc retained size.
- **`GC.heap_dump`:** xuất snapshot heap để phân tích object graph. Heap dump có thể chứa secrets, tokens, PII và dữ liệu người dùng; áp dụng quyền đọc, lưu trữ, mã hóa và thời hạn xóa phù hợp.
- Các flags/biến thể hỗ trợ như `-all` có thể thay đổi việc có yêu cầu full GC trước dump hay không. **Đọc `jcmd <PID> help GC.heap_dump`** trên đúng JVM thay vì phỏng đoán hiệu ứng pause hoặc đối tượng được đưa vào dump.

Heap dump không phải “bộ giải đáp tự động”. Bạn cần truy **reference chains** để biết vì sao các objects còn sống.

### Dùng Eclipse MAT / heap analyzer

Một quy trình tương đối hiệu quả:

1. Mở `.hprof` trong công cụ phân tích như Eclipse Memory Analyzer (MAT).
2. Xem histogram, tìm classes bất thường: `byte[]`, `char[]`, DTOs, `ArrayList`, `HashMap$Node`, listener classes, request contexts.
3. Xem **Dominator Tree** để tìm object owners có **retained size lớn**.
4. Với một nhóm instances nghi ngờ, dùng **Path To GC Roots** và loại trừ những weak/soft/phantom edges nếu muốn tìm đường strong retention cụ thể.
5. Đọc **incoming/outgoing references** từ owner về các values; tìm field cụ thể như `CACHE`, `listeners`, `threadLocals`.
6. Đối chiếu lifecycle: owner nên còn sống hay phải được giải phóng? Nếu đáng lẽ đã đóng, kiểm tra `close/remove/invalidate` đã chạy trên tất cả đường lỗi chưa.
7. Lặp lại sau fix cùng kịch bản tải; số cache entries/listeners/context values có về mức ổn định không?

**Một đường tới GC root có nhiều nhánh.** Việc tìm được `static CACHE -> object` không chứng minh đó là **đường duy nhất**. Xóa cache rồi vẫn thấy object sống có thể do ThreadLocal, listener hoặc pending task còn giữ.

## 16. Đọc ThreadLocal leak trong heap dump

Một đường retention điển hình trong MAT có dạng ý niệm:

```text
Thread "http-worker-17"
  └── threadLocals
      └── ThreadLocalMap
          └── table[]
              └── Entry
                  ├── referent: ThreadLocal key hoặc null nếu cleared
                  └── value: RequestContext
                              └── byte[] / user/session graph
```

Tùy JDK/build/dump, tên field nội bộ có thể khác. Đây là sơ đồ minh họa chứ không phải hợp đồng API về cấu trúc `ThreadLocalMap`.

Điều tra các câu hỏi:

- Thread có phải worker lâu dài trong pool không? Pool sở hữu bởi ai?
- `ThreadLocal` key còn tồn tại hay đã được GC clear thành stale entry?
- Value chứa những reference gì, retained size bao nhiêu?
- Có dùng `remove()` trong `finally` cho mọi đường thoát, bao gồm exception/timeouts/cancellation không?
- Code có vô tình tạo `ThreadLocal` trong mỗi request thay vì tái dùng một key có lifecycle rõ ràng?
- Task có chạy xen kẽ giữa nhiều tenants/users, và leak value có thể gây lỗi bảo mật?

Nếu chỉ có một instance value lớn, đó có thể là request đang chạy hợp lệ. Nếu mỗi worker giữ contexts của requests đã hoàn thành lâu, hoặc nhiều stale entries tích tụ sau workload tương đương, nghi ngờ cao hơn.

## 17. Đọc cache/listener leak trong heap dump

### Cache

```text
Application.class
  └── static CACHE
      └── ConcurrentHashMap
          └── table[]
              └── Node
                  ├── key: request-382773
                  └── val: ResponseSnapshot
                              └── byte[] / nested DTOs
```

Dấu hiệu đáng nghi: key cardinality liên tục tăng, keys không được tái sử dụng, values không có TTL hoặc bộ nhớ vẫn giữ sau khi client/session kết thúc. Lưu ý class histogram của `byte[]` không nói keys thuộc map nào; cần đi từ **incoming references** về owner.

### Listener

```text
GlobalEventBus
  └── listeners
      └── ArrayList/CopyOnWriteArrayList
          └── Consumer/lambda/method reference
              └── ScreenController
                  └── viewModel / resource graph
```

Nếu Controller đã bị nghiệp vụ đóng nhưng vẫn có path từ singleton event bus, đó là dấu hiệu mạnh của leak. Fix là **remove listener đúng instance/reference**, không chỉ `screen = null` ở một biến local không liên quan.

### Một leak có thể có nhiều “bẫy chủ sở hữu”

Nếu Controller tự đăng ký listener, rồi listener capture Controller, thì việc Controller giữ `Subscription` là một chu trình. Chu trình ấy **tự nó không gây leak** nếu toàn bộ graph không có roots. Vấn đề là global bus tiếp tục giữ một đầu của chu trình; vì vậy cần **hủy đăng ký với bus**.

## 18. Tránh sửa leak bằng giải pháp che giấu triệu chứng

Những cách đối phó không giải quyết nguyên nhân:

- **Tăng `-Xmx`:** có thể trì hoãn OOME nhưng cache/listeners/ThreadLocals vẫn giữ objects theo quy luật cũ.
- **Gọi `System.gc()` liên tục:** không thể thu hồi objects còn strongly reachable; còn có thể giảm throughput và tăng pauses.
- **Chỉ xóa biến local:** nếu object còn được static cache hoặc listener list giữ, reference ở owner vẫn tồn tại.
- **Đổi mọi reference thành WeakReference:** có thể làm mất dữ liệu khi GC, không giải quyết memory budget hay logic cleanup.
- **Đóng worker thread pool vô tội vạ:** có thể cắt ThreadLocal values nhưng làm hỏng service, còn không sửa owner gốc của task lifecycle.
- **Chỉ sửa heap dump analyzer:** root cause nằm ở ownership/lifecycle code, không ở công cụ quan sát.
- **Tin vào finalizer:** finalization không có bảo đảm thời điểm và là cơ chế lỗi thời; dùng explicit `close()`, `Cleaner` khi thật phù hợp cho backup native cleanup, và `try-with-resources`.

**Fix tốt nhất** thường là một trong ba loại: đặt **budget/eviction cho cache**, **unsubscribe listener đúng lifecycle**, hoặc **remove/restore ThreadLocal đúng task boundary**. Có thể cần kết hợp nếu object đang bị giữ qua nhiều roots.

## 19. Checklist thiết kế để không tái xuất hiện leak

| Thành phần | Câu hỏi review | Biện pháp |
| --- | --- | --- |
| Cache | Số entries/estimated weight có giới hạn không? | Maximum size/weight, eviction, expiration, invalidation |
| Cache key | Key có giữ request/session/object graph không? | Key nhỏ, immutable, stable, có lifecycle |
| Cache value | Value có giữ cả graph lớn hay native resource không? | Giảm retained graph, close khi evict nếu cần |
| Listener | Ai giữ subscription và hủy vào lúc nào? | `AutoCloseable`/dispose/unsubscribe |
| Listener | Lambda/method reference capture object nào? | Tránh capture context quá rộng; cleanup đúng |
| ThreadLocal | Value thuộc thread hay thuộc request/task? | `try/finally remove()` tại task boundary |
| ThreadLocal | Thread pool có reuse workers giữa users? | Context isolation và cleanup |
| ThreadLocal | Có stale entry do key bị clear không? | Giữ key lifecycle rõ, gọi remove, kiểm tra heap dump |
| ClassLoader | Plugin có được shutdown đầy đủ khi unload không? | Cancel tasks, close registries, unregister, reset TCCL |
| Resources | Có file/socket/direct memory cần release không? | Explicit close và owner lifecycle |
| Diagnostics | Có baseline và metrics trước/sau workload? | Heap occupancy, counts, heap dumps, JFR khi phù hợp |
| Testing | Có lặp thao tác tạo/hủy rồi đo retention? | Lifecycle regression và boundedness tests |

Một policy tốt còn ghi **ai sở hữu dữ liệu** và **khi nào kết thúc thời gian giữ**: request, session, window, tenant, plugin hay cả application. Cùng một object có thể được cache hợp lệ trong vòng đời session nhưng thành leak nếu giữ sau logout.

## 20. Bài tự kiểm tra

**Câu 1:** Một `HashMap` chứa object A và B trỏ qua lại thành chu trình. Sau khi bỏ tất cả external roots tới map, A và B có bị “kẹt” vì cycle không?

**Không.** Tracing GC có thể thu gom cả graph không reachable từ GC roots. Chu trình không tự tạo leak.

**Câu 2:** `static final Map` có phải luôn gây leak?

**Không.** Static map có thể là cache/registry đúng thiết kế. Leak xuất hiện khi retention vượt vòng đời/budget thực tế; modifier `final` chỉ ngăn gán lại field reference, không ngăn contents của map thay đổi.

**Câu 3:** `ConcurrentHashMap` có tự eviction không?

**Không.** Nó cung cấp concurrent map semantics; phải có policy size/time/invalidation riêng.

**Câu 4:** Một view đã đóng nhưng `GlobalEventBus.listeners` còn chứa `view::onEvent`. Vì sao view chưa collectible?

Vì bus giữ method-reference callback, callback giữ receiver view; có **strong path từ root** tới view.

**Câu 5:** `ThreadLocalMap` có weak keys, vậy value chắc chắn biến mất ngay khi key bị clear?

**Không.** Value có thể là strong reference trong stale entry tới khi cleanup, nên cần `remove()` đúng vòng đời.

**Câu 6:** Một worker dùng `REQUEST_ID.set(...)` cho request A rồi xử lý request B. Nếu thiếu cleanup có thể xảy ra gì?

Memory retention qua context A, và nguy cơ B đọc **stale data** của A nếu code dùng `get()` khi không set lại.

**Câu 7:** `WeakHashMap` với value có strong reference quay lại key có chắc entry sẽ biến mất khi không còn external key variable không?

**Không.** Đường `map → value → key` có thể vẫn giữ key strongly reachable.

**Câu 8:** Heap used tăng ngay trước GC nhưng về gần baseline sau GC. Đây có chắc là leak không?

**Không.** Có thể là allocation churn bình thường. Cần quan sát retained live set và object lifecycle.

**Câu 9:** Heap dump histogram cho thấy rất nhiều `byte[]`. Có thể kết luận lỗi nằm ở nơi cấp phát byte arrays?

**Không.** Phải truy retained owner/path to GC roots. Một cache entry hoặc ThreadLocal value có thể đang giữ các arrays.

**Câu 10:** Xóa entry cache liệu có buộc RSS giảm ngay tương ứng với retained size?

**Không.** Có thể còn roots khác; GC chưa thu hồi ngay; JVM có thể giữ committed heap, còn OS RSS theo trang/bộ nhớ native.

## 21. Quy trình thực hành điều tra và xác nhận fix

Một kịch bản kiểm thử có thể lập lại:

1. **Đo baseline** sau warm-up hợp lý, lưu memory pools, số listeners, cache entry counts, thread count và heap usage.
2. **Tạo chuỗi thao tác** có lifecycle rõ: 1.000 request/100 lần mở-đóng view/10 lần plugin start-stop, với đầu vào tương đương.
3. **Chờ hệ thống quiescent** nếu hợp lý, đo lại counts và các metrics sau GC ở những thời điểm được instrument/ghi nhận, không ép một con số chính xác.
4. **Nếu object counts tăng liên tục**, thu heap dump và tìm top owners bằng dominator tree.
5. **Tìm path to GC roots**: static cache, event bus, threadLocalMap hay một owner khác.
6. **Xác định object hết vòng đời ở điểm nào**: response complete, screen close, tenant delete, task finally, plugin shutdown.
7. **Sửa code tại owner** bằng eviction/invalidate, unsubscribe/dispose hoặc remove ThreadLocal.
8. **Bổ sung test**: sau lifecycle close, listenerCount bằng 0; cache size không vượt max; task tiếp theo không thấy request context cũ.
9. **Kiểm tra lại dưới concurrent workload**: cleanup trong `finally` kể cả khi lỗi, cancellation hoặc timeout; tránh race giữa subscribe và unsubscribe.
10. **Theo dõi production**: số lượng listeners/cache entries, hit rate, ThreadLocal context hygiene, heap live set, OOME/GC pressure. Fix phải duy trì ổn định theo thời gian.

**Không cần đợi `OutOfMemoryError` mới kiểm tra:** leak mức thấp thường biểu hiện trước qua cache size tăng đều, listeners tích lũy và long-lived thread contexts.

## Tài liệu chuẩn để tra cứu

- [JVMS Java SE 17 §2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): objects, arrays và quản lý heap.
- [Java SE 17 `java.lang.ref` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): các cấp reachability và reference objects.
- [Java SE 17 `Reference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html), [`WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [`SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): reachability, clearing, `reachabilityFence` và vòng đời reference.
- [Java SE 17 `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, lưu ý về value trỏ ngược key.
- [Java SE 17 `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove` và per-thread values.
- [Java SE 17 `LinkedHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): access order và `removeEldestEntry` cho bounded LRU demo.
- [Java SE 17 `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): quản lý vòng đời unsubscribe/cleanup với try-with-resources.
- [Java SE 17 `ManagementFactory`, `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage và metrics.
- [Java SE 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `GC.class_histogram`, `GC.heap_dump` và điều kiện chẩn đoán.
- [Java SE 17 `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): thống kê GC/memory utilization.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/): heap dump, retained size, dominator tree, path to GC roots.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): cơ sở quan sát runtime qua JFR, khi cần bổ sung evidence theo thời gian.

**Ghi nhớ:** GC thu hồi những objects **không còn reachable**, chứ không tự đoán dữ liệu nào đã hết giá trị nghiệp vụ. **Cache cần budget/eviction**, **listener cần unsubscribe đúng vòng đời**, **ThreadLocal cần `remove()` hoặc restore trong `finally`**. Khi thấy heap tăng, hãy truy **đường tham chiếu mạnh từ GC roots tới retained graph**, sửa **owner giữ sống**, rồi xác minh bằng một workload lặp lại và metrics trước–sau.
