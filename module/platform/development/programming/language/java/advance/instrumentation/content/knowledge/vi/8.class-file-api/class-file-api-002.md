# ClassFile.parse, ClassModel và cách đọc cây thành phần của lớp

**Chủ đề:** Java Advance → instrumentation → **Class-File API**. Khi phân tích bytecode, một tệp `.class` chứa cấu trúc nhị phân gồm tên lớp, các trường, các phương thức, thuộc tính (attributes), constant pool và mã lệnh của từng phương thức. Kể từ **JDK 24**, gói chuẩn `java.lang.classfile` cung cấp mô hình để **đọc, phân tích, sinh và biến đổi class file** mà không cần tự dịch từng byte hay phụ thuộc ASM cho những tác vụ cơ bản.

Bài học tập trung vào **`ClassFile.of().parse(...)`**, **`ClassModel`** và cách **đi từ lớp xuống field, method, CodeModel, instruction và attributes**. Đây là nền tảng hữu ích trước khi viết các công cụ instrumentation cần tìm đúng lớp/phương thức hoặc quyết định vị trí chèn bytecode.

> **Yêu cầu phiên bản:** Mã chạy độc lập bên dưới dùng **JDK 24 trở lên**. Class-File API từng ở trạng thái preview trong JDK 22–23 và được hoàn thiện trong **JDK 24 (JEP 484)**. Không thể mang các import `java.lang.classfile.*` sang JDK 17 rồi biên dịch như một API chuẩn; cũng không cần `--enable-preview` khi dùng API đã hoàn thiện trên JDK 24+. Ví dụ chỉ đọc class file và không cần Java agent.

## 1. Đọc class file nghĩa là gì?

Một class file có cấu trúc theo **JVMS, Chapter 4**:

```text
ClassFile (tệp .class, dữ liệu nhị phân)
├── magic / minor_version / major_version
├── constant_pool
├── access_flags
├── this_class / super_class / interfaces
├── fields[]
│   └── field_info: name, descriptor, flags, attributes[]
├── methods[]
│   └── method_info: name, descriptor, flags, attributes[]
│       └── Code attribute (nếu có)
│           ├── max_stack / max_locals
│           ├── instructions / operands
│           ├── exception_table
│           └── attributes: lines, locals, stack maps...
└── attributes[]: SourceFile, Signature, annotations, ...
```

Đọc tệp bằng Class-File API **không đồng nghĩa** nạp lớp vào JVM, khởi tạo static fields hay gọi phương thức của lớp đó. `ClassFile.of().parse(...)` tạo đối tượng mô tả cấu trúc class file; đối tượng ấy là **mô hình bất biến nhìn từ bên ngoài** để truy vấn nội dung. Việc truy cập các phần sâu hơn có thể làm thư viện đọc thêm dữ liệu theo nhu cầu (**lazy parsing**).

Một ví dụ cần phân biệt:

- **`ClassFile`**: *ngữ cảnh API* chứa các lựa chọn phân tích/ghi; lấy bằng factory `ClassFile.of()`.
- **`ClassModel`**: *kết quả parse một class file*, là gốc của cây mô hình.
- **`FieldModel`**: một định nghĩa trường, gồm tên, descriptor, flags và field attributes.
- **`MethodModel`**: một định nghĩa phương thức/constructor, gồm chữ ký và method attributes.
- **`CodeModel`**: thân bytecode của một phương thức khi `Code` attribute tồn tại.
- **`ClassElement`, `MethodElement`, `CodeElement`**: các **loại phần tử** có thể duyệt trong từng mô hình.

`ClassModel` không phải một đối tượng `java.lang.Class<?>`. `Class<?>` đại diện cho loại đã được JVM định nghĩa tại runtime (thường thông qua reflection), còn `ClassModel` mô tả một cấu trúc class file được đọc từ **bytes**, kể cả khi nó chưa từng được load.

## 2. Cú pháp chính xác của `ClassFile.parse`

Cách gọi đúng là **tạo context trước, rồi parse trên context**:

```java
ClassFile classFile = ClassFile.of();
ClassModel model = classFile.parse(bytes);
```

Hai dòng là **fragment**: cần import `java.lang.classfile.ClassFile`, `java.lang.classfile.ClassModel` và khai báo `byte[] bytes`. Đừng hiểu tên đề bài “ClassFile.parse” là một phương thức static gọi kiểu `ClassFile.parse(bytes)`.

API JDK 24 có hai kiểu đầu vào thường gặp:

```java
// Cách A: byte[] đã có sẵn, chẳng hạn đọc từ JAR hoặc transformer.
ClassModel modelFromBytes = ClassFile.of().parse(bytes);

// Cách B: đọc trực tiếp từ một Path trỏ tới tệp .class.
ClassModel modelFromPath = ClassFile.of().parse(classPath);
```

