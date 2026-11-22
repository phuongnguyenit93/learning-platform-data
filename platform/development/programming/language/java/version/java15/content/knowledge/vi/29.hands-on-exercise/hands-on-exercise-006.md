# Đo ảnh hưởng của cache tới vòng đời lớp sinh động trong Java

## 1. Bài toán thực hành và kết quả cần quan sát

Một framework có thể tạo lớp Java **tại thời điểm chạy** để làm proxy, ánh xạ dữ liệu, phát sinh mã bytecode hoặc triển khai một interface. Việc tạo lớp chỉ là nửa đầu của câu chuyện: nếu cache của ứng dụng tiếp tục giữ `Class<?>`, đối tượng proxy hoặc `ClassLoader` bằng **strong reference**, các lớp đó có thể tiếp tục tồn tại dù nghiệp vụ đã xử lý xong. Với ứng dụng tạo nhiều loader và lớp theo phiên bản/plugin/tenant, việc giữ tham chiếu sai có thể khiến metadata lớp trong JVM (ví dụ **Metaspace** trên HotSpot) tăng theo thời gian.

Bài này hướng dẫn **đo tác động của chiến lược cache** lên khả năng giải phóng lớp được tạo động. Chúng ta dùng `java.lang.reflect.Proxy.newProxyInstance(...)`, một API được hỗ trợ trong Java hiện đại, để sinh một lớp proxy thuộc một `ClassLoader` riêng cho từng mẫu thử. Sau đó so sánh ba trường hợp:

1. **Weak value:** cache giữ `WeakReference<Class<?>>`, không cố giữ lớp/loader sống.
2. **Strong value:** cache tĩnh giữ `Class<?>` trực tiếp, khiến loader liên quan vẫn reachable.
3. **Weak key nhưng strong value:** `WeakHashMap<ClassLoader, Class<?>>`; tuy key là weak, value lại tham chiếu tới chính loader qua `Class<?>`, vì vậy cache vẫn có thể giữ loader sống.

Mục tiêu là quan sát sự khác nhau giữa **còn tham chiếu mạnh**, **được phép thu gom bởi GC** và **đã có bằng chứng class unloading**, không chỉ so một con số bộ nhớ.

**Giới hạn quan trọng:** GC không có deadline bảo đảm. `System.gc()` chỉ đề nghị JVM thu gom; việc không thấy lớp bị unload trong một lượt chạy không tự chứng minh memory leak. Cần kết hợp phân tích đồ thị tham chiếu, nhiều lần quan sát, log class unloading và test trên đúng JDK/GC được sử dụng.

## 2. Phân biệt đối tượng, lớp và ClassLoader

| Đối tượng/khái niệm | Vai trò trong vòng đời | Điều đáng đo |
| --- | --- | --- |
| `Object` proxy | Instance của lớp được tạo động | Nếu instance còn reachable, lớp của nó cũng phải còn dùng được. |
| `Class<?>` | Đại diện runtime cho định nghĩa lớp | Có liên kết đến defining `ClassLoader`; giữ `Class<?>` có thể giữ loader sống. |
| `ClassLoader` | Định nghĩa/khởi tạo tập lớp thông thường | Với lớp thông thường, unload thường gắn với khả năng thu hồi loader định nghĩa. |
| Cache (`Map`, registry, singleton) | Giữ tham chiếu đến class, loader, instance, `Method`, `Constructor`, `MethodHandle`... | Một entry có thể kéo dài vòng đời của toàn bộ loader và các lớp nó định nghĩa. |
| GC root | Điểm bắt đầu của đồ thị tham chiếu mạnh: static, stack, thread, JNI... | Nếu vẫn có đường tham chiếu mạnh từ root tới loader thì không thể thu hồi loader đó. |
| Metaspace (HotSpot) | Khu vực metadata của lớp ngoài Java heap | Có thể tăng khi nhiều lớp/loader tồn tại; không phải một phép đo 1:1 với số lớp. |

Sơ đồ tham chiếu trong ví dụ strong cache:

