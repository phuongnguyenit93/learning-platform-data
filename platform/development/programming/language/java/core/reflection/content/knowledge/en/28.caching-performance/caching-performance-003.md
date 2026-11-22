# Khóa cache cần xét `Class` và định danh ClassLoader trong Java Reflection

## 1. Vấn đề: “cùng tên lớp” chưa chắc là cùng kiểu

Trong ứng dụng dùng **Reflection**, framework, plugin, ứng dụng chạy nhiều class loader hay cơ chế hot reload, chúng ta thường cache kết quả tốn chi phí tìm kiếm như `Class<?>`, `Method`, `Constructor<?>`, `Field`, annotation metadata hoặc bộ chuyển đổi dữ liệu. Lỗi khó phát hiện xuất hiện khi khóa cache chỉ là tên chuỗi:

~~~java
// Cách dễ sai khi có nhiều class loader
Map<String, Method> methodCache = new HashMap<>();
methodCache.put("com.example.Plugin#execute", aMethod);
~~~

Tên `com.example.Plugin` chỉ là **binary name**. Nó không đủ nhận diện một lớp Java tại runtime: **hai class loader khác nhau có thể định nghĩa hai class khác nhau mang cùng binary name**. Nếu lấy `Method` từ lớp thứ nhất đem gọi trên đối tượng của lớp thứ hai, Java Reflection có thể ném `IllegalArgumentException` vì receiver không phải instance của declaring class phù hợp.

Bài này giải thích cách chọn khóa đúng, minh họa lỗi bằng Java 17+ chạy được, đề xuất `ClassValue` để giữ metadata theo từng `Class<?>`, và phân tích cache gây giữ class loader trong bộ nhớ.

**Kết quả cần đạt:** phân biệt tên lớp, class loader được yêu cầu nạp và class loader thực sự định nghĩa; xây cache có định danh chính xác; xử lý overload/thread safety; tránh giữ class/plugin cũ sau khi unload.

## 2. Định danh lớp tại JVM: binary name **cùng** defining loader

JVM xác định một class/interface runtime dựa trên **tên nhị phân và class loader định nghĩa nó**. Vì vậy, có thể có:

~~~text
Loader-A --define--> demo.Plugin   (Class object A)
Loader-B --define--> demo.Plugin   (Class object B)
~~~

Dù `Class.getName()` trả cùng `"demo.Plugin"`:

- `classA == classB` là `false`; chúng biểu diễn **hai kiểu runtime khác nhau**.
- `classA.getClassLoader() != classB.getClassLoader()` nếu chúng được định nghĩa bởi hai loader khác nhau.
- Đối tượng do `classA` tạo không tự động là instance của `classB`: `classB.isInstance(objectFromA)` trả `false`.
- `Method`/`Constructor` hoặc `Field` tra cứu trên class A không thể tùy ý áp dụng cho class B, kể cả bytecode nhìn giống hệt.
- Các static field và quá trình khởi tạo class cũng thuộc từng class runtime; việc một loader nạp cùng tên không làm hai class chia sẻ trạng thái static.

**Phân biệt defining và initiating loader:** khi gọi `requestedLoader.loadClass("demo.Plugin")`, loader ấy có thể **ủy quyền cho parent**. Kết quả `Class<?>` lúc đó do **parent định nghĩa**, nên `type.getClassLoader()` có thể khác `requestedLoader`. Chọn khóa theo `Class<?>` sau khi đã phân giải là cách đơn giản và chính xác nhất khi cache metadata phụ thuộc vào *kiểu thực tế*.

Trường hợp bootstrap loader như `String.class.getClassLoader()` có thể trả về `null`; `null` ở đây là trường hợp hợp lệ, không phải lỗi.

## 3. Chọn khóa cache theo thứ đang được cache

Không có một kiểu khóa phù hợp mọi bài toán. Trước tiên hãy xác định bạn muốn cache **kết quả phân giải tên** hay **metadata của một class đã xác định**:

| Dữ liệu cache | Khóa gợi ý | Vì sao? |
| --- | --- | --- |
| Metadata/annotation của một class | `Class<?>` hoặc `ClassValue<T>` | Chính `Class` đã mang định danh runtime gồm loader |
| Danh sách `Method` của một class | `Class<?>` rồi khóa phụ cho signature | Chặn nhầm method giữa hai lớp trùng tên |
| Một `Method` cụ thể | `Class<?>` + tên + kiểu tham số + chính sách declared/public | Overload không có cùng metadata |
| Một `Constructor` | `Class<?>` + kiểu tham số | Constructor overload theo tham số |
| Một `Field` | `Class<?>` + tên field + phạm vi tra cứu | Field được gắn với declaring class cụ thể |
| Phân giải tên `"demo.Plugin"` thành `Class<?>` | **Tên + initiating loader / ngữ cảnh phân giải** | Cùng tên có thể phân giải khác nhau theo loader |
| Tra cứu theo JPMS layer/module | Khóa bổ sung `Module`/`ModuleLayer` khi cách phân giải phụ thuộc chúng | Loader đơn thuần không luôn mô tả đầy đủ chính sách tìm module |

Đối với **metadata đã có `Class<?>`**, khóa bằng `Class<?>` là **đủ để phân biệt loader**. Không bắt buộc thêm `type.getClassLoader()` vào khóa, vì hai `Class` khác nhau đã khác nhau rồi. Một khóa `(Class<?>, ClassLoader)` đôi khi dùng được, nhưng thường dư thừa và có thể vô tình giữ thêm tham chiếu mạnh.

Nếu API nhận **tên lớp dạng chuỗi** và lựa chọn loader ở thời điểm tìm, hãy dùng một khóa có cả tên **và chính ngữ cảnh yêu cầu phân giải**. Nên dùng **đối tượng loader**, không chỉ `loader.getClass().getName()`, `toString()` hay `hashCode()`: hai instance loader cùng lớp vẫn có thể định nghĩa những class khác nhau. Nếu hệ thống có layer, phiên bản plugin, biến thể lookup hay rule tùy biến, cần phản ánh những yếu tố làm thay đổi kết quả trong khóa.

**Quan hệ tương đương phải đúng:** hai request chỉ chia sẻ kết quả cache nếu chương trình thực sự bảo đảm chúng phân giải tới cùng đối tượng runtime và cùng chính sách truy cập.

## 4. Ví dụ chạy được: cùng tên nhưng hai class loader khác nhau

Ví dụ dưới đây tự đọc bytecode của lớp nested `Widget` rồi tạo hai `ClassLoader` tùy chỉnh để **định nghĩa lại đúng một tên class**. Loader tùy chỉnh chỉ bỏ qua cơ chế ủy quyền parent đối với `Widget`; những lớp còn lại vẫn ủy quyền bình thường.

