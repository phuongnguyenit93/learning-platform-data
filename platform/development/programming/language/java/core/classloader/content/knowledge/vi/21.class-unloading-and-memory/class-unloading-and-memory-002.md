# Vì sao không có thao tác unload tùy ý một lớp thông thường trong Java?

Trong Java, ta có thể yêu cầu nạp một class bằng `ClassLoader.loadClass(...)`, `Class.forName(...)` hoặc cơ chế runtime khác. Nhưng Java **không cung cấp một API đối xứng kiểu `Class.unload()`, `ClassLoader.unloadClass("p.Name")` hoặc `System.unloadClass(...)` để ứng dụng tự xóa ngay một lớp thông thường đã được JVM định nghĩa**.

Đây không phải thiếu sót ngẫu nhiên. Một runtime class liên quan đến **định danh kiểu, các instance còn sống, method đang chạy, stack frames, field/method references đã liên kết, static state, reflection và class loader**. Xóa riêng một class bất kỳ theo ý ứng dụng có thể làm mất tính nhất quán của chương trình đang hoạt động.

Thay vào đó, **class unloading là cơ chế tùy JVM, có liên hệ với khả năng garbage collector (GC) thu hồi defining class loader**. Với class/interface thông thường, nguyên tắc của **Java Language Specification (JLS) `12.7`** là: class/interface **chỉ có thể được unload khi defining loader của nó có thể được GC thu hồi**. Nhưng đủ điều kiện thu hồi không phải lời hứa rằng JVM sẽ unload vào một thời điểm xác định. Class unloading là một tối ưu hóa quản lý bộ nhớ, và chương trình hợp lệ **không được phụ thuộc vào việc một class có được unload hay không**.

> Ghi nhớ trước: **ngừng sử dụng plugin → tháo references → loader có thể trở nên collectible → JVM có thể unload classes**. Không có mũi tên nào trong chuỗi này có nghĩa “ngay lập tức và chắc chắn”.

## 1. Phân biệt load, link, initialize, stop, close và unload

Các từ sau thường bị dùng lẫn:

| Khái niệm | Ý nghĩa thực tế | Có xóa runtime class không? |
|---|---|---|
| **Loading** | JVM tìm/tạo `Class<?>` theo binary name và loader | Không |
| **Linking** | Verification, preparation và có thể resolution theo JVM | Không |
| **Initialization** | Chạy logic `<clinit>`: static initializers/field initializers khi cần | Không |
| **Stop plugin** | Quy trình nghiệp vụ ngừng nhận request, đóng services, unregister handlers | Không tự động |
| **`URLClassLoader.close()`** | Giải phóng resource/JAR/file handles do loader này quản lý trong phạm vi API | **Không** unload classes đã tải |
| **`System.gc()`** | Gợi ý JVM thực hiện GC; không bảo đảm xử lý ngay, không chỉ định class | **Không** phải unload command |
| **Class unloading** | JVM giải phóng định nghĩa class/metadata theo điều kiện và chiến lược của nó | Có, khi JVM quyết định |
| **`Instrumentation.redefineClasses`** | Thay một số nội dung định nghĩa theo giới hạn instrumentation | **Không** phải xóa class |
| **`ClassLoader#defineClass` ở loader mới | Tạo runtime class thuộc một namespace loader khác | Không xóa class cũ |

**Điểm quan trọng:** `ClassLoader.close()` là thao tác lifecycle **nguồn tải**, còn **class unloading** là thao tác quản lý **định nghĩa runtime class**. Chúng có thể nằm trong cùng kế hoạch dỡ plugin nhưng **không đồng nghĩa**.

## 2. Tại sao không thể đơn giản “xóa tên class khỏi JVM”?

Một class trong JVM không chỉ là tệp `.class` hoặc tên chuỗi. Với class/interface thông thường, runtime identity được xác định bằng:

```text
(binary name, defining class loader)
```

Ví dụ:

