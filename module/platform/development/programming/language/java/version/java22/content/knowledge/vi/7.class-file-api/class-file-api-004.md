# Khảo sát `FieldModel`, `MethodModel`, `CodeModel` và các thuộc tính của class file

Class-File API cung cấp một mô hình có cấu trúc để đọc thông tin trong tệp `.class`. Khi phân tích một lớp, ta thường cần biết lớp có những field nào, mỗi method có descriptor và access flag gì, thân method gồm những instruction nào, và các metadata như generic signature, annotation, exception declaration hay debug information được lưu ở đâu.

API tổ chức dữ liệu thành các model và element. `ClassModel` là model gốc; `FieldModel` và `MethodModel` mô tả thành viên của lớp; `CodeModel` mô tả phần bytecode của một method. Các model này còn cung cấp quyền truy cập tới những attribute gắn với cấu trúc tương ứng. Bài viết tập trung vào cách đọc và duyệt các thành phần đó bằng Class-File API chính thức từ JDK 24 trở lên.

## 1. Phiên bản API cần sử dụng

Class-File API được giới thiệu qua ba mốc:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| JDK 22 | [JEP 457](https://openjdk.org/jeps/457) | Preview lần đầu. |
| JDK 23 | [JEP 466](https://openjdk.org/jeps/466) | Preview lần thứ hai. |
| JDK 24 | [JEP 484](https://openjdk.org/jeps/484) | API chính thức. |

Các ví dụ trong bài dùng package `java.lang.classfile` của API final. Không cần `--enable-preview` và không sử dụng tên hoặc chữ ký của các phiên bản preview cũ. API thuộc module `java.base`, nên không cần thêm dependency bên ngoài.

## 2. Cây model của một class file

Class-File API biểu diễn class file như một cấu trúc phân cấp. Có thể hình dung như sau:

```text
ClassModel
|-- class attributes
|-- FieldModel
|   |-- field metadata
|   `-- field attributes
|-- MethodModel
|   |-- method metadata
|   |-- method attributes
|   `-- CodeModel (nếu method có thân)
|       |-- instructions
|       |-- pseudo-instructions
|       |-- exception handlers
|       `-- code attributes
`-- các class elements khác
```

Mỗi model có hai cách tiếp cận dữ liệu:

- **Truy cập trực tiếp (random access):** dùng các accessor như `ClassModel.fields()`, `ClassModel.methods()`, `MethodModel.code()` hoặc `AttributedElement.attributes()` để lấy đúng phần cần phân tích.
- **Duyệt tuần tự (element traversal):** duyệt các element của model bằng `for-each`, `iterator()` hoặc `elementStream()`. Một model như `FieldModel` cũng là element của `ClassModel`, và `CodeModel` cũng là element của `MethodModel`.

Các model là immutable và được phân tích theo cơ chế lazy. Điều này giúp công cụ chỉ phải đọc sâu những phần nó thực sự truy cập. Ví dụ, chỉ liệt kê tên method không nhất thiết phải giải mã toàn bộ instruction của từng method.

## 3. Đọc `ClassModel`

`ClassModel` là điểm bắt đầu để phân tích một class file. Ta có thể tạo model từ byte array hoặc đường dẫn:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public class ReadClassModel {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ReadClassModel <class-file>");
        }

        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(Path.of(args[0]));

        System.out.println("Class: " + model.thisClass());
        System.out.println("Major version: " + model.majorVersion());
        System.out.println("Fields: " + model.fields().size());
        System.out.println("Methods: " + model.methods().size());

        model.fields().forEach(field ->
                System.out.println("Field: " + field.fieldName().stringValue()));

        model.methods().forEach(method ->
                System.out.println("Method: " + method.methodName().stringValue()));
    }
}
```

`ClassModel` còn cung cấp thông tin như superclass, interfaces, access flags, constant pool và các class attribute. Khi cần phân tích dependency hoặc metadata sâu hơn, nên lấy model này làm gốc rồi đi xuống field, method và code tương ứng.

## 4. Khảo sát `FieldModel`

`FieldModel` mô tả một field được khai báo trong class file. Các accessor quan trọng gồm:

| Accessor | Thông tin |
| --- | --- |
| `fieldName()` | Tên field dưới dạng `Utf8Entry`. |
| `fieldType()` | Field descriptor trong class file, cũng là `Utf8Entry`. |
| `fieldTypeSymbol()` | Kiểu field dưới dạng `ClassDesc`. |
| `flags()` | Access flags và các property flag của field. |
| `attributes()` | Các attribute gắn với field. |
| `elementStream()` | Dòng các `FieldElement` cấu thành model. |

Ví dụ đọc tên, descriptor và kiểu biểu diễn của từng field:

```java
for (FieldModel field : model.fields()) {
    System.out.println("Name: " + field.fieldName().stringValue());
    System.out.println("Descriptor: " + field.fieldType().stringValue());
    System.out.println("Type symbol: "
            + field.fieldTypeSymbol().descriptorString());
    System.out.println("Flags: " + field.flags());
}
```

Descriptor là biểu diễn kiểu theo định dạng JVM. Một số ví dụ:

| Kiểu Java | Field descriptor |
| --- | --- |
| `int` | `I` |
| `long` | `J` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `List<String>` sau type erasure | `Ljava/util/List;` |

Với field generic như `List<String> names`, descriptor chỉ thể hiện kiểu đã xóa generic (`List`). Nếu class file có `Signature` attribute, thông tin generic được lưu riêng và có thể đọc qua `SignatureAttribute`.

### Ví dụ đọc attribute của field

Một field có thể mang các attribute như `ConstantValue`, `Signature`, `Deprecated`, `Synthetic` hoặc annotation. Có thể duyệt danh sách attribute và xử lý theo kiểu cụ thể:

```java
import java.lang.classfile.Attribute;
import java.lang.classfile.FieldModel;
import java.lang.classfile.attribute.ConstantValueAttribute;
import java.lang.classfile.attribute.SignatureAttribute;

for (FieldModel field : model.fields()) {
    System.out.println("Field: " + field.fieldName().stringValue());

    for (Attribute<?> attribute : field.attributes()) {
        System.out.println("  Attribute: "
                + attribute.attributeName().stringValue());

        if (attribute instanceof SignatureAttribute signature) {
            System.out.println("  Generic signature: "
                    + signature.signature().stringValue());
        } else if (attribute instanceof ConstantValueAttribute constant) {
            System.out.println("  Constant pool value: " + constant.constant());
        }
    }
}
```

`ConstantValueAttribute` thường xuất hiện với field `static final` có giá trị hằng được biểu diễn trong class file. Không phải mọi giá trị khởi tạo field đều được lưu dưới dạng attribute này; phép gán thực hiện trong constructor hoặc static initializer nằm trong bytecode của method tương ứng.

## 5. Khảo sát `MethodModel`

`MethodModel` mô tả method hoặc constructor. Nó cũng là một `CompoundElement`, vì vậy có thể truy cập metadata bằng accessor hoặc duyệt các `MethodElement`.

| Accessor | Thông tin |
| --- | --- |
| `methodName()` | Tên method dưới dạng `Utf8Entry`. Constructor thường có tên `<init>`; static initializer có tên `<clinit>`. |
| `methodType()` | Method descriptor dưới dạng `Utf8Entry`. |
| `methodTypeSymbol()` | Kiểu method dưới dạng `MethodTypeDesc`. |
| `flags()` | Access flags của method. |
| `code()` | `Optional<CodeModel>` chứa thân method nếu có. |
| `attributes()` | Các attribute gắn với method. |
| `elementStream()` | Dòng các `MethodElement` cấu thành method. |

Ví dụ đọc thông tin method:

```java
for (MethodModel method : model.methods()) {
    System.out.println("Method: " + method.methodName().stringValue());
    System.out.println("Descriptor: " + method.methodType().stringValue());
    System.out.println("Method type: "
            + method.methodTypeSymbol().descriptorString());
    System.out.println("Flags: " + method.flags());

    System.out.println("Has code: " + method.code().isPresent());
}
```

Method descriptor chứa kiểu tham số và kiểu trả về. Ví dụ, method Java `int sum(int a, int b)` có descriptor `(II)I`; method `void print(String text)` có descriptor `(Ljava/lang/String;)V`.

`methodTypeSymbol()` hữu ích khi muốn làm việc với kiểu method ở dạng biểu tượng thay vì tự phân tích chuỗi descriptor. Nếu cần thông tin generic như `List<String>`, hãy kiểm tra thêm `SignatureAttribute`; method descriptor chỉ chứa kiểu đã xóa generic.

### Vì sao `code()` trả về `Optional`?

Không phải method nào cũng có thân bytecode. Method abstract và native thường không có `Code` attribute, vì vậy `MethodModel.code()` có thể là `Optional.empty()`.

```java
for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        System.out.println(method.methodName().stringValue()
                + " has " + code.exceptionHandlers().size()
                + " exception handlers");
    });
}
```

Không nên giả định mọi method đều có `CodeModel`. Hãy kiểm tra `Optional` trước khi duyệt instruction.

### Các attribute thường gặp của method

| Attribute | Ý nghĩa |
| --- | --- |
| `Code` | Thân bytecode của method; được truy cập qua `MethodModel.code()`. |
| `Exceptions` | Danh sách checked exception được khai báo trong `throws`. |
| `MethodParameters` | Tên và cờ của các tham số method nếu có metadata. |
| `Signature` | Generic signature của method hoặc constructor. |
| `AnnotationDefault` | Giá trị mặc định của phần tử annotation. |
| Runtime annotations | Annotation được giữ lại trong class file ở mức runtime hoặc class. |

Ví dụ đọc `Exceptions` và `Signature`:

```java
import java.lang.classfile.Attribute;
import java.lang.classfile.MethodModel;
import java.lang.classfile.attribute.ExceptionsAttribute;
import java.lang.classfile.attribute.SignatureAttribute;

