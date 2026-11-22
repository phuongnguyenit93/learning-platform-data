# VerifyError, lỗi nạp lớp và lỗi biến đổi bytecode

## 1. Tại sao những lỗi này thường xuất hiện khi nâng JDK?

Khi chuyển ứng dụng từ JDK cũ sang JDK mới, source Java có thể biên dịch thành công nhưng chương trình lại không khởi động được, hoặc chỉ lỗi khi gọi một chức năng cụ thể. Các thông báo như sau thường bị gom chung thành “lỗi không tương thích Java”:

~~~text
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.NoClassDefFoundError: com/example/api/Order
java.lang.NoSuchMethodError: 'void com.example.api.Order.setId(...)'
java.lang.UnsupportedClassVersionError: ... class file version 65.0
java.lang.ClassFormatError: Invalid constant pool index ...
java.lang.reflect.InaccessibleObjectException: ...
~~~

Những lỗi đó **không thuộc cùng một nguyên nhân**. Có lỗi bắt nguồn từ bytecode không hợp lệ; có lỗi đến từ classpath và class loader; có lỗi do thay đổi API giữa các JAR; có lỗi do Java Module System; và có lỗi xuất hiện sau khi một agent, mocking framework hoặc thư viện instrumentation biến đổi class file.

Ví dụ tình huống:

- Ứng dụng compile trên JDK 21 và dùng class-file major version 65.
- Một coverage agent chứa ASM cũ chưa đọc được class file mới, nên công cụ báo `Unsupported class file major version 65`.
- Một agent khác đọc được bytecode nhưng chèn lời gọi vào method mà không cập nhật stack map frames, khiến JVM báo `VerifyError`.
- Một JAR bị shading làm mất dependency, dẫn đến `NoClassDefFoundError` khi tính năng được gọi lần đầu.
- Một consumer được compile với library v1 nhưng chạy với v2 thay đổi method descriptor, dẫn đến `NoSuchMethodError`.

Nếu sửa bằng cách thêm tùy tiện JVM flags, đổi source level hoặc bỏ qua mọi exception, quá trình migration có thể che lỗi tạm thời nhưng mất tính an toàn và khả năng tái lập.

Mục tiêu của bài học **“VerifyError, lỗi nạp lớp và lỗi biến đổi bytecode”** trong chương **Chẩn đoán lỗi** của **Java Advance Compatibility Migration** là giúp nhận diện đúng tầng lỗi, thu thập bằng chứng, xác định tác nhân và chọn biện pháp sửa tương ứng.

## 2. Kết quả cần đạt

Sau bài học, người đọc cần có khả năng:

1. Giải thích các giai đoạn loading, linking, verification, preparation, resolution và initialization của JVM.
2. Phân biệt `VerifyError` với `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError` và những `LinkageError` khác.
3. Xác định lúc nào nguồn lỗi nhiều khả năng là Java source/compiler, JAR deployment, custom class loader hoặc bytecode transformer.
4. Hiểu local variables, operand stack, method descriptors, stack map frames và control-flow merge ở mức đủ để điều tra.
5. Sử dụng `java -version`, `jar`, `javap`, `jdeps`, logging class loading và dependency graph để tìm class bytes thật đang chạy.
6. Điều tra ASM, Byte Buddy, JaCoCo, Mockito, APM agents, generated code và JVMTI/instrumentation khi nâng JDK.
7. Thiết kế reproduction, test matrix và tiêu chí xử lý regression mà không tắt bytecode verification.

## 3. JVM không chỉ “mở file .class rồi chạy”

Một biểu diễn khái quát:

~~~text
Java source / generated source / transformed bytecode
                        |
                        v
             .class / JAR / module
                        |
                        v
                Class loading
                        |
                        v
              Linking / Verification
                        |
                   Preparation
                        |
                 Resolution (*)
                        |
                        v
               Initialization
                        |
                        v
                 Execution
~~~

`(*)` Một số resolution có thể được thực hiện lười (*lazy*) trong quá trình thực thi; mô hình này không có nghĩa mọi tham chiếu được resolve hết trước khi method đầu tiên chạy. Thời điểm kiểm tra và resolution có những giới hạn được JVM Specification cho phép.

### 3.1. Loading

JVM tìm binary representation của class, thường là bytecode trong JAR, directory, module image, hoặc bytes do một class loader/generator cung cấp. **Tên class và class loader** cùng tham gia vào danh tính runtime của type.

### 3.2. Linking

Liên kết gồm verification, preparation và resolution. JVM cần bảo đảm class file, bytecode và tham chiếu thích hợp với những ràng buộc của runtime. Nếu bytecode không thỏa luật verifier, `VerifyError` là một kết quả có thể xuất hiện.

### 3.3. Initialization

JVM thực thi static initializers và gán các giá trị static theo luật class initialization. Một failure ở bước này có thể tạo `ExceptionInInitializerError` hoặc một `Error` gốc, và những lần dùng class sau đó có thể thấy `NoClassDefFoundError: Could not initialize class ...`.

### 3.4. Vì sao stack trace có thể xuất hiện muộn?

Class không nhất thiết được nạp/verify khi JVM vừa startup. Ví dụ một payment adapter chỉ được nạp khi request đầu tiên đi qua đường thanh toán. Vì thế application health check pass không chứng minh mọi class trong tất cả JAR đều nạp và liên kết thành công.

## 4. Các loại lỗi cần phân biệt trước khi điều tra

| Lỗi/triệu chứng | Tầng thường thất bại | Câu hỏi đầu tiên |
| --- | --- | --- |
| `ClassNotFoundException` | Lookup tên class qua API | Class loader đang tìm ở đâu? |
| `NoClassDefFoundError` | Runtime không định nghĩa/nạp hoặc class init đã lỗi | Có thiếu JAR hay lỗi initializer trước đó? |
| `ClassFormatError` | Class file malformed | Bytes class file có đúng định dạng không? |
| `UnsupportedClassVersionError` | Class-file format vượt khả năng JVM | JVM đang dùng JDK nào, class major version nào? |
| `VerifyError` | Bytecode không thỏa luật verifier | Operand stack, types, frames hoặc control flow nào không hợp lệ? |
| `NoSuchMethodError` | Method symbolic reference không khớp | Bên gọi compile với API nào, runtime có method nào? |
| `NoSuchFieldError` | Field symbolic reference không khớp | Kiểu/tên field có đổi giữa JAR versions? |
| `IllegalAccessError` | Access khi liên kết | Access modifier hoặc module export có đổi? |
| `AbstractMethodError` | Method invocation không có implementation hợp lệ | Interface/class binary compatibility có phá? |
| `IncompatibleClassChangeError` | Dạng class/interface/method không khớp | Static/instance hay class hierarchy có đổi? |
| `BootstrapMethodError` | Bootstrap của dynamic linkage thất bại | `invokedynamic`/`ConstantDynamic` hoặc bootstrap method có lỗi? |
| `InaccessibleObjectException` | Reflection bị hạn chế | Module nào không `opens` package? |
| `Unsupported class file major version` từ ASM/agent | Bytecode parser bên thứ ba | Tool/embedded ASM nào chưa hỗ trợ version mới? |
| `UnsatisfiedLinkError` | Native/JNI loading/binding | Native binary/symbol/OS/ABI có đúng? |

Đây là bản đồ chẩn đoán, không phải phép suy luận tuyệt đối: một lỗi ban đầu có thể được bọc hoặc khiến các lỗi sau xuất hiện. **Luôn giữ thông điệp đầu tiên cùng các `Caused by` và class name liên quan.**

## 5. Quan hệ kế thừa của một số lỗi liên quan

~~~text
java.lang.Throwable
├── java.lang.Error
│   ├── java.lang.LinkageError
│   │   ├── VerifyError
│   │   ├── ClassFormatError
│   │   │   └── UnsupportedClassVersionError
│   │   ├── NoClassDefFoundError
│   │   ├── ClassCircularityError
│   │   ├── BootstrapMethodError
│   │   ├── UnsatisfiedLinkError
│   │   └── IncompatibleClassChangeError
│   │       ├── NoSuchMethodError
│   │       ├── NoSuchFieldError
│   │       ├── AbstractMethodError
│   │       └── IllegalAccessError
│   └── ExceptionInInitializerError
└── java.lang.Exception
    ├── ClassNotFoundException
    └── RuntimeException
        ├── ClassCastException
        └── java.lang.reflect.InaccessibleObjectException
~~~

Sơ đồ chỉ hiển thị những nhánh hữu ích cho bài học. Các tên subtype trong nhóm `LinkageError` là **Java Errors** và thường không phải loại lỗi nên được code nghiệp vụ bắt rộng rồi tiếp tục hoạt động.

Đặc biệt:

- `VerifyError` là một dạng `LinkageError`.
- `NoClassDefFoundError` khác `ClassNotFoundException` cả về hệ phân cấp và con đường lỗi.
- `UnsatisfiedLinkError` vẫn là `LinkageError` nhưng nguyên nhân thường nằm ở native library hoặc binding.
- `InaccessibleObjectException` là runtime exception liên quan reflective access, không phải `VerifyError`.

## 6. `VerifyError` thực sự có nghĩa gì?

`VerifyError` cho biết JVM verifier phát hiện một class file có bytecode không thể thỏa các ràng buộc bắt buộc của Java Virtual Machine Specification.

Một số thông điệp thường gặp:

~~~text
java.lang.VerifyError: Bad type on operand stack
java.lang.VerifyError: Bad local variable type
java.lang.VerifyError: Inconsistent stackmap frames at branch target ...
java.lang.VerifyError: Expecting a stackmap frame at branch target ...
java.lang.VerifyError: Operand stack overflow
java.lang.VerifyError: Illegal type at constant pool entry ...
~~~

Chi tiết văn bản có thể thay đổi theo JDK/vendor và điểm kiểm tra. Điều quan trọng không phải thuộc lòng message, mà là hiểu verifier đang bảo vệ những gì:

- Mọi instruction phải dùng operand types hợp lệ.
- Operand stack không bị underflow/overflow và phải nhất quán theo control flow.
- Local variables có kiểu hợp lệ tại những điểm sử dụng.
- Branch targets phải hợp lệ.
- Method return instructions phải phù hợp declared return type.
- Object initialization và uninitialized references phải tuân thủ luật.
- Stack map frames, khi được yêu cầu, phải mô tả trạng thái kiểu nhất quán.
- Bytecode không thể tạo ra những thao tác bị cấm chỉ bằng cách ghi bytes tùy ý.

Verifier là một cơ chế an toàn của JVM, không phải linter định dạng code. Nó xác minh các ràng buộc ở mức bytecode trước/đúng lúc class được dùng để bảo vệ type safety.

## 7. Bytecode verifier khác Java compiler như thế nào?

Code Java được `javac` sinh ra hợp lệ trong điều kiện bình thường. Tuy nhiên, JVM **không chỉ** nạp code do `javac` chính thức tạo:

- Một bytecode generator có thể tự tạo class.
- ASM/Byte Buddy có thể rewrite instruction stream.
- Agent có thể transform bytes khi class load.
- Framework có thể sinh proxies ở runtime.
- Build plugin có thể instrument classes để đo coverage.
- Obfuscator/shader có thể xử lý class ở post-compile stage.
- Một custom class loader có thể định nghĩa class từ dữ liệu đã giải mã.
- JAR hỏng, output stale hoặc sai version có thể xuất hiện trong deployment.

Vì thế:

~~~text
javac compilation successful
             ≠
all runtime class definitions are verifier-valid
~~~

Đặc biệt, nếu build ban đầu pass nhưng thêm `-javaagent` khiến JVM báo `VerifyError`, cần tập trung vào **bytes trước/sau instrumentation** và phiên bản transformer. Đừng vội sửa business source vốn compile hợp lệ.

## 8. Operand stack: nguồn gốc của “Bad type on operand stack”

Java bytecode là kiến trúc stack-based. Nhiều instructions lấy operands từ stack và đưa kết quả trở lại stack.

Ví dụ method:

~~~java
public static int sum(int a, int b) {
    return a + b;
}
~~~

Một dạng bytecode điển hình được hiển thị bởi `javap -c`:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

Diễn biến stack:

| Instruction | Operand stack sau lệnh |
| --- | --- |
| `iload_0` | `[int a]` |
| `iload_1` | `[int a, int b]` |
| `iadd` | `[int result]` |
| `ireturn` | `[]`; trả về `int` |

Nếu một transformer thay `iadd` bằng instruction yêu cầu reference, ví dụ `invokevirtual` không có receiver phù hợp, verifier có thể phát hiện stack type không đúng.

### 8.1. Stack height và stack type đều quan trọng

Một nhánh bytecode có cùng **độ cao stack** ở hai đường đi chưa chắc hợp lệ nếu kiểu phần tử ở vị trí tương ứng không tương thích với frame dự kiến.

Ví dụ minh họa:

~~~text
Branch A stack: [java.lang.String]
Branch B stack: [int]
Merge target:   expects java.lang.String
~~~

Một nhánh đưa `int` tới nơi cần reference tạo sự không nhất quán. Verifier phải đánh giá luồng dữ liệu theo instruction semantics chứ không chỉ đếm số slot.

### 8.2. Category-1 và category-2 values

`long` và `double` sử dụng hai slots trong local variables/operand stack ở cách mô hình hóa verifier, còn nhiều kiểu khác dùng một slot. Transformer thay method descriptor từ `(I)I` sang `(J)J` nhưng không cập nhật local indexes và stack handling có thể tạo lỗi.

Đây là lý do thay chữ ký Java method hoặc chèn instrumentation vào method có `long`/`double` phải được xử lý qua bytecode library hiểu descriptors, thay vì chỉnh chỉ số bằng cảm tính.

## 9. Local variables, frames và control-flow merge

Một Java method có thể có nhiều nhánh:

~~~java
static Object choose(boolean flag) {
    Object result;
    if (flag) {
        result = "ok";
    } else {
        result = Integer.valueOf(10);
    }
    return result;
}
~~~

Compiler sinh control-flow graph. Tại điểm merge sau `if/else`, verifier phải biết trạng thái kiểu của locals và operand stack. Java source có thể hợp lệ vì hai giá trị đều gán được cho `Object`.

Nếu agent thêm một branch mới nhưng không cập nhật stack map frame ở nơi merge, JVM có thể từ chối class:

~~~text
VerifyError: Inconsistent stackmap frames
VerifyError: Expecting a stackmap frame at branch target ...
~~~

### 9.1. `StackMapTable` là gì?

`StackMapTable` là class-file attribute mô tả những verification type states tại những vị trí quan trọng trong method, phục vụ type checking theo cơ chế verification được quy định.

Nó không phải Java stack trace; đó là metadata **trong class file**. Một số versions/methods có những quy tắc xử lý đặc thù, vì thế không kết luận mọi class file đều phải chứa một attribute tường minh trong mọi trường hợp.

Xem bằng:

~~~bash
javap -v -p -c -classpath build/classes example.Service
~~~

Trong output tìm `StackMapTable`, `Code`, `max_stack`, `max_locals`, exception table và instruction offsets.

### 9.2. Offset thay đổi sau instrumentation

Khi chèn instructions, branch target offsets và exception-handler ranges có thể cần điều chỉnh. Bytecode library tốt có thể quản lý những phần này; transformer tự thao tác mảng bytes mà không hiểu class-file structure có nguy cơ tạo class không hợp lệ.

## 10. `max_stack`, `max_locals` và exception handlers

Phần `Code` của class file mô tả:

- `max_stack`: giới hạn operand stack theo quy tắc class file.
- `max_locals`: số slots local variables cần cho method.
- Dãy bytecode instructions.
- Exception handler table.
- Các attributes như `StackMapTable`, line numbers và local variable metadata.

Một transformer thêm logging với lời gọi helper nhưng không tăng `max_stack` khi cần có thể làm verifier báo lỗi. Thêm local variables mà vượt `max_locals` cũng có thể làm class bị từ chối.

Exception handlers phức tạp hơn vì nhiều control-flow edges dẫn tới catch blocks. Việc chèn instrumentation ở đầu/cuối method phải xét cả exception paths, synchronized regions, constructor initialization và paths đi qua `athrow`.

### 10.1. Constructor có ràng buộc riêng

Trong constructor, reference `this` có trạng thái chưa được khởi tạo đầy đủ trước lời gọi constructor phù hợp (`super(...)` hoặc `this(...)`). Transformer dùng `this` như một object đã được khởi tạo quá sớm có thể làm verifier từ chối class.

Đừng copy cùng instrumentation snippet áp vào mọi method gồm constructor, static initializer và synthetic method mà không xét bytecode rules.

## 11. `ClassFormatError` khác `VerifyError`

Hai lỗi đều có thể xuất hiện khi JVM xử lý class file, nhưng góc kiểm tra khác nhau.

**`ClassFormatError`** thường gợi ý cấu trúc của class file vi phạm format, chẳng hạn constant-pool entry malformed, attribute length sai hoặc một quan hệ cấu trúc không hợp lệ.

**`VerifyError`** thường gợi ý bytecode/verification type state không phù hợp với ràng buộc thực thi, ví dụ instruction đòi `int` nhưng operand stack chứa object reference.

Ví dụ:

~~~text
ClassFormatError: Invalid constant pool index ...
VerifyError: Bad type on operand stack ...
~~~

Đây là phân biệt hướng điều tra, không phải cam kết ranh giới message luôn giống nhau trên mọi JVM: cùng một class file sai có thể được phát hiện tại điểm kiểm tra khác nhau theo specification/implementation.

