# Class-File API: từ JEP 457 tới API chính thức trong JDK 24

Class-File API là API chuẩn của Java để đọc, tạo và biến đổi tệp `.class`. Tính năng này xuất hiện lần đầu dưới dạng preview trong JDK 22 qua JEP 457, tiếp tục được hoàn thiện trong JDK 23 và trở thành API chính thức từ JDK 24 qua JEP 484. Khi phát triển ứng dụng hiện đại, hãy học và sử dụng phiên bản API đã được chuẩn hóa trong JDK 24 trở lên; phần preview của JDK 22 chỉ có ý nghĩa lịch sử để hiểu quá trình hình thành tính năng.

API nằm trong package `java.lang.classfile` thuộc module `java.base`, vì vậy không cần thêm thư viện bên ngoài hoặc bật preview khi dùng bản chính thức. API cung cấp một mô hình có cấu trúc cho class file, các builder để sinh class file và các transform để thay đổi những phần cần thiết trong class file hiện có.

## 1. Vì sao Java cần Class-File API?

Sau khi biên dịch, mã nguồn Java được chuyển thành bytecode và lưu trong tệp `.class`. JVM đọc cấu trúc này để nạp, liên kết và thực thi lớp. Một class file không chỉ chứa các lệnh bytecode. Nó còn có phiên bản định dạng, constant pool, cờ truy cập, tên lớp cha, danh sách interface, field, method và nhiều attribute mô tả thông tin bổ sung.

Các công cụ phát triển Java thường cần đọc hoặc thay đổi class file để thực hiện những công việc như:

- Phân tích dependency: xác định một lớp đang gọi method hoặc truy cập field của những lớp nào.
- Sinh bytecode: tạo lớp triển khai proxy, adapter, mã cho framework hoặc mã trung gian của compiler.
- Instrumentation: thêm lệnh ghi log, đo thời gian, thu thập metrics hoặc kiểm tra hành vi.
- Phân tích và kiểm tra mã: phát hiện cách sử dụng API, kiểm tra cấu trúc bytecode hoặc tìm các lời gọi không mong muốn.
- Xử lý class file trong build tool, agent và các công cụ phát triển.

Trước Class-File API, nhà phát triển thường phải tự xử lý định dạng nhị phân hoặc dựa vào thư viện bytecode bên ngoài. Tự xử lý byte thường dễ sai vì constant pool dùng các chỉ mục liên kết chéo, instruction có độ dài khác nhau, lệnh nhảy tham chiếu tới vị trí trong code array và nhiều attribute phụ thuộc vào cấu trúc khác. Chỉ cần thay đổi một phần, công cụ có thể phải cập nhật lại nhiều thông tin liên quan.

Reflection giải quyết một nhu cầu khác: xem thông tin của class đã được JVM nạp. Reflection không cung cấp mô hình để đọc và ghi trực tiếp toàn bộ cấu trúc class file, cũng không phải công cụ để tạo hoặc biến đổi bytecode. Class-File API làm việc trực tiếp với biểu diễn class file, phù hợp với compiler, build tool, bytecode processor và Java agent.

## 2. Từ JEP 457 đến API ổn định

Class-File API được phát triển qua ba mốc chính:

| Phiên bản JDK | JEP | Trạng thái | Ý nghĩa |
| --- | --- | --- | --- |
| JDK 22 | [JEP 457](https://openjdk.org/jeps/457) | Preview lần đầu | Giới thiệu API để đọc, tạo và biến đổi class file. |
| JDK 23 | [JEP 466](https://openjdk.org/jeps/466) | Preview lần thứ hai | Tiếp tục điều chỉnh thiết kế và API dựa trên phản hồi từ lần preview đầu. |
| JDK 24 | [JEP 484](https://openjdk.org/jeps/484) | Chính thức | Chuẩn hóa Class-File API thành API Java SE. |

Điểm cần nhớ khi học một module có phiên bản Java 22 là: **JEP 457 là điểm khởi đầu của tính năng, nhưng API nên dùng hiện nay là phiên bản final từ JDK 24**. Trong hai giai đoạn preview, tên và chữ ký của một số thành phần đã thay đổi. Vì vậy, không lấy ví dụ preview của JDK 22 rồi mặc định rằng chúng vẫn biên dịch được với API final.

Từ JDK 24 trở lên:

- Dùng package `java.lang.classfile` và các package con của nó.
- Không cần `--enable-preview` để sử dụng Class-File API.
- Không cần thêm dependency bên thứ ba chỉ để có API đọc, tạo và biến đổi class file cơ bản.
- Có thể tham chiếu API này khi biên dịch với `--release 24` hoặc một release mới hơn.

Mã nguồn cần chạy trên JDK 22 không thể sử dụng bản API final của JDK 24. Nếu phải hỗ trợ JDK cũ hơn, cần chọn giải pháp bytecode tương thích với baseline đó. Bài này tập trung vào cách dùng API final trong Java hiện đại.

## 3. Class-File API giải quyết những công việc nào?

API cung cấp ba nhóm thao tác chính:

| Thao tác | Điểm vào thường dùng | Kết quả |
| --- | --- | --- |
| Đọc và phân tích | `ClassFile.of().parse(...)` | `ClassModel` biểu diễn cấu trúc class file. |
| Tạo mới | `ClassFile.of().build(...)` hoặc `buildTo(...)` | Mảng byte hoặc tệp `.class` mới. |
| Biến đổi | `ClassFile.of().transformClass(...)` | Class file mới sau khi áp dụng transform. |

Ngoài ra, `ClassFile.verify(...)` hỗ trợ kiểm tra class file và trả về danh sách `VerifyError` nếu phát hiện lỗi trong phạm vi kiểm tra của API.

Một quy trình điển hình có dạng:

```text
Tệp .class / byte[]
        |
        v
ClassFile.of().parse(...)
        |
        v
    ClassModel
        |
        +----> Duyệt model và elements để phân tích
        |
        +----> ClassTransform / MethodTransform / CodeTransform
        |                  |
        |                  v
        |            Builder tương ứng
        |                  |
        +------------------+
                           v
                    byte[] class file mới
                           |
                           v
                     Ghi ra .class
```

## 4. Các khái niệm cốt lõi

### 4.1. `ClassFile`: ngữ cảnh làm việc

`ClassFile` là điểm vào chính để đọc, tạo, biến đổi và xác minh class file. Cách khởi tạo thông thường:

```java
ClassFile classFile = ClassFile.of();
```

`ClassFile.of()` tạo một ngữ cảnh với các tùy chọn mặc định. Khi cần xử lý attribute tùy chỉnh, thông tin phân cấp lớp hoặc các lựa chọn liên quan đến việc sinh bytecode, có thể truyền các `ClassFile.Option` phù hợp vào `ClassFile.of(...)` hoặc tạo ngữ cảnh mới bằng `withOptions(...)`.

### 4.2. Model và Element

Model biểu diễn một cấu trúc có ý nghĩa trong class file. Một số model thường gặp:

| Model | Nội dung biểu diễn |
| --- | --- |
| `ClassModel` | Toàn bộ class file. |
| `FieldModel` | Một field. |
| `MethodModel` | Một method hoặc constructor. |
| `CodeModel` | Nội dung của attribute `Code` trong method. |

Model cũng có thể được duyệt như một chuỗi `Element`. Ví dụ, `ClassModel` cung cấp các `ClassElement`; `MethodModel` cung cấp `MethodElement`; `CodeModel` cung cấp `CodeElement`. Các instruction như gọi method hoặc truy cập field được biểu diễn bởi những element chuyên biệt, chẳng hạn `InvokeInstruction` và `FieldInstruction`.

Có hai cách duyệt phổ biến:

- Truy cập trực tiếp qua accessor như `classModel.methods()` hoặc `classModel.fields()` khi đã biết loại dữ liệu cần lấy.
- Duyệt chuỗi element hoặc dùng `elementStream()` khi cần xử lý tuần tự nhiều loại cấu trúc.

Model và element là các mô tả bất biến. API tạo chúng theo cơ chế lazy: dữ liệu của một phần class file chỉ được phân tích khi phần đó được truy cập. Cách này tránh phải xử lý toàn bộ class file nếu công cụ chỉ quan tâm đến một vài thành phần. Đổi lại, lỗi định dạng có thể chỉ xuất hiện khi gọi accessor tương ứng, thay vì ngay tại thời điểm `parse(...)`.

### 4.3. Builder

Builder dùng để tạo class file hoặc tạo lại một phần cấu trúc trong class file. Các builder thường gặp:

- `ClassBuilder`: tạo cấu trúc lớp.
- `MethodBuilder`: tạo method.
- `CodeBuilder`: phát ra các instruction trong thân method.

API truyền builder vào lambda, vì vậy thông thường không cần tự khởi tạo builder. Các lời gọi trên builder có thể nối tiếp nhau để mô tả cấu trúc cần tạo.

### 4.4. Transform

Transform mô tả cách xử lý một chuỗi element: giữ nguyên, loại bỏ hoặc thay thế element. API cung cấp transform ở nhiều cấp:

- `ClassTransform`: thay đổi element ở cấp class.
- `MethodTransform`: thay đổi element ở cấp method.
- `CodeTransform`: thay đổi element trong thân method.

Các transform có thể được kết hợp hoặc nâng từ cấp thấp lên cấp cao. Ví dụ, một `CodeTransform` có thể được áp dụng cho thân tất cả method thông qua `ClassTransform.transformingMethodBodies(...)`.

### 4.5. Descriptor thay cho chuỗi mô tả tự ghép

Class-File API sử dụng các kiểu mô tả danh nghĩa trong `java.lang.constant`, nổi bật là:

- `ClassDesc`: mô tả một kiểu lớp.
- `MethodTypeDesc`: mô tả kiểu trả về và danh sách tham số của method.

Descriptor giúp biểu diễn kiểu Java theo cấu trúc và giảm lỗi khi tự ghép tên lớp hoặc method descriptor theo định dạng JVM. Khi xây dựng class file, nên ưu tiên các descriptor này ở những API hỗ trợ chúng.

## 5. Đọc và liệt kê thông tin của một class file

Ví dụ sau đọc một tệp `.class`, sau đó in tên lớp, field và method. `parse(Path)` phù hợp khi class file đã nằm trên hệ thống tệp.

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public class InspectClassFile {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: InspectClassFile <path-to-class-file>");
        }

        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(Path.of(args[0]));

        System.out.println("Class: " + model.thisClass().asInternalName());

        model.fields().forEach(field ->
                System.out.println("Field: " + field.fieldName().stringValue()));

        model.methods().forEach(method ->
                System.out.println("Method: " + method.methodName().stringValue()));
    }
}
```

Biên dịch bằng JDK 24 trở lên:

```bash
javac --release 24 -d out src/InspectClassFile.java
```

Chạy chương trình và truyền đường dẫn tới một class file:

```bash
java -cp out InspectClassFile target/classes/com/example/OrderService.class
```

`ClassModel` còn cung cấp các accessor để đọc cờ truy cập, lớp cha, interface, constant pool và attribute. Khi chỉ cần danh sách method hoặc field, dùng accessor tương ứng sẽ dễ đọc hơn việc duyệt toàn bộ element.

## 6. Phân tích các lớp được tham chiếu trong bytecode

Một trường hợp thực tế là tìm các lớp mà method sử dụng thông qua lệnh gọi method và truy cập field. Đoạn mã sau duyệt từ class xuống method, rồi xuống `CodeModel` để thu thập chủ sở hữu của các lệnh tương ứng:

```java
import java.lang.classfile.ClassElement;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.MethodElement;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.FieldInstruction;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.util.HashSet;
import java.util.Set;

public class FindBytecodeDependencies {
    public static Set<ClassDesc> findDependencies(ClassModel classModel) {
        Set<ClassDesc> dependencies = new HashSet<>();

        for (ClassElement classElement : classModel) {
            if (classElement instanceof MethodModel method) {
                for (MethodElement methodElement : method) {
                    if (methodElement instanceof CodeModel code) {
                        for (CodeElement codeElement : code) {
                            switch (codeElement) {
                                case InvokeInstruction instruction ->
                                        dependencies.add(
                                                instruction.owner().asSymbol());
                                case FieldInstruction instruction ->
                                        dependencies.add(
                                                instruction.owner().asSymbol());
                                default -> {
                                    // Bỏ qua các loại instruction khác.
                                }
                            }
                        }
                    }
                }
            }
        }

        return dependencies;
    }
}
```

Ví dụ minh họa cách đi từ cấu trúc cấp cao xuống instruction. Kết quả là tập các lớp xuất hiện trong lệnh gọi method hoặc truy cập field. Nếu công cụ cần phân tích đầy đủ dependency, cần xem xét thêm các nguồn tham chiếu khác như superclass, interface, kiểu field, kiểu tham số, kiểu trả về, annotation, bootstrap method và các attribute liên quan.

## 7. Tạo một class file mới

Builder cho phép tạo class file bằng cách mô tả lớp, method và instruction. Ví dụ sau tạo `Hello.class` với constructor mặc định và method `main` in một dòng ra console.

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.constant.ConstantDescs.*;

public class GenerateHelloClass {
    public static void main(String[] args) throws IOException {
        ClassDesc hello = ClassDesc.of("Hello");
        ClassDesc system = ClassDesc.of("java.lang.System");
        ClassDesc printStream = ClassDesc.of("java.io.PrintStream");

        MethodTypeDesc noArgsVoid = MethodTypeDesc.of(CD_void);
        MethodTypeDesc mainType = MethodTypeDesc.of(
                CD_void, CD_String.arrayType());
        MethodTypeDesc printlnType = MethodTypeDesc.of(CD_void, CD_String);

        byte[] bytes = ClassFile.of().build(hello, classBuilder ->
                classBuilder.withFlags(ClassFile.ACC_PUBLIC)
                        .withMethodBody(
                                INIT_NAME,
                                noArgsVoid,
                                ClassFile.ACC_PUBLIC,
                                code -> code.aload(0)
                                        .invokespecial(CD_Object, INIT_NAME, noArgsVoid)
                                        .return_())
                        .withMethodBody(
                                "main",
                                mainType,
                                ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                                code -> code.getstatic(system, "out", printStream)
                                        .ldc("Hello from Class-File API")
                                        .invokevirtual(
                                                printStream, "println", printlnType)
                                        .return_()));

        Files.write(Path.of("Hello.class"), bytes);
    }
}
```

Biên dịch và chạy chương trình sinh class:

```bash
javac --release 24 -d out src/GenerateHelloClass.java
java -cp out GenerateHelloClass
java -cp . Hello
```

`ClassFile.of().build(...)` trả về byte array. Nếu muốn ghi trực tiếp class file bằng API, có thể dùng `buildTo(Path, ClassDesc, Consumer<ClassBuilder>)`. Ví dụ trên tạo constructor bằng cách nạp `this`, gọi constructor của `Object`, rồi trả về. Method `main` lấy `System.out`, nạp chuỗi, gọi `PrintStream.println` và kết thúc.

Đây là ví dụ tạo bytecode trực tiếp. Khi sinh class file cho ứng dụng thật, cần bảo đảm descriptor, cờ truy cập, thứ tự instruction, kiểu dữ liệu trên operand stack, nhãn nhảy và các attribute liên quan phù hợp với JVM Specification.

## 8. Biến đổi class file bằng `ClassTransform`

Trong nhiều công cụ, ta chỉ muốn thay đổi một vài element và giữ nguyên các phần còn lại. `ClassTransform` hỗ trợ cách làm này. Ví dụ sau loại bỏ các method có tên bắt đầu bằng `debug`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;
import java.nio.file.Files;
import java.nio.file.Path;

public class RemoveDebugMethods {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: RemoveDebugMethods <input.class> <output.class>");
        }

        ClassFile classFile = ClassFile.of();
        ClassModel original = classFile.parse(Path.of(args[0]));

        ClassTransform removeDebugMethods = ClassTransform.dropping(
                element -> element instanceof MethodModel method
                        && method.methodName().stringValue().startsWith("debug"));

        byte[] transformed = classFile.transformClass(
                original, removeDebugMethods);

        Files.write(Path.of(args[1]), transformed);
    }
}
```

`ClassTransform.dropping(...)` nhận một predicate để quyết định element nào cần bỏ. API cũng có thể tạo transform bằng lambda `(builder, element) -> ...`; trong đó `builder.with(element)` chuyển element hiện tại sang kết quả khi muốn giữ nó. Không gọi `builder.with(element)` có nghĩa là transform không phát element đó ra đầu ra.

Ví dụ trên chỉ an toàn khi các method bị loại bỏ không còn được phần khác của chương trình gọi đến, hoặc công cụ đã xử lý các lời gọi phụ thuộc. Việc tạo được byte array không chứng minh rằng lớp vẫn giữ nguyên hành vi hoặc có thể liên kết thành công trong mọi ngữ cảnh.

### Kết hợp `CodeTransform` ở cấp instruction

Khi cần xử lý bytecode bên trong method, dùng `CodeTransform`. Đoạn mã dưới đây minh họa cách duyệt instruction gọi method, giữ nguyên instruction hiện tại và nâng transform lên cấp class. Phần xử lý bên trong `if` là nơi đặt logic phân tích hoặc phát instruction thay thế:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.InvokeInstruction;

// classModel là model đã được đọc từ class file đầu vào.
CodeTransform codeTransform = (builder, element) -> {
    if (element instanceof InvokeInstruction invocation) {
        // Thực hiện xử lý dựa trên instruction gọi method.
        // Có thể phát instruction mới vào builder tại đây.
    }

    builder.with(element); // Giữ instruction hiện tại.
};

ClassTransform classTransform =
        ClassTransform.transformingMethodBodies(codeTransform);

byte[] transformed = ClassFile.of().transformClass(classModel, classTransform);
```

