# Cấu hình classpath, module path, thư mục đầu ra và --release khi biên dịch Java lúc chạy

## 1. Bối cảnh và bốn cấu hình bắt buộc hiểu

Trong hệ thống Java có khả năng mở rộng lúc chạy (*runtime extensibility*), ứng dụng chủ (host) có thể nhận file `.java` của plugin, biên dịch bằng `javax.tools.JavaCompiler` và nạp các file `.class` vừa tạo. Biên dịch trong ứng dụng khác biên dịch trong IDE ở chỗ **host phải quyết định tường minh** loại dependency được phép nhìn thấy, mô hình module, nơi đặt bytecode và phiên bản Java đích.

Bốn tham số trọng tâm của bài:

| Cấu hình | Cờ javac | Vai trò chính |
| --- | --- | --- |
| **Classpath** | `--class-path` / `-classpath` / `-cp` | Cho compiler tìm các class, package và JAR trong **mô hình classpath** |
| **Module path** | `--module-path` / `-p` | Cho compiler tìm những **named modules đã biên dịch** dùng trong JPMS |
| **Thư mục output** | `-d` | Chỉ đường dẫn lưu kết quả `.class`, có thể gồm `module-info.class` |
| **Java release đích** | `--release N` | Giới hạn mức cú pháp, class-file version và Java platform API theo phiên bản N được javac hỗ trợ |

Ví dụ, host chạy trên JDK 21 có thể muốn tạo plugin dùng được ở Java 17. `--release 17` sẽ ngăn source sử dụng tính năng ngôn ngữ hoặc Java platform API chỉ có ở Java 21. Tuy nhiên, nó **không tự cố định phiên bản thư viện của plugin** và không bảo đảm JVM lúc chạy tìm được mọi dependency.

**Mục tiêu học tập:** biết khi nào dùng classpath hay module path; truyền chúng vào `JavaCompiler.getTask`; chọn thư mục output sạch; compile cho đúng release; kiểm tra kết quả và nạp plugin mà không nhầm compile-time với runtime.

## 2. Phân tách quá trình compile và quá trình nạp

Luồng tổng quát:

~~~text
File .java của plugin
      |
      v
JavaCompiler (javac)
      |  --class-path     -> nơi tìm class/JAR không theo named module
      |  --module-path    -> nơi tìm dependency named module
      |  --release 17     -> cú pháp + bytecode + platform API
      |  -encoding UTF-8  -> charset đọc source
      |  -d build/output  -> gốc file .class được sinh ra
      v
Class files trong build/output
      |
      | host xác minh artifact và runtime dependencies
      v
ClassLoader hoặc JPMS module layer thích hợp
      |
      v
Plugin được nạp và gọi qua hợp đồng dùng chung
~~~

**Biên dịch thành công chưa phải là nạp thành công.** Compiler cần các đường dẫn để phân giải kiểu ở source. JVM cần loader hoặc module graph để tìm các lớp lúc chạy. Cờ `-d` chỉ quyết định output của compiler, không tự thêm output vào classpath của tiến trình hiện tại.

Trước khi compile, host nên xác định source là code classpath hay source của named module, compiler/JDK thực tế đang dùng, phiên bản API host mà plugin được phép tham chiếu, các JAR/module được tin cậy và thư mục do ai sở hữu. Đây là đầu vào của mỗi build, không nên lấy ngầm tất cả dependency của host hoặc toàn bộ classpath của ứng dụng.

## 3. Classpath: cấu hình phụ thuộc theo mô hình truyền thống

Giả sử host công bố hợp đồng sau trong `plugin-api.jar`:

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

Plugin cung cấp implementation:

~~~java
package demo.plugin;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Các đoạn trên là file nội dung sẽ dùng trong ví dụ chạy được ở mục 7. Khi biên dịch `UppercaseTransformer.java`, javac phải tìm được `demo.api.Transformer`. Nếu API nằm trong `build/plugin-api.jar`:

~~~bash
javac --release 17 --class-path build/plugin-api.jar \
  -d build/generated/classes \
  src/plugin/demo/plugin/UppercaseTransformer.java
~~~

Trong đó:

- `--class-path build/plugin-api.jar` là **compile-time dependency**; cho phép javac phân giải `demo.api.Transformer`.
- `--release 17` chọn ngôn ngữ, class-file format và Java platform APIs của Java 17.
- `-d build/generated/classes` tạo file `build/generated/classes/demo/plugin/UppercaseTransformer.class` (giả sử thư mục output gốc có quyền ghi).

