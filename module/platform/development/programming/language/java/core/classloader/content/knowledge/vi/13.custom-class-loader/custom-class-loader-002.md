# Chọn constructor, parent và tên loader khi xây dựng ClassLoader tùy chỉnh

## 1. Ba quyết định khi tạo một custom class loader

Một class loader tùy chỉnh (*custom class loader*) có thể đọc class bytes từ JAR, thư mục riêng, tài nguyên plugin, mạng hoặc nguồn do chương trình quản lý. Trước khi viết cách tìm class, hãy xác định **ba điều khác nhau**:

1. **Constructor nào dùng để khởi tạo class loader object?** Trong Java 17, `ClassLoader` có constructor mặc định, constructor nhận parent, và constructor nhận tên cộng parent.
2. **Loader nào là parent trong quá trình delegation?** Điều này ảnh hưởng class và resource mà custom loader nhìn thấy, ranh giới shared API, khả năng cách ly plugin và nguy cơ trùng runtime type.
3. **Tên loader nào sẽ xuất hiện khi chẩn đoán?** Tên giúp con người phân biệt loader nhưng không thay cho object identity và không tự thay đổi parent hoặc bytecode lookup.

Cần phân biệt: **tạo một ClassLoader object không có nghĩa đã tạo một Java class mới**. Nếu subclass không cài đặt logic tìm/định nghĩa class mới, nó có thể chỉ ủy quyền cho parent mà không tự định nghĩa bất cứ class ứng dụng nào.

Một lựa chọn hợp lý thường thấy:

```java
public final class PluginClassLoader extends ClassLoader {
    public PluginClassLoader(String pluginId, ClassLoader apiParent) {
        super("plugin:" + pluginId, apiParent);
    }
}
```

Đây là subclass tối giản minh họa cách chọn **name** và **parent**. Nó chưa đọc plugin JAR; muốn nạp bytecode riêng còn cần cơ chế phù hợp, chẳng hạn override `findClass` hoặc sử dụng một loader có khả năng đọc nguồn class được chỉ định.

## 2. Các constructor của ClassLoader trên Java 17

`java.lang.ClassLoader` cung cấp ba constructor `protected` sau:

| Constructor | Parent | Tên của loader | Tình huống |
|---|---|---|---|
| `ClassLoader()` | `ClassLoader.getSystemClassLoader()` | Không đặt tên (`getName() == null`) | Loader đơn giản muốn mặc định delegating qua system loader |
| `ClassLoader(ClassLoader parent)` | Chính `parent` được truyền | Không đặt tên (`getName() == null`) | Cần chọn parent rõ ràng nhưng không cần nhãn |
| `ClassLoader(String name, ClassLoader parent)` | Chính `parent` được truyền | `name` hoặc `null` nếu không đặt tên | Plugin/module loader muốn cả parent lẫn tên dễ truy vết |

Điểm cần nhớ:

- `protected` có nghĩa các constructor được gọi từ subclass như `super(...)`, không phải `new ClassLoader()` trực tiếp trong mã ứng dụng ngoài phạm vi phù hợp.
- Constructor không tham số thực sự dùng **system class loader** làm parent theo contract JDK 17; nó không chọn “loader của class gọi” hay TCCL của thread hiện tại.
- `parent == null` trong constructor hai/ba tham số biểu thị parent là **bootstrap class loader** ở cơ chế delegation mặc định. Nó **không** tạo một bootstrap loader object mới.
- Với constructor có `name`, `null` được chấp nhận để tạo loader không tên; **chuỗi rỗng `""` không được phép** và gây `IllegalArgumentException`.
- Constructor có tên được giới thiệu từ **Java 9**, vì vậy dùng được trên Java 17 nhưng không có trên Java 8.

### Mẫu subclass hợp lệ

```java
public final class DemoLoader extends ClassLoader {
    public DemoLoader() {
        super();
    }

    public DemoLoader(ClassLoader parent) {
        super(parent);
    }

    public DemoLoader(String name, ClassLoader parent) {
        super(name, parent);
    }
}
```

Đây là class độc lập hợp lệ nếu lưu trong file `DemoLoader.java`. Trong Java 17, lời gọi constructor của superclass bằng `super(...)` cần xuất hiện đầu tiên trong constructor tương ứng. Nếu bỏ `super()` ở constructor không tham số, Java compiler chèn lời gọi `super()` ngầm.