Đoạn mã là khung cấu trúc để minh họa cách kết hợp transform, chưa thay đổi instruction. Khi thay thế một instruction, cần phát instruction mới đúng thứ tự và không đồng thời giữ lại instruction cũ nếu mục tiêu là thay thế. Cũng cần bảo đảm các giá trị trên operand stack, kiểu trả về, exception handler, nhãn nhảy và metadata của method vẫn hợp lệ.

## 9. Kiểm tra kết quả và các điểm cần chú ý

Class-File API giúp thao tác với class file có cấu trúc hơn, nhưng không tự suy luận ý nghĩa nghiệp vụ của phép biến đổi. Một số điểm cần lưu ý khi dùng trong công cụ thật:

### 9.1. Phân tích class file theo cơ chế lazy

`ClassFile.parse(...)` tạo model trước; nhiều phần dữ liệu chỉ được đọc khi accessor tương ứng được gọi. Vì vậy, một class file hỏng có thể làm `parse(...)` thành công nhưng phát sinh `IllegalArgumentException` khi duyệt field, method, instruction hoặc attribute chứa dữ liệu lỗi. Nên đặt xử lý lỗi quanh toàn bộ quá trình truy cập model, không chỉ quanh lời gọi `parse(...)`.

Các model được phân tích lazy cũng không nên mặc định chia sẻ đồng thời giữa nhiều thread. Nếu cần xử lý song song, hãy thiết kế vòng đời model và việc truy cập dữ liệu theo đúng yêu cầu thread-safety của API.

