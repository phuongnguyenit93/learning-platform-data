# Tìm và gọi công cụ bằng java.util.spi.ToolProvider (Java 9+)

## 1. Công cụ nhúng là gì?

Một ứng dụng Java có thể cần chạy các thao tác vốn quen thuộc ở dòng lệnh: biên dịch một tệp `.java` thành `.class` bằng `javac`, đóng gói tập tin thành JAR bằng `jar`, tạo runtime tùy biến bằng `jlink` hoặc gọi công cụ do thư viện cung cấp. Cách truyền thống là tạo một tiến trình hệ điều hành, nhưng với các công cụ **có triển khai SPI phù hợp**, Java cung cấp cách gọi trực tiếp qua **`java.util.spi.ToolProvider`**.

`ToolProvider` là một **giao diện chuẩn trong module `java.base`, xuất hiện từ Java 9**. Nó biểu diễn một công cụ kiểu command-line có tên, nhận danh sách đối số, hai đầu ra bình thường/lỗi và trả về mã trạng thái. Nền tảng thường tìm công cụ thông qua cơ chế **`java.util.ServiceLoader`**.

Luồng sử dụng:

```text
Ứng dụng Java
   |
   | ToolProvider.findFirst("javac")
   v
ServiceLoader: tìm provider có name() = "javac"
   |
   +-- Không có: Optional.empty() → báo thiếu công cụ
   |
   +-- Tìm thấy: ToolProvider
                      |
                      | run(out, err, "-d", "...", "Source.java")
                      v
              Thực thi logic của công cụ
                      |
                      +-- Ghi thông báo vào out / err
                      +-- Trả số nguyên 0 hoặc khác 0
```

Điểm mạnh là **không bắt buộc phải khởi động một JVM mới** chỉ để gọi công cụ. Nhưng hợp đồng API không hứa mọi provider luôn chạy hoàn toàn trong cùng tiến trình: cách triển khai do provider quyết định. Vì thế không coi `ToolProvider` là sandbox, cơ chế timeout hay ranh giới bảo mật.

Trong bài này, trọng tâm là **tìm và gọi công cụ bằng API hiện hành**, xử lý thiếu công cụ, đối số, mã lỗi và điều kiện đóng gói runtime. Ví dụ chạy với **Java 17+** để thuận tiện kiểm thử; API nền tảng đã có từ Java 9.

## 2. Các phương thức cần biết

```java
import java.util.spi.ToolProvider;
```

| Phương thức | Vai trò | Giá trị cần kiểm tra |
| --- | --- | --- |
| `ToolProvider.findFirst(String name)` | Tìm provider có tên tương ứng bằng `ServiceLoader` và system class loader | Trả `Optional<ToolProvider>`; có thể rỗng |
| `tool.name()` | Lấy tên công cụ của provider | Thường giống tên dòng lệnh: `javac`, `jar`, `jlink` |
| `tool.run(PrintWriter out, PrintWriter err, String... args)` | Gọi công cụ với hai nơi nhận output và dãy đối số | `0` là chạy thành công; mã khác `0` biểu thị lỗi riêng của công cụ |
| `tool.run(PrintStream out, PrintStream err, String... args)` | Overload thuận tiện cho stream byte (mặc định bọc thành `PrintWriter`) | Cùng ý nghĩa mã trả về |
| `tool.description()` | Mô tả ngắn, có thể vắng mặt | `Optional<String>`; phương thức mặc định được bổ sung từ **Java 19** |

**Phân biệt quan trọng:**

- `findFirst(...)` **chỉ tìm provider**. Nó không chạy `javac` hay tạo file.
- `run(...)` **mới thực hiện công việc**; các tham số sau `out` và `err` là **từng đối số riêng** của công cụ, không phải một chuỗi lệnh shell.
- `out` nhận output bình thường/dự kiến; `err` nhận thông báo lỗi hoặc chẩn đoán. Việc một tool có ghi vào `err` không đồng nghĩa mọi lần chạy đều thất bại: **mã trả về là tín hiệu đầu tiên**.
- `run` trả về `int`, **không phải** `boolean` hay `Process`. Không mặc định mọi mã lỗi có cùng ý nghĩa giữa các công cụ.
- Các tham số `name`, `out`, `err`, từng `args` không được `null` theo hợp đồng; kiểm tra đầu vào thay vì vô tình truyền `null`.

