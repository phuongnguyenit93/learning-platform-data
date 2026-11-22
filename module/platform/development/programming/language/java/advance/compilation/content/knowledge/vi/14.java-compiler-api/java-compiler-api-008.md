# Quản lý file manager, tài nguyên và các lần biên dịch kế tiếp bằng Java Compiler API

Khi dùng `javac` từ terminal, công cụ tự tìm source, thư viện và nơi xuất file. Khi nhúng trình biên dịch Java vào **IDE, công cụ build, bộ sinh mã, bài kiểm tra hoặc một dịch vụ compile** bằng API `javax.tools`, ứng dụng phải quản lý rõ những việc đó: file Java được lấy từ đâu, kết quả `.class` ghi vào đâu, resource nào nằm trên classpath, khi nào có thể sử dụng output, và vòng đời của file manager qua **nhiều lượt biên dịch liên tiếp**.

Các thành phần trọng tâm:

- **`JavaCompiler`**: tạo một compilation task để chạy trình biên dịch.
- **`StandardJavaFileManager`**: ánh xạ các `JavaFileObject`/`FileObject` sang file hệ thống, quản lý source path, classpath, output locations và tài nguyên I/O của trình biên dịch.
- **`JavaFileObject` / `FileObject`**: trừu tượng hóa source Java, bytecode hoặc tài nguyên không nhất thiết phải nằm ở một file vật lý.
- **`DiagnosticListener` / `DiagnosticCollector`**: nhận các cảnh báo/lỗi của lần biên dịch.
- **`JavaCompiler.CompilationTask`**: đối tượng đại diện cho **một** lần compile; không phải đối tượng được gọi đi gọi lại để compile nhiều lần.

Bài học sử dụng Java 17+, bao gồm ví dụ đầy đủ **biên dịch thư viện ở lượt 1, biên dịch ứng dụng sử dụng thư viện đó ở lượt 2, viết resource và nạp kết quả** bằng API chuẩn. Sau đó phân tích các điểm dễ gây lỗi khi tái sử dụng file manager, thay đổi output, quản lý class loader và kiểm soát tài nguyên.

## 1. Bản đồ các interface quan trọng

| Thành phần | Nhiệm vụ chính | Vòng đời thực hành |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler của môi trường JDK đang chạy | Lấy trước khi lập task; có thể trả `null` |
| `JavaCompiler` | Tạo task từ options, file manager và compilation units | Một compiler có thể tạo nhiều task |
| `JavaCompiler.CompilationTask` | Đại diện một lượt biên dịch, có `call()` | **Tạo mới cho mỗi lượt**; không gọi `call()` lần thứ hai |
| `JavaFileManager` | Giao diện truy cập file để compiler tìm class, source, resources | Có thể có implementation chuẩn hoặc tùy biến |
| `StandardJavaFileManager` | File manager tiêu chuẩn có API làm việc với `Path`/`File` và các locations | Có thể tái sử dụng **tuần tự**, cần `flush()`/`close()` hợp lý |
| `JavaFileObject` | Source/class Java, với `Kind.SOURCE` hoặc `Kind.CLASS` | Input/output thuộc từng task và file manager |
| `FileObject` | Tệp tổng quát, gồm các resource ngoài `.java`/`.class` | Đọc/ghi bằng reader, writer hoặc stream |
| `DiagnosticCollector<JavaFileObject>` | Thu thập diagnostic của một lượt | Nên tạo riêng cho từng task để tránh trộn lỗi |
| `StandardLocation` | Tên vị trí chuẩn: `CLASS_PATH`, `SOURCE_PATH`, `CLASS_OUTPUT`, `SOURCE_OUTPUT`... | Cấu hình trên file manager theo mục đích |

Luồng một compilation task:

~~~text
Source files / JavaFileObject
          |
          v
JavaCompiler.getTask(writer, fileManager, diagnostics, options, classes, units)
          |
          v
CompilationTask.call()
          |
          +--> FileManager: tìm source/class/module/resource
          |
          +--> Diagnostics: báo lỗi và cảnh báo
          |
          +--> FileManager: ghi .class và output cần thiết
          |
          v
Kết quả true / false
~~~

`task.call()` trả `Boolean.TRUE` khi compilation task thành công theo hợp đồng tool. Nó **không** đồng nghĩa với việc các class đã được tải vào JVM hiện tại, các file đầu ra đều đã được đóng gói vào JAR, hoặc chương trình chắc chắn chạy được với mọi runtime classpath.

## 2. Khởi tạo compiler từ JDK đang chạy

Cách lấy compiler chuẩn:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "This runtime has no system Java compiler"
    );
}
~~~

Đoạn trên là **fragment của một method**, không phải chương trình độc lập.

`getSystemJavaCompiler()` có thể trả `null` nếu runtime không cung cấp module/tool compiler thích hợp. Trên Java 9+, compiler hệ thống thuộc module `jdk.compiler` của JDK; ứng dụng được đóng bằng runtime image tối giản có thể không bao gồm module đó. Cài JDK đầy đủ hoặc xây runtime image có compiler nếu chương trình thật sự cần biên dịch tại runtime.

Kiểm tra môi trường:

~~~bash
java -version
javac -version
~~~

