# Tránh cache toàn JVM không có chính sách vòng đời trong Java Reflection

## 1. Câu hỏi quan trọng trước khi tạo cache

Một cache Reflection được xem là hoàn chỉnh khi **đúng dữ liệu, đúng chủ sở hữu và đúng thời hạn**. `ConcurrentHashMap` làm việc với nhiều thread nhưng không tự đặt kích thước tối đa, thời gian hết hạn hoặc điểm hủy. Vì vậy, với cache metadata, phải chỉ rõ: *ai tạo, ai được dùng, lúc nào metadata còn hợp lệ, ai loại bỏ, và cần quan sát điều gì sau khi loại bỏ*.

Tình huống cần quyết định khác nhau: metadata cho một request ngắn hạn có thể giữ ở biến local; schema của class dùng hàng triệu lần có thể nằm trong `ClassValue`; registry plugin thay phiên bản phải hủy cache khi plugin dừng; kết quả phụ thuộc policy/tenant phải gắn version hoặc chỉ nằm trong phạm vi request.

Về class loader, một entry giữ `Class<?>`, `Method`, `Field` hoặc handle trong thành phần sống lâu **có thể** giữ loader của plugin cũ. Nhưng không phải cứ thấy `static` là leak: cần xét owner và đường tham chiếu thực. Nội dung chuyên sâu về GC roots và `WeakHashMap` nằm ở bài “Cache giữ Class có thể giữ cả class loader”; bài này tập trung xây **chính sách vòng đời có thể kiểm tra**.

## 2. Phân loại dữ liệu để xác định thời hạn hợp lệ

| Dữ liệu cache | Identity/scope chính | Lúc cần tính lại hoặc loại bỏ |
| --- | --- | --- |
| `Field`, `Method`, `Constructor` của một class cụ thể | `Class<?>`, member signature và quy tắc lookup | Owner/plugin unload hoặc metadata cần rebuild |
| Descriptor bất biến suy từ class | Theo `Class<?>`; `ClassValue` khi phù hợp | Class/schema policy thực sự thay đổi |
| Schema đã lọc theo naming policy/config | Class **cộng policy generation/version** | Đổi policy hoặc phiên bản schema |
| Quyết định field được lộ cho người dùng/tenant | Request/user/policy; tránh cache class-only | Thay quyền, tenant hoặc request context |
| Giá trị `Field.get(instance)` | Trạng thái **instance**, không phải class metadata | Đổi state; thông thường không thuộc metadata cache |
| Dữ liệu/handler của plugin generation cũ | Instance/generation của plugin | Đóng plugin, hủy đăng ký và kết thúc in-flight work |

**Key đúng chưa đủ.** `Class<?>` phân biệt runtime class theo loader; tuy nhiên cùng một class có thể có schema khác nhau khi policy hoặc cấu hình thay đổi. Một `ClassValue` chỉ phân biệt theo class, nên dữ liệu phụ thuộc version cần thêm tầng quản lý version/invalidation. Ngược lại, cache bằng chuỗi `getName()` có thể ghép nhầm class từ hai loader.

**Value cũng phải được xét.** Nếu shared value chứa capability truy cập private hoặc trạng thái theo tenant, chỉ thêm phần tử vào key không tự tạo ra ranh giới quyền phù hợp. Nên giữ metadata chung ở scope đã kiểm chứng và áp dụng kiểm tra quyền theo request tại nơi sử dụng.

## 3. Ba lựa chọn thực tế và trách nhiệm dọn dẹp

### 3.1. Cache thuộc request, session hoặc plugin

Dùng khi dữ liệu chỉ lặp lại trong thời gian ngắn hoặc gắn với một plugin generation. Một `InspectionSession` có thể chứa `Map<Class<?>, Metadata>`, đóng bằng `AutoCloseable` và xóa entries trong `close()`; ví dụ chạy được ở mục 4.