for (MethodModel method : model.methods()) {
    System.out.println("Method: " + method.methodName().stringValue());

    for (Attribute<?> attribute : method.attributes()) {
        if (attribute instanceof ExceptionsAttribute exceptions) {
            System.out.println("  Declared exceptions: "
                    + exceptions.exceptions());
        } else if (attribute instanceof SignatureAttribute signature) {
            System.out.println("  Generic signature: "
                    + signature.signature().stringValue());
        }
    }
}
```

`ExceptionsAttribute` phản ánh danh sách exception được khai báo trong class file. Nó không liệt kê mọi exception mà method có thể ném khi chạy; một method có thể ném unchecked exception mà không khai báo trong `throws`.

## 6. Khảo sát `CodeModel`

`CodeModel` mô tả phần thân của method, tức cấu trúc `Code` attribute trong class file. Model này được lấy từ `MethodModel.code()` hoặc khi duyệt các member element của method.

Khác với danh sách field hoặc method, **thứ tự các element trong `CodeModel` có ý nghĩa**. Instruction, branch target và một số metadata được sắp theo vị trí tương đối trong code. Khi phân tích hoặc biến đổi code, phải giữ đúng thứ tự này.

`CodeModel` cung cấp:

- Các `CodeElement` thông qua iterator, `forEach()` hoặc `elementStream()`.
- Bảng exception handler qua `exceptionHandlers()`.
- Attribute và metadata liên quan tới thân method qua `attributes()` và các element được mô hình hóa.
- Quan hệ với method cha qua `parent()` nếu model biết method chứa nó.

### Instruction và pseudo-instruction

Các `CodeElement` thường được chia thành hai nhóm:

| Nhóm | Vai trò | Ví dụ |
| --- | --- | --- |
| `Instruction` | Lệnh bytecode thực thi trên JVM. | `InvokeInstruction`, `FieldInstruction`, `LoadInstruction`, `ReturnInstruction`, `BranchInstruction`. |
| `PseudoInstruction` | Metadata gắn với vị trí trong code, không phải opcode thực thi thông thường. | `LabelTarget`, `LineNumber`, `LocalVariable`, `LocalVariableType`, `ExceptionCatch`. |

Ví dụ duyệt lời gọi method, truy cập field và số dòng nguồn:

```java
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.instruction.FieldInstruction;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.classfile.instruction.LineNumber;

