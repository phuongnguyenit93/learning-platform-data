# JavaCompiler và StandardJavaFileManager trong dự án mô-đun (Java 9+)

## 1. Vì sao dự án có module cần cấu hình compiler khác?

Từ Java 9, **Java Platform Module System (JPMS)** cho phép khai báo một *named module* bằng `module-info.java`. Compiler phải biết nguồn của từng module, những module khác nó `requires` và vị trí ghi `.class`. Khi muốn thực hiện việc này **ngay trong một chương trình Java** (công cụ sinh mã, IDE, plugin build, bộ kiểm tra mã...), dùng **Java Compiler API** trong gói `javax.tools`.

Hai vai trò chính:

- `JavaCompiler`: công cụ thực hiện **biên dịch Java**. `ToolProvider.getSystemJavaCompiler()` lấy compiler của JDK đang chạy nếu có sẵn; `getTask(...)` tạo một tác vụ; `CompilationTask.call()` thực thi biên dịch và trả kết quả thành công/thất bại.
- `StandardJavaFileManager`: quản lý vị trí các tệp nguồn, class, module và thư viện; chuyển `Path` thành `JavaFileObject`; cho compiler truy cập hệ thống tệp theo các vị trí chuẩn. File manager **không tự biên dịch**.
- `DiagnosticCollector<JavaFileObject>`: nhận lỗi/cảnh báo có thông tin dòng, cột, nguồn và mô tả; thuận tiện cho IDE/build tool phản hồi người dùng.

Các API này vẫn đang được hỗ trợ trên JDK hiện đại. `JavaCompiler` đã có từ Java 6; các khả năng cho *module-oriented locations* và `setLocationForModule` xuất hiện từ Java 9; overload `getJavaFileObjectsFromPaths(Collection<? extends Path>)` là cách gọi được khuyến nghị từ Java 13 trở lên. Bài này dùng **Java 17+** để tránh ví dụ đã lỗi thời nhưng vẫn làm rõ kiến thức mô-đun hóa khởi đầu ở Java 9.

**Phân biệt:** dùng API trong chương trình gọi compiler **không đồng nghĩa** chạy `javac` bằng một tiến trình hệ điều hành mới. Tác vụ ở đây được khởi tạo từ JVM hiện tại. Muốn cách ly nguồn mã không đáng tin, cần thiết kế môi trường chạy riêng; API biên dịch không cung cấp sandbox.

## 2. Các vị trí chuẩn trong dự án module

Java compiler hỗ trợ nhiều `JavaFileManager.Location`, thường sử dụng các hằng của `StandardLocation`:

| Location | Nội dung và mục đích | Thường tương đương trong javac CLI |
| --- | --- | --- |
| `MODULE_SOURCE_PATH` | **Thư mục nguồn của nhiều named modules**; compiler nhận biết `module-info.java` của từng module | `--module-source-path` |
| `CLASS_OUTPUT` | Nơi ghi `.class` và `module-info.class`; khi biên dịch nhiều module, sẽ có các thư mục con theo tên module | `-d` |
| `MODULE_PATH` | Tìm **module đã biên dịch** (modular JAR hoặc thư mục chứa các module) khi giải quyết `requires` | `--module-path` hoặc `-p` |
| `CLASS_PATH` | Tìm thư viện/class theo cơ chế classpath, thường dùng cho mã **unnamed module** hoặc tương thích thư viện không có module | `--class-path` hoặc `-cp` |
| `SOURCE_PATH` | Tìm nguồn theo package hierarchy; thích hợp khi không biên dịch cùng lúc nhiều module | `--source-path` |
| `ANNOTATION_PROCESSOR_MODULE_PATH` | Tìm annotation processors đã đóng gói dưới dạng modules, khi có nhu cầu annotation processing | `--processor-module-path` |

Lưu ý:

