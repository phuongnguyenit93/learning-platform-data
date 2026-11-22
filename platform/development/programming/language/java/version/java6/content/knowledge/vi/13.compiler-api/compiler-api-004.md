# StandardJavaFileManager và các JavaFileObject trong Java Compiler API

## 1. Mục tiêu bài học

Khi biên dịch Java ngay từ một ứng dụng Java (thay vì khởi chạy tiến trình `javac`), `JavaCompiler` cần hai thứ: **các đơn vị mã nguồn cần biên dịch** và **một cơ chế tìm/đọc/ghi tệp**. Trong Java Compiler API (`javax.tools`):

- `JavaFileObject` biểu diễn một nguồn hoặc sản phẩm biên dịch ở mức trừu tượng (mã nguồn `.java`, bytecode `.class`, v.v.).
- `JavaFileManager` định nghĩa hợp đồng tìm, đọc, ghi các file object.
- `StandardJavaFileManager` là file manager tiêu chuẩn để tương tác thuận tiện với **tệp và đường dẫn trên hệ thống tệp**, classpath/module path và thư mục output.
- `SimpleJavaFileObject` là lớp nền để tự xây `JavaFileObject`, đặc biệt hữu ích khi mã nguồn nằm trong một `String` thay vì tệp vật lý.

Đây vẫn là các API chính thức của Java hiện đại, đặc biệt hữu ích cho công cụ sinh mã, chạy trình biên dịch trong build tool, IDE, kiểm tra mã nguồn động và kiểm thử code generator. Ví dụ chạy được bằng **JDK 17+**; phần lưu ý về module và API mới được nêu rõ theo phiên bản.

Sau bài học, bạn có thể tạo `StandardJavaFileManager`, chuyển `Path` thành `JavaFileObject`, cấu hình nơi xuất `.class`, biên dịch kết hợp mã nguồn trên đĩa và trong bộ nhớ, đọc chẩn đoán, quản lý tài nguyên đúng cách và tránh các overload đã bị đánh dấu deprecated.

## 2. Bản đồ các thành phần và luồng dữ liệu

```text
Nguồn do ứng dụng cung cấp
├─ Path của Demo.java                  (tệp vật lý)
│   └─ StandardJavaFileManager
│       └─ JavaFileObject.Kind.SOURCE
└─ String chứa mã Java                 (không có tệp nguồn)
    └─ SimpleJavaFileObject tùy biến
        └─ JavaFileObject.Kind.SOURCE
                     │
                     ▼
            JavaCompiler.getTask(...)
               + options
               + DiagnosticListener
               + JavaFileManager
                     │
              CompilationTask.call()
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
  Diagnostic<JavaFileObject>   JavaFileManager
  lỗi/cảnh báo/vị trí             ghi đầu ra
                                      │
                                      ▼
                            JavaFileObject.Kind.CLASS
                            thư mục CLASS_OUTPUT
```

Cần phân biệt **đơn vị biên dịch** với **file manager**. `JavaFileObject` là đối tượng đại diện cho *một file*; `StandardJavaFileManager` là thành phần quản lý *cách tìm, đọc và xuất nhiều file*. Compiler quyết định cách phân tích mã nguồn, còn file manager đảm nhận thao tác lưu trữ.

Ví dụ tạo compiler và manager:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Cần JDK có module jdk.compiler");
}

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
    // Thiết lập locations, tạo compilation units, gọi compiler.getTask(...).
}
```

Đoạn trên là **minh họa chưa độc lập**; phần 6 có chương trình hoàn chỉnh. Cần có một JDK mang triển khai compiler: `getSystemJavaCompiler()` có thể trả `null` trong runtime đã được đóng gói mà không có compiler. `StandardJavaFileManager` kế thừa `Closeable` nên dùng `try-with-resources` để đảm bảo giải phóng tài nguyên.

## 3. `FileObject`, `JavaFileObject` và `Kind`

### 3.1. `FileObject`: giao diện file trừu tượng

`javax.tools.FileObject` mô tả cách truy cập dữ liệu của một đối tượng kiểu file, với những thao tác quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `toUri()` | URI nhận diện file object; không buộc là URI của tệp đĩa. |
| `getName()` | Tên thuận tiện cho người đọc; không nhất thiết trùng đường dẫn vật lý. |
| `getCharContent(boolean)` | Trả nội dung dưới dạng ký tự khi implementation hỗ trợ. |
| `openReader(boolean)` / `openInputStream()` | Đọc nội dung qua luồng, cần đóng luồng được mở. |
| `openWriter()` / `openOutputStream()` | Ghi nội dung khi implementation cho phép. |
| `getLastModified()`, `delete()` | Thông tin thay đổi/xóa nếu loại file object hỗ trợ. |

`FileObject` là một trừu tượng, **không phải mặc định một `java.io.File` hay `Path`**. Nếu object có URI như `string:///demo/Memory.java`, bạn không thể coi nó là tệp trên đĩa và gọi `Path.of(uri)` một cách tùy tiện.

