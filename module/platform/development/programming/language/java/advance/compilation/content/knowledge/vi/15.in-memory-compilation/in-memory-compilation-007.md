# Quản lý vòng đời bộ đệm, file manager và kết quả thất bại

**Biên dịch Java trong bộ nhớ** là kỹ thuật đưa mã nguồn cho `JavaCompiler` mà không bắt buộc lưu từng tệp `.java` xuống đĩa, rồi thu nhận các classfile `.class` vào bộ đệm byte thay vì một thư mục đầu ra thông thường. Nó hữu ích khi tạo mã động, kiểm tra lời giải, phân tích mã hoặc thử nghiệm những nguồn Java ngắn trong một công cụ phát triển.

Tuy nhiên, viết một `SimpleJavaFileObject` chứa chuỗi mã nguồn mới chỉ là bước đầu. Một thiết kế đáng tin cậy phải trả lời thêm:

- **Bộ đệm thuộc về ai?** Ai tạo, giữ, sao chép và giải phóng bytecode?
- **File manager sống đến lúc nào?** Khi nào compiler cần nó, khi nào phải `close()`, và có được dùng lại?
- **Nếu biên dịch thất bại thì sao?** Có được trả các classfile đã tạo dở hoặc giữ lại kết quả lần trước?
- **Diagnostics nằm ở đâu?** Làm sao phân biệt lỗi nguồn, lỗi cấu hình, ngoại lệ I/O và môi trường không có compiler?
- **Nhiều tác vụ đồng thời thì sao?** Làm sao tránh việc một tác vụ ghi vào buffer của tác vụ khác?

Nguyên tắc thiết kế xuyên suốt: **mỗi lượt biên dịch sở hữu trạng thái tạm riêng; chỉ xuất bản bản chụp kết quả sau khi cả lượt thành công; mọi đường thoát đều đóng file manager và không làm rò các bộ đệm dở.**

Bài dùng **Java 17+**, API chuẩn `javax.tools`, ví dụ biên dịch một lớp trong RAM rồi biên dịch một phiên bản cố ý sai kiểu. Chương trình chính chạy được và in trạng thái của cả hai lượt mà không ghi các classfile được sinh vào đĩa.

## 1. Luồng dữ liệu trong một lượt in-memory compilation

Sơ đồ cơ bản:

~~~text
Chuỗi Java source
      |
      v
StringSource : SimpleJavaFileObject
      |
      |  JavaCompiler.getTask(... compilationUnits)
      v
MemoryFileManager : ForwardingJavaFileManager
      |
      |  compiler gọi getJavaFileForOutput(...)
      v
MemoryClass : SimpleJavaFileObject
      |
      |  openOutputStream() trả ByteArrayOutputStream
      v
Bộ đệm bytecode tạm của lượt biên dịch
      |
      +-- task.call() == true
      |       |
      |       v
      |   Sao chép kết quả -> BuildResult SUCCESS
      |
      +-- task.call() == false
      |       |
      |       v
      |   Không publish bytecode -> BuildResult FAILED
      |
      +-- Exception / thiếu compiler
              |
              v
          Xử lý riêng theo nguyên nhân

Cuối cùng: close file manager, bỏ tham chiếu trạng thái tạm
~~~

Đây là một luồng **giao dịch theo chính sách của ứng dụng**, không phải cam kết rằng `javac` thực hiện “transaction” tự động. Compiler có thể đã phát ra một hoặc nhiều classfile trước khi phát hiện lỗi ở đơn vị nguồn khác. Vì vậy **ứng dụng chủ động quyết định không công bố output nếu toàn lượt thất bại**.

### Các đối tượng có vòng đời khác nhau

| Đối tượng | Vòng đời khuyến nghị | Trách nhiệm |
| --- | --- | --- |
| Chuỗi nguồn/`StringSource` | Trong lượt hoặc lưu lâu hơn nếu cần chẩn đoán | Giữ text của một đơn vị nguồn |
| `DiagnosticCollector` | **Mỗi lượt biên dịch** | Ghi nhận diagnostic của chính lượt đó |
| `StandardJavaFileManager` | Một lượt hoặc được tái sử dụng có kiểm soát | Tra cứu lớp, nguồn, module và tài nguyên từ môi trường chuẩn |
| `MemoryFileManager` | **Mỗi lượt** trong thiết kế mẫu | Chuyển output class từ compiler sang RAM, nắm map output tạm |
| `MemoryClass`/`ByteArrayOutputStream` | Từ lúc compiler yêu cầu output tới khi snapshot/dọn dẹp | Nhận bytes của một classfile |
| `CompilationTask` | **Một lần gọi `call()`** | Điều phối một compilation |
| `BuildResult` | Sau lượt hoàn tất | Trả trạng thái và dữ liệu đã được chấp thuận |

