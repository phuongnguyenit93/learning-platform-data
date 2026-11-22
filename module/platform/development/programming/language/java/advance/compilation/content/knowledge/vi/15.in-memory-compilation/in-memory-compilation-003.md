# Thu bytecode bằng ForwardingJavaFileManager khi biên dịch Java trong bộ nhớ

Java Compiler API cho phép một chương trình Java gọi trình biên dịch mà không cần chạy tiến trình `javac` bên ngoài. Khi muốn **thu kết quả biên dịch dưới dạng mảng byte** thay vì để compiler ghi `.class` vào thư mục, cách thiết kế được Java SE hỗ trợ là tạo một **`ForwardingJavaFileManager`** bao quanh `StandardJavaFileManager`, rồi ghi đè phương thức xuất file class.

Ý tưởng chính: compiler hỏi file manager “tôi cần ghi class có tên nhị phân `demo.Hello`, cho tôi một `JavaFileObject`”. File manager tùy biến trả một đối tượng có `openOutputStream()` cung cấp `ByteArrayOutputStream`. Sau khi `CompilationTask.call()` hoàn tất, ứng dụng lấy `byte[]` từ từng class để phân tích, lưu trữ theo chính sách riêng hoặc nạp bằng class loader.

Bài học dùng Java 17+ và ví dụ thực tế đã được chạy thử trên JDK 21, bao gồm cả class lồng nhau, chẩn đoán lỗi, quản lý lifecycle và giới hạn quan trọng: **thu bytecode trong RAM không đồng nghĩa toàn bộ quá trình biên dịch bị cô lập khỏi filesystem, classpath hoặc mã của annotation processor.**

## 1. Vì sao cần một ForwardingJavaFileManager?

`javax.tools.JavaCompiler` đảm nhận compilation, nhưng nó cần một `JavaFileManager` để đọc và ghi các đơn vị dữ liệu. `StandardJavaFileManager` hoạt động tốt với source file, thư mục output, JAR, classpath và module path. Tuy nhiên, khi ứng dụng muốn nhận trực tiếp bytecode, không nên phải tạo file tạm rồi đọc file ấy về RAM chỉ để xóa sau đó.

`ForwardingJavaFileManager<M extends JavaFileManager>` là lớp tiện ích dùng **ủy quyền (delegation)**: mặc định hầu hết thao tác được chuyển cho file manager gốc; ta chỉ ghi đè những thao tác muốn tùy chỉnh.

```text
JavaCompiler
    |
    | getTask(..., customManager, ...)
    v
ForwardingJavaFileManager
    |
    +-- compiler cần đọc Java platform classes/JARs
    |       |
    |       +--> chuyển cho StandardJavaFileManager
    |
    +-- compiler sinh demo.Hello.class
            |
            +--> getJavaFileForOutput(CLASS_OUTPUT,
                                      "demo.Hello", CLASS, sibling)
                      |
                      +--> InMemoryClassFile
                              |
                              +--> openOutputStream()
                                      |
                                      +--> ByteArrayOutputStream
                                              |
                                              +--> byte[] trong Map
```

Ta **không viết lại** parser, type checker hay compiler. Ta chỉ can thiệp vào cách compiler nhận object để ghi class file.

Một vài API cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `JavaCompiler` | Khởi tạo compilation task và thực thi biên dịch |
| `StandardJavaFileManager` | File manager nền dùng cho classpath, platform classes, source file và các location có sẵn |
| `ForwardingJavaFileManager<StandardJavaFileManager>` | Bao bọc manager nền, ghi đè một số hoạt động cần thiết |
| `SimpleJavaFileObject` | Lớp cơ sở để tự biểu diễn source hoặc output class |
| `getJavaFileForOutput(...)` | Điểm compiler xin nơi ghi một Java source/class file |
| `openOutputStream()` | Nơi compiler thực sự ghi các byte cho output object |
| `ByteArrayOutputStream` | Bộ đệm tăng trưởng trong RAM; `toByteArray()` sao chép nội dung đã ghi |
| `DiagnosticCollector<JavaFileObject>` | Thu thập diagnostic như lỗi, cảnh báo, note có cấu trúc |

## 2. Đâu là nơi phải chặn đầu ra?

Phương thức quan trọng trên `JavaFileManager`:

```java
JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException;
```

Đây là **chữ ký API minh họa**, không phải một method độc lập có thể paste để chạy.

Khi `javac` muốn tạo một class, các giá trị thường mang ý nghĩa:

- `location`: location đích, ví dụ `StandardLocation.CLASS_OUTPUT`.
- `className`: **binary name**, như `demo.Hello` hoặc `demo.Hello$Nested`; không phải đường dẫn `demo/Hello.class`.
- `kind`: `JavaFileObject.Kind.CLASS` cho class file; `Kind.SOURCE` cho source file.
- `sibling`: object liên quan mà compiler có thể dùng làm gợi ý vị trí; có thể `null`. Không dùng nó làm định danh class.

Một override an toàn cho bài toán thu class bytecode có điều kiện:

```java
if (location == StandardLocation.CLASS_OUTPUT
        && kind == JavaFileObject.Kind.CLASS) {
    // Trả JavaFileObject với openOutputStream() vào RAM.
}
return super.getJavaFileForOutput(location, className, kind, sibling);
```

Đây là **snippet nằm trong method của subclass**, không phải file Java độc lập.

Lý do phải kiểm tra location/kind: file manager còn có thể được yêu cầu tạo source trong `SOURCE_OUTPUT` hay những loại file khác. Nếu chặn mọi request và giả vờ chúng đều là class file, annotation processing và các output khác có thể hỏng. Một compiler có thể cung cấp các location riêng cho module; bài học này tập trung vào chương trình đơn giản **không khai báo module**.

## 3. Ví dụ Java 17+ hoàn chỉnh: biên dịch source và thu mọi .class trong RAM

