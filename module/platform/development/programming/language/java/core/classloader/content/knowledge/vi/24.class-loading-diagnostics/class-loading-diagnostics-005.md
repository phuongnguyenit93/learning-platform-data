# Chẩn đoán class loading với -verbose:class và -Xlog:class+load trong Java 17

## 1. Vì sao cần quan sát class loading?

Khi gặp lỗi `ClassNotFoundException`, `NoClassDefFoundError`, `ClassCastException`, `NoSuchMethodError`, `LinkageError` hoặc plugin dùng nhầm phiên bản thư viện, câu hỏi quan trọng thường không phải “file `.class` có nằm đâu đó trên máy không?”, mà là:

1. **Runtime đã thực sự nạp/định nghĩa class có binary name nào?**
2. **Class đó được lấy từ nguồn nào** — JDK runtime image, application classpath, JAR, thư mục plugin?
3. **Định nghĩa thuộc class loader nào**, có phải loader mà ứng dụng kỳ vọng?
4. **Lúc nào class được load**, lúc nào class mới được initialize, và lỗi xảy ra ở bước nào?
5. Một lần gọi `loadClass` thứ hai **tái sử dụng `Class<?>` đã có** hay định nghĩa một class mới bởi loader khác?

Java 17 có hai cách chẩn đoán cơ bản:

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

và:

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

Ở HotSpot/JDK 17, cách thứ hai dùng **Unified JVM Logging** với tag set `class+load`. Nó cho phép chọn mức log, đầu ra, decorators, file rotation, cùng nhiều tag khác. Cách thứ nhất là tùy chọn truyền thống còn hỗ trợ để tiện kiểm tra nhanh.

**Một chi tiết phải nhớ:** Tài liệu lệnh `java` của Oracle JDK 17 ánh xạ `-verbose:class` tương đương với:

```text
-Xlog:class+load=info,class+unload=info
```

Vì vậy, nếu chỉ sử dụng `-Xlog:class+load=info`, bạn đã chọn **load events** và **không tự yêu cầu unload events**. Dù cả hai cách có nhiều dòng giống nhau, chúng không nên bị gọi là hai chuỗi tùy chọn đồng nghĩa tuyệt đối.

## 2. Nắm ngữ nghĩa: loading, linking, initialization, unloading

Một runtime class có thể trải qua các giai đoạn khác nhau:

```text
Tên class / yêu cầu lookup
          |
          v
     LOADING
  Tìm/định nghĩa class
          |
          v
     LINKING
  Verify -> Prepare -> Resolve
  (resolution có thể được thực hiện vào những thời điểm phù hợp)
          |
          v
   INITIALIZATION
  <clinit> và static initialization
          |
          v
  Thực thi constructor/method theo nhu cầu
          |
          v
  Có thể UNLOAD khi defining loader đủ điều kiện GC
  và JVM thực sự chọn unloading
```

**Log `class+load` là quan sát quá trình class loading**, không phải log riêng của initialization. Một class có thể đã được load từ trước nhưng `static { ... }` chưa chạy.

Ví dụ:

```java
Class<?> token = Class.forName(
        "demo.trace.PluginMarker", false, pluginLoader);
```

Overload ba tham số `Class.forName(name, initialize, loader)` với `false` **không yêu cầu initialization**. Log `class+load` có thể xuất hiện cho `PluginMarker` trong khi static initializer chưa chạy. Khi method static sau đó được gọi qua reflection, class có thể được initialized.

