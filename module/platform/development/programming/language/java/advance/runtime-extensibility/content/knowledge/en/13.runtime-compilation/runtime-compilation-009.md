# Đóng file manager và tách giai đoạn biên dịch khỏi thực thi trong Java

## 1. Mục tiêu và tình huống áp dụng

Java hỗ trợ **biên dịch mã ngay trong lúc ứng dụng đang chạy** thông qua API `javax.tools.JavaCompiler`. Một host có thể nhận source code từ bộ sinh mã, tạo implementation của SPI, biên dịch lớp tùy biến rồi nạp kết quả để gọi bằng reflection hoặc interface chung. Tuy nhiên, **tác vụ biên dịch không phải là tác vụ thực thi**, và `JavaFileManager` không phải class loader dùng để chạy mã.

Khi thiết kế quy trình này, phải trả lời rõ:

- Ai sở hữu và đóng `StandardJavaFileManager`?
- Lúc nào `JavaCompiler.CompilationTask.call()` kết thúc, lúc nào mới được nạp class?
- Nếu biên dịch lỗi hoặc đóng tài nguyên lỗi, làm sao bảo đảm **không thực thi** mã chưa hợp lệ hoặc bytecode cũ?
- Có thể tái sử dụng file manager giữa nhiều lượt biên dịch không, và khi nào nên kết thúc vòng đời?
- Sau khi đóng file manager, file `.class` có còn tồn tại và ai chịu trách nhiệm giải phóng class loader?
- Trường hợp in-memory compilation, JAR dependencies, nhiều request song song hay plugin hot reload cần đổi cấu trúc ra sao?

**Nguyên tắc chính:** Giai đoạn **COMPILE** tạo artifact đã kiểm tra và sở hữu một file manager với vòng đời hữu hạn; sau khi task và file manager kết thúc thành công, giai đoạn **LOAD/EXECUTE** dùng artifact đó với một loader/vòng đời **khác**. Không để class loader hay code của plugin tiếp tục sử dụng file manager đã đóng.

## 2. Những đối tượng tham gia và phạm vi trách nhiệm

| API/đối tượng | Trách nhiệm | Đóng khi nào? |
|---|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler Java được runtime hiện tại cung cấp | Không phải một `Closeable`; có thể trả `null` nếu không có compiler |
| `JavaCompiler` | Tạo tác vụ biên dịch | Không đồng nghĩa với class loader hay file manager |
| `JavaCompiler.CompilationTask` | Biên dịch một tập compilation units khi gọi `call()` | Đợi `call()` hoàn thành trước khi dùng artifact |
| `StandardJavaFileManager` | Đọc source/class/JAR, định vị output và tạo file objects | `close()` ở cuối vùng sở hữu; dùng `try-with-resources` |
| `DiagnosticCollector<JavaFileObject>` | Thu nhận lỗi/cảnh báo từ compiler | Không phải file manager, có thể đọc sau khi task hoàn tất |
| `Path outputDirectory` | Nơi chứa artifact bytecode `.class` | Không bị xóa khi đóng file manager; chủ ứng dụng dọn |
| `URLClassLoader` hoặc custom class loader | Tìm/định nghĩa các class trong artifact để chạy | Đóng loader khi hết lượt sử dụng và hết tham chiếu/plugin lifecycle |
| Object/class đã nạp | Thực thi method và có thể giữ class loader sống | Phải được giải phóng theo hợp đồng runtime |

Theo Java 17, `JavaFileManager.close()` giải phóng các tài nguyên mà manager đã mở **trực tiếp hoặc gián tiếp**, có thể ném `IOException`. Việc gọi tiếp manager hoặc file object lấy từ nó **sau khi đóng** có hiệu ứng không được bảo đảm, trừ những thao tác API cho phép rõ ràng. Đừng phụ thuộc vào chuyện một implementation cụ thể đôi khi vẫn hoạt động sau `close()`.

`JavaFileManager.flush()` khác `close()`: `flush()` đẩy những tài nguyên output đang ghi; `close()` kết thúc vòng đời sử dụng và giải phóng handle/cache liên quan. Gọi `flush()` **không thay thế** `close()` khi chủ sở hữu đã xong giai đoạn biên dịch.

## 3. Tách hai giai đoạn thành hợp đồng rõ ràng

Một luồng thực thi an toàn có dạng:

```text
Nhận source / xác thực yêu cầu
              |
              v
   Tạo thư mục output RIÊNG cho một build
              |
              v
          COMPILE PHASE
  ┌─────────────────────────────────────────┐
  │ JavaCompiler + DiagnosticCollector      │
  │ try (StandardJavaFileManager manager)   │
  │   CLASS_OUTPUT = output directory       │
  │   tạo compilation units                 │
  │   CompilationTask.call()                 │
  │ }  <-- close() ở cuối scope              │
  └─────────────────────────────────────────┘
              |
              v
   Task SUCCESS và close() SUCCESS?
          /                  \
         no                  yes
         |                    |
  báo lỗi, KHÔNG chạy        v
                      xác minh artifact
                             |
                             v
                       EXECUTE PHASE
                      try (ClassLoader)
                        Class.forName(...)
                        gọi API / reflection
                      close loader
                             |
                             v
                     dọn phiên build cũ
```

