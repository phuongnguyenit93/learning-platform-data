# Cấu hình annotation processor và mô-đun cho tác vụ JavaCompiler API

## 1. Bài toán: biên dịch từ chương trình Java thay vì chạy lệnh javac

Một ứng dụng IDE, code generator, test harness hoặc build tool đôi khi cần tự khởi tạo một lần biên dịch Java, thay vì gọi `javac` qua terminal. Java cung cấp **Java Compiler API (JSR 199)** trong module `java.compiler`:

- `javax.tools.JavaCompiler`: tạo compilation task;
- `javax.tools.JavaCompiler.CompilationTask`: cấu hình và khởi chạy task;
- `javax.tools.StandardJavaFileManager` và `JavaFileManager.Location`: xác định file nguồn, output, classpath và module locations;
- `javax.tools.DiagnosticCollector`: nhận lỗi/cảnh báo theo cấu trúc;
- `javax.annotation.processing.Processor` (JSR 269): xử lý annotations khi compilation task hoạt động.

Tác vụ có thể vừa biên dịch **named modules** theo Java Platform Module System (JPMS), vừa chạy **annotation processors** để kiểm tra hoặc sinh mã. Hai chức năng này liên quan nhưng không được lẫn:

- **Module của ứng dụng đang được biên dịch** là những modules chứa source/classes mà compiler cần phân tích. Chúng dùng `MODULE_SOURCE_PATH`, `MODULE_PATH` và `module-info.java`.
- **Module chứa processor** là nơi có implementation `Processor` cùng các thư viện mà processor cần để **thực thi trong môi trường compiler**. Nó có thể được nạp từ `ANNOTATION_PROCESSOR_MODULE_PATH` với JPMS service provider, hoặc processor có thể nằm trên `ANNOTATION_PROCESSOR_PATH` như classpath thông thường.
- **Tác vụ API** có thể bỏ qua processor discovery và đưa **object instance** trực tiếp bằng `task.setProcessors(...)`. Khi đó cần tự quản lý cách nạp/khởi tạo processor; processor path không tự làm việc này thay cho ứng dụng gọi API.

Mục tiêu học tập: tạo task từ `ToolProvider.getSystemJavaCompiler()`, cấu hình processor theo hai cách, đặt đúng module source path, module path và output, xử lý diagnostics, và tránh nhầm runtime environment với compilation environment.

## 2. Các lớp và sự kiện của một compilation task

Quy trình điển hình:

```text
ToolProvider.getSystemJavaCompiler()
                 |
                 v
JavaCompiler + StandardJavaFileManager
                 |
      +----------+-----------+
      |                      |
Source units + options    Locations
      |                CLASS_OUTPUT / SOURCE_OUTPUT
      |                CLASS_PATH / MODULE_PATH
      |                MODULE_SOURCE_PATH
      |                ANNOTATION_PROCESSOR_PATH
      |                ANNOTATION_PROCESSOR_MODULE_PATH
      +----------+-----------+
                 |
                 v
JavaCompiler.getTask(...)
                 |
         CompilationTask
                 |
      setProcessors(...)   (nếu dùng instance)
      addModules(...)      (nếu cần root modules)
      setLocale(...)       (nếu cần)
                 |
               call()
                 |
          diagnostics + output
```

Những nguyên tắc quan trọng:

1. `ToolProvider.getSystemJavaCompiler()` cần một runtime có system compiler (thường là **JDK**). Nếu chạy bằng một runtime image không có `jdk.compiler`, API có thể trả `null`; kiểm tra trước khi sử dụng.
2. `compiler.getTask(...)` **tạo** task, chưa thực thi. `task.call()` mới khởi động compilation.
3. `CompilationTask.setProcessors(...)` và `addModules(...)` phải được gọi **trước** `call()`.
4. Một `CompilationTask` chỉ được gọi `call()` **một lần**. Muốn compile thêm một nhóm nguồn, hãy tạo task khác; standard file manager có thể tái sử dụng cho những task tuần tự nếu được quản lý đúng.
5. `call()` trả về `Boolean` thành công/thất bại theo hợp đồng API; lỗi từ các thành phần do caller cung cấp có thể còn phát sinh exception, vì vậy không coi mọi exception là một diagnostic Java source bình thường.
6. `StandardJavaFileManager` là resource cần đóng bằng try-with-resources; không đóng nó giữa lúc task chưa xong.
7. Một nguồn generated bằng `Filer` có thể được đưa vào round sau và biên dịch trong cùng task, miễn là processor được bật và không có lỗi cản trở.

**Không lẫn JSR 199 với JSR 269:** JSR 199 điều khiển compiler/task/file manager, còn JSR 269 cho processor xem mô hình ngôn ngữ và tạo file. Một chương trình có thể dùng JavaCompiler API mà không dùng processor; processor cũng có thể chạy khi người dùng gọi `javac` trực tiếp.

## 3. Phân biệt sáu đường dẫn thường bị nhầm

`StandardLocation` (trong `javax.tools`) cung cấp các vị trí chuẩn. Những tên sau đặc biệt quan trọng:

| Location trong file manager | Tùy chọn javac tương đương về ý tưởng | Mục đích |
| --- | --- | --- |
| `CLASS_OUTPUT` | `-d` | Đầu ra `.class` từ compilation |
| `SOURCE_OUTPUT` | `-s` | Đầu ra `.java` do processors tạo |
| `CLASS_PATH` | `--class-path` / `-cp` | Binary dependencies của source được compile trong classpath mode |
| `SOURCE_PATH` | `--source-path` | Source dependencies có thể được tìm ngầm |
| `MODULE_PATH` | `--module-path` | **Các module đã compile** mà ứng dụng cần đọc |
| `MODULE_SOURCE_PATH` | `--module-source-path` | **Các module có source** đang được compiler tìm/compile |
| `ANNOTATION_PROCESSOR_PATH` | `--processor-path` / `-processorpath` | Processor classes/JAR và dependencies trên processor classpath |
| `ANNOTATION_PROCESSOR_MODULE_PATH` | `--processor-module-path` | **Named modules chứa processors** và các module processor liên quan |