### 3.2. `JavaFileObject`: có thêm ý nghĩa ngôn ngữ Java

`javax.tools.JavaFileObject` mở rộng `FileObject` để cung cấp:

- `getKind()`: loại file.
- `isNameCompatible(simpleName, kind)`: kiểm tra tên đơn giản có phù hợp với loại file không.
- `getNestingKind()`, `getAccessLevel()`: các gợi ý về kiểu lồng nhau và cấp truy cập, có thể trả `null` nếu không biết.

`JavaFileObject.Kind` có bốn giá trị:

| Kind | Ví dụ | Khi nào dùng |
| --- | --- | --- |
| `SOURCE` | `Example.java` | Đơn vị đầu vào để compiler phân tích và biên dịch. |
| `CLASS` | `Example.class` | Bytecode đầu ra hoặc file class được tìm để resolve phụ thuộc. |
| `HTML` | `Example.html` | Loại tài liệu HTML trong giao diện file object. |
| `OTHER` | Tệp khác | Dữ liệu không thuộc các loại trên. |

Không thể chỉ đổi tên file `.txt` thành `.java` rồi mặc nhiên có `JavaFileObject` hợp lệ: khi tạo object tùy biến phải bảo đảm **`Kind`, URI, nội dung và tên lớp/package** nhất quán với hợp đồng compiler.

`JavaCompiler.getTask(...)` chấp nhận `Iterable<? extends JavaFileObject>` làm compilation units; **các đơn vị dùng để biên dịch mã nguồn phải có `Kind.SOURCE`**. File `.class` thường được compiler tìm hoặc ghi qua `JavaFileManager`, không đưa vào danh sách source compilation units.

## 4. `StandardJavaFileManager`: nguồn, classpath và đầu ra

### 4.1. Lấy file objects từ `Path`

Sau khi đã có `StandardJavaFileManager manager`, có thể biến một hoặc nhiều tệp `.java` có thật thành compilation units:

```java
Path source = Path.of("src/main/java/demo/Hello.java");

Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(List.of(source));
```

`getJavaFileObjectsFromPaths(Collection<? extends Path>)` là overload nên ưu tiên trong Java hiện đại (**từ Java 13**). Truyền `List.of(source)` chọn đúng overload `Collection`; overload cùng tên nhận `Iterable<? extends Path>` đã **deprecated**. Đây là khác biệt quan trọng khi chọn API tránh lỗi thời.

Nếu chỉ có vài `Path`, có thể dùng overload varargs:

```java
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjects(
                Path.of("src/main/java/demo/Hello.java"));
```

Hai ví dụ trên giả định đường dẫn là **tệp nguồn có thật** và `manager` còn mở. Không truyền một thư mục vào phương thức tạo `JavaFileObject` cho file; muốn biên dịch cả cây thư mục thì ứng dụng tự tìm các tệp `.java` cần thiết trước (ví dụ qua `Files.walk` được đóng đúng cách).

Các API `getJavaFileObjectsFromFiles(...)` hoặc `getJavaFileObjectsFromStrings(...)` vẫn tồn tại và dùng được, nhưng nếu ứng dụng đã sử dụng `java.nio.file.Path` thì phương thức nhận `Path` thuận tiện hơn.

### 4.2. Thiết lập `StandardLocation`

Một location mô tả vai trò của đường dẫn trong quá trình biên dịch. Các location phổ biến:

| `StandardLocation` | Vai trò |
| --- | --- |
| `CLASS_OUTPUT` | Nơi compiler ghi `.class`. |
| `SOURCE_OUTPUT` | Nơi ghi mã nguồn được sinh, ví dụ từ annotation processor. |
| `CLASS_PATH` | Các thư mục/JAR để tìm class phụ thuộc theo cơ chế classpath. |
| `SOURCE_PATH` | Nơi compiler có thể tìm source bổ sung. |
| `MODULE_PATH` | Đường dẫn tìm module trong dự án JPMS. |
| `MODULE_SOURCE_PATH` | Bố cục đường dẫn mã nguồn của các module. |

