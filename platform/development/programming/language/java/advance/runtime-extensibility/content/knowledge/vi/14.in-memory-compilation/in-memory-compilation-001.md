# Biểu diễn mã nguồn bằng SimpleJavaFileObject và URI phù hợp

Trong Java, **biên dịch mã nguồn nằm trong bộ nhớ** không nhất thiết phải tạo file `.java` trên ổ đĩa. API `javax.tools.JavaCompiler` nhận các đối tượng `JavaFileObject` biểu diễn đơn vị biên dịch. Một cách đơn giản để tạo đầu vào là **kế thừa `SimpleJavaFileObject`, gắn cho đối tượng một URI thể hiện đúng tên nguồn, chọn `Kind.SOURCE` và trả về nội dung Java qua `getCharContent(...)`**.

Tuy nhiên, “nội dung là một chuỗi `String`” chưa đủ để compiler hiểu đúng đơn vị biên dịch. **URI phải phù hợp với tên lớp/package và loại file**, bởi compiler/file manager có thể sử dụng tên đó để nhận diện, kiểm tra tính tương thích, đưa ra chẩn đoán và quản lý nhiều nguồn.

Bài này giải thích các hợp đồng API, quy tắc tạo URI đáng tin cậy, ví dụ Java 17 biên dịch từ `String` và giữ cả file `.class` trong bộ nhớ, cùng lỗi hay gặp ở tên nguồn, namespace, diagnostics, class loader và vòng đời tài nguyên.

## 1. Phân biệt mã nguồn, JavaFileObject, URI và file vật lý

Một bài toán thường bắt đầu bằng mã nguồn được sinh động:

```java
String code = """
        package demo.generated;
        public final class Greeter {
            public static String message() {
                return "Hello from memory";
            }
        }
        """;
```

Đoạn trên là **chuỗi Java**, không phải file trên filesystem. Để truyền cho `JavaCompiler`, cần một **compilation unit** có tên, kiểu và cách đọc nội dung:

```text
Chuỗi mã nguồn Java (String)
          |
          v
SimpleJavaFileObject (Kind.SOURCE)
  - URI: string:///demo/generated/Greeter.java
  - getCharContent(): trả mã nguồn
          |
          v
JavaCompiler.getTask(..., compilationUnits)
          |
          v
JavaFileManager nhận bytecode đầu ra
          |
          v
Class bytes và/hoặc class được nạp vào ClassLoader
```

Có bốn khái niệm:

| Khái niệm | Vai trò | Điều không nên nhầm |
| --- | --- | --- |
| `String` / `CharSequence` | Nội dung mã Java theo Unicode | Không chứa metadata package/file kind |
| `JavaFileObject` | Abstraction cho source, class hoặc loại output khác | Không bắt buộc trỏ tới file trên đĩa |
| `URI` | Định danh của đối tượng đầu vào/đầu ra | `string:///...` hoặc `mem:///...` không phải địa chỉ web hay file thật |
| `JavaFileManager` | Cung cấp input/output cho compiler và quản lý nơi ghi class | Đầu vào từ bộ nhớ **không tự động** khiến output cũng vào bộ nhớ |

`SimpleJavaFileObject` là lớp base giúp triển khai `JavaFileObject` với các hành vi mặc định. Khi chỉ cần đưa source từ chuỗi vào compiler, việc override `getCharContent(...)` thường là đủ. Khi cần **lấy bytecode mà không ghi ra đĩa**, phải xử lý thêm output bằng một `JavaFileManager` thích hợp.

## 2. Các hợp đồng JavaFileObject và SimpleJavaFileObject

### `JavaFileObject.Kind`

`JavaFileObject.Kind` cho compiler biết loại đơn vị:

- `SOURCE`: mã nguồn Java; extension mặc định `.java`.
- `CLASS`: bytecode Java; extension `.class`.
- `HTML`: tài liệu HTML.
- `OTHER`: các loại còn lại.

**Nguồn tạo từ `String` phải khai báo `Kind.SOURCE`**, không phải `Kind.CLASS`. Còn class bytes sinh sau biên dịch phải được biểu diễn bằng `Kind.CLASS`. Kiểu không tương ứng với nội dung có thể làm compiler và file manager xử lý sai.

### Constructor của SimpleJavaFileObject

```java
protected SimpleJavaFileObject(URI uri, JavaFileObject.Kind kind)
```