**Constructor chỉ cấu hình loader object.** Class `DemoLoader` phía trên không override `findClass`, nên chưa có cơ chế riêng để đọc một JAR mới.

## 3. Parent là gì trong class loading?

`ClassLoader` thường dùng **parent delegation** khi được yêu cầu nạp một class. Với `ClassLoader.loadClass(String, boolean)` mặc định:

1. Gọi `findLoadedClass(name)` xem class đã được JVM ghi nhận đối với loader này chưa.
2. Nếu chưa có, thử nhờ `parent.loadClass(name)`. Nếu parent `null`, thử dùng **bootstrap loader**.
3. Nếu parent/bootstrap không cung cấp class, gọi `findClass(name)` của loader hiện tại.
4. Nếu yêu cầu resolve, gọi `resolveClass` theo contract rồi trả `Class<?>`.

Mô hình khái niệm:

```text
custom.loadClass("com.example.Service")
              |
              v
     Đã nạp qua loader này?
        | yes                 | no
        v                     v
  Dùng Class<?> cũ       Parent delegation
                               |
                  +------------+-----------+
                  | tìm được               | không tìm được
                  v                        v
             Dùng Class<?>            custom.findClass
              của parent                    |
                                      Tự tìm/định nghĩa
                                      hoặc thất bại
```

**Parent không đồng nghĩa superclass Java.** Một class loader có thể có `parent` là loader object của class khác bất kể quan hệ kế thừa Java giữa hai class loader implementations.

**Parent không đồng nghĩa defining loader của chính custom loader class.** Ví dụ `PluginClassLoader.class` có thể được application loader định nghĩa; trong khi object `new PluginClassLoader(..., platformLoader)` do app tạo có `getParent() == platformLoader`. Hai thuộc tính nói về hai chuyện khác nhau.

### Khi parent tìm được class

Nếu parent trả `Class<?>`, custom loader dùng class đó; **không tự tạo thêm class có cùng tên**.

```java
ClassLoader app = MainApp.class.getClassLoader();
ClassLoader child = new ClassLoader(app) { };

Class<?> c = child.loadClass("MainApp");
```

Đây là đoạn minh họa cần class `MainApp` đã có. Nếu `MainApp` được app loader định nghĩa, `c == MainApp.class` là true; còn `c.getClassLoader() == child` là false. **Initiating loader và defining loader có thể khác nhau**.

### Khi parent không tìm được class

Loader hiện tại được phép dùng `findClass` để tìm class từ nguồn riêng. Nhưng nếu subclass không override `findClass` thì implementation mặc định ném `ClassNotFoundException`.

Vì vậy:

```java
ClassLoader isolated = new ClassLoader(null) { };
isolated.loadClass("java.lang.String"); // thường thành công qua bootstrap
isolated.loadClass("MyApplication");    // thường thất bại nếu không tự tìm được
```

Đoạn trên minh họa hành vi trên JDK 17 chạy class path thông thường, với `MyApplication` chỉ là class ứng dụng. Lời gọi thứ hai có thể ném checked exception nên cần xử lý trong chương trình thật.

## 4. Chọn parent nào cho từng nhu cầu?

Trên JDK 17, các tầng loader thường gặp là bootstrap, platform và application/system. Nhưng custom loaders có thể được tổ chức theo nhiều mô hình khác nhau.

| Parent được chọn | Khả năng thường có | Điểm cần thận trọng |
|---|---|---|
| `null` | Delegation tới bootstrap trong thuật toán mặc định | Không bảo đảm nhìn thấy mọi platform class và class của app; phải tự cung cấp logic `findClass` cho phần riêng |
| `ClassLoader.getPlatformClassLoader()` | Có thể truy cập các lớp platform nhìn thấy được | Không mặc nhiên thấy mọi class nằm ở application class path |
| `ClassLoader.getSystemClassLoader()` | Trong app class path điển hình, nhìn thấy API/class của ứng dụng | Không mặc nhiên thấy các class/plugin được nạp bởi custom loader khác |
| `SharedApi.class.getClassLoader()` | Dùng cùng loader có thể nhìn thấy shared API type | Cần xác nhận implementation/plugin classes được cung cấp bởi finder riêng; tránh duplicate shared API |
| Loader plugin khác | Có thể ủy quyền sang loader chuyên biệt nếu thiết kế yêu cầu | Cân nhắc lifecycle, dependency graph, visibility và nguy cơ deadlock |

