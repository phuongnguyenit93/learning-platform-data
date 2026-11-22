# Rò rỉ bộ nhớ Java do `static`, bộ nhớ đệm và đăng ký không được gỡ

## 1. Vấn đề: vì sao Java có GC mà vẫn rò rỉ bộ nhớ?

Java quản lý bộ nhớ cho các objects dựa trên **reachability**. Garbage collector (GC) có thể thu hồi những objects không còn đường tham chiếu thích hợp từ GC roots. Tuy nhiên, nếu chương trình **vẫn giữ strong references** đến objects đã hết giá trị sử dụng về mặt nghiệp vụ, GC không thể biết chúng “không cần nữa” và sẽ tiếp tục giữ bộ nhớ của chúng.

Ví dụ:

```java
static final java.util.List<byte[]> DATA =
        new java.util.ArrayList<>();
```

Nếu ứng dụng thêm arrays vào DATA mãi mà không loại bỏ phần tử, mỗi array có thể tiếp tục reachable qua một đường tham chiếu từ class/runtime đến static list rồi đến phần tử. Mặc dù không còn code nào cần dữ liệu cũ, GC không được thu gom arrays đang được giữ sống.

Tương tự:

- **Static collection** giữ references đến sessions, objects hoặc callback closures.
- **Cache** thiếu giới hạn kích thước, hết hạn, eviction hoặc invalidation.
- **Listener/observer registration** được thêm vào event source sống lâu nhưng không `remove/unsubscribe`.
- **ThreadLocal** trên thread pool giữ request context qua nhiều công việc.
- **Scheduled task / callback / lambda** giữ object graph lớn thông qua captured reference.

Đây là dạng *logical memory leak* hoặc *unintended object retention*. Nó khác với rò rỉ native resources như không đóng file descriptor/socket, dù hai vấn đề có thể cùng xảy ra.

> **Nguyên tắc cốt lõi:** “Không còn được dùng” **không đồng nghĩa** “không còn reachable”. Phải **cắt đúng đường tham chiếu mạnh** theo lifecycle/ownership, không chờ `System.gc()` giải quyết thiết kế sai.

Trong bài này, mọi ví dụ độc lập dùng Java 17+, và stdout được lựa chọn sao cho có thể kiểm tra **không phụ thuộc thời điểm GC**.

## 2. Mô hình đối tượng, tham chiếu và GC roots

Giả sử một chương trình có đồ thị:

```text
GC roots
   │
   └── class/runtime
          │
          └── static SessionRegistry.SESSIONS
                 │
                 └── ArrayList
                        │
                        ├── Session A ──> byte[] payload
                        └── Session B ──> image/metadata...
```

Nếu static list vẫn reachable, các phần tử và object graph từ phần tử có thể vẫn reachable. GC không “xóa object vì quá cũ” trừ khi chính ứng dụng hoặc một cơ chế collection/cache thích hợp cắt reference path.

Một **GC root** là khái niệm runtime: các live references từ frames/threads, class/static state đang sống, JNI/runtime handles và những nguồn đặc thù VM. Static reference thường là một retention path quan trọng, nhưng **không phải mọi class/static field đều vĩnh viễn sống đến khi process kết thúc**; class loading/unloading và class-loader lifetime cũng có vai trò.

### Cần tách ba khái niệm

| Khái niệm | Câu hỏi |
| --- | --- |
| Object reachable | Vẫn có đường tham chiếu từ roots thích hợp? |
| Object useful | Ứng dụng còn cần dữ liệu này về nghiệp vụ? |
| Object collected | GC đã thực sự thu hồi bộ nhớ? |

Có thể reachable nhưng không useful: đó chính là tín hiệu của retention leak. Cũng có thể không còn reachable nhưng chưa collected vì GC chưa chạy. Vì vậy mọi thử nghiệm trong bài kiểm **số phần tử/đường tham chiếu**, không khẳng định GC đã thu gom đúng một thời điểm.

## 3. Lỗi số 1: static List tăng không giới hạn

Tạo **`UnboundedStaticRegistryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class SessionRegistry {
    static final List<StringBuilder> ACTIVE =
            new ArrayList<>();

    static void add(StringBuilder session) {
        ACTIVE.add(session);
    }
}

public class UnboundedStaticRegistryDemo {
    public static void main(String[] args) {
        for (int i = 1; i <= 3; i++) {
            StringBuilder data =
                    new StringBuilder("session-" + i);
            SessionRegistry.add(data);
        }

        System.out.println(SessionRegistry.ACTIVE.size());
        System.out.println(SessionRegistry.ACTIVE.get(0));
    }
}
```

```bash
javac UnboundedStaticRegistryDemo.java
java UnboundedStaticRegistryDemo
```

```text
3
session-1
```

Code không “rò” vì tạo StringBuilder, mà vì **mỗi reference được thêm vào ACTIVE và không có chính sách loại bỏ**. Sau khi vòng lặp kết thúc, biến data cục bộ không còn được dùng, nhưng SessionRegistry.ACTIVE vẫn giữ các references.

Khi số request tăng hàng triệu, static list tương tự có thể làm live heap tăng theo thời gian. Với payload chứa nhiều objects khác, **retained size** có thể lớn hơn rất nhiều kích thước của chính list.

**Phân biệt:** Static list *có chủ đích* giữ các sessions đang active không sai. Sai xảy ra khi sessions đã đóng/hết hạn nhưng vẫn bị giữ lại.

## 4. Đừng nhầm `static final` với đối tượng bất biến

Ở ví dụ:

```java
static final List<String> ITEMS = new ArrayList<>();
```

`final` chỉ ngăn **gán lại field reference** bằng một list khác. Nó không ngăn:

```java
ITEMS.add("A");
ITEMS.add("B");
ITEMS.clear();
```

Các methods thay đổi **nội dung của chính list**. Do đó `static final Map` hoặc `static final List` vẫn có thể tạo memory retention nếu phát triển không giới hạn.

### Cẩn thận với constant-like declarations

`static final int LIMIT = 100` là một giá trị primitive, không kéo dài vòng đời hàng triệu objects. `static final Map<Key,Value> CACHE` lại có thể nắm giữ một object graph lớn. Không nên gộp mọi static field thành một nhóm “luôn leak”; **loại object, tốc độ thêm dữ liệu và lifecycle** mới quyết định.

## 5. Sửa registry: có thao tác remove theo ownership

Tạo **`RegistryLifecycleDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class SessionRegistry {
    private static final Map<String, Session> SESSIONS =
            new HashMap<>();

    static void open(Session session) {
        SESSIONS.put(session.id(), session);
    }

    static void close(String id) {
        SESSIONS.remove(id);
    }

    static int activeCount() {
        return SESSIONS.size();
    }

    private SessionRegistry() {
    }
}

record Session(String id, String user) {
}

public class RegistryLifecycleDemo {
    public static void main(String[] args) {
        SessionRegistry.open(new Session("1", "An"));
        SessionRegistry.open(new Session("2", "Binh"));

        System.out.println(SessionRegistry.activeCount());
        SessionRegistry.close("1");
        System.out.println(SessionRegistry.activeCount());
    }
}
```

```bash
javac RegistryLifecycleDemo.java
java RegistryLifecycleDemo
```

```text
2
1
```

`remove(id)` cắt reference edge từ map entry đến session object. Nếu không có các strong paths khác, session có thể trở nên unreachable.

### Phần quan trọng không nằm ở tên method

- Ai **gọi close** khi user logout, timeout, request kết thúc?
- Có code path exception nào quên close không?
- Nếu `open` bị gọi trùng id, entry cũ bị thay thế có cần cleanup bên ngoài không?
- Registry có hỗ trợ concurrent access không?
- App shutdown có giải phóng registrations/resources được sở hữu không?

Ví dụ dùng `HashMap` vì chạy đơn luồng. Trong production, khi nhiều threads truy cập, cần đồng bộ thích hợp hoặc data structure concurrent; việc chuyển sang `ConcurrentHashMap` **không tự sửa memory leak**.

## 6. “Clear mọi thứ” không phải luôn là giải pháp

Gọi `CACHE.clear()` bừa bãi có thể phá chức năng nếu các entries vẫn cần thiết. Một retention policy đúng cần xác định:

1. **Owner**: ai tạo và ai chịu trách nhiệm loại bỏ?
2. **Lifetime**: entry có hiệu lực cho session, request, transaction hay cả ứng dụng?
3. **Maximum size**: cache có giới hạn phần tử hoặc tổng memory weight?
4. **Expiry**: hết hạn theo thời gian, idle time hay event nghiệp vụ?
5. **Invalidation**: khi dữ liệu gốc thay đổi, entry nào phải được xóa?
6. **Concurrency**: việc thêm/xóa/đọc có thread-safe không?
7. **Failure paths**: exception, cancellation, timeout có cleanup không?
8. **Monitoring**: live entries, hit rate, eviction count có được quan sát không?

**Static scope thường sống lâu** hơn request scope. Không lưu dữ liệu request vào static structures nếu không có lý do và chính sách lifecycle rõ ràng.

## 7. Cache khác registry nhưng đều giữ strong references

