# Vai trò của java.lang.classfile trong phân tích, sinh và biến đổi bytecode

## Class-File API giải quyết bài toán gì?

Sau khi biên dịch, mã Java được lưu trong các file `.class`. Mỗi file class chứa cấu trúc nhị phân theo JVM Specification, gồm phiên bản class file, constant pool, thông tin class, fields, methods và attributes. Phần thân phương thức chứa các lệnh bytecode mà JVM thực thi.

Khi viết công cụ phân tích hoặc thay đổi bytecode, việc tự đọc và ghi định dạng nhị phân này rất phức tạp. Công cụ phải xử lý chỉ số constant pool, độ dài attribute, offset của lệnh nhảy, stack map, phiên bản class file và nhiều chi tiết khác.

Class-File API trong package `java.lang.classfile` cung cấp một mô hình Java có cấu trúc để:

- **Phân tích (parsing):** đọc file `.class`, duyệt metadata, fields, methods, attributes và bytecode.
- **Sinh (generation):** tạo file `.class` mới bằng builder và các lệnh bytecode có kiểu rõ ràng.
- **Biến đổi (transformation):** đọc class hiện có, giữ lại phần không đổi, xóa hoặc thay thế những thành phần cần chỉnh sửa rồi ghi thành class file mới.

API này thuộc module `java.base`, nên không cần thêm thư viện bên ngoài chỉ để thực hiện các tác vụ class-file cơ bản.

Các package liên quan được chia theo nội dung:

- `java.lang.classfile`: model, builder, transform và các API điều phối chính.
- `java.lang.classfile.attribute`: biểu diễn các attribute của class file.
- `java.lang.classfile.constantpool`: biểu diễn các entry trong constant pool.
- `java.lang.classfile.instruction`: biểu diễn các instruction và pseudo-instruction trong method body.

## Lộ trình từ Java 22 tới API chính thức

| Phiên bản | JEP | Trạng thái | Ý nghĩa |
|---|---|---|---|
| JDK 22 | JEP 457 – Class-File API | Preview lần đầu | Giới thiệu API chuẩn hóa để đọc, ghi và biến đổi class file. |
| JDK 23 | JEP 466 – Class-File API (Second Preview) | Preview lần hai | Tiếp tục hoàn thiện API trước khi đưa vào nền tảng. |
| JDK 24 | JEP 484 – Class-File API | Chính thức | API được hoàn thiện và trở thành API chuẩn của Java SE. |
| JDK 25–27 | API trong `java.lang.classfile` | API chuẩn | Tiếp tục được duy trì và mở rộng cùng các phiên bản class file mới. |

Vì vậy, khi xây dựng công cụ hiện đại, hãy dùng API chính thức từ JDK 24 trở lên. Trong JDK 22 và 23, Class-File API còn là preview; cú pháp preview từ hai phiên bản đó không phải nền tảng phù hợp cho mã mới cần duy trì lâu dài.

## Ba nhóm abstraction cốt lõi

Class-File API được thiết kế quanh ba nhóm abstraction: model/element, builder và transform.

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| Model và element | Biểu diễn nội dung class file để đọc và duyệt | `ClassModel`, `MethodModel`, `CodeModel`, `InvokeInstruction` |
| Builder | Xây dựng cấu trúc class file và bytecode mới | `ClassBuilder`, `MethodBuilder`, `CodeBuilder` |
| Transform | Chọn lọc, giữ, bỏ hoặc thay thế các element khi tạo class mới | `ClassTransform`, `MethodTransform`, `CodeTransform` |

Các model và element là đối tượng bất biến. Chúng được nạp dữ liệu theo nhu cầu (lazy), nghĩa là API không cần phân tích toàn bộ nội dung ngay khi tạo model. Cách này giúp công cụ chỉ đọc những phần thật sự cần thiết.

Một model có thể được duyệt bằng accessor như `ClassModel.methods()`, hoặc như một chuỗi element. Ví dụ, `ClassModel` chứa các element ở cấp class; `MethodModel` chứa các element ở cấp method; `CodeModel` biểu diễn phần thân phương thức và các lệnh bytecode.

## ClassFile là điểm vào chính

`ClassFile` là context điều khiển việc đọc, sinh và biến đổi class file. Tạo context mặc định bằng:

~~~java
import java.lang.classfile.ClassFile;

ClassFile classFile = ClassFile.of();
~~~

Có thể dùng các phương thức chính sau:

| Phương thức | Mục đích |
|---|---|
| `ClassFile.of()` | Tạo context với các tùy chọn mặc định. |
| `parse(byte[])` | Đọc dữ liệu nhị phân thành `ClassModel`. |
| `parse(Path)` | Đọc class file trực tiếp từ đường dẫn. |
| `build(ClassDesc, Consumer)` | Sinh class file mới thành `byte[]`. |
| `buildTo(Path, ClassDesc, Consumer)` | Sinh class file trực tiếp ra file. |
| `transformClass(ClassModel, ClassTransform)` | Biến đổi model thành class file mới. |
| `verify(byte[])` / `verify(ClassModel)` | Kiểm tra class file và trả về danh sách lỗi xác minh. |

`ClassFile.of(options...)` cho phép điều chỉnh cách xử lý attribute, debug information, stack map, constant pool và một số khía cạnh khác. Hãy dùng tùy chọn khi có yêu cầu cụ thể; cấu hình mặc định phù hợp với nhiều tác vụ thông thường.

## Phân tích class file

### Đọc metadata, field và method

Dùng `ClassFile.parse` để chuyển file nhị phân thành `ClassModel`. Từ model, có thể lấy phiên bản class file, flags, superclass, interfaces, fields, methods và attributes.

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.FieldModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public class InspectClass {
    public static void main(String[] args) throws Exception {
        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(Path.of(args[0]));

        System.out.println("Major version: " + model.majorVersion());
        System.out.println("Minor version: " + model.minorVersion());
        System.out.println("Fields:");

        for (FieldModel field : model.fields()) {
            System.out.println("  " + field.fieldName().stringValue());
        }

        System.out.println("Methods:");

        for (MethodModel method : model.methods()) {
            System.out.println(
                "  " + method.methodName().stringValue()
                    + method.methodType().stringValue()
            );
        }
    }
}
~~~

Ví dụ này hữu ích khi xây dựng:

- Công cụ liệt kê API công khai của thư viện.
- Báo cáo class file được biên dịch từ phiên bản Java nào.
- Công cụ kiểm tra class có method hoặc field theo quy ước hay không.
- Bộ phân tích cấu trúc class trước khi đóng gói hoặc triển khai.

`MethodModel.code()` trả về `Optional<CodeModel>`. Một method trừu tượng hoặc native có thể không có phần thân bytecode, vì vậy cần xử lý trường hợp không có code.

### Phân tích lệnh gọi và dependency

Một công cụ có thể duyệt các lệnh trong `CodeModel` để tìm class mà method đang gọi. Ví dụ, tìm các lệnh gọi method và in tên class sở hữu method đó:

~~~java
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.InvokeInstruction;

for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        for (CodeElement element : code) {
            if (element instanceof InvokeInstruction invocation) {
                System.out.println(
                    method.methodName().stringValue()
                        + " calls "
                        + invocation.owner().asInternalName()
                        + "."
                        + invocation.name().stringValue()
                );
            }
        }
    });
}
~~~

Có thể mở rộng cách duyệt này để:

- Tạo đồ thị dependency giữa các class.
- Tìm nơi gọi một API cụ thể.
- Phát hiện việc sử dụng một method đã bị cấm trong dự án.
- Phân tích lời gọi reflection, `invokedynamic`, truy cập field hoặc thao tác tạo object.
- Tạo báo cáo bytecode cho công cụ tối ưu hoặc kiểm tra bảo mật.

`CodeModel` giữ thứ tự các element vì thứ tự lệnh bytecode có ý nghĩa khi JVM thực thi. Khi phân tích, hãy phân biệt instruction thật với pseudo-instruction dùng cho metadata như line number hoặc local variable.

## Sinh class file mới

### ClassBuilder và CodeBuilder

Sinh class file bằng `ClassFile.build` hoặc `buildTo`. API cung cấp builder cho từng cấp cấu trúc:

- `ClassBuilder`: flags, superclass, interfaces, fields và methods.
- `MethodBuilder`: flags, descriptor và attributes của method.
- `CodeBuilder`: các lệnh bytecode, label, exception handler và metadata của code.

Ví dụ tạo một class có method static `answer()` trả về số nguyên 42:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public class GenerateClass {
    public static void main(String[] args) throws Exception {
        ClassFile classFile = ClassFile.of();

        byte[] bytes = classFile.build(
            ClassDesc.of("example", "GeneratedAnswer"),
            builder -> builder
                .withVersion(ClassFile.JAVA_24_VERSION, 0)
                .withFlags(ClassFile.ACC_PUBLIC | ClassFile.ACC_SUPER)
                .withSuperclass(ClassDesc.of("java.lang.Object"))
                .withMethodBody(
                    "answer",
                    MethodTypeDesc.of(ConstantDescs.CD_int),
                    ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                    code -> code.ldc(42).ireturn()
                )
        );

        Path output = Path.of("out/example/GeneratedAnswer.class");
        Files.createDirectories(output.getParent());
        Files.write(output, bytes);
    }
}
~~~