Đoạn trên là **fragment minh họa**, với `bytes` là `byte[]` và `classPath` là `java.nio.file.Path`. `parse(Path)` có thể ném `IOException` do đọc file; `parse(byte[])` không có I/O trực tiếp. Cả hai có thể ném `IllegalArgumentException` nếu class file sai cấu trúc hoặc dùng phiên bản class file mà JDK hiện tại không hỗ trợ. Do parser làm việc **theo nhu cầu**, một truy cập sau này như đọc method, constant pool hoặc instruction cũng có thể ném `IllegalArgumentException`.

Ví dụ bọc try/catch trong code ứng dụng:

```java
try {
    ClassModel model = ClassFile.of().parse(path);
    System.out.println(model.thisClass().asInternalName());
} catch (java.io.IOException e) {
    System.err.println("Không đọc được file: " + e.getMessage());
} catch (IllegalArgumentException e) {
    System.err.println("Class file không hợp lệ/không hỗ trợ: " + e.getMessage());
}
```

Đây cũng là **fragment**, giả định `path` đã khai báo là `Path`. Với ứng dụng cần đọc sâu, bắt lỗi ở mức thao tác *toàn bộ traversal*, không chỉ riêng lệnh `parse`.

### 2.1. JDK, module và class-file version

API được xuất từ module **`java.base`**, sử dụng các package:

```text
java.lang.classfile
java.lang.classfile.attribute
java.lang.classfile.constantpool
java.lang.classfile.instruction
```

Trong chương trình thông thường JDK 24+, **không cần thêm Maven dependency**, cũng không cần `--add-exports` hoặc `--add-modules` cho `java.base`. Cần JDK đủ mới cho **mã nguồn gọi API** và cho **class file version** của dữ liệu đầu vào.

Ví dụ: tệp biên dịch bằng `javac --release 24` có major version **68**; JDK 24 biết xử lý định dạng của bản phát hành này. JVM/JDK cũ có thể không hiểu class file major version lớn hơn nó hỗ trợ. `ClassModel.majorVersion()` và `minorVersion()` trả những số này; **không** phải phiên bản Maven của ứng dụng.

## 3. Cây mô hình: từ `ClassModel` xuống code

```text
ClassModel                   Iterable<ClassElement>
│
├── flags(): AccessFlags     [metadata lớp]
├── thisClass(): ClassEntry
├── superclass(): Optional<ClassEntry>
├── interfaces(): List<ClassEntry>
├── constantPool(): ConstantPool
├── attributes(): List<Attribute<?>>
│
├── fields(): List<FieldModel>
│   └── FieldModel            Iterable<FieldElement>
│       ├── fieldName(): Utf8Entry
│       ├── fieldType(): Utf8Entry
│       ├── flags(): AccessFlags
│       └── attributes() / FieldElement(s)
│
└── methods(): List<MethodModel>
    └── MethodModel           Iterable<MethodElement>
        ├── methodName(): Utf8Entry
        ├── methodType(): Utf8Entry
        ├── flags(): AccessFlags
        ├── attributes()
        └── code(): Optional<CodeModel>
            └── CodeModel     Iterable<CodeElement>
                ├── Instruction: iload, iadd, invokespecial, ...
                ├── PseudoInstruction: label, line number, local...
                ├── attributes / exception handlers
                └── các phần tử code liên quan
```

Có **hai cách nhìn** cùng một mô hình:

1. **Truy cập trực tiếp (random-access navigation):** `model.fields()`, `model.methods()`, `model.attributes()`, rồi `method.code()`. Dùng khi biết rõ muốn lấy thông tin nào.
2. **Duyệt thành phần (element traversal):** `for (ClassElement e : model)` hoặc `model.elementStream()`; khi gặp `MethodModel` thì duyệt `MethodElement`; khi gặp `CodeModel` thì duyệt `CodeElement`. Dùng khi muốn đi qua cấu trúc theo tầng hoặc xây một visitor/analysis pipeline.

Một phần tử cũng có thể là mô hình: **`FieldModel` và `MethodModel` đồng thời là `ClassElement`; `CodeModel` đồng thời là `MethodElement`**. Nhờ vậy không cần dựng một “cây DTO” tự viết.

**Quan trọng:** đây là một cây mô hình *logic* để làm việc với class file, không phải “mọi byte trong tệp = một node”. Một số thành phần, đặc biệt `BootstrapMethods`, `StackMapTable`, `LineNumberTable` và `LocalVariableTable`, được thư viện ánh xạ như metadata hoặc pseudo-instructions gắn với các phần khác; không phải tất cả luôn xuất hiện thành một node trong `for (ClassElement e : model)`.

## 4. Các getter quan trọng của `ClassModel`

