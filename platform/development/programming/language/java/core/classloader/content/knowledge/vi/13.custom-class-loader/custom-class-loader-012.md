# `findLibrary` và trách nhiệm tra cứu thư viện native trong Custom ClassLoader

Khi ứng dụng Java sử dụng JNI (*Java Native Interface*), một lớp Java có thể yêu cầu nạp thư viện native qua `System.loadLibrary("codec")`. JVM lúc đó phải tìm **tệp thư viện của hệ điều hành** tương ứng, ví dụ `codec.dll` trên Windows hoặc `libcodec.so` trên Linux. Nhưng thư viện native không phải `.class` hay resource Java thông thường: nó được hệ điều hành/JVM nạp vào không gian địa chỉ của tiến trình, có vòng đời và lỗi liên kết riêng.

Với **custom class loader**, Java cung cấp điểm mở rộng:

```java
protected String findLibrary(String libname)
```

**`findLibrary` cho loader chỉ ra vị trí tuyệt đối của một native library mà những class do loader ấy nạp yêu cầu.** Nó không thực hiện việc nạp DLL/SO/DYLIB vào bộ nhớ, không định nghĩa Java class và không tự tìm thư viện trong JAR. Khi trả `null`, JVM có thể tìm tiếp theo `java.library.path`. Khi trả một đường dẫn, JVM sử dụng kết quả đó để thử nạp library qua cơ chế native.

Bài thuộc nhóm **Loader tùy chỉnh** của Java core – classloader. Mục tiêu: hiểu đúng lời gọi `findLibrary`, phân biệt `findClass`/`findResource`/`findLibrary`, chọn phương thức nạp native phù hợp, tự xây loader Java 17+ có override, phân tích lỗi JNI và quản lý an toàn thư viện cho plugin.

## 1. Vì sao class loader phải quan tâm thư viện native?

Một framework/plugin có thể được đóng gói thành hai phần:

- **Java classes:** bytecode trong `plugin.jar` hoặc thư mục classes, ví dụ `plugin.NativeEngine`.
- **Native library:** mã máy theo hệ điều hành và kiến trúc CPU, ví dụ `libengine.so`, `engine.dll` hoặc `libengine.dylib`.

Java có thể định nghĩa class plugin qua `URLClassLoader` hoặc custom loader. Nhưng lệnh `System.loadLibrary` phải định vị **bản native tương thích**. Nếu chỉ cấu hình đường tới Java class files, JVM **không mặc nhiên biết** thư viện native nằm ở đâu.

Sơ đồ:

```text
Host application
      |
      v
PluginLoader  ---- loadClass("plugin.NativeEngine") ---> bytecode .class
      |
      | class plugin thực thi System.loadLibrary("engine")
      v
JVM native-library loader
      |
      +-- hỏi PluginLoader.findLibrary("engine")
      |        |
      |        +-- trả absolute path ----> thử mở DLL/SO/DYLIB
      |        |
      |        +-- trả null ------------> thử java.library.path
      |
      v
Liên kết thư viện native vào tiến trình
      |
      v
JNI method được đăng ký/tìm theo quy tắc liên kết JNI
```

Đó là lý do API `ClassLoader` có hai trách nhiệm phân biệt: **định nghĩa/tìm class Java** và **hỗ trợ JVM tìm thư viện native gắn với class do loader nạp**.

## 2. Hợp đồng Java 17 của `ClassLoader.findLibrary`

Chữ ký:

```java
protected String findLibrary(String libname)
```

Theo API Java SE 17:

1. **JVM gọi method này** khi cần định vị thư viện native cho những class đã được nạp bằng loader đó.
2. Tham số `libname` là **tên logic của thư viện** mà lời gọi `loadLibrary` yêu cầu, không phải path tuyệt đối.
3. Kết quả hợp lệ khi tìm được là **chuỗi đường dẫn tuyệt đối tới thư viện native**.
4. Nếu kết quả **`null`**, VM tìm thư viện theo đường tìm thông thường được biểu diễn qua thuộc tính `java.library.path`.
5. **Triển khai mặc định trả `null`**. Subclass muốn quản lý native libraries ở nơi riêng cần override phương thức.
6. `findLibrary` là **`protected`**: không phải API public cho application tự gọi trực tiếp như `ClassLoader.loadClass`.

Điều quan trọng: `findLibrary` là **hook tìm đường dẫn**, không phải factory khởi tạo một class, và cũng không phải nơi nên gọi lại `System.loadLibrary` cho chính `libname`. Gọi như vậy có thể tạo vòng lặp tìm library. JVM đã có trách nhiệm thực hiện bước nạp thật sự sau khi nhận được path.

### So sánh các hook thường thấy trong custom loader

| Hook/API | Đối tượng được tìm | Kiểu kết quả | Ai dùng? |
| --- | --- | --- | --- |
| `findClass(String)` | Java binary name, ví dụ `plugin.Engine` | `Class<?>` | `loadClass`/JVM trong quy trình class loading |
| `findResource(String)` | Resource path, ví dụ `config/default.json` | `URL` hoặc `null` | `getResource`/`getResources` theo quy tắc delegation |
| `findLibrary(String)` | Native library logical name, ví dụ `engine` | **Absolute file path** hoặc `null` | JVM khi xử lý native library loading |
| `System.mapLibraryName(String)` | Logical native library name | Tên file theo nền tảng | Ứng dụng cần ánh xạ `engine` → tên file OS |
| `System.loadLibrary(String)` | Logical native library name | `void` hoặc lỗi | Code Java yêu cầu JVM nạp native library |
| `System.load(String)` | **Absolute native library path** | `void` hoặc lỗi | Code Java biết sẵn file đích, không yêu cầu hook tìm tên logic theo cách `loadLibrary` |