Tạo file `ClassCacheKeyDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

public class ClassCacheKeyDemo {
    public static class Widget {
        public Widget() {}
        public String ping() { return "pong"; }
    }

    static class ShadowLoader extends ClassLoader {
        private final byte[] bytes;

        ShadowLoader(byte[] bytes) {
            super(ClassCacheKeyDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(Widget.class.getName())) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytes, 0, bytes.length);
                }
                if (resolve) resolveClass(found);
                return found;
            }
        }
    }

    static byte[] widgetBytes() throws IOException {
        try (InputStream in = ClassCacheKeyDemo.class.getResourceAsStream(
                "ClassCacheKeyDemo$Widget.class")) {
            if (in == null) throw new IOException("Class bytes not found");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = widgetBytes();
        Class<?> appClass = Widget.class;
        Class<?> pluginClass =
                new ShadowLoader(bytes).loadClass(Widget.class.getName());
        Class<?> otherPluginClass =
                new ShadowLoader(bytes).loadClass(Widget.class.getName());

        System.out.println("Same name: "
                + appClass.getName().equals(pluginClass.getName()));
        System.out.println("Same Class: " + (appClass == pluginClass));
        System.out.println("Different plugin classes: "
                + (pluginClass != otherPluginClass));
        System.out.println("Different defining loaders: "
                + (pluginClass.getClassLoader()
                        != otherPluginClass.getClassLoader()));

        Map<String, Method> wrongCache = new HashMap<>();
        wrongCache.put(appClass.getName() + "#ping",
                appClass.getMethod("ping"));
        Object pluginObject = pluginClass.getConstructor().newInstance();
        try {
            wrongCache.get(pluginClass.getName() + "#ping")
                    .invoke(pluginObject);
        } catch (IllegalArgumentException expected) {
            System.out.println("Wrong cached Method: IllegalArgumentException");
        }

        Map<Class<?>, Method> correctCache = new HashMap<>();
        correctCache.put(appClass, appClass.getMethod("ping"));
        correctCache.put(pluginClass, pluginClass.getMethod("ping"));
        System.out.println("Correct reflection call: "
                + correctCache.get(pluginClass).invoke(pluginObject));
    }
}
~~~

Biên dịch/chạy tại thư mục chứa file bằng **Java 17+**:

~~~bash
javac --release 17 ClassCacheKeyDemo.java
java ClassCacheKeyDemo
~~~

Kết quả thực tế đã kiểm tra trên JDK 21 với `--release 17`:

~~~text
Same name: true
Same Class: false
Different plugin classes: true
Different defining loaders: true
Wrong cached Method: IllegalArgumentException
Correct reflection call: pong
~~~

**Phân tích:**

1. Cả hai loader tùy chỉnh định nghĩa bytecode của `ClassCacheKeyDemo$Widget`, tạo các `Class<?>` khác với lớp `Widget` do loader ứng dụng định nghĩa.
2. Cache sai dùng `getName() + "#ping"` nên trả `Method` của lớp ứng dụng, dù đối tượng nhận lời gọi thuộc lớp do plugin loader định nghĩa.
3. `Method.invoke(pluginObject)` ném `IllegalArgumentException` vì receiver không thuộc kiểu khai báo method tương ứng.
4. Cache dùng `Map<Class<?>, Method>` phân biệt hai runtime class; gọi method của lớp plugin trên instance plugin trả kết quả chính xác.

Đây là **demo cố ý** dùng child-first cho một class nhằm tái hiện sự khác biệt. Đừng biến toàn bộ loader thành child-first trong sản phẩm nếu không hiểu ranh giới dependency, package, resource và bảo mật.

## 5. Cache method phải xét cả signature và quy tắc Reflection

Ngay cả khi khóa ngoài đã là `Class<?>`, một lớp có thể overload:

~~~java
String substring(int beginIndex)
String substring(int beginIndex, int endIndex)
~~~

Vì vậy không nên cache bằng mỗi tên `"substring"`. Nếu sử dụng `Class.getMethod(name, parameterTypes)` (chỉ tìm method public, có cả kế thừa), khóa phụ nên mang tên và **danh sách `Class<?>` của tham số theo đúng thứ tự**. Với `getDeclaredMethod(...)`, phải rõ chính sách lấy method khai báo trực tiếp; đừng trộn cache của `getMethod` và `getDeclaredMethod`.

Những điều dễ sót:

- `int.class` khác `Integer.class`; `String[].class` khác `String.class`.
- Overload `call(String)` khác `call(Object)`; số lượng và thứ tự tham số đều quan trọng.
- Method có varargs vẫn có kiểu tham số mảng trong Reflection, ví dụ `String...` thành `String[].class`.
- `Method.getDeclaringClass()` có thể là **lớp cha/interface khai báo** chứ không phải owner class dùng để tra cứu. Cache theo class yêu cầu và định danh method/declaring class cho phù hợp mục đích.
- Generic sau **type erasure** không làm `List<String>` và `List<Integer>` trở thành hai kiểu tham số runtime khác nhau.
- Trong bytecode có thể tồn tại bridge/synthetic method. Nếu đang làm việc với metadata thô hoặc descriptor JVM, kiểm tra cả `getReturnType()`, `isBridge()` và `isSynthetic()` khi thích hợp. API `getMethod` thông thường không cho chọn method bằng return type.
- Quyền truy cập thành viên có thể phụ thuộc **caller lookup, module, `exports`/`opens`**. Lấy được `Method` hay cache nó không đồng nghĩa mọi caller đều có quyền gọi/private access.

Với ứng dụng chỉ có một `status()` không tham số và API public, khóa phụ có thể rất đơn giản. Với thư viện Reflection tổng quát, cần biểu diễn đầy đủ signature, loại thành viên, cách lookup và chính sách truy cập.

## 6. `ClassValue<T>`: cache giá trị gắn trực tiếp với từng `Class<?>`

JDK cung cấp `java.lang.ClassValue<T>` (Java 7+) để **gắn dữ liệu tính toán theo từng class runtime**. Vì `Class<?>` đã phân biệt loader, `ClassValue` cũng phân biệt hai class trùng tên được định nghĩa bởi loader khác nhau.

~~~java
private static final ClassValue<Metadata> CACHE = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return inspect(type);
    }
};
~~~

Đây là **fragment minh họa**; `Metadata` và `inspect` là kiểu/hàm do ứng dụng tự định nghĩa. `CACHE.get(type)` tính giá trị khi chưa có rồi lưu theo `type`; `CACHE.remove(type)` bỏ giá trị của class đó để lần tiếp theo tạo lại.

Lợi ích chính: tránh phải tự quản lý một `Map<Class<?>, ...>` toàn cục chỉ để ánh xạ class sang metadata; `ClassValue` được thiết kế riêng cho mối liên hệ này và hỗ trợ truy cập đồng thời. Tuy nhiên:

- `computeValue` **có thể chạy nhiều lần khi thread cạnh tranh**, dù chỉ một kết quả được cài đặt để trả về. Không đặt thao tác side effect không an toàn hoặc giao dịch bắt buộc chạy đúng một lần trong `computeValue`.
- `remove(type)` chỉ xóa association của **đúng đối tượng `Class<?>`** khỏi **đúng đối tượng `ClassValue`** đó. Nó không “xóa mọi cache” của ứng dụng.
- `ClassValue` không tự ngăn mọi memory leak: nếu code khác vẫn giữ `Class<?>`, loader, instance hoặc handle của plugin cũ thì lớp vẫn có thể còn sống.
- Chỉ thêm `ClassValue` khi metadata thực sự dùng nhiều lần; cache làm tăng độ phức tạp và tiêu thụ bộ nhớ nếu phép tra cứu rất rẻ/ít lặp.

### Ví dụ Java 17 hoàn chỉnh: `ClassValue` và overload

Tạo file `ClassValueDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