### Ví dụ tìm tool mà chưa thực thi

```java
import java.util.Optional;
import java.util.spi.ToolProvider;

Optional<ToolProvider> compiler = ToolProvider.findFirst("javac");

if (compiler.isPresent()) {
    System.out.println("Tìm thấy: " + compiler.get().name());
} else {
    System.out.println("Runtime không có provider javac");
}
```

Đây là **đoạn mã minh họa** đặt trong một phương thức/lớp; chưa có `main` để chạy độc lập. Trên JDK có module `jdk.compiler` và provider tương ứng, trường hợp thông thường là `Tìm thấy: javac`. Trên runtime image đã loại module này, `Optional.empty()` là kết quả hợp lệ; không tự tìm chương trình `javac.exe` trên `PATH` để thay thế.

Tìm bằng tên nên dùng **định danh chính xác mà provider công bố**; tên/alias do người dùng tự đoán có thể không khớp. `findFirst` lấy **provider đầu tiên** phù hợp; nếu ứng dụng cho phép nhiều provider cùng tên, không dựa vào thứ tự tìm kiếm để thực thi công cụ nhạy cảm.

## 3. Provider đến từ đâu?

`ToolProvider` là **service interface**, còn từng công cụ là một **service provider**. Java có thể khám phá provider được khai báo trong module hoặc tệp cấu hình dịch vụ của thư viện phù hợp, thông qua cơ chế `ServiceLoader`.

Trên JDK đầy đủ, các ví dụ quen thuộc gồm:

| Tên yêu cầu | Module thường cung cấp | Nhu cầu |
| --- | --- | --- |
| `javac` | `jdk.compiler` | Biên dịch mã nguồn Java |
| `jar` | `jdk.jartool` | Tạo, cập nhật, liệt kê và trích xuất JAR |
| `jlink` | `jdk.jlink` | Tạo ảnh runtime Java gồm các module được chọn |
| `jmod` | `jdk.jlink` | Tạo, mô tả, kiểm tra các file JMOD |
| `javadoc` | `jdk.javadoc` | Tạo tài liệu API từ mã nguồn Java |

**Không suy luận ngược:** có một tệp thực thi như `java`, `jimage` hay một lệnh bất kỳ trên hệ điều hành **không có nghĩa** `ToolProvider.findFirst("tên-lệnh")` sẽ trả kết quả. Chỉ những công cụ **thực sự cung cấp SPI** mới được tìm theo cách này.

### Vì sao dùng JDK vẫn có thể không tìm thấy `javac`?

- Ứng dụng đang chạy trong **custom runtime image** tạo bởi `jlink` và không có `jdk.compiler`.
- Runtime dùng module/class loader hoặc cơ chế đóng gói không đưa provider vào tập service được tìm kiếm.
- Provider của thư viện tùy chỉnh chưa được đăng ký/resolve chính xác.
- Cấu hình có lỗi trong khai báo service, dẫn đến `ServiceConfigurationError` khi tìm kiếm.

`java.util.spi.ToolProvider` thuộc `java.base` nên **lớp API vẫn có thể tồn tại** trong runtime tối giản, nhưng **công cụ cụ thể** thì không. Xử lý `Optional.empty()` là bắt buộc với ứng dụng cần chạy trên nhiều kiểu runtime.

### Các module khi xây ứng dụng

Nếu chương trình **sử dụng API `ToolProvider`** từ một module do bạn tạo, nó có thể gọi `ToolProvider.findFirst(...)` vì giao diện thuộc `java.base`. Nếu chương trình **tự gọi `ServiceLoader.load(ToolProvider.class)` từ một named module**, module của caller cần khai báo `uses java.util.spi.ToolProvider;`.