Chọn `parent` đúng là chọn **ràng buộc lookup và chia sẻ kiểu**. Không có một lựa chọn cố định luôn phù hợp với mọi ứng dụng.

### Parent null không có nghĩa “không thấy Java core”

Khi `parent == null`, `ClassLoader.loadClass` mặc định sử dụng bootstrap loader ở bước delegation. Vì vậy, `java.lang.Object` và `java.lang.String` thông thường vẫn có thể được nạp.

Tuy nhiên trên JDK 17, **không phải mọi Java platform class đều do bootstrap định nghĩa**. Các module và built-in loaders được phân chia phù hợp với runtime. Tài liệu constructor của Java SE 17 cảnh báo rõ: khi parent là `null`, **không có đảm bảo mọi platform class đều visible**.

Không nên chọn parent null chỉ vì muốn “cách ly tuyệt đối” hoặc “an toàn tuyệt đối”: loader đó vẫn sử dụng core runtime, và class loading không phải một sandbox bảo mật hoàn chỉnh.

### Parent là system loader có phù hợp plugin?

Có khi phù hợp, nếu plugin cần share interfaces/DTO do app loader định nghĩa. Nhưng với application server, module layer, OSGi-like container hoặc plugin framework, system loader chưa chắc là loader chứa shared API cần dùng.

Một cách ổn định hơn: tìm loader **định nghĩa shared contract**, chẳng hạn `PluginApi.class.getClassLoader()`, rồi dùng nó làm parent nếu architecture mong muốn. Trường hợp API class được bootstrap định nghĩa thì `getClassLoader()` có thể trả `null`, cần hiểu semantics của constructor đích.

## 5. Tên loader dùng để làm gì?

Từ Java 9, constructor:

```java
super("plugin:billing", parent);
```

cho phép gắn tên cho loader. Có thể đọc qua:

```java
String name = loader.getName();
```

Tên được dùng để **nhận biết** loader trong công cụ, log, diagnostic hoặc khi in thông tin cấu hình.

Những điều tên **không làm được**:

- Không quyết định binary name hoặc runtime identity của class.
- Không thay đổi parent delegation hoặc thứ tự tìm class.
- Không chỉ định đường dẫn JAR, thư mục hoặc module.
- Không bảo đảm uniqueness; hai loader objects có thể cùng tên.
- Không làm một loader trở thành bootstrap, platform hay system loader.
- Không tự đặt tên cho classes hoặc threads.

Ví dụ:

```java
ClassLoader app = MyApp.class.getClassLoader();
DemoLoader a = new DemoLoader("plugins", app);
DemoLoader b = new DemoLoader("plugins", app);

boolean sameName = a.getName().equals(b.getName());
boolean sameObject = a == b;
```

Đây là đoạn minh họa cần hai class `MyApp`/`DemoLoader`. `sameName` là true, `sameObject` là false. **Tên giống nhau không có nghĩa hai loader là một**.

### Quy tắc chọn tên thực tế

Tên hữu ích thường gồm chức năng và một định danh **không nhạy cảm**:

- `plugin:invoice`
- `tenant-loader:west`
- `module:reporting`
- `reload:inventory:v2`

Không nên ghi mật khẩu, token, đường dẫn riêng tư hoặc secret vào loader name vì các công cụ chẩn đoán có thể hiển thị tên đó. Tên dễ đọc nhưng **không phải security boundary**.

Khi cần phân biệt các lần hot reload, có thể dùng nhãn version hoặc run ID nội bộ không nhạy cảm, song đừng dựa vào label để xác định runtime class identity; hãy so sánh loader objects hoặc `Class<?>`.

### Tên null, tên rỗng và getName

- `new DemoLoader(null, app)` với constructor tên cho một loader **không tên**.
- `new DemoLoader("", app)` ném **`IllegalArgumentException`** theo Java SE 17.
- `loader.getName()` trả `null` nếu loader không tên.
- `getName()` là public và không `final` vì tương thích API; nếu subclass override, contract yêu cầu trả đúng tên được đặt tại thời điểm tạo.