Constructor nhận **URI hợp lệ** và `kind`, lưu những thông tin đó để các phương thức như `toUri()`, `getKind()` và `isNameCompatible(...)` sử dụng. URI phải có **path component không rỗng**; không được nghĩ rằng URI chỉ là một chuỗi nhãn tùy ý. URI nên cung cấp một đường dẫn logic nhất quán với package và tên file.

### `getCharContent(boolean ignoreEncodingErrors)`

Đối tượng SOURCE từ bộ nhớ thường override:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
```

Đây là snippet của subclass có field `sourceCode` kiểu `String` hoặc `CharSequence`. Compiler có thể lấy source qua phương thức này, nên không cần tạo `FileInputStream`. Tham số `ignoreEncodingErrors` vốn có ý nghĩa ở những implementation phải decode byte; khi đã giữ nội dung trong `String`, quá trình giải mã đã xảy ra trước đó. Không được bỏ qua lỗi encoding khi **đọc bytes ban đầu** từ nguồn khác.

Các default method của `SimpleJavaFileObject` không biến nó thành file I/O đa năng. Chẳng hạn, nếu bạn chỉ override `getCharContent` thì đừng mặc định `openInputStream`/`openOutputStream` sẽ được hỗ trợ. Nếu compiler hoặc thành phần khác thực sự cần đường byte/reader riêng, phải triển khai đúng hợp đồng đó.

### `isNameCompatible(...)`

`JavaFileObject.isNameCompatible(simpleName, kind)` kiểm tra liệu tên nguồn có tương thích với simple class name và loại file. Với URI:

```text
string:///demo/generated/Greeter.java
```

`isNameCompatible("Greeter", Kind.SOURCE)` trả `true` trong ví dụ thực hành. URI kết thúc bằng tên khác hoặc extension khác có thể khiến kiểm tra thất bại. Ngoài sự tương thích tên đơn giản, **tên package trong mã nguồn** cũng cần thống nhất với cách ứng dụng định danh compilation unit.

## 3. URI phù hợp cho nguồn Java tạo trong bộ nhớ

### Quy tắc quan trọng nhất

Với một **binary name** bình thường của top-level class, ví dụ `demo.generated.Greeter`, có thể đặt:

```java
String binaryName = "demo.generated.Greeter";
URI uri = URI.create("string:///" +
        binaryName.replace('.', '/') +
        JavaFileObject.Kind.SOURCE.extension);
```

Kết quả:

```text
string:///demo/generated/Greeter.java
```

Đường dẫn URI lúc này phản ánh đúng các thành phần:

- `demo.generated` → `demo/generated/`;
- `Greeter` → tên top-level type/compilation unit;
- `.java` → extension của `Kind.SOURCE`;
- `string` → scheme tùy biến diễn đạt dữ liệu nguồn do ứng dụng cung cấp, không khẳng định tồn tại file `.java` trên filesystem;
- `///` → cấu trúc URI có đường dẫn tuyệt đối, không phải “ba dấu slash tương đương đường dẫn hệ điều hành”.

Với đơn vị đơn giản, công thức này dễ đọc và được dùng phổ biến cùng API compiler. `JavaCompiler` xem đối tượng `JavaFileObject` là nguồn; nó không cần gọi HTTP hay truy cập file có tên `string:///...`.

### Vì sao không dùng URI như thế này?

| URI/biểu diễn | Vấn đề |
| --- | --- |
| `URI.create("Greeter.java")` | URI tương đối, thiếu scheme; không phải lựa chọn phù hợp cho object do compiler/file manager định danh |
| `URI.create("string:///Greeter")` | Thiếu extension `.java`, tên không tương thích với `Kind.SOURCE` theo quy ước |
| `URI.create("string:///demo/Other.java")` | Không thống nhất với tên `Greeter` được yêu cầu; dễ khó hiểu trong diagnostics |
| `URI.create("file:///tmp/Greeter.java")` dù không có file | Dùng scheme `file` dễ gây kỳ vọng sai rằng file thật tồn tại hoặc kích hoạt logic filesystem ở thành phần khác |
| `URI.create("string:///demo.generated.Greeter.java")` | Dùng dấu chấm của package thay vì chuyển thành các phân đoạn `/`; sai namespace dự định |
| `URI.create("string:///demo/Greeter.java")` khi source có package `demo.generated` | URI không phản ánh thư mục package dự định; dễ gây lỗi nếu compiler/file manager cần suy ra binary name |
| `URI.create("string:///demo/My File.java")` | Dấu cách chưa encode khiến `URI.create` báo lỗi; cần validate/encode tên hợp lệ |

