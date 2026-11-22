# 16.6 Quản lý file qua `StandardJavaFileManager` và `ForwardingJavaFileManager`

Khi dùng Java Compiler API (`javax.tools`) để **biên dịch Java lúc chương trình đang chạy**, compiler không nhất thiết đọc nguồn trực tiếp từ một file `.java` rồi ghi class file vào thư mục mặc định. Nó làm việc thông qua một tầng trừu tượng là **`JavaFileManager`**, với các `FileObject` và `JavaFileObject` đại diện cho những tài nguyên đầu vào/đầu ra.

Hai thành phần đặc biệt quan trọng:

- **`StandardJavaFileManager`**: file manager có sẵn của compiler, làm việc với `File`/`Path`, thư mục, JAR và các vị trí tìm kiếm nguồn/class. Đây là lựa chọn thông thường khi muốn đọc `.java`, khai báo classpath/module path, chỉ định nơi ghi `.class` và tái sử dụng file manager giữa các lần compile.
- **`ForwardingJavaFileManager<M extends JavaFileManager>`**: lớp **ủy quyền (decorator)** các yêu cầu của compiler tới file manager khác. Bạn có thể override một số thao tác, ví dụ `getJavaFileForOutput(...)` để lưu bytecode `.class` vào RAM hoặc ghi log, còn các thao tác classpath, platform classes, tìm source và module vẫn **delegate** tới standard manager.

Bản chất của bài không phải học một lệnh `javac` mới, mà là hiểu **compiler chọn nguồn, tìm dependency, tạo output và trả diagnostics thông qua file manager như thế nào**. Khi thiết kế đúng, bạn có thể biên dịch từ file, từ chuỗi Java source hoặc hỗn hợp; có thể thu output vào thư mục hoặc RAM; và có thể lựa chọn chính xác điểm cần tùy biến mà không tự viết lại toàn bộ bộ quản lý file của compiler.

> **Phạm vi thực hành:** Java 17+ với JDK có module `jdk.compiler`. Năm ví dụ `.java` độc lập trong bài đã được biên dịch bằng `javac --release 17` và chạy để kiểm tra stdout. Các ví dụ tạo thư mục tạm khi cần, rồi xóa trong `finally`; không yêu cầu tạo output vào thư mục dự án ngoài quá trình biên dịch chính các ví dụ. Để đơn giản hóa và giữ output xác định, các task dùng `--release 17` và `-proc:none` (không chạy annotation processors).

## 1. Kiến trúc trước khi viết code

Hình dung một lời gọi compile bằng Java Compiler API:

```text
                     ToolProvider.getSystemJavaCompiler()
                                    |
                                    v
                               JavaCompiler
                                    |
                   getStandardFileManager(...)
                                    |
                                    v
                           StandardJavaFileManager
                             |                 |
                    đọc source/JAR      ghi .class ra disk
                             |                 |
                             +--------+--------+
                                      |
                         (có thể bọc decorator)
                                      |
                                      v
              ForwardingJavaFileManager<StandardJavaFileManager>
                 |                                     |
         override 1 vài method                     super.* -> delegate
                 |                                     |
         chặn output .class                       source/classpath/JDK
         ghi vào RAM hoặc log                     theo standard manager
                 \                                     /
                  \                                   /
                   +-------------+-------------------+
                                 |
               JavaCompiler.getTask(..., manager, ...)
                                 |
                           task.call()
                                 |
                         Boolean + diagnostics
```

Một file manager không phải bản thân compiler; nó là **dịch vụ lưu trữ/tìm kiếm** compiler sử dụng. Compiler quyết định cách parse, resolve symbol, type-check và sinh bytecode. File manager quyết định compiler sẽ lấy `JavaFileObject` nào và ghi ra đâu. Đó là lý do bọc standard manager thường đơn giản hơn tự implement toàn bộ `JavaFileManager`.

### 1.1. Ba API cần phân biệt

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| `JavaCompiler` | Tạo compilation task, điều phối compiler | `ToolProvider.getSystemJavaCompiler()`, `getTask(...)` |
| `JavaFileManager` | Hợp đồng SPI đọc/ghi nguồn, class, resource và liệt kê/tìm file | `getJavaFileForOutput(...)`, `list(...)`, `inferBinaryName(...)` |
| `StandardJavaFileManager` | `JavaFileManager` tiêu chuẩn dựa trên filesystem | `setLocationFromPaths(...)`, `getJavaFileObjectsFromPaths(...)` |
| `ForwardingJavaFileManager` | Decorator ủy quyền, override điểm mở rộng | `super.getJavaFileForOutput(...)` hoặc trả memory object |

Các object `JavaFileObject` đại diện từng tệp hoặc từng vùng dữ liệu; chúng không nhất thiết là `java.io.File` thật trên đĩa.

## 2. Dòng đời tiêu chuẩn của một compilation task

Mẫu code thường thấy:

```java
// Fragment minh họa: "sourcePath" và "outputDir" đã được tạo đúng trước đó.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Ứng dụng cần JDK có compiler");
}
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager standard =
             compiler.getStandardFileManager(
                     diagnostics, java.util.Locale.ROOT,
                     java.nio.charset.StandardCharsets.UTF_8)) {
    standard.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, java.util.List.of(outputDir));
    Iterable<? extends JavaFileObject> units =
            standard.getJavaFileObjectsFromPaths(java.util.List.of(sourcePath));
    Boolean ok = compiler.getTask(
            null, standard, diagnostics,
            java.util.List.of("--release", "17", "-proc:none"),
            null, units).call();
}
```

Đây là **fragment**, không chạy độc lập vì `sourcePath`/`outputDir` chưa khai báo. Các chương trình hoàn chỉnh bắt đầu từ mục 5.

Trình tự:

1. Lấy `JavaCompiler` từ `ToolProvider`. Nếu không có compiler trong runtime hiện tại, `getSystemJavaCompiler()` có thể trả `null`; cần kiểm tra sớm thay vì NPE.
2. Tạo `StandardJavaFileManager` với `DiagnosticListener` hoặc `DiagnosticCollector`, `Locale` và `Charset` nếu cần.
3. Chỉ định **vị trí output** và/hoặc vị trí input bằng các API của standard manager; đảm bảo đường dẫn đã tồn tại khi API yêu cầu.
4. Chuyển `Path` hoặc `File` thành `JavaFileObject`, tạo `compilationUnits`.
5. Gọi `compiler.getTask(out, fileManager, diagnostics, options, classes, compilationUnits)` để tạo **một `CompilationTask` mới**.
6. Gọi `task.call()` đúng một lần; `Boolean.TRUE` biểu thị compilation task thành công. Đọc diagnostics kể cả khi kết quả không thành công.
7. Đóng file manager đúng cách sau khi kết thúc; nếu cần load class đã biên dịch, dùng class loader phù hợp sau khi output hoàn tất.

### 2.1. Sáu tham số của `getTask`

| Tham số | Ý nghĩa |
| --- | --- |
| `Writer out` | Nơi compiler ghi các thông báo không được biểu diễn qua diagnostics (hoặc `null` để dùng mặc định) |
| `JavaFileManager fileManager` | Nguồn/tệp đầu ra; có thể là standard manager hoặc forwarding manager |
| `DiagnosticListener<? super JavaFileObject> diagnosticListener` | Nhận lỗi/cảnh báo có cấu trúc, ví dụ `DiagnosticCollector` |
| `Iterable<String> options` | Các lựa chọn trình biên dịch như `--release`, `-proc:none`, `-classpath` |
| `Iterable<String> classes` | Tên lớp liên quan đến annotation processing trong một số chế độ; thường `null` khi biên dịch source |
| `Iterable<? extends JavaFileObject> compilationUnits` | Các nguồn đầu vào; có thể đến từ path hoặc chuỗi trong RAM |

