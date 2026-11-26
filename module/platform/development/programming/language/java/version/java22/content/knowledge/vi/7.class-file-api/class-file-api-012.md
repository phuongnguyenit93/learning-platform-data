# Đối chiếu API chính thức với ví dụ preview Java 22 và thư viện bytecode đang sử dụng

## Bối cảnh và trạng thái hiện tại

Java 22 giới thiệu **Class-File API** dưới dạng preview qua JEP 457. API tiếp tục được điều chỉnh ở JDK 23 qua JEP 466 và trở thành API chính thức từ JDK 24 qua JEP 484. Tại ngày 25/11/2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất; Class-File API vẫn là API ổn định trong package `java.lang.classfile`, thuộc module `java.base`.

| JDK | JEP | Trạng thái | Cách sử dụng |
|---|---|---|---|
| 22 | [JEP 457](https://openjdk.org/jeps/457) | Preview lần đầu | Cần bật preview khi biên dịch và chạy. |
| 23 | [JEP 466](https://openjdk.org/jeps/466) | Preview lần thứ hai | Cần bật preview của đúng JDK 23; API có thể tiếp tục thay đổi. |
| 24 | [JEP 484](https://openjdk.org/jeps/484) | Final, chính thức | Không cần `--enable-preview`. |
| 25–27 | Cùng API final | Stable | Dùng API trong `java.lang.classfile`; JDK 27 hỗ trợ class-file version 71. |

Vì thế, mã nguồn preview từ JDK 22 chỉ nên được xem là tư liệu lịch sử hoặc đầu vào để chuyển đổi. Khi viết công cụ mới, hãy dùng API final của JDK 24 trở lên. Không dùng package nội bộ như `jdk.internal.org.objectweb.asm`: đó không phải API Java SE được hỗ trợ cho ứng dụng.

## Class-File API giải quyết vấn đề gì?

File `.class` lưu cấu trúc mà JVM nạp và thực thi: class, field, method, constant pool, attribute, instruction, exception table và các metadata liên quan. Các công cụ như compiler, framework proxy, agent, bộ instrument, bộ kiểm tra bảo mật và công cụ phân tích dependency thường phải đọc hoặc biến đổi cấu trúc này.

Trước API chuẩn của JDK, nhiều dự án dùng thư viện như ASM, Byte Buddy hoặc Javassist. JDK cũng có bản sao nội bộ của ASM để phục vụ chính nền tảng, nhưng mã ứng dụng không nên phụ thuộc vào bản sao nội bộ đó.

Class-File API đưa vào Java SE một mô hình chuẩn gồm:

- **Model và Element:** biểu diễn bất biến của class file, method, field, attribute và instruction.
- **Builder:** tạo class, method, code và các thành phần của class file.
- **Transform:** đọc một model, giữ lại, bỏ hoặc thay thế các element rồi tạo class file mới.
- **Symbolic descriptor:** dùng `ClassDesc`, `MethodTypeDesc` và các kiểu trong `java.lang.constant` thay cho nhiều chuỗi tên hoặc descriptor thô.

API hỗ trợ cả truy cập theo cấu trúc cây và duyệt tuần tự. Model được parse lazy; phần dữ liệu chỉ được xử lý khi cần truy cập. Điều này hữu ích cho công cụ chỉ cần đọc một số thành phần của class file.

## Khác biệt giữa preview Java 22 và API final

### Cách bật preview

Khi thử JEP 457 trên JDK 22, phải biên dịch và chạy với preview của đúng phiên bản:

```shell
javac --enable-preview --release 22 PreviewClassTool.java
java --enable-preview PreviewClassTool
```

JDK 23 có vòng preview riêng. Mã nguồn preview cần được kiểm tra và biên dịch lại với JDK 23; không nên dùng class file đã biên dịch ở preview JDK 22 như một binary ổn định cho các JDK tiếp theo.

Với API final từ JDK 24, không cần cờ preview:

```shell
javac --release 24 ClassTool.java
java ClassTool
```

Nếu build bằng JDK 27 nhưng cần target JDK 24, có thể dùng `--release 24` khi biên dịch. Việc chọn target class-file version không tự làm cho các API mới hơn tương thích với runtime cũ; mã nguồn vẫn phải giới hạn ở API có trong JDK mục tiêu.

### Thay đổi tên và cách gọi API

Các ý tưởng chính của API được giữ lại qua các vòng preview: parse thành model, build qua builder và transform qua các element. Tuy nhiên, preview không đảm bảo source compatibility. JEP 466 tiếp tục điều chỉnh thiết kế và JEP 484 chốt API final; cần đọc lại chữ ký trong Java SE API thay vì chỉ đổi cờ biên dịch.

Một thay đổi dễ nhận ra ở API final là thao tác biến đổi toàn bộ class có tên `transformClass(...)`. Tên này phân biệt rõ với các phương thức transform ở builder và với `ClassFileBuilder.transform(...)` tổng quát hơn.

Ví dụ chuyển lời gọi transform ở preview JDK 22 sang API final:

```java
// JDK 22 preview — minh họa mã của vòng preview đầu tiên
byte[] updated = classFile.transform(model, transform);

// JDK 24+ final
byte[] updated = classFile.transformClass(model, transform);
```

Đây là một khác biệt tên phương thức có thể thấy trực tiếp trong API final. Không nên suy rộng rằng chỉ cần đổi `transform` thành `transformClass` là mọi mã preview đã được chuyển xong; hãy kiểm tra cả kiểu tham số, option, element và builder method trong JDK mục tiêu.

Một khác biệt lớn hơn nằm ở package phụ trợ. Preview JDK 22/23 có package `java.lang.classfile.components` với các tiện ích như `ClassRemapper`, `ClassPrinter`, `CodeStackTracker` và `CodeRelabeler`. Package preview này không nằm trong danh sách package của Class-File API final từ JDK 24. Vì vậy, không giữ các import `java.lang.classfile.components.*` rồi giả định chúng là API stable. Với nhu cầu remap hoặc instrument, hãy viết `ClassTransform`/`CodeTransform` trên API final hoặc tiếp tục dùng thư viện bytecode có abstraction tương ứng; với việc in cấu trúc class, có thể dùng `javap -c -v` hoặc xây công cụ đọc model riêng.

| Nhu cầu | Cách viết trong API final từ JDK 24 |
|---|---|
| Tạo context | `ClassFile.of()` |
| Parse byte array | `classFile.parse(bytes)` |
| Parse từ đường dẫn | `classFile.parse(path)` |
| Tạo class file | `classFile.build(classDesc, classBuilder -> ...)` |
| Biến đổi class | `classFile.transformClass(model, classTransform)` |
| Kiểm tra class file | `classFile.verify(bytes)` hoặc `classFile.verify(model)` |

### Ví dụ parse và transform theo API final

Ví dụ sau bỏ các method có tên bắt đầu bằng `debug_`, sau đó kiểm tra class file mới:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ClassTool {
    public static void main(String[] args) throws IOException {
        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);

        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(input);

        ClassTransform removeDebugMethods = ClassTransform.dropping(
                element -> element instanceof MethodModel method
                        && method.methodName().stringValue().startsWith("debug_"));

        byte[] transformed = classFile.transformClass(model, removeDebugMethods);
        List<VerifyError> errors = classFile.verify(transformed);

        if (!errors.isEmpty()) {
            throw new IllegalArgumentException("Class file không hợp lệ: " + errors);
        }

        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.write(output, transformed);
    }
}
```

Biên dịch và chạy bằng JDK 24 trở lên:

```shell
javac --release 24 ClassTool.java
java ClassTool input/Example.class output/Example.class
```

`ClassTransform.dropping(...)` giúp diễn đạt quy tắc loại bỏ element. Nếu không muốn thay đổi một element trong transform tự viết, phải chuyển tiếp element đó bằng `builder.with(element)`; không đưa element vào builder có nghĩa là bỏ nó. Sau khi biến đổi, `verify` kiểm tra các lỗi cấu trúc mà verifier của API phát hiện được, nhưng không chứng minh logic ứng dụng vẫn đúng. Việc xóa method có thể phá vỡ lời gọi từ class khác, reflection, framework hoặc serialization.

### Quy trình chuyển mã preview sang API final

1. **Xác định nơi dùng preview.** Tìm import `java.lang.classfile`, các lệnh build/transform và mọi tùy chọn preview trong cấu hình biên dịch.
2. **Chuyển sang JDK 24+ để biên dịch.** Bỏ cờ preview sau khi đã sửa source theo API final.
3. **Đối chiếu tên và chữ ký.** Đặc biệt kiểm tra transform API, builder method, option và các kiểu element đã thay đổi qua preview.
4. **Biên dịch lại toàn bộ công cụ.** Không tái sử dụng binary preview JDK 22 hoặc 23 như thể đó là binary stable.
5. **Kiểm tra class file đầu vào.** JDK 27 hỗ trợ class-file version đến Java 27; một runtime cũ hơn không tự hiểu class-file version mới hơn chỉ vì chương trình gọi API chuẩn.
6. **Kiểm tra kết quả sau transform.** Dùng `ClassFile.verify`, tải class trong môi trường thử nghiệm, chạy test và kiểm tra các attribute/metadata mà công cụ cần giữ.

## So sánh Class-File API với các thư viện bytecode phổ biến

Không có danh sách dependency của một dự án cụ thể trong metadata của bài này. Vì vậy, phần dưới so sánh các lựa chọn phổ biến trên hệ sinh thái Java; không khẳng định dự án đang dùng thư viện nào.

### Tổng quan

| Tiêu chí | Class-File API | ASM | Byte Buddy | Javassist |
|---|---|---|---|---|
| Nơi cung cấp | Java SE, package `java.lang.classfile` trong `java.base`. | Thư viện độc lập của OW2. | Thư viện độc lập, xây trên ASM. | Thư viện độc lập. |
| Mức trừu tượng | Mô hình class-file, element, builder và transform. | Thấp, gần với instruction và cấu trúc class file. | Cao, tập trung tạo kiểu, proxy, Advice và instrument. | Có API source-level và bytecode-level. |
| Đọc class file | `ClassModel`, accessor và element traversal. | `ClassReader`, visitor hoặc tree API. | Qua các abstraction của Byte Buddy và ASM bên dưới. | `ClassPool`, `CtClass`, `CtMethod` và `javassist.bytecode`. |
| Sinh bytecode | `ClassBuilder`, `MethodBuilder`, `CodeBuilder`. | `ClassWriter`, `MethodVisitor`, `Label`. | API mô tả type, method, matcher, delegation và Advice. | Có thể chèn mã Java dạng chuỗi hoặc thao tác instruction trực tiếp. |
| Biến đổi | `ClassTransform`, `MethodTransform`, `CodeTransform`. | Visitor, adapter và tree node. | `AgentBuilder`, `redefine`, `rebase`, `Advice` và các transformer. | Sửa `CtClass`, `CtMethod`, bytecode attribute. |
| Phụ thuộc ngoài | Không cần dependency bytecode ngoài JDK. | Cần dependency ASM tương ứng. | Cần Byte Buddy; ASM là thành phần nền tảng. | Cần dependency Javassist. |
| Điểm mạnh | API chuẩn của JDK, mô hình rõ, theo kịp class-file format khi nâng JDK. | Kiểm soát instruction chi tiết, hiệu năng tốt, hệ sinh thái trưởng thành. | Tạo class và instrument ở mức cao, phù hợp agent/proxy. | Dễ bắt đầu với thao tác ở mức source-like, vẫn có API bytecode thấp. |
| Đổi lại | Yêu cầu JDK có API này; code thấp cấp vẫn cần hiểu class-file format và verifier. | Phải hiểu bytecode/stack/frame nhiều hơn; cập nhật dependency khi cần hỗ trợ class-file version mới. | Ít phải viết instruction trực tiếp, nhưng cần hiểu abstraction và quản lý dependency ASM. | Source snippet cần resolve type và biên dịch nội bộ; thao tác phức tạp có thể phải xuống API bytecode. |

### ASM: khi cần kiểm soát thấp cấp

ASM là framework phân tích và thao tác bytecode tập trung vào hiệu năng. API visitor cho phép xử lý class theo luồng; API tree biểu diễn cấu trúc dưới dạng node để dễ duyệt và biến đổi.

Ví dụ khung đọc class bằng visitor (đã lược phần khai báo phương thức `main`):

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public class AsmReadMethods {
  public static void main(String[] args) throws IOException {
    byte[] classBytes = Files.readAllBytes(Path.of(args[0]));
ClassReader reader = new ClassReader(classBytes);

reader.accept(new ClassVisitor(Opcodes.ASM9) {
    @Override
    public MethodVisitor visitMethod(
            int access,
            String name,
            String descriptor,
            String signature,
            String[] exceptions) {

        System.out.println(name + descriptor);
        return super.visitMethod(access, name, descriptor, signature, exceptions);
    }
}, 0);
  }
}
```

Khi sinh hoặc sửa class, thường kết hợp `ClassWriter`, `MethodVisitor`, `Label` và các instruction visitor. ASM phù hợp khi cần điều khiển chính xác thứ tự instruction, frame, label, exception table hoặc khi một framework hiện tại đã xây trên ASM.

ASM vẫn là thư viện được duy trì tích cực. Theo trang phát hành chính thức, ASM 9.11.1 được phát hành ngày 17/10/2026; ASM 9.11 bổ sung hằng `Opcodes.V28` và ghi rõ chưa hỗ trợ preview features. Vì vậy, cần chọn phiên bản ASM dựa trên class-file version và loại bytecode cần xử lý, không chỉ dựa vào phiên bản JDK cài trên máy.

### Byte Buddy: khi cần tạo kiểu và instrument ở mức cao

Byte Buddy giúp tạo class runtime, tạo proxy, sửa class hoặc thêm logic vào method mà không cần viết từng opcode. Các API như `Advice`, method matcher, delegation và agent builder cho phép mô tả ý định ở mức gần với cấu trúc Java.

Ví dụ minh họa gắn Advice vào method `run` (giả sử `Target` là class cần instrument):

```java
import net.bytebuddy.ByteBuddy;
import net.bytebuddy.asm.Advice;

import static net.bytebuddy.matcher.ElementMatchers.named;

new ByteBuddy()
        .redefine(Target.class)
        .visit(Advice.to(TraceAdvice.class).on(named("run")))
        .make();
```

`TraceAdvice` là class do ứng dụng định nghĩa với method được đánh dấu `@Advice.OnMethodEnter` hoặc `@Advice.OnMethodExit`. Đoạn ví dụ chỉ tạo ra một `DynamicType.Unloaded`; ứng dụng còn phải lưu byte array hoặc nạp class bằng cơ chế phù hợp.

Byte Buddy tiếp tục sử dụng ASM làm nền tảng bytecode. Release notes của Byte Buddy 1.18.16 ghi nhận cập nhật ASM lên 9.11.1 và cập nhật cầu nối ASM với Class-File API; bản 1.18.17 được phát hành ngày 01/11/2026. Điều đó cho thấy Class-File API có thể cùng tồn tại và tích hợp với thư viện cấp cao, thay vì buộc mọi ứng dụng phải bỏ Byte Buddy.

Chọn Byte Buddy khi bài toán là proxy, mocking, runtime code generation, agent hoặc Advice. Nếu chỉ cần đọc một class file hay thay một attribute nhỏ, Class-File API hoặc ASM có thể trực tiếp và ít tầng abstraction hơn.

### Javassist: khi muốn sửa class bằng mã gần với Java source

Javassist cung cấp hai cấp API. `CtClass` và `CtMethod` cho phép thao tác gần với cấu trúc Java; `javassist.bytecode` cung cấp cách làm việc thấp cấp hơn với constant pool và instruction.

Ví dụ chèn lệnh trước method:

```java
import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtMethod;

ClassPool pool = ClassPool.getDefault();
CtClass type = pool.get("com.example.Target");
CtMethod method = type.getDeclaredMethod("run");

method.insertBefore("{ System.out.println(\"enter run\"); }");

byte[] transformed = type.toBytecode();
type.detach();
```

API source-level giúp giảm lượng mã bytecode phải viết, nhưng đoạn source chèn vào vẫn phải biên dịch được và resolve được kiểu. Với class loader, module hoặc môi trường runtime phức tạp, cần kiểm tra cách Javassist định nghĩa class và quyền truy cập của loader.

Javassist vẫn được phát hành; phiên bản 3.33.0-GA được công bố ngày 23/08/2026. Vì vậy không nên gọi thư viện này là legacy chỉ vì JDK đã có API chuẩn. Hãy đánh giá theo nhu cầu, mức bảo trì, tương thích class-file version và cách tích hợp hiện tại.

## Class-File API có thay thế ASM, Byte Buddy hoặc Javassist không?

Không có một lựa chọn duy nhất phù hợp cho mọi tầng công việc:

- Class-File API là lựa chọn tự nhiên khi công cụ cần API Java SE, đọc/ghi/transform class file trực tiếp và chạy trên JDK 24 trở lên.
- ASM vẫn hữu ích khi cần API instruction-level, hiệu năng, visitor/tree ecosystem hoặc phải duy trì tương thích với framework đang dùng ASM.
- Byte Buddy phù hợp hơn khi cần tạo proxy, subclass, Advice, mocking hoặc agent ở mức abstraction cao.
- Javassist hữu ích khi muốn chỉnh sửa class bằng source-like snippets hoặc cần API bytecode cấp thấp của nó.

Class-File API cũng không tự động thay thế mọi tính năng runtime của các thư viện này. Nó đọc, tạo và biến đổi byte array của class file; việc định nghĩa class, cài agent, instrument class đang chạy, quản lý class loader hoặc điều phối lifecycle vẫn thuộc trách nhiệm của các API/runtime khác.

## Chiến lược lựa chọn và chuyển đổi trong dự án

Trước khi thay thư viện, hãy lập danh sách tác vụ bytecode thực sự cần:

1. Đọc metadata hoặc kiểm tra dependency.
2. Tạo class mới hoặc method mới.
3. Chèn instrumentation vào method đang có.
4. Tạo proxy, subclass, mock hoặc Advice.
5. Hỗ trợ class-file version mới và các attribute đặc thù của compiler/framework.
6. Tích hợp với Java agent, class loader hoặc build plugin.

Sau đó chọn theo phạm vi:

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Chỉ parse, inspect hoặc transform class file bằng API JDK | Thử `java.lang.classfile`. |
| Sửa opcode, label, stack frame hoặc exception table chi tiết | So sánh Class-File API và ASM bằng một prototype có test. |
| Tạo proxy, mock, runtime subclass hoặc method Advice | Giữ abstraction của Byte Buddy nếu đang đáp ứng tốt. |
| Chèn đoạn mã Java nhỏ vào method | Cân nhắc Javassist; đánh giá thêm cách resolve type và class loader. |
| Công cụ phải chạy trên JDK dưới 24 | Dùng thư viện ngoài tương thích với runtime mục tiêu; Class-File API không có trong các JDK đó. |

Khi chuyển từ thư viện ngoài sang Class-File API, nên chuyển từng tác vụ độc lập và đo hiệu năng, kích thước output, khả năng giữ attribute, stack-map generation, class loading và hành vi agent. Không nên thay toàn bộ dependency chỉ vì API mới đã trở thành một phần của JDK.

## Ghi nhớ

- JEP 457 trong JDK 22 và JEP 466 trong JDK 23 là các bản preview; JEP 484 đưa Class-File API thành API final từ JDK 24.
- Preview cần `--enable-preview` và phải được kiểm tra theo đúng JDK preview; API final từ JDK 24 không cần cờ này.
- Một khác biệt rõ ở API final là `ClassFile.transformClass(...)`; không giả định mã preview sẽ biên dịch nguyên trạng.
- JDK 27 có `java.lang.classfile` stable và hỗ trợ class-file version Java 27; runtime cũ không tự hỗ trợ định dạng class mới hơn.
- ASM, Byte Buddy và Javassist vẫn là các lựa chọn được duy trì. Class-File API là một API chuẩn mới trong hệ sinh thái, không phải tuyên bố rằng các thư viện bytecode bên ngoài đã obsolete.
- Chọn công cụ theo cấp abstraction và yêu cầu runtime; kiểm thử class sau khi biến đổi và kiểm tra cả metadata mà framework cần.

## Tài liệu tham khảo

### JEP và tài liệu JDK

- [JEP 457 — Class-File API (Preview, JDK 22)](https://openjdk.org/jeps/457)
- [JEP 466 — Class-File API (Second Preview, JDK 23)](https://openjdk.org/jeps/466)
- [JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484)
- [Java SE 22 Preview API — `ClassFile.transform`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java SE 22 Preview API — `java.lang.classfile.components`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/classfile/components/package-summary.html)
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Java SE 27 API — Package `java.lang.classfile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java SE 27 API — `ClassFile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)

### Thư viện bytecode

- [ASM — Official Project Site](https://asm.ow2.io/)
- [ASM — Versions and Release Notes](https://asm.ow2.io/versions.html)
- [Byte Buddy — Official Project Site](https://bytebuddy.net/)
- [Byte Buddy — Release Notes](https://github.com/raphw/byte-buddy/blob/master/release-notes.md)
- [Javassist — Official Project Site](https://www.javassist.org/)
- [Javassist — Releases](https://github.com/jboss-javassist/javassist/releases)