1. `MODULE_SOURCE_PATH` **khác** `MODULE_PATH`: một bên chứa **source**, một bên chứa các **module đã biên dịch**. Đặt `.java` vào `MODULE_PATH` không biến chúng thành code cần biên dịch.
2. `MODULE_SOURCE_PATH` của nhiều module phải khớp **cấu trúc thư mục module**, chẳng hạn `src/com.example.app/module-info.java`. Compiler sẽ đọc cấu hình JPMS từ những tệp `module-info.java`.
3. `CLASS_OUTPUT` là một thư mục đích; với `StandardJavaFileManager.setLocationFromPaths` và output location, tạo thư mục đó trước và truyền **chính xác một root output path**.
4. `module-info.java` mô tả quyền đọc/phơi bày module ở cấp biên dịch; `exports` công bố package ra bên ngoài, `requires` khai báo dependency. Hai từ khóa khác nhau và thường phải có cả hai trong quan hệ library → app.

## 3. Ví dụ: hai named modules phụ thuộc nhau

Tạo thư mục `modular-compiler-demo` với cấu trúc sau:

```text
modular-compiler-demo/
├── CompileModules.java              # Chương trình dùng Compiler API
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/example/greetings/Greeting.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

Tên module có dấu chấm (`com.example.greetings`), tên package được tổ chức theo thư mục (`com/example/greetings`); đây là hai khái niệm có liên hệ nhưng **không phải một**.

### 3.1. Module thư viện: com.example.greetings

`src/com.example.greetings/module-info.java`:

```java
module com.example.greetings {
    exports com.example.greetings;
}
```

`src/com.example.greetings/com/example/greetings/Greeting.java`:

```java
package com.example.greetings;

public final class Greeting {
    public static String hello(String who) {
        return "Hello, " + who;
    }
}
```

`exports com.example.greetings` cho phép module khác sử dụng những kiểu `public` trong package này theo các quy tắc JPMS. Không có `exports` thì `Greeting` không được truy cập từ module app, dù class được khai báo `public`.

### 3.2. Module ứng dụng: com.example.app

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greetings;
}
```

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greetings.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.hello("Java"));
    }
}
```

Lúc này app *đọc được* module `com.example.greetings` vì có `requires`, và *truy cập được* `Greeting` vì thư viện đã `exports` đúng package. Đây là một **module graph** đơn giản: `com.example.app` → `com.example.greetings`.

## 4. Chương trình dùng JavaCompiler + StandardJavaFileManager

Tạo tệp **`CompileModules.java`** tại gốc thư mục demo. Chương trình này biên dịch cả hai module trong cùng một lần gọi API.

```java
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

public final class CompileModules {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK containing javac");
        }

        Path sourceRoot = Path.of("src").toAbsolutePath();
        Path outputRoot = Path.of("out").toAbsolutePath();
        Files.createDirectories(outputRoot);

        List<Path> sources = List.of(
                sourceRoot.resolve("com.example.greetings/module-info.java"),
                sourceRoot.resolve(
                        "com.example.greetings/com/example/greetings/Greeting.java"),
                sourceRoot.resolve("com.example.app/module-info.java"),
                sourceRoot.resolve("com.example.app/com/example/app/Main.java"));

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        boolean success;

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.MODULE_SOURCE_PATH, List.of(sourceRoot));
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(outputRoot));

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(sources);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17"), null, units);

            success = Boolean.TRUE.equals(task.call());
        }

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            System.err.printf("%s:%d: %s%n", d.getKind(),
                    d.getLineNumber(), d.getMessage(Locale.ROOT));
        }

        System.out.println("compiled modules: " + success);
        if (!success) {
            System.exit(1);
        }
    }
}
```

### 4.1. Chạy thử từ gốc demo

Mở terminal tại thư mục `modular-compiler-demo`, cài JDK có `javac` và chạy:

```bash
javac -encoding UTF-8 CompileModules.java
java CompileModules
java --module-path out -m com.example.app/com.example.app.Main
```

Stdout từ lần chạy thành công (đã kiểm tra với JDK 24; mã target Java 17):

```text
compiled modules: true
Hello, Java
```

Dòng đầu đến từ `CompileModules`; dòng thứ hai từ `com.example.app.Main`. Sau khi biên dịch, thư mục `out` có dạng:

```text
out/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/example/greetings/Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Chú ý `javac -encoding UTF-8 CompileModules.java` chỉ biên dịch **chương trình nhúng compiler**. Lệnh `java CompileModules` mới thực thi `JavaCompiler` để biên dịch **hai module trong `src`**. Cuối cùng, `java --module-path out -m ...` mới **chạy app trong module graph**. Ba bước có vai trò khác nhau.