for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        System.out.println("Code of " + method.methodName().stringValue());

        for (CodeElement element : code) {
            if (element instanceof InvokeInstruction invocation) {
                System.out.println("  invokes owner: "
                        + invocation.owner().asSymbol());
            } else if (element instanceof FieldInstruction access) {
                System.out.println("  accesses owner: "
                        + access.owner().asSymbol());
            } else if (element instanceof LineNumber lineNumber) {
                System.out.println("  source line: " + lineNumber.line());
            }
        }
    });
}
```

`InvokeInstruction` mô tả lệnh gọi method thông thường; `invokedynamic` có model riêng là `InvokeDynamicInstruction`. `FieldInstruction` mô tả các lệnh đọc hoặc ghi field. Các model instruction cung cấp owner và thông tin constant pool tương ứng, giúp công cụ phân tích dependency mà không phải tự giải mã byte array.

### Exception handler

`CodeModel.exceptionHandlers()` trả về bảng exception handler của method. Đây là thông tin thể hiện các vùng `try/catch` trong bytecode:

```java
for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        code.exceptionHandlers().forEach(handler ->
                System.out.println(method.methodName().stringValue()
                        + " handler: " + handler));
    });
}
```

Exception handler cũng xuất hiện như `ExceptionCatch` pseudo-instruction trong góc nhìn tuần tự của `CodeModel`. Dùng accessor `exceptionHandlers()` khi chỉ cần bảng handler; duyệt element khi cần hiểu vị trí tương đối giữa handler, label và instruction.

## 7. Debug metadata và các tùy chọn duyệt CodeModel

Compiler có thể ghi thông tin debug vào class file, ví dụ:

- `LineNumberTable`: ánh xạ vị trí bytecode tới số dòng nguồn.
- `LocalVariableTable`: tên, kiểu và phạm vi sống của biến cục bộ.
- `LocalVariableTypeTable`: generic signature của biến cục bộ.
- Các label và branch target dùng để mô tả vị trí trong code.

Class-File API mô hình hóa một số thông tin này thành pseudo-instruction như `LineNumber`, `LocalVariable`, `LocalVariableType` và `LabelTarget`. Chúng được đưa vào quá trình duyệt `CodeModel` theo các tùy chọn tương ứng của `ClassFile`, gồm `LineNumbersOption`, `DebugElementsOption` và `DeadLabelsOption`.

Ví dụ, `LineNumber` chỉ xuất hiện theo thiết lập `LineNumbersOption`; các pseudo-instruction debug như local variable phụ thuộc `DebugElementsOption`. Nếu class file không chứa debug metadata (chẳng hạn được biên dịch không có debug info), API không thể tự khôi phục tên biến hoặc số dòng đã bị loại bỏ.

`StackMapTable` là trường hợp đặc biệt: đây là metadata phục vụ xác minh bytecode và được xem là thuộc tính dẫn xuất từ code body. Nó không được biểu diễn như pseudo-instruction thông thường; khi cần đọc attribute này, phải truy cập attribute một cách tường minh. Khi xử lý code, nên ưu tiên `CodeModel` và các element có cấu trúc thay vì tự giải mã `StackMapTable` bằng byte thủ công.

## 8. Các attribute nằm ở đâu?

Attribute là metadata được gắn vào một cấu trúc class file. `AttributedElement` là giao diện chung cung cấp `attributes()`, `findAttribute(...)` và `findAttributes(...)`. Các model class, field, method và code đều có thể cung cấp attribute của riêng mình.

| Vị trí | Ví dụ attribute | Mục đích |
| --- | --- | --- |
| Class | `SourceFile`, `InnerClasses`, `EnclosingMethod`, `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`, `Module` | Mô tả nguồn, cấu trúc lồng nhau, nest, record, sealed class hoặc module. |
| Field | `ConstantValue`, `Signature`, `Deprecated`, annotations | Giá trị hằng, generic type và metadata của field. |
| Method | `Exceptions`, `MethodParameters`, `AnnotationDefault`, `Signature`, annotations | Exception khai báo, tham số, generic signature và annotation. |
| Code | `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, `StackMapTable`, exception table | Debug metadata, xác minh bytecode và xử lý ngoại lệ. |