Hãy nhớ ba câu hỏi độc lập:

- “Compiler cần đọc **mã ứng dụng** ở đâu?” → source path, module source path, classpath, module path.
- “Processor được **nạp để thực thi** từ đâu?” → processor classpath/module path hoặc object instance tự cung cấp.
- “Nguồn và class mới phải **ghi** ở đâu?” → source output và class output.

Không đặt JAR processor vào `MODULE_PATH` của ứng dụng rồi mong nó được discover. `MODULE_PATH` dành cho các modules mà **mã ứng dụng** được compile cần tìm; `ANNOTATION_PROCESSOR_MODULE_PATH` dùng để tìm các **named modules cung cấp Processor**. Tương tự, `CLASS_OUTPUT` không tự động trở thành `CLASS_PATH` cho một lần compile khác.

**Cấu hình bằng file manager hoặc bằng options:** với standard file manager, có thể dùng `setLocationFromPaths(...)`. Cũng có thể truyền javac options trong `compiler.getTask`. Nên chọn một cách nhất quán cho cùng location để tránh mơ hồ, vì option và file-manager state đều tham gia xác định môi trường compilation.

## 4. Cấu hình bằng StandardJavaFileManager

Với một dự án có thư mục thật trên đĩa:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("JDK compiler unavailable");
}

try (StandardJavaFileManager files =
         compiler.getStandardFileManager(null, null, null)) {

    files.setLocationFromPaths(
            StandardLocation.CLASS_OUTPUT, List.of(classOutput));

    files.setLocationFromPaths(
            StandardLocation.SOURCE_OUTPUT, List.of(generatedSourceOutput));

    files.setLocationFromPaths(
            StandardLocation.CLASS_PATH, List.of(applicationLibDirectory));

    // Tạo compilation units, getTask(...), setProcessors(...), call().
}
```

Đây là **mẫu code minh họa**, giả định `classOutput`, `generatedSourceOutput` và `applicationLibDirectory` đã được khai báo kiểu `Path`, có giá trị phù hợp; chưa phải một chương trình Java độc lập. Những thư mục output phải **tồn tại** trước khi gọi `setLocationFromPaths` của standard file manager, và caller nên kiểm soát rõ trạng thái sạch/cũ của chúng.

Với `StandardLocation.MODULE_SOURCE_PATH`, root thường chứa các thư mục theo tên module. Đừng đặt nó là thư mục chứa một file package đơn lẻ rồi mong compiler tự hiểu bố cục nhiều modules.

**Cẩn trọng với đa module:** `StandardJavaFileManager.setLocationForModule(...)` có thể gắn location riêng cho một named module. Khi gán lại một root cho cùng module-oriented location bằng `setLocationFromPaths(...)`, các association đã đặt riêng cho module có thể bị xóa. Nếu cần kiểm soát modules ở mức sâu, nên nắm rõ hợp đồng `JavaFileManager.Location` và thứ tự các lời gọi cấu hình.

## 5. getTask, options, diagnostics và processors: ý nghĩa từng tham số

Chữ ký phổ biến:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        writer,
        fileManager,
        diagnosticListener,
        options,
        classes,
        compilationUnits);
```

Ý nghĩa:

| Tham số | Chức năng |
| --- | --- |
| `writer` | Nhận output văn bản từ compiler khi có; `null` dùng writer mặc định |
| `fileManager` | Tìm/đọc/ghi `JavaFileObject`; có thể dùng `StandardJavaFileManager` |
| `diagnosticListener` | Nhận diagnostics dạng `Diagnostic<? extends JavaFileObject>` |
| `options` | Các compiler options như `--release`, `-encoding`, `--module-path`; không chứa tên file nguồn ở đây |
| `classes` | Tên lớp được xử lý cho annotation processing trong trường hợp thích hợp, **không** phải nơi chứa `Class<?>` objects; phần lớn ví dụ source compilation truyền `null` |
| `compilationUnits` | `Iterable<? extends JavaFileObject>` đại diện các file `.java` cần compile |

Nhiều người thấy tham số tên `classes` rồi truyền `List<Class<?>>` vào đây: sai kiểu và sai ý nghĩa. Nó nhận **tên lớp** dạng `String` khi dùng cơ chế processing classes được hỗ trợ, còn source inputs thường được cung cấp qua `compilationUnits`.

Để nhận lỗi có cấu trúc:

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

JavaCompiler.CompilationTask task = compiler.getTask(
        null, files, diagnostics,
        List.of("--release", "17", "-encoding", "UTF-8"),
        null, units);

boolean success = Boolean.TRUE.equals(task.call());

for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        System.err.println(d.getKind() + ": " + d.getMessage(null));
    }
}
```

Đây là đoạn code trong method có sẵn `compiler`, `files`, `units`. `getMessage(null)` dùng formatting theo mặc định; câu chữ diagnostics không phải API contract bất biến. Khi cần IDE positioning, đọc thêm `getSource()`, `getLineNumber()`, `getColumnNumber()`. `DiagnosticCollector` không thay việc kiểm tra `task.call()`: một task có thể báo warning nhưng vẫn thành công.

**Các options API không giống command line của Java launcher.** Ví dụ `-J-Xmx...` là cú pháp truyền option JVM khi gọi chương trình `javac` qua command line; khi compiler chạy **trong JVM ứng dụng** bằng JSR 199, hãy cấu hình JVM **chứa ứng dụng** lúc khởi động. Không coi `-J...` là cách đáng tin để thay đổi heap của JVM đã chạy.

## 6. Hai chiến lược cung cấp processor

### 6.1. Cấp object Processor trực tiếp qua setProcessors

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, files, diagnostics, options, null, units);

task.setProcessors(List.of(new MyProcessor()));
boolean ok = Boolean.TRUE.equals(task.call());
```