Cũng đừng đánh đồng **unloading** với việc object instance hết scope. Theo JLS `12.7, class chỉ có thể unload khi **defining loader** đủ điều kiện được garbage collector thu gom; JVM không bảo đảm class sẽ unload trong một lần GC cụ thể. Thiếu log `class+unload` trong demo ngắn **không chứng minh memory leak**.

## 3. -verbose:class cho biết điều gì?

Tùy chọn:

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

yêu cầu Java runtime xuất thông tin class loading qua cơ chế verbose. Trên HotSpot/JDK 17, nội dung thực tế có thể dùng định dạng Unified Logging, ví dụ một dòng có hình thức gần giống:

```text
[0.123s][info][class,load] demo.trace.PluginMarker source: file:/path/to/out/plugin/
```

**Đây là ví dụ dạng log**, không phải timestamp/đường dẫn/stdout cố định. Thời gian, path, dòng log hỗ trợ, decorators, module source, chính sách class loading và số class nạp thay đổi theo JDK, OS và cách chạy.

`-verbose:class` hữu ích khi:

- Cần kiểm tra nhanh liệu một binary name có xuất hiện trong log load.
- Cần nhìn nguồn class ở mức cơ bản khi chẩn đoán classpath trùng JAR.
- Muốn một option quen thuộc và chưa cần cấu hình file/rotation.
- Cần chạy lại một bài test nhỏ rồi đọc toàn bộ các sự kiện load/unload.

**Hạn chế:** Nó thường sinh rất nhiều output từ JDK classes và thư viện framework. Với production, nên lọc theo tên class và dùng Unified Logging để giới hạn đầu ra.

### Có thể dùng -verbose:class để biết chính xác loader object không?

**Không nên mặc định.** Dòng `class,load` ở mức `info` thường có tên class và source, nhưng có thể không hiển thị mọi thông tin identity/parent/loader object mà ứng dụng cần. Cùng một URL hoặc cùng binary name chưa chắc là cùng defining loader.

Trong code, xác nhận độc lập:

```java
ClassLoader actualDefiner = token.getClassLoader();
System.out.println(token.getName());
System.out.println(actualDefiner);
```

Snippet trên yêu cầu biến `token` thuộc `Class<?>`. Nếu cần kết luận identity, so sánh `tokenA == tokenB` và `token.getClassLoader() == expectedLoader`; không chỉ so sánh tên class hoặc tên loader.

## 4. Unified Logging: cú pháp tổng quan của -Xlog

JVM Unified Logging (JEP 158) cho phép cấu hình:

```text
-Xlog:<what>:<output>:<decorators>:<output-options>
```

Các phần:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `what` | Tag selector và mức log | `class+load=info` |
| `output` | Gửi log đến stdout/stderr hoặc file | `stdout`, `stderr`, `file=classload.log` |
| `decorators` | Thông tin kèm mỗi dòng | `uptime,level,tags` |
| `output-options` | Cấu hình output/rotation | `filecount=3,filesize=10M` |

Mẫu dùng phổ biến:

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

Tương đương một biểu diễn tường minh về đầu ra:

```bash
java -Xlog:class+load=info:stdout:uptime,level,tags -cp out/host TraceLoadDemo
```

Với `-Xlog`, output mặc định là `stdout`, và các decorators mặc định thường gồm uptime, level và tags.

Kiểm tra các tag/level/decorators mà chính JVM của bạn hỗ trợ:

```bash
java -Xlog:help
```

**Không tự đoán tag tồn tại trong mọi vendor/version**. Unified Logging thuộc triển khai HotSpot/JDK và tài liệu lệnh `java`; cách hiển thị thực tế có thể khác giữa Java distributions.

### Các mức log

Những mức chính: `off`, `error`, `warning`, `info`, `debug` và `trace`. Mức càng chi tiết thường càng nhiều dòng và chi phí logging càng cao.

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
java -Xlog:class+load=debug -cp out/host TraceLoadDemo
```

Theo tài liệu Oracle JDK 17, `info` dùng cho class loading thông thường; `debug` cho thông tin bổ sung tùy log site. Không bảo đảm rằng mỗi class đều có đúng một dòng `debug` hoặc rằng format của `debug` giữ nguyên giữa JDK updates.

### Tag set không phải dấu cộng logic tùy ý

Trong Unified Logging, `class+load` biểu diễn một **tập tag** gắn với một log event. Không có wildcard, selector thường khớp chính xác tag set được định nghĩa cho event.

```text
class+load=info       -> chọn tag set class+load tại info
class+unload=info     -> chọn tag set class+unload tại info
class*=debug          -> chọn các tag set có class theo wildcard
```

`class*=debug` là cách rộng hơn; nó có thể tạo rất nhiều logs khác liên quan class. Khi học hoặc chẩn đoán một lỗi cụ thể, bắt đầu bằng `class+load=info`, rồi mở rộng sau khi xác định cần thêm loại sự kiện nào.

## 5. Bảng tùy chọn cần nhớ trên JDK 17

| Tùy chọn | Quan sát chính | Trường hợp dùng |
|---|---|---|
| `-verbose:class` | Legacy verbose class information; trên HotSpot JDK 17 tương đương load + unload info | Kiểm tra nhanh |
| `-Xlog:class+load=info` | Class loading events | Xác định class nào/nguồn nào được nạp |
| `-Xlog:class+load=debug` | Loading chi tiết hơn khi log sites có dữ liệu | Điều tra sâu |
| `-Xlog:class+load=info,class+unload=info` | Load và unload | Quan sát vòng đời class loader |
| `-Xlog:class+unload=info` | Unload events thực sự xảy ra | Hot reload/metaspace, không thay thế GC roots analysis |
| `-Xlog:class+resolve=debug` | Constant-pool class/member resolution | Lỗi liên kết hoặc resolution |
| `-Xlog:class+init=info` | Class initialization log | Phân biệt load với static initialization |
| `-Xlog:class+loader+constraints=info` | Các loading constraints được ghi nhận | Nghi vấn linkage across loaders |
| `-Xlog:class+path=info` | Class path details | Nghi vấn classpath sai |
| `-Xlog:class+preorder=debug` | Load/reference preorder diagnostics | Theo dõi tham chiếu trước class load |
| `-Xlog:help` | Tùy chọn/tags mà JVM hỗ trợ | Kiểm tra runtime trước khi áp dụng |