| Getter | Trả về | Diễn giải |
| --- | --- | --- |
| `thisClass()` | `ClassEntry` | Tên kiểu đang được mô tả; `asInternalName()` cho `demo/Example` |
| `superclass()` | `Optional<ClassEntry>` | Không có giá trị với `java/lang/Object` hoặc module descriptor |
| `interfaces()` | `List<ClassEntry>` | Các interface được khai báo trực tiếp |
| `flags()` | `AccessFlags` | Tập cờ truy cập và tính chất lớp |
| `majorVersion()`, `minorVersion()` | `int` | Phiên bản class-file format |
| `fields()` | `List<FieldModel>` | Field được khai báo trong class file |
| `methods()` | `List<MethodModel>` | Methods và constructor được khai báo ở class file |
| `constantPool()` | `ConstantPool` | Các entry `CONSTANT_*`, gồm tên, descriptors, references... |
| `attributes()` | `List<Attribute<?>>` | Các thuộc tính gắn với lớp |
| `elementStream()` | `Stream<ClassElement>` | Dòng phần tử trực tiếp thuộc class |
| `isModuleInfo()` | `boolean` | Class file đại diện cho module descriptor hay không |

Đối với tên:

- `model.thisClass().asInternalName()` có thể trả `java/lang/String` hoặc `demo/SampleTarget`. Dấu `/` là **internal name** trong class file. Tên Java trong source thường là `java.lang.String`, với dấu `.`.
- `field.fieldName().stringValue()` lấy tên như `base`; `field.fieldType().stringValue()` lấy **field descriptor** như `I` hoặc `Ljava/lang/String;`.
- `method.methodName().stringValue()` có thể là tên Java hoặc tên đặc biệt **`<init>`** (constructor), **`<clinit>`** (class initializer); `method.methodType().stringValue()` trả descriptor như `(I)V` hay `(I)I`.
- `model.flags().has(java.lang.reflect.AccessFlag.PUBLIC)` là phép kiểm tra một cờ cụ thể; có thể dùng `flags().flags()` để lấy tập `AccessFlag`.

Đừng gọi `toString()` trên một `Utf8Entry` rồi coi output là chuỗi tên ổn định. API cung cấp **`stringValue()`** để lấy giá trị. Tương tự, `ClassEntry.asSymbol()` trả `ClassDesc` biểu diễn kiểu theo descriptor, hữu ích khi cần xử lý ký hiệu type chứ không phải chỉ in tên nội bộ.

## 5. Ví dụ Java 24+ hoàn chỉnh: đọc tên, fields và methods

Ta biên dịch một class có đủ **field, constructor, method có Code và abstract method không có Code**, sau đó đọc bằng Class-File API.

Tạo cấu trúc:

```text
classfile-reader/
└── src/
    ├── ClassTreeReader.java
    └── demo/
        └── SampleTarget.java
```

### 5.1. Tệp `src/demo/SampleTarget.java`

```java
package demo;

public abstract class SampleTarget {
    private final int base;

    protected SampleTarget(int base) {
        this.base = base;
    }

    public int plus(int value) {
        return base + value;
    }

    public abstract int compute(int value);
}
```

`SampleTarget` là **abstract**, vì vậy không có phương thức `main` để tự chạy. Chúng ta chỉ **biên dịch** để tạo class file làm dữ liệu cho chương trình inspector; đây là điều hoàn toàn bình thường khi phân tích bytecode.

### 5.2. Tệp `src/ClassTreeReader.java`

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.FieldModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public final class ClassTreeReader {
    private ClassTreeReader() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ClassTreeReader <path-to-class-file>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));

        System.out.println("CLASS " + model.thisClass().asInternalName());
        System.out.println("SUPER "
                + model.superclass()
                        .map(c -> c.asInternalName())
                        .orElse("<none>"));
        System.out.println("VERSION "
                + model.majorVersion() + "." + model.minorVersion());

        System.out.println("FIELDS " + model.fields().size());
        for (FieldModel field : model.fields()) {
            System.out.println("FIELD "
                    + field.fieldName().stringValue() + " "
                    + field.fieldType().stringValue());
        }

        System.out.println("METHODS " + model.methods().size());
        for (MethodModel method : model.methods()) {
            System.out.println("METHOD "
                    + method.methodName().stringValue() + " "
                    + method.methodType().stringValue() + " CODE="
                    + method.code().isPresent());
        }
    }
}
```

**Chạy:** dùng terminal tại thư mục `classfile-reader`. Tạo thư mục output `out` trước khi biên dịch nếu chưa có (trên Linux/macOS: `mkdir -p out`; trên PowerShell: `New-Item -ItemType Directory -Force out`).

```bash
java -version
javac -version
javac --release 24 -d out src/demo/SampleTarget.java src/ClassTreeReader.java
java -cp out ClassTreeReader out/demo/SampleTarget.class
```

Vì `--release 24` cố định định dạng đầu ra Java 24, **stdout** của lệnh `java -cp out ClassTreeReader ...` với đúng hai tệp trên là:

```text
CLASS demo/SampleTarget
SUPER java/lang/Object
VERSION 68.0
FIELDS 1
FIELD base I
METHODS 3
METHOD <init> (I)V CODE=true
METHOD plus (I)I CODE=true
METHOD compute (I)I CODE=false
```

**Giải thích theo thứ tự output:**

- `CLASS demo/SampleTarget` là **internal name**; `SUPER java/lang/Object` là supertype trực tiếp. Cả hai đọc từ constant-pool references của class file.
- `VERSION 68.0` là major/minor của tệp biên dịch với `--release 24` (không phải Java runtime mà inspector đang chạy).
- `FIELDS 1`: field `base` có descriptor **`I`**, tức `int`. `final`/`private` nằm ở `FieldModel.flags()`, không nằm trong descriptor.
- `METHODS 3`: `<init>(I)V` là constructor nhận một `int` và trả `void`; `plus(I)I` nhận và trả `int`; `compute(I)I` là abstract.
- `CODE=true` chỉ rằng `MethodModel.code()` trả `Optional` có `CodeModel`; `CODE=false` là **không có Code attribute**, đúng với abstract method. Một method `native` cũng không có `Code`.

Vì chỉ cần đọc file, chương trình inspector **không khởi tạo `SampleTarget`, không gọi constructor, không thực thi `plus`**. Không dùng reflection hay `Class.forName` để đọc thông tin class file này.

### 5.3. `ClassFile.parse(byte[])` nếu dữ liệu đã nằm trong bộ nhớ

Trong agent/transformer, thường nhận trực tiếp `byte[] classfileBuffer`. Cú pháp đọc:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;

ClassModel model = ClassFile.of().parse(classfileBuffer);
String internalName = model.thisClass().asInternalName();
```

