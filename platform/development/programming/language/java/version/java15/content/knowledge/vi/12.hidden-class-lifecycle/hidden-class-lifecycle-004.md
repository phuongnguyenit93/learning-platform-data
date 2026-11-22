# Cache, reference và nguy cơ giữ hidden class lâu hơn dự kiến (Java 15+)

## 1. Tại sao vòng đời của hidden class quan trọng?

Một **hidden class** là lớp được định nghĩa động, thường qua `MethodHandles.Lookup.defineHiddenClass(...)`. Tính năng xuất hiện từ **Java 15** và vẫn được hỗ trợ trong Java hiện hành. Nó phù hợp với framework sinh lớp tạm thời, trình thông dịch, proxy, adapter hoặc mã tạo ra khi chạy mà không cần một binary name có thể nạp như lớp Java thông thường.

Điểm đáng chú ý của hidden class không chỉ là “không thể dùng `Class.forName` để tìm lớp theo tên runtime”. Nó còn có **quan hệ vòng đời với class loader khác lớp thông thường**. Nếu hệ thống tạo rất nhiều hidden class, cơ chế giữ tham chiếu và cache sẽ quyết định liệu chúng có thể đủ điều kiện được JVM thu hồi hay cứ tồn tại lâu hơn mong đợi.

Một hệ thống có thể:
- Tạo **hàng nghìn định nghĩa hidden class** từ cùng một tập bytecode hoặc từ các phiên bản mã sinh khác nhau.
- Lưu `Class<?>`, `MethodHandles.Lookup`, `MethodHandle`, instance hoặc callback vào cache để tái sử dụng.
- Không còn yêu cầu nghiệp vụ đối với lớp cũ nhưng vẫn giữ một **đường tham chiếu mạnh** từ static field, singleton, thread, task queue hoặc cache.
- Tăng mức sử dụng **class metadata/metaspace** và tài nguyên liên quan mà heap dump thông thường không phản ánh đầy đủ.

Mấu chốt: **hidden** không có nghĩa là **tự giải phóng**, `WeakReference` không bảo đảm class được thu hồi, và việc xóa một entry cache không bảo đảm JVM lập tức unload lớp.

## 2. Hai quan hệ với defining class loader: mặc định và STRONG

`defineHiddenClass` nhận một số tùy chọn trong `MethodHandles.Lookup.ClassOption`. Đối với **vòng đời**, tùy chọn quan trọng là **`STRONG`**.

### 2.1. Mặc định: hidden class có quan hệ yếu với defining loader

```java
// Minh họa trong code có Lookup đủ quyền và byte[] bytes hợp lệ:
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(bytes, true);
Class<?> hiddenType = hiddenLookup.lookupClass();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Với lựa chọn mặc định, hidden class **có thể được unload ngay cả khi defining class loader vẫn còn reachable**, miễn JVM thấy lớp đó không còn các tham chiếu sống cần thiết và quyết định thực hiện class unloading.

Điểm này khác lớp Java thông thường: một lớp thường được nạp bởi loader có quan hệ mạnh với loader; theo quy tắc chung của JLS, nó chỉ đủ điều kiện unload khi **defining class loader** có thể bị thu hồi. Hidden class mặc định được phép có vòng đời ngắn hơn.

**“Có thể” không đồng nghĩa “sẽ xảy ra ngay”**. Việc unload là hoạt động do JVM/GC quyết định; có khả năng class vẫn nằm trong bộ nhớ một thời gian sau khi không còn được sử dụng.

### 2.2. `STRONG`: gắn vòng đời với defining loader

```java
// Minh họa trong code có Lookup đủ quyền và byte[] bytes hợp lệ:
MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
        .defineHiddenClass(
                bytes,
                true,
                MethodHandles.Lookup.ClassOption.STRONG);