Đừng nhầm `classes` với output `.class`. Nó là tham số khác của API; file manager mới quản lý `JavaFileObject.Kind.CLASS` được tạo bởi compiler.

### 2.2. `Compiler API` không tự load class vừa biên dịch

`task.call() == true` cho biết compilation task thành công, **không** có nghĩa lớp mới đã được nạp vào một class loader để bạn gọi được ngay. Nếu `StandardJavaFileManager` ghi vào thư mục output, một `URLClassLoader` hoặc loader tương thích cần truy cập thư mục đó. Nếu output được giữ trong RAM, bạn phải có loader đọc bytes rồi `defineClass(...)`, hoặc chuyển tiếp bytes tới cơ chế khác thích hợp.

Việc biên dịch và việc thực thi là **hai giai đoạn khác nhau**, có vấn đề class loader, module, bảo mật và vòng đời riêng. Compiler file manager **không phải sandbox** để chạy Java source không tin cậy.

## 3. `StandardJavaFileManager`: lớp nền đọc/ghi file và JAR

`StandardJavaFileManager` là một **interface**, lấy instance bằng:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
StandardJavaFileManager fm =
        compiler.getStandardFileManager(null, null, null);
```

Đây là fragment Java hợp lệ sau khi import tương ứng, nhưng phải có môi trường JDK để `compiler` không null.

Standard manager có thể tạo `JavaFileObject` cho:

- Source file `.java` trên filesystem;
- Class file `.class` trong directory hoặc JAR;
- Một số tài nguyên trong ZIP/JAR theo các `Location` đã cấu hình;
- Nguồn/output được compiler sử dụng khi xử lý package, module hoặc annotation processors.

Bạn không tự instantiate class cụ thể của JDK standard manager bằng `new`. Implementation được compiler cung cấp. Vì thế **không nên kế thừa implementation nội bộ** của nó để tùy biến; `ForwardingJavaFileManager` là cách bọc hợp đồng chuẩn, không phụ thuộc vào class nội bộ của `javac`.

### 3.1. Các method thường dùng

| Method | Dùng khi |
| --- | --- |
| `getJavaFileObjectsFromPaths(Collection<? extends Path>)` | Có danh sách nguồn `.java` được chỉ bằng `Path` |
| `getJavaFileObjects(File...)` / `getJavaFileObjectsFromFiles(...)` | Có file objects `java.io.File` |
| `getJavaFileObjects(String...)` / `getJavaFileObjectsFromStrings(...)` | Có tên tệp dưới dạng string |
| `setLocationFromPaths(Location, Collection<? extends Path>)` | Cấu hình directory/JAR cho một vị trí |
| `getLocationAsPaths(Location)` | Kiểm tra các đường dẫn đã gán cho vị trí |
| `setLocationForModule(...)` | Cấu hình module-oriented location nếu làm module-aware compilation |
| `flush()` | Flush các nguồn output còn đang buffer (không đóng toàn bộ manager) |
| `close()` | Giải phóng tài nguyên liên quan manager, như các handle JAR/file |

**Ưu tiên overload nhận `Collection<? extends Path>`** khi dùng danh sách `Path`. Overload `getJavaFileObjectsFromPaths(Iterable<? extends Path>)` đã được đánh dấu deprecated từ Java 13, một phần để tránh việc vô tình truyền **một `Path` duy nhất**: chính `Path` cũng là `Iterable<Path>` theo các thành phần tên, dẫn tới chọn overload không mong muốn.

Nếu chỉ có một `Path`, dùng `List.of(path)` hoặc `getJavaFileObjects(path)` để diễn đạt rõ “một tệp”, không dùng trực tiếp `getJavaFileObjectsFromPaths(path)` rồi kỳ vọng Java hiểu thành singleton.

### 3.2. Các `StandardLocation` quan trọng

| Location | Ý nghĩa điển hình | Lưu ý |
| --- | --- | --- |
| `StandardLocation.CLASS_PATH` | Nơi compiler tìm class/JAR dependencies cho classpath compilation | Trong compiler API, classpath môi trường có thể khác kỳ vọng; cấu hình rõ khi cần |
| `StandardLocation.SOURCE_PATH` | Tìm nguồn phụ thuộc/khả dụng trên source path | Khác với `compilationUnits` được truyền trực tiếp |
| `StandardLocation.CLASS_OUTPUT` | Ghi output `.class` | Tương đương ý tưởng `javac -d output`, nhưng cấu hình qua file manager |
| `StandardLocation.SOURCE_OUTPUT` | Ghi generated source, thường từ annotation processor | Có thể cần interception riêng nếu output trong RAM |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Nơi tìm annotation processors khi dùng classpath processors | Khác classpath dùng resolve types |
| `StandardLocation.MODULE_PATH` | Tìm module dependencies | Có thể cần logic module-specific như `getLocationForModule(...)` |

Các vị trí đầu vào/đầu ra là **ngữ cảnh** để interpreter của compiler/file manager xử lý tên class và package. Không phải mọi `Location` đều dùng chung một directory hoặc hỗ trợ cùng các thao tác. Ví dụ `CLASS_OUTPUT` là output location; không dùng nó như một danh sách arbitrary source files.

### 3.3. Classpath không đồng nhất với output directory

Khi biên dịch nhiều lần liên tiếp ngoài cơ chế module:

- `CLASS_OUTPUT` cho biết nơi ghi class files;
- `CLASS_PATH` cho biết nơi compiler **đọc** class files như dependencies.

Nếu task B cần type đã được task A biên dịch vào output, cấu hình rõ `CLASS_PATH` chứa output (hoặc truyền `-classpath` tương ứng), thay vì cho rằng output sẽ luôn được tự search. Oracle `javac` cũng khuyến nghị thêm output directory vào classpath khi compilation không dựa vào modules.

Ví dụ 4 thực hiện đúng: dùng cùng manager cho hai compilation tasks tuần tự và đặt cả `CLASS_OUTPUT` lẫn `CLASS_PATH` đến thư mục chung.

### 3.4. Encoding và diagnostic locale

`compiler.getStandardFileManager(listener, locale, charset)` hỗ trợ gán charset đọc source và locale cho diagnostics. Trong các ví dụ:

```java
compiler.getStandardFileManager(
        diagnostics, java.util.Locale.ROOT,
        java.nio.charset.StandardCharsets.UTF_8);
```

Đây là fragment, cần class/import đã có. Lựa chọn charset giúp tránh khác biệt Windows/Linux khi input chứa ký tự tiếng Việt. Khi source là `String` nằm trong `SimpleJavaFileObject`, `getCharContent` trả Unicode chars trực tiếp; charset vẫn có ích cho file/JAR được standard manager đọc.

## 4. `FileObject` và `JavaFileObject`: hợp đồng mà compiler dùng

Hai interface nằm trong `javax.tools`:

- `FileObject`: tệp/resource tổng quát, có thể đọc/ghi qua stream hoặc reader/writer, lấy URI, tên hiển thị, thời điểm sửa đổi;
- `JavaFileObject extends FileObject`: thêm `Kind`, binary name/access level/nesting information và các thao tác tùy loại tệp Java.

`JavaFileObject.Kind` thường gặp:

| Kind | Phần mở rộng | Trường hợp |
| --- | --- | --- |
| `SOURCE` | `.java` | Compilation unit đầu vào, generated source |
| `CLASS` | `.class` | Bytecode compiler sinh ra hoặc class dependency |
| `HTML` | `.html` | Dữ liệu dạng HTML liên quan tới file objects |
| `OTHER` | Không cố định | Resource khác như cấu hình hay artifact ngoài Java |

Một `JavaFileObject.Kind.CLASS` có thể được lưu trong RAM; nó **không phải** một `Path` trỏ tới file `.class` trên đĩa. Đây chính là cách `ForwardingJavaFileManager` chặn output.

### 4.1. URI đúng khi tạo `SimpleJavaFileObject`

Khi tự tạo một nguồn từ chuỗi Java:

```java
// Fragment: binaryName = "demo.mem.MathBox"
java.net.URI uri = java.net.URI.create(
        "string:///" + binaryName.replace('.', '/')
        + JavaFileObject.Kind.SOURCE.extension);