Các ánh xạ `TraceClassLoading`, `TraceClassResolution`, `TraceClassInitialization`, `TraceLoaderConstraints` được tài liệu Java 17 mô tả qua Unified Logging. Không sao chép máy móc flags `-XX:+TraceClassLoading` từ bài hướng dẫn JDK rất cũ: những flags legacy có thể đã bị loại bỏ và làm JVM không khởi động. Chọn `-Xlog` tương ứng.

## 6. Ví dụ Java 17 đầy đủ: nạp class plugin rồi tái sử dụng cùng Class<?>

Ví dụ này cố tình đặt `demo.trace.PluginMarker` **ngoài application classpath** và đưa riêng vào một `URLClassLoader`. Khi chạy, ta thấy một sự kiện load class plugin, nhưng hai yêu cầu lookup vẫn trả **cùng `Class<?>`**.

### 6.1. Cây project

```text
src/
  plugin/
    demo/
      trace/
        PluginMarker.java
  host/
    TraceLoadDemo.java

out/
  plugin/
  host/
```

`out` chưa cần tồn tại; `javac -d` sẽ tạo output packages, còn lệnh shell bên dưới tạo root directories.

### 6.2. PluginMarker.java

Tạo file `src/plugin/demo/trace/PluginMarker.java`:

```java
package demo.trace;

public final class PluginMarker {
    static {
        System.out.println("PLUGIN_INITIALIZED");
    }

    public static String run() {
        return "PLUGIN_OK";
    }
}
```

Static initializer là marker **initialization**, khác thời điểm class được load. Class có method public để host gọi bằng reflection.

### 6.3. TraceLoadDemo.java

Tạo file `src/host/TraceLoadDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class TraceLoadDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("BEGIN_USER_LOOKUP");

        URL pluginRoot = Path.of("out/plugin").toUri().toURL();
        ClassLoader hostLoader =
                TraceLoadDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                "demo-plugin",
                new URL[] {pluginRoot},
                hostLoader)) {

            Class<?> first = Class.forName(
                    "demo.trace.PluginMarker", false, pluginLoader);
            Class<?> second =
                    pluginLoader.loadClass("demo.trace.PluginMarker");

            System.out.println("SAME_CLASS=" + (first == second));
            System.out.println("DEFINED_BY_PLUGIN="
                    + (first.getClassLoader() == pluginLoader));

            System.out.println("BEFORE_STATIC_CALL");
            Object value = first.getMethod("run").invoke(null);
            System.out.println("RESULT=" + value);
        }

        System.out.println("END_USER_LOOKUP");
    }
}
```

Ở đây:

1. `hostLoader` chỉ có host class; không có `demo.trace.PluginMarker`.
2. `pluginLoader` dùng parent-first nhưng parent không thấy class plugin, nên `URLClassLoader` tìm file dưới `out/plugin`.
3. `Class.forName(name, false, pluginLoader)` yêu cầu load nhưng **không yêu cầu initialization**.
4. `pluginLoader.loadClass(name)` trả class đã ghi nhận qua loader đó; không định nghĩa lại class cùng binary name.
5. `first.getClassLoader() == pluginLoader` chứng minh defining loader của class plugin.
6. Reflection gọi static `run` kích hoạt initialization nếu class chưa initialized. Vì thế `PLUGIN_INITIALIZED` xuất hiện sau `BEFORE_STATIC_CALL`.
7. `URLClassLoader.close()` nhờ try-with-resources giải phóng resources của loader; nó **không có nghĩa** class unload ngay sau khi ra khỏi khối try.

### 6.4. Biên dịch và chạy không bật JVM log