**Không thay `findClass` bằng `findLibrary`**: JVM không coi đường dẫn `.dll` là một Java class. Và `findLibrary` **không được gọi chỉ vì** code đọc một `.so` bằng `ClassLoader.getResourceAsStream`.

## 3. Tên logic, tên file hệ điều hành và đường dẫn tuyệt đối

Khi code viết:

```java
System.loadLibrary("engine");
```

tham số phải là tên thư viện **không kèm** directory path, prefix hoặc extension nền tảng. JVM sẽ xử lý tên logic theo quy tắc nền tảng. Ví dụ thường gặp:

| Hệ điều hành | Logical name | File name thường gặp |
| --- | --- | --- |
| Windows | `engine` | `engine.dll` |
| Linux | `engine` | `libengine.so` |
| macOS | `engine` | `libengine.dylib` hoặc dạng tương thích do runtime hỗ trợ |

Không tự ghép `".dll"` hoặc `"lib" + name + ".so"` cho mọi nền tảng. Sử dụng API:

```java
String nativeFileName = System.mapLibraryName("engine");
System.out.println(nativeFileName);
```

Đây là **đoạn minh họa đặt trong method**; kết quả phụ thuộc OS/JVM, vì vậy không có một stdout cố định dùng chung mọi máy.

Ví dụ cách tạo đường dẫn:

```java
Path nativeDir = Path.of("plugins", "engine", "native");
Path fullPath = nativeDir
        .toAbsolutePath()
        .resolve(System.mapLibraryName("engine"))
        .normalize();

System.out.println(fullPath.isAbsolute());
```

Đây là **đoạn minh họa** (cần `import java.nio.file.Path;`). Trên filesystem bình thường, dòng cuối in `true`. Chỉ mới tạo chuỗi path **không chứng minh** file tồn tại hoặc tải được.

Trong `findLibrary`, thường cần kiểm tra file có thực sự tồn tại là regular file hay không, path có bị thoát khỏi root cho phép không, và OS/CPU architecture có khớp không. Nếu không có bản tương ứng, **trả `null` nếu chính sách cho phép fallback**; hoặc khi muốn fail closed, có thể trả path tới artifact kỳ vọng và để JVM báo lỗi, nhưng phải làm vậy có chủ đích. Không trả chuỗi tương đối như `"native/libengine.so"`.

## 4. Luồng thực thi và loader nào được hỏi?

Phần tinh tế là **loader của class thực hiện lời gọi native loading**.

Giả sử:

```text
                  System/Application loader
                       |  host.NativeHelper
                       |
                       v parent
                 PluginClassLoader
                       |  plugin.NativeEngine
                       |
                       +-- native/engine.dll, native/libengine.so ...
```

Nếu **`plugin.NativeEngine`** (được plugin loader định nghĩa) gọi `System.loadLibrary("engine")` từ static initializer, native lookup được liên hệ với loader của class gọi ấy; JVM có thể gọi **`PluginClassLoader.findLibrary("engine")`**.

Nhưng nếu một method **`host.NativeHelper.loadIt()`** do system loader định nghĩa mới là nơi trực tiếp thực hiện `System.loadLibrary("engine")`, runtime dùng ngữ cảnh của class caller là helper, **không tự suy ra plugin loader** từ object plugin ở stack trên. Do đó override `findLibrary` ở plugin loader có thể **không được gọi** trong trường hợp helper của host thực hiện native load.

Điểm khác biệt này thường gây câu hỏi “tại sao đã override `findLibrary` nhưng không thấy log?”. Hãy kiểm tra **class chứa câu lệnh `System.loadLibrary` đang được defining loader nào nạp**.

Cũng đừng nhầm với **thread context class loader (TCCL)**: `Thread.currentThread().getContextClassLoader()` được một số SPI framework chủ động sử dụng, nhưng JVM không vì thế mà **mặc định** thay loader tra native libraries theo TCCL ở mọi `System.loadLibrary`. Nếu ứng dụng muốn dùng plugin context, hãy thiết kế method load trong class do plugin loader định nghĩa hoặc dùng chiến lược `System.load(absolutePath)` với quyền sở hữu rõ ràng.

### Loader được yêu cầu và defining loader

Một class `plugin.Entry` được gọi qua `customLoader.loadClass(...)` chưa chắc **do** custom loader định nghĩa nếu parent đã có class cùng tên. Lệnh native của `Entry` sẽ hoạt động theo **defining loader thực sự** của class. Luôn kiểm tra:

```java
Class<?> entry = customLoader.loadClass("plugin.Entry");
System.out.println(entry.getClassLoader() == customLoader);
```

Đây là **đoạn minh họa**, với `customLoader` đã được tạo và method xử lý `ClassNotFoundException`. Nếu in `false`, phải điều tra parent delegation/classpath trùng trước khi kết luận `findLibrary` ở custom loader có hiệu lực.

## 5. Ví dụ Java 17+ chạy được mà không cần cài native compiler

Ví dụ cố ý **không cung cấp native library hợp lệ**. Mục đích là chứng minh JVM thực sự gọi `findLibrary` của loader tùy chỉnh, đường dẫn được chọn là absolute path, và lỗi nạp file không tồn tại được báo đúng dạng. Ta sẽ **bắt lỗi được dự đoán**, nên cả chương trình kết thúc bình thường.

### 5.1 Cấu trúc

```text
native-demo/
├── src/
│   └── plugin/
│       └── Entry.java
├── NativeLookupDemo.java
├── plugin-classes/        (output plugin)
└── host-classes/          (output host)
```