`-m com.example.app/com.example.app.Main` trong lệnh `java` gồm **tên module / tên main class đầy đủ**. Tùy chọn `--module-path out` dùng compiled module hierarchy, không phải source root `src`.

## 5. Giải thích tuần tự luồng API

### 5.1. ToolProvider và compiler runtime

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
```

`ToolProvider` thuộc module chuẩn `java.compiler`. Compiler hệ thống thực tế do provider, thông thường `jdk.compiler` trong JDK, cung cấp. Trên runtime image đã rút gọn không có compiler, kết quả có thể là `null`. Vì vậy phải **kiểm tra null** hoặc dùng công cụ build được triển khai cùng JDK phù hợp. Chỉ việc có JVM để *chạy* ứng dụng không đồng nghĩa có compiler để *biên dịch* mã Java.

### 5.2. File manager làm nhiệm vụ I/O và tìm modules

```java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    manager.setLocationFromPaths(
            StandardLocation.MODULE_SOURCE_PATH, List.of(sourceRoot));
    manager.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, List.of(outputRoot));
    // ... tạo compilation units và gọi compiler
}
```

- `getStandardFileManager(...)` tạo file manager chuẩn cho các tệp bình thường; tham số `charset` hướng dẫn cách giải mã source qua file manager. Sử dụng `StandardCharsets.UTF_8` để tránh phụ thuộc cấu hình máy.
- `setLocationFromPaths(MODULE_SOURCE_PATH, List.of(sourceRoot))` khai báo **root chứa nhiều module**, không phải đường dẫn riêng của `Greeting.java`. Trong ví dụ, `sourceRoot` trỏ đến `.../src` và các module là thư mục con.
- `setLocationFromPaths(CLASS_OUTPUT, List.of(outputRoot))` thay cho việc truyền tùy chọn `-d out` trong `getTask`. Khi compile nhiều module, compiler tạo thư mục con mang tên từng module bên dưới `out`.
- `Files.createDirectories(outputRoot)` tạo sẵn output root trước khi gắn vào output location. Hãy chắc chắn build tool có quyền ghi vào nơi này.
- `try-with-resources` đóng manager sau khi compile, giải phóng file/ZIP/JAR handles. Không đóng manager trước lúc `task.call()` kết thúc.

Các overload `setLocationFromPaths` và `setLocationForModule` có từ Java 9. Trong cùng một location, **gọi lại `setLocationFromPaths` sẽ xóa các association per-module** được tạo trước đó bằng `setLocationForModule`. Nếu cần override theo từng module, khai báo root chung **trước**, sau đó mới cấu hình module riêng.

### 5.3. Đổi Path thành JavaFileObject

```java
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(sources);
```

- `sources` chứa **đường dẫn tới các tệp .java cụ thể**, bao gồm `module-info.java` của từng module.
- `getJavaFileObjectsFromPaths(Collection<? extends Path>)` là overload hiện hành nên dùng trên Java 17+. Overload nhận `Iterable<? extends Path>` đã được **deprecated từ Java 13** vì `Path` cũng implement `Iterable<Path>`, dễ truyền nhầm một `Path` rồi bị hiểu là nhiều thành phần của đường dẫn.
- Không truyền **thư mục** vào `getJavaFileObjectsFromPaths`; API mong các file nguồn. Nếu muốn tự động thu thập mã nguồn, tự duyệt `Files.walk(...)` có lọc file `.java` và xây dựng `List<Path>` trước khi gọi, đóng stream khi xong. Với bài học này, danh sách cố định giúp kết quả dễ kiểm tra.
- File manager quyết định cách đọc source theo filesystem/location; `JavaFileObject` là giao diện trừu tượng cho compiler, không phải bytecode.

### 5.4. getTask và call

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17"), null, units);
boolean success = Boolean.TRUE.equals(task.call());
```

Sáu tham số của `getTask`, theo thứ tự:

| Tham số | Giá trị mẫu | Ý nghĩa |
| --- | --- | --- |
| `Writer out` | `null` | Kênh thông tin bổ sung mà compiler có thể ghi; null dùng mặc định |
| `JavaFileManager fileManager` | `manager` | Chịu trách nhiệm lấy nguồn, vị trí module, ghi output |
| `DiagnosticListener` | `diagnostics` | Thu thập lỗi/cảnh báo theo cấu trúc |
| `Iterable<String> options` | `List.of("--release", "17")` | Cấu hình compiler; ở đây biên dịch theo API/language target Java 17 |
| `Iterable<String> classes` | `null` | Danh sách tên class dành cho **annotation processing** nếu được yêu cầu; **không phải danh sách tên module** |
| `Iterable<? extends JavaFileObject> compilationUnits` | `units` | Các tệp nguồn thực sự biên dịch, trong ví dụ gồm hai `module-info.java` và hai class |

`task.call()` là bước **thực thi**, trả `Boolean.TRUE` khi biên dịch thành công. Tạo `getTask` không đồng nghĩa việc biên dịch đã hoàn tất. Một `CompilationTask` là một tác vụ; không gọi `call()` nhiều lần trên cùng instance để biên dịch lại. Nếu muốn compile lần khác, tạo task mới và có thể tái sử dụng **file manager một cách tuần tự**, miễn vẫn mở và được cấu hình phù hợp.

`--release 17` khác `-source 17`: nó nhằm biên dịch theo language/class-file/API của Java 17 (trong phạm vi compiler hỗ trợ), tránh vô tình liên kết tới Java API chỉ có trên JDK chạy chương trình. Nếu target là Java 17, hãy chạy chương trình trên runtime 17+ tương thích. Module system có từ Java 9; `--release 8` **không** dùng để biên dịch ứng dụng chứa `module-info.java`.

### 5.5. DiagnosticCollector và thông báo lỗi

`DiagnosticCollector<JavaFileObject>` gom `Diagnostic` theo từng lần biên dịch. Thông tin hữu ích:

- `getKind()`: loại thông báo (ERROR, WARNING, MANDATORY_WARNING, NOTE...).
- `getSource()`: nguồn liên quan khi có; có thể `null` đối với lỗi tổng quát của compiler.
- `getLineNumber()`, `getColumnNumber()`: dòng/cột khi có; có thể là giá trị sentinel khi không xác định.
- `getCode()`: mã thông báo compiler để xử lý máy.
- `getMessage(Locale)`: thông điệp dành cho người đọc, có thể thay đổi theo JDK và locale.

Không nên parse tiếng Anh trong `getMessage` để quyết định nghiệp vụ. Muốn báo lỗi IDE thân thiện, lấy file, dòng, cột, mức độ; chuẩn hóa đường dẫn và giới hạn thông tin khi đưa ra bên ngoài.

Trong demo, `System.err.printf` in `kind`, số dòng và mô tả; vì compiler thành công nên không có diagnostic và chỉ thấy `compiled modules: true`. Khi cố tình xóa `requires com.example.greetings;` khỏi `com.example.app/module-info.java`, chương trình sẽ báo lỗi liên quan tới module app không đọc được package từ module greetings. **Câu chữ chẩn đoán cụ thể có thể khác giữa các JDK**, vì vậy không gán một stdout cố định cho tình huống lỗi.

## 6. MODULE_PATH, classpath và module dependency đã biên dịch

Trong demo, cả hai module được biên dịch **từ source** trong cùng một task, nên module graph được giải quyết qua `MODULE_SOURCE_PATH`. Dự án thực thường phụ thuộc vào modular JAR hoặc module build sẵn. Khi đó, cấu hình `MODULE_PATH` trước khi gọi `getTask`:

```java
// Mã minh họa bên trong try(StandardJavaFileManager manager = ...).
Path compiledDependencies = Path.of("modular-libs").toAbsolutePath();
manager.setLocationFromPaths(
        StandardLocation.MODULE_PATH, List.of(compiledDependencies));
```

`modular-libs` ở đây là một thư mục **đã tồn tại** chứa các modular JAR hoặc các module được tổ chức đúng để javac tìm thấy; đoạn này **không nằm trong chương trình demo độc lập ở trên**, vì demo không có dependency bên ngoài. Trong trường hợp phụ thuộc vào một modular JAR riêng lẻ, `MODULE_PATH` có thể chứa trực tiếp path tới JAR theo cách provider hỗ trợ.