`MyProcessor` trong đoạn này là **class do ứng dụng gọi API đã load được**, ví dụ class trong code host hoặc dependency của host; nó không cần được discovery từ `ANNOTATION_PROCESSOR_PATH`. `setProcessors(...)` **bỏ qua cơ chế processor discovery mặc định** theo đặc tả `CompilationTask`.

Ưu điểm: chọn chính xác instances/versions, tiện cho chương trình tích hợp, unit tests, IDE và tool có dependency injection.

Điểm cần nhớ: `Processor` vẫn chạy trong **runtime/compiler environment**, không tự nạp dependency ở module path của source đang compile. Host phải tự có khả năng load processor và dependencies của nó; nếu processor đã được instantiate trong ứng dụng, `--processor-module-path` không tự thêm module đó vào classloader của host sau khi JVM khởi động.

Với `setProcessors`, không đồng thời thêm `-processor` chỉ để “chọn lại cùng processor”: đây là hai phương án chọn processor khác nhau; một đường dẫn cấu hình rõ ràng sẽ dễ bảo trì hơn. Đừng dùng `-proc:none` rồi mong processor object vẫn chạy.

### 6.2. Để javac tìm processor từ path/module path

Ví dụ qua options:

```java
List<String> options = List.of(
        "--release", "17",
        "--processor-path", "processor-libs",
        "-processor", "tools.MyProcessor",
        "-s", "build/generated",
        "-d", "build/classes");
```

Đây là **đoạn cấu hình minh họa**, yêu cầu `processor-libs` thực sự chứa `tools.MyProcessor` và dependencies của nó. Một named processor module có thể được tìm trên `--processor-module-path` thông qua service provider metadata của module; đây **không** phải classpath processor thông thường.

Nếu dùng discovery từ classpath, processor JAR thường có service file:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung:

```text
tools.MyProcessor
```

Đối với named module, thay vì chỉ dựa vào resource kiểu service-file, module descriptor khai báo:

```java
module tools.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with tools.MyProcessor;
}
```

Đây là **một `module-info.java` minh họa**, chỉ hợp lệ khi class `tools.MyProcessor` thực sự implement `Processor` và module được biên dịch/đặt trên processor module path đúng cách. `requires java.compiler` cần thiết để processor tham chiếu `javax.annotation.processing` và language model APIs; `provides` cho cơ chế `ServiceLoader` tìm provider. Không cần `exports tools` chỉ để service loader tạo một provider hợp lệ khi các quy tắc provider accessibility được đáp ứng.

**Khác biệt JDK version:** từ JDK 23, compiler không tự chạy processors một cách ngầm chỉ vì có processor tình cờ trên classpath. Dự án sử dụng codegen cần cấu hình tường minh `-processor` hoặc processor path/module path và chế độ processing thích hợp thay vì dựa vào default; kiểm tra behavior theo JDK/toolchain cụ thể.

## 7. Ví dụ runnable: JavaCompiler API gắn processor trực tiếp

Ví dụ sau là **một file Java chạy được trên JDK 17+**, không yêu cầu Maven/Gradle hay JAR ngoài. Nó làm bốn việc:

1. Tạo hai file nguồn tạm: annotation `demo.Generate` và class `demo.App`.
2. Tạo compilation task bằng JavaCompiler API, đặt output locations.
3. Gắn instance processor với `task.setProcessors(List.of(new GenProcessor()))`; processor sinh `demo.GeneratedMessage`.
4. Kiểm tra task thành công, xác nhận generated file tồn tại và nạp/chạy `demo.App` từ class output.

### 7.1. Tạo file CompilerApiDemo.java

```java
import java.io.IOException;
import java.io.Writer;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class CompilerApiDemo {
    @SupportedAnnotationTypes("demo.Generate")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class GenProcessor extends AbstractProcessor {
        @Override
        public boolean process(Set<? extends TypeElement> annotations,
                               RoundEnvironment round) {
            if (round.processingOver()) return true;

            for (TypeElement annotation : annotations) {
                for (Element element
                        : round.getElementsAnnotatedWith(annotation)) {
                    try {
                        JavaFileObject file = processingEnv.getFiler()
                                .createSourceFile("demo.GeneratedMessage", element);
                        try (Writer w = file.openWriter()) {
                            w.write("package demo;\n"
                                    + "public final class GeneratedMessage {\n"
                                    + "  public static String text() { "
                                    + "return \"GENERATED\"; }\n"
                                    + "}\n");
                        }
                    } catch (IOException e) {
                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.ERROR, e.toString(), element);
                    }
                }
            }
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        Path root = Files.createTempDirectory("api-processor-");
        Path src = Files.createDirectories(root.resolve("src/demo"));
        Path classes = Files.createDirectories(root.resolve("classes"));
        Path generated = Files.createDirectories(root.resolve("generated"));
        Path marker = src.resolve("Generate.java");
        Path app = src.resolve("App.java");

        Files.writeString(marker, """
                package demo;
                import java.lang.annotation.*;
                @Target(ElementType.TYPE)
                @Retention(RetentionPolicy.SOURCE)
                public @interface Generate {}
                """);

        Files.writeString(app, """
                package demo;
                @Generate
                public class App {
                    public static void main(String[] args) {
                        System.out.println(GeneratedMessage.text());
                    }
                }
                """);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager files =
                 compiler.getStandardFileManager(diagnostics, null, null)) {

            files.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            files.setLocationFromPaths(
                    StandardLocation.SOURCE_OUTPUT, List.of(generated));

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjectsFromPaths(List.of(marker, app));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-encoding", "UTF-8"),
                    null, units);

            task.setProcessors(List.of(new GenProcessor()));
            success = Boolean.TRUE.equals(task.call());
        }

        System.out.println("compiled=" + success);
        System.out.println("generated=" + Files.isRegularFile(
                generated.resolve("demo/GeneratedMessage.java")));

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                System.err.println(d.getKind() + ": " + d.getMessage(null));
            }
        }

        if (!success) {
            throw new IllegalStateException("Compilation failed");
        }

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { classes.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> appClass = Class.forName("demo.App", true, loader);
            appClass.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);
        }
    }
}
```

