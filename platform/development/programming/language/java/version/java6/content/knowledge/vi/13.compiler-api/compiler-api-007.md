# Giới hạn phiên bản ngôn ngữ theo compiler đang sử dụng: JavaCompiler API và --release

## 1. Vấn đề cần giải quyết

Trong một dự án Java hiện đại, **JDK dùng để biên dịch** có thể mới hơn **phiên bản Java mà ứng dụng cần hỗ trợ khi chạy**. Ví dụ, công cụ build chạy với JDK 21 nhưng sản phẩm phải chạy trên Java 17. Nếu không khóa phiên bản tương thích, mã nguồn có thể vô tình sử dụng cú pháp hoặc API chỉ có ở JDK mới, khiến hệ thống triển khai không chạy được.

Java có hai cách gọi trình biên dịch thường gặp:

- Dòng lệnh `javac`.
- **Java Compiler API** trong `javax.tools`, gồm `ToolProvider.getSystemJavaCompiler()`, `JavaCompiler.getTask(...)`, `DiagnosticCollector` và `StandardJavaFileManager`.

Cả hai cách đều chịu một giới hạn căn bản: **trình biên dịch cụ thể chỉ hiểu những phiên bản ngôn ngữ và target mà chính nó hỗ trợ**. Compiler chạy trên JDK 17 không thể biên dịch cú pháp chỉ xuất hiện trong Java 21. Compiler JDK 21 thường có thể biên dịch mã tương thích Java 17 nếu sử dụng lựa chọn `--release 17`. Tuy nhiên, một compiler mới **không bắt buộc hỗ trợ mọi phiên bản Java cũ**; phải xem danh sách `--release` mà compiler đó công bố.

Mục tiêu bài học:
1. Phân biệt phiên bản **compiler/JDK đang chạy**, cú pháp **source**, **bytecode target** và **Java SE API**.
2. Chọn `--release` để giới hạn đồng thời ngôn ngữ, bytecode và API nền tảng.
3. Truyền cấu hình phiên bản qua `JavaCompiler.getTask(...)`; quan sát lỗi bằng diagnostics.
4. Dùng `SourceVersion` đúng mục đích mà không suy đoán sai về các release hỗ trợ.
5. Đưa cấu hình vào Gradle/Maven và kiểm tra artifact chạy trên runtime đích.

Nội dung sử dụng các API và tùy chọn **vẫn được hỗ trợ trên Java hiện đại**; ví dụ thao tác trực tiếp trên JDK 17 trở lên.

## 2. Bốn lớp phiên bản khác nhau

| Lớp phiên bản | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **JDK/compiler thực tế** | `javac 21`, `javac 25` | Trình biên dịch được gọi, quyết định cú pháp và release mà công cụ *có khả năng* xử lý. |
| **Source language level** | `--source 17` | Bộ quy tắc cú pháp/ngữ nghĩa ngôn ngữ Java áp dụng cho source. |
| **Target class-file level** | `--target 17` | Phiên bản định dạng `.class` mà compiler phát ra; không tự khóa API thư viện được gọi. |
| **Nền tảng Java API** | `--release 17` | Giới hạn API Java SE/JDK công khai và hai lớp source/target theo Java 17. |

Ví dụ, JDK 21 có `Stream.toList()` và hỗ trợ record, nhưng JDK 11 không có hai tính năng đó. Khi cần phát hành ứng dụng chạy trên Java 11, chỉ tạo file class có phiên bản bytecode Java 11 là **chưa đủ**. Mã còn phải tránh gọi API Java được bổ sung sau Java 11.

Các câu hỏi khác nhau cần câu trả lời khác nhau:

- **Máy đang dùng compiler nào?** Chạy `javac -version`, kiểm tra Java toolchain trong build hoặc lấy compiler thật được cung cấp cho process.
- **Compiler này hỗ trợ source phiên bản nào?** Đọc các lựa chọn của `javac --help` và thông tin `JavaCompiler.getSourceVersions()`.
- **Compiler này còn hỗ trợ `--release 11` không?** Xem danh sách target `--release` ở `javac --help` hoặc thử cấu hình trên compiler đó.
- **JAR sau biên dịch chạy được trên Java 17 không?** Kiểm tra source/API/bytecode và cả dependencies, rồi chạy integration/smoke test với đúng JRE/JDK 17.

`java -version` cho biết JVM mà lệnh `java` đang gọi. Nó **không bảo đảm** `javac` trong `PATH`, Gradle toolchain hoặc compiler nhúng trong IDE là cùng phiên bản; hãy xác minh đúng compiler thực thi tác vụ.

## 3. Vì sao ưu tiên --release

Khi biên dịch cho Java 17 bằng một compiler mới hơn, cấu hình được khuyến nghị là:

```bash
javac --release 17 -d out src/demo/App.java
```

Ở đây, `out` là thư mục chứa class output, và `src/demo/App.java` là ví dụ đường dẫn source trong dự án. Tùy chọn `--release 17` buộc compiler:

1. Kiểm tra **cú pháp và ngôn ngữ** theo Java 17.
2. Tạo **class file phù hợp Java 17**.
3. Chỉ cho phép dùng **API nền tảng Java SE/JDK được công bố cho Java 17**, không vô tình tham chiếu API JDK mới hơn.

Trong khi đó, chỉ đặt:

```bash
javac -source 17 -target 17 -d out src/demo/App.java
```

không phải cách bảo đảm đầy đủ mức API. `-source` điều khiển cú pháp, còn `-target` điều khiển class-file version. Nếu thiếu cấu hình platform API tương ứng, javac chạy trên JDK mới có thể chấp nhận các API nền tảng mới rồi tạo bytecode cũ. Khi chuyển sang runtime cũ, ứng dụng có nguy cơ lỗi như `NoSuchMethodError` hoặc `NoClassDefFoundError`.

**Quy tắc:** Khi hỗ trợ một Java release cụ thể trên compiler có hỗ trợ release đó, ưu tiên **`--release N`**. Không kết hợp `--release` với `--source` hoặc `--target` trong cùng lần biên dịch; javac không cho phép kết hợp này.

Bảng quyết định:

| Mục tiêu | Cấu hình |
| --- | --- |
| Biên dịch với JDK 21 nhưng hỗ trợ chạy trên Java 17 | `--release 17` |
| Biên dịch với JDK 17 cho chính Java 17, cần khóa target rõ ràng | `--release 17` |
| Kiểm tra cú pháp Java 11 trên JDK hỗ trợ Java 11 | `--release 11` (khóa cả API và bytecode) |
| Kiểm tra tính năng chỉ có ở Java 21 nhưng compiler là JDK 17 | **Không làm được trên compiler này**; cần compiler có hỗ trợ source Java 21. |
| Nhắm đến một release cũ bị compiler hiện tại ngừng hỗ trợ | Dùng toolchain/compiler khác còn hỗ trợ release mục tiêu; không ép `--release` với giá trị không hợp lệ. |

**Không có "biên dịch tương lai":** một JDK không thể hiểu và hỗ trợ đầy đủ cú pháp của release tương lai mà nó chưa triển khai. Ví dụ, đặt `--release 25` trên JDK 17 không tạo ra compiler Java 25.

## 4. Compiler API nhận giới hạn phiên bản ở đâu?

Java Compiler API tiêu chuẩn:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
```

Snippet trên nằm trong phương thức Java; biến `compiler` có thể là `null` nếu môi trường chạy không có compiler, chẳng hạn runtime image không chứa module `jdk.compiler`. Hãy phát hiện trường hợp này và thông báo rõ ràng; không mặc định mọi Java runtime đều có javac.

Sau khi có compiler, `getTask` tạo một tác vụ biên dịch:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null,          // Writer cho thông tin khác nếu cần
        fileManager,   // JavaFileManager
        diagnostics,   // DiagnosticListener
        List.of("--release", "17", "-d", outputDir.toString()),
        null,          // classes dùng cho annotation processing riêng, nếu có
        sources        // Các JavaFileObject của source
);

boolean ok = Boolean.TRUE.equals(task.call());
```

