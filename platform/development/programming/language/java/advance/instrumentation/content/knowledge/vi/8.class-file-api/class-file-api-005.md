# ClassBuilder, MethodBuilder, CodeBuilder và cách giữ lại phần không thay đổi

**Java Class-File API** (gói `java.lang.classfile`) cho phép đọc, tạo và biến đổi file `.class` mà không phải tự xử lý thủ công từng offset trong constant pool hoặc bytecode. Khi instrument Java, thao tác thường gặp không phải xây dựng lại toàn bộ class từ đầu, mà là **chỉ thay một ít phần tử và chuyển tiếp tất cả phần tử còn lại**.

Trọng tâm của bài này là ba tầng builder:

- `ClassBuilder` xây dựng **class file** từ các `ClassElement`: method, field, thuộc tính của class và các phần tử liên quan.
- `MethodBuilder` xây dựng **một method** từ các `MethodElement`, đặc biệt là `CodeModel` và các thuộc tính của method.
- `CodeBuilder` xây dựng **thân bytecode** từ `CodeElement`: JVM instructions, labels và những phần tử metadata biểu diễn ở cấp code.

Bí quyết giữ lại phần không đổi là: **ở mỗi cấp, gọi `builder.with(element)` cho các phần tử không cần sửa**. Chỉ đi vào cấp sâu hơn bằng `transformMethod(...)` và `transformCode(...)` khi thực sự muốn thay method hoặc instruction cụ thể.

> **Yêu cầu phiên bản:** Class-File API trở thành API chính thức trong **JDK 24** (JEP 484). Các ví dụ Java chạy trực tiếp bằng `javac` và `java` của **JDK 24 trở lên**, **không cần `--enable-preview`**. JDK 17/21 không có API ổn định này; không được sao chép ví dụ sang JDK 17 rồi kỳ vọng nó biên dịch. Các bản preview JDK 22/23 có thể khác chữ ký.

## 1. Mô hình tư duy: đọc Model, đưa Element vào Builder

Một file class có cấu trúc lồng nhau:

~~~text
Class file (ClassModel)
  |-- class metadata / attributes (ClassElement)
  |-- field (FieldModel, cũng là ClassElement)
  |-- method (MethodModel, cũng là ClassElement)
  |      |-- method metadata / attributes (MethodElement)
  |      |-- body (CodeModel, cũng là MethodElement)
  |               |-- instruction (CodeElement)
  |               |-- label, line info và code metadata (CodeElement)
  |-- các class-level elements khác
~~~

Các model là một **cách nhìn bất biến** (*immutable view*) của class file; việc parse thường **lazy**, nên một số lỗi định dạng có thể xuất hiện khi truy cập sâu vào model. Các builder không phải đối tượng để tùy ý giữ làm trạng thái chia sẻ lâu dài: thông thường API trao builder cho một callback của `build` hoặc `transformClass` và ta phát phần tử vào builder trong callback đó.

| Cấp | Model | Loại phần tử | Builder | Transform |
| --- | --- | --- | --- | --- |
| Class | `ClassModel` | `ClassElement` | `ClassBuilder` | `ClassTransform` |
| Method | `MethodModel` | `MethodElement` | `MethodBuilder` | `MethodTransform` |
| Code | `CodeModel` | `CodeElement` | `CodeBuilder` | `CodeTransform` |
| Field | `FieldModel` | `FieldElement` | `FieldBuilder` | `FieldTransform` |

Luồng đọc và biến đổi tối thiểu:

~~~java
ClassFile api = ClassFile.of();
ClassModel oldClass = api.parse(originalBytes);
byte[] newBytes = api.transformClass(oldClass,
        (classBuilder, element) -> classBuilder.with(element));
~~~

Đoạn trên là **mảnh mã**, yêu cầu biến `originalBytes` đã có kiểu `byte[]`. Nó phát **mọi class element** vào `ClassBuilder` để tái tạo một định nghĩa class tương đương về mặt mô hình. Nó **không bảo đảm `Arrays.equals(originalBytes, newBytes)`**: cách sắp xếp constant pool, cấu trúc biểu diễn, stack maps hoặc attributes có thể được xử lý theo tùy chọn của API.

## 2. ClassBuilder: giữ class, field, method và thuộc tính không đổi

`ClassBuilder` có hai nhóm thao tác quan trọng:

1. **Thêm/tạo** thành phần mới: `withField(...)`, `withMethod(...)`, `withMethodBody(...)`, `withFlags(...)`, `withSuperclass(...)`, v.v.
2. **Chuyển tiếp hoặc biến đổi** thành phần của class gốc: `with(ClassElement)`, `transformField(FieldModel, FieldTransform)`, `transformMethod(MethodModel, MethodTransform)`.

Khi đọc một `ClassModel`, nếu chỉ có **một** method cần sửa thì mô hình an toàn là:

~~~java
ClassTransform transform = (classBuilder, classElement) -> {
    if (classElement instanceof MethodModel method
            && method.methodName().stringValue().equals("compute")) {
        classBuilder.transformMethod(method, methodTransform);
    } else {
        classBuilder.with(classElement);
    }
};
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập; `methodTransform` phải được tạo trước. Nó có nghĩa:

- Nếu đúng method `compute`, mở method đó bằng `MethodBuilder` và áp dụng một biến đổi cấp method.
- Nếu là field, constructor, method khác, class attribute, version hoặc phần tử khác, **chuyển tiếp nguyên phần tử về mặt mô hình** bằng `with(classElement)`.
- Đừng chỉ viết nhánh `if (đúng method) ...` rồi bỏ nhánh `else`: trong cách biến đổi *element stream*, **không phát phần tử vào builder nghĩa là bỏ phần tử đó** khỏi đầu ra.

### Vì sao nên dùng transformClass thay vì build lại từ đầu?

`ClassFile.build(ClassDesc, Consumer<ClassBuilder>)` tạo một class bằng các phần tử bạn tự cung cấp; phù hợp với code generation. Trong khi đó, `ClassFile.transformClass(ClassModel, ClassTransform)` lấy **class cũ làm nguồn**, thuận tiện cho phép biến đổi cục bộ. Lựa chọn thứ hai cũng có thể tận dụng **constant pool của class gốc** để giữ và tối ưu xử lý những phần không đổi.

Nếu tự `build` lại toàn bộ class nhưng quên đưa constructor, annotation, generic signature, field, interface hoặc attribute vào builder thì chúng có thể **biến mất khỏi class file mới**. Khi instrumentation yêu cầu giữ nguyên public API, đó là lỗi nghiêm trọng.

## 3. MethodBuilder: chỉ đi sâu vào method cần sửa

Một `MethodModel` gồm nhiều phần tử cấp method; `CodeModel` chỉ là **một trong các phần tử đó**. `MethodBuilder` hỗ trợ:

| API | Tác dụng |
| --- | --- |
| `with(MethodElement)` | Đưa phần tử method không đổi vào method mới |
| `withFlags(...)` | Thiết lập access flags (có giới hạn về `ACC_STATIC`) |
| `withCode(Consumer<CodeBuilder>)` | Sinh thân method mới |
| `transformCode(CodeModel, CodeTransform)` | Biến đổi thân code **đã tồn tại** và giữ các phần code không sửa |

Mẫu xử lý:

~~~java
MethodTransform methodTransform = (methodBuilder, methodElement) -> {
    if (methodElement instanceof CodeModel code) {
        methodBuilder.transformCode(code, codeTransform);
    } else {
        methodBuilder.with(methodElement);
    }
};
~~~

Đây cũng là **mảnh mã**, cần một `CodeTransform codeTransform`. Nếu method có annotation, attribute hoặc metadata khác ở cấp method, nhánh `else` giúp chuyển tiếp chúng. Nếu method có `CodeModel`, gọi `transformCode` để không phải tự tái tạo toàn bộ các instruction và label.

**Lưu ý về flags:** Khi tạo method từ class gốc, `ClassBuilder.transformMethod(method, transform)` lấy tên, descriptor và flags từ method nguồn. `ACC_STATIC` của method không thể được đổi tùy tiện sau khi `MethodBuilder` đã được tạo; API áp đặt giới hạn đó. Khi tạo một method mới với `withMethod(...)`, truyền đúng flags ngay từ đầu.

### withMethod, withMethodBody và transformMethod khác nhau

- `withMethod(name, descriptor, flags, handler)`: tạo method mới và cho handler truy cập `MethodBuilder` để cấu hình cả method attributes lẫn code.
- `withMethodBody(name, descriptor, flags, codeHandler)`: tiện ích tạo method mới **chỉ cần flags và Code attribute**, không cần custom method attributes.
- `transformMethod(originalMethod, transform)`: xây dựng method mới từ **method nguồn**, có thể giữ nguyên mọi method element không được nhắm tới.