Một **registry** thường ghi nhận những đối tượng hiện đăng ký/đang hoạt động. Một **cache** giữ bản sao kết quả để tránh tính toán hoặc truy xuất lặp. Chúng có semantics loại bỏ khác nhau:

| Cấu trúc | Khi nào phần tử được giữ? | Khi nào phải loại bỏ? |
| --- | --- | --- |
| Active session registry | Session còn active | Logout, timeout, shutdown |
| Listener registry | Listener còn subscription hợp lệ | Unsubscribe, component close |
| Memoization cache | Kết quả còn hữu ích | Eviction, expiry, invalidation |
| Request context | Request còn xử lý | `finally` sau request |
| ThreadLocal context | Context thuộc task hiện tại | `remove()` ở cuối task |
| Pending task queue | Công việc chưa chạy/hủy | Completion, cancellation, rejection |
| Static singleton | Service theo app lifecycle | App/classloader shutdown |

Một cache có thể **cố ý giữ** objects; vấn đề không phải “giữ reference” mà là giữ **không kiểm soát sau khi lợi ích đã hết**.

## 8. Lỗi số 2: memoization cache tăng vô hạn

Tạo **`UnboundedCacheDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class NameCache {
    private static final Map<Integer, String> CACHE =
            new HashMap<>();

    static String valueFor(int id) {
        return CACHE.computeIfAbsent(
                id, key -> "user-" + key);
    }

    static int size() {
        return CACHE.size();
    }
}

public class UnboundedCacheDemo {
    public static void main(String[] args) {
        for (int id = 1; id <= 4; id++) {
            NameCache.valueFor(id);
        }

        System.out.println(NameCache.size());
        System.out.println(NameCache.valueFor(2));
        System.out.println(NameCache.size());
    }
}
```

```bash
javac UnboundedCacheDemo.java
java UnboundedCacheDemo
```

```text
4
user-2
4
```

`computeIfAbsent` tránh tính toán lại cho key đang tồn tại. Nhưng nếu **số key duy nhất tăng không giới hạn**, CACHE có thể giữ mọi key/value trong suốt đời app hoặc classloader.

Đặc biệt nguy hiểm khi key là request ID/UUID/timestamp, khiến hit rate gần bằng 0 mà cache vẫn lớn dần.

### Đừng lầm hit rate với correctness

Một cache có hit rate cao vẫn có thể giữ hàng triệu entries cũ. Một cache hit rate thấp có thể tốn memory và CPU mà không mang lợi ích. Cần **giới hạn kích thước**, chính sách eviction/expiry và đánh giá payload size.

## 9. Giới hạn cache bằng LRU: mẫu đơn giản Java 17

`LinkedHashMap` có thể cấu hình **access-order** và override `removeEldestEntry` để giữ một số entries tối đa. Đây là ví dụ đơn luồng, không phải production-grade concurrent cache.

Tạo **`BoundedLruCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

class LruCache<K, V> extends LinkedHashMap<K, V> {
    private final int maximum;

    LruCache(int maximum) {
        super(16, 0.75f, true);
        if (maximum < 1) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.maximum = maximum;
    }

    @Override
    protected boolean removeEldestEntry(
            Map.Entry<K, V> eldest) {
        return size() > maximum;
    }
}

public class BoundedLruCacheDemo {
    public static void main(String[] args) {
        LruCache<String, String> cache =
                new LruCache<>(2);

        cache.put("A", "alpha");
        cache.put("B", "beta");
        cache.get("A");
        cache.put("C", "gamma");

        System.out.println(cache.size());
        System.out.println(cache.containsKey("A"));
        System.out.println(cache.containsKey("B"));
        System.out.println(cache.get("C"));
    }
}
```

```bash
javac BoundedLruCacheDemo.java
java BoundedLruCacheDemo
```

```text
2
true
false
gamma
```

Khi `get("A")`, A thành most recently used. Thêm C vượt giới hạn 2 entries nên B là eldest và bị evict. Bộ nhớ của B's key/value không được **đảm bảo** thu hồi ngay, nhưng cache không còn giữ entry B nữa.

### Giới hạn của ví dụ

- `LinkedHashMap` không thread-safe.
- Số entries tối đa **không** đồng nghĩa giới hạn số bytes: một value có thể rất lớn.
- Eviction không đóng `AutoCloseable` resources trong value trừ khi code thiết kế cleanup riêng.
- Cache production cần xem xét TTL, concurrency, weights, metrics, cache stampede và errors.
- `removeEldestEntry` không nhất thiết chạy khi app ngừng thêm entries; TTL vẫn cần cơ chế riêng.

## 10. TTL: hết hạn theo thời gian mà không dựa GC

Một cache có thể cho entry sống tối đa một khoảng thời gian tính theo clock. Chọn **clock injection** để tests deterministic, không `Thread.sleep`.

Tạo **`TtlCacheDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.function.LongSupplier;

class TtlCache<K, V> {
    private record Entry<V>(V value, long expiresAt) {
    }

    private final Map<K, Entry<V>> entries = new HashMap<>();
    private final LongSupplier clock;
    private final long ttlMillis;

    TtlCache(LongSupplier clock, long ttlMillis) {
        if (ttlMillis <= 0) {
            throw new IllegalArgumentException("ttl must be positive");
        }
        this.clock = clock;
        this.ttlMillis = ttlMillis;
    }

    void put(K key, V value) {
        entries.put(key,
                new Entry<>(value, clock.getAsLong() + ttlMillis));
    }

    V get(K key) {
        Entry<V> entry = entries.get(key);
        if (entry == null) {
            return null;
        }
        if (clock.getAsLong() >= entry.expiresAt()) {
            entries.remove(key);
            return null;
        }
        return entry.value();
    }

    int size() {
        return entries.size();
    }
}

public class TtlCacheDemo {
    public static void main(String[] args) {
        final long[] clock = {1000L};
        TtlCache<String, String> cache =
                new TtlCache<>(() -> clock[0], 100L);

        cache.put("key", "cached");
        System.out.println(cache.get("key"));

        clock[0] = 1100L;
        System.out.println(cache.get("key") == null);
        System.out.println(cache.size());
    }
}
```

```bash
javac TtlCacheDemo.java
java TtlCacheDemo
```

```text
cached
true
0
```

Entry có hạn 1100 (1000 + TTL 100). Ở thời điểm 1100, get loại entry rồi trả null. Đây là **lazy expiration**: entry hết hạn nhưng không được đọc lại có thể **vẫn nằm trong map**.

Trong hệ thống thực tế, muốn đảm bảo memory bound cần thêm **max size và proactive expiry/periodic cleanup phù hợp**, hoặc dùng cache library đã có chính sách rõ.

**Lưu ý về time source:** Với duration trong ứng dụng, `System.nanoTime()` phù hợp đo elapsed time; `currentTimeMillis()` chịu điều chỉnh clock wall. Ví dụ dùng clock giả lập cho mục đích test, không đề xuất tự triển khai TTL production chỉ bằng arithmetic này.

## 11. Cache invalidation khi dữ liệu nguồn thay đổi

Một cache có bounded size nhưng dữ liệu stale vẫn có thể gây lỗi logic. Khi database thay đổi, entry tương ứng cần được cập nhật hoặc invalidated.

Ví dụ mô hình:

```java
void onUserUpdated(long userId) {
    userCache.remove(userId);
}
```

Đây là **mảnh method minh họa**, không có `userCache` được khai báo độc lập ở đây.

Cache chính sách phải trả lời:

- Ai biết user changed event?
- Cắt entry theo một key hay nhiều secondary keys?
- Cache value có chứa references tới mutable objects bị chia sẻ không?
- Một request khác có thể tái thêm giá trị cũ trong lúc invalidation không?
- Nếu refresh thất bại, có giữ stale result, retry hay propagate exception?

**Cache correctness và memory safety là hai nhiệm vụ riêng**. Eviction sửa retention, còn invalidation sửa freshness; thường cần cả hai.

## 12. Cache keys và values đều có thể giữ object graph

`Map<K,V>` thường giữ strong references tới cả key và value. Key nhỏ không có nghĩa value nhỏ; một value có thể giữ:

```text
CACHE
 └── entry
      ├── key: UserId
      └── value: Report
                 ├── List<Detail>
                 ├── byte[] attachment
                 └── SessionContext
```

Nếu Report vô tình tham chiếu SessionContext, cache có thể kéo dài vòng đời cả request graph dù chỉ muốn giữ report summary.

**Review retained size:** Hãy kiểm các fields của cached objects và các nested references. Đôi khi giải pháp tốt là lưu **DTO nhỏ/immutable snapshot**, không lưu toàn bộ entity/session/request object.

Một cache max 100 entries mà mỗi value là 100 MB vẫn có thể gây áp lực memory nghiêm trọng. Hạn chế **bytes/weight** quan trọng hơn số entries trong các trường hợp payload rất khác nhau.

## 13. Không dùng `WeakReference` như lời giải phổ quát

`WeakReference<T>` không giữ referent sống nếu nó chỉ còn weakly reachable. Nhưng:

- Kết quả `get()` có thể trở thành null ở thời điểm do GC quyết định.
- Cache weak values có thể mất entries bất ngờ dưới memory pressure.
- Metadata/keys/structures của chính cache vẫn có thể tích lũy nếu quản lý kém.
- Weak references **không** tự xác định TTL, size, eviction hay ownership.
- Không được viết logic nghiệp vụ đòi referent phải sống tới một deadline dựa trên weak reference.

Tạo **`WeakReferenceDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println(weak.get() != null);
        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("strong variable cleared");
    }
}
```

```bash
javac WeakReferenceDemo.java
java WeakReferenceDemo
```

```text
true
strong variable cleared
```

Ví dụ cố ý **không** assert `weak.get() == null` sau System.gc: việc GC clear weak reference là không deterministic.

`Reference.reachabilityFence(strong)` giữ referent strongly reachable đến fence, giúp ví dụ kiểm `weak.get() != null` có cơ sở. Sau dòng clear, ta chỉ xác nhận assignment, không khẳng định referent đã collected.

## 14. `WeakHashMap` có weak keys nhưng value vẫn quan trọng

`WeakHashMap<K,V>` có weak references đối với keys; entry có thể được loại sau khi key không còn strongly reachable từ nơi khác. Tuy nhiên, **value thường được giữ mạnh** trong entry khi entry còn đó.

Đặc biệt nguy hiểm là trường hợp value **tham chiếu ngược về key**:

```text
live WeakHashMap
   │
   └── entry (weak key, strong value)
                         │
                         └── value.owner ──> key
```

Khi value có strong path quay về key, key có thể vẫn strongly reachable từ map qua value, khiến weak-key policy không giúp entry biến mất như người viết dự kiến.

### Ví dụ cấu trúc (không giả định GC)

Tạo **`WeakMapBackReferenceDemo.java`**:

```java
import java.util.WeakHashMap;

record Holder(Object owner) {
}

public class WeakMapBackReferenceDemo {
    public static void main(String[] args) {
        WeakHashMap<Object, Holder> map =
                new WeakHashMap<>();

        Object key = new Object();
        map.put(key, new Holder(key));

        System.out.println(map.size());
        System.out.println(map.get(key).owner() == key);
    }
}
```

```bash
javac WeakMapBackReferenceDemo.java
java WeakMapBackReferenceDemo
```

```text
1
true
```

Đây là một sơ đồ retention qua value. Không cố chứng minh bằng chờ GC; hãy quan sát object graph và semantics của map. **Weak keys không bảo vệ** khi có đường strong reference khác giữ key.

## 15. Lỗi số 3: đăng ký listener nhưng không hủy

Một event source thường giữ danh sách listeners bằng **strong references**. Khi component đăng ký listener, event source có thể giữ component hoặc captured objects **lâu hơn lifecycle mong muốn**.

Hình dung:

```text
static EventHub
    └── LISTENERS
         └── listener object/lambda
              └── captured ScreenController
                   ├── big view model
                   └── resources / UI state
```

Đóng màn hình hoặc bỏ local variable controller **không đủ** nếu EventHub vẫn giữ listener.

### Ví dụ lỗi và cách phát hiện

Tạo **`LeakingListenerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EventHub {
    private static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static void subscribe(Runnable listener) {
        LISTENERS.add(listener);
    }

    static int listenerCount() {
        return LISTENERS.size();
    }

    static void publish() {
        for (Runnable listener : LISTENERS) {
            listener.run();
        }
    }
}

final class Screen {
    private final String name;

    Screen(String name) {
        this.name = name;
        EventHub.subscribe(() ->
                System.out.println("event:" + name));
    }
}

public class LeakingListenerDemo {
    public static void main(String[] args) {
        new Screen("A");
        new Screen("B");

        System.out.println(EventHub.listenerCount());
        EventHub.publish();
    }
}
```

```bash
javac LeakingListenerDemo.java
java LeakingListenerDemo
```

```text
2
event:A
event:B
```

`Screen` objects không được lưu trực tiếp sau `new Screen(...)`, nhưng listeners giữ captured `name`. Ở ví dụ này listener capture String, **không nhất thiết giữ toàn bộ Screen object**. Nếu lambda truy cập `this` hoặc instance methods/fields của Screen, nó có thể giữ cả Screen.

Để tránh khẳng định quá mức, hãy hiểu ví dụ này là retention **listeners và captured name strings**. Ví dụ tiếp theo minh họa việc giữ cả owner object.

## 16. Lambda capture `this` có thể giữ cả component

Tạo **`ListenerCapturesOwnerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Hub {
    private static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static void subscribe(Runnable listener) {
        LISTENERS.add(listener);
    }

    static int count() {
        return LISTENERS.size();
    }
}

final class Screen {
    private final String name;
    private final byte[] snapshot = new byte[1024];

    Screen(String name) {
        this.name = name;
        Hub.subscribe(this::refresh);
    }

    private void refresh() {
        System.out.println(name + ":" + snapshot.length);
    }
}

public class ListenerCapturesOwnerDemo {
    public static void main(String[] args) {
        new Screen("home");
        System.out.println(Hub.count());
    }
}
```

```bash
javac ListenerCapturesOwnerDemo.java
java ListenerCapturesOwnerDemo
```

```text
1
```

`this::refresh` tạo listener object có receiver là Screen instance. Khi Hub giữ callback, Screen (và snapshot array) tiếp tục reachable qua callback.

**Quan trọng:** Có thể Screen không còn visible trong UI và không còn local variable, nhưng subscription vẫn còn trong Hub. Đây là tình huống điển hình mà heap profiler cho thấy retained path từ static field đến object “đã đóng”.

Để khắc phục, cần lưu **chính callback/subscription handle** và gỡ đăng ký khi owner close.

## 17. Sửa listener: giữ reference và gọi `unsubscribe`

Tạo **`ListenerUnsubscribeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Hub {
    private final List<Runnable> listeners =
            new ArrayList<>();

    void subscribe(Runnable listener) {
        listeners.add(listener);
    }

    void unsubscribe(Runnable listener) {
        listeners.remove(listener);
    }

    int count() {
        return listeners.size();
    }

    void publish() {
        for (Runnable listener : List.copyOf(listeners)) {
            listener.run();
        }
    }
}

final class Screen implements AutoCloseable {
    private final Hub hub;
    private final Runnable listener;

    Screen(Hub hub) {
        this.hub = hub;
        this.listener = this::refresh;
        hub.subscribe(listener);
    }

    private void refresh() {
        System.out.println("screen refreshed");
    }

    @Override
    public void close() {
        hub.unsubscribe(listener);
    }
}

public class ListenerUnsubscribeDemo {
    public static void main(String[] args) {
        Hub hub = new Hub();

        try (Screen screen = new Screen(hub)) {
            System.out.println(hub.count());
            hub.publish();
        }

        System.out.println(hub.count());
        hub.publish();
    }
}
```

```bash
javac ListenerUnsubscribeDemo.java
java ListenerUnsubscribeDemo
```

```text
1
screen refreshed
0
```

- Screen tạo callback một lần và lưu trong field `listener`.
- Hub lưu callback khi subscribe.
- `close` remove đúng callback đã đăng ký.
- `try-with-resources` đảm bảo close được gọi khi block kết thúc.
- Sau close, hub không còn listener; `publish()` không còn in refresh.
- Ví dụ đơn luồng; event bus production cần concurrency policy.

**Điểm rất dễ quên:** Đừng gọi `unsubscribe(this::refresh)` bằng cách tạo lại method-reference expression và giả định nó luôn equal với callback đã đăng ký. Identity/equality của các functional objects không phải contract bảo đảm các biểu thức riêng sẽ cho cùng object. Hãy **giữ handle hoặc đúng listener reference**.

## 18. Thiết kế subscription handle `AutoCloseable` tốt hơn

Một API event source có thể trả về một **subscription handle** khi đăng ký, để caller không phải nhớ chính xác listener object khi gỡ.

Tạo **`SubscriptionHandleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class EventSource {
    private final List<Runnable> listeners =
            new ArrayList<>();

    AutoCloseable subscribe(Runnable listener) {
        Objects.requireNonNull(listener);
        listeners.add(listener);

        return new AutoCloseable() {
            private boolean closed;

            @Override
            public void close() {
                if (!closed) {
                    closed = true;
                    listeners.remove(listener);
                }
            }
        };
    }

    void publish() {
        for (Runnable listener : List.copyOf(listeners)) {
            listener.run();
        }
    }

    int count() {
        return listeners.size();
    }
}

public class SubscriptionHandleDemo {
    public static void main(String[] args) throws Exception {
        EventSource events = new EventSource();

        try (AutoCloseable subscription =
                     events.subscribe(() ->
                             System.out.println("received"))) {
            events.publish();
            System.out.println(events.count());
        }

        events.publish();
        System.out.println(events.count());
    }
}
```

```bash
javac SubscriptionHandleDemo.java
java SubscriptionHandleDemo
```

```text
received
1
0
```

`subscribe` trả AutoCloseable để client biểu diễn **lifetime của subscription bằng resource scope**. Handle này close idempotently (gọi thêm lần nữa không remove lần thứ hai).

### Những điều cần xem xét khi triển khai thật