`--release` không thể thay thế classpath của thư viện nghiệp vụ: Java 17 không tự chứa `demo.api.Transformer`. Nếu thiếu API JAR, compiler sẽ báo lỗi như `package demo.api does not exist` hoặc `cannot find symbol`.

### 3.1. Nhiều dependency và dấu phân cách path

Một compile classpath có thể chứa nhiều JAR hoặc thư mục chứa file `.class`. Dùng một chuỗi path-list được nối theo hệ điều hành:

| Hệ điều hành | Ký tự phân cách | Ví dụ |
| --- | --- | --- |
| Linux/macOS | `:` | `"build/plugin-api.jar:lib/helper.jar"` |
| Windows | `;` | `"build/plugin-api.jar;lib/helper.jar"` |

Nếu host tự tạo chuỗi path trong Java, dùng `File.pathSeparator` thay vì hard-code dấu hai chấm. Với code dùng Java Compiler API, mỗi cặp option/value nên là hai phần tử danh sách riêng, ví dụ `List.of("--class-path", cp)`.

Classpath wildcard, chẳng hạn `lib/*`, có thể đưa các JAR trực tiếp trong thư mục vào classpath theo quy tắc của công cụ Java, nhưng không là lời hứa tự quét đệ quy mọi thư mục con. Nên chỉ định rõ API và thư viện được phép thay vì quét mọi JAR không kiểm soát; thứ tự và phiên bản dependency có thể ảnh hưởng resolution.

### 3.2. Classpath lúc compile khác classpath lúc chạy

Plugin được compile thành `build/generated/classes`, nhưng host đang chạy **không tự nhìn thấy** các lớp mới. Có thể:

1. Khởi động một JVM mới với output directory/JAR trên runtime classpath.
2. Dùng `URLClassLoader` hoặc classloader riêng nhìn thấy output directory.
3. Với named modules, tạo module layer hoặc khởi động JVM với module path phù hợp.

Nếu classpath compile dùng `plugin-api.jar` phiên bản A, nhưng runtime host chỉ có API phiên bản B không tương thích, plugin có thể lỗi liên kết/ép kiểu khi chạy. Vì vậy build nên ghi nhận version và kiểm thử với runtime API thật.

## 4. Module path: cấu hình JPMS khác với classpath

**Java Platform Module System (JPMS)** từ Java 9 dùng `module-info.java` mô tả named module, phụ thuộc `requires`, package công khai `exports`, và service `uses`/`provides`.

Ba descriptor minh họa:

~~~java
// File module-info.java của module demo.api
module demo.api {
    exports demo.api;
}
~~~

~~~java
// File module-info.java của module demo.provider
module demo.provider {
    requires demo.api;
    provides demo.api.Transformer
            with demo.provider.UppercaseTransformer;
}
~~~

~~~java
// File module-info.java của module demo.host
module demo.host {
    requires demo.api;
    uses demo.api.Transformer;
}
~~~

Đây là **ba file khác nhau** (không thể đặt cả ba khai báo vào một file). Mục 8 có source code và lệnh chạy đầy đủ.

`--module-path` trỏ tới các **named modules đã biên dịch** trong các modular JAR hoặc exploded module directories. Ví dụ `demo.api` đã được biên dịch vào `build/mods/demo.api` thì compiler của `demo.provider` có thể dùng:

~~~bash
javac --release 17 --module-path build/mods \
  -d build/mods/demo.provider \
  modsrc/demo.provider/module-info.java \
  modsrc/demo.provider/demo/provider/UppercaseTransformer.java
~~~

Compiler biết `module demo.provider` có `requires demo.api`, từ đó tìm `demo.api` trong module path và kiểm tra package `demo.api` có được export hay không.

**Không đánh đồng** đường dẫn sau:

| Option | Dùng cho |
| --- | --- |
| `--class-path` | Class/JAR theo mô hình unnamed module và classpath |
| `--module-path` | Module **đã biên dịch** được tìm theo module name |
| `--module-source-path` | Cây **source** tổ chức theo từng module, thường dùng khi compile nhiều module cùng lần |
| `--add-modules` | Bổ sung root modules cần resolve |
| `--add-reads` | Điều chỉnh quan hệ đọc module cho một trường hợp tích hợp có chủ đích |

