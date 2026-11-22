# Compiler API: Cấu hình encoding, classpath và vị trí đầu ra

## Mục tiêu bài học

Khi biên dịch mã Java ngay trong ứng dụng bằng **Java Compiler API**, ba cấu hình cần được kiểm soát rõ ràng là:

1. **Encoding**: trình biên dịch giải mã byte của tệp nguồn **.java** bằng bảng mã nào.
2. **Classpath**: trình biên dịch tìm các lớp, giao diện và thư viện phụ thuộc ở đâu.
3. **Vị trí đầu ra**: các tệp **.class** sau biên dịch được ghi vào thư mục nào.

Sau bài này, bạn sẽ biết cấu hình ba yếu tố trên qua **javax.tools.JavaCompiler**, **StandardJavaFileManager**, và các tùy chọn hiện hành của **javac**; phân biệt đường dẫn lúc biên dịch và lúc chạy; tự chạy một ví dụ Java 17+; cùng cách chẩn đoán những lỗi thường gặp.

**Phạm vi:** Bài tập trung vào Java Compiler API chuẩn vẫn được hỗ trợ trên các JDK hiện đại. Dùng **JDK 17 trở lên** để chạy ví dụ. Những cơ chế build cũ đã ngừng áp dụng không được sử dụng.

## 1. Vì sao phải cấu hình cả ba?

Giả sử ứng dụng có một chương trình Java đọc mã nguồn chứa tiếng Việt, gọi hàm từ thư viện riêng rồi sinh ra bytecode để chạy. Ba cấu hình giải quyết ba câu hỏi khác nhau:

| Cấu hình | Đọc/ghi dữ liệu gì? | Nếu cấu hình sai |
| --- | --- | --- |
| **Encoding** | Byte trong tệp **.java** → ký tự mã nguồn | Ký tự sai, lỗi đọc/biên dịch source hoặc chuỗi văn bản bị biến dạng |
| **Classpath** | Thư mục **.class** và JAR chứa các loại mà source tham chiếu | **package ... does not exist**, **cannot find symbol** dù tệp thư viện có trên máy |
| **Class output** | Thư mục đích của các **.class** mới tạo | Không tạo được file, file nằm sai chỗ hoặc bước chạy không tìm được class |

Một sơ đồ cơ bản:

~~~text
Nguồn .java (UTF-8)
       │
       ▼
JavaCompiler + StandardJavaFileManager
       │                         ▲
       │                         │
       │                  CLASS_PATH: thư mục/JAR
       │                  chứa dependency đã biên dịch
       ▼
CLASS_OUTPUT: thư mục chứa .class
       │
       ▼
Lệnh java -cp ... hoặc runtime module path
       │
       ▼
Chương trình chạy
~~~

**Điểm mấu chốt:** Encoding xác định cách đọc source; classpath xác định **đầu vào phục vụ phân giải type**; class output xác định **đích ghi kết quả**. Chúng là các cấu hình độc lập. Biên dịch thành công cũng **không tự thiết lập runtime classpath** khi chạy bằng một tiến trình JVM khác.

## 2. API hiện đại nên dùng

Các thành phần quan trọng của **javax.tools**:

| API | Vai trò |
| --- | --- |
| **ToolProvider.getSystemJavaCompiler()** | Lấy compiler Java chuẩn khả dụng trong runtime hiện tại |
| **JavaCompiler.getStandardFileManager(...)** | Tạo file manager quản lý mã nguồn, dependency và đích đầu ra |
| **StandardJavaFileManager.getJavaFileObjectsFromPaths(Collection<Path>)** | Chuyển đường dẫn source thành các compilation units |
| **StandardJavaFileManager.setLocationFromPaths(...)** | Gán danh sách đường dẫn cho vị trí **CLASS_PATH**, **CLASS_OUTPUT** hoặc vị trí khác |
| **JavaCompiler.getTask(...).call()** | Tạo rồi thực thi một tác vụ biên dịch với options, diagnostics và source |
| **DiagnosticCollector<JavaFileObject>** | Thu thập lỗi/cảnh báo để giải thích thất bại khi biên dịch |