### 11.1. `UnsupportedClassVersionError` là một nhánh của `ClassFormatError`

Khi class major version mới hơn khả năng JVM hỗ trợ:

~~~text
java.lang.UnsupportedClassVersionError:
  class file version 65.0, this runtime only recognizes ...
~~~

Vấn đề thường không phải stack frames. Cần so compiler target với runtime, ví dụ Java 21 class file major 65 không chạy trực tiếp trên Java 17 JVM có mức tương ứng major 61.

## 12. Class-file major version cần biết

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Với JDK mới hơn, xem JVM Specification/JDK documentation tương ứng thay vì đoán qua số năm.

Kiểm tra class:

~~~bash
javap -verbose -classpath build/classes example.Service
~~~

Tìm:

~~~text
major version: 65
~~~

Hoặc kiểm tra một class trong JAR:

~~~bash
javap -v -classpath app.jar com.example.Service
~~~

Lưu ý `javap` cần được dùng đúng chế độ khi JAR là **multi-release JAR**. Một class ở root có thể có major 52, còn bản `META-INF/versions/21` cùng tên có major 65; muốn chẩn đoán phải chọn effective view theo runtime.

## 13. Vì sao “Unsupported class file major version 65” chưa chắc do JVM?

Cùng ý tưởng “không hiểu class file Java 21” có thể đến từ nhiều công cụ:

~~~text
java.lang.UnsupportedClassVersionError: ...
~~~

thường xuất hiện khi JVM/class loading liên quan class file vượt version được nhận.

Trong khi:

~~~text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
~~~

thường cho thấy **ASM version đang được dùng** chưa hiểu format mới. JVM đích có thể hoàn toàn là Java 21, nhưng một agent/formatter/coverage tool tích hợp ASM cũ vẫn thất bại.

### 13.1. Quy trình phân biệt

1. Xem exception class đầy đủ, không chỉ message.
2. Xem stack trace xuất hiện `java.lang.ClassLoader`, `org.objectweb.asm`, `net.bytebuddy`, `org.jacoco` hay plugin nào.
3. Xác nhận `java -version` của tiến trình lỗi.
4. Xác nhận major version của class mà tool đang đọc.
5. Kiểm tra phiên bản bytecode parser embedded trong tool đó.
6. Chọn version của tool được vendor công bố hỗ trợ class-file/JDK đích.

Không sửa bằng cách thêm `--add-opens` nếu nguyên nhân là ASM parser chưa hiểu version 65; module access và parser format support là hai vấn đề khác.

## 14. `ClassNotFoundException` và `NoClassDefFoundError`

### 14.1. `ClassNotFoundException`

Exception checked thường xảy ra khi code chủ động tra một class theo tên:

~~~java
Class<?> plugin =
        Class.forName("com.example.plugins.JsonProvider");
~~~

Nếu class loader không tìm thấy class đó, có thể ném `ClassNotFoundException`. Cần kiểm tra tên class, deployment JAR, class loader, classpath và module path.

### 14.2. `NoClassDefFoundError`

`NoClassDefFoundError` là một `LinkageError`. Nó có thể xảy ra khi class từng tồn tại trong compile environment nhưng không thể được định nghĩa/tìm ở runtime, hoặc class đã khởi tạo thất bại.

~~~text
java.lang.NoClassDefFoundError:
  com/example/json/JsonProvider
~~~

Kiểm tra JAR đã deploy, dependency transitive bị loại, shading, class loaders và modules.

### 14.3. `NoClassDefFoundError: Could not initialize class`

Ví dụ:

~~~java
public final class CryptoBridge {
    static {
        System.loadLibrary("cryptohelper");
    }
}
~~~

Nếu lần đầu gọi class gặp `UnsatisfiedLinkError` trong static initializer, những lần sau trong cùng JVM có thể báo:

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class example.CryptoBridge
~~~

Không thêm JAR Java bừa bãi để sửa trường hợp này. Tìm **lần đầu class initialization thất bại**; root cause có thể là native library.

## 15. `ExceptionInInitializerError` có thể che stack trace gốc

Một static initializer:

~~~java
final class Settings {
    static final String URL = loadUrl();

    private static String loadUrl() {
        throw new IllegalStateException("missing URL");
    }
}
~~~

Lần đầu dùng `Settings` có thể tạo:

~~~text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException: missing URL
~~~

Những lần sau có thể thấy `NoClassDefFoundError` cho class initialization đã thất bại.

Lưu ý: nếu static initialization ném một đối tượng `Error`, JVM không nhất thiết bọc nó trong `ExceptionInInitializerError`; hãy đọc đúng `Caused by` và timeline.

### 15.1. Restart không phải bằng chứng lỗi đã được sửa

Khởi động JVM mới làm quá trình class initialization bắt đầu lại. Có thể lần đầu sau restart thấy `UnsatisfiedLinkError`, rồi các lần tiếp theo trong cùng process lại thấy `NoClassDefFoundError`. Đó có thể là **một vấn đề** hiển thị qua hai giai đoạn, không phải hai bug khác nhau.

## 16. `NoSuchMethodError` và những lỗi ABI không phải `VerifyError`

Giả sử consumer compile với:

~~~java
// library v1
public final class PriceService {
    public int calculate(int units) {
        return units * 10;
    }
}
~~~

Nhưng runtime triển khai v2:

~~~java
// library v2
public final class PriceService {
    public long calculate(long units) {
        return units * 10;
    }
}
~~~

Caller bytecode v1 vẫn tham chiếu method descriptor `calculate(I)I`. Nếu runtime v2 không còn method ấy, JVM có thể báo `NoSuchMethodError`. Bytecode của caller có thể hoàn toàn hợp lệ về type state; lỗi đến từ symbolic reference resolution.

### 16.1. Method descriptor có cả return type

Sử dụng:

~~~bash
javap -s -p -classpath library.jar example.PriceService
~~~

Các descriptor điển hình:

~~~text
calculate(int): int    -> (I)I
calculate(long): long  -> (J)J
~~~

Đổi method descriptor, static/instance kind, class/interface shape hoặc field type có thể tạo những lỗi liên kết khác nhau. Không sửa bằng tăng `max_stack` hoặc recompute stack map frames.

### 16.2. Vì sao lỗi Java linkage có thể chỉ xuất hiện sau instrumentation?

Một transformer có thể chèn lời gọi tới helper API mà agent đã compile với version mới, nhưng ở runtime helper JAR cũ được resolve. JVM có thể báo `NoSuchMethodError` từ instruction mới chèn. Nguồn thay đổi vẫn là instrumentation, nhưng **bản chất lỗi** là method linkage, không phải bytecode verification.

## 17. `IllegalAccessError` khác lỗi reflection

`IllegalAccessError` có thể xảy ra khi bytecode cố truy cập một class/member không được phép theo quy tắc linking/access.

`java.lang.reflect.InaccessibleObjectException` thường xuất hiện khi reflective code tìm cách mở quyền truy cập sâu vào class/package mà Java Module System không cho phép.

Ví dụ:

~~~text
java.lang.IllegalAccessError: class A tried to access class B ...
~~~

so với:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible: module ... does not "opens" ...
~~~

Giải pháp có thể là cập nhật dependency hoặc configuration exports/opens khi hợp đồng cho phép. Nhưng đừng gán mọi lỗi liên quan module cho `VerifyError`; verifier type checking, module access và reflection policy có mục đích riêng.

### 17.1. Không dùng `--add-opens` làm thuốc chữa chung

Một cờ như:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

chỉ là ví dụ cú pháp cho một phạm vi reflective access cụ thể. Nó không thêm method bị thiếu, không sửa class-file format, và không cung cấp stack frames hợp lệ. Khi cần, phải xác định chính xác thư viện đang truy cập package nào, quyền nào thiếu và phiên bản hỗ trợ.

## 18. Hai class có cùng tên chưa chắc là một type

Một Java type runtime được xác định bởi **binary name và defining class loader**. Trong application server, plugin framework hoặc OSGi, có thể nạp hai lớp cùng tên:

~~~text
loader A -> com.example.Model
loader B -> com.example.Model
~~~

Kết quả chuyển type có thể gây:

~~~text
ClassCastException:
  class com.example.Model cannot be cast
  to class com.example.Model
~~~

Đó thường là lỗi class identity/class-loader isolation, không phải JVM verifier. Một bytecode transformer cũng phải tính đến class loader của class được instrument khi chèn helper references.

### 18.1. Parent delegation không phải thiết kế duy nhất

Một custom class loader có thể dùng child-first hoặc chiến lược riêng. Nếu agent assume mọi helper tồn tại trên system class loader, một class do plugin loader nạp có thể không resolve được helper và ném `NoClassDefFoundError`. Điều này có thể chỉ xảy ra khi plugin được gọi, trong khi ứng dụng chính vẫn hoạt động.