Không suy đoán phiên bản compiler qua `System.getProperty("java.version")` mà không hiểu module/toolchain: với API này bạn dùng compiler từ runtime đang nạp nó; công cụ build ngoài tiến trình có thể dùng JDK khác.

### Vì sao nên dùng file manager do compiler tạo?

~~~java
try (javax.tools.StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                null,
                java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8
        )) {
    // Tạo compilation tasks, đọc/ghi file.
}
~~~

- Đối số listener `null` nghĩa là file manager không nhận một diagnostic listener riêng ở lúc tạo.
- `Locale.ROOT` phục vụ lựa chọn locale khi cần thông báo; không thay đổi quy tắc Java.
- `StandardCharsets.UTF_8` đặt encoding của file manager chuẩn cho source dạng ký tự.
- `try-with-resources` gọi `close()` kể cả khi có exception, tránh giữ file handle/JAR handle lâu hơn cần thiết.

File manager chuẩn có thể cache thông tin JAR và file để phục vụ nhiều compilation task **tuần tự**. Tái sử dụng thường tiết kiệm hơn khởi tạo mới liên tục, nhưng cần nhớ locations cấu hình và cache của nó vẫn thuộc cùng manager. Không giả định manager này thread-safe để nhiều task biên dịch đồng thời.

## 3. Các location ảnh hưởng compile và tài nguyên

Một `StandardJavaFileManager` ánh xạ các `StandardLocation` sang đường dẫn hoặc tập đường dẫn:

| Location | Mục đích | Hình thức minh họa |
| --- | --- | --- |
| `StandardLocation.CLASS_OUTPUT` | Gốc output của class được biên dịch | `build/classes` |
| `StandardLocation.SOURCE_OUTPUT` | Gốc source được annotation processor sinh, nếu cấu hình | `build/generated-sources` |
| `StandardLocation.CLASS_PATH` | Thư mục/JAR nơi compiler tìm class phụ thuộc | `build/classes`, `libs/tool.jar` |
| `StandardLocation.SOURCE_PATH` | Source root để compiler tìm `.java` bổ sung | `src/main/java` |
| `StandardLocation.ANNOTATION_PROCESSOR_PATH` | Vị trí tìm annotation processor trong cấu hình phù hợp | `processors/processor.jar` |
| `StandardLocation.MODULE_PATH` | Vị trí tìm các named modules | `mods`, `libs/module.jar` |
| `StandardLocation.PLATFORM_CLASS_PATH` | Platform classes trong cấu hình phù hợp; semantics thay đổi theo JDK | Không nên tự tùy biến tùy tiện |

Với API làm việc theo `Path`:

~~~java
manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        java.util.List.of(classesDirectory)
);
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        java.util.List.of(classesDirectory, dependencyJar)
);
~~~

Hai dòng là **fragment trong một method**, giả định `manager`, `classesDirectory` và `dependencyJar` đều hợp lệ. Đường dẫn `classesDirectory` phải là root chứa cây package của file `.class`. Ví dụ:

~~~text
build/classes/
└── example/
    ├── lib/Messages.class
    └── app/App.class
~~~

Để compiler tìm `example.lib.Messages`, đặt **`build/classes`** lên `CLASS_PATH`, không đặt `build/classes/example/lib`. Để JVM chạy `example.app.App`, runtime classpath cũng phải chỉ đến root tương ứng.

### Dùng options hay cấu hình trên file manager?

Có hai cách thường gặp:

- Truyền CLI-style options như `-d`, `-classpath`, `--release` vào `compiler.getTask(...)`.
- Cấu hình trực tiếp những vị trí có API `StandardJavaFileManager.setLocationFromPaths(...)`.

**Không nên cấu hình mâu thuẫn cùng location bằng hai cách** trong một task. Khi dùng API file manager, ưu tiên một nơi làm nguồn sự thật cho đường output, compile classpath và module path. Các options ngôn ngữ như `--release 17`, `-encoding UTF-8` có thể truyền riêng.

## 4. Ví dụ đầy đủ: biên dịch hai lượt, tái sử dụng file manager

Thí nghiệm sau chỉ cần **JDK 17+** và một file Java bên ngoài tên **`CompileTwiceDemo.java`**. Chương trình:

1. Tạo thư mục tạm, source của `example.lib.Messages` và `example.app.App`.
2. Dùng một `StandardJavaFileManager` với `CLASS_OUTPUT` trỏ đến thư mục `classes`.
3. Tạo task thứ nhất để compile `Messages.java`.
4. `flush()` manager, sau đó thêm thư mục `classes` vào `CLASS_PATH`.
5. Tạo **task mới** compile `App.java` phụ thuộc `Messages.class` từ lượt trước.
6. Tạo resource `config/flag.txt` qua file manager trong `CLASS_OUTPUT`.
7. Đóng manager, tạo một `URLClassLoader` riêng để chạy `App.main` và đọc resource.