### 7.2. Biên dịch và chạy

Tại thư mục chứa file:

```bash
javac --release 17 CompilerApiDemo.java
java CompilerApiDemo
```

**Stdout chính xác khi đã thử bằng OpenJDK 21:**

```text
compiled=true
generated=true
GENERATED
```

Mỗi lần chạy, ví dụ tạo một thư mục tạm mới có tiền tố `api-processor-`. `classes` và `generated` là hai thư mục con của root đó. Chúng được tạo trước `setLocationFromPaths` để tuân theo hợp đồng output location. Ví dụ không chủ động xóa temp folder, giúp người học có thể kiểm tra output khi cần.

**Vì sao có thể gọi `demo.GeneratedMessage` dù ban đầu chưa có file source?** Processor được gắn trực tiếp bằng `setProcessors`, xử lý `@Generate` rồi ghi file với `Filer`. Compiler đưa generated source vào round tiếp và tạo class file. Khi task thành công, `URLClassLoader` mở class output rồi gọi `main` của class đã biên dịch.

**Vì sao dùng `ClassLoader.getPlatformClassLoader()` làm parent?** Để giảm khả năng loader này vô tình lấy một `demo.App` trùng tên từ application classpath của chương trình host; runtime Java platform vẫn khả dụng. Đây là lựa chọn cho ví dụ minh họa, không phải một sandbox bảo mật. Trong ứng dụng thực tế, quản lý classloader isolation và lifecycle của code mới biên dịch thận trọng.

Ví dụ đã dùng `@SupportedSourceVersion(RELEASE_17)` và `--release 17` nhất quán. Trên JDK cũ hơn không hỗ trợ Java text blocks, mã host này không compile; điều kiện của bài là **JDK 17+**.

### 7.3. Những điểm compiler API được thể hiện rõ

- `getSystemJavaCompiler()`: lấy compiler có trong system runtime.
- `getStandardFileManager(...)`: tạo manager đọc/ghi đường dẫn thực.
- `getJavaFileObjectsFromPaths(...)`: biến `Path` thành Java compilation units.
- `getTask(...)`: tập hợp options, diagnostics, manager và units.
- `setProcessors(...)`: cấp processor instance, **bỏ qua service discovery**.
- `call()`: thực sự chạy compiler, processing rounds và code generation.
- `SOURCE_OUTPUT`: nơi `Filer` ghi `GeneratedMessage.java`.
- `CLASS_OUTPUT`: nơi lưu `App.class`, `Generate.class` và `GeneratedMessage.class`.
- `DiagnosticCollector`: lưu diagnostics có cấu trúc, kể cả khi không in ra stdout.
- `URLClassLoader`: bước thực thi **sau compilation**, tách biệt với việc processor chạy trong compiler.

Nếu tắt processing hoặc không gọi `setProcessors` trong ví dụ (và không cấu hình processor discovery thay thế), code `App` sẽ thiếu `GeneratedMessage`, dẫn đến lỗi compile khi không có binary cùng tên từ môi trường khác.

## 8. Cấu hình named modules từ JavaCompiler API

Một module Java tên `demo.app` có thể gồm `module-info.java` và source của nó:

```text
project/
└── src/
    └── demo.app/
        ├── module-info.java
        └── sample/
            └── App.java
```

File `src/demo.app/module-info.java`:

```java
module demo.app {
    exports sample;
}
```

File `src/demo.app/sample/App.java`:

```java
package sample;

public class App {
    public static String name() {
        return "MODULE";
    }
}
```

`module-info.java` là **nguồn của module**, không phải file cấu hình của annotation processor. Ở đây module không cần phụ thuộc ngoài `java.base` nên không có `requires` khác.

### 8.1. Ví dụ runnable của MODULE_SOURCE_PATH

Tạo **ModuleTaskDemo.java** — chương trình host tạo module source tạm rồi yêu cầu JavaCompiler API compile nó:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class ModuleTaskDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("module-task-");
        Path src = Files.createDirectories(root.resolve("src"));
        Path packageDir = Files.createDirectories(
                src.resolve("demo.app/sample"));
        Path moduleInfo = src.resolve("demo.app/module-info.java");
        Path app = packageDir.resolve("App.java");

        Files.writeString(
                moduleInfo, "module demo.app { exports sample; }\n");
        Files.writeString(app,
                "package sample; public class App { "
                + "public static String name() { return \"MODULE\"; } }\n");

        Path output = Files.createDirectories(root.resolve("out"));
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager files =
                 compiler.getStandardFileManager(diagnostics, null, null)) {

            files.setLocationFromPaths(
                    StandardLocation.MODULE_SOURCE_PATH, List.of(src));
            files.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjectsFromPaths(
                            List.of(moduleInfo, app));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17"), null, units);

            success = Boolean.TRUE.equals(task.call());
        }

        System.out.println("compiled=" + success);
        System.out.println("moduleInfo=" + Files.exists(
                output.resolve("demo.app/module-info.class")));
        System.out.println("app=" + Files.exists(
                output.resolve("demo.app/sample/App.class")));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 ModuleTaskDemo.java