```text
GC root
  |
  v
DynamicClassCacheLab.STRONG_CACHE (static Map)
  |
  v
Class<?> của proxy do Java sinh
  |
  v
ClassLoader riêng (defining loader)
  |
  v
Các lớp/metadata gắn với loader
```

Chỉ đặt biến local `loader = null` **không làm mất** đường tham chiếu qua cache. Ngược lại, khi cache không giữ strong reference và không còn thread, instance, handle hoặc registry khác giữ loader, GC **có thể** thu hồi loader và unload các lớp thông thường do nó định nghĩa.

### Lớp tạo động không phải lúc nào cũng là cùng một loại lớp

- **Lớp proxy thông thường** do `Proxy.newProxyInstance(...)` sinh ra được định nghĩa bởi loader cung cấp cho API. Đây là đối tượng chúng ta đo.
- **Lớp bình thường** do bytecode generator định nghĩa qua `ClassLoader.defineClass(...)` cũng cần được phân tích theo loader và các tham chiếu tới lớp.
- **Hidden class** tạo bởi `MethodHandles.Lookup.defineHiddenClass(...)` có quy tắc đặc biệt: mặc định hidden class có thể được unload ngay cả khi defining loader vẫn reachable; khi dùng `Lookup.ClassOption.STRONG`, vòng đời của hidden class gắn chặt với loader hơn. Không được lấy kết quả thí nghiệm proxy thông thường rồi khẳng định giống hệt cho mọi hidden class. Cơ chế hidden class là API hiện hành, được đưa vào JDK 15, không phải một mẹo nội bộ nên bị loại bỏ.

## 3. Hai khái niệm về “cache yếu” cần tách rõ

`WeakReference<T>` chỉ giữ **tham chiếu yếu** tới đối tượng `T`; nếu không còn đường tham chiếu mạnh khác, GC có thể xóa tham chiếu yếu. Khi đó `ref.get()` trả `null`; `ReferenceQueue` có thể nhận thông báo về reference được thu hồi. Một weak cache cần chấp nhận **cache miss** và tạo lại giá trị.

`WeakHashMap<K,V>` giữ **key yếu** nhưng **value mạnh**. Đây là điểm dễ gây lỗi:

```java
Map<ClassLoader, Class<?>> cache = new WeakHashMap<>();
cache.put(loader, generatedClass);
```

Đoạn trên là minh họa, chưa phải chương trình hoàn chỉnh. Vì `generatedClass.getClassLoader()` trả về `loader`, value giữ đường tham chiếu mạnh ngược tới key. `WeakHashMap` không tự phá vòng tham chiếu đó; JavaDoc chính thức đã cảnh báo value có thể trực tiếp hoặc gián tiếp tham chiếu tới key và ngăn key bị thu hồi.

Có thể hình dung:

```text
GC root -> WeakHashMap -> value (Class<?>) -> ClassLoader (key)
                         \_________________________|
```

Weak key chỉ có ích nếu **không có đường tham chiếu mạnh khác** đi đến key. Khi xây cache metadata cho plugin/runtime class, phải kiểm tra cả **key lẫn value**, và cả reference chain đi qua class, loader, method, instance hoặc thread context classloader.

## 4. Hợp đồng thí nghiệm: giữ mọi điều kiện khác giống nhau

Ta tạo **24 loader riêng**, mỗi loader tạo **một lớp proxy** triển khai `Runnable` (interface chuẩn, dễ nhìn). Tất cả đều sinh bằng `Proxy.newProxyInstance`; chỉ khác cách lưu cache.

| Hạng mục | Cấu hình |
| --- | --- |
| Số mẫu mỗi mode | `24` loader và các lớp proxy tương ứng. |
| Interface proxy | `Runnable.class`, được Java chuẩn cung cấp. |
| Loader | Một `ClassLoader` mới có parent là `ClassLoader.getPlatformClassLoader()` cho mỗi mẫu. |
| Phạm vi cache | Ba static map độc lập trong chương trình. |
| Bằng chứng reachability | `WeakReference<ClassLoader>` cho từng loader; **chỉ** reference yếu được giữ làm probe. |
| Quan sát trước clear | Gọi `System.gc()` vài lượt, đếm probe có `get() == null`. |
| Quan sát sau clear | Xóa strong/weak/trap cache, lặp lại quan sát để thấy thay đổi khi bỏ root. |
| Bằng chứng class unloading | Chạy thêm với `-Xlog:class+unload=info` trên HotSpot; đối chiếu thời điểm và tên proxy. |