**Toàn bộ file `CompileTwiceDemo.java`:**

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompileTwiceDemo {
    private static Path writeSource(
            Path sourceRoot, String relativeName, String source)
            throws Exception {
        Path file = sourceRoot.resolve(relativeName);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
        return file;
    }

    private static boolean compile(
            JavaCompiler compiler,
            StandardJavaFileManager manager,
            Path source) {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Iterable<? extends JavaFileObject> units =
                manager.getJavaFileObjectsFromPaths(List.of(source));

        JavaCompiler.CompilationTask task = compiler.getTask(
                null,
                manager,
                diagnostics,
                List.of("--release", "17", "-encoding", "UTF-8"),
                null,
                units
        );

        boolean ok = Boolean.TRUE.equals(task.call());

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            System.err.println(
                    d.getKind() + " at line "
                            + d.getLineNumber() + ": "
                            + d.getMessage(Locale.ROOT)
            );
        }
        return ok;
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK 17+");
        }

        Path root = Files.createTempDirectory("compiler-api-");
        Path src = root.resolve("src");
        Path classes = root.resolve("classes");
        Files.createDirectories(classes);

        Path messagesSource = writeSource(
                src,
                "example/lib/Messages.java",
                """
                package example.lib;

                public final class Messages {
                    private Messages() {}

                    public static String text() {
                        return "compiled in pass 1";
                    }
                }
                """
        );

        Path appSource = writeSource(
                src,
                "example/app/App.java",
                """
                package example.app;

                import example.lib.Messages;

                public final class App {
                    public static void main(String[] args) {
                        System.out.println(Messages.text());
                    }
                }
                """
        );

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             null, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));

            boolean first = compile(compiler, manager, messagesSource);
            System.out.println("pass 1: " + first);
            if (!first) {
                return;
            }

            manager.flush();

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_PATH, List.of(classes));

            boolean second = compile(compiler, manager, appSource);
            System.out.println("pass 2: " + second);
            if (!second) {
                return;
            }

            Files.createDirectories(classes.resolve("config"));
            FileObject resource = manager.getFileForOutput(
                    StandardLocation.CLASS_OUTPUT,
                    "",
                    "config/flag.txt",
                    null
            );
            try (OutputStream stream = resource.openOutputStream()) {
                stream.write(
                        "managed-resource\n"
                                .getBytes(StandardCharsets.UTF_8));
            }
        }

        boolean bothExist =
                Files.exists(classes.resolve("example/lib/Messages.class"))
                        && Files.exists(
                                classes.resolve("example/app/App.class"));

        System.out.println("class files: " + bothExist);

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { classes.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> app = Class.forName(
                    "example.app.App", true, loader);
            app.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);

            try (InputStream resource = loader.getResourceAsStream(
                    "config/flag.txt")) {
                if (resource == null) {
                    throw new IllegalStateException("Resource not found");
                }
                System.out.print("resource: " + new String(
                        resource.readAllBytes(), StandardCharsets.UTF_8));
            }
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac -encoding UTF-8 CompileTwiceDemo.java
java CompileTwiceDemo
~~~

**Stdout dự kiến chính xác trên JDK 17+ trong môi trường bình thường:**

~~~text
pass 1: true
pass 2: true
class files: true
compiled in pass 1
resource: managed-resource
~~~

Thư mục tạm có tên khác nhau ở mỗi lần chạy nên ví dụ **không in đường dẫn tạm** để giữ output ổn định. Các diagnostics nếu có được in ra **stderr**, tách biệt stdout. Sau thí nghiệm, thư mục tạm vẫn tồn tại; ứng dụng thật nên có chính sách dọn các output tạm có chủ đích khi không còn cần.

### Vì sao ví dụ này chứng minh nhiều lượt biên dịch?

Lượt đầu tạo:

~~~text
classes/example/lib/Messages.class
~~~

Lượt sau dùng output ấy như compile dependency bằng `setLocationFromPaths(CLASS_PATH, List.of(classes))`, rồi tạo:

~~~text
classes/example/app/App.class
~~~

Không cần gọi `javac` từ shell cho từng file con. Cả hai task được tạo từ **một** `JavaCompiler` và dùng **cùng một** `StandardJavaFileManager`, nhưng là **hai đối tượng `CompilationTask` riêng**.

`manager.flush()` giúp file manager giải phóng/đẩy các buffer hoặc cache tùy implementation trước khi cấu hình tiếp. Dù vậy, nguyên nhân chính để lượt 2 tìm được `Messages` là: class file từ lượt 1 đã được ghi và `classes` đã được thêm vào `CLASS_PATH`. `flush()` **không thay thế** việc đặt đúng classpath.

### Vì sao cần một class loader riêng để chạy?

`JavaCompiler` tạo file `.class` nhưng không tự nạp những class đó vào class loader của ứng dụng hiện tại. `URLClassLoader` với URL `classes` và parent `ClassLoader.getPlatformClassLoader()` cho phép ví dụ kiểm tra đúng output vừa tạo, tránh phụ thuộc vào class cùng tên có thể đã tồn tại trên application classpath bên ngoài.

Reflection gọi `main(String[])` bằng `invoke(null, (Object) new String[0])`: cast `(Object)` giữ mảng chuỗi là **một đối số** của lời gọi phản chiếu. `URLClassLoader` được đóng bằng `try-with-resources` khi hoàn tất.

## 5. Quản lý tài nguyên: stream, writer, file manager và class loader

Các đối tượng tham gia compile thường sở hữu I/O resources:

| Đối tượng | Cần quản lý ra sao? |
| --- | --- |
| `JavaFileObject.openInputStream()/openReader()` | Đóng stream/reader sau khi đọc |
| `JavaFileObject.openOutputStream()/openWriter()` | Đóng stream/writer sau khi ghi để nội dung hoàn chỉnh |
| `FileObject.openOutputStream()/openWriter()` | Đóng tài nguyên output/resource |
| `StandardJavaFileManager` | `flush()` giữa các tác vụ khi cần, `close()` khi không còn dùng |
| `URLClassLoader` tự tạo | Đóng để giải phóng file/JAR handle khi không còn cần |
| `DiagnosticCollector` | Không cần close; nhưng tạo collector mới cho từng task để giữ lỗi riêng |
| `CompilationTask` | Không có vòng đời kiểu “reset task”; tạo task mới cho lượt biên dịch mới |

**`flush()` và `close()` khác nhau:**

- `flush()` thực hiện việc đẩy/giải phóng những tài nguyên tạm mà file manager có thể xử lý, nhằm giúp các thao tác kế tiếp thấy trạng thái phù hợp. Nó **không xóa output**, không thiết lập lại mọi location, không tự quét source đã thay đổi.
- `close()` kết thúc việc sử dụng file manager, giải phóng tài nguyên do manager nắm giữ. Sau khi đóng, không nên tiếp tục dùng manager cho các task mới; tạo file manager mới nếu cần một session compile khác.
- Đóng file manager không tự đóng mọi class loader khác do ứng dụng đã tạo; chúng có vòng đời riêng.
- Nếu build tool hoặc processor tạo resource, đảm bảo output stream đóng **trước** khi công cụ đóng gói JAR đọc file đó.

Trên Windows, giữ mở JAR handle có thể khiến thay thế/xóa JAR không thành công. Vì vậy việc đóng file manager và class loader ở ranh giới phù hợp rất quan trọng trong ứng dụng chạy lâu như IDE hoặc server build.

## 6. Nhiều task: tái sử dụng manager, không tái sử dụng task

**Đúng:**

~~~java
JavaCompiler.CompilationTask first = compiler.getTask(
        null, manager, firstDiagnostics, options, null, firstSources);
boolean firstOk = Boolean.TRUE.equals(first.call());

JavaCompiler.CompilationTask second = compiler.getTask(
        null, manager, secondDiagnostics, options, null, secondSources);
boolean secondOk = Boolean.TRUE.equals(second.call());
~~~

Đây là **fragment** trong một method có sẵn compiler, manager, diagnostics, options và danh sách source. Nếu lượt 2 phụ thuộc output lượt 1, phải bảo đảm manager đã nhìn thấy class output qua `CLASS_PATH` như ví dụ trước.

**Sai ý tưởng:**

~~~java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, sources);
task.call();
task.call(); // Không phải cách thực hiện lần biên dịch tiếp theo.
~~~

Một compilation task chỉ có thể gọi `call()` một lần theo hợp đồng API `JavaCompiler.CompilationTask` (kế thừa `Callable<Boolean>` với ràng buộc đặc thù). Với lượt compile mới, khởi tạo **task mới**. `StandardJavaFileManager` được thiết kế để có thể tái sử dụng trong **các compilation tuần tự**, giúp tận dụng việc đọc file/JAR của manager.

Không gọi nhiều `CompilationTask.call()` đồng thời trên cùng một `StandardJavaFileManager` khi không có hợp đồng thread-safety rõ ràng. Nếu chạy build parallel, dùng file managers/compiler contexts riêng và phân tách output locations, tránh cùng ghi một `.class` hoặc resource.

### DiagnosticCollector nên tạo mới

Collector có thể giữ diagnostics từ task đã hoàn thành:

~~~java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
~~~

Khi biên dịch nhiều lượt, tạo collector mới giúp phân biệt lỗi nào xảy ra ở lượt 1 hoặc lượt 2, kể cả khi cùng tên file được compile lại. Đừng gộp nhiều cảnh báo và dựa vào số thứ tự mà không biết chúng thuộc compilation task nào.

## 7. Khi source thay đổi giữa hai lần compile

Một yêu cầu thường gặp của IDE là **biên dịch lại cùng một source sau khi người dùng sửa**. Ví dụ:

~~~text
pass 1:
  Source A.java -> A.class

người dùng sửa A.java

pass 2:
  Source A.java -> A.class mới
~~~

Với API, bạn tạo một `CompilationTask` mới sau khi thay nội dung source. Tùy file manager, cần bảo đảm mọi stream đã đóng, sử dụng `flush()` hoặc tạo file manager mới khi muốn ranh giới cache rõ ràng. Tuy nhiên có ba vấn đề độc lập:

1. **Output cũ có thể còn tồn tại**: compiler không tự xóa tất cả `.class` không còn hợp lệ khi xóa/đổi tên source.
2. **Các class phụ thuộc có thể cần compile lại**: JavaCompiler API không phải một hệ thống incremental build hoàn chỉnh. Nó không tự lập đồ thị dependency và xác định tất cả source cần rebuild.
3. **JVM đã tải class cũ**: nếu một class loader đã định nghĩa `A`, chỉ ghi lại `A.class` trên disk không làm class đang chạy tự trở thành phiên bản mới.

Trong hệ thống build thực, cần thuật toán quyết định compilation units, quản lý stale artifacts và chiến lược class loading phù hợp. `StandardJavaFileManager` giúp đọc/ghi file, **không cung cấp toàn bộ cache invalidation và dependency tracking** của Gradle, Maven hay IDE.