```text
Loader-A defines app.Plugin
  -> runtime type (app.Plugin, Loader-A)

Loader-B defines app.Plugin
  -> runtime type (app.Plugin, Loader-B)
```

Hai runtime types này **khác nhau**, dù tên nhị phân trùng và bytecode có thể giống hệt. Một object của bản A không tự biến thành object bản B.

Một class đã định nghĩa có thể liên quan đến:

1. **Instance trên heap**: JVM phải biết kiểu, layout, virtual method dispatch và metadata tương ứng.
2. **Static fields**: một bản trạng thái tĩnh cho mỗi runtime class; giá trị có thể trỏ đến các objects, services và tài nguyên.
3. **Method đang thực thi**: call stack có thể đang chứa frame của class đó.
4. **References trong bytecode khác**: liên kết fields/methods/type descriptors, resolution và các loader constraints.
5. **Reflection**: các object `Class<?>`, `Method`, `Field`, `Constructor`, `MethodHandle` có thể gắn với kiểu.
6. **Kế thừa và interfaces**: subclasses/implementations có thể đã được nạp và dùng class đó.
7. **Runtime services**: proxy, serialization, JNI, exception handling hoặc framework caches có thể nắm metadata liên quan.

Nếu có API `unloadClass("app.Plugin")` trả về thành công ngay, JVM phải xử lý chuyện gì xảy ra với các object còn sống, frame đang chạy và code khác gọi method của class này sau đó. Java tránh cung cấp một hành động thiếu định nghĩa rõ về mặt semantics như thế.

### Ví dụ suy luận

```java
Object plugin = createPlugin();
Class<?> type = plugin.getClass();
Method method = type.getMethod("run");
```

Đây là **snippet minh họa**, chưa runnable độc lập vì `createPlugin()` và method `run` cần được định nghĩa.

Nếu ngay sau đó ta “xóa class theo tên”, `plugin` vẫn là một Java object, `type` vẫn đại diện runtime type, và `method` còn dùng để gọi code. Một JVM không thể giả định những references ấy tự biến mất chỉ vì ứng dụng muốn thay thế JAR.

**Không phải JVM hoàn toàn không thể quản lý lại metadata**, mà JVM phải đảm bảo class unloading diễn ra khi **các điều kiện thu hồi an toàn** được thỏa, thay vì ở một thời điểm tùy ý do một dòng lệnh ứng dụng quyết định.

## 3. Điều kiện class unloading theo JLS `12.7`

**JLS `12.7` — Unloading of Classes and Interfaces** quy định:

- Một implementation **có thể** unload classes/interfaces.
- Một class/interface **chỉ có thể** bị unload nếu **defining class loader của nó có thể được garbage collector thu hồi**.
- Classes/interfaces được **bootstrap loader** nạp **không thể bị unload** theo quy tắc JLS.
- Việc unload là **optimization**, và chương trình không được phụ thuộc vào quyết định unload.

Sơ đồ tư duy:

```text
Class p.A được loader L định nghĩa
           |
           v
Còn reference khiến L chưa collectible?
           |
    +------+------+
    |             |
   Có           Không
    |             |
    v             v
Không đủ      L có thể eligible
điều kiện     để GC thu hồi
để unload          |
                  v
         JVM có thể unload classes
         do L định nghĩa, khi phù hợp
```

Đây là **quan hệ điều kiện cần**, không phải thuật toán GC chính xác. Đừng hiểu “không còn biến địa phương tên `loader`” tự động chứng minh L đã không còn reachable: có thể còn references khác qua objects/classes/threads/registries.

### “Defining loader” khác “loader đã gọi loadClass”

```java
Class<?> type = child.loadClass("java.lang.String");
```

Một child loader có thể chỉ **ủy quyền** lên parent/bootstrap. Với `String`, defining loader trên JDK thông thường là bootstrap; `type.getClassLoader()` trả `null`. Hủy child loader **không làm `String` trở thành eligible for unloading**.