**Không phải mọi URI khác dạng `string:///...` đều bị JDK cấm.** Đây là **quy ước ổn định, dễ tương thích** cho bộ nguồn trên bộ nhớ. Có thể dùng scheme `mem`, `memory` hoặc scheme tùy biến khác nếu file manager/compiler của ứng dụng xử lý được. Điều quan trọng là URI hợp lệ, đủ path, nhất quán với source name/kind và không bị hiểu nhầm là đường dẫn file vật lý.

### Chuẩn hóa và an toàn tên

Đừng ghép nguyên giá trị `className` do người dùng nhập tự do vào URI rồi cho compiler xử lý. Trước hết phải:

1. Xác định tên lớp từ metadata đã được ứng dụng xác thực hoặc parse theo luật Java, không chỉ đoán từ ký tự cuối.
2. Kiểm tra package name và từng identifier có hợp lệ, không có `/`, `..` kiểu path traversal, khoảng trắng hoặc ký tự điều khiển.
3. Áp dụng chính sách lớp/namespace được phép sinh; không tạo tên đè lên class của host.
4. Dùng API `URI` để encode khi thật sự cần tên chứa ký tự đặc biệt; tránh tạo chuỗi URL bằng tay từ đầu vào không tin cậy.

Có thể bắt đầu với whitelist identifier ASCII nếu sản phẩm chỉ cho phép kiểu tên đó; nhưng đừng nhầm whitelist ASCII với **toàn bộ** cú pháp identifier Java, vốn cho phép Unicode.

### Tên file đặc biệt

Bài toán nhiều compilation units cần xử lý cả:

- `package-info.java`: không phải một tên top-level class thông thường;
- `module-info.java`: descriptor module, không có FQCN của class theo công thức thay dấu chấm;
- nhiều top-level types trong một file: **tên compilation unit** phải phù hợp với public top-level type và luật file name của Java;
- nested/anonymous classes: file nguồn top-level có thể sinh ra nhiều file `.class` như `Outer$Inner.class`, không nên tạo “source URI cho inner class” trừ khi đó thật sự là một đơn vị nguồn độc lập.

Vì vậy công thức `binaryName.replace('.', '/') + ".java"` phù hợp cho **top-level type bình thường**, không phải bộ giải tổng quát cho mọi loại Java source file.

## 4. Java 17 chạy độc lập: String → SimpleJavaFileObject → bytecode trong bộ nhớ

Ví dụ sau thực hiện **cả hai phần**:

1. Nguồn nằm trong `String`, được đóng gói trong `SourceFile extends SimpleJavaFileObject` với URI `string:///demo/generated/Greeter.java`.
2. Bytecode đầu ra được chặn bằng `MemoryFileManager`, lưu trong `ByteArrayOutputStream` của `ClassFile` với URI `mem:///demo/generated/Greeter.class`.

Sau biên dịch, ví dụ dùng một `ClassLoader` riêng để định nghĩa class từ bytes. Không có file nguồn/bytecode của `demo.generated.Greeter` được tạo trên đĩa; chỉ file `MemoryCompileDemo.java` và `MemoryCompileDemo.class` dùng để chạy **chương trình minh họa** là file vật lý.