- `AutoCloseable.close()` có thể khai báo `throws Exception`; API có thể trả một interface riêng như `Subscription extends AutoCloseable` với signature hẹp hơn.
- Nếu một listener đăng ký nhiều lần, remove một lần có thể chỉ xóa một occurrence; cần định nghĩa duplicates policy.
- Trong concurrent event sources, việc subscribe/close/publish cần synchronization hoặc concurrent collection.
- Callback đang được thực thi có thể tiếp tục chạy dù đã unsubscribe; contract về *in-flight events* phải rõ.
- Event source sống ngắn hơn owner cũng cần shutdown/clear của riêng nó.

## 19. Vì sao `List.copyOf(listeners)` được dùng lúc publish?

Nếu event handler unsubscribe trong lúc Hub đang duyệt `ArrayList` trực tiếp bằng for-each, nó có thể tạo `ConcurrentModificationException` hoặc behavior không mong muốn.

Chụp snapshot:

```java
for (Runnable listener : List.copyOf(listeners)) {
    listener.run();
}
```

giúp duyệt một danh sách không thay đổi trong callback loop **ở demo đơn luồng**. Nó **không** làm subscribe/unsubscribe từ nhiều threads tự thread-safe; muốn concurrency safety phải điều phối các writes/reads.

Snapshot cũng giữ references tới listeners trong suốt lúc publish, nên unsubscribe giữa lúc đang publish không bảo đảm callback chưa được gọi trong lượt publish hiện tại.

**Bài học:** Memory retention, mutation semantics và concurrency là những hợp đồng riêng phải được thiết kế và test.

## 20. Listeners có thể là closures giữ payload lớn

Một listener lambda có thể capture các objects, không chỉ một vài values.

Tạo **`CapturedPayloadDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CapturedPayloadDemo {
    private static final List<Runnable> CALLBACKS =
            new ArrayList<>();

    public static void main(String[] args) {
        byte[] report = new byte[2048];

        CALLBACKS.add(() ->
                System.out.println(report.length));

        System.out.println(CALLBACKS.size());
        CALLBACKS.get(0).run();

        CALLBACKS.clear();
        System.out.println(CALLBACKS.isEmpty());
    }
}
```

```bash
javac CapturedPayloadDemo.java
java CapturedPayloadDemo
```

```text
1
2048
true
```

Lambda reference được giữ trong static CALLBACKS; listener capture `report`, giữ array có thể reachable lâu hơn main code ban đầu cần. `clear` xóa path từ list; không có khẳng định GC chạy ngay.

### Giảm retention

- Nếu handler chỉ cần ID, capture một **immutable ID** thay vì cả request context.
- Khi owner close, unsubscribe.
- Tránh đăng ký lại listener trùng mỗi lần render/mở màn hình.
- Nếu event system hỗ trợ weak listeners, hiểu rõ semantics trước khi dùng; weak listener có thể biến mất khi caller tưởng vẫn active.
- Không xây listener chỉ để tránh nhớ cleanup bằng cách dựa vào GC.

## 21. Đăng ký trùng và số listener tăng qua từng lần mở màn hình

Một pattern dễ gây leak:

```java
void onOpen() {
    eventHub.subscribe(this::onEvent);
}
```

Nếu gọi `onOpen` nhiều lần mà mỗi lần thêm callback mới, số listeners tăng. Không hề có invariant “mỗi instance chỉ đăng ký một lần” nếu API không thực thi.

Một component lifecycle tốt cần:

1. Subscription được thiết lập **đúng một lần** trong phase start/open phù hợp.
2. Handle được giữ bởi owner.
3. Stop/close gọi unsubscribe **đúng lúc**.
4. Lặp lại stop/close không tạo lỗi hoặc vô tình gỡ subscription của instance khác.
5. Nếu restart được, subscription mới phải được tạo và các state fields phải cập nhật hợp lệ.
6. Test chu kỳ open/close nhiều lần và assert count trở về baseline.

**Không nên dùng boolean guard tùy tiện** nếu nhiều threads/async callbacks có thể race. Khi lifecycle concurrent, cần state machine và synchronization thích hợp.

## 22. Các kiểu registration khác cũng có cùng rủi ro

Không chỉ UI event bus; cùng một cấu trúc references tồn tại trong:

- Observer pattern và callbacks của service.
- Property change listeners.
- Message subscriptions và pub/sub consumers.
- Scheduled tasks, timers, executor queues.
- Database change listeners.
- Metrics registries gắn labels tới object graph.
- Monitoring/tracing hooks.
- Watch services / file watchers.
- Global event bus.
- Application context giữ beans/request data nhầm scope.

**Cách truy vấn:** Đối tượng nào **đăng ký** với manager sống lâu hơn nó? Manager giữ reference **mạnh hay yếu**? Có API `close/unsubscribe/remove/cancel` không, và ai gọi?

Trả lời được bốn câu hỏi này thường nhanh hơn việc thêm hàng loạt null assignments.

## 23. `ThreadLocal` trong thread pool: leak qua worker thread sống lâu

`ThreadLocal<T>` liên kết giá trị với thread hiện tại. Nếu dùng thread pool, threads được **tái sử dụng**, nên dữ liệu của task trước có thể ở lại lâu sau khi task kết thúc nếu không gọi `remove()`.

Đường retention khái niệm:

```text
live worker Thread
   └── ThreadLocalMap
         └── entry
               └── value: RequestContext
                     └── large payload/session references
```

Kể cả khi ThreadLocal key sử dụng weak reference trong nội bộ, values có thể tiếp tục được giữ đến khi cơ chế cleanup thích hợp xảy ra; đừng coi weak key là tự động cleanup đúng deadline.

### Ví dụ an toàn và deterministic

Tạo **`ThreadLocalCleanupDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            Future<?> first = pool.submit(() -> {
                CONTEXT.set("request-1");

                try {
                    System.out.println(CONTEXT.get());
                } finally {
                    CONTEXT.remove();
                }
            });
            first.get();

            Future<?> second = pool.submit(() ->
                    System.out.println(CONTEXT.get() == null));
            second.get();
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

```text
request-1
true
```

`newSingleThreadExecutor` tái sử dụng một worker thread cho hai tasks trong ví dụ. Dùng `Future.get()` để chờ tasks hoàn tất và tạo thứ tự output rõ ràng. `finally` đảm bảo remove ngay cả khi task gặp exception.

**Không chỉ reset `CONTEXT.set(null)` rồi cho là đủ:** `remove()` là cách explicit để loại entry của ThreadLocal khỏi thread-local map theo API. Việc set null có semantics khác và dễ che khuất lifecycle.

## 24. Nếu quên `ThreadLocal.remove()` thì có chuyện gì?

Về logic, task sau trên cùng worker thread có thể đọc request context còn sót của task trước. Đây vừa là nguy cơ **memory retention**, vừa là **cross-request data contamination**.

**Mã sai có chủ đích về lifecycle** (không có cleanup):

```java
static final ThreadLocal<String> REQUEST =
        new ThreadLocal<>();

void handleRequest(String id) {
    REQUEST.set(id);
    // xử lý request; quên REQUEST.remove()
}
```

Đây chỉ là mảnh minh họa trong một class hợp lệ, không phải chương trình độc lập.

### Sửa

```java
void handleRequest(String id) {
    REQUEST.set(id);
    try {
        // Xử lý request.
    } finally {
        REQUEST.remove();
    }
}
```

**Không hứa remove mọi leak tự động:** Nếu request context đã được chụp vào static callback/cache, loại ThreadLocal chỉ cắt **một reference path**. Phải kiểm toàn bộ graph.

Trong application servers, thread pools tồn tại lâu, nên ThreadLocal cleanup đặc biệt quan trọng.

## 25. Task queue và cancellation cũng có thể giữ callbacks

Một `Runnable` hoặc `Callable` có thể capture big objects. Nếu task bị queue trong một executor sống lâu và không được chạy/loại bỏ, queue giữ task → captured references.

Một scheduled future với thời gian chờ dài cũng có thể giữ payload mà app nghĩ đã hủy bỏ. `cancel` và executor cleanup policies có các chi tiết implementation/configuration, nên cần thiết kế theo APIs thực tế.

**Các câu hỏi:**

- Có giới hạn pending tasks/queue capacity không?
- Hủy job có xóa reference tới task khỏi cấu trúc lưu trữ không, và lúc nào?
- Task có capture cả request/controller thay vì immutable identifier không?
- Các pending futures có được bỏ khỏi registry sau completion?
- Có xử lý shutdown và shutdownNow rõ ràng không?
- Có timeout, backpressure và cancellation contract không?

Đây là **cùng một pattern**: một owner sống lâu giữ closure/object graph vượt lifecycle cần thiết.

## 26. Resource leak và heap memory leak là hai lớp vấn đề

Một đối tượng FileInputStream có thể hết scope trong Java nhưng file descriptor vẫn chưa được đóng đúng lúc. Đó là **resource leak**, không được coi là “GC chắc chắn dọn”.

Ngược lại, một static list chứa hàng nghìn byte arrays là **heap retention**, dù không chứa external resource nào.

| Dấu hiệu | Heap retention | Resource leak |
| --- | --- | --- |
| Thứ bị giữ | Java object graphs | File/socket/DB/native handles |
| Chẩn đoán | Heap dump, retained paths, live-set trend | Open descriptors, pools, native memory metrics |
| Lỗi thường gặp | Static cache/listener chưa remove | Quên close/rollback/unsubscribe |
| Cách sửa | Cắt strong references đúng lifecycle | Dùng `AutoCloseable`/`try-with-resources` |
| `System.gc()` có sửa được? | Không sửa ownership | Không bảo đảm cleanup đúng hạn |
| Có thể cùng xuất hiện? | Có | Có |

**Một listener đăng ký không được gỡ** có thể vừa giữ Java objects, vừa làm resource wrapper không được close nếu component owner cũng chịu trách nhiệm resource.

## 27. `try-with-resources` kết hợp tốt với subscription lifetime

Thay vì trông chờ garbage collection, API có thể biểu diễn một registration như `AutoCloseable`.

Ví dụ từ SubscriptionHandleDemo:

```java
try (AutoCloseable subscription =
         events.subscribe(this::handle)) {
    // Hoạt động khi subscription còn sống.
}
// close() gỡ listener.
```

Đây là **mảnh minh họa** giả định `events`, `handle` và `this` nằm trong scope phù hợp; nếu method trả AutoCloseable có thể ném checked exception từ close, cần signature/catch tương ứng.

Tốt hơn đối với event source có lifecycle dài, component owner cũng implements AutoCloseable:

- Construction/start tạo subscription handle.
- Close/stop close handle.
- Owner stop được gọi khi UI screen, request hoặc service bị dỡ.
- Không tạo lại handle vào mỗi callback.
- Cleanup ở `finally` cho startup lỗi/cancellation.

**Khác với GC:** `close` được gọi theo control flow đã thiết kế, **không phụ thuộc khi nào object biến mất**.

## 28. Đừng giữ toàn bộ object khi chỉ cần identifier

Một static cache:

```java
static final Map<String, RequestContext> REQUESTS =
        new java.util.HashMap<>();