Một named module không thể viết `requires unnamed` để tự đọc dependency trên classpath. Khi plugin và host dùng JPMS, nên có module API được đặt đúng module path hoặc một cơ chế bridge được thiết kế tường minh; không dùng các option vá module graph một cách ngẫu nhiên.

Module path có thể gồm nhiều phần tử, nối bằng `File.pathSeparator`. Nó không có nghĩa mọi module trên đĩa đều tự được resolved hay mọi package đều được truy cập. Cần phân biệt **tìm thấy module**, **module được resolve**, **quan hệ requires/reads** và **exports/opens**.

## 5. Thư mục đầu ra -d và quản lý artifact

`-d <dir>` chỉ định thư mục gốc để javac ghi các file `.class` theo cấu trúc package. Ví dụ:

~~~text
build/generated/classes/
  demo/
    plugin/
      UppercaseTransformer.class
~~~

Với JPMS biên dịch từng module, output có thể là:

~~~text
build/mods/
  demo.api/
    module-info.class
    demo/api/Transformer.class
  demo.provider/
    module-info.class
    demo/provider/UppercaseTransformer.class
  demo.host/
    module-info.class
    demo/host/ModHost.class
~~~

Directory `build/mods` chứa các exploded modules ở thư mục con trực tiếp. `module-info.class` nằm ở gốc directory **của từng module**.

Các quy tắc quan trọng khi biên dịch lúc chạy:

- Tạo directory output với `Files.createDirectories(output)` và kiểm tra quyền ghi. Không để source của người dùng tự quyết định đường dẫn output bên ngoài vùng host kiểm soát.
- Dùng đường dẫn riêng theo plugin/build/version, tránh trộn các file từ lần compile cũ vào lần mới.
- Một compile thất bại vẫn có thể tạo **một phần output**. Không được phát hành hoặc nạp folder này chỉ vì nó có file `.class`.
- `-d` không tự làm output trở thành runtime classpath/module path; loader phải được cấu hình rõ.
- `-s` dành cho generated source của annotation processing; `-h` dành cho native headers khi có nhu cầu. Đừng dùng `-d` để trộn output khác loại vào cùng directory mà không kiểm soát.
- Khi thay version plugin, compile vào chỗ mới và chỉ chuyển sang artifact đó khi QA đạt. Tránh ghi đè directory/JAR đang được loader hoặc thread plugin cũ sử dụng.
- Dọn output theo lifecycle sau khi chắc rằng không còn reader, handle, classloader hoặc task nào cần artifact cũ.

Thư mục output đóng vai trò **build artifact**, không phải mặc định là nguồn sự thật hay nơi tự do cho mọi plugin ghi file. Nếu cần tính lặp lại, lưu lại source hash, compiler version, options, dependency versions và ID bản build.

## 6. --release so với -source/-target

`--release 17` yêu cầu compiler tạo class file phù hợp Java 17 và chỉ cho sử dụng các cú pháp cùng Java platform APIs được hỗ trợ trong Java 17. Với Java 17, major version của file class là **61**.

| Cấu hình | Cú pháp | Bytecode | Hạn chế Java platform API |
| --- | --- | --- | --- |
| `--release 17` | Java 17 | Java 17 | Có: theo API của release 17 |
| `-source 17 -target 17` | Java 17 | Java 17 | Không bảo đảm khi javac chạy trên JDK mới hơn |
| Không có cờ phiên bản | Mặc định bản javac được gọi | Mặc định javac | Có thể đổi khi nâng compiler |

Khi dùng `-source 17 -target 17` trên JDK mới, code có thể vẫn tham chiếu một method của Java platform vừa xuất hiện ở release mới; việc tạo bytecode version 61 **không ngăn runtime Java 17 gặp lỗi** vì method không tồn tại. `--release 17` là cách thông thường để ràng buộc source, target và platform API trong một option.

Lưu ý:

1. Không kết hợp `--release` với `-source` hoặc `-target` cho một compilation task.
2. Bản javac chỉ hỗ trợ những release mà compiler đó công bố trong `javac --help`; JDK 17 không thể compile với `--release 21`.
3. `--release 17` không khóa phiên bản JAR bên ngoài JDK. Dependency được compile cho Java 21 hoặc API host/plugin khác nhau vẫn có thể làm build/runtime thất bại.
4. `--release` không phải sandbox; nó không ngăn source, annotation processor hoặc bytecode đã nạp có tác dụng phụ khi chạy.
5. Nếu host dùng JavaCompiler API, truyền cờ dưới dạng các phần tử option, ví dụ `List.of("--release", "17")`. Tránh gộp thành một string `"--release 17"` rồi truyền cho `getTask`.