Đừng dùng `withMethodBody` để thay thế toàn bộ một method có sẵn nếu cần giữ annotations, `Exceptions` attribute, signature và metadata khác mà bạn chưa chủ động thêm lại. Trong ví dụ thực hành dưới đây, chúng ta sử dụng `transformMethod` rồi `transformCode` để thay **một** opcode duy nhất.

## 4. CodeBuilder: giữ toàn bộ instruction không liên quan

`CodeModel` biểu diễn thân code của method. Khi duyệt nó, bạn có thể gặp:

- Các JVM instructions thật như `iload`, `iadd`, `isub`, `ireturn`, `invokevirtual`.
- Các phần tử biểu diễn **label, line number, exception handling, local variable metadata**; không được bỏ bừa khi dựng lại method phức tạp.
- Những phần tử metadata gắn với vùng code được Class-File API biểu diễn ở mức thích hợp.

`CodeBuilder` cho phép hai kiểu thao tác:

- `codeBuilder.isub()`, `codeBuilder.iload(0)`, `codeBuilder.ireturn()`: **phát instruction mới**.
- `codeBuilder.with(codeElement)`: **chuyển tiếp code element cũ** mà không viết lại nó.

Ví dụ thay một opcode:

~~~java
CodeTransform replaceAdd = (codeBuilder, element) -> {
    if (element instanceof java.lang.classfile.instruction.OperatorInstruction op
            && op.opcode() == Opcode.IADD) {
        codeBuilder.isub();
    } else {
        codeBuilder.with(element);
    }
};
~~~

Nếu method gốc chứa `iload_1; iload_2; iadd; ireturn`, transform sẽ cho đầu ra tương đương `iload_1; iload_2; isub; ireturn`. Những phần tử khác của `CodeModel` đều được đưa sang builder.

Đây là thay đổi có chủ ý **thay đúng một lệnh số học**, bảo toàn dạng stack của ví dụ; không phải chiến lược instrumentation tổng quát. Trong method thực tế, thay hoặc chèn lệnh có thể ảnh hưởng chiều cao stack, branch targets, stack maps và exception handlers. Phải hiểu quy tắc JVM và kiểm tra class sau biến đổi.

### Bốn cách xử lý một element trong transform

| Hành vi trong callback | Ý nghĩa |
| --- | --- |
| `builder.with(element)` | Giữ phần tử trong mô hình đầu ra |
| Phát một phần tử mới và **không** phát phần tử gốc | Thay phần tử |
| Không phát phần tử nào | Loại bỏ phần tử |
| Phát nhiều phần tử | Một phần tử nguồn có thể trở thành nhiều phần tử đầu ra |

Đó là bản chất *flatMap* của Class-File API. **Không có bảo đảm tự giữ nguyên những phần tử mà callback bỏ qua.** Điều này khác với `ClassFileTransformer.transform(...)` của Java Instrumentation: nếu agent callback trả `null`, JVM hiểu rằng agent **không thay class bytes ở bước đó**. Còn callback của `ClassTransform`/`MethodTransform`/`CodeTransform` phải **chủ động** phát các elements muốn giữ.

## 5. Ví dụ JDK 24+ chạy được: đổi một instruction, giữ field và method khác

Mục tiêu: tạo một class ban đầu có field, constructor, hai method. Sau đó dùng **cả ClassBuilder, MethodBuilder và CodeBuilder** để chỉ sửa method `compute(int,int)`, đổi `iadd` thành `isub`; mọi class element và method/code element khác được chuyển tiếp.

Ví dụ này **xử lý file .class trên đĩa**, chưa attach vào JVM và chưa dùng `java.lang.instrument.Instrumentation`. Nhờ vậy có thể kiểm chứng class trước khi tích hợp vào agent.

### 5.1. Tệp LessonTarget.java

Tạo file `LessonTarget.java`:

~~~java
public class LessonTarget {
    private final int base = 7;

    public int compute(int a, int b) {
        return a + b;
    }

    public int untouched(int x) {
        return base + x;
    }
}
~~~

Class có constructor mặc định công khai, field `base`, method `compute` và method `untouched`. `javac` có thể tối ưu hóa một số cách đọc field `final`, nhưng class vẫn có khai báo field và hai method như trên.

### 5.2. Tệp ClassFileKeepDemo.java