Cấu hình output:

```java
Path output = Files.createDirectories(Path.of("build/generated-classes"));

manager.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(output));
```

`CLASS_OUTPUT` là location xuất, nên ở đây cung cấp **một đường dẫn thư mục tồn tại**. Nếu cung cấp nhiều đường dẫn cho output location hoặc thư mục không hợp lệ, manager có thể ném ngoại lệ; luôn tạo thư mục trước.

Đặt classpath theo nhu cầu thực tế của chương trình:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("libs/dependency.jar"), Path.of("build/classes")));
```

Đoạn trên là **minh họa** khi các đường dẫn tồn tại và phù hợp; không phải lệnh bắt buộc cho mọi bản biên dịch. `setLocationFromPaths` sẽ thay location tương ứng, nên nếu bạn đặt `CLASS_PATH` thủ công, phải tự liệt kê đúng các phụ thuộc. Không áp nguyên mẫu này cho module path mà không xét `module-info.java` và `--module-path`.

Có thể đọc vị trí đã cấu hình bằng:

```java
Iterable<? extends Path> outputLocations =
        manager.getLocationAsPaths(StandardLocation.CLASS_OUTPUT);
```

Kết quả có thể là `null` nếu location chưa được thiết lập hoặc không có đường dẫn liên kết; không giả định luôn có một giá trị.

### 4.3. Tìm file đầu vào và đầu ra

`StandardJavaFileManager` triển khai `JavaFileManager`, trong đó có các phương thức:

```java
JavaFileObject compiled = manager.getJavaFileForInput(
        StandardLocation.CLASS_OUTPUT,
        "demo.Hello",
        JavaFileObject.Kind.CLASS);
```

Phương thức này yêu cầu file object tương ứng với binary name `demo.Hello` trong location đầu ra, nếu có. Nó có thể trả `null` nếu không tìm thấy file. Tên `demo.Hello` là **binary class name**, không phải đường dẫn `demo/Hello.class`.

Khi biên dịch, compiler thường dùng `getJavaFileForOutput(...)` của file manager để yêu cầu nơi ghi class file. Với `StandardJavaFileManager`, kết quả thông thường được lưu trên đĩa tại `CLASS_OUTPUT`. Nếu bạn muốn chặn đầu ra để ghi bytecode vào bộ nhớ, đó là bài toán của **file manager tùy biến**; một phương án thường dùng là `ForwardingJavaFileManager` bao quanh manager tiêu chuẩn và tùy biến `getJavaFileForOutput(...)`.

## 5. Dữ liệu trong bộ nhớ: `SimpleJavaFileObject`

`SimpleJavaFileObject` là lớp tiện ích để xây dựng `JavaFileObject` tùy biến. Để biên dịch một chuỗi mã Java, tạo object loại `SOURCE` với URI phù hợp và override `getCharContent(...)`.

Ví dụ class tối thiểu dùng được từ Java 17:

```java
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///"
                        + binaryName.replace('.', '/')
                        + JavaFileObject.Kind.SOURCE.extension),
                JavaFileObject.Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Nếu `binaryName = "demo.Hello"`, URI sẽ là `string:///demo/Hello.java`, phù hợp tên package/class của mã nguồn `package demo; public class Hello {...}`.

Điểm quan trọng:

- `getCharContent(...)` là đường đọc ký tự của source object trong bộ nhớ; compiler không bắt bạn lưu chuỗi thành `.java` vật lý.
- URI phải có dạng hợp lệ và đường dẫn phù hợp với tên lớp; với `public class`, tên đơn vị nguồn phải nhất quán.
- Không tự cho rằng mọi method đọc/ghi đều hoạt động. Implementation mặc định của `SimpleJavaFileObject` có thể ném `UnsupportedOperationException` với các thao tác chưa được override.
- `JavaFileObject.Kind.CLASS` dùng cho bytecode; nếu muốn giữ bytecode trong RAM, cần triển khai object đầu ra có `openOutputStream()` và kết nối nó với file manager thích hợp.

Không cần tự kế thừa `SimpleJavaFileObject` nếu bạn đã có một `Path` trỏ tới file: `StandardJavaFileManager` đã tạo được file object thích hợp. Chỉ dùng object tùy biến khi cần một nguồn dữ liệu không nằm ở filesystem mặc định hoặc cần kiểm soát hành vi I/O.