Tên loader không được dùng thay vì kiểm tra `Class.getClassLoader()` khi muốn biết **defining loader**.

## 6. Ví dụ Java 17: so sánh ba constructor, parent và tên

Tạo file **`LoaderConstructorDemo.java`**:

```java
public class LoaderConstructorDemo {
    static class DemoLoader extends ClassLoader {
        DemoLoader() {
            super();
        }

        DemoLoader(ClassLoader parent) {
            super(parent);
        }

        DemoLoader(String name, ClassLoader parent) {
            super(name, parent);
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = LoaderConstructorDemo.class.getClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        DemoLoader defaultLoader = new DemoLoader();
        DemoLoader parentLoader = new DemoLoader(app);
        DemoLoader namedA = new DemoLoader("plugin:orders", app);
        DemoLoader namedB = new DemoLoader("plugin:orders", app);
        DemoLoader bootstrapChild = new DemoLoader("isolated", null);

        System.out.println("Default parent is system: "
                + (defaultLoader.getParent() == system));

        System.out.println("Explicit parent is app: "
                + (parentLoader.getParent() == app));

        System.out.println("No-arg name is null: "
                + (defaultLoader.getName() == null));

        System.out.println("Parent-only name is null: "
                + (parentLoader.getName() == null));

        System.out.println("Named loader: " + namedA.getName());

        System.out.println("Same name: "
                + namedA.getName().equals(namedB.getName()));

        System.out.println("Different loader objects: "
                + (namedA != namedB));

        System.out.println("Null parent: "
                + (bootstrapChild.getParent() == null));

        System.out.println("Bootstrap supplies String: "
                + (bootstrapChild.loadClass("java.lang.String")
                        == String.class));

        System.out.println("App parent supplies main: "
                + (parentLoader.loadClass("LoaderConstructorDemo")
                        == LoaderConstructorDemo.class));

        try {
            bootstrapChild.loadClass("LoaderConstructorDemo");
            System.out.println("Unexpected app lookup success");
        } catch (ClassNotFoundException expected) {
            System.out.println("Bootstrap-only cannot find main");
        }

        boolean rejectedEmptyName = false;
        try {
            new DemoLoader("", app);
        } catch (IllegalArgumentException expected) {
            rejectedEmptyName = true;
        }
        System.out.println("Empty name rejected: "
                + rejectedEmptyName);
    }
}
```

Chạy trên JDK 17 ở thư mục chứa file:

```bash
javac LoaderConstructorDemo.java
java LoaderConstructorDemo
```

Stdout trong cấu hình JDK 17 class path thông thường:

```text
Default parent is system: true
Explicit parent is app: true
No-arg name is null: true
Parent-only name is null: true
Named loader: plugin:orders
Same name: true
Different loader objects: true
Null parent: true
Bootstrap supplies String: true
App parent supplies main: true
Bootstrap-only cannot find main
Empty name rejected: true
```

Đọc kết quả:

1. Constructor không tham số của `ClassLoader` chọn system class loader làm parent; constructor nhận `app` đặt chính app loader.
2. Không truyền tên khiến `getName()` trả `null`; constructor `(name,parent)` cho tên `plugin:orders`.
3. Hai loader objects có thể dùng cùng tên nhưng vẫn là hai objects khác nhau.
4. `bootstrapChild` có parent `null` và thông qua default `loadClass` vẫn tìm được `String` từ bootstrap; nó không tự đọc `LoaderConstructorDemo.class` từ application class path.
5. `parentLoader.loadClass("LoaderConstructorDemo")` ủy quyền để trả class được **app loader định nghĩa**, không tự tạo một bản.
6. `""` là tên loader không hợp lệ, vì thế `IllegalArgumentException` được bắt và kết quả cuối là `true`.

**Điều kiện của ví dụ:** chạy chương trình ở class path thông thường và không thay đổi các loader classes/bytecode trong quá trình chạy. Nếu cấu hình một system loader đặc biệt, quy tắc constructor không tham số vẫn là dùng loader mà `getSystemClassLoader()` trả về; nhưng chi tiết visibility của app có thể khác.

## 7. Parent được chọn ảnh hưởng lúc nào tới findClass?