java ModuleTaskDemo
```

**Stdout đã kiểm tra trên OpenJDK 21:**

```text
compiled=true
moduleInfo=true
app=true
```

Trong thí nghiệm này, `StandardLocation.MODULE_SOURCE_PATH` trỏ đến root `src`, nơi mỗi thư mục con là một named module. Vì vậy `demo.app` là một module root, không phải package name. Output của compilation là:

```text
out/
└── demo.app/
    ├── module-info.class
    └── sample/
        └── App.class
```

Bạn có thể làm tương đương bằng options:

```java
List<String> options = List.of(
        "--release", "17",
        "--module-source-path", "src",
        "-d", "out");
```

Đây là **mẩu config**, không phải một lời gọi task hoàn chỉnh. Trong ví dụ runnable, ta cấu hình file-manager locations thay cho options `--module-source-path` và `-d`. Không kết hợp cả hai cách để thiết lập cùng một location mà không có lý do rõ ràng.

### 8.2. MODULE_PATH không phải MODULE_SOURCE_PATH

- `MODULE_SOURCE_PATH` cho compiler biết **nơi tìm source module** cần compile.
- `MODULE_PATH` cho compiler biết **nơi tìm module đã biên dịch** dùng làm dependency.
- `CLASS_PATH` dành cho classpath mode và các binary không được dùng như named modules theo đường module.
- `CLASS_OUTPUT` cho compiler biết **nơi sinh modules đã biên dịch**, thường được tổ chức thành `out/<module-name>/...` khi compile nhiều modules.

Nếu `demo.app` có `requires demo.lib;`, module `demo.lib` cần được tìm theo module graph. Có thể cung cấp bản compiled của `demo.lib` trên `MODULE_PATH`, hoặc đưa cả source của `demo.lib` vào tập modules biên dịch từ `MODULE_SOURCE_PATH`. Chỉ khai báo `requires` không khiến compiler tự tải dependency từ Internet.

Trong `StandardJavaFileManager`:

```java
files.setLocationFromPaths(
        StandardLocation.MODULE_PATH, List.of(compiledModulesRoot));
```

Đây là **đoạn code minh họa**, giả định `compiledModulesRoot` là `Path` hợp lệ trỏ đến JAR module, thư mục module, hoặc thư mục chứa modules theo cấu trúc phù hợp, và không nhất thiết là application classpath. Không tự thay `MODULE_PATH` bằng `ANNOTATION_PROCESSOR_MODULE_PATH`: hai nơi phục vụ hai môi trường khác nhau.

## 9. Processor đặt trong named module: cấu hình đúng môi trường

Xét một processor implementation:

```java
package tools;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Generate")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GenerateProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        return true;
    }
}
```

Đây là **processor skeleton để minh họa nạp qua module**, không sinh file; dùng nó để quan sát discovery, không thay thế `GenProcessor` đầy đủ ở mục 7.

Descriptor module processor:

```java
module tools.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with tools.GenerateProcessor;
}
```

Đây là `module-info.java` hợp lệ khi `GenerateProcessor` nằm trong module này và được biên dịch. Khi đóng gói, module có thể nằm dưới một thư mục root kiểu `processor-modules/tools.processor` hoặc dưới dạng module JAR. Compiler có thể tìm processor theo provider declaration thông qua processor module path.

Cấu hình **bằng options** của `getTask` có thể như sau:

```java
List<String> options = List.of(
        "--release", "17",
        "--processor-module-path", "processor-modules",
        "-d", "build/classes",
        "-s", "build/generated");
```

Ở đây `processor-modules` **phải chứa processor module đã biên dịch** và các phụ thuộc module của nó. Chỉ đặt `module-info.java` chưa biên dịch vào đường dẫn này không khiến compiler chạy processor. Với module path processor, service registration qua `provides ... with ...` là hợp đồng quan trọng; classpath service file đơn thuần không thay thế descriptor của named module.

Cấu hình **bằng file-manager location** tương ứng:

```java
files.setLocationFromPaths(
        StandardLocation.ANNOTATION_PROCESSOR_MODULE_PATH,
        List.of(processorModulesRoot));