Nếu xây runtime bằng `jlink`, hãy chắc chắn các module cung cấp công cụ được đưa vào ảnh runtime. Ví dụ, `jdk.compiler` phải có khi cần provider `javac`. Việc kiểm tra `findFirst` ở **runtime đích** đáng tin hơn suy luận rằng “máy lập trình có JDK thì ứng dụng triển khai cũng có javac”.

## 4. Quy trình an toàn để tìm và gọi công cụ

Một ứng dụng nên theo thứ tự:

1. **Xác định tool và tác vụ** bằng tên SPI chuẩn mà môi trường đã kiểm chứng. Ví dụ `javac` dùng để biên dịch, `jar` để đóng gói.
2. **Tìm provider:** `ToolProvider.findFirst("javac")`, xử lý `Optional.empty()` rõ ràng.
3. **Xây đối số dạng danh sách:** mỗi option/path là một phần tử `String`. Không ghép chuỗi command đầy đủ theo cú pháp shell.
4. **Tạo nơi nhận output và error:** `PrintWriter`, `StringWriter` khi muốn giữ chẩn đoán trong bộ nhớ; có thể dùng `PrintStream` nếu cần in trực tiếp.
5. **Gọi `run(...)` và đọc mã trả về:** chỉ coi `0` là thành công; với mã khác, hiển thị/log chẩn đoán có kiểm soát.
6. **Xác minh artifact đầu ra** (file `.class`, `.jar`...) thay vì suy luận mọi file đều đúng chỉ vì tool trả `0`. Dọn thư mục tạm nếu lỗi.
7. Nếu tác vụ dài hoặc chạy từ GUI/server, chuyển sang thread/background job thích hợp, điều khiển giới hạn tài nguyên và quyền theo mô hình ứng dụng.

Ví dụ ngắn với `PrintStream`, **không chạy độc lập**:

```java
ToolProvider tool = ToolProvider.findFirst("javac")
    .orElseThrow(() -> new IllegalStateException("Thiếu javac"));

int status = tool.run(System.out, System.err, "-version");
if (status != 0) {
    throw new IllegalStateException("javac -version thất bại: " + status);
}
```

Kết quả version tùy runtime, ví dụ `javac 17.x` hay `javac 25.x`, vì vậy **không kiểm thử bằng cách so sánh chuỗi version cố định**.

### Tránh lỗi truyền một chuỗi command duy nhất

**Sai:**

```java
tool.run(System.out, System.err, "-d classes Hello.java");
```

Phần sau được xem là **một đối số**. Nó không được tách thành ba token như shell.

**Đúng:**

```java
tool.run(System.out, System.err,
    "-d", "classes", "Hello.java");
```

Nếu đường dẫn chứa dấu cách, cứ truyền đường dẫn đó thành một phần tử của mảng `args`. Không thêm dấu nháy `"..."` theo cú pháp shell vào trong giá trị đối số; dấu nháy sẽ trở thành ký tự thật nếu API tool không tự xử lý chúng.

## 5. Ví dụ Java 17+ hoàn chỉnh: gọi `javac` rồi `jar` trong chương trình

Ví dụ sau:

- Tìm `javac` qua `ToolProvider.findFirst`, không gọi `ProcessBuilder` hay `Runtime.exec`.
- Tạo một file Java thử nghiệm ở **thư mục tạm**, biên dịch với `--release 17` và `-d` rõ ràng.
- Khi provider `jar` có sẵn, tạo JAR từ file `.class` mới biên dịch.
- Thu cả output/error bằng `PrintWriter`, kiểm tra mã trả về và artifact thực tế.
- Xóa thư mục tạm ngay cả khi thao tác thất bại.

**Tệp duy nhất `EmbeddedToolsDemo.java`:**

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.spi.ToolProvider;
import java.util.stream.Stream;

public class EmbeddedToolsDemo {
    private record ToolResult(int exitCode, String output, String errors) {}