```

URI trở thành `string:///demo/mem/MathBox.java`, có **scheme**, path bắt đầu từ gốc và khớp Java file name. Với output trong RAM, có thể dùng scheme `mem:///...` và `Kind.CLASS`. Javadoc standard manager yêu cầu các URI đại diện file phải tuyệt đối và normalized; khi tự tạo `SimpleJavaFileObject`, nên giữ URI có scheme hợp lệ để diagnostics và compiler có thể định danh rõ.

Một `Source extends SimpleJavaFileObject` thông thường override:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return code;
}
```

Với output, `ByteCode extends SimpleJavaFileObject` thường override:

```java
@Override
public java.io.OutputStream openOutputStream() {
    return byteStream;
}
```

Hai đoạn trên là **fragments**, không có các biến/constructor đầy đủ. Tất cả lớp hỗ trợ được viết hoàn chỉnh trong ví dụ 2–3.

### 4.2. Biên dịch source từ RAM khác output vào RAM

Đây là hai quyết định riêng:

- Input từ RAM: truyền `List.of(new Source(...))` vào `getTask(..., compilationUnits)`.
- Output vào RAM: file manager phải trả `JavaFileObject` mà `openOutputStream()` ghi vào memory buffer khi compiler gọi `getJavaFileForOutput(...)`.

Nếu chỉ tạo source từ chuỗi rồi dùng **standard manager nguyên bản**, compiler vẫn có thể ghi `.class` ra filesystem. Nếu chỉ intercept output `CLASS` nhưng input là `Path`, bạn vẫn có thể compile **từ file disk nhưng sinh output RAM**. Đừng gọi cả hai trường hợp là "fully in-memory" mà không xem rõ input, output, dependencies và annotation processors.

## 5. Thực hành 1 — `StandardJavaFileManager` đọc `Path`, ghi `CLASS_OUTPUT`

Ví dụ tạo source có package `demo.disk` trong thư mục tạm, chạy compiler bằng file manager chuẩn, rồi nạp class từ thư mục output.

Tạo tệp **`DiskCompileDemo.java`**:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class DiskCompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("standard-manager-");
        try {
            Path source = root.resolve("src/demo/disk/Greeter.java");
            Path output = Files.createDirectories(root.resolve("out"));
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package demo.disk; public class Greeter { "
                    + "public static String say(String name) { return \"Hi \" + name; } }",
                    StandardCharsets.UTF_8);
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
                manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(output));
                Iterable<? extends JavaFileObject> units =
                        manager.getJavaFileObjectsFromPaths(List.of(source));
                boolean ok = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, diagnostics,
                        List.of("--release", "17", "-proc:none"),
                        null, units).call());
                System.out.println("compiled: " + ok);
                System.out.println("class exists: "
                        + Files.isRegularFile(output.resolve("demo/disk/Greeter.class")));
                System.out.println("errors: " + diagnostics.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count());
                if (!ok) throw new IllegalStateException("Compilation failed");
            }
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{output.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> type = Class.forName("demo.disk.Greeter", true, loader);
                System.out.println("invoke: " + type.getMethod(
                        "say", String.class).invoke(null, "Ada"));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Lệnh (thực hiện trong một thư mục thử nghiệm riêng, với JDK 17+):

```bash
javac --release 17 DiskCompileDemo.java
java DiskCompileDemo
```

**Stdout chính xác:**

```text
compiled: true
class exists: true
errors: 0
invoke: Hi Ada
```

**Phân tích:**

1. `ToolProvider.getSystemJavaCompiler()` cung cấp compiler. Không có compiler thì chương trình chủ động báo lỗi, thay vì xảy ra NPE.
2. `Files.writeString(...)` tạo một source vật lý dưới `root/src/demo/disk/Greeter.java`. Trong `getTask`, đối tượng source được standard manager tạo từ đúng `Path` đó.
3. `setLocationFromPaths(CLASS_OUTPUT, List.of(output))` khiến output `demo.disk.Greeter` đặt tại `out/demo/disk/Greeter.class`.
4. `--release 17` yêu cầu compiler dùng Java 17 API/source/target phù hợp; `-proc:none` tắt annotation processors trong bài demo để tránh side effects.
5. `DiagnosticCollector` thu diagnostics; bài thành công không có lỗi (số errors bằng 0).
6. `URLClassLoader` đọc class đã sinh sau khi compiler hoàn tất và standard manager được đóng; `Class.forName(..., true, loader)` tìm class theo **binary name**.
7. Cả manager, loader và thư mục tạm được đóng/xóa theo thứ tự. Ví dụ không để một thư mục output do demo tạo tồn tại sau khi chạy thành công.

**Lưu ý:** Biên dịch thành công không tự đồng bộ class loader đang sống để thay thế class đã nạp cùng tên. Nếu cần tải phiên bản mới với cùng binary name, phải thiết kế loader/versioning phù hợp; `StandardJavaFileManager` chỉ là công cụ quản lý file của compiler.

## 6. `ForwardingJavaFileManager`: decorator thay vì viết lại toàn bộ `JavaFileManager`

Khai báo khái niệm:

```java
public class ForwardingJavaFileManager<M extends JavaFileManager>
        implements JavaFileManager
```

Đây là **trích chữ ký API**, không phải code độc lập.

Constructor `protected ForwardingJavaFileManager(M fileManager)` nhận file manager làm **delegate**. Trong subclass, trường `protected final M fileManager` cho phép giữ delegate; các method không override mặc định được chuyển tiếp đến nó theo Javadoc.

Điểm mạnh của mẫu này là **chỉ tùy biến nơi cần**, còn những chức năng phức tạp như platform classpath, JAR handling, module path, package scanning, `list(...)` và `inferBinaryName(...)` có thể dùng implementation chuẩn.

### 6.1. Cách bọc và điều quan trọng khi cấu hình

```java
// Fragment: compiler đã được khởi tạo, output là Path đã tạo.
StandardJavaFileManager standard =
        compiler.getStandardFileManager(null, null, null);
standard.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, java.util.List.of(output));
JavaFileManager decorated = new MyForwardingManager(standard);
```

Đây chỉ là fragment với `MyForwardingManager` chưa khai báo. Cần hiểu: `ForwardingJavaFileManager` **không triển khai interface `StandardJavaFileManager`** chỉ vì nó đang bọc standard manager. Khi bạn giữ reference kiểu `JavaFileManager`, bạn không tự nhiên gọi được `setLocationFromPaths(...)` của standard manager thông qua biến wrapper. Hãy:

- Cấu hình `standard` trước khi bọc, hoặc tiếp tục giữ reference đến standard manager để cấu hình.
- Truyền **wrapper** làm `fileManager` vào `compiler.getTask(...)`, nếu muốn override được gọi.
- Đóng wrapper để delegate đóng underlying manager; tránh tạo hai đường close không được điều phối.
- Không cast một `ForwardingJavaFileManager` thông thường sang `StandardJavaFileManager` chỉ vì generic type parameter `M` là `StandardJavaFileManager`.

### 6.2. Phương thức chặn output Java class

Override phổ biến:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {
    if (location == StandardLocation.CLASS_OUTPUT
            && kind == JavaFileObject.Kind.CLASS) {
        // Có thể ghi log, hoặc trả JavaFileObject dùng RAM.
    }
    return super.getJavaFileForOutput(
            location, className, kind, sibling);
}
```