Có thể liệt kê attribute của từng cấp bằng cùng một cách:

```java
import java.lang.classfile.AttributedElement;

static void printAttributes(String owner, AttributedElement element) {
    element.attributes().forEach(attribute ->
            System.out.println(owner + " -> "
                    + attribute.attributeName().stringValue()));
}

printAttributes("class", model);

for (FieldModel field : model.fields()) {
    printAttributes("field " + field.fieldName().stringValue(), field);
}

for (MethodModel method : model.methods()) {
    String name = method.methodName().stringValue();
    printAttributes("method " + name, method);
    method.code().ifPresent(code -> printAttributes("code " + name, code));
}
```

`attributes()` hữu ích khi muốn khảo sát tên attribute tổng quát. Nếu cần đọc nội dung, nên dùng interface attribute có kiểu cụ thể như `SignatureAttribute`, `ExceptionsAttribute` hoặc `ConstantValueAttribute`, thay vì tự phân tích cấu trúc byte.

Khi đã biết attribute cần tìm, có thể dùng `findAttribute(...)` với mapper được cung cấp trong lớp `Attributes`:

```java
import java.lang.classfile.Attributes;

for (MethodModel method : model.methods()) {
    method.findAttribute(Attributes.exceptions())
            .ifPresent(exceptions ->
                    System.out.println(method.methodName().stringValue()
                            + " declares: " + exceptions.exceptions()));
}
```