Nếu muốn quản lý vòng đời plugin, phải xác định **loader thực sự định nghĩa các private classes của plugin**, không chỉ loader mà plugin manager dùng để gọi `loadClass`.

### Unload là quyền của VM, không phải yêu cầu bắt buộc

Ngay cả khi một class loader đã trở nên unreachable và đủ điều kiện thu hồi, ứng dụng vẫn **không thể chỉ định thời điểm** GC chạy hoặc class metadata được giải phóng. Những hành vi có vẻ thành công trên một JDK/GC configuration có thể khác trên JDK/GC hoặc workload khác. Vì vậy logic nghiệp vụ như cập nhật plugin, xóa file, làm sạch registry phải dựa vào **lifecycle do ứng dụng điều khiển**, không dựa vào “GC đã unload lớp X rồi”.

## 4. Tại sao đóng URLClassLoader vẫn dùng được class đã nạp?

`URLClassLoader.close()` quản lý resource và khả năng tìm class/resource mới từ URL của loader. Class đã được định nghĩa **không bị xóa**, instance đã tạo vẫn mang runtime type cũ, và method đã liên kết có thể tiếp tục chạy khi còn tham chiếu hợp lệ.

Đó là lý do `close()` không tương đương với `unloadClass`. Ví dụ chạy được ở phần 5 kiểm tra điều này, đồng thời nạp phiên bản mới bằng một defining loader khác.

## 5. Demo Java 17+: close không unload, loader mới tạo kiểu mới

Demo có hai class nguồn, trong hai output directories tách biệt:

```text
class-unload-demo/
├── src/
│   ├── plugin/
│   │   └── Greeting.java
│   └── app/
│       └── UnloadDemo.java
└── out/
    ├── plugin/
    └── app/
```

**Mấu chốt:** Runtime classpath **chỉ chứa `out/app`**. Plugin class `plugin.Greeting` được hai đối tượng `URLClassLoader` khác nhau định nghĩa từ `out/plugin`.

### 5.1. Tệp src/plugin/Greeting.java

```java
package plugin;

public final class Greeting {
    private static int visits;

    static {
        System.out.println("Plugin initialized");
    }

    public static String greet() {
        return "hello " + (++visits);
    }
}
```

`visits` là **static field** thuộc runtime class. Mỗi defining loader sẽ có một bản `plugin.Greeting` độc lập và một giá trị `visits` độc lập.

### 5.2. Tệp src/app/UnloadDemo.java

```java
package app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadDemo {
    public static void main(String[] args) throws Exception {
        URL url = Path.of(args[0]).toUri().toURL();
        ClassLoader parent = UnloadDemo.class.getClassLoader();

        try (URLClassLoader first =
                new URLClassLoader(new URL[] {url}, parent)) {

            Class<?> original =
                    first.loadClass("plugin.Greeting");

            System.out.println("Same class in one loader: "
                    + (original ==
                       first.loadClass("plugin.Greeting")));

            System.out.println("First call: "
                    + original.getMethod("greet").invoke(null));

            // Giải phóng nguồn loader; class hiện có vẫn sử dụng được.
            first.close();

            System.out.println("After close: "
                    + original.getMethod("greet").invoke(null));

            try (URLClassLoader second = new URLClassLoader(
                    new URL[] {url}, parent)) {

                Class<?> replacement =
                        second.loadClass("plugin.Greeting");

                System.out.println("Different classes: "
                        + (original != replacement));

                System.out.println("First loader identity: "
                        + (original.getClassLoader() == first));

                System.out.println("Second call: "
                        + replacement.getMethod("greet").invoke(null));
            }
        }
    }
}
```

### 5.3. Biên dịch/chạy

Trên Bash (Linux/macOS/Git Bash), từ thư mục `class-unload-demo`:

```bash
mkdir -p out/plugin out/app

javac --release 17 -d out/plugin src/plugin/Greeting.java
javac --release 17 -d out/app src/app/UnloadDemo.java

java -cp out/app app.UnloadDemo out/plugin
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/plugin, out/app | Out-Null
javac --release 17 -d out/plugin src/plugin/Greeting.java
javac --release 17 -d out/app src/app/UnloadDemo.java
java -cp out/app app.UnloadDemo out/plugin
```

**Đầu ra đã biên dịch/chạy và kiểm chứng** với `javac --release 17` trên OpenJDK 24:

```text
Same class in one loader: true
Plugin initialized
First call: hello 1
After close: hello 2
Different classes: true
First loader identity: true
Plugin initialized
Second call: hello 1
```

### 5.4. Giải thích từng dòng

1. **Same class in one loader: true** — `first.loadClass` gọi lại cùng binary name trả cùng `Class<?>` đã được loader đó nạp; không tự định nghĩa hai bản cùng tên trong một loader.
2. **Plugin initialized** — gọi static method `greet` yêu cầu initialization của runtime class do loader `first` định nghĩa.
3. **First call: hello 1** — static field `visits` của class ở loader `first` tăng từ 0 lên 1.
4. **After close: hello 2** — đã gọi `first.close()` nhưng `original` vẫn là một `Class<?>` có thể sử dụng, và method đã nạp vẫn chạy; static field tiếp tục từ 1.
5. **Different classes: true** — loader `second` định nghĩa một runtime class `plugin.Greeting` **khác** với bản `original` dù bytecode và binary name giống nhau.
6. **First loader identity: true** — `original.getClassLoader()` vẫn là `first`, không bị đổi sang `second` bởi `close`.
7. **Plugin initialized** lần nữa — class ở `second` là runtime class mới, có initialization riêng.
8. **Second call: hello 1** — static field của bản `second` bắt đầu từ 0, độc lập với bản cũ.

**Điều ví dụ không chứng minh:** `first` đã được garbage-collected hoặc `plugin.Greeting` V1 đã unload. Thực tế trong code, biến `original` vẫn giữ `Class<?>` V1, nên việc đòi JVM gỡ V1 ngay sau `close` là không hợp lý. Sau khi `main` kết thúc, tiến trình demo thoát; đó là kết thúc JVM process, **không phải một test thực nghiệm class unloading trong cùng JVM**.

### 5.5. Vì sao giữ `original` là quan trọng?

Thử nghiệm giữ một `Class<?>` object đang còn reachable, đồng thời cho thấy class/loader đã nạp không bị “xóa” bởi `close`. Nếu gọi `System.gc()` trong lúc còn giữ reference, cũng không biến object này thành không hợp lệ.

Không nên cố ép test bằng `original = null` rồi assert class chắc chắn unload; `null` cho một local variable **không chứng minh** mọi đường tham chiếu trong chương trình/JVM đã biến mất, và GC không bị buộc chạy đúng lúc bạn muốn.

## 6. Class unloading không giống garbage collection của object

**Instance GC** thu hồi object trên Java heap khi nó không còn reachable theo quy tắc của collector. **Class unloading** liên quan runtime class/metadata và defining loader; **đóng JAR handles** là vòng đời tài nguyên I/O.

Một instance có thể được thu hồi trong khi class vẫn dùng được; một loader có thể đóng JAR nhưng chưa đủ điều kiện reclaim. Không suy ra việc unload chỉ từ `instance = null`, `close()` hay một lần GC.

## 7. Những thứ hay giữ class loader còn sống

Host static cache, listener/event bus, reflection `Class<?>`/`Method` cache, thread pools, `ThreadLocal`, context class loader, scheduled jobs và provider cache là các nhóm tham chiếu điển hình.

Ví dụ: `host registry → plugin callback → plugin Class<?> → defining loader`. Cần gỡ reference tại đúng **owner** thay vì chỉ gọi `loader = null`. Các bài chuyên về cache, threads và ServiceLoader đào sâu từng cơ chế giữ sống và cách xử lý.