## 19. Cơ chế `ClassFileTransformer` trong Java agents

Java Instrumentation API cho phép agent đăng ký transformer:

~~~java
instrumentation.addTransformer(transformer);
~~~

Lúc một class được định nghĩa hoặc xử lý lại theo cơ chế instrumentation, JVM có thể gọi transformer để lấy class bytes mới.

Một transformer tối giản chỉ quan sát class names:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ObserveClasses implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if (className != null
                && className.startsWith("example/service/")) {
            System.err.println("[agent] " + className);
        }
        return null; // Không thay đổi class bytes.
    }
}
~~~

Ví dụ dùng overload truyền thống; các JDK hiện đại còn có overload nhận `Module`. Khi trả `null`, transformer không yêu cầu sửa bytes. Nếu trả bytes mới, JVM sẽ kiểm tra class file mới theo những ràng buộc phù hợp.

### 19.1. Một transformer gây `VerifyError` như thế nào?

Ví dụ chuỗi thay đổi:

~~~text
Original class bytes (valid)
             |
             v
Transformer inserts instructions
             |
             +--> updated method descriptor?
             +--> updated stack / locals?
             +--> updated branch targets?
             +--> updated StackMapTable?
             +--> preserved constructor constraints?
             |
             v
Transformed class bytes
             |
             v
JVM verifier
             |
             +--> valid -> class can link
             |
             +--> invalid -> VerifyError / related error
~~~

Lỗi có thể đến từ **transformer implementation**, **một transform khác trước/sau**, hoặc **bytecode library không hỗ trợ class-file version mới**.

## 20. Startup agent khác dynamic attach trong chẩn đoán

Startup agent được cấu hình bằng:

~~~bash
java -javaagent:/opt/agents/monitor.jar -jar app.jar
~~~

JVM gọi `premain` trước `main`. Agent có thể thấy class loads từ rất sớm.

Dynamic attach dùng `VirtualMachine.loadAgent` qua Attach API để JVM đang chạy gọi `agentmain` khi chính sách/quyền cho phép.

### 20.1. Tại sao cần biết thời điểm agent được nạp?

Nếu class bị lỗi được nạp trước khi dynamic agent xuất hiện, transformer chỉ được đăng ký về sau không tự làm nó thay đổi. Agent cần retransformation/redefinition khi được JVM hỗ trợ và khi class có thể sửa. Ngược lại, startup agent có thể chặn ngay lần định nghĩa đầu.

Điều tra phải ghi:

- Agent JAR, version và checksum.
- Startup hay dynamic attach.
- Thứ tự các `-javaagent`.
- Transformer nào trả bytes mới.
- Class đã nạp trước hay sau agent.
- Có yêu cầu `Can-Retransform-Classes` không.
- JVM support `isRetransformClassesSupported()` và `isModifiableClass()`.

### 20.2. JEP 451 và JDK 21

Từ JDK 21, dynamic agent loading có thể tạo cảnh báo theo JEP 451 trên các JVM phù hợp, hướng tới chính sách yêu cầu sự cho phép rõ hơn. Warning này không đồng nghĩa `VerifyError`. Một agent có thể được nạp hợp lệ nhưng transform lỗi; cũng có thể bị policy từ chối trước khi có bất kỳ class transformation nào.

Không tắt security controls hoặc cho phép dynamic attach rộng chỉ để chẩn đoán một exception nếu policy môi trường không cho phép.

## 21. ASM: đọc, ghi và tính toán frames

ASM là thư viện thao tác bytecode ở class-file level. Trong instrumentation pipeline, ASM có thể:

- Đọc `ClassReader`.
- Tạo/biến đổi visitors cho class và methods.
- Ghi `ClassWriter`.
- Tính toán một số metadata như maximum stack/local sizes và stack map frames.
- Cung cấp utility để kiểm tra representation trước khi JVM tải class.

Ví dụ minh họa cách đọc và ghi lại class bằng ASM:

~~~java
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;

public final class BytecodeRewriter {
    public static byte[] rewrite(byte[] original) {
        ClassReader reader = new ClassReader(original);

        ClassWriter writer = new ClassWriter(
                reader,
                ClassWriter.COMPUTE_FRAMES
                        | ClassWriter.COMPUTE_MAXS);

        reader.accept(writer, ClassReader.EXPAND_FRAMES);
        return writer.toByteArray();
    }
}
~~~

Đây là ví dụ **cơ chế** để tìm hiểu các flags, không phải một transformer sản xuất an toàn cho mọi class loader/module. Khi `COMPUTE_FRAMES` cần tìm common superclass, ASM có thể phải resolve types. Cách resolution mặc định có thể không phù hợp custom class loaders, modules hoặc những classes chỉ tồn tại bên trong target JVM.

### 21.1. `COMPUTE_MAXS` không thay `COMPUTE_FRAMES`

`COMPUTE_MAXS` giúp tính toán giới hạn stack/locals. Nó không có nghĩa mọi stack map frames được tái tính đúng cho biến đổi control flow. `COMPUTE_FRAMES` xử lý việc tính frames theo những điều kiện của ASM version và classpath/type hierarchy mà nó nhìn thấy.

Nếu một agent chèn jump hoặc thay data-flow mà chỉ dùng `COMPUTE_MAXS`, những frame cũ có thể không còn phù hợp. Tuy nhiên chỉ bật `COMPUTE_FRAMES` mà input class bị malformed hoặc hierarchy lookup sai cũng chưa giải quyết hết.

### 21.2. Cần tương thích ASM với JDK/class file

Phiên bản ASM phải biết class-file format/opcodes/attributes mà nó cần đọc/ghi. Khi nâng từ Java 17 sang 21, một agent nhúng ASM cũ có thể báo `Unsupported class file major version 65`.

Giải pháp là nâng **tool hoặc agent thực sự đóng gói ASM**, ưu tiên phiên bản được vendor hỗ trợ. Ép override một dependency ASM bắc cầu trong ứng dụng có thể không có tác dụng nếu agent đã shade ASM vào JAR riêng.

## 22. Kiểm tra output ASM bằng `CheckClassAdapter`

ASM có utilities hỗ trợ kiểm tra một số tính đúng đắn của class representation:

~~~java
import java.io.PrintWriter;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.util.CheckClassAdapter;

public final class InspectBytes {
    public static void inspect(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        CheckClassAdapter.verify(
                reader, false, new PrintWriter(System.err, true));
    }
}
~~~

Ví dụ phụ thuộc ASM utility artifact và runtime/classpath phù hợp. Đây là bước hỗ trợ phát hiện vấn đề **trước khi JVM định nghĩa class**, không phải chứng nhận mọi behavior hoặc JVM verifier luôn chấp nhận bytes trong mọi môi trường.

Một số biến thể của `CheckClassAdapter.verify` dùng class loader riêng để resolve types. Khi debug classes của application server/OSGi, phải cung cấp ngữ cảnh giải quyết type thích hợp nếu API version cho phép.

### 22.1. Không kiểm tra sai bytes

Nếu agent A tạo bytes A, agent B sửa tiếp thành bytes B và JVM nạp B, kiểm tra A “pass” không chứng minh B hợp lệ.

Cần biết **bytes ở từng điểm pipeline** và, khi có thể, kiểm tra bytes cuối cùng sẽ được JVM nhận. Instrumentation frameworks có thể cung cấp cơ chế dump transformed classes; nên dùng tính năng được hỗ trợ và lưu file bảo mật.

## 23. Byte Buddy và dynamic code generation

Byte Buddy thường được các framework sử dụng để tạo subclasses, proxies, method interceptors hoặc biến đổi class. Trong migration, lỗi có thể xuất hiện:

- Khi library chưa hỗ trợ class-file version mới.
- Khi generated method trả kiểu không khớp declared method.
- Khi instrumentation chèn lời gọi tới helper không được class loader thấy.
- Khi method/field access hoặc module boundaries thay đổi.
- Khi agent retransformation đụng các giới hạn thay cấu trúc class.
- Khi một mock framework hoặc runtime library dùng Byte Buddy bị resolve sai version.

Không nên quy tất cả lỗi có frame `net.bytebuddy.*` thành bug của Byte Buddy core. Có thể chính plugin cấu hình matcher/Advice sai hoặc dùng API version không tương thích.

### 23.1. Advice và kiểu return

Giả sử một method có:

~~~java
public long getBalance() {
    return 100L;
}
~~~

Một advice tự xây cố return object reference thay cho `long` mà không có boxing/unboxing và descriptor phù hợp có thể khiến bytecode không hợp lệ. Các thư viện instrumentation cung cấp API để khai báo binding/return types; cần dùng đúng contract thay vì tự chèn stack instructions.

### 23.2. Phân biệt generate và transform