`findAttribute(...)` trả về `Optional` vì attribute có thể không xuất hiện. Với attribute cho phép nhiều instance trong cùng cấu trúc, dùng `findAttributes(...)` để lấy danh sách.

### Attribute không phải lúc nào cũng là element thông thường

Nhiều attribute được đưa trực tiếp vào element traversal của model bao quanh. Ví dụ, `SignatureAttribute` có thể là `ClassElement`, `FieldElement` hoặc `MethodElement` tùy vị trí xuất hiện. Tuy nhiên, một số attribute gắn chặt với cấu trúc khác được API xử lý như một phần của cấu trúc đó. `LineNumberTable` và local variable tables được biểu diễn qua pseudo-instruction trong `CodeModel`; `BootstrapMethods` được mô hình hóa cùng constant pool; `StackMapTable` cần được đọc tường minh.

Vì vậy, khi cần đầy đủ dữ liệu, hãy xem cả accessor chuyên biệt, `attributes()` và element traversal. Chỉ duyệt `ClassModel` một lượt không có nghĩa mọi chi tiết nhị phân đều xuất hiện như cùng một loại element.

## 9. Attribute chuẩn, custom attribute và unknown attribute

Class-File API có các interface cho attribute chuẩn của JVM và một số attribute riêng do nền tảng hoặc công cụ định nghĩa. Tên attribute được truy cập qua `attributeName()`; nội dung được đọc bằng interface chuyên biệt.

Hai trường hợp cần phân biệt:

- **Custom attribute:** attribute riêng do công cụ hoặc framework định nghĩa. Có thể cung cấp `AttributeMapper` để chuyển đổi giữa dạng byte trong class file và object attribute trong API.
- **Unknown attribute:** attribute được đọc từ class file nhưng không có mapper phù hợp trong cấu hình hiện tại. API có thể biểu diễn nó bằng `UnknownAttribute`.

Khi xây dựng công cụ cần bảo toàn metadata của framework, hãy cấu hình `ClassFile.AttributeMapperOption` phù hợp. Nếu bỏ qua custom/unknown attribute trong quá trình biến đổi, công cụ có thể làm mất thông tin mà framework khác cần.

Attribute có thể phụ thuộc vào constant pool, label hoặc cấu trúc khác. Không nên tự sao chép raw bytes của attribute sang class file mới nếu các chỉ mục hoặc vị trí liên quan đã thay đổi. Hãy dùng mapper và cơ chế transform của API để dữ liệu được xử lý theo ngữ cảnh.