    public static void main(String[] args) throws Exception {
        ToolProvider javac = ToolProvider.findFirst("javac")
            .orElseThrow(() ->
                new IllegalStateException("Runtime thiếu provider javac"));

        Path work = Files.createTempDirectory("embedded-tools-");
        try {
            Path source = work.resolve("HelloTool.java");
            Path classes = Files.createDirectory(work.resolve("classes"));

            Files.writeString(source, """
                public class HelloTool {
                    public static String greeting() {
                        return "Hello from a tool!";
                    }
                }
                """, StandardCharsets.UTF_8);

            ToolResult compile = execute(
                javac,
                "--release", "17",
                "-encoding", "UTF-8",
                "-d", classes.toString(),
                source.toString()
            );

            if (compile.exitCode() != 0) {
                throw new IllegalStateException(
                    "javac thất bại: " + compile.errors()
                );
            }

            Path classFile = classes.resolve("HelloTool.class");
            if (!Files.isRegularFile(classFile)) {
                throw new IllegalStateException("Thiếu HelloTool.class");
            }

            System.out.println("Compiler name: " + javac.name());
            System.out.println("Compiler exit: " + compile.exitCode());
            System.out.println("Class created: " + Files.isRegularFile(classFile));

            // jar là công cụ tùy theo module của runtime.
            Optional<ToolProvider> jarTool = ToolProvider.findFirst("jar");
            if (jarTool.isPresent()) {
                Path archive = work.resolve("example.jar");
                ToolResult pack = execute(
                    jarTool.get(),
                    "--create",
                    "--file", archive.toString(),
                    "-C", classes.toString(), "HelloTool.class"
                );

                if (pack.exitCode() != 0) {
                    throw new IllegalStateException(
                        "jar thất bại: " + pack.errors()
                    );
                }
                if (!Files.isRegularFile(archive)) {
                    throw new IllegalStateException("Thiếu example.jar");
                }
                System.out.println("Jar exit: " + pack.exitCode());
                System.out.println("Jar created: " + Files.isRegularFile(archive));
            } else {
                System.out.println("Jar tool unavailable");
            }
        } finally {
            // Thu xong danh sách trước khi xóa để tránh giữ handle trên Windows.
            List<Path> paths;
            try (Stream<Path> stream = Files.walk(work)) {
                paths = stream.sorted(Comparator.reverseOrder()).toList();
            }
            for (Path path : paths) {
                Files.deleteIfExists(path);
            }
        }
    }