Với một hệ thống plugin, cần chạy **integration tests trên runtime đích** bên cạnh compile với `--release`.

## 7. Chương trình Java 17 chạy được: host gọi JavaCompiler để biên dịch plugin

Ví dụ này chứng minh cả classpath, `-d` và `--release` trong một luồng thực tế. Host chỉ được compile trước với API; file source plugin vẫn chưa có `.class`. Khi chạy, host gọi compiler, tạo class output rồi chủ động nạp nó.

### 7.1. Cấu trúc thư mục

~~~text
runtime-compiler-demo/
  src/
    api/demo/api/Transformer.java
    plugin/demo/plugin/UppercaseTransformer.java
    host/demo/host/CompileHost.java
  build/
    api/
    host/
    plugin-api.jar
    generated/classes/
~~~

Các file bên dưới nằm đúng đường dẫn nêu trên. Thư mục `build` được tạo trong quá trình chạy lệnh, không cần tự tạo file `.class`.

### 7.2. File hợp đồng API

**`src/api/demo/api/Transformer.java`:**

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

### 7.3. File nguồn plugin

**`src/plugin/demo/plugin/UppercaseTransformer.java`:**

~~~java
package demo.plugin;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Interface thuộc API dùng chung; implementation chỉ biết hợp đồng và Java standard library. Ta chưa dùng javac để compile file plugin ở terminal.

### 7.4. File host gọi JavaCompiler API

**`src/host/demo/host/CompileHost.java`:**

~~~java
package demo.host;

import demo.api.Transformer;
import java.net.URL;
import java.net.URLClassLoader;
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
import javax.tools.ToolProvider;

public final class CompileHost {
    private CompileHost() {
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with a system compiler is required");
        }

        Path source = Path.of(
                "src/plugin/demo/plugin/UppercaseTransformer.java");
        Path apiJar = Path.of("build/plugin-api.jar");
        Path output = Path.of("build/generated/classes");
        Files.createDirectories(output);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        List<String> options = List.of(
                "--release", "17",
                "-encoding", "UTF-8",
                "-proc:none",
                "--class-path", apiJar.toString(),
                "-d", output.toString()
        );

        boolean compiled;
        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjectsFromPaths(List.of(source));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics, options, null, units);
            compiled = Boolean.TRUE.equals(task.call());
        }

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            System.err.println(
                    d.getKind() + ": " + d.getMessage(Locale.ROOT));
        }

        System.out.println("compiled=" + compiled);
        if (!compiled) {
            throw new IllegalStateException("Plugin compilation failed");
        }

        URL classesUrl = output.toUri().toURL();
        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{classesUrl},
                CompileHost.class.getClassLoader())) {

            Class<?> implementation = Class.forName(
                    "demo.plugin.UppercaseTransformer", true, loader);
            Transformer plugin = (Transformer) implementation
                    .getDeclaredConstructor().newInstance();

            System.out.println(
                    "result=" + plugin.transform("hello plugin"));
        }
    }
}
~~~

**Giải thích các điểm quan trọng:**

1. `ToolProvider.getSystemJavaCompiler()` lấy system compiler trên JDK phù hợp. Một runtime image không có compiler có thể trả `null`; host phải báo lỗi tường minh.
2. `StandardJavaFileManager` chuyển `Path` thành `JavaFileObject`, quản lý I/O và được đóng bằng try-with-resources. `DiagnosticCollector` ghi lại lỗi/warning khi compile.
3. `--class-path build/plugin-api.jar` cho javac giải quyết `demo.api.Transformer` mà plugin cần. Host không compile phụ thuộc implementation plugin.
4. `--release 17` chọn Java 17; `-encoding UTF-8` đọc source nhất quán. `-proc:none` tắt annotation processing vì ví dụ không dùng processor.
5. `-d build/generated/classes` chỉ file output. Sau compile, host tự tạo `URLClassLoader` trỏ đến output.
6. Parent loader của plugin là loader của `CompileHost` đang biết `Transformer`, nhờ vậy cast sang interface dùng chung có thể thực hiện.
7. Host chỉ nạp plugin nếu compilation task trả `true`. Một task trả `false` phải kèm diagnostics; không dùng class cũ tồn dư từ lần compile trước.
8. `URLClassLoader.close()` đóng tài nguyên do loader quản lý, nhưng không tự ngắt các thread plugin hay bảo đảm class được unload ngay. Plugin thực tế cần hợp đồng lifecycle riêng.