```

có thể giữ mọi fields của RequestContext (HTTP request, user profile, buffers, attachments...). Nếu chỉ cần trạng thái ID, hãy cân nhắc lưu value đơn giản như String, immutable record summary hoặc một DTO nhỏ.

Ví dụ:

```java
record RequestSummary(String id, int status) {
}
```

**Không phải luôn copy mọi object:** Cần cân nhắc memory/cost và semantics. Nhưng thay reference đến graph lớn bằng một immutable snapshot nhỏ có thể giảm retained size nhiều lần.

**Giải pháp tối ưu là giữ đúng dữ liệu và đúng lifetime**, không phải đơn giản thay strong reference bằng weak reference trong mọi trường hợp.

## 29. ClassLoader retention và static fields: điểm nâng cao

Mỗi class được định danh trong JVM bởi cặp gồm binary name và defining class loader. Các static fields thuộc class tương ứng với classloader đó. Trong ứng dụng có reloadable plugins/webapp, classloader có thể bị giữ sống nếu có references từ thành phần sống lâu hơn đến objects/classes liên quan.

Đường giữ đơn giản:

```text
long-lived platform/service
    └── listener registry
          └── callback from plugin
                └── plugin object
                      └── plugin class / loader relationships
```

Nếu module/plugin “unload” về mặt nghiệp vụ nhưng không unregister callback, classloader liên quan có thể không thể được unload.

**Cẩn thận:** Không phải mọi static field mặc nhiên là một GC root bất tử; class unloading và reachability semantics phức tạp. Nhưng việc giữ references qua **boundary giữa classloaders/lifecycles** là nguồn memory retention rất thường gặp trong plugin/app-server environments.

### Cleanup đúng hướng

- Registry ở platform cần gỡ plugin callbacks khi plugin stop.
- Threads do plugin tạo cần dừng.
- ThreadLocal values/classes gắn với plugin trên shared worker threads cần cleanup.
- Caches có keys/values là plugin classes cần invalidation phù hợp.
- Resources do plugin mở cần close.
- Dùng heap analysis để xác nhận classloader paths trước khi kết luận.

## 30. Ví dụ lifecycle manager đóng toàn bộ registrations

Khi một component đăng ký **nhiều** subscriptions, nên quản lý tập handles thuộc cùng owner và close tất cả.

Tạo **`SubscriptionGroupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class CloseGroup implements AutoCloseable {
    private final List<AutoCloseable> resources =
            new ArrayList<>();
    private boolean closed;

    void add(AutoCloseable resource) {
        if (closed) {
            throw new IllegalStateException("group closed");
        }
        resources.add(resource);
    }

    @Override
    public void close() throws Exception {
        if (closed) {
            return;
        }
        closed = true;

        Exception first = null;
        for (int i = resources.size() - 1; i >= 0; i--) {
            try {
                resources.get(i).close();
            } catch (Exception ex) {
                if (first == null) {
                    first = ex;
                } else {
                    first.addSuppressed(ex);
                }
            }
        }
        resources.clear();

        if (first != null) {
            throw first;
        }
    }
}

public class SubscriptionGroupDemo {
    public static void main(String[] args) throws Exception {
        try (CloseGroup group = new CloseGroup()) {
            group.add(() -> System.out.println("unregister A"));
            group.add(() -> System.out.println("unregister B"));
            System.out.println("active");
        }
        System.out.println("closed all");
    }
}
```

```bash
javac SubscriptionGroupDemo.java
java SubscriptionGroupDemo
```

```text
active
unregister B
unregister A
closed all
```

**Vì sao có xử lý exceptions?** Nếu một close thất bại, group vẫn cố close những handles còn lại. Exception đầu tiên được ném lại, các exceptions sau được gắn suppressed. Đây là policy minh họa; trong production cần định nghĩa rõ error reporting, concurrency và registration rollback nếu `add` thất bại.

**Cần nhớ:** Nhóm handles chưa tự biến tất cả subscriptions thành weak references. Nó cung cấp **một nơi duy nhất chịu trách nhiệm cleanup**, giúp tránh quên từng registration.

## 31. Thiết kế observer API tránh quên ownership

Một API subscriber nên nói rõ:

- `subscribe` trả **handle** hay cần truyền lại listener object?
- Handler được giữ **strongly hay weakly**?
- `unsubscribe/close` có **idempotent** không?
- Gỡ listener trong khi đang publish có làm callback hiện tại chạy tiếp không?
- Có cho duplicate registrations không?
- Owner sống lâu hơn source hay source sống lâu hơn owner?
- Ai close subscriptions nếu initialization thất bại một nửa?
- API thread-safe không?
- Subscriptions có timeout/TTL hoặc expire theo connection không?

Ví dụ đặt trách nhiệm:

| Phía | Trách nhiệm |
| --- | --- |
| Event source | Quản lý listeners, phát sự kiện, loại đúng entry |
| Subscriber owner | Giữ handle và close khi lifecycle kết thúc |
| Application lifecycle | Gọi stop/close trên các owners |
| Test | Assert listener count trở về baseline |
| Monitoring | Quan sát registration count/retained size theo thời gian |

**Đừng ẩn lifecycle:** Nếu API chỉ trả void từ subscribe, caller dễ quên làm sao remove. Trả `Subscription` handle giúp code review thấy đường cleanup.

## 32. Heap dump: đi từ retained object ngược về root

Một profiler/heap dump analyzer thường có khả năng xem:

1. **Shallow size**: bộ nhớ tương ứng một object.
2. **Retained size**: tổng bộ nhớ có thể được giải phóng nếu object/nhánh retention nhất định không còn reachable (theo công cụ và định nghĩa dominator graph).
3. **Paths to GC roots**: tại sao object vẫn reachable?
4. **Dominators**: những objects giữ sống những nhóm lớn trong graph.
5. **Class histogram**: bao nhiêu instances của từng class và tổng heap footprint ước tính.

Quy trình:

- Chụp số liệu sau warm-up hoặc trước/sau workload xác định.
- Quan sát **live set sau collections phù hợp**, không chỉ allocated bytes.
- Tìm các class tăng về live instance count hoặc retained size.
- Truy ngược root path đến static map/listener registry/ThreadLocal/queue.
- Tương ứng path ấy với expected lifecycle.
- Sửa loại bỏ đúng reference edge.
- Kiểm lại bằng workload tương tự để tránh kết luận từ một snapshot đơn.

**Không được khẳng định một object “leak” chỉ vì nó vẫn sống khi heap dump được chụp.** Cần đối chiếu nó với chức năng, lifecycle và tốc độ tăng thực tế.

## 33. Những số liệu nên theo dõi

| Metric | Mục đích |
| --- | --- |
| Cache entry count | Có tiến gần/qua giới hạn? |
| Cache weight/bytes | Memory footprint thực tế |
| Hit/miss rate | Cache có mang lợi ích không? |
| Eviction/expiry count | Chính sách loại bỏ có hoạt động? |
| Active sessions | Có giảm sau logout/timeout? |
| Listener count | Có tăng sau mỗi open/close cycle? |
| Pending task count | Queue/scheduler có tích tụ? |
| ThreadLocal cleanup failures | Context có thể sót giữa tasks? |
| Post-GC live heap trend | Live objects có tăng lâu dài? |
| Native resource count | Leak không thuộc heap? |
| ClassLoader instances | Plugin/redeploy có unload đúng không? |

Những metrics không tự chứng minh root cause. Nhưng **giữ lifecycle expectations** như “mỗi screen đóng thì listener count giảm 1” thường giúp phát hiện regression sớm.

## 34. Vì sao `Runtime.freeMemory()` là phép kiểm leak kém?

JVM heap management có thể giữ committed heap, cấp phát thêm, compact, optimize hoặc GC không đồng bộ với lệnh ứng dụng. Các giá trị `totalMemory/freeMemory` thay đổi vì nhiều nguyên nhân không chỉ live object count.

Ví dụ assertion thiếu tin cậy:

```java
// long before = Runtime.getRuntime().freeMemory();
// registry.clear();
// long after = Runtime.getRuntime().freeMemory();
// assert after > before; // Không được bảo đảm.
```

Đây là **mã sai về giả định đo lường**.

### Test thay thế

Kiểm deterministic business invariants:

- Cache size không vượt limit.
- Sau close, listener count giảm về baseline.
- Khi timeout, get trả null và entry bị xóa.
- Sau task, ThreadLocal được remove, task tiếp theo không thấy context cũ.
- Sau shutdown, pending handles được close.
- Không có duplicate registrations sau 100 vòng open/close.

Còn chứng minh leak thật cần profiling theo thời gian và workload.

## 35. Lỗi số 4: giữ request/session trong singleton

Một singleton/service thường sống suốt app. Nếu service cất `HttpRequest` hoặc `UserSession` trong field/static list “để dùng sau”, request graph sẽ sống lâu ngoài dự kiến.

Ví dụ conceptual:

```java
class AuditService {
    private Object lastRequest;