Có thể thiết kế cache và tái sử dụng các thành phần, nhưng điều đó đòi hỏi quy tắc riêng về đóng/mở, invalidation và đồng bộ. Để học cơ chế và tránh rò trạng thái, **một file manager + collector mới cho mỗi lượt** là lựa chọn rõ ràng.

## 2. FileObject không nhất thiết là tệp thật

`JavaFileObject` là mô hình trừu tượng cho đơn vị mã nguồn hoặc class. Chúng có thể được triển khai bằng tệp vật lý, URI hoặc dữ liệu RAM.

Một nguồn Java từ chuỗi thường kế thừa `SimpleJavaFileObject`, cung cấp:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
~~~

Đây là **đoạn method trong subclass**, không phải chương trình độc lập. Compiler sẽ gọi `getCharContent(...)` để lấy nội dung. URI của nguồn cần hợp lệ và thường có phần đuôi `.java` tương ứng loại `JavaFileObject.Kind.SOURCE`.

Một output class được ghi vào RAM thường override:

~~~java
@Override
public OutputStream openOutputStream() {
    return buffer;
}
~~~

Đây cũng là **đoạn method trong subclass**, với `buffer` là `ByteArrayOutputStream`. Khi compiler tạo classfile, nó viết bytes vào stream đó. `ByteArrayOutputStream.toByteArray()` trả **bản sao** của nội dung đang có, giúp kết quả tồn tại độc lập với stream tạm.

**Lưu ý:** một `OutputStream` đóng không nhất thiết xóa dữ liệu bộ nhớ. `ByteArrayOutputStream.close()` không giải phóng mảng ngay lập tức; bộ đệm tiếp tục giữ bytes chừng nào còn được tham chiếu. Khi thiết kế vòng đời, cần **thả tham chiếu** hoặc `reset()` khi thích hợp, chứ không chỉ gọi `close()` rồi giả định bộ nhớ đã sạch.

## 3. Vì sao cần `ForwardingJavaFileManager`?

`JavaCompiler` dùng `JavaFileManager` để tìm nguồn/lớp và để tạo tệp output. Không nên tự triển khai toàn bộ cơ chế tìm class của JDK chỉ để thay đổi nơi nhận classfile.

`ForwardingJavaFileManager` cho phép **ủy quyền** những thao tác phức tạp cho file manager chuẩn và chỉ override phần cần thay, chẳng hạn:

~~~java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {

    if (kind == JavaFileObject.Kind.CLASS) {
        // Tạo JavaFileObject có output stream lưu bytes trong RAM.
    }
    return super.getJavaFileForOutput(location, className, kind, sibling);
}
~~~

Đây là **mã minh họa bên trong một subclass của `ForwardingJavaFileManager`**. Nó giải thích điểm móc (hook) nơi compiler yêu cầu nơi lưu classfile. Ở ví dụ chính, đối tượng class output được giữ trong một `Map` gắn với lượt biên dịch.

File manager không phải một kho dữ liệu bất biến: nó có state, tham chiếu tới delegate, và có thể nắm tài nguyên. `JavaFileManager` hỗ trợ `close()`; file manager chuẩn thường nên được đóng khi không còn cần. Dùng `try-with-resources` là cách rõ ràng để đảm bảo đóng **kể cả task thất bại hoặc ném exception**.

Không nên đóng file manager **trước** khi `task.call()` kết thúc: compiler vẫn có thể cần nó để đọc dependency, ghi classfile hay phát sinh các vòng annotation processing.

## 4. Ví dụ Java 17+: biên dịch source thành bytes, chỉ công bố khi thành công