Các path tương đối được giải theo **working directory của tiến trình host**. Khi chạy từ thư mục khác, cần tính absolute paths hoặc truyền cấu hình rõ ràng. Không xây một shell command bằng cách nối source path của người dùng: `getTask` nhận **danh sách option** nên host có thể kiểm tra từng path và policy trước khi gọi compiler.

### 7.5. Lệnh biên dịch và chạy

Từ thư mục `runtime-compiler-demo` trên Linux/macOS với JDK 17+, dùng Bash:

~~~bash
mkdir -p build/api build/host

# Biên dịch API và đóng gói thành JAR.
javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Transformer.java
jar --create --file build/plugin-api.jar -C build/api .

# Host được biên dịch với API mà không cần implementation plugin.
javac --release 17 -encoding UTF-8 \
  --class-path build/plugin-api.jar \
  -d build/host src/host/demo/host/CompileHost.java

# Không biên dịch UppercaseTransformer ở terminal.
# CompileHost sẽ dùng JavaCompiler khi chạy.
java --class-path "build/host:build/plugin-api.jar" \
  demo.host.CompileHost
~~~

**Stdout chính xác khi build thành công:**

~~~text
compiled=true
result=HELLO PLUGIN
~~~

Vì source hợp lệ, không có diagnostics được in lên stderr trong lần chạy thành công. Sau khi host hoàn tất, xuất hiện:

~~~text
build/generated/classes/
  demo/plugin/UppercaseTransformer.class
~~~

Với Windows PowerShell, lệnh khởi chạy tương ứng (sau khi đã tạo JAR và class host) dùng dấu chấm phẩy:

~~~powershell
java --class-path "build/host;build/plugin-api.jar" demo.host.CompileHost
~~~

Các lệnh Bash nhiều dòng dùng ký tự nối dòng backslash, còn PowerShell nên dùng lệnh `javac`/`jar` trên một dòng hoặc cú pháp riêng.

### 7.6. Nếu đổi option thì điều gì xảy ra?

- Bỏ `--class-path build/plugin-api.jar` khi compile plugin: javac không thấy `demo.api.Transformer` và báo lỗi tên package/symbol.
- Bỏ `-d`: output có thể đi vào vị trí mặc định không nằm nơi host dự kiến. Với runtime compiler, đặt location có chủ đích để dễ kiểm soát và dọn dẹp.
- Dùng `--release 21` trên JDK 17: compiler không hỗ trợ target mới hơn chính nó; không được giả định sẽ compile thành công.
- Thay `-d` bằng một directory cũ còn file class phiên bản trước: compile lỗi có thể vẫn để lại artifact có vẻ hợp lệ. Dùng output directory mới theo từng build để không nhầm lần compile.
- Bỏ `URLClassLoader` hoặc không cấu hình classpath runtime: compile vẫn thành công nhưng host không tự nhìn thấy class trong `-d`.
- Tạo một bản `Transformer.class` khác trong plugin loader: có nguy cơ hai class identity khác nhau, dẫn tới lỗi subtype/cast.

## 8. Ví dụ JPMS đầy đủ: ba named module và module path

Bây giờ biên dịch **một chương trình khác** theo JPMS. Có ba named module: API, provider và host. Trên module path, provider dùng `provides` trong descriptor thay vì file `META-INF/services` như SPI classpath.

### 8.1. Cấu trúc nguồn

~~~text
modsrc/
  demo.api/
    module-info.java
    demo/api/Transformer.java
  demo.provider/
    module-info.java
    demo/provider/UppercaseTransformer.java
  demo.host/
    module-info.java
    demo/host/ModHost.java
build/
  mods/                (được tạo trong các bước compile)
~~~

Tên module trong `module-info.java` phải đúng với module mà các lệnh `requires` và `--module` tham chiếu.

**`modsrc/demo.api/module-info.java`:**

~~~java
module demo.api {
    exports demo.api;
}
~~~

**`modsrc/demo.api/demo/api/Transformer.java`:**

~~~java
package demo.api;

