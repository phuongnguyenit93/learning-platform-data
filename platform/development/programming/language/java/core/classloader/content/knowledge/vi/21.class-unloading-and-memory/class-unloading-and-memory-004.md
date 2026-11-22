# Quan hệ giữa Class, đối tượng instance và ClassLoader khi dỡ lớp trong Java

## 1. Câu hỏi trung tâm: điều gì còn sống khi plugin ngừng chạy?

Trong một hệ plugin, ứng dụng tạo `URLClassLoader` riêng, yêu cầu nó nạp `plugin.Widget`, tạo một instance, chạy một số phương thức rồi đóng loader. Khi đó có ba loại đối tượng/khái niệm cần phân biệt:

1. **`ClassLoader` instance:** đối tượng tổ chức việc tìm và định nghĩa class; xác định không gian tên runtime cho các class do nó định nghĩa.
2. **`Class<?>` object:** đại diện phản chiếu (*class mirror*) cho **một runtime class/interface cụ thể**. Có thể lấy qua `Widget.class`, `instance.getClass()` hoặc kết quả của `loadClass`.
3. **Instance của class:** một đối tượng bình thường được tạo từ class đó bằng constructor, reflection, factory hoặc cơ chế khác.

Ba thứ liên quan nhưng **không phải một đối tượng**, cũng không có cùng điều kiện vòng đời. Đóng tài nguyên của ClassLoader không làm các instance tự biến mất, còn xóa một biến tham chiếu instance không đồng nghĩa các class đã được unload.

Các câu hỏi quan trọng:

- Tại sao `object.getClass().getClassLoader()` cho biết loader định nghĩa kiểu của object?
- Vì sao giữ lại một instance, một `Class<?>` hay một thread đang thực thi mã plugin có thể ngăn class/loader đủ điều kiện thu hồi?
- Vì sao hai loader dùng cùng bytecode tạo hai kiểu Java khác nhau?
- `URLClassLoader.close()`, garbage collection, class unloading và Metaspace khác nhau thế nào?
- Làm thế nào xác định **GC root → object → class/loader** trong một sự cố memory leak?

Đây là trọng tâm của quan hệ **Class ↔ instance ↔ loader** trong ngữ cảnh **dỡ lớp và bộ nhớ**.

## 2. Hình dung ba thực thể và liên kết của chúng

Ví dụ mã nguồn:

```java
package plugin;

public final class Widget {
    public String message() {
        return "hello";
    }
}
```

Đây là source của một class mẫu, không phải chương trình có `main` độc lập.

Khi một custom loader `L` định nghĩa `plugin.Widget`, rồi tạo hai instance, có thể hình dung:

```text
Custom ClassLoader object L
        |
        | defining loader của runtime class
        v
Runtime class: ("plugin.Widget", L)
        |
        +-- Class<?> mirror C
        |       C.getName()          = "plugin.Widget"
        |       C.getClassLoader()   = L
        |
        +-- Instance A ---- A.getClass() == C
        |
        +-- Instance B ---- B.getClass() == C
```

Sơ đồ là **mô hình khái niệm**: JVM có thể tổ chức heap, mirrors và metadata khác nhau theo implementation. Không nên suy ra mọi mũi tên là một trường Java public có thể nhìn trực tiếp bằng reflection.

Những phép so sánh thường đúng khi cả hai đối tượng được tạo từ cùng runtime class:

```java
Class<?> aType = a.getClass();
Class<?> bType = b.getClass();

System.out.println(aType == bType); 
System.out.println(aType.getClassLoader() == definingLoader);
```

Đoạn này là **snippet** (cần biến `a`, `b`, `definingLoader`). `Class<?>` đại diện một định nghĩa runtime, không phải một descriptor chữ thuần và cũng không phải instance của `Widget`.

### Tại sao `Class<?>` là object, nhưng lại khác object đang học?

`java.lang.Class` là một class thuộc nền tảng Java. Bản thân `Widget.class` là một đối tượng Java thuộc kiểu `Class<Widget>` hoặc `Class<?>`. Còn `new Widget()` là một **instance của `Widget`**. Khác biệt:

- `Widget.class.getName()` hỏi tên định nghĩa kiểu.
- `widget.getClass()` trả class mirror của kiểu runtime của instance.
- `Widget.class.getClassLoader()` trả **defining loader** của `Widget`.
- `Widget.class.getClass()` mô tả class của **class mirror**, thường là `java.lang.Class`; nó không trả `Widget`.
- Class literal `Widget.class` trong code host yêu cầu kiểu Widget khả dụng với loader/linkage của host; trong hệ plugin động, host thường không thể import implementation cụ thể và sẽ làm việc qua interface chung cùng reflection.

**Không nên đồng nhất** câu “Class là object” với “tạo object class mới khi tạo mỗi instance”. Hai instance cùng runtime class thông thường trả **cùng đối tượng `Class<?>`** từ `getClass()`.

## 3. Danh tính runtime class: binary name cộng defining loader

JVM xác định danh tính của một runtime class/interface bằng cặp:

```text
(binary name, defining ClassLoader)
```

Ví dụ:

```text
("plugin.Widget", PluginLoader#1) !=
("plugin.Widget", PluginLoader#2)
```

Dù hai loader đọc **cùng bytecode byte-for-byte**, nếu mỗi loader tự định nghĩa `plugin.Widget` thì chúng là **hai runtime types khác nhau**.

| Đặc tính | Class ở Loader A | Class ở Loader B |
| --- | --- | --- |
| `getName()` | `plugin.Widget` | `plugin.Widget` |
| `getClassLoader()` | A | B |
| `Class<?> ==` | Không bằng bản ở B | Không bằng bản ở A |
| Instance có thể cast sang bản kia? | Không chỉ vì tên/bytes giống | Không chỉ vì tên/bytes giống |
| Static fields | Gắn với runtime class A | Gắn với runtime class B |
| Class initialization | Độc lập theo class A | Độc lập theo class B |

Nếu loader con gọi `loadClass("plugin.Widget")` nhưng parent đã có class ấy, kết quả có thể là class do parent **định nghĩa**. Trong trường hợp đó, loader con chỉ là loader **khởi xướng yêu cầu** (*initiating loader*), không phải defining loader. Nhiều code nhầm loader được gọi với loader xác lập type identity.

### Trường hợp `java.lang.String` và bootstrap loader

Các class lõi như `java.lang.String` được bootstrap loader định nghĩa trong môi trường Java tiêu chuẩn. Vì vậy:

```java
System.out.println(String.class.getClassLoader() == null);
```

thường in:

```text
true
```

Giá trị `null` từ `Class.getClassLoader()` là biểu diễn API cho **bootstrap loader**, không có nghĩa kiểu `String` “không có loader” theo mô hình JVM.

Với **primitive types** như `int.class` và `void.class`, `getClassLoader()` cũng trả `null` theo API nhưng không nên suy rằng đây là class file định nghĩa bởi một bootstrap ClassLoader bình thường. Với **array classes**, JVM tạo array class theo quy tắc riêng; defining loader được gắn theo kiểu thành phần tham chiếu hoặc biểu diễn bootstrap nếu thành phần là primitive.

## 4. Khi có instance còn reachable, điều gì được giữ?

Giả sử host giữ:

```java
Object pluginInstance = pluginType
        .getDeclaredConstructor().newInstance();
```

Đây là snippet, `pluginType` là Class mirror của implementation plugin và constructor được phép truy cập.

Khi `pluginInstance` còn reachable, JVM phải giữ kiểu runtime đủ để nhận biết và sử dụng đối tượng đó. Nếu defining loader cùng các runtime classes do nó định nghĩa được dỡ tùy tiện, VM sẽ không còn mô hình kiểu/method dispatch hợp lệ cho instance đang sống.

Đối với dỡ class theo JVMS, một class/interface **chỉ có thể** unload khi defining ClassLoader của nó có thể được garbage collector thu hồi. Đây là **điều kiện cần**, không phải lệnh yêu cầu JVM unload class ngay sau khi tham chiếu Java được gán `null`.