Trong ví dụ:

1. `ClassDesc` mô tả tên class bằng dạng symbolic descriptor.
2. `withVersion` đặt major version 68, tương ứng class file của Java 24, để class được tạo có thể chạy trên Java 24 trở lên.
3. `withFlags` đặt class là public và có cờ `ACC_SUPER`.
4. `withSuperclass` khai báo `java.lang.Object`.
5. `withMethodBody` tạo method `answer()I`, nghĩa là không có tham số và trả về `int`.
6. `ldc(42)` đẩy hằng số 42 lên operand stack; `ireturn()` trả về giá trị đó.

Nếu muốn sinh class tương thích với một phiên bản JVM cụ thể, cần chọn major/minor version phù hợp và chỉ dùng các cấu trúc, instruction mà phiên bản đó hỗ trợ. Không nên mặc định class file được tạo bởi JDK mới sẽ chạy trên runtime cũ hơn.

### Vì sao CodeBuilder hữu ích?

`CodeBuilder` cung cấp phương thức có tên theo mnemonic của JVM instruction, chẳng hạn:

| Phương thức | Bytecode tương ứng | Tác dụng |
|---|---|---|
| `aload(0)` | `aload_0` hoặc dạng tương ứng | Đưa reference từ local variable lên stack. |
| `ldc(value)` | `ldc` / dạng wide khi cần | Nạp hằng số từ constant pool. |
| `invokevirtual(...)` | `invokevirtual` | Gọi instance method. |
| `invokestatic(...)` | `invokestatic` | Gọi static method. |
| `ireturn()` | `ireturn` | Trả về giá trị int. |
| `return_()` | `return` | Kết thúc method void. |

CodeBuilder xử lý nhiều chi tiết biểu diễn bytecode như chọn dạng instruction, quản lý label và hỗ trợ tạo stack map theo tùy chọn. Thứ tự gọi các phương thức trên builder là thứ tự instruction trong method.

## Biến đổi class file hiện có

### ClassTransform: giữ, bỏ hoặc thay element

Một tác vụ phổ biến là đọc class, xóa một nhóm method rồi ghi ra class file mới. Ví dụ, loại bỏ các method nội bộ có tên bắt đầu bằng `debug`:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;
import java.nio.file.Files;
import java.nio.file.Path;

ClassFile classFile = ClassFile.of();

ClassModel original = classFile.parse(Path.of("Service.class"));

ClassTransform removeDebugMethods = ClassTransform.dropping(
    element -> element instanceof MethodModel method
        && method.methodName().stringValue().startsWith("debug")
);

byte[] transformed =
    classFile.transformClass(original, removeDebugMethods);

Files.write(Path.of("Service-transformed.class"), transformed);
~~~

`ClassTransform.dropping(predicate)` chuyển tiếp các element còn lại và bỏ những element thỏa predicate. Nếu cần logic phức tạp hơn, có thể tự viết transform để gọi `builder.with(element)`, bỏ element hoặc thêm element thay thế.

Chỉ xóa method khi đã xác định không còn mã nào cần gọi method đó, hoặc khi đây là một thay đổi API có chủ đích. Xóa một method vẫn đang được class khác tham chiếu có thể gây lỗi liên kết khi chương trình chạy.

### CodeTransform: thay đổi instruction trong method

Có thể biến đổi sâu hơn ở cấp bytecode. Ví dụ, chuyển các lệnh gọi static từ `example/OldLogger` sang `example/NewLogger`, giữ nguyên tên và descriptor method:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.constant.ClassDesc;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.classfile.instruction.Opcode;
import java.nio.file.Path;

ClassFile classFile = ClassFile.of();
ClassModel original = classFile.parse(Path.of("Service.class"));

CodeTransform redirectLoggerCalls = (builder, element) -> {
    if (element instanceof InvokeInstruction invocation
            && invocation.opcode() == Opcode.INVOKESTATIC
            && invocation.owner().asInternalName()
                .equals("example/OldLogger")) {

        builder.invokestatic(
            ClassDesc.of("example", "NewLogger"),
            invocation.name().stringValue(),
            invocation.typeSymbol(),
            invocation.isInterface()
        );
    } else {
        builder.with(element);
    }
};

ClassTransform transformMethods =
    ClassTransform.transformingMethodBodies(redirectLoggerCalls);

byte[] rewritten =
    classFile.transformClass(original, transformMethods);
~~~