Đây là **fragment** để hiểu hình dạng override, chưa có class chứa method. `className` thường là **binary class name** như `demo.mem.MathBox` hoặc `demo.mem.MathBox$Inner`, không phải tệp `.class` dưới dạng path. `kind` cho biết nguồn đích thuộc loại `SOURCE`, `CLASS`, v.v.; `location` chỉ bối cảnh output.

`sibling` là hint về nguồn liên quan, có thể null. Hợp đồng của `JavaFileManager` cho phép implementation dùng hint này khi chưa có output directory rõ ràng, ví dụ ghi class file cạnh source. Nếu bạn delegate, chuyển tiếp các tham số nguyên vẹn; nếu tự quản lý output, phải quyết định mapping hợp lệ từ className và location đến file object.

### 6.3. Không override đồng nghĩa với delegate, không phải mất chức năng

Một `LoggingManager` chỉ override `getJavaFileForOutput` có thể tiếp tục dùng:

- `list(...)` để compiler tìm classes trong packages;
- `getJavaFileForInput(...)` để đọc dependencies;
- `inferBinaryName(...)` để compiler suy tên class;
- `getClassLoader(...)`/`handleOption(...)` theo delegate;
- `close()`/`flush()` theo delegate.

Điều này chỉ đúng trong phạm vi các method được forwarding implementation thực sự delegate; nếu bạn tạo một custom file manager **không dùng decorator**, các SPI method cần được triển khai hợp lệ, tránh giả định mọi method đều hoạt động.

## 7. Thực hành 2 — Override output chỉ để log, vẫn ghi file thật

Tạo **`ForwardingLogDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ForwardingLogDemo {
    static final class Source extends SimpleJavaFileObject {
        Source() {
            super(URI.create("string:///demo/log/Check.java"), Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return "package demo.log; public class Check { "
                    + "public static class Child {} }";
        }
    }

    static final class LoggingManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final List<String> outputs = new ArrayList<>();

        LoggingManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                outputs.add(className);
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("forwarding-log-");
        try {
            Path output = Files.createDirectories(root.resolve("out"));
            StandardJavaFileManager standard = compiler.getStandardFileManager(
                    null, null, StandardCharsets.UTF_8);
            try (LoggingManager manager = new LoggingManager(standard)) {
                standard.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(output));
                boolean ok = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null,
                        List.of("--release", "17", "-proc:none"),
                        null, List.of(new Source())).call());
                Collections.sort(manager.outputs);
                System.out.println("compiled: " + ok);
                System.out.println("logged: " + manager.outputs);
                System.out.println("disk class: " + Files.isRegularFile(
                        output.resolve("demo/log/Check.class")));
                System.out.println("nested class: " + Files.isRegularFile(
                        output.resolve("demo/log/Check$Child.class")));
                if (!ok) throw new IllegalStateException("Compilation failed");
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Lệnh:

```bash
javac --release 17 ForwardingLogDemo.java
java ForwardingLogDemo
```

**Stdout chính xác:**

```text
compiled: true
logged: [demo.log.Check, demo.log.Check$Child]
disk class: true
nested class: true
```

**Phân tích:**

- `Source` chứa source code ngay trong Java string, không cần file `Check.java` trên disk. URI `string:///demo/log/Check.java` mô tả tên/package khớp.
- `LoggingManager` chỉ quan sát hai `JavaFileObject.Kind.CLASS` output, rồi gọi `super.getJavaFileForOutput(...)` để delegate thực hiện xử lý file thật.
- Source khai báo **hai binary class names**: `demo.log.Check` và `demo.log.Check$Child`. Vì thế compiler tạo **hai class files**, không phải một output cho toàn bộ source.
- Kết quả chứng minh wrapper vẫn ủy quyền tới standard manager: file `out/demo/log/Check.class` và `out/demo/log/Check$Child.class` thực sự tồn tại.
- Chương trình sort danh sách `outputs` trước khi in; không dựa vào thứ tự compiler báo class files là cố định.
- Lớp wrapper giữ `StandardJavaFileManager` dưới generic `<StandardJavaFileManager>`, nhưng bạn vẫn cấu hình location trên reference `standard`. Nhìn thấy tên class ở log không tự có nghĩa output đã chuyển vào RAM.

**Bài học thiết kế:** Một `ForwardingJavaFileManager` có thể làm việc **chỉ để quan sát/giới hạn/ghi log**, chứ không phải luôn thay chiến lược lưu trữ output.

## 8. Biên dịch hoàn toàn trong RAM: cần thay cả nguồn và nơi nhận class

Để compile mà không ghi class files sinh ra vào thư mục dự án, ta thiết kế ba thành phần:

1. **`Source extends SimpleJavaFileObject`**: mang chuỗi source Java, override `getCharContent(...)`.
2. **`ByteCode extends SimpleJavaFileObject`**: mang `ByteArrayOutputStream`, override `openOutputStream()`; compiler ghi bytes của `.class` vào buffer.
3. **`MemoryManager extends ForwardingJavaFileManager<StandardJavaFileManager>`**: override `getJavaFileForOutput(...)` và trả `ByteCode` khi compiler muốn ghi `CLASS` tại `CLASS_OUTPUT`. Các thao tác khác được delegate để vẫn dùng platform types và dependencies tiêu chuẩn.

```text
Source "string:///demo/mem/MathBox.java"
         |
         | JavaCompiler.getTask(..., memoryManager, ...)
         v
      javac
         |
         | getJavaFileForOutput(CLASS_OUTPUT,
         |                      "demo.mem.MathBox", CLASS, sibling)
         v
      ByteCode "mem:///demo/mem/MathBox.class"
         |
         | openOutputStream()
         v
      byte[] lưu trong Map<String, ByteCode>

Sau compilation:
  ByteLoader.findClass("demo.mem.MathBox")
         |
         v
      defineClass(name, byte[], 0, len)
         |
         v
      Class<?> thực sự được JVM nạp và có thể invoke
```

### 8.1. Vì sao phải dùng map theo binary name?

Vì một source Java có thể phát ra **nhiều class files**: nested classes, local/anonymous classes, classes khác trong cùng compilation unit (khi hợp lệ) hoặc generated classes. Một `ByteArrayOutputStream` duy nhất sẽ bị ghi đè hoặc trộn dữ liệu. Map như `Map<String, ByteCode>` giúp mỗi className có bytecode riêng.

Một class name có thể trùng nếu bạn compile lại; với hệ thống nhiều phiên bản, cần thiết kế version key/class loader và eviction phù hợp. Demo chỉ chạy một compilation task.

### 8.2. Vì sao vẫn cần standard manager làm delegate?

Nếu bạn chỉ thay output, compiler vẫn cần:

- Tra cứu `java.lang.Object`, `java.lang.String` và platform APIs;
- Resolve classes/dependencies từ classpath/module path;
- Thực hiện `list(...)` và `inferBinaryName(...)` khi tìm các class đã có;
- Đọc các tài nguyên/metadata hợp lệ khác.

`ForwardingJavaFileManager` kế thừa việc delegate, nên không phải viết lại toàn bộ cơ chế đọc JDK modules/JAR files. Đây là ưu điểm chính so với tự implement `JavaFileManager` từ đầu.

### 8.3. Output trong RAM chưa chắc compile dependencies RAM được

Ví dụ 3 compile **một task** chứa class chính và nested class, rồi load cả hai qua ByteLoader. Nếu muốn **task tiếp theo** compile source mới tham chiếu các bytecode RAM vừa sinh, chỉ override `getJavaFileForOutput` **chưa đủ**.

Compiler task mới còn cần thấy class bytes RAM như **input**: có thể phải override đúng `getJavaFileForInput(...)`, `list(...)`, `inferBinaryName(...)`, `contains(...)` và đường `getClassLoader(...)` khi cần, để compiler discover/resolution được class RAM theo binary name. Hoặc ghi outputs ra một location có thể tìm như output directory/JAR rồi đặt lên CLASS_PATH cho task kế tiếp, như ví dụ 4.