### 4.1. File MemoryCompileDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class MemoryCompileDemo {
    static final class SourceFile extends SimpleJavaFileObject {
        private final String code;

        SourceFile(String binaryName, String code) {
            super(URI.create("string:///" +
                            binaryName.replace('.', '/') +
                            JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        ClassFile(String binaryName) {
            super(URI.create("mem:///" +
                            binaryName.replace('.', '/') +
                            JavaFileObject.Kind.CLASS.extension),
                    JavaFileObject.Kind.CLASS);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] bytecode() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassFile> outputs = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(location, className, kind, sibling);
            }
            ClassFile output = new ClassFile(className);
            outputs.put(className, output);
            return output;
        }

        Map<String, byte[]> classBytes() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            outputs.forEach((name, file) -> result.put(name, file.bytecode()));
            return Map.copyOf(result);
        }
    }

    public static void main(String[] args) throws Exception {
        String name = "demo.generated.Greeter";
        String code = """
                package demo.generated;
                public final class Greeter {
                    public static String message() {
                        return "Hello from memory";
                    }
                }
                """;

        SourceFile source = new SourceFile(name, code);
        System.out.println("sourceUri=" + source.toUri());
        System.out.println("kind=" + source.getKind());
        System.out.println("compatible=" +
                source.isNameCompatible("Greeter", JavaFileObject.Kind.SOURCE));

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiled;

        StandardJavaFileManager standard = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
        try (MemoryFileManager files = new MemoryFileManager(standard)) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(source));
            if (!Boolean.TRUE.equals(task.call())) {
                for (Diagnostic<? extends JavaFileObject> diagnostic
                        : diagnostics.getDiagnostics()) {
                    System.err.println(diagnostic);
                }
                throw new IllegalStateException("Compilation failed");
            }
            compiled = files.classBytes();
        }

        System.out.println("generated=" + compiled.containsKey(name));

        ClassLoader loader = new ClassLoader(MemoryCompileDemo.class.getClassLoader()) {
            @Override
            protected Class<?> findClass(String binaryName)
                    throws ClassNotFoundException {
                byte[] bytes = compiled.get(binaryName);
                if (bytes == null) {
                    throw new ClassNotFoundException(binaryName);
                }
                return defineClass(binaryName, bytes, 0, bytes.length);
            }
        };
        Class<?> greeter = loader.loadClass(name);
        System.out.println("result=" + greeter.getMethod("message").invoke(null));
    }
}
```

**Biên dịch và chạy:** trong thư mục chứa file `MemoryCompileDemo.java`, với JDK 17+:

```bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
```

**Stdout đã được kiểm chứng với `javac --release 17` và `java`:**

```text
sourceUri=string:///demo/generated/Greeter.java
kind=SOURCE
compatible=true
generated=true
result=Hello from memory
```

Không cần đưa `demo.generated.Greeter` ra thư mục `demo/generated` để biên dịch: compiler nhận source qua `getCharContent`. Bộ quản lý output nhận tên class được compiler yêu cầu, tạo `ClassFile` rồi thu bytes. Class loader nhận các bytes đó và định nghĩa class khi `loadClass("demo.generated.Greeter")` thực hiện.

### 4.2. Phân tích các điểm chính

**A. URI nguồn liên kết logic package và tên đơn vị biên dịch**

`SourceFile(name, code)` tạo URI:

```text
string:///demo/generated/Greeter.java
```

`Kind.SOURCE` là metadata; `getCharContent` là nội dung. Hai thành phần phải đi đôi, đặc biệt khi compiler phát diagnostics, tìm source file và đối chiếu tên class. `Objects.requireNonNull` tránh source `null` đi qua quá trình biên dịch.

**B. Output có URI và Kind khác source**

`ClassFile` dùng:

```text
mem:///demo/generated/Greeter.class
Kind.CLASS
```

`openOutputStream()` cung cấp `ByteArrayOutputStream` để compiler ghi bytecode. Nếu chỉ viết `SourceFile` mà không triển khai file manager, compiler có thể ghi class files theo standard output location, thường trên filesystem. **Source in memory ≠ output in memory.**

**C. JavaFileManager là ranh giới I/O của compiler**

`MemoryFileManager` kế thừa `ForwardingJavaFileManager<StandardJavaFileManager>` và override `getJavaFileForOutput` để chặn output `Kind.CLASS`. Nó vẫn ủy quyền cho standard file manager với các tác vụ khác như tìm class trên classpath/module path. Trong ví dụ, option `-proc:none` tắt annotation processing nên không có generated source từ annotation processor cần được lưu riêng.

Đây là bản trình diễn có chủ đích: nếu compiler được phép tạo `Kind.SOURCE`, file tài nguyên hoặc output module khác, code hiện tại **forward** các loại không phải `CLASS` cho standard manager. Muốn **toàn bộ mọi loại output** đều ở trong RAM cho mọi quy trình phức tạp thì cần xử lý cả những đường output đó thay vì tin rằng override một method là bao phủ mọi trường hợp.

**D. Không nhầm package/loader của lớp đang chạy với lớp sinh động**

`MemoryCompileDemo` chạy trên classpath hiện tại; `demo.generated.Greeter` được định nghĩa ở class loader riêng. Class loader có mặc định **parent-first delegation**: nếu parent đã có class cùng binary name, `loadClass` có thể trả class của parent mà không gọi `findClass`. Trong ví dụ, tên `demo.generated.Greeter` được chọn duy nhất để không va chạm. Trong plugin runtime thực, cần kiểm soát namespace và class-loader policy, không cho mã động tự ý ghi đè class của host.

**E. Đóng JavaFileManager, không giữ compiler task vô thời hạn**

`try (MemoryFileManager files = ...)` đóng forwarding manager và standard manager sau khi lấy bản sao class bytes. Java compiler task là thao tác có vòng đời; không tái sử dụng cùng task để biên dịch nhiều lần. Nên tạo một task/file manager hoặc ngữ cảnh được quản lý đúng cho từng lần compile, giải phóng references lớn tới source/bytecode khi hết nhu cầu.

## 5. API compiler: nguồn từ CharSequence vào compilationUnits

Phần kết nối quan trọng nằm ở:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        files,
        diagnostics,
        List.of("--release", "17", "-proc:none"),
        null,
        List.of(source));
boolean ok = Boolean.TRUE.equals(task.call());
```