## 6. Chương trình độc lập: biên dịch source trên đĩa và trong RAM

Ví dụ dưới đây dùng **một file `.java` trên đĩa** và **một `String` chứa mã Java** làm hai compilation units. Compiler sẽ ghi **hai file `.class`** vào thư mục output do `StandardJavaFileManager` quản lý; mã nguồn trong bộ nhớ không cần được xuất thành `Memory.java`.

### 6.1. Tệp `FMTest.java`

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.tools.*;

public class FMTest {
    static class MemorySource extends SimpleJavaFileObject {
        String code;

        MemorySource(String name, String code) {
            super(URI.create("string:///"
                            + name.replace('.', '/')
                            + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        Path folder = Files.createTempDirectory("fm-run-");
        Path output = Files.createDirectories(folder.resolve("out"));
        Path file = folder.resolve("Disk.java");
        Files.writeString(
                file, "public class Disk {}", StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with jdk.compiler is required");
        }

        DiagnosticCollector<JavaFileObject> issues =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             issues, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));

            List<JavaFileObject> units = new ArrayList<>();
            for (JavaFileObject source :
                    manager.getJavaFileObjectsFromPaths(List.of(file))) {
                units.add(source);
            }
            units.add(new MemorySource(
                    "Memory", "public class Memory {}"));

            System.out.println("units=" + units.size());
            System.out.println("kinds="
                    + units.get(0).getKind()
                    + "," + units.get(1).getKind());

            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(
                            null, manager, issues,
                            List.of("-proc:none"), null, units)
                            .call());

            System.out.println("compiled=" + ok);
            System.out.println(
                    "disk=" + Files.exists(output.resolve("Disk.class")));
            System.out.println(
                    "memory=" + Files.exists(output.resolve("Memory.class")));
            System.out.println("errors="
                    + issues.getDiagnostics().stream()
                            .filter(d -> d.getKind()
                                    == Diagnostic.Kind.ERROR)
                            .count());

            JavaFileObject result = manager.getJavaFileForInput(
                    StandardLocation.CLASS_OUTPUT,
                    "Disk", JavaFileObject.Kind.CLASS);
            System.out.println("outputKind=" + result.getKind());
        }

        try (var paths = Files.walk(folder)) {
            for (Path p : paths.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
        }
    }
}
```

Chương trình dùng `Files.createTempDirectory` để không cần chuẩn bị cây thư mục nguồn. Sau khi biên dịch thành công, nó xóa các file test từ dưới lên trên. Trong chương trình thật, nên đặt việc xóa thư mục tạm trong `finally` để dọn dẹp ngay cả khi có lỗi giữa chừng; ví dụ giữ phần luồng chính ngắn để dễ thấy cách phối hợp các API.

### 6.2. Biên dịch và chạy

Lưu mã thành `FMTest.java` và chạy tại thư mục chứa file. Cần JDK 17 hoặc mới hơn:

```bash
javac --release 17 FMTest.java
java FMTest
```

**Stdout của chương trình:**

```text
units=2
kinds=SOURCE,SOURCE
compiled=true
disk=true
memory=true
errors=0
outputKind=CLASS
```

Diễn giải từng kết quả:

1. `units=2`: một `JavaFileObject` do manager tạo từ `Path` và một `MemorySource` tự viết.
2. `kinds=SOURCE,SOURCE`: cả hai đều là mã nguồn; input của `getTask(...)` không phải bytecode `.class`.
3. `compiled=true`, `errors=0`: `CompilationTask.call()` thành công và collector không nhận diagnostic mức `ERROR`.
4. `disk=true`, `memory=true`: **dù một source nằm trong bộ nhớ**, sản phẩm biên dịch của cả hai vẫn được manager ghi vào thư mục `CLASS_OUTPUT`.
5. `outputKind=CLASS`: truy vấn lại `Disk.class` qua `getJavaFileForInput` trả object loại `CLASS`.

`javac --release 17 FMTest.java` ở đây yêu cầu compiler bên ngoài xây chính chương trình demo tương thích Java 17. Nếu ứng dụng biên dịch mã khách hàng bằng `compiler.getTask` và cũng cần bytecode Java 17, hãy truyền thêm option `"--release", "17"` vào **task bên trong**. Hai lần biên dịch là hai tác vụ riêng biệt, không tự thừa hưởng cài đặt `--release` của nhau.

Giải thích option `List.of("-proc:none")`: không chạy annotation processing trong demo, tránh phụ thuộc processor có trên classpath. Khi thực sự cần annotation processor, hãy chủ động cấu hình processor path/module path và chính sách chạy phù hợp.

## 7. Chuẩn đoán lỗi đúng cách

`DiagnosticCollector<JavaFileObject>` là một implementation của `DiagnosticListener`, có thể nhận lỗi, cảnh báo và vị trí nguồn. Khi biên dịch thất bại, `CompilationTask.call()` thường trả `false`; lỗi cú pháp Java bình thường không nên được kiểm tra bằng cách chỉ bắt `IOException`.

Ví dụ **đoạn thêm vào chương trình đang có `issues`**:

```java
boolean success = Boolean.TRUE.equals(task.call());

