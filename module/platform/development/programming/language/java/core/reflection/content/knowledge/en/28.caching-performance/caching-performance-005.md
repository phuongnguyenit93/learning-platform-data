# Cache giữ `Class` có thể giữ cả class loader: vòng đời metadata Reflection trong Java

## 1. Vấn đề: cache giúp nhanh hơn nhưng có thể giữ plugin trong bộ nhớ

Một framework dùng Reflection thường phải tra cứu đi tra cứu lại cùng một lớp: danh sách field, method, constructor, annotation, bộ ánh xạ dữ liệu, `MethodHandle` hoặc cấu hình serialization. Cache các kết quả đó giúp giảm chi phí khám phá metadata và xây dựng adapter.

Tuy nhiên, trong ứng dụng **nạp và gỡ plugin**, môi trường triển khai lại module, application server hoặc chương trình tạo nhiều class loader động, **cache sống lâu hơn class loader** có thể làm các lớp cũ không được thu hồi. Ví dụ:

~~~java
// Minh họa nguy cơ: map tĩnh sống theo toàn bộ ứng dụng.
static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();
~~~

Nếu `Class<?>` trong map là một lớp được nạp bởi loader của plugin, entry được giữ bằng tham chiếu mạnh (*strong reference*). Trong tình huống thông thường, chuỗi tham chiếu này có thể giữ `Class` và class loader định nghĩa nó còn có thể truy cập được, do đó chặn việc thu hồi class loader và các lớp do loader đó quản lý.

**Bản chất lỗi là lệch vòng đời:** thành phần cache của ứng dụng tồn tại lâu dài, trong khi plugin và các lớp do plugin nạp phải có thể được giải phóng sau khi gỡ. Điều này không có nghĩa mọi cache `Class` đều gây lỗi. Nếu mọi class tồn tại cùng vòng đời ứng dụng, cache hữu hạn có thể hoàn toàn hợp lý. Vấn đề xuất hiện khi cache **sống lâu hơn namespace nạp lớp** mà nó giữ.

Sau bài này, bạn sẽ biết cách nhận diện đường giữ tham chiếu, lựa chọn cache có phạm vi phù hợp, sử dụng `ClassValue` và weak-key cache đúng cách, kiểm chứng bằng công cụ chẩn đoán, và tránh một số sửa chữa không hiệu quả.

## 2. Nhớ lại định danh kiểu và class loader

Trong Java, **tên nhị phân chưa đủ để xác định một kiểu runtime**. Class loader định nghĩa kiểu là thành phần của danh tính kiểu. Hai lớp có cùng `getName()` nhưng được định nghĩa bởi hai loader khác nhau có thể là hai `Class<?>` khác nhau:

~~~text
Ứng dụng chính: AppClassLoader
    └── com.example.PluginApi       → Class A

Plugin được nạp riêng: PluginClassLoader
    └── com.example.PluginApi       → Class B

A.getName().equals(B.getName())     → true
A == B                              → false
~~~

Đây là tình huống minh họa, không phải hai định nghĩa cùng package trong một mã nguồn độc lập. Trong chương trình thật, cần xem loader có **ủy quyền cho cha** hay **tự định nghĩa lớp**. Một loader con có thể trả về `Class` đã được loader cha định nghĩa; điều này không tạo ra một kiểu mới.

Class unloading là khả năng của JVM trong quá trình quản lý bộ nhớ: theo Java Language Specification, một lớp/interface **có thể** được unload khi class loader định nghĩa nó có thể được GC thu hồi. Việc class thực sự được unload và thời điểm thực hiện là quyết định của JVM; ứng dụng không được dựa vào việc class unloading xảy ra ngay lập tức.

Hai điểm cần phân biệt:

- **Đối tượng `Class<?>` là metadata gateway của một kiểu cụ thể.** Nếu mã ngoài plugin giữ mạnh đối tượng này, loader định nghĩa lớp có thể tiếp tục bị giữ.
- **Class loader còn sống** có thể giữ nhiều thứ hơn một lớp: metadata của các lớp được nạp, liên kết giữa chúng, các đối tượng liên quan. Vì thế một entry nhỏ trong cache có thể làm phần bộ nhớ đáng kể không được thu hồi.

## 3. Đường tham chiếu gây giữ class loader

Ví dụ cache nằm trong một class của ứng dụng chính, thường tồn tại đến cuối chương trình:

~~~text
GC Root: Class/static field của ứng dụng chính
      ↓
ConcurrentHashMap (cache tồn tại lâu)
      ↓
entry: key là Class<?> của plugin       [strong]
      ↓
Class metadata / runtime type
      ↓
defining PluginClassLoader
      ↓
các lớp/metadata liên quan của plugin
~~~

Đây là **sơ đồ khái niệm về khả năng truy cập**, không phải mô tả bắt buộc từng cạnh nội bộ của mọi JVM. Khi phân tích heap dump, đường tham chiếu có thể chứa những đối tượng trung gian và cạnh khác với sơ đồ trên.

Một số dạng giữ mạnh dễ gặp:

- `Map<Class<?>, ...>`, `Set<Class<?>>` hoặc danh sách `Class<?>` nằm trong singleton, static registry.
- `Map<String, Method>` hoặc `Map<String, Field>`. **Key là `String` không loại bỏ nguy cơ** nếu value là đối tượng Reflection tham chiếu tới lớp khai báo của plugin.
- Cache chứa `Constructor<?>`, `MethodHandle`, `MethodType`, `CallSite`, factory, lambda, instance của plugin hoặc một object có field tham chiếu các thành phần đó.
- Cấu trúc không trực tiếp giữ `Class` nhưng value chứa class, class loader, đối tượng plugin hoặc dữ liệu `ThreadLocal` còn sống trong thread pool.
- Thread còn chạy có **thread context class loader (TCCL)** trỏ tới plugin loader sau khi plugin đã ngừng sử dụng.

Vì vậy, chẩn đoán phải hỏi **ai còn giữ mạnh cái gì, và giữ lâu đến đâu**, thay vì chỉ tìm các biến có tên `CACHE`.

## 4. Ví dụ Java 17+ chạy độc lập: cùng tên, hai loader, một cache mạnh

Ví dụ tạo hai đối tượng `Class` cho một tên, trong đó class thứ hai được một loader con **tự định nghĩa**. Không phụ thuộc vào việc GC sẽ chạy; chương trình chỉ kiểm tra danh tính kiểu và việc cache mạnh đang chứa entry.