Đây là snippet lấy từ chương trình phần 4; các biến `compiler`, `files`, `diagnostics`, `source` đã được tạo trước đó.

Các tham số `getTask` lần lượt là:

1. `Writer out` để compiler ghi nội dung bổ sung (ở đây `null`);
2. `JavaFileManager` kiểm soát cách compiler tìm input/ghi output;
3. `DiagnosticListener` nhận errors/warnings; `DiagnosticCollector` là implementation tiện dụng;
4. `options` như `--release 17` (biên dịch theo API/ngôn ngữ mục tiêu) và `-proc:none` (không chạy annotation processors);
5. `classes` dùng cho xử lý annotation processing theo tên class; không phải các source compilation units nên đặt `null` trong ví dụ;
6. `compilationUnits` là `Iterable<? extends JavaFileObject>`: ở đây nguồn duy nhất là `List.of(source)`.

Điểm mấu chốt: **`JavaCompiler` không nhận trực tiếp `String` mã nguồn dưới dạng tham số compilationUnits**. Ta dùng `SimpleJavaFileObject` làm cầu nối hợp đồng I/O.

### Khi biên dịch nhiều class cùng lúc

Có thể truyền nhiều đơn vị nguồn:

```java
List<JavaFileObject> units = List.of(
    new SourceFile("demo.generated.Greeter", greeterSource),
    new SourceFile("demo.generated.Helper", helperSource)
);
```

Đây là snippet cần hai chuỗi mã `greeterSource`, `helperSource` và class `SourceFile` như ví dụ. Nếu các source tham chiếu nhau, truyền đủ compilation units vào cùng task là một cách để compiler biết về các class đó. Không nên gộp hai public top-level classes khác tên vào một file source bất hợp lệ. Nếu code sinh ra nested classes, compiler có thể gọi `getJavaFileForOutput` nhiều lần để ghi `Outer.class`, `Outer$Inner.class`, v.v.; file manager cần lưu theo **binary class name** mà compiler yêu cầu.

## 6. Diagnostics: vì sao URI có giá trị ngoài việc “đặt tên”

Khi biên dịch lỗi, `Diagnostic<? extends JavaFileObject>` có thể cung cấp:

- `getSource()`: source object gây lỗi, từ đó tra được `toUri()`;
- `getLineNumber()`, `getColumnNumber()`: vị trí;
- `getKind()`: ERROR, WARNING, NOTE;
- `getMessage(locale)`: lời mô tả.

Đoạn ghi log minh họa (dùng `DiagnosticCollector<JavaFileObject> diagnostics` đã có):

```java
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    String sourceUri = d.getSource() == null
            ? "(unknown)" : d.getSource().toUri().toString();

    System.err.printf("%s %s:%d:%d %s%n",
            d.getKind(), sourceUri,
            d.getLineNumber(), d.getColumnNumber(),
            d.getMessage(Locale.ROOT));
}
```

Đoạn này không phải chương trình độc lập, cần các import và biến từ phần 4. URI logic ổn định như `string:///demo/generated/Greeter.java` giúp frontend/editor ánh xạ lỗi về đúng tab hoặc bộ nguồn sinh. Nếu tất cả source objects dùng chung `string:///Source.java` thì diagnostics nhiều file có thể không phân biệt được; nếu URI được xây ngẫu nhiên mỗi lần một cách vô cớ, việc đối chiếu kết quả và cache trở nên khó hơn.