Tạo hai thư mục output trước khi compile. Chạy toàn bộ lệnh từ `native-demo`. **Không** đưa `plugin-classes` vào classpath của host.

### 5.2 Class plugin là nơi gọi `System.loadLibrary`

File `src/plugin/Entry.java`:

```java
package plugin;

public final class Entry {
    public static void attemptLoad() {
        System.loadLibrary("step4_missing_native_demo_159");
    }
}
```

Tên thư viện dài và đặc biệt ở đây được cố ý chọn để **không trùng** với library thật trên máy. Không có JNI method để thực thi: mục đích của test là riêng **native lookup**.

### 5.3 Custom loader override `findLibrary`

File `NativeLookupDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.InvocationTargetException;

public class NativeLookupDemo {
    static class PluginLoader extends URLClassLoader {
        private final Path nativeDirectory;

        PluginLoader(URL[] urls, ClassLoader parent, Path nativeDirectory) {
            super(urls, parent);
            this.nativeDirectory = nativeDirectory;
        }

        @Override
        protected String findLibrary(String name) {
            System.out.println("findLibrary: " + name);

            if (!name.equals("step4_missing_native_demo_159")) {
                return null;
            }

            return nativeDirectory
                    .resolve(System.mapLibraryName(name))
                    .toAbsolutePath()
                    .toString();
        }
    }

    public static void main(String[] args) throws Exception {
        Path classes = Path.of("plugin-classes");
        Path nativeDir = Path.of("intentionally-empty-native-dir");

        try (PluginLoader loader = new PluginLoader(
                new URL[] {classes.toUri().toURL()},
                ClassLoader.getPlatformClassLoader(),
                nativeDir)) {

            Class<?> entry = loader.loadClass("plugin.Entry");
            System.out.println("custom defining loader: "
                    + (entry.getClassLoader() == loader));

            try {
                entry.getMethod("attemptLoad").invoke(null);
                System.out.println("unexpected success");
            } catch (InvocationTargetException e) {
                System.out.println("native load error: "
                        + e.getCause().getClass().getSimpleName());
            }
        }
    }
}
```

Chú ý:

- `PluginLoader` extends `URLClassLoader` để tìm `plugin.Entry.class` từ `plugin-classes`.
- Parent = `ClassLoader.getPlatformClassLoader()`, trong ví dụ này không chứa `plugin.Entry`, giúp bảo đảm class plugin do loader tùy chỉnh **định nghĩa thật**.
- `findLibrary` nhận tên logic `step4_missing_native_demo_159` và trả đường dẫn tuyệt đối tới file native **không tồn tại**. Không gọi lại `System.loadLibrary` trong override.
- `getMethod(...).invoke(null)` kích hoạt **static method do class plugin định nghĩa**. Vì lệnh `System.loadLibrary` nằm bên trong `plugin.Entry`, JVM chọn ngữ cảnh loader plugin.
- Method reflection bọc lỗi phát từ target method trong `InvocationTargetException`; test chỉ in tên loại `getCause()`. Nó không coi lỗi native giả lập là thành công.

### 5.4 Biên dịch và chạy

```bash
javac --release 17 -d plugin-classes src/plugin/Entry.java
javac --release 17 -d host-classes NativeLookupDemo.java
java -cp host-classes NativeLookupDemo
```

Kết quả application stdout đã được kiểm tra khi biên dịch bằng `javac --release 17` và thực thi:

```text
custom defining loader: true
findLibrary: step4_missing_native_demo_159
native load error: UnsatisfiedLinkError
```

JDK mới hơn có thể **in thêm cảnh báo native access trên stderr** khi gọi `System.loadLibrary`, trong khi ba dòng application stdout phía trên vẫn đúng. Cảnh báo quyền native access và `UnsatisfiedLinkError` là **hai vấn đề khác nhau**; xem phần Java 17+/JPMS ở cuối bài.

**Không được kết luận việc override thành công chỉ vì `UnsatisfiedLinkError` xuất hiện:** phải nhìn thấy dòng `findLibrary: ...` và xác nhận class plugin thật sự do custom loader định nghĩa. Nếu loader không bao giờ được hỏi, lỗi có thể đến từ `java.library.path` hoặc helper loader khác.

## 6. Tại sao trả `null` lại có ý nghĩa?

Triển khai mặc định của `ClassLoader.findLibrary` trả `null`. JavaDoc quy định khi method này trả `null`, VM tìm library trong đường dẫn do thuộc tính `java.library.path` mô tả.

Triển khai tùy chỉnh thường muốn ưu tiên một thư mục native riêng nhưng giữ fallback:

```java
@Override
protected String findLibrary(String name) {
    Path file = nativeDir.resolve(System.mapLibraryName(name));

    if (java.nio.file.Files.isRegularFile(file)) {
        return file.toAbsolutePath().toString();
    }
    return null; // JVM dùng cơ chế lookup thông thường.
}
```

Đây là **đoạn mã minh họa trong subclass `ClassLoader`**, giả định `nativeDir` có sẵn. Nên chuẩn hóa/kiểm tra path và nguồn thư viện đáng tin trước khi dùng trong ứng dụng thật.

Ba kết quả cần phân biệt:

| `findLibrary` trả | Diễn giải | Kết quả có thể xảy ra |
| --- | --- | --- |
| Absolute path tồn tại, native đúng kiến trúc và dependency đầy đủ | JVM thử load thư viện đích | Thành công hoặc lỗi liên kết/native khác |
| Absolute path không tồn tại, sai bitness hoặc hỏng | JVM đã có ứng viên rõ ràng nhưng không thể nạp | `UnsatisfiedLinkError`, không suy ra sẽ tìm tiếp mọi thư mục |
| `null` | Loader không cung cấp path riêng | JVM thực hiện lookup mặc định theo quy tắc `java.library.path` |