Đây là snippet giải thích API: `fileManager`, `diagnostics`, `outputDir` và `sources` cần tồn tại trước khi gọi. Trong `getTask`, tham số `options` nhận **từng token đúng như option của javac**, ví dụ `"--release", "17"`. Gọi `task.call()` thực hiện biên dịch và trả về `Boolean` báo thành công/thất bại; lỗi cú pháp/API thường xuất hiện qua `DiagnosticCollector` khi được cung cấp.

`JavaCompiler` là API yêu cầu compiler trên JVM; nó **không tự tải thêm một JDK** để biên dịch release không hỗ trợ. Nếu chọn source release không hợp lệ, compiler có thể báo option invalid hoặc ném ngoại lệ về cấu hình; trường hợp này cần xử lý riêng với lỗi source Java thông thường.

## 5. Ví dụ Java 17+ chạy được: một compiler, hai target release

Ví dụ dưới đây dùng **Compiler API thật** để biên dịch Java source từ chuỗi trong bộ nhớ, sau đó kiểm tra hai trường hợp:

- **Cú pháp:** `record` được hỗ trợ từ Java 16; chạy với `--release 17` sẽ thành công, còn `--release 11` thất bại.
- **API nền tảng:** `Stream.toList()` được bổ sung ở Java 16; chạy với `--release 17` thành công, còn `--release 11` thất bại, dù cú pháp nguồn không có cấu trúc quá mới.

Ví dụ yêu cầu **JDK có compiler hỗ trợ cả `--release 11` lẫn `--release 17`** (đã kiểm tra hành vi trên JDK 24). Nếu chạy trên JDK khác, xác minh hai release này trong `javac --help` trước. Không cần thiết phải cài riêng Java 11.

Tạo một file tên **`CompilerVersionDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompilerVersionDemo {

    // Một source file "ảo" để đưa nội dung Java từ String vào compiler.
    static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String type, String text) {
            super(
                URI.create("string:///" + type + Kind.SOURCE.extension),
                Kind.SOURCE
            );
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    static boolean compile(
            JavaCompiler compiler,
            String release,
            JavaFileObject source) throws IOException {

        Path dir = Files.createTempDirectory("compiler-release-");
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            var task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of(
                            "--release", release,
                            "-d", dir.toString(),
                            "-proc:none"
                    ),
                    null,
                    List.of(source)
            );

            // false khi source không đạt yêu cầu của release.
            return Boolean.TRUE.equals(task.call());
        } finally {
            // Xóa class files và thư mục tạm sau phép thử.
            try (var paths = Files.walk(dir)) {
                for (Path path :
                        paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "No Java compiler: use a JDK with jdk.compiler");
        }

        JavaFileObject recordSource = new Source(
                "Point",
                "public record Point(int x, int y) {}"
        );

        JavaFileObject apiSource = new Source(
                "ModernApi",
                "public class ModernApi { "
                + "public static int count() { "
                + "return java.util.stream.Stream.of(1, 2).toList().size(); "
                + "} }"
        );

        System.out.println(
                "record@17=" + compile(compiler, "17", recordSource));
        System.out.println(
                "record@11=" + compile(compiler, "11", recordSource));
        System.out.println(
                "streamApi@17=" + compile(compiler, "17", apiSource));
        System.out.println(
                "streamApi@11=" + compile(compiler, "11", apiSource));
    }
}
```