Tạo file **`InMemoryLifecycleDemo.java`** với nội dung sau. Ví dụ đầy đủ gồm một source object, class output object, file manager chuyển tiếp và một kết quả biên dịch. Không tạo tệp nguồn phụ trong lúc chạy: cả nguồn đầu vào và class output đều ở RAM.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryLifecycleDemo {
    private InMemoryLifecycleDemo() {
    }

    private static final class StringSource extends SimpleJavaFileObject {
        private final String sourceCode;

        StringSource(String binaryName, String sourceCode) {
            super(URI.create(
                    "string:///" + binaryName.replace('.', '/')
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.sourceCode = sourceCode;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return sourceCode;
        }
    }

    private static final class MemoryClass extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes =
                new ByteArrayOutputStream();

        MemoryClass(String binaryName, Kind kind) {
            super(URI.create(
                    "mem:///" + binaryName.replace('.', '/')
                            + kind.extension),
                    kind);
        }

        @Override
        public OutputStream openOutputStream() {
            bytes.reset();
            return bytes;
        }

        byte[] snapshot() {
            return bytes.toByteArray();
        }
    }

    private static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, MemoryClass> generated =
                new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (kind == JavaFileObject.Kind.CLASS) {
                MemoryClass output = new MemoryClass(className, kind);
                generated.put(className, output);
                return output;
            }
            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> copy = new LinkedHashMap<>();
            for (var entry : generated.entrySet()) {
                copy.put(entry.getKey(), entry.getValue().snapshot());
            }
            return Map.copyOf(copy);
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                generated.clear();
            }
        }
    }

    private record BuildResult(
            boolean success,
            Map<String, byte[]> classes,
            boolean hasErrors) {
    }

    private static BuildResult compile(
            JavaCompiler compiler, String sourceCode) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        StandardJavaFileManager delegate =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);

        try (MemoryFileManager manager = new MemoryFileManager(delegate)) {
            JavaFileObject source =
                    new StringSource("demo.Generated", sourceCode);

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    options,
                    null,
                    List.of(source));

            boolean success = Boolean.TRUE.equals(task.call());
            boolean hasErrors = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            // Không dùng classfile tạm nếu toàn lượt thất bại.
            Map<String, byte[]> published = success
                    ? manager.snapshot()
                    : Map.of();

            return new BuildResult(success, published, hasErrors);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.err.println("COMPILER_UNAVAILABLE");
            return;
        }

        String valid = """
                package demo;
                public class Generated {
                    public static int answer() {
                        return 42;
                    }
                }
                """;

        String invalid = """
                package demo;
                public class Generated {
                    public static int answer() {
                        return "not an int";
                    }
                }
                """;

        BuildResult ok = compile(compiler, valid);
        BuildResult bad = compile(compiler, invalid);

        System.out.println("ok=" + ok.success());
        System.out.println("okClasses=" + ok.classes().size());
        System.out.println("bad=" + bad.success());
        System.out.println("badClasses=" + bad.classes().size());
        System.out.println("badHasErrors=" + bad.hasErrors());
    }
}
~~~

Biên dịch **chương trình điều phối** và chạy bằng JDK có compiler:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryLifecycleDemo.java
java InMemoryLifecycleDemo
~~~

Khi compiler có mặt và môi trường biên dịch hợp lệ, **stdout chính xác**:

~~~text
ok=true
okClasses=1
bad=false
badClasses=0
badHasErrors=true
~~~

Diễn giải:

- `valid` là một lớp `demo.Generated` có kiểu trả về `int` đúng. Lượt thứ nhất biên dịch thành công, trả map có **một** classfile.
- `invalid` trả chuỗi `"not an int"` từ phương thức có kiểu trả về `int`. Lượt thứ hai tạo diagnostic `ERROR` và biên dịch thất bại.
- Đối với lượt lỗi, `bad.classes().size()` là **0 theo chính sách của phương thức `compile`**: code chỉ gọi `manager.snapshot()` khi `success == true`.
- Các bộ đệm tạm của lượt lỗi không được công bố. Điều này **không có nghĩa compiler luôn chưa ghi byte nào** trước khi báo lỗi.
- Hai lần gọi `compile` có file manager, map output và collector riêng. Kết quả lượt đầu không bị lẫn với lượt sau.

Ở nhánh thiếu compiler, chương trình chỉ in `COMPILER_UNAVAILABLE` ra **stderr** rồi return, nên không có năm dòng stdout trên. Chỉ khi chạy bằng runtime có compiler mới dự đoán stdout như khối trên.

### Điểm thiết kế đáng chú ý trong ví dụ

**1. Nguồn tách khỏi output.** `StringSource` dùng URI có `.java` và cấp nội dung qua `getCharContent`. `MemoryClass` dùng URI có `.class` và cấp `OutputStream` cho compiler.

**2. Dùng file manager chuẩn làm delegate.** `MemoryFileManager` chỉ chặn `getJavaFileForOutput` đối với `Kind.CLASS`; phần tìm kiếm nguồn, API JDK và các thao tác không chặn vẫn được file manager chuẩn đảm nhiệm.

**3. Chặn output ở điểm compiler yêu cầu.** Mỗi class được compiler đề nghị tạo một `MemoryClass` và được lưu theo `className`. Dự án thật có thể sinh thêm inner/nested/anonymous classes; **không được mặc định mỗi tệp nguồn chỉ tạo một classfile**. Ví dụ đơn giản này chỉ sinh một lớp.

