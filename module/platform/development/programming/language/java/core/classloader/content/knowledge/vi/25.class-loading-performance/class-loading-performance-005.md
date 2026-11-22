# Cache đúng phạm vi mà không giữ ClassLoader đã hết vòng đời

## 1. Vấn đề: cache nhanh hơn, nhưng có thể khiến plugin không bao giờ được dỡ

Một hệ thống plugin thường tạo `ClassLoader` riêng cho từng plugin hoặc từng phiên bản. Để giảm chi phí reflection, lookup hay xử lý metadata, host có thể cache `Class<?>`, `Method`, `Constructor`, provider instance, parser hoặc các đối tượng đã tính toán.

Ví dụ:

```java
static final Map<String, Class<?>> CLASSES = new ConcurrentHashMap<>();
```

Đây là đoạn mã minh họa cần imports và đặt trong một class. Nếu map này là **static field của host sống suốt tiến trình** và chứa class do plugin loader định nghĩa, map có thể giữ class → defining loader → toàn bộ tập class metadata của plugin còn reachable. Plugin đã được “stop” về mặt nghiệp vụ nhưng Java heap/Metaspace vẫn giữ dấu vết của loader thế hệ cũ.

**Nguyên tắc chính:** **vòng đời của cache không được dài hơn vòng đời của dữ liệu/lớp/plugin mà nó sở hữu, trừ khi cache dùng cơ chế không giữ đối tượng cũ sống và có chính sách eviction được hiểu đúng.**

Một bảng quyết định nhanh:

| Đang cache gì? | Chủ sở hữu hợp lý | Bao giờ giải phóng? |
|---|---|---|
| Metadata bất biến của JDK/shared API | Cache của host, nếu không chứa plugin-private references | Theo vòng đời host hoặc chính sách giới hạn dung lượng |
| `Class<?>`/`Method` của plugin | Cache gắn với **plugin session/generation** | Khi plugin dừng hoặc reload |
| Provider/plugin instance | Registry gắn với deployment đang hoạt động | Khi stop, sau khi dừng callbacks/tasks |
| Kết quả parse của một request | Request-local cache | Kết thúc request |
| Metadata tính theo runtime `Class<?>` | Có thể cân nhắc `ClassValue` | Theo lifecycle của Class association; vẫn xét references bên ngoài |
| Kết quả âm “class không tìm thấy” | Tối đa trong phạm vi finder/version snapshot xác định | Hủy khi sources thay đổi, không cache vô hạn |
| Reflection method lookup | Per-plugin cache keyed đúng class + signature | Clear cùng plugin loader |

Không có câu trả lời đơn giản “luôn dùng weak refs” hoặc “luôn dùng static map”. Phải biết **ai đang giữ cache**, **cache giữ gì**, **key là gì**, **giá trị có trỏ ngược tới loader hay không**, và **sự kiện lifecycle nào loại bỏ entry**.

## 2. Cơ sở JVM: vì sao giữ Class<?> có thể giữ loader?

Theo JLS 17 `12.7, một class/interface **chỉ có thể được unload nếu defining class loader của nó có thể được GC thu gom**. “Có thể” không có nghĩa JVM sẽ unload ngay.

Một graph thường gặp:

```text
GC root của host
     |
     v
static ConcurrentHashMap<String, Class<?>>
     |
     v
plugin.Worker.class
     |
     v
Defining PluginClassLoader
     |
     v
Các runtime classes / metadata do loader định nghĩa
```

Cache có thể giữ loader theo đường gián tiếp:

```text
Host static cache
   -> java.lang.reflect.Method
   -> declaring Class<?> của plugin
   -> defining loader của plugin
```

Hoặc:

```text
Host event registry
   -> plugin callback/lambda
   -> plugin object/class
   -> plugin defining loader
```

Vì vậy, chỉ đặt biến `loader = null` không đủ nếu vẫn còn `Method`, `Class<?>`, provider object, callback hoặc thread context class loader đang trỏ tới thế hệ plugin đó.

### Defining loader khác initiating loader

`pluginLoader.loadClass("api.Plugin")` có thể ủy quyền cho parent để lấy **cùng `api.Plugin.class` của host**. Cache class shared API này không đồng nghĩa giữ một class do plugin loader định nghĩa. Ngược lại, `pluginLoader.loadClass("plugin.Worker")` thường trả class do plugin loader định nghĩa nếu parent không có tên đó.

Phải phân biệt:

- **Defining loader:** loader thực sự định nghĩa runtime class; có ảnh hưởng trực tiếp tới khả năng class unloading.
- **Initiating loader:** loader mà JVM ghi nhận đã khởi xướng lookup, có thể nhận lại class từ parent.
- **Class identity:** binary name + defining loader, không chỉ class name.

Đừng suy “tôi gọi loadClass qua plugin loader nên mọi Class<?> nhận về đều do plugin loader sở hữu”.

## 3. ClassLoader đã có cơ chế nhớ class được nạp; không nên cache trùng vô ích

Trong `ClassLoader.loadClass(String, boolean)` mặc định, JVM/loader kiểm tra `findLoadedClass(name)` trước khi tìm parent hoặc `findClass`. Một lần gọi lại:

```java
Class<?> a = loader.loadClass("plugin.Worker");
Class<?> b = loader.loadClass("plugin.Worker");
System.out.println(a == b);
```

Đây là snippet cần biến `loader` và phải xử lý `ClassNotFoundException`. Với loader hoạt động đúng, cùng một runtime class name/loader lookup policy thường trả cùng `Class<?>`; trong tình huống đó, in `true`. Nói cách khác, lập thêm `static Map<String, Class<?>>` chỉ để “tránh load class lần hai” có thể đem lại lợi ích rất ít nhưng rủi ro giữ plugin cũ rất lớn.

Cache bổ sung chỉ nên có khi đã đo/biết chi phí cần tối ưu, chẳng hạn:

- Reflection lookup với `getMethod`, `getDeclaredConstructor` hoặc member scanning.
- Metadata phân tích annotation/schema.
- Method handle, serializer/deserializer được compile cho một class cụ thể.
- Kết quả resolution của một plugin registry với cấu trúc đã biết.

**Phải đo cache hit rate, allocation và lookup latency** trước khi biến một cache nội bộ thành static global. Caching có chi phí đồng bộ hóa, key construction, memory và invalidation riêng.

## 4. Chọn cache scope theo lifecycle, không theo mức tiện của static field

Có ít nhất bốn scope:

| Scope | Ví dụ | Có phù hợp plugin-private Class<?> không? |
|---|---|---|
| Method/request | Local map dùng trong request hiện tại | Có thể, nếu thực sự chỉ cần trong request |
| Operation/job | Cache của một batch/job thực thi trong plugin | Có thể, miễn job kết thúc và không bị queue giữ vô hạn |
| Plugin session/generation | `PluginSession` chứa loader và reflection caches | **Thường là lựa chọn tốt** |
| Host process/global singleton | Static map của application loader | **Nguy hiểm** nếu giữ private class/loader qua nhiều reloads |

**Plugin generation** là một lần nạp xác định: plugin X v1 có loader L1; reload plugin X v2 tạo loader L2. Hai lần deploy có thể dùng cùng logical plugin ID và cùng binary class name, nhưng chúng là **hai cache scopes khác nhau**.

### Sai: global cache keyed bằng binary name

```java
static final Map<String, Class<?>> TYPES = new ConcurrentHashMap<>();