Những reference từ host thường khiến plugin chưa sẵn sàng được thu hồi:

```text
GC Root (thread / static field / registry)
   |
   v
Host service registry
   |
   v
Plugin instance
   |
   v
Runtime class / JVM metadata
   |
   v
Defining ClassLoader
```

Mũi tên liên quan runtime class/loader là **sơ đồ quan hệ reachability ở mức VM**, không giả định instance Java có trường `ClassLoader loader;`. Điểm chính là **không thể dỡ định nghĩa class khi các instance của nó vẫn còn cần dùng**.

### Còn nếu giữ lại một Class<?>?

Một reference từ host đến `Class<?>` của class plugin cũng có thể neo định nghĩa lớp và defining loader. Ví dụ:

```java
static final Map<String, Class<?>> PLUGIN_CLASS_CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Đây là snippet, cần import `Map` hoặc dùng tên đầy đủ; bản thân `Class<?>` từ plugin được lưu vào map lâu dài sẽ là điểm cần kiểm tra khi điều tra loader leak.

Tương tự, `Method`, `Constructor`, `MethodHandle`, proxy metadata, lambda, method reference và framework reflection caches có thể duy trì đường tham chiếu khiến code loader cũ còn reachable. Mức độ giữ object cụ thể phụ thuộc implementation/API, nhưng **đừng chỉ tìm tham chiếu trực tiếp tới chính ClassLoader**.

## 5. Ví dụ Java 17: hai loader, hai Class objects, instance vẫn dùng được sau close

Thí nghiệm tạo một class file lúc runtime bằng `JavaCompiler` (JDK 17+), rồi đọc cùng thư mục bytecode qua **hai `URLClassLoader` độc lập**. Ta đo những điều có thể khẳng định **không phụ thuộc GC**:

1. Cùng tên class và cùng bytecode không tạo cùng runtime `Class<?>` nếu defining loaders khác.
2. Mỗi instance trả về đúng class mirror do defining loader tương ứng định nghĩa.
3. Đóng URLClassLoader không làm instance đã tồn tại tự động mất khả năng chạy phương thức đã được định nghĩa.
4. Class nền tảng vẫn đến từ bootstrap/parent delegation.

### 5.1. Mã đầy đủ: `ClassInstanceLoaderDemo.java`

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class ClassInstanceLoaderDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use JDK 17+ with javac");
        }

        Path work = Files.createTempDirectory("class-instance-loader-");
        try {
            Path source = work.resolve("src/plugin/Widget.java");
            Path classes = work.resolve("classes");
            Files.createDirectories(source.getParent());
            Files.createDirectories(classes);

            Files.writeString(source, """
                    package plugin;
                    public final class Widget {
                        public String message() {
                            return "hello";
                        }
                    }
                    """);

            int exit = compiler.run(null, null, null,
                    "--release", "17",
                    "-d", classes.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL classesUrl = classes.toUri().toURL();
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            Class<?> typeA;
            Object instanceA;

            try (URLClassLoader loaderA = new URLClassLoader(
                        new URL[]{classesUrl}, parent);
                 URLClassLoader loaderB = new URLClassLoader(
                        new URL[]{classesUrl}, parent)) {

                typeA = loaderA.loadClass("plugin.Widget");
                Class<?> typeB = loaderB.loadClass("plugin.Widget");

                instanceA = typeA.getDeclaredConstructor()
                        .newInstance();
                Object instanceB = typeB.getDeclaredConstructor()
                        .newInstance();

                System.out.println("sameBinaryName="
                        + typeA.getName().equals(typeB.getName()));
                System.out.println("sameClass=" + (typeA == typeB));
                System.out.println("aDefiningIsA="
                        + (typeA.getClassLoader() == loaderA));
                System.out.println("bDefiningIsB="
                        + (typeB.getClassLoader() == loaderB));
                System.out.println("instanceClassIsA="
                        + (instanceA.getClass() == typeA));
                System.out.println("crossLoaderCompatible="
                        + typeA.isInstance(instanceB));
                System.out.println("stringBootstrap="
                        + (loaderA.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }

            // Cả hai loader đã close, nhưng instanceA/typeA
            // vẫn còn reference trong scope hiện tại.
            Object result = typeA.getMethod("message")
                    .invoke(instanceA);
            System.out.println("afterClose=" + result);
        } finally {
            try (Stream<Path> stream = Files.walk(work)) {
                for (Path path :
                        stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ClassInstanceLoaderDemo.java
java ClassInstanceLoaderDemo
```