**Chú ý:** chương trình có `throws IOException` ở `main` và `compile`. Các option minh họa đã được kiểm tra trước; để đơn giản, ví dụ không xử lý mọi lỗi cấu hình compiler ngoài `IOException`. Khi dùng trong dịch vụ thật, nên phân biệt lỗi option và lỗi source.

Biên dịch và chạy:

```bash
javac CompilerVersionDemo.java
java CompilerVersionDemo
```

**Stdout chính xác**, khi compiler hỗ trợ hai release đích:

```text
record@17=true
record@11=false
streamApi@17=true
streamApi@11=false
```

Giải thích chi tiết:
1. `recordSource` sử dụng `record`, cú pháp Java 16+. Compiler dưới `--release 17` chấp nhận; dưới `--release 11` từ chối.
2. `apiSource` chỉ dùng cú pháp thông thường, nhưng gọi `Stream.toList()`. Java 11 chưa có phương thức này; `--release 11` kiểm tra API nền tảng và từ chối dù source không có `record`.
3. `DiagnosticCollector` nhận lỗi biên dịch; ở đây program chỉ in trạng thái thành công/thất bại để output ổn định giữa hệ điều hành và locale. Trong ứng dụng thật, dùng `diagnostics.getDiagnostics()` để hiển thị mã, vị trí và thông điệp lỗi.
4. Mỗi phép thử ghi class (khi thành công) vào thư mục tạm khác nhau dưới hệ thống; `finally` dọn thư mục sau từng task. `-proc:none` tắt annotation processing nhằm giữ thử nghiệm tập trung vào source/API.
5. Java code của chương trình kiểm tra chạy trên JDK 17+; **source được kiểm tra** lại tuân theo release tương ứng qua option, nên không có mâu thuẫn giữa `toList()` trong tool và `toList()` của target.

### 5.1. Nếu muốn xem lỗi thay vì chỉ in true/false

Thay nội dung xử lý lỗi của `compile` bằng đoạn sau **bên trong block đang có biến `diagnostics`**:

```java
boolean success = Boolean.TRUE.equals(task.call());
if (!success) {
    for (var d : diagnostics.getDiagnostics()) {
        if (d.getKind() == javax.tools.Diagnostic.Kind.ERROR) {
            System.out.println(
                d.getKind() + " line=" + d.getLineNumber()
                + " code=" + d.getCode()
            );
        }
    }
}
return success;
```

Đây **không phải chương trình độc lập** và nếu áp dụng sẽ có thêm stdout so với kết quả bốn dòng ở trên. Mã lỗi/line number cụ thể có thể khác theo compiler, source và JDK; không hard-code nội dung message của javac vào kiểm thử có tính di động.

## 6. SourceVersion cho biết điều gì, và không cho biết điều gì?

Các API liên quan:

```java
import javax.lang.model.SourceVersion;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler != null) {
    System.out.println(compiler.getSourceVersions());
}
System.out.println(SourceVersion.latestSupported());
```

Đây là snippet đặt trong phương thức Java. Kết quả phụ thuộc JDK/compiler đang chạy, vì vậy không có một stdout cố định cho mọi môi trường.

Phân biệt:

| API | Kết quả | Cách dùng phù hợp |
| --- | --- | --- |
| `JavaCompiler.getSourceVersions()` | Tập `SourceVersion` mà implementation compiler tuyên bố hỗ trợ. | Tìm hiểu giới hạn **ngôn ngữ nguồn** của compiler đang dùng. |
| `SourceVersion.latestSupported()` | Source version mới nhất được hỗ trợ đầy đủ bởi **môi trường thực thi hiện tại**. | Tham khảo khả năng xử lý ngôn ngữ của môi trường/tool đang chạy. |
| `SourceVersion.latest()` | Source version mới nhất mà API có thể **mô hình hóa**. | Không đồng nhất với release javac có thể tạo class cho runtime đích. |
| `javac --help` | Các option/giá trị release mà **javac cụ thể** công bố. | Xác minh `--release N`, `--source N`, `--target N` được hỗ trợ. |