Tệp `module-info.java` của app vẫn cần `requires ten.module;` cho các module được đọc; việc đặt một JAR trên module path **không tự động tạo `requires`**. Ngoài ra:

- `MODULE_PATH` là nơi compiler tìm **module dependency** đã biên dịch.
- `CLASS_PATH` dành cho code theo classpath, không biểu diễn module graph của named modules như `MODULE_PATH`.
- `MODULE_SOURCE_PATH` dành cho source của các module đang được biên dịch.
- `CLASS_OUTPUT` dành cho kết quả.
- Khi chạy, lệnh `java --module-path ... -m ...` phải thấy module ứng dụng và những module dependency cần thiết. Compile thành công không bảo đảm runtime module path đã đúng.

**Lưu ý về automatic modules:** một JAR không có `module-info.class` khi đặt trên module path có thể được xem như *automatic module* nếu phù hợp. Tên module có thể do manifest hoặc tên file quyết định, gây biến động nếu không kiểm soát. Dự án mới nên ưu tiên module names và dependency rõ ràng; xác minh tên module của JAR trước khi viết `requires`.

## 7. Phân biệt cấu hình cả path với cấu hình riêng từng module

`StandardJavaFileManager` còn có:

```java
manager.setLocationForModule(
        StandardLocation.MODULE_SOURCE_PATH,
        "com.example.app",
        List.of(Path.of("custom-app-source").toAbsolutePath()));
```

Đây là **mã minh họa**, dành cho dự án có source directory của `com.example.app` khác pattern root chung. `custom-app-source` phải là **root chứa `module-info.java` và package tree của module app**; phải tồn tại và chứa mã nguồn phù hợp. `setLocationForModule` chỉ hợp lệ với location hướng module hoặc output. Không gọi sau đó `setLocationFromPaths(MODULE_SOURCE_PATH, ...)` nếu muốn giữ override: lệnh set root mới sẽ xóa mapping riêng của location đó.

Khi cần truy vấn module đã được file manager nhận ra, các phương thức kế thừa từ `JavaFileManager` gồm:

- `getLocationForModule(location, moduleName)`: tìm location package-oriented tương ứng với module đã đặt trên location module-oriented. Kết quả có thể `null` nếu không xác định được module.
- `inferModuleName(moduleLocation)`: lấy tên module từ một module location phù hợp.
- `listLocationsForModules(location)`: liệt kê những locations đại diện cho modules mà file manager tìm được.

Các API này giúp công cụ IDE/build phân giải đường dẫn module một cách cấu trúc, nhưng không thay cho việc kiểm tra dependency graph, exports, module-info, và quyền đọc của module. Với compiler mặc định, đường dẫn được tổ chức theo module như demo thường là phương án đơn giản nhất.

## 8. Khi muốn tìm mọi file .java thay vì nhập danh sách thủ công

Trong công cụ lớn, danh sách `sources` có thể được tạo bằng `Files.walk`, có lọc extension và sắp xếp để log/build ổn định. Ví dụ **đoạn thay thế** cho phần khởi tạo `List<Path> sources` ở `CompileModules.java` (cần import `java.util.stream.Stream`):

```java
List<Path> sources;
try (var stream = Files.walk(sourceRoot)) {
    sources = stream
            .filter(Files::isRegularFile)
            .filter(path -> path.getFileName().toString().endsWith(".java"))
            .sorted()
            .toList();
}
if (sources.isEmpty()) {
    throw new IllegalArgumentException("No Java source files found");
}
```

Đây là code đặt **trong phương thức `main` của ví dụ**, không phải chương trình độc lập. Duyệt cả cây có thể chậm với repository lớn; trong build system thực, dùng cơ chế source sets/file collections của hệ thống build và giới hạn đúng module roots. Không duyệt tùy tiện thư mục đầu vào không đáng tin.

`getJavaFileObjectsFromPaths(sources)` vẫn nhận collection của những **file cụ thể**. Đừng truyền `sourceRoot` trực tiếp rồi chờ compiler tự quét toàn bộ thư mục; đó không phải ý nghĩa của API này.

## 9. Xử lý lỗi và kiểm tra output đúng module