Stdout mong đợi với JDK 17+ có compiler và quyền tạo file tạm:

```text
sameBinaryName=true
sameClass=false
aDefiningIsA=true
bDefiningIsB=true
instanceClassIsA=true
crossLoaderCompatible=false
stringBootstrap=true
afterClose=hello
```

### 5.2. Giải thích từng dòng

- **`sameBinaryName=true`:** cả hai type đều mang tên `plugin.Widget` theo `Class.getName()`.
- **`sameClass=false`:** vì hai `URLClassLoader` độc lập đã tự định nghĩa class đó; `Class<?>` mirror khác nhau.
- **`aDefiningIsA=true` và `bDefiningIsB=true`:** class A do loader A định nghĩa, class B do loader B định nghĩa. Cùng URL class directory không gộp chúng thành một kiểu.
- **`instanceClassIsA=true`:** instanceA thuộc runtime class A; `instanceA.getClass()` trả đúng class mirror A.
- **`crossLoaderCompatible=false`:** instanceB không được coi là instance của class A, dù code source và class name giống hệt.
- **`stringBootstrap=true`:** lớp `String` được bootstrap định nghĩa, không bị mỗi plugin loader tự định nghĩa.
- **`afterClose=hello`:** sau khi hai `URLClassLoader` được đóng bởi try-with-resources, `instanceA` và `typeA` vẫn còn reference và có thể dùng method đã nạp. Đây là minh chứng rằng **`close()` không phải `unload()`**.

Chương trình không dùng `System.gc()` và không đặt kỳ vọng thời điểm dỡ lớp, vì GC/class unloading không có stdout xác định theo thời gian.

### 5.3. Giới hạn của demo

- Class `Widget` không phụ thuộc class riêng nào khác được nạp muộn từ thư mục `classes` sau khi loader đóng. Nếu method cần nạp thêm một dependency chưa được định nghĩa trước `close()`, có thể xảy ra lỗi nạp sau close. Không suy rằng đóng URLClassLoader là vô hại trong mọi luồng thực thi.
- Ví dụ giữ `typeA` và `instanceA` bằng local references để **cố ý ngăn kết luận unload đã xảy ra**.
- Chỉ là ví dụ về class trên **classpath** qua `URLClassLoader`, không phải triển khai module layer hay plugin framework hoàn chỉnh.
- Việc xóa thư mục tạm chỉ xảy ra sau khi cả loader được đóng; có thể lỗi nếu môi trường từ chối xóa file, và đây là lỗi resource cleanup độc lập với class identity.
- Lệnh `--release 17` đảm bảo bytecode Java 17 cho class sinh ra; dự án demo chạy với Java 17+ có text block, stream `toList()`.

## 6. ClassLoader.close() không phải quy trình unload class

`URLClassLoader` triển khai `Closeable`, nên có thể dùng try-with-resources:

```java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    Class<?> plugin = loader.loadClass(binaryName);
    // Tạo instance và thực thi khi loader đang mở.
}
```

Đây là snippet, biến `urls`, `parent` và `binaryName` phải tồn tại ở ứng dụng.

**`close()` làm gì?** Theo API `URLClassLoader`, đóng những file JAR/resource loader đã mở và ngăn một số thao tác tìm thêm class/resource mới từ các URL đã được loader quản lý. Nó **không**:

- Tự gọi `Plugin.stop()` hay `AutoCloseable.close()` trên mọi plugin instance.
- Tự đóng worker executor, socket, JDBC connection hoặc event listener do plugin tạo.
- Tự xóa `Class<?>` đã định nghĩa, method/field đã liên kết hoặc các đối tượng Java còn reachable.
- Ép `System.gc()` hoặc bảo đảm JVM unload ngay khi close.
- Biến instance còn sống thành object “không hợp lệ”; các method đã nạp có thể tiếp tục chạy.
- Đảm bảo một loader cũ không còn được giữ bởi host static caches, TCCL hay framework metadata.