Dynamic class generation có thể tạo class hoàn toàn mới; transformation sửa một class có sẵn. Khi đang retransform/redefine một class đã nạp, JVM áp dụng những giới hạn về thay đổi class schema. Một thao tác hợp lệ khi tạo class mới chưa chắc hợp lệ khi retransform class hiện hữu.

## 24. Coverage, mocking và APM agents

Các nhóm công cụ thường can thiệp bytecode:

| Công cụ/nhóm | Cơ chế có thể dùng | Lỗi cần để ý khi nâng JDK |
| --- | --- | --- |
| JaCoCo/coverage | Thêm probes vào methods | Classfile version chưa hỗ trợ, frames/instrumentation |
| Mockito với inline instrumentation | Byte Buddy/agent instrumentation | Dynamic attach policy, transformer compatibility |
| APM/tracing Java agents | Startup `-javaagent` và class transformers | Framework matcher, module access, classfile support |
| Profiling/monitoring | Java/native agent, JVMTI/JFR | Native/JVM version, permissions và class loading |
| Framework proxies | Runtime-generated subclasses/classes | Constructor, method descriptors, module access |
| Build-time enhancer | Rewrite class files sau `javac` | Stale output, bad frames, plugin version |

Một unit test lỗi vì mocking/coverage không có nghĩa application source Java sai. Nhưng khi test infrastructure không thể chạy, nhóm chưa có đủ bằng chứng chất lượng để công bố migration hoàn tất.

### 24.1. Khi không có agent thì test pass

Đây là một tín hiệu khoanh vùng, không phải kết luận cuối:

~~~text
JDK 21 + application + agent A = VerifyError
JDK 21 + application without agent = PASS
~~~

Tiếp theo phải xác định class nào được agent A transform và vì sao bytes không hợp lệ. Không coi việc tắt agent đo hiệu năng/bảo mật/coverage trong production là một fix hợp lệ nếu agent thuộc yêu cầu vận hành.

## 25. Một pipeline có nhiều transformers

Ví dụ:

~~~text
Original .class from JAR
          |
          v
Transformer A: tracing
          |
          v
Transformer B: mocking / testing
          |
          v
Transformer C: coverage
          |
          v
JVM verification and class definition
~~~

Sơ đồ đơn giản hóa: thứ tự thực tế và các quy tắc áp dụng có thể khác khi retransformation hay transformer registered ở nhóm khác nhau. Nhưng nó cho thấy một thực tế: **lỗi chỉ xuất hiện khi kết hợp agents** có thể do biến đổi tương tác, dù từng agent đứng riêng đều pass.

### 25.1. Test tổ hợp và thứ tự

Khi nghi có xung đột:

1. Ghi đầy đủ mọi `-javaagent` và `-agentlib`/`-agentpath`.
2. Xác nhận thứ tự startup agents thực tế.
3. Chạy A-only, B-only và A+B trong staging.
4. So class bytes hoặc logs transformed class names.
5. Xem helper class visibility và duplicate instrumentation.
6. Đọc vendor guidance về việc hai agents cùng instrument framework.

Không đơn giản đổi thứ tự agents trên production mà không kiểm thử; tác động có thể lan tới observability, performance và business behavior.

## 26. Class loading từ JAR bị shading, relocation hoặc repackaging

Một JAR có thể được build đúng, nhưng bước packaging làm thay đổi bytes:

- Maven Shade/Gradle Shadow relocation.
- Bytecode obfuscation/minification.
- Repackaging into fat/nested JAR.
- Bỏ file `META-INF/services` hoặc rewrite manifest.
- Gộp duplicate classes từ nhiều dependencies.
- Build plugin instrument output sau compilation.

Ví dụ library A tham chiếu `com.vendor.Helper`, nhưng shading đổi sang `shaded.com.vendor.Helper` mà bỏ sót một descriptor/annotation/reference. Runtime có thể gặp `NoClassDefFoundError`, `ClassFormatError`, `VerifyError` hoặc lỗi linkage tùy vị trí/reference bị hỏng.

### 26.1. Kiểm tra artifact cuối cùng

Không chỉ kiểm tra `target/classes` hoặc `build/classes/java/main`. Hãy kiểm tra chính **JAR/container/JVM image sẽ được triển khai**:

~~~bash
jar --list --file build/final-app.jar
java -version
~~~

Sau đó dùng `javap`/`jdeps` trên artifact phù hợp, hoặc extract class để phân tích trong workspace riêng khi cần.

### 26.2. Multi-release JAR

MRJAR có root classes và các variants dưới `META-INF/versions/N`. Một tool quét ZIP thô có thể đọc bản Java 21 trên JVM thấp hoặc bỏ qua branch được chọn thực sự. Với `javap`/`jdeps` hỗ trợ:

~~~bash
javap --multi-release 21 \
  -classpath library.jar -v com.example.Feature

jdeps --multi-release 21 --summary library.jar
~~~

Lưu ý: lựa chọn view trong tool không thay thế việc test runtime trên JDK thật. Custom class loader hoặc nested-JAR launcher có thể có cách hỗ trợ MRJAR khác nhau.

## 27. `invokedynamic`, lambdas và bootstrap method errors

Từ Java 7/8, JVM có cơ chế dynamic linkage như `invokedynamic`, dùng rộng rãi cho lambdas và những ngôn ngữ trên JVM. `ConstantDynamic` có từ class-file format đời sau và cũng dùng bootstrap mechanism.

Một bootstrap method có thể:

- Nằm trong class/helper không khả dụng.
- Có method handle/descriptor không phù hợp.
- Ném exception khi tạo call site hoặc dynamic constant.
- Gặp module accessibility hoặc class-loader issue.

Kết quả có thể là `BootstrapMethodError` hoặc một lỗi linkage/initialization khác, **không nhất thiết là `VerifyError`**.

### 27.1. Khi nào nghi bootstrap?

Nếu stack trace chứa:

~~~text
java.lang.BootstrapMethodError: bootstrap method initialization exception
~~~

hoặc frames liên quan `java.lang.invoke`, kiểm tra:

- Constant pool entries liên quan `InvokeDynamic`/`Dynamic`.
- BootstrapMethods attribute.
- Method handles và referenced classes.
- Classpath/module path và helper JAR versions.
- Bytecode transformer có thay constant pool hoặc bootstrap arguments không.

Không sửa bằng cách thay `StackMapTable` trước khi xác định thực sự có verification failure.

## 28. Các lỗi đặc thù khi dùng Java Module System

Khi nâng từ JDK 8 lên JDK 11/17/21, strong encapsulation và module boundaries có thể làm tooling lỗi.

Ví dụ:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

Những lỗi này có thể phát sinh từ agent, annotation processor, reflection library hoặc custom loader. Nguyên nhân không tự động là bytecode malformed.

### 28.1. Module readability và exports

Một class trong module A tham chiếu type trong module B có thể cần read edge và package exports phù hợp. Một transformer chèn helper reference mà target module không được phép truy cập có thể làm runtime linkage thất bại.

### 28.2. Reflection cần opens

Framework dùng `setAccessible(true)` có thể cần package được mở theo luật JPMS. Với library cũ, ưu tiên bản hỗ trợ JDK đích. Nếu cần workaround, chỉ mở đúng package cho đúng module với owner/mốc gỡ.

### 28.3. `Instrumentation.redefineModule`

Java Instrumentation API cung cấp cách điều chỉnh một số module relationships trong phạm vi được JVM hỗ trợ. Đây là API nâng cao, không phải lý do mở toàn bộ JDK internals. Agent phải được kiểm thử về security/access trên đúng runtime.

## 29. Bytecode do annotation processors và generators tạo

Không phải mọi generated code đi qua cùng đường:

- Annotation processors thông thường sinh Java source và compiler sau đó compile.
- Một số bytecode generators viết class files trực tiếp.
- Build-time enhancers sửa class file sau compiler.
- Proxies được tạo tại runtime.
- OpenAPI/JAXB/protobuf generators chủ yếu sinh Java source, nhưng pipeline tổng thể có thể tích hợp enhancer/instrumentation khác.

Nếu generated **Java source** không compile, nguyên nhân chưa phải JVM `VerifyError`. Nếu source compile nhưng class đã bị plugin rewrite sau đó nạp lỗi, cần phân tích output cuối.

### 29.1. Phân biệt hai lỗi

~~~text
error: cannot find symbol ...
~~~

là compiler/source error trong tình huống thông thường.

~~~text
java.lang.VerifyError: ...
~~~

cho thấy JVM verifier đang từ chối bytecode. Không gọi cả hai chung là “generator lỗi” mà bỏ qua pha xảy ra.

### 29.2. Nâng generator và compiler phải đồng bộ

Một parser/plugin JDK cũ có thể không hiểu records, sealed classes hoặc pattern switch. Một class file version mới cũng có thể vượt phiên bản bytecode engine của enhancer. Trong migration, kiểm kê **generator/parser/bytecode library versions** riêng với **application runtime JDK**.