Đây **chỉ là fragment**; `classfileBuffer` phải có sẵn. Khi áp dụng trong `ClassFileTransformer`, **không ghi đè mảng input do JVM cung cấp**. Parse tạo mô hình đọc; nếu sau này cần biến đổi, dùng builder/transformer của API để tạo **mảng class-file output mới**, và chỉ trả output khi cần theo hợp đồng agent.

## 6. Duyệt `ClassModel` như cây phần tử: `ClassElement → MethodElement → CodeElement`

Lối truy cập ở phần 5 dùng các danh sách `fields()` và `methods()`. Khi muốn **đi hết cây**, ta có thể dùng `for-each` vì mỗi model tương ứng triển khai `Iterable`:

```text
for ClassElement trong ClassModel:
    nếu là FieldModel: xử lý field
    nếu là MethodModel:
        xử lý method
        for MethodElement trong MethodModel:
            nếu là CodeModel:
                for CodeElement trong CodeModel:
                    nếu là Instruction: xử lý opcode
                    nếu là pseudo-instruction: xử lý label/debug metadata
    nếu là class-level attribute: xử lý loại attribute cần thiết
```

Pseudo-code ở trên mô tả **các tầng**, không phải cú pháp Java. Có thể viết Java thật bằng `instanceof`/pattern matching hoặc `switch` có pattern.

### 6.1. Tệp `src/ClassElementWalk.java` chạy độc lập

```java
import java.lang.classfile.ClassElement;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.FieldModel;
import java.lang.classfile.Instruction;
import java.lang.classfile.MethodElement;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public final class ClassElementWalk {
    private ClassElementWalk() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ClassElementWalk <path-to-class-file>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        System.out.println("ROOT " + model.thisClass().asInternalName());

        for (ClassElement element : model) {
            if (element instanceof FieldModel field) {
                System.out.println("  FIELD "
                        + field.fieldName().stringValue());
            } else if (element instanceof MethodModel method) {
                System.out.println("  METHOD "
                        + method.methodName().stringValue());

                for (MethodElement methodElement : method) {
                    if (methodElement instanceof CodeModel code) {
                        System.out.println("    CODE");
                        for (CodeElement codeElement : code) {
                            if (codeElement instanceof Instruction instruction) {
                                System.out.println("      "
                                        + instruction.opcode());
                            }
                        }
                    }
                }
            }
        }
    }
}
```

Biên dịch/run trong cùng project:

```bash
javac --release 24 -d out src/ClassElementWalk.java
java -cp out ClassElementWalk out/demo/SampleTarget.class
```

Output bắt đầu bằng:

```text
ROOT demo/SampleTarget
  FIELD base
  METHOD <init>
    CODE
```

Sau đó sẽ có nhiều opcode như `ALOAD_0`, `INVOKESPECIAL`, `PUTFIELD` và các phần tiếp theo cho `plus`; thứ tự/định dạng đầy đủ tùy bytecode do compiler tạo ra. **Đoạn trên là tiền tố minh họa**, không phải stdout đầy đủ. Với `compute` abstract, bạn sẽ thấy dòng `METHOD compute` nhưng **không có `CODE`** dưới nó.