**Đường ranh giới quyết định:** `CompilationTask.call()` trả `true` chứng tỏ tác vụ thông báo biên dịch thành công. Nhưng một phương thức wrapper dùng `try-with-resources` chỉ thực sự trả về cho caller **sau khi** `StandardJavaFileManager.close()` hoàn thành. Nếu `close()` ném lỗi, phương thức wrapper không trả về kết quả thành công bình thường và phía gọi không bắt đầu execution.

Đây là điểm giúp tránh tình trạng “task xong nhưng file handle, JAR cache hoặc output stream vẫn còn sống” khi một runtime muốn ngay lập tức dùng, thay thế hoặc dọn artifact.

Với tác vụ bất đồng bộ, thay vì giả định rằng việc lập lịch biên dịch đã xong đồng nghĩa có artifact, trả về kết quả tương lai chỉ **khi compile + close + validate hoàn tất**. Chỉ consumer nhận trạng thái thành công mới được tiến sang load/execute.

## 4. Chương trình Java 17+ hoàn chỉnh: biên dịch, đóng manager, sau đó thực thi

Ví dụ dùng `JavaCompiler` để tạo một lớp `dynamic.Message` từ chuỗi Java, lưu source xuống disk, biên dịch vào một output directory mới và nạp bằng `URLClassLoader`. Host không được nạp trực tiếp lớp nguồn này từ class path của mình.

Ví dụ được giữ độc lập, không cần thư viện thứ ba, không cần tên lớp đặt trước trong source path. Mỗi lần chạy tạo output directory duy nhất; điều đó tránh tình huống lần biên dịch lỗi nhưng `.class` của lần trước vẫn nằm ở output cũ.

**Tệp duy nhất `CompileThenRun.java` (đặt tại thư mục làm việc):**

```java
import java.io.IOException;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompileThenRun {
    private static boolean compile(Path sourceFile, Path output,
                                   DiagnosticCollector<JavaFileObject> diagnostics)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK with jdk.compiler is required");
        }

        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            files.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output));
            Iterable<? extends JavaFileObject> sources =
                    files.getJavaFileObjectsFromPaths(List.of(sourceFile));
            List<String> options = List.of("--release", "17", "-proc:none");

            return Boolean.TRUE.equals(compiler.getTask(
                    null, files, diagnostics, options, null, sources).call());
        } // files.close() runs before compile(...) returns.
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build", "compiler-demo").toAbsolutePath();
        Path source = root.resolve("src/dynamic/Message.java");
        Files.createDirectories(source.getParent());
        Path output = Files.createTempDirectory(
                Files.createDirectories(root.resolve("outputs")), "run-");

        Files.writeString(source, """
                package dynamic;
                public final class Message {
                    public static String say() {
                        return "Hello from runtime compilation";
                    }
                }
                """, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        boolean compiled = compile(source, output, diagnostics);

        if (!compiled) {
            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                    System.err.println(diagnostic.getMessage(Locale.ROOT));
                }
            }
            throw new IllegalStateException("Compile failed; execution skipped");
        }

        System.out.println("compiled=" + compiled);
        System.out.println("class-file-present=" +
                Files.isRegularFile(output.resolve("dynamic/Message.class")));

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { output.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> generated = Class.forName("dynamic.Message", true, loader);
            Object result = generated.getMethod("say").invoke(null);
            System.out.println("message=" + result);
        }
    }
}
```

### 4.1. Lệnh biên dịch và chạy trên Windows PowerShell

Đứng ở thư mục chứa `CompileThenRun.java` và dùng JDK 17 hoặc mới hơn:

```powershell
New-Item -ItemType Directory -Force -Path build/host | Out-Null
javac --release 17 -d build/host CompileThenRun.java
java -cp build/host CompileThenRun
```

### 4.2. Lệnh trên Linux/macOS

```bash
mkdir -p build/host
javac --release 17 -d build/host CompileThenRun.java
java -cp build/host CompileThenRun
```

Host chỉ cần class path `build/host`. Mã sinh ra sẽ được đặt trong `build/compiler-demo/outputs/run-.../dynamic/Message.class`; không đưa thư mục đó lên class path của JVM lúc khởi chạy host.

### 4.3. Stdout chính xác ở nhánh thành công

```text
compiled=true
class-file-present=true
message=Hello from runtime compilation
```

Chương trình đã được biên dịch với `javac --release 17` và chạy kiểm chứng trên JDK mới hơn có hỗ trợ release 17. Thư mục `run-...` có tên ngẫu nhiên do `Files.createTempDirectory` sinh ra, nhưng không được in nên stdout vẫn ổn định.