## 30. Quy trình điều tra từng bước

### Bước 1 — Thu thông điệp đầu tiên

Ghi stack trace đầy đủ, `Caused by`, class name, method name, loader/module information, timestamp và thread. Nếu class initialization thất bại rồi gây `NoClassDefFoundError`, phải tìm **lỗi gốc** trong cùng process.

### Bước 2 — Xác định tầng lỗi

Hỏi:

- JVM từ chối class file → `ClassFormatError` hay `VerifyError`?
- JVM không hiểu class-file version → `UnsupportedClassVersionError`?
- Tool ASM từ chối version → exception từ thư viện parser?
- JVM không tìm class/helper → `NoClassDefFoundError`?
- Method/field API bị thay → `NoSuchMethodError`/`NoSuchFieldError`?
- Có deep reflection/module denial?
- Có JNI/native loader failure?

### Bước 3 — Ghi môi trường thật

~~~bash
java -version
javac -version
~~~

Ghi vendor/build của JVM đích, OS/image, CPU architecture, JVM flags, agents và artifact hash.

### Bước 4 — Tìm class bytes thực tế

Xác định JAR/directory/module nguồn mà runtime loader dùng. Nếu class được generated hoặc transformed, cần tìm bytes **sau** những bước ấy, không chỉ class file trong source output.

### Bước 5 — Kiểm tra class file

~~~bash
javap -v -c -p -classpath path/to/classes-or.jar \
  com.example.Service
~~~

Tìm version, methods, descriptors, `Code`, `StackMapTable` và constant-pool references liên quan.

### Bước 6 — So sánh baseline và target

So cùng class trước/sau JDK migration, trước/sau transformer, hoặc agent A bật/tắt trong môi trường kiểm soát.

### Bước 7 — Sửa đúng tầng

- Compile target sai → sửa toolchain/`--release`.
- JAR/version lệch → sửa dependency resolution và packaging.
- Agent/ASM cũ → nâng tool theo support matrix.
- Frames/bytecode sai → sửa transformation logic rồi tái kiểm.
- Loader/module conflict → sửa visibility/access policy phù hợp.
- Native library thiếu → sửa native artifact/image/ABI.

### Bước 8 — Chạy lại kiểm thử hồi quy

Chạy trên JVM/runtime image thật; xác nhận không chỉ exception biến mất mà instrumentation, data behavior, tests, observability và performance vẫn đúng.

## 31. Phân tích lỗi từ chính `VerifyError` message

Ví dụ:

~~~text
Exception in thread "main" java.lang.VerifyError:
  Bad type on operand stack
Exception Details:
  Location:
    com/example/Service.process()V @25: invokevirtual
  Reason:
    Type integer (current frame, stack[0])
    is not assignable to 'java/lang/Object'
  Current Frame:
    bci: @25
    locals: { ... }
    stack: { integer }
  Bytecode:
    ...
  Stackmap Table:
    ...
~~~

Đây là cấu trúc minh họa kiểu thông điệp HotSpot; trường và wording thay đổi tùy lỗi.

**Cách đọc:**

1. `Location`: class, method, descriptor và bytecode index (`bci`).
2. `Reason`: ràng buộc kiểu nào bị vi phạm.
3. `Current Frame`: locals và operand stack verifier đang suy ra.
4. `Bytecode`: vùng instructions gây vấn đề.
5. `Stackmap Table`: expected verification states tại các frame liên quan.

Đặt `bci 25` cạnh `javap -c -v -p` để hiểu instruction đang yêu cầu operand nào. Nếu class đã được transformer rewrite, dùng disassembly của **transformed bytes**, không phải original source class.

### 31.1. `bci` không phải line number Java

Bytecode index là vị trí trong instruction stream, không phải số dòng source. `LineNumberTable` có thể giúp đối chiếu, nhưng code sinh/runtime-generated có thể không chứa source line information. Khi thiếu debug metadata, phân tích bytecode và stack state vẫn là nguồn dữ liệu chính.

## 32. Logging class loading và class loader inspection

Trên những JDK HotSpot hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Lệnh có thể cung cấp tên class và nguồn nạp để phát hiện class từ JAR/version ngoài dự kiến. Log có thể rất lớn; cần giới hạn phạm vi và không để đường dẫn/chi tiết nhạy cảm bị chia sẻ bừa bãi.

`java -Xlog:help` giúp kiểm tra tags/levels có trên JVM cụ thể. Không mặc định mọi JDK vendor dùng đúng hệ logging hoặc tags giống nhau.

### 32.1. Quan sát class loader khi JVM đang chạy

Một số JDK cung cấp diagnostics qua `jcmd`:

~~~bash
jcmd <pid> help
jcmd <pid> VM.classloaders
~~~

`<pid>` phải là PID của JVM được phép quản trị; command availability phụ thuộc JVM/version và attach policy. Không dùng những công cụ này để truy cập process không được phép, và không coi khả năng chạy `jcmd` là bằng chứng Java agent dynamic loading cũng được cho phép.

### 32.2. Class source có thể khác compile classpath

Một application server có class loader isolation, hoặc một fat JAR có nested dependencies, có thể nạp một version thư viện khác với version IDE/`mvn dependency:tree` kỳ vọng. Vì vậy, danh sách dependencies trong build là **một loại bằng chứng**, còn class source ở runtime là bằng chứng khác.

## 33. Dependency graph: tìm đúng version runtime

### 33.1. Maven

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Kiểm tra BOM, scopes, exclusions, plugin dependencies và JARs thực tế trong deployment. Dependency runtime và annotation processor/plugin classpaths có thể không giống nhau.

### 33.2. Gradle

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
  --dependency byte-buddy \
  --configuration runtimeClasspath
~~~

Nếu lỗi đến từ build plugin hoặc test agent, `runtimeClasspath` của application **chưa chắc chứa tool đang lỗi**. Hãy xem buildscript/plugin/test configuration tương ứng và agent JAR đóng gói độc lập.

### 33.3. Dependency shading

Một APM agent có thể nhúng ASM dưới package đã relocate, nên không xuất hiện dưới tên `org.objectweb.asm` trong dependency tree của ứng dụng. Cần xem **agent release/version và embedded libraries** theo vendor documentation.

## 34. So sánh original class và transformed class

Tình huống thực tế:

~~~text
classes/original/com/example/OrderService.class
classes/transformed/com/example/OrderService.class
~~~

Nếu framework cung cấp tính năng dump transformed bytecode, hãy lưu vào workspace chẩn đoán được phép rồi so:

~~~bash
javap -v -c -p \
  -classpath classes/original \
  com.example.OrderService

javap -v -c -p \
  -classpath classes/transformed \
  com.example.OrderService
~~~

Ghi:

- Class-file major/minor versions.
- Method descriptors.
- New instructions và method references.
- Exception handlers.
- `max_stack`/`max_locals`.
- `StackMapTable`.
- Helper classes và module references.

### 34.1. Không tự công bố transformed bytes chứa bí mật

Bytecode dump có thể bao gồm string constants, class/method names, endpoint names hoặc dữ liệu kinh doanh. Lưu và chia sẻ theo chính sách bảo mật; không đưa artifact production chưa được kiểm duyệt lên diễn đàn công khai.

### 34.2. Dùng dữ liệu quan sát thay cho phỏng đoán

Một test A/B xác nhận `VerifyError` chỉ xuất hiện với agent mới là bằng chứng hữu ích. Nhưng nguyên nhân cụ thể vẫn cần xem bytes và stack trace. Có thể agent mới làm lộ bug của một transformer khác, không nhất thiết nó là transformer trực tiếp tạo class lỗi.

## 35. Test class trước khi đưa vào class loader

Với một pipeline bytecode generator nội bộ, nên có nhiều lớp kiểm tra:

1. Parse output bằng bytecode library tương thích.
2. Kiểm tra structural invariants và frames qua utility thích hợp.
3. Define class trong JVM test/isolation đúng JDK target.
4. Chạy methods chứa branches, exceptions và constructors.
5. Test với class loaders và modules thực tế.
6. Chạy các integration scenarios dùng code được sinh.

### 35.1. Parse/verify offline không thay JVM verifier

Một library có thể đọc và kiểm tra được bytes nhưng JVM vẫn có thể từ chối do những ràng buộc sâu hơn, đặc thù environment hoặc dependencies không resolve được. Đừng gọi “ASM checks pass” là “JVM đã verified”.

### 35.2. Đừng đưa malformed class vào production để test

Việc cố ý tạo class bytes sai nên chỉ làm trong isolated tests hoặc tooling của developer, với dữ liệu/kịch bản có kiểm soát. Đừng thử trực tiếp trên production JVM đang phục vụ traffic.

## 36. Vì sao không nên tắt bytecode verification?