Nhiều người viết subclass:

```java
public class FileBackedLoader extends ClassLoader {
    FileBackedLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        // Đọc bytes của name từ nguồn class riêng.
        // Sau khi kiểm tra hợp lệ, defineClass(name, bytes, 0, bytes.length).
        throw new ClassNotFoundException(name);
    }
}
```

Đây là **khung cấu trúc để giải thích**; chưa phải loader đọc file thật và luôn ném `ClassNotFoundException`. Điều quan trọng là `findClass` thường được gọi **sau khi parent thất bại**, trong thuật toán `loadClass` mặc định.

Vì vậy, nếu parent **đã thấy class cùng tên**, code `findClass` của bạn có thể không bao giờ chạy với tên đó. Muốn một implementation có quyền tự định nghĩa namespace riêng, cần thiết kế **đường lookup** cẩn thận, không phải chỉ đổi tên loader.

### Ví dụ Java 17: parent-first khiến findClass không chạy khi parent tìm được

Tạo file **`ParentFirstDemo.java`**:

```java
public class ParentFirstDemo {
    static class ProbeLoader extends ClassLoader {
        private int findCalls;

        ProbeLoader(String name, ClassLoader parent) {
            super(name, parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            findCalls++;
            throw new ClassNotFoundException(name);
        }

        int findCalls() {
            return findCalls;
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = ParentFirstDemo.class.getClassLoader();
        ProbeLoader child = new ProbeLoader("probe", app);

        Class<?> loaded = child.loadClass("ParentFirstDemo");
        System.out.println("Parent supplied main: "
                + (loaded == ParentFirstDemo.class));
        System.out.println("findClass calls after hit: "
                + child.findCalls());

        boolean missing = false;
        try {
            child.loadClass("example.never.Exists123456");
        } catch (ClassNotFoundException expected) {
            missing = true;
        }

        System.out.println("Missing class reported: " + missing);
        System.out.println("findClass calls after miss: "
                + child.findCalls());
    }
}
```

Chạy trong một class path sạch không chứa class `example.never.Exists123456`:

```bash
javac ParentFirstDemo.java
java ParentFirstDemo
```

Stdout:

```text
Parent supplied main: true
findClass calls after hit: 0
Missing class reported: true
findClass calls after miss: 1
```

`ParentFirstDemo` đã được app loader định nghĩa, nên loader con nhận lại class đó và **không cần gọi `findClass`**. Class `example.never.Exists123456` không có ở parent; `findClass` của loader con được thử và ném `ClassNotFoundException`. Việc gắn tên `probe` giúp nhận diện loader, **không làm thay thuật toán parent-first**.

Trong hệ thống thật, nên ưu tiên override `findClass` khi chỉ muốn cung cấp cách tìm bytes riêng. Override `loadClass` để đổi parent-first thành child-first chỉ khi có kiến trúc rõ, kiểm soát namespace chia sẻ và xử lý đồng bộ hóa đúng cách.

## 8. Chọn parent và shared API trong ứng dụng plugin

Giả sử ứng dụng host có:

```text
Host / shared API loader
    api.Plugin
    api.Request
    |
    +-- Plugin loader A
    |      plugin.AImplementation
    |
    +-- Plugin loader B
           plugin.BImplementation
```

Nếu cả hai plugin cần implement `api.Plugin` và nhận `api.Request`, một thiết kế thông thường là cho plugin loader ủy quyền các shared types `api.*` tới **cùng loader sở hữu API**.

Nếu plugin loader tự định nghĩa một bản `api.Plugin` riêng, dù binary name trùng, đó có thể là **runtime class khác**, dẫn đến lỗi ép kiểu hoặc loading constraint khi host và plugin trao đổi types.

Chọn parent đúng giúp:

- Shared API/interface/DTO có cùng runtime identity.
- Code của plugin vẫn tự định nghĩa implementation và dependency riêng nếu lookup policy cho phép.
- Giảm nguy cơ `ClassCastException`, `LinkageError` hoặc provider không assignable.
- Dễ kiểm soát lifecycle: loader riêng có thể được bỏ tham chiếu khi plugin dừng, trong khi shared API loader sống cùng host.