Một plugin unload cần thứ tự rõ ràng: ngừng nhận việc mới → hoàn tất/hủy việc đang chạy → unregister listener/callback/task → xóa cache và reference do plugin sở hữu → đóng tài nguyên phù hợp. `clear()` chỉ cắt reference của chính map, không chứng minh JVM đã unload lớp. Với session có nhiều thread, `close()` còn phải phối hợp với in-flight operation thay vì cho phép lookup và shutdown tranh chấp.

### 3.2. `ClassValue<T>` cho metadata thật sự thuộc về từng Class

Nếu một descriptor chỉ là hàm của `Class<?>` và tái dùng thường xuyên, `ClassValue` tránh map global giữ key mạnh trực tiếp. `computeValue(type)` có thể chạy nhiều lần dưới contention, nên tạo metadata hoàn chỉnh, lý tưởng không có side effect. `remove(type)` chỉ invalid một class trong một `ClassValue`, không cung cấp TTL, `clearAll` hay việc đóng tài nguyên bên ngoài. Lần đọc đang giữ value cũ có thể tiếp tục dùng nó; nếu policy cần chuyển đổi đồng nhất, phải có synchronization/generation ở tầng sở hữu.

### 3.3. Cache bounded/TTL hoặc generation-aware

Chọn khi hệ thống phải cache theo nhiều khóa động như `(Class, policyVersion)`, cần giới hạn memory và kiểm soát eviction. Đặt rõ **maximum size/weight, idle/TTL, trigger invalidation và owner**; `ConcurrentHashMap` không cung cấp các khả năng này tự động.

Ví dụ, khi cấu hình serialization nâng từ generation `v12` lên `v13`, xây snapshot metadata mới, công bố generation mới rồi hủy entries `v12` sau khi lượt xử lý cũ hoàn thành. TTL là giới hạn thời gian dự phòng, không thay cho sự kiện invalidate do schema/security policy đổi. Theo dõi hit/miss, current entries, evictions và retained old loaders để phát hiện chính sách không hoạt động.

### Checklist thiết kế

Trước khi triển khai hãy xác định **owner**, **key/value dependencies**, **thời hạn hiệu lực**, **điểm invalidate**, **hành vi concurrent close/reload** và **cách xác minh**. Một cache thiếu bất kỳ mục nào trong các mục đó có thể nhanh ở trạng thái ổn định nhưng trả schema cũ hoặc giữ plugin lâu ngoài dự kiến.

## 4. Ví dụ Java 17+ hoàn chỉnh: global map, ClassValue và session

Ví dụ dưới đây dùng metadata đơn giản là tên field của lớp `Invoice`. Chương trình minh họa **so sánh hành vi cache**, không mô phỏng đầy đủ class unloading. Vì chạy tuần tự trên một class bình thường, các con số scan ổn định. Đừng sao chép `GLOBAL` làm giải pháp production không có chính sách giải phóng.