```

Đây là đoạn code với `files` và `processorModulesRoot` đã tồn tại; không phải một chương trình riêng. Nếu processor là class/JAR thông thường không phải named module, dùng `ANNOTATION_PROCESSOR_PATH`.

**Lưu ý về JDK và discovery:** ý nghĩa mặc định của việc tìm processors có thể thay đổi theo compiler version. Nếu build bắt buộc có generated code, đừng chỉ tin vào sự hiện diện của JAR trên classpath; nên cấu hình processor explicit theo cơ chế phù hợp (setProcessors, -processor hoặc processor module path với provider declaration) và có kiểm thử rằng generated file thực sự xuất hiện.

## 10. Application module và processor module có cần đọc nhau không?

Đây là một trong những nhầm lẫn phổ biến nhất.

Giả sử:

- Module của ứng dụng `shop.app` khai báo `module shop.app { requires shop.api; }`.
- Module `shop.api` cung cấp annotation hoặc types mà ứng dụng sử dụng.
- Module processor `shop.processor` implements `Processor` để sinh classes dựa vào annotation.

Phân biệt quan hệ:

1. `shop.app` cần `requires shop.api;` **nếu** source của nó dùng public types thuộc module đó.
2. `shop.processor` thường cần `requires java.compiler;` để dùng `javax.annotation.processing`, `javax.lang.model` và `javax.tools`.
3. Nếu processor **tham chiếu annotation API bằng class trực tiếp** trong code của chính processor, processor module có thể cần `requires shop.api;` và module `shop.api` phải có mặt trong **processor runtime module graph**.
4. `shop.app` **không mặc nhiên cần** `requires shop.processor;` chỉ để chạy annotation processing. Module processor là build-time tool, không phải dependency runtime của ứng dụng nếu generated code không tham chiếu chính API của processor.
5. Nếu mã được sinh tham chiếu các kiểu khác, ứng dụng cần compile-time và runtime dependencies tương ứng, độc lập với việc processor được load thành công.

**Hai môi trường:** compiler phân tích ứng dụng trong **compilation environment**, còn processor chạy trong runtime/tool environment của compiler. Module graph của ứng dụng và module graph của processor có thể khác nhau; thêm JAR vào một bên không tự xuất hiện bên kia.

Nếu ứng dụng host dùng `setProcessors(new MyProcessor())`, host phải tự load `MyProcessor` trong runtime module graph/classpath của nó; không nhất thiết dùng `--processor-module-path`. Cần quyết định **một chiến lược nạp processor** rõ ràng trước khi triển khai.

## 11. addModules khác với thêm module vào module path

`JavaCompiler.CompilationTask` có API:

```java
task.addModules(List.of("my.optional.module"));
```

Đây là **mẩu code minh họa**, giả định module `my.optional.module` thật sự observable và hợp lệ trong cấu hình. Lệnh này thêm **root modules** vào việc resolve module graph của compilation task. Nó không tạo module, không tải JAR, không thay thế việc cung cấp `MODULE_PATH` và **không phải cách đăng ký processor**.

Đừng nhầm:

- `files.setLocationFromPaths(MODULE_PATH, ...)`: module binaries **đang nằm ở đâu**.
- `task.addModules(...)`: bổ sung **module roots nào** cho resolution.
- `--add-modules`: javac option tương đương ở cấp module resolution khi thích hợp.
- `requires ...;` trong `module-info.java`: khai báo **module dependency** của một named module.
- `provides Processor with ...;` trong module processor: khai báo **service implementation** cho processor discovery.

Trong chương trình JavaCompiler API, gọi `addModules` trước `task.call()`. Nếu task đã khởi động, API có thể ném `IllegalStateException`.

## 12. Khi nào chọn classpath processor, module processor hay instance?

| Bối cảnh | Chiến lược thường hợp lý | Lưu ý |
| --- | --- | --- |
| Test một processor đã có instance trong JVM | `task.setProcessors(List.of(instance))` | Bỏ discovery, host chịu trách nhiệm nạp dependencies |
| CLI/build tool dùng processor JAR classpath | `-processorpath` + `-processor` hoặc service file | Cô lập processor dependencies với app classpath |
| Processor là named JPMS module | `--processor-module-path` + `provides Processor with ...` | Module phải đã compile, module graph processor hợp lệ |
| Ứng dụng có named modules | `MODULE_SOURCE_PATH` / `MODULE_PATH` + `module-info.java` | Không tự động xác định processor location |
| Muốn chỉ validation/codegen, không tạo final classes | `-proc:only` khi được compiler hỗ trợ | Cần bước compile riêng nếu app cần class files |
| Không muốn processing | `-proc:none` | Nếu app gọi class generated, thiếu generated classes sẽ lỗi |
| Cần processor option riêng | `-Akey=value` và `ProcessingEnvironment.getOptions()` | Processor công bố supported options; khóa giá trị để tái hiện |

Không trộn tùy tiện `--processor-path` với `--processor-module-path` trong một invocation: chúng đại diện hai cơ chế cung cấp processor khác nhau, và `javac` có các ràng buộc đối với việc đồng thời chỉ định cả hai. Thực hành dễ bảo trì là **một nguồn processor được xác định rõ** và đường dẫn dependency phù hợp với nguồn đó.

## 13. Vòng xử lý, generated files và task.call()

Với processor dùng `Filer.createSourceFile(...)`:

```text
compilationUnits (source app + annotations)
    |
    v
Round 1: processor đọc Element, TypeMirror
    |
    +-- tạo GeneratedMessage.java qua Filer
    |
    v
Round 2: compiler nhận generated source
    |
    v
Round cuối: processingOver() == true
    |
    v