**Nhưng parent được chọn không tự áp đặt toàn bộ chính sách isolation.** Nếu cần child-first cho một số packages và parent-first cho `java.*`/`api.*`, phải tự thiết kế chính sách lookup phù hợp và đảm bảo các ràng buộc Java/JVM.

### Parent null trong plugin có phải tốt hơn?

Không nhất thiết. Plugin parent-null có thể nhìn thấy bootstrap classes nhưng **không tự thấy API host**. Nếu plugin bytecode implement `api.Plugin` do host sở hữu, JVM cần resolve kiểu đó. Không có shared lookup path thì quá trình nạp/liên kết có thể thất bại.

Nếu cần plugin cô lập khỏi app nhưng vẫn chia sẻ contract, có thể dùng một loader chung chuyên biệt làm parent hoặc cơ chế delegate có kiểm soát, thay vì đặt parent null mà không có chiến lược tìm API.

## 9. Cách xác minh loader đã chọn

Khi debug, dùng các thuộc tính tách biệt:

```java
ClassLoader parent = myLoader.getParent();
String label = myLoader.getName();

Class<?> found = myLoader.loadClass("com.example.SomeClass");
ClassLoader actualOwner = found.getClassLoader();
```

Đây là đoạn **minh họa**, cần các biến/class thực tế và xử lý `ClassNotFoundException`. Ý nghĩa:

- `myLoader.getParent()`: parent cho delegation.
- `myLoader.getName()`: tên để chẩn đoán, có thể null.
- `found.getClassLoader()`: **defining loader của runtime class đã trả về**; có thể khác `myLoader` nếu parent cung cấp class.

Một bảng chẩn đoán nhanh:

| Quan sát | Không nên kết luận | Cách hiểu đúng |
|---|---|---|
| `myLoader.getName().equals(other.getName())` | Hai loader là một | Tên có thể trùng; so sánh object identity |
| `myLoader.getParent() == null` | Không delegation | Với default `loadClass`, ủy quyền tới bootstrap |
| `loaded.getClassLoader() != myLoader` | Lookup thất bại | Class có thể được parent định nghĩa và child trả về |
| `ClassNotFoundException` từ loader parent-null | JVM thiếu core classes | Loader có thể không biết class app và không override `findClass` |
| Loader có tên khác nhau | Classes của chúng chắc chắn khác | Nếu cùng ủy quyền cho parent, có thể nhận **cùng Class<?>** |
| `findClass` không được gọi | Override bị lỗi | Parent có thể đã trả kết quả trước |

### Class loader name có xuất hiện trong lỗi và log không?

Các công cụ JVM như class loading logs, stack traces hoặc diagnostics có thể hiển thị thông tin loader và tên. Trên HotSpot JDK 17, có thể bật:

```bash
java -Xlog:class+load=info LoaderConstructorDemo
```

Output có thể chứa nhiều lớp thư viện được nạp; định dạng log phụ thuộc JVM/version. Tên có ích để đọc, nhưng không dùng chỉ tên làm bằng chứng loader object nào đã định nghĩa class. Khi cần, xem thêm `Class.getClassLoader()` và các công cụ thống kê loader tương ứng.

## 10. Constructor và vòng đời của loader object

Tạo `new DemoLoader(...)` chỉ tạo một **loader object**, chưa nhất thiết định nghĩa class riêng. Trong JVM chạy lâu:

- Loader có thể sống rất lâu nếu nằm trong static registry, thread context class loader, thread-local, listener, cache hoặc executor.
- Các class do loader định nghĩa có runtime identities gắn với loader đó.
- Muốn hot reload version mới của cùng binary name, thường tạo **loader mới** thay vì cố định nghĩa lại class đã có ở loader cũ.
- Một loader mới có thể có **cùng name** với loader cũ nhưng là object khác và có thể định nghĩa class runtime khác.
- Việc bỏ tham chiếu tới loader/plugin không đảm bảo class unloading xảy ra ngay; garbage collection và class unloading phụ thuộc reachability cùng JVM implementation.

Do đó tên loader nên biểu thị logical owner và optional version để debug, nhưng **lifecycle phải quản lý qua object references và trách nhiệm giải phóng resources**, không qua tên.

### Constructor chưa đủ để đọc JAR