**Điểm tinh tế:** `getSourceVersions()` và `SourceVersion.latestSupported()` **không phải danh sách bảo đảm** mọi giá trị `--release N` có thể tạo output. `--release` còn phụ thuộc compiler có chứa thông tin API/target thích hợp của từng bản Java. Một compiler có thể hiểu cú pháp của release nhưng không duy trì dữ liệu cross-compilation cho tất cả bản cũ. Khi thiết kế UI cho người dùng chọn Java target, cần lấy phạm vi giá trị được compiler/build tool hỗ trợ thật và xử lý lỗi cấu hình.

Ngoài ra:
- Không hard-code enum như `SourceVersion.RELEASE_25` trong code phải **biên dịch bằng JDK 17**, vì enum hằng này chưa tồn tại ở JDK 17.
- `SourceVersion.RELEASE_17` là hằng thích hợp khi compiler/API ở mức Java 17+, nhưng điều đó không thay thế bước xác minh `--release 17`.
- Muốn kiểm tra class file phát ra, dùng `javap -verbose` trên artifact; không suy đoán chỉ từ cấu hình IDE.

## 7. Thấy rõ khác biệt giữa giới hạn cú pháp và giới hạn API

Đây là file `ModernApi.java` dùng ngôn ngữ khá đơn giản nhưng gọi phương thức chỉ có từ Java 16:

```java
import java.util.stream.Stream;

public class ModernApi {
    public static void main(String[] args) {
        System.out.println(Stream.of("a", "b").toList());
    }
}
```

Trên một JDK hỗ trợ cả Java 11 và Java 17, chạy:

```bash
javac --release 17 ModernApi.java
```

sẽ thành công. Nhưng:

```bash
javac --release 11 ModernApi.java
```

sẽ **thất bại khi biên dịch**, do `Stream.toList()` chưa thuộc API của Java 11. Thông điệp lỗi chính xác phụ thuộc phiên bản compiler.

Nếu thay bằng `-source 11 -target 11` trên compiler JDK mới mà không cung cấp API nền tảng Java 11 thích hợp, có thể compiler vẫn cho biên dịch `Stream.toList()` thành class-file Java 11. Khi chạy bằng Java 11, bytecode gọi một phương thức không tồn tại trong Java 11, có thể gây `NoSuchMethodError`. Đây là lý do **bytecode version tương thích không đồng nghĩa với tương thích API**.

Trong ví dụ này, nếu compiler JDK đã báo error, không tiếp tục chạy file `ModernApi.class` cũ còn tồn tại trên đĩa từ lần biên dịch trước. Nên dùng thư mục build sạch hoặc output directory tách biệt để không kiểm tra nhầm artifact cũ.

## 8. Tích hợp mức Java trong Gradle và Maven

### 8.1. Gradle Java toolchain và release

Trong Gradle Groovy DSL, ví dụ build bằng **JDK 21 compiler** nhưng phát hành class tương thích **Java 17**:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Đây là nội dung `build.gradle`, không phải Java code. Hai cấu hình giải quyết **hai việc khác nhau**:
- `toolchain.languageVersion = 21` yêu cầu Gradle chọn JDK 21 làm compiler, miễn là toolchain này có sẵn hoặc Gradle được cấu hình để cấp phát nó.
- `options.release = 17` truyền ý định biên dịch tương thích Java 17 vào javac.

Nếu dự án chạy unit test hoặc công cụ code generation, hãy kiểm tra JDK dùng cho **các task khác** (đặc biệt test runtime và plugin/annotation processor). `options.release` cho `JavaCompile` không tự đổi JVM chạy test/application sang Java 17; cần thêm test đúng trên runtime target.

Không nên đặt đồng thời `options.release = 17` với những option javac mâu thuẫn như `--source 21` hoặc `--target 21`.

### 8.2. Maven Compiler Plugin