**Vì sao trình tự này đúng?**

1. `Files.createTempDirectory` tạo output mới bên dưới root thuộc quyền sở hữu của demo. Không vô tình dùng class cũ khi biên dịch một phiên bản mới thất bại.
2. `ToolProvider.getSystemJavaCompiler()` kiểm tra môi trường có compiler. Custom runtime image có thể thiếu `jdk.compiler`, khi đó phải báo khả năng không được hỗ trợ thay vì giả định luôn có.
3. `getStandardFileManager(...)` được tạo **bên trong `compile`**; caller không giữ tham chiếu và không dùng manager ngoài scope.
4. `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output))` yêu cầu compiler ghi class files vào thư mục đã tồn tại; output file có thể nằm trong package folder con.
5. `getJavaFileObjectsFromPaths(List.of(sourceFile))` biến `Path` thành compilation unit mà compiler có thể đọc. `List.of(...)` chọn overload nhận `Collection<? extends Path>`, tránh gọi nhầm overload nhận `Iterable<Path>` đã deprecated.
6. `getTask(...).call()` chạy tác vụ thực tế; `Boolean.TRUE.equals(...)` chỉ nhận đúng `Boolean.TRUE` là thành công, không coi `false`/`null` là thành công.
7. `try-with-resources` bảo đảm gọi `files.close()` cả khi compile thất bại hoặc ném lỗi. Caller chỉ nhận kết quả bình thường khi method `compile` đã rời scope.
8. Nhánh `!compiled` in diagnostic lỗi và **ném exception trước khi tạo class loader**. Không có “thử chạy tạm” một artifact chưa biên dịch thành công.
9. Sau compile, host kiểm tra file output rồi mới dùng `URLClassLoader` và `Class.forName`. Loader có parent là platform loader vì lớp demo chỉ sử dụng Java platform API. Với code cần host SPI, phải chọn parent cung cấp đúng SPI đó.
10. `URLClassLoader` có scope và thao tác `close()` riêng. Việc đóng nó không phải là đóng compiler manager; hai tài nguyên thuộc hai giai đoạn khác nhau.

**Giới hạn của ví dụ:** code hiển thị trạng thái `class-file-present`, rồi dùng `Class.forName`. Trong production, nếu thiếu artifact bắt buộc thì nên ném lỗi **ngay tại validation**, không tiếp tục. Demo để lại source và các thư mục `run-...` để học viên có thể kiểm tra; runtime thật cần chính sách thu gom artifact sau khi không còn loader dùng nó.

## 5. Vì sao phải đóng file manager bằng try-with-resources?

Một cách viết dễ gây lỗi là:

```java
StandardJavaFileManager manager =
        compiler.getStandardFileManager(null, null, null);
boolean ok = compiler.getTask(null, manager, null,
        options, null, sources).call();
runGeneratedClass();  // thực thi trong khi manager có thể vẫn mở
manager.close();       // không chạy nếu runGeneratedClass ném lỗi
```

Đây là **mã phản ví dụ**, dùng các biến/hàm chưa được khai báo; không phải chương trình độc lập. Trong mẫu sai:

- `manager.close()` nằm sau code thực thi; nếu logic runtime ném exception, manager không được đóng.
- Đường biên giữa compiler và runtime bị lẫn, khó quy định khi nào được thay thế JAR hoặc xóa output.
- Nếu quên kiểm tra `ok`, code có thể nạp class cũ trong cùng thư mục output.
- Với nhiều tác vụ liên tiếp, exception ở một bước có thể giữ tài nguyên file manager của các lần biên dịch khác.

Thay bằng:

```java
boolean compiled;
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null, null)) {
    // cấu hình locations, tạo compilation units
    // ...
    compiled = Boolean.TRUE.equals(
            compiler.getTask(null, manager, diagnostics,
                    options, null, sources).call());
} // manager.close() ở đây, kể cả khi có exception

if (!compiled) {
    throw new IllegalStateException("Compilation failed");
}
// Dùng output đã được xác thực để load/execute.
```

Đoạn này là **mẫu minh họa** với `compiler`, `diagnostics`, `options`, `sources` đã có; chương trình hoàn chỉnh là mục 4. Ở production, phần tạo compilation units phải nằm trong scope của manager.

**Điều cần lưu ý về exception:** `close()` có thể ném `IOException`. Với `try-with-resources`, nếu code trong khối cũng ném lỗi thì lỗi đóng tài nguyên được gắn làm **suppressed exception** vào lỗi chính. Đừng catch rộng rồi bỏ qua `IOException` từ close mà vẫn coi artifact là “sẵn sàng chạy”.

## 6. Compile thành công không đồng nghĩa đã thực thi thành công