**Không nên dùng return `null` như cơ chế báo “hãy bỏ qua native support hoàn toàn”.** Nó chỉ có nghĩa custom loader không đề xuất đường dẫn; JVM có thể vẫn tìm được và nạp phiên bản khác trong system library path. Nếu plugin cần một phiên bản native **cụ thể và bắt buộc**, thiết kế không được cho fallback vô tình lấy file khác tên trùng từ môi trường.

### `java.library.path` khác `java.class.path`

| Thuộc tính / tùy chọn | Vai trò |
| --- | --- |
| `java.class.path`, `-cp` | Java classes và resources của application classpath |
| `java.library.path`, thường cấu hình khởi động bằng `-Djava.library.path=...` | Đường tìm native libraries khi cơ chế native lookup dùng |
| `System.mapLibraryName` | Tên file native theo OS cho tên logic |
| `PATH` trên Windows, `LD_LIBRARY_PATH` trên Linux, `DYLD_*` trên macOS | Các biến môi trường thuộc cơ chế tìm shared libraries/dependencies của hệ điều hành; hành vi tùy nền tảng/launcher và chính sách bảo vệ |
| `java.home` | Đường tới cài đặt runtime Java, không phải plugin native directory |

Ví dụ một đường tìm native ở startup:

```bash
java -Djava.library.path=./native -cp host-classes NativeLookupDemo
```

Lệnh này chỉ minh họa **cú pháp cấu hình native search path**. Vì test `NativeLookupDemo` chủ động trả absolute path tới file giả không tồn tại, không nên trông chờ `-Djava.library.path` giải cứu lần nạp được override đó.

Trong ứng dụng Java 17, nên quyết định `java.library.path` từ **startup configuration**; đừng viết code thay `System.setProperty("java.library.path", ...)` lúc đang chạy rồi mặc định JVM sẽ lập tức dùng đường mới. JVM có thể cache native-library search configuration và hành vi phụ thuộc runtime.

## 7. `System.loadLibrary` khác `System.load` ở điểm nào?

Hai API có trách nhiệm khác nhau:

```java
System.loadLibrary("engine");
```

- Đầu vào là **tên logic** không kèm path/prefix/extension.
- Thư viện được tìm theo cơ chế native-library lookup phù hợp, bao gồm hook `findLibrary` của loader tương ứng khi JVM yêu cầu.
- Dễ viết portable nếu thư viện được đặt đúng đường tra.

```java
System.load("/opt/myapp/native/libengine.so");
```

- Đầu vào là **đường dẫn tuyệt đối** tới thư viện (ví dụ trên là Linux).
- Không yêu cầu tên logic để `findLibrary` quyết định vị trí.
- Phù hợp khi ứng dụng đã kiểm chứng exact file và muốn chỉ định bản native cụ thể; path không portable nếu hard-code.

Đoạn trên là **minh họa API**, không thể chạy thành công nếu file native chưa tồn tại và chưa được build phù hợp. Đừng dùng `System.load("engine")` rồi kỳ vọng Java tự tìm file từ `java.library.path` như `loadLibrary`; nếu đường dẫn không tuyệt đối, API có thể phát `UnsatisfiedLinkError`.

### Vì sao không gọi `System.load` ngay trong `findLibrary`?

`findLibrary` được JVM gọi **trong lúc** đang cố load native library. Nó chỉ phải trả **path string**. Nếu tự gọi thêm `System.load` hay `System.loadLibrary` bên trong hook, bạn tạo thêm thao tác load khác trong lúc lookup hiện tại chưa xong. Điều này làm tăng nguy cơ reentrancy, lỗi trùng load, deadlock hoặc exception khó chẩn đoán.

Thiết kế đúng:

```text
Java class yêu cầu System.loadLibrary("engine")
                    |
                    v
JVM -> customLoader.findLibrary("engine")
                    |
                    v
customLoader trả "/trusted/native/.../libengine.so"
                    |
                    v
JVM thực hiện load và JNI linking
```

## 8. JNI liên quan tới định danh class loader như thế nào?

Native code **không chạy trong sandbox bytecode Java**. Các hàm JNI dùng pointers/handles tới JVM và liên kết tên symbol hoặc đăng ký native methods. Do đó JNI phải bảo toàn ranh giới giữa các class loaders.

JNI Specification quy định: **mỗi class loader quản lý tập native libraries liên quan tới nó**; cùng một native library JNI **không được load vào hơn một class loader đồng thời**. Nếu cố làm vậy, `System.loadLibrary` có thể phát `UnsatisfiedLinkError`.

Ví dụ tình huống:

```text
PluginLoader A ----loadLibrary("engine")----> /opt/plugin/native/libengine.so
PluginLoader B ----loadLibrary("engine")----> /opt/plugin/native/libengine.so
                                                   |
                                                   v
                                  Có thể lỗi: library already loaded
                                  in another classloader
```

Đây là một **tình huống minh họa**, không phải output chính xác cố định. Quy tắc đặc tả là không dùng đồng thời cùng JNI library trong hai namespace loader khác nhau. Trên thực tế thông báo chi tiết của `UnsatisfiedLinkError` và hành vi path/canonicalization phụ thuộc JVM/OS.

Điều này ảnh hưởng mạnh tới plugin reload:

- Class Java mới có thể được định nghĩa trong loader mới, nhưng bản JNI library ở path cũ có thể vẫn gắn với loader cũ.
- Gọi `URLClassLoader.close()` chỉ đóng các nguồn URL classpath; **không phải lệnh JNI unload**.
- Để native library có thể được unload, loader cũ và các class/object liên quan cần đủ điều kiện GC thu hồi theo các quy tắc JVM.
- JNI `JNI_OnUnload` là hook vòng đời có thể được JVM gọi khi loader chứa native library bị thu hồi; không dùng nó như một callback xảy ra ngay khi gọi `close()`.
- Với native state còn giữ global references, threads hoặc OS resources, việc shutdown phải có hợp đồng rõ, độc lập với JVM GC.

**Không giải quyết xung đột JNI class loader bằng cách tùy tiện copy DLL/SO thành hàng chục đường dẫn mới** nếu native library không hỗ trợ nhiều instance/cùng process. Cách này có thể dẫn đến state duplication, crash và data corruption. Hãy xem thư viện native có hỗ trợ multi-loader/multi-instance không; nếu không, cân nhắc một layer JNI chung ổn định do loader chung sở hữu.

## 9. Lỗi `UnsatisfiedLinkError` không phải chỉ có một nguyên nhân

| Dạng vấn đề | Ví dụ nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| **Library chưa được tìm thấy** | `findLibrary` trả `null`, `java.library.path` không có file | In tên logic, mapped filename, startup native path |
| **Path được trả không hợp lệ** | `findLibrary` trả relative path hoặc absolute path không tồn tại | `Path.isAbsolute()`, `Files.isRegularFile`, normalized/canonical path |
| **Sai kiến trúc** | Chạy 64-bit JVM nhưng chỉ có 32-bit native DLL/SO | Xác minh `os.arch`, file architecture và ABI |
| **Thiếu dependency native** | Main `engine.dll` tồn tại nhưng thư viện C/C++ mà nó phụ thuộc không có | Công cụ loader OS, lệnh dependency inspection phù hợp |
| **Sai JNI symbol/signature** | Library load thành công nhưng lời gọi `native` method không tìm được entry phù hợp | `javac -h`, JNI naming hoặc `RegisterNatives` |
| **Library đã gắn loader khác** | Hai custom loaders thử nạp cùng JNI library | Xác định defining loader của caller và lifecycle plugin |
| **Native access restrictions** | Runtime mới yêu cầu cấp quyền native access cho module caller | Kiểm tra phiên bản JDK, flags và cảnh báo/lỗi về native access |
| **Static linked library khác dynamic** | Runtime tích hợp thư viện native và có `JNI_OnLoad_<L>` | Xem JNI Invocation API; không suy từ việc file vật lý không tồn tại |
| **Bị chặn quyền OS** | File không được phép load, bị quarantine/policy/antivirus | Kiểm tra OS permissions và security logs |

`UnsatisfiedLinkError` là subclass của `LinkageError`. **Đừng bắt rồi im lặng** trong hệ thống production: cần log tên library, đường dự kiến, caller defining loader, OS/architecture và nguyên nhân root. Nếu native setup được gọi trong `static` initializer, lỗi có thể làm class rơi vào trạng thái erroneous; lần dùng sau có thể thấy `NoClassDefFoundError`.

### Library có file trên đĩa vẫn có thể lỗi

Giả sử `findLibrary("engine")` trả `C:\app\native\engine.dll`. Điều đó chỉ giải quyết *vị trí của library chính*. Windows loader vẫn có thể không tìm được dependency DLL thứ hai, hoặc library không phải DLL hợp lệ cho kiến trúc CPU đang dùng.

Tương tự, một `libengine.so` có tồn tại trên Linux vẫn có thể báo lỗi do thiếu `libstdc++.so` tương thích, sai ELF class, symbol bị thiếu hoặc dynamic linker configuration. **Đừng đọc mỗi câu “file exists” rồi kết luận `findLibrary` đã làm xong mọi trách nhiệm end-to-end.**

## 10. Thiết kế `findLibrary` cho plugin an toàn

Một loader plugin có thể có đường native root riêng:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.net.URL;
import java.net.URLClassLoader;

public final class NativePluginLoader extends URLClassLoader {
    private final Path nativeRoot;

    public NativePluginLoader(
            URL[] classUrls, ClassLoader parent, Path nativeRoot) {
        super(classUrls, parent);
        this.nativeRoot = nativeRoot.toAbsolutePath().normalize();
    }