**Diagnostic source không phải lúc nào cũng có** (chẳng hạn một số lỗi option/configuration), nên luôn kiểm tra `null`. Một số lỗi có số dòng/cột âm khi không xác định được vị trí. Đừng để log vô tình chứa mã nguồn bí mật hoặc chi tiết hạ tầng nếu source đến từ nội dung nhạy cảm.

## 7. Quy tắc định danh: binary name, canonical name, source file name

Đối với top-level type `demo.generated.Greeter`:

```text
Binary name:       demo.generated.Greeter
Package:           demo.generated
Simple name:       Greeter
Source URI path:   /demo/generated/Greeter.java
Source kind:       SOURCE
Class URI path:    /demo/generated/Greeter.class
Class kind:        CLASS
```

Đó là ánh xạ thông thường. Nhưng cần tách khái niệm khi mở rộng:

- **Binary name** của nested class có thể chứa `$`, ví dụ `demo.generated.Outer$Inner`; **source file** khai báo cả hai có thể vẫn là `Outer.java`.
- **Canonical name** có thể dùng dấu `.` cho nested type; đừng ghép tùy tiện canonical name thành đường source file. Lấy metadata đơn vị nguồn/top-level type thực sự.
- `package-info.java` và `module-info.java` không đi theo quy tắc “một source cho một top-level class”.
- Với source không có package (unnamed package), URI như `string:///Greeter.java` có thể phù hợp cho môi trường đơn giản, nhưng plugin/module production nên dùng namespace rõ ràng để tránh xung đột.

Trong demo, `MemoryFileManager.getJavaFileForOutput` nhận `className` **do compiler cung cấp**, vì vậy đúng với cả class phụ/nested classes mà compiler sinh. Không nên tự đoán rằng mỗi `SourceFile` chỉ sinh đúng một `.class`.

### Về URI không phải file: đừng tự biến ngược thành Path

Khi `source.toUri()` là `string:///...`, đoạn này không hợp lệ như một lối lấy file nguồn:

```java
// Minh họa sai: không có filesystem provider cho scheme "string".
java.nio.file.Path path = java.nio.file.Path.of(source.toUri());
```

Đoạn trên là snippet minh họa sai, không nên thực thi như chương trình mẫu. `Path.of(URI)` cần filesystem provider tương ứng URI; `string` ở đây là định danh logic, không khẳng định tồn tại tệp vật lý. Nếu muốn lưu source khi cần debug hoặc export, phải thực hiện thao tác I/O **tường minh** theo policy ứng dụng, thay vì suy rằng URI tùy biến tự ánh xạ sang file.

## 8. Mã nguồn trong bộ nhớ không đồng nghĩa biên dịch “không dùng đĩa” hoàn toàn

Một compilation task có thể vẫn cần tham khảo các artifact vật lý:

- `javac` tìm các dependency class và module qua standard file manager, classpath/module path;
- các API của Java và thư viện có thể nằm trong JDK runtime image, JAR hoặc các nguồn ngoài;
- annotation processor có thể sinh thêm source/class/resources và yêu cầu vị trí output khác;
- nếu file manager mặc định nhận `CLASS_OUTPUT`, class đầu ra có thể được ghi ra đĩa.

**Ví dụ hoàn chỉnh đã tắt annotation processing (`-proc:none`)** và intercept `Kind.CLASS` để minh họa rõ in-memory output; nó không khẳng định compiler/JDK hoàn toàn không đọc bất kỳ resource vật lý nào ở bước giải quyết dependencies.

Nếu muốn biên dịch một dự án đa-module, annotation processing hoặc incremental compilation chỉ từ bộ nhớ, cần xây dựng `JavaFileManager` quản lý thêm `list`, `getJavaFileForInput`, `inferBinaryName`, các location module, `getFileForOutput`/`getJavaFileForOutput` và cache theo graph. Đừng nghĩ một wrapper `SourceFile` đủ để thay toàn bộ hệ thống build.

### Khi nào nên dùng StandardJavaFileManager?

`StandardJavaFileManager` rất phù hợp để compiler lấy thư viện ngoài từ classpath/module path và xử lý các đường chuẩn mà ứng dụng không override. `ForwardingJavaFileManager` cho phép giữ nguyên hành vi đó, chỉ thay phần ghi output hoặc input động cần thiết. Đây thường là cách ít lỗi hơn so với triển khai toàn bộ `JavaFileManager` từ đầu.