**Không nhầm:** `ByteLoader` dùng sau compilation để chạy class không tự động trở thành **JavaFileManager** của compiler. Class loader của JVM và file manager của JavaCompiler là hai SPI khác nhau.

## 9. Thực hành 3 — `ForwardingJavaFileManager` thu `.class` vào RAM

Tạo tệp **`MemoryCompileDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class MemoryCompileDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class ByteCode extends SimpleJavaFileObject {
        final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        ByteCode(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            buffer.reset();
            return buffer;
        }

        byte[] bytes() {
            return buffer.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, ByteCode> classes = new HashMap<>();

        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                ByteCode file = new ByteCode(className, kind);
                classes.put(className, file);
                return file;
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }
    }

    static final class ByteLoader extends ClassLoader {
        private final Map<String, ByteCode> classes;

        ByteLoader(Map<String, ByteCode> classes) {
            super(ClassLoader.getPlatformClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            ByteCode output = classes.get(name);
            if (output == null) throw new ClassNotFoundException(name);
            byte[] bytes = output.bytes();
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        String code = "package demo.mem; public class MathBox { "
                + "public static int sum(int a, int b) { return a+b; } "
                + "public static class Inner { "
                + "public static int triple(int n) { return n*3; } } }";
        StandardJavaFileManager standard = compiler.getStandardFileManager(
                null, null, StandardCharsets.UTF_8);
        try (MemoryManager manager = new MemoryManager(standard)) {
            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, null, List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source("demo.mem.MathBox", code))).call());
            System.out.println("compiled: " + ok);
            List<String> names = new ArrayList<>(manager.classes.keySet());
            Collections.sort(names);
            System.out.println("outputs: " + names);
            System.out.println("all bytes present: " + manager.classes.values().stream()
                    .allMatch(item -> item.bytes().length > 0));
            if (!ok) throw new IllegalStateException("Compilation failed");

            ClassLoader loader = new ByteLoader(manager.classes);
            Class<?> box = Class.forName("demo.mem.MathBox", true, loader);
            Class<?> inner = Class.forName("demo.mem.MathBox$Inner", true, loader);
            System.out.println("sum: " + box.getMethod(
                    "sum", int.class, int.class).invoke(null, 19, 23));
            System.out.println("triple: " + inner.getMethod(
                    "triple", int.class).invoke(null, 7));
        }
    }
}
```

Lệnh:

```bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
```

**Stdout chính xác:**

```text
compiled: true
outputs: [demo.mem.MathBox, demo.mem.MathBox$Inner]
all bytes present: true
sum: 42
triple: 21
```

Giải thích cặn kẽ:

1. `Source("demo.mem.MathBox", code)` tạo `JavaFileObject.Kind.SOURCE` từ string, URI `string:///demo/mem/MathBox.java`.
2. `MemoryManager` nhận mọi lời gọi file manager từ compiler. Với `getJavaFileForOutput(CLASS_OUTPUT, binaryName, CLASS, sibling)`, nó trả một `ByteCode` trong RAM thay vì gọi standard manager.
3. Compiler sinh **hai** class outputs: `MathBox.class` và `MathBox$Inner.class`. Mỗi output được giữ ở một value của map.
4. `ByteCode.openOutputStream()` trả output stream tới `ByteArrayOutputStream`. Sau `task.call()` thành công, `bytes()` trả classfile bytes.
5. `ByteLoader` là loader riêng có quyền `defineClass(name, bytes, ...)`. `Class.forName(binaryName, true, loader)` lúc này có thể **tìm class trong ByteLoader** vì classfile bytes đã được loader đưa vào namespace của nó; điều này **không** có nghĩa `Class.forName(name)` bằng loader hệ thống cũng sẽ tìm được.
6. `getMethod("sum", ...)` và `getMethod("triple", ...)` chạy code vừa biên dịch, trả `42` và `21`.
7. **Không có output `MathBox.class`/`MathBox$Inner.class` được standard manager ghi ra disk** trong task này vì mọi `CLASS_OUTPUT` class output đã được intercept. Nếu bật annotation processors hay sinh resource/`SOURCE_OUTPUT`, cần kiểm soát thêm các đường output khác.

### 9.1. Những giới hạn của ví dụ in-memory

Ví dụ có chủ đích **không** tạo framework compiler tổng quát. Trong hệ thống sản xuất, cần:

- Đảm bảo map/thread-safety nếu nhiều tasks/threads có thể dùng cùng manager. Bản demo dùng `HashMap` một task tuần tự.
- Bảo vệ resource/memory: class bytes lớn, nested classes nhiều, giới hạn size, timeout, eviction và lifecycle class loader.
- Tránh binary name collision khi parent loader đã có class cùng tên. Ví dụ chọn package `demo.mem` và parent platform class loader để dễ kiểm chứng.
- Xử lý output stream failure, partial compilation và kết quả `false`. Không load bytecode của task thất bại.
- Nếu cần processors, generated source/resources hoặc compiler search RAM classes giữa tasks, triển khai các SPI khác tương ứng, thay vì chỉ ghi `.class` vào map.
- Hiểu rằng `ClassLoader#defineClass` và thực thi code tùy ý **không tạo sandbox bảo mật**; cần isolation/quyền phù hợp.

### 9.2. Vì sao `ByteCode` nên có một URI cho từng class?

Mỗi `JavaFileObject` mô tả một file логic với URI và `Kind`; compiler, diagnostics và file manager có thể dựa vào danh tính đó. Vì vậy URI như `mem:///demo/mem/MathBox$Inner.class` rõ nghĩa hơn một object thiếu tên hoặc dùng URI trùng cho mọi class. `SimpleJavaFileObject` lo một phần hợp đồng mặc định, subclass chỉ override stream cần thiết.

## 10. Mở rộng `ForwardingJavaFileManager`: chọn đúng điểm intercept

### 10.1. `getJavaFileForOutput` khác `getFileForOutput`

`JavaFileManager.getJavaFileForOutput(Location, className, Kind, sibling)` tạo file objects cho **Java source/class** output. `getFileForOutput(Location, packageName, relativeName, sibling)` dành cho **resource bất kỳ** tại vị trí/package/relative path tương ứng.

| Output muốn xử lý | Điểm hook thường cần |
| --- | --- |
| `.class` compiler sinh | `getJavaFileForOutput(..., Kind.CLASS, ...)` |
| Generated `.java` của processor | `getJavaFileForOutput(..., Kind.SOURCE, ...)` ở `SOURCE_OUTPUT` |
| Resource như `META-INF/...` | `getFileForOutput(...)` |
| Đọc class đã có trong RAM | `getJavaFileForInput(...)` và/hoặc `list(...)` cùng suy tên |
| Điều chỉnh cách compiler nhận biết class name | `inferBinaryName(...)` đối với custom file objects |
| Phục vụ module-aware tools | `getLocationForModule(...)`, `listLocationsForModules(...)`, các method liên quan |

Nếu implementation/compiler dùng overload mới `getJavaFileForOutputForOriginatingFiles(...)` hoặc `getFileForOutputForOriginatingFiles(...)`, cần kiểm tra đường ủy quyền/mặc định và override nếu pipeline có yêu cầu. Đừng giả định chặn một overload luôn bắt được mọi output trong mọi phiên bản compiler và annotation processor.

### 10.2. `sibling` và originating files không phải runtime dependency

`sibling`/`originatingFiles` cung cấp thông tin nguồn liên quan khi quyết định **địa điểm output** hoặc quan hệ sinh file; không phải danh sách classpath dependencies. Nếu location output đã được đặt tường minh, standard manager có thể bỏ qua vị trí source để chọn output directory, như demo 2. Với custom manager, vẫn nên giữ metadata phù hợp cho annotation processing/incremental compilation nếu framework cần.

### 10.3. Khi nào phải override `list` hoặc `inferBinaryName`?