Tạo file `ClassFileKeepDemo.java` cùng thư mục:

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.OperatorInstruction;
import java.lang.reflect.AccessFlag;
import java.nio.file.*;
import java.net.URL;
import java.net.URLClassLoader;

public class ClassFileKeepDemo {
    public static void main(String[] args) throws Exception {
        ClassFile api = ClassFile.of();
        byte[] original = Files.readAllBytes(Path.of("LessonTarget.class"));
        ClassModel model = api.parse(original);

        byte[] updated = api.transformClass(model, (classBuilder, element) -> {
            if (element instanceof MethodModel method
                    && method.methodName().stringValue().equals("compute")) {
                classBuilder.transformMethod(method, (methodBuilder, member) -> {
                    if (member instanceof CodeModel code) {
                        methodBuilder.transformCode(code, (codeBuilder, instruction) -> {
                            if (instruction instanceof OperatorInstruction operation
                                    && operation.opcode() == Opcode.IADD) {
                                codeBuilder.isub();
                            } else {
                                codeBuilder.with(instruction);
                            }
                        });
                    } else {
                        methodBuilder.with(member);
                    }
                });
            } else {
                classBuilder.with(element);
            }
        });

        Path output = Path.of("out");
        Files.createDirectories(output);
        Files.write(output.resolve("LessonTarget.class"), updated);

        System.out.println("sourceMethods=" + model.methods().size());
        System.out.println("rewrittenMethods=" + api.parse(updated).methods().size());
        System.out.println("verifyErrors=" + api.verify(updated).size());

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{output.toUri().toURL()}, null)) {
            Class<?> type = Class.forName("LessonTarget", true, loader);
            Object obj = type.getConstructor().newInstance();
            System.out.println("compute(8,3)="
                    + type.getMethod("compute", int.class, int.class)
                            .invoke(obj, 8, 3));
            System.out.println("untouched(5)="
                    + type.getMethod("untouched", int.class).invoke(obj, 5));
            System.out.println("fieldCount=" + type.getDeclaredFields().length);
        }

        byte[] generated = api.build(
                java.lang.constant.ClassDesc.of("GeneratedOps"),
                builder -> builder.withFlags(AccessFlag.PUBLIC)
                        .withMethodBody("twice",
                                java.lang.constant.MethodTypeDesc.ofDescriptor("(I)I"),
                                ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                                code -> code.iload(0).iconst_2().imul().ireturn()));
        System.out.println("generatedMethods=" + api.parse(generated).methods().size());
    }
}
~~~

**Điểm quyết định trong code:**

1. `ClassFile.of().parse(original)` trả về `ClassModel` để duyệt.
2. `transformClass(model, ...)` cung cấp `ClassBuilder` và lần lượt các `ClassElement`.
3. Chỉ khi phần tử là `MethodModel` tên `compute`, chương trình dùng `classBuilder.transformMethod(...)`. Constructor, field `base`, method `untouched` cùng class-level metadata đều đi qua `classBuilder.with(element)`.
4. Ở tầng `MethodBuilder`, chỉ `CodeModel` được đưa vào `transformCode(...)`; các method elements còn lại đi qua `methodBuilder.with(member)`.
5. Ở tầng `CodeBuilder`, chỉ instruction `IADD` được đổi thành `ISUB`; toàn bộ code elements khác đi qua `codeBuilder.with(instruction)`.
6. `api.verify(updated)` kiểm tra lỗi trong class file. Sau đó một `URLClassLoader` với parent `null` nạp file ở `out/`, tránh tình huống class gốc trên classpath đã được loader ứng dụng nạp trước.
7. Đoạn tạo `GeneratedOps` ở cuối là ví dụ **generation riêng** dùng `ClassBuilder.withMethodBody`/`CodeBuilder`; nó không làm thay đổi `LessonTarget`. Class sinh ra chỉ có một static method và **không có constructor được khai báo**; mục tiêu ở đây chỉ là demo cách builder tạo method mới.

**Ví dụ này chọn method bằng tên** vì `LessonTarget` chỉ có một `compute`. Với class thật có overload, phải lọc cả **method descriptor** (qua `MethodModel.methodTypeSymbol()` hoặc dữ liệu descriptor tương ứng) để tránh biến đổi nhầm method khác cùng tên.

### 5.3. Lệnh chạy

Dùng command line trong thư mục chứa hai tệp, với `javac`/`java` từ **JDK 24+**:

~~~bash
javac LessonTarget.java ClassFileKeepDemo.java
java ClassFileKeepDemo
javap -c -p -classpath out LessonTarget
~~~

Chương trình tự tạo thư mục `out` để lưu `LessonTarget.class` đã biến đổi, **không ghi đè** bản gốc ở thư mục hiện tại. Hãy dùng một thư mục thực hành riêng để không lẫn các file class cũ.

**Stdout chính xác đã biên dịch/chạy trên Zulu OpenJDK 24.0.2:**

~~~text
sourceMethods=3
rewrittenMethods=3
verifyErrors=0
compute(8,3)=5
untouched(5)=12
fieldCount=1
generatedMethods=1
~~~

Vì `compute(8,3)` vốn trả `11`, kết quả `5` chứng minh opcode cộng đã thành trừ. `untouched(5)` vẫn trả `12`, field count vẫn là `1` và số method vẫn là `3` (gồm constructor). `verifyErrors=0` nghĩa là phép kiểm tra của Class-File API không phát hiện lỗi trong output.

Lệnh `javap -c -p -classpath out LessonTarget` phải cho thấy phần thân tương ứng:

~~~text
public int compute(int, int);
  Code:
     0: iload_1
     1: iload_2
     2: isub
     3: ireturn
~~~

Trong khi method `untouched` vẫn có `iadd`. Đây là cách kiểm chứng **điểm sửa có tác dụng đúng nơi cần sửa**, không chỉ nhìn một biến boolean thông báo thành công.

## 6. Giữ nguyên phần không thay đổi chính xác đến mức nào?

Cần phân biệt **giữ nguyên ý nghĩa cấu trúc** và **giữ nguyên byte-for-byte**.

### 6.1. Chuyển tiếp element không đồng nghĩa bản nhị phân giống hệt

`builder.with(element)` chuyển nội dung của element vào cấu trúc class mới. API có thể cần phát lại offset, constant pool index, stack maps và các cấu trúc phụ thuộc vị trí. Kết quả class vẫn có thể tương đương về mặt metadata/hành vi dù chuỗi bytes toàn bộ file khác bản trước.

Bởi vậy:

- Kiểm chứng tên class, superclass/interfaces, fields, methods, flags, attributes cần thiết và bytecode liên quan.
- Không dùng `Arrays.equals(oldBytes, newBytes)` làm điều kiện duy nhất của việc “giữ phần không thay đổi”.
- Với công cụ chữ ký, cache theo hash hoặc phát hành class artifact, phải biết rằng **tạo lại file** có thể thay đổi hash dù hành vi không đổi.
- Không gửi class đã viết lại vào JVM chỉ vì parser đọc thành công; cần kiểm tra bằng `ClassFile.verify` và thực thi/test tương ứng.

### 6.2. Constant pool sharing và tối ưu hóa

Khi gọi `ClassFile.transformClass(...)`, chế độ thông thường là chia sẻ constant pool gốc (tùy chọn `SHARED_POOL` theo mặc định). Điều này cho phép API tận dụng các entry cũ và đôi khi **bulk-copy** methods/attributes không cần biến đổi, thay vì phân tích và sinh lại mọi byte.

Nếu cố loại bỏ rất nhiều thành phần, bạn có thể xem xét tùy chọn `ClassFile.ConstantPoolSharingOption` để tránh giữ nhiều constant pool entry không còn được tham chiếu. Nhưng “không sharing” không có nghĩa mọi phần tử cũ tự động bị xóa; builder vẫn xử lý theo những phần tử transform phát ra.

### 6.3. Attributes, annotations và debug information

Các attributes chuẩn có thể thuộc nhiều cấp:

| Ví dụ | Cấp liên quan | Cách tránh vô tình làm mất |
| --- | --- | --- |
| `Signature`, `RuntimeVisibleAnnotations` | Class, field, method tùy thuộc attribute | Chuyển tiếp element không sửa bằng `with(...)` đúng cấp |
| `Exceptions` | Method | Đừng thay toàn bộ method bằng `withMethodBody` nếu chưa tạo lại attribute |
| `Code` | Method | Dùng `transformCode` khi chỉ đổi instruction |
| Line numbers, local variables | Code model | Không bỏ các code elements tương ứng; kiểm tra options |
| `StackMapTable` | Metadata code có liên kết JVM verifier | Để Class-File API xử lý/generate theo options và xác minh kết quả |
| Custom/unknown attributes | Cấp mà attribute được khai báo | Xem mapper và processing option, kiểm tra khả năng bảo toàn |