## 8. Vòng đời plugin đúng cách

Để ngừng sử dụng plugin có kiểm soát, ngăn request mới trước; sau đó hoàn tất/hủy công việc đang chạy, unregister callbacks, dọn state trên worker threads, close các resource được plugin sở hữu và cuối cùng đóng URL loader nếu có.

Hot reload tạo generation/defining loader mới cho cùng binary name khi cần code mới. JVM tự quyết định thời điểm GC/class unloading sau khi generation cũ không còn reachable. Đây là lifecycle ứng dụng, **không phải API buộc xóa một class đã định nghĩa**.

## 9. Reload class khác với unload class

Ba thao tác cần phân biệt:

### A. Tạo loader mới cho một phiên bản plugin mới

```text
Plugin V1: (com.acme.Widget, LoaderV1)
Plugin V2: (com.acme.Widget, LoaderV2)
```

Có thể coexist trong JVM. Host chọn thế hệ cho công việc mới và cho thế hệ cũ hoàn tất; sau đó xóa references V1. Đây là hướng thường dùng cho hot-reload dựa trên classloader isolation.

### B. Instrumentation redefine/retransform

`java.lang.instrument.Instrumentation` có APIs:

```java
redefineClasses(ClassDefinition... definitions)
retransformClasses(Class<?>... classes)
```

Đây là **tên phương thức API minh họa**, không phải đoạn chương trình chạy độc lập. Instrumentation có giới hạn nghiêm ngặt về redefinition/retransformation tùy JDK/VM và khả năng hỗ trợ của agent.

Các APIs này **không đồng nghĩa dỡ runtime class**. Class identity thường vẫn gắn với runtime class hiện có; các instances và static state không mặc nhiên bị xóa/reset chỉ vì bạn thay bytecode trong những giới hạn được phép. Chúng phù hợp với agents/profilers/hot code replace kiểu nhất định, **không** biến ứng dụng thành nơi có `Class.unload()`.

### C. Restart process/JVM

Kết thúc JVM process giải phóng toàn bộ địa chỉ và runtime state qua hệ điều hành. Đây là một giải pháp **deployment/lifecycle** khác với “unload đúng một class khi JVM vẫn hoạt động”.

Một ứng dụng yêu cầu bảo đảm toàn bộ code không đáng tin được gỡ và tài nguyên hệ thống được cô lập có thể dùng **plugin process riêng** rồi terminate/restart process. ClassLoader đơn lẻ không phải sandbox hay cơ chế bảo đảm xóa mọi side effects của code.

## 10. Vì sao cùng một loader không thể defineClass lần hai để “cập nhật”?

Với một defining loader `L` và binary name `p.Widget`, runtime class identity là `(p.Widget, L)`. Sau khi định nghĩa thành công, JVM không cho bạn `defineClass` lại **một runtime class khác** cùng name trong L chỉ bằng cách gọi lại với bytes mới.

Cố định nghĩa trùng tên có thể dẫn tới `LinkageError` (duplicate class definition). Việc đọc bytecode từ JAR mới không tự thay class cũ: loader có thể trả lại class đã ghi nhận qua `findLoadedClass`/`loadClass`.

Ví dụ giả mã:

```text
Loader L:
  defineClass("p.Widget", bytesV1) -> Class<p.Widget,V1>

  defineClass("p.Widget", bytesV2)
      -> lỗi duplicate definition, KHÔNG thay V1
```

Cách chuyển **thế hệ class** là loader khác (hoặc dùng Instrumentation theo contract nếu thực sự cần thay body/behavior trong giới hạn của nó). Không cố giải quyết bằng cách bỏ cache/`findLoadedClass`: JVM vẫn quản lý identity và liên kết types.

### Tại sao namespace plugin nên đặt dưới loader riêng?