Nếu file manager cung cấp **classfile inputs ngoài disk**, compiler có thể hỏi:

- `list(CLASS_PATH, packageName, kinds, recurse)` để tìm candidate file objects của một package;
- `inferBinaryName(location, file)` để xác định binary class name;
- `getJavaFileForInput(location, className, Kind.CLASS)` để đọc bytes cụ thể.

Nếu bạn trả custom `ByteCode` object nhưng không dạy manager cách suy binary name, compiler có thể không resolve được class dù object chứa bytecode đúng. Điều này thường xuất hiện khi biến một demo in-memory một task thành IDE/compiler service đa task. **Đường ghi output** và **đường đọc dependency** là hai nửa phải được thiết kế đồng bộ.

## 11. Tái sử dụng `StandardJavaFileManager` giữa nhiều tasks

Theo Javadoc `JavaCompiler`, standard file manager được thiết kế để **có thể tái sử dụng cho nhiều compilation tasks theo thứ tự**. Điều này có thể tiết kiệm việc scan filesystem/JAR. Nhưng:

- **Không tái sử dụng chính `CompilationTask`** sau khi đã `call()`; tạo một task mới cho mỗi lần compile.
- **Có thể tái sử dụng cùng standard manager** giữa các task tuần tự, nếu chưa `close()`.
- Cần đặt classpath phù hợp để task sau nhìn thấy class output task trước.
- Không mặc nhiên coi một manager là thread-safe cho các concurrent compile tasks. Hãy cô lập manager theo task/request hoặc kiểm chứng tài liệu implementation và đồng bộ nếu muốn sharing.
- Có thể dùng `flush()` giữa các lần khi cần đảm bảo output đã được chuyển đến nơi lưu; `flush()` không thay `close()`.

### 11.1. Thực hành 4 — Compile hai lần bằng cùng standard manager

Tạo **`ReuseManagerDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ReuseManagerDemo {
    static final class Source extends SimpleJavaFileObject {
        final String content;

        Source(String name, String content) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        Path root = Files.createTempDirectory("reuse-java-manager-");
        try {
            Path out = Files.createDirectories(root.resolve("out"));
            try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                    null, null, StandardCharsets.UTF_8)) {
                manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                        List.of(out));
                manager.setLocationFromPaths(StandardLocation.CLASS_PATH,
                        List.of(out));
                List<String> options = List.of("--release", "17", "-proc:none");
                boolean first = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null, options, null, List.of(new Source(
                                "demo.chain.First",
                                "package demo.chain; public class First {"
                                + "public static int value() {return 40;} }"))).call());
                boolean second = Boolean.TRUE.equals(compiler.getTask(
                        null, manager, null, options, null, List.of(new Source(
                                "demo.chain.Second",
                                "package demo.chain; public class Second {"
                                + "public static int value() {return First.value()+2;} }"))).call());
                System.out.println("first: " + first);
                System.out.println("second: " + second);
                System.out.println("second file: " + Files.isRegularFile(
                        out.resolve("demo/chain/Second.class")));
                if (!first || !second) throw new IllegalStateException("compile failed");
            }
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{out.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> second = Class.forName("demo.chain.Second", true, loader);
                System.out.println("result: " + second.getMethod("value").invoke(null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Lệnh:

```bash
javac --release 17 ReuseManagerDemo.java
java ReuseManagerDemo
```

**Stdout chính xác:**

```text
first: true
second: true
second file: true
result: 42
```

**Diễn giải:**

1. `Source` là `SimpleJavaFileObject` trong RAM, nhưng **output** của hai tasks là file thật trong thư mục `out`.
2. Task thứ nhất sinh `demo.chain.First.class` chứa `First.value() == 40`.
3. Cùng standard manager được dùng cho **task thứ hai**. Task này có source `demo.chain.Second` tham chiếu `First.value()`.
4. `CLASS_OUTPUT` chỉ định nơi ghi class mới; `CLASS_PATH` chỉ định nơi compiler tìm class đã sinh trước đó. Task thứ hai compile thành công vì output của task thứ nhất giờ có trên classpath.
5. Program nạp `demo.chain.Second` rồi gọi `value()`, kết quả `40+2=42`.
6. Mỗi `compiler.getTask(...)` tạo một **task riêng**, còn `manager` được tái sử dụng; đó là pattern được JavaCompiler API khuyến nghị cho sequential compilations.

### 11.2. Khi nào cần thay `StandardJavaFileManager` bằng forwarding giữa tasks?

Nếu muốn vừa tận dụng khả năng cache classpath/JAR của standard manager vừa có behavior như lưu output RAM hoặc ghi metrics, bạn có thể bọc cùng standard manager bằng forwarding manager. Nhưng mọi thứ cache/in-memory state phải được xét theo lifecycle:

- Dữ liệu outputs sau task A có thể không tự xuất hiện trong list/getJavaFileForInput của task B.
- Hai tasks dùng cùng wrapper có thể chia sẻ map; cần xóa/quản lý entries khi version thay.
- Chỉ sau khi implement đường đọc bổ sung mới thực sự có "RAM classpath" cho compiler.
- Nếu dùng output on-disk cho task trước, cấu hình `CLASS_PATH` rõ ràng thường là cách đơn giản và dễ debug hơn.

## 12. Diagnostics: file manager không thay `DiagnosticCollector`

Có hai kênh khác nhau:

- **File manager**: cung cấp source/output `JavaFileObject` và mô hình tra cứu file.
- **DiagnosticListener` / `DiagnosticCollector`**: nhận các lỗi, cảnh báo, ghi nhận source, kind, line/column/position/code/message từ compiler.

Nếu compilation sai, `getTask(...).call()` thường trả `false` thay vì tự tạo class hợp lệ. Bạn cần đọc `DiagnosticCollector.getDiagnostics()`, không đoán từ việc có vài bytes trong map hay có file output partial.

### 12.1. Thực hành 5 — Source trong RAM và lỗi compile có cấu trúc

Tạo **`DiagnosticsDemo.java`**:

```java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK required");
        JavaFileObject broken = new SimpleJavaFileObject(
                URI.create("string:///demo/Broken.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return "package demo; public class Broken { "
                        + "int get() { return missingName; } }";
            }
        };
        DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(collector, null, null)) {
            boolean ok = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, collector,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(broken)).call());
            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
            System.out.println("compiled: " + ok);
            System.out.println("errors present: " + (errors > 0));
            System.out.println("source is known: " + collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .allMatch(d -> d.getSource() == broken));
        }
    }
}
```

```bash
javac --release 17 DiagnosticsDemo.java
java DiagnosticsDemo
```

**Stdout chính xác:**

```text
compiled: false
errors present: true
source is known: true
```

Phân tích:

1. JavaCompiler compile source `Broken` có tên biến `missingName` chưa được khai báo.
2. Task trả `false`. `DiagnosticCollector` nhận ít nhất một `Diagnostic.Kind.ERROR`; program không in nguyên message do wording/locale có thể thay đổi theo JDK.
3. Mỗi error trong demo có source chính là `broken`, cho thấy diagnostics liên kết với `JavaFileObject` của source, dù source không tồn tại dưới dạng tệp vật lý.
4. Không chạy class vì compilation **thất bại**. Với file manager lưu output RAM hoặc disk, nếu task dở dang đã phát sinh artifacts, production code cần có chính sách rollback/cleanup trước khi dùng chúng.
5. Chuyển cả `collector` vào `getStandardFileManager` và `getTask` không có nghĩa compiler sẽ tự sửa lỗi hay thay semantics; đó chỉ là hai chỗ API nhận listener để báo diagnostics của các phần tương ứng.

### 12.2. Kết quả `false` khác với exception của compiler/file manager

Phân biệt:

| Sự kiện | Điều thường quan sát |
| --- | --- |
| Java source có lỗi cú pháp/kiểu | `getTask(...).call()` trả `false` và có `Diagnostic.Kind.ERROR` |
| File manager không thể đọc/ghi | IOException trong SPI có thể được compiler báo thành diagnostics hoặc ném exception, tùy API/implementation |
| `compiler == null` | Môi trường không cung cấp system compiler; không thể tạo task |
| Tool option không hợp lệ | Có thể có `IllegalArgumentException`/diagnostics từ `getTask` hoặc khi thực thi, tùy lựa chọn |
| Exception trong custom `SimpleJavaFileObject`/`ForwardingJavaFileManager` | Compilation có thể fail theo đường exception hoặc diagnostics; không nên nuốt lỗi rồi return file object hỏng |
| Task đã gọi `call()` rồi bị gọi lại | Không nên tái sử dụng `CompilationTask`; tạo task mới |

Trong ứng dụng, xử lý cả **Boolean task result**, **diagnostics** và **exceptions**. Chỉ thấy `.class` tồn tại không đủ chứng minh build hoàn toàn thành công.

## 13. Vấn đề file manager trong hệ thống có annotation processors

Khi annotation processing được bật:

1. Processor có thể sinh **source** (`SOURCE_OUTPUT`), **class** (`CLASS_OUTPUT`) và **resource** theo `Filer`.
2. Compiler có thể dùng `getJavaFileForOutput` cho Java source/class và `getFileForOutput` cho resources.
3. Ngoài overload nhận `sibling`, JDK API mới có biến thể `ForOriginatingFiles` để giữ quan hệ nguồn sinh output; cần kiểm tra JDK cụ thể.
4. Nếu in-memory manager chỉ intercept `getJavaFileForOutput(CLASS_OUTPUT, ..., CLASS, ...)`, thì generated source/resource có thể **vẫn ghi ra filesystem**.
5. Nếu processor hoặc compiler tìm generated class ngay trong cùng/khác task, manager còn phải đảm bảo các thao tác input/list/binary name phục vụ resolution được.
6. Output location cần tương thích với compiler và processor; đừng biến mọi request kể cả resource/module thành một file object RAM không phân biệt location/kind.

Các ví dụ ở bài đều đặt `-proc:none` để chỉ tập trung vào file manager, tránh tạo processor outputs không thuộc phạm vi demo. Khi bỏ option này trong ứng dụng thực tế, phải kiểm thử đường phát sinh artifacts riêng.

### 13.1. Modules và file location

Java 9+ cung cấp module-oriented locations. Khi compile module code:

- Tìm platform/user modules qua module path;
- Phải lưu ý location phụ thuộc module name;
- Các phương thức như `getLocationForModule` và `listLocationsForModules` có thể tham gia;
- `StandardJavaFileManager.setLocationForModule(...)` phục vụ cấu hình module-specific paths;
- Custom in-memory manager chỉ thay `CLASS_OUTPUT` theo cách so sánh object identity có thể không bắt đúng **module-specific output location**.

Đối với compilation module-aware hoặc JDK/toolchain khác, cần kiểm thử hợp đồng location thực tế thay vì hard-code giả định từ classpath-only example.

## 14. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime không cung cấp system compiler/tool module | Chạy với JDK có `jdk.compiler` và module phù hợp |
| Task compile source nhưng không có class ở `out` | `CLASS_OUTPUT` sai, wrapper chặn output, task thất bại, module layout khác | Kiểm tra task status, diagnostics và file manager đang truyền vào |
| Source `Path` bị hiểu sai là nhiều path components | Gọi nhầm overload nhận `Iterable<Path>` với một `Path` | Dùng `List.of(path)` hoặc `getJavaFileObjects(path)` |
| `IllegalArgumentException` khi cấu hình location | Directory không hợp lệ, output location không đúng, Path không được hỗ trợ | Tạo directory/đường dẫn hợp lệ, chọn đúng `StandardLocation` |
| `ClassNotFoundException` sau `call() == true` | Classloader chưa thấy directory/map hoặc class name sai | Nạp qua loader phù hợp, kiểm tra binary package name |
| Một source sinh nhiều class, map chỉ có một entry | Intercept không lưu theo từng binary name | Dùng `Map<String, ByteCode>`, xử lý nested/anonymous classes |
| Nguồn ở RAM nhưng vẫn có file `.class` trên disk | Chỉ thay input source, vẫn dùng standard output | Intercept `getJavaFileForOutput(CLASS_OUTPUT,CLASS)` |
| Output RAM thành công nhưng task kế tiếp không resolve được class | Thiếu đường đọc input `list`/`getJavaFileForInput` | Implement SPI đọc hoặc đưa bytecode vào CLASS_PATH |
| Wrapper có log nhưng không capture bytes | Override log rồi `return super.getJavaFileForOutput` | Trả `JavaFileObject` dùng RAM nếu thật sự muốn in-memory |
| `ForwardingJavaFileManager` không có `setLocationFromPaths` | Wrapper không implement `StandardJavaFileManager` | Cấu hình reference `standard`, không ép cast wrapper |
| Compiler không thấy output task trước | `CLASS_OUTPUT` không phải classpath cho task mới | Thêm output directory vào `CLASS_PATH` hoặc options |
| Bytecode RAM chỉ chứa outer class, thiếu nested class | Không lưu mọi `className` mà compiler yêu cầu | Intercept từng call theo binary class name |
| Diagnostics rỗng nhưng task lỗi | Lỗi xảy ra ở SPI, startup/options hoặc exception trước khi collector ghi | Kiểm tra exceptions/out/return value, không chỉ đếm errors |
| Đóng manager trước khi task hoàn thành | File/JAR streams có thể đã đóng | Giữ manager đến sau `task.call()` và flush/output completion |
| Load generated code không an toàn | File manager chỉ quản lý I/O, không sandbox code | Cô lập execution và giới hạn quyền/tài nguyên ở tầng runtime |
| Memory leak do `URLClassLoader`/`ByteLoader` giữ class | Loader/class bytecode/cache tiếp tục reachable | Quản lý references, close URLClassLoader, quan sát class unloading |
| Annotation processor sinh tài nguyên lọt ra disk | Chưa intercept `SOURCE_OUTPUT`/`getFileForOutput` | Mở rộng wrapper cho source/resource outputs |
| Cùng binary name nhưng classloader trả class cũ | Parent delegation hoặc class identity đã nạp | Dùng name/version/loader strategy phù hợp |
| Ghi đè classfile của task khác | Shared output directory hoặc concurrent file manager | Tách output theo task/version, không share manager không đồng bộ |

### 14.1. Bẫy `super`, `fileManager` và recursion

Trong subclass:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location, String name,
        JavaFileObject.Kind kind, FileObject sibling) throws IOException {
    // Mẫu delegate đúng:
    return super.getJavaFileForOutput(location, name, kind, sibling);
}
```

Đây là fragment minh họa, thiếu class/import context. **Không** gọi lại `this.getJavaFileForOutput(...)` từ chính override nếu không có điều kiện dừng: đó là recursion vô hạn. `super...` gọi forwarding implementation để delegate tới manager gốc. Nếu cần ghi log, log trước rồi delegate.

### 14.2. Bẫy `FileObject.toUri()` và binary names

`toUri()` là danh tính của file object, **không phải** tên class mà JVM dùng ở mọi nơi. `demo.mem.MathBox` là binary class name, còn `mem:///demo/mem/MathBox.class` là URI. Nếu dùng URI như string cho `Class.forName`, sẽ không có class tên đó.

### 14.3. Bẫy lifetime file manager và loader

- File manager quản lý **biên dịch**; loader quản lý **nạp/thi hành class**.
- Đóng file manager không làm class đã nạp tự unload.
- Đóng URLClassLoader giải phóng tài nguyên loader nhưng không lập tức unload classes còn reachable.
- Một in-memory bytes map đang được giữ có thể tăng memory dù không còn compilation task.
- Nhiều dynamic versions cùng binary name có thể là **các classes khác nhau** nếu defining classloader khác; không dựa vào tên string duy nhất để nhận diện class qua mọi loader.