Với Maven Compiler Plugin hiện đại, có thể đặt trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Mục đích là yêu cầu Maven Compiler Plugin truyền cấu hình tương đương `--release 17` khi compiler hỗ trợ. **Phiên bản Java dùng để chạy Maven/compiler** vẫn phải được quản lý riêng qua JDK trong CI hoặc Maven toolchain. Đừng cho rằng đặt property trên tự tải hoặc tự chuyển sang JDK 17.

### 8.3. IDE và CI/CD

Một bản build có thể thành công trong IDE nhưng fail trên CI, hoặc ngược lại, nếu compiler khác nhau. Với một pipeline có nhiều môi trường:

1. Ghi rõ runtime tối thiểu cần hỗ trợ, ví dụ Java 17.
2. Cố định JDK/toolchain dùng để compile và `release` được chọn.
3. In/log compiler/JDK thực tế ở CI (`javac -version`, `java -version` hoặc toolchain metadata).
4. Biên dịch bằng `--release 17` và chạy test/smoke test trên Java 17 thật.
5. Kiểm tra các thư viện bên ngoài: `--release` giới hạn **JDK platform API** chứ không bắt thư viện bên thứ ba phải tương thích với Java 17. Một dependency được biên dịch cho Java 21 vẫn có thể khiến runtime Java 17 báo lỗi class-file version.

Với project nhiều module, áp dụng mức release phù hợp cho từng module. Nếu module API phải chạy trên Java 17 còn module ứng dụng yêu cầu Java 21, đừng tự động nâng release của module API lên 21 chỉ vì ứng dụng dùng compiler mới.

## 9. Kiểm tra phiên bản class file sau build

Bytecode format có version riêng (class-file major version). Ví dụ:

| Java release đích | Class-file major version |
| --- | ---: |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Sau khi build, kiểm tra:

```bash
javap -verbose -classpath out demo.App
```

hoặc dùng `javap -verbose ModernApi.class` nếu có file class từ một lần biên dịch thành công. Trong output, tìm `major version: 61` với class file Java 17. Cú pháp `javap` ở trên giả định class tồn tại và đúng đường dẫn output.

**Giới hạn:** `major version: 61` xác nhận mức bytecode nhưng **không tự chứng minh** code chỉ dùng API Java 17 hoặc mọi dependency đều tương thích. Phải kết hợp `--release`, kiểm tra dependency và kiểm thử runtime đích.

## 10. Các trường hợp đặc biệt

**Preview language features.** `--enable-preview` chỉ hỗ trợ preview của release hiện tại mà compiler đang chạy, với `-source` hoặc `--release` phù hợp. Không dùng preview ở JDK 21 rồi hy vọng `--release 17` có thể biên dịch/tạo class chạy trên Java 17. Preview có ràng buộc biên dịch và runtime riêng; muốn phát hành sản phẩm ổn định, ưu tiên tính năng đã hoàn thiện ở release tối thiểu được hỗ trợ.

**Không tự kéo API ứng dụng xuống phiên bản đích.** `--release` bảo vệ việc gọi API nền tảng Java, không tự kiểm tra hành vi triển khai, JNI, reflection, native dependencies hoặc phiên bản thư viện bên thứ ba. Ứng dụng vẫn cần test trên runtime mục tiêu.