```

`STRONG` yêu cầu hidden class có **quan hệ mạnh với loader được đánh dấu là defining loader**, tương tự lớp thông thường. Theo tài liệu API, hidden class này chỉ có thể unload khi defining loader không còn reachable và có thể được GC thu hồi. Nếu defining loader sống lâu (chẳng hạn loader ứng dụng tồn tại suốt quá trình), hidden class dùng `STRONG` thường sẽ không đủ điều kiện unload riêng chỉ vì cache ứng dụng đã bị xóa.

| Thuộc tính | Không có `STRONG` (mặc định) | Có `ClassOption.STRONG` |
|---|---|---|
| Có phải hidden class không? | Có | Có |
| `Class.isHidden()` | `true` | `true` |
| Có thể tìm bằng `Class.forName(runtimeName)`? | Không | Không |
| Có thể unload khi defining loader còn reachable? | **Có thể**, nếu các điều kiện khác cho phép và JVM thực hiện unloading | **Không**, theo hợp đồng quan hệ mạnh với loader |
| Còn nhiều reference mạnh tới class/instance/handle? | Chúng có thể ngăn unloading | Chúng cũng có thể kéo dài thời gian sống |
| Dùng khi nào? | Lớp triển khai sinh tạm, cần khả năng được thu hồi độc lập với loader | Lớp cần cùng vòng đời với loader hoặc lớp thông thường liên quan |

**Quan trọng:** `STRONG` là **tùy chọn khi định nghĩa lớp**, không phải đặc tính có thể bật/tắt cho một hidden class đã tồn tại. `Class.isHidden()` **không cho biết** class đã được tạo với tùy chọn `STRONG` hay chưa.

`ClassOption.NESTMATE` là lựa chọn khác, chủ yếu về **quan hệ nest và quyền truy cập private**, không thay thế `STRONG` và không phải cơ chế dọn cache.

## 3. Reachability: đường tham chiếu nào giữ lớp sống?

Để suy luận việc thu hồi, cần phân biệt **đối tượng tham chiếu** và **nơi tạo ra đường tham chiếu mạnh đến nó**.

```text
GC root: static field / thread / singleton / registry / task queue
      |
      +--> Map<String, Class<?>> ---------> Class<?> hiddenType
      |
      +--> Map<String, Lookup> -----------> Lookup(hiddenType)
      |
      +--> Map<String, MethodHandle> -----> MethodHandle
      |                                      |
      |                                      +--> target hoặc MethodType liên quan hidden class
      |                                      +--> receiver nếu đã bindTo(instance)
      |
      +--> Map<String, Object> -----------> instance của hidden class
      |
      +--> listener/callback ------------> captured instance / bound handle
```

Đây là sơ đồ **các khả năng giữ tham chiếu**, không phải mô tả chi tiết một cấu trúc dữ liệu bắt buộc duy nhất của JVM. Nếu có đường reference mạnh từ GC root tới metadata hoặc object của hidden class, lớp có thể bị giữ lại lâu hơn dự tính.

### Những đối tượng thường bị quên

| Giá trị còn được giữ | Vì sao có thể giữ lớp hidden? | Chỗ dễ phát sinh reference |
|---|---|---|
| **Instance** của hidden class | Object đang sống cần class runtime của nó | Factory, listener, callback, session, queue |
| **`Class<?>`** của hidden class | Một tham chiếu mạnh trực tiếp tới class object | `Map<String, Class<?>>`, reflection registry |
| **`MethodHandles.Lookup`** trả về bởi `defineHiddenClass` | Lookup gắn với lookup class là hidden class | Cache lookup hoặc giữ trong singleton |
| **`MethodHandle`** tới constructor/method | Handle có target và/hoặc `MethodType` liên quan hidden class; handle đã bind còn có receiver | Cache delegate, callback, adapter |
| **Lambda/closure** giữ instance hoặc handle | Closure có thể capture reference tới object/handle | Scheduler, event bus, executor, stream callback |
| **`ThreadLocal`** hoặc task còn nằm trong queue | Thread sống lâu có thể giữ value/task | Thread pool, executor, xử lý request |
| **Static field** của class sống lâu | Static registry trở thành điểm xuất phát của đường reference | Cache toàn cục, plugin manager |

Một **bound method handle** được tạo bằng `someHandle.bindTo(instance)` đặc biệt dễ bị bỏ sót: nhìn từ API, nó giống một callback gọi được mà không cần truyền receiver, nhưng **receiver đã được gắn bên trong handle**. Giữ bound handle cũng có thể giữ instance và hidden class.

Cần lưu ý rằng bản thân **tên chuỗi** của hidden class không phải yếu tố giữ class; lưu chuỗi `getName()` khác hẳn lưu `Class<?>`, `Lookup` hoặc `MethodHandle`. Tuy nhiên, tên runtime của hidden class cũng **không phải ID ổn định** thích hợp làm cache key lâu dài.

## 4. Cache đúng chức năng nhưng sai vòng đời

### 4.1. Static `HashMap` có thể vô tình tạo retention dài hạn

Giả sử framework tạo hidden class cho mỗi quy tắc xử lý và lưu handle:

```java
// Minh họa trong một lớp có quyền truy cập, không phải chương trình độc lập.
static final java.util.Map<String, java.lang.invoke.MethodHandle> CACHE =
        new java.util.HashMap<>();