**Compiler API không đồng nghĩa mọi JVM đều có compiler.** API **java.compiler** có thể hiện diện nhưng implementation **jdk.compiler** không có trong custom runtime image; khi đó **ToolProvider.getSystemJavaCompiler()** có thể trả **null**. Hãy chạy bước biên dịch trong JDK có compiler, hoặc đóng gói module compiler nếu tạo runtime image chuyên biệt.

### Chu trình mẫu

~~~text
1. Lấy JavaCompiler, kiểm tra khác null
2. Tạo DiagnosticCollector
3. Mở StandardJavaFileManager với charset xác định
4. Chỉ định CLASS_PATH và CLASS_OUTPUT
5. Chuyển source .java thành JavaFileObject
6. Tạo CompilationTask, truyền các compiler options
7. Gọi call(), kiểm tra Boolean.TRUE.equals(...)
8. Đọc diagnostics nếu thất bại/có cảnh báo
9. Đóng file manager bằng try-with-resources
~~~

Nên dùng **getTask(...)** khi cần kiểm soát tệp nguồn, file manager, classpath và diagnostics chi tiết. Phương thức **JavaCompiler.run(...)** tồn tại và phù hợp với lời gọi giống CLI đơn giản, nhưng không cho bạn cùng mức điều khiển file manager.

## 3. Encoding: giải mã mã nguồn chính xác

### 3.1. Cần phân biệt những loại encoding nào?

- **Encoding của source** quyết định compiler chuyển byte từ **.java** thành ký tự thế nào; cấu hình bằng **StandardCharsets.UTF_8** ở file manager và/hoặc tùy chọn **-encoding UTF-8**.
- **Encoding của tệp dữ liệu runtime** (CSV, JSON, file cấu hình...) là quyết định độc lập của code đọc/ghi dữ liệu runtime.
- Tệp **.class** là định dạng bytecode nhị phân; chỉ định **-encoding UTF-8** không có nghĩa đầu ra trở thành “tệp class UTF-8”.
- **Encoding của console/terminal** ảnh hưởng việc hiển thị chữ khi chạy chương trình và không thay thế encoding của source.

Trong dự án mới, **UTF-8** là lựa chọn thực tế để giữ ký tự tiếng Việt, ký hiệu Unicode và hành vi nhất quán qua máy phát triển, CI và container. Dù môi trường có mặc định UTF-8, khai báo tường minh vẫn dễ kiểm tra và tái lập.

### 3.2. Đặt encoding khi tạo StandardJavaFileManager

~~~java
// Mảnh mã minh họa, cần JavaCompiler compiler và diagnostics.
try (StandardJavaFileManager fm =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // fm đọc các JavaFileObject từ file hệ thống với UTF-8.
}
~~~

- **StandardCharsets.UTF_8** chỉ định charset cho file manager.
- **Locale.ROOT** tác động ngôn ngữ/locale của diagnostic messages, không phải charset của source.
- **try-with-resources** đóng file manager đúng vòng đời, kể cả khi biên dịch thất bại.

Đây là mảnh code cần import **java.nio.charset.StandardCharsets**, **java.util.Locale**, và các lớp thuộc **javax.tools**; ví dụ chạy đầy đủ có ở mục 6.

### 3.3. Tùy chọn javac tương ứng

~~~bash
javac -encoding UTF-8 --release 17 -d build/classes src/example/Main.java
~~~

Trong **JavaCompiler.getTask(...)**, truyền các tùy chọn compiler dưới dạng danh sách phần tử riêng biệt:

~~~java
// Mảnh mã minh họa:
List<String> options = List.of(
        "--release", "17",
        "-encoding", "UTF-8");
~~~

**Không** truyền cả chuỗi **"-encoding UTF-8"** làm một phần tử vì API nhận các token tùy chọn, không tự tách chuỗi như shell. Nếu vừa truyền charset cho file manager vừa dùng **-encoding**, hãy để chúng nhất quán như ví dụ.

**--release 17** xác định ngôn ngữ, classfile và API nền tảng Java 17 mà mã nguồn được phép dùng. Nó giải quyết tính tương thích phiên bản đích, **không thay thế encoding**. Khi dùng **--release**, không kết hợp đồng thời **-source** và **-target**.