    @Override
    protected String findLibrary(String logicalName) {
        // Chỉ cho phép những library đã biết của plugin.
        if (!logicalName.equals("engine")
                && !logicalName.equals("codec")) {
            return null;
        }

        String fileName = System.mapLibraryName(logicalName);
        Path candidate = nativeRoot.resolve(fileName).normalize();

        if (!candidate.startsWith(nativeRoot)) {
            return null;
        }
        if (!Files.isRegularFile(candidate)) {
            return null;
        }
        return candidate.toString();
    }
}
```

Đây là **class Java độc lập có thể biên dịch với JDK 17+**; chưa thể kiểm thử native loading thực sự nếu `engine`/`codec` native files chưa được cung cấp. Danh sách allowlist, path normalization và kiểm tra regular file giúp giảm lỗi đặt sai file hoặc path traversal. Nhưng trong môi trường không tin cậy, **không đủ để ngăn symlink race**, thay file sau khi kiểm tra hay binary độc hại. Cần xác minh nguồn artifact, quyền filesystem và tính toàn vẹn trước khi JVM nạp library.

**Trách nhiệm thiết kế quan trọng:**

1. **Đặt owner rõ ràng:** plugin nào được quyền sở hữu/đòi native lib nào? Shared JNI library có nên để loader chung nạp một lần?
2. **Xác định platform artifact:** OS, CPU architecture, ABI, runtime C/C++ dependencies tương thích.
3. **Ánh xạ tên portable:** `System.mapLibraryName` thay vì hard-code extension.
4. **Chỉ trả absolute path:** `findLibrary` theo hợp đồng API. Dùng path canonical/real path sau khi đã có artifact, tránh nhầm những location tương đương.
5. **Fail closed khi cần:** nếu không cho phép fallback sang system library cùng tên, cần một chính sách rõ ràng; `return null` không phải fail closed.
6. **Không giữ locks nặng trong hook:** native library loading có thể diễn ra trong initialization và có tương tác bất đồng bộ, tránh recursive load/deadlock.
7. **Log vừa đủ:** ghi logical name và mapping, không rò rỉ path bí mật vào log public.
8. **Quản lý lifecycle:** không unload/reload vội khi vẫn còn native methods, global references hoặc threads chạy.

Nếu thư viện native được **đóng gói bên trong JAR** dưới `native/windows-x64/engine.dll` hay `native/linux-x64/libengine.so`, JVM không thể chỉ nhận một `jar:file:...!/...` URL qua `findLibrary` rồi coi đó là file native trên đĩa. Thông thường plugin manager cần **giải nén tới một thư mục an toàn**, kiểm tra tên/kiến trúc/tính toàn vẹn/quyền truy cập, rồi cho `findLibrary` trả đường dẫn tuyệt đối. Cần quản lý xóa file sau khi không còn library/OS handles đang dùng; có hệ điều hành không cho xóa/thay file đang được load.

## 11. `findLibrary` và phương thức nạp native nằm ở đâu trong kiến trúc?

Một thiết kế dễ bảo trì:

```text
Application host
  |
  +-- Shared Java API (interface/DTO) ở parent loader
  |
  +-- PluginManager
        |
        +-- kiểm tra platform + chữ ký/native artifacts
        +-- chuẩn bị trusted native directory
        +-- tạo PluginClassLoader(class URLs, parent, native directory)
        +-- nạp plugin.Entry do PluginClassLoader định nghĩa
        |
        v
     plugin.Entry (Java code của plugin)
        |
        +-- static { System.loadLibrary("engine"); }
        |             |
        |             v
        |        PluginClassLoader.findLibrary("engine")
        |             |
        |             v
        |        return absolute path
        |             |
        |             v
        |        JVM/OS native loader
        |
        +-- native method / JNI entry