Đặt mọi plugin vào một loader chung giúp chia sẻ classes dễ hơn, nhưng việc cập nhật riêng một implementation thường buộc quản lý một namespace mới cho **cả nhóm**. Với per-plugin loader, có thể thay thế định nghĩa private classes của một plugin mà không đổi class identity của các plugin còn lại, miễn API chung nằm ở parent và lifecycle references được thu dọn.

Đổi lại, những private types từ V1/V2 không cast lẫn nhau, nên host cần giao tiếp bằng **shared SPI/DTO**. Một object thuộc `LoaderV1` không tự trở thành instance kiểu `LoaderV2` dù cùng class name.

## 11. Quan sát class unloading bằng công cụ — không lấy log làm contract

Trên HotSpot, `-Xlog:class+unload=info` có thể ghi lại sự kiện JVM unload class. Event có giá trị như **bằng chứng thực nghiệm** của lần chạy tương ứng, còn không thấy event không chứng minh leak. Không dùng `System.gc()` làm bước kiểm thử có kết quả bắt buộc.

Bài cuối chương đưa ra quy trình quan sát class count, loader generations, log và retaining paths với đúng giới hạn của từng tín hiệu.

## 12. Không lẫn class unloading với các loại “unload” khác

| Thao tác thường bị nhầm | Nó làm gì? | Không làm gì? |
|---|---|---|
| Xóa `.class` hoặc plugin JAR trên disk | Xóa bytes khỏi nguồn cho việc load mới | Không xóa runtime class đã định nghĩa |
| `URLClassLoader.close()` | Đóng resource/JAR handles theo contract | Không hủy Class/instances đã load |
| `ClassLoader.loadClass` trên loader mới | Có thể tạo runtime class identity khác | Không dỡ class cũ |
| `System.gc()` | Yêu cầu/gợi ý xem xét GC | Không chỉ định class unload |
| `WeakReference.clear()` | Xóa reference được giữ trong object WeakReference | Không xóa actual class/loader |
| Clear application cache | Bỏ một đường strong reference | Không bảo đảm tất cả đường reference khác biến mất |
| `ServiceLoader.reload()` | Xóa cache provider của **ServiceLoader object đó** | Không redefine/unload provider classes |
| `Instrumentation.redefineClasses` | Thay định nghĩa được hỗ trợ trong giới hạn VM | Không biến object hiện tại thành class khác |
| Xóa một `ModuleLayer` reference | Bỏ một reference có thể giữ graph module/loader | Không ép các classes trong layer unload |
| Kết thúc JVM process | Chấm dứt toàn bộ runtime process | Không phải API chọn một class giữa runtime còn chạy |

Một file JAR có thể đã được xóa nhưng code vẫn tiếp tục chạy vì JVM đã định nghĩa classes trong bộ nhớ. Ngược lại, đóng JAR handle có thể cần thiết để cập nhật file trên một số hệ điều hành, nhưng đó là vấn đề **file-resource lifetime**, không phải bằng chứng class unloading.

## 13. Các tình huống gây hiểu nhầm thường gặp

### “Mình đã gán loader = null; sao class còn?”

`loader = null` chỉ xóa một reference. Một `Class<?>` hoặc plugin instance còn sống, một thread đang chạy, TCCL hoặc host registry có thể vẫn giữ loader/type liên quan. Cũng có thể JVM chưa thực hiện GC hoặc class unloading dù loader đã đủ điều kiện. Hãy kiểm tra retaining paths.

### “Mình đã close JAR rồi; sao gọi method vẫn được?”

Bởi `URLClassLoader.close()` không invalid classes đã nạp; JavaDoc nêu rõ existing classes/resources vẫn truy cập được. Demo phần 5 chứng minh điều này.

### “Đã deploy V2 mà người dùng vẫn chạy V1”

Host có thể còn reference tới plugin object V1 hoặc cache factory/`Class<?>` của V1. Loader V2 tồn tại không tự thay mọi reference ứng dụng. Cần versioned service registry/atomic handoff/stop old requests theo thiết kế.