### 3.4. Xử lý lỗi encoding

Nếu source lưu UTF-8 mà compiler giải mã bằng charset khác, bạn có thể gặp lỗi **unmappable character for encoding ...**, ký tự bất hợp lệ hoặc nội dung chuỗi không như mong đợi. Hãy kiểm tra:

1. **Byte thực tế** của file nguồn trong repo/artifact và encoding IDE đã dùng khi lưu.
2. Charset truyền cho file manager; tùy chọn **-encoding** có bị đặt chồng bởi cấu hình khác không.
3. Nếu nguồn được sinh tự động, code tạo file đã ghi đúng charset chưa (ví dụ **Files.writeString(path, text, StandardCharsets.UTF_8)**).
4. Kiểm tra lại đầu ra chương trình trong terminal có hỗ trợ Unicode; đừng nhầm lỗi hiển thị với lỗi biên dịch.

Tránh cách “sửa lỗi” bằng việc bỏ dấu tiếng Việt trong source hoặc thay đổi encoding toàn JVM một cách ngầm định.

## 4. Classpath: nơi tìm các lớp phụ thuộc

### 4.1. Classpath bao gồm những gì?

Khi biên dịch source thông thường trên **classpath** (unnamed module), compiler cần tìm được những class mà source dùng, có thể nằm trong:

- Thư mục chứa cây **package/.../*.class** đã biên dịch.
- Các file **.jar** chứa bytecode của dependency.
- Các vị trí đầu vào đã được tổ chức theo cấu trúc mà compiler hỗ trợ.

Ví dụ source ứng dụng import **example.lib.Message** trong khi class đó nằm ở:

~~~text
build/lib-classes/example/lib/Message.class
~~~

Classpath cần chứa **build/lib-classes**, tức **gốc của cây package**, chứ không trỏ tới **Message.class** hoặc **example/lib/**.

### 4.2. Chỉ định CLASS_PATH trong StandardJavaFileManager

~~~java
// Mảnh mã minh họa, fm là StandardJavaFileManager:
Path compiledLibrary = Path.of("build/lib-classes").toAbsolutePath();
Path thirdPartyJar = Path.of("libs/helper.jar").toAbsolutePath();

fm.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(compiledLibrary, thirdPartyJar));
~~~

- Mỗi **Path** là một thư mục chứa class hoặc JAR phù hợp; truyền **Collection<Path>** giúp khỏi tự ghép chuỗi classpath phụ thuộc hệ điều hành.
- Các vị trí được truyền phải tồn tại và truy cập được theo cách compiler kỳ vọng.
- Gán vị trí **CLASS_PATH** thay thế đường dẫn đã gắn trước đó cho file manager. Với dự án nhiều bước, cần truyền **toàn bộ dependency** của bước hiện tại.
- Nếu không có dependency riêng cho một bước, có thể đặt **List.of()** để classpath của bước đó rỗng; các lớp chuẩn của JDK vẫn được tìm qua cơ chế nền tảng.

Ví dụ chương trình đầy đủ ở mục 6 sẽ biên dịch thư viện trước, sau đó đưa thư mục output của thư viện vào **CLASS_PATH** để biên dịch ứng dụng.

### 4.3. Tùy chọn javac tương ứng

~~~bash
# Bash: Linux/macOS
javac -encoding UTF-8 --release 17 \
    -classpath "build/lib-classes:libs/helper.jar" \
    -d build/app-classes src/app/example/app/Main.java
~~~

~~~powershell
# PowerShell: Windows
javac -encoding UTF-8 --release 17 -classpath "build/lib-classes;libs/helper.jar" -d build/app-classes src/app/example/app/Main.java
~~~

- Đối với classpath **dạng chuỗi** trên Windows, dùng dấu **;** để ngăn cách các mục; trên Linux/macOS dùng **:**.
- Trong chương trình Java tự tạo chuỗi đường dẫn, **File.pathSeparator** hoặc **File.pathSeparatorChar** là lựa chọn phù hợp nền tảng. Khi dùng **setLocationFromPaths(...)** thì không cần tự ghép dấu phân cách.
- Thư mục chứa **source .java** không tự thay thế được thư mục chứa **.class** đã biên dịch.
- **Classpath lúc chạy** do lệnh **java -cp** hoặc môi trường runtime quyết định, có thể khác hoàn toàn với classpath lúc biên dịch.

Nếu ứng dụng dùng **named modules**, không trộn lẫn các khái niệm: dependency của module thường dùng **module path**, **module-info.java**, và khi dùng file manager là các vị trí như **StandardLocation.MODULE_PATH**. Ví dụ trong bài chủ động dùng classpath để tập trung đúng ba cấu hình được yêu cầu.

## 5. Vị trí đầu ra: kiểm soát nơi chứa .class

### 5.1. Đặt CLASS_OUTPUT bằng file manager

~~~java
// Mảnh mã minh họa; directory phải tồn tại trước khi gán:
Path outputDir = Path.of("build/classes").toAbsolutePath();
Files.createDirectories(outputDir);

fm.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT,
        List.of(outputDir));
~~~

**CLASS_OUTPUT** nhận **một thư mục** làm gốc xuất bytecode. Trong trình quản lý file chuẩn, hãy tạo trước thư mục đó. Compiler sẽ tổ chức các class theo package:

~~~text
build/classes/
└── example/
    └── app/
        └── Main.class
~~~

**CLASS_OUTPUT** không phải đường dẫn đến một file **Main.class**, và không phải một danh sách nhiều thư mục. Khi biên dịch nhiều nhóm source ra nhiều thư mục khác nhau, hãy sử dụng các tác vụ/file manager được cấu hình thích hợp cho từng nhóm.

### 5.2. Tùy chọn javac tương ứng và trường hợp cần phân biệt

~~~bash
javac -encoding UTF-8 --release 17 \
    -d build/classes src/example/app/Main.java
~~~

**-d** chỉ đích ghi **.class**. Các tùy chọn/vị trí liên quan nhưng khác chức năng:

| Tùy chọn / Location | Chức năng |
| --- | --- |
| **-d** / **StandardLocation.CLASS_OUTPUT** | Đích xuất file **.class** |
| **-s** / **StandardLocation.SOURCE_OUTPUT** | Đích xuất **.java** do annotation processor tạo, khi dự án có processor |
| **-classpath** / **StandardLocation.CLASS_PATH** | Nơi tìm class/JAR phụ thuộc của bước compile |
| **--module-path** / **StandardLocation.MODULE_PATH** | Nơi tìm module khi biên dịch module |
| **--source-path** / **StandardLocation.SOURCE_PATH** | Nơi tìm thêm source, nếu workflow cần compiler tìm theo đường dẫn nguồn |

File manager không tự tạo **JAR phát hành**, không tự copy resources, không tự dọn các file **.class** cũ và không tự tạo runtime classpath. Các việc đó thuộc build/packaging pipeline (ví dụ Gradle, Maven hoặc công cụ đóng gói riêng).

### 5.3. Vì sao tách output quan trọng?

Một quy trình rõ ràng có thể phân tách:

~~~text
build/tools/       -> lớp của chương trình gọi Compiler API
build/lib-classes/ -> lớp thư viện được biên dịch trước
build/app-classes/ -> lớp ứng dụng sử dụng thư viện
~~~

Lợi ích:

- Dễ kiểm tra bước nào tạo ra file nào.
- Dễ đặt classpath cho bước phụ thuộc tiếp theo.
- Hạn chế làm bẩn thư mục source và tránh vô tình dùng bytecode cũ.
- Thuận tiện cho kiểm thử, đóng gói và xóa sạch output khi cần build tái lập.

Nếu một lần biên dịch thất bại, một số file output trước đó có thể vẫn còn. Hệ thống build nên xử lý dữ liệu đầu ra cũ một cách có chủ đích, nhất là khi có incremental compilation.

## 6. Ví dụ đầy đủ chạy được bằng Java 17+

Ví dụ sau dùng **Compiler API** để biên dịch hai dự án classpath nhỏ:

- **Thư viện**: cung cấp phương thức chứa chuỗi tiếng Việt UTF-8.
- **Ứng dụng**: import thư viện đó và in chuỗi.
- **Bộ điều khiển biên dịch**: cấu hình **UTF-8**, **CLASS_PATH** và **CLASS_OUTPUT** ở cả hai bước.

Ví dụ không yêu cầu framework hay thư viện ngoài JDK. Chạy các lệnh tại thư mục **compiler-config/**.

### 6.1. Cấu trúc trước khi biên dịch

~~~text
compiler-config/
├── CompileProject.java
└── src/
    ├── lib/
    │   └── example/lib/Message.java
    └── app/
        └── example/app/Main.java
~~~

**src/lib/example/lib/Message.java**

~~~java
package example.lib;

public final class Message {
    private Message() {}

    public static String hello() {
        return "Xin chào Java";
    }
}
~~~

**src/app/example/app/Main.java**

~~~java
package example.app;

import example.lib.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.hello());
    }
}
~~~

Lúc này, **Main.java** không thể được biên dịch độc lập nếu compiler không nhìn thấy **example.lib.Message**.

### 6.2. Chương trình điều khiển JavaCompiler

**CompileProject.java** ở thư mục gốc:

~~~java
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

public final class CompileProject {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                "Compiler không có sẵn: cần JDK với module jdk.compiler");
        }

        Path libOut = Path.of("build/lib-classes").toAbsolutePath();
        Path appOut = Path.of("build/app-classes").toAbsolutePath();
        Files.createDirectories(libOut);
        Files.createDirectories(appOut);

        compile(compiler, Path.of("src/lib/example/lib/Message.java"),
                libOut, List.of());
        compile(compiler, Path.of("src/app/example/app/Main.java"),
                appOut, List.of(libOut));

        System.out.println("COMPILE_OK");
    }

    private static void compile(JavaCompiler compiler, Path source,
                                Path output, List<Path> classpath)
            throws IOException {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fm =
                     compiler.getStandardFileManager(
                         diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            fm.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
                    List.of(output));
            fm.setLocationFromPaths(StandardLocation.CLASS_PATH, classpath);

            Iterable<? extends JavaFileObject> units =
                    fm.getJavaFileObjectsFromPaths(List.of(source));

            List<String> options = List.of(
                    "--release", "17", "-encoding", "UTF-8");

            Boolean ok = compiler.getTask(
                    null, fm, diagnostics, options, null, units).call();

            if (!Boolean.TRUE.equals(ok)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    String file = d.getSource() == null
                            ? "<unknown>" : d.getSource().getName();
                    System.err.printf(Locale.ROOT, "%s:%d: %s%n",
                            file, d.getLineNumber(), d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compile failed: " + source);
            }
        }
    }
}
~~~

### 6.3. Đọc đoạn code theo ba cấu hình

**Encoding** được chỉ định ở hai chỗ có cùng giá trị:

~~~java
compiler.getStandardFileManager(
        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);

List<String> options = List.of(
        "--release", "17", "-encoding", "UTF-8");
~~~

**Classpath** của lần biên dịch thư viện là rỗng; ở lần biên dịch ứng dụng, nó chứa thư mục output đã tạo từ bước trước:

~~~java
compile(compiler, Path.of("src/lib/example/lib/Message.java"),
        libOut, List.of());

compile(compiler, Path.of("src/app/example/app/Main.java"),
        appOut, List.of(libOut));
~~~

**Vị trí đầu ra** của hai lần biên dịch là khác nhau:

~~~java
fm.setLocationFromPaths(StandardLocation.CLASS_OUTPUT,
        List.of(output));
~~~

Các mảnh code trong mục 6.3 chỉ dùng để giải thích dòng lệnh trong **CompileProject.java**; không cần tạo thêm file từ chúng.

### 6.4. Biên dịch bộ điều khiển rồi chạy

Trên **Bash (Linux/macOS)**:

~~~bash
mkdir -p build/tools
javac -encoding UTF-8 -d build/tools CompileProject.java
java -cp build/tools CompileProject
java -cp "build/app-classes:build/lib-classes" example.app.Main
~~~

Trên **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force build/tools | Out-Null
javac -encoding UTF-8 -d build/tools CompileProject.java
java -cp build/tools CompileProject
java -cp "build/app-classes;build/lib-classes" example.app.Main
~~~

Với một lần chạy hợp lệ, **lệnh java đầu tiên** (bộ điều khiển Compiler API) ghi stdout:

~~~text
COMPILE_OK
~~~

**Lệnh java thứ hai** (ứng dụng đã được biên dịch) ghi stdout:

~~~text
Xin chào Java
~~~

Không có dòng kết quả thứ ba từ code ví dụ. **javac** không in thông báo thành công theo mặc định.

### 6.5. Kiểm tra cấu trúc sau khi biên dịch

~~~text
compiler-config/
├── build/
│   ├── tools/CompileProject.class
│   ├── lib-classes/example/lib/Message.class
│   └── app-classes/example/app/Main.class
├── CompileProject.java
└── src/...
~~~

Chương trình **CompileProject** được nạp từ **build/tools**. Thư viện **Message.class** và ứng dụng **Main.class** nằm trong hai gốc classpath độc lập. Khi chạy Main, cần cung cấp **cả hai gốc** vì JVM cũng phải tìm được class của thư viện.

**Kết quả đã kiểm chứng:** cấu trúc và chương trình ở trên biên dịch/chạy thành công với OpenJDK 24 bằng đúng API và các lệnh tương ứng.

### 6.6. Thử nghiệm để thấy rõ vai trò từng cấu hình

1. **Bỏ thư viện khỏi compile classpath:** sửa tham số cuối của lần gọi **compile(...)** cho ứng dụng từ **List.of(libOut)** thành **List.of()**. Biên dịch Main thất bại vì compiler không giải quyết được **example.lib.Message**; các diagnostics thường cho biết package không tồn tại/không tìm thấy biểu tượng. Khôi phục tham số sau thử nghiệm.
2. **Bỏ thư viện khỏi runtime classpath:** giữ biên dịch thành công, chỉ chạy **java -cp build/app-classes example.app.Main**. JVM không tìm thấy phụ thuộc **Message** khi thực thi; thường nhận **NoClassDefFoundError** với nguyên nhân sâu liên quan class loading. Bổ sung **build/lib-classes** vào runtime classpath.
3. **Đổi class output:** thay đường dẫn **build/app-classes** bằng **build/new-app-classes**, chạy lại bộ điều khiển rồi dùng đường dẫn mới trong lệnh **java -cp**. Compiler tạo cấu trúc package trong thư mục mới.
4. **Thử nguồn Unicode:** xác nhận **Message.java** được lưu UTF-8 và in **Xin chào Java**. Nếu dùng file có byte được mã hóa khác, hãy sửa encoding thống nhất từ khâu sinh/lưu source đến khâu compiler đọc; không kết luận lỗi chỉ dựa vào cách console hiển thị chữ.

## 7. Quy tắc chẩn đoán và xử lý lỗi thực tế

### 7.1. Khi compiler trả false

**JavaCompiler.CompilationTask.call()** trả **Boolean**. Khi trả **false**, đó là thất bại biên dịch thông thường: cần đọc **DiagnosticCollector**. Đừng chỉ in **Compilation failed** mà bỏ mất vị trí và nguyên nhân.

Thông tin nên ghi cho từng diagnostic:

- **kind**: ERROR, WARNING hoặc loại thông báo khác.
- **source**: tệp nguồn gây lỗi, nếu có.
- **line/column**: số dòng và cột, có thể không khả dụng với một số diagnostic.
- **message**: mô tả lỗi theo locale cụ thể.
- **compiler options và các đường dẫn liên quan**: chỉ in phần không nhạy cảm, phù hợp quyền chẩn đoán.

Mã ví dụ đầy đủ đã xử lý trường hợp lỗi bằng **Boolean.TRUE.equals(ok)** và thông báo file/dòng. Với ứng dụng production, nên trả kết quả lỗi có cấu trúc thay vì chỉ in stderr; kiểm soát các đường dẫn/chuỗi có thể chứa dữ liệu nhạy cảm.

### 7.2. Khi gặp ngoại lệ trong quá trình cấu hình

Một số sai sót xuất hiện **trước khi** gọi **call()**:

| Vấn đề | Điểm kiểm tra | Hướng xử lý |
| --- | --- | --- |
| **ToolProvider.getSystemJavaCompiler() == null** | Runtime không cung cấp Java compiler | Dùng JDK phù hợp hoặc đưa module compiler vào runtime image |
| **setLocationFromPaths(CLASS_OUTPUT, ...)** thất bại | Đích không tồn tại, không phải thư mục hoặc không truy cập được | Tạo thư mục trước; kiểm tra quyền và đường dẫn |
| **IOException** khi đọc source/ghi output | File bị thiếu, quyền/đĩa có vấn đề | Ghi nguyên nhân theo đường dẫn, xử lý lỗi I/O rõ ràng |
| **IllegalArgumentException** với options/location | Truyền tùy chọn không hỗ trợ, tham số hoặc dạng đường dẫn sai | Kiểm tra danh sách options, API và JDK đang chạy |
| **call() == false** | Compiler tìm thấy lỗi trong source hoặc tham chiếu | Đọc diagnostics; kiểm tra encoding, classpath, source |
| **Runtime ClassNotFoundException / NoClassDefFoundError** | JVM khi chạy không thấy class cần thiết | Kiểm tra classpath/module path lúc chạy, không chỉ lúc biên dịch |

Đừng dùng **catch (Throwable)** để che toàn bộ lỗi compiler. Phân biệt lỗi cấu hình file manager, lỗi I/O và lỗi Java source giúp hệ thống báo cáo chính xác.

### 7.3. Bảng quyết định nhanh

| Triệu chứng | Khả năng chính | Cần làm |
| --- | --- | --- |
| Text tiếng Việt biến dạng hoặc lỗi ký tự | Source encoding và compiler encoding không khớp | Kiểm tra byte source, editor, **-encoding**, file manager charset |
| **package x does not exist** | Thiếu class/JAR trên **CLASS_PATH** của tác vụ | Kiểm tra output dependency và classpath gốc package |
| **cannot find symbol** với class đã build | Sai package/tên class, thiếu hoặc sai dependency | Kiểm tra import, phiên bản dependency và artifact thực tế |
| Compile OK nhưng **NoClassDefFoundError** lúc chạy | Runtime classpath thiếu dependency | Cung cấp đủ thư mục/JAR trong **java -cp** |
| **.class** xuất hiện gần source, không ở build | Đích output không được chỉ định đúng | Dùng **CLASS_OUTPUT** hoặc **-d** |
| File đầu ra không tạo được | Thư mục, quyền file hoặc dung lượng có vấn đề | Tạo output directory và xử lý IOException |
| Dùng API Java mới hơn mức đích | **--release** nhỏ hơn API mà code sử dụng | Chỉ dùng API có trên release mục tiêu, hoặc thay đổi mục tiêu theo yêu cầu sản phẩm |
| Kết quả biên dịch lúc đúng lúc sai giữa CI và máy cá nhân | Dựa vào classpath/charset mặc định, output còn dữ liệu cũ | Khai báo tường minh charset, dependency, output và dọn artifact theo build lifecycle |

### 7.4. Giữ cấu hình tái lập và an toàn

- Dùng đường dẫn bắt nguồn từ **workspace/base directory** đã xác định, tránh tùy tiện phụ thuộc vào working directory của tiến trình hosting.
- Chuẩn hóa đường dẫn bằng **Path.toAbsolutePath().normalize()** khi cần log, so sánh hoặc xây dựng file manager; kiểm tra tồn tại và quyền đọc/ghi trước bước nặng.
- Chỉ cho phép các thư mục/JAR nằm trong tập dependency được phê duyệt; không tự tải hoặc biên dịch mã nguồn không tin cậy cùng quyền với ứng dụng chính.
- Một tác vụ biên dịch nên có source, classpath, output và options xác định; tạo task mới cho mỗi lần biên dịch. Không tái sử dụng cùng một **CompilationTask** để gọi **call()** nhiều lần.
- Đóng **StandardJavaFileManager** sau khi xong. Có thể tổ chức chia sẻ file manager theo một lifecycle được thiết kế, nhưng phải quản lý tài nguyên, cache và đồng thời cẩn thận.
- Khi cần annotation processors, cấu hình đường dẫn processor và **SOURCE_OUTPUT** riêng theo mục tiêu; đừng nhầm **classpath của ứng dụng** với nơi tìm processor. Các thiết lập processor phải tương thích với chính sách bảo mật và build của dự án.
- Kiểm thử bằng **JDK/--release** và cách đóng gói được dùng ở môi trường đích; một lần chạy ví dụ trên máy cá nhân không chứng minh mọi dependency hoặc phiên bản JDK sẽ tương thích.

## 8. Checklist áp dụng

Trước khi tích hợp JavaCompiler vào một công cụ hoặc hệ thống build riêng, xác nhận:

- **Nguồn:** những file **.java** nào được biên dịch; chúng thực sự dùng encoding nào?
- **Charset:** file manager có được tạo với **UTF-8** (hoặc charset đúng theo dữ liệu) và options có thống nhất?
- **Dependencies:** classpath chứa đúng thư mục gốc của package và mọi JAR cần thiết cho bước compile?
- **Modules:** nguồn là classpath hay named module; có dùng đúng classpath/module path?
- **Đầu ra:** **CLASS_OUTPUT** là một directory đã có quyền ghi; có tách source và generated bytecode?
- **Tương thích:** có chỉ định **--release** phù hợp với runtime mục tiêu?
- **Diagnostics:** có kiểm tra kết quả **call()**, thông báo lỗi có file/dòng và loại lỗi, giữ chi tiết phù hợp?
- **Runtime:** sau khi compile, lệnh chạy có classpath/module path chứa toàn bộ class và dependency cần thiết?
- **Build vệ sinh:** có chiến lược dọn output cũ để không vô tình dùng class stale?

## 9. Bài tập tự luyện

1. Bổ sung một JAR hợp lệ vào **CLASS_PATH** của bước biên dịch ứng dụng và gọi một API từ JAR. Đảm bảo JAR đó có mặt cả ở runtime classpath.
2. Đổi class output của thư viện thành **build/common-classes** và cập nhật đúng duy nhất các vị trí phụ thuộc. Giải thích vì sao không cần sửa **import example.lib.Message**.
3. Thay **--release 17** bằng một mức release phù hợp JDK hiện tại và runtime mục tiêu. Thử gọi một API chưa tồn tại trong release mục tiêu rồi quan sát compiler diagnostics.
4. Dùng **Files.writeString(..., StandardCharsets.UTF_8)** để tạo source có tiếng Việt tự động; biên dịch qua Compiler API và kiểm tra stdout không bị mất dấu.
5. Viết kiểm thử cho hai tình huống: compile thiếu dependency phải thất bại có diagnostic, compile đúng phải tạo file **Main.class** ở **CLASS_OUTPUT** chỉ định.

## Kết luận

Trong Java Compiler API, cấu hình ba yếu tố theo một hợp đồng rõ ràng:

**UTF-8 ở file manager và compiler options → CLASS_PATH chứa dependency đúng cho từng tác vụ → CLASS_OUTPUT là thư mục bytecode xác định.**

Sau khi biên dịch, **runtime classpath hoặc module path** là cấu hình độc lập cần được thiết lập cho chương trình chạy. Khi có lỗi, hãy kiểm tra đúng lớp vấn đề: byte source, đường dẫn dependency, quyền/vị trí output và diagnostics. Việc định nghĩa tường minh các tham số này giúp quá trình build dễ tái lập, dễ kiểm thử và dễ chẩn đoán trên những JDK hiện đại.

**Tài liệu tham khảo chính thức:**

- [JavaCompiler — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [StandardJavaFileManager — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html)
- [StandardLocation — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardLocation.html)
- [javac: -encoding, -classpath, -d, --release — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)