Một số tài liệu hoặc câu trả lời cũ có thể khuyên:

~~~text
-Xverify:none
-noverify
~~~

Những cách bỏ qua verification này đã bị deprecate và/hoặc không còn hữu dụng/được hỗ trợ ở các JDK mới. Quan trọng hơn, **tắt verifier không sửa bytecode malformed** và có thể loại bỏ cơ chế an toàn của JVM.

Không coi đây là cách xử lý production cho `VerifyError`. Nếu một agent sinh bytecode sai, hãy sửa agent/transformer hoặc chọn version tương thích. Nếu class file bị lỗi packaging, sửa artifact. Nếu compiler target sai, sửa build.

### 36.1. `-Xverify:all` có vai trò khác

Trên những JVM hỗ trợ, `-Xverify:all` yêu cầu verification theo chế độ được chỉ định, có thể hữu ích khi điều tra. Tuy nhiên nó không phải giải pháp “tăng độ tương thích” và không thay việc xem bytes/stack trace. Cần xác nhận option availability với JDK vendor/release mục tiêu.

## 37. Ba ví dụ chẩn đoán phổ biến

### Ví dụ A — JDK 17 lên 21, coverage parser không hiểu class file

Tình huống:

~~~text
Compile Java 21: SUCCESS
Start app without coverage: SUCCESS
Run tests with coverage: FAIL
IllegalArgumentException: Unsupported class file major version 65
Stack trace contains ASM/coverage library
~~~

Phân tích:

- Major version 65 là Java 21.
- JVM Java 21 tự chạy được class.
- Lỗi xảy ra trong bytecode parser của coverage tool, không phải Java verifier.

Hướng xử lý:

1. Xác định coverage plugin/agent version thực tế.
2. Xem vendor support matrix cho Java 21 class files.
3. Nâng đúng plugin/agent/embedded parser stack theo policy.
4. Chạy lại unit tests, instrumentation và coverage reports.
5. Kiểm tra agent có đang được nạp startup hoặc dynamic không; xử lý chính sách attach riêng nếu liên quan.

Không giảm target xuống Java 17 chỉ để che công cụ coverage quá cũ khi sản phẩm đã quyết định chuyển Java 21.

### Ví dụ B — Agent chèn branch thiếu frames

Tình huống:

~~~text
Java app without agent: PASS
Java app with tracing agent: VerifyError
  Expecting a stackmap frame at branch target ...
Affected class: com.example.OrderService
~~~

Giả thuyết chính: Transformer chèn jump/exception handler nhưng stack map frames không còn nhất quán.

Hướng xử lý:

1. Ghi agent JAR/version và class output path.
2. Dump transformed bytes nếu công cụ hỗ trợ.
3. So `javap -c -v` trước/sau và xem `bci` trong VerifyError.
4. Kiểm tra transformer có cập nhật control flow, stack/locals và frames không.
5. Nếu dùng ASM, xem `COMPUTE_FRAMES` và khả năng resolve type hierarchy đúng class loader.
6. Dùng công cụ kiểm tra bytes kết hợp JVM load test.
7. Sửa/up-version transformer và thử trên cả JDK cũ/mới theo contract.

Không sửa bằng thêm JAR giả định hoặc tắt verifier.

### Ví dụ C — Shaded JAR thiếu helper class

Tình huống:

~~~text
CI unit test on classes directory: PASS
Packaged application start: PASS
First API request: NoClassDefFoundError
  com/vendor/codec/InternalHelper
~~~

Giả thuyết: Helper bị loại/relocate sai khi shading hoặc class loader không thấy.

Hướng xử lý:

1. Xác định class được nạp từ final JAR.
2. Kiểm tra `jar --list` và output packaging.
3. Xem dependency graph và shading relocations.
4. Dùng `jdeps`/`javap` xem references.
5. Sửa packaging/loader rules.
6. Test chức năng cần helper trên final artifact, không chỉ startup.

Đây là lỗi class loading/linkage; tính lại `StackMapTable` không giải quyết class bị thiếu.

## 38. Tình huống `NoSuchMethodError` chỉ khi thêm agent

Một agent được compile với `TraceHelper` v2 có method:

~~~java
public static void onEnter(String operation, long startedAt);
~~~

Nhưng runtime helper mà JVM thấy lại là v1:

~~~java
public static void onEnter(String operation);
~~~

Transformer chèn lời gọi tới descriptor v2. JVM có thể nạp class được transform mà đến lúc resolve helper method thì báo:

~~~text
java.lang.NoSuchMethodError:
  'void example.agent.TraceHelper.onEnter(java.lang.String,long)'
~~~

Điểm chẩn đoán:

- Instruction gọi method đúng mặt cú pháp/stack chưa chắc method đó tồn tại ở runtime.
- Error không phải `VerifyError` nếu bytecode structure và operand types hợp lệ.
- Cần kiểm tra helper class thực tế được class loader resolve và version agent JAR.

Với agents có shading/relocation hoặc class-loader isolation, việc thêm một dependency `trace-helper` vào app classpath không phải lúc nào cũng đúng. Nên theo tài liệu đóng gói agent và sửa loader strategy.

## 39. Một tình huống nhiều class loaders cùng tên class

Giả sử:

~~~text
AppClassLoader    -> com.example.spi.Payment
PluginClassLoader -> com.example.spi.Payment
~~~

Khi plugin trả về một object của `Payment` do loader plugin định nghĩa, code ứng dụng cast sang `Payment` do app loader định nghĩa có thể gặp `ClassCastException`.

Nếu transformer chèn method call dùng helper class `Payment` trong loader khác, có thể dẫn đến linkage/access issues khác.

### 39.1. Các bước điều tra

1. Ghi class name và defining loader của từng type khi có thể.
2. Kiểm tra parent/child-first delegation model.
3. Xác định các API classes có cần được share qua parent loader không.
4. Xem JAR duplicates và plugin isolation.
5. Cân nhắc transformer/helper visibility trong từng loader.
6. Chạy integration tests với cấu trúc loader thực.

Không coi hai class “cùng fully qualified name” là một class type trong JVM.

## 40. Test matrix cho quá trình migration JDK

Một ma trận hỗ trợ tối thiểu cho hệ có bytecode agents:

| Case | JDK | App artifact | Agent/instrumentation | Mục tiêu |
| --- | --- | --- | --- | --- |
| A | JDK cũ | Artifact cũ | Agent cũ | Baseline |
| B | JDK mới | Artifact cũ nếu được hỗ trợ | Agent cũ nếu được hỗ trợ | Tách tác động runtime |
| C | JDK mới | Artifact mới | Không agent (staging) | Tách lỗi app/packaging |
| D | JDK mới | Artifact mới | Agent mới | Tổ hợp mục tiêu |
| E | JDK mới | Artifact mới | Tất cả agents thật | Phát hiện tương tác |
| F | JDK tối thiểu còn hỗ trợ | Final artifact phù hợp | Agent tương thích | Backward support |

Không ép chạy tổ hợp không được vendor support. Mỗi test record phải có JDK vendor/build, image digest, agent checksum, JVM flags và test report.

### 40.1. Những test bắt buộc nên có

- Clean build và source/bytecode target.
- JAR/module/classloader resolution.
- Generated code và proxies.
- Bytecode verification thực tế khi load các chức năng quan trọng.
- Unit/integration tests với agent/coverage/mock đã được duyệt.
- Startup và first-request smoke tests.
- Serialization/HTTP/JDBC/async paths có instrumentation.
- Module/reflection access và JNI nếu liên quan.
- Observability: traces, metrics và error capture.
- Performance/GC/startup overhead ở workload quan trọng.

### 40.2. Test artifact phát hành, không chỉ thư mục build

Một build plugin có thể transform class sau lúc unit tests compile source. Nếu chỉ test `build/classes` mà deploy `app-all.jar`, class thực tế có thể khác. Cần chạy ít nhất một smoke/integration suite với **artifact cuối cùng**.

## 41. Thu thập bằng chứng tối thiểu khi báo cáo incident

Mẫu record:

~~~text
Incident ID:
Java application artifact and SHA-256:
JDK vendor/version/build:
OS image/architecture:
First Throwable and full stack trace:
Class binary name / method / descriptor:
Bytecode index (bci), if VerifyError:
Class-file major/minor version:
Loaded-from JAR/module/class-loader:
Manifest/MRJAR version selected:
Build tool/compiler --release:
Transformers/agents and versions/checksums:
Transformation timing and class loading order:
Original/transformed class byte checksums:
Dependency and shading graph:
Known-good baseline:
Smallest reproducible scenario:
Fix and test evidence:
Owner and release decision:
~~~

Không đưa credentials, tokens, heap/core dumps hoặc bytecode có thông tin nhạy cảm lên issue công khai. Redact JVM arguments và đường dẫn theo chính sách.