## 15. Checklist cho một runtime compiler đáng tin

Trước khi đưa bộ biên dịch runtime vào sản phẩm:

1. **Môi trường:** kiểm tra compiler có sẵn và version/release options hợp lệ.
2. **Nguồn:** chọn Path/source-in-memory và đảm bảo `JavaFileObject.Kind.SOURCE`, URI, binary name/package nhất quán.
3. **Input dependencies:** cấu hình `CLASS_PATH`, `MODULE_PATH`, `SOURCE_PATH` đúng; tránh phụ thuộc vô thức vào working directory.
4. **Output:** quyết định file hay RAM, chọn hook `getJavaFileForOutput`/`getFileForOutput` và `Location` tương ứng.
5. **Nhiều class outputs:** lưu theo mỗi binary class name và location/version nếu cần.
6. **Wrapper:** giữ delegate, chỉ override các thao tác cần thay; dùng `super` cho phần còn lại.
7. **Diagnostics:** gom lỗi/cảnh báo; đọc `getTask(...).call()`; không dùng bytes partial từ một task thất bại.
8. **Annotation processing:** quyết định bật/tắt; nếu bật, kiểm thử generated sources/resources và output locations.
9. **Classloader:** chọn chiến lược nạp đúng loader, hạn chế name collisions, hỗ trợ cleanup.
10. **Tái sử dụng:** chia sẻ manager **tuần tự** khi hợp lý; không tái sử dụng `CompilationTask`; không mặc định thread-safe.
11. **Resource safety:** try-with-resources, flush/close streams, temp cleanup, quản lý cache/lifecycle.
12. **Bảo mật:** không thi hành source không tin cậy trong cùng process chỉ vì bạn đã kiểm soát file manager; cần isolation phù hợp.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `StandardJavaFileManager` là một lớp implementation có thể `new` trực tiếp hay một interface được compiler cung cấp instance? Lấy instance ra sao?

**Câu 2.** `ForwardingJavaFileManager` có tự trở thành `StandardJavaFileManager` vì generic type là `<StandardJavaFileManager>` không?

**Câu 3.** Khi chỉ muốn log output của compiler và vẫn ghi `.class` ra disk, cần override gì và nên return gì?

**Câu 4.** Muốn thu `.class` vào RAM thì file manager phải trả một object ghi vào đâu? Method nào trên `JavaFileObject` quan trọng?

**Câu 5.** Một source có nested class có thể sinh mấy class files? Vì sao cần map theo className?

**Câu 6.** `getTask(..., compilationUnits)` có bắt buộc nhận files `.java` vật lý không?

**Câu 7.** Vì sao task 2 ở `ReuseManagerDemo` phải nhìn thấy `CLASS_PATH` chứa thư mục output của task 1?

**Câu 8.** Có nên gọi `task.call()` hai lần trên cùng một compilation task không? Có thể dùng lại standard manager không?

**Câu 9.** Nếu source compiler nằm trong RAM và không có `.java` file, diagnostics có tìm lại được vị trí/đối tượng source không?

**Câu 10.** Nếu in-memory manager chỉ override `getJavaFileForOutput(CLASS_OUTPUT, Kind.CLASS)`, các generated resources của annotation processor có chắc nằm trong RAM không?

**Câu 11.** Tại sao `ByteLoader` dùng trong ví dụ 3 không tự làm compiler task sau resolve class bytes trong RAM?

**Câu 12.** `FileObject.toUri()`, binary class name và `Path` có phải là cùng một khái niệm không?

**Câu 13.** Khi cần compile module-oriented code, vì sao chỉ kiểm tra `StandardLocation.CLASS_OUTPUT` có thể chưa đủ?

**Câu 14.** File manager đã đóng thì class đã được `URLClassLoader` load có tự unload không?

**Câu 15.** Dùng `ForwardingJavaFileManager` bọc standard manager có khiến source Java không tin cậy trở nên an toàn để chạy không?

**Câu 16.** Trên Java 17, cách rõ ràng nhất để đưa **một `Path`** vào `getJavaFileObjectsFromPaths` là gì? Vì sao?

### Gợi ý đáp án

1. Interface; dùng `compiler.getStandardFileManager(listener, locale, charset)`.
2. Không. Wrapper vẫn là `JavaFileManager`, muốn set locations theo API standard thì dùng reference delegate.
3. Override `getJavaFileForOutput`; log rồi `return super.getJavaFileForOutput(...)`.
4. Trả một custom `JavaFileObject` có `openOutputStream()` ghi vào `ByteArrayOutputStream` hoặc storage phù hợp.
5. Có thể nhiều file: outer, nested, anonymous/local...; mỗi binary class name cần output riêng.
6. Không; có thể dùng `SimpleJavaFileObject` chứa source string, URI hợp lệ.
7. Vì nơi **ghi** class không mặc nhiên là nơi compiler **tìm** class cho task tiếp theo.
8. Không dùng lại task; standard manager hỗ trợ nhiều tasks **tuần tự**.
9. Có; `Diagnostic.getSource()` có thể trả chính `JavaFileObject` nguồn trong RAM.
10. Không; phải xử lý `SOURCE_OUTPUT`, resources/`getFileForOutput` và có thể originating-files overload.
11. Compiler dùng `JavaFileManager`, loader của JVM là API khác; phải đưa bytes vào đường file manager input/list.
12. Không: URI định danh file object, binary name định danh class, Path là filesystem path.
13. Module-oriented location có thể khác singleton `CLASS_OUTPUT`, cần hỗ trợ `getLocationForModule`/module output.
14. Không; nạp/unloading phụ thuộc classloader, object references và GC.
15. Không; file manager không phải sandbox.
16. `List.of(path)` trong overload nhận `Collection<Path>`; tránh overload `Iterable<Path>` deprecated và nhầm `Path` như iterable các thành phần.

## 17. Nguồn tài liệu chính thức

- [Java SE 21 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getStandardFileManager`, `getTask`, standard manager reuse và diagnostics.
- [Java SE 21 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): hỗ trợ `File`/`Path`, URI, `getJavaFileObjectsFromPaths` và `setLocationFromPaths`.
- [Java SE 21 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): constructor delegate, forwarding methods và khả năng override.
- [Java SE 21 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): hợp đồng SPI về source/class/resource, location, output hints, originating files, `list`, `inferBinaryName`.
- [Java SE 21 — `JavaFileObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind.SOURCE`, `Kind.CLASS` và binary-name metadata.
- [Java SE 21 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): base class tạo source/output file objects tùy biến.
- [Java SE 21 — `StandardLocation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardLocation.html): `CLASS_PATH`, `CLASS_OUTPUT`, `SOURCE_OUTPUT`, `MODULE_PATH`.
- [Java SE 21 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): quản lý diagnostics có cấu trúc.
- [JDK 21 `javac` command specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-d`, `--class-path`, `--release`, `-proc:none` và đường tìm class output/dependencies.
- [Java SE 21 — `ToolProvider`](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html): cách lấy compiler hệ thống.

**Kết luận:** `StandardJavaFileManager` là nền tảng có sẵn để compiler đọc/ghi file, JAR, classpath/module paths và cho phép tái sử dụng giữa các compilation tasks. `ForwardingJavaFileManager` là decorator giúp **thay một vài thao tác** như đường sinh `.class` mà vẫn giữ lại toàn bộ chức năng delegate. Khi làm compiler runtime, cần phân biệt **nguồn đầu vào**, **nơi lưu class output**, **nơi compiler tìm dependencies**, **nơi JVM load class** và **kênh diagnostics**; đúng từng vai trò đó sẽ tránh phần lớn lỗi của hệ thống compile động.