**4. Snapshot trước khi đóng.** Khi `task.call()` thành công, `manager.snapshot()` sao chép bytes qua `toByteArray()`. Khi `try-with-resources` đóng manager, `generated.clear()` thả các tham chiếu tới buffer tạm. Map kết quả giữ các mảng bytes đã sao chép.

**5. Không lẫn kết quả thất bại.** Lượt lỗi trả `Map.of()`, mặc dù buffer tạm có thể đã nhận một phần output. Không cache hay nạp bytecode từ một lượt chưa thành công.

**6. Tắt annotation processing trong thí nghiệm.** `-proc:none` làm ví dụ tập trung vào việc biên dịch Java thuần và tránh nạp annotation processors được tìm thấy ngoài ý muốn. Trong hệ thống cần processor, hãy bật có chủ đích và cấu hình processor path/độ tin cậy tương ứng.

**7. Kết quả map chưa phải bất biến sâu.** `Map.copyOf(copy)` không cho thêm/xóa key, nhưng `byte[]` vẫn là mảng **có thể sửa**. Nếu public API trả bytecode cho nhiều caller, hãy sao chép mảng khi trao ra, dùng wrapper chỉ đọc hoặc thiết kế ownership rõ. Một snapshot đúng thời điểm **không tự biến mọi giá trị bên trong thành immutable**.

## 5. Vòng đời bộ đệm: tạo, ghi, snapshot, loại bỏ

Một `ByteArrayOutputStream` được cấp phát khi compiler yêu cầu class output. Trong quá trình ghi, dung lượng mảng nội bộ có thể tăng. Với nhiều lớp hoặc một classfile lớn, tổng bộ nhớ dùng cho quá trình biên dịch có thể cao hơn tổng kích thước bytecode cuối cùng.

### Trước khi compile

- Tạo collector mới cho diagnostic.
- Tạo file manager mới cho lượt hiện tại.
- Tạo các `JavaFileObject` nguồn chứa nội dung đã biết.
- Đặt giới hạn về kích thước source, số tác vụ đồng thời và thời gian xử lý theo yêu cầu hệ thống.

### Trong khi compile

- Compiler gọi `getJavaFileForOutput(...)` để yêu cầu nơi nhận classfile.
- Bộ đệm nhận bytes theo các lần ghi.
- Chưa coi bất cứ buffer đang ghi nào là classfile đã sẵn sàng nạp.
- Compiler có thể tạo nhiều class từ một hoặc nhiều đơn vị nguồn.

### Khi compile thành công

- Chỉ sau `Boolean.TRUE.equals(task.call())` mới tạo snapshot toàn bộ classfile.
- Xác nhận những output bắt buộc thực sự có mặt trước khi đưa vào class loader hoặc cache.
- Chuyển ownership của dữ liệu đã sao chép cho đối tượng kết quả.
- Đóng file manager rồi giải phóng bản tạm.

### Khi compile thất bại

- Ghi nhận diagnostic để phản hồi cho caller.
- Bỏ mọi bản classfile tạm **khỏi kết quả public**.
- Đóng file manager kể cả khi không có output hoặc chỉ có một phần.
- Không ghi đè cache bản build tốt trước đó bằng build thất bại.
- Nếu cần giữ lỗi phục vụ người dùng, giữ **diagnostic đã được sao chép**, không giữ cả compiler/manager/buffer quá hạn.

### Tại sao `reset()` không giống `close()`?

`ByteArrayOutputStream.reset()` đặt lại số byte có hiệu lực để có thể sử dụng buffer từ đầu, nhưng thường **giữ mảng dung lượng đã cấp phát**. `close()` không làm mọi tham chiếu đang giữ buffer biến mất. Cả hai đều không đồng nghĩa xóa dữ liệu nhạy cảm khỏi bộ nhớ.

Với nguồn có dữ liệu nhạy cảm, cần chính sách vòng đời nghiêm ngặt, hạn chế log/raw dump và tránh lưu cache không kiểm soát. Đừng quảng cáo rằng gọi `reset()` đủ để bảo đảm xóa sạch bytes khỏi RAM.

## 6. Quản lý `JavaFileManager` đúng cách

Tài nguyên cần được đóng khi không còn sử dụng. Trong ví dụ:

~~~java
try (MemoryFileManager manager = new MemoryFileManager(delegate)) {
    // Tạo task, gọi task.call(), snapshot nếu thành công.
}
~~~

Đây là **đoạn minh họa bên trong method `compile`**, không phải chương trình độc lập. `MemoryFileManager.close()` gọi `super.close()` để đóng delegate, rồi `generated.clear()` trong khối `finally` để bỏ tham chiếu output. Nếu `task.call()` ném exception, Java vẫn gọi `close()`.