Một số lỗi điển hình:

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | JVM/runtime image đang chạy thiếu compiler provider | Dùng JDK có `jdk.compiler` hoặc triển khai build trong môi trường JDK đầy đủ |
| `module not found: com.example.greetings` | Không thấy module ở module-source-path/module-path, sai tên thư mục hoặc `module-info.java` | Kiểm tra source root, tên module, `requires` và phân loại dependency source hay compiled |
| Package không nhìn thấy dù class `public` | Thiếu `requires` bên dùng, hoặc thiếu `exports` bên cung cấp | Sửa `module-info.java` của đúng module |
| Source file bị coi như ở unnamed module hoặc sai module | Cấu trúc `src/<module-name>/...` sai hoặc dùng `SOURCE_PATH` cho nhiều module | Dùng `MODULE_SOURCE_PATH` và kiểm tra `module-info.java` |
| `IllegalArgumentException` khi đọc source paths | Truyền thư mục vào `getJavaFileObjectsFromPaths` hoặc sai kinds/paths | Truyền collection `Path` của file `.java` cụ thể |
| Không tạo được output | `CLASS_OUTPUT` không tồn tại, không đủ quyền ghi hoặc chỉ định sai số lượng paths | `Files.createDirectories(out)`, cung cấp một output root hợp lệ |
| Compiler báo thành công nhưng chạy `ClassNotFoundException` hoặc lỗi module launch | Lệnh `java -m` sai tên module/main class hoặc runtime module path khác output | Kiểm tra `out/<module>/module-info.class` và chạy `java --module-path out -m module/fully.qualified.Main` |
| Class biên dịch dùng API Java quá mới | Không đặt target tương ứng với runtime | Dùng `--release` phù hợp với JDK đích, kiểm tra bằng CI |
| Chỉ thấy thông báo lỗi khó parse | Dựa vào output dạng chuỗi thay vì diagnostics | Dùng `DiagnosticCollector`, quan sát kind/code/source/line/column |

### Bài tập chủ động gây lỗi

1. Xóa `requires com.example.greetings;` khỏi module app; biên dịch lại và xem `DiagnosticCollector` báo lỗi khả năng đọc module. Khôi phục `requires`.
2. Xóa `exports com.example.greetings;` khỏi module thư viện; biên dịch lại và xem lỗi truy cập package. Khôi phục `exports`.
3. Đổi `Path.of("src")` thành một thư mục không chứa các module và kiểm tra đường dẫn source: lỗi có thể xuất hiện trước khi `task.call()` hoặc trong diagnostic, tùy điểm lỗi.
4. Bỏ `Files.createDirectories(outputRoot)` khi `out` chưa có để kiểm chứng output location yêu cầu thư mục hợp lệ.
5. Sau khi biên dịch thành công, thử chạy app với sai `--module-path`; phân biệt lỗi **khi compile** và lỗi **khi launch**.

Đối với các bài thử lỗi, không kỳ vọng thông điệp giống nhau trên mọi bản JDK; xác nhận loại lỗi và ý nghĩa thực tế là quan trọng hơn.

## 10. Cách ứng dụng trong hệ thống build/IDE hiện đại

**Tái sử dụng file manager:** tài liệu `JavaCompiler` cho phép dùng một standard file manager cho **nhiều lần biên dịch tuần tự**, giúp cache thông tin đọc JAR và giảm I/O. Tạo **task mới** cho mỗi lần biên dịch và đóng manager sau khi công việc hoàn tất. Đừng chia sẻ manager cho nhiều tác vụ đồng thời nếu không có bảo đảm thread-safety rõ ràng từ provider.

**Phân biệt biên dịch và tải class:** sau `task.call()`, compiler đã tạo file `.class`, nhưng JVM đang chạy **không tự load hoặc thay thế** các class đó. Nếu cần chạy plugin đã biên dịch, thiết kế việc tạo ModuleLayer/class loading và quản lý vòng đời riêng; `StandardJavaFileManager` không đóng vai trò class loader ứng dụng tự động.

**Annotation processing:** `classes` trong `getTask` là tham số liên quan annotation processing, không phải `-m` của command line. Nếu build yêu cầu annotation processors, cấu hình `ANNOTATION_PROCESSOR_PATH` hoặc `ANNOTATION_PROCESSOR_MODULE_PATH` và các tùy chọn liên quan một cách tường minh, tùy compiler/JDK. Processor được kích hoạt có thể chạy code trong quá trình build; chỉ dùng processor đáng tin và cấu hình rõ ràng trên CI. Nếu không cần, có thể đặt `-proc:none` trong `options` để tắt xử lý annotation.