static void remember(String id, java.lang.invoke.MethodHandle handle) {
    CACHE.put(id, handle);
}
```

Nếu `id` luôn mới và không có bước `remove`/eviction, số entry tăng không giới hạn. Mỗi handle có thể duy trì một đường tham chiếu tới hidden class, do đó hidden class **mặc định** cũng có thể không đủ điều kiện để unload dù quan hệ với loader là yếu.

Đây không nhất thiết là **heap leak của toàn bộ object graph** theo nghĩa mọi object đều không mong muốn; nó có thể là **retention của class metadata, method handles và các đối tượng do runtime sinh** do thiết kế cache.

### 4.2. `clear()` chỉ xóa reference của cache đó

```java
CACHE.remove(ruleId);  // Xóa một mapping cụ thể.
CACHE.clear();          // Xóa toàn bộ mapping của cache này.
```

Hai lệnh trên chỉ giải phóng các **cạnh tham chiếu do chính cache giữ**. Chúng không:
- Xóa các local variable còn sống như `instance`, `hiddenLookup`, `Class<?> hiddenType`.
- Xóa handle đã được đưa tới registry hoặc callback ở chỗ khác.
- Làm `MethodHandle` trở thành một đối tượng có thể `close()`.
- Bắt buộc GC chạy hay buộc JVM thực hiện class unloading.
- Bỏ hiệu lực `STRONG` đã được chọn khi class được định nghĩa.

Do đó, câu “đã `clear` cache nên lớp chắc chắn được thu hồi” là **không được bảo đảm**.

### 4.3. Cùng một bytecode có thể tạo nhiều class runtime khác nhau

Mỗi lần gọi `defineHiddenClass` có thể tạo **một định nghĩa class mới**, dù `byte[]` đầu vào giống hệt. Hai `Class<?>` có thể:
- Đều `isHidden() == true`.
- Có cùng defining class loader.
- Nhưng **không cùng class identity** (so sánh `==` cho `false`).

Vì vậy, cache theo khóa nghiệp vụ nên cân nhắc **tái sử dụng implementation đang còn hợp lệ**, thay vì cứ tạo lớp mới trên mỗi request. Nếu phải tạo mới do thay đổi mã sinh, cần có cơ chế invalidation cho phiên bản cũ.

## 5. Ví dụ Java 17+: class được định nghĩa mặc định/STRONG, handle được cache

Ví dụ hoàn chỉnh sau phân biệt **class identity**, **cache handle** và **weak observer**, nhưng cố ý không chờ GC hay khẳng định thời điểm unload.

Chuẩn bị **ba tệp** trong cùng một thư mục. Hai tệp đầu sẽ được biên dịch thành classfile; file implementation được đổi đuôi thành `.bytes` để chương trình thứ ba nạp bytecode làm hidden class.

### 5.1. `Task.java`

```java
public interface Task {
    String execute();
}
```

### 5.2. `GeneratedTask.java`

```java
final class GeneratedTask implements Task {
    @Override
    public String execute() {
        return "ok";
    }
}
```

Tệp này chỉ tạo **classfile đầu vào**. Việc class trong source là package-private không tự làm nó thành hidden class; **`defineHiddenClass` tại runtime** mới thực hiện điều đó.

### 5.3. `HiddenCacheDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

public class HiddenCacheDemo {
    private static final Map<String, MethodHandle> HANDLES = new HashMap<>();