### Khi nào Class có cơ hội được unload?

Quy tắc quan trọng từ JVMS là một runtime class/interface có thể được unload **nếu và chỉ nếu** defining loader của nó có thể được GC thu hồi. Trong thực tế, để một custom loader đủ điều kiện thu hồi, ứng dụng cần bảo đảm không còn đường strong reference từ GC roots tới loader hoặc những class/instance và runtime structures khiến loader còn sống.

Điều này không có nghĩa:

```text
pluginLoader = null;
System.gc();
=> Class đã unload xong
```

Sơ đồ trên là **một kết luận sai**, không phải code có thể dựa vào. Gán một reference thành null chỉ loại bỏ **một cạnh**. GC là quá trình được JVM quyết định; tồn tại nhiều reference khác có thể khiến loader còn reachable.

### Vì sao JVM có thể giữ class metadata ở Metaspace?

Trên HotSpot JVM, class metadata thường được lưu trong **Metaspace** (bộ nhớ native), trong khi `Class<?>` mirrors là đối tượng Java theo mô hình runtime. Các đường reference từ heap/thread/static roots vẫn có thể giữ class/loader và metadata liên quan sống.

Do đó, một ứng dụng plugin có thể:

- Không tăng heap quá nhiều nhưng Metaspace tăng sau hàng trăm lần reload.
- Có heap dump cho thấy loader/plugin classes bị giữ bởi listener, cache hoặc thread.
- Giảm áp lực Metaspace khi dỡ được những classloader thực sự không còn cần thiết, nhưng mức bộ nhớ OS được trả lại và thời điểm unload phụ thuộc JVM/GC và allocator.

**Không đồng nhất** `OutOfMemoryError: Metaspace` với `OutOfMemoryError: Java heap space`. Đều là áp lực bộ nhớ nhưng vùng và nguyên nhân cần điều tra khác nhau.

## 7. Chu trình tham chiếu không phải lúc nào cũng gây leak

Một sơ đồ dễ khiến người mới hiểu sai:

```text
Plugin ClassLoader
   -> runtime class / metadata
   -> static field
   -> plugin instance
   -> object dùng class đó
   -> liên kết ngược về runtime class
```

Có thể tưởng “có vòng reference thì GC không thể thu hồi”. Thực tế **garbage collector dựa trên reachability từ GC roots**, không đơn giản đếm tham chiếu rồi từ chối mọi chu trình.

Nếu một nhóm object chỉ tham chiếu lẫn nhau mà **không còn reachable từ GC roots**, GC có thể thu hồi cả nhóm, với những điều kiện/cơ chế JVM thích hợp. Cùng một reasoning áp dụng khi loader và những class/instance của nó không còn được giữ bởi host, threads, registries hoặc những root khác.

Một vòng tham chiếu giữa plugin instance và callback là vấn đề nghiêm trọng **khi host event bus là GC root hoặc reachable từ root**:

```text
GC Root
   -> static HostEventBus
   -> callback
   -> plugin instance
   -> plugin runtime class
   -> loader
```

Chỉ xóa plugin khỏi một `PluginManager.map` **không** loại bỏ đường qua event bus nếu event bus vẫn giữ callback. Vì thế dỡ plugin cần **unregister tại nơi đã register**.

## 8. Các đường reference gây giữ ClassLoader phổ biến

Retaining paths phổ biến gồm **host cache → `Class<?>`/instance**, event bus → callback plugin, pool thread → TCCL/`ThreadLocal`, executor queue → pending task và service/framework registry → provider instance.

Cùng là reference tới plugin nhưng owner và cách cleanup khác nhau. Dùng heap dump `path to GC roots` để tìm nguồn sống lâu thực sự; bài static caches, threads và ServiceLoader giải thích các loại root này bằng ví dụ riêng.

## 9. WeakReference<ClassLoader>: quan sát được gì và không được gì?