Việc đổi owner chỉ đúng khi `example/NewLogger` có method static cùng tên và descriptor tương thích với method gốc. Transform thay đổi instruction; nó không tự tạo class logger đích hoặc kiểm tra logic nghiệp vụ của method thay thế.

Trong ví dụ này:

- `CodeTransform` nhận từng `CodeElement` và một `CodeBuilder`.
- Khi gặp lệnh `invokestatic` gọi class cũ, transform tạo instruction mới gọi class thay thế.
- Các element không liên quan được chuyển tiếp bằng `builder.with(element)`.
- `ClassTransform.transformingMethodBodies` áp dụng code transform vào phần thân các method và giữ các element khác.

Có thể kết hợp nhiều transform bằng `andThen`. Ví dụ, một transform đổi owner của method call có thể chạy trước transform thêm logging. Nhờ cùng mô hình builder/element, transform cấp code có thể được nâng lên cấp method hoặc class.

## Class-File API hỗ trợ công cụ như thế nào?

| Loại công cụ | Cách sử dụng API | Kết quả |
|---|---|---|
| Static analyzer | Parse model, duyệt fields, methods, attributes và instructions | Báo cáo cấu trúc, dependency và quy tắc bytecode |
| Code generator | Dùng ClassBuilder, MethodBuilder, CodeBuilder | Sinh class file từ metadata hoặc cấu hình |
| Bytecode instrumentation | Dùng CodeTransform và ClassTransform | Chèn logging, tracing, metrics hoặc kiểm tra |
| Framework proxy / adapter | Sinh hoặc biến đổi class theo interface và method descriptor | Tạo implementation ở runtime hoặc build time |
| Migration tool | Tìm và thay các invocation hoặc cấu trúc bytecode cụ thể | Chuyển đổi class theo quy tắc migration |
| Build-time optimizer | Phân tích và biến đổi các phần class cần thiết | Tạo artifact đã xử lý trước khi chạy |

API cũng có thể được sử dụng trong Java agent, compiler, framework hoặc công cụ build. Lựa chọn thời điểm xử lý phụ thuộc mục tiêu: phân tích khi build để phát hiện lỗi sớm, sinh class khi chạy để tạo implementation linh hoạt, hoặc biến đổi class trước khi JVM nạp nó.

## Constant pool, attributes và các tùy chọn

### Constant pool

Constant pool chứa các biểu diễn symbolic mà bytecode tham chiếu tới, chẳng hạn tên class, tên method, descriptor, string literal và method handle.

`ClassModel.constantPool()` cung cấp góc nhìn chỉ đọc. Khi sinh hoặc biến đổi class, `ClassBuilder` cung cấp `ConstantPoolBuilder` để thêm các entry cần thiết. Trong các tác vụ thông thường, hãy để builder quản lý chỉ số constant pool thay vì tự chỉnh sửa byte offset hoặc index nhị phân.

Khi biến đổi một class, API mặc định có thể chia sẻ constant pool gốc để tránh phải phân tích và ghi lại những phần không thay đổi. Có thể điều chỉnh bằng `ClassFile.ConstantPoolSharingOption` khi có lý do cụ thể, ví dụ muốn loại bỏ nhiều entry không còn được tham chiếu.

### Attributes

Attribute có thể xuất hiện ở class, field, method và code. Các attribute tiêu chuẩn có model riêng trong package `java.lang.classfile.attribute`. Attribute không nhận diện được có thể được biểu diễn dưới dạng `UnknownAttribute`; với định dạng custom, có thể đăng ký `AttributeMapper` qua tùy chọn của `ClassFile`.

Nếu công cụ cần bảo toàn custom attribute, cần cấu hình mapper phù hợp. Nếu chỉ quan tâm metadata tiêu chuẩn, các mapper dựng sẵn thường đã đủ.

### Tùy chọn xử lý

`ClassFile.of(ClassFile.Option...)` cho phép cấu hình:

- Cách xử lý attribute gốc hoặc attribute không thể xác minh sau transform.
- Resolver cho class hierarchy khi tạo stack map.
- Có chia sẻ constant pool từ class gốc hay không.
- Cách xử lý dead code, dead label và short jump.
- Có duyệt debug element và line number hay không.
- Cách sinh stack map.

Các tùy chọn này quan trọng với công cụ chuyên sâu, nhưng không cần thiết phải cấu hình lại trong mọi ứng dụng. Hãy giữ mặc định nếu chưa có yêu cầu rõ ràng về hiệu năng, tính tương thích hoặc nội dung class file.

## Xác minh class file sau khi sinh hoặc biến đổi