    void audit(Object request) {
        lastRequest = request;
    }
}
```

Khai báo này hợp lệ nhưng có thể gây retention nếu service sống lâu và lastRequest giữ graph lớn. Đôi khi lưu object request mới nhất trong thời gian ngắn có chủ đích; nhưng cần đánh giá **retained size và ownership**.

Một hướng tốt hơn:

```java
record AuditRecord(String requestId, int status) {
}
```

Lưu một dữ liệu nhỏ cần audit thay vì giữ toàn bộ request object, stream/body buffers, session refs.

**Không nhầm:** Không phải mọi singleton field là memory leak; **đường sống lâu vượt lifecycle cần thiết** mới là vấn đề.

## 36. Cache mutable object vs immutable snapshot

Nếu cache giữ mutable entity mà caller có thể sửa, bạn gặp hai vấn đề:

- **Memory retention**: reference sống lâu.
- **State consistency**: cache chứa object bị mutate ngoài ý muốn hoặc share với request.

Sử dụng immutable snapshot như record components nhỏ hoặc copy của collection giúp tránh một số side effects. Nhưng immutable object vẫn có thể bị retained nếu nằm mãi trong static map.

**Lưu ý:** `List.copyOf` chỉ tạo/cung cấp unmodifiable list structure, không deep-copy những mutable elements. Một list cache chứa `byte[]` objects vẫn có thể share nội dung mutable ở từng phần tử.

Chọn representation theo domain và size; không lấy “immutable” làm lý do bỏ qua eviction.

## 37. Một static cache trong tests làm rò state giữa test cases

Tests trong cùng JVM có thể chia sẻ static fields. Nếu test A đưa dữ liệu vào static cache, test B có thể quan sát lại dữ liệu ấy nếu không reset; tests trở nên order-dependent.

Tạo **`StaticStateIsolationDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class TestRegistry {
    private static final Set<String> VALUES =
            new HashSet<>();

    static void add(String value) {
        VALUES.add(value);
    }

    static int size() {
        return VALUES.size();
    }

    static void reset() {
        VALUES.clear();
    }
}

public class StaticStateIsolationDemo {
    public static void main(String[] args) {
        TestRegistry.add("from-test-A");
        System.out.println(TestRegistry.size());

        TestRegistry.reset();
        System.out.println(TestRegistry.size());
    }
}
```

```bash
javac StaticStateIsolationDemo.java
java StaticStateIsolationDemo
```

```text
1
0
```

**Trong production:** Một global reset không phải luôn hợp lệ khi có active users. Trong tests, nếu component sở hữu state tạm thì cleanup qua fixture/afterEach hoặc dependency injection sẽ rõ hơn.

Một thiết kế tránh static mutable fields cũng làm testing/isolation dễ hơn: inject cache/registry instance vào code cần dùng, rồi tạo instance mới mỗi test.

## 38. Refactor từ static sang instance scope

Nếu registry chỉ phục vụ một request/session/component, thay vì static global registry, ta có thể tạo registry instance thuộc owner. Khi owner không còn reachable và các subscriptions/threads bên ngoài không giữ lại nó, cả graph có thể được GC thu hồi tự nhiên.

Tạo **`ScopedRegistryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class RequestRegistry {
    private final List<String> messages =
            new ArrayList<>();

    void add(String message) {
        messages.add(message);
    }

    int size() {
        return messages.size();
    }
}

public class ScopedRegistryDemo {
    static int handleRequest() {
        RequestRegistry registry = new RequestRegistry();
        registry.add("one");
        registry.add("two");
        return registry.size();
    }

    public static void main(String[] args) {
        System.out.println(handleRequest());
        System.out.println(handleRequest());
    }
}
```

```bash
javac ScopedRegistryDemo.java
java ScopedRegistryDemo
```

```text
2
2
```

Mỗi request có registry riêng, không dùng static state. Tuy nhiên, nếu registry được return/stored trong static field hoặc captured trong callback dài hạn, nó vẫn có thể được giữ sống. **Instance field không tự bảo đảm không leak**; nó chỉ làm ownership boundary dễ kiểm soát hơn.

## 39. Tình huống xử lý exception: cleanup trong `finally`

Khi registration hoặc ThreadLocal là tạm thời, cần cleanup cả trên success, failure, early return và cancellation (theo control flow có thể kiểm soát).

Tạo **`FinallyCleanupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Registry {
    private static final List<String> ACTIVE =
            new ArrayList<>();

    static void enter(String id) {
        ACTIVE.add(id);
    }

    static void leave(String id) {
        ACTIVE.remove(id);
    }

    static int size() {
        return ACTIVE.size();
    }
}

public class FinallyCleanupDemo {
    static void execute(String id) {
        Registry.enter(id);
        try {
            throw new IllegalStateException("failed");
        } finally {
            Registry.leave(id);
        }
    }