    private static MethodHandles.Lookup define(byte[] bytes, boolean strong)
            throws IllegalAccessException {
        MethodHandles.Lookup caller = MethodHandles.lookup();
        return strong
                ? caller.defineHiddenClass(bytes, true, MethodHandles.Lookup.ClassOption.STRONG)
                : caller.defineHiddenClass(bytes, true);
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(Path.of("GeneratedTask.bytes"));
        MethodHandles.Lookup weakLookup = define(bytes, false);
        MethodHandles.Lookup strongLookup = define(bytes, true);
        Class<?> weakType = weakLookup.lookupClass();
        Class<?> strongType = strongLookup.lookupClass();

        System.out.println("hidden=" + weakType.isHidden());
        System.out.println("different-definitions=" + (weakType != strongType));
        System.out.println("same-loader="
                + (weakType.getClassLoader() == strongType.getClassLoader()));

        MethodHandle constructor = weakLookup.findConstructor(
                weakType, MethodType.methodType(void.class));
        Task task = (Task) constructor.invoke();
        MethodHandle bound = weakLookup.findVirtual(
                weakType, "execute", MethodType.methodType(String.class))
                .bindTo(task);
        HANDLES.put("demo", bound);

        System.out.println("via-interface=" + task.execute());
        System.out.println("via-handle=" + (String) HANDLES.get("demo").invokeExact());
        WeakReference<Class<?>> watched = new WeakReference<>(weakType);
        System.out.println("weak-observer-with-strong-ref="
                + (watched.get() == weakType));
        System.out.println("cache-before=" + HANDLES.size());
        HANDLES.clear();
        System.out.println("cache-after=" + HANDLES.size());
    }
}
```

Vì `HiddenCacheDemo` và classfile `GeneratedTask` nằm **cùng package mặc định** trong ví dụ, `MethodHandles.lookup()` tại vị trí này có quyền để gọi `defineHiddenClass` cho classfile đó. Trong code ứng dụng thực, nên dùng một **named package** và bảo đảm lookup class/classfile cùng runtime package, có đủ full privilege access; không thể thay bằng `publicLookup()` tùy tiện.

Phương thức `define` tạo một hidden class mặc định hoặc một hidden class có `ClassOption.STRONG`, không tạo ordinary class bằng `ClassLoader.defineClass`. Cả hai cùng là hidden class.

### 5.4. Biên dịch và chạy

Dùng JDK 17 trở lên. Trên macOS/Linux:

```bash
javac --release 17 -encoding UTF-8 Task.java GeneratedTask.java HiddenCacheDemo.java
mv GeneratedTask.class GeneratedTask.bytes
java -cp . HiddenCacheDemo
```

Trong PowerShell:

```powershell
javac --release 17 -encoding UTF-8 Task.java GeneratedTask.java HiddenCacheDemo.java
Rename-Item GeneratedTask.class GeneratedTask.bytes
java -cp . HiddenCacheDemo
```

Bước đổi đuôi **không thay đổi bytecode**; nó giúp tránh việc loader tự nạp `GeneratedTask.class` như ordinary class bằng tên trên classpath trong thí nghiệm. Lúc chương trình chạy, `Files.readAllBytes(Path.of("GeneratedTask.bytes"))` phụ thuộc working directory; khi triển khai trong JAR nên đọc bytecode bằng resource API phù hợp.

**Stdout chính xác:**

```text
hidden=true
different-definitions=true
same-loader=true
via-interface=ok
via-handle=ok
weak-observer-with-strong-ref=true
cache-before=1
cache-after=0
```

Các kết luận **có thể kiểm chứng trực tiếp** từ stdout:

- `hidden=true`: class default đã được định nghĩa là hidden class.
- `different-definitions=true`: hai lần định nghĩa từ cùng bytecode tạo **hai Class identity khác nhau**.
- `same-loader=true`: ở ví dụ, hai class có cùng defining loader; **không** có nghĩa chúng cùng class identity.
- `via-interface=ok`: đối tượng của hidden class dùng được qua `Task`.
- `via-handle=ok`: một **bound MethodHandle** trong cache vẫn gọi được phương thức của instance.
- `weak-observer-with-strong-ref=true`: `WeakReference` **không cản** việc đọc class object khi `weakType` vẫn đang được tham chiếu mạnh trong cùng biểu thức.
- `cache-before=1` và `cache-after=0`: xóa mapping hoạt động, **không chứng minh class đã unload**.

**Đừng diễn giải nhầm:** Sau khi `HANDLES.clear()`, phương thức `main` vẫn có các local variable như `weakLookup`, `weakType`, `constructor`, `task`, `bound`, và `strongLookup`. Ngay cả khi một số biến không còn được JIT coi là live ở điểm cuối, việc xóa cache **không tạo bảo đảm** rằng mọi reference đã mất hoặc lớp đã được unload. Ngoài ra, class dùng `STRONG` bị ràng buộc với defining loader cho dù cache đã bị xóa.

Chương trình **không gọi `System.gc()`** và không in những dự đoán về thời điểm GC, vì kết quả đó không đáng tin để làm stdout cố định.

## 6. Strong reference, WeakReference và ReferenceQueue

### 6.1. `WeakReference<T>` chỉ giữ yếu đối tượng được theo dõi

```java
// Minh họa trong phương thức đã có Class<?> hiddenType.
java.lang.ref.WeakReference<Class<?>> probe =
        new java.lang.ref.WeakReference<>(hiddenType);

