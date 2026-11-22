# Chuẩn bị đơn vị nguồn bằng StandardJavaFileManager

## 1. Vị trí trong quy trình biên dịch Java lúc chạy

Java Compiler API (`javax.tools`, có trong module `java.compiler`) cho phép host biên dịch source Java mà không gọi tiến trình `javac` bên ngoài. Một bước quan trọng là chuyển đường dẫn các file `.java` thành `JavaFileObject` để đưa vào `JavaCompiler.CompilationTask`. `StandardJavaFileManager` cung cấp các thao tác này theo quy ước của hệ thống tệp và cấu hình compiler.

Quy trình tiêu biểu:

```text
ToolProvider.getSystemJavaCompiler()
      |
      v
JavaCompiler.getStandardFileManager(...)
      |
      +--> đặt CLASS_PATH / CLASS_OUTPUT (khi cần)
      |
      +--> getJavaFileObjectsFromPaths(...)
      |             |
      |             v
      |       Iterable<? extends JavaFileObject>
      |
      v
compiler.getTask(..., fileManager, ..., compilationUnits)
      |
      v
task.call() --> kiểm tra diagnostics và .class output
```

Trong hệ thống plugin, host có thể nhận các tệp source từ thư mục được phép, chuyển chúng thành compilation units rồi tạo class cho một plugin mới. **Chuẩn bị compilation units** khác với việc compile, load class, instantiate provider hoặc thực thi mã plugin; đó là các bước riêng cần kiểm soát.

## 2. Những đối tượng cần hiểu

| Đối tượng | Vai trò |
|---|---|
| `JavaCompiler` | Compiler được lấy qua `ToolProvider.getSystemJavaCompiler()`; tạo tác vụ biên dịch |
| `StandardJavaFileManager` | Adapter chuẩn giữa compiler và file system; tạo `JavaFileObject` và quản lý file location |
| `JavaFileObject` | Trừu tượng của tệp source/class; `Kind.SOURCE` đại diện đơn vị nguồn |
| `Iterable<? extends JavaFileObject>` | Tập compilation units được truyền vào `getTask` |
| `StandardLocation.CLASS_PATH` | Nơi compiler tìm dependency từ class path |
| `StandardLocation.CLASS_OUTPUT` | Nơi ghi file `.class` khi compiler thành công |
| `DiagnosticCollector<JavaFileObject>` | Thu thập thông tin lỗi/cảnh báo có source, line và column khi có |

`StandardJavaFileManager` mở rộng `JavaFileManager` và `Closeable`: cần đóng khi không sử dụng. Đừng nhầm file manager với class loader: file manager hỗ trợ compiler tìm/đọc/ghi file; việc load và chạy `.class` sau khi biên dịch cần được thiết kế riêng.

## 3. Lấy StandardJavaFileManager

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Không có system Java compiler");
}

DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
try (StandardJavaFileManager files = compiler.getStandardFileManager(
        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // Cấu hình location, chuẩn bị JavaFileObject, gọi getTask.
}
```

Đoạn này là **mảnh mã minh họa**; cần import `javax.tools.*`, `java.util.Locale`, `java.nio.charset.StandardCharsets` và đặt vào phương thức có xử lý exception. `getSystemJavaCompiler()` thường sẵn có khi chạy trên JDK có module `jdk.compiler`; trong runtime image tối giản không có compiler, nó có thể trả `null`. `java.compiler` chỉ định nghĩa các API, không bảo đảm provider compiler luôn hiện diện.

Ba tham số của `getStandardFileManager` lần lượt là diagnostic listener, locale và charset. Khi biên dịch nguồn tiếng Việt hoặc có literal Unicode, chọn charset rõ ràng để việc đọc source ổn định giữa các máy. `Locale.ROOT` chủ yếu ảnh hưởng cách hiển thị thông báo chẩn đoán, không thay đổi ngữ nghĩa chương trình.

## 4. Chuyển file nguồn thành JavaFileObject

Các phương thức quan trọng của `StandardJavaFileManager`:

```java
Iterable<? extends JavaFileObject> units =
    files.getJavaFileObjectsFromPaths(List.of(
        Path.of("src/demo/Hello.java"),
        Path.of("src/demo/Helper.java")
    ));
```

Những file `.java` ở đây phải thật sự tồn tại và thuộc phạm vi được host cho phép. `getJavaFileObjectsFromPaths` giúp chuyển từng `Path` thành Java file object; nó không tự tìm mọi source trong cả thư mục theo một quy tắc plugin. Nếu muốn compile cả cây source, host tự duyệt file trong thư mục, lọc `.java`, sắp xếp đầu vào có chủ đích rồi truyền danh sách path.

Các biến thể khác: `getJavaFileObjects(File...)`, `getJavaFileObjectsFromFiles(Iterable<? extends File>)` và `getJavaFileObjectsFromStrings(Iterable<String>)`. Khi code đã dùng `java.nio.file.Path`, ưu tiên `getJavaFileObjectsFromPaths` để tránh chuyển qua lại giữa `Path` và `File`.

**Bảo đảm hợp đồng:** Trình biên dịch không chấp nhận tùy tiện bytecode hoặc file `class` làm compilation unit nguồn. Nên chỉ truyền `JavaFileObject.Kind.SOURCE`; nếu source không tồn tại, không đọc được hoặc có tên khác cấu trúc package/public class, compiler sẽ báo lỗi thích hợp.

## 5. Ví dụ hoàn chỉnh, biên dịch được trên Java 17+

Ví dụ tạo một source Java từ trước trên ổ đĩa, dùng `StandardJavaFileManager` để tạo compilation unit và biên dịch `.class` vào thư mục output. Mục đích là kiểm chứng riêng quá trình chuẩn bị units và compile.

Cây thư mục ban đầu:

```text
compile-demo/
├── src/
│   └── demo/
│       └── Greeter.java
└── CompileSources.java
```

`src/demo/Greeter.java`:

```java
package demo;

public class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from compiled source");
    }
}
```

`CompileSources.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompileSources {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        Path source = Path.of("src/demo/Greeter.java");
        Path output = Path.of("build/classes");
        if (!Files.isRegularFile(source)) {
            throw new IOException("Missing source: " + source);
        }
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(List.of(source));

            List<String> options = List.of("--release", "17", "-encoding", "UTF-8");
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics, options, null, units);

            boolean ok = Boolean.TRUE.equals(task.call());
            System.out.println("compiled: " + ok);

            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + " line "
                            + d.getLineNumber() + ": " + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }
        }
    }
}
```

Từ thư mục `compile-demo/`, chạy trên JDK 17+:

```bash
javac -encoding UTF-8 CompileSources.java
java CompileSources
java -cp build/classes demo.Greeter
```

Output chính xác khi source hợp lệ và compiler khả dụng:

```text
compiled: true
Hello from compiled source
```

Dòng đầu từ `CompileSources`; dòng thứ hai từ chương trình `demo.Greeter` vừa được biên dịch. Tệp kết quả là `build/classes/demo/Greeter.class`. Chương trình biên dịch **không tự thực thi** class này trong `task.call()`; lệnh `java -cp` là bước riêng.

### Vì sao ví dụ dùng setLocationFromPaths?

`manager.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output))` cấu hình nơi sinh file `.class` ở mức file manager. Nó tương tự chỉ định `-d build/classes` cho compiler, và không cần tự đặt `-d` một lần nữa trong `options`. Một số location khác như `CLASS_PATH` và `SOURCE_PATH` có thể cấu hình tùy dependency và cấu trúc project; tránh vừa cấu hình file manager vừa truyền cờ mâu thuẫn khiến việc kiểm chứng khó khăn.

## 6. Chuẩn bị nhiều compilation units

Trong dự án thực, một plugin có thể gồm nhiều file cùng package hoặc import lẫn nhau. Cần đưa tập `JavaFileObject` vào cùng một compilation task để compiler kiểm tra các phụ thuộc nguồn.

Ví dụ Java 17+ (đặt trong một phương thức đã có `manager`):

```java
List<Path> sourceFiles = List.of(
        Path.of("src/demo/Greeter.java"),
        Path.of("src/demo/Util.java"));

Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(sourceFiles);
```

Đây là ví dụ **chưa độc lập**, cần file `src/demo/Util.java` thật sự tồn tại. Một lỗi phổ biến là chỉ truyền file entry point và kỳ vọng mọi source ngoài source path tự được phát hiện. Khi cần compile toàn bộ module plugin, hãy xác định rõ file đầu vào, source path và dependency path theo build graph.

### Thu thập source từ thư mục an toàn

```java
Path root = Path.of("src").toAbsolutePath().normalize();
List<Path> sourceFiles;
try (var paths = Files.walk(root)) {
    sourceFiles = paths
            .filter(Files::isRegularFile)
            .filter(p -> p.toString().endsWith(".java"))
            .sorted()
            .toList();
}
```

Đoạn trên là một phần của chương trình đã import `Files`, `Path`, `List` và phải xử lý `IOException`; nó không phải chương trình độc lập. `Files.walk` trả stream cần đóng. Trong host plugin nhận source từ người dùng, còn phải kiểm tra symlink, giới hạn thư mục được phép, số lượng/tổng dung lượng file và đường dẫn canonical. `normalize()` chỉ xử lý cú pháp path, **không** tự giải quyết symlink hay bảo đảm file nằm trong root đáng tin cậy.

## 7. Class path, module path và dependency

File manager chuẩn có thể cấu hình các location khác nhau. Khi mã plugin import contract API:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(Path.of("lib/plugin-api.jar")));
```