API có các tùy chọn xử lý attributes (mặc định `PASS_ALL_ATTRIBUTES`), debug elements (mặc định `PASS_DEBUG`), line numbers (mặc định `PASS_LINE_NUMBERS`) và stack maps (mặc định `STACK_MAPS_WHEN_REQUIRED`) trong JDK 24. Các thuộc tính lạ không được hiểu đầy đủ có thể chứa **chỉ số constant pool hoặc offset bytecode** mà công cụ không biết cách điều chỉnh sau khi sửa. Nếu bảo toàn một custom attribute là yêu cầu bắt buộc, nên dùng `AttributeMapper` tương thích và kiểm tra output bằng công cụ hiểu định dạng đó, thay vì mặc nhiên tin rằng sao chép byte thô sẽ đúng sau mọi phép biến đổi.

## 7. Các API tiện ích để giữ phần không đổi tự động

Nếu không cần điều khiển callback ở ba tầng bằng tay, Class-File API cung cấp các **transform combinators** để “đi sâu” vào phần mong muốn nhưng tự chuyển tiếp những thành phần khác.

### 7.1. Chỉ transform body của method được chọn

Cùng một ý tưởng với ví dụ trên có thể được biểu diễn như sau:

~~~java
CodeTransform changeAdd = (codeBuilder, element) -> {
    if (element instanceof java.lang.classfile.instruction.OperatorInstruction op
            && op.opcode() == Opcode.IADD) {
        codeBuilder.isub();
    } else {
        codeBuilder.with(element);
    }
};

ClassTransform changeOnlyCompute =
        ClassTransform.transformingMethodBodies(
                method -> method.methodName().stringValue().equals("compute"),
                changeAdd);

byte[] result = ClassFile.of().transformClass(model, changeOnlyCompute);
~~~

Đây là **đoạn mã đặt bên trong một chương trình Java có `ClassModel model` và import `java.lang.classfile.*`**, không phải một lớp hoàn chỉnh độc lập. `transformingMethodBodies(predicate, transform)` chỉ transform body của các method khớp predicate và đưa những class/method elements khác qua builder. Với API tiện ích này, trách nhiệm giữ metadata không đổi đã được đóng gói trong combinator.

### 7.2. Lifting ở từng tầng

Có thể chuyển một `CodeTransform` lên cấp method và class:

~~~java
MethodTransform methodTransform = MethodTransform.transformingCode(changeAdd);
ClassTransform classTransform = ClassTransform.transformingMethods(methodTransform);
~~~

Đây là **mảnh code minh họa**, với `changeAdd` đã được định nghĩa ở trên. Cách này biến đổi body của **mọi** method chứa opcode tương ứng nếu không lọc thêm; vì thế không dùng bừa trong production nếu chỉ cần đổi đúng một method.

API còn có `ClassTransform.transformingMethods(predicate, methodTransform)`, `ClassTransform.transformingFields(fieldTransform)` và các overload khác, giúp thu hẹp đúng tầng thay đổi mà không viết lại các nhánh passthrough thủ công.

### 7.3. Kết hợp nhiều transform

Các transform cùng loại có thể nối bằng `andThen(...)`:

~~~java
CodeTransform combined = firstCodeTransform.andThen(secondCodeTransform);
~~~

**Đoạn minh họa** yêu cầu hai biến transform có sẵn. Các elements mà transform thứ nhất phát ra sẽ trở thành input của transform thứ hai, theo thứ tự. Không được tùy tiện đảo hai bước nếu bước thứ hai phụ thuộc kết quả của bước thứ nhất.

Khi xây dựng một Java agent có nhiều bước instrument, hãy làm rõ ở mỗi cấp điều kiện lọc method/instruction và đảm bảo các transformer không vô tình áp dụng lặp cùng một thay đổi.

## 8. Từ Class-File API sang Java Instrumentation

`java.lang.classfile` là thư viện **xử lý bytecode**, còn `java.lang.instrument.ClassFileTransformer` là cơ chế **nhận class bytes từ JVM và trả class bytes mới**. Hai API bổ trợ nhau nhưng không đồng nhất.

Ví dụ mã tư duy trong một implementation của `ClassFileTransformer`:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"com/example/OrderService".equals(className)) {
        return null; // Không thay class bytes ở bước instrumentation này.
    }

    ClassFile api = ClassFile.of();
    ClassModel model = api.parse(classfileBuffer);
    return api.transformClass(model, myClassTransform);
}
~~~