Class<?> current = probe.get();
if (current != null) {
    System.out.println(current.isHidden());
}
```

`WeakReference` không giữ `Class<?>` sống bằng một **strong reference của chính nó**. Khi class không còn được strong/soft reachable theo quy tắc GC, GC có thể xóa weak reference. Nhưng nếu có **bất kỳ đường strong reference khác** tới class, `probe.get()` vẫn có thể trả đối tượng.

Hãy chép kết quả `get()` sang **local strong variable `current`** trước khi dùng để tránh kiểm tra `get() != null` rồi đọc `get()` lần thứ hai và gặp `null` do GC ở giữa. Việc tham chiếu yếu bị xóa cũng không có nghĩa bạn có thể biết thời điểm JVM đã giải phóng toàn bộ class metadata.

Nếu một thao tác cần giữ đối tượng sống đến đúng một điểm, `java.lang.ref.Reference.reachabilityFence(object)` là API hiện hành để biểu đạt ranh giới strong reachability đó; nó **không phải lệnh GC/cleanup**.

### 6.2. `ReferenceQueue` dùng để nhận thông báo bất đồng bộ

Có thể đăng ký weak reference với một `ReferenceQueue<Class<?>>` để **quan sát** khi tham chiếu bị GC xóa và enqueue. Nhưng:

- Không có cam kết rằng GC sẽ xảy ra vào thời điểm định trước.
- Không có cam kết rằng một hidden class không còn dùng sẽ được unload ngay lập tức.
- `poll()` có thể trả `null` vì queue chưa có phần tử.
- Một test dựa trên “sau 100 ms hoặc sau một `System.gc()` thì queue phải có phần tử” là **flaky**.

`ReferenceQueue` giúp cleanup bookkeeping khi có tín hiệu; chính sách dọn dẹp nghiệp vụ, TTL, giới hạn kích thước và shutdown vẫn cần thiết độc lập.

### 6.3. Bẫy của `WeakHashMap`: weak keys, strong values

Một cách sửa cache dễ tưởng nhầm là:

```java
// Minh họa nguy hiểm, không khuyến nghị áp dụng nguyên trạng:
java.util.Map<Class<?>, java.lang.invoke.MethodHandle> cache =
        new java.util.WeakHashMap<>();
cache.put(hiddenType, boundHandle);
```

`WeakHashMap` giữ **key yếu**, nhưng **value mạnh**. Nếu `boundHandle` có target/reference/receiver giữ lại chính `hiddenType`, sơ đồ có thể trở thành:

```text
WeakHashMap -> value MethodHandle (strong) -> class hoặc instance
      ^                                      |
      |---------- key Class<?> (weak) <------+
```

Value làm class/key vẫn strong reachable qua đường khác, nên entry **không tự biến mất chỉ nhờ key được khai báo là weak**. Oracle Javadoc của `WeakHashMap` cảnh báo trực tiếp về values tham chiếu trở lại keys (trực tiếp hoặc gián tiếp).

Với cache chứa các method handle gắn tới hidden class, **không được coi `WeakHashMap<Class<?>, MethodHandle>` là giải pháp chống retention mặc định**. Hãy kiểm tra toàn bộ đồ thị tham chiếu; cân nhắc giới hạn cache/invalidate theo vòng đời hoặc cấu trúc trong đó value không giữ key, thay vì chỉ đổi `HashMap` sang `WeakHashMap`.

**`SoftReference` cũng không phải giải pháp TTL đáng tin:** nó cho GC quyền quyết định thời điểm xóa theo chính sách bộ nhớ, không tạo hợp đồng “hết hạn sau N phút”.

## 7. Thiết kế cache để không giữ lớp vô hạn

### 7.1. Chỉ cache khi lợi ích lớn hơn chi phí sinh lớp

Nếu một lớp sinh từ template ổn định và nhiều request dùng cùng hành vi, việc tạo hidden class mới cho mỗi request có thể tốn class metadata và CPU. Có thể cache **theo khóa nghiệp vụ ổn định** (ví dụ mã template + phiên bản, cấu hình sinh code), tái sử dụng cùng handle hoặc instance nếu chúng đúng hợp đồng và an toàn giữa các luồng.

Ngược lại, cache toàn cục với khóa duy nhất trên mỗi request không có tái sử dụng thực sự, lại tăng số lớp và reference sống. Khi không cần tái sử dụng, tránh cho instance, handle hoặc `Lookup` thoát ra khỏi phạm vi xử lý.

### 7.2. Giới hạn dung lượng và có chính sách invalidation

Một cache production cần ít nhất các đặc tính thích hợp với nghiệp vụ:

- **Giới hạn kích thước** (maximum entries/weight) hoặc eviction phù hợp; đừng dùng `ConcurrentHashMap` vô hạn chỉ vì thread-safe.
- **TTL/idle expiry** nếu các phiên bản không còn dùng theo thời gian; hết hạn cần được triển khai bằng cache/library phù hợp, không phải đặc tính sẵn có của `HashMap`.
- **Invalidation khi cập nhật plugin/template**, hủy tenant/session hoặc shutdown module.
- **Không leak scope**: cache thuộc một module/tenant nên hết vòng đời cùng module/tenant, không bị singleton toàn tiến trình giữ.
- **Không giữ `Lookup` full-privilege lâu hơn cần thiết**; có thể giữ handle đã giảm quyền/phạm vi nếu thiết kế cho phép.
- **Đồng bộ với thao tác còn đang chạy**: eviction không tự “hủy” một lời gọi đang sử dụng handle/instance. Cần tách chính sách ngừng nhận công việc mới khỏi reference của tác vụ đang thực thi.

Ví dụ một helper **minh họa** (không phải cơ chế GC hay cache production hoàn chỉnh):

```java
import java.lang.invoke.MethodHandle;
import java.util.HashMap;
import java.util.Map;