Tạo tệp `ClassCacheLifetimeDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ClassCacheLifetimeDemo {
    record Metadata(String binaryName, int methodCount) {}

    static final Map<Class<?>, Metadata> STRONG_CACHE =
            new ConcurrentHashMap<>();

    static final ClassValue<Metadata> CLASS_METADATA = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            return new Metadata(
                    type.getName(), type.getDeclaredMethods().length);
        }
    };

    // Chỉ với tên PluginPayload, loader này tự định nghĩa lớp.
    static final class IsolatedLoader extends ClassLoader {
        private final String isolatedName;

        IsolatedLoader(ClassLoader parent, String isolatedName) {
            super(parent);
            this.isolatedName = isolatedName;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(isolatedName)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent()
                            .getResourceAsStream(resource)) {
                        if (in == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = in.readAllBytes();
                        result = defineClass(
                                name, bytes, 0, bytes.length);
                    } catch (IOException ex) {
                        throw new ClassNotFoundException(name, ex);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> hostType = PluginPayload.class;
        ClassLoader pluginLoader = new IsolatedLoader(
                hostType.getClassLoader(), hostType.getName());
        Class<?> pluginType = Class.forName(
                hostType.getName(), false, pluginLoader);

        System.out.println("same name: "
                + hostType.getName().equals(pluginType.getName()));
        System.out.println("same Class: " + (hostType == pluginType));
        System.out.println("defined by child: "
                + (pluginType.getClassLoader() == pluginLoader));

        Metadata data = new Metadata(
                pluginType.getName(),
                pluginType.getDeclaredMethods().length);
        STRONG_CACHE.put(pluginType, data);
        System.out.println("strong entries: " + STRONG_CACHE.size());

        Metadata fromClassValue = CLASS_METADATA.get(pluginType);
        System.out.println("ClassValue result: "
                + fromClassValue.binaryName().equals(pluginType.getName()));

        // Chủ động bỏ tham chiếu do ứng dụng giữ trong map.
        STRONG_CACHE.remove(pluginType);
        System.out.println("strong entries after remove: "
                + STRONG_CACHE.size());
    }
}

// Cùng tệp nguồn: javac tạo thêm PluginPayload.class.
class PluginPayload {
    public int answer() {
        return 42;
    }
}
~~~

Lệnh chạy (đứng trong thư mục ghi tệp):

~~~bash
javac ClassCacheLifetimeDemo.java
java ClassCacheLifetimeDemo
~~~

Kết quả xác định:

~~~text
same name: true
same Class: false
defined by child: true
strong entries: 1
ClassValue result: true
strong entries after remove: 0
~~~

**Giải thích:**

1. `PluginPayload.class` là kiểu do loader thông thường của ứng dụng thấy. `IsolatedLoader` tự đọc bytecode và gọi `defineClass` cho **chính tên `PluginPayload`**, nên `pluginType` khác `hostType` dù tên bằng nhau.
2. Entry `STRONG_CACHE.put(pluginType, data)` giữ mạnh đối tượng `Class` làm khóa khi map còn sống. Nếu mã này là một registry tồn tại lâu dài, entry có thể giữ loader/plugin cũ.
3. `ClassValue.get(pluginType)` tạo metadata gắn **theo đúng `Class<?>`**, phù hợp cho dữ liệu tính một lần theo từng kiểu.
4. `STRONG_CACHE.remove(pluginType)` bỏ tham chiếu **của map**. Các biến local `pluginType`, `pluginLoader`, metadata và các tham chiếu JVM khác có thể vẫn tồn tại trong thời gian chương trình chạy. **Không được suy ra loader đã unload** chỉ từ `size() == 0`.

Chương trình này minh họa cơ chế và quyền sở hữu cache; nó **không dùng `System.gc()`, `finalize()` hoặc thời gian chờ** để tạo một kết quả GC không đáng tin. `IsolatedLoader` là công cụ học tập, không phải loader plugin production đã xử lý đầy đủ resource, security và module boundaries.

## 5. Tại sao key là `Class<?>` lại khác key là tên lớp?

Xem hai cách tổ chức cache:

~~~java
Map<Class<?>, Metadata> byClass = new ConcurrentHashMap<>();
Map<String, Metadata> byName = new ConcurrentHashMap<>();
~~~

*Đây là fragment: cần `Metadata`, import `Map` và `ConcurrentHashMap` như ví dụ trên.*

### Cache theo `Class<?>`

**Ưu điểm:** tự phân biệt các kiểu có cùng tên nhưng do loader khác nhau định nghĩa; lookup theo đúng kiểu runtime; tiện cho Reflection.

**Rủi ro:** map tồn tại lâu với strong key có thể giữ lớp và loader không còn được ứng dụng sử dụng. Nếu cache không có chính sách gỡ từng plugin, dữ liệu sẽ tích tụ sau nhiều lần reload.

### Cache theo `String`

**Ưu điểm:** bản thân `String` tên lớp không nhất thiết giữ class loader. Có thể phù hợp cho nội dung độc lập với loader, chẳng hạn tên hiển thị đã chuẩn hóa.

**Rủi ro:** hai plugin có thể có lớp trùng `binaryName` nhưng khác metadata. Dùng mỗi tên làm khóa **có thể trả nhầm dữ liệu**. Hơn nữa, nếu `Metadata` bên value chứa `Class`, `Method`, `Field` hoặc instance plugin, cache `Map<String, Metadata>` vẫn có thể giữ loader. Chuyển key sang `String` không phải cách sửa tổng quát.

**Chọn key theo định danh nghiệp vụ.** Nếu cache cần một namespace của plugin, có thể tạo khóa logic `pluginId + pluginGeneration + className` (gồm phiên bản/vòng đời reload) và **xóa các entry** khi gỡ plugin. Khi dùng `Class<?>`, áp dụng phạm vi cache phù hợp hoặc giải pháp vòng đời bên dưới.

## 6. Lựa chọn 1: cache có phạm vi và xóa chủ động

Đơn giản nhất là **đưa cache vào đúng vòng đời**:

~~~text
PluginSession #42
  ├── loader
  ├── services
  └── metadata cache chỉ dùng cho session #42

Khi unload session:
  1. Ngừng các lời gọi mới, đợi công việc đang chạy hoàn tất
  2. Hủy đăng ký handler, listener, task, timer, ThreadLocal
  3. Xóa metadata cache và tham chiếu tới services/loader
  4. Đóng tài nguyên loader hỗ trợ close() nếu thích hợp
  5. Cho phép JVM tự quyết định GC và class unloading
~~~

Nếu một cache tĩnh chứa nhiều plugin, có thể tổ chức namespace theo `pluginId` và một phương thức `evictPlugin(id)`. **Phải kiểm soát đồng thời:** không nên gỡ entry trong khi request cũ còn dùng nó rồi tuyên bố plugin đã unload; cần chuyển trạng thái plugin sang dừng nhận việc mới, kết thúc những tác vụ đang chạy và hủy đăng ký các điểm giữ tham chiếu.

Dùng API cache có giới hạn kích thước hoặc thời gian sống khi mục tiêu là kiểm soát bộ nhớ tổng thể. Nhưng chính sách hết hạn **không bảo đảm** loader được gỡ đúng thời điểm nếu entry còn được truy cập, và cũng không thay thế cleanup vòng đời đối với resource khác.

**Phù hợp khi:** plugin có lifecycle rõ, module được triển khai lại, hoặc cache chứa nhiều thành phần (metadata, instance, handler) mà GC yếu không thể giải quyết yêu cầu hủy đăng ký/tài nguyên.

## 7. Lựa chọn 2: `ClassValue<T>` cho metadata theo từng `Class`

`java.lang.ClassValue<T>` là API chuẩn Java để **gắn giá trị tính lười theo từng `Class<?>`**. Đặc biệt phù hợp cho metadata phát sinh từ chính class đang xét: mapping field, thông tin serializer, descriptor dùng trong framework.

~~~java
static final ClassValue<Field[]> DECLARED_FIELDS = new ClassValue<>() {
    @Override
    protected Field[] computeValue(Class<?> type) {
        return type.getDeclaredFields();
    }
};

Field[] fields = DECLARED_FIELDS.get(SomeType.class);
~~~

*Fragment cần `import java.lang.reflect.Field;` và lớp `SomeType` tồn tại.*

Đặc điểm quan trọng:

- Giá trị được liên kết với **đúng `Class<?>`**, nên hai class cùng tên nhưng khác loader có thể nhận metadata riêng.
- `get(type)` tính dữ liệu theo nhu cầu bằng `computeValue(type)`; trong cạnh tranh nhiều thread, `computeValue` **có thể được gọi nhiều lần**, dù một giá trị được chấp nhận cho lần liên kết đó. Không thực hiện side effect không thể lặp hoặc đăng ký resource một cách vô điều kiện trong `computeValue`.
- `remove(type)` xóa liên kết của `ClassValue` cho lớp đó; lần `get` sau có thể tính lại. Đây là **invalidation metadata**, không phải lệnh dỡ lớp và cũng không loại bỏ các tham chiếu mà code bên ngoài đang giữ.
- Khác với một `static Map<Class<?>, V>` nằm ở ứng dụng, `ClassValue` được thiết kế để gắn giá trị với đời sống của `Class` mà không cần dùng một bản đồ global giữ mạnh khóa kiểu theo cách thông thường. Nó giúp tránh **một nguồn** giữ loader; không đảm bảo unloading nếu nơi khác vẫn giữ class, loader hoặc giá trị.

Nếu `Field[]` trong ví dụ là mảng cache, **đừng cho code gọi sửa trực tiếp mảng chung** nếu điều đó ảnh hưởng đến các thành phần khác; trả bản sao hoặc metadata bất biến khi cần. `ClassValue` bảo đảm cơ chế liên kết, **không bảo đảm object giá trị là immutable hoặc thread-safe**.

Cũng cần phân biệt `ClassValue` với `ThreadLocal`: `ClassValue` liên kết theo **class**, không theo thread. Đây thường là lợi thế đối với metadata dùng chung giữa nhiều luồng; việc đồng bộ nội bộ giá trị vẫn là trách nhiệm của thiết kế.

**Phù hợp khi:** dữ liệu được tính từ một class, truy cập lặp lại, nên giữ theo vòng đời class và không cần quét danh sách mọi entry để xuất báo cáo.

## 8. Lựa chọn 3: `WeakHashMap<Class<?>, V>` — cần kiểm tra cả value

`WeakHashMap` lưu **key bằng weak reference**. Khi key không còn được tham chiếu mạnh từ nơi khác, GC có thể thu hồi nó và entry sẽ được loại bỏ. Đây là lựa chọn có thể cân nhắc cho một số cache, nhưng có một bẫy lớn: **value của `WeakHashMap` vẫn được giữ mạnh**.

Ví dụ **không giải quyết được vòng giữ tham chiếu**:

~~~java
Map<Class<?>, Method> methods = new WeakHashMap<>();

Class<?> type = ...;
Method method = type.getDeclaredMethod("run");
methods.put(type, method);
~~~

*Fragment minh họa giả định `type` có phương thức `run` và xử lý ngoại lệ tra cứu.*

Đường tham chiếu có thể là:

~~~text
Global WeakHashMap
    │
    ├── key (weak) ─────→ Class<?> của plugin
    │
    └── value (strong) ─→ Method
                             └── declaring Class<?> của plugin
                                      └── loader plugin
~~~

Giá trị `Method` lại giữ đường tham chiếu mạnh tới **chính class dùng làm key**. Vì vậy key có thể không đủ điều kiện bị GC dọn, và việc dùng weak key không đem lại tác dụng mong đợi.

Tương tự, value là một `MethodHandle`, metadata object chứa `Class<?>`, mảng `Field[]` hoặc lambda đóng trên class/instance của plugin cũng có thể giữ key trực tiếp hoặc gián tiếp. Có thể dùng value chỉ chứa thông tin bất biến độc lập với class, hoặc cần một cấu trúc cache xử lý vòng tham chiếu kiểu *ephemeron* phù hợp; **không mặc định rằng `WeakHashMap` là ephemeron map**.

Các lưu ý:

- `WeakHashMap` mặc định **không thread-safe**. Với truy cập đồng thời, dùng đồng bộ thích hợp hoặc lựa chọn khác; `Collections.synchronizedMap(...)` chỉ đồng bộ các thao tác theo hợp đồng wrapper, không tự giải quyết giá trị giữ key.
- Số lượng entry có thể thay đổi do GC; `size()` không phải một số liệu ổn định để làm logic nghiệp vụ hoặc snapshot test.
- Weak reference **không khiến GC chạy ngay**; đừng xây test yêu cầu entry biến mất sau `System.gc()`.
- Giá trị yếu (`WeakReference<V>`) cũng có đánh đổi: dữ liệu có thể bị thu hồi nhanh, phải tạo lại thường xuyên; vẫn cần bảo đảm tính đúng đắn và concurrency.

**Phù hợp khi:** bạn hiểu rõ đường giữ tham chiếu của cả key/value, metadata không trỏ ngược tới key, và chấp nhận eviction do GC. Với cache theo class thông thường, `ClassValue` thường là lựa chọn nên thử trước.

## 9. Cache `Method`, `Field`, `MethodHandle` và proxy cũng có thể giữ class loader

Mối nguy không chỉ nằm trong generic type của key.

| Cache chứa | Vì sao cần xem đường tham chiếu | Hướng xử lý |
| --- | --- | --- |
| `Class<?>` | Gắn với danh tính runtime của lớp và loader định nghĩa | Giới hạn scope, chủ động evict hoặc dùng `ClassValue` |
| `Method` / `Constructor<?>` | Metadata của thành viên thuộc declaring class | Không giữ trong global registry vượt đời plugin |
| `Field` | Tham chiếu field của declaring class | Cache theo class/scope phù hợp và xóa khi unload |
| `MethodHandle` / `MethodType` | Có thể tham chiếu lớp, member, adapter và các kiểu liên quan | Kiểm tra value graph, không chỉ cache key |
| `Proxy` instance / `InvocationHandler` | Instance, handler và các interface/proxy class có thể neo plugin | Hủy đăng ký listener/handler, ngừng công việc còn chạy |
| Lambda/factory/callback | Có thể capture instance hoặc class/loader plugin | Unregister theo vòng đời, tránh holder static |
| `ThreadLocal` và TCCL | Thread pool của ứng dụng có thể sống lâu hơn plugin | `remove()` ThreadLocal, khôi phục context loader, kết thúc task |
| `ClassValue<V>` | Gắn metadata theo class, có cơ chế quản lý liên kết | Không xuất giá trị ra global holder sống lâu; cân nhắc `remove` khi invalidate |

Một ví dụ phổ biến: một **static map trong lớp được nạp bởi AppClassLoader** giữ `Method` của plugin. Dù map dùng key `String`, value chứa một reflective member nên đường tham chiếu có thể giữ plugin loader. Khi triển khai lại plugin, bản method cũ không phải method của class mới chỉ vì hai class trùng tên.

## 10. Dọn lifecycle: đâu là trách nhiệm của hệ thống plugin?

Một hệ thống nạp/gỡ plugin nên định nghĩa các bước cleanup có chủ sở hữu rõ:

1. **Ngừng sử dụng plugin cũ.** Chặn request mới, kết thúc hoặc hủy các task đang chạy, callback hoặc timer liên quan.
2. **Hủy đăng ký đối tượng sống lâu.** Loại listener, interceptor, registry, event bus subscription, driver/provider hoặc service chứa instance từ plugin.
3. **Xóa cache theo plugin/class loader.** Cả key và value có thể giữ metadata; kiểm tra các singleton và vùng static của ứng dụng chính.
4. **Dọn thread và ngữ cảnh.** Khôi phục TCCL sau từng công việc; loại `ThreadLocal` của plugin khỏi thread do ứng dụng quản lý; tránh thread chạy mã plugin vô thời hạn.
5. **Đóng tài nguyên có thể đóng.** Chẳng hạn `URLClassLoader.close()` dừng việc nạp tài nguyên/JAR mới và giải phóng resource liên quan theo API; **không có nghĩa gọi `close()` sẽ tự unload các class đã nạp**.
6. **Chỉ sau khi không còn tham chiếu mạnh cần thiết** mới kỳ vọng loader *có thể* trở thành đối tượng đủ điều kiện GC. JVM quyết định khi nào thu gom và unload class.

Tránh chạy cleanup trong `finalize()` hoặc coi `System.gc()` là cơ chế vận hành bắt buộc. Dọn lifecycle phải là hành vi chủ động, có thể quan sát và xử lý lỗi.

### `ClassLoader` tạo ra theo từng lần tải lại

Nếu một plugin được reload nhiều lần, mỗi thế hệ loader có thể giữ bản riêng của cùng tên class. Khi đăng ký cache hoặc callback, hãy gắn thông tin thế hệ (*generation*) để tránh trả metadata cũ cho plugin mới.

Ví dụ logic:

~~~text
plugin: payments
generation: 17 → loader A → com.example.Handler (Class A)
generation: 18 → loader B → com.example.Handler (Class B)

Tên lớp giống nhau, Class A != Class B.
Các cache/handler của generation 17 phải được giải phóng theo lifecycle.
~~~

Một lớp mới cùng tên không tự xóa các entry do ứng dụng chính đang giữ cho lớp cũ.

## 11. Chẩn đoán thực tế: heap, class unloading và đường về GC root

Nếu thấy bộ nhớ tăng sau mỗi vòng redeploy, hãy đo và xác định nguồn giữ tham chiếu.

### 11.1. Dấu hiệu cần phân biệt

- **Heap tăng:** có thể do cache value/instance/plugin registry còn sống; heap không phải toàn bộ bộ nhớ JVM.
- **Metaspace tăng:** có thể liên quan số lớp/loader và khả năng class unloading, nhưng cũng phụ thuộc chính sách GC, workload và hành vi nạp lớp bình thường.
- **Số class loader cũ không giảm sau khi đã gỡ plugin:** cần kiểm tra vòng đời, GC thực tế và có còn đường tham chiếu mạnh hay không. Không kết luận từ một lần quan sát đơn lẻ.

Một cache lớn nhưng có giới hạn và hoạt động đúng có thể là chi phí chủ ý. Đối với leak, hãy ưu tiên bằng chứng **những đối tượng không còn cần thiết nhưng vẫn được giữ qua GC roots**.

### 11.2. Dùng công cụ HotSpot/JDK khi phù hợp

Trên JVM HotSpot với công cụ chẩn đoán sẵn có:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Ví dụ lệnh này có thể giúp xem thống kê class loader; tính khả dụng và tên command phụ thuộc JVM/JDK. `<pid>` là mã tiến trình thực, không nhập nguyên dấu ngoặc nhọn vào shell.

Khi chủ động bật log trong một môi trường thử nghiệm HotSpot:

~~~bash
java -Xlog:class+unload=info YourApplication
~~~

Các dòng class unload cho biết sự kiện unload thực tế; **không xuất hiện dòng log** trong một cửa sổ ngắn không tự chứng minh có leak, vì JVM có thể chưa thực hiện class unloading.

Với Native Memory Tracking (cần cấu hình phù hợp lúc khởi động nếu JVM hỗ trợ), bạn có thể xem bộ nhớ native tổng thể/metaspace bằng công cụ tương ứng. Đừng dùng một số liệu NMT đơn lẻ để quy lỗi cho cache.

### 11.3. Heap dump: tìm đường từ đối tượng bị giữ đến GC root

Trong heap analyzer như Eclipse Memory Analyzer hoặc VisualVM (tùy môi trường), hãy:

1. Tìm các **class loader cũ** của plugin, group theo loại và số lượng.
2. Chọn loader đáng lẽ đã ngừng sử dụng, xem **path to GC roots** và các strong references giữ loader, `Class` hoặc reflective member của plugin.
3. Theo ngược tới thành phần dài hạn: static map, singleton, thread, `ThreadLocal`, TCCL, listener, callback hoặc cache value.
4. Kiểm tra cả value graph: weak key không giúp nếu value giữ key.
5. Xử lý điểm giữ tham chiếu thực sự rồi thử lại chu kỳ load/unload trong cùng điều kiện kiểm thử.

Heap dump cần được quản lý cẩn thận vì có thể chứa dữ liệu nhạy cảm của ứng dụng. Chẩn đoán chỉ trên môi trường được phép và giữ phạm vi dữ liệu cần thiết.

## 12. Chiến lược kiểm thử không phụ thuộc GC có chạy đúng lúc không

Bạn có thể kiểm thử chắc chắn **lifecycle cache**, ngay cả khi không thể yêu cầu JVM thu hồi class loader tức thì:

- Nạp plugin thế hệ mới, xác nhận `Class<?>` của thế hệ mới **khác** lớp của thế hệ cũ nếu loader tự định nghĩa kiểu.
- Cache được gắn đúng scope hoặc key thế hệ, không trả nhầm metadata cũ.
- Khi gọi `unloadPlugin(id)`, registry của ứng dụng không còn entry/callback/task được sở hữu bởi plugin đó; phương thức này có thể được kiểm tra bằng số entry còn lại hoặc danh sách đăng ký.
- Với `ClassValue`, kiểm tra `get`, `remove` và việc tính lại metadata qua một hàm `computeValue` không có side effect không thể lặp. Không giả định `computeValue` chỉ được gọi đúng một lần khi chạy đa luồng.
- Với weak reference, chỉ ghi nhận GC thu hồi được loader trong **kiểm thử tích hợp có kiểm soát** như một tín hiệu hỗ trợ. Không viết assertion kiểu “gọi `System.gc()` rồi nhất định `weakRef.get() == null`”.

Ví dụ tự kiểm tra logic chủ sở hữu cache:

~~~java
Map<Class<?>, Metadata> cache = new HashMap<>();
cache.put(pluginType, metadata);

// Sau bước unregister/evict thuộc lifecycle:
cache.remove(pluginType);
if (cache.containsKey(pluginType)) {
    throw new AssertionError("Plugin cache entry remains");
}
~~~

*Fragment giả định các kiểu/biến đã khai báo; ví dụ này kiểm tra entry chứ không khẳng định JVM đã unload class.*

Đừng nhầm giữa **“code đã bỏ tham chiếu do mình sở hữu”** và **“JVM đã thu hồi mọi dữ liệu của plugin”**. Một thư viện bên thứ ba hoặc thread khác vẫn có thể giữ tham chiếu.

## 13. Checklist lựa chọn cache cho Reflection

| Nhu cầu | Lựa chọn thường phù hợp | Điều phải kiểm tra |
| --- | --- | --- |
| Metadata chỉ dùng trong một request/task | Biến cục bộ hoặc cache theo request | Không lưu ra singleton |
| Metadata theo từng class, dùng nhiều lần | `ClassValue<V>` | `computeValue` thuần, value an toàn luồng, không có global holder giữ lại |
| Plugin có lifecycle rõ và nhiều resource đi kèm | Cache theo plugin, `evictPlugin` | Unregister đầy đủ và chờ task cũ xong |
| Cache chung có giới hạn kích thước/thời gian | Bounded/expiring cache | Key/value giữ loader bao lâu, dữ liệu có bị tính lại quá nhiều không |
| Weak-key cache khi value độc lập key | `WeakHashMap<Class<?>, V>` (cẩn thận) | Value không giữ ngược class; concurrency và GC |
| Cần lưu danh sách mọi class toàn hệ thống lâu dài | Registry được cấp quyền sở hữu cụ thể | Phải có chính sách loại lớp của plugin khi unload |
| Chỉ muốn giữ tên hiển thị độc lập plugin | `String` hoặc DTO bất biến | Không dùng cùng tên làm danh tính runtime giữa nhiều loader |

Không có một loại cache tối ưu cho mọi trường hợp. Hãy bắt đầu từ **ai sở hữu metadata**, **khi nào dữ liệu hết hạn**, **có nhiều loader hay không**, và **value chứa những tham chiếu nào**.

## 14. Hiểu lầm thường gặp

**“`Class<?>` chỉ là một tên nhẹ, giữ nó không ảnh hưởng loader.”** Sai. Nó đại diện kiểu runtime cụ thể, liên quan đến class loader định nghĩa lớp.

**“Chỉ cần đổi `Map<Class<?>, V>` thành `Map<String, V>`.”** Không chắc. Value vẫn có thể giữ class, method hoặc instance; còn key tên đơn lẻ có thể nhập nhằng giữa plugin generations.

**“`WeakHashMap<Class<?>, Method>` đảm bảo không leak.”** Sai nếu `Method` giữ đường tham chiếu về chính declaring class làm key. Value được giữ mạnh.

**“`ClassValue` đảm bảo JVM unload lớp ngay.”** Sai. Nó giúp tổ chức metadata theo class, nhưng loader chỉ đủ điều kiện thu hồi khi không còn các đường tham chiếu mạnh khác; JVM không cam kết thời điểm unload.

**“Gọi `URLClassLoader.close()` là unload tất cả class.”** Sai. `close()` là đóng nguồn tài nguyên/khả năng nạp thêm theo API, không phải lệnh gỡ mọi đối tượng `Class`.

**“Không thấy unload log là chắc chắn memory leak.”** Chưa đủ. Cần xem đã có một chu kỳ GC/class unloading phù hợp chưa và có đường tham chiếu nào còn giữ loader không.

**“Chỉ có static field gây leak.”** Không đúng. Thread pool, TCCL, callback, listener, timer, instance trong container và value của cache đều có thể là nguồn giữ.

## 15. Tự kiểm tra

1. Tại sao `static Map<Class<?>, Metadata>` có thể giữ plugin sau khi gỡ? **Key `Class` được giữ mạnh bởi map tồn tại lâu và có thể giữ loader cùng lớp liên quan.**
2. Hai class có cùng `getName()` nhưng khác defining loader có luôn là một kiểu không? **Không.**
3. `WeakHashMap<Class<?>, Method>` có tự động an toàn với class unloading không? **Không, vì value `Method` có thể giữ lại declaring class/key.**
4. Metadata nên gắn theo `Class` và không cần liệt kê toàn bộ cache: thử API nào? **`ClassValue<T>`.**
5. Gọi `ClassValue.remove(type)` có bắt JVM unload class không? **Không.** Nó chỉ xóa liên kết metadata tương ứng.
6. Khi reload plugin, ngoài cache cần dọn gì? **Callback, listener, task, `ThreadLocal`, TCCL, instance và resource mà hệ thống còn sở hữu.**
7. Vì sao không dùng `System.gc()` rồi assert loader biến mất? **GC/class unloading không có thời điểm đảm bảo; kết quả có thể không ổn định.**
8. Nếu map dùng `String` key mà value là `Method` từ plugin thì còn nguy cơ giữ loader không? **Có.**

## 16. Kết luận

Cache metadata Reflection là một tối ưu hợp lý, nhưng một tham chiếu mạnh đến `Class<?>`, `Method`, `Field`, `MethodHandle` hoặc instance plugin có thể kéo dài vòng đời của **cả class loader**. Điều cần thiết là thiết kế **cache theo đúng vòng đời dữ liệu**, phân biệt danh tính kiểu theo loader, chủ động dọn đăng ký khi gỡ plugin, dùng `ClassValue` khi cần giá trị gắn theo class và tránh nhầm weak key với việc value không còn giữ class.

Khi nghi ngờ leak, kiểm chứng bằng đường tham chiếu từ GC roots và số liệu class loader/metaspace theo thời gian. Việc entry biến mất khỏi cache chỉ chứng minh một nguồn giữ đã được bỏ; việc JVM unload lớp vẫn phụ thuộc vào toàn bộ đồ thị tham chiếu và hoạt động của GC.

### Tài liệu tham khảo

- [Java SE 21 — `ClassValue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html)
- [Java SE 21 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html)
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 21 — `URLClassLoader.close`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html)
- [JLS `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7)