Bash (Linux/macOS):

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/trace/PluginMarker.java
javac -d out/host src/host/TraceLoadDemo.java
java -cp out/host TraceLoadDemo
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/demo/trace/PluginMarker.java
javac -d out/host src/host/TraceLoadDemo.java
java -cp out/host TraceLoadDemo
```

**Không thêm `out/plugin` vào `-cp`!** Nếu parent classpath nhìn thấy PluginMarker, một `URLClassLoader` parent-first có thể nhận class từ parent, làm `DEFINED_BY_PLUGIN` thành `false` và phá ý nghĩa bài test.

Stdout **xác định** khi chạy sạch theo cấu trúc trên:

```text
BEGIN_USER_LOOKUP
SAME_CLASS=true
DEFINED_BY_PLUGIN=true
BEFORE_STATIC_CALL
PLUGIN_INITIALIZED
RESULT=PLUGIN_OK
END_USER_LOOKUP
```

Các markers này dùng để đọc log. Khi bật JVM logging, các log lines có thể xen giữa markers nhưng **thứ tự logic của các markers do chương trình in vẫn đúng**.

### 6.5. Bật -verbose:class

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

Khi lọc log, tìm tên:

```text
demo.trace.PluginMarker
```

Một dòng `class,load` tương tự (chỉ minh họa hình dạng):

```text
[0.080s][info][class,load] demo.trace.PluginMarker source: file:/.../out/plugin/
```

Sau đó, gần lời gọi reflection, stdout `PLUGIN_INITIALIZED` xuất hiện; nếu bật thêm `class+init`, có thể quan sát log initialization riêng. Không suy “class đã initialized” chỉ từ class-load log.

### 6.6. Bật riêng class+load

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

Tập trung vào:

- `TraceLoadDemo` được load từ `out/host` hoặc nguồn classpath tương ứng.
- `demo.trace.PluginMarker` được load từ `out/plugin`.
- Runtime cũng nạp nhiều classes thuộc JDK và thư viện cần để chạy. Đừng nhầm các dòng đó là plugin classes.

**Không có bảo đảm mỗi lời gọi `loadClass` sẽ in một log load mới.** Hai lần lookup trong demo trả lại cùng runtime `Class<?>` nên không phải hai class definitions độc lập.

### 6.7. Ghi log ra file thay vì trộn với stdout ứng dụng

Trên JDK 17 HotSpot:

```bash
java -Xlog:class+load=info:file=classload.log:uptime,level,tags \
     -cp out/host TraceLoadDemo
```

Trong PowerShell:

```powershell
java -Xlog:class+load=info:file=classload.log:uptime,level,tags -cp out/host TraceLoadDemo
```

Khi đó **stdout ứng dụng** vẫn là bảy dòng cố định ở phần 6.4, còn JVM class-load logs được ghi trong `classload.log` tại working directory.

Lọc trên Linux/macOS:

```bash
grep -F 'demo.trace.PluginMarker' classload.log
```

Hoặc PowerShell:

```powershell
Select-String -Path classload.log -Pattern 'demo.trace.PluginMarker'
```

Một class-load record phù hợp chứng minh JVM đã ghi nhận loading event của tên class ấy trong lần chạy được quan sát; không dùng duy nhất dòng này để kết luận class loader identity hay authorization.

## 7. Cách đọc một dòng Unified Logging

Một dòng log có hình dạng:

```text
[0.147s][info][class,load] demo.trace.PluginMarker source: file:/.../out/plugin/
```

Các phần:

| Thành phần | Diễn giải |
|---|---|
| `[0.147s]` | Uptime tại thời điểm event, **không phải elapsed time của thao tác load đó** |
| `[info]` | Log level |
| `[class,load]` | Tag set |
| `demo.trace.PluginMarker` | Binary name hiển thị trong record |
| `source: ...` | Nguồn bytes/module/path theo JVM logging |

**Uptime không phải thời lượng nạp lớp.** Chênh lệch giữa hai timestamps cũng có thể bao gồm các công việc khác, JIT, I/O hoặc scheduling; không nên dùng khoảng thời gian đó như một microbenchmark thời gian `ClassLoader.loadClass`.

**Source không phải chứng chỉ niềm tin.** `file:/.../plugin.jar` cho biết JVM báo nguồn class; không chứng minh JAR đã được hash/signed hay được phép thực thi. Nếu cần kiểm tra provenance, phải có cơ chế xác thực artifact riêng.

**Không chắc source là file path.** Nhiều JDK classes đến từ runtime image `jrt:/` hoặc `shared objects file` tùy CDS/JVM. Dynamic/generated classes có thể không có file nguồn thông thường.

## 8. Tách class loading khỏi initialization bằng hai loại dấu vết

Một nhầm lẫn phổ biến: “Tôi thấy class-load log khi `Class.forName(name, false, loader)` chạy, vậy static initializer đã chạy rồi.”

Không đúng. Trong ví dụ:

```text
BEGIN_USER_LOOKUP
[class,load] demo.trace.PluginMarker ...   <-- event loading
SAME_CLASS=true
DEFINED_BY_PLUGIN=true
BEFORE_STATIC_CALL
PLUGIN_INITIALIZED                      <-- static initialization của class
RESULT=PLUGIN_OK
END_USER_LOOKUP
```

Sơ đồ xen kẽ trên **minh họa**, không phải toàn bộ exact stdout/log của một JVM.

Muốn yêu cầu JVM ghi thêm events initialization:

```bash
java -Xlog:class+load=info,class+init=info \
     -cp out/host TraceLoadDemo