    public static void main(String[] args) {
        try {
            execute("R1");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println(Registry.size());
    }
}
```

```bash
javac FinallyCleanupDemo.java
java FinallyCleanupDemo
```

```text
failed
0
```

Code cố tình ném exception; finally vẫn remove entry. **Trường hợp initialization thất bại trước enter** cần xem theo design riêng; không blindly remove entry của task khác khi key trùng.

Với async workflows, lifecycle có thể không gói trong một lexical try block; lúc đó sử dụng subscription handles, structured ownership hoặc task completion callbacks một cách rõ ràng.

## 40. Concurrency trong caches và registries: phân biệt race với leak

Một `HashMap` được truy cập đồng thời mà không synchronization có thể dẫn tới race, visibility problems và cấu trúc/hành vi sai. Đổi sang `ConcurrentHashMap` có thể giải quyết một số vấn đề thread safety, nhưng **không tự giới hạn kích thước**.

Ví dụ:

```java
static final java.util.concurrent.ConcurrentMap<String, Object>
        CACHE = new java.util.concurrent.ConcurrentHashMap<>();
```

Dù thread-safe ở mức map operations, nếu gọi `CACHE.put(...)` với keys không ngừng tăng, map vẫn có thể giữ objects vô hạn.

**Hai chính sách độc lập:**

- Concurrency control: an toàn khi nhiều threads đọc/ghi.
- Lifetime/memory control: giới hạn, expire, remove, invalidate.

Cần cả hai khi cache shared giữa threads.

## 41. Những hiểu lầm về `System.gc()` và GC tuning

Một ứng dụng gặp `OutOfMemoryError` do static registry tăng vô hạn đôi khi cố:

```java
System.gc();
```

Việc này **không cắt strong references**. GC có thể tìm thấy list và entries vẫn reachable, nên không được loại chúng chỉ vì chương trình không còn cần.

Tăng heap size có thể trì hoãn `OutOfMemoryError`, nhưng cũng **không sửa nguyên nhân root path**. GC tuning có thể tốt cho latency/throughput nếu retention hợp lệ, nhưng với logic giữ dữ liệu vô hạn thì bài toán đầu tiên là lifecycle/eviction.

**Quy trình ưu tiên:** Tìm đồ thị tham chiếu → xác định owner/retention policy → sửa cleanup/limits → kiểm lại live set → sau đó mới tuning nếu còn cần.

## 42. Nếu memory tiếp tục tăng sau khi remove, kiểm gì?

Không nên vội kết luận fix không có tác dụng vì process memory chưa giảm ngay. Hãy kiểm:

1. Entry được remove đúng map/list, đúng key/callback instance không?
2. Có map khác, snapshot, closure hay future vẫn giữ object không?
3. Có thread-local context giữ value không?
4. Có classloader hoặc JNI handle giữ references không?
5. Object count/live set sau GC còn tăng không?
6. JVM đang giữ committed heap để tái sử dụng không?
7. Có native/off-heap allocations chưa release?
8. Workload, cache warm-up và allocation rate thay đổi chưa?

**Memory leak diagnosis là bài toán retained object graph**, không phải chỉ in `Runtime.freeMemory()` trước và sau một remove.

## 43. Phân loại: normal caching, high memory use, leak

| Trường hợp | Đánh giá |
| --- | --- |
| Cache cố định 100 entries, phù hợp tải và payload | Thường retention có chủ đích |
| Cache có TTL nhưng lazy cleanup, không bao giờ đọc keys cũ | Vẫn có nguy cơ tích tụ |
| Static list không giới hạn với dữ liệu request | Rủi ro leak rất cao |
| Listener count trở về baseline sau mọi close | Một dấu hiệu lifecycle tốt |
| Listener count tăng sau mỗi open/close | Dấu hiệu duplicate/unremoved subscription |
| Heap committed vẫn lớn sau GC nhưng live set ổn định | Chưa đủ kết luận leak |
| Live objects tăng vô hạn dưới workload tương tự | Cần điều tra root paths |
| WeakHashMap nhưng values giữ keys | Weak-key eviction có thể không hiệu quả |
| Resource đã close nhưng object còn reachable | Không nhất thiết là resource leak; có thể retention |
| Object unreachable nhưng external resource chưa close | Resource leak có thể xảy ra |

**Không có một threshold áp dụng cho mọi ứng dụng.** Điều quyết định là business lifetime, load pattern và chính sách giữ dữ liệu.

## 44. Bài thực hành: đo invariant listener qua nhiều vòng open/close

Tạo **`RepeatedSubscriptionSelfTest.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Bus {
    private final List<Runnable> listeners =
            new ArrayList<>();

    AutoCloseable subscribe(Runnable listener) {
        listeners.add(listener);
        return () -> listeners.remove(listener);
    }

    int count() {
        return listeners.size();
    }
}

public class RepeatedSubscriptionSelfTest {
    static void check(boolean result, String label) {
        if (!result) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws Exception {
        Bus bus = new Bus();

        for (int i = 0; i < 100; i++) {
            try (AutoCloseable ignored =
                         bus.subscribe(() -> {})) {
                check(bus.count() == 1, "registered");
            }
            check(bus.count() == 0, "unregistered");
        }

        System.out.println("listener lifecycle PASS");
    }
}
```

```bash
javac RepeatedSubscriptionSelfTest.java
java RepeatedSubscriptionSelfTest
```

```text
listener lifecycle PASS
```

Test không quan sát GC. Nó chứng minh vòng subscribe/close hiện tại không làm Bus.listeners tăng sau 100 lần mở/đóng.

### Cần test thêm

- Callback ném exception.
- Đăng ký hai listeners khác nhau và hủy một.
- Hủy nhiều lần (idempotency policy).
- Đăng ký trùng listener reference nếu API cho phép.
- Unsubscribe trong lúc publish.
- Shutdown toàn event source.
- Concurrent subscription/delivery nếu là requirement.

## 45. Bài thực hành: kiểm cache capacity nhiều lần thêm dữ liệu

Tạo **`CacheCapacitySelfTest.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

class LimitedCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;

    LimitedCache(int capacity) {
        super(16, 0.75f, true);
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

public class CacheCapacitySelfTest {
    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError();
        }
    }

    public static void main(String[] args) {
        LimitedCache<Integer, String> cache =
                new LimitedCache<>(3);

        for (int i = 0; i < 100; i++) {
            cache.put(i, "value-" + i);
            check(cache.size() <= 3);
        }

        System.out.println(cache.size());
        System.out.println(cache.containsKey(99));
        System.out.println(cache.containsKey(0));
        System.out.println("capacity PASS");
    }
}
```

```bash
javac CacheCapacitySelfTest.java
java CacheCapacitySelfTest
```

```text
3
true
false
capacity PASS
```

Với 100 keys khác nhau và capacity 3, map giữ tối đa ba entries. Test không dựa vào bytes hoặc GC scheduling. Production có thể còn cần weight bound, time eviction và synchronization.

## 46. Bài thực hành: sửa một static cache không giới hạn

Mã có vấn đề:

```java
static final Map<String, byte[]> CACHE =
        new HashMap<>();

static void remember(String id, byte[] payload) {
    CACHE.put(id, payload);
}
```

Đây là **mảnh minh họa**. Với các id mới liên tục, map giữ tất cả arrays theo strong references.

**Yêu cầu:** Đề xuất một chính sách:

- Số entries tối đa hợp lý hoặc max weighted bytes.
- TTL/idle expiry dựa trên domain.
- Invalidation khi source data thay đổi.
- Có cleanup khi application/module đóng.
- Không giữ request object graph khi chỉ cần snapshot.
- Có metric size/evictions/weight.
- Nếu values sở hữu external resources, có cleanup contract khi evict.
- Nếu shared, có concurrency control.

**Một sửa tối thiểu** là bounded LRU ở phần 9. Nhưng nếu payload size thay đổi rất lớn, chỉ giới hạn số entries là chưa đủ; chọn weight-based eviction hoặc lưu dữ liệu ở cấp storage phù hợp.

## 47. Bài thực hành: sửa đăng ký UI không được gỡ

Mã sai về lifecycle:

```java
class Editor {
    Editor(EventHub hub) {
        hub.addListener(this::onChange);
    }

    void onChange() {
        // Cập nhật giao diện.
    }
}
```

`EventHub` là API giả định. Vì không giữ listener/subscription handle, owner không có cách rõ ràng để gọi `removeListener`.

Một hướng sửa:

```java
class Editor implements AutoCloseable {
    private final EventHub hub;
    private final Runnable listener;

    Editor(EventHub hub) {
        this.hub = hub;
        this.listener = this::onChange;
        hub.addListener(listener);
    }

    private void onChange() {
        // Cập nhật.
    }