### Recompile và ClassLoader

Ví dụ biến đổi source có method mới, compile lại để xuất `A.class` vào cùng thư mục. Một class loader đã nạp `A` vẫn tham chiếu định nghĩa cũ; để quan sát class mới trong một thí nghiệm đơn giản, hãy dùng **class loader mới với ranh giới ủy quyền thích hợp**, rồi đóng loader cũ khi an toàn. Nếu object cũ từ loader A tương tác với class từ loader B, danh tính type khác nhau có thể dẫn đến vấn đề cast/linkage.

Không giải quyết reload bằng cách cố gọi `Class.forName(...)` lặp lại với cùng loader và mong JVM bỏ class đã được định nghĩa.

## 8. Cấu hình nhiều đường tìm kiếm một cách rõ ràng

Khi có dependency JAR:

~~~java
Path output = Path.of("build/classes");
Path library = Path.of("libs/example-lib.jar");

manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(output)
);

manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(output, library)
);
~~~

Đây là **fragment**. Paths phải tồn tại hoặc phù hợp với yêu cầu location/file manager. Thư mục `output` là root của các package class vừa compile hoặc sẽ compile; `library` là một JAR dependency cụ thể.

API `setLocationFromPaths` hữu ích vì không phải tự nối classpath string bằng `;` trên Windows và `:` trên Linux. Cấu trúc `List<Path>` cung cấp từng entry rõ ràng. Nếu ứng dụng cũng xây lệnh `java -cp` thủ công, khi đó vẫn phải dùng ký hiệu tách entry theo nền tảng.

### Classpath không phải processor path

- `CLASS_PATH` dùng để phân giải các class/kiểu mà source cần trong compilation, gồm các dependency Java.
- `ANNOTATION_PROCESSOR_PATH` là đường tìm processor để **chạy trong compile** nếu cấu hình annotation processing.
- `SOURCE_PATH` là đường tìm source dependency bổ sung.
- `MODULE_PATH` dùng cho các named modules JPMS; nó không phải synonym của `CLASS_PATH`.
- `CLASS_OUTPUT` là nơi xuất bytecode; tự đặt một `CLASS_OUTPUT` **không có nghĩa** đó luôn là input classpath ở lần compile sau. Nếu lượt sau cần class đã xuất, hãy cấu hình classpath rõ ràng.

Nếu bạn chạy trên JDK mới nhưng cần target Java 17, đặt `--release 17` để compiler phối hợp source level, target bytecode và API nền tảng tương ứng. Tuy vậy `--release` không tự kiểm tra mọi thư viện bên thứ ba trong classpath có khả năng chạy trên Java 17 hay không.

## 9. Diagnostic và xử lý lỗi từng lần compile

`JavaCompiler.getTask(...)` nhận một `DiagnosticListener<? super JavaFileObject>`. Với `DiagnosticCollector<JavaFileObject>`, sau `call()` có thể xem:

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    System.out.println(
            diagnostic.getKind() + ": "
                    + diagnostic.getMessage(Locale.ROOT)
    );
}
~~~