Tất cả các probe `WeakReference<ClassLoader>` được giữ trong `List` để tránh bản thân probe bị GC trước khi quan sát. Chúng **không** giữ loader sống.

Từ một lần chạy có thể tính:

\[
\text{Tỷ lệ loader đã được GC quan sát}=\frac{\text{số WeakReference đã bị xóa}}{\text{số loader tạo ra}}\times100\%.
\]

Đây là phép đo **loader reachability**. Để xác nhận việc **unload lớp**, cần thêm log JVM hoặc bộ đếm class unloading; không nên đổi tên chỉ số này thành “số lớp unload” khi chưa có bằng chứng.

## 5. Mã Java 17+ hoàn chỉnh: ba chiến lược cache

Lưu toàn bộ đoạn sau vào một file tên **`DynamicClassCacheLab.java`**. Đoạn mã chỉ dùng Java SE, không cần framework hoặc thư viện ngoài, không dùng API `Proxy.getProxyClass(...)` đã bị deprecated.

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;

public final class DynamicClassCacheLab {
    enum Mode {
        WEAK_VALUE,
        STRONG_VALUE,
        WEAK_KEY_STRONG_VALUE
    }

    private static final Map<Integer, Class<?>> STRONG_CACHE =
            new HashMap<>();

    private static final Map<Integer, WeakReference<Class<?>>> WEAK_CACHE =
            new HashMap<>();

    private static final Map<ClassLoader, Class<?>> WEAK_KEY_TRAP =
            new WeakHashMap<>();

    private static WeakReference<ClassLoader> makeProxyAndCache(
            int id,
            Mode mode,
            ReferenceQueue<ClassLoader> queue) {

        ClassLoader loader =
                new ClassLoader(ClassLoader.getPlatformClassLoader()) {};

        Object proxy = Proxy.newProxyInstance(
                loader,
                new Class<?>[] { Runnable.class },
                (instance, method, arguments) -> null);

        Class<?> generatedClass = proxy.getClass();

        if (generatedClass.getClassLoader() != loader) {
            throw new AssertionError("Proxy used unexpected ClassLoader");
        }

        switch (mode) {
            case STRONG_VALUE ->
                    STRONG_CACHE.put(id, generatedClass);

            case WEAK_VALUE ->
                    WEAK_CACHE.put(id, new WeakReference<>(generatedClass));

            case WEAK_KEY_STRONG_VALUE ->
                    WEAK_KEY_TRAP.put(loader, generatedClass);
        }

        return new WeakReference<>(loader, queue);
    }