    private static ToolResult execute(ToolProvider tool, String... args) {
        StringWriter output = new StringWriter();
        StringWriter errors = new StringWriter();

        PrintWriter out = new PrintWriter(output);
        PrintWriter err = new PrintWriter(errors);

        int exitCode = tool.run(out, err, args);
        out.flush();
        err.flush();

        return new ToolResult(exitCode, output.toString(), errors.toString());
    }
}
```

Chạy trên JDK 17+ **có module `jdk.compiler` và `jdk.jartool`**:

```bash
javac -encoding UTF-8 EmbeddedToolsDemo.java
java EmbeddedToolsDemo
```

**Stdout chuẩn khi cả hai provider có sẵn và hoạt động thành công:**

```text
Compiler name: javac
Compiler exit: 0
Class created: true
Jar exit: 0
Jar created: true
```

Nếu runtime có `javac` nhưng không có `jar`, ba dòng đầu giữ nguyên, dòng cuối là `Jar tool unavailable`. Nếu thiếu `javac`, chương trình phát sinh `IllegalStateException` với nguyên nhân cụ thể và **không biên dịch**. Không hardcode tên phiên bản JDK hoặc đường dẫn thư mục tạm vào stdout.

### Giải thích từng phần

- `ToolProvider.findFirst("javac")` tìm đúng provider SPI, không tìm tệp thực thi trên `PATH`.
- `Files.writeString` tạo một source đơn giản; `--release 17` chọn mức API/bytecode của Java 17 khi dùng JDK hỗ trợ. Tùy mục đích ứng dụng, nên cho phép người dùng chọn `--release` theo các phiên bản **được compiler hiện tại hỗ trợ**, không tự giả định bản JDK nào cũng hỗ trợ mọi phiên bản.
- `-d classes` chỉ định thư mục đầu ra; việc biên dịch là thao tác có tác động file hệ thống, nên demo dùng thư mục tạm thay cho repo người dùng.
- `ToolResult` tách mã trả về, stdout và stderr. Demo chỉ in các kiểm chứng ổn định; với mã lỗi khác `0` mới ghép thông báo lỗi vào ngoại lệ.
- `jar --create --file example.jar -C classes HelloTool.class` tương đương cách dùng dòng lệnh hiện hành và tạo một archive có class đã biên dịch.
- `Files.walk` duyệt các file đã tạo và xóa từ sâu lên nông. Trong ứng dụng thật, thư mục workspace có thể cần được giữ để người dùng lấy artifact: khi đó **không xóa** ngay mà chuyển thành thư mục output quản lý rõ ràng.

**Điểm cần chú ý:** demo xây source từ chuỗi **cố định, tin cậy**. Nếu ứng dụng biên dịch source do người dùng cung cấp, **đừng hiểu đây là sandbox an toàn**. Trong toolchain, annotation processor, plugin và quá trình build có thể thực thi logic ngoài ý muốn; đối với mã/đầu vào không tin cậy cần môi trường cách ly, quyền tối thiểu và hạn chế tài nguyên phù hợp.

## 6. Cách viết API nhỏ để tái sử dụng `ToolProvider`

Với nhiều công cụ, nên đóng gói hành vi “tìm, chạy, kiểm tra, trả chẩn đoán”:

```java
// ĐOẠN MINH HỌA: đặt trong lớp tiện ích có import tương ứng.
static int runNamedTool(
        String name,
        PrintWriter out,
        PrintWriter err,
        String... arguments) {

    ToolProvider tool = ToolProvider.findFirst(name)
        .orElseThrow(() -> new IllegalStateException(
            "Tool không được cài trong runtime: " + name
        ));

    int code = tool.run(out, err, arguments);
    out.flush();
    err.flush();
    return code;
}
```

Đây là **đoạn hàm**, không phải lớp Java tự chạy. Khi gọi, truyền hai `PrintWriter` hợp lệ và một mảng đối số đã kiểm tra:

```java
int status = runNamedTool(
    "javac",
    new PrintWriter(System.out, true),
    new PrintWriter(System.err, true),
    "-version"
);
```

Ưu điểm: một chỗ xử lý thông báo “thiếu provider”, lệnh gọi được tạo từ dữ liệu có kiểm soát, chỗ gọi nhận mã hoàn tất. Hạn chế: không tái sử dụng cùng một tool và nhiều thread đồng thời trừ khi provider xác nhận nó an toàn; khi thư viện cần concurrency, queue tác vụ hoặc tạo môi trường thực thi riêng.

### Nếu cần liệt kê tool thay vì tìm một tên

`ToolProvider.findFirst(name)` là lựa chọn tốt khi **đã biết tên**. Với màn hình “Các công cụ đang có”, có thể dùng `ServiceLoader` trực tiếp:

```java
import java.util.ServiceLoader;
import java.util.spi.ToolProvider;

for (ToolProvider tool : ServiceLoader.load(ToolProvider.class)) {
    System.out.println(tool.name());
}
```

Đây là **đoạn minh họa**; danh sách và thứ tự provider phụ thuộc runtime. Trong **named module** tự gọi `ServiceLoader.load`, cần khai báo:

```java
module my.application {
    uses java.util.spi.ToolProvider;
}
```

Khi `findFirst(name)` được dùng, việc tìm kiếm nằm trong implementation chuẩn của `ToolProvider`; không phải là yêu cầu gọi `ServiceLoader.load` thủ công từ mã ứng dụng. Trường hợp cùng tên nhiều provider, hãy đánh giá danh tính module/lớp triển khai hoặc cấu hình chuyên biệt, vì việc chọn “đầu tiên” không phải chính sách tin cậy đủ mạnh.

## 7. Đăng ký một công cụ tự viết (SPI)

Một thư viện có thể cung cấp provider riêng bằng cách triển khai `ToolProvider`. Ví dụ **minh họa** công cụ `echo-demo`:

**`EchoTool.java`:**

```java
package example.tools;