```

JDK 17 có mapping cũ `TraceClassInitialization` sang `-Xlog:class+init=info`. Log cụ thể của class initialization phụ thuộc VM, nên đọc marker do chương trình in cùng log `class+init` là cách kiểm tra dễ hiểu.

Các API khác nhau:

| API | Loading? | Initialization? |
|---|---|---|
| `Class.forName(name)` | Yêu cầu class loading/lookup theo loader của class gọi | **Yêu cầu** initialization |
| `Class.forName(name, false, loader)` | Yêu cầu lookup qua loader chỉ định | **Không yêu cầu** initialization |
| `loader.loadClass(name)` | Yêu cầu lookup qua loader | **Không tự yêu cầu** initialization |
| `SomeType.class` | Class literal | Không yêu cầu khởi tạo chỉ vì literal |
| Gọi active static method `SomeType.run()` | Có thể cần class đã load/link | **Có thể kích hoạt** initialization theo quy tắc JVM |

Đừng mặc định initialization luôn xảy ra “ngay sau loading”. JVM resolution/initialization có những quy tắc riêng và một số resolution có thể bị trì hoãn.

## 9. Dùng class-load log để tìm JAR bị chọn nhầm

Giả sử ứng dụng có:

```text
libs/common-v1.jar
plugins/report/lib/common-v2.jar
```

Cả hai chứa `com.example.common.Codec`. Khi plugin gặp `NoSuchMethodError`, một khả năng là plugin biên dịch với v2 nhưng runtime nạp v1 từ parent classpath.

Cách kiểm tra:

1. Chạy lại với `-Xlog:class+load=info` và giữ log.
2. Lọc theo binary name `com.example.common.Codec`.
3. Xem `source` có khớp artifact runtime kỳ vọng hay không.
4. In `Codec.class.getClassLoader()` hoặc lấy token qua plugin loader để xác nhận defining loader.
5. So sánh ABI bằng `javap -classpath ... -s -p com.example.common.Codec` trên hai artifacts.
6. Kiểm tra `parent-first` và vị trí thư viện riêng: nếu parent có cùng binary name, nó có thể che bản private.
7. Giải quyết ở dependency ownership/delegation, không sửa bằng cách bắt `NoSuchMethodError` để bỏ qua.

Lệnh bytecode inspection minh họa:

```bash
javap -classpath libs/common-v1.jar -s -p com.example.common.Codec
javap -classpath plugins/report/lib/common-v2.jar -s -p com.example.common.Codec
```

Đây là ví dụ đường dẫn và tên class cần thay phù hợp dự án. `javap` chỉ kiểm tra **artifact được chỉ định**, không tự chứng minh runtime đã dùng artifact đó; vì thế phải kết hợp class-load log.

### Cùng class name có thể xuất hiện nhiều lần trong log

Hai custom loaders có thể **định nghĩa hai runtime classes khác nhau có cùng binary name**. Không kết luận log trùng tên là VM đã nạp cùng class hai lần trong một loader.

Để xác minh identity:

```java
Class<?> a = loaderA.loadClass("com.example.common.Codec");
Class<?> b = loaderB.loadClass("com.example.common.Codec");

System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
```

Snippet này cần hai loaders đã tạo. Nếu cả hai ủy quyền về cùng parent, `a == b` có thể là `true`. Nếu chúng thực sự tự định nghĩa riêng, `a == b` là `false` dù tên giống nhau. Dòng class log mức info không thay thế phép so sánh class token.

## 10. Debug parent delegation: log class loading nói được gì?

Mặc định `ClassLoader.loadClass(String, boolean)`:

1. Kiểm tra `findLoadedClass(name)`.
2. Nếu chưa có, hỏi parent; nếu parent null, hỏi bootstrap theo contract.
3. Nếu chưa tìm thấy, gọi `findClass(name)`.
4. Resolve class khi `resolve` được yêu cầu.

**Class-load event không phải nhật ký từng nhánh của thuật toán.** Không nhìn thấy `findClass` event không có nghĩa method không từng được gọi; cũng không thể đọc một dòng `class,load` rồi suy rằng parent lookup đã thất bại bao nhiêu lần.

Nếu cần hiểu logic delegation của **custom loader chính mình**, thêm instrumentation có chọn lọc vào loader implementation:

```java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    System.out.println("FIND_CLASS_ATTEMPT=" + binaryName);
    return super.findClass(binaryName);
}
```

Đây là **snippet minh họa** nằm trong subclass `ClassLoader`; method mặc định của superclass ném `ClassNotFoundException`, nên không phải loader đọc JAR thực tế. Trong production, tránh ghi logs vô hạn hoặc rò tên class nhạy cảm.

Có thể kết hợp:

- `-Xlog:class+load=info` để thấy các classes được VM ghi nhận.
- Logs ở `findClass`/factory để thấy nguồn lookup dự kiến.
- `Class.getClassLoader()` để xác nhận defining loader.
- `ClassLoader.getParent()` để kiểm tra parent chain.
- `Thread.currentThread().getContextClassLoader()` khi API sử dụng TCCL.

**Không đánh đồng TCCL và defining loader.** TCCL là trạng thái gắn với thread, trong khi `Class.getClassLoader()` phản ánh loader định nghĩa runtime class. `ServiceLoader.load(service)` dùng TCCL, nhưng `Class.forName(String)` overload một tham số dùng loader của class gọi.

## 11. Kết hợp sự kiện unload với bằng chứng về loader

Muốn xem HotSpot thực sự ghi nhận class unloading, bật riêng `-Xlog:class+unload=info` hoặc kết hợp với `class+load=info`. Việc `URLClassLoader.close()` không tạo cam kết class sẽ unload ngay; JVM chỉ có thể unload khi defining loader đủ điều kiện GC và runtime thực hiện unloading.

Nếu kiểm tra redeploy/metaspace, so nhiều chu kỳ `load → stop → GC/unload` và đối chiếu loader còn sống, references từ threads/TCCL, listeners hoặc caches. **Không thấy unload event trong một lần chạy ngắn chưa chứng minh leak.** Bài tiếp theo dành riêng cho `class+init`/`class+unload`, còn bài JFR/heap dump giải thích cách truy GC roots để tìm holder thật sự.
## 12. Ghi Unified Logs ra file, đặt decorators và rotation

Production logs thường cần giới hạn dung lượng:

```bash
java -Xlog:class+load=info:file=classload-%p-%t.log:uptime,level,tags:filecount=3,filesize=10M \
     -cp out/host TraceLoadDemo