**Vì sao chỉ in `Instruction`?** `CodeModel` có cả phần tử lệnh thực thi lẫn pseudo-instructions như label, line number, phạm vi local và exception-table entries. Nếu muốn liệt kê **tất cả các CodeElement**, hãy phân loại từng subtype, thay vì giả định `for (CodeElement e : code)` luôn trả opcode. Trong source ở trên, `instanceof Instruction` chủ động bỏ qua pseudo-instructions.

### 6.2. Dùng `elementStream()` khi cần filter/map

`ClassModel`, `MethodModel` và `CodeModel` đều có `elementStream()`:

```java
long methodCount = model.elementStream()
        .filter(e -> e instanceof MethodModel)
        .count();

long codeInstructionCount = model.methods().stream()
        .flatMap(m -> m.code().stream())
        .flatMap(code -> code.elementStream())
        .filter(e -> e instanceof Instruction)
        .count();
```

Đây là **fragment**: cần biến `ClassModel model`, và import `MethodModel`/`Instruction`. `Optional.stream()` giúp method không có `Code` đóng góp **0** element, tránh gọi `.get()` khi `Optional` trống. `codeInstructionCount` là tổng số **instruction objects**, không phải `code_length` tính bằng byte; mỗi opcode có thể dài hơn một byte.

Nếu chỉ cần biết một method có `Code` hay không, `method.code().isPresent()` trực tiếp hơn việc duyệt mọi `MethodElement`.

## 7. Đọc chi tiết một instruction: owner, name, descriptor

Đối với instrumentation, ta thường muốn biết **phương thức đang gọi ai** hoặc **field nào được đọc/ghi**. Trong `CodeElement`, những lệnh có cấu trúc tương ứng được mô hình hóa bởi:

- `InvokeInstruction`: các lời gọi như `invokevirtual`, `invokestatic`, `invokespecial`, `invokeinterface` (**không bao gồm `invokedynamic`**, có model riêng).
- `FieldInstruction`: `getfield`, `putfield`, `getstatic`, `putstatic`.
- `Instruction.opcode()`: trả `Opcode`, có thể in tên mã lệnh; `Instruction.sizeInBytes()` trả kích thước của instruction.
- `InvokeInstruction.owner()` và `FieldInstruction.owner()`: trả `ClassEntry` để xác định lớp/interface sở hữu member. `name()` và `type()` trả `Utf8Entry`, đọc bằng `stringValue()`.

### 7.1. Tệp `src/MemberRefs.java`: tìm các tham chiếu tới method/field

```java
import java.lang.classfile.ClassElement;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.MethodElement;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.FieldInstruction;
import java.lang.classfile.instruction.InvokeInstruction;
import java.nio.file.Path;
import java.util.SortedSet;
import java.util.TreeSet;

public final class MemberRefs {
    private MemberRefs() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: MemberRefs <path-to-class-file>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        SortedSet<String> references = new TreeSet<>();

        for (ClassElement classElement : model) {
            if (classElement instanceof MethodModel method) {
                for (MethodElement methodElement : method) {
                    if (methodElement instanceof CodeModel code) {
                        for (CodeElement codeElement : code) {
                            switch (codeElement) {
                                case InvokeInstruction call ->
                                        references.add("CALL "
                                                + call.owner().asInternalName()
                                                + "."
                                                + call.name().stringValue()
                                                + call.type().stringValue());
                                case FieldInstruction field ->
                                        references.add("FIELD "
                                                + field.owner().asInternalName()
                                                + "."
                                                + field.name().stringValue()
                                                + ":"
                                                + field.type().stringValue());
                                default -> { }
                            }
                        }
                    }
                }
            }
        }

        for (String reference : references) {
            System.out.println(reference);
        }
    }
}
```

Chạy với đúng `SampleTarget.class` từ `--release 24` ở trên:

```bash
javac --release 24 -d out src/MemberRefs.java
java -cp out MemberRefs out/demo/SampleTarget.class
```

Stdout dự kiến cho class mẫu này:

```text
CALL java/lang/Object.<init>()V
FIELD demo/SampleTarget.base:I
```

- Constructor của `SampleTarget` gọi `Object.<init>()V` bằng `invokespecial`.
- Constructor ghi vào `base`, còn `plus` đọc `base`; vì code gom references trong `TreeSet` và **không in opcode**, hai lần truy cập field tạo **một** dòng duy nhất.
- `MemberRefs` là bộ nhận diện dependency theo **field/method instructions**, **không phải bộ phát hiện tất cả dependency của một class**: `invokedynamic`, class literal, method handles, annotations, superclass/interfaces, generic types hoặc bootstrap metadata cần các nhánh phân tích khác.

Nếu cần phân biệt **đọc** với **ghi** field, bổ sung `field.opcode()` vào key; nếu cần phát hiện đúng lệnh gọi mục tiêu, đối chiếu **owner + name + descriptor**, không chỉ tên method.

## 8. Attributes: tại sao không phải mọi dữ liệu đều là “node” thường?

Các **attribute** theo JVMS có thể gắn ở nhiều cấp:

| Cấp | Ví dụ |
| --- | --- |
| Class | `SourceFile`, `Signature`, `RuntimeVisibleAnnotations`, `Record`, `NestMembers` |
| Field | `ConstantValue`, `Signature`, annotations |
| Method | `Code`, `Exceptions`, `Signature`, `MethodParameters` |
| Code | `LineNumberTable`, `LocalVariableTable`, `StackMapTable`, type annotations |

Các model là `AttributedElement`, nên có:

```java
// Fragment: model có kiểu ClassModel.
model.attributes().forEach(attr ->
        System.out.println(attr.attributeName().stringValue()));

// Fragment: chọn đúng mapper khi biết attribute cần tìm.
model.findAttribute(Attributes.sourceFile())
        .ifPresent(sourceAttr ->
                System.out.println(sourceAttr.sourceFile().stringValue()));
```

`Attributes` nằm trong `java.lang.classfile.Attributes`; `sourceFile()` của attribute trả về một `Utf8Entry` mô tả tên file nguồn nếu attribute có trong class file. Đây là **fragment**, cần import `ClassModel`/`Attributes` tương ứng. Nếu class được biên dịch không giữ thông tin nguồn, `findAttribute` trả `Optional.empty()`.

Đặc biệt:

- `BootstrapMethods` được xem như phần cấu trúc gắn với **constant pool**. Đừng chờ nó xuất hiện trong mỗi vòng lặp `ClassElement`.
- `LineNumberTable` và `LocalVariableTable` có thể được tách thành **pseudo-instructions** trong `CodeModel` khi đọc; các option xử lý debug ảnh hưởng việc duyệt.
- `StackMapTable` được gắn chặt với việc xác minh stack frames; đối với mã code thường cần đọc bằng attribute API phù hợp, không phải một `Instruction` thông thường.
- **Custom/unknown attributes** cần `AttributeMapper` hoặc có thể chỉ truy cập dưới dạng `UnknownAttribute` với raw bytes. Tránh tự diễn giải byte lạ theo cấu trúc của một attribute khác.

Để lấy **tên attribute**, `attr.attributeName().stringValue()` là cách rõ ràng; để đọc **nội dung có kiểu**, dùng API của subtype hoặc `findAttribute(Attributes.X())` nếu có mapper.

## 9. Constant pool và descriptors khi đi qua cây

Một `ClassModel` có `constantPool()`, trả mô hình read-only:

```java
var pool = model.constantPool();
for (var entry : pool) {
    System.out.println("#" + entry.index() + " tag=" + entry.tag());
}
```

Đây là **fragment**; cần `ClassModel model`. Việc duyệt `ConstantPool` bằng `for-each` tránh truy cập nhầm slot không sử dụng: entry `long` hoặc `double` chiếm hai vị trí, và `size()` là **giới hạn trên độc quyền của chỉ số hợp lệ**, không phải số entry thực sự.

Các descriptor thông dụng:

| Chuỗi descriptor | Ý nghĩa |
| --- | --- |
| `I` | `int` |
| `J` | `long` |
| `Z` | `boolean` |
| `V` | `void` (trong vị trí return type) |
| `Ljava/lang/String;` | reference `java.lang.String` |
| `[I` | `int[]` |
| `(I)I` | nhận một `int`, trả `int` |
| `(Ljava/lang/String;)V` | nhận `String`, trả `void` |
| `(IJ)Ljava/lang/String;` | nhận `int` và `long`, trả `String` |

**Field descriptor** và **method descriptor** mô tả kiểu JVM đã *erasure*; chúng không chứa toàn bộ thông tin generics Java. Ví dụ `List<String>` có descriptor dùng raw `java/util/List` và thông tin generic nằm trong `Signature` attribute nếu có. Khi định danh method overload, phải xét **tên + descriptor**, không chỉ tên.

## 10. Lazy parsing: lợi ích và bẫy

Javadoc nói `ClassModel` là mô hình **immutable và lazily inflated**: có thể nhận model trước khi parser giải mã toàn bộ class file. Lợi ích là công cụ chỉ quan tâm tới **fields()** không phải giải mã mọi bytecode của **methods()**. Nhưng có các hệ quả:

1. **Lỗi có thể đến muộn:** `ClassFile.of().parse(bytes)` trả về model không có nghĩa mọi cấu trúc sâu đã được kiểm tra. Một `method.code()` hay `InvokeInstruction.owner()` có thể mới phát hiện chỉ số constant pool sai và ném `IllegalArgumentException`.
2. **Không mặc nhiên thread-safe:** tài liệu lưu ý do lazy inflation, các models **có thể không thread-safe**. Trong pipeline chạy song song, tránh dùng chung một model chưa được chuẩn bị giữa nhiều thread nếu chưa có bảo đảm phù hợp; mỗi tác vụ có thể parse mô hình riêng.
3. **Bất biến là giao diện API:** không nên coi model là cây mutable có thể `add/remove` phần tử trực tiếp. Muốn sửa class file, tạo **output mới** thông qua `ClassFile.build(...)` hoặc `transformClass(...)` và các builder/transform; ví dụ đọc ở đây không thay đổi bytes nguồn.
4. **Một phần tử có nhiều vai trò:** `MethodModel` xuất hiện trong `ClassModel.methods()` và trong vòng lặp `ClassModel`. Đó không phải hai phương thức khác nhau; chỉ là hai cách truy cập tới cùng loại mô hình.
5. **Không phải class verifier hoàn chỉnh:** đọc cấu trúc không tự chứng minh JVM sẽ chấp nhận hoặc chương trình có ngữ nghĩa đúng. `ClassFile.verify(...)` hỗ trợ kiểm tra lỗi cấu trúc/bytecode và JVM verification/runtime tests vẫn cần theo nhu cầu.

### 10.1. Khi nào chọn kiểu truy cập nào?

| Nhu cầu | Hướng truy cập |
| --- | --- |
| Chỉ lấy tên lớp, superclass, version | `thisClass()`, `superclass()`, `majorVersion()` |
| Liệt kê tất cả fields | `fields()` |
| Tìm method theo tên và descriptor | `methods().stream().filter(...)` |
| Biết method có thân hay abstract/native | `method.code()` |
| Đếm hoặc lọc opcodes | `method.code().stream()` → `CodeModel.elementStream()` → `Instruction` |
| Phát hiện method/field calls | Lọc `InvokeInstruction` / `FieldInstruction` trong `CodeElement` |
| Xem một attribute cụ thể | `findAttribute(Attributes.someMapper())` |
| Xem toàn bộ các class elements | `for (ClassElement e : model)` hoặc `elementStream()` |
| Đọc thông tin constant pool | `constantPool()` và các subtype `PoolEntry` |

Nếu chỉ cần tên các phương thức, **đừng duyệt toàn bộ bytecode**: `model.methods()` vừa ngắn gọn vừa tận dụng lazy parsing.

## 11. Quan hệ với `javap`, reflection và ASM

| Công cụ/API | Phù hợp với | Điểm khác biệt |
| --- | --- | --- |
| `javap -c -v` | Kiểm tra thủ công class file, xem opcode/constant pool/attributes | Xuất text, tốt để đối chiếu; khó thao tác dữ liệu theo kiểu Java |
| `java.lang.reflect` | Xem class/members đã load trong JVM | Nhắm runtime loaded class; không cho duyệt trực tiếp bytecode instruction |
| **Class-File API `java.lang.classfile`** | Đọc, lọc, phân tích, sinh/biến đổi class file qua API chuẩn JDK 24+ | Mô hình typed immutable/lazy; API theo định dạng class file |
| ASM | Công cụ bytecode có hệ sinh thái rộng và chạy trên nhiều phiên bản Java khác nhau | API/versions riêng; có các mô hình visitor/tree và cơ chế transform khác Class-File API |

Với instrumentation, một hướng làm việc hữu ích là: xác định bytes của class mục tiêu → `ClassFile.of().parse(bytes)` → duyệt `ClassModel.methods()` → tìm đúng name + descriptor → đọc `CodeModel` và các `Instruction` → quyết định biến đổi → dùng API builder/transform tạo bytes mới → kiểm tra class output và hành vi JVM.

**Không nhầm:** “đọc cây thành phần” là kỹ thuật phân tích input; thao tác đó tự thân **không chèn agent**, không sửa class đã load và không gọi `Instrumentation.retransformClasses`.

## 12. Lỗi phổ biến khi viết công cụ đọc cây class file

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `package java.lang.classfile does not exist` | Dùng JDK ≤ 21 hoặc compiler không phải JDK 24+ | Kiểm tra `javac -version`, dùng JDK 24+ cho code hoàn thiện |
| Dùng JDK 22/23 nhưng ví dụ mới không compile | API còn preview, một số chữ ký đã thay đổi | Dùng docs đúng phiên bản hoặc chuyển sang JDK 24+ |
| Gọi `ClassFile.parse(bytes)` như static | `parse` là phương thức của context | Dùng `ClassFile.of().parse(bytes)` |
| `IllegalArgumentException` khi parse hoặc truy cập getter | Class file sai/unsupported version hoặc lỗi phát hiện muộn | Kiểm tra header, version, format, bước getter gây lỗi |
| `NoSuchFileException` | `Path` tương đối tính từ working directory sai | Kiểm tra `pwd` và vị trí `out/demo/SampleTarget.class` |
| Chọn JVM target class bằng `Class.forName` | Đã chuyển sang runtime class loading, có thể gây side effects | Đọc `.class` bytes trực tiếp nếu chỉ cần phân tích |
| `Optional.get()` ném lỗi khi đọc `method.code()` | Method là abstract/native, không có `Code` | Dùng `ifPresent` / `isPresent` hoặc `Optional.stream()` |
| Tưởng `CodeModel` chỉ có opcode | Nó có cả pseudo-instructions và metadata | Lọc `instanceof Instruction`, phân loại phần còn lại |
| Tưởng mọi attribute xuất hiện trong `ClassElement` | Một số attribute được trình bày qua metadata/constant pool | Dùng `attributes()`, `findAttribute` hoặc API riêng |
| Tưởng `majorVersion() == phiên bản JDK chạy tool` | Đó là version của class file đang đọc | Xem `javac --release` và JVMS major versions |
| Tưởng `String` và `Ljava/lang/String;` là cùng chuỗi tên | Một bên là Java name, một bên là field descriptor | Dùng đúng API `ClassEntry`/descriptor |
| So `methodName()` mà bỏ descriptor | Overload cùng tên bị gộp nhầm | So cả `methodType()` |
| Lấy `constantPool().size()` làm số entry thật | Long/double dùng hai slot; index 0 không hợp lệ | Lặp bằng `for (var entry : pool)` |
| Kết luận parse thành công nghĩa code hợp lệ | Lazy parsing và verification tách biệt | Traverse phần cần kiểm và dùng `verify`/runtime tests |
| Truy cập cùng model lazy từ nhiều thread | Không được bảo đảm thread-safety | Chọn mô hình xử lý mỗi tác vụ riêng hoặc cơ chế đồng bộ đã kiểm chứng |