for (Diagnostic<? extends JavaFileObject> d :
        issues.getDiagnostics()) {
    System.out.printf(
            "%s line=%d col=%d: %s%n",
            d.getKind(),
            d.getLineNumber(),
            d.getColumnNumber(),
            d.getMessage(Locale.ROOT));
}

if (!success) {
    throw new IllegalStateException("Compilation failed");
}
```

Đây là đoạn minh họa cho một biến `task` đã được khai báo là `JavaCompiler.CompilationTask`; **không phải chương trình standalone**. `Diagnostic.Kind` thường gặp: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. Vị trí dòng/cột có thể không xác định trong một số diagnostic, vì vậy không dùng chúng làm số dương bắt buộc.

Một mẫu cấu hình lỗi phổ biến:

```java
DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("-proc:none", "-encoding", "UTF-8"),
        null, sourceUnits);
```

`getTask` có sáu tham số theo thứ tự: `out` (`Writer` có thể `null`), `fileManager`, `diagnosticListener`, `options`, `classes`, `compilationUnits`. Dùng `null` cho `classes` khi biên dịch một tập source đơn giản. `getTask` chỉ *tạo tác vụ*; `task.call()` mới *thực hiện tác vụ*. Mỗi `CompilationTask` chỉ nên được gọi một lần.

Đừng in tuyệt đối nội dung thông báo diagnostic làm expected output của test đa nền tảng: văn bản có thể phụ thuộc locale, phiên bản JDK và loại lỗi. Để kiểm thử, thường so sánh `boolean` của task, `Diagnostic.Kind`, nguồn hoặc vị trí phù hợp và sự tồn tại của file đầu ra.

## 8. Vòng đời file manager: `close()`, `flush()` và tái sử dụng

Một `StandardJavaFileManager` có thể được **dùng lại cho nhiều compilation tasks** và có thể cache thông tin về JAR/file system để tiết kiệm thao tác I/O khi thực hiện các lần biên dịch liên tiếp. Tái sử dụng manager hợp lý trong cùng một tác vụ build có thể cải thiện hiệu suất.

```java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

    // Lần 1: tạo compilation task mới, gọi task1.call().
    // Lần 2: tạo compilation task khác, gọi task2.call().
    // Mỗi lần phải cung cấp đúng units, options, locations.
}
```

Lưu ý:

- `flush()` yêu cầu đẩy nội dung đã ghi ra nơi lưu trữ nhưng **không đồng nghĩa đóng manager**.
- `close()` giải phóng các tài nguyên mà manager đã mở, chẳng hạn file handles. `try-with-resources` gọi `close()` cả khi có ngoại lệ.
- Không sử dụng file object lấy từ manager sau khi đóng manager trừ khi implementation/hợp đồng của object đó cho phép rõ ràng; với thiết kế thường gặp, xem chúng là các resource gắn với vòng đời manager.
- Không mặc định một manager có thể chạy đồng thời nhiều compilation tasks trên các luồng khác nhau. Nếu cần biên dịch song song, cân nhắc mỗi task một manager hoặc thiết kế bảo vệ tài nguyên rõ ràng.
- Cấu hình location có thể được thay đổi giữa các compilation tasks nếu cần; cần hiểu hệ quả trên cache/đầu ra. Không đóng manager rồi cố tiếp tục dựa vào trạng thái trước đó.

Bộ nhớ đệm của file manager (tài nguyên và thông tin file) không phải một “cache kết quả biên dịch” chung. Tái sử dụng manager không thay thế cho công cụ incremental compilation hay tự động xác định các source cần biên dịch lại.

## 9. Classpath, module path và mối quan hệ với compiler

### 9.1. Classpath truyền thống vẫn đang được hỗ trợ

Với mã nguồn không dùng Java modules, file manager có thể tìm thư viện ở `CLASS_PATH` và ghi class vào `CLASS_OUTPUT`. Nếu thư viện phụ thuộc ở nơi khác, cấu hình `CLASS_PATH` hoặc truyền compiler option tương đương có chủ đích; không giả định task tự tìm mọi JAR trong dự án.

Ví dụ **minh họa** với thư mục/JAR thực sự tồn tại:

```java
manager.setLocationFromPaths(
        StandardLocation.CLASS_PATH,
        List.of(Path.of("libs/util.jar"),
                Path.of("build/dependency-classes")));