### 9.2. Phiên bản class file phải được runtime hỗ trợ

Runtime chỉ đọc được những phiên bản class file mà implementation hiện tại hỗ trợ. Nếu đầu vào được biên dịch bởi một JDK mới hơn runtime đang chạy công cụ, `parse(...)` có thể ném `IllegalArgumentException`. Có thể dùng `ClassFile.latestMajorVersion()` để biết major version mới nhất mà runtime hiện tại hỗ trợ.

Trong pipeline build, nên chọn JDK chạy công cụ tương thích với phiên bản class file đầu vào và đầu ra. Không nên giả định rằng API chạy trên JDK 24 sẽ đọc được mọi class file được tạo bởi các JDK phát hành sau đó.

### 9.3. Attribute có thể phụ thuộc vào cấu trúc đang thay đổi

Class file chứa nhiều attribute, trong đó có attribute chuẩn và attribute riêng của công cụ hoặc nền tảng. API có mapper cho các attribute chuẩn và cho phép đăng ký `AttributeMapper` để đọc/ghi attribute tùy chỉnh.

Khi biến đổi class file, một số attribute phụ thuộc vào constant pool hoặc nhãn trong bytecode nên API có thể cập nhật chúng. Một số attribute khác phụ thuộc vào cấu trúc mà API không theo dõi đầy đủ. Nếu thay đổi class, method, field hoặc code, cần xác định attribute nào vẫn hợp lệ. Các tùy chọn như `ClassFile.AttributesProcessingOption` cho phép quyết định cách xử lý attribute không thể bảo đảm tính đúng đắn sau transform.