`WeakReference<ClassLoader>` không giữ loader sống chỉ nhờ chính reference đó, nên thích hợp quan sát khả năng reclaim. Tuy nhiên `weak.get() != null` sau một lần thử không chứng minh leak; `weak.get() == null` chứng tỏ referent đã được clear, **không tự cung cấp log cho từng class unload**.

Tránh giữ `Class<?>`, instance, `Method` hoặc loader trong biến local khi muốn thử eligibility. Bài quan sát unloading phân biệt các tín hiệu này với sự kiện JVM.

## 10. Reload plugin là tạo defining loader mới, không phải đổi bytes trong loader cũ

Loader đã định nghĩa `plugin.Widget` thường trả chính `Class<?>` cũ khi gọi `loadClass("plugin.Widget")` lần nữa. Muốn dùng định nghĩa mới, tạo loader mới, chuyển lifecycle/traffic an toàn, rồi retire loader cũ.

Một instance của version cũ vẫn thuộc runtime type cũ; đóng URL loader không thay đổi type identity hay static state của class đang sống.

## 11. Lỗi thường gặp liên quan Class–instance–loader

`ClassCastException` giữa hai tên giống nhau thường chỉ hai defining loaders khác nhau. `LinkageError` dạng loading constraint violation liên quan chữ ký API bị liên kết với hai runtime types không tương thích. `IllegalAccessError` có thể phản ánh runtime package khác nhau dù source package trùng tên.

Để chẩn đoán, so sánh trực tiếp `Class<?>` và `getClassLoader()` ở hai phía. Những lỗi này liên quan **type/linkage/access**, không mặc nhiên chứng minh class unloading hay memory leak.

## 12. Công cụ và chiến lược chẩn đoán thực tế

### 12.1. Truy xuất defining loader từ instance và Class mirror

Một helper dùng trong ứng dụng:

```java
static void describe(Object instance) {
    Class<?> type = instance.getClass();
    System.out.println("type=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

Đây là snippet (cần đặt trong class và truyền instance phù hợp). Nếu class được tạo bởi custom loader với tên hiển thị không ổn định, log thêm ID loader do framework gán cho **phiên bản/plugin session**. `System.identityHashCode(loader)` chỉ hỗ trợ chẩn đoán, không phải ID toàn cục không va chạm.

### 12.2. Quan sát class loading/unloading

JDK/HotSpot có thể cung cấp:

```bash
java -Xlog:class+load=info,class+unload=info -cp app/classes com.example.Main
```

Lệnh dùng dấu cách/argument phù hợp cho Unix shell và Java launcher; thay app/classes và tên main cho dự án thật. Log khi JVM unload class **không** xuất hiện bắt buộc ngay sau close, vì unloading không đồng bộ với API close.

Một số lệnh attach/thống kê tham khảo:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
```

Đây là các ví dụ lệnh cần thay `<pid>`, phụ thuộc JDK/VM, quyền attach và chi phí vận hành. Classloader stats có thể giúp thấy số lượng class/loaders; thread dump giúp xem thread plugin còn chạy và TCCL/stack liên quan. Heap histogram giúp xem instance classes; không một lệnh nào tự chứng minh toàn bộ quy trình dispose đúng.

### 12.3. Phân tích GC roots và reference path

Khi nghi leak:

1. Xác định một loader cũ cụ thể đã lẽ ra phải rời lifecycle.
2. Kiểm tra những class mirror và instance do nó định nghĩa còn được giữ không.
3. Dò **path to GC root** của loader/instance qua heap dump/profiler.
4. Chú ý các static fields thuộc host, event bus, TCCL, ThreadLocal và cache của thư viện chung.
5. Kiểm tra thread còn sống đang thực thi class/plugin code.
6. Xác minh listener/route/metric/MBean/JDBC driver registrations đã được unregister.
7. Theo dõi xu hướng sau nhiều lần load–stop–dispose, thay vì kết luận dựa trên một snapshot.
8. Nếu loader unreachable mà class chưa unload, cân nhắc hoạt động GC/VM và điều kiện đánh giá, không vội gọi đó là bug của ClassLoader.