// Host gọi trong nhiều plugin generations:
TYPES.put("plugin.Worker", workerClass);
```

Đoạn này minh họa và cần imports/class chứa field. Nếu plugin A và B đều có `plugin.Worker` nhưng do loaders khác nhau định nghĩa, key chỉ là `"plugin.Worker"` sẽ gây **đụng cache**. Host có thể trả class của plugin A cho B, rồi cast/linking sai hoặc tiếp tục pin old loader.

**Hai lỗi độc lập:**

1. **Sai identity:** class name không đủ làm cache key giữa nhiều defining loaders.
2. **Sai lifetime:** static map có thể giữ class của những generations đã dừng.

Dù thêm `pluginId` vào key, ví dụ `"plugin-a:plugin.Worker"`, vẫn cần version/generation và chính sách eviction. Một ID có thể được tái sử dụng khi reload, còn loader object mới có identity khác.

### Đúng hơn: cache trong một PluginSession

```text
Host registry (chỉ chứa sessions đang active)
  -> Session plugin-A generation 42
     -> URLClassLoader L42
     -> Method / Class<?> cache thuộc L42
  -> Session plugin-B generation 7
     -> URLClassLoader L7
     -> cache riêng

Khi stop plugin-A:
  dừng task/callback
  registry.remove(plugin-A)
  session.clearCaches()
  session.closeLoader()
  bỏ mọi strong references tới session cũ
```

Trong mô hình này, **strong references bên trong session không sai**. Chúng có ích khi plugin đang hoạt động. Điều quan trọng là session phải thật sự được **gỡ khỏi các roots sống lâu** khi plugin kết thúc.

## 5. Ví dụ Java 17 hoàn chỉnh: cache Method trong phạm vi PluginSession

Ví dụ dùng `URLClassLoader` riêng để nạp class `plugin.Greeter`, memoize reflection `Method` theo class và signature, rồi xóa cache/đóng loader khi session kết thúc.

Không đoán rằng việc đóng loader sẽ tạo class-unload event ngay lập tức; chỉ chứng minh deterministic cache hit và **cleanup theo lifecycle**.

### 5.1. Cấu trúc file

```text
src/
  plugin/
    plugin/
      Greeter.java
  host/
    SessionCacheDemo.java

out/
  plugin/
  host/
```

`out` được tạo ở bước biên dịch.

### 5.2. Plugin class

File `src/plugin/plugin/Greeter.java`:

```java
package plugin;

public final class Greeter {
    static {
        System.out.println("PLUGIN_INITIALIZED");
    }

    public static String greet(String name) {
        return "Hello " + name;
    }
}
```

### 5.3. Host với cache riêng cho từng session

File `src/host/SessionCacheDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SessionCacheDemo {
    static final class PluginSession implements AutoCloseable {
        private record MethodKey(
                String owner, String name, List<Class<?>> parameterTypes) {
        }

        private final URLClassLoader loader;
        private final Map<MethodKey, Method> methodCache =
                new HashMap<>();
        private int misses;
        private boolean closed;

        PluginSession(URL source, ClassLoader parent) {
            loader = new URLClassLoader(
                    "plugin-session", new URL[]{source}, parent);
        }

        Method method(String owner, String name, Class<?>... params)
                throws ReflectiveOperationException {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }

            MethodKey key = new MethodKey(
                    owner, name, List.copyOf(Arrays.asList(params)));
            Method cached = methodCache.get(key);
            if (cached != null) {
                return cached;
            }

            Class<?> type = Class.forName(owner, false, loader);
            Method found = type.getMethod(name, params);
            methodCache.put(key, found);
            misses++;
            return found;
        }

        ClassLoader loader() {
            return loader;
        }

        int missCount() {
            return misses;
        }

        int cacheSize() {
            return methodCache.size();
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                methodCache.clear();
                loader.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL pluginRoot = Path.of("out/plugin").toUri().toURL();
        ClassLoader sharedParent =
                SessionCacheDemo.class.getClassLoader();

        try (PluginSession session =
                     new PluginSession(pluginRoot, sharedParent)) {

            Method first = session.method(
                    "plugin.Greeter", "greet", String.class);
            Method second = session.method(
                    "plugin.Greeter", "greet", String.class);

            System.out.println("Same cached Method: "
                    + (first == second));
            System.out.println("Reflection cache misses: "
                    + session.missCount());
            System.out.println("Declaring loader is plugin: "
                    + (first.getDeclaringClass().getClassLoader()
                       == session.loader()));
            System.out.println("Before invocation");

            System.out.println(first.invoke(null, "Ada"));
            System.out.println(second.invoke(null, "Bao"));

            System.out.println("Cache entries before close: "
                    + session.cacheSize());
        }

        System.out.println("Session closed");
    }
}
```

**Tại sao key có `Class<?>` thay vì chuỗi tên kiểu tham số?** `MethodKey` chứa declaring binary name, method name và **runtime parameter classes**. Các `Class<?>` trong `List` được so sánh bằng identity theo Java; `Class<?>` do hai loaders khác nhau định nghĩa sẽ không bị coi như cùng type chỉ vì `getName()` giống nhau. Phạm vi session bảo đảm declaring name chỉ được tìm theo loader của session đó.

`List.copyOf(Arrays.asList(params))` giữ một bản immutable snapshot của danh sách parameter types; không sử dụng một mảng varargs mutable làm key.

**Đối với production:** key có thể dùng trực tiếp declaring `Class<?>` nếu đã có type và các method signatures chính xác; nếu cache dùng chung giữa classes từ nhiều loaders, tuyệt đối không chỉ dùng tên chuỗi. Nếu có inherited methods hoặc overloads/varargs, phải kiểm soát lookup contract và parameter descriptors đúng.

### 5.4. Biên dịch/chạy trên JDK 17

Bash:

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/plugin/Greeter.java
javac -d out/host src/host/SessionCacheDemo.java
java -cp out/host SessionCacheDemo
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/plugin/Greeter.java
javac -d out/host src/host/SessionCacheDemo.java
java -cp out/host SessionCacheDemo
```