### 9.4. Stack map và thông tin phân cấp lớp

Khi sinh hoặc biến đổi bytecode, JVM cần các metadata phù hợp, trong đó có stack map frame ở những trường hợp yêu cầu. Class-File API có các tùy chọn xử lý stack map và `ClassHierarchyResolver` để cung cấp thông tin phân cấp lớp khi cần.

Resolver mặc định có thể không phù hợp với môi trường có class loader riêng, agent hoặc các lớp chưa thể truy cập qua system class loader. Với các trường hợp đó, cần cung cấp resolver phù hợp thay vì giả định rằng hệ thống có thể tra cứu mọi lớp.

### 9.5. Xác minh class file

Có thể dùng API `verify(...)` để yêu cầu kiểm tra class file:

```java
ClassFile classFile = ClassFile.of();
ClassModel model = classFile.parse(Path.of("Hello.class"));

var errors = classFile.verify(model);
if (!errors.isEmpty()) {
    errors.forEach(System.err::println);
    throw new IllegalStateException("Generated class file is invalid");
}
```

`verify(...)` trả về danh sách `VerifyError`, không thay thế việc chạy kiểm thử trong môi trường thực tế. Sau khi biến đổi bytecode, vẫn nên nạp lớp trong class loader dự kiến và chạy test cho các đường đi quan trọng. Kiểm tra cấu trúc không thể chứng minh rằng phép biến đổi giữ nguyên logic nghiệp vụ.