public interface Transformer {
    String transform(String input);
}
~~~

**`modsrc/demo.provider/module-info.java`:**

~~~java
module demo.provider {
    requires demo.api;
    provides demo.api.Transformer
            with demo.provider.UppercaseTransformer;
}
~~~

**`modsrc/demo.provider/demo/provider/UppercaseTransformer.java`:**

~~~java
package demo.provider;

import demo.api.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    public UppercaseTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**`modsrc/demo.host/module-info.java`:**

~~~java
module demo.host {
    requires demo.api;
    uses demo.api.Transformer;
}
~~~

**`modsrc/demo.host/demo/host/ModHost.java`:**

~~~java
package demo.host;

import demo.api.Transformer;
import java.util.ServiceLoader;

public final class ModHost {
    private ModHost() {
    }

    public static void main(String[] args) {
        int count = 0;
        for (Transformer provider : ServiceLoader.load(Transformer.class)) {
            count++;
            System.out.println(
                    "module=" + provider.transform("hello module"));
        }
        if (count == 0) {
            throw new IllegalStateException("No provider resolved");
        }
    }
}
~~~

Module `demo.provider` không cần `exports demo.provider` để service provider được tìm bởi `ServiceLoader` khi nó được công bố trong `provides` và module đã resolved. Host chỉ dùng API và `ServiceLoader`, không tham chiếu tên implementation.

### 8.2. Biên dịch từng module bằng --module-path

Trong terminal tại directory chứa `modsrc`, với JDK 17+:

~~~bash
mkdir -p build/mods/demo.api build/mods/demo.provider build/mods/demo.host

# 1. Module API.
javac --release 17 -encoding UTF-8 \
  -d build/mods/demo.api \
  modsrc/demo.api/module-info.java \
  modsrc/demo.api/demo/api/Transformer.java

# 2. Module provider cần demo.api từ module path.
javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.provider \
  modsrc/demo.provider/module-info.java \
  modsrc/demo.provider/demo/provider/UppercaseTransformer.java

# 3. Module host cũng cần demo.api.
javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.host \
  modsrc/demo.host/module-info.java \
  modsrc/demo.host/demo/host/ModHost.java

# 4. Chạy module host, resolve rõ provider.
java --module-path build/mods --add-modules demo.provider \
  --module demo.host/demo.host.ModHost
~~~

**Stdout:**

~~~text
module=HELLO MODULE
~~~

`--add-modules demo.provider` bảo đảm provider module được đưa vào module graph trong demo. `demo.host` khai báo `uses demo.api.Transformer` và `demo.provider` khai báo `provides`, nên `ServiceLoader` trả implementation.

Kết quả biên dịch:

~~~text
build/mods/
  demo.api/
    module-info.class
    demo/api/Transformer.class
  demo.provider/
    module-info.class
    demo/provider/UppercaseTransformer.class
  demo.host/
    module-info.class
    demo/host/ModHost.class
~~~

`build/mods` là directory chứa các exploded modules con, nên dùng nó làm `--module-path` cho compile/run. Nếu ở Windows có nhiều đường dẫn module path, nối bằng dấu chấm phẩy; ví dụ hiện tại chỉ có **một** phần tử `build/mods` nên không cần dấu phân cách.

### 8.3. Lựa chọn khác: compile nhiều module qua --module-source-path

Với layout `modsrc/<module-name>/...`, có thể biên dịch cùng ba module **trong một lần javac**, thay cho ba lệnh compile riêng ở trên:

~~~bash
mkdir -p build/allmods
javac --release 17 -encoding UTF-8 \
  --module-source-path modsrc \
  -d build/allmods \
  --module demo.api,demo.provider,demo.host
java --module-path build/allmods --add-modules demo.provider \
  --module demo.host/demo.host.ModHost
~~~

Cờ `--module-source-path` mô tả **nơi tìm source theo module**, còn `--module-path` mô tả nơi tìm **các module đã compile**. Ở tình huống compile từ đầu cả ba module, `--module-source-path` cho javac biết layout và dependency giữa các module ngay trong cùng task.

Trong Java Compiler API, cách cấu hình options (đoạn minh họa, chưa phải chương trình độc lập):

~~~java
List<String> moduleOptions = List.of(
        "--release", "17",
        "--module-source-path", "modsrc",
        "--module", "demo.api,demo.provider,demo.host",
        "-d", "build/allmods"
);
~~~