Lưu nội dung vào `ReflectionCacheLifetimeDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ReflectionCacheLifetimeDemo {
    static final class Invoice {
        private final String id = "INV-7";
        private final int amount = 500;
        private transient String debug = "temporary";
    }

    private static final AtomicInteger SCANS = new AtomicInteger();

    // Anti-pattern demo: never cleared, strongly retains Class keys.
    private static final ConcurrentMap<Class<?>, List<String>> GLOBAL =
            new ConcurrentHashMap<>();

    private static final ClassValue<List<String>> PER_CLASS = new ClassValue<>() {
        @Override
        protected List<String> computeValue(Class<?> type) {
            return scan(type);
        }
    };

    private static List<String> scan(Class<?> type) {
        SCANS.incrementAndGet();
        return Arrays.stream(type.getDeclaredFields())
                .filter(f -> !f.isSynthetic())
                .filter(f -> !Modifier.isStatic(f.getModifiers()))
                .filter(f -> !Modifier.isTransient(f.getModifiers()))
                .map(Field::getName)
                .sorted()
                .toList();
    }

    static final class InspectionSession implements AutoCloseable {
        private final Map<Class<?>, List<String>> cache = new HashMap<>();
        private boolean closed;

        List<String> fieldNames(Class<?> type) {
            if (closed) throw new IllegalStateException("session closed");
            return cache.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan);
        }

        int entries() {
            return cache.size();
        }

        @Override
        public void close() {
            if (!closed) {
                cache.clear();
                closed = true;
            }
        }
    }

    public static void main(String[] args) {
        Class<?> type = Invoice.class;
        System.out.println("global first: " +
                GLOBAL.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan) +
                ", scans=" + SCANS.get());
        System.out.println("global again: " +
                GLOBAL.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan) +
                ", scans=" + SCANS.get());

        System.out.println("ClassValue first: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());
        System.out.println("ClassValue again: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());
        PER_CLASS.remove(type);
        System.out.println("ClassValue after remove: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());

        try (InspectionSession session = new InspectionSession()) {
            System.out.println("session first: " + session.fieldNames(type) +
                    ", scans=" + SCANS.get());
            System.out.println("session again: " + session.fieldNames(type) +
                    ", entries=" + session.entries() +
                    ", scans=" + SCANS.get());
        }
        System.out.println("session closed: references cleared");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 ReflectionCacheLifetimeDemo.java
java ReflectionCacheLifetimeDemo
~~~

Output chính xác (chương trình một luồng):

~~~text
global first: [amount, id], scans=1
global again: [amount, id], scans=1
ClassValue first: [amount, id], scans=2
ClassValue again: [amount, id], scans=2
ClassValue after remove: [amount, id], scans=3
session first: [amount, id], scans=4
session again: [amount, id], entries=1, scans=4
session closed: references cleared
~~~

**Ý nghĩa:**

1. `GLOBAL` chỉ scan một lần, nhưng entry `Class<?>` sẽ tồn tại trong `static` map cho tới lúc xóa hoặc cache được GC. Map này không có `remove/clear`.
2. `PER_CLASS` cũng reuse metadata; gọi `remove(Invoice.class)` khiến lần `get` kế tiếp scan lại. Với nhiều thread, số lần `computeValue` không bắt buộc giống demo.
3. `InspectionSession` tái sử dụng kết quả trong phiên; `close()` xóa map. Dòng `"references cleared"` chỉ xác nhận cleanup do ứng dụng thực hiện, **không chứng minh ClassLoader đã được unload**.
4. `scan` chỉ lấy metadata, không đọc state của instance `Invoice`. Việc bỏ field `transient` là **chính sách riêng của demo**, không phải quy tắc bắt buộc khi dùng Reflection.
5. `getDeclaredFields()` không bảo đảm thứ tự; ví dụ `sorted()` để output ổn định.
6. `InspectionSession` minh họa **cách dùng tuần tự**. `HashMap`/`closed` không thread-safe; session chia sẻ đa luồng cần đồng bộ và quy tắc dừng tác vụ trước khi `close()`.

## 5. Tại sao key đúng vẫn có thể cho value sai?

`Class<?>` là key hợp lý cho metadata **cấu trúc của class**, nhưng nhiều giá trị derived metadata còn phụ thuộc vào policy. Cùng một class có thể có projection khác nhau khi:

- Audit nội bộ cần trường kỹ thuật, API công khai thì loại trường nhạy cảm.
- Tenant A và tenant B được nhìn các field khác nhau.
- Cấu hình serialization, naming strategy, locale hoặc version schema thay đổi.
- Module layer/access context khác nhau, hoặc plugin được hot reload.
- Mapping giữa field với business property thay đổi dù `Class<?>` không đổi.

Không được cache quyết định `allowed=true` cho user A trong `Map<Class<?>, Boolean>` toàn JVM rồi tái dùng cho user B. Nên cache phần **metadata có thể chia sẻ** và tính authorization/redaction theo request; hoặc đưa policy identity/version vào key và đặt cache trong owner có vòng đời cụ thể.

Không nên cache `Field.get(obj)` như thể metadata: đó là **giá trị runtime của một instance**, có thể đổi theo thời gian, có tác dụng bảo mật và không tự tạo snapshot nhất quán trên nhiều field.

## 6. Eviction, unload và concurrency là ba chủ đề riêng

### 6.1. Eviction không đồng nghĩa class unloading ngay

Khi xóa entry, map thôi giữ tham chiếu **của riêng nó**. Đối tượng đang chạy, stack frame, thread-local, executor, listener, callbacks, công cụ monitoring hoặc cache khác vẫn có thể giữ ClassLoader. Ngay cả khi không còn đường tham chiếu mạnh, JVM có thể trì hoãn GC/class unloading.

Không kiểm thử leak bằng cách gọi `System.gc()` một lần rồi kết luận chắc chắn. Hãy phân tích heap dump, GC roots và retained heap sau nhiều chu kỳ chạy/phục hồi phù hợp.

### 6.2. Compute không bảo đảm exactly once

Javadoc `ClassValue.get` cho phép nhiều thread cùng tính `computeValue` và cài đặt một kết quả; do đó compute phải có tính lặp lại an toàn, lý tưởng là thuần hàm trên metadata và policy bất biến. `remove(type)` cạnh tranh với `get(type)` có các quy tắc state riêng.

`ConcurrentHashMap.computeIfAbsent` điều phối atomic mapping của map; không nên ngoại suy ngữ nghĩa exactly-once của map sang `ClassValue`. Khi phân tích benchmark nhiều luồng, đừng assert đúng một lần compute nếu API cho phép cạnh tranh.

### 6.3. Close cần phối hợp với in-flight work

`close()` trên cache scoped không tự đợi các request đang giữ reference hoàn tất. Nếu nhiều worker đang sử dụng plugin, chủ sở hữu nên ngừng nhận công việc mới, đợi/cancel công việc đang xử lý theo policy, rồi giải phóng cache và ClassLoader. Tránh đồng thời dỡ loader trong khi một operation vẫn truy cập metadata của plugin.

## 7. Quy trình thiết kế cache Reflection có thể kiểm chứng

1. **Đo nhu cầu:** đo tỷ lệ scan lặp lại, thời gian Reflection, tổng latency, khối lượng class và heap/metaspace trước khi cache.
2. **Phân loại dữ liệu:** chỉ cache metadata dùng lại hợp lệ; phân biệt derived schema, dữ liệu theo user và giá trị object.
3. **Chọn owner:** request/session, plugin, application component hay JVM. Tránh owner lâu hơn dữ liệu mà không có lý do và cleanup.
4. **Chọn key:** `Class<?>` cho class identity, bổ sung policy/config generation khi cần; không dùng tên class đơn độc xuyên loader.
5. **Chọn implementation:** cache scoped, `ClassValue`, bounded/TTL; xem value có tham chiếu ngược tới class/loader không.
6. **Định nghĩa expiration/invalidation:** clear ở `close`, remove khi đổi policy, unload plugin, hoặc bounded eviction; xác định hành vi khi concurrent load.
7. **Đo/kiểm thử:** hit/miss, entry count (nếu có), retained class loaders, memory usage, thời gian reload và hành vi sau shutdown. Chạy lặp nhiều vòng plugin unload/reload, không chỉ một lần.

Các dấu hiệu cần điều tra gồm: class loader thế hệ cũ không mất khỏi GC roots sau khi plugin dừng, số entry tăng theo mỗi lần reload, retained heap/metaspace tăng liên tục, hoặc cache chứa field/Method của loader đã không còn phục vụ request nào.

## 8. Ví dụ lựa chọn theo tình huống

| Tình huống | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Quét vài loại DTO trong một request | Cache trong request/session | Dọn ngay sau request hoặc khi close. |
| Metadata bất biến theo `Class` dùng trên nhiều request | `ClassValue` | Không trộn auth/config per-user; `computeValue` có thể chạy nhiều lần. |
| Plugin hot deploy, runtime cần reload | Cache sở hữu bởi plugin hoặc per-class association | Gỡ registry, listener, worker và mọi reference khác tới loader cũ. |
| Schema phụ thuộc phiên bản cấu hình | Bounded cache key chứa version hoặc cache generation scoped | Invalidate khi version thay đổi. |
| Shared cache có nguy cơ gặp hàng trăm nghìn kiểu | Cache bounded có memory budget/TTL hoặc bỏ cache | `ConcurrentHashMap` nguyên bản không có max size. |
| Dữ liệu nhạy cảm theo tenant | Không giữ trong metadata cache toàn JVM | Redaction/permission theo request. |

## 9. Các lỗi vòng đời nên phát hiện trong review

| Dấu hiệu | Phân tích | Hành động |
| --- | --- | --- |
| Cache global tăng entries qua mỗi plugin reload | Có thể giữ metadata thế hệ cũ | Owner cho từng plugin/generation; evict khi unload |
| Policy đã cập nhật nhưng metadata vẫn cũ | Key thiếu policy version hoặc không invalidate | Versioned key/snapshot và quy trình chuyển đổi rõ |
| `close()` chạy trong khi request còn dùng metadata | Reference cũ vẫn còn trong in-flight work | Chặn việc mới, chờ/hủy việc cũ rồi dọn owner |
| Bounded cache hết hạn nhưng dữ liệu bảo mật vẫn sai | TTL không bảo đảm invalidation ngay khi quyền đổi | Quyết định quyền theo request hoặc invalidate ngay |
| Chọn `ClassValue` nhưng cần `clearAll()`/TTL | API không cung cấp thao tác đó | Chọn owner/cache policy khác hoặc quản lý instance/generation |
| `ConcurrentHashMap` được coi là có giới hạn dung lượng | Thread-safe không đồng nghĩa bounded | Đặt eviction/memory budget riêng |
| Chỉ đo GC một lần để kết luận hết leak | GC/class unloading không được đảm bảo đúng lúc | Theo dõi GC roots, retained loaders qua nhiều chu kỳ |

Không kiểm tra an toàn cache chỉ bằng tỷ lệ hit. Cần đồng thời kiểm thử việc đổi schema/tenant policy, plugin reload, lỗi trong compute, đồng thời khi close và các tham chiếu còn sống sau khi dọn.

## 10. Bài tập tự kiểm tra

1. Thêm class `Receipt` trong chương trình và gọi `GLOBAL.computeIfAbsent(Receipt.class, ...)`. Kích thước global map thay đổi ra sao? Nó tự xóa entry khi hết dùng class không?
2. Bỏ dòng `PER_CLASS.remove(type)` và dự đoán `SCANS`. Khi thêm nhiều thread, điều gì khiến kết quả đếm compute khác đi?
3. Gọi `InspectionSession.fieldNames` sau `close()`: tại sao chương trình chủ động từ chối?
4. Thiết kế trường hợp hai loader A/B nạp class cùng binary name. Vì sao key `getName()` sai, còn `Class<?>` đủ để phân biệt?
5. Vẽ reference graph của `WeakHashMap<Class<?>, List<Field>>` và giải thích vì sao key có thể chưa được thu gom.
6. Một công cụ export schema có policy theo tenant và tự động reload plugin: chọn loại cache nào cho metadata thô, loại nào cho view theo user, và các điểm invalidation cụ thể.
7. Đề xuất bài stress test tải/dỡ plugin 100 vòng. Theo dõi loader cũ bằng heap/GC roots và cache entries; nếu số retained loader tăng, cần kiểm tra những owner nào ngoài cache?

**Tự đánh giá:** Khi một cache dùng `Class<?>`/`Method`/`Field` làm key hay value, bạn có xác định được **đơn vị sở hữu, hạn tồn tại, nơi invalidation, key có thể trỏ tới loader nào và liệu dữ liệu bị sai khi policy đổi** không? Nếu chưa, cache toàn JVM không giới hạn là một thiết kế chưa hoàn chỉnh.

## 11. Tài liệu chính thức

- [Java SE 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html) — `get`, `computeValue`, `remove` và cạnh tranh.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getDeclaredFields`, `getClassLoader` và class identity.
- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html) — declaring class, metadata.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) — atomic map operations, `computeIfAbsent`.
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) — weak keys, strong values và vòng tham chiếu.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — định nghĩa class qua loader.