### 9.6. Không nhầm Class-File API với Reflection hoặc ClassLoader

Class-File API xử lý biểu diễn của class file. Nó không tự nạp class vào JVM, không thực thi bytecode và không thay thế `ClassLoader`, Reflection hoặc Java Instrumentation. Các thành phần này có thể phối hợp trong một công cụ: agent nhận sự kiện nạp lớp, Class-File API phân tích hoặc biến đổi byte array, rồi agent trả về byte array đã xử lý theo hợp đồng của Instrumentation.

## 10. Khi nào nên dùng Class-File API?

Class-File API phù hợp khi ứng dụng hoặc công cụ cần làm việc trực tiếp với cấu trúc class file trên các JDK hiện đại:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Đọc tên lớp, field, method và attribute | `ClassFile.parse(...)`, sau đó truy cập `ClassModel`. |
| Tìm lời gọi method hoặc truy cập field | Duyệt `MethodModel`, `CodeModel` và các instruction element. |
| Sinh một lớp hoặc method mới | Dùng `ClassFile.build(...)`, `ClassBuilder` và `CodeBuilder`. |
| Loại bỏ hoặc thay đổi một số thành phần | Dùng `ClassTransform`, `MethodTransform` hoặc `CodeTransform`. |
| Xử lý attribute riêng | Đăng ký `AttributeMapper` phù hợp. |
| Kiểm tra class file sau biến đổi | Dùng `ClassFile.verify(...)` và kiểm thử khi nạp/chạy lớp. |