### 41.1. Giữ nguyên lỗi đầu tiên

Một service tự restart liên tục có thể ghi log theo nhiều process. Khi class initialization lỗi, dòng `NoClassDefFoundError` ở request sau không phải root cause. Giữ logs từ lần đầu JVM load class/agent; nếu có nhiều process, gắn log với PID/container ID tương ứng.

## 42. Luồng chẩn đoán tổng quát

~~~text
App does not start / fails at first use
                |
                v
      Which exception/error?
                |
     +----------+-----------------------------+
     |          |                             |
     v          v                             v
 VerifyError  ClassNotFound / NoClassDef    Method/field linkage
     |          |                             |
     v          v                             v
 Frames,     JAR/class-loader,             API descriptors,
 stack,      initialization cause,         resolved versions,
 control     shading, modules              static/instance kind
 flow
     |
     v
 Was class transformed?
     |
     +-- yes --> agent/ASM/Byte Buddy, bytes before/after
     |
     +-- no  --> compiler, generator, artifact integrity

 Cross-cutting:
 - JVM full version and class-file major
 - OS/container and runtime artifact
 - JPMS and security policy
 - original first stack trace
 - integration test on final artifact
~~~

Đây là cây quyết định sơ lược. Nếu exception đến từ native loader, FFM/JNI hoặc bootstrap method, phải chuyển sang nhánh điều tra chuyên biệt tương ứng chứ không ép vào một trong ba cột.

## 43. Các anti-pattern cần tránh

**“Bật `-noverify` là sửa được `VerifyError`.”** Không đúng và không an toàn. Phải sửa malformed bytecode hoặc công cụ tạo nó.

**“Compile pass nghĩa là mọi class runtime đều hợp lệ.”** Không đúng nếu sau compile còn transformation, shading, code generation hoặc custom loaders.

**“`Unsupported class file major version` luôn do JVM cũ.”** Không đúng nếu message đến từ ASM hoặc công cụ bytecode parser.

**“Thấy `NoClassDefFoundError` thì chỉ cần thêm JAR.”** Không đúng khi class initialization đã thất bại hoặc loader không có visibility.

**“`NoSuchMethodError` là stack-frame error.”** Không đúng trong phần lớn trường hợp; cần xem method descriptor/runtime ABI.

**“Cứ `--add-opens` là mọi lỗi JDK 17/21 biến mất.”** Không đúng; đây không phải cách sửa verifier hoặc method/class thiếu.

**“`COMPUTE_MAXS` tự tái tạo mọi stack map frame.”** Không đúng; phải hiểu `COMPUTE_FRAMES` và type hierarchy.

**“`COMPUTE_FRAMES` luôn thành công trên class loader bất kỳ.”** Không chắc; common-superclass lookup có thể không thấy types trong loader/module thực tế.

**“Agent loaded nghĩa là instrumentation đúng.”** Không đúng; class đã nạp, matcher, helper visibility và behavior còn cần kiểm chứng.

**“Chỉ cần test một agent một mình.”** Không đủ nếu production có nhiều transformers.

**“Các file trong `target/classes` chính là final artifact.”** Không chắc sau shading/repackaging/instrumentation.

**“Một JAR có đúng tên dependency thì chắc chắn là đúng version.”** Không đúng; cần resolved version, checksum, class loader và deployment evidence.

**“Class loader trùng tên class nên type identity trùng.”** Không đúng; defining loader là một phần của runtime identity.

**“Tắt coverage/APM giúp build xanh là migration đã xong.”** Không đúng nếu đó là quality/operational gate bắt buộc.

**“Lỗi xảy ra khi gọi chức năng mới nên chắc chắn chức năng mới viết sai.”** Không chắc; có thể chỉ đến thời điểm ấy JVM mới nạp class và phát hiện bytes từ một transformer cũ.

## 44. Checklist trước khi chốt hướng sửa

- [ ] Đã lưu đầy đủ error đầu tiên, `Caused by` và stack trace.
- [ ] Đã xác định chính xác error subtype: VerifyError, ClassFormatError, NoClassDefFoundError, v.v.
- [ ] Đã ghi JDK vendor/build, OS/architecture, artifact và JVM flags thực.
- [ ] Đã xác định class-file major/minor của class lỗi.
- [ ] Đã xác định class/JAR/module/loader thực tế chứa bytes được nạp.
- [ ] Đã kiểm tra API method/field descriptors nếu là linkage error.
- [ ] Đã tìm initialization cause nếu thấy `Could not initialize class`.
- [ ] Đã rà soát classpath/module path, BOM và dependency resolution.
- [ ] Đã kiểm tra shading, fat JAR và MRJAR branch selection nếu có.
- [ ] Đã kiểm kê tất cả Java/native agents và bytecode transformers.
- [ ] Đã phân biệt lỗi JVM verifier với lỗi ASM/Byte Buddy parser.
- [ ] Đã xem `bci`, stack state, branch targets, exception handlers và `StackMapTable` nếu là VerifyError.
- [ ] Đã kiểm tra `max_stack`/`max_locals` và constructor constraints khi sửa transformer.
- [ ] Đã xem helper class visibility, class-loader và module access.
- [ ] Đã kiểm tra tool/agent version được vendor hỗ trợ trên JDK đích.
- [ ] Đã xác nhận original và transformed bytes không bị nhầm lẫn.
- [ ] Không dùng `-noverify` hoặc nới module/security policy vô điều kiện.
- [ ] Đã thử tái hiện trên staging với/không với từng agent nếu được phép.
- [ ] Đã chạy regression tests trên artifact cuối và runtime image thật.
- [ ] Đã kiểm tra observability/coverage và performance sau sửa.
- [ ] Incident report có artifact hash, owner, bằng chứng và quyết định phát hành.

## 45. Tài liệu nên đối chiếu

Khi cần xử lý một JVM hoặc bytecode library cụ thể, ưu tiên tài liệu theo **đúng release**:

- **Java Virtual Machine Specification**, các chương về class-file format, verification, loading/linking/initialization và `invokedynamic`.
- **Java SE API — `java.lang.VerifyError`, `LinkageError`, `ClassFormatError`, `NoClassDefFoundError`, `ClassNotFoundException`**.
- **Java Instrumentation API — `Instrumentation` và `ClassFileTransformer`**, cùng Java agent manifest specification.
- **ASM User Guide và release notes** về `ClassReader`, `ClassWriter`, `COMPUTE_FRAMES`, `CheckClassAdapter` và class-file version support.
- **Byte Buddy documentation/release notes** về agent, Advice, redefinition và supported JDK versions.
- **JaCoCo, Mockito, APM vendor documentation** về test/coverage instrumentation và JVM/bytecode compatibility.
- **`javap`, `jdeps`, `jar` và `java` tool guides** để xem bytes, dependencies, MRJAR variants và class-loading diagnostics.
- **JPMS documentation** về `requires`, `exports`, `opens` và module access.
- **Gradle/Maven compiler, toolchains, shading và test plugin docs** để xác định output thực tế trong pipeline.
- **OpenJDK JEP 451** nếu incident liên quan dynamic agent loading trên JDK 21 trở đi, không nhầm với verification.

Mọi quy tắc về JVM flags, diagnostic tags và bytecode parser versions có thể thay đổi theo JDK hoặc thư viện. Bản fix cần được xác nhận trong **tổ hợp phiên bản được triển khai thực**, không chỉ trong ví dụ từ một tài liệu cũ.

## 46. Kết luận

**`VerifyError` là tín hiệu verifier từ chối bytecode**, còn lỗi nạp lớp, method/field linkage, class initialization, module access và bytecode parser thường phản ánh những tầng khác nhau của JVM và tooling. Các lỗi có thể xuất hiện cùng thời điểm trong Java Advance Compatibility Migration, đặc biệt khi nâng JDK kèm ASM/Byte Buddy, Java agent, mocking/coverage tool, code generator hoặc build-time enhancer.

Để chẩn đoán đúng, hãy bắt đầu bằng **lỗi đầu tiên và class thực sự được nạp**, rồi đối chiếu class-file version, method descriptors, operand stack, local variables, control flow và `StackMapTable` khi cần. Nếu code đã được transform, phân tích bytes cuối cùng và toàn bộ transformer pipeline; nếu class/method thiếu, điều tra dependency resolution, shading, loader và module boundaries; nếu parser không hiểu Java release mới, nâng đúng tool theo support policy.

Không bỏ qua bytecode verification để “cho ứng dụng chạy”. Một migration an toàn phải chứng minh **artifact cuối cùng nạp được trên JVM đích, instrumentation hoạt động đúng, dữ liệu/hành vi không hồi quy và các test/quality gates còn hiệu lực**. Khi lỗi được sửa ở đúng tầng và có thể tái hiện bằng cùng JDK, JAR, agent và runtime image, việc nâng Java mới có cơ sở vận hành tin cậy.