### Vì sao không đóng file manager ngay khi tạo task?

`getTask(...)` chỉ chuẩn bị compilation. Compiler còn cần file manager trong `task.call()` để tra cứu classpath, platform classes, tệp nguồn và đường output. Nếu đóng quá sớm, task có thể thất bại vì sử dụng file manager đã đóng.

### Vì sao không giữ file manager vô hạn?

Một file manager có thể duy trì tài nguyên và cache liên quan đường dẫn, ZIP/JAR hoặc kết quả tìm kiếm. Nếu giữ lâu, cần chiến lược invalidation và giới hạn sử dụng. Với service nhiều request, dùng manager riêng mỗi request dễ tránh stale state và nhầm output hơn.

### Có thể dùng lại `StandardJavaFileManager` không?

API cho phép những cách tái sử dụng file manager có kiểm soát trong các compiler tasks, đặc biệt để giảm chi phí quét file hệ thống. Nhưng **không đồng nghĩa an toàn dùng cùng một instance đồng thời từ nhiều thread**. Muốn tái sử dụng phải hiểu hợp đồng API và implementation, reset những vị trí tùy biến và quản lý vòng đời chặt. Bài học dùng một manager mới mỗi lượt để tránh phụ thuộc giả định concurrency.

### Nếu mở file manager thành công nhưng việc chuẩn bị task ném exception?

Bọc file manager trong `try-with-resources` ngay sau khi tạo giúp đóng khi có exception lúc tạo `JavaFileObject`, cấu hình options, gọi `getTask(...)` hoặc `call()`. Nếu việc tạo standard file manager đã thất bại trước khi trả đối tượng, caller phải xử lý exception ở mức tạo môi trường.

## 7. Kết quả thất bại không chỉ là `false`

Cần phân biệt:

| Tình huống | Tín hiệu | Cách xử lý |
| --- | --- | --- |
| Không có compiler | `ToolProvider.getSystemJavaCompiler() == null` | Trả trạng thái `UNAVAILABLE`; không gọi task |
| Mã nguồn sai cú pháp/kiểu | `task.call() == false`, diagnostic `ERROR` | Trả `FAILED` và danh sách lỗi nguồn; không publish output |
| Warning nhưng compile thành công | `task.call() == true` và có warning | Có thể publish, kèm warning theo chính sách |
| Cấu hình option không hợp lệ | Có thể ném exception hoặc báo lỗi công cụ | Phân loại `CONFIGURATION_ERROR`; không giả là lỗi source |
| File manager/đường dẫn gặp I/O error | `IOException` hoặc lỗi triển khai liên quan | Trả `INFRASTRUCTURE_ERROR`, đóng tài nguyên |
| Task bị hủy hoặc hết hạn theo hệ thống điều phối | Trạng thái cancel/timeout do ứng dụng quy định | Không publish output; dọn state và tránh dùng cache dở |

Trong code mẫu, `compile` trả `BuildResult` cho hai trường hợp **task trả bình thường** (thành công hoặc lỗi biên dịch). Nó ném `IOException` nếu gặp lỗi I/O ở tầng file manager; các exception không mong muốn khác vẫn có thể nổi lên. **Không nên biến mọi exception thành một kết quả `false` giống lỗi Java của người dùng.**

Với API production, có thể dùng một kiểu kết quả gồm:

~~~text
BuildOutcome
  status: SUCCESS | COMPILE_FAILED | UNAVAILABLE | INFRASTRUCTURE_ERROR
  diagnostics: danh sách bất biến / đã copy
  classBytes: chỉ có ở SUCCESS
  metadata: thời gian, compiler version, source hash (nếu cần)
~~~

Đây là **sơ đồ thiết kế**, không phải mã Java. Mục tiêu là để caller phân biệt hướng xử lý: người dùng sửa code, admin sửa runtime, hay hệ thống retry theo chính sách. `status` phải đi cùng **ràng buộc không có classBytes khi thất bại**.

### Vì sao cần giữ diagnostics khi build lỗi?

`DiagnosticCollector` có thể báo:

- `Diagnostic.Kind.ERROR`: lỗi ngôn ngữ hoặc cấu hình có vị trí liên quan.
- `WARNING` / `MANDATORY_WARNING`: cảnh báo compiler.
- `NOTE` / `OTHER`: thông báo khác.

Bạn có thể lấy `kind`, `source`, `lineNumber`, `columnNumber` và `getMessage(Locale)`. Không có bảo đảm rằng mọi diagnostic đều có dòng/cột; `Diagnostic.NOPOS` biểu thị vị trí không khả dụng. Khi trả kết quả qua API, hãy **sao chép các trường diagnostic cần thiết** thay vì giữ mọi object compiler/file manager sau khi đóng.