**Quan trọng:** một plugin có thể cleanup thread đúng nhưng vẫn leak do host cache `Class<?>`. Ngược lại, một cache không giữ class mirror vẫn có thể leak qua plugin instance. Cần xem toàn bộ đồ thị tham chiếu.

## 13. So sánh các trạng thái plugin với tình trạng memory

| Tình trạng | Instance | Class<?> | ClassLoader | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Plugin ACTIVE | Thường reachable | Có định nghĩa runtime | Đang phục vụ | Bình thường |
| Plugin STOPPED nhưng registry chưa dọn | Có thể còn reachable | Có | Thường vẫn reachable | Có nguy cơ leak |
| Plugin DISPOSED, loader đã close | Có thể còn reference ở host/cache | Có thể còn | Có thể còn reachable | Close chưa chứng minh unload |
| Plugin không còn đường root strong reference | Có thể GC thu hồi nếu unreachable | Có thể được VM thu hồi cùng class metadata theo quy tắc | Có thể đủ điều kiện GC | **Có cơ hội** unload, không có deadline |
| GC đã thực sự thu hồi defining loader | Không thể còn instance cần runtime class đó trong heap reachable bình thường | Runtime class liên quan có thể unload theo cơ chế VM | Đã thu hồi | Kết quả quan sát sau GC, không phải do `close()` trực tiếp |

Đây là bảng khái niệm. Thời điểm, allocator, GC mode, class mirror layout và class unloading support phụ thuộc JVM; không áp dụng số liệu thời gian/bộ nhớ cụ thể khi chưa đo.

## 14. Những hiểu lầm phổ biến

**“Mỗi object giữ một bản Class<?> riêng.”** Sai. Instances của cùng runtime class thường trả cùng `Class<?>` mirror.

**“`instance.getClass().getClassLoader()` luôn là loader đã gọi `loadClass`.”** Sai. Nếu parent delegation đã trả class, defining loader có thể là parent/bootstrap.

**“Hai Class cùng tên do hai loader tạo là một kiểu.”** Sai. Runtime type identity gồm binary name và defining loader.

**“Đã gọi `URLClassLoader.close()`, toàn bộ instance do loader tạo phải không dùng được.”** Sai. Existing class/instance có thể tiếp tục dùng; chỉ những hoạt động cần tìm class/resource chưa có mới có thể thất bại.

**“Đặt biến local loader = null là chắc chắn unload.”** Sai. Class/instance/registry/thread có thể giữ loader, GC không có thời điểm bắt buộc.

**“Class<?> chỉ chứa tên nên cache bao nhiêu cũng không ảnh hưởng loader.”** Sai. Cache class mirrors là một dạng strong retention cần kiểm soát.

**“Có vòng reference là JVM không thu hồi được.”** Sai. Reachability từ GC roots mới là điểm quyết định của garbage collection thông thường.

**“System.gc() là cách đo unload chắc chắn.”** Sai. Là yêu cầu/gợi ý GC, không phải barrier đảm bảo class unloading.

**“Metaspace tăng thì chắc chỉ cần gọi close() thêm lần nữa.”** Sai. Cần tìm root paths giữ loader và xem lifecycle/GC thực tế; close không tự thu hồi metadata.

**“ServiceLoader.reload() thay toàn bộ class implementation.”** Sai. Nó chỉ ảnh hưởng cache provider của ServiceLoader instance, không thay defining loader.

## 15. Bài tập tự kiểm tra

**Câu 1.** Hai instance `a` và `b` được tạo từ cùng một runtime class. Phép `a.getClass() == b.getClass()` thường cho kết quả gì?

**Trả lời:** `true`. Chúng dùng cùng class mirror của một định nghĩa runtime.

**Câu 2.** Hai `URLClassLoader` độc lập cùng đọc `plugin.Widget.class`. Tại sao `typeA == typeB` là `false`?

**Trả lời:** Vì defining loaders khác nhau, nên hai runtime classes khác nhau dù tên và bytecode giống hệt.