### “Metaspace tăng mỗi lần reload plugin”

Mỗi loader generation định nghĩa classes mới và có metadata/caches riêng. Nếu loader cũ còn referenced, memory có thể tiếp tục tăng. Hãy khảo sát classloader statistics, JFR, heap retention, TCCL, threads, caches và native services. **Metaspace tăng không tự chứng minh chỉ có một loại leak**; hoạt động bình thường hoặc collector policy cũng ảnh hưởng quan sát.

### “Không còn instances nên chắc class unload được”

Không đủ: Java cho phép code vẫn giữ `Class<?>`, reflection handles hoặc các runtime references khác. Mặt khác, GC roots cần phân tích theo đồ thị; không phải class nào có static fields cũng tồn tại vĩnh viễn.

### “Có class unloading log thì plugin đã dừng sạch”

Không hẳn. Class unloading nói về runtime class metadata, không xác nhận mọi external side effects (file, network, DB state, process-level property, dữ liệu nghiệp vụ) đã được rollback. Lifecycle cleanup của host vẫn phải được thiết kế độc lập.

## 14. Khi nào class unloading thực sự hữu ích?

Class unloading giúp VM giải phóng metadata của các classes không còn cần thiết khi application thực hiện dynamic loading:

- **Application servers/containers** có nhiều deploy/undeploy cycles.
- **Plugin systems** tạo loader riêng cho các phiên bản plugin.
- **Dynamic code generation** (proxy classes, scripting engines, compilers) với scoped loaders.
- **Hot reload/devtools** tạo nhiều thế hệ class loader.
- **Long-running services** nơi tránh retaining class loaders cũ giúp kiểm soát memory.

Những hệ thống này thường không gọi “unload class X”; chúng **dừng phạm vi sử dụng** (scope) rồi loại bỏ references để GC có thể thu hồi một loader generation.

### Vì sao có những loại class khác như hidden class?

Java còn có **`MethodHandles.Lookup#defineHiddenClass`** dành cho code-generated classes với semantics khác ordinary named classes. Hidden classes có những quy tắc discoverability/lifetime riêng, ví dụ options như `NESTMATE` và `STRONG`.

Đây là cơ chế nâng cao phục vụ dynamic languages/frameworks, **không làm xuất hiện API unload tùy ý cho class thông thường**. Đừng lấy hành vi hidden class làm bằng chứng rằng `ClassLoader.unloadClass("p.Normal")` tồn tại.

## 15. Quy trình quyết định khi muốn “gỡ class” khỏi một hệ thống

Nếu yêu cầu là **ngừng chạy code**:
- Dừng dispatch, unregister services và chờ/cancel active tasks theo contract.
- Không cần chờ class unload mới coi nghiệp vụ đã dừng.

Nếu yêu cầu là **nạp phiên bản mới**:
- Sử dụng loader generation mới hoặc một cơ chế instrumentation phù hợp và có giới hạn rõ.
- Giữ API chung ổn định ở parent, chuyển registry sang V2 có kiểm soát.

Nếu yêu cầu là **giải phóng tài nguyên/JAR handle**:
- Gọi `close` trên loaders/resources có hỗ trợ và cleanup đúng lifecycle.
- Không khẳng định việc đó tự xóa classes.

Nếu yêu cầu là **giảm memory/metaspace**:
- Xác định loader generations cũ còn reachable từ đâu, dọn strong references hợp lệ.
- Dùng logs/JFR/heap analysis để xác minh, không cố “force unload” bằng GC loops.

Nếu yêu cầu là **cô lập code không tin cậy**:
- Class loader không đủ; cân nhắc process isolation, OS permissions, container sandbox và IPC contracts.

## 16. Checklist trước khi retire một plugin loader