Một phần mở rộng trong `compile` có thể đếm lỗi:

~~~java
long errors = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
        .count();
~~~

Đây là **đoạn minh họa đặt trong method `compile`** sau khi task thực thi. Không nên suy số lỗi là số classfile hỏng hoặc số tệp không hợp lệ. Một source có thể sinh nhiều lỗi; compiler cũng có thể dừng sớm.

## 8. Vì sao failure có thể để lại output tạm?

Đặc tính thực tế của biên dịch nhiều source/round là compiler có thể yêu cầu và ghi một số classfile trước khi phát hiện lỗi ở vị trí khác. Do đó:

~~~text
Lượt build:
  A.java -> A.class đã được ghi vào buffer
  B.java -> compile error
  --------------------------
  task.call() -> false

Chính sách đúng:
  KHÔNG trả A.class như bản build hoàn chỉnh
  Không cập nhật cache "latest successful"
  Trả diagnostics cho người gọi
  Dọn bộ đệm A.class và mọi output tạm
~~~

Đây là một **tình huống minh họa**, không cam kết thứ tự compiler ghi classfile trong mọi lần chạy. Đừng thiết kế test yêu cầu chính xác A.class phải xuất hiện trước khi B.java báo lỗi. Điều cần kiểm thử là **dù output tạm có hay không, kết quả thất bại không bao giờ công bố bytecode dở**.

Nếu hệ thống lưu một bản build tốt trước đó, nên tách:

~~~text
committedBuild : bản dùng được sau lần SUCCESS gần nhất
workingBuild   : buffer tạm của một lần compile mới

SUCCESS -> xác nhận, sao chép, thay committedBuild một lần
FAILURE -> bỏ workingBuild, giữ committedBuild như cũ
~~~

Mô hình này gần với **commit/rollback do ứng dụng tự quản lý**, không phải rollback được `JavaCompiler` bảo đảm. Đối với cache hoặc class loader dùng lâu dài, điều này tránh tình trạng một phần lớp thuộc phiên bản mới trong khi phần còn lại thuộc phiên bản cũ.

### Chỉ đặt `Map.of()` khi lỗi đã đủ chưa?

Đó là một **chính sách publish**, không phải chiến lược giải phóng tài nguyên tự động. Nếu manager vẫn sống và giữ `generated`, bytes tạm vẫn đang chiếm bộ nhớ. Bởi vậy cần **cả hai**: không trả output vào kết quả thất bại **và** đóng/bỏ tham chiếu file manager để bộ nhớ có thể được thu hồi khi không còn sử dụng.

## 9. Nhiều lượt biên dịch và đồng thời

Một service thường nhận nhiều tác vụ cùng lúc. Rủi ro chính:

1. Hai request dùng **chung `Map<String, MemoryClass>`** và cùng class name, dẫn tới overwrite/đọc nhầm bytecode.
2. Collector cũ không được reset, khiến user B nhận diagnostic của user A.
3. Một request đóng file manager trong lúc request khác vẫn đang dùng.
4. Cache classfile được cập nhật từng entry; request khác đọc kết quả nửa mới nửa cũ.
5. Source code lớn hoặc nhiều compiler tasks đồng thời làm tăng áp lực heap.

Cách an toàn mặc định:

- Mỗi request có một `DiagnosticCollector`, `MemoryFileManager` và map output riêng.
- Gọi `task.call()` trên task của request đó; không chia sẻ cùng một `CompilationTask` cho nhiều thread.
- Sau `SUCCESS`, tạo snapshot riêng rồi cập nhật cache một cách nguyên tử theo version/build ID.
- Khi `FAILED`/cancelled, dọn state của request mà không chạm vào build đã publish.
- Giới hạn concurrency và kích thước input/output; với mã không đáng tin cậy, dùng môi trường xử lý riêng có giới hạn tài nguyên.

**Không có nghĩa mọi đối tượng JavaCompiler đều có thể chia sẻ tùy ý giữa các task song song.** Khả năng thread-safety cần xác minh theo API/implementation đang dùng. Cách tổ chức không chia sẻ mutable file manager là một điểm khởi đầu ít rủi ro hơn.

## 10. Khi nào dùng `SoftReference`, cache hay pool?

Các tối ưu bộ nhớ dễ gây hiểu lầm:

**`SoftReference`:** chỉ là một cơ chế tham chiếu có thể được GC thu hồi; không phải chiến lược cache có thời hạn/dung lượng chắc chắn. Tránh dùng nó để đại diện cho “bản build hiện hành” cần luôn có khi caller dùng.