    private static void requestCollection() throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            System.gc();
            Thread.sleep(50);
        }
    }

    private static int clearedCount(
            List<WeakReference<ClassLoader>> probes) {

        int count = 0;
        for (WeakReference<ClassLoader> reference : probes) {
            if (reference.get() == null) {
                count++;
            }
        }
        return count;
    }

    private static void run(Mode mode) throws InterruptedException {
        final int total = 24;
        ReferenceQueue<ClassLoader> queue = new ReferenceQueue<>();
        List<WeakReference<ClassLoader>> probes = new ArrayList<>();

        for (int id = 0; id < total; id++) {
            probes.add(makeProxyAndCache(id, mode, queue));
        }

        requestCollection();
        int beforeClear = clearedCount(probes);

        STRONG_CACHE.clear();
        WEAK_CACHE.clear();
        WEAK_KEY_TRAP.clear();

        requestCollection();
        int afterClear = clearedCount(probes);

        int enqueued = 0;
        while (queue.poll() != null) {
            enqueued++;
        }

        System.out.printf(
                "%s: beforeClear=%d/%d, afterClear=%d/%d, enqueued=%d%n",
                mode, beforeClear, total, afterClear, total, enqueued);
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length == 0) {
            for (Mode mode : Mode.values()) {
                run(mode);
            }
        } else if (args.length == 1) {
            run(Mode.valueOf(args[0]));
        } else {
            throw new IllegalArgumentException(
                    "Usage: java DynamicClassCacheLab [MODE]");
        }
    }
}
```

### Vì sao code được cấu trúc như vậy?

1. `makeProxyAndCache` là **method riêng**. Khi nó trả về, biến local `loader`, `proxy`, `generatedClass` ra khỏi phạm vi thực thi; người đo không vô tình giữ loader bởi biến local trong vòng GC.
2. Mỗi lần tạo **loader mới**, tránh trường hợp cache trong Java trả lại proxy class cho cùng tập interface và cùng loader. Ta muốn đo **24 nhóm lớp/loader**, không đo 24 instance của cùng một lớp.
3. `Proxy.newProxyInstance` định nghĩa lớp proxy trong `loader` được truyền vào. Điều kiện `generatedClass.getClassLoader() == loader` xác nhận giả định căn bản của bài.
4. `Runnable.class` được cung cấp từ Java chuẩn, nên custom loader có thể dùng interface qua cơ chế parent delegation. Lambda invocation handler chỉ phục vụ tạo proxy; bài không gọi `run()` nên handler không tạo side effect.
5. Static map tồn tại xuyên suốt lượt đo. Trước `clear`, chế độ **strong** và **weak-key trap** còn có root tới class/loader; weak-value không cố duy trì root đó.
6. `ReferenceQueue` chỉ là chứng cứ bổ trợ. Không bắt buộc số enqueued tại một thời điểm bằng số reference đã có `get() == null`, vì việc xếp queue và thời điểm quan sát có thể không đồng bộ hoàn toàn.
7. `clear()` diễn ra **sau phép đo thứ nhất**. Phép đo thứ hai cho thấy khi bỏ strong reference, JVM có cơ hội thu hồi các loader từng bị cache giữ.
8. `System.gc()` + `Thread.sleep(50)` chỉ tạo **cơ hội quan sát có giới hạn trong lab**; không sử dụng cách thúc GC này như chính sách quản lý bộ nhớ production.

Các map chỉ được truy cập từ luồng main trong bài. `HashMap` và `WeakHashMap` không có bảo đảm thread safety; nếu đưa cache vào ứng dụng đa luồng cần có chiến lược đồng bộ/cache concurrent phù hợp.

## 6. Biên dịch, chạy và giải thích stdout

Biên dịch bằng JDK hỗ trợ `--release 17` (ví dụ JDK 17, 21, 24):

```bash
javac --release 17 -encoding UTF-8 DynamicClassCacheLab.java
```

Chạy đủ ba trường hợp trên cùng JVM:

```bash
java DynamicClassCacheLab
```

Hoặc kiểm tra một mode trong **JVM riêng** để tránh ảnh hưởng của các lượt thử khác:

```bash
java DynamicClassCacheLab WEAK_VALUE
java DynamicClassCacheLab STRONG_VALUE
java DynamicClassCacheLab WEAK_KEY_STRONG_VALUE
```

Một lượt thử trên **OpenJDK 24.0.2** với logic thí nghiệm tương ứng đã quan sát được:

```text
WEAK_VALUE: beforeClear=24/24, afterClear=24/24, enqueued=24
STRONG_VALUE: beforeClear=0/24, afterClear=24/24, enqueued=24
WEAK_KEY_STRONG_VALUE: beforeClear=0/24, afterClear=24/24, enqueued=24
```

Đây là **số liệu minh họa của một lần chạy**, không phải stdout bắt buộc. Những con số có thể khác trên JDK/GC/OS khác, hoặc khi JVM không thực hiện GC tại thời điểm thí nghiệm.

Ý nghĩa của từng mode:

| Mode | Trước khi clear cache | Sau khi clear cache |
| --- | --- | --- |
| `WEAK_VALUE` | Có thể thấy nhiều loader được GC vì cache không giữ class mạnh. | Thường không còn khác biệt lớn nếu các loader đã được GC. |
| `STRONG_VALUE` | Những `Class<?>` giữ trong static map có đường mạnh tới defining loader, vì vậy loader của các entry còn tồn tại. | Khi bỏ entry, GC có thể thu hồi loader nếu không còn root khác. |
| `WEAK_KEY_STRONG_VALUE` | Weak key **không cứu được** cache vì strong `Class<?>` value tham chiếu ngược về loader key. | `clear()` cắt đường tham chiếu; các loader có thể được GC ở những lượt thu gom sau. |

**Cách đọc đúng:** `beforeClear=0/24` ở strong cache cho biết tất cả 24 loader **còn reachable** trong phép thử. `afterClear=24/24` cho biết 24 weak references đến loader đã được xóa; muốn kết luận JVM đã unload lớp proxy tương ứng, cần thêm bằng chứng lớp thực sự bị unload.

Nếu chạy nhiều lần và mode weak chưa thu hồi đủ 24 loader, hãy ghi lại `clearedCount` cùng JDK/GC và điều kiện chạy; không tự đánh dấu code sai chỉ vì `System.gc()` chưa kích hoạt một chu kỳ phù hợp.

## 7. Xác nhận class unloading bằng log JVM

Trên **HotSpot** (bao gồm các bản OpenJDK HotSpot thông dụng), tùy chọn unified logging `-Xlog:class+unload=info` ghi sự kiện unload lớp. Chạy lệnh sau để quan sát riêng mỗi kịch bản:

```bash
java -Xlog:class+unload=info DynamicClassCacheLab WEAK_VALUE
java -Xlog:class+unload=info DynamicClassCacheLab STRONG_VALUE
java -Xlog:class+unload=info DynamicClassCacheLab WEAK_KEY_STRONG_VALUE
```

Khi lớp proxy được unload, log có thể có dạng:

```text
[0.000s][info][class,unload] unloading class jdk.proxy...$Proxy... ...
```

Đây là **dạng minh họa**, không phải một dòng stdout chính xác; timestamp, tên package/module và kiểu log có thể thay đổi theo JDK. Không dựa vào tên lớp proxy nội bộ cố định trong assert.

Cách phân tích:
- Ở `WEAK_VALUE`, sự kiện unload có thể xảy ra **trước** lúc cache bị clear.
- Ở `STRONG_VALUE` và `WEAK_KEY_STRONG_VALUE`, các proxy class còn được static map giữ sẽ chưa đủ điều kiện unload trước `clear`; sau khi xóa cache, JVM có thể unload chúng.
- Nếu không thấy dòng unload trong thời gian chạy ngắn, chưa đủ cơ sở kết luận bị leak: GC có thể không thực hiện class unloading trong cửa sổ quan sát; kiểm tra collector, flags và kéo dài thời gian đo một cách có kiểm soát.

Có thể kiểm tra JVM có hỗ trợ tag cấu hình đó bằng:

```bash
java -Xlog:help
```

`-Xlog:class+unload=info` là tùy chọn của **JVM HotSpot**, không phải bảo đảm của đặc tả Java SE cho mọi máy ảo. Nếu dùng JVM khác, đọc hướng dẫn class-loading/unloading logging của chính JVM đó.

### Thêm bộ đếm của Java Management API

Nếu cần một chỉ số tổng quát, `ClassLoadingMXBean` cung cấp số lớp đã unload từ khi JVM khởi động:

```java
var classLoading = java.lang.management.ManagementFactory
        .getClassLoadingMXBean();