- [ ] Host đã ngừng tạo **new work** liên quan plugin cũ.
- [ ] Active requests/tasks được hoàn tất hoặc cancel an toàn.
- [ ] Plugin `stop/close` đã được gọi đúng thứ tự.
- [ ] Schedulers/executors/threads do plugin quản lý đã ngừng.
- [ ] TCCL của threads phục hồi về loader thích hợp.
- [ ] `ThreadLocal`/event listeners/global registries được cleanup.
- [ ] JDBC/MBeans/logging/caches/ServiceLoader provider references được unregister/clear khi cần.
- [ ] Open files, sockets, JAR handles/resources được đóng.
- [ ] Host không giữ `Class<?>`/`Method`/`MethodHandle`/plugin object cũ ngoài scope.
- [ ] Loader mới dùng shared SPI/DTO contracts đúng runtime type identity.
- [ ] Có metrics/logging theo generation để tìm retention bất thường.
- [ ] Không dùng “unload đã xảy ra” làm điều kiện bắt buộc cho request routing.

## 17. Câu hỏi tự kiểm tra

**1. Java có `Class.unload()` hoặc `ClassLoader.unloadClass(String)` cho ordinary class không?** Không có API công khai như vậy.

**2. JLS quy định điều kiện cần nào cho class unloading?** Defining loader của class phải có thể được GC thu hồi.

**3. Nếu loader collectible thì JVM có bắt buộc unload class ngay không?** Không. Unloading là optimization phụ thuộc implementation/GC.

**4. Tại sao `URLClassLoader.close()` không dỡ class?** Vì `close()` đóng nguồn tải và file/resource handles; classes đã nạp vẫn tồn tại và dùng được khi còn hợp lệ.

**5. Tạo loader mới với cùng binary name có cập nhật class cũ không?** Không. Nó tạo runtime type mới với defining loader khác.

**6. Static field được chia sẻ giữa hai bản `plugin.Greeting` do hai loaders khác nhau định nghĩa không?** Không; đó là hai runtime classes có static state riêng.

**7. Không còn plugin instances thì chắc chắn loader được GC chưa?** Chưa; vẫn có thể có `Class<?>`, active threads, host registries hoặc references khác.

**8. Một static field bên trong plugin có tự khiến loader leak vĩnh viễn không?** Không phải luôn luôn; quan trọng là đồ thị có còn reachable từ GC roots bên ngoài không.

**9. `System.gc()` có bảo đảm class unload không?** Không. Nó không phải unload API và không cho chương trình chọn một class để dỡ.

**10. `ServiceLoader.reload()` có unload provider classes không?** Không. Nó xóa provider cache của đối tượng ServiceLoader; lifecycle class vẫn riêng.

**11. Có cần plugin classes unload xong mới cho người dùng chuyển sang V2?** Không. Host có thể chuyển request mới sang V2 sau khi xử lý handoff đúng contract; V1 có thể còn trong bộ nhớ trong thời gian cleanup/GC.

**12. Cách debug loader retention tốt hơn đoán mò là gì?** Quan sát classloader statistics/JFR/heap retaining paths, TCCL và registries; kiểm tra references thực tế.

## 18. Nguồn chính thức

- **Java Language Specification (Java SE 17), `12.7` — Unloading of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- **Java Virtual Machine Specification (Java SE 17), `5.5/`5.3 — Initialization, defining/initiating loaders và runtime class identity:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 API, `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API, `URLClassLoader.close()`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 API, `System.gc()`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- **Java SE 17 API, `Instrumentation`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Java SE 17, `java` command, `-Xlog:class+unload`:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

**Ghi nhớ:** Không tồn tại thao tác **unload tùy ý một class thông thường** vì runtime class phải nhất quán với objects, code đang thực thi, class identity và loader graph. **Ứng dụng điều khiển vòng đời sử dụng; JVM/GC điều khiển unloading.** Muốn hot-reload hoặc giảm memory, hãy quản lý loader generations, cleanup references và quan sát class unloading như một optimization — không làm nó thành điều kiện nghiệp vụ.