```

- `file=classload-%p-%t.log`: tạo file log; `%p` là PID, `%t` là timestamp khởi động theo Java launcher logging.
- `uptime,level,tags`: giữ thông tin thời gian, mức độ, tag.
- `filecount=3,filesize=10M`: cấu hình log rotation theo kích thước với các giới hạn **xấp xỉ**, không phải SLA lưu giữ chính xác từng byte.
- Đường dẫn log phải có quyền ghi phù hợp; đừng cho người không đáng tin sửa log nếu cần điều tra sự cố.

Log rotation có thể **ghi đè/xóa log cũ** theo cấu hình. Nếu điều tra bắt buộc lưu đầy đủ, chọn retention ngoài runtime hoặc tập hợp log theo quy trình an toàn.

### Ghi vào stderr

```bash
java -Xlog:class+load=info:stderr:uptime,level,tags \
     -cp out/host TraceLoadDemo
```

Việc chọn stdout/stderr/file giúp tách JVM diagnostics với application output. Cần nhớ rằng một số môi trường hoặc log aggregation có thể ghép lại các streams, khiến thứ tự hiển thị liên luồng khác thứ tự flush thực tế.

### Quản lý lượng dữ liệu

Nên bật verbose class logs trong môi trường có kiểm soát để tránh:

- Ghi log hàng chục nghìn classes không liên quan.
- Tăng chi phí I/O và dung lượng đĩa.
- Làm khó phân tích do log rotation.
- Tiết lộ cấu trúc package/artifact paths hoặc thông tin môi trường trong logs.

Ở lần đầu, chạy bài test nhỏ, lọc theo target class. Chỉ tăng mức `debug` hoặc phạm vi tags khi cần thiết.

## 13. JDK 8 và JDK 17: đừng dùng nhầm option legacy

Nhiều bài viết cũ gợi ý:

```text
-XX:+TraceClassLoading
-XX:+TraceClassUnloading
-XX:+TraceClassResolution
```

Các JVM options lịch sử này đã có những thay đổi/loại bỏ trong các JDK mới. Trên JDK 17, tài liệu Oracle hướng dẫn dùng Unified Logging:

```text
-XX:+TraceClassLoading    -> -Xlog:class+load=info
-XX:+TraceClassUnloading  -> -Xlog:class+unload=info
-XX:+TraceClassResolution -> -Xlog:class+resolve=debug
```

Bảng là **mapping khái niệm của legacy options**, không phải các flags nên đưa đồng thời vào lệnh chạy. Trước khi chép một command từ tài liệu cũ, xác nhận version:

```bash
java -version
java -Xlog:help
```

Đặc biệt khi dùng shell scripts deploy qua nhiều Java versions, không áp đặt `-Xlog` của HotSpot/JDK 17 cho runtime cũ không hỗ trợ. Quản lý runtime options theo environment.

## 14. Chẩn đoán exception bằng đúng loại dữ liệu

| Triệu chứng | Class-load log giúp gì? | Còn phải xem gì? |
|---|---|---|
| `ClassNotFoundException` | Tên class đã từng được ghi nhận loading chưa; source có hợp lý không | Loader visibility, binary name, classpath/module path |
| `NoClassDefFoundError` | Những classes/dependencies liên quan đã load từ đâu | Root cause, linkage/init failure, nested `Caused by` |
| `NoSuchMethodError` | Library class thực tế đến từ artifact nào | ABI/method descriptor bằng `javap`; phiên bản compile-time |
| `ClassCastException` | Có thể thấy cùng binary name xuất hiện từ nhiều sources | Runtime `Class<?>` identity và defining loaders |
| `LinkageError` / loader constraint | Tham gia những classes nào, loading order | `class+loader+constraints`, method descriptors, shared API |
| `ExceptionInInitializerError` | Class đã load trước khi lỗi init | `class+init`, `<clinit>`, static dependencies |
| `ServiceConfigurationError` | Provider class có được load không | `ServiceLoader`, TCCL, provider descriptor/module, assignability |
| `IllegalAccessError` / reflection access | Class được load từ module nào | Module readability, `exports`/`opens`, Java access modifiers |
| Metaspace tăng sau reload | Load/unload events qua nhiều cycles | GC roots, old loaders, heap dump, jcmd/JFR |

**Cần phân biệt “log không có class name” và “class chắc chắn không tồn tại”.** Một class có thể chưa từng được yêu cầu nạp, được nạp trong process/run khác, hoặc JVM logging selector không ghi sự kiện bạn cần. Đừng kết luận chỉ từ việc grep không có kết quả.

### Ví dụ phân tích NoSuchMethodError

Giả sử `com.acme.Parser` bản 1 có `parse(String)`, còn bản 2 có thêm `parse(byte[])`. Plugin compile với v2 nhưng runtime parent trả bản 1.

Một hướng điều tra:

1. Ghi stack trace với method gây lỗi.
2. Bật `-Xlog:class+load=info`; lọc `com.acme.Parser`.
3. Đọc `source` của event, kiểm tra JAR/version ở đó.
4. So sánh `javap -s -p` trên JAR v1/v2.
5. Xem parent loader có JAR v1 và plugin loader parent-first không.
6. Sửa dependency layout hoặc plugin isolation theo contract, không catch `NoSuchMethodError` rồi tiếp tục.

Ví dụ chỉ minh họa tình huống ABI mismatch; `NoSuchMethodError` còn có nguyên nhân khác liên quan binary compatibility.

## 15. Công thức quan sát theo mục tiêu

**Muốn biết class nào được JVM nạp:**

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

**Muốn so sánh nhanh với tùy chọn truyền thống:**

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

**Muốn cùng ghi load và unload:**

```bash
java -Xlog:class+load=info,class+unload=info -cp out/host TraceLoadDemo
```

**Muốn phân biệt load và initialization:**

```bash
java -Xlog:class+load=info,class+init=info -cp out/host TraceLoadDemo
```

**Muốn xem class resolution chi tiết:**

```bash
java -Xlog:class+resolve=debug -cp out/host TraceLoadDemo
```

**Muốn tách JVM log khỏi stdout ứng dụng:**

```bash
java -Xlog:class+load=info:file=classload.log:uptime,level,tags -cp out/host TraceLoadDemo
```

**Muốn kiểm tra tag thực sự được runtime hỗ trợ:**

```bash
java -Xlog:help
```

Một quy trình tiết kiệm thời gian thường là: **bật info → lọc binary name → xác định source → xác minh defining loader trong code → chỉ mở thêm debug/resolve/init/constraints khi bằng chứng yêu cầu**.

## 16. Lỗi thường gặp khi đọc log

| Ngộ nhận | Diễn giải chính xác |
|---|---|
| “`-verbose:class` chỉ log load” | Trong mapping của Oracle JDK 17, nó tương đương load và unload mức info |
| “`-Xlog:class+load=info` và `-verbose:class` hoàn toàn giống nhau” | Cách thứ hai còn bao gồm unload trong mapping JDK 17 |
| “Mỗi `loadClass` call tương ứng một dòng class-load mới” | Loader có thể tái sử dụng `Class<?>` đã nạp |
| “Class xuất hiện trong log tức là static initializer đã chạy” | Load và initialize là hai giai đoạn khác |
| “Source path chắc chắn cho biết defining loader object” | Source thường chỉ là nguồn bytes; cần thêm class token/loader identity |
| “Không thấy class trong log nghĩa class không tồn tại” | Class có thể chưa được yêu cầu hoặc log cấu hình khác |
| “Có hai dòng cùng binary name nghĩa duplicate definition trong một loader” | Hai loaders khác nhau có thể định nghĩa cùng tên |
| “Uptime chênh lệch là thời gian load class” | Uptime là thời điểm log, không phải elapsed load cost |
| “Đóng URLClassLoader thì phải có unload event ngay” | Close không quyết định GC/unloading ngay |
| “`class+load=debug` in luôn mọi quan hệ parent/child” | Mức debug phụ thuộc log sites/JDK; xác nhận bằng API/profiler |
| “Cứ bật `class*=trace` ở production là tốt” | Khối lượng log/performance/privacy có thể không chấp nhận |
| “Flags `TraceClassLoading` cũ vẫn chắc chắn chạy trên 17” | Dùng ánh xạ Unified Logging trong tài liệu JDK 17 |

## 17. Bài tập tự kiểm tra

**Câu 1.** `-verbose:class` trong Oracle JDK 17 tương đương cấu hình Unified Logging nào?

**Đáp án:** `-Xlog:class+load=info,class+unload=info` theo tài liệu lệnh `java`.

**Câu 2.** Dùng `-Xlog:class+load=info` có bắt buộc xuất hiện unload events không?

**Đáp án:** Không. Selector này dành cho tag set class+load. Muốn unload, thêm `class+unload=info`.

**Câu 3.** Trong demo, `Class.forName(name, false, pluginLoader)` rồi `pluginLoader.loadClass(name)` trả cùng `Class<?>`. Có bắt buộc hai load events riêng không?

**Đáp án:** Không. Loader có thể dùng class đã nạp/ghi nhận; hai lookup calls không tương đương hai class definitions.

**Câu 4.** `-Xlog:class+load` xuất hiện trước `PLUGIN_INITIALIZED` cho biết điều gì?

**Đáp án:** Class đã được load trước khi static initialization chạy. Không thể suy init đã hoàn tất chỉ từ class-load event.

**Câu 5.** Vì sao log `source: file:/.../plugin.jar` không chứng minh artifact đáng tin?

**Đáp án:** Nó cho biết source theo JVM, không kiểm tra digest/signature/approval của artifact.

**Câu 6.** Nếu plugin nạp `Parser` từ parent v1 thay vì child v2, log có thể giúp gì?

**Đáp án:** Nó có thể chỉ ra source của runtime `Parser`; kết hợp defining loader và `javap` để xác nhận ABI/version mismatch.

**Câu 7.** Vì sao hai custom loaders có thể khiến một binary name xuất hiện nhiều lần trong log?

**Đáp án:** Vì runtime type identity còn có defining loader; mỗi loader có thể định nghĩa một class riêng cùng tên.

**Câu 8.** Có unload log ngay sau `URLClassLoader.close()` là điều chắc chắn không?

**Đáp án:** Không. Close giải phóng resources; unloading phụ thuộc loader có thể GC và quyết định của VM.

**Câu 9.** Một dòng `[0.205s][info][class,load] ...` nghĩa load class mất 205 ms?

**Đáp án:** Không. `0.205s` là uptime của JVM tại thời điểm event, không phải duration của thao tác.

**Câu 10.** Muốn điều tra lỗi `ExceptionInInitializerError` nên kết hợp tag nào?

**Đáp án:** `class+load` với `class+init`, cùng stack trace/static initializer của class.

**Câu 11.** Nếu `grep` không tìm thấy tên class, kết luận class chắc chắn chưa được load được không?

**Đáp án:** Chưa đủ nếu chưa chắc runtime log đang đầy đủ cho process/run và selector liên quan; class có thể chưa từng được yêu cầu hoặc log lọc/rotation.

**Câu 12.** Muốn ghi class load vào file, tách khỏi stdout của ứng dụng, dùng ví dụ nào?

**Đáp án:** `-Xlog:class+load=info:file=classload.log:uptime,level,tags`.

## 18. Tóm tắt và nguồn chính thức

**Năm điểm chính:**

1. **`-verbose:class`** là cách quan sát nhanh và trên HotSpot/JDK 17 có mapping sang **class load + unload info**.
2. **`-Xlog:class+load=info`** là selector rõ ràng cho sự kiện **class loading**; có thể chọn `debug`, output, decorators và rotation.
3. **Class load khác initialization, resolution và unload.** Đọc logs đúng giai đoạn, kết hợp stack trace và các tag phù hợp.
4. **Dòng log không phải bằng chứng đầy đủ về class identity hoặc trust.** Kiểm tra `Class.getClassLoader()`, `Class<?> ==`, classpath/module path và artifact digest khi cần.
5. **Chẩn đoán theo giả thuyết:** xác định binary name/source rồi mở rộng logging có mục tiêu, không bật mọi tag vô hạn.

Tài liệu chuẩn Java 17:

- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-verbose:class`, `-Xlog`, tags/levels/outputs và mapping legacy tracing flags.
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): cấu trúc log levels, tags, outputs, decorators.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation và `findLoadedClass`.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): overload có tham số `initialize` và loader.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nạp class/resources từ URL và `close()`.
- [JLS 17 — `12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization và unloading.
- [JVMS 17 — `5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): quy tắc JVM về class lifecycle.