final class HandleRegistry {
    private final Map<String, MethodHandle> entries = new HashMap<>();

    void put(String key, MethodHandle handle) {
        entries.put(key, handle);
    }

    MethodHandle get(String key) {
        return entries.get(key);
    }

    void invalidate(String key) {
        entries.remove(key);
    }

    void clear() {
        entries.clear();
    }
}
```

Helper trên không thread-safe, không giới hạn dung lượng và không có TTL; **chỉ minh họa explicit invalidation**. Khi dùng thật, bổ sung điều khiển đồng thời và giới hạn theo mức truy cập; xóa entry chỉ bỏ reference do registry sở hữu, không phải lệnh unload class.

### 7.3. Khi cache dữ liệu gắn với `Class<?>`

`ClassValue<T>` là API hiện hành cho giá trị tính theo một `Class<?>` và thường là lựa chọn đáng cân nhắc hơn một global map thủ công nếu bài toán thực sự là **metadata gắn với class**. Tuy nhiên, nó không thay thế việc phân tích đồ thị tham chiếu của method handle/instance hoặc giải quyết tùy chọn `STRONG`. Chỉ chọn `ClassValue` khi mô hình sở hữu và việc invalidate/compute phù hợp với API.

Tương tự, một `WeakReference<MethodHandle>` có thể để handle biến mất trước lúc tái sử dụng; code phải xử lý cache miss và tái tạo an toàn. Weak caching không mặc nhiên tối ưu: có thể làm mất hiệu năng, tăng số lần sinh lớp và tạo thêm metadata tạm.

## 8. `STRONG` không thay thế quản lý cache

Một hiểu nhầm phổ biến: bật `STRONG` để “giữ lớp ổn định”, sau đó hy vọng xóa cache sẽ cho lớp unload. Hai bước đó mâu thuẫn nếu defining loader vẫn còn reachable.

**Với hidden class mặc định:**
- Xóa các strong reference từ cache và các scope khác **có thể** khiến lớp đủ điều kiện unload ngay cả khi loader vẫn sống.
- Điều kiện “đủ điều kiện” không buộc JVM chạy class unloading hay đặt thời hạn thu hồi.
- Giữ một live instance hoặc method handle là lý do đủ để lớp tiếp tục cần tồn tại.

**Với hidden class `STRONG`:**
- Tính đủ điều kiện unload **gắn với khả năng thu hồi defining loader** theo hợp đồng API.
- Nếu loader là loader ứng dụng sống suốt tiến trình, việc tạo lặp lại nhiều hidden class `STRONG` có nguy cơ kéo dài class metadata tới khi loader kết thúc vòng đời.
- Giải pháp không phải gọi `System.gc()` liên tục mà là **chọn tùy chọn định nghĩa đúng**, tránh tạo class trùng lặp, quản lý loader/module và thiết kế cache có vòng đời rõ.

Nếu mục đích là sinh lớp ngắn hạn độc lập với loader, mặc định **không cần `STRONG`**. Nếu hidden class có quan hệ vòng đời chặt với một ordinary class/loader và phải tồn tại tương ứng, `STRONG` có thể là lựa chọn hợp lý. Hãy dựa trên yêu cầu runtime cụ thể, không bật chỉ vì tên nghe “an toàn hơn”.

## 9. Giám sát: đừng dùng một lần GC làm bằng chứng

### 9.1. Phân biệt heap memory và class metadata

Một dịch vụ Java động có thể gặp:
- Heap tăng do cache key, value, handle, instance hoặc dữ liệu capture.
- Metaspace/class metadata tăng vì nhiều class definitions còn sống.
- Thời gian CPU tăng do define/verify/link/initialize nhiều lớp lặp lại.
- Thông số class loading/unloading tăng nhưng **không chỉ ra nguyên nhân retention** nếu không kết hợp dấu vết tham chiếu và đặc tả của JVM.

Nhìn riêng `Runtime.getRuntime().totalMemory()`/heap usage không đủ để khẳng định lớp hidden đã được unload hoặc metaspace khỏe mạnh.

### 9.2. Các nguồn quan sát thực tế

Với **HotSpot JDK 17+**, có thể thử logging của JVM:

```bash
java -Xlog:class+load=info,class+unload=info -cp . HiddenCacheDemo
```

Đây là lệnh dùng để **quan sát class load/unload events**, không phải biến nó thành kết quả phải xuất hiện ngay. Một lần chạy ngắn có thể không có sự kiện unload, và số lượng dòng log phụ thuộc JVM/JDK nên **không được đưa vào stdout mẫu** của chương trình phần 5.

Trong một dịch vụ lâu dài, có thể kết hợp:
- Số lượng class load/unload và class count từ JVM management/JMX, theo thời gian chứ không chỉ một lần chụp.
- Flight Recorder/JFR hoặc công cụ chẩn đoán JVM mà môi trường thực tế hỗ trợ.
- Giám sát metaspace, heap cache size/hit/miss/eviction, số lần gọi `defineHiddenClass`, số phiên bản template/plugin đang active.
- Phân tích retention path từ GC roots (static fields, thread-local, event registrations, method handles) khi có hiện tượng tăng trưởng bất thường.

**Giới hạn:** số lượng unloading và độ chi tiết event có thể khác giữa các triển khai JVM hoặc cấu hình GC; không xây dựng logic nghiệp vụ dựa vào một con số log cụ thể.

### 9.3. Đừng test GC theo timeout

Các kiểm thử kiểu:

```java
System.gc();
Thread.sleep(100);
assert weakReference.get() == null;
```

**không đáng tin**: `System.gc()` là yêu cầu/gợi ý, không bảo đảm class unloading; thời gian ngủ không tạo hợp đồng. Ngoài ra, compiler/JIT có thể tối ưu liveness của local variables khác điều người đọc source nghĩ.

Đối với unit test, hãy kiểm tra **hành vi quyết định được**:
- Cache `put/get/invalidate/clear` trả đúng kích thước và kết quả.
- Hai định nghĩa hidden class từ một bytecode là hai `Class<?> identity` khác nhau.
- Interface/MethodHandle hoạt động trước khi xóa cache.
- Không còn mục lưu giữ ngoài ý muốn trong các registry do ứng dụng quản lý.
- Close/shutdown dọn đúng các bảng đăng ký, callback và thread-local được thiết kế.

Còn khả năng thực tế class unload và metaspace ổn định nên được đánh giá bằng **integration/soak test**, quan sát xu hướng và instrumentation phù hợp; không kết luận tuyệt đối từ một lần gọi GC.

## 10. Tình huống dễ mắc lỗi

| Triệu chứng | Nguyên nhân cần xem xét | Biện pháp có cơ sở |
|---|---|---|
| Metaspace tăng đều khi sinh nhiều lớp | `defineHiddenClass` lặp lại, cache giữ class/handle; có thể có `STRONG` | Kiểm kê số định nghĩa mỗi key, lựa chọn class options, cache entries, retention path |
| `WeakReference<Class<?>>.get()` không trả null | Vẫn có class/Lookup/instance/handle sống ở chỗ khác; hoặc chưa có GC thích hợp | Tìm GC roots và loại bỏ reference do ứng dụng sở hữu; không ép thời hạn |
| `WeakHashMap` không tự giảm số phần tử | Value mạnh tham chiếu ngược tới key hoặc có reference mạnh ngoài map | Kiểm tra đồ thị key-value; không nhầm weak key với weak value |
| Đã `cache.clear()` nhưng lớp vẫn còn | Local variable, registry khác, task đang chạy, hoặc `STRONG` gắn loader | Kiểm tra toàn bộ scope; riêng `STRONG` cần xem vòng đời loader |
| Plugin đã tắt nhưng classloader chưa thu hồi | Callback/static/thread-local/task giữ plugin loader hoặc class | Cleanup đăng ký, task và các handle; theo dõi đường strong reference |
| Nhiều định nghĩa từ cùng `byte[]` | Không cache/reuse theo khóa nghiệp vụ, hoặc cache miss liên tục | Thiết kế reuse, bounded cache và invalidation khi phiên bản thay đổi |
| Kiểm thử unload lúc pass lúc fail | Dựa vào GC timing, sleep, `System.gc()` | Chuyển sang test deterministic; đo lifecycle bằng soak test |
| `Class.isHidden()` là `true` nhưng không rõ `STRONG` | `isHidden()` không bộc lộ class option | Ghi nhận tùy chọn tại thời điểm factory define; đừng đoán qua tên/class |
| Cache mới dùng weak value liên tục miss | Handle bị GC thu hồi trước khi có reuse, phải sinh lại class | Đánh đổi hit rate, số lần define và bộ nhớ bằng đo lường thực tế |
| Dùng tên runtime của hidden class làm cache key | Tên không là binary name có thể liên kết và không ổn định giữa lần define | Dùng ID/template/version nghiệp vụ, quản lý class identity riêng khi cần |

## 11. Quy trình thiết kế và kiểm tra vòng đời

1. **Xác định ai sở hữu việc tạo lớp:** một request, một phiên plugin, một tenant hay toàn ứng dụng? Đừng đặt cache toàn cục nếu class chỉ có vòng đời một request.
2. **Xác định `STRONG` có thật sự cần không:** lớp tạm được sinh hàng loạt thường nên giữ khả năng unload độc lập với loader; lớp cần gắn chặt loader có thể có lý do dùng `STRONG`.
3. **Liệt kê mọi đường tham chiếu:** `Class<?>`, `Lookup`, `MethodHandle`, instance, callback, `ThreadLocal`, queue, static registry, lambda capture.
4. **Chọn khóa cache đúng:** khóa nghiệp vụ ổn định + version; tránh dùng tên runtime hidden class như ID ngoài hệ thống.
5. **Đặt bound rõ:** maximum entries/weight, TTL hoặc eviction, hành vi khi plugin đổi phiên bản và shutdown.
6. **Thiết kế invalidation:** dỡ đăng ký sự kiện, ngừng queue/task khi cần, dọn thread-local, xóa cache đúng owner. Hiểu rằng những caller đang dùng object có quyền giữ reference cho tới khi hoàn tất.
7. **Đo và kiểm thử:** xác nhận cache sizing/hit/miss, số lần define và số lớp còn live; quan sát heap/metaspace và class-unloading trong môi trường lâu dài.
8. **Không hứa hẹn GC determinism:** chỉ kiểm tra những bất biến nghiệp vụ có thể xác nhận; mọi diễn giải thời điểm unload phải tôn trọng đặc tả JVM.

## 12. Ghi nhớ

**Hidden class mặc định** có thể được JVM unload độc lập với defining loader, nhưng chỉ khi các điều kiện về reachability cho phép và JVM thực sự quyết định unload. `ClassOption.STRONG` thay đổi điều kiện đó để gắn vòng đời với defining loader, **không** giúp cache tự dọn.

Trong thực tế, nguồn gốc của retention thường là **một reference mạnh mà lập trình viên không còn nghĩ tới**: cache `MethodHandle`, `Lookup`, `Class<?>`, bound callback, instance hoặc registry lâu đời. `WeakReference`, `WeakHashMap`, `clear()` và `System.gc()` đều có phạm vi tác dụng riêng; không cái nào là cam kết “giải phóng class ngay bây giờ”.

Thiết kế đáng tin cậy là **chọn class option theo vòng đời**, **quản lý cache có giới hạn và cách hủy rõ ràng**, **xác định mọi reference owner**, và **đo lường bằng tín hiệu JVM thay vì suy diễn từ một test GC**.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — `MethodHandles.Lookup` (hidden class, class loader relationship)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Oracle Java SE 26 — `MethodHandles.Lookup.ClassOption.STRONG`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html).
- [Oracle Java SE 26 — `WeakReference`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/WeakReference.html), [`ReferenceQueue`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/ReferenceQueue.html), [`Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Reference.html).
- [Oracle Java SE 26 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/WeakHashMap.html), [`ClassValue`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassValue.html).
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) (tính năng được giới thiệu ở Java 15; các API đang được dùng trong Java hiện hành).