Tách kết quả thành các trạng thái riêng:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| `SOURCE_RECEIVED` | Có input nhưng chưa phân tích/biên dịch | Kiểm soát nguồn, encoding và cấu hình |
| `COMPILING` | `CompilationTask.call()` đang chạy | Chưa cho phép load |
| `COMPILE_FAILED` | Task trả false/không tạo artifact hợp lệ | Trả diagnostics, tuyệt đối không execute |
| `COMPILED` | Task thành công và file manager đóng bình thường | Có thể bước sang kiểm tra artifact |
| `VALIDATED` | Đúng class files, version, manifest/hash và scope mong đợi | Cho phép tạo loader |
| `EXECUTING` | Nạp lớp, initialize, instantiate, invoke theo contract | Áp dụng timeout/lifecycle riêng |
| `EXECUTION_FAILED` | Linkage, class init, constructor hoặc business logic lỗi | Không sửa đổi ý nghĩa compile success |
| `RETIRED` | Không còn lượt chạy nào dùng artifact/loader | Dọn reference, đóng loader và xóa artifact khi an toàn |

Tên trạng thái trên là **đề xuất thiết kế của ứng dụng**, không phải enum có sẵn của JavaCompiler. Compiler chỉ báo kết quả compile và diagnostics; application cần tự quản lý state machine và điều kiện được phép execute.

Ví dụ, `ClassNotFoundException` khi nạp kết quả có thể do sai output path/loader dù `CompilationTask.call()` thành công. `NoClassDefFoundError` hoặc `UnsupportedClassVersionError` có thể phát sinh khi có dependency/version không phù hợp. `InvocationTargetException` khi gọi reflection thường bao bọc exception ném từ method đang chạy. Những lỗi đó xảy ra ở **execute phase**, không nên gộp thành compiler diagnostics.

## 7. Đường lỗi biên dịch: diagnostics và điều kiện dừng