long before = classLoading.getUnloadedClassCount();

// Chạy một giai đoạn đo có kiểm soát, rồi lấy lại bộ đếm.

long after = classLoading.getUnloadedClassCount();
System.out.println("Unloaded classes delta: " + (after - before));
```

Đây là **trích đoạn để tích hợp vào chương trình đo**, chưa phải một file độc lập; cần đặt lời gọi trước/sau đúng giai đoạn thử. Bộ đếm là **toàn JVM**, có thể gồm lớp khác bị unload, không chỉ 24 lớp proxy. Vì vậy không mặc định `delta == 24`; muốn quy nguyên nhân hãy đối chiếu thêm class-unload log, `ClassLoader` identity và môi trường test cô lập.

## 8. Đo bộ nhớ đúng ngữ cảnh: heap khác Metaspace

Với HotSpot, các đối tượng `Class<?>`, map và loader có mối liên hệ với heap, còn metadata lớp dùng Metaspace/Compressed Class Space tùy cấu hình. Giữ nhiều loader có thể giữ metadata, nhưng:

- **Used Metaspace** không giảm ngay lập tức sau mỗi lần bỏ một tham chiếu.
- **Committed Metaspace** có thể giảm muộn hơn used, tùy bộ cấp phát và GC. Bộ nhớ chưa trả về OS không tự chứng minh lớp vẫn sống.
- **Heap usage** có thể giảm dù metadata lớp vẫn được giữ, hoặc ngược lại.
- **Số lớp unloaded** là dữ liệu tổng của JVM; không trực tiếp quy ra MB tiết kiệm nếu không có phép đo trước/sau và tải ổn định.

Trong test hiện đại, nên theo dõi **đồng thời**:
1. Số loader probe đã clear (`WeakReference<ClassLoader>`).
2. Sự kiện class unloading từ `-Xlog:class+unload=info`.
3. `ClassLoadingMXBean.getLoadedClassCount()` và `getUnloadedClassCount()` trước/sau.
4. Metaspace và heap trong công cụ profiler/JFR/metrics phù hợp với runtime.
5. Kích thước cache, số key/value còn sống, tốc độ tạo loader và số lớp mới mỗi đơn vị thời gian.

Nếu dùng `jcmd`, hãy xác minh các diagnostic command thực sự có trên JVM đó (`jcmd <pid> help`) và chỉ dùng chúng trong môi trường được phép. Một số lệnh/chế độ profiling có chi phí cao hoặc tác động tới GC, vì vậy cần ghi rõ điều kiện đo.

Đừng bật tùy tiện cờ GC hay Metaspace cổ chỉ để “giống bài cũ”: hãy dùng unified logging và management/profiling API còn được hỗ trợ trên JDK đang chạy.

## 9. Thiết kế phép thử công bằng và có thể tái lập

Để một kết luận “cache gây giữ lớp” đáng tin, cần kiểm soát những biến dễ làm kết quả sai:

**Số lớp và loader.** Nếu tái dùng một `ClassLoader` cho 24 lần `Proxy.newProxyInstance` với cùng interface, API có thể tái sử dụng cùng proxy class. Khi đó không còn là phép thử 24 lớp/loader độc lập.

**GC và thời gian quan sát.** `System.gc()` là lời đề nghị; `-XX:+DisableExplicitGC` hoặc bộ thu gom khác có thể khiến kết quả khác. Chạy nhiều lượt trong JVM riêng, ghi thời gian và tổng hợp phân bố kết quả. Không đặt assertion kiểu “GC bắt buộc thu hồi đủ N trong 100 ms” làm test ổn định của CI.

**Vòng đời method local.** Nếu vẫn có `Class<?>`, `Object proxy` hoặc `ClassLoader` trong stack của method đang chạy GC, đối tượng có thể còn reachable. Chuyển phần tạo đối tượng sang method riêng, rồi đo sau khi method đó trả về như ví dụ. JIT tối ưu hóa liveness có thể thay đổi thời điểm thật sự có root.

**Thread context classloader.** Framework có thể đặt loader bằng `Thread.currentThread().setContextClassLoader(...)`. Nếu không phục hồi loader trước khi thread về pool, loader của plugin có thể bị pin dù cache chính đã xóa. Đối với hệ thống có context loader, cần lưu và phục hồi giá trị cũ theo đúng hợp đồng luồng.

**Đăng ký chưa gỡ.** Listeners, schedulers, `ThreadLocal`, MBeans, executors, logger registries, callback và registry toàn cục có thể giữ class/loader/instance. Phép thử một map đơn giản chỉ cô lập một cơ chế giữ tham chiếu, không bao phủ mọi đường leak trong production.

**Thư viện, JVM và công cụ.** Các implementation của proxy, hệ điều hành, class unloading policy và GC có thể khác giữa JDK/vendor. Khi so sánh, giữ cùng version/artifact, tham số heap/GC, số mẫu, tải và điều kiện môi trường; đổi một biến một lần.

**Đo sau clear.** Xóa cache chỉ làm đối tượng **có thể thu hồi**, không gọi unload đồng bộ. `WeakReference` không làm cho tài nguyên bên ngoài (file descriptor, thread, socket) tự đóng; tài nguyên phải có lifecycle riêng.

## 10. Khi nào nên dùng strong cache, weak cache hoặc cache theo vòng đời?

Cache mạnh **không tự động là lỗi**. Nếu các lớp được dùng suốt tuổi thọ ứng dụng và tập key hữu hạn, giữ mạnh có thể giảm chi phí sinh lớp và reflection. Rủi ro xuất hiện khi số key/loader tăng không giới hạn hoặc cache sống lâu hơn plugin, tenant, reload cycle hay module mà nó phục vụ.

| Nhu cầu | Cách thiết kế hợp lý | Điều cần kiểm chứng |
| --- | --- | --- |
| Class metadata gắn với một vòng đời application cố định | Strong cache có giới hạn key, chính sách eviction/cleanup khi cần | Tập lớp bounded, không có loader mới tăng mãi. |
| Cache theo plugin/hot reload | Cache theo scope plugin; xóa toàn bộ khi unload plugin; gỡ thread/listener/registry | Loader cũ trở thành unreachable sau teardown. |
| Giá trị có thể tái tạo, không cần giữ lâu | Weak values hoặc cơ chế cache cho phép reclaim, xử lý cache miss | Correctness khi value biến mất và concurrency khi tạo lại. |
| Cache gắn trực tiếp với `Class<?>` | Cân nhắc `ClassValue<T>` khi phù hợp cho metadata theo class | Không giữ class/loader bởi registry tĩnh khác và không tạo chu kỳ ngoài ý muốn. |
| Weak keys | Chỉ dùng nếu values **không** giữ key trực tiếp/gián tiếp | Kiểm tra tham chiếu ngược key qua value, method, class và loader. |
| Cache đa luồng | Bộ nhớ đệm concurrent có eviction, upper bound, lifecycle rõ | Race khi tạo lớp và dọn cache; không giữ class ngoài scope. |

**WeakReference không phải “giải pháp chống leak” cho mọi cấu trúc.** Nếu nơi khác vẫn giữ `Class<?>` mạnh thì tham chiếu yếu không thay đổi điều gì. Ngược lại, nếu chỉ dùng weak values, giá trị có thể bị GC ngay sau khi tạo, khiến tỉ lệ cache miss cao và tăng chi phí tạo lớp. Cần cân bằng tuổi thọ cache với hiệu năng và yêu cầu nghiệp vụ.

### Một quy trình sửa lỗi rò rỉ ClassLoader thực tế

1. Xác định loader nào tăng theo mỗi lần reload/plugin activation, và thời điểm đáng lẽ được giải phóng.
2. Chụp heap dump hoặc reference graph phù hợp, tìm **GC root path** đến loader cũ.
3. Kiểm tra map tĩnh, `Class<?>`, reflection handle, thread/context loader, registry và executor liên quan.
4. Thiết lập lifecycle dọn dẹp hoặc sửa cache key/value theo đúng yêu cầu. Không chỉ thêm `System.gc()`.
5. Dùng load/unload log, loader weak probes, class counts và memory profile để so sánh trước/sau fix.
6. Thử lại qua nhiều chu kỳ plugin reload với tải đại diện; kết luận dựa trên xu hướng và bằng chứng, không dựa trên một lần GC đơn lẻ.

## 11. Những sai lầm thường gặp khi diễn giải kết quả

| Phát biểu sai hoặc thiếu | Phân tích chính xác hơn |
| --- | --- |
| “Biến `proxy = null` rồi, lớp phải unload ngay.” | Cache có thể vẫn giữ `Class<?>`; GC cũng không unload đồng bộ. |
| “Dùng `WeakHashMap` thì key chắc chắn bị GC.” | Strong value có thể tham chiếu lại key qua lớp/loader và giữ key sống. |
| “WeakReference bị clear nghĩa là đã đo được đúng N lớp unload.” | Chỉ chứng minh referent đã bị GC; cần class-unload log/metrics để xác nhận lớp cụ thể. |
| “Metaspace chưa giảm nghĩa là class leak.” | Committed memory và allocator behavior không phản ánh 1:1 số lớp còn reachable. |
| “Không có log class unload sau 1 giây là JVM không unload.” | Thời điểm GC, collector, cấu hình log và điều kiện reachability có thể khiến chưa quan sát được. |
| “Proxy class giống hidden class.” | Hidden class có quy tắc unload riêng, tùy `ClassOption.STRONG`; thí nghiệm này đo proxy class thông thường. |
| “Mọi strong cache đều sai.” | Cache có scope và kích thước giới hạn là lựa chọn hợp lý; vấn đề là lifetime không phù hợp và thiếu eviction. |
| “Gọi `URLClassLoader.close()` thì chắc chắn lớp được unload.” | `close()` giải phóng tài nguyên loader có quản lý, nhưng không xóa mọi strong reference tới loader/class. |

## 12. Bài tập mở rộng

1. Giải thích vì sao `STRONG_CACHE.put(id, generatedClass)` có thể giữ `ClassLoader` dù biến `loader` chỉ tồn tại trong một method ngắn.
2. Dùng chương trình mẫu chạy `WEAK_VALUE`, `STRONG_VALUE`, `WEAK_KEY_STRONG_VALUE` trên **ba JVM riêng** với `-Xlog:class+unload=info`. Đánh dấu thời điểm unload so với `clear()`. Ghi rõ trường hợp không quan sát được.
3. Thử tăng `total` từ `24` lên `100` trong môi trường test có đủ tài nguyên. Kết quả loader weak refs và Metaspace có thay đổi nhất quán qua nhiều lượt không?
4. Vì sao weak key của `WeakHashMap<ClassLoader, Class<?>>` không đủ để thu hồi key? Hãy vẽ đồ thị tham chiếu từ static map đến key.
5. Nếu một framework giữ `MethodHandle` hoặc `Method` thay vì `Class<?>`, tại sao vẫn cần điều tra đường tham chiếu tới declaring class/loader?
6. Khi reload plugin liên tục, bạn sẽ phân biệt memory leak thật với độ trễ GC và bộ nhớ Metaspace đã commit nhưng chưa trả về OS bằng những bằng chứng nào?
7. Với hidden class mặc định và hidden class dùng `ClassOption.STRONG`, kỳ vọng về điều kiện unload khác nhau thế nào?
8. Đề xuất chính sách cache cho ứng dụng có plugin runtime: tạo, dùng, xóa, vô hiệu hóa và đo lại thế nào để loader cũ có thể được thu hồi?

## 13. Tài liệu chính thức và phiên bản API

- [Oracle Java API — `Proxy.newProxyInstance` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html): tạo lớp proxy runtime và chọn defining loader.
- [Oracle Java API — `ClassLoader` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): quan hệ giữa lớp và defining loader.
- [Oracle Java API — `WeakReference` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability và reference clearing.
- [Oracle Java API — `ReferenceQueue` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/ReferenceQueue.html): quan sát reference đã được GC xếp queue.
- [Oracle Java API — `WeakHashMap` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html): cảnh báo value giữ key.
- [Oracle Java API — `ClassLoadingMXBean` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): loaded/unloaded class counters.
- [Oracle Java Tool Specification — `java -Xlog` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): logging class loading/unloading trên HotSpot.
- [Oracle Java API — `MethodHandles.Lookup.ClassOption` (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `STRONG` và vòng đời hidden class.
- [OpenJDK JEP 371 — Hidden Classes (JDK 15)](https://openjdk.org/jeps/371): động cơ và mô hình hidden class.

**Điểm cần nhớ:** Khi một cache giữ `Class<?>`, `Method`, instance hoặc loader qua strong reference, nó có thể kéo dài vòng đời của **cả nhóm lớp được sinh động**. Muốn đo đúng, hãy kiểm tra **đường tham chiếu mạnh**, dùng weak probes cho loader, đối chiếu với **class unloading log**, quan sát **trước/sau xóa cache** và chỉ kết luận trong giới hạn của JDK/GC thực tế.