**Reuse ByteArrayOutputStream:** có thể giảm cấp phát nếu hiểu chính xác cách tái sử dụng và reset, nhưng buffer có thể giữ lại mảng lớn, gây chiếm heap sau tác vụ lớn. Không tái sử dụng bộ đệm của hai request đồng thời.

**Cache classfile:** hữu ích khi cùng nguồn, cùng compiler options và dependencies không đổi. Khóa cache phải xét đủ điều kiện ảnh hưởng kết quả (source, version, compiler, classpath/module path, processor, options...), không chỉ tên lớp.

**Pool file manager:** có thể giảm chi phí trong workload đặc thù, nhưng phải quản lý ownership, state, close, invalidation và concurrency. Đừng tối ưu sớm trước khi có số đo. Một manager riêng mỗi lượt thường dễ bảo đảm đúng hơn.

Cần nhớ `byte[]` là mutable, vì vậy map chỉ đọc chưa bảo đảm nội dung classfile không bị thay đổi. Khi chia sẻ kết quả cho bên không tin cậy, dùng defensive copy hoặc cấu trúc bảo vệ quyền sở hữu dữ liệu.

## 11. Tối ưu chẩn đoán và kiểm thử vòng đời

Để bảo đảm code không chỉ “đúng ở ví dụ thành công”, nên có các bài test sau:

| Trường hợp thử | Kỳ vọng |
| --- | --- |
| Một nguồn Java hợp lệ, một lớp | `SUCCESS`; đúng một classfile có byte không rỗng |
| Nguồn có phương thức trả sai kiểu | `COMPILE_FAILED`, có diagnostic ERROR; public output trống |
| Hai nguồn, một lỗi giữa quá trình | Không publish **bất kỳ** output nào của lượt lỗi |
| Compiler API không có implementation | Trả `UNAVAILABLE`; không gọi `getTask` |
| File manager ném exception khi ghi | Trả lỗi hạ tầng; resource được đóng trong `finally` |
| Cùng tên lớp, hai lượt nối tiếp | Không nhiễm classfile của lượt trước sang lượt sau |
| Hai request chạy đồng thời | Output/diagnostics được tách riêng; không có cross-talk |
| Compiler tạo inner/nested class | Map output chứa đủ classfile mà compiler sinh |
| Callback lỗi trong lúc snapshot | Không publish nửa kết quả; trạng thái nhất quán |

Một chiến lược test tốt dùng instrumentation trong file manager để ghi nhận số lần `openOutputStream`, `close` và số classfile; các số liệu ấy không cần công khai trong API production nhưng giúp phát hiện rò state.

Khi test lỗi biên dịch, **đừng khẳng định bắt buộc có classfile dở**: thứ tự compilation không được bảo đảm giống hệt giữa các bản JDK. Chỉ khẳng định output public rỗng khi `task.call()` không thành công.

### Kiểm tra bằng lệnh gì?

Tệp ví dụ trên là chương trình độc lập. Chạy:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryLifecycleDemo.java
java InMemoryLifecycleDemo
~~~

Sau đó thử đổi `invalid` thành một nguồn hợp lệ khác và quan sát `bad` trở thành `true`. Nếu muốn xem chi tiết lỗi, in từng `Diagnostic` trong phương thức `compile` hoặc trả danh sách diagnostic có cấu trúc trong `BuildResult`. Không cần chạy hay nạp các classfile RAM vào JVM chỉ để kiểm tra trạng thái compiler.

Nếu bạn muốn **nạp bytecode đã thành công**, đó là công việc tiếp theo của một `ClassLoader` phù hợp. Classloader nên chỉ nhận các bytes sau SUCCESS và chỉ khi nguồn được tin cậy. **Không tự động load/execute class bytes từ người dùng không đáng tin** chỉ vì compile đã thành công.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Tại sao nguy hiểm | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng một map output static cho mọi lượt | Dữ liệu trộn giữa nhiều build | Map riêng theo attempt |
| Trả bytes ngay trong `getJavaFileForOutput` | File chưa được compiler ghi xong | Snapshot sau khi task hoàn tất và thành công |
| Trả mọi bytes khi `task.call() == false` | Output từng phần có thể không nhất quán | Không publish output thất bại |
| Chỉ gọi `ByteArrayOutputStream.close()` | Không đồng nghĩa buffer đã được giải phóng | Thả tham chiếu, giới hạn cache, close manager |
| Không đóng file manager | Có thể giữ file handle/cache/bộ đệm | `try-with-resources` và cleanup trong `finally` |
| Gọi `close()` trước `task.call()` | Compiler vẫn cần file manager | Giữ manager sống suốt task |
| Coi mọi exception là lỗi source | Che lỗi I/O, option, runtime | Phân loại riêng compile failure và infrastructure failure |
| Giữ diagnostic objects và file manager lâu dài | Dễ giữ lại object graph/tài nguyên | Copy các trường diagnostic cần thiết |
| Dùng chung manager giữa nhiều thread | Có nguy cơ race và state nhiễm lẫn | Isolation theo request hoặc synchronization có kiểm chứng |
| `Map.copyOf` rồi tin byte arrays bất biến | `byte[]` vẫn có thể sửa | Defensive copy/wrapper khi trao quyền |
| Publish cache từng class | Reader thấy build chưa hoàn tất | Publish cả snapshot theo version một lần |
| Mặc định compiler luôn có | Runtime tối giản có thể trả null | Kiểm tra `ToolProvider` trước |