Nếu cần hỗ trợ source sinh tự động ở lần biên dịch kế tiếp, registry có thể lưu cả mã nguồn lẫn bytecode và cung cấp `JavaFileObject` tương ứng theo package/binary name. Hãy quản lý phiên bản nguồn, cache invalidation và class loader ownership để tránh chọn nhầm bản cũ.

## 9. Thiết kế SourceFile có thể bảo trì

Mẫu tối thiểu:

```java
final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') +
                Kind.SOURCE.extension), Kind.SOURCE);
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Đây là snippet yêu cầu các import `URI`, `SimpleJavaFileObject` (và môi trường Java 17+) khi đặt riêng. Nó là phần cốt lõi của nguồn text. Trong thực tế, nên tách chức năng:

1. **Source identity**: package, top-level type, name, version, URI; tạo một cách nhất quán, immutable.
2. **Source content**: `String` hoặc `CharSequence` immutable để compiler đọc ổn định.
3. **Compilation diagnostics**: ánh xạ mỗi URI sang input source và lỗi.
4. **Output bytecode**: map theo binary class name, riêng với nguồn đầu vào.
5. **Runtime loading**: class loader có scope/version và lifecycle xác định.

Không nên để `SourceFile` tự tạo class loader, tự lưu file vật lý hoặc giữ cache toàn JVM chỉ vì nó có URI; như vậy sẽ trộn trách nhiệm của mô hình source với trách nhiệm build/runtime.

### Khả năng an toàn luồng

`SourceFile` chứa `String` không đổi thường dễ chia sẻ dưới dạng dữ liệu. Nhưng **`JavaCompiler.CompilationTask`, `JavaFileManager` và bộ nhớ output** có state và không nên mặc định dùng đồng thời từ nhiều job mà thiếu kiểm soát. Một compilation job nên có riêng source list, diagnostics và output mapping. Nếu có cache, chỉ publish các bản source/bytecode đã hoàn chỉnh với cơ chế concurrency phù hợp.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Compiler nói không tìm thấy source hoặc class dù có String | Chỉ tạo String nhưng không đưa vào `compilationUnits` qua `JavaFileObject` | Tạo `SourceFile(URI, Kind.SOURCE)` và truyền `List.of(source)` |
| Compiler/diagnostics chỉ ra tên nguồn lạ | URI không thống nhất package/top-level class | Tạo `string:///package/path/Class.java` và validate name |
| `isNameCompatible` trả false | URI path/extension không tương ứng simple name/kind | Kiểm tra `.java`, ký tự hoa/thường và kiểu `SOURCE` |
| `URI.create` ném `IllegalArgumentException` | URI không hợp lệ, chứa khoảng trắng/ký tự cần encode | Validate identifier, tạo URI đúng thay vì ghép user input tùy ý |
| Dù source “trong bộ nhớ”, vẫn thấy file `.class` trên đĩa | Standard file manager vẫn điều khiển output | Intercept `getJavaFileForOutput` với `Kind.CLASS` và lưu `ByteArrayOutputStream` |
| Có source lỗi nhưng thiếu thông tin dòng | Không dùng `DiagnosticCollector`/URI không phân biệt nguồn | Gắn URI ổn định, đọc `Diagnostic` và ánh xạ sang editor |
| Sinh nested class nhưng chỉ có bytecode lớp ngoài | Output manager giả định mỗi source sinh một class | Lưu mọi `className` mà compiler yêu cầu |
| Nạp class trả về implementation cũ | Parent-first loader đã có cùng binary name | Dùng namespace/version/class-loader policy rõ ràng |
| `ToolProvider.getSystemJavaCompiler()` trả null | Runtime không chứa system compiler (ví dụ bản runtime tinh gọn) | Dùng JDK/runtime có module compiler cần thiết |
| `task.call()` không thành công | Mã nguồn sai hoặc thiếu classpath/module path | In diagnostics; kiểm tra package, options và dependencies |
| Chạy tốt trên IDE nhưng lỗi trong deployment | Compilation classpath, module path hoặc encoding khác nhau | Cấu hình tool options/file manager tường minh; kiểm thử runtime thật |
| Code plugin không đáng tin tạo nguy cơ bảo mật | Tưởng URI custom hoặc class loader là sandbox | Không chạy source chưa tin cậy trong JVM đặc quyền; cô lập bằng tiến trình/OS policy thích hợp |