API chuẩn trong JDK giúp giảm nhu cầu phụ thuộc vào thư viện bên ngoài đối với các thao tác class file thông dụng. Tuy nhiên, hệ sinh thái thư viện bytecode bên ngoài vẫn có giá trị khi dự án cần hỗ trợ JDK cũ, cần tích hợp với công cụ cụ thể hoặc đang phụ thuộc vào những abstraction riêng của thư viện đó. Hãy chọn theo baseline JDK, yêu cầu tương thích và khả năng bảo trì của dự án.

## 11. Quy trình thực hành đề xuất

Khi xây dựng một công cụ đọc hoặc biến đổi class file, có thể triển khai theo thứ tự sau:

1. **Xác định baseline JDK**: nếu dùng API final, chọn JDK 24 trở lên cho compile và runtime của công cụ.
2. **Đọc class file**: dùng `ClassFile.of().parse(Path)` hoặc `parse(byte[])`.
3. **Chọn đúng phạm vi cần duyệt**: dùng accessor của model nếu chỉ cần metadata; duyệt element nếu cần xử lý nhiều loại cấu trúc.
4. **Xây dựng transform nhỏ và rõ ràng**: tách xử lý class, method và code theo đúng cấp độ thay đổi.
5. **Giữ lại element không liên quan**: khi tự viết transform, chuyển element cần giữ bằng `builder.with(element)`.
6. **Kiểm tra attribute và metadata**: chú ý custom attribute, stack map, nhãn nhảy và class hierarchy.
7. **Xác minh và kiểm thử đầu ra**: dùng `verify(...)`, nạp class trong môi trường đích và chạy test.

Thiết kế transform theo từng thay đổi nhỏ giúp dễ kiểm tra tác động và khoanh vùng lỗi hơn so với việc viết lại toàn bộ class file bằng cách xử lý byte thủ công.

## 12. Kết luận kiến thức cần nhớ

- JEP 457 đưa Class-File API vào JDK 22 dưới dạng preview; JEP 466 là preview lần hai trong JDK 23; JEP 484 chuẩn hóa API trong JDK 24.
- Với Java hiện đại, hãy dùng API final trong `java.lang.classfile` từ JDK 24 trở lên. Không lấy mã preview JDK 22 làm chuẩn cho API hiện tại.
- `ClassFile` là điểm vào; `ClassModel` và `Element` dùng để đọc; các builder dùng để tạo; các transform dùng để thay đổi class file.
- `ClassDesc` và `MethodTypeDesc` biểu diễn thông tin kiểu theo dạng danh nghĩa, giúp xây dựng class file rõ ràng hơn.
- Parse có tính lazy; cần xử lý lỗi khi truy cập model, chú ý phiên bản class file, attribute và class hierarchy.
- Sau khi sinh hoặc biến đổi bytecode, cần xác minh và kiểm thử trong môi trường chạy thực tế.

## Tài liệu tham khảo

- [JEP 457: Class-File API (Preview)](https://openjdk.org/jeps/457) — lần preview đầu trong JDK 22.
- [JEP 466: Class-File API (Second Preview)](https://openjdk.org/jeps/466) — lần preview thứ hai trong JDK 23.
- [JEP 484: Class-File API](https://openjdk.org/jeps/484) — API được chuẩn hóa trong JDK 24.
- [Package `java.lang.classfile` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/package-summary.html) — mô hình đọc, builder, transform, attribute và các tùy chọn hiện hành.
- [Interface `ClassFile` — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html) — các phương thức `of`, `parse`, `build`, `transformClass` và `verify` từ phiên bản final.