    @Override
    public void close() {
        hub.removeListener(listener);
    }
}
```

Đây là **mẫu minh họa**, cần định nghĩa EventHub đúng signature. Điểm cần học là owner **giữ chính listener reference đã đăng ký** và unsubscribe khi close.

**Trong code thật:** Đảm bảo close được gọi ở teardown của UI, và test listener count sau khi open/close nhiều lần.

## 48. Bài thực hành: ThreadLocal context sót giữa hai requests

Mã sai về lifecycle:

```java
static final ThreadLocal<String> USER =
        new ThreadLocal<>();

void handle(String name) {
    USER.set(name);
    System.out.println(USER.get());
}
```

Trong thread pool, value có thể ở lại cho task tiếp theo.

Sửa:

```java
void handle(String name) {
    USER.set(name);
    try {
        System.out.println(USER.get());
    } finally {
        USER.remove();
    }
}
```

Đây là **các mảnh method** giả định được đặt trong class có USER static field.

**Lưu ý:** Dù có remove, nếu callback async giữ name/context, context có thể tồn tại trong một path khác. Tránh chia sẻ request-scoped mutable objects bừa bãi.

## 49. Checklist kiểm tra memory retention

- [ ] Có static `Map/List/Set` lưu dữ liệu theo request/user/session không?
- [ ] Static fields giữ objects cần thiết hay chỉ do tiện tay?
- [ ] Có hiểu `static final` không làm mutable collection trở thành immutable?
- [ ] Có xác định owner và lifecycle cho mỗi cache/registry?
- [ ] Có remove khi logout, timeout, stop, close, failure?
- [ ] Cache có capacity limit hoặc weight-based bound?
- [ ] TTL có cleanup ngay cả khi keys không được đọc lại?
- [ ] Cache có invalidation khi source data thay đổi?
- [ ] Có cache key cardinality gần vô hạn khiến hit rate thấp?
- [ ] Value cache có vô tình giữ request/controller/large payload graph?
- [ ] Có metrics size, weight, evictions, expiry, hit rate?
- [ ] Có dùng `ConcurrentHashMap` mà tưởng nó tự bound size?
- [ ] Listener registration có matching unregistration path?
- [ ] Có giữ **đúng listener reference/handle** dùng khi subscribe?
- [ ] `close`/unsubscribe có được gọi ở teardown phù hợp?
- [ ] Có duplicate subscriptions sau nhiều vòng open/close?
- [ ] Lambda/method reference có capture `this`/buffer/large object graph?
- [ ] Có subscriptions không được đóng khi initialization thất bại?
- [ ] Event delivery/unsubscribe concurrency contract có rõ?
- [ ] ThreadLocal values có `remove()` trong `finally`?
- [ ] Worker threads/thread pools có được reuse qua requests?
- [ ] Scheduled task queue có limits, cancel, completion cleanup?
- [ ] `WeakHashMap` values có strong back-reference tới keys không?
- [ ] Không dùng weak references như giải pháp cache eviction mặc định?
- [ ] Không dựa vào System.gc/finalize/Cleaner để sửa ownership leak?
- [ ] Resource `AutoCloseable` được close theo contract?
- [ ] Đã phân biệt heap retention với native resource leak?
- [ ] Khi phân tích, đã đi từ object đến GC root path?
- [ ] Có xem retained size, live set trend, không chỉ committed heap?
- [ ] Có regression tests kiểm cache bound và listener baseline?
- [ ] Có cân nhắc classloader/redeployment lifecycle nếu ứng dụng là server/plugin?
- [ ] Có kiểm concurrency và semantics khi nhiều users/tasks hoạt động?
- [ ] Tất cả ví dụ Java 17+ có tên file, class đúng và stdout deterministic?

## 50. Bảng quyết định giải pháp

| Nguồn retention | Căn nguyên | Cách xử lý ưu tiên |
| --- | --- | --- |
| Static list sessions | Không remove entries khi session kết thúc | Logout/timeout cleanup, scope đúng |
| Static unbounded memoization | Key cardinality vô hạn | Capacity/weight, TTL, invalidation |
| Cache lazy TTL | Entries expired nhưng không được get | Periodic/batched expiry và max bound |
| Cache value giữ request graph | Retained size lớn | Cache immutable DTO nhỏ |
| UI listener | Event source giữ callback sau close | Unsubscribe/AutoCloseable handle |
| Method-reference listener | Remove bằng listener object khác | Giữ đúng listener reference/handle |
| Duplicate subscriptions | Start/open gọi subscribe nhiều lần | Lifecycle state và tests lặp |
| ThreadLocal on pool | Không remove value sau task | `try/finally { remove(); }` |
| Queued tasks/futures | Queue giữ captured contexts | Backpressure, cancel/cleanup |
| Classloader không unload | Plugin callbacks/static cross-links | Stop/unregister/clear đúng boundary |
| WeakHashMap key không được clear | Value tham chiếu ngược key | Cắt strong back-reference/design khác |
| File/socket/DB connection | Quên explicit close | `try-with-resources` |
| Heap committed không giảm | JVM có thể giữ heap để tái sử dụng | Xem live set/object graph trước khi kết luận |

**Không có một “GC switch” sửa tất cả.** Tất cả giải pháp hiệu quả đều quy về *right-sized retention policy*, *ownership rõ* và *cleanup chắc chắn*.

## 51. Câu hỏi ôn tập có đáp án

**1.** Java có garbage collector thì còn memory leak được không?

*Có. Objects không còn hữu ích nhưng vẫn reachable qua strong references có thể tiếp tục chiếm bộ nhớ.*

**2.** `static final List` có tự immutable không?

*Không. Final cố định field reference; list content vẫn có thể thay đổi.*

**3.** Vì sao một static cache giữ dữ liệu request có thể leak?

*Static map sống lâu và giữ values/cả object graph vượt request lifecycle.*

**4.** Gán local variable bằng null có giải phóng object đang nằm trong static list không?

*Không, list còn strong reference.*

**5.** Khi remove entry khỏi map, GC có thu hồi object ngay không?

*Không có timing guarantee, và object có thể còn references khác.*

**6.** Cache bounded theo số entries có chắc chắn bounded theo bytes không?

*Không; payload sizes có thể khác nhau rất lớn.*

**7.** `LinkedHashMap` với access-order + removeEldestEntry hỗ trợ gì?

*Có thể xây LRU bounded cache đơn giản trong bối cảnh phù hợp.*

**8.** LRU example có tự thread-safe không?

*Không; LinkedHashMap không thread-safe.*

**9.** TTL lazy cleanup còn có nguy cơ gì?

*Entries expired không được đọc lại có thể tiếp tục chiếm chỗ.*

**10.** Cache invalidation khác eviction gì?

*Invalidation loại giá trị stale theo thay đổi nguồn; eviction loại theo capacity/usage/time policy.*

**11.** Listener registry có thể giữ component như thế nào?

*Giữ callback có reference/capture tới component, từ đó giữ cả object graph.*

**12.** Đăng ký `this::onEvent` rồi remove `this::onEvent` ở biểu thức khác có chắc cùng listener object không?

*Không. Nên lưu đúng listener reference hoặc subscription handle.*

**13.** Vì sao trả AutoCloseable subscription handle hữu ích?

*Nó làm ownership và cleanup gắn với scope/close operation rõ ràng.*

**14.** Listener count tăng sau mỗi lần screen open/close gợi ý gì?

*Có thể duplicate registrations hoặc thiếu unsubscription.*

**15.** `List.copyOf(listeners)` khi publish có tự đảm bảo thread safety không?

*Không; chỉ hỗ trợ snapshot iteration, vẫn cần concurrency policy.*

**16.** Lambda capture byte[] có thể kéo dài lifetime của array không?

*Có nếu lambda còn strongly reachable.*

**17.** `ThreadLocal` vì sao rủi ro trên thread pool?

*Worker thread tái sử dụng có thể giữ value từ request trước nếu không remove.*

**18.** Cleanup ThreadLocal nên làm ở đâu?

*Trong finally sau task/request sử dụng context.*

**19.** `ConcurrentHashMap` có tự giới hạn số entries không?

*Không.*

**20.** `WeakReference` có đảm bảo referent còn tồn tại tới một deadline không?

*Không.*

**21.** `WeakHashMap` weak keys có luôn tự xóa mọi entry không cần thiết không?

*Không, values hoặc references khác có thể giữ key.*

**22.** Có nên assert WeakReference.get()==null ngay sau System.gc không?

*Không, GC timing không xác định.*

**23.** Heap leak và resource leak khác gì?

*Heap retention là objects bị giữ; resource leak là external/native resources không được release theo contract.*

**24.** `System.gc()` có sửa static registry không remove không?

*Không; nó không cắt strong references.*

**25.** Vì sao tăng heap size chỉ là giải pháp tạm với unbounded cache?

*Bộ nhớ vẫn tăng theo key cardinality nếu không có eviction.*

**26.** Một cached value là object nhỏ có thể giữ rất nhiều memory không?

*Có; nó có thể giữ một graph lớn qua các nested references.*

**27.** Heap dump path to GC root giúp gì?

*Xác định chính reference path nào giữ object còn reachable.*

**28.** Retained size khác shallow size thế nào?

*Retained size phản ánh phần object graph bị giữ do một reference dominator/nhánh retention, không chỉ footprint của object đó.*

**29.** Vì sao committed heap lớn không đủ chứng minh leak?

*JVM có thể giữ bộ nhớ đã commit để tái sử dụng dù live set ổn định.*

**30.** Khi classloader plugin không unload, kiểm những nguồn nào?

*Global registrations, ThreadLocals, worker tasks, caches và cross-loader references.*

**31.** Thay static registry bằng instance registry có tự đảm bảo không leak không?

*Không; instance cũng có thể bị giữ từ callback/static field khác. Nhưng scoped ownership có thể dễ quản lý hơn.*

**32.** Nếu listener close có thể throw, có nên bỏ close các handles còn lại?

*Thường không; có thể dùng group cleanup tiếp tục đóng và tổng hợp exceptions theo policy.*

**33.** Nếu không dùng GC làm phép kiểm, nên test memory lifecycle bằng gì?

*Invariant deterministic như listener count về baseline, cache bounded và ThreadLocal task sau không thấy context cũ.*

**34.** Quy tắc quan trọng nhất để tránh leak dạng này là gì?

*Thiết kế rõ ai giữ strong reference, tại sao giữ, giới hạn bao lâu và ai cắt nó khi lifecycle kết thúc.*

## 52. Tham khảo Java 17+

- *Java API — `java.lang.ref`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html — các mức reference reachability.
- *Java API — `WeakHashMap`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html — weak keys và lưu ý values tham chiếu về keys.
- *Java API — `ThreadLocal`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html — `set/get/remove` và giá trị gắn với thread.
- *Java API — `LinkedHashMap`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html — access-order và `removeEldestEntry`.
- *Java API — `AutoCloseable`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html — deterministic cleanup và try-with-resources.
- *Java API — `Reference.reachabilityFence`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html — ranh giới reachability có chủ đích.
- *Java API — `ExecutorService`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html — quản lý tasks và shutdown.

---

**Ghi nhớ cuối bài:** GC của Java thu hồi bộ nhớ của objects **không còn reachable**, không thu hồi objects chỉ vì chúng đã “hết hữu ích” trong logic ứng dụng. Một `static Map/List`, cache thiếu giới hạn hoặc event source giữ listener lâu dài có thể tạo đường **strong reference** từ roots tới toàn bộ object graph. Cách sửa đúng là đặt **ownership/lifecycle** rõ ràng: xóa entries khi kết thúc, giới hạn cache bằng capacity/weight/expiry/invalidation, trả và đóng subscription handles, gọi `ThreadLocal.remove()` trong `finally`, quản lý tasks và resources bằng cleanup APIs thích hợp. **Weak references và `System.gc()` không thay thế chính sách retention**. Hãy kiểm các đường tham chiếu bằng heap analysis khi cần, và viết tests dựa vào **count/bound/cleanup invariants xác định**, không dựa vào thời điểm GC chạy.