public class ClassValueDemo {
    record Signature(String name, List<Class<?>> parameters) {
        Signature(String name, Class<?>... parameters) {
            this(name, List.of(parameters));
        }
    }

    private static final ClassValue<ConcurrentHashMap<Signature, Method>> CACHE =
            new ClassValue<>() {
                @Override
                protected ConcurrentHashMap<Signature, Method> computeValue(
                        Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    static Method publicMethod(Class<?> owner, String name,
                               Class<?>... parameters)
            throws NoSuchMethodException {
        Signature key = new Signature(name, parameters);
        var methods = CACHE.get(owner);
        Method cached = methods.get(key);
        if (cached != null) return cached;

        Method discovered = owner.getMethod(name, parameters);
        Method prior = methods.putIfAbsent(key, discovered);
        return prior == null ? discovered : prior;
    }

    public static void main(String[] args) throws Exception {
        Method one = publicMethod(String.class, "substring", int.class);
        Method again = publicMethod(String.class, "substring", int.class);
        Method two = publicMethod(
                String.class, "substring", int.class, int.class);

        System.out.println("Same cached method: " + (one == again));
        System.out.println("Overloads distinct: " + (one != two));
        System.out.println("First call: " + one.invoke("abcd", 2));
        System.out.println("Second call: " + two.invoke("abcd", 1, 3));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ClassValueDemo.java
java ClassValueDemo
~~~

Output đã kiểm tra:

~~~text
Same cached method: true
Overloads distinct: true
First call: cd
Second call: bc
~~~

`Signature` là record nên có so sánh theo giá trị; `List.of(parameters)` tạo danh sách bất biến chứa tham số theo đúng thứ tự thay vì giữ trực tiếp mảng `Class<?>...` có thể bị caller sửa. `ConcurrentHashMap` cho phép các thread truy cập cùng metadata class an toàn theo thao tác map.

Ví dụ cố ý chỉ cache **method public** qua `getMethod`. Nếu method vắng mặt, nó ném `NoSuchMethodException` và không lưu “không tồn tại”. Với hệ thống cần cache cả *negative lookup*, hãy dùng kiểu kết quả riêng (sentinel/`Optional` hoặc object chứa trạng thái) và xác định chính sách invalidation cẩn thận. `ConcurrentHashMap` không cho key hoặc value `null`.

Về concurrency, ví dụ dùng `get` → tra cứu Reflection → `putIfAbsent`. Hai thread có thể cùng tra cứu method một lần trong tình huống cạnh tranh, nhưng map giữ một giá trị cuối; điều này phù hợp vì tra cứu method là thao tác không có side effect nghiệp vụ.

## 7. Khi phải cache bằng tên trước khi có `Class<?>`

Một resolver nhận:

~~~java
Class<?> resolve(String binaryName, ClassLoader requestedLoader)
        throws ClassNotFoundException {
    return Class.forName(binaryName, false, requestedLoader);
}
~~~

là **fragment đầy đủ của hàm** để đặt trong class. `Class.forName(..., false, requestedLoader)` yêu cầu tra cứu mà **không chủ động khởi tạo lớp**. Đối số loader là loader dùng để yêu cầu phân giải, không bảo đảm đó là defining loader của kết quả.

Nếu cache kết quả `resolve`, khóa phải bao gồm tối thiểu **`binaryName` và `requestedLoader` theo identity**, hoặc một namespace/version context có hợp đồng tương đương. Hãy phân biệt:

- `Map<String, Class<?>>` **sai** nếu cùng tên có thể được giải bằng nhiều loader.
- `Map<Key(String, ClassLoader), Class<?>>` có thể đúng về phân biệt request, với điều kiện `ClassLoader` được so sánh theo **định danh thực sự của instance** (identity). `record` dùng `equals` của loader; nếu có loader tùy biến ghi đè `equals`, hãy chọn wrapper identity hoặc cấu trúc phù hợp.
- Nếu đã có `Class<?> resolved`, cache metadata theo **`resolved`**, không cần tính lại key tên + loader.
- Không cache `ClassNotFoundException` vĩnh viễn theo một loader có thể tìm thêm class sau khi thêm JAR/plugin; negative lookup phải có chính sách làm mới tương ứng.

**Tránh dùng** `requestedLoader.getClass().getName()` làm loader id; nó chỉ nói **loại loader**, không phải instance nào. Cũng không dùng mỗi `System.identityHashCode(loader)` để làm định danh duy nhất trong cache lâu dài: mã hash có thể trùng và bản thân hash không giữ được tham chiếu chính xác tới loader.

Với nền tảng có nhiều `ModuleLayer`, resolver có thể phụ thuộc module/layer bên cạnh loader. Định nghĩa khóa theo **đúng các đầu vào của phép resolve đang dùng**, thay vì giả định mỗi `binaryName` có một class toàn cục.

## 8. Vòng đời cache và nguy cơ giữ class loader

Một khóa metadata theo `Class<?>` có thể **đúng về identity** nhưng cache global như `static ConcurrentHashMap<Class<?>, Method>` lại sống lâu hơn plugin. Map giữ mạnh cả key `Class` lẫn `Method` trỏ về declaring class, khiến loader cũ có thể chưa được thu hồi sau khi gỡ plugin. Đổi sang `WeakHashMap<Class<?>, Method>` không tự giải quyết vòng giữ từ value về key.

Với metadata tính riêng cho mỗi class, `ClassValue` thường phù hợp; với plugin có lifecycle rõ, cache nằm trong plugin hoặc có thao tác `evict` khi unload cũng là lựa chọn hợp lý. Những nguồn giữ khác như callback, thread, `ThreadLocal` hay handle phải được dọn theo lifecycle; **GC và class unloading không có hạn chót được bảo đảm**. Bài “Cache giữ Class có thể giữ cả class loader” phân tích reference graph, weak keys, heap dump và kiểm tra GC roots cụ thể.

## 9. Reload, dynamic proxy, hidden class và thay đổi định nghĩa

**Reload plugin:** phiên bản mới cùng binary name thường xuất hiện dưới **loader mới**, tức `Class<?>` mới. Cache theo class tự phân biệt phiên bản cũ/mới; cache theo tên có thể trả metadata cũ.

**Dynamic proxy:** proxy class sinh ra phụ thuộc loader, tập interface và ngữ cảnh module. Dùng tên hiển thị hoặc tên proxy class sinh ra làm định danh bền vững là rủi ro. Nếu cache phản chiếu trên proxy, dùng `proxy.getClass()` hoặc một khóa dựa trên cấu hình proxy đã chuẩn hóa theo đúng loader/interface identity.

**Hidden class:** class có thể được tạo bằng `MethodHandles.Lookup.defineHiddenClass`; nó không nhất thiết được định danh/tra cứu lại bằng `Class.forName(name)` theo cách thông thường. Nếu cần cache metadata, khóa bằng chính `Class<?>` đã được cấp.

**Instrumentation/redefinition:** các API như `Instrumentation.redefineClasses` có thể thay bytecode của **cùng class runtime** trong giới hạn JVM cho phép. Khi đó **identity của `Class<?>` không đổi**, nhưng metadata/behavior có thể thay đổi theo thao tác công cụ. Cache theo `Class<?>` không tự biết phiên bản bytecode đã đổi: cơ chế instrumentation/framework phải có **invalidation hoặc generation/version** phù hợp nếu dữ liệu cache phụ thuộc nội dung có thể thay đổi.

**Class loader delegation:** hai loader khác nhau có thể cùng ủy quyền nạp về parent và nhận **chính một `Class<?>`**. Trong trường hợp đó cache theo kết quả `Class<?>` cho metadata có thể chia sẻ an toàn theo identity. Không suy đoán hai kiểu khác nhau chỉ vì hai lời gọi `loadClass` bắt đầu từ hai loader khác nhau.

## 10. Quy tắc vận hành để cache Reflection an toàn

### 10.1. Tách metadata khỏi quyền truy cập

Một `Method` có thể tồn tại nhưng không truy cập được từ một module/caller cụ thể. `setAccessible(true)` vẫn chịu ràng buộc `opens`; `MethodHandles.Lookup` mang quyền của caller hoặc lookup được cấp. Nếu cache **handle có đặc quyền** hay dữ liệu phụ thuộc caller, khóa và cách chia sẻ phải phản ánh ranh giới quyền, không phát tán handle/lookup cho đối tượng không tin cậy.

### 10.2. Thread safety không đồng nghĩa key correctness

`ConcurrentHashMap` giúp các thao tác map nhất quán giữa thread, **không biến `String className` thành định danh class an toàn**. Phải sửa thiết kế khóa trước khi bàn tối ưu lock hay compute-if-absent.

Với `computeIfAbsent`, hàm tính toán có thể ném checked exception khiến bạn phải quy đổi/wrap rồi xử lý rõ ràng; không cache một ngoại lệ ở dạng thành công. Cân nhắc thất bại tạm thời, thay đổi plugin, quyền module và cơ chế invalidation trước khi dùng negative cache.

### 10.3. Đừng tối ưu khi chưa đo

Reflection lookup lặp lại có thể tốn chi phí nhưng tạo cache cũng có giá thành: lookup khóa, bộ nhớ, giữ loader, đồng bộ và invalidation. Dùng benchmark phù hợp (ví dụ JMH với warm-up) để quyết định cache gì. Nếu đường gọi nóng đã có `MethodHandle`/`VarHandle` ổn định và được cấp đúng quyền, đôi khi lưu handle trong phạm vi lifecycle rõ ràng tốt hơn cache `Method` toàn cục.

### 10.4. Checklist review

- Cache đang lưu **kết quả tra tên** hay metadata của **`Class<?>` cụ thể**?
- Nếu key là `String`, lớp ấy có thể được định nghĩa từ bao nhiêu loader/plugin?
- Nếu key là `Class<?>`, có đang vô tình giữ loader cũ qua global strong map?
- Key của method có phân biệt overload, kiểu tham số theo thứ tự, static/instance và `getMethod` với `getDeclaredMethod`?
- Nếu có quyền truy cập khác nhau theo caller/module, liệu cache có vô tình chia sẻ handle đặc quyền?
- Khi reload/unload hoặc redefine, entry nào phải bị loại bỏ?
- Có test hai loader **cùng nạp một binary name** hay mới chỉ test một loader mặc định?

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `Method.invoke` báo `IllegalArgumentException` dù “đúng class name” | `Method` thuộc class do loader khác định nghĩa | So sánh `method.getDeclaringClass()` và `receiver.getClass()`, cả loader |
| `ClassCastException` với hai lớp cùng tên | Hai defining loader tạo hai runtime type | Dùng chung API/interface do loader phù hợp chia sẻ, không ép theo tên |
| `NoSuchMethodException` sau deploy phiên bản mới | Cache cũ, signature khác, overload sai | Tra đúng `Class<?>` mới và đúng kiểu tham số |
| `LinkageError` hoặc loader constraint violation | Loading/linking không tương thích giữa các class loader | Rà soát delegation và dependency giữa loader |
| Loader plugin không được unload | Cache tĩnh giữ `Class`, `Method`, handle hoặc instance | Dùng `ClassValue`/cache theo vòng đời và dọn các reference |
| Cache name + loader class vẫn va chạm | Dùng **loại loader**, không phải instance loader | Dùng class đã resolve hoặc loader object identity |
| Cùng loader nạp class qua parent nhưng cache bị nhân đôi | Khóa dùng initiating loader khi chỉ cache class metadata | Cache theo `Class<?>` kết quả để gộp được cùng identity |
| Cache không đổi sau redefine cùng `Class` | Không có invalidation theo phiên bản | Gắn vòng đời cache với generation/redefine event |
| Cache map thread-safe nhưng trả method sai | Đồng bộ đúng, định danh sai | Thiết kế lại key trước khi tối ưu đồng bộ |

## 12. Tự kiểm tra

1. Hai `Class<?>` có `getName()` bằng nhau nhưng defining loader khác nhau. Có được dùng chung `Method` không? **Không**; đó là hai runtime type riêng.
2. Cache `Map<Class<?>, Metadata>` đã phân biệt loader chưa? **Có**; `Class<?>` mang định danh runtime bao gồm defining loader.
3. Nếu cache `Class.forName(name, false, requestedLoader)` trước khi biết kết quả, có thể chỉ dùng `name` không? **Không**, nếu nhiều loader/ngữ cảnh có thể phân giải khác nhau.
4. `requestedLoader` và `resolvedClass.getClassLoader()` có luôn giống nhau không? **Không**, vì parent delegation.
5. Vì sao `WeakHashMap<Class<?>, Method>` chưa chắc cho loader unload? **Method value có thể giữ declaring class**, tạo đường tham chiếu mạnh từ map value đến key.
6. `ClassValue.computeValue` có chắc chỉ chạy đúng một lần trong cạnh tranh không? **Không**; nhiều thread có thể cùng tính, một giá trị được cài đặt.
7. Sau khi redefine bytecode của một class mà giữ nguyên `Class<?>`, key theo `Class<?>` đã tự invalid cache chưa? **Chưa**; cần generation/invalidation nếu metadata ảnh hưởng.
8. Với `getMethod("substring", int.class)` và `getMethod("substring", int.class, int.class)`, cache key nên khác nhau ở đâu? **Danh sách kiểu tham số**.

## 13. Tài liệu chính thức

- [Java Virtual Machine Specification 17 — Creation and Loading, `5.3](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html)
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html)

**Ghi nhớ:** Đối với metadata Reflection, **khóa bằng chính `Class<?>`** (hoặc dùng `ClassValue`) để phân biệt cả defining loader. Chỉ khi cache **phân giải tên trước khi có class** mới cần giữ tên cùng initiating loader/ngữ cảnh; sau khi có class, đừng quay lại khóa bằng tên. Cân nhắc vòng đời plugin và strong references để một cache đúng về mặt ngữ nghĩa không trở thành nguyên nhân memory leak.