### Ba ngộ nhận cần tránh

**“Chỉ cần `new SimpleJavaFileObject(...)` là compiler đọc được String.”** Không đúng: lớp base không tự biết chuỗi nội dung của bạn. Phải override `getCharContent` hoặc method đọc phù hợp.

**“URI `string:///...` là đường dẫn file cần tồn tại.”** Không đúng: nó là định danh logic; có thể chứa package path và extension `.java` mà không có file vật lý. File manager/compiler dùng URI theo hợp đồng `JavaFileObject`.

**“Đầu vào memory nghĩa là mọi output và dependency đều trong memory.”** Không đúng: output do file manager quyết định, dependency có thể cần classpath/module path; annotation processors có thể sinh nhiều loại file. Cần thiết kế từng đường I/O riêng.

## 11. An toàn và giới hạn khi biên dịch mã động

Tính đúng của URI **không tạo ranh giới an ninh**. Compiler có thể tiêu tốn nhiều CPU/RAM; code đã biên dịch khi được chạy sẽ có quyền theo tiến trình JVM. Vì vậy:

- Không nhận Java source từ người không tin cậy rồi nạp/chạy trực tiếp vào JVM chứa dữ liệu nhạy cảm. Với use case có nguồn chưa tin cậy, dùng ranh giới process/container/OS permissions và quota phù hợp.
- `-proc:none` tắt annotation processing trong ví dụ, giảm đường thực thi processor ngoài ý muốn, **không biến javac hoặc class loader thành sandbox**.
- Hạn chế classpath/module path, API cho phép và cách chọn class loader; không coi việc prefix URI bằng `mem` là cách cách ly code.
- Giới hạn kích thước source, thời gian biên dịch, số nguồn/lớp đầu ra; quản lý class loader/version để tránh rò rỉ metaspace và tham chiếu cũ.
- Không ghi toàn bộ source hoặc diagnostics chứa bí mật ra log nếu input có dữ liệu riêng tư.
- Với ứng dụng multi-tenant, định danh source/cache cần mang tenant/build scope tách biệt để tránh dùng nhầm source hoặc bytecode từ một phiên bản khác.

## 12. Checklist áp dụng vào hệ thống sinh mã thật

- [ ] Có top-level source identity chính xác: package, tên unit, mã nguồn, version.
- [ ] URI hợp lệ với scheme phù hợp, path có dạng `/pkg/path/Class.java` và extension `SOURCE`.
- [ ] URI và source content nhất quán; xử lý riêng `module-info.java`, `package-info.java` và nested types.
- [ ] `SourceFile` override `getCharContent(...)`, không dựa vào default unsupported I/O methods.
- [ ] `JavaCompiler.getTask` nhận đầy đủ compilation units và compiler options rõ ràng.
- [ ] DiagnosticCollector giữ URI/line/column để tra cứu ngược source khi có lỗi.
- [ ] Nếu yêu cầu output RAM, file manager chặn toàn bộ những output kinds mà hệ thống có thể sinh, không chỉ dựa vào SOURCE từ String.
- [ ] Kết quả bytecode được map theo **class binary name** do compiler cung cấp, không đoán một class mỗi source.
- [ ] Class loader dùng đúng namespace, version, parent delegation; lifecycle và references được quản lý.
- [ ] Có test cùng package/tên lớp, nhiều source, nested class, Unicode, source lỗi, thiếu compiler và output manager.
- [ ] Có chính sách resource limits và isolation nếu source không tin cậy.

### Tài liệu tham khảo chính thức Java 17

- [`SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [`JavaFileObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html)
- [`JavaCompiler` và `CompilationTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [`ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html)
- [`DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)

**Kết luận:** `SimpleJavaFileObject` là cầu nối biến nội dung mã nguồn nằm trong `CharSequence` thành một **compilation unit có tên, Kind và URI hợp lệ**. Quy ước `string:///package/path/Type.java` giúp định danh nguồn rõ ràng; `getCharContent` cung cấp bytes đã được giải mã ở dạng ký tự. Muốn giữ cả `.class` trong bộ nhớ, phải thêm file manager xử lý output và class loader thích hợp — **hai trách nhiệm độc lập với việc tạo URI nguồn**.