```

Khi set location mới, giá trị cũ bị thay thế. Đừng vô tình loại bỏ toàn bộ phụ thuộc mặc định nếu ứng dụng cần chúng. Có thể đọc lại bằng `getLocationAsPaths(CLASS_PATH)`.

### 9.2. Dự án dùng JPMS

Từ Java 9, hệ thống module dùng những location và option riêng như `MODULE_PATH`, `MODULE_SOURCE_PATH` và `--module-path`. Đối với dự án có `module-info.java`, xem xét rõ module graph, layout nguồn và output theo module; không lấy một ví dụ classpath rồi coi là cấu hình đầy đủ của compilation task theo module.

`JavaFileManager` và `StandardJavaFileManager` có các phương thức như `getLocationForModule(...)`, `listLocationsForModules(...)` và `setLocationForModule(...)`. Chúng giúp tools xử lý location theo module khi implementation hỗ trợ. `setLocationFromPaths` trên location module-oriented/output có thể thay các mapping module-specific trước đó; tránh trộn hai cách cấu hình mà không kiểm tra.

Khi chương trình của bạn nằm trong **named module** và dùng Java Compiler API, cần khai báo đọc module API `java.compiler`. Để lấy compiler mặc định trên JDK cần triển khai phù hợp có sẵn; runtime thu gọn có thể không chứa `jdk.compiler`.

## 10. Phân biệt đầu vào trên đĩa, đầu vào RAM và đầu ra RAM

| Mong muốn | Hướng đi phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Biên dịch file `.java` có thật | `StandardJavaFileManager.getJavaFileObjectsFromPaths(...)` | `Path` trỏ file hợp lệ; charset; locations. |
| Biên dịch mã Java nằm trong `String` | `SimpleJavaFileObject` với `Kind.SOURCE` và `getCharContent(...)` | URI/tên package và public class; compiler có thể đọc nội dung. |
| Ghi `.class` ra thư mục | `StandardJavaFileManager` + `CLASS_OUTPUT` | Thư mục tồn tại; sản phẩm output thực sự được tạo. |
| Nhận bytecode trong RAM | `ForwardingJavaFileManager` + object `Kind.CLASS` có `openOutputStream()` | Quản lý tên lớp, byte array, streams và ownership. |
| Đọc diagnostic cho source RAM | `DiagnosticCollector`, dùng `JavaFileObject` source trong diagnostic | Vị trí/URI có thể là `string:///...`; không giả định có đường dẫn vật lý. |
| Nạp class vừa tạo vào JVM | Class loader riêng, sau khi biên dịch thành công | Compiler không tự nạp class vào ứng dụng; classloader, dependencies và lifecycle do ứng dụng quản lý. |

Nếu muốn ghi đầu ra vào RAM, ví dụ về kiến trúc (không phải code standalone) là: dùng `ForwardingJavaFileManager<StandardJavaFileManager>`, override `getJavaFileForOutput(...)` để trả `SimpleJavaFileObject` có `Kind.CLASS`, triển khai `openOutputStream()` để ghi vào `ByteArrayOutputStream`, sau đó đưa bytecode tới class loader phù hợp. Không có lý do phải thay toàn bộ hành vi đọc file của standard manager khi chỉ cần tùy biến output.

## 11. Kiểm thử và kiểm soát các trường hợp lỗi

Một bộ test có giá trị nên xác minh **hành vi public API**, không phụ thuộc class nội bộ của JDK:

| Test case | Chuẩn bị | Assertion |
| --- | --- | --- |
| Source vật lý | Tạo tệp `Disk.java`, chuyển qua manager | Object có `Kind.SOURCE`, biên dịch tạo `Disk.class`. |
| Source trong bộ nhớ | `MemorySource` với URI `string:///Memory.java` | Không cần file `Memory.java` trên đĩa nhưng compile tạo `Memory.class`. |
| Lỗi cú pháp | Một source có Java syntax không hợp lệ | `task.call()` trả `false`, collector có diagnostic mức `ERROR`. |
| Thư mục output | Tạo folder tạm, gắn `CLASS_OUTPUT` | `.class` đúng tên/package nằm trong folder chỉ định. |
| Charset | Source có ký tự Unicode hợp lệ | `getStandardFileManager(..., UTF_8)` đọc đúng; dùng `-encoding UTF-8` nếu cấu hình options. |
| Tên file không khớp | `public class Wrong` trong `Right.java` | Biên dịch thất bại với diagnostic; không dựa vào nguyên văn lỗi cụ thể. |
| Không có compiler | Môi trường không cung cấp system Java compiler | Xử lý `getSystemJavaCompiler() == null` bằng thông báo rõ yêu cầu JDK. |
| Đóng tài nguyên | Manager/streams trong `try-with-resources` | Không rò rỉ tài nguyên; dọn thư mục tạm khi test kết thúc. |

Ví dụ unit test JUnit Jupiter **phụ thuộc cấu trúc helper do dự án định nghĩa**; đây là dạng assertion gợi ý, không phải class standalone:

```java
assertTrue(Boolean.TRUE.equals(task.call()));
assertEquals(0, diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
        .count());
assertTrue(Files.isRegularFile(outputDir.resolve("demo/Hello.class")));
```

Không dùng `assertSame` để so sánh hai `JavaFileObject` trả từ những lần gọi manager khác nhau. API không yêu cầu object identity giống nhau; cần so sánh ngữ nghĩa như `Kind`, URI phù hợp, location và kết quả biên dịch.

### Các lỗi thường gặp

**1. `ToolProvider.getSystemJavaCompiler()` trả `null`.** Thường do runtime không có triển khai compiler. Dùng JDK thích hợp hoặc đóng gói module compiler nếu ứng dụng cần; không giả định mọi môi trường chạy Java đều có `javac`.

**2. Truyền thư mục vào phương thức tạo source file objects.** `getJavaFileObjectsFromPaths(Collection)` làm việc với những file paths được liệt kê, không tự quét cả cây thư mục. Hãy liệt kê các tệp `.java` trước.

**3. Chọn nhầm overload deprecated.** Trong Java hiện đại, dùng `getJavaFileObjectsFromPaths(List.of(path))` để chọn overload `Collection`; không khai báo đối số kiểu `Iterable<Path>` rồi vô tình gọi overload deprecated.

**4. Quên tạo `CLASS_OUTPUT` trước khi set.** Output location phải hợp lệ; sử dụng `Files.createDirectories(...)` trước khi set.

**5. Nhầm tên binary class và đường dẫn.** `getJavaFileForInput(CLASS_OUTPUT, "demo.Hello", CLASS)` cần tên `demo.Hello`; không truyền chuỗi `"demo/Hello.class"` vào vị trí tên lớp.

**6. Đặt `SimpleJavaFileObject` sai `Kind` hoặc URI.** Source cần `Kind.SOURCE`; path trong URI nên tương ứng package/class. `JavaFileObject.Kind.CLASS` dùng cho bytecode, không cho source text.

**7. Gọi `getTask(...)` rồi kỳ vọng kết quả đã được tạo.** Cần `task.call()` để biên dịch. Mỗi task chỉ gọi một lần; với lần biên dịch mới hãy tạo task mới.

**8. Dùng charset mặc định trong nguồn Unicode.** Truyền `StandardCharsets.UTF_8` cho manager và thống nhất encoding của tệp/option compiler. Tránh output phụ thuộc thiết lập locale hoặc shell.

**9. Trộn lẫn `-d`, `CLASS_OUTPUT` và địa điểm phát sinh class.** Có thể đặt output bằng location hoặc option `-d`; đừng đặt hai hướng mâu thuẫn. Một cách rõ ràng khi dùng `StandardJavaFileManager` là quản lý `CLASS_OUTPUT` trực tiếp.

**10. Không đóng file manager hoặc stream.** Compiler có thể giữ file handles và cache nội bộ. Đóng manager bằng `try-with-resources`; đóng cả `Files.walk` hoặc các luồng I/O tự mở.