## 10. Descriptor, constant pool và generic signature

Khi đọc model, ta thường gặp `Utf8Entry`, `ClassEntry` và các loại `PoolEntry` khác. Đây là các biểu diễn có cấu trúc của entry trong constant pool. API cung cấp phương thức chuyển đổi sang symbolic descriptor để tránh phải tự giải mã chuỗi.

| Dữ liệu | Dạng raw/constant pool | Dạng biểu tượng |
| --- | --- | --- |
| Field type | `FieldModel.fieldType()` (`Utf8Entry`) | `FieldModel.fieldTypeSymbol()` (`ClassDesc`) |
| Method descriptor | `MethodModel.methodType()` (`Utf8Entry`) | `MethodModel.methodTypeSymbol()` (`MethodTypeDesc`) |
| Class reference | `ClassEntry` | `ClassDesc` qua `asSymbol()` |
| Generic signature | `SignatureAttribute.signature()` | Có thể phân tích thành `Signature`, `ClassSignature` hoặc `MethodSignature` |

Descriptor mô tả kiểu mà JVM sử dụng sau type erasure. Generic signature giữ thêm thông tin tham số hóa, ví dụ `List<String>`. Vì thế, công cụ phân tích API công khai, framework hoặc schema generic thường cần đọc cả descriptor và `SignatureAttribute`.

`ClassModel.constantPool()` cung cấp góc nhìn chỉ đọc, được nạp lazy, về constant pool. Không cần duyệt constant pool thủ công nếu mục tiêu chỉ là đọc tên field, method hoặc owner của instruction; các model đã cung cấp accessor tương ứng. Hãy dùng constant pool khi cần phân tích các entry hoặc liên kết mà accessor cấp cao không thể hiện trực tiếp.

## 11. Kết hợp duyệt model và element

Ví dụ sau thu thập các lớp được method gọi hoặc truy cập field trong bytecode. Nó minh họa việc đi từ `ClassModel` xuống `MethodModel`, tiếp tục xuống `CodeModel` rồi xử lý instruction:

```java
import java.lang.classfile.ClassElement;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.MethodElement;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.FieldInstruction;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.util.HashSet;
import java.util.Set;

static Set<ClassDesc> findReferencedClasses(ClassModel model) {
    Set<ClassDesc> references = new HashSet<>();

    for (ClassElement classElement : model) {
        if (classElement instanceof MethodModel method) {
            for (MethodElement methodElement : method) {
                if (methodElement instanceof CodeModel code) {
                    for (CodeElement codeElement : code) {
                        if (codeElement instanceof InvokeInstruction invocation) {
                            references.add(invocation.owner().asSymbol());
                        } else if (codeElement instanceof FieldInstruction access) {
                            references.add(access.owner().asSymbol());
                        }
                    }
                }
            }
        }
    }

    return references;
}
```

Đây là một phép phân tích dependency ở mức instruction. Nó không bao quát mọi tham chiếu kiểu trong class file: superclass, interface, field descriptor, method descriptor, annotation, generic signature, bootstrap method và các attribute khác cũng có thể chứa tham chiếu lớp. Nếu cần dependency graph đầy đủ, phải mở rộng phạm vi phân tích tương ứng.

## 12. Lazy parsing và những giới hạn cần lưu ý

Các model được tạo lazy, nên `parse(...)` thành công chưa chứng minh mọi phần của class file đều hợp lệ. Một accessor hoặc quá trình duyệt sâu có thể phát hiện lỗi định dạng và ném `IllegalArgumentException` khi phần dữ liệu đó được phân tích.

Ngoài ra:

- Model immutable nhưng do lazy inflation nên không nên mặc định rằng cùng một model có thể được truy cập đồng thời an toàn từ nhiều thread.
- Class file phải có phiên bản mà runtime hiện tại hỗ trợ. Công cụ chạy trên JDK cũ có thể không đọc được class file được tạo bởi JDK mới hơn.
- Một số attribute hoặc debug element có thể vắng mặt do compiler không ghi chúng hoặc do tùy chọn xử lý của `ClassFile`.
- `MethodModel.code()` có thể rỗng với method không có thân bytecode.
- `CodeModel` phải được duyệt theo thứ tự vì instruction, label và metadata vị trí có quan hệ thứ tự.
- Các attribute custom cần mapper tương ứng nếu muốn diễn giải nội dung thay vì chỉ giữ dưới dạng unknown.