**Không** đưa `out/plugin` vào `-cp` của host, nếu không parent loader có thể cung cấp `plugin.Greeter` trước khi `URLClassLoader` của session được hỏi theo parent-first policy.

Stdout xác định khi chạy sạch:

```text
Same cached Method: true
Reflection cache misses: 1
Declaring loader is plugin: true
Before invocation
PLUGIN_INITIALIZED
Hello Ada
Hello Bao
Cache entries before close: 1
Session closed
```

### 5.5. Hiểu kết quả

1. Hai lookup cùng `MethodKey` trong một session trả cùng `Method` instance, chứng minh cache hit.
2. Chỉ lookup đầu tiên thực hiện `Class.forName(..., false, loader)` và `getMethod`; `missCount` bằng 1.
3. Declaring `Class<?>` của `Method` thực sự do session URLClassLoader định nghĩa.
4. `Class.forName(..., false, ...)` tìm class nhưng không yêu cầu initialization. Static initializer `PLUGIN_INITIALIZED` chỉ chạy khi reflective invocation của static method được thực hiện.
5. Cache vẫn giữ mạnh `Method` và những `Class<?>` mà key/value tham chiếu tới **trong lúc session active**. Điều đó là chủ đích.
6. `close()` xóa cache và đóng tài nguyên URLClassLoader.
7. Sau khi thoát scope và không còn roots khác giữ session/Method/Class, defining loader **có thể** trở nên eligible cho GC. Ví dụ **không** khẳng định JVM đã GC hay unload class ngay khi in `Session closed`.

Các biến local `first` và `second`, cùng stack/liveness của JVM, cũng có thể ảnh hưởng khả năng GC tại thời điểm gần khối `try`. Đó là lý do demo cố tình **không** in một boolean “unloaded=true” sau khi close.

### 5.6. Điều kiện triển khai song song

`HashMap` trong demo chỉ dành cho access tuần tự. Nếu một `PluginSession` phục vụ nhiều threads đồng thời, không chia sẻ `HashMap` không đồng bộ như thể nó thread-safe. Có thể:

- Dùng `ConcurrentHashMap<MethodKey, Method>` và `computeIfAbsent` với chính sách exception/lookup phù hợp.
- Hoặc đồng bộ vùng cache lookup một cách có kiểm soát.
- Quan trọng hơn, **phối hợp close với in-flight tasks** để không đóng loader và clear cache trong lúc worker còn cần nạp lớp hoặc chạy plugin.

Không dùng một khóa global cho tất cả plugins nếu chúng có thể hoạt động độc lập; tránh contention không cần thiết.

## 6. Dọn cache khi dừng plugin: thứ tự quan trọng

Một lifecycle hợp lý:

```text
ACTIVE
  |
  v
STOPPING: ngừng nhận request mới
  |
  v
DRAIN: chờ in-flight tasks hoàn tất
  |
  v
UNREGISTER: listeners / scheduled jobs / providers
  |
  v
CLEAR: method/class/provider caches của session
  |
  v
CLOSE: streams / JAR handles / URLClassLoader
  |
  v
REMOVE: gỡ session khỏi registry của host
  |
  v
Để old loader không còn strong reachability
  |
  v
JVM có thể GC/unload khi thích hợp (không có deadline)
```

Trật tự cụ thể có thể khác theo framework; yêu cầu bất biến là **không có công việc mới truy cập session đã đóng** và phải xóa mọi root không cần thiết. Đôi khi cần remove registry entry **trước khi** đóng loader để cấm lookup mới, nhưng vẫn giữ một local/session handle cho quá trình drain rồi close. Cần đồng bộ trạng thái `ACTIVE → STOPPING → CLOSED` để tránh race.

### Registry của host giữ active sessions

Snippet kiến trúc:

```java
Map<String, PluginSession> active = new ConcurrentHashMap<>();

// Start: thêm session đang hoạt động
active.put(pluginId, session);

// Stop: ngăn request mới trước, drain tasks rồi:
PluginSession old = active.remove(pluginId);
if (old != null) {
    old.close();
}
```

Đây là **snippet**, không phải program độc lập: cần khai báo types/variables và chính sách chặn request/drain phù hợp. Không giữ session đã remove trong một `List<PluginSession> oldSessions` static “để debug” mãi; điều đó tái tạo leak theo đường khác.

**Một cache có thể dùng strong references miễn vòng đời của nó được giới hạn và dọn rõ ràng.** Không bắt buộc mọi cache phải yếu.