**11. Tưởng compiled class tự chạy.** `task.call()` chỉ biên dịch, không tự execute class. Nếu cần chạy, phải định nghĩa cơ chế class loading/execution và tách quyền hạn rõ ràng.

**12. Biên dịch mã không tin cậy trong tiến trình ứng dụng như thể vô hại.** Annotation processors hoặc plugin compiler có thể thực thi Java code, nên ví dụ dùng `-proc:none`. Với đầu vào không tin cậy, cần giới hạn tài nguyên và cô lập quá trình biên dịch theo kiến trúc phù hợp; việc tắt processors riêng nó không biến việc xử lý input tùy ý thành môi trường an toàn tuyệt đối.

## 12. Checklist triển khai

Trước khi gọi compiler trong ứng dụng:

1. Xác nhận JDK có `JavaCompiler`; quyết định biên dịch source ở filesystem hay RAM.
2. Chỉ định encoding, tạo thư mục output, chọn đúng classpath/module path.
3. Tạo `StandardJavaFileManager` bằng `getStandardFileManager(...)` và đặt trong `try-with-resources`.
4. Chuyển `Path` thành các `JavaFileObject.Kind.SOURCE` qua overload `Collection<Path>`, hoặc cung cấp `SimpleJavaFileObject` từ chuỗi.
5. Tạo `DiagnosticCollector` để ghi nhận lỗi; cấu hình options có chủ đích (`--release`, `-proc:none`, `-encoding`... tùy yêu cầu).
6. Tạo `CompilationTask` mới, gọi `call()` đúng một lần và kiểm tra `true/false`.
7. Đọc diagnostics nếu thất bại; xác minh sản phẩm output bằng file manager hoặc `Files.isRegularFile`.
8. Đóng tài nguyên và dọn source/output tạm; chỉ load/execute compiled code khi ứng dụng có nhu cầu rõ ràng.

### Tự kiểm tra

**Câu 1.** Hai input source, một từ `Path` và một từ `String`, có thể nằm trong cùng một danh sách `compilationUnits` không? **Có** nếu cả hai đều là `JavaFileObject.Kind.SOURCE` phù hợp.

**Câu 2.** `SimpleJavaFileObject` có tự hiểu code từ biến `String` không? **Không** trong một subclass tự tạo; bạn phải cung cấp nội dung qua `getCharContent(...)` hoặc cơ chế đọc thích hợp.

**Câu 3.** Tạo `StandardJavaFileManager` xong, có cần tự gọi `javac` dưới dạng tiến trình ngoài không? **Không**; `JavaCompiler.getTask(...).call()` biên dịch trong tiến trình Java khi có implementation.

**Câu 4.** Thêm `manager.setLocationFromPaths(CLASS_OUTPUT, List.of(output))` làm compiler tự tạo thư mục output chưa tồn tại không? **Không nên giả định vậy**; hãy tạo folder hợp lệ trước.

**Câu 5.** `getJavaFileObjectsFromPaths(Iterable<Path>)` có còn là overload nên ưu tiên không? **Không**; overload `Iterable` đã deprecated, hãy chọn overload `Collection<Path>` hoặc varargs `Path...`.

**Câu 6.** `task.call()` thành công có nghĩa class tự được nạp và thực thi chưa? **Không**; nó chỉ tạo kết quả biên dịch, việc class loading/execution là bước khác.

## Tài liệu API chính thức

- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html) — `getStandardFileManager`, `getTask`, compiler task.
- [Java SE 26 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html) — các overload `Path`, locations, charset và ngữ nghĩa file trên filesystem.
- [Java SE 26 — `JavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileObject.html) và [`JavaFileObject.Kind`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileObject.Kind.html) — contract của source/class file.
- [Java SE 26 — `FileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/FileObject.html) — giao diện đọc/ghi và URI của file object.
- [Java SE 26 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html) — nền tảng cho source trong RAM.
- [Java SE 26 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html) — hợp đồng locations, tìm input, tạo output và quản lý vòng đời.
- [Java SE 26 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — thu thập lỗi/cảnh báo để báo cáo và kiểm thử.

Những API được dùng trong chương trình chính vẫn có ích trong Java hiện tại. Phần ví dụ tránh overload đã deprecated, chạy được với Java 17 và không phụ thuộc hành vi nội bộ của một triển khai compiler cụ thể.