Đây là đoạn minh họa trong ngữ cảnh đã có `manager`. Compiler tìm `plugin-api.jar` trên class path khi resolve symbol. Nếu API thuộc named module và plugin biên dịch dạng JPMS module, cần cấu hình `MODULE_PATH` và source/module options phù hợp; đừng nhầm compile class path với module path.

Đối với code chạy runtime, dependency visibility lại phụ thuộc class loader/module layer của host. Việc `javac` tìm thấy thư viện tại compile time không đảm bảo loader của plugin khi thực thi cũng nhìn thấy đúng artifact ấy. Trong kiến trúc plugin, contract API nên được chia sẻ nhất quán và tránh đóng gói trùng dẫn đến class identity conflict.

## 8. Diagnostics và luồng lỗi

`DiagnosticCollector` tích lũy lỗi, cảnh báo và thông báo từ compiler. `Diagnostic` có thể cung cấp kind, message, source, line và column, nhưng một số diagnostics mang vị trí `NOPOS` và không liên kết file cụ thể. Khi hiển thị lỗi trong UI, không giả định mọi lỗi đều có line hợp lệ.

```java
for (Diagnostic<? extends JavaFileObject> diagnostic :
        diagnostics.getDiagnostics()) {
    String name = diagnostic.getSource() == null
            ? "<compiler>"
            : diagnostic.getSource().getName();
    System.out.println(name + ":" + diagnostic.getLineNumber()
            + " " + diagnostic.getKind());
}
```

Đây là đoạn đặt trong ngữ cảnh ví dụ, không độc lập. Trước khi đưa nội dung diagnostic ra giao diện hay log, cân nhắc loại bỏ đường dẫn tuyệt đối và thông tin riêng tư. Không nên dùng nguyên văn message compiler làm khóa ổn định để quyết định nghiệp vụ vì chúng có thể khác giữa JDK/locale.

Phân biệt các trường hợp:

- `compiler == null`: runtime thiếu system Java compiler.
- `task.call()` trả `false`: có lỗi biên dịch thông thường, xem diagnostics.
- `getTask(...)`, file manager hoặc I/O ném exception: cấu hình/đọc file hoặc lỗi công cụ cần xử lý riêng.
- `task.call()` có thể ném runtime exception với lỗi bất thường; không đồng nhất mọi exception với lỗi cú pháp source.

## 9. Quản lý vòng đời StandardJavaFileManager

File manager có thể giữ cache thông tin file hoặc tài nguyên phục vụ compiler. Nên dùng `try-with-resources` để đóng ngay sau đợt compile. Không nên tái sử dụng cùng một file manager cho các tác vụ đồng thời mà không kiểm chứng thread-safety của implementation.

Một file manager chuẩn có thể được dùng qua nhiều compilation tasks tuần tự để tận dụng cache. Tuy nhiên, mỗi task chỉ được gọi một lần; tạo task mới khi compile lại. Nếu đang triển khai dịch vụ compile lâu dài, cần quy định rõ khi nào tạo, tái sử dụng và đóng file manager để tránh leak và trạng thái cấu hình từ plugin này ảnh hưởng plugin khác.