## 7. Bẫy WeakHashMap: khóa yếu nhưng giá trị giữ loader sống

`WeakHashMap<K,V>` giữ **keys qua weak references**, nhưng **values qua strong references**. Tài liệu Java SE 17 đặc biệt cảnh báo: nếu value có đường mạnh **trực tiếp hoặc gián tiếp** quay về key, key sẽ không bị GC bỏ đi.

Ví dụ nguy hiểm:

```java
static final Map<ClassLoader, Class<?>> CACHE =
        new WeakHashMap<>();

CACHE.put(pluginLoader, pluginLoader.loadClass("plugin.Greeter"));
```

Đây là snippet với variables/imports phù hợp. Map static của host chứa:

```text
Host static WeakHashMap
    |
    +-- weak key ----> pluginLoader
    |
    +-- STRONG value -> plugin.Greeter.class
                             |
                             v
                      defining pluginLoader
```

Dù key yếu, **value** là `Class<?>` của class do chính loader ấy định nghĩa, nên giá trị có thể giữ loader key còn strongly reachable. Entry không tự biến mất như bạn kỳ vọng.

Tương tự:

```java
Map<ClassLoader, Method> methods = new WeakHashMap<>();
methods.put(pluginLoader, pluginMethod);
```

`Method` liên hệ với declaring class, có thể kéo theo defining loader. Nếu map sống cùng host, “đổi HashMap thành WeakHashMap” **không tự sửa** mọi classloader leak.

### Nếu value chỉ là String thì sao?

`WeakHashMap<ClassLoader, String>` với giá trị không giữ lại key hoặc plugin graph có thể phù hợp trong một số bài toán. Nhưng vẫn phải xét:

- Tập các other strong references đến key.
- `WeakHashMap` không thread-safe mặc định.
- Cleanup xảy ra phụ thuộc GC; không có deadline deterministic.
- Không dùng weak-key cache để cam kết business correctness/lifecycle shutdown.

Dùng weak keys chỉ khi **thật sự cần semantic weak ownership** và đã kiểm tra không có đường strong reference ngược từ value tới key.

### WeakReference cho value có tự động giải quyết mọi vấn đề?

Có thể thử:

```java
Map<ClassLoader, WeakReference<Class<?>>> cache =
        new WeakHashMap<>();
```

Nhưng đây vẫn chỉ là **snippet kiến trúc**. Value cũng yếu có thể tránh một đường giữ root, song giá trị cache có thể bị GC bất cứ lúc nào, khiến hit/miss không ổn định. Từ `ref.get()` nếu nhận non-null, cần giữ referent trong strong local trong suốt thao tác sử dụng. Phải xét concurrency, key identity, stale entries và cleanup. Không dùng weak refs như một công cụ ép unload.

**Với plugin có lifecycle rõ, per-session strong cache + explicit teardown thường dễ hiểu và kiểm soát hơn** một mạng weak maps phức tạp.

## 8. ClassValue: metadata gắn với Class<?> thay vì global Map<Class<?>, V>

`java.lang.ClassValue<T>` giúp gắn một giá trị tính toán lười (*lazy computed value*) với một runtime `Class<?>`. Nó hữu ích cho per-class metadata, dispatch tables hoặc thông tin reflection, và tránh việc tự xây một static map global keyed bằng `Class<?>` mà có thể pin plugin classes.

Ví dụ Java 17 độc lập — file `ClassValueDemo.java`:

```java
import java.lang.reflect.Method;

public final class ClassValueDemo {
    private static final ClassValue<Integer> PUBLIC_METHOD_COUNT =
            new ClassValue<>() {
                @Override
                protected Integer computeValue(Class<?> type) {
                    return type.getMethods().length;
                }
            };

    public static void main(String[] args) {
        Class<?> type = String.class;
        int a = PUBLIC_METHOD_COUNT.get(type);
        int b = PUBLIC_METHOD_COUNT.get(type);

        System.out.println("Same computed value: " + (a == b));
        System.out.println("Nonnegative method count: " + (a >= 0));

        PUBLIC_METHOD_COUNT.remove(type);
        int afterRemove = PUBLIC_METHOD_COUNT.get(type);
        System.out.println("Recomputed value is nonnegative: "
                + (afterRemove >= 0));
    }
}
```

Biên dịch/chạy:

```bash
javac ClassValueDemo.java
java ClassValueDemo
```

Stdout xác định:

```text
Same computed value: true
Nonnegative method count: true
Recomputed value is nonnegative: true
```

Chọn ví dụ `Integer` và so sánh giá trị số, không dựa vào identity của Integer wrappers hay số lượng public methods cụ thể của `String` vốn có thể thay đổi theo JDK.

**Các giới hạn cần hiểu:**

1. `ClassValue.get(type)` tính/lấy value gắn với **runtime class identity**, không chỉ binary name.
2. `computeValue` có thể được gọi nhiều lần trong race; API bảo đảm một value được chọn khi cài đặt, **không hứa mọi compute chỉ chạy một lần**.
3. `remove(type)` xóa association để lần `get` sau có thể tính lại; không phải lệnh unload class.
4. `ClassValue` không tự biến một metadata value thành an toàn để chia sẻ ngoài loader boundary.
5. Nếu value hoặc class token được giữ ở **một global cache khác**, ClassValue không sửa được đường strong reference bên ngoài đó.
6. Không cache `Method`/MethodHandle/`Class<?>` do plugin định nghĩa thêm trong static maps khác mà quên lifecycle.

Dùng `ClassValue` khi **cache thực sự là thuộc tính của class**. Dùng per-session cache khi logic phụ thuộc plugin configuration, version, permissions hoặc lifecycle riêng.

## 9. Chọn khóa cache đúng class identity, không chỉ dùng getName()

Một loader generation A và B có thể cùng định nghĩa `plugin.Service`:

```text
("plugin.Service", LoaderA) != ("plugin.Service", LoaderB)
```

Nếu cache đặt tại host:

```java
Map<String, Method> cache = new ConcurrentHashMap<>();
cache.put(method.getDeclaringClass().getName() + "#run", method);
```

Snippet này không phân biệt loader A/B, và value `Method` có thể pin old loader. Ngay cả khi key mở rộng theo `pluginId`, nếu plugin v1/v2 dùng cùng pluginId, sẽ cần generation discriminator và explicit invalidation.

### Khi cache nằm trong session

Nếu session chỉ sở hữu đúng một loader thế hệ và được dọn khi stop, binary name có thể là một phần của key; scope đã cung cấp identity. Tuy nhiên method overload phải xét parameter types:

```java
record MethodKey(
    Class<?> declaringClass,
    String methodName,
    List<Class<?>> parameterTypes) {}
```

Đây là type declaration minh họa cần `import java.util.List`. Các `Class<?>` keys giữ mạnh runtime classes — **được phép trong session đang active**, nhưng không nên giữ trong một static map vô hạn.

### Cache lookup vs cache compiled metadata

Nếu computed metadata độc lập instance và thuộc về runtime class, cân nhắc `ClassValue`. Nếu metadata phụ thuộc application configuration, locale, plugin version hoặc tenant, key phải bao gồm các dimensions ảnh hưởng kết quả; không lấy `Class<?>` làm khóa duy nhất khi kết quả thực ra phụ thuộc nhiều tham số.

**Cache sai key có thể làm sai chức năng ngay cả khi không có memory leak.**

## 10. Caching “không tìm thấy class” là một trường hợp đặc biệt

Một số hệ plugin cache kết quả âm để tránh mỗi request lại quét JAR:

```java
Set<String> notFound = ConcurrentHashMap.newKeySet();
```

Snippet này cần imports và nằm trong class. Negative caching chỉ đúng trong **source snapshot cố định** với lookup policy cố định.

Nếu plugin directory/ModuleLayer/classpath được cập nhật, tên trước đây không có có thể trở thành có. Global negative cache có thể khiến hệ thống báo `ClassNotFoundException` mãi dù artifact đã triển khai. Ngược lại, một cache dương có thể giữ class của version cũ sau reload.

Quy tắc:

- Gắn negative cache với **plugin generation**.
- Khi version/artifact/finder/layer thay đổi, bỏ negative cache cũ.
- Không cache mọi lỗi như “không tìm thấy”: `LinkageError`, `SecurityException`, initialization failure và dependency failure có semantics khác.
- Nếu dùng TTL, nhớ rằng TTL không thay lifecycle event: khi stop/reload phải invalidate ngay, không chờ thời gian trôi hết.
- Nếu loader không thực sự đọc lại dynamic sources trong cùng generation, thiết kế một **immutable snapshot** sẽ khiến negative caching dễ lý giải hơn.

## 11. TCCL, thread pools và ThreadLocal là những cache roots không rõ ràng

Dù session cache đã xóa, loader có thể vẫn còn sống vì worker thread giữ **thread context class loader (TCCL)**:

```text
Long-lived Executor worker
   -> Thread.contextClassLoader
   -> Old PluginClassLoader
```

Hoặc:

```text
Worker Thread
   -> ThreadLocalMap.value
   -> plugin-specific context
   -> plugin class
   -> plugin loader
```