**Phân tách build và chạy:** output compiler là dữ liệu build. Việc kiểm thử/chạy named module cần `java --module-path ... -m ...` phù hợp hoặc một cơ chế test runner/module layer được cấu hình rõ ràng. Không chỉ thêm `out` vào `-cp` rồi kỳ vọng module graph/`requires`/`exports` hoạt động tương tự named module.

**Tự động hóa ổn định:** quản lý nguồn/đích theo `Path`, giữ thứ tự file ổn định, phân tách thư mục output sạch theo build, ghi diagnostic đầy đủ, báo trạng thái thất bại cho CI. Tránh trộn bytecode cũ từ lần compile trước vào kết quả mới vì nó có thể làm ẩn thiếu sót của nguồn hiện tại.

**Bảo mật:** Compiler API phục vụ mã nguồn mà ứng dụng quyết định biên dịch; nó không phải môi trường thực thi an toàn cho mã không đáng tin. Một service nhận mã từ người dùng cần giới hạn tài nguyên, filesystem/network, annotation processors và quyền thực thi trong môi trường cách ly phù hợp. Tùy chọn `-proc:none` giảm nguy cơ processor không mong muốn nhưng **không biến việc biên dịch hoặc chạy mã thành sandbox**.

## 11. Tự kiểm tra kiến thức

1. `JavaCompiler` và `StandardJavaFileManager` có trách nhiệm khác nhau ở điểm nào?
2. Khi biên dịch cùng lúc hai named modules từ source, vì sao phải dùng `MODULE_SOURCE_PATH` thay cho `MODULE_PATH`?
3. Vì sao `getJavaFileObjectsFromPaths(List.of(sourceRoot))` là lựa chọn sai khi `sourceRoot` là thư mục?
4. `CLASS_OUTPUT` trong ví dụ tạo các file `.class` ở những vị trí nào? Vì sao có thư mục con theo tên module?
5. Khi `Greeting` là `public`, tại sao app vẫn cần `requires` và library cần `exports`?
6. Trong `getTask`, `classes` có phải là tên các module cần compile không? Nếu không, `compilationUnits` chứa gì?
7. `--release 17` giải quyết vấn đề gì khi chạy chương trình biên dịch trên JDK mới hơn?
8. Khi `task.call()` trả `false`, vì sao nên đọc `DiagnosticCollector` thay vì chỉ kiểm tra Boolean?
9. Gọi `setLocationFromPaths(MODULE_SOURCE_PATH, ...)` sau `setLocationForModule` có tác động gì tới per-module mapping?
10. Vì sao biên dịch thành công chưa đồng nghĩa có thể gọi `java Main` trực tiếp để chạy app named module?

**Điều cần nhớ:** trong dự án mô-đun, `JavaCompiler` là **bộ biên dịch**, `StandardJavaFileManager` là **bản đồ source/module/output**, và `module-info.java` là **hợp đồng dependency/export**. Dùng `MODULE_SOURCE_PATH` cho source nhiều module, `MODULE_PATH` cho dependency đã build, `CLASS_OUTPUT` cho bytecode, `DiagnosticCollector` cho lỗi và `try-with-resources` để quản lý file manager. Ví dụ này chạy trên Java 17+ và sử dụng những API còn được hỗ trợ hiện nay.

## Tài liệu chính thức

- [Java SE 25 — JavaCompiler API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, diagnostics, tái sử dụng file manager.
- [Java SE 25 — StandardJavaFileManager API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): `setLocationFromPaths`, `setLocationForModule`, `getJavaFileObjectsFromPaths(Collection)`.
- [Java SE 25 — StandardLocation API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/StandardLocation.html): `MODULE_SOURCE_PATH`, `MODULE_PATH`, `CLASS_OUTPUT` và các locations khác.
- [Java SE 25 — JavaFileManager API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaFileManager.html): `getLocationForModule`, `inferModuleName`, `listLocationsForModules`.
- [Java SE 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--module-path`, `--release` và cấu trúc module compilation.