Đây là **fragment** dùng collector và `Locale` đã có trong method. Diagnostic có thể chứa:
- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`...
- `getSource()`: `JavaFileObject` liên quan (nếu có).
- `getLineNumber()`, `getColumnNumber()`: vị trí, có thể là `Diagnostic.NOPOS` nếu không xác định.
- `getCode()` và `getMessage(locale)`: mã và thông điệp compiler.

Khi `task.call()` trả `false`, không nên chạy ngay class output như một kết quả build chắc chắn hợp lệ: compiler có thể để lại output một phần hoặc output cũ từ lần trước. Dùng thư mục output tách theo compilation hoặc xây trong staging directory rồi chỉ thay artifact chính sau khi build thành công nếu cần tính nguyên tử ở mức artifact.

### Ví dụ báo lỗi được khoanh vùng

Nguồn `Broken.java`:

~~~java
public class Broken {
    public static void main(String[] args) {
        UnknownType value = null;
    }
}
~~~

Đây là **source cố ý không biên dịch**. `JavaCompiler` sẽ báo không tìm được kiểu `UnknownType` nếu không có khai báo phù hợp. Collector của task đang compile `Broken.java` cần giữ lỗi ấy, không bị gộp với thông báo của task sau. Vị trí và câu chữ diagnostic phụ thuộc trình biên dịch/JDK; không nên hardcode một nguyên văn stderr duy nhất cho mọi môi trường.

## 10. JavaFileObject, FileObject và file manager tùy biến

`StandardJavaFileManager` làm việc với các file trên disk. Một IDE hoặc service compile từ mã nguồn người dùng nhập vào editor có thể không muốn tạo `.java` trên disk trước. Khi đó có thể tạo **in-memory `JavaFileObject`**.

Ví dụ **fragment** triển khai object cho source:

~~~java
import java.net.URI;
import javax.tools.SimpleJavaFileObject;

final class StringSource extends SimpleJavaFileObject {
    private final String source;

    StringSource(String className, String source) {
        super(
                URI.create(
                        "string:///"
                                + className.replace('.', '/')
                                + Kind.SOURCE.extension
                ),
                Kind.SOURCE
        );
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

Đây là một **top-level helper class**, không có `main`. Có thể đưa object `new StringSource("demo.Hello", "package demo; public class Hello {}")` vào `compilationUnits` của `compiler.getTask(...)` để cung cấp source không dựa vào file vật lý.

Nhưng **source input trong memory chưa có nghĩa class output cũng ở memory**. Nếu vẫn dùng `StandardJavaFileManager` bình thường, output thường được ghi theo `CLASS_OUTPUT`. Muốn giữ `.class` hoàn toàn trong RAM, cần một file manager tùy biến, thường kế thừa `ForwardingJavaFileManager<StandardJavaFileManager>`, override các phương thức nhận output class (như `getJavaFileForOutput` theo hợp đồng compiler) và cung cấp `JavaFileObject` ghi byte vào buffer.

Thiết kế memory manager phải lo:
- Mapping binary name ↔ `JavaFileObject`.
- Đầu ra của annotation processor và resource qua `getFileForOutput`/`Filer` khi cần.
- Đường tìm dependency và source.
- Closing/flush của stream, đồng bộ dữ liệu giữa các lượt.
- Chuyển byte array thành class có thể nạp qua class loader hợp lệ.
- Isolation, kích thước file và giới hạn bộ nhớ.

Đừng thay mọi thành phần `JavaFileManager` bằng stub đơn giản khi muốn biên dịch code thật: JDK modules, classpath lookup và JavaFileObject kinds vẫn phải được xử lý theo hợp đồng của compiler. `ForwardingJavaFileManager` giúp tái sử dụng behavior chuẩn ở những phương thức không cần override.

## 11. Tài nguyên không phải file .class: đọc, ghi, đóng gói

Ngoài `.java` và `.class`, compiler hoặc annotation processor có thể tạo **resource** như:

~~~text
META-INF/services/com.example.spi.Plugin
config/feature.properties
META-INF/app/index.txt
~~~

`JavaFileManager.getFileForOutput(...)` là một cơ chế ở cấp file manager để mở tài nguyên đầu ra. Ví dụ trong `CompileTwiceDemo`:

~~~java
FileObject file = manager.getFileForOutput(
        StandardLocation.CLASS_OUTPUT,
        "",
        "config/flag.txt",
        null
);
try (OutputStream output = file.openOutputStream()) {
    output.write("managed-resource\n".getBytes(
            StandardCharsets.UTF_8));
}
~~~

Đây là **fragment trích từ ví dụ runnable**, đặt trong method có manager, và output được cấu hình. `location=CLASS_OUTPUT` khiến resource nằm trong cây class output; `pkg=""` nghĩa là tương đối từ gốc location; `relativeName="config/flag.txt"` là đường dẫn bên trong location.

Chú ý với annotation processor: nên dùng **`ProcessingEnvironment.getFiler().createResource(...)`** để tạo resource mới, vì `Filer` quản lý ownership/output và phát hiện trùng trong processing run. File manager ở tầng compiler I/O; Filer ở tầng chuẩn annotation processing. Không lấy `FileManager.getFileForOutput` làm cách né quy tắc `FilerException`.

### Đóng gói resource vào JAR

Nếu output dưới `build/classes` gồm:

~~~text
build/classes/
├── example/app/App.class
└── config/flag.txt
~~~

Có thể đóng cả cây output vào JAR:

~~~bash
jar --create --file build/app.jar -C build/classes .
jar --list --file build/app.jar
~~~

Các lệnh là **ví dụ**, chỉ chạy khi đã có cấu trúc `build/classes` phù hợp. Resource `config/flag.txt` cần được đóng cùng JAR nếu ứng dụng runtime muốn đọc nó qua `ClassLoader.getResourceAsStream("config/flag.txt")`. Nếu resource nằm ngoài output được đóng gói, runtime sẽ không tự tìm được.

Với nhiều JAR cùng chứa resource tên giống nhau, `getResource(...)` có thể trả một URL phù hợp, còn `getResources(...)` có thể liệt kê nhiều URL theo loader; không giả định Java luôn hợp nhất nội dung resource. Một số metadata như `META-INF/services` có cơ chế tiêu thụ riêng bởi `ServiceLoader`.

## 12. Khi dùng annotation processor và các lượt sinh source

Trong một compilation task có annotation processing, processor có thể tạo source mới bằng `Filer.createSourceFile(...)`, khiến `javac` thực hiện thêm processing rounds. Đây là **rounds bên trong một task**, khác với việc ứng dụng chủ động gọi **hai lần `compiler.getTask(...)`**.

~~~text
Ứng dụng host
  |
  +-- CompilationTask #1
  |      round 1 -> processor tạo Generated.java
  |      round 2 -> compiler/processor thấy source mới
  |      round cuối -> hoàn tất .class
  |
  +-- CompilationTask #2 (một getTask mới)
         nguồn input khác, file manager có thể dùng lại
~~~

Phân biệt:

- **Processing round** là vòng trong **một lần biên dịch** khi annotation processor xử lý annotated elements.
- **Compilation task** là đơn vị mà host gọi qua `JavaCompiler.getTask(...).call()`.
- **Source output** và **class output** cần được cấu hình phù hợp với build pipeline.
- Mỗi processor instance có state theo processing environment/compilation tương ứng, không tự chia sẻ an toàn giữa các task khác nhau.

Cấu hình file manager dùng cùng cách đặt locations cho compiler và processor, nhưng khi processor cần sinh file thì API chuẩn là `Filer`. Nếu task sau cần dùng code được task trước sinh, hãy bảo đảm output class/source thực sự đã tồn tại và nằm trên đường tìm kiếm của task sau.

## 13. Caching, stale output và trách nhiệm của hệ thống build

File manager chuẩn có thể cache thông tin file/JAR để tiết kiệm công việc, nhưng **nó không phải incremental compiler hoàn chỉnh**.

Nếu host tạo nhiều task trên cùng output:
- File `A.class` cũ có thể còn lại khi source `A.java` đã bị xóa.
- Một dependency có thể đã đổi binary API, khiến class đã compile ở lượt trước không còn tương thích.
- Một task thất bại có thể để lại output không đủ để chạy nhưng vẫn còn class cũ.
- Một resource generated ở vòng trước có thể trở thành dữ liệu stale nếu build không dọn đúng.
- Cache của custom file manager có thể tiếp tục trả nội dung cũ dù file trên disk đã thay đổi.

Các phương án thực hành:

1. Đặt output riêng theo version/build hoặc build trong thư mục staging và chỉ publish artifact sau khi mọi task thành công.
2. Làm sạch output khi chạy clean build; ở incremental build cần theo dõi input → output để dọn đúng file bị xóa/đổi tên.
3. Khi dependency thay đổi, xác định các source phụ thuộc cần compile lại, không chỉ compile chính file đã sửa.
4. Dùng `flush()` hoặc tạo file manager mới khi cần cắt ranh giới cache; **đừng** xem `flush()` là một thao tác thay thế dependency graph.
5. Tạo class loader mới khi cần chạy bytecode mới; không giả định loader cũ tự nạp lại định nghĩa class.
6. Nếu build nhiều task song song, tách output để tránh race write vào cùng file/resource.

### Đảm bảo “task 2 dùng output task 1” thực sự đúng

Trước task 2, kiểm tra:
- Task 1 trả thành công.
- `Messages.class` đã có tại `classes/example/lib/Messages.class`.
- File manager của task 2 có `CLASS_PATH` chứa đúng `classes`.
- Task 2 sử dụng class/module API tương thích với target release.
- Runtime classpath chứa **cả** `App.class` và `Messages.class`.

Đó là các điều kiện khác nhau. Có output đúng nhưng classpath sai vẫn gây `cannot find symbol` lúc compile; compile thành công nhưng runtime classpath thiếu dependency vẫn có thể gây `NoClassDefFoundError` lúc chạy.

## 14. Lỗi thường gặp khi làm việc với file manager

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime không có compiler tool/module thích hợp | Dùng JDK có `jdk.compiler`, kiểm tra runtime image |
| `task.call()` trả `false` | Lỗi source, classpath, module path, options | Thu diagnostics riêng của task |
| Lượt 2 báo `cannot find symbol` cho kiểu từ lượt 1 | Chưa đưa output cũ vào `CLASS_PATH`, output sai root, task 1 thất bại | Xem `.class`, `CLASS_OUTPUT` và `CLASS_PATH` |
| `getJavaFileObjectsFromPaths` không tìm được source | Path nguồn sai, file chưa tạo, working directory khác | Kiểm tra `Files.exists(source)` và đường tuyệt đối |
| Resource tạo được nhưng runtime trả `null` | Ghi sai location/path, thiếu resource trong JAR/classpath | Kiểm tra `CLASS_OUTPUT`, dùng `jar --list` |
| `IOException`/file locked khi build lại | Writer/stream/manager/class loader còn mở | Dùng try-with-resources, đóng đúng thứ tự |
| Output không cập nhật dù source đổi | Cache custom manager, task không lấy input mới, stale output | Tạo task mới, flush/tách session, kiểm tra input |
| Lượt sau lặp lỗi lượt trước trong log | Tái sử dụng collector hoặc gộp diagnostics không gắn task | Collector mới cho mỗi lượt |
| `IllegalStateException` khi gọi task | Task đã thực thi/được dùng sai lifecycle | Tạo `CompilationTask` mới, không gọi lại `call()` |
| Biên dịch đúng nhưng chạy class cũ | Class loader hiện tại đã định nghĩa class cũ | Tạo loader riêng khi cần reload; quản lý type identity |
| Java code sinh thêm source nhưng không có class | Dùng `-proc:only` hoặc pipeline chưa compile generated source | Kiểm tra annotation processing rounds, `-s`, `-d` |
| Runtime thiếu dependency đã có lúc compile | Runtime classpath khác compile classpath | So sánh đường tìm class ở hai giai đoạn |
| Compile dùng nhầm encoding | File manager và compiler option không đồng nhất | Chọn UTF-8 rõ ràng cho source/resource |
| Dùng memory JavaFileObject nhưng output vẫn trên disk | Chỉ tùy biến input, chưa tùy biến output manager | Cần forwarding/custom manager cho class output |
| Build song song làm hỏng file output | Task cùng ghi file trên một location, manager không có cam kết thread-safety | Tách manager/output và đồng bộ ở host |

## 15. Checklist thiết kế API compile bền vững

1. **Chọn compiler:** kiểm tra `ToolProvider.getSystemJavaCompiler()` và JDK target.
2. **Chuẩn bị source:** phân biệt source file trên disk và `JavaFileObject` trong memory.
3. **Chọn encoding:** nhất quán UTF-8 cho source và resource.
4. **Cấu hình location:** đặt output, classpath, source path, processor path/module path nếu cần; tránh cấu hình mâu thuẫn.
5. **Tạo task:** một `getTask(...)` cho một compilation, options và diagnostics riêng.
6. **Kiểm tra kết quả:** dùng `Boolean.TRUE.equals(task.call())`, đọc diagnostics, không chạy kết quả khi task thất bại.
7. **Giữa các task:** bảo đảm các stream đã đóng, quản lý cache/flush, đưa output của task trước vào classpath khi cần.
8. **Sau task:** xác minh class files/resources đầu ra, dọn stale output nếu đây là trách nhiệm của host.
9. **Khi chạy generated bytecode:** tạo loader thích hợp và chú ý class identity, nạp class từ đúng output.
10. **Đóng tài nguyên:** `try-with-resources` cho file manager, stream, writer và custom URLClassLoader.
11. **Đóng gói:** xác minh những gì xuất hiện trong JAR, bao gồm resources và dependency runtime.
12. **Ở hệ thống chạy lâu:** kiểm soát bộ nhớ, temp directory, log diagnostics, isolation/security và concurrency theo chính sách của ứng dụng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Sau task 1, có `classes/example/lib/Messages.class`. Vì sao task 2 không nhất thiết tự tìm được `Messages` chỉ vì dùng cùng `CLASS_OUTPUT`?

**Đáp án:** `CLASS_OUTPUT` là nơi ghi; muốn dùng một class đã có làm dependency, cần bảo đảm nó nằm trên đường tra class thích hợp của task 2, ví dụ đặt `CLASS_PATH` chứa `classes`.

**Câu 2.** Có được dùng cùng `CompilationTask` và gọi `call()` hai lần để compile hai nhóm source không?

**Đáp án:** Không. Tạo một task mới cho lượt biên dịch mới. `StandardJavaFileManager` có thể tái sử dụng cho các compilation tuần tự.

**Câu 3.** Tại sao đóng `StandardJavaFileManager` sau build là quan trọng?

**Đáp án:** Manager có thể giữ file/JAR handles và tài nguyên I/O. Đóng manager giúp giải phóng chúng và đặt ranh giới sử dụng rõ ràng.

**Câu 4.** `manager.flush()` có xóa tất cả `.class` cũ và recompile mọi source phụ thuộc không?

**Đáp án:** Không. `flush()` là thao tác quản lý file manager, không phải clean build, dependency analysis hay class-loader reload.

**Câu 5.** Processor muốn tạo resource `META-INF/app/index.txt` trong runtime artifact. Nên làm gì?

**Đáp án:** Trong annotation processor dùng `Filer.createResource(CLASS_OUTPUT, "", "META-INF/app/index.txt", origins...)`; đóng stream và xác minh resource được gói vào JAR. Khi viết công cụ ở tầng compiler I/O, có thể làm việc qua `JavaFileManager.getFileForOutput` với location tương ứng.

**Câu 6.** Có hai task chạy song song cùng một manager và ghi cùng `CLASS_OUTPUT`. Có nên mặc định an toàn không?

**Đáp án:** Không. Không mặc định file manager chuẩn thread-safe cho các thao tác compile đồng thời, và cạnh tranh ghi file có thể làm output không nhất quán. Dùng session/output tách biệt hoặc điều phối đồng bộ phù hợp.

**Câu 7.** Vì sao sửa `App.class` trên disk không khiến `Class.forName("example.app.App")` từ cùng loader trả định nghĩa mới?

**Đáp án:** Class được định nghĩa theo binary name + defining loader; loader đã có thể giữ định nghĩa cũ. Cần một cơ chế reload hợp lệ/loader mới chứ không chỉ ghi file lại.

**Câu 8.** Chỉ tạo `StringSource` trong memory có bảo đảm mọi class output cũng ở memory không?

**Đáp án:** Không. Input JavaFileObject và output file manager là hai việc riêng. Muốn bytecode output trong RAM cần xử lý `getJavaFileForOutput`/stream output bằng manager tùy biến.

## Ghi nhớ

- **`JavaCompiler` tạo task; `StandardJavaFileManager` quản lý I/O và locations; `CompilationTask` chỉ chạy một lần.**
- Có thể tái sử dụng một file manager cho **nhiều task tuần tự**, nhưng cần quản lý classpath, buffer/cache, diagnostics và vòng đời close.
- **`CLASS_OUTPUT` khác `CLASS_PATH`**: output từ lượt trước muốn được lượt sau sử dụng thì phải nằm trên đường tra class của lượt sau.
- Resource trong `CLASS_OUTPUT` có thể được đóng vào JAR cùng `.class`; annotation processor nên sinh resource qua **`Filer`**.
- Compile thành công **không** tự nạp class mới, cập nhật loader cũ, xóa file stale hoặc kiểm chứng runtime dependencies.
- Xây công cụ compile đáng tin cần **đường dẫn rõ ràng, đóng mọi stream/manager, task mới mỗi lượt và kiểm tra bytecode/resource cuối cùng**.