Builder kiểm tra nhiều điều kiện biểu diễn, ví dụ giá trị có vừa kiểu dữ liệu trong định dạng class file hay không. Tuy nhiên, API không tự thực hiện mọi kiểm tra nhất quán về ngữ nghĩa khi build hoặc transform. Một chuỗi instruction sai hoặc label không được liên kết đúng vẫn có thể khiến quá trình build thất bại hoặc tạo class không hợp lệ.

Có thể yêu cầu API xác minh class file:

~~~java
import java.util.List;

List<VerifyError> errors = classFile.verify(transformed);

if (!errors.isEmpty()) {
    throw new IllegalStateException(
        "Class file không hợp lệ: " + errors
    );
}
~~~

Ngoài xác minh, công cụ nên:

1. Kiểm tra class file output được tạo đúng đường dẫn và đúng phiên bản.
2. Nạp class trong môi trường kiểm thử tương ứng nếu mục tiêu là chạy trên JVM.
3. Chạy test cho các method đã được biến đổi.
4. Kiểm tra attribute và metadata cần bảo toàn.
5. Đảm bảo transform xử lý element không biết đến theo cách có chủ đích.

Nếu transform chỉ quan tâm một nhóm instruction, hãy giữ các element khác bằng `builder.with(element)`. Nếu transform phải hiểu và xử lý mọi instruction, cần có chiến lược rõ ràng khi gặp element mới mà JDK tương lai bổ sung. Đừng âm thầm bỏ những thành phần mà công cụ chưa hiểu.

## Những giới hạn cần hiểu đúng

- Class-File API thao tác với file `.class` và cấu trúc bytecode; nó không phải API biên dịch mã nguồn Java.
- API không thực thi bytecode. Việc sinh được một class file không đồng nghĩa chương trình trong đó có logic đúng.
- Model được phân tích lazy; thao tác truy cập sâu có thể phát hiện lỗi định dạng muộn hơn. Model cũng không được bảo đảm thread-safe.
- Do phân tích lazy, accessor có thể ném `IllegalArgumentException` khi phát hiện class file bị malformed ở phần dữ liệu đang được đọc.
- Việc build hoặc transform không thay thế bước xác minh, kiểm thử và kiểm tra khả năng liên kết class.
- Thay đổi method descriptor, field descriptor, invocation hoặc class hierarchy có thể làm hỏng tương thích nhị phân với mã đã biên dịch khác.
- Khi xử lý class file từ nguồn không tin cậy, cần xem lỗi parse và giới hạn tài nguyên là một phần của thiết kế công cụ.

## Chọn abstraction theo công việc

| Công việc | Thành phần chính |
|---|---|
| Đọc metadata class | `ClassFile.parse`, `ClassModel` |
| Duyệt field và method | `FieldModel`, `MethodModel` |
| Phân tích instruction | `CodeModel`, `CodeElement`, `Instruction` |
| Sinh class mới | `ClassFile.build`, `ClassBuilder` |
| Sinh method | `MethodBuilder` |
| Sinh bytecode | `CodeBuilder` |
| Bỏ hoặc thay thành phần class | `ClassTransform` |
| Biến đổi method | `MethodTransform` |
| Biến đổi instruction | `CodeTransform` |
| Xác minh kết quả | `ClassFile.verify` |

## Phiên bản Java cần dùng

- JDK 22 giới thiệu Class-File API dưới dạng preview theo JEP 457.
- JDK 23 tiếp tục preview theo JEP 466.
- JDK 24 hoàn thiện API theo JEP 484; đây là phiên bản đầu tiên có API chính thức.
- Dùng JDK 24 trở lên cho các ví dụ và ứng dụng mới dựa trên API chuẩn.
- Với API chính thức từ JDK 24 trở lên, không cần bật `--enable-preview`.
- Tài liệu Java SE 27 tiếp tục ghi các abstraction cốt lõi như `ClassFile`, `ClassModel`, `ClassBuilder`, `ClassTransform` và `CodeModel` có từ phiên bản 24.

## Tài liệu tham khảo

- [JEP 457 – Class-File API (Preview trong JDK 22)](https://openjdk.org/jeps/457)
- [JEP 466 – Class-File API (Second Preview trong JDK 23)](https://openjdk.org/jeps/466)
- [JEP 484 – Class-File API (Final trong JDK 24)](https://openjdk.org/jeps/484)
- [Package java.lang.classfile – Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html)
- [ClassFile – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [ClassModel – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassModel.html)
- [ClassBuilder – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassBuilder.html)
- [ClassTransform – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [CodeModel – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeModel.html)
- [CodeBuilder – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [CodeTransform – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeTransform.html)