Đoạn này là **mã minh họa cần đặt trong một class triển khai `ClassFileTransformer`**, với `myClassTransform` đã được khởi tạo đúng kiểu `ClassTransform`; bản thân nó **không phải chương trình hoàn chỉnh**.

Phân biệt hai kiểu “giữ nguyên”:

- **Bên trong Class-File API**: `classBuilder.with(element)` / `methodBuilder.with(element)` / `codeBuilder.with(element)` đưa phần tử vào kết quả.
- **Bên ngoài, ở Java Instrumentation**: `ClassFileTransformer.transform(...)` trả `null` nếu không có class bytes thay thế; nếu muốn đổi bytecode, trả một `byte[]` hợp lệ.

Khi xử lý class **đã nạp**, `Instrumentation.retransformClasses(...)` và `redefineClasses(...)` còn có các giới hạn cấu trúc: không thể tùy tiện thêm/xóa field, đổi method signature hoặc thay supertype như khi tạo một class mới. Việc Class-File API tạo được `byte[]` không có nghĩa JVM bắt buộc chấp nhận nó trong một phép retransform/redefine. Cần kiểm tra capability, modifiability và contract của JVM trước khi áp dụng.

## 9. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ phát method mục tiêu, quên `classBuilder.with(otherElement)` | Field/method/class attribute khác có thể mất | Dùng nhánh `else -> with(element)` |
| Vào `MethodBuilder` nhưng quên `methodBuilder.with(...)` | Method annotation/attribute có thể mất | Chỉ transform `CodeModel`, pass-through phần khác |
| Vào `CodeBuilder` nhưng chỉ sinh instruction mới, bỏ hết label | Nhánh/exception handler có thể bị hỏng | Giữ code elements không đổi; kiểm tra labels |
| Dùng `withMethodBody` cho một method có metadata phong phú | Không tự giữ method attributes | Dùng `transformMethod` hoặc tự phát lại từng attribute |
| Lọc method chỉ bằng tên trong class có overload | Có thể sửa nhầm nhiều method | Lọc thêm descriptor/flags phù hợp |
| Nhầm `builder.with(element)` với `ClassFileTransformer.transform() == null` | Bỏ phần tử trong class mới | Phân biệt phạm vi hai API |
| Kỳ vọng output byte-for-byte giống input | False alarm khi constant pool/stack maps khác | So sánh ngữ nghĩa, metadata và hành vi |
| Parse được nên cho rằng bytes hợp lệ | JVM có thể từ chối khi verify/load | Dùng `verify`, `javap`, test chạy thực |
| Quên Java version | `package java.lang.classfile does not exist` trên JDK cũ | Biên dịch/chạy trên JDK 24+ |
| Thiếu custom attribute mapper | Thuộc tính không được giữ/viết lại đúng ý nghĩa | Cấu hình `AttributeMapper` và test artifact |
| Dùng Class-File API để thêm field vào class đã load rồi retransform | Vi phạm giới hạn JVM TI | Tách load-time transformation khỏi retransform/redefine |
| Reuse builder ngoài callback hoặc sai tầng builder | Sai cấu trúc, lỗi build hoặc race | Chỉ dùng builder trong handler, phát đúng kiểu element |

Trong một công cụ thực tế, hãy có test tự động so sánh **danh sách method/field trước–sau**, các annotations/attributes quan trọng, rồi nạp output để kiểm tra hành vi. Đối với bytecode chứa branches, try/catch, synchronized block hoặc invokedynamic, bổ sung kiểm thử ở mức verifier và runtime tương ứng.

## 10. Quy trình an toàn khi chỉ muốn instrument một phần class

1. **Chọn đúng Java version**: dùng JDK 24+; xác minh runtime của agent nếu tích hợp vào JVM khác.
2. **Parse nguồn** thành `ClassModel`, kiểm tra class name/version/metadata cần giữ.
3. **Xác định tiêu chí chọn method** (name + descriptor, và đôi khi class loader/module) để không sửa nhầm overload.
4. **Dùng `transformClass`**, tại class level chỉ đi sâu vào các `MethodModel` mục tiêu; `with(...)` cho phần khác.
5. **Ở method level**, chỉ đi sâu vào `CodeModel` cần thay đổi, dùng `with(...)` cho các method elements còn lại.
6. **Ở code level**, chỉ thay/chèn các instruction đã phân tích stack/flow, phát `with(...)` cho toàn bộ phần tử không thay.
7. **Kiểm tra output** bằng `ClassFile.verify(newBytes)`, `javap -v/-c`, metadata diff và test chạy.
8. **Nếu đưa vào Instrumentation**, kiểm tra quyền/capability/giới hạn redefine hoặc retransform và xử lý lỗi trong transformer một cách có kiểm soát.