Cần sử dụng `JavaCompiler.getTask` và file manager phù hợp, hoặc compile từng module trong nhiều task với module path cập nhật sau mỗi lần. Đừng bỏ qua việc phát hành output và classloader/module layer sau compile: các module vừa compile không tự động xuất hiện trong graph của JVM host đã khởi động.

## 9. Ánh xạ với Java Compiler API

`JavaCompiler` thuộc package `javax.tools` của module `java.compiler`. Ví dụ mục 7 dùng `getTask` với `StandardJavaFileManager` và `DiagnosticCollector`. Trên JDK thông thường, compiler được tìm qua `ToolProvider.getSystemJavaCompiler()`.

| Nhu cầu | Command-line javac | List options của getTask |
| --- | --- | --- |
| Thư viện classpath | `--class-path cp` | `List.of("--class-path", cp)` |
| Module dependencies | `--module-path mp` | `List.of("--module-path", mp)` |
| Source layout của nhiều module | `--module-source-path src` | `List.of("--module-source-path", src)` |
| Chọn module cần biên dịch | `--module names` | `List.of("--module", names)` |
| Output class files | `-d out` | `List.of("-d", out)` |
| Target platform release | `--release 17` | `List.of("--release", "17")` |
| Charset source | `-encoding UTF-8` | `List.of("-encoding", "UTF-8")` |
| Tắt annotation processing | `-proc:none` | `List.of("-proc:none")` |
| Source code do processor tạo | `-s generated` | `List.of("-s", generated)` |

Ngoài options, `StandardJavaFileManager` cho phép cấu hình locations như `StandardLocation.CLASS_PATH`, `MODULE_PATH`, `CLASS_OUTPUT` và `SOURCE_OUTPUT`. Có thể dùng các setter phù hợp để cấu hình đường dẫn qua API; tránh đồng thời truyền options mâu thuẫn với các locations đã thiết lập. `getTask` lấy source qua `Iterable<? extends JavaFileObject>`, không phải bằng cách ghép câu lệnh shell và gọi subprocess.

**Quan trọng với đường dẫn:** trong process Java, một path tương đối như `build/plugin-api.jar` được giải theo working directory, không mặc nhiên theo directory chứa source file. Host nên resolve path, kiểm tra nó thuộc vùng được phép, ghi log path đã chuẩn hóa và lựa chọn `File.pathSeparator` phù hợp OS khi tạo path-list.

**Diagnostics và kết quả:** khi task trả `false`, `DiagnosticCollector` chứa thông tin có thể gồm file, dòng, cột, mức độ lỗi. Hãy ghi chúng theo build ID; không nạp output cũ. Khi task ném exception do cấu hình path, file manager hoặc option, cũng cần báo lỗi rõ. Một lượt compile chỉ được công bố là thành công khi kết quả compiler và các điều kiện artifact của hệ thống đều đạt.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách kiểm tra |
| --- | --- | --- |
| `package ... does not exist` / `cannot find symbol` | Thiếu API/dependency trong classpath hoặc package module không được đọc/export | Kiểm tra `--class-path`, `--module-path`, `requires`/`exports` |
| `module not found` | Tên/module output sai hoặc module chưa nằm ở `--module-path` | Kiểm tra `module-info.class` và tên module |
| Compile thành công nhưng `ClassNotFoundException` | Output `-d` không có trong runtime classpath/loader | Xem file class, classloader URL, runtime path |
| Compile thành công nhưng `NoClassDefFoundError` | Thiếu runtime dependency hoặc liên kết loại lớp thất bại | Đọc cause/stack trace và dependency runtime |
| `UnsupportedClassVersionError` | Class được compile với Java mới hơn runtime | Đối chiếu javac `--release` với JVM target |
| Có provider module nhưng ServiceLoader rỗng | Provider module chưa resolved hoặc `uses`/`provides` sai | Kiểm tra `--add-modules`, module graph, descriptors |
| Plugin bị `ClassCastException` | API bị định nghĩa bởi hai classloaders hoặc sai kiểu | Giữ API chung, kiểm tra defining loader |
| Output bị lẫn file cũ | Dùng lại output directory sau build lỗi hoặc đổi package | Dùng directory sạch theo build/version |
| `ToolProvider.getSystemJavaCompiler() == null` | JVM đang chạy thiếu system compiler | Dùng JDK/runtime image có compiler |
| Lỗi API trên runtime Java cũ | Dùng `-source/-target` mà không giới hạn platform API hoặc thư viện ngoài quá mới | Dùng `--release` và test trên runtime thật |
| Compiler báo lỗi mà host tiếp tục nạp | Không kiểm tra `CompilationTask.call()` / diagnostics | Fail-fast, rollback artifact, không chạy class cũ |