Đặc biệt, `getJavaFileObjectsFromPaths(...)` trả các file objects gắn với manager; không nên giữ chúng sau khi manager bị đóng rồi kỳ vọng tiếp tục đọc source. Thông thường các compilation units được chuẩn bị và tiêu thụ trong cùng scope của manager.

## 10. Biên dịch plugin không đồng nghĩa an toàn khi chạy

Trong hệ thống plugin do người dùng cung cấp, Java Compiler API **không phải sandbox**. Source có thể chứa mã nguy hiểm và việc compile còn có thể kích hoạt annotation processors nếu không giới hạn. Khi dùng compiler với nguồn không tin cậy:

- Chỉ nhận source từ vị trí được cho phép, giới hạn file count, size và compile timeout.
- Kiểm soát class path, module path và annotation processors; nếu không cần xử lý annotation, cấu hình `-proc:none`.
- Tránh chạy compile trong cùng process với quyền quá rộng nếu xử lý nguồn không tin cậy; cân nhắc tiến trình riêng với giới hạn tài nguyên và OS isolation.
- Không tự động load hoặc khởi tạo class vừa compile nếu chưa có bước thẩm định.
- Kiểm tra dependency runtime và contract version trước khi kích hoạt plugin.

Quyền truy cập file hệ thống, mạng và các thư viện ở runtime vẫn phụ thuộc quyền của process/OS và thiết kế isolation, không được hạn chế tự động chỉ bởi `StandardJavaFileManager`.

## 11. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getSystemJavaCompiler()` trả null | Không có provider system compiler trong runtime image | Chạy JDK đầy đủ hoặc runtime image có `jdk.compiler` |
| Không tìm thấy `src/demo/Greeter.java` | Working directory/path sai | Kiểm tra working directory và dùng `Path` đã xác minh |
| `package demo does not exist` | Thiếu dependency hoặc source path | Cấu hình `CLASS_PATH`/`MODULE_PATH` đúng và đưa đủ sources |
| Không sinh `.class` ở thư mục mong muốn | Chưa đặt `CLASS_OUTPUT` hoặc cấu hình output sai | `setLocationFromPaths(CLASS_OUTPUT, List.of(output))` |
| File `.java` có tiếng Việt bị đọc sai | Charset đầu vào không thống nhất | Chỉ định UTF-8 cho file manager và compiler options |
| Source có public class sai tên file | Tên `.java` không khớp public top-level class | Đặt đúng file/package theo Java |
| Gọi `task.call()` nhiều lần | Compilation task chỉ thực thi một lần | Tạo task mới từ compiler cho lần biên dịch kế tiếp |
| Leak file descriptor | Không đóng file manager hoặc stream duyệt thư mục | Dùng try-with-resources |
| Compile OK nhưng chạy lỗi ClassNotFound | Runtime class path/loader không thấy output | Cấu hình loader/runtime module path sau compile |

## 12. Checklist thực hành

1. Kiểm tra system compiler có tồn tại.
2. Xác thực source roots và từng path đầu vào; xác định `.java` cần compile.
3. Tạo `DiagnosticCollector` và `StandardJavaFileManager` với charset cụ thể.
4. Tạo thư mục output và cấu hình `StandardLocation.CLASS_OUTPUT`.
5. Cấu hình dependency `CLASS_PATH`/`MODULE_PATH` phù hợp.
6. Chuyển `Path` sang `Iterable<? extends JavaFileObject>` bằng `getJavaFileObjectsFromPaths`.
7. Truyền compilation units vào `getTask` cùng compiler options rõ ràng.
8. Gọi `task.call()` đúng một lần, xử lý Boolean và diagnostics.
9. Đóng file manager; kiểm tra `.class` đầu ra và chỉ nạp plugin ở giai đoạn activation riêng.

**Kết luận:** `StandardJavaFileManager` là cầu nối chuẩn giữa file system và `JavaCompiler`. Chuẩn bị compilation units đúng giúp compiler nhận được file nguồn cần thiết, resolve dependency và ghi class output vào vị trí có kiểm soát. Đây là bước nền tảng cho hệ thống biên dịch plugin lúc chạy, nhưng không thay thế quản lý class loader, module layer hay kiểm soát an toàn khi kích hoạt mã đã biên dịch.