**JDK chạy JavaCompiler API thiếu compiler.** `ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi runtime image không chứa module `jdk.compiler`. Chạy ứng dụng sinh mã/biên dịch động cần JDK/runtime image có công cụ phù hợp. `java.compiler` chứa interface API, còn `jdk.compiler` cung cấp compiler implementation của OpenJDK/JDK thông thường.

**Compiler khác với JVM đang chạy tool.** Dù Java Compiler API mặc định trả compiler đi kèm runtime hiện tại, build tool/IDE có thể chọn compiler JDK khác qua toolchain hoặc tiến trình riêng. Chỗ duy nhất xác nhận được target thực tế là tác vụ build chạy với toolchain nào, option gì, và artifact tạo ra ra sao.

**Release không được hỗ trợ.** Nếu yêu cầu một release ngoài phạm vi compiler, đây là lỗi cấu hình, không nên tự sửa thành "latest" rồi bỏ qua chính sách tương thích. Báo rõ compiler version, requested release và cách chọn toolchain đúng.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `error: release version ... not supported` | Compiler quá cũ đối với target mới, hoặc compiler hiện tại không hỗ trợ bản target đó. | Kiểm tra `javac -version` và danh sách `--release`; đổi JDK toolchain hoặc chọn release được hỗ trợ theo yêu cầu sản phẩm. |
| `record is not supported in -source 11` | Dùng cú pháp sau Java 11 nhưng target đang khóa Java 11. | Viết lại theo cú pháp hỗ trợ hoặc nâng target khi sản phẩm cho phép. |
| `cannot find symbol: method toList()` khi biên dịch `--release 11` | API này chưa tồn tại trong Java 11. | Dùng API có ở target, hoặc cập nhật runtime tối thiểu. |
| `UnsupportedClassVersionError` khi chạy | Một class/dependency có major version cao hơn runtime. | Kiểm tra artifact và dependency; biên dịch theo release thực sự hỗ trợ. |
| `NoSuchMethodError` khi chạy Java cũ | Bytecode gọi API không có ở runtime hoặc dependency version khác. | Kiểm tra `--release`, API và dependency thực tế; test trên target JRE. |
| JavaCompiler API trả `null` | Runtime không có system compiler. | Dùng JDK/runtime image có `jdk.compiler` hoặc bố trí compiler phù hợp. |
| Biên dịch pass ở IDE, CI fail | JDK, compiler options và dependencies khác nhau. | Khóa toolchain, đối chiếu `java/javac -version` và build logs. |
| `getSourceVersions()` có release nhưng `--release N` không chấp nhận | Danh sách ngôn ngữ và dữ liệu cross-compilation không phải cùng một hợp đồng. | Xác minh option/value theo compiler thực tế thay vì dựa riêng vào enum. |
| Test vẫn chạy class cũ sau lần compile thất bại | Output cũ chưa bị xóa. | Build sạch hoặc tách output directories; chỉ chạy artifact của lần compile thành công. |

## 12. Ghi nhớ

- **Phiên bản compiler** là giới hạn trên của cú pháp/ngữ nghĩa mà trình biên dịch có thể hiểu; không thể hỗ trợ source release ở tương lai chỉ bằng cách đổi option.
- **`--release N`** là lựa chọn phù hợp để biên dịch cho một Java release cũ được compiler hỗ trợ: khóa **ngôn ngữ + bytecode + API nền tảng**.
- **`-source N` và `-target N`** chỉ giải quyết hai khía cạnh đầu; cần lưu ý API nền tảng khi biên dịch bằng JDK mới.
- **`JavaCompiler.getTask`** chuyển option như `"--release", "17"` vào compiler; `DiagnosticCollector` giúp quan sát các lỗi thực tế.
- **`SourceVersion` và `getSourceVersions`** hỗ trợ mô tả/kiểm tra phiên bản ngôn ngữ, không thay thế kiểm tra danh sách `--release`.
- Tính tương thích cuối cùng cần **compiler đúng + dependency đúng + runtime test thực tế**.

## 13. Tài liệu chính thức

- [Oracle JDK 25: javac command — --release, --source, --target](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Java SE 17: javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [Java SE 17: javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html).
- [Java SE 25: javax.lang.model.SourceVersion](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/SourceVersion.html).
- [Gradle: Java toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- [Gradle: Java plugin --release](https://docs.gradle.org/current/userguide/building_java_projects.html#sec:java_cross_compilation).
- [Maven Compiler Plugin: setting the --release option](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html).