import java.io.PrintWriter;
import java.util.spi.ToolProvider;

public final class EchoTool implements ToolProvider {
    @Override
    public String name() {
        return "echo-demo";
    }

    @Override
    public int run(PrintWriter out, PrintWriter err, String... args) {
        if (args.length != 1) {
            err.println("Usage: echo-demo <message>");
            return 2;
        }
        out.println(args[0]);
        return 0;
    }
}
```

Nếu provider được đóng gói thành **named module**, module của thư viện khai báo:

**`module-info.java` (module của provider):**

```java
module example.tools {
    provides java.util.spi.ToolProvider with example.tools.EchoTool;
}
```

Một ứng dụng khác có thể gọi:

```java
var echo = ToolProvider.findFirst("echo-demo")
    .orElseThrow(() -> new IllegalStateException("Thiếu echo-demo"));

int result = echo.run(
    new PrintWriter(System.out, true),
    new PrintWriter(System.err, true),
    "Xin chào"
);
```

Các đoạn trên mô tả **ba phần ở các module/lớp khác nhau**, không phải một chương trình Java đơn lẻ có thể dán tất cả vào một file. Provider phải hiện diện trên module path và được **resolve** khi khởi động (hoặc đăng ký qua cơ chế classpath service file). Nếu phát hành provider dưới dạng JAR chạy trên classpath, thông lệ `ServiceLoader` là file `META-INF/services/java.util.spi.ToolProvider` chứa **tên lớp đầy đủ** `example.tools.EchoTool`.

Chỉ triển khai `ToolProvider` chưa làm provider có thể tìm được: cần **đăng ký service chính xác** và bảo đảm nó được nạp trong runtime mà caller sử dụng. Không dùng reflection tới những lớp nội bộ của JDK để thay thế service registration.

## 8. Phân biệt với các API hay bị nhầm

### 8.1. `java.util.spi.ToolProvider` và `javax.tools.ToolProvider`

Dù trùng tên, hai API có mục đích khác nhau:

| API | Dùng khi | Điểm khác biệt |
| --- | --- | --- |
| `java.util.spi.ToolProvider.findFirst("javac")` | Cần **lời gọi như công cụ CLI** với các tham số String và mã kết quả | SPI chung cho nhiều tool, ở `java.base` |
| `javax.tools.ToolProvider.getSystemJavaCompiler()` | Cần **API biên dịch có cấu trúc**, diagnostics, file manager, in-memory `JavaFileObject` | Trả `JavaCompiler` hoặc `null` nếu không có, ở module `java.compiler` |
| `ProcessBuilder` | Cần tiến trình **riêng** có I/O, exit status, timeout/process lifecycle | Dựa vào executable của hệ điều hành, không phải SPI |
| `ServiceLoader<ToolProvider>` | Cần duyệt, lọc hoặc tự quản lý nhiều provider | Cơ chế dịch vụ chung; cần `uses` với direct call từ named module |

Chọn **`javax.tools.JavaCompiler`** khi ứng dụng cần kiểm soát nguồn Java trong bộ nhớ, nhận `DiagnosticListener` có cấu trúc hoặc quản lý `JavaFileManager`. Chọn **`java.util.spi.ToolProvider`** khi cần gọi `javac`/`jar` theo dạng gần CLI và muốn đơn giản hóa tích hợp. Chọn **`ProcessBuilder`** khi cần cách ly tiến trình, kiểm soát thời hạn chạy, JVM options hoặc thực thi công cụ không cung cấp SPI.

**Ví dụ minh họa JavaCompiler, không phải chương trình độc lập:**

```java
javax.tools.JavaCompiler compiler =
    javax.tools.ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    throw new IllegalStateException("Runtime không có compiler");
}
```

Không cần sử dụng cả hai `ToolProvider` trong một tác vụ nếu không có mục đích rõ. Chúng cùng tồn tại và được hỗ trợ; **không** import nhầm gói rồi gọi `findFirst` trên lớp `javax.tools.ToolProvider`.

### 8.2. ToolProvider khác với khả năng chạy mọi lệnh terminal

Nếu ứng dụng gọi:

```java
ToolProvider.findFirst("git");
```

kết quả **không bảo đảm có mặt** ngay cả khi lệnh `git --version` chạy được từ terminal. Cần một provider thực sự cung cấp tên `git`; Java không tự chuyển mọi chương trình trong `PATH` thành `ToolProvider`.

`ToolProvider.run(...)` nhận mảng đối số Java; nó **không** thực hiện phân tích cú pháp shell, expansion `*`, pipe `|`, biến môi trường hay chuyển hướng `>`. Đối với các thao tác đó, phải triển khai bằng API file/stream hoặc dùng cơ chế process thích hợp một cách chủ động.

## 9. Xử lý lỗi và thiết kế đáng tin cậy

| Tình huống | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Provider không được cài | `findFirst(...)` trả `Optional.empty()` | Hiển thị yêu cầu module/tool, cấu hình runtime hoặc dùng tính năng dự phòng đã được thiết kế |
| Khai báo service lỗi | `ServiceConfigurationError` trong quá trình tìm/nạp | Kiểm tra `provides`, `uses`, module path, service file và class loader |
| Tham số công cụ sai | `run(...)` trả khác `0`, có thông báo ở `err` | Ghi mã lỗi và thông báo cần thiết, sửa các đối số cụ thể |
| Tool không ghi stderr nhưng trả lỗi | `code != 0` với `err` trống | Vẫn coi là lỗi, đừng dựa trên stderr để quyết định |
| Tool ném ngoại lệ runtime | Có thể không có mã trả về | Bắt và báo lỗi ở ranh giới gọi thích hợp, dọn tài nguyên |
| Có `javac` trong IDE nhưng không có trong runtime image | `findFirst("javac")` rỗng khi triển khai | Bảo đảm module `jdk.compiler` trong runtime, kiểm tra trên build deploy thật |
| Path chứa dấu cách không biên dịch | Ghép tất cả option thành chuỗi | Mỗi option, value, đường dẫn là một phần tử `args` |
| Tool báo thành công nhưng thiếu file đầu ra | Thư mục đích/đối số sai, logic tool đặc thù | Kiểm tra file đầu ra và cấu trúc mong đợi sau khi code trả `0` |
| Hai tác vụ công cụ chạy đồng thời gây lỗi khó tái hiện | Provider giữ trạng thái dùng chung, file output trùng tên | Tách thư mục output; xác minh tính reentrant, serialize khi cần |
| Không thể dừng thao tác đang chạy trong JVM | Tool chạy đồng bộ/không hỗ trợ hủy | Thực thi qua tiến trình riêng nếu yêu cầu timeout/cancel bắt buộc |

### Những ràng buộc bảo mật cần giữ

- **Chỉ gọi tool được tin cậy.** Provider chạy logic trong môi trường ứng dụng hoặc tự tổ chức thực thi; không có cơ chế quyền tối thiểu tự động do `ToolProvider` cấp.
- **Không chạy công cụ build trên source không tin cậy trong cùng JVM của server quan trọng.** Compiler/plugin/annotation processor và toolchain có thể làm nhiều việc hơn biên dịch cú pháp. Nếu người dùng upload mã tùy ý, dùng worker/VM/container bị hạn chế quyền theo kiến trúc bảo mật thực tế.
- **Xác thực đối số và path**. Việc không thông qua shell giảm lỗi quoting/shell injection, nhưng không loại bỏ rủi ro **option injection, ghi đè file, path traversal** hoặc dùng các cờ nguy hiểm của chính tool.
- **Giới hạn resource và thời gian.** Khi cần giới hạn CPU, RAM, I/O hoặc kill chắc chắn, cân nhắc một process riêng và sandbox phù hợp; không xem `Future.cancel(true)` là bảo đảm dừng mọi provider.
- **Không bắt lỗi rồi báo thành công.** Một lần `run(...)` trả mã khác `0` phải được ghi nhận; có thể còn artifact chưa hoàn chỉnh, cần cleanup hoặc cách commit output có kiểm chứng.
- **Không log nguyên bản dữ liệu bí mật** trong đối số, output, error hay temporary files. Giới hạn kích thước output để tránh chiếm nhiều bộ nhớ khi thu bằng `StringWriter`.

### Kiểm thử nên có

1. **Provider có mặt**: tìm đúng tên, nhận được `name()` mong đợi.
2. **Provider vắng mặt**: ứng dụng báo rõ khả năng bị thiếu, không gây `NoSuchElementException` vô nghĩa.
3. **Lệnh hợp lệ**: `run` trả `0` và artifact thực tế đúng.
4. **Lệnh sai**: mã khác `0` được xử lý, log có thông tin chẩn đoán và không đưa artifact lỗi vào sử dụng.
5. **Đường dẫn chứa dấu cách/Unicode**: vẫn hoạt động vì đối số được truyền rời.
6. **Custom runtime image**: với/không có module công cụ, hành vi `findFirst` phù hợp.
7. **Nhiều lần hoặc đồng thời**: không ghi đè thư mục và không dùng provider vượt quá mức concurrency được hỗ trợ.
8. **Dữ liệu đầu vào không tin cậy**: xử lý trong môi trường có quyền và giới hạn tài nguyên phù hợp.

## 10. Lựa chọn sử dụng trong thực tế

Đối với một **ứng dụng build/IDE/tooling trên JDK**, hãy dùng `java.util.spi.ToolProvider` khi cần gọi chức năng như `javac`, `jar`, `jlink` với đối số CLI và đọc mã kết quả ngay trong chương trình. API nhỏ, phù hợp tích hợp, nhưng phải quản lý sự tồn tại của provider và vòng đời artifact.

Đối với một **dịch vụ server**, trước tiên hỏi có cần cho người dùng nạp/tạo code hay không. Nếu chạy công cụ trên nội dung do bên ngoài cung cấp, **tách môi trường thực thi** để kiểm soát an ninh và tài nguyên, ngay cả khi `ToolProvider` có thể gọi tool thuận tiện trong JVM. Với biên dịch có diagnostics và file manager chuyên sâu, nên dùng `JavaCompiler` ở `javax.tools`.

Đối với một **ứng dụng dùng runtime image tối giản**, hãy kiểm tra tên module cung cấp tool trong quá trình đóng gói, rồi xác nhận bằng `findFirst` lúc chạy. Không coi khả năng tìm `ToolProvider` là tương đương với việc có mọi công cụ JDK.

**Tổng quy tắc API:** `findFirst(name)` → kiểm tra `Optional` → chuẩn bị các đối số riêng biệt → `run(out, err, args...)` → kiểm tra mã trả về, output và artifact. Đó là quy trình ổn định từ Java 9 đến các JDK hiện hành.

## 11. Tài liệu chính thức

- [Java SE 25 — java.util.spi.ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/ToolProvider.html): định nghĩa `findFirst`, `name`, `run`, `description` và hợp đồng mã trả về.
- [Java SE 17 — java.util.spi.ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ToolProvider.html): xác nhận API có thể dùng trong ví dụ Java 17+.
- [Java SE 25 — java.util.ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): đăng ký provider, nạp module/classpath và yêu cầu `uses`.
- [Java SE 25 — jdk.compiler module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/module-summary.html): `javac` như `ToolProvider` và JavaCompiler SPI.
- [Java SE 25 — jdk.jartool module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jartool/module-summary.html): `jar` cung cấp ToolProvider.
- [Java SE 25 — jdk.jlink module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jlink/module-summary.html): `jlink`/`jmod` cung cấp ToolProvider, mô tả runtime image.
- [Java SE 25 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): API tìm Java compiler khác với `java.util.spi.ToolProvider`.
- [Java SE 25 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): biên dịch có chẩn đoán cấu trúc và file manager.

Bài viết dùng **những API chuẩn còn được hỗ trợ**, tránh phụ thuộc vào lớp triển khai nội bộ của JDK. Khi đưa vào hệ thống thực, hãy kiểm chứng provider bằng chính **runtime được triển khai**, vì tập công cụ phụ thuộc module đi kèm.