Như vậy, “giữ nguyên phần không thay đổi” không phải một công tắc toàn cục; đó là **hợp đồng phát element rõ ràng ở từng tầng builder**, được hỗ trợ bởi các convenience transforms và khả năng tận dụng phần classfile gốc của API.

## 11. Bài tập và đáp án

**Bài 1.** Trong `ClassTransform`, vì sao callback chỉ xử lý `MethodModel` tên `compute` nhưng không có nhánh `else` là nguy hiểm?

**Bài 2.** Một method có `RuntimeVisibleAnnotations` và `Code`. Bạn chỉ muốn đổi một lệnh `IADD`. Tại sao `transformMethod(...)` với `methodBuilder.transformCode(...)` hợp lý hơn so với tạo lại method bằng `withMethodBody(...)`?

**Bài 3.** Nếu `CodeTransform` gặp một `LabelTarget`, `LineNumber` hoặc instruction không cần sửa, phải làm gì để giữ lại?

**Bài 4.** `ClassFile.verify(updated)` trả danh sách rỗng. Bạn có thể kết luận metadata và hành vi của toàn bộ ứng dụng đã hoàn toàn đúng không?

**Bài 5.** Tại sao `ClassFile.of().transformClass(model, ClassTransform.ACCEPT_ALL)` không bắt buộc cho bytes giống hệt đầu vào?

**Bài 6.** Bạn có một `CodeTransform` đổi `IADD` thành `ISUB`, nhưng chỉ muốn áp dụng cho `compute(int,int)`. Tiện ích nào giúp giữ nguyên các method khác?

**Bài 7.** Agent muốn đổi implementation của một method đã load. `ClassFile.transformClass(...)` sinh ra file class hợp lệ và có thêm một field. Có thể chắc chắn `retransformClasses(...)` chấp nhận không?

**Đáp án:**

1. Trong mô hình *flatMap*, phần tử không được phát vào builder là phần tử bị loại khỏi class file mới. Phải `classBuilder.with(element)` cho mọi thành phần không đổi.
2. `transformMethod` lấy metadata method nguồn; nhánh `methodBuilder.with(member)` giữ các method elements không phải `CodeModel`. `transformCode` chỉ đổi phần code; `withMethodBody` không tự mang theo những method attributes cần giữ.
3. Gọi `codeBuilder.with(element)` với phần tử đó; không được giả định API sẽ tự thêm nó trở lại nếu callback bỏ qua.
4. **Không.** Verifier là một kiểm tra cần thiết, nhưng cần thêm kiểm tra method/field/attribute, kiểm thử hành vi và ràng buộc của môi trường chạy.
5. Vì Class-File API có thể tái cấu trúc constant pool, stack maps hoặc metadata khi build; chuyển tiếp phần tử giữ mô hình tương đương, không cam kết identity từng byte.
6. `ClassTransform.transformingMethodBodies(predicate, codeTransform)`, dùng predicate kiểm tra cả **name và descriptor** khi có overload.
7. **Không.** Thêm field vào class đang load vượt giới hạn thông thường của retransform/redefine, dù class file sinh ra hợp lệ.

## 12. Tài liệu chính thức

- [Java SE 24 — Package `java.lang.classfile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): models, elements, builders, transforms, cách pass-through và constant pool sharing.
- [Java SE 24 — `ClassBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassBuilder.html): `withField`, `withMethod`, `withMethodBody`, `transformMethod`.
- [Java SE 24 — `MethodBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodBuilder.html): `withCode`, `transformCode`, method-level metadata.
- [Java SE 24 — `CodeBuilder`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html): phát JVM instructions, labels, thao tác trên code elements.
- [Java SE 24 — `ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `build`, `transformClass`, `verify`, processing options.
- [Java SE 24 — `ClassTransform` và `MethodTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): các convenience transforms và cách giữ phần không đổi.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): động cơ thiết kế và việc chuẩn hóa API trong JDK 24.