Tạo class files nếu compilation hoàn tất
```

`task.call()` trả về sau khi toàn bộ tác vụ xử lý và compile đã kết thúc; nó không phải lệnh “bắt đầu rồi trả về một future có thể poll” dù tên `CompilationTask` có thể gợi liên tưởng. API thực thi đồng bộ theo cách gọi `call()`. Nếu muốn compile công việc song song, bạn phải quản lý concurrency, classloaders, file managers, output ownership và trạng thái processor của riêng ứng dụng; **không** tái sử dụng một task để call hai lần.

Một processor object không nên được share qua các compilation tasks đồng thời như thể không có state. `AbstractProcessor` có `processingEnv` được gắn cho một processing environment; lifecycle của một instance cần được quản lý thận trọng. Đối với mỗi task độc lập, tạo processor instance mới là lựa chọn rõ ràng.

Với source files generated trong named module, cần đảm bảo module context của output được xác định. Các tùy chọn như `--default-module-for-created-files` có thể cần thiết trong những cấu hình module phức tạp nếu compiler không thể tự suy ra module chứa file mới; đừng mặc định “generated source luôn vào unnamed module” hoặc cứ tạo source tên có package là đủ. Generated sources cũng cần tuân thủ exports, reads và các quy tắc package của module đang compile.

## 14. Diagnostics, lỗi cấu hình và an toàn

### 14.1. Ba loại lỗi nên phân biệt

| Loại lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Compiler diagnostic** | `cannot find symbol`, module không đọc được package, code generated lỗi cú pháp | `DiagnosticCollector`, `task.call()==false`, source/line/column |
| **Processor diagnostic** | Processor dùng `Messager.printMessage(ERROR, ...)` để báo annotation sai | Báo đúng `Element`, kiểm tra processing options và input |
| **Exception của caller/tooling** | File manager không mở được file, processor ném exception không được xử lý, options sai kiểu | Catch/log exception riêng, không đổi thành “code nguồn sai” giả |

Khi cần test ổn định, kiểm tra **loại lỗi**, source vị trí và nội dung có nghĩa; không phụ thuộc nguyên văn mọi câu diagnostic hoặc đường dẫn tuyệt đối có thể đổi theo OS và JDK.

### 14.2. Vì sao không nên chạy processor không tin cậy?

Processors là **mã thực thi bên trong môi trường build**, có thể đọc file, environment variables và sử dụng API Java mà nó được cấp quyền. Nó không được sandbox tự động chỉ vì thuộc annotation processing. Khi một compiler host nhận project từ người khác, việc tự discover processor trên classpath không được kiểm soát có thể tạo bề mặt rủi ro. Nên:

- Chỉ chạy processors đã được phê duyệt, pin version/checksum;
- Cô lập processor classpath/module path và dependency graph;
- Không đưa secrets cần tránh vào process/CI job nếu processor không cần;
- Giới hạn tài nguyên, thời gian và filesystem scope qua **môi trường thực thi** của build tool;
- Kiểm tra generated sources trước khi đóng gói/phát hành.

`setProcessors` giảm sự bất ngờ do discovery nhưng **không** tự sandbox code processor object do host chọn.

### 14.3. Build tái hiện và nguồn cũ

`-d out` hay `CLASS_OUTPUT` không tự động xóa class cũ. Nếu task dùng cache hoặc generated file từ lần trước, ví dụ thiếu processor có thể bị che khuất. Với negative tests, hãy dùng thư mục mới/sạch cho output. Cần ghi toolchain, options, module roots, processor versions, file inputs/hashes và output để tái hiện compile failure.

Generated names nên ổn định, processor phải tránh `FilerException` do tạo trùng class, và không nên phụ thuộc thứ tự round/processor ngầm. `Filer.createSourceFile(name, originatingElements...)` hỗ trợ liên hệ output với originating element; build tools có thể tận dụng thông tin đó cho incremental compilation khi processor phù hợp.

## 15. Các lỗi thường gặp trong JavaCompiler API

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime image không có system compiler | Chạy host bằng JDK hoặc runtime image chứa module compiler |
| `ClassNotFoundException` cho processor | Host không load được processor object hoặc processor path sai | Phân biệt `setProcessors` và discovery; kiểm tra classloader/JAR |
| `Provider ... not found` | Named processor module không khai báo `provides` đúng hoặc không trên module path | Kiểm tra `module-info.java`, module JAR và `ANNOTATION_PROCESSOR_MODULE_PATH` |
| Generated class không xuất hiện | Processor không chạy, annotation không match, `-proc:none`, lỗi `Filer` | Kiểm tra `setProcessors`/options, diagnostics, `SOURCE_OUTPUT` |
| `module not found` | `MODULE_PATH`/`MODULE_SOURCE_PATH` sai hoặc module dependency không có | Kiểm tra `requires`, đường dẫn thực và module layouts |
| `package ... is not visible` | Module readability/exports không thỏa | Xem `module-info.java`, `requires` và `exports` |
| `duplicate module` | Các module candidates trùng tên hoặc source/module roots chồng nhau | Kiểm tra danh mục module candidates và output sạch |
| Generated file đặt sai module | Compiler không suy ra module phù hợp | Xem package/module context, `--default-module-for-created-files` khi cần |
| `IllegalStateException` sau `task.call()` | Gọi lại task hoặc cấu hình task sau khi đã bắt đầu | Tạo task mới cho lần compile khác |
| `IOException` từ `setLocationFromPaths` | Output directory chưa tồn tại hoặc quyền/đường dẫn không đúng | Tạo root output, xác nhận filesystem |
| Compile pass nhưng runtime không load class | Nhầm compiler output với runtime classpath/module path | Cấu hình lệnh `java` riêng, xem module graph khi chạy |
| Compiler dùng JDK khác mong đợi | Host JVM chứa compiler khác toolchain của project | Ghi `java -version` của host và compiler metadata |
| Cờ `-J` không tác dụng | Dùng CLI launcher option trong API task | Thiết lập JVM arguments lúc khởi động host process |

## 16. Quy trình thiết kế task API đáng tin

1. **Chọn ngữ nghĩa source:** unnamed module/classpath hay one/multiple named modules? Có `module-info.java` không?
2. **Xác định nguồn processor:** object instance trong host hay discovery qua classpath/named module? Tránh chồng chéo.
3. **Ghi toolchain Java:** host runtime/JDK, `ToolProvider`, mức `--release`, encoding, source file list.
4. **Tạo file manager** và khai báo rõ `CLASS_OUTPUT`, `SOURCE_OUTPUT`, `CLASS_PATH` hoặc `MODULE_PATH`/`MODULE_SOURCE_PATH`.
5. **Tạo units từ Paths** hoặc custom `JavaFileObject`, bảo đảm tên file/package/module hợp lệ.
6. **Tạo task qua getTask**, truyền options và diagnostics; đặt `setProcessors` hoặc `addModules` nếu cần, trước call.
7. **Gọi một lần `call()`**; ghi Boolean result, diagnostics và các exceptions của tool host/processor.
8. **Đối chiếu artifacts:** class outputs, generated sources, module-info.class và các files cần có; không chấp nhận output cũ che lỗi.
9. **Kiểm thử runtime** bằng classpath hoặc module path được cấu hình riêng, dùng Java runtime tối thiểu mà ứng dụng phải hỗ trợ.
10. **Giữ build reproducible và an toàn:** pin processor binaries, dependencies, hạn chế tài nguyên/secret, đóng file manager và loaders.

Một rule nhanh: **vị trí code ứng dụng** và **vị trí processor được thực thi** không có lý do gì phải giống nhau. Khi module graph của ứng dụng sai, sửa `MODULE_PATH` và `module-info.java`; khi processor không được discover, sửa `ANNOTATION_PROCESSOR_MODULE_PATH` hoặc `setProcessors`. Đừng sửa lẫn hai bên chỉ vì cùng có từ “module”.

## 17. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng host tạo `CompilationTask` rồi muốn dùng một `Processor` object đã có. Cần gọi API nào và khi nào?

**Đáp án:** `task.setProcessors(List.of(processorInstance))` **trước `task.call()`**. Cách này bỏ qua discovery mặc định; host phải load được processor.

**Câu 2.** Dự án đang compile module `shop.app` có `requires shop.api;`. JAR `shop.api` đã biên dịch thuộc location nào?

**Đáp án:** `StandardLocation.MODULE_PATH` (hoặc option `--module-path`), không phải `ANNOTATION_PROCESSOR_MODULE_PATH` chỉ vì dự án có processor.

**Câu 3.** Một named module cung cấp annotation processor qua `ServiceLoader` phải khai báo gì?

**Đáp án:** Module thường `requires java.compiler;` và `provides javax.annotation.processing.Processor with ...;`. Module processor và dependencies phải nằm trên processor module path thích hợp.

**Câu 4.** `MODULE_SOURCE_PATH` và `MODULE_PATH` khác gì?

**Đáp án:** Cái thứ nhất tìm source của named modules đang compile, cái thứ hai tìm các named modules đã biên dịch dùng làm dependency.

**Câu 5.** `task.addModules(List.of("shop.api"))` có tự tải JAR `shop.api` từ Internet hoặc đăng ký processor của module này không?

**Đáp án:** Không. Nó thêm root module cho resolution; module vẫn cần observable qua cấu hình system/module paths thích hợp, và việc processor discovery là cơ chế riêng.

**Câu 6.** Vì sao không dùng `-J-Xmx2g` trong `getTask(..., options, ...)` để nâng heap?

**Đáp án:** `-J` là tùy chọn của `javac` command-line launcher để chuyển JVM option. Trong Compiler API in-process, host JVM đã chạy, cần cấu hình heap lúc khởi động **host**.

**Câu 7.** Task trả `true` nhưng `GeneratedMessage.java` không có. Điều này có thể hợp lý không?

**Đáp án:** Có nếu processor không được yêu cầu, annotation không match hoặc codegen không nằm trong hợp đồng task. Nếu project kỳ vọng codegen, phải xác nhận processor đã chạy và output cụ thể được sinh; compilation success một mình không chứng minh có generator.

**Câu 8.** Tại sao cần `Files.createDirectories(output)` trước `StandardJavaFileManager.setLocationFromPaths(CLASS_OUTPUT, ...)`?

**Đáp án:** Hợp đồng StandardJavaFileManager yêu cầu output location trỏ tới existing directory; nếu đường dẫn không tồn tại, API có thể báo `IOException`.

**Câu 9.** Sau lần compile lỗi, chương trình host vẫn thấy `App.class` ở output. Có được coi task vừa tạo artifact hợp lệ không?

**Đáp án:** Không. Output có thể chứa file cũ hoặc partial artifacts. Dùng output mới/sạch, kiểm tra `task.call()` và diagnostics.

**Câu 10.** Vì sao với named modules, việc đặt processor JAR trên `MODULE_PATH` chưa chắc khiến processor chạy?

**Đáp án:** `MODULE_PATH` của compilation environment phục vụ modules ứng dụng; processor chạy trong compiler environment và cần processor instance hoặc processor discovery location tương ứng.

## 18. Tài liệu tham khảo chính thức

- **Java SE 21 JavaCompiler API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html — `getTask`, compiler file manager, diagnostics.
- **Java SE 21 CompilationTask API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html — `setProcessors`, `addModules`, `setLocale` và `call`.
- **Java SE 21 StandardJavaFileManager:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html — `getJavaFileObjectsFromPaths`, `setLocationFromPaths`, `setLocationForModule`.
- **Java SE 21 StandardLocation:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardLocation.html — `MODULE_PATH`, `MODULE_SOURCE_PATH`, `ANNOTATION_PROCESSOR_PATH`, `ANNOTATION_PROCESSOR_MODULE_PATH` và output locations.
- **Java SE 21 ToolProvider:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html — `getSystemJavaCompiler` và khi nào có thể `null`.
- **Oracle JDK 21 javac reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — các options module, processor và phần *Compilation Environment and Runtime Environment*.
- **Java SE 21 Processor API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html — lifecycle và semantics của annotation processing.
- **Java Language Specification `7, `9:** https://docs.oracle.com/javase/specs/jls/se21/html/ — packages, modules, annotations.

**Tóm lại:** khi dùng JavaCompiler API, cấu hình **modules của ứng dụng** qua `MODULE_SOURCE_PATH`/`MODULE_PATH`, cấu hình **processor được thực thi** qua `setProcessors` hoặc processor path/module path, và cấu hình **nơi ghi artifacts** qua `SOURCE_OUTPUT`/`CLASS_OUTPUT`. Tách ba vai trò này rồi kiểm tra `task.call()`, diagnostics và generated files sẽ giúp bạn tạo các tác vụ biên dịch có thể kiểm soát, tái hiện và debug.