Lưu nguyên chương trình sau vào **`MemoryBytecodeDemo.java`**. Chỉ cần JDK 17 trở lên, không có thư viện phụ thuộc bên ngoài.

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
import java.util.TreeSet;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class MemoryBytecodeDemo {

    // 1. Nguồn Java ở trong RAM.
    static final class SourceFile extends SimpleJavaFileObject {
        private final String source;

        SourceFile(String className, String source) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // 2. Một class output do compiler ghi vào ByteArrayOutputStream.
    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream data =
                new ByteArrayOutputStream();

        ClassFile(String className, Kind kind) {
            super(URI.create("mem:///"
                    + className.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return data;
        }

        byte[] bytes() {
            return data.toByteArray();
        }
    }

    // 3. Phần lớn thao tác ủy quyền, riêng class output giữ trong RAM.
    static final class CaptureManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, ClassFile> classes =
                new LinkedHashMap<>();

        CaptureManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                ClassFile result = new ClassFile(className, kind);
                classes.put(className, result);
                return result;
            }

            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            classes.forEach((name, file) ->
                    result.put(name, file.bytes()));
            return result;
        }
    }

    // 4. Nạp class được sinh từ RAM để kiểm chứng kết quả.
    static final class BytesLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        BytesLoader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = Map.copyOf(classes);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler required");
        }

        String source = """
                package demo;
                public class Hello {
                    public static String text() { return "ready"; }
                    static class Nested {}
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        Map<String, byte[]> bytes;

        try (CaptureManager manager = new CaptureManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT,
                        StandardCharsets.UTF_8))) {

            JavaFileObject input =
                    new SourceFile("demo.Hello", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(input));

            success = Boolean.TRUE.equals(task.call());
            bytes = manager.snapshot();
        }

        long errors = diagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("success=" + success);
        System.out.println("classCount=" + bytes.size());
        System.out.println("classes=" + new TreeSet<>(bytes.keySet()));
        System.out.println("errors=" + errors);

        if (success) {
            BytesLoader loader = new BytesLoader(
                    MemoryBytecodeDemo.class.getClassLoader(), bytes);
            Class<?> klass = loader.loadClass("demo.Hello");
            System.out.println("result="
                    + klass.getMethod("text").invoke(null));
        }
    }
}
```

Biên dịch và chạy chương trình điều khiển:

```bash
javac --release 17 -encoding UTF-8 MemoryBytecodeDemo.java
java MemoryBytecodeDemo
```

Stdout **chính xác** trên bài mẫu (đã kiểm tra bằng JDK 21):

```text
success=true
classCount=2
classes=[demo.Hello, demo.Hello$Nested]
errors=0
result=ready
```

Lệnh `javac` trên biên dịch **`MemoryBytecodeDemo.java`** thành class trên filesystem, vì ta gọi compiler từ terminal. Nhưng khi chạy chương trình `MemoryBytecodeDemo`, **lượt biên dịch bên trong** tạo hai class `demo.Hello` và `demo.Hello$Nested` **trong RAM**, không ghi `demo/Hello.class` hoặc `demo/Hello$Nested.class` ra thư mục output thông thường.

`Nested` vẫn sinh class file dù không được gọi. Java compiler tạo artifact cho class được khai báo, bao gồm nested class; vì thế map phải lưu **nhiều kết quả** thay vì chỉ giữ class chính. `TreeSet` trong câu lệnh in giúp thứ tự tên ổn định dù thứ tự compiler gọi callback có thể thay đổi.

## 4. Phân tích SourceFile: nguồn Java trong RAM

`SourceFile` mở rộng `SimpleJavaFileObject` với `Kind.SOURCE` và lưu một chuỗi:

```java
super(URI.create("string:///"
        + className.replace('.', '/')
        + Kind.SOURCE.extension), Kind.SOURCE);
```

Với `className = "demo.Hello"`, URI có dạng `string:///demo/Hello.java`. URI này là **định danh logic** của file object, không phải khẳng định có một file thật ở thư mục `demo`.

Override:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return source;
}
```

cho compiler đọc source từ `String`. Compiler tiếp tục xử lý Java text như nguồn thường. Khi text đã là `String` trong RAM, việc giải mã byte nguồn trước đó không còn thuộc `SourceFile`; nếu đầu vào ban đầu đến từ file/network, người gọi phải giải mã đúng charset trước khi tạo chuỗi.

Tên file logic và khai báo package/class nên nhất quán, nhất là khi có public top-level type. Nếu source có `public class Hello`, class name truyền cho file object nên là `demo.Hello` với package tương ứng.

Không cần override `openInputStream()` cho nguồn chuỗi vì ví dụ sử dụng `getCharContent()`. Với một loại file object khác, lựa chọn giữa stream, reader và char content phụ thuộc contract mà compiler sử dụng; hãy triển khai phương thức phù hợp với kind và mục tiêu.

## 5. Phân tích ClassFile: nơi lưu bytes thật sự

`ClassFile` cũng mở rộng `SimpleJavaFileObject`, nhưng sử dụng `Kind.CLASS` và URI `mem:///demo/Hello.class`. Quan trọng nhất:

```java
@Override
public OutputStream openOutputStream() {
    return data;
}
```

Khi compiler được cung cấp file object làm output, nó ghi class-file bytes vào stream này. `ByteArrayOutputStream` tích lũy các byte. Sau `task.call()`, gọi `data.toByteArray()` để lấy **bản sao** nội dung.

Không được nhầm hai bước:

- `getJavaFileForOutput(...)` **chọn nơi ghi**; trả object thôi chưa có nghĩa đã có bytecode hoàn chỉnh.
- `openOutputStream()` là **đường nhận byte** mà compiler dùng khi code generation và ghi file.

Byte array không phải mã nguồn dạng UTF-8. Nó là **JVM class file** ở định dạng binary; không nên chuyển nó thành `new String(bytes, UTF_8)` để đọc như text. Nếu cần xem nội dung class, dùng công cụ phân tích class-file, `javap` sau khi có artifact, hoặc thư viện bytecode thích hợp.

Class file hợp lệ bắt đầu bằng magic bytes `CA FE BA BE`; tuy nhiên kiểm tra bốn byte đầu **không đủ** để chứng minh class hợp lệ về toàn bộ cấu trúc và khả năng nạp. Compiler status và việc thực sự nạp/đọc bytecode mới là những kiểm tra sâu hơn.

## 6. Vì sao cần Map<String, ClassFile> thay vì một byte[]?

Một compilation có thể sinh:

- Class top-level, ví dụ `demo.Hello`.
- Nested/member class, ví dụ `demo.Hello$Nested`.
- Anonymous class, ví dụ `demo.Hello$1`.
- Các class phụ sinh từ enum, record hoặc construct khác tùy Java source.
- Nhiều top-level classes khi một compilation unit chứa nhiều khai báo hoặc có nhiều file nguồn.

Tên map nên dùng **binary class name** do compiler truyền vào `getJavaFileForOutput`. Với nested class, binary name thường có ký tự `$`, không phải chuỗi `demo.Hello.Nested`.

Nếu chỉ giữ một biến `byte[] output` và mỗi lần callback lại gán đè, kết quả của class trước sẽ bị mất. Map giúp giữ một byte array riêng cho mỗi class. Ở ví dụ, `classes.put(className, result)` diễn ra trước khi compiler ghi byte vào stream; sau khi `task.call()` kết thúc, `snapshot()` lấy bản sao.

Để đảm bảo output ổn định, code nên kiểm tra **key set mong đợi** và kích thước hợp lý thay vì dựa vào thứ tự callback. Nếu một compilation task tạo lại cùng binary name, hành vi ghi đè map có thể che lỗi thiết kế; công cụ sản xuất nên phát hiện collision và báo diagnostic/thất bại thay vì im lặng giữ class cuối.

## 7. Cơ chế Forwarding và delegation

`ForwardingJavaFileManager<StandardJavaFileManager>` không thay mọi tính năng của file manager chuẩn. Chỉ một method được override:

```java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {

    if (location == StandardLocation.CLASS_OUTPUT
            && kind == JavaFileObject.Kind.CLASS) {
        // Capture class output.
    }

    return super.getJavaFileForOutput(
            location, className, kind, sibling);
}
```

Phần còn lại — ví dụ các kiểu có sẵn của Java SE, JAR trên classpath, option handling hoặc đọc source theo các location mặc định — được manager gốc xử lý theo contract tương ứng.

**Lưu ý về Java 18+:** `JavaFileManager` bổ sung các phương thức output nhận originating files, như `getJavaFileForOutputForOriginatingFiles(...)`. `ForwardingJavaFileManager` hiện hành quy định nếu subclass đã override `getJavaFileForOutput(...)`, phương thức dạng originating-files sẽ chuyển tới override ấy; nếu không, nó chuyển trực tiếp tới manager gốc. Khi dùng compiler implementation khác hoặc tối ưu cho một release cụ thể, nên kiểm tra contract của JDK tương ứng và thử nghiệm cả các đường output mà compiler sử dụng. Cách chặn trong ví dụ dựa vào API được mô tả cho Java 21.

Nếu application cũng cần giữ **generated source** hoặc resource trong RAM, chỉ chặn `CLASS_OUTPUT` không đủ. Cần xem `getJavaFileForOutput(...)` cho source, `getFileForOutput(...)` cho resource và các location như `SOURCE_OUTPUT`; đôi khi cần cài đặt thêm phương thức **đọc lại** generated source/class từ RAM. Đây là mở rộng của bài toán, không phải hệ quả tự động từ một override.

## 8. JavaCompiler.getTask và quy trình thực thi

Trong ví dụ:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, List.of(input));
```

Các tham số có vai trò:

| Tham số | Giá trị trong demo | Ý nghĩa |
| --- | --- | --- |
| Writer | `null` | Dùng output writer mặc định cho thông tin không đi qua listener |
| File manager | `manager` | Forwarding manager chặn class output |
| Diagnostic listener | `diagnostics` | Thu lỗi/warning/note có cấu trúc |
| Options | `--release 17`, `-proc:none` | Biên dịch theo Java 17, không chạy annotation processors |
| Classes | `null` | Không yêu cầu danh sách class riêng phục vụ annotation processing |
| Compilation units | `List.of(input)` | Một source file object được compiler đọc trong RAM |

`getTask(...)` **tạo tác vụ**, `task.call()` mới thực hiện compilation. Một task chỉ nên được gọi **một lần**; muốn compile bộ source khác thì tạo task mới.

`Boolean.TRUE.equals(task.call())` trả boolean biểu thị thành công theo JavaCompiler API. Khi task thất bại, manager có thể đã nhận một số output tạm/partial từ trước thời điểm lỗi; do đó không nên “publish” các byte đã thu nếu `success != true`.

Dùng `-proc:none` để bài tập cô lập khỏi annotation processor có thể nằm trên classpath. Nếu muốn thực sự chạy annotation processor, phải quản lý thêm processor path, vòng xử lý và file sinh ra. Từ JDK 23, hành vi kích hoạt processing mặc định đã thay đổi; explicit options giúp kết quả demo ít phụ thuộc môi trường.

## 9. Đọc DiagnosticCollector thay vì parse stderr

`DiagnosticCollector<JavaFileObject>` thu những diagnostic mà compiler hoặc processor phát ra. Mỗi diagnostic có:

- `getKind()`: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` hoặc `OTHER`.
- `getSource()`: source liên quan nếu biết, có thể `null`.
- `getLineNumber()`, `getColumnNumber()`, `getPosition()`: vị trí nếu biết, nếu không là `Diagnostic.NOPOS`.
- `getMessage(Locale)`: thông điệp cho người đọc, **không** phải schema ổn định để một chương trình parse.
- `getCode()`: mã compiler cung cấp nếu có; **implementation-dependent**, không nên dựa vào nó như một chuẩn chung cho mọi JDK.

Với input là `SimpleJavaFileObject`, source name được cung cấp bởi file object, không nhất thiết là path thật trên disk.

Trong ứng dụng thực tế, nên dùng compilation status và diagnostic kind để phân loại. Để hiển thị lỗi cho người dùng, hiển thị message cùng source/line/column nếu có; không khóa nghiệp vụ vào một câu tiếng Anh của `javac`.

Một ví dụ nguồn cố ý sai:

```java
package demo;
public class Broken {
    int value = "not an integer";
}
```

Nếu thay `source` trong demo bằng chuỗi trên và đồng thời dùng `new SourceFile("demo.Broken", source)`, task sẽ báo lỗi `String` không tương thích `int`. Không có quy tắc “cứ compiler gặp lỗi là map class hoàn toàn rỗng” trong mọi compilation nhiều file; cần kiểm tra `success` trước khi sử dụng bytes.

Đây là **mã minh họa lỗi**, không phải class chạy độc lập. Lời giải thích lỗi có thể đổi theo compiler/locale. Đừng cố ấn định toàn bộ stderr trong unit test.

## 10. Nạp bytecode bằng ClassLoader: vì sao đây là một bước khác?

Sau compilation, byte array chỉ là dữ liệu. Để thực thi class, JVM cần được yêu cầu định nghĩa/nạp class qua class loader hoặc một cơ chế liên quan.

Trong ví dụ, `BytesLoader` ghi đè `findClass`:

```java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = classes.get(name);
    if (bytes == null) {
        throw new ClassNotFoundException(name);
    }
    return defineClass(name, bytes, 0, bytes.length);
}
```

`defineClass` chuyển bytecode thành một `Class<?>` do loader đó định nghĩa, có thể dẫn tới verify/linking theo quy tắc JVM. Sau đó:

```java
Class<?> klass = loader.loadClass("demo.Hello");
Object result = klass.getMethod("text").invoke(null);
```

được dùng để kiểm chứng phương thức public `text()` trả về `ready`.

**Cảnh báo:** `ClassLoader.loadClass` có cơ chế **parent-first delegation** thông thường. Nếu parent đã có class cùng binary name, `loadClass` có thể dùng class parent thay vì class mới được capture; khi đó test tưởng đang chạy bytes mới nhưng thực chất chạy artifact cũ. Demo chọn `demo.Hello` không nằm trên application classpath. Với hệ thống hỗ trợ hot reload, phải thiết kế loader namespace/identity và lifecycle thật cẩn thận.

Class identity trong JVM không chỉ là tên binary; nó còn phụ thuộc **defining class loader**. Hai loader định nghĩa hai class cùng tên vẫn có thể tạo ra hai kiểu runtime khác nhau và gây `ClassCastException` khi trộn. Class loader riêng cũng không làm bytecode từ nguồn không tin cậy tự nhiên an toàn.

## 11. Nhiều class có phụ thuộc nhau: chỉ bắt output thôi có đủ?

Đối với **một task** biên dịch `demo.A` và `demo.B` cùng lúc, compiler thường có đủ symbol từ compilation units để kiểm tra các phụ thuộc; map nhận class output tương ứng. Nhưng nếu biên dịch lần một chỉ nhận `A.class` trong RAM và lần hai cần biên dịch `B.java` dựa trên `A`, việc giữ `A` trong map **không làm `StandardJavaFileManager` tự đọc được nó**.

Cần thiết kế thêm một file manager hỗ trợ **input**:

- `getJavaFileForInput(...)`: trả một `JavaFileObject` chứa bytes class đã compile cho tên và location phù hợp.
- `list(...)`: khi compiler liệt kê các class của một package, cung cấp các class object trong RAM theo yêu cầu hợp đồng.
- `inferBinaryName(...)`: trả đúng binary name cho file object tùy biến.
- `hasLocation(...)`, module-aware methods hoặc các phương thức liên quan tùy mục tiêu; không giả định mọi trường hợp đều dùng cùng một đường tìm.

Điều đó phức tạp hơn chặn output. Đối với chương trình học, cách đơn giản là đưa tất cả source cần biên dịch **vào cùng một compilation task**. Nếu thật sự cần incremental in-memory compiler, nên thiết kế và kiểm thử mọi ngả tìm symbol theo contract `JavaFileManager`, bao gồm package, nested types, generated sources và classpath/module path.

Đừng mô tả một `Map<String, byte[]>` thu output như một “classpath trong bộ nhớ” đã hoàn chỉnh. Nó chỉ là **kho kết quả**, chưa cung cấp đầy đủ interface lookup mà compiler cần.

## 12. Khi dùng annotation processor hoặc generated source

Annotation processor có thể:

1. Đọc root elements và annotation của source.
2. Gọi `Filer.createSourceFile(...)` để sinh Java source ở `SOURCE_OUTPUT`.
3. Tạo resource hoặc class file bổ sung bằng API của `Filer`.
4. Gây ra các vòng xử lý tiếp theo để compiler đọc source vừa sinh.

Nếu forwarding manager chỉ chặn:

```java
location == StandardLocation.CLASS_OUTPUT
        && kind == JavaFileObject.Kind.CLASS
```

thì nó **không đảm bảo tất cả generated sources/resources đều trong RAM**. Có output có thể được ủy quyền cho manager nền và ghi xuống filesystem, hoặc thất bại nếu chưa cấu hình location hợp lệ.

Để làm pipeline **hoàn toàn in-memory**, cần mở rộng xử lý `getJavaFileForOutput` cho `SOURCE_OUTPUT`, `getFileForOutput` cho resources, và input/lookup cho các file mới nếu compiler cần đọc chúng ở round sau. Cần quan tâm cả các API origin-aware từ JDK 18, việc đóng stream và phản hồi file objects đúng kind.

Với bài tập, dùng `-proc:none` để tránh trường hợp đó. Khi tích hợp processor thật, hãy tạo integration tests: processor được gọi hay chưa, source có được sinh đúng không, round tiếp có đọc được file không, class cuối được capture đủ không.

## 13. File manager có thể vẫn truy cập filesystem

Chữ “in-memory” ở bài này áp dụng **nguồn `String`** và **đầu ra class bytes**. File manager vẫn ủy quyền các việc sau cho `StandardJavaFileManager`:

- Tra cứu platform classes từ JDK.
- Đọc JAR/classpath nếu options hoặc môi trường yêu cầu.
- Đọc source phụ thuộc từ sourcepath/classpath trong cấu hình rộng hơn.
- Truy cập metadata file/locations hay mở JAR theo nhu cầu.
- Ghi các output khác nếu không có override tương ứng.

Vì vậy đây **không phải sandbox**. Biên dịch source người dùng không tin cậy còn có rủi ro nếu annotation processor/plugin chạy code tùy ý trong process. Việc `-proc:none` ngăn annotation processing theo cách thông thường không đồng nghĩa khóa toàn bộ quyền truy cập hệ thống hoặc tạo một môi trường bảo mật cho compiler/toolchain.

Nếu ứng dụng đa tenant cần chạy code sau khi compile, phải có giới hạn CPU/RAM, isolation phù hợp, quyền filesystem/network và class loader policy; chỉ dùng `ForwardingJavaFileManager` là không đủ.

## 14. Quản lý tài nguyên và vòng đời

`CaptureManager` trong ví dụ kế thừa `ForwardingJavaFileManager` và triển khai `Closeable` thông qua `JavaFileManager`. `try-with-resources` giúp đóng manager ở cuối:

```java
try (CaptureManager manager = new CaptureManager(
        compiler.getStandardFileManager(
                diagnostics, Locale.ROOT,
                StandardCharsets.UTF_8))) {
    // Tạo compilation task, gọi call(), sao chép byte[].
}
```

`ForwardingJavaFileManager.close()` chuyển thao tác đóng tới manager nền, nhả những handle mà `StandardJavaFileManager` quản lý. Trong ví dụ, `snapshot()` sao chép `ByteArrayOutputStream` thành `byte[]` trước khi manager bị đóng, nên kết quả tồn tại độc lập sau khối `try`.

Một số quy tắc vận hành:

- Tạo **`CompilationTask` mới cho mỗi lượt**; không gọi lại một task đã kết thúc.
- Chạy nhiều task tuần tự có thể dùng lại standard file manager theo contract và kiểm soát state cẩn thận; với output capture, phải tạo map riêng/làm sạch output per run.
- Không tự giả định file manager hoặc map của bạn thread-safe. Nếu biên dịch đồng thời, cần cô lập instance per task hoặc đồng bộ hóa đúng.
- `ByteArrayOutputStream` tăng bộ nhớ theo tổng bytecode; nếu compile nhiều class, đặt giới hạn tổng kích thước/quota và giải phóng map sau khi dùng.
- Không publish bytes của một compilation thất bại như artifact đã kiểm chứng.
- Nếu muốn lưu vào JAR/disk sau đó, đó phải là bước riêng, với quy tắc tên entry `demo/Hello.class` tương ứng binary name, không phải viết bytes như text.

## 15. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` trả `null` | Runtime không có system compiler | Dùng JDK/runtime image có compiler cần thiết |
| `getJavaFileForOutput` không được gọi | Task không chạy, lỗi xảy ra trước codegen, hoặc compiler dùng đường output khác | Xem `task.call()`, diagnostic, location/kind |
| Map chỉ có một class nhưng dự kiến nhiều class | Chưa lưu theo từng binary name, hoặc source không tạo thêm class | Ghi key names và tạo map per output |
| Class được capture nhưng bytes rỗng | Stream chưa được ghi/đóng, đọc snapshot quá sớm hoặc compilation thất bại | Snapshot sau `call()` và kiểm tra status |
| Source không compile | Sai package/class name, lỗi cú pháp/kiểu, options, classpath | Đọc `DiagnosticCollector`; kiểm tra source string |
| `IllegalArgumentException` từ URI | URI logic không hợp lệ, ký tự hoặc scheme/path bị xây sai | Dùng `URI.create` với URI hợp lệ, chuẩn hóa tên class |
| `ClassNotFoundException` khi nạp | Loader không có bytes của class cần tìm | Kiểm tra map key và `findClass` |
| `NoClassDefFoundError` khi dùng class | Thiếu một dependency lúc runtime, có thể nested/dependency khác | Cung cấp bytes của toàn bộ dependency hoặc parent loader phù hợp |
| `ClassCastException` giữa hai class cùng tên | Class được định nghĩa bởi hai loader khác nhau | Kiểm soát classloader identity và giao diện chung |
| File `.class` vẫn xuất hiện trên disk | Có output request không bị chặn, processor tạo file, hoặc file cũ | Kiểm tra `location/kind` và output sạch |
| Nhiều lần compile thấy bytes cũ | Giữ map qua các lượt hoặc không reset manager | Một manager/map per task, cập nhật theo lifecycle rõ |
| OOM khi build lớn | Byte arrays tích lũy trong RAM | Áp hạn mức, stream theo chính sách, xóa artifact không cần |
| Biên dịch được nhưng nạp class thất bại | Linkage/verification, thiếu classpath hoặc mismatch JDK | Đọc throwable gốc, kiểm tra `--release` và dependencies |

Phân biệt **compiler diagnostics**, **class output capture** và **class loading**. Ba bước này có thể thất bại độc lập. Thấy byte[] trong map chưa chứng minh code đã được link/nạp và chạy thành công.

## 16. Những lỗi thiết kế nên tránh

**Trả cùng một ByteArrayOutputStream cho mọi class.** Nhiều class file sẽ bị trộn bytes, tạo artifact hỏng. Mỗi binary name cần một object/stream riêng.

**Dùng class name như file path tùy ý mà không chuẩn hóa.** Với `demo.Hello`, URI logic nên được xây theo package path. Nested class có thể có ký tự `$` trong binary name.

**Quên chặn đúng output location.** `CLASS_OUTPUT` là đích class file thông thường của demo. Các output khác cần xử lý theo chức năng tương ứng; không chặn bừa mọi `getFileForOutput`.

**Mất khả năng đọc dependency.** Nếu thay hẳn `JavaFileManager` bằng một implementation thiếu `list`, `inferBinaryName` và xử lý platform classes, compiler có thể không phân giải được tên. Forwarding cho phép giữ tính năng chuẩn và chỉ đổi nơi ghi class.

**Giữ bytecode khi biên dịch lỗi rồi đưa ra runtime.** Compiler có thể tạo artifact một phần trước khi thất bại; chỉ publish khi status và diagnostics được xử lý.

**Gọi `new String(classBytes)` để lưu bytecode.** Class file là nhị phân, không phải UTF-8 text. Ghi raw bytes khi lưu hoặc dùng Base64 nếu cần truyền qua giao thức text.

**Dùng class loader parent-first nhưng mong tự động thay thế class đã load.** Nếu parent đã có binary name, class mới có thể không được chọn. Cần thiết kế loader và versioning cho hệ thống hot reload.

**Cho rằng compilation hoàn toàn không chạm file system.** Compiler vẫn có thể đọc JDK/JAR và quản lý output khác; không dùng thủ thuật capture bytes làm security isolation.

## 17. Bài tập và câu trả lời

**Bài 1.** Compiler yêu cầu ghi `demo.Hello$Nested`. Tại sao không nên lưu vào duy nhất biến `byte[] helloBytes`?

**Đáp án:** Một source tạo nhiều class. Phải lưu theo từng binary name để không mất class lồng nhau hoặc class khác.

**Bài 2.** Ghi đè `getJavaFileForOutput(...)` đã đủ để khiến compiler có thể đọc class bytecode đã capture từ **task trước** chưa?

**Đáp án:** Chưa. Cần cung cấp đường **input/lookup** thích hợp như `getJavaFileForInput`, `list` và `inferBinaryName` hoặc đặt tất cả source vào cùng task.

**Bài 3.** `ClassFile.openOutputStream()` trả một stream nào để lưu trong RAM?

**Đáp án:** Một `ByteArrayOutputStream` thuộc riêng class output object; lấy bản sao bằng `toByteArray()` sau khi compile.

**Bài 4.** Nếu compiler tạo file resource qua annotation processor, override dành riêng `CLASS_OUTPUT + Kind.CLASS` có đảm bảo resource nằm trong RAM không?

**Đáp án:** Không. Cần xử lý thêm output location và file object cho resource.

**Bài 5.** `task.call()` trả `false` nhưng map có một số bytes. Có thể trả kết quả đó như build thành công không?

**Đáp án:** Không. Chúng có thể là output partial; cần dựa trên compilation status và diagnostic.

**Bài 6.** Tại sao `LoaderA.loadClass("demo.Hello")` và `LoaderB.loadClass("demo.Hello")` có thể tạo hai runtime types khác nhau?

**Đáp án:** Class identity gồm cả defining class loader, không chỉ binary name.

**Bài 7.** Vì sao trong demo phải dùng `TreeSet` khi in danh sách class names?

**Đáp án:** Không nên dựa vào thứ tự compiler gọi callback. `TreeSet` sắp xếp keys để output text ổn định.

**Bài 8.** Kết quả thật của chương trình `MemoryBytecodeDemo` đã kiểm tra trên JDK 21 là gì?

**Đáp án:** `success=true`, `classCount=2`, `classes=[demo.Hello, demo.Hello$Nested]`, `errors=0`, `result=ready`.

## 18. Checklist áp dụng trong hệ thống thật

1. Xác định cần **thu class file cuối**, generated source hay cả dependency class input; các nhu cầu này cần mức tùy chỉnh khác nhau.
2. Dùng `ToolProvider.getSystemJavaCompiler()` và kiểm tra compiler có sẵn.
3. Dùng `StandardJavaFileManager` làm delegate để giữ khả năng tìm JDK classes/JAR.
4. Tạo source `SimpleJavaFileObject` với URI logic và `getCharContent()`, hoặc dùng file source thực nếu cần.
5. Override `getJavaFileForOutput` cho đúng `CLASS_OUTPUT` và `Kind.CLASS`.
6. Tạo **một output object per binary class name**, stream riêng, map riêng per task.
7. Gọi `compiler.getTask(...)`, truyền options và `DiagnosticCollector` rõ ràng.
8. Gọi `task.call()` đúng một lần; không phát hành kết quả nếu thất bại.
9. Snapshot toàn bộ byte[] sau khi task kết thúc; đóng manager.
10. Nếu cần runtime execution, dùng class loader phù hợp và kiểm tra dependencies; đừng giả định parent-first luôn chọn bytes mới.
11. Nếu cần incremental compile hoặc processor, mở rộng input/output contract và kiểm thử vòng xử lý, locations, nested classes.
12. Với môi trường untrusted/multi-tenant, thiết kế cô lập và quota độc lập với file manager.
13. Test trên JDK/toolchain thực tế; giữ `--release` phù hợp target Java.
14. Dùng kết quả build, `Diagnostic.Kind` và artifacts để kiểm thử; không phụ thuộc nguyên văn stdout/stderr compiler.

## 19. Kết luận và tài liệu chính thức

`ForwardingJavaFileManager` là cách mở rộng Java Compiler API **theo hướng ủy quyền**: giữ toàn bộ khả năng thông thường của `StandardJavaFileManager`, chỉ đổi cách xử lý một vài yêu cầu. Với bài toán thu bytecode, **ghi đè `getJavaFileForOutput`**, trả một `SimpleJavaFileObject` có `openOutputStream()` dẫn vào `ByteArrayOutputStream`, rồi lấy bytes sau `CompilationTask.call()`. Đây là một chuỗi thao tác có thể kiểm chứng: **source → compiler → output object → bytes map → optional class loader**.

Mấu chốt là phải giữ rõ giới hạn: map bytecode chỉ thu **output**, không tự cung cấp **input classpath trong RAM**, không tự quản lý generated source/resource và không trở thành sandbox. Với những ranh giới đó, kỹ thuật này hữu ích cho công cụ phân tích, trình biên dịch động, hệ thống sinh mã và các test muốn kiểm tra bytecode mà không phải quản lý các file class tạm.

Nguồn tham khảo:

- [Java SE 21 ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): hợp đồng delegation và các phương thức output.
- [Java SE 21 JavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): `getJavaFileForOutput`, input/list/inferBinaryName, locations.
- [Java SE 21 SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): cách tạo file object từ URI, override char/byte I/O.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `getStandardFileManager`, compilation lifecycle.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): thu compiler diagnostics có cấu trúc.