## 13. Bài thực hành củng cố

**Bài 1 — Thành công và thất bại.** Chạy `InMemoryLifecycleDemo.java`, giải thích vì sao `okClasses=1` còn `badClasses=0`. Khẳng định output trống ở lượt lỗi là **chính sách của wrapper**, không phải bảo đảm compiler không ghi bytes.

**Bài 2 — In diagnostic.** Thay `boolean hasErrors` bằng một danh sách giá trị chẩn đoán gồm `kind`, `line`, `column`, `message`. Sao chép dữ liệu cần thiết ra kết quả, không giữ file manager sống.

**Bài 3 — Nhiều classfile.** Thêm một inner class có tên tường minh vào `demo.Generated`. Dự đoán map sẽ có thêm classfile nào và vì sao một source không tương đương một output class.

**Bài 4 — Tái sử dụng sai state.** Cố tình chuyển map output từ cấp instance `MemoryFileManager` sang static, rồi gọi hai lượt với cùng tên `demo.Generated`. Phân tích nguy cơ cache cũ và cách cô lập.

**Bài 5 — I/O exception.** Thiết kế một file manager thử nghiệm ném `IOException` khi tạo output. Phân biệt exception ấy với kết quả `task.call() == false` do nguồn sai, và kiểm tra `close` vẫn được gọi.

**Bài 6 — Publish nguyên tử.** Giả sử service có bản build A đang dùng và bắt đầu build B. Hãy thiết kế `workingBuild` và `committedBuild` để lỗi của B không làm hỏng A.

**Bài 7 — Concurrency.** Hai request compile cùng class name nhưng nội dung khác. Xác định những object bắt buộc tách riêng và cách tránh một request trả bytes của request khác.

### Câu hỏi tự đánh giá

1. **Vai trò của `MemoryFileManager` là gì?** — Chặn yêu cầu tạo class output và cung cấp `JavaFileObject` ghi vào RAM, còn các thao tác khác ủy quyền cho file manager chuẩn.
2. **Khi nào được snapshot class bytes?** — Sau khi task hoàn tất **thành công** và output đã sẵn sàng.
3. **`task.call() == false` có bảo đảm chưa ghi một classfile nào không?** — Không; chỉ biết toàn lượt không thành công.
4. **Vì sao cần `try-with-resources`?** — Đảm bảo đóng file manager trên cả đường thành công và exception.
5. **`ByteArrayOutputStream.close()` có tự giải phóng toàn bộ RAM ngay không?** — Không; cần bỏ tham chiếu để dữ liệu có thể được thu hồi.
6. **Có nên giữ cùng diagnostic collector cho nhiều build không?** — Không nếu không có cơ chế reset/ownership rõ; mặc định tạo mới mỗi lượt.
7. **`Map.copyOf` có làm byte array bất biến không?** — Không; map không cho sửa cấu trúc, nhưng `byte[]` bên trong vẫn mutable.
8. **Nếu thiếu compiler, loại trạng thái nào?** — `UNAVAILABLE`, khác `COMPILE_FAILED`.
9. **Một file Java có thể sinh nhiều classfile không?** — Có, ví dụ nested/anonymous classes.
10. **Vì sao phải publish cache như một snapshot?** — Tránh người dùng khác thấy build mới chỉ hoàn thành một phần.

**Tổng kết:** Với biên dịch trong bộ nhớ, phần khó nhất không phải tạo `ByteArrayOutputStream` mà là **quản lý ownership và các đường thoát**. Tạo file manager và bộ đệm riêng mỗi lượt; để compiler hoàn tất trước khi đọc bytes; chỉ sao chép/publish output khi thành công; giữ diagnostic hữu ích khi thất bại; đóng tài nguyên trong mọi trường hợp; và không để trạng thái của build lỗi rò sang build tốt hoặc request khác.