## 13. Câu hỏi tự kiểm tra

1. **`ClassFile.parse` là static method của `ClassFile`?**  
   Không. Cách dùng chính xác là **`ClassFile.of().parse(bytes)`** hoặc **`ClassFile.of().parse(path)`**.
2. **`ClassModel` có phải `Class<?>` đã được JVM load?**  
   Không. Nó là mô hình class file được đọc từ bytes và không yêu cầu class loading.
3. **Hai cách truy cập danh sách methods?**  
   `model.methods()` hoặc duyệt `for (ClassElement e : model)` rồi chọn `e instanceof MethodModel`.
4. **Tại sao `MethodModel` vừa là `ClassElement` vừa là `Iterable<MethodElement>`?**  
   Bởi nó vừa nằm trong class tree, vừa chứa các thành phần riêng của phương thức, cho phép duyệt xuống tầng tiếp theo.
5. **Vì sao `method.code()` là `Optional`?**  
   Phương thức abstract/native không có `Code` attribute.
6. **`CodeModel` có chứa cả metadata lẫn executable instructions?**  
   Có; cần lọc `instanceof Instruction` nếu chỉ quan tâm opcode.
7. **Tại sao vòng lặp `for (var e : model.constantPool())` an toàn hơn tự duyệt index?**  
   Nó bỏ qua slot không sử dụng do `long/double` chiếm hai vị trí.
8. **`ClassFile.of().parse(bytes)` đã bảo đảm mọi getter không ném lỗi?**  
   Không. Lazy parsing cho phép lỗi định dạng xuất hiện ở truy cập sâu.
9. **Muốn tìm invocation đến `foo(int)` cần so gì?**  
   Owner, name và method descriptor, ví dụ `(I)V` nếu trả `void`.
10. **Dùng JDK 17 để biên dịch ví dụ Java 24 có được không?**  
    Không; Class-File API ổn định yêu cầu toolchain JDK 24+.
11. **Đổi object `ClassModel` để thêm method có phải cách sửa bytecode?**  
    Không. Mô hình immutable; phải tạo output bytes mới qua builder/transform.
12. **Một `ClassModel` đại diện cho tất cả các class trong package?**  
    Không. Mỗi model đại diện cho một class file cụ thể; duyệt nhiều lớp thì phải đọc nhiều file.

## 14. Tài liệu gốc để đối chiếu

- **JEP 484 — Class-File API**, hoàn thiện trong JDK 24: https://openjdk.org/jeps/484
- **Oracle JDK 24 — `java.lang.classfile` package**, mô hình lazy, compound elements và options: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html
- **Oracle JDK 24 — `ClassFile`**, `of()`, `parse(byte[])`, `parse(Path)` và `verify`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html
- **Oracle JDK 24 — `ClassModel`**, `fields()`, `methods()`, `thisClass()`, `constantPool()`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html
- **Oracle JDK 24 — `MethodModel`, `CodeModel`**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html và https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html
- **Oracle JDK 24 — `Attribute`, `AttributedElement`, `ConstantPool`**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/Attribute.html
- **Java Virtual Machine Specification 24 — ClassFile structure**: https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html

Khi đọc một class file, hãy bắt đầu bằng **`ClassFile.of().parse(...)`**, dùng **`ClassModel`** để đi từ cấu trúc lớp tới **FieldModel / MethodModel / CodeModel**, và chỉ duyệt `CodeElement` khi thực sự cần phân tích lệnh. Nhờ cách phân cấp này, công cụ instrumentation có thể phân tích đúng đối tượng và hạn chế xử lý bytecode không cần thiết.