Với công cụ phân tích class file không tin cậy, hãy xử lý lỗi quanh toàn bộ quá trình đọc accessor và duyệt model, không chỉ quanh lời gọi `parse(...)`.

## 13. Quy trình phân tích một class file

Một quy trình thực tế có thể triển khai như sau:

1. **Parse class file:** dùng `ClassFile.of().parse(Path)` hoặc `parse(byte[])` để lấy `ClassModel`.
2. **Đọc metadata cấp lớp:** tên lớp, superclass, interfaces, flags và class attributes.
3. **Duyệt field:** đọc tên, descriptor, symbolic type, flags và attributes.
4. **Duyệt method:** đọc tên, descriptor, symbolic method type, flags và attributes.
5. **Kiểm tra `code()`:** nếu có `CodeModel`, duyệt instruction, pseudo-instruction và exception handler theo thứ tự.
6. **Đọc attribute có kiểu:** dùng các interface trong `java.lang.classfile.attribute` và mapper phù hợp.
7. **Xử lý constant pool khi cần:** ưu tiên symbolic descriptor; chỉ đọc entry trực tiếp khi phân tích yêu cầu chi tiết hơn.
8. **Xử lý lỗi lazy parsing:** bảo đảm các accessor và traversal được thực hiện trong phạm vi xử lý lỗi thích hợp.

## 14. Kiến thức cần nhớ

- `ClassModel` là model gốc; `FieldModel`, `MethodModel` và `CodeModel` biểu diễn các phần có cấu trúc của class file.
- `FieldModel.fieldType()` và `MethodModel.methodType()` trả về descriptor; các phương thức `*Symbol()` cung cấp kiểu biểu tượng `ClassDesc` hoặc `MethodTypeDesc`.
- Generic signature được lưu riêng trong `SignatureAttribute`; descriptor không giữ lại tham số generic đã bị xóa.
- `MethodModel.code()` trả về `Optional<CodeModel>` vì abstract/native method có thể không có thân bytecode.
- `CodeModel` chứa các `CodeElement`; thứ tự instruction và pseudo-instruction có ý nghĩa và phải được giữ khi duyệt hoặc transform.
- `AttributedElement.attributes()` cung cấp attribute tại cấp class, field, method hoặc code; dùng attribute interface có kiểu để đọc nội dung.
- Debug metadata được mô hình hóa qua pseudo-instruction và chịu ảnh hưởng của các `ClassFile.Option` tương ứng.
- Custom attribute cần `AttributeMapper`; attribute không được nhận diện có thể xuất hiện dưới dạng `UnknownAttribute`.
- Model được parse lazy và có thể phát hiện lỗi khi accessor được gọi; không mặc định dùng chung model giữa nhiều thread.
- Dùng API final trong JDK 24 trở lên theo JEP 484; không dùng preview JDK 22/23 cho mã mới.

## Tài liệu tham khảo

- [JEP 484: Class-File API](https://openjdk.org/jeps/484) — chuẩn hóa Class-File API trong JDK 24.
- [JEP 457: Class-File API (Preview)](https://openjdk.org/jeps/457) — mốc preview đầu tiên trong JDK 22.
- [JEP 466: Class-File API (Second Preview)](https://openjdk.org/jeps/466) — mốc preview thứ hai trong JDK 23.
- [Package `java.lang.classfile` — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html) — tổng quan model, element, constant pool và attribute.
- [FieldModel — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/FieldModel.html) — accessor và attribute của field.
- [MethodModel — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html) — descriptor, code và attribute của method.
- [CodeModel — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html) — instruction, exception handler và code attributes.
- [AttributedElement — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/AttributedElement.html) — truy cập attribute theo cấu trúc.
- [Attribute package — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/attribute/package-summary.html) — các attribute chuẩn và custom.