```

**Chủ đích:** logic Java của plugin nên có một điểm rõ ràng chịu trách nhiệm gọi `System.loadLibrary`. Plugin manager quản lý artifact và loader, còn hook `findLibrary` chỉ ánh xạ tên → file hợp lệ. Có thể tách thêm lớp kiểm tra chữ ký, phiên bản và platform compatibility.

Nếu một shared Java host class chứa lời gọi `System.loadLibrary`, hãy cân nhắc cấu trúc JNI bridge ở **loader chung** tương ứng, hoặc explicit absolute load với chính sách sở hữu. Đừng ngẫu nhiên thay TCCL chỉ để mong làm native loader chọn đường của plugin: đó không phải hợp đồng của `findLibrary`.

## 12. Tại sao thêm `-Djava.library.path` vẫn chưa sửa được lỗi?

Một chuỗi tình huống minh họa:

```text
1. plugin.Entry gọi System.loadLibrary("engine")
2. PluginClassLoader.findLibrary("engine") trả C:\plugins\engine-v2.dll
3. File trên không tồn tại hoặc sai kiến trúc
4. UnsatisfiedLinkError xảy ra
5. Đổi -Djava.library.path tới thư mục khác
6. Vẫn có thể lỗi vì findLibrary tiếp tục trả absolute path cũ
```

Nếu `findLibrary` trả một candidate cụ thể, debugger cần kiểm tra chính path ấy. Nếu nó trả `null`, mới xem kỹ `java.library.path` và quy tắc native lookup mặc định.

Một nhầm lẫn khác: người dùng chỉ thêm thư mục DLL vào **Java classpath `-cp`**. Điều đó khiến `ClassLoader` có thể tìm **class/resource Java**, **không bảo đảm** JVM native linker tìm được DLL/SO qua chính classpath. Native library path là cơ chế riêng.

### Khi chạy trong môi trường container

Trong container/Docker:

- File JNI phải được copy/mount vào đúng container filesystem, không phải đường của host OS.
- Linux container cần thư viện theo **Linux ABI/CPU**; Windows DLL không hoạt động chỉ vì tên logic giống.
- Dynamic linker còn cần các dependency native của file chính.
- Native file có thể là resource từ image layer không có quyền ghi hoặc execute; cân nhắc extraction directory phù hợp.
- Nếu dùng custom loader, `findLibrary` nên trả path **bên trong container** đã tồn tại và được xác minh.

## 13. Quản lý native library khi reload/unload custom loader

Native lifecycle khác vòng đời Java classes:

| Sự kiện | Kết quả |
| --- | --- |
| `ClassLoader.loadClass` | Tìm/định nghĩa Java class; không tự nạp native library nếu class chưa thực hiện thao tác yêu cầu |
| `System.loadLibrary` thành công | JVM ghi nhận native library đã được nạp cho ngữ cảnh loader thích hợp |
| `URLClassLoader.close()` | Đóng các nguồn classpath/JAR do URL loader sở hữu; **không là JNI unload API** |
| Loader không còn reachable và GC thu hồi | JVM **có thể** unload các class/native libraries gắn với loader theo quy tắc runtime |
| `JNI_OnUnload` nếu được cung cấp | Hook có thể được gọi khi runtime unload native lib; không phải callback bắt buộc ngay sau close |
| Tạo loader mới cho phiên bản plugin mới | Có namespace Java mới, nhưng vẫn phải xử lý xung đột JNI native library đang gắn loader cũ |

Plugin reload an toàn thường cần:

1. Ngừng yêu cầu mới và đợi mọi Java/native task đang chạy hoàn tất.
2. Ngắt callbacks, shutdown native services theo API của thư viện native và giải phóng JNI global refs nếu có.
3. Unregister listeners, caches, thread locals và context loader references còn giữ plugin.
4. Close nguồn URL của loader khi không còn cần load class/resource mới.
5. Bỏ strong references tới class/loader cũ; chấp nhận rằng GC/class-unloading không có thời điểm bảo đảm.
6. Chỉ mở phiên bản mới sau khi đã giải quyết quy tắc reuse/exclusivity của native lib; nếu cần hard isolation, có thể phải dùng **process riêng**.

Không làm điều này:

```java
oldLoader.close();
System.gc();          // Không bảo đảm unload native lib.
newLoader.loadClass("plugin.Entry"); // Không bảo đảm có thể load lại same JNI.
```

Đoạn trên là **mã minh họa**, không biên dịch độc lập nếu chưa khai báo `oldLoader` và `newLoader`. `System.gc()` là hint, không phải JNI unload operation. Xung đột `already loaded in another classloader` cần thiết kế ownership/lifecycle, không chữa bằng việc ép GC giả định.

## 14. Kiểm thử `findLibrary` mà không làm hỏng môi trường máy

Có ba mức kiểm thử, nên phân biệt:

**Mức A – unit test chỉ ánh xạ path.** Cho loader một `nativeRoot` tạm và tên logic đã biết; kiểm tra hook trả absolute path, không thoát root, và `null` cho tên ngoài allowlist. Vì method là `protected`, test có thể đặt trong subclass cùng package/test helper để gọi bằng wrapper test-only.

**Mức B – integration test thiếu library có chủ đích.** Ví dụ `NativeLookupDemo` ở mục 5 xác nhận JVM **thực sự đi qua** `findLibrary` và báo `UnsatisfiedLinkError` khi không có file. Đây là thử nghiệm JVM lookup, không phải thử nghiệm JNI symbol thực.

**Mức C – integration test với JNI library thật.** Biên dịch Java native declaration, dùng `javac -h` để sinh C header; build DLL/SO/DYLIB tương thích, đặt vào thư mục được map; test native method end-to-end, kiểm tra ABI, dependency và unload/reload semantics. Nên chạy riêng theo OS/architecture trong CI, không dự đoán stdout tuyệt đối khi native code và platform khác nhau.

### Ví dụ khai báo một native method

```java
package plugin;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    public static native int add(int a, int b);
}
```

Đây là **class Java biên dịch được**, nhưng gọi `NativeMath.add(...)` sẽ cần native library thực có JNI implementation đúng tên/signature. Có thể sinh header:

```bash
javac --release 17 -h headers -d plugin-classes src/plugin/NativeMath.java
```

Nếu thực hiện, cần tạo đúng file `src/plugin/NativeMath.java`, thư mục output và native implementation trước khi dùng method; đoạn này minh họa cơ chế, **không tuyên bố đã kiểm thử thư viện C thật**.

Sử dụng `javac -h` giúp tránh đoán JNI mangled names cho overloaded methods. Khi module/native access restrictions của JDK tương lai áp dụng, còn cần khởi chạy JVM với quyền native access theo tài liệu phiên bản JDK.

## 15. Những hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`findLibrary` tự nạp và liên kết DLL.” | Nó **trả đường dẫn**; JVM/OS thực hiện native load và linking. |
| “Mọi subclass `ClassLoader` bắt buộc override `findLibrary`.” | Không; mặc định trả `null`, JVM dùng native lookup path thông thường. |
| “`findLibrary` phải trả `URL` của resource trong JAR.” | Hợp đồng trả **absolute file path string** tới native library. |
| “`System.loadLibrary("engine.dll")` là portable.” | `loadLibrary` nhận tên logic như `engine`, không kèm extension/path. |
| “`System.load` và `System.loadLibrary` giống nhau hoàn toàn.” | `load` nhận **absolute path**; `loadLibrary` nhận **logical name**. |
| “Classpath `-cp` chứa JAR thì JVM sẽ tự tìm DLL trong JAR ấy.” | Không. Native library cần cơ chế file/path/load riêng. |
| “Đổi TCCL là JVM dùng plugin `findLibrary`.” | Không mặc định; phải xem defining loader của class thực hiện native loading. |
| “`findLibrary` trả `null` nghĩa là fail ngay.” | Nó cho phép JVM dùng lookup theo `java.library.path`. |
| “File native tồn tại tức sẽ nạp thành công.” | ABI, dependencies, symbol exports, quyền OS hoặc trùng loader có thể vẫn lỗi. |
| “Hai class loaders cùng load một JNI library mà không liên quan nhau.” | JNI spec hạn chế cùng library nạp vào nhiều class loaders; có thể `UnsatisfiedLinkError`. |
| “`URLClassLoader.close()` giải phóng native lib ngay.” | Close classpath sources khác JNI/native unloading; GC/lifecycle mới liên quan. |
| “`System.gc()` bảo đảm dỡ JNI và reload version mới.” | Không có bảo đảm đó. |

## 16. Tự kiểm tra có đáp án

**1.** `findLibrary("codec")` cần trả gì khi thư viện nằm ở `C:\app\native\codec.dll` trên Windows?

**Đáp án:** Chuỗi **đường dẫn tuyệt đối** đến file đó nếu file là ứng viên đúng. Không trả tên logic `codec` hay đường tương đối `native/codec.dll`.

**2.** Nếu `findLibrary` trả `null`, JVM lập tức phát `UnsatisfiedLinkError` đúng không?

**Đáp án:** Không. Theo Java 17 API, JVM tìm library theo `java.library.path`; chỉ khi không thể tìm/nạp library thì việc load mới có thể thất bại.

**3.** `System.mapLibraryName("engine")` trả gì?

**Đáp án:** **Tên file phụ thuộc nền tảng**; ví dụ Windows thường là `engine.dll`, Linux là `libengine.so`. Không hard-code một output cho mọi OS.

**4.** Vì sao override `findLibrary` trong plugin loader không chạy nếu `host.NativeHelper` gọi `System.loadLibrary`?

**Đáp án:** Loader dùng khi native lookup gắn với class caller trực tiếp yêu cầu load. Nếu `NativeHelper` do system loader định nghĩa, đó không phải plugin loader; TCCL không tự sửa sự lựa chọn ấy.

**5.** Vì sao native library đã được tìm thấy vẫn `UnsatisfiedLinkError`?

**Đáp án:** Có thể sai CPU bitness/ABI, thiếu native dependency, symbol JNI không phù hợp, library đã được loader khác nạp hoặc bị hạn chế bởi OS/JVM. Cần đọc thông báo và kiểm tra nguyên nhân cụ thể.

**6.** Plugin muốn load JNI từ JAR resource. Có thể return `"jar:file:/...!/libengine.so"` từ `findLibrary` không?

**Đáp án:** Không đúng hợp đồng absolute native file path. Thông thường cần extract đến file thật ở trusted directory, xác minh nó và trả đường dẫn tuyệt đối.

**7.** `URLClassLoader.close()` có ngay lập tức giải quyết lỗi library already loaded in another classloader không?

**Đáp án:** Không. Nó đóng nguồn classpath/JAR do loader phụ trách, không tương đương native library unloading. Class loader cũ còn sống/GC chưa thu hồi vẫn có thể gắn native library.

**8.** Mục đích của `System.load("/abs/path/libengine.so")` là gì?

**Đáp án:** Chỉ định file native bằng **absolute pathname**, không cần `findLibrary` map từ tên logic như `System.loadLibrary`. Đường path thực tế vẫn phải hợp OS/ABI và nạp được.

**9.** Nếu `findLibrary` trả path đúng file nhưng ở thư mục plugin không đáng tin, có an toàn không?

**Đáp án:** Không. Native code có quyền tác động trực tiếp vào tiến trình. Cần kiểm tra nguồn artifact, quyền ghi/thay file, symlink/path traversal, chữ ký/hash và isolation nếu code không tin cậy.

**10.** Khi nào nên cân nhắc đưa JNI bridge vào loader chung thay vì mỗi plugin tự nạp?

**Đáp án:** Khi native library không hỗ trợ nhiều class-loader instances hoặc cần chia sẻ native state trong một JVM. Bridge chung cần API contract ổn định, ownership rõ và xử lý concurrent access/native lifecycle.

## 17. Checklist trước khi vận hành custom loader có JNI

1. **Caller đúng:** Class chứa lệnh `System.loadLibrary` được defining loader nào định nghĩa?
2. **Hook đúng:** `findLibrary` có được override tại loader ấy và trả absolute path/`null` đúng hợp đồng?
3. **Mapping đúng:** Logical name, `System.mapLibraryName` và file name theo OS đã khớp?
4. **Root an toàn:** Directory đã normalize/canonicalize, artifact có nguồn đáng tin, không bị thay sau xác minh?
5. **Artifact phù hợp:** OS, architecture, ABI, phụ thuộc native, exports JNI đã kiểm tra?
6. **Module/runtime:** Quyền native access và chính sách runtime có cho phép JNI theo JDK đang chạy?
7. **Không trùng loader:** JNI library có đang được nạp bởi defining loader khác hay không?
8. **Error report:** Ghi loại lỗi và cause, không che mất `UnsatisfiedLinkError` bằng thông báo chung “class not found”?
9. **Lifecycle:** Plugin có stop tasks/native resources, release references, close URL loader đúng lúc không?
10. **Reload:** Cần loader/process mới hay JNI bridge chung để quản lý native library version?
11. **Tests:** Unit mapping + integration thiếu file + test native thật trên từng nền tảng có trong CI.
12. **Fallback rõ:** `return null` có được phép dẫn đến một system library cùng tên nhưng khác version không?

## Kết luận

**`ClassLoader.findLibrary` chịu trách nhiệm trả lời “native library có tên logic này nằm ở absolute path nào đối với lớp do loader này định nghĩa?”**. JVM chịu trách nhiệm **thực hiện load, liên kết và quản lý native library**. Hook trả **absolute path** khi biết file hợp lệ, trả **`null`** khi muốn dùng cơ chế tra mặc định, và không thay thế `findClass`, `findResource`, `System.load` hay `System.loadLibrary`.

Trong ứng dụng plugin, thành công không chỉ là “tìm được file”: còn phải đúng caller loader, tránh trùng JNI giữa loader, đúng OS/ABI, quản lý native file/threads/global refs và có chính sách reload/shutdown. Đây là ranh giới giữa **class loader Java** và **native linker/OS** mà người xây custom loader cần nắm vững.

**Tài liệu chính thức (Java SE 17 / JNI):**

- [`ClassLoader.findLibrary` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String)).
- [`System.load`, `System.loadLibrary` và `System.mapLibraryName` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html).
- [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html).
- [JNI Specification — Invocation API, Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).