**Câu 3.** Sau `loader.close()`, `instance.message()` đã được nạp vẫn có thể chạy không?

**Trả lời:** Có thể, nếu mã và những dependencies cần cho lời gọi đã khả dụng. Đóng loader không xóa instance hoặc class đã định nghĩa; không nên suy luận mọi lời gọi đều thành công sau close nếu cần nạp lớp mới.

**Câu 4.** Host giữ `Map<String, Class<?>>` cache type của plugin đã dừng. Đây có thể là nguyên nhân classloader leak không?

**Trả lời:** Có. Reference mạnh tới `Class<?>` có thể giữ định nghĩa class/loader và metadata của plugin sống.

**Câu 5.** WeakReference tới loader chưa được clear ngay sau khi gán local loader = null. Có chứng minh leak không?

**Trả lời:** Không. JVM có thể chưa GC, hoặc còn references khác; phải quan sát GC roots, lifecycle và nhiều chu kỳ.

**Câu 6.** Vì sao một vòng `loader → static object → plugin instance → runtime class` không tự động là leak?

**Trả lời:** Nếu toàn bộ nhóm không còn reachable từ GC roots, garbage collector có thể thu hồi chu trình. Chỉ khi có đường từ root giữ nhóm thì mới là retained data thực sự.

**Câu 7.** Tại sao một thread pool host có thể giữ loader dù manager đã remove plugin khỏi registry?

**Trả lời:** Worker thread có thể giữ TCCL/plugin-defined ThreadLocal value hoặc runnable/callback đang chờ trong queue; cần cleanup trên đúng thread và đóng task/registration.

**Câu 8.** Muốn reload `plugin.Widget` thành bytecode mới, nên tiếp tục gọi `loadClass` trên loader cũ không?

**Trả lời:** Không để thay một định nghĩa đã nạp. Thường cần defining loader mới, ranh giới API chung và lifecycle handoff rõ ràng.

**Câu 9.** Nếu `String.class.getClassLoader() == null`, có phải do `String` không có runtime class không?

**Trả lời:** Không. `null` đại diện bootstrap loader trong API; `String` vẫn là runtime class bình thường của Java.

**Câu 10.** Điều kiện cần của class unloading trong JVMS là gì?

**Trả lời:** Defining class loader của class ấy có thể được garbage collector thu hồi. Điều này không bảo đảm VM đã unload class ngay lúc ứng dụng gọi close/null.

## 16. Checklist thiết kế plugin tránh giữ class/loader ngoài ý muốn

Giữ interface API dùng chung ở loader ổn định; tách implementation theo generation và bảo đảm mỗi resource có owner cleanup. Gỡ plugin instances, callbacks, caches, TCCL/`ThreadLocal`, queued tasks và open resources khi retire.

Đọc `instance.getClass()` / `Class.getClassLoader()` để xác định đúng runtime class và defining loader. Muốn kiểm chứng reclaim, quan sát retaining graph và class unload events theo giới hạn JVM.

## 17. Kết luận và nguồn chính thức

**ClassLoader định nghĩa runtime class; `Class<?>` đại diện runtime class ấy; instance là đối tượng thuộc runtime class.** Chúng được liên kết về danh tính và vòng đời nhưng không bị hủy đồng loạt khi gọi `URLClassLoader.close()`.

Điều kiện để JVM có cơ hội unload class của plugin là **defining loader đủ điều kiện được GC thu hồi**. Class mirrors, instances, threads, TCCL, callbacks, reflection caches và các registry bên ngoài có thể làm loader tiếp tục reachable. Thiết kế plugin đúng phải **dừng hoạt động, hủy đăng ký, đóng resource và bỏ strong references** trước khi kỳ vọng GC/unloading xảy ra; ngay cả khi đó, không có deadline unload được API bảo đảm.

Tài liệu tham khảo:

- JVMS 17 §5.3, *Creation of Classes and Interfaces* (runtime class identity): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVMS 17 §5.5, *Initialization*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- JVMS 17 §5.5/§5.6/§5.7 (including *Unloading*): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java SE 17 `Class` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `URLClassLoader` API, `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `WeakReference` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