`DiagnosticCollector<JavaFileObject>` thu thập cảnh báo và lỗi với mức độ như `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. Có thể đọc `Diagnostic.getKind()`, `getLineNumber()`, `getColumnNumber()`, `getCode()`, `getMessage(locale)` và `getSource()` nếu có. Cần tránh tự suy diễn rằng mọi diagnostic đều có dòng/cột hợp lệ; khi không biết, Javadoc dùng giá trị biểu thị không có thông tin vị trí.

Cách xử lý hợp lý:

1. Tạo collector mới **cho mỗi compilation job** hoặc quản lý reset của collector theo phiên.
2. Lấy output riêng và build identifier trước khi compile.
3. Gọi `task.call()` đúng một lần cho một task. Không thực thi mã chỉ vì file class có tồn tại.
4. Khi `false`, ghi nhận diagnostics, chuyển trạng thái thất bại, không xây class loader runtime.
5. Nếu `getTask`/`call` ném runtime exception hoặc manager `close()` ném `IOException`, báo lỗi hệ thống/compile infrastructure; không đổi thành `compiled=true`.
6. Không trả về source code nhạy cảm hay đường dẫn máy chủ trong thông báo lỗi cho người dùng không tin cậy; log chi tiết tại nơi được kiểm soát.

Lưu ý: Một số thông điệp của compiler có thể được ghi ra writer hoặc stderr thay vì hoàn toàn nằm trong `DiagnosticCollector`. `getTask(out, ...)` cho phép chỉ định writer; nếu cần thu thập đầy đủ trong sản phẩm, thiết kế cả hai kênh thông báo. `DiagnosticCollector` không tự quyết định mức nghiêm trọng nào sẽ bị coi là thất bại; **kết quả `call()` mới là tín hiệu chính**.

### 7.1. Khi compile thất bại nhưng class cũ vẫn tồn tại

Với một đường dẫn output dùng lại như `build/classes`:

```text
Lần 1: class A biên dịch thành công -> A.class xuất hiện.
Lần 2: source A có lỗi cú pháp -> call() trả false.
Lỗi thiết kế: vẫn nạp A.class của lần 1 -> chạy mã đã lỗi thời.
```

Giải pháp phù hợp:

- Ghi mỗi build vào thư mục/namespace **mới, bất biến**; xuất bản bản build chỉ sau compile, close, validate.
- Xóa output thuộc **riêng build đó** khi job thất bại và khi không còn ai sử dụng (không xóa bừa thư mục chung).
- Lưu build ID/hash, tập file dự kiến và artifact manifest; runtime kiểm chứng đúng phiên thay vì chỉ dựa vào tên class.
- Nếu buộc dùng một output path cố định, dọn artifact cũ **trước** compile với ownership và locking rõ ràng. Cẩn thận với reader đang dùng class file/JAR trên Windows.
- Không fallback âm thầm sang bytecode cũ nếu chính sách của ứng dụng không cho phép; nếu có fallback phiên ổn định, phải hiển thị đó là một quyết định rollback riêng.

Tạo thư mục output mới ở mục 4 là minh họa cho lựa chọn đầu tiên.

## 8. Đóng file manager có xóa .class hoặc unload class không?

**Không.** Có ba loại tài nguyên khác nhau:

1. **Tài nguyên compiler/file manager:** streams, file handles, cache đọc JAR, file objects; kết thúc bằng `JavaFileManager.close()`.
2. **Artifact sinh ra:** file `.class`/JAR/metadata trên disk hoặc byte array trong bộ nhớ; tồn tại theo owner của output, không tự biến mất vì manager được đóng.
3. **Lớp đã định nghĩa trong JVM:** đối tượng `Class<?>` và instance liên kết với defining class loader; không được “unload trực tiếp” bằng `manager.close()` hoặc `URLClassLoader.close()`.

`URLClassLoader.close()` giải phóng tài nguyên mà URL loader sở hữu; nó không tự dừng thread, callback, registry, static references hay instance đã được tạo. Class loader có thể chỉ được thu gom khi không còn tham chiếu mạnh giữ nó/class liên quan, tùy GC và runtime.

Do đó vòng đời đủ gồm:

```text
Compile manager: OPEN -> task.call -> CLOSED
Artifact:        CREATED -> VALIDATED -> PUBLISHED -> RETIRED -> DELETED
Runtime loader:                       OPEN -> USE -> CLOSE -> eligible for GC
```

Đừng giữ `StandardJavaFileManager` bên trong object plugin hoặc cache dùng xuyên nhiều lần execute. Đừng xóa class files ngay lúc `close()` manager nếu việc load code còn chưa hoàn tất. Trên Windows, việc xóa JAR khi loader còn giữ handle đặc biệt dễ phát sinh lỗi; gắn thời điểm cleanup với lifetime của **runtime loader**, không chỉ compiler.

## 9. Khi nào được tái sử dụng StandardJavaFileManager?

Javadoc JavaCompiler cho phép **tái sử dụng standard file manager qua nhiều tác vụ biên dịch tuần tự**. Lý do có thể giảm chi phí đọc JAR và scan file system. Điều đó không có nghĩa mọi triển khai đều chịu được nhiều task đồng thời.

Hai chiến lược phổ biến:

### 9.1. File manager riêng cho mỗi build

```text
Job A: open manager A -> compile A -> close A -> validate A
Job B: open manager B -> compile B -> close B -> validate B
```

Ưu điểm: ownership rõ, không lẫn options/locations/cache giữa các build, dễ cô lập lỗi. Nhược điểm: có thể tốn công mở lại JAR và scan đường dẫn. Đây là lựa chọn hợp lý cho ứng dụng có lượng compile vừa phải hoặc yêu cầu tách biệt mạnh; ví dụ mục 4 áp dụng chiến lược này.

### 9.2. Reuse qua nhiều task tuần tự bên trong một phiên compile

```java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null, null)) {
    // Task 1 với manager đang mở: .call() hoàn tất.
    // Task 2 tuần tự cũng dùng manager này sau khi điều chỉnh cấu hình.
    // Các compilation units có thể được tạo lại trong scope này.
}
// Hết phiên: đóng manager một lần.
```

Đây là **mẫu vòng đời**, không phải chương trình độc lập. Tái sử dụng chỉ khi các tác vụ được sắp xếp **tuần tự**, manager chưa bị đóng, cấu hình output/class path được đặt lại đúng cho từng task, và không có reader nào dùng artifact chưa hoàn chỉnh. Nếu nhiều tenant/plugin muốn compile song song, đừng chia sẻ manager mà không có hợp đồng đồng bộ hóa cụ thể; có thể cấp manager riêng từng job hoặc một hàng đợi compile tuần tự.

JavaFileManager được phép **không hỗ trợ truy cập đa luồng trên chính manager đó**. API yêu cầu hỗ trợ concurrent access tới **các file object khác nhau** được tạo ra, nhưng điều này không biến toàn bộ manager thành thread-safe. Đó là một lý do khác để tránh dùng một manager shared toàn JVM theo kiểu không kiểm soát.

## 10. Phân tách bằng API kết quả: không đưa manager ra khỏi compile phase

Trong hệ thống lớn, có thể biểu diễn giao kèo giữa hai giai đoạn bằng DTO:

```java
record CompilationArtifact(
        String buildId,
        java.nio.file.Path outputDirectory,
        String mainClassName) {
}
```

Đây là **đoạn minh họa**. Một service dạng `CompilationArtifact compile(Request request)` có thể:

- Tạo output/metadata mới và manager riêng.
- Thu diagnostics cho đúng job.
- Chỉ trả artifact khi `call()` thành công, manager đã đóng, tệp và checksum đã được xác minh.
- Nếu thất bại, trả cấu trúc lỗi compile/diagnostics chứ không xuất bản artifact.
- Không trả `JavaFileManager`, `JavaFileObject` hoặc `CompilationTask` cho runtime consumer.

Bên thực thi nhận `CompilationArtifact`, tạo class loader/layer, kiểm tra entry point, chạy trong vòng đời được quản lý và cuối cùng dọn loader/artifact.

Để tránh race khi deploy nhiều bản, có thể dùng **build ID bất biến**, thư mục staging và thao tác xuất bản nguyên tử khi nền tảng file system cho phép. Điều kiện “artifact ready” phải gắn với **job compile cụ thể**, không phải một biến toàn cục dạng `lastSuccessfulCompile` có thể bị job khác ghi đè.

## 11. Classpath, module path và quan hệ giữa compile và execute

Cả hai giai đoạn phải nhìn thấy dependency phù hợp, nhưng **đường tìm kiếm của compiler không tự biến thành đường tìm kiếm của runtime class loader**.

Ví dụ, ở compile phase có thể cung cấp dependency jars:

```java
files.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(apiJar, dependencyJar));
files.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(outputDirectory));
```

Đây là **đoạn minh họa**, với `apiJar`, `dependencyJar` và `outputDirectory` là các `Path` có sẵn, không phải chương trình độc lập.

Runtime phải tạo loader với path tương ứng hoặc cung cấp API qua parent; nếu không, class biên dịch thành công có thể báo `NoClassDefFoundError` khi execute. Ngược lại, không nên mặc nhiên nạp tất cả thư viện của host vào loader plugin nếu chỉ một SPI được cho phép.

Với named modules (JPMS), compilation có thể cần `MODULE_PATH`, `MODULE_SOURCE_PATH`, `--module-path`, `--module-source-path` hoặc cấu hình output location theo module. Runtime có thể cần `ModuleFinder`, `Configuration` và `ModuleLayer`; `URLClassLoader` với thư mục class path đơn giản **không tự tạo named module layer**.

**Điều cần tách:** Ưu tiên class path hay module path trong compiler là cấu hình biên dịch, còn khả năng đọc module/class khi execute phụ thuộc class loader và module graph của runtime. Compile success chỉ chứng minh artifact phù hợp tại thời điểm compiler kiểm tra, không phải rằng runtime visibility chắc chắn tương đương.

### 11.1. Chọn API được chia sẻ giữa host và mã sinh

Nếu mã sinh implement một SPI do host định nghĩa, parent loader của runtime phải cung cấp **chính đối tượng `Class` của interface đó**; đừng để child nạp bản copy SPI khác. Trong ví dụ mục 4, parent là `ClassLoader.getPlatformClassLoader()` vì mã sinh không phụ thuộc host API. Đối với SPI tùy biến, thường phải dùng host/API loader làm parent hoặc chọn module layer phù hợp.

## 12. In-memory compilation: vẫn phải đóng manager và đóng luồng output

Một ứng dụng có thể cung cấp source bằng `SimpleJavaFileObject` trong bộ nhớ và dùng `ForwardingJavaFileManager` để nhận `.class` vào `ByteArrayOutputStream`. Cách này giảm ghi disk nhưng **không xóa nhu cầu quản lý vòng đời**:

- Wrapper manager nên delegate `close()`/`flush()` đúng xuống manager nền và đóng các luồng riêng mà nó sở hữu.
- Không dùng `JavaFileObject` phụ thuộc vào một manager đã đóng như kho lưu artifact lâu dài.
- Sau khi `task.call()` thành công, **snapshot byte arrays đã hoàn chỉnh** thành một map bất biến `binaryName -> byte[]` hoặc một đối tượng artifact tách biệt.
- Chỉ sau khi manager đóng và dữ liệu đã xác minh mới cấp map đó cho một custom class loader dùng `defineClass`.
- Custom manager phải tuân theo hợp đồng `getJavaFileForOutput`, đóng stream, tính thread safety và luồng thông báo diagnostic. Không phải cứ override một phương thức là tương thích mọi compiler.

Luồng tương đương:

```text
Source JavaFileObject trong bộ nhớ
  -> JavaCompiler + ForwardingJavaFileManager
  -> output streams/byte buffers
  -> task.call() thành công
  -> đóng output streams và JavaFileManager
  -> artifact snapshot bất biến
  -> ByteArrayClassLoader định nghĩa lớp
  -> invoke