Đổi TCCL ở thread submit **không nhất thiết** đổi TCCL của worker có sẵn trong pool. Nếu một framework bắt buộc sử dụng TCCL, phải đặt/restore **trong đúng worker**:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    invokeLegacyFramework();
} finally {
    thread.setContextClassLoader(old);
}
```

Đây là snippet minh họa, cần `pluginLoader` và `invokeLegacyFramework()` trong scope. Không dùng `setContextClassLoader(null)` như một cách reset mặc định; phải restore chính giá trị `old`.

Với `ThreadLocal`, gọi `remove()` trong `finally` của chính worker thread trước khi trả worker cho pool. Việc key `ThreadLocal` yếu không làm value trở thành yếu; một value plugin sống trong worker lâu dài vẫn có thể pin loader.

### Async task sau khi session đóng

Một callback bị giữ trong queue có thể chứa lambda class/closure được định nghĩa bởi plugin loader, hoặc capture plugin object. Thậm chí registry entry chính đã xóa, scheduled task còn tồn tại vẫn có thể giữ old generation sống.

**Lifecycle cache và lifecycle tác vụ cần phối hợp**: stop nhận việc mới, cancel scheduled tasks, drain in-flight work, unregister listeners/callbacks, dọn ThreadLocals và TCCL, sau đó dọn caches/loader.

## 12. ServiceLoader, proxy, reflection và MethodHandle

Các framework thường cache metadata đa dạng:

| Loại cached value | Có thể giữ gì? | Gợi ý scope |
|---|---|---|
| `ServiceLoader<S>` | Service/provider metadata và instances, loader/layer tùy cấu hình | Theo plugin/provider registry, không cache vô hạn theo TCCL |
| `Method` / `Constructor` / `Field` | Declaring class và related metadata | Per-class `ClassValue` hoặc per-session |
| `MethodHandle` / `MethodHandles.Lookup` | Method/type/access context | Per-session hoặc per-class theo ownership |
| Dynamic proxy class/instance | Interface types, invocation handler, defining loader | Không để singleton host giữ proxy của plugin cũ |
| Lambda/callback | Captured objects/instances và classes | Unregister/cancel khi plugin dừng |
| Serializer/deserializer compiled cho private DTO | Runtime class metadata | Per-class/per-session, không global unbounded |
| `URLClassLoader` | JAR/resource handles và class loader object | Đóng khi hết công việc; bỏ strong references |

Một `ServiceLoader.load(Plugin.class)` sử dụng TCCL, trong khi overload `ServiceLoader.load(Plugin.class, chosenLoader)` cho phép chọn loader rõ ràng. Với plugin registry đã biết loader, nên hạn chế dependency vào TCCL ngầm.

Nếu muốn cache provider, cache trong **session/layer có lifecycle**, chứ không giữ `ServiceLoader` của plugin v1 trong host singleton sau khi đã reload v2.

## 13. Một cache yếu không thay được lifecycle quản lý resources

`WeakReference` và `ReferenceQueue` giúp theo dõi khả năng GC, nhưng chúng không tự gọi `URLClassLoader.close()` đúng thời điểm hay chấm dứt thread đang chạy.

Ví dụ thông tin quan sát:

```java
WeakReference<ClassLoader> weak = new WeakReference<>(loader);
```

Snippet cần import `java.lang.ref.WeakReference` và loader variable. Nếu có strong reference khác, `weak.get()` vẫn có thể trả loader. Nếu `weak.get() == null`, collector đã xử lý referent theo weak-reference semantics; **không bảo đảm class-unload log hoặc RSS giảm ngay**.

Đừng viết test dựa trên:

```java
System.gc();
if (weak.get() != null) {
    throw new AssertionError("Leak!");
}
```

`System.gc()` là yêu cầu, không phải một cam kết collector đã reclaim loader. Một lần `get() != null` không chứng minh leak; JVM có thể chưa collect.

Nếu dùng `WeakReference.get()` để thao tác:

```java
ClassLoader alive = weak.get();
if (alive != null) {
    // Dùng alive ngay trong phạm vi strong local này.
    java.lang.ref.Reference.reachabilityFence(alive);
}
```

Đoạn này minh họa: `alive` không được lưu vào host cache vô thời hạn; `reachabilityFence` bảo đảm reachability qua điểm fence theo contract. Nó không thay lifecycle owner.

### WeakReference là công cụ quan sát, không là nguồn chân lý duy nhất

Khi một loader được thu gom, Java API không cho một “sự kiện unload class” đồng bộ, portable cho mọi JVM. Kết hợp weak reference monitoring với GC/class-unload logs, classloader statistics và heap reference graph phù hợp.

Nếu dùng `Cleaner` để dọn tài nguyên, cẩn thận action **không capture chính referent** hoặc plugin instance/loader, nếu không có thể lại giữ nó sống. Với `URLClassLoader`, nên đóng chủ động theo lifecycle thay vì chỉ trông chờ cleaner/finalization.

## 14. ClassValue, WeakHashMap và per-session map: so sánh thực dụng

| Thiết kế | Ưu điểm | Rủi ro/cần nhớ | Khi nào phù hợp |
|---|---|---|---|
| Static `Map<String, Class<?>>` | Lookup đơn giản | Sai key giữa loaders, giữ old Class/loader | Tránh cho plugin-private classes |
| Static `Map<Class<?>, Method>` | Identity key chính xác | Key và value mạnh → pin plugin | Tránh nếu không có eviction theo lifecycle |
| Static `WeakHashMap<ClassLoader, Class<?>>` | Key yếu | Value Class trỏ gián tiếp về key → pin loader | **Thường không đúng** khi value là class của key |
| `WeakHashMap<ClassLoader, WeakReference<V>>` | Hạn chế giữ mạnh value | GC nondeterministic, phức tạp race/cleanup | Chỉ khi weak semantics thực sự được thiết kế |
| `ClassValue<V>` | Tự gắn value với runtime Class identity | Không giải quyết roots nằm trong cache khác, compute có race | Per-class derived metadata |
| `PluginSession` + `HashMap`/`ConcurrentHashMap` | Lifecycle rõ, lookup nhanh, dễ test | Phải đóng/clear đúng lúc và đồng bộ in-flight | **Lựa chọn mặc định tốt** cho nhiều plugin systems |
| Host bounded cache với explicit eviction | Có giới hạn số entries | Eviction không đồng nghĩa ngừng plugin; key/value vẫn phải đúng | Shared, non-plugin metadata hoặc cache có versioned ownership |

**Không có lựa chọn nào mặc nhiên đúng cho mọi workload.** Trước tiên chọn ownership/lifecycle; sau đó mới chọn collection type và concurrency policy.

## 15. Concurrency: race giữa cache hit, lookup và close

Nếu request R1 đang lookup method trong session thì R2 ra lệnh stop plugin, có thể xảy ra:

```text
R1: đọc session ACTIVE
R2: đặt session STOPPING
R2: clear cache và close loader
R1: cố findClass từ JAR đã close
R1: ClassNotFoundException hoặc behavior không như mong muốn
```

Java SE 17 `URLClassLoader.close()` ghi rõ: khi thread khác đang load class đồng thời với `close`, **kết quả class loading là không xác định** theo contract. Do đó đơn thuần dùng `ConcurrentHashMap` không đủ để bảo vệ lifecycle.

Một thiết kế production có thể dùng:

1. Một state machine `ACTIVE / STOPPING / CLOSED`.
2. Bộ đếm active operations hoặc read–write lock.
3. Khi stop: ngăn mở operations mới, chờ operations đã bắt đầu kết thúc.
4. Hủy/cancel scheduled work, xóa caches và đóng loader.
5. Gỡ khỏi registry và thả references.

**Không nên giữ một global lock** cho mọi plugin khi chỉ cần serialize stop/lookup trong cùng plugin session. Với cached `Method`, nếu value đã được trả về một worker, clear map **không thu hồi reference mà worker đang giữ**; cần drain worker trước.

### Có cần ConcurrentHashMap.computeIfAbsent?

Dùng được khi mapping function không tạo side effects nguy hiểm và exception behavior phù hợp. `getMethod`/`Class.forName` ném checked exceptions nên cần wrapper/synchronization hợp lý thay vì nuốt lỗi hoặc biến mọi failure thành `null`.

Một `ConcurrentHashMap` keyed theo `MethodKey` vẫn giữ strong keys/values. Nó sửa **thread safety**, không sửa **classloader retention** nếu đặt trong host singleton sống vô hạn.

## 16. Đo hiệu năng trước khi cache

Chi phí của một cache không chỉ là thời gian lookup class:

- **Cache hit rate**: bao nhiêu lượt thật sự reuse metadata?
- **Miss cost**: reflective lookup/annotation parsing/method handle creation tốn bao nhiêu?
- **Memory footprint**: bao nhiêu `Class<?>`, `Method`, metadata objects và plugin generations bị giữ?
- **Invalidation cost**: có xóa chính xác entry khi plugin reload không?
- **Concurrency**: lock contention, racing computations, publish visibility có ảnh hưởng?
- **Cold start**: cache warm-up có tạo nhiều classes/proxies không cần?
- **Lifecycle effects**: Metaspace có tăng qua 100 lần reload mặc dù active plugins không đổi?

Nếu class loading đã được VM cache, tạo thêm một global map cho `ClassLoader.loadClass` có thể chỉ thêm chi phí và leak. Chỉ tối ưu sau khi profiler/JMH hoặc benchmark thực tế chứng minh bottleneck.

**Không dùng `System.nanoTime` đo một lần gọi cold reflection rồi suy ra “cache nhanh hơn X lần”**: JIT, warm-up, GC và class initialization có thể gây sai lệch lớn. Với workload thực, đo cả p95/p99 latency và memory retention theo chu kỳ deploy.

## 17. Quan sát Metaspace và class unloading

Để đánh giá **cache có pin loader hay không**, thử nhiều vòng start/stop/reload với số plugin active không đổi. Nếu sau khi quiesce vẫn còn class loaders của các generations cũ, điều tra **retaining path từ host static map, `Method`/`Class<?>`, `ServiceLoader`, TCCL hoặc queued tasks**. Một cache sai lifetime thường hiện ra là chuỗi root → cached value → declaring class → defining loader.

Trên HotSpot JDK 17 có thể xem `-Xlog:class+unload=info`, `jcmd PID VM.classloader_stats`, JFR, heap dump và Metaspace used/committed. Ví dụ session rất ngắn có thể kết thúc **không có unload event**: close/clear tạo điều kiện, nhưng JVM không cam kết GC/unload đúng thời điểm. Đừng dùng một lần `System.gc()` hay WeakReference check để kết luận leak.

Muốn chứng minh bản sửa cache có hiệu quả, so cùng workload nhiều generations trước/sau, log cache entries bị xóa, current loaded classes, số old loaders reachable và heap **path to GC root**. Metaspace committed hoặc RSS có thể không giảm lập tức dù metadata đã được reclaimed; tránh kết luận chỉ từ một metric.

## 18. Vấn đề ClassLoader.close và ClassValue.remove

**`URLClassLoader.close()` không phải “dỡ tất cả class ngay”**. JDK 17 mô tả rằng các classes/resources đã load vẫn có thể sử dụng sau close; close chủ yếu dừng tìm mới từ URLs và đóng các tài nguyên mở. Nếu host còn giữ `Method`/instance thì class/loader có thể tiếp tục reachable.

**`ClassValue.remove(clazz)` không phải “yêu cầu unload clazz”**. Nó chỉ gỡ association của đúng ClassValue cho clazz. Nếu clazz còn reachable qua host map hoặc static field, loader có thể tiếp tục sống.

**Xóa một `HashMap` cũng không bảo đảm hết roots khác**: worker có thể đang giữ Method trong local, listener registry giữ plugin object, TCCL giữ loader, `ModuleLayer` có thể đang được host quản lý, hoặc service provider cache còn reference.

**Dọn theo lifecycle là điều kiện thiết kế để có cơ hội GC, không phải API bảo đảm unloading**.

## 19. Checklist review cache ở ranh giới plugin

- [ ] Cache nằm trong đúng plugin session/generation hoặc có eviction rõ ràng.
- [ ] Không có static host cache giữ `Class<?>`/`Method` của plugin không giới hạn.
- [ ] Key phân biệt đúng runtime `Class<?>` identity; không chỉ dùng binary name khi nhiều loaders cùng tồn tại.
- [ ] Có metrics hits/misses/size để biết cache có đáng tồn tại hay không.
- [ ] Không dùng `WeakHashMap` một cách mù quáng khi value có thể tham chiếu về key/loader.
- [ ] Nếu dùng `ClassValue`, metadata thật sự là per-class và không được lưu strong ra global map khác.
- [ ] Khi reload, cache/negative cache của thế hệ cũ bị bỏ.
- [ ] Stop plugin chặn task mới, drain active tasks, unregister listeners/jobs rồi clear/close.
- [ ] ThreadLocal được `remove()` đúng thread; TCCL được restore trong `finally`.
- [ ] `ServiceLoader`/provider registry và reflection/proxy caches được giải phóng theo owner.
- [ ] Concurrent lookup và close không được race trên `URLClassLoader`.
- [ ] Có regression test cho nhiều chu kỳ start/stop/reload và kiểm tra old loader roots.
- [ ] Không dùng `System.gc()` hoặc một lần WeakReference.get để quyết định test pass/fail về unload.
- [ ] Đã tham khảo ClassLoader, WeakHashMap và ClassValue contract của đúng JDK.

## 20. Các lỗi tư duy thường gặp

| Quan niệm sai | Cách hiểu đúng |
|---|---|
| “Cache bằng String name là đủ.” | Runtime type identity còn có defining loader; cùng tên có thể là hai classes. |
| “ClassLoader.loadClass luôn định nghĩa lại class.” | Mặc định kiểm tra class đã loaded và có thể trả cùng `Class<?>`. |
| “WeakHashMap dùng khóa yếu nên không thể leak loader.” | Value được giữ mạnh và có thể trỏ ngược tới loader key. |
| “Method không giữ Class<?>.” | Reflection metadata liên hệ với declaring class; cần xét reachability. |
| “Clear map đồng nghĩa loader đã unload.” | Chỉ gỡ một tập references; JVM GC/unloading độc lập. |
| “URLClassLoader.close sẽ dỡ class ngay.” | Close resources/lookup không bằng unload class. |
| “Đổi plugin version nhưng cache cùng tên vẫn hợp lệ.” | Generation mới có loader/type identity mới. |
| “ConcurrentHashMap sửa được classloader leak.” | Nó sửa thread safety, không tự thay key/lifecycle semantics. |
| “TTL 10 phút là đủ để stop plugin.” | Stop phải invalidate theo lifecycle, không chờ timer nếu còn pin resources. |
| “ClassValue bảo đảm mọi reference của plugin được dọn.” | Nó chỉ quản lý association per-class; cache roots ngoài vẫn tồn tại. |
| “Phải dùng weak reference mọi chỗ mới an toàn.” | Per-session strong cache + explicit cleanup thường đơn giản hơn. |
| “Không có unload event trong một test ngắn nghĩa leak.” | GC/class unloading là nondeterministic và phụ thuộc nhiều roots. |
| “Host giữ parent loader nên child bắt buộc còn sống.” | Child thường giữ parent; parent không mặc nhiên giữ child. |
| “Một plugin hết requests tức là threads/lambdas đã hết.” | Worker queues, callbacks và ThreadLocal còn có thể giữ loader. |

## 21. Bài tập tự kiểm tra

**Câu 1.** Host có static `Map<String, Class<?>>` lưu `plugin.Worker` của phiên bản cũ. Plugin đã được stop và biến loader local = null. Loader cũ đủ điều kiện reclaim chưa?

**Đáp án:** Chưa thể kết luận đủ điều kiện; static map còn giữ `Class<?>` của plugin, có thể giữ defining loader reachable. Phải xóa entry và các roots khác.

**Câu 2.** Dùng `WeakHashMap<ClassLoader, Method>` là đủ vì key weak?

**Đáp án:** Không. Value `Method` có thể giữ declaring class → defining loader quay lại key; value được WeakHashMap giữ mạnh.

**Câu 3.** Vì sao `ClassLoader.loadClass` nhiều lần không bắt buộc tạo nhiều runtime classes?

**Đáp án:** Mặc định loader kiểm tra class đã được nạp và trả lại nếu phù hợp. Cache Class<?> global có thể là tối ưu thừa.

**Câu 4.** Hai plugin loaders định nghĩa cùng binary name `plugin.Service`. Cache key chỉ dùng `"plugin.Service"` có an toàn không?

**Đáp án:** Không nếu cache dùng chung. Key thiếu loader/runtime class identity, có nguy cơ trả sai class generation.

**Câu 5.** `ClassValue` khác `static Map<Class<?>, Metadata>` chủ yếu ở đâu?

**Đáp án:** ClassValue cung cấp association gắn với runtime class, tránh giữ per-class data qua một map key mạnh global tự quản. Tuy nhiên không chữa được strong roots khác và phải hiểu `computeValue` concurrency.

**Câu 6.** `ClassValue.remove(clazz)` có unload class đó không?

**Đáp án:** Không. Nó chỉ xóa associated value của ClassValue; unloading phụ thuộc defining loader reachability và quyết định VM.

**Câu 7.** Tại sao phải drain in-flight tasks trước `URLClassLoader.close()`?

**Đáp án:** Concurrent class load khi close có kết quả không xác định theo contract; worker còn giữ plugin instances/metadata cũng cản cleanup.

**Câu 8.** Cache `ClassNotFoundException` hoặc trạng thái “không thấy tên này” qua các plugin versions có rủi ro gì?

**Đáp án:** Artifact/snapshot mới có thể chứa tên đó; cache âm cũ sẽ đưa ra kết quả stale. Invalidate theo generation/source change.

**Câu 9.** Dùng weak reference để kiểm tra loader có leak sau một lần `System.gc()`, kết quả `weak.get() != null` đủ chứng minh leak chưa?

**Đáp án:** Chưa. GC/unloading không có bảo đảm diễn ra đúng thời điểm; cần phân tích GC-root paths và nhiều chu kỳ lifecycle.

**Câu 10.** Vì sao trong demo `Same cached Method` là true và `Reflection cache misses` là 1?

**Đáp án:** Hai lookup dùng cùng MethodKey trong một PluginSession, nên lần đầu tạo entry, lần sau nhận lại chính Method instance.

**Câu 11.** TCCL còn là plugin loader cũ trên worker thread sau reload có tác dụng gì?

**Đáp án:** Worker còn sống có thể giữ old loader strongly reachable, dù session cache đã clear. Restore TCCL đúng worker trong finally.

**Câu 12.** Cache Method/MethodHandle của plugin nên tồn tại trong host singleton suốt tiến trình không?

**Đáp án:** Chỉ khi có ownership/eviction rõ ràng và không giữ thế hệ plugin đã hết hạn; mặc định per-plugin session là thiết kế dễ quản lý hơn.

## 22. Ghi nhớ và tài liệu chính thức

**Năm kết luận trọng tâm:**

1. **Cache đúng scope trước khi tối ưu collection**: per-plugin/per-generation cache có strong references là bình thường nếu được clear và không còn root ngoài khi stop.
2. **Sai cache key vừa gây lỗi logic vừa gây leak**: class name không đủ phân biệt defining loader, còn Method/Class token có thể giữ loader cũ.
3. **WeakHashMap không là thuốc chữa tự động**: value mạnh có thể tham chiếu về weak key qua Class<?> hoặc Method.
4. **ClassValue hợp với per-class metadata**, nhưng không thay lifecycle plugin và không xóa root references từ host caches/threads.
5. **Close + clear + unregister + drain tạo cơ hội reclaim**, không bảo đảm class unload ngay; phải quan sát GC roots và Metaspace theo nhiều chu kỳ.

**Nguồn chính thức Java 17:**

- [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, parent delegation.
- [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): classpath URL, `close` và concurrency caveats.
- [WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values và vòng tham chiếu key/value.
- [ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): `computeValue`, `get`, `remove`.
- [WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability.
- [Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): bảo đảm reachability khi dùng referent.
- [JLS 17 `12.7 — Unloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): điều kiện unload theo defining loader.
- [JVMS 17 `5 — Loading/Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity và loading.
- [Java SE 17 java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+unload` và chẩn đoán JVM.