`new DemoLoader("plugin:A", appLoader)` không làm loader hiểu đường dẫn JAR plugin. Nếu dùng `URLClassLoader`, cần cung cấp URLs/parent đúng constructor mà loại loader đó hỗ trợ. Với subclass `ClassLoader`, thường cài `findClass` đọc bytes và `defineClass` theo API; cần xử lý package identity, access controls, resources và lỗi.

Nếu loader sở hữu tài nguyên có thể đóng (ví dụ `URLClassLoader`), thiết kế lifecycle để gọi `close()` khi thích hợp và sau khi không còn tác vụ sử dụng. `close()` không có nghĩa JVM tức thì unload mọi class do loader đã định nghĩa.

## 11. Những lựa chọn thường sai

### “Để super() tự chọn parent vì loader hiện tại là plugin loader”

Không đúng. `ClassLoader()` lấy **system class loader**, không tự động dùng TCCL hoặc loader của class plugin. Trong môi trường phức tạp, parent mặc định có thể không thấy shared API cần dùng.

**Sửa:** nếu biết loader sở hữu API, truyền tường minh vào `super(apiLoader)` hoặc `super(name, apiLoader)`.

### “Truyền parent null để có loader hoàn toàn độc lập với Java core”

Không đúng. Parent null được `loadClass` mặc định diễn giải thành bootstrap delegation. Đồng thời không đảm bảo mọi platform class visible.

**Sửa:** thiết kế isolation có chủ đích, đảm bảo shared runtime/API types được resolve đúng.

### “Tên loader là khóa duy nhất để xác định các class”

Không đúng. Hai loader objects có thể trùng tên. JVM class identity dựa vào binary name cộng **defining loader**, không dùng `getName()`.

**Sửa:** lưu loader object/reference, khi cần so sánh runtime class identity thì so sánh `Class<?>` bằng `==`.

### “Đặt name là plugin-v2 thì JVM tự nạp JAR v2”

Không đúng. `name` là label; không quyết định classpath, URL hay finder.

**Sửa:** quản lý nguồn class bytes/resource URLs trong finder riêng, không nhồi đường dẫn vào tên như một phương thức cấu hình.

### “Dùng super(null) tương đương super()”

Không đúng. `super()` dùng system loader làm parent; `super((ClassLoader) null)` chọn bootstrap lookup trong default delegation.

**Sửa:** chọn rõ behavior mong muốn; trong source code, `super(null)` là constructor một tham số khi không có constructor một tham số kiểu khác gây nhập nhằng, còn `super(name,null)` rõ parent hơn.

### “Cứ override findClass thì class trong plugin luôn được định nghĩa bởi custom loader”

Không đúng. Parent-first sẽ ưu tiên class tìm được ở parent; `findClass` chỉ được gọi khi cần.

**Sửa:** thiết kế namespace: shared API parent-first, implementation có thể cần đường tìm riêng. Chỉ override `loadClass` khi thật sự cần, đồng bộ hóa qua `getClassLoadingLock(name)` và `findLoadedClass(name)`.

### “Tên loader rỗng giúp tiết kiệm log”

Không đúng. Constructor có tên từ Java 9 từ chối `""`.

**Sửa:** truyền `null` để không đặt tên hoặc truyền tên **không rỗng**.

### “Tên loader sẽ tự bảo đảm class unloading”

Không đúng. Tên là metadata cho chẩn đoán; garbage collection/unloading phụ thuộc reachability và JVM.

**Sửa:** dọn các tham chiếu dài hạn như thread pools, listener, callback, registries, context class loader và caches khi plugin đóng.

## 12. Một checklist lựa chọn nhanh

Trước khi triển khai, trả lời theo thứ tự:

1. **Loader này có cần thấy shared API của host không?** Nếu có, chọn một parent nhìn thấy đúng API classes; kiểm tra runtime identity.
2. **Nó cần nạp class riêng từ đâu?** JAR, directory, generated bytecode hay nguồn khác — phải có finder phù hợp; constructor không tự giải quyết.
3. **Ứng dụng muốn parent-first hay một chiến lược có chọn lọc?** Đừng child-first cho mọi package nếu có shared contracts.
4. **Có cần tên loader để debug không?** Nếu có, dùng `ClassLoader(String, ClassLoader)` và nhãn không nhạy cảm, không rỗng.
5. **Parent null có thực sự cần không?** Nhớ bootstrap delegation và giới hạn platform visibility.
6. **Có tình huống hot reload không?** Mỗi loader object sở hữu class identities; quản lý vòng đời, đóng tài nguyên và xóa references phù hợp.
7. **Có concurrency không?** Nếu override `loadClass`, giữ các thao tác check/delegate/find/resolve đồng bộ phù hợp `getClassLoadingLock` và parallel-capable contract.
8. **Có dùng named modules không?** Parent và `ClassLoader` không bỏ qua JPMS readability, exports/opens hoặc module-layer relationships.

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong Java 17, `new DemoLoader()` và `new DemoLoader(null)` có cùng parent không nếu cả hai constructor tương ứng gọi `super()` và `super(parent)`?

**Đáp án:** Không. `super()` chọn system loader; `super(null)` chọn parent null, tức bootstrap delegation trong default `loadClass`.

**Câu 2.** `new DemoLoader("", app)` và `new DemoLoader(null, app)` khác nhau chỗ nào?

**Đáp án:** Chuỗi rỗng gây `IllegalArgumentException`, còn tên `null` hợp lệ và tạo loader không tên.

**Câu 3.** Hai loaders đều tên `plugin:orders`. Chúng có phải cùng một loader object không?

**Đáp án:** Không thể suy ra từ tên. Name không nhất thiết duy nhất, class identity cũng không dựa vào name.

**Câu 4.** Loader con có parent `app`. Vì sao `child.loadClass("MyApp")` có thể trả class do app loader định nghĩa?

**Đáp án:** Vì thuật toán mặc định ưu tiên parent lookup. `Class<?>` trả về giữ nguyên defining loader là app, không trở thành class do child định nghĩa.

**Câu 5.** Vì sao truyền `null` làm parent không luôn giúp tìm mọi Java SE/JDK platform class?

**Đáp án:** Bootstrap không định nghĩa mọi platform class trên JDK 17. API của constructor cũng cảnh báo không có bảo đảm toàn bộ platform classes visible khi parent `null`.

**Câu 6.** Nếu `findClass` đã được override, tại sao khi nạp một class parent thấy được, bộ đếm lần `findClass` vẫn là 0?

**Đáp án:** `loadClass` mặc định kiểm tra lớp đã nạp rồi ủy quyền parent; chỉ khi parent không cung cấp class thì mới thử `findClass`.

**Câu 7.** Một plugin cần dùng interface `api.Plugin` của host. Nên chọn parent theo điều gì?

**Đáp án:** Loader phải resolve interface qua **đúng shared API runtime class**; thường chọn parent có thể thấy/định nghĩa `api.Plugin` thay vì đơn giản chọn null hoặc system loader theo thói quen.

**Câu 8.** Loader mới mang cùng tên với loader của phiên bản plugin cũ có tự thay thế các class runtime cũ không?

**Đáp án:** Không. Loader objects khác nhau có thể định nghĩa các runtime classes khác nhau, dù cùng tên hoặc cùng class binary name; class unloading phụ thuộc reachability, không phụ thuộc tên.

## 14. Ghi nhớ và tài liệu tham khảo

- **`ClassLoader()`** chọn **system class loader** làm parent.
- **`ClassLoader(parent)`** chọn parent tường minh; **`parent == null`** biểu thị bootstrap trong thuật toán mặc định.
- **`ClassLoader(name,parent)`** (Java 9+) đặt tên loader; `name == null` hợp lệ, `name == ""` bị từ chối.
- **Tên loader không tạo runtime class identity**; binary name cộng defining loader mới xác định class.
- **Parent quyết định đường delegation**, còn `findClass`/nguồn bytes quyết định loader có thể tự định nghĩa những class nào.
- **Khi thiết kế plugin**, ưu tiên một loader chung cho shared API types, xác định lookup policy và lifecycle trước khi chọn constructor.

Nguồn chính thức:

1. [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): constructors, `getName`, `getParent`, `loadClass`, `findClass`, `getClassLoadingLock` và runtime built-in loaders.
2. [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): ví dụ loader có URLs, parent, tên và lifecycle `close`.
3. [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, type identity và constraints.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): cách built-in loaders và Java modules hoạt động từ Java 9.