Nếu compile thất bại, xử lý lỗi **compile** trước. Nếu compile thành công nhưng load thất bại, kiểm tra **runtime path, classloader identity, module resolution và dependency** thay vì giả định compiler không nhận cờ.

## 11. Quy ước vận hành cho biên dịch động

Một implementation có thể áp dụng các chính sách:

1. **Input và version:** nhận source, định danh plugin, chế độ classpath/module, API version, target `--release` và danh sách dependency được phép. Không lấy tùy tiện toàn bộ host classpath.
2. **Output ownership:** compiler service tạo directory build riêng, không sửa directory đang được plugin chạy sử dụng. Đặt cấu trúc output dễ truy vết và dọn cleanup theo lifecycle.
3. **Idempotency:** với cùng source, options, compiler và dependencies đã pin, kết quả build có thể được xác minh/đối chiếu theo fingerprint. Không để file build cũ làm thay đổi kết quả.
4. **Build failure:** thu diagnostics, đánh dấu build thất bại, không publish output một phần và không fallback âm thầm sang class cũ.
5. **Publish:** xác minh bytecode/manifest/dependency trước khi chuyển plugin mới sang active; có đường rollback về artifact đã kiểm tra.
6. **Runtime boundary:** compile xong mới chọn classloader/module layer; kiểm tra API compatibility, stop/cancel/close plugin cũ theo hợp đồng.
7. **An toàn:** tắt processor khi không cần (ví dụ `-proc:none`). Compiler/processor và bytecode/plugin có thể chạy mã có tác dụng phụ; `--release`, `-proc:none` và classloader **không phải sandbox** cho mã không tin cậy. Nếu cần, biên dịch và chạy trong tiến trình cô lập với giới hạn OS, CPU, bộ nhớ và thời gian.

Một compile task chạy trong JVM host cũng có thể tốn thời gian/bộ nhớ đáng kể. Hệ thống dùng trong sản phẩm cần giới hạn số job song song, theo dõi cancel/timeout theo hợp đồng và bảo vệ storage khỏi output không giới hạn.

## 12. Tự kiểm tra nhanh

1. Source `UppercaseTransformer.java` cần `demo.api.Transformer` trong JAR: cờ nào cho javac thấy API? **`--class-path build/plugin-api.jar`**.
2. Muốn file `.class` ra `build/generated/classes`: dùng **`-d build/generated/classes`**, và sau compile còn phải cho loader nhìn thấy directory này.
3. Có `module-info.java` với `requires demo.api` và module API đã biên dịch: dùng **`--module-path`** trỏ tới module path chứa `demo.api`.
4. Có cả cây source `modsrc/demo.api`, `modsrc/demo.provider`, `modsrc/demo.host`: dùng **`--module-source-path modsrc`** nếu muốn compile nhiều module cùng lần.
5. Host dùng JDK 21, plugin phải chạy trên Java 17: dùng **`--release 17`** và test dependency/runtime phiên bản Java 17. `-target 17` đơn lẻ chưa đủ để ràng buộc platform APIs.
6. Dùng `getTask`: mỗi compiler option và giá trị truyền thành **phần tử riêng** trong `List<String>`; `"--release 17"` không phải một phần tử option hợp lệ thay cho hai phần tử `"--release", "17"`.
7. Thấy `compiled=true` nhưng host không tìm thấy class: xem **loader/runtime classpath hoặc module layer**; `-d` chỉ ghi output.
8. Lần build mới thất bại nhưng directory còn class cũ: **không nạp file ấy**; tạo build directory mới và chỉ công bố artifact đủ điều kiện.

**Kết luận:** Khi biên dịch plugin lúc chạy, cần xác định đúng **classpath hay module path**, truyền phụ thuộc tường minh, đặt **output directory** do host kiểm soát và dùng **--release** phù hợp với runtime đích. Tách compilation và class loading, cùng với diagnostics và quản lý artifact, giúp host thêm khả năng mở rộng mà không biến compiler thành một nguồn trạng thái không kiểm soát.