```

Đây là **sơ đồ kiến trúc**, không phải mã chạy. Với use case cơ bản, dùng `StandardJavaFileManager` và output directory của mục 4 đơn giản và đáng tin hơn. Nếu cần in-memory compiler, hãy kiểm thử khắt khe việc stream được đóng, dữ liệu không bị thay đổi giữa compile và load, các class phụ thuộc lẫn nhau và class identity.

## 13. Đường lỗi đúng tầng: compile, close, load và execute

| Triệu chứng | Nguồn gốc thường gặp | Phản ứng đúng |
|---|---|---|
| `getSystemJavaCompiler() == null` | Không có compiler trong runtime image/JDK hiện tại | Không compile; báo yêu cầu runtime có `jdk.compiler` |
| `CompilationTask.call() == false` | Source sai hoặc compiler báo lỗi | Lấy diagnostics và dừng trước load |
| `IllegalArgumentException` từ `getTask` hoặc options | Option/compilation units không hợp lệ | Sửa cấu hình job, không fallback sang artifact cũ |
| `IOException` khi tạo output/get file/close manager | File system, quyền truy cập, handle hoặc storage | Đánh dấu build chưa hoàn chỉnh, không publish |
| `Files.isRegularFile(...) == false` | Artifact không được sinh như kỳ vọng | Validation thất bại, không execute |
| `ClassNotFoundException` | Class loader không thấy đúng binary name/path | Kiểm tra output path và loader configuration |
| `NoClassDefFoundError` | Dependency thiếu hoặc linking lỗi | Kiểm tra class path/module graph ở execute |
| `UnsupportedClassVersionError` | Artifact được build cho runtime mới hơn | Dùng `--release` phù hợp và xác minh môi trường |
| `ExceptionInInitializerError` | Static initialization của class sinh ném lỗi | Chẩn đoán logic execute, không thay đổi compile verdict |
| `InvocationTargetException` | Method/constructor được gọi qua reflection ném exception | Kiểm tra `getCause()` và chính sách thực thi |
| Không xóa/thay thế được JAR sau compile | Manager hoặc runtime loader còn giữ handle | Đóng manager ở compile phase và loader đúng lifetime; không xóa khi đang dùng |
| Chạy sai phiên bản sau khi compile lỗi | Output path bị dùng lại; class cũ vẫn có | Dùng output theo build ID, chỉ publish build mới đã xác thực |

Một hệ thống cần phân biệt **biên dịch lỗi**, **lỗi đóng tài nguyên**, **artifact validation lỗi** và **execution lỗi** để báo cáo chính xác. Gộp mọi lỗi thành `catch (Exception) { return false; }` khiến thiếu diagnostics, khó dọn tài nguyên và có thể kích hoạt fallback nguy hiểm.

## 14. Đồng thời, thread pool và ownership của file manager

Biên dịch thường tốn CPU, I/O và bộ nhớ. Khi nhiều request đến đồng thời:

1. Tạo job ID riêng và output directory riêng.
2. Cấp file manager mới cho mỗi job hoặc dùng pool/queue có giới hạn concurrency và policy rõ ràng.
3. Chặn cùng một file manager bị hai compilation task truy cập đồng thời nếu chưa có hợp đồng thread safety.
4. Bảo đảm lớp nguồn và dependency input không bị sửa giữa chừng khi compiler đang đọc. Với pipeline nghiêm ngặt, snapshot source/JAR đã chọn trước compile.
5. Không cho executor tự tiếp tục execute chỉ dựa vào việc “đã gửi task compile”; chờ kết quả compile + close + artifact validation của đúng job.
6. Khi hủy task, kiểm tra interrupted/cancellation behavior thật của compiler implementation. Không giả định gọi `Future.cancel(true)` ngay lập tức dừng javac và dọn mọi output; phải dọn artifact chưa publish sau khi bảo đảm job không còn ghi.
7. Khi unload plugin, gỡ callbacks/threads/reference trước khi đóng class loader, rồi dọn artifact khi không còn lượt thực thi sử dụng.

**Ownership phù hợp:** compiler manager thuộc một compile scope; runtime loader thuộc một execution/plugin scope; output artifact thuộc một build/version scope. Đừng thiết kế ba vòng đời này thành một singleton khó kiểm soát.

## 15. Bảo mật: biên dịch runtime không phải sandbox

Chỉ vì `JavaCompiler` nhận một chuỗi source không có nghĩa mã được sinh là an toàn để chạy trong cùng JVM. Compiler có thể đọc nhiều file/classpath entry hoặc chạy **annotation processor** nếu được cấu hình; mã đã biên dịch có thể mở file, dùng mạng, tạo thread, chặn luồng hay gọi API nguy hiểm theo quyền tiến trình.

Các biện pháp cần có theo mô hình tin cậy:

- Hạn chế source size, số file, độ phức tạp và concurrency; dùng timeout/CPU/memory limits **ở biên tiến trình** khi cần mức cô lập mạnh.
- Chỉ dùng những class path/module path được chủ sở hữu cho phép, tránh rò thông tin từ application class path không kiểm soát.
- Ví dụ dùng `-proc:none` để vô hiệu annotation processing trong job mẫu. Đây **không phải sandbox**, không ngăn mã sinh chạy sau compilation.
- Biên dịch bằng `--release 17` để nhắm API/language/class-file target của Java 17, nhưng vẫn phải kiểm tra runtime dependencies; flag này không hạn chế quyền của mã được thực thi.
- Không chạy source không tin cậy trực tiếp trong cùng JVM chỉ nhờ `URLClassLoader`/`ProtectionDomain`. Class loader tạo ranh giới type/visibility, không cung cấp cách ly tài nguyên và quyền hệ điều hành.
- Nếu cần nhận mã từ bên ngoài tổ chức, cân nhắc worker process/container riêng với filesystem, network, memory và quyền hạn được hạn chế, IPC rõ ràng và lifecycle dọn dẹp.

Bảo mật của compile phase và execute phase có thể khác nhau: compiler worker có thể chỉ có quyền ghi thư mục staging, còn runtime worker chỉ cần đọc artifact đã được publish. Sự tách biệt này giúp kiểm toán, rollback và tránh mở rộng quyền không cần thiết.

## 16. Bộ test nên có cho một runtime compiler

| Kiểm thử | Kỳ vọng |
|---|---|
| Source hợp lệ | `call()` true, manager đóng, artifact có đủ, loader nạp và invoke đúng |
| Source sai cú pháp | `call()` false, nhận ERROR diagnostics, không tạo loader và không execute |
| File output thiếu/không hợp lệ | Bước validation dừng trước execute, không dùng artifact khác |
| `close()` ném `IOException` | Job không được publish thành công; lỗi được giữ nguyên/suppressed đúng |
| Hai lượt compile cùng binary name | Hai output/build ID riêng; runtime không nạp nhầm class phiên trước |
| Compiler không khả dụng | Báo rõ không có `jdk.compiler`; không dùng reflection gọi class cũ |
| Hai job chạy đồng thời | Output, diagnostics, file manager và trạng thái tách theo job |
| Sai dependency khi execute | Ghi nhận lỗi load/link riêng, không coi compile diagnostics là nguồn duy nhất |
| Method sinh ném exception | Compile thành công nhưng execution thất bại; `InvocationTargetException.getCause()` được xử lý đúng |
| Hủy task / timeout | Không publish artifact dở dang; không xóa output khi worker vẫn đang ghi |
| Dùng in-memory manager | Stream đóng, bytes được snapshot, manager nền được close, loader độc lập với manager |
| Unload/redeploy plugin | Không còn listener, thread, cache, TCCL, loader reference giữ phiên cũ |
| Runtime thiếu quyền I/O | Báo đúng lỗi file manager/output; tuyệt đối không fallback âm thầm |

Một bài test tích hợp có giá trị nhất là: **biên dịch phiên A thành công → sửa source thành lỗi ở phiên B → xác minh B không chạy A.class**. Nếu test này thất bại, pipeline chưa thực sự tách compile với execute theo build identity.

## 17. Những lỗi thiết kế cần tránh

- Gọi `getTask(...).call()` rồi chạy mã ngay trong `try` của manager dù không có lý do giữ manager mở.
- Chỉ đóng manager ở đường thành công, quên `try-with-resources` nên lỗi runtime hoặc compile làm rò file handle.
- Nhầm `flush()` với `close()`, hoặc tiếp tục dùng file objects sau khi manager đóng.
- Tái sử dụng một manager cho nhiều compilation jobs đồng thời khi không có hợp đồng thread safety.
- Dùng chung output directory và chỉ kiểm tra “có file class” mà không kiểm tra build ID + kết quả task.
- Coi `compiled=true` là `executed=true` hoặc không phân biệt compile error với exception từ method sinh.
- Sử dụng compiler class path làm mặc định runtime class path mà không kiểm tra ranh giới SPI/type identity.
- Đóng `URLClassLoader` như thể nó tự unload class hay dừng các thread/callback đang sống.
- Ghi class file vào thư mục dùng chung có tên dự đoán được và cho nhiều tenant ghi chồng nhau.
- Dùng `-proc:none` hoặc custom class loader như giải pháp bảo mật hoàn chỉnh cho mã không tin cậy.
- Xóa artifact ngay sau khi đóng file manager mặc dù class loader runtime chưa đọc xong hoặc còn cần load lazy dependency.

**Checklist gọn khi review code:** (1) file manager có owner và scope rõ; (2) compile + close kết thúc trước execute; (3) output độc lập theo build; (4) lỗi compile chặn load; (5) artifact được validate; (6) runtime loader được đóng theo lifecycle riêng; (7) cleanup không động vào build đang được dùng.

## 18. Kết luận và tài liệu chuẩn

Bộ đôi `JavaCompiler` + `StandardJavaFileManager` giải quyết việc **sinh bytecode**; `ClassLoader`/`ModuleLayer` giải quyết việc **nạp và thực thi bytecode**. Hai phần có mối quan hệ dữ liệu thông qua artifact nhưng không nên chia sẻ vòng đời tài nguyên.

Quy tắc có thể áp dụng ngay:

1. Nhận source và tạo output directory riêng theo build.
2. Dùng `JavaCompiler.getTask(...).call()` trong scope `try (StandardJavaFileManager ...)`.
3. Rời scope để manager được `close()`; chỉ coi compile thành công nếu task và close đều thành công.
4. Nếu compile thất bại, dừng và trả diagnostics; tuyệt đối không nạp output cũ.
5. Xác minh artifact thuộc đúng build, rồi mới tạo loader, nạp class, execute.
6. Đóng loader và thu gom artifact theo vòng đời thực thi, không theo vòng đời file manager.

Tài liệu chính thức Java SE 17: [